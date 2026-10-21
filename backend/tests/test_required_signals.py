"""Required fields: what the page shows is recorded signal by signal (HTML attribute, ARIA
attribute, group ARIA, label marker, group label marker), for attachments as for every other
control. The job data's requirement is never lowered. Execution is blocked only where it
would be unsafe: the page requires a field the approved package leaves empty. The receiver's
ledger is the oracle for what was disclosed."""

import sys

import pytest

from app.modules.execution import runner
from app.modules.preparation import gh_readonly as ro
from app.modules.preparation import greenhouse_dom as gdom
from tests.execution_harness import BASE, ROOT, Receiver, attempt, queue
from tests.test_greenhouse_dom import v2_application

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
NONE = {"html": False, "aria": False, "group_aria": False, "label_marker": False,
        "group_label_marker": False}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")


def mapping(receiver, mode):
    receiver.config(mode=mode)
    api = greenhouse_v2._api_json(BOARD, JOB, BASE)
    obs = ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api)
    return {f["key"]: f for f in obs["mapping"]["fields"]}


def test_signals_are_recorded_separately_for_attachments_and_other_controls(receiver):
    by = mapping(receiver, "normal")
    # Text input: ARIA plus a marker on its own label.
    assert by["first_name"]["required_signals"] == NONE | {"aria": True, "label_marker": True}
    # Attachment: ARIA on the input; its label is the group's label, so both markers.
    assert by["resume"]["required_signals"] == NONE | {
        "aria": True, "label_marker": True, "group_label_marker": True}  # fmt: skip
    assert by["cover_letter"]["required_signals"] == NONE  # optional, unmarked
    assert by["resume"]["required_evidence"] == "consistent"
    assert by["cover_letter"]["required_evidence"] == "consistent"


def test_group_level_marking_of_an_attachment_counts_as_a_signal(receiver):
    by = mapping(receiver, "gh2_required_group")
    s = by["resume"]["required_signals"]
    assert s["group_aria"] is True and s["aria"] is False
    assert by["resume"]["required_evidence"] == "consistent"


def test_an_unmarked_field_stays_required(receiver):
    by = mapping(receiver, "gh2_required_unmarked")
    assert by["first_name"]["required_signals"] == NONE
    assert by["first_name"]["required"] is True  # the job data's requirement stands
    assert by["first_name"]["required_evidence"] == "api_required_page_unmarked"


@pytest.mark.parametrize("mode", ["gh2_required_extra", "gh2_required_marker_only"])
def test_a_page_requirement_the_job_data_lacks_is_flagged(receiver, mode):
    f = mapping(receiver, mode)["cover_letter"]
    assert f["required"] is False and f["required_evidence"] == "page_required_api_optional"


def test_evidence_rule():
    assert gdom.required_evidence(True, NONE) == "api_required_page_unmarked"
    assert gdom.required_evidence(True, NONE | {"label_marker": True}) == "consistent"
    assert gdom.required_evidence(False, NONE | {"group_aria": True}) == (
        "page_required_api_optional"
    )
    assert gdom.required_evidence(True, None) == "not_observable"


# -- execution (fixture adapter, receiver oracle) --------------------------------------------


def answer_of(api, app_id, key):
    p = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return next(a for a in p["answers"] if a["key"] == key)["value"]


def test_api_required_field_unmarked_on_the_page_still_runs_with_its_answer(api, receiver):
    """No ARIA, no asterisk: not a prerequisite. The field keeps its requirement and its
    approved answer; this alone does not block execution."""
    receiver.config(mode="gh2_required_unmarked")
    aid = queue(api, v2_application(api))
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"]["first_name"]


@pytest.mark.parametrize("mode", ["gh2_required_extra", "gh2_required_marker_only"])
def test_page_requires_a_field_with_no_approved_answer_stops_before_disclosure(api, receiver, mode):
    receiver.config(mode=mode)
    app_id = v2_application(api)
    assert answer_of(api, app_id, "cover_letter") is None  # optional, no document approved
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "cover_letter: required by the page, no approved answer" in detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_page_requires_a_field_that_has_an_approved_answer(api, receiver):
    receiver.config(mode="gh2_required_answered")
    app_id = v2_application(api)
    assert answer_of(api, app_id, "question_8103")  # optional, answered from the profile
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["acceptances"][0]["fields"]["question_8103"]


# -- attachment groups, unreadable status, approval retirement ------------------------------


def test_resume_group_required_by_the_page_runs_with_its_document(api, receiver):
    """As on the real page (run #9): the resume is required by its group, not its input."""
    receiver.config(mode="gh2_required_group")
    aid = queue(api, v2_application(api))
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    assert [d["kind"] for d in led["disclosures"]].count("upload") == 1  # the resume only


def test_cover_letter_group_required_by_the_page_blocks_without_a_document(api, receiver):
    """Tested apart from the resume: the cover letter's group (file input and its text
    alternative) is marked required; the package has no cover letter, so it stops."""
    receiver.config(mode="gh2_required_cover_group")
    by = mapping(receiver, "gh2_required_cover_group")
    assert by["cover_letter"]["required_signals"]["group_aria"] is True
    assert by["cover_letter"]["required_evidence"] == "page_required_api_optional"
    assert by["resume"]["required_evidence"] == "consistent"
    receiver.reset()
    receiver.config(mode="gh2_required_cover_group")
    app_id = v2_application(api)
    assert answer_of(api, app_id, "cover_letter") is None
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "cover_letter: required by the page" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_unreadable_required_status_stops_safely(api, receiver, monkeypatch):
    receiver.config(mode="normal")
    aid = queue(api, v2_application(api))
    monkeypatch.setattr(gdom, "REQUIRED_SIGNALS_JS", "(id) => null")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert ": not readable" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_approval_bound_to_an_earlier_adapter_version_is_retired(api, receiver):
    """The required rule (v2) and the dropdown strategies (v3) changed what the adapter does:
    an approval given under an earlier version is refused at queueing and retired."""
    import uuid

    from app.core.db import SessionLocal
    from app.modules.execution import policy
    from app.modules.preparation.models import PackageApproval

    assert policy.ADAPTER_VERSIONS["greenhouse_dom"].startswith("greenhouse-dom-3+")
    app_id = v2_application(api)
    with SessionLocal() as db:
        a = (db.query(PackageApproval)
             .filter(PackageApproval.application_id == uuid.UUID(app_id))
             .order_by(PackageApproval.approved_at.desc()).first())  # fmt: skip
        a.adapter_version = "greenhouse-dom-1+" + gdom.EXTRACTION_VERSION
        db.commit()
        approval_id = a.id
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "changed after you approved" in r.text
    with SessionLocal() as db:
        assert db.get(PackageApproval, approval_id).invalidated_at is not None
    assert receiver.ledger()["disclosures"] == []
