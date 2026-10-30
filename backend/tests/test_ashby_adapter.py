"""The Ashby-style adapter (`fixture_ashby`, D87) against the labelled local approximation
(fixtures/ats_receiver/ashby_like.py). The receiver's own ledger is the oracle for every claim
about what reached the employer. Synthetic candidate data only; no Ashby host is contacted, and
the adapter has no Ashby identity, so a real Ashby job stays a manual handoff."""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import policy, rehearsal, runner
from app.modules.execution.adapters.ashby import AshbyFixtureAdapter
from app.modules.execution.models import Evidence, ExecutionAttempt
from app.modules.providers import registry, routing, wording
from tests.execution_harness import BASE, PDF, Receiver, attempt, queue, synthetic_candidate

BOARD, POSTING = "examplehealth", "00000000-0000-4000-8000-00000000c001"
POSTING_URL = f"{BASE}/ashby/{BOARD}/{POSTING}"
SLUG = f"ashby-{BOARD}-{POSTING}"
COVER = b"%PDF-1.4\n% synthetic cover letter for the Ashby-style fixture\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def ashby_job(api, url=POSTING_URL, title="Clinical Data Analyst") -> str:
    r = api.post("/jobs", json={"url": url, "title": title,
                                "employer": "Example Health (fictional)"})  # fmt: skip
    assert r.status_code in (200, 201), r.text
    return r.json()["job"]["id"]


def ashby_application(api, *, approve=True, scope=None, url=POSTING_URL, cover=False,
                      title=None, why=None) -> str:  # fmt: skip
    """Synthetic candidate, the posting's form captured, the user's own answers and consent;
    approved (to submit unless `scope` says otherwise). The optional "Why" question stays blank
    unless `why` is given."""
    synthetic_candidate(api)
    job_id = ashby_job(api, url, title or "Clinical Data Analyst")
    r = api.post(f"/jobs/{job_id}/form/ashby")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {
        "tool": {"label": "Python"},
        "domains": {"labels": ["Oncology", "Cardiology"]},
    } | ({"why": {"text": why}} if why else {})
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
                json={"key": "_systemfield_data_consent", "choice": "agree"}).json()  # fmt: skip
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


def test_the_posting_form_is_captured_with_stable_keys(api, receiver):
    synthetic_candidate(api)
    job_id = ashby_job(api)
    first = api.post(f"/jobs/{job_id}/form/ashby").json()
    assert first["source"] == "fixture_ashby"
    assert (
        first["source_label"] == "Ashby-style form: local test approximation (fictional employer)"
    )
    fields = {f["key"]: f for f in first["schema"]["fields"]}
    assert fields["_systemfield_location"]["type"] == "unsupported"  # a location picker
    assert (
        fields["_systemfield_resume"]["type"] == "file" and fields["cover_letter"]["type"] == "file"
    )
    assert fields["authorized"]["type"] == "radio" and fields["sponsorship"]["required"]
    assert fields["_systemfield_data_consent"]["required"]
    assert not {"form_token", "_systemfield_resume_file_handle", "bot_check"} & set(fields)
    # A new form token on every load changes nothing: the same schema, the same version.
    again = api.post(f"/jobs/{job_id}/form/ashby").json()
    assert (again["id"], again["fingerprint"]) == (first["id"], first["fingerprint"])
    assert api.get(f"/jobs/{job_id}/route").json()["provider"] == "fixture_ashby"


def test_facts_fill_what_they_answer_and_the_rest_waits_for_you(api, receiver):
    synthetic_candidate(api)
    job_id = ashby_job(api)
    api.post(f"/jobs/{job_id}/form/ashby")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    a = {x["key"]: x for x in content["answers"]}
    assert a["_systemfield_name"]["value"] == {"text": "Sam Synthetic"}
    # Both questions name the country, so your US facts answer them.
    assert a["authorized"]["value"]["option"] == "Yes"
    assert a["sponsorship"]["value"]["option"] == "No"
    assert set(content["unresolved"]) == {"tool", "_systemfield_data_consent"}
    assert a["_systemfield_location"]["value"] is None  # a picker: never typed into
    assert a["survey.gender"]["value"] is None  # never inferred
    assert a["years_sql"]["value"] is None  # a number NoEfforts does not know


def test_unknown_sponsorship_blocks_approval(api, receiver):
    synthetic_candidate(api)
    wa = api.get("/profile/work-authorizations").json()[0]
    r = api.put(f"/profile/work-authorizations/{wa['id']}",
                json={"country_code": "US", "authorized": "yes", "sponsorship_needed_now": "no",
                      "sponsorship_needed_future": "unknown"})  # fmt: skip
    assert r.status_code == 200, r.text
    job_id = ashby_job(api)
    api.post(f"/jobs/{job_id}/form/ashby")
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert "sponsorship" in p["content"]["unresolved"]
    assert {x["key"]: x for x in p["content"]["answers"]}["sponsorship"]["value"] is None
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code in (400, 409)


