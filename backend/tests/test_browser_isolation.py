"""Network isolation for the browser, tested with the in-process interception layer disabled.
Real namespaces, real Chromium, real egress proxy; the canary server counts anything that
gets through."""

import fcntl
import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest
from playwright.sync_api import Error as PlaywrightError

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.execution.browser import (
    IsolationUnavailable,
    _netns_wrapper,
    browser_session,
    hidden_paths,
    isolation_self_check,
)
from app.modules.execution.sandbox.egress_proxy import EgressProxy
from tests.execution_harness import (
    BACKEND,
    BASE,
    Receiver,
    attempt,
    prepared_application,
    queue,
)

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


@pytest.mark.parametrize("breakage", ["unshare_rejects", "unshare_missing"])
def test_isolation_failure_refuses_instead_of_browsing_unrestricted(
    api, receiver, monkeypatch, breakage
):
    """If the namespaces cannot be created, the attempt stops before disclosure; there is no
    fallback to an unisolated browser."""
    from app.modules.execution import browser

    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    if breakage == "unshare_rejects":
        monkeypatch.setattr(browser, "_unshare_flags", lambda: ["--no-such-namespace-flag"])
    else:
        monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "isolation unavailable" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_stale_workdirs_of_dead_workers_are_removed():
    from app.modules.execution.browser import WORKDIR_PREFIX, cleanup_stale_workdirs

    dead = subprocess.Popen(["true"])
    dead.wait()
    gone = tempfile.mkdtemp(prefix=f"{WORKDIR_PREFIX}{dead.pid}-")
    live = tempfile.mkdtemp(prefix=f"{WORKDIR_PREFIX}{os.getpid()}-")
    odd = tempfile.mkdtemp(prefix=f"{WORKDIR_PREFIX}sibling-")
    try:
        assert cleanup_stale_workdirs() >= 1
        assert not os.path.exists(gone)
        assert os.path.exists(live) and os.path.exists(odd)
    finally:
        for d in (gone, live, odd):
            shutil.rmtree(d, ignore_errors=True)


def test_proxy_checks_every_resolved_address_and_connects_to_the_checked_one(monkeypatch):
    """A name that resolves to public and private addresses is refused; an allowed name is
    connected by the exact address that was checked (no second lookup can redirect it)."""
    from app.modules.execution.sandbox import egress_proxy

    answers = {
        "mixed.example": ["93.184.216.34", "10.0.0.5"],
        "public.example": ["93.184.216.34"],
        "meta.example": ["169.254.169.254"],
    }

    def fake_getaddrinfo(host, port, type=0):  # noqa: A002
        return [(2, 1, 6, "", (ip, port)) for ip in answers[host]]

    monkeypatch.setattr(egress_proxy.socket, "getaddrinfo", fake_getaddrinfo)
    p = EgressProxy("/unused", allow={(h, 443) for h in answers})
    assert p.check("mixed.example", 443)[0] is None
    assert p.check("meta.example", 443)[0] is None
    assert p.check("public.example", 443) == ("93.184.216.34", "allowed")
    assert p.check("public.example", 80)[0] is None  # port is part of the allow-list


def test_proxy_connect_and_absolute_http_follow_the_same_policy(receiver):
    """HTTPS goes through CONNECT, plain HTTP as absolute-form requests; both are checked."""
    work = tempfile.mkdtemp(prefix="ne-proxytest-")
    sock_path = os.path.join(work, "p.sock")
    proxy = EgressProxy(
        sock_path, allow={("127.0.0.1", 8799)}, allow_private={("127.0.0.1", 8799)}
    ).start()

    def ask(raw: bytes) -> bytes:
        c = socket.socket(socket.AF_UNIX)
        c.settimeout(10)
        c.connect(sock_path)
        c.sendall(raw)
        data = c.recv(200)
        c.close()
        return data

    try:
        assert ask(b"CONNECT 127.0.0.1:8799 HTTP/1.1\r\nHost: x\r\n\r\n").startswith(
            b"HTTP/1.1 200"
        )
        assert b" 403 " in ask(b"CONNECT 127.0.0.1:8798 HTTP/1.1\r\n\r\n")
        assert b" 403 " in ask(b"CONNECT 127.0.0.1:5432 HTTP/1.1\r\n\r\n")
        ok = ask(b"GET http://127.0.0.1:8799/apply/health-check HTTP/1.1\r\nHost: x\r\n\r\n")
        assert ok.startswith(b"HTTP/1.1 200"), ok
        assert b" 403 " in ask(b"GET http://127.0.0.1:6379/ HTTP/1.1\r\n\r\n")
        assert b" 403 " in ask(b"GET ftp://127.0.0.1:8799/ HTTP/1.1\r\n\r\n")
    finally:
        proxy.stop()
        shutil.rmtree(work, ignore_errors=True)


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


class _SlowPost(http.server.BaseHTTPRequestHandler):
    posts: list[float] = []

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<form method=post action=/submit><input name=a value=1>"
            b"<button id=go>Send</button></form>"
        )

    def do_POST(self):  # noqa: N802
        _SlowPost.posts.append(time.monotonic())
        self.rfile.read(int(self.headers.get("content-length", 0)))
        time.sleep(30)  # accepted; the reply never arrives in time

    def log_message(self, *a):
        pass


