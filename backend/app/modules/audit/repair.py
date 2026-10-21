"""One-way privacy repair of audit metadata stored before the current write-time rules.

Every `audit_events.meta` object is passed through `service.sanitize`, the function applied to
every new write (scoped by the row's own `user_id`), and rewritten only when the result
differs. Only `audit_events.id`, `user_id` and `meta` are read and only `meta` is written; no
other table is touched. The repair is irreversible (removed values are not kept anywhere) and
idempotent (a second run changes no row).

Version 1 (migration c303eee5a3c9) removed raw values stored before sanitizing existed.
Version 2 (migration 7a1e4c2b9d30) removes legacy unkeyed references: their source identifier
is no longer stored anywhere in the audit row, so they cannot be converted and become
"[omitted]" (a constant that correlates nothing). Raw `field` values still present are
converted to keyed references. Both migrations run this same function.

It reports aggregate counts only. A failure is re-raised as `AuditRepairError` naming the error
type, never its message or the row's content, with no exception chained to it."""

import sqlalchemy as sa

from app.modules.audit.service import sanitize

REPAIR_VERSION = 2
BATCH = 500

_audit = sa.table(
    "audit_events",
    sa.column("id", sa.Uuid),
    sa.column("user_id", sa.Uuid),
    sa.column("meta", sa.JSON),
)


class AuditRepairError(RuntimeError):
    pass


def _repaired(meta: object, user_id: object) -> object:
    if meta is None:
        return None  # nothing stored, nothing to remove
    return sanitize(meta, scope=user_id) if isinstance(meta, dict) else {}


def repair_meta(conn: sa.Connection, batch: int = BATCH) -> tuple[int, int]:
    """(rows scanned, rows changed). Runs inside the caller's transaction."""
    scanned = changed = 0
    failure = None
    try:
        last = None
        while True:
            q = sa.select(_audit.c.id, _audit.c.user_id, _audit.c.meta)
            q = q.order_by(_audit.c.id).limit(batch)
            rows = conn.execute(q if last is None else q.where(_audit.c.id > last)).all()
            for row_id, user_id, meta in rows:
                scanned += 1
                new = _repaired(meta, user_id)
                if new != meta:
                    conn.execute(sa.update(_audit).where(_audit.c.id == row_id).values(meta=new))
                    changed += 1
            if len(rows) < batch:
                break
            last = rows[-1][0]
    except Exception as e:  # noqa: BLE001 - re-raised below without its message or context
        failure = type(e).__name__
    if failure:
        raise AuditRepairError(f"audit metadata repair failed after {scanned} row(s) ({failure})")
    return scanned, changed
