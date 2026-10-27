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
    assert not a["relocate"]["bankable"]  # C6: from Preferences, never from a saved answer
    assert a["linkedin"]["source"] == "profile_fact"
    assert a["resume"]["source"] == "document"
    # Checkpoints: no fact for these, and the acknowledgment is never auto-checked.
    assert a["hear_about"]["status"] == "needs_user"
    assert not a["hear_about"]["bankable"]  # C6: about the employer or the job (D51)
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

    # User corrections. How you heard about this job is never saved for reuse (D51): the
    # request is refused and stores nothing; the same answer for this application is saved.
    r = api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "hear_about", "value": {"label": "Referral"}, "save_to_bank": True},
    )
    assert r.status_code == 400 and "about the employer or the job" in r.json()["detail"]
    assert api.get("/answer-bank").json() == []
    v = api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "hear_about", "value": {"label": "Referral"}},
    ).json()
    assert answers(v)["hear_about"]["source"] == "user_entered"
    v = api.put(
        f"/applications/{app['id']}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
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
    api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Job board"}}
    )
    v = api.put(
        f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
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
    api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Job board"}}
    )
    v = api.put(
        f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
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
        api.put(f"/applications/{aid}/consents", json={"key": "gender", "choice": "withhold"})
    elif change == "destination":
        api.patch(f"/jobs/{job['id']}", json={"title": "Senior Clinic Assistant"})
    else:
        api.put(
            f"/applications/{aid}/answers",
            json={"key": "hear_about", "value": {"label": "Referral"}},
        )
    v = api.get(f"/applications/{aid}/package").json()
    assert v["approval"]["status"] == "invalidated", change


def test_unrelated_fact_change_keeps_approval(api):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Job board"}}
    )
    v = api.put(
        f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
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
    r = api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "work_auth_us", "value": {"label": "Yes"}},
    )
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
    """A saved answer is reused for the same wording, help text and options on another job, and
    for nothing else (D51). The question is tricky.html's "Highest level of education completed"
    (with help text): how you heard about a job is never saved for reuse."""
    setup_candidate(api)
    _, app1 = new_application(api, fixture="tricky")
    r = api.put(
        f"/applications/{app1['id']}/answers",
        json={"key": "education", "value": {"label": "Bachelor's degree"}, "save_to_bank": True},
    )
    assert r.status_code == 200, r.text
    bank = api.get("/answer-bank").json()
    assert len(bank) == 1 and bank[0]["value"] == {"labels": ["Bachelor's degree"]}
    assert bank[0]["help_text"] == "Choose the highest level you have finished."

    _, app2 = new_application(api, fixture="tricky", title="Dispatcher", employer="Other Logistics")
    a = answers(api.get(f"/applications/{app2['id']}/package").json())
    assert (a["education"]["source"], a["education"]["display"]) == (
        "answer_bank",
        "Bachelor's degree",
    )

    from app.modules.preparation.fixtures_registry import fixture_html

    tricky = fixture_html("tricky")

    def education_on(html, employer):
        job = api.post("/jobs", json={"title": "Dispatcher", "employer": employer}).json()["job"]
        assert api.post(f"/jobs/{job['id']}/form", json={"html": html}).status_code == 201
        app = api.post("/applications", json={"job_id": job["id"]}).json()
        return answers(api.get(f"/applications/{app['id']}/package").json())["education"]

    # Reworded question -> no reuse.
    a = education_on(
        tricky.replace(
            "Highest level of education completed",
            "What is the highest level of education you have completed?",
        ),
        "Third Logistics",
    )
    assert (a["status"], a["source"]) == ("needs_user", "unresolved")

    # Options changed -> explicit checkpoint, not a silent mapping.
    a = education_on(
        tricky.replace(
            '<option value="other">Other</option>\n    </select>\n    <p id="education_help">',
            '<option value="other">Other</option>\n      <option value="phd">Doctorate</option>'
            '\n    </select>\n    <p id="education_help">',
        ),
        "Fourth Logistics",
    )
    assert a["status"] == "needs_user"
    assert "options have changed" in a["explanation"]

    # Other help text -> no reuse (D51).
    a = education_on(
        tricky.replace(
            "Choose the highest level you have finished.",
            "Choose the highest level you have started.",
        ),
        "Fifth Logistics",
    )
    assert (a["status"], a["source"]) == ("needs_user", "unresolved")

    # How you heard about a job is never saved for reuse; the saved answer above is untouched.
    _, basic = new_application(api, title="Clinic Assistant")
    r = api.put(
        f"/applications/{basic['id']}/answers",
        json={"key": "hear_about", "value": {"label": "Company website"}, "save_to_bank": True},
    )
    assert r.status_code == 400 and "about the employer or the job" in r.json()["detail"]
    assert api.get("/answer-bank").json() == bank


