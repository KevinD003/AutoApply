"""L2/L3 (D73): tailored resumes and cover letters, generated only through the drafting provider
(none is configured; a labelled test double stands in) from approved facts, checked like every
draft, stored as an unaccepted document written for one application, used only once accepted,
and never once a fact it cites changes. Synthetic data and the generic receiver only."""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.documents.extract import DOCX, extract_text
from app.modules.documents.models import Document
from app.modules.documents.storage import LocalStorage
from app.modules.preparation import drafting, generation
from tests.execution_harness import Receiver, prepared_application
from tests.test_drafting import Canned, use


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def ready(api, receiver, **kw) -> str:
    """The receiver's form for the synthetic candidate, with one approved work entry to cite."""
    app_id = prepared_application(api, receiver, approve=False, **kw)
    if not api.get("/profile/employment").json():
        api.post("/profile/employment", json={"employer": "Synthetic Care", "title": "Front Desk",
                                              "description": "Handled patient intake for 3 "
                                              "doctors."})  # fmt: skip
    return app_id


def generate(api, app_id, kind="resume"):
    return api.post(f"/applications/{app_id}/generated-documents", json={"kind": kind})


def stored(doc_id) -> Document:
    with SessionLocal() as db:
        d = db.get(Document, uuid.UUID(doc_id))
        db.expunge(d)
        return d


def file_of(doc: Document):
    return LocalStorage(get_settings().storage_dir)._path(doc.storage_key)


def resume_choice(api, app_id, doc_id):
    return api.put(f"/applications/{app_id}/documents", json={"resume_document_id": doc_id})


def test_nothing_is_generated_without_a_provider(api, receiver):
    app_id = ready(api, receiver)
    r = generate(api, app_id)
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(Document).where(Document.origin == "generated")) is None


def test_a_docx_round_trips_and_escapes_markup():
    text = "Line one <b>&</b>\nLine two"
    assert extract_text(DOCX, generation.docx_bytes(text)).splitlines() == text.splitlines()


def test_a_tailored_resume_is_stored_unaccepted_for_this_application(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("Front Desk at Synthetic Care\nHandled patient intake for 3 doctors."))
    r = generate(api, app_id)
    assert r.status_code == 201, r.text
    g = r.json()
    assert (g["kind"], g["accepted"], g["usable"], g["stale"]) == ("resume", False, False, False)
    assert g["text"].splitlines() == ["Front Desk at Synthetic Care",
                                      "Handled patient intake for 3 doctors."]  # fmt: skip
    assert g["base_label"] and g["diff"] is None  # the synthetic base PDF has no text to compare
    assert all(c["text"] for c in g["cited"])
    doc = stored(g["id"])
    assert (doc.origin, doc.made_for_application_id, doc.accepted_at) == (
        "generated", uuid.UUID(app_id), None)  # fmt: skip
    assert doc.base_document_id is not None and doc.content_type == DOCX
    assert doc.grounded_on and doc.grounding_hash
    # Not usable until accepted.
    r = resume_choice(api, app_id, g["id"])
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: document_not_accepted)")
    a = api.post(f"/applications/{app_id}/generated-documents/{g['id']}/accept").json()
    assert a["accepted"] and a["usable"]
    r = resume_choice(api, app_id, g["id"])
    docs = r.json()["package"]["content"]["documents"]
    (resume,) = [d for d in docs if d["field"] == "resume"]
    assert (resume["document_id"], resume["origin"]) == (g["id"], "generated")
    assert resume["base_document_id"] == str(doc.base_document_id)
    with SessionLocal() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))]
    assert "document.generated" in actions and "document.generated_accepted" in actions


def test_a_cover_letter_is_generated_without_a_base(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("I handled patient intake for 3 doctors and would like to help you."))
    g = generate(api, app_id, "cover_letter").json()
    assert (g["kind"], g["diff"], g["base_label"]) == ("cover_letter", None, None)


