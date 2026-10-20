"""Isolated browser sessions.

Network isolation (enforced outside the browser; see sandbox/):
  * Chromium runs in its own network namespace with only a loopback interface: no routes, no
    DNS, no database or broker. Its only way out is a relay to the egress proxy, which allows
    exactly the approved destination host:port and refuses non-public addresses (except an
    explicit test-only fixture exception).
  * Separation from the orchestrator's credentials: a minimal environment (no database URL,
    broker URL, API keys); its own PID namespace and /proc, so the worker's process and
    environment are invisible; its own mount namespace in which the backend code, `.env`,
    storage directory, common credential files in $HOME and every other attempt's work
    directory under /tmp are hidden; and a nested user namespace so those mounts are locked.
  * Remaining limit: hiding is a deny-list on a shared filesystem under the same OS user.
    Production must run browser workers as a dedicated user, in a container that mounts no
    secrets, before untrusted live browsing.

In-process layers on top (defence in depth):
  * a fresh, non-persistent context per attempt: no shared cookies or storage, no downloads;
  * service workers blocked, so every request goes through routing;
  * every HTTP(S) request and WebSocket to any origin other than the approved destination is
    aborted and counted; non-HTTP schemes are aborted;
  * pop-ups are closed immediately;
  * Chromium's host resolver maps every hostname except the destination host to NOTFOUND.
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


def _unshare_flags() -> list[str]:
    # Network + PID (fresh /proc) + mount namespaces; unprivileged workers add a user namespace.
    # --kill-child: if unshare dies, the namespace's processes die with it.
    flags = ["-n", "-p", "-f", "--mount-proc", "--kill-child"]
    return flags if os.geteuid() == 0 else ["-r", *flags]


_HOME_SECRETS = (
    ".ssh",
    ".aws",
    ".azure",
    ".config",
    ".docker",
    ".kube",
    ".gnupg",
    ".git-credentials",
    ".gitconfig",
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
)


def hidden_paths() -> list[str]:
    """What the browser must not see: our code and configuration, stored user data, and the
    usual credential files of the OS user the worker runs as."""
    from app.core.config import get_settings

    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    home = os.path.expanduser("~")
    paths = [
        backend,
        os.path.join(os.path.dirname(backend), ".env"),
        str(get_settings().storage_dir.resolve()),
        "/run/secrets",
        *(os.path.join(home, n) for n in _HOME_SECRETS),
    ]
    return [os.path.realpath(p) for p in paths]


def _netns_wrapper(
    workdir: str, sock: str, port: int, chrome: str, hide: list[str] | None = None
) -> str:
    """Executable that Playwright launches instead of Chromium: unshare -> netns_boot -> chrome.
    DevTools pipes (fds 3/4) pass through unshare and exec unchanged."""
    if shutil.which("unshare") is None:
        raise IsolationUnavailable("unshare(1) is not installed")
    boot = os.path.join(os.path.dirname(__file__), "sandbox", "netns_boot.py")
    hide = hidden_paths() if hide is None else hide
    if any(os.path.commonpath([h, os.path.realpath(chrome)]) == h for h in hide):
        raise IsolationUnavailable("the browser binary lies inside a hidden path")
    path = os.path.join(workdir, "chromium-netns")
    with open(path, "w") as f:
        f.write(
            f'#!/bin/sh\nexec unshare {" ".join(_unshare_flags())} "{sys.executable}" -I '
            f'"{boot}" "{sock}" {port} "{workdir}" "{os.pathsep.join(hide)}" "{chrome}" "$@"\n'
        )
    os.chmod(path, 0o700)
    return path


WORKDIR_PREFIX = "ne-browser-"


def cleanup_stale_workdirs() -> int:
    """Remove work directories whose owning worker process no longer exists (a hard-killed
    worker cannot clean up). Directories of live processes, other users or unknown shape are
    left alone; PID reuse can only make us keep a directory, never remove a live one."""
    removed = 0
    base = tempfile.gettempdir()
    for name in os.listdir(base):
        if not name.startswith(WORKDIR_PREFIX):
            continue
        pid = name[len(WORKDIR_PREFIX) :].split("-", 1)[0]
        path = os.path.join(base, name)
        if not pid.isdigit() or not os.path.isdir(path) or os.stat(path).st_uid != os.getuid():
            continue
        try:
            os.kill(int(pid), 0)
            continue  # owner alive
        except ProcessLookupError:
            pass
        except PermissionError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed += 1
    return removed


def isolation_self_check() -> None:
    """Fail fast if the namespaces cannot be created here."""
    import subprocess

    r = subprocess.run(["unshare", *_unshare_flags(), "true"], capture_output=True, timeout=10)
    if r.returncode != 0:
        raise IsolationUnavailable(f"cannot create namespaces: {r.stderr[:200]!r}")


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
            workdir = tempfile.mkdtemp(prefix=f"{WORKDIR_PREFIX}{os.getpid()}-")
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
        try:
            browser = p.chromium.launch(**launch)
        except Exception as e:  # noqa: BLE001 - never retry without isolation
            raise IsolationUnavailable(
                f"isolated browser did not start ({type(e).__name__})"
            ) from e
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
        if r.request.method not in ("GET", "HEAD"):
            # Never fetch-and-fulfill a non-idempotent request: if that fetch is still pending
            # (or timed out) when the browser closes, Playwright resumes the paused original
            # and the employer receives it twice (reproduced). The browser sends it, once.
            # Redirect hops it follows are re-checked by the egress proxy, which allows only
            # the destination host:port.
            log.allowed += 1
            return r.continue_()
        # Redirects followed by the browser are not re-intercepted, so fetch without
        # following them and refuse any hop that leaves the allowed origin.
        try:
            resp = r.fetch(max_redirects=0)
        except Exception:
            # Abort rather than leave the request paused (Playwright would resume it later).
            try:
                r.abort("failed")
            except Exception:
                pass  # browser already closing
            return None
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
