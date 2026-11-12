"""D154: before the send gate, what the page itself would refuse at the final click stops the
attempt with nothing sent; and after a page's answers are entered, what they started is waited
for before the checks. Through the runner against the stand-ins' FIXTURE ASSUMPTIONS (FA8 in
fixtures/ats_receiver/workday_like.py, the page_check settings of greenhouse_v2.py), never a
real page. The receiver's own ledger is the oracle for what reached the employer: its
acceptances, its draft rows and the POSTs it logged, never NoEfforts' tables. Synthetic
candidate data only.

Before D154 each case below reached the final click: the browser refused it (no request:
`unknown`, quarantined), the page's own script refused it (`rejected` after `sending`), or the
click could not be made (`unknown`); a rehearsal of such a page was recorded as passing."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import fixture_ats as fa
from app.modules.execution.models import ApplicationPause, RehearsalRecord
from tests.execution_harness import Receiver, attempt, queue
from tests.test_execution_security import open_checkpoint, start_worker
from tests.test_greenhouse_dom import v2_application
from tests.test_workday_adapter import fresh_url, workday_application
from tests.test_workday_follow_up import follow_up_application
from tests.test_workday_wizard import approvals, draft_pages, posts, wizard_application

CODE = "AB12CD34"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def run(api, app_id: str) -> tuple[str, str]:
    aid = queue(api, app_id)
    return runner.run_attempt(aid, "w1"), aid


def nothing_sent(led, path: str) -> bool:
    """No acceptance and no final POST logged by the receiver."""
    return led["accepted"] == 0 and posts(led, path) == 0


def stopped_after_entry(aid: str, app_id: str) -> bool:
    """Abandoned before the send gate, every approval retired with the stop (D132)."""
    att = attempt(aid)
    found = approvals(app_id)
    return (
        att.state == "abandoned"
        and att.disclosure_started_at is not None
        and att.send_started_at is None
        and bool(found)
        and all(a.invalidated_at is not None for a in found)
    )


def single(api, receiver, check: str, **kw) -> str:
    """A Workday-style single page with this check, captured, answered and approved."""
    receiver.config(page_check=check)
    return workday_application(api, url=fresh_url(), **kw)


# ---------------------------------------------------------------------------- Workday-style


@pytest.mark.parametrize("check, part", [
    ("pattern", "1 value(s) it does not accept"),
    ("custom_error", "1 field(s) it marks as not valid"),
], ids=["pattern", "custom_error"])  # fmt: skip
def test_a_value_the_browser_would_refuse_stops_before_the_send_gate(api, receiver, check, part):
    app_id = single(api, receiver, check)
    out, aid = run(api, app_id)
    assert out == "abandoned"
    assert nothing_sent(receiver.ledger(), "/apply")
    assert stopped_after_entry(aid, app_id)
    detail = attempt(aid).outcome_detail
    assert fa.PAGE_WOULD_REFUSE in detail and part in detail
    assert "phone" not in detail.lower() and "555" not in detail  # counts only


def test_a_submit_button_the_page_keeps_disabled_stops_before_the_send_gate(api, receiver):
    app_id = single(api, receiver, "button_disabled")
    out, aid = run(api, app_id)
    assert out == "abandoned" and fa.FINAL_BUTTON_UNAVAILABLE in attempt(aid).outcome_detail
    assert nothing_sent(receiver.ledger(), "/apply") and stopped_after_entry(aid, app_id)


def test_a_submit_button_enabled_a_second_after_the_last_answer_is_waited_for(api, receiver):
    app_id = single(api, receiver, "button_late_enable")
    out, _ = run(api, app_id)
    assert out == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_a_follow_up_shown_after_a_request_pauses_for_your_answer(api, receiver):
    """D148's limit: the page reacts to the shift only once its request is answered. The wait
    after filling sees the follow-up shown and required, with no approved answer: the single
    page pauses so you can answer it (D135), with nothing sent."""
    receiver.config(page_check="late_follow_up")
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required", single=True)
    out, aid = run(api, app_id)
    assert out == "abandoned"
    assert nothing_sent(receiver.ledger(), "/apply")
    with SessionLocal() as db:
        pause = db.scalar(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert (pause.kind, pause.status, pause.detail) == (
            "conditional_required", "open", {"required": 1})  # fmt: skip
    assert attempt(aid).send_started_at is None


def test_a_follow_up_shown_after_a_request_stops_a_wizard_before_its_pages_next(api, receiver):
    """On a wizard the same follow-up, on page 4, ends the attempt before page 4's Next (a
    wizard never pauses, D142): page 4 is never sent."""
    receiver.config(page_check="late_follow_up")
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required")
    out, aid = run(api, app_id)
    assert out == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3] and nothing_sent(led, "/apply")
    assert attempt(aid).outcome_detail.endswith(fa.CONDITIONAL_REQUIRED)


def test_a_wizard_whose_review_page_refuses_an_earlier_page_stops_before_the_send_gate(
    api, receiver
):
    """The browser validates every page of the form at the final click, the hidden ones too:
    on the review page the page's script refuses page 1's phone."""
    receiver.config(page_check="late_invalid")
    app_id = wizard_application(api, receiver, "plain")
    out, aid = run(api, app_id)
    assert out == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and nothing_sent(led, "/apply")
    assert "1 field(s) it marks as not valid" in attempt(aid).outcome_detail


@pytest.mark.parametrize("wizard", [None, "plain"], ids=["single_page", "wizard"])
def test_a_page_still_loading_after_the_answers_stops_before_its_checks(
    api, receiver, monkeypatch, wizard
):
    monkeypatch.setattr(runner, "SETTLE_LOAD_MS", 1500)
    receiver.config(page_check="slow_after_entry", page_check_delay_ms=4000, wizard=wizard)
    app_id = workday_application(api, url=fresh_url())
    out, aid = run(api, app_id)
    assert out == "abandoned" and runner.STILL_LOADING in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert draft_pages(led) == [] and nothing_sent(led, "/apply")


def test_a_rehearsal_of_a_page_that_would_refuse_the_click_is_never_recorded(api, receiver):
    app_id = single(api, receiver, "custom_error", scope="disclose_only")
    out, aid = run(api, app_id)
    assert out == "abandoned" and fa.PAGE_WOULD_REFUSE in attempt(aid).outcome_detail
    with SessionLocal() as db:
        assert db.scalar(select(RehearsalRecord).where(
            RehearsalRecord.attempt_id == uuid.UUID(aid))) is None  # fmt: skip
    assert nothing_sent(receiver.ledger(), "/apply")


# ---------------------------------------------------------------------------- Greenhouse v2


def v2(api, receiver, check: str) -> str:
    """The v2 stand-in's application, captured and approved, then the check switched on (the
    page as it is at the run)."""
    app_id = v2_application(api)
    receiver.config(page_check=check)
    return app_id


@pytest.mark.parametrize("check", ["aria_invalid", "check_validity"])
def test_a_field_the_pages_own_script_refuses_stops_before_the_send_gate(api, receiver, check):
    app_id = v2(api, receiver, check)
    out, aid = run(api, app_id)
    assert out == "abandoned"
    assert nothing_sent(receiver.ledger(), "/submit") and stopped_after_entry(aid, app_id)
    detail = attempt(aid).outcome_detail
    assert "1 field(s) it marks as not valid" in detail and "example" not in detail


def test_a_hidden_field_a_novalidate_page_never_reads_is_not_counted(api, receiver):
    """The page decides (`novalidate`): a hidden field its markup would refuse is never read or
    sent by the page, and the application goes through."""
    app_id = v2(api, receiver, "hidden_invalid")
    out, _ = run(api, app_id)
    assert out == "confirmed" and receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize("check, reason", [
    ("two_submit", "SUBMIT_UNIDENTIFIED"),
    ("button_disabled", "FINAL_BUTTON_UNAVAILABLE"),
], ids=["two_submit", "button_disabled"])  # fmt: skip
def test_a_final_click_that_cannot_be_made_stops_before_the_send_gate(api, receiver, check, reason):
    app_id = v2(api, receiver, check)
    out, aid = run(api, app_id)
    assert out == "abandoned" and getattr(fa, reason) in attempt(aid).outcome_detail
    assert nothing_sent(receiver.ledger(), "/submit")


def test_a_v2_submit_button_enabled_a_second_later_is_waited_for(api, receiver):
    app_id = v2(api, receiver, "button_late_enable")
    out, _ = run(api, app_id)
    assert out == "confirmed" and receiver.ledger()["accepted"] == 1


def test_security_code_boxes_shown_before_the_click_are_left_for_the_checkpoint(api, receiver):
    """D116: the code's boxes appear once the address is typed, required by the page here; they
    are filled only from your checkpoint, so they never count against the form."""
    receiver.config(
        mode="gh2_live_like",
        ll_code="before_click",
        ll_code_value=CODE,
        ll_invalid=False,
        upload_fail_field=None,
        page_check="code_boxes_required",
    )
    app_id = v2_application(api)  # captured as it declares itself (no submit address)
    aid = queue(api, app_id)
    w = start_worker(aid, "w-d154")
    cp = open_checkpoint(api, app_id, 1)
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                 json={"round": 1, "code": CODE})  # fmt: skip
    assert r.status_code == 202
    out, err = w.communicate(timeout=90)
    assert out.strip() == "confirmed", err[-800:]
    assert receiver.ledger()["accepted"] == 1
