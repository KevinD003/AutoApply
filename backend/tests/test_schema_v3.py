"""C18 (D71): the one SCHEMA_VERSION=3 change. Preference facts are hashed by their value, a
document says where it came from and must fit the field's `accept`, an implicit resume is
explained as proposed, a generated document is used only once accepted, and an answer awaiting
consent is never written into a package version. Every approval given under 2 is invalidated.
Synthetic data only."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal, utcnow
from app.modules.documents.models import Document
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApplicationPackage, PackageApproval
from app.modules.preparation.resolver import accepts
from tests.execution_harness import Receiver, prepared_application
from tests.test_input_binding import GENDER, answer, start
from tests.test_preparation import setup_candidate

SALARY = {"key": "salary", "label": "Expected annual salary (USD)", "type": "number",
          "required": True}  # fmt: skip
RESUME = {"key": "resume", "label": "Resume/CV", "type": "file", "required": True,
          "accept": ".pdf,.docx"}  # fmt: skip
TXT = b"Synthetic plain-text resume.\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


def view(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()


def rows(v) -> dict:
    return {a["key"]: a for a in v["package"]["content"]["answers"]}


def prefs(api, **salary):
    body = {"salary_min": 50000, "salary_max": 60000, "salary_currency": "USD",
            "salary_period": "year"} | salary  # fmt: skip
    assert api.put("/profile/preferences", json=body).status_code == 200


def test_the_schema_is_3():
    assert pk.SCHEMA_VERSION == 3


def test_changing_only_the_salary_range_is_a_new_version(api):
    """A number field sends the minimum; the maximum is in the fact reference's value, which the
    hash covers (under 2 it sat in a `version` the hash leaves out)."""
    setup_candidate(api)
    prefs(api)
    _, app_id = start(api, SALARY)
    before = view(api, app_id)["package"]
    assert rows(view(api, app_id))["salary"]["value"] == {"number": 50000.0}
    prefs(api, salary_max=70000)
    after = view(api, app_id)["package"]
    assert rows(view(api, app_id))["salary"]["value"] == {"number": 50000.0}
    assert after["content_hash"] != before["content_hash"] and after["version"] > before["version"]
    (ref,) = rows(view(api, app_id))["salary"]["fact_refs"]
    assert ref["value"] == {"min": "50000.00", "max": "70000.00", "currency": "usd",
                            "period": "year"} and "version" not in ref  # fmt: skip


@pytest.mark.parametrize(
    "accept,name,ctype,ok",
    [
        (None, "cv.txt", "text/plain", True),
        (".pdf,.docx", "cv.pdf", "application/pdf", True),
        (
            ".pdf,.docx",
            "CV.DOCX",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            True,
        ),
        (".pdf,.docx", "cv.txt", "text/plain", False),
        ("application/pdf", "cv.pdf", "application/pdf", True),
        ("application/pdf", "cv.txt", "text/plain", False),
        ("text/*", "cv.txt", "text/plain", True),
        ("image/*", "cv.pdf", "application/pdf", False),
    ],
)
def test_accepts(accept, name, ctype, ok):
    assert accepts(accept, name, ctype) is ok


def test_a_txt_resume_into_a_pdf_or_docx_field_is_a_checkpoint(api):
    setup_candidate(api)  # uploads a PDF resume
    txt = api.post("/documents", files={"file": ("plain.txt", TXT, "text/plain")},
                   data={"kind": "resume"}).json()  # fmt: skip
    _, app_id = start(api, RESUME)
    r = api.put(f"/applications/{app_id}/documents", json={"resume_document_id": txt["id"]})
    row = rows(r.json())["resume"]
    assert row["status"] == "needs_user" and row["value"] is None
    assert "takes .pdf,.docx files; plain.txt is not one" in row["explanation"]
    assert r.json()["package"]["content"]["documents"] == []


def test_an_implicit_resume_is_explained_as_proposed_and_a_chosen_one_as_chosen(api):
    doc = setup_candidate(api)
    _, app_id = start(api, RESUME)
    row = rows(view(api, app_id))["resume"]
    assert row["status"] == "resolved" and "NoEfforts proposes it" in row["explanation"]
    r = api.put(f"/applications/{app_id}/documents", json={"resume_document_id": doc["id"]})
    assert rows(r.json())["resume"]["explanation"] == (
        "The resume version you chose for this application."
    )


def generated(api, base_id) -> uuid.UUID:
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        base = db.get(Document, uuid.UUID(base_id))
        d = Document(user_id=me, lineage_id=uuid.uuid4(), version=1, kind=base.kind,
                     label="Tailored resume", original_filename="tailored.pdf",
                     content_type="application/pdf", size_bytes=base.size_bytes,
                     sha256=base.sha256, storage_key=base.storage_key, origin="generated",
                     base_document_id=base.id, grounding_hash="a" * 64)  # fmt: skip
        db.add(d)
        db.commit()
        return d.id


def test_a_generated_document_is_used_only_once_accepted(api):
    base = setup_candidate(api)
    gen = generated(api, base["id"])
    _, app_id = start(api, RESUME)
    # Two resume lineages now: none is proposed, and the unaccepted one cannot be chosen.
    r = api.put(f"/applications/{app_id}/documents", json={"resume_document_id": str(gen)})
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: document_not_accepted)")
    with SessionLocal() as db:
        db.get(Document, gen).accepted_at = utcnow()
        db.commit()
    r = api.put(f"/applications/{app_id}/documents", json={"resume_document_id": str(gen)})
    (doc,) = r.json()["package"]["content"]["documents"]
    assert (doc["origin"], doc["base_document_id"], doc["grounding_hash"]) == (
        "generated", base["id"], "a" * 64)  # fmt: skip
    assert doc["accepted_at"] is not None


def test_an_uploaded_document_records_its_origin(api):
    setup_candidate(api)
    _, app_id = start(api, RESUME)
    (doc,) = view(api, app_id)["package"]["content"]["documents"]
    assert (doc["origin"], doc["base_document_id"], doc["grounding_hash"], doc["accepted_at"]) == (
        "upload", None, None, None)  # fmt: skip


def test_an_answer_awaiting_consent_is_never_written_into_a_version(api):
    """The page shows it from your live answer; a version records it only once you include it."""
    setup_candidate(api)
    _, app_id = start(api, GENDER)
    answer(api, app_id, "gender", {"label": "Female"})
    v = view(api, app_id)
    row = rows(v)["gender"]
    assert row["status"] == "needs_consent" and row["value"] is None and row["display"] is None
    assert v["review"]["gender"]["proposed"] == "Female"
    with SessionLocal() as db:
        kept = db.scalars(select(ApplicationPackage).where(
            ApplicationPackage.application_id == uuid.UUID(app_id))).all()  # fmt: skip
    for p in kept:  # the option list names it too; the row's own value and display never
        (g,) = [a for a in p.content["answers"] if a["key"] == "gender"]
        assert (g["value"], g["display"]) == (None, None), p.version
    r = api.put(f"/applications/{app_id}/consents", json={"key": "gender", "choice": "disclose"})
    assert rows(r.json())["gender"]["status"] == "resolved"
    assert rows(r.json())["gender"]["display"] == "Female"
    r = api.put(f"/applications/{app_id}/consents", json={"key": "gender", "choice": "withhold"})
    assert rows(r.json())["gender"]["status"] == "blank_optional"


def test_an_approval_given_under_schema_2_is_invalidated(api, receiver):
    """A package built under 2 is rebuilt under 3 at its next load: a new version, and the
    approval of the old one no longer counts."""
    app_id = prepared_application(api, receiver)
    with SessionLocal() as db:
        pkg = pk.latest_package(db, uuid.UUID(app_id))
        old = {**pkg.content, "schema": 2, "policy": {**pkg.content["policy"], "package_schema": 2}}
        pkg.content, pkg.content_hash = old, pk.content_hash(old)
        for a in db.scalars(select(PackageApproval).where(PackageApproval.package_id == pkg.id)):
            a.content_hash = pkg.content_hash
            a.expires_at = utcnow() + timedelta(days=1)
        db.commit()
        stale = pkg.version
    v = view(api, app_id)
    assert v["package"]["version"] > stale and v["package"]["content"]["schema"] == 3
    assert v["approval"]["status"] != "approved"
