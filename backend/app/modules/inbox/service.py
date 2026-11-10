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
  report, D53). A "we received your application" email is proposed as the reconciliation of a
  submission whose outcome is unknown (`submitted_unconfirmed`) only when it correlates strongly
  (D103, `_settles`): it names exactly one application's employer and also its job title, it
  arrived after that submission's final click, and no other such proposal is open for it. You
  confirm it was received, with the email as what you checked; confirming changes the
  application's state only and never sends, queues or retries anything. Otherwise it is only
  noted. Nothing is sent, deleted, labelled or marked read.

Only what an event needs is kept: a keyed reference to the message, when it arrived, the
sender's domain, its kind, the application and the state. Never the text, the subject, the
sender's name or a code. Errors are kept as fixed codes.

D103: none of this runs on the owner's switch alone. Each action needs the owner's recorded
authorization (app/core/authorizations.py): reading code emails and entering a code each, and
reading application emails. None has been given, so nothing is read; a code you type yourself
at the checkpoint is entered as before.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authorizations
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
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from app.modules.identity.models import User
from app.modules.inbox import parsing, rules
from app.modules.inbox.models import InboxConsent, InboxEvent, InboxSettings
from app.modules.inbox.provider import GmailReader, InboxUnavailable, Message
from app.modules.jobs.models import Job

# The recognised event → the reportable application Outcome it proposes (spec §2/§3). Events not
# here (received, under_review, info_requested, interview_cancelled, position_closed, talent_pool,
# recommendation, other) are recognised and surfaced but change no status on their own.
OUTCOME_OF = {
    "rejected": Outcome.rejected,
    "offer": Outcome.offer,
    "withdrawn": Outcome.withdrawn,
    "interview": Outcome.interviewing,
    "interview_scheduled": Outcome.interviewing,
    "interview_rescheduled": Outcome.interviewing,
    "next_round": Outcome.interviewing,
    "assessment": Outcome.assessment_received,
    "assessment_reminder": Outcome.assessment_received,
}
# An outcome event's note distinguishes an email-derived change from a manual one (for the
# manual-lock guard and for undo). Kept deliberately content-free (domain + date only).
_EMAIL_NOTE = "From an email from"
_AUTO_NOTE = "Automatically from an email from"
_MAX_READ = 1500  # messages read in one pass; a fuller backfill is surfaced, never skipped (§8)
# The recognised event, in words, for the application's timeline — so an interview invitation and
# a scheduled interview stay distinct there even though both derive the "interviewing" outcome.
_KIND_PHRASE = {
    "interview": "interview invitation",
    "interview_scheduled": "scheduled interview",
    "interview_rescheduled": "rescheduled interview",
    "next_round": "invitation to the next round",
    "assessment": "assessment invitation",
    "assessment_reminder": "assessment reminder",
    "rejected": "rejection",
    "offer": "offer",
    "withdrawn": "withdrawal",
}


def _note(
    kind: str, domain: str | None, day: date, prefix: str, *, correction: bool = False
) -> str:
    """One timeline note for an email-derived outcome: who it came from and the day, plus the
    recognised event in words (invitation vs scheduled, etc.). Starts with `prefix` so the manual-
    vs-email check in `_latest_outcome_event` still recognises it."""
    phrase = _KIND_PHRASE.get(kind)
    tail = (f" ({phrase})" if phrase else "") + (" (your correction)" if correction else "")
    return f"{prefix} {domain or 'unknown'} on {day.isoformat()}.{tail}"


APPLICATION_EMAIL = "read_application_email"
# The version of the in-app consent disclosure (the scope note + the authorize control's copy) in
# force. Recorded on each consent so a later wording change never rewrites a past consent; bump it
# whenever that disclosure materially changes.
CONSENT_DISCLOSURE_VERSION = "appmail-consent/v1"


def may(action: str) -> bool:
    """Whether the owner's recorded authorization covers this action (D103, the reviewed-source
    register). Verification codes (read_codes/enter_codes) are authorized only this way."""
    return authorizations.covers(authorizations.INBOX, action)


def codes_authorized() -> bool:
    """Entering a code from the mail needs both: reading code emails, and entering what they say."""
    return may("read_codes") and may("enter_codes")


def is_inbox_owner(user: User) -> bool:
    """This account is the server's inbox owner — the only account whose own mail is ever read."""
    s = get_settings()
    return user.email.strip().lower() in {e.strip().lower() for e in s.inbox_owner_emails}


def _active_consent(
    db: Session, user_id, action: str, today: date | None = None
) -> InboxConsent | None:
    """The owner's active (granted, not revoked, not past its end) in-app consent for `action`, or
    None. Newest matching row wins; the table is an append-only consent history."""
    today = today or utcnow().date()
    for c in db.scalars(
        select(InboxConsent)
        .where(
            InboxConsent.user_id == user_id,
            InboxConsent.action == action,
            InboxConsent.revoked_at.is_(None),
        )
        .order_by(InboxConsent.granted_at.desc())
    ):
        if c.ends_on is None or today <= c.ends_on:
            return c
    return None


def may_read_applications(db: Session, user: User) -> bool:
    """The owner may read application emails when either path authorizes it: a recorded
    authorization in reviewed source (D103) OR the owner's own active in-app consent (an
    authenticated, auditable, revocable record). Both are owner-scoped; neither covers verification
    codes, sending or submission — those keep their own separate gates."""
    return may(APPLICATION_EMAIL) or _active_consent(db, user.id, APPLICATION_EMAIL) is not None


def active_application_consent(db: Session, user: User) -> InboxConsent | None:
    """The owner's active in-app consent to read application emails, or None (for display)."""
    return _active_consent(db, user.id, APPLICATION_EMAIL)


def _revoke_active(db: Session, user_id, action: str) -> int:
    now = utcnow()
    rows = db.scalars(
        select(InboxConsent).where(
            InboxConsent.user_id == user_id,
            InboxConsent.action == action,
            InboxConsent.revoked_at.is_(None),
        )
    ).all()
    for c in rows:
        c.revoked_at = now
    return len(rows)


def grant_application_consent(
    db: Session, user: User, attestation: str, ends_on: date | None
) -> InboxConsent:
    """Record the owner's own authenticated consent to read application emails in their own mailbox.
    Only the inbox owner may do this; it covers read_application_email alone (never codes, sending
    or submission) and is scoped to the owner's own account. Supersedes any earlier active consent
    (revoked here), and is audited. The owner's words are kept verbatim as the consent attestation;
    no code change is needed to activate."""
    if not is_inbox_owner(user):
        raise PermissionError("not_owner")
    text = (attestation or "").strip()
    if not text:
        raise ValueError("no_attestation")
    _revoke_active(db, user.id, APPLICATION_EMAIL)
    c = InboxConsent(
        user_id=user.id,
        action=APPLICATION_EMAIL,
        attestation=text[:500],
        disclosure_version=CONSENT_DISCLOSURE_VERSION,
        ends_on=ends_on,
    )
    db.add(c)
    db.flush()
    ends = ends_on.isoformat() if ends_on else None
    record(db, user.id, "inbox.authorization_granted", "inbox", None,
           capability=APPLICATION_EMAIL, ends_on=ends)  # fmt: skip
    return c


def revoke_application_consent(db: Session, user: User) -> int:
    """Withdraw the owner's in-app consent to read application emails. Returns how many active
    consents were revoked; reading is gated again at once. Audited. (Disconnecting the Gmail token
    and revoking in the Google account are separate, stronger steps — see the API scope note.)"""
    if not is_inbox_owner(user):
        raise PermissionError("not_owner")
    n = _revoke_active(db, user.id, APPLICATION_EMAIL)
    if n:
        record(db, user.id, "inbox.authorization_revoked", "inbox", None,
               capability=APPLICATION_EMAIL)  # fmt: skip
    return n


def available_for(db: Session, user: User) -> str | None:
    """Why reading this user's mail is not available, or None."""
    s = get_settings()
    if not s.inbox_enabled:
        return "not_enabled"
    if not is_inbox_owner(user):
        return "not_for_this_account"
    if not (codes_authorized() or may_read_applications(db, user)):
        return "not_authorized"  # switched on is not authorized (D103)
    if not owner_token_file(db, user):
        return "not_connected"
    return None


def owner_token_file(db: Session, user: User) -> str:
    """The token file this owner's mail is read from: the app's browser-connected Gmail (D128) when
    present, else the connect.py CLI's configured file (`inbox_token_file`). Either is a 0600 file
    on the server; the connection is the same read-only Gmail either way."""
    from app.modules.connections import service as connections  # lazy: avoid an import cycle

    return connections.connected_token_file(db, user) or get_settings().inbox_token_file


