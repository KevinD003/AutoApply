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

Lock order (docs/architecture.md, "Lock order")
-----------------------------------------------
Every transaction that locks more than one of these rows takes them in this order: the
execution attempt, then its application, then its approval, then what the rehearsal
prerequisite relies on (a rehearsal record or a receipt, FOR SHARE). Inserting a row that
references an application (evidence, events) key-share locks the application too, after the
attempt: the same order. Paths that never lock an attempt (approve, revoke, answers, withdraw,
evidence deletion) start at the application. A checkpoint row is locked only alone (the user
entering a code; D143: the sweeper's pass over stale requests, which holds nothing else and so
never waits on a worker), while holding its attempt (the worker; D143: every outcome, and the
sweeper recovering an attempt, which close its request), or after its application's key-share
lock (D143: the mailbox entering a code, which then writes rows that key-share lock the
application, and commits each code at once). A form-change pause (D132) is written after the
approvals, under the attempt and application locks (the worker), or under the application lock
alone (reading the form again, approving, cancelling).
"""

import logging
import re
import uuid
from datetime import timedelta
from typing import NamedTuple

from sqlalchemy import delete, exists, func, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased

from app.core import authorizations
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.applications.service import transition
from app.modules.applications.states import Actor, AppState
from app.modules.audit.service import record
from app.modules.execution import live, rehearsal
from app.modules.execution.models import (
    ACTIVE,
    PAUSE_UNRESOLVED,
    ApplicationPause,
    AttemptEvent,
    AttemptState,
    Checkpoint,
    Evidence,
    ExecutionAttempt,
    OutboxMessage,
    RehearsalRecord,
)
from app.modules.execution.policy import (
    BindingChanged,
    UnsupportedDestination,
    adapter_for,
    approved_binding,
    check_binding,
)
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApplicationPackage, ApprovalScope, PackageApproval

log = logging.getLogger("noefforts.execution")
S = AttemptState
TOPIC_EXECUTE = "execute_attempt"
LOCK_NOT_AVAILABLE = "55P03"  # PostgreSQL: NOWAIT found the row locked


class LostAuthority(RuntimeError):
    """The worker no longer holds this attempt (lease lost, cancelled, or fenced out)."""


class GateRefused(RuntimeError):
    """`code`: a fixed reason code (execution/rehearsal.py), or None for the gates' own
    refusals. Safe to store and show."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def event(db: Session, att: ExecutionAttempt, kind: str, **detail) -> None:
    db.add(AttemptEvent(attempt_id=att.id, generation=att.generation, kind=kind, detail=detail))


def _app_to(db, app: Application, target: AppState, actor: Actor, reason: str) -> None:
    if app.state != target:
        transition(db, app, target, actor, reason)


# --------------------------------------------------------------------------------------------
# Enqueue (called in the same transaction as the user's queue transition)


def enqueue(db: Session, app: Application) -> ExecutionAttempt:
    if wizard_entered(db, app):  # D142: first, before anything about the approval
        raise pk.refused("wizard_draft_at_employer")
    pkg = pk.latest_package(db, app.id)
    appr = pk.active_approval(db, pkg)
    if appr is None:
        raise pk.refused("approval_needed")
    confirmed_before = select(ExecutionAttempt.id).where(
        ExecutionAttempt.application_id == app.id, ExecutionAttempt.state == S.confirmed
    )
    if db.scalar(confirmed_before.limit(1)) is not None:
        # Whatever the application's state says, the employer's receipt was recorded once.
        raise pk.refused("already_confirmed")
    _supersede_stale_attempt(db, app)
    adapter_for(pkg.content["destination"])  # raises if unsupported
    try:
        binding = check_binding(appr, pkg.content["destination"])
    except BindingChanged as e:
        e.approval_id = appr.id  # the caller retires it after rolling back the queue
        raise
    adapter, dest = binding["adapter"], pkg.content["destination"]
    if adapter == live.ADAPTER and appr.scope == ApprovalScope.submit:
        # D103: submitting is the pilot's permission 4, recorded on its own; your approval to
        # submit is needed as well, and neither stands in for the other.
        if live.permission_refusal(("submit",)):
            raise UnsupportedDestination(live.WHY["not_authorized"], "live_not_authorized")
    cls = rehearsal.destination_class(dest.get("origin"))
    ref = rehearsal.path_ref(app.user_id, rehearsal.execution_path(dest, adapter))
    if appr.scope == ApprovalScope.submit:
        v = rehearsal.prerequisite(
            db,
            layer="enqueue",
            user_id=app.user_id,
            destination=dest,
            adapter=adapter,
            adapter_version=binding["adapter_version"],
            destination_class=cls,
            path_ref_value=ref,
            approval=appr,
        )
        if v.status == rehearsal.UNMET:
            raise rehearsal.RehearsalRequired(v.code)  # the caller rolls the queueing back
    att = ExecutionAttempt(
        application_id=app.id,
        user_id=app.user_id,
        package_id=pkg.id,
        package_hash=pkg.content_hash,
        approval_id=appr.id,
        adapter=adapter,
        destination_class=cls,
        path_ref=ref,
    )
    db.add(att)
    db.flush()
    db.add(OutboxMessage(topic=TOPIC_EXECUTE, attempt_id=att.id))
    event(db, att, "enqueued", package_version=pkg.version)
    return att


# D142: a multi-page form (the Workday-style stand-in's wizard; package content key `wizard`).
WIZARD_ADAPTER = "fixture_workday"  # the one adapter that drives a wizard, page by page


def _is_wizard(db: Session, att: ExecutionAttempt) -> bool:
    """The attempt's package is a multi-page wizard (read from the immutable package)."""
    pkg = db.get(ApplicationPackage, att.package_id)
    return pkg is not None and pkg.user_id == att.user_id and "wizard" in (pkg.content or {})


def wizard_entered(db: Session, app: Application) -> bool:
    """D142: an attempt of this application passed the disclosure gate on a multi-page wizard,
    so the employer may keep a draft of it, or have received it: NoEfforts never runs it again
    (approve, queue, enqueue and claim refuse it). Read from the attempt's disclosure stamp and
    its immutable package, scoped by the application and its owner; neither is ever purged or
    deleted with the evidence. Takes no row lock: the callers hold the application lock, and
    locking attempts here would take them against the order (D46)."""
    package_ids = db.scalars(
        select(ExecutionAttempt.package_id).where(
            ExecutionAttempt.application_id == app.id,
            ExecutionAttempt.user_id == app.user_id,
            ExecutionAttempt.disclosure_started_at.is_not(None),
        )
    ).all()
    for pid in set(package_ids):
        pkg = db.scalar(
            select(ApplicationPackage).where(
                ApplicationPackage.id == pid, ApplicationPackage.user_id == app.user_id
            )
        )
        if pkg is not None and "wizard" in (pkg.content or {}):
            return True
    return False


def _nexts(db: Session, att: ExecutionAttempt) -> int:
    """How many pages' Next this attempt was authorized to click (each may have been saved)."""
    rows = db.scalars(
        select(AttemptEvent.detail).where(
            AttemptEvent.attempt_id == att.id, AttemptEvent.kind == "step_authorized"
        )
    ).all()
    return sum(1 for d in rows if (d or {}).get("phase") == "next")


