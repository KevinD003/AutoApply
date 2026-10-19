"""Phase C validation: forced readback failures, disclosure counting (uploads and autosave),
real lease expiry, and every protected-data mutation path racing a running attempt.

Real vs simulated is stated per test. Receiver ledger counts are the oracle."""

import os
import subprocess
import sys
import tempfile
import time
import uuid

import pytest

from app.core.db import SessionLocal, utcnow
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import drafting
from app.modules.preparation.drafting import DraftResult
from tests.execution_harness import (
    BACKEND,
    PDF,
    Receiver,
    attempt,
    prepared_application,
    queue,
)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def blocked_worker(aid, point, extra_env=None):
    gate = tempfile.mktemp(prefix="release-")
    env = (
        os.environ
        | {"NOEFFORTS_FAULT": f"{point}=waitfile:{gate}", "PYTHONPATH": str(BACKEND)}
        | (extra_env or {})
    )
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.modules.execution.cli",
            "run",
            aid,
            f"w-{uuid.uuid4().hex[:6]}",
        ],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return p, gate


def release(p, gate):
    open(gate, "w").close()
    out, err = p.communicate(timeout=90)
    return out.strip().splitlines()[-1] if out.strip() else err[-500:]


def wait_for(pred, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.1)
    raise AssertionError("condition not reached")


def kinds(led):
    out = {}
    for d in led["disclosures"]:
        out[d["kind"]] = out.get(d["kind"], 0) + 1
    return out


# ------------------------------------------------------------------ readback (real browser)


@pytest.mark.parametrize(
    "tamper,key",
    [
        ("text", "first_name"),
        ("select", "country"),
        ("checkbox", "privacy_ack"),
        ("file", "resume"),
    ],
)
def test_page_altering_a_filled_value_stops_before_submit(api, receiver, tamper, key):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(tamper=tamper)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    rb = next(e for e in att["evidence"] if e["kind"] == "readback")["data"]
    assert key in rb["mismatches"], rb
    assert att["send_started_at"] is None


# ------------------------------------------------------------------ disclosure counting


