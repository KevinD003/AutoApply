"""The user's explicit API authorizations (one provider, one destination origin, scope
"submit"). Granting one changes the route NoEfforts would use for that origin, so any approval
given for the browser route stops matching and is retired when queued (policy.check_binding)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.errors import bad_request, not_found
from app.core.urlsafety import is_fixture_origin
from app.modules.audit.service import record
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.providers import readiness, registry
from app.modules.providers.model import Kind
from app.modules.providers.models import ApiAuthorization

router = APIRouter(tags=["providers"])


class GrantIn(BaseModel):
    provider: str = Field(max_length=50)
    origin: str = Field(max_length=300)


def _out(a: ApiAuthorization) -> dict:
    return {"id": str(a.id), "provider": a.provider, "origin": a.origin, "scope": a.scope,
            "granted_at": a.granted_at.isoformat(),
            "revoked_at": a.revoked_at.isoformat() if a.revoked_at else None}  # fmt: skip


@router.get("/providers")
def providers(user: User = Depends(current_user)) -> dict:
    return registry.summary()


@router.get("/providers/greenhouse_dom/readiness")
def greenhouse_readiness(user: User = Depends(current_user)) -> dict:
    """Whether a live filling pilot could be proposed (providers/readiness.py): each condition
    derived from recorded evidence. Holds no user data; approves and enables nothing."""
    return readiness.summary()


@router.get("/api-authorizations")
def list_grants(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ApiAuthorization).where(ApiAuthorization.user_id == user.id))
    return [_out(a) for a in rows]


@router.post("/api-authorizations", status_code=201)
def grant(body: GrantIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    spec = registry.PROVIDERS.get(body.provider)
    if spec is None or spec.kind != Kind.api:
        raise bad_request("Unknown API provider")
    origin = body.origin.strip().rstrip("/").lower()
    if not is_fixture_origin(origin):
        raise bad_request("API submission is only available for local test fixtures")
    a = ApiAuthorization(
        id=uuid.uuid4(),
        user_id=user.id,
        provider=spec.name,
        origin=origin,
        scope="submit",
        granted_at=utcnow(),
    )
    db.add(a)
    record(db, user.id, "api_authorization.grant", "api_authorization", a.id,
           provider=spec.name)  # fmt: skip
    db.commit()
    return _out(a)


@router.delete("/api-authorizations/{grant_id}")
def revoke(grant_id: uuid.UUID, user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict:  # fmt: skip
    a = db.get(ApiAuthorization, grant_id)
    if a is None or a.user_id != user.id:
        raise not_found("Authorization")
    if a.revoked_at is None:
        a.revoked_at = utcnow()
        record(db, user.id, "api_authorization.revoke", "api_authorization", a.id)
        db.commit()
    return _out(a)
