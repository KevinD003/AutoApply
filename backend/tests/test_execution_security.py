"""Verification-code checkpoints, browser egress, secret leakage, tenancy and production
lockout for execution. Synthetic data and the local receiver only."""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal, engine, utcnow
from app.core.urlsafety import UnsafeURL, check_url_syntax
from app.modules.execution import runner
from app.modules.execution.models import Checkpoint
from app.modules.execution.policy import UnsupportedDestination, adapter_for
from app.modules.preparation.models import ApplicationPackage
from tests.execution_harness import (
    BACKEND,
    BASE,
    PDF,
    Receiver,
    attempt,
    prepared_application,
    queue,
)

FAKE_SECRET = "SYNTHETIC-SECRET-7F3A9-DO-NOT-LEAK"
CANARY_PORT = 8798


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def wait_for(pred, timeout=40.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("condition not reached")


def open_checkpoint(api, app_id, round_=1):
    def get():
        atts = api.get(f"/applications/{app_id}/attempts").json()
        cps = [c for a in atts for c in a["checkpoints"]]
        return next((c for c in cps if c["status"] == "open" and c["round"] == round_), None)

    return wait_for(get)


def start_worker(aid, worker="w-otp"):
    env = os.environ | {"PYTHONPATH": str(BACKEND), "NOEFFORTS_FAULT": ""}
    return subprocess.Popen(
        [sys.executable, "-m", "app.modules.execution.cli", "run", aid, worker],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


# ------------------------------------------------------------------ verification codes


def test_code_checkpoint_wrong_then_right_code_and_replay(api, receiver, other_api):
    app_id = prepared_application(api, receiver, why_text=f"Intake work. {FAKE_SECRET}")
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    w = start_worker(aid)
    cp = open_checkpoint(api, app_id, 1)
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    real = wait_for(lambda: receiver.ledger()["challenges"])[-1]["code"]
    wrong = "999999" if real != "999999" else "111111"
    # Other users cannot touch it, even with the right ids.
    assert (
        other_api.post(
            f"/applications/{app_id}/checkpoints/{cp['id']}/code", json={"round": 1, "code": real}
        ).status_code
        == 404
    )
    assert (
        api.post(
            f"/applications/{app_id}/checkpoints/{cp['id']}/code", json={"round": 1, "code": wrong}
        ).status_code
        == 202
    )
    cp2 = open_checkpoint(api, app_id, 2)
    # Replaying round 1 is refused.
    assert (
        api.post(
            f"/applications/{app_id}/checkpoints/{cp['id']}/code", json={"round": 1, "code": real}
        ).status_code
        == 409
    )
    assert (
        api.post(
            f"/applications/{app_id}/checkpoints/{cp2['id']}/code", json={"round": 2, "code": real}
        ).status_code
        == 202
    )
    out, err = w.communicate(timeout=60)
    assert out.strip() == "confirmed", err[-800:]
    assert receiver.ledger()["accepted"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"
    # Code erased; nothing about it in any stored artifact or worker output.
    with SessionLocal() as db:
        assert all(c.code is None for c in db.query(Checkpoint).all())
    leaks = scan_for([real, FAKE_SECRET])
    assert leaks == {}, leaks
    assert real not in out + err and FAKE_SECRET not in out + err


def test_code_checkpoint_expiry_stops_without_acceptance(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    w = start_worker(aid)
    cp = open_checkpoint(api, app_id, 1)
    with SessionLocal() as db:
        db.get(Checkpoint, uuid.UUID(cp["id"])).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    out, _ = w.communicate(timeout=60)
    assert out.strip() == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    r = api.post(
        f"/applications/{app_id}/checkpoints/{cp['id']}/code", json={"round": 1, "code": "123456"}
    )
    assert r.status_code == 409


def test_too_many_wrong_codes(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    w = start_worker(aid)
    for rnd in (1, 2, 3):
        cp = open_checkpoint(api, app_id, rnd)
        real = receiver.ledger()["challenges"][-1]["code"]
        api.post(
            f"/applications/{app_id}/checkpoints/{cp['id']}/code",
            json={"round": rnd, "code": "000000" if real != "000000" else "000001"},
        )
    out, _ = w.communicate(timeout=60)
    assert out.strip() == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def scan_for(needles: list[str]) -> dict:
    """Search every stored artifact type except the approved package itself (which legitimately
    contains the answers) for the given strings."""
    tables = {
        "execution_evidence": "data::text",
        "attempt_events": "detail::text",
        "audit_events": "meta::text",
        "application_events": "coalesce(reason,'')",
        "outbox_messages": "attempt_id::text || coalesce(last_error,'')",
        "checkpoints": "coalesce(code,'') || coalesce(message,'')",
        "execution_attempts": "coalesce(outcome_detail,'')",
    }
    found = {}
    with engine.connect() as c:
        for t, col in tables.items():
            for n in needles:
                hit = c.execute(
                    text(f"select count(*) from {t} where {col} like :n"), {"n": f"%{n}%"}
                ).scalar()
                if hit:
                    found[f"{t}:{n}"] = hit
    return found


# ------------------------------------------------------------------ egress


class _Canary(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):  # noqa: N802
        _Canary.hits.append(self.path)
        self.send_response(200)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *a):
        pass


@pytest.fixture
def canary():
    _Canary.hits = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", CANARY_PORT), _Canary)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield _Canary.hits
    srv.shutdown()
    srv.server_close()


def test_browser_cannot_reach_other_origins(api, receiver, canary):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="hostile", canary=f"http://127.0.0.1:{CANARY_PORT}")
    assert runner.run_attempt(aid, "w1") == "confirmed"
    time.sleep(0.5)
    assert canary == [], canary  # img, iframe, fetch, beacon and redirect all blocked
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    eg = next(e for e in att["evidence"] if e["kind"] == "egress")["data"]
    for origin in (
        f"http://127.0.0.1:{CANARY_PORT}",
        "http://169.254.169.254",
        "http://10.0.0.1",
        "http://[::1]",
    ):
        assert origin in eg["origins"], eg
    assert receiver.ledger()["accepted"] == 1


def test_production_rejects_fixture_destinations(monkeypatch):
    s = get_settings()
    dest = {"origin": BASE, "submit_url": f"{BASE}/apply/clinic/submit"}
    assert adapter_for(dest) == "fixture_ats"
    assert check_url_syntax(f"{BASE}/apply/clinic")
    monkeypatch.setattr(s, "env", "production")
    with pytest.raises(UnsupportedDestination):
        adapter_for(dest)
    with pytest.raises(UnsafeURL):
        check_url_syntax(f"{BASE}/apply/clinic")


def test_real_employer_destination_is_refused_at_queue(api, receiver):
    """An approved package for a real ATS URL cannot be queued: no live adapter exists."""
    from app.modules.preparation.fixtures_registry import fixture_html

    app_id = prepared_application(api, receiver)  # builds profile, resume, etc.
    job = api.post(
        "/jobs",
        json={"url": "https://boards.greenhouse.io/acme/jobs/1", "title": "T", "employer": "E"},
    ).json()["job"]
    html = fixture_html("basic").replace('action="#"', 'action="/acme/jobs/1/submit"')
    assert api.post(f"/jobs/{job['id']}/form", json={"html": html}).status_code == 201
    real_app = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    api.put(f"/applications/{real_app}/answers/hear_about", json={"value": {"label": "Referral"}})
    v = api.put(f"/applications/{real_app}/consents/privacy_ack", json={"choice": "agree"}).json()[
        "package"
    ]
    assert v["content"]["destination"]["origin"] == "https://boards.greenhouse.io"
    api.post(
        f"/applications/{real_app}/package/approve",
        json={"version": v["version"], "content_hash": v["content_hash"]},
    )
    r = api.post(f"/applications/{real_app}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "only supported for local test fixtures" in r.json()["detail"]
    assert api.get(f"/applications/{real_app}/attempts").json() == []
    assert app_id  # the fixture application is untouched


# ------------------------------------------------------------------ tenancy


def test_execution_resources_are_tenant_bound(api, receiver, other_api):
    app_id = prepared_application(api, receiver)
    queue(api, app_id)
    assert other_api.get(f"/applications/{app_id}/attempts").status_code == 404
    assert other_api.post(f"/applications/{app_id}/cancel").status_code == 404
    # Nested mismatch: the other user's own application id with this user's checkpoint id.
    other_job = other_api.post("/jobs", json={"title": "X", "employer": "Y"}).json()["job"]
    other_app = other_api.post("/applications", json={"job_id": other_job["id"]}).json()["id"]
    fake_cp = str(uuid.uuid4())
    assert (
        other_api.post(
            f"/applications/{other_app}/checkpoints/{fake_cp}/code",
            json={"round": 1, "code": "123456"},
        ).status_code
        == 404
    )


def test_worker_derives_tenant_from_attempt_not_payload(api, receiver, other_api):
    """A package pointing at another user's document is refused by the worker."""
    other_doc = other_api.post(
        "/documents", files={"file": ("x.pdf", PDF, "application/pdf")}
    ).json()
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        pkg = db.get(ApplicationPackage, attempt(aid).package_id)
        content = json.loads(json.dumps(pkg.content))
        content["documents"][0]["document_id"] = other_doc["id"]
        pkg.content = content  # simulate tampering; the hash is not recomputed
        db.commit()
    assert runner.run_attempt(aid, "w1") in ("failed_safe", "error")
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
