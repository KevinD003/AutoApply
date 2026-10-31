"""inbox reading

Revision ID: b7d2f4a91c05
Revises: a4c8e2d61f93
Create Date: 2026-10-31 16:00:00.000000

D101. `inbox_settings`: your choices for reading your own Gmail (verification codes, application
emails), off until you turn each on, and where the last read ended. `inbox_events`: one row per
email read, as its kind and what happened (a keyed reference, the arrival time, the sender's
domain, the application it names); never its text. Both are deleted with the user. Downgrade
drops both tables: reading stops and nothing else changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2f4a91c05"
down_revision: str | Sequence[str] | None = "a4c8e2d61f93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("codes_enabled", sa.Boolean(), nullable=False),
        sa.Column("tracking_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "inbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message_ref", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender_domain", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_ref", name="uq_inbox_message"),
    )
    op.create_index("ix_inbox_events_user_id", "inbox_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_inbox_events_user_id", table_name="inbox_events")
    op.drop_table("inbox_events")
    op.drop_table("inbox_settings")
