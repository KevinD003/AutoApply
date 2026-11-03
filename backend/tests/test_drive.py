"""D124 Phase F: Google Drive import. Owner-activated, narrowest scope (drive.file),
download-only snapshot import. Off by default. A local fixture HTTP server stands in
for the Drive API (googleapis never contacted). Synthetic data only."""

import http.server
import socketserver
import threading

import pytest

from app.core.config import get_settings

PDF = b"%PDF-1.4\n% synthetic drive test\n"


class _Handler(http.server.BaseHTTPRequestHandler):
    bytes_for: dict[str, bytes] = {}
    calls: list[tuple[str, str]] = []

    def log_message(self, *a):  # keep test output quiet
        pass

    def _file_id(self) -> str:
        return self.path.split("/drive/v3/files/")[-1].split("?")[0].split("/")[0]

    def do_GET(self):
        _Handler.calls.append(("GET", self.path))
        data = _Handler.bytes_for.get(self._file_id())
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # If these are ever called the test fails its "read-only" assertion.
    def do_DELETE(self):
        _Handler.calls.append(("DELETE", self.path))
        self.send_response(204)
        self.end_headers()

    def do_PATCH(self):
        _Handler.calls.append(("PATCH", self.path))
        self.send_response(200)
        self.end_headers()


@pytest.fixture
def drive_server():
    _Handler.bytes_for = {}
    _Handler.calls = []
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield _Handler, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def enabled(monkeypatch, drive_server):
    _, base = drive_server
    s = get_settings()
    monkeypatch.setattr(s, "google_drive_enabled", True)
    monkeypatch.setattr(s, "google_drive_client_id", "synthetic.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_drive_api_key", "synthetic-api-key")
    monkeypatch.setattr(s, "google_drive_api_base", base)
    return drive_server


def _import(api, **over):
    body = {
        "file_id": "file123",
        "access_token": "synthetic-token",
        "name": "My Resume.pdf",
        "mime_type": "application/pdf",
    }
    body.update(over)
    return api.post("/integrations/drive/import", json=body)


def test_disabled_by_default(api):
    st = api.get("/integrations/drive/status").json()
    assert st["enabled"] is False and st["configured"] is False
    assert st["client_id"] == "" and st["api_key"] == ""
    assert _import(api).status_code == 404  # not set up


def test_status_when_enabled(api, enabled):
    st = api.get("/integrations/drive/status").json()
    assert st["enabled"] and st["configured"]
    assert st["scope"].endswith("/auth/drive.file")
    assert st["client_id"] and st["api_key"]


def test_import_creates_snapshot_and_only_reads_drive(api, enabled):
    handler, _ = enabled
    handler.bytes_for["file123"] = PDF
    r = _import(api)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["origin"] == "drive" and doc["kind"] == "resume" and doc["version"] == 1
    assert doc["label"].endswith(".pdf")
    assert any(d["id"] == doc["id"] for d in api.get("/documents").json())

    handler.bytes_for["file456"] = PDF
    r2 = _import(api, file_id="file456", name="Resume v2.pdf")
    assert r2.status_code == 201
    assert r2.json()["lineage_id"] != doc["lineage_id"]  # each import is its own snapshot

    # Drive was only ever read — never deleted or modified.
    assert handler.calls and all(method == "GET" for method, _ in handler.calls)


def test_rejects_unsupported_type(api, enabled):
    handler, _ = enabled
    handler.bytes_for["x"] = PDF
    assert (
        _import(
            api, file_id="x", name="thing.exe", mime_type="application/octet-stream"
        ).status_code
        == 400
    )


def test_rejects_content_mismatch(api, enabled):
    handler, _ = enabled
    handler.bytes_for["y"] = b"this is not a pdf"
    assert _import(api, file_id="y", name="resume.pdf").status_code == 400


def test_import_is_user_scoped(api, other_api, enabled):
    handler, _ = enabled
    handler.bytes_for["z"] = PDF
    mine = _import(api, file_id="z", name="mine.pdf").json()["id"]
    assert all(d["id"] != mine for d in other_api.get("/documents").json())
