"""rehearsal records

Revision ID: 0b1c00a7e222
Revises: 9597307f950d
Create Date: 2026-10-22 13:51:54.794471

A rehearsal's stop now repeats every gate check and records what the rehearsal proved, as counts
and fixed values only (`rehearsal_records`). Attempts record the class of their destination
(`fixture` or `real`) when queued. Existing attempts keep NULL: they predate the record and count
in no evidence class. No existing row is changed and no package hash changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b1c00a7e222"
down_revision: str | Sequence[str] | None = "9597307f950d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rehearsal_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("destination_class", sa.String(length=10), nullable=False),
        sa.Column("route", sa.String(length=10), nullable=False),
        sa.Column("adapter", sa.String(length=50), nullable=False),
        sa.Column("adapter_version", sa.String(length=100), nullable=False),
        sa.Column("uploads_expected", sa.Integer(), nullable=False),
        sa.Column("uploads_acknowledged", sa.Integer(), nullable=False),
        sa.Column("readback_mismatched", sa.Integer(), nullable=True),
        sa.Column("recheck_matched", sa.Boolean(), nullable=False),
        sa.Column("egress_proxy_denied", sa.Integer(), nullable=False),
        sa.Column("unresolved", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=30), nullable=True),
        sa.CheckConstraint("destination_class IN ('fixture','real')", name="ck_rehearsal_class"),
        sa.CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN ('withdrawn_by_user','evidence_deleted')",
            name="ck_rehearsal_revoked_reason",
        ),
        sa.CheckConstraint("route IN ('browser','api')", name="ck_rehearsal_route"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["package_approvals.id"]),
        sa.ForeignKeyConstraint(["attempt_id"], ["execution_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_index(
        "ix_rehearsal_records_user_adapter", "rehearsal_records", ["user_id", "adapter"]
    )
    op.add_column(
        "execution_attempts", sa.Column("destination_class", sa.String(length=10), nullable=True)
    )
    op.create_check_constraint(
        "ck_attempt_destination_class",
        "execution_attempts",
        "destination_class IS NULL OR destination_class IN ('fixture','real')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_attempt_destination_class", "execution_attempts", type_="check")
    op.drop_column("execution_attempts", "destination_class")
    op.drop_index("ix_rehearsal_records_user_adapter", table_name="rehearsal_records")
    op.drop_table("rehearsal_records")
