"""D168: the owner's console (app/modules/debug/service.py): read only, scoped to the signed-in
account, and app-only, as the inbox and account pages are: never reachable by an API token."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import not_found
from app.modules.debug import service
from app.modules.identity.deps import current_user, session_only
from app.modules.identity.models import User

router = APIRouter(prefix="/debug", tags=["debug"], dependencies=[Depends(session_only)])


@router.get("/system")
def get_system(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return service.system(db, user)


@router.get("/activity")
def get_activity(
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"items": service.activity(db, user, limit)}


@router.get("/applications/{application_id}")
def get_trace(
    application_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    out = service.trace(db, user, application_id)
    if out is None:  # another account's, or none: the same 404 as everywhere
        raise not_found("Application")
    return out
