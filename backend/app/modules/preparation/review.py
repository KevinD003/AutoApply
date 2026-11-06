"""D105: review several packages on one page and approve the ones you choose, each on its own.

The owner's rule (2026-10-31): "A future batch-review interface may approve individually
identified, immutable packages, but it must not mean unrestricted approval for future
applications." So a batch is only a list of single approvals, each exactly as the review page of
that application would give it (`package.approve`, unchanged):

* **Individually identified.** Each item names its application, the package version and that
  version's content hash, as the list showed them, and its own scope. Nothing is approved by
  default, by filter or by wildcard, and there is no "approve all", only the items sent.
* **Immutable.** An item whose package has changed since it was shown (a new version, or the
  inputs changed and rebuilt it) is refused (`package_changed`). Nothing else is approved in its
  place.
* **Bound and limited as one approval is.** Each approval is bound to the user, application,
  destination, adapter and version, package hash and scope. It expires
  (`approval_ttl_hours`) and is revoked or used as any other. An approval to submit still needs
  the employer's path rehearsed first (E6).
* **Approval only.** Approving queues, sends and submits nothing. Each application is still
  submitted, or rehearsed, from its own page.
* **One at a time.** Each item is checked and approved in its own transaction. One that is
  refused leaves the others as they are, and the answer says which was which.
* **Yours only.** Another account's application is "not found", item by item, as on its own
  page.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.modules.applications.models import Application
from app.modules.applications.service import ever_submitted
from app.modules.applications.states import AppState
from app.modules.audit.service import record
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApprovalScope

router = APIRouter(prefix="/review", tags=["review"])

MAX_ITEMS = 25  # one batch: as many as one person can review on one page
# Where an application may still be approved (the states its own page offers approval in).
REVIEWABLE = frozenset({AppState.draft, AppState.preparing, AppState.awaiting_approval,
                        AppState.needs_user_action})  # fmt: skip


class Item(BaseModel):
    application_id: uuid.UUID
    version: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    scope: ApprovalScope  # required: never a default, never "submit" by omission


class BatchIn(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=MAX_ITEMS)

    @field_validator("items")
    @classmethod
    def one_per_application(cls, items: list[Item]) -> list[Item]:
        ids = [i.application_id for i in items]
        if len(set(ids)) != len(ids):
            raise ValueError("each application may appear once in a batch")
        return items


def _summary(db: Session, app: Application, job: Job, pkg) -> dict:
    """What the list shows of one package: enough to identify it and see whether it can be
    approved; the full package is on the application's own page."""
    from app.modules.execution import rehearsal
    from app.modules.jobs import signals
    from app.modules.providers import wording

    c = pkg.content
    appr = pk.active_approval(db, pkg)
    blocked = []
    if c["unresolved"]:
        blocked.append(f"{len(c['unresolved'])} question(s) need your answer")
    if c["validation_errors"]:
        blocked.append(f"{len(c['validation_errors'])} answer(s) do not fit their question")
    code = signals.approval_refusal(db, job)
    if code is not None:
        blocked.append(signals.refusal(code))
    pause = pk.unresolved_pause(db, app.id)
    if pause is not None and pause.package_hash == pkg.content_hash:
        # D132: this exact package stopped on a changed form; never approved again.
        blocked.append("The employer's form changed: read it again under Questions")
    return {
        "application_id": str(app.id),
        "state": app.state.value,
        "title": job.title,
        "employer": job.employer,
        "destination": wording.destination_label(c["destination"]["origin"]),
        "form_source": wording.form_source_label(c["destination"]["form_source"]),
        "version": pkg.version,
        "content_hash": pkg.content_hash,
        "created_at": pkg.created_at,
        "answers": sum(1 for a in c["answers"] if a["value"] is not None),
        "documents": len(c.get("documents") or []),
        "blocked": blocked,
        "approval": (
            {"scope": appr.scope, "expires_at": appr.expires_at, "version": pkg.version}
            if appr is not None
            else None
        ),
        "rehearsal_prerequisite": rehearsal.view(db, app, pkg, appr),
    }


@router.get("/packages")
def review_list(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Your applications that could be approved now, each with its current package (rebuilt
    first if its inputs changed, as its own page does). Nothing is approved here."""
    rows = db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id, Application.state.in_(REVIEWABLE))
        .order_by(Application.created_at)
    ).all()
    items = []
    for app, job in rows:
        if ever_submitted(db, app):
            continue
        try:
            pkg = pk.ensure_current(db, app)
        except pk.NoForm:
            db.rollback()
            continue  # no form captured yet: nothing to review
        db.commit()
        items.append(_summary(db, app, job, pkg))
    return {
        "items": items,
        "max_items": MAX_ITEMS,
        "approval_ttl_hours": get_settings().approval_ttl_hours,
    }


@router.post("/approve")
def review_approve(
    body: BatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Approve each item on its own, exactly as its own page would; never queue or send."""
    batch = uuid.uuid4().hex[:12]
    results = []
    for item in body.items:
        out = {"application_id": str(item.application_id), "version": item.version}
        app = db.get(Application, item.application_id)
        if app is None or app.user_id != user.id:
            results.append({**out, "status": "not_found"})
            continue
        if app.state not in REVIEWABLE or ever_submitted(db, app):
            results.append({**out, "status": "refused", "reason": "This application can no "
                            "longer be approved from here; open it to see why."})  # fmt: skip
            continue
        try:
            appr = pk.approve(db, app, item.version, item.content_hash, item.scope)
            record(db, user.id, "package.approve_reviewed", "application", app.id,
                   batch=batch, version=item.version, scope=item.scope.value)  # fmt: skip
            db.commit()
            results.append({**out, "status": "approved", "scope": appr.scope,
                            "expires_at": appr.expires_at})  # fmt: skip
        except pk.ApprovalError as e:  # RehearsalRequired among them (E6)
            db.commit()  # keep a package version rebuilt while checking, as its own page does
            results.append({**out, "status": "refused", "reason": str(e),
                            "reason_code": getattr(e, "code", None)})  # fmt: skip
        except pk.NoForm as e:
            db.rollback()
            results.append({**out, "status": "refused", "reason": str(e)})
        except HTTPException:
            db.rollback()
            raise
    return {"results": results}
