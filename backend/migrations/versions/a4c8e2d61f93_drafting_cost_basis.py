"""drafting cost basis

Revision ID: a4c8e2d61f93
Revises: e5a1c3f80d47
Create Date: 2026-10-31 14:00:00.000000

D97. `drafting_usage.cost_basis` says what each amount is (reserved, estimated, unknown,
not_sent) and `drafting_usage.price_version` names the list prices an estimate used. Existing
rows: still reserved stay `reserved`; refused before sending become `not_sent`; settled with
reported tokens become `estimated` at the only prices ever used; settled without tokens keep
or regain their worst case and become `unknown`. That includes a provider error recorded at 0
before D97: the provider may have charged for it, so its worst case counts again. Downgrade
drops both columns; the restored worst cases stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c8e2d61f93"
down_revision: str | Sequence[str] | None = "e5a1c3f80d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICE_VERSION = "anthropic-list-2026-10-06"


def upgrade() -> None:
    op.add_column(
        "drafting_usage",
        sa.Column("cost_basis", sa.String(20), server_default="reserved", nullable=False),
    )
    op.add_column("drafting_usage", sa.Column("price_version", sa.String(40), nullable=True))
    op.execute(f"UPDATE drafting_usage SET price_version = '{PRICE_VERSION}'")
    op.execute(
        "UPDATE drafting_usage SET cost_basis = 'not_sent', cost_usd = 0 "
        "WHERE status = 'settled' AND outcome = 'provider_destination_refused'"
    )
    op.execute(
        "UPDATE drafting_usage SET cost_basis = 'estimated' "
        "WHERE status = 'settled' AND cost_basis = 'reserved' AND input_tokens IS NOT NULL"
    )
    op.execute(
        "UPDATE drafting_usage SET cost_basis = 'unknown', cost_usd = reserved_usd "
        "WHERE status = 'settled' AND cost_basis = 'reserved'"
    )


def downgrade() -> None:
    op.drop_column("drafting_usage", "price_version")
    op.drop_column("drafting_usage", "cost_basis")
