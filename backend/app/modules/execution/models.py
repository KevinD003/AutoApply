"""Durable execution records. Broker messages carry only attempt ids; everything that matters
lives here, in PostgreSQL."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class AttemptState(enum.StrEnum):
    pending = "pending"  # waiting for a worker to claim it
    claimed = "claimed"  # a worker holds the lease; nothing irreversible yet
    sending = "sending"  # final gate passed; the submit click may be in flight
    awaiting_code = "awaiting_code"  # employer asked for a verification code after sending
    confirmed = "confirmed"  # employer receipt observed
    unknown = "unknown"  # may or may not have been accepted: reconcile, never auto-retry
    rejected = "rejected"  # employer explicitly refused (validation, expired session)
    failed_safe = "failed_safe"  # stopped before disclosing anything
    abandoned = "abandoned"  # data disclosed (fill/upload) but not submitted; user decides
    # A rehearsal (approval scope disclose_only) ended as approved: filled, uploaded, read
    # back and re-checked, then stopped before the send gate. Nothing was submitted.
    rehearsed = "rehearsed"
    cancelled = "cancelled"


ACTIVE = (
    AttemptState.pending,
    AttemptState.claimed,
    AttemptState.sending,
    AttemptState.awaiting_code,
)


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        # At most one active attempt per application, enforced by the database.
        Index(
            "uq_one_active_attempt",
            "application_id",
            unique=True,
            postgresql_where=text("state IN ('pending','claimed','sending','awaiting_code')"),
        ),
        CheckConstraint(
            "destination_class IS NULL OR destination_class IN ('fixture','real')",
            name="ck_attempt_destination_class",
        ),
        CheckConstraint(
            "rehearsal_prerequisite IS NULL OR "
            "rehearsal_prerequisite IN ('met','established','not_required')",
            name="ck_attempt_rehearsal_prerequisite",
        ),
        Index("ix_execution_attempts_user_path", "user_id", "path_ref", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application_packages.id"))
    package_hash: Mapped[str] = mapped_column(String(64))
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("package_approvals.id"))
    adapter: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(20), default=AttemptState.pending)
    # Fencing token: incremented on every claim. Every worker write is conditional on it.
    generation: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # D134: queued by your standing rule (D113), not by you; a pause or the rule's switch
    # stops it before anything is sent.
    queued_by_rule: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # "fixture" or "real" (rehearsal.destination_class), fixed when queued; NULL = queued before
    # it was recorded, which counts in no evidence class.
    destination_class: Mapped[str | None] = mapped_column(String(10))
    # E6: the employer/provider path (user, adapter, origin, board) as a keyed reference
    # (rehearsal.path_ref), computed when queued; NULL when no path can be derived or for an
    # attempt queued before it was recorded. Never served, logged or audited.
    path_ref: Mapped[str | None] = mapped_column(String(64))
    # How the send gate found the rehearsal prerequisite: met (a valid rehearsal), established
    # (an earlier confirmed submission on the path), not_required (fixture paths); NULL = the
    # send gate was never passed, or passed before this was recorded.
    rehearsal_prerequisite: Mapped[str | None] = mapped_column(String(20))
    disclosure_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AttemptEvent(Base):
    """Append-only attempt history. Never contains codes, cookies or answer values."""

    __tablename__ = "attempt_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), index=True
    )
    generation: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxMessage(Base):
    """Transactional outbox: written in the same transaction as the attempt, published later.
    A crash between publish and marking dispatched causes a duplicate delivery, which the
    claim compare-and-swap ignores. D146: `dispatched_at` is the time of the last publication
    and `publish_attempts` counts them all: an attempt still waiting to be taken is published
    again from its newest message (`service.republish_waiting`)."""

    __tablename__ = "outbox_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(50))
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class Checkpoint(Base):
    """A pause for the user, e.g. an emailed verification code. Bound to user and attempt.
    The code is held only until the worker consumes it, then erased."""

    __tablename__ = "checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30), default="email_code")
    # open -> submitted -> (consumed -> open again on a wrong code) ... -> done/expired/failed
    status: Mapped[str] = mapped_column(String(20), default="open")
    round: Mapped[int] = mapped_column(Integer, default=1)
    code: Mapped[str | None] = mapped_column(String(32))
    wrong_attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    message: Mapped[str | None] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


PAUSE_UNRESOLVED = ("open", "unexplained")


class ApplicationPause(Base):
    """D132: an application stopped, before anything was entered on the page, because the
    employer's form no longer matched the approved one in a way a fresh read can show. It
    outlives its attempt by design, which is never resumed or retried. While it is unresolved
    the application has no live approval and none can be given: the owner reads the form again
    (a new form version resolves it), tries this version again (closes it), or the application
    leaves review. Counts only, never a question's key or label.

    status: open (read the form again), unexplained (read again, no difference NoEfforts can
    see), resolved (a new form version was read), closed (tried again, superseded, or the
    application left review: cancelled, applied by hand, expired, failed, submitted).

    kind: form_changed (D132, before anything was entered), or conditional_required (D135, after
    filling and before the send gate: the page showed and required a question it reveals by its
    own logic, with no approved answer; it is answered, then tried again)."""

    __tablename__ = "application_pauses"
    __table_args__ = (
        Index(
            "uq_one_unresolved_pause",
            "application_id",
            unique=True,
            postgresql_where=text("status IN ('open','unexplained')"),
        ),
        Index("ix_application_pauses_user_status", "user_id", "status"),
        CheckConstraint("kind IN ('form_changed','conditional_required')", name="ck_pause_kind"),
        CheckConstraint(
            "status IN ('open','unexplained','resolved','closed')", name="ck_pause_status"
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('new_form','dismissed','superseded',"
            "'cancelled','expired','failed','submitted')",
            name="ck_pause_resolution",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), default="form_changed")
    status: Mapped[str] = mapped_column(String(20), default="open")
    # The package the attempt ran (for display and the version diff; the gate is the pause).
    package_version: Mapped[int] = mapped_column(Integer)
    package_hash: Mapped[str] = mapped_column(String(64))
    # The form version the attempt ran against (a read must find a different one).
    form_version: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # counts only
    recaptured_version: Mapped[int | None] = mapped_column(Integer)
    # How it ended (ck_pause_resolution).
    resolution: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evidence(Base):
    """Minimal outcome evidence. No answer values, cookies, codes, screenshots or traces."""

    __tablename__ = "execution_evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # disclosure | readback | recheck | egress | receipt | step (D142: one page of a wizard read
    # back before its Next: {page, checked, mismatched})
    kind: Mapped[str] = mapped_column(String(30))
    # employer_receipt | employer_confirmation_page | api_receipt | none
    strength: Mapped[str] = mapped_column(String(30), default="none")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RehearsalRecord(Base):
    """What a rehearsal proved, written by the rehearsal stop in the same transaction that ends
    the attempt `rehearsed` (service.finish_rehearsal), after every gate check passed again.
    Counts and fixed values only: no host, URL, board, field key, file or page text. It holds
    while its evidence rows still match it (rehearsal.assess_record); a withdrawn or deleted
    one is revoked, never edited back."""

    __tablename__ = "rehearsal_records"
    __table_args__ = (
        CheckConstraint("destination_class IN ('fixture','real')", name="ck_rehearsal_class"),
        CheckConstraint("route IN ('browser','api')", name="ck_rehearsal_route"),
        CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN ('withdrawn_by_user','evidence_deleted')",
            name="ck_rehearsal_revoked_reason",
        ),
        Index("ix_rehearsal_records_user_adapter", "user_id", "adapter"),
        Index("ix_rehearsal_records_user_path", "user_id", "path_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), unique=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("package_approvals.id"))
    destination_class: Mapped[str] = mapped_column(String(10))
    route: Mapped[str] = mapped_column(String(10))  # browser | api
    adapter: Mapped[str] = mapped_column(String(50))
    adapter_version: Mapped[str] = mapped_column(String(100))
    # The attempt's path_ref, copied at the stop (NULL for one made before paths were recorded,
    # which then counts for no path).
    path_ref: Mapped[str | None] = mapped_column(String(64))
    uploads_expected: Mapped[int] = mapped_column(Integer)
    uploads_acknowledged: Mapped[int] = mapped_column(Integer)
    readback_mismatched: Mapped[int | None] = mapped_column(Integer)  # NULL on the API route
    recheck_matched: Mapped[bool] = mapped_column(Boolean)
    egress_proxy_denied: Mapped[int] = mapped_column(Integer, default=0)
    unresolved: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(30))


class InstanceStamp(Base):
    """D147: which database this is. A restored database cannot know what happened after its
    backup was taken, so it has to know that it was restored: `db_oid` is the oid PostgreSQL
    gave the database the stamp was written in, and `cluster_id` the system identifier of its
    server's cluster (made by `initdb`). A restore into a new database on the same server (the
    deployment guide's §7) changes the oid; a restore onto another server changes the cluster's
    identifier, while the oid may well repeat (every new cluster gives its first database the
    same one: 16384, measured). The stamp is restored with the rest, so it differs until the
    restore is resolved (`execution.restore`). One row (`id` 1)."""

    __tablename__ = "instance_stamp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    db_oid: Mapped[int] = mapped_column(BigInteger)
    cluster_id: Mapped[int] = mapped_column(BigInteger)
    stamped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The last restore found and resolved here, and what resolving it did (counts only).
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restore_summary: Mapped[dict | None] = mapped_column(JSON)
