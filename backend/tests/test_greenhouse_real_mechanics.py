"""D116: Greenhouse real-page mechanics, rebuilt from the legacy bot's notes (legacy apply.py)
and tested against the receiver's `gh2_live_like` mode, which plays them (FIXTURE ASSUMPTIONS,
never observed by NoEfforts): a form that declares no submit address and posts to its own job
page, uploads acknowledged only by the file's name in its field, an emailed security code
(the code comes only from the user's checkpoint), the page's own validation blocking the click,
and a confirmation page. The receiver's ledger is the oracle. Synthetic data only."""

import json

import pytest

from app.modules.execution import runner
from tests.execution_harness import attempt, queue
from tests.test_execution_security import open_checkpoint, start_worker, wait_for
from tests.test_greenhouse_dom import kinds, live_application, v2_application

CODE = "AB12CD34"


@pytest.fixture(autouse=True)
def _live_like(receiver):
    receiver.config(mode="gh2_live_like", ll_code="none")


@pytest.fixture(scope="module")
def receiver():
    from tests.execution_harness import Receiver

    r = Receiver()
    yield r
    r.stop()


def form(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]["content"]


@pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])
def test_a_form_without_a_submit_address_is_bound_to_its_own_job_page(api, receiver, make):
    """Captured without `data-submit-path`: the submit address is the job page itself; the
    upload is acknowledged by its file name; the confirmation page follows this POST."""
    app_id = make(api)
    dest = form(api, app_id)["destination"]
    assert dest["submit_url"].endswith("/gh2/northwind/jobs/5020001")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and kinds(led) == {"upload": 1}
    sent = led["acceptances"][0]["fields"]
    up = json.loads(led["disclosures"][0]["detail"])
    assert sent["resume_attachment_id"] == up["attachment_id"]
    assert sent["preferred_name"] == "Sammy" and sent["question_8101"] == "1"
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_a_form_that_starts_declaring_another_address_stops_before_anything_is_sent(api, receiver):
    app_id = v2_application(api)  # captured bound to the job page
    receiver.config(mode="normal")  # now the form declares .../submit
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert "different address" in attempt_of(api, app_id).outcome_detail
    assert receiver.ledger()["disclosures"] == []


def attempt_of(api, app_id):
    aid = api.get(f"/applications/{app_id}/attempts").json()[0]["id"]
    return attempt(aid)


def test_the_pages_own_checks_blocking_the_click_is_rejected_with_nothing_sent(api, receiver):
    app_id = v2_application(api)
    receiver.config(mode="gh2_live_like", ll_code="none", ll_invalid=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "rejected"
    assert "nothing was sent" in attempt_of(api, app_id).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and kinds(led) == {"upload": 1}  # the upload alone left


def test_an_upload_the_page_marks_failed_stops_after_the_upload_and_never_submits(api, receiver):
    app_id = v2_application(api)
    receiver.config(mode="gh2_live_like", ll_code="none", upload_fail_field="resume")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_the_security_code_wrong_then_right_comes_only_from_the_users_checkpoint(api, receiver):
    """The first click asks for the emailed code: a checkpoint; a wrong code is reported by
    the page and asked again; the right one is typed into the 8 boxes and sent once."""
    app_id = v2_application(api)
    receiver.config(mode="gh2_live_like", ll_code="after_click", ll_code_value=CODE)
    aid = queue(api, app_id)
    w = start_worker(aid, "w-ll")
    cp = open_checkpoint(api, app_id, 1)
    assert receiver.ledger()["accepted"] == 0
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                 json={"round": 1, "code": "ZZ99ZZ99"})  # fmt: skip
    assert r.status_code == 202
    cp2 = open_checkpoint(api, app_id, 2)
    wait_for(lambda: [d for d in receiver.ledger()["disclosures"] if d["kind"] == "code_wrong"])
    r = api.post(f"/applications/{app_id}/checkpoints/{cp2['id']}/code",
                 json={"round": 2, "code": CODE.lower()})  # fmt: skip
    assert r.status_code == 202
    out, err = w.communicate(timeout=90)
    assert out.strip() == "confirmed", err[-800:]
    led = receiver.ledger()
    assert led["accepted"] == 1
    assert kinds(led) == {"upload": 1, "code_requested": 1, "code_wrong": 1}
    assert CODE not in out + err


def test_a_code_asked_for_before_the_click_is_a_checkpoint_not_a_new_question(api, receiver):
    """Legacy notes: the code can be emailed once the address is typed, so its boxes appear
    while filling. They are recognised (not "the form has changed"); nothing is clicked until
    the user gives the code."""
    app_id = v2_application(api)
    receiver.config(mode="gh2_live_like", ll_code="before_click", ll_code_value=CODE)
    aid = queue(api, app_id)
    w = start_worker(aid, "w-ll2")
    cp = open_checkpoint(api, app_id, 1)
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                 json={"round": 1, "code": CODE})  # fmt: skip
    assert r.status_code == 202
    out, err = w.communicate(timeout=90)
    assert out.strip() == "confirmed", err[-800:]
    assert receiver.ledger()["accepted"] == 1