@pytest.mark.parametrize("isolation", ["netns", "off"])
def test_closing_the_browser_mid_submit_never_resends(isolation):
    """Found by the browser test (the receiver counted two acceptances for one attempt): a POST
    answered via route.fetch + fulfill was re-sent by Playwright when the browser closed while
    that fetch was still pending or had timed out. The employer must see exactly one POST."""
    _SlowPost.posts = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowPost)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_port}"
    try:
        # Without a proxy ("off") the fixture flag is refused (D86) and would change nothing.
        private = isolation != "off"
        with browser_session(
            origin, 3000, isolation=isolation, allow_private_destination=private
        ) as (page, _log):
            page.goto(origin + "/")
            page.click("#go", no_wait_after=True)
            # Wait the way the adapter does (through Playwright, so route handlers run).
            for _ in range(100):
                if _SlowPost.posts:
                    break
                page.wait_for_timeout(100)
            assert len(_SlowPost.posts) == 1
            page.wait_for_timeout(4000)  # past the 3s timeout; then the worker gives up
        time.sleep(2)  # bounded observation window for a late duplicate
        assert len(_SlowPost.posts) == 1, _SlowPost.posts
    finally:
        srv.shutdown()
        srv.server_close()


PROBE = """#!/bin/sh
# Runs exactly where Chromium would: inside the browser's namespaces.
[ -e "/proc/$1" ] && echo WORKER_VISIBLE || echo worker_hidden
cat "$2/marker" 2>/dev/null | grep -q SYNTHETIC && echo DIR_LEAK || echo dir_hidden
grep -q SYNTHETIC "$3" 2>/dev/null && echo FILE_LEAK || echo file_hidden
[ -e "$4" ] && echo SIBLING_VISIBLE || echo sibling_hidden
umount "$2" 2>/dev/null && echo UMOUNT_OK || echo umount_refused
cat "$2/marker" 2>/dev/null | grep -q SYNTHETIC && echo DIR_LEAK_AFTER_UMOUNT
[ -x "$0" ] && echo own_workdir_visible
echo "procs=$(ls /proc | grep -cE '^[0-9]+$')"
[ -e ./pyproject.toml ] && echo CWD_LEAK || echo cwd_clean
[ -e "/proc/$$/fd/$5" ] && echo FD_LEAK || echo fd_closed
"""


def test_browser_cannot_see_worker_process_secrets_or_other_attempts():
    """Credential separation, checked from inside the browser's namespaces with synthetic
    markers: the worker's /proc entry, hidden directories and files, and another attempt's
    work directory are invisible, and the hiding mounts cannot be undone from inside."""
    secret_dir = tempfile.mkdtemp(prefix="ne-hidden-", dir="/var/tmp")
    secret_file = os.path.join(tempfile.mkdtemp(prefix="ne-hidden-", dir="/var/tmp"), "env")
    sibling = tempfile.mkdtemp(prefix="ne-browser-sibling-")
    work = tempfile.mkdtemp(prefix="ne-browser-")
    try:
        for p in (os.path.join(secret_dir, "marker"), secret_file):
            with open(p, "w") as f:
                f.write("SYNTHETIC-SECRET-MARKER\n")
        probe = os.path.join(work, "probe.sh")
        with open(probe, "w") as f:
            f.write(PROBE)
        os.chmod(probe, 0o700)
        wrapper = _netns_wrapper(
            work, os.path.join(work, "unused.sock"), 9, probe, hide=[secret_dir, secret_file]
        )
        # Started from the worker's own directory with an extra open descriptor, as a
        # careless parent might leave them.
        # (fds 3 and 4 are Chromium's DevTools pipes and pass on purpose; use a higher one.)
        low = os.open(os.path.join(secret_dir, "marker"), os.O_RDONLY)
        leaked = fcntl.fcntl(low, fcntl.F_DUPFD, 20)
        os.close(low)
        try:
            out = subprocess.run(
                [wrapper, str(os.getpid()), secret_dir, secret_file, sibling, str(leaked)],
                capture_output=True,
                text=True,
                timeout=30,
                env={"PATH": "/usr/bin:/bin"},
                cwd=BACKEND,
                pass_fds=(leaked,),
            )
        finally:
            os.close(leaked)
        lines = out.stdout.split()
        assert {
            "worker_hidden",
            "dir_hidden",
            "file_hidden",
            "sibling_hidden",
            "umount_refused",
            "own_workdir_visible",
            "cwd_clean",
            "fd_closed",
        } <= set(lines), (out.stdout, out.stderr)
        assert not {
            "WORKER_VISIBLE",
            "DIR_LEAK",
            "FILE_LEAK",
            "SIBLING_VISIBLE",
            "CWD_LEAK",
            "FD_LEAK",
        } & set(lines)
        assert "DIR_LEAK_AFTER_UMOUNT" not in lines and "UMOUNT_OK" not in lines
        procs = int(next(x for x in lines if x.startswith("procs=")).split("=")[1])
        assert procs <= 5, out.stdout  # only the namespace's own processes
        # Outside, nothing changed.
        with open(os.path.join(secret_dir, "marker")) as f:
            assert "SYNTHETIC" in f.read()
    finally:
        for d in (secret_dir, os.path.dirname(secret_file), sibling, work):
            shutil.rmtree(d, ignore_errors=True)


def test_default_hidden_paths_cover_code_config_and_storage():
    hidden = hidden_paths()
    backend = os.path.realpath(BACKEND)
    assert backend in hidden
    assert os.path.join(os.path.dirname(backend), ".env") in hidden
    assert str(get_settings().storage_dir.resolve()) in hidden
    assert os.path.join(os.path.realpath(os.path.expanduser("~")), ".ssh") in hidden


def test_refuses_a_browser_binary_inside_a_hidden_path():
    work = tempfile.mkdtemp(prefix="ne-browser-")
    try:
        with pytest.raises(IsolationUnavailable):
            _netns_wrapper(work, "/unused", 9, "/var/tmp/x/chrome", hide=["/var/tmp/x"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
