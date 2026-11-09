"""D113: the owner's standing rule to apply automatically.

The owner chose "Fully automatic" on 2026-11-02: "Discover, fill and submit without asking you,
for fully answered packages only, within a daily cap and your recorded permission." This module
is that rule, and nothing wider. A worker task (`tick`) runs it for the pilot's owner only:

  * only where the Greenhouse pilot itself may act: switched on, production, container isolation,
    the owner's account, the owner's recorded permission for every step (app/core/authorizations,
    with its end date and its attempt limit), and the owner has not paused the rule in the app;
  * only for a job whose address is a Greenhouse job post the pilot accepts, not closed, excluded
    or a possible duplicate, with no checked preference unmet;
  * only for a package with every answer resolved from the owner's own approved facts, answers
    and documents: nothing open, nothing awaiting consent, no control NoEfforts cannot fill;
  * the first application to each employer path is a rehearsal (E6: fill and check, never
    submit); a submission follows only once that rehearsal held;
  * at most `auto_apply_daily_cap` approvals a day; never a retry of an attempt that stopped,
    failed or ended with an unknown outcome (those wait for the owner).

Each approval it gives is the same approval the owner gives in the app (exact version and content
hash), recorded with the rule as its reason, and every gate still checks it. Each thing the rule
does or declines is an `AutoApplyEvent` with a fixed reason code, shown to the owner.
"""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import authorizations
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.applications.service import transition
from app.modules.applications.states import Actor, AppState
from app.modules.audit.service import record
from app.modules.autoapply.models import AutoApplyEvent, AutoApplyPrefs
from app.modules.execution import live
from app.modules.execution.models import AttemptState, ExecutionAttempt
from app.modules.identity.models import User
from app.modules.jobs.models import Job, JobStatus

log = logging.getLogger(__name__)

RULE = "D113"
# D114: what an account agrees to when it turns the rule on (shown before it does).
CONSENT_TEXT = (
    "NoEfforts approves and submits, in your name, Greenhouse applications whose every answer "
    "comes from your own approved profile, saved answers and documents. Anything open waits for "
    "you; the first application to each employer is a rehearsal that never submits; at most "
    "the daily limit; an attempt that stops is never retried. Pause it here at any time."
)
QUEUE_REASON = "automatic: the owner's standing rule (D113)"
APPROVED = ("approved_rehearsal", "approved_submit")
# Fixed reason codes, each with the words the owner sees.
REASONS = {
    "rehearsal_queued": "A rehearsal (fill and check, never submit) was queued: the first "
    "application to this employer.",
    "submission_queued": "The submission was queued: this employer's rehearsal held.",
    "capture_failed": "The job post could not be read as NoEfforts can map it; it waits for you.",
    "open_questions": "Some questions need your answer; it continues once they are answered.",
    "checkpoint": "The form has a control NoEfforts cannot fill; apply on the employer's site.",
    "job_signal": "The job is closed, excluded or may duplicate another application.",
    "preferences_not_met": "One of your checked preferences is not met, so it was not applied to.",
    "daily_cap": "Today's automatic applications are used up; it continues tomorrow.",
    "permission_limit": "Your recorded permission's attempts are used up; renew it to continue.",
    "attempt_stopped": "The last attempt stopped or its outcome is unknown; it is never retried "
    "automatically.",
    # D132: continuing after a form change is the owner's decision, not the rule's.
    "form_changed": "The employer's form changed during an attempt; automatic applying leaves "
    "this application to you.",
    # D134: an application whose approval you revoked is yours from then on.
    "owner_revoked": "You revoked this application's approval; automatic applying leaves it "
    "to you.",
    "approval_refused": "NoEfforts could not approve this package automatically.",
    "queue_refused": "The approved package could not be queued.",
}
# Network reads (capturing a job post) are tried at most once a day per job.
RECAPTURE_AFTER = timedelta(hours=24)
# How many jobs one tick examines per owner.
JOBS_PER_TICK = 25
# An attempt in one of these states holds the application; nothing new is queued meanwhile.
HELD = (
    AttemptState.pending,
    AttemptState.claimed,
    AttemptState.sending,
    AttemptState.awaiting_code,
)
# The application already went as far as it can without the owner.
FINAL_STATES = (
    AppState.submitted_confirmed,
    AppState.submitted_unconfirmed,
    AppState.failed_terminal,
    AppState.failed_retryable,
    AppState.cancelled,
    AppState.expired,
)


