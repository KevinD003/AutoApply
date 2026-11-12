"""D150: a request to stop the worker is honoured before the next protected step.

`docker compose stop` sends SIGTERM to the worker's main process, and Celery then waits for the
running task, which runs in a pool process the signal never reaches. Before D150 that attempt
went on and could submit (D144, measured). The main process now sets a flag the pool processes
share (execution/stopping.py), and the runner stops at its next check: before the page is
opened, before each field, document and page's Next, before the send gate, in the wait for a
verification code, and before it claims an attempt. Stopped before anything was entered, the
attempt goes back in the queue for the next worker (as the sweeper does for a killed worker's);
after, it is abandoned and never retried. Past the send gate the click is made and its outcome
read. The runs are against local stand-ins (FIXTURE ASSUMPTIONS), with the receiver's ledger as
the oracle; the last tests send SIGTERM to a real Celery worker. Synthetic data only."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner, stopping
from app.modules.execution import service as svc
from app.modules.execution.models import Checkpoint, OutboxMessage
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue
from tests.test_code_wait_quarantine import open_checkpoint
from tests.test_execution_failures import _browser_application, reached, wait_for


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    stopping.clear()
    yield
    stopping.clear()


def app_state(api, app_id: str) -> str:
    return api.get(f"/applications/{app_id}").json()["state"]


def uploads(led) -> int:
    return sum(1 for d in led["disclosures"] if d["kind"] == "upload")


def waiting_messages(aid: str) -> int:
    """Messages for the attempt that the relay has not published yet."""
    with SessionLocal() as db:
        q = select(OutboxMessage).where(
            OutboxMessage.attempt_id == uuid.UUID(aid), OutboxMessage.dispatched_at.is_(None)
        )
        return len(list(db.scalars(q)))


def checkpoints(aid: str) -> list[tuple[str, str | None]]:
    with SessionLocal() as db:
        rows = db.scalars(select(Checkpoint).where(Checkpoint.attempt_id == uuid.UUID(aid)))
        return [(c.status, c.code) for c in rows]


# ------------------------------------------------------------------------------- the flag

FORKED = """
import os
from app.modules.execution import stopping
r, w = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(w)
    os.read(r, 1)
    os._exit(0 if stopping.requested() else 3)
