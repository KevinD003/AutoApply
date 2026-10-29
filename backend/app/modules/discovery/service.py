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
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.urlsafety import UnsafeURL, check_url_syntax
from app.modules.audit.service import record
from app.modules.discovery.models import (
    DiscoveredJob,
    DiscoveryBackoff,
    DiscoveryRunApproval,
    DiscoveryWatch,
)
from app.modules.discovery.provider import (
    PROVIDERS,
    DiscoveryError,
    DiscoveryFilters,
    DiscoveryProvider,
    MalformedRecord,
    NormalizedJob,
)
from app.modules.identity.models import User
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
    deleted_by_you: int = 0  # D56: records you deleted; kept deleted, never imported again
    ids: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)  # per record: ids and outcomes only


# S6 (D67, R9.2): the longest wait a provider's Retry-After can set for a user's requests.
MAX_BACKOFF_S = 86400


def check_backoff(db: Session, user_id, provider_name: str) -> None:
    """Refuse, before any request, while the provider's last Retry-After for this user runs."""
    row = db.get(DiscoveryBackoff, (user_id, provider_name))
    if row is not None and utcnow() < row.not_before:
        label = PROVIDERS[provider_name].label if provider_name in PROVIDERS else provider_name
        raise DiscoveryError(
            "rate_limited_wait",
            f"{label} asked NoEfforts to wait before sending more of your requests; try again "
            f"after {row.not_before:%H:%M:%S} UTC. Nothing was sent.",
        )


def note_backoff(db: Session, user_id, provider_name: str, retry_after: int | None) -> None:
    """After a refusal with a Retry-After in seconds: no request for this user before then.
    Nothing re-runs by itself; without the header nothing is assumed."""
    if not retry_after:
        return
    until = utcnow() + timedelta(seconds=min(max(int(retry_after), 1), MAX_BACKOFF_S))
    row = db.get(DiscoveryBackoff, (user_id, provider_name))
    if row is None:
        db.add(DiscoveryBackoff(user_id=user_id, provider=provider_name, not_before=until))
    else:
        row.not_before, row.updated_at = max(row.not_before, until), utcnow()


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
    if row is not None and row.status == "dismissed":
        res.deleted_by_you += 1  # D56: only its id is kept, so that it stays deleted
        return row
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
    if n.closed_at_source and not (row.stale and row.stale_reason == "closed at source"):
        row.stale_since = now  # S3 (D59): when the source first said so
    row.stale = n.closed_at_source
    row.stale_reason = "closed at source" if n.closed_at_source else None
    row.stale_since = row.stale_since if row.stale else None
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


