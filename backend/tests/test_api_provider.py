"""The authorized-API route (adapters/fake_api.py) against the local fake API
(fixtures/ats_receiver/fake_api.py). That API is the receiver's, with its own acceptance ledger:
the ledger, not NoEfforts' tables, is the oracle for what was created, uploaded and accepted.
No real ATS is claimed to offer this interface."""

import json
import logging
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import AttemptEvent, Evidence, ExecutionAttempt
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import BASE, PDF, Receiver, attempt, queue
from tests.test_greenhouse_dom import v2_application

TOKEN = "fixture-api-token"
SLUG = "fapi:northwind/5020001"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)


def grant(api) -> str:
    r = api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def approve(api, app_id):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 200, r.text


def api_application(api) -> str:
    app_id = v2_application(api, approve=False)
    grant(api)
    approve(api, app_id)
    with SessionLocal() as db:
        appr = db.scalar(select(PackageApproval).where(
            PackageApproval.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert appr.adapter == "fake_api"
    return app_id


def fapi_requests(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]
            if r["path"].startswith("/fapi/")]  # fmt: skip


def acceptances(receiver):
    return [a for a in receiver.ledger()["acceptances"] if a["slug"] == SLUG]


def test_authorized_api_submission_sends_exactly_the_approved_package(api, receiver):
    app_id = api_application(api)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "fake_api"
    page_reads = len([r for r in receiver.ledger()["requests"] if r["path"].startswith("/gh2/")])
    assert runner.run_attempt(aid, "w1") == "confirmed"
    acc = acceptances(receiver)
    assert len(acc) == 1 and acc[0]["form_token"] == aid  # the idempotency key
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    for a in content["answers"]:
        if a["value"] is not None and a["type"] not in ("file", "unsupported"):
            assert acc[0]["fields"][a["key"]] == a["value"], a["key"]
    uploads = [json.loads(d["detail"]) for d in receiver.ledger()["disclosures"]
               if d["kind"] == "upload"]  # fmt: skip
    assert uploads == [{"field": "resume", "sha256": content["documents"][0]["sha256"]}]
    # No browser: the run itself requested no form page (preparation read it earlier).
    after = len([r for r in receiver.ledger()["requests"] if r["path"].startswith("/gh2/")])
    assert after == page_reads


def test_without_authorization_the_api_is_never_contacted(api, receiver):
    app_id = v2_application(api)  # approved for the browser route
    with SessionLocal() as db:
        appr = db.scalar(select(PackageApproval).where(
            PackageApproval.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert appr.adapter == "greenhouse_dom"
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"  # by the browser
    assert fapi_requests(receiver) == []


def test_granting_the_api_retires_a_browser_approval_and_revoking_retires_it_again(api, receiver):
    """Never a silent switch: the route changes only with a new approval."""
    app_id = v2_application(api)
    gid = grant(api)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "changed after you approved" in r.text
    approve(api, app_id)  # approved again, now for the API route
    api.delete(f"/api-authorizations/{gid}")
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409
    assert fapi_requests(receiver) == []


def test_missing_credentials_after_approval_stop_before_anything_is_sent(api, receiver):
    aid = queue(api, api_application(api))
    get_settings().fake_api_token = ""  # restored by the autouse fixture
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "execution method changed" in attempt(aid).outcome_detail
    assert fapi_requests(receiver) == []


def test_a_stale_approval_stops_before_disclosure(api, receiver):
    app_id = api_application(api)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        appr = db.scalar(select(PackageApproval).where(
            PackageApproval.application_id == uuid.UUID(app_id)))  # fmt: skip
        appr.expires_at = appr.approved_at
        db.commit()
    # Refused at claim or at the gate, never run: nothing created, uploaded or accepted.
    assert runner.run_attempt(aid, "w1") in ("ignored", "failed_safe")
    assert attempt(aid).state != "confirmed"
    assert not any(m == "POST" for m, _ in fapi_requests(receiver))
    assert receiver.ledger()["disclosures"] == []


def test_an_attempt_recorded_for_another_provider_is_refused(api, receiver):
    aid = queue(api, api_application(api))
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).adapter = "greenhouse_dom"
        db.commit()
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert fapi_requests(receiver) == [] and receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("fapi_schema_changed", "the API's form differs from what you approved (1 field(s))"),
        ("fapi_unauthorized", "the API refused NoEfforts' authorization"),
        ("fapi_rate_limited_schema", "the API is rate limiting requests (not retried)"),
    ],
)
def test_refusals_before_disclosure(api, receiver, mode, reason):
    aid = queue(api, api_application(api))
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert reason in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert [m for m, _ in fapi_requests(receiver)] == ["GET"]  # the schema read only


@pytest.mark.parametrize(
    "mode,result,accepted",
    [
        ("fapi_reject", "rejected", 0),
        ("fapi_error_before_accept", "unknown", 0),
        ("fapi_rate_limited_submit", "unknown", 0),  # after sending: reconciled, never resent
    ],
)
def test_outcomes_after_sending(api, receiver, mode, result, accepted):
    aid = queue(api, api_application(api))
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == result
    assert len(acceptances(receiver)) == accepted
    submits = [p for m, p in fapi_requests(receiver) if p.endswith("/submit")]
    assert len(submits) == 1  # sent once, never again
    assert runner.run_attempt(aid, "w2") == "ignored"


