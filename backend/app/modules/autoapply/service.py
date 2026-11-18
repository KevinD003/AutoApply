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
    failed or ended with an unknown outcome (those wait for the owner). D169: for the owner's
    own accounts, an attempt the employer's changed form stopped before anything was entered is
    continued (the form read again; a version tried once more; at most `FORM_STOPS` stops),
    never one that entered anything. D170: whatever its job's age; what is shown as the owner's
    stays theirs (`verdict`); a job its signals or the owner's preferences rule out is declined
    before its post is read, and a paused one waits until that changes.

Each approval it gives is the same approval the owner gives in the app (exact version and content
hash), recorded with the rule as its reason, and every gate still checks it. Each thing the rule
does or declines is an `AutoApplyEvent` with a fixed reason code, shown to the owner.
"""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta

from celery.exceptions import SoftTimeLimitExceeded
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
from app.modules.execution import live, restore
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
    "capture_failed": "The job post could not be read as NoEfforts can map it; it is read again a "
    "day later.",
    "open_questions": "Some questions need your answer; it continues once they are answered.",
    "checkpoint": "The form has a control NoEfforts cannot fill; apply on the employer's site.",
    "job_signal": "The job is closed, excluded or may duplicate another application.",
    "preferences_not_met": "One of your checked preferences is not met, so it was not applied to.",
    "daily_cap": "Today's automatic applications are used up; it continues tomorrow.",
    "permission_limit": "Your recorded permission's attempts are used up; renew it to continue.",
    "attempt_stopped": "The last attempt stopped or its outcome is unknown; it is never retried "
    "automatically.",
    # D132: the rule never continued an application that paused; kept with these words for every
    # event recorded so, and for an account that is not the owner's (D169 below is the owner's).
    "form_changed": "The employer's form changed during an attempt; automatic applying leaves "
    "this application to you.",
    # D169: for the owner's accounts the rule continues after a form change (the form read
    # again; finding no difference, that version tried once more), within FORM_STOPS.
    "form_read_again": "The employer's form changed; NoEfforts read it again and continues with "
    "it (nothing had been entered).",
    "form_tried_again": "The employer's page differed from its form, but reading it again found no "
    "change; NoEfforts tries it once more (the page is checked before anything is entered).",
    "form_kept_changing": "The employer's page kept differing from its form as NoEfforts reads "
    "it, so automatic applying stopped trying; this application is yours to continue.",
    # D135, D169: an attempt that entered your data and did not end as a rehearsal or a
    # submission is never followed by the rule (CLAUDE.md: no retry after disclosure).
    "stopped_after_entry": "An attempt stopped after entering your data on the employer's page; "
    "automatic applying never enters it a second time, so it is yours.",
    # D134: an application whose approval you revoked is yours from then on.
    "owner_revoked": "You revoked this application's approval; automatic applying leaves it "
    "to you.",
    # D147: the server was restored from a backup after this application began; what happened
    # to it after that backup is not recorded here, so only you can continue it.
    "restored_from_backup": "This server was restored from a backup after this application "
    "began; automatic applying leaves it to you.",
    "approval_refused": "NoEfforts could not approve this package automatically.",
    "queue_refused": "The approved package could not be queued.",
}
# Network reads (capturing a job post) are tried at most once a day per job.
RECAPTURE_AFTER = timedelta(hours=24)
# D169: the rule continues an application after at most this many stops on a changed form; a
# page that keeps differing is the owner's (each stop came before anything was entered).
FORM_STOPS = 3
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

    # As it is now, not as this session last saw it (D169); so never between changing the row
    # and committing it (the change would be read over).
    row = db.get(AutoApplyPrefs, user.id, populate_existing=True)
    if row is None:
        return not owner(user.email)
    return bool(row.paused)


# D134: one account's pause and its rule's work on each job are serialized (pg advisory lock,
# this class and the account): a pause waits for a job being approved and queued, then stops it.
_RULE_LOCK = 7_402_113
# D168: in sole-owner mode one daily cap counts every account's approvals; one account's step at
# a time from that count to its approval (this class, key 0), released when the step commits.
# Taken last, after the account's own lock and its application's row lock. Only rule steps take
# it, each holding only its own account's rows, so a step waiting for it holds nothing a step
# holding it needs.
_CAP_LOCK = 7_402_168


def _hold(db: Session, user_id, exclusive: bool = False) -> None:
    fn = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    key = int.from_bytes(uuid.UUID(str(user_id)).bytes[:4], "big", signed=True)
    db.execute(text(f"SELECT {fn}(:c, :k)"), {"c": _RULE_LOCK, "k": key})


def set_paused(db: Session, user_id, value: bool, reason_code: str | None = None) -> dict | None:
    """Pause or resume the account's rule. D134: pausing also stops what the rule queued that
    has not started sending (execution.service.stop_for_pause) and retires the approvals it
    gave; it returns what it stopped. `reason_code`: a pause NoEfforts made, not the account
    (D147: `restored_from_backup`), recorded with it. D147: while the database is held after a
    restore it only pauses: what the rule queued is the resolver's to end, as an unknown
    outcome, and every approval is retired then."""
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
    if restore.held(db):  # D147: what the backup shows in progress is the resolver's to end
        stopped = {"cancelled": 0, "stopped": 0, "in_flight": 0, "approvals": 0}
    else:
        stopped = stop_for_pause(db, user_id) | {"approvals": pk.retire_rule_approvals(db, user_id)}
    counts = {k: stopped[k] for k in ("cancelled", "stopped", "in_flight", "approvals")}
    if reason_code:  # D147: NoEfforts paused it, not the account
        record(db, user_id, "auto_apply.paused", "user", user_id, cancelled=counts["cancelled"],
               stopped=counts["stopped"], in_flight=counts["in_flight"],
               approvals=counts["approvals"], reason_code=reason_code)  # fmt: skip
    else:
        record(db, user_id, "auto_apply.paused", "user", user_id, cancelled=counts["cancelled"],
               stopped=counts["stopped"], in_flight=counts["in_flight"],
               approvals=counts["approvals"])  # fmt: skip
    return stopped


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(UTC).date(), time.min, UTC)


def approved_today(db: Session, user_id, now: datetime | None = None) -> int:
    """The rule's approvals today: this account's, or every account's when `user_id` is None."""
    now = now or utcnow()
    q = (
        select(func.count())
        .select_from(AutoApplyEvent)
        .where(AutoApplyEvent.action.in_(APPROVED), AutoApplyEvent.created_at >= _day_start(now))
    )
    if user_id is not None:
        q = q.where(AutoApplyEvent.user_id == user_id)
    return int(db.scalar(q) or 0)


