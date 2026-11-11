"""D147: a database restored from a backup comes up held, and nothing it restored runs.

A restored database cannot know what happened after its backup was taken: an application it
shows as queued, or in progress, may have been sent since, and one it shows as approved may
have been queued and sent since. Since D146 a queued attempt is published again by itself, so
it would be sent a second time. The database therefore carries a stamp of its own identity
(`InstanceStamp`: the oid PostgreSQL gave the database the stamp was written in). A restore into
a new database, as the deployment guide's §7 does it (dropdb, createdb, pg_restore), keeps the
stamp and changes the oid. While the two differ the database is *held*:

  * no attempt is claimed (`service.claim`) and nothing is queued (`service.enqueue`);
  * the standing rule does nothing (`autoapply.service.tick`);
  * the relay's task first resolves the hold (`resolve`), within seconds of the scheduler
    starting, before it publishes anything.

Resolving it never runs anything. Every attempt still active is ended: one that was queued, or
taken before anything was entered, `failed_safe`; one that had entered data, `abandoned`; one
past the send gate, `unknown` (its application `submitted_unconfirmed`, as the sweeper does).
Every live approval is retired, so nothing is sent again on a decision made before the backup;
every account's standing rule is paused. Each account's feed says so (`notifications`). Only
then is the stamp made this database's. Each step is its own transaction and can be repeated: a
pass that stops half way leaves the database held, and the next pass finishes it.

What it cannot see: a restore that keeps the database (`pg_restore --clean` into it, a copy of
its files, a volume snapshot), and a backup taken before D147 (it has no stamp; its upgrade
stamps it). `resolve(force=True)` (the CLI's `restore-resolve --force`) treats the database as
restored whatever its stamp says. And no restore can show what was sent after its backup: the
owner checks that before approving or resuming anything.
"""

import copy
import logging

from sqlalchemy import or_, select, text, update
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
STAMP_ID = 1
_LOCK = 7_402_147  # one resolver at a time (a pg advisory lock held for all three steps)

ENDED_QUEUED = (
    "This server's database was restored from a backup taken while this application was "
    "queued. It may have been sent after that backup: NoEfforts cannot tell, so it ran nothing. "
    "Check with the employer before you approve it again."
)
ENDED_ENTERED = (
    "This server's database was restored from a backup taken while this application was being "
    "entered on the employer's page. What happened after that backup is not recorded here: "
    "NoEfforts will not run it again. Check with the employer."
)
ENDED_SENDING = (
    "This server's database was restored from a backup taken while this application was being "
    "sent. Its outcome is unknown, and it is never sent again automatically: check with the "
    "employer, then record what happened."
)


def _oid(db: Session) -> int:
    return db.scalar(text("SELECT oid::bigint FROM pg_database WHERE datname = current_database()"))


def held(db: Session) -> bool:
    """True while this database carries another database's stamp: it was restored and the
    restore is not resolved yet. No stamp at all is not held (a database stamps itself when its
    upgrade runs, and `resolve` stamps one that has none)."""
    row = db.execute(
        text(
            "SELECT s.db_oid, d.oid::bigint FROM instance_stamp s "
            "JOIN pg_database d ON d.datname = current_database() WHERE s.id = :id"
        ),
        {"id": STAMP_ID},
    ).first()
    return row is not None and row[0] != row[1]


def status() -> dict:
    """What the CLI prints: whether the database is held, and the last restore resolved."""
    with SessionLocal() as db:
        stamp = db.get(InstanceStamp, STAMP_ID)
        return {
            "held": held(db),
            "stamped": stamp is not None,
            "restored_at": stamp.restored_at.isoformat() if stamp and stamp.restored_at else None,
            "summary": stamp.restore_summary if stamp else None,
        }


def resolve(force: bool = False) -> dict | None:
    """Resolve a hold (see the module's docstring). Returns what resolving did; None when the
    database was not held (a database with no stamp is stamped); {"busy": True} when another
    resolver is at work (the database stays held meanwhile, so nothing runs). `force`: resolve
    it as a restore whatever its stamp says (the owner restored it another way)."""
    if not force:
        with SessionLocal() as db:
            if db.get(InstanceStamp, STAMP_ID) is not None and not held(db):
                return None  # this database's own stamp: the common case, every relay pass
    with engine.connect() as lock:  # one resolver at a time, for all three steps
        if not lock.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK}).scalar():
            return {"busy": True}
        try:
            return _resolve(force)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK})


def _resolve(force: bool) -> dict | None:
    with SessionLocal() as db:
        stamp = db.get(InstanceStamp, STAMP_ID)
        oid = _oid(db)
        if stamp is None and not force:
            db.add(InstanceStamp(id=STAMP_ID, db_oid=oid))
            db.commit()
            return None
        if stamp is not None and stamp.db_oid == oid and not force:
            return None
        if stamp is None:
            stamp = InstanceStamp(id=STAMP_ID, db_oid=-1)
            db.add(stamp)
        if force:
            stamp.db_oid = -1  # held from here until the last step, whatever happens between
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

    paused = _pause_rules()  # 2: each account's rule, in its own transaction; still held

    with SessionLocal() as db:
        stamp = db.get(InstanceStamp, STAMP_ID)
        summary = copy.deepcopy(stamp.restore_summary)
        summary["paused"] += paused
        summary["resolved_at"] = utcnow().isoformat()
        stamp.restore_summary = summary
        stamp.restored_at, stamp.db_oid, stamp.stamped_at = utcnow(), _oid(db), utcnow()
        db.commit()  # 3: the stamp is this database's: no longer held
    log.warning("restore resolved: %s", summary)
    return summary


def _end_active(db: Session) -> tuple[dict, int]:
    """End every attempt still active, under the cancel lock order (each attempt, then its
    application), never to run again; retire every live approval. Counts only."""
    from app.modules.applications.states import Actor, AppState
    from app.modules.audit.service import record
    from app.modules.execution import service as svc
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import PackageApproval

    ended: dict[str, int] = {}
    ids = db.scalars(select(ExecutionAttempt.id).where(ExecutionAttempt.state.in_(ACTIVE))).all()
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
            att.state, att.outcome_detail = S.unknown, ENDED_SENDING
            svc.close_checkpoints(db, att.id)
            if app.state in (AppState.submitting, AppState.needs_user_action):
                svc._app_to(db, app, AppState.submitted_unconfirmed, Actor.system, ENDED_SENDING)
        elif att.disclosure_started_at is not None:
            att.state, att.outcome_detail = S.abandoned, ENDED_ENTERED
            svc._app_to(db, app, AppState.needs_user_action, Actor.system, ENDED_ENTERED)
        else:  # queued, or taken before anything was entered
            att.state, att.outcome_detail = S.failed_safe, ENDED_QUEUED
            svc._claim_refused(db, app, ENDED_QUEUED)
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


def _pause_rules() -> int:
    """Pause every account's standing rule that is not paused: a restored database does not
    know what the rule applied to after the backup, so it could apply to the same job again.
    Each account in its own transaction (the rule's own lock order); how many were paused."""
    from app.modules.autoapply import service as auto
    from app.modules.identity.models import User

    n = 0
    with SessionLocal() as db:
        ids = db.scalars(select(User.id)).all()
    for uid in ids:
        with SessionLocal() as db:
            user = db.get(User, uid)
            if user is None or auto.paused(db, user):
                continue
            auto.set_paused(db, uid, True)
            db.commit()
            n += 1
    return n