def _supersede_stale_attempt(db: Session, app: Application) -> None:
    """Before a new attempt is inserted (under the application lock): an earlier one still
    active would make the insert fail as a duplicate, or wait on its uniqueness check while a
    claim holding it waits for this lock (a deadlock). One that is pending under an approval
    no longer valid (queued, then edited before a worker took it) can never run and has
    disclosed nothing: it is stopped here. It is locked without waiting, the attempt lock being
    against the order after the application (D46); if a worker is taking it, try again."""
    old = db.scalar(
        select(ExecutionAttempt).where(
            ExecutionAttempt.application_id == app.id, ExecutionAttempt.state.in_(ACTIVE)
        )
    )
    if old is None:
        return
    if old.state != S.pending or _approval_still_valid(db, app, old):
        raise pk.refused("attempt_running")
    try:
        with db.begin_nested():
            locked = db.scalar(
                select(ExecutionAttempt)
                .where(ExecutionAttempt.id == old.id, ExecutionAttempt.state == S.pending)
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            )
    except DBAPIError as e:
        if getattr(e.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        locked = None
    if locked is None:
        raise pk.refused("attempt_being_claimed")
    locked.state, locked.finished_at = S.failed_safe, utcnow()
    locked.outcome_detail = (
        "Stopped before anything was sent: the package changed and was queued again."
    )
    event(db, locked, "superseded")


def retire_approval(db: Session, approval_id, reason: str) -> bool:
    """Invalidate one approval whose execution meaning changed, so the user can approve the same
    content again under the method that would now run. True if it was still live."""
    appr = db.get(PackageApproval, approval_id)
    if appr is not None and appr.invalidated_at is None:
        appr.invalidated_at, appr.invalidation_reason = utcnow(), reason
        return True
    return False


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


def republish_waiting(publish, limit: int = 50) -> int:
    """D146: publish again for an attempt still waiting to be taken, once its last publication
    is older than `outbox_republish_seconds`. Nothing else sends a dispatched message a second
    time: one lost with the broker's memory, or taken by a worker that stopped before starting
    it, would leave its attempt queued (for good, or until the broker hands the message out
    again an hour later).

    Only an attempt the claim would still take: `pending`, no cancel requested, nothing
    entered. One a worker holds, and one that ended, is never published here. That an attempt
    which entered data is never run again is not this function's doing: the sweeper never puts
    one back in the queue, and the claim itself refuses one (`claim`). This select only keeps
    such an attempt from being published.

    It repeats: an attempt still waiting gets another message each time that wait has passed
    since its last one, with no limit (D146 says what that costs). If a message was not lost
    there are then several. The claim takes an attempt once; every other delivery is ignored
    (`runner.run_attempt`). The attempt's newest message decides: one not yet dispatched is the
    relay's, and one dispatched recently is waited for.

    Only the messages are locked, never the attempt (`of=OutboxMessage`): a claim, a cancel or
    a revocation does not wait for a pass, even while it is talking to the broker. A second
    pass skips a message the first holds (SKIP LOCKED). The pass ends at the first failed
    publish: the broker is down, and each further try would hold its message longer. Returns
    how many attempts were published again."""
    cutoff = utcnow() - timedelta(seconds=get_settings().outbox_republish_seconds)
    newer = aliased(OutboxMessage)
    sent = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(OutboxMessage)
            .join(ExecutionAttempt, ExecutionAttempt.id == OutboxMessage.attempt_id)
            .where(
                OutboxMessage.dispatched_at < cutoff,
                ExecutionAttempt.state == S.pending,
                ExecutionAttempt.cancel_requested.is_(False),
                ExecutionAttempt.disclosure_started_at.is_(None),
                ~exists().where(
                    newer.attempt_id == OutboxMessage.attempt_id,
                    newer.created_at > OutboxMessage.created_at,
                ),
            )
            .order_by(OutboxMessage.dispatched_at)
            .limit(limit)
            .with_for_update(of=OutboxMessage, skip_locked=True)
        ).all()
        for m in rows:
            m.publish_attempts += 1
            try:
                publish(m.topic, str(m.attempt_id))  # ids only, never candidate data
            except Exception as e:  # broker down: its age is unchanged, so the next pass tries
                m.last_error = type(e).__name__  # the type only, as in relay_outbox
                break
            m.dispatched_at = utcnow()
            m.last_error = None
            sent += 1
            log.info("attempt %s: still queued; published again", m.attempt_id)
        db.commit()
    return sent


# --------------------------------------------------------------------------------------------
# Claim, authority, heartbeats


