"""Execution state transitions. Every worker write is a compare-and-swap on (state, generation).

Guarantee (and its limits)
--------------------------
* At most one *active* attempt per application (partial unique index).
* At most one worker can pass the final gate for an attempt: the gate is a conditional update
  from `claimed` to `sending` that requires the caller's generation, lease and a live approval
  of the exact package hash. A worker that lost its lease fails the gate and must not click.
* After `sending` nothing is ever retried automatically. Lost or ambiguous outcomes become
  `unknown` (application `submitted_unconfirmed`) and need reconciliation.
* This is duplicate *suppression* on our side. It is not exactly-once delivery at the employer:
  an employer that accepts twice from one click, or a user resubmitting elsewhere, is outside it.
"""

import re
import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.applications.service import transition
from app.modules.applications.states import Actor, AppState
from app.modules.audit.service import record
from app.modules.execution.models import (
    ACTIVE,
    AttemptEvent,
    AttemptState,
    Checkpoint,
    Evidence,
    ExecutionAttempt,
    OutboxMessage,
)
from app.modules.execution.policy import (
    BindingChanged,
    UnsupportedDestination,
    adapter_for,
    check_binding,
)
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApprovalScope, PackageApproval

S = AttemptState
TOPIC_EXECUTE = "execute_attempt"
SERIALIZATION_FAILURE = "40001"  # PostgreSQL: a row changed after this transaction's snapshot


class LostAuthority(RuntimeError):
    """The worker no longer holds this attempt (lease lost, cancelled, or fenced out)."""


class GateRefused(RuntimeError):
    pass


def event(db: Session, att: ExecutionAttempt, kind: str, **detail) -> None:
    db.add(AttemptEvent(attempt_id=att.id, generation=att.generation, kind=kind, detail=detail))


def _app_to(db, app: Application, target: AppState, actor: Actor, reason: str) -> None:
    if app.state != target:
        transition(db, app, target, actor, reason)


# --------------------------------------------------------------------------------------------
# Enqueue (called in the same transaction as the user's queue transition)


def enqueue(db: Session, app: Application) -> ExecutionAttempt:
    pkg = pk.latest_package(db, app.id)
    appr = pk.active_approval(db, pkg)
    if appr is None:
        raise pk.ApprovalError("Approve the current package version before queueing.")
    adapter_for(pkg.content["destination"])  # raises if unsupported
    try:
        adapter = check_binding(appr, pkg.content["destination"])["adapter"]
    except BindingChanged as e:
        e.approval_id = appr.id  # the caller retires it after rolling back the queue
        raise
    att = ExecutionAttempt(
        application_id=app.id,
        user_id=app.user_id,
        package_id=pkg.id,
        package_hash=pkg.content_hash,
        approval_id=appr.id,
        adapter=adapter,
    )
    db.add(att)
    db.flush()
    db.add(OutboxMessage(topic=TOPIC_EXECUTE, attempt_id=att.id))
    event(db, att, "enqueued", package_version=pkg.version)
    return att


def retire_approval(db: Session, approval_id, reason: str) -> None:
    """Invalidate one approval whose execution meaning changed, so the user can approve the same
    content again under the method that would now run."""
    appr = db.get(PackageApproval, approval_id)
    if appr is not None and appr.invalidated_at is None:
        appr.invalidated_at, appr.invalidation_reason = utcnow(), reason