os.close(r)
before = stopping.requested()
stopping.request()
os.write(w, b"x")
_, status = os.waitpid(pid, 0)
print(before, os.waitstatus_to_exitcode(status))
"""


def test_the_flag_is_shared_with_a_process_forked_after_it_and_starts_cleared():
    """As in a Celery worker: the module is imported, then a process is forked (the pool's);
    the parent's later request is seen in the child. A new interpreter starts cleared. Run in a
    process of its own, so the test process never forks."""
    env = os.environ | {"PYTHONPATH": str(BACKEND)}
    out = subprocess.run([sys.executable, "-c", FORKED], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert out.stdout.split() == ["False", "0"], out.stderr[-800:]


# ------------------------------------------------------------------- each check, in-process

ADAPTERS = ["fixture_ats", "greenhouse_dom", "greenhouse_live", "fixture_workday"]


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_stopped_before_anything_is_entered_the_attempt_goes_back_in_the_queue(
    api, receiver, monkeypatch, adapter
):
    """Requested while the browser starts: the form is never opened, and the attempt goes back
    in the queue with a new message, as the sweeper puts back a killed worker's. The next
    worker runs it, once."""
    app_id = _browser_application(adapter, api, receiver)
    aid = queue(api, app_id)
    before, messages = receiver.ledger()["requests"], waiting_messages(aid)
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_navigate=stop")
    assert runner.run_attempt(aid, "w1") == "requeued"
    a = attempt(aid)
    assert a.adapter == adapter and a.state == "pending" and a.retry_count == 1
    assert a.lease_owner is None and a.disclosure_started_at is None
    assert receiver.ledger()["requests"] == before  # the run asked the employer for nothing
    assert waiting_messages(aid) == messages + 1  # a new message for the relay
    stopping.clear()
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


# point: (documents uploaded before the stop)
AFTER_ENTRY = {"after_disclosure_gate": False, "before_send_gate": True}


@pytest.mark.parametrize("point", list(AFTER_ENTRY))
@pytest.mark.parametrize("adapter", ADAPTERS)
def test_stopped_after_the_disclosure_gate_the_attempt_is_abandoned_for_good(
    api, receiver, monkeypatch, adapter, point
):
    """Right after the disclosure gate: nothing is entered (the check before the first field).
    Right before the send gate: the gate is never passed. Either way data may have reached the
    page, so the attempt is abandoned, the text says why, and it is never run again."""
    app_id = _browser_application(adapter, api, receiver)
    aid = queue(api, app_id)
    messages = waiting_messages(aid)
    monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    a = attempt(aid)
    assert a.adapter == adapter and a.state == "abandoned"
    assert a.outcome_detail.startswith("Stopped after entering data"), a.outcome_detail
    assert runner.STOP_REQUESTED in a.outcome_detail and "internal error" not in a.outcome_detail
    assert a.send_started_at is None and app_state(api, app_id) == "needs_user_action"
    led = receiver.ledger()
    assert led["accepted"] == 0 and (uploads(led) > 0) is AFTER_ENTRY[point]
    assert waiting_messages(aid) == messages  # none added
    stopping.clear()
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "ignored"  # never run again
    assert receiver.ledger()["requests"] == led["requests"]


def test_a_third_stop_in_a_row_before_entry_fails_safe_as_the_sweeper_would(
    api, receiver, monkeypatch
):
    """Put back in the queue at most `max_safe_retries` times (2), the count shared with the
    sweeper's; the next stop ends it failed_safe, as a worker that keeps dying would."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_navigate=stop")
    outcomes = []
    for i in range(3):  # three workers, each asked to stop while its browser starts
        stopping.clear()
        outcomes.append(runner.run_attempt(aid, f"w{i}"))
    assert outcomes == ["requeued", "requeued", "failed_safe"]
    a = attempt(aid)
    assert a.state == "failed_safe" and a.retry_count == 2
    assert a.outcome_detail == "Worker kept stopping before sending anything."
    assert app_state(api, app_id) == "failed_retryable"
    assert receiver.ledger()["accepted"] == 0


def test_after_the_send_gate_the_click_and_its_outcome_are_completed(api, receiver, monkeypatch):
    """Requested right after the send gate: the click is made and its answer recorded. Ending
    the run there would leave an application the employer may have, with no outcome."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_click=stop")
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert attempt(aid).state == "confirmed" and receiver.ledger()["accepted"] == 1


def test_a_worker_asked_to_stop_claims_nothing(api, receiver, monkeypatch):
    """Requested as the task starts: the attempt is not claimed and stays queued, for the next
    worker (the relay publishes it again, D146), which runs it once."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    before = receiver.ledger()["requests"]
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_claim=stop")
    assert runner.run_attempt(aid, "w1") == "stopping"
    a = attempt(aid)
    assert a.state == "pending" and a.lease_owner is None and a.generation == 0
    assert receiver.ledger()["requests"] == before
    stopping.clear()
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize("point,drafts", [("before_next_gate_1", []), ("before_fill_gate_2", [1])])
def test_on_a_wizard_a_stop_request_ends_the_run_before_the_next_page_step(
    api, receiver, monkeypatch, point, drafts
):
    """Before page 1's Next: never clicked, nothing saved at the employer. Before page 2 is
    filled: page 1 was saved, nothing of page 2 is entered. Every approval is retired (pages may
    be saved at the employer, D142)."""
    from tests.test_workday_wizard import all_retired_for_wizard, draft_pages, wizard_application

    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    a = attempt(aid)
    assert a.state == "abandoned" and runner.STOP_REQUESTED in a.outcome_detail
    assert "never made the final submit" in a.outcome_detail
    led = receiver.ledger()
    assert draft_pages(led) == drafts and led["accepted"] == 0
    assert all_retired_for_wizard(app_id)


def test_waiting_for_a_code_a_stop_request_leaves_the_verification_unfinished(
    api, receiver, monkeypatch
):
    """The click was made and the employer asked for a code: no code is entered after the stop
    request. The verification is left unfinished (the approval that made the click is used
    up) and its request is closed."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    monkeypatch.setenv("NOEFFORTS_FAULT", "in_code_wait=stop")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    a = attempt(aid)
    assert a.state == "abandoned"
    assert a.outcome_detail == f"Verification was not completed: {runner.STOP_REQUESTED}"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["challenges"] and not led["challenges"][-1]["done"]
    assert checkpoints(aid) and all(s != "open" and c is None for s, c in checkpoints(aid))
    assert app_state(api, app_id) == "needs_user_action"


def test_a_code_taken_after_the_stop_request_is_never_entered_and_is_erased(
    api, receiver, monkeypatch
):
    """The code is typed and the worker takes it; the stop request comes before it is entered.
    It is never entered, and the request is closed with the code erased."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    take = svc.take_code
    typed = []

    def take_then_stop(*args, **kwargs):
        if not typed:
            cp = open_checkpoint(api, app_id)
            code = receiver.ledger()["challenges"][-1]["code"]
            r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                         json={"round": 1, "code": code})  # fmt: skip
            assert r.status_code == 202, r.text
            typed.append(code)
        out = take(*args, **kwargs)
        if out[0] is not None:
            stopping.request()  # after the worker took it, before it is entered
        return out

    monkeypatch.setattr(svc, "take_code", take_then_stop)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    a = attempt(aid)
    assert a.outcome_detail == f"Verification was not completed: {runner.STOP_REQUESTED}"
    led = receiver.ledger()
    assert typed and led["accepted"] == 0 and not led["challenges"][-1]["done"]
    assert led["challenges"][-1]["attempts"] == 0  # the employer was never given a code
    assert all(c is None for _, c in checkpoints(aid))