@pytest.mark.parametrize(
    "mode", ["ashby_location_required", "ashby_custom_boolean", "ashby_spam_on_form"]
)
def test_an_unsupported_required_control_or_the_spam_check_blocks_approval(api, receiver, mode):
    receiver.config(mode=mode)
    synthetic_candidate(api)
    job_id = ashby_job(api)
    form = api.post(f"/jobs/{job_id}/form/ashby").json()
    if mode == "ashby_spam_on_form":
        assert any(f["key"] == "bot_check" and f["required"] for f in form["schema"]["fields"])
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "checkpoint" and route["reason"] == "unsupported_required_control"
    assert receiver.ledger()["disclosures"] == []


@pytest.mark.parametrize(
    "url",
    [f"https://jobs.ashbyhq.com/acme/{uuid.uuid4()}",
     f"https://jobs.ashbyhq.com/acme/{uuid.uuid4()}/application",
     f"https://careers.examplehealth.invalid/jobs?ashby_jid={uuid.uuid4()}"],
)  # fmt: skip
def test_a_real_ashby_posting_is_never_read_and_is_a_manual_handoff(api, receiver, url):
    synthetic_candidate(api)
    job_id = ashby_job(api, url=url)
    r = api.post(f"/jobs/{job_id}/form/ashby")
    if "jobs.ashbyhq.com" in url:
        assert r.status_code == 409 and "Reading real Ashby postings is not enabled" in r.text
    else:  # an embed names no board: not an Ashby-style posting at all
        assert r.status_code == 400
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] == "manual_handoff" and route["provider"] == "manual_handoff"
    assert route["reason"] == "real_destination_disabled"
    assert [r["path"] for r in receiver.ledger()["requests"]] == []  # nothing fetched at all


# ---------------------------------------------------------------------------- full runs


def test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents(api, receiver):
    app_id = ashby_application(api, cover=True, why="I want clinical data to be trustworthy.")
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "fixture_ashby"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["_systemfield_name"] == "Sam Synthetic"
    assert sent["_systemfield_email"] == "sam.synthetic@example.com"
    assert sent["authorized"] == "Yes" and sent["sponsorship"] == "No"
    assert sent["tool"] == "Python" and sent["domains"] == ["Oncology", "Cardiology"]
    assert sent["linkedin"] == "https://www.linkedin.com/in/sam-synthetic"
    assert sent["why"] == "I want clinical data to be trustworthy."
    assert sent["_systemfield_data_consent"] == "true"
    # Never typed, inferred or chosen for you: the picker, the survey, an unknown number.
    assert not sent.get("_systemfield_location") and not sent.get("survey.gender")
    assert not sent.get("years_sql")
    # Each document left the browser as its own disclosure, byte for byte the approved one.
    ups = {u["field"]: u for u in uploads(led)}
    assert ups["_systemfield_resume"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert ups["cover_letter"]["sha256"] == hashlib.sha256(COVER).hexdigest()
    assert sent["_systemfield_resume_file_handle"] == ups["_systemfield_resume"]["upload_id"]
    assert sent["cover_letter_file_handle"] == ups["cover_letter"]["upload_id"]
    assert "cookie_choice" not in kinds(led)  # the cookie banner was never clicked
    receipt = evidence(aid, "receipt")[0]
    assert receipt["receipt_id"] == led["acceptances"][0]["receipt"]
    assert set(receipt) == {"receipt_id", "confirmation", "final_origin", "http_status"}
    assert evidence(aid, "readback")[0]["mismatched"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_a_rehearsal_discloses_under_its_approval_and_never_submits(api, receiver):
    app_id = ashby_application(api, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["_systemfield_resume"]
    assert not [r for r in led["requests"]
                if r["method"] == "POST" and r["path"].endswith("/application")]  # fmt: skip
    # Submitting needs its own approval: the rehearsal's approval is used up, never reused.
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 0


def test_a_duplicate_delivery_never_submits_twice(api, receiver):
    receiver.config(idempotent=False)  # every POST would count: a second send would show
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"  # the same message delivered again
    assert receiver.ledger()["accepted"] == 1


def test_an_uncertain_final_send_is_quarantined_and_never_retried(api, receiver):
    receiver.config(mode="drop_after_accept")
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1  # it did arrive; NoEfforts cannot know that
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize(
    ("mode", "submit_kind", "detail"),
    [("ashby_spam_after_submit", "submit_spam_blocked", "spam check"),
     ("ashby_duplicate", "submit_duplicate", "already applied")],
)  # fmt: skip
def test_the_spam_check_or_a_repeat_after_the_final_click_is_a_hard_stop(
    api, receiver, mode, submit_kind, detail
):
    """Never solved, retried or resent: an unknown outcome, quarantined, and the employer saw
    exactly one submission."""
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert detail in attempt(aid).outcome_detail
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    led = receiver.ledger()
    assert kinds(led).count(submit_kind) == 1 and led["accepted"] == 0
    assert evidence(aid, "receipt") == []


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("validation_fail", "rejected"),
        ("error_before_accept", "unknown"),
        ("error_after_accept", "unknown"),
        ("ashby_spam_after_submit", "unknown"),
        ("ashby_duplicate", "unknown"),
        ("ashby_receipt_elsewhere", "unknown"),
    ],
)
def test_outcomes_after_the_final_click(api, receiver, mode, expected):
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == expected
    led = receiver.ledger()
    assert led["accepted"] == (1 if mode in ("ashby_receipt_elsewhere", "error_after_accept")
                               else 0)  # fmt: skip
    assert runner.run_attempt(aid, "w2") == "ignored"  # never sent again
    assert receiver.ledger()["accepted"] == led["accepted"]


def test_a_confirmation_page_that_also_shows_a_bot_check_is_not_a_confirmation(api, receiver):
    """The page says submitted and shows a challenge: NoEfforts does not know what the challenge
    gates, so the outcome is unknown, quarantined and never resent."""
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="ashby_challenge_on_confirmation")
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert "bot check" in attempt(aid).outcome_detail and evidence(aid, "receipt") == []
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == 1  # it did arrive, once


