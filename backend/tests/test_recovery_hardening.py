"""D143: recovery hardening. An attempt's run is bounded by the runner itself, between steps,
and a run past its budget stops before the final click; its task has one time limit that covers
the whole wait for a verification code, at which the worker process is ended and the sweeper
decides; a long form keeps its lease while it makes progress; a verification request ends with
its attempt and keeps no code, and a code typed late is still entered under a lease; the send
lease covers the adapter's wait for the click's answer; and a worker killed at each point on the
Greenhouse-style (gh2, by id) and Workday-style forms leaves what the phase says, never a second
submission. The receiver's ledger is the oracle for everything said to have reached the employer.
Every form is a local stand-in (FIXTURE ASSUMPTIONS); rows edited by hand are labelled simulated.
Synthetic data only."""

import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
import redis

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.execution import faults, runner
from app.modules.execution import service as svc
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter
from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from tests.execution_harness import (
    BACKEND,
    Receiver,
    attempt,
    prepared_application,
    queue,
    run_worker_process,
)
from tests.test_code_wait_quarantine import open_checkpoint
from tests.test_execution_failures import (
    _browser_application,
    expire_lease,
    reached,
    release,
    start_blocked_worker,
    wait_for,
)

ROOT = BACKEND.parent
S = svc.S
LIMITS = ("attempt_run_budget_seconds", "attempt_after_send_seconds", "checkpoint_ttl_seconds")
REAL_WATCH = 123  # a real Greenhouse page: 10 s for the click, 75 s for its answer and half again


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def app_state(api, app_id: str) -> str:
    return api.get(f"/applications/{app_id}").json()["state"]


