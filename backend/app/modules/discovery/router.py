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
from app.modules.providers import registry, wording

router = APIRouter(prefix="/discovery", tags=["discovery"])

STATUS = {
    "freehire": {
        "implemented_locally": True,
        "external_api_configured": False,
        "external_api_tested": False,
        "production_ready": False,
        "note": "Not yet validated against Freehire: built to its documented public API "
        "(documentation reviewed 2026-10-21) and tested only against a local fixture. Personal "
        "prototype only: a live read is limited to the owner's account and needs the owner's "
        "single-use run approval for the exact search (D55). Listings are credited "
        '"via freehire.me".',
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
    if e.kind == "not_authorized":
        return HTTPException(status.HTTP_403_FORBIDDEN, str(e))
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
        "source_updated_at": n.get("source_updated_at"),
        "attribution": n.get("attribution") or _attribution(r.provider),
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


def _attribution(provider: str) -> dict:
    """For rows stored before attribution was recorded: the provider's own credit."""
    cls = PROVIDERS.get(provider)
    return dict(
        getattr(cls, "ATTRIBUTION", None) or {"text": cls.label if cls else provider, "url": None}
    )


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
                # Derived from the provider registry's evidence (providers/wording.py).
                "support_label": wording.support_label(registry.PROVIDERS[name]),
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
    max_pages = get_settings().freehire_max_pages
    try:
        if p.name == "freehire" and p.wants_live():
            # D55: the owner and the approval for this exact search, then the address, are
            # checked; the approval is used (and committed) before the first request.
            used = service.use_live_approval(db, user, p.name, f.query, p.check_live_destination)
            max_pages = min(max_pages, used)
            p.live = True
        res = service.import_from(db, user.id, p, f, max_pages=max_pages)
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
    from app.modules.providers import routing

    row = _owned(db, user, row_id)
    out = _row(row, detail=True)
    d = service.application_route(db, row)
    out["route"] = routing.route_view(d)
    # A linked row shows its tracker job's route: recorded as the job page records it. A row
    # without a job has no job to record against (its route is always a manual handoff).
    if row.job_id is not None and routing.audit_route(db, user.id, row.job_id, d):
        db.commit()
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
