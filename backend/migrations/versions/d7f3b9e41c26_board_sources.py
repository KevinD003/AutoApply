"""board sources

Revision ID: d7f3b9e41c26
Revises: c4e8a2d17b55
Create Date: 2026-10-31 09:00:00.000000

D95. `board_sources`: one row per public employer job board an account added (provider, the
board's identifier, what the user calls the employer, paused, and what the last read did).
`discovered_jobs.board_source_id` links a posting to the board it was read from; deleting the
source deletes its postings. Both are deleted with the user. Downgrade drops the column and the
table: board postings and sources are lost; Freehire discovery is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7f3b9e41c26"
down_revision: str | Sequence[str] | None = "c4e8a2d17b55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("region", sa.String(length=10), nullable=False),
        sa.Column("board", sa.String(length=100), nullable=False),
        sa.Column("employer", sa.String(length=200), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("last_count", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "region", "board", name="uq_board_source"),
    )
    op.create_index("ix_board_sources_user_id", "board_sources", ["user_id"])
    op.add_column("discovered_jobs", sa.Column("board_source_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "discovered_jobs_board_source_id_fkey", "discovered_jobs", "board_sources",
        ["board_source_id"], ["id"], ondelete="CASCADE",
    )  # fmt: skip
    op.create_index("ix_discovered_jobs_board_source_id", "discovered_jobs", ["board_source_id"])


def downgrade() -> None:
    op.drop_index("ix_discovered_jobs_board_source_id", table_name="discovered_jobs")
    op.drop_constraint(
        "discovered_jobs_board_source_id_fkey", "discovered_jobs", type_="foreignkey"
    )
    op.drop_column("discovered_jobs", "board_source_id")
    op.drop_index("ix_board_sources_user_id", table_name="board_sources")
    op.drop_table("board_sources")
