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


# -- D120: the deliberate extraction-version bump (greenhouse-dom-v3 -> v4) -----------------------
# Not a SCHEMA_VERSION change: a package's content, hash and version are untouched. What changes is
# the adapter version an approval is bound to (D28): greenhouse_dom and greenhouse_live both embed
# gdom.EXTRACTION_VERSION. So an approval recorded before the bump is retired at the next gate, and
# only an explicit re-approval of the same content restores it, recorded at the new version.
# (Queued work bound to an older version is refused before any page action: the version-mismatch
# test in test_execution_routing, test_semantics_change_after_queueing_stops_before_disclosure and
# test_change_between_loading_and_the_disclosure_gate_is_refused here, and the section-bearing
# case in test_greenhouse_sections_e2e.)
# The extraction versions approvals were actually recorded under before the combined build:
# v3 (main before D130) and v4 (main with D130; D120's own branch also called itself v4). The
# combined build is v5 (preparation/greenhouse_dom.py), which neither carried.
ENCOUNTERED = ("greenhouse-dom-v3", "greenhouse-dom-v4")
PREFIX = {"greenhouse_dom": "greenhouse-dom-4+", "greenhouse_live": "greenhouse-live-2+"}


@pytest.mark.parametrize("prior", ENCOUNTERED)
@pytest.mark.parametrize("adapter", sorted(PREFIX))
def test_an_approval_from_before_the_extraction_bump_is_retired_never_renewed(
    api, receiver, adapter, prior
):
    from tests.test_greenhouse_controls import d104_application, d104_live_application

    make = d104_live_application if adapter == "greenhouse_live" else d104_application
    app_id = make(api)
    assert approval_of(app_id).adapter == adapter
    assert policy.ADAPTER_VERSIONS[adapter] == PREFIX[adapter] + "greenhouse-dom-v5"
    before = api.get(f"/applications/{app_id}/package").json()["package"]
    set_approval(app_id, adapter_version=PREFIX[adapter] + prior)  # as recorded under `prior`

    r = try_queue(api, app_id)
    assert r.status_code == 409 and "changed after you approved" in r.text
    retired = approval_of(app_id)
    assert retired.invalidated_at is not None  # retired, never re-bound in place
    assert receiver.ledger()["disclosures"] == []
    # The stored package is untouched: same version and content hash (EXTRACTION_VERSION is not
    # hashed content), so the owner re-approves identical content -- explicitly.
    after = api.get(f"/applications/{app_id}/package").json()["package"]
    assert (after["version"], after["content_hash"]) == (before["version"], before["content_hash"])
    assert try_queue(api, app_id).status_code != 200  # nothing renews it on its own
    assert approval_of(app_id).id == retired.id  # no new approval was created behind the owner

    assert reapprove(api, app_id).status_code == 200
    renewed = approval_of(app_id)
    assert renewed.id != retired.id and renewed.adapter_version == policy.ADAPTER_VERSIONS[adapter]
    queue(api, app_id)  # only now can it be queued


def _combined_package(api, receiver, kind: str) -> str:
    """An approved greenhouse_dom package of the kind each version change is about: a structured
    section (D120) or the optional phone's second control (D130)."""
    if kind == "sections":
        from tests.test_greenhouse_sections_e2e import sections_application

        receiver.config(mode="gh2_sections")
        return sections_application(api)
    from tests.test_phone_companion import by_id

    receiver.config(mode="gh2_phone_companion", pcm="")
    return by_id(api)


@pytest.mark.parametrize("prior", ENCOUNTERED)
@pytest.mark.parametrize("kind", ["sections", "phone_companion"])
def test_a_worker_at_an_encountered_version_refuses_before_any_page_action(
    api, receiver, monkeypatch, kind, prior
):
    """Queued at v5; a worker built at v3 or v4 (it would skip a section, or not know the phone's
    second control) refuses before anything is entered."""
    aid = queue(api, _combined_package(api, receiver, kind))
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_dom", PREFIX["greenhouse_dom"] + prior)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "execution method changed" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def _flip_at(monkeypatch, point: str, prior: str) -> None:
    """At the runner's fault point `point`, the worker's own version becomes `prior` (a deploy or
    a mixed fleet mid-run); the gate after it must re-check the binding under lock."""
    real = runner.fault
    current = policy.ADAPTER_VERSIONS["greenhouse_dom"]
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "greenhouse_dom", current)  # restored after

    def flip(p):
        if p == point:
            policy.ADAPTER_VERSIONS["greenhouse_dom"] = PREFIX["greenhouse_dom"] + prior
        real(p)

    monkeypatch.setattr(runner, "fault", flip)


@pytest.mark.parametrize("prior", ENCOUNTERED)
def test_the_disclosure_gate_refuses_an_encountered_version_after_loading(
    api, receiver, monkeypatch, prior
):
    aid = queue(api, _combined_package(api, receiver, "phone_companion"))
    _flip_at(monkeypatch, "before_navigate", prior)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert attempt(aid).outcome_detail.endswith("the execution method changed after approval")
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@pytest.mark.parametrize("prior", ENCOUNTERED)
def test_the_send_gate_refuses_an_encountered_version_after_filling(
    api, receiver, monkeypatch, prior
):
    """After filling (the upload was disclosed) the send gate re-checks: nothing is submitted, and
    nothing is retried."""
    aid = queue(api, _combined_package(api, receiver, "phone_companion"))
    _flip_at(monkeypatch, "before_send_gate", prior)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "the execution method changed after approval" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []
