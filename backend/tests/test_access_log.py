"""Access logs carry the method, the route template and the status only (core/access_log.py).

Requests carry synthetic markers in their paths, query strings and bodies: a posting question
key, a URL, a token-like string and applicant-like values. No route takes a question key in its
path any more (tests/test_api_paths.py); a request that puts one there anyway is unmatched.
Nothing contacts anything external; the real-server test starts uvicorn on a free loopback port
and stops only that process."""

import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from app.core.access_log import ACCESS_LOGGER, UNMATCHED

BACKEND = os.path.join(os.path.dirname(__file__), "..")
APP = "00000000-0000-0000-0000-0000000000a1"
QUERY = ("token=tok_SYNTHETIC&email=sam.synthetic%40example.com"
         "&next=https%3A%2F%2Fboards.example.com%2Fx")  # fmt: skip
MARKERS = ["question_8101", "tok_SYNTHETIC", "sam.synthetic", "boards.example.com", APP]
CLIENT = re.compile(r"\d+\.\d+\.\d+\.\d+:\d+ - \"")  # a client address before a request line


def access_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == ACCESS_LOGGER]


def clean(text: str) -> None:
    for m in MARKERS:
        assert m not in text, m


def test_access_lines_carry_the_route_template_never_the_raw_path(api, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    answer = {"key": "question_8101", "value": "Sam"}
    api.put(f"/applications/{APP}/answers?{QUERY}", json=answer)
    api.put(f"/applications/{APP}/answers/question_8101?{QUERY}", json={"value": "Sam"})
    api.get(f"/nope/question_8101?{QUERY}")

    def boom(*a, **kw):
        raise RuntimeError("question_8101 tok_SYNTHETIC")

    monkeypatch.setattr("app.modules.providers.routing.route_for_job", boom)
    from tests.test_greenhouse_dom import v2_job

    job = v2_job(api)
    caplog.clear()
    assert api.get(f"/jobs/{job}/route?{QUERY}").status_code == 500
    api.put(f"/applications/{APP}/answers?{QUERY}", json=answer)  # the key in the body
    api.put(f"/applications/{APP}/answers/question_8101?{QUERY}", json={"value": "Sam"})
    api.get(f"/nope/question_8101?{QUERY}")
    lines = access_lines(caplog)
    assert lines == [
        '- - "GET /api/jobs/{job_id}/route HTTP/1.1" 500',
        '- - "PUT /api/applications/{app_id}/answers HTTP/1.1" 422',
        f'- - "PUT {UNMATCHED} HTTP/1.1" 404',  # the old key-in-path form matches no route
        f'- - "GET {UNMATCHED} HTTP/1.1" 404',
    ]
    clean("\n".join(lines) + job)


def test_raw_access_records_from_the_server_are_dropped(api, caplog):
    caplog.set_level(logging.INFO)
    api.get("/auth/me")  # the app (and its filter) is installed
    caplog.clear()
    logging.getLogger(ACCESS_LOGGER).info(  # exactly what uvicorn itself would write
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:50000", "PUT",
        f"/api/applications/{APP}/answers/question_8101?{QUERY}", "1.1", 200,
    )  # fmt: skip
    assert access_lines(caplog) == []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, method: str = "GET") -> int:
    req = urllib.request.Request(url, method=method, data=b"{}" if method != "GET" else None)
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def test_the_real_server_prints_route_templates_only():
    """uvicorn with its default logging configuration, as every server command starts it."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=BACKEND, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )  # fmt: skip
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        codes = [
            _get(f"{base}/api/health?{QUERY}"),
            _get(f"{base}/api/applications/{APP}/answers?{QUERY}", "PUT"),
            _get(f"{base}/api/applications/{APP}/answers/question_8101?{QUERY}", "PUT"),
            _get(f"{base}/api/nope/question_8101?{QUERY}"),
            _get(f"{base}/api/jobs/{uuid.uuid4()}/route?{QUERY}"),
        ]
    finally:
        proc.terminate()  # only the server this test started
        out, _ = proc.communicate(timeout=20)
    assert codes[0] == 200 and codes[2] == codes[3] == 404, codes
    assert '"GET /api/health HTTP/1.1" 200' in out
    assert "PUT /api/applications/{app_id}/answers HTTP/1.1" in out
    assert f"PUT {UNMATCHED} HTTP/1.1" in out
    assert f"GET {UNMATCHED} HTTP/1.1" in out and "GET /api/jobs/{job_id}/route HTTP/1.1" in out
    clean(out)
    assert not CLIENT.search(out)  # no client address on any access line
