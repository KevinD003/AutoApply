"""Application packages: build, version, approve, invalidate.

A package is a deterministic snapshot of what would be sent: destination, form version,
documents, every answer with its source and fact references, consent choices, unresolved
questions and validation errors. Its SHA-256 `content_hash` covers all of that.

`ensure_current` rebuilds the content from current data. If the hash differs from the latest
version, a new immutable version is written and any approval of an older version is
invalidated with a reason. Approval is therefore always bound to exact content: changing a
referenced fact, a document, an answer, the destination or a consent produces a new hash.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.modules.applications.models import Application
from app.modules.applications.service import transition
from app.modules.applications.states import Actor, AppState
from app.modules.audit.service import record
from app.modules.documents.models import Document, DocumentKind
from app.modules.jobs.models import Job
from app.modules.preparation import drafting
from app.modules.preparation.forms import FieldType, FormSchema
from app.modules.preparation.models import (
    AnswerBankEntry,
    ApplicationInput,
    ApplicationPackage,
    JobForm,
    PackageApproval,
)
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.profiles.models import CandidateProfile, JobPreferences, WorkAuthorization

# Bumped to 2 (Phase C hardening): the manifest now binds owner, destination origin and submit
# endpoint, explicit document digests, policy versions. Every existing package hash changes,
# so existing approvals stop matching and must be re-approved. That is intended.
SCHEMA_VERSION = 2
RESOLVER_VERSION = "deterministic-1"
# Packages are only rebuilt while nothing has been sent; later states keep their history frozen.
REBUILDABLE = {
    AppState.draft,
    AppState.preparing,
    AppState.awaiting_approval,
    AppState.needs_user_action,
    AppState.queued,
    AppState.failed_retryable,
}
SECTIONS = ("destination", "documents", "answers", "consents")


class NoForm(LookupError):
    pass


class ApprovalError(ValueError):
    pass


def lock_application(db: Session, app_id: uuid.UUID) -> Application:
    """Row-lock the application. Approve, revoke, consent/answer writes, package rebuilds,
    claim and the final dispatch gate all take this lock, so they serialize per application."""
    return db.scalar(select(Application).where(Application.id == app_id).with_for_update())


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


def latest_form(db: Session, job_id: uuid.UUID) -> JobForm | None:
    return db.scalar(
        select(JobForm).where(JobForm.job_id == job_id).order_by(JobForm.version.desc()).limit(1)
    )


def load_context(db: Session, app: Application) -> Context:
    uid = app.user_id
    inputs = db.scalars(
        select(ApplicationInput).where(ApplicationInput.application_id == app.id)
    ).all()
    docs = {}
    for i in inputs:
        if i.kind == "document":
            doc = db.get(Document, uuid.UUID(i.value["document_id"]))
            if doc is not None and doc.user_id == uid:
                docs[i.field_key] = doc
    if "resume" not in docs:
        # Propose the latest version only when the user has exactly one resume.
        resumes = db.scalars(
            select(Document).where(Document.user_id == uid, Document.kind == DocumentKind.resume)
        ).all()
        lineages = {d.lineage_id for d in resumes}
        if len(lineages) == 1:
            docs["resume"] = max(resumes, key=lambda d: d.version)
    answer_inputs = {i.field_key: i for i in inputs if i.kind == "answer"}
    if any(i.provenance == "draft_accepted" for i in answer_inputs.values()):
        current = {f.id: f for f in drafting.grounding_facts(db, uid)}
        for i in answer_inputs.values():
            if i.provenance == "draft_accepted" and i.meta:
                used = [current.get(e) for e in i.meta.get("evidence", [])]
                now = drafting.grounding_hash([f for f in used if f is not None])
                # Flag only; the resolver turns a stale draft into a checkpoint.
                i.stale = None in used or now != i.meta.get("grounding_hash")
    return Context(
        profile=db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == uid)),
        work_auth={
            w.country_code: w
            for w in db.scalars(select(WorkAuthorization).where(WorkAuthorization.user_id == uid))
        },
        prefs=db.scalar(select(JobPreferences).where(JobPreferences.user_id == uid)),
        bank={
            e.question_key: e
            for e in db.scalars(select(AnswerBankEntry).where(AnswerBankEntry.user_id == uid))
        },
        inputs=answer_inputs,
        consents={i.field_key: i.value.get("choice") for i in inputs if i.kind == "consent"},
        documents=docs,
    )


def _condition_met(cond, value: dict | None) -> bool:
    if not value:
        return False
    chosen = {value.get("option")} | {o.get("option") for o in value.get("options") or []}
    return bool(chosen & set(cond.any_of))


def build_content(db: Session, app: Application) -> dict:
    job = db.get(Job, app.job_id)
    form = latest_form(db, job.id)
    if form is None:
        raise NoForm("No application form is attached to this job yet.")
    schema = FormSchema.model_validate(form.schema)
    ctx = load_context(db, app)
    answers, unresolved, errors = [], [], []
    values: dict[str, dict | None] = {}
    statuses: dict[str, str] = {}
    for f in schema.fields:
        r = resolve_field(f, ctx)
        trigger = statuses.get(f.condition.key) if f.condition else None
        if f.condition and f.condition.key not in statuses:
            # Depends on a question that is missing, later in the form, or circular: when it
            # is asked cannot be known, so it is never filled; if required, apply manually.
            r.value = r.display = None
            r.user_input_allowed = r.draftable = r.bankable = False
            r.status = "needs_user" if f.required else "blank_optional"
            r.explanation = (
                "NoEfforts cannot tell when this question is asked (it depends on a question "
                "that is missing, later in the form, or circular). "
                + (
                    "It is required, so apply on the employer's site."
                    if f.required
                    else "Left blank."
                )
            )
        elif f.condition and trigger in ("needs_user", "needs_consent"):
            # The trigger is unanswered, so whether this question is shown is unknown: it keeps
            # its own resolution and is never "not asked".
            r.explanation = (
                f"{r.explanation} Whether this question is asked depends on an unanswered "
                "question above."
            ).strip()
        elif f.condition and not _condition_met(f.condition, values.get(f.condition.key)):
            # Not shown for the answers given, so not asked: nothing is entered or sent.
            r.status, r.value, r.display = "blank_optional", None, None
            r.explanation = "Not asked: this question only appears for a different answer above."
        values[f.key] = r.value
        statuses[f.key] = r.status
        answers.append(
            {
                "key": f.key,
                "label": f.label,
                "help_text": f.help_text,
                "type": f.type.value,
                "required": f.required,
                "step": f.step,
                "max_length": f.max_length,
                "options": [o.model_dump() for o in f.options],
                "status": r.status,
                "source": r.source,
                "value": r.value,
                "display": r.display,
                "explanation": r.explanation,
                "fact_refs": r.fact_refs,
                "intent": r.intent,
                "sensitive": r.sensitive,
                "acknowledgment": r.acknowledgment,
                "protected": r.protected,
                "bankable": r.bankable,
                "user_input_allowed": r.user_input_allowed,
                "draftable": r.draftable,
                # Only for forms that use them, so other packages keep their exact content.
                **({"condition": f.condition.model_dump()} if f.condition else {}),
                **(
                    {"unsupported_reason": f.unsupported_reason}
                    if f.type == FieldType.unsupported
                    else {}
                ),
            }
        )
        if r.status in ("needs_user", "needs_consent"):
            unresolved.append(f.key)
            if f.required:
                errors.append({"key": f.key, "message": f"Required: {f.label}"})
    docs = []
    for a in answers:
        if a["source"] == "document":
            doc = db.get(Document, uuid.UUID(a["value"]["document_id"]))
            docs.append(
                {
                    "field": a["key"],
                    "document_id": str(doc.id),
                    "lineage_id": str(doc.lineage_id),
                    "version": doc.version,
                    "sha256": doc.sha256,
                    "size_bytes": doc.size_bytes,
                    "content_type": doc.content_type,
                    "display": a["display"],
                }
            )
    job_url = job.url or job.canonical_url  # as given; canonical form is for dedupe only
    return {
        "schema": SCHEMA_VERSION,
        "owner": {"user_id": str(app.user_id), "application_id": str(app.id)},
        "policy": {"resolver": RESOLVER_VERSION, "package_schema": SCHEMA_VERSION},
        "destination": {
            "origin": _origin(job_url),
            "submit_url": urljoin(job_url, schema.action) if job_url and schema.action else None,
            "submit_method": schema.method,
            "job_id": str(job.id),
            "employer": job.employer,
            "title": job.title,
            "url": job_url,
            "ats_provider": job.ats_provider,
            "form_id": str(form.id),
            "form_version": form.version,
            "form_fingerprint": form.fingerprint,
            "form_source": form.source,
            "form_title": schema.title,
        },
        "documents": docs,
        "answers": answers,
        "consents": {k: v for k, v in sorted(ctx.consents.items())},
        "unresolved": unresolved,
        "validation_errors": errors,
    }


def content_hash(content: dict) -> str:
    material = content_material(content)
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def _material(refs: list) -> list:
    return [{k: v for k, v in r.items() if k != "version"} for r in refs]


def content_material(content: dict) -> dict:
    """Content minus record version counters: what an approval actually depends on."""
    out = dict(content)
    out["answers"] = [a | {"fact_refs": _material(a["fact_refs"])} for a in content["answers"]]
    return out


def _summarize(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["first version"]
    out = []
    for s in SECTIONS:
        if s == "answers":
            before = {
                a["key"]: (a["value"], a["source"], _material(a["fact_refs"])) for a in old[s]
            }
            after = {a["key"]: (a["value"], a["source"], _material(a["fact_refs"])) for a in new[s]}
            changed = sorted(
                k for k in before.keys() | after.keys() if before.get(k) != after.get(k)
            )
            if changed:
                out.append("answers changed: " + ", ".join(changed[:10]))
        elif old.get(s) != new.get(s):
            out.append(f"{s} changed")
    return out or ["metadata changed"]


def latest_package(db: Session, app_id: uuid.UUID) -> ApplicationPackage | None:
    return db.scalar(
        select(ApplicationPackage)
        .where(ApplicationPackage.application_id == app_id)
        .order_by(ApplicationPackage.version.desc())
        .limit(1)
    )


def active_approval(db: Session, pkg: ApplicationPackage | None) -> PackageApproval | None:
    if pkg is None:
        return None
    return db.scalar(
        select(PackageApproval).where(
            PackageApproval.package_id == pkg.id,
            PackageApproval.invalidated_at.is_(None),
            PackageApproval.content_hash == pkg.content_hash,
            or_(PackageApproval.expires_at.is_(None), PackageApproval.expires_at > utcnow()),
        )
    )


def execution_owns_state(db: Session, app: Application) -> bool:
    """True while a worker holds an attempt (claimed, sending, or waiting for a verification
    code). Only the execution service may then change the application's state: during a code
    wait the state is `needs_user_action`, which preparation would otherwise re-settle to
    `awaiting_approval` and so re-open submission after the data was already sent."""
    from app.modules.execution.models import AttemptState, ExecutionAttempt

    held = (AttemptState.claimed, AttemptState.sending, AttemptState.awaiting_code)
    return (
        db.scalar(
            select(ExecutionAttempt.id)
            .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.state.in_(held))
            .limit(1)
        )
        is not None
    )


def ensure_current(db: Session, app: Application) -> ApplicationPackage:
    """Return the current package version, writing a new one if inputs changed.

    Takes the application row lock, so concurrent rebuilds cannot both write version N+1."""
    lock_application(db, app.id)
    db.refresh(app)
    latest = latest_package(db, app.id)
    if app.state not in REBUILDABLE or execution_owns_state(db, app):
        if latest is None:
            raise NoForm("This application has no prepared package.")
        return latest
    content = build_content(db, app)
    h = content_hash(content)
    if latest is not None and latest.content_hash == h:
        _settle_state(db, app, latest)
        return latest
    pkg = ApplicationPackage(
        application_id=app.id,
        user_id=app.user_id,
        version=(latest.version + 1) if latest else 1,
        content=content,
        content_hash=h,
        change_summary=_summarize(latest.content if latest else None, content),
    )
    db.add(pkg)
    db.flush()
    reason = "; ".join(pkg.change_summary)
    for appr in db.scalars(
        select(PackageApproval).where(
            PackageApproval.application_id == app.id, PackageApproval.invalidated_at.is_(None)
        )
    ):
        appr.invalidated_at = utcnow()
        appr.invalidation_reason = f"Package changed in version {pkg.version}: {reason}"
        record(
            db,
            app.user_id,
            "package.approval_invalidated",
            "application",
            app.id,
            version=pkg.version,
        )
    _settle_state(db, app, pkg, changed=latest is not None)
    return pkg


def _settle_state(
    db: Session, app: Application, pkg: ApplicationPackage, changed: bool = False
) -> None:
    """Move the application to the state the package implies, via legal system transitions."""
    ready = not pkg.content["unresolved"] and not pkg.content["validation_errors"]
    target = AppState.awaiting_approval if ready else AppState.needs_user_action
    s = app.state
    if s == AppState.failed_retryable:
        return
    if s == AppState.queued:
        if not changed:
            return
        transition(
            db,
            app,
            AppState.awaiting_approval,
            Actor.system,
            "Package changed after approval; approval required again",
        )
        s = app.state
    if s == target and not changed:
        return
    if s == AppState.draft:
        transition(db, app, AppState.preparing, Actor.system, "Preparing application package")
    elif s in (AppState.awaiting_approval, AppState.needs_user_action) and (s != target or changed):
        transition(
            db, app, AppState.preparing, Actor.system, f"Package version {pkg.version} prepared"
        )
    if app.state == AppState.preparing:
        transition(
            db,
            app,
            target,
            Actor.system,
            "Ready for your approval"
            if ready
            else f"{len(pkg.content['unresolved'])} question(s) need your input",
        )


def approve(db: Session, app: Application, version: int, expected_hash: str) -> PackageApproval:
    pkg = ensure_current(db, app)
    if pkg.version != version or pkg.content_hash != expected_hash:
        raise ApprovalError(
            "The package changed since you reviewed it. Review the latest "
            "version and approve again."
        )
    if pkg.content["unresolved"] or pkg.content["validation_errors"]:
        raise ApprovalError("Resolve every required question before approving.")
    if active_approval(db, pkg) is not None:
        return active_approval(db, pkg)
    now = utcnow()
    appr = PackageApproval(
        package_id=pkg.id,
        application_id=app.id,
        user_id=app.user_id,
        content_hash=pkg.content_hash,
        approved_at=now,
        expires_at=now + timedelta(hours=get_settings().approval_ttl_hours),
    )
    db.add(appr)
    record(
        db,
        app.user_id,
        "package.approve",
        "application",
        app.id,
        version=pkg.version,
        content_hash=pkg.content_hash,
    )
    return appr


def revoke(db: Session, app: Application) -> None:
    lock_application(db, app.id)
    for appr in db.scalars(
        select(PackageApproval).where(
            PackageApproval.application_id == app.id, PackageApproval.invalidated_at.is_(None)
        )
    ):
        appr.invalidated_at = utcnow()
        appr.invalidation_reason = "Revoked by you"
    record(db, app.user_id, "package.revoke", "application", app.id)


def require_valid_approval(db: Session, app: Application) -> None:
    """Gate for queueing: the current content must carry a live approval."""
    pkg = ensure_current(db, app)
    if active_approval(db, pkg) is None:
        raise ApprovalError("Approve the current package version before queueing.")
