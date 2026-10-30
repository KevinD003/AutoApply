"""The Lever-style adapter (`fixture_lever`, D85) against the labelled local approximation
(fixtures/ats_receiver/lever_like.py). The receiver's ledger is the oracle: what it accepted,
and every disclosure it saw. Passing these tests shows compatibility with that fixture only,
never with a real Lever posting, which stays a manual handoff. Synthetic data only."""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.urlsafety import is_fixture_origin
from app.modules.execution import policy, rehearsal, runner
from app.modules.execution.adapters.lever import LeverFixtureAdapter
from app.modules.execution.models import Evidence, ExecutionAttempt
from app.modules.providers import registry, routing, wording
from tests.execution_harness import BASE, PDF, Receiver, attempt, queue, synthetic_candidate

SITE, POSTING = "examplehealth", "00000000-0000-4000-8000-00000000a001"
POSTING_URL = f"{BASE}/lever/{SITE}/{POSTING}"
SLUG = f"lever-{SITE}-{POSTING}"
COVER = b"%PDF-1.4\n% synthetic cover letter for the Lever-style fixture\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def lever_job(api, url=POSTING_URL, title="Registered Nurse, Night Shift") -> str:
    r = api.post("/jobs", json={"url": url, "title": title,
                                "employer": "Example Health (fictional)"})  # fmt: skip
    assert r.status_code in (200, 201), r.text
    return r.json()["job"]["id"]


def lever_application(api, *, approve=True, scope=None, url=POSTING_URL, cover=False,
                      certifications=("BLS", "ACLS"), title=None) -> str:  # fmt: skip
    """Synthetic candidate, the posting's form captured, the user's own answers and consent;
    approved (to submit unless `scope` says otherwise)."""
    synthetic_candidate(api)
    job_id = lever_job(api, url, title or "Registered Nurse, Night Shift")
    r = api.post(f"/jobs/{job_id}/form/lever")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {
        "cards[q1][field0]": {"label": "Nights"},
        # Sponsorship asked with no country named: your answer for this application (D81).
        "cards[q1][field2]": {"label": "No"},
        "cards[q1][field3]": {"text": "I want to keep night wards calm and safe."},
        "cards[q1][field4]": {"labels": list(certifications)},
    }
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    if cover:
        doc = api.post("/documents", data={"kind": "cover_letter"},
                       files={"file": ("cover.pdf", COVER, "application/pdf")}).json()  # fmt: skip
        r = api.put(f"/applications/{app_id}/documents",
                    json={"cover_letter_document_id": doc["id"]})  # fmt: skip
        assert r.status_code == 200, r.text
    api.put(f"/applications/{app_id}/consents",
            json={"key": "consent[marketing]", "choice": "decline"})  # fmt: skip
    v = api.put(f"/applications/{app_id}/consents",
                json={"key": "consent[store]", "choice": "agree"}).json()  # fmt: skip
    p = v["package"]
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    if approve:
        body = {"version": p["version"], "content_hash": p["content_hash"]}
        r = api.post(f"/applications/{app_id}/package/approve",
                     json=body | ({"scope": scope} if scope else {}))  # fmt: skip
        assert r.status_code == 200, r.text
    return app_id


def evidence(aid: str, kind: str) -> list[dict]:
    with SessionLocal() as db:
        return [e.data for e in db.scalars(select(Evidence).where(
            Evidence.attempt_id == uuid.UUID(aid), Evidence.kind == kind))]  # fmt: skip


def uploads(led) -> list[dict]:
    return [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "upload"]


# ---------------------------------------------------------------------------- capture


def test_the_posting_form_is_captured_with_stable_keys(api, receiver):
    synthetic_candidate(api)
    job_id = lever_job(api)
    first = api.post(f"/jobs/{job_id}/form/lever").json()
    assert first["source"] == "fixture_lever"
    assert (
        first["source_label"] == "Lever-style form: local test approximation (fictional employer)"
    )
    fields = {f["key"]: f for f in first["schema"]["fields"]}
    assert fields["location"]["type"] == "unsupported" and not fields["location"]["required"]
    assert fields["resume"]["type"] == "file" and fields["resume"]["required"]
    assert fields["cards[q1][field1]"]["type"] == "radio" and fields["consent[store]"]["required"]
    assert "form_token" not in fields and "resume_upload_id" not in fields
    # A new form token on every load changes nothing: the same schema, the same version.
    again = api.post(f"/jobs/{job_id}/form/lever").json()
    assert (again["id"], again["fingerprint"]) == (first["id"], first["fingerprint"])
    assert api.get(f"/jobs/{job_id}/route").json()["provider"] == "fixture_lever"


