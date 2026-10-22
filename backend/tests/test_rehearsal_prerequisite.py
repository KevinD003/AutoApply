"""The rehearsal prerequisite (E6): before the first submission through an employer/provider
path (user, adapter, origin, board), a successful recorded rehearsal on that path is required.
It is checked at five layers (approve, enqueue, claim, the disclosure gate and the send gate),
fails closed, and is never permission to submit: submitting still needs its own approval.

Every real destination has the rule, but real destinations stay refused before it is reached
(a manual handoff). These tests put the rule on local fixture paths through the TEST-ONLY
setting (honoured only when env == "test"). Synthetic data and the local receiver only; the
receiver's ledger is the oracle for what was sent."""

import pathlib
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.urlsafety import is_fixture_origin
from app.modules.applications.models import Application
from app.modules.execution import policy, rehearsal, runner
from app.modules.execution import service as svc
from app.modules.execution.models import (
    AttemptEvent,
    ExecutionAttempt,
    OutboxMessage,
    RehearsalRecord,
)
from app.modules.identity.models import User
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApplicationPackage, PackageApproval
from app.modules.providers import routing
from tests.execution_harness import (
    BASE,
    Receiver,
    attempt,
    prepared_application,
    queue,
    synthetic_candidate,
)
from tests.test_execution_validation import blocked_worker, release

MARK = "fixture_ats:e6-*"  # the fictional slugs these tests use


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.fixture
def marked(monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", [MARK])


def approve(api, app_id, scope="submit"):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"],
                          "scope": scope})  # fmt: skip


def prereq(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["rehearsal_prerequisite"]


def unapproved(api, receiver, slug="e6-a", suffix="") -> str:
    return prepared_application(api, receiver, slug=slug, url_suffix=suffix, approve=False)


def rehearse(api, receiver, slug="e6-a", suffix="") -> tuple[str, str]:
    app_id = prepared_application(
        api, receiver, slug=slug, url_suffix=suffix, scope="disclose_only"
    )
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    return app_id, aid


def submit(api, app_id) -> str:
    r = approve(api, app_id)
    assert r.status_code == 200, r.text
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    return aid


def latest_attempt(app_id: str) -> str:
    with SessionLocal() as db:
        return str(db.scalar(select(ExecutionAttempt.id).where(
            ExecutionAttempt.application_id == uuid.UUID(app_id))
            .order_by(ExecutionAttempt.created_at.desc()).limit(1)))  # fmt: skip


def accepted_and_uploads(receiver) -> tuple[int, int]:
    led = receiver.ledger()
    return led["accepted"], sum(d["kind"] == "upload" for d in led["disclosures"])


def events(aid: str) -> list[tuple[str, dict]]:
    with SessionLocal() as db:
        rows = db.scalars(select(AttemptEvent).where(AttemptEvent.attempt_id == uuid.UUID(aid))
                          .order_by(AttemptEvent.created_at))  # fmt: skip
        return [(e.kind, e.detail) for e in rows]


def user_id(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def verdict(app_id: str, **overrides) -> rehearsal.Verdict:
    """The prerequisite computed directly for an application's current package (unit level)."""
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        dest = pk.latest_package(db, app.id).content["destination"]
        binding = policy.execution_binding(dest, app.user_id)
        kw = dict(layer="test", user_id=app.user_id, destination=dest,
                  adapter=binding["adapter"], adapter_version=binding["adapter_version"],
                  destination_class=rehearsal.destination_class(dest["origin"]))  # fmt: skip
        return rehearsal.prerequisite(db, **(kw | overrides))


# ---------------------------------------------------------------- the rule and its result


def test_a_fixture_path_without_the_marker_needs_no_rehearsal(api, receiver):
    app_id = unapproved(api, receiver, slug="e6-free")
    shown = prereq(api, app_id)
    assert (shown["status"], shown["reason_code"]) == ("not_required", None)
    aid = submit(api, app_id)
    assert attempt(aid).rehearsal_prerequisite == "not_required"
    assert accepted_and_uploads(receiver) == (1, 1)


def test_the_first_submission_on_a_path_needs_a_recorded_rehearsal(api, receiver, marked):
    app_id = unapproved(api, receiver)
    shown = prereq(api, app_id)
    assert (shown["status"], shown["reason_code"]) == ("unmet", "no_rehearsal")
    assert shown["message"] == rehearsal.REASONS["no_rehearsal"] and shown["label"]
    r = approve(api, app_id)
    assert r.status_code == 409 and "(reason: no_rehearsal)" in r.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count(PackageApproval.id))) == 0
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert [q for q in led["requests"] if q["method"] != "GET"] == []