def reader(token_file: str = "") -> GmailReader:
    s = get_settings()
    return GmailReader(token_file or s.inbox_token_file, s.inbox_api_base, s.inbox_token_url)


def settings_of(db: Session, user_id) -> InboxSettings:
    st = db.get(InboxSettings, user_id)
    if st is None:
        # Every mailbox-processing option is opt-in: a new account starts with all of them off
        # (codes, application-email tracking, auto-apply), so nothing is read until the owner
        # turns each on. The D117 code-reading authorization is unchanged; only this toggle
        # default moved from on to off, so the owner opts in rather than opting out.
        st = InboxSettings(user_id=user_id)
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


def _event(db, user_id, m: Message, mref: str, kind: str, state: str, app_id=None, *,
           thread_ref=None, match_band=None, class_band=None, match_basis=None,
           proposed_outcome=None, prev_outcome=None,
           applied_outcome=None) -> InboxEvent:  # fmt: skip
    e = InboxEvent(
        user_id=user_id,
        message_ref=mref,
        thread_ref=thread_ref,
        received_at=m.received_at,
        sender_domain=m.sender_domain or "unknown",
        kind=kind,
        state=state,
        match_band=match_band,
        class_band=class_band,
        match_basis=match_basis,
        proposed_outcome=proposed_outcome,
        prev_outcome=prev_outcome,
        applied_outcome=applied_outcome,
        application_id=app_id,
    )
    db.add(e)
    db.flush()
    return e


def _code_sender(domain: str) -> bool:
    d = (domain or "").lower()
    return any(d == s or d.endswith("." + s) for s in get_settings().inbox_code_senders)


def fill_codes(db: Session, user: User, gmail: GmailReader | None = None) -> int:
    """Enter a code from your mail for each code step of yours that is waiting. Returns how many
    codes were entered. Each code entered is committed at once (D143); the caller commits the
    rest."""
    st = settings_of(db, user.id)
    if not st.codes_enabled or available_for(db, user) or not codes_authorized():
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
    gmail = gmail or reader(owner_token_file(db, user))
    entered = 0
    for cp in waiting:
        # D117 (legacy notes): the code can be emailed once the address is typed, before the
        # step opens: messages from the start of this attempt's filling in count too.
        started = db.scalar(select(ExecutionAttempt.disclosure_started_at)
                            .where(ExecutionAttempt.id == cp.attempt_id))  # fmt: skip
        since = min(cp.created_at, started or cp.created_at) - timedelta(seconds=5)
        employer = db.scalar(select(Job.employer).join(Application, Application.job_id == Job.id)
                             .where(Application.id == cp.application_id,
                                    Application.user_id == user.id))  # fmt: skip
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
        if not found:
            continue
        # D117: when several applications wait at once, the email naming this one's employer
        # in its subject is this one's (legacy notes); the others stay for their own steps.
        named = [x for x in found if employer and rules.names_employer(employer, x[0].subject)]
        if named and len(named) < len(found):
            found = named
        codes = {c for _, _, c in found if c}
        if len(codes) != 1 or any(c is None for _, _, c in found):
            for m, mref, _ in found:  # never guessed: the step stays yours
                _event(db, user.id, m, mref, "code", "code_unclear", cp.application_id)
            continue
        code = codes.pop()
        # D143 (lock order): the application before the request, as every outcome and the
        # sweeper take them. The event rows below key-share lock the application; taken after
        # the request's lock, that could deadlock with an outcome closing this request.
        db.execute(
            select(Application.id)
            .where(Application.id == cp.application_id)
            .with_for_update(read=True, key_share=True)
        )
        try:
            execution.submit_code(db, user.id, cp.application_id, cp.id, cp.round, code)
        except (LookupError, PermissionError, ValueError):
            db.commit()  # nothing was entered: the locks are not kept for the next request
            continue
        for m, mref, _ in found:
            _event(db, user.id, m, mref, "code", "code_used", cp.application_id)
        record(db, user.id, "inbox.code_entered", "checkpoint", cp.id, round=cp.round)
        entered += 1
        # D143: committed at once. The waiting worker reads this request under its attempt's
        # lock, and must not wait for the rest of the mailbox.
        db.commit()
    return entered


