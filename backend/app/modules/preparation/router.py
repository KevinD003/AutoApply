import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import bad_request, conflict, not_found
from app.modules.applications.models import Application
from app.modules.audit.service import record, ref
from app.modules.documents.models import Document, DocumentKind
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation import drafting
from app.modules.preparation import greenhouse as gh
from app.modules.preparation import package as pk
from app.modules.preparation.fixtures_registry import FIXTURES, fixture_html
from app.modules.preparation.forms import (
    EXTRACTION_VERSION,
    ExtractionError,
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
    JobForm,
    PackageApproval,
)
from app.modules.preparation.resolver import (
    answer_shape,
    normalize_input,
    option_labels,
    question_key,
)
from app.modules.profiles.models import (
    Approval,
    Provenance,
)

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
    except gh.SchemaMismatch as e:
        raise conflict(f"Could not capture the form: {e}") from None
    except (OSError, ValueError, ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the job post ({type(e).__name__})") from None
    return _store_form(db, user, job, schema, source, posting.ref, extraction)


def _form_out(form) -> dict:
    return {
        "id": str(form.id),
        "version": form.version,
        "source": form.source,
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
        "approval": (
            {"status": "approved", "approved_at": appr.approved_at, "version": pkg.version}
            if appr
            else {
                "status": "invalidated",
                "approved_at": last.approved_at,
                "invalidated_at": last.invalidated_at,
                "reason": last.invalidation_reason,
            }
            if last and last.invalidated_at
            else {"status": "not_approved"}
        ),
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


class AnswerIn(BaseModel):
    value: dict
    save_to_bank: bool = False


@router.put("/applications/{app_id}/answers/{key}")
def put_answer(
    app_id: uuid.UUID,
    key: str,
    body: AnswerIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    entry, f = _field(db, app, key)
    if entry["acknowledgment"]:
        raise bad_request("Legal statements and consents are answered with a consent choice.")
    if not entry["user_input_allowed"] or entry["source"] in (
        "profile_fact",
        "deterministic_mapping",
    ):
        raise bad_request(
            "This answer comes from your verified profile. Update your profile "
            "instead, so every application stays consistent."
        )
    try:
        value = normalize_input(f, body.value)
    except ValueError as e:
        raise bad_request(str(e)) from None
    _upsert_input(db, app, "answer", key, value)
    if body.save_to_bank:
        if not entry["bankable"]:
            raise bad_request("This answer depends on the specific job and cannot be reused.")
        _save_to_bank(db, user, app, f, value, sensitive=entry["sensitive"])
    record(db, user.id, "application.answer", "application", app.id, field_ref=ref(key))
    db.flush()
    return _package_view(db, app, _current(db, app))


def _save_to_bank(db, user, app, f, value, sensitive: bool) -> None:
    shape = answer_shape(f)
    stored = (
        {"labels": [value["label"]]}
        if shape == "choice"
        else {"labels": [o["label"] for o in value["options"]]}
        if shape == "multi"
        else value
    )
    qk = question_key(f)
    entry = db.scalar(
        select(AnswerBankEntry).where(
            AnswerBankEntry.user_id == user.id, AnswerBankEntry.question_key == qk
        )
    )
    if entry is None:
        entry = AnswerBankEntry(user_id=user.id, question_key=qk, version=1)
        db.add(entry)
    elif entry.value != stored or entry.options_snapshot != option_labels(f):
        entry.version += 1
    entry.question_text, entry.answer_shape, entry.value = f.label, shape, stored
    entry.options_snapshot, entry.sensitive = option_labels(f), sensitive
    entry.provenance, entry.approval_status = Provenance.user_entered, Approval.approved
    entry.source_application_id = app.id


@router.delete("/applications/{app_id}/answers/{key}")
def delete_answer(
    app_id: uuid.UUID, key: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    row = db.scalar(
        select(ApplicationInput).where(
            ApplicationInput.application_id == app.id,
            ApplicationInput.kind == "answer",
            ApplicationInput.field_key == key,
        )
    )
    if row is not None:
        db.delete(row)
        db.flush()
    return _package_view(db, app, _current(db, app))


class ConsentIn(BaseModel):
    choice: Literal["agree", "decline", "disclose", "withhold"] | None


@router.put("/applications/{app_id}/consents/{key}")
def put_consent(
    app_id: uuid.UUID,
    key: str,
    body: ConsentIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    entry, _ = _field(db, app, key)
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
        _upsert_input(db, app, "consent", key, {"choice": body.choice})
    record(db, user.id, "application.consent", "application", app.id, field_ref=ref(key),
           choice=body.choice)  # fmt: skip
    db.flush()
    return _package_view(db, app, _current(db, app))


class DocumentsIn(BaseModel):
    resume_document_id: uuid.UUID | None = None
    cover_letter_document_id: uuid.UUID | None = None


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
    db.flush()
    return _package_view(db, app, _current(db, app))


class ApproveIn(BaseModel):
    version: int
    content_hash: str = Field(min_length=64, max_length=64)


@router.post("/applications/{app_id}/package/approve")
def approve_package(
    app_id: uuid.UUID,
    body: ApproveIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    try:
        pk.approve(db, app, body.version, body.content_hash)
    except pk.NoForm as e:
        raise conflict(str(e)) from None
    except pk.ApprovalError as e:
        db.commit()  # keep any new package version that was written while checking
        raise conflict(str(e)) from None
    db.commit()
    return _package_view(db, app, pk.latest_package(db, app.id))


@router.post("/applications/{app_id}/package/revoke")
def revoke_package(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
    pk.revoke(db, app)
    db.flush()
    return _package_view(db, app, _current(db, app))


# ---------------------------------------------------------------------------------------------
# Long-form drafting (optional)


@router.post("/applications/{app_id}/answers/{key}/draft")
def request_draft(
    app_id: uuid.UUID, key: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    app = _owned_app(db, user, app_id)
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
            record(db, user.id, "draft.rejected", "application", app.id, field_ref=ref(key),
                   reason_code=e.code)  # fmt: skip
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
            field=key,
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
        meta={
            "draft_id": str(d.id),
            "evidence": list(d.evidence),
            "grounding_hash": drafting.grounding_hash(used),
        },
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


@router.get("/answer-bank", response_model=list[BankOut])
def list_bank(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(AnswerBankEntry)
        .where(AnswerBankEntry.user_id == user.id)
        .order_by(AnswerBankEntry.updated_at.desc())
    ).all()


@router.delete("/answer-bank/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank(
    entry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    e = db.get(AnswerBankEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise not_found("Saved answer")
    db.delete(e)
    record(db, user.id, "answer_bank.delete", "answer_bank", entry_id)
    db.commit()
