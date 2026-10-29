"""generated documents

Revision ID: 60e18e9115c8
Revises: c14a371a79e8
Create Date: 2026-10-29 02:40:00.000000

L2/L3 (D73). A generated document (a tailored resume or a cover letter) records the application
it was written for and the ids of the facts it cites; NULL for uploads (every existing row).
Downgrade drops both columns; C18's downgrade then refuses while an unaccepted generated
document exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60e18e9115c8"
down_revision: str | Sequence[str] | None = "c14a371a79e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "documents_made_for_application_id_fkey"


def upgrade() -> None:
    op.add_column("documents", sa.Column("made_for_application_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("grounded_on", sa.JSON(), nullable=True))
    op.create_foreign_key(
        FK, "documents", "applications", ["made_for_application_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(FK, "documents", type_="foreignkey")
    op.drop_column("documents", "grounded_on")
    op.drop_column("documents", "made_for_application_id")