def test_facts_fill_what_they_answer_and_the_rest_waits_for_you(api, receiver):
    synthetic_candidate(api)
    job_id = lever_job(api)
    api.post(f"/jobs/{job_id}/form/lever")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    a = {x["key"]: x for x in content["answers"]}
    assert a["name"]["value"] == {"text": "Sam Synthetic"}
    assert a["cards[q1][field1]"]["value"]["option"] == "Yes"  # authorized: your US fact
    # Sponsorship with no country named, the shift, and both consents are yours to give.
    assert {"cards[q1][field2]", "cards[q1][field0]", "consent[store]",
            "consent[marketing]"} <= set(content["unresolved"])  # fmt: skip
    assert a["cards[q1][field2]"]["value"] is None
    assert a["location"]["value"] is None  # a picker: never typed into
    assert a["eeo[gender]"]["value"] is None  # never inferred


def test_unknown_authorization_blocks_approval(api, receiver):
    synthetic_candidate(api)
    wa = api.get("/profile/work-authorizations").json()[0]
    r = api.put(f"/profile/work-authorizations/{wa['id']}",
                json={"country_code": "US", "authorized": "unknown", "sponsorship_needed_now": "no",
                      "sponsorship_needed_future": "no"})  # fmt: skip
    assert r.status_code == 200, r.text
    job_id = lever_job(api)
    api.post(f"/jobs/{job_id}/form/lever")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert "cards[q1][field1]" in p["content"]["unresolved"]
    assert {x["key"]: x for x in p["content"]["answers"]}["cards[q1][field1]"]["value"] is None
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code in (400, 409)


@pytest.mark.parametrize("mode", ["lever_location_required", "lever_captcha"])
def test_a_required_picker_or_a_bot_check_on_the_form_blocks_approval(api, receiver, mode):
    receiver.config(mode=mode)
    synthetic_candidate(api)
    job_id = lever_job(api)
    assert api.post(f"/jobs/{job_id}/form/lever").status_code == 201
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "checkpoint" and route["reason"] == "unsupported_required_control"
    assert receiver.ledger()["disclosures"] == []


def test_a_real_lever_posting_is_never_read_and_is_a_manual_handoff(api, receiver):
    synthetic_candidate(api)
    job_id = lever_job(api, url=f"https://jobs.lever.co/acme/{uuid.uuid4()}")
    r = api.post(f"/jobs/{job_id}/form/lever")
    assert r.status_code == 409 and "Reading real Lever postings is not enabled" in r.text
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "manual_handoff" and route["reason"] == "planned_adapter_only"
    assert route["provider"] == "manual_handoff"
    assert [r["path"] for r in receiver.ledger()["requests"]] == []  # nothing fetched at all


# ---------------------------------------------------------------------------- full runs


