"""D137: the evidence of what reached the employer survives any failure after it. Each disclosure
(an acknowledged upload, a location search, a section control) is recorded the moment it is made,
fenced by the attempt's generation, not after filling ends; a failure during an upload counts
that document as possibly received. Faults use NOEFFORTS_FAULT (honoured only in tests). What
reached the employer is read from the receiver's own ledger; local fixtures only."""

import http.client
import json
import time
import urllib.error
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.urlsafety import UnsafeURL
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.adapters import fake_api, fixture_ats
from app.modules.execution.models import Evidence, ExecutionAttempt
from tests.execution_harness import (
    Receiver,
    prepared_application,
    queue,
    run_worker_process,
)
from tests.test_api_provider import TOKEN, api_application
from tests.test_greenhouse_adapter import gh_application
from tests.test_greenhouse_dom import v2_application
from tests.test_workday_adapter import workday_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)


def disclosures(aid: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(Evidence)
            .where(Evidence.attempt_id == uuid.UUID(aid), Evidence.kind == "disclosure")
            .order_by(Evidence.created_at)
        ).all()
        return [r.data for r in rows]


def finished(aid: str) -> tuple[str, str]:
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, uuid.UUID(aid))
        return att.state, att.outcome_detail or ""


def resume_sha(api, app_id: str) -> str:
    """The approved résumé's digest. Read it before the run: reading the package afterwards
    prepares it again, which moves a stopped application back to awaiting approval."""
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return next(d["sha256"] for d in content["documents"] if d["field"] == "resume")


def uploads(receiver) -> list[dict]:
    return [d for d in receiver.ledger()["disclosures"] if d["kind"] == "upload"]


def expire_lease(aid: str) -> None:
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()


# ------------------------------------------------------------------ the generic form


def test_a_completed_run_records_each_disclosure_once(api, receiver):
    app_id = prepared_application(api, receiver)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert disclosures(aid) == [{"field": "resume", "ack": "attachment_shown", "sha256": sha}]


def test_an_unexpected_error_after_an_upload_keeps_its_evidence(api, receiver, monkeypatch):
    app_id = prepared_application(api, receiver)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "after_disclosure_recorded=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    led = receiver.ledger()
    assert led["accepted"] == 0 and len(led["disclosures"]) == 1  # the résumé reached it
    assert disclosures(aid) == [{"field": "resume", "ack": "attachment_shown", "sha256": sha}]
    state, outcome = finished(aid)
    assert state == "abandoned" and "internal error (RuntimeError)" in outcome
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    monkeypatch.delenv("NOEFFORTS_FAULT")
    assert runner.run_attempt(aid, "w2") == "ignored"  # never retried
    assert receiver.ledger()["accepted"] == 0


def test_a_worker_killed_after_an_upload_leaves_its_evidence(api, receiver):
    app_id = prepared_application(api, receiver)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault="after_disclosure_recorded=exit")
    assert r.returncode == 137
    recorded = [{"field": "resume", "ack": "attachment_shown", "sha256": sha}]
    assert disclosures(aid) == recorded  # written before the worker died
    led = receiver.ledger()
    assert led["accepted"] == 0 and len(led["disclosures"]) == 1
    expire_lease(aid)
    assert svc.sweep()["abandoned"] == 1
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert disclosures(aid) == recorded and receiver.ledger()["accepted"] == 0


def test_an_error_during_an_upload_counts_the_document_as_possibly_received(
    api, receiver, monkeypatch
):
    app_id = prepared_application(api, receiver)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "during_upload=raise")  # once the file was handed over
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert disclosures(aid) == [{"field": "resume", "ack": "none", "sha256": sha}]
    state, outcome = finished(aid)
    assert state == "abandoned" and "a document upload was interrupted" in outcome
    # Whether the page's own upload finished before the browser closed is exactly what NoEfforts
    # cannot know: hence "possibly received". Nothing was submitted either way.
    led = receiver.ledger()
    assert led["accepted"] == 0 and len(led["disclosures"]) <= 1


# ------------------------------------------------------------------ Greenhouse's id-only pages


def test_on_greenhouse_pages_an_error_after_an_upload_keeps_its_evidence(
    api, receiver, monkeypatch
):
    app_id = v2_application(api)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "after_disclosure_recorded=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    assert disclosures(aid) == [{"field": "resume", "ack": "attachment_shown", "sha256": sha}]
    assert len(uploads(receiver)) == 1 and receiver.ledger()["accepted"] == 0
    assert finished(aid)[0] == "abandoned"


# ------------------------------------------------------------------ the authorized API route


def test_through_the_api_an_error_after_a_document_keeps_its_evidence(api, receiver, monkeypatch):
    app_id = api_application(api)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "after_disclosure_recorded=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    assert disclosures(aid) == [
        {"route": "api", "kind": "application_draft"},
        {"field": "resume", "sha256": sha, "route": "api", "ack": "digest_matched"},
    ]
    assert finished(aid)[0] == "abandoned"
    assert [json.loads(d["detail"]) for d in uploads(receiver)] == [
        {"field": "resume", "sha256": sha}
    ]


