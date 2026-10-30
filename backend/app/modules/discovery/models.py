import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class BoardSource(Base):
    """D95: one employer's public job board that you added (Greenhouse, Lever or Ashby), read
    only when you ask. `board` is the identifier the provider's public postings API uses; the
    request URL is built from it and the provider's fixed host, never taken as a URL. Status
    fields say what the last read did; nothing here is an application route."""

    __tablename__ = "board_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "region", "board", name="uq_board_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))  # greenhouse | lever | ashby
    region: Mapped[str] = mapped_column(String(10), default="global")  # lever: global | eu
    board: Mapped[str] = mapped_column(String(100))
    employer: Mapped[str] = mapped_column(String(200))  # what you call this employer
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))  # ok | failed
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    last_count: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscoveredJob(Base):
    """One source record, as the discovery provider last reported it. Linked to a tracker job
    (deduplicated with the user's existing jobs) when it is complete enough; otherwise it waits
    for a manual import. Source statements live in `source_facts`, never in the profile."""

    __tablename__ = "discovered_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "source_job_id", name="uq_discovered_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # D95: the job board this posting was read from; removing the source removes its postings
    # (a job you saved from one stays in your jobs).
    board_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("board_sources.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    source_job_id: Mapped[str] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(64))
    normalized: Mapped[dict] = mapped_column(JSON)
    source_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20))  # linked | incomplete | closed
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String(100))
    # S3 (D59): when the source first said it was stale; a later report that it is still stale
    # keeps this time, so a "still open" statement made after it holds.
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # How the record was matched to a tracker job: new_job | application_url | job_url |
    # employer_title_location | previous_link; None when not linked.
    link_basis: Mapped[str | None] = mapped_column(String(40))
    # The filter outcome of the last import: {"result": match | insufficient, "fields": [...]}.
    filter_result: Mapped[dict | None] = mapped_column(JSON)
    # Fields that changed at the source in the last refresh (names only). The tracker job is
    # never changed by a refresh: the user decides.
    changed_fields: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A reference for debugging, never the raw payload: provider, id, fingerprint, field names.
    raw_ref: Mapped[dict | None] = mapped_column(JSON)


class DiscoveryRunApproval(Base):
    """The owner's approval of one live discovery run (D55): the exact search, the page limit,
    the time window and the retention statement, recorded by the owner with
    `python -m app.modules.discovery.approve`. Used once, before the first request, so a run that
    fails needs a new approval; nothing re-runs on its own."""

    __tablename__ = "discovery_run_approvals"
    __table_args__ = (
        CheckConstraint("max_pages BETWEEN 1 AND 5", name="ck_run_approval_pages"),
        CheckConstraint("not_after > not_before", name="ck_run_approval_window"),
        CheckConstraint("length(trim(query)) > 0", name="ck_run_approval_query"),
        CheckConstraint("length(trim(retention)) > 0", name="ck_run_approval_retention"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    query: Mapped[str] = mapped_column(String(200))
    max_pages: Mapped[int] = mapped_column(Integer)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retention: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscoveryWatch(Base):
    """The owner's standing approval to check one search again and again (D56): the exact
    search, how often (at least once a minute), until when (at most 90 days) and the retention
    statement, recorded with `python -m app.modules.discovery.watch create`. A worker task checks
    a due watch, newest postings first, and stops at the first posting it already has. Stopped
    (`revoked_at`) by the owner at any time; paused (`paused_reason`) when it may not run, or
    after ten failures in a row. `requests_on_day` counts this watch's requests on `budget_day`
    (UTC) for the daily cap."""

    __tablename__ = "discovery_watches"
    __table_args__ = (
        CheckConstraint("interval_seconds BETWEEN 60 AND 86400", name="ck_watch_interval"),
        CheckConstraint("not_after > not_before", name="ck_watch_window"),
        CheckConstraint("not_after <= not_before + interval '90 days'", name="ck_watch_length"),
        CheckConstraint("length(trim(query)) > 0", name="ck_watch_query"),
        CheckConstraint("length(trim(retention)) > 0", name="ck_watch_retention"),
        CheckConstraint("failures >= 0 AND requests_on_day >= 0", name="ck_watch_counts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    query: Mapped[str] = mapped_column(String(200))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retention: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_reason: Mapped[str | None] = mapped_column(String(40))
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_outcome: Mapped[str | None] = mapped_column(String(40))
    failures: Mapped[int] = mapped_column(Integer, default=0)
    found_total: Mapped[int] = mapped_column(Integer, default=0)
    budget_day: Mapped[date | None] = mapped_column(Date)
    requests_on_day: Mapped[int] = mapped_column(Integer, default=0)


class DiscoveryBackoff(Base):
    """S6 (D67): when a provider refused this user's requests with a Retry-After, the time
    before which NoEfforts sends it none of this user's imports or refreshes. Never re-run by
    itself: the user imports again after that time."""

    __tablename__ = "discovery_backoffs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