def test_a_valid_rehearsal_then_a_separate_approval_to_submit(api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    shown = prereq(api, app_id)
    assert (shown["status"], shown["reason_code"]) == ("met", None)
    # The rehearsal is never permission to submit: its approval was used up.
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "Approve the current package version" in r.text
    assert approve(api, app_id).status_code == 200
    with SessionLocal() as db:
        appr = db.scalar(select(PackageApproval).where(PackageApproval.scope == "submit"))
        assert appr.prerequisite_attempt_id == uuid.UUID(rid)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert attempt(aid).rehearsal_prerequisite == "met"
    assert accepted_and_uploads(receiver) == (1, 2)
    shown = {a["id"]: a for a in api.get(f"/applications/{app_id}/attempts").json()}
    assert shown[rid]["rehearsal"] == {"status": "valid", "revoked_at": None, "withdrawable": True}
    assert {a["evidence_class"] for a in shown.values()} == {"fixture"}  # a fixture counts as none
    assert shown[aid]["rehearsal_prerequisite"] == "met" and shown[aid]["rehearsal"] is None


def test_a_confirmed_submission_establishes_its_path(api, receiver, marked):
    app1, rid = rehearse(api, receiver)
    s1 = submit(api, app1)
    app2 = unapproved(api, receiver, suffix="?posting=2")
    assert prereq(api, app2)["status"] == "established"
    # Withdrawing the rehearsal changes nothing now: a submission after it is newer.
    assert api.post(f"/applications/{app1}/rehearsals/{rid}/withdraw").status_code == 200
    assert prereq(api, app2)["status"] == "established"
    s2 = submit(api, app2)
    assert (attempt(s1).rehearsal_prerequisite, attempt(s2).rehearsal_prerequisite) == (
        "met", "established")  # fmt: skip
    # Each establishing submission needs its retained receipt; when none is left, the newest
    # rehearsal decides again (here: withdrawn).
    assert api.delete(f"/applications/{app2}/evidence").status_code == 200
    app3 = unapproved(api, receiver, suffix="?posting=3")
    assert prereq(api, app3)["status"] == "established"
    assert api.delete(f"/applications/{app1}/evidence").status_code == 200
    shown = prereq(api, app3)
    assert (shown["status"], shown["reason_code"]) == ("unmet", "rehearsal_revoked")
    assert accepted_and_uploads(receiver) == (2, 3)


def test_one_rehearsal_serves_another_posting_on_the_same_path(api, receiver, marked):
    rehearse(api, receiver)
    app2 = unapproved(api, receiver, suffix="?posting=2")
    assert prereq(api, app2)["status"] == "met"
    aid = submit(api, app2)
    assert attempt(aid).rehearsal_prerequisite == "met"


def test_a_rehearsal_on_another_board_does_not_count(api, receiver, marked):
    rehearse(api, receiver, slug="e6-a")
    other = unapproved(api, receiver, slug="e6-b")
    assert prereq(api, other)["reason_code"] == "no_rehearsal"
    assert approve(api, other).status_code == 409


def test_a_rehearsal_never_counts_for_another_user(api, other_api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    theirs = unapproved(other_api, receiver)
    assert prereq(other_api, theirs)["reason_code"] == "no_rehearsal"
    assert other_api.post(f"/applications/{app_id}/rehearsals/{rid}/withdraw").status_code == 404
    assert other_api.get(f"/applications/{app_id}/attempts").status_code == 404
    # Their own application id with my attempt id is not theirs to withdraw either.
    assert other_api.post(f"/applications/{theirs}/rehearsals/{rid}/withdraw").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(RehearsalRecord)).revoked_at is None


def test_the_user_filter_holds_even_if_path_references_collided(api, other_api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    ref = attempt(rid).path_ref
    assert verdict(app_id, path_ref_value=ref).status == "met"
    # The same stored reference, asked for by another user, finds nothing of theirs.
    v = verdict(app_id, path_ref_value=ref, user_id=user_id(other_api))
    assert (v.status, v.code) == ("unmet", "no_rehearsal")


def test_a_later_failed_rehearsal_supersedes_an_earlier_success(api, receiver, marked):
    app1, _ = rehearse(api, receiver)
    receiver.config(mode="upload_fail")
    app2 = prepared_application(
        api, receiver, slug="e6-a", url_suffix="?posting=2", scope="disclose_only"
    )
    assert runner.run_attempt(queue(api, app2), "w1") == "abandoned"
    receiver.config(mode="normal")
    assert prereq(api, app1)["reason_code"] == "rehearsal_failed"
    r = approve(api, app1)
    assert r.status_code == 409 and "(reason: rehearsal_failed)" in r.text


def test_an_in_progress_rehearsal_never_displaces_a_finished_one(api, receiver, marked):
    rehearse(api, receiver)
    pending = prepared_application(
        api, receiver, slug="e6-a", url_suffix="?posting=2", scope="disclose_only"
    )
    queue(api, pending)  # queued, never run
    assert prereq(api, unapproved(api, receiver, suffix="?posting=3"))["status"] == "met"
    alone = prepared_application(api, receiver, slug="e6-c", scope="disclose_only")
    queue(api, alone)
    shown = prereq(api, unapproved(api, receiver, slug="e6-c", suffix="?posting=2"))
    assert shown["reason_code"] == "rehearsal_in_progress"


def test_the_rehearsal_that_finished_last_decides_whatever_the_queue_order(api, receiver, marked):
    """Queued first, finished last: R1 waits while R2 (queued after it) succeeds; R1 then fails.
    The newest result on the path is the failure."""
    app1 = prepared_application(api, receiver, slug="e6-a", scope="disclose_only")
    r1 = queue(api, app1)
    app2, _ = rehearse(api, receiver, suffix="?posting=2")
    assert prereq(api, app2)["status"] == "met"
    receiver.config(mode="upload_fail")
    assert runner.run_attempt(r1, "w1") == "abandoned"
    receiver.config(mode="normal")
    shown = prereq(api, unapproved(api, receiver, suffix="?posting=3"))
    assert (shown["status"], shown["reason_code"]) == ("unmet", "rehearsal_failed")


def test_a_newer_failed_rehearsal_outvotes_an_established_path(api, receiver, marked):
    app1, _ = rehearse(api, receiver)
    submit(api, app1)
    assert prereq(api, unapproved(api, receiver, suffix="?posting=2"))["status"] == "established"
    receiver.config(mode="upload_fail")
    failing = prepared_application(
        api, receiver, slug="e6-a", url_suffix="?posting=3", scope="disclose_only"
    )
    assert runner.run_attempt(queue(api, failing), "w1") == "abandoned"
    receiver.config(mode="normal")
    shown = prereq(api, unapproved(api, receiver, suffix="?posting=4"))
    assert (shown["status"], shown["reason_code"]) == ("unmet", "rehearsal_failed")


def test_an_established_path_needs_a_new_rehearsal_after_an_adapter_version_change(
    api, receiver, marked, monkeypatch
):
    app1, _ = rehearse(api, receiver)
    s1 = submit(api, app1)
    app2 = unapproved(api, receiver, suffix="?posting=2")
    assert prereq(api, app2)["status"] == "established"
    with SessionLocal() as db:  # simulated: the submission recorded as another class
        db.get(ExecutionAttempt, uuid.UUID(s1)).destination_class = "real"
        db.commit()
    assert prereq(api, app2)["status"] == "met"  # no longer established; the rehearsal decides
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(s1)).destination_class = "fixture"
        db.commit()
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "fixture_ats", "fixture-ats-test-bump")
    shown = prereq(api, app2)
    assert (shown["status"], shown["reason_code"]) == ("unmet", "rehearsal_mismatched")


