"""One-way privacy repair of audit metadata stored before write-time sanitizing existed.

Every `audit_events.meta` object is passed through `service.sanitize`, the function applied to
every new write, and rewritten only when the result differs. Nothing else is read or written:
no other column and no other table. The repair is irreversible (removed values are not kept
anywhere) and idempotent (a second run changes no row).

It reports aggregate counts only. A failure is re-raised as `AuditRepairError` naming the error
type, never its message or the row's content, with no exception chained to it."""

import sqlalchemy as sa

from app.modules.audit.service import sanitize

REPAIR_VERSION = 1
BATCH = 500

_audit = sa.table("audit_events", sa.column("id", sa.Uuid), sa.column("meta", sa.JSON))


class AuditRepairError(RuntimeError):
    pass


def _repaired(meta: object) -> object:
    if meta is None:
        return None  # nothing stored, nothing to remove
    return sanitize(meta) if isinstance(meta, dict) else {}


def repair_meta(conn: sa.Connection, batch: int = BATCH) -> tuple[int, int]:
    """(rows scanned, rows changed). Runs inside the caller's transaction."""
    scanned = changed = 0
    failure = None
    try:
        last = None
        while True:
            q = sa.select(_audit.c.id, _audit.c.meta).order_by(_audit.c.id).limit(batch)
            rows = conn.execute(q if last is None else q.where(_audit.c.id > last)).all()
            for row_id, meta in rows:
                scanned += 1
                new = _repaired(meta)
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