@pytest.mark.parametrize("point,state", [("after_claim", "pending"),
                                         ("after_disclosure_gate", "abandoned"),
                                         ("before_send_gate", "abandoned")])  # fmt: skip
def test_on_the_api_route_a_stop_request_ends_the_run_before_its_next_request(
    api, receiver, monkeypatch, point, state
):
    """The API route (no browser) checks at its two gates and before its uploads: before the
    disclosure gate nothing is sent and the attempt goes back in the queue; after it, nothing
    is uploaded; before the send gate the application is never submitted."""
    from tests.test_api_provider import acceptances, api_application, fapi_requests

    app_id = api_application(api)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop")
    assert runner.run_attempt(aid, "w1") == ("requeued" if state == "pending" else "abandoned")
    a = attempt(aid)
    assert a.adapter == "fake_api" and a.state == state
    if state == "abandoned":
        assert runner.STOP_REQUESTED in a.outcome_detail
    assert acceptances(receiver) == []
    led = receiver.ledger()
    assert (uploads(led) > 0) is (point == "before_send_gate")
    if point == "after_claim":
        assert fapi_requests(receiver) == []


# ---------------------------------------------------------------------- a real Celery worker


def _held(point: str):
    """A real worker (prefork, one process, as deployed), held at `point` until released."""
    from tests.test_celery_execution import Worker, clean_broker

    clean_broker()
    gate = tempfile.mktemp(prefix="release-")
    return Worker(fault=f"{point}=waitfile:{gate}", concurrency=1), gate


def _ask_to_stop_then_release(w, gate) -> tuple[int, float]:
    """SIGTERM to the main process, as `docker compose stop` sends first; once Celery has begun
    its warm shutdown, release the held pool process. The exit code, and the seconds from the
    release to the worker's exit."""
    w.p.send_signal(signal.SIGTERM)
    w.wait_log("Warm shutdown", 20)
    released = time.monotonic()
    open(gate, "w").close()
    code = w.p.wait(timeout=90)
    return code, time.monotonic() - released


