"""The fixture-origin boundary (D86): what may count as a local test fixture, and the checks on
every connection to one.

A fixture origin is honoured only when NOEFFORTS_ENV=test, only for an exact plain-http origin
listed in NOEFFORTS_FIXTURE_ORIGINS, and only when its host is a loopback or test-network
address literal or exactly one of `urlsafety.FIXTURE_SERVICE_HOSTS` (the Compose receiver).
A listed name is checked again when connecting: the server-side opener (`connect_fixture`) and
the egress proxy both require every resolved address, and the address actually reached, to be
loopback or on the configured test network. Redirects are never followed server-side, every
hop is checked by origin, and a fixture is never browsed without the egress proxy.

Nothing here contacts a public address: every public answer comes from a fake resolver, and each
check refuses before a connection is opened. Synthetic data only.
"""

import http.server
import os
import shutil
import socket
import tempfile
import threading
import urllib.error
import urllib.request
import uuid

import pytest
from pydantic import ValidationError

from app.core import urlsafety
from app.core.config import Settings, get_settings
from app.core.urlsafety import (
    FixtureHTTPHandler,
    UnsafeURL,
    check_url_syntax,
    connect_fixture,
    fixture_address,
    fixture_opener,
    is_fixture_origin,
    local_fixture_host,
    parse_fixture_networks,
)
from app.modules.execution import runner
from app.modules.execution.browser import IsolationUnavailable, browser_session
from app.modules.execution.sandbox import egress_proxy, proxy_service
from app.modules.execution.sandbox.egress_proxy import EgressProxy
from app.modules.preparation import lever
from tests.conftest import CANARY_PORT, RECEIVER_PORT
from tests.execution_harness import BASE, Receiver, attempt, queue, synthetic_candidate
from tests.test_lever_adapter import lever_application, lever_job

CANARY = CANARY_PORT
NAMED = f"http://receiver:{RECEIVER_PORT}"  # the Compose receiver's name, here on loopback
TEST_NET = parse_fixture_networks(["10.231.47.0/24"])
_real_getaddrinfo = socket.getaddrinfo


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


@pytest.fixture
def listed(monkeypatch):
    """Adds origins to NOEFFORTS_FIXTURE_ORIGINS for one test."""
    s = get_settings()

    def add(*origins):
        monkeypatch.setattr(s, "fixture_origins", [*s.fixture_origins, *origins])

    return add