def paused(db: Session, user: User) -> bool:
    """The account's own choice. With none recorded: on for the server owner, who chose it
    (D113); off for every other account until that account turns it on (D114): applying in
    someone's name needs that person's own choice, never only the server owner's."""
    from app.core.accounts import owner

    row = db.get(AutoApplyPrefs, user.id)
    if row is None:
        return not owner(user.email)
    return bool(row.paused)


# D134: one account's pause and its rule's work on each job are serialized (pg advisory lock,
# this class and the account): a pause waits for a job being approved and queued, then stops it.
_RULE_LOCK = 7_402_113


def _hold(db: Session, user_id, exclusive: bool = False) -> None:
    fn = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    key = int.from_bytes(uuid.UUID(str(user_id)).bytes[:4], "big", signed=True)
    db.execute(text(f"SELECT {fn}(:c, :k)"), {"c": _RULE_LOCK, "k": key})


def set_paused(db: Session, user_id, value: bool) -> dict | None:
    """Pause or resume the account's rule. D134: pausing also stops what the rule queued that
    has not started sending (execution.service.stop_for_pause) and retires the approvals it
    gave; it returns what it stopped."""
    from app.modules.execution.service import stop_for_pause
    from app.modules.preparation import package as pk

    if value:
        _hold(db, user_id, exclusive=True)
    row = db.get(AutoApplyPrefs, user_id)
    if row is None:
        row = AutoApplyPrefs(user_id=user_id)
        db.add(row)
    row.paused, row.updated_at = value, utcnow()
    if not value:
        record(db, user_id, "auto_apply.resumed", "user", user_id)
        return None
    db.flush()
    stopped = stop_for_pause(db, user_id) | {"approvals": pk.retire_rule_approvals(db, user_id)}
    record(db, user_id, "auto_apply.paused", "user", user_id, cancelled=stopped["cancelled"],
           stopped=stopped["stopped"], in_flight=stopped["in_flight"],
           approvals=stopped["approvals"])  # fmt: skip
    return stopped


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(UTC).date(), time.min, UTC)


def approved_today(db: Session, user_id, now: datetime | None = None) -> int:
    now = now or utcnow()
    return int(
        db.scalar(
            select(func.count())
            .select_from(AutoApplyEvent)
            .where(
                AutoApplyEvent.user_id == user_id,
                AutoApplyEvent.action.in_(APPROVED),
                AutoApplyEvent.created_at >= _day_start(now),
            )
        )
        or 0
    )


def owner_refusal(user: User) -> str | None:
    """Why the rule cannot act for this account now (a fixed code), or None."""
    if not get_settings().auto_apply_enabled:
        return "rule_off"
    return live.refusal(user)  # switch, environment, owner, every recorded permission


def _last_event(db: Session, job_id) -> AutoApplyEvent | None:
    return db.scalar(
        select(AutoApplyEvent)
        .where(AutoApplyEvent.job_id == job_id)
        .order_by(AutoApplyEvent.created_at.desc())
        .limit(1)
    )


def _note(db: Session, user_id, job: Job, app: Application | None, action: str, reason: str):
    """Record what the rule did. A skip already recorded last for this job is not repeated."""
    last = _last_event(db, job.id)
    if action == "skipped" and last is not None and (last.action, last.reason) == (action, reason):
        return
    db.add(AutoApplyEvent(user_id=user_id, job_id=job.id,
                          application_id=app.id if app else None, action=action,
                          reason=reason))  # fmt: skip
    record(db, user_id, f"auto_apply.{action}", "job", job.id, reason_code=reason)


def _candidates(db: Session, user: User) -> list[Job]:
    jobs = db.scalars(
        select(Job)
        .where(
            Job.user_id == user.id,
            Job.url.is_not(None),
            Job.status.notin_((JobStatus.excluded, JobStatus.closed)),
        )
        .order_by(Job.created_at.desc())
        .limit(JOBS_PER_TICK * 4)
    ).all()
    return [j for j in jobs if live.posting(j.url) is not None][:JOBS_PER_TICK]


