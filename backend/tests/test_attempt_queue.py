"""D144: an attempt's task has a queue and a worker of its own. An attempt may keep its worker
process for the whole wait for a verification code (D143), so the schedule's tasks (the sweeper,
the outbox relay, the mailbox reader and the rest) run on another worker and never wait behind
one. Real Celery workers (prefork) on the run's own Redis, the receiver's ledger as the oracle
for what reached the employer. Every form is a local stand-in; synthetic data only."""

import os
import subprocess
import sys
import tempfile
import time
import uuid

import pytest
import redis

from app.core.config import get_settings
from app.modules.execution import service as svc
from app.modules.execution.browser import WORKDIR_PREFIX
from tests.execution_harness import BACKEND, Receiver, attempt, prepared_application, queue
from tests.test_celery_execution import Worker, claims, clean_broker, queued, wait_state
from tests.test_code_wait_quarantine import open_checkpoint

ROOT = BACKEND.parent
ENDED = {"confirmed", "unknown", "abandoned", "failed_safe", "rejected"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset_receiver_and_broker(receiver):
    receiver.reset()
    clean_broker()
    yield
    clean_broker()


def broker() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def wait_until(pred, timeout=60, what="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def publish_as_before_the_queues(topic: str, attempt_id: str) -> None:
    """What a relay from before D144 did: the attempt's task on the default queue."""
    from app.worker import DEFAULT_QUEUE, celery_app

    assert topic == "execute_attempt"
    celery_app.send_task("noefforts.execute_attempt", args=[attempt_id], queue=DEFAULT_QUEUE)


# ---------------------------------------------------------------------------------- routing


def test_only_an_attempts_task_goes_to_the_attempts_queue():
    """Every task but an attempt's is routed to the default queue, and the schedule names none
    that is not: a task added to the attempts' queue, or an attempt's task left on the default
    one, fails here."""
    from app.worker import ATTEMPT_QUEUE, DEFAULT_QUEUE, celery_app, execute_attempt

    celery_app.loader.import_default_modules()
    tasks = sorted(n for n in celery_app.tasks if n.startswith("noefforts."))
    routed = {n: celery_app.amqp.router.route({}, n)["queue"].name for n in tasks}
    assert len(tasks) >= 10 and routed.pop(execute_attempt.name) == ATTEMPT_QUEUE
    assert set(routed.values()) == {DEFAULT_QUEUE}, routed
    assert (DEFAULT_QUEUE, ATTEMPT_QUEUE) == ("celery", "attempts")
    # Both are declared, so a worker started without -Q takes both (local development, tests).
    # Each has an exchange and a routing key of its own name (the next test reads what that
    # makes of the broker's bindings).
    declared = {q.name: (q.exchange.name, q.exchange.type, q.routing_key)
                for q in celery_app.amqp.queues.values()}  # fmt: skip
    assert declared == {
        DEFAULT_QUEUE: (DEFAULT_QUEUE, "direct", DEFAULT_QUEUE),
        ATTEMPT_QUEUE: (ATTEMPT_QUEUE, "direct", ATTEMPT_QUEUE),
    }
    assert celery_app.conf.task_default_queue == DEFAULT_QUEUE
    scheduled = {e["task"] for e in celery_app.conf.beat_schedule.values()}
    assert scheduled == set(routed), (scheduled, routed)  # all of them periodic, none an attempt


def test_each_queue_is_bound_to_its_own_exchange_only():
    """What the declaration makes of the broker: each queue under an exchange of its own name
    and nowhere else. Declared by name only, both would sit under the default exchange with one
    key, and a message published to that exchange and key would reach both (a probe showed it;
    Celery's own publishing addresses a queue directly and reaches one either way)."""
    from app.worker import ATTEMPT_QUEUE, DEFAULT_QUEUE, celery_app

    r = broker()
    names = (DEFAULT_QUEUE, ATTEMPT_QUEUE)
    r.delete(*(f"_kombu.binding.{n}" for n in names))  # as a broker that never saw them
    with celery_app.connection_for_write() as conn:
        for name in names:
            celery_app.amqp.queues[name](conn.default_channel).declare()
    bound = {
        n: sorted(m.decode().split("\x06\x16")[-1] for m in r.smembers(f"_kombu.binding.{n}"))
        for n in names
    }
    assert bound == {DEFAULT_QUEUE: [DEFAULT_QUEUE], ATTEMPT_QUEUE: [ATTEMPT_QUEUE]}


def test_each_message_reaches_one_queue_only(api, receiver):
    """On the real broker: an attempt's message is in the attempts' queue and not in the
    default one, however it is published (the relay, or the task's own `delay`); a periodic
    task's is in the default queue and not in the attempts'."""
    from app.worker import celery_app, execute_attempt, publish

    aid = queue(api, prepared_application(api, receiver))
    assert svc.relay_outbox(publish) == 1
    assert queued(broker()) == {"celery": 0, "attempts": 1}
    execute_attempt.delay(aid)
    assert queued(broker()) == {"celery": 0, "attempts": 2}
    celery_app.send_task("noefforts.sweep_attempts")
    assert queued(broker()) == {"celery": 1, "attempts": 2}
    assert attempt(aid).state == "pending"


def test_a_worker_started_without_queues_takes_both(api, receiver):
    """Local development and the tests: one worker, no -Q. It runs an attempt and a periodic
    task alike (with no separation between them)."""
    from app.worker import celery_app, publish

    aid = queue(api, prepared_application(api, receiver))
    w = Worker()
    try:
        assert svc.relay_outbox(publish) == 1
        celery_app.send_task("noefforts.sweep_attempts")
        assert wait_state(aid, ENDED) == "confirmed"
        w.wait_log("Task noefforts.sweep_attempts[", 30)
    finally:
        w.stop()
    assert receiver.ledger()["accepted"] == 1 and claims(aid) == 1


# -------------------------------------------------------------- separation of the two workers


def test_two_attempts_waiting_for_codes_do_not_hold_up_the_periodic_tasks(api, receiver):
    """The attempts' worker has two processes, and both are held by attempts waiting for their
    emailed codes. A periodic task published meanwhile is run at once by the other worker, which
    finds nothing to recover; a third application waits in the attempts' queue, unclaimed. Both
    codes are then entered and both applications submitted, once each."""
    from app.worker import celery_app, publish

    receiver.config(mode="otp")
    attempts_worker = Worker(
        queues="attempts", concurrency=2, NOEFFORTS_CHECKPOINT_TTL_SECONDS="120"
    )
    periodic_worker = Worker(queues="celery", concurrency=1)
    waiting = []
    try:
        for n in (1, 2):
            app_id = prepared_application(api, receiver, url_suffix=f"?posting={n}")
            aid = queue(api, app_id)
            assert svc.relay_outbox(publish) == 1
            assert wait_state(aid, {"awaiting_code"} | ENDED) == "awaiting_code"
            # The newest challenge is this attempt's: the other one asked before it was queued.
            code = receiver.ledger()["challenges"][-1]["code"]
            waiting.append((app_id, aid, open_checkpoint(api, app_id), code))
        # A third application: its message stays in the attempts' queue, both processes held.
        third = queue(api, prepared_application(api, receiver, url_suffix="?posting=3"))
        assert svc.relay_outbox(publish) == 1
        swept = "Task noefforts.sweep_attempts["
        celery_app.send_task("noefforts.sweep_attempts")
        periodic_worker.wait_log(swept, 20)
        periodic_worker.wait_log("succeeded", 20)
        assert swept not in attempts_worker.text()
        assert [attempt(aid).state for _, aid, _, _ in waiting] == ["awaiting_code"] * 2
        assert attempt(third).state == "pending" and claims(third) == 0
        assert queued(broker()) == {"celery": 0, "attempts": 1}
        assert "'repended': 0, 'abandoned': 0, 'unknown': 0" in periodic_worker.text()
        assert "Task noefforts.execute_attempt[" not in periodic_worker.text()
        receiver.config(mode="normal")  # the third application's form asks for no code
        for app_id, _aid, cp, code in waiting:
            url = f"/applications/{app_id}/checkpoints/{cp['id']}/code"
            assert api.post(url, json={"round": 1, "code": code}).status_code == 202
        for _, aid, _, _ in waiting:
            assert wait_state(aid, ENDED) == "confirmed"
        assert wait_state(third, ENDED, timeout=90) == "confirmed"
    finally:
        attempts_worker.stop()
        periodic_worker.stop()
    assert receiver.ledger()["accepted"] == 3
    assert [claims(aid) for _, aid, _, _ in waiting] + [claims(third)] == [1, 1, 1]


def test_a_message_on_another_queue_is_passed_on_and_never_run_there(api, receiver):
    """A message published before the queues existed sits on the default queue. The worker of
    that queue passes it to the attempts' queue and claims nothing; the attempts' worker then
    runs it, once."""
    aid = queue(api, prepared_application(api, receiver))
    assert svc.relay_outbox(publish_as_before_the_queues) == 1
    assert queued(broker()) == {"celery": 1, "attempts": 0}
    requests_before = receiver.ledger()["requests"]  # the form as it was read, nothing more
    periodic_worker = Worker(queues="celery", concurrency=1)
    try:
        periodic_worker.wait_log("succeeded in", 30)
        passed_on = {"celery": 0, "attempts": 1}
        wait_until(lambda: queued(broker()) == passed_on, 20, "the message to be passed on")
        assert "'forwarded'" in periodic_worker.text()
        assert attempt(aid).state == "pending" and claims(aid) == 0
        assert receiver.ledger()["requests"] == requests_before  # that worker opened nothing
        attempts_worker = Worker(queues="attempts", concurrency=1)
        try:
            assert wait_state(aid, ENDED) == "confirmed"
            attempts_worker.wait_log("'confirmed'", 30)
        finally:
            attempts_worker.stop()
        # Received and passed on, each logged once; never run there.
        assert periodic_worker.text().count("noefforts.execute_attempt[") == 2
    finally:
        periodic_worker.stop()
    assert receiver.ledger()["accepted"] == 1 and claims(aid) == 1
    assert queued(broker()) == {"celery": 0, "attempts": 0}


def test_a_message_is_passed_on_once_at_most(api, receiver):
    """One already passed on is run wherever it arrives: a broker that named the queue
    differently could cost a hop, never a loop and never a lost attempt."""
    from app.worker import DEFAULT_QUEUE, celery_app

    aid = queue(api, prepared_application(api, receiver))
    assert svc.relay_outbox(lambda topic, attempt_id: None) == 1  # dispatched by hand below
    celery_app.send_task(
        "noefforts.execute_attempt", args=[aid], kwargs={"forwarded": True}, queue=DEFAULT_QUEUE
    )
    w = Worker(queues="celery", concurrency=1)
    try:
        assert wait_state(aid, ENDED) == "confirmed"
        w.wait_log("'confirmed'", 30)
    finally:
        w.stop()
    assert "'forwarded'" not in w.text()
    assert receiver.ledger()["accepted"] == 1 and claims(aid) == 1
    assert queued(broker()) == {"celery": 0, "attempts": 0}


def test_a_message_passed_on_is_marked_as_passed_on(monkeypatch):
    """The mark is what stops a second hop (the test above): it is set when a message is passed
    on, and only then."""
    from app import worker

    sent = []
    monkeypatch.setattr(worker, "publish", lambda *a, **kw: sent.append((a, kw)))
    task = worker.execute_attempt
    task.push_request(delivery_info={"exchange": "celery", "routing_key": "celery"})
    try:
        assert task.run("an-attempt-id") == "forwarded"
    finally:
        task.pop_request()
    assert sent == [(("execute_attempt", "an-attempt-id"), {"forwarded": True})]


def test_a_task_called_directly_is_run():
    """No delivery, so no queue to judge it by (the Compose harness and a shell call it so)."""
    from app.worker import execute_attempt

    assert execute_attempt(str(uuid.uuid4())) == "ignored"
    assert execute_attempt.apply(args=[str(uuid.uuid4())]).get() == "ignored"


# ------------------------------------------------------------ the attempt worker's own host


def _dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def test_an_attempts_worker_removes_its_own_hosts_stale_browser_directories(tmp_path, monkeypatch):
    """A hard-killed worker's browser directory. The sweeper removes those too, but it may run
    on another host, where it cannot see them: the attempts' worker cleans up before each run.
    A live process's directory is never touched. (A temporary directory of the test's own: the
    machine's is shared with every other run's workers, whose cleanup would race this one.)"""
    from app.worker import execute_attempt

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    base = tempfile.gettempdir()
    assert base == str(tmp_path)
    stale = os.path.join(base, f"{WORKDIR_PREFIX}{_dead_pid()}-stale")
    live = os.path.join(base, f"{WORKDIR_PREFIX}{os.getpid()}-live")
    os.mkdir(stale)
    os.mkdir(live)
    try:
        assert execute_attempt(str(uuid.uuid4())) == "ignored"
        assert not os.path.exists(stale) and os.path.isdir(live)
    finally:
        for d in (stale, live):
            if os.path.isdir(d):
                os.rmdir(d)


def test_a_cleanup_that_fails_does_not_stop_the_attempt(monkeypatch, caplog):
    """Housekeeping never decides whether an application runs. Were the task to fail before
    the claim, its message would be acknowledged with the attempt never claimed, and nothing
    would take it up again. The failure is logged by its type only (its text names a path)."""
    from app import worker
    from app.modules.execution import browser, runner

    def broken():
        raise PermissionError("[Errno 13] Permission denied: '/tmp/ne-browser-123-secret'")

    ran = []
    monkeypatch.setattr(browser, "cleanup_stale_workdirs", broken)
    monkeypatch.setattr(runner, "run_attempt", lambda aid, who: ran.append(aid) or "ran")
    aid = str(uuid.uuid4())
    with caplog.at_level("WARNING", logger="noefforts.worker"):
        assert worker.execute_attempt(aid) == "ran"
    assert ran == [aid]
    assert "PermissionError" in caplog.text and "ne-browser-123" not in caplog.text


def test_a_directory_that_vanishes_under_the_cleanup_is_not_an_error(tmp_path, monkeypatch):
    """Two cleanups can now run at once on one host (the sweeper's, an attempt's), and an
    attempt removes its own directory when it ends. One that is gone between the cleanup's two
    looks at it is skipped; the others are still handled."""
    from app.modules.execution import browser

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    vanishing = tmp_path / f"{WORKDIR_PREFIX}{_dead_pid()}-vanishing"
    stale = tmp_path / f"{WORKDIR_PREFIX}{_dead_pid()}-stale"
    vanishing.mkdir()
    stale.mkdir()
    real_isdir = os.path.isdir

    def isdir(path):
        if str(path) == str(vanishing) and vanishing.exists():
            vanishing.rmdir()  # a directory at this look, gone before the next
            return True
        return real_isdir(path)

    monkeypatch.setattr(browser.os.path, "isdir", isdir)
    assert browser.cleanup_stale_workdirs() == 1
    assert not stale.exists() and not vanishing.exists()


# ------------------------------------------------------------------- the deployment's check


def _ping(*nodes: str) -> subprocess.CompletedProcess:
    """scripts/smoke_lib.sh's check, with the real `inspect ping` of this run's broker."""
    ping = f"{sys.executable} -m celery -A app.worker inspect ping --timeout 3"
    lib = ROOT / "scripts" / "smoke_lib.sh"
    script = f"source '{lib}'; WORKER_PING_SLEEP=1; wait_worker_ping 6 {' '.join(nodes)}"
    env = os.environ | {"WORKER_PING": ping, "PYTHONPATH": str(BACKEND)}
    return subprocess.run(["bash", "-c", script], cwd=BACKEND, env=env, capture_output=True,
                          text=True, timeout=120)  # fmt: skip


def test_the_smoke_check_needs_both_named_workers_to_answer():
    """The Compose file names the two workers `attempts@host` and `scheduler@host`; the smoke
    test's ping passes only when both answered, read from Celery's real reply."""
    attempts_worker = Worker(queues="attempts", concurrency=1, node="attempts")
    try:
        one = _ping("attempts", "scheduler")
        assert one.returncode == 1 and "attempts@" in one.stdout, one.stdout + one.stderr
        scheduler = Worker(queues="celery", concurrency=1, node="scheduler")
        try:
            both = _ping("attempts", "scheduler")
            assert both.returncode == 0, both.stdout + both.stderr
            assert "attempts@" in both.stdout and "scheduler@" in both.stdout
        finally:
            scheduler.stop()
    finally:
        attempts_worker.stop()