def _settles(db: Session, user_id, app: Application, title: str, m: Message) -> bool:
    """D103: whether a "received" email may be proposed as the reconciliation of `app`'s
    submission of unknown outcome. All of: the application is in submitted_unconfirmed; the email
    also names its job title (the employer alone is not enough: one employer, several roles);
    it arrived after the final click of the attempt that left the outcome unknown (an earlier
    email is about something else); and no other such proposal is open for the application (one
    at a time, so one email cannot be confirmed over another unseen)."""
    if app.state != AppState.submitted_unconfirmed:
        return False
    if not rules.mentions(title, "", m.subject, m.text):
        return False
    sent = db.scalar(
        select(ExecutionAttempt.send_started_at)
        .where(ExecutionAttempt.application_id == app.id,
               ExecutionAttempt.send_started_at.is_not(None))
        .order_by(ExecutionAttempt.send_started_at.desc())
        .limit(1)
    )  # fmt: skip
    if sent is None or m.received_at < sent:
        return False
    open_one = select(InboxEvent.id).where(
        InboxEvent.user_id == user_id,
        InboxEvent.application_id == app.id,
        InboxEvent.kind == "received",
        InboxEvent.state == "proposed",
    )
    return db.scalar(open_one.limit(1)) is None


def _candidates(db: Session, user_id) -> list[rules.Candidate]:
    """The user's submitted applications, as the matcher sees them (employer, title, requisition
    id and posting URL). Only a submitted application can receive an employer email (D103)."""
    rows = db.execute(
        select(Application, Job.employer, Job.title, Job.requisition_id, Job.url)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user_id)
    ).all()
    return [
        rules.Candidate(str(a.id), emp, title or "", req, url)
        for a, emp, title, req, url in rows
        if emp and ever_submitted(db, a)
    ]


def _thread_app(db: Session, user_id, thread_ref: str | None) -> str | None:
    """The application a prior message in this mail thread was linked to (spec §1: previously
    linked email thread), if it is still one of the user's applications."""
    if not thread_ref:
        return None
    e = db.scalar(
        select(InboxEvent)
        .where(
            InboxEvent.user_id == user_id,
            InboxEvent.thread_ref == thread_ref,
            InboxEvent.application_id.is_not(None),
        )  # fmt: skip
        .order_by(InboxEvent.received_at.desc())
        .limit(1)
    )
    if e is None:
        return None
    app = db.get(Application, e.application_id)
    return str(e.application_id) if app and app.user_id == user_id else None


def _latest_outcome_event(db: Session, app_id) -> tuple[Outcome, date | None, bool] | None:
    """(to_outcome, occurred_on, email_derived) of the application's most recent outcome event, or
    None. `email_derived` tells a manual correction apart from an email-recorded one."""
    from app.modules.applications.models import ApplicationEvent

    e = db.scalar(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app_id, ApplicationEvent.kind == "outcome")
        .order_by(ApplicationEvent.created_at.desc())
        .limit(1)
    )
    if e is None:
        return None
    note = e.evidence_note or ""
    return e.to_outcome, e.occurred_on, note.startswith((_EMAIL_NOTE, _AUTO_NOTE))


def _guard(db: Session, app: Application, proposed: Outcome, m: Message) -> str:
    """Temporal and conflict consistency (spec §3), by explicit rules — never a numeric stage
    ranking. Returns 'apply_ok' (consistent), 'noted' (redundant or a stale earlier signal that
    must not pull a later stage back), or 'review' (a conflict for you to resolve)."""
    cur = app.outcome
    if cur == proposed:
        return "noted"  # already recorded; a repeat changes nothing
    latest = _latest_outcome_event(db, app.id)
    day = m.received_at.date()
    # Older than the recorded activity: an old message must not override newer activity.
    if latest and latest[1] is not None and day < latest[1]:
        return "review"
    # A manual correction must not be silently overridden by a later, differing email.
    if latest and not latest[2] and latest[0] != Outcome.none and latest[0] != proposed:
        return "review"
    # An earlier-stage signal must not pull a later stage back (a reminder after an interview).
    if proposed == Outcome.assessment_received and cur in (Outcome.interviewing, Outcome.offer):
        return "noted"
    if proposed == Outcome.interviewing and cur == Outcome.offer:
        return "noted"
    # Opposite decisions, or a reactivation after a decision, are genuine conflicts.
    if cur == Outcome.rejected and proposed in (
        Outcome.interviewing,
        Outcome.assessment_received,
        Outcome.offer,
    ):
        return "review"
    if {cur, proposed} == {Outcome.offer, Outcome.rejected}:
        return "review"
    return "apply_ok"


