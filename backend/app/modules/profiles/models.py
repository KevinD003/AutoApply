"""Candidate facts (true statements about the person) and targeting preferences (what they want).

Facts and preferences live in separate tables on purpose: a preference such as a desired city
must never leak into a factual answer such as current residence or work authorization.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class TriState(enum.StrEnum):
    yes = "yes"
    no = "no"
    unknown = "unknown"
    not_applicable = "not_applicable"


class Provenance(enum.StrEnum):
    user_entered = "user_entered"
    resume_parse = "resume_parse"
    import_ = "import"


class Approval(enum.StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"


class SalaryPeriod(enum.StrEnum):
    hour = "hour"
    day = "day"
    week = "week"
    month = "month"
    year = "year"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


tri = _enum(TriState, "tri_state")


class FactMixin:
    """Every reusable fact carries provenance, approval status, version and update time."""

    provenance: Mapped[Provenance] = mapped_column(
        _enum(Provenance, "provenance"), default=Provenance.user_entered
    )
    approval_status: Mapped[Approval] = mapped_column(
        _enum(Approval, "approval_status"), default=Approval.approved
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CandidateProfile(Base, FactMixin):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    # Actual residence. None means unknown; never filled from a target location.
    residence_country: Mapped[str | None] = mapped_column(String(2))
    residence_region: Mapped[str | None] = mapped_column(String(100))
    residence_city: Mapped[str | None] = mapped_column(String(100))
    links: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)


class WorkAuthorization(Base, FactMixin):
    """Per-country authorization and sponsorship. Three separate facts, never merged."""

    __tablename__ = "work_authorizations"
    __table_args__ = (UniqueConstraint("user_id", "country_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    country_code: Mapped[str] = mapped_column(String(2))
    authorized: Mapped[TriState] = mapped_column(tri, default=TriState.unknown)
    sponsorship_needed_now: Mapped[TriState] = mapped_column(tri, default=TriState.unknown)
    sponsorship_needed_future: Mapped[TriState] = mapped_column(tri, default=TriState.unknown)
    notes: Mapped[str | None] = mapped_column(Text)


class EmploymentRecord(Base, FactMixin):
    __tablename__ = "employment_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    employer: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)


class EducationRecord(Base, FactMixin):
    __tablename__ = "education_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(200))
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    completed: Mapped[TriState] = mapped_column(tri, default=TriState.unknown)


class Credential(Base, FactMixin):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)


class JobPreferences(Base):
    __tablename__ = "job_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    titles: Mapped[list] = mapped_column(JSON, default=list)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    seniority: Mapped[list] = mapped_column(JSON, default=list)
    employment_types: Mapped[list] = mapped_column(JSON, default=list)
    work_modes: Mapped[list] = mapped_column(JSON, default=list)
    excluded_employers: Mapped[list] = mapped_column(JSON, default=list)
    # [{"city": ..., "region": ..., "country": "CA"}] — targets, not residence.
    target_locations: Mapped[list] = mapped_column(JSON, default=list)
    willing_to_relocate: Mapped[TriState] = mapped_column(tri, default=TriState.unknown)
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(_enum(SalaryPeriod, "salary_period"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FactVersion(Base):
    """Immutable snapshot of a fact each time it changes."""

    __tablename__ = "fact_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
