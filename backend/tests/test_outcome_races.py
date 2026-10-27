"""Outcomes and confirmations race the worker's receipt in one lock order (D46, D53): the
attempts, then the application. Two real PostgreSQL transactions on separate connections; one
side is held at an exact point (a barrier, not a sleep) until the other is blocked on a row
lock. Neither side may fail, hang or deadlock, and the employer's side is read from the
receiver's ledger. Synthetic data and the local receiver only."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.applications import service as app_svc
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.states import Actor, AppState
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import package as pk
from tests.execution_harness import Receiver, prepared_application, queue
from tests.test_lock_order import no_errors, race

EVIDENCE = "Confirmation email REF-1 arrived"  # synthetic


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def _events(app_id):
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == uuid.UUID(app_id))
                .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
            )
        )


def _app(app_id) -> Application:
    with SessionLocal() as db:
        return db.get(Application, uuid.UUID(app_id))


def _while_finishing(app):
    return app is not None and app.state == AppState.submitting


def _run_held(monkeypatch, api, receiver, second):
    """The real worker submits to the receiver and is held inside its final step, holding the
    attempt and the application, while `second` arrives."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    worker, other = race(
        monkeypatch,
        "worker",
        pk,
        "lock_application",
        lambda: runner.run_attempt(aid, "w1"),
        lambda: second(app_id),
        after=True,
        when=_while_finishing,
    )
    no_errors(worker, other)
    assert worker.result == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    return app_id, other.result


def test_an_outcome_recorded_while_the_worker_records_the_receipt_waits_and_decides_on_it(
    api, receiver, monkeypatch
):
    """The outcome waits for the receipt and is then decided on the submission it confirmed;
    before S2 the unlocked PATCH lost the row version and answered 500."""
    app_id, r = _run_held(
        monkeypatch,
        api,
        receiver,
        lambda a: api.patch(f"/applications/{a}", json={"outcome": "interviewing"}),
    )
    assert r.status_code == 200, r.text
    app = _app(app_id)
    assert (app.state, app.outcome.value) == (AppState.submitted_confirmed, "interviewing")
    *_, receipt, outcome = _events(app_id)
    assert (receipt.kind, receipt.source, receipt.actor) == (
        "state_change",
        "receipt",
        Actor.worker,
    )
    assert (outcome.kind, outcome.from_outcome.value, outcome.to_outcome.value) == (
        "outcome",
        "none",
        "interviewing",
    )


def test_a_note_saved_while_the_worker_records_an_outcome_is_not_a_500(api, receiver, monkeypatch):
    app_id, r = _run_held(
        monkeypatch,
        api,
        receiver,
        lambda a: api.patch(f"/applications/{a}", json={"notes": "called them"}),
    )
    assert r.status_code == 200, r.text
    app = _app(app_id)
    assert (app.notes, app.state) == ("called them", AppState.submitted_confirmed)


def test_a_late_receipt_arriving_while_the_user_confirms_waits_and_never_deadlocks(
    api, receiver, monkeypatch
):
    """The user's confirmation holds the attempts and the application; the slow worker's
    receipt waits for the attempt row, then is recorded on the attempt without a second move
    of the application. The employer received it once."""
    receiver.config(mode="drop_after_accept")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    with SessionLocal() as db:
        gen = db.get(ExecutionAttempt, uuid.UUID(aid)).generation

    def confirm_by_user():
        with SessionLocal() as db:
            app = db.get(Application, uuid.UUID(app_id))
            app_svc.lock_submission(db, app)
            app_svc.transition(
                db,
                app,
                AppState.submitted_confirmed,
                Actor.user,
                app_svc.CONFIRMED_BY_YOU,
                evidence_note=EVIDENCE,
            )
            db.commit()
            return True

    user, worker = race(
        monkeypatch,
        "user",
        pk,
        "lock_application",
        confirm_by_user,
        lambda: svc.confirmed(uuid.UUID(aid), "w1", gen, []),
        after=True,
    )
    no_errors(user, worker)
    assert worker.result is True
    into = [e for e in _events(app_id) if e.to_state == AppState.submitted_confirmed]
    assert [(e.actor, e.source) for e in into] == [(Actor.user, "user_claimed")]
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).state == "confirmed"
    assert api.get(f"/applications/{app_id}").json()["submission"] == "receipt"
    assert receiver.ledger()["accepted"] == 1
