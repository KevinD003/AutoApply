"""providers and discovery

Revision ID: 8b41c0d7e2f5
Revises: 5d2e7a91c4b0
Create Date: 2026-10-21 18:00:00.000000

The user's explicit API authorizations (providers), discovered job records (discovery), and the
"discovery" job source. No existing row changes meaning.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b41c0d7e2f5"
down_revision: str | Sequence[str] | None = "5d2e7a91c4b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'discovery'")
    op.create_table(
        "api_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("origin", sa.String(length=300), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_api_authorizations_user_id"), "api_authorizations", ["user_id"], unique=False
    )
    op.create_table(
        "discovered_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("source_job_id", sa.String(length=200), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=False),
        sa.Column("source_facts", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("stale_reason", sa.String(length=100), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "source_job_id", name="uq_discovered_source"),
    )
    op.create_index(
        op.f("ix_discovered_jobs_user_id"), "discovered_jobs", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema. (The enum value 'discovery' cannot be removed in PostgreSQL; it is
    left in place and unused.)"""
    op.drop_index(op.f("ix_discovered_jobs_user_id"), table_name="discovered_jobs")
    op.drop_table("discovered_jobs")
    op.drop_index(op.f("ix_api_authorizations_user_id"), table_name="api_authorizations")
    op.drop_table("api_authorizations")
