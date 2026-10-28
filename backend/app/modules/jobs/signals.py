"""S3 (D59): what is known about a job that should stop an approval, shown before any disclosure.

* Source says closed: a discovered posting linked to the job was reported closed, or gone (a
  404), by its source. The job itself is never changed (discovery never edits a tracker job);
  the signal is read from the discovered rows. "Still open", your audited statement, answers it
  until the source reports it closed again after that statement.
* Excluded or closed by you: the job's own status.
* Possible duplicate: another of your jobs with the same employer and title (and the same
  location when both have one) has an application past draft. Never merged. "A different
  role", your audited statement, answers the applications known at that moment.

Preparation is never blocked; approval is refused with a fixed reason code until the signal is
answered. Every query is scoped to the job's own user."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.applications.models import Application
from app.modules.applications.states import AppState
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import PROVIDERS
from app.modules.jobs.canonical import normalize_text
from app.modules.jobs.models import Job, JobStatus

# Reason codes, checked in this order (docs/job-signals.md lists exactly these).
REASONS = {
    "job_excluded": "You excluded this job. Change its status on the job page before approving "
    "an application to it.",
    "job_closed_by_you": "You marked this job closed. Change its status on the job page before "
    "approving an application to it.",
    "job_source_closed": "Its source says this posting is closed or gone. If it is still open, "
    "say so on the job page, then approve.",
    "job_possible_duplicate": "It looks like a role you already have an application for (same "
    "employer and title). If it is a different role, say so on the job page, then approve.",
}
CLOSED_REASONS = ("closed at source", "no longer at the source")


def refusal(code: str) -> str:
    return f"{REASONS[code]} (reason: {code})"


def source_closed(db: Session, job: Job) -> dict | None:
    """The latest report, by a linked discovered posting, that the source closed it, unless your
    "still open" statement is later than that report."""
    rows = db.scalars(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == job.user_id,
            DiscoveredJob.job_id == job.id,
            DiscoveredJob.stale.is_(True),
            DiscoveredJob.stale_reason.in_(CLOSED_REASONS),
        )
    ).all()
    seen = [
        r
        for r in rows
        if job.open_confirmed_at is None
        or r.stale_since is None
        or r.stale_since > job.open_confirmed_at
    ]
    if not seen:
        return None
    r = max(seen, key=lambda x: x.stale_since or x.last_seen_at)
    cls = PROVIDERS.get(r.provider)
    return {
        "provider": r.provider,
        "provider_label": cls.label if cls else r.provider,
        "reason": r.stale_reason,
        "since": (r.stale_since or r.last_seen_at).isoformat(),
    }


def _same_role(a: Job, b: Job) -> bool:
    if not a.employer_key or a.employer_key != b.employer_key:
        return False
    if not normalize_text(a.title) or normalize_text(a.title) != normalize_text(b.title):
        return False
    la, lb = normalize_text(a.location), normalize_text(b.location)
    return not (la and lb) or la == lb


def _applied(db: Session, user_id, employer_key: str | None = None) -> list:
    """Your jobs with an application past draft, with that application."""
    q = (
        select(Job, Application)
        .join(Application, Application.job_id == Job.id)
        .where(
            Job.user_id == user_id,
            Application.user_id == user_id,
            Application.state != AppState.draft,
        )
    )
    if employer_key is not None:
        q = q.where(Job.employer_key == employer_key)
    return db.execute(q.order_by(Application.created_at)).all()


def _duplicates(job: Job, applied: list) -> list[dict]:
    return [
        {
            "job_id": str(other.id),
            "title": other.title,
            "employer": other.employer,
            "location": other.location,
            "application_id": str(app.id),
            "state": app.state.value,
            "outcome": app.outcome.value,
        }
        for other, app in applied
        if other.id != job.id
        and _same_role(job, other)
        and (job.distinct_confirmed_at is None or app.created_at > job.distinct_confirmed_at)
    ]


def possible_duplicates(db: Session, job: Job) -> list[dict]:
    """Your other jobs for the same role that have an application past draft, with its state and
    outcome; those already answered by "a different role" are left out."""
    if not job.employer_key or not normalize_text(job.title):
        return []
    return _duplicates(job, _applied(db, job.user_id, job.employer_key))


def for_rows(db: Session, user_id, jobs: list[Job]) -> dict:
    """For a list (the Discover page): each job's own application and how many possible
    duplicates it has, in two queries."""
    applied = _applied(db, user_id)
    own = {
        a.job_id: a
        for a in db.scalars(
            select(Application).where(
                Application.user_id == user_id, Application.job_id.in_([j.id for j in jobs])
            )
        )
    }
    return {
        j.id: {
            "application": {"state": own[j.id].state.value, "outcome": own[j.id].outcome.value}
            if j.id in own
            else None,
            "possible_duplicates": len(_duplicates(j, applied)),
        }
        for j in jobs
    }


def approval_refusal(db: Session, job: Job) -> str | None:
    if job.status == JobStatus.excluded:
        return "job_excluded"
    if job.status == JobStatus.closed:
        return "job_closed_by_you"
    if source_closed(db, job) is not None:
        return "job_source_closed"
    if possible_duplicates(db, job):
        return "job_possible_duplicate"
    return None


def view(db: Session, job: Job) -> dict:
    code = approval_refusal(db, job)
    return {
        "source_closed": source_closed(db, job),
        "possible_duplicates": possible_duplicates(db, job),
        "open_confirmed_at": job.open_confirmed_at.isoformat() if job.open_confirmed_at else None,
        "distinct_confirmed_at": job.distinct_confirmed_at.isoformat()
        if job.distinct_confirmed_at
        else None,
        "approval_blocked": {"code": code, "message": REASONS[code]} if code else None,
    }
