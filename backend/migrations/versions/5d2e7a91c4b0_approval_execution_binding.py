"""approval execution binding

Revision ID: 5d2e7a91c4b0
Revises: c55aebd101ce
Create Date: 2026-10-20 15:30:00.000000

Approvals record the adapter and adapter version they were given for. Existing rows keep NULL:
they predate bindings and mean the route the code had then (execution.policy.approved_binding),
so no existing approval is invalidated by this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d2e7a91c4b0"
down_revision: str | Sequence[str] | None = "c55aebd101ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("package_approvals", sa.Column("adapter", sa.String(length=50), nullable=True))
    op.add_column(
        "package_approvals", sa.Column("adapter_version", sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("package_approvals", "adapter_version")
    op.drop_column("package_approvals", "adapter")