def cap_used(db: Session, user_id, now: datetime | None = None) -> int:
    """What counts against the daily cap today: this account's approvals, or in sole-owner mode
    (D168: every account is the owner's, and the cap is the owner's) every account's."""
    return approved_today(db, None if get_settings().sole_owner else user_id, now)


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


def _read_failed_recently(db: Session, job: Job, now: datetime) -> bool:
    """A read of this job's post failed less than RECAPTURE_AFTER ago: not read again yet."""
    at = db.scalar(
        select(func.max(AutoApplyEvent.created_at)).where(
            AutoApplyEvent.job_id == job.id,
            AutoApplyEvent.user_id == job.user_id,
            AutoApplyEvent.reason == "capture_failed",
        )
    )
    return at is not None and now - at < RECAPTURE_AFTER


def _note(db: Session, user_id, job: Job, app: Application | None, action: str, reason: str):
    """Record what the rule did. A skip already recorded last for this job is not repeated, but a
    failed read always is: the once-a-day limit on reads counts from the last one (D169)."""
    last = _last_event(db, job.id)
    if (
        action == "skipped"
        and reason != "capture_failed"
        and last is not None
        and (last.action, last.reason) == (action, reason)
    ):
        return
    db.add(AutoApplyEvent(user_id=user_id, job_id=job.id,
                          application_id=app.id if app else None, action=action,
                          reason=reason))  # fmt: skip
    record(db, user_id, f"auto_apply.{action}", "job", job.id, reason_code=reason)
    db.flush()  # D169: the step's next note compares with this one (the session never autoflushes)


