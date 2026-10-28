"""discovery run approvals

Revision ID: 4bc9c342d34c
Revises: e3a91c5d7b20
Create Date: 2026-10-28 00:29:10.608375

S7 (D55). One row per approval the owner records for a single live Freehire read: the exact
search, the page limit (1 to 5), the time window and the retention statement. `consumed_at` is
set when an import uses it, before its first request; a used approval is never used again. New
table only: no existing row changes. Downgrade drops the table (recorded approvals, used or not,
are lost; audit rows of their creation and use stay).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4bc9c342d34c"
down_revision: str | Sequence[str] | None = "e3a91c5d7b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_run_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(query)) > 0", name="ck_run_approval_query"),
        sa.CheckConstraint("length(trim(retention)) > 0", name="ck_run_approval_retention"),
        sa.CheckConstraint("max_pages BETWEEN 1 AND 5", name="ck_run_approval_pages"),
        sa.CheckConstraint("not_after > not_before", name="ck_run_approval_window"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discovery_run_approvals_user_id"),
        "discovery_run_approvals",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discovery_run_approvals_user_id"), table_name="discovery_run_approvals")
    op.drop_table("discovery_run_approvals")
