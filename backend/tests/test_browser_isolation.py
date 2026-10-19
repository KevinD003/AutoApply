"""Network isolation for the browser, tested with the in-process interception layer disabled.
Real namespaces, real Chromium, real egress proxy; the canary server counts anything that
gets through."""

import http.server
import os
import socket
import subprocess
import sys
import threading
import time

import pytest
from playwright.sync_api import Error as PlaywrightError

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.execution.browser import browser_session, isolation_self_check
from app.modules.execution.sandbox.egress_proxy import EgressProxy
from tests.execution_harness import BASE, Receiver, attempt, prepared_application, queue

CANARY = 8798


class _Hits(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):  # noqa: N802
        _Hits.hits.append(self.path)
        self.send_response(200)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *a):
        pass


@pytest.fixture
def canary():
    _Hits.hits = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", CANARY), _Hits)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield _Hits.hits
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def test_namespace_can_be_created_here():
    isolation_self_check()


def test_namespace_alone_has_no_network():
    """Inside a fresh namespace, even with loopback up, nothing outside is reachable."""
    probe = (
        "import socket,sys\n"
        "res=[]\n"
        "for host,port in [('127.0.0.1',5432),('127.0.0.1',6379),('127.0.0.1',8799),"
        "('169.254.169.254',80),('1.1.1.1',80)]:\n"
        "    s=socket.socket(); s.settimeout(2)\n"
        "    try: s.connect((host,port)); res.append(f'OPEN {host}:{port}')\n"
        "    except OSError as e: res.append(f'closed {host}:{port}')\n"
        "print(res)\n"
        "try: socket.getaddrinfo('example.com',80); print('DNS OK')\n"
        "except OSError: print('DNS FAIL')\n"
    )
    flags = ["-n"] if os.geteuid() == 0 else ["-rn"]
    out = subprocess.run(
        ["unshare", *flags, sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert "OPEN" not in out and "DNS FAIL" in out, out


def test_proxy_policy_unit():
    p = EgressProxy("/unused", allow={("127.0.0.1", 8799), ("localhost", 9)})
    assert p.check("127.0.0.1", 8799)[0] is None  # loopback needs the fixture exception
    assert p.check("example.com", 443)[0] is None  # not allow-listed
    p2 = EgressProxy("/unused", allow={("127.0.0.1", 8799)}, allow_private={("127.0.0.1", 8799)})
    assert p2.check("127.0.0.1", 8799)[0] == "127.0.0.1"
    assert p2.check("127.0.0.1", 8798)[0] is None  # other port on the same host


def test_isolation_alone_blocks_egress_without_interception(receiver, canary):
    receiver.config(mode="hostile", canary=f"http://127.0.0.1:{CANARY}")
    with browser_session(
        BASE, 15000, isolation="netns", intercept=False, allow_private_destination=True
    ) as (page, log):
        page.goto(f"{BASE}/apply/clinic")
        assert "SYNTHETIC" in page.title()  # allowed destination works
        # In no-cors mode the proxy's 403 is an opaque response, so the page cannot tell
        # blocked from reached; the proxy's decision log and the canary are the evidence.
        page.evaluate("""async () => {
            const out = {};
            for (const u of ['http://127.0.0.1:8798/direct-fetch', 'http://127.0.0.1:5432/',
                             'http://127.0.0.1:6379/', 'http://169.254.169.254/latest/',
                             'https://example.com/', 'http://[::1]:8798/']) {
              try { const r = await fetch(u, {mode: 'no-cors'}); out[u] = 'reached'; }
              catch (e) { out[u] = 'blocked'; }
            }
            return out; }""")
        # Same-origin hops, then off to the canary: the proxy answers 403 for the last hop.
        with pytest.raises(PlaywrightError, match="ERR_HTTP_RESPONSE_CODE_FAILURE"):
            page.goto(f"{BASE}/redirect-chain")
        time.sleep(1)
        chrome_pids = [p for p in os.listdir("/proc") if p.isdigit() and _is_isolated_chrome(p)]
        denied = log.proxy_denied()
    expected = {
        "127.0.0.1:8798",
        "127.0.0.1:5432",
        "127.0.0.1:6379",
        "169.254.169.254:80",
        "10.0.0.1:80",
        "::1:80",
        "::1:8798",
        "example.com:443",
    }
    assert expected <= set(denied), sorted(expected - set(denied))
    assert canary == [], canary
    # Chromium really ran in another network namespace, without our credentials.
    assert chrome_pids, "no isolated Chromium process seen"


def _is_isolated_chrome(pid: str) -> bool:
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read()
        if b"--proxy-server=http://127.0.0.1:" not in cmd:
            return False
        if os.readlink(f"/proc/{pid}/ns/net") == os.readlink("/proc/self/ns/net"):
            return False
        env = open(f"/proc/{pid}/environ", "rb").read()
        return b"NOEFFORTS_DATABASE_URL" not in env and b"NOEFFORTS_REDIS_URL" not in env
    except OSError:
        return False


def test_loopback_destination_denied_without_fixture_exception(receiver):
    with browser_session(
        BASE, 8000, isolation="netns", intercept=False, allow_private_destination=False
    ) as (page, log):
        with pytest.raises(PlaywrightError, match="ERR_"):
            page.goto(f"{BASE}/apply/clinic")
        assert "127.0.0.1:8799" in log.proxy_denied()


def test_production_refuses_to_run_without_isolation(api, receiver, monkeypatch):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    s = get_settings()
    monkeypatch.setattr(s, "browser_isolation", "off")
    monkeypatch.setattr(s, "env", "production")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "isolation is required" in attempt(aid).outcome_detail
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_full_run_goes_through_the_proxy(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert get_settings().browser_isolation == "netns"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_free_port_helper_is_not_reachable_from_namespace():
    # Sanity: a port bound in the host namespace is invisible from a new namespace.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        flags = ["-n"] if os.geteuid() == 0 else ["-rn"]
        code = (
            f"import socket;s=socket.socket();s.settimeout(1)\n"
            f"try: s.connect(('127.0.0.1',{port}));print('OPEN')\n"
            f"except OSError: print('closed')"
        )
        out = subprocess.run(
            ["unshare", *flags, sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
        assert "closed" in out
