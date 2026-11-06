"""D132: a form that changes after approval pauses the application instead of ending in a dead
end. The attempt stops (never resumed or retried), every live approval is retired, and a pause
bound to the package that ran is recorded; "Questions needing your answer" lists it; reading the
form again brings the new question; once it is answered and approved, exactly one new attempt
runs. The receiver's ledger is the oracle: what reached the employer, never our own tables.
Synthetic, fictional employers only; nothing real is read or sent."""

import sys
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ApplicationPause, AttemptEvent, ExecutionAttempt
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import (
    BASE,
    ROOT,
    Receiver,
    attempt,
    pilot_on,
    queue,
    synthetic_candidate,
)

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))

BOARD, JOB = "northwind", "5020001"
ADDED = "question_8106"  # greenhouse_v2.ADDED_QUESTION: "Are you available to work weekends?"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def v2_application(api, *, approve=True) -> str:
    synthetic_candidate(api)
    job_id = api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{JOB}",
            "title": "Support Specialist",
            "employer": "Northwind Example (fictional)",
        },
    ).json()["job"]["id"]
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "preferred_name": {"text": "Sammy"},
        "question_8101": {"label": "Yes"},
        "question_8104": {"label": "No"},
    }.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, r.text
    if approve:
        approve_current(api, app_id)
    return app_id


def live_application(api, **kw) -> str:
    pilot_on()
    return v2_application(api, **kw)


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def approve_current(api, app_id):
    p = package(api, app_id)
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def pauses(app_id) -> list[ApplicationPause]:
    with SessionLocal() as db:
        return db.scalars(
            select(ApplicationPause)
            .where(ApplicationPause.application_id == uuid.UUID(app_id))
            .order_by(ApplicationPause.created_at)
        ).all()


def live_approvals(app_id) -> list[PackageApproval]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()


def paused_application(api, receiver, make=v2_application) -> tuple[str, str]:
    """An approved application whose employer added a required question before the worker ran."""
    app_id = make(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    return app_id, aid


# ------------------------------------------------------------------ the pause


@pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])
def test_a_question_added_after_approval_pauses_before_anything_is_sent(api, receiver, make):
    app_id, aid = paused_application(api, receiver, make)
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert "changed since you approved" in attempt(aid).outcome_detail
    (p,) = pauses(app_id)
    assert (p.status, p.phase, p.kind) == ("open", "before_disclosure", "form_changed")
    assert p.detail == {"new": 1, "changed": 0, "missing": 0}
    assert p.package_hash == attempt(aid).package_hash and p.attempt_id == uuid.UUID(aid)
    assert live_approvals(app_id) == []  # every approval retired: nothing can send it again
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    r = approve_current(api, app_id)
    assert r.status_code == 409 and "form_recapture_needed" in r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    with SessionLocal() as db:
        assert db.scalar(
            select(ExecutionAttempt.id).where(
                ExecutionAttempt.application_id == uuid.UUID(app_id),
                ExecutionAttempt.state == "pending",
            )
        ) is None  # fmt: skip


def test_the_pause_is_listed_with_what_to_do(api, receiver):
    app_id, _ = paused_application(api, receiver)
    (item,) = api.get("/questions").json()["items"]
    assert item["application_id"] == app_id
    assert item["pause"]["status"] == "open" and item["pause"]["counts"]["new"] == 1
    assert item["paused_package"] is True and item["recapture_available"] is True
    assert api.get("/questions/count").json() == {"applications": 1, "paused": 1}
    feed = api.get("/notifications").json()["items"]
    mine = [n for n in feed if n["application_id"] == app_id]
    assert [n["kind"] for n in mine].count("form_changed") == 1
    assert next(n for n in mine if n["kind"] == "form_changed")["link"] == "/questions"
    assert not [n for n in mine if n["key"].startswith("attempt:")]  # the pause is the item


# ------------------------------------------------------------------ read again, answer, one run


@pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])
def test_reading_the_form_again_brings_the_question_and_one_new_attempt_sends_it(
    api, receiver, make
):
    app_id, _ = paused_application(api, receiver, make)
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["form"]["changed"] is True
    assert out["pause"]["status"] == "resolved" and out["pause"]["resolution"] == "new_form"
    content = package(api, app_id)["content"]
    assert ADDED in content["unresolved"]
    a = {x["key"]: x for x in content["answers"]}
    assert a["question_8101"]["value"]["label"] == "Yes"  # earlier answers kept
    (item,) = api.get("/questions").json()["items"]
    assert [q["key"] for q in item["questions"]] == [ADDED] and item["pause"] is None
    r = api.put(f"/applications/{app_id}/answers", json={"key": ADDED, "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    assert approve_current(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1  # exactly one acceptance, with the new answer
    assert led["acceptances"][0]["fields"][ADDED] == "1"
    assert api.get("/questions").json()["items"] == []


def test_a_recapture_that_finds_no_difference_leaves_this_package_refused(api, receiver):
    app_id, _ = paused_application(api, receiver)
    receiver.config(mode="normal")  # the employer changed it back before it was read again
    out = api.post(f"/applications/{app_id}/form/recapture").json()
    assert out["form"]["changed"] is False and out["pause"]["status"] == "unexplained"
    r = approve_current(api, app_id)
    assert r.status_code == 409 and "form_change_unexplained" in r.text
    # A different package is a new decision: approving it ends the pause.
    r = api.put(
        f"/applications/{app_id}/answers",
        json={"key": "preferred_name", "value": {"text": "Sam"}},
    )
    assert r.status_code == 200, r.text
    assert approve_current(api, app_id).status_code == 200
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("resolved", "new_package")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_a_recapture_refused_by_the_capture_route_leaves_the_pause_open(api, receiver):
    app_id, _ = paused_application(api, receiver, live_application)
    pilot_on(permitted=())  # the recorded permission to read is gone: the route's check refuses
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 409, r.text
    assert receiver.ledger()["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_reading_again_is_refused_while_an_attempt_holds_the_application(api, receiver):
    app_id = v2_application(api)
    queue(api, app_id)  # pending, not yet run
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 409 and "recapture_not_available" in r.text


# ------------------------------------------------------------------ boundaries


def test_a_stale_worker_writes_no_pause(api, receiver):
    app_id = v2_application(api)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    assert gen is not None
    stale = svc.pause_for_form_change(aid, "w1", gen + 1, "the form has changed", {"new": 1})
    assert stale is False
    assert pauses(app_id) == [] and len(live_approvals(app_id)) == 1
    assert attempt(aid).state == "claimed"


def test_a_pause_recorded_after_filling_is_abandoned_and_never_tried_again(api, receiver):
    # The runner records a pause only before filling; the service still judges the phase from
    # the row, never from the caller, and such a pause is never "tried again".
    app_id = v2_application(api)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    with SessionLocal() as db:
        from app.core.db import utcnow

        db.get(ExecutionAttempt, uuid.UUID(aid)).disclosure_started_at = utcnow()
        db.commit()
    assert svc.pause_for_form_change(aid, "w1", gen, "the form has changed", {"new": 1}) is True
    a = attempt(aid)
    assert a.state == "abandoned" and a.outcome_detail.startswith("Stopped after entering data")
    (p,) = pauses(app_id)
    assert p.phase == "after_disclosure" and p.status == "open"
    r = api.post(f"/applications/{app_id}/pause/dismiss")
    assert r.status_code == 409 and "pause_after_disclosure" in r.text


def test_trying_this_version_again_runs_it_again_and_a_change_still_there_stops_it(api, receiver):
    app_id, _ = paused_application(api, receiver)
    r = api.post(f"/applications/{app_id}/pause/dismiss")
    assert r.status_code == 200, r.text
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")
    assert approve_current(api, app_id).status_code == 200  # the same package, your decision
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"  # the change is still there
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert [x.status for x in pauses(app_id)] == ["closed", "open"]


def test_a_change_only_the_page_shows_stays_a_plain_stop(api, receiver):
    # Options that differ on the page only: the job data a re-read compares with is the same,
    # so no pause; the stop is what it always was.
    app_id = v2_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    assert pauses(app_id) == []


def test_cancelling_closes_the_pause(api, receiver):
    app_id, _ = paused_application(api, receiver)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "cancelled"})
    assert r.status_code == 200, r.text
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("closed", "cancelled")
    assert api.get("/questions/count").json()["paused"] == 0


def test_another_account_cannot_read_the_form_again_or_see_the_pause(api, other_api, receiver):
    app_id, _ = paused_application(api, receiver)
    assert other_api.post(f"/applications/{app_id}/form/recapture").status_code == 404
    assert other_api.post(f"/applications/{app_id}/pause/dismiss").status_code == 404
    assert other_api.get("/questions").json()["items"] == []
    assert other_api.get("/questions/count").json() == {"applications": 0, "paused": 0}
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_the_count_never_writes_a_package(api, receiver):
    app_id, _ = paused_application(api, receiver)
    before = package(api, app_id)["version"]
    for _ in range(3):
        api.get("/questions/count")
    assert package(api, app_id)["version"] == before


def test_no_question_key_or_label_in_the_pause_its_events_or_the_audit(api, receiver):
    app_id, aid = paused_application(api, receiver)
    api.post(f"/applications/{app_id}/form/recapture")
    (p,) = pauses(app_id)
    assert set(p.detail) == {"new", "changed", "missing"}
    with SessionLocal() as db:
        events = db.scalars(
            select(AttemptEvent.detail).where(AttemptEvent.attempt_id == uuid.UUID(aid))
        ).all()
        audits = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "application.form_recaptured")
        ).all()
    blob = repr(events) + repr(audits) + repr(p.detail)
    assert "question_" not in blob and "weekends" not in blob.lower()
    assert audits and set(audits[-1]) == {"form_version", "new_version", "pause"}
