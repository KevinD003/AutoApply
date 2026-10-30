import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class FollowUp(Base):
    """Your choices about following up on one application (D92). The reminder itself is not
    stored: when it is due is derived from the application's own records (followups/service.py)
    and these choices, which are the only state kept: the day you said you followed up, a day
    you asked to be reminded on, and whether you stopped the reminders."""

    __tablename__ = "follow_ups"
    __table_args__ = (UniqueConstraint("user_id", "application_id", name="uq_follow_up"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    followed_up_on: Mapped[date | None] = mapped_column(Date)
    remind_on: Mapped[date | None] = mapped_column(Date)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
