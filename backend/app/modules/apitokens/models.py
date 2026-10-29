import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class ApiToken(Base):
    """A personal access token (priority D, D84; docs/api-tokens.md). The token itself is shown
    once, when it is made, and never stored: only its SHA-256 hash is, with a short public id
    to find it by. It always expires; revoking it takes effect on the next request."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The 8 characters after "ne_": not secret, shown in the list so you can tell tokens apart.
    public_id: Mapped[str] = mapped_column(String(8), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(100))
    scopes: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # To the hour: enough to spot a token in use that should not be.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
