"""email status tracking

Revision ID: c3f1a7e5b921
Revises: ff6947989bba
Create Date: 2026-11-04 07:00:00.000000

Email-to-application status tracking (spec): enrich the existing inbox records (no parallel
status system). `inbox_events` gains the recognised event's richer taxonomy (wider `kind`), the
two separate confidences (`match_band`, `class_band`), the match basis as short codes only (never
message content), the proposed and previous application outcome, and a keyed reference to the
message's mail thread (for linking later messages in the same thread). `inbox_settings` gains
`auto_apply` (default off): suggest updates only, or automatically apply clear, well-matched ones.

All columns are additive; no message text/subject/sender-name is stored. Both tables are still
deleted with the user. Downgrade drops the new columns and narrows `kind`; recognition continues
on the original fields.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f1a7e5b921"
down_revision: str | Sequence[str] | None = "ff6947989bba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("inbox_events", "kind", type_=sa.String(length=32), existing_type=sa.String(20))
    op.add_column("inbox_events", sa.Column("match_band", sa.String(length=16), nullable=True))
    op.add_column("inbox_events", sa.Column("class_band", sa.String(length=16), nullable=True))
    op.add_column("inbox_events", sa.Column("match_basis", sa.String(length=120), nullable=True))
    op.add_column(
        "inbox_events", sa.Column("proposed_outcome", sa.String(length=24), nullable=True)
    )
    op.add_column("inbox_events", sa.Column("prev_outcome", sa.String(length=24), nullable=True))
    op.add_column("inbox_events", sa.Column("thread_ref", sa.String(length=64), nullable=True))
    op.create_index("ix_inbox_events_thread", "inbox_events", ["user_id", "thread_ref"])
    op.add_column(
        "inbox_settings",
        sa.Column("auto_apply", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("inbox_settings", "auto_apply")
    op.drop_index("ix_inbox_events_thread", table_name="inbox_events")
    for col in ("thread_ref", "prev_outcome", "proposed_outcome", "match_basis", "class_band",
                "match_band"):  # fmt: skip
        op.drop_column("inbox_events", col)
    op.alter_column("inbox_events", "kind", type_=sa.String(20), existing_type=sa.String(32))
