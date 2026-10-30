"""Your email reminders (D94): set and verify your address, choose what is emailed, turn it on
or off. Signed in to the app only (an API token is refused) and acting on your account only.
Nothing here emails anyone but you, and no route acts on an application."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.audit.service import record
from app.modules.identity.deps import current_user, session_only
from app.modules.identity.models import User
from app.modules.mail import service
from app.modules.mail.models import EmailDelivery

router = APIRouter(prefix="/account/email", tags=["email"], dependencies=[Depends(session_only)])

# Why a request is refused, shown after the message ("(reason: code)").
REASONS = {
    "email_not_configured": "Email is not set up on this NoEfforts (the owner's mail settings)",
    "email_config_incomplete": "Email is switched on but its server or sender is missing",
    "email_base_url_invalid": "Email is switched on but the link address is not valid",
    "email_tls_required": "Email in production needs STARTTLS to a mail server off this machine",
    "address_invalid": "That is not an email address NoEfforts can use",
    "address_domain": "Reminders may only go to the domains this NoEfforts allows",
    "address_missing": "Add your email address first",
    "address_unverified": "Verify your address with the code first",
    "code_limit": "Too many codes today; try again tomorrow",
    "code_missing": "Ask for a code first",
    "code_expired": "That code has expired; ask for a new one",
    "code_attempts": "Too many wrong codes; ask for a new one",
    "code_wrong": "That code is not right",
}
STATUS_FOR = {"code_wrong": status.HTTP_400_BAD_REQUEST}


def _refuse(e: service.Refused) -> HTTPException:
    code = STATUS_FOR.get(e.code, status.HTTP_409_CONFLICT)
    return HTTPException(code, f"{REASONS[e.code]} (reason: {e.code})")


class AddressIn(BaseModel):
    address: str = Field(max_length=254)


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


class PreferencesIn(BaseModel):
    attention: bool
    follow_ups: bool
    digest_hour_utc: int = Field(ge=0, le=23)


def _view(db: Session, user: User) -> dict:
    row = service.settings_for(db, user.id)
    recent = db.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.user_id == user.id)
        .order_by(EmailDelivery.created_at.desc())
        .limit(10)
    )
    return {
        "configured": service.config_problem() is None,
        "address": row.address if row else None,
        "verified": bool(row and row.verified_at),
        "code_pending": bool(row and row.code_digest),
        "enabled": bool(row and row.enabled),
        "attention": row.attention if row else True,
        "follow_ups": row.follow_ups if row else True,
        "digest_hour_utc": row.digest_hour_utc if row else 7,
        "recent": [
            {
                "kind": d.kind,
                "status": d.status,
                "outcome_code": d.outcome_code,
                "item_count": d.item_count,
                "created_at": d.created_at.isoformat(),
                "sent_at": d.sent_at.isoformat() if d.sent_at else None,
            }
            for d in recent
        ],
    }


def _done(db: Session, user: User, change: str) -> dict:
    row = service.settings_for(db, user.id)
    record(db, user.id, "email.update", "email_settings", row.id if row else None, change=change)
    db.commit()
    return _view(db, user)


@router.get("")
def get_email(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _view(db, user)


@router.put("/address")
def put_address(body: AddressIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:  # fmt: skip
    try:
        service.set_address(db, user.id, body.address)
    except service.Refused as e:
        raise _refuse(e) from None
    return _done(db, user, "address")


@router.post("/code")
def send_code(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Queues the code for your address; the worker sends it. Nothing else is queued here."""
    try:
        service.request_code(db, user.id)
    except service.Refused as e:
        raise _refuse(e) from None
    return _done(db, user, "code")


@router.post("/verify")
def verify(body: CodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        service.verify_code(db, user.id, body.code)
    except service.Refused as e:
        db.commit()  # a wrong code counts
        raise _refuse(e) from None
    return _done(db, user, "verify")


@router.put("/preferences")
def put_preferences(body: PreferencesIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> dict:  # fmt: skip
    service.set_preferences(db, user.id, attention=body.attention, follow_ups=body.follow_ups,
                            digest_hour_utc=body.digest_hour_utc)  # fmt: skip
    return _done(db, user, "preferences")


@router.post("/enable")
def enable(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        service.set_enabled(db, user.id, True)
    except service.Refused as e:
        raise _refuse(e) from None
    return _done(db, user, "enable")


@router.post("/disable")
def disable(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    service.set_enabled(db, user.id, False)
    return _done(db, user, "disable")


@router.delete("")
def remove(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = service.settings_for(db, user.id)
    record(db, user.id, "email.update", "email_settings", row.id if row else None, change="remove")
    service.remove(db, user.id)
    db.commit()
    return _view(db, user)
