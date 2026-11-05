"""D128: Account -> Connections endpoints for the Gmail browser OAuth flow (connections/service).

App-only (session_only): the whole flow runs in the owner's signed-in browser; no API token can
start it, complete it or disconnect. `start` and `callback` are GETs because they are top-level
browser navigations (the system browser, not an embedded view); the single-use, account-bound
`state` is the request-forgery protection for the callback, and the callback redirects only to one
fixed in-app destination — never a value taken from the request (no open redirect).
"""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import conflict
from app.modules.connections import service
from app.modules.identity.deps import current_user, session_only
from app.modules.identity.models import User

router = APIRouter(
    prefix="/connections", tags=["connections"], dependencies=[Depends(session_only)]
)

WHY = {
    "not_enabled": "Connecting Gmail from the app is switched off on this server.",
    "not_configured": "This server has no Gmail web OAuth client configured yet.",
    "not_owner": "Connecting Gmail is set up for the server owner's account only.",
}


@router.get("")
def get_connections(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"gmail": service.status(db, user)}


@router.get("/gmail/start")
def start_gmail(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Begin the flow and send the owner's browser to Google's consent page."""
    try:
        url = service.start(db, user)
    except service.NotOwner:
        db.rollback()
        raise conflict(WHY["not_owner"]) from None
    except ValueError as v:
        db.rollback()
        raise conflict(WHY.get(str(v), WHY["not_enabled"])) from None
    db.commit()
    return RedirectResponse(url, status_code=302)


@router.get("/gmail/callback")
def gmail_callback(
    state: str = "",
    code: str = "",
    error: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Google returns the owner here. Validate, store on success, then redirect back into the app
    with a fixed result code the Connections page shows."""
    try:
        outcome = service.callback(db, user, state, code, error)
    except service.NotOwner:
        db.rollback()
        outcome = "not_owner"
    db.commit()
    return RedirectResponse(service.return_url(outcome), status_code=302)


@router.post("/gmail/disconnect")
def disconnect_gmail(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Remove this server's stored Google access for the owner (delete the token, mark revoked)."""
    try:
        service.disconnect(db, user)
    except service.NotOwner:
        db.rollback()
        raise conflict(WHY["not_owner"]) from None
    db.commit()
    return {"gmail": service.status(db, user)}
