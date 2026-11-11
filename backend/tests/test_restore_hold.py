"""D147: a database restored from a backup comes up held, and nothing it restored runs.

A restore is made here by giving the database's stamp another database's identity, which is what
a restore leaves behind (the deployment guide's §7). `test_migrations.py` makes a real copy of a
migrated database and finds it held; the Compose smoke test (CI) restores a real dump. The
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


def stamps() -> list[tuple[int, int]]:
    with SessionLocal() as db:
        return [(r.db_oid, r.cluster_id) for r in db.scalars(select(InstanceStamp)).all()]


def identity() -> tuple[int, int]:
    with SessionLocal() as db:
        return restore._state(db)[:2]


def restored(onto_another_server: bool = False) -> None:
    """As a restore leaves the database: the stamp is another database's. Into a new database
    on this server, another oid; onto another server, another cluster, and the same oid (as two
    new clusters give their first database)."""
    restore.resolve()  # stamps the database (the per-test cleanup removes every row)
    with SessionLocal() as db:
        moved = (
            {"cluster_id": InstanceStamp.cluster_id + 1}
            if onto_another_server
            else {"db_oid": InstanceStamp.db_oid + 1}
        )
        db.execute(update(InstanceStamp).values(**moved))
        db.commit()


def held() -> bool:
    with SessionLocal() as db:
        return restore.held(db)


def attempt_app(aid: str) -> str:
    return str(attempt(aid).application_id)


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
        cluster = db.scalar(text("SELECT system_identifier FROM pg_control_system()"))
        assert restore.held(db) is False
    assert stamps() == [(own, cluster)]
    assert restore.resolve() is None  # its own stamp: nothing to do
    assert restore.status() == {"held": False, "stamped": True, "restored_at": None,
                                "summary": None}  # fmt: skip


def test_a_database_with_no_stamp_is_not_held(api, receiver):
    """A database restored from a backup made before D147 has no stamp until its upgrade
    stamps it; that cannot be told from a new database (D147 says so)."""
    aid = queue(api, prepared_application(api, receiver))
    assert stamps() == []
    assert not held()
    assert svc.claim(uuid.UUID(aid), "w1") == 1


def test_a_restore_onto_another_server_is_held_though_its_oid_is_the_same(api, receiver):
    """Every new cluster gives its first database the same oid (16384, measured on two), so a
    backup restored onto another server can have its old oid again: the cluster's identifier
    tells them apart. Resolved, the stamp is this server's."""
    aid = queue(api, prepared_application(api, receiver))
    restored(onto_another_server=True)
    ((oid, _),) = stamps()
    assert oid == identity()[0]  # the oid alone would not tell
    assert held() and svc.claim(uuid.UUID(aid), "w1") is None
    summary = restore.resolve()
    assert summary["ended"] == {"pending": 1}
    assert not held() and stamps() == [identity()]
    assert restore.resolve() is None
    nothing_reached_the_employer(receiver)


def test_a_stamp_the_new_server_wrote_first_does_not_hide_the_restore(api, receiver):
    """The new server may stamp the empty database before the backup's rows arrive (a backend
    that migrated it first, a scheduler left running): both stamps are then there. The
    backup's still holds it; resolving removes it and keeps this database's own."""
    aid = queue(api, prepared_application(api, receiver))
    restore.resolve()  # this database's own stamp, written first
    with SessionLocal() as db:  # then the backup's, loaded beside it
        oid, cluster = identity()
        db.add(InstanceStamp(db_oid=oid + 1, cluster_id=cluster))
        db.commit()
    assert len(stamps()) == 2
    assert held() and svc.claim(uuid.UUID(aid), "w1") is None
    assert restore.resolve()["ended"] == {"pending": 1}
    assert not held() and stamps() == [identity()]
    nothing_reached_the_employer(receiver)


# --------------------------------------------------------------------------- held


