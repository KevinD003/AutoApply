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
  soft/hard time limits            240s / 300s per task.
None of these settings makes an external submission idempotent. Duplicate deliveries are made
harmless by the claim compare-and-swap; sends are never repeated by the queue (see
app/modules/execution/service.py).
"""

import socket
import uuid

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from sqlalchemy import delete

import app.models  # noqa: F401  (register every table before any task runs)
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.log_safety import install_worker_filters
from app.modules.identity.models import UserSession

settings = get_settings()
celery_app = Celery("noefforts", broker=settings.redis_url, backend=None)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=240,
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


def publish(topic: str, attempt_id: str) -> None:
    if topic != "execute_attempt":
        raise ValueError(f"unknown topic {topic}")
    celery_app.send_task("noefforts.execute_attempt", args=[attempt_id])


@celery_app.task(name="noefforts.execute_attempt")
def execute_attempt(attempt_id: str) -> str:
    from app.modules.execution.runner import run_attempt

    return run_attempt(attempt_id, f"{WORKER_ID}-{uuid.uuid4().hex[:6]}")


@celery_app.task(name="noefforts.relay_outbox")
def relay_outbox() -> int:
    from app.modules.execution.service import relay_outbox as relay

    return relay(publish)


@celery_app.task(name="noefforts.sweep_attempts")
def sweep_attempts() -> dict:
    from app.modules.execution.browser import cleanup_stale_workdirs
    from app.modules.execution.service import sweep

    out = sweep()
    out["stale_workdirs_removed"] = cleanup_stale_workdirs()  # this host's crashed workers
    return out


@celery_app.task(name="noefforts.check_discovery_watches")
def check_discovery_watches() -> int:
    from app.modules.discovery.service import check_due_watches

    return check_due_watches()


@celery_app.task(name="noefforts.check_board_sources")
def check_board_sources() -> int:
    from app.modules.discovery.board_sync import check_due

    return check_due()


@celery_app.task(name="noefforts.email_tick")
def email_tick() -> dict:
    from app.modules.mail.service import tick

    return tick(WORKER_ID)


@celery_app.task(name="noefforts.purge_expired_sessions")
def purge_expired_sessions() -> int:
    with SessionLocal() as db:
        n = db.execute(delete(UserSession).where(UserSession.expires_at < utcnow())).rowcount
        db.commit()
        return n


@celery_app.task(name="noefforts.purge_expired_evidence")
def purge_expired_evidence() -> int:
    from app.modules.execution.service import purge_expired_evidence as purge

    return purge()
