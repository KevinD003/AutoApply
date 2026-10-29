"""One lock order for everything that touches an attempt (E6 follow-up): the attempt row, then
the application row, then the approval row, then what the rehearsal prerequisite relies on (a
rehearsal record or a receipt). These tests race two real PostgreSQL transactions on separate
connections. Each holds one side at an exact point (a barrier, not a sleep), waits until the
other side is blocked on a row lock (read from pg_stat_activity), then releases it. Both
sides must finish within a bounded time: neither hangs, and no deadlock is left for
PostgreSQL to break. The final attempt and application states are checked each time.

A cancellation, withdrawal or deletion that commits before a gate's check stops the gate. One
that arrives while a gate holds its locks waits for it, and once the gate has authorized the
step, it cannot recall what the worker then sends. Synthetic data and the local receiver
only."""

import threading
import time
import uuid

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.modules.applications.models import Application
from app.modules.execution import rehearsal, runner
from app.modules.execution import service as svc
from app.modules.execution.models import Evidence, ExecutionAttempt, RehearsalRecord
from app.modules.preparation import package as pk
from tests.execution_harness import Receiver, attempt, prepared_application, queue

TIMEOUT = 30  # seconds; a side that has not finished by then has hung
MARK = "fixture_ats:e6-*"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


class Hold:
    """Holds the one thread named `name` the first time it reaches the wrapped call: `reached`
    is set there, and it continues when `go` is set (bounded)."""

    def __init__(self, name: str):
        self.name, self.reached, self.go = name, threading.Event(), threading.Event()

    def wrap(self, original, after=False, when=lambda result: True):
        """`after`: hold once the call has returned (and `when(result)` holds), keeping
        whatever the call locked."""

        def wrapper(*args, **kwargs):
            mine = threading.current_thread().name == self.name and not self.reached.is_set()
            if mine and not after:
                self._hold()
            result = original(*args, **kwargs)
            if mine and after and when(result):
                self._hold()
            return result

        return wrapper

    def _hold(self):
        self.reached.set()
        assert self.go.wait(TIMEOUT), "never released"


class Side:
    """One side of a race, in its own thread (and so its own connection)."""

    def __init__(self, name: str, fn):
        self.result, self.error = None, None
        self.thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)
        self.thread.start()

    def _run(self, fn):
        try:
            self.result = fn()
        except BaseException as e:  # noqa: BLE001 - reported by the test
            self.error = e

    def join(self):
        self.thread.join(TIMEOUT)
        assert not self.thread.is_alive(), f"{self.thread.name} hung"
        return self


WAITERS = text(
    "select count(*) from pg_stat_activity "
    "where datname = current_database() and wait_event_type = 'Lock'"
)


def lock_waiters() -> int:
    with engine.connect() as c:
        return c.execute(WAITERS).scalar()


def wait_until(predicate, what: str):
    end = time.monotonic() + TIMEOUT
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"never reached: {what}")


def sqlstate(e) -> str | None:
    return getattr(getattr(e, "orig", None), "sqlstate", None)


def no_errors(*sides):
    for s in sides:
        assert s.error is None, (s.thread.name, type(s.error).__name__, sqlstate(s.error), s.error)


def cancel_in_own_session(app_id: str):
    with SessionLocal() as db:
        out = svc.cancel(db, db.get(Application, uuid.UUID(app_id)))
        db.commit()
        return out


def app_state(app_id: str) -> str:
    with SessionLocal() as db:
        return db.get(Application, uuid.UUID(app_id)).state.value


def claimed(api, receiver, **kw) -> tuple[str, uuid.UUID, int]:
    app_id = prepared_application(api, receiver, **kw)
    aid = uuid.UUID(queue(api, app_id))
    gen = svc.claim(aid, "w1")
    assert gen is not None
    return app_id, aid, gen


def race(monkeypatch, holder: str, target, attr: str, first, second, **wrap):
    """`first` runs in thread `holder` and is held at `target.attr` (before the call, or after
    it with after=True) while holding its earlier locks; `second` then starts and must block
    on a row lock; then `first` is released. Returns both sides, finished."""
    hold = Hold(holder)
    monkeypatch.setattr(target, attr, hold.wrap(getattr(target, attr), **wrap))
    a = Side(holder, first)
    assert hold.reached.wait(TIMEOUT), f"{holder} never reached {attr}"
    before = lock_waiters()
    b = Side("second", second)
    wait_until(lambda: lock_waiters() > before or not b.thread.is_alive(), "the second side waits")
    assert b.thread.is_alive(), (b.error, "the second side did not wait for the first")
    hold.go.set()
    return a.join(), b.join()