def _auto_apply(db: Session, user_id, app: Application, outcome: Outcome, m: Message,
                kind: str) -> bool:  # fmt: skip
    """Apply a clear, well-matched, consistent outcome automatically (spec §4). Still recorded,
    audited and undoable; records nothing it is refused (e.g. an employer outcome before
    submission)."""
    from app.modules.applications.states import Refused
    from app.modules.preparation.package import lock_application

    lock_application(db, app.id)
    db.refresh(app)
    day = m.received_at.date()
    auto_note = _note(kind, m.sender_domain, day, _AUTO_NOTE)
    try:
        record_outcome(db, app, outcome, occurred_on=day, note=auto_note)
    except Refused:
        return False
    record(db, user_id, "inbox.auto_applied", "application", app.id, to=outcome.value)
    return True


def _ingest(db: Session, user_id, m: Message, mref: str, cands: list[rules.Candidate],
            st: InboxSettings) -> str | None:  # fmt: skip
    """Recognise one message, match it to an application and keep it as one InboxEvent. Returns
    the event's state, or None when nothing is kept (a code, or mail about no application)."""
    current = parsing.current_text(m.subject, m.text)
    event, cband = rules.classify_detail(m.subject, current)
    if event == "code":
        return None  # codes are fill_codes' alone, and only while a step waits
    thread_ref = ref(m.thread_id, user_id) if m.thread_id else None
    thread_app = _thread_app(db, user_id, thread_ref)
    mr = rules.match(cands, m.sender_name, m.sender_domain, m.subject, current, thread_app)
    app = db.get(Application, uuid.UUID(mr.application_id)) if mr.application_id else None
    proposed = OUTCOME_OF.get(event)
    common = {
        "thread_ref": thread_ref, "match_band": mr.band, "class_band": cband,
        "match_basis": ",".join(mr.basis) or None,
        "proposed_outcome": proposed.value if proposed else None,
        "prev_outcome": app.outcome.value if app else None,
    }  # fmt: skip

    def keep(state: str) -> str:
        _event(db, user_id, m, mref, event, state, app.id if app else None, **common)
        return state

    # "received" acknowledgement: the D103 reconciliation of a submission of unknown outcome.
    if event == "received":
        if app and app.outcome in (
            Outcome.interviewing,
            Outcome.offer,
            Outcome.rejected,
            Outcome.assessment_received,
        ):
            return keep("noted")  # a late acknowledgement must not undo a later stage (§3)
        title = next((c.title for c in cands if c.application_id == mr.application_id), "")
        if app and _settles(db, user_id, app, title, m):
            return keep("proposed")
        if app:
            return keep("noted")
        return keep("review" if mr.band in ("weak", "ambiguous") else "unlinked")

    # Outcome-bearing events.
    if proposed is not None:
        if app is None:
            return keep("review" if mr.band in ("weak", "ambiguous") else "unlinked")
        decision = _guard(db, app, proposed, m)
        if decision == "review":
            return keep("review")
        if decision == "noted":
            return keep("noted")
        if st.auto_apply and cband == "explicit" and mr.band in ("strong", "good") \
                and _auto_apply(db, user_id, app, proposed, m, event):  # fmt: skip
            common["applied_outcome"] = proposed.value
            return keep("auto_applied")
        return keep("proposed")

    # Informational events (under_review, info_requested, interview_cancelled, position_closed,
    # talent_pool, recommendation, other): recognised and surfaced, never an automatic outcome.
    if event == "recommendation" or (event == "other" and app is None):
        return None  # a job suggestion, or mail about no application: nothing kept
    if app is None:
        return keep("review" if mr.band in ("weak", "ambiguous") else "unlinked")
    return keep("noted")


