"""D147: a database restored from a backup comes up held, and nothing it restored runs.

A restore is made here by giving the database another database's stamp, which is what a restore
into a new database leaves behind (the deployment guide's §7). `test_migrations.py` makes a real
copy of a migrated database and finds it held; the Compose smoke test restores a real dump. The
receiver's ledger is the oracle for what reached the employer. Every form is a local stand-in;
synthetic data only."""

import json
import time
import uuid

import pytest
import redis
from sqlalchemy import select, text, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.audit.models import AuditEvent
from app.modules.autoapply import service as auto
from app.modules.autoapply.models import AutoApplyPrefs
from app.modules.execution import cli, restore, runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt, InstanceStamp, OutboxMessage
from app.modules.preparation.models import PackageApproval
from tests.conftest import Api
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_celery_execution import Worker, claims, clean_broker, queued
from tests.test_republish_queued import Published, set_attempt

RESTORED = svc.RETIRED["restored_from_backup"]


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    clean_broker()
    yield
    clean_broker()


def restored() -> None:
    """As a restore into a new database leaves it: the stamp is another database's."""
    restore.resolve()  # stamps the database (the per-test cleanup removes every row)
    with SessionLocal() as db:
        db.execute(update(InstanceStamp).values(db_oid=InstanceStamp.db_oid + 1))
        db.commit()


def held() -> bool:
    with SessionLocal() as db:
        return restore.held(db)


def app_state(app_id: str) -> str:
    with SessionLocal() as db:
        return db.get(Application, uuid.UUID(app_id)).state


def set_app(app_id: str, state: str) -> None:
    with SessionLocal() as db:
        db.execute(
            update(Application).where(Application.id == uuid.UUID(app_id)).values(state=state)
        )
        db.commit()


def live_approvals(app_id: str) -> list[PackageApproval]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()


def retired_reasons(app_id: str) -> list[str]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval.invalidation_reason).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_not(None),
            )
        ).all()


def nothing_reached_the_employer(receiver) -> None:
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []


# --------------------------------------------------------------------------- the stamp


def test_a_database_stamps_itself_and_is_not_held():
    assert restore.resolve() is None  # the per-test cleanup removed the stamp: written again
    with SessionLocal() as db:
        own = db.scalar(text("SELECT oid FROM pg_database WHERE datname = current_database()"))
        assert db.get(InstanceStamp, restore.STAMP_ID).db_oid == own
        assert restore.held(db) is False
    assert restore.resolve() is None  # its own stamp: nothing to do
    assert restore.status() == {"held": False, "stamped": True, "restored_at": None,
                                "summary": None}  # fmt: skip


def test_a_database_with_no_stamp_is_not_held(api, receiver):
    """A database restored from a backup made before D147 has no stamp until its upgrade
    stamps it; that cannot be told from a new database (D147 says so)."""
    aid = queue(api, prepared_application(api, receiver))
    with SessionLocal() as db:
        assert db.get(InstanceStamp, restore.STAMP_ID) is None
        assert restore.held(db) is False
    assert svc.claim(uuid.UUID(aid), "w1") == 1


# --------------------------------------------------------------------------- held