def relay_outbox(publish, limit: int = 50) -> int:
    """Publish undispatched messages. Safe to run concurrently (SKIP LOCKED) and repeatedly."""
    sent = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.dispatched_at.is_(None))
            .order_by(OutboxMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for m in rows:
            m.publish_attempts += 1
            try:
                publish(m.topic, str(m.attempt_id))  # ids only, never candidate data
            except Exception as e:  # broker down: keep the message, try again later
                # The type only: a broker error's text can quote its URL, credentials included.
                m.last_error = type(e).__name__
                continue
            m.dispatched_at = utcnow()
            m.last_error = None
            sent += 1
        db.commit()
    return sent


# --------------------------------------------------------------------------------------------
# Claim, authority, heartbeats


def claim(attempt_id: uuid.UUID, worker: str) -> int | None:
    """Atomically take a pending attempt. Returns the new generation, or None if another
    delivery already claimed it (duplicate deliveries are ignored here)."""
    lease = timedelta(seconds=get_settings().lease_seconds)
    with SessionLocal() as db:
        app_id = db.scalar(
            select(ExecutionAttempt.application_id).where(ExecutionAttempt.id == attempt_id)
        )
        if app_id is None:
            return None
        app = pk.lock_application(db, app_id)  # serialize with revoke/cancel/approve
        now = utcnow()
        gen = db.execute(
            update(ExecutionAttempt)
            .where(
                ExecutionAttempt.id == attempt_id,
                ExecutionAttempt.state == S.pending,
                ExecutionAttempt.cancel_requested.is_(False),
            )
            .values(
                state=S.claimed,
                generation=ExecutionAttempt.generation + 1,
                lease_owner=worker,
                lease_expires_at=now + lease,
                heartbeat_at=now,
            )
            .returning(ExecutionAttempt.generation)
        ).scalar_one_or_none()
        if gen is None:
            db.rollback()
            return None
        att = db.get(ExecutionAttempt, attempt_id)
        if not _approval_still_valid(db, app, att):
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = "Approval no longer valid when a worker picked this up."
            event(db, att, "claim_refused_approval")
            if app.state == AppState.queued:
                _app_to(db, app, AppState.awaiting_approval, Actor.system, att.outcome_detail)
            db.commit()
            return None
        if app.state == AppState.queued:
            _app_to(db, app, AppState.running, Actor.worker, "A worker started this application")
        event(db, att, "claimed", worker=worker)
        db.commit()
        return gen


def _approval_still_valid(db: Session, app: Application, att: ExecutionAttempt) -> bool:
    pkg = pk.latest_package(db, app.id)
    appr = pk.active_approval(db, pkg)
    return (
        pkg is not None
        and appr is not None
        and pkg.id == att.package_id
        and pkg.content_hash == att.package_hash
        and appr.id == att.approval_id
    )


def heartbeat(
    attempt_id: uuid.UUID, worker: str, gen: int, states=(S.claimed, S.awaiting_code, S.sending)
) -> None:
    """Extend the lease, or raise LostAuthority. Call between every browser step."""
    lease = timedelta(seconds=get_settings().lease_seconds)
    with SessionLocal() as db:
        n = db.execute(
            update(ExecutionAttempt)
            .where(
                ExecutionAttempt.id == attempt_id,
                ExecutionAttempt.generation == gen,
                ExecutionAttempt.lease_owner == worker,
                ExecutionAttempt.state.in_(states),
                ExecutionAttempt.cancel_requested.is_(False),
                ExecutionAttempt.lease_expires_at > utcnow(),
            )
            .values(lease_expires_at=utcnow() + lease, heartbeat_at=utcnow())
        ).rowcount
        db.commit()
    if n != 1:
        raise LostAuthority("lease lost, attempt cancelled, or fenced by a newer generation")


def _locked_attempt(db: Session, attempt_id, worker: str, gen: int, state) -> ExecutionAttempt:
    att = db.scalar(
        select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
    )
    states = state if isinstance(state, tuple) else (state,)
    if (
        att is None
        or att.generation != gen
        or att.lease_owner != worker
        or att.state not in states
        or att.cancel_requested
        or att.lease_expires_at is None
        or att.lease_expires_at <= utcnow()
    ):
        raise LostAuthority("attempt is no longer held by this worker")
    return att


def _gate_checks(db: Session, att: ExecutionAttempt) -> Application:
    """Authorization checks shared by both gates. Runs inside a REPEATABLE READ transaction
    holding the application and attempt row locks.

    The snapshot is taken at the attempt lock, before the application lock, so a revocation (or
    a new package version) committed while this gate waited for the application lock is not in
    it. The approval row is therefore locked as well: if it changed after the snapshot,
    PostgreSQL refuses the lock with a serialization failure, and so does the gate."""
    try:
        app = pk.lock_application(db, att.application_id)
        db.execute(
            select(PackageApproval.id)
            .where(PackageApproval.id == att.approval_id)
            .with_for_update(read=True)
        )
    except DBAPIError as e:
        if getattr(e.orig, "sqlstate", None) == SERIALIZATION_FAILURE:
            raise GateRefused("the approval changed while it was being checked") from None
        raise
    if app.state != AppState.running:
        raise GateRefused(f"application is {app.state.value}")
    if not _approval_still_valid(db, app, att):
        raise GateRefused("approval revoked, expired or superseded")
    content = pk.build_content(db, app)
    if pk.content_hash(content) != att.package_hash:
        raise GateRefused("profile, documents or answers changed after approval")
    appr = db.get(PackageApproval, att.approval_id)
    try:
        check_binding(appr, content["destination"], att.adapter)
    except (BindingChanged, UnsupportedDestination):
        raise GateRefused("the execution method changed after approval") from None
    return app


def _repeatable_read() -> Session:
    db = SessionLocal()
    db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    return db


def gate_before_disclosure(attempt_id, worker: str, gen: int) -> None:
    """Authority to disclose the approved package to its destination (fill/upload may transmit
    data). Records that disclosure is starting; after this, a crash is never retried silently."""
    with _repeatable_read() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            _gate_checks(db, att)
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e)) from None
        att.disclosure_started_at = utcnow()
        event(db, att, "disclosure_authorized")
        db.commit()


