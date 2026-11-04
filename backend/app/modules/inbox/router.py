"""D101: your Gmail, read-only, for verification codes and application emails (service.py)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import conflict, not_found
from app.modules.applications.states import Refused
from app.modules.audit.service import record
from app.modules.identity.deps import current_user, session_only
from app.modules.identity.models import User
from app.modules.inbox import service
from app.modules.inbox.models import InboxEvent

# The whole inbox feature reads the owner's own private mailbox: it is app-only, never reachable
# by an API token (no token scope includes any inbox route, and recording consent, like account
# export/deletion and token management, stays behind a signed-in session and its CSRF token).
router = APIRouter(prefix="/inbox", tags=["inbox"], dependencies=[Depends(session_only)])

WHY = {
    "not_enabled": "Reading your email is switched off on this server.",
    "not_for_this_account": "Reading email is set up for the server owner's account only.",
    "not_connected": "No Gmail account is connected on this server yet.",
    "not_authorized": "Reading your email needs the server owner's explicit, recorded "
    "authorization; switching it on is not one. Codes you type yourself are unaffected.",
}
ERRORS = {
    "not_configured": "No Gmail account is connected.",
    "token_unreadable": "The saved Gmail connection could not be read. Connect again.",
    "revoked": "Gmail refused the connection (it may have been removed). Connect again.",
    "unreachable": "Gmail could not be reached. NoEfforts tries again later.",
    "refused_host": "The configured Gmail address is not allowed.",
    "bad_reply": "Gmail answered in an unexpected way. NoEfforts tries again later.",
    "too_many": "There was a lot of mail to read at once; NoEfforts read the newest and will "
    "continue. Lower the first-read window if this persists.",
}

# The honest OAuth scope (spec §7): the owner's token was granted Gmail's read-only scope, which
# can read message bodies — broader than the metadata NoEfforts actually uses. App-side filters do
# not narrow the provider-issued scope; narrowing it, or revoking, is done in the Google account.
SCOPE_NOTE = (
    "NoEfforts uses read-only Gmail access. That read-only access can read message "
    "bodies — broader than what NoEfforts reads, which is only enough to recognise recruitment "
    "emails. It never sends, replies, deletes, marks read or changes labels, and stores no "
    "message content (only a keyed reference, the sender's domain, the recognised event and the "
    "application). This filter is in NoEfforts, not in the Google permission; manage or revoke "
    "access in your Google account's Security settings."
)
# Plain-language reasons a message was matched to an application (spec §9). Codes only; no content.
BASIS_LABEL = {
    "requisition_id": "the requisition ID in the message",
    "email_thread": "an earlier message in the same email thread",
    "employer": "the employer's name",
    "employer_domain": "the sender's own company domain",
    "job_title": "the job title",
    "ats_sender": "a known application-system sender",
}


class InboxSettingsIn(BaseModel):
    codes_enabled: bool
    tracking_enabled: bool
    # Suggest updates only (default), or automatically apply clear, well-matched updates (spec §4).
    auto_apply: bool = False


class AcceptIn(BaseModel):
    # An optional corrected outcome (e.g. the message read as an interview but you mark it
    # rejected). Omitted: the recognised event's outcome is used.
    outcome: str | None = None


class RelinkIn(BaseModel):
    # The application this message is really about ("wrong application"), or null to clear it.
    application_id: uuid.UUID | None = None


class AuthorizeIn(BaseModel):
    # Your own words authorizing NoEfforts to read your recruitment emails; kept verbatim as the
    # consent record. An optional last day the consent holds (null: no end date).
    attestation: str
    ends_on: date | None = None


def _why_matched(basis: str | None) -> str | None:
    if not basis:
        return None
    return ", ".join(BASIS_LABEL.get(b, b) for b in basis.split(","))


def _view(db: Session, user: User) -> dict:
    st = service.settings_of(db, user.id)
    why = service.available_for(db, user)
    events = db.scalars(
        select(InboxEvent)
        .where(InboxEvent.user_id == user.id)
        .order_by(InboxEvent.received_at.desc())
        .limit(50)
    ).all()
    # How application-email tracking is authorized, if it is: "recorded" (the reviewed-source
    # register, server-wide, not revocable here) or "in_app" (the owner's own authenticated,
    # revocable consent). None means it is not authorized, so the tracking toggle stays disabled.
    authz = None
    if service.may(service.APPLICATION_EMAIL):
        authz = {"source": "recorded"}
    elif (c := service.active_application_consent(db, user)) is not None:
        authz = {
            "source": "in_app",
            "granted_at": c.granted_at,
            "ends_on": c.ends_on,
            "attestation": c.attestation,
            "disclosure_version": c.disclosure_version,
        }
    return {
        "available": why is None,
        "why_not": WHY.get(why) if why else None,
        "codes_enabled": st.codes_enabled,
        "tracking_enabled": st.tracking_enabled,
        "auto_apply": st.auto_apply,
        "tracking_authorized": service.may_read_applications(db, user),
        "is_inbox_owner": service.is_inbox_owner(user),
        "authorization": authz,
        "scope_note": SCOPE_NOTE,
        # The bounded start of reading: the first read reaches back this many days and no further;
        # after that only newly arrived mail is read (spec §8). Set server-side at deploy.
        "first_read_days": get_settings().inbox_first_read_days,
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
                # The recognised event and its two confidences kept apart (spec); the proposed and
                # previous application outcome; a plain-language reason it matched. No content.
                "match_band": e.match_band,
                "class_band": e.class_band,
                "proposed_outcome": e.proposed_outcome,
                "prev_outcome": e.prev_outcome,
                "why_matched": _why_matched(e.match_basis),
                "automatic": e.state == "auto_applied",
                "needs_review": e.state in ("proposed", "review"),
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
    why = service.available_for(db, user)
    if why and (body.codes_enabled or body.tracking_enabled):
        raise conflict(WHY[why])
    # D103: each use needs its own recorded authorization; one never stands in for the other.
    if (body.codes_enabled and not service.codes_authorized()) or (
        body.tracking_enabled and not service.may_read_applications(db, user)
    ):
        raise conflict(WHY["not_authorized"])
    st = service.settings_of(db, user.id)
    st.codes_enabled, st.tracking_enabled = body.codes_enabled, body.tracking_enabled
    st.auto_apply = body.auto_apply  # inert unless tracking is on and authorized
    record(db, user.id, "inbox.settings", "inbox", None, codes=body.codes_enabled,
           tracking=body.tracking_enabled, auto_apply=body.auto_apply)  # fmt: skip
    db.commit()
    return _view(db, user)


@router.post("/authorize")
def authorize_tracking(
    body: AuthorizeIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Record your own authenticated consent to read your recruitment emails — no code change, and
    only the inbox owner may. It covers reading application emails alone (never verification codes,
    sending or submission), is scoped to your own mailbox, and you can revoke it here any time."""
    try:
        service.grant_application_consent(db, user, body.attestation, body.ends_on)
    except PermissionError:
        db.rollback()
        raise conflict(WHY["not_for_this_account"]) from None
    except ValueError:
        db.rollback()
        raise conflict("Type your consent, in your own words, to authorize this.") from None
    db.commit()
    return _view(db, user)


