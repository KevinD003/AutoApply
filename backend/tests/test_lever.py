"""Lever as a planned provider (F1, F2, F4, F5): identity from known hostnames only, a
specification with no operations or capabilities, a route that says Lever is not supported
yet, and support wording that never claims more. Nothing here contacts Lever: the URLs below
are fictional (company "acme", random posting ids) and are never requested."""

import pathlib
import re

import pytest

from app.modules.jobs.canonical import canonicalize_url, detect_ats
from app.modules.providers import registry, routing, wording
from app.modules.providers.model import ROUTING_CAPABILITIES, Trait, routing_view
from tests.execution_harness import Receiver

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "provider-architecture.md"
POSTING = "0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"
LEVER_URL = f"https://jobs.lever.co/acme/{POSTING}"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.mark.parametrize(
    "url",
    [
        LEVER_URL,
        f"https://jobs.lever.co/Acme/{POSTING}/apply",
        f"https://jobs.lever.co/acme/{POSTING}?lever-source=feed&lever-origin=applied",
        f"https://jobs.eu.lever.co/acme/{POSTING}",
    ],
)
def test_lever_postings_are_identified_from_their_hostname_and_path(url):
    ats = detect_ats(canonicalize_url(url))
    assert (ats.provider, ats.company, ats.requisition_id) == ("lever", "acme", POSTING)
    assert "lever-source" not in canonicalize_url(url)  # a tracking parameter, dropped


@pytest.mark.parametrize(
    "url",
    [
        "https://www.lever.co/",  # the vendor's own site, not a posting
        "https://jobs.lever.co/acme",  # a company page without a posting
        "https://jobs.lever.co/acme/not-a-posting-id",
        f"https://lever.co.example.com/acme/{POSTING}",  # a lookalike host
        f"https://careers.example.com/jobs?lever={POSTING}",
    ],
)
def test_anything_else_is_not_lever(url):
    assert detect_ats(canonicalize_url(url)).provider == "unknown"


def test_lever_is_a_specification_only():
    lv = registry.get("lever")
    assert lv.stage == "planned" and lv.ats == "lever" and not lv.operations
    assert not lv.capabilities and not lv.real_destinations_enabled
    view = routing_view(lv)
    caps = {k: v for k, v in view.items() if not isinstance(ROUTING_CAPABILITIES[k], Trait)}
    assert set(caps.values()) == {"none"}  # nothing is implemented
    traits = {t: lv.trait(t) for t in Trait}
    assert traits[Trait.captcha_possible].value == "expected"  # a checkpoint, never solved
    for t in (Trait.login_required, Trait.multi_step, Trait.manual_verification_required):
        assert traits[t].value == "unknown" and "unverified" in traits[t].note  # never "no"
    assert "not supported" in lv.status
    assert wording.support_label(lv) == "Planned only: no automation exists"


def test_a_lever_job_is_shown_unsupported_and_never_routed_to_greenhouse(api, receiver):
    new = {"url": LEVER_URL, "title": "Engineer", "employer": "Acme Example (fictional)"}
    job = api.post("/jobs", json=new).json()["job"]
    assert job["ats_provider"] == "lever"
    r = api.get(f"/jobs/{job['id']}/route").json()
    assert (r["route"], r["provider"], r["reason"]) == ("manual_handoff", "manual_handoff",
                                                        "planned_adapter_only")  # fmt: skip
    assert r["message"].startswith("Lever applications are not supported yet")
    # Even a form claiming to be Greenhouse cannot pull a Lever job into the Greenhouse adapter.
    d = routing.decide({"origin": "https://jobs.lever.co", "url": LEVER_URL,
                        "submit_url": LEVER_URL, "form_source": "greenhouse_api_dom"})  # fmt: skip
    assert (d.provider, d.reason) == ("manual_handoff", "planned_adapter_only")
    # And its form is never captured as a Greenhouse form (refused without any request).
    assert api.post(f"/jobs/{job['id']}/form/greenhouse").status_code == 400
    assert receiver.ledger()["requests"] == []


def _table(text: str, marker: str) -> list[list[str]]:
    block = text.split(marker, 1)[1]
    rows = [r for r in block.split("\n\n", 2)[1].splitlines() if r.startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows if "---" not in r]


def test_the_documented_routing_vocabulary_is_the_registry():
    """Every provider column of the routing-vocabulary table equals routing_view (first word of
    a cell; "n/a" is not_applicable), so a planned provider can never be shown with more."""
    header, *rows = _table(DOC.read_text(), "Levels: `fixture` = local fixture only")
    columns = {}
    for i, name in enumerate(header[1:], 1):
        key = name.removesuffix(" (planned)")
        columns[i] = ["freehire", "freehire_mock"] if key == "freehire / mock" else [key]
    assert "lever" in [n for names in columns.values() for n in names]
    for row in rows:
        capability = row[0].removesuffix(" *(trait)*")
        for i, names in columns.items():
            cell = "not_applicable" if row[i] == "n/a" else re.split(r"[ (]", row[i])[0]
            for name in names:
                assert routing_view(registry.get(name))[capability] == cell, (capability, name)