def use_live_approval(db: Session, user, provider_name: str, query: str | None, preflight) -> int:
    """D55: before a live read, the owner's unused run approval for this exact search, inside
    its window, is marked used and committed, so a run that then fails needs a new approval and
    nothing re-runs on its own. Returns the approved page limit. In order, with nothing
    looked up or requested before the first two: the account must be named in
    NOEFFORTS_DISCOVERY_OWNER_EMAILS; such an approval must exist (locked); `preflight` (the
    public-address check) must pass. A refusal at any step uses nothing."""
    owners = {e.strip().lower() for e in get_settings().discovery_owner_emails if e.strip()}
    if user.email.lower() not in owners:
        raise DiscoveryError(
            "not_authorized",
            "Live Freehire reads are limited to the owner's account; nothing was requested.",
        )
    now = utcnow()
    approval = db.scalar(
        select(DiscoveryRunApproval)
        .where(
            DiscoveryRunApproval.user_id == user.id,
            DiscoveryRunApproval.provider == provider_name,
            DiscoveryRunApproval.query == (query or ""),
            DiscoveryRunApproval.consumed_at.is_(None),
            DiscoveryRunApproval.not_before <= now,
            DiscoveryRunApproval.not_after > now,
        )
        .order_by(DiscoveryRunApproval.created_at)
        .limit(1)
        .with_for_update()
    )
    if approval is None:
        raise DiscoveryError(
            "not_authorized",
            "No unused run approval covers this exact search now; nothing was requested. The "
            "owner records one with `python -m app.modules.discovery.approve`.",
        )
    preflight()
    approval.consumed_at = now
    record(
        db,
        user.id,
        "discovery.run_approval.use",
        "discovery_run_approval",
        approval.id,
        provider=provider_name,
        max_pages=approval.max_pages,
    )
    db.commit()
    return approval.max_pages


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
        if row.status != "dismissed":
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
                row.stale_since = utcnow()
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
        if not (row.stale and row.stale_reason == "no longer at the source"):
            row.stale_since = now  # S3 (D59)
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

    if row.job_id is None and row.status == "closed":
        return routing.RouteDecision("manual_handoff", "manual_handoff",
                                     ["the posting was closed at its source"],
                                     "This posting was closed at its source, so it was not "
                                     "added to your tracker.",
                                     "source_posting_closed")  # fmt: skip
    if row.job_id is None:
        return routing.RouteDecision("manual_handoff", "manual_handoff",
                                     ["the source record is incomplete"],
                                     "Import this job manually.",
                                     "source_record_incomplete")  # fmt: skip
    return routing.route_for_job(db, db.get(Job, row.job_id))


# -- D56: watched searches ------------------------------------------------------------------------

WATCH_PAGES = 2  # requests a check may make: newest first, it stops at a posting already stored
WATCH_PAUSE_AFTER = 10  # failures in a row
WATCH_MAX_BACKOFF = 3600  # seconds


def owners() -> set[str]:
    return {e.strip().lower() for e in get_settings().discovery_owner_emails if e.strip()}


def check_due_watches(now: datetime | None = None, limit: int = 20) -> int:
    """The worker task (every 10 s): each due watch is checked once, in its own transaction,
    locked with SKIP LOCKED so that two workers never check one watch at the same time. Returns
    how many watches were checked or paused. Nothing runs while Freehire is not an enabled
    discovery provider."""
    if "freehire" not in get_settings().discovery_providers:
        return 0
    now = now or utcnow()
    with SessionLocal() as db:
        due = db.scalars(
            select(DiscoveryWatch.id)
            .where(
                DiscoveryWatch.revoked_at.is_(None),
                DiscoveryWatch.paused_reason.is_(None),
                DiscoveryWatch.not_before <= now,
                DiscoveryWatch.not_after > now,
                DiscoveryWatch.next_check_at <= now,
            )
            .order_by(DiscoveryWatch.next_check_at)
            .limit(limit)
        ).all()
    done = 0
    for watch_id in due:
        with SessionLocal() as db:
            w = db.scalar(
                select(DiscoveryWatch)
                .where(DiscoveryWatch.id == watch_id)
                .with_for_update(skip_locked=True)
            )
            if w is None or w.revoked_at or w.paused_reason or w.next_check_at > now:
                continue  # another worker has it, or it changed since
            _check_watch(db, w, now)
            db.commit()
            done += 1
    return done


def _pause(db: Session, w: DiscoveryWatch, reason: str) -> None:
    w.paused_reason = w.last_outcome = reason
    record(db, w.user_id, "discovery.watch.pause", "discovery_watch", w.id, reason=reason)


