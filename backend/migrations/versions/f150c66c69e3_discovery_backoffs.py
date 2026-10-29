"""discovery backoffs

Revision ID: f150c66c69e3
Revises: 269ea4b8bc0c
Create Date: 2026-10-28 23:39:49.212895

S6 (D67). One row per (user, discovery provider): the time before which NoEfforts sends that
provider none of the user's imports or refreshes, set from a Retry-After after a 429. Deleted
with the user. Nothing else changes. Downgrade drops the table: the next import is sent at once
(a provider still limiting answers 429 again, which is reported and never retried).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f150c66c69e3"
down_revision: str | Sequence[str] | None = "269ea4b8bc0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_backoffs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "provider"),
    )


def downgrade() -> None:
    op.drop_table("discovery_backoffs")
