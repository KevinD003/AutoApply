"""approval scope

Revision ID: 9597307f950d
Revises: 7a1e4c2b9d30
Create Date: 2026-10-22 09:45:29.227229

Approvals record what they permit: `submit` (fill, upload, check and submit once) or
`disclose_only` (a rehearsal that stops before the send gate). Every existing approval was given
to fill and submit, so existing rows get `submit`: no approval changes meaning, none is
invalidated, and no package hash changes (the scope is not package content).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9597307f950d"
down_revision: str | Sequence[str] | None = "7a1e4c2b9d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "package_approvals",
        sa.Column("scope", sa.String(length=20), server_default="submit", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("package_approvals", "scope")
