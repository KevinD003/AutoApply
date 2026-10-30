"""board daily check

Revision ID: e5a1c3f80d47
Revises: d7f3b9e41c26
Create Date: 2026-10-31 12:00:00.000000

D96. `board_sources.daily_check`: you chose to have the board read once a day (off for every
existing board). `board_sources.baseline_at`: its first successful read; postings first seen
after it are new to you. A board already read gets its last successful read as its baseline,
so nothing it already listed is announced as new. Downgrade drops both columns: daily checks
stop and nothing else changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a1c3f80d47"
down_revision: str | Sequence[str] | None = "d7f3b9e41c26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "board_sources",
        sa.Column("daily_check", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "board_sources", sa.Column("baseline_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE board_sources SET baseline_at = last_success_at")


def downgrade() -> None:
    op.drop_column("board_sources", "baseline_at")
    op.drop_column("board_sources", "daily_check")
