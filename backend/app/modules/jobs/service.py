import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.urlsafety import UnsafeURL, check_url_syntax
from app.modules.jobs.canonical import (
    canonicalize_url,
    dedupe_key,
    detect_ats,
    employer_key,
    normalize_text,
    url_key,
)
from app.modules.jobs.models import Job, JobSource, JobStatus
from app.modules.profiles.models import JobPreferences


def upsert_job(
    db: Session,
    user_id: uuid.UUID,
    *,
    source: JobSource,
    url: str | None = None,
    employer: str | None = None,
    title: str | None = None,
    location: str | None = None,
    requisition_id: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    posted_on: date | None = None,
    status: JobStatus | None = None,
) -> tuple[Job, bool]:
    """Insert a job or recognise it as a duplicate. Safe under concurrent imports.

    Returns (job, created). Duplicates refresh `last_seen_at` but do not overwrite user edits.
    """
    canonical = None
    ats_provider, ats_req = "unknown", None
    if url:
        url = check_url_syntax(url)
        canonical = canonicalize_url(url)
        if len(canonical) > 2048:  # canonicalizing can lengthen it (scheme, encoded query)
            raise UnsafeURL("URL is too long")
        ats = detect_ats(canonical)
        ats_provider, ats_req = ats.provider, ats.requisition_id
        if ats_req and len(ats_req) > 200:  # jobs.requisition_id is String(200)
            ats_req = None
    key = dedupe_key(
        canonical_url=canonical,
        employer=employer,
        title=title,
        location=location,
        requisition_id=requisition_id,
    )
    now = utcnow()
    values = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        dedupe_key=key,
        employer=employer,
        employer_key=employer_key(employer) or None,
        title=title,
        location=location,
        url=url,
        canonical_url=canonical,
        ats_provider=ats_provider,
        requisition_id=requisition_id or ats_req,
        description=description,
        source=source,
        status=status or JobStatus.new,
        notes=notes,
        posted_on=posted_on,
        first_seen_at=now,
        last_seen_at=now,
        seen_count=1,
        created_at=now,
        updated_at=now,
    )
    if canonical and key.startswith("ats:"):
        # S3 (D59): a job stored before its ATS was recognised (a Greenhouse embed URL) keeps
        # the URL key it was stored under; the same URL finds it, never a second job.
        legacy = db.scalar(
            select(Job).where(Job.user_id == user_id, Job.dedupe_key == url_key(canonical))
        )
        if legacy is not None:
            key = legacy.dedupe_key
    stmt = (
        insert(Job)
        .values(**{**values, "dedupe_key": key})
        .on_conflict_do_nothing(constraint="uq_jobs_user_dedupe")
        .returning(Job.id)
    )
    inserted = db.execute(stmt).scalar_one_or_none()
    if inserted is not None:
        job = db.get(Job, inserted)
        apply_exclusions(db, job)
        return job, True
    job = db.scalar(select(Job).where(Job.user_id == user_id, Job.dedupe_key == key))
    job.last_seen_at = now
    job.seen_count += 1
    # Fill gaps from the new sighting without overwriting existing values.
    for field, val in (
        ("employer", employer),
        ("title", title),
        ("location", location),
        ("description", description),
        ("posted_on", posted_on),
    ):
        if val and not getattr(job, field):
            setattr(job, field, val)
    return job, False


def apply_exclusions(db: Session, job: Job) -> None:
    prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == job.user_id))
    if prefs is None or job.status != JobStatus.new:
        return
    excluded = {employer_key(e) for e in prefs.excluded_employers or []}
    if job.employer_key and job.employer_key in excluded:
        job.status = JobStatus.excluded
        job.exclusion_reason = f"Employer '{job.employer}' is on your excluded list"


def explain(job: Job, prefs: JobPreferences | None) -> list[dict]:
    """Plain-language reasons for and against this job. Phase A: preference checks only."""
    if prefs is None:
        return [{"kind": "info", "text": "Set your preferences to see match explanations."}]
    reasons: list[dict] = []
    if job.exclusion_reason:
        reasons.append({"kind": "exclude", "text": job.exclusion_reason})
    title = normalize_text(job.title)
    if prefs.titles:
        hits = [t for t in prefs.titles if normalize_text(t) and normalize_text(t) in title]
        reasons.append(
            {"kind": "match", "text": f"Title matches '{hits[0]}'"}
            if hits
            else {"kind": "mismatch", "text": "Title does not match any target title"}
        )
    loc = normalize_text(job.location)
    if prefs.target_locations and loc:
        hit = next(
            (
                t
                for t in prefs.target_locations
                if any(
                    normalize_text(t.get(k)) and normalize_text(t.get(k)) in loc
                    for k in ("city", "region")
                )
            ),
            None,
        )
        if hit:
            reasons.append({"kind": "match", "text": "Location is one of your targets"})
        elif "remote" in loc and "remote" in (prefs.work_modes or []):
            reasons.append({"kind": "match", "text": "Remote role and you accept remote work"})
        else:
            reasons.append({"kind": "mismatch", "text": "Location is not one of your targets"})
    if not reasons:
        reasons.append({"kind": "info", "text": "No preference rules applied to this job yet."})
    return reasons
