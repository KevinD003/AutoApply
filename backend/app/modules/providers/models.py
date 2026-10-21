import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class ApiAuthorization(Base):
    """The user's explicit permission for NoEfforts to submit through one provider's API for
    one destination origin. Without an active row the API route is never chosen. Credentials
    are not stored here (see docs/provider-architecture.md, "API credentials")."""

    __tablename__ = "api_authorizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    origin: Mapped[str] = mapped_column(String(300))
    scope: Mapped[str] = mapped_column(String(20), default="submit")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
