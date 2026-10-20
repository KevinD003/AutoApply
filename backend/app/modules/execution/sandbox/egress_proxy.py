"""Default-deny egress proxy for sandboxed browsers.

Listens on a UNIX socket (reachable from inside the browser's network namespace only through
the relay in `netns_boot.py`). Every request names its destination (CONNECT host:port, or an
absolute-form HTTP URL); it is allowed only if (host, port) is on the allow-list, the host
resolves, and every resolved address is public, except for an explicit test-only fixture
exception. The proxy then connects to the exact address it checked (no second DNS lookup).
Decisions are logged without paths, headers or bodies.
"""

import asyncio
import ipaddress
import os
import socket
import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit

DENY = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def check_destination(allow, allow_private, host: str, port: int) -> tuple[str | None, str]:
    """(address to connect to, reason). Exact host:port allow-list; every resolved address must
    be public unless that exact host:port is in `allow_private` (fixture origins only)."""
    key = (host.lower().strip("[]"), port)
    if key not in allow:
        return None, "destination not on the allow-list"
    try:
        infos = socket.getaddrinfo(key[0], port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None, "does not resolve"
    ips = sorted({i[4][0] for i in infos})
    for ip in ips:
        a = ipaddress.ip_address(ip.split("%")[0])
        if not a.is_global and key not in allow_private:
            return None, f"resolves to non-public address {a}"
    return ips[0], "allowed"


@dataclass
class Decision:
    host: str
    port: int
    allowed: bool
    reason: str


@dataclass
class EgressProxy:
    socket_path: str
    allow: set[tuple[str, int]]
    allow_private: set[tuple[str, int]] = field(default_factory=set)  # test fixtures only
    decisions: list[Decision] = field(default_factory=list)

    def __post_init__(self):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # -- lifecycle ---------------------------------------------------------------------------
    def start(self) -> "EgressProxy":
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("egress proxy did not start")
        return self

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def _run(self):
        asyncio.set_event_loop(self._loop)
        server = self._loop.run_until_complete(
            asyncio.start_unix_server(self._handle, path=self.socket_path)
        )
        os.chmod(self.socket_path, 0o600)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            server.close()

    # -- policy ------------------------------------------------------------------------------
    def check(self, host: str, port: int) -> tuple[str | None, str]:
        return check_destination(self.allow, self.allow_private, host, port)

    # -- connection handling -----------------------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await serve_connection(reader, writer, lambda head: self)


AUTH_REQUIRED = (
    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
    b'Proxy-Authenticate: Basic realm="noefforts"\r\nContent-Length: 0\r\n'
    b"Connection: close\r\n\r\n"
)


async def serve_connection(reader, writer, policy_for):
    """One proxied connection. `policy_for(head)` returns the policy (an object with `check`
    and `decisions`) the request is subject to, or None to demand proxy authentication."""
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
        writer.close()
        return
    policy = policy_for(head)
    if policy is None:
        writer.write(AUTH_REQUIRED)
        await writer.drain()
        writer.close()
        return
    first, _, rest = head.partition(b"\r\n")
    try:
        method, target, version = first.decode("latin-1").split(" ", 2)
    except ValueError:
        writer.write(DENY)
        writer.close()
        return
    if method.upper() == "CONNECT":
        host, _, p = target.rpartition(":")
        try:
            port, path = int(p or 443), None
        except ValueError:
            writer.write(DENY)
            writer.close()
            return
    else:
        u = urlsplit(target)
        if u.scheme not in ("http",) or not u.hostname:
            writer.write(DENY)
            writer.close()
            return
        host, port = u.hostname, u.port or 80
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    ip, reason = policy.check(host, port)
    policy.decisions.append(Decision(host, port, ip is not None, reason))
    if ip is None:
        writer.write(DENY)
        await writer.drain()
        writer.close()
        return
    try:
        up_r, up_w = await asyncio.wait_for(asyncio.open_connection(ip, port), 15)
    except (OSError, TimeoutError):
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        writer.close()
        return
    if path is None:
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    else:
        headers = [h for h in rest.split(b"\r\n") if h and not h.lower().startswith(b"proxy-")]
        up_w.write(
            f"{method} {path} {version}\r\n".encode("latin-1") + b"\r\n".join(headers) + b"\r\n\r\n"
        )
    # Later requests on a kept-alive connection can only reach this same checked upstream.
    await asyncio.gather(_pipe(reader, up_w), _pipe(up_r, writer), return_exceptions=True)


async def _pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    finally:
        w.close()
