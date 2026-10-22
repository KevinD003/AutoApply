"""A revocation the user commits while a gate waits for the application lock must stop that
gate. The gates take their locks (attempt, application, approval) and then read what is
committed (D46): a revocation committed in between is seen. (They used to read a REPEATABLE READ
snapshot taken at the attempt lock, which missed it until D43 locked the approval row.)
Synthetic data and the local receiver only."""

import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.execution import service as svc
from app.modules.preparation import package as pk
from tests.execution_harness import Receiver, attempt, prepared_application, queue


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def revoke_while_the_gate_waits(monkeypatch, app_id: str) -> list[bool]:
    """The first application lock a gate takes is preceded by a revocation committed in a
    second session, after the gate's snapshot (taken at its attempt lock) was fixed."""
    original, done = pk.lock_application, []

    def lock_application(db, aid):
        if not done:
            done.append(True)
            with SessionLocal() as other:
                pk.revoke(other, other.get(Application, uuid.UUID(app_id)))
                other.commit()
        return original(db, aid)

    monkeypatch.setattr(pk, "lock_application", lock_application)
    return done


@pytest.mark.parametrize("gate", ["disclosure", "send"])
def test_a_revocation_committed_while_a_gate_waits_is_refused(api, receiver, monkeypatch, gate):
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    gen = svc.claim(aid, "w1")
    if gate == "send":
        svc.gate_before_disclosure(aid, "w1", gen)
    done = revoke_while_the_gate_waits(monkeypatch, app_id)
    with pytest.raises(svc.GateRefused, match="approval revoked"):
        (svc.gate_before_send if gate == "send" else svc.gate_before_disclosure)(aid, "w1", gen)
    assert done == [True]  # the revocation really happened inside the window
    a = attempt(str(aid))
    assert a.state == "claimed" and a.send_started_at is None
    assert svc.abandon(aid, "w1", gen, "test finished") or svc.fail_safe(aid, "w1", gen, "test")
