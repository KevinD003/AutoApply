import socket

import pytest

from app.core.urlsafety import UnsafeURL, resolve_public_destination


def _fake(ip):
    def resolver(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolver


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fd00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_dns_rebinding_to_private_ranges_blocked(ip):
    with pytest.raises(UnsafeURL):
        resolve_public_destination("https://jobs.example.com/x", resolver=_fake(ip))


def test_public_destination_allowed():
    assert resolve_public_destination(
        "https://jobs.example.com/x", resolver=_fake("93.184.215.14")
    ) == ["93.184.215.14"]
