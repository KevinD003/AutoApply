"""Treat every job URL as an SSRF input.

`check_url_syntax` is used when storing a URL. `resolve_public_destination` must be called
before any server-side fetch, and again for every redirect hop.

Local test fixtures (D86) are the one exception, and only in the test environment: an exact
origin listed in NOEFFORTS_FIXTURE_ORIGINS whose host is a loopback address, an address on a
configured test network, or exactly one of FIXTURE_SERVICE_HOSTS. A name is checked again when
connecting (`connect_fixture`, the egress proxy): every address it resolves to, and the address
actually connected to, must be loopback or on a configured test network.
"""

import http.client
import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata"}
# Names a fixture origin may use, each listed exactly: the Compose test network's receiver
# service (docker-compose.execution-test.yml). No other name, single-label or not, is a fixture
# host; a bare name can resolve anywhere through a DNS search suffix, so it is also checked
# when connecting.
FIXTURE_SERVICE_HOSTS = frozenset({"receiver"})


class UnsafeURL(ValueError):
    pass


def is_fixture_origin(url: str) -> bool:
    """True only in the test environment, for an exact plain-http origin listed in
    NOEFFORTS_FIXTURE_ORIGINS whose host is a fixture host (`local_fixture_host`): listing a
    public site, an unlisted name or another spelling of an address never makes it a fixture."""
    from app.core.config import get_settings

    s = get_settings()
    if s.env != "test" or not s.fixture_origins:
        return False
    p = urlsplit(url.strip())
    if p.scheme != "http" or p.username or p.password:
        return False
    origin = f"{p.scheme}://{p.netloc}".lower()
    listed = origin in {o.lower().rstrip("/") for o in s.fixture_origins}
    return listed and local_fixture_host(p.hostname or "")


def local_fixture_host(host: str) -> bool:
    """A host a listed fixture origin may name: an address literal in standard form that is
    loopback or on a configured test network (an IPv4-mapped IPv6 address counts as its IPv4
    address), or exactly one of FIXTURE_SERVICE_HOSTS. Never any other name: other spellings of
    an address (decimal, hex, octal, shortened) are names to Python and are refused here."""
    host = host.lower()
    if host in FIXTURE_SERVICE_HOSTS:
        return True
    try:
        return fixture_address(ipaddress.ip_address(host))
    except ValueError:
        return False


def fixture_networks() -> tuple:
    """The configured test networks (NOEFFORTS_FIXTURE_NETWORKS), validated by Settings."""
    from app.core.config import get_settings

    return parse_fixture_networks(get_settings().fixture_networks)


