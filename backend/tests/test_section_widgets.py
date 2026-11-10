"""D141: the employment section on the second Greenhouse-style stand-in, and section comboboxes that
are safe on react-select-style controls, driven by the real runner. The receiver's ledger is the
oracle (what its own submit posted from the DOM). The employment section, its ids and every
`section_widget` variant are FIXTURE ASSUMPTIONS (legacy-evidence ids; no real Greenhouse section
page has been observed). Synthetic data only."""

import pytest

from app.modules.execution import runner
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_greenhouse_dom import v2_job

ANSWERS = {"preferred_name": {"text": "Sammy"}, "question_8101": {"label": "Yes"},
           "question_8104": {"label": "No"}}  # fmt: skip
EMP_CURRENT = {"employer": "Example Health", "title": "Clinic Assistant",
               "start_date": "2019-01-01", "is_current": True}  # fmt: skip
EMP_PAST = {"employer": "Riverside Care", "title": "Front Desk", "start_date": "2016-03-01",
            "end_date": "2018-11-01", "is_current": False}  # fmt: skip
EDU = {
    "institution": "State University",
    "degree": "Bachelor's Degree",
    "field_of_study": "Computer Science",
    "start_date": "2014-09-01",
    "end_date": "2018-05-01",
}
EDU2 = {
    "institution": "Metro College",
    "degree": "Master's Degree",
    "field_of_study": "Mathematics",
    "start_date": "2019-09-01",
    "end_date": "2021-06-01",
}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def _record(api, path, body):
    r = api.post(f"/profile/{path}", json=body)
    assert r.status_code == 201, r.text
    assert api.post(f"/profile/{path}/{r.json()['id']}/approve").status_code == 200


def application(api, receiver, *, sections="education", widget="plain", education=(EDU,),
                employment=()) -> str:  # fmt: skip
    """The second stand-in read with its structured sections, the owner's approved records, the
    other questions answered; approved."""
    receiver.config(mode="gh2_sections", sections=sections, section_widget=widget)
    synthetic_candidate(api)
    for e in education:
        _record(api, "education", e)
    for e in employment:
        _record(api, "employment", e)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in ANSWERS.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, r.text
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    kinds = [s["kind"] for s in p["content"].get("sections") or []]
    assert kinds == [k for k in ("education", "employment") if k in sections], (
        kinds, p["content"]["validation_errors"])  # fmt: skip
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200
    return app_id


def sent(receiver) -> dict:
    (acc,) = receiver.ledger()["acceptances"]
    return acc["fields"]


# ------------------------------------------------------------------ the employment stand-in


def test_a_current_role_sends_current_and_no_end_date(api, receiver):
    app_id = application(api, receiver, sections="education,employment", employment=(EMP_CURRENT,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert (got["company-name-0"], got["title-0"]) == ("Example Health", "Clinic Assistant")
    assert (got["start-date-month-0"], got["start-date-year-0"]) == ("1", "2019")
    assert got["current-role-0"] == "true"
    assert "end-date-month-0" not in got and "end-date-year-0" not in got
    assert got["school--0"] == "sch_state"  # the education section beside it, untouched


def test_a_past_role_sends_its_end_date(api, receiver):
    app_id = application(api, receiver, sections="employment", education=(), employment=(EMP_PAST,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert got["current-role-0"] == "false"
    assert (got["end-date-month-0"], got["end-date-year-0"]) == ("11", "2018")


def test_each_section_adds_and_fills_its_own_rows(api, receiver):
    app_id = application(api, receiver, sections="education,employment", education=(EDU, EDU2),
                         employment=(EMP_CURRENT, EMP_PAST))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    # Newest first in each section, each row from its own record.
    assert (got["school--0"], got["school--1"]) == ("sch_metro", "sch_state")
    assert (got["company-name-0"], got["company-name-1"]) == ("Example Health", "Riverside Care")
    assert (got["current-role-0"], got["current-role-1"]) == ("true", "false")
    assert "end-date-year-0" not in got and got["end-date-year-1"] == "2018"


# ------------------------------------------------------------------ react-select-safe comboboxes


def test_section_comboboxes_are_never_typed_into(api, receiver):
    app_id = application(api, receiver)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)["fx_section_typed"] == "0"


def test_a_react_select_section_reads_back_from_its_single_value(api, receiver):
    app_id = application(api, receiver, widget="react_select")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert (got["school--0"], got["degree--0"], got["discipline--0"]) == (
        "sch_state",
        "deg_bach",
        "dis_cs",
    )
    assert (got["start-month--0"], got["end-month--0"]) == ("9", "5")


def test_a_choice_the_page_ignores_is_never_submitted(api, receiver):
    app_id = application(api, receiver, widget="ignores_choice")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "after choosing" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_an_option_recording_another_id_is_refused(api, receiver):
    app_id = application(api, receiver, widget="wrong_value")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0
    assert "zz" not in str(led["acceptances"])


def test_an_end_date_the_page_fills_for_a_current_role_is_refused(api, receiver):
    app_id = application(api, receiver, sections="employment", widget="prefill_end_date",
                         education=(), employment=(EMP_CURRENT,))  # fmt: skip
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "did not keep their values" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0
