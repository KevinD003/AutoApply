import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import Text, case, cast, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, new_id, utcnow
from app.core.errors import bad_request, conflict, not_found
from app.modules.applications.models import Application
from app.modules.audit.service import record, ref
from app.modules.documents.models import Document, DocumentKind
from app.modules.execution import rehearsal
from app.modules.execution.models import AttemptState, ExecutionAttempt
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs import signals
from app.modules.jobs.models import Job
from app.modules.preparation import bankscope, binding, drafting
from app.modules.preparation import greenhouse as gh
from app.modules.preparation import package as pk
from app.modules.preparation.classify import classify
from app.modules.preparation.fixtures_registry import FIXTURES, fixture_html
from app.modules.preparation.forms import (
    EXTRACTION_VERSION,
    KEY_PATTERN,
    ExtractionError,
    FieldType,
    FormField,
    FormSchema,
    extract_form_schema,
    form_fingerprint,
)
from app.modules.preparation.models import (
    AnswerBankEntry,
    AnswerDraft,
    ApplicationInput,
    ApplicationPackage,
    ApprovalScope,
    JobForm,
    PackageApproval,
)
from app.modules.preparation.resolver import (
    answer_shape,
    normalize_input,
    option_labels,
    question_key,
    saved_answer_scope,
)
from app.modules.profiles.models import (
    Approval,
    Provenance,
)
from app.modules.providers import wording

router = APIRouter(tags=["preparation"])


def _owned_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise not_found("Job")
    return job


