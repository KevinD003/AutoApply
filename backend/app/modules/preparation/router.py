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
from app.modules.preparation import bank_edit, bankscope, binding, drafting, generation
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
                extract_form_schema(fixture_html(body.fixture), challenges=True),
                "fixture",
                body.fixture,
            )
        elif body.html is not None:
            schema, source, ref = extract_form_schema(body.html, challenges=True), "html", None
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
    """Local test fixture only (callers check is_fixture_origin; so does every connection,
    by the address it reaches): no proxies, no redirects."""
    from app.core.urlsafety import fixture_opener

    with fixture_opener().open(url, timeout=10) as r:
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


@router.post("/jobs/{job_id}/form/lever", status_code=status.HTTP_201_CREATED)
def capture_lever_form(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Read a Lever-style posting's form page and store its schema (D85). Only the local
    Lever-style approximation is read: a real Lever posting is refused before any request, and
    reading one would not be permission to submit an application."""
    from urllib.parse import urljoin, urlsplit

    from app.core.urlsafety import is_fixture_origin
    from app.modules.preparation import lever

    job = _owned_job(db, user, job_id)
    url = job.url or job.canonical_url or ""
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    posting = lever.parse_posting(url, fixture_origin=is_fixture_origin(origin))
    if posting is None:
        raise bad_request("This job's address is not a Lever-style posting")
    if not posting.fixture:
        raise conflict(
            "Reading real Lever postings is not enabled in this version; it needs separate "
            "approval. Apply on the employer's site and record it in the tracker."
        )
    form_page = origin + lever.apply_path(posting)
    try:
        schema = extract_form_schema(
            _fetch_fixture(form_page).decode("utf-8", "replace"), challenges=True
        )
    except (OSError, ValueError, ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the posting's form ({type(e).__name__})") from None
    target = urlsplit(urljoin(form_page, schema.action or ""))
    if (f"{target.scheme}://{target.netloc}" != origin or target.path != lever.apply_path(posting)
            or (schema.method or "").lower() != "post"):  # fmt: skip
        raise conflict(
            "Could not capture the form: it does not submit to this posting. Nothing was sent; "
            "apply on the employer's site. (reason: form_submits_elsewhere)"
        )
    source, ref = "fixture_lever", f"{posting.site}/{posting.posting_id}"
    return _store_form(db, user, job, schema, source, ref, EXTRACTION_VERSION)


@router.post("/jobs/{job_id}/form/ashby", status_code=status.HTTP_201_CREATED)
def capture_ashby_form(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Read an Ashby-style posting's application page and store its schema (D87). Only the
    local Ashby-style approximation is read: a real Ashby posting is refused before any request,
    and reading one would not be permission to submit an application."""
    from urllib.parse import urljoin, urlsplit

    from app.core.urlsafety import is_fixture_origin
    from app.modules.preparation import ashby

    job = _owned_job(db, user, job_id)
    url = job.url or job.canonical_url or ""
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    posting = ashby.parse_posting(url, fixture_origin=is_fixture_origin(origin))
    if posting is None:
        raise bad_request("This job's address is not an Ashby-style posting")
    if not posting.fixture:
        raise conflict(
            "Reading real Ashby postings is not enabled in this version; it needs separate "
            "approval. Apply on the employer's site and record it in the tracker."
        )
    form_page = origin + ashby.application_path(posting)
    try:
        schema = ashby.extract_schema(_fetch_fixture(form_page).decode("utf-8", "replace"))
    except (OSError, ValueError, ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the posting's form ({type(e).__name__})") from None
    target = urlsplit(urljoin(form_page, schema.action or ""))
    if (f"{target.scheme}://{target.netloc}" != origin
            or target.path != ashby.application_path(posting)
            or (schema.method or "").lower() != "post"):  # fmt: skip
        raise conflict(
            "Could not capture the form: it does not submit to this posting. Nothing was sent; "
            "apply on the employer's site. (reason: form_submits_elsewhere)"
        )
    source, ref = "fixture_ashby", f"{posting.board}/{posting.posting_id}"
    return _store_form(db, user, job, schema, source, ref, EXTRACTION_VERSION)


@router.post("/jobs/{job_id}/form/workday", status_code=status.HTTP_201_CREATED)
def capture_workday_form(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Read a Workday-style posting's application page and store its schema, checkpoint-first
    (D88). Only the local Workday-style approximation is read: a real Workday posting is refused
    before any request, and reading one would not be permission to submit an application."""
    from urllib.parse import urljoin, urlsplit

    from app.core.urlsafety import is_fixture_origin
    from app.modules.preparation import workday

    job = _owned_job(db, user, job_id)
    url = job.url or job.canonical_url or ""
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    posting = workday.parse_posting(url, fixture_origin=is_fixture_origin(origin))
    if posting is None:
        raise bad_request("This job's address is not a Workday-style posting")
    if not posting.fixture:
        raise conflict(
            "Reading real Workday postings is not enabled in this version; it needs separate "
            "approval. Apply on the employer's site and record it in the tracker."
        )
    form_page = origin + workday.apply_path(posting)
    try:
        schema = workday.extract_schema(_fetch_fixture(form_page).decode("utf-8", "replace"))
    except (OSError, ValueError, ExtractionError, ValidationError) as e:
        raise bad_request(f"Could not read the posting's form ({type(e).__name__})") from None
    target = urlsplit(urljoin(form_page, schema.action or ""))
    if (f"{target.scheme}://{target.netloc}" != origin
            or target.path != workday.apply_path(posting)
            or (schema.method or "").lower() != "post"):  # fmt: skip
        raise conflict(
            "Could not capture the form: it does not submit to this posting. Nothing was sent; "
            "apply on the employer's site. (reason: form_submits_elsewhere)"
        )
    source, ref = "fixture_workday", f"{posting.tenant}/{posting.req}"
    return _store_form(db, user, job, schema, source, ref, EXTRACTION_VERSION)


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
        select(AnswerDraft)
        .where(AnswerDraft.application_id == app.id, AnswerDraft.status == "proposed")
        .order_by(AnswerDraft.created_at, AnswerDraft.id)
    ).all()
    facts = {f.id: f for f in drafting.grounding_facts(db, app.user_id)} if drafts else {}
    _, drafting_status = drafting.provider_for(db, db.get(User, app.user_id))
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
        # C12 (D64): what the review page may offer per question (outside the content); C18:
        # an answer awaiting your consent, read from your live answer.
        "review": _review(db, app, pkg),
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
        # L4 (D74): why drafting is or is not available to this user (drafting.provider_for).
        "drafting_available": drafting_status == "available",
        "drafting_status": drafting_status,
        "drafts": [
            {
                "id": str(d.id),
                "field_key": d.field_key,
                "text": d.text,
                "evidence": d.evidence,
                # C15 (D68): the facts the draft cites, as they are now; a fact changed or
                # withdrawn since is listed without text.
                "cited": [
                    {"kind": facts[e].kind, "text": facts[e].text}
                    if e in facts
                    else {"kind": None, "text": None}
                    for e in d.evidence
                ],
                "provider": d.provider,
                "created_at": d.created_at,
            }
            for d in drafts
        ],
    }


def _review(db: Session, app: Application, pkg: ApplicationPackage) -> dict:
    out = pk.review_controls(db, app.id, pkg.content)
    for key, (value, display) in pk.live_proposals(db, app).items():
        if key in out:
            out[key] = out[key] | {"proposed": display, "proposed_value": value}
    return out


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
    "credential": "This is about a licence, certification or credential: keep those in your "
    "profile's credentials, which record when they expire, so its answer is never saved for "
    "reuse.",
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
    bank_edit.keep_version(db, db.scalars(stmt).one(), bank_edit.SAVED)  # C (D78): history


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
            # C18: the answer as proposed now (a package version no longer keeps it).
            proposed = pk.live_proposals(db, app).get(key, (entry["value"], None))[0]
            meta["value_digest"] = binding.value_digest(user.id, key, proposed)
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
        if (code := generation.refusal(db, doc, app.id)) is not None:
            raise conflict(f"{generation.REFUSALS[code]} (reason: {code})")
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
    provider = _drafting_provider(db, user, "Write this answer yourself.")
    facts = drafting.grounding_facts(db, user.id)
    if not facts:
        raise bad_request(
            "Add work history or a summary to your profile first; drafts only "
            "use facts you have entered."
        )
    req = _draft_request(db, app, f, facts)
    h = req.input_hash()
    # A draft the user rejected is never offered again; an accepted one is shown as accepted.
    cached = db.scalar(
        select(AnswerDraft)
        .where(
            AnswerDraft.application_id == app.id,
            AnswerDraft.field_key == key,
            AnswerDraft.input_hash == h,
            AnswerDraft.status != "rejected",
        )
        .order_by(AnswerDraft.created_at.desc())
        .limit(1)
    )
    if cached is None:
        instead = "Write this answer yourself or ask again."
        try:
            result = _call_provider(provider, req, instead)
        except drafting.ProviderFailed as e:
            record(db, user.id, "draft.provider_failed", "application", app.id,
                   field_ref=ref(key, user.id), reason_code=e.code)  # fmt: skip
            db.commit()
            raise _provider_failed(e, instead) from None
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
            # C15 (D68): the cited facts as they were when drafted, compared at accept.
            grounding_hash=drafting.grounding_hash(drafting.cited(facts, result.evidence)),
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


class DraftingConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The version of the consent text the user read (drafting_access.CONSENT_VERSION).
    version: str = Field(min_length=1, max_length=64)


def _consent_view(db: Session, user: User) -> dict:
    """L4 (D74): whether AI drafting is offered to this account, the exact consent text with
    what is sent and what never is, and whether the user agreed to this text."""
    from app.modules.preparation import drafting_access as da

    configured = drafting.get_provider()
    offered = (
        configured is not None and getattr(configured, "external", False) and da.is_owner(user)
    )
    _, why = drafting.provider_for(db, user)
    c = da.consent_of(db, user.id, configured.name) if offered else None
    live = c is not None and c.withdrawn_at is None
    return {
        "status": why,
        "offered": offered,
        "provider": "Anthropic (Claude)" if offered else None,
        "model": configured.model if offered else None,
        "consent": {
            "version": da.CONSENT_VERSION,
            "text": da.CONSENT_TEXT,
            "sends": list(da.SENDS),
            "never_sends": list(da.NEVER_SENDS),
        },  # fmt: skip
        "given_at": c.given_at if live and c.consent_version == da.CONSENT_VERSION else None,
        # Agreed to an earlier wording: it no longer counts until the user agrees again.
        "earlier_text": live and c.consent_version != da.CONSENT_VERSION,
        "spent_today_usd": float(da.spent_today(db)) if offered else None,
        "daily_budget_usd": float(da.budget()) if offered else None,
    }


@router.get("/drafting/consent")
def get_drafting_consent(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _consent_view(db, user)


@router.put("/drafting/consent")
def give_drafting_consent(
    body: DraftingConsentIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    from app.modules.preparation import drafting_access as da

    view = _consent_view(db, user)
    if not view["offered"]:
        raise conflict(
            "AI drafting is not offered to this account; nothing was recorded. "
            "(reason: drafting_not_available)"
        )
    provider = drafting.get_provider()
    try:
        c = da.give(db, user, provider.name, body.version)
    except ValueError:
        raise conflict(
            "The consent text has changed since you read it; read it again. Nothing was "
            "recorded. (reason: consent_text_changed)"
        ) from None
    record(db, user.id, "drafting.consent_given", "drafting_consent", c.id,
           provider=provider.name, consent_version=c.consent_version)  # fmt: skip
    db.commit()
    return _consent_view(db, user)


@router.delete("/drafting/consent")
def withdraw_drafting_consent(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    from app.modules.preparation import anthropic_provider as ap
    from app.modules.preparation import drafting_access as da

    if da.withdraw(db, user, ap.NAME):
        c = da.consent_of(db, user.id, ap.NAME)
        record(db, user.id, "drafting.consent_withdrawn", "drafting_consent", c.id,
               provider=ap.NAME)  # fmt: skip
        db.commit()
    return _consent_view(db, user)


@router.get("/drafting/usage")
def get_drafting_usage(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """D97: this account's drafting requests against the server's daily budget, each amount
    with its basis (estimated, worst case kept, held, nothing sent). Never the provider's bill."""
    from app.modules.preparation import drafting_access as da

    configured = drafting.get_provider()
    offered = (
        configured is not None and getattr(configured, "external", False) and da.is_owner(user)
    )
    return da.usage_view(db, user, offered, configured.name if offered else None,
                         configured.model if offered else None)  # fmt: skip


_NOT_CONFIGURED = "AI drafting is not configured."


def _drafting_provider(db: Session, user: User, instead: str):
    """L4 (D74): the provider this user may use now, or the refusal that says why not."""
    provider, why = drafting.provider_for(db, user)
    if provider is not None:
        return provider
    if why == "consent_needed":
        raise conflict(
            "Turn on AI drafting in your profile first: it says what is sent, and to whom. "
            "(reason: drafting_consent_needed)"
        )
    if why == "budget_reached":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Today's AI drafting budget on this server is used up. {instead} "
            "(reason: drafting_budget_reached)",
        )
    if why == "not_for_this_account":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"AI drafting is not available for this account. {instead} "
            "(reason: drafting_not_for_this_account)",
        )
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{_NOT_CONFIGURED} {instead}")


def _call_provider(provider, req, instead: str) -> drafting.DraftResult:
    """One request to the provider; a spent budget is refused before anything is sent. A
    provider failure (drafting.ProviderFailed) is the caller's to record (L4, D74)."""
    from app.modules.preparation import drafting_access

    try:
        return provider.draft(req)
    except drafting_access.BudgetReached:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Today's AI drafting budget on this server is used up. {instead} "
            "(reason: drafting_budget_reached)",
        ) from None