def test_a_restored_database_takes_nothing_and_queues_nothing(api, receiver):
    aid = queue(api, prepared_application(api, receiver))
    restored()
    assert held()
    assert svc.claim(uuid.UUID(aid), "w1") is None  # whatever delivers its message
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert attempt(aid).state == "pending" and claims(aid) == 0
    other = prepared_application(api, receiver, url_suffix="?posting=2")
    r = api.post(f"/applications/{other}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "(reason: restored_backup_held)" in r.text, r.text
    assert app_state(other) != "queued"
    nothing_reached_the_employer(receiver)


def test_the_standing_rule_does_nothing_while_held(api, receiver, monkeypatch):
    """The rule would act (it does once the hold is resolved and you resume it), but not while
    the database is held: it approves and queues nothing."""
    from tests.test_auto_apply import ready

    s = get_settings()
    monkeypatch.setattr(s, "auto_apply_enabled", True)
    monkeypatch.setattr(s, "auto_apply_daily_cap", 5)
    monkeypatch.setattr(s, "execution_test_rehearsal_rule_paths", ["greenhouse_live:*"])
    receiver.config(mode="normal")
    _, app_id = ready(api)
    restored()
    assert auto.tick() == 0
    assert live_approvals(app_id) == [] and not attempts_of(app_id)
    assert restore.resolve() is not None
    assert auto.tick() == 0  # the restore paused it
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert auto.tick() == 1  # resumed by you: it acts again
    assert len(attempts_of(app_id)) == 1


def attempts_of(app_id: str) -> list[ExecutionAttempt]:
    with SessionLocal() as db:
        return db.scalars(
            select(ExecutionAttempt).where(ExecutionAttempt.application_id == uuid.UUID(app_id))
        ).all()


# --------------------------------------------------------------------------- resolving


def test_resolving_ends_what_was_queued_and_never_runs_it(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)  # its message not published yet
    restored()
    done = restore.resolve()
    assert done["ended"] == {"pending": 1} and done["approvals"] == 1 and done["resolved_at"]
    att = attempt(aid)
    assert (att.state, att.outcome_detail) == ("failed_safe", restore.ENDED_QUEUED)
    assert app_state(app_id) == "awaiting_approval"
    assert retired_reasons(app_id) == [RESTORED] and live_approvals(app_id) == []
    (m,) = msgs(aid)
    assert m.dispatched_at is not None and m.last_error == "restored"  # never published
    with SessionLocal() as db:
        audit = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "package.approval_retired")
        ).all()
    assert [a.get("reason_code") for a in audit] == ["restored_from_backup"]
    assert not held() and runner.run_attempt(aid, "w1") == "ignored"
    out = Published()
    assert svc.relay_outbox(out) == 0 and svc.republish_waiting(out) == 0 and out.sent == []
    nothing_reached_the_employer(receiver)
    st = restore.status()
    assert st["held"] is False and st["restored_at"] and st["summary"] == done


def msgs(aid: str) -> list[OutboxMessage]:
    with SessionLocal() as db:
        return db.scalars(
            select(OutboxMessage).where(OutboxMessage.attempt_id == uuid.UUID(aid))
        ).all()


@pytest.mark.parametrize(
    "was,app_before,entered,state,app_after,detail",
    [
        ("claimed", "running", False, "failed_safe", "needs_user_action", restore.ENDED_QUEUED),
        ("claimed", "running", True, "abandoned", "needs_user_action", restore.ENDED_ENTERED),
        ("sending", "submitting", True, "unknown", "submitted_unconfirmed", restore.ENDED_SENDING),
        ("awaiting_code", "needs_user_action", True, "unknown", "submitted_unconfirmed",
         restore.ENDED_SENDING),
    ],
)  # fmt: skip
def test_resolving_ends_each_state_in_progress_as_the_sweeper_would(
    api, receiver, was, app_before, entered, state, app_after, detail
):
    """What the backup shows in progress had no worker after the restore. Ended as the sweeper
    ends an attempt whose worker is gone, except that nothing is ever put back in the queue:
    taken before anything was entered, it stopped; entered, it waits for you; past the send
    gate, its outcome is unknown and it is never sent again."""
    from app.core.db import utcnow

    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    set_attempt(aid, state=was, generation=1, lease_owner="gone", lease_expires_at=utcnow(),
                disclosure_started_at=utcnow() if entered else None)  # fmt: skip
    set_app(app_id, app_before)
    restored()
    done = restore.resolve()
    assert done["ended"] == {was: 1}
    att = attempt(aid)
    assert (att.state, att.outcome_detail, att.lease_owner) == (state, detail, None)
    assert app_state(app_id) == app_after
    assert live_approvals(app_id) == []
    assert svc.claim(uuid.UUID(aid), "w1") is None and claims(aid) == 0
    nothing_reached_the_employer(receiver)


def test_resolving_pauses_every_rule_and_tells_every_account(api, other_api, receiver):
    """Every account that existed then: its rule paused, and its feed says what the restore
    did. An account made after the restore lost nothing to it and is told nothing."""
    owner = api.get("/auth/me").json()["user_id"]
    with SessionLocal() as db:
        db.add(AutoApplyPrefs(user_id=uuid.UUID(owner), paused=False))
        db.commit()
    restored()
    done = restore.resolve()
    assert done["paused"] == 1  # the other account had not turned it on
    assert api.get("/auto-apply").json()["paused"] is True
    for a in (api, other_api):
        items = [i for i in a.get("/notifications").json()["items"]
                 if i["kind"] == "restored_backup"]  # fmt: skip
        assert len(items) == 1 and items[0]["needs_action"] is True, items
        assert "restored from a backup" in items[0]["text"]
    later = Api()
    later.register(email="later.synthetic@example.com")
    assert not [i for i in later.get("/notifications").json()["items"]
                if i["kind"] == "restored_backup"]  # fmt: skip


