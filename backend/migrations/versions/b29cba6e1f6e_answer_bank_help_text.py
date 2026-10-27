"""answer bank help text

Revision ID: b29cba6e1f6e
Revises: 33c1622938ba
Create Date: 2026-10-27 01:45:00.000000

C6 (D51): a saved answer records the help text of the question it was saved for (NULL: saved
before C6, not recorded; '': the question had none). A question with help text now has its own
key (resolver.question_key); a question without help text keeps its key, so no row is re-keyed
or deleted and there is no data step. Existing rows keep NULL and, by their key, answer only a
question without help text. The migration itself changes no package hash. After a downgrade,
rows saved for a question with help text keep keys the old code never computes: inert, still
listed and deletable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b29cba6e1f6e"
down_revision: str | Sequence[str] | None = "33c1622938ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("answer_bank", sa.Column("help_text", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("answer_bank", "help_text")
