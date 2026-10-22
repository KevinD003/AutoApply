"""A rehearsal (E5 step 1): an approval that permits disclosure only (live-pilot gate permission
3, "C", without permission 4). The attempt fills, uploads, reads back and re-checks the form
exactly as an attempt to submit does, then stops before the send gate: nothing is submitted,
and the approval is used up. The receiver's ledger, not NoEfforts' tables, is the oracle.
Local fixtures and synthetic data only."""

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt
from tests.execution_harness import Receiver, attempt, prepared_application
from tests.test_api_provider import TOKEN, acceptances, fapi_requests, grant
from tests.test_greenhouse_dom import v2_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def approve(api, app_id, scope=None):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    return api.post(f"/applications/{app_id}/package/approve",
                    json=body | ({"scope": scope} if scope else {}))  # fmt: skip


def queue(api, app_id) -> str:
    """Queue and return the newest attempt (an application may have several)."""
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        return str(db.scalar(
            select(ExecutionAttempt.id)
            .where(ExecutionAttempt.application_id == uuid.UUID(app_id))
            .order_by(ExecutionAttempt.created_at.desc()).limit(1)))  # fmt: skip


def uploads(led) -> list[dict]:
    return [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "upload"]


def submits(led) -> list[str]:
    return [r["path"] for r in led["requests"]
            if r["method"] == "POST" and r["path"].endswith("/submit")]  # fmt: skip


def test_a_rehearsal_fills_and_checks_then_stops_without_submitting(api, receiver):
    app_id = prepared_application(api, receiver, scope="disclose_only")
    view = api.get(f"/applications/{app_id}/package").json()
    assert view["approval"]["scope"] == "disclose_only"
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    led = receiver.ledger()
    # Disclosed: the approved document, by its digest. Submitted: nothing.
    digest = view["package"]["content"]["documents"][0]["sha256"]
    assert [u["sha256"] for u in uploads(led)] == [digest]
    assert led["accepted"] == 0 and submits(led) == []
    a = attempt(aid)
    assert a.state == "rehearsed" and a.disclosure_started_at and a.send_started_at is None
    assert "nothing was submitted" in a.outcome_detail
    (shown,) = api.get(f"/applications/{app_id}/attempts").json()
    assert shown["approval_scope"] == "disclose_only"
    kinds = {e["kind"] for e in shown["evidence"]}  # egress counts too, when requests were blocked
    assert {"disclosure", "readback"} <= kinds and "receipt" not in kinds
    readback = next(e for e in shown["evidence"] if e["kind"] == "readback")
    assert readback["data"]["mismatched"] == 0
    shown_app = api.get(f"/applications/{app_id}").json()
    assert shown_app["state"] == "needs_user_action"
    assert shown_app["last_attempt"] == {"state": "rehearsed", "approval_scope": "disclose_only"}
    # The approval is used up: the same approval cannot start a second rehearsal.
    view = api.get(f"/applications/{app_id}/package").json()
    assert view["state"] == "awaiting_approval"
    # Shown as used by the rehearsal, not as an invalidation (no reason text to interpret).
    assert view["approval"]["status"] == "used_by_rehearsal"
    assert view["approval"]["version"] == view["package"]["version"]
    assert view["approval"]["rehearsed_at"] and "reason" not in view["approval"]
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409
    with SessionLocal() as db:
        retired = db.scalars(select(AuditEvent).where(
            AuditEvent.action == "package.approval_retired")).all()  # fmt: skip
        assert [e.meta for e in retired] == [{"reason_code": "rehearsal_completed"}]
    assert receiver.ledger()["accepted"] == 0


def test_after_a_rehearsal_an_approval_to_submit_submits_once(api, receiver):
    app_id = prepared_application(api, receiver, scope="disclose_only")
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    assert approve(api, app_id).status_code == 200  # the default scope: submit
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w2") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and len(submits(led)) == 1
    assert len(uploads(led)) == 2  # each attempt uploads again: every check is repeated
    states = [a["state"] for a in api.get(f"/applications/{app_id}/attempts").json()]
    assert states == ["confirmed", "rehearsed"]
    (listed,) = api.get("/applications").json()  # the tracker shows the latest attempt
    assert listed["last_attempt"] == {"state": "confirmed", "approval_scope": "submit"}


def test_the_send_gate_refuses_a_rehearsal_even_if_the_runner_did_not_stop(
    api, receiver, monkeypatch
):
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    monkeypatch.setattr(runner, "_rehearsal", lambda attempt_id: False)  # the stop bypassed
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and submits(led) == []
    a = attempt(aid)
    assert a.send_started_at is None and "permits filling and checking only" in a.outcome_detail


def test_the_send_gate_itself_refuses_an_approval_to_fill_only(api, receiver):
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = uuid.UUID(queue(api, app_id))
    gen = svc.claim(aid, "w1")
    svc.gate_before_disclosure(aid, "w1", gen)
    with pytest.raises(svc.GateRefused, match="permits filling and checking only"):
        svc.gate_before_send(aid, "w1", gen)
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None  # the refusal changed nothing
    assert svc.abandon(aid, "w1", gen, "test finished")


def test_a_rehearsal_on_the_greenhouse_style_form(api, receiver):
    app_id = v2_application(api, approve=False)
    assert approve(api, app_id, "disclose_only").status_code == 200
    aid = queue(api, app_id)
    assert attempt(aid).adapter == "greenhouse_dom"
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    led = receiver.ledger()
    assert len(uploads(led)) == 1 and led["accepted"] == 0 and submits(led) == []


def test_the_api_route_rehearses_too(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)
    app_id = v2_application(api, approve=False)
    grant(api)
    assert approve(api, app_id, "disclose_only").status_code == 200
    aid = queue(api, app_id)
    assert attempt(aid).adapter == "fake_api"
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    posts = [p for m, p in fapi_requests(receiver) if m == "POST"]
    assert posts and not any(p.endswith("/submit") for p in posts)  # a draft and its upload
    assert acceptances(receiver) == [] and len(uploads(receiver.ledger())) == 1


def test_the_scope_defaults_to_submit_is_validated_and_is_never_switched_silently(
    api, receiver, other_api
):
    app_id = prepared_application(api, receiver)  # no scope given: existing flows unchanged
    view = api.get(f"/applications/{app_id}/package").json()
    assert view["approval"]["scope"] == "submit"
    approved_at = view["approval"]["approved_at"]
    assert approve(api, app_id, "submit").json()["approval"]["approved_at"] == approved_at
    r = approve(api, app_id, "disclose_only")
    assert r.status_code == 409 and "Revoke" in r.text
    assert approve(api, app_id, "fill_everything").status_code == 422
    assert other_api.post(f"/applications/{app_id}/package/approve", json={
        "version": view["package"]["version"], "content_hash": view["package"]["content_hash"],
        "scope": "disclose_only"}).status_code == 404  # fmt: skip
    with SessionLocal() as db:
        (row,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "package.approve"))
        assert row.meta["scope"] == "submit"
    # Revoked, it can be approved for a rehearsal instead. A revocation is still shown as one.
    revoked = api.post(f"/applications/{app_id}/package/revoke").json()["approval"]
    assert revoked["status"] == "invalidated" and revoked["reason"] == "Revoked by you"
    assert api.get("/applications").json()[0]["last_attempt"] is None  # nothing queued yet
    assert approve(api, app_id, "disclose_only").json()["approval"]["scope"] == "disclose_only"