def test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents(api, receiver):
    app_id = lever_application(api, cover=True)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "fixture_lever"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["name"] == "Sam Synthetic" and sent["email"] == "sam.synthetic@example.com"
    assert sent["cards[q1][field0]"] == "Nights"
    assert sent["cards[q1][field1]"] == "Yes" and sent["cards[q1][field2]"] == "No"
    assert sent["cards[q1][field4]"] == ["BLS", "ACLS"]
    assert sent["consent[store]"] == "on" and "consent[marketing]" not in sent
    assert not sent.get("location") and not sent.get("eeo[gender]")
    # Each document left the browser as its own disclosure, byte for byte the approved one.
    ups = {u["field"]: u for u in uploads(led)}
    assert ups["resume"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert ups["cards[q1][field5]"]["sha256"] == hashlib.sha256(COVER).hexdigest()
    assert sent["resume_upload_id"] == ups["resume"]["upload_id"]
    receipt = evidence(aid, "receipt")[0]
    assert receipt["receipt_id"] == led["acceptances"][0]["receipt"]
    assert set(receipt) == {"receipt_id", "confirmation", "final_origin", "http_status"}
    assert evidence(aid, "readback")[0]["mismatched"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_a_rehearsal_discloses_under_its_approval_and_never_submits(api, receiver):
    app_id = lever_application(api, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["resume"]
    assert not [
        r for r in led["requests"] if r["method"] == "POST" and r["path"].endswith("/apply")
    ]
    # Submitting needs its own approval: the rehearsal's approval is used up, never reused.
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 0


def test_a_duplicate_delivery_never_submits_twice(api, receiver):
    receiver.config(idempotent=False)  # every POST would count: a second send would show
    app_id = lever_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"  # the same message delivered again
    assert receiver.ledger()["accepted"] == 1


def test_an_uncertain_final_send_is_quarantined_and_never_retried(api, receiver):
    receiver.config(mode="drop_after_accept")
    app_id = lever_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1  # it did arrive; NoEfforts cannot know that
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("validation_fail", "rejected"),
        ("error_before_accept", "unknown"),
        ("lever_captcha_after_submit", "unknown"),
        ("lever_verification", "unknown"),
        ("lever_receipt_elsewhere", "unknown"),
    ],
)
def test_outcomes_after_the_final_click(api, receiver, mode, expected):
    app_id = lever_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == expected
    led = receiver.ledger()
    assert led["accepted"] == (1 if mode == "lever_receipt_elsewhere" else 0)
    assert runner.run_attempt(aid, "w2") == "ignored"  # never sent again
    assert receiver.ledger()["accepted"] == led["accepted"]


def test_confirmation_bound_to_attempt(api, receiver):
    """A confirmation on another posting's page is not this attempt's: unknown, never
    confirmed, never resent."""
    receiver.config(mode="lever_receipt_elsewhere")
    app_id = lever_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert evidence(aid, "receipt") == []
    assert "not for this submission" in attempt(aid).outcome_detail
    led = receiver.ledger()  # it did arrive: the receiver accepted it once, and only once
    assert led["accepted"] == 1 and led["acceptances"][0]["slug"] == SLUG


# ---------------------------------------------------------------------------- stops


def test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure(api, receiver):
    receiver.config(upload_fail_field="cards[q1][field5]")
    app_id = lever_application(api, cover=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["resume"]
    sent = {d["field"]: d["ack"] for d in evidence(aid, "disclosure")}
    assert sent == {"resume": "attachment_shown", "cards[q1][field5]": "error_shown"}


def test_a_parsed_resume_that_changes_a_field_stops_before_submit(api, receiver):
    """The page writes a parsed location into a field NoEfforts leaves empty (and a parsed name,
    which the approved value replaces): what would be sent is no longer what you approved."""
    receiver.config(mode="lever_prefill")
    app_id = lever_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert evidence(aid, "readback")[0]["mismatched"] == 1
    assert "did not keep their values" in attempt(aid).outcome_detail


def test_a_bot_check_that_appears_after_approval_stops_before_disclosure(api, receiver):
    app_id = lever_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="lever_captcha")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert "CAPTCHA" in attempt(aid).outcome_detail


def test_form_changed_after_approval_stops_before_disclosure(api, receiver):
    app_id = lever_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="lever_drift")  # a new required question
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert "the form has changed" in attempt(aid).outcome_detail


def test_a_changed_approved_input_invalidates_the_approval(api, receiver):
    app_id = lever_application(api)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "cards[q1][field0]", "value": {"label": "Days"}})  # fmt: skip
    assert r.status_code == 200, r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------------------- the local boundary

REAL = f"https://jobs.lever.co/acme/{uuid.uuid4()}"


