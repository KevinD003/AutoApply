"""Job discovery: optional, replaceable providers that only find jobs (docs/discovery.md).

Every provider is off unless named in NOEFFORTS_DISCOVERY_PROVIDERS. A provider failure is
reported (503) and changes nothing; manual job entry and spreadsheet import never depend on a
provider. Responses never include credentials, raw source payloads or anything from the
candidate profile."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import not_found
from app.modules.audit.service import record
from app.modules.discovery import service
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import PROVIDERS, DiscoveryError, DiscoveryFilters, enabled
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.profiles.models import JobPreferences

router = APIRouter(prefix="/discovery", tags=["discovery"])

STATUS = {
    "freehire": {
        "implemented_locally": True,
        "external_api_configured": False,
        "external_api_tested": False,
        "production_ready": False,
        "note": "Potential future discovery provider; not yet connected or validated. Built to "
        "Freehire's documented public API (reviewed 2026-10-19) and tested only against a local "
        "fixture.",
    },
    "freehire_mock": {
        "implemented_locally": True,
        "external_api_configured": False,
        "external_api_tested": False,
        "production_ready": False,
        "note": "Local mock file with an invented record shape; development and tests only.",
    },
}


class ImportIn(BaseModel):
    provider: str = Field(max_length=50)
    titles: list[str] = Field(default_factory=list, max_length=20)
    cities: list[str] = Field(default_factory=list, max_length=20)
    workplaces: list[str] = Field(default_factory=list, max_length=3)
    sponsorship: str = Field(default="any", pattern="^(any|offered)$")
    query: str | None = Field(default=None, max_length=200)
    use_preferences: bool = False
    include_insufficient: bool = True


def _provider(name: str):
    if name not in PROVIDERS:
        raise not_found("Discovery provider")
    if not enabled(name):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{PROVIDERS[name].label} is disabled.")
    return PROVIDERS[name]()


def _fail(e: DiscoveryError) -> HTTPException:
    if e.kind == "disabled":
        return HTTPException(status.HTTP_409_CONFLICT, str(e))
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{e} Nothing was changed.")


def _row(r: DiscoveredJob, detail: bool = False) -> dict:
    n = r.normalized or {}
    out = {
        "id": str(r.id),
        "provider": r.provider,
        "provider_label": PROVIDERS[r.provider].label if r.provider in PROVIDERS else r.provider,
        "source_job_id": r.source_job_id,
        "title": n.get("title"),
        "employer": n.get("employer"),
        "location": n.get("location"),
        "workplace": n.get("workplace"),
        "employment_type": n.get("employment_type"),
        "job_url": n.get("job_url"),
        "application_url": n.get("application_url"),
        "ats_provider": n.get("ats_provider"),
        "published_on": n.get("published_on"),
        "source_last_seen_at": n.get("source_last_seen_at"),
        "status": r.status,
        "job_id": str(r.job_id) if r.job_id else None,
        "link_basis": r.link_basis,
        "missing": n.get("missing") or [],
        "filter": r.filter_result,
        "source_facts": r.source_facts,
        "stale": r.stale,
        "stale_reason": r.stale_reason,
        "changed_fields": r.changed_fields or [],
        "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        "first_seen_at": r.first_seen_at.isoformat(),
        "last_seen_at": r.last_seen_at.isoformat(),
    }
    if detail:
        out["description_summary"] = n.get("description_summary")
        out["raw_ref"] = r.raw_ref
    return out


def _owned(db: Session, user: User, row_id: uuid.UUID) -> DiscoveredJob:
    row = db.get(DiscoveredJob, row_id)
    if row is None or row.user_id != user.id:
        raise not_found("Discovered job")
    return row


@router.get("/providers")
def providers(user: User = Depends(current_user)) -> list[dict]:
    s = get_settings()
    out = []
    for name, cls in PROVIDERS.items():
        out.append(
            {
                "name": name,
                "label": cls.label,
                "kind": "discovery",
                "enabled": enabled(name),
                "capabilities": cls().provider_capabilities(),
                # Whether settings are present, never their values.
                "configured": {
                    "base_url": bool(s.freehire_base_url),
                    "api_key": bool(s.freehire_api_key),
                }
                if name == "freehire"
                else {},
                "status": STATUS[name],
            }
        )
    return out


@router.post("/providers/{name}/healthcheck")
def healthcheck(name: str, user: User = Depends(current_user)) -> dict:
    return _provider(name).healthcheck()


@router.post("/import")
def run_import(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _provider(body.provider)
    f = DiscoveryFilters(
        titles=[t.strip() for t in body.titles if t.strip()],
        cities=[c.strip() for c in body.cities if c.strip()],
        workplaces=[w for w in body.workplaces if w in ("remote", "hybrid", "onsite")],
        sponsorship=body.sponsorship,
        query=body.query,
        include_insufficient=body.include_insufficient,
    )
    if body.use_preferences:
        # Preferences (targets) only. Sponsorship needs are facts and are never used here.
        prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == user.id))
        if prefs is not None:
            f.titles = f.titles or list(prefs.titles or [])
            f.cities = f.cities or [
                loc.get("city")
                for loc in prefs.target_locations or []
                if isinstance(loc, dict) and loc.get("city")
            ]
            f.workplaces = f.workplaces or list(prefs.work_modes or [])
    try:
        res = service.import_from(db, user.id, p, f, max_pages=get_settings().freehire_max_pages)
    except DiscoveryError as e:
        db.rollback()
        raise _fail(e) from None
    record(
        db,
        user.id,
        "discovery.import",
        "discovery",
        None,
        provider=p.name,
        fetched=res.fetched,
        created=res.created,
        updated=res.updated,
    )
    db.commit()
    out = {k: v for k, v in res.__dict__.items() if k != "ids"}
    out["provider"] = p.name
    return out


@router.get("/jobs")
def list_rows(
    provider: str | None = Query(default=None, max_length=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = select(DiscoveredJob).where(DiscoveredJob.user_id == user.id)
    if provider:
        q = q.where(DiscoveredJob.provider == provider)
    return [_row(r) for r in db.scalars(q.order_by(DiscoveredJob.last_seen_at.desc()).limit(500))]


@router.get("/jobs/{row_id}")
def get_row(row_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _owned(db, user, row_id)
    out = _row(row, detail=True)
    d = service.application_route(db, row)
    out["route"] = {"route": d.route, "provider": d.provider, "message": d.message}
    return out


@router.post("/jobs/{row_id}/refresh")
def refresh_row(
    row_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = _owned(db, user, row_id)
    p = _provider(row.provider)
    try:
        outcome = service.refresh(db, row, p)
    except DiscoveryError as e:
        db.rollback()
        raise _fail(e) from None
    db.commit()
    return {"outcome": outcome, "job": _row(row)}
