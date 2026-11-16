"""D150: a request to stop the worker is honoured before the next protected step.

`docker compose stop` (and an upgrade's restart, Ctrl-C) sends SIGTERM or SIGINT to the worker's
main process, and Celery then waits for the running task, which runs in a pool process the signal
never reaches. Before D150 that attempt went on and could submit (D144, measured). The main
process now sets a flag the pool processes share (execution/stopping.py), and the run stops at
its next check: before it claims an attempt, before the page is opened, before each field,
document, section control and page's Next, inside each gate before it commits, and in the wait
for a verification code. Stopped before anything was entered, the attempt goes back in the queue
for the next worker (as the sweeper does for a killed worker's); after, it is abandoned and never
retried. Past the send gate the click is made and its outcome read, and a rehearsal that has
filled ends as rehearsed. The runs are against local stand-ins (FIXTURE ASSUMPTIONS), with the
receiver's ledger as the oracle; the last tests send SIGTERM to a real Celery worker. Synthetic
data only."""

import glob
import http.client
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
import yaml
from playwright.sync_api import BrowserType, ElementHandle, Locator
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.execution import runner, stopping
from app.modules.execution import service as svc
from app.modules.execution.adapters import greenhouse_sections as gsections
from app.modules.execution.adapters.fake_api import FakeApiAdapter
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter
from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter
from app.modules.execution.browser import IsolationUnavailable
from app.modules.execution.models import AttemptEvent, Checkpoint, ExecutionAttempt, OutboxMessage
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue
from tests.test_code_wait_quarantine import open_checkpoint
from tests.test_disclosure_evidence import disclosures
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


def events(aid: str, kind: str) -> int:
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(AttemptEvent)
            .where(AttemptEvent.attempt_id == uuid.UUID(aid), AttemptEvent.kind == kind)
        )


def checkpoints(aid: str) -> list[tuple[str, str | None]]:
    with SessionLocal() as db:
        rows = db.scalars(select(Checkpoint).where(Checkpoint.attempt_id == uuid.UUID(aid)))
        return [(c.status, c.code) for c in rows]


# Each written out, never looked up by a name built at run time: test_forbidden_capabilities
# (R11.4) refuses that in any file where a page runs.
ACTIONS = (
    (Locator, "fill", Locator.fill),
    (Locator, "click", Locator.click),
    (Locator, "check", Locator.check),
    (Locator, "set_checked", Locator.set_checked),
    (Locator, "select_option", Locator.select_option),
    (Locator, "set_input_files", Locator.set_input_files),
    (Locator, "press", Locator.press),
    (ElementHandle, "fill", ElementHandle.fill),
    (ElementHandle, "click", ElementHandle.click),
    (ElementHandle, "check", ElementHandle.check),
    (ElementHandle, "select_option", ElementHandle.select_option),
    (ElementHandle, "set_input_files", ElementHandle.set_input_files),
    (ElementHandle, "press", ElementHandle.press),
)


def actions_after_stop(monkeypatch) -> list[str]:
    """Every action on the page (typing, clicking, choosing, uploading) made after the stop was
    requested, by name."""
    seen: list[str] = []
    for cls, name, original in ACTIONS:

        def act(self, *a, _orig=original, _name=f"{cls.__name__}.{name}", **k):
            if stopping.requested():
                seen.append(_name)
            return _orig(self, *a, **k)

        monkeypatch.setattr(cls, name, act)
    return seen


def stop_in_gate(monkeypatch, nth: int) -> None:
    """A stop requested inside the nth gate the attempt passes (its checks done, its locks
    held), as if it came while that gate ran."""
    real, calls = svc._gate_checks, [0]

    def checks(db, att, *a, **k):
        out = real(db, att, *a, **k)
        if att.state == svc.S.claimed:
            calls[0] += 1
            if calls[0] == nth:
                stopping.request()
        return out

    monkeypatch.setattr(svc, "_gate_checks", checks)


def no_requeue(monkeypatch) -> None:
    """After data was entered a stopped run never asks for the requeue: the requeue's own
    refusal then (service.requeue_on_stop) is the second guard, never the one relied on."""

    def refuse(*_a, **_k):
        raise AssertionError("asked to requeue an attempt after data was entered")

    monkeypatch.setattr(svc, "requeue_on_stop", refuse)


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

