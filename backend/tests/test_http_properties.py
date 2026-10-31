"""D103: the standard-library HTTP clients that reach real services (the Gmail reader and its
token exchange, D101; the Greenhouse pilot's reads, D102), checked for the properties the owner
listed, on real sockets:

* explicit timeouts, and a silent server is given up on within them;
* TLS certificates verified, with the hostname: an untrusted certificate is refused;
* redirects never followed, and nothing sent to where one points;
* bounded answers: a larger one is refused, never read in full or read truncated as if whole;
* sanitized errors: fixed codes, never an answer's text, a token or a header;
* nothing of a token, an authorization header or a message's content in the logs.

Real Google and Greenhouse hosts are never contacted. Their openers are the same as these:
`public_https_opener` for HTTPS, and `fixture_opener` for the local stand-ins, with the same
request code (`GmailReader._send`, `connect._post`, `live.fetch`)."""

import ast
import http.server
import json
import logging
import socket
import ssl
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from app.core import urlsafety
from app.core.config import get_settings
from app.modules.execution import live
from app.modules.inbox import connect, provider
from app.modules.inbox.provider import GmailReader, InboxUnavailable

APP = Path(__file__).resolve().parents[1] / "app"
REFRESH = "SYNTHETIC-REFRESH-TOKEN-7Q2"  # synthetic credentials: tests only
SECRET = "SYNTHETIC-CLIENT-SECRET-4K8"
ACCESS = "SYNTHETIC-ACCESS-TOKEN-9Z1"
SUBJECT = "SYNTHETIC-SUBJECT-LINE-3M5"


# -- TLS and the openers themselves ---------------------------------------------------------------


def _https_handler(opener) -> urllib.request.HTTPSHandler:
    (h,) = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
    return h


@pytest.mark.parametrize("no_redirect", [provider._NoRedirect, connect._NoRedirect,
                                         live._NoRedirect])  # fmt: skip
def test_public_openers_verify_certificates_and_use_no_proxy(monkeypatch, no_redirect):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")  # an environment proxy is ignored
    opener = urlsafety.public_https_opener("gmail.googleapis.com", no_redirect)
    ctx = _https_handler(opener)._context
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    kinds = {type(h) for h in opener.handlers}
    for refused in (urllib.request.ProxyHandler, urllib.request.FileHandler,
                    urllib.request.DataHandler, urllib.request.FTPHandler):  # fmt: skip
        assert refused not in kinds, refused
    assert any(isinstance(h, no_redirect) for h in opener.handlers)


@pytest.fixture
def self_signed(tmp_path):
    """A certificate for localhost that no system trusts (made here, for this test only)."""
    key, cert = tmp_path / "key.pem", tmp_path / "cert.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost"],
        check=True, capture_output=True, timeout=60,
    )  # fmt: skip
    return key, cert


def _tls_server(key: Path, cert: Path) -> tuple[http.server.HTTPServer, int]:
    class Ok(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Ok)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_an_untrusted_certificate_is_refused(self_signed, monkeypatch):
    """The opener's own context against a live TLS server with a certificate it does not trust:
    refused. The same server with the certificate trusted answers, so the refusal is the
    verification and nothing else. (Loopback is allowed here for the test only; the public
    opener refuses it otherwise.)"""
    key, cert = self_signed
    srv, port = _tls_server(key, cert)
    monkeypatch.setattr(urlsafety, "_check_ip", lambda ip: None)
    ctx = _https_handler(urlsafety.public_https_opener("localhost", provider._NoRedirect))._context
    try:
        conn = urlsafety._PublicHTTPSConnection("localhost", port, timeout=5, context=ctx)
        with pytest.raises(ssl.SSLCertVerificationError):
            conn.request("GET", "/")
        trusting = ssl.create_default_context(cafile=str(cert))
        ok = urlsafety._PublicHTTPSConnection("localhost", port, timeout=5, context=trusting)
        ok.request("GET", "/")
        assert ok.getresponse().status == 200
    finally:
        srv.shutdown()


def test_loopback_is_refused_before_any_connection():
    ctx = ssl.create_default_context()
    conn = urlsafety._PublicHTTPSConnection("localhost", 9, timeout=5, context=ctx)
    with pytest.raises(urlsafety.UnsafeURL):
        conn.connect()


def test_a_silent_server_is_given_up_on_within_the_timeout(monkeypatch):
    """It accepts the connection and never answers the TLS handshake."""
    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)
    monkeypatch.setattr(urlsafety, "_check_ip", lambda ip: None)
    conn = urlsafety._PublicHTTPSConnection("localhost", silent.getsockname()[1], timeout=0.5,
                                            context=ssl.create_default_context())  # fmt: skip
    started = time.monotonic()
    try:
        with pytest.raises((TimeoutError, OSError)):
            conn.connect()
    finally:
        silent.close()
    assert time.monotonic() - started < 5


def test_every_request_to_a_real_service_has_an_explicit_timeout():
    """Each `.open(` of an opener in these modules passes `timeout=`; none waits for ever. (Not
    `os.open`, the token file, or `webbrowser.open`, the owner's own browser.)"""
    for rel in ("modules/inbox/provider.py", "modules/inbox/connect.py",
                "modules/execution/live.py"):  # fmt: skip
        tree = ast.parse((APP / rel).read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "open"
                 and ast.unparse(n.func.value) not in ("os", "webbrowser")]  # fmt: skip
        assert calls, rel
        for c in calls:
            assert any(k.arg == "timeout" for k in c.keywords), (rel, ast.unparse(c))


