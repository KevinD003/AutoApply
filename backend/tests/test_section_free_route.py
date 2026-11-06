"""The section-free Greenhouse route end to end, on synthetic data (D129 and D130 together), through
the pilot's own path with the approximation playing a board host:

    capture -> locked-identity verification -> optional phone omission -> approved answers and
    documents -> readback -> rehearsal stop -> a separately approved, single submission

The receiver's own ledger is the only oracle for what reached the "employer" (never NoEfforts'
tables). The form is a FIXTURE (fixtures/ats_receiver/greenhouse_v2.py, mode gh2_phone_companion
with `email_locked`): passing here shows that the combined code paths work together. It does not
show that any real posting is supported.

The other safeguards keep their own suites and are not weakened here: uploads
(test_upload_evidence.py), late controls (test_greenhouse_controls.py, test_phone_companion.py),
cancellation (test_execution_failures.py) and uncertain outcomes (test_greenhouse_dom.py,
test_execution_failures.py). Two of them are repeated below on this very form."""

import json
import sys

import pytest

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.preparation.resolver import PHONE_OMITTED
from tests.execution_harness import ROOT, Receiver, attempt, pilot_on, queue
from tests.test_approval_binding import approval_of
from tests.test_execution_failures import start_blocked_worker, wait_for
from tests.test_execution_validation import release
from tests.test_greenhouse_controls import content, prepare
from tests.test_greenhouse_dom import BOARD, kinds

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))

MODE = "gh2_phone_companion"
PICKER = "phone-cc-input"
EMAIL = "sam.synthetic@example.com"  # the synthetic candidate's address, pre-filled and locked


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.fixture
def rehearsal_rule(monkeypatch):
    """As for a real board: the first submission on this path needs a recorded rehearsal (E6)."""
    monkeypatch.setattr(
        get_settings(), "execution_test_rehearsal_rule_paths", [f"greenhouse_live:{BOARD}"]
    )


def approve(api, app_id, scope):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"],
                          "scope": scope})  # fmt: skip


def readback(api, app_id, aid) -> dict:
    att = next(a for a in api.get(f"/applications/{app_id}/attempts").json() if a["id"] == aid)
    return next(e for e in att["evidence"] if e["kind"] == "readback")["data"]


def uploads(receiver) -> list[dict]:
    led = receiver.ledger()
    return [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "upload"]


def test_the_section_free_route_on_synthetic_data(api, receiver, rehearsal_rule):
    receiver.config(mode=MODE, pcm="", email_locked=True)
    pilot_on()

    # 1. Capture: the pilot reads the job data and the page (GETs only, nothing of yours sent).
    _, app_id = prepare(api)
    c = content(api, app_id)
    assert not c["unresolved"], c["unresolved"]
    rows = {a["key"]: a for a in c["answers"]}
    assert receiver.ledger()["disclosures"] == []

    # 2. Review: the locked email is the approved identity; the optional phone is shown as
    #    omitted (not as your choice, not as a profile preference); its control is not asked.
    assert rows["email"]["value"] == {"text": EMAIL}
    assert (rows["phone"]["status"], rows["phone"]["value"]) == ("blank_optional", None)
    assert rows["phone"]["explanation"].startswith(PHONE_OMITTED)
    assert (rows[PICKER]["status"], rows[PICKER]["widget"]) == ("blank_optional", "phone_companion")
    assert api.get("/profile").json()["phone"] == "+1 555 0100"  # the profile is unchanged
    resume = next(d for d in c["documents"] if d["field"] == "resume")["sha256"]

    # 3. No submission before a rehearsal on this path.
    r = approve(api, app_id, "submit")
    assert r.status_code == 409 and "(reason: no_rehearsal)" in r.text

    # 4. Rehearsal: approved to disclose only. The page's locked email is verified, never typed;
    #    the approved answers and the approved resume go in; the readback is clean; it stops
    #    before the send gate.
    assert approve(api, app_id, "disclose_only").status_code == 200
    assert approval_of(app_id).adapter == "greenhouse_live"
    rid = queue(api, app_id)
    assert runner.run_attempt(rid, "w1") == "rehearsed", attempt(rid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []
    assert kinds(led) == {"upload": 1}
    assert [u["sha256"] for u in uploads(receiver)] == [resume]  # the approved bytes
    assert readback(api, app_id, rid)["mismatched"] == 0

    # 5. The rehearsal is not permission to submit: a separate approval is needed.
    #    After the rehearsal the application waits for you; nothing queues it on its own.
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 400 and "needs_user_action" in r.text
    assert receiver.ledger()["accepted"] == 0
    assert approve(api, app_id, "submit").status_code == 200
    sid = queue(api, app_id)
    assert runner.run_attempt(sid, "w1") == "confirmed", attempt(sid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1
    fields = led["acceptances"][0]["fields"]
    # The page's own locked value, checked before disclosure. The field is disabled on this page,
    # so a confirmed run is itself the proof that nothing tried to type into it (D129).
    assert fields["email"] == EMAIL
    assert "phone" not in fields  # omitted: nothing entered, nothing sent
    assert fields[PICKER] == "US" and fields["fx_companion_touched"] == "0"  # never touched
    assert fields["preferred_name"] == "Sammy"
    assert (fields["question_8101"], fields["question_8104"]) == ("1", "0")  # Yes, No
    assert [u["sha256"] for u in uploads(receiver)] == [resume, resume]
    assert readback(api, app_id, sid)["mismatched"] == 0

    # 6. Single: nothing sends it again.
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code != 200
    assert receiver.ledger()["accepted"] == 1


def test_a_control_that_appears_after_approval_stops_it_before_anything_is_entered(api, receiver):
    """A late control on this form (a second one in the phone's group) is never filled around."""
    receiver.config(mode=MODE, pcm="", email_locked=True)
    _, app_id = prepare(api)
    assert approve(api, app_id, "submit").status_code == 200
    receiver.config(mode=MODE, pcm="two", email_locked=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "changed since you approved" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_cancelling_before_the_send_gate_still_wins_on_this_form(api, receiver):
    receiver.config(mode=MODE, pcm="", email_locked=True)
    _, app_id = prepare(api)
    assert approve(api, app_id, "submit").status_code == 200
    aid = queue(api, app_id)
    w, gate = start_blocked_worker(aid, "w1", "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    assert api.post(f"/applications/{app_id}/cancel").json()["state"] == "cancelled"
    assert release(w, gate) == "lost_authority"
    assert receiver.ledger()["accepted"] == 0
