"""D113: the owner's standing rule to apply automatically (app/modules/autoapply).

Against the local Greenhouse-style stand-in playing a real board through the pilot
(execution_harness.pilot_on); the receiver's ledger is the oracle for what was disclosed and
submitted. Synthetic data only."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.autoapply import service
from app.modules.autoapply.models import AutoApplyEvent, AutoApplyPrefs
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ApplicationPause, ExecutionAttempt
from app.modules.identity.models import User
from app.modules.preparation import package as pk
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import Receiver, pilot_on, queue, synthetic_candidate
from tests.test_greenhouse_dom import SCREEN_JOB, v2_job

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
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 0)
    assert tick() == 0 and events(job)[-1] == ("skipped", "daily_cap")
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 5)
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


def back_date_failed_reads(job: str, by: timedelta) -> None:
    """As if the failed reads of this job's post were `by` earlier (the limit is a day)."""
    with SessionLocal() as db:
        e = AutoApplyEvent
        failed = (e.job_id == uuid.UUID(job), e.reason == "capture_failed")
        db.execute(update(e).where(*failed).values(created_at=e.created_at - by))
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
    # The owner's decision: trying it again themselves, the rule continues from there.
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    receiver.config(mode="normal")
    assert tick() == 1 and runner.run_attempt(latest_attempt(), "w1") == "rehearsed"


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
    # The owner's decision: trying it again themselves, the rule continues from there.
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    assert tick() == 1 and events(job)[-1] == ("approved_rehearsal", "rehearsal_queued")


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
    back_date_failed_reads(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
    assert tick() == 0 and len(reads) == 2  # a day later: read again, failed again
    assert tick() == 0 and len(reads) == 2  # the limit counts from that failure, not the first
    back_date_failed_reads(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
    assert tick() == 0 and len(reads) == 3
    monkeypatch.setattr(service, "_capture", capture)
    back_date_failed_reads(job, service.RECAPTURE_AFTER + timedelta(minutes=1))
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
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 0)
    assert tick() == 0 and events(job)[-1] == ("skipped", "daily_cap")
    (p,) = pause_rows(app_id)
    assert (p.status, p.resolution) == ("unexplained", None)
    assert ("continued", "form_tried_again") not in events(job)
    monkeypatch.setattr(get_settings(), "auto_apply_daily_cap", 5)
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
    note, continues = shown()
    assert continues is False and note["needs_action"] is True
    assert "nothing is sent until you do" in note["text"]
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert tick() == 0 and tick() == 1  # read, then tried once more
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"  # stopped on it again
    assert tick() == 0 and tick() == 0 and events(job)[-1] == ("skipped", "form_kept_changing")
    note, continues = shown()
    assert continues is False and note["needs_action"] is True
    assert "apply on the employer's site" in note["text"]


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
            select(PackageApproval).where(PackageApproval.application_id == uuid.UUID(app_id))
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
