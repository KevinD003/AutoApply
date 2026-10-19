import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow
from app.modules.profiles.models import FactMixin


class JobForm(Base):
    """A captured application-form schema for a job. New captures add versions."""

    __tablename__ = "job_forms"
    __table_args__ = (UniqueConstraint("job_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30))  # fixture | html | manual
    source_ref: Mapped[str | None] = mapped_column(String(200))
    extraction_version: Mapped[str] = mapped_column(String(30))
    fingerprint: Mapped[str] = mapped_column(String(64))
    schema: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnswerBankEntry(Base, FactMixin):
    """A reusable answer, bound to the exact wording it was given for.

    `question_key` hashes the normalized wording and answer shape, so a reworded question never
    silently reuses an answer. Choice answers store option *labels* plus the option set seen at
    the time, so a changed option list is detected instead of mapped blindly.
    """

    __tablename__ = "answer_bank"
    __table_args__ = (UniqueConstraint("user_id", "question_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question_key: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    answer_shape: Mapped[str] = mapped_column(String(20))
    value: Mapped[dict] = mapped_column(JSON)
    options_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    source_application_id: Mapped[uuid.UUID | None] = mapped_column()


class ApplicationInput(Base):
    """Per-application user input: an answer, a consent choice, or a document selection."""

    __tablename__ = "application_inputs"
    __table_args__ = (UniqueConstraint("application_id", "kind", "field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))  # answer | consent | document
    field_key: Mapped[str] = mapped_column(String(200))
    value: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(30), default="user_entered")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ApplicationPackage(Base):
    """Immutable snapshot of everything that would be sent. Rows are never updated."""

    __tablename__ = "application_packages"
    __table_args__ = (UniqueConstraint("application_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_summary: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PackageApproval(Base):
    """Approval bound to one package version and its content hash."""

    __tablename__ = "package_approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_packages.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)


class AnswerDraft(Base):
    """A long-form draft proposed by an LLM provider. Never used until the user accepts it."""

    __tablename__ = "answer_drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    field_key: Mapped[str] = mapped_column(String(200))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(20), default="proposed"
    )  # proposed|accepted|rejected
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
