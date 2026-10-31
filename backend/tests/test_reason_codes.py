"""The route reason-code contract (providers.routing.REASONS).

Every code is a fixed identifier that is safe to record; every code but the fail-closed fallback
is produced by a known path; the routing documentation lists exactly these codes; and a route
shown again unchanged, on the job page or in the discovery view, is audited once. Synthetic data
and local fixtures only: nothing here contacts an employer, an ATS or Freehire."""

import ast
import itertools
import pathlib
import re
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import sanitize
from app.modules.execution import policy
from app.modules.providers import routing
from tests.execution_harness import BASE, Receiver, pilot_on
from tests.test_discovery import feed_copy, rows, run_import
from tests.test_execution_routing import WORKDAY_URL
from tests.test_greenhouse_dom import LOC_JOB, v2_job

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
DOC = ROOT / "docs" / "provider-architecture.md"
LEVER_URL = "https://jobs.lever.co/acme/0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"  # planned
ASHBY_URL = "https://jobs.ashbyhq.com/acme/0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"  # no spec
ELSEWHERE = "https://careers.example.com"  # a non-fixture origin; never contacted
GH2 = {"origin": BASE, "url": f"{BASE}/gh2/northwind/jobs/5020001",
       "submit_url": f"{BASE}/gh2/northwind/jobs/5020001/submit",
       "form_source": "greenhouse_api_dom"}  # fmt: skip
REAL = {"origin": ELSEWHERE, "url": f"{ELSEWHERE}/jobs/1", "submit_url": f"{ELSEWHERE}/jobs/1",
        "form_source": "html"}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", "")  # no credentials unless a test sets


def me(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def authorize_api(api, monkeypatch) -> uuid.UUID:
    """The user's grant for the local fake API, and its credentials configured."""
    assert api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE}).is_success
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    return me(api)


def route_rows(job_id=None) -> list[AuditEvent]:
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.action == "route.decision")
        if job_id is not None:
            q = q.where(AuditEvent.entity_id == str(job_id))
        return list(db.scalars(q.order_by(AuditEvent.created_at)))


# -- each code, through the path that produces it ------------------------------------------------


def _job_route(c, job=None, capture=False) -> str:
    job_id = v2_job(c.api, job) if job else v2_job(c.api)
    if capture:
        assert c.api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    return c.api.get(f"/jobs/{job_id}/route").json()["reason"]


def _no_adapter(c) -> str:
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.check_binding(SimpleNamespace(), REAL)  # queueing or running a manual route
    return e.value.code


def _discovery_view(c, source_job_id: str, closed: bool = False) -> str:
    def close(jobs):  # closed at the source before its first import
        return [{**j, "closed": True} if j["id"] == source_job_id else j for j in jobs]

    uid = me(c.api)
    run_import(uid, feed_copy(c.tmp_path, close) if closed else None)
    row = rows(uid)[source_job_id]
    assert row.job_id is None  # never linked to a tracker job
    return c.api.get(f"/discovery/jobs/{row.id}").json()["route"]["reason"]


def _production(c) -> str:
    c.monkeypatch.setattr(get_settings(), "env", "production")
    return routing.decide(GH2).reason


GH_REAL = "https://job-boards.greenhouse.io/exampleboard/jobs/4000001"  # a fictional board


def _pilot_job(c, *, env=None, isolation=None, owner="synthetic.user@example.com") -> str:
    """D102: a Greenhouse job post routed with the Greenhouse pilot on: on its stand-in board
    host in the test environment, on a (fictional) real board host anywhere else."""
    pilot_on(owner)
    if env is None:
        job_id = v2_job(c.api)
    else:
        new = {"url": GH_REAL, "title": "Engineer", "employer": "Example Board (fictional)"}
        job_id = c.api.post("/jobs", json=new).json()["job"]["id"]
    if env:
        c.monkeypatch.setattr(get_settings(), "env", env)
    if isolation:
        c.monkeypatch.setattr(get_settings(), "browser_isolation", isolation)
    return c.api.get(f"/jobs/{job_id}/route").json()["reason"]


def _pilot_off(c) -> str:
    """A form captured through the pilot, after the owner switched it off."""
    return routing.decide({**GH2, "form_source": "greenhouse_live"}, me(c.api)).reason


