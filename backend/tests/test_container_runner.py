"""Container-mode browser path without Docker: the real egress-proxy service and the real
browser-runner launcher (browser/launcher.js, Chromium sandbox on, unprivileged user) run as
local processes, and the worker reaches them exactly as it does in Compose. The network
separation itself (no route from the browser except the proxy) needs containers and is tested
by the Compose execution test (scripts/compose-execution-test.sh)."""

import asyncio
import base64
import os
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import playwright
import pytest

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.execution.sandbox import proxy_service
from tests.execution_harness import ROOT, Receiver, attempt, prepared_application, queue

CONTROL_TOKEN = "test-control-token-0123456789"
RUNNER_TOKEN = "test-runner-token-0123456789"
DRIVER = Path(playwright.__file__).parent / "driver"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.fixture(scope="module")
def stack():
    proxy_port, control_port, runner_port = free_port(), free_port(), free_port()
    loop = asyncio.new_event_loop()

    def run_proxy():
        asyncio.set_event_loop(loop)
        loop.create_task(proxy_service.serve(proxy_port, control_port, CONTROL_TOKEN, 300))
        loop.run_forever()

    t = threading.Thread(target=run_proxy, daemon=True)
    t.start()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "DRIVER_PACKAGE": str(DRIVER / "package"),
        "RUNNER_TOKEN": RUNNER_TOKEN,
        "EGRESS_PROXY": f"http://127.0.0.1:{proxy_port}",
        "RUNNER_PORT": str(runner_port),
        "RUNNER_PUBLIC_HOST": "127.0.0.1",
        "MAX_SESSIONS": "2",
        "MAX_SESSION_SECONDS": "60",
    }
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    elif os.geteuid() != 0:
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(Path.home() / ".cache" / "ms-playwright")
    cmd = [str(DRIVER / "node"), str(ROOT / "browser" / "launcher.js")]
    if os.geteuid() == 0:  # the runner refuses root, as it must; use an unprivileged user
        envs = " ".join(f"{k}={v}" for k, v in env.items())
        inner = f"cd /tmp && exec env -i {envs} {' '.join(cmd)}"
        cmd = ["su", "nobody", "-s", "/bin/sh", "-c", inner]
        env = None
    log = open(tempfile.mktemp(prefix="launcher-", suffix=".log"), "w")  # noqa: SIM115
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{runner_port}"
    for _ in range(120):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code in (200, 503):
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    yield {
        "runner": url,
        "control": f"http://127.0.0.1:{control_port}",
        "proxy_port": proxy_port,
    }
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    loop.call_soon_threadsafe(loop.stop)
    log.close()


@pytest.fixture
def container_mode(stack, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "browser_isolation", "container")
    monkeypatch.setattr(s, "browser_runner_url", stack["runner"])
    monkeypatch.setattr(s, "browser_runner_token", RUNNER_TOKEN)
    monkeypatch.setattr(s, "egress_control_url", stack["control"])
    monkeypatch.setattr(s, "egress_control_token", CONTROL_TOKEN)
    return stack


def test_runner_verified_its_own_sandbox(stack):
    h = httpx.get(f"{stack['runner']}/health").json()
    assert h["sandbox_ok"] is True, h
    r = httpx.get(f"{stack['runner']}/selfcheck", headers={"X-Runner-Token": RUNNER_TOKEN}).json()
    renderers = [p for p in r["processes"] if p["type"] == "renderer"]
    assert renderers and all(p["seccomp"] == "2" for p in renderers)
    assert not any(p["no_sandbox_flag"] for p in r["processes"])
    assert r["runner_uid"] != 0 and all(p["uid"] != 0 for p in r["processes"])


