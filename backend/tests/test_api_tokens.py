"""API tokens, the CLI and the MCP server (priority D, D84; docs/api-tokens.md): shown once and
stored as a hash, expiring by default, revocable, read from the Authorization header only, and
limited per scope to an allow-list of routes (default deny). No token reaches review, consent,
approval, submission, profile facts, documents, saved answers, the export, deletion or token
management. Synthetic data only; the real-server test starts uvicorn on a free loopback port
and stops only that process."""

import hashlib
import importlib.util
import io
import json
import logging
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta
from http.cookiejar import CookieJar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.db import SessionLocal, utcnow
from app.main import create_app
from app.modules.apitokens import service
from app.modules.apitokens.models import ApiToken
from app.modules.audit.models import AuditEvent

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
TOKEN_RE = re.compile(r"^ne_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cli = _load("noefforts")
mcp = _load("noefforts_mcp")


def make(api, scopes=("read",), days=None, label="laptop") -> str:
    body = {"label": label, "scopes": list(scopes)} | ({"expires_in_days": days} if days else {})
    r = api.post("/account/tokens", json=body)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def bare() -> TestClient:
    """A client with no session cookie: what a script or MCP client is."""
    return TestClient(create_app(), base_url="http://testserver/api")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def add_job(api, n=1, **kw) -> str:
    body = {"url": f"https://careers.example.com/tokens/{n}", "title": f"Analyst {n}",
            "employer": "Example Co"} | kw  # fmt: skip
    r = api.post("/jobs", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()["job"]["id"]


# ---------------------------------------------------------------------------- lifecycle


def test_a_token_is_shown_once_and_only_its_hash_is_kept(api):
    r = api.post("/account/tokens", json={"label": "laptop", "scopes": ["read"]})
    assert r.status_code == 201
    token = r.json()["token"]
    assert TOKEN_RE.match(token)
    details = r.json()["details"]
    assert details["public_id"] == token[3:11] and details["state"] == "active"
    # Expires by default, in 30 days.
    left = (datetime.fromisoformat(details["expires_at"]) - utcnow()).total_seconds()
    assert 29 * 86400 < left <= 30 * 86400
    listed = api.get("/account/tokens").json()
    assert token not in json.dumps(listed) and "secret_hash" not in json.dumps(listed)
    assert [t["public_id"] for t in listed["items"]] == [details["public_id"]]
    with SessionLocal() as db:
        (row,) = db.scalars(select(ApiToken)).all()
        stored = json.dumps({c.name: str(getattr(row, c.name)) for c in ApiToken.__table__.c})
        audit = json.dumps([e.meta for e in db.scalars(select(AuditEvent))])
    assert row.secret_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored and token[12:] not in stored  # neither the token nor its secret
    assert token[12:] not in audit and row.secret_hash not in audit


@pytest.mark.parametrize(
    "body, code",
    [
        ({"label": "x", "scopes": ["read"], "expires_in_days": 91}, 422),  # at most 90 days
        ({"label": "x", "scopes": ["read"], "expires_in_days": 0}, 422),
        ({"label": "x", "scopes": []}, 422),
        ({"label": "x", "scopes": ["admin"]}, 400),  # no such scope
        ({"label": "x", "scopes": ["submit"]}, 400),
        ({"label": "", "scopes": ["read"]}, 422),
    ],
)
def test_a_token_always_expires_and_has_known_scopes(api, body, code):
    assert api.post("/account/tokens", json=body).status_code == code


def test_reads_work_with_the_header_alone(api):
    job_id = add_job(api, description="Daily Excel reports.")
    token = make(api)
    c = bare()
    jobs = c.get("/jobs", headers=bearer(token))
    assert jobs.status_code == 200 and [j["id"] for j in jobs.json()["items"]] == [job_id]
    assert jobs.json()["items"][0]["match"] is not None  # the list's match summary
    assert c.get("/applications", headers=bearer(token)).status_code == 200
    assert c.get("/notifications", headers=bearer(token)).json()["unread"] == 0
    assert c.get("/token", headers=bearer(token)).json()["scopes"] == ["read"]


def test_a_token_reads_a_job_without_the_eligibility_that_shows_your_facts(api):
    api.post("/profile/work-authorizations", json={"country_code": "US", "authorized": "yes",
             "sponsorship_needed_now": "no", "sponsorship_needed_future": "no"})  # fmt: skip
    job_id = add_job(api)
    in_app = api.get(f"/jobs/{job_id}").json()["fit"]
    assert in_app["eligibility"] and in_app["eligibility"][0]["yours"]
    by_token = bare().get(f"/jobs/{job_id}", headers=bearer(make(api))).json()["fit"]
    assert by_token["eligibility"] == [] and "app only" in by_token["eligibility_hidden"]
    assert by_token["preferences"] == in_app["preferences"]
    assert "authorized" not in json.dumps(by_token)


# ---------------------------------------------------------------------------- scope


def _routes():
    """Every operation the app serves, from its OpenAPI document (as tests/test_api_paths.py)."""
    for path, ops in create_app().openapi()["paths"].items():
        for method in ops:
            yield method.upper(), path


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000001", path)


def test_every_route_outside_a_scope_refuses_the_token_before_doing_anything(api):
    """Default deny, swept over every route the app has: a `read` token reaches its allow-list
    and nothing else, a write never succeeds, and nothing is recorded."""
    read, imp = make(api, ["read"]), make(api, ["import:jobs"], label="importer")
    with SessionLocal() as db:
        audit_before = db.scalar(select(func.count()).select_from(AuditEvent))
    c, anonymous = bare(), bare()
    checked = 0
    for method, path in _routes():
        url = _concrete(path.removeprefix("/api"))
        if anonymous.request(method, url).status_code != 401:
            continue  # public (health, sign-in, register, test fixtures): no token involved
        for token, scope in ((read, "read"), (imp, "import:jobs")):
            r = c.request(method, url, headers=bearer(token))
            if (method, path) in service.allowed([scope]):
                assert r.status_code not in (401, 403), (method, path, r.text)
                continue
            checked += 1
            assert r.status_code in (401, 403), (method, path, r.status_code)
            if r.status_code == 403:
                assert r.json()["detail"].endswith(
                    ("(reason: token_scope)", "(reason: token_session_only)")
                ), (method, path)
    assert checked > 150
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_before


def test_no_scope_reaches_review_consent_approval_submission_or_your_facts():
    reachable = {p for scope in service.SCOPES for _, p in service.allowed([scope])}
    for word in ("approve", "consent", "answers", "transition", "cancel", "checkpoint", "code",
                 "package", "profile", "documents", "answer-bank", "account", "drafting",
                 "reconcile", "outcome", "attempts", "form"):  # fmt: skip
        assert not [p for p in reachable if word in p], word
    assert {m for scope in service.SCOPES for m, _ in service.allowed([scope])} == {"GET", "POST"}
    assert service.SCOPES["import:jobs"] == {("POST", "/api/jobs"), ("POST", "/api/jobs/import")}
    assert all(m == "GET" for m, _ in service.SCOPES["read"])


def test_an_import_token_adds_a_job_and_nothing_else(api):
    token = make(api, ["import:jobs"])
    c = bare()
    body = {"url": "https://careers.example.com/imported/1", "title": "Imported"}
    r = c.post("/jobs", headers=bearer(token), json=body)
    assert r.status_code == 201, r.text
    assert c.get("/jobs", headers=bearer(token)).status_code == 403  # import is not read
    assert [j["title"] for j in api.get("/jobs").json()["items"]] == ["Imported"]
    job_id = r.json()["job"]["id"]
    r = c.post("/applications", headers=bearer(token), json={"job_id": job_id})
    assert r.status_code == 403
    assert c.patch(f"/jobs/{job_id}", headers=bearer(token), json={"status": "excluded"}
                   ).status_code == 403  # fmt: skip


def test_session_only_routes_refuse_a_token_even_next_to_a_valid_session(api):
    token = make(api, ["read", "import:jobs"])
    for method, url in (("GET", "/account/tokens"), ("POST", "/account/tokens"),
                        ("GET", "/account/export"), ("GET", "/account/deletion"),
                        ("POST", "/account/delete")):  # fmt: skip
        # api.client still carries a valid session cookie and CSRF token.
        r = api.client.request(method, url, headers=bearer(token) | {"X-CSRF-Token": api.csrf},
                               json={})  # fmt: skip
        assert r.status_code == 403, (method, url)
        assert r.json()["detail"].endswith("(reason: token_session_only)"), (method, url)
    assert api.get("/account/tokens").status_code == 200  # the app itself still can


def test_a_header_never_falls_back_to_the_cookie(api):
    r = api.client.get("/jobs", headers={"Authorization": "Bearer ne_aaaaaaaa_" + "x" * 43})
    assert r.status_code == 401 and r.json()["detail"].endswith("(reason: token_invalid)")
    assert api.client.get("/jobs", headers={"Authorization": "Basic Zm9vOmJhcg=="}
                          ).status_code == 401  # fmt: skip


# ---------------------------------------------------------------------------- tenancy


def test_a_token_reads_its_own_account_only(api, other_api):
    mine = add_job(api, 1)
    theirs = add_job(other_api, 2)
    token = make(api)
    c = bare()
    assert [j["id"] for j in c.get("/jobs", headers=bearer(token)).json()["items"]] == [mine]
    r = c.get(f"/jobs/{theirs}", headers=bearer(token))
    assert r.status_code == 404 and r.json()["detail"] == "Job not found"
    make(other_api, label="theirs")
    their_id = other_api.get("/account/tokens").json()["items"][0]["id"]
    assert api.post(f"/account/tokens/{their_id}/revoke").status_code == 404
    assert other_api.get("/account/tokens").json()["items"][0]["state"] == "active"
    assert [t["label"] for t in api.get("/account/tokens").json()["items"]] == ["laptop"]


# ---------------------------------------------------------------------------- expiry, revocation


def test_expired_revoked_and_unknown_tokens_read_the_same(api):
    expired, revoked = make(api, label="old"), make(api, label="gone")
    with SessionLocal() as db:  # simulated: the expiry time moved into the past
        db.execute(update(ApiToken).where(ApiToken.public_id == expired[3:11])
                   .values(expires_at=utcnow() - timedelta(seconds=1)))  # fmt: skip
        db.commit()
    rid = next(t["id"] for t in api.get("/account/tokens").json()["items"] if t["label"] == "gone")
    c = bare()
    assert c.get("/jobs", headers=bearer(revoked)).status_code == 200
    assert api.post(f"/account/tokens/{rid}/revoke").json()["state"] == "revoked"
    unknown = "ne_zzzzzzzz_" + "A" * 43
    active = make(api, label="live")
    # An active token's public id with another secret: the hash decides, not the id.
    tampered = active[:12] + ("A" if active[12] != "A" else "B") + active[13:]
    assert c.get("/jobs", headers=bearer(active)).status_code == 200
    bodies = set()
    for t in (expired, revoked, unknown, tampered, "ne_short", "x"):
        r = c.get("/jobs", headers=bearer(t))
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", t
        bodies.add(r.text)
    assert len(bodies) == 1  # nothing says which tokens exist
    states = {t["label"]: t["state"] for t in api.get("/account/tokens").json()["items"]}
    assert states == {"old": "expired", "gone": "revoked", "live": "active"}


def test_a_token_is_never_read_from_a_query_string_or_a_cookie(api):
    token = make(api)
    c = bare()
    assert c.get(f"/jobs?token={token}").status_code == 401
    assert c.get(f"/jobs?access_token={token}").status_code == 401
    c.cookies.set("ne_session", token)
    assert c.get("/jobs").status_code == 401


def test_failed_tokens_are_rate_limited_per_client(api):
    c = bare()
    codes = [c.get("/jobs", headers=bearer("ne_zzzzzzzz_" + "B" * 43)).status_code
             for _ in range(12)]  # fmt: skip
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    detail = c.get("/jobs", headers=bearer("x")).json()["detail"]
    assert detail.endswith("(reason: token_rate_limited)")


def test_last_used_is_kept_to_the_hour(api):
    token = make(api)
    c = bare()
    c.get("/jobs", headers=bearer(token))
    (first,) = [t["last_used_at"] for t in api.get("/account/tokens").json()["items"]]
    assert first is not None and first.endswith(("00:00Z", "00:00+00:00"))
    c.get("/jobs", headers=bearer(token))
    assert [t["last_used_at"] for t in api.get("/account/tokens").json()["items"]] == [first]


# ---------------------------------------------------------------------------- logs, export, delete


def test_no_log_line_carries_a_token(api, caplog):
    caplog.set_level(logging.DEBUG)
    token = make(api)
    c = bare()
    c.get("/jobs", headers=bearer(token))
    c.post("/jobs", headers=bearer(token), json={})
    c.get("/jobs", headers=bearer(token + "x"))
    c.get(f"/jobs/{uuid.uuid4()}", headers=bearer(token))
    text = "\n".join(f"{r.name} {r.getMessage()} {r.args}" for r in caplog.records)
    assert token not in text and token[12:] not in text and "Bearer" not in text


def test_tokens_are_exported_without_their_hash_and_deleted_with_the_account(api):
    token = make(api)
    z = zipfile.ZipFile(io.BytesIO(api.get("/account/export").content))
    data = json.loads(z.read("noefforts-export.json"))
    (row,) = data["tables"]["api_tokens"]
    assert row["public_id"] == token[3:11] and "secret_hash" not in row
    assert data["left_out"]["columns"]["api_tokens"] == {
        "secret_hash": "an API token's hash: a login secret"
    }
    confirm = {"password": "correct-horse-1", "confirmation": "delete my account"}
    assert api.post("/account/delete", json=confirm).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApiToken)) == 0
    assert bare().get("/jobs", headers=bearer(token)).status_code == 401


