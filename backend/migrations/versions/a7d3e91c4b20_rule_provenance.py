"""rule provenance: approvals given and attempts queued by the standing rule (D134)

Revision ID: a7d3e91c4b20
Revises: bd671d7d0e10
Create Date: 2026-11-09 20:00:00.000000

Two flags, false for every existing row: package_approvals.by_rule (an approval the owner's
standing rule gave, which pausing the rule retires) and execution_attempts.queued_by_rule (an
attempt the rule queued, which pausing the rule or switching it off stops before anything is
sent). Outside the package content, so no package hash changes. Downgrade drops both.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e91c4b20"
down_revision: str | Sequence[str] | None = "bd671d7d0e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "package_approvals",
        sa.Column("by_rule", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "execution_attempts",
        sa.Column("queued_by_rule", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("execution_attempts", "queued_by_rule")
    op.drop_column("package_approvals", "by_rule")