def gate_before_send(attempt_id, worker: str, gen: int) -> None:
    """The linearization point. If this commits, this worker (and only it) may click submit.
    Cancellation, revocation or edits that commit before this point stop the send; anything
    after it cannot recall data already in flight."""
    with _repeatable_read() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            app = _gate_checks(db, att)
            # A rehearsal stops before this gate (runner); this refusal holds even if it did not.
            if db.get(PackageApproval, att.approval_id).scope != ApprovalScope.submit:
                raise GateRefused("this approval permits filling and checking only, not submitting")
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e)) from None
        now = utcnow()
        att.state, att.send_started_at = S.sending, now
        att.lease_expires_at = now + timedelta(seconds=get_settings().submit_timeout_seconds + 30)
        _app_to(db, app, AppState.ready_to_submit, Actor.worker, "Filled and checked")
        _app_to(db, app, AppState.submitting, Actor.worker, "Submitting")
        event(db, att, "send_authorized")
        db.commit()


# --------------------------------------------------------------------------------------------
# Outcomes (all fenced by generation)


def _finish(
    attempt_id,
    worker,
    gen,
    from_states,
    to: AttemptState,
    app_target: AppState | None,
    detail: str,
    evidence: list[dict] | None = None,
    retire: str | None = None,
) -> bool:
    """`retire`: a reason code (RETIRED); the attempt's approval is retired with it in the same
    transaction, so it cannot outlive the outcome that used it up."""
    with SessionLocal() as db:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
        )
        if att is None or att.generation != gen or att.state not in from_states:
            return False
        app = pk.lock_application(db, att.application_id)
        att.state, att.finished_at, att.outcome_detail = to, utcnow(), detail[:2000]
        att.lease_owner, att.lease_expires_at = None, None
        if app_target is not None:
            _app_to(db, app, app_target, Actor.worker, detail[:900])
        for ev in evidence or []:
            add_evidence(db, att, **ev)
        if retire is not None:
            retire_approval(db, att.approval_id, RETIRED[retire])
            record(db, att.user_id, "package.approval_retired", "application",
                   att.application_id, reason_code=retire)  # fmt: skip
        event(db, att, f"outcome_{to.value}", detail=detail[:500])
        record(db, att.user_id, f"execution.{to.value}", "application", att.application_id)
        db.commit()
        return True


