"""D101: your Gmail, read-only, for verification codes and application emails (service.py)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import conflict, not_found
from app.modules.applications.states import Refused
from app.modules.audit.service import record
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.inbox import service
from app.modules.inbox.models import InboxEvent

router = APIRouter(prefix="/inbox", tags=["inbox"])

WHY = {
    "not_enabled": "Reading your email is switched off on this server.",
    "not_for_this_account": "Reading email is set up for the server owner's account only.",
    "not_connected": "No Gmail account is connected on this server yet.",
}
ERRORS = {
    "not_configured": "No Gmail account is connected.",
    "token_unreadable": "The saved Gmail connection could not be read. Connect again.",
    "revoked": "Gmail refused the connection (it may have been removed). Connect again.",
    "unreachable": "Gmail could not be reached. NoEfforts tries again later.",
    "refused_host": "The configured Gmail address is not allowed.",
    "bad_reply": "Gmail answered in an unexpected way. NoEfforts tries again later.",
}


class InboxSettingsIn(BaseModel):
    codes_enabled: bool
    tracking_enabled: bool


def _view(db: Session, user: User) -> dict:
    st = service.settings_of(db, user.id)
    why = service.available_for(user)
    events = db.scalars(
        select(InboxEvent)
        .where(InboxEvent.user_id == user.id)
        .order_by(InboxEvent.received_at.desc())
        .limit(50)
    ).all()
    return {
        "available": why is None,
        "why_not": WHY.get(why) if why else None,
        "codes_enabled": st.codes_enabled,
        "tracking_enabled": st.tracking_enabled,
        "last_checked_at": st.last_checked_at,
        "last_error": ERRORS.get(st.last_error) if st.last_error else None,
        "events": [
            {
                "id": str(e.id),
                "received_at": e.received_at,
                "sender_domain": e.sender_domain,
                "kind": e.kind,
                "state": e.state,
                "application_id": str(e.application_id) if e.application_id else None,
            }
            for e in events
        ],  # fmt: skip
    }


@router.get("")
def get_inbox(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    out = _view(db, user)
    db.commit()  # the settings row, created on first view
    return out


@router.put("")
def put_inbox(
    body: InboxSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if service.available_for(user) and (body.codes_enabled or body.tracking_enabled):
        raise conflict(WHY[service.available_for(user)])
    st = service.settings_of(db, user.id)
    st.codes_enabled, st.tracking_enabled = body.codes_enabled, body.tracking_enabled
    record(db, user.id, "inbox.settings", "inbox", None, codes=body.codes_enabled,
           tracking=body.tracking_enabled)  # fmt: skip
    db.commit()
    return _view(db, user)


@router.post("/check")
def check_now(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    why = service.available_for(user)
    if why:
        raise conflict(WHY[why])
    result = service.check(db, user)
    db.commit()
    return {"result": result, **_view(db, user)}


@router.post("/events/{event_id}/accept")
def accept_event(
    event_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        e = service.accept(db, user, event_id)
    except service.Settled:
        db.rollback()
        raise conflict("This application's submission is already settled.") from None
    except Refused as r:
        db.rollback()
        raise conflict(str(r)) from None
    except ValueError:
        db.rollback()
        raise conflict("This email is not waiting for your answer.") from None
    if e is None:
        raise not_found("Email")
    db.commit()
    return _view(db, user)


@router.post("/events/{event_id}/dismiss")
def dismiss_event(
    event_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        e = service.dismiss(db, user, event_id)
    except ValueError:
        db.rollback()
        raise conflict("This email is not waiting for your answer.") from None
    if e is None:
        raise not_found("Email")
    db.commit()
    return _view(db, user)