def claim(attempt_id: uuid.UUID, worker: str) -> int | None:
    """Atomically take a pending attempt. Returns the new generation, or None if another
    delivery already claimed it (duplicate deliveries are ignored here). Locks the attempt (the
    compare-and-swap), then the application, in the global lock order; the approval is checked
    under the application lock, so a revocation or cancel committed first is seen.

    D146: an attempt that has entered data is never taken, whatever its state says. None is
    ever `pending` (the sweeper puts back only one that entered nothing); with several messages
    for one attempt now possible, the rule also stands here, where every delivery ends."""
    lease = timedelta(seconds=get_settings().lease_seconds)
    with SessionLocal() as db:
        app_id = db.scalar(
            select(ExecutionAttempt.application_id).where(ExecutionAttempt.id == attempt_id)
        )
        if app_id is None:
            return None
        now = utcnow()
        gen = db.execute(
            update(ExecutionAttempt)
            .where(
                ExecutionAttempt.id == attempt_id,
                ExecutionAttempt.state == S.pending,
                ExecutionAttempt.cancel_requested.is_(False),
                ExecutionAttempt.disclosure_started_at.is_(None),
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
        app = pk.lock_application(db, app_id)  # serialize with revoke/cancel/approve
        att = db.get(ExecutionAttempt, attempt_id)
        if wizard_entered(db, app):
            # D142: an earlier attempt entered this application on a multi-page form.
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = WIZARD_CLAIM_REFUSED
            event(db, att, "claim_refused_wizard_draft")
            _claim_refused(db, app, att.outcome_detail)
            db.commit()
            return None
        if not _approval_still_valid(db, app, att):
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = "Approval no longer valid when a worker picked this up."
            event(db, att, "claim_refused_approval")
            _claim_refused(db, app, att.outcome_detail)
            db.commit()
            return None
        if att.queued_by_rule and _is_wizard(db, att):
            # D142: whether the standing rule may drive a multi-page form is the owner's
            # decision, not taken: refused before any page is opened.
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = RULE_WIZARD
            event(db, att, "claim_refused_rule_wizard")
            _claim_refused(db, app, att.outcome_detail)
            db.commit()
            return None
        if att.queued_by_rule and _rule_stopped(db, att):
            # D134: queued by the standing rule, which is now paused or switched off.
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = RULE_STOPPED
            event(db, att, "claim_refused_rule_stopped")
            _claim_refused(db, app, att.outcome_detail)
            db.commit()
            return None
        code = _claim_prerequisite(db, att)
        if code is not None:  # before any page is opened; nothing is disclosed
            att.state, att.finished_at = S.failed_safe, now
            att.outcome_detail = rehearsal.refusal(code)
            event(db, att, "claim_refused_rehearsal", reason_code=code)
            _claim_refused(db, app, att.outcome_detail)
            db.commit()
            return None
        if app.state == AppState.queued:
            _app_to(db, app, AppState.running, Actor.worker, "A worker started this application")
        event(db, att, "claimed", worker=worker)
        db.commit()
        return gen


RULE_STOPPED = "Your automatic rule is paused or switched off; nothing was sent."
# D142
WIZARD_CLAIM_REFUSED = (
    "NoEfforts already entered this application on the employer's multi-page form and never "
    "runs it again; this attempt sent nothing. Finish it on the employer's site."
)
RULE_WIZARD = (
    "Your automatic rule does not apply on a multi-page form; nothing was sent. Apply on the "
    "employer's site, or approve and queue it yourself."
)
PAUSE_STOPPED = "stopped_by_pause"  # the attempt event of an attempt a pause stopped (D134)


def _rule_stopped(db: Session, att: ExecutionAttempt) -> bool:
    """D134: the standing rule that queued this attempt no longer acts: switched off on this
    server, or paused by the account (read under the claim's locks)."""
    from app.modules.autoapply.service import paused
    from app.modules.identity.models import User

    if not get_settings().auto_apply_enabled:
        return True
    user = db.get(User, att.user_id)
    return user is None or paused(db, user)


def _claim_refused(db: Session, app: Application, reason: str) -> None:
    """The application after a claim refused its attempt: back to approval when it was queued;
    waiting for the user when it was already running (a re-claim after the sweeper re-pended
    an attempt that had disclosed nothing), so it is never left `running` with no attempt."""
    if app.state == AppState.queued:
        _app_to(db, app, AppState.awaiting_approval, Actor.system, reason)
    elif app.state == AppState.running:
        _app_to(db, app, AppState.needs_user_action, Actor.system, reason)


def _claim_prerequisite(db: Session, att: ExecutionAttempt) -> str | None:
    """The rehearsal prerequisite at claim, from the attempt's recorded class and path and its
    immutable package; a code if unmet. Only an approval to submit has the prerequisite."""
    appr = db.get(PackageApproval, att.approval_id)
    if appr.scope != ApprovalScope.submit or att.destination_class is None:
        return None  # no class recorded: the disclosure gate refuses it, with its own message
    dest = db.get(ApplicationPackage, att.package_id).content["destination"]
    binding = approved_binding(appr, dest) or {}
    v = rehearsal.prerequisite(
        db,
        layer="claim",
        user_id=att.user_id,
        destination=dest,
        adapter=att.adapter,
        adapter_version=binding.get("adapter_version"),
        destination_class=att.destination_class,
        path_ref_value=att.path_ref,
        approval=appr,
    )
    return v.code if v.status == rehearsal.UNMET else None


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
    # After a wait, the row as committed by whoever held it (e.g. a cancel): checked below.
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


class GateContext(NamedTuple):
    app: Application
    content: dict
    approval: PackageApproval


def _gate_checks(db: Session, att: ExecutionAttempt, approval_lock: str = "share") -> GateContext:
    """Authorization checks shared by both gates and the rehearsal stop, in a transaction that
    holds the attempt row lock (D46). It takes the application lock, then the approval row lock
    (`share`, or `update` where the caller retires it), and only then reads, at READ COMMITTED:
    every check sees what was committed before it ran, including a revocation, an edit or a
    profile change committed while this gate waited for a lock. (A REPEATABLE READ snapshot,
    taken at the first statement, missed those.) Writers of the rows it locks (the attempt, the
    application and its inputs, the approval, the record or receipt the prerequisite locks) wait
    for this gate to commit. Inputs it does not lock (profile facts, work authorizations, the
    document library, the answer bank, the job and its form, API authorizations) are checked as
    of the statement that reads them: a change committed after that read does not wait and does
    not stop this gate; what is sent is still the approved package."""
    app = pk.lock_application(db, att.application_id)
    db.execute(
        select(PackageApproval.id)
        .where(PackageApproval.id == att.approval_id)
        .with_for_update(read=approval_lock == "share")
    )
    if app.state != AppState.running:
        raise GateRefused(f"application is {app.state.value}")
    if not _approval_still_valid(db, app, att):
        raise GateRefused("approval revoked, expired or superseded")
    content = pk.build_content(db, app)
    if pk.content_hash(content) != att.package_hash:
        raise GateRefused("profile, documents or answers changed after approval")
    _pilot_permission(att, ("open", "disclose"))
    appr = db.get(PackageApproval, att.approval_id)
    try:
        check_binding(appr, content["destination"], att.adapter)
    except (BindingChanged, UnsupportedDestination):
        raise GateRefused("the execution method changed after approval") from None
    # The class recorded at queueing is what readiness counts this attempt as; it must still be
    # what the destination is (e.g. not a fixture origin removed from the configuration since).
    if att.destination_class is None:
        raise GateRefused("this attempt was queued before NoEfforts recorded what kind of "
                          "destination it is; queue it again")  # fmt: skip
    if att.destination_class != rehearsal.destination_class(content["destination"].get("origin")):
        raise GateRefused("the destination is no longer the kind it was when queued")
    return GateContext(app, content, appr)


def _pilot_permission(att: ExecutionAttempt, actions: tuple[str, ...]) -> None:
    """D103: through the Greenhouse pilot, each action on a real employer's page needs the owner's
    recorded permission (app/core/authorizations.py), checked at every gate: the switch is not
    one, and a permission that ends while an attempt waits stops it here."""
    if att.adapter == live.ADAPTER and live.permission_refusal(actions):
        raise GateRefused(live.WHY["not_authorized"], "live_not_authorized")


_PILOT_LIMIT_LOCK = 7_402_112  # pg_advisory_xact_lock key: one disclosure gate at a time counts


def _pilot_limit(db: Session, att: ExecutionAttempt) -> None:
    """D112: through the Greenhouse pilot, no more attempts pass the disclosure gate than the
    owner's recorded authorization allows (rehearsals and submissions alike, counted from the day
    of the owner's words). Counted under one lock, so two gates cannot both take the last one."""
    if att.adapter != live.ADAPTER:
        return
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose")
    if cap is None:
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PILOT_LIMIT_LOCK})
    if live.attempts_used(db, cap[1], exclude=att.id) >= cap[0]:
        raise GateRefused(live.WHY["limit_reached"].format(n=cap[0]), "live_limit_reached")


def _gate_prerequisite(db: Session, att: ExecutionAttempt, ctx: GateContext, layer: str):
    """The rehearsal prerequisite inside a gate, with what it relies on locked; GateRefused (with
    its code) if unmet. Returns the verdict, or None for an attempt that does not submit."""
    if ctx.approval.scope != ApprovalScope.submit:
        return None
    dest = ctx.content["destination"]
    v = rehearsal.prerequisite(
        db,
        layer=layer,
        user_id=att.user_id,
        destination=dest,
        adapter=att.adapter,
        adapter_version=approved_binding(ctx.approval, dest)["adapter_version"],
        destination_class=att.destination_class,
        path_ref_value=att.path_ref,
        approval=ctx.approval,
        lock=True,
    )
    if v.status == rehearsal.UNMET:
        raise GateRefused(rehearsal.refusal(v.code), v.code)
    return v


def _gate_session() -> Session:
    """The gates and the rehearsal stop: READ COMMITTED, set explicitly (not left to a server
    or engine default), reading after their locks (_gate_checks)."""
    db = SessionLocal()
    db.connection(execution_options={"isolation_level": "READ COMMITTED"})
    return db


