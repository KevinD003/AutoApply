"""D128: connect the owner's Gmail from the app with a browser OAuth authorization-code flow.

The owner starts from Account -> Connections; the backend redirects their browser to Google's
consent page; Google redirects back to one fixed, allowlisted callback; the backend validates the
callback, exchanges the code (a confidential "Web application" client, its secret server-side
only), verifies exactly the read-only scope was granted, learns which mailbox was connected
(users.getProfile), and writes the refresh token to a 0600 file per account — never the database,
the frontend, logs or chat. Connecting enables nothing on its own: reading application emails still
needs the separate in-app consent (D127) and the per-use toggles (D101/D103). The connect.py CLI
stays as an operator fallback.
"""

import secrets
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.urlsafety import UnsafeURL, fixture_opener, is_fixture_origin, public_https_opener
from app.modules.audit.service import record
from app.modules.connections.models import GmailConnection, OAuthFlow
from app.modules.identity.models import User
from app.modules.inbox import connect
from app.modules.inbox.provider import SCOPE, TOKEN_URL, GmailReader, InboxUnavailable
from app.modules.inbox.service import is_inbox_owner

PROVIDER = "gmail"
STATE_TTL = timedelta(minutes=10)  # a started flow must be completed within this
# Google's authorization endpoint, used unless a test points inbox_oauth_auth_base at a fixture.
# accounts.google.com is the OAuth sign-in host (as in connect.py), not a mailbox endpoint.
GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
CALLBACK_PATH = "/api/connections/gmail/callback"
# The fixed destinations the callback sends the browser back to (never a value from the request):
RETURN_PATH = "/account?connections=gmail"


class NotOwner(PermissionError):
    """Only the inbox owner may connect, disconnect or view the Gmail connection."""


def available() -> str | None:
    """Why connecting Gmail from the app is unavailable, or None: 'not_enabled' (the server has not
    turned the web flow on) or 'not_configured' (no web OAuth client is set)."""
    s = get_settings()
    if not s.inbox_oauth_enabled:
        return "not_enabled"
    if not (s.inbox_oauth_client_id and s.inbox_oauth_client_secret.get_secret_value()):
        return "not_configured"
    return None


def _auth_base() -> str:
    return get_settings().inbox_oauth_auth_base or GOOGLE_AUTH_BASE


def _token_url() -> str:
    return get_settings().inbox_token_url or TOKEN_URL


def redirect_uri() -> str:
    """The one fixed callback URI, under the server's own public base URL. It is what is registered
    with Google and what the code is exchanged against; it never comes from the request."""
    return get_settings().public_base_url.rstrip("/") + CALLBACK_PATH


def return_url(outcome: str) -> str:
    return get_settings().public_base_url.rstrip("/") + RETURN_PATH + "&result=" + outcome


def token_path(user_id) -> Path:
    return Path(get_settings().inbox_connections_dir) / f"{user_id}.json"


# -- SSRF-safe token POST: Google's token host over HTTPS to a public address, or a fixture origin
# in the test environment; no redirects, no other host (mirrors GmailReader._opener). ------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise connect.ConnectError(
            "the token endpoint answered with a redirect; it is not followed"
        )


def _opener(url: str) -> urllib.request.OpenerDirector:
    if url.startswith(TOKEN_URL):
        return public_https_opener(urlsplit(url).hostname, _NoRedirect)
    origin = url[: url.find("/", 8)] if url.startswith(("http://", "https://")) else ""
    if is_fixture_origin(origin):
        return fixture_opener(_NoRedirect)
    raise connect.ConnectError("the token endpoint host is not allowed")


def _post(url: str, timeout: float, data: dict) -> "connect._Reply":
    req = urllib.request.Request(
        url,
        data=urlencode(data).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with _opener(url).open(req, timeout=timeout) as r:
            body = r.read(connect.MAX_REPLY + 1)
    except urllib.error.HTTPError as e:
        return connect._Reply(e.code, b"{}")
    except (UnsafeURL, urllib.error.URLError, TimeoutError, OSError):
        raise connect.ConnectError("the token endpoint could not be reached safely") from None
    if len(body) > connect.MAX_REPLY:
        raise connect.ConnectError("the token endpoint answered with more than expected")
    return connect._Reply(r.status, body)


def start(db: Session, user: User) -> str:
    """Begin a flow: record a single-use, account-bound, expiring state and return the Google
    authorization URL to send the owner's browser to. Raises NotOwner, or ValueError(why)."""
    if not is_inbox_owner(user):
        raise NotOwner(PROVIDER)
    why = available()
    if why:
        raise ValueError(why)
    state = secrets.token_urlsafe(24)
    verifier, challenge = connect.pkce()
    rid = redirect_uri()
    db.add(OAuthFlow(state=state, user_id=user.id, provider=PROVIDER, code_verifier=verifier,
                     redirect_uri=rid))  # fmt: skip
    client = {"client_id": get_settings().inbox_oauth_client_id, "auth_uri": _auth_base()}
    return connect.auth_url(client, rid, state, challenge)


def _exchange(code: str, redirect_uri_: str, verifier: str) -> dict:
    s = get_settings()
    r = _post(_token_url(), 20, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri_,
        "client_id": s.inbox_oauth_client_id,
        "client_secret": s.inbox_oauth_client_secret.get_secret_value(),
        "code_verifier": verifier})  # fmt: skip
    return r.json() if r.status_code == 200 else {}