def test_a_submission_made_while_the_rule_did_not_apply_establishes_nothing(
    api, receiver, monkeypatch
):
    app1 = unapproved(api, receiver)
    s1 = submit(api, app1)
    assert attempt(s1).rehearsal_prerequisite == "not_required"
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", [MARK])
    shown = prereq(api, unapproved(api, receiver, suffix="?posting=2"))
    assert (shown["status"], shown["reason_code"]) == ("unmet", "no_rehearsal")


def test_a_claim_refused_after_a_sweeper_repend_leaves_nothing_running(api, receiver, marked):
    """A worker that disclosed nothing loses its lease; the sweeper re-pends the attempt (the
    application stays running). The rehearsal is withdrawn meanwhile: the re-claim refuses it,
    and the application waits for the user instead of staying `running` with no attempt."""
    app_id, rid = rehearse(api, receiver)
    assert approve(api, app_id).status_code == 200
    aid = uuid.UUID(queue(api, app_id))
    assert svc.claim(aid, "w1") is not None
    with SessionLocal() as db:
        db.get(ExecutionAttempt, aid).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.sweep(publish_new=False)["repended"] == 1
    assert api.post(f"/applications/{app_id}/rehearsals/{rid}/withdraw").status_code == 200
    receiver.reset()
    assert runner.run_attempt(str(aid), "w2") == "ignored"
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, aid).state == "failed_safe"
        assert db.get(Application, uuid.UUID(app_id)).state.value == "needs_user_action"
    assert receiver.ledger()["requests"] == []


