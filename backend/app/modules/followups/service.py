"""Follow-ups (D92): a reminder to check on an application you submitted, derived from its own
records every time, so it changes when they change and never says more than they do.

When one is due:
  * only after the application entered a submitted state (by an employer receipt, or because
    you recorded that you applied yourself): never before;
  * `settings.follow_up_days` (default 7) after the latest of: the day it was first submitted,
    the day you last said you followed up, and the day of an outcome that keeps it open
    (an assessment or an interview you recorded);
  * or on the day you chose ("remind me on"), until you next say you followed up;
  * never once the outcome closes it (an offer, a rejection, a withdrawal, or "no response"
    that you recorded), and never while you have stopped the reminders.
Stored (models.FollowUp): only those choices of yours. Nothing here sends anything: the message
is a draft for you to copy, made from the job and your approved name, never sent by NoEfforts."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.applications import states
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.states import Outcome
from app.modules.followups.models import FollowUp
from app.modules.jobs.models import Job
from app.modules.profiles.models import CandidateProfile

# Outcomes after which following up still makes sense; every other recorded outcome closes it.
OPEN_OUTCOMES = frozenset({Outcome.none, Outcome.assessment_received, Outcome.interviewing})
MAX_REMIND_AHEAD_DAYS = 365


def today() -> date:
    return datetime.now(UTC).date()


def _submitted_on(db: Session, user_id, app_ids=None) -> dict[uuid.UUID, date]:
    """The day each application first entered a submitted state, from its insert-only
    timeline. Scoped to the account."""
    q = (
        select(ApplicationEvent.application_id, func.min(ApplicationEvent.created_at))
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(
            Application.user_id == user_id,
            ApplicationEvent.kind == "state_change",
            ApplicationEvent.to_state.in_(states.SUBMITTED),
        )
        .group_by(ApplicationEvent.application_id)
    )
    if app_ids is not None:
        q = q.where(ApplicationEvent.application_id.in_(app_ids))
    return {a: at.astimezone(UTC).date() for a, at in db.execute(q)}


def _outcome_on(db: Session, user_id, app_ids) -> dict[uuid.UUID, date]:
    """The day of each application's latest outcome event: the day you said the employer acted,
    else the day you recorded it."""
    rows = db.execute(
        select(
            ApplicationEvent.application_id,
            ApplicationEvent.occurred_on,
            ApplicationEvent.created_at,
        )
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(
            Application.user_id == user_id,
            ApplicationEvent.kind == "outcome",
            ApplicationEvent.application_id.in_(app_ids),
        )
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    )
    out = {}
    for app_id, occurred_on, created_at in rows:
        out[app_id] = occurred_on or created_at.astimezone(UTC).date()
    return out


def evaluate(app: Application, submitted_on, outcome_on, choice: FollowUp | None, now: date):
    """The follow-up of one application as of `now`: a dict, or None before any submission."""
    if submitted_on is None:
        return None
    days = get_settings().follow_up_days
    followed_up_on = choice.followed_up_on if choice else None
    remind_on = choice.remind_on if choice else None
    stopped = bool(choice and choice.stopped)
    open_ = app.outcome in OPEN_OUTCOMES
    base = max(
        d
        for d in (
            submitted_on,
            followed_up_on,
            outcome_on if app.outcome != Outcome.none else None,
        )
        if d is not None
    )
    due_on = remind_on or base + timedelta(days=days)
    if not open_:
        status = "closed"
    elif stopped:
        status = "stopped"
    else:
        status = "due" if due_on <= now else "scheduled"
    return {
        "application_id": str(app.id),
        "status": status,
        "due_on": due_on if status in ("due", "scheduled") else None,
        "submitted_on": submitted_on,
        "followed_up_on": followed_up_on,
        "remind_on": remind_on,
        "stopped": stopped,
        "outcome": app.outcome.value,
        "days": days,
    }


def for_user(db: Session, user_id, now: date | None = None) -> list[dict]:
    """Every follow-up of the account's submitted applications, soonest first, each with the
    job it concerns. Scoped to the account in every query."""
    now = now or today()
    submitted = _submitted_on(db, user_id)
    if not submitted:
        return []
    rows = db.execute(
        select(Application, Job.title, Job.employer)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user_id, Application.id.in_(submitted))
    ).all()
    outcome_on = _outcome_on(db, user_id, list(submitted))
    choices = {
        c.application_id: c
        for c in db.scalars(
            select(FollowUp).where(
                FollowUp.user_id == user_id, FollowUp.application_id.in_(submitted)
            )
        )
    }
    out = []
    for app, title, employer in rows:
        item = evaluate(app, submitted[app.id], outcome_on.get(app.id), choices.get(app.id), now)
        item["job"] = " — ".join(x for x in (title or "Untitled role", employer) if x)
        out.append(item)
    order = {"due": 0, "scheduled": 1, "stopped": 2, "closed": 3}
    return sorted(out, key=lambda i: (order[i["status"]], i["due_on"] or date.max, i["job"]))


def for_application(db: Session, app: Application, now: date | None = None) -> dict | None:
    """The caller checked ownership."""
    now = now or today()
    submitted = _submitted_on(db, app.user_id, [app.id]).get(app.id)
    if submitted is None:
        return None
    outcome_on = _outcome_on(db, app.user_id, [app.id]).get(app.id)
    choice = db.scalar(
        select(FollowUp).where(FollowUp.user_id == app.user_id, FollowUp.application_id == app.id)
    )
    return evaluate(app, submitted, outcome_on, choice, now)


def due_at(item: dict) -> datetime:
    return datetime.combine(item["due_on"], time.min, tzinfo=UTC)


def _long_date(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def draft(db: Session, app: Application, item: dict) -> dict:
    """A message to copy, never sent: the job's title and employer, the day you applied, and
    your name as approved in your profile (a placeholder when you have none). Nothing else of
    yours, and no claim about you beyond the outcome you recorded."""
    job = db.get(Job, app.job_id)
    role = (job.title if job else None) or "the role"
    employer = job.employer if job else None
    at = f" at {employer}" if employer else ""
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == app.user_id))
    name = (profile.full_name or "").strip() if profile else ""
    applied = _long_date(item["submitted_on"])
    if app.outcome == Outcome.interviewing:
        subject = f"Following up on my interview: {role}"
        opening = (
            f"Thank you again for the opportunity to interview for the {role} position{at}. "
            "I wanted to follow up and ask whether there is any update."
        )
    elif app.outcome == Outcome.assessment_received:
        subject = f"Following up on my application: {role}"
        opening = (
            f"I am following up on my application for the {role} position{at} and the "
            "assessment that was part of it. Could you let me know whether there is any update?"
        )
    else:
        subject = f"Following up on my application: {role}"
        opening = (
            f"I applied for the {role} position{at} on {applied}. I am following up to ask "
            "whether there is any update on my application."
        )
    body = (
        f"Hello,\n\n{opening}\n\nThank you for your time.\n\nKind regards,\n{name or '[Your name]'}"
    )
    return {"subject": subject, "body": body, "name_missing": not name}
