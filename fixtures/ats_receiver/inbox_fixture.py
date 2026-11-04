"""D101: a local stand-in of the parts of Gmail's REST API NoEfforts reads (list messages, get one
message, refresh an access token), so the inbox reader is tested without Google. Synthetic
messages only; a test adds them through the admin endpoint, and the OTP form mode can deposit its
own code email. FIXTURE ASSUMPTION: the shapes follow Google's published Gmail API reference
(users.messages.list / users.messages.get, format=full; the OAuth token endpoint); nothing here
was observed on a real account.

The ledger's `inbox_requests` table records each request's route and whether a bearer token
came with it (never the token)."""

import base64
import json
import re
import time
import uuid

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

PREFIX = "/inbox-fixture"
API = f"{PREFIX}/gmail/v1/users/me/messages"
API_PROFILE = f"{PREFIX}/gmail/v1/users/me/profile"  # users.getProfile stand-in (D128)
AUTHORIZE = f"{PREFIX}/authorize"  # Google's consent page stand-in (D128 browser OAuth flow)
TOKEN = "fixture-access-token"
REFRESH = "fixture-refresh-token"


def _scope_code(granted_scope: str) -> str:
    """Encode the granted scope into the authorization code, so the token endpoint can echo exactly
    what consent granted without this fixture ever writing a Gmail scope literal of its own."""
    return "ac." + base64.urlsafe_b64encode(granted_scope.encode()).decode().rstrip("=")


def _code_scope(code: str) -> str:
    try:
        raw = code[3:] if code.startswith("ac.") else ""
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(sender: str, subject: str, text: str, at: float | None = None) -> dict:
    """A message in the API's `format=full` shape: a text/plain part and an HTML part."""
    at = time.time() if at is None else at
    mid = uuid.uuid4().hex[:16]
    return {
        "id": mid,
        "threadId": mid,
        "internalDate": str(int(at * 1000)),
        "snippet": text[:100],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                                                        time.gmtime(at))},  # fmt: skip
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(text)}},
                {"mimeType": "text/html", "body": {"data": _b64(f"<p>{text}</p>")}},
            ],
        },
    }


def mount(app, ledger, cfg) -> None:
    ledger.run("create table if not exists inbox_messages (id text primary key, at real, body text)")
    ledger.run("create table if not exists inbox_requests (id integer primary key, route text, "
               "bearer integer, created_at real)")  # fmt: skip

    def seen(route: str, authorization: str | None) -> None:
        ledger.run("insert into inbox_requests (route,bearer,created_at) values (?,?,?)",
                   (route, int(bool(authorization)), time.time()))
        if cfg.get("inbox_mode") == "unauthorized" or authorization != f"Bearer {TOKEN}":
            raise HTTPException(401, "invalid credentials")

    @app.get(AUTHORIZE)
    def authorize(request: Request):
        """Google's consent page stand-in (D128): redirect back to the app's callback with a code,
        or an error. The granted scope (echoed at the token endpoint) is carried in the code; a mode
        can deny consent or add a scope the app did not ask for."""
        q = request.query_params
        state, redirect_uri = q.get("state", ""), q.get("redirect_uri", "")
        ledger.run("insert into inbox_requests (route,bearer,created_at) values (?,?,?)",
                   ("authorize", 0, time.time()))  # fmt: skip
        if cfg.get("oauth_mode") == "deny":
            return RedirectResponse(f"{redirect_uri}?error=access_denied&state={state}", 302)
        granted = q.get("scope", "")
        extra = cfg.get("oauth_extra_scope")
        if extra:  # a scope beyond what was requested (the app must refuse this)
            granted = (granted + " " + extra).strip()
        code = _scope_code(granted)
        return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", 302)

    @app.post(f"{PREFIX}/token")
    async def token(request: Request):
        form = await request.form()
        grant = form.get("grant_type")
        ledger.run("insert into inbox_requests (route,bearer,created_at) values (?,?,?)",
                   ("token", 0, time.time()))  # fmt: skip
        if grant == "authorization_code":
            code = str(form.get("code") or "")
            if not code.startswith("ac."):
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            body = {"access_token": TOKEN, "expires_in": 3599, "token_type": "Bearer",
                    "scope": _code_scope(code)}  # fmt: skip
            if cfg.get("oauth_mode") != "no_refresh":  # a reply without a refresh token
                body["refresh_token"] = REFRESH
            return body
        if grant != "refresh_token" or not form.get("refresh_token"):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if cfg.get("inbox_mode") == "revoked":
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return {"access_token": TOKEN, "expires_in": 3599, "token_type": "Bearer",
                "scope": "readonly"}  # fmt: skip

    @app.get(API_PROFILE)
    def get_profile(authorization: str | None = Header(None)):
        """users.getProfile stand-in (D128): the connected mailbox's own address."""
        seen("profile", authorization)
        return {"emailAddress": cfg.get("oauth_email") or "owner.mailbox@example.com",
                "messagesTotal": 0, "threadsTotal": 0, "historyId": "1"}  # fmt: skip

    @app.get(API)
    def list_messages(q: str = "", maxResults: int = 100, pageToken: str = "",  # noqa: N803
                      authorization: str | None = Header(None)):  # fmt: skip
        seen("list", authorization)
        after = re.search(r"\bafter:(\d+)", q)
        since = int(after.group(1)) if after else 0
        rows = ledger.run("select id, at from inbox_messages where at > ? order by at desc",
                          (since,))  # fmt: skip
        start = int(pageToken or 0)
        page = rows[start: start + maxResults]
        out = {"messages": [{"id": i, "threadId": i} for i, _ in page],
               "resultSizeEstimate": len(rows)}  # fmt: skip
        if start + maxResults < len(rows):
            out["nextPageToken"] = str(start + maxResults)
        return out

    @app.get(API + "/{mid}")
    def get_message(mid: str, format: str = "full", authorization: str | None = Header(None)):  # noqa: A002
        seen("get", authorization)
        row = ledger.run("select body from inbox_messages where id=?", (mid,))
        if not row:
            raise HTTPException(404, "not found")
        return json.loads(row[0][0])


def deposit(ledger, sender: str, subject: str, text: str, at: float | None = None) -> str:
    m = message(sender, subject, text, at)
    ledger.run("insert into inbox_messages (id,at,body) values (?,?,?)",
               (m["id"], int(m["internalDate"]) / 1000, json.dumps(m)))
    return m["id"]
