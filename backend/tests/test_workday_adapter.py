"""The Workday-style adapter (`fixture_workday`, D88), checkpoint-first, against the labelled
local approximation (fixtures/ats_receiver/workday_like.py). The receiver's own ledger is the
oracle for every claim about what reached the employer. Synthetic candidate data only; no
Workday host is contacted, and the adapter has no Workday identity, so a real Workday job stays
the planned specification's manual handoff."""

import hashlib
import json
import random
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import policy, rehearsal, runner
from app.modules.execution.adapters.workday import WorkdayFixtureAdapter
from app.modules.execution.models import Evidence, ExecutionAttempt
from app.modules.providers import registry, routing, wording
from tests.execution_harness import BASE, PDF, Receiver, attempt, queue, synthetic_candidate

TENANT, REQ = "examplehealth", "R-100001"
POSTING_URL = f"{BASE}/workday/{TENANT}/{REQ}"
SLUG = f"workday-{TENANT}-{REQ}"
COVER = b"%PDF-1.4\n% synthetic cover letter for the Workday-style fixture\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def fresh_url() -> str:
    return f"{BASE}/workday/{TENANT}/R-{random.randint(10**8, 10**9 - 1)}"


def workday_job(api, url=POSTING_URL, title="Registered Nurse, Night Shift") -> str:
    r = api.post("/jobs", json={"url": url, "title": title,
                                "employer": "Example Health (fictional)"})  # fmt: skip
    assert r.status_code in (200, 201), r.text
    return r.json()["job"]["id"]