def test_form_option_change_invalidates_saved_choice(api):
    setup_candidate(api)
    job, app = new_application(api)
    api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "hear_about", "value": {"label": "Referral"}},
    )
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
        f"/applications/{app['id']}/answers",
        json={"key": "eligible_here", "value": {"label": "Yes"}, "save_to_bank": True},
    )
    assert r.status_code == 400
    r = api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "eligible_here", "value": {"label": "Yes"}},
    )
    assert answers(r.json())["eligible_here"]["source"] == "user_entered"
    # C6 (D51): relevant experience, a start date, pay and shifts are never saved for reuse
    # (setup_candidate sets no salary expectation, so the salary is the user's to answer).
    for key, value, phrase in (
        ("years", {"number": 3}, "about the employer or the job"),
        ("start_date", {"date": "2026-11-02"}, "depends on when you apply"),
        ("salary", {"number": 50000}, "Pay is never saved for reuse"),
        ("shifts", {"labels": ["Day"]}, "depends on when you apply"),
    ):
        body = {"key": key, "value": value, "save_to_bank": True}
        r = api.put(f"/applications/{app['id']}/answers", json=body)
        assert r.status_code == 400 and phrase in r.json()["detail"], (key, r.text)
        r = api.put(f"/applications/{app['id']}/answers", json=body | {"save_to_bank": False})
        assert answers(r.json())[key]["source"] == "user_entered", key
    assert api.get("/answer-bank").json() == []


def test_input_validation(api):
    setup_candidate(api)
    _, app = new_application(api, fixture="tricky")
    aid = app["id"]
    assert (
        api.put(
            f"/applications/{aid}/answers", json={"key": "years", "value": {"number": "lots"}}
        ).status_code
        == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers",
            json={"key": "start_date", "value": {"date": "next week"}},
        ).status_code
        == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers",
            json={"key": "shifts", "value": {"labels": ["Day", "Weekend"]}},
        ).status_code
        == 400
    )
    v = api.put(
        f"/applications/{aid}/answers",
        json={"key": "shifts", "value": {"labels": ["Day", "Night"]}},
    ).json()
    assert answers(v)["shifts"]["display"] == "Day, Night"
    assert (
        api.put(
            f"/applications/{aid}/consents", json={"key": "years", "choice": "agree"}
        ).status_code
        == 400
    )
    assert (
        api.put(
            f"/applications/{aid}/answers",
            json={"key": "background_check", "value": {"label": "Yes"}},
        ).status_code
        == 400
    )


