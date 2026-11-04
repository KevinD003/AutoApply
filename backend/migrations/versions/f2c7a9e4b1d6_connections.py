"""connections: browser OAuth Gmail connection and in-progress OAuth flows (D128)

Revision ID: f2c7a9e4b1d6
Revises: e5b9c1f3a2d8
Create Date: 2026-11-04 22:30:00.000000

`gmail_connections`: one row per account (the inbox owner) with the connected mailbox's address,
the granted read-only scope, status and timestamps. `oauth_flows`: a single-use, account-bound,
short-lived authorization-code state with its PKCE verifier. Neither holds a token: the refresh
token the flow obtains is written to a 0600 file per account, never the database. Both cascade on
user delete. Downgrade drops both; any web connection must then be made again with the CLI.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c7a9e4b1d6"
down_revision: str | Sequence[str] | None = "e5b9c1f3a2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gmail_connections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "oauth_flows",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.String(length=400), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index("ix_oauth_flows_user_id", "oauth_flows", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_flows_user_id", table_name="oauth_flows")
    op.drop_table("oauth_flows")
    op.drop_table("gmail_connections")
