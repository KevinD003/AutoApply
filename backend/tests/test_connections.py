"""D128: connecting the owner's Gmail from the app with a browser OAuth authorization-code flow,
driven end to end against the local Google-OAuth stand-in (fixtures/ats_receiver/inbox_fixture.py):
the authorize hop issues a code, the token endpoint echoes exactly the granted scope, and
users.getProfile names the connected mailbox. Synthetic only; nothing contacts Google. No scope or
Gmail-endpoint literal appears here — the one place that may name them is the reader (provider.py).
"""

import datetime
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.models import AuditEvent
from app.modules.connections import service
from app.modules.connections.models import GmailConnection, OAuthFlow
from app.modules.identity.models import User
from app.modules.inbox.provider import SCOPE
from tests.execution_harness import BASE, Receiver

OWNER = "synthetic.user@example.com"  # the `api` fixture's account
OWNER2 = "another.synthetic@example.com"  # the `other_api` fixture's account (also an owner here)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.fixture
def web(monkeypatch, tmp_path):
    """The server has the web OAuth flow enabled and a web client configured; the authorize, token
    and API hosts point at the local stand-in; tokens are written under a temp dir."""
    s = get_settings()
    for k, v in (
        ("inbox_enabled", True),
        ("inbox_owner_emails", [OWNER, OWNER2]),
        ("inbox_oauth_enabled", True),
        ("inbox_oauth_client_id", "web-client-id.apps.example"),
        ("inbox_oauth_auth_base", f"{BASE}/inbox-fixture/authorize"),
        ("inbox_token_url", f"{BASE}/inbox-fixture/token"),
        ("inbox_api_base", f"{BASE}/inbox-fixture"),
        ("public_base_url", "http://testserver"),
        ("inbox_connections_dir", str(tmp_path / "connections")),
    ):
        monkeypatch.setattr(s, k, v)
    from pydantic import SecretStr

    monkeypatch.setattr(s, "inbox_oauth_client_secret", SecretStr("web-client-secret"))
    return s


def _uid(email: str):
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def begin(api) -> tuple[str, str]:
    """Start the flow; return (authorize_url, state) from the 302 to the stand-in's consent page."""
    r = api.get("/connections/gmail/start", follow_redirects=False)
    assert r.status_code == 302, r.text
    auth_url = r.headers["location"]
    state = dict(parse_qsl(urlsplit(auth_url).query))["state"]
    return auth_url, state


def consent(auth_url: str) -> dict:
    """Follow the authorize hop (the stand-in's consent page) and return the callback's query."""
    ar = httpx.get(auth_url, follow_redirects=False)
    assert ar.status_code == 302, ar.text
    return dict(parse_qsl(urlsplit(ar.headers["location"]).query))


def finish(api, auth_url: str) -> str:
    """Complete a flow and return the outcome the callback redirects back with."""
    q = consent(auth_url)
    cr = api.get("/connections/gmail/callback", params=q, follow_redirects=False)
    assert cr.status_code == 302, cr.text
    return dict(parse_qsl(urlsplit(cr.headers["location"]).query)).get("result", "")


# -- the happy path -------------------------------------------------------------------------------


def test_connecting_in_the_browser_stores_the_connection_and_binds_the_mailbox(api, web, receiver):
    receiver.config(oauth_email="owner.inbox@example.com")
    auth_url, _ = begin(api)
    assert auth_url.startswith(f"{BASE}/inbox-fixture/authorize")
    assert finish(api, auth_url) == "connected"
    # Status shows connected, the connected mailbox identity, and plain-language read-only scope.
    v = api.get("/connections").json()["gmail"]
    assert v["state"] == "connected" and v["email"] == "owner.inbox@example.com"
    assert v["is_owner"] is True and "read-only" in v["scope_label"].lower()
    # The connection row is bound to this account; the refresh token is in a 0600 file, not the DB.
    uid = _uid(OWNER)
    with SessionLocal() as db:
        row = db.get(GmailConnection, uid)
        assert row.status == "connected" and row.scope == SCOPE
    path = service.token_path(uid)
    assert path.exists() and (path.stat().st_mode & 0o777) == 0o600
    # Audited; no flow state lingers.
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "connections.gmail_connected")) == 1  # fmt: skip


def test_connecting_enables_no_processing_by_itself(api, web, receiver):
    assert finish(api, begin(api)[0]) == "connected"
    v = api.get("/inbox").json()
    # Connected, but reading application emails, codes, tracking and auto-apply are all still off
    # and unauthorized until the owner chooses them (D101/D103/D127).
    assert v["codes_enabled"] is False and v["tracking_enabled"] is False
    assert v["auto_apply"] is False and v["tracking_authorized"] is False
    # A read is still refused (no authorization), and turning tracking on is refused too.
    assert api.post("/inbox/check").status_code == 409
    r = api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    assert r.status_code == 409


# -- failure and abuse cases (requirement 6) ------------------------------------------------------


def test_denied_consent_stores_nothing(api, web, receiver):
    receiver.config(oauth_mode="deny")
    assert finish(api, begin(api)[0]) == "denied"
    assert api.get("/connections").json()["gmail"]["state"] == "not_connected"
    assert not service.token_path(_uid(OWNER)).exists()


def test_an_unknown_state_is_refused(api, web, receiver):
    r = api.get("/connections/gmail/callback", params={"state": "nope", "code": "ac.x"},
                follow_redirects=False)  # fmt: skip
    assert dict(parse_qsl(urlsplit(r.headers["location"]).query))["result"] == "invalid_state"