def test_a_rehearsal_with_no_record_cannot_be_withdrawn_or_counted(api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    with SessionLocal() as db:  # simulated: rehearsed before records existed
        db.delete(db.scalar(select(RehearsalRecord)))
        db.commit()
    (shown,) = [a for a in api.get(f"/applications/{app_id}/attempts").json() if a["id"] == rid]
    assert shown["rehearsal"] == {
        "status": "rehearsal_evidence_missing",
        "revoked_at": None,
        "withdrawable": False,
    }
    assert api.post(f"/applications/{app_id}/rehearsals/{rid}/withdraw").status_code == 404
    assert prereq(api, app_id)["reason_code"] == "rehearsal_evidence_missing"


def test_a_fixture_rehearsal_never_satisfies_a_real_path(api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    ref = attempt(rid).path_ref
    v = verdict(app_id, path_ref_value=ref, destination_class="real")
    assert (v.status, v.code) == ("unmet", "rehearsal_mismatched")


# ---------------------------------------------------------------- every layer, alone

LAYERS = ["approve", "enqueue", "claim", "disclosure", "send"]


@pytest.mark.parametrize("layer", [*LAYERS, "none"])
def test_each_layer_refuses_with_the_others_bypassed(api, receiver, marked, monkeypatch, layer):
    """Every other layer is replaced by one that always says met; the one under test must still
    refuse, at its own point, with what it lets through so far and no further."""
    real = rehearsal.prerequisite

    def only_this_layer(db, **kw):
        return real(db, **kw) if kw["layer"] == layer else rehearsal.Verdict(rehearsal.MET)

    monkeypatch.setattr(rehearsal, "prerequisite", only_this_layer)
    app_id = unapproved(api, receiver, slug="e6-layers")
    r = approve(api, app_id)
    if layer == "approve":
        assert r.status_code == 409 and "(reason: no_rehearsal)" in r.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count(PackageApproval.id))) == 0
        return
    assert r.status_code == 200, r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    if layer == "enqueue":
        assert r.status_code == 409 and "(reason: no_rehearsal)" in r.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ExecutionAttempt.id))) == 0
            assert db.scalar(select(func.count(OutboxMessage.id))) == 0
            assert db.get(Application, uuid.UUID(app_id)).state.value == "awaiting_approval"
        return
    assert r.status_code == 200, r.text
    aid = latest_attempt(app_id)
    receiver.reset()
    out = runner.run_attempt(aid, "w1")
    led, a = receiver.ledger(), attempt(aid)
    reasons = [d.get("reason_code") for _, d in events(aid) if d.get("reason_code")]
    if layer == "claim":
        assert (out, a.state) == ("ignored", "failed_safe") and "(reason: no_rehearsal)" in (
            a.outcome_detail)  # fmt: skip
        assert ("claim_refused_rehearsal", {"reason_code": "no_rehearsal"}) in events(aid)
        assert led["requests"] == []  # no page was even opened
    elif layer == "disclosure":
        assert (out, a.state, reasons) == ("failed_safe", "failed_safe", ["no_rehearsal"])
        assert led["disclosures"] == [] and led["accepted"] == 0
    elif layer == "send":
        assert (out, a.state, reasons) == ("abandoned", "abandoned", ["no_rehearsal"])
        assert accepted_and_uploads(receiver) == (0, 1)
        assert svc.sweep(publish_new=False)["repended"] == 0
        assert attempt(aid).state == "abandoned"  # never retried after disclosing
    else:
        assert (out, a.rehearsal_prerequisite) == ("confirmed", "met")
        assert led["accepted"] == 1


