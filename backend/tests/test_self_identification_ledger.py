"""D139: your self-identification (D122) on Greenhouse- and Workday-shaped forms, shown up to the
employer: what you opt into is sent, a decline sends the form's own decline, nothing you did not
choose is sent, a question it cannot tell apart is left to you, and turning it off or changing
it retires every approval of what it answered before anything more is sent. Local fixtures only
(the required gender question, the Workday-style veteran, Hispanic-origin and disability
questions and the values each sends are FIXTURE ASSUMPTIONS); what reached the employer is read
from the receiver's own ledger, never from our tables."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import Receiver, attempt, pilot_on, queue, synthetic_candidate
from tests.test_execution_validation import blocked_worker, release, wait_for
from tests.test_greenhouse_dom import SCREEN_JOB, refusal, v2_job
from tests.test_workday_adapter import workday_job

GENDER = "question_8113"  # the screening job's optional Gender: Male 1, Female 2, Decline 3


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def self_id(api, labels, enabled=True) -> dict:
    r = api.put("/profile/self-identification", json={"enabled": enabled, "labels": labels})
    assert r.status_code == 200, r.text
    return r.json()


def put(api, app_id, key, value):
    r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
    assert r.status_code == 200, (key, r.text)


def consent(api, app_id, key, choice):
    r = api.put(f"/applications/{app_id}/consents", json={"key": key, "choice": choice})
    assert r.status_code == 200, (key, r.text)


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def row(api, app_id, key) -> dict:
    return next(a for a in package(api, app_id)["content"]["answers"] if a["key"] == key)


def approve(api, app_id):
    p = package(api, app_id)
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def live_approvals(app_id) -> list[PackageApproval]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()


def retired_reasons(app_id) -> list[str]:
    with SessionLocal() as db:
        return [
            a.invalidation_reason
            for a in db.scalars(
                select(PackageApproval).where(
                    PackageApproval.application_id == uuid.UUID(app_id),
                    PackageApproval.invalidated_at.is_not(None),
                )
            )
        ]


def sent(receiver) -> dict:
    (acc,) = receiver.ledger()["acceptances"]
    return acc["fields"]


def nothing_sent(receiver):
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == [], led


# ------------------------------------------------------------------ Greenhouse-shaped (gh2)


def gh2_screening(api) -> str:
    """The screening job read by id; every question but gender answered by you (the felony
    answer included for this application): only gender is left to your self-identification."""
    synthetic_candidate(api)
    job_id = v2_job(api, SCREEN_JOB)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "preferred_name": {"text": "Sammy"},
        "question_8101": {"label": "Yes"},
        "question_8104": {"label": "No"},
        "question_8111": {"label": "No"},
        "question_8112": {"label": "No"},
    }.items():
        put(api, app_id, key, value)
    consent(api, app_id, "question_8111", "disclose")
    return app_id


@pytest.mark.parametrize("pilot", [False, True], ids=["by_id", "pilot"])
@pytest.mark.parametrize(
    "enabled,labels",
    [(False, ["Male"]), (True, ["Nonbinary"]), (True, [])],
    ids=["off", "no_matching_label", "no_labels"],
)
def test_without_a_match_you_chose_gender_is_never_sent(api, receiver, pilot, enabled, labels):
    if pilot:
        pilot_on()
    self_id(api, labels, enabled)
    app_id = gh2_screening(api)
    g = row(api, app_id, GENDER)
    assert (g["status"], g["value"]) == ("blank_optional", None) and g["source"] != (
        "self_identification"
    )
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert GENDER not in sent(receiver)


@pytest.mark.parametrize("pilot", [False, True], ids=["by_id", "pilot"])
def test_opted_in_your_label_is_sent_and_a_decline_label_sends_the_forms_decline(
    api, receiver, pilot
):
    if pilot:
        pilot_on()
    self_id(api, ["Decline To Self Identify"])
    app_id = gh2_screening(api)
    g = row(api, app_id, GENDER)
    assert (g["status"], g["source"], g["display"]) == (
        "resolved",
        "self_identification",
        "Decline To Self Identify",
    )
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[GENDER] == "3"


def test_your_dont_disclose_for_one_application_beats_your_standing_self_identification(
    api, receiver
):
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert row(api, app_id, GENDER)["source"] == "self_identification"
    consent(api, app_id, GENDER, "withhold")
    g = row(api, app_id, GENDER)
    assert (g["status"], g["source"], g["value"]) == ("blank_optional", "consent", None)
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert GENDER not in sent(receiver)


def test_a_required_gender_without_a_match_waits_for_you_and_dont_disclose_sends_the_decline(
    api, receiver
):
    receiver.config(mode="gh2_eeo_required")
    self_id(api, ["Nonbinary"])
    app_id = gh2_screening(api)
    g = row(api, app_id, GENDER)
    assert (g["status"], g["required"]) == ("needs_user", True)
    assert refusal(approve(api, app_id)) == "package_unresolved"
    q = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert q.status_code == 400, q.text
    nothing_sent(receiver)

    consent(api, app_id, GENDER, "withhold")
    g = row(api, app_id, GENDER)
    assert (g["status"], g["source"], g["display"]) == (
        "resolved",
        "consent",
        "Decline To Self Identify",
    )
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[GENDER] == "3"


@pytest.mark.parametrize("pilot", [False, True], ids=["by_id", "pilot"])
@pytest.mark.parametrize(
    "change,expected",
    [((False, ["Male"]), None), ((True, ["Female"]), "2")],
    ids=["turned_off", "changed"],
)
def test_withdrawing_or_changing_it_after_approval_retires_the_approval_at_once(
    api, receiver, pilot, change, expected
):
    if pilot:
        pilot_on()
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert approve(api, app_id).status_code == 200
    assert len(live_approvals(app_id)) == 1

    enabled, labels = change
    out = self_id(api, labels, enabled)
    assert out["applications_to_approve_again"] == 1
    assert live_approvals(app_id) == []  # at once, before anything reads the package
    (reason,) = retired_reasons(app_id)
    assert GENDER in reason and "Male" not in reason  # the question, never your answer
    q = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert q.status_code in (400, 409) and "approval_needed" in q.text, q.text
    nothing_sent(receiver)

    assert approve(api, app_id).status_code == 200  # approved again, as it now stands
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver).get(GENDER) == expected


def test_withdrawing_it_while_queued_stops_the_queued_attempt_before_anything_is_sent(
    api, receiver
):
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert self_id(api, ["Male"], enabled=False)["applications_to_approve_again"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "awaiting_approval"
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert "no longer valid" in attempt(aid).outcome_detail
    nothing_sent(receiver)


def test_withdrawing_it_while_a_worker_holds_the_attempt_stops_it_at_the_send_gate(api, receiver):
    """A worker holding the attempt owns the application's state, so the change cannot rebuild
    it then: the send gate rebuilds the package itself, sees it changed and abandons the
    attempt. The page was filled, nothing was submitted."""
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    w, gate = blocked_worker(aid, "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    assert self_id(api, ["Male"], enabled=False)["applications_to_approve_again"] == 0
    assert release(w, gate) == "abandoned"
    assert "changed after approval" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_an_unrelated_change_to_it_leaves_an_approval_alone(api, receiver):
    """Adding a label that answers nothing on this form changes nothing that is sent: the
    approval stands and the next run sends what was approved."""
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert approve(api, app_id).status_code == 200
    assert self_id(api, ["Male", "Asian"])["applications_to_approve_again"] == 0
    assert len(live_approvals(app_id)) == 1
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[GENDER] == "1"


# ------------------------------------------------------------------ Workday-shaped


def wd_application(api, receiver) -> str:
    """The Workday-style form read, your own answers and the terms acknowledgement given;
    every self-identification question left to your saved self-identification."""
    synthetic_candidate(api)
    job_id = workday_job(api)
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "legalName--firstName": {"text": "Sam"},
        "q.licence_type": {"label": "RN"},
        "q.shift": {"label": "Nights"},
    }.items():
        put(api, app_id, key, value)
    consent(api, app_id, "terms_ack", "agree")
    return app_id


def test_on_workday_pages_your_label_is_sent_as_the_options_own_value(api, receiver):
    self_id(api, ["Female"])
    app_id = wd_application(api, receiver)
    g = row(api, app_id, "vd.gender")
    assert (g["status"], g["source"], g["display"]) == ("resolved", "self_identification", "Female")
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)["vd.gender"] == "Female"


def test_on_workday_pages_each_question_takes_only_the_label_that_names_its_category(api, receiver):
    receiver.config(mode="wd_self_identify")
    self_id(
        api,
        [
            "Male",
            "I am not a protected veteran",
            "No, I do not have a disability and have not had one in the past",
            "No",
        ],
    )
    app_id = wd_application(api, receiver)
    rows = {a["key"]: a for a in package(api, app_id)["content"]["answers"]}
    for key in ("vd.gender", "vd.veteran", "si.disability"):
        assert (rows[key]["status"], rows[key]["source"]) == ("resolved", "self_identification")
    # A bare "No" names no category: it answers neither Hispanic origin nor any other question.
    assert (rows["vd.hispanic"]["status"], rows["vd.hispanic"]["value"]) == ("blank_optional", None)
    for key in ("q.work_eligibility", "q.sponsorship"):
        assert rows[key]["source"] != "self_identification"
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert (got["vd.gender"], got["vd.veteran"], got["si.disability"]) == (
        "Male",
        "Not a veteran",
        "No",
    )
    assert not got.get("vd.hispanic")
    assert (got["q.work_eligibility"], got["q.sponsorship"]) == ("Yes", "No")  # your facts


def test_on_workday_pages_two_labels_for_one_question_are_never_guessed(api, receiver):
    self_id(api, ["Male", "Female"])
    app_id = wd_application(api, receiver)
    g = row(api, app_id, "vd.gender")
    assert (g["status"], g["value"]) == ("blank_optional", None)
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert not sent(receiver).get("vd.gender")


def test_on_workday_pages_a_decline_label_declines_only_where_the_choices_name_a_category(
    api, receiver
):
    receiver.config(mode="wd_self_identify")
    self_id(api, ["I do not wish to answer"])
    app_id = wd_application(api, receiver)
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert (got["vd.gender"], got["vd.veteran"]) == ("Decline", "Decline")
    # Yes / No / decline: nothing says which question your decline was for; and the disability
    # form's own decline is worded "I do not want to answer", which is not your label.
    assert not got.get("vd.hispanic") and not got.get("si.disability")


@pytest.mark.parametrize(
    "change,expected",
    [((False, ["Female"]), None), ((True, ["Male"]), "Male")],
    ids=["turned_off", "changed"],
)
def test_on_workday_pages_withdrawing_or_changing_it_retires_the_approval(
    api, receiver, change, expected
):
    self_id(api, ["Female"])
    app_id = wd_application(api, receiver)
    assert approve(api, app_id).status_code == 200
    enabled, labels = change
    assert self_id(api, labels, enabled)["applications_to_approve_again"] == 1
    assert live_approvals(app_id) == []
    q = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert q.status_code in (400, 409) and "approval_needed" in q.text, q.text
    nothing_sent(receiver)
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert (sent(receiver).get("vd.gender") or None) == expected


def test_on_workday_pages_withdrawing_it_while_queued_sends_nothing(api, receiver):
    self_id(api, ["Female"])
    app_id = wd_application(api, receiver)
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert self_id(api, ["Female"], enabled=False)["applications_to_approve_again"] == 1
    assert runner.run_attempt(aid, "w1") == "ignored"
    nothing_sent(receiver)


def test_on_workday_pages_a_required_gender_waits_for_you_and_dont_disclose_sends_the_decline(
    api, receiver
):
    receiver.config(mode="wd_gender_required")
    self_id(api, ["Nonbinary"])
    app_id = wd_application(api, receiver)
    g = row(api, app_id, "vd.gender")
    assert (g["status"], g["required"]) == ("needs_user", True)
    assert refusal(approve(api, app_id)) == "package_unresolved"
    nothing_sent(receiver)
    consent(api, app_id, "vd.gender", "withhold")
    g = row(api, app_id, "vd.gender")
    assert (g["status"], g["source"], g["display"]) == (
        "resolved",
        "consent",
        "I do not wish to answer",
    )
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)["vd.gender"] == "Decline"


def test_a_save_also_retires_an_approval_already_out_of_date_for_another_reason(api, receiver):
    """The save rebuilds every package it could change, so an approval made stale by an edit that
    does not rebuild by itself (your phone, changed after approving) is retired by the same save,
    as a worker's gate would refuse it anyway; approved again, what is sent is what you now
    have."""
    self_id(api, ["Male"])
    app_id = gh2_screening(api)
    assert approve(api, app_id).status_code == 200
    prof = api.get("/profile").json()
    keep = ("full_name", "given_name", "family_name", "contact_email", "residence_country",
            "residence_city", "links")  # fmt: skip
    r = api.put("/profile", json={k: prof[k] for k in keep} | {"phone": "+1 555 0199"})
    assert r.status_code == 200, r.text
    assert len(live_approvals(app_id)) == 1  # the profile edit alone rebuilds nothing
    assert self_id(api, ["Male"])["applications_to_approve_again"] == 1  # nothing about you changed
    (reason,) = retired_reasons(app_id)
    assert "phone" in reason and GENDER not in reason
    nothing_sent(receiver)
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = sent(receiver)
    assert (got["phone"], got[GENDER]) == ("+1 555 0199", "1")
