"""An outcome that becomes unknown during a verification-code step is quarantined
(`submitted_unconfirmed`), never retried, never left stuck. Found in the 2026-10-27 review: the
transition table listed `needs_user_action -> submitted_unconfirmed` twice, the later entry (user
only) won, and both the worker and the sweeper were refused. One refused row also rolled back the
sweeper's whole batch. Synthetic data and the local receiver only; the receiver's ledger is the
oracle for what reached the employer."""

import ast
import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.db import SessionLocal, utcnow
from app.modules.applications.states import TRANSITIONS, Actor, AppState
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from tests.execution_harness import (
    BACKEND,
    Receiver,
    attempt,
    prepared_application,
    queue,
    run_worker_process,
)


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


def open_checkpoint(api, app_id):
    def get():
        atts = api.get(f"/applications/{app_id}/attempts").json()
        return next((c for a in atts for c in a["checkpoints"] if c["status"] == "open"), None)

    return wait_for(get)


def start_worker(aid, worker, **settings):
    env = os.environ | {"PYTHONPATH": str(BACKEND), "NOEFFORTS_FAULT": ""}
    env |= {f"NOEFFORTS_{k.upper()}": str(v) for k, v in settings.items()}
    return subprocess.Popen(
        [sys.executable, "-m", "app.modules.execution.cli", "run", aid, worker],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def expire_lease(aid: str) -> None:
    with SessionLocal() as db:
        db.get(ExecutionAttempt, uuid.UUID(aid)).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()


def stale_claimed_attempt(api, receiver, slug) -> tuple[str, str]:
    """An attempt whose worker died before opening the page: claimed, nothing disclosed."""
    app_id = prepared_application(api, receiver, slug=slug)
    aid = queue(api, app_id)
    assert run_worker_process(aid, "w-dead", fault="before_navigate=exit").returncode == 137
    expire_lease(aid)
    return app_id, aid


# ------------------------------------------------------------------ the table


def test_no_dict_literal_in_the_backend_repeats_a_key():
    """Python keeps the last of two equal keys silently, and ruff checks literal keys only."""
    found = []
    for p in sorted((BACKEND / "app").rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(), str(p))):
            if isinstance(node, ast.Dict):
                keys = [ast.dump(k) for k in node.keys if k is not None]
                found += [f"{p.name}:{node.lineno}" for k in set(keys) if keys.count(k) > 1]
    assert found == []


def test_an_unknown_outcome_in_the_code_step_may_be_recorded_by_the_worker_and_the_sweeper():
    actors = TRANSITIONS[AppState.needs_user_action][AppState.submitted_unconfirmed]
    assert actors == {Actor.worker, Actor.system, Actor.user}


# ------------------------------------------------------------------ the worker


def test_an_unknown_result_after_the_code_is_quarantined_and_never_sent_again(api, receiver):
    """The employer accepts the code but its reply never arrives: the worker cannot tell, so the
    application is `submitted_unconfirmed` and nothing is ever sent again."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp", verify_drop=True)
    w = start_worker(aid, "w-code", submit_timeout_seconds=4)
    cp = open_checkpoint(api, app_id)
    code = wait_for(lambda: receiver.ledger()["challenges"])[-1]["code"]
    body = {"round": 1, "code": code}
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code", json=body)
    assert r.status_code == 202, r.text
    out, err = w.communicate(timeout=90)
    assert out.strip() == "unknown", err[-800:]
    assert receiver.ledger()["accepted"] == 1  # it did reach the employer
    assert attempt(aid).state == "unknown"
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    time.sleep(3)  # bounded observation window: a late duplicate would land here
    assert runner.run_attempt(aid, "w-again") == "ignored"
    again = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert again.status_code == 400 and "Cannot move" in again.text, again.text
    assert receiver.ledger()["accepted"] == 1


# ------------------------------------------------------------------ the sweeper


def test_the_sweeper_quarantines_a_worker_that_died_waiting_for_the_code(api, receiver, other_api):
    """Recovered in the same sweep as another user's stale attempt, which is re-pended as
    before. The code that was typed for the dead worker is erased, and its checkpoint takes no
    more codes."""
    _, other_aid = stale_claimed_attempt(other_api, receiver, "clinic2")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    receiver.config(mode="otp")
    w = start_worker(aid, "w-code")
    cp = open_checkpoint(api, app_id)
    w.kill()
    w.wait(timeout=30)
    code = receiver.ledger()["challenges"][-1]["code"]
    body = {"round": 1, "code": code}
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code", json=body)
    assert r.status_code == 202, r.text  # typed after the worker died: held, never used
    expire_lease(aid)
    out = svc.sweep(publish_new=False)
    assert (out["unknown"], out["repended"], out["errors"]) == (1, 1, 0), out
    assert attempt(aid).state == "unknown"
    assert attempt(other_aid).state == "pending"
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    with SessionLocal() as db:
        held = db.get(Checkpoint, uuid.UUID(cp["id"]))
        assert (held.status, held.code) == ("expired", None)
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code", json=body)
    assert r.status_code == 409, r.text
    assert runner.run_attempt(aid, "w-again") == "ignored"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["challenges"][-1]["done"] is False


def test_one_row_that_cannot_be_recovered_does_not_stop_the_others(
    api, receiver, other_api, monkeypatch
):
    """Defence in depth: each stale attempt is recovered in its own savepoint. One that fails
    part-way (here a database error after its changes were made) stays exactly as it was for
    the next sweep, is counted, and never stops the others or leaves a half-written row."""
    _, mine = stale_claimed_attempt(api, receiver, "clinic")
    _, theirs = stale_claimed_attempt(other_api, receiver, "clinic2")
    broken = attempt(mine).id
    real = svc.event

    def event(db, att, kind, **kw):
        if att.id == broken:
            db.execute(text("select 1/0"))  # fails after this row's changes
        return real(db, att, kind, **kw)

    monkeypatch.setattr(svc, "event", event)
    out = svc.sweep(publish_new=False)
    assert (out["repended"], out["errors"]) == (1, 1), out
    assert attempt(theirs).state == "pending"
    still = attempt(mine)
    assert (still.state, still.retry_count) == ("claimed", 0)
    assert still.lease_expires_at is not None and still.lease_expires_at < utcnow()
    monkeypatch.setattr(svc, "event", real)
    out = svc.sweep(publish_new=False)
    assert (out["repended"], out["errors"]) == (1, 0), out
    assert attempt(mine).state == "pending"