def _check_watch(db: Session, w: DiscoveryWatch, now: datetime) -> None:
    """One check of one watch: who and where first (nothing requested before), then the daily
    cap, then the newest postings until a known one. Never retried inside a check."""
    s = get_settings()
    user = db.get(User, w.user_id)
    if user is None or user.email.lower() not in owners():
        _pause(db, w, "not_owner")
        return
    p = PROVIDERS[w.provider]()
    if not p.wants_live() and not _fixture(p):
        _pause(db, w, "address_refused")
        return
    today = now.date()
    if w.budget_day != today:
        w.budget_day, w.requests_on_day = today, 0
    used = db.scalar(
        select(func.coalesce(func.sum(DiscoveryWatch.requests_on_day), 0)).where(
            DiscoveryWatch.budget_day == today
        )
    )
    if used + WATCH_PAGES > s.freehire_daily_request_budget:
        w.last_outcome = "daily_budget"
        w.next_check_at = datetime.combine(today + timedelta(days=1), time(0), tzinfo=now.tzinfo)
        return
    w.last_checked_at = now
    try:
        # A savepoint: a failed check keeps none of its rows, while the watch stays locked.
        with db.begin_nested():
            if p.wants_live():
                p.check_live_destination()
                p.live = True
            p.newest_first = True
            p.stop_at = set(
                db.scalars(
                    select(DiscoveredJob.source_job_id).where(
                        DiscoveredJob.user_id == w.user_id, DiscoveredJob.provider == w.provider
                    )
                )
            )
            res = import_from(db, w.user_id, p, DiscoveryFilters(query=w.query), WATCH_PAGES)
    except Exception as e:  # a provider failure, or anything unexpected: back off, never loop
        if not isinstance(e, DiscoveryError):
            log.exception("discovery watch check failed watch=%s", w.id)
        w.requests_on_day += p.requests
        w.failures += 1
        kind = getattr(e, "kind", "error")
        kind = "address_refused" if kind == "disabled" else kind
        w.last_outcome = kind
        wait = min(w.interval_seconds * 2 ** (w.failures - 1), WATCH_MAX_BACKOFF)
        if kind == "rate_limited":
            wait = max(wait, p.retry_after or 300)
        w.next_check_at = now + timedelta(seconds=wait)
        if w.failures >= WATCH_PAUSE_AFTER:
            _pause(db, w, kind)
        return
    w.requests_on_day += p.requests
    w.failures, w.last_outcome = 0, "ok"
    w.found_total += res.created
    wait = w.interval_seconds
    if p.rate.get("remaining") == "0":
        wait = max(wait, 60)  # Freehire's budget is used up for now: never sooner than a minute
    w.next_check_at = now + timedelta(seconds=wait)
    if res.created:
        record(
            db, w.user_id, "discovery.watch.found", "discovery_watch", w.id,
            provider=w.provider, created=res.created,
        )  # fmt: skip


def _fixture(p) -> bool:
    from app.modules.discovery import provider as fh

    return bool(getattr(p, "base", "")) and fh.is_fixture_origin(p.base)


# -- D56: deleting a discovered posting ----------------------------------------------------------


def dismiss(db: Session, row: DiscoveredJob) -> dict:
    """Erase a discovered posting and keep only its id, so that no import or watch brings it
    back. Its tracker job is deleted too when discovery created it, nothing else links to it and
    it has no application; otherwise the job stays and the answer says why."""
    from app.modules.applications.models import Application

    out = {"job_deleted": False, "job_kept_because": None}
    job = db.get(Job, row.job_id) if row.job_id else None
    if job is not None:
        others = db.scalar(
            select(func.count(DiscoveredJob.id)).where(
                DiscoveredJob.job_id == job.id, DiscoveredJob.id != row.id
            )
        )
        applied = db.scalar(select(func.count(Application.id)).where(Application.job_id == job.id))
        if job.source != JobSource.discovery:
            out["job_kept_because"] = "you added it yourself"
        elif applied:
            out["job_kept_because"] = "it has an application"
        elif others:
            out["job_kept_because"] = "another discovered posting links to it"
        else:
            db.delete(job)
            out["job_deleted"] = True
    row.status, row.job_id, row.link_basis = "dismissed", None, None
    row.normalized, row.source_facts, row.raw_ref, row.filter_result = {}, {}, None, None
    row.changed_fields, row.changed_at, row.stale, row.stale_reason = [], None, False, None
    row.stale_since = None
    return out