def add_evidence(
    db: Session, att: ExecutionAttempt, kind: str, data: dict, strength: str = "none"
) -> None:
    days = get_settings().evidence_retention_days
    db.add(
        Evidence(
            attempt_id=att.id,
            application_id=att.application_id,
            user_id=att.user_id,
            kind=kind,
            strength=strength,
            data=data,
            retain_until=utcnow() + timedelta(days=days),
        )
    )


def record_evidence(attempt_id, worker, gen, kind, data, strength="none") -> None:
    with SessionLocal() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, (S.claimed, S.sending, S.awaiting_code))
        add_evidence(db, att, kind, data, strength)
        db.commit()


def fail_safe(attempt_id, worker, gen, reason: str) -> bool:
    """Stopped before disclosing anything. The application waits for the user."""
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.claimed,),
        S.failed_safe,
        AppState.needs_user_action,
        f"Stopped before sending anything: {reason}",
    )


def abandon(attempt_id, worker, gen, reason: str) -> bool:
    """Data was disclosed (filled/uploaded) but not submitted. Never retried automatically."""
    ok = _finish(
        attempt_id,
        worker,
        gen,
        (S.claimed,),
        S.abandoned,
        AppState.needs_user_action,
        f"Stopped after entering data but before submitting: {reason}",
    )
    return ok or _finish(
        attempt_id,
        worker,
        gen,
        (S.awaiting_code,),
        S.abandoned,
        AppState.needs_user_action,
        f"Verification was not completed: {reason}",
    )


REHEARSAL_DONE = "Rehearsal finished: the form was filled and checked, and nothing was submitted."
# Why an outcome retired its approval (`_finish(retire=...)`), shown on the review page.
RETIRED = {
    "rehearsal_completed": "Used by a rehearsal: the form was filled and checked, and nothing "
    "was submitted. Approve again to submit, or to rehearse again.",
}


def rehearsed(attempt_id, worker, gen) -> bool:
    """A rehearsal (an approval to disclose only) ends here: filled, uploaded, read back and
    re-checked, before the send gate. Nothing was submitted. Its approval is used up, so
    submitting needs an approval to submit and a new attempt, which repeats every check."""
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.claimed,),
        S.rehearsed,
        AppState.needs_user_action,
        REHEARSAL_DONE,
        retire="rehearsal_completed",
    )


def confirmed(attempt_id, worker, gen, evidence: list[dict]) -> bool:
    # `unknown` is accepted too: a slow worker may still observe the receipt after the sweeper
    # gave up on it. Upgrading to confirmed never causes a send.
    with SessionLocal() as db:
        app_state = db.scalar(
            select(Application.state)
            .join(ExecutionAttempt, ExecutionAttempt.application_id == Application.id)
            .where(ExecutionAttempt.id == attempt_id)
        )
    target = AppState.submitted_confirmed
    if app_state == AppState.submitted_unconfirmed:
        target = None  # leave reconciliation state; the user confirms with the evidence
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.sending, S.awaiting_code, S.unknown),
        S.confirmed,
        target,
        "Employer receipt observed",
        evidence,
    )


def unknown(attempt_id, worker, gen, reason: str) -> bool:
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.sending, S.awaiting_code),
        S.unknown,
        AppState.submitted_unconfirmed,
        f"Outcome unknown — check with the employer before doing anything: {reason}",
    )


def rejected(attempt_id, worker, gen, reason: str) -> bool:
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.sending,),
        S.rejected,
        AppState.failed_terminal,
        f"The employer's form refused the submission: {reason}",
    )


# --------------------------------------------------------------------------------------------
# Verification-code checkpoints


