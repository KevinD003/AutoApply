import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class EmailSettings(Base):
    """Your email reminders (D94): to you, the account owner, never to anyone else. Off until
    you verify an address with a code you enter in the app and turn them on. `code_digest` is a
    keyed digest of the pending code (never the code); `recipient_ref` of the address."""

    __tablename__ = "email_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    address: Mapped[str | None] = mapped_column(String(254))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_digest: Mapped[str | None] = mapped_column(String(64))
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_attempts: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    attention: Mapped[bool] = mapped_column(Boolean, default=True)
    follow_ups: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_hour_utc: Mapped[int] = mapped_column(Integer, default=7)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmailDelivery(Base):
    """One email NoEfforts tried to send you (D94): a verification code or a daily digest. Its
    content is never stored: only what it covered (the notification keys) and what happened.
    `status`: pending -> sending -> sent | uncertain | failed; pending -> cancelled. `uncertain`
    (the server may have accepted it) is final: never resent automatically. Worker writes are
    fenced by `generation`, like execution attempts."""

    __tablename__ = "email_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_email_delivery_dedupe"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # verification | digest
    dedupe_key: Mapped[str] = mapped_column(String(120))
    recipient_ref: Mapped[str] = mapped_column(String(64))  # keyed digest of the address
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_keys: Mapped[list] = mapped_column(JSON, default=list)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    outcome_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