def test_confirmation_bound_to_attempt(api, receiver):
    """A confirmation on another posting's page is not this attempt's: unknown, never
    confirmed, never resent."""
    receiver.config(mode="ashby_receipt_elsewhere")
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert evidence(aid, "receipt") == []
    assert "not for this submission" in attempt(aid).outcome_detail
    led = receiver.ledger()  # it did arrive: the receiver accepted it once, and only once
    assert led["accepted"] == 1 and led["acceptances"][0]["slug"] == SLUG


# ---------------------------------------------------------------------------- stops


def test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure(api, receiver):
    receiver.config(upload_fail_field="cover_letter")
    app_id = ashby_application(api, cover=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and [u["field"] for u in uploads(led)] == ["_systemfield_resume"]
    sent = {d["field"]: d["ack"] for d in evidence(aid, "disclosure")}
    assert sent == {"_systemfield_resume": "attachment_shown", "cover_letter": "error_shown"}


def test_a_resume_autofill_that_changes_a_field_stops_before_submit(api, receiver):
    """Autofill writes a parsed location into the picker NoEfforts leaves empty (and a parsed
    name and LinkedIn, which the approved values replace): what would be sent is no longer what
    you approved."""
    receiver.config(mode="ashby_autofill")
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert evidence(aid, "readback")[0]["mismatched"] == 1
    assert "did not keep their values" in attempt(aid).outcome_detail


def test_a_spam_check_that_appears_after_approval_stops_before_disclosure(api, receiver):
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="ashby_spam_on_form")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert "bot check" in attempt(aid).outcome_detail


def test_form_changed_after_approval_stops_before_disclosure(api, receiver):
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="ashby_drift")  # a new required question
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert "the form has changed" in attempt(aid).outcome_detail


def test_a_changed_approved_input_invalidates_the_approval(api, receiver):
    app_id = ashby_application(api)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "tool", "value": {"label": "R"}})  # fmt: skip
    assert r.status_code == 200, r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    assert receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------------------- the local boundary

REAL = f"https://jobs.ashbyhq.com/acme/{uuid.uuid4()}"


def test_fixture_evidence_never_enables_a_real_destination():
    real = {"origin": "https://jobs.ashbyhq.com", "url": REAL,
            "submit_url": f"{REAL}/application", "form_source": "fixture_ashby",
            "ats_provider": "ashby"}  # fmt: skip
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for(real)
    assert e.value.code == "real_destination_disabled"
    d = routing.decide(real)
    assert (d.route, d.provider) == ("manual_handoff", "manual_handoff")
    assert rehearsal.execution_path(real, "fixture_ashby") is None  # no rehearsal counts there
    spec = registry.PROVIDERS["fixture_ashby"]
    assert spec.ats is None and not spec.real_destinations_enabled
    assert registry.planned_for_ats("ashby") is None  # Ashby: no specification either


def test_the_app_never_calls_this_live_support(api, receiver):
    synthetic_candidate(api)
    job_id = ashby_job(api)
    api.post(f"/jobs/{job_id}/form/ashby")
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["label"] == "Browser adapter (local test fixture only)"
    assert route["provider_support"] == "Local test fixtures only"
    shown = [route["label"], route["provider_support"], route["message"],
             wording.form_source_label("fixture_ashby")]  # fmt: skip
    assert not [t for t in shown if t and wording.CLAIMS.search(t)]
    p = api.get("/providers").json()["fixture_ashby"]
    assert p["support_state"] == "fixture_only" and p["real_destinations_enabled"] is False


def test_a_form_page_off_the_destination_site_is_never_opened(api, receiver, monkeypatch):
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    elsewhere = f"http://127.0.0.1:8798/ashby/{BOARD}/{POSTING}/application"  # another origin
    monkeypatch.setattr(AshbyFixtureAdapter, "form_url", lambda self: elsewhere)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "the form is not on the destination's site" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered(
    api, receiver, monkeypatch
):
    receiver.config(canary="http://127.0.0.1:8798")
    app_id = ashby_application(api)
    aid = queue(api, app_id)
    monkeypatch.setattr(AshbyFixtureAdapter, "form_url", lambda self: f"{BASE}/redirect-chain")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert [r["path"] for r in led["requests"] if r["path"].startswith("/redirect")] == [
        "/redirect-chain", "/redirect-to-canary"]  # fmt: skip