def test_an_api_upload_without_an_answer_counts_as_possibly_received(api, receiver, monkeypatch):
    app_id = api_application(api)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "during_upload=raise")  # after the request was sent
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert disclosures(aid) == [
        {"route": "api", "kind": "application_draft"},
        {"field": "resume", "sha256": sha, "route": "api", "ack": "no_response"},
    ]
    state, outcome = finished(aid)
    assert state == "abandoned" and "the API did not answer a document upload" in outcome
    deadline = time.monotonic() + 5
    while not uploads(receiver) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert len(uploads(receiver)) == 1  # it did arrive: the evidence was right to count it


@pytest.mark.parametrize(
    ("make", "field"),
    [(v2_application, "resume"), (workday_application, "resume"), (gh_application, "resume")],
    ids=["greenhouse_by_id", "workday_style", "greenhouse_first_fixture"],
)
def test_on_each_page_adapter_an_error_during_an_upload_counts_it(
    api, receiver, monkeypatch, make, field
):
    app_id = make(api)
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    sha = next(d["sha256"] for d in content["documents"] if d["field"] == field)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "during_upload=raise")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert disclosures(aid) == [{"field": field, "ack": "none", "sha256": sha}]
    state, outcome = finished(aid)
    assert state == "abandoned" and "a document upload was interrupted" in outcome
    assert receiver.ledger()["accepted"] == 0
    monkeypatch.delenv("NOEFFORTS_FAULT")
    assert runner.run_attempt(aid, "w2") == "ignored"


def test_a_failure_before_the_document_is_handed_over_stays_an_internal_error(
    api, receiver, monkeypatch, caplog
):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)

    def broken(self, page, key, loc):
        raise KeyError("no such document")  # an adapter or package bug, before set_input_files

    monkeypatch.setattr(fixture_ats.FixtureAtsAdapter, "_attach_file", broken)
    assert runner.run_attempt(aid, "w1") == "error"
    assert disclosures(aid) == []  # nothing was handed to the page: no disclosure is claimed
    state, outcome = finished(aid)
    assert state == "abandoned" and "internal error (KeyError)" in outcome
    assert receiver.ledger()["disclosures"] == []


def test_an_upload_stop_keeps_the_type_and_place_of_what_caused_it(
    api, receiver, monkeypatch, caplog
):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "during_upload=raise")
    with caplog.at_level("WARNING", logger="noefforts.execution"):
        assert runner.run_attempt(aid, "w1") == "abandoned"
    (line,) = [
        r.getMessage() for r in caplog.records if "stopped after disclosure by" in r.getMessage()
    ]
    assert "RuntimeError" in line and "injected fault" not in line  # the type, never the message
    # ... and where: the fault raised in faults.py, inside the generic form's upload.
    assert "faults.py:" in line and ":fault" in line and "fixture_ats.py:" in line


@pytest.mark.parametrize(
    ("mode", "ack", "documents", "reason"),
    [
        ("fapi_redirect_draft", "no_response", 0, "the API did not answer the application draft"),
        ("fapi_draft_error", "not_created", 0, "the API did not create the application"),
        ("fapi_redirect_document", None, 1, "the API did not answer a document upload"),
    ],
)
def test_through_the_api_a_request_answered_badly_after_it_arrived_is_recorded(
    api, receiver, mode, ack, documents, reason
):
    app_id = api_application(api)
    sha = resume_sha(api, app_id)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    draft = {"route": "api", "kind": "application_draft"}
    if documents:
        want = [draft, {"field": "resume", "sha256": sha, "route": "api", "ack": "no_response"}]
    else:
        want = [draft | {"ack": ack}]
    assert disclosures(aid) == want
    state, outcome = finished(aid)
    assert state == "abandoned" and reason in outcome
    led = receiver.ledger()
    kinds = sorted(d["kind"] for d in led["disclosures"])
    assert kinds == ["api_draft"] + ["upload"] * documents  # it did arrive: rightly recorded
    assert led["accepted"] == 0


@pytest.mark.parametrize(
    ("error", "arrived"),
    [
        (fake_api.ApiRefused("the API destination is not enabled"), False),
        (fake_api.ApiRefused("API credentials are not configured"), False),
        (UnsafeURL("not a local test fixture origin"), False),
        (urllib.error.URLError(ConnectionRefusedError(111, "refused")), False),
        (fake_api._Redirected("the API redirected (HTTP 307); not followed"), True),
        (urllib.error.URLError(ConnectionResetError(104, "reset")), True),
        (TimeoutError("timed out"), True),
        (http.client.RemoteDisconnected("closed"), True),
        (json.JSONDecodeError("Expecting value", "x", 0), True),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, BaseException) else str(v),
)
def test_only_a_request_refused_before_sending_counts_as_never_arrived(error, arrived):
    """D137: what the API route records as possibly received. A refusal before anything was
    sent stays a refusal (nothing recorded); anything after sending may have arrived."""
    assert fake_api._may_have_arrived(error) is arrived
