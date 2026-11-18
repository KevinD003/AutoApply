"""D113: the owner's standing rule to apply automatically (app/modules/autoapply).

Against the local Greenhouse-style stand-in playing a real board through the pilot
(execution_harness.pilot_on); the receiver's ledger is the oracle for what was disclosed and
submitted. Synthetic data only."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.core import authorizations
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.autoapply import service
from app.modules.autoapply.models import AutoApplyEvent, AutoApplyPrefs
from app.modules.execution import live, runner
from app.modules.execution import service as svc
from app.modules.execution.models import ApplicationPause, ExecutionAttempt, RehearsalRecord
from app.modules.identity.models import User
from app.modules.preparation import package as pk
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import (
    PILOT_PERMISSIONS,
    Receiver,
    pilot_add,
    pilot_on,
    queue,
    synthetic_candidate,
)
from tests.test_greenhouse_dom import BASE, BOARD, SCREEN_JOB, v2_job

ANSWERS = {
    "preferred_name": {"text": "Sammy"},
    "question_8101": {"label": "Yes"},
    "question_8104": {"label": "No"},
}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    receiver.config(mode="normal")
    s = get_settings()
    monkeypatch.setattr(s, "auto_apply_enabled", True)
    monkeypatch.setattr(s, "auto_apply_daily_cap", 5)
    # E6 on the pilot's path, as on a real board: the first application is a rehearsal.
    monkeypatch.setattr(s, "execution_test_rehearsal_rule_paths", ["greenhouse_live:*"])


def tick() -> int:
    return service.tick()


def events(job_id=None) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        q = select(AutoApplyEvent).order_by(AutoApplyEvent.created_at)
        rows = db.scalars(q).all()
        return [(e.action, e.reason) for e in rows if job_id is None or str(e.job_id) == job_id]


def latest_attempt(app_id=None) -> str:
    with SessionLocal() as db:
        q = select(ExecutionAttempt).order_by(ExecutionAttempt.created_at.desc()).limit(1)
        return str(db.scalars(q).one().id)


def app_of(api, job_id) -> str:
    return api.post("/applications", json={"job_id": job_id}).json()["id"]


def answer(api, app_id) -> None:
    for key, value in ANSWERS.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)


def test_off_or_without_the_pilot_it_does_nothing(api, receiver, monkeypatch):
    synthetic_candidate(api)
    v2_job(api)
    assert tick() == 0  # the pilot is off: nothing is read
    pilot_on()
    monkeypatch.setattr(get_settings(), "auto_apply_enabled", False)
    assert tick() == 0
    assert receiver.ledger()["requests"] == [] and events() == []


def test_it_reads_the_post_waits_for_answers_then_rehearses_then_submits(api, receiver):
    """The whole rule: capture, a package with open questions waits for the owner; once answered,
    a rehearsal (never submits); once that held, the submission; then nothing more."""
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0
    assert events(job) == [("skipped", "open_questions")]  # the form was read; it waits
    assert receiver.ledger()["disclosures"] == []
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]  # not repeated
    app_id = app_of(api, job)  # the application the rule made
    waiting = [i for i in api.get("/notifications").json()["items"]
               if i["kind"] == "auto_apply_questions"]  # fmt: skip
    assert len(waiting) == 1 and waiting[0]["needs_action"] is True  # D115: the "pop-up"
    assert waiting[0]["application_id"] == app_id
    answer(api, app_id)
    assert not [i for i in api.get("/notifications").json()["items"]
                if i["kind"] == "auto_apply_questions"]  # fmt: skip
    assert tick() == 1
    assert events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["disclosures"] and led["accepted"] == 0  # filled and uploaded, never submitted
    assert tick() == 1
    assert events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    assert tick() == 0 and receiver.ledger()["accepted"] == 1  # done: never applied twice
    state = api.get("/auto-apply").json()
    assert state["active"] is True and state["approved_today"] == 2
    assert [e["action"] for e in state["events"]][:2] == ["approved_submit", "approved_rehearsal"]


def test_paused_by_the_owner_it_does_nothing(api, receiver):
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    r = api.put("/auto-apply", json={"paused": True})
    assert r.status_code == 200 and r.json()["paused"] is True and r.json()["active"] is False
    assert tick() == 0 and events(job) == [] and receiver.ledger()["requests"] == []
    assert api.put("/auto-apply", json={"paused": False}).json()["active"] is True


def test_the_daily_cap_and_the_permission_limit_hold(api, receiver, monkeypatch):
    pilot_on(max_attempts=1)
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0
    answer(api, app_of(api, job))
    with monkeypatch.context() as m:  # today's approvals used up
        m.setattr(service, "cap_used", lambda db, user_id, now=None: 5)
        assert tick() == 0 and events(job)[-1] == ("skipped", "daily_cap")
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 0 and events(job)[-1] == ("skipped", "permission_limit")  # 1 of 1 used
    assert receiver.ledger()["accepted"] == 0


def test_a_stopped_attempt_is_never_retried_automatically(api, receiver):
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    answer(api, app_of(api, job))
    receiver.config(mode="gh2_required_cover_group")  # the running page requires a document
    assert tick() == 1
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    receiver.config(mode="normal")
    assert tick() == 0 and events(job)[-1] == ("skipped", "attempt_stopped")
    assert receiver.ledger()["disclosures"] == []


# ------------------------------------------------- D169: the rule continues after a form change

ADDED = "question_8106"  # greenhouse_v2.ADDED_QUESTION, required once the employer adds it


def pause_rows(app_id: str) -> list[ApplicationPause]:
    with SessionLocal() as db:
        return db.scalars(
            select(ApplicationPause)
            .where(ApplicationPause.application_id == uuid.UUID(app_id))
            .order_by(ApplicationPause.created_at)
        ).all()


def rehearsal_queued(api) -> tuple[str, str]:
    """The rule's rehearsal for a fully answered application, queued and not yet run."""
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    return job, app_id


def requests_made(receiver) -> int:
    return len(receiver.ledger()["requests"])


def back_date_events(job: str, by: timedelta) -> None:
    """As if everything the rule noted for this job happened `by` earlier, in the same order (the
    read limit is a day; a note repeated last is never noted twice)."""
    with SessionLocal() as db:
        e = AutoApplyEvent
        db.execute(update(e).where(e.job_id == uuid.UUID(job)).values(created_at=e.created_at - by))
        db.commit()


def test_d169_a_page_changed_back_is_read_again_tried_once_more_and_sent_once(api, receiver):
    # The page asked something new when the attempt ran (it stopped before entering anything);
    # read again, the form shows no difference: the pause is marked unexplained and the step
    # ends; the next step tries that version once more, as the owner's "Try this version again"
    # does; it rehearses, then submits, exactly once.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    receiver.config(mode="normal")
    assert tick() == 0  # read: no difference; the step ends there
    (p,) = pause_rows(app_id)
    assert (p.status, p.recaptured_version) == ("unexplained", 1)
    assert tick() == 1
    assert events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_rehearsal", "rehearsal_queued"),
    ]
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    assert tick() == 0 and receiver.ledger()["accepted"] == 1  # done: never applied twice
    shown = api.get("/auto-apply").json()["events"]
    assert service.REASONS["form_tried_again"] in [e["text"] for e in shown]