SPAWNED = """
import os, subprocess, sys
from app.modules.execution import stopping
stopping.share()
child = subprocess.Popen(
    [sys.executable, "-c",
     "import sys; from app.modules.execution import stopping; sys.stdin.read(1); "
     "print(stopping.requested())"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
stopping.request()
out, _ = child.communicate("x")
path = os.environ[stopping.ENV]
stopping.unshare()
print(out.strip(), os.path.exists(path), stopping.ENV in os.environ)
"""


def _python(script: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != stopping.ENV}
    env["PYTHONPATH"] = str(BACKEND)
    out = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout.split()


def test_the_flag_is_shared_with_a_process_forked_after_it_and_starts_cleared():
    """As in a Celery worker on Linux: the module is imported, then a process is forked (the
    pool's); the parent's later request is seen in the child. Run in a process of its own, so
    the test process never forks."""
    assert _python(FORKED) == ["False", "0"]


def test_shared_through_its_file_a_process_started_afresh_sees_the_request():
    """As on macOS, where billiard spawns its pool processes: a new interpreter imports the
    module afresh and maps the file the main process named (share, at worker_init). The file is
    removed at the end (unshare, at worker_shutdown)."""
    assert _python(SPAWNED) == ["True", "False", "False"]


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
    no_requeue(monkeypatch)
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
    """Requested as the task starts: the attempt is not claimed and stays queued, with a new
    message for the relay, for the next worker, which runs it once."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    before, messages = receiver.ledger()["requests"], waiting_messages(aid)
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_claim=stop")
    assert runner.run_attempt(aid, "w1") == "stopping"
    a = attempt(aid)
    assert a.state == "pending" and a.lease_owner is None and a.generation == 0
    assert receiver.ledger()["requests"] == before
    assert waiting_messages(aid) == messages + 1
    stopping.clear()
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize("point,drafts", [("before_next_gate_1", []), ("before_fill_gate_2", [1])])
def test_on_a_wizard_a_stop_request_ends_the_run_before_the_next_page_step(
    api, receiver, monkeypatch, point, drafts
):
    """Before page 1's Next: never clicked, nothing saved at the employer, and no step recorded.
    Before page 2 is filled: page 1 was saved, nothing of page 2 is entered. Every approval is
    retired (pages may be saved at the employer, D142)."""
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
    assert events(aid, "step_authorized") == len(drafts)  # the gate it stopped at recorded none
    assert all_retired_for_wizard(app_id)


# ------------------------------------------------------------------------ inside the gates


def test_a_stop_while_the_disclosure_gate_runs_records_nothing_and_requeues(
    api, receiver, monkeypatch
):
    """The gate reads the request last, under its locks: nothing is stamped (the pilot's count
    of disclosure gates included), and the attempt goes back in the queue."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    stop_in_gate(monkeypatch, 1)
    assert runner.run_attempt(aid, "w1") == "requeued"
    a = attempt(aid)
    assert a.state == "pending" and a.disclosure_started_at is None
    assert events(aid, "disclosure_authorized") == 0
    assert receiver.ledger()["accepted"] == 0 and uploads(receiver.ledger()) == 0