def test_accepted_but_response_lost_is_unknown_and_never_resent(api, receiver):
    aid = queue(api, api_application(api))
    receiver.config(mode="fapi_drop_after_accept", drop_s=8)  # longer than the submit timeout
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert len(acceptances(receiver)) == 1  # it was accepted
    assert "no response from the API after sending" in attempt(aid).outcome_detail
    assert runner.run_attempt(aid, "w2") == "ignored"  # a second delivery does nothing
    receiver.config(mode="normal")
    assert runner.reconcile_api(aid) == "accepted"  # read-only lookup by idempotency key
    assert len(acceptances(receiver)) == 1
    assert len([p for m, p in fapi_requests(receiver) if p.endswith("/submit")]) == 1
    assert attempt(aid).state == "unknown"  # the user reconciles; nothing changes by itself
    with SessionLocal() as db:
        kinds = [e.kind for e in db.scalars(select(AttemptEvent).where(
            AttemptEvent.attempt_id == uuid.UUID(aid)))]  # fmt: skip
    assert "reconciliation_checked" in kinds


def test_the_fake_api_itself_never_accepts_one_key_twice(receiver):
    """The contract's idempotency, on the API side: the same key creates one draft and at most
    one acceptance, however often it is sent; an incomplete draft accepts nothing."""
    import base64
    import urllib.error
    import urllib.request

    def call(method, path, body=None, key=None):
        h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        if key:
            h["Idempotency-Key"] = key
        req = urllib.request.Request(BASE + path, json.dumps(body or {}).encode(), h,
                                     method=method)  # fmt: skip
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    jobs = "/fapi/v1/boards/northwind/jobs/5020001/applications"
    partial = call("POST", jobs, {"answers": {"question_8101": {"option": "1"}}}, key="p1")
    with pytest.raises(urllib.error.HTTPError) as e:
        call("POST", f"/fapi/v1/applications/{partial['application']}/submit", key="p1")
    assert e.value.code == 422
    answers = {k: {"text": "x"} for k in ("first_name", "last_name", "preferred_name", "email",
                                          "phone")}  # fmt: skip
    answers |= {"question_8101": {"option": "1"}, "question_8102": {"option": "913"},
                "question_8104": {"option": "0"}}  # fmt: skip
    d1 = call("POST", jobs, {"answers": answers}, key="k1")["application"]
    d2 = call("POST", jobs, {"answers": answers}, key="k1")["application"]
    assert d1 == d2
    call("POST", f"/fapi/v1/applications/{d1}/documents", {
        "field": "resume", "filename": "r.pdf", "content_type": "application/pdf",
        "content_b64": base64.b64encode(PDF).decode()})  # fmt: skip
    r1 = call("POST", f"/fapi/v1/applications/{d1}/submit", key="k1")
    r2 = call("POST", f"/fapi/v1/applications/{d1}/submit", key="k1")
    assert r1["receipt"] == r2["receipt"] and len(acceptances(receiver)) == 1
    assert call("GET", "/fapi/v1/applications?idempotency_key=k1")["status"] == "accepted"
    assert call("GET", "/fapi/v1/applications?idempotency_key=k9")["status"] == "not_found"


def test_api_evidence_and_logs_carry_no_candidate_data_secrets_or_raw_ids(api, receiver, caplog):
    caplog.set_level(logging.DEBUG)
    app_id = api_application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    receipt = acceptances(receiver)[0]["receipt"]
    with SessionLocal() as db:
        ev = [e.data for e in db.scalars(select(Evidence).where(
            Evidence.attempt_id == uuid.UUID(aid)))]  # fmt: skip
        events = [e.detail for e in db.scalars(select(AttemptEvent).where(
            AttemptEvent.attempt_id == uuid.UUID(aid)))]  # fmt: skip
        detail = db.get(ExecutionAttempt, uuid.UUID(aid)).outcome_detail or ""
    text = json.dumps([ev, events, detail], default=str) + caplog.text
    import base64

    for marker in ("sam.synthetic@example.com", "555 0100", TOKEN, receipt,
                   base64.b64encode(PDF).decode()[:40]):  # fmt: skip
        assert marker not in text, marker
    assert any(e.get("receipt_ref_sha256") for e in ev)  # a reference, not the receipt


def test_confirmation_bound_to_attempt(api, receiver):
    """S5 (D62): an acceptance that names another application is not this attempt's: unknown,
    never sent again, reconciled by its own idempotency key."""
    aid = queue(api, api_application(api))
    receiver.config(mode="fapi_receipt_other")
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert "not the one this attempt created" in attempt(aid).outcome_detail
    assert len(acceptances(receiver)) == 1
    assert len([p for m, p in fapi_requests(receiver) if p.endswith("/submit")]) == 1
    assert runner.run_attempt(aid, "w2") == "ignored"