def test_turning_the_rule_on_after_queueing_is_caught_by_the_worker(api, receiver, monkeypatch):
    app_id = unapproved(api, receiver)
    assert approve(api, app_id).status_code == 200  # not required yet
    aid = queue(api, app_id)
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", [MARK])
    receiver.reset()
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert attempt(aid).state == "failed_safe"
    assert ("claim_refused_rehearsal", {"reason_code": "no_rehearsal"}) in events(aid)
    assert receiver.ledger()["requests"] == []


# ---------------------------------------------------------------- withdrawal racing a gate


def test_deleting_an_establishing_receipt_after_the_gate_snapshot_is_refused(
    api, receiver, marked, monkeypatch
):
    """Deterministic, as above, for an established path: the evidence of the submission that
    established it is deleted after the send gate's snapshot. The gate holds that receipt FOR
    SHARE, so the deletion is a serialization failure and the gate refuses."""
    app1, _ = rehearse(api, receiver)
    submit(api, app1)
    app2 = unapproved(api, receiver, suffix="?posting=2")
    assert approve(api, app2).status_code == 200  # established
    aid = uuid.UUID(queue(api, app2))
    gen = svc.claim(aid, "w1")
    svc.gate_before_disclosure(aid, "w1", gen)
    original, done = pk.lock_application, []

    def lock_application(db, app):
        if not done:
            done.append(True)
            with SessionLocal() as other:
                svc.delete_application_evidence(other, other.get(Application, uuid.UUID(app1)))
                other.commit()
        return original(db, app)

    monkeypatch.setattr(pk, "lock_application", lock_application)
    with pytest.raises(svc.GateRefused) as refused:
        svc.gate_before_send(aid, "w1", gen)
    assert done == [True] and refused.value.code == "rehearsal_check_unavailable"
    assert attempt(str(aid)).send_started_at is None
    assert svc.abandon(aid, "w1", gen, "test finished")


def test_withdrawing_the_relied_on_rehearsal_while_the_send_gate_waits(
    api, receiver, marked, monkeypatch
):
    app_id, rid = rehearse(api, receiver)
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    env = {"NOEFFORTS_EXECUTION_TEST_REHEARSAL_RULE_PATHS": f'["{MARK}"]'}
    w, gate = blocked_worker(aid, "before_send_gate", env)
    waiting = pathlib.Path(gate + ".waiting")
    deadline = time.monotonic() + 60
    while not waiting.exists():
        assert w.poll() is None and time.monotonic() < deadline, "the worker never reached it"
        time.sleep(0.1)
    assert api.post(f"/applications/{app_id}/rehearsals/{rid}/withdraw").status_code == 200
    assert release(w, gate) == "abandoned"
    a = attempt(aid)
    assert a.state == "abandoned" and "(reason: rehearsal_revoked)" in a.outcome_detail
    assert accepted_and_uploads(receiver) == (0, 2)  # the rehearsal's upload and this one's


def test_a_withdrawal_after_the_gate_snapshot_is_refused_not_missed(
    api, receiver, marked, monkeypatch
):
    """Deterministic: the withdrawal commits in a second session after the send gate's snapshot
    was fixed (at its attempt lock). The gate holds the relied-on record FOR SHARE, so the change
    is a serialization failure, and the gate refuses rather than trusting its snapshot."""
    app_id, rid = rehearse(api, receiver)
    assert approve(api, app_id).status_code == 200
    aid = uuid.UUID(queue(api, app_id))
    gen = svc.claim(aid, "w1")
    svc.gate_before_disclosure(aid, "w1", gen)
    original, done = pk.lock_application, []

    def lock_application(db, app):
        if not done:
            done.append(True)
            with SessionLocal() as other:
                svc.withdraw_rehearsal(
                    other, other.get(Application, uuid.UUID(app_id)), uuid.UUID(rid)
                )
                other.commit()
        return original(db, app)

    monkeypatch.setattr(pk, "lock_application", lock_application)
    with pytest.raises(svc.GateRefused) as refused:
        svc.gate_before_send(aid, "w1", gen)
    assert done == [True] and refused.value.code == "rehearsal_check_unavailable"
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None
    assert svc.abandon(aid, "w1", gen, "test finished")


