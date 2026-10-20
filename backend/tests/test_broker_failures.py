"""Real broker failures. A disposable Redis process (port 6391, no persistence) and real Celery
worker processes; the receiver ledger is the oracle.

Production differences: these tests shorten the visibility timeout to 5s
(NOEFFORTS_BROKER_VISIBILITY_TIMEOUT_SECONDS) on the disposable broker only; production keeps
3600s. Everything else uses app/worker.py unchanged."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta

import pytest
import redis

from app.core.db import SessionLocal, utcnow
from app.modules.execution import service as svc
from app.modules.execution.models import AttemptEvent, ExecutionAttempt, OutboxMessage
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue

PORT = 6391
BROKER = f"redis://127.0.0.1:{PORT}/0"


class Broker:
    def __init__(self):
        self.p = None
        self.start()

    def start(self):
        self.p = subprocess.Popen(
            [
                "redis-server",
                "--port",
                str(PORT),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                tempfile.gettempdir(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                redis.Redis(port=PORT).ping()
                return
            except redis.ConnectionError:
                time.sleep(0.05)
        raise RuntimeError("disposable redis did not start")

    def stop(self):
        self.p.terminate()
        self.p.wait(timeout=10)

    def client(self):
        return redis.Redis(port=PORT)


def env(**extra):
    return (
        os.environ
        | {"NOEFFORTS_REDIS_URL": BROKER, "PYTHONPATH": str(BACKEND), "NOEFFORTS_FAULT": ""}
        | extra
    )


class Worker:
    def __init__(self, **extra):
        self.log = tempfile.mktemp(prefix="celery-", suffix=".log")
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
                "1",
                "--loglevel=INFO",
                "-n",
                f"bw-{uuid.uuid4().hex[:6]}@%h",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
            ],
            cwd=BACKEND,
            env=env(**extra),
            stdout=open(self.log, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.wait("ready", 60)

    def text(self):
        return open(self.log).read()

    def wait(self, needle, timeout=60, count=1):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.text().count(needle) >= count:
                return
            time.sleep(0.2)
        raise AssertionError(f"{needle!r} x{count} not in log:\n{self.text()[-3000:]}")

    def kill_hard(self):
        """SIGKILL the whole worker (main process and pool children): no ack, no cleanup."""
        os.killpg(self.p.pid, signal.SIGKILL)
        self.p.wait(timeout=10)

    def stop(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(self.p.pid, signal.SIGKILL)


def relay() -> str:
    r = subprocess.run(
        [sys.executable, "-m", "app.modules.execution.cli", "relay"],
        cwd=BACKEND,
        env=env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.stdout.strip()


def wait_attempt(aid, states, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if attempt(aid).state in states:
            return attempt(aid).state
        time.sleep(0.2)
    raise AssertionError(f"attempt stuck in {attempt(aid).state}")


def claims(aid):
    with SessionLocal() as db:
        return db.query(AttemptEvent).filter_by(attempt_id=uuid.UUID(aid), kind="claimed").count()


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture
def broker():
    b = Broker()
    yield b
    if b.p.poll() is None:
        b.stop()


@pytest.fixture(autouse=True)
def _reset_receiver(receiver):
    receiver.reset()


def test_real_broker_outage_around_outbox_publication(api, receiver, broker):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    broker.stop()  # real outage: the Redis process is gone
    t0 = time.monotonic()
    assert relay() == "0"
    assert time.monotonic() - t0 < 30  # bounded: the relay does not hang on a dead broker
    with SessionLocal() as db:
        m = db.query(OutboxMessage).filter_by(attempt_id=uuid.UUID(aid)).one()
        assert m.dispatched_at is None and m.last_error
    broker.start()  # broker back, empty (no persistence): only the outbox remembers
    w = Worker()
    try:
        assert relay() == "1"
        assert wait_attempt(aid, {"confirmed", "unknown", "abandoned"}) == "confirmed"
        assert relay() == "0"
    finally:
        w.stop()
    assert receiver.ledger()["accepted"] == 1


def test_worker_survives_broker_restart(api, receiver, broker):
    w = Worker()
    try:
        broker.stop()
        time.sleep(1)
        broker.start()
        app_id = prepared_application(api, receiver)
        aid = queue(api, app_id)
        assert relay() == "1"
        assert wait_attempt(aid, {"confirmed", "unknown", "abandoned"}, 90) == "confirmed"
    finally:
        w.stop()
    assert receiver.ledger()["accepted"] == 1


def _killed_mid_send_then_redelivered(api, receiver, broker, *, mode, fault=""):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    if mode:
        receiver.config(mode=mode)
    w1 = Worker(
        NOEFFORTS_BROKER_VISIBILITY_TIMEOUT_SECONDS="5",
        NOEFFORTS_SUBMIT_TIMEOUT_SECONDS="120",
        NOEFFORTS_FAULT=fault,
    )
    assert relay() == "1"
    end = time.monotonic() + 60
    while receiver.ledger()["accepted"] < 1 and time.monotonic() < end:
        time.sleep(0.2)
    assert receiver.ledger()["accepted"] == 1
    assert attempt(aid).state == "sending"
    w1.kill_hard()
    # The message was reserved with acks_late and never acknowledged.
    assert broker.client().hlen("unacked") == 1
    # Observed with kombu 5.6.2 and this configuration (not a general timing guarantee): unacked
    # messages older than the visibility timeout are restored when a worker starts
    # (on_poll_init) and then roughly every 100 s. Let the 5 s timeout lapse so the
    # replacement worker's startup restore redelivers it.
    time.sleep(6)
    w2 = Worker(NOEFFORTS_BROKER_VISIBILITY_TIMEOUT_SECONDS="5")
    try:
        w2.wait("Task noefforts.execute_attempt[", timeout=90)  # a real redelivery
        w2.wait("'ignored'", timeout=60)  # refused by the claim compare-and-swap
    finally:
        w2.stop()
    assert broker.client().hlen("unacked") == 0  # redelivered and acknowledged
    assert claims(aid) == 1
    assert receiver.ledger()["accepted"] == 1
    # The dead worker's lease is simulated as expired here rather than waited out (it was
    # set to submit timeout + 30s); the sweeper then quarantines the attempt.
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.sweep()["unknown"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"


def test_redelivery_after_accepted_but_response_lost(api, receiver, broker):
    _killed_mid_send_then_redelivered(api, receiver, broker, mode="drop_after_accept")


def test_redelivery_after_crash_after_acceptance(api, receiver, broker):
    gate = tempfile.mktemp(prefix="never-")  # never created: the worker blocks, then dies
    _killed_mid_send_then_redelivered(
        api, receiver, broker, mode=None, fault=f"after_receipt_before_commit=waitfile:{gate}"
    )
