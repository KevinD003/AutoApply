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
from fastapi.responses import JSONResponse

PREFIX = "/inbox-fixture"
API = f"{PREFIX}/gmail/v1/users/me/messages"
TOKEN = "fixture-access-token"


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

    @app.post(f"{PREFIX}/token")
    async def token(request: Request):
        form = await request.form()
        ledger.run("insert into inbox_requests (route,bearer,created_at) values (?,?,?)",
                   ("token", 0, time.time()))
        if form.get("grant_type") != "refresh_token" or not form.get("refresh_token"):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if cfg.get("inbox_mode") == "revoked":
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return {"access_token": TOKEN, "expires_in": 3599, "token_type": "Bearer",
                "scope": "readonly"}  # fmt: skip

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
