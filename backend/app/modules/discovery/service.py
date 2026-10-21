"""Import from a discovery provider: fetch, normalize, filter, deduplicate, link, mark stale.

* Fetch first, write after: every page is fetched (bounded) before anything is stored, so an
  outage, a rate limit or a pagination loop leaves the database exactly as it was.
* One row per (user, provider, source job id); an unchanged fingerprint is "unchanged"; a
  changed one records which fields changed.
* Merge policy: discovery never modifies an existing tracker job. A new job is created only
  when no existing job matches; matches link to the existing job as it is. What changed at
  the source is shown on the discovered record, and the user edits the job if they want.
* Matching (most specific first): the normalized application URL, then the job URL (the
  canonical form drops tracking parameters), then a conservative fallback: exactly one of the
  user's jobs with no URL and the same employer, title and location.
* Records without a URL, a title or an employer are kept but not linked (manual import).
* Filters apply only to what the source supplied; missing data is "not enough data", never a
  reason to exclude or include by inference.
* Stale: closed at the source; or, for providers that list everything (`complete_listing`)
  after a complete, unqueried listing, absent from it. The tracker job is never changed.
* Nothing is written to the candidate profile."""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.urlsafety import UnsafeURL, check_url_syntax
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import (
    PROVIDERS,
    DiscoveryError,
    DiscoveryFilters,
    DiscoveryProvider,
    MalformedRecord,
    NormalizedJob,
)
from app.modules.jobs.canonical import canonicalize_url, dedupe_key, employer_key, normalize_text
from app.modules.jobs.models import Job, JobSource
from app.modules.jobs.service import upsert_job

log = logging.getLogger(__name__)

# Fields compared between two versions of a source record (names only are stored).
COMPARED = (
    "title",
    "employer",
    "location",
    "workplace",
    "job_url",
    "application_url",
    "employment_type",
    "description_summary",
    "published_on",
    "closed_at_source",
    "cities",
)


@dataclass
class ImportResult:
    fetched: int = 0
    pages: int = 0
    truncated: bool = False  # paging stopped early: the listing is not complete
    stop_reason: str | None = None  # why it stopped early (page limit, rate budget)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    malformed: int = 0
    duplicates_in_listing: int = 0
    excluded_by_filters: int = 0
    insufficient_data: int = 0
    incomplete: int = 0
    stale: int = 0
    linked_new_jobs: int = 0
    linked_existing_jobs: int = 0
    ids: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)  # per record: ids and outcomes only


def fetch_all(provider: DiscoveryProvider, filters: DiscoveryFilters, max_pages: int):
    """All pages, bounded. Returns (records, pages, stop_reason); stop_reason is None when the
    listing ended by itself. Raises DiscoveryError (nothing has been written yet)."""
    records, cursor, seen, pages = [], None, set(), 0
    while True:
        page = provider.list_jobs(filters, cursor)
        pages += 1
        records.extend(page.records)
        if page.next_cursor is None:
            return records, pages, page.stop
        if page.next_cursor in seen or page.next_cursor == cursor:
            raise DiscoveryError("pagination_loop", "The provider's paging repeated; stopped.")
        if pages >= max_pages:
            return records, pages, f"page limit reached ({max_pages} pages)"
        seen.add(page.next_cursor)
        cursor = page.next_cursor


def _norm(value) -> str:
    return normalize_text(value or "")


def apply_filters(n: NormalizedJob, f: DiscoveryFilters) -> dict:
    """{"result": "match" | "excluded" | "insufficient", "fields": [...]}: the fields that
    excluded the record, or the ones the source did not supply."""
    excluded, unknown = [], []
    if f.titles:
        if not n.title:
            unknown.append("title")
        elif not any(_norm(t) and _norm(t) in _norm(n.title) for t in f.titles):
            excluded.append("title")
    if f.cities:
        places = [p for p in [n.location, *n.cities] if p]
        if not places:
            unknown.append("location")
        elif not any(_norm(c) and _norm(c) in _norm(p) for c in f.cities for p in places):
            excluded.append("location")
    if f.workplaces:
        if n.workplace == "unknown":
            unknown.append("workplace")
        elif n.workplace not in f.workplaces:
            excluded.append("workplace")
    if f.sponsorship == "offered":
        value = (n.source_facts.get("sponsorship_offered") or {}).get("value", "unknown")
        if value == "unknown":
            unknown.append("sponsorship")
        elif value != "yes":
            excluded.append("sponsorship")
    if excluded:
        return {"result": "excluded", "fields": excluded}
    if unknown:
        return {"result": "insufficient", "fields": unknown}
    return {"result": "match", "fields": []}