def test_d169_a_question_the_employer_added_waits_for_your_answer_then_is_sent_once(api, receiver):
    # Read again, the new question is in the form: the pause ends (a new form version); the next
    # step rebuilds the package from it, the new question waiting for the owner's answer as any
    # other; then the rule rehearses and submits with it.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")  # the employer added a required question
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0 and events(job)[-1] == ("continued", "form_read_again")
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution, p.form_version, p.recaptured_version) == (
        "resolved",
        "new_form",
        1,
        2,
    )
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    waiting = [i for i in api.get("/notifications").json()["items"]
               if i["kind"] == "auto_apply_questions"]  # fmt: skip
    assert [i["application_id"] for i in waiting] == [app_id]  # the "pop-up" asks again
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    assert requests_made(receiver) == reads  # never read again
    r = api.put(f"/applications/{app_id}/answers", json={"key": ADDED, "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][ADDED] == "1"


def test_d169_a_change_a_read_cannot_see_is_tried_once_then_left_to_you(api, receiver):
    # Options only the running page changed: reading the form again finds no difference. The
    # rule tries that version once more; stopped again on it, the application is the owner's,
    # and the rule never reads it again.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0 and tick() == 1 and events(job)[-2] == ("continued", "form_tried_again")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stopped on it again
    assert tick() == 0  # read once more: no difference
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert [(p.status, p.form_version) for p in pause_rows(app_id)] == [
        ("closed", 1),
        ("unexplained", 1),
    ]
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert requests_made(receiver) == reads  # nothing read or tried again
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    shown = api.get("/auto-apply").json()["events"]
    assert shown[0]["text"] == service.REASONS["form_kept_changing"]
    # D170: the owner's for good: their own try hands nothing back; they approve it themselves.
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    receiver.config(mode="normal")
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    approve_yourself(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"


def test_d169_a_page_that_keeps_changing_is_yours_after_three_stops(api, receiver):
    # Each stop came before anything was entered, and each read found a new version; after
    # FORM_STOPS stops the rule leaves the application to the owner without reading it again.
    job, app_id = rehearsal_queued(api)
    for i, mode in enumerate(["gh2_question_added", "normal", "gh2_question_added"]):
        receiver.config(mode=mode)
        assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe", i
        assert tick() == 0 and events(job)[-1] == ("continued", "form_read_again"), i
        if i == 0:  # the new question waits for the owner's answer first
            assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
            r = api.put(f"/applications/{app_id}/answers",
                        json={"key": ADDED, "value": {"label": "Yes"}})  # fmt: skip
            assert r.status_code == 200, r.text
        assert tick() == 1, i
    receiver.config(mode="normal")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert len(pause_rows(app_id)) == service.FORM_STOPS + 1
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert requests_made(receiver) == reads  # the form is not read a fourth time
    assert pause_rows(app_id)[-1].status == "open"  # the owner's to read again
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # D170: the owner's for good: reading the form again themselves (the page without the
    # question it stopped with: a new version) hands nothing back (D132's words promise
    # "nothing is sent until you do").
    assert api.post(f"/applications/{app_id}/form/recapture").status_code == 200
    assert pause_rows(app_id)[-1].resolution == "new_form"
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert receiver.ledger()["disclosures"] == []


def test_d169_a_stop_after_your_data_was_entered_is_never_run_again_by_the_rule(api, receiver):
    # D135: after filling, the page required a question it reveals by its own logic; the
    # owner's data was on the page. The rule never enters it a second time (CLAUDE.md: no retry
    # after disclosure), even once the owner answered and tried it again themselves.
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "question_8104", "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200, r.text
    receiver.config(mode="gh2_conditional_required")
    assert tick() == 1
    # The rehearsal itself enters the data; then the page requires the question it revealed.
    assert runner.run_attempt(latest_attempt(), "w1") == "abandoned"
    (p,) = pause_rows(app_id)
    assert (p.kind, p.status) == ("conditional_required", "open")
    assert tick() == 0 and events(job)[-1] == ("skipped", "stopped_after_entry")
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "question_8105", "value": {"text": "Platform"}})  # fmt: skip
    assert r.status_code == 200, r.text
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    assert tick() == 0 and events(job)[-1] == ("skipped", "stopped_after_entry")
    assert receiver.ledger()["accepted"] == 0


def test_d169_an_attempt_that_entered_data_meanwhile_is_never_followed_by_the_rule(
    api, receiver, monkeypatch
):
    # The rule judges the application under its lock, as it is then: here, while its step ran,
    # the owner tried the paused version again and that attempt stopped after entering the data
    # (every approval retired). Judged on what it read before, the rule would approve and enter
    # the data a second time.
    from tests.test_hidden_search import MODE

    receiver.config(mode=MODE, hs="late")  # the form as read: a box the page shows once filled
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # paused before entry
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    lock, ran = pk.lock_application, []

    def owner_runs_it_meanwhile(db, app_uuid):
        if not ran:
            ran.append(True)
            approve_yourself(api, app_id)
            receiver.config(mode=MODE, hs="late")
            assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"  # data entered
        return lock(db, app_uuid)

    monkeypatch.setattr(pk, "lock_application", owner_runs_it_meanwhile)
    before = len(approvals(app_id))
    assert tick() == 0 and ran
    assert events(job)[-1] == ("skipped", "attempt_stopped")
    assert len(approvals(app_id)) == before + 1  # the owner's own, and no other
    # The owner tries again; that attempt stops on a changed form before anything is entered:
    # still theirs, since an attempt of this application entered the data.
    monkeypatch.setattr(pk, "lock_application", lock)
    approve_yourself(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert tick() == 0 and events(job)[-1] == ("skipped", "stopped_after_entry")
    assert receiver.ledger()["accepted"] == 0


def test_d169_a_newer_pause_made_during_the_rules_try_is_never_tried_without_a_read(
    api, receiver, monkeypatch
):
    # The rule tries an unexplained pause once more only as it read it; one the owner ended
    # meanwhile, followed by a new stop, is left for the next step, which reads the form for it.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0  # read: no difference, unexplained
    lock_pause, ran = service._lock_pause, []

    def owner_tries_it_meanwhile(db, j, app):
        if not ran:
            ran.append(True)
            assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
            approve_yourself(api, app_id)
            assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
        return lock_pause(db, j, app)

    monkeypatch.setattr(service, "_lock_pause", owner_tries_it_meanwhile)
    assert tick() == 0 and ran
    first, second = pause_rows(app_id)
    assert (first.status, first.resolution) == ("closed", "dismissed")  # the owner's
    assert (second.status, second.resolution) == ("open", None)  # read first, next step
    assert ("continued", "form_tried_again") not in events(job)


@pytest.mark.parametrize("act", ["cancel", "revoke"])
def test_d169_what_the_owner_does_during_the_rules_step_is_seen(api, receiver, monkeypatch, act):
    # The rule judges the application under its lock, as it is then: cancelled or revoked by
    # the owner since the step began, it is never approved by the rule.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    lock, ran = pk.lock_application, []

    def owner_acts_meanwhile(db, app_uuid):
        if not ran:
            ran.append(True)
            if act == "cancel":
                r = api.post(f"/applications/{app_id}/transition", json={"to": "cancelled"})
            else:
                approve_yourself(api, app_id)
                r = api.post(f"/applications/{app_id}/package/revoke")
            assert r.status_code == 200, r.text
        return lock(db, app_uuid)

    monkeypatch.setattr(pk, "lock_application", owner_acts_meanwhile)
    assert tick() == 0 and ran
    assert not [a for a in approvals(app_id) if a.by_rule and a.invalidated_at is None]
    assert receiver.ledger()["disclosures"] == []


def test_d169_a_read_that_fails_leaves_the_pause_and_is_tried_again_a_day_after_the_last(
    api, receiver, monkeypatch
):
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    capture, reads = service._capture, []

    def refused(db, user, j):  # the capture route refused the read (the post is gone), as
        reads.append(j.id)  # `_capture` reports it: rolled back, False
        db.rollback()
        return False

    monkeypatch.setattr(service, "_capture", refused)
    assert tick() == 0 and events(job)[-1] == ("skipped", "capture_failed")
    assert tick() == 0 and len(reads) == 1  # not read again the same day
    (p,) = pause_rows(app_id)
    assert p.status == "open"
    back_date_events(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
    assert tick() == 0 and len(reads) == 2  # a day later: read again, failed again
    assert tick() == 0 and len(reads) == 2  # the limit counts from that failure, not the first
    back_date_events(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
    assert tick() == 0 and len(reads) == 3
    monkeypatch.setattr(service, "_capture", capture)
    back_date_events(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
    assert tick() == 0 and events(job)[-1] == ("continued", "form_read_again")


def test_d169_a_paused_rule_continues_nothing(api, receiver, monkeypatch):
    # The owner pauses the rule while it reads the form: what the read found is kept (the pause
    # is marked unexplained, as the owner's own read would), nothing is approved, and while the
    # rule stays paused nothing more happens; resumed, it tries that version once more.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    capture = service._capture

    def read_then_pause(db, user, j):
        ok = capture(db, user, j)
        with SessionLocal() as other:
            service.set_paused(other, user.id, True)
            other.commit()
        return ok

    monkeypatch.setattr(service, "_capture", read_then_pause)
    before = len(approvals(app_id))
    assert tick() == 0
    (p,) = pause_rows(app_id)
    assert p.status == "unexplained"
    assert tick() == 0 and len(approvals(app_id)) == before
    assert events(job)[-1][0] != "continued"
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert tick() == 1 and events(job)[-2] == ("continued", "form_tried_again")


def test_d169_a_step_any_other_check_declines_never_counts_as_a_try(api, receiver, monkeypatch):
    # The version is tried once more only as it is approved: a step the daily cap declines
    # leaves the pause as it was, unexplained, and records no try.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0  # read: no difference
    with monkeypatch.context() as m:  # today's approvals used up
        m.setattr(service, "cap_used", lambda db, user_id, now=None: 5)
        assert tick() == 0 and events(job)[-1] == ("skipped", "daily_cap")
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("unexplained", None)
    assert ("continued", "form_tried_again") not in events(job)
    assert tick() == 1 and events(job)[-2] == ("continued", "form_tried_again")


def test_d169_what_d132_handed_to_you_stays_yours(api, receiver):
    # An application the rule left to the owner before D169 ("skipped: form_changed") stays
    # theirs, as D132 said: they may have applied on the employer's site meanwhile.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    with SessionLocal() as db:
        db.add(AutoApplyEvent(user_id=owner_id(), job_id=uuid.UUID(job),
                              application_id=uuid.UUID(app_id), action="skipped",
                              reason="form_changed"))  # fmt: skip
        db.commit()
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_changed")
    assert requests_made(receiver) == reads and pause_rows(app_id)[0].status == "open"
    shown = api.get("/auto-apply").json()["events"]
    assert shown[0]["text"] == service.REASONS["form_changed"]
    assert "during an attempt" in shown[0]["text"]  # D132's words, never "stopped trying"


def test_d169_an_account_that_is_not_the_owners_keeps_d132(api, other_api, receiver, monkeypatch):
    # It turned the rule on under its consent ("an attempt that stops is never retried"): its
    # paused application stays its own, never read again by the rule.
    pilot_on()  # names only the `api` account as the server owner
    monkeypatch.setattr(get_settings(), "all_accounts", True)
    synthetic_candidate(other_api)
    job = v2_job(other_api)
    assert other_api.put("/auto-apply", json={"paused": False}).json()["active"] is True
    tick()
    app_id = app_of(other_api, job)
    answer(other_api, app_id)
    assert tick() == 1
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_changed")
    assert requests_made(receiver) == reads
    item = next(i for i in other_api.get("/questions").json()["items"]
                if i["application_id"] == app_id)  # fmt: skip
    assert item["rule_continues"] is False
    assert rule_of(other_api, app_id) == [("yours", None)] * 2  # D170: never "waits"


def test_d169_the_pause_says_whether_the_rule_continues_it(api, receiver):
    # Shown with the pause (the feed and Questions), so the owner never applies by hand while
    # the rule continues it; once the rule leaves it, the D132 words and their action are back.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"

    def shown():
        note = next(n for n in api.get("/notifications").json()["items"]
                    if n["kind"] == "form_changed")  # fmt: skip
        item = next(i for i in api.get("/questions").json()["items"]
                    if i["application_id"] == app_id)  # fmt: skip
        return note, item["rule_continues"]

    note, continues = shown()
    assert continues is True and note["needs_action"] is False
    assert "continues it by itself" in note["text"]
    assert api.put("/auto-apply", json={"paused": True}).status_code == 200
    note, continues = shown()  # D170: it waits for the rule, never D132's words meanwhile
    assert continues is False and note["needs_action"] is True
    assert "is stopped now" in note["text"] and "I applied myself" in note["text"]
    assert "nothing is sent until you do" not in note["text"]
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert tick() == 0 and tick() == 1  # read, then tried once more
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stopped on it again
    assert tick() == 0 and tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    note, continues = shown()
    assert continues is False and note["needs_action"] is True
    assert "apply on the employer's site" in note["text"]


def test_d169_a_pause_on_an_application_you_once_revoked_is_yours(api, receiver):
    # The rule never approves an application whose approval the owner revoked (D134), so its
    # pause is the owner's, and shown so, even after the owner approved it again themselves.
    job, app_id = ready(api)
    approve_yourself(api, app_id)
    assert api.post(f"/applications/{app_id}/package/revoke").status_code == 200
    approve_yourself(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    note = next(n for n in api.get("/notifications").json()["items"]
                if n["kind"] == "form_changed")  # fmt: skip
    assert note["needs_action"] is True and "nothing is sent until you do" in note["text"]
    item = next(i for i in api.get("/questions").json()["items"]
                if i["application_id"] == app_id)  # fmt: skip
    assert item["rule_continues"] is False
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "owner_revoked")
    assert requests_made(receiver) == reads


def test_d169_a_pause_recorded_meanwhile_is_read_as_it_is_now(api, receiver):
    # The rule reads the account's switch as it is now, not as its session last saw it.
    pilot_on()
    synthetic_candidate(api)
    with SessionLocal() as db:
        user = db.get(User, owner_id())
        service.set_paused(db, user.id, False)  # the account's own choice: on
        db.commit()
        prefs = db.get(AutoApplyPrefs, user.id)  # held by this session
        assert service.paused(db, user) is False
        with SessionLocal() as other:
            service.set_paused(other, user.id, True)
            other.commit()
        assert prefs is not None and service.paused(db, user) is True


def test_d169_trying_again_yourself_while_the_rule_does_waits_and_it_happens_once(
    api, receiver, monkeypatch
):
    # The rule changes a pause under the application's lock, as the owner's routes do: "Try this
    # version again" clicked during the rule's step waits, then finds it already done. One
    # dismissal, one approval, no deadlock.
    from fastapi import HTTPException

    from app.modules.preparation import router as prep
    from tests.test_lock_order import Hold, Side, lock_waiters, no_errors, wait_until

    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    out = api.post(f"/applications/{app_id}/form/recapture").json()  # the owner read it: no change
    assert out["pause"]["status"] == "unexplained"
    before = len(approvals(app_id))
    hold = Hold("rule")  # held once it has read the pause under its locks
    held = hold.wrap(pk.unresolved_pause, after=True, when=lambda r: r is not None)
    monkeypatch.setattr(pk, "unresolved_pause", held)

    def owner_tries_again():
        with SessionLocal() as db:
            try:
                return prep.dismiss_pause(uuid.UUID(app_id), user=db.get(User, owner_id()), db=db)
            except HTTPException as e:
                return e.detail

    try:
        rule = Side("rule", tick)
        assert hold.reached.wait(30), "the rule never reached the pause"
        waiting = lock_waiters()
        owner = Side("owner", owner_tries_again)
        wait_until(lambda: lock_waiters() > waiting or not owner.thread.is_alive(), "it waits")
        assert owner.thread.is_alive(), (owner.error, owner.result, "it did not wait")
    finally:
        hold.go.set()
    rule.join(), owner.join()
    no_errors(rule, owner)
    assert rule.result == 1 and "no_pause" in str(owner.result)
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")
    assert len(approvals(app_id)) == before + 1
    assert events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_rehearsal", "rehearsal_queued"),
    ]


def test_d169_a_form_read_during_the_rules_try_again_waits_and_is_never_lost(
    api, receiver, monkeypatch
):
    # The rule reads the pause under its row lock, as it is now: a form read on the job's page
    # that would resolve it meanwhile waits for the rule's step, then finds it ended.
    from app.modules.preparation import router as prep
    from tests.test_lock_order import Hold, Side, lock_waiters, no_errors, wait_until

    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    out = api.post(f"/applications/{app_id}/form/recapture").json()  # the owner read it: no change
    assert out["pause"]["status"] == "unexplained"
    receiver.config(mode="gh2_question_added")  # a read now finds a new version
    hold = Hold("rule")  # held once it has read the pause under its locks
    held = hold.wrap(pk.unresolved_pause, after=True, when=lambda r: r is not None)
    monkeypatch.setattr(pk, "unresolved_pause", held)

    def read():
        with SessionLocal() as db:
            user = db.get(User, owner_id())
            return prep.capture_greenhouse_form(uuid.UUID(job), user=user, db=db)

    try:
        rule = Side("rule", tick)
        assert hold.reached.wait(30), "the rule never reached the pause"
        waiting = lock_waiters()
        reader = Side("read", read)
        wait_until(lambda: lock_waiters() > waiting or not reader.thread.is_alive(), "it waits")
        assert reader.thread.is_alive(), (reader.error, "the read did not wait")
    finally:
        hold.go.set()
    rule.join(), reader.join()
    no_errors(rule, reader)
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")  # one outcome, never overwritten


def test_d169_a_newer_pause_made_while_the_rule_reads_is_left_for_its_next_step(
    api, receiver, monkeypatch
):
    # While the rule reads the form for one pause, the owner tries that version again and the
    # attempt stops on the page again: the rule never marks or ends the newer pause in this
    # step (its form was not read for it).
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    capture = service._capture

    def read_while_the_owner_tries_again(db, user, j):
        ok = capture(db, user, j)  # no difference to see
        assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
        approve_yourself(api, app_id)
        assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
        return ok

    monkeypatch.setattr(service, "_capture", read_while_the_owner_tries_again)
    assert tick() == 0
    first, second = pause_rows(app_id)
    assert (first.status, first.resolution) == ("closed", "dismissed")  # the owner's
    assert (second.status, second.resolution) == ("open", None)  # untouched in this step
    assert events(job)[-1][0] != "continued"


def test_d169_an_application_you_approved_yourself_is_continued_and_asks_for_the_answer(
    api, receiver
):
    # The rule continues the account's applications it may apply to, not only those it
    # approved: here the owner approved and queued it after the rule asked for answers. The new
    # question is asked again (the notification is derived from the rule's note).
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]
    app_id = app_of(api, job)
    answer(api, app_id)
    approve_yourself(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert tick() == 0 and tick() == 0
    assert events(job) == [
        ("skipped", "open_questions"),
        ("continued", "form_read_again"),
        ("skipped", "open_questions"),
    ]
    waiting = [i for i in api.get("/notifications").json()["items"]
               if i["kind"] == "auto_apply_questions"]  # fmt: skip
    assert [i["application_id"] for i in waiting] == [app_id]
    assert receiver.ledger()["disclosures"] == []


def test_d169_each_form_version_is_tried_once_more(api, receiver, monkeypatch):
    # "Once more" counts per form version: a version read after another was tried once more is
    # tried once more itself.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stop 1, version 1
    assert tick() == 0 and tick() == 1 and events(job)[-2] == ("continued", "form_tried_again")
    receiver.config(mode="normal")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stop 2, version 1
    assert tick() == 0 and events(job)[-1] == ("continued", "form_read_again")
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    r = api.put(f"/applications/{app_id}/answers", json={"key": ADDED, "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stop 3, version 2
    monkeypatch.setattr(service, "_capture", lambda db, user, j: True)  # a read: no difference
    assert tick() == 0 and tick() == 1 and events(job)[-2] == ("continued", "form_tried_again")
    assert [(p.form_version, p.resolution) for p in pause_rows(app_id)] == [
        (1, "dismissed"),
        (1, "new_form"),
        (2, "dismissed"),
    ]
    assert receiver.ledger()["accepted"] == 0


def test_d169_only_a_stop_on_a_changed_form_before_anything_was_entered_is_continued(api, receiver):
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    att_id = latest_attempt()
    assert runner.run_attempt(att_id, "w1") == "failed_safe"
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, uuid.UUID(att_id))
        assert service._stopped_on_form_change(db, att)
        att.disclosure_started_at = utcnow()  # had anything been entered: never continued
        assert not service._stopped_on_form_change(db, att)
        att.disclosure_started_at = None
        db.execute(
            update(ApplicationPause)
            .where(ApplicationPause.attempt_id == att.id)
            .values(kind="conditional_required")
        )
        assert not service._stopped_on_form_change(db, att)  # a pause of another kind
        db.rollback()


def test_d169_a_note_after_continued_is_never_taken_for_a_repeat(api, receiver):
    # A skip already recorded last is not repeated: "last" includes a note of this very step
    # (the session never flushes by itself), so "waiting for your answers" after "continued" is
    # recorded again, whatever else the step wrote in between.
    from app.modules.applications.models import Application
    from app.modules.jobs.models import Job

    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]
    app_id = app_of(api, job)
    with SessionLocal() as db:
        user, j = db.get(User, owner_id()), db.get(Job, uuid.UUID(job))
        app = db.get(Application, uuid.UUID(app_id))
        service._note(db, user.id, j, app, "continued", "form_read_again")
        service._note(db, user.id, j, app, "skipped", "open_questions")
        service._note(db, user.id, j, app, "skipped", "open_questions")  # a repeat: not recorded
        db.commit()
    assert events(job) == [
        ("skipped", "open_questions"),
        ("continued", "form_read_again"),
        ("skipped", "open_questions"),
    ]


# ---------- D170: a paused application is the rule's to continue, waits for it, or is yours


def form_change_pause(api, receiver) -> tuple[str, str]:
    """The rule's rehearsal stopped on a changed form before anything was entered, the page as
    it was again since: a pause the rule continues by itself (D169), and shown so."""
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    receiver.config(mode="normal")
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    assert rule_of(api, app_id) == [("continues", None)] * 2
    assert tracker_rule(api, app_id) == "continues"
    return job, app_id


OTHER_ROLE = {"url": f"{BASE}/gh2/{BOARD}/jobs/5020003", "title": "Clinic Coordinator",
              "employer": "Northwind Example (fictional)"}  # fmt: skip


def tracker_rule(api, app_id: str) -> str | None:
    """The rule's verdict as the Tracker's row for the application carries it."""
    return next(a for a in api.get("/applications").json() if a["id"] == app_id)["rule"]


def pause_shown(api, app_id: str) -> tuple[dict, bool]:
    """The pause's notification and whether Questions says the rule continues it."""
    note = next(n for n in api.get("/notifications").json()["items"]
                if n["kind"] == "form_changed" and n["application_id"] == app_id)  # fmt: skip
    item = next(i for i in api.get("/questions").json()["items"]
                if i["application_id"] == app_id)  # fmt: skip
    return note, item["rule_continues"]


def rule_of(api, app_id: str) -> list[tuple]:
    """The rule's verdict and why it waits, as Questions and the application's page carry them."""
    item = next(i for i in api.get("/questions").json()["items"]
                if i["application_id"] == app_id)  # fmt: skip
    view = api.get(f"/applications/{app_id}/package").json()
    return [(item["rule"], item["rule_why"]), (view["rule"], view["rule_why"])]


def assert_yours(api, app_id: str) -> None:
    """Shown as the owner's for good: D132's words for the pause as it is, and its action."""
    note, continues = pause_shown(api, app_id)
    assert continues is False and note["needs_action"] is True
    unexplained = pause_rows(app_id)[-1].status == "unexplained"
    if unexplained:
        assert "apply on the employer's site" in note["text"]
        assert "and then choose “I applied myself”" in note["text"]
    else:
        assert "nothing is sent until you do" in note["text"]
    assert "continues it by itself" not in note["text"]
    assert rule_of(api, app_id) == [("yours", None)] * 2
    assert tracker_rule(api, app_id) == "yours"


WAITS_WORDS = {"stopped": "is stopped now", "declined": "rule it out",
               "unreadable": "could not read the employer's page again",
               "questions": "as soon as you answer the open questions",
               "submit_not_permitted":
                   "does not cover submitting (step 4) for your standing rule"}  # fmt: skip


def assert_waits(api, app_id: str, why: str, step4: bool = False) -> None:
    """Shown as waiting for the rule, with why: never D132's words, which would invite applying
    by hand while the rule may still send it; how to take it over instead. D171: `step4`, it
    waits for the pilot's step 4 too, said in the same words."""
    note, continues = pause_shown(api, app_id)
    assert continues is False and note["needs_action"] is True
    link = "/questions" if why == "questions" else f"/tracker?highlight={app_id}"
    key = f":waits:{why}" + (":step4" if step4 else "")
    assert note["link"] == link and note["key"].endswith(key)  # new when why changes
    assert WAITS_WORDS[why] in note["text"] and "I applied myself" in note["text"]
    assert (STEP4_WORDS in note["text"]) is step4
    assert "nothing is sent until you do" not in note["text"]
    assert rule_of(api, app_id) == [("waits", why)] * 2
    assert step4_of(api, app_id) == [step4] * 3
    assert tracker_rule(api, app_id) == "waits"


def step4_of(api, app_id: str) -> list[bool]:
    """D171: whether Questions, the application's page and the Tracker's row say it waits for
    step 4 too."""
    item = next(i for i in api.get("/questions").json()["items"]
                if i["application_id"] == app_id)  # fmt: skip
    view = api.get(f"/applications/{app_id}/package").json()
    return [item["rule_step4"], view["rule_step4"], tracker_row(api, app_id)["rule_step4"]]


def tracker_row(api, app_id: str) -> dict:
    return next(a for a in api.get("/applications").json() if a["id"] == app_id)


def never_read_or_tried(receiver, app_id: str, reads: int) -> None:
    """The pause as the attempt left it (open, never read again nor ended as a try), and nothing
    reached the page since `reads` requests."""
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("open", None)
    assert requests_made(receiver) == reads
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def same_role_applied(api, job: str = "5020002") -> str:
    """Another of the owner's jobs for the same role (title and employer) with an application
    past draft: a possible duplicate (D93) of every job for that role."""
    from app.modules.applications.models import Application
    from app.modules.applications.states import AppState

    other = v2_job(api, job=job)
    with SessionLocal() as db:
        applied = AppState.submitted_confirmed
        db.add(Application(user_id=owner_id(), job_id=uuid.UUID(other), state=applied,
                           state_changed_at=utcnow()))  # fmt: skip
        db.commit()
    return other


def continued_by_itself(job: str) -> None:
    """The rule reads the form again (no difference), then tries that version once more."""
    assert tick() == 0
    assert tick() == 1
    assert events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_rehearsal", "rehearsal_queued"),
    ]


def test_d170_a_paused_application_is_continued_whatever_its_jobs_age(api, receiver, monkeypatch):
    # The rule examines the newest jobs it may apply to (JOBS_PER_TICK of them) and every job whose
    # application waits on a form-change pause, however many jobs came after it.
    job, app_id = form_change_pause(api, receiver)
    monkeypatch.setattr(service, "JOBS_PER_TICK", 1)
    other_role = {"url": f"{BASE}/gh2/{BOARD}/jobs/5020003", "title": "Clinic Coordinator",
                  "employer": "Northwind Example (fictional)"}  # fmt: skip
    newer = api.post("/jobs", json=other_role).json()["job"]["id"]  # a newer job, another role
    with SessionLocal() as db:
        examined = [j.id for j in service._candidates(db, db.get(User, owner_id()))]
    assert examined == [uuid.UUID(job), uuid.UUID(newer)]  # first: never left behind by time
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    tick()  # the paused one read again: no difference, marked unexplained
    (p,) = pause_rows(app_id)
    assert p.status == "unexplained"
    tick()
    assert ("continued", "form_tried_again") in events(job)
    assert events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    # Its pause ended by the rule's own try: followed to the end all the same, never left to the
    # window (stalled, then sent once newer jobs close, long after the owner may have given up).
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d170_a_paused_application_on_a_possible_duplicate_waits_until_that_changes(api, receiver):
    # Another of the owner's jobs for the same role has an application past draft: the rule does
    # not continue this one, nor read its post, while that holds; it waits, never in D132's words.
    # Answered "a different role", the rule continues it by itself.
    job, app_id = form_change_pause(api, receiver)
    same_role_applied(api)
    assert_waits(api, app_id, "declined")
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "job_signal")
    assert tick() == 0 and events(job)[-1] == ("skipped", "job_signal")  # noted once
    assert events(job).count(("skipped", "job_signal")) == 1
    never_read_or_tried(receiver, app_id, reads)
    assert api.post(f"/jobs/{job}/different-role").status_code == 200
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    continued_by_itself(job)


def test_d170_a_paused_application_an_unmet_preference_rules_out_waits_until_it_is_met(
    api, receiver
):
    # A checked preference the job does not meet holds it, whatever else holds it too: while the
    # rule is paused it waits for the rule; resumed, for the preference; never in D132's words,
    # so the decline lifting after the owner applied by hand cannot send it unseen. Once the
    # preference no longer rules the job out, the rule continues it by itself.
    job, app_id = form_change_pause(api, receiver)
    assert api.put("/auto-apply", json={"paused": True}).status_code == 200
    assert_waits(api, app_id, "stopped")
    assert api.put("/profile/preferences", json={"titles": ["Registered Nurse"]}).status_code == 200
    assert_waits(api, app_id, "stopped")
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert_waits(api, app_id, "declined")
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "preferences_not_met")
    never_read_or_tried(receiver, app_id, reads)
    assert api.put("/profile/preferences", json={"titles": []}).status_code == 200
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    continued_by_itself(job)


def test_d170_a_post_unreadable_since_the_pause_waits_and_is_read_again_a_day_later(
    api, receiver, monkeypatch
):
    # Every read of the post fails (it is gone, or needs its own scripts): never shown as
    # continued meanwhile; read again once a day, and once it can be, continued by itself.
    job, app_id = form_change_pause(api, receiver)

    def refused(db, user, job):  # as `_capture` reports a read the capture route refuses
        db.rollback()
        return False

    with monkeypatch.context() as m:
        m.setattr(service, "_capture", refused)
        assert tick() == 0 and events(job)[-1] == ("skipped", "capture_failed")
    assert_waits(api, app_id, "unreadable")
    reads = requests_made(receiver)
    assert tick() == 0  # not read again within a day
    never_read_or_tried(receiver, app_id, reads)
    back_date_events(job, timedelta(hours=25))
    assert tick() == 0  # read again: no difference, marked unexplained
    (p,) = pause_rows(app_id)
    assert p.status == "unexplained"
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")


def test_d170_a_job_the_rule_declines_is_never_read_for_it(api, receiver):
    # A new job its signals or the owner's preferences rule out: declined before its post is read,
    # and no application is made for it.
    from app.modules.applications.models import Application

    pilot_on()
    synthetic_candidate(api)
    assert api.put("/profile/preferences", json={"titles": ["Registered Nurse"]}).status_code == 200
    job = v2_job(api)
    assert tick() == 0 and events(job) == [("skipped", "preferences_not_met")]
    assert requests_made(receiver) == 0
    assert api.put("/profile/preferences", json={"titles": []}).status_code == 200
    same_role_applied(api)
    assert tick() == 0 and events(job)[-1] == ("skipped", "job_signal")
    assert requests_made(receiver) == 0
    with SessionLocal() as db:
        made = db.scalars(select(Application).where(Application.job_id == uuid.UUID(job))).all()
    assert made == []


def test_d170_a_job_ruled_out_while_its_post_is_read_is_declined_after_the_read(
    api, receiver, monkeypatch
):
    # The decline is judged on what is true now: a preference the owner checks while the rule
    # reads a new job's post declines it before anything is made of what was read (the rule's
    # step read the owner's preferences before the read: never those again).
    from app.modules.applications.models import Application

    pilot_on()
    synthetic_candidate(api)
    assert api.put("/profile/preferences", json={"titles": []}).status_code == 200
    job = v2_job(api)
    real = service._capture

    def read_while_the_owner_edits(db, user, j):
        done = real(db, user, j)
        assert (
            api.put("/profile/preferences", json={"titles": ["Registered Nurse"]}).status_code
            == 200
        )
        return done

    monkeypatch.setattr(service, "_capture", read_while_the_owner_edits)
    assert tick() == 0 and events(job) == [("skipped", "preferences_not_met")]
    with SessionLocal() as db:
        made = db.scalars(select(Application).where(Application.job_id == uuid.UUID(job))).all()
    assert made == []


def test_d170_a_job_closed_while_its_post_is_read_is_declined_after_the_read(
    api, receiver, monkeypatch
):
    # The job's own state as it is now: closed by the owner while the rule reads its post.
    from app.modules.applications.models import Application

    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    real = service._capture

    def read_while_the_owner_closes_it(db, user, j):
        done = real(db, user, j)
        assert api.patch(f"/jobs/{job}", json={"status": "closed"}).status_code == 200
        return done

    monkeypatch.setattr(service, "_capture", read_while_the_owner_closes_it)
    assert tick() == 0 and events(job) == [("skipped", "job_signal")]
    with SessionLocal() as db:
        made = db.scalars(select(Application).where(Application.job_id == uuid.UUID(job))).all()
    assert made == []


def test_d170_a_pause_waits_for_the_rule_while_automatic_applying_is_stopped(
    api, receiver, monkeypatch
):
    # The rule would continue it, and does once it runs again: while it cannot (the recorded
    # permission's attempt limit used up, no recorded permission, no approval allowed a day), the
    # pause is shown as waiting, and the employer's page is not read for it.
    from app.modules.execution import live

    job, app_id = form_change_pause(api, receiver)
    pilot_on(max_attempts=1)
    # Used up by attempts of other applications (D112 counts those that passed the disclosure
    # gate; the stop on a changed form came before it): its count is tested above.
    monkeypatch.setattr(live, "attempts_used", lambda db, since, exclude=None: 1)
    assert_waits(api, app_id, "stopped")
    state = api.get("/auto-apply").json()  # "the Tracker shows why"
    assert state["active"] is False and state["unavailable"]["code"] == "limit_reached"
    assert "at most 1 attempts" in state["unavailable"]["message"]
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "permission_limit")
    pilot_on(permitted=())  # no recorded permission: the rule does not run at all
    assert_waits(api, app_id, "stopped")
    assert tick() == 0 and events(job)[-1] == ("skipped", "permission_limit")
    never_read_or_tried(receiver, app_id, reads)
    pilot_on()  # a new permission
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 0)  # no approval allowed a day
    assert_waits(api, app_id, "stopped")
    assert api.get("/auto-apply").json()["unavailable"]["code"] == "no_daily_approvals"
    assert tick() == 0  # the rule does nothing then: no post read for nothing
    never_read_or_tried(receiver, app_id, reads)
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 5)
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    continued_by_itself(job)


