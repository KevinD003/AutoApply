"""Isolated browser sessions.

Network isolation (enforced outside the browser; see sandbox/):
  * Chromium runs in its own network namespace with only a loopback interface: no routes, no
    DNS, no database or broker. Its only way out is a relay to the egress proxy, which allows
    exactly the approved destination host:port and refuses non-public addresses (except an
    explicit test-only fixture exception). Chromium gets a minimal environment: no database
    URL, broker URL, API keys or other credentials.
  * Remaining limit: the filesystem is not isolated (no mount namespace); a compromised
    renderer process could read files the worker user can read. Run workers as a dedicated
    user without access to secrets files, or in a container, before untrusted live browsing.

In-process layers on top (defence in depth):
  * a fresh, non-persistent context per attempt: no shared cookies or storage, no downloads;
  * service workers blocked, so every request goes through routing;
  * every HTTP(S) request and WebSocket to any origin other than the approved destination is
    aborted and counted; non-HTTP schemes are aborted;
  * pop-ups are closed immediately;
  * Chromium's host resolver maps every hostname except the destination host to NOTFOUND.
Production deployments must additionally run browsers in a network namespace whose egress
firewall permits only the destination (see docs/architecture.md). That layer is not
implemented in this repository.
"""

import os
import shutil
import socket
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright


@dataclass
class EgressLog:
    allowed: int = 0
    blocked: list[str] = field(default_factory=list)
    proxy: object | None = None  # EgressProxy when network isolation is active

    def proxy_denied(self) -> list[str]:
        if self.proxy is None:
            return []
        return sorted({f"{d.host}:{d.port}" for d in self.proxy.decisions if not d.allowed})


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower()


class IsolationUnavailable(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _netns_wrapper(workdir: str, sock: str, port: int, chrome: str) -> str:
    """Executable that Playwright launches instead of Chromium: unshare -> netns_boot -> chrome.
    DevTools pipes (fds 3/4) pass through unshare and exec unchanged."""
    if shutil.which("unshare") is None:
        raise IsolationUnavailable("unshare(1) is not installed")
    boot = os.path.join(os.path.dirname(__file__), "sandbox", "netns_boot.py")
    flags = "-n" if os.geteuid() == 0 else "-rn"  # unprivileged: user + network namespace
    path = os.path.join(workdir, "chromium-netns")
    with open(path, "w") as f:
        f.write(
            f'#!/bin/sh\nexec unshare {flags} "{sys.executable}" -I "{boot}" '
            f'"{sock}" {port} "{chrome}" "$@"\n'
        )
    os.chmod(path, 0o700)
    return path


def isolation_self_check() -> None:
    """Fail fast if a network namespace cannot be created here."""
    import subprocess

    flags = ["-n"] if os.geteuid() == 0 else ["-r", "-n"]
    r = subprocess.run(["unshare", *flags, "true"], capture_output=True, timeout=10)
    if r.returncode != 0:
        raise IsolationUnavailable(f"cannot create a network namespace: {r.stderr[:200]!r}")


@contextmanager
def browser_session(
    allowed_origin: str,
    nav_timeout_ms: int,
    *,
    isolation: str = "netns",
    intercept: bool = True,
    allow_private_destination: bool = False,
):
    """`intercept=False` disables the in-process layers; used only by isolation tests to show
    that the namespace + egress proxy alone enforce the policy."""
    from app.modules.execution.sandbox.egress_proxy import EgressProxy

    allowed = allowed_origin.lower().rstrip("/")
    u = urlsplit(allowed)
    host, port = u.hostname or "", u.port or (443 if u.scheme == "https" else 80)
    log = EgressLog()
    args = ["--disable-background-networking", "--no-first-run", "--disable-sync"]
    if intercept:
        args.insert(0, f"--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE {host}")
    with ExitStack() as stack, sync_playwright() as p:
        launch: dict = {"headless": True, "args": args}
        chrome = os.environ.get("PW_CHROMIUM_PATH") or p.chromium.executable_path
        if isolation == "netns":
            workdir = tempfile.mkdtemp(prefix="ne-browser-")
            stack.callback(shutil.rmtree, workdir, True)
            os.chmod(workdir, 0o700)
            sock = os.path.join(workdir, "egress.sock")
            proxy = EgressProxy(
                sock,
                allow={(host, port)},
                allow_private={(host, port)} if allow_private_destination else set(),
            ).start()
            stack.callback(proxy.stop)
            log.proxy = proxy
            launch["executable_path"] = _netns_wrapper(workdir, sock, _free_port(), chrome)
            launch["env"] = {"PATH": "/usr/bin:/bin", "HOME": workdir, "TMPDIR": workdir}
        elif isolation == "off":
            launch["executable_path"] = chrome
        else:
            raise IsolationUnavailable(f"unknown isolation mode {isolation!r}")
        browser = p.chromium.launch(**launch)
        try:
            ctx = browser.new_context(
                service_workers="block" if intercept else "allow", accept_downloads=False
            )
            ctx.set_default_navigation_timeout(nav_timeout_ms)
            ctx.set_default_timeout(nav_timeout_ms)
            if intercept:
                _install_interception(ctx, allowed, log)
            pages = []
            ctx.on("page", lambda pg: pg.close() if pages else pages.append(pg))
            page = ctx.new_page()
            yield page, log
        finally:
            browser.close()  # always: a worker that loses authority closes its browser


def _install_interception(ctx, allowed: str, log: "EgressLog") -> None:
    def route(r):
        url = r.request.url
        if not (url.startswith(("http://", "https://")) and _origin(url) == allowed):
            log.blocked.append(url[:200])
            return r.abort("blockedbyclient")
        # Redirects followed by the browser are not re-intercepted, so fetch without
        # following them and refuse any hop that leaves the allowed origin.
        resp = r.fetch(max_redirects=0)
        loc = resp.headers.get("location")
        if 300 <= resp.status < 400 and loc:
            target = urljoin(url, loc)
            if _origin(target) != allowed:
                log.blocked.append(target[:200])
                return r.abort("blockedbyclient")
        log.allowed += 1
        return r.fulfill(response=resp)

    ctx.route("**/*", route)

    def ws(w):
        if _origin(w.url.replace("ws", "http", 1)) != allowed:
            log.blocked.append(w.url[:200])
            w.close()
        else:
            w.connect_to_server()

    ctx.route_web_socket("**/*", ws)
