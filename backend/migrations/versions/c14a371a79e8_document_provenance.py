"""document provenance

Revision ID: c14a371a79e8
Revises: d1e3ab560050
Create Date: 2026-10-29 01:53:52.000000

C18 (D71). A generated document records the document it was made from, the hash of the facts
it was grounded on and when the user accepted it; all NULL for an upload (every existing row).
A generated document without an acceptance is never chosen, proposed or sent. Downgrade is
refused while such a document exists (the earlier code would use it), then drops the columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c14a371a79e8"
down_revision: str | Sequence[str] | None = "d1e3ab560050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "documents_base_document_id_fkey"


def upgrade() -> None:
    op.add_column("documents", sa.Column("base_document_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("grounding_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        FK, "documents", "documents", ["base_document_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    waiting = op.get_bind().execute(
        sa.text("select count(*) from documents where origin = 'generated' and accepted_at is null")
    )
    if waiting.scalar():
        raise RuntimeError(
            "generated documents await acceptance; the earlier schema would use them. "
            "Delete them or accept them first."
        )
    op.drop_constraint(FK, "documents", type_="foreignkey")
    op.drop_column("documents", "accepted_at")
    op.drop_column("documents", "grounding_hash")
    op.drop_column("documents", "base_document_id")
