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
import time
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
    """`code` is a fixed reason code, the only part shown to users or logged. The message is
    NoEfforts' own wording: it never includes service addresses, response bodies or command
    output. `status` is the HTTP status of a refusing service, if any."""

    def __init__(
        self, message: str, code: str = "isolation_unavailable", status: int | None = None
    ):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class SubresourceRule:
    """One extra origin a read-only observation may load page dependencies from: exact origin,
    and only these methods and resource types. Never used by execution (adapters pass none).
    `allow_private` exists for local test fixtures only."""

    origin: str  # scheme://host[:port], exact
    methods: frozenset
    resource_types: frozenset
    allow_private: bool = False

    @property
    def host_port(self) -> tuple[str, int]:
        u = urlsplit(self.origin)
        return (u.hostname or "").lower(), u.port or (443 if u.scheme == "https" else 80)


def _rules_by_origin(rules) -> dict:
    return {_origin(r.origin): r for r in rules}


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
        raise IsolationUnavailable("unshare(1) is not installed", "unshare_missing")
    boot = os.path.join(os.path.dirname(__file__), "sandbox", "netns_boot.py")
    hide = hidden_paths() if hide is None else hide
    if any(os.path.commonpath([h, os.path.realpath(chrome)]) == h for h in hide):
        raise IsolationUnavailable(
            "the browser binary lies inside a hidden path", "browser_path_hidden"
        )
    path = os.path.join(workdir, "chromium-netns")
    with open(path, "w") as f:
        f.write(
            f'#!/bin/sh\nexec unshare {" ".join(_unshare_flags())} "{sys.executable}" -I '
            f'"{boot}" "{sock}" {port} "{workdir}" "{os.pathsep.join(hide)}" "{chrome}" "$@"\n'
        )
    os.chmod(path, 0o700)
    return path