def gate_before_disclosure(attempt_id, worker: str, gen: int) -> None:
    """Authority to disclose the approved package to its destination (fill/upload may transmit
    data). Records that disclosure is starting; after this, a crash is never retried silently."""
    with _gate_session() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            ctx = _gate_checks(db, att)
            if "wizard" in ctx.content:  # D142: only its adapter, and only to submit
                if att.adapter != WIZARD_ADAPTER:
                    raise GateRefused(WIZARD_ADAPTER_REFUSED, "wizard_adapter")
                if ctx.approval.scope != ApprovalScope.submit:
                    raise GateRefused(WIZARD_REHEARSAL, "wizard_rehearsal")
            _gate_prerequisite(db, att, ctx, "disclosure")
            _pilot_limit(db, att)
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e), e.code) from None
        att.disclosure_started_at = utcnow()
        event(db, att, "disclosure_authorized")
        db.commit()


def _watch_covered(watch_seconds: int | None) -> int:
    """D143: the wait for an answer from the employer that a lease covers: what the adapter
    says it may wait (`send_watch_seconds`), at least the submit timeout and at most
    attempt_after_send_seconds."""
    cfg = get_settings()
    watch = max(cfg.submit_timeout_seconds, int(watch_seconds or 0))
    return min(watch, max(cfg.attempt_after_send_seconds, cfg.submit_timeout_seconds))


def gate_before_send(attempt_id, worker: str, gen: int, watch_seconds: int | None = None) -> None:
    """The linearization point. If this commits, this worker (and only it) may click submit.
    Cancellation, revocation or edits committed before this gate reads them stop the send
    (_gate_checks says which writers wait for it); anything after it cannot recall data already
    in flight. D143: `watch_seconds` is how long this adapter may wait for the click's answer
    (`send_watch_seconds`); the send lease covers it (at least the submit timeout, at most
    attempt_after_send_seconds, plus 30s), so the sweeper does not call a send it is still
    watching unknown. A longer lease only delays that sweep: nothing ever runs a sending attempt
    again."""
    with _gate_session() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            ctx = _gate_checks(db, att)
            # A rehearsal stops before this gate (runner); this refusal holds even if it did not.
            if ctx.approval.scope != ApprovalScope.submit:
                raise GateRefused("this approval permits filling and checking only, not submitting")
            _pilot_permission(att, ("submit",))
            verdict = _gate_prerequisite(db, att, ctx, "send")
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e), e.code) from None
        app = ctx.app
        now = utcnow()
        att.state, att.send_started_at = S.sending, now
        att.rehearsal_prerequisite = verdict.status
        att.lease_expires_at = now + timedelta(seconds=_watch_covered(watch_seconds) + 30)
        _app_to(db, app, AppState.ready_to_submit, Actor.worker, "Filled and checked")
        _app_to(db, app, AppState.submitting, Actor.worker, "Submitting")
        event(db, att, "send_authorized")
        db.commit()


WIZARD_ADAPTER_REFUSED = "this multi-page form can only be filled by its own adapter"
WIZARD_REHEARSAL = "a rehearsal is not available on a multi-page form"
WIZARD_STEP_ORDER = "a page of the employer's multi-page form was reached out of order"
STEP_PHASES = ("fill", "next")


def _expected_steps(pages: int) -> list[tuple[int, str]]:
    """D142: every step gate of a wizard of `pages` pages, in order: the Next of page 1 (the
    disclosure gate authorized filling it), then for each later page before the review page,
    filling it and its Next."""
    return [(1, "next")] + [(i, p) for i in range(2, pages) for p in STEP_PHASES]


def gate_before_step(attempt_id, worker: str, gen: int, page: int, phase: str) -> None:
    """D142: authority for one step of a multi-page form, after the disclosure gate and before
    the send gate: filling page `page` (from page 2) or clicking its Next. In one transaction
    under the gates' locks (the attempt, then the application and approval in _gate_checks), it
    re-checks everything the other gates check (authority, application state, the approval
    still live, the content and execution method unchanged, the destination's class), that the
    approval permits submitting, the rehearsal prerequisite, and that this is exactly the next
    step: never one repeated, skipped or out of order. Only then does it record the step
    (`step_authorized`) and commit, before the page is filled or the Next clicked, so a worker
    lost after the click leaves the record. It never stamps `disclosure_started_at` again and
    never counts against the pilot's limit. A refusal raises GateRefused (nothing written);
    LostAuthority propagates."""
    with _gate_session() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            ctx = _gate_checks(db, att)
            wizard = ctx.content.get("wizard")
            if (
                not wizard
                or att.disclosure_started_at is None
                or att.send_started_at is not None
                or phase not in STEP_PHASES
            ):
                raise GateRefused(WIZARD_STEP_ORDER, "wizard_step_order")
            if ctx.approval.scope != ApprovalScope.submit:
                raise GateRefused(WIZARD_REHEARSAL, "wizard_rehearsal")
            _gate_prerequisite(db, att, ctx, "disclosure")
            pages = len(wizard["pages"])
            expected = _expected_steps(pages)
            done = db.scalar(
                select(func.count())
                .select_from(AttemptEvent)
                .where(
                    AttemptEvent.attempt_id == att.id,
                    AttemptEvent.generation == att.generation,
                    AttemptEvent.kind == "step_authorized",
                )
            )
            if done >= len(expected) or (page, phase) != expected[done]:
                raise GateRefused(WIZARD_STEP_ORDER, "wizard_step_order")
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e), e.code) from None
        event(db, att, "step_authorized", page=page, phase=phase, pages=pages)
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
    reason_code: str | None = None,
    retire: str | None = None,
    retire_every: str | None = None,
    *,
    require_undisclosed: bool = False,
    reason: str | None = None,
) -> bool:
    """`app_target` may be a function of the locked application: an outcome that depends on the
    application's state decides it under the lock, never from an earlier read.
    `require_undisclosed` (D142): write nothing, and return False, once the disclosure gate was
    passed (a stop "before sending anything" would then be untrue). D142: an attempt abandoned on
    a multi-page form says so (`WIZARD_STOPPED`, with `reason`) and retires every live approval
    of the application, whatever the caller asked: it is never run again."""
    with SessionLocal() as db:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
        )
        if att is None or att.generation != gen or att.state not in from_states:
            return False
        if require_undisclosed and att.disclosure_started_at is not None:
            return False
        app = pk.lock_application(db, att.application_id)
        if (
            to == S.abandoned
            and tuple(from_states) == (S.claimed,)
            and att.disclosure_started_at is not None
            and _is_wizard(db, att)
        ):
            detail = WIZARD_STOPPED.format(k=_nexts(db, att), reason=reason or detail)
            retire_every = "wizard_draft_at_employer"
        target = app_target(app) if callable(app_target) else app_target
        _apply_outcome(db, att, app, to, target, detail, evidence, reason_code=reason_code,
                       retire=retire, retire_every=retire_every)  # fmt: skip
        db.commit()
        return True