def test_d170_a_read_needs_the_permission_as_it_is_now(api, receiver, monkeypatch):
    # A tick can outlast a recorded permission's last day: the post is read only while the
    # permission covers reading as it is now, and nothing is noted as a failed read for it.
    from app.modules.execution import live

    job, app_id = form_change_pause(api, receiver)
    real = live.refusal

    def refusal(user, actions=live.TO_APPLY, *, approver):
        if tuple(actions) == ("read",):
            return "not_authorized"
        return real(user, actions, approver=approver)

    monkeypatch.setattr(live, "refusal", refusal)
    other_role = {"url": f"{BASE}/gh2/{BOARD}/jobs/5020003", "title": "Clinic Coordinator",
                  "employer": "Northwind Example (fictional)"}  # fmt: skip
    newer = api.post("/jobs", json=other_role).json()["job"]["id"]  # a new job: read first
    reads = requests_made(receiver)
    assert tick() == 0
    never_read_or_tried(receiver, app_id, reads)
    assert ("skipped", "capture_failed") not in events(job)
    assert events(newer) == []  # neither read nor noted as a failed read


def test_d170_the_tasks_time_limit_stops_the_rule_at_once(api, receiver, monkeypatch):
    # The worker task's soft time limit ends the tick: no further job is started after it.
    from celery.exceptions import SoftTimeLimitExceeded

    ready(api)
    started = []

    def out_of_time(db, user, job, now):
        started.append(job.id)
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(service, "_advance", out_of_time)
    v2_job(api, job="5020003")  # a second job the rule would examine
    with pytest.raises(SoftTimeLimitExceeded):
        tick()
    assert len(started) == 1