def open_checkpoint(attempt_id, worker, gen, message: str) -> uuid.UUID:
    ttl = timedelta(seconds=get_settings().checkpoint_ttl_seconds)
    with SessionLocal() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, (S.sending, S.awaiting_code))
        app = pk.lock_application(db, att.application_id)
        cp = db.scalar(
            select(Checkpoint).where(
                Checkpoint.attempt_id == att.id, Checkpoint.status.in_(("open", "submitted"))
            )
        )
        if cp is None:
            cp = Checkpoint(
                attempt_id=att.id,
                application_id=att.application_id,
                user_id=att.user_id,
                expires_at=utcnow() + ttl,
                message=message,
            )
            db.add(cp)
        att.state = S.awaiting_code
        att.lease_expires_at = cp.expires_at + timedelta(seconds=30)
        _app_to(
            db,
            app,
            AppState.needs_user_action,
            Actor.worker,
            "The employer sent a verification code. Enter it to continue.",
        )
        event(db, att, "checkpoint_opened")
        db.commit()
        return cp.id


def take_code(checkpoint_id, attempt_id, worker, gen) -> tuple[str | None, str]:
    """Worker side: returns (code, status). The code is erased from the database as it is read."""
    with SessionLocal() as db:
        _locked_attempt(db, attempt_id, worker, gen, S.awaiting_code)
        cp = db.scalar(select(Checkpoint).where(Checkpoint.id == checkpoint_id).with_for_update())
        if cp.expires_at <= utcnow() and cp.status in ("open", "submitted"):
            cp.status, cp.code = "expired", None
            db.commit()
            return None, "expired"
        if cp.status != "submitted":
            db.commit()
            return None, cp.status
        code, cp.code, cp.status = cp.code, None, "consumed"
        db.commit()
        return code, "consumed"


def code_result(checkpoint_id, attempt_id, worker, gen, accepted: bool) -> str:
    """After typing the code: done, or reopen for another round, or failed after max wrong."""
    with SessionLocal() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.awaiting_code)
        cp = db.scalar(select(Checkpoint).where(Checkpoint.id == checkpoint_id).with_for_update())
        if accepted:
            cp.status = "done"
            att.state = S.sending
            app = pk.lock_application(db, att.application_id)
            _app_to(db, app, AppState.submitting, Actor.worker, "Verification code accepted")
        else:
            cp.wrong_attempts += 1
            if cp.wrong_attempts >= cp.max_attempts:
                cp.status = "failed"
            else:
                cp.status, cp.round = "open", cp.round + 1
                cp.message = "The employer rejected that code. Check the latest email."
        event(db, att, "checkpoint_result", accepted=accepted, round=cp.round)
        db.commit()
        return cp.status


_CODE = re.compile(r"^[A-Za-z0-9-]{4,12}$")


def submit_code(db: Session, user_id, app_id, checkpoint_id, round_: int, code: str) -> Checkpoint:
    """User side. Bound to owner, application, checkpoint and round; old rounds are replays."""
    cp = db.scalar(select(Checkpoint).where(Checkpoint.id == checkpoint_id).with_for_update())
    if cp is None or cp.user_id != user_id or cp.application_id != app_id:
        raise LookupError("Checkpoint")
    if cp.expires_at <= utcnow():
        raise PermissionError("This verification request has expired.")
    if cp.status != "open" or cp.round != round_:
        raise PermissionError("This verification request is not waiting for a code.")
    if not _CODE.match(code or ""):
        raise ValueError("Codes are 4–12 letters, digits or dashes.")
    cp.code, cp.status = code, "submitted"
    record(db, user_id, "checkpoint.code_submitted", "checkpoint", cp.id, round=round_)
    return cp


# --------------------------------------------------------------------------------------------
# Cancellation and recovery


