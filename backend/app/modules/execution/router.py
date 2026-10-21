import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.errors import bad_request, conflict, not_found
from app.modules.applications.models import Application
from app.modules.execution import service as svc
from app.modules.execution.models import AttemptEvent, Checkpoint, Evidence, ExecutionAttempt
from app.modules.execution.policy import CAPABILITIES
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.providers.registry import summary as provider_summary

router = APIRouter(tags=["execution"])


def _owned_app(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise not_found("Application")
    return app


@router.get("/execution/capabilities")
def capabilities(user: User = Depends(current_user)) -> dict:
    return {
        "adapters": CAPABILITIES,
        # Machine-readable provider model (providers.registry): per capability "none",
        # "fixture", "observed", "live_fill" or "live_submit".
        "providers": provider_summary(),
        "note": "Adapters run only against local synthetic fixtures (the Greenhouse one against "
        "a labelled approximation). No live employer system is supported for automatic "
        "submission.",
    }


@router.get("/applications/{app_id}/attempts")
def list_attempts(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[dict]:
    app = _owned_app(db, user, app_id)
    out = []
    for a in db.scalars(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.user_id == user.id)
        .order_by(ExecutionAttempt.created_at.desc())
    ):
        events = db.scalars(
            select(AttemptEvent)
            .where(AttemptEvent.attempt_id == a.id)
            .order_by(AttemptEvent.created_at)
        ).all()
        cps = db.scalars(
            select(Checkpoint).where(Checkpoint.attempt_id == a.id, Checkpoint.user_id == user.id)
        ).all()
        ev = db.scalars(
            select(Evidence).where(Evidence.attempt_id == a.id, Evidence.user_id == user.id)
        ).all()
        out.append(
            {
                "id": str(a.id),
                "state": a.state,
                "adapter": a.adapter,
                "package_hash": a.package_hash,
                "created_at": a.created_at,
                "disclosure_started_at": a.disclosure_started_at,
                "send_started_at": a.send_started_at,
                "finished_at": a.finished_at,
                "outcome": a.outcome_detail,
                "retry_count": a.retry_count,
                "events": [
                    {
                        "kind": e.kind,
                        "generation": e.generation,
                        "detail": e.detail,
                        "at": e.created_at,
                    }
                    for e in events
                ],
                "checkpoints": [
                    {
                        "id": str(c.id),
                        "status": c.status,
                        "round": c.round,
                        "message": c.message,
                        "expires_at": c.expires_at,
                        "wrong_attempts": c.wrong_attempts,
                        "max_attempts": c.max_attempts,
                    }
                    for c in cps
                ],
                "evidence": [
                    {
                        "kind": e.kind,
                        "strength": e.strength,
                        "data": e.data,
                        "at": e.created_at,
                        "retain_until": e.retain_until,
                    }
                    for e in ev
                ],
            }
        )
    return out


class CodeIn(BaseModel):
    round: int = Field(ge=1)
    code: str = Field(min_length=1, max_length=32)


@router.post(
    "/applications/{app_id}/checkpoints/{checkpoint_id}/code", status_code=status.HTTP_202_ACCEPTED
)
def submit_code(
    app_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    body: CodeIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        cp = svc.submit_code(db, user.id, app.id, checkpoint_id, body.round, body.code.strip())
    except LookupError:
        raise not_found("Checkpoint") from None
    except PermissionError as e:
        db.rollback()
        raise conflict(str(e)) from None
    except ValueError as e:
        raise bad_request(str(e)) from None
    db.commit()
    return {"status": cp.status, "round": cp.round, "received_at": utcnow()}


@router.post("/applications/{app_id}/cancel")
def cancel(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        svc.cancel(db, app)
    except PermissionError as e:
        db.rollback()
        raise conflict(str(e)) from None
    except Exception as e:  # IllegalTransition from a terminal state
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    db.commit()
    return {"state": app.state.value}


@router.delete("/applications/{app_id}/evidence")
def delete_evidence(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        n = svc.delete_application_evidence(db, app)
    except PermissionError as e:
        raise conflict(str(e)) from None
    db.commit()
    return {"deleted": n}