def check(db: Session, user: User, gmail: GmailReader | None = None, now=None) -> dict:
    """Read the messages received since the last read, in the order they arrived, and keep what
    each says (spec §3/§6/§8). The caller commits. Returns counts by state."""
    st = settings_of(db, user.id)
    why = available_for(db, user) or (None if may_read_applications(db, user) else "not_authorized")
    if why or not st.tracking_enabled:
        return {"skipped": why or "tracking_off"}
    now = now or utcnow()
    since = st.last_checked_at or now - timedelta(days=get_settings().inbox_first_read_days)
    gmail = gmail or reader(owner_token_file(db, user))
    cands = _candidates(db, user.id)
    counts: dict[str, int] = {}
    try:
        ids = gmail.received_after(since, limit=_MAX_READ)
        msgs: list[Message] = []
        for mid in ids:
            mref = ref(mid, user.id)
            if not _known(db, user.id, mref):
                msgs.append((mref, gmail.read(mid)))
    except InboxUnavailable as e:
        st.last_error = e.code
        if e.code in ("revoked", "token_unreadable"):
            # D128: a web-connected token that stopped working puts the connection into
            # "reconnect required" so Account -> Connections says so (a CLI token file is not).
            from app.modules.connections import service as connections

            connections.mark_reconnect_required(db, user.id)
        record(db, user.id, "inbox.read_failed", "inbox", None, reason_code=e.code)
        return {"error": e.code}
    # Process oldest first, so each message's consistency guard sees the ones before it (§3).
    for mref, m in sorted(msgs, key=lambda x: x[1].received_at):
        state = _ingest(db, user.id, m, mref, cands, st)
        if state:
            counts[state] = counts.get(state, 0) + 1
    # Sync safety: the id list is newest-first, so a full batch may hide older messages we did not
    # read. Rather than advance the cursor past them (and silently skip intermediate mail, §8), we
    # surface it and leave the cursor; a smaller `inbox_first_read_days` resolves a huge backfill.
    if len(ids) >= _MAX_READ:
        st.last_error = "too_many"
        record(db, user.id, "inbox.read_capped", "inbox", None)
        return {"capped": True, **counts}
    st.last_checked_at, st.last_error = now, None
    record(db, user.id, "inbox.read", "inbox", None, proposed=counts.get("proposed", 0),
           auto_applied=counts.get("auto_applied", 0), review=counts.get("review", 0),
           noted=counts.get("noted", 0), unlinked=counts.get("unlinked", 0))  # fmt: skip
    return counts


def _owned_event(db: Session, user_id, event_id: uuid.UUID) -> InboxEvent | None:
    return db.scalar(
        select(InboxEvent)
        .where(InboxEvent.id == event_id, InboxEvent.user_id == user_id)
        .with_for_update()
    )


class Settled(ValueError):
    """The application's submission is no longer of unknown outcome: nothing to reconcile."""


def _chosen_outcome(value: str | None) -> Outcome | None:
    if not value:
        return None
    try:
        return Outcome(value)
    except ValueError:
        return None


def accept(
    db: Session, user: User, event_id: uuid.UUID, outcome: str | None = None
) -> InboxEvent | None:
    """You confirm, or correct, what an email says, as your statement (D53): its outcome is
    recorded on its application, dated the day the email arrived; a "received" email reconciles a
    submission of unknown outcome. `outcome` overrides the recognised event when you correct it.
    Works on a proposed event, or a review event you have linked to the right application. None:
    not yours (404)."""
    from app.modules.preparation.package import lock_application

    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if e.state not in ("proposed", "review") or e.application_id is None:
        raise ValueError("not_proposed")
    app = db.get(Application, e.application_id)
    day: date = e.received_at.date()
    chosen = _chosen_outcome(outcome)
    if e.kind == "received" and chosen is None:
        lock_submission(db, app)  # D46: its attempts, then the application, as reconcile does
        if app.state != AppState.submitted_unconfirmed:
            raise Settled("settled")
        transition(db, app, AppState.submitted_confirmed, Actor.user, RECONCILED_RECEIVED,
                   evidence_note=f"An email from {e.sender_domain} on {day.isoformat()} says "
                   "the application was received.")  # fmt: skip
    else:
        chosen = chosen or OUTCOME_OF.get(e.kind)
        if chosen is None:
            raise ValueError("no_outcome")  # this event names no outcome; pick one to record
        lock_application(db, e.application_id)
        db.refresh(app)
        corrected = outcome is not None and chosen != OUTCOME_OF.get(e.kind)
        note = _note(e.kind, e.sender_domain, day, _EMAIL_NOTE, correction=corrected)
        record_outcome(db, app, chosen, occurred_on=day, note=note)
        e.applied_outcome = chosen.value
    e.state = "accepted"
    record(db, user.id, "inbox.accepted", "application", app.id, kind=e.kind,
           corrected=bool(outcome))  # fmt: skip
    return e