def test_d170_a_pause_on_a_job_the_rule_never_examines_is_yours(api, receiver, monkeypatch):
    # Not a post the pilot accepts: the rule never acts on it, so it is the owner's (D132's words),
    # whatever else holds; never shown as waiting for the rule.
    from tests.test_form_change_loop import paused_application

    monkeypatch.setattr(get_settings(), "live_owner_emails", ["synthetic.user@example.com"])
    app_id, _ = paused_application(api, receiver)  # by the job's id: the pilot is off
    assert_yours(api, app_id)


def test_d170_the_feed_never_says_it_continues_beside_a_pause(api, receiver):
    # The pause's own item says what the rule does; an earlier "answer the open questions and it
    # continues by itself" for the same application never stands beside it.
    job, app_id = form_change_pause(api, receiver)
    with SessionLocal() as db:
        db.add(AutoApplyEvent(user_id=owner_id(), job_id=uuid.UUID(job),
                              application_id=uuid.UUID(app_id), action="skipped",
                              reason="open_questions"))  # fmt: skip
        db.commit()
    kinds = [n["kind"] for n in api.get("/notifications").json()["items"]
             if n["application_id"] == app_id]  # fmt: skip
    assert kinds == ["form_changed"]


def test_d170_the_questions_count_leaves_out_what_the_rule_continues(api, receiver):
    # A pause the account's rule continues by itself does not wait for the owner.
    _, app_id = form_change_pause(api, receiver)
    assert api.get("/questions/count").json()["paused"] == 0
    assert api.put("/auto-apply", json={"paused": True}).status_code == 200
    assert api.get("/questions/count").json()["paused"] == 1