def _owned_app(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise not_found("Application")
    return app


# ---------------------------------------------------------------------------------------------
# Fixture forms (local development and tests only)


@router.get("/fixtures/forms")
def list_fixtures() -> dict:
    return {"fixtures": FIXTURES, "note": "Local test fixtures with fictional employers."}


@router.get("/fixtures/forms/{name}")
def get_fixture(name: str):
    if get_settings().env == "production":
        raise not_found("Fixture")
    try:
        return Response(
            fixture_html(name),
            media_type="text/html; charset=utf-8",
            headers={"X-Robots-Tag": "noindex"},
        )
    except KeyError:
        raise not_found("Fixture") from None


# ---------------------------------------------------------------------------------------------
# Job forms


class FormIn(BaseModel):
    fixture: str | None = None
    html: str | None = Field(default=None, max_length=2_000_000)
    form: FormSchema | None = None

    @model_validator(mode="after")
    def _one(self):
        if sum(x is not None for x in (self.fixture, self.html, self.form)) != 1:
            raise ValueError("Provide exactly one of: fixture, html, form")
        return self


@router.post("/jobs/{job_id}/form", status_code=status.HTTP_201_CREATED)
def attach_form(
    job_id: uuid.UUID,
    body: FormIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Capture a form schema for a job. Pasted HTML is parsed as data, never executed."""
    job = _owned_job(db, user, job_id)
    try:
        if body.fixture is not None:
            if get_settings().env == "production":
                raise bad_request("Fixtures are disabled in production")
            schema, source, ref = (
                extract_form_schema(fixture_html(body.fixture)),
                "fixture",
                body.fixture,
            )
        elif body.html is not None:
            schema, source, ref = extract_form_schema(body.html), "html", None
        else:
            schema, source, ref = body.form, "manual", None
    except KeyError:
        raise bad_request("Unknown fixture") from None
    except (ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the form: {e}") from None
    return _store_form(db, user, job, schema, source, ref, EXTRACTION_VERSION)


def _store_form(db, user, job, schema: FormSchema, source, ref, extraction) -> dict:
    latest = pk.latest_form(db, job.id)
    fp = form_fingerprint(schema)
    if latest is not None and latest.fingerprint == fp:
        return _form_out(latest)
    form = JobForm(
        user_id=user.id,
        job_id=job.id,
        version=(latest.version + 1) if latest else 1,
        source=source,
        source_ref=ref,
        extraction_version=extraction,
        fingerprint=fp,
        schema=schema.model_dump(mode="json"),
    )
    db.add(form)
    db.flush()
    record(db, user.id, "job.form_captured", "job", job.id, version=form.version, source=source)
    db.commit()
    return _form_out(form)


def _fetch_fixture(url: str) -> bytes:
    """Loopback fixture only (callers check is_fixture_origin); no proxies, no redirects."""
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    with opener.open(url, timeout=10) as r:
        return r.read(2_000_001)[:2_000_000]


@router.post("/jobs/{job_id}/form/greenhouse", status_code=status.HTTP_201_CREATED)
def capture_greenhouse_form(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Read a Greenhouse-style job post (JSON) and its hosted form (page), cross-check them and
    store the schema. Only local fixtures are read: reading a real job post is not enabled, and
    reading one would not be permission to submit an application."""
    import json
    from urllib.parse import urlsplit

    from app.core.urlsafety import is_fixture_origin

    job = _owned_job(db, user, job_id)
    url = job.url or job.canonical_url or ""
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    fixture = is_fixture_origin(origin)
    posting = gh.parse_posting(url, fixture_origin=fixture)
    if posting is None:
        raise bad_request("This job's address is not a Greenhouse job post")
    if not posting.fixture:
        raise conflict(
            "Reading real Greenhouse job posts is not enabled in this version; it needs separate "
            "approval. Apply on the employer's site and record it in the tracker."
        )
    from app.modules.preparation import greenhouse_dom

    source, extraction = "greenhouse_api", gh.EXTRACTION_VERSION
    try:
        api = json.loads(_fetch_fixture(gh.api_url(posting, origin)))
        page = _fetch_fixture(url).decode("utf-8", "replace")
        try:
            schema = gh.build_schema(api, page)
        except ExtractionError:
            # No named controls (the structure seen on a real hosted page): map by id, label
            # and role instead, refusing anything absent or ambiguous.
            schema, _ = greenhouse_dom.build_schema(api, page)
            source, extraction = "greenhouse_api_dom", greenhouse_dom.EXTRACTION_VERSION
    except gh.SchemaMismatch as e:  # generic wording plus the fixed code; no form structure
        raise conflict(
            "Could not capture the form: its structure is unsupported or incomplete. Nothing was "
            f"sent; apply on the employer's site. (reason: {e.code})"
        ) from None
    except (OSError, ValueError, ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the job post ({type(e).__name__})") from None
    return _store_form(db, user, job, schema, source, posting.ref, extraction)


def _form_out(form) -> dict:
    return {
        "id": str(form.id),
        "version": form.version,
        "source": form.source,
        "source_label": wording.form_source_label(form.source),
        "source_ref": form.source_ref,
        "fingerprint": form.fingerprint,
        "extraction_version": form.extraction_version,
        "captured_at": form.captured_at,
        "schema": form.schema,
    }


@router.get("/jobs/{job_id}/form")
def get_form(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    job = _owned_job(db, user, job_id)
    form = pk.latest_form(db, job.id)
    if form is None:
        raise not_found("Form")
    return _form_out(form)


# ---------------------------------------------------------------------------------------------
# Package review


def _approval_view(db: Session, app: Application, pkg, appr, last) -> dict:
    """The current approval, or what became of the last one. An approval a rehearsal used up
    is shown as such (from its rehearsed attempt), not as an invalidation."""
    if appr is not None:
        return {
            "status": "approved",
            "approved_at": appr.approved_at,
            "version": pkg.version,
            "scope": appr.scope,
        }
    if last is None or last.invalidated_at is None:
        return {"status": "not_approved"}
    rehearsal = db.scalar(
        select(ExecutionAttempt).where(
            ExecutionAttempt.approval_id == last.id,
            ExecutionAttempt.user_id == app.user_id,
            ExecutionAttempt.state == AttemptState.rehearsed,
        )
    )
    if rehearsal is not None:
        return {
            "status": "used_by_rehearsal",
            "approved_at": last.approved_at,
            "rehearsed_at": rehearsal.finished_at,
            "version": db.get(ApplicationPackage, last.package_id).version,
        }
    return {
        "status": "invalidated",
        "approved_at": last.approved_at,
        "invalidated_at": last.invalidated_at,
        "reason": last.invalidation_reason,
    }


def _package_view(db: Session, app: Application, pkg: ApplicationPackage) -> dict:
    appr = pk.active_approval(db, pkg)
    last = db.scalar(
        select(PackageApproval)
        .where(PackageApproval.application_id == app.id)
        .order_by(PackageApproval.approved_at.desc())
        .limit(1)
    )
    history = db.scalars(
        select(ApplicationPackage)
        .where(ApplicationPackage.application_id == app.id)
        .order_by(ApplicationPackage.version.desc())
        .limit(20)
    ).all()
    approved_ids = {
        a.package_id
        for a in db.scalars(select(PackageApproval).where(PackageApproval.application_id == app.id))
    }
    drafts = db.scalars(
        select(AnswerDraft).where(
            AnswerDraft.application_id == app.id, AnswerDraft.status == "proposed"
        )
    ).all()
    return {
        "application_id": str(app.id),
        "state": app.state.value,
        "package": {
            "id": str(pkg.id),
            "version": pkg.version,
            "content_hash": pkg.content_hash,
            "created_at": pkg.created_at,
            "change_summary": pkg.change_summary,
            "content": pkg.content,
        },
        # Outside the content, so wording never changes the package hash.
        "labels": {
            "form_source": wording.form_source_label(pkg.content["destination"]["form_source"]),
            "destination": wording.destination_label(pkg.content["destination"]["origin"]),
        },
        # C12 (D64): what the review page may offer per question (outside the content).
        "review": pk.review_controls(db, app.id, pkg.content),
        "approval": _approval_view(db, app, pkg, appr, last),
        # E6: whether a submission here needs a rehearsal first, and why (execution/rehearsal.py).
        "rehearsal_prerequisite": rehearsal.view(db, app, pkg, appr),
        # S3 (D59): what about the job itself holds an approval back (outside the content).
        "job_signals": signals.view(db, db.get(Job, app.job_id)),
        "history": [
            {
                "version": h.version,
                "created_at": h.created_at,
                "change_summary": h.change_summary,
                "was_approved": h.id in approved_ids,
            }
            for h in history
        ],
        "drafting_available": drafting.get_provider() is not None,
        "drafts": [
            {
                "id": str(d.id),
                "field_key": d.field_key,
                "text": d.text,
                "evidence": d.evidence,
                "provider": d.provider,
                "created_at": d.created_at,
            }
            for d in drafts
        ],
    }


def _current(db: Session, app: Application) -> ApplicationPackage:
    try:
        pkg = pk.ensure_current(db, app)
    except pk.NoForm as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    db.commit()
    return pkg


@router.get("/applications/{app_id}/package")
def get_package(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    return _package_view(db, app, _current(db, app))


def _field(db: Session, app: Application, key: str) -> tuple[dict, FormField]:
    pkg = _current(db, app)
    entry = next((a for a in pkg.content["answers"] if a["key"] == key), None)
    if entry is None:
        raise not_found("Question")
    form = pk.latest_form(db, app.job_id)
    f = next(FormField.model_validate(x) for x in form.schema["fields"] if x["key"] == key)
    return entry, f


def _upsert_input(
    db: Session,
    app: Application,
    kind: str,
    key: str,
    value: dict,
    provenance: str = "user_entered",
    meta: dict | None = None,
) -> None:
    pk.lock_application(db, app.id)  # serialize with approve/revoke/claim
    row = db.scalar(
        select(ApplicationInput).where(
            ApplicationInput.application_id == app.id,
            ApplicationInput.kind == kind,
            ApplicationInput.field_key == key,
        )
    )
    if row is None:
        row = ApplicationInput(
            application_id=app.id,
            user_id=app.user_id,
            kind=kind,
            field_key=key,
            value=value,
            provenance=provenance,
            meta=meta,
        )
        db.add(row)
    else:
        row.value, row.provenance, row.meta = value, provenance, meta


# A posting's question key travels in the request body, never in the path: a proxy in front of
# the app could log a path (docs/audit-events.md, "Logs"; tests/test_api_paths.py).
QuestionKey = Annotated[str, Field(min_length=1, max_length=200, pattern=KEY_PATTERN)]


class QuestionIn(BaseModel):
    key: QuestionKey


class AnswerIn(QuestionIn):
    value: dict
    save_to_bank: bool = False


@router.put("/applications/{app_id}/answers")
def put_answer(
    app_id: uuid.UUID,
    body: AnswerIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    key = body.key
    entry, f = _field(db, app, key)
    if entry["acknowledgment"]:
        raise bad_request("Legal statements and consents are answered with a consent choice.")
    if not entry["user_input_allowed"] or entry["source"] in (
        "profile_fact",
        "deterministic_mapping",
    ):
        raise bad_request(
            "This answer comes from your verified profile or your preferences. Update them "
            "instead, so every application stays consistent."
        )
    try:
        value = normalize_input(f, body.value)
    except ValueError as e:
        raise bad_request(str(e)) from None
    if body.save_to_bank:
        # Checked before anything is written: a refused request changes nothing (D51).
        refusal = _reuse_refusal(db, app, entry, f)
        if refusal:
            raise bad_request(refusal)
    _upsert_input(db, app, "answer", key, value, meta=binding.input_meta(f))  # C7: bound
    if body.save_to_bank:
        db.flush()  # the input row before the saved answer (lock order, D46 item 6)
        _save_to_bank(db, user, app, f, value, sensitive=entry["sensitive"])
    record(db, user.id, "application.answer", "application", app.id, field_ref=ref(key, user.id))
    db.flush()
    return _package_view(db, app, _current(db, app))


# Why an answer is not saved for reuse (D51), by bankscope category. The 400 aborts the request,
# so the typed answer is not saved either.
REUSE_REFUSED = {
    "fact": "This is about work authorization, sponsorship, citizenship, immigration status or "
    "residence, so its answer is never saved for reuse.",
    "employer": "This question is about the employer or the job (how you heard about it, a "
    "referral, working or applying there before, its requirements or terms), so its answer is "
    "never saved for reuse.",
    "time": "This answer depends on when you apply (a start date, availability, a schedule, a "
    "length of time, or something current or valid now), so it is never saved for reuse.",
    "pay": "Pay is never saved for reuse: keep your salary expectation in Preferences, or answer "
    "it for each application.",
    "place": "Relocation, commuting, travel, work location and address are never saved for "
    "reuse: keep relocation in Preferences, or answer it for each application.",
    "section": "This question is in a section about the job, pay, availability, your work history "
    "or other people, so its answer is never saved for reuse.",
    "repeated": "The same question appears more than once on this form, so its answer is never "
    "saved for reuse.",
    "followup": "This follow-up depends on a question whose answer is never saved, so it is not "
    "saved either.",
}
NOT_SAVED = (
    " Nothing was saved: save your answer again without \u201cReuse for this exact question\u201d."
)


def _reuse_refusal(db: Session, app: Application, entry: dict, f: FormField) -> str | None:
    """The 400 detail when this answer may not be saved for reuse, else None (D51). The package
    row decides, and the wording is checked again: a package built before C6 and not rebuilt
    since (its application is past preparation) cannot save what C6 never reuses."""
    pkg = pk.latest_package(db, app.id)
    fields = [FormField.model_validate(x) for x in pk.latest_form(db, app.job_id).schema["fields"]]
    keys = [question_key(x) for x in fields if x.type != FieldType.file]
    parent = next(
        (a for a in pkg.content["answers"] if f.condition and a["key"] == f.condition.key), None
    )
    parent_bankable = None
    if parent is not None:
        # A stored row may predate C6 too: its own wording is checked again (review, D51).
        pf = next((x for x in fields if x.key == parent["key"]), None)
        parent_bankable = parent["bankable"] and (
            pf is None
            or bankscope.refusal_code(pf, classify(pf), repeated=keys.count(question_key(pf)) > 1)
            is None
        )
    code = bankscope.refusal_code(
        f,
        classify(f),
        parent=SimpleNamespace(bankable=parent_bankable) if parent is not None else None,
        repeated=keys.count(question_key(f)) > 1,
    )
    if entry["bankable"] and code is None:
        return None
    if code in ("repeated", "followup"):  # true whatever the topic (a repeated Gender question)
        return REUSE_REFUSED[code] + NOT_SAVED
    if entry["sensitive"] or entry["protected"]:
        return (
            "Sensitive and protected answers are never saved for reuse; answer them for each "
            "application."
        )
    if code in REUSE_REFUSED:
        return REUSE_REFUSED[code] + NOT_SAVED
    # S4 (D54): also someone else's details, and a fact that does not fit this field.
    return (
        "This answer is for this application only (it depends on the job, is about someone other "
        "than you, or replaces a profile fact this field cannot take), so it is never saved for "
        "reuse." + NOT_SAVED
    )


def _save_to_bank(db, user, app, f, value, sensitive: bool) -> None:
    """Insert or update this user's saved answer for this exact question in one statement
    (D51): two first saves from two applications, or a save racing the deletion of the entry,
    never fail. PostgreSQL inserts, or waits for the row's other writer and then updates the
    row, or inserts again if that writer deleted it. The version counts changes of the value or
    the options only. Lock order (D46): the application (taken by _upsert_input), then this
    row."""
    shape = answer_shape(f)
    stored = (
        {"labels": [value["label"]]}
        if shape == "choice"
        else {"labels": [o["label"] for o in value["options"]]}
        if shape == "multi"
        else value
    )
    t = AnswerBankEntry.__table__
    ins = pg_insert(AnswerBankEntry).values(
        id=new_id(),
        user_id=user.id,
        question_key=question_key(f),
        # PostgreSQL text cannot hold NUL; page text can (the key keeps it, so nothing re-keys).
        question_text=f.label.replace("\x00", ""),
        help_text=(f.help_text or "").replace("\x00", "").strip(),  # "": none; NULL: before C6
        answer_shape=shape,
        value=stored,
        options_snapshot=option_labels(f),
        sensitive=sensitive,
        source_application_id=app.id,
        provenance=Provenance.user_entered,
        approval_status=Approval.approved,
        version=1,
        updated_at=utcnow(),  # onupdate= is not applied to ON CONFLICT DO UPDATE
    )
    ex = ins.excluded
    # json has no "=" operator, and jsonb refuses a \u0000 that json accepts: compare the text,
    # which the same serializer wrote both times (a difference only costs a version number).
    changed = or_(
        cast(t.c.value, Text) != cast(ex["value"], Text),
        cast(t.c.options_snapshot, Text) != cast(ex["options_snapshot"], Text),
    )
    copied = (
        "question_text",
        "help_text",
        "answer_shape",
        "value",
        "options_snapshot",
        "sensitive",
        "source_application_id",
        "provenance",
        "approval_status",
        "updated_at",
    )
    stmt = (
        ins.on_conflict_do_update(
            index_elements=[t.c.user_id, t.c.question_key],  # answer_bank_user_id_question_key_key
            set_={"version": case((changed, t.c.version + 1), else_=t.c.version)}
            | {c: ex[c] for c in copied},
        )
        .returning(AnswerBankEntry)
        # This session loaded the row unlocked while rebuilding the package: refresh it.
        .execution_options(populate_existing=True)
    )
    db.scalars(stmt).one()


@router.post("/applications/{app_id}/answers/clear")
def clear_answer(
    app_id: uuid.UUID,
    body: QuestionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    # The application first, then its input (the order _upsert_input and rebuilds use), so a
    # clear and a save of the same question serialize instead of deadlocking.
    pk.lock_application(db, app.id)
    row = db.scalar(
        select(ApplicationInput).where(
            ApplicationInput.application_id == app.id,
            ApplicationInput.kind == "answer",
            ApplicationInput.field_key == body.key,
        )
    )
    if row is not None:
        db.delete(row)
        record(db, user.id, "application.answer_cleared", "application", app.id,
               field_ref=ref(body.key, user.id))  # fmt: skip
        db.flush()
    return _package_view(db, app, _current(db, app))


class ConsentIn(QuestionIn):
    choice: Literal["agree", "decline", "disclose", "withhold"] | None


@router.put("/applications/{app_id}/consents")
def put_consent(
    app_id: uuid.UUID,
    body: ConsentIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    key = body.key
    entry, f = _field(db, app, key)
    allowed = (
        {"agree", "decline"}
        if entry["acknowledgment"]
        else {"disclose", "withhold"}
        if entry["sensitive"]
        else set()
    )
    if body.choice is not None and body.choice not in allowed:
        raise bad_request(
            f"Choose one of {sorted(allowed)} for this question."
            if allowed
            else "This question does not take a consent choice."
        )
    pk.lock_application(db, app.id)  # the application, then its input (as in clear_answer)
    row = db.scalar(
        select(ApplicationInput).where(
            ApplicationInput.application_id == app.id,
            ApplicationInput.kind == "consent",
            ApplicationInput.field_key == key,
        )
    )
    if body.choice is None:
        if row is not None:
            db.delete(row)
    else:
        # C7 (D60): bound to the question as shown, and a "disclose" to the exact answer shown.
        meta = binding.input_meta(f)
        if body.choice == "disclose":
            meta["value_digest"] = binding.value_digest(user.id, key, entry["value"])
        _upsert_input(db, app, "consent", key, {"choice": body.choice}, meta=meta)
    record(db, user.id, "application.consent", "application", app.id, field_ref=ref(key, user.id),
           choice=body.choice)  # fmt: skip
    db.flush()
    return _package_view(db, app, _current(db, app))


class DocumentsIn(BaseModel):
    resume_document_id: uuid.UUID | None = None
    cover_letter_document_id: uuid.UUID | None = None
    # C12 (D64): send no document of these roles (an optional cover letter left out).
    clear: list[Literal["resume", "cover_letter"]] = []


@router.put("/applications/{app_id}/documents")
def put_documents(
    app_id: uuid.UUID,
    body: DocumentsIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    for role, doc_id, kind in (
        ("resume", body.resume_document_id, DocumentKind.resume),
        ("cover_letter", body.cover_letter_document_id, DocumentKind.cover_letter),
    ):
        if doc_id is None:
            continue
        doc = db.get(Document, doc_id)
        if doc is None or doc.user_id != user.id:
            raise not_found("Document")
        if doc.kind != kind:
            raise bad_request(f"That document is not a {role.replace('_', ' ')}.")
        _upsert_input(db, app, "document", role, {"document_id": str(doc.id)})
        record(db, user.id, "application.document", "application", app.id, role=role,
               change="chosen")  # fmt: skip
    if body.clear:
        pk.lock_application(db, app.id)  # the application, then its inputs (as in clear_answer)
        for role in sorted(set(body.clear)):
            row = db.scalar(
                select(ApplicationInput).where(
                    ApplicationInput.application_id == app.id,
                    ApplicationInput.kind == "document",
                    ApplicationInput.field_key == role,
                )
            )
            if row is not None:
                db.delete(row)
                record(db, user.id, "application.document", "application", app.id, role=role,
                       change="cleared")  # fmt: skip
    db.flush()
    return _package_view(db, app, _current(db, app))


class ApproveIn(BaseModel):
    version: int
    content_hash: str = Field(min_length=64, max_length=64)
    # submit: fill and submit once. disclose_only: a rehearsal that never submits.
    scope: ApprovalScope = ApprovalScope.submit


@router.post("/applications/{app_id}/package/approve")
def approve_package(
    app_id: uuid.UUID,
    body: ApproveIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        pk.approve(db, app, body.version, body.content_hash, body.scope)
    except pk.NoForm as e:
        raise conflict(str(e)) from None
    except pk.ApprovalError as e:
        db.commit()  # keep any new package version that was written while checking
        raise conflict(str(e)) from None
    db.commit()
    return _package_view(db, app, pk.latest_package(db, app.id))


@router.get("/applications/{app_id}/package/diff")
def package_diff(
    app_id: uuid.UUID,
    from_version: int | None = None,
    to_version: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """C14 (D66): what changed between two versions of your package (by default, the latest and
    the one before it). Read-only: nothing is rebuilt, approved or recorded."""
    app = _owned_app(db, user, app_id)
    pkgs = {
        p.version: p
        for p in db.scalars(
            select(ApplicationPackage).where(ApplicationPackage.application_id == app.id)
        )
    }
    to = pkgs.get(to_version if to_version is not None else max(pkgs, default=0))
    frm = pkgs.get(from_version if from_version is not None else (to.version - 1 if to else 0))
    if to is None or frm is None:
        raise not_found("Package version")
    approved = {
        a.package_id
        for a in db.scalars(select(PackageApproval).where(PackageApproval.application_id == app.id))
    }

    def side(p: ApplicationPackage) -> dict:
        return {"version": p.version, "content_hash": p.content_hash, "created_at": p.created_at,
                "was_approved": p.id in approved}  # fmt: skip

    return {"from": side(frm), "to": side(to), **pk.diff_contents(frm.content, to.content)}


@router.post("/applications/{app_id}/package/revoke")
def revoke_package(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    from app.modules.execution import service as execution

    try:
        effect = execution.stop_for_revoke(db, app)
    except pk.ApprovalError as e:
        db.rollback()
        raise conflict(str(e)) from None
    pk.revoke(db, app, effect)
    db.flush()
    # C13 (D65): what revoking did to an attempt in progress, for the page to say.
    return _package_view(db, app, _current(db, app)) | {"revoke_effect": effect}


# ---------------------------------------------------------------------------------------------
# Long-form drafting (optional)


@router.post("/applications/{app_id}/drafts")
def request_draft(
    app_id: uuid.UUID,
    body: QuestionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    key = body.key
    entry, f = _field(db, app, key)
    if not entry["draftable"]:
        raise bad_request("Only long-form questions can be drafted.")
    provider = drafting.get_provider()
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI drafting is not configured. Write this answer yourself.",
        )
    job = db.get(Job, app.job_id)
    facts = drafting.grounding_facts(db, user.id)
    if not facts:
        raise bad_request(
            "Add work history or a summary to your profile first; drafts only "
            "use facts you have entered."
        )
    req = drafting.DraftRequest(
        question=f.label,
        help_text=f.help_text,
        max_chars=f.max_length or 1500,
        employer=job.employer,
        job_title=job.title,
        job_text=(job.description or "")[:6000] or None,
        facts=facts,
    )
    h = req.input_hash()
    cached = db.scalar(
        select(AnswerDraft).where(
            AnswerDraft.application_id == app.id,
            AnswerDraft.field_key == key,
            AnswerDraft.input_hash == h,
        )
    )
    if cached is None:
        result = provider.draft(req)
        try:
            text = drafting.validate_draft(req, result)
        except drafting.InvalidDraft as e:
            record(db, user.id, "draft.rejected", "application", app.id,
                   field_ref=ref(key, user.id), reason_code=e.code)  # fmt: skip
            db.commit()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"The draft failed validation and was discarded: {e}",
            ) from None
        cached = AnswerDraft(
            application_id=app.id,
            user_id=user.id,
            field_key=key,
            input_hash=h,
            provider=result.provider,
            model=result.model,
            text=text,
            evidence=result.evidence,
            cost_usd=result.cost_usd,
        )
        db.add(cached)
        record(
            db,
            user.id,
            "draft.created",
            "application",
            app.id,
            field_ref=ref(key, user.id),
            provider=result.provider,
            cost_usd=result.cost_usd,
        )
        db.commit()
    return {
        "id": str(cached.id),
        "field_key": key,
        "text": cached.text,
        "evidence": cached.evidence,
        "provider": cached.provider,
        "status": cached.status,
    }


@router.post("/applications/{app_id}/drafts/{draft_id}/accept")
def accept_draft(
    app_id: uuid.UUID,
    draft_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    d = db.get(AnswerDraft, draft_id)
    if d is None or d.application_id != app.id:
        raise not_found("Draft")
    _, f = _field(db, app, d.field_key)
    pk.lock_application(db, app.id)
    current = {g.id: g for g in drafting.grounding_facts(db, user.id)}
    used = [current[e] for e in d.evidence if e in current]
    if len(used) != len(d.evidence):
        raise conflict("Facts this draft relied on have changed; request a new draft.")
    _upsert_input(
        db,
        app,
        "answer",
        d.field_key,
        normalize_input(f, {"text": d.text}),
        provenance="draft_accepted",
        meta=binding.input_meta(
            f,
            {
                "draft_id": str(d.id),
                "evidence": list(d.evidence),
                "grounding_hash": drafting.grounding_hash(used),
            },
        ),
    )
    d.status = "accepted"
    db.flush()
    return _package_view(db, app, _current(db, app))


# ---------------------------------------------------------------------------------------------
# Answer bank


class BankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question_text: str
    answer_shape: str
    value: dict
    options_snapshot: list
    sensitive: bool
    provenance: Provenance
    approval_status: Approval
    version: int
    updated_at: datetime
    help_text: str | None  # None: saved before NoEfforts recorded help text (C6); "": none
    not_reused: str | None = None  # why this entry no longer answers its own wording (D51)


NOT_REUSED = {
    # Shown after a "Not reused" badge (review, D51).
    "fact": "It is about work authorization, sponsorship, citizenship, immigration status or "
    "residence.",
    "employer": "It is about one employer or job.",
    "time": "Its answer depends on when you apply.",
    "pay": "Pay comes from your Preferences or is answered for each application.",
    "place": "Relocation comes from your Preferences; travel, work location and address are "
    "answered for each application.",
    "other": "NoEfforts asks this in each application.",
}


@router.get("/answer-bank", response_model=list[BankOut])
def list_bank(user: User = Depends(current_user), db: Session = Depends(get_db)):
    entries = db.scalars(
        select(AnswerBankEntry)
        .where(AnswerBankEntry.user_id == user.id)
        .order_by(AnswerBankEntry.updated_at.desc())
    ).all()
    return [
        BankOut.model_validate(e).model_copy(
            update={"not_reused": NOT_REUSED.get(saved_answer_scope(e))}
        )
        for e in entries
    ]


@router.delete("/answer-bank/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank(
    entry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    # One statement scoped by user (D51): another user's entry, one that never existed and one
    # deleted meanwhile (a second tab: it waits for the first deletion) are all 404, and a
    # deletion is recorded once. Locks only this row.
    gone = db.scalar(
        delete(AnswerBankEntry)
        .where(AnswerBankEntry.id == entry_id, AnswerBankEntry.user_id == user.id)
        .returning(AnswerBankEntry.id)
    )
    if gone is None:
        raise not_found("Saved answer")
    record(db, user.id, "answer_bank.delete", "answer_bank", entry_id)
    db.commit()
