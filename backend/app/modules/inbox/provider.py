"""D101: reading the owner's own Gmail, read-only, through Google's REST API.

The only module allowed to name Gmail's API (tests/test_forbidden_capabilities.py: INBOX_READING).
It lists messages received after a time and reads one message; it never sends, deletes, labels or
changes anything (the token it uses was granted the read-only scope by the owner in their own
browser, `connect.py`). The token file lives on the owner's machine, outside the repository and
the database, readable only by its owner.

Hosts are fixed: Google's API and token endpoints. A test points both at the local stand-in
(fixtures/ats_receiver/inbox_fixture.py), allowed only for a fixture origin in the test
environment; every other host is refused before a connection is made.
"""

import base64
import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from app.core.urlsafety import UnsafeURL, fixture_opener, is_fixture_origin, public_https_opener

API_BASE = "https://gmail.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
MESSAGES = "/gmail/v1/users/me/messages"
MAX_TEXT = 20_000  # what is read of one message's text; the rest is ignored
MAX_REPLY = 5_000_000  # the largest answer read from the API


class InboxUnavailable(RuntimeError):
    """code: not_configured | token_unreadable | revoked | unreachable | refused_host | bad_reply"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Message:
    id: str
    received_at: datetime
    sender_name: str
    sender_domain: str
    subject: str
    text: str


def _origin(url: str) -> str:
    m = re.match(r"^(https?://[^/]+)", url)
    return m.group(1) if m else ""


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _text_of(payload: dict) -> str:
    """The message's plain text: its text/plain parts, else its HTML parts without tags."""
    plain, rich = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(_strip_html(_decode(data)))
        for p in part.get("parts") or []:
            walk(p)

    walk(payload or {})
    text = "\n".join(plain) if plain else "\n".join(rich)
    return " ".join(text.split())[:MAX_TEXT]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InboxUnavailable("bad_reply")  # a redirect is never followed


def _json(raw: bytes):
    if len(raw) > MAX_REPLY:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


class GmailReader:
    def __init__(self, token_file: str, api_base: str = "", token_url: str = "",
                 timeout: float = 15.0):  # fmt: skip
        self.token_file = token_file
        self.api_base = (api_base or API_BASE).rstrip("/")
        self.token_url = token_url or TOKEN_URL
        self.timeout = timeout
        self._token: str | None = None

    def _opener(self, url: str) -> urllib.request.OpenerDirector:
        """Google's API and token hosts over HTTPS to public addresses only (checked at
        connection time), or a fixture origin in the test environment; no redirects. Any other
        host is refused before a connection is made."""
        if url.startswith((API_BASE + "/", TOKEN_URL)):
            return public_https_opener(urlsplit(url).hostname, _NoRedirect)
        if is_fixture_origin(_origin(url)):
            return fixture_opener(_NoRedirect)
        raise InboxUnavailable("refused_host")

    def _send(self, req: urllib.request.Request) -> tuple[int, bytes]:
        """(status, body) of one request; a refused or failed connection is `unreachable`."""
        try:
            with self._opener(req.full_url).open(req, timeout=self.timeout) as r:
                return r.status, r.read(MAX_REPLY + 1)
        except InboxUnavailable:
            raise
        except urllib.error.HTTPError as e:
            return e.code, b""
        except (UnsafeURL, urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise InboxUnavailable("unreachable") from None

    def _creds(self) -> dict:
        if not self.token_file:
            raise InboxUnavailable("not_configured")
        try:
            c = json.loads(Path(self.token_file).read_text())
        except (OSError, ValueError):
            raise InboxUnavailable("token_unreadable") from None
        if not all(isinstance(c.get(k), str) and c[k] for k in
                   ("client_id", "client_secret", "refresh_token")):  # fmt: skip
            raise InboxUnavailable("token_unreadable")
        return c

    def _access_token(self) -> str:
        if self._token:
            return self._token
        c = self._creds()
        form = urlencode({"grant_type": "refresh_token", "refresh_token": c["refresh_token"],
                          "client_id": c["client_id"],
                          "client_secret": c["client_secret"]}).encode()  # fmt: skip
        req = urllib.request.Request(self.token_url, data=form, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded"})  # fmt: skip
        status, raw = self._send(req)
        if status in (400, 401):
            raise InboxUnavailable("revoked")
        body = _json(raw) if status == 200 else None
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
            raise InboxUnavailable("bad_reply")
        self._token = body["access_token"]
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = self.api_base + path + ("?" + urlencode(params) if params else "")
        self._opener(url)  # an unknown host is refused before the token is even asked for
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": f"Bearer {self._access_token()}"})  # fmt: skip
        status, raw = self._send(req)
        if status == 401:
            raise InboxUnavailable("revoked")
        body = _json(raw) if status == 200 else None
        if not isinstance(body, dict):
            raise InboxUnavailable("bad_reply")
        return body

    def received_after(self, after: datetime, limit: int = 200) -> list[str]:
        """Ids of messages received after `after` (newest first), at most `limit`."""
        ids: list[str] = []
        page = ""
        while len(ids) < limit:
            params = {"q": f"after:{int(after.timestamp())}", "maxResults": min(100, limit)}
            if page:
                params["pageToken"] = page
            body = self._get(MESSAGES, params)
            ids += [m["id"] for m in body.get("messages") or [] if isinstance(m.get("id"), str)]
            page = body.get("nextPageToken") or ""
            if not page:
                break
        return ids[:limit]

    def read(self, message_id: str) -> Message:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", message_id):
            raise InboxUnavailable("bad_reply")
        body = self._get(f"{MESSAGES}/{message_id}", {"format": "full"})
        payload = body.get("payload") or {}
        headers = {h.get("name", "").lower(): h.get("value", "") for h in
                   payload.get("headers") or [] if isinstance(h, dict)}  # fmt: skip
        name, addr = parseaddr(headers.get("from", ""))
        try:
            at = datetime.fromtimestamp(int(body.get("internalDate", "0")) / 1000, UTC)
        except (TypeError, ValueError):
            at = datetime.now(UTC)
        return Message(
            id=message_id,
            received_at=at,
            sender_name=(name or "")[:200],
            sender_domain=addr.rsplit("@", 1)[-1].lower()[:200] if "@" in addr else "",
            subject=(headers.get("subject") or "")[:500],
            text=_text_of(payload),
        )
