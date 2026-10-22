"""Error boundaries (Phase 11A): internal failures reach users, attempt outcomes, audit events and
logs only as generic wording plus a fixed reason code. Synthetic data and local fixtures only;
nothing contacts anything external."""

import io
import json
import logging
import re
import subprocess
import types
import urllib.error
import urllib.request

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.errors import UNEXPECTED_ERROR
from app.modules.audit.models import AuditEvent
from app.modules.execution import browser, runner
from app.modules.execution.browser import IsolationUnavailable, RemoteBrowser
from tests.execution_harness import Receiver, attempt, queue
from tests.test_greenhouse_adapter import gh_job
from tests.test_greenhouse_dom import v2_application, v2_job

# Synthetic stand-ins for what internal failures can carry: a service address, a response body,
# a posting's question key, a token-like string and traceback-shaped text.
URL = "http://browser-runner.internal:9330/sessions/abc"
BODY = '{"error": "session token tok_live_SYNTHETIC rejected", "field": "question_8101"}'
TRACE = 'Traceback (most recent call last):\n  File "/app/x.py", line 1, in <module>'
MARKERS = ["browser-runner.internal", "9330", "tok_live_SYNTHETIC", "question_8101", "Traceback",
           "/app/x.py", "127.0.0.1:8799", "/gh2/", "/gh/"]  # fmt: skip
RAW = f"{URL} refused: {BODY}\n{TRACE}"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def clean(text: str) -> None:
    for m in MARKERS:
        assert m not in text, m


def app_logs(caplog) -> str:
    """What NoEfforts itself logged (the test client's own request log is not the app's)."""
    return "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))


def audit_dump() -> str:
    with SessionLocal() as db:
        return json.dumps([[r.action, r.meta] for r in db.scalars(select(AuditEvent))])


# -- 1. execution and isolation failures ------------------------------------------------------


def test_an_isolation_failure_reaches_the_user_as_a_code_only(api, receiver, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    app_id = v2_application(api)
    aid = queue(api, app_id)

    def refuse(*a, **kw):
        raise IsolationUnavailable(RAW, "runner_refused", 503)

    monkeypatch.setattr(runner, "browser_session", refuse)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert attempt(aid).outcome_detail == (
        "Stopped before sending anything: browser isolation unavailable (runner_refused)"
    )
    shown = api.get(f"/applications/{app_id}/attempts").text
    assert "runner_refused" in shown
    for text in (shown, audit_dump(), app_logs(caplog)):
        clean(text)
    assert receiver.ledger()["disclosures"] == []


def test_a_refusing_runner_keeps_neither_its_address_nor_its_body(monkeypatch):
    class Opener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError(URL, 503, "unavailable", {}, io.BytesIO(BODY.encode()))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(IsolationUnavailable) as e:
        RemoteBrowser._call(URL, "X-Runner-Token", "t", "GET", "/health")
    assert (e.value.code, e.value.status) == ("runner_refused", 503)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    clean(str(e.value))

    class Down:
        def open(self, req, timeout):
            raise OSError(f"cannot reach {URL}")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: Down())
    with pytest.raises(IsolationUnavailable) as e:
        RemoteBrowser._call(URL, "X-Runner-Token", "t", "GET", "/health")
    assert e.value.code == "runner_unreachable"
    clean(str(e.value))


def test_a_refusing_egress_proxy_and_failing_namespaces_keep_no_output(monkeypatch):
    remote = RemoteBrowser.__new__(RemoteBrowser)
    remote.s = types.SimpleNamespace(egress_control_socket="/x", egress_control_token="t")
    monkeypatch.setattr(browser, "control_request", lambda *a, **kw: (500, {"error": RAW}))
    with pytest.raises(IsolationUnavailable) as e:
        remote._proxy("POST", "/sessions", {})
    assert (e.value.code, e.value.status) == ("proxy_refused", 500)
    clean(str(e.value))

    failed = subprocess.CompletedProcess([], 1, b"", RAW.encode())
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: failed)
    with pytest.raises(IsolationUnavailable) as e:
        browser.isolation_self_check()
    assert e.value.code == "namespaces_unavailable"
    clean(str(e.value))


# -- 2. form capture and form drift -----------------------------------------------------------


@pytest.mark.parametrize(
    "mode, job, code",
    [
        ("gh_drift", gh_job, "form_sources_disagree"),
        ("gh2_duplicate_id", v2_job, "controls_do_not_match"),
        ("gh2_label_mismatch", v2_job, "controls_do_not_match"),
    ],
)
def test_a_form_capture_mismatch_shows_a_generic_message_and_a_code(api, receiver, mode, job, code):
    job_id = job(api)
    receiver.config(mode=mode)
    r = api.post(f"/jobs/{job_id}/form/greenhouse")
    assert r.status_code == 409
    assert "unsupported or incomplete" in r.text and f"(reason: {code})" in r.text
    clean(r.text)
    clean(audit_dump())


# -- 3. the global exception boundary ---------------------------------------------------------


def _jobs_route(api):
    return f"/jobs/{v2_job(api)}/route", "app.modules.providers.routing.route_for_job"


def _attempts(api):
    return (
        f"/applications/{v2_application(api)}/attempts",
        "app.modules.execution.router._owned_app",
    )


def _auth(api):
    # A failure inside authentication itself: it must fail closed, returning nothing.
    return "/jobs", "app.modules.identity.deps.hash_token"


@pytest.mark.parametrize("target", [_jobs_route, _attempts, _auth])
def test_an_unexpected_error_is_a_generic_500_logged_by_type(api, receiver, monkeypatch, caplog,
                                                             target):  # fmt: skip
    caplog.set_level(logging.DEBUG)
    url, where = target(api)

    def boom(*a, **kw):
        raise RuntimeError(RAW)

    monkeypatch.setattr(where, boom)
    r = api.get(url)
    assert r.status_code == 500 and r.json() == {"detail": UNEXPECTED_ERROR}
    assert r.headers.get("x-content-type-options") == "nosniff"  # still inside the app's layers
    # The route template ({placeholders}), never the raw path with its identifiers.
    assert re.search(r"unhandled RuntimeError in GET /[a-z/_{}]*$", app_logs(caplog), re.M)
    for text in (r.text, app_logs(caplog)):
        clean(text)


def test_expected_errors_keep_their_status_and_own_messages(api, other_api, receiver):
    from fastapi.testclient import TestClient

    from app.main import create_app

    job_id = v2_job(api)
    anonymous = TestClient(create_app(), base_url="http://testserver/api")
    assert anonymous.get("/jobs").status_code == 401  # authentication fails closed
    assert other_api.get(f"/jobs/{job_id}/route").status_code == 404  # tenancy fails closed
    r = api.get("/jobs", params={"limit": 0})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)  # validation
    real = api.post("/jobs", json={"url": "https://job-boards.greenhouse.io/acme/jobs/4567890",
                                   "title": "Any role"}).json()["job"]["id"]  # fmt: skip
    r = api.post(f"/jobs/{real}/form/greenhouse")
    assert r.status_code == 409 and "not enabled" in r.text  # a NoEfforts refusal
