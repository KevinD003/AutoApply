"""Checks requested when verifying the Phase A foundation."""

import os
import subprocess
import sys
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.applications.service import transition
from app.modules.applications.states import Actor, AppState
from tests.conftest import Api


def test_csrf_token_is_bound_to_its_session(api, other_api):
    # A valid token from session B must not authorize a write with session A's cookie.
    r = api.client.put(
        "/profile", json={"full_name": "X"}, headers={"X-CSRF-Token": other_api.csrf}
    )
    assert r.status_code == 403
    assert api.put("/profile", json={"full_name": "X"}).status_code == 200


def test_logout_invalidates_cookie_and_token(api):
    cookie = api.client.cookies.get("ne_session")
    assert api.post("/auth/logout").status_code == 204
    replay = Api()
    replay.client.cookies.set("ne_session", cookie)
    assert replay.client.get("/profile").status_code == 401
    assert (
        replay.client.put(
            "/profile", json={"full_name": "X"}, headers={"X-CSRF-Token": api.csrf}
        ).status_code
        == 401
    )


def test_get_requests_do_not_need_csrf_but_writes_do(api):
    assert api.client.get("/profile").status_code == 200
    assert api.client.post("/jobs", json={"title": "A", "employer": "B"}).status_code == 403


def test_imports_never_touch_another_users_jobs(api, other_api):
    csv = b"job_url,title,employer\nhttps://boards.greenhouse.io/acme/jobs/77,Cook,Acme\n"
    a = api.post("/jobs/import", files={"file": ("a.csv", csv, "text/csv")}).json()
    b = other_api.post("/jobs/import", files={"file": ("b.csv", csv, "text/csv")}).json()
    assert a["created"] == 1 and b["created"] == 1  # each user gets their own row
    assert a["rows"][0]["job_id"] != b["rows"][0]["job_id"]
    mine = api.get("/jobs").json()["items"][0]
    assert mine["seen_count"] == 1  # the other user's import did not count as a sighting


def test_duplicate_applications_blocked_by_database(api):
    job = api.post("/jobs", json={"title": "Cook", "employer": "Diner"}).json()["job"]
    user_id = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        db.add(Application(user_id=user_id, job_id=uuid.UUID(job["id"])))
        db.commit()
        db.add(Application(user_id=user_id, job_id=uuid.UUID(job["id"])))
        try:
            db.commit()
            raise AssertionError("duplicate application was accepted")
        except IntegrityError:
            db.rollback()


def test_concurrent_application_creation_yields_one(api):
    job = api.post("/jobs", json={"title": "Cook", "employer": "Diner"}).json()["job"]
    results = []

    def go():
        results.append(api.post("/applications", json={"job_id": job["id"]}).json()["id"])

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(results)) == 1
    assert len(api.get("/applications").json()) == 1


def _app_in_state(api, state: AppState) -> str:
    job = api.post("/jobs", json={"title": "Cook", "employer": "Diner"}).json()["job"]
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        app.state = state
        db.commit()
    return app_id


def test_uncertain_submission_cannot_be_requeued_directly(api):
    app_id = _app_in_state(api, AppState.submitted_unconfirmed)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 400
    # Reconciliation needs a real statement and explicit confirmation.
    assert (
        api.post(
            f"/applications/{app_id}/reconcile",
            json={"finding": "not_received", "evidence": "short"},
        ).status_code
        == 422
    )
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={"finding": "not_received", "evidence": "Called HR, nothing on file"},
    )
    assert r.status_code == 400
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={
            "finding": "not_received",
            "evidence": "Called HR, nothing on file",
            "confirm_not_received": True,
        },
    )
    assert r.json()["state"] == "failed_retryable"
    # Even then, re-queueing needs an approved package (none exists here).
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409


def test_reconcile_received(api):
    app_id = _app_in_state(api, AppState.submitted_unconfirmed)
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={"finding": "received", "evidence": "Confirmation email REF-1 arrived"},
    )
    assert r.json()["state"] == "submitted_confirmed"


def test_application_state_survives_process_restart(api):
    """State lives in PostgreSQL: a separate process writes it, a fresh one reads it back."""
    app_id = _app_in_state(api, AppState.draft)
    code = (
        "import uuid,sys\n"
        "import app.models\n"
        "from app.core.db import SessionLocal\n"
        "from app.modules.applications.models import Application\n"
        "from app.modules.applications.service import transition\n"
        "from app.modules.applications.states import Actor, AppState\n"
        "with SessionLocal() as db:\n"
        f"    a = db.get(Application, uuid.UUID('{app_id}'))\n"
        "    transition(db, a, AppState.preparing, Actor.system, 'written by worker process')\n"
        "    db.commit()\n"
        "sys.exit(0)\n"
    )
    env = os.environ | {"PYTHONPATH": os.getcwd()}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, timeout=60)
    # The writer process has exited; a new session sees the committed state and its event.
    detail = api.get(f"/applications/{app_id}").json()
    assert detail["state"] == "preparing"
    assert detail["events"][-1]["reason"] == "written by worker process"


def test_concurrent_writers_conflict_instead_of_overwriting(api):
    app_id = uuid.UUID(_app_in_state(api, AppState.draft))
    with SessionLocal() as a, SessionLocal() as b:
        x = a.get(Application, app_id)
        y = b.get(Application, app_id)
        transition(a, x, AppState.preparing, Actor.system)
        a.commit()
        transition(b, y, AppState.cancelled, Actor.user)
        try:
            b.commit()
            raise AssertionError("stale write succeeded")
        except Exception as e:  # StaleDataError
            assert "StaleData" in type(e).__name__ or "expected to update" in str(e)
            b.rollback()
    with SessionLocal() as db:
        assert (
            db.scalar(select(Application.state).where(Application.id == app_id))
            == AppState.preparing
        )
