"""email tracking: applied_outcome on inbox_events (undo-after-newer guard)

Revision ID: d4e8f1a2b3c7
Revises: c3f1a7e5b921
Create Date: 2026-11-04 10:30:00.000000

Additive: `inbox_events.applied_outcome` records the outcome an accept/auto-apply actually wrote,
so undo can tell whether a newer update has since superseded this event (then undo refuses rather
than clobbering the newer state). An outcome value only (e.g. "interviewing"), never message
content. Null for events not yet applied, and for rows written before this revision. Still deleted
with the user.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8f1a2b3c7"
down_revision: str | Sequence[str] | None = "c3f1a7e5b921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inbox_events", sa.Column("applied_outcome", sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column("inbox_events", "applied_outcome")
