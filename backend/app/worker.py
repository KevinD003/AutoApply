"""Celery worker. Durable state lives in PostgreSQL; Redis only carries attempt ids.

Delivery settings (Celery 5.6.3, kombu 5.6.2, Redis transport, prefork pool):
  task_acks_late=True              ack after the task returns, so a crash mid-task does not
                                   silently drop a delivery that never started work;
  task_reject_on_worker_lost=False if the worker *process* dies, the message is acknowledged,
                                   not redelivered. Recovery is the sweeper's job, driven by
                                   database leases, so a killed worker never causes Celery to
                                   re-run a task that may have reached the submit click;
  worker_prefetch_multiplier=1     one reserved task per process;
  visibility_timeout=3600          Redis redelivers unacknowledged messages after an hour
                                   (NOEFFORTS_BROKER_VISIBILITY_TIMEOUT_SECONDS; tests only
                                   shorten it on a disposable broker);
  publish retry: 2 quick retries   then the relay leaves the outbox row for the next tick;
  soft/hard time limits            240s / 300s for every task but an attempt's, the soft
                                   one set on each task (SOFT_LIMIT). An attempt's task
                                   has one limit of its own and no soft limit (D143;
                                   config: attempt_time_limit_seconds): its run budget,
                                   the waits after the click and the whole wait for a
                                   verification code, so a code typed late in its wait is
                                   never cut off. It stays under the visibility timeout,
                                   or a still-running task's message would be redelivered
                                   (harmless: the claim refuses it).
None of these settings makes an external submission idempotent. Duplicate deliveries are made
harmless by the claim compare-and-swap; sends are never repeated by the queue (see
app/modules/execution/service.py).

Queues (D144). An attempt's task goes to a queue of its own (ATTEMPT_QUEUE); every other task,
all of them periodic, goes to the default queue. An attempt may hold its process for the
whole wait for a verification code (D143), so a deployment runs two workers: one that takes
only attempts, with one process per browser slot, and one that runs the schedule and the
periodic tasks (docker-compose.yml: `worker` and `scheduler`). The sweeper, the outbox relay
and the mailbox reader then never wait behind an attempt. A worker started without `-Q` takes
both queues (local development, tests): it works, with no such separation. An attempt's task
is run from its own queue: a message for it that arrives on any other queue (one published
before this routing existed) is passed on to ATTEMPT_QUEUE, once, instead of being run there.
"""

import logging
import socket
import uuid

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from kombu import Exchange, Queue
from sqlalchemy import delete

import app.models  # noqa: F401  (register every table before any task runs)
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.log_safety import install_worker_filters
from app.modules.identity.models import UserSession

settings = get_settings()
log = logging.getLogger("noefforts.worker")
DEFAULT_QUEUE = "celery"  # the schedule's tasks (Celery's own default name, kept)
ATTEMPT_QUEUE = "attempts"  # D144: noefforts.execute_attempt, and nothing else
celery_app = Celery("noefforts", broker=settings.redis_url, backend=None)
celery_app.conf.update(
    # D144: both queues are declared, so a worker started without -Q takes both; a deployment
    # gives each queue its own worker (see the module docstring). Each queue has an exchange
    # and routing key of its own name, as a queue Celery creates itself has. Declared by name
    # only, both would be bound to the default exchange under one key: Celery's own publishing
    # addresses a queue directly and would not notice, but a message published to that
    # exchange and key would reach both queues (measured).
    task_default_queue=DEFAULT_QUEUE,
    task_queues=tuple(
        Queue(name, Exchange(name, type="direct"), routing_key=name)
        for name in (DEFAULT_QUEUE, ATTEMPT_QUEUE)
    ),
    task_routes={"noefforts.execute_attempt": {"queue": ATTEMPT_QUEUE}},
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,
    # D143: no soft limit by default; every task but an attempt's sets SOFT_LIMIT itself (the
    # pool arms a soft limit first whenever a task has one, and the attempt's must have none).
    task_time_limit=300,
    broker_transport_options={"visibility_timeout": settings.broker_visibility_timeout_seconds},
    # Publishing gives up quickly when the broker is down; the outbox row stays undispatched
    # and the next relay tick tries again. Nothing is lost, nothing blocks.
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 1,
    },
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "purge-expired-sessions": {"task": "noefforts.purge_expired_sessions", "schedule": 3600.0},
        "relay-outbox": {
            "task": "noefforts.relay_outbox",
            "schedule": settings.outbox_relay_interval_seconds,
        },
        "sweep-attempts": {"task": "noefforts.sweep_attempts", "schedule": 15.0},
        "purge-expired-evidence": {"task": "noefforts.purge_expired_evidence", "schedule": 86400.0},
        # D56: watched Freehire searches; does nothing unless Freehire is an enabled provider.
        "check-discovery-watches": {"task": "noefforts.check_discovery_watches", "schedule": 10.0},
        # D96: boards whose owners chose a daily check; nothing unless job boards are enabled.
        "check-board-sources": {"task": "noefforts.check_board_sources", "schedule": 300.0},
        # D101: the owner's Gmail, read-only; does nothing unless the owner connected it and
        # turned on codes or application emails.
        "check-inbox": {"task": "noefforts.check_inbox", "schedule": 15.0},
        # D113: the owner's standing rule to apply automatically; does nothing unless it is on
        # and the Greenhouse pilot may act on this server (autoapply/service.py).
        "auto-apply": {
            "task": "noefforts.auto_apply",
            "schedule": float(settings.auto_apply_interval_seconds),
        },
        # D94: owner email reminders; does nothing unless the owner configured email.
        "email-tick": {
            "task": "noefforts.email_tick",
            "schedule": settings.email_dispatch_interval_seconds,
        },
    },
)

