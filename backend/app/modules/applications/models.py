import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_id, utcnow
from app.modules.applications.states import Actor, AppState, Outcome


def _enum(e, name):
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    # One application identity per user and job: the first guard against duplicate submissions.
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    state: Mapped[AppState] = mapped_column(_enum(AppState, "app_state"), default=AppState.draft)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    outcome: Mapped[Outcome] = mapped_column(_enum(Outcome, "app_outcome"), default=Outcome.none)
    notes: Mapped[str | None] = mapped_column(Text)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": lock_version}


# Same text as migration e3a91c5d7b20 (autogenerate does not compare check constraints).
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


class ApplicationEvent(Base):
    """Immutable timeline entry. Rows are only ever inserted: a database trigger refuses an
    UPDATE and a DELETE that is not a cascade (migration e3a91c5d7b20, D53). `source`: what the
    event rests on (states.Source), set by applications.service only. Outcome events:
    `from_outcome`/`to_outcome` (NULL before S2; see `reason`) and `occurred_on`, the day the
    user says the employer acted. `evidence_note`: what the user checked, or their private note;
    served to its owner only, never audited or logged."""

    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(SOURCE_CHECK, name="ck_application_events_source"),
        CheckConstraint(OUTCOME_FIELDS_CHECK, name="ck_application_events_outcome_fields"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(50))  # state_change | outcome | note
    from_state: Mapped[AppState | None] = mapped_column(_enum(AppState, "app_state"))
    to_state: Mapped[AppState | None] = mapped_column(_enum(AppState, "app_state"))
    actor: Mapped[Actor] = mapped_column(_enum(Actor, "app_actor"))
    reason: Mapped[str | None] = mapped_column(String(1000))
    from_outcome: Mapped[Outcome | None] = mapped_column(_enum(Outcome, "app_outcome"))
    to_outcome: Mapped[Outcome | None] = mapped_column(_enum(Outcome, "app_outcome"))
    source: Mapped[str | None] = mapped_column(String(20))
    occurred_on: Mapped[date | None] = mapped_column(Date)
    evidence_note: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
