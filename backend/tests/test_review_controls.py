"""C12 (D64): what the review page may offer for each question (change, answer an optional
question, clear an answer given here, the cover letter to send, where the form sends), outside
the package content. The Greenhouse-like fixture form; synthetic data only."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.preparation import greenhouse as gh
from tests.execution_harness import Receiver
from tests.test_greenhouse_adapter import gh_application

PDF = b"%PDF-1.4\n% synthetic cover letter for review tests\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def view(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()


def rows(v) -> dict:
    return {a["key"]: a for a in v["package"]["content"]["answers"]}


def events(api, action) -> list[dict]:
    """The user's audit rows of one action, oldest first (entity ids are keyed references)."""
    uid = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.user_id == uid, AuditEvent.action == action)
        return [e.meta for e in db.scalars(q.order_by(AuditEvent.created_at))]


def test_each_question_says_what_the_page_may_offer(api, receiver):
    app_id = gh_application(api, approve=False)
    v = view(api, app_id)
    rc = v["review"]
    assert set(rc) == set(rows(v))  # one entry per question, outside the content
    assert "review" not in v["package"]["content"]
    # An answer given for this application: change it or clear it.
    assert rc["question_7004"] == {"answer_here": True, "clear": True, "document_role": None,
                                   "not_asked": False}  # fmt: skip
    # A conditional question that is not asked for the answers given: nothing to offer.
    assert rc["question_7006"]["not_asked"] and not rc["question_7006"]["answer_here"]
    # Documents, acknowledgments and facts that belong in the profile are not answered here.
    assert rc["resume"]["document_role"] == "resume" and not rc["resume"]["answer_here"]
    assert rc["cover_letter"]["document_role"] == "cover_letter"
    assert not rc[gh.CONSENT_KEY]["answer_here"]
    assert not rc["question_7002"]["answer_here"]  # work authorization: the profile's
    assert rc["first_name"]["clear"] is False


def test_the_page_controls_never_change_the_package(api, receiver):
    app_id = gh_application(api, approve=False)
    before = view(api, app_id)["package"]
    again = view(api, app_id)["package"]
    assert (again["version"], again["content_hash"]) == (before["version"], before["content_hash"])
    assert set(before["content"]) == {
        "schema", "owner", "policy", "destination", "documents", "answers", "consents",
        "unresolved", "validation_errors",
    }  # fmt: skip


def test_clearing_an_answer_removes_it_and_is_audited_without_its_key(api, receiver):
    app_id = gh_application(api, approve=False)
    r = api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_7004"})
    assert r.status_code == 200, r.text
    row = rows(r.json())["question_7004"]
    assert (row["status"], row["value"]) == ("needs_user", None)
    assert r.json()["review"]["question_7004"]["clear"] is False
    (detail,) = events(api, "application.answer_cleared")
    assert set(detail) == {"field_ref"} and "question_7004" not in str(detail)
    # Clearing what was never answered changes nothing and records nothing.
    api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_7004"})
    assert len(events(api, "application.answer_cleared")) == 1


def test_an_optional_cover_letter_is_chosen_and_left_out_again(api, receiver):
    app_id = gh_application(api, approve=False)
    assert not [d for d in view(api, app_id)["package"]["content"]["documents"]
                if d["field"] == "cover_letter"]  # fmt: skip
    doc = api.post("/documents", files={"file": ("letter.pdf", PDF, "application/pdf")},
                   data={"kind": "cover_letter"}).json()  # fmt: skip
    r = api.put(f"/applications/{app_id}/documents", json={"cover_letter_document_id": doc["id"]})
    assert r.status_code == 200, r.text
    sent = {d["field"]: d["document_id"] for d in r.json()["package"]["content"]["documents"]}
    assert sent["cover_letter"] == doc["id"]
    r = api.put(f"/applications/{app_id}/documents", json={"clear": ["cover_letter"]})
    assert r.status_code == 200, r.text
    assert "cover_letter" not in {d["field"] for d in r.json()["package"]["content"]["documents"]}
    got = events(api, "application.document")
    assert got == [{"change": "chosen", "role": "cover_letter"},
                   {"change": "cleared", "role": "cover_letter"}]  # fmt: skip
    # A resume is not a cover letter.
    resume = next(d for d in api.get("/documents").json() if d["kind"] == "resume")
    r = api.put(
        f"/applications/{app_id}/documents", json={"cover_letter_document_id": resume["id"]}
    )
    assert r.status_code == 400


def test_another_users_application_cannot_be_cleared_or_changed(api, other_api, receiver):
    app_id = gh_application(api, approve=False)
    r = other_api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_7004"})
    assert r.status_code == 404
    r = other_api.put(f"/applications/{app_id}/documents", json={"clear": ["cover_letter"]})
    assert r.status_code == 404
    assert rows(view(api, app_id))["question_7004"]["status"] == "resolved"


def test_the_page_says_where_the_form_sends(api, receiver):
    v = view(api, gh_application(api, approve=False))
    dest = v["package"]["content"]["destination"]
    assert dest["submit_url"].startswith(dest["origin"])
    assert v["labels"]["destination"].startswith("Local test fixture")
    from app.modules.providers import wording

    assert (
        wording.destination_label("https://job-boards.greenhouse.io") == "The employer's own site"
    )
    assert wording.destination_label(None) is None