def _provider_failed(e: drafting.ProviderFailed, instead: str) -> HTTPException:
    """Nothing the provider returned is kept or shown: a fixed message and code only."""
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        f"{drafting.PROVIDER_FAILURES[e.code]} Nothing was kept. {instead} (reason: {e.code})",
    )


def _draft_request(db: Session, app: Application, f: FormField, facts) -> drafting.DraftRequest:
    """One construction for requesting and accepting a draft, so that accept can tell whether
    anything the draft was made from has changed (C15, D68)."""
    job = db.get(Job, app.job_id)
    return drafting.DraftRequest(
        question=f.label,
        help_text=f.help_text,
        max_chars=f.max_length or 1500,
        employer=job.employer,
        job_title=job.title,
        job_text=(job.description or "")[:6000] or None,
        facts=facts,
    )


def _owned_draft(db: Session, app: Application, draft_id: uuid.UUID) -> AnswerDraft:
    d = db.get(AnswerDraft, draft_id)
    if d is None or d.application_id != app.id or d.user_id != app.user_id:
        raise not_found("Draft")
    return d


DRAFT_REFUSALS = {
    # C15 (D68): why a draft cannot be used; the code is the "(reason: code)" suffix.
    "draft_rejected": "You rejected this draft; request a new one.",
    "not_draftable": "This question can no longer be drafted; write the answer yourself.",
    "draft_facts_changed": "Facts this draft relied on have changed; request a new draft.",
    "draft_inputs_changed": "The question, the job or your facts changed since this draft was "
    "made; request a new draft.",
    "draft_does_not_fit": "This draft no longer fits the question; request a new draft or "
    "write the answer yourself.",
}


