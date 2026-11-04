"""inbox application-email consent (authenticated, in-app owner consent)

Revision ID: e5b9c1f3a2d8
Revises: d4e8f1a2b3c7
Create Date: 2026-11-04 19:00:00.000000

`inbox_consents`: the owner's own authenticated, auditable, revocable in-app consent to read
application emails in their mailbox, so activating email tracking needs no source edit. Covers
read_application_email only (never codes, sending or submission); holds the owner's attestation in
their own words, when it was granted, an optional last day it holds, and when it was revoked. No
message content and no token. Deleted with the user. Downgrade drops the table: any in-app consent
is gone and the feature is gated by the reviewed-source register alone, as before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b9c1f3a2d8"
down_revision: str | Sequence[str] | None = "d4e8f1a2b3c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("attestation", sa.String(length=500), nullable=False),
        sa.Column("disclosure_version", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_consents_user_id", "inbox_consents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_inbox_consents_user_id", table_name="inbox_consents")
    op.drop_table("inbox_consents")
