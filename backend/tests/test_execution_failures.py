"""Failure injection against the independent receiver. Every assertion about what reached the
employer uses the receiver's own ledger. Faults use NOEFFORTS_FAULT (honoured only in tests):
`exit` simulates SIGKILL at that point (no cleanup, no commit)."""

import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt, OutboxMessage
from tests.execution_harness import (
    BACKEND,
    PDF,
    Receiver,
    attempt,
    prepared_application,
    queue,
    run_worker_process,
)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def expire_lease(aid: str) -> None:
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()


def start_blocked_worker(aid: str, worker: str, point: str) -> tuple[subprocess.Popen, str]:
    gate = tempfile.mktemp(prefix="release-")
    env = os.environ | {"NOEFFORTS_FAULT": f"{point}=waitfile:{gate}", "PYTHONPATH": str(BACKEND)}
    p = subprocess.Popen(
        [sys.executable, "-m", "app.modules.execution.cli", "run", aid, worker],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return p, gate


def reached(gate: str) -> bool:
    """The blocked worker is waiting at its fault point (not merely past an earlier step)."""
    return os.path.exists(gate + ".waiting")


def wait_for(pred, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    raise AssertionError("condition not reached")


def release(p: subprocess.Popen, gate: str) -> str:
    open(gate, "w").close()
    out, err = p.communicate(timeout=90)
    return out.strip().splitlines()[-1] if out.strip() else err[-500:]


def ready(api, receiver, **kw) -> tuple[str, str]:
    app_id = prepared_application(api, receiver, **kw)
    return app_id, queue(api, app_id)


# ---------------------------------------------------------------- duplicate delivery


def test_duplicate_delivery_sequential_is_ignored(api, receiver):
    receiver.config(idempotent=False)  # receiver would happily accept twice
    _, aid = ready(api, receiver)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1


def test_competing_workers_on_one_attempt_send_once(api, receiver):
    receiver.config(idempotent=False)
    _, aid = ready(api, receiver)
    results = []
    threads = [
        threading.Thread(
            target=lambda w=w: results.append(run_worker_process(aid, w).stdout.strip())
        )
        for w in ("wa", "wb", "wc")
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["confirmed", "ignored", "ignored"]
    assert receiver.ledger()["accepted"] == 1


def test_second_active_attempt_is_blocked_by_database(api, receiver):
    app_id, aid = ready(api, receiver)
    with SessionLocal() as db:
        a = db.get(ExecutionAttempt, uuid.UUID(aid))
        db.add(
            ExecutionAttempt(
                application_id=a.application_id,
                user_id=a.user_id,
                package_id=a.package_id,
                package_hash=a.package_hash,
                approval_id=a.approval_id,
                adapter=a.adapter,
            )
        )
        with pytest.raises(Exception, match="uq_one_active_attempt"):
            db.commit()


# ---------------------------------------------------------------- crashes


def test_crash_before_any_external_write_is_retried_once_safely(api, receiver):
    app_id, aid = ready(api, receiver)
    r = run_worker_process(aid, "w1", fault="before_navigate=exit")
    assert r.returncode == 137
    assert receiver.ledger()["accepted"] == 0 and receiver.ledger()["disclosures"] == []
    expire_lease(aid)
    assert svc.sweep()["repended"] == 1
    assert runner.run_attempt(aid, "w2") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_crash_after_disclosure_is_not_retried(api, receiver):
    app_id, aid = ready(api, receiver)
    r = run_worker_process(aid, "w1", fault="before_send_gate=exit")
    assert r.returncode == 137
    led = receiver.ledger()
    assert led["accepted"] == 0 and len(led["disclosures"]) == 1  # resume was uploaded
    expire_lease(aid)
    assert svc.sweep()["abandoned"] == 1
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"


def test_crash_at_final_send_boundary_becomes_unknown(api, receiver):
    app_id, aid = ready(api, receiver)
    r = run_worker_process(aid, "w1", fault="before_click=exit")
    assert r.returncode == 137
    assert attempt(aid).state == "sending"
    expire_lease(aid)
    assert svc.sweep()["unknown"] == 1
    assert runner.run_attempt(aid, "w2") == "ignored"  # never retried
    assert receiver.ledger()["accepted"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"


def test_crash_after_receipt_before_local_commit(api, receiver):
    app_id, aid = ready(api, receiver)
    r = run_worker_process(aid, "w1", fault="after_receipt_before_commit=exit")
    assert r.returncode == 137
    assert receiver.ledger()["accepted"] == 1  # employer has it; we never recorded it
    expire_lease(aid)
    assert svc.sweep()["unknown"] == 1
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    # Reconciliation needs an explicit check; re-queueing then needs a fresh approval.
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={"finding": "received", "evidence": "Receiver ledger shows one receipt"},
    )
    assert r.json()["state"] == "submitted_confirmed"


def test_accepted_but_response_dropped(api, receiver):
    receiver.config(mode="drop_after_accept")
    app_id, aid = ready(api, receiver)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"


@pytest.mark.parametrize("nav_s", [10, 4])
def test_giving_up_on_a_dropped_response_sends_nothing_more(api, receiver, monkeypatch, nav_s):
    """Found by the browser test: when the worker gave up waiting and closed the browser while
    the intercepted submit request was still pending, a second copy of the POST reached the
    employer. nav_s == submit timeout (4s) is the timing the browser test hit."""
    monkeypatch.setattr(get_settings(), "navigation_timeout_seconds", nav_s)
    receiver.config(mode="drop_after_accept")
    app_id, aid = ready(api, receiver)
    assert runner.run_attempt(aid, "w1") == "unknown"
    time.sleep(3)  # bounded observation window: a late duplicate would land here
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize(
    "mode,expected,accepted",
    [
        ("error_after_accept", "unknown", 1),
        ("error_before_accept", "unknown", 0),  # indistinguishable from outside: stays unknown
        ("validation_fail", "rejected", 0),
        ("expired_session", "rejected", 0),
        ("upload_fail", "abandoned", 0),
        ("conditional_field", "failed_safe", 0),
    ],
)
def test_receiver_failure_modes(api, receiver, mode, expected, accepted):
    app_id, aid = ready(api, receiver)  # approve against the normal form...
    receiver.config(mode=mode)  # ...then the employer side changes behaviour
    assert runner.run_attempt(aid, "w1") == expected
    led = receiver.ledger()
    assert led["accepted"] == accepted
    if mode == "conditional_field":
        assert led["disclosures"] == []  # form change detected before entering anything
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == accepted


def test_slow_but_successful_response(api, receiver):
    receiver.config(mode="delay", delay_s=2)
    _, aid = ready(api, receiver)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


# ---------------------------------------------------------------- stale workers


def test_old_worker_cannot_continue_after_lease_loss(api, receiver):
    receiver.config(idempotent=False)
    _, aid = ready(api, receiver)
    old, gate = start_blocked_worker(aid, "old", "after_claim")
    wait_for(lambda: attempt(aid).state == "claimed")
    expire_lease(aid)
    assert svc.sweep()["repended"] == 1
    assert runner.run_attempt(aid, "new") == "confirmed"
    assert release(old, gate) == "lost_authority"
    assert receiver.ledger()["accepted"] == 1


def test_no_takeover_while_old_worker_may_have_disclosed(api, receiver):
    _, aid = ready(api, receiver)
    old, gate = start_blocked_worker(aid, "old", "before_send_gate")
    # Wait for the worker to sit at the gate: earlier, it may still hold the attempt's row lock
    # while recording evidence, and the sweeper skips locked rows.
    assert wait_for(lambda: reached(gate))
    assert attempt(aid).disclosure_started_at is not None
    assert len(receiver.ledger()["disclosures"]) == 1
    expire_lease(aid)
    assert svc.sweep()["abandoned"] == 1  # not re-pended: no replacement worker
    assert release(old, gate) == "lost_authority"
    assert receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------- approval races


def test_revocation_before_claim(api, receiver):
    app_id, aid = ready(api, receiver)
    api.post(f"/applications/{app_id}/package/revoke")
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert attempt(aid).state == "failed_safe"
    assert receiver.ledger()["accepted"] == 0


def test_revocation_while_preparing_stops_before_disclosure(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_navigate")
    wait_for(lambda: attempt(aid).state == "claimed")
    api.post(f"/applications/{app_id}/package/revoke")
    assert release(w, gate) == "failed_safe"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []


def test_revocation_after_disclosure_stops_before_send(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    api.post(f"/applications/{app_id}/package/revoke")
    assert release(w, gate) == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_document_change_after_approval_stops_send(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    resume = api.get("/documents").json()[0]
    api.post(
        "/documents",
        files={"file": ("resume2.pdf", PDF + b"v2", "application/pdf")},
        data={"lineage_id": resume["lineage_id"]},
    )
    assert release(w, gate) == "abandoned"
    assert "changed after approval" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_protected_fact_change_while_running_stops_send(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    wa = api.get("/profile/work-authorizations").json()[0]
    api.put(
        f"/profile/work-authorizations/{wa['id']}",
        json={
            "country_code": "US",
            "authorized": "yes",
            "sponsorship_needed_now": "no",
            "sponsorship_needed_future": "yes",
        },
    )
    assert release(w, gate) == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_cancel_before_send_gate_wins(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    assert api.post(f"/applications/{app_id}/cancel").json()["state"] == "cancelled"
    assert release(w, gate) == "lost_authority"
    assert receiver.ledger()["accepted"] == 0


def test_cancel_after_send_gate_is_refused(api, receiver):
    app_id, aid = ready(api, receiver)
    w, gate = start_blocked_worker(aid, "w1", "before_click")
    wait_for(lambda: attempt(aid).state == "sending")
    r = api.post(f"/applications/{app_id}/cancel")
    assert r.status_code == 409 and "in flight" in r.json()["detail"]
    assert release(w, gate) == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_cancel_reports_only_its_own_refusals(api, receiver, monkeypatch):
    import sqlalchemy as sa

    app_id, aid = ready(api, receiver)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    r = api.post(f"/applications/{app_id}/cancel")  # a terminal state: NoEfforts' own refusal
    assert r.status_code == 400 and "cancelled" in r.json()["detail"]

    raw = "UPDATE applications SET state=%(state)s -- sam.synthetic@example.com"

    def broken(db, app):
        raise sa.exc.OperationalError(raw, {"state": "x"}, Exception("lock timeout"))

    monkeypatch.setattr(svc, "cancel", broken)
    # Any other error is not turned into a 400 carrying its text; it stays a server error.
    with pytest.raises(sa.exc.OperationalError):
        api.post(f"/applications/{app_id}/cancel")


# ---------------------------------------------------------------- broker outage


def test_broker_outage_after_commit_loses_nothing(api, receiver):
    """Simulated publish failure (the publish function raises, as a down broker would)."""
    app_id, aid = ready(api, receiver)

    def down(topic, attempt_id):
        raise ConnectionError("broker unavailable")

    assert svc.relay_outbox(down) == 0
    with SessionLocal() as db:
        m = db.query(OutboxMessage).filter_by(attempt_id=uuid.UUID(aid)).one()
        assert m.dispatched_at is None and "broker unavailable" in m.last_error
    published = []
    assert svc.relay_outbox(lambda t, a: published.append(a)) == 1
    assert published == [aid]
    assert svc.relay_outbox(lambda t, a: published.append(a)) == 0  # not published twice
    assert runner.run_attempt(published[0], "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