def cancel(db: Session, app: Application) -> str:
    """User cancel. Takes the same locks as the final gate, so it is either before the gate
    (and stops the send) or after it (and is refused)."""
    pk.lock_application(db, app.id)
    att = db.scalar(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.state.in_(ACTIVE))
        .with_for_update()
    )
    if att is not None and att.state in (S.sending, S.awaiting_code):
        raise PermissionError(
            "Submission may already be in flight; it cannot be cancelled. "
            "Wait for the outcome or reconcile."
        )
    if att is not None:
        att.cancel_requested = True
        att.state, att.finished_at = S.cancelled, utcnow()
        att.outcome_detail = "Cancelled by you before anything was submitted."
        event(db, att, "cancelled")
    transition(db, app, AppState.cancelled, Actor.user, "Cancelled")
    return "cancelled"


def sweep(publish_new: bool = True) -> dict:
    """Recover attempts whose worker vanished. Never takes over a possibly-submitting attempt."""
    s = get_settings()
    out = {"repended": 0, "abandoned": 0, "unknown": 0, "failed": 0}
    with SessionLocal() as db:
        stale = db.scalars(
            select(ExecutionAttempt)
            .where(
                ExecutionAttempt.state.in_((S.claimed, S.sending, S.awaiting_code)),
                ExecutionAttempt.lease_expires_at < utcnow(),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for att in stale:
            app = pk.lock_application(db, att.application_id)
            att.lease_owner, att.lease_expires_at = None, None
            if att.state in (S.sending, S.awaiting_code):
                att.state, att.finished_at = S.unknown, utcnow()
                att.outcome_detail = "Worker stopped after the submit step began; outcome unknown."
                if app.state in (AppState.submitting, AppState.needs_user_action):
                    _app_to(
                        db, app, AppState.submitted_unconfirmed, Actor.system, att.outcome_detail
                    )
                event(db, att, "swept_unknown")
                out["unknown"] += 1
            elif att.disclosure_started_at is not None:
                att.state, att.finished_at = S.abandoned, utcnow()
                att.outcome_detail = (
                    "Worker stopped after entering data but before "
                    "submitting. Not retried automatically."
                )
                _app_to(db, app, AppState.needs_user_action, Actor.system, att.outcome_detail)
                event(db, att, "swept_abandoned")
                out["abandoned"] += 1
            elif att.retry_count < s.max_safe_retries:
                att.state, att.retry_count = S.pending, att.retry_count + 1
                event(db, att, "swept_repended", retry=att.retry_count)
                if publish_new:
                    db.add(OutboxMessage(topic=TOPIC_EXECUTE, attempt_id=att.id))
                out["repended"] += 1
            else:
                att.state, att.finished_at = S.failed_safe, utcnow()
                att.outcome_detail = "Worker kept stopping before sending anything."
                _app_to(db, app, AppState.failed_retryable, Actor.system, att.outcome_detail)
                event(db, att, "swept_failed")
                out["failed"] += 1
        db.commit()
    return out


# --------------------------------------------------------------------------------------------
# Evidence lifecycle


def purge_expired_evidence() -> int:
    """Delete evidence past its retention date. Runs daily from Celery beat."""
    with SessionLocal() as db:
        n = db.execute(delete(Evidence).where(Evidence.retain_until < utcnow())).rowcount
        db.commit()
        return n


def delete_application_evidence(db: Session, app: Application) -> int:
    """User-requested deletion. Refused while an attempt is active (it may still write)."""
    active = db.scalar(
        select(ExecutionAttempt.id).where(
            ExecutionAttempt.application_id == app.id, ExecutionAttempt.state.in_(ACTIVE)
        )
    )
    if active is not None:
        raise PermissionError("An attempt is still running; wait for it to finish.")
    n = db.execute(
        delete(Evidence).where(Evidence.application_id == app.id, Evidence.user_id == app.user_id)
    ).rowcount
    record(db, app.user_id, "evidence.delete", "application", app.id, rows=n)
    return n
