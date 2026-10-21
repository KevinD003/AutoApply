"""Execution routing (providers.routing): authorized API, then a supported browser adapter, then
a checkpoint or manual handoff; the routing vocabulary and execution interface (providers.model)
as views over evidence-levelled capabilities. Local fixtures only: the receiver and its fake API
are labelled stand-ins, no real employer or ATS is contacted, and no live API is claimed."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.execution import policy, runner
from app.modules.preparation.models import JobForm
from app.modules.providers import registry, routing
from app.modules.providers.checkpoints import POLICY, CheckpointKind
from app.modules.providers.model import INTERFACE, ROUTING_CAPABILITIES, Trait, routing_view
from tests.execution_harness import BASE, Receiver, attempt, queue, synthetic_candidate
from tests.test_greenhouse_adapter import gh_application
from tests.test_greenhouse_dom import LOC_JOB, v2_application, v2_job

WORKDAY_URL = "https://acme-example.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R-1234"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", "")  # no credentials unless a test sets


def job_route(api, job_id) -> dict:
    r = api.get(f"/jobs/{job_id}/route")
    assert r.status_code == 200, r.text
    return r.json()


def job_of(api, app_id) -> str:
    return api.get(f"/applications/{app_id}").json()["job"]["id"]


def disclosures(receiver) -> list:
    return receiver.ledger()["disclosures"]


# -- vocabulary and interface ------------------------------------------------------------------


def test_every_provider_declares_the_routing_vocabulary_without_live_claims():
    for spec in registry.PROVIDERS.values():
        view = routing_view(spec)
        assert set(view) == set(ROUTING_CAPABILITIES), spec.name
        assert not {"live_fill", "live_submit"} & set(view.values()), spec.name
    gd = routing_view(registry.get("greenhouse_dom"))
    assert (gd["browser_fill"], gd["custom_dropdown"], gd["location_picker"]) == (
        "fixture", "fixture", "none")  # fmt: skip
    assert gd["public_schema_read"] == "observed" and gd["API_submission"] == "none"
    assert gd["CAPTCHA_possible"] == "unknown"  # none seen; never claimed either way
    assert routing_view(registry.get("fake_api"))["API_submission"] == "fixture"
    assert routing_view(registry.get("freehire"))["browser_fill"] == "none"


def test_workday_is_a_specification_only():
    wd = registry.get("workday")
    assert wd.stage == "planned" and wd.ats == "workday" and not wd.operations
    view = routing_view(wd)
    caps = {k: v for k, v in view.items() if not isinstance(ROUTING_CAPABILITIES[k], Trait)}
    assert set(caps.values()) == {"none"}  # nothing is implemented
    traits = [view[k] for k in ("login_required", "manual_verification_required",
                                "CAPTCHA_possible", "multi_step")]  # fmt: skip
    assert traits == ["expected"] * 4  # the specification's expectations, not observations
    assert "not supported" in wd.status


def test_interface_is_implemented_only_where_the_operations_exist():
    names = set(INTERFACE)
    assert names == {"inspect_application", "extract_form_schema", "prepare_application",
                     "validate_application", "request_user_action", "upload_documents",
                     "submit_application", "collect_confirmation_evidence",
                     "reconcile_unknown_outcome"}  # fmt: skip
    summary = registry.summary()
    assert all(summary["greenhouse_dom"]["interface"][n] for n in names - {
        "reconcile_unknown_outcome"})  # browser outcomes are reconciled by the user  # fmt: skip
    assert summary["fake_api"]["interface"]["reconcile_unknown_outcome"] is True
    assert [n for n, ok in summary["manual_handoff"]["interface"].items() if ok] == [
        "request_user_action"]  # fmt: skip
    assert not any(summary["workday"]["interface"].values())
    assert not any(summary["freehire"]["interface"].values())


# -- route selection ---------------------------------------------------------------------------


def test_route_selection_api_then_browser_then_manual(api, receiver, monkeypatch):
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert job_route(api, job_id)["message"] == "Capture the application form first."
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    r = job_route(api, job_id)
    assert (r["route"], r["provider"]) == ("browser", "greenhouse_dom")
    # The API route needs the user's grant AND configured credentials AND declared support.
    api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE})
    assert job_route(api, job_id)["provider"] == "greenhouse_dom"  # no credentials yet
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    r = job_route(api, job_id)
    assert (r["route"], r["provider"]) == ("api", "fake_api")
    real_job = {"url": "https://job-boards.greenhouse.io/acme/jobs/1", "title": "Analyst",
                "employer": "Acme"}  # fmt: skip
    real = api.post("/jobs", json=real_job).json()["job"]["id"]
    r = job_route(api, real)
    assert r["route"] == "manual_handoff"  # nothing captured or enabled for a real origin


def test_a_known_api_connector_is_never_selected_without_explicit_authorization(
    api, receiver, monkeypatch
):
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")  # credentials only
    app_id = v2_application(api, approve=False)
    assert job_route(api, job_of(api, app_id))["provider"] == "greenhouse_dom"
    with SessionLocal() as db:
        from app.modules.applications.models import Application

        user_id = db.get(Application, uuid.UUID(app_id)).user_id
    dest = api.get(f"/applications/{app_id}/package").json()["package"]["content"]["destination"]
    d = routing.decide(dest, user_id)
    assert d.provider == "greenhouse_dom"
    assert any("no active authorization from the user" in s for s in d.steps)
    assert not any(r["path"].startswith("/fapi/") for r in receiver.ledger()["requests"])


def test_an_unsupported_required_control_is_a_checkpoint_before_disclosure(api, receiver):
    synthetic_candidate(api)
    job_id = v2_job(api, LOC_JOB)  # a location question with page-managed hidden coordinates
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    r = job_route(api, job_id)
    assert (r["route"], r["provider"]) == ("checkpoint", "manual_handoff")
    assert "required controls NoEfforts cannot fill" in r["message"]
    assert "Nothing is sent" in r["message"] and r["reason"] == "unsupported_required_control"
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert {"latitude", "longitude"} <= set(p["content"]["unresolved"])  # never guessed
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code != 200  # cannot be approved, so nothing can be queued
    assert disclosures(receiver) == []


def test_an_adapter_version_mismatch_blocks_queueing_and_execution(api, receiver, monkeypatch):
    app_id = v2_application(api)  # approved for greenhouse_dom at its current version
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_dom", "greenhouse-dom-99")
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "changed after you approved" in r.text
    monkeypatch.undo()
    app_id = v2_application(api, worked_before="Yes")  # a fresh approval, then queued
    aid = queue(api, app_id)
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_dom", "greenhouse-dom-99")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "execution method changed" in attempt(aid).outcome_detail
    assert disclosures(receiver) == [] and receiver.ledger()["accepted"] == 0


# -- job sources and other ATSs ----------------------------------------------------------------


def test_freehire_imports_are_never_treated_as_form_schemas(api, receiver, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "discovery_providers", ["freehire"])
    monkeypatch.setattr(s, "freehire_base_url", f"{BASE}/freehire-fixture")
    assert api.post("/discovery/import", json={"provider": "freehire"}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count(JobForm.id))) == 0  # a listing is not a form
    rows = [r for r in api.get("/discovery/jobs").json() if r["job_id"]]
    assert rows
    for row in rows:
        r = job_route(api, row["job_id"])
        assert r["route"] == "manual_handoff"
        assert r["message"] == "Capture the application form first."
    routes = {r["route"] for r in receiver.ledger()["freehire_requests"]}
    assert routes == {"search"}  # Freehire's apply-form endpoint is never asked
    from app.modules.discovery.provider import FreehireApiProvider

    public = [m for m in dir(FreehireApiProvider) if not m.startswith("_")]
    assert not any("form" in m for m in public)  # it has no way to fetch an application form


def test_a_workday_job_is_shown_unsupported_never_routed_to_greenhouse(api, receiver):
    job = api.post("/jobs", json={"url": WORKDAY_URL, "title": "Engineer",
                                  "employer": "Acme Example"}).json()["job"]  # fmt: skip
    assert job["ats_provider"] == "workday"
    r = job_route(api, job["id"])
    assert (r["route"], r["provider"], r["stage"]) == ("manual_handoff", "manual_handoff",
                                                       "implemented")  # fmt: skip
    assert "Workday applications are not supported yet" in r["message"]
    # Even a form claiming to be Greenhouse cannot pull a Workday job into the Greenhouse adapter.
    origin = "https://acme-example.wd5.myworkdayjobs.com"
    d = routing.decide({"origin": origin, "url": WORKDAY_URL, "submit_url": WORKDAY_URL,
                        "form_source": "greenhouse_api_dom"})  # fmt: skip
    assert d.provider == "manual_handoff" and "Workday" in d.message
    # And its form is never captured as a Greenhouse form (refused without any request).
    assert api.post(f"/jobs/{job['id']}/form/greenhouse").status_code == 400
    assert receiver.ledger()["requests"] == []


def test_a_form_from_another_ats_is_refused():
    url = "https://jobs.lever.co/acme/0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"
    d = routing.decide({"origin": "https://jobs.lever.co", "url": url, "submit_url": url,
                        "form_source": "greenhouse_api_dom"})  # fmt: skip
    assert d.provider == "manual_handoff" and "does not belong" in d.message


# -- checkpoints -------------------------------------------------------------------------------


def test_a_captcha_becomes_a_user_action_never_an_automated_solve(api, receiver):
    app_id = gh_application(api)  # the fixture whose page can show a CAPTCHA (a labelled mode)
    aid = queue(api, app_id)
    receiver.config(mode="captcha")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    a = attempt(aid)
    assert "does not solve" in a.outcome_detail
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    assert disclosures(receiver) == [] and receiver.ledger()["accepted"] == 0
    assert POLICY[CheckpointKind.captcha].automated is False
    assert all(not p.automated for p in POLICY.values())