def test_d170_a_pause_on_an_application_begun_before_a_restore_is_yours(api, receiver):
    # A restored database leaves to the owner every application begun before it (D147), even
    # once the owner resumes the rule: its pause is shown as theirs, and never read again.
    from app.modules.execution import restore
    from tests.test_restore_hold import restored

    job, app_id = form_change_pause(api, receiver)
    restored()
    assert restore.resolve() is not None  # resolving pauses the rule
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200  # resumed by you
    assert_yours(api, app_id)
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "restored_from_backup")
    never_read_or_tried(receiver, app_id, reads)


def test_d170_a_pause_while_a_restore_is_unresolved_is_yours(api, receiver):
    # Once resolved, an application begun before the restore is the owner's for good (D147), so
    # it is shown as theirs from the moment the restore is found, never as continued.
    from tests.test_restore_hold import restored

    _, app_id = form_change_pause(api, receiver)
    restored()
    assert_yours(api, app_id)


def test_d170_a_final_application_is_never_shown_as_continued(api, receiver):
    # The rule never acts on a final application, so its pause, were one still waiting, is the
    # owner's for good. (Five of the six final states end the pause first; failed_retryable leaves
    # it, though a paused application never reaches that state today.)
    from app.modules.applications.models import Application
    from app.modules.applications.states import AppState

    finals = {AppState.submitted_confirmed, AppState.submitted_unconfirmed,
              AppState.failed_terminal, AppState.failed_retryable, AppState.cancelled,
              AppState.expired}  # fmt: skip
    assert set(service.FINAL_STATES) == finals
    _, app_id = form_change_pause(api, receiver)
    with SessionLocal() as db:
        user, app = db.get(User, owner_id()), db.get(Application, uuid.UUID(app_id))
        assert service.verdict(db, user, app) == (service.CONTINUES, None)
        for state in finals:
            app.state = state
            db.flush()
            assert service.verdict(db, user, app) == (service.YOURS, None), state
        db.rollback()


