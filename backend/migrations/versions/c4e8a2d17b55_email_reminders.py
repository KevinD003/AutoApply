"""email reminders

Revision ID: c4e8a2d17b55
Revises: b6d41f8e2a93
Create Date: 2026-10-30 16:00:00.000000

D94. `email_settings`: one row per account that set an email address for reminders to itself
(off until verified and turned on). `email_deliveries`: each email NoEfforts tried to send to
that address (a code or a daily digest) and what happened; never its content. Both are deleted
with the user. Downgrade drops both: reminders stop and their history is lost; nothing else
changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a2d17b55"
down_revision: str | Sequence[str] | None = "b6d41f8e2a93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(length=254), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_digest", sa.String(length=64), nullable=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_attempts", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("attention", sa.Boolean(), nullable=False),
        sa.Column("follow_ups", sa.Boolean(), nullable=False),
        sa.Column("digest_hour_utc", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("recipient_ref", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_keys", sa.JSON(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("outcome_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_email_delivery_dedupe"),
    )
    op.create_index("ix_email_deliveries_user_id", "email_deliveries", ["user_id"])
    op.create_index("ix_email_deliveries_status", "email_deliveries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_deliveries_status", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_user_id", table_name="email_deliveries")
    op.drop_table("email_deliveries")
    op.drop_table("email_settings")
