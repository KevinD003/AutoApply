"""Phase B workflow against local fixture forms (fictional employers, synthetic candidate).

profile -> questions -> deterministic resolution -> missing-answer checkpoint -> user
correction -> package review -> approval -> invalidation on change.
"""

import pytest

from app.modules.preparation import drafting
from app.modules.preparation.drafting import DraftResult

PDF = b"%PDF-1.4\n% synthetic resume\n"


def setup_candidate(api, *, with_auth=True):
    api.put(
        "/profile",
        json={
            "full_name": "Sam Synthetic",
            "given_name": "Sam",
            "family_name": "Synthetic",
            "contact_email": "sam.synthetic@example.com",
            "phone": "+1 555 0100",
            "residence_country": "US",
            "residence_city": "Springfield",
            "links": ["https://www.linkedin.com/in/sam-synthetic"],
            "summary": "Clinic assistant with patient intake experience.",
        },
    )
    if with_auth:
        api.post(
            "/profile/work-authorizations",
            json={
                "country_code": "US",
                "authorized": "yes",
                "sponsorship_needed_now": "no",
                "sponsorship_needed_future": "no",
            },
        )
    api.put("/profile/preferences", json={"willing_to_relocate": "no"})
    api.post(
        "/profile/employment",
        json={
            "employer": "Synthetic Care",
            "title": "Front Desk",
            "description": "Handled patient intake for 3 doctors.",
        },
    )
    return api.post("/documents", files={"file": ("resume.pdf", PDF, "application/pdf")}).json()


def new_application(api, fixture="basic", title="Clinic Assistant", employer="Example Health"):
    job = api.post("/jobs", json={"title": title, "employer": employer}).json()["job"]
    assert api.post(f"/jobs/{job['id']}/form", json={"fixture": fixture}).status_code == 201
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    return job, app


def answers(view):
    return {a["key"]: a for a in view["package"]["content"]["answers"]}


@pytest.fixture
def no_llm(monkeypatch):
    """Spy provider: fails the test if anything calls it."""
    calls = []

    class Spy:
        name = "spy"

        def draft(self, req):
            calls.append(req)
            raise AssertionError("LLM must not be called")

    monkeypatch.setattr(drafting, "get_provider", lambda: Spy())
    return calls