def test_the_relay_task_resolves_a_restore_before_it_publishes(api, receiver, monkeypatch):
    from app import worker

    out = Published()
    monkeypatch.setattr(worker, "publish", out)
    aid = queue(api, prepared_application(api, receiver))
    restored()
    assert worker.relay_outbox() == 0 and out.sent == []
    assert attempt(aid).state == "failed_safe" and not held()
    newer = queue(api, prepared_application(api, receiver, url_suffix="?posting=2"))
    assert worker.relay_outbox() == 1 and out.sent == [("execute_attempt", newer)]


def test_a_pass_that_stops_half_way_is_finished_by_the_next(api, receiver, monkeypatch):
    aid = queue(api, prepared_application(api, receiver))
    restored()

    def fails():
        raise RuntimeError("stopped half way")

    monkeypatch.setattr(restore, "_pause_rules", fails)
    with pytest.raises(RuntimeError):
        restore.resolve()
    assert held()  # what was queued is ended, and the database is still held
    assert attempt(aid).state == "failed_safe" and svc.claim(uuid.UUID(aid), "w1") is None
    assert restore.status()["summary"]["ended"] == {"pending": 1}
    monkeypatch.undo()
    done = restore.resolve()
    assert done["ended"] == {"pending": 1} and done["resolved_at"]  # the first pass's, kept
    assert not held()
    assert restore.resolve() is None


def test_one_resolver_at_a_time(api, receiver):
    """A pass that finds another resolver at work does nothing and says so; the database stays
    held meanwhile, so nothing runs. The next pass resolves it."""
    from app.core.db import engine

    aid = queue(api, prepared_application(api, receiver))
    restored()
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": restore._LOCK})
        try:
            assert restore.resolve() == {"busy": True}
            assert held() and attempt(aid).state == "pending"
            assert svc.claim(uuid.UUID(aid), "w1") is None
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": restore._LOCK})
    assert restore.resolve()["ended"] == {"pending": 1} and not held()


def test_force_resolves_a_database_restored_another_way(api, receiver, capsys):
    """A restore that keeps the database (pg_restore --clean, a copy of its volume) keeps its
    oid too, so the stamp cannot tell; `restore-resolve --force` treats it as restored."""
    aid = queue(api, prepared_application(api, receiver))
    assert cli.main(["restore-resolve"]) == 0
    assert capsys.readouterr().out.strip() == "not held"
    assert cli.main(["restore-status"]) == 0
    assert json.loads(capsys.readouterr().out)["held"] is False
    assert cli.main(["restore-resolve", "--force"]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["ended"] == {"pending": 1} and attempt(aid).state == "failed_safe"
    assert cli.main(["restore-status"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["held"] is False and st["summary"] == done
    assert cli.main(["no-such-command"]) == 2


# --------------------------------------------------------------------------- a real worker


def test_a_worker_never_runs_what_a_restored_database_queued(api, receiver):
    """The message of an attempt the backup showed as queued is still in the broker when the
    restored database comes up. A real worker takes it while the database is held: the claim
    refuses it. Resolved, the attempt is over, and nothing reached the employer."""
    from app.worker import publish

    aid = queue(api, prepared_application(api, receiver))
    assert svc.relay_outbox(publish) == 1
    r = redis.Redis.from_url(get_settings().redis_url)
    assert queued(r) == {"celery": 0, "attempts": 1}
    restored()
    w = Worker(queues="attempts", concurrency=1)
    try:
        w.wait_log("not claimed: the database was restored", 60)
        assert attempt(aid).state == "pending" and claims(aid) == 0
        assert queued(r) == {"celery": 0, "attempts": 0}
        assert restore.resolve()["ended"] == {"pending": 1}
        assert svc.republish_waiting(publish) == 0
        time.sleep(2)
    finally:
        w.stop()
    assert attempt(aid).state == "failed_safe" and claims(aid) == 0
    nothing_reached_the_employer(receiver)
