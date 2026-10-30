"""Your public employer job boards (D95): add, rename, pause, resume or remove a board, read it
when you choose, see its postings, and save one to your jobs. Every route acts on your account
only (another account's source or posting is 404). A posting is never an application route."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import not_found
from app.modules.audit.service import record
from app.modules.discovery import board_sync, boards
from app.modules.discovery.models import BoardSource, DiscoveredJob
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job

router = APIRouter(prefix="/discovery/sources", tags=["discovery"])

ERROR_TEXT = {
    "board_not_found": "The provider has no public board by that name.",
    "rate_limited": "The provider is limiting requests; NoEfforts waits before reading again.",
    "unavailable": "The provider did not answer properly; nothing was changed.",
    "redirected": "The provider answered with a redirect, which is never followed.",
    "destination_refused": "The provider's address was not a public address; nothing was sent.",
    "too_large": "The board's answer was larger than allowed; nothing was changed.",
    "bad_response": "The board's answer was not in the documented shape; nothing was changed.",
}


class SourceIn(BaseModel):
    provider: str = Field(max_length=20)
    board: str = Field(max_length=100)
    region: str = Field(default="global", max_length=10)
    employer: str = Field(min_length=1, max_length=200)


class SourcePatch(BaseModel):
    employer: str | None = Field(default=None, min_length=1, max_length=200)
    paused: bool | None = None


def _refuse(code: str, message: str, http: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(http, f"{message} (reason: {code})")


def _owned(db: Session, user: User, source_id: uuid.UUID) -> BoardSource:
    src = db.get(BoardSource, source_id)
    if src is None or src.user_id != user.id:
        raise not_found("Job board")
    return src


def _view(db: Session, src: BoardSource) -> dict:
    counts = dict(
        db.execute(
            select(DiscoveredJob.stale, func.count())
            .where(DiscoveredJob.board_source_id == src.id, DiscoveredJob.user_id == src.user_id,
                   DiscoveredJob.status != "dismissed")
            .group_by(DiscoveredJob.stale)
        ).all()
    )  # fmt: skip
    saved = db.scalar(
        select(func.count()).where(DiscoveredJob.board_source_id == src.id,
                                   DiscoveredJob.user_id == src.user_id,
                                   DiscoveredJob.job_id.is_not(None))
    )  # fmt: skip
    spec = boards.PROVIDERS.get(src.provider)
    return {
        "id": str(src.id),
        "provider": src.provider,
        "provider_label": spec.label if spec else src.provider,
        "region": src.region,
        "board": src.board,
        "employer": src.employer,
        "paused": src.paused,
        "last_attempt_at": src.last_attempt_at.isoformat() if src.last_attempt_at else None,
        "last_success_at": src.last_success_at.isoformat() if src.last_success_at else None,
        "last_status": src.last_status,
        "last_error_code": src.last_error_code,
        "last_error": ERROR_TEXT.get(src.last_error_code) if src.last_error_code else None,
        "next_allowed_at": src.next_allowed_at.isoformat() if src.next_allowed_at else None,
        "listed": counts.get(False, 0),
        "no_longer_listed": counts.get(True, 0),
        "in_your_jobs": saved or 0,
    }


@router.get("")
def list_sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(BoardSource).where(BoardSource.user_id == user.id).order_by(BoardSource.created_at)
    ).all()
    return {
        "enabled": get_settings().board_sources_enabled,
        "providers": [
            {"key": k, "label": v.label, "identifier": v.identifier, "regions": list(v.hosts)}
            for k, v in boards.PROVIDERS.items()
        ],
        "not_built": boards.NOT_BUILT,
        "items": [_view(db, s) for s in rows],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def add_source(body: SourceIn, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:  # fmt: skip
    try:
        board = boards.check_identifier(body.provider, body.region, body.board)
    except boards.BoardError as e:
        raise _refuse(e.code, e.message, status.HTTP_400_BAD_REQUEST) from None
    src = BoardSource(user_id=user.id, provider=body.provider, region=body.region, board=board,
                      employer=body.employer.strip(), paused=False, last_count=0,
                      failures=0)  # fmt: skip
    db.add(src)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _refuse("source_exists", "You already added this board.") from None
    record(db, user.id, "board_source.update", "board_source", src.id, change="add",
           provider=src.provider)  # fmt: skip
    db.commit()
    return _view(db, src)


@router.patch("/{source_id}")
def edit_source(source_id: uuid.UUID, body: SourcePatch, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:  # fmt: skip
    src = _owned(db, user, source_id)
    change = "edit"
    if body.employer is not None:
        src.employer = body.employer.strip()
    if body.paused is not None and body.paused != src.paused:
        src.paused, change = body.paused, "pause" if body.paused else "resume"
    record(db, user.id, "board_source.update", "board_source", src.id, change=change,
           provider=src.provider)  # fmt: skip
    db.commit()
    return _view(db, src)


@router.delete("/{source_id}")
def remove_source(source_id: uuid.UUID, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> dict:  # fmt: skip
    """The board and its postings are deleted; a job you saved from it stays in your jobs."""
    src = _owned(db, user, source_id)
    record(db, user.id, "board_source.update", "board_source", src.id, change="remove",
           provider=src.provider)  # fmt: skip
    db.delete(src)
    db.commit()
    return {"removed": True}


@router.post("/{source_id}/sync")
def sync_source(source_id: uuid.UUID, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:  # fmt: skip
    _owned(db, user, source_id)
    try:
        out = board_sync.sync(db, user.id, source_id)
    except board_sync.Refused as e:
        raise _refuse(e.code, e.message) from None
    except LookupError:
        raise not_found("Job board") from None
    record(db, user.id, "board_source.update", "board_source", source_id, change="sync",
           outcome=out["status"])  # fmt: skip
    db.commit()
    return out | {"source": _view(db, _owned(db, user, source_id))}


@router.get("/{source_id}/postings")
def postings(source_id: uuid.UUID, user: User = Depends(current_user),
             db: Session = Depends(get_db)) -> dict:  # fmt: skip
    from app.modules.jobs import fit
    from app.modules.jobs.router import _fit_inputs

    src = _owned(db, user, source_id)
    rows = db.scalars(
        select(DiscoveredJob)
        .where(DiscoveredJob.board_source_id == src.id, DiscoveredJob.user_id == user.id,
               DiscoveredJob.status != "dismissed")
        .order_by(DiscoveredJob.stale, DiscoveredJob.first_seen_at.desc())
        .limit(500)
    ).all()  # fmt: skip
    prefs, profile, auths, creds = _fit_inputs(db, user)
    items = []
    for r in rows:
        n = r.normalized or {}
        transient = Job(user_id=user.id, title=n.get("title"), employer=n.get("employer"),
                        location=n.get("location"), description=n.get("description_summary"),
                        url=n.get("job_url"))  # fmt: skip
        items.append({
            "id": str(r.id),
            "title": n.get("title"),
            "employer": n.get("employer"),
            "location": n.get("location"),
            "workplace": n.get("workplace"),
            "employment_type": n.get("employment_type"),
            "job_url": n.get("job_url"),
            "description_summary": n.get("description_summary"),
            # Kept apart (D95): what the source says, what you saved, how it matches you.
            "source_lists_it": not r.stale,
            "no_longer_listed_since": r.stale_since.isoformat() if r.stale else None,
            "job_id": str(r.job_id) if r.job_id else None,
            "changed_fields": r.changed_fields or [],
            "match": fit.summary(fit.assess(transient, prefs, profile, auths, creds, [])),
            "attribution": n.get("attribution"),
        })  # fmt: skip
    return {"source": _view(db, src), "items": items}


@router.post("/postings/{row_id}/save")
def save_posting(row_id: uuid.UUID, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:  # fmt: skip
    try:
        out = board_sync.save(db, user.id, row_id)
    except LookupError:
        raise not_found("Posting") from None
    except board_sync.Refused as e:
        raise _refuse(e.code, e.message) from None
    record(db, user.id, "board_source.update", "discovered_job", row_id, change="save",
           outcome=out["outcome"])  # fmt: skip
    db.commit()
    return out
