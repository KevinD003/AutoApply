"""drafting consents and usage

Revision ID: 452ae3b5aec9
Revises: 60e18e9115c8
Create Date: 2026-10-29 02:47:10.474478

L4 (D74). Two new tables, empty on upgrade: a user's agreement to the exact consent text for
an external drafting provider, and the ledger of requests to it (worst case reserved before a
request is sent, then the reported cost; numbers and codes only). Downgrade drops both.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "452ae3b5aec9"
down_revision: str | Sequence[str] | None = "60e18e9115c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drafting_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider"),
    )
    op.create_index(
        op.f("ix_drafting_consents_user_id"), "drafting_consents", ["user_id"], unique=False
    )
    op.create_table(
        "drafting_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.Column("reserved_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_drafting_usage_day"), "drafting_usage", ["day"], unique=False)
    op.create_index(op.f("ix_drafting_usage_user_id"), "drafting_usage", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_drafting_usage_user_id"), table_name="drafting_usage")
    op.drop_index(op.f("ix_drafting_usage_day"), table_name="drafting_usage")
    op.drop_table("drafting_usage")
    op.drop_index(op.f("ix_drafting_consents_user_id"), table_name="drafting_consents")
    op.drop_table("drafting_consents")