def test_a_stop_while_the_send_gate_runs_never_clicks(api, receiver, monkeypatch):
    """A stop that comes while the send gate waits for its locks: the gate commits nothing, so
    the click never follows."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    stop_in_gate(monkeypatch, 2)  # the disclosure gate, then this one
    assert runner.run_attempt(aid, "w1") == "abandoned"
    a = attempt(aid)
    assert a.state == "abandoned" and a.send_started_at is None
    assert runner.STOP_REQUESTED in a.outcome_detail
    assert events(aid, "send_authorized") == 0 and receiver.ledger()["accepted"] == 0


def test_a_stop_while_a_wizard_s_step_gate_runs_records_no_step(api, receiver, monkeypatch):
    from tests.test_workday_wizard import draft_pages, wizard_application

    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    stop_in_gate(monkeypatch, 2)  # the disclosure gate, then page 1's Next
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert runner.STOP_REQUESTED in attempt(aid).outcome_detail
    assert events(aid, "step_authorized") == 0 and draft_pages(receiver.ledger()) == []


# --------------------------------------------------- the browser lost while the worker stops


@pytest.mark.parametrize("point,outcome,state", [
    ("before_navigate", "requeued", "pending"),
    ("after_disclosure_gate", "abandoned", "abandoned"),
])  # fmt: skip
def test_an_error_while_the_worker_is_stopping_ends_as_the_stop_does(
    api, receiver, monkeypatch, point, outcome, state
):
    """The whole stack stopping with the worker, or Ctrl-C, can take the browser away under the
    run: an error then, with a stop requested and before the send gate, ends as the stop does,
    never as an internal error."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop,{point}=raise")
    assert runner.run_attempt(aid, "w1") == outcome
    a = attempt(aid)
    assert a.state == state and "internal error" not in (a.outcome_detail or "")
    if state == "abandoned":
        assert runner.STOP_REQUESTED in a.outcome_detail
    assert receiver.ledger()["accepted"] == 0


class _Busy(set):
    """The page's own requests, never finished; the stop is requested the first time the
    readiness wait looks (and, with `fail`, the page is lost then)."""

    fail = False
    asked: float | None = None

    def __bool__(self):
        if _Busy.asked is None:
            _Busy.asked = time.monotonic()
            stopping.request()
            if _Busy.fail:
                raise RuntimeError("Target page, context or browser has been closed")
        return True


@pytest.mark.parametrize("fail", [False, True], ids=["still-loading", "browser-lost"])
def test_a_stop_while_the_first_page_loads_puts_the_attempt_back_at_once(
    api, receiver, monkeypatch, fail
):
    """The wait for the first page to finish loading ends at the request (never its whole
    eight seconds), and a page lost then is the stop's: back in the queue either way."""

    class StillLoading(runner._Loading):
        def __init__(self, page):
            super().__init__(page)
            self.pending = _Busy()

    monkeypatch.setattr(_Busy, "fail", fail)
    monkeypatch.setattr(_Busy, "asked", None)
    monkeypatch.setattr(runner, "_Loading", StillLoading)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "requeued"
    assert time.monotonic() - _Busy.asked < runner.SETTLE_LOAD_MS / 1000 / 2
    a = attempt(aid)
    assert a.state == "pending" and a.disclosure_started_at is None


def test_a_browser_that_cannot_be_started_while_stopping_is_the_stop_s(api, receiver, monkeypatch):
    """The browser runner stopping with the worker refuses the session: back in the queue."""

    def gone(*a, **k):
        stopping.request()
        raise IsolationUnavailable("the runner is stopping", "runner_unreachable")

    monkeypatch.setattr(runner, "browser_session", gone)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "requeued"
    assert attempt(aid).state == "pending"


# ---------------------------------------------------- between controls, on the adapters


def test_greenhouse_section_controls_stop_at_the_next_one(api, receiver, monkeypatch):
    """D120's education rows on the Greenhouse-style form (the live pilot's filling): a stop
    after the first control enters no further control or row."""
    from tests.test_greenhouse_sections_e2e import sections_application

    real, done = gsections._apply_op, []

    def op_then_stop(page, op, *rest):  # rest: the time limit and, since D151, `late`
        real(page, op, *rest)
        if not done:
            done.append(op.field)
            stopping.request()

    monkeypatch.setattr(gsections, "_apply_op", op_then_stop)
    receiver.config(mode="gh2_sections")  # the captured and served form carries the section
    app_id = sections_application(api)
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert runner.STOP_REQUESTED in attempt(aid).outcome_detail
    fields = [d for d in disclosures(aid) if d.get("kind") == "section_field"]
    assert [d["field"] for d in fields] == done and seen == []
    assert receiver.ledger()["accepted"] == 0


