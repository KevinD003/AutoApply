"""rehearsal paths

Revision ID: 33c1622938ba
Revises: 0b1c00a7e222
Create Date: 2026-10-22 15:16:39.379107

E6: a submission on an employer/provider path needs a valid recorded rehearsal on that path
first (execution/rehearsal.py). Attempts and rehearsal records keep the path as a keyed
reference (`path_ref`), attempts keep how the send gate found the prerequisite, and an approval
to submit keeps the attempt that met it. Existing rows keep NULL: they count for no path, so
the rule can only refuse them. No package hash changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "33c1622938ba"
down_revision: str | Sequence[str] | None = "0b1c00a7e222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("execution_attempts", sa.Column("path_ref", sa.String(length=64), nullable=True))
    op.add_column(
        "execution_attempts",
        sa.Column("rehearsal_prerequisite", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_attempt_rehearsal_prerequisite",
        "execution_attempts",
        "rehearsal_prerequisite IS NULL OR "
        "rehearsal_prerequisite IN ('met','established','not_required')",
    )
    op.create_index(
        "ix_execution_attempts_user_path",
        "execution_attempts",
        ["user_id", "path_ref", "created_at"],
        unique=False,
    )
    op.add_column(
        "package_approvals", sa.Column("prerequisite_attempt_id", sa.Uuid(), nullable=True)
    )
    op.add_column("rehearsal_records", sa.Column("path_ref", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_rehearsal_records_user_path", "rehearsal_records", ["user_id", "path_ref"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_rehearsal_records_user_path", table_name="rehearsal_records")
    op.drop_column("rehearsal_records", "path_ref")
    op.drop_column("package_approvals", "prerequisite_attempt_id")
    op.drop_index("ix_execution_attempts_user_path", table_name="execution_attempts")
    op.drop_constraint("ck_attempt_rehearsal_prerequisite", "execution_attempts", type_="check")
    op.drop_column("execution_attempts", "rehearsal_prerequisite")
    op.drop_column("execution_attempts", "path_ref")
