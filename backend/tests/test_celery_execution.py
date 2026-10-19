"""Real Celery worker (prefork, pinned settings in app/worker.py) with Redis, against the
receiver. Verifies duplicate deliveries and worker-process death behave as documented."""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta

import pytest
import redis

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.execution import service as svc
from app.modules.execution.models import AttemptEvent, ExecutionAttempt
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _clean_broker(receiver):
    receiver.reset()
    r = redis.Redis.from_url(get_settings().redis_url)
    r.delete("celery", "unacked", "unacked_index")


class Worker:
    def __init__(self, fault: str = "", name: str = "w"):
        self.log = tempfile.mktemp(prefix="celery-", suffix=".log")
        env = os.environ | {"NOEFFORTS_FAULT": fault, "PYTHONPATH": str(BACKEND)}
        self.p = subprocess.Popen(
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
                "2",
                "--loglevel=INFO",
                "-n",
                f"{name}-{uuid.uuid4().hex[:6]}@%h",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
            ],
            cwd=BACKEND,
            env=env,
            stdout=open(self.log, "w"),
            stderr=subprocess.STDOUT,
        )
        self.wait_log("ready", 60)

    def text(self) -> str:
        return open(self.log).read()

    def wait_log(self, needle, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if needle in self.text():
                return
            time.sleep(0.2)
        raise AssertionError(f"'{needle}' not in worker log:\n{self.text()[-3000:]}")

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def wait_state(aid, states, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = attempt(aid).state
        if s in states:
            return s
        time.sleep(0.2)
    raise AssertionError(f"attempt stuck in {attempt(aid).state}")


def claims(aid) -> int:
    with SessionLocal() as db:
        return db.query(AttemptEvent).filter_by(attempt_id=uuid.UUID(aid), kind="claimed").count()


def test_duplicate_deliveries_through_celery_send_once(api, receiver):
    from app.worker import publish

    receiver.config(idempotent=False)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w = Worker()
    try:
        assert svc.relay_outbox(publish) == 1
        publish("execute_attempt", aid)  # duplicate delivery
        publish("execute_attempt", aid)  # and another
        assert wait_state(aid, {"confirmed", "unknown", "abandoned", "failed_safe"}) == "confirmed"
        w.wait_log("succeeded", 30)
        time.sleep(3)  # let the duplicates run to completion
    finally:
        w.stop()
    assert receiver.ledger()["accepted"] == 1
    assert claims(aid) == 1
    assert w.text().count("'ignored'") >= 2, w.text()[-2000:]


def test_worker_process_death_at_send_is_not_redelivered(api, receiver):
    from app.worker import publish

    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w = Worker(fault="before_click=exit")
    try:
        svc.relay_outbox(publish)
        wait_state(aid, {"sending"})
        w.wait_log("WorkerLostError", 60)
        time.sleep(4)  # if Celery were to redeliver, it would do so now
        r = redis.Redis.from_url(get_settings().redis_url)
        assert r.llen("celery") == 0 and r.hlen("unacked") == 0
    finally:
        w.stop()
    assert claims(aid) == 1
    assert attempt(aid).state == "sending"
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.sweep()["unknown"] == 1
    assert receiver.ledger()["accepted"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"


def test_death_before_any_write_recovers_through_outbox(api, receiver):
    from app.worker import publish

    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w1 = Worker(fault="before_navigate=exit", name="crashy")
    try:
        svc.relay_outbox(publish)
        w1.wait_log("WorkerLostError", 60)
    finally:
        w1.stop()
    assert receiver.ledger()["accepted"] == 0
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.sweep()["repended"] == 1
    w2 = Worker(name="healthy")
    try:
        assert svc.relay_outbox(publish) == 1
        assert wait_state(aid, {"confirmed", "unknown", "abandoned"}) == "confirmed"
    finally:
        w2.stop()
    assert receiver.ledger()["accepted"] == 1
    assert claims(aid) == 2  # one per generation; the first never got past navigation
