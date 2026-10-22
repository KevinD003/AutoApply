"""The rehearsal stop is a gate (E5 step 3). A rehearsal ends `rehearsed` only through
service.finish_rehearsal, which repeats every gate check in one REPEATABLE READ transaction
(authority, the approval still live and locked, the content and the execution method unchanged,
the destination's class) and checks that the evidence rows show a complete rehearsal. Only then
is its record written, in the same commit. A refusal ends the attempt `abandoned`. Nothing is
ever submitted. Synthetic data and local fixtures only; the receiver's ledger is the oracle."""

import json
import pathlib
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.audit.models import AuditEvent
from app.modules.execution import rehearsal, runner
from app.modules.execution import service as svc
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters.fake_api import FakeApiAdapter
from app.modules.execution.models import (
    AttemptEvent,
    Evidence,
    ExecutionAttempt,
    RehearsalRecord,
)
from app.modules.execution.policy import ADAPTER_VERSIONS
from app.modules.preparation import package as pk
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_api_provider import TOKEN, grant
from tests.test_execution_validation import blocked_worker, release
from tests.test_greenhouse_dom import v2_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def approve(api, app_id, scope):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"],
                       "scope": scope})  # fmt: skip
    assert r.status_code == 200, r.text


def api_rehearsal(api, monkeypatch) -> str:
    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)
    app_id = v2_application(api, approve=False)
    grant(api)
    approve(api, app_id, "disclose_only")
    return app_id


def records(app_id: str) -> list[RehearsalRecord]:
    with SessionLocal() as db:
        return list(db.scalars(select(RehearsalRecord).where(
            RehearsalRecord.application_id == uuid.UUID(app_id))))  # fmt: skip


def retired_audits(app_id: str) -> list[dict]:
    with SessionLocal() as db:
        return [e.meta for e in db.scalars(select(AuditEvent).where(
            AuditEvent.action == "package.approval_retired",
            AuditEvent.entity_id == app_id))]  # fmt: skip


def accepted_and_uploads(receiver) -> tuple[int, int]:
    led = receiver.ledger()
    return led["accepted"], sum(d["kind"] == "upload" for d in led["disclosures"])


# ---------------------------------------------------------------- what a rehearsal records


@pytest.mark.parametrize("route", ["browser", "api"])
def test_a_rehearsal_records_what_it_proved_at_its_stop(api, receiver, monkeypatch, route):
    if route == "api":
        app_id = api_rehearsal(api, monkeypatch)
    else:
        app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    (rec,) = records(app_id)
    a = attempt(aid)
    assert (rec.attempt_id, rec.user_id, rec.approval_id) == (a.id, a.user_id, a.approval_id)
    assert (rec.destination_class, a.destination_class, rec.route) == ("fixture", "fixture", route)
    assert rec.adapter == a.adapter and rec.adapter_version == ADAPTER_VERSIONS[a.adapter]
    assert (rec.uploads_expected, rec.uploads_acknowledged, rec.unresolved) == (1, 1, 0)
    assert rec.readback_mismatched == (None if route == "api" else 0)
    assert rec.recheck_matched and rec.revoked_at is None
    with SessionLocal() as db:
        assert rehearsal.assess_record(db, rec, adapter_version=rec.adapter_version) is None
    assert retired_audits(app_id) == [{"reason_code": "rehearsal_completed"}]
    assert accepted_and_uploads(receiver) == (0, 1)


def test_records_events_and_audit_hold_no_external_identifiers(api, receiver):
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rehearsed"
    (rec,) = records(app_id)
    with SessionLocal() as db:
        events = [e.detail for e in db.scalars(select(AttemptEvent).where(
            AttemptEvent.attempt_id == uuid.UUID(aid)))]  # fmt: skip
        audit = [e.meta for e in db.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == app_id))]  # fmt: skip
    row = {c.name: getattr(rec, c.name) for c in RehearsalRecord.__table__.columns}
    text = json.dumps([row, events, audit], default=str)
    for marker in ("://", "127.0.0.1", "clinic", "resume", "Sam", "example.com"):
        assert marker not in text, marker


# ---------------------------------------------------------------- the stop repeats the gate


def stopped_rehearsal(api, receiver, extra_env=None):
    """A real worker process held at the stop, after filling and uploading."""
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    w, gate = blocked_worker(aid, "before_rehearsal_stop", extra_env)
    waiting = pathlib.Path(gate + ".waiting")
    deadline = time.monotonic() + 60
    while not waiting.exists():
        assert w.poll() is None and time.monotonic() < deadline, "the worker never reached the stop"
        time.sleep(0.1)
    return app_id, aid, w, gate


