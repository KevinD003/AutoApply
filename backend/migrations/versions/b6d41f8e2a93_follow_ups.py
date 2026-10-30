"""follow ups

Revision ID: b6d41f8e2a93
Revises: 9e1f3a7c2d84
Create Date: 2026-10-30 12:00:00.000000

D92. One row per application you acted on about following up: the day you said you followed
up, a day you chose to be reminded on, and whether you stopped the reminders. When a follow-up
is due is derived, never stored. Deleted with the user and with the application. Downgrade drops
the table: those choices are lost and every follow-up falls back to its derived day.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d41f8e2a93"
down_revision: str | Sequence[str] | None = "9e1f3a7c2d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("followed_up_on", sa.Date(), nullable=True),
        sa.Column("remind_on", sa.Date(), nullable=True),
        sa.Column("stopped", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "application_id", name="uq_follow_up"),
    )


def downgrade() -> None:
    op.drop_table("follow_ups")