def test_fixture_evidence_never_enables_a_real_destination():
    real = {"origin": "https://jobs.lever.co", "url": REAL, "submit_url": f"{REAL}/apply",
            "form_source": "fixture_lever", "ats_provider": "lever"}  # fmt: skip
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for(real)
    assert e.value.code == "real_destination_disabled"
    d = routing.decide(real)
    assert (d.route, d.provider, d.reason) == ("manual_handoff", "manual_handoff",
                                               "planned_adapter_only")  # fmt: skip
    assert rehearsal.execution_path(real, "fixture_lever") is None  # no rehearsal counts there
    spec = registry.PROVIDERS["fixture_lever"]
    assert spec.ats is None and not spec.real_destinations_enabled
    assert registry.planned_for_ats("lever").name == "lever"  # real Lever: a plan only


def test_the_app_never_calls_this_live_support(api, receiver):
    synthetic_candidate(api)
    job_id = lever_job(api)
    api.post(f"/jobs/{job_id}/form/lever")
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["label"] == "Browser adapter (local test fixture only)"
    assert route["provider_support"] == "Local test fixtures only"
    shown = [route["label"], route["provider_support"], route["message"],
             wording.form_source_label("fixture_lever")]  # fmt: skip
    assert not [t for t in shown if t and wording.CLAIMS.search(t)]
    p = api.get("/providers").json()["fixture_lever"]
    assert p["support_state"] == "fixture_only" and p["real_destinations_enabled"] is False


def test_a_form_page_off_the_destination_site_is_never_opened(api, receiver, monkeypatch):
    app_id = lever_application(api)
    aid = queue(api, app_id)
    elsewhere = f"http://127.0.0.1:8798/lever/{SITE}/{POSTING}/apply"  # another origin
    monkeypatch.setattr(LeverFixtureAdapter, "form_url", lambda self: elsewhere)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "the form is not on the destination's site" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered(
    api, receiver, monkeypatch
):
    receiver.config(canary="http://127.0.0.1:8798")
    app_id = lever_application(api)
    aid = queue(api, app_id)
    monkeypatch.setattr(LeverFixtureAdapter, "form_url", lambda self: f"{BASE}/redirect-chain")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert [r["path"] for r in led["requests"] if r["path"].startswith("/redirect")] == [
        "/redirect-chain", "/redirect-to-canary"]  # fmt: skip


@pytest.mark.parametrize(
    "origin",
    ["https://jobs.lever.co", "https://careers.example.com", "http://8.8.8.8",
     "http://10.0.0.5:8799"],
)  # fmt: skip
def test_listing_a_public_site_as_a_fixture_never_makes_it_one(api, receiver, monkeypatch, origin):
    monkeypatch.setattr(get_settings(), "fixture_origins",
                        [*get_settings().fixture_origins, origin])  # fmt: skip
    assert not is_fixture_origin(origin)
    assert is_fixture_origin(BASE) and is_fixture_origin("http://receiver:8799") is False
    synthetic_candidate(api)
    r = api.post("/jobs", json={"url": f"{origin}/lever/{SITE}/{POSTING}", "title": "Nurse",
                                "employer": "Example Health (fictional)"})  # fmt: skip
    if r.status_code == 400:  # a private address is refused as a job address at all
        assert "non-public" in r.text
    else:
        job_id = r.json()["job"]["id"]
        assert api.post(f"/jobs/{job_id}/form/lever").status_code in (400, 409)
        assert api.get(f"/jobs/{job_id}/route").json()["route"] == "manual_handoff"
    assert [r for r in receiver.ledger()["requests"] if "/lever/" in r["path"]] == []


def test_only_the_listed_compose_receiver_name_is_a_fixture_host():
    """The Compose test network's receiver (scripts/compose-execution-test.sh) is listed by
    name (D86); no other single-label name, `localhost` included, is a fixture host."""
    from app.core.urlsafety import local_fixture_host

    assert local_fixture_host("receiver") and local_fixture_host("127.0.0.1")
    assert local_fixture_host("::1") and not local_fixture_host("localhost")
    assert not local_fixture_host("jobs.lever.co") and not local_fixture_host("10.0.0.5")
    assert not local_fixture_host("") and not local_fixture_host("8.8.8.8")
    assert not local_fixture_host("other") and not local_fixture_host("receiver.")