# ---------------------------------------------------------------- real destinations, the marker


def test_a_real_destination_is_still_refused_first(api, receiver, monkeypatch):
    """Even with the marker on every path, a real employer's form gets the honest manual
    handoff: the prerequisite is not where it stops. The URL is a reserved, unresolvable name;
    nothing is contacted."""
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", ["*"])
    synthetic_candidate(api)
    job = api.post("/jobs", json={"url": "https://jobs.example.invalid/apply/e6-real",
                                  "title": "Role (fictional)"}).json()  # fmt: skip
    job_id = job["job"]["id"]
    html = receiver.form_html("e6-real")
    assert api.post(f"/jobs/{job_id}/form", json={"html": html}).status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    api.put(f"/applications/{app_id}/answers",
            json={"key": "hear_about", "value": {"label": "Referral"}})  # fmt: skip
    api.put(f"/applications/{app_id}/consents", json={"key": "privacy_ack", "choice": "agree"})
    shown = prereq(api, app_id)
    assert shown["status"] == "not_applicable"
    assert shown["reason_code"] == "real_destination_disabled"
    assert approve(api, app_id).status_code == 200  # an approval with no execution method
    shown = prereq(api, app_id)  # still the manual handoff once approved
    assert (shown["status"], shown["reason_code"]) == (
        "not_applicable",
        "real_destination_disabled",
    )
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and policy.REAL_DESTINATION_DISABLED in r.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ExecutionAttempt.id))) == 0


def test_the_marker_only_adds_the_rule_and_only_in_tests(monkeypatch):
    s = get_settings()
    fixture = {"origin": BASE, "url": f"{BASE}/apply/e6-a",
               "submit_url": f"{BASE}/apply/e6-a/submit", "form_source": "html"}  # fmt: skip
    path = rehearsal.execution_path(fixture, "fixture_ats")
    before = (is_fixture_origin(BASE), policy.adapter_for(fixture), routing.decide(fixture).route,
              rehearsal.destination_class(BASE))  # fmt: skip
    assert not rehearsal.rule_applies("fixture", path)
    monkeypatch.setattr(s, "execution_test_rehearsal_rule_paths", ["*"])
    assert rehearsal.rule_applies("fixture", path)
    after = (is_fixture_origin(BASE), policy.adapter_for(fixture), routing.decide(fixture).route,
             rehearsal.destination_class(BASE))  # fmt: skip
    assert before == after == (True, "fixture_ats", "browser", "fixture")
    for env in ("development", "production"):
        monkeypatch.setattr(s, "env", env)
        assert not rehearsal.rule_applies("fixture", path)
        assert rehearsal.rule_applies("real", path) and rehearsal.rule_applies("real", None)
        assert rehearsal.rule_applies(None, path)  # an unknown class has the rule
    monkeypatch.setattr(s, "execution_test_rehearsal_rule_paths", [])
    assert rehearsal.rule_applies("real", path)  # the setting can never remove it