def workday_application(api, *, approve=True, scope=None, url=POSTING_URL, cover=False,
                        title=None) -> str:  # fmt: skip
    """Synthetic candidate, the application page captured, the user's own answers and the terms
    acknowledgement; approved (to submit unless `scope` says otherwise)."""
    synthetic_candidate(api)
    job_id = workday_job(api, url, title or "Registered Nurse, Night Shift")
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {
        # "Given Name(s)" is not a wording the resolver knows: your answer, for this application.
        "legalName--firstName": {"text": "Sam"},
        "q.licence_type": {"label": "RN"},
        "q.shift": {"label": "Nights"},
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
    v = api.put(f"/applications/{app_id}/consents",
                json={"key": "terms_ack", "choice": "agree"}).json()  # fmt: skip
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


def kinds(led) -> list[str]:
    return [d["kind"] for d in led["disclosures"]]


# ---------------------------------------------------------------------------- capture


def test_the_application_page_is_captured_with_stable_keys(api, receiver):
    synthetic_candidate(api)
    job_id = workday_job(api)
    first = api.post(f"/jobs/{job_id}/form/workday").json()
    assert first["source"] == "fixture_workday"
    assert first["source_label"] == (
        "Workday-style application: local test approximation (fictional employer)"
    )
    fields = {f["key"]: f for f in first["schema"]["fields"]}
    assert fields["resume"]["type"] == "file" and fields["resume"]["required"]
    assert fields["q.work_eligibility"]["type"] == "radio" and fields["terms_ack"]["required"]
    assert fields["aria:source"]["type"] == "unsupported"  # a custom dropdown: never operated
    assert not {"form_token", "resume_attachment", "multi_step", "prefilled_values"} & set(fields)
    again = api.post(f"/jobs/{job_id}/form/workday").json()  # a new form token changes nothing
    assert (again["id"], again["fingerprint"]) == (first["id"], first["fingerprint"])
    assert api.get(f"/jobs/{job_id}/route").json()["provider"] == "fixture_workday"


def test_facts_fill_what_they_answer_and_the_rest_waits_for_you(api, receiver):
    synthetic_candidate(api)
    job_id = workday_job(api)
    api.post(f"/jobs/{job_id}/form/workday")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    a = {x["key"]: x["value"] for x in content["answers"]}
    assert a["legalName--lastName"] == {"text": "Synthetic"}
    assert a["q.work_eligibility"]["option"] == "Yes" and a["q.sponsorship"]["option"] == "No"
    assert set(content["unresolved"]) == {"legalName--firstName", "q.licence_type", "q.shift",
                                          "terms_ack"}  # fmt: skip
    assert a["vd.gender"] is None and a["aria:source"] is None  # never inferred or operated
    assert a["address--addressLine1"] is None  # no fact answers it


def test_unknown_authorization_blocks_approval(api, receiver):
    synthetic_candidate(api)
    wa = api.get("/profile/work-authorizations").json()[0]
    r = api.put(f"/profile/work-authorizations/{wa['id']}",
                json={"country_code": "US", "authorized": "unknown", "sponsorship_needed_now": "no",
                      "sponsorship_needed_future": "no"})  # fmt: skip
    assert r.status_code == 200, r.text
    job_id = workday_job(api)
    api.post(f"/jobs/{job_id}/form/workday")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert "q.work_eligibility" in p["content"]["unresolved"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code in (400, 409)


@pytest.mark.parametrize(
    ("mode", "key"),
    [("wd_account_required", "account.password"), ("wd_multi_step", "multi_step"),
     ("wd_prefilled", "prefilled_values"), ("wd_location_cascade", "address--region"),
     ("wd_custom_dropdown", "aria:source")],
)  # fmt: skip
def test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints(
    api, receiver, mode, key
):
    receiver.config(mode=mode)
    synthetic_candidate(api)
    job_id = workday_job(api, url=fresh_url())
    form = api.post(f"/jobs/{job_id}/form/workday").json()
    field = {f["key"]: f for f in form["schema"]["fields"]}[key]
    assert field["type"] == "unsupported" and field["required"], field
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "checkpoint" and route["reason"] == "unsupported_required_control"
    assert receiver.ledger()["disclosures"] == []


def test_a_real_workday_posting_is_never_read_and_is_a_manual_handoff(api, receiver):
    synthetic_candidate(api)
    url = "https://acme.wd5.myworkdayjobs.com/External/job/Springfield/Nurse_R-100001"
    job_id = workday_job(api, url=url)
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 409 and "Reading real Workday postings is not enabled" in r.text
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "manual_handoff" and route["reason"] == "planned_adapter_only"
    assert [r["path"] for r in receiver.ledger()["requests"]] == []  # nothing fetched at all


# ---------------------------------------------------------------------------- full runs


def test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents(api, receiver):
    app_id = workday_application(api, cover=True)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "fixture_workday"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["legalName--firstName"] == "Sam" and sent["legalName--lastName"] == "Synthetic"
    assert sent["email"] == "sam.synthetic@example.com"
    assert sent["q.work_eligibility"] == "Yes" and sent["q.sponsorship"] == "No"
    assert sent["q.licence_type"] == "RN" and sent["q.shift"] == "Nights"
    assert sent["terms_ack"] == "1"
    assert not sent.get("vd.gender") and not sent.get("address--addressLine1")
    ups = {u["field"]: u for u in uploads(led)}
    assert ups["resume"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert ups["cover_letter"]["sha256"] == hashlib.sha256(COVER).hexdigest()
    assert sent["resume_attachment"] == ups["resume"]["upload_id"]
    receipt = evidence(aid, "receipt")[0]
    assert receipt["receipt_id"] == led["acceptances"][0]["receipt"]
    assert set(receipt) == {"receipt_id", "confirmation", "final_origin", "http_status"}
    assert evidence(aid, "readback")[0]["mismatched"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_a_rehearsal_discloses_under_its_approval_and_never_submits(api, receiver):
    app_id = workday_application(api, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["resume"]
    assert not [r for r in led["requests"]
                if r["method"] == "POST" and r["path"].endswith("/apply")]  # fmt: skip
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)  # submitting needs its own approval
    assert receiver.ledger()["accepted"] == 0


def test_a_duplicate_delivery_never_submits_twice(api, receiver):
    receiver.config(idempotent=False)  # every POST would count: a second send would show
    app_id = workday_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1


def test_an_uncertain_final_send_is_quarantined_and_never_retried(api, receiver):
    receiver.config(mode="drop_after_accept")
    app_id = workday_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1  # it did arrive; NoEfforts cannot know that
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 1


def test_email_verification_after_the_final_click_is_a_hard_stop(api, receiver):
    """No inbox is read and no code entered: an unknown outcome, quarantined, never resent."""
    app_id = workday_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="wd_verification")
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert "verify your email" in attempt(aid).outcome_detail
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    led = receiver.ledger()
    assert kinds(led).count("submit_verification") == 1 and led["accepted"] == 0


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("validation_fail", "rejected"),
        ("error_before_accept", "unknown"),
        ("error_after_accept", "unknown"),
        ("wd_verification", "unknown"),
        ("wd_receipt_elsewhere", "unknown"),
    ],
)
def test_outcomes_after_the_final_click(api, receiver, mode, expected):
    app_id = workday_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == expected
    led = receiver.ledger()
    assert led["accepted"] == (1 if mode in ("wd_receipt_elsewhere", "error_after_accept")
                               else 0)  # fmt: skip
    assert runner.run_attempt(aid, "w2") == "ignored"  # never sent again
    assert receiver.ledger()["accepted"] == led["accepted"]


def test_confirmation_bound_to_attempt(api, receiver):
    receiver.config(mode="wd_receipt_elsewhere")
    app_id = workday_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert evidence(aid, "receipt") == []
    assert "not for this submission" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["slug"] == SLUG


# ---------------------------------------------------------------------------- stops


def test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure(api, receiver):
    receiver.config(upload_fail_field="cover_letter")
    app_id = workday_application(api, cover=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["resume"]
    sent = {d["field"]: d["ack"] for d in evidence(aid, "disclosure")}
    assert sent == {"resume": "attachment_shown", "cover_letter": "error_shown"}


def test_resume_parsing_is_never_trusted_without_readback(api, receiver):
    """The parse fills an address NoEfforts leaves blank (and a name and city, which the
    approved values replace): what would be sent is no longer what you approved."""
    receiver.config(mode="wd_resume_parse")
    app_id = workday_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert evidence(aid, "readback")[0]["mismatched"] == 1
    assert "did not keep their values" in attempt(aid).outcome_detail


@pytest.mark.parametrize(
    ("mode", "detail"),
    [("wd_account_required", "sign in or create an account"),
     ("wd_multi_step", "several pages")],
)  # fmt: skip
def test_an_account_gate_or_several_pages_after_approval_stop_before_disclosure(
    api, receiver, mode, detail
):
    app_id = workday_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert detail in attempt(aid).outcome_detail


def test_form_changed_after_approval_stops_before_disclosure(api, receiver):
    app_id = workday_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="wd_drift")  # a new required question
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert "the form has changed" in attempt(aid).outcome_detail


def test_a_changed_approved_input_invalidates_the_approval(api, receiver):
    app_id = workday_application(api)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "q.shift", "value": {"label": "Days"}})  # fmt: skip
    assert r.status_code == 200, r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------------------- the local boundary

