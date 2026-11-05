"""D128: connecting the owner's Gmail from the app with a browser OAuth authorization-code flow.

Two tables, and neither ever holds a token: the access/refresh tokens the flow obtains are written
to a 0600 file per account (connections/service.token_path), exactly as the connect.py CLI does,
never to the database, an image, logs, the frontend or chat.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class GmailConnection(Base):
    """One connected Gmail per NoEfforts account (the inbox owner). Non-secret binding and status
    facts only: which mailbox is connected (`email`), the granted scope (read-only), the status and
    when it changed. The refresh token is NOT here — it is in the account's 0600 token file.
    status: connected | revoked | error (the stored token no longer works; reconnect required)."""

    __tablename__ = "gmail_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(320))  # the connected mailbox's own address
    scope: Mapped[str] = mapped_column(String(200))  # the granted scope (read-only)
    status: Mapped[str] = mapped_column(String(16))  # connected | revoked | error
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(40))


class OAuthFlow(Base):
    """One in-progress browser OAuth authorization-code flow. The `state` is single-use (stamped
    `used_at` when the callback consumes it) and short-lived (created_at + a TTL, checked on the
    callback), and it binds the flow to the NoEfforts account that started it (`user_id`), so a
    callback presented in another account's session cannot complete it. The PKCE verifier is kept
    here only until the code is exchanged. No token is stored here; a row alone is of no use."""

    __tablename__ = "oauth_flows"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))  # "gmail"
    code_verifier: Mapped[str] = mapped_column(String(128))
    redirect_uri: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