def test_the_docs_list_exactly_the_refusal_codes():
    doc = (ROOT / "docs/api-tokens.md").read_text()
    listed = set(re.findall(r"^\| `(token_[a-z_]+)` \|", doc, re.M))
    assert listed == set(service.REASONS)


# ---------------------------------------------------------------------------- CLI and MCP


def _send(client: TestClient):
    def send(method, url, headers, body):
        r = client.request(method, url.split("/api", 1)[1], headers=headers, content=body)
        return r.status_code, r.content

    return send


def run_cli(argv, env, client=None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    rc = cli.main(argv, env=env, send=_send(client or bare()), out=out, err=err)
    return rc, out.getvalue(), err.getvalue()


def test_the_cli_reads_and_imports_within_its_token_and_never_prints_it(api, tmp_path):
    job_id = add_job(api)
    read = make(api)
    env = {"NOEFFORTS_TOKEN": read}
    rc, out, err = run_cli(["jobs"], env)
    assert rc == 0 and json.loads(out)["items"][0]["id"] == job_id
    rc, out, _ = run_cli(["job", job_id], env)
    assert rc == 0 and json.loads(out)["fit"]["eligibility"] == []
    rc, out, err = run_cli(["import-job", "https://careers.example.com/cli/1"], env)
    assert rc == 1 and "HTTP 403" in err and "token_scope" in err
    rc, _, err = run_cli(["job", "../account/export"], env)
    assert rc == 1 and "UUID" in err  # never put in a path
    imp = make(api, ["import:jobs"], label="importer")
    rc, out, _ = run_cli(["import-job", "https://careers.example.com/cli/1", "--title", "CLI"],
                         {"NOEFFORTS_TOKEN": imp})  # fmt: skip
    assert rc == 0 and json.loads(out)["job"]["title"] == "CLI"
    for text in (out, err):
        assert read not in text and imp not in text
    # A token file must be yours only; the token is never an argument.
    f = tmp_path / "token"
    f.write_text(read)
    f.chmod(0o644)
    rc, _, err = run_cli(["--token-file", str(f), "jobs"], {})
    assert rc == 1 and "chmod 600" in err
    f.chmod(0o600)
    assert run_cli(["--token-file", str(f), "jobs"], {})[0] == 0
    for argv in (["--token", read, "jobs"], ["--token-f", read, "jobs"], ["jobs", read]):
        err = io.StringIO()
        with pytest.raises(SystemExit), __import__("contextlib").redirect_stderr(err):
            cli.parser().parse_args(argv)
        assert read not in err.getvalue() and "see --help" in err.getvalue()
    rc, _, err = run_cli(["--token-file", read, "jobs"], {})  # a token where a path belongs
    assert rc == 1 and read not in err and "Cannot read the token file" in err
    assert not [a for a in cli.parser()._actions if "token" in a.dest and a.dest != "token_file"]


@pytest.mark.parametrize(
    "url, ok",
    [
        ("http://127.0.0.1:8000/api", True),
        ("http://localhost:8000/api", True),
        ("https://noefforts.example.com/api", True),
        ("http://noefforts.example.com/api", False),  # a token in clear text over a network
        ("http://user:pw@127.0.0.1/api", False),
        ("file:///etc/passwd", False),
    ],
)
def test_the_cli_sends_a_token_in_clear_text_to_this_machine_only(url, ok):
    if ok:
        assert cli.api_base(url) == url
    else:
        with pytest.raises(cli.CliError):
            cli.api_base(url)


def mcp_session(token: str, *messages) -> list[dict]:
    lines = "\n".join(json.dumps(m) for m in messages) + "\n"
    out = io.StringIO()
    server = mcp.Server(cli.Client("http://127.0.0.1:8000/api", token, _send(bare())))
    mcp.serve(server, io.StringIO(lines), out)
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_the_mcp_server_offers_read_tools_and_never_a_way_to_apply(api):
    job_id = add_job(api)
    token = make(api)
    init, listed, called, refused, notify_ok = mcp_session(
        token,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_jobs", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "import_job", "arguments": {"url": "https://x.example.com/1"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
    )  # fmt: skip
    assert init["result"]["serverInfo"]["name"] == "noefforts"
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {"list_jobs", "get_job", "list_applications", "get_application",
                     "list_notifications"}  # fmt: skip
    for word in ("submit", "approve", "answer", "consent", "queue", "code", "apply"):
        assert not [n for n in names if word in n], word
    assert json.loads(called["result"]["content"][0]["text"])["items"][0]["id"] == job_id
    assert refused["error"]["code"] == -32602  # not offered to a read token, so refused
    assert notify_ok["result"] == {}
    (imported,) = [m for m in mcp_session(
        make(api, ["read", "import:jobs"], label="both"),
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )]  # fmt: skip
    assert "import_job" in {t["name"] for t in imported["result"]["tools"]}


def test_the_mcp_server_refuses_bad_ids_and_arguments(api):
    token = make(api)
    bad_id, bad_args, unknown = mcp_session(
        token,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "get_job", "arguments": {"job_id": "../account/export"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "get_job", "arguments": ["x"]}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
    )  # fmt: skip
    assert bad_id["result"]["isError"] and "UUID" in bad_id["result"]["content"][0]["text"]
    assert bad_args["error"]["code"] == -32602 and unknown["error"]["code"] == -32601


# ---------------------------------------------------------------------------- a real server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_against_a_real_server_the_cli_and_mcp_work_and_no_output_shows_the_token():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=BACKEND, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )  # fmt: skip
    base = f"http://127.0.0.1:{port}/api"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(CookieJar())
    )

    def post(path, body, headers=None):
        h = {"Content-Type": "application/json"} | (headers or {})
        req = urllib.request.Request(base + path, json.dumps(body).encode(), h, method="POST")
        with opener.open(req, timeout=10) as r:
            return json.loads(r.read())

    try:
        for _ in range(150):
            try:
                opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        csrf = post("/auth/register", {"email": "real.token@example.com",
                                       "password": "correct-horse-1"})["csrf_token"]  # fmt: skip
        h = {"X-CSRF-Token": csrf}
        post("/jobs", {"url": "https://careers.example.com/real/1", "title": "Real Server"}, h)
        token = post("/account/tokens", {"label": "real", "scopes": ["read"]}, h)["token"]
        env = os.environ | {"NOEFFORTS_TOKEN": token, "NOEFFORTS_API": base}
        r = subprocess.run([sys.executable, str(ROOT / "scripts/noefforts.py"), "jobs"],
                           env=env, capture_output=True, text=True, timeout=30)  # fmt: skip
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["items"][0]["title"] == "Real Server"
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "list_applications", "arguments": {}}}]  # fmt: skip
        m = subprocess.run([sys.executable, str(ROOT / "scripts/noefforts_mcp.py")], env=env,
                           input="\n".join(json.dumps(x) for x in msgs) + "\n",
                           capture_output=True, text=True, timeout=30)  # fmt: skip
        replies = [json.loads(x) for x in m.stdout.splitlines()]
        assert replies[1]["result"]["isError"] is False, m.stderr
        for out in (r.stdout, r.stderr, m.stdout, m.stderr):
            assert token not in out
    finally:
        proc.terminate()
        logs = proc.communicate(timeout=10)[0]
    assert "GET /api/jobs" in logs  # the access line, by route template
    assert token not in logs and token[12:] not in logs and "Bearer" not in logs
