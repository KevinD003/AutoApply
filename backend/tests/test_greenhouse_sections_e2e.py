"""D120 end-to-end: a captured Greenhouse stand-in that carries a structured Education section is
frozen into the package, approved, and driven by the REAL runner against the independent receiver.
The receiver records what actually arrives (each combobox's option id, each text value), parsed
from the DOM by its own generic submit -- never from the planner under test.

Covers your #1: values reach the correct fields and match the approved package; multiple rows do
not overwrite one another; a rehearsal never submits; a separately approved submission sends once;
and a real (non-stand-in) destination refuses the legacy-only section before anything is entered.
Synthetic data only; nothing contacts a real board.
"""

import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.execution import policy, runner
from app.modules.execution.adapters import greenhouse_dom as gd_adapter
from app.modules.execution.models import ExecutionAttempt
from tests.execution_harness import Receiver, queue
from tests.test_greenhouse_dom import synthetic_candidate, v2_job


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    receiver.config(mode="gh2_sections")  # the captured and served form carries the section


def _approve_education(api, institution, degree, field, start, end):
    r = api.post(
        "/profile/education",
        json={"institution": institution, "degree": degree, "field_of_study": field,
              "start_date": start, "end_date": end},
    ).json()  # fmt: skip
    assert api.post(f"/profile/education/{r['id']}/approve").status_code == 200


def sections_application(api, *, two_rows=False, approve=True, scope=None) -> str:
    synthetic_candidate(api)
    _approve_education(api, "State University", "Bachelor's Degree", "Computer Science",
                       "2014-09-01", "2018-05-01")  # fmt: skip
    if two_rows:
        _approve_education(api, "Metro College", "Master's Degree", "Mathematics",
                           "2019-09-01", "2021-06-01")  # fmt: skip
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {"preferred_name": {"text": "Sammy"}, "question_8101": {"label": "Yes"},
                       "question_8104": {"label": "No"}}.items():  # fmt: skip
        assert api.put(f"/applications/{app_id}/answers",
                       json={"key": key, "value": value}).status_code == 200  # fmt: skip
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert "sections" in p["content"], p["content"].get("validation_errors")
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    if approve:
        body = {"version": p["version"], "content_hash": p["content_hash"]}
        if scope:
            body["scope"] = scope
        assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200
    return app_id


def _row0(api, app_id) -> dict:
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return content["sections"][0]["rows"][0]["fields"]


def test_education_section_values_reach_the_receiver_and_match_the_package(api, receiver):
    app_id = sections_application(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = receiver.ledger()["acceptances"][0]["fields"]
    # The receiver independently recorded each combobox option id and text value from the DOM.
    assert fields["school--0"] == "sch_state"
    assert fields["degree--0"] == "deg_bach"
    assert fields["discipline--0"] == "dis_cs"
    assert fields["start-month--0"] == "9" and fields["start-year--0"] == "2014"
    # ... and they equal the ids the approved package froze (receiver == approved package).
    row = _row0(api, app_id)
    assert fields["school--0"] == row["school_name_id"]["value"]["id"]
    assert fields["degree--0"] == row["degree_id"]["value"]["id"]
    assert fields["discipline--0"] == row["discipline_id"]["value"]["id"]


def test_two_rows_fill_their_own_controls_and_do_not_overwrite(api, receiver):
    app_id = sections_application(api, two_rows=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = receiver.ledger()["acceptances"][0]["fields"]
    # Each row kept its own controls (no cross-row overwrite). Order is newest-first, so assert the
    # per-row pairing rather than a fixed order.
    assert fields["school--0"] != fields["school--1"]
    pairs = {
        (fields["school--0"], fields["degree--0"], fields["discipline--0"]),
        (fields["school--1"], fields["degree--1"], fields["discipline--1"]),
    }
    assert pairs == {("sch_state", "deg_bach", "dis_cs"), ("sch_metro", "deg_mast", "dis_math")}


def test_a_rehearsal_fills_the_section_but_never_submits(api, receiver):
    app_id = sections_application(api, scope="disclose_only")
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    assert receiver.ledger()["accepted"] == 0  # nothing was submitted


def test_submission_sends_once(api, receiver):
    app_id = sections_application(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_a_section_package_cannot_reach_a_section_blind_worker(api, receiver, monkeypatch):
    # D120 compatibility: a section-bearing package is approved at the current, section-aware
    # adapter version (greenhouse-dom-v4). An OLD worker whose greenhouse_dom predates D120 computes
    # the pre-section version (greenhouse-dom-v3); the binding fence (check_binding) then refuses the
    # attempt before anything is entered -- so a section package can never be claimed by a worker
    # that would fill the ordinary fields and silently skip the section. This is why SCHEMA_VERSION
    # can stay 3: worker compatibility is carried by adapter_version, not the content hash.
    app_id = sections_application(api)
    aid = queue(api, app_id)  # queued fine at the matching (current) version
    monkeypatch.setitem(
        policy.ADAPTER_VERSIONS, "greenhouse_dom", "greenhouse-dom-4+greenhouse-dom-v3"
    )
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["accepted"] == 0 and receiver.ledger()["disclosures"] == []
    with SessionLocal() as db:
        detail = db.get(ExecutionAttempt, uuid.UUID(aid)).outcome_detail or ""
    assert "execution method changed" in detail or "approve" in detail.lower()


def test_a_real_destination_refuses_the_legacy_only_section(api, receiver, monkeypatch):
    app_id = sections_application(api)
    aid = queue(api, app_id)
    # Treat the destination as a real (non-stand-in) page: the unobserved section must refuse
    # before anything is entered, not fill from a synthetic structure.
    monkeypatch.setattr(gd_adapter, "stand_ins", lambda content: False)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["accepted"] == 0 and receiver.ledger()["disclosures"] == []
    with SessionLocal() as db:
        detail = db.get(ExecutionAttempt, uuid.UUID(aid)).outcome_detail or ""
    assert "stand-in" in detail or "only" in detail
