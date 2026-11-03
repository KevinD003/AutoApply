"""Google Drive import (D124, Phase F) — owner-activated, narrowest scope.

The owner connects Drive in the browser with the Google Picker, which grants the
`drive.file` scope: access to *only the files the user picks*, never the whole
Drive. The browser sends the picked file's id and the short-lived OAuth access
token here; this module downloads that one file and stores it as a new, immutable
document version (a snapshot), exactly like an upload. It never lists or scans
Drive, never deletes or modifies anything in Drive, and never sends the content to
any AI provider. The access token is used once for the download and never stored.

It is off until the owner provides the (public) OAuth client id + API key via the
environment and enables it. No secret is requested in chat or kept in the repo.
"""

from __future__ import annotations

import hashlib
import re
import uuid

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.service import record
from app.modules.documents.models import Document, DocumentKind
from app.modules.documents.router import ALLOWED
from app.modules.documents.storage import get_storage
from app.modules.identity.models import User

# The only scope NoEfforts ever asks Drive for: files the user explicitly picks.
SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_API = "https://www.googleapis.com"

# Google-native documents are not binary; they must be exported. We export a Google
# Doc to PDF and then treat it as an ordinary PDF upload (validated the same way).
EXPORTS = {"application/vnd.google-apps.document": ("application/pdf", "pdf")}

_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class DriveError(Exception):
    """A Drive import problem, carrying a stable code for the API layer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def status() -> dict:
    s = get_settings()
    configured = bool(s.google_drive_client_id and s.google_drive_api_key)
    on = s.google_drive_enabled
    return {
        "enabled": on,
        "configured": on and configured,
        # These are public, embeddable browser values, never secrets.
        "client_id": s.google_drive_client_id if on else "",
        "api_key": s.google_drive_api_key if on else "",
        "scope": SCOPE,
        "max_bytes": s.max_upload_bytes,
    }


def _download(file_id: str, access_token: str, mime_type: str) -> tuple[bytes, str, str]:
    """Download exactly one picked file from the Drive API. Returns (bytes,
    content_type, extension). Never follows redirects; only talks to the configured
    Google base (a local fixture base is allowed only in the test environment)."""
    s = get_settings()
    base = s.google_drive_api_base.rstrip("/")
    if s.env != "test" and base != GOOGLE_API:
        raise DriveError("drive_misconfigured", "Drive import must use the Google API.")

    export = EXPORTS.get(mime_type)
    if mime_type.startswith("application/vnd.google-apps") and not export:
        raise DriveError("unsupported_google_type", "This Google file type cannot be imported.")
    if export:
        url, params = f"{base}/drive/v3/files/{file_id}/export", {"mimeType": export[0]}
    else:
        url, params = f"{base}/drive/v3/files/{file_id}", {"alt": "media"}

    try:
        with httpx.Client(timeout=30, follow_redirects=False) as c:
            r = c.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError:
        raise DriveError("drive_unreachable", "Google Drive could not be reached.") from None
    if r.status_code != 200:
        raise DriveError("drive_fetch_failed", "Google Drive did not return the file.")
    data = r.content
    if len(data) > s.max_upload_bytes:
        raise DriveError("too_large", "The file is too large.")
    if not data:
        raise DriveError("empty", "The file is empty.")
    # The extension the stored document takes: the export target, or the picked name's.
    ext = export[1] if export else ""
    return data, (export[0] if export else ""), ext


def import_file(
    db: Session,
    user: User,
    *,
    file_id: str,
    access_token: str,
    name: str,
    mime_type: str,
    kind: DocumentKind = DocumentKind.resume,
) -> Document:
    """Import one Picker-selected Drive file as a new document snapshot. Never
    touches Drive beyond the single read, and never reuses the token afterwards."""
    s = get_settings()
    if not s.google_drive_enabled:
        raise DriveError("drive_not_enabled", "Google Drive import is not enabled on this server.")
    if not (s.google_drive_client_id and s.google_drive_api_key):
        raise DriveError(
            "drive_not_configured", "Google Drive import is not configured on this server."
        )
    if not _FILE_ID.match(file_id or ""):
        raise DriveError("bad_file_id", "That does not look like a Drive file id.")
    if not access_token or len(access_token) > 4096:
        raise DriveError("bad_token", "A valid access token is required.")
    label = _SAFE_NAME.sub("", (name or "").strip())[:200] or "Imported document"

    data, forced_type, forced_ext = _download(file_id, access_token, mime_type)
    ext = forced_ext or (label.rsplit(".", 1)[-1].lower() if "." in label else "")
    if ext not in ALLOWED:
        raise DriveError("unsupported_type", "Only PDF, DOCX or TXT files can be imported.")
    content_type, looks_ok = ALLOWED[ext]
    if not looks_ok(data):
        raise DriveError("content_mismatch", "The file content does not match its type.")
    if forced_ext and not label.lower().endswith(f".{forced_ext}"):
        label = f"{label}.{forced_ext}"

    doc = Document(
        user_id=user.id,
        lineage_id=uuid.uuid4(),  # each import is its own snapshot lineage
        version=1,
        kind=kind,
        label=label,
        original_filename=label,
        content_type=forced_type or content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=get_storage().put(data),
        origin="drive",
    )
    db.add(doc)
    db.flush()
    record(db, user.id, "document.drive_import", "document", doc.id, version=1)
    db.commit()
    db.refresh(doc)
    return doc
