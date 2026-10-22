import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.db import get_db, utcnow
from app.core.errors import bad_request, conflict, not_found
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.service import transition
from app.modules.applications.states import (
    Actor,
    AppState,
    IllegalTransition,
    Outcome,
    check,
)
from app.modules.audit.service import record
from app.modules.execution.models import ExecutionAttempt
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation.models import PackageApproval

router = APIRouter(prefix="/applications", tags=["applications"])


class AppCreate(BaseModel):
    job_id: uuid.UUID


class TransitionIn(BaseModel):
    to: AppState
    reason: str | None = Field(default=None, max_length=1000)


class ReconcileIn(BaseModel):
    finding: Literal["received", "not_received"]
    # What the user actually checked, e.g. "Called the employer's HR on 3 May; no application".
    evidence: str = Field(min_length=15, max_length=2000)
    confirm_not_received: bool = False


class AppPatch(BaseModel):
    outcome: Outcome | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: str
    from_state: AppState | None
    to_state: AppState | None
    actor: Actor
    reason: str | None
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


class AppDetail(AppOut):
    events: list[EventOut]


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
    base = dict(
        id=app.id,
        job=JobSummary.model_validate(job),
        state=app.state,
        state_changed_at=app.state_changed_at,
        outcome=app.outcome,
        notes=app.notes,
        created_at=app.created_at,
        last_attempt=_last_attempt(db, app),
    )
    if not detail:
        return AppOut(**base)
    events = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.created_at)
    ).all()
    return AppDetail(**base, events=[EventOut.model_validate(e) for e in events])


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
    from app.modules.preparation.package import execution_owns_state

    if execution_owns_state(db, app):
        raise conflict("A submission is in progress; wait for it to finish or cancel it.")
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
    app = _owned(db, user, app_id)
    if app.state != AppState.submitted_unconfirmed:
        raise bad_request("Only submissions with an unknown outcome can be reconciled")
    if body.finding == "received":
        transition(
            db,
            app,
            AppState.submitted_confirmed,
            Actor.user,
            f"Reconciled as received: {body.evidence}",
        )
    else:
        if not body.confirm_not_received:
            raise bad_request("Confirm that you checked and the employer did not receive it")
        transition(
            db,
            app,
            AppState.failed_retryable,
            Actor.system,
            f"User reconciled as not received: {body.evidence}",
        )
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
    app = _owned(db, user, app_id)
    if body.outcome is not None and body.outcome != app.outcome:
        db.add(
            ApplicationEvent(
                application_id=app.id,
                kind="outcome",
                actor=Actor.user,
                reason=f"outcome: {app.outcome.value} → {body.outcome.value}",
            )
        )
        app.outcome = body.outcome
    if "notes" in body.model_fields_set:
        app.notes = body.notes
    db.commit()
    return _out(db, app, detail=True)
