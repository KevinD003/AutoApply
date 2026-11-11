"""D147: a database restored from a backup comes up held, and nothing it restored runs.

A restored database cannot know what happened after its backup was taken: an application it
shows as queued, or in progress, may have been sent since, and one it shows as approved may
have been queued and sent since. Since D146 a queued attempt is published again by itself, so
it would be sent a second time. The database therefore carries stamps of identity
(`InstanceStamp`, keyed by the oid PostgreSQL gave the database a stamp was written in and the
system identifier of its server's cluster). A restore brings back the backup's stamp: into a new
database on the same server, as the deployment guide's §7 does it (dropdb, createdb,
pg_restore), with another oid; onto another server, with another cluster (where the oid may
repeat). A stamp the new server writes for itself before the backup's arrives (a scheduler left
running, a backend that migrated the empty database first) does not hide it: while any stamp
names another database, the database is *held*:

  * no attempt is claimed (`service.claim`), nothing is queued (`service.enqueue`) or approved
    (`package.approve`);
  * the standing rule does nothing (`autoapply.service.tick`);
  * the relay's task first resolves the hold (`resolve`), within seconds of the scheduler
    starting, before it publishes anything; while another resolver is at work, it publishes
    nothing.

Resolving it never runs anything. Every attempt still active is ended, and what became of its
application after the backup is unknown: it may have run and been sent since (after a rehearsal,
by the submission that followed it). So it ends `unknown` and its application
`submitted_unconfirmed`, quarantined as an unknown outcome after the final click is, for the
owner to reconcile. Until then the sweeper does nothing, and cancelling, revoking and pausing do
not end what the backup shows in progress (each would record that nothing was sent). Every live
approval is retired,
so nothing is sent again on a decision made before the backup; every account's standing rule is
paused, and it leaves every application made before the restore to its owner
(`autoapply.service`). Each account's feed says so (`notifications`). Only then are the stamps
of other databases removed. Each step is its own transaction and can be repeated: a pass that
stops half way leaves the database held, and the next pass finishes it.

What it cannot see: a restore into the same database (`pg_restore --clean` into it), a copy of
the server's own files (its volume, a snapshot, a physical backup, a promoted replica, a cloned
server image: the cluster's identifier and the oid are copied too), and a backup taken before
D147 (it has no stamp; its upgrade stamps it). `resolve(force=True)` (the CLI's
`restore-resolve --force`) treats the database as restored whatever its stamps say: it holds the
database at once, then resolves. And no restore can show what was sent after its backup: the
owner checks that before approving or resuming anything.
"""

import copy
import logging
from datetime import datetime

from sqlalchemy import delete, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine, utcnow
from app.modules.execution.models import (
    ACTIVE,
    AttemptState,
    ExecutionAttempt,
    InstanceStamp,
    OutboxMessage,
)

log = logging.getLogger("noefforts.execution.restore")
S = AttemptState
FORCED = (-1, -1)  # the identity of no database: `--force` holds the database with it
_LOCK = 7_402_147  # one resolver at a time (a pg advisory lock held for all three steps)

# This database's identity, and whether any stamp names another (held) or this one (own).
_STATE = text(
    "SELECT d.oid::bigint, c.system_identifier, "
    "EXISTS (SELECT 1 FROM instance_stamp s WHERE (s.db_oid, s.cluster_id) "
    "<> (d.oid::bigint, c.system_identifier)), "
    "EXISTS (SELECT 1 FROM instance_stamp s WHERE (s.db_oid, s.cluster_id) "
    "= (d.oid::bigint, c.system_identifier)) "
    "FROM pg_database d, pg_control_system() c WHERE d.datname = current_database()"
)
_HELD = text(
    "SELECT EXISTS (SELECT 1 FROM instance_stamp s, pg_database d, pg_control_system() c "
    "WHERE d.datname = current_database() "
    "AND (s.db_oid, s.cluster_id) <> (d.oid::bigint, c.system_identifier))"
)
_RESTORED_AT = text(
    "SELECT s.restored_at FROM instance_stamp s, pg_database d, pg_control_system() c "
    "WHERE d.datname = current_database() "
    "AND s.db_oid = d.oid::bigint AND s.cluster_id = c.system_identifier"
)