def _apply_outcome(
    db: Session,
    att: ExecutionAttempt,
    app: Application,
    to: AttemptState,
    app_target: AppState | None,
    detail: str,
    evidence: list[dict] | None = None,
    *,
    retire: str | None = None,
    retire_every: str | None = None,
    reason_code: str | None = None,
) -> None:
    """End the attempt in the caller's transaction, which holds its row and application locks.
    `retire`: a reason code (RETIRED); the attempt's approval is retired with it here, so it
    cannot outlive the outcome that used it up, and the retirement is recorded only if the
    approval was still live. `retire_every` (D132): the same for every live approval of the
    application, including one given while this attempt ran (approving does not wait for a
    running attempt), recorded once. `reason_code`: a fixed code kept on the outcome event."""
    att.state, att.finished_at, att.outcome_detail = to, utcnow(), detail[:2000]
    att.lease_owner, att.lease_expires_at = None, None
    # D143: its verification request ends with it. Nothing may take a code for an attempt that
    # is over, and a code already typed is erased (lock order: the attempt, then its checkpoint).
    close_checkpoints(db, att.id)
    if app_target is not None:
        _app_to(db, app, app_target, Actor.worker, detail[:900])
    for ev in evidence or []:
        add_evidence(db, att, **ev)
    if retire is not None and retire_approval(db, att.approval_id, RETIRED[retire]):
        record(db, att.user_id, "package.approval_retired", "application",
               att.application_id, reason_code=retire)  # fmt: skip
    if retire_every is not None and retire_live_approvals(
        db, att.application_id, RETIRED[retire_every]
    ):
        record(db, att.user_id, "package.approval_retired", "application",
               att.application_id, reason_code=retire_every)  # fmt: skip
    extra = {"reason_code": reason_code} if reason_code else {}
    event(db, att, f"outcome_{to.value}", detail=detail[:500], **extra)
    record(db, att.user_id, f"execution.{to.value}", "application", att.application_id)


def close_checkpoints(db: Session, attempt_id) -> int:
    """D143: this attempt's verification requests that still wait for a code, or hold one not
    yet read, take no more and keep none. Called holding the attempt's row lock."""
    return db.execute(
        update(Checkpoint)
        .where(Checkpoint.attempt_id == attempt_id, Checkpoint.status.in_(("open", "submitted")))
        .values(status="expired", code=None)
    ).rowcount


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
    """Record evidence for an attempt this worker still holds (`_locked_attempt`). D143: that
    is progress, so it also renews the lease as a heartbeat does (never shortening a longer
    one): a long form that keeps disclosing is not taken for a lost worker."""
    with SessionLocal() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, (S.claimed, S.sending, S.awaiting_code))
        add_evidence(db, att, kind, data, strength)
        now = utcnow()
        renewed = now + timedelta(seconds=get_settings().lease_seconds)
        if att.lease_expires_at < renewed:
            att.lease_expires_at = renewed
        att.heartbeat_at = now
        db.commit()


def fail_safe(attempt_id, worker, gen, reason: str, code: str | None = None) -> bool:
    """Stopped before disclosing anything. The application waits for the user. D142: once the
    disclosure gate was passed this is never written; the attempt is abandoned instead (no
    current path calls it then; a guard for every adapter)."""
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.claimed,),
        S.failed_safe,
        AppState.needs_user_action,
        f"Stopped before sending anything: {reason}",
        reason_code=code,
        require_undisclosed=True,
    ) or _abandon_claimed(attempt_id, worker, gen, reason, code)


def _abandon_claimed(attempt_id, worker, gen, reason: str, code=None, retire_every=None) -> bool:
    return _finish(
        attempt_id,
        worker,
        gen,
        (S.claimed,),
        S.abandoned,
        AppState.needs_user_action,
        f"Stopped after entering data but before submitting: {reason}",
        reason_code=code,
        retire_every=retire_every,
        reason=reason,
    )


def abandon(
    attempt_id, worker, gen, reason: str, code: str | None = None, retire_every: str | None = None
) -> bool:
    """Data was disclosed (filled/uploaded) but not submitted. Never retried automatically.
    `retire_every` (D132): every live approval of the application is retired with that reason in
    the same transaction, so entering the same data again is a new approval. D142: on a
    multi-page form, always every live approval, and the outcome says pages may be saved at the
    employer (`_finish`)."""
    ok = _abandon_claimed(attempt_id, worker, gen, reason, code, retire_every)
    # Waiting for a code, the final click was already made: the approval that made it is used
    # up, so sending again is a new decision (D15).
    return ok or _finish(
        attempt_id,
        worker,
        gen,
        (S.awaiting_code,),
        S.abandoned,
        AppState.needs_user_action,
        f"Verification was not completed: {reason}",
        retire="verification_not_completed",
    )


def pause_for_form_change(attempt_id, worker, gen, reason: str, counts: dict) -> bool:
    """D132: before anything was entered, the employer's form no longer matches the approved one
    in a way a fresh read of the form can show (the adapter's `FormChanged`). One
    generation-fenced finish from `claimed`, in one transaction: the attempt ends failed_safe
    with its usual text; the application waits for the user; every live approval of the
    application is retired, including one given while the attempt ran; and an open pause
    records the form version the attempt ran against. While the pause is unresolved no approval
    can be given (package.approve). The attempt is never resumed or retried, and nothing waits on
    a worker, a lease or a browser. Returns False and writes nothing when the fence fails or
    data was already entered (never a pause then): the caller ends the attempt as before.

    Lock order: the attempt, then its application, then its approvals (as `_apply_outcome`);
    the pause rows come last, under them. An earlier unresolved pause of the application (there
    should be none: a pause blocks approval) is closed first, so the partial unique index can
    never turn this stop into an internal error."""
    with SessionLocal() as db:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
        )
        if (
            att is None
            or att.generation != gen
            or att.state != S.claimed
            or att.disclosure_started_at is not None
        ):
            return False
        app = pk.lock_application(db, att.application_id)
        _apply_outcome(db, att, app, S.failed_safe, AppState.needs_user_action,
                       f"Stopped before sending anything: {reason}",
                       retire_every="form_changed", reason_code="form_changed")  # fmt: skip
        now = utcnow()
        db.execute(
            update(ApplicationPause)
            .where(
                ApplicationPause.application_id == app.id,
                ApplicationPause.status.in_(PAUSE_UNRESOLVED),
            )
            .values(status="closed", resolution="superseded", resolved_at=now)
        )
        package = db.get(ApplicationPackage, att.package_id)
        dest = (package.content or {}).get("destination", {}) if package else {}
        safe = {k: int(counts.get(k) or 0) for k in ("new", "changed", "missing")}
        db.add(
            ApplicationPause(
                user_id=att.user_id,
                application_id=app.id,
                attempt_id=att.id,
                kind="form_changed",
                status="open",
                package_version=package.version if package else 0,
                package_hash=att.package_hash,
                form_version=dest.get("form_version"),
                detail=safe,
                created_at=now,
            )
        )
        event(db, att, "paused", reason_code="form_changed", **safe)
        db.commit()
        return True


def pause_after_entry(attempt_id, worker, gen, reason: str, required: int) -> bool:
    """D135: after filling, the page showed a question it reveals by its own logic (after an
    earlier answer), requires it, and no answer was approved for it. One generation-fenced finish
    from `claimed`, after the disclosure gate and before the send gate (nothing was submitted), in
    one transaction: the attempt ends `abandoned`, as any stop after entering data; the
    application waits for you; every live approval is retired (entering the data again is a new
    approval); and an open pause of kind `conditional_required` records the form version, with a
    count only. While it is open, every such question you can answer asks for your answer
    (package.load_context) and nothing can be approved; "Try this version again" ends it once they
    are answered. Never resumed or retried. Returns False and writes nothing when the fence fails
    (the caller then abandons the attempt as before).

    Lock order as `pause_for_form_change`: the attempt, its application, its approvals, then the
    pause rows."""
    with SessionLocal() as db:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
        )
        if (
            att is None
            or att.generation != gen
            or att.state != S.claimed
            or att.disclosure_started_at is None
            or att.send_started_at is not None
            or _is_wizard(db, att)  # D142: never a pause on a multi-page form (defence only)
        ):
            return False
        app = pk.lock_application(db, att.application_id)
        _apply_outcome(db, att, app, S.abandoned, AppState.needs_user_action,
                       f"Stopped after entering data but before submitting: {reason}",
                       retire_every="stopped_after_entry",
                       reason_code=pk.CONDITIONAL_REQUIRED)  # fmt: skip
        now = utcnow()
        db.execute(
            update(ApplicationPause)
            .where(
                ApplicationPause.application_id == app.id,
                ApplicationPause.status.in_(PAUSE_UNRESOLVED),
            )
            .values(status="closed", resolution="superseded", resolved_at=now)
        )
        package = db.get(ApplicationPackage, att.package_id)
        dest = (package.content or {}).get("destination", {}) if package else {}
        db.add(
            ApplicationPause(
                user_id=att.user_id,
                application_id=app.id,
                attempt_id=att.id,
                kind=pk.CONDITIONAL_REQUIRED,
                status="open",
                package_version=package.version if package else 0,
                package_hash=att.package_hash,
                form_version=dest.get("form_version"),
                detail={"required": int(required)},
                created_at=now,
            )
        )
        event(db, att, "paused", reason_code=pk.CONDITIONAL_REQUIRED, required=int(required))
        db.commit()
        return True


