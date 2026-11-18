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
from app.modules.autoapply.models import AutoApplyEvent, AutoApplyPrefs
from app.modules.execution import live
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job

router = APIRouter(prefix="/auto-apply", tags=["auto-apply"])

WHY = {
    "rule_off": "Automatic applying is switched off on this server.",
    # D170: the server allows no automatic approval a day.
    "no_daily_approvals": "This server allows no automatic approvals a day "
    "(NOEFFORTS_AUTO_APPLY_DAILY_CAP is 0).",
} | live.WHY


def _state(db: Session, user: User) -> dict:
    s = get_settings()
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose")
    # D170: what stops the rule, the recorded permission's attempts used up and no approval
    # allowed a day among it, as the pause's words ("the Tracker shows why") promise.
    refusal = service.owner_refusal(user) or service.limit_refusal(db)
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
        "active": refusal is None and not service.paused(db, user),
        "paused": service.paused(db, user),
        # D114: whether this account made its own choice (else the default applies: on for the
        # server owner, off for everyone else until they turn it on).
        "chosen": db.get(AutoApplyPrefs, user.id) is not None,
        "consent": service.CONSENT_TEXT,
        "unavailable": None
        if refusal is None
        else {"code": refusal, "message": WHY[refusal].format(n=cap[0] if cap else 0)},
        "daily_cap": s.auto_apply_daily_cap,
        # D168: in sole-owner mode the cap counts every account's approvals (cap_used).
        "approved_today": service.cap_used(db, user.id),
        "cap_every_account": s.sole_owner,
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
    stopped = service.set_paused(db, user.id, body.paused)
    db.commit()
    # D134: what pausing stopped of the rule's queued work (none when resuming).
    return _state(db, user) | ({"stopped": stopped} if stopped is not None else {})
