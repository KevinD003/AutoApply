"""Audit events and diagnostics carry safe metadata only (audit/service.py, routing.audit_route):
no applicant data, documents, credentials, employer or posting identifiers, or raw exception or
page content. Synthetic data and local fixtures only; nothing here contacts anything external."""

import json
import logging
import threading
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import ref, sanitize
from app.modules.execution import runner
from app.modules.preparation import drafting
from tests.execution_harness import BASE, Receiver, queue, synthetic_candidate
from tests.test_greenhouse_dom import LOC_JOB, v2_application, v2_job

WORKDAY_URL = "https://acme-example.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R-1234"
# Synthetic applicant, employer and posting markers that must never reach an audit event.
MARKERS = ["Sam Synthetic", "sam.synthetic@example.com", "555 0100", "Springfield", "Sammy",
           "resume.pdf", "%PDF", "Northwind", "Support Specialist", "/gh2/", "127.0.0.1",
           "question_8101", "question_8104", "myworkdayjobs", "Acme Example", "Engineer_R-1234",
           "fixture-api-token"]  # fmt: skip
ROUTE_META = {"route", "provider", "adapter_version", "reason_code", "evidence", "api_grant"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", "")


def audit_rows(action=None) -> list[AuditEvent]:
    with SessionLocal() as db:
        q = select(AuditEvent)
        if action:
            q = q.where(AuditEvent.action == action)
        return list(db.scalars(q.order_by(AuditEvent.created_at)))


def dump(rows) -> str:
    return json.dumps([[r.action, r.entity_type, r.entity_id, r.meta] for r in rows])


def assert_no_markers(text: str, extra=()):
    for m in [*MARKERS, *extra]:
        assert m not in text, m


# -- the sanitizer, one prohibited category at a time ------------------------------------------


@pytest.mark.parametrize(
    "meta",
    [
        {"answer": "Yes", "value": "Sammy", "text": "I led a team"},  # application answers
        {
            "filename": "resume.pdf",
            "content": "%PDF-1.4",
            "resume": "x",
            "cv": "y",
            "file": "resume.pdf",
            "attachments": "resume.pdf",
        },  # documents  # fmt: skip
        {
            "email": "a@b.c",
            "phone": "+1 555 0100",
            "address": "1 Main St",
            "name": "Sam",
            "full_name": "Sam Synthetic",
        },  # PII  # fmt: skip
        {
            "password": "p",
            "token": "t",
            "access_token": "t",
            "cookie": "c",
            "headers": "h",
            "session_id": "s",
            "authorization": "Bearer t",
            "api_secret": "s",
            "otp": "1",
            "code": "123456",
        },  # credentials and codes  # fmt: skip
        {
            "employer": "Acme",
            "company_name": "Acme",
            "title": "Engineer",
            "posting_url": "x",
            "url": "x",
            "origin": "x",
            "host": "x",
        },  # employer / posting identifiers  # fmt: skip
        {
            "exception": "boom",
            "traceback": "t",
            "raw": "r",
            "payload": "p",
            "message": "m",
            "body": "b",
            "detail": "d",
        },  # raw exception payloads and page content  # fmt: skip
    ],
)
def test_prohibited_keys_are_redacted(meta):
    out = sanitize(meta)
    assert set(out) == set(meta) and set(out.values()) == {"[redacted]"}


@pytest.mark.parametrize(
    "value",
    [
        "sam.synthetic@example.com",  # e-mail
        "+1 555 0100",  # phone (spaces, plus)
        "Sam Synthetic",  # a name (free text)
        "https://boards.example.com/acme/jobs/1",  # a URL
        "Bearer abc.def",  # a header value
        "Traceback (most recent call last): ...",  # a raw exception
        "<p>page content</p>",  # markup
        "x" * 65,  # anything long
        {"nested": "object"},  # structured payloads
        b"%PDF-1.4",  # bytes (document content)
        ["ok", "not ok"],  # a list with free text
        ["a"] * 21,  # a long list
    ],
)
def test_unsafe_values_are_omitted_under_any_key(value):
    assert sanitize({"reason_code": value}) == {"reason_code": "[omitted]"}


def test_safe_metadata_is_kept_and_external_identifiers_become_references():
    meta = {"route": "browser", "provider": "greenhouse_dom", "adapter_version": "greenhouse-dom-3",
            "reason_code": "browser_supported", "evidence": "fixture", "api_grant": "none",
            "version": 3, "flag": True, "fields": ["title", "notes"], "nothing": None,
            "content_hash": "a" * 64}  # fmt: skip
    assert sanitize(meta) == meta
    r = ref("question_8101", None)  # sanitize() without a user scopes to "no user"
    assert r.startswith("ref:v2:") and "8101" not in r and r == ref("question_8101", None)
    assert sanitize({"field_ref": r}) == {"field_ref": r}
    assert sanitize({"weird key!": 1}) == {}  # keys themselves must be identifier-like
    # `field` always held a posting's question key: it is stored as its reference.
    assert sanitize({"field": "question_8101"}) == {"field_ref": r}
    assert sanitize({"field": "question_8101", "field_ref": "ref:0"}) == {"field_ref": "ref:0"}
    assert sanitize({"field": ["question_8101"]}) == {"field_ref": "[omitted]"}


@pytest.mark.parametrize(
    "meta",
    [
        {"field": "question_8101", "reason": "Draft mentions 40 nurses", "version": 2},
        {"email": "a@b.c", "source": "https://boards.example.com/x", "weird key!": 1},
        {"fields": ["title", "notes"], "nested": {"a": 1}, "flag": False, "n": None},
        {"reason_code": "[redacted]", "route": "[omitted]"},
    ],
)
def test_sanitizing_is_idempotent(meta):
    once = sanitize(meta)
    assert sanitize(once) == once


def test_record_sanitizes_before_anything_is_stored(api):
    from app.modules.audit.service import record

    user_id = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        record(db, user_id, "test.event", "job", "00000000-0000-0000-0000-000000000001",
               email="sam.synthetic@example.com", reason_code="https://boards.example.com/x",
               provider="greenhouse_dom")  # fmt: skip
        db.commit()
    (row,) = audit_rows("test.event")
    assert row.meta == {"email": "[redacted]", "reason_code": "[omitted]",
                        "provider": "greenhouse_dom"}  # fmt: skip


# -- route decisions are audited with safe metadata only --------------------------------------


def test_route_decisions_are_audited_without_applicant_or_external_data(api, receiver, monkeypatch):
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.get(f"/jobs/{job_id}/route").json()["reason"] == "no_form_captured"
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    browser = api.get(f"/jobs/{job_id}/route").json()
    assert (browser["route"], browser["reason"], browser["authorization"]) == (
        "browser", "browser_supported", "none")  # fmt: skip
    api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE})
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    viaapi = api.get(f"/jobs/{job_id}/route").json()
    assert (viaapi["route"], viaapi["reason"], viaapi["authorization"]) == (
        "api", "api_authorized", "granted")  # fmt: skip
    loc = v2_job(api, LOC_JOB)
    api.post(f"/jobs/{loc}/form/greenhouse")
    cp = api.get(f"/jobs/{loc}/route").json()
    assert (cp["route"], cp["reason"]) == ("checkpoint", "unsupported_required_control")
    wd = api.post("/jobs", json={"url": WORKDAY_URL, "title": "Engineer",
                                 "employer": "Acme Example"}).json()["job"]["id"]  # fmt: skip
    assert api.get(f"/jobs/{wd}/route").json()["reason"] == "planned_adapter_only"

    rows = audit_rows("route.decision")
    got = [(r.entity_id, r.meta["route"], r.meta["reason_code"], r.meta["evidence"],
            r.meta["api_grant"]) for r in rows]  # fmt: skip
    assert got == [
        (job_id, "manual", "no_form_captured", "none", "not_applicable"),
        (job_id, "browser", "browser_supported", "fixture", "none"),
        (job_id, "api", "api_authorized", "fixture", "granted"),
        (loc, "checkpoint", "unsupported_required_control", "none", "not_applicable"),
        (wd, "manual", "planned_adapter_only", "none", "not_applicable"),
    ]
    assert all(set(r.meta) == ROUTE_META and r.entity_type == "job" for r in rows)
    assert rows[1].meta["adapter_version"].startswith("greenhouse-dom-3+")
    assert rows[2].meta["adapter_version"] == "fake-api-1"
    assert_no_markers(dump(rows), extra=["latitude", "Location", "Field Technician"])