def test_full_workflow_with_zero_llm_calls(api, no_llm):
    setup_candidate(api)
    job, app = new_application(api)
    view = api.get(f"/applications/{app['id']}/package").json()
    a = answers(view)

    # Standard questions resolved from verified facts.
    assert a["first_name"]["display"] == "Sam" and a["first_name"]["source"] == "profile_fact"
    assert a["country"]["display"] == "United States"
    assert a["country"]["source"] == "deterministic_mapping"
    assert a["work_auth_us"]["display"] == "Yes"
    assert a["sponsorship_us"]["display"] == "No"
    assert a["relocate"]["display"] == "No"
    assert a["linkedin"]["source"] == "profile_fact"
    assert a["resume"]["source"] == "document"
    # Checkpoints: no fact for these, and the acknowledgment is never auto-checked.
    assert a["hear_about"]["status"] == "needs_user"
    assert a["privacy_ack"]["status"] == "needs_consent"
    assert a["gender"]["status"] == "blank_optional" and a["gender"]["sensitive"]
    assert a["why_us"]["status"] == "blank_optional" and a["why_us"]["draftable"]
    assert view["state"] == "needs_user_action"
    assert set(view["package"]["content"]["unresolved"]) == {"hear_about", "privacy_ack"}

    # Approval is refused while required questions are open.
    pkg = view["package"]
    r = api.post(
        f"/applications/{app['id']}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    )
    assert r.status_code == 409

    # User corrections.
    v = api.put(
        f"/applications/{app['id']}/answers/hear_about",
        json={"value": {"label": "Referral"}, "save_to_bank": True},
    ).json()
    assert answers(v)["hear_about"]["source"] == "user_entered"
    v = api.put(f"/applications/{app['id']}/consents/privacy_ack", json={"choice": "agree"}).json()
    assert answers(v)["privacy_ack"]["value"] == {"checked": True}
    assert v["state"] == "awaiting_approval"
    assert v["package"]["content"]["unresolved"] == []

    pkg = v["package"]
    v = api.post(
        f"/applications/{app['id']}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    ).json()
    assert v["approval"]["status"] == "approved"
    # Approved, but this job has no captured destination, so execution is refused rather than
    # queued into something that can never run (Phase C supports only local fixtures).
    q = api.post(f"/applications/{app['id']}/transition", json={"to": "queued"})
    assert q.status_code == 409 and "no captured destination" in q.json()["detail"]
    assert api.get(f"/applications/{app['id']}").json()["state"] == "awaiting_approval"
    assert no_llm == []


def test_protected_fact_change_invalidates_approval(api):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    api.put(f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Job board"}})
    v = api.put(f"/applications/{aid}/consents/privacy_ack", json={"choice": "agree"}).json()
    pkg = v["package"]
    api.post(
        f"/applications/{aid}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    )
    api.post(f"/applications/{aid}/transition", json={"to": "queued"})

    # Change a protected fact the package relies on.
    wa = api.get("/profile/work-authorizations").json()[0]
    api.put(
        f"/profile/work-authorizations/{wa['id']}",
        json={
            "country_code": "US",
            "authorized": "yes",
            "sponsorship_needed_now": "no",
            "sponsorship_needed_future": "yes",
        },
    )
    v = api.get(f"/applications/{aid}/package").json()
    assert v["package"]["version"] == pkg["version"] + 1
    assert answers(v)["sponsorship_us"]["display"] == "Yes"
    assert v["approval"]["status"] == "invalidated"
    assert "sponsorship_us" in v["approval"]["reason"]
    assert "work_auth_us" not in v["approval"]["reason"]  # its fact value did not change
    assert v["state"] == "awaiting_approval"  # pulled back out of the queue
    # The old hash can no longer be approved.
    r = api.post(
        f"/applications/{aid}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    )
    assert r.status_code == 409
    assert api.post(f"/applications/{aid}/transition", json={"to": "queued"}).status_code == 409


@pytest.mark.parametrize("change", ["document", "consent", "destination", "answer"])
def test_other_material_changes_invalidate_approval(api, change):
    setup_candidate(api)
    job, app = new_application(api)
    aid = app["id"]
    api.put(f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Job board"}})
    v = api.put(f"/applications/{aid}/consents/privacy_ack", json={"choice": "agree"}).json()
    pkg = v["package"]
    api.post(
        f"/applications/{aid}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    )
    if change == "document":
        resume = api.get("/documents").json()[0]
        api.post(
            "/documents",
            files={"file": ("resume2.pdf", PDF + b"v2", "application/pdf")},
            data={"lineage_id": resume["lineage_id"]},
        )
    elif change == "consent":
        api.put(f"/applications/{aid}/consents/gender", json={"choice": "withhold"})
    elif change == "destination":
        api.patch(f"/jobs/{job['id']}", json={"title": "Senior Clinic Assistant"})
    else:
        api.put(f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Referral"}})
    v = api.get(f"/applications/{aid}/package").json()
    assert v["approval"]["status"] == "invalidated", change


def test_unrelated_fact_change_keeps_approval(api):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    api.put(f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Job board"}})
    v = api.put(f"/applications/{aid}/consents/privacy_ack", json={"choice": "agree"}).json()
    pkg = v["package"]
    api.post(
        f"/applications/{aid}/package/approve",
        json={"version": pkg["version"], "content_hash": pkg["content_hash"]},
    )
    api.post("/profile/education", json={"institution": "Synthetic College"})
    # Editing an unrelated field on the same profile record does not invalidate either.
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
    api.put("/profile", json=keep | {"summary": "Updated summary text."})
    v = api.get(f"/applications/{aid}/package").json()
    assert v["approval"]["status"] == "approved"
    assert v["package"]["version"] == pkg["version"]


def test_missing_fact_parks_application_and_profile_fix_resolves(api):
    setup_candidate(api, with_auth=False)
    _, app = new_application(api)
    v = api.get(f"/applications/{app['id']}/package").json()
    a = answers(v)
    assert a["work_auth_us"]["status"] == "needs_user"
    assert "Work authorization" in a["work_auth_us"]["explanation"]
    # Protected facts are fixed in the profile, not per application.
    r = api.put(f"/applications/{app['id']}/answers/work_auth_us", json={"value": {"label": "Yes"}})
    assert r.status_code == 400
    api.post(
        "/profile/work-authorizations",
        json={
            "country_code": "US",
            "authorized": "no",
            "sponsorship_needed_now": "yes",
            "sponsorship_needed_future": "yes",
        },
    )
    a = answers(api.get(f"/applications/{app['id']}/package").json())
    assert a["work_auth_us"]["display"] == "No"
    assert a["sponsorship_us"]["display"] == "Yes"


def test_answer_bank_reuse_across_jobs_and_wording_changes(api):
    setup_candidate(api)
    _, app1 = new_application(api)
    api.put(
        f"/applications/{app1['id']}/answers/hear_about",
        json={"value": {"label": "Company website"}, "save_to_bank": True},
    )
    bank = api.get("/answer-bank").json()
    assert len(bank) == 1 and bank[0]["value"] == {"labels": ["Company website"]}

    _, app2 = new_application(api, title="Receptionist", employer="Other Clinic")
    a = answers(api.get(f"/applications/{app2['id']}/package").json())
    assert (a["hear_about"]["source"], a["hear_about"]["display"]) == (
        "answer_bank",
        "Company website",
    )

    # Same employer form, reworded question -> no reuse.
    job3 = api.post("/jobs", json={"title": "Aide", "employer": "Third Clinic"}).json()["job"]
    html = (
        __import__("app.modules.preparation.fixtures_registry", fromlist=["x"])
        .fixture_html("basic")
        .replace(
            "How did you hear about this job?", "Where did you first learn about this opening?"
        )
    )
    api.post(f"/jobs/{job3['id']}/form", json={"html": html})
    app3 = api.post("/applications", json={"job_id": job3["id"]}).json()
    a = answers(api.get(f"/applications/{app3['id']}/package").json())
    assert a["hear_about"]["status"] == "needs_user"

    # Options changed -> explicit checkpoint, not a silent mapping.
    job4 = api.post("/jobs", json={"title": "Aide", "employer": "Fourth Clinic"}).json()["job"]
    html4 = (
        __import__("app.modules.preparation.fixtures_registry", fromlist=["x"])
        .fixture_html("basic")
        .replace(
            '<option value="other">Other</option>\n    </select>\n    <label for="why_us">',
            '<option value="other">Other</option>\n      <option value="fair">Career fair</option>'
            '\n    </select>\n    <label for="why_us">',
        )
    )
    api.post(f"/jobs/{job4['id']}/form", json={"html": html4})
    app4 = api.post("/applications", json={"job_id": job4["id"]}).json()
    a = answers(api.get(f"/applications/{app4['id']}/package").json())
    assert a["hear_about"]["status"] == "needs_user"
    assert "options have changed" in a["hear_about"]["explanation"]


def test_form_option_change_invalidates_saved_choice(api):
    setup_candidate(api)
    job, app = new_application(api)
    api.put(f"/applications/{app['id']}/answers/hear_about", json={"value": {"label": "Referral"}})
    html = (
        __import__("app.modules.preparation.fixtures_registry", fromlist=["x"])
        .fixture_html("basic")
        .replace(
            '<option value="referral">Referral</option>',
            '<option value="employee">Employee referral</option>',
        )
    )
    r = api.post(f"/jobs/{job['id']}/form", json={"html": html})
    assert r.json()["version"] == 2
    a = answers(api.get(f"/applications/{app['id']}/package").json())
    assert a["hear_about"]["status"] == "needs_user"
    assert "no longer" in a["hear_about"]["explanation"]


def test_job_specific_answers_cannot_go_to_bank(api):
    setup_candidate(api)
    _, app = new_application(api, fixture="tricky")
    r = api.put(
        f"/applications/{app['id']}/answers/eligible_here",
        json={"value": {"label": "Yes"}, "save_to_bank": True},
    )
    assert r.status_code == 400
    r = api.put(
        f"/applications/{app['id']}/answers/eligible_here", json={"value": {"label": "Yes"}}
    )
    assert answers(r.json())["eligible_here"]["source"] == "user_entered"


def test_input_validation(api):
    setup_candidate(api)
    _, app = new_application(api, fixture="tricky")
    aid = app["id"]
    assert (
        api.put(
            f"/applications/{aid}/answers/years", json={"value": {"number": "lots"}}
        ).status_code
        == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers/start_date", json={"value": {"date": "next week"}}
        ).status_code
        == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers/shifts", json={"value": {"labels": ["Day", "Weekend"]}}
        ).status_code
        == 400
    )
    v = api.put(
        f"/applications/{aid}/answers/shifts", json={"value": {"labels": ["Day", "Night"]}}
    ).json()
    assert answers(v)["shifts"]["display"] == "Day, Night"
    assert (
        api.put(f"/applications/{aid}/consents/years", json={"choice": "agree"}).status_code == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers/background_check", json={"value": {"label": "Yes"}}
        ).status_code
        == 400
    )


def test_drafting_unavailable_without_provider(api):
    setup_candidate(api)
    _, app = new_application(api)
    v = api.get(f"/applications/{app['id']}/package").json()
    assert v["drafting_available"] is False
    r = api.post(f"/applications/{app['id']}/answers/why_us/draft")
    assert r.status_code == 503
    # Manual answer still works.
    v = api.put(
        f"/applications/{app['id']}/answers/why_us",
        json={"value": {"text": "I value careful patient intake."}},
    ).json()
    assert answers(v)["why_us"]["source"] == "user_entered"


class FakeProvider:
    """TEST DOUBLE — not an AI integration. Returns canned text to exercise validation."""

    name = "test-fake"

    def __init__(self, text, evidence=None):
        self.text, self.evidence, self.calls = text, evidence, 0

    def draft(self, req):
        self.calls += 1
        ev = self.evidence if self.evidence is not None else [req.facts[0].id]
        return DraftResult(text=self.text, evidence=ev, provider=self.name)


def test_fake_provider_draft_is_validated_and_needs_acceptance(api, monkeypatch):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    invented = FakeProvider("I led a team of 40 nurses for 12 years.")
    monkeypatch.setattr(drafting, "get_provider", lambda: invented)
    r = api.post(f"/applications/{aid}/answers/why_us/draft")
    assert r.status_code == 422 and "numbers not found" in r.json()["detail"]

    bad_cite = FakeProvider("I enjoy patient intake.", evidence=["made-up-id"])
    monkeypatch.setattr(drafting, "get_provider", lambda: bad_cite)
    assert api.post(f"/applications/{aid}/answers/why_us/draft").status_code == 422

    good = FakeProvider("I handled patient intake for 3 doctors and want to keep doing it well.")
    monkeypatch.setattr(drafting, "get_provider", lambda: good)
    d = api.post(f"/applications/{aid}/answers/why_us/draft").json()
    assert d["provider"] == "test-fake"
    # Not used until accepted.
    a = answers(api.get(f"/applications/{aid}/package").json())
    assert a["why_us"]["status"] == "blank_optional"
    # Same inputs -> cached, no second provider call.
    api.post(f"/applications/{aid}/answers/why_us/draft")
    assert good.calls == 1
    v = api.post(f"/applications/{aid}/drafts/{d['id']}/accept").json()
    assert answers(v)["why_us"]["source"] == "draft"


def test_tenant_isolation_for_preparation(api, other_api):
    setup_candidate(api)
    job, app = new_application(api)
    aid = app["id"]
    other_doc = other_api.post(
        "/documents", files={"file": ("x.pdf", PDF, "application/pdf")}
    ).json()
    assert other_api.get(f"/applications/{aid}/package").status_code == 404
    assert (
        other_api.put(
            f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Referral"}}
        ).status_code
        == 404
    )
    assert (
        other_api.put(
            f"/applications/{aid}/consents/privacy_ack", json={"choice": "agree"}
        ).status_code
        == 404
    )
    assert (
        other_api.post(
            f"/applications/{aid}/package/approve", json={"version": 1, "content_hash": "0" * 64}
        ).status_code
        == 404
    )
    assert other_api.get(f"/jobs/{job['id']}/form").status_code == 404
    assert other_api.post(f"/jobs/{job['id']}/form", json={"fixture": "basic"}).status_code == 404
    # Owner cannot attach someone else's document either.
    r = api.put(f"/applications/{aid}/documents", json={"resume_document_id": other_doc["id"]})
    assert r.status_code == 404
    # Answer bank is per user.
    api.put(
        f"/applications/{aid}/answers/hear_about",
        json={"value": {"label": "Referral"}, "save_to_bank": True},
    )
    assert other_api.get("/answer-bank").json() == []
    entry = api.get("/answer-bank").json()[0]
    assert other_api.delete(f"/answer-bank/{entry['id']}").status_code == 404


def test_package_versions_are_immutable(api):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    v1 = api.get(f"/applications/{aid}/package").json()["package"]
    v2 = api.put(
        f"/applications/{aid}/answers/hear_about", json={"value": {"label": "Referral"}}
    ).json()["package"]
    assert v2["version"] == v1["version"] + 1
    from app.core.db import SessionLocal
    from app.modules.preparation.models import ApplicationPackage

    with SessionLocal() as db:
        rows = (
            db.query(ApplicationPackage)
            .filter_by(application_id=aid)
            .order_by(ApplicationPackage.version)
            .all()
        )
        assert rows[0].content_hash == v1["content_hash"]
        assert (
            answers({"package": {"content": rows[0].content}})["hear_about"]["status"]
            == "needs_user"
        )


def test_attaching_unreadable_html_is_rejected(api):
    job = api.post("/jobs", json={"title": "X", "employer": "Y"}).json()["job"]
    r = api.post(f"/jobs/{job['id']}/form", json={"html": "<p>no form here</p>"})
    assert r.status_code == 400
    assert api.post(f"/jobs/{job['id']}/form", json={"fixture": "nope"}).status_code == 400
