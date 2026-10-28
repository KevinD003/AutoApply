"""job signals

Revision ID: 269ea4b8bc0c
Revises: 29588d78e7e1
Create Date: 2026-10-28 21:08:35.608786

S3 (D59). Three nullable timestamps: on jobs, the user's audited statements that a posting is
still open (`open_confirmed_at`) and that a job is a different role (`distinct_confirmed_at`);
on discovered jobs, when the source first said the posting was stale (`stale_since`), set from
`last_seen_at` for rows already stale (the latest time NoEfforts saw that report). No data is
changed otherwise. Downgrade drops the three columns: the statements are lost (their audit rows
stay), so approvals refused for a job signal ask again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "269ea4b8bc0c"
down_revision: str | Sequence[str] | None = "29588d78e7e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovered_jobs", sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("jobs", sa.Column("open_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs", sa.Column("distinct_confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE discovered_jobs SET stale_since = last_seen_at WHERE stale")


def downgrade() -> None:
    op.drop_column("jobs", "distinct_confirmed_at")
    op.drop_column("jobs", "open_confirmed_at")
    op.drop_column("discovered_jobs", "stale_since")