def test_a_revocation_at_the_stop_ends_abandoned_not_rehearsed(api, receiver):
    app_id, aid, w, gate = stopped_rehearsal(api, receiver)
    api.post(f"/applications/{app_id}/package/revoke")
    assert release(w, gate) == "abandoned"
    a = attempt(aid)
    assert a.state == "abandoned" and "approval revoked" in a.outcome_detail
    assert records(app_id) == [] and retired_audits(app_id) == []
    shown = api.get(f"/applications/{app_id}/package").json()["approval"]
    assert shown["status"] == "invalidated" and shown["reason"] == "Revoked by you"
    assert accepted_and_uploads(receiver) == (0, 1)  # the upload was made; nothing submitted


def test_a_change_to_the_profile_at_the_stop_ends_abandoned(api, receiver):
    app_id, aid, w, gate = stopped_rehearsal(api, receiver)
    profile = {
        "full_name": "Sam Synthetic",
        "given_name": "Sam",
        "family_name": "Synthetic",
        "contact_email": "sam.synthetic@example.com",
        "phone": "+1 555 0199",
        "residence_country": "US",
        "residence_city": "Springfield",
        "links": ["https://www.linkedin.com/in/sam-synthetic"],
    }  # only the phone changed
    assert api.put("/profile", json=profile).status_code == 200
    assert release(w, gate) == "abandoned"
    assert "changed after approval" in attempt(aid).outcome_detail
    assert records(app_id) == []
    assert accepted_and_uploads(receiver) == (0, 1)


def test_a_cancel_at_the_stop_is_not_a_rehearsal(api, receiver):
    app_id, aid, w, gate = stopped_rehearsal(api, receiver)
    assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    assert release(w, gate) == "lost_authority"
    assert attempt(aid).state == "cancelled" and records(app_id) == []


def test_a_lost_lease_at_the_stop_is_not_a_rehearsal(api, receiver):
    app_id, aid, w, gate = stopped_rehearsal(api, receiver)
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert svc.sweep(publish_new=False)["abandoned"] == 1  # disclosed: never re-pended
    assert release(w, gate) == "lost_authority"
    assert attempt(aid).state == "abandoned" and records(app_id) == []


def test_the_api_route_reads_the_form_again_before_its_stop(api, receiver, monkeypatch):
    app_id = api_rehearsal(api, monkeypatch)
    aid = queue(api, app_id)
    calls = []
    original = FakeApiAdapter.validate_before_disclosure

    def second_read_differs(self):
        calls.append(1)
        return original(self) if len(calls) == 1 else "the job's questions changed"

    monkeypatch.setattr(FakeApiAdapter, "validate_before_disclosure", second_read_differs)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert len(calls) == 2 and "questions changed" in attempt(aid).outcome_detail
    assert records(app_id) == [] and receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------- the stop checks the evidence


def at_the_stop(api, receiver) -> tuple[str, uuid.UUID, int, dict]:
    """A rehearsal claimed and past its disclosure gate, with no evidence yet: the test writes
    the rows the runner would, then calls the stop directly."""
    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = uuid.UUID(queue(api, app_id))
    gen = svc.claim(aid, "w1")
    svc.gate_before_disclosure(aid, "w1", gen)
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return app_id, aid, gen, content


def write(aid, gen, rows):
    for kind, data in rows:
        svc.record_evidence(aid, "w1", gen, kind, data)


def complete(content, **change):
    (doc,) = content["documents"]
    upload = {"field": doc["field"], "ack": fixture_ats.ACK_SHOWN, "sha256": doc["sha256"]}
    rows = {"upload": ("disclosure", upload),
            "readback": ("readback", {"checked": 5, "mismatched": 0}),
            "recheck": ("recheck", rehearsal.RECHECK_MATCHED)}  # fmt: skip
    for name, value in change.items():
        if value is None:
            rows.pop(name)
        else:
            rows[name] = value
    return list(rows.values())


def test_the_stop_ends_rehearsed_only_with_complete_evidence(api, receiver):
    app_id, aid, gen, content = at_the_stop(api, receiver)
    # Requests the egress controls denied are counted in the record, not disqualifying.
    egress = ("egress", {"blocked_requests": 2, "proxy_denied": {"named": 3}})
    write(aid, gen, complete(content, egress=egress))
    svc.finish_rehearsal(aid, "w1", gen)
    assert attempt(str(aid)).state == "rehearsed"
    (rec,) = records(app_id)
    assert rec.egress_proxy_denied == 3


