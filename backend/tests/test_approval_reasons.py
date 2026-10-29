"""C13 (D65): every refusal to approve, queue or revoke carries a fixed reason code, each produced
by its own path, and revoking stops an attempt no worker has taken yet. The receiver's ledger is
the oracle; synthetic data only."""

import pathlib
import re
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.applications.states import AppState
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution.models import AttemptState, ExecutionAttempt
from app.modules.preparation.package import APPROVAL_REASONS
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_execution_failures import release, start_blocked_worker, wait_for

DOC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "approval-reasons.md"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def code_of(r) -> str:
    assert r.status_code == 409, r.text
    m = re.search(r"\(reason: ([a-z_]+)\)$", r.json()["detail"])
    assert m, r.text
    return m.group(1)


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def approve(api, app_id, scope=None, p=None):
    p = p or package(api, app_id)
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    return api.post(f"/applications/{app_id}/package/approve",
                    json=body | ({"scope": scope} if scope else {}))  # fmt: skip


def set_state(app_id=None, aid=None, app_state=None, att_state=None):
    with SessionLocal() as db:
        if app_state:
            db.get(Application, uuid.UUID(app_id)).state = app_state
        if att_state:
            db.get(ExecutionAttempt, uuid.UUID(aid)).state = att_state
        db.commit()


def revoke_audits(api) -> list[dict]:
    uid = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.user_id == uid,
                                     AuditEvent.action == "package.revoke")  # fmt: skip
        return [e.meta for e in db.scalars(q.order_by(AuditEvent.created_at))]


def test_the_document_lists_exactly_the_codes():
    listed = re.findall(r"^\| `([a-z_]+)` \|", DOC.read_text(), re.M)
    assert listed == list(APPROVAL_REASONS)


def test_approval_refusals_carry_their_codes(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    p = package(api, app_id)
    stale = approve(api, app_id, p={**p, "content_hash": "0" * 64})
    assert code_of(stale) == "package_changed"
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert code_of(r) == "approval_needed"
    assert approve(api, app_id, scope="disclose_only").status_code == 200
    assert code_of(approve(api, app_id)) == "approval_other_scope"
    assert "for a rehearsal" in approve(api, app_id).json()["detail"]
    api.post(f"/applications/{app_id}/package/revoke")
    api.post(f"/applications/{app_id}/answers/clear", json={"key": "hear_about"})
    assert code_of(approve(api, app_id)) == "package_unresolved"


def test_queueing_refusals_carry_their_codes(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    # A worker holds the attempt while the application is left waiting (simulated).
    set_state(app_id, aid, AppState.awaiting_approval, AttemptState.claimed)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert code_of(r) == "submission_in_progress"
    # Still pending under a valid approval: never a second attempt beside it.
    set_state(app_id, aid, None, AttemptState.pending)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert code_of(r) == "attempt_running"
    # An attempt left pending under a stale approval, locked by a worker taking it.
    set_state(app_id, aid, None, AttemptState.pending)
    api.put(
        f"/applications/{app_id}/answers", json={"key": "hear_about", "value": {"label": "Other"}}
    )
    assert approve(api, app_id).status_code == 200
    with SessionLocal() as held:
        held.scalar(select(ExecutionAttempt).where(ExecutionAttempt.id == uuid.UUID(aid))
                    .with_for_update())  # fmt: skip
        r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
        held.rollback()
    assert code_of(r) == "attempt_being_claimed"


def test_a_recorded_confirmation_is_never_queued_again_with_its_code(api, receiver):
    app_id = prepared_application(api, receiver)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    set_state(app_id, app_state=AppState.awaiting_approval)  # simulated
    assert approve(api, app_id).status_code == 200
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert code_of(r) == "already_confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_revoking_before_a_worker_takes_the_attempt_stops_it_at_once(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    r = api.post(f"/applications/{app_id}/package/revoke")
    assert r.status_code == 200 and r.json()["revoke_effect"] == "cancelled"
    a = attempt(aid)
    assert a.state == "cancelled" and "before a worker picked this up" in a.outcome_detail
    assert api.get(f"/applications/{app_id}").json()["state"] == "awaiting_approval"
    assert runner.run_attempt(aid, "w1") == "ignored"  # a late delivery does nothing
    assert receiver.ledger()["accepted"] == 0 and receiver.ledger()["disclosures"] == []
    assert revoke_audits(api) == [{"queued_attempt": "cancelled"}]
    # Approving again queues a new attempt, which submits once.
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w2") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_revoking_while_a_worker_holds_the_attempt_leaves_it_to_the_gates(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = start_blocked_worker(aid, "w1", "before_navigate")
    wait_for(lambda: attempt(aid).state == "claimed")
    r = api.post(f"/applications/{app_id}/package/revoke")
    assert r.status_code == 200 and r.json()["revoke_effect"] == "stopping"
    assert release(w, gate) == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    assert revoke_audits(api) == [{"queued_attempt": "stopping"}]


@pytest.mark.parametrize("state", [AttemptState.sending, AttemptState.awaiting_code])
def test_revoking_after_the_final_click_is_refused(api, receiver, state):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    set_state(aid=aid, att_state=state)  # simulated: past the send gate
    r = api.post(f"/applications/{app_id}/package/revoke")
    assert code_of(r) == "revoke_in_flight"
    v = api.get(f"/applications/{app_id}/package").json()
    assert v["approval"]["status"] == "approved"  # unchanged: revoking could not stop it
    assert revoke_audits(api) == []


def test_another_users_revoke_is_404(api, other_api, receiver):
    app_id = prepared_application(api, receiver)
    queue(api, app_id)
    assert other_api.post(f"/applications/{app_id}/package/revoke").status_code == 404
    assert api.get(f"/applications/{app_id}").json()["state"] == "queued"