def test_runner_and_proxy_control_need_their_tokens(stack):
    assert httpx.post(f"{stack['runner']}/sessions", json={}).status_code == 401
    bad = {"X-Runner-Token": "x" * len(RUNNER_TOKEN)}
    assert httpx.post(f"{stack['runner']}/sessions", json={}, headers=bad).status_code == 401
    assert httpx.post(f"{stack['control']}/sessions", json={"allow": [["a", 1]]}).status_code == 401


def test_proxy_requires_a_session_and_keeps_sessions_apart(stack, receiver):
    def raw(req: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", stack["proxy_port"]), timeout=10) as c:
            c.sendall(req)
            return c.recv(200)

    h = {"X-Control-Token": CONTROL_TOKEN}
    a = httpx.post(
        f"{stack['control']}/sessions",
        headers=h,
        json={"allow": [["127.0.0.1", 8799]], "allow_private": [["127.0.0.1", 8799]]},
    ).json()
    b = httpx.post(
        f"{stack['control']}/sessions",
        headers=h,
        json={"allow": [["127.0.0.1", 8798]], "allow_private": [["127.0.0.1", 8798]]},
    ).json()
    assert raw(b"CONNECT 127.0.0.1:8799 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 407")
    auth_a = base64.b64encode(f"{a['id']}:{a['token']}".encode())
    auth_b = base64.b64encode(f"{b['id']}:{b['token']}".encode())
    ok = raw(
        b"CONNECT 127.0.0.1:8799 HTTP/1.1\r\nProxy-Authorization: Basic " + auth_a + b"\r\n\r\n"
    )
    assert ok.startswith(b"HTTP/1.1 200"), ok
    # B's credentials do not open A's destination, and a wrong token is not a session.
    connect = b"CONNECT 127.0.0.1:8799 HTTP/1.1\r\nProxy-Authorization: Basic "
    denied = raw(connect + auth_b + b"\r\n\r\n")
    assert b" 403 " in denied
    forged = base64.b64encode(f"{a['id']}:wrong".encode())
    assert raw(
        b"CONNECT 127.0.0.1:8799 HTTP/1.1\r\nProxy-Authorization: Basic " + forged + b"\r\n\r\n"
    ).startswith(b"HTTP/1.1 407")
    # An allow-list can only name a few destinations, and private ones only if also allowed.
    r = httpx.post(
        f"{stack['control']}/sessions",
        headers=h,
        json={"allow": [["a", 1]], "allow_private": [["10.0.0.1", 80]]},
    )
    assert r.status_code == 400


def test_container_mode_full_run(container_mode, api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    # The runner's session is closed afterwards.
    assert httpx.get(f"{container_mode['runner']}/health").json()["sessions"] == 0


def test_container_mode_hostile_page_reaches_nothing_else(container_mode, api, receiver):
    hits = []

    class Canary(threading.Thread):
        def run(self):
            import http.server

            class H(http.server.BaseHTTPRequestHandler):
                def do_GET(self):  # noqa: N802
                    hits.append(self.path)
                    self.send_response(200)
                    self.end_headers()

                do_POST = do_GET

                def log_message(self, *a):
                    pass

            self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8798), H)
            self.srv.serve_forever()

    c = Canary(daemon=True)
    c.start()
    try:
        receiver.config(mode="hostile", canary="http://127.0.0.1:8798")
        app_id = prepared_application(api, receiver)
        aid = queue(api, app_id)
        assert runner.run_attempt(aid, "w1") == "confirmed"
        att = api.get(f"/applications/{app_id}/attempts").json()[0]
        eg = next(e for e in att["evidence"] if e["kind"] == "egress")["data"]
        assert hits == [], hits
        assert eg["blocked_requests"] >= 1
    finally:
        c.srv.shutdown()
    assert receiver.ledger()["accepted"] == 1


def test_container_mode_fails_closed_when_the_runner_is_unavailable(
    container_mode, api, receiver, monkeypatch
):
    monkeypatch.setattr(get_settings(), "browser_runner_url", f"http://127.0.0.1:{free_port()}")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "isolation unavailable" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
