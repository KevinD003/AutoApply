"""discovery provenance and merge fields

Revision ID: 955a3214d25a
Revises: 8b41c0d7e2f5
Create Date: 2026-10-21 16:58:55.506462

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "955a3214d25a"
down_revision: str | Sequence[str] | None = "8b41c0d7e2f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema. Existing rows get an empty change list (server default)."""
    op.add_column("discovered_jobs", sa.Column("link_basis", sa.String(length=40), nullable=True))
    op.add_column("discovered_jobs", sa.Column("filter_result", sa.JSON(), nullable=True))
    op.add_column(
        "discovered_jobs",
        sa.Column("changed_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "discovered_jobs", sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("discovered_jobs", sa.Column("raw_ref", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("discovered_jobs", "raw_ref")
    op.drop_column("discovered_jobs", "changed_at")
    op.drop_column("discovered_jobs", "changed_fields")
    op.drop_column("discovered_jobs", "filter_result")
    op.drop_column("discovered_jobs", "link_basis")
