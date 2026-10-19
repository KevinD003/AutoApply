import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_id, utcnow


class JobSource(enum.StrEnum):
    manual = "manual"
    url = "url"
    csv = "csv"
    xlsx = "xlsx"


class JobStatus(enum.StrEnum):
    new = "new"
    shortlisted = "shortlisted"
    excluded = "excluded"
    closed = "closed"


def _enum(e, name):
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_jobs_user_dedupe"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(200))
    employer: Mapped[str | None] = mapped_column(String(200))
    employer_key: Mapped[str | None] = mapped_column(String(200), index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    ats_provider: Mapped[str] = mapped_column(String(50), default="unknown")
    requisition_id: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[JobSource] = mapped_column(_enum(JobSource, "job_source"))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), default=JobStatus.new)
    exclusion_reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    posted_on: Mapped[date | None] = mapped_column(Date)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(10))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    # [{"row": 3, "row_id": "...", "outcome": "created|duplicate|error", "job_id", "errors"}]
    rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