def test_d170_a_page_that_kept_changing_is_yours_whatever_a_later_read_finds(api, receiver):
    # Read once more, with no difference: shown as the owner's from that read, before the
    # rule's next step, and theirs for good: a read finding a new version since (the owner's own
    # here) ends the pause and hands nothing back to the rule.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0 and tick() == 1  # read again (no difference), then tried once more
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stopped on it again
    assert tick() == 0  # read once more: no difference
    assert_yours(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert api.post(f"/applications/{app_id}/form/recapture").status_code == 200
    assert pause_rows(app_id)[-1].resolution == "new_form"
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert requests_made(receiver) == reads
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_d170_the_owners_own_read_finding_no_difference_counts_as_the_rules(api, receiver):
    # The second stop on a version tried once more, read again by the owner before the rule could
    # (no difference): the page kept changing, whoever read it, so it is never tried a third time.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    assert tick() == 0 and tick() == 1  # read again (no difference), then tried once more
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stopped on it again
    assert api.post(f"/applications/{app_id}/form/recapture").status_code == 200
    assert pause_rows(app_id)[-1].status == "unexplained"
    assert_yours(api, app_id)
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    assert requests_made(receiver) == reads
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_d170_the_upgrade_leaves_every_application_paused_before_it_to_its_owner(
    api, other_api, receiver
):
    # Before D169 the rule left every application that had paused to its owner for good (D132's
    # words: "nothing is sent until you do"). The upgrade records that hand-over once for each
    # application with a pause, under its own account; one without a pause gets nothing.
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.modules.applications.models import Application
    from tests.test_form_change_loop import paused_application

    path = (
        Path(__file__).parents[1] / "migrations/versions/d170b0a8e3c1_hand_over_earlier_pauses.py"
    )
    spec = importlib.util.spec_from_file_location("d170_hand_over", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def upgrade() -> None:  # its data step: the column is there already (the schema is at head)
        with SessionLocal() as db:
            with Operations.context(MigrationContext.configure(db.connection())):
                migration.hand_over()
            db.commit()

    others, _ = paused_application(other_api, receiver)  # by the job's id: before the pilot is on
    receiver.config(mode="normal")
    job, app_id = form_change_pause(api, receiver)  # the rule's to continue, until the upgrade
    unpaused = same_role_applied(api)
    upgrade()
    upgrade()  # nothing twice
    with SessionLocal() as db:
        rows = db.execute(
            select(AutoApplyEvent.user_id, AutoApplyEvent.application_id, AutoApplyEvent.job_id)
            .where(AutoApplyEvent.reason == "form_changed", AutoApplyEvent.action == "skipped")
            .order_by(AutoApplyEvent.created_at)
        ).all()
        other_user = db.scalar(select(User.id).where(User.id != owner_id()))
        other_job = db.scalar(select(Application.job_id).where(Application.id == uuid.UUID(others)))
    assert sorted(rows) == sorted([
        (owner_id(), uuid.UUID(app_id), uuid.UUID(job)),
        (other_user, uuid.UUID(others), other_job),
    ])  # fmt: skip
    assert events(unpaused) == []
    assert_yours(api, app_id)
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "form_changed")
    assert requests_made(receiver) == reads
    assert api.put("/auto-apply", json={"paused": True}).status_code == 200
    assert_yours(api, app_id)  # never "waits" (its words promise it continues by itself)


def test_d170_a_paused_application_is_followed_after_its_pause_whatever_its_jobs_age(
    api, receiver, monkeypatch
):
    # The rule's read finds a new question, which ends the pause: the rule still examines the
    # application however many jobs came after it, so the question is asked for (the feed's
    # "Questions are waiting") and, answered, the application is approved by itself.
    job, app_id = rehearsal_queued(api)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    monkeypatch.setattr(service, "JOBS_PER_TICK", 1)
    newer = api.post("/jobs", json=OTHER_ROLE).json()["job"]["id"]
    assert tick() == 0 and events(job)[-1] == ("continued", "form_read_again")  # pause ended
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    kinds = [n["kind"] for n in api.get("/notifications").json()["items"]
             if n["application_id"] == app_id]  # fmt: skip
    assert "auto_apply_questions" in kinds
    r = api.put(f"/applications/{app_id}/answers", json={"key": ADDED, "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    with SessionLocal() as db:
        examined = [j.id for j in service._candidates(db, db.get(User, owner_id()))]
    assert examined == [uuid.UUID(job), uuid.UUID(newer)]


def test_d170_a_try_that_waits_for_your_answer_says_so(api, receiver):
    # The version is to be tried once more, and its package now asks for an answer (here the owner
    # cleared one): the rule approves nothing until it is given, so the pause asks for it, and
    # never says "continues it by itself" meanwhile. Answered, the rule tries it by itself.
    job, app_id = form_change_pause(api, receiver)
    assert tick() == 0  # read again: no difference
    assert pause_rows(app_id)[-1].status == "unexplained"
    r = api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_8101"})
    assert r.status_code == 200, r.text
    assert_waits(api, app_id, "questions")
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    assert pause_rows(app_id)[-1].status == "unexplained"  # never tried meanwhile
    assert_waits(api, app_id, "questions")
    kinds = [n["kind"] for n in api.get("/notifications").json()["items"]
             if n["application_id"] == app_id]  # fmt: skip
    assert kinds == ["form_changed"]  # one message for the application
    assert api.get("/questions/count").json()["paused"] == 1
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "question_8101", "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200, r.text
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    assert tick() == 1 and events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_rehearsal", "rehearsal_queued"),
    ]


def test_d170_a_pause_made_while_the_account_was_not_the_owners_stays_its_own(
    api, other_api, receiver, monkeypatch
):
    # Not the owner's account when its attempt stopped (sole-owner mode off), its own rule off: D132
    # holds for it, recorded with the pause, so a setting that makes it the owner's later (sole-
    # owner mode switched on) never hands the application to the rule.
    pilot_on()  # names only the `api` account as the server owner
    monkeypatch.setattr(get_settings(), "all_accounts", True)
    synthetic_candidate(other_api)
    job = v2_job(other_api)
    assert other_api.post(f"/jobs/{job}/form/greenhouse").status_code == 201
    app_id = other_api.post("/applications", json={"job_id": job}).json()["id"]
    answer(other_api, app_id)
    assert other_api.get("/auto-apply").json()["paused"] is True  # off until it turns it on
    approve_yourself(other_api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(queue(other_api, app_id), "w1") == "failed_safe"
    receiver.config(mode="normal")
    assert events(job) == [("skipped", "form_changed")]  # with the pause, not by the rule
    assert rule_of(other_api, app_id) == [("yours", None)] * 2
    monkeypatch.setattr(get_settings(), "sole_owner", True)  # D168: every account the owner's
    assert other_api.get("/auto-apply").json()["paused"] is False  # its rule on by default now
    assert rule_of(other_api, app_id) == [("yours", None)] * 2
    reads = requests_made(receiver)
    assert tick() == 0 and events(job) == [("skipped", "form_changed")]
    assert requests_made(receiver) == reads
    assert receiver.ledger()["accepted"] == 0


def test_d170_each_account_examines_only_its_own_paused_applications(
    api, other_api, receiver, monkeypatch
):
    # Two accounts, each with a paused application on a stand-in posting and its rule on: each
    # account's rule examines only its own, and none ever makes an application on a job of
    # another account, whatever selected it.
    from app.modules.applications.models import Application
    from app.modules.jobs.models import Job

    pilot_on()
    monkeypatch.setattr(get_settings(), "all_accounts", True)
    synthetic_candidate(other_api)
    theirs_job = v2_job(other_api)
    assert other_api.put("/auto-apply", json={"paused": False}).status_code == 200
    tick()
    theirs_app = app_of(other_api, theirs_job)
    answer(other_api, theirs_app)
    assert tick() == 1
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(theirs_app), "w1") == "failed_safe"
    receiver.config(mode="normal")
    job, app_id = form_change_pause(api, receiver)
    with SessionLocal() as db:
        other = db.scalar(select(User.id).where(User.id != owner_id()))
        mine = {j.id for j in service._candidates(db, db.get(User, owner_id()))}
        their = {j.id for j in service._candidates(db, db.get(User, other))}
    assert uuid.UUID(job) in mine and uuid.UUID(theirs_job) not in mine
    assert uuid.UUID(theirs_job) in their and uuid.UUID(job) not in their
    real = service._candidates

    def with_a_job_of_the_other_account(db, user):  # as a fault would select it
        return real(db, user) + [db.get(Job, uuid.UUID(theirs_job))]

    monkeypatch.setattr(service, "_candidates", with_a_job_of_the_other_account)
    tick()
    tick()
    with SessionLocal() as db:
        for a in db.scalars(select(Application)).all():
            assert db.get(Job, a.job_id).user_id == a.user_id
        on_theirs = AutoApplyEvent.job_id == uuid.UUID(theirs_job)
        noted = db.scalars(select(AutoApplyEvent).where(on_theirs, AutoApplyEvent.user_id != other))
        noted = noted.all()
    assert noted == []  # nothing noted on it for the owner either


def test_d170_the_tasks_time_limit_during_queueing_ends_the_tick(api, receiver, monkeypatch):
    # Celery's soft limit can fire while the rule queues what it approved: never taken for a
    # refusal, so nothing it began is kept (its approval among it) and no further job is started.
    from celery.exceptions import SoftTimeLimitExceeded

    from app.modules.execution import service as execution

    _, app_id = ready(api)

    def out_of_time(db, app):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(execution, "enqueue", out_of_time)
    with pytest.raises(SoftTimeLimitExceeded):
        tick()
    assert approvals(app_id) == []


def test_d170_a_refused_queue_is_not_the_try_once_more(api, receiver, monkeypatch):
    # The version to be tried once more, and the queue refused after the rule approved it: nothing
    # was tried, so the pause stays as it was (unexplained, shown as the rule's), and the next
    # step tries it.
    from app.modules.execution import service as execution

    job, app_id = form_change_pause(api, receiver)
    assert tick() == 0  # read again: no difference
    real = execution.enqueue

    def refused(db, app):
        raise RuntimeError("refused")

    monkeypatch.setattr(execution, "enqueue", refused)
    assert tick() == 0 and events(job)[-1] == ("skipped", "queue_refused")
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("unexplained", None)
    assert ("continued", "form_tried_again") not in events(job)
    assert [a for a in approvals(app_id) if a.by_rule and a.invalidated_at is None] == []
    note, continues = pause_shown(api, app_id)
    assert continues is True
    monkeypatch.setattr(execution, "enqueue", real)
    assert tick() == 1 and events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_rehearsal", "rehearsal_queued"),
    ]


def test_d170_a_job_closed_just_before_the_rules_approval_is_not_approved(
    api, receiver, monkeypatch
):
    # The job's state at the approval is as it is then: closed by the owner after the rule's
    # step judged it, before the approval, the approval is refused.
    from app.modules.preparation import package as pk

    job, app_id = ready(api)
    real = pk.ensure_current

    def built_while_the_owner_closes_it(db, app):
        out = real(db, app)
        if str(app.id) == app_id:
            assert api.patch(f"/jobs/{job}", json={"status": "closed"}).status_code == 200
        return out

    monkeypatch.setattr(pk, "ensure_current", built_while_the_owner_closes_it)
    assert tick() == 0 and events(job)[-1] == ("skipped", "approval_refused")
    assert approvals(app_id) == []


def test_d170_a_read_held_by_a_recent_failure_is_shown_as_unreadable(api, receiver):
    # A read of the post failed shortly before the pause: the rule's next read is held a day after
    # it, so the pause waits as unreadable; a failure more than a day before the pause holds
    # nothing, and the pause is shown as continued.
    job, app_id = form_change_pause(api, receiver)
    (p,) = pause_rows(app_id)
    with SessionLocal() as db:
        db.add(AutoApplyEvent(user_id=owner_id(), job_id=uuid.UUID(job),
                              application_id=uuid.UUID(app_id), action="skipped",
                              reason="capture_failed",
                              created_at=p.created_at - timedelta(hours=2)))  # fmt: skip
        db.commit()
    assert_waits(api, app_id, "unreadable")
    reads = requests_made(receiver)
    assert tick() == 0
    never_read_or_tried(receiver, app_id, reads)
    back_date_events(job, timedelta(days=1))  # that failure now more than a day before
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False


# ------------------------------------- D171: a recorded permission for rehearsals only

REHEARSALS_ONLY = ("read", "open", "disclose")  # the pilot's steps 1-3, not step 4
STEP4_WORDS = "and your recorded permission covers submitting (step 4) for your standing rule"


def scopes(app_id: str) -> list[str]:
    return [str(getattr(a.scope, "value", a.scope)) for a in approvals(app_id)]


def held(api, app_id: str) -> tuple:
    """The rule's state of an application with no pause, as its page and its row carry it."""
    view = api.get(f"/applications/{app_id}/package").json()
    row = tracker_row(api, app_id)
    return ((view["rule"], view["rule_why"], view["rule_step4"]),
            (row["rule"], row["rule_why"], row["rule_step4"]))  # fmt: skip


def rehearsed_and_held(api) -> tuple[str, str]:
    """Steps 1-3 recorded: the rule rehearses the employer's first application, then holds it."""
    pilot_on(permitted=REHEARSALS_ONLY)
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    return job, app_id


def submission_paused(api, receiver) -> tuple[str, str]:
    """The rule's submission (its employer's rehearsal held) stopped on a changed form before
    anything was entered, the page as it was again since; then steps 1-3 only are recorded."""
    job, app_id = rehearsal_queued(api)
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    receiver.config(mode="normal")
    note, continues = pause_shown(api, app_id)
    assert continues is True  # step 4 recorded: the rule continues it
    pilot_on(permitted=REHEARSALS_ONLY)
    return job, app_id


def test_d171_with_a_permission_for_rehearsals_only_it_rehearses_and_submits_nothing(
    api, receiver, monkeypatch
):
    # Steps 1-3 recorded, not step 4: the rule reads the post and rehearses the employer's first
    # application (filled and checked, never submitted), then approves nothing more and says why,
    # once: on the application's page and its row (it may still send it), the rehearsal's own item
    # (never "approve again to submit") and the Tracker's card. Step 4 recorded, it is submitted
    # once, and its page and row are its own again.
    pilot_on(permitted=REHEARSALS_ONLY)
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]  # read (step 1)
    app_id = app_of(api, job)
    answer(api, app_id)
    state = api.get("/auto-apply").json()
    assert state["active"] is True and state["submits"] is False
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert receiver.ledger()["disclosures"] and receiver.ledger()["accepted"] == 0
    assert held(api, app_id) == ((None, None, False),) * 2  # not held yet
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    assert tick() == 0 and events(job).count(("skipped", "submit_not_permitted")) == 1
    assert scopes(app_id) == ["disclose_only"]  # the rehearsal's only: no submission approved
    assert held(api, app_id) == (("waits", "submit_not_permitted", False),) * 2
    shown = api.get("/auto-apply").json()["events"]
    assert service.REASONS["submit_not_permitted"] in [e["text"] for e in shown]
    (r,) = [n for n in api.get("/notifications").json()["items"] if n["kind"] == "rehearsal"]
    assert "Automatic applying queued this rehearsal" in r["text"]
    assert "Approve again to submit" not in r["text"]
    with monkeypatch.context() as m:  # the pilot off: the rule is stopped; every page served
        m.setattr(get_settings(), "live_greenhouse_enabled", False)
        for path in (
            "/notifications",
            "/questions",
            "/applications",
            f"/applications/{app_id}/package",
        ):
            assert api.get(path).status_code == 200, path
        # Stopped, and nothing to execute it through: no "step 4 too" (the binding's guard).
        assert held(api, app_id) == (("waits", "stopped", False),) * 2
    assert receiver.ledger()["accepted"] == 0
    pilot_on()  # step 4 recorded
    assert api.get("/auto-apply").json()["submits"] is True
    assert held(api, app_id) == (("continues", None, False),) * 2
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    assert held(api, app_id) == ((None, None, False),) * 2  # final: its own words
    assert tick() == 0 and receiver.ledger()["accepted"] == 1


def test_d171_a_paused_submission_waits_for_the_permission_and_is_never_counted_as_tried(
    api, receiver
):
    # Shown as waiting for step 4, with why, never as continued; the form is read again meanwhile
    # (step 1) with one message, not a new one; that version is not counted as tried: once step 4
    # is recorded it is tried once more, and sent once.
    job, app_id = submission_paused(api, receiver)
    assert_waits(api, app_id, "submit_not_permitted")
    key = pause_shown(api, app_id)[0]["key"]
    reads = requests_made(receiver)
    assert tick() == 0  # read again (step 1): no difference
    assert requests_made(receiver) > reads
    (p,) = pause_rows(app_id)
    assert p.status == "unexplained"
    assert pause_shown(api, app_id)[0]["key"] == key  # the same message
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("unexplained", None)  # never counted as tried
    assert ("continued", "form_tried_again") not in events(job)
    assert scopes(app_id) == ["disclose_only", "submit"]  # nothing approved since the pause
    assert_waits(api, app_id, "submit_not_permitted")
    pilot_on()  # step 4 recorded
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    assert tick() == 1
    assert events(job)[-2:] == [
        ("continued", "form_tried_again"),
        ("approved_submit", "submission_queued"),
    ]
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d171_an_open_question_and_step_4_are_both_said(api, receiver):
    # The paused submission read again (no difference) and a question open again: it waits for the
    # answer and for step 4, both said in the same words and linked to Questions, as the step
    # checks them; answered, it waits for step 4 alone.
    job, app_id = submission_paused(api, receiver)
    assert tick() == 0 and pause_rows(app_id)[-1].status == "unexplained"
    r = api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_8101"})
    assert r.status_code == 200, r.text
    assert_waits(api, app_id, "questions", step4=True)
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    assert_waits(api, app_id, "questions", step4=True)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "question_8101", "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200, r.text
    assert_waits(api, app_id, "submit_not_permitted")
    assert receiver.ledger()["accepted"] == 0


def test_d171_a_paused_rehearsal_is_continued_under_a_permission_for_rehearsals_only(api, receiver):
    # The employer's rehearsal itself stopped on a changed form: its next approval is a rehearsal
    # again, which the permission covers, so the rule continues it by itself (and says so); it
    # stops before the submission.
    job, app_id = form_change_pause(api, receiver)
    pilot_on(permitted=REHEARSALS_ONLY)
    note, continues = pause_shown(api, app_id)
    assert continues is True and note["needs_action"] is False
    assert rule_of(api, app_id) == [("continues", None)] * 2
    continued_by_itself(job)
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    assert receiver.ledger()["accepted"] == 0