def test_drafting_unavailable_without_provider(api):
    setup_candidate(api)
    _, app = new_application(api)
    v = api.get(f"/applications/{app['id']}/package").json()
    assert v["drafting_available"] is False
    r = api.post(f"/applications/{app['id']}/drafts", json={"key": "why_us"})
    assert r.status_code == 503
    # Manual answer still works.
    v = api.put(
        f"/applications/{app['id']}/answers",
        json={"key": "why_us", "value": {"text": "I value careful patient intake."}},
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
    r = api.post(f"/applications/{aid}/drafts", json={"key": "why_us"})
    assert r.status_code == 422 and "numbers not found" in r.json()["detail"]

    bad_cite = FakeProvider("I enjoy patient intake.", evidence=["made-up-id"])
    monkeypatch.setattr(drafting, "get_provider", lambda: bad_cite)
    assert api.post(f"/applications/{aid}/drafts", json={"key": "why_us"}).status_code == 422

    good = FakeProvider("I handled patient intake for 3 doctors and want to keep doing it well.")
    monkeypatch.setattr(drafting, "get_provider", lambda: good)
    d = api.post(f"/applications/{aid}/drafts", json={"key": "why_us"}).json()
    assert d["provider"] == "test-fake"
    # Not used until accepted.
    a = answers(api.get(f"/applications/{aid}/package").json())
    assert a["why_us"]["status"] == "blank_optional"
    # Same inputs -> cached, no second provider call.
    api.post(f"/applications/{aid}/drafts", json={"key": "why_us"})
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
            f"/applications/{aid}/answers",
            json={"key": "hear_about", "value": {"label": "Referral"}},
        ).status_code
        == 404
    )
    assert (
        other_api.put(
            f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"}
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
    # Answer bank is per user (a stable question: how you heard about a job is never saved).
    _, tricky = new_application(api, fixture="tricky", title="Dispatcher")
    r = api.put(
        f"/applications/{tricky['id']}/answers",
        json={"key": "education", "value": {"label": "Bachelor's degree"}, "save_to_bank": True},
    )
    assert r.status_code == 200, r.text
    assert other_api.get("/answer-bank").json() == []
    entry = api.get("/answer-bank").json()[0]
    assert other_api.delete(f"/answer-bank/{entry['id']}").status_code == 404
    assert api.get("/answer-bank").json() == [entry]  # the owner's saved answer is untouched


def test_tenant_isolation_for_revoke_documents_drafts_and_the_bank(api, other_api, monkeypatch):
    """The routes C1 found without a cross-tenant test: each is a 404 for another user (or for
    the owner with another application's draft), and nothing of the owner's changes."""
    monkeypatch.setattr(drafting, "get_provider", lambda: _CountingProvider())
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    saved = {"key": "hear_about", "value": {"label": "Referral"}}  # never saved for reuse (D51)
    assert api.put(f"/applications/{aid}/answers", json=saved).status_code == 200
    p = api.put(f"/applications/{aid}/consents",
                json={"key": "privacy_ack", "choice": "agree"}).json()["package"]  # fmt: skip
    r = api.post(f"/applications/{aid}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 200, r.text
    d = api.post(f"/applications/{aid}/drafts", json={"key": "why_us"}).json()

    other_doc = other_api.post(
        "/documents", files={"file": ("x.pdf", PDF, "application/pdf")}
    ).json()
    own_doc = api.get("/documents").json()[0]
    _, other_app = new_application(other_api, title="Their own role")
    _, second = new_application(api, title="Second role")
    _, saved_from = new_application(api, fixture="tricky", title="Dispatcher")
    edu = {"key": "education", "value": {"label": "Bachelor's degree"}, "save_to_bank": True}
    assert api.put(f"/applications/{saved_from['id']}/answers", json=edu).status_code == 200

    assert other_api.post(f"/applications/{aid}/package/revoke").status_code == 404
    for body in ({"resume_document_id": other_doc["id"]}, {"resume_document_id": own_doc["id"]}):
        assert other_api.put(f"/applications/{aid}/documents", json=body).status_code == 404
    assert other_api.post(f"/applications/{aid}/drafts/{d['id']}/accept").status_code == 404
    accept_elsewhere = f"/applications/{other_app['id']}/drafts/{d['id']}/accept"
    assert other_api.post(accept_elsewhere).status_code == 404
    # The owner cannot use one application's draft in another application either.
    assert api.post(f"/applications/{second['id']}/drafts/{d['id']}/accept").status_code == 404
    assert [x["id"] for x in other_api.get("/documents").json()] == [other_doc["id"]]
    assert other_api.get(f"/documents/{own_doc['id']}/versions").status_code == 404

    view = api.get(f"/applications/{aid}/package").json()
    assert view["approval"]["status"] == "approved"  # still live: nothing changed
    assert answers(view)["why_us"]["source"] == "unresolved"  # the draft was never accepted
    assert view["package"]["content"]["documents"][0]["document_id"] == own_doc["id"]
    second_view = api.get(f"/applications/{second['id']}/package").json()
    assert answers(second_view)["why_us"]["status"] == "blank_optional"
    # Another user with the same question never resolves it from the owner's saved answer.
    setup_candidate(other_api)
    assert len(api.get("/answer-bank").json()) == 1 and other_api.get("/answer-bank").json() == []
    other_view = other_api.get(f"/applications/{other_app['id']}/package").json()
    assert answers(other_view)["hear_about"]["status"] == "needs_user"
    assert answers(other_view)["hear_about"]["source"] == "unresolved"
    _, their_tricky = new_application(other_api, fixture="tricky", title="Their dispatcher")
    theirs = answers(other_api.get(f"/applications/{their_tricky['id']}/package").json())
    assert (theirs["education"]["status"], theirs["education"]["source"]) == (
        "needs_user",
        "unresolved",
    )


class _CountingProvider:
    name = "test-fake"

    def draft(self, req):
        return DraftResult(text="I value careful patient intake.", provider=self.name,
                           evidence=[f.id for f in req.facts if f.kind == "summary"])  # fmt: skip


def test_package_versions_are_immutable(api):
    setup_candidate(api)
    _, app = new_application(api)
    aid = app["id"]
    v1 = api.get(f"/applications/{aid}/package").json()["package"]
    v2 = api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Referral"}}
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