def dismiss(db: Session, user: User, event_id: uuid.UUID) -> InboxEvent | None:
    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if e.state not in ("proposed", "review", "unlinked", "noted"):
        raise ValueError("not_open")
    e.state = "dismissed"
    record(db, user.id, "inbox.dismissed", "inbox_event", e.id, kind=e.kind)
    return e


def undo(db: Session, user: User, event_id: uuid.UUID) -> InboxEvent | None:
    """Undo an accepted or automatically applied email outcome by recording a compensating
    outcome back to the value before it (application_events are insert-only, so this is a new
    event, not an edit). A "received" reconciliation to submitted_confirmed is terminal and
    cannot be undone. None: not yours (404)."""
    from app.modules.preparation.package import lock_application

    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if e.state not in ("accepted", "auto_applied"):
        raise ValueError("not_undoable")
    if e.kind == "received":
        raise ValueError("terminal")  # submitted_confirmed is terminal (states.py)
    app = db.get(Application, e.application_id) if e.application_id else None
    if app is not None:
        lock_application(db, app.id)
        db.refresh(app)
        applied = _chosen_outcome(e.applied_outcome)
        # A newer update has since changed this application: undoing this one would clobber it.
        # Undo the newer one first, so the application's history stays coherent.
        if applied is not None and app.outcome != applied:
            raise ValueError("superseded")
        prev = _chosen_outcome(e.prev_outcome) or Outcome.none
        undo_note = f"Undo of the outcome from an email from {e.sender_domain}."
        record_outcome(db, app, prev, occurred_on=utcnow().date(), note=undo_note)
        record(db, user.id, "inbox.undone", "application", app.id, kind=e.kind)
    e.state = "undone"
    return e


def relink(
    db: Session, user: User, event_id: uuid.UUID, application_id: uuid.UUID | None
) -> InboxEvent | None:
    """Attach a review/unlinked email to the right application ("wrong application" correction), or
    clear the link (application_id=None). The target must be one of your applications (LookupError
    → 404). Not after the email has been acted on — undo first. None: not yours (404)."""
    e = _owned_event(db, user.id, event_id)
    if e is None:
        return None
    if e.state in ("accepted", "auto_applied"):
        raise ValueError("already_acted")
    if application_id is None:
        e.application_id, e.state, e.prev_outcome = None, "unlinked", None
    else:
        app = db.scalar(
            select(Application).where(
                Application.id == application_id, Application.user_id == user.id
            )
        )
        if app is None:
            raise LookupError("application")
        e.application_id = app.id
        e.prev_outcome = app.outcome.value
        e.state = "proposed" if (e.kind in OUTCOME_OF or e.kind == "received") else "noted"
    record(db, user.id, "inbox.relinked", "inbox_event", e.id, kind=e.kind)
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
        if available_for(db, u):
            continue
        stale = st.last_checked_at is None or st.last_checked_at <= now - every
        codes = st.codes_enabled and codes_authorized()
        if codes or (st.tracking_enabled and stale and may_read_applications(db, u)):
            out.append((u, st))
    return out


def inbox_tick() -> dict:
    """The worker's pass: codes for every waiting step, then application emails when due. Each
    account in its own transaction; one that fails is counted and the others go on."""
    from app.core.db import SessionLocal

    out = {"codes": 0, "reads": 0, "errors": 0}
    with SessionLocal() as db:
        # D117: the owner's settings exist from the start (codes on by default), without first
        # opening the inbox page.
        owners = {e.strip().lower() for e in get_settings().inbox_owner_emails}
        if get_settings().inbox_enabled and owners:
            for u in db.scalars(select(User)):
                if u.email.strip().lower() in owners:
                    settings_of(db, u.id)
            db.commit()
        accounts = [(u.id, st.codes_enabled, st.tracking_enabled) for u, st in due(db)]
    every = timedelta(seconds=get_settings().inbox_check_interval_seconds)
    for user_id, codes, tracking in accounts:
        try:
            with SessionLocal() as db:
                user = db.get(User, user_id)
                st = settings_of(db, user_id)
                gmail = reader(owner_token_file(db, user))
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