_WHEN = {
    "queued": "while this application was queued",
    "started": "while this application was being started, before anything was entered",
    "entering": "while this application was being entered on the employer's page",
    "sending": "while this application was being sent",
}
# The feed adds what to do (notifications._UNKNOWN_NOTE): check, then record what happened.
ENDED = {
    phase: "This server's database was restored from a backup taken "
    + when
    + ". It may have been sent after that backup: NoEfforts cannot tell."
    for phase, when in _WHEN.items()
}
# The application states an attempt still active can leave its application in, and the
# system's moves from them for a restore (applications.states).
_QUARANTINABLE = ("queued", "running", "submitting", "needs_user_action")


def _state(db: Session) -> tuple[int, int, bool, bool]:
    oid, cluster, is_held, own = db.execute(_STATE).one()
    return oid, cluster, bool(is_held), bool(own)


def held(db: Session) -> bool:
    """True while any stamp names another database: it was restored (or `--force`d) and the
    restore is not resolved yet. No stamp at all is not held (a database stamps itself when its
    upgrade runs, and `resolve` stamps one that has none)."""
    return bool(db.scalar(_HELD))


def restored_at(db: Session) -> datetime | None:
    """When the last restore of this database was resolved (its own stamp), or None."""
    return db.scalar(_RESTORED_AT)


def _own(db: Session, oid: int, cluster: int) -> InstanceStamp | None:
    return db.get(InstanceStamp, (oid, cluster))


def _stamp_own(db: Session, oid: int, cluster: int) -> None:
    db.execute(
        insert(InstanceStamp)
        .values(db_oid=oid, cluster_id=cluster, stamped_at=utcnow())
        .on_conflict_do_nothing()
    )


def status() -> dict:
    """What the CLI prints: whether the database is held, and the last restore resolved."""
    with SessionLocal() as db:
        oid, cluster, is_held, _ = _state(db)
        own = _own(db, oid, cluster)
        return {
            "held": is_held,
            "stamped": own is not None,
            "restored_at": own.restored_at.isoformat() if own and own.restored_at else None,
            "summary": own.restore_summary if own else None,
        }


def resolve(force: bool = False) -> dict | None:
    """Resolve a hold (see the module's docstring). Returns what resolving did; None when the
    database was not held (a database with no stamp of its own is stamped); {"busy": True}
    when another resolver is at work (the database stays held meanwhile, so nothing runs).
    `force`: resolve it as a restore whatever its stamps say (the owner restored it another
    way); the hold is committed before anything else, so nothing is taken meanwhile."""
    if not force:
        with SessionLocal() as db:
            oid, cluster, is_held, own = _state(db)
            if not is_held:  # the common case, every relay pass
                if not own:
                    _stamp_own(db, oid, cluster)
                    db.commit()
                return None
    with engine.connect() as lock:  # one resolver at a time, for all three steps
        if not lock.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK}).scalar():
            return {"busy": True}
        try:
            return _resolve(force)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK})


def _resolve(force: bool) -> dict | None:
    with SessionLocal() as db:
        if force:  # held from here, whatever happens next: the stamp of no database
            db.execute(
                insert(InstanceStamp)
                .values(db_oid=FORCED[0], cluster_id=FORCED[1], stamped_at=utcnow())
                .on_conflict_do_nothing()
            )
            db.commit()
        oid, cluster, is_held, own = _state(db)  # again, under the lock
        if not is_held:  # resolved meanwhile by another pass, or never held
            if not own:
                _stamp_own(db, oid, cluster)
                db.commit()
            return None
        _stamp_own(db, oid, cluster)
        stamp = _own(db, oid, cluster)
        summary = copy.deepcopy(stamp.restore_summary or {})
        if not summary or summary.get("resolved_at"):  # a new restore (or the first)
            summary = {"found_at": utcnow().isoformat(), "ended": {}, "approvals": 0, "paused": 0}
            log.warning("database restored from a backup: holding everything it restored")
        ended, approvals = _end_active(db)
        for state, n in ended.items():
            summary["ended"][state] = summary["ended"].get(state, 0) + n
        summary["approvals"] += approvals
        stamp.restore_summary = summary
        db.commit()  # 1: what was active is ended, every live approval retired; still held

    _pause_rules(oid, cluster)  # 2: each account's rule, in its own transaction; still held

    with SessionLocal() as db:
        stamp = _own(db, oid, cluster)
        summary = copy.deepcopy(stamp.restore_summary)
        summary["resolved_at"] = utcnow().isoformat()
        stamp.restore_summary = summary
        stamp.restored_at = stamp.stamped_at = utcnow()
        db.execute(
            delete(InstanceStamp).where(
                tuple_(InstanceStamp.db_oid, InstanceStamp.cluster_id) != (oid, cluster)
            )
        )
        db.commit()  # 3: only this database's own stamp is left: no longer held
    log.warning("restore resolved: %s", summary)
    return summary