@pytest.fixture
def resolve(monkeypatch):
    """`resolve("receiver", "8.8.8.8")`: what a name resolves to for every lookup in this
    process (the opener and the in-process egress proxy). Other names resolve as usual."""
    answers: dict[str, list[str]] = {}

    def fake(host, port, *a, **k):
        if host in answers:
            fam = socket.AF_INET6 if ":" in answers[host][0] else socket.AF_INET
            return [(fam, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in answers[host]]
        return _real_getaddrinfo(host, port, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", fake)

    def set_(host, *ips):
        answers[host] = list(ips)

    return set_


def _never(*a, **k):
    raise AssertionError("a connection was opened")


# ------------------------------------------------------------------- which hosts count


def test_only_names_listed_exactly_are_fixture_hosts():
    """No general single-label rule: `receiver` (the Compose service) is listed; any other bare
    name, `localhost`, a trailing-dot or dotted variant is not."""
    assert urlsafety.FIXTURE_SERVICE_HOSTS == frozenset({"receiver"})
    assert local_fixture_host("receiver") and local_fixture_host("RECEIVER")
    for host in ("other", "localhost", "receiver.", "receiver.example.com", "db", "redis",
                 "metadata", "canary", "cdn-fixture", ""):  # fmt: skip
        assert not local_fixture_host(host), host


def test_an_unlisted_single_label_name_is_refused(api, listed):
    listed("http://other:8799", "http://receiver:8799")
    assert is_fixture_origin("http://receiver:8799")
    assert not is_fixture_origin("http://other:8799")  # listed as an origin, not as a host
    with pytest.raises(UnsafeURL):
        fixture_opener().open("http://other:8799/lever/x", timeout=2)
    synthetic_candidate(api)
    job_id = lever_job(api, url=f"http://other:8799/lever/examplehealth/{uuid.uuid4()}")
    assert api.post(f"/jobs/{job_id}/form/lever").status_code == 400  # not a fixture posting
    assert api.get(f"/jobs/{job_id}/route").json()["route"] == "manual_handoff"


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_fixture_origins_are_refused_outside_the_test_environment(api, monkeypatch, env):
    monkeypatch.setattr(get_settings(), "env", env)
    assert not is_fixture_origin(BASE)
    with pytest.raises(UnsafeURL):
        check_url_syntax(f"{BASE}/lever/examplehealth/{uuid.uuid4()}")  # just loopback now
    with pytest.raises(UnsafeURL):
        FixtureHTTPHandler().http_open(urllib.request.Request(f"{BASE}/apply/health-check"))


@pytest.mark.parametrize(
    "host",
    ["2130706433", "0x7f000001", "0x7f.0.0.1", "0177.0.0.1", "0177.0.0.01", "127.1", "127.0.1",
     "017700000001", "127.000.000.001"],
)  # fmt: skip
def test_other_spellings_of_a_loopback_address_never_count(listed, host):
    """Decimal, hex, octal and shortened forms are what resolvers and browsers turn into
    127.0.0.1: listed or not, they are never fixture hosts, and as job addresses they are
    refused as the address they spell."""
    origin = f"http://{host}:{RECEIVER_PORT}"
    listed(origin)
    assert not is_fixture_origin(origin)
    with pytest.raises(UnsafeURL, match="non-public"):
        check_url_syntax(f"{origin}/lever/examplehealth/{uuid.uuid4()}")


@pytest.mark.parametrize("host", ["134744072", "0x8080808", "8.8.2056"])
def test_other_spellings_of_a_public_address_are_public_not_fixtures(listed, host):
    origin = f"http://{host}"
    listed(origin)
    assert not is_fixture_origin(origin)
    assert check_url_syntax(f"{origin}/x") == f"{origin}/x"  # an ordinary (real) address


@pytest.mark.parametrize(
    ("host", "fixture"),
    [("[::1]", True), ("[0:0:0:0:0:0:0:1]", True), ("[::ffff:127.0.0.1]", True),
     ("[::ffff:7f00:1]", True), ("[::ffff:8.8.8.8]", False), ("[::ffff:169.254.169.254]", False),
     ("[::ffff:10.0.0.5]", False), ("[fe80::1]", False), ("[::]", False), ("[fd00::1]", False),
     ("[2001:4860:4860::8888]", False)],
)  # fmt: skip
def test_ipv6_loopback_and_mapped_forms(listed, host, fixture):
    """IPv6 loopback in any standard notation, and an IPv4-mapped address, count as the address
    they are: mapped loopback is loopback, mapped public or link-local is refused."""
    origin = f"http://{host}:{RECEIVER_PORT}"
    listed(origin)
    assert is_fixture_origin(origin) is fixture
    assert is_fixture_origin(f"http://{host}:1") is False  # never without the exact origin


def test_https_userinfo_and_case_variants_are_not_listed_origins(listed):
    listed(BASE)
    assert is_fixture_origin(BASE) and is_fixture_origin(BASE.replace("http", "HTTP", 1))
    assert not is_fixture_origin(BASE.replace("http://", "https://"))
    assert not is_fixture_origin(BASE.replace("http://", "http://u:p@"))
    assert not is_fixture_origin(BASE + ".")


@pytest.mark.parametrize(
    ("ip", "with_net", "ok"),
    [("127.0.0.1", False, True), ("127.0.0.2", False, True), ("::1", False, True),
     ("::ffff:127.0.0.1", False, True), ("10.231.47.5", False, False),
     ("10.231.47.5", True, True), ("::ffff:10.231.47.5", True, True),
     ("10.231.48.5", True, False), ("169.254.169.254", True, False), ("0.0.0.0", True, False),
     ("::", True, False), ("fe80::1%eth0", True, False), ("8.8.8.8", True, False),
     ("100.64.0.1", True, False), ("224.0.0.1", True, False)],
)  # fmt: skip
def test_fixture_addresses_are_loopback_or_on_the_test_network(ip, with_net, ok):
    assert fixture_address(ip, TEST_NET if with_net else ()) is ok


@pytest.mark.parametrize(
    "net",
    ["8.8.8.0/24", "169.254.0.0/16", "10.0.0.0/8", "0.0.0.0/0", "127.0.0.0/8", "224.0.0.0/24",
     "fe80::/64", "::/0", "10.231.47.5/24", "100.64.0.0/16", "fd00::/8", "not-a-network",
     "0.0.0.0/16", "0.0.0.1/32", "172.32.0.0/16", "192.0.2.0/24"],
)  # fmt: skip
def test_a_test_network_must_be_a_narrow_private_network(net):
    with pytest.raises(ValueError):
        parse_fixture_networks([net])
    with pytest.raises(ValidationError):
        Settings(fixture_networks=[net])


def test_test_networks_must_be_given_as_a_list():
    for value in ("10.231.47.0/24", b"10.231.47.0/24", {"10.231.47.0/24": 1}, None):
        with pytest.raises(ValueError):
            parse_fixture_networks(value)


def test_narrow_private_test_networks_are_accepted():
    assert [str(n) for n in parse_fixture_networks(["10.231.47.0/24", "fd12:3456:789a::/48"])] == [
        "10.231.47.0/24", "fd12:3456:789a::/48"]  # fmt: skip
    assert Settings(fixture_networks=["10.231.47.0/24"]).fixture_networks == ["10.231.47.0/24"]


# ------------------------------------------------------- server-side connections (capture)


def test_a_listed_name_resolving_to_a_public_address_is_refused_before_connecting():
    def public(host, port, type=0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    def mixed(host, port, type=0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in ("127.0.0.1", "8.8.8.8")]  # fmt: skip

    for resolver in (public, mixed):
        with pytest.raises(UnsafeURL, match="outside the local test network"):
            connect_fixture("receiver", 8799, 2, resolver=resolver, open_socket=_never)


def test_the_address_actually_connected_to_is_checked_again():
    """Even when every resolved address is loopback, a connection that reaches another address
    is closed before anything is sent."""

    class Elsewhere:
        closed = False

        def __init__(self, *a):
            pass

        def settimeout(self, t):
            pass

        def connect(self, addr):
            pass

        def getpeername(self):
            return ("8.8.8.8", 8799)

        def close(self):
            Elsewhere.closed = True

    def loopback(host, port, type=0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    with pytest.raises(UnsafeURL, match="not the checked fixture address"):
        connect_fixture("receiver", 8799, 2, resolver=loopback, open_socket=Elsewhere)
    assert Elsewhere.closed


def test_every_request_the_opener_makes_is_checked_by_origin():
    """A hop that is not a listed fixture origin is refused when it is opened, before any
    connection (so a followed redirect would be too); https is never used for a fixture."""
    for url in (
        "http://127.0.0.1:8798/x",
        f"http://[::1]:{RECEIVER_PORT}/x",
        "http://10.0.0.5:8799/x",
        "http://8.8.8.8/x",
    ):  # literals: no lookup either way
        with pytest.raises(UnsafeURL, match="not a local test fixture origin"):
            fixture_opener().open(url, timeout=2)
    with pytest.raises(UnsafeURL, match="plain http"):
        fixture_opener().open(BASE.replace("http://", "https://") + "/x", timeout=2)
    for url in ("file:///etc/hostname", "ftp://127.0.0.1/x", "data:text/plain,x"):
        with pytest.raises(urllib.error.URLError, match="unknown url type"):
            fixture_opener().open(url, timeout=2)


def test_the_opener_never_follows_a_redirect(receiver, canary):
    receiver.config(canary=f"http://127.0.0.1:{CANARY}")
    with pytest.raises(urllib.error.HTTPError) as e:
        fixture_opener().open(f"{BASE}/redirect-to-canary", timeout=5)
    assert e.value.code == 302 and canary == []


def test_a_listed_name_is_read_only_while_it_resolves_locally(api, receiver, listed, resolve):
    """The Compose shape (`http://receiver:PORT`), here on loopback: read while `receiver`
    resolves to loopback; refused, with nothing requested, once it resolves publicly."""
    listed(NAMED)
    resolve("receiver", "127.0.0.1")
    synthetic_candidate(api)
    posting = str(uuid.uuid4())
    job_id = lever_job(api, url=f"{NAMED}/lever/examplehealth/{posting}")
    assert api.post(f"/jobs/{job_id}/form/lever").status_code == 201
    receiver.reset()
    resolve("receiver", "8.8.8.8")
    r = api.post(f"/jobs/{job_id}/form/lever")
    assert r.status_code == 400 and "UnsafeURL" in r.text
    assert [x for x in receiver.ledger()["requests"] if posting in x["path"]] == []


def test_a_capture_redirect_off_the_fixture_is_never_followed(api, receiver, canary, monkeypatch):
    receiver.config(canary=f"http://127.0.0.1:{CANARY}")
    monkeypatch.setattr(lever, "apply_path", lambda posting: "/redirect-chain")
    synthetic_candidate(api)
    job_id = lever_job(api, url=f"{BASE}/lever/examplehealth/{uuid.uuid4()}")
    r = api.post(f"/jobs/{job_id}/form/lever")
    assert r.status_code == 400 and "HTTPError" in r.text
    assert canary == []
    assert [x["path"] for x in receiver.ledger()["requests"]] == ["/redirect-chain"]


# --------------------------------------------------------------------- the egress proxy


def test_the_proxy_refuses_a_fixture_name_resolving_outside_the_test_network(monkeypatch):
    """A fixture host:port (allow_private) no longer accepts any address: public, link-local
    and off-network private answers are refused, loopback and the test network are not."""
    answers = {"public": ["8.8.8.8"], "meta": ["169.254.169.254"], "lan": ["10.0.0.5"],
               "mixed": ["127.0.0.1", "8.8.8.8"], "loop": ["127.0.0.1"],
               "testnet": ["10.231.47.9"], "mapped": ["::ffff:8.8.8.8"]}  # fmt: skip

    def fake_getaddrinfo(host, port, type=0):  # noqa: A002
        return [(2, 1, 6, "", (ip, port)) for ip in answers[host]]

    monkeypatch.setattr(egress_proxy.socket, "getaddrinfo", fake_getaddrinfo)
    keys = {(h, 8799) for h in answers}
    p = EgressProxy("/unused", allow=keys, allow_private=keys, networks=TEST_NET)
    for host in ("public", "meta", "lan", "mixed", "mapped"):
        assert p.check(host, 8799)[0] is None, host
    assert p.check("loop", 8799) == ("127.0.0.1", "allowed")
    assert p.check("testnet", 8799) == ("10.231.47.9", "allowed")
    assert EgressProxy("/unused", allow=keys, allow_private=keys).check("testnet", 8799)[0] is None


def _ask(sock_path: str, raw: bytes) -> bytes:
    c = socket.socket(socket.AF_UNIX)
    c.settimeout(10)
    c.connect(sock_path)
    c.sendall(raw)
    data = c.recv(200)
    c.close()
    return data


def test_the_proxy_checks_the_peer_it_actually_reached(receiver, monkeypatch):
    work = tempfile.mkdtemp(prefix="ne-proxytest-")
    sock = os.path.join(work, "p.sock")
    key = ("127.0.0.1", RECEIVER_PORT)
    proxy = EgressProxy(sock, allow={key}, allow_private={key}).start()
    req = f"GET {BASE}/apply/health-check HTTP/1.1\r\nHost: x\r\n\r\n".encode()
    try:
        assert _ask(sock, req).startswith(b"HTTP/1.1 200")  # control: the real peer passes
        receiver.reset()
        monkeypatch.setattr(egress_proxy, "peer_address", lambda writer: "8.8.8.8")
        assert b" 403 " in _ask(sock, req)
        assert receiver.ledger()["requests"] == []  # connected, but nothing relayed
        assert any(d.reason == "connected to an unchecked address" for d in proxy.decisions)
    finally:
        proxy.stop()
        shutil.rmtree(work, ignore_errors=True)


def test_the_proxy_service_takes_its_own_test_network_and_refuses_a_wide_one(monkeypatch):
    reg = proxy_service.Registry(60, TEST_NET)
    s = reg.create([("receiver", 8799)], [("receiver", 8799)])
    assert s.policy.networks == TEST_NET
    assert proxy_service.Registry(60).create([("receiver", 8799)], []).policy.networks == ()
    monkeypatch.setenv("EGRESS_CONTROL_TOKEN", "x" * 32)
    for bad in ('["10.0.0.0/8"]', '["8.8.8.0/24"]', '"10.231.47.0/24"', "{"):
        monkeypatch.setenv("EGRESS_FIXTURE_NETWORKS", bad)
        with pytest.raises(SystemExit, match="EGRESS_FIXTURE_NETWORKS"):
            proxy_service.main()


# ------------------------------------------------------------------------ execution


def test_a_fixture_is_never_browsed_without_the_egress_proxy(api, receiver, monkeypatch):
    with pytest.raises(IsolationUnavailable) as e:
        with browser_session(BASE, 5000, isolation="off", allow_private_destination=True):
            pass
    assert e.value.code == "fixture_needs_proxy"
    app_id = lever_application(api)
    aid = queue(api, app_id)
    receiver.reset()
    monkeypatch.setattr(get_settings(), "browser_isolation", "off")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["requests"] == []  # the browser never opened the form


def test_in_netns_mode_the_page_load_itself_passes_the_egress_proxy(receiver):
    """The Playwright driver runs outside the browser's namespace: a request it made itself
    would never reach the proxy. Every page load must show up in the proxy's decisions."""
    with browser_session(BASE, 8000, isolation="netns", allow_private_destination=True) as (
        page, log):  # fmt: skip
        page.goto(f"{BASE}/apply/health-check")
        seen = [(d.host, d.port) for d in log.proxy.decisions if d.allowed]
    assert seen.count(("127.0.0.1", RECEIVER_PORT)) >= 1, seen
    assert log.allowed >= 1 and log.blocked == []


def test_execution_through_a_listed_name_follows_where_it_resolves(api, receiver, listed, resolve):
    """Compose-style execution (`http://receiver:PORT`) through the real worker, namespace and
    egress proxy: it runs while the name resolves to loopback; once it resolves publicly, the
    proxy refuses the connection and nothing is disclosed."""
    listed(NAMED)
    resolve("receiver", "127.0.0.1")
    first = lever_application(api, url=f"{NAMED}/lever/examplehealth/{uuid.uuid4()}")
    assert runner.run_attempt(queue(api, first), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1

    receiver.reset()
    second = lever_application(api, url=f"{NAMED}/lever/examplehealth/{uuid.uuid4()}",
                               title="Registered Nurse, Day Shift")  # fmt: skip
    aid = queue(api, second)
    resolve("receiver", "8.8.8.8")  # after approval, before the browser opens the form
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    a = attempt(aid)
    assert a.state == "failed_safe" and a.outcome_detail.startswith("Stopped before sending")


@pytest.mark.parametrize("answer", ["8.8.8.8", "127.0.0.1"])
def test_a_client_that_hangs_up_never_crashes_the_proxy(monkeypatch, caplog, receiver, answer):
    """CI #124: a browser closing while the proxy answered it (a refusal, or a relayed reply)
    raised ConnectionResetError out of the connection handler, which asyncio logged with a
    traceback. A hang-up is not an error: nothing is logged and the proxy keeps serving."""
    import logging
    import time

    caplog.set_level(logging.DEBUG)
    real = egress_proxy.socket.getaddrinfo

    def slow(host, port, *a, **k):  # the client is gone before the proxy answers
        if host == "slow":
            time.sleep(0.3)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answer, RECEIVER_PORT))]
        return real(host, port, *a, **k)

    monkeypatch.setattr(egress_proxy.socket, "getaddrinfo", slow)
    work = tempfile.mkdtemp(prefix="ne-proxytest-")
    sock = os.path.join(work, "p.sock")
    key = ("slow", RECEIVER_PORT)
    proxy = EgressProxy(sock, allow={key}, allow_private={key}).start()
    try:
        for _ in range(3):
            c = socket.socket(socket.AF_UNIX)
            c.connect(sock)
            c.sendall(f"GET http://slow:{RECEIVER_PORT}/apply/health-check HTTP/1.1\r\n"
                      "Host: x\r\n\r\n".encode())  # fmt: skip
            c.close()
        time.sleep(1.2)
        req = f"GET {BASE}/apply/health-check HTTP/1.1\r\nHost: x\r\n\r\n".encode()
        proxy.allow.add(("127.0.0.1", RECEIVER_PORT))
        proxy.allow_private.add(("127.0.0.1", RECEIVER_PORT))
        assert _ask(sock, req).startswith(b"HTTP/1.1 200")  # still serving
    finally:
        proxy.stop()
        shutil.rmtree(work, ignore_errors=True)
    assert "Traceback" not in caplog.text and "Unhandled exception" not in caplog.text


def test_stopping_the_proxy_finishes_its_open_connections(receiver):
    """A connection still open when the proxy stops is finished there and then: nothing is left
    pending to be destroyed later, logging from whatever runs next."""
    work = tempfile.mkdtemp(prefix="ne-proxytest-")
    sock = os.path.join(work, "p.sock")
    key = ("127.0.0.1", RECEIVER_PORT)
    proxy = EgressProxy(sock, allow={key}, allow_private={key}).start()
    c = socket.socket(socket.AF_UNIX)
    try:
        c.settimeout(10)
        c.connect(sock)
        c.sendall(f"CONNECT 127.0.0.1:{RECEIVER_PORT} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        assert c.recv(200).startswith(b"HTTP/1.1 200")  # relaying, and left open
        proxy.stop()
        assert proxy._loop.is_closed() and not proxy._thread.is_alive()
    finally:
        c.close()
        shutil.rmtree(work, ignore_errors=True)
