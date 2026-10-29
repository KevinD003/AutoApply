"""notification reads

Revision ID: 7d2c4e9a1b60
Revises: 452ae3b5aec9
Create Date: 2026-10-29 19:30:00.000000

Priority C (D83). One row per notification you marked read, by its key (which names a record of
yours). Notifications themselves are derived, never stored. Deleted with the user. Downgrade
drops the table: every notification shows as unread again; nothing else changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d2c4e9a1b60"
down_revision: str | Sequence[str] | None = "452ae3b5aec9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=120), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_key", name="uq_notification_read"),
    )


def downgrade() -> None:
    op.drop_table("notification_reads")