def test_ui_route_messages_are_generic_and_carry_a_reason_code(api, receiver):
    synthetic_candidate(api)
    loc = v2_job(api, LOC_JOB)
    api.post(f"/jobs/{loc}/form/greenhouse")
    r = api.get(f"/jobs/{loc}/route").json()
    text = r["message"] + " ".join(r["steps"])
    for posting_text in ("latitude", "longitude", "Location", "search picker", "question_"):
        assert posting_text not in text, posting_text  # the form's own wording is not echoed
    assert r["reason"] == "unsupported_required_control"


def test_a_full_application_leaves_no_applicant_or_posting_data_in_audit_events(api, receiver):
    app_id = v2_application(api)  # profile, document, form capture, answers, approval
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    rows = audit_rows()
    actions = {r.action for r in rows}
    assert {"application.answer", "job.form_captured", "document.upload"} <= actions
    answer = next(r for r in rows if r.action == "application.answer")
    assert set(answer.meta) == {"field_ref"} and answer.meta["field_ref"].startswith("ref:")
    assert_no_markers(dump(rows))


def test_a_rejected_draft_records_a_reason_code_not_its_content(api, monkeypatch):
    from tests.test_preparation import FakeProvider, new_application, setup_candidate

    setup_candidate(api)
    _, app = new_application(api)
    invented = FakeProvider("I led a team of 40 nurses for 12 years.")
    monkeypatch.setattr(drafting, "get_provider", lambda: invented)
    r = api.post(f"/applications/{app['id']}/answers/why_us/draft")
    assert r.status_code == 422
    (row,) = audit_rows("draft.rejected")
    assert row.meta == {"field_ref": ref("why_us", row.user_id), "reason_code": "invented_numbers"}
    assert "40" not in dump([row]) and "nurses" not in dump([row])


