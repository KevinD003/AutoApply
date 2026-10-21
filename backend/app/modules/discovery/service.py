"""Import from a discovery provider: normalize, deduplicate, mark stale, link to the tracker.

* one row per (user, provider, source job id); an unchanged fingerprint is "unchanged";
* complete records are linked to a tracker job through jobs.upsert_job, so a posting the
  user already has (same canonical URL) is recognised, not duplicated, and two source records
  for the same posting share one job;
* incomplete records (no URL, no title or no employer) are kept but not linked: the user can
  import the job manually;
* records missing from the latest listing, or closed at the source, are marked stale; the
  tracker job itself is never changed by that (the user decides);
* nothing is written to the candidate profile."""

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import PROVIDERS, DiscoveryProvider
from app.modules.jobs.models import Job, JobSource
from app.modules.jobs.service import upsert_job


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    incomplete: int = 0
    stale: int = 0
    linked_new_jobs: int = 0
    linked_existing_jobs: int = 0
    ids: list[str] = field(default_factory=list)


def import_from(db: Session, user_id, provider: DiscoveryProvider) -> ImportResult:
    res = ImportResult()
    now = utcnow()
    seen: set[str] = set()
    for raw in provider.fetch():
        n = provider.normalize(raw)
        seen.add(n.source_job_id)
        row = db.scalar(select(DiscoveredJob).where(
            DiscoveredJob.user_id == user_id, DiscoveredJob.provider == provider.name,
            DiscoveredJob.source_job_id == n.source_job_id))  # fmt: skip
        if row is not None and row.fingerprint == n.raw_fingerprint:
            res.unchanged += 1
            row.last_seen_at = now
        else:
            if row is None:
                row = DiscoveredJob(user_id=user_id, provider=provider.name,
                                    source_job_id=n.source_job_id, first_seen_at=now)  # fmt: skip
                db.add(row)
                res.created += 1
            else:
                res.updated += 1
            row.fingerprint = n.raw_fingerprint
            row.normalized = n.as_dict()
            row.source_facts = n.source_facts
            row.last_seen_at = row.imported_at = now
        row.stale = n.closed_at_source
        row.stale_reason = "closed at source" if n.closed_at_source else None
        if n.missing:
            row.status, row.job_id = "incomplete", None
            res.incomplete += 1
        else:
            job, created = upsert_job(
                db, user_id, source=JobSource.discovery, url=n.job_url or n.application_url,
                employer=n.employer, title=n.title, location=n.location,
                description=n.description_summary, posted_on=n.published_on,
            )  # fmt: skip
            row.status, row.job_id = "linked", job.id
            if created:
                res.linked_new_jobs += 1
            else:
                res.linked_existing_jobs += 1
        db.flush()
        res.ids.append(str(row.id))
    for row in db.scalars(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user_id, DiscoveredJob.provider == provider.name
        )
    ):
        if row.source_job_id not in seen and not row.stale:
            row.stale, row.stale_reason = True, "not in the latest source listing"
    db.flush()  # the session does not autoflush
    res.stale = len(db.scalars(select(DiscoveredJob.id).where(
        DiscoveredJob.user_id == user_id, DiscoveredJob.provider == provider.name,
        DiscoveredJob.stale.is_(True))).all())  # fmt: skip
    return res


def provider(name: str, **kw) -> DiscoveryProvider:
    return PROVIDERS[name](**kw)


def application_route(db: Session, row: DiscoveredJob):
    """How NoEfforts could apply to a discovered job: only once its application form has been
    captured; until then, and for anything unsupported, a manual handoff."""
    from app.modules.preparation.models import JobForm
    from app.modules.providers import routing

    if row.job_id is None:
        return routing.RouteDecision("manual_handoff", "manual_handoff",
                                     ["the source record is incomplete"],
                                     "Import this job manually.")  # fmt: skip
    job = db.get(Job, row.job_id)
    form = db.scalar(select(JobForm).where(JobForm.job_id == job.id, JobForm.user_id == job.user_id)
                     .order_by(JobForm.version.desc()))  # fmt: skip
    if form is None:
        return routing.RouteDecision("manual_handoff", "manual_handoff",
                                     ["no application form captured yet"],
                                     "Capture the application form first.")  # fmt: skip
    p = urlsplit(job.url or "")
    action = (form.schema or {}).get("action")
    destination = {
        "origin": f"{p.scheme}://{p.netloc}" if p.netloc else None,
        "url": job.url,
        "submit_url": urljoin(job.url, action) if job.url and action else None,
        "form_source": form.source,
    }
    return routing.decide(destination, job.user_id)