def start_worker(aid: str, worker: str, fault: str, **settings) -> subprocess.Popen:
    env = os.environ | {"NOEFFORTS_FAULT": fault, "PYTHONPATH": str(BACKEND)}
    env |= {f"NOEFFORTS_{k.upper()}": str(v) for k, v in settings.items()}
    return subprocess.Popen(
        [sys.executable, "-m", "app.modules.execution.cli", "run", aid, worker],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def checkpoint(cp_id: str) -> tuple[str, str | None]:
    with SessionLocal() as db:
        cp = db.get(Checkpoint, uuid.UUID(cp_id))
        return cp.status, cp.code


def disclosed(led, kind: str) -> int:
    return sum(1 for d in led["disclosures"] if d["kind"] == kind)


def uploads(led) -> int:
    return disclosed(led, "upload")


def default_limits() -> Settings:
    """The settings a deployment gets for the three parts of an attempt's time limit."""
    return Settings(_env_file=None, **{k: Settings.model_fields[k].default for k in LIMITS})


# ------------------------------------------------------------------------------- time limits


def test_an_attempts_task_has_one_time_limit_that_covers_the_whole_code_wait():
    from app.worker import celery_app, execute_attempt

    s = get_settings()
    limit = s.attempt_time_limit_seconds
    assert limit == sum(getattr(s, k) for k in LIMITS)
    # One limit and no soft limit: nothing is raised inside a running attempt (one raised
    # inside a browser wait could not be handled; measured, D143). The pool arms a soft limit
    # whenever a task or the default has one, so the default has none ...
    assert (execute_attempt.soft_time_limit, execute_attempt.time_limit) == (None, limit)
    assert (celery_app.conf.task_soft_time_limit, celery_app.conf.task_time_limit) == (None, 300)
    # ... and every other task sets the short one itself, under the default hard limit.
    others = {n: t for n, t in celery_app.tasks.items()
              if n.startswith("noefforts.") and n != execute_attempt.name}  # fmt: skip
    assert len(others) >= 9
    assert {(t.soft_time_limit, t.time_limit) for t in others.values()} == {(240, None)}
    # The defaults a deployment gets: 7 minutes to reach the final click, the whole 10-minute
    # wait for a code, and 6 minutes for the other waits after the click.
    d = default_limits()
    assert [getattr(d, k) for k in LIMITS] == [420, 360, 600]
    assert d.attempt_time_limit_seconds == 1380
    # Under the broker's visibility timeout, or a still-running task's message is redelivered.
    visibility = Settings.model_fields["broker_visibility_timeout_seconds"].default
    assert d.attempt_time_limit_seconds < visibility
    # After the click, besides the wait for a code: the longest watch for the click's answer
    # and for the last code's (a real Greenhouse page), and a minute of overrun before it.
    submit_ms = d.submit_timeout_seconds * 1000
    real = SimpleNamespace(_stand_in=False)
    assert GreenhouseDomAdapter.send_watch_seconds(real, submit_ms) == REAL_WATCH
    assert 2 * REAL_WATCH + 60 <= d.attempt_after_send_seconds


def test_the_browser_and_proxy_sessions_outlast_the_attempts_task():
    """The browser runner closes a session at its own limit, and the egress proxy's session
    expires at its own (the browser's next connection is then refused). Below the task's limit,
    a run still waiting for a code would lose its browser, or its way out, first."""
    limit = default_limits().attempt_time_limit_seconds
    compose = (ROOT / "docker-compose.yml").read_text()
    (default,) = re.findall(r"MAX_SESSION_SECONDS: \$\{BROWSER_MAX_SESSION_SECONDS:-(\d+)\}",
                            compose)  # fmt: skip
    launcher = (ROOT / "browser" / "launcher.js").read_text()
    (fallback,) = re.findall(r"process\.env\.MAX_SESSION_SECONDS \|\| (\d+)\)", launcher)
    assert int(default) == int(fallback) >= limit + 60
    (proxy,) = re.findall(
        r"EGRESS_SESSION_TTL_SECONDS: \$\{EGRESS_SESSION_TTL_SECONDS:-(\d+)\}", compose
    )
    service = (BACKEND / "app/modules/execution/sandbox/proxy_service.py").read_text()
    (proxy_fallback,) = re.findall(r'get\("EGRESS_SESSION_TTL_SECONDS", "(\d+)"\)', service)
    assert int(proxy) == int(proxy_fallback) >= limit + 60


# point: (attempt state, how the outcome begins, documents uploaded before the stop)
BUDGET_CASES = {
    "before_navigate": ("failed_safe", "Stopped before sending anything", False),
    "after_disclosure_gate": ("abandoned", "Stopped after entering data", False),
    "before_send_gate": ("abandoned", "Stopped after entering data", True),
}


def over_budget(point: str) -> str:
    """A fault that makes the run's clock pass its budget at `point`, without the wait."""
    return f"{point}=elapse:{get_settings().attempt_run_budget_seconds + 1}"


@pytest.mark.parametrize("point", list(BUDGET_CASES))
@pytest.mark.parametrize("adapter", ["fixture_ats", "greenhouse_dom", "greenhouse_live",
                                     "fixture_workday"])  # fmt: skip
def test_a_run_past_its_budget_stops_before_the_final_click(api, receiver, monkeypatch,
                                                            adapter, point):  # fmt: skip
    """The runner checks the budget itself between steps (never inside a browser wait): after
    opening the form, between fields, and right before the send gate. Past it the run stops as
    its phase says, the text says the time limit, and the final click is never made."""
    app_id = _browser_application(adapter, api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setattr(faults, "_elapsed", 0.0)
    monkeypatch.setenv("NOEFFORTS_FAULT", over_budget(point))
    assert runner.run_attempt(aid, "w1") == "error"
    state, begins, uploaded = BUDGET_CASES[point]
    a = attempt(aid)
    assert a.adapter == adapter and a.state == state
    assert a.outcome_detail.startswith(begins), a.outcome_detail
    assert runner.TIME_LIMIT in a.outcome_detail and "internal error" not in a.outcome_detail
    assert a.send_started_at is None and app_state(api, app_id) == "needs_user_action"
    led = receiver.ledger()
    assert led["accepted"] == 0 and (uploads(led) > 0) is uploaded
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "ignored"  # never run again
    again = receiver.ledger()
    assert again["accepted"] == 0 and again["requests"] == led["requests"]


def test_a_run_within_its_budget_is_not_stopped(api, receiver, monkeypatch):
    """Half a minute under the budget at the send gate: submitted, once."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setattr(faults, "_elapsed", 0.0)
    almost = get_settings().attempt_run_budget_seconds - 30
    monkeypatch.setenv("NOEFFORTS_FAULT", f"before_send_gate=elapse:{almost}")
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_the_budget_never_stops_a_run_after_the_send_gate(api, receiver, monkeypatch):
    """Past the budget right after the send gate: the click is made and its answer recorded.
    After that gate only the waits' own limits apply."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setattr(faults, "_elapsed", 0.0)
    monkeypatch.setenv("NOEFFORTS_FAULT", over_budget("before_click"))
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert attempt(aid).state == "confirmed" and receiver.ledger()["accepted"] == 1


def test_a_wizard_past_its_budget_stops_for_good(api, receiver, monkeypatch):
    from tests.test_workday_wizard import all_retired_for_wizard, draft_pages, wizard_application

    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setattr(faults, "_elapsed", 0.0)
    monkeypatch.setenv("NOEFFORTS_FAULT", over_budget("before_next_gate_2"))
    assert runner.run_attempt(aid, "w1") == "error"
    a = attempt(aid)
    assert a.state == "abandoned" and "multi-page form" in a.outcome_detail
    assert runner.TIME_LIMIT in a.outcome_detail
    assert "never made the final submit" in a.outcome_detail
    led = receiver.ledger()
    assert draft_pages(led) == [1] and led["accepted"] == 0
    assert all_retired_for_wizard(app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "")
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["requests"] == led["requests"]


def test_at_the_time_limit_the_worker_process_is_ended_and_the_sweeper_decides(
    api, receiver, monkeypatch
):
    """A real Celery worker (prefork) with a 32-second limit on the attempt's task; the worker
    hangs after the final click, which the employer accepted. No soft limit is raised: the
    process is ended at the limit, the message is not redelivered, and the sweeper calls the
    outcome unknown. Nothing is ever sent again."""
    from app.worker import publish
    from tests.test_celery_execution import Worker, claims, wait_state

    broker = redis.Redis.from_url(get_settings().redis_url)
    broker.delete("celery", "unacked", "unacked_index")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_ATTEMPT_RUN_BUDGET_SECONDS", "30")
    monkeypatch.setenv("NOEFFORTS_ATTEMPT_AFTER_SEND_SECONDS", "1")
    monkeypatch.setenv("NOEFFORTS_CHECKPOINT_TTL_SECONDS", "1")
    w = Worker(fault="after_click=sleep:300")
    try:
        assert svc.relay_outbox(publish) == 1
        wait_state(aid, {"sending"})
        w.wait_log("Hard time limit (32s) exceeded", 90)
        time.sleep(4)  # if Celery were to redeliver or run it again, it would do so now
        assert broker.llen("celery") == 0 and broker.hlen("unacked") == 0
    finally:
        w.stop()
    assert "Soft time limit" not in w.text()
    a = attempt(aid)
    assert claims(aid) == 1 and a.state == "sending" and a.finished_at is None
    assert receiver.ledger()["accepted"] == 1  # the employer has it; NoEfforts does not know
    expire_lease(aid)
    assert svc.sweep(publish_new=False)["unknown"] == 1
    assert attempt(aid).state == "unknown"
    assert app_state(api, app_id) == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1


# ------------------------------------------------------------------------------- checkpoints


def _code_request(api, receiver, fault_after_wait: str = "", **settings):
    """An attempt waiting for the emailed code, its worker held right after it asked."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    gate = tempfile.mktemp(prefix="release-")
    fault = f"in_code_wait=waitfile:{gate}" + (f",{fault_after_wait}" if fault_after_wait else "")
    p = start_worker(aid, "w-code", fault, **settings)
    wait_for(lambda: reached(gate), timeout=60)
    cp = open_checkpoint(api, app_id)
    code = receiver.ledger()["challenges"][-1]["code"]
    return app_id, aid, p, gate, cp, code


def test_a_code_typed_for_an_attempt_that_then_ends_is_erased_and_its_request_closed(api, receiver):
    """The worker fails while it waits for the code. The code you had just typed is erased, the
    request takes no more, and nothing was submitted with it."""
    app_id, aid, p, gate, cp, code = _code_request(api, receiver, "in_code_wait=raise")
    url = f"/applications/{app_id}/checkpoints/{cp['id']}/code"
    body = {"round": 1, "code": code}
    try:
        assert api.post(url, json=body).status_code == 202
        assert checkpoint(cp["id"]) == ("submitted", code)  # held for the worker
    finally:
        result = release(p, gate)
    assert result == "error"
    a = attempt(aid)
    assert a.state == "unknown" and a.outcome_detail.startswith("Outcome unknown")
    assert checkpoint(cp["id"]) == ("expired", None)
    r = api.post(url, json=body)
    assert r.status_code == 409, r.text
    assert app_state(api, app_id) == "submitted_unconfirmed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["challenges"][-1]["done"] is False
    assert runner.run_attempt(aid, "w-again") == "ignored"
    assert receiver.ledger()["requests"] == led["requests"]


def test_a_request_takes_a_code_only_while_its_attempt_waits_and_the_sweeper_closes_the_rest(
    api, receiver
):
    app_id, aid, p, gate, cp, code = _code_request(api, receiver)
    url = f"/applications/{app_id}/checkpoints/{cp['id']}/code"
    try:
        # A live wait is left alone by the sweeper's pass, also in the minute after its time
        # ran out (its own worker closes it then), and closed after that (simulated: the row's
        # expiry, 30 s and then 120 s ago).
        assert svc.close_stale_checkpoints() == 0 and checkpoint(cp["id"]) == ("open", None)
        for ago, closed in ((30, 0), (120, 1)):
            with SessionLocal() as db:
                row = db.get(Checkpoint, uuid.UUID(cp["id"]))
                row.expires_at = utcnow() - timedelta(seconds=ago)
                db.commit()
            assert svc.close_stale_checkpoints() == closed
        assert checkpoint(cp["id"]) == ("expired", None)
    finally:
        p.kill()
        p.wait(timeout=30)
    # Simulated: an attempt that ended before D143, which left its request open.
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, uuid.UUID(aid))
        att.state, att.lease_owner, att.lease_expires_at = S.unknown, None, None
        row = db.get(Checkpoint, uuid.UUID(cp["id"]))
        row.status, row.expires_at = "open", utcnow() + timedelta(seconds=300)
        db.commit()
    r = api.post(url, json={"round": 1, "code": code})
    assert r.status_code == 409 and "not waiting for a code" in r.json()["detail"], r.text
    assert checkpoint(cp["id"]) == ("open", None)  # nothing was stored
    # Simulated: such a request that had already taken a code.
    with SessionLocal() as db:
        row = db.get(Checkpoint, uuid.UUID(cp["id"]))
        row.status, row.code = "submitted", code
        db.commit()
    assert svc.sweep(publish_new=False)["checkpoints_closed"] == 1
    assert checkpoint(cp["id"]) == ("expired", None)
    assert receiver.ledger()["accepted"] == 0


def test_a_code_typed_late_in_its_wait_is_entered_under_a_lease_that_covers_its_answer(
    api, receiver
):
    """The wait's lease ends 30 s after the request does, and a code typed at the very end is
    answered after that. Taking the code extends the lease over the watch for its answer, so
    the employer's answer is recorded, not swept as unknown. Simulated: the lease as it is that
    late in the wait (8 s left); the employer answers the code 12 s after accepting it, within
    the worker's 30-second timeouts (the click that sends a code waits for its page as well)."""
    app_id, aid, p, gate, cp, code = _code_request(
        api, receiver, submit_timeout_seconds=30, navigation_timeout_seconds=30
    )
    receiver.config(verify_delay_s=12)
    url = f"/applications/{app_id}/checkpoints/{cp['id']}/code"
    late = utcnow() + timedelta(seconds=8)
    try:
        with SessionLocal() as db:
            db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = late
            db.commit()
        assert api.post(url, json={"round": 1, "code": code}).status_code == 202
    finally:
        result = release(p, gate)
    assert result == "confirmed"
    a = attempt(aid)
    assert a.state == "confirmed" and a.finished_at > late  # after the wait's lease had ended
    assert checkpoint(cp["id"]) == ("done", None)
    assert app_state(api, app_id) == "submitted_confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_a_code_accepted_in_the_last_moment_of_its_wait_is_still_entered(api, receiver):
    """The code was accepted (202) while the request was open; its time ran out before the
    worker's next look (simulated: the request's expiry a second ago, and the worker's own
    clock past the end of its wait). The worker enters it all the same. Before, either end
    won and the accepted code was erased unused. The run is also past its budget by then,
    which no longer applies after the final click."""
    over = get_settings().attempt_run_budget_seconds + 1
    app_id, aid, p, gate, cp, code = _code_request(api, receiver, f"in_code_wait=elapse:{over}")
    url = f"/applications/{app_id}/checkpoints/{cp['id']}/code"
    try:
        assert api.post(url, json={"round": 1, "code": code}).status_code == 202
        with SessionLocal() as db:
            db.get(Checkpoint, uuid.UUID(cp["id"])).expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        # Too late for another: the request's own time is checked when a code is typed.
        assert api.post(url, json={"round": 1, "code": code}).status_code == 409
    finally:
        result = release(p, gate)
    assert result == "confirmed"
    assert attempt(aid).state == "confirmed" and checkpoint(cp["id"]) == ("done", None)
    assert receiver.ledger()["accepted"] == 1


# ------------------------------------------------------------------------------------ leases


def _claimed(api, receiver, **kw) -> tuple[str, str, int]:
    app_id = prepared_application(api, receiver, **kw)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    assert gen is not None
    return app_id, aid, gen


def _set_lease(aid: str, seconds: float) -> None:
    with SessionLocal() as db:  # simulated: the lease as it would be that long after a beat
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() + timedelta(
            seconds=seconds
        )
        db.commit()


def test_recording_evidence_renews_the_lease_and_never_shortens_it(api, receiver):
    _, aid, gen = _claimed(api, receiver)
    lease = get_settings().lease_seconds
    _set_lease(aid, 2)
    svc.record_evidence(uuid.UUID(aid), "w1", gen, "disclosure", {"kind": "synthetic"})
    left = (attempt(aid).lease_expires_at - utcnow()).total_seconds()
    assert lease - 5 < left <= lease
    _set_lease(aid, lease + 500)  # a longer one (a code wait's) is kept
    svc.record_evidence(uuid.UUID(aid), "w1", gen, "disclosure", {"kind": "synthetic"})
    assert (attempt(aid).lease_expires_at - utcnow()).total_seconds() > lease + 400
    _set_lease(aid, -1)  # an expired one is never revived
    with pytest.raises(svc.LostAuthority):
        svc.record_evidence(uuid.UUID(aid), "w1", gen, "disclosure", {"kind": "synthetic"})
    with pytest.raises(svc.LostAuthority):
        svc.heartbeat(uuid.UUID(aid), "w1", gen)
    assert receiver.ledger()["accepted"] == 0


def test_a_slow_form_keeps_its_lease_while_it_makes_progress(api, receiver):
    """Every field takes a second, while filling and while reading back: longer in all than
    the worker's 15-second lease, and the read-back alone runs past the last renewal an upload
    gives. It renews the lease between fields and submits once. (The lease is long enough for
    the browser to start on a slow machine.)"""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault="between_fields=sleep:1", timeout=150,
                           extra_env={"NOEFFORTS_LEASE_SECONDS": "15"})  # fmt: skip
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == "confirmed", r.stderr[-800:]
    a = attempt(aid)
    assert a.state == "confirmed"
    assert (a.finished_at - a.disclosure_started_at).total_seconds() > 20  # well over a lease
    assert receiver.ledger()["accepted"] == 1


def test_a_worker_that_stops_making_progress_loses_its_lease(api, receiver):
    """No background heartbeat holds the lease for a stuck worker, as before D143: after its
    upload the worker does nothing for 20 s under a 15-second lease, and finds the lease gone
    at its next step. Nothing is submitted."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault="after_disclosure_recorded=sleep:20", timeout=150,
                           extra_env={"NOEFFORTS_LEASE_SECONDS": "15"})  # fmt: skip
    assert r.stdout.strip().splitlines()[-1] == "lost_authority", r.stderr[-800:]
    assert attempt(aid).state == "claimed"
    assert svc.sweep(publish_new=False)["abandoned"] == 1  # disclosed: never taken over
    assert receiver.ledger()["accepted"] == 0
    assert runner.run_attempt(aid, "w2") == "ignored"


def test_the_send_lease_covers_the_adapters_wait_for_the_answer(api, receiver):
    # What each adapter may wait: the generic form its submit timeout; the Greenhouse page a
    # 10-second click, then its watch (on a real page at least 75 s) and half again, because
    # the watch counts its own waits and not the page reads between them.
    assert FixtureAtsAdapter.send_watch_seconds(SimpleNamespace(), 30_000) == 30
    stand_in = SimpleNamespace(_stand_in=True)
    assert GreenhouseDomAdapter.send_watch_seconds(stand_in, 30_000) == 55
    real = SimpleNamespace(_stand_in=False)
    assert GreenhouseDomAdapter.send_watch_seconds(real, 30_000) == REAL_WATCH
    assert GreenhouseDomAdapter.send_watch_seconds(real, 120_000) == 190  # a longer timeout
    # The step that enters a code: on the Greenhouse page 12 s for its button first (18 by the
    # clock); elsewhere the same wait as the final click's.
    assert GreenhouseDomAdapter.code_watch_seconds(real, 30_000) == 18 + REAL_WATCH
    assert object.__new__(FixtureAtsAdapter).code_watch_seconds(30_000) == 30
    submit = get_settings().submit_timeout_seconds

    postings = iter(range(2, 9))

    def sending_lease(watch) -> float:  # each on a posting of its own: they all stay sending
        """The lease the send gate sets, in seconds from the moment the send began."""
        _, aid, gen = _claimed(api, receiver, url_suffix=f"?posting={next(postings)}")
        svc.gate_before_disclosure(uuid.UUID(aid), "w1", gen)
        if watch is None:
            svc.gate_before_send(uuid.UUID(aid), "w1", gen)
        else:
            svc.gate_before_send(uuid.UUID(aid), "w1", gen, watch)
        a = attempt(aid)
        assert a.state == "sending"
        return (a.lease_expires_at - a.send_started_at).total_seconds()

    assert sending_lease(None) == submit + 30  # as before
    assert sending_lease(REAL_WATCH) == REAL_WATCH + 30  # the real page's wait, and 30 s
    assert sending_lease(submit - 1) == submit + 30  # never under the submit timeout
    cap = get_settings().attempt_after_send_seconds
    assert cap > REAL_WATCH and sending_lease(10_000) == cap + 30  # bounded
    assert receiver.ledger()["accepted"] == 0


def test_the_greenhouse_watch_ends_by_the_clock_its_lease_was_sized_to():
    """The watch counts only its own 250 ms waits. With page reads of half a second each (a
    stand-in for a struggling page; no browser), a 1-second watch would run for almost four
    seconds. The clock ends it at half again, the figure the lease was sized to."""

    class Page:
        def wait_for_timeout(self, ms):
            time.sleep(ms / 1000)

    stub = SimpleNamespace(
        _stand_in=True,
        _code_boxes=lambda page: time.sleep(0.5),  # no code boxes, slowly
        _confirmed=lambda page: False,
        _form_errors=lambda page: [],
        _challenge_now=lambda page: False,
    )
    assert GreenhouseDomAdapter.send_watch_seconds(stub, 1000) == 10 + 2  # the click, then 1.5 s
    began = time.monotonic()
    out = GreenhouseDomAdapter._watch(stub, Page(), 1000, False, False, [], [], False)
    took = time.monotonic() - began
    assert out.kind == "unknown" and "no response" in out.detail
    assert 1.4 < took < 3.0, took  # by its waits alone: five steps of 0.75 s


# ------------------------------------------------------------------------------- cancelling


def test_a_cancel_after_entry_says_what_may_have_been_entered(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    p, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    try:
        wait_for(lambda: reached(gate), timeout=60)
        assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    finally:
        result = release(p, gate)
    assert result == "lost_authority"
    a = attempt(aid)
    assert a.state == "cancelled" and a.outcome_detail == svc.CANCELLED_AFTER_ENTRY
    led = receiver.ledger()
    assert led["accepted"] == 0 and len(led["disclosures"]) == 1  # the resume had been uploaded


def test_a_cancel_while_a_form_is_filled_stops_the_worker_between_fields(api, receiver):
    """The page saves each field as it changes (the receiver's autosave), and every field takes
    two seconds. Cancelled after the first fields, the worker finds its attempt gone at its next
    lease renewal (every 4 s here), between two fields: the rest are never entered, and nothing
    is submitted."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(autosave=True)
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    typed = [a for a in content["answers"] if a["value"] is not None and a["type"] != "file"]
    p = start_worker(aid, "w1", "between_fields=sleep:2", lease_seconds=16)
    try:
        wait_for(lambda: disclosed(receiver.ledger(), "autosave") >= 2, timeout=60)
        assert api.post(f"/applications/{app_id}/cancel").status_code == 200
        out, err = p.communicate(timeout=60)
    finally:
        if p.poll() is None:
            p.kill()
    assert out.strip().splitlines()[-1] == "lost_authority", err[-800:]
    a = attempt(aid)
    assert a.state == "cancelled" and a.outcome_detail == svc.CANCELLED_AFTER_ENTRY
    led = receiver.ledger()
    assert led["accepted"] == 0
    assert 2 <= disclosed(led, "autosave") < len(typed) - 2  # the rest were never entered


def test_a_cancelled_attempt_hands_over_no_document(api, receiver):
    """Cancelled right after the disclosure gate, with a lease so long that no renewal falls
    due while the first fields are typed: the worker still checks before it hands a document
    over, so the resume never reaches the employer."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(autosave=True)
    gate = tempfile.mktemp(prefix="release-")
    p = start_worker(aid, "w1", f"after_disclosure_gate=waitfile:{gate}", lease_seconds=240)
    try:
        wait_for(lambda: reached(gate), timeout=60)
        assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    finally:
        result = release(p, gate)
    assert result == "lost_authority"
    a = attempt(aid)
    assert a.state == "cancelled" and a.outcome_detail == svc.CANCELLED_AFTER_ENTRY
    led = receiver.ledger()
    assert disclosed(led, "autosave") >= 1  # fields before the document were typed ...
    assert uploads(led) == 0 and led["accepted"] == 0  # ... the document was never handed over


def test_a_cancel_before_anything_was_entered_says_so(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    p, gate = start_blocked_worker(aid, "w1", "before_navigate")
    try:
        wait_for(lambda: reached(gate), timeout=60)
        assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    finally:
        result = release(p, gate)
    assert result == "lost_authority"
    assert attempt(aid).outcome_detail == "Cancelled by you before anything was submitted."
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []


# ------------------------------------------------------------- a killed worker, both providers

PROVIDERS = ["greenhouse_dom", "fixture_workday"]


def send_watch(adapter: str) -> int:
    """What the adapter says it may wait for the final click's answer, with the submit timeout
    the workers here run with."""
    submit_ms = get_settings().submit_timeout_seconds * 1000
    if adapter == "greenhouse_dom":
        return GreenhouseDomAdapter.send_watch_seconds(SimpleNamespace(_stand_in=True), submit_ms)
    return FixtureAtsAdapter.send_watch_seconds(SimpleNamespace(), submit_ms)


@pytest.mark.parametrize("adapter", PROVIDERS)
def test_a_worker_killed_before_anything_was_sent_is_run_again_once(api, receiver, adapter):
    app_id = _browser_application(adapter, api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault="before_navigate=exit")
    assert r.returncode == 137
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    expire_lease(aid)
    assert svc.sweep(publish_new=False)["repended"] == 1
    assert runner.run_attempt(aid, "w2") == "confirmed"
    assert attempt(aid).adapter == adapter
    assert receiver.ledger()["accepted"] == 1
    assert runner.run_attempt(aid, "w3") == "ignored"
    assert receiver.ledger()["accepted"] == 1


# point: (state the kill leaves, what the sweeper counts, final state, application, accepted)
KILLS = {
    "before_send_gate": ("claimed", "abandoned", "abandoned", "needs_user_action", 0),
    "before_click": ("sending", "unknown", "unknown", "submitted_unconfirmed", 0),
    "after_click": ("sending", "unknown", "unknown", "submitted_unconfirmed", 1),
    "after_receipt_before_commit": ("sending", "unknown", "unknown", "submitted_unconfirmed", 1),
}


@pytest.mark.parametrize("point", list(KILLS))
@pytest.mark.parametrize("adapter", PROVIDERS)
def test_a_worker_killed_after_entering_data_is_never_run_again(api, receiver, adapter, point):
    """Killed after the form was filled, at the send gate, around the final click, or after the
    employer's receipt but before it was recorded: the sweeper abandons it or calls the outcome
    unknown, and nothing sends it a second time. The ledger says what the employer holds."""
    left, counted, final, application, accepted = KILLS[point]
    app_id = _browser_application(adapter, api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault=f"{point}=exit")
    assert r.returncode == 137
    a = attempt(aid)
    assert a.adapter == adapter and a.state == left and a.disclosure_started_at is not None
    if point == "before_click":
        # The send lease the runner asked for: this adapter's wait for the answer, and 30 s.
        assert (a.lease_expires_at - a.send_started_at).total_seconds() == send_watch(adapter) + 30
    led = receiver.ledger()
    assert led["accepted"] == accepted
    assert uploads(led) > 0  # the resume reached it
    expire_lease(aid)
    assert svc.sweep(publish_new=False)[counted] == 1
    assert attempt(aid).state == final and app_state(api, app_id) == application
    assert runner.run_attempt(aid, "w2") == "ignored"
    again = receiver.ledger()
    assert again["accepted"] == accepted and again["requests"] == led["requests"]


@pytest.mark.parametrize("point,counted,final,application", [
    ("before_send_gate", "abandoned", "abandoned", "needs_user_action"),
    ("before_click", "unknown", "unknown", "submitted_unconfirmed"),
])  # fmt: skip
def test_a_worker_killed_on_the_wizards_review_page_is_never_run_again(
    api, receiver, point, counted, final, application
):
    from tests.test_workday_wizard import CODE, approve, draft_pages, wizard_application

    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault=f"{point}=exit")
    assert r.returncode == 137
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and led["accepted"] == 0
    expire_lease(aid)
    assert svc.sweep(publish_new=False)[counted] == 1
    assert attempt(aid).state == final and app_state(api, app_id) == application
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    again = receiver.ledger()
    assert again["accepted"] == 0 and again["requests"] == led["requests"]
