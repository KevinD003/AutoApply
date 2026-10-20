"""Container-mode browser path without Docker: the real egress-proxy service and the real
browser-runner launcher (browser/launcher.js, Chromium sandbox on, unprivileged user) run as
local processes, and the worker reaches them exactly as it does in Compose. The network
separation itself (no route from the browser except the proxy) needs containers and is tested
by the Compose execution test (scripts/compose-execution-test.sh)."""

import asyncio
import base64
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import playwright
import pytest

from app.core.config import get_settings
from app.modules.execution import browser as browser_mod
from app.modules.execution import runner
from app.modules.execution.browser import (
    IsolationUnavailable,
    RemoteBrowser,
    browser_session,
    control_request,
)
from app.modules.execution.sandbox import proxy_service
from tests.execution_harness import (
    BASE,
    ROOT,
    Receiver,
    attempt,
    prepared_application,
    queue,
)

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
    proxy_port, runner_port = free_port(), free_port()
    control_dir = tempfile.mkdtemp(prefix="egress-control-")
    control_socket = os.path.join(control_dir, "control.sock")
    loop = asyncio.new_event_loop()

    def run_proxy():
        asyncio.set_event_loop(loop)
        loop.create_task(proxy_service.serve(proxy_port, control_socket, CONTROL_TOKEN, 300))
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
        "MAX_SESSIONS": "1",
        "CONNECT_SECONDS": "10",
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
        "control_socket": control_socket,
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
    monkeypatch.setattr(s, "egress_control_socket", stack["control_socket"])
    monkeypatch.setattr(s, "egress_control_token", CONTROL_TOKEN)
    return stack


def ctl(stack, method, path, body=None, token=CONTROL_TOKEN):
    return control_request(stack["control_socket"], token, method, path, body)


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
    assert ctl(stack, "POST", "/sessions", {"allow": [["a", 1]]}, token="")[0] == 401
    assert ctl(stack, "POST", "/sessions", {"allow": [["a", 1]]}, token="x" * 28)[0] == 401


