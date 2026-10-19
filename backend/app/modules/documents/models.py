import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class DocumentKind(enum.StrEnum):
    resume = "resume"
    cover_letter = "cover_letter"
    other = "other"


class Document(Base):
    """An immutable document version. Changing content means adding a new version row."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("lineage_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="document_kind", values_callable=lambda x: [m.value for m in x])
    )
    label: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(30), default="upload")  # upload | generated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
