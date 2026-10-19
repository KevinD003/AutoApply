"""Isolated browser sessions with an origin allow-list.

Layers (defence in depth, not a substitute for network-level egress control):
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
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


@dataclass
class EgressLog:
    allowed: int = 0
    blocked: list[str] = field(default_factory=list)


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower()


@contextmanager
def browser_session(allowed_origin: str, nav_timeout_ms: int):
    allowed = allowed_origin.lower().rstrip("/")
    host = urlsplit(allowed).hostname or ""
    log = EgressLog()
    args = [
        f"--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE {host}",
        "--disable-background-networking",
        "--no-first-run",
        "--disable-sync",
    ]
    exe = os.environ.get("PW_CHROMIUM_PATH") or None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=args, executable_path=exe)
        try:
            ctx = browser.new_context(
                service_workers="block", accept_downloads=False, java_script_enabled=True
            )
            ctx.set_default_navigation_timeout(nav_timeout_ms)
            ctx.set_default_timeout(nav_timeout_ms)

            def route(r):
                url = r.request.url
                if url.startswith(("http://", "https://")) and _origin(url) == allowed:
                    log.allowed += 1
                    return r.continue_()
                log.blocked.append(url[:200])
                return r.abort("blockedbyclient")

            ctx.route("**/*", route)

            def ws(w):
                if _origin(w.url.replace("ws", "http", 1)) != allowed:
                    log.blocked.append(w.url[:200])
                    w.close()
                else:
                    w.connect_to_server()

            ctx.route_web_socket("**/*", ws)
            pages = []
            ctx.on("page", lambda pg: pg.close() if pages else pages.append(pg))
            page = ctx.new_page()
            yield page, log
        finally:
            browser.close()  # always: a worker that loses authority closes its browser