WIZARD_STOPPED = (
    "Stopped on the employer's multi-page form after entering data: up to {k} page(s) were "
    "sent there with Next, and the employer may keep what was entered as a draft. NoEfforts "
    "never made the final submit and will not run this application again: finish it on the "
    "employer's site. Why: {reason}"
)
WIZARD_POSSIBLY_SUBMITTED = (
    "Outcome unknown — check with the employer before doing anything: after a page's Next on "
    "the employer's multi-page form, {what}. The employer may hold this application. NoEfforts "
    "will not run it again."
)
WIZARD_SWEPT = (
    "Worker stopped on the employer's multi-page form after entering data: pages may be saved "
    "there as a draft, and the employer may hold the application. NoEfforts will not run it "
    "again: check with the employer, and finish it on their site."
)


def quarantine_after_step(attempt_id, worker, gen, what: str) -> bool:
    """D142: after a page's Next on a multi-page form, the page showed something that may mean
    the employer received the application (a confirmation, "already applied", or it left the
    form). The final click was never made, but nothing may run it again: one generation-fenced
    finish from `claimed`, in one transaction, ends the attempt `unknown` (reason code
    `wizard_possibly_submitted`), retires every live approval of the application, and moves the
    application to `submitted_unconfirmed` through `needs_user_action` (the transitions the
    sweeper uses), for you to reconcile. Never retried, never resent. Returns False and writes
    nothing unless the attempt is this worker's generation, still `claimed`, past the
    disclosure gate and not past the send gate, on a wizard, with at least one Next authorized.

    Lock order: the attempt, then its application, then its approvals (as `_apply_outcome`)."""
    with SessionLocal() as db:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
        )
        if (
            att is None
            or att.generation != gen
            or att.state != S.claimed
            or att.disclosure_started_at is None
            or att.send_started_at is not None
            or not _is_wizard(db, att)
            or _nexts(db, att) < 1
        ):
            return False
        app = pk.lock_application(db, att.application_id)
        detail = WIZARD_POSSIBLY_SUBMITTED.format(what=what)
        _apply_outcome(db, att, app, S.unknown, None, detail,
                       retire_every="wizard_draft_at_employer",
                       reason_code="wizard_possibly_submitted")  # fmt: skip
        if app.state == AppState.running:
            _app_to(db, app, AppState.needs_user_action, Actor.worker, detail[:900])
        if app.state == AppState.needs_user_action:
            _app_to(db, app, AppState.submitted_unconfirmed, Actor.worker, detail[:900])
        db.commit()
        return True


def retire_live_approvals(db: Session, application_id, reason: str) -> int:
    """Invalidate every approval of the application that is still live; how many were."""
    rows = db.scalars(
        select(PackageApproval)
        .where(
            PackageApproval.application_id == application_id,
            PackageApproval.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all()
    now = utcnow()
    for appr in rows:
        appr.invalidated_at, appr.invalidation_reason = now, reason
    return len(rows)


REHEARSAL_DONE = "Rehearsal finished: the form was filled and checked, and nothing was submitted."
# Why an outcome retired its approval (`_finish(retire=...)`), shown on the review page.
RETIRED = {
    "rehearsal_completed": "Used by a rehearsal: the form was filled and checked, and nothing "
    "was submitted. Approve again to submit, or to rehearse again.",
    # D15: after an unknown outcome the user said was not received, sending it again is a new
    # decision; the approval that sent it once never sends it twice.
    "reconciled_not_received": "Used by a submission whose outcome you reconciled as not "
    "received. Approve again to send it again.",
    "verification_not_completed": "Used by a submission the employer asked to verify with a "
    "code that was not completed. Approve again to send it again.",
    # D132: the employer's form no longer matched this package when it ran.
    "form_changed": "The employer's form no longer matched this package when it ran. Read the "
    "form again under Questions, answer what is new, then approve again.",
    # D132: the page no longer matched after your answers were entered on it; nothing was
    # submitted. Entering them again is a new decision.
    "stopped_after_entry": "Used by an attempt that entered your answers on the employer's page "
    "and stopped before submitting, because the page then no longer matched. Approve again to "
    "run it again.",
    # D142: an attempt entered the application on a multi-page form; it is never run again.
    "wizard_draft_at_employer": "Used by an attempt that entered this application on the "
    "employer's multi-page form, which may keep it as a draft or have received it. NoEfforts "
    "never runs it again: finish it on the employer's site.",
}


def finish_rehearsal(attempt_id, worker: str, gen: int) -> None:
    """A rehearsal (an approval to disclose only) ends here, before the send gate, and only
    through a gate: in one transaction, under the same locks, it repeats every check the send
    gate makes (authority, application state, the approval still live and locked, the content
    and the execution method unchanged, the destination's class), then checks that the evidence
    rows show a complete rehearsal (rehearsal.evidence_facts). Only then does it record what the
    rehearsal proved, end the attempt `rehearsed` and use its approval up, all in one commit.

    A refusal raises GateRefused (with a fixed code where there is one): the runner then ends the
    attempt `abandoned`, never `rehearsed`. LostAuthority propagates. Nothing is ever submitted,
    and the approval is never extended or turned into one to submit."""
    with _gate_session() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.claimed)
        try:
            ctx = _gate_checks(db, att, approval_lock="update")
            if ctx.approval.scope != ApprovalScope.disclose_only:
                raise GateRefused("this attempt is not a rehearsal")
            if att.disclosure_started_at is None or att.send_started_at is not None:
                raise GateRefused("the rehearsal did not run as approved")
            facts, code = rehearsal.evidence_facts(db, att, ctx.content)
            if code is not None:
                raise GateRefused(rehearsal.MESSAGES[code], code)
        except GateRefused as e:
            db.rollback()
            raise GateRefused(str(e), e.code) from None
        version = approved_binding(ctx.approval, ctx.content["destination"])["adapter_version"]
        db.add(
            RehearsalRecord(
                user_id=att.user_id,
                application_id=att.application_id,
                attempt_id=att.id,
                approval_id=att.approval_id,
                destination_class=att.destination_class,
                adapter=att.adapter,
                adapter_version=version,
                path_ref=att.path_ref,
                **facts,
            )
        )
        _apply_outcome(db, att, ctx.app, S.rehearsed, AppState.needs_user_action,
                       REHEARSAL_DONE, retire="rehearsal_completed")  # fmt: skip
        db.commit()


def confirmed(attempt_id, worker, gen, evidence: list[dict]) -> bool:
    # `unknown` is accepted too: a slow worker may still observe the receipt after the sweeper
    # gave up on it. Upgrading to confirmed never causes a send. Decided under the application
    # lock: still awaiting reconciliation, it is left for the user to confirm with the evidence;
    # reconciled as not received meanwhile, the receipt shows it was received.
    def target(app: Application) -> AppState | None:
        return None if app.state == AppState.submitted_unconfirmed else AppState.submitted_confirmed

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


def take_code(
    checkpoint_id, attempt_id, worker, gen, watch_seconds: int | None = None
) -> tuple[str | None, str]:
    """Worker side: returns (code, status). The code is erased from the database as it is read.
    D143: a code handed to the worker is about to be entered, so the lease is extended to cover
    the watch for its answer (`watch_seconds`, the adapter's `code_watch_seconds`, bounded as
    the send lease is, plus 30s; never shortened). The wait's own lease ends 30s after the
    request does, and a code typed late in the wait would otherwise be answered after it."""
    with SessionLocal() as db:
        att = _locked_attempt(db, attempt_id, worker, gen, S.awaiting_code)
        cp = db.scalar(select(Checkpoint).where(Checkpoint.id == checkpoint_id).with_for_update())
        # D143: a held code is handed over even if the request's time has run out since: it was
        # accepted in time (`submit_code` refuses after the expiry), and the lease covers it.
        if cp.status == "open" and cp.expires_at <= utcnow():
            cp.status, cp.code = "expired", None
            db.commit()
            return None, "expired"
        if cp.status != "submitted":
            db.commit()
            return None, cp.status
        code, cp.code, cp.status = cp.code, None, "consumed"
        covered = utcnow() + timedelta(seconds=_watch_covered(watch_seconds) + 30)
        if att.lease_expires_at < covered:
            att.lease_expires_at = covered
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
    # D143: only while its attempt still waits for it. An attempt that ended closes its request
    # (`close_checkpoints`); this refuses one left open by anything else. Read without a lock:
    # the checkpoint row is locked alone here (lock order), and an attempt that ends after this
    # read erases the code as it closes the request.
    state = db.scalar(select(ExecutionAttempt.state).where(ExecutionAttempt.id == cp.attempt_id))
    if state != S.awaiting_code:
        raise PermissionError("This verification request is not waiting for a code.")
    if not _CODE.match(code or ""):
        raise ValueError("Codes are 4–12 letters, digits or dashes.")
    cp.code, cp.status = code, "submitted"
    record(db, user_id, "checkpoint.code_submitted", "checkpoint", cp.id, round=round_)
    return cp


# --------------------------------------------------------------------------------------------
# Cancellation and recovery


CANCELLED_AFTER_ENTRY = (
    "Cancelled by you before anything was submitted. The worker stops at its next check: it may "
    "type into a few more fields first, but it hands over no further document and never "
    "submits. What it had already entered on the employer's page stays entered, and a document "
    "it was handing over when you cancelled may have been received."
)


def _active_attempt(db: Session, app_id, *, nowait: bool = False) -> ExecutionAttempt | None:
    return db.scalar(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app_id, ExecutionAttempt.state.in_(ACTIVE))
        .with_for_update(nowait=nowait)
        .execution_options(populate_existing=True)
    )


