"""Follow-ups (D92): when to check on an application you submitted, and a message to copy.
Each route acts on the signed-in account only; another account's application is 404. Nothing is
sent: no email, text message or push."""

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import not_found
from app.modules.applications.models import Application
from app.modules.audit.service import record
from app.modules.followups import service
from app.modules.followups.models import FollowUp
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(tags=["follow-ups"])

# Why a change is refused, shown after the message ("(reason: code)").
REASONS = {
    "not_submitted": "There is nothing to follow up yet: this application has not been submitted",
    "outcome_closed": "The outcome you recorded closes this application, so there is nothing to "
    "follow up",
    "remind_on_required": "Choose the day to be reminded on",
    "remind_on_range": "Choose a day from today to a year ahead",
}


def _refuse(code: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f"{REASONS[code]} (reason: {code})")


class FollowUpAction(BaseModel):
    action: Literal["done", "remind", "stop", "resume"]
    remind_on: date | None = None


def _owned(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise not_found("Application")
    return app


@router.get("/follow-ups")
def list_follow_ups(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    items = service.for_user(db, user.id)
    return {
        "items": items,
        "due": sum(1 for i in items if i["status"] == "due"),
        "days": get_settings().follow_up_days,
    }


@router.get("/applications/{app_id}/follow-up")
def get_follow_up(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned(db, user, app_id)
    item = service.for_application(db, app)
    if item is None:
        return {"status": "not_submitted", "draft": None}
    return item | {"draft": service.draft(db, app, item)}


@router.post("/applications/{app_id}/follow-up")
def change_follow_up(
    app_id: uuid.UUID,
    body: FollowUpAction,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned(db, user, app_id)
    item = service.for_application(db, app)
    if item is None:
        raise _refuse("not_submitted")
    if item["status"] == "closed" and body.action in ("done", "remind", "resume"):
        raise _refuse("outcome_closed")
    now = service.today()
    if body.action == "remind":
        if body.remind_on is None:
            raise _refuse("remind_on_required")
        if not now <= body.remind_on <= now + timedelta(days=service.MAX_REMIND_AHEAD_DAYS):
            raise _refuse("remind_on_range")
    db.execute(
        insert(FollowUp)
        .values(id=uuid.uuid4(), user_id=user.id, application_id=app.id, stopped=False)
        .on_conflict_do_nothing(constraint="uq_follow_up")
    )
    choice = db.scalar(
        select(FollowUp)
        .where(FollowUp.user_id == user.id, FollowUp.application_id == app.id)
        .with_for_update()
    )
    if body.action == "done":
        choice.followed_up_on, choice.remind_on = now, None
    elif body.action == "remind":
        choice.remind_on = body.remind_on
    else:
        choice.stopped = body.action == "stop"
    record(db, user.id, "follow_up.update", "application", app.id, change=body.action)
    db.commit()
    item = service.for_application(db, app)
    return item | {"draft": service.draft(db, app, item)}
