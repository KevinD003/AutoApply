"""D113: the owner's standing rule to apply automatically (app/modules/autoapply).

Against the local Greenhouse-style stand-in playing a real board through the pilot
(execution_harness.pilot_on); the receiver's ledger is the oracle for what was disclosed and
submitted. Synthetic data only."""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.autoapply import service
from app.modules.autoapply.models import AutoApplyEvent
from app.modules.execution import runner
from app.modules.execution.models import ExecutionAttempt
from tests.execution_harness import Receiver, pilot_on, synthetic_candidate
from tests.test_greenhouse_dom import v2_job

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
    receiver.config(mode="gh2_new_question")  # the page now asks something the data does not
    assert tick() == 1
    assert runner.run_attempt(latest_attempt(), "w1") == "failed_safe"
    receiver.config(mode="normal")
    assert tick() == 0 and events(job)[-1] == ("skipped", "attempt_stopped")
    assert receiver.ledger()["disclosures"] == []


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
    # One mailbox token on the server, the owner's: never opened to every account.
    assert "app.core.accounts" not in src and "all_accounts" not in src