@pytest.mark.parametrize(
    "change,code",
    [
        ({"recheck": None}, rehearsal.EVIDENCE_MISSING),
        ({"readback": None}, rehearsal.EVIDENCE_MISSING),
        ({"upload": None}, rehearsal.EVIDENCE_MISSING),
        ({"readback": ("readback", {"checked": 5, "mismatched": 1})},
         rehearsal.EVIDENCE_INCONSISTENT),
        ({"recheck": ("recheck", {"form": "changed"})}, rehearsal.EVIDENCE_INCONSISTENT),
    ],
    ids=["no_recheck", "no_readback", "no_upload", "readback_mismatch", "form_changed"],
)  # fmt: skip
def test_the_stop_refuses_incomplete_or_contradicting_evidence(api, receiver, change, code):
    app_id, aid, gen, content = at_the_stop(api, receiver)
    write(aid, gen, complete(content, **change))
    with pytest.raises(svc.GateRefused) as refused:
        svc.finish_rehearsal(aid, "w1", gen)
    assert refused.value.code == code
    assert attempt(str(aid)).state == "claimed" and records(app_id) == []  # nothing written
    assert svc.abandon(aid, "w1", gen, str(refused.value), code=refused.value.code)
    with SessionLocal() as db:
        (ev,) = db.scalars(select(AttemptEvent).where(
            AttemptEvent.attempt_id == aid, AttemptEvent.kind == "outcome_abandoned"))  # fmt: skip
        assert ev.detail["reason_code"] == code


@pytest.mark.parametrize("ack", [fixture_ats.ACK_ERROR, fixture_ats.ACK_NONE])
def test_the_stop_refuses_an_upload_not_acknowledged(api, receiver, ack):
    app_id, aid, gen, content = at_the_stop(api, receiver)
    (doc,) = content["documents"]
    write(aid, gen, complete(content, upload=("disclosure", {
        "field": doc["field"], "ack": ack, "sha256": doc["sha256"]})))  # fmt: skip
    with pytest.raises(svc.GateRefused) as refused:
        svc.finish_rehearsal(aid, "w1", gen)
    assert refused.value.code == rehearsal.EVIDENCE_INCONSISTENT and records(app_id) == []


def test_the_stop_refuses_a_document_that_was_not_approved(api, receiver):
    app_id, aid, gen, content = at_the_stop(api, receiver)
    (doc,) = content["documents"]
    rows = complete(content)
    rows.append(("disclosure", {"field": doc["field"], "ack": fixture_ats.ACK_SHOWN,
                                "sha256": "0" * 64}))  # fmt: skip
    write(aid, gen, rows)
    with pytest.raises(svc.GateRefused) as refused:
        svc.finish_rehearsal(aid, "w1", gen)
    assert refused.value.code == rehearsal.EVIDENCE_INCONSISTENT


def test_a_revocation_committed_while_the_stop_waits_is_refused(api, receiver, monkeypatch):
    app_id, aid, gen, content = at_the_stop(api, receiver)
    write(aid, gen, complete(content))
    original, done = pk.lock_application, []

    def lock_application(db, app_uuid):
        if not done:
            done.append(True)
            with SessionLocal() as other:
                pk.revoke(other, other.get(Application, uuid.UUID(app_id)))
                other.commit()
        return original(db, app_uuid)

    monkeypatch.setattr(pk, "lock_application", lock_application)
    with pytest.raises(svc.GateRefused, match="approval changed while it was being checked"):
        svc.finish_rehearsal(aid, "w1", gen)
    assert done == [True] and records(app_id) == [] and attempt(str(aid)).state == "claimed"


def test_a_gate_refuses_a_destination_whose_class_changed(api, receiver, monkeypatch):
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    assert attempt(str(aid)).destination_class == "fixture"
    gen = svc.claim(aid, "w1")
    monkeypatch.setattr(rehearsal, "destination_class", lambda origin: "real")
    with pytest.raises(svc.GateRefused, match="no longer the kind it was when queued"):
        svc.gate_before_disclosure(aid, "w1", gen)
    assert svc.fail_safe(aid, "w1", gen, "test finished")


def test_an_attempt_queued_before_classes_were_recorded_is_refused_plainly(api, receiver):
    """An attempt from before the migration (no recorded class) counts in no evidence class
    and is refused at its next gate with a plain message, never as a changed destination."""
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    with SessionLocal() as db:
        db.get(ExecutionAttempt, aid).destination_class = None
        db.commit()
    assert runner.run_attempt(str(aid), "w1") == "failed_safe"
    assert "queued before NoEfforts recorded what kind of destination" in attempt(
        str(aid)).outcome_detail  # fmt: skip
    assert receiver.ledger()["disclosures"] == []


def test_a_failed_statement_while_checking_a_record_is_a_refusal_not_an_error(
    api, receiver, monkeypatch
):
    _, rec = rehearsed_record(api, receiver)

    def broken(db, att, content):
        db.execute(text("SELECT 1 / 0"))  # the database refuses this statement

    monkeypatch.setattr(rehearsal, "evidence_facts", broken)
    with SessionLocal() as db:
        r = db.get(RehearsalRecord, rec.id)
        assert rehearsal.assess_record(db, r, adapter_version=r.adapter_version) == (
            rehearsal.CHECK_UNAVAILABLE)  # fmt: skip
        assert db.scalar(select(RehearsalRecord.id)) == rec.id  # the session is still usable


