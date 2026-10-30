"""Treat every job URL as an SSRF input.

`check_url_syntax` is used when storing a URL. `resolve_public_destination` must be called
before any server-side fetch, and again for every redirect hop.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata"}


class UnsafeURL(ValueError):
    pass


def is_fixture_origin(url: str) -> bool:
    """True only outside production, for an exact origin listed in NOEFFORTS_FIXTURE_ORIGINS
    whose host is local (`local_fixture_host`): listing a public site there never makes it a
    fixture (D85)."""
    from app.core.config import get_settings

    s = get_settings()
    if s.env == "production" or not s.fixture_origins:
        return False
    p = urlsplit(url.strip())
    origin = f"{p.scheme}://{p.netloc}".lower()
    listed = origin in {o.lower().rstrip("/") for o in s.fixture_origins}
    return listed and p.scheme in ALLOWED_SCHEMES and local_fixture_host(p.hostname or "")


def local_fixture_host(host: str) -> bool:
    """A host a local fixture may run on: a loopback address, "localhost", or a single-label
    name (an internal service, such as the Compose test network's receiver). Never a dotted
    public name or any other address."""
    host = host.lower().rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return bool(host) and "." not in host and ":" not in host


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
    return url


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
