import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class InboxSettings(Base):
    """D101: your choices for reading your own Gmail. Off until you turn each one on: verification
    codes for an application that is waiting for one, and application emails proposed as
    outcomes. `last_checked_at`: the end of the last completed read (the next one starts there);
    `last_error`: a fixed code, never a message from the provider."""

    __tablename__ = "inbox_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    codes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Suggest updates only (default), or automatically apply clear, well-matched, temporally
    # consistent updates (spec §4). An automatic change is still recorded, audited and undoable.
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InboxEvent(Base):
    """D101 + email status tracking: one email NoEfforts read, as what it said. Kept: a keyed
    reference to the message (so it is read once) and to its mail thread (so a later message in
    the same thread links to the same application), when it arrived, the sender's domain, the
    recognised event (`kind`), the two confidences kept apart (`match_band`, `class_band`), the
    match basis as short codes, the proposed and previous application outcome, the application it
    names (if one) and what happened (`state`). Never its text, subject, sender's name or a code.

    kind (the recognised recruitment event, spec §2): code | received | under_review | assessment
    | assessment_reminder | interview | interview_scheduled | interview_rescheduled |
    interview_cancelled | info_requested | next_round | offer | rejected | position_closed |
    withdrawn | talent_pool | recommendation | other | unclear.
    state: proposed (an outcome waiting for you) | review (match or meaning ambiguous — pick/
    confirm) | auto_applied (clear + well-matched, applied automatically per your setting) |
    accepted | dismissed | undone | relinked | unlinked (no single application named) |
    code_used | code_unclear | noted.
    match_band: strong | good | weak | ambiguous | none. class_band: explicit | ambiguous |
    tentative. match_basis: short codes only (e.g. "requisition_id,ats_sender"), never content."""

    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("user_id", "message_ref", name="uq_inbox_message"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_ref: Mapped[str] = mapped_column(String(64))
    thread_ref: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sender_domain: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(20))
    match_band: Mapped[str | None] = mapped_column(String(16))
    class_band: Mapped[str | None] = mapped_column(String(16))
    match_basis: Mapped[str | None] = mapped_column(String(120))
    proposed_outcome: Mapped[str | None] = mapped_column(String(24))
    prev_outcome: Mapped[str | None] = mapped_column(String(24))
    # The outcome an accept/auto-apply actually recorded, so undo can tell whether a newer update
    # has since superseded this event (then undo must refuse rather than clobber the newer state).
    applied_outcome: Mapped[str | None] = mapped_column(String(24))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InboxConsent(Base):
    """The owner's own authenticated consent to read application emails in their mailbox, recorded
    in the app (not in reviewed source) so activation needs no code change. It satisfies the inbox's
    application-email authorization gate for THIS user only; it never widens the server-wide
    `authorizations.RECORDED` register, and it covers only `read_application_email` — never codes,
    sending or submission. Auditable (who, when, the owner's attestation in their own words),
    time-bounded (`ends_on`, the last day it holds) and revocable (`revoked_at`). A grant inserts a
    new row; revoke stamps `revoked_at` on the active one, so the table is an append-only consent
    history. Cascades on user delete. Never holds message content or a token."""

    __tablename__ = "inbox_consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(
        String(32)
    )  # the scope; only "read_application_email" today
    attestation: Mapped[str] = mapped_column(String(500))  # the owner's own words, verbatim
    # The version of the in-app consent disclosure (the scope note and the authorize control's copy)
    # in force when this consent was given, so a later change to that wording never rewrites what a
    # past consent was granted against.
    disclosure_version: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_on: Mapped[date | None] = mapped_column(Date)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