# ---------------------------------------------------------------- a record holds while it is true


def rehearsed_record(api, receiver) -> tuple[str, RehearsalRecord]:
    app_id = prepared_application(api, receiver, scope="disclose_only")
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    (rec,) = records(app_id)
    return app_id, rec


def assess(rec_id, **kw):
    with SessionLocal() as db:
        rec = db.get(RehearsalRecord, rec_id)
        return rehearsal.assess_record(db, rec, adapter_version=kw.pop("version",
                                       rec.adapter_version), **kw)  # fmt: skip


def edit_evidence(attempt_id, kind, **values):
    with SessionLocal() as db:
        row = db.scalar(select(Evidence).where(Evidence.attempt_id == attempt_id,
                                               Evidence.kind == kind))  # fmt: skip
        for k, v in values.items():
            setattr(row, k, v)
        db.commit()


def test_a_record_holds_only_while_its_evidence_and_attributes_do(api, receiver, monkeypatch):
    _, rec = rehearsed_record(api, receiver)
    assert assess(rec.id) is None
    assert assess(rec.id, version="another-version") == rehearsal.MISMATCHED
    assert assess(rec.id, destination_class="real") == rehearsal.MISMATCHED
    later = utcnow() + timedelta(days=get_settings().rehearsal_max_age_days, minutes=1)
    assert assess(rec.id, now=later) == rehearsal.STALE
    monkeypatch.setattr(get_settings(), "rehearsal_max_age_days", 0)
    assert assess(rec.id) == rehearsal.CHECK_UNAVAILABLE  # an invalid window refuses
    monkeypatch.undo()
    edit_evidence(rec.attempt_id, "readback", data={"checked": 5, "mismatched": 2})
    assert assess(rec.id) == rehearsal.EVIDENCE_INCONSISTENT
    edit_evidence(rec.attempt_id, "readback", data={"checked": 5, "mismatched": 0})
    assert assess(rec.id) is None
    with SessionLocal() as db:  # complete rows that no longer agree with the record
        db.get(RehearsalRecord, rec.id).egress_proxy_denied += 7
        db.commit()
    assert assess(rec.id) == rehearsal.EVIDENCE_INCONSISTENT
    with SessionLocal() as db:
        db.get(RehearsalRecord, rec.id).egress_proxy_denied -= 7
        db.commit()
    assert assess(rec.id) is None
    edit_evidence(rec.attempt_id, "recheck", retain_until=utcnow() - timedelta(seconds=1))
    assert assess(rec.id) == rehearsal.EVIDENCE_MISSING  # expired rows no longer count
    with SessionLocal() as db:
        db.get(RehearsalRecord, rec.id).destination_class = "real"  # tampered
        db.commit()
    assert assess(rec.id) == rehearsal.MISMATCHED


def test_deleting_an_applications_evidence_revokes_its_rehearsals(api, receiver, other_api):
    app_id, rec = rehearsed_record(api, receiver)
    assert other_api.delete(f"/applications/{app_id}/evidence").status_code == 404
    assert assess(rec.id) is None
    assert api.delete(f"/applications/{app_id}/evidence").status_code == 200
    (rec,) = records(app_id)
    assert rec.revoked_reason == "evidence_deleted" and assess(rec.id) == rehearsal.REVOKED
    with SessionLocal() as db:
        (ev,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.delete"))
        assert ev.meta["rehearsals_revoked"] == 1


# ---------------------------------------------------------------- shared vocabulary


def test_the_ack_and_strength_vocabulary_matches_the_adapters():
    from app.modules.execution.adapters import fake_api, greenhouse, greenhouse_dom

    assert rehearsal.PAGE_ACK_OK == fixture_ats.ACK_SHOWN
    assert rehearsal.API_ROUTE_ADAPTERS == set(runner.API_ADAPTERS)
    adapters = [*runner.ADAPTERS.values(), *runner.API_ADAPTERS.values()]
    assert rehearsal.ATTEMPT_BOUND_STRENGTHS == {a.confirmation_strength for a in adapters}
    assert {fake_api.FakeApiAdapter, greenhouse.GreenhouseHostedAdapter,
            greenhouse_dom.GreenhouseDomAdapter} <= set(adapters)  # fmt: skip


def test_only_a_configured_fixture_origin_outside_production_is_a_fixture(monkeypatch):
    fixture = get_settings().fixture_origins[0]
    assert rehearsal.destination_class(fixture) == "fixture"
    assert rehearsal.destination_class("https://careers.example.com") == "real"
    assert rehearsal.destination_class(None) == "real" and rehearsal.destination_class("") == "real"
    monkeypatch.setattr(get_settings(), "env", "production")
    assert rehearsal.destination_class(fixture) == "real"
