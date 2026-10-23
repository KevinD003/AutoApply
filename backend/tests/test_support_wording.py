"""Support wording (providers/wording.py): every label follows from evidence and none claims
more. A provider's support state is derived from its stage and capability levels, a live level
has no label, an API or browser route always carries its evidence, the API serves the labels
(outside the package content, so the package hash is unaffected), and the frontend writes none
of its own. Synthetic data and local fixtures only; nothing here contacts anything external."""

import ast
import pathlib
from dataclasses import replace

import pytest

from app.modules.providers import registry, routing, wording
from app.modules.providers.model import Capability, Kind, Support
from tests.execution_harness import Receiver, synthetic_candidate
from tests.test_greenhouse_adapter import gh_job
from tests.test_greenhouse_dom import v2_job

ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "backend" / "app" / "modules" / "preparation" / "router.py"
FRONTEND = ROOT / "frontend" / "src"
CLAIMS = wording.CLAIMS
# Wording the pages used to write themselves; it now comes from the API.
RETIRED = ["test approximation", "not tested against the live service", "local test fixture only"]
EXPECTED = {
    "fixture_ats": "fixture_only", "greenhouse_hosted": "fixture_only",
    "greenhouse_dom": "observed_read_only", "fake_api": "fixture_only",
    "greenhouse_readonly": "observed_read_only", "freehire_mock": "fixture_only",
    "freehire": "fixture_only", "workday": "planned", "lever": "planned",
    "manual_handoff": "manual",
}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def labels() -> list[str]:
    return [*wording.SUPPORT_LABELS.values(), *wording.ROUTE_LABELS.values(),
            *filter(None, wording.EVIDENCE_LABELS.values()),
            *filter(None, wording.FORM_SOURCE_LABELS.values()),
            *wording.EVIDENCE_CLASS_LABELS.values(),
            *wording.PREREQUISITE_LABELS.values()]  # fmt: skip


# -- derived from evidence -----------------------------------------------------------------------


def test_each_providers_support_state_follows_its_evidence():
    assert {n: wording.support_state(p) for n, p in registry.PROVIDERS.items()} == EXPECTED
    assert all(wording.support_label(p) for p in registry.PROVIDERS.values())


def test_a_live_level_has_no_label_until_one_is_added_deliberately():
    gd = registry.get("greenhouse_dom")
    live_fill = Support(fixture=True, observed=True, live_fill=True)
    live = replace(gd, capabilities={**gd.capabilities, Capability.deterministic_fill: live_fill})
    assert wording.support_state(live) == "live"
    with pytest.raises(KeyError):
        wording.support_label(live)
    for level in wording.LIVE_LEVELS:
        with pytest.raises(KeyError):
            wording.route_label("browser", level)


def test_an_api_or_browser_route_always_carries_its_evidence():
    for route in ("api", "browser"):
        with pytest.raises(ValueError):
            wording.route_label(route, "none")
        assert wording.route_label(route, "fixture").endswith(" (local test fixture only)")
    assert wording.route_label("checkpoint", "none") == wording.ROUTE_LABELS["checkpoint"]
    # Every implemented API or browser provider has labelled evidence for what its route does.
    for spec in registry.PROVIDERS.values():
        route = {Kind.api: "api", Kind.browser: "browser"}.get(spec.kind)
        if route and spec.stage == "implemented":
            d = routing.RouteDecision(route, spec.name, reason="browser_supported")
            assert "local test fixture" in wording.route_label(route, routing.evidence_level(d))


def test_no_label_claims_more_than_its_evidence():
    for label in labels():
        assert not CLAIMS.search(label), label
    for state in ("fixture_only", "observed_read_only"):
        assert "test fixtures only" in wording.SUPPORT_LABELS[state]
    assert "never filled" in wording.SUPPORT_LABELS["observed_read_only"]
    for source in ("fixture", *routing.FORM_SOURCE_ATS):  # the local test stand-ins
        label = wording.FORM_SOURCE_LABELS[source]
        assert "local test" in label.lower() and "(fictional employer)" in label, source


def test_every_form_source_the_capture_code_stores_is_worded():
    """Read from the source: each `source` the capture endpoints assign before storing a form."""
    stored = set()
    for n in ast.walk(ast.parse(CAPTURE.read_text())):
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            t, v = n.targets[0], n.value
            tuples = isinstance(t, ast.Tuple) and isinstance(v, ast.Tuple)
            pairs = zip(t.elts, v.elts, strict=True) if tuples else [(t, v)]
            stored |= {value.value for name, value in pairs
                       if isinstance(name, ast.Name) and name.id == "source"
                       and isinstance(value, ast.Constant)}  # fmt: skip
    assert len(stored) >= 5 and stored == set(wording.FORM_SOURCE_LABELS)


def test_the_frontend_writes_no_support_wording_of_its_own():
    """The pages show the labels the API serves. A page that hard-codes one, or the wording
    they used to write themselves, fails here."""
    sources = [p for p in FRONTEND.rglob("*") if p.suffix in (".ts", ".tsx")]
    assert len(sources) > 10  # the scan read the frontend at all
    for path in sources:
        text = path.read_text().lower()
        for s in [*labels(), *RETIRED]:
            assert s.lower() not in text, (path.relative_to(FRONTEND).as_posix(), s)


# -- served by the API ---------------------------------------------------------------------------


def test_the_api_serves_the_labels(api, receiver):
    summary = api.get("/providers").json()
    assert {n: v["support_state"] for n, v in summary.items()} == EXPECTED
    assert summary["workday"]["support_label"] == "Planned only: no automation exists"
    for p in api.get("/discovery/providers").json():
        assert p["support_label"] == "Local test fixtures only", p["name"]
    synthetic_candidate(api)
    job_id = v2_job(api)
    manual = api.get(f"/jobs/{job_id}/route").json()
    assert (manual["label"], manual["provider_support"]) == (
        wording.ROUTE_LABELS["manual_handoff"], wording.SUPPORT_LABELS["manual"])  # fmt: skip
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    browser = api.get(f"/jobs/{job_id}/route").json()
    assert (browser["label"], browser["provider_support"]) == (
        "Browser adapter (local test fixture only)",
        wording.SUPPORT_LABELS["observed_read_only"],
    )  # fmt: skip
    form = api.get(f"/jobs/{job_id}/form").json()
    assert form["source_label"] == wording.FORM_SOURCE_LABELS["greenhouse_api_dom"]
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    view = api.get(f"/applications/{app_id}/package").json()
    assert view["labels"] == {"form_source": form["source_label"]}  # the same on both pages


def test_wording_never_changes_the_package_or_its_hash(api, receiver, monkeypatch):
    synthetic_candidate(api)
    job_id = gh_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    before = api.get(f"/applications/{app_id}/package").json()
    assert before["labels"]["form_source"] == wording.FORM_SOURCE_LABELS["greenhouse_api"]
    assert "labels" not in before["package"]["content"]
    monkeypatch.setitem(wording.FORM_SOURCE_LABELS, "greenhouse_api", "Reworded for this test")
    after = api.get(f"/applications/{app_id}/package").json()
    assert after["labels"]["form_source"] == "Reworded for this test"
    assert (after["package"]["version"], after["package"]["content_hash"]) == (
        before["package"]["version"], before["package"]["content_hash"])  # fmt: skip
