"""Helpers for execution tests: the independent receiver process and prepared attempts."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution.models import ExecutionAttempt
from tests.conftest import RECEIVER_PORT

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RECEIVER = ROOT / "fixtures" / "ats_receiver" / "receiver.py"
BASE = f"http://127.0.0.1:{RECEIVER_PORT}"
PDF = b"%PDF-1.4\n% synthetic resume for execution tests\n"


class Receiver:
    """The test oracle. Counts come from its own SQLite ledger, never from NoEfforts' DB."""

    def __init__(self) -> None:
        self.token = uuid.uuid4().hex
        self.ledger_path = tempfile.mktemp(prefix="receiver-ledger-", suffix=".db")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(RECEIVER),
                "--port",
                str(RECEIVER_PORT),
                "--ledger",
                self.ledger_path,
                "--admin-token",
                self.token,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", RECEIVER_PORT), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("receiver did not start")

    def _h(self):
        return {"X-Admin-Token": self.token}

    def config(self, **cfg):
        httpx.post(f"{BASE}/_admin/config", json=cfg, headers=self._h()).raise_for_status()

    def reset(self):
        httpx.post(f"{BASE}/_admin/reset", headers=self._h()).raise_for_status()

    def ledger(self) -> dict:
        return httpx.get(f"{BASE}/_admin/ledger", headers=self._h()).json()

    def form_html(self, slug="clinic") -> str:
        return httpx.get(f"{BASE}/apply/{slug}").text

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # a dropped-response request may still be sleeping
            self.proc.kill()
            self.proc.wait(timeout=5)


def synthetic_candidate(api) -> None:
    """Fictional candidate: profile, US work authorization (no sponsorship), one resume."""
    api.put(
        "/profile",
        json={
            "full_name": "Sam Synthetic",
            "given_name": "Sam",
            "family_name": "Synthetic",
            "contact_email": "sam.synthetic@example.com",
            "phone": "+1 555 0100",
            "residence_country": "US",
            "residence_city": "Springfield",
            "links": ["https://www.linkedin.com/in/sam-synthetic"],
        },
    )
    if not api.get("/profile/work-authorizations").json():
        api.post(
            "/profile/work-authorizations",
            json={
                "country_code": "US",
                "authorized": "yes",
                "sponsorship_needed_now": "no",
                "sponsorship_needed_future": "no",
            },
        )
    if not api.get("/documents").json():
        api.post("/documents", files={"file": ("resume.pdf", PDF, "application/pdf")})


def prepared_application(
    api,
    receiver,
    *,
    slug="clinic",
    why_text=None,
    bank_question=None,
    scope=None,
    url_suffix="",
    approve=True,
    sensitive=None,
) -> str:
    """Synthetic candidate + approved package for the receiver's form. Returns app id.
    `scope`: the approval's scope; None sends none (the default, submit). `url_suffix`: e.g.
    "?posting=2", another posting on the same form. `approve`: False leaves it unapproved.
    `bank_question` (the receiver in mode "bank_question" only): "input" or "save_to_bank"
    answers "Highest level of education completed"; "bank" relies on a saved answer. How you
    heard about the job is always answered for this application: never saved (D51).
    `sensitive` (C8): {"gender": (answer value or None, "disclose" | "withhold" | None)}.
    Each form or posting other than the default is another role, with its own title: one
    employer and one title would be a possible duplicate (S3, D59)."""
    synthetic_candidate(api)
    job = api.post(
        "/jobs",
        json={
            "url": f"{BASE}/apply/{slug}{url_suffix}",
            "title": "Clinic Assistant"
            + ("" if (slug, url_suffix) == ("clinic", "") else f" ({slug}{url_suffix})"),
            "employer": "Example Health Clinic (fictional)",
        },
    ).json()
    job_id = job["job"]["id"]
    r = api.post(f"/jobs/{job_id}/form", json={"html": receiver.form_html(slug)})
    assert r.status_code in (200, 201), r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    api.put(
        f"/applications/{app_id}/answers",
        json={"key": "hear_about", "value": {"label": "Referral"}},
    )
    if bank_question in ("input", "save_to_bank"):
        r = api.put(
            f"/applications/{app_id}/answers",
            json={
                "key": "education",
                "value": {"label": "Bachelor's degree"},
                "save_to_bank": bank_question == "save_to_bank",
            },
        )
        assert r.status_code == 200, r.text
    # bank_question == "bank": rely on an existing saved answer for the same wording
    if why_text:
        api.put(
            f"/applications/{app_id}/answers", json={"key": "why_us", "value": {"text": why_text}}
        )
    for key, (value, choice) in (sensitive or {}).items():
        if value is not None:
            r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
            assert r.status_code == 200, r.text
        if choice is not None:
            r = api.put(f"/applications/{app_id}/consents", json={"key": key, "choice": choice})
            assert r.status_code == 200, r.text
    v = api.put(
        f"/applications/{app_id}/consents", json={"key": "privacy_ack", "choice": "agree"}
    ).json()
    p = v["package"]
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    if not approve:
        return app_id
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    r = api.post(
        f"/applications/{app_id}/package/approve", json=body | ({"scope": scope} if scope else {})
    )
    assert r.status_code == 200, r.text
    return app_id


def queue(api, app_id) -> str:
    """Queue the application; the id of the attempt this created (its newest)."""
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        return str(
            db.scalar(
                select(ExecutionAttempt.id)
                .where(ExecutionAttempt.application_id == uuid.UUID(app_id))
                .order_by(ExecutionAttempt.created_at.desc())
                .limit(1)
            )
        )


def run_worker_process(
    attempt_id: str, worker: str, fault: str = "", timeout=90, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    env = os.environ | {"NOEFFORTS_FAULT": fault, "PYTHONPATH": str(BACKEND)} | (extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "app.modules.execution.cli", "run", attempt_id, worker],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def attempt(attempt_id: str) -> ExecutionAttempt:
    with SessionLocal() as db:
        return db.get(ExecutionAttempt, uuid.UUID(attempt_id))


def dump(obj) -> str:
    return json.dumps(obj, default=str)
