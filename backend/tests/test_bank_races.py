"""C6 (D51): saving an answer for reuse, and deleting a saved answer, never fail under
concurrency. Two real PostgreSQL transactions on separate connections; one side is held at an
exact point (a barrier, not a sleep) while the other is seen waiting on a row lock
(pg_stat_activity), then released: the pattern and helpers of tests/test_lock_order.py.

The hold point is the flush that writes a request's audit event, the last write before it
commits: a save's "application.answer" (its saved answer is written by then, before C6 by that
same flush) and a deletion's "answer_bank.delete" (likewise). So each test runs unchanged against
the code before C6, where it fails as described in its docstring. Synthetic data only."""

import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.audit.models import AuditEvent
from app.modules.identity.models import User
from app.modules.preparation import router as prep
from app.modules.preparation.models import AnswerBankEntry
from tests.test_lock_order import TIMEOUT, Side, lock_waiters, no_errors, wait_until
from tests.test_preparation import answers, new_application, setup_candidate

EDU = "education"  # tricky.html: "Highest level of education completed", with help text
HELP = "Choose the highest level you have finished."
SAVED, DELETED = "application.answer", "answer_bank.delete"


def _apps(api, n=2) -> list[str]:
    setup_candidate(api)
    return [
        new_application(api, fixture="tricky", title=f"Dispatcher {i}")[1]["id"] for i in range(n)
    ]


def _save(app_id: str, label: str):
    """put_answer with "Reuse for this exact question", in its own session (connection)."""
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        body = prep.AnswerIn(key=EDU, value={"label": label}, save_to_bank=True)
        return prep.put_answer(app.id, body, db.get(User, app.user_id), db)


def _delete(entry_id, user_id):
    with SessionLocal() as db:
        return prep.delete_bank(entry_id, db.get(User, user_id), db)


def _rows() -> list[AnswerBankEntry]:
    with SessionLocal() as db:
        return list(db.scalars(select(AnswerBankEntry)).all())


def _count(action: str) -> int:
    with SessionLocal() as db:
        q = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        return db.scalar(q)


def _shown(api, app_id) -> tuple:
    a = answers(api.get(f"/applications/{app_id}/package").json())[EDU]
    return a["source"], a["display"]


class _HeldAtFlush:
    """Holds the thread `name` after the first flush that writes the audit event `action` (its
    rows written, not committed, and so still locked) until `go` is set."""

    def __init__(self, name: str, action: str):
        self.name, self.action = name, action
        self.reached, self.go = threading.Event(), threading.Event()

    def __call__(self, session, _context):
        mine = threading.current_thread().name == self.name and not self.reached.is_set()
        if mine and any(isinstance(o, AuditEvent) and o.action == self.action for o in session.new):
            self.reached.set()
            assert self.go.wait(TIMEOUT), "never released"


def _race(holder: str, action: str, first, second) -> tuple[Side, Side]:
    """`first` runs in thread `holder` and is held at its `action` flush; `second` then starts
    and must block on a row lock; then `first` is released. Returns both sides, finished."""
    held = _HeldAtFlush(holder, action)
    event.listen(Session, "after_flush", held)
    try:
        a = Side(holder, first)
        assert held.reached.wait(TIMEOUT), f"{holder} never reached its {action} flush"
        before = lock_waiters()
        b = Side("second", second)
        wait_until(lambda: lock_waiters() > before or not b.thread.is_alive(), "the second waits")
        assert b.thread.is_alive(), (b.error, "the second side did not wait for the first")
        held.go.set()
        return a.join(), b.join()
    finally:
        held.go.set()
        event.remove(Session, "after_flush", held)


@pytest.mark.parametrize("second", ["Master's degree or higher", "Bachelor's degree"])
def test_two_first_saves_of_one_question_from_two_applications_never_fail(api, second):
    """Before C6 the second failed on the unique key (IntegrityError 23505, a 500) and its typed
    answer was lost with it. Now it waits for the first, then updates the saved answer; the
    version moves only if the value does."""
    a1, a2 = _apps(api)
    first, other = _race("first", SAVED, lambda: _save(a1, "Bachelor's degree"),
                         lambda: _save(a2, second))  # fmt: skip
    no_errors(first, other)
    (row,) = _rows()
    assert row.value == {"labels": [second]} and str(row.source_application_id) == a2
    assert row.version == (1 if second == "Bachelor's degree" else 2)
    assert row.help_text == HELP
    assert _shown(api, a1) == ("user_entered", "Bachelor's degree")  # neither typed answer lost
    assert _shown(api, a2) == ("user_entered", second)


def test_two_updates_of_one_saved_answer_count_both_changes(api):
    """Before C6 both requests read version 1 and both wrote 2 (a lost version). Now the
    second updates the row as the first left it: version 3, the second value."""
    a1, a2, a3 = _apps(api, 3)
    _save(a1, "Bachelor's degree")
    first, other = _race("first", SAVED, lambda: _save(a2, "Master's degree or higher"),
                         lambda: _save(a3, "High school diploma"))  # fmt: skip
    no_errors(first, other)
    (row,) = _rows()
    assert (row.version, row.value) == (3, {"labels": ["High school diploma"]})
    assert str(row.source_application_id) == a3


def test_a_save_waits_for_the_deletion_of_its_saved_answer(api):
    """Before C6 the save's UPDATE matched no row once the deletion committed (StaleDataError,
    a 500). Now the save waits, then saves a new answer."""
    a1, a2 = _apps(api)
    _save(a1, "Bachelor's degree")
    (old,) = _rows()
    d, s = _race("delete", DELETED, lambda: _delete(old.id, old.user_id),
                 lambda: _save(a2, "Master's degree or higher"))  # fmt: skip
    no_errors(d, s)
    (row,) = _rows()  # the save came second: a new saved answer, nothing left of the old one
    assert row.id != old.id and row.version == 1
    assert row.value == {"labels": ["Master's degree or higher"]}
    assert str(row.source_application_id) == a2 and row.help_text == HELP
    assert _count(DELETED) == 1
    assert _shown(api, a2) == ("user_entered", "Master's degree or higher")


def test_a_deletion_waits_for_a_save_of_its_saved_answer(api):
    """The reverse order (passed before C6 too: a guard on the lock order): the save holds the
    row; the deletion waits, then deletes the updated row."""
    a1, a2 = _apps(api)
    _save(a1, "Bachelor's degree")
    (old,) = _rows()
    s, d = _race("save", SAVED, lambda: _save(a2, "Master's degree or higher"),
                 lambda: _delete(old.id, old.user_id))  # fmt: skip
    no_errors(s, d)
    assert _rows() == [] and _count(DELETED) == 1
    assert _shown(api, a2) == ("user_entered", "Master's degree or higher")


def test_a_second_deletion_of_one_saved_answer_is_not_found(api):
    """Two tabs delete the same saved answer. Before C6 the second returned 204 and recorded a
    second deletion. Now it waits for the first, then finds nothing: 404, one deletion."""
    (a1,) = _apps(api, 1)
    _save(a1, "Bachelor's degree")
    (old,) = _rows()
    d1, d2 = _race("first", DELETED, lambda: _delete(old.id, old.user_id),
                   lambda: _delete(old.id, old.user_id))  # fmt: skip
    no_errors(d1)
    assert isinstance(d2.error, HTTPException) and d2.error.status_code == 404, d2.error
    assert _rows() == [] and _count(DELETED) == 1