def filters_active(f: DiscoveryFilters) -> bool:
    return bool(f.titles or f.cities or f.workplaces or f.sponsorship != "any")


def _existing_job(db: Session, user_id, n: NormalizedJob) -> tuple[Job | None, str | None]:
    for basis, url in (("application_url", n.application_url), ("job_url", n.job_url)):
        if not url:
            continue
        try:
            canonical = canonicalize_url(check_url_syntax(url))
        except (UnsafeURL, ValueError):
            continue
        key = dedupe_key(
            canonical_url=canonical, employer=n.employer, title=n.title, location=n.location
        )
        job = db.scalar(
            select(Job)
            .where(
                Job.user_id == user_id, (Job.canonical_url == canonical) | (Job.dedupe_key == key)
            )
            .limit(1)
        )
        if job is not None:
            return job, basis
    ek = employer_key(n.employer)
    if ek and n.title:
        same = [
            j
            for j in db.scalars(
                select(Job).where(Job.user_id == user_id, Job.employer_key == ek, Job.url.is_(None))
            )
            if _norm(j.title) == _norm(n.title) and _norm(j.location) == _norm(n.location)
        ]
        if len(same) == 1:
            return same[0], "employer_title_location"
    return None, None


def _link(db: Session, user_id, row: DiscoveredJob, n: NormalizedJob, res: ImportResult) -> str:
    if row.job_id is not None and db.get(Job, row.job_id) is not None:
        row.link_basis = row.link_basis or "previous_link"
        return "existing"
    job, basis = _existing_job(db, user_id, n)
    if job is not None:
        row.job_id, row.link_basis = job.id, basis
        res.linked_existing_jobs += 1
        return "existing"
    if n.closed_at_source:
        # A posting already closed at the source never creates a tracker job.
        row.status, row.job_id, row.link_basis = "closed", None, None
        return "not_linked"
    try:
        job, created = upsert_job(
            db,
            user_id,
            source=JobSource.discovery,
            url=n.job_url or n.application_url,
            employer=n.employer,
            title=n.title,
            location=n.location,
            description=n.description_summary,
            posted_on=n.published_on,
        )
    except UnsafeURL:
        row.status, row.job_id, row.link_basis = "incomplete", None, None
        n.missing.append("URL not accepted")
        res.incomplete += 1
        return "not_linked"
    row.job_id, row.link_basis = job.id, "new_job" if created else "job_url"
    if created:
        res.linked_new_jobs += 1
        return "new"
    res.linked_existing_jobs += 1
    return "existing"


def _store(
    db: Session,
    user_id,
    provider: DiscoveryProvider,
    n: NormalizedJob,
    now,
    res: ImportResult,
    filt: dict | None,
) -> DiscoveredJob:
    row = db.scalar(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user_id,
            DiscoveredJob.provider == provider.name,
            DiscoveredJob.source_job_id == n.source_job_id,
        )
    )
    outcome = "unchanged"
    if row is None:
        row = DiscoveredJob(
            user_id=user_id,
            provider=provider.name,
            source_job_id=n.source_job_id,
            first_seen_at=now,
            changed_fields=[],
        )
        db.add(row)
        res.created += 1
        outcome = "created"
    elif row.fingerprint == n.raw_fingerprint:
        res.unchanged += 1
    else:
        old, new = row.normalized or {}, n.as_dict()
        row.changed_fields = [k for k in COMPARED if old.get(k) != new.get(k)]
        row.changed_at = now
        res.updated += 1
        outcome = "updated"
    row.fingerprint = n.raw_fingerprint
    row.source_facts = n.source_facts
    row.raw_ref = {
        "provider": provider.name,
        "source_job_id": n.source_job_id,
        "fingerprint": n.raw_fingerprint,
        "fields": n.raw_keys,
    }
    row.last_seen_at = row.imported_at = now
    row.filter_result = filt
    row.stale = n.closed_at_source
    row.stale_reason = "closed at source" if n.closed_at_source else None
    if n.missing:
        row.status, row.job_id, row.link_basis = "incomplete", None, None
        res.incomplete += 1
        link = "not_linked"
    else:
        row.status = "linked"
        link = _link(db, user_id, row, n, res)
    row.normalized = n.as_dict()  # after linking: "URL not accepted" may have been added
    db.flush()
    res.records.append(
        {
            "id": str(row.id),
            "source_job_id": n.source_job_id,
            "outcome": outcome,
            "link": link,
            "link_basis": row.link_basis,
            "missing": list(n.missing),
            "filter": filt,
            "changed_fields": row.changed_fields if outcome == "updated" else [],
        }
    )
    return row