# ---------------------------------------------------------------- cancellation and the gates


def test_a_cancel_arriving_while_the_disclosure_gate_holds_its_locks_waits_for_it(
    api, receiver, monkeypatch
):
    """The gate holds the attempt and is about to take the application; the cancel arrives and
    waits. Released, the gate authorizes disclosure; the cancel then cancels the attempt, and
    the worker's next fenced step fails (it must stop). Nothing hangs and nothing deadlocks."""
    app_id, aid, gen = claimed(api, receiver)
    gate, cancel = race(monkeypatch, "gate", pk, "lock_application",
                        lambda: svc.gate_before_disclosure(aid, "w1", gen),
                        lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(gate, cancel)
    a = attempt(str(aid))
    assert a.state == "cancelled" and a.disclosure_started_at is not None
    assert app_state(app_id) == "cancelled"
    with pytest.raises(svc.LostAuthority):  # the worker stops at its next step
        svc.record_evidence(aid, "w1", gen, "disclosure", {"field": "x"})
    assert receiver.ledger()["disclosures"] == []


def test_a_cancel_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it(
    api, receiver, monkeypatch
):
    """The send gate authorizes the click first; the cancel that waited for it is then refused,
    because the submission may already be in flight. The outcome stays the worker's: here it is
    recorded as unknown, which quarantines the application, and nothing is retried."""
    app_id, aid, gen = claimed(api, receiver)
    svc.gate_before_disclosure(aid, "w1", gen)
    gate, cancel = race(monkeypatch, "gate", pk, "lock_application",
                        lambda: svc.gate_before_send(aid, "w1", gen),
                        lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(gate)
    assert isinstance(cancel.error, PermissionError) and "in flight" in str(cancel.error)
    assert attempt(str(aid)).state == "sending" and app_state(app_id) == "submitting"
    assert svc.unknown(aid, "w1", gen, "test: no response")
    assert app_state(app_id) == "submitted_unconfirmed"
    assert svc.sweep(publish_new=False)["repended"] == 0  # never retried


@pytest.mark.parametrize("gate", ["disclosure", "send"])
def test_a_cancel_committed_before_a_gate_checks_stops_that_gate(api, receiver, gate):
    """The cancel holds its locks first; the gate (its snapshot already taken) waits for the
    attempt. When the cancel commits, the gate finds the attempt changed and stops: nothing is
    authorized."""
    app_id, aid, gen = claimed(api, receiver)
    if gate == "send":
        svc.gate_before_disclosure(aid, "w1", gen)
    locked, go = threading.Event(), threading.Event()

    def cancel_then_wait():
        with SessionLocal() as db:
            svc.cancel(db, db.get(Application, uuid.UUID(app_id)))
            locked.set()
            assert go.wait(TIMEOUT)
            db.commit()

    c = Side("cancel", cancel_then_wait)
    assert locked.wait(TIMEOUT)
    before = lock_waiters()
    g = Side("gate", lambda: (svc.gate_before_send if gate == "send"
                              else svc.gate_before_disclosure)(aid, "w1", gen))  # fmt: skip
    wait_until(lambda: lock_waiters() > before or not g.thread.is_alive(), "the gate waits")
    assert g.thread.is_alive(), (g.error, "the gate did not wait")
    go.set()
    c.join(), g.join()
    no_errors(c)
    assert isinstance(g.error, svc.LostAuthority), (type(g.error).__name__, sqlstate(g.error))
    a = attempt(str(aid))
    assert a.state == "cancelled" and a.send_started_at is None
    if gate == "disclosure":
        assert a.disclosure_started_at is None
    assert app_state(app_id) == "cancelled"


def test_a_duplicate_delivery_while_a_gate_holds_the_attempt_is_ignored_without_waiting(
    api, receiver, monkeypatch
):
    """A broker may deliver an attempt twice. While a gate holds the attempt, the second claim
    does not even wait: its compare-and-swap matches only a pending attempt, and this one is
    claimed. It is ignored, and the gate's worker keeps its authority."""
    app_id, aid, gen = claimed(api, receiver)
    hold = Hold("gate")
    monkeypatch.setattr(pk, "lock_application", hold.wrap(pk.lock_application))
    gate = Side("gate", lambda: svc.gate_before_disclosure(aid, "w1", gen))
    assert hold.reached.wait(TIMEOUT)
    dup = Side("second", lambda: svc.claim(aid, "w2")).join()  # finishes while the gate holds
    assert gate.thread.is_alive()
    hold.go.set()
    gate.join()
    no_errors(gate, dup)
    assert dup.result is None
    a = attempt(str(aid))
    assert (a.state, a.lease_owner, a.generation) == ("claimed", "w1", gen)
    assert a.disclosure_started_at is not None
    assert svc.abandon(aid, "w1", gen, "test finished")


def test_a_cancel_arriving_while_a_worker_claims_the_attempt_waits_for_the_claim(
    api, receiver, monkeypatch
):
    """The claim holds the attempt and the application; the cancel waits, then cancels the
    claimed attempt, whose worker stops at its first fenced step. (Were the claim to lock the
    application first and the cancel the attempt first, this would deadlock.)"""
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    claim, cancel = race(monkeypatch, "claim", pk, "lock_application",
                         lambda: svc.claim(aid, "w1"),
                         lambda: cancel_in_own_session(app_id), after=True)  # fmt: skip
    no_errors(claim, cancel)
    assert claim.result is not None
    assert attempt(str(aid)).state == "cancelled" and app_state(app_id) == "cancelled"
    with pytest.raises(svc.LostAuthority):
        svc.gate_before_disclosure(aid, "w1", claim.result)
    assert receiver.ledger()["disclosures"] == []


def test_a_cancel_racing_the_worker_writing_an_outcome_waits_for_it(api, receiver, monkeypatch):
    app_id, aid, gen = claimed(api, receiver)
    worker, cancel = race(monkeypatch, "worker", pk, "lock_application",
                          lambda: svc.fail_safe(aid, "w1", gen, "test: stopped"),
                          lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(worker, cancel)
    assert worker.result is True
    assert attempt(str(aid)).state == "failed_safe"  # the worker's outcome stands
    assert app_state(app_id) == "cancelled"


def test_a_cancel_racing_the_worker_recording_evidence_waits_for_it(api, receiver, monkeypatch):
    """Recording evidence locks the attempt only, but inserting the row also takes a key-share
    lock on its application (the foreign key). That is the same order: attempt, then
    application."""
    app_id, aid, gen = claimed(api, receiver)
    svc.gate_before_disclosure(aid, "w1", gen)
    worker, cancel = race(monkeypatch, "worker", svc, "add_evidence",
                          lambda: svc.record_evidence(aid, "w1", gen, "disclosure", {"n": 1}),
                          lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(worker, cancel)
    with SessionLocal() as db:
        assert db.scalar(select(Evidence).where(Evidence.attempt_id == aid)) is not None
    assert attempt(str(aid)).state == "cancelled" and app_state(app_id) == "cancelled"


def queue_in_own_session(app_id: str):
    from app.modules.applications.service import transition
    from app.modules.applications.states import Actor, AppState

    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        pk.require_valid_approval(db, app)
        transition(db, app, AppState.queued, Actor.user, "test")
        svc.enqueue(db, app)
        db.commit()


def held_queue(monkeypatch, app_id: str) -> tuple[Side, Hold]:
    """A queueing transaction held after it created the attempt, holding the application lock,
    not yet committed (so the attempt is not visible to others yet)."""
    hold = Hold("queue")
    monkeypatch.setattr(svc, "enqueue", hold.wrap(svc.enqueue, after=True))
    q = Side("queue", lambda: queue_in_own_session(app_id))
    assert hold.reached.wait(TIMEOUT)
    return q, hold


def test_a_cancel_waiting_for_a_queueing_transaction_takes_its_new_attempt_too(
    api, receiver, monkeypatch
):
    """The cancel sees no active attempt, then waits for the application while a queueing
    transaction (holding it) creates one. It must not cancel the application and leave that
    attempt pending: after the lock it looks again and cancels the attempt too."""
    app_id = prepared_application(api, receiver)
    q, hold = held_queue(monkeypatch, app_id)
    before = lock_waiters()
    c = Side("cancel", lambda: cancel_in_own_session(app_id))
    wait_until(lambda: lock_waiters() > before or not c.thread.is_alive(), "the cancel waits")
    hold.go.set()
    q.join(), c.join()
    no_errors(q, c)
    with SessionLocal() as db:
        att = db.scalar(select(ExecutionAttempt).where(
            ExecutionAttempt.application_id == uuid.UUID(app_id)))  # fmt: skip
    assert att.state == "cancelled" and app_state(app_id) == "cancelled"


def test_a_cancel_never_waits_for_an_attempt_it_finds_after_the_application_lock(
    api, receiver, monkeypatch
):
    """Three sides. A queueing transaction creates the attempt while the cancel waits for the
    application; the queue commits, the cancel takes the application, and a claim takes the new
    attempt and is about to take the application. Waiting for that attempt now would deadlock
    with the claim, so the cancel does not wait: it is refused (try again). The claim
    proceeds, and a second cancel then holds."""
    app_id = prepared_application(api, receiver)
    q, queue_hold = held_queue(monkeypatch, app_id)
    original = pk.lock_application
    cancel_locked, cancel_go = threading.Event(), threading.Event()
    claim_waits, claim_go = threading.Event(), threading.Event()

    def lock_application(db, aid):
        name = threading.current_thread().name
        if name == "claim" and not claim_waits.is_set():
            claim_waits.set()  # it holds the attempt (its compare-and-swap)
            assert claim_go.wait(TIMEOUT)
        app = original(db, aid)
        if name == "cancel" and not cancel_locked.is_set():
            cancel_locked.set()
            assert cancel_go.wait(TIMEOUT)
        return app

    monkeypatch.setattr(pk, "lock_application", lock_application)
    before = lock_waiters()
    c = Side("cancel", lambda: cancel_in_own_session(app_id))
    wait_until(lambda: lock_waiters() > before, "the cancel waits for the application")
    queue_hold.go.set()
    q.join()
    assert cancel_locked.wait(TIMEOUT)  # the cancel now holds the application
    aid = uuid.UUID(attempt_of(app_id))
    claim = Side("claim", lambda: svc.claim(aid, "w1"))
    assert claim_waits.wait(TIMEOUT)
    cancel_go.set()
    c.join()
    assert isinstance(c.error, PermissionError) and "Try again" in str(c.error), c.error
    claim_go.set()
    claim.join()
    no_errors(q, claim)
    assert claim.result is not None and attempt(str(aid)).state == "claimed"
    assert cancel_in_own_session(app_id) == "cancelled"  # tried again
    assert attempt(str(aid)).state == "cancelled" and app_state(app_id) == "cancelled"


def attempt_of(app_id: str) -> str:
    with SessionLocal() as db:
        return str(db.scalar(select(ExecutionAttempt.id).where(
            ExecutionAttempt.application_id == uuid.UUID(app_id))))  # fmt: skip


# ---------------------------------------------------------------- withdrawal, deletion, gates


@pytest.fixture
def marked(monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", [MARK])


def rehearse(api, receiver, suffix="") -> tuple[str, str]:
    app_id = prepared_application(api, receiver, slug="e6-a", url_suffix=suffix,
                                  scope="disclose_only")  # fmt: skip
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w0") == "rehearsed"
    return app_id, aid


def submission_at_the_send_gate(api, receiver, suffix) -> tuple[str, uuid.UUID, int]:
    app_id, aid, gen = claimed(api, receiver, slug="e6-a", url_suffix=suffix)
    svc.gate_before_disclosure(aid, "w1", gen)
    return app_id, aid, gen


def withdraw_in_own_session(app_id: str, rid: str, hold: threading.Event | None = None,
                            go: threading.Event | None = None):  # fmt: skip
    with SessionLocal() as db:
        svc.withdraw_rehearsal(db, db.get(Application, uuid.UUID(app_id)), uuid.UUID(rid))
        if hold is not None:
            hold.set()
            assert go.wait(TIMEOUT)
        db.commit()


def test_a_withdrawal_arriving_while_the_send_gate_relies_on_the_rehearsal_waits(
    api, receiver, marked, monkeypatch
):
    """The gate holds the rehearsal record FOR SHARE; the withdrawal waits for it. The gate
    authorizes the send; the withdrawal then revokes the record, which counts for later
    submissions only: it does not recall this one."""
    app1, rid = rehearse(api, receiver)
    app2, aid, gen = submission_at_the_send_gate(api, receiver, "?posting=2")
    gate, withdraw = race(monkeypatch, "gate", rehearsal, "_assess",
                          lambda: svc.gate_before_send(aid, "w1", gen),
                          lambda: withdraw_in_own_session(app1, rid))  # fmt: skip
    no_errors(gate, withdraw)
    a = attempt(str(aid))
    assert (a.state, a.rehearsal_prerequisite) == ("sending", "met")
    with SessionLocal() as db:
        assert db.scalar(select(RehearsalRecord)).revoked_reason == "withdrawn_by_user"
    assert svc.unknown(aid, "w1", gen, "test finished")


def test_a_withdrawal_committed_while_the_send_gate_waits_for_the_record_stops_it(
    api, receiver, marked
):
    app1, rid = rehearse(api, receiver)
    app2, aid, gen = submission_at_the_send_gate(api, receiver, "?posting=2")
    locked, go = threading.Event(), threading.Event()
    w = Side("withdraw", lambda: withdraw_in_own_session(app1, rid, locked, go))
    assert locked.wait(TIMEOUT)
    before = lock_waiters()
    g = Side("gate", lambda: svc.gate_before_send(aid, "w1", gen))
    wait_until(lambda: lock_waiters() > before or not g.thread.is_alive(), "the gate waits")
    assert g.thread.is_alive(), (g.error, "the gate did not wait")
    go.set()
    w.join(), g.join()
    no_errors(w)
    assert isinstance(g.error, svc.GateRefused) and g.error.code == "rehearsal_revoked"
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None
    assert svc.abandon(aid, "w1", gen, str(g.error), code=g.error.code)
    assert receiver.ledger()["accepted"] == 0


def established(api, receiver) -> str:
    app1, _ = rehearse(api, receiver)
    assert api.post(f"/applications/{app1}/package/approve", json={
        **{k: api.get(f"/applications/{app1}/package").json()["package"][k]
           for k in ("version", "content_hash")}}).status_code == 200  # fmt: skip
    assert runner.run_attempt(queue(api, app1), "w0") == "confirmed"
    return app1


def delete_evidence_in_own_session(app_id: str, hold=None, go=None):
    with SessionLocal() as db:
        svc.delete_application_evidence(db, db.get(Application, uuid.UUID(app_id)))
        if hold is not None:
            hold.set()
            assert go.wait(TIMEOUT)
        db.commit()


def test_an_evidence_deletion_arriving_while_the_send_gate_relies_on_its_receipt_waits(
    api, receiver, marked, monkeypatch
):
    app1 = established(api, receiver)
    app2, aid, gen = submission_at_the_send_gate(api, receiver, "?posting=2")
    gate, delete = race(monkeypatch, "gate", rehearsal, "_establishes",
                        lambda: svc.gate_before_send(aid, "w1", gen),
                        lambda: delete_evidence_in_own_session(app1), after=True,
                        when=lambda established: established is True)  # fmt: skip
    no_errors(gate, delete)
    a = attempt(str(aid))
    assert (a.state, a.rehearsal_prerequisite) == ("sending", "established")
    with SessionLocal() as db:
        assert db.scalar(select(Evidence).where(Evidence.application_id == uuid.UUID(app1))) is None
    assert svc.unknown(aid, "w1", gen, "test finished")


def test_an_evidence_deletion_committed_while_the_send_gate_waits_for_the_receipt_stops_it(
    api, receiver, marked
):
    app1 = established(api, receiver)
    app2, aid, gen = submission_at_the_send_gate(api, receiver, "?posting=2")
    locked, go = threading.Event(), threading.Event()
    d = Side("delete", lambda: delete_evidence_in_own_session(app1, locked, go))
    assert locked.wait(TIMEOUT)
    before = lock_waiters()
    g = Side("gate", lambda: svc.gate_before_send(aid, "w1", gen))
    wait_until(lambda: lock_waiters() > before or not g.thread.is_alive(), "the gate waits")
    assert g.thread.is_alive(), (g.error, "the gate did not wait")
    go.set()
    d.join(), g.join()
    no_errors(d)
    assert isinstance(g.error, svc.GateRefused) and g.error.code == "rehearsal_revoked"
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None
    assert svc.abandon(aid, "w1", gen, str(g.error), code=g.error.code)
    assert receiver.ledger()["accepted"] == 1  # only the establishing submission


# ---------------------------------------------------------------- preparation inputs


@pytest.mark.parametrize("kind", ["consent", "answer"])
def test_clearing_an_input_while_it_is_being_saved_serializes_instead_of_deadlocking(
    api, receiver, monkeypatch, kind
):
    """Two requests on one question (two tabs, a quick toggle): one clears it, one saves it.
    The clear is held the moment its DELETE of the input has been flushed (row locked, not
    committed). Taking the application before that delete, it then holds the application too,
    so the save waits for it. (Deleting first and locking the application after, at any point,
    deadlocks with the save, which takes the application and then the row.)"""
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.modules.identity.models import User
    from app.modules.preparation import router as prep
    from app.modules.preparation.models import ApplicationInput

    app_id = prepared_application(api, receiver, approve=False)
    # A value other than the stored one, so the save really writes the row.
    key, value = {"consent": ("privacy_ack", {"choice": "decline"}),
                  "answer": ("hear_about", {"label": "Referral (changed)"})}[kind]  # fmt: skip
    reached, go = threading.Event(), threading.Event()

    def after_flush(session, _context):
        deleted = any(isinstance(o, ApplicationInput) for o in session.deleted)
        if threading.current_thread().name == "clear" and deleted and not reached.is_set():
            reached.set()
            assert go.wait(TIMEOUT)

    event.listen(Session, "after_flush", after_flush)

    def clear():
        with SessionLocal() as db:
            app = db.get(Application, uuid.UUID(app_id))
            user = db.get(User, app.user_id)
            if kind == "consent":
                prep.put_consent(app.id, prep.ConsentIn(key=key, choice=None), user, db)
            else:
                prep.clear_answer(app.id, prep.QuestionIn(key=key), user, db)
            db.commit()

    def save():
        with SessionLocal() as db:
            prep._upsert_input(db, db.get(Application, uuid.UUID(app_id)), kind, key, value)
            db.commit()

    try:
        c = Side("clear", clear)
        assert reached.wait(TIMEOUT)
        before = lock_waiters()
        s = Side("save", save)
        wait_until(lambda: lock_waiters() > before or not s.thread.is_alive(), "the save waits")
        assert s.thread.is_alive(), (s.error, "the save did not wait for the clear")
        go.set()
        c.join(), s.join()
    finally:
        event.remove(Session, "after_flush", after_flush)
    no_errors(c, s)
    with SessionLocal() as db:  # the save came second, so its row is what remains
        (row,) = db.scalars(select(ApplicationInput).where(
            ApplicationInput.application_id == uuid.UUID(app_id), ApplicationInput.kind == kind,
            ApplicationInput.field_key == key)).all()  # fmt: skip
        assert row.value == value


# ---------------------------------------------------------------- the stop and the sweeper


def test_a_cancel_racing_the_rehearsal_stop_waits_for_it(api, receiver, monkeypatch):
    from tests.test_rehearsal_stop import at_the_stop, complete, write

    app_id, aid, gen, content = at_the_stop(api, receiver)
    write(aid, gen, complete(content))
    stop, cancel = race(monkeypatch, "stop", pk, "lock_application",
                        lambda: svc.finish_rehearsal(aid, "w1", gen),
                        lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(stop, cancel)
    assert attempt(str(aid)).state == "rehearsed"  # the stop's outcome stands
    assert app_state(app_id) == "cancelled"


def test_a_cancel_racing_the_sweeper_waits_for_it(api, receiver, monkeypatch):
    """The sweeper holds a stale attempt (its worker vanished before disclosing anything) and is
    about to take the application; the cancel waits, then cancels the attempt it re-pended."""
    from app.core.db import utcnow

    app_id, aid, gen = claimed(api, receiver)
    with SessionLocal() as db:
        db.get(ExecutionAttempt, aid).lease_expires_at = utcnow()
        db.commit()
    sweep, cancel = race(monkeypatch, "sweep", pk, "lock_application",
                         lambda: svc.sweep(publish_new=False),
                         lambda: cancel_in_own_session(app_id))  # fmt: skip
    no_errors(sweep, cancel)
    assert sweep.result["repended"] == 1
    assert attempt(str(aid)).state == "cancelled" and app_state(app_id) == "cancelled"


# ---------------------------------------------------------------- what a gate reads


def gate_held_before_the_application(monkeypatch, aid, gen, gate):
    """A gate in its own thread, held after it took the attempt and before the application."""
    hold = Hold("gate")
    monkeypatch.setattr(pk, "lock_application", hold.wrap(pk.lock_application))
    fn = svc.gate_before_send if gate == "send" else svc.gate_before_disclosure
    g = Side("gate", lambda: fn(aid, "w1", gen))
    assert hold.reached.wait(TIMEOUT)
    return g, hold


@pytest.mark.parametrize("gate", ["disclosure", "send"])
@pytest.mark.parametrize("change", ["answer", "profile"])
def test_an_edit_committed_while_a_gate_waits_stops_that_gate(
    api, receiver, monkeypatch, gate, change
):
    """The gate has started (it holds the attempt) when the user changes an answer or the
    profile, and that change commits before the gate checks the content. The gate must see it
    and refuse: it checks what is committed after it holds its locks, not an earlier snapshot."""
    app_id, aid, gen = claimed(api, receiver)
    if gate == "send":
        svc.gate_before_disclosure(aid, "w1", gen)
    g, hold = gate_held_before_the_application(monkeypatch, aid, gen, gate)
    if change == "answer":
        from app.modules.preparation import router as prep

        with SessionLocal() as db:
            prep._upsert_input(db, db.get(Application, uuid.UUID(app_id)), "answer",
                               "hear_about", {"label": "Job board"})  # fmt: skip
            db.commit()
    else:
        profile = api.get("/profile").json()
        assert (
            api.put("/profile", json={**profile, "residence_city": "Shelbyville"}).status_code
            == 200
        )
    hold.go.set()
    g.join()
    assert isinstance(g.error, svc.GateRefused), (type(g.error).__name__, g.error)
    assert "changed after approval" in str(g.error)
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None
    if gate == "disclosure":
        assert a.disclosure_started_at is None
    assert svc.fail_safe(aid, "w1", gen, "test finished") or svc.abandon(aid, "w1", gen, "test")


def test_a_note_saved_while_a_gate_waits_does_not_stop_it(api, receiver, monkeypatch):
    """A change that is not part of the package (the user's notes) is no reason to refuse."""
    app_id, aid, gen = claimed(api, receiver)
    g, hold = gate_held_before_the_application(monkeypatch, aid, gen, "disclosure")
    assert api.patch(f"/applications/{app_id}", json={"notes": "called them"}).status_code == 200
    hold.go.set()
    g.join()
    no_errors(g)
    assert attempt(str(aid)).disclosure_started_at is not None
    assert svc.abandon(aid, "w1", gen, "test finished")


def test_a_write_to_the_approval_waits_for_a_gate_that_holds_it(api, receiver, monkeypatch):
    """Every approval writer also takes the application lock, which the gate holds; the
    approval row lock (FOR SHARE) still serializes a writer that does not, such as retiring an
    approval after a refused queueing."""
    app_id, aid, gen = claimed(api, receiver)
    approval_id = attempt(str(aid)).approval_id

    def retire():
        with SessionLocal() as db:
            svc.retire_approval(db, approval_id, "test: retired")
            db.commit()

    gate, writer = race(monkeypatch, "gate", svc, "_gate_prerequisite",
                        lambda: svc.gate_before_disclosure(aid, "w1", gen), retire)  # fmt: skip
    no_errors(gate, writer)
    assert attempt(str(aid)).disclosure_started_at is not None  # authorized before the write
    assert svc.abandon(aid, "w1", gen, "test finished")


# ---------------------------------------------------------------- queueing again


def orphaned_pending_attempt(api, receiver) -> tuple[str, uuid.UUID]:
    """Queued, then edited before a worker picked it up: the package is rebuilt and the
    application waits for approval again, while its first attempt is still pending."""
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    api.put(f"/applications/{app_id}/answers",
            json={"key": "hear_about", "value": {"label": "Job board"}})  # fmt: skip
    assert app_state(app_id) == "awaiting_approval" and attempt(str(aid)).state == "pending"
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"]}
                    ).status_code == 200  # fmt: skip
    return app_id, aid


def test_queueing_again_stops_an_earlier_attempt_that_can_no_longer_run(api, receiver):
    """The earlier attempt is pending under an approval no longer valid: it can never run and
    has disclosed nothing, so queueing again stops it (before, the second attempt failed as a
    duplicate: an error the user could not get past)."""
    app_id, aid = orphaned_pending_attempt(api, receiver)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        rows = db.scalars(select(ExecutionAttempt).where(
            ExecutionAttempt.application_id == uuid.UUID(app_id))
            .order_by(ExecutionAttempt.created_at)).all()  # fmt: skip
    assert [(a.id == aid, a.state) for a in rows] == [(True, "failed_safe"), (False, "pending")]
    assert app_state(app_id) == "queued"
    assert receiver.ledger()["disclosures"] == []


def test_queueing_again_while_the_earlier_attempt_is_being_claimed_never_deadlocks(
    api, receiver, monkeypatch
):
    """The worker's claim of the earlier attempt holds that attempt and is about to take the
    application. Queueing again (holding the application) must not wait for that attempt: it
    is refused ("try again"), and the claim then finds the approval changed and stops the
    earlier attempt before anything is sent."""
    app_id, aid = orphaned_pending_attempt(api, receiver)
    claim_has_attempt, claim_go = threading.Event(), threading.Event()
    original = pk.lock_application

    def lock_application(db, app):
        if threading.current_thread().name == "claim" and not claim_has_attempt.is_set():
            claim_has_attempt.set()
            assert claim_go.wait(TIMEOUT)
        return original(db, app)

    monkeypatch.setattr(pk, "lock_application", lock_application)
    claim = Side("claim", lambda: svc.claim(aid, "w1"))
    assert claim_has_attempt.wait(TIMEOUT)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "Try again" in r.json()["detail"], r.text
    claim_go.set()
    claim.join()
    no_errors(claim)
    assert claim.result is None and attempt(str(aid)).state == "failed_safe"
    assert receiver.ledger()["disclosures"] == []


# ---------------------------------------------------------------- revoking (C13, D65)


def revoke_in_own_session(app_id: str) -> str:
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        effect = svc.stop_for_revoke(db, app)
        pk.revoke(db, app, effect)
        db.commit()
        return effect


def test_a_revoke_arriving_while_a_worker_claims_the_attempt_waits_then_leaves_it_to_the_gates(
    api, receiver, monkeypatch
):
    """The claim holds the attempt and the application; the revoke waits for it, finds the
    attempt claimed and leaves it to the gates, which refuse the revoked approval."""
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    claim, revoke = race(monkeypatch, "claim", pk, "lock_application",
                         lambda: svc.claim(aid, "w1"),
                         lambda: revoke_in_own_session(app_id), after=True)  # fmt: skip
    no_errors(claim, revoke)
    assert claim.result is not None and revoke.result == "stopping"
    with pytest.raises(svc.GateRefused):
        svc.gate_before_disclosure(aid, "w1", claim.result)
    assert receiver.ledger()["disclosures"] == []


def test_a_revoke_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it(
    api, receiver, monkeypatch
):
    """The send gate authorizes the click first; the revoke that waited for it is refused, and
    the approval stays as it was: revoking could not stop what may already be in flight."""
    app_id, aid, gen = claimed(api, receiver)
    svc.gate_before_disclosure(aid, "w1", gen)
    gate, revoke = race(monkeypatch, "gate", pk, "lock_application",
                        lambda: svc.gate_before_send(aid, "w1", gen),
                        lambda: revoke_in_own_session(app_id))  # fmt: skip
    no_errors(gate)
    assert isinstance(revoke.error, pk.ApprovalError) and revoke.error.code == "revoke_in_flight"
    assert attempt(str(aid)).state == "sending"
    v = api.get(f"/applications/{app_id}/package").json()
    assert v["approval"]["status"] == "approved"
