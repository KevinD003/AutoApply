"""Celery worker. Durable state lives in PostgreSQL; Redis only carries task messages.

Phase A ships the worker process and a housekeeping task. Application execution tasks are
added in Phase C behind the execution-provider contract.
"""

from celery import Celery
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow

settings = get_settings()
celery_app = Celery("noefforts", broker=settings.redis_url, backend=None)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    beat_schedule={
        "purge-expired-sessions": {"task": "noefforts.purge_expired_sessions", "schedule": 3600.0}
    },
)


@celery_app.task(name="noefforts.purge_expired_sessions")
def purge_expired_sessions() -> int:
    from app.modules.identity.models import UserSession

    with SessionLocal() as db:
        n = db.execute(delete(UserSession).where(UserSession.expires_at < utcnow())).rowcount
        db.commit()
        return n