# A failed task is logged with its exception's type only: no message, no traceback (a database
# error's text can quote a row). Installed now and again after Celery configures its logging.
install_worker_filters()
after_setup_logger.connect(lambda **_: install_worker_filters(), weak=False)
after_setup_task_logger.connect(lambda **_: install_worker_filters(), weak=False)

WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def publish(topic: str, attempt_id: str, **kwargs) -> None:
    """To the attempts' queue: the task's route (task_routes) decides, here as everywhere."""
    if topic != "execute_attempt":
        raise ValueError(f"unknown topic {topic}")
    celery_app.send_task("noefforts.execute_attempt", args=[attempt_id], kwargs=kwargs)


SOFT_LIMIT = 240  # seconds; every task but an attempt's


# D143: an attempt's task has one time limit and no soft limit. A soft limit raises inside the
# running task from a signal handler; measured with a real worker, one that lands inside a
# browser wait leaves the browser unable to close, so the runner's own handler never runs and
# the process hangs until the hard limit anyway. The run's time is bounded by the runner
# itself, between steps (attempt_run_budget_seconds); at this limit the worker process is
# ended, the message is acknowledged (never redelivered), and the sweeper decides from the
# attempt's phase.
@celery_app.task(
    name="noefforts.execute_attempt", bind=True, time_limit=settings.attempt_time_limit_seconds
)
def execute_attempt(self, attempt_id: str, forwarded: bool = False) -> str:
    # D144: only ever run from the attempts' own queue. A message that arrived on another one
    # (published before the routing existed, or by anything that names the wrong queue) is
    # passed on and acknowledged: nothing was claimed, and the claim ignores a duplicate. It
    # is passed on once: a message already passed on is run wherever it arrives, so a broker
    # that reported the queue differently could cost a hop but never a loop or a lost attempt.
    arrived_on = (self.request.delivery_info or {}).get("routing_key")
    if arrived_on not in (None, ATTEMPT_QUEUE) and not forwarded:
        publish("execute_attempt", attempt_id, forwarded=True)
        return "forwarded"
    from app.modules.execution.browser import cleanup_stale_workdirs
    from app.modules.execution.runner import run_attempt

    # D144: this host's own leftovers (a hard-killed worker's browser directories; they exist
    # only where the browser runs inside the worker, `browser_isolation=netns`). The sweeper
    # removes them too, but it may now run on another host, where it cannot see them. It never
    # decides whether the attempt runs: a task that failed here would be acknowledged with the
    # attempt never claimed, and nothing would take it up again.
    try:
        cleanup_stale_workdirs()
    except Exception as e:  # noqa: BLE001
        log.warning("stale browser directories not removed (%s)", type(e).__name__)
    return run_attempt(attempt_id, f"{WORKER_ID}-{uuid.uuid4().hex[:6]}")


@celery_app.task(name="noefforts.relay_outbox", soft_time_limit=SOFT_LIMIT)
def relay_outbox() -> int:
    from app.modules.execution.service import relay_outbox as relay

    return relay(publish)


@celery_app.task(name="noefforts.sweep_attempts", soft_time_limit=SOFT_LIMIT)
def sweep_attempts() -> dict:
    from app.modules.execution.browser import cleanup_stale_workdirs
    from app.modules.execution.service import sweep

    out = sweep()
    out["stale_workdirs_removed"] = cleanup_stale_workdirs()  # this host's crashed workers
    return out


@celery_app.task(name="noefforts.check_discovery_watches", soft_time_limit=SOFT_LIMIT)
def check_discovery_watches() -> int:
    from app.modules.discovery.service import check_due_watches

    return check_due_watches()


@celery_app.task(name="noefforts.check_board_sources", soft_time_limit=SOFT_LIMIT)
def check_board_sources() -> int:
    from app.modules.discovery.board_sync import check_due

    return check_due()


@celery_app.task(name="noefforts.check_inbox", soft_time_limit=SOFT_LIMIT)
def check_inbox() -> dict:
    from app.modules.inbox.service import inbox_tick

    return inbox_tick()


@celery_app.task(name="noefforts.email_tick", soft_time_limit=SOFT_LIMIT)
def email_tick() -> dict:
    from app.modules.mail.service import tick

    return tick(WORKER_ID)


@celery_app.task(name="noefforts.purge_expired_sessions", soft_time_limit=SOFT_LIMIT)
def purge_expired_sessions() -> int:
    with SessionLocal() as db:
        n = db.execute(delete(UserSession).where(UserSession.expires_at < utcnow())).rowcount
        db.commit()
        return n


@celery_app.task(name="noefforts.purge_expired_evidence", soft_time_limit=SOFT_LIMIT)
def purge_expired_evidence() -> int:
    from app.modules.execution.service import purge_expired_evidence as purge

    return purge()


@celery_app.task(name="noefforts.auto_apply", soft_time_limit=SOFT_LIMIT)
def auto_apply() -> int:
    """D113: the owner's standing rule to apply automatically (autoapply/service.py)."""
    from app.modules.autoapply.service import tick

    return tick()
