"""The runner's wait for a form's page to finish loading what it needs (runner._settle, D97).

A page is ready once none of its own document, script, stylesheet, fetch or XHR requests has
been in flight for QUIET_MS; a page still loading after SETTLE_LOAD_MS is not ready and the
attempt stops safely (test_dropdown_strategies checks that through the receiver's ledger).
Images, media, fonts, event streams and WebSockets are not waited on. The wait never types,
clicks or sends anything. A local page server only; every request it receives is recorded.
"""

import http.server
import os
import threading
import time

import pytest
from playwright.sync_api import sync_playwright

from app.modules.execution import runner

PAGES = {
    "/fast": "<form><input name='a'></form>",
    "/slow": "<form><input name='a'></form><script>fetch('/data/slow')</script>",
    "/never": "<form><input name='a'></form><script>fetch('/data/hang')</script>",
    # Started once the page has loaded and never finished: an image (a tracking pixel) and an
    # event stream, which change no control's behaviour or stay open by design. Not waited on.
    "/ignored": "<form><input name='a'></form><script>addEventListener('load', () => {"
    "const i = new Image(); i.src = '/img/hang'; document.body.append(i);"
    "new EventSource('/stream/hang'); })</script>",
}
SLOW_MS = 1200


class _Server:
    def __init__(self):
        self.release = threading.Event()  # set at teardown: hanging responses then end
        self.requests = []
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                srv.requests.append((self.command, self.path))
                if self.path in PAGES:
                    body, ctype = PAGES[self.path].encode(), "text/html"
                elif self.path == "/data/slow":
                    time.sleep(SLOW_MS / 1000)
                    body, ctype = b"{}", "application/json"
                elif self.path.endswith("/hang"):
                    srv.release.wait(30)
                    body, ctype = b"", "text/plain"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.release.set()
        self.httpd.shutdown()


@pytest.fixture(scope="module")
def server():
    s = _Server()
    yield s
    s.stop()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM_PATH") or None)
        yield b
        b.close()


def settle(browser, server, path):
    """Open the page as the runner does (tracker first, then the page) and time the wait."""
    page = browser.new_page()
    try:
        loading = runner._Loading(page)
        page.goto(server.base + path)
        t = time.monotonic()
        try:
            ready = runner._settle(page, loading)
        finally:
            loading.close()
        return ready, (time.monotonic() - t) * 1000, page.input_value("input[name=a]")
    finally:
        page.close()


def test_a_ready_page_proceeds_at_once(browser, server):
    ready, ms, typed = settle(browser, server, "/fast")
    assert ready and typed == ""
    assert ms < 1000, ms  # QUIET_MS plus polling, not a fixed allowance


def test_a_slow_request_of_the_page_is_waited_for(browser, server):
    ready, ms, _ = settle(browser, server, "/slow")
    assert ready
    assert ms >= SLOW_MS - 300, ms  # it waited for the slow request, not a quiet moment
    assert ms < runner.SETTLE_LOAD_MS, ms


def test_a_page_that_never_finishes_loading_is_not_ready(browser, server, monkeypatch):
    monkeypatch.setattr(runner, "SETTLE_LOAD_MS", 700)
    before = len(server.requests)
    ready, ms, typed = settle(browser, server, "/never")
    assert not ready and typed == ""
    assert 700 <= ms < 2500, ms  # bounded by the allowance
    # Only the page and its own request: the wait repeats nothing.
    assert [p for _, p in server.requests[before:]] == ["/never", "/data/hang"]


def test_images_and_event_streams_are_not_waited_for(browser, server):
    before = len(server.requests)
    ready, ms, _ = settle(browser, server, "/ignored")
    assert ready
    assert ms < 1000, ms
    assert {"/img/hang", "/stream/hang"} <= {p for _, p in server.requests[before:]}


def test_the_tracker_stops_listening_when_closed(browser, server):
    page = browser.new_page()
    try:
        loading = runner._Loading(page)
        loading.close()
        page.goto(server.base + "/slow")
        assert loading.pending == set()
    finally:
        page.close()
