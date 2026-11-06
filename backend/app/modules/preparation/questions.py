"""D132: "Questions needing your answer", across your applications, on one page.

Read only. For each application that waits for you, the questions its current package leaves to
you, each with what you can do about it, and a form-change pause if the employer's form changed
under an attempt. Answers go through the application's own routes (PUT .../answers and
.../consents, question keys in bodies, A8); reading the form again through
POST /applications/{id}/form/recapture. Nothing is approved, queued or sent from here: each
application is still approved from its own page.

The count is cheap: it never rebuilds a package, so navigating never writes package versions or
invalidates an approval as a side effect."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.applications.models import Application
from app.modules.applications.service import ever_submitted
from app.modules.execution.models import PAUSE_UNRESOLVED, ApplicationPause
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation import package as pk
from app.modules.preparation.forms import FieldType
from app.modules.preparation.models import ApplicationPackage
from app.modules.preparation.review import REVIEWABLE
from app.modules.providers import wording

router = APIRouter(prefix="/questions", tags=["questions"])

OPEN = ("needs_user", "needs_consent")


def category(a: dict, control: dict) -> str:
    """What answering this question means. `answer`: you answer it here; `consent`: a choice
    only you make (include a sensitive answer or not, agree or decline a statement); `document`:
    a document to choose (a resume, a cover letter) on the application's page; `profile`: a fact
    that belongs in your profile, answered there; `technical`: a control NoEfforts cannot fill
    or a question that depends on page logic: apply on the employer's site."""
    if a["status"] == "needs_consent" or a.get("acknowledgment"):
        return "consent"
    if control.get("answer_here"):
        return "answer"
    if control.get("document_role"):
        return "document"
    if a["type"] in (FieldType.unsupported.value, FieldType.file.value) or not a.get(
        "user_input_allowed"
    ):
        return "technical" if not a.get("protected") else "profile"
    return "profile"


def _row(a: dict, control: dict) -> dict:
    return {
        "key": a["key"],
        "label": a["label"],
        "help_text": a.get("help_text"),
        "type": a["type"],
        "required": a["required"],
        "options": a.get("options") or [],
        "status": a["status"],
        "explanation": a.get("explanation"),
        "sensitive": a.get("sensitive", False),
        "acknowledgment": a.get("acknowledgment", False),
        "protected": a.get("protected", False),
        "category": category(a, control),
        "answer_here": bool(control.get("answer_here")),
        # What the answer box needs (components/AnswerInput): the saved-answer choice is offered
        # only where the bank rules allow reuse.
        "bankable": a.get("bankable", False),
        "max_length": a.get("max_length"),
        "value": a.get("value"),
    }


@router.get("")
def questions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Your applications that wait for an answer or a decision, each with its open questions and
    any form-change pause. Each package is brought up to date first, as its own page does."""
    from app.modules.preparation.router import _RECAPTURE, _pause_out

    rows = db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id, Application.state.in_(REVIEWABLE))
        .order_by(Application.created_at)
    ).all()
    items = []
    for app, job in rows:
        pause = pk.unresolved_pause(db, app.id)
        if ever_submitted(db, app) and pause is None:
            continue  # a resubmission is decided on its own page
        try:
            pkg = pk.ensure_current(db, app)
        except pk.NoForm:
            db.rollback()
            continue
        db.commit()
        pause = pk.unresolved_pause(db, app.id)  # as it stands after any rebuild
        controls = pk.review_controls(db, app.id, pkg.content)
        open_rows = [
            _row(a, controls.get(a["key"], {}))
            for a in pkg.content["answers"]
            if a["status"] in OPEN
        ]
        if not open_rows and pause is None:
            continue
        form = pk.latest_form(db, app.job_id)
        items.append(
            {
                "application_id": str(app.id),
                "title": job.title,
                "employer": job.employer,
                "state": app.state.value,
                "form_source": wording.form_source_label(pkg.content["destination"]["form_source"]),
                "package": {"version": pkg.version, "content_hash": pkg.content_hash},
                # D132: while it is unresolved nothing is approved for this application.
                "pause": _pause_out(pause),
                "recapture_available": form is not None and form.source in _RECAPTURE,
                "questions": open_rows,
            }
        )
    return {"items": items}


@router.get("/count")
def count(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """How many applications wait for you (an open question in the stored package, or a
    form-change pause). Reads what is stored; never rebuilds or writes anything."""
    paused = set(
        db.scalars(
            select(ApplicationPause.application_id).where(
                ApplicationPause.user_id == user.id,
                ApplicationPause.status.in_(PAUSE_UNRESOLVED),
            )
        )
    )
    latest = (
        select(ApplicationPackage.application_id, func.max(ApplicationPackage.version))
        .join(Application, Application.id == ApplicationPackage.application_id)
        .where(Application.user_id == user.id, Application.state.in_(REVIEWABLE))
        .group_by(ApplicationPackage.application_id)
    )
    waiting = set(paused)
    for app_id, version in db.execute(latest):
        content = db.scalar(
            select(ApplicationPackage.content).where(
                ApplicationPackage.application_id == app_id,
                ApplicationPackage.version == version,
            )
        )
        if any(a["status"] in OPEN for a in (content or {}).get("answers", [])):
            waiting.add(app_id)
    return {"applications": len(waiting), "paused": len(paused)}
