"""application_pauses: an application stopped because the employer's form changed (D132)

Revision ID: bd671d7d0e10
Revises: f2c7a9e4b1d6
Create Date: 2026-11-06 13:30:00.000000

One row per stop for a changed form: the attempt it ended (never resumed), whether anything had
been entered on the page, the package it ran (its hash: never approved or sent again) and the
form version it ran against. Counts only, never a question's key or label. At most one
unresolved (open or unexplained) pause per application, enforced by a partial unique index.
Cascades with the user, the application and the attempt. Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bd671d7d0e10"
down_revision: str | Sequence[str] | None = "f2c7a9e4b1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_pauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("package_hash", sa.String(length=64), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("recaptured_version", sa.Integer(), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('form_changed')", name="ck_pause_kind"),
        sa.CheckConstraint(
            "phase IN ('before_disclosure','after_disclosure')", name="ck_pause_phase"
        ),
        sa.CheckConstraint(
            "status IN ('open','unexplained','resolved','closed')", name="ck_pause_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["execution_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_pauses_application_id", "application_pauses", ["application_id"]
    )
    op.create_index("ix_application_pauses_attempt_id", "application_pauses", ["attempt_id"])
    op.create_index(
        "ix_application_pauses_user_status", "application_pauses", ["user_id", "status"]
    )
    op.create_index(
        "uq_one_unresolved_pause",
        "application_pauses",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open','unexplained')"),
    )


def downgrade() -> None:
    op.drop_index("uq_one_unresolved_pause", table_name="application_pauses")
    op.drop_index("ix_application_pauses_user_status", table_name="application_pauses")
    op.drop_index("ix_application_pauses_attempt_id", table_name="application_pauses")
    op.drop_index("ix_application_pauses_application_id", table_name="application_pauses")
    op.drop_table("application_pauses")