def import_from(
    db: Session,
    user_id,
    provider: DiscoveryProvider,
    filters: DiscoveryFilters | None = None,
    max_pages: int = 5,
) -> ImportResult:
    filters = filters or DiscoveryFilters()
    res = ImportResult()
    raw_records, res.pages, res.stop_reason = fetch_all(provider, filters, max_pages)
    res.truncated = res.stop_reason is not None
    res.fetched = len(raw_records)
    now = utcnow()
    seen: set[str] = set()
    for raw in raw_records:
        try:
            n = provider.normalize_job(raw)
        except MalformedRecord:
            res.malformed += 1
            continue
        if n.source_job_id in seen:
            res.duplicates_in_listing += 1
            continue
        seen.add(n.source_job_id)
        filt = apply_filters(n, filters) if filters_active(filters) else None
        if filt and filt["result"] == "excluded":
            res.excluded_by_filters += 1
            continue
        if filt and filt["result"] == "insufficient":
            res.insufficient_data += 1
            if not filters.include_insufficient:
                continue
        row = _store(db, user_id, provider, n, now, res, filt)
        res.ids.append(str(row.id))
    complete = (
        provider.provider_capabilities().get("complete_listing")
        and not res.truncated
        and not filters.query
        and not filters_active(filters)
    )
    if complete:
        for row in db.scalars(
            select(DiscoveredJob).where(
                DiscoveredJob.user_id == user_id, DiscoveredJob.provider == provider.name
            )
        ):
            if row.source_job_id not in seen and not row.stale:
                row.stale, row.stale_reason = True, "not in the latest source listing"
    db.flush()  # the session does not autoflush
    res.stale = len(
        db.scalars(
            select(DiscoveredJob.id).where(
                DiscoveredJob.user_id == user_id,
                DiscoveredJob.provider == provider.name,
                DiscoveredJob.stale.is_(True),
            )
        ).all()
    )
    log.info(
        "discovery import provider=%s pages=%d fetched=%d created=%d updated=%d malformed=%d",
        provider.name,
        res.pages,
        res.fetched,
        res.created,
        res.updated,
        res.malformed,
    )
    return res


def refresh(db: Session, row: DiscoveredJob, provider: DiscoveryProvider) -> str:
    """Re-read one record at the source (get_job): "updated", "unchanged" or "gone". Raises
    DiscoveryError before writing anything."""
    raw = provider.get_job(row.source_job_id)
    now = utcnow()
    if raw is None:
        row.stale, row.stale_reason, row.last_seen_at = True, "no longer at the source", now
        return "gone"
    try:
        n = provider.normalize_job(raw)
    except MalformedRecord:
        raise DiscoveryError("bad_response", "The source returned a malformed record.") from None
    res = ImportResult()
    _store(db, row.user_id, provider, n, now, res, row.filter_result)
    return "updated" if res.updated else "unchanged"


def provider(name: str, **kw) -> DiscoveryProvider:
    return PROVIDERS[name](**kw)


def application_route(db: Session, row: DiscoveredJob):
    """How NoEfforts could apply to a discovered job. A discovery record is never a form schema:
    until the application form has been captured from the employer's own page, and for anything
    unsupported, it is a manual handoff (providers.routing.route_for_job)."""
    from app.modules.providers import routing

    if row.job_id is None:
        return routing.RouteDecision("manual_handoff", "manual_handoff",
                                     ["the source record is incomplete"],
                                     "Import this job manually.")  # fmt: skip
    return routing.route_for_job(db, db.get(Job, row.job_id))
