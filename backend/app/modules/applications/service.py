from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.applications import states
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.states import Actor, AppState, Outcome, Refused, Source
from app.modules.audit.service import record
from app.modules.execution.models import AttemptState, ExecutionAttempt

# Fixed event reasons: what the user wrote goes to evidence_note, never into the label (D53).
CONFIRMED_BY_YOU = "Confirmed by you"
RECONCILED_RECEIVED = "Reconciled as received"
RECONCILED_NOT_RECEIVED = "Reconciled as not received"


def transition(
    db: Session,
    app: Application,
    target: AppState,
    actor: Actor,
    reason: str | None = None,
    *,
    evidence_note: str | None = None,
) -> None:
    """Validate and apply a transition. The version column makes concurrent writers conflict.
    The event's source follows from the target and the actor (D53); it is never passed in."""
    states.check(app.state, target, actor)
    note = (evidence_note or "").strip() or None
    if (
        target == AppState.submitted_confirmed
        and actor == Actor.user
        and len(note or "") < states.EVIDENCE_MIN
    ):
        raise states.IllegalTransition("A confirmation by you needs what you checked")
    db.add(
        ApplicationEvent(
            application_id=app.id,
            kind="state_change",
            from_state=app.state,
            to_state=target,
            actor=actor,
            reason=reason,
            source=states.event_source(target, actor),
            evidence_note=note,
        )
    )
    app.state = target
    app.state_changed_at = utcnow()


def lock_submission(db: Session, app: Application) -> list[AttemptState]:
    """D46: the application's attempts (by id), then the application, re-read as locked. A
    worker recording the employer's receipt takes the attempt first too, so the two are
    ordered, never interleaved."""
    from app.modules.preparation import package as pk

    attempts = db.scalars(
        select(ExecutionAttempt.state)
        .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.user_id == app.user_id)
        .order_by(ExecutionAttempt.id)
        .with_for_update()
    ).all()
    pk.lock_application(db, app.id)
    db.refresh(app)  # as locked: a concurrent change is seen, not overwritten
    return list(attempts)


def submission_facts(db: Session, app: Application) -> tuple[bool, bool, bool]:
    """(a receipt is recorded on one of its attempts, it ever entered a submitted state, its
    latest entry into submitted_unconfirmed rests on the user). The caller checked ownership."""
    receipt = db.scalar(
        select(ExecutionAttempt.id)
        .where(
            ExecutionAttempt.application_id == app.id,
            ExecutionAttempt.user_id == app.user_id,
            ExecutionAttempt.state == AttemptState.confirmed,
        )
        .limit(1)
    )
    entries = db.execute(
        select(ApplicationEvent.to_state, ApplicationEvent.actor, ApplicationEvent.source)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(
            ApplicationEvent.application_id == app.id,
            Application.user_id == app.user_id,
            ApplicationEvent.kind == "state_change",
            ApplicationEvent.to_state.in_(states.SUBMITTED),
        )
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    ).all()
    unconfirmed = [e for e in entries if e.to_state == AppState.submitted_unconfirmed]
    last = unconfirmed[-1] if unconfirmed else None
    by_user = last is not None and states.claimed_by_user(last.source, last.actor)
    return receipt is not None, bool(entries), by_user


def ever_submitted(db: Session, app: Application) -> bool:
    receipt, entered, _ = submission_facts(db, app)
    return states.reached_submission(app.state, entered, receipt)


def record_outcome(
    db: Session,
    app: Application,
    outcome: Outcome,
    *,
    occurred_on: date | None = None,
    note: str | None = None,
) -> bool:
    """What the user reports the employer did, as one insert-only event (D53). The caller holds
    the application lock and has refreshed `app`. Never changes a state. False: nothing new."""
    if outcome == app.outcome and occurred_on is None and note is None:
        return False
    if (
        outcome not in states.OUTCOMES_BEFORE_SUBMISSION
        and states.OUTCOME_BEFORE_SUBMISSION == "refuse"
        and not ever_submitted(db, app)
    ):
        raise Refused("outcome_before_submission")
    db.add(
        ApplicationEvent(
            application_id=app.id,
            kind="outcome",
            actor=Actor.user,
            reason=f"outcome: {app.outcome.value} → {outcome.value}",
            from_outcome=app.outcome,
            to_outcome=outcome,
            source=Source.user_reported,
            occurred_on=occurred_on,
            evidence_note=note,
        )
    )
    app.outcome = outcome
    record(db, app.user_id, "application.outcome", "application", app.id, to=outcome.value,
           source=Source.user_reported.value)  # fmt: skip
    return True
