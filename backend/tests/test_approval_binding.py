"""An approval is bound to the execution method it was given for (adapter + adapter version).

The package hash protects destination, form fingerprint, document digests and answers, but not
*how* NoEfforts executes them. These tests show that an approval cannot silently run through a
different adapter or changed adapter semantics, and that approvals are retired only when that
meaning actually changes. The receiver's ledger is the oracle for "nothing was sent"."""

import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.execution import policy, runner
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import Receiver, attempt, queue
from tests.test_greenhouse_adapter import gh_application
from tests.test_greenhouse_dom import v2_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def approval_of(app_id) -> PackageApproval:
    with SessionLocal() as db:
        return (
            db.query(PackageApproval)
            .filter(PackageApproval.application_id == uuid.UUID(app_id))
            .order_by(PackageApproval.approved_at.desc())
            .first()
        )


def set_approval(app_id, **cols):
    with SessionLocal() as db:
        a = db.get(PackageApproval, approval_of(app_id).id)
        for k, v in cols.items():
            setattr(a, k, v)
        db.commit()


def try_queue(api, app_id):
    return api.post(f"/applications/{app_id}/transition", json={"to": "queued"})


def reapprove(api, app_id):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def test_approval_records_the_execution_method(api, receiver):
    a = approval_of(gh_application(api))
    assert (a.adapter, a.adapter_version) == (
        "greenhouse_hosted",
        policy.ADAPTER_VERSIONS["greenhouse_hosted"],
    )
    assert approval_of(v2_application(api)).adapter == "greenhouse_dom"


def test_original_adapter_approval_cannot_run_through_a_new_route(api, receiver, monkeypatch):
    """Simulates a code change that routes original-structure forms to the id-mapping adapter.
    The approval was given for the original adapter: queueing is refused, the approval is
    retired, nothing reaches the employer, and the same content can be approved again."""
    app_id = gh_application(api)
    original = policy.adapter_for
    monkeypatch.setattr(
        policy,
        "adapter_for",
        lambda d: "greenhouse_dom" if d.get("form_source") == "greenhouse_api" else original(d),
    )
    r = try_queue(api, app_id)
    assert r.status_code == 409 and "changed after you approved" in r.text
    with SessionLocal() as db:
        assert not db.query(ExecutionAttempt).filter_by(application_id=uuid.UUID(app_id)).count()
    retired = approval_of(app_id)
    assert retired.invalidated_at is not None
    assert retired.invalidation_reason == "execution method changed after approval"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert reapprove(api, app_id).status_code == 200
    assert approval_of(app_id).adapter == "greenhouse_dom"  # the new approval names it


def test_semantics_change_after_queueing_stops_before_disclosure(api, receiver, monkeypatch):
    aid = queue(api, gh_application(api))
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_hosted", "greenhouse-hosted-2+x")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "execution method changed" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_attempt_recorded_for_another_adapter_is_refused(api, receiver):
    """An approval for the id-mapping adapter does not authorize the original adapter either."""
    aid = queue(api, v2_application(api))
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).adapter = "greenhouse_hosted"
        db.commit()
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_pre_binding_approval_stays_valid_while_its_meaning_is_unchanged(api, receiver):
    app_id = gh_application(api)
    set_approval(app_id, adapter=None, adapter_version=None)  # as given before this change
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_pre_binding_approval_is_retired_when_its_adapter_changes(api, receiver, monkeypatch):
    app_id = gh_application(api)
    set_approval(app_id, adapter=None, adapter_version=None)
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_hosted", "greenhouse-hosted-2+x")
    assert try_queue(api, app_id).status_code == 409
    assert approval_of(app_id).invalidated_at is not None
    assert receiver.ledger()["disclosures"] == []
    assert reapprove(api, app_id).status_code == 200
    assert approval_of(app_id).adapter_version == "greenhouse-hosted-2+x"


def test_unrelated_adapter_change_does_not_retire_approvals(api, receiver, monkeypatch):
    app_id = gh_application(api)
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_dom", "greenhouse-dom-2+x")
    aid = queue(api, app_id)
    assert approval_of(app_id).invalidated_at is None
    assert runner.run_attempt(aid, "w1") == "confirmed"


def test_pre_binding_approval_never_implies_the_new_source():
    """`greenhouse_api_dom` did not exist before bindings, so no legacy approval covers it."""

    class Legacy:
        adapter = adapter_version = None

    assert policy.approved_binding(Legacy(), {"form_source": "greenhouse_api_dom"}) is None


def test_change_between_loading_and_the_disclosure_gate_is_refused(api, receiver, monkeypatch):
    """The gates re-check the binding under lock: a change after the attempt was loaded (e.g. a
    deploy mid-run) still stops it before anything is filled."""
    aid = queue(api, gh_application(api))
    real_fault = runner.fault

    def change_on_navigate(point):
        if point == "before_navigate":
            policy.ADAPTER_VERSIONS["greenhouse_hosted"] = "greenhouse-hosted-2+x"
        real_fault(point)

    current = policy.ADAPTER_VERSIONS["greenhouse_hosted"]
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_hosted", current)  # restored after
    monkeypatch.setattr(runner, "fault", change_on_navigate)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert attempt(aid).outcome_detail.endswith("the execution method changed after approval")
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_approval_given_for_a_manual_handoff_never_runs_through_an_adapter(
    api, receiver, monkeypatch
):
    """Approved while the route was a manual handoff (here: the origin was not a test fixture
    then), the approval records that route. When the same package later routes to an adapter,
    the approval does not match it: it is retired and nothing is sent. Recorded with no adapter,
    it would have read as an approval given before bindings existed, valid for that adapter."""
    from app.core.config import get_settings

    app_id = gh_application(api, approve=False)
    origins = get_settings().fixture_origins
    monkeypatch.setattr(get_settings(), "fixture_origins", [])
    assert reapprove(api, app_id).status_code == 200
    a = approval_of(app_id)
    assert (a.adapter, a.adapter_version) == (policy.MANUAL_BINDING, None)
    monkeypatch.setattr(get_settings(), "fixture_origins", origins)
    assert try_queue(api, app_id).status_code == 409
    assert approval_of(app_id).invalidated_at is not None
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