# -- the Gmail reader against a misbehaving server ------------------------------------------------


class _Server:
    """A local stand-in that misbehaves on purpose, by path; it counts what reaches it."""

    def __init__(self):
        self.seen: list[str] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def _reply(self, status: int, body: bytes, headers=()):
                self.send_response(status)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up first, as it should

            def do_POST(self):  # noqa: N802 - the token endpoint
                outer.seen.append(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                if self.path.startswith("/text-token"):
                    return self._reply(200, b"<html>not json " + SUBJECT.encode() + b"</html>")
                self._reply(200, json.dumps({"access_token": ACCESS}).encode())

            def do_GET(self):  # noqa: N802
                outer.seen.append(self.path)
                if self.path.startswith("/redirect"):
                    return self._reply(302, b"", [("Location", f"{outer.base}/elsewhere")])
                if self.path.startswith("/big"):
                    return self._reply(200, b" " * (provider.MAX_REPLY + 10))
                if self.path.startswith("/slow"):
                    time.sleep(3)
                    return self._reply(200, b"{}")
                if self.path.startswith("/fail"):
                    return self._reply(500, json.dumps({"error": SUBJECT}).encode())
                self._reply(200, json.dumps({"messages": [{"id": "m1"}], "subject": SUBJECT})
                            .encode())  # fmt: skip

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()


@pytest.fixture
def server(monkeypatch, tmp_path):
    s = _Server()
    monkeypatch.setattr(get_settings(), "fixture_origins",
                        [*get_settings().fixture_origins, s.base])  # fmt: skip
    yield s
    s.stop()


def _reader(server, tmp_path, path: str, token: str = "/token", timeout: float = 5.0):
    creds = tmp_path / "token.json"
    creds.write_text(json.dumps({"client_id": "synthetic-client", "client_secret": SECRET,
                                 "refresh_token": REFRESH}))  # fmt: skip
    return GmailReader(str(creds), f"{server.base}{path}", f"{server.base}{token}", timeout)


@pytest.mark.parametrize(
    "path,token,code",
    [
        ("/redirect", "/token", "bad_reply"),  # never followed
        ("/big", "/token", "bad_reply"),  # larger than MAX_REPLY: refused, not truncated
        ("/fail", "/token", "bad_reply"),  # an error answer's body is never read
        ("/ok", "/text-token", "bad_reply"),  # a token answer that is not JSON
    ],
)
def test_the_reader_refuses_with_a_fixed_code_and_logs_nothing_private(
    server, tmp_path, caplog, capsys, path, token, code
):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(InboxUnavailable) as e:
        _reader(server, tmp_path, path, token).received_after(
            __import__("datetime").datetime(2026, 1, 1)
        )
    assert e.value.code == code and str(e.value) == code  # the code, nothing else
    assert not [p for p in server.seen if p.startswith("/elsewhere")]  # the redirect's target
    out, err = capsys.readouterr()
    for private in (REFRESH, SECRET, ACCESS, SUBJECT, "Bearer", "Authorization"):
        assert private not in caplog.text + out + err, private


def test_a_slow_answer_is_given_up_on_within_the_readers_timeout(server, tmp_path):
    started = time.monotonic()
    with pytest.raises(InboxUnavailable) as e:
        _reader(server, tmp_path, "/slow", timeout=0.5).received_after(
            __import__("datetime").datetime(2026, 1, 1)
        )
    assert e.value.code == "unreachable" and time.monotonic() - started < 2.5


def test_a_successful_read_logs_no_token_header_or_content(server, tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    ids = _reader(server, tmp_path, "/ok").received_after(
        __import__("datetime").datetime(2026, 1, 1), limit=1
    )
    assert ids == ["m1"]
    out, err = capsys.readouterr()
    for private in (REFRESH, SECRET, ACCESS, SUBJECT, "Bearer"):
        assert private not in caplog.text + out + err, private


# -- the token exchange (connect.py) --------------------------------------------------------------


@pytest.mark.parametrize(
    "body,ok",
    [
        (b"<html>not json</html>", False),
        (b"[1, 2]", False),
        (b" " * (connect.MAX_REPLY + 1), False),
        (json.dumps({"refresh_token": "r", "scope": connect.SCOPE}).encode(), True),
    ],
)
def test_the_token_exchange_reads_only_a_whole_json_object(monkeypatch, body, ok):
    """A non-JSON or non-object answer reads as nothing (no refresh token: refused with a fixed
    message), and an answer larger than allowed is refused, never parsed truncated."""

    class Answer:
        status = 200

        def __init__(self, data: bytes):
            self.data = data

        def read(self, n: int) -> bytes:
            return self.data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout):
            assert timeout == 20
            return Answer(body)

    monkeypatch.setattr(connect, "public_https_opener", lambda host, nr: Opener())
    client = {"token_uri": "https://oauth2.googleapis.com/token", "client_id": "c",
              "client_secret": SECRET}  # fmt: skip
    if ok:
        assert connect.exchange(client, "code", "http://127.0.0.1:1/", "v")["refresh_token"] == "r"
        return
    with pytest.raises(connect.ConnectError) as e:
        connect.exchange(client, "code", "http://127.0.0.1:1/", "v")
    assert SECRET not in str(e.value) and "html" not in str(e.value)
