"""Provider model, registry invariants, route selection and the checkpoint policy."""

import pathlib
import uuid
from dataclasses import replace

import pytest

from app.core.config import get_settings
from app.modules.providers import registry, routing
from app.modules.providers.checkpoints import POLICY, CheckpointKind
from app.modules.providers.model import (
    Capability,
    Kind,
    Operation,
    ProviderSpec,
    SpecError,
    Support,
    check_spec,
    matrix,
)
from tests.execution_harness import BASE

GH2 = {"origin": BASE, "url": f"{BASE}/gh2/northwind/jobs/5020001",
       "submit_url": f"{BASE}/gh2/northwind/jobs/5020001/submit",
       "form_source": "greenhouse_api_dom"}  # fmt: skip


# -- registry -------------------------------------------------------------------------------


def test_no_provider_is_enabled_for_real_destinations_or_claims_live_support():
    for spec in registry.PROVIDERS.values():
        assert spec.real_destinations_enabled is False, spec.name
        for cap, s in spec.capabilities.items():
            assert not (s.live_fill or s.live_submit), (spec.name, cap)


def test_real_page_evidence_is_recorded_only_where_it_exists():
    observed = {(p.name, c.value) for p in registry.PROVIDERS.values()
                for c, s in p.capabilities.items() if s.observed}  # fmt: skip
    assert observed == {
        ("greenhouse_dom", "posting_read"), ("greenhouse_dom", "form_extract"),
        ("greenhouse_readonly", "posting_read"), ("greenhouse_readonly", "form_extract"),
        ("greenhouse_readonly", "custom_dropdowns"),
    }  # fmt: skip
    gd = matrix(registry.get("greenhouse_dom"))
    assert gd["custom_dropdowns"] == "fixture" and gd["location_picker"] == "none"


@pytest.mark.parametrize(
    "bad,message",
    [
        (dict(capabilities={Capability.final_submit: Support(fixture=True, observed=True,
                                                             live_submit=True)}),
         "live submission without live filling"),
        (dict(capabilities={Capability.deterministic_fill: Support(fixture=True,
                                                                   live_fill=True)}),
         "live support without real-page evidence"),
        (dict(capabilities={Capability.form_extract: Support(observed=True)}),
         "observed but never implemented locally"),
        (dict(capabilities={Capability.deterministic_fill: Support(
            fixture=True, observed=True, live_fill=True)}),
         "live capabilities while real destinations are disabled"),
        (dict(kind=Kind.discovery), "cannot fill, upload or submit"),
        (dict(capabilities={Capability.official_api_submission: Support(fixture=True)}),
         "a browser provider cannot claim API submission"),
    ],
)  # fmt: skip
def test_spec_invariants_reject_unsupported_claims(bad, message):
    base = registry.get("fixture_ats")
    with pytest.raises(SpecError, match=message):
        check_spec(replace(base, **bad))


def test_freehire_is_a_discovery_provider_only():
    fh = registry.get("freehire_mock")
    assert fh.kind == Kind.discovery and fh.operations == frozenset({Operation.discover})
    assert fh.status == "Potential future discovery provider; not yet connected or validated."


def test_capabilities_are_machine_readable_through_the_api(api):
    body = api.get("/execution/capabilities").json()
    assert body["providers"]["fake_api"]["kind"] == "api"
    assert set(body["providers"]["greenhouse_dom"]["capabilities"]) == {c.value for c in Capability}
    assert api.get("/providers").json()["manual_handoff"]["kind"] == "manual"


# -- routing --------------------------------------------------------------------------------


def test_real_destinations_go_to_a_manual_handoff():
    real = {"origin": "https://job-boards.greenhouse.io",
            "url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "submit_url": "https://job-boards.greenhouse.io/acme/jobs/1/submit",
            "form_source": "greenhouse_api_dom"}  # fmt: skip
    d = routing.decide(real)
    assert (d.route, d.provider) == ("manual_handoff", "manual_handoff")
    assert "Apply on the employer's site" in d.message


def test_no_captured_destination_is_a_manual_handoff():
    d = routing.decide({"origin": BASE, "url": f"{BASE}/x"})
    assert d.route == "manual_handoff" and "no captured destination" in d.message


def test_browser_unless_the_api_is_authorized_configured_and_supported(api, monkeypatch):
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    assert routing.decide(GH2, me).provider == "greenhouse_dom"  # no authorization
    gid = api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE}).json()[
        "id"
    ]
    monkeypatch.setattr(get_settings(), "fake_api_token", "")
    d = routing.decide(GH2, me)
    assert d.provider == "greenhouse_dom" and any(
        "credentials not configured" in s for s in d.steps
    )
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    d = routing.decide(GH2, me)
    assert (d.route, d.provider) == ("api", "fake_api")
    api.delete(f"/api-authorizations/{gid}")
    assert routing.decide(GH2, me).provider == "greenhouse_dom"


def test_observation_and_discovery_providers_are_never_routes(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE})
    for dest in (GH2, {**GH2, "form_source": "html"}, {"origin": BASE}):
        d = routing.decide(dest, me)
        assert registry.get(d.provider).kind in (Kind.api, Kind.browser, Kind.manual)


def test_authorizations_are_user_scoped_and_fixture_only(api, other_api):
    r = api.post("/api-authorizations",
                 json={"provider": "fake_api", "origin": "https://api.example.com"})  # fmt: skip
    assert r.status_code == 400
    r = api.post("/api-authorizations", json={"provider": "freehire_mock", "origin": BASE})
    assert r.status_code == 400  # not an API provider
    gid = api.post("/api-authorizations", json={"provider": "fake_api", "origin": BASE}).json()[
        "id"
    ]
    assert other_api.delete(f"/api-authorizations/{gid}").status_code == 404
    assert other_api.get("/api-authorizations").json() == []
    other = uuid.UUID(other_api.get("/auth/me").json()["user_id"])
    assert routing.decide(GH2, other).provider == "greenhouse_dom"  # the grant is not theirs


# -- checkpoints ----------------------------------------------------------------------------


def test_no_checkpoint_is_ever_completed_by_noefforts():
    assert set(POLICY) == set(CheckpointKind)
    assert all(p.automated is False for p in POLICY.values())
    assert [k for k, p in POLICY.items() if p.resumable_in_noefforts] == [CheckpointKind.email_code]
    assert "does not solve or bypass" in POLICY[CheckpointKind.captcha].user_action


def test_no_solver_or_evasion_code_exists():
    """A static guard: no CAPTCHA-solving service, solver library or stealth plugin anywhere in
    the application code."""
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    banned = ("2captcha", "anticaptcha", "anti-captcha", "capsolver", "capmonster",
              "deathbycaptcha", "playwright_stealth", "puppeteer-extra-plugin-stealth",
              "undetected_chromedriver")  # fmt: skip
    for path in root.rglob("*.py"):
        text = path.read_text().lower()
        assert not any(b in text for b in banned), path


def test_manual_handoff_spec_cannot_fill():
    with pytest.raises(SpecError):
        check_spec(ProviderSpec("x", Kind.manual, "", frozenset({Operation.submit})))
