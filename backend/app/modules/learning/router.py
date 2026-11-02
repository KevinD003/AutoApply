"""D115: the answer brain's suggestions for an application, your verdicts on them, and the state
of your own model. Every query is scoped to the signed-in account; another account's application
is a 404. A question's key travels in the request body, never in the path (A8)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import conflict
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.learning import service
from app.modules.preparation.router import QuestionKey, _owned_app

router = APIRouter(tags=["answer-brain"])

GONE = "This suggestion no longer applies (the question was answered or changed). Reload it."


class VerdictIn(BaseModel):
    key: QuestionKey
    bank_entry_id: uuid.UUID


def _public(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in ("features", "question_key")}


@router.get("/applications/{app_id}/suggestions")
def get_suggestions(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    items = [_public(s) for s in service.suggestions(db, user, app)]
    return {"brain": service.status(db, user), "suggestions": items}


@router.post("/applications/{app_id}/suggestions/accept")
def accept_suggestion(
    app_id: uuid.UUID,
    body: VerdictIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        return service.accept(db, user, app, body.key, body.bank_entry_id)
    except service.NoSuggestion:
        raise conflict(GONE) from None


@router.post("/applications/{app_id}/suggestions/reject")
def reject_suggestion(
    app_id: uuid.UUID,
    body: VerdictIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        service.reject(db, user, app, body.key, body.bank_entry_id)
    except service.NoSuggestion:
        raise conflict(GONE) from None
    items = [_public(s) for s in service.suggestions(db, user, app)]
    return {"brain": service.status(db, user), "suggestions": items}


@router.get("/answer-brain")
def brain_status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return service.status(db, user)


@router.delete("/answer-brain")
def brain_forget(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    service.forget(db, user)
    return service.status(db, user)