def _draft_refused(code: str) -> HTTPException:
    return conflict(f"{DRAFT_REFUSALS[code]} (reason: {code})")


@router.post("/applications/{app_id}/drafts/{draft_id}/accept")
def accept_draft(
    app_id: uuid.UUID,
    draft_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    app = _owned_app(db, user, app_id)
    d = _owned_draft(db, app, draft_id)
    entry, f = _field(db, app, d.field_key)
    pk.lock_application(db, app.id)
    if d.status == "rejected":
        raise _draft_refused("draft_rejected")
    if not entry["draftable"]:
        raise _draft_refused("not_draftable")  # e.g. the question now reads as sensitive
    facts = drafting.grounding_facts(db, user.id)
    used = drafting.cited(facts, d.evidence)
    if used is None or (
        d.grounding_hash is not None and drafting.grounding_hash(used) != d.grounding_hash
    ):
        raise _draft_refused("draft_facts_changed")
    if _draft_request(db, app, f, facts).input_hash() != d.input_hash:
        raise _draft_refused("draft_inputs_changed")
    try:
        value = normalize_input(f, {"text": d.text})
    except ValueError:
        raise _draft_refused("draft_does_not_fit") from None
    _upsert_input(
        db,
        app,
        "answer",
        d.field_key,
        value,
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
    record(db, user.id, "draft.accepted", "application", app.id,
           field_ref=ref(d.field_key, user.id))  # fmt: skip
    db.flush()
    return _package_view(db, app, _current(db, app))


@router.post("/applications/{app_id}/drafts/{draft_id}/reject")
def reject_draft(
    app_id: uuid.UUID,
    draft_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """C15 (D68): the user rejects a proposed draft. Its text is erased at once; the row keeps
    only what is needed never to offer it again. An accepted draft is the user's answer and is
    changed or cleared on the review page instead."""
    app = _owned_app(db, user, app_id)
    d = _owned_draft(db, app, draft_id)
    if d.status == "accepted":
        raise conflict(
            "This draft is already your answer; change or clear the answer instead. "
            "(reason: draft_accepted)"
        )
    if d.status != "rejected":
        d.status, d.text = "rejected", None
        record(db, user.id, "draft.rejected", "application", app.id,
               field_ref=ref(d.field_key, user.id), reason_code="by_user")  # fmt: skip
    db.flush()
    return _package_view(db, app, _current(db, app))


# ---------------------------------------------------------------------------------------------
# L2/L3 (D73): tailored resumes and cover letters, generated only through the drafting provider


class GenerateIn(BaseModel):
    kind: Literal["resume", "cover_letter"]


def _generated(db: Session, app: Application, doc: Document, storage) -> dict:
    """What the review page shows of a generated document: its text, the facts it cites as they
    are now, whether it can still be used, and for a tailored resume the lines changed from the
    resume it replaces."""
    import difflib

    from app.modules.documents.extract import ExtractError, extract_text

    def text_of(d: Document) -> str | None:
        try:
            return extract_text(d.content_type, storage.get(d.storage_key))
        except (ExtractError, OSError):
            return None

    text = text_of(doc) or ""
    facts = {f.id: f for f in drafting.grounding_facts(db, app.user_id)}
    diff = None
    base = db.get(Document, doc.base_document_id) if doc.base_document_id else None
    if base is not None and base.user_id == app.user_id:
        before = text_of(base)
        if before is not None:
            diff = [
                {"op": line[0], "line": line[2:]}
                for line in difflib.ndiff(before.splitlines(), text.splitlines())
                if line[0] in "+- "
            ]
    return {
        "id": str(doc.id),
        "kind": doc.kind.value,
        "label": doc.label,
        "created_at": doc.created_at,
        "accepted": doc.accepted_at is not None,
        "usable": generation.refusal(db, doc, app.id) is None,
        "stale": generation.is_stale(db, doc),
        "text": text,
        "cited": [
            {"kind": facts[e].kind, "text": facts[e].text} if e in facts
            else {"kind": None, "text": None}
            for e in doc.grounded_on or []
        ],
        "base_label": base.label if base is not None else None,
        "diff": diff,
    }  # fmt: skip


def _owned_generated(db: Session, app: Application, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    if (
        doc is None
        or doc.user_id != app.user_id
        or doc.origin != "generated"
        or doc.made_for_application_id != app.id
    ):
        raise not_found("Generated document")
    return doc


@router.post("/applications/{app_id}/generated-documents", status_code=status.HTTP_201_CREATED)
def generate_document(
    app_id: uuid.UUID,
    body: GenerateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """A tailored resume or a cover letter for this application, from your approved facts only.
    Nothing is used until you accept it."""
    import hashlib

    from app.modules.documents.extract import DOCX
    from app.modules.documents.storage import get_storage

    app = _owned_app(db, user, app_id)
    provider = _drafting_provider(db, user, "Upload your own resume or cover letter instead.")
    facts = drafting.grounding_facts(db, user.id)
    if not facts:
        raise bad_request(
            "Add work history or a summary to your profile first; generated documents only use "
            "facts you have approved."
        )
    job = db.get(Job, app.job_id)
    kind, _, noun = generation.KINDS[body.kind]
    req = generation.request_for(job, body.kind, facts)
    instead = "Upload your own or ask again."
    try:
        result = _call_provider(provider, req, instead)
    except drafting.ProviderFailed as e:
        record(db, user.id, "document.generation_failed", "application", app.id,
               kind=body.kind, reason_code=e.code)  # fmt: skip
        db.commit()
        raise _provider_failed(e, instead) from None
    try:
        text = drafting.validate_draft(req, result)
    except drafting.InvalidDraft as e:
        record(db, user.id, "document.generation_rejected", "application", app.id,
               kind=body.kind, reason_code=e.code)  # fmt: skip
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The {noun} failed validation and was discarded: {e} (reason: {e.code})",
        ) from None
    base = None
    if kind == DocumentKind.resume:
        chosen = pk.load_context(db, app).documents.get("resume")
        base = chosen if chosen is not None and chosen.origin != "generated" else None
    storage = get_storage()
    data = generation.docx_bytes(text)
    doc = Document(
        user_id=user.id,
        lineage_id=uuid.uuid4(),
        version=1,
        kind=kind,
        label=f"{noun.capitalize()} for {job.title or 'this job'}"[:200],
        original_filename=f"{body.kind.replace('_', '-')}.docx",
        content_type=DOCX,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=storage.put(data),
        origin="generated",
        base_document_id=base.id if base is not None else None,
        grounding_hash=drafting.grounding_hash(drafting.cited(facts, result.evidence)),
        grounded_on=list(result.evidence),
        made_for_application_id=app.id,
    )
    db.add(doc)
    db.flush()
    record(db, user.id, "document.generated", "document", doc.id, kind=body.kind,
           provider=result.provider, cost_usd=result.cost_usd)  # fmt: skip
    db.commit()
    return _generated(db, app, doc, storage)


@router.get("/applications/{app_id}/generated-documents")
def list_generated(
    app_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[dict]:
    from app.modules.documents.storage import get_storage

    app = _owned_app(db, user, app_id)
    docs = db.scalars(
        select(Document)
        .where(
            Document.user_id == user.id,
            Document.origin == "generated",
            Document.made_for_application_id == app.id,
        )
        .order_by(Document.created_at, Document.id)
    ).all()
    storage = get_storage()
    return [_generated(db, app, d, storage) for d in docs]


@router.post("/applications/{app_id}/generated-documents/{doc_id}/accept")
def accept_generated(
    app_id: uuid.UUID,
    doc_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """You read it and it is yours to choose for this application. Refused when a fact it cites
    has changed since it was written."""
    from app.modules.documents.storage import get_storage

    app = _owned_app(db, user, app_id)
    doc = _owned_generated(db, app, doc_id)
    db.execute(select(Document.id).where(Document.id == doc.id).with_for_update())
    if generation.is_stale(db, doc):
        raise conflict(f"{generation.REFUSALS['document_facts_changed']} "
                       "(reason: document_facts_changed)")  # fmt: skip
    if doc.accepted_at is None:
        doc.accepted_at = utcnow()
        record(db, user.id, "document.generated_accepted", "document", doc.id,
               kind=doc.kind.value)  # fmt: skip
    db.commit()
    return _generated(db, app, doc, get_storage())


@router.post(
    "/applications/{app_id}/generated-documents/{doc_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reject_generated(
    app_id: uuid.UUID,
    doc_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a generated document you did not accept, with its file. One you accepted is
    deleted from Documents instead (C17), which checks nothing still needs it."""
    from app.modules.documents.storage import get_storage

    app = _owned_app(db, user, app_id)
    doc = _owned_generated(db, app, doc_id)
    if doc.accepted_at is not None:
        raise conflict(
            "You accepted this document; delete it from Documents instead. "
            "(reason: document_accepted)"
        )
    key = doc.storage_key
    db.delete(doc)
    record(db, user.id, "document.generated_rejected", "application", app.id,
           kind=doc.kind.value)  # fmt: skip
    db.commit()
    get_storage().delete(key)


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
    "credential": "Licences and certifications come from your profile's credentials.",
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


class BankValueIn(BaseModel):
    value: dict


class BankEditOut(BaseModel):
    entry: BankOut
    changed: bool
    applications_to_approve_again: int


class BankVersionOut(BaseModel):
    version: int
    value: dict
    how: str
    recorded_at: datetime


@router.put("/answer-bank/{entry_id}", response_model=BankEditOut)
def edit_bank(
    entry_id: uuid.UUID,
    body: BankValueIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """C (D78): a new version of the answer; the question it is bound to is unchanged, and
    every application that used the earlier version asks for approval again."""
    try:
        out = bank_edit.edit(db, user.id, entry_id, body.value)
    except bank_edit.EditRefused as e:
        db.rollback()
        raise bad_request(str(e)) from None
    if out is None:
        raise not_found("Saved answer")
    entry, changed, invalidated = out
    view = BankOut.model_validate(entry).model_copy(
        update={"not_reused": NOT_REUSED.get(saved_answer_scope(entry))}
    )
    return BankEditOut(entry=view, changed=changed, applications_to_approve_again=invalidated)


@router.get("/answer-bank/{entry_id}/history", response_model=list[BankVersionOut])
def bank_history(
    entry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    out = bank_edit.history(db, user.id, entry_id)
    if out is None:
        raise not_found("Saved answer")
    return out


class BankImportRow(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=4000)


class BankImportIn(BaseModel):
    rows: list[BankImportRow] = Field(min_length=1, max_length=5000)
    dry_run: bool = True


@router.post("/answer-bank/import")
def import_bank(
    body: BankImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """D99: question/answer pairs from a file, judged by the rules for saved answers. With
    `dry_run` nothing is written; otherwise the importable rows become proposals that answer
    nothing until approved. The response says what happened to each row by its position and a
    reason code, never by its text; the audit keeps counts only."""
    from app.modules.preparation import bank_import as bi

    rows = [bi.Row(r.question, r.answer) for r in body.rows]
    decisions = bi.plan(db, user.id, rows)
    refused: dict[str, int] = {}
    for d in decisions:
        if d.outcome == "refused":
            refused[d.reason] = refused.get(d.reason, 0) + 1
    added = 0
    if not body.dry_run:
        added = bi.apply(db, user.id, decisions)
        record(db, user.id, "answer_bank.import", "answer_bank", None, rows=len(rows),
               added=added, refused=sum(refused.values()))  # fmt: skip
        db.commit()
    return {
        "dry_run": body.dry_run,
        "rows": len(rows),
        "importable": sum(d.outcome == "import" for d in decisions),
        "added": added,
        "refused": refused,
        "reasons": {
            k: bi.REASONS.get(k) or NOT_REUSED.get(k) or bi.REASONS["not_saved"] for k in refused
        },
        "outcomes": [
            {"row": i, "outcome": d.outcome, "reason": d.reason} for i, d in enumerate(decisions)
        ],  # fmt: skip
    }


@router.post("/answer-bank/{entry_id}/approve", response_model=BankOut)
def approve_bank(
    entry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """D99: an imported proposal becomes a saved answer you approved; only then is it reused."""
    from app.modules.preparation import bank_import as bi

    try:
        e = bi.approve(db, user.id, entry_id)
    except ValueError:
        db.rollback()
        raise conflict("This saved answer is not waiting for your approval.") from None
    if e is None:
        raise not_found("Saved answer")
    record(db, user.id, "answer_bank.approve", "answer_bank", entry_id)
    db.commit()
    return BankOut.model_validate(e).model_copy(
        update={"not_reused": NOT_REUSED.get(saved_answer_scope(e))}
    )


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
