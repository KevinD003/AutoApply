import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
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
    """A reusable answer, bound to the exact question it was given for.

    `question_key` hashes the normalized wording and answer shape, plus the normalized help text
    when the question has help text (bankscope.question_key, D51): a reworded question, or the
    same wording with other help text, never silently reuses an answer, and a question without
    help text keeps the key it had before C6, so no row is ever re-keyed. `help_text` is the help
    text as shown when saved: NULL = saved before C6 (not recorded; by its key such a row answers
    only a question without help text), "" = the question had none. Choice answers store option
    *labels* plus the option set seen at the time, so a changed option list is detected instead
    of mapped blindly.
    """

    __tablename__ = "answer_bank"
    __table_args__ = (UniqueConstraint("user_id", "question_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question_key: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    help_text: Mapped[str | None] = mapped_column(Text)  # C6 (D51)
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
    # For accepted drafts: {"draft_id", "evidence": [...], "grounding_hash"} so a later change
    # to the facts a draft relied on is detected.
    meta: Mapped[dict | None] = mapped_column(JSON)
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


class ApprovalScope(enum.StrEnum):
    """What an approval permits (docs/live-pilot-gate.md §2: permission C, disclosure, and
    permission D, submission). Fixed when the approval is given; not package content."""

    submit = "submit"  # fill, upload, check and submit once (C and D)
    disclose_only = "disclose_only"  # a rehearsal: fill, upload and check; never submit (C)


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
    # Execution method approved (execution.policy.execution_binding); NULL = given before
    # bindings were recorded (see policy.approved_binding).
    adapter: Mapped[str | None] = mapped_column(String(50))
    adapter_version: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(
        String(20), default=ApprovalScope.submit, server_default=ApprovalScope.submit.value
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    # E6: the attempt that met the rehearsal prerequisite when this approval to submit was given
    # (a rehearsal, or a submission that established the path; execution/rehearsal.py). No
    # foreign key: one would make a cycle with execution_attempts.approval_id, and an id that
    # no longer matches simply fails the check.
    prerequisite_attempt_id: Mapped[uuid.UUID | None] = mapped_column()


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
    # Erased when the user rejects the draft (C15, D68): a rejected draft's text is never kept.
    text: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    # C15 (D68): the cited facts' hash when drafted; None for drafts made before C15.
    grounding_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), default="proposed"
    )  # proposed|accepted|rejected
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DraftingConsent(Base):
    """L4 (D74): a user's agreement that drafting requests may be sent to an external provider,
    bound to the exact consent text (`consent_version`, its digest). It counts only for that
    text and until withdrawn; a changed text needs a new agreement."""

    __tablename__ = "drafting_consents"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    consent_version: Mapped[str] = mapped_column(String(64))
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DraftingUsage(Base):
    """L4 (D74): one request to an external drafting provider. Written with the request's worst
    case cost before it is sent (`reserved`), then set to what the provider reported
    (`settled`, once); a request whose outcome is unknown keeps its worst case. The day's budget
    is counted from these rows. Numbers and codes only: no text.

    `cost_basis` (D97) says what `cost_usd` is: `reserved` (the worst case held while the request
    runs), `estimated` (NoEfforts' estimate from the tokens the provider reported, at the list
    prices named by `price_version`), `unknown` (the worst case kept: the provider may have
    charged and nothing says what) or `not_sent` (refused before it left: 0). None of these is
    the provider's bill."""

    __tablename__ = "drafting_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date, index=True)  # UTC
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="reserved")  # reserved|settled
    outcome: Mapped[str | None] = mapped_column(String(50))
    reserved_usd: Mapped[float] = mapped_column(Numeric(10, 6))
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_basis: Mapped[str] = mapped_column(
        String(20), default="reserved", server_default="reserved"
    )
    price_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
