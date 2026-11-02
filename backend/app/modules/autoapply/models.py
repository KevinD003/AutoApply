"""D113: the owner's standing rule to apply automatically, and what it did.

`AutoApplyPrefs` holds the owner's own pause switch (the rule is on by default where the server
enables it). `AutoApplyEvent` records each thing the rule did or declined to do for one job, so
the owner can see it, the daily cap can count it, and a job is not re-examined in a loop."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class AutoApplyPrefs(Base):
    __tablename__ = "auto_apply_prefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutoApplyEvent(Base):
    __tablename__ = "auto_apply_events"
    __table_args__ = (Index("ix_auto_apply_events_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    # approved_rehearsal | approved_submit | skipped
    action: Mapped[str] = mapped_column(String(30))
    # A fixed code (autoapply/service.py REASONS); never a field key, a value or page text.
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