def test_a_created_draft_records_a_field_reference_not_the_question_key(api, monkeypatch):
    from tests.test_preparation import FakeProvider, new_application, setup_candidate

    setup_candidate(api)
    _, app = new_application(api)
    good = FakeProvider("I handled patient intake for 3 doctors and want to keep doing it well.")
    monkeypatch.setattr(drafting, "get_provider", lambda: good)
    assert api.post(f"/applications/{app['id']}/answers/why_us/draft").status_code == 200
    (row,) = audit_rows("draft.created")
    assert set(row.meta) == {"field_ref", "provider", "cost_usd"}
    assert (
        row.meta["field_ref"] == ref("why_us", row.user_id) and row.meta["provider"] == "test-fake"
    )


# -- diagnostics: logs keep the type, never the payload ---------------------------------------


def test_unexpected_runner_errors_are_logged_by_type_only(api, receiver, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    aid = queue(api, v2_application(api))
    secret = "https://boards.example.com/acme/jobs/1 locator('#question_8101') sam@example.com"

    def boom(point):
        if point == "before_navigate":
            raise RuntimeError(secret)

    monkeypatch.setattr(runner, "fault", boom)
    assert runner.run_attempt(aid, "w1") == "error"
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text and "Traceback" not in caplog.text
    assert receiver.ledger()["disclosures"] == []  # stopped before anything was sent


def test_the_egress_proxy_never_logs_destination_hosts(tmp_path, caplog):
    from app.modules.execution.browser import control_request
    from app.modules.execution.sandbox.proxy_service import Registry, control_server

    caplog.set_level(logging.DEBUG)
    token = "test-control-token-" + uuid.uuid4().hex
    path = str(tmp_path / "control.sock")
    srv = control_server(path, Registry(60), token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code, body = control_request(path, token, "POST", "/sessions",
                                     {"allow": [["employer-host.example", 443]]})  # fmt: skip
        assert code == 201 and body["id"]
    finally:
        srv.shutdown()
        srv.server_close()
    assert "1 destination(s)" in caplog.text
    assert "employer-host.example" not in caplog.text and body["token"] not in caplog.text
