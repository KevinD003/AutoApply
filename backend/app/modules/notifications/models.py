import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class NotificationRead(Base):
    """That you read one notification (priority C, D83). Notifications themselves are not
    stored: they are derived from the records they describe (notifications/service.py). Only
    this mark is kept, by the notification's key, which names a record of yours."""

    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("user_id", "item_key", name="uq_notification_read"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_key: Mapped[str] = mapped_column(String(120))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
