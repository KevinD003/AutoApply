"""D101: what NoEfforts does with your own Gmail when you turn it on.

* Verification codes (`codes_enabled`): while one of your applications waits at a code step
  (execution's checkpoint), the messages received since that step opened are read. A code is
  entered for you only when exactly one new message from a code sender (`inbox_code_senders`)
  reads as a code email with exactly one code; anything else leaves the step to you. A message
  is used once; a code the employer rejects is not entered again.
* Application emails (`tracking_enabled`): every message received since the last read ends (the
  first read goes back `inbox_first_read_days`) is sorted by fixed rules (rules.py) and kept as
  one event. A rejection, interview or assessment that names exactly one of your submitted
  applications is proposed as its outcome; you accept or dismiss it (outcomes are what you
  report, D53). A "we received your application" email that names exactly one application whose
  submission has an unknown outcome (`submitted_unconfirmed`) is proposed as its reconciliation:
  you confirm it was received, with the email as what you checked. Nothing is sent, deleted,
  labelled or marked read.

Only what an event needs is kept: a keyed reference to the message, when it arrived, the
sender's domain, its kind, the application and the state. Never the text, the subject, the
sender's name or a code. Errors are kept as fixed codes.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.modules.applications.models import Application
from app.modules.applications.service import (
    RECONCILED_RECEIVED,
    ever_submitted,
    lock_submission,
    record_outcome,
    transition,
)
from app.modules.applications.states import Actor, AppState, Outcome
from app.modules.audit.service import record, ref
from app.modules.execution import service as execution
from app.modules.execution.models import Checkpoint
from app.modules.identity.models import User
from app.modules.inbox import rules
from app.modules.inbox.models import InboxEvent, InboxSettings
from app.modules.inbox.provider import GmailReader, InboxUnavailable, Message
from app.modules.jobs.models import Job

OUTCOME_OF = {
    "rejected": Outcome.rejected,
    "interview": Outcome.interviewing,
    "assessment": Outcome.assessment_received,
}


def available_for(user: User) -> str | None:
    """Why reading this user's mail is not available, or None."""
    s = get_settings()
    if not s.inbox_enabled:
        return "not_enabled"
    if user.email.strip().lower() not in {e.strip().lower() for e in s.inbox_owner_emails}:
        return "not_for_this_account"
    if not s.inbox_token_file:
        return "not_connected"
    return None


def reader() -> GmailReader:
    s = get_settings()
    return GmailReader(s.inbox_token_file, s.inbox_api_base, s.inbox_token_url)


def settings_of(db: Session, user_id) -> InboxSettings:
    st = db.get(InboxSettings, user_id)
    if st is None:
        st = InboxSettings(user_id=user_id, codes_enabled=False, tracking_enabled=False)
        db.add(st)
        db.flush()
    return st


def _known(db: Session, user_id, mref: str) -> bool:
    return (
        db.scalar(
            select(InboxEvent.id).where(
                InboxEvent.user_id == user_id, InboxEvent.message_ref == mref
            )
        )
        is not None
    )


def _event(db, user_id, m: Message, mref: str, kind: str, state: str, app_id=None) -> InboxEvent:
    e = InboxEvent(user_id=user_id, message_ref=mref, received_at=m.received_at,
                   sender_domain=m.sender_domain or "unknown", kind=kind, state=state,
                   application_id=app_id)  # fmt: skip
    db.add(e)
    db.flush()
    return e


def _code_sender(domain: str) -> bool:
    d = (domain or "").lower()
    return any(d == s or d.endswith("." + s) for s in get_settings().inbox_code_senders)


