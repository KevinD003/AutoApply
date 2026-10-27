"""outcome integrity

Revision ID: e3a91c5d7b20
Revises: b29cba6e1f6e
Create Date: 2026-10-27 18:00:00.000000

S2 (D53). The outcome assessment_received, before interviewing, so the type's order matches
applications.states.Outcome. Application events gain from_outcome and to_outcome (the change an
outcome event records), source (what an event rests on: receipt, user_claimed, user_reported),
occurred_on (the day the user says the employer acted) and evidence_note (what the user checked,
or their private note; never copied into audit rows). No row is rewritten and nothing is
inferred: rows written before S2 keep NULL in every new column, and both checks hold for them.
Events become insert-only in the database: a trigger refuses UPDATE, and DELETE unless it is a
cascade (deleting the application or user still removes its events); a later data repair must
drop and recreate it deliberately. No package content changes, so no package hash or approval
changes. Downgrade: refused while an application's outcome is assessment_received (the earlier
code cannot load it; nothing is remapped); otherwise drops the trigger, its function, the checks
and the columns (notes written since S2 are lost). The enum value stays, unused (PostgreSQL
cannot remove one).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3a91c5d7b20"
down_revision: str | Sequence[str] | None = "b29cba6e1f6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same text as app/modules/applications/models.py.
SOURCE_CHECK = (
    "source IS NULL"
    " OR (source = 'receipt' AND kind = 'state_change' AND actor = 'worker'"
    " AND to_state IS NOT NULL AND to_state = 'submitted_confirmed')"
    " OR (source = 'user_claimed' AND kind = 'state_change' AND actor = 'user'"
    " AND to_state IS NOT NULL AND (to_state = 'submitted_unconfirmed'"
    " OR (to_state = 'submitted_confirmed' AND evidence_note IS NOT NULL)))"
    " OR (source = 'user_reported' AND kind = 'outcome' AND actor = 'user'"
    " AND from_outcome IS NOT NULL AND to_outcome IS NOT NULL)"
)
OUTCOME_FIELDS_CHECK = (
    "kind = 'outcome' OR (from_outcome IS NULL AND to_outcome IS NULL AND occurred_on IS NULL)"
)
# A cascade from applications runs inside the foreign key's own trigger (depth 2 or more); a
# DELETE issued on this table directly runs at depth 1. TRUNCATE fires no row trigger.
INSERT_ONLY = (
    "CREATE FUNCTION application_events_insert_only() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF; "
    "RAISE EXCEPTION 'application_events rows are insert-only' "
    "USING ERRCODE = 'integrity_constraint_violation'; END $$"
)


def upgrade() -> None:
    """Upgrade schema."""
    # Not used in this transaction (PostgreSQL refuses an uncommitted value), as 8b41c0d7e2f5.
    op.execute(
        "ALTER TYPE app_outcome ADD VALUE IF NOT EXISTS 'assessment_received' BEFORE 'interviewing'"
    )
    outcome = postgresql.ENUM(name="app_outcome", create_type=False)
    op.add_column("application_events", sa.Column("from_outcome", outcome, nullable=True))
    op.add_column("application_events", sa.Column("to_outcome", outcome, nullable=True))
    op.add_column("application_events", sa.Column("source", sa.String(length=20), nullable=True))
    op.add_column("application_events", sa.Column("occurred_on", sa.Date(), nullable=True))
    op.add_column(
        "application_events", sa.Column("evidence_note", sa.String(length=2000), nullable=True)
    )
    op.create_check_constraint("ck_application_events_source", "application_events", SOURCE_CHECK)
    op.create_check_constraint(
        "ck_application_events_outcome_fields", "application_events", OUTCOME_FIELDS_CHECK
    )
    op.execute(INSERT_ONLY)
    op.execute(
        "CREATE TRIGGER application_events_insert_only BEFORE UPDATE OR DELETE ON "
        "application_events FOR EACH ROW EXECUTE FUNCTION application_events_insert_only()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if context.is_offline_mode():
        raise RuntimeError("This downgrade checks applications.outcome; run it online.")
    held = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM applications WHERE outcome = 'assessment_received'"))
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{held} application(s) record the outcome assessment_received, which the previous "
            "revision cannot read. Record another outcome for them first; nothing was changed."
        )
    op.execute("DROP TRIGGER application_events_insert_only ON application_events")
    op.execute("DROP FUNCTION application_events_insert_only()")
    op.drop_constraint("ck_application_events_outcome_fields", "application_events", type_="check")
    op.drop_constraint("ck_application_events_source", "application_events", type_="check")
    for column in ("evidence_note", "occurred_on", "source", "to_outcome", "from_outcome"):
        op.drop_column("application_events", column)
