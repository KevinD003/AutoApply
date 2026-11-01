"""D111 §5: the in-app milestone-B handoff (execution/handoff.py).

It reads the system as it is and grants nothing: each prerequisite is computed from the same
settings, register and approval the gates check, and a rehearsal it calls ready still goes
through every gate. Synthetic data only; the pilot plays against the local stand-in."""

import pytest

from app.core import authorizations
from app.modules.execution import runner
from tests.execution_harness import Receiver, pilot_on, queue
from tests.test_greenhouse_dom import live_application, v2_application
from tests.test_greenhouse_live import approve


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def handoff(api, app_id) -> dict:
    r = api.get(f"/applications/{app_id}/rehearsal-handoff")
    assert r.status_code == 200, r.text
    return r.json()


def met(h) -> dict:
    return {p["code"]: p["met"] for p in h["prerequisites"]}


def test_someone_elses_application_is_not_found(api, other_api, receiver):
    app_id = v2_application(api, approve=False)
    assert other_api.get(f"/applications/{app_id}/rehearsal-handoff").status_code == 404


def test_off_by_default_every_missing_prerequisite_is_listed_and_nothing_is_ready(api, receiver):
    """No switch, no recorded permission, a local fixture's job, and no rehearsal approval."""
    app_id = v2_application(api, approve=False)
    before = len(receiver.ledger()["requests"])  # capture read the job post
    h = handoff(api, app_id)
    assert h["ready"] is False
    assert {"pilot_switch", "owner_account", "greenhouse_posting", "permission_read",
            "permission_open", "permission_disclose", "captured_through_pilot",
            "rehearsal_approval"} <= set(h["outstanding"])  # fmt: skip
    assert met(h)["no_checkpoints"] is True  # every question answered
    assert h["submit_permission"]["met"] is False
    assert len(receiver.ledger()["requests"]) == before  # the handoff itself read nothing


def test_it_shows_exactly_what_filling_and_uploading_would_disclose(api, receiver):
    pilot_on()
    app_id = v2_application(api, approve=False)
    h = handoff(api, app_id)
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    sent = {a["key"]: a["display"] for a in c["answers"]
            if a["status"] == "resolved" and a["value"] is not None}  # fmt: skip
    assert {w["key"]: w["display"] for w in h["will_disclose"]} == sent
    how = {w["key"]: w["how"] for w in h["will_disclose"]}
    assert how["first_name"] == "typed" and how["question_8101"] == "chosen"
    assert how["resume"] == "uploaded"
    assert [d["field"] for d in h["documents"]] == [d["field"] for d in c["documents"]]
    assert {w["key"] for w in h["not_disclosed"]} == {
        a["key"] for a in c["answers"] if a["key"] not in sent}  # fmt: skip
    assert h["destination"]["url"] == c["destination"]["url"]
    assert any("before and without any submission" in e for e in h["exposure"])
    assert any("never reaches that step" in s for s in h["stop_before_submit"])


def test_with_every_prerequisite_met_a_rehearsal_runs_and_stops_before_submitting(api, receiver):
    """Ready only once you approved the exact package as a rehearsal; the gates still decide."""
    app_id = live_application(api, approve=False)  # captured through the pilot
    pilot_on(permitted=("read", "open", "disclose"))  # now without permission 4
    h = handoff(api, app_id)
    assert h["outstanding"] == ["rehearsal_approval"], h["outstanding"]
    assert h["submit_permission"]["met"] is False
    assert approve(api, app_id, "disclose_only").status_code == 200
    h = handoff(api, app_id)
    assert (h["ready"], h["outstanding"]) == (True, [])
    assert h["package"]["approval_scope"] == "disclose_only"
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == [] and led["disclosures"]


def test_a_permission_that_is_not_recorded_is_outstanding_whatever_the_switch_says(api, receiver):
    app_id = live_application(api, approve=False)
    pilot_on(permitted=("read", "open"))
    assert approve(api, app_id, "disclose_only").status_code == 200
    h = handoff(api, app_id)
    assert h["ready"] is False and h["outstanding"] == ["permission_disclose"]
    assert not any(a.what == authorizations.GREENHOUSE_PILOT and "disclose" in a.actions
                   for a in authorizations.RECORDED)  # fmt: skip
