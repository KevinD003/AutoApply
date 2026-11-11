"""which database this is: a stamp a restore leaves behind (D147)

Revision ID: d147a0c2e5f1
Revises: c4e8f2a19d35
Create Date: 2026-11-11 16:30:00.000000

One row holding the oid PostgreSQL gave this database. A database restored from a backup into a
new database (the deployment guide's §7: dropdb, createdb, pg_restore) keeps the stamp and gets
another oid; `app.modules.execution.restore` then holds everything the backup shows as queued or
in progress until it has ended it. The upgrade stamps the database it runs in. A database
restored from a backup taken before this revision has no stamp when its upgrade runs, so it is
stamped then and is not seen as restored. Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d147a0c2e5f1"
down_revision: str | Sequence[str] | None = "c4e8f2a19d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_stamp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("db_oid", sa.BigInteger(), nullable=False),
        sa.Column("stamped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restore_summary", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO instance_stamp (id, db_oid, stamped_at) "
            "SELECT 1, oid::bigint, now() FROM pg_database WHERE datname = current_database()"
        )
    )


def downgrade() -> None:
    op.drop_table("instance_stamp")