REAL = "https://acme.wd5.myworkdayjobs.com/External/job/Springfield/Nurse_R-100001"


def test_fixture_evidence_never_enables_a_real_destination():
    real = {"origin": "https://acme.wd5.myworkdayjobs.com", "url": REAL,
            "submit_url": f"{REAL}/apply", "form_source": "fixture_workday",
            "ats_provider": "workday"}  # fmt: skip
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for(real)
    assert e.value.code == "real_destination_disabled"
    d = routing.decide(real)
    assert (d.route, d.provider, d.reason) == ("manual_handoff", "manual_handoff",
                                               "planned_adapter_only")  # fmt: skip
    assert rehearsal.execution_path(real, "fixture_workday") is None
    spec = registry.PROVIDERS["fixture_workday"]
    assert spec.ats is None and not spec.real_destinations_enabled
    assert registry.planned_for_ats("workday").name == "workday"  # real Workday: a plan only


def test_the_app_never_calls_this_live_support(api, receiver):
    synthetic_candidate(api)
    job_id = workday_job(api)
    api.post(f"/jobs/{job_id}/form/workday")
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["label"] == "Browser adapter (local test fixture only)"
    assert route["provider_support"] == "Local test fixtures only"
    shown = [route["label"], route["provider_support"], route["message"],
             wording.form_source_label("fixture_workday")]  # fmt: skip
    assert not [t for t in shown if t and wording.CLAIMS.search(t)]
    p = api.get("/providers").json()["fixture_workday"]
    assert p["support_state"] == "fixture_only" and p["real_destinations_enabled"] is False


def test_a_form_page_off_the_destination_site_is_never_opened(api, receiver, monkeypatch):
    app_id = workday_application(api)
    aid = queue(api, app_id)
    elsewhere = f"http://127.0.0.1:8798/workday/{TENANT}/{REQ}/apply"  # another origin
    monkeypatch.setattr(WorkdayFixtureAdapter, "form_url", lambda self: elsewhere)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "the form is not on the destination's site" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered(
    api, receiver, monkeypatch
):
    receiver.config(canary="http://127.0.0.1:8798")
    app_id = workday_application(api)
    aid = queue(api, app_id)
    monkeypatch.setattr(WorkdayFixtureAdapter, "form_url", lambda self: f"{BASE}/redirect-chain")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert [r["path"] for r in led["requests"] if r["path"].startswith("/redirect")] == [
        "/redirect-chain", "/redirect-to-canary"]  # fmt: skip