def test_workday_section_entries_stop_at_the_next_control(api, receiver, monkeypatch):
    """D149's Work Experience entries on the Workday-style wizard: the run checks before each
    entry and each control, so a stop after the first control enters no further one, and its
    page's Next is never clicked."""
    from app.modules.execution.adapters import workday_sections as ws
    from tests.test_workday_experience import experience_application
    from tests.test_workday_wizard import draft_pages

    real, done = ws._give, []

    def give_then_stop(page, op, timeout_ms):
        real(page, op, timeout_ms)
        if not done:
            done.append(op.field)
            stopping.request()

    monkeypatch.setattr(ws, "_give", give_then_stop)
    app_id = experience_application(api, receiver)
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert runner.STOP_REQUESTED in attempt(aid).outcome_detail
    fields = [d for d in disclosures(aid) if d.get("kind") == "section_field"]
    assert [d["field"] for d in fields] == done and seen == []
    led = receiver.ledger()
    assert draft_pages(led) == [1] and led["accepted"] == 0


def test_workday_education_entries_stop_at_the_next_control(api, receiver, monkeypatch):
    """D163's Education entries, likewise: a stop after the first list was chosen chooses or
    types nothing more, and its page's Next is never clicked."""
    from app.modules.execution.adapters import workday_sections as ws
    from tests.test_workday_education import education_application
    from tests.test_workday_wizard import draft_pages

    real, done = ws._give, []

    def give_then_stop(page, op, timeout_ms):
        real(page, op, timeout_ms)
        if not done:
            done.append(op.field)
            stopping.request()

    monkeypatch.setattr(ws, "_give", give_then_stop)
    app_id = education_application(api, receiver)
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert runner.STOP_REQUESTED in attempt(aid).outcome_detail
    fields = [d for d in disclosures(aid) if d.get("kind") == "section_field"]
    assert [d["field"] for d in fields] == done == ["school_name_id"] and seen == []
    led = receiver.ledger()
    assert draft_pages(led) == [1] and led["accepted"] == 0


def test_greenhouse_section_rows_are_not_added_after_a_stop(api, receiver, monkeypatch):
    """Two education rows: a stop that comes as the second row is looked for clicks no "Add
    another"; the first row stays as entered."""
    from tests.test_greenhouse_sections_e2e import sections_application

    plan, present, filling = gsections.apply_section_plan, gsections._present, []

    def apply(*a, **k):
        filling.append(True)
        return plan(*a, **k)

    def present_then_stop(*a, **k):
        out = present(*a, **k)
        if filling:  # the second row, before its "Add another" (never before disclosure)
            stopping.request()
        return out

    monkeypatch.setattr(gsections, "apply_section_plan", apply)
    monkeypatch.setattr(gsections, "_present", present_then_stop)
    receiver.config(mode="gh2_sections")
    app_id = sections_application(api, two_rows=True)
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    rows = {d["row"] for d in disclosures(aid) if d.get("kind") == "section_field"}
    assert rows == {0} and seen == [] and receiver.ledger()["accepted"] == 0


def test_on_greenhouse_pages_the_stop_is_read_after_the_page_settles_from_an_upload(
    api, receiver, monkeypatch
):
    """After the résumé the page re-draws its fields (D116) and NoEfforts waits for it; a stop
    during that wait enters nothing more."""
    from tests.test_greenhouse_dom import v2_application

    real = GreenhouseDomAdapter._settle

    def settle(self, page):
        if self._filled:  # the wait after an upload (not the reads before disclosure)
            stopping.request()
        return real(page)

    monkeypatch.setattr(GreenhouseDomAdapter, "_settle", settle)
    app_id = v2_application(api)
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert seen == [] and [d["field"] for d in disclosures(aid)] == ["resume"]
    assert receiver.ledger()["accepted"] == 0


def test_on_the_hosted_form_a_stop_during_the_wait_for_a_shown_question_enters_it_not(
    api, receiver, monkeypatch
):
    from tests.test_greenhouse_adapter import gh_application

    real = Locator.wait_for

    def wait_for_then_stop(self, *a, **k):
        out = real(self, *a, **k)
        if "question_7006" in repr(self):  # the question the answer "Yes" shows
            stopping.request()
        return out

    monkeypatch.setattr(Locator, "wait_for", wait_for_then_stop)
    app_id = gh_application(api, employed="Yes", site="Main campus")
    aid = queue(api, app_id)
    seen = actions_after_stop(monkeypatch)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert seen == [] and receiver.ledger()["accepted"] == 0