def control_request(
    socket_path: str, token: str, method: str, path: str, body=None, timeout: float = 30
) -> tuple[int, dict]:
    """HTTP over the egress proxy's UNIX control socket."""
    import http.client
    import json

    class _Conn(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect(socket_path)

    conn = _Conn("egress-control", timeout=timeout)
    try:
        conn.request(
            method,
            path,
            body=json.dumps(body).encode() if body is not None else None,
            headers={"X-Control-Token": token, "Content-Type": "application/json"},
        )
        r = conn.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        conn.close()


def local_driver_version() -> str:
    import json
    from pathlib import Path

    import playwright

    pkg = Path(playwright.__file__).parent / "driver" / "package" / "package.json"
    return json.loads(pkg.read_text())["version"]


class RemoteBrowser:
    """A browser in the browser-runner service, reachable only through an egress-proxy session
    that allows exactly this attempt's destination. Fails closed: any refusal or error raises
    IsolationUnavailable, and nothing falls back to a local browser."""

    def __init__(self, host: str, port: int, allow_private: bool, subresources=()):
        from app.core.config import get_settings

        self.s = get_settings()
        self.host, self.port, self.allow_private = host, port, allow_private
        self.subresources = tuple(subresources)
        self.proxy_session = self.runner_session = None

    @staticmethod
    def _call(base: str, header: str, token: str, method: str, path: str, body=None) -> dict:
        import json as _json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            base.rstrip("/") + path,
            data=_json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={header: token, "Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=60) as r:
                return _json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:  # neither the address nor the body is kept
            raise IsolationUnavailable(
                f"the browser runner refused ({e.code})", "runner_refused", e.code
            ) from None
        except OSError as e:
            raise IsolationUnavailable(
                f"the browser runner is unreachable ({type(e).__name__})", "runner_unreachable"
            ) from None

    def _proxy(self, method: str, path: str, body=None) -> dict:
        s = self.s
        try:
            code, out = control_request(
                s.egress_control_socket, s.egress_control_token, method, path, body
            )
        except OSError as e:
            raise IsolationUnavailable(
                f"egress proxy control unreachable ({type(e).__name__})", "proxy_unreachable"
            ) from None
        if code >= 300:  # the proxy's answer is not kept
            raise IsolationUnavailable(
                f"egress proxy control refused ({code})", "proxy_refused", code
            )
        return out

    def _runner(self, method: str, path: str, body=None) -> dict:
        s = self.s
        return self._call(
            s.browser_runner_url, "X-Runner-Token", s.browser_runner_token, method, path, body
        )

    def _check_runner(self) -> None:
        """The runner must have verified its sandbox and run the same Playwright driver as this
        worker (the protocol is version-specific); otherwise refuse with the reason."""
        h = self._call(self.s.browser_runner_url, "X-Runner-Token", "", "GET", "/health")
        mine = local_driver_version()
        if h.get("driver_version") != mine:
            raise IsolationUnavailable(
                f"browser runner driver {h.get('driver_version')!r} does not match this "
                f"worker's {mine!r}; rebuild the browser-runner image from this revision",
                "runner_version_mismatch",
            )

    def _runner_session(self, body: dict) -> dict:
        """One browser per runner slot. While the slot is busy, wait a bounded time (nothing has
        been disclosed yet and the claim's lease outlasts the wait), then refuse."""
        deadline = time.monotonic() + self.s.browser_slot_wait_seconds
        while True:
            try:
                return self._runner("POST", "/sessions", body)
            except IsolationUnavailable as e:
                if e.status != 429 or time.monotonic() >= deadline:
                    raise
            time.sleep(1)

    def open(self) -> str:
        self._check_runner()
        dest = [[self.host, self.port]]
        extra = [list(r.host_port) for r in self.subresources]
        private = (dest if self.allow_private else []) + [
            list(r.host_port) for r in self.subresources if r.allow_private
        ]
        self.proxy_session = self._proxy(
            "POST", "/sessions", {"allow": dest + extra, "allow_private": private}
        )
        self.runner_session = self._runner_session(
            {
                "proxy_username": self.proxy_session["id"],
                "proxy_password": self.proxy_session["token"],
                "allowed_host": self.host,
                "extra_allowed_hosts": [h for h, _ in extra],
            },
        )
        return self.runner_session["ws_endpoint"]

    @property
    def decisions(self) -> list:
        """Denied destinations of this session, in the shape EgressLog expects."""
        from app.modules.execution.sandbox.egress_proxy import Decision

        if not self.proxy_session:
            return []
        out = []
        for hp in self._proxy("GET", f"/sessions/{self.proxy_session['id']}/decisions")["denied"]:
            h, _, p = hp.rpartition(":")
            out.append(Decision(h, int(p), False, "denied"))
        return out

    def close(self) -> None:
        for fn, sess in ((self._runner, self.runner_session), (self._proxy, self.proxy_session)):
            if sess:
                try:
                    fn("DELETE", f"/sessions/{sess['id']}")
                except IsolationUnavailable:
                    pass  # the runner's time limit and the proxy's TTL end it anyway


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
        raise IsolationUnavailable("cannot create namespaces", "namespaces_unavailable")


@contextmanager
def browser_session(
    allowed_origin: str,
    nav_timeout_ms: int,
    *,
    isolation: str = "netns",
    intercept: bool = True,
    allow_private_destination: bool = False,
    subresources: tuple = (),
):
    """`intercept=False` disables the in-process layers; used only by isolation tests to show
    that the namespace + egress proxy alone enforce the policy. `subresources`: extra origins
    for page dependencies (SubresourceRule), read-only observation only; every layer (resolver
    rules, interception, egress proxy, runner) is widened by exactly these and nothing else."""
    from app.modules.execution.sandbox.egress_proxy import EgressProxy

    allowed = allowed_origin.lower().rstrip("/")
    u = urlsplit(allowed)
    host, port = u.hostname or "", u.port or (443 if u.scheme == "https" else 80)
    log = EgressLog()
    args = ["--disable-background-networking", "--no-first-run", "--disable-sync"]
    rules = tuple(subresources)
    extra_hp = [r.host_port for r in rules]
    if intercept:
        keep = " , ".join(f"EXCLUDE {h}" for h in [host, *(h for h, _ in extra_hp)])
        args.insert(0, f"--host-resolver-rules=MAP * ~NOTFOUND , {keep}")
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
                allow={(host, port), *extra_hp},
                allow_private=({(host, port)} if allow_private_destination else set())
                | {r.host_port for r in rules if r.allow_private},
            ).start()
            stack.callback(proxy.stop)
            log.proxy = proxy
            launch["executable_path"] = _netns_wrapper(workdir, sock, _free_port(), chrome)
            launch["env"] = {"PATH": "/usr/bin:/bin", "HOME": workdir, "TMPDIR": workdir}
        elif isolation == "off":
            launch["executable_path"] = chrome
        elif isolation != "container":
            raise IsolationUnavailable("unknown isolation mode", "unknown_isolation_mode")
        try:
            if isolation == "container":
                remote = RemoteBrowser(host, port, allow_private_destination, rules)
                stack.callback(remote.close)
                log.proxy = remote
                browser = p.chromium.connect(
                    remote.open(),
                    timeout=30_000,
                    headers={"X-Runner-Token": remote.s.browser_runner_token},
                )
            else:
                browser = p.chromium.launch(**launch)
        except IsolationUnavailable:
            raise
        except Exception as e:  # noqa: BLE001 - never retry without isolation
            raise IsolationUnavailable(
                f"isolated browser did not start ({type(e).__name__})", "browser_start_failed"
            ) from None
        try:
            ctx = browser.new_context(
                service_workers="block" if intercept else "allow", accept_downloads=False
            )
            ctx.set_default_navigation_timeout(nav_timeout_ms)
            ctx.set_default_timeout(nav_timeout_ms)
            if intercept:
                _install_interception(
                    ctx, allowed, log, driver_fetch=isolation != "container", subresources=rules
                )
            pages = []
            ctx.on("page", lambda pg: pg.close() if pages else pages.append(pg))
            page = ctx.new_page()
            yield page, log
        finally:
            browser.close()  # always: a worker that loses authority closes its browser


def _install_interception(
    ctx, allowed: str, log: "EgressLog", *, driver_fetch=True, subresources=()
) -> None:
    """`driver_fetch=False` (container mode): never fetch or connect from the Playwright
    driver, which runs in the browser container but outside the browser's proxy settings;
    every allowed request is left to the browser, so it can only leave through the proxy.
    `subresources`: a request to one of those origins passes only with one of its methods and
    resource types; so must every redirect target."""
    rules = _rules_by_origin(subresources)

    def permitted(url: str, method: str, rtype: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        o = _origin(url)
        if o == allowed:
            return True
        rule = rules.get(o)
        return rule is not None and method in rule.methods and rtype in rule.resource_types

    def route(r):
        url, method, rtype = r.request.url, r.request.method, r.request.resource_type
        if not permitted(url, method, rtype):
            log.blocked.append(url[:200])
            return r.abort("blockedbyclient")
        if _origin(url) != allowed:
            # An approved dependency origin (GET/HEAD only, by its rule). In container mode
            # the browser fetches it through the proxy; otherwise fetch without following
            # redirects and require the target to satisfy the same policy.
            if not driver_fetch:
                log.allowed += 1
                return r.continue_()
            try:
                resp = r.fetch(max_redirects=0)
            except Exception:
                try:
                    r.abort("failed")
                except Exception:
                    pass
                return None
            loc = resp.headers.get("location")
            if 300 <= resp.status < 400 and loc:
                target = urljoin(url, loc)
                if not permitted(target, method, rtype):
                    log.blocked.append(target[:200])
                    return r.abort("blockedbyclient")
            log.allowed += 1
            return r.fulfill(response=resp)
        if r.request.method not in ("GET", "HEAD") or not driver_fetch:
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
            if _origin(target) != allowed and not permitted(target, method, rtype):
                log.blocked.append(target[:200])
                return r.abort("blockedbyclient")
        log.allowed += 1
        return r.fulfill(response=resp)

    ctx.route("**/*", route)
    if not driver_fetch:
        return  # WebSockets stay in the browser and reach the proxy like everything else

    def ws(w):
        if _origin(w.url.replace("ws", "http", 1)) != allowed:
            log.blocked.append(w.url[:200])
            w.close()
        else:
            w.connect_to_server()

    ctx.route_web_socket("**/*", ws)
