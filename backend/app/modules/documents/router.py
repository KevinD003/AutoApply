import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import bad_request, conflict, not_found
from app.modules.audit.service import record
from app.modules.documents.models import Document, DocumentKind
from app.modules.documents.storage import Storage, get_storage
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/documents", tags=["documents"])
log = logging.getLogger("noefforts.documents")

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
    # L2/L3 (D73): a generated document is chosen only once accepted, for its own application.
    accepted_at: datetime | None = None
    made_for_application_id: uuid.UUID | None = None


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


# C17 (D70): why a document cannot be deleted now; the code is the "(reason: code)" suffix.
IN_USE = {
    "document_in_approval": "This document is in a package you approved. Revoke that approval "
    "first; nothing was deleted.",
    "document_in_attempt": "This document is part of a submission in progress. Wait for it to "
    "finish; nothing was deleted.",
}


def in_use(db: Session, user_id: uuid.UUID, ids: set[str]) -> str | None:
    """The reason the documents `ids` are needed now, under the locks of every application whose
    package names one: a live approval of that package, or an attempt still running on it.
    The applications are locked in id order (approve, revoke, claim and the gates take the same
    lock), so neither can start using one of them while the deletion runs."""
    from app.modules.execution.models import ACTIVE, ExecutionAttempt
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import ApplicationPackage

    naming = [
        p
        for p in db.scalars(select(ApplicationPackage).where(ApplicationPackage.user_id == user_id))
        if any(d.get("document_id") in ids for d in p.content.get("documents", []))
    ]
    for app_id in sorted({p.application_id for p in naming}):
        pk.lock_application(db, app_id)
    if any(pk.active_approval(db, p) is not None for p in naming):
        return "document_in_approval"
    running = db.scalar(
        select(ExecutionAttempt.id)
        .where(
            ExecutionAttempt.package_id.in_([p.id for p in naming]),
            ExecutionAttempt.state.in_(ACTIVE),
        )
        .limit(1)
    )
    return "document_in_attempt" if running is not None else None


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: uuid.UUID,
    scope: Literal["version", "lineage"] = Query(default="version"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> None:
    """C17 (D70): delete one version, or every version of the document. Refused while a live
    approval or a running attempt needs one of them. The rows go, with any application's choice
    of them (that package is rebuilt without the document and asks again), and then the files.
    Past package versions keep what they recorded: the id, version, size, type, digest and the
    name shown then."""
    from app.modules.applications.models import Application
    from app.modules.preparation.models import ApplicationInput

    doc = _owned(db, user, doc_id)
    q = select(Document).where(Document.user_id == user.id)
    q = (
        q.where(Document.lineage_id == doc.lineage_id)
        if scope == "lineage"
        else q.where(Document.id == doc.id)
    )
    docs = db.scalars(q.order_by(Document.version).with_for_update()).all()
    ids = {str(d.id) for d in docs}
    if (code := in_use(db, user.id, ids)) is not None:
        db.rollback()
        raise conflict(f"{IN_USE[code]} (reason: {code})")
    chosen = db.scalars(
        select(ApplicationInput)
        .join(Application, Application.id == ApplicationInput.application_id)
        .where(Application.user_id == user.id, ApplicationInput.kind == "document")
    ).all()
    for i in chosen:
        if (i.value or {}).get("document_id") in ids:
            db.delete(i)
    keys = [d.storage_key for d in docs]
    for d in docs:
        db.delete(d)
    record(db, user.id, "document.delete", "document", doc.id, scope=scope, versions=len(docs))
    db.commit()
    for key in keys:  # after the commit: a failed commit keeps both the rows and the files
        try:
            storage.delete(key)
        except OSError as e:
            log.warning("document file not removed: %s", type(e).__name__)


@router.post("/{doc_id}/propose-facts")
def propose_facts(
    doc_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    """L1 (D72): read this resume's text and propose the work history, education and credentials
    it states, each left `proposed` until you approve it in your profile (nothing uses a
    proposed fact). What you already have is not proposed again. The text is not kept."""
    from app.modules.documents.extract import ExtractError, extract_text
    from app.modules.profiles import resume_parse
    from app.modules.profiles.models import (
        Credential,
        EducationRecord,
        EmploymentRecord,
        Provenance,
    )
    from app.modules.profiles.service import apply_fact_update

    doc = _owned(db, user, doc_id)
    if doc.kind != DocumentKind.resume:
        raise bad_request("Facts are proposed from a resume only.")
    try:
        text = extract_text(doc.content_type, storage.get(doc.storage_key))
    except ExtractError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"{e} (reason: {e.code})"
        ) from None
    found = resume_parse.propose(text)

    def norm(*parts) -> tuple:
        return tuple(re.sub(r"\s+", " ", (p or "").lower()).strip() for p in parts)

    targets = (
        ("employment", EmploymentRecord, found.employment, ("title", "employer")),
        ("education", EducationRecord, found.education, ("degree", "institution")),
        ("credential", Credential, found.credential, ("name",)),
    )
    proposed, existing = {}, 0
    for entity, model, items, key in targets:
        have = {
            norm(*(getattr(r, k) for k in key))
            for r in db.scalars(select(model).where(model.user_id == user.id))
        }
        n = 0
        for item in items:
            k = norm(*(item.get(f) for f in key))
            if k in have:
                existing += 1
                continue
            have.add(k)
            apply_fact_update(db, model(user_id=user.id), item, entity_type=entity,
                              provenance=Provenance.resume_parse)  # fmt: skip
            n += 1
        proposed[entity] = n
    counts = {"proposed": proposed, "skipped": {"existing": existing,
                                                "sensitive": found.skipped_sensitive}}  # fmt: skip
    record(db, user.id, "document.facts_proposed", "document", doc.id,
           employment=proposed["employment"], education=proposed["education"],
           credential=proposed["credential"])  # fmt: skip
    db.commit()
    return counts