def _save_connection(db: Session, user: User, email: str) -> None:
    now = utcnow()
    row = db.get(GmailConnection, user.id)
    if row is None:
        row = GmailConnection(user_id=user.id)
        db.add(row)
    row.email, row.scope, row.status = email, SCOPE, "connected"
    row.connected_at, row.revoked_at, row.last_error = now, None, None


def _fail(db: Session, user: User, reason: str) -> str:
    """Record a failed connect attempt; never leave a half-written token behind."""
    p = token_path(user.id)
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
    record(db, user.id, "connections.gmail_connect_failed", "connection", None,
           provider=PROVIDER, reason_code=reason)  # fmt: skip
    return reason


def callback(db: Session, user: User, state: str, code: str, error: str) -> str:
    """Validate the callback and, on success, store the connection. Returns an outcome code:
    connected | denied | invalid_state | unexpected_scope | exchange_failed | unreachable.
    Never stores a token on any non-'connected' outcome."""
    if not is_inbox_owner(user):
        raise NotOwner(PROVIDER)
    now = utcnow()
    flow = db.get(OAuthFlow, state) if state else None
    # The state must exist, belong to THIS account (not another's), be unused and unexpired. A
    # replayed, forged, cross-account or stale state falls here before any code is exchanged.
    created = flow.created_at if flow else None
    if created is not None and created.tzinfo is None:
        from datetime import UTC

        created = created.replace(tzinfo=UTC)
    if (
        flow is None
        or flow.user_id != user.id
        or flow.provider != PROVIDER
        or flow.used_at is not None
        or created is None
        or now - created > STATE_TTL
    ):
        return "invalid_state"
    flow.used_at = now  # single use: consumed now, so a replay of the same state is invalid above
    db.flush()
    if error or not code:
        return _fail(db, user, "denied")
    try:
        body = _exchange(code, flow.redirect_uri, flow.code_verifier)
    except connect.ConnectError:
        return _fail(db, user, "unreachable")
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        return _fail(db, user, "exchange_failed")
    # Exactly the read-only scope must have been granted — no send or modify scope may enter
    # (defaults to the requested scope when the reply omits it, as Google's does echo it).
    if set(str(body.get("scope", SCOPE)).split()) != {SCOPE}:
        return _fail(db, user, "unexpected_scope")
    s = get_settings()
    creds = {"client_id": s.inbox_oauth_client_id,
             "client_secret": s.inbox_oauth_client_secret.get_secret_value(),
             "refresh_token": refresh}  # fmt: skip
    path = token_path(user.id)
    connect.save(creds, path)
    try:
        email = GmailReader(str(path), s.inbox_api_base, _token_url()).profile()
    except InboxUnavailable:
        email = ""
    _save_connection(db, user, email)
    record(db, user.id, "connections.gmail_connected", "connection", None, provider=PROVIDER)
    return "connected"


def active(db: Session, user: User) -> GmailConnection | None:
    row = db.get(GmailConnection, user.id)
    return row if row is not None and row.status == "connected" else None


def connected_token_file(db: Session, user: User) -> str:
    """The token file of this owner's active web connection, if its file is present; else "". The
    inbox reader prefers it over the CLI's configured file (inbox.service.reader)."""
    if active(db, user) is None:
        return ""
    p = token_path(user.id)
    return str(p) if p.exists() else ""


def mark_reconnect_required(db: Session, user_id) -> None:
    """The stored token stopped working (revoked at Google, or unreadable): the owner must
    reconnect. Called by the reader's failure path; keeps the row so the UI can say so."""
    row = db.get(GmailConnection, user_id)
    if row is not None and row.status == "connected":
        row.status, row.last_error = "error", "revoked"


def disconnect(db: Session, user: User) -> bool:
    """Remove the stored Google access: delete the token file and mark the connection revoked.
    (Revoking at Google is a separate, stronger step the UI points to.) Returns whether a
    connection was present. Audited."""
    if not is_inbox_owner(user):
        raise NotOwner(PROVIDER)
    row = db.get(GmailConnection, user.id)
    try:
        token_path(user.id).unlink(missing_ok=True)
    except OSError:
        pass
    if row is None:
        return False
    row.status, row.revoked_at, row.last_error = "revoked", utcnow(), None
    record(db, user.id, "connections.gmail_disconnected", "connection", None, provider=PROVIDER)
    return True


SCOPE_LABEL = (
    "Read-only access to your Gmail. NoEfforts can read your mail; it can never send, reply, "
    "delete, mark read or change labels, and stores no message content."
)
_STATE = {"connected": "connected", "error": "reconnect_required", "revoked": "not_connected"}


def status(db: Session, user: User) -> dict:
    """What Account -> Connections shows for Gmail: availability, whether this is the owner, the
    connection state, the connected mailbox identity, the access scope in plain words, and the last
    error if any. No token, ever."""
    why = available()
    owner = is_inbox_owner(user)
    row = db.get(GmailConnection, user.id) if owner else None
    state = _STATE.get(row.status, "not_connected") if row else "not_connected"
    return {
        "available": why is None,
        "why_not": why,
        "is_owner": owner,
        "state": state,
        "email": row.email if row and state != "not_connected" else None,
        "scope_label": SCOPE_LABEL,
        "connected_at": row.connected_at if row and state == "connected" else None,
        "last_error": row.last_error if row and state == "reconnect_required" else None,
    }