def test_d171_a_held_application_is_followed_whatever_its_jobs_age(api, receiver, monkeypatch):
    # Held for step 4, it is examined first in each tick, whatever came after it: newer jobs
    # pushing it out of the newest never stall it, to be sent when they close, long after the
    # owner may have applied by hand. Step 4 recorded, it is submitted at the next step, once.
    job, app_id = rehearsed_and_held(api)
    monkeypatch.setattr(service, "JOBS_PER_TICK", 1)
    newer = api.post("/jobs", json=OTHER_ROLE).json()["job"]["id"]
    with SessionLocal() as db:
        examined = [j.id for j in service._candidates(db, db.get(User, owner_id()))]
    assert examined == [uuid.UUID(job), uuid.UUID(newer)]
    pilot_on()  # step 4 recorded
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d171_a_rehearsal_that_no_longer_counts_is_not_repeated_before_step_4(api, receiver):
    # The employer's rehearsal held, then went stale (older than its maximum age): another one
    # would enter the owner's data on the employer's page again for nothing, and use one of the
    # permission's attempts. Held instead; once step 4 is recorded the rule rehearses again first
    # (E6), then submits once.
    job, app_id = rehearsed_and_held(api)
    days = get_settings().rehearsal_max_age_days + 1
    with SessionLocal() as db:
        r = RehearsalRecord
        db.execute(update(r).where(r.application_id == uuid.UUID(app_id))
                   .values(recorded_at=r.recorded_at - timedelta(days=days)))  # fmt: skip
        db.commit()
    disclosed = len(receiver.ledger()["disclosures"])
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    assert scopes(app_id) == ["disclose_only"]
    assert len(receiver.ledger()["disclosures"]) == disclosed
    assert held(api, app_id) == (("waits", "submit_not_permitted", False),) * 2
    pilot_on()  # step 4 recorded
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d171_held_for_step_4_before_the_daily_cap(api, receiver, monkeypatch):
    # Today's approvals used up (by rehearsals elsewhere, say): it is still held for step 4, never
    # "it continues tomorrow", and the notes never alternate between the two.
    job, app_id = rehearsed_and_held(api)
    with monkeypatch.context() as m:
        m.setattr(service, "cap_used", lambda db, user_id, now=None: 5)
        assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    assert ("skipped", "daily_cap") not in events(job)


def test_d171_a_held_application_with_a_question_open_says_both(api, receiver):
    # Held for step 4 with no pause, and a question open again: its page and row say it waits for
    # the answer and for step 4, and the feed's "questions are waiting" never says it continues
    # by itself once they are answered.
    job, app_id = rehearsed_and_held(api)
    r = api.post(f"/applications/{app_id}/answers/clear", json={"key": "question_8101"})
    assert r.status_code == 200, r.text
    assert tick() == 0 and events(job)[-1] == ("skipped", "open_questions")
    assert held(api, app_id) == (("waits", "questions", True),) * 2
    items = api.get("/notifications").json()["items"]
    (item,) = [n for n in items if n["kind"] == "auto_apply_questions"]
    assert item["application_id"] == app_id
    assert (
        "it submits nothing until your recorded permission covers submitting (step 4) for your "
        "standing rule" in item["text"]
    )
    assert "continues by itself" not in item["text"]
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "question_8101", "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200, r.text
    assert held(api, app_id) == (("waits", "submit_not_permitted", False),) * 2


# --------------------------- D172: whose approvals a recorded permission covers


def test_d172_your_own_step_4_never_lets_the_rule_submit(api, receiver):
    """D172: steps 1-3 recorded for the standing rule's packages and all four for your own: the
    rule rehearses, then holds the application for step 4 (D171), while your own approval to
    submit it is queued and sent, once."""
    pilot_on(permitted=REHEARSALS_ONLY, approvers={authorizations.RULE})
    pilot_add(PILOT_PERMISSIONS, approvers={authorizations.OWNER})
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 0 and events(job)[-1] == ("skipped", "submit_not_permitted")
    state = api.get("/auto-apply").json()
    assert (state["submits"], state["submits_yours"]) == (False, True)  # yours is still sent
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"], "scope": "submit"}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    assert tick() == 0 and receiver.ledger()["accepted"] == 1


def test_d172_a_permission_for_your_own_approvals_only_stops_the_rule(api, receiver):
    """D172: every step recorded for your own approvals only: the standing rule reads nothing
    and approves nothing, and says it cannot act."""
    pilot_on(approvers={authorizations.OWNER})
    synthetic_candidate(api)
    job = v2_job(api)
    assert tick() == 0 and events(job) == [] and receiver.ledger()["requests"] == []
    state = api.get("/auto-apply").json()
    assert state["active"] is False and state["unavailable"]["code"] == "not_authorized"
    assert state["unavailable"]["message"] == live.WHY["owner_only"]
    assert state["submits"] is False
    pilot_on(permitted=())  # nothing recorded at all: the words say so
    assert api.get("/auto-apply").json()["unavailable"]["message"] == live.WHY["not_authorized"]


def test_d172_the_rules_attempt_limit_is_that_of_its_own_entries(api, receiver, monkeypatch):
    """D112's limit, D172: of the entries covering the standing rule's approvals. Yours (1) used
    up stops your own attempts, not the rule: its card shows its own (5) and it approves."""
    pilot_on(approvers={authorizations.OWNER}, max_attempts=1)
    pilot_add(PILOT_PERMISSIONS, approvers={authorizations.RULE}, max_attempts=5)
    monkeypatch.setattr(live, "attempts_used", lambda db, since, exclude=None: 1)
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    answer(api, app_of(api, job))
    state = api.get("/auto-apply").json()
    assert state["active"] is True and state["permission_attempts"] == {"used": 1, "of": 5}
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")


def test_d172_a_read_during_a_tick_needs_the_rules_own_permission(api, receiver, monkeypatch):
    """D170's read as the permission is now, D172: the standing rule's own. Its entry ends during
    a tick while yours still covers reading: the post is neither read for the rule nor noted."""
    pilot_on(approvers={authorizations.RULE})
    pilot_add(("read",), approvers={authorizations.OWNER})
    synthetic_candidate(api)
    job = v2_job(api)  # a new job: read first
    real = service._read_failed_recently

    def ends_now(db, job, now):
        pilot_on(permitted=("read",), approvers={authorizations.OWNER})  # the rule's entry ended
        return real(db, job, now)

    monkeypatch.setattr(service, "_read_failed_recently", ends_now)
    assert tick() == 0 and events(job) == [] and requests_made(receiver) == 0


def test_d172_a_permission_for_the_rules_approvals_only_lets_it_apply_start_to_finish(
    api, receiver
):
    """D172 (B9): every step recorded for the standing rule's approvals only: it reads, rehearses
    and submits by itself, once (the queue and both gates ask for the rule's own entries)."""
    pilot_on(approvers={authorizations.RULE})
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    answer(api, app_of(api, job))
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d172_your_own_approval_is_queued_only_under_your_own_permission(api, receiver):
    """D172 (both reviews): steps 1-3 recorded for your own approvals and all four for the rule's.
    The rule rehearses; you approve the submission yourself, which your permission does not
    cover: your queue is refused, and the rule, to which approving returns your approval, does
    not queue it either and says why, once (never "could not be queued" at each step). Once a
    permission names your own approvals for submitting, it is queued and sent, once."""
    pilot_on(permitted=REHEARSALS_ONLY, approvers={authorizations.OWNER})
    pilot_add(PILOT_PERMISSIONS, approvers={authorizations.RULE})
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"], "scope": "submit"}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and live.WHY["rule_only"] in r.json()["detail"]
    assert tick() == 0 and tick() == 0
    assert events(job)[-1] == ("skipped", "your_approval_not_permitted")
    assert events(job).count(("skipped", "your_approval_not_permitted")) == 1
    assert ("skipped", "queue_refused") not in events(job)
    assert receiver.ledger()["accepted"] == 0
    pilot_add(("submit",), approvers={authorizations.OWNER})  # your own approvals may submit
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_d172_your_own_approval_waits_while_your_attempt_limit_is_used(api, receiver, monkeypatch):
    """D172 (both reviews): your own entries' attempt limit used, not the rule's: the rule does not
    queue your approval, so no page is opened for an attempt the disclosure gate would refuse."""
    pilot_on(approvers={authorizations.OWNER}, max_attempts=1)
    pilot_add(PILOT_PERMISSIONS, approvers={authorizations.RULE}, max_attempts=5)
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    approve_yourself(api, app_id)  # a rehearsal, not queued
    monkeypatch.setattr(live, "attempts_used", lambda db, since, exclude=None: 1)
    reads = requests_made(receiver)
    assert tick() == 0 and events(job)[-1] == ("skipped", "your_approval_not_permitted")
    assert requests_made(receiver) == reads


def test_another_account_never_sees_or_triggers_the_owners_rule(api, other_api, receiver):
    pilot_on()  # the owner is the `api` account; `other_api` is not named
    synthetic_candidate(other_api)
    v2_job(other_api)
    assert tick() == 0 and events() == []
    state = other_api.get("/auto-apply").json()
    assert state["active"] is False and state["unavailable"]["code"] == "not_for_this_account"
    assert state["events"] == []


def test_d113_defaults_are_on_outside_tests_and_explicit_settings_win():
    """The owner's choice: Freehire discovery, the pilot switch and automatic applying are on
    by default outside tests; anything set explicitly (environment, .env) is kept as set."""
    from app.core.config import Settings

    for env in ("development", "production"):
        s = Settings(_env_file=None, env=env)
        assert (
            s.discovery_providers == ["freehire"] and s.freehire_base_url == "https://freehire.me"
        )
        assert s.live_greenhouse_enabled is True and s.auto_apply_enabled is True
        assert s.discovery_search_approves is True and s.discovery_search_watch_days == 90
    off = Settings(_env_file=None, env="production", discovery_providers=[],
                   live_greenhouse_enabled=False, auto_apply_enabled=False)  # fmt: skip
    assert (off.discovery_providers, off.live_greenhouse_enabled, off.auto_apply_enabled) == (
        [], False, False)  # fmt: skip
    t = Settings(_env_file=None, env="test")
    assert (t.discovery_providers, t.live_greenhouse_enabled, t.auto_apply_enabled) == (
        [], False, False)  # fmt: skip
    # D168: sole-owner mode follows the same rule (tests/test_debug_console.py).
    assert [Settings(_env_file=None, env=e).sole_owner for e in ("production", "test")] == [
        True, False]  # fmt: skip


# -- D114: every account is served; applying in someone's name needs that account's own choice --


def test_d114_every_account_may_use_the_pilot_and_opts_in_to_automatic_applying_itself(
    api, other_api, receiver, monkeypatch
):
    pilot_on()  # names only the `api` account as the server owner
    monkeypatch.setattr(get_settings(), "all_accounts", True)
    synthetic_candidate(other_api)
    job = v2_job(other_api)
    state = other_api.get("/auto-apply").json()
    assert state["unavailable"] is None  # the pilot serves this account too
    assert (state["paused"], state["chosen"], state["active"]) == (True, False, False)
    assert "in your name" in state["consent"]
    assert tick() == 0 and events(job) == []  # never in its name before it chose
    assert receiver.ledger()["requests"] == []
    state = other_api.put("/auto-apply", json={"paused": False}).json()
    assert (state["active"], state["chosen"]) == (True, True)
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]  # now it acts
    answer(other_api, app_of(other_api, job))
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert receiver.ledger()["accepted"] == 0


