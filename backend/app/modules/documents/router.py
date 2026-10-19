import hashlib
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.modules.audit.service import record
from app.modules.documents.models import Document, DocumentKind
from app.modules.documents.storage import Storage, get_storage
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/documents", tags=["documents"])

# extension -> (content type, magic-byte check)
ALLOWED = {
    "pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        lambda b: b.startswith(b"PK\x03\x04"),
    ),
    "txt": ("text/plain", lambda b: b"\x00" not in b[:4096]),
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lineage_id: uuid.UUID
    version: int
    kind: DocumentKind
    label: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    origin: str
    created_at: datetime


def _owned(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise not_found("Document")
    return doc


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: DocumentKind = Form(DocumentKind.resume),
    label: str | None = Form(default=None, max_length=200),
    lineage_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """Upload a new document, or a new version of an existing one via `lineage_id`."""
    settings = get_settings()
    name = _SAFE_NAME.sub("_", (file.filename or "document").rsplit("/", 1)[-1])[:255]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise bad_request("Allowed file types: PDF, DOCX, TXT")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise bad_request("File is too large")
    if not data:
        raise bad_request("File is empty")
    content_type, looks_ok = ALLOWED[ext]
    if not looks_ok(data):
        raise bad_request("File content does not match its extension")

    version = 1
    if lineage_id is not None:
        prev = db.scalar(
            select(Document)
            .where(Document.lineage_id == lineage_id, Document.user_id == user.id)
            .order_by(Document.version.desc())
            .limit(1)
        )
        if prev is None:
            raise not_found("Document")
        version = prev.version + 1
        kind, label = prev.kind, label or prev.label
    else:
        lineage_id = uuid.uuid4()

    doc = Document(
        user_id=user.id,
        lineage_id=lineage_id,
        version=version,
        kind=kind,
        label=label or name,
        original_filename=name,
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=storage.put(data),
    )
    db.add(doc)
    db.flush()
    record(db, user.id, "document.upload", "document", doc.id, version=version)
    db.commit()
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Latest version of each document lineage."""
    latest = (
        select(Document.lineage_id, func.max(Document.version).label("v"))
        .where(Document.user_id == user.id)
        .group_by(Document.lineage_id)
        .subquery()
    )
    return db.scalars(
        select(Document)
        .join(
            latest, (Document.lineage_id == latest.c.lineage_id) & (Document.version == latest.c.v)
        )
        .order_by(Document.created_at.desc())
    ).all()


@router.get("/{doc_id}/versions", response_model=list[DocumentOut])
def versions(doc_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = _owned(db, user, doc_id)
    return db.scalars(
        select(Document)
        .where(Document.lineage_id == doc.lineage_id, Document.user_id == user.id)
        .order_by(Document.version)
    ).all()


@router.get("/{doc_id}/download")
def download(
    doc_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    doc = _owned(db, user, doc_id)
    return Response(
        storage.get(doc.storage_key),
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.original_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
