import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


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
    provider: Mapped[str] = mapped_column(String(50))
    source_job_id: Mapped[str] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(64))
    normalized: Mapped[dict] = mapped_column(JSON)
    source_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20))  # linked | incomplete | closed
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String(100))
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
