"""audit reference v2 repair

Revision ID: 7a1e4c2b9d30
Revises: c303eee5a3c9
Create Date: 2026-10-21 23:20:00.000000

Data only: legacy unkeyed audit references (`ref:` + 12 hex characters) are enumerable, so
every stored `audit_events.meta` is passed through the current sanitizer again
(app/modules/audit/repair.py, repair version 2). A legacy reference cannot be converted (its
source identifier is not stored) and becomes "[omitted]"; a raw `field` value still present
becomes a keyed `ref:v2:` reference scoped to the row's user. No schema change, no other column
or table. Irreversible by design: the downgrade restores nothing. Needs NOEFFORTS_AUDIT_REF_KEY.
"""

import logging
from collections.abc import Sequence

from alembic import context, op

from app.modules.audit.repair import REPAIR_VERSION, repair_meta
from app.modules.audit.service import check_ref_key

# revision identifiers, used by Alembic.
revision: str = "7a1e4c2b9d30"
down_revision: str | Sequence[str] | None = "c303eee5a3c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Replace legacy references; log aggregate counts only."""
    if context.is_offline_mode():
        raise RuntimeError("The audit reference repair reads rows; run this migration online.")
    check_ref_key()  # a missing key fails here, before any row is read
    scanned, changed = repair_meta(op.get_bind())
    log.info(
        "audit reference repair v%d: %d row(s) scanned, %d changed",
        REPAIR_VERSION,
        scanned,
        changed,
    )


def downgrade() -> None:
    """Nothing to undo: removed references are gone and are never restored."""