def _candidates(db: Session, user: User) -> list[Job]:
    """The jobs the rule examines: D170, first every job whose application ever paused on a
    changed form and is not final, whatever the job's age or state, then the newest it may apply
    to (`JOBS_PER_TICK` of them). The owner is told the rule continues such an application, and
    not to apply on the employer's site meanwhile (`verdict`), also once its pause has ended (the
    rule's own read or try ends it): the window never decides it, since newer jobs pushing it out
    would stall it and closing them would bring it back, sent long after the owner may have given
    up and applied by hand. First, so a tick that runs out of time (the task's soft limit) reading
    new posts never leaves them behind."""
    from app.modules.execution.models import ApplicationPause

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
    newest = [j for j in jobs if live.posting(j.url) is not None][:JOBS_PER_TICK]
    paused_once = (
        select(ApplicationPause.id)
        .where(
            ApplicationPause.application_id == Application.id,
            ApplicationPause.user_id == user.id,
            ApplicationPause.kind == "form_changed",
        )
        .exists()
    )
    waiting = db.scalars(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(
            Job.user_id == user.id,
            Job.url.is_not(None),
            Application.user_id == user.id,
            Application.state.notin_(FINAL_STATES),
            paused_once,
        )
        .order_by(Application.created_at)
    ).all()
    first = [j for j in waiting if live.posting(j.url) is not None]
    firsts = {j.id for j in first}
    return first + [j for j in newest if j.id not in firsts]


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


def _declined(db: Session, user: User, job: Job) -> str | None:
    """D170: why the rule never applies to this job (a reason code), whatever it has read of it:
    its signals (closed, excluded, a possible duplicate) or a checked preference it does not meet.
    Judged before the job's post is read, so a job the rule declines is never read for it."""
    from app.modules.jobs import signals

    job = db.get(Job, job.id, populate_existing=True)  # as it is now, not as this tick began
    if job is None or signals.approval_refusal(db, job) is not None:
        return "job_signal"
    if _preferences_unmet(db, user, job):
        return "preferences_not_met"
    return None


