"""Personal access tokens (priority D, D84; docs/api-tokens.md): made, checked and revoked here.

A token is `ne_<public id>_<secret>`: 8 lowercase letters or digits, then 43 URL-safe
characters (256 random bits). Only its SHA-256 hash is kept. It is read from the
`Authorization: Bearer` header only, never from a query string or a cookie.

What a token may reach is an allow-list of (method, route template) per scope: every other
route refuses it (default deny). No scope reaches answering, consent, approval, queueing,
submission, verification codes, profile facts, documents, saved answers, the account's export
or deletion, or token management: those stay behind a signed-in session and its CSRF token."""

import hmac
import re
import secrets
import string
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_log import template
from app.core.config import get_settings
from app.core.db import utcnow
from app.modules.apitokens.models import ApiToken
from app.modules.identity.models import User
from app.modules.identity.security import hash_token, login_limiter

PREFIX = "/api"
DEFAULT_DAYS, MAX_DAYS = 30, 90
_ID = string.ascii_lowercase + string.digits
_TOKEN = re.compile(r"^ne_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")

# Any token may read what it is itself (its scopes and expiry): the CLI and MCP server ask.
_SELF = {("GET", "/api/token")}
SCOPES: dict[str, frozenset[tuple[str, str]]] = {
    "read": frozenset(
        {
            ("GET", "/api/jobs"),
            ("GET", "/api/jobs/{job_id}"),
            ("GET", "/api/applications"),
            ("GET", "/api/applications/funnel"),
            ("GET", "/api/applications/{app_id}"),
            ("GET", "/api/notifications"),
            ("GET", "/api/notifications/unread"),
            ("GET", "/api/follow-ups"),  # D92: the list; not the draft, which names you
        }
    ),
    # The same as the Jobs page: add one job, or import a CSV or XLSX file. Nothing else.
    "import:jobs": frozenset({("POST", "/api/jobs"), ("POST", "/api/jobs/import")}),
}

# Why a token request is refused, shown after the message ("(reason: code)"). The messages do
# not say whether a token exists: unknown, expired and revoked read the same.
REASONS = {
    "token_invalid": "This API token is not valid: it is unknown, expired or revoked.",
    "token_scope": "This API token's scopes do not allow this request.",
    "token_rate_limited": "Too many requests with tokens that are not valid. Try again in a "
    "minute.",
    "token_session_only": "This needs you signed in to the app: API tokens cannot do it.",
}


def reason(code: str) -> str:
    return f"{REASONS[code]} (reason: {code})"


def allowed(scopes: list[str]) -> frozenset[tuple[str, str]]:
    out = set(_SELF)
    for s in scopes:
        out |= SCOPES.get(s, frozenset())
    return frozenset(out)


def create(db: Session, user_id, label: str, scopes: list[str], days: int) -> tuple[ApiToken, str]:
    """A new token and its one-time plaintext. The caller commits; the plaintext is returned
    once and never stored or logged."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"A token expires within 1 to {MAX_DAYS} days.")
    if not scopes or set(scopes) - set(SCOPES):
        raise ValueError(f"Scopes must be one or more of: {', '.join(SCOPES)}.")
    for _ in range(5):
        public_id = "".join(secrets.choice(_ID) for _ in range(8))
        if db.scalar(select(ApiToken.id).where(ApiToken.public_id == public_id)) is None:
            break
    token = f"ne_{public_id}_{secrets.token_urlsafe(32)}"
    row = ApiToken(
        user_id=user_id,
        public_id=public_id,
        secret_hash=hash_token(token),
        label=label,
        scopes=sorted(set(scopes)),
        expires_at=utcnow() + timedelta(days=days),
    )
    db.add(row)
    db.flush()
    return row, token


def state(row: ApiToken, now=None) -> str:
    now = now or utcnow()
    if row.revoked_at is not None:
        return "revoked"
    return "expired" if row.expires_at <= now else "active"


def _refuse(request: Request) -> HTTPException:
    client = request.client.host if request.client else "unknown"
    limit = get_settings().login_rate_limit_per_minute
    if not login_limiter.allow(f"api-token:{client}", limit):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, reason("token_rate_limited"))
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        reason("token_invalid"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate(request: Request, db: Session) -> User:
    """The user of the Bearer token in this request, if the token is valid and its scopes allow
    this route. Sets request.state.api_token (its public id) for routes that serve less to a
    token than to the app."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    token = value.strip()
    m = _TOKEN.match(token) if scheme.lower() == "bearer" else None
    row = db.scalar(select(ApiToken).where(ApiToken.public_id == m.group(1))) if m else None
    # Compared in constant time, and computed even for an unknown id.
    matches = hmac.compare_digest(row.secret_hash if row else "0" * 64, hash_token(token))
    now = utcnow()
    if row is None or not matches or state(row, now) != "active":
        raise _refuse(request)
    if (request.method, template(request.scope, PREFIX)) not in allowed(row.scopes):
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason("token_scope"))
    user = db.get(User, row.user_id)
    if user is None:
        raise _refuse(request)
    if row.last_used_at is None or now - row.last_used_at >= timedelta(hours=1):
        row.last_used_at = now.replace(minute=0, second=0, microsecond=0)
        db.commit()
    request.state.api_token = row.public_id
    return user


def is_token_request(request: Request) -> bool:
    return getattr(request.state, "api_token", None) is not None
