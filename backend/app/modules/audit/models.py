import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class AuditEvent(Base):
    """Append-only record of user-visible actions. Never store secrets or codes in `meta`."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
