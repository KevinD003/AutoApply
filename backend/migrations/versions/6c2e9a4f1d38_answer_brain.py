"""answer brain

Revision ID: 6c2e9a4f1d38
Revises: 51e5cd3d9c4d
Create Date: 2026-11-02 10:12:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c2e9a4f1d38"
down_revision: str | Sequence[str] | None = "51e5cd3d9c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "learning_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("bank_entry_id", sa.Uuid(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bank_entry_id"], ["answer_bank.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_learning_labels_user_id"), "learning_labels", ["user_id"], unique=False
    )
    op.create_table(
        "learning_models",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("learning_models")
    op.drop_index(op.f("ix_learning_labels_user_id"), table_name="learning_labels")
    op.drop_table("learning_labels")