def test_d114_the_mailbox_and_the_owner_default_stay_the_owners(api, other_api, monkeypatch):
    from app.core import accounts
    from app.modules.inbox import service as inbox

    monkeypatch.setattr(get_settings(), "all_accounts", True)
    monkeypatch.setattr(get_settings(), "live_owner_emails", ["synthetic.user@example.com"])
    assert accounts.named("anyone@example.com", []) is True
    assert accounts.owner("anyone@example.com") is False
    src = open(inbox.__file__).read()
    # One mailbox token on the server, the owner's: never opened to every account. (Sole-owner
    # mode, D168, gives every account the Gmail features, and each reads only a mailbox it
    # connected itself: tests/test_debug_console.py.)
    assert "app.core.accounts" not in src and "all_accounts" not in src


def test_d168_in_sole_owner_mode_one_daily_cap_counts_every_account(
    api, other_api, receiver, monkeypatch
):
    """Every account is the owner's (D168), so the owner's daily cap is one cap for all of them:
    two accounts each with an application ready, a cap of 1, and only one is approved. Each
    account's page counts every account's approvals against it."""
    pilot_on()
    s = get_settings()
    monkeypatch.setattr(s, "sole_owner", True)
    jobs = []
    for client in (api, other_api):
        synthetic_candidate(client)
        jobs.append((client, v2_job(client)))
    assert tick() == 0  # each form read; each waits for its answers
    for client, job in jobs:
        answer(client, app_of(client, job))
    monkeypatch.setattr(s, "auto_apply_daily_cap", 1)
    assert tick() == 1
    last = sorted(events(job)[-1] for _, job in jobs)
    assert last == [("approved_rehearsal", "rehearsal_queued"), ("skipped", "daily_cap")]
    for client, _ in jobs:
        state = client.get("/auto-apply").json()
        assert (state["approved_today"], state["daily_cap"], state["cap_every_account"]) == (
            1, 1, True)  # fmt: skip
    # One owner again (D114): each account counts its own approvals, and another account acts
    # once it chose to.
    monkeypatch.setattr(s, "sole_owner", False)
    monkeypatch.setattr(s, "all_accounts", True)
    other_api.put("/auto-apply", json={"paused": False})
    assert tick() == 1
    assert [events(job)[-1][0] for _, job in jobs] == ["approved_rehearsal"] * 2


# ------------------------------------------------------------------ D134: your pause and revocation


def attempt_row(att_id: str) -> ExecutionAttempt:
    with SessionLocal() as db:
        return db.get(ExecutionAttempt, uuid.UUID(att_id))


def approvals(app_id: str) -> list[PackageApproval]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval)
            .where(PackageApproval.application_id == uuid.UUID(app_id))
            .order_by(PackageApproval.approved_at)
        ).all()


def owner_id() -> uuid.UUID:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == "synthetic.user@example.com"))


def ready(api) -> tuple[str, str]:
    """A job whose package the rule may approve: read, answered; nothing approved yet."""
    pilot_on()
    synthetic_candidate(api)
    job = v2_job(api)
    tick()
    app_id = app_of(api, job)
    answer(api, app_id)
    return job, app_id


def approve_yourself(api, app_id: str) -> None:
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"], "scope": "disclose_only"}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200


def test_pausing_stops_what_the_rule_queued_before_a_worker_takes_it(api, receiver):
    job, app_id = ready(api)
    assert tick() == 1  # a rehearsal queued, not yet taken by a worker
    att = latest_attempt()
    assert attempt_row(att).queued_by_rule is True
    assert [a.by_rule for a in approvals(app_id)] == [True]
    r = api.put("/auto-apply", json={"paused": True})
    assert r.status_code == 200, r.text
    assert r.json()["stopped"] == {"cancelled": 1, "stopped": 0, "in_flight": 0, "approvals": 1}
    assert runner.run_attempt(att, "w1") == "ignored"  # nothing left for a worker to take
    assert attempt_row(att).state == "cancelled"
    assert [a.invalidation_reason for a in approvals(app_id)] == [pk.PAUSED_RULE]
    assert api.get(f"/applications/{app_id}").json()["state"] == "awaiting_approval"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert tick() == 0  # paused: nothing new either
    # Resumed, the rule continues: a pause stopped this before anything was entered.
    api.put("/auto-apply", json={"paused": False})
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")


def test_pausing_stops_an_attempt_a_worker_holds_before_anything_is_entered(
    api, receiver, monkeypatch
):
    job, app_id = ready(api)
    assert tick() == 1
    att = latest_attempt()
    claim = svc.claim

    def claim_then_pause(aid, worker):
        gen = claim(aid, worker)
        assert api.put("/auto-apply", json={"paused": True}).status_code == 200
        return gen

    monkeypatch.setattr(svc, "claim", claim_then_pause)
    assert runner.run_attempt(att, "w1") not in ("rehearsed", "confirmed")
    assert attempt_row(att).state == "cancelled"
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    # Resumed, the rule continues it: the pause stopped it before anything was entered.
    monkeypatch.setattr(svc, "claim", claim)
    api.put("/auto-apply", json={"paused": False})
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")


def test_what_you_queued_yourself_is_never_stopped_by_a_pause(api, receiver):
    job, app_id = ready(api)
    approve_yourself(api, app_id)
    att = queue(api, app_id)
    assert attempt_row(att).queued_by_rule is False
    assert [a.by_rule for a in approvals(app_id)] == [False]
    r = api.put("/auto-apply", json={"paused": True})
    assert r.json()["stopped"] == {"cancelled": 0, "stopped": 0, "in_flight": 0, "approvals": 0}
    assert runner.run_attempt(att, "w1") == "rehearsed"
    assert receiver.ledger()["disclosures"]


def test_after_you_revoke_the_rule_never_approves_that_application_again(api, receiver):
    job, app_id = ready(api)
    approve_yourself(api, app_id)
    assert api.post(f"/applications/{app_id}/package/revoke").status_code == 200
    assert tick() == 0 and events(job)[-1] == ("skipped", "owner_revoked")
    assert all(a.invalidated_at is not None for a in approvals(app_id))  # none given again
    assert receiver.ledger()["disclosures"] == []


def test_switched_off_the_rules_queued_attempt_is_refused_when_a_worker_takes_it(
    api, receiver, monkeypatch
):
    job, app_id = ready(api)
    assert tick() == 1
    att = latest_attempt()
    monkeypatch.setattr(get_settings(), "auto_apply_enabled", False)
    assert runner.run_attempt(att, "w1") == "ignored"
    row = attempt_row(att)
    assert (row.state, row.outcome_detail) == ("failed_safe", svc.RULE_STOPPED)
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_a_pause_recorded_without_stopping_is_still_read_when_a_worker_takes_it(api, receiver):
    job, app_id = ready(api)
    assert tick() == 1
    att = latest_attempt()
    with SessionLocal() as db:  # paused, as an older version recorded it: nothing stopped
        db.add(AutoApplyPrefs(user_id=owner_id(), paused=True))
        db.commit()
    assert runner.run_attempt(att, "w1") == "ignored"
    assert attempt_row(att).outcome_detail == svc.RULE_STOPPED
    assert receiver.ledger()["disclosures"] == []


def test_a_pause_waits_for_a_job_being_queued_then_the_job_sees_it(api, receiver, monkeypatch):
    """The pause and the rule's step for one job are serialized: a pause waits for a job being
    approved and queued (then stops what it queued), and a job after the pause sees it."""
    job_id, app_id = ready(api)
    uid = owner_id()
    with SessionLocal() as tick_db, SessionLocal() as pause_db:
        service._hold(tick_db, uid)  # a tick's step for one job, in progress
        pause_db.execute(text("SET lock_timeout = '300ms'"))
        with pytest.raises(DBAPIError):  # the pause waits for it
            service.set_paused(pause_db, uid, True)
        pause_db.rollback()
        tick_db.commit()
        assert service.set_paused(pause_db, uid, True) is not None  # the step is done
        pause_db.commit()
    api.put("/auto-apply", json={"paused": False})
    # A pause recorded after a tick began, before its next job: that job reads it.
    candidates = service._candidates

    def candidates_then_pause(db, user):
        jobs = candidates(db, user)
        with SessionLocal() as other:
            service.set_paused(other, user.id, True)
            other.commit()
        return jobs

    monkeypatch.setattr(service, "_candidates", candidates_then_pause)
    with SessionLocal() as db:
        assert service.run_for(db, db.get(User, uid)) == 0
    assert approvals(app_id) == [] and receiver.ledger()["disclosures"] == []


def test_a_pause_never_touches_another_accounts_work(api, other_api, receiver):
    job, app_id = ready(api)
    assert tick() == 1
    att = latest_attempt()
    r = other_api.put("/auto-apply", json={"paused": True})
    assert r.json()["stopped"] == {"cancelled": 0, "stopped": 0, "in_flight": 0, "approvals": 0}
    assert attempt_row(att).state == "pending"


@pytest.mark.parametrize("withdraw", [False, True], ids=["sent", "withdrawn_before_the_run"])
def test_the_rule_sends_your_self_identification_and_withdrawing_it_stops_what_it_queued(
    api, receiver, withdraw
):
    """D139 (D122, D133): with your self-identification on, the rule approves the screening job
    once you have answered its other questions, and your gender reaches the employer as you
    stated it (the receiver's ledger). Turned off after the rule queued the submission, the
    approval is retired at once: the queued attempt is refused before any page is opened,
    nothing reaches the employer, and the rule never tries that application again."""
    pilot_on()
    synthetic_candidate(api)
    r = api.put("/profile/self-identification", json={"enabled": True, "labels": ["Male"]})
    assert r.status_code == 200, r.text
    job = v2_job(api, SCREEN_JOB)
    assert tick() == 0 and events(job) == [("skipped", "open_questions")]
    app_id = app_of(api, job)
    answer(api, app_id)
    for key in ("question_8111", "question_8112"):  # felony and sponsorship: yours to answer
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": {"label": "No"}})
        assert r.status_code == 200, r.text
    r = api.put(
        f"/applications/{app_id}/consents", json={"key": "question_8111", "choice": "disclose"}
    )
    assert r.status_code == 200, r.text
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")
    assert runner.run_attempt(latest_attempt(), "w1") == "rehearsed"
    assert tick() == 1 and events(job)[-1] == ("approved_submit", "submission_queued")
    aid = latest_attempt()
    if not withdraw:
        assert runner.run_attempt(aid, "w1") == "confirmed"
        (acc,) = receiver.ledger()["acceptances"]
        assert acc["fields"]["question_8113"] == "1"
        return
    r = api.put("/profile/self-identification", json={"enabled": False, "labels": ["Male"]})
    assert r.status_code == 200 and r.json()["applications_to_approve_again"] == 1, r.text
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert receiver.ledger()["accepted"] == 0
    assert tick() == 0 and events(job)[-1] == ("skipped", "attempt_stopped")
    assert receiver.ledger()["accepted"] == 0
