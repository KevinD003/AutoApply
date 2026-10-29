"""API tokens (priority D, D84): made, listed and revoked from the app only (a signed-in session
and its CSRF token; never with a token). `GET /token` lets a token read what it is itself."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.errors import not_found
from app.modules.apitokens import service
from app.modules.apitokens.models import ApiToken
from app.modules.audit.service import record
from app.modules.identity.deps import current_user, session_only
from app.modules.identity.models import User

router = APIRouter(tags=["api tokens"])


class TokenIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=len(service.SCOPES))
    expires_in_days: int = Field(default=service.DEFAULT_DAYS, ge=1, le=service.MAX_DAYS)


class TokenOut(BaseModel):
    id: uuid.UUID
    public_id: str
    label: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    state: str


def _out(row: ApiToken) -> TokenOut:
    return TokenOut(
        id=row.id,
        public_id=row.public_id,
        label=row.label,
        scopes=row.scopes,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        state=service.state(row),
    )


@router.get("/account/tokens", dependencies=[Depends(session_only)])
def list_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return {"items": [_out(r) for r in rows], "scopes": sorted(service.SCOPES)}


@router.post(
    "/account/tokens", status_code=status.HTTP_201_CREATED, dependencies=[Depends(session_only)]
)
def create_token(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The token is in this response only: NoEfforts keeps its hash and cannot show it again."""
    try:
        row, token = service.create(db, user.id, body.label, body.scopes, body.expires_in_days)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    record(db, user.id, "api_token.create", "api_token", row.id, scopes=row.scopes,
           days=body.expires_in_days)  # fmt: skip
    db.commit()
    return {"token": token, "details": _out(row)}


@router.post("/account/tokens/{token_id}/revoke", dependencies=[Depends(session_only)])
def revoke_token(
    token_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TokenOut:
    row = db.scalar(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
        .with_for_update()
    )  # fmt: skip
    if row is None:
        raise not_found("Token")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        record(db, user.id, "api_token.revoke", "api_token", row.id)
        db.commit()
    return _out(row)


@router.get("/token")
def this_token(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What the calling token is: its scopes and expiry. A request without a token has none."""
    public_id = getattr(request.state, "api_token", None)
    if public_id is None:
        raise not_found("Token")
    row = db.scalar(
        select(ApiToken).where(ApiToken.public_id == public_id, ApiToken.user_id == user.id)
    )
    return {"public_id": row.public_id, "scopes": row.scopes, "expires_at": row.expires_at}