@router.post("/authorize/revoke")
def revoke_tracking(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Withdraw your in-app consent to read application emails; reading is gated again at once.
    (Disconnecting the Gmail token and removing NoEfforts in your Google account are separate,
    stronger steps — see the scope note.)"""
    try:
        service.revoke_application_consent(db, user)
    except PermissionError:
        db.rollback()
        raise conflict(WHY["not_for_this_account"]) from None
    db.commit()
    return _view(db, user)


@router.post("/check")
def check_now(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    why = service.available_for(db, user)
    if why or not service.may_read_applications(db, user):
        raise conflict(WHY[why or "not_authorized"])
    result = service.check(db, user)
    db.commit()
    return {"result": result, **_view(db, user)}


@router.post("/events/{event_id}/accept")
def accept_event(
    event_id: uuid.UUID,
    body: AcceptIn | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        e = service.accept(db, user, event_id, outcome=body.outcome if body else None)
    except service.Settled:
        db.rollback()
        raise conflict("This application's submission is already settled.") from None
    except Refused as r:
        db.rollback()
        raise conflict(str(r)) from None
    except ValueError:
        db.rollback()
        raise conflict("This email is not waiting for your answer, or names no outcome.") from None
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


@router.post("/events/{event_id}/undo")
def undo_event(
    event_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        e = service.undo(db, user, event_id)
    except ValueError as v:
        db.rollback()
        msg = {
            "terminal": "A confirmed receipt can't be undone.",
            "not_undoable": "This email hasn't been applied, so there's nothing to undo.",
            "superseded": "A newer update has changed this application since; undo that one first.",
        }.get(str(v), "This email can't be undone.")
        raise conflict(msg) from None
    if e is None:
        raise not_found("Email")
    db.commit()
    return _view(db, user)


@router.post("/events/{event_id}/relink")
def relink_event(
    event_id: uuid.UUID,
    body: RelinkIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        e = service.relink(db, user, event_id, body.application_id)
    except LookupError:
        db.rollback()
        raise not_found("Application") from None
    except ValueError:
        db.rollback()
        raise conflict("Undo this email before linking it to a different application.") from None
    if e is None:
        raise not_found("Email")
    db.commit()
    return _view(db, user)
