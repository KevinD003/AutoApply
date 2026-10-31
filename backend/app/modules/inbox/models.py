import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class InboxSettings(Base):
    """D101: your choices for reading your own Gmail. Off until you turn each one on: verification
    codes for an application that is waiting for one, and application emails proposed as
    outcomes. `last_checked_at`: the end of the last completed read (the next one starts there);
    `last_error`: a fixed code, never a message from the provider."""

    __tablename__ = "inbox_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    codes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InboxEvent(Base):
    """D101: one email NoEfforts read, as what it said. Kept: a keyed reference to the message
    (so it is read once), when it arrived, the sender's domain, its kind, the application it
    names (if exactly one) and what happened (`state`). Never its text, subject, sender's name
    or a code.

    kind: code | rejected | interview | assessment | received | unclear | other.
    state: proposed (an outcome waiting for you) | accepted | dismissed | unlinked (no single
    application named) | code_used | code_unclear | noted."""

    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("user_id", "message_ref", name="uq_inbox_message"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_ref: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sender_domain: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
