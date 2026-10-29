"""draft grounding hash

Revision ID: d1e3ab560050
Revises: f150c66c69e3
Create Date: 2026-10-29 00:05:46.460640

C15 (D68). A draft records the hash of the facts it cites when it is made, compared when the
user accepts it; existing drafts keep NULL (accept then compares the request instead). A draft
the user rejects has its text erased, so the text may be NULL. Downgrade deletes those erased
rows (the earlier code would offer an empty cached draft) and drops the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e3ab560050"
down_revision: str | Sequence[str] | None = "f150c66c69e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("answer_drafts", sa.Column("grounding_hash", sa.String(length=64), nullable=True))
    op.alter_column("answer_drafts", "text", existing_type=sa.TEXT(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM answer_drafts WHERE text IS NULL")
    op.alter_column("answer_drafts", "text", existing_type=sa.TEXT(), nullable=False)
    op.drop_column("answer_drafts", "grounding_hash")