def test_a_rehearsal_that_has_filled_ends_as_rehearsed(api, receiver, monkeypatch):
    """Once a rehearsal has filled, what is left (reading back, the re-check, its stop) enters
    nothing: a stop request no longer cuts it short, and it counts as the rehearsal it was."""
    real = FixtureAtsAdapter.readback

    def readback(self, page):
        stopping.request()
        return real(self, page)

    monkeypatch.setattr(FixtureAtsAdapter, "readback", readback)
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    assert attempt(aid).state == "rehearsed" and receiver.ledger()["accepted"] == 0


def test_a_stop_during_a_heartbeat_is_read_before_the_step_it_precedes(api, receiver, monkeypatch):
    """The check comes again after the heartbeat's round trip, right before the document it
    precedes: a stop that arrives during it sends no document."""
    real = svc.heartbeat

    def heartbeat(aid, worker, gen, *a, **k):
        out = real(aid, worker, gen, *a, **k)
        if attempt(str(aid)).disclosure_started_at is not None:
            stopping.request()
        return out

    monkeypatch.setattr(svc, "heartbeat", heartbeat)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert uploads(led) == 0 and led["accepted"] == 0


def test_an_error_after_the_send_gate_while_stopping_is_an_unknown_outcome(
    api, receiver, monkeypatch
):
    """Past the send gate a stop request changes nothing: an error there is an unknown outcome,
    quarantined and never resent, as before."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "before_click=stop,before_click=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    assert attempt(aid).state == "unknown"
    assert app_state(api, app_id) == "submitted_unconfirmed"


def test_a_new_message_is_queued_only_for_an_attempt_still_waiting(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    n = waiting_messages(aid)
    assert svc.publish_again(uuid.UUID(aid)) and waiting_messages(aid) == n + 1
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).cancel_requested = True
        db.commit()
    assert not svc.publish_again(uuid.UUID(aid))  # a cancel requested
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).cancel_requested = False
        db.commit()
    assert svc.claim(uuid.UUID(aid), "w1") is not None
    assert not svc.publish_again(uuid.UUID(aid))  # taken by a worker
    assert waiting_messages(aid) == n + 1


# ------------------------------------------------------------------ the verification code


def test_waiting_for_a_code_a_stop_request_leaves_the_verification_unfinished(
    api, receiver, monkeypatch
):
    """The employer asked for a code: no code is entered after the stop request. The
    verification is left unfinished (the approval that made the click is used up) and its
    request is closed."""
    monkeypatch.setattr(get_settings(), "checkpoint_ttl_seconds", 5)  # a missed check ends soon
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
    monkeypatch.setattr(get_settings(), "checkpoint_ttl_seconds", 5)
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


# ----------------------------------------------------------------------- the API route


@pytest.fixture()
def fake_api(monkeypatch):
    from tests.test_api_provider import TOKEN

    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)


@pytest.mark.parametrize("point,state", [("after_claim", "pending"),
                                         ("after_disclosure_gate", "abandoned"),
                                         ("before_send_gate", "abandoned")])  # fmt: skip
def test_on_the_api_route_a_stop_request_ends_the_run_before_its_next_request(
    api, receiver, monkeypatch, fake_api, point, state
):
    """The API route (no browser) checks as it starts, at its two gates, before its draft and
    before each document: asked to stop as it starts, the API is asked nothing and the attempt
    goes back in the queue; after the disclosure gate, nothing is created or uploaded; before
    the send gate the application is never submitted."""
    from tests.test_api_provider import acceptances, api_application, fapi_requests

    app_id = api_application(api)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop")
    if state == "abandoned":
        no_requeue(monkeypatch)
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
    if point == "after_disclosure_gate":
        assert disclosures(aid) == []  # not even the draft


def test_a_stop_while_the_api_reads_the_job_s_schema_puts_the_attempt_back(
    api, receiver, monkeypatch, fake_api
):
    """Requested while the API route reads the job's schema (read-only): the disclosure gate is
    never passed, nothing is created or uploaded, and the attempt goes back in the queue."""
    from tests.test_api_provider import acceptances, api_application, fapi_requests

    app_id = api_application(api)
    aid = queue(api, app_id)
    read = FakeApiAdapter.validate_before_disclosure

    def read_then_stop(self):
        out = read(self)
        stopping.request()
        return out

    monkeypatch.setattr(FakeApiAdapter, "validate_before_disclosure", read_then_stop)
    assert runner.run_attempt(aid, "w1") == "requeued"
    a = attempt(aid)
    assert a.state == "pending" and a.disclosure_started_at is None
    assert [m for m, _ in fapi_requests(receiver)] == ["GET"]  # the schema, and nothing else
    assert acceptances(receiver) == [] and uploads(receiver.ledger()) == 0


def test_a_stop_while_the_api_creates_the_draft_sends_no_document(
    api, receiver, monkeypatch, fake_api
):
    from tests.test_api_provider import acceptances, api_application

    app_id = api_application(api)
    aid = queue(api, app_id)
    prepare = FakeApiAdapter.prepare

    def prepare_then_stop(self):
        out = prepare(self)
        stopping.request()
        return out

    monkeypatch.setattr(FakeApiAdapter, "prepare", prepare_then_stop)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert runner.STOP_REQUESTED in attempt(aid).outcome_detail
    assert disclosures(aid) == [{"route": "api", "kind": "application_draft"}]
    assert uploads(receiver.ledger()) == 0 and acceptances(receiver) == []


@pytest.mark.parametrize("point,outcome,state", [
    ("schema", "requeued", "pending"),
    ("after_disclosure_gate", "abandoned", "abandoned"),
])  # fmt: skip
def test_on_the_api_route_an_error_while_the_worker_is_stopping_ends_as_the_stop_does(
    api, receiver, monkeypatch, fake_api, point, outcome, state
):
    """As on the browser route: an error with a stop requested, before the send gate, ends as
    the stop does, never as an internal error. The schema's answer cut off (urllib raises a
    connection closed before the answer as http.client.RemoteDisconnected, which the read does
    not turn into a reason) puts the attempt back in the queue; after the disclosure gate it is
    abandoned."""
    from tests.test_api_provider import acceptances, api_application, fapi_requests

    app_id = api_application(api)
    aid = queue(api, app_id)
    if point == "schema":
        call = FakeApiAdapter._call

        def cut_off(self, *a, **k):
            call(self, *a, **k)  # the request reaches the API; its answer never comes back
            stopping.request()
            raise http.client.RemoteDisconnected("Remote end closed connection without response")

        monkeypatch.setattr(FakeApiAdapter, "_call", cut_off)
    else:
        monkeypatch.setenv("NOEFFORTS_FAULT", f"{point}=stop,{point}=raise")
    assert runner.run_attempt(aid, "w1") == outcome
    a = attempt(aid)
    assert a.state == state and "internal error" not in (a.outcome_detail or "")
    if state == "abandoned":
        assert runner.STOP_REQUESTED in a.outcome_detail
    else:
        assert a.disclosure_started_at is None
        assert [m for m, _ in fapi_requests(receiver)] == ["GET"]  # the schema, and nothing else
    assert acceptances(receiver) == [] and uploads(receiver.ledger()) == 0


# ------------------------------------------------------------------- the requeue's fence


def test_the_requeue_writes_nothing_for_a_worker_that_no_longer_holds_the_attempt(api, receiver):
    """Fenced by the worker, the generation, the lease and a cancel, as every worker write; and
    never once data was entered (the caller abandons it instead)."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    assert gen is not None

    def change(**fields):
        with SessionLocal() as db:
            att = db.get(ExecutionAttempt, uuid.UUID(aid))
            for k, v in fields.items():
                setattr(att, k, v)
            db.commit()

    assert svc.requeue_on_stop(uuid.UUID(aid), "w2", gen) is None  # another worker
    assert svc.requeue_on_stop(uuid.UUID(aid), "w1", gen + 1) is None  # another generation
    change(disclosure_started_at=utcnow())
    assert svc.requeue_on_stop(uuid.UUID(aid), "w1", gen) is None  # data entered
    change(disclosure_started_at=None, cancel_requested=True)
    assert svc.requeue_on_stop(uuid.UUID(aid), "w1", gen) is None  # a cancel requested
    change(cancel_requested=False, lease_expires_at=utcnow() - timedelta(seconds=1))
    assert svc.requeue_on_stop(uuid.UUID(aid), "w1", gen) is None  # its lease ran out
    a = attempt(aid)
    assert a.state == "claimed" and a.retry_count == 0 and a.generation == gen
    assert events(aid, "stop_requeued") == 0


