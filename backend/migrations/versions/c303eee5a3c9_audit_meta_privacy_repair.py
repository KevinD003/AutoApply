"""audit meta privacy repair

Revision ID: c303eee5a3c9
Revises: 955a3214d25a
Create Date: 2026-10-21 21:23:24.795788

Data only: rewrites `audit_events.meta` of rows stored before write-time sanitizing
(app/modules/audit/repair.py, repair version 1). No schema change, no other column or table.
Irreversible by design: the downgrade restores nothing. A later change to the sanitizer that
should reach stored rows needs a new repair revision (version 2: 7a1e4c2b9d30). This revision
runs the current repair function, so on a database that has not reached it yet it already
applies the version 2 rules, and 7a1e4c2b9d30 then changes nothing.
"""

import logging
from collections.abc import Sequence

from alembic import context, op

from app.modules.audit.repair import repair_meta

# revision identifiers, used by Alembic.
revision: str = "c303eee5a3c9"
down_revision: str | Sequence[str] | None = "955a3214d25a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Sanitize every stored audit metadata object; log aggregate counts only."""
    if context.is_offline_mode():
        raise RuntimeError("The audit metadata repair reads rows; run this migration online.")
    scanned, changed = repair_meta(op.get_bind())
    log.info("audit metadata repair v1: %d row(s) scanned, %d changed", scanned, changed)


def downgrade() -> None:
    """Nothing to undo: removed values are gone and are never restored."""
