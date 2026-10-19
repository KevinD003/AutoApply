"""Evidence retention, user deletion, tenancy, and secrets in real worker logs."""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta

import pytest

from app.core.db import SessionLocal, utcnow
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import Evidence
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue

FAKE_SECRET = "SYNTHETIC-SECRET-LOG-CHECK-91C2"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def evidence_count(app_id) -> int:
    with SessionLocal() as db:
        return db.query(Evidence).filter_by(application_id=uuid.UUID(app_id)).count()


def test_retention_purge(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    n = evidence_count(app_id)
    assert n >= 3  # disclosure, readback, receipt
    with SessionLocal() as db:
        rows = db.query(Evidence).filter_by(application_id=uuid.UUID(app_id)).all()
        assert all(r.retain_until > utcnow() + timedelta(days=300) for r in rows)
        rows[0].retain_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.purge_expired_evidence() == 1
    assert evidence_count(app_id) == n - 1


def test_user_can_delete_evidence_and_others_cannot(api, receiver, other_api):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert other_api.delete(f"/applications/{app_id}/evidence").status_code == 404
    assert evidence_count(app_id) > 0
    r = api.delete(f"/applications/{app_id}/evidence")
    assert r.status_code == 200 and r.json()["deleted"] > 0
    assert evidence_count(app_id) == 0
    assert api.get(f"/applications/{app_id}/attempts").json()[0]["evidence"] == []
    assert attempt(aid).state == "confirmed"  # the outcome itself stays


def test_cannot_delete_evidence_while_running(api, receiver):
    app_id = prepared_application(api, receiver)
    queue(api, app_id)
    r = api.delete(f"/applications/{app_id}/evidence")
    assert r.status_code == 409


def test_no_secrets_in_real_worker_logs(api, receiver):
    """Run a real Celery worker at INFO level and scan everything it wrote."""
    app_id = prepared_application(api, receiver, why_text=f"Intake work. {FAKE_SECRET}")
    aid = queue(api, app_id)
    log = tempfile.mktemp(prefix="celery-leak-", suffix=".log")
    env = os.environ | {"PYTHONPATH": str(BACKEND), "NOEFFORTS_FAULT": ""}
    w = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.worker",
            "worker",
            "-P",
            "prefork",
            "-c",
            "1",
            "--loglevel=DEBUG",
            "-n",
            f"leak-{uuid.uuid4().hex[:6]}@%h",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ],
        cwd=BACKEND,
        env=env,
        stdout=open(log, "w"),
        stderr=subprocess.STDOUT,
    )
    try:
        from app.worker import publish

        end = time.monotonic() + 60
        while "ready" not in open(log).read() and time.monotonic() < end:
            time.sleep(0.2)
        assert svc.relay_outbox(publish) == 1
        while (
            attempt(aid).state not in ("confirmed", "unknown", "abandoned")
            and time.monotonic() < end + 60
        ):
            time.sleep(0.2)
    finally:
        w.terminate()
        w.wait(timeout=20)
    assert attempt(aid).state == "confirmed"
    text = open(log).read()
    assert "execute_attempt" in text  # the log really captured the task
    for needle in (FAKE_SECRET, "sam.synthetic@example.com", "+1 555 0100", "Springfield"):
        assert needle not in text, needle
    assert receiver.ledger()["accepted"] == 1