# ------------------------------------------------------------- the browser and the stack


def test_the_browser_is_launched_without_playwright_s_own_signal_handling(
    api, receiver, monkeypatch
):
    """Playwright's driver shares the worker's process group: on Ctrl-C it would close the
    browser under the run. The worker's own stop request closes it at the next check."""
    seen = []
    real = BrowserType.launch

    def launch(self, **kw):
        seen.append({k: kw.get(k) for k in ("handle_sigint", "handle_sigterm", "handle_sighup")})
        return real(self, **kw)

    monkeypatch.setattr(BrowserType, "launch", launch)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert seen == [{"handle_sigint": False, "handle_sigterm": False, "handle_sighup": False}]


def test_the_worker_stops_before_its_browser_and_waits_for_a_click_s_answer():
    """`docker compose stop` and `down` stop the worker before the browser runner and the egress
    proxy, and give it as long as a real Greenhouse page's answer to the click may take."""
    compose = yaml.safe_load((BACKEND.parent / "docker-compose.yml").read_text())
    worker = compose["services"]["worker"]
    for service in ("browser-runner", "egress-proxy"):
        assert worker["depends_on"][service] == {"condition": "service_started"}, service
    grace = int(str(worker["stop_grace_period"]).removesuffix("s"))
    submit_ms = Settings.model_fields["submit_timeout_seconds"].default * 1000
    real = SimpleNamespace(_stand_in=False)
    assert grace >= GreenhouseDomAdapter.send_watch_seconds(real, submit_ms) + 20


