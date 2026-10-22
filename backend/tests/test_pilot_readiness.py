"""Pilot readiness (providers/readiness.py): the seven conditions for proposing a live
Greenhouse filling pilot are derived from recorded evidence. Today none is met; the owner's
manual observation (Path A) meets none; a condition follows the registry only. Synthetic data
only."""

import pathlib
import re
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import RehearsalRecord
from app.modules.providers import path_a, readiness, registry
from app.modules.providers.evidence import EVIDENCE_CLASSES
from app.modules.providers.model import Capability, Support
from tests.execution_harness import Receiver, queue
from tests.test_greenhouse_dom import v2_application

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


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


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
    assert r.status_code == 200
    assert r.json() == readiness.summary(evidence=readiness.RecordedEvidence(scope="user"))
    api.client.cookies.clear()
    assert api.get("/providers/greenhouse_dom/readiness").status_code == 401


EVERY_COUNT = readiness.RecordedEvidence(
    scope="user", fixture_rehearsals=4, fixture_submissions=4, rehearsals_valid=4,
    rehearsals_valid_with_upload=4, rehearsals_not_valid=4, real_submissions=4)  # fmt: skip


def real_destinations_enabled(monkeypatch):
    """A patched registry only: nothing is enabled anywhere."""
    gd = registry.get("greenhouse_dom")
    monkeypatch.setitem(registry.PROVIDERS, "greenhouse_dom",
                        replace(gd, real_destinations_enabled=True))  # fmt: skip


def met(evidence, observation=None) -> dict:
    return {r["id"]: r["met"] for r in readiness.conditions(observation, evidence=evidence)}


def test_recorded_evidence_meets_nothing_while_real_destinations_are_disabled():
    assert sum(met(EVERY_COUNT).values()) == 0
    assert readiness.summary(None, evidence=EVERY_COUNT)["met"] == 0


def test_a_real_condition_needs_real_destinations_and_evidence_of_its_own_class(monkeypatch):
    real_destinations_enabled(monkeypatch)
    for evidence in (readiness.NO_EVIDENCE, readiness.RecordedEvidence(
            scope="user", fixture_rehearsals=9, fixture_submissions=9,
            rehearsals_valid=9, rehearsals_not_valid=9)):  # fmt: skip
        m = met(evidence)  # fixture evidence, and rehearsals without an upload, meet neither
        assert not m["real_upload"] and not m["real_submission"]
    m = met(readiness.RecordedEvidence(scope="user", rehearsals_valid_with_upload=1))
    assert m["real_upload"] and not m["real_submission"]
    m = met(readiness.RecordedEvidence(scope="user", real_submissions=1))
    assert m["real_submission"] and not m["real_upload"]


def test_each_condition_is_met_only_by_its_own_evidence_class():
    rows = readiness.conditions(None)
    assert {r["id"]: r["meets_by"] for r in rows} == readiness.MEETS_BY
    classes = readiness.evidence_classes()
    assert list(classes) == list(EVIDENCE_CLASSES)
    assert classes["fixture"]["meets"] == [] and classes["public_doc_expectation"]["meets"] == []
    assert classes["rehearsal"]["meets"] == ["real_upload"]
    assert classes["real_submission"]["meets"] == ["real_submission"]
    assert classes["read_only_observation"]["meets"] == ["dropdowns", "location"]


def test_the_documented_evidence_classes_are_the_code():
    text = (ROOT / "docs" / "upload-and-submission-evidence.md").read_text()
    block = text.split("**Evidence classes**", 1)[1].split("\n\n", 2)[1]
    rows = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \| ([^|]+) \|", block, re.M)
    assert [r[0] for r in rows] == list(EVIDENCE_CLASSES)
    for name, meaning, meets in rows:
        assert meaning.strip() == EVIDENCE_CLASSES[name], name
        documented = re.findall(r"`([a-z_]+)`", meets)
        assert documented == readiness.evidence_classes()[name]["meets"], name


def test_readiness_reads_only_the_callers_own_records(api, other_api, receiver):
    app_id = v2_application(api, approve=False)
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert api.post(f"/applications/{app_id}/package/approve", json={
        "version": p["version"], "content_hash": p["content_hash"],
        "scope": "disclose_only"}).status_code == 200  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    mine = api.get("/providers/greenhouse_dom/readiness").json()
    assert mine["scope"] == "user" and mine["met"] == 0
    assert mine["recorded_evidence"]["fixture_rehearsals"] == 1
    assert mine["evidence_classes"]["rehearsal"]["counts"]["valid"] == 0  # a fixture is not one
    theirs = other_api.get("/providers/greenhouse_dom/readiness").json()
    assert theirs["recorded_evidence"]["fixture_rehearsals"] == 0
    # A record edited to claim a real destination no longer holds, and meets nothing.
    with SessionLocal() as db:
        db.scalar(select(RehearsalRecord)).destination_class = "real"
        db.commit()
    mine = api.get("/providers/greenhouse_dom/readiness").json()["recorded_evidence"]
    assert (mine["fixture_rehearsals"], mine["rehearsals_valid"], mine["rehearsals_not_valid"],
            mine["rehearsals_valid_with_upload"]) == (0, 0, 1, 0)  # fmt: skip


def test_a_real_submission_counts_only_after_its_prerequisite_held(api, receiver):
    """Simulated rows (labelled): a confirmed fixture submission edited to claim a real
    destination counts as real-submission evidence only if its send gate recorded that the
    rehearsal prerequisite held, and even then meets nothing while real destinations are off."""
    from app.modules.execution.models import ExecutionAttempt

    app_id = v2_application(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    with SessionLocal() as db:
        att = db.scalar(select(ExecutionAttempt))
        assert att.rehearsal_prerequisite == "not_required"
        att.destination_class = "real"  # simulated
        db.commit()
    mine = api.get("/providers/greenhouse_dom/readiness").json()
    assert mine["recorded_evidence"]["real_submissions"] == 0
    with SessionLocal() as db:
        db.scalar(select(ExecutionAttempt)).rehearsal_prerequisite = "met"  # simulated
        db.commit()
    mine = api.get("/providers/greenhouse_dom/readiness").json()
    assert mine["recorded_evidence"]["real_submissions"] == 1 and mine["met"] == 0