def _preferences_unmet(db: Session, user: User, job: Job) -> bool:
    """Any of the owner's checked preferences explicitly not met by this job (jobs/fit.py)."""
    from app.modules.jobs import fit
    from app.modules.jobs.router import _fit
    from app.modules.profiles.models import JobPreferences

    prefs = db.scalar(
        select(JobPreferences)
        .where(JobPreferences.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    assessment = _fit(db, user, job, prefs)
    return any(p.get("result") == fit.NOT_MET for p in assessment["preferences"])


def _may_read(user: User) -> bool:
    """D170: the recorded permission covers reading as it is now, not as the tick began (a tick
    can outlast a permission's last day)."""
    return live.refusal(user, ("read",)) is None


def _capture(db: Session, user: User, job: Job) -> bool:
    """Read the job post through the pilot (permission 1), as the job page's button does."""
    from app.modules.preparation.router import _capture_live

    try:
        _capture_live(db, user, job, job.url, live.posting(job.url))
    except HTTPException:
        db.rollback()
        return False
    return True


def _pauses(db: Session, app) -> list:
    from app.modules.execution.models import ApplicationPause

    return db.scalars(
        select(ApplicationPause)
        .where(ApplicationPause.application_id == app.id, ApplicationPause.user_id == app.user_id)
        .order_by(ApplicationPause.created_at)
    ).all()


def _entered(db: Session, app) -> bool:
    """An attempt of this application entered the owner's data on the employer's page and did not
    end as a rehearsal or a confirmed submission (D135's pause after filling among them)."""
    return (
        db.scalar(
            select(ExecutionAttempt.id)
            .where(
                ExecutionAttempt.application_id == app.id,
                ExecutionAttempt.user_id == app.user_id,
                ExecutionAttempt.disclosure_started_at.is_not(None),
                ExecutionAttempt.state.notin_((AttemptState.rehearsed, AttemptState.confirmed)),
            )
            .limit(1)
        )
        is not None
    )


def _handed_to_you(db: Session, app) -> bool:
    """D132 left this application to the owner (an event recorded so: by the rule before D169, or
    by D170's upgrade for every application that had paused before it): it stays theirs, as
    D132 said; they may have applied on the employer's site meanwhile."""
    return (
        db.scalar(
            select(AutoApplyEvent.id)
            .where(
                AutoApplyEvent.application_id == app.id,
                AutoApplyEvent.user_id == app.user_id,
                AutoApplyEvent.reason == "form_changed",
            )
            .limit(1)
        )
        is not None
    )


def _unresolved(pauses: list):
    """The pause that still waits (open or unexplained; at most one, by a partial unique index),
    whatever order the workers' clocks gave the rest."""
    from app.modules.execution.models import PAUSE_UNRESOLVED

    return next((p for p in pauses if p.status in PAUSE_UNRESOLVED), None)


def _yours(db: Session, user: User, app, pauses: list) -> str | None:
    """D169: why an application that paused is the owner's (a reason code), or None while the rule
    may continue it. D170: each reason is for good, so what is shown as the owner's stays theirs
    (D132's words promise "nothing is sent until you do")."""

    if _entered(db, app):  # D135's pause after filling among them
        return "stopped_after_entry"  # never entered a second time by the rule
    if _handed_to_you(db, app):
        # D132's rule: D132 handed it over, or the account was not the owner's when it paused
        # (recorded with the pause, execution `_hand_over_unless_owner`); never re-derived from
        # the server's settings as they are now, which may change back (D170).
        return "form_changed"
    if _kept_changing(pauses):
        return "form_kept_changing"
    return None


def _kept_changing(pauses: list) -> bool:
    """D169: the employer's page kept differing from its form as NoEfforts reads it: more than
    FORM_STOPS stops, or a read finding no difference on a second stop on a form version already
    tried once more (by the rule or the owner); a visible change made since (a new question) is
    continued. D170: judged only from what no later step changes (the stops, each one's form
    version, a try once more, which is final, and `unexplained_at`, never cleared), so what is
    shown as the owner's stays theirs: neither the owner's own read nor their own try hands it
    back. (D169 judged by `recaptured_version`, which a later read finding a new version
    overwrites.)"""
    if len(pauses) > FORM_STOPS:
        return True
    tried = [q for q in pauses if q.resolution == "dismissed"]
    return any(
        p.unexplained_at is not None
        and any(q is not p and q.form_version == p.form_version for q in tried)
        for p in pauses
    )


def _lock_pause(db: Session, job: Job, app):
    """The application's unresolved pause as it is now, under its locks, taken in the order a form
    read takes them: the job's row (key share: the rule's notes reference it, a key-share lock a
    read's update lock refuses), the application's, the pause's. Taken the other way round, a
    read in between waits for the pause while the rule waits for the job (a deadlock)."""
    from app.modules.preparation import package as pk

    db.execute(select(Job.id).where(Job.id == job.id).with_for_update(key_share=True))
    pk.lock_application(db, app.id)
    return pk.unresolved_pause(db, app.id, lock=True)


def _after_pause(db: Session, user: User, job: Job, app, now: datetime):
    """D169, the owner's words (2026-11-18): "Do not pauses anything. Make it enable for the
    auto application." Whether the rule goes on with an application that paused (D132 left every
    one to the owner). Returns False (it does not, in this step), True (nothing waits: go on), or
    the unexplained pause to try once more: ended by `_advance` just before the approval, once
    every other check has passed, so a step that approves nothing never counts as a try.

    A stop on a changed form comes before anything is entered (execution's
    `pause_for_form_change`), so for the owner's accounts the rule continues it as the owner's
    two buttons do. An open pause: it reads the form again through the same capture route ("Read
    the form again"); a version differing from the one it paused on ends the pause
    (`_resolve_pauses`) and the package is rebuilt from it next step, a new question waiting for
    the owner's answer as any other. Finding no difference, it marks the pause unexplained, as the
    owner's route does. Either way the step ends there: the read committed (every lock ended), so
    the next step judges the application as it is then, without reading again. An unexplained
    pause: that version is tried once more ("Try this version again"); the live page is checked
    again before anything is entered. The owner's (`_yours`): a second stop on a version tried
    once more, a fourth stop (FORM_STOPS), anything after an attempt entered the owner's data,
    an account that is not the owner's, and what D132 already handed to the owner."""
    from app.modules.preparation import package as pk

    pauses = _pauses(db, app)
    if not pauses:
        return True
    why = _yours(db, user, app, pauses)
    if why is not None:
        _note(db, user.id, job, app, "skipped", why)
        return False
    current = _unresolved(pauses)
    if current is None:
        return True  # ended, by the owner or by a read
    declined = _declined(db, user, job)
    if declined is not None:
        # D170: not continued, nor read, while its signals or the owner's preferences rule the job
        # out; shown as waiting for that to change (`verdict`), never as the owner's for good.
        _note(db, user.id, job, app, "skipped", declined)
        return False
    if current.status == "open":
        if _limit_used(db):  # D170: nothing can be approved until a new permission: never read
            _note(db, user.id, job, app, "skipped", "permission_limit")
            return False
        if _read_failed_recently(db, job, now) or not _may_read(user):
            return False
        if not _capture(db, user, job):  # commits; a differing version ends the pause
            _note(db, user.id, job, app, "skipped", "capture_failed")
            return False
        if current.resolution == "new_form":  # this read ended it (`_resolve_pauses`, this row)
            _note(db, user.id, job, app, "continued", "form_read_again")
            return False
        pause = _lock_pause(db, job, app)
        if pause is not None and pause.id == current.id and pause.status == "open":
            # No version differing from the one it paused on: never guessed (D132). Kept now,
            # as the owner's route keeps it, so it is never read again for this pause.
            pause.status = "unexplained"
            pause.recaptured_version = pk.latest_form(db, job.id).version
            pause.unexplained_at = utcnow()  # D170: kept, whatever a later read finds
        return False
    pause = _lock_pause(db, job, app)
    if pause is None or pause.id != current.id:
        return False  # changed since this step began: the next step reads it
    return pause


def _stopped_on_form_change(db: Session, att: ExecutionAttempt) -> bool:
    """D169: an attempt that stopped because the employer's form changed, before anything was
    entered: not a stop of its own, so the rule may continue its application (`_after_pause`)."""
    from app.modules.execution.models import ApplicationPause

    if att.disclosure_started_at is not None:
        return False
    return (
        db.scalar(
            select(ApplicationPause.id)
            .where(
                ApplicationPause.attempt_id == att.id,
                ApplicationPause.user_id == att.user_id,
                ApplicationPause.kind == "form_changed",
            )
            .limit(1)
        )
        is not None
    )


# D170: what the rule does with an application that has a pause waiting (`verdict`).
CONTINUES, WAITS, YOURS = "continues", "waits", "yours"


def _limit_used(db: Session) -> bool:
    """D112: the recorded permission's attempt limit is used up (every step declines until the
    owner records a new permission)."""
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose")
    return cap is not None and live.attempts_used(db, cap[1]) >= cap[0]


def verdict(db: Session, user: User, app) -> tuple[str, str | None]:
    """D170: what the standing rule does with this paused application, as its next steps will judge
    it, and why it waits; shown with the pause (the feed, Questions, the application's page), so
    the owner never applies by hand while the rule may still send it:
    - CONTINUES: it continues it by itself (D169);
    - WAITS: it would once what holds it lifts: automatic applying stopped now ("stopped":
      switched off or paused, the pilot not running here, no recorded permission covering it, its
      attempt limit used up, no approval allowed a day), the job's signals or the owner's
      preferences ruling it out ("declined"), the post unreadable since the pause began
      ("unreadable", read again once a day), or, the version to be tried once more, a question
      waiting for the owner's answer ("questions"). Never D132's words: how to take it over
      instead;
    - YOURS: it never will (D132's words), and that is for good: a final or revoked application,
      one begun before a restore or while one is unresolved, a job it never examines (not a post
      the pilot accepts), or what `_yours` leaves to the owner.
    For an application that has a pause waiting (its callers' only use)."""
    if app.state in FINAL_STATES or _owner_revoked(db, app):
        return YOURS, None
    if restore.held(db):
        return YOURS, None  # once resolved, an application begun before it is the owner's
    restored = restore.restored_at(db)
    if restored is not None and app.created_at < restored:
        return YOURS, None
    job = db.get(Job, app.job_id)
    if job is None or job.url is None or live.posting(job.url) is None:
        return YOURS, None  # never examined by the rule
    pauses = _pauses(db, app)
    if _yours(db, user, app, pauses) is not None:
        return YOURS, None
    if owner_refusal(user) is not None or paused(db, user) or limit_refusal(db) is not None:
        return WAITS, "stopped"
    if _declined(db, user, job) is not None:
        return WAITS, "declined"
    current = _unresolved(pauses)
    if (
        current is not None
        and current.status == "open"
        and (_read_failed_since(db, job, current) or _read_failed_recently(db, job, utcnow()))
    ):
        return WAITS, "unreadable"  # its next read is held a day after the last failed one
    if current is not None and current.status == "unexplained" and _questions_open(db, app):
        return WAITS, "questions"  # its next step, the try, waits for them (`open_questions`)
    return CONTINUES, None


def _questions_open(db: Session, app) -> bool:
    """D170: the application's package as it stands asks the owner for an answer (or holds one
    the form refuses): the rule approves nothing until it is given (`_advance`)."""
    from app.modules.preparation import package as pk

    pkg = pk.latest_package(db, app.id)
    return pkg is not None and bool(pkg.content["unresolved"] or pkg.content["validation_errors"])


def limit_refusal(db: Session) -> str | None:
    """D170: why the rule can approve nothing on this server now, beyond `owner_refusal`: the
    recorded permission's attempts used up (D112), or no approval allowed a day (a daily cap of
    0). Shown on the Tracker with automatic applying's state."""
    if _limit_used(db):
        return "limit_reached"
    if get_settings().auto_apply_daily_cap <= 0:
        return "no_daily_approvals"
    return None


def _read_failed_since(db: Session, job: Job, pause) -> bool:
    """D170: a read of the job's post for this pause failed (the rule reads it again once a day)."""
    return (
        db.scalar(
            select(AutoApplyEvent.id)
            .where(
                AutoApplyEvent.job_id == job.id,
                AutoApplyEvent.user_id == job.user_id,
                AutoApplyEvent.reason == "capture_failed",
                AutoApplyEvent.created_at > pause.created_at,
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
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import ApprovalScope
    from app.modules.providers.routing import form_checkpoint

    if job.user_id != user.id:  # D170: never another account's job, whatever selected it
        log.error("auto-apply: a job of another account was selected; skipped")
        return None
    app = _application(db, user, job)
    if app is not None:
        if app.state in FINAL_STATES:
            return None
        if _owner_revoked(db, app):
            _note(db, user.id, job, app, "skipped", "owner_revoked")
            return None
        restored = restore.restored_at(db)
        if restored is not None and app.created_at < restored:  # D147: began before a restore
            _note(db, user.id, job, app, "skipped", "restored_from_backup")
            return None
        att = _latest_attempt(db, app)
        if att is not None and att.state in HELD:
            return None  # never a read while an attempt holds the application
        after = _after_pause(db, user, job, app, now)  # D169
        if after is False:
            return None
        retry = None if after is True else after
        # The application as it is now, under its lock: the owner may have acted since this step
        # began (a revocation, a cancel, an attempt of their own).
        pk.lock_application(db, app.id)
        db.refresh(app)
        if app.state in FINAL_STATES or _owner_revoked(db, app):
            return None  # the next step says why
        att = _latest_attempt(db, app)  # one that ended is never changed again
        if att is not None and att.state not in (AttemptState.rehearsed,):
            if att.state in HELD or att.state == AttemptState.confirmed:
                return None
            if not (_paused_before_entry(db, att) or _stopped_on_form_change(db, att)):
                _note(db, user.id, job, app, "skipped", "attempt_stopped")
                return None
    else:
        retry = None
    declined = _declined(db, user, job)
    if declined is not None:  # D170: before the post is read, never for a job the rule declines
        _note(db, user.id, job, app, "skipped", declined)
        return None
    form = pk.latest_form(db, job.id)
    if form is None:
        if _read_failed_recently(db, job, now) or not _may_read(user):
            return None
        if not _capture(db, user, job):
            _note(db, user.id, job, None, "skipped", "capture_failed")
            return None
        # The capture committed, which ended this step's hold (run_for): hold again first.
        _hold(db, user.id)
        if paused(db, user):
            return None
        declined = _declined(db, user, job)  # D170: as it is after the read
        if declined is not None:
            _note(db, user.id, job, app, "skipped", declined)
            return None
        form = pk.latest_form(db, job.id)
    if form_checkpoint(form.schema):
        _note(db, user.id, job, app, "skipped", "checkpoint")
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
    if _limit_used(db):
        _note(db, user.id, job, app, "skipped", "permission_limit")
        return None
    if get_settings().sole_owner:
        db.execute(text("SELECT pg_advisory_xact_lock(:c, 0)"), {"c": _CAP_LOCK})
    if cap_used(db, user.id, now) >= get_settings().auto_apply_daily_cap:
        _note(db, user.id, job, app, "skipped", "daily_cap")
        return None
    if retry is not None:
        # D169: that version tried once more, now that it will be approved; a step any check
        # above declined left the pause as it was. A refused approval below rolls this back.
        retry.status, retry.resolution, retry.resolved_at = "closed", "dismissed", utcnow()
        _note(db, user.id, job, app, "continued", "form_tried_again")  # flushes the pause too
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
    except SoftTimeLimitExceeded:  # D170: the task's time is up, not a refusal (`run_for`)
        raise
    except Exception:  # noqa: BLE001 - any refusal leaves nothing queued; it waits for the owner
        log.info("auto-apply: queueing refused (job kept for the owner)")
        if retry is not None:
            # D170: nothing was queued, so that version was not tried once more: the pause stays
            # as it was (with the rule's approval, which nothing used).
            db.rollback()
        _note(db, user.id, job, app, "skipped", "queue_refused")
        return None
    _note(db, user.id, job, app, "approved_rehearsal" if rehearsal else "approved_submit",
          "rehearsal_queued" if rehearsal else "submission_queued")  # fmt: skip
    record(db, user.id, "application.transition", "application", app.id, to="queued", by=RULE)
    return "approved"


def run_for(db: Session, user: User, now: datetime | None = None) -> int:
    """The rule for one account; how many applications it queued."""
    now = now or utcnow()
    if owner_refusal(user) or paused(db, user) or limit_refusal(db) == "no_daily_approvals":
        return 0  # D170: with no approval allowed a day, no post is read for nothing either
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
        except SoftTimeLimitExceeded:  # D170: the task's time is up: no further job is started
            db.rollback()
            raise
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
        if restore.held(db):  # D147: restored from a backup: the relay ends what it restored
            return 0
        if s.all_accounts or s.sole_owner:  # D114/D168: every account, each unless paused
            users = db.scalars(select(User)).all()
        else:
            users = db.scalars(select(User).where(func.lower(User.email).in_(owners))).all()
        for user in users:
            total += run_for(db, user, now)
    return total
