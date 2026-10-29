import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.db import get_db, utcnow
from app.core.errors import bad_request, conflict, not_found
from app.modules.applications import funnel, states
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.service import (
    CONFIRMED_BY_YOU,
    RECONCILED_NOT_RECEIVED,
    RECONCILED_RECEIVED,
    lock_submission,
    record_outcome,
    submission_facts,
    transition,
)
from app.modules.applications.states import (
    Actor,
    AppState,
    Basis,
    IllegalTransition,
    Outcome,
    Refused,
    Source,
    check,
)
from app.modules.audit.service import record
from app.modules.execution.models import AttemptState, ExecutionAttempt
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation.models import PackageApproval

router = APIRouter(prefix="/applications", tags=["applications"])


class AppCreate(BaseModel):
    job_id: uuid.UUID


def _strip(v):
    """The same strip as applications.service.transition(), so both layers measure one string."""
    return v.strip() if isinstance(v, str) else v


def _no_nul(v: str) -> str:
    if "\x00" in v:  # PostgreSQL text cannot hold NUL
        raise ValueError("must not contain a NUL character")
    return v


# What the user writes, stripped; never copied into audit rows (D53). BeforeValidator runs
# before the length constraints.
Note = Annotated[
    str,
    StringConstraints(max_length=states.EVIDENCE_MAX),
    BeforeValidator(_strip),
    AfterValidator(_no_nul),
]
Evidence = Annotated[
    str,
    StringConstraints(min_length=states.EVIDENCE_MIN, max_length=states.EVIDENCE_MAX),
    BeforeValidator(_strip),
    AfterValidator(_no_nul),
]
Text = Annotated[str, AfterValidator(_no_nul)]


class TransitionIn(BaseModel):
    to: AppState
    reason: Text | None = Field(default=None, max_length=1000)
    evidence: Note | None = None  # what you checked: needed to confirm a submission yourself


class ReconcileIn(BaseModel):
    finding: Literal["received", "not_received"]
    # What the user actually checked, e.g. "Called the employer's HR on 3 May; no application".
    evidence: Evidence
    confirm_not_received: bool = False


class AppPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a source is NoEfforts' to set, never a client's
    outcome: Outcome | None = None
    occurred_on: date | None = None  # the day the user says the employer acted
    evidence_note: Note | None = None  # a private note on the outcome
    notes: Text | None = Field(default=None, max_length=10_000)

    @field_validator("evidence_note")
    @classmethod
    def _blank(cls, v):
        return v or None

    @model_validator(mode="after")
    def _with_outcome(self):
        detail = self.occurred_on is not None or self.evidence_note is not None
        if self.outcome is None and detail:
            raise ValueError("A date or a note is recorded with an outcome: choose the outcome too")
        if self.outcome == Outcome.none and self.occurred_on is not None:
            raise ValueError("Clearing the outcome takes no date")
        if self.occurred_on is not None and self.occurred_on > utcnow().date() + timedelta(days=1):
            raise ValueError("The date cannot be in the future")
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: str
    from_state: AppState | None
    to_state: AppState | None
    actor: Actor
    reason: str | None
    from_outcome: Outcome | None = None
    to_outcome: Outcome | None = None
    source: Source | None = None
    occurred_on: date | None = None
    evidence_note: str | None = None  # served to its owner only
    created_at: datetime


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str | None
    employer: str | None
    location: str | None
    url: str | None
    ats_provider: str


class LastAttempt(BaseModel):
    state: str  # execution AttemptState
    approval_scope: str | None  # submit, or disclose_only (a rehearsal)


class AppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job: JobSummary
    state: AppState
    state_changed_at: datetime
    outcome: Outcome
    notes: str | None
    created_at: datetime
    last_attempt: LastAttempt | None = None
    # receipt whenever an attempt is confirmed; otherwise from the current submitted state and
    # who entered it; null otherwise (D53)
    submission: Basis | None = None
    reached_submission: bool = False


class AppDetail(AppOut):
    outcome_choices: list[Outcome]
    events: list[EventOut]


class FunnelStage(BaseModel):
    stage: str
    count: int
    of: int
    of_stage: str


class SubmittedSplit(BaseModel):
    total: int
    receipt: int
    user_claimed: int
    unconfirmed: int
    confirmed_by_you: int
    applied_by_you: int


class FunnelOut(BaseModel):
    """Counts and their denominators only; no rate (D53)."""

    tracked: int
    stages: list[FunnelStage]
    submitted: SubmittedSplit
    no_response_after_days: int
    min_submissions_to_compare: int
    too_few_to_compare: bool
    note: str | None
    outcome_before_submission: int


def _owned(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise not_found("Application")
    return app


def _last_attempt(db: Session, app: Application) -> dict | None:
    att = db.scalar(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.user_id == app.user_id)
        .order_by(ExecutionAttempt.created_at.desc())
        .limit(1)
    )
    if att is None:
        return None
    scope = db.scalar(select(PackageApproval.scope).where(PackageApproval.id == att.approval_id))
    return {"state": att.state, "approval_scope": scope}