def cancel(db: Session, app: Application) -> str:
    """User cancel. Takes the same locks as the gates, in the same order (the attempt, then the
    application), so it is either before a gate (and stops it) or after it: after the
    disclosure gate it still cancels (the worker stops at its next step, but what it had
    already entered stays entered); after the send gate it is refused, since the submission
    may be in flight. D142: on a multi-page form it is refused from the disclosure gate on
    (`wizard_in_progress`): each page's Next may already be saved, or even received, at the
    employer, and a cancel would end the attempt with nothing recorded of a Next in flight.
    Revoking stops it instead: the attempt stays held, so its next step gate ends it with the
    wizard outcome, and a Next in flight still reaches its quarantine."""
    att = _active_attempt(db, app.id)  # waits for a gate holding the attempt
    pk.lock_application(db, app.id)
    db.refresh(app)  # as locked: a copy loaded before the wait would fail its update (stale)
    if att is None:
        # Queued while this waited for the application lock: taken without waiting (it may be
        # being claimed), else the user tries again. Never a lock against the order that waits.
        try:
            with db.begin_nested():
                att = _active_attempt(db, app.id, nowait=True)
        except DBAPIError as e:
            if getattr(e.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
                raise
            raise PermissionError(
                "The application changed while it was being cancelled. Try again."
            ) from None
    if att is not None and att.state in (S.sending, S.awaiting_code):
        raise PermissionError(
            "Submission may already be in flight; it cannot be cancelled. "
            "Wait for the outcome or reconcile."
        )
    if (
        att is not None
        and att.state == S.claimed
        and att.disclosure_started_at is not None
        and _is_wizard(db, att)
    ):
        raise PermissionError(str(pk.refused("wizard_in_progress")))
    if att is not None:
        att.cancel_requested = True
        att.state, att.finished_at = S.cancelled, utcnow()
        # D143: after the disclosure gate the worker may already have entered answers or
        # uploaded a document, and one in flight when you cancelled is not recorded.
        att.outcome_detail = (
            CANCELLED_AFTER_ENTRY
            if att.disclosure_started_at is not None
            else "Cancelled by you before anything was submitted."
        )
        event(db, att, "cancelled")
    transition(db, app, AppState.cancelled, Actor.user, "Cancelled")
    return "cancelled"


def stop_for_revoke(db: Session, app: Application) -> str:
    """C13 (D65): what revoking does to an attempt in progress, under the cancel lock order (the
    attempt, then the application). An attempt no worker has taken yet is cancelled at once,
    and the application waits for an approval again ("cancelled"). One a worker holds before
    the send gate is left to the gates, which refuse a revoked approval ("stopping"). After the
    send gate the submission may be in flight: revoking is refused. "none": no attempt.
    An attempt the sweeper put back in the queue (its worker stopped before entering anything)
    is pending while its application still shows running: it is cancelled the same way, and
    the application moves as for a refused claim (D146 review: it used to fail, nothing was
    revoked, and the attempt would have run later)."""
    att = _active_attempt(db, app.id)  # waits for a gate holding the attempt
    pk.lock_application(db, app.id)
    db.refresh(app)
    if att is None:
        return "none"
    if att.state in (S.sending, S.awaiting_code):
        raise pk.refused("revoke_in_flight")
    if att.state != S.pending:
        return "stopping"
    att.cancel_requested = True
    att.state, att.finished_at = S.cancelled, utcnow()
    att.outcome_detail = "Approval revoked before a worker picked this up; nothing was sent."
    event(db, att, "cancelled")
    _claim_refused(db, app, "Approval revoked")  # queued: approval again; running: you
    return "cancelled"


def stop_for_pause(db: Session, user_id) -> dict:
    """D134: pausing the standing rule stops what it queued, under the cancel lock order (each
    attempt, then its application). An attempt no worker has taken is cancelled at once; one a
    worker holds is cancelled too, and the worker stops at its next step (anything it had already
    entered on the page stays entered, as with Cancel). One past the send gate may be in flight:
    it is left alone and counted. What you queued yourself is never touched."""
    out = {"cancelled": 0, "stopped": 0, "in_flight": 0}
    ids = db.scalars(
        select(ExecutionAttempt.id).where(
            ExecutionAttempt.user_id == user_id,
            ExecutionAttempt.queued_by_rule.is_(True),
            ExecutionAttempt.state.in_(ACTIVE),
        )
    ).all()
    for att_id in ids:
        att = db.scalar(  # waits for a gate holding the attempt
            select(ExecutionAttempt).where(ExecutionAttempt.id == att_id).with_for_update()
        )
        app = pk.lock_application(db, att.application_id)
        db.refresh(app)
        if att.state in (S.sending, S.awaiting_code):
            out["in_flight"] += 1
            continue
        if att.state not in (S.pending, S.claimed):
            continue  # it finished while this waited
        held = att.state == S.claimed
        att.cancel_requested = True
        att.state, att.finished_at = S.cancelled, utcnow()
        att.outcome_detail = (
            "Your automatic rule was paused while a worker held this; it stops at its next step. "
            "Anything already entered on the page stays entered."
            if held and att.disclosure_started_at is not None
            else "Your automatic rule was paused before anything was sent."
        )
        event(db, att, PAUSE_STOPPED)
        _claim_refused(db, app, "Your automatic rule was paused")
        out["stopped" if held else "cancelled"] += 1
    return out


def sweep(publish_new: bool = True) -> dict:
    """Recover attempts whose worker vanished. Never takes over a possibly-submitting attempt.
    Each attempt is recovered in its own savepoint: one that cannot be (counted in `errors`)
    stays as it was for the next sweep and never stops the others."""
    out = {"repended": 0, "abandoned": 0, "unknown": 0, "failed": 0, "errors": 0}
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
            att_id = att.id
            try:
                with db.begin_nested():
                    out[_sweep_one(db, att, publish_new)] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("sweep: attempt %s not recovered (%s)", att_id, type(e).__name__)
                out["errors"] += 1
        db.commit()
    out["checkpoints_closed"] = close_stale_checkpoints()
    return out


CHECKPOINT_GRACE_SECONDS = 60  # past its time before the sweeper closes a request itself


def close_stale_checkpoints() -> int:
    """D143: a verification request must not outlive its use. In its own transaction, holding
    no attempt lock (so it can never wait on a worker inside the lock order), close every
    request still open, or holding a code, whose attempt no longer waits for a code, or whose
    time ran out more than a minute ago (a worker still polling closes its own sooner, and
    reads "expired" either way). The code is erased. How many were closed."""
    waiting = select(ExecutionAttempt.id).where(ExecutionAttempt.state == S.awaiting_code)
    cutoff = utcnow() - timedelta(seconds=CHECKPOINT_GRACE_SECONDS)
    with SessionLocal() as db:
        n = db.execute(
            update(Checkpoint)
            .where(
                Checkpoint.status.in_(("open", "submitted")),
                or_(Checkpoint.attempt_id.not_in(waiting), Checkpoint.expires_at < cutoff),
            )
            .values(status="expired", code=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        db.commit()
    return n


def _sweep_one(db: Session, att: ExecutionAttempt, publish_new: bool) -> str:
    app = pk.lock_application(db, att.application_id)
    att.lease_owner, att.lease_expires_at = None, None
    if att.state in (S.sending, S.awaiting_code):
        att.state, att.finished_at = S.unknown, utcnow()
        att.outcome_detail = "Worker stopped after the submit step began; outcome unknown."
        # A code typed for the dead worker is erased, and the checkpoint takes no more.
        close_checkpoints(db, att.id)
        if app.state in (AppState.submitting, AppState.needs_user_action):
            _app_to(db, app, AppState.submitted_unconfirmed, Actor.system, att.outcome_detail)
        event(db, att, "swept_unknown")
        return "unknown"
    if att.disclosure_started_at is not None:
        att.state, att.finished_at = S.abandoned, utcnow()
        att.outcome_detail = (
            "Worker stopped after entering data but before submitting. Not retried automatically."
        )
        if _is_wizard(db, att):
            # D142: pages may be saved at the employer, which may even hold the application;
            # every live approval is retired (the attempt, then the application, then them).
            att.outcome_detail = WIZARD_SWEPT
            if retire_live_approvals(db, att.application_id, RETIRED["wizard_draft_at_employer"]):
                record(db, att.user_id, "package.approval_retired", "application",
                       att.application_id, reason_code="wizard_draft_at_employer")  # fmt: skip
        _app_to(db, app, AppState.needs_user_action, Actor.system, att.outcome_detail)
        event(db, att, "swept_abandoned")
        return "abandoned"
    if att.retry_count < get_settings().max_safe_retries:
        att.state, att.retry_count = S.pending, att.retry_count + 1
        event(db, att, "swept_repended", retry=att.retry_count)
        if publish_new:
            db.add(OutboxMessage(topic=TOPIC_EXECUTE, attempt_id=att.id))
        return "repended"
    att.state, att.finished_at = S.failed_safe, utcnow()
    att.outcome_detail = "Worker kept stopping before sending anything."
    _app_to(db, app, AppState.failed_retryable, Actor.system, att.outcome_detail)
    event(db, att, "swept_failed")
    return "failed"


# --------------------------------------------------------------------------------------------
# Evidence lifecycle


def purge_expired_evidence() -> int:
    """Delete evidence past its retention date. Runs daily from Celery beat."""
    with SessionLocal() as db:
        n = db.execute(delete(Evidence).where(Evidence.retain_until < utcnow())).rowcount
        db.commit()
        return n


def withdraw_rehearsal(db: Session, app: Application, attempt_id) -> RehearsalRecord:
    """The user withdraws a rehearsal: its record is revoked (never edited back), so it no longer
    meets the prerequisite. Takes the application lock, then the record; a gate relying on the
    record holds it FOR SHARE, so a withdrawal is either before that gate (and refuses it) or
    after it. Idempotent. LookupError if the attempt is not this application's rehearsal."""
    pk.lock_application(db, app.id)
    rec = db.scalar(
        select(RehearsalRecord)
        .where(
            RehearsalRecord.attempt_id == attempt_id,
            RehearsalRecord.application_id == app.id,
            RehearsalRecord.user_id == app.user_id,
        )
        .with_for_update()
    )
    if rec is None:
        raise LookupError("Rehearsal")
    if rec.revoked_at is None:
        rec.revoked_at, rec.revoked_reason = utcnow(), "withdrawn_by_user"
        record(db, app.user_id, "rehearsal.withdraw", "application", app.id)
    return rec


def delete_application_evidence(db: Session, app: Application) -> int:
    """User-requested deletion. Refused while an attempt is active (it may still write). A
    rehearsal record cannot be checked against evidence that is gone, so the application's
    records are revoked in the same transaction (under the application lock the gates take)."""
    pk.lock_application(db, app.id)
    active = db.scalar(
        select(ExecutionAttempt.id).where(
            ExecutionAttempt.application_id == app.id, ExecutionAttempt.state.in_(ACTIVE)
        )
    )
    if active is not None:
        raise PermissionError("An attempt is still running; wait for it to finish.")
    revoked = db.execute(
        update(RehearsalRecord)
        .where(
            RehearsalRecord.application_id == app.id,
            RehearsalRecord.user_id == app.user_id,
            RehearsalRecord.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="evidence_deleted")
    ).rowcount
    n = db.execute(
        delete(Evidence).where(Evidence.application_id == app.id, Evidence.user_id == app.user_id)
    ).rowcount
    record(db, app.user_id, "evidence.delete", "application", app.id, rows=n,
           rehearsals_revoked=revoked)  # fmt: skip
    return n
