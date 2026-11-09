"""a pause for a question the page reveals and requires after filling (D135)

Revision ID: c4e8f2a19d35
Revises: a7d3e91c4b20
Create Date: 2026-11-09 22:30:00.000000

One more value for application_pauses.kind: conditional_required (after filling and before the
send gate, the page showed and required a question it reveals by its own logic, with no approved
answer). Existing rows keep form_changed. Downgrade deletes the conditional_required rows (the
older code knows no such pause; deleting one also lifts the approval block it held) and restores
the one-value check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8f2a19d35"
down_revision: str | Sequence[str] | None = "a7d3e91c4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_pause_kind", "application_pauses", type_="check")
    op.create_check_constraint(
        "ck_pause_kind", "application_pauses", "kind IN ('form_changed','conditional_required')"
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM application_pauses WHERE kind = 'conditional_required'"))
    op.drop_constraint("ck_pause_kind", "application_pauses", type_="check")
    op.create_check_constraint("ck_pause_kind", "application_pauses", "kind IN ('form_changed')")
