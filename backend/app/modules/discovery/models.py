import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
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
    status: Mapped[str] = mapped_column(String(20))  # linked | incomplete
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String(100))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