def fill_codes(db: Session, user: User, gmail: GmailReader | None = None) -> int:
    """Enter a code from your mail for each code step of yours that is waiting. Returns how many
    codes were entered. The caller commits."""
    st = settings_of(db, user.id)
    if not st.codes_enabled or available_for(user):
        return 0
    waiting = db.scalars(
        select(Checkpoint).where(
            Checkpoint.user_id == user.id,
            Checkpoint.status == "open",
            Checkpoint.expires_at > utcnow(),
        )  # fmt: skip
    ).all()
    if not waiting:
        return 0
    gmail = gmail or reader()
    entered = 0
    for cp in waiting:
        since = cp.created_at - timedelta(seconds=5)
        try:
            found = []
            for mid in gmail.received_after(since - timedelta(seconds=1), limit=20):
                mref = ref(mid, user.id)
                if _known(db, user.id, mref):
                    continue  # a message is used once
                m = gmail.read(mid)
                if m.received_at < since or not _code_sender(m.sender_domain):
                    continue
                found.append((m, mref, rules.extract_code(m.subject, m.text)))
        except InboxUnavailable as e:
            st.last_error = e.code
            return entered
        codes = {c for _, _, c in found if c}
        if not found:
            continue
        if len(codes) != 1 or any(c is None for _, _, c in found):
            for m, mref, _ in found:  # never guessed: the step stays yours
                _event(db, user.id, m, mref, "code", "code_unclear", cp.application_id)
            continue
        code = codes.pop()
        try:
            execution.submit_code(db, user.id, cp.application_id, cp.id, cp.round, code)
        except (LookupError, PermissionError, ValueError):
            continue
        for m, mref, _ in found:
            _event(db, user.id, m, mref, "code", "code_used", cp.application_id)
        record(db, user.id, "inbox.code_entered", "checkpoint", cp.id, round=cp.round)
        entered += 1
    return entered


def _submitted_apps(db: Session, user_id) -> list[tuple[Application, str]]:
    rows = db.execute(
        select(Application, Job.employer)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user_id)
    ).all()
    return [(a, emp) for a, emp in rows if emp and ever_submitted(db, a)]


def check(db: Session, user: User, gmail: GmailReader | None = None, now=None) -> dict:
    """Read the messages received since the last read and keep what they say. The caller
    commits. Returns counts by state."""
    st = settings_of(db, user.id)
    why = available_for(user)
    if why or not st.tracking_enabled:
        return {"skipped": why or "tracking_off"}
    now = now or utcnow()
    since = st.last_checked_at or now - timedelta(days=get_settings().inbox_first_read_days)
    gmail = gmail or reader()
    apps = _submitted_apps(db, user.id)
    counts: dict[str, int] = {}
    try:
        for mid in gmail.received_after(since, limit=500):
            mref = ref(mid, user.id)
            if _known(db, user.id, mref):
                continue
            m = gmail.read(mid)
            kind = rules.classify(m.subject, m.text)
            if kind == "code":
                continue  # codes are fill_codes' alone, and only while a step waits
            named = [a for a, emp in apps if rules.mentions(emp, m.sender_name, m.subject, m.text)]
            app = named[0] if len(named) == 1 else None
            app_id = app.id if app else None
            if kind == "other" and app_id is None:
                continue  # not about your applications: nothing kept
            if kind in OUTCOME_OF:
                state = "proposed" if app_id else "unlinked"
            elif kind == "received" and app and app.state == AppState.submitted_unconfirmed:
                state = "proposed"  # it may settle a submission whose outcome is unknown
            else:
                state = "noted" if app_id else "unlinked"
            _event(db, user.id, m, mref, kind, state, app_id)
            counts[state] = counts.get(state, 0) + 1
    except InboxUnavailable as e:
        st.last_error = e.code
        record(db, user.id, "inbox.read_failed", "inbox", None, reason_code=e.code)
        return {"error": e.code}
    st.last_checked_at, st.last_error = now, None
    record(db, user.id, "inbox.read", "inbox", None, proposed=counts.get("proposed", 0),
           unlinked=counts.get("unlinked", 0), noted=counts.get("noted", 0))  # fmt: skip
    return counts