_PRIVATE_SPACE = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def parse_fixture_networks(values) -> tuple:
    """A list of networks, each inside RFC 1918 or IPv6 unique-local space and at most /16
    (IPv4) or /48 (IPv6): never public, link-local (cloud metadata), loopback, "this network"
    or any other special space, and never a whole private range."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError("test networks must be a list")
    nets = []
    for v in values:
        n = ipaddress.ip_network(str(v), strict=True)
        inside = any(n.version == b.version and n.subnet_of(b) for b in _PRIVATE_SPACE)
        if not inside or n.prefixlen < (16 if n.version == 4 else 48):
            raise ValueError(f"not a narrow private test network: {v}")
        nets.append(n)
    return tuple(nets)


def fixture_address(ip, networks=None) -> bool:
    """A loopback address, or one inside a configured test network. Never link-local,
    unspecified, multicast or public."""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return True
    nets = fixture_networks() if networks is None else networks
    return any(ip.version == n.version and ip in n for n in nets)


def connect_fixture(host: str, port: int, timeout=None, *, resolver=None,
                    open_socket=None) -> socket.socket:  # fmt: skip
    """A TCP connection to a fixture host: every address the host resolves to must be a fixture
    address, the connection goes to the checked address (no second lookup), and the peer
    actually connected to is checked again before anything is sent."""
    try:
        infos = (resolver or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURL("the fixture host does not resolve") from e
    if not infos:
        raise UnsafeURL("the fixture host does not resolve")
    for info in infos:
        if not fixture_address(info[4][0]):
            raise UnsafeURL("the fixture host resolves outside the local test network")
    family, kind, proto, _, addr = infos[0]
    sock = (open_socket or socket.socket)(family, kind, proto)
    try:
        if timeout is not None and timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)
        sock.connect(addr)
        peer = sock.getpeername()[0]
        same = ipaddress.ip_address(peer.split("%")[0]) == ipaddress.ip_address(
            addr[0].split("%")[0]
        )
        if not same or not fixture_address(peer):
            raise UnsafeURL("the connected address is not the checked fixture address")
    except BaseException:
        sock.close()
        raise
    return sock


class _FixtureConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = connect_fixture(self.host, self.port, self.timeout)


class FixtureHTTPHandler(urllib.request.HTTPHandler):
    """Plain HTTP to fixture origins only: each request's origin is checked when it is opened
    (a redirect hop included), then its connection by `connect_fixture`."""

    def http_open(self, req):
        if not is_fixture_origin(req.full_url):
            raise UnsafeURL("not a local test fixture origin")
        return self.do_open(_FixtureConnection, req)


class _RefuseHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        raise UnsafeURL("fixture origins are plain http")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # a redirect is an HTTP error to the caller, never followed


def fixture_opener(no_redirect=_NoRedirect) -> urllib.request.OpenerDirector:
    """The only way server-side code reaches a local test fixture: plain http only (no file,
    ftp or data handlers), no proxies, no redirects (`no_redirect`, a handler class that never
    follows one, may say why in the caller's own terms), every connection checked
    (`FixtureHTTPHandler`)."""
    opener = urllib.request.OpenerDirector()
    for h in (urllib.request.UnknownHandler(), urllib.request.HTTPDefaultErrorHandler(),
              urllib.request.HTTPErrorProcessor(), no_redirect(), FixtureHTTPHandler(),
              _RefuseHTTPS()):  # fmt: skip
        opener.add_handler(h)
    return opener


def check_url_syntax(url: str) -> str:
    url = url.strip()
    if is_fixture_origin(url):
        return url  # test-only synthetic receiver; production never reaches this branch
    if len(url) > 2048:
        raise UnsafeURL("URL is too long")
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURL("Only http and https URLs are allowed")
    if not parts.hostname:
        raise UnsafeURL("URL has no host")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed")
    host = parts.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".internal"):
        raise UnsafeURL("URL points to a local or internal host")
    try:
        _check_ip(ipaddress.ip_address(host))
    except ValueError as e:
        if isinstance(e, UnsafeURL):
            raise
        legacy = _legacy_ipv4(host)
        if legacy is not None:
            _check_ip(legacy)
    return url


def _legacy_ipv4(host: str):
    """Other spellings of an IPv4 address that resolvers and browsers accept (decimal, hex,
    octal, shortened such as 127.1) are checked as that address. Anything else is a name."""
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        raise UnsafeURL("URL resolves to a non-public address")


DESTINATION_CATEGORIES = ("loopback", "link_local", "private", "named", "public", "other")


def destination_category(host: str) -> str:
    """A fixed category for a destination host, for records that must not keep the host
    itself. No lookup is made: a name stays `named`."""
    h = (host or "").strip().strip("[]").lower()
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return "loopback" if h == "localhost" or h.endswith(".localhost") else "named"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return "loopback"
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "other"
    if ip.is_link_local:
        return "link_local"
    if ip.is_private:
        return "private"
    return "public" if ip.is_global else "other"


def resolve_public_destination(url: str, resolver=socket.getaddrinfo) -> list[str]:
    """Return the resolved public IPs for `url`, or raise if any resolve to a blocked range."""
    check_url_syntax(url)
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = resolver(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURL("Host could not be resolved") from e
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise UnsafeURL("Host could not be resolved")
    for ip in ips:
        _check_ip(ipaddress.ip_address(ip.split("%")[0]))
    return ips
