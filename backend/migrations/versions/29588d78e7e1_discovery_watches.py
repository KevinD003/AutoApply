"""discovery watches

Revision ID: 29588d78e7e1
Revises: 4bc9c342d34c
Create Date: 2026-10-28 02:10:00.000000

S8 (D56). One row per watched Freehire search: the owner's standing approval (the exact search,
an interval of 60 s to a day, at most 90 days, a retention statement) and its bookkeeping (next
check, last outcome, failures in a row, the pause reason, found postings, requests per UTC day
for the daily cap). New table only. Discovered records deleted by their owner keep their row
with status "dismissed" and no content (a value of an existing text column; no schema change).
Downgrade drops the table: watches are lost; audit rows stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29588d78e7e1"
down_revision: str | Sequence[str] | None = "4bc9c342d34c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_watches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_reason", sa.String(length=40), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(length=40), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("found_total", sa.Integer(), nullable=False),
        sa.Column("budget_day", sa.Date(), nullable=True),
        sa.Column("requests_on_day", sa.Integer(), nullable=False),
        sa.CheckConstraint("not_after <= not_before + interval '90 days'", name="ck_watch_length"),
        sa.CheckConstraint("failures >= 0 AND requests_on_day >= 0", name="ck_watch_counts"),
        sa.CheckConstraint("interval_seconds BETWEEN 60 AND 86400", name="ck_watch_interval"),
        sa.CheckConstraint("length(trim(query)) > 0", name="ck_watch_query"),
        sa.CheckConstraint("length(trim(retention)) > 0", name="ck_watch_retention"),
        sa.CheckConstraint("not_after > not_before", name="ck_watch_window"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discovery_watches_next_check_at"),
        "discovery_watches",
        ["next_check_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_watches_user_id"), "discovery_watches", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discovery_watches_user_id"), table_name="discovery_watches")
    op.drop_index(op.f("ix_discovery_watches_next_check_at"), table_name="discovery_watches")
    op.drop_table("discovery_watches")
