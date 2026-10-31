"""D101: connect your own Gmail, read-only, on your own machine.

    cd backend
    uv run python -m app.modules.inbox.connect --credentials ~/Downloads/credentials.json \\
        --out ~/.noefforts/inbox-token.json

`credentials.json` is the OAuth client you created in your Google Cloud project ("Desktop app").
Your browser opens Google's consent page for read-only access to your mail; you approve it there.
The token is written to `--out`, readable by you only, and never printed. Then set
NOEFFORTS_INBOX_TOKEN_FILE to that path, NOEFFORTS_INBOX_ENABLED=true and
NOEFFORTS_INBOX_OWNER_EMAILS to your NoEfforts account's email. Keep both files out of the
repository; to disconnect, delete the token file and remove NoEfforts in your Google account's
"Third-party access" page.

The flow is Google's documented one for installed apps: a loopback redirect to 127.0.0.1 on a
free port, a state value and PKCE (S256). Nothing else is requested.
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from app.modules.inbox.provider import SCOPE

GOOGLE_AUTH = ("https://accounts.google.com/",)
GOOGLE_TOKEN = ("https://oauth2.googleapis.com/", "https://accounts.google.com/")


class ConnectError(RuntimeError):
    pass


def client_of(credentials: dict) -> dict:
    """The installed-app client in a credentials.json from Google Cloud Console."""
    c = credentials.get("installed") or {}
    if not all(isinstance(c.get(k), str) and c[k] for k in
               ("client_id", "client_secret", "auth_uri", "token_uri")):  # fmt: skip
        raise ConnectError('Not a desktop-app OAuth client (expected an "installed" entry).')
    if not c["auth_uri"].startswith(GOOGLE_AUTH) or not c["token_uri"].startswith(GOOGLE_TOKEN):
        raise ConnectError("The credentials name an authorization server that is not Google's.")
    return c


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def auth_url(client: dict, redirect_uri: str, state: str, challenge: str) -> str:
    return client["auth_uri"] + "?" + urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})  # fmt: skip


def exchange(client: dict, code: str, redirect_uri: str, verifier: str, post=httpx.post) -> dict:
    r = post(client["token_uri"], timeout=20, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "code_verifier": verifier})  # fmt: skip
    body = r.json() if r.status_code == 200 else {}
    if not isinstance(body.get("refresh_token"), str):
        raise ConnectError("Google did not return a refresh token. Run this again and approve.")
    if SCOPE not in str(body.get("scope", SCOPE)).split():
        raise ConnectError("Google granted a different scope than read-only mail.")
    return {"client_id": client["client_id"], "client_secret": client["client_secret"],
            "refresh_token": body["refresh_token"]}  # fmt: skip


def save(token: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token, f)
    os.chmod(out, 0o600)


def _wait_for_code(state: str) -> tuple[str, str]:
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            q = parse_qs(urlsplit(self.path).query)
            ok = q.get("state", [""])[0] == state and "code" in q
            got.update(code=q.get("code", [""])[0] if ok else "", error=q.get("error", [""])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"NoEfforts: you can close this tab." if ok
                             else b"NoEfforts: this was not the expected answer.")  # fmt: skip
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}/"
    return srv, redirect, got  # type: ignore[return-value]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Connect your Gmail to NoEfforts, read-only.")
    ap.add_argument("--credentials", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        client = client_of(json.loads(a.credentials.read_text()))
        state, (verifier, challenge) = secrets.token_urlsafe(24), pkce()
        srv, redirect, got = _wait_for_code(state)
        url = auth_url(client, redirect, state, challenge)
        print("Opening Google's consent page for read-only access to your mail. If it does not "
              f"open, visit:\n{url}")  # fmt: skip
        webbrowser.open(url)
        srv.serve_forever()
        if not got.get("code"):
            raise ConnectError(f"Not connected ({got.get('error') or 'no answer'}).")
        save(exchange(client, got["code"], redirect, verifier), a.out)
    except (OSError, ValueError, ConnectError, httpx.HTTPError) as e:
        print(f"Not connected: {e}", file=sys.stderr)
        return 1
    print(f"Connected, read-only. The token is saved to {a.out} (readable by you only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