def test_a_restored_database_takes_nothing_and_queues_nothing(api, receiver):
    """Held, nothing is claimed, queued or approved."""
    aid = queue(api, prepared_application(api, receiver))
    other = prepared_application(api, receiver, url_suffix="?posting=2")
    unapproved = prepared_application(api, receiver, url_suffix="?posting=3", approve=False)
    restored()
    assert held()
    assert svc.claim(uuid.UUID(aid), "w1") is None  # whatever delivers its message
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert attempt(aid).state == "pending" and claims(aid) == 0
    r = api.post(f"/applications/{other}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "(reason: restored_backup_held)" in r.text, r.text
    assert app_state(other) != "queued"
    p = api.get(f"/applications/{unapproved}/package").json()["package"]
    r = api.post(f"/applications/{unapproved}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 409 and "(reason: restored_backup_held)" in r.text, r.text
    assert live_approvals(unapproved) == []
    nothing_reached_the_employer(receiver)


def test_the_standing_rule_does_nothing_while_held(api, receiver, monkeypatch):
    """The rule would act on this application, but not while the database is held: it approves
    and queues nothing. Resolving pauses it; resumed by you, it leaves to you every application
    that began before the restore (what happened to it after the backup is unknown)."""
    from tests.test_auto_apply import events, ready

    s = get_settings()
    monkeypatch.setattr(s, "auto_apply_enabled", True)
    monkeypatch.setattr(s, "auto_apply_daily_cap", 5)
    monkeypatch.setattr(s, "execution_test_rehearsal_rule_paths", ["greenhouse_live:*"])
    receiver.config(mode="normal")
    job, app_id = ready(api)
    restored()
    before = events(job)
    assert auto.tick() == 0
    assert events(job) == before  # it did nothing at all, not even a refused approval noted
    assert live_approvals(app_id) == [] and not attempts_of(app_id)
    assert restore.resolve() is not None
    assert auto.tick() == 0  # the restore paused it
    assert api.put("/auto-apply", json={"paused": False}).status_code == 200
    assert auto.tick() == 0  # resumed by you: it leaves this one to you
    assert live_approvals(app_id) == [] and not attempts_of(app_id)
    assert events(job)[-1] == ("skipped", "restored_from_backup")


def attempts_of(app_id: str) -> list[ExecutionAttempt]:
    with SessionLocal() as db:
        return db.scalars(
            select(ExecutionAttempt).where(ExecutionAttempt.application_id == uuid.UUID(app_id))
        ).all()


# --------------------------------------------------------------------------- resolving


def test_resolving_ends_what_was_queued_and_never_runs_it(api, receiver):
    """It may have run, and been sent, after the backup: an unknown outcome, quarantined for
    you to reconcile. An application approved but not queued at the backup keeps no approval
    either: it may have been queued and sent after the backup."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)  # its message not published yet
    approved = prepared_application(api, receiver, url_suffix="?posting=2")
    restored()
    done = restore.resolve()
    assert done["ended"] == {"pending": 1} and done["approvals"] == 2 and done["resolved_at"]
    att = attempt(aid)
    assert (att.state, att.outcome_detail) == ("unknown", restore.ENDED["queued"])
    assert app_state(app_id) == "submitted_unconfirmed"
    assert retired_reasons(app_id) == [RESTORED] and live_approvals(app_id) == []
    assert retired_reasons(approved) == [RESTORED] and live_approvals(approved) == []
    assert app_state(approved) == "awaiting_approval"
    (m,) = msgs(aid)
    assert m.dispatched_at is not None and m.last_error == "restored"  # never published
    with SessionLocal() as db:
        audit = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "package.approval_retired")
        ).all()
    assert [a.get("reason_code") for a in audit] == ["restored_from_backup"] * 2
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
    "was,app_before,entered,phase",
    [
        ("claimed", "running", False, "queued"),
        ("claimed", "running", True, "entering"),
        ("sending", "submitting", True, "sending"),
        ("awaiting_code", "needs_user_action", True, "sending"),
    ],
)
def test_resolving_quarantines_each_state_in_progress(api, receiver, was, app_before, entered,
                                                      phase):  # fmt: skip
    """Whatever the backup shows in progress may have gone on, and been sent, after the backup.
    Each ends with an unknown outcome and its application `submitted_unconfirmed`, never put
    back in the queue and never sent again: you reconcile it."""
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
    assert (att.state, att.outcome_detail, att.lease_owner, att.cancel_requested) == (
        "unknown", restore.ENDED[phase], None, True)  # fmt: skip
    assert app_state(app_id) == "submitted_unconfirmed"
    assert live_approvals(app_id) == []
    assert svc.claim(uuid.UUID(aid), "w1") is None
    nothing_reached_the_employer(receiver)


@pytest.mark.parametrize(
    "was,app_before,entered,state,app_after",
    [
        ("pending", "queued", False, "failed_safe", "awaiting_approval"),
        ("claimed", "running", True, "abandoned", "needs_user_action"),
    ],
)
def test_a_rehearsal_in_progress_is_ended_as_the_sweeper_would(
    api, receiver, was, app_before, entered, state, app_after
):
    """A rehearsal never submits, so nothing it was doing can have been sent: it is ended as
    the sweeper ends one whose worker is gone, never run again."""
    from app.core.db import utcnow
    from app.modules.preparation.models import ApprovalScope

    app_id = prepared_application(api, receiver, scope="disclose_only")
    aid = queue(api, app_id)
    with SessionLocal() as db:
        scope = db.get(PackageApproval, attempt(aid).approval_id).scope
    assert scope == ApprovalScope.disclose_only
    if was != "pending":
        set_attempt(aid, state=was, generation=1, lease_owner="gone", lease_expires_at=utcnow(),
                    disclosure_started_at=utcnow() if entered else None)  # fmt: skip
    set_app(app_id, app_before)
    restored()
    assert restore.resolve()["ended"] == {was: 1}
    att = attempt(aid)
    assert (att.state, att.outcome_detail) == (state, restore.REHEARSAL_ENDED)
    assert app_state(app_id) == app_after
    assert svc.claim(uuid.UUID(aid), "w1") is None
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
    with SessionLocal() as db:
        paused = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "auto_apply.paused")
        ).all()
    assert [m.get("reason_code") for m in paused] == ["restored_from_backup"]
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
    assert attempt(aid).state == "unknown" and not held()
    newer = queue(api, prepared_application(api, receiver, url_suffix="?posting=2"))
    assert worker.relay_outbox() == 1 and out.sent == [("execute_attempt", newer)]


def test_the_relay_command_resolves_a_restore_first(api, receiver, monkeypatch, capsys):
    """`cli relay` does what the periodic task does: the restore first, then the messages."""
    from app import worker

    out = Published()
    monkeypatch.setattr(worker, "publish", out)
    aid = queue(api, prepared_application(api, receiver))
    restored()
    assert cli.main(["relay"]) == 0
    assert capsys.readouterr().out.strip() == "0" and out.sent == []
    assert attempt(aid).state == "unknown" and not held()


def test_a_pass_that_stops_half_way_is_finished_by_the_next(api, other_api, receiver,
                                                             monkeypatch):  # fmt: skip
    """A pass that stops after the first account's rule was paused: the database is still held,
    what was queued is ended, and the next pass finishes, keeping every count."""
    aid = queue(api, prepared_application(api, receiver))
    with SessionLocal() as db:
        for a in (api, other_api):
            db.add(AutoApplyPrefs(user_id=uuid.UUID(a.get("/auth/me").json()["user_id"]),
                                  paused=False))  # fmt: skip
        db.commit()
    restored()
    real, calls = auto.set_paused, []

    def second_fails(db, user_id, value, reason_code=None):
        calls.append(user_id)
        if len(calls) == 2:
            raise RuntimeError("stopped half way")
        return real(db, user_id, value, reason_code=reason_code)

    monkeypatch.setattr(auto, "set_paused", second_fails)
    with pytest.raises(RuntimeError):
        restore.resolve()
    assert held()  # what was queued is ended, and the database is still held
    assert attempt(aid).state == "unknown" and svc.claim(uuid.UUID(aid), "w1") is None
    summary = restore.status()["summary"]
    assert summary["ended"] == {"pending": 1} and summary["paused"] == 1
    monkeypatch.undo()
    done = restore.resolve()
    assert done["ended"] == {"pending": 1} and done["paused"] == 2 and done["resolved_at"]
    assert not held()
    assert restore.resolve() is None


def test_a_resolver_that_finds_it_resolved_under_the_lock_does_nothing(api, receiver):
    """A pass that saw the hold just before another finished: under the lock it finds the
    database resolved, and leaves alone what was queued since."""
    restored()
    assert restore.resolve()["resolved_at"]
    aid = queue(api, prepared_application(api, receiver))
    assert restore._resolve(False) is None
    assert attempt(aid).state == "pending" and live_approvals(attempt_app(aid))


def test_one_resolver_at_a_time(api, receiver, monkeypatch):
    """A pass that finds another resolver at work does nothing and says so; the database stays
    held meanwhile, so nothing runs, and the relay's task publishes nothing. The next pass
    resolves it."""
    from app import worker
    from app.core.db import engine

    out = Published()
    monkeypatch.setattr(worker, "publish", out)
    aid = queue(api, prepared_application(api, receiver))  # its message not published yet
    restored()
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": restore._LOCK})
        try:
            assert restore.resolve() == {"busy": True}
            assert worker.relay_outbox() == 0 and out.sent == []
            assert held() and attempt(aid).state == "pending"
            assert svc.claim(uuid.UUID(aid), "w1") is None
            assert cli.main(["restore-resolve"]) == 1  # nothing resolved: try again
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": restore._LOCK})
    assert restore.resolve()["ended"] == {"pending": 1} and not held()


def test_force_resolves_a_database_restored_another_way(api, receiver, capsys):
    """A restore into the same database (pg_restore --clean) or a copy of the server's files
    keeps its oid and its cluster too, so the stamp cannot tell; `restore-resolve --force`
    treats it as restored."""
    aid = queue(api, prepared_application(api, receiver))
    assert cli.main(["restore-resolve"]) == 0
    assert capsys.readouterr().out.strip() == "not held"
    assert cli.main(["restore-status"]) == 0
    assert json.loads(capsys.readouterr().out)["held"] is False
    assert cli.main(["restore-resolve", "--force"]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["ended"] == {"pending": 1} and attempt(aid).state == "unknown"
    assert cli.main(["restore-status"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["held"] is False and st["summary"] == done
    assert stamps() == [identity()]
    assert cli.main(["no-such-command"]) == 2


def test_force_holds_the_database_before_anything_else(api, receiver, monkeypatch):
    """`--force` commits its hold first: a pass that stops before ending anything leaves the
    database held, so nothing is taken meanwhile; the next pass resolves it."""
    aid = queue(api, prepared_application(api, receiver))

    def fails(db):
        raise RuntimeError("stopped before step 1 committed")

    monkeypatch.setattr(restore, "_end_active", fails)
    with pytest.raises(RuntimeError):
        restore.resolve(force=True)
    assert held() and restore.FORCED in stamps()
    assert svc.claim(uuid.UUID(aid), "w1") is None and attempt(aid).state == "pending"
    monkeypatch.undo()
    assert restore.resolve()["ended"] == {"pending": 1}
    assert not held() and stamps() == [identity()]


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
    assert attempt(aid).state == "unknown" and claims(aid) == 0
    nothing_reached_the_employer(receiver)
