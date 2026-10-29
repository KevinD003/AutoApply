"""Your account: a full export, and deletion (priority B, D77; docs/account-deletion.md).

Each route acts on the signed-in account only; none takes an account id."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.modules.account import deletion, export, policy
from app.modules.audit.service import record
from app.modules.documents.storage import Storage, get_storage
from app.modules.identity.deps import SESSION_COOKIE, current_user, session_only
from app.modules.identity.models import User
from app.modules.identity.security import login_limiter, verify_password

# Export and deletion are the app's only (D84): an API token is refused, whatever its scopes.
router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(session_only)])
CONFIRMATION = "delete my account"


@router.get("/export")
def export_account(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Everything NoEfforts holds about your account, as a ZIP (export.py says what is left
    out). Audited with counts only."""
    data, summary = export.build(db, user.id, storage)
    record(
        db,
        user.id,
        "account.export",
        "user",
        user.id,
        tables=summary["tables"],
        rows=summary["rows"],
        documents=summary["files"],
    )
    db.commit()
    name = f"noefforts-export-{utcnow():%Y%m%d}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


class DeletionPreview(BaseModel):
    counts: dict[str, int]
    submitted_applications: int
    blocked_by: list[str]
    blocked_reasons: list[str]
    retained_in_database: list[str]
    grace_period_days: int
    outside_noefforts: list[dict[str, str]]
    confirmation: str


@router.get("/deletion", response_model=DeletionPreview)
def deletion_preview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = deletion.preview(db, user.id)
    return DeletionPreview(
        **p,
        blocked_reasons=[deletion.refusal(c) for c in p["blocked_by"]],
        retained_in_database=list(policy.RETAINED_IN_DATABASE),
        grace_period_days=policy.GRACE_PERIOD_DAYS,
        outside_noefforts=[{"what": w, "note": n} for w, n in policy.OUTSIDE_NOEFFORTS],
        confirmation=CONFIRMATION,
    )


class DeleteRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str = Field(max_length=100)


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: DeleteRequest,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> None:
    """Deletes your account and everything that names it, at once. Needs your password and the
    confirmation phrase; refused, with nothing deleted, while a submission may be in flight."""
    if body.confirmation.strip().lower() != CONFIRMATION:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, deletion.refusal("deletion_unconfirmed"))
    if not login_limiter.allow(f"delete:{user.id}", get_settings().login_rate_limit_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try later")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, deletion.refusal("deletion_password"))
    try:
        deletion.delete_account(db, user.id, storage)
    except deletion.DeletionRefused as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    response.delete_cookie(SESSION_COOKIE, path="/")