# ---------------------------------------------------------------------- a real Celery worker

ASKED = "NoEfforts: asked to stop"  # app/worker.py, written once the flag is set


def _held(point: str):
    """A real worker (prefork, one process, as deployed), held at `point` until released."""
    from tests.test_celery_execution import Worker, clean_broker

    clean_broker()
    gate = tempfile.mktemp(prefix="release-")
    return Worker(fault=f"{point}=waitfile:{gate}", concurrency=1), gate


def _ask_to_stop_then_release(w, gate) -> tuple[int, float]:
    """SIGTERM to the main process, as `docker compose stop` sends first; once the worker says
    the flag is set, release the held pool process. The exit code, and the seconds from the
    release to the worker's exit."""
    w.p.send_signal(signal.SIGTERM)
    w.wait_log(ASKED, 20)
    released = time.monotonic()
    open(gate, "w").close()
    code = w.p.wait(timeout=90)
    return code, time.monotonic() - released


def _run_held(api, receiver, point: str, app_id: str | None = None):
    from app.worker import publish

    app_id = app_id or prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = _held(point)
    flag_files = os.path.join(tempfile.gettempdir(), f"noefforts-stop-{w.p.pid}-*")
    try:
        assert len(glob.glob(flag_files)) == 1  # shared at worker_init, for every pool process
        assert svc.relay_outbox(publish) == 1
        wait_for(lambda: reached(gate), timeout=120)
        code, seconds = _ask_to_stop_then_release(w, gate)
    finally:
        w.stop()
    assert code == 0, w.text()[-3000:]
    assert glob.glob(flag_files) == []  # removed at worker_shutdown
    print(f"{point}: the worker exited {seconds:.1f} s after its held process was released")
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
    """Told to stop as the task starts: nothing is claimed, the attempt stays queued and a new
    message is queued for it. The next worker (its flag cleared, a new process) runs it once."""
    from app.worker import publish
    from tests.test_celery_execution import Worker, claims, wait_state

    app_id, aid, seconds, w = _run_held(api, receiver, "before_claim")
    assert "not claimed, the worker was asked to stop" in w.text()
    assert attempt(aid).state == "pending" and claims(aid) == 0
    assert receiver.ledger()["accepted"] == 0
    w2 = Worker(concurrency=1)
    try:
        assert svc.relay_outbox(publish) == 1  # the message the stopping worker queued
        wait_state(aid, {"confirmed"}, timeout=120)
    finally:
        w2.stop()
    assert claims(aid) == 1 and receiver.ledger()["accepted"] == 1