def _application(db: Session, user: User, job: Job) -> Application | None:
    return db.scalar(
        select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
    )


def _new_application(db: Session, user: User, job: Job) -> Application:
    now = utcnow()
    app = Application(user_id=user.id, job_id=job.id, state=AppState.draft,
                      state_changed_at=now)  # fmt: skip
    db.add(app)
    db.flush()
    record(db, user.id, "application.create", "application", app.id, by=RULE)
    return app


def _latest_attempt(db: Session, app: Application) -> ExecutionAttempt | None:
    return db.scalar(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app.id)
        .order_by(ExecutionAttempt.created_at.desc())
        .limit(1)
    )


def _preferences_unmet(db: Session, user: User, job: Job) -> bool:
    """Any of the owner's checked preferences explicitly not met by this job (jobs/fit.py)."""
    from app.modules.jobs import fit
    from app.modules.jobs.router import _fit
    from app.modules.profiles.models import JobPreferences

    prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == user.id))
    assessment = _fit(db, user, job, prefs)
    return any(p.get("result") == fit.NOT_MET for p in assessment["preferences"])


def _capture(db: Session, user: User, job: Job) -> bool:
    """Read the job post through the pilot (permission 1), as the job page's button does."""
    from app.modules.preparation.router import _capture_live

    try:
        _capture_live(db, user, job, job.url, live.posting(job.url))
    except HTTPException:
        db.rollback()
        return False
    return True


def _ever_paused(db: Session, app) -> bool:
    """D132: an application that ever stopped on a changed form is the owner's from then on,
    even after they answered and approved again (a pause resolved or not)."""
    from app.modules.execution.models import ApplicationPause

    return (
        db.scalar(
            select(ApplicationPause.id)
            .where(
                ApplicationPause.application_id == app.id,
                ApplicationPause.user_id == app.user_id,
            )
            .limit(1)
        )
        is not None
    )


def _paused_before_entry(db: Session, att: ExecutionAttempt) -> bool:
    """D134: an attempt your pause stopped before anything was entered is not a stop of the
    attempt's own: resumed, the rule continues the application. One stopped after entering
    something stays yours, like any other stop."""
    from app.modules.execution.models import AttemptEvent
    from app.modules.execution.service import PAUSE_STOPPED

    if att.state != AttemptState.cancelled or att.disclosure_started_at is not None:
        return False
    return (
        db.scalar(
            select(AttemptEvent.id)
            .where(AttemptEvent.attempt_id == att.id, AttemptEvent.kind == PAUSE_STOPPED)
            .limit(1)
        )
        is not None
    )


def _owner_revoked(db: Session, app) -> bool:
    """D134: an application whose approval you revoked is yours from then on: the rule never
    approves it again, whatever it queued or not (only you can)."""
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import PackageApproval

    return (
        db.scalar(
            select(PackageApproval.id)
            .where(
                PackageApproval.application_id == app.id,
                PackageApproval.user_id == app.user_id,
                PackageApproval.invalidation_reason == pk.REVOKED_BY_YOU,
            )
            .limit(1)
        )
        is not None
    )