def _run_held(api, receiver, point: str, app_id: str | None = None):
    from app.worker import publish

    app_id = app_id or prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = _held(point)
    try:
        assert svc.relay_outbox(publish) == 1
        wait_for(lambda: reached(gate), timeout=120)
        code, seconds = _ask_to_stop_then_release(w, gate)
    finally:
        w.stop()
    assert code == 0, w.text()[-3000:]
    return app_id, aid, seconds, w


def test_a_real_worker_told_to_stop_before_the_send_gate_submits_nothing(api, receiver):
    """D144's measurement, repeated: the worker is told to stop while its application waits
    before the send gate. It now stops there, submits nothing, and exits."""
    from tests.test_celery_execution import claims

    app_id, aid, seconds, w = _run_held(api, receiver, "before_send_gate")
    a = attempt(aid)
    assert a.state == "abandoned" and runner.STOP_REQUESTED in a.outcome_detail, a.outcome_detail
    assert claims(aid) == 1 and receiver.ledger()["accepted"] == 0
    assert app_state(api, app_id) == "needs_user_action"
    assert seconds < 10, seconds  # inside `docker compose stop`'s ten seconds


def test_a_real_worker_told_to_stop_before_opening_the_form_leaves_it_for_the_next(api, receiver):
    """Told to stop while its browser started: the form is never opened and the attempt goes
    back in the queue. The next worker (a new process, its flag cleared) runs it once."""
    from app.worker import publish
    from tests.test_celery_execution import Worker, claims, wait_state

    app_id = prepared_application(api, receiver)
    before = receiver.ledger()["requests"]
    app_id, aid, seconds, w = _run_held(api, receiver, "before_navigate", app_id)
    a = attempt(aid)
    assert a.state == "pending" and a.retry_count == 1 and claims(aid) == 1
    assert receiver.ledger()["requests"] == before
    assert seconds < 10, seconds
    w2 = Worker(concurrency=1)
    try:
        assert svc.relay_outbox(publish) == 1  # the message the stop queued
        wait_state(aid, {"confirmed"}, timeout=120)
    finally:
        w2.stop()
    assert claims(aid) == 2 and receiver.ledger()["accepted"] == 1


def test_a_real_worker_told_to_stop_after_the_send_gate_completes_the_click(api, receiver):
    """D144's second measurement: before the final click, past the send gate. The click is made
    and its outcome recorded, once; the worker then exits."""
    app_id, aid, seconds, w = _run_held(api, receiver, "before_click")
    assert attempt(aid).state == "confirmed" and receiver.ledger()["accepted"] == 1


def test_a_real_worker_told_to_stop_while_waiting_for_a_code_enters_none(api, receiver):
    app_id = prepared_application(api, receiver)
    receiver.config(mode="otp")
    app_id, aid, seconds, w = _run_held(api, receiver, "in_code_wait", app_id)
    a = attempt(aid)
    assert a.outcome_detail == f"Verification was not completed: {runner.STOP_REQUESTED}"
    led = receiver.ledger()
    assert led["accepted"] == 0 and not led["challenges"][-1]["done"]
    assert seconds < 10, seconds


def test_a_real_worker_told_to_stop_as_it_takes_an_attempt_leaves_it_for_the_next(api, receiver):
    """Told to stop as the task starts: nothing is claimed and the attempt stays queued. The
    next worker (its flag cleared, a new process) runs it once."""
    from app.worker import publish
    from tests.test_celery_execution import Worker, claims, wait_state

    app_id, aid, seconds, w = _run_held(api, receiver, "before_claim")
    assert "not claimed, the worker was asked to stop" in w.text()
    assert attempt(aid).state == "pending" and claims(aid) == 0
    assert receiver.ledger()["accepted"] == 0
    w2 = Worker(concurrency=1)
    try:
        publish("execute_attempt", aid)  # as the relay does for a waiting attempt (D146)
        wait_state(aid, {"confirmed"}, timeout=120)
    finally:
        w2.stop()
    assert claims(aid) == 1 and receiver.ledger()["accepted"] == 1