def _end_active(db: Session) -> tuple[dict, int]:
    """End every attempt still active, under the cancel lock order (each attempt, then its
    application; attempts in order of their ids), never to run again; retire every live
    approval. Counts only."""
    from app.modules.applications.states import Actor, AppState
    from app.modules.audit.service import record
    from app.modules.execution import service as svc
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import PackageApproval

    ended: dict[str, int] = {}
    ids = db.scalars(
        select(ExecutionAttempt.id)
        .where(ExecutionAttempt.state.in_(ACTIVE))
        .order_by(ExecutionAttempt.id)
    ).all()
    for att_id in ids:
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.id == att_id).with_for_update()
        )
        app = pk.lock_application(db, att.application_id)
        db.refresh(app)
        was = att.state
        if was not in ACTIVE:
            continue  # it finished while this waited
        att.lease_owner, att.lease_expires_at, att.finished_at = None, None, utcnow()
        att.cancel_requested = True  # a worker still holding it stops at its next step
        if was in (S.sending, S.awaiting_code):
            phase = "sending"
        elif att.disclosure_started_at is not None:
            phase = "entering"
        else:
            phase = "started" if was == S.claimed else "queued"
        # It, or what followed it (a submission after a rehearsal), may have been sent after the
        # backup: an unknown outcome, whatever it was doing.
        att.state, att.outcome_detail = S.unknown, ENDED[phase]
        svc.close_checkpoints(db, att.id)
        if app.state in _QUARANTINABLE:
            svc._app_to(db, app, AppState.submitted_unconfirmed, Actor.system, ENDED[phase])
        else:
            log.warning("restore: an attempt's application was left in its state (%s)",
                        app.state)  # fmt: skip
        svc.event(db, att, "restore_ended", was=str(was))
        ended[str(was)] = ended.get(str(was), 0) + 1
    if ids:  # what the relay has not published yet is never published: nothing is to run
        db.execute(
            update(OutboxMessage)
            .where(OutboxMessage.attempt_id.in_(ids), OutboxMessage.dispatched_at.is_(None))
            .values(dispatched_at=utcnow(), last_error="restored")
        )
    now, apps = utcnow(), {}
    live = db.scalars(
        select(PackageApproval)
        .where(
            PackageApproval.invalidated_at.is_(None),
            or_(PackageApproval.expires_at.is_(None), PackageApproval.expires_at > now),
        )
        .order_by(PackageApproval.id)
        .with_for_update()
    ).all()
    for appr in live:
        appr.invalidated_at = now
        appr.invalidation_reason = svc.RETIRED["restored_from_backup"]
        apps[appr.application_id] = appr.user_id
    for app_id, user_id in apps.items():  # written once per application, as other retirements
        record(db, user_id, "package.approval_retired", "application", app_id,
               reason_code="restored_from_backup")  # fmt: skip
    return ended, len(live)


def _pause_rules(oid: int, cluster: int) -> None:
    """Pause every account's standing rule that is not paused: a restored database does not
    know what the rule applied to after the backup, so it could apply to the same job again.
    Each account in its own transaction (the rule's own lock order), its count with it, so a
    pass that stops half way keeps the count of those it paused."""
    from app.modules.autoapply import service as auto
    from app.modules.identity.models import User

    with SessionLocal() as db:
        ids = db.scalars(select(User.id).order_by(User.id)).all()
    for uid in ids:
        with SessionLocal() as db:
            user = db.get(User, uid)
            if user is None or auto.paused(db, user):
                continue
            auto.set_paused(db, uid, True, reason_code="restored_from_backup")
            stamp = _own(db, oid, cluster)
            summary = copy.deepcopy(stamp.restore_summary)
            summary["paused"] += 1
            stamp.restore_summary = summary
            db.commit()