def test_autosave_and_upload_are_counted_separately_from_acceptance(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(autosave=True)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    k = kinds(led)
    assert led["accepted"] == 1 and k["upload"] == 1 and k["autosave"] >= 5, k
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    disc = next(e for e in att["evidence"] if e["kind"] == "disclosure")["data"]
    approved = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert disc["sha256"] == approved["documents"][0]["sha256"]
    upload = next(d for d in led["disclosures"] if d["kind"] == "upload")
    assert __import__("json").loads(upload["detail"])["sha256"] == disc["sha256"]


def test_revoking_after_disclosure_cannot_recall_transmitted_data(api, receiver):
    """Real process paused before the send gate; approval revoked through the API."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(autosave=True)
    w, gate = blocked_worker(aid, "before_send_gate")
    wait_for(lambda: kinds(receiver.ledger()).get("upload") == 1)
    api.post(f"/applications/{app_id}/package/revoke")
    assert release(w, gate) == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0
    assert kinds(led)["upload"] == 1 and kinds(led)["autosave"] >= 5  # already sent; stays sent
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    assert att["disclosure_started_at"] is not None
    assert any(e["kind"] == "disclosure" for e in att["evidence"])


# ------------------------------------------------------------------ real lease expiry


def test_stale_worker_with_real_lease_expiry(api, receiver):
    """Real paused process; the lease expires by wall-clock time (3s), not by editing the DB."""
    receiver.config(idempotent=False)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    old, gate = blocked_worker(aid, "after_claim", {"NOEFFORTS_LEASE_SECONDS": "3"})
    wait_for(lambda: attempt(aid).state == "claimed")
    wait_for(lambda: attempt(aid).lease_expires_at < utcnow(), timeout=10)
    assert svc.sweep()["repended"] == 1
    assert runner.run_attempt(aid, "new") == "confirmed"
    assert release(old, gate) == "lost_authority"
    assert receiver.ledger()["accepted"] == 1


# ------------------------------------------------------------------ mutation paths


def _keep_profile(api):
    prof = api.get("/profile").json()
    return {
        k: prof[k]
        for k in (
            "full_name",
            "given_name",
            "family_name",
            "contact_email",
            "phone",
            "residence_country",
            "residence_city",
            "links",
            "summary",
        )
    }


class _Fake:
    name = "test-fake"

    def draft(self, req):
        return DraftResult(
            text="I value careful patient intake.", provider=self.name, evidence=[req.facts[0].id]
        )


def m_work_auth(api, app_id, ctx):
    wa = api.get("/profile/work-authorizations").json()[0]
    api.put(
        f"/profile/work-authorizations/{wa['id']}",
        json={
            "country_code": "US",
            "authorized": "yes",
            "sponsorship_needed_now": "yes",
            "sponsorship_needed_future": "yes",
        },
    )


def m_profile_name(api, app_id, ctx):
    api.put("/profile", json=_keep_profile(api) | {"given_name": "Samuel"})


def m_document(api, app_id, ctx):
    r = api.get("/documents").json()[0]
    api.post(
        "/documents",
        files={"file": ("cv2.pdf", PDF + b"2", "application/pdf")},
        data={"lineage_id": r["lineage_id"]},
    )


def m_consent(api, app_id, ctx):
    api.put(f"/applications/{app_id}/consents/gender", json={"choice": "withhold"})


def m_answer(api, app_id, ctx):
    api.put(f"/applications/{app_id}/answers/hear_about", json={"value": {"label": "Job board"}})


def m_answer_bank(api, app_id, ctx):
    entry = api.get("/answer-bank").json()[0]
    api.delete(f"/answer-bank/{entry['id']}")


def m_preferences(api, app_id, ctx):
    api.put("/profile/preferences", json={"willing_to_relocate": "yes"})


def m_job(api, app_id, ctx):
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    api.patch(f"/jobs/{job_id}", json={"title": "Senior Clinic Assistant"})


def m_form(api, app_id, ctx):
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    html = ctx["receiver"].form_html().replace("Location (City)", "City you live in")
    assert api.post(f"/jobs/{job_id}/form", json={"html": html}).json()["version"] == 2


def m_draft(api, app_id, ctx):
    # A summary to ground on (editing the summary alone does not affect this package).
    api.put("/profile", json=_keep_profile(api) | {"summary": "Patient intake experience."})
    ctx["monkeypatch"].setattr(drafting, "get_provider", lambda: _Fake())
    d = api.post(f"/applications/{app_id}/answers/why_us/draft").json()
    assert api.post(f"/applications/{app_id}/drafts/{d['id']}/accept").status_code == 200


MUTATIONS = {
    "work_authorization": m_work_auth,
    "profile_name": m_profile_name,
    "document_version": m_document,
    "consent": m_consent,
    "answer": m_answer,
    "answer_bank_delete": m_answer_bank,
    "preferences": m_preferences,
    "job_destination": m_job,
    "form_version": m_form,
    "draft_accept": m_draft,
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_every_protected_mutation_stops_a_running_attempt(api, receiver, monkeypatch, name):
    """Real worker process paused after filling; the mutation goes through the public API."""
    if name == "answer_bank_delete":
        prepared_application(api, receiver, hear_about="save_to_bank")
        # Different job (slug) so this is a second application whose answer comes from the bank.
        app_id = prepared_application(api, receiver, slug="clinic2", hear_about="bank")
        assert (
            next(
                a
                for a in api.get(f"/applications/{app_id}/package").json()["package"]["content"][
                    "answers"
                ]
                if a["key"] == "hear_about"
            )["source"]
            == "answer_bank"
        )
    else:
        app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = blocked_worker(aid, "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    MUTATIONS[name](api, app_id, {"receiver": receiver, "monkeypatch": monkeypatch})
    assert release(w, gate) == "abandoned", name
    assert "changed after approval" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_unrelated_edit_does_not_stop_a_running_attempt(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = blocked_worker(aid, "before_send_gate")
    wait_for(lambda: attempt(aid).disclosure_started_at is not None)
    api.post("/profile/education", json={"institution": "Synthetic College"})
    assert release(w, gate) == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_mutations_after_send_gate_do_not_change_what_was_sent(api, receiver):
    """After the linearization point the worker sends the approved snapshot, not live data."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    w, gate = blocked_worker(aid, "before_click")
    wait_for(lambda: attempt(aid).state == "sending")
    api.put("/profile", json=_keep_profile(api) | {"given_name": "Changed"})
    assert release(w, gate) == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"]["first_name"] == "Sam"
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).state == "confirmed"