def test_proxy_requires_a_session_and_keeps_sessions_apart(stack, receiver):
    def raw(req: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", stack["proxy_port"]), timeout=10) as c:
            c.sendall(req)
            return c.recv(200)

    a = ctl(
        stack,
        "POST",
        "/sessions",
        {"allow": [["127.0.0.1", 8799]], "allow_private": [["127.0.0.1", 8799]]},
    )[1]
    b = ctl(
        stack,
        "POST",
        "/sessions",
        {"allow": [["127.0.0.1", 8798]], "allow_private": [["127.0.0.1", 8798]]},
    )[1]
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
    r = ctl(stack, "POST", "/sessions", {"allow": [["a", 1]], "allow_private": [["10.0.0.1", 80]]})
    assert r[0] == 400


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
        c.srv.server_close()  # release port 8798 for the next canary
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


# Run in a separate process, as another worker would be.
TRY_CONNECT = """
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    try:
        p.chromium.connect(sys.argv[1], timeout=5000, headers={"X-Runner-Token": sys.argv[2]})
        print("connected")
    except Exception as e:
        print("refused", str(e).splitlines()[0][:200])
"""

# A worker that dies without closing anything (os._exit skips all cleanup).
CONNECT_THEN_DIE = """
import os, sys
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect(sys.argv[1], timeout=10000, headers={"X-Runner-Token": sys.argv[2]})
b.new_context().new_page()
print("connected", flush=True)
os._exit(9)
"""


def _sessions(stack) -> int:
    return httpx.get(f"{stack['runner']}/health").json()["sessions"]


def _wait_sessions(stack, n: int, timeout=15.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if _sessions(stack) == n:
            return True
        time.sleep(0.2)
    return False


def test_control_channel_is_single_use_and_authenticated(container_mode):
    remote = RemoteBrowser("127.0.0.1", 8799, True)
    ws = remote.open()
    try:
        # The browser's own server is on the runner's loopback; the endpoint handed out is
        # the runner's relay, and it needs the runner token as well as the session secret.
        assert ws.startswith(f"ws://127.0.0.1:{container_mode['runner'].rsplit(':', 1)[1]}/")

        def try_connect(endpoint, token):
            r = subprocess.run(
                [sys.executable, "-c", TRY_CONNECT, endpoint, token],
                capture_output=True,
                timeout=60,
            )
            return r.stdout.decode().strip()

        assert try_connect(ws, "wrong-token-0123456789").startswith("refused")
        assert try_connect(ws[:-4] + "0000", RUNNER_TOKEN).startswith("refused")
        assert _sessions(container_mode) == 1  # failed tries did not use up the session
        with browser_mod.sync_playwright() as p:
            b = p.chromium.connect(ws, timeout=10_000, headers={"X-Runner-Token": RUNNER_TOKEN})
            assert b.new_context().new_page().evaluate("1 + 1") == 2
            # A second controller (e.g. a stale worker) cannot attach to the same browser.
            assert try_connect(ws, RUNNER_TOKEN).startswith("refused")
    finally:
        remote.close()
    assert _wait_sessions(container_mode, 0)


def test_hard_killed_controller_leaves_no_browser(container_mode):
    """A worker that dies without cleaning up: the runner closes the browser itself, so no page
    is left for anyone to drive later."""
    remote = RemoteBrowser("127.0.0.1", 8799, True)
    ws = remote.open()
    r = subprocess.run(
        [sys.executable, "-c", CONNECT_THEN_DIE, ws, RUNNER_TOKEN], capture_output=True, timeout=60
    )
    assert b"connected" in r.stdout, r.stderr[-500:]
    assert _wait_sessions(container_mode, 0), "browser left running after its controller died"
    remote.proxy_session and remote._proxy("DELETE", f"/sessions/{remote.proxy_session['id']}")


def test_unused_session_expires(container_mode):
    remote = RemoteBrowser("127.0.0.1", 8799, True)
    remote.open()  # never connected
    assert _sessions(container_mode) == 1
    assert _wait_sessions(container_mode, 0, timeout=20)
    remote.close()


def test_busy_runner_waits_then_refuses(container_mode, monkeypatch):
    monkeypatch.setattr(get_settings(), "browser_slot_wait_seconds", 2)
    first = RemoteBrowser("127.0.0.1", 8799, True)
    first.open()
    second = RemoteBrowser("127.0.0.1", 8799, True)
    try:
        t0 = time.monotonic()
        with pytest.raises(IsolationUnavailable, match="429"):
            second.open()
        assert time.monotonic() - t0 >= 2
    finally:
        second.close()
        first.close()
    assert _wait_sessions(container_mode, 0)


def test_driver_version_mismatch_is_refused_with_reason(container_mode, api, receiver, monkeypatch):
    monkeypatch.setattr(browser_mod, "local_driver_version", lambda: "0.0.0")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "does not match" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_container_boundary_alone_blocks_egress_without_interception(container_mode, receiver):
    """In-process route interception off: only the runner's launch settings and the session
    proxy stand between a hostile page and everything else."""
    hits = []

    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8798), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        receiver.config(mode="hostile", canary="http://127.0.0.1:8798")
        with browser_session(
            BASE, 15000, isolation="container", intercept=False, allow_private_destination=True
        ) as (page, log):
            page.goto(f"{BASE}/apply/clinic")
            assert "SYNTHETIC" in page.title()  # the allowed destination works
            page.evaluate("""async () => {
                for (const u of ['http://127.0.0.1:8798/direct-fetch', 'http://127.0.0.1:5432/',
                                 'http://127.0.0.1:6379/', 'http://169.254.169.254/latest/',
                                 'https://example.com/', 'http://[::1]:8798/']) {
                  try { await fetch(u, {mode: 'no-cors'}); } catch (e) {}
                }
                try { new WebSocket('ws://127.0.0.1:8798/ws'); } catch (e) {}
                await new Promise(r => setTimeout(r, 1500)); }""")
            denied = log.proxy_denied()
    finally:
        srv.shutdown()
        srv.server_close()
    assert hits == [], hits
    assert {"127.0.0.1:8798", "127.0.0.1:5432", "127.0.0.1:6379", "169.254.169.254:80"} <= set(
        denied
    ), denied


def test_interception_cannot_be_disabled_outside_test_environments(
    container_mode, api, receiver, monkeypatch
):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    s = get_settings()
    monkeypatch.setattr(s, "execution_test_disable_interception", True)
    monkeypatch.setattr(s, "env", "production")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "cannot be disabled" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == []


@pytest.mark.skipif(
    os.geteuid() != 0 or not shutil.which("unshare") or not shutil.which("setpriv"),
    reason="needs root to start the runner as PID 1 of its own PID namespace; the Compose "
    "execution test covers the same case in CI (the runner is PID 1 in its container)",
)
def test_self_check_finds_its_browsers_when_the_runner_is_pid_1():
    """Regression (CI #21): as PID 1 the self-check's ancestry walk never matched, found no
    browser processes, and the runner refused every session."""
    port = free_port()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "DRIVER_PACKAGE": str(DRIVER / "package"),
        "RUNNER_TOKEN": RUNNER_TOKEN,
        "EGRESS_PROXY": "http://127.0.0.1:9",
        "RUNNER_PORT": str(port),
        "RUNNER_PUBLIC_HOST": "127.0.0.1",
    }
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    cmd = [
        "unshare",
        "-p",
        "-f",
        "--mount-proc",
        "setpriv",
        "--reuid=65534",
        "--regid=65534",
    ]
    cmd += ["--clear-groups", str(DRIVER / "node"), str(ROOT / "browser" / "launcher.js")]
    proc = subprocess.Popen(
        cmd, env=env, cwd="/tmp", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        health = None
        for _ in range(120):
            try:
                health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).json()
                break
            except httpx.HTTPError:
                time.sleep(0.25)
        assert health and health["sandbox_ok"] is True, health
    finally:
        # Stop the namespace's PID 1 (the runner; its exit ends everything inside), then
        # unshare exits. (unshare --kill-child cannot do it: the parent-death signal is
        # cleared when setpriv changes the user.)
        task = f"/proc/{proc.pid}/task/{proc.pid}/children"
        for child in open(task).read().split() if os.path.exists(task) else []:
            os.kill(int(child), 15)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_control_api_is_an_owner_only_unix_socket_not_a_network_listener(stack):
    """The worker manages its own sessions over the socket; the token is still required; the
    proxy opens no TCP listener for control (its only TCP port is the browser-facing proxy)."""
    import stat

    st = os.stat(stack["control_socket"])
    assert stat.S_ISSOCK(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600
    code, made = ctl(stack, "POST", "/sessions", {"allow": [["127.0.0.1", 8799]]})
    assert code == 201
    assert ctl(stack, "GET", f"/sessions/{made['id']}/decisions")[0] == 200
    assert ctl(stack, "GET", f"/sessions/{made['id']}/decisions", token="")[0] == 401
    assert ctl(stack, "DELETE", f"/sessions/{made['id']}")[0] == 200
    assert ctl(stack, "GET", f"/sessions/{made['id']}/decisions")[0] == 404
    # No TCP socket of this process listens anywhere except the proxy port (and test servers
    # that are not part of the proxy service).
    from app.modules.execution.sandbox import proxy_service as ps

    assert "ThreadingHTTPServer" not in vars(ps), "control must not be a TCP HTTP server"


def test_restart_replaces_a_stale_control_socket(tmp_path):
    from app.modules.execution.sandbox.proxy_service import Registry, control_server

    path = str(tmp_path / "control.sock")
    first = control_server(path, Registry(60), CONTROL_TOKEN)
    first.server_close()  # simulates a killed proxy: the socket file is left behind
    assert os.path.exists(path)
    second = control_server(path, Registry(60), CONTROL_TOKEN)  # a restart must not fail
    threading.Thread(target=second.serve_forever, daemon=True).start()
    try:
        assert control_request(path, CONTROL_TOKEN, "GET", "/health")[0] == 200
        # the new registry knows no sessions from before the restart
        assert (
            control_request(path, CONTROL_TOKEN, "GET", "/sessions/0123456789abcdef/decisions")[0]
            == 404
        )
    finally:
        second.shutdown()
        second.server_close()


def test_browser_lost_after_disclosure_is_abandoned_not_retried(
    container_mode, api, receiver, monkeypatch
):
    """The runner (or its browser) goes away after the form was filled: the attempt is
    classified by its disclosure evidence - abandoned, needs the user - never failed_safe
    (which would claim nothing was sent) and never re-run automatically."""
    from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter

    opened, original_open, original_readback = [], RemoteBrowser.open, FixtureAtsAdapter.readback

    def remember(self):
        opened.append(self)
        return original_open(self)

    def runner_dies_then_readback(self, page):
        for r in opened:  # the runner ends the browser, as on an OOM kill or restart
            httpx.delete(
                f"{container_mode['runner']}/sessions/{r.runner_session['id']}",
                headers={"X-Runner-Token": RUNNER_TOKEN},
            )
        return original_readback(self, page)

    monkeypatch.setattr(RemoteBrowser, "open", remember)
    monkeypatch.setattr(FixtureAtsAdapter, "readback", runner_dies_then_readback)
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    result = runner.run_attempt(aid, "w1")
    att = attempt(aid)
    led = receiver.ledger()
    assert result in ("error", "abandoned") and att.state == "abandoned", (result, att.state)
    assert att.disclosure_started_at is not None and att.retry_count == 0
    assert led["accepted"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    assert runner.run_attempt(aid, "w2") == "ignored"  # a redelivery does not resend
    assert receiver.ledger()["accepted"] == 0


def test_refusals_are_delivered_not_broken_pipes(tmp_path):
    """Regression (CI #26): the control API answered 401 before reading the request body and
    closed, so a client still sending its body got EPIPE instead of the refusal (10 of 500 in
    a local loop before the fix)."""
    from app.modules.execution.sandbox.proxy_service import Registry, control_server

    path = str(tmp_path / "control.sock")
    srv = control_server(path, Registry(60), CONTROL_TOKEN)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = {"allow": [["a", 1]] * 200}  # a body big enough to be sent after the headers
        codes = [control_request(path, "x" * 28, "POST", "/sessions", body)[0] for _ in range(300)]
        assert codes == [401] * 300
    finally:
        srv.shutdown()
        srv.server_close()
