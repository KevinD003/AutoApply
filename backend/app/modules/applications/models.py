import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ApplicationEvent(Base):
    """Immutable timeline entry. Rows are only ever inserted."""

    __tablename__ = "application_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(50))  # state_change | outcome | note
    from_state: Mapped[AppState | None] = mapped_column(_enum(AppState, "app_state"))
    to_state: Mapped[AppState | None] = mapped_column(_enum(AppState, "app_state"))
    actor: Mapped[Actor] = mapped_column(_enum(Actor, "app_actor"))
    reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