def _out(db: Session, app: Application, detail: bool = False):
    job = db.get(Job, app.job_id)
    receipt, entered, by_user = submission_facts(db, app)
    reached = states.reached_submission(app.state, entered, receipt)
    base = dict(
        id=app.id,
        job=JobSummary.model_validate(job),
        state=app.state,
        state_changed_at=app.state_changed_at,
        outcome=app.outcome,
        notes=app.notes,
        created_at=app.created_at,
        last_attempt=_last_attempt(db, app),
        submission=states.submission_basis(app.state, receipt, by_user),
        reached_submission=reached,
    )
    if not detail:
        return AppOut(**base)
    events = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    ).all()
    flag = states.OUTCOME_BEFORE_SUBMISSION == "flag"
    choices = [o for o in Outcome if reached or flag or o in states.OUTCOMES_BEFORE_SUBMISSION]
    return AppDetail(
        **base, outcome_choices=choices, events=[EventOut.model_validate(e) for e in events]
    )


@router.post("", response_model=AppOut, status_code=status.HTTP_201_CREATED)
def create_application(
    body: AppCreate,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Idempotent: returns the existing application for this job if there is one."""
    job = db.get(Job, body.job_id)
    if job is None or job.user_id != user.id:
        raise not_found("Job")
    now = utcnow()
    new_id = db.execute(
        insert(Application)
        .values(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=job.id,
            state=AppState.draft,
            state_changed_at=now,
            outcome=Outcome.none,
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_application_user_job")
        .returning(Application.id)
    ).scalar_one_or_none()
    if new_id is None:
        response.status_code = status.HTTP_200_OK
        app = db.scalar(
            select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
        )
    else:
        app = db.get(Application, new_id)
        db.add(
            ApplicationEvent(
                application_id=app.id,
                kind="state_change",
                from_state=None,
                to_state=AppState.draft,
                actor=Actor.user,
                reason="created",
            )
        )
        record(db, user.id, "application.create", "application", app.id)
    db.commit()
    return _out(db, app)


@router.get("", response_model=list[AppOut])
def list_applications(
    state: AppState | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Application).where(Application.user_id == user.id)
    if state:
        stmt = stmt.where(Application.state == state)
    apps = db.scalars(stmt.order_by(Application.state_changed_at.desc())).all()
    return [_out(db, a) for a in apps]


@router.get("/funnel", response_model=FunnelOut)  # before /{app_id}, which would take "funnel"
def get_funnel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The user's own counts, computed now; writes nothing (D53)."""
    return funnel.for_user(db, user.id, utcnow())


@router.get("/{app_id}", response_model=AppDetail)
def get_application(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return _out(db, _owned(db, user, app_id), detail=True)


@router.post("/{app_id}/transition", response_model=AppDetail)
def transition_application(
    app_id: uuid.UUID,
    body: TransitionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    app = _owned(db, user, app_id)
    if body.to == AppState.cancelled:
        # Cancellation goes through execution so it is serialized with the final send gate.
        from app.modules.execution.service import cancel

        try:
            check(app.state, body.to, Actor.user)
            cancel(db, app)
        except PermissionError as e:
            db.rollback()
            raise conflict(str(e)) from None
        except IllegalTransition as e:
            db.rollback()
            raise bad_request(str(e)) from None
        db.commit()
        return _out(db, app, detail=True)
    from app.modules.preparation.package import execution_owns_state, refused

    if execution_owns_state(db, app):
        raise conflict(str(refused("submission_in_progress")))
    if body.to == AppState.submitted_confirmed:
        return _confirm_by_user(db, user, app, body.evidence)
    try:
        check(app.state, body.to, Actor.user)
        if body.to == AppState.queued:
            # Queueing needs a live approval of the *current* package content.
            from app.modules.preparation.package import (
                ApprovalError,
                NoForm,
                require_valid_approval,
            )

            try:
                require_valid_approval(db, app)
            except (ApprovalError, NoForm) as e:
                db.commit()
                raise conflict(str(e)) from None
        transition(db, app, body.to, Actor.user, body.reason)
        if body.to == AppState.queued:
            # Same transaction: the attempt and its outbox message exist iff the queue happened.
            from app.modules.execution.policy import BindingChanged, UnsupportedDestination
            from app.modules.execution.service import enqueue, retire_approval

            try:
                enqueue(db, app)
            except BindingChanged as e:
                db.rollback()  # not queued; only the outdated approval is retired
                retire_approval(db, e.approval_id, "execution method changed after approval")
                record(db, user.id, "package.approval_retired", "application", app.id,
                       reason_code="execution_method_changed")  # fmt: skip
                db.commit()
                raise conflict(str(e)) from None
            except UnsupportedDestination as e:
                db.rollback()
                raise conflict(str(e)) from None
            except ApprovalError as e:  # e.g. the rehearsal prerequisite (E6); nothing queued
                db.rollback()
                raise conflict(str(e)) from None
        record(db, user.id, "application.transition", "application", app.id, to=body.to.value)
        db.commit()
    except IllegalTransition as e:
        db.rollback()
        raise bad_request(str(e)) from None
    except StaleDataError:
        db.rollback()
        raise conflict("Application changed concurrently; reload and try again") from None
    return _out(db, app, detail=True)


def _confirm_by_user(db: Session, user: User, app: Application, evidence: str | None):
    """The user confirms a submission, saying what they checked; recorded as their statement,
    never as an employer receipt (D53)."""
    try:
        if not states.USER_CONFIRMS_THROUGH_TRANSITION:
            raise Refused("confirm_through_reconcile")
        lock_submission(db, app)
        check(app.state, AppState.submitted_confirmed, Actor.user)
        if len(evidence or "") < states.EVIDENCE_MIN:
            raise Refused("evidence_required")
        transition(db, app, AppState.submitted_confirmed, Actor.user, CONFIRMED_BY_YOU,
                   evidence_note=evidence)  # fmt: skip
        record(db, user.id, "application.transition", "application", app.id,
               to=AppState.submitted_confirmed.value)  # fmt: skip
        db.commit()
    except (IllegalTransition, Refused) as e:
        db.rollback()
        raise bad_request(str(e)) from None
    except StaleDataError:
        db.rollback()
        raise conflict("Application changed concurrently; reload and try again") from None
    return _out(db, app, detail=True)


@router.post("/{app_id}/reconcile", response_model=AppDetail)
def reconcile_application(
    app_id: uuid.UUID,
    body: ReconcileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Resolve an uncertain submission. There is no one-click resubmit.

    `received` confirms it. `not_received` requires the user to say what they checked and to
    confirm explicitly; it then becomes retryable, and re-queueing still needs a fresh approval.
    """
    from app.modules.execution.service import RETIRED, retire_approval

    app = _owned(db, user, app_id)
    # D46: its attempts, then the application, then its approvals. A slow worker recording the
    # employer's receipt locks the attempt first too, so the two are ordered, never interleaved.
    attempts = lock_submission(db, app)
    if app.state != AppState.submitted_unconfirmed:
        raise bad_request("Only submissions with an unknown outcome can be reconciled")
    if body.finding == "not_received" and AttemptState.confirmed in attempts:
        raise conflict("NoEfforts recorded the employer's confirmation of this submission since: "
                       "it was received. Reconcile it as received.")  # fmt: skip
    if body.finding == "not_received" and not body.confirm_not_received:
        raise bad_request("Confirm that you checked and the employer did not receive it")
    received = body.finding == "received"
    try:  # a backstop: the request types already refuse evidence transition() would refuse
        if received:
            transition(db, app, AppState.submitted_confirmed, Actor.user, RECONCILED_RECEIVED,
                       evidence_note=body.evidence)  # fmt: skip
        else:
            transition(db, app, AppState.failed_retryable, Actor.system, RECONCILED_NOT_RECEIVED,
                       evidence_note=body.evidence)  # fmt: skip
    except IllegalTransition as e:
        db.rollback()
        raise bad_request(str(e)) from None
    if not received:
        # D15: re-queueing needs a fresh approval. The one that sent it is used up here.
        live = db.scalars(
            select(PackageApproval.id).where(
                PackageApproval.application_id == app.id, PackageApproval.invalidated_at.is_(None)
            )
        )
        reason = "reconciled_not_received"
        if any([retire_approval(db, a, RETIRED[reason]) for a in live]):
            record(db, user.id, "package.approval_retired", "application", app.id,
                   reason_code=reason)  # fmt: skip
    record(db, user.id, "application.reconcile", "application", app.id, finding=body.finding)
    db.commit()
    return _out(db, app, detail=True)


@router.patch("/{app_id}", response_model=AppDetail)
def patch_application(
    app_id: uuid.UUID,
    body: AppPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.modules.preparation.package import lock_application

    app = _owned(db, user, app_id)
    try:
        lock_application(db, app.id)  # D46: the application only; it decides on what is locked
        db.refresh(app)
        if body.outcome is not None:
            record_outcome(db, app, body.outcome, occurred_on=body.occurred_on,
                           note=body.evidence_note)  # fmt: skip
        if "notes" in body.model_fields_set:
            app.notes = body.notes
        db.commit()
    except Refused as e:
        db.rollback()  # nothing is written, not even the notes
        raise bad_request(str(e)) from None
    except StaleDataError:
        db.rollback()
        raise conflict("Application changed concurrently; reload and try again") from None
    return _out(db, app, detail=True)