def _owned_event(db: Session, user_id, event_id: uuid.UUID) -> InboxEvent | None:
    return db.scalar(
        select(InboxEvent)
        .where(InboxEvent.id == event_id, InboxEvent.user_id == user_id)
        .with_for_update()
    )


class Settled(ValueError):
    """The application's submission is no longer of unknown outcome: nothing to reconcile."""


def accept(db: Session, user: User, event_id: uuid.UUID) -> InboxEvent | None:
    """You confirm what a proposed email says, as your statement (D53): its outcome is recorded
    on its application, dated the day the email arrived; a "received" email reconciles a
    submission of unknown outcome as received, with the email as what you checked (the same
    transition as reconciling it yourself). None: not yours (404)."""
    from app.modules.preparation.package import lock_application

    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if (
        e.state != "proposed"
        or e.application_id is None
        or (e.kind not in OUTCOME_OF and e.kind != "received")
    ):
        raise ValueError("not_proposed")
    app = db.get(Application, e.application_id)
    day: date = e.received_at.date()
    if e.kind == "received":
        lock_submission(db, app)  # D46: its attempts, then the application, as reconcile does
        if app.state != AppState.submitted_unconfirmed:
            raise Settled("settled")
        transition(db, app, AppState.submitted_confirmed, Actor.user, RECONCILED_RECEIVED,
                   evidence_note=f"An email from {e.sender_domain} on {day.isoformat()} says "
                   "the application was received.")  # fmt: skip
    else:
        lock_application(db, e.application_id)
        db.refresh(app)
        note = f"From an email from {e.sender_domain} on {day.isoformat()}."
        record_outcome(db, app, OUTCOME_OF[e.kind], occurred_on=day, note=note)
    e.state = "accepted"
    record(db, user.id, "inbox.accepted", "application", app.id, kind=e.kind)
    return e


def dismiss(db: Session, user: User, event_id: uuid.UUID) -> InboxEvent | None:
    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if e.state not in ("proposed", "unlinked", "noted"):
        raise ValueError("not_open")
    e.state = "dismissed"
    record(db, user.id, "inbox.dismissed", "inbox_event", e.id, kind=e.kind)
    return e


def due(db: Session, now: datetime | None = None) -> list[tuple[User, InboxSettings]]:
    """Accounts whose mail the worker reads now: codes whenever one of their steps waits,
    application emails once per `inbox_check_interval_seconds`."""
    now = now or utcnow()
    every = timedelta(seconds=get_settings().inbox_check_interval_seconds)
    out = []
    for u, st in db.execute(
        select(User, InboxSettings).join(InboxSettings, InboxSettings.user_id == User.id)
    ).all():
        if available_for(u):
            continue
        stale = st.last_checked_at is None or st.last_checked_at <= now - every
        if st.codes_enabled or (st.tracking_enabled and stale):
            out.append((u, st))
    return out


def inbox_tick() -> dict:
    """The worker's pass: codes for every waiting step, then application emails when due. Each
    account in its own transaction; one that fails is counted and the others go on."""
    from app.core.db import SessionLocal

    out = {"codes": 0, "reads": 0, "errors": 0}
    with SessionLocal() as db:
        accounts = [(u.id, st.codes_enabled, st.tracking_enabled) for u, st in due(db)]
    every = timedelta(seconds=get_settings().inbox_check_interval_seconds)
    for user_id, codes, tracking in accounts:
        try:
            with SessionLocal() as db:
                user = db.get(User, user_id)
                st = settings_of(db, user_id)
                gmail = reader()
                if codes:
                    out["codes"] += fill_codes(db, user, gmail)
                if tracking and (st.last_checked_at is None
                                 or st.last_checked_at <= utcnow() - every):  # fmt: skip
                    check(db, user, gmail)
                    out["reads"] += 1
                db.commit()
        except Exception:  # noqa: BLE001 - one account's failure never stops the others
            out["errors"] += 1
    return out
