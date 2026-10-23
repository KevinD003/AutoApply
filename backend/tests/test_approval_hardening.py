"""Approval integrity: manifest contents, expiry, monotonic revocation, value distinctions,
draft dependencies and deterministic interleavings with concurrent edits."""

import threading
import uuid
from datetime import timedelta

import pytest

from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.preparation import drafting
from app.modules.preparation import package as pk
from app.modules.preparation.drafting import DraftResult
from app.modules.preparation.forms import FieldType, FormField
from app.modules.preparation.models import PackageApproval
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.profiles.models import WorkAuthorization
from tests.test_preparation import answers, new_application, setup_candidate


def ready_app(api):
    setup_candidate(api)
    job, app = new_application(api)
    aid = app["id"]
    api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Job board"}}
    )
    v = api.put(
        f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
    return job, aid, v


def approve(api, aid, v):
    p = v["package"]
    return api.post(
        f"/applications/{aid}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def test_manifest_binds_owner_destination_documents_and_policy(api):
    _, aid, v = ready_app(api)
    c = v["package"]["content"]
    me = api.get("/auth/me").json()
    assert c["owner"] == {"user_id": me["user_id"], "application_id": aid}
    assert c["policy"]["package_schema"] == pk.SCHEMA_VERSION
    assert c["destination"]["form_fingerprint"]
    doc = c["documents"][0]
    assert len(doc["sha256"]) == 64 and doc["size_bytes"] > 0 and doc["version"] == 1
    # Real option values and labels, wording and help text are all in the manifest.
    a = answers(v)
    assert a["sponsorship_us"]["help_text"] == "Answer for the United States."
    assert {"value": "yes", "label": "Yes"} in a["sponsorship_us"]["options"]


def test_client_hash_alone_cannot_approve(api):
    _, aid, v = ready_app(api)
    r = api.post(
        f"/applications/{aid}/package/approve",
        json={"version": v["package"]["version"], "content_hash": "f" * 64},
    )
    assert r.status_code == 409
    assert api.get(f"/applications/{aid}/package").json()["approval"]["status"] == "not_approved"


def test_approval_expires(api):
    _, aid, v = ready_app(api)
    approve(api, aid, v)
    with SessionLocal() as db:
        for a in db.query(PackageApproval).filter_by(application_id=uuid.UUID(aid)):
            a.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert api.get(f"/applications/{aid}/package").json()["approval"]["status"] != "approved"
    assert api.post(f"/applications/{aid}/transition", json={"to": "queued"}).status_code == 409


def test_restoring_a_fact_does_not_resurrect_a_revoked_approval(api):
    _, aid, v = ready_app(api)
    approve(api, aid, v)
    original_hash = v["package"]["content_hash"]
    wa = api.get("/profile/work-authorizations").json()[0]
    body = {
        k: wa[k]
        for k in (
            "country_code",
            "authorized",
            "sponsorship_needed_now",
            "sponsorship_needed_future",
        )
    }
    api.put(
        f"/profile/work-authorizations/{wa['id']}", json=body | {"sponsorship_needed_future": "yes"}
    )
    assert api.get(f"/applications/{aid}/package").json()["approval"]["status"] == "invalidated"
    api.put(f"/profile/work-authorizations/{wa['id']}", json=body)  # restore
    v2 = api.get(f"/applications/{aid}/package").json()
    assert v2["package"]["content_hash"] == original_hash  # same content again...
    assert v2["package"]["version"] == v["package"]["version"] + 2  # ...as a new version
    assert v2["approval"]["status"] == "invalidated"  # history is monotonic
    with SessionLocal() as db:
        assert all(
            a.invalidated_at is not None
            for a in db.query(PackageApproval).filter_by(application_id=uuid.UUID(aid))
        )


def test_false_null_and_decline_are_distinct():
    box = FormField(key="ack", label="I agree to the terms of use", type=FieldType.checkbox)
    unanswered = resolve_field(box, Context())
    declined = resolve_field(box, Context(consents={"ack": "decline"}))
    agreed = resolve_field(box, Context(consents={"ack": "agree"}))
    assert (unanswered.status, unanswered.value) == ("needs_consent", None)
    assert (declined.status, declined.value) == ("resolved", {"checked": False})
    assert agreed.value == {"checked": True}
    blank = resolve_field(FormField(key="t", label="Nickname", type=FieldType.text), Context())
    assert (blank.status, blank.value) == ("blank_optional", None)
    hashes = {
        pk.content_hash({"answers": [{"value": x.value, "fact_refs": []}]})
        for x in (unanswered, declined, agreed)
    }
    assert len(hashes) == 3


def test_empty_text_is_rejected_not_stored_as_answer(api):
    _, aid, _ = ready_app(api)
    r = api.put(f"/applications/{aid}/answers", json={"key": "why_us", "value": {"text": "   "}})
    assert r.status_code == 400


class _Fake:
    name = "test-fake"

    def draft(self, req):
        return DraftResult(
            text="I value careful patient intake.",
            provider=self.name,
            evidence=[f.id for f in req.facts if f.kind == "summary"],
        )


def test_accepted_draft_depends_on_its_facts(api, monkeypatch):
    monkeypatch.setattr(drafting, "get_provider", lambda: _Fake())
    _, aid, _ = ready_app(api)
    d = api.post(f"/applications/{aid}/drafts", json={"key": "why_us"}).json()
    v = api.post(f"/applications/{aid}/drafts/{d['id']}/accept").json()
    assert answers(v)["why_us"]["source"] == "draft"
    approve(api, aid, v)
    # Editing the summary the draft relied on makes the draft stale and invalidates approval.
    prof = api.get("/profile").json()
    keep = {
        k: prof[k]
        for k in (
            "full_name",
            "given_name",
            "family_name",
            "contact_email",
            "phone",
            "residence_country",
            "residence_city",
            "links",
        )
    }
    api.put("/profile", json=keep | {"summary": "Different summary now."})
    v = api.get(f"/applications/{aid}/package").json()
    # A checkpoint although optional (test_sending.py): nothing stale can be approved or sent.
    assert answers(v)["why_us"]["status"] == "needs_user"
    assert "why_us" in v["package"]["content"]["unresolved"]
    assert "changed" in answers(v)["why_us"]["explanation"]
    assert v["approval"]["status"] == "invalidated"


def test_edit_committed_between_review_and_approve_blocks_approval(api):
    """Deterministic interleaving: A builds the package, B edits a protected fact and commits,
    then A tries to approve what it saw. The server rebuilds and refuses."""
    _, aid, v = ready_app(api)
    seen = v["package"]
    with SessionLocal() as a, SessionLocal() as b:
        app_a = a.get(Application, uuid.UUID(aid))
        wa = b.query(WorkAuthorization).first()
        wa.sponsorship_needed_now = "yes"
        wa.version += 1
        b.commit()
        with pytest.raises(pk.ApprovalError):
            pk.approve(a, app_a, seen["version"], seen["content_hash"])
        a.commit()
    assert api.get(f"/applications/{aid}/package").json()["approval"]["status"] == "not_approved"


def test_edit_committed_after_approval_invalidates_before_queue(api):
    _, aid, v = ready_app(api)
    approve(api, aid, v)
    with SessionLocal() as b:
        wa = b.query(WorkAuthorization).first()
        wa.sponsorship_needed_now = "yes"
        wa.version += 1
        b.commit()
    # No GET in between: the queue gate itself rebuilds and refuses.
    assert api.post(f"/applications/{aid}/transition", json={"to": "queued"}).status_code == 409


def test_concurrent_rebuilds_write_one_version(api):
    _, aid, v = ready_app(api)
    with SessionLocal() as db:
        wa = db.query(WorkAuthorization).first()
        wa.sponsorship_needed_future = "yes"
        db.commit()
    codes, versions = [], []
    start = threading.Barrier(6)

    def go():
        start.wait()
        r = api.get(f"/applications/{aid}/package")
        codes.append(r.status_code)
        versions.append(r.json()["package"]["version"])

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes == [200] * 6
    assert set(versions) == {v["package"]["version"] + 1}