def test_the_path_is_user_provider_origin_and_board():
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    p = rehearsal.Path("greenhouse_dom", "https://boards.example.invalid", "x")
    ref = rehearsal.path_ref(u1, p)
    assert ref.startswith("path:v1:") and len(ref) == 40 and ref == rehearsal.path_ref(u1, p)
    others = [rehearsal.path_ref(u2, p), rehearsal.path_ref(u1, p._replace(board="y")),
              rehearsal.path_ref(u1, p._replace(board="X")),
              rehearsal.path_ref(u1, p._replace(adapter="fake_api")),
              rehearsal.path_ref(u1, p._replace(origin="https://o.example.invalid"))]  # fmt: skip
    assert len({ref, *others}) == 6
    assert rehearsal.path_ref(u1, None) is None
    n = rehearsal.normalize_origin
    assert n("HTTPS://Boards.Example.Invalid:443") == "https://boards.example.invalid"
    assert n("http://127.0.0.1:80") == "http://127.0.0.1" and n("http://h:8799") == "http://h:8799"
    for bad in (None, "", "ftp://h", "https://", "https://h/path", "https://u@h", "https://h:x"):
        assert n(bad) is None, bad
    fx = {"origin": BASE, "url": f"{BASE}/apply/e6-a?posting=2"}
    assert rehearsal.execution_path(fx, "fixture_ats") == rehearsal.Path(
        "fixture_ats", BASE, "e6-a")  # fmt: skip
    gh2 = {"origin": BASE, "url": f"{BASE}/gh2/northwind/jobs/5020001"}
    assert rehearsal.execution_path(gh2, "greenhouse_dom").board == "northwind"
    assert rehearsal.execution_path(gh2, "fake_api").board == "northwind"
    for dest, adapter in [
        ({"origin": BASE, "url": f"{BASE}/apply/a/b"}, "fixture_ats"),  # not one slug
        ({"origin": BASE, "url": "http://elsewhere.example.invalid/apply/a"}, "fixture_ats"),
        ({"origin": BASE, "url": f"{BASE}/apply/a"}, "an_unknown_adapter"),
        ({"origin": BASE, "url": f"{BASE}/careers"}, "greenhouse_dom"),
        ({"url": f"{BASE}/apply/a"}, "fixture_ats"),
        ({"origin": BASE, "url": None}, "fixture_ats"),
    ]:
        assert rehearsal.execution_path(dest, adapter) is None, dest


def test_an_attempt_and_its_record_keep_the_path_only_as_a_keyed_reference(api, receiver, marked):
    app_id, rid = rehearse(api, receiver)
    a = attempt(rid)
    with SessionLocal() as db:
        rec = db.scalar(select(RehearsalRecord))
        dest = db.get(ApplicationPackage, a.package_id).content["destination"]
        me = db.get(User, a.user_id).id
    expected = rehearsal.path_ref(me, rehearsal.execution_path(dest, "fixture_ats"))
    assert a.path_ref == rec.path_ref == expected
    assert "e6-a" not in a.path_ref and "127.0.0.1" not in a.path_ref
    served = api.get(f"/applications/{app_id}/attempts").text + api.get(
        f"/applications/{app_id}/package").text  # fmt: skip
    assert a.path_ref not in served  # never served


def test_an_error_while_checking_is_a_refusal_and_leaves_the_session_usable(
    api, receiver, marked, monkeypatch
):
    app_id, _ = rehearse(api, receiver)
    real = rehearsal._from_rehearsal

    def failing_statement(db, *args):
        db.execute(text("select 1/0"))  # the database refuses it
        return real(db, *args)

    monkeypatch.setattr(rehearsal, "_from_rehearsal", failing_statement)
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        dest = pk.latest_package(db, app.id).content["destination"]
        binding = policy.execution_binding(dest, app.user_id)
        v = rehearsal.prerequisite(db, layer="test", user_id=app.user_id, destination=dest,
                                   adapter=binding["adapter"],
                                   adapter_version=binding["adapter_version"],
                                   destination_class="fixture")  # fmt: skip
        assert (v.status, v.code) == ("unmet", "rehearsal_check_unavailable")
        assert db.execute(text("select 1")).scalar() == 1  # the savepoint kept the session
    r = approve(api, app_id)
    assert r.status_code == 409 and "(reason: rehearsal_check_unavailable)" in r.text


def test_a_stale_window_outside_its_bounds_fails_closed(api, receiver, marked, monkeypatch):
    app_id, _ = rehearse(api, receiver)
    for days in (0, get_settings().evidence_retention_days + 1):
        monkeypatch.setattr(get_settings(), "rehearsal_max_age_days", days)
        assert prereq(api, app_id)["reason_code"] == "rehearsal_check_unavailable"
    monkeypatch.setattr(get_settings(), "rehearsal_max_age_days", 30)
    with SessionLocal() as db:
        db.scalar(select(RehearsalRecord)).recorded_at -= timedelta(days=31)  # simulated age
        db.commit()
    assert prereq(api, app_id)["reason_code"] == "rehearsal_stale"