PATHS = {
    "api_authorized": lambda c: routing.decide(GH2, authorize_api(c.api, c.monkeypatch)).reason,
    "browser_supported": lambda c: routing.decide(GH2).reason,
    "planned_adapter_only": lambda c: routing.decide({**GH2, "url": WORKDAY_URL}).reason,
    "form_ats_mismatch": lambda c: routing.decide({**GH2, "url": ASHBY_URL}).reason,
    "no_form_captured": lambda c: _job_route(c),
    "unsupported_required_control": lambda c: _job_route(c, LOC_JOB, capture=True),
    "real_destination_disabled": lambda c: routing.decide(REAL).reason,
    "production_disabled": _production,
    "no_captured_destination": lambda c: routing.decide({**GH2, "submit_url": None}).reason,
    "submit_origin_mismatch": lambda c: (
        routing.decide({**GH2, "form_source": "html", "submit_url": f"{ELSEWHERE}/submit"}).reason
    ),
    "no_adapter": _no_adapter,
    "source_record_incomplete": lambda c: _discovery_view(c, "fh-1004"),
    "source_posting_closed": lambda c: _discovery_view(c, "fh-1003", closed=True),
    "live_not_enabled": _pilot_off,
    "live_not_for_this_account": lambda c: _pilot_job(c, owner="someone.else@example.com"),
    "live_needs_production": lambda c: _pilot_job(c, env="development"),
    "live_needs_container": lambda c: _pilot_job(c, env="production", isolation="netns"),
}


def test_every_code_but_the_fallback_has_a_path_and_the_fallback_has_none():
    assert set(PATHS) == set(routing.REASONS) - {routing.FALLBACK_REASON}
    assert routing.FALLBACK_REASON in routing.REASONS  # recorded for anything unknown


@pytest.mark.parametrize("code", sorted(PATHS))
def test_each_code_is_produced_by_its_path(code, api, receiver, monkeypatch, tmp_path):
    c = SimpleNamespace(api=api, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert PATHS[code](c) == code


def test_codes_are_fixed_identifiers_that_are_safe_to_record():
    for code, meaning in routing.REASONS.items():
        assert re.fullmatch(r"[a-z][a-z_]{2,40}", code), code
        assert sanitize({"reason_code": code}) == {"reason_code": code}, code
        assert meaning and meaning == meaning.strip(), code


# -- no path falls through to the fallback ------------------------------------------------------


def _calls(name: str):
    for path in APP.rglob("*.py"):
        for n in ast.walk(ast.parse(path.read_text())):
            if isinstance(n, ast.Call) and name in (getattr(n.func, "id", None),
                                                    getattr(n.func, "attr", None)):  # fmt: skip
                yield path, n


def _arg(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    return next((k.value for k in call.keywords if k.arg == keyword), None)


def test_every_decision_and_refusal_in_the_code_names_a_known_code():
    """Read from the source: a RouteDecision or a refusal that relies on the default code (the
    fallback), or names a code REASONS does not list, fails here."""
    literal = set()
    for path, call in _calls("RouteDecision"):
        reason = _arg(call, 4, "reason")
        assert reason is not None, f"{path.name}:{call.lineno}: a decision without a reason code"
        if isinstance(reason, ast.Constant):
            literal.add(reason.value)
    for path, call in _calls("UnsupportedDestination"):
        code = _arg(call, 1, "code")
        assert isinstance(code, ast.Constant), f"{path.name}:{call.lineno}: no fixed reason code"
        literal.add(code.value)
    assert literal and literal <= set(routing.REASONS), literal - set(routing.REASONS)
    assert routing.FALLBACK_REASON not in literal


@pytest.mark.parametrize("env", ["test", "production"])
def test_no_destination_falls_through_to_the_fallback(env, api, monkeypatch):
    """Every combination of origin, submit address, form source and ATS, with and without an
    API grant: each gets a specific code, never the fallback."""
    user_ids = (None, authorize_api(api, monkeypatch))
    monkeypatch.setattr(get_settings(), "env", env)
    origins = (BASE, ELSEWHERE, None)
    # Every source an adapter executes, the generic ones, and one no adapter executes.
    sources = (None, *sorted(s for s in policy.GENERIC_FORM_SOURCES if s),
               *policy.FORM_SOURCE_ADAPTERS, "example_form")  # fmt: skip
    for origin, user_id, source in itertools.product(origins, user_ids, sources):
        submits = (f"{origin}/submit" if origin else None, f"{ELSEWHERE}/elsewhere", None)
        urls = (f"{origin}/gh2/northwind/jobs/5020001" if origin else None, WORKDAY_URL,
                LEVER_URL, ASHBY_URL, None)  # fmt: skip
        for submit, url in itertools.product(submits, urls):
            dest = {"origin": origin, "url": url, "submit_url": submit, "form_source": source}
            d = routing.decide(dest, user_id)
            assert d.reason in routing.REASONS and d.reason != routing.FALLBACK_REASON, dest
            assert d.authorization in routing.AUTHORIZATION_STATES, dest
            if d.route != "manual_handoff":
                assert env != "production" and origin == BASE, dest  # fixture origins only


def test_the_router_refuses_a_real_destination_even_if_the_adapter_policy_accepts_it(
    monkeypatch,
):
    """The router's own gate, independent of policy.adapter_for: a real origin is a manual
    handoff even if the adapter policy were changed to accept it."""
    monkeypatch.setattr(policy, "adapter_for", lambda destination: "fixture_ats")
    d = routing.decide(REAL)
    assert (d.route, d.provider, d.reason) == ("manual_handoff", "manual_handoff",
                                               "real_destination_disabled")  # fmt: skip
    assert d.message == "Apply on the employer's site."


def test_a_browser_refusal_does_not_block_an_authorized_api_route(api, monkeypatch):
    """The API adapter sends only to the authorized origin's own API, never to the captured
    form's submit address, so a refusal about that address leaves the API route available."""
    user_id = authorize_api(api, monkeypatch)
    for submit in (None, f"{ELSEWHERE}/submit"):
        d = routing.decide({**GH2, "submit_url": submit}, user_id)
        assert (d.route, d.provider, d.reason) == ("api", "fake_api", "api_authorized")
    d = routing.decide({**GH2, "submit_url": None})  # no grant: the browser refusal stands
    assert (d.route, d.reason) == ("manual_handoff", "no_captured_destination")


def test_a_real_destination_is_told_so_before_any_form_step(api, monkeypatch):
    """No captured form could make a real employer's site, or production, automatable, so the
    route says so instead of asking for a form. A local fixture, or a job without an address,
    still goes on to the form."""
    job = {"url": f"{ELSEWHERE}/jobs/1", "title": "Analyst", "employer": "Example Co (fictional)"}
    real = api.post("/jobs", json=job).json()["job"]["id"]
    r = api.get(f"/jobs/{real}/route").json()
    assert (r["route"], r["reason"]) == ("manual_handoff", "real_destination_disabled")
    assert r["message"] == policy.REAL_DESTINATION_DISABLED and "Capture" not in r["message"]
    assert api.post(f"/jobs/{real}/form", json={"fixture": "basic"}).status_code == 201
    assert api.get(f"/jobs/{real}/route").json()["reason"] == "real_destination_disabled"
    plain = api.post("/jobs", json={"title": "Clerk", "employer": "Example Co (fictional)"})
    assert api.get(f"/jobs/{plain.json()['job']['id']}/route").json()["reason"] == (
        "no_form_captured"
    )
    assert api.get(f"/jobs/{v2_job(api)}/route").json()["reason"] == "no_form_captured"
    monkeypatch.setattr(get_settings(), "env", "production")
    local = SimpleNamespace(url=GH2["url"], ats_provider=None)
    d = routing.route_for_job(None, local)  # refused before any form is looked up
    assert (d.reason, d.message) == ("production_disabled", policy.PRODUCTION_DISABLED)


def test_the_documentation_lists_exactly_the_reason_codes():
    block = DOC.read_text().split("**Reason codes**", 1)[1].split("\n\n**", 1)[0]
    documented = re.findall(r"^\| `([a-z_]+)` \|", block, re.M)
    assert len(documented) == len(set(documented))
    assert set(documented) == set(routing.REASONS)


# -- auditing: changes only, wherever the route is shown -----------------------------------------


def test_a_repeated_route_check_is_recorded_once_and_each_change_again(api, receiver, monkeypatch):
    job_id = v2_job(api)
    check = lambda: api.get(f"/jobs/{job_id}/route").json()["reason"]  # noqa: E731
    assert [check(), check(), check()] == ["no_form_captured"] * 3
    assert [r.meta["reason_code"] for r in route_rows(job_id)] == ["no_form_captured"]
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    assert check() == "browser_supported"
    grant = api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE}).json()
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    assert [check(), check()] == ["api_authorized"] * 2
    assert api.delete(f"/api-authorizations/{grant['id']}").is_success
    assert [check(), check()] == ["browser_supported"] * 2
    got = [(r.meta["reason_code"], r.meta["api_grant"]) for r in route_rows(job_id)]
    assert got == [
        ("no_form_captured", "not_applicable"),
        ("browser_supported", "none"),
        ("api_authorized", "granted"),
        ("browser_supported", "none"),  # as before the grant, but a change from the last one
    ]


def test_the_discovery_view_records_a_linked_jobs_route_as_the_job_page_does(api, other_api):
    uid = me(api)
    run_import(uid)
    r = rows(uid)
    linked, incomplete = r["fh-1001"], r["fh-1004"]
    view = api.get(f"/discovery/jobs/{linked.id}").json()["route"]
    assert view == {"route": "manual_handoff", "provider": "manual_handoff",
                    "message": "Capture the application form first.",
                    "reason": "no_form_captured", "authorization": "not_applicable",
                    "evidence": "none", "label": "Manual: apply on the employer's site",
                    "provider_support": "Manual: you apply on the employer's site"}  # fmt: skip
    assert [x.meta["reason_code"] for x in route_rows(linked.job_id)] == ["no_form_captured"]
    page = api.get(f"/jobs/{linked.job_id}/route").json()
    assert {k: page[k] for k in view} == view  # the same decision, from the job page...
    assert len(route_rows(linked.job_id)) == 1  # ...is not recorded again
    assert api.get(f"/discovery/jobs/{incomplete.id}").json()["route"]["reason"] == (
        "source_record_incomplete"
    )
    assert other_api.get(f"/discovery/jobs/{linked.id}").status_code == 404
    assert len(route_rows()) == 1  # a row without a job, or another user's view, records nothing