def test_a_document_failing_the_draft_checks_is_never_stored(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    for text, code in (("I supervised 12 doctors.", "invented_numbers"),
                       ("I will never need visa sponsorship.", "legal_status"),
                       ("I am a licensed practical nurse.", "uncited_credential"),
                       ("x" * 7000, "too_long")):  # fmt: skip
        use(monkeypatch, Canned(text))
        r = generate(api, app_id)
        assert r.status_code == 422 and r.json()["detail"].endswith(f"(reason: {code})"), text
    with SessionLocal() as db:
        assert db.scalar(select(Document).where(Document.origin == "generated")) is None
        rows = db.scalars(select(AuditEvent).where(
            AuditEvent.action == "document.generation_rejected")).all()  # fmt: skip
    assert len(rows) == 4 and all("text" not in r.meta for r in rows)


def test_the_request_holds_only_approved_facts_and_quoted_job_text(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    seen = use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    generate(api, app_id)
    (req,) = seen.requests
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        assert req.facts == drafting.grounding_facts(db, me)
    assert req.max_chars == 6000 and "using only the facts given" in req.question


def test_a_document_is_never_used_for_another_application(api, receiver, monkeypatch):
    first = ready(api, receiver)
    second = ready(api, receiver, slug="clinic2")
    use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    g = generate(api, first).json()
    api.post(f"/applications/{first}/generated-documents/{g['id']}/accept")
    r = resume_choice(api, second, g["id"])
    assert r.status_code == 409
    assert r.json()["detail"].endswith("(reason: document_for_another_application)")
    assert api.get(f"/applications/{second}/generated-documents").json() == []
    assert (
        api.post(f"/applications/{second}/generated-documents/{g['id']}/accept").status_code == 404
    )


def test_a_changed_fact_makes_it_unusable(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    g = generate(api, app_id).json()
    api.post(f"/applications/{app_id}/generated-documents/{g['id']}/accept")
    assert resume_choice(api, app_id, g["id"]).status_code == 200
    job = api.get("/profile/employment").json()[0]
    body = {k: job[k] for k in ("employer", "title")} | {"description": "Answered phones."}
    assert api.put(f"/profile/employment/{job['id']}", json=body).status_code == 200
    v = api.get(f"/applications/{app_id}/package").json()
    resume = next(a for a in v["package"]["content"]["answers"] if a["key"] == "resume")
    # The document you chose stops the row; your uploaded resume is never put in its place.
    assert (resume["status"], resume["value"]) == ("needs_user", None)
    assert "was generated from facts that have changed since" in resume["explanation"]
    assert all(d["field"] != "resume" for d in v["package"]["content"]["documents"])
    listed = api.get(f"/applications/{app_id}/generated-documents").json()[0]
    assert (listed["stale"], listed["usable"]) == (True, False)
    assert resume_choice(api, app_id, g["id"]).json()["detail"].endswith(
        "(reason: document_facts_changed)")  # fmt: skip


def test_rejecting_deletes_it_and_its_file(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    g = generate(api, app_id).json()
    f = file_of(stored(g["id"]))
    assert f.exists()
    r = api.post(f"/applications/{app_id}/generated-documents/{g['id']}/reject")
    assert r.status_code == 204 and not f.exists()
    assert api.get(f"/documents/{g['id']}/download").status_code == 404
    kept = generate(api, app_id).json()
    api.post(f"/applications/{app_id}/generated-documents/{kept['id']}/accept")
    r = api.post(f"/applications/{app_id}/generated-documents/{kept['id']}/reject")
    assert r.status_code == 409 and "(reason: document_accepted)" in r.json()["detail"]


def test_another_users_application_and_documents_are_404(api, other_api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    g = generate(api, app_id).json()
    assert generate(other_api, app_id).status_code == 404
    assert other_api.get(f"/applications/{app_id}/generated-documents").status_code == 404
    for action in ("accept", "reject"):
        url = f"/applications/{app_id}/generated-documents/{g['id']}/{action}"
        assert other_api.post(url).status_code == 404
    assert stored(g["id"]).accepted_at is None


def test_a_tailored_resume_shows_what_changed_from_its_base(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    file = ("base.txt", b"Front Desk\nAnswered phones.\n", "text/plain")
    base = api.post("/documents", files={"file": file}, data={"kind": "resume"}).json()
    assert resume_choice(api, app_id, base["id"]).status_code == 200
    use(monkeypatch, Canned("Front Desk\nHandled patient intake for 3 doctors."))
    g = generate(api, app_id).json()
    assert g["base_label"] == "base.txt"
    assert {(x["op"], x["line"]) for x in g["diff"]} == {
        (" ", "Front Desk"), ("-", "Answered phones."),
        ("+", "Handled patient intake for 3 doctors.")}  # fmt: skip


def test_a_document_whose_facts_changed_cannot_be_accepted(api, receiver, monkeypatch):
    app_id = ready(api, receiver)
    use(monkeypatch, Canned("Handled patient intake for 3 doctors."))
    g = generate(api, app_id).json()
    job = api.get("/profile/employment").json()[0]
    body = {k: job[k] for k in ("employer", "title")} | {"description": "Answered phones."}
    assert api.put(f"/profile/employment/{job['id']}", json=body).status_code == 200
    r = api.post(f"/applications/{app_id}/generated-documents/{g['id']}/accept")
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: document_facts_changed)")
    assert stored(g["id"]).accepted_at is None
