"""D113: the owner's standing rule to apply automatically: its state, what it did, and the
owner's pause switch. Every query is scoped to the signed-in account."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authorizations
from app.core.config import get_settings
from app.core.db import get_db
from app.modules.autoapply import service
from app.modules.autoapply.models import AutoApplyEvent
from app.modules.execution import live
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job

router = APIRouter(prefix="/auto-apply", tags=["auto-apply"])

WHY = {"rule_off": "Automatic applying is switched off on this server."} | live.WHY


def _state(db: Session, user: User) -> dict:
    s = get_settings()
    refusal = service.owner_refusal(user)
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose")
    used = live.attempts_used(db, cap[1]) if cap is not None else None
    rows = db.execute(
        select(AutoApplyEvent, Job.title, Job.employer)
        .join(Job, Job.id == AutoApplyEvent.job_id)
        .where(AutoApplyEvent.user_id == user.id, Job.user_id == user.id)
        .order_by(AutoApplyEvent.created_at.desc())
        .limit(30)
    ).all()
    return {
        "rule": service.RULE,
        "active": refusal is None and not service.paused(db, user.id),
        "paused": service.paused(db, user.id),
        "unavailable": None if refusal is None else {"code": refusal, "message": WHY[refusal]},
        "daily_cap": s.auto_apply_daily_cap,
        "approved_today": service.approved_today(db, user.id),
        "permission_attempts": None if cap is None else {"used": used, "of": cap[0]},
        "events": [
            {
                "at": e.created_at,
                "job_id": str(e.job_id),
                "application_id": str(e.application_id) if e.application_id else None,
                "job": " — ".join(x for x in (title or "Untitled role", employer) if x),
                "action": e.action,
                "reason": e.reason,
                "text": service.REASONS.get(e.reason, e.reason),
            }
            for e, title, employer in rows
        ],
    }


@router.get("")
def get_state(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _state(db, user)


class PauseIn(BaseModel):
    paused: bool


@router.put("")
def set_state(
    body: PauseIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    service.set_paused(db, user.id, body.paused)
    db.commit()
    return _state(db, user)