def test_an_expired_state_is_refused(api, web, receiver):
    auth_url, state = begin(api)
    q = consent(auth_url)
    with SessionLocal() as db:  # age the flow past its TTL
        flow = db.get(OAuthFlow, state)
        flow.created_at = utcnow() - datetime.timedelta(minutes=30)
        db.commit()
    assert finish_params(api, q) == "invalid_state"
    assert not service.token_path(_uid(OWNER)).exists()


def test_a_replayed_state_is_refused_the_second_time(api, web, receiver):
    auth_url, _ = begin(api)
    q = consent(auth_url)
    assert finish_params(api, q) == "connected"  # first use
    assert finish_params(api, q) == "invalid_state"  # the same state again (single use)


def test_another_account_cannot_complete_this_accounts_flow(api, other_api, web, receiver):
    # api (OWNER) starts; other_api (OWNER2, also an owner here) presents api's state.
    auth_url, _ = begin(api)
    q = consent(auth_url)
    assert finish_params(other_api, q) == "invalid_state"  # bound to the account that started it
    assert not service.token_path(_uid(OWNER)).exists()


def test_a_scope_beyond_read_only_is_refused_and_nothing_is_stored(api, web, receiver):
    receiver.config(oauth_extra_scope="openid")  # the grant adds a scope the app never asked for
    assert finish(api, begin(api)[0]) == "unexpected_scope"
    assert api.get("/connections").json()["gmail"]["state"] == "not_connected"
    assert not service.token_path(_uid(OWNER)).exists()


def test_a_grant_without_a_refresh_token_is_refused(api, web, receiver):
    receiver.config(oauth_mode="no_refresh")
    assert finish(api, begin(api)[0]) == "exchange_failed"
    assert not service.token_path(_uid(OWNER)).exists()


def test_a_non_owner_cannot_connect(other_api, monkeypatch, tmp_path, receiver):
    s = get_settings()
    for k, v in (("inbox_enabled", True), ("inbox_owner_emails", [OWNER]),  # OWNER2 is NOT an owner
                 ("inbox_oauth_enabled", True), ("inbox_oauth_client_id", "x"),
                 ("inbox_connections_dir", str(tmp_path))):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    from pydantic import SecretStr

    monkeypatch.setattr(s, "inbox_oauth_client_secret", SecretStr("y"))
    assert other_api.get("/connections/gmail/start", follow_redirects=False).status_code == 409
    v = other_api.get("/connections").json()["gmail"]
    assert v["is_owner"] is False and v["state"] == "not_connected"


def test_unavailable_when_the_web_flow_is_off(api, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "inbox_oauth_enabled", False)
    monkeypatch.setattr(s, "inbox_owner_emails", [OWNER])
    assert api.get("/connections/gmail/start", follow_redirects=False).status_code == 409
    assert api.get("/connections").json()["gmail"]["available"] is False


# -- disconnect / reconnect / revoked credentials -------------------------------------------------


def test_disconnect_removes_the_token_and_reconnect_connects_again(api, web, receiver):
    assert finish(api, begin(api)[0]) == "connected"
    uid = _uid(OWNER)
    assert service.token_path(uid).exists()
    v = api.post("/connections/gmail/disconnect").json()
    assert v["gmail"]["state"] == "not_connected"
    assert not service.token_path(uid).exists()
    with SessionLocal() as db:
        assert db.get(GmailConnection, uid).status == "revoked"
    # Reconnect works and returns to connected.
    assert finish(api, begin(api)[0]) == "connected"
    assert api.get("/connections").json()["gmail"]["state"] == "connected"


def test_a_revoked_token_puts_the_connection_into_reconnect_required(
    api, web, receiver, monkeypatch
):
    from app.core import authorizations
    from app.modules.inbox import service as inbox
    from tests.authorized import authorize

    assert finish(api, begin(api)[0]) == "connected"
    # Authorize + enable tracking (D117/D127) so a read is attempted, then make the token fail.
    authorize(monkeypatch, authorizations.INBOX)
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True}).raise_for_status()
    receiver.config(inbox_mode="revoked")
    with SessionLocal() as db:
        user = db.get(User, _uid(OWNER))
        inbox.check(db, user)
        db.commit()
    assert api.get("/connections").json()["gmail"]["state"] == "reconnect_required"


def test_the_web_connected_token_is_what_the_reader_reads(api, web, receiver, monkeypatch):
    """End to end: with the browser connection (no CLI token file set) plus authorization and
    tracking on, a read uses the web connection's token and proposes an email."""
    from app.core import authorizations
    from app.modules.inbox import service as inbox
    from tests.authorized import authorize

    assert finish(api, begin(api)[0]) == "connected"
    authorize(monkeypatch, authorizations.INBOX)
    assert get_settings().inbox_token_file == ""  # no CLI token file: only the web connection
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True}).raise_for_status()
    httpx.post(f"{BASE}/_admin/inbox", headers=receiver._h(), json={
        "sender": "Example Health Clinic <talent@examplehealth.test>",
        "subject": "Your application", "text": "Unfortunately we are moving forward with others."
    }).raise_for_status()  # fmt: skip
    with SessionLocal() as db:
        user = db.get(User, _uid(OWNER))
        out = inbox.check(db, user)
        # A completed read (not skipped for "not connected" and not an auth error) proves the web
        # connection's token file was found and used; the cursor only advances on success.
        assert "skipped" not in out and "error" not in out
        assert inbox.settings_of(db, user.id).last_checked_at is not None
        db.commit()


def finish_params(api, q: dict) -> str:
    cr = api.get("/connections/gmail/callback", params=q, follow_redirects=False)
    assert cr.status_code == 302, cr.text
    return dict(parse_qsl(urlsplit(cr.headers["location"]).query)).get("result", "")
