"""Pilot readiness (providers/readiness.py): the seven conditions for proposing a live
Greenhouse filling pilot are derived from recorded evidence. Today none is met; the owner's
manual observation (Path A) meets none; a condition follows the registry only. Synthetic data
only."""

import pathlib
import re
from dataclasses import replace

from app.modules.providers import path_a, readiness, registry
from app.modules.providers.model import Capability, Support

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "greenhouse-readiness-gap.md"
FAVOURABLE = path_a.validate({  # synthetic: every answer as favourable as the checklist allows
    "status": "recorded", "provenance": path_a.PROVENANCE, "observed_on": "2026-10-22",
    "dropdowns_checked": 2,
    "answers": {"q1_single_click_opens": "yes", "q2_typing_filters": "no",
                "q3_opening_speed": "immediately", "q4_appearance": "popup",
                "q5_option_count": "under_10", "q6_locale_requests_load": "yes",
                "q7_options_shown": "all_at_once", "q8a_phone_group_control": "dialling_code",
                "q8b_other_required_control": "yes_no"},
})  # fmt: skip


def test_no_condition_is_met_today():
    s = readiness.summary()
    assert (s["met"], s["total"], s["proposable"], s["path_a"]) == (0, 7, False, "pending")
    assert [r["id"] for r in s["conditions"]] == [
        "dropdowns", "unmatched_required_controls", "location", "real_upload",
        "real_submission", "pilot_gate", "capability_entry"]  # fmt: skip


def test_the_owners_manual_observation_meets_no_condition():
    s = readiness.summary(FAVOURABLE)
    assert (s["met"], s["proposable"], s["path_a"]) == (0, False, "recorded")
    evidence = {r["id"]: r["evidence"] for r in s["conditions"]}
    assert "Path A: candidate" in evidence["dropdowns"]  # shown beside it, advisory only


def test_a_condition_follows_the_registry_alone(monkeypatch):
    gd = registry.get("greenhouse_dom")
    observed = Support(fixture=True, observed=True)
    raised = replace(gd, capabilities={**gd.capabilities, Capability.custom_dropdowns: observed})
    monkeypatch.setitem(registry.PROVIDERS, "greenhouse_dom", raised)
    met = {r["id"]: r["met"] for r in readiness.conditions(None)}
    assert met["dropdowns"] and sum(met.values()) == 1
    monkeypatch.setattr(readiness, "GATE_PERMISSIONS_RECORDED", True)
    assert sum(r["met"] for r in readiness.conditions(None)) == 2  # still not proposable


def test_the_documented_status_equals_the_computed_one():
    block = DOC.read_text().split("**Status**", 1)[1].split("\n\n", 2)[1]
    documented = dict(re.findall(r"^\| `([a-z_]+)` \| (met|not met) \|", block, re.M))
    computed = {r["id"]: "met" if r["met"] else "not met" for r in readiness.conditions()}
    assert documented == computed


def test_the_api_serves_readiness(api):
    r = api.get("/providers/greenhouse_dom/readiness")
    assert r.status_code == 200 and r.json() == readiness.summary()
    api.client.cookies.clear()
    assert api.get("/providers/greenhouse_dom/readiness").status_code == 401