def _advance(db: Session, user: User, job: Job, now: datetime) -> str | None:
    """One step for one job. Returns "approved" when it queued something, else None."""
    from app.modules.execution.rehearsal import RehearsalRequired
    from app.modules.execution.service import enqueue
    from app.modules.jobs import signals
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import ApprovalScope
    from app.modules.providers.routing import form_checkpoint

    app = _application(db, user, job)
    if app is not None:
        if app.state in FINAL_STATES:
            return None
        if _ever_paused(db, app):
            _note(db, user.id, job, app, "skipped", "form_changed")
            return None
        if _owner_revoked(db, app):
            _note(db, user.id, job, app, "skipped", "owner_revoked")
            return None
        att = _latest_attempt(db, app)
        if att is not None and att.state in HELD:
            return None
        if att is not None and att.state not in (AttemptState.rehearsed,):
            if att.state == AttemptState.confirmed:
                return None
            if not _paused_before_entry(db, att):
                _note(db, user.id, job, app, "skipped", "attempt_stopped")
                return None
    form = pk.latest_form(db, job.id)
    if form is None:
        last = _last_event(db, job.id)
        if (
            last is not None
            and last.reason == "capture_failed"
            and (now - last.created_at < RECAPTURE_AFTER)
        ):
            return None
        if not _capture(db, user, job):
            _note(db, user.id, job, None, "skipped", "capture_failed")
            return None
        # The capture committed, which ended this step's hold (run_for): hold again first.
        _hold(db, user.id)
        if paused(db, user):
            return None
        form = pk.latest_form(db, job.id)
    if form_checkpoint(form.schema):
        _note(db, user.id, job, app, "skipped", "checkpoint")
        return None
    if signals.approval_refusal(db, job) is not None:
        _note(db, user.id, job, app, "skipped", "job_signal")
        return None
    if _preferences_unmet(db, user, job):
        _note(db, user.id, job, app, "skipped", "preferences_not_met")
        return None
    if app is None:
        app = _new_application(db, user, job)
    try:
        pkg = pk.ensure_current(db, app)
    except pk.NoForm:
        _note(db, user.id, job, app, "skipped", "capture_failed")
        return None
    if pkg.content["unresolved"] or pkg.content["validation_errors"]:
        _note(db, user.id, job, app, "skipped", "open_questions")
        return None
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose")
    if cap is not None and live.attempts_used(db, cap[1]) >= cap[0]:
        _note(db, user.id, job, app, "skipped", "permission_limit")
        return None
    if approved_today(db, user.id, now) >= get_settings().auto_apply_daily_cap:
        _note(db, user.id, job, app, "skipped", "daily_cap")
        return None
    try:
        try:
            appr = pk.approve(
                db, app, pkg.version, pkg.content_hash, ApprovalScope.submit, by_rule=True
            )
        except RehearsalRequired:
            appr = pk.approve(
                db, app, pkg.version, pkg.content_hash, ApprovalScope.disclose_only, by_rule=True
            )
    except pk.ApprovalError:
        db.rollback()
        _note(db, user.id, job, app, "skipped", "approval_refused")
        return None
    rehearsal = str(getattr(appr.scope, "value", appr.scope)) == ApprovalScope.disclose_only.value
    try:
        with db.begin_nested():
            pk.require_valid_approval(db, app)
            transition(db, app, AppState.queued, Actor.user, QUEUE_REASON)
            enqueue(db, app).queued_by_rule = True
    except Exception:  # noqa: BLE001 - any refusal leaves nothing queued; it waits for the owner
        log.info("auto-apply: queueing refused (job kept for the owner)")
        _note(db, user.id, job, app, "skipped", "queue_refused")
        return None
    _note(db, user.id, job, app, "approved_rehearsal" if rehearsal else "approved_submit",
          "rehearsal_queued" if rehearsal else "submission_queued")  # fmt: skip
    record(db, user.id, "application.transition", "application", app.id, to="queued", by=RULE)
    return "approved"


def run_for(db: Session, user: User, now: datetime | None = None) -> int:
    """The rule for one account; how many applications it queued."""
    now = now or utcnow()
    if owner_refusal(user) or paused(db, user):
        return 0
    queued = 0
    for job in _candidates(db, user):
        try:
            # D134: before any row lock, as a pause takes it (exclusive): a pause recorded while
            # this tick runs waits for this job's step, and every later step reads it.
            _hold(db, user.id)
            if paused(db, user):
                db.rollback()
                break
            if _advance(db, user, job, now) == "approved":
                queued += 1
            db.commit()
        except Exception:  # noqa: BLE001 - one job's failure never stops the others
            db.rollback()
            log.exception("auto-apply: a job could not be examined")
    return queued


def tick(now: datetime | None = None) -> int:
    """The worker task: the rule for the pilot's owner(s). Does nothing unless the rule is on and
    the pilot may act on this server."""
    s = get_settings()
    if not s.auto_apply_enabled or live.environment_refusal() is not None:
        return 0
    owners = {e.strip().lower() for e in s.live_owner_emails if e.strip()}
    total = 0
    with SessionLocal() as db:
        if s.all_accounts:  # D114: every account; each acts only if not paused (its choice)
            users = db.scalars(select(User)).all()
        else:
            users = db.scalars(select(User).where(func.lower(User.email).in_(owners))).all()
        for user in users:
            total += run_for(db, user, now)
    return total
