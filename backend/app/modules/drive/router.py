"""Google Drive import endpoints (D124, Phase F). Off until the owner enables and
configures it. The browser (Google Picker) sends one picked file id + a short-lived
`drive.file` token; the server downloads that one file and stores a snapshot."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.modules.documents.models import DocumentKind
from app.modules.documents.router import DocumentOut
from app.modules.drive import service
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/integrations/drive", tags=["drive"])

_BAD_REQUEST = {
    "bad_file_id",
    "bad_token",
    "unsupported_type",
    "unsupported_google_type",
    "content_mismatch",
    "too_large",
    "empty",
}


class DriveStatusOut(BaseModel):
    enabled: bool
    configured: bool
    client_id: str
    api_key: str
    scope: str
    max_bytes: int


class ImportIn(BaseModel):
    file_id: str = Field(min_length=1, max_length=256)
    access_token: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(default="", max_length=200)
    kind: DocumentKind = DocumentKind.resume


@router.get("/status", response_model=DriveStatusOut)
def drive_status(user: User = Depends(current_user)):
    return service.status()


@router.post("/import", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def drive_import(
    body: ImportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return service.import_file(
            db,
            user,
            file_id=body.file_id,
            access_token=body.access_token,
            name=body.name,
            mime_type=body.mime_type,
            kind=body.kind,
        )
    except service.DriveError as e:
        if e.code in ("drive_not_enabled", "drive_not_configured"):
            raise not_found("Google Drive import") from None
        if e.code in _BAD_REQUEST:
            raise bad_request(e.message) from None
        # drive_unreachable / drive_fetch_failed / drive_misconfigured
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from None
