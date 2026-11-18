"""every application that paused before D169 stays its owner's; a pause keeps its no-difference read (D170)

Revision ID: d170b0a8e3c1
Revises: d147a0c2e5f1
Create Date: 2026-11-18 07:00:00.000000

Before D169 the standing rule left every application that had ever stopped on a changed form to
its owner for good (D132), and showed its pause in D132's words ("nothing is sent until you do";
"…or apply on the employer's site"). D169 lets the rule continue such an application unless it is
recorded as handed over ("skipped: form_changed"), an event the rule wrote only for an application
it examined after the stop: among its newest jobs, the account's rule on and a recorded permission
in force. An application that paused before this upgrade may have no such event, and the rule
would then take back one its owner was told was theirs, which they may have applied to by hand
meanwhile. The upgrade records that hand-over for every application with a pause and none, as
D132 left it (`hand_over`). The downgrade keeps them: they were true before this revision too.

`application_pauses.unexplained_at`: when a read of the employer's form first found no difference
from the version a pause stopped on. Never cleared, so the rule's judgement that a page kept
changing (autoapply `_kept_changing`) survives a later read finding a new version, which ends the
pause and overwrites `recaptured_version`. Unknown (null) for earlier pauses: each of their
applications is its owner's by the hand-over above. The downgrade drops it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d170b0a8e3c1"
down_revision: str | Sequence[str] | None = "d147a0c2e5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_pauses", sa.Column("unexplained_at", sa.DateTime(timezone=True), nullable=True)
    )
    hand_over()


def hand_over() -> None:
    """One `skipped: form_changed` event for each application with a pause and none yet, under
    the application's own account."""
    op.execute(
        sa.text(
            "INSERT INTO auto_apply_events "
            "(id, user_id, job_id, application_id, action, reason, created_at) "
            "SELECT gen_random_uuid(), a.user_id, a.job_id, a.id, 'skipped', 'form_changed', now() "
            "FROM applications a "
            "WHERE EXISTS (SELECT 1 FROM application_pauses p "
            "WHERE p.application_id = a.id AND p.user_id = a.user_id) "
            "AND NOT EXISTS (SELECT 1 FROM auto_apply_events e "
            "WHERE e.application_id = a.id AND e.user_id = a.user_id AND e.reason = 'form_changed')"
        )
    )


def downgrade() -> None:
    """The hand-overs stay: D132 left those applications to their owners before D169 too."""
    op.drop_column("application_pauses", "unexplained_at")
