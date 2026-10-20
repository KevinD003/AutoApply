"""Egress proxy as its own service, for browsers running in a separate container.

Two listeners:
  * the proxy port (TCP, browser-facing): every connection must authenticate as one session
    (`Proxy-Authorization: Basic <session-id>:<session-token>`). Its destination is then
    checked against THAT session's allow-list by the same code as the in-process proxy
    (`EgressProxy.check`: exact host:port, every resolved address public unless the exact
    host:port is a fixture origin, connect to the checked address). Unauthenticated → 407.
  * the control socket (worker-facing): create / inspect / delete sessions. It is a UNIX
    socket, not a network listener: in Compose it lives on a volume mounted only into this
    service and the worker, so the browser container has neither a route nor a path to it.
    It still requires the control token, which only the worker holds.
Sessions expire on their own. Decisions are logged as host:port only.

Run: python -m app.modules.execution.sandbox.proxy_service
Env: EGRESS_CONTROL_TOKEN (required, >= 16 chars), EGRESS_PROXY_PORT (3128),
     EGRESS_CONTROL_SOCKET (/run/egress-control/control.sock), EGRESS_SESSION_TTL_SECONDS (900).
"""

import asyncio
import base64
import hmac
import json
import logging
import os
import secrets
import socketserver
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler

from app.modules.execution.sandbox.egress_proxy import Decision, check_destination, serve_connection

log = logging.getLogger("noefforts.egress")


@dataclass
class Policy:
    allow: set[tuple[str, int]]
    allow_private: set[tuple[str, int]]
    decisions: list[Decision] = field(default_factory=list)

    def check(self, host: str, port: int) -> tuple[str | None, str]:
        return check_destination(self.allow, self.allow_private, host, port)


@dataclass
class Session:
    id: str
    token: str
    policy: Policy
    expires: float


class Registry:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(self, allow, allow_private) -> Session:
        policy = Policy(
            allow={(h.lower(), int(p)) for h, p in allow},
            allow_private={(h.lower(), int(p)) for h, p in allow_private},
        )
        s = Session(secrets.token_hex(8), secrets.token_urlsafe(24), policy, time.time() + self.ttl)
        with self._lock:
            self._purge()
            self._sessions[s.id] = s
        return s

    def get(self, sid: str) -> Session | None:
        with self._lock:
            self._purge()
            return self._sessions.get(sid)

    def delete(self, sid: str) -> bool:
        with self._lock:
            return self._sessions.pop(sid, None) is not None

    def _purge(self):
        now = time.time()
        for k in [k for k, v in self._sessions.items() if v.expires < now]:
            del self._sessions[k]

    def authenticate(self, head: bytes) -> Policy | None:
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() != b"proxy-authorization":
                continue
            scheme, _, cred = value.strip().partition(b" ")
            if scheme.lower() != b"basic":
                return None
            try:
                sid, _, token = base64.b64decode(cred, validate=True).decode().partition(":")
            except (ValueError, UnicodeDecodeError):
                return None
            s = self.get(sid)
            if s and hmac.compare_digest(s.token.encode(), token.encode()):
                return s.policy
            return None
        return None


def control_handler(registry: Registry, control_token: str):
    class Handler(BaseHTTPRequestHandler):
        def _auth(self) -> bool:
            got = self.headers.get("X-Control-Token", "")
            return len(control_token) >= 16 and hmac.compare_digest(got, control_token)

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if not self._auth():
                return self._send(401, {"error": "unauthorised"})
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "decisions":
                s = registry.get(parts[1])
                if not s:
                    return self._send(404, {})
                d = s.policy.decisions
                return self._send(
                    200,
                    {
                        "allowed": sum(1 for x in d if x.allowed),
                        "denied": sorted({f"{x.host}:{x.port}" for x in d if not x.allowed}),
                    },
                )
            return self._send(404, {})

        def do_POST(self):  # noqa: N802
            if not self._auth():
                return self._send(401, {"error": "unauthorised"})
            if self.path != "/sessions":
                return self._send(404, {})
            try:
                n = min(int(self.headers.get("Content-Length", "0")), 16384)
                body = json.loads(self.rfile.read(n) or b"{}")
                allow = [(str(h), int(p)) for h, p in body["allow"]]
                private = [(str(h), int(p)) for h, p in body.get("allow_private", [])]
            except (ValueError, KeyError, TypeError):
                return self._send(400, {"error": "bad request"})
            if not allow or len(allow) > 4 or not set(private) <= set(allow):
                return self._send(400, {"error": "allow-list must name 1-4 destinations"})
            s = registry.create(allow, private)
            log.info("session %s: allow=%s private=%s", s.id, allow, private)
            return self._send(201, {"id": s.id, "token": s.token, "ttl": registry.ttl})

        def do_DELETE(self):  # noqa: N802
            if not self._auth():
                return self._send(401, {"error": "unauthorised"})
            parts = self.path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "sessions":
                return self._send(200 if registry.delete(parts[1]) else 404, {})
            return self._send(404, {})

        def address_string(self):
            return "control-socket"  # UNIX peers have no address

        def log_message(self, *a):
            pass

    return Handler


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def control_server(path: str, registry: Registry, control_token: str) -> _UnixHTTPServer:
    """The control API on a UNIX socket (owner-only permissions). A stale socket left by a
    previous run is replaced, so a restart never falls back to a network listener."""
    if os.path.exists(path):
        os.unlink(path)
    old = os.umask(0o177)
    try:
        return _UnixHTTPServer(path, control_handler(registry, control_token))
    finally:
        os.umask(old)


async def serve(proxy_port: int, control_socket: str, control_token: str, ttl: float):
    registry = Registry(ttl)
    httpd = control_server(control_socket, registry, control_token)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    async def handle(reader, writer):
        await serve_connection(reader, writer, registry.authenticate)

    server = await asyncio.start_server(handle, "0.0.0.0", proxy_port)
    log.info("egress proxy on :%d; control on UNIX socket %s", proxy_port, control_socket)
    async with server:
        await server.serve_forever()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    token = os.environ.get("EGRESS_CONTROL_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("EGRESS_CONTROL_TOKEN (at least 16 characters) is required")
    asyncio.run(
        serve(
            int(os.environ.get("EGRESS_PROXY_PORT", "3128")),
            os.environ.get("EGRESS_CONTROL_SOCKET", "/run/egress-control/control.sock"),
            token,
            float(os.environ.get("EGRESS_SESSION_TTL_SECONDS", "900")),
        )
    )


if __name__ == "__main__":
    main()
