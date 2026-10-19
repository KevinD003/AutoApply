import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.profiles.models import Approval, Provenance, SalaryPeriod, TriState

_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _country(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip().upper()
    if not _COUNTRY.match(v):
        raise ValueError("country must be an ISO 3166-1 alpha-2 code, e.g. US, CA, IN")
    return v


class FactMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provenance: Provenance
    approval_status: Approval
    version: int
    updated_at: datetime


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    residence_country: str | None = None
    residence_region: str | None = Field(default=None, max_length=100)
    residence_city: str | None = Field(default=None, max_length=100)
    links: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)

    _c = field_validator("residence_country")(_country)


class ProfileOut(ProfileIn, FactMeta):
    pass


class WorkAuthorizationIn(BaseModel):
    country_code: str
    authorized: TriState = TriState.unknown
    sponsorship_needed_now: TriState = TriState.unknown
    sponsorship_needed_future: TriState = TriState.unknown
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("country_code")
    @classmethod
    def _cc(cls, v: str) -> str:
        out = _country(v)
        if out is None:
            raise ValueError("country_code is required")
        return out


class WorkAuthorizationOut(WorkAuthorizationIn, FactMeta):
    pass


class _Dated(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class EmploymentIn(_Dated):
    employer: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    is_current: bool = False
    description: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def _current(self):
        if self.is_current and self.end_date:
            raise ValueError("a current position cannot have an end_date")
        return self


class EmploymentOut(EmploymentIn, FactMeta):
    pass


class EducationIn(_Dated):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    completed: TriState = TriState.unknown


class EducationOut(EducationIn, FactMeta):
    pass


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issued_on: date | None = None
    expires_on: date | None = None


class CredentialOut(CredentialIn, FactMeta):
    pass


class TargetLocation(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    country: str | None = None

    _c = field_validator("country")(_country)


class PreferencesIn(BaseModel):
    titles: list[str] = Field(default_factory=list, max_length=50)
    fields: list[str] = Field(default_factory=list, max_length=50)
    industries: list[str] = Field(default_factory=list, max_length=50)
    seniority: list[str] = Field(default_factory=list, max_length=20)
    employment_types: list[str] = Field(default_factory=list, max_length=10)
    work_modes: list[str] = Field(default_factory=list, max_length=3)
    excluded_employers: list[str] = Field(default_factory=list, max_length=500)
    target_locations: list[TargetLocation] = Field(default_factory=list, max_length=50)
    willing_to_relocate: TriState = TriState.unknown
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: SalaryPeriod | None = None

    @field_validator("work_modes")
    @classmethod
    def _modes(cls, v: list[str]) -> list[str]:
        allowed = {"remote", "hybrid", "onsite"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"work_modes must be among {sorted(allowed)}")
        return v

    @model_validator(mode="after")
    def _salary(self):
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_max < self.salary_min:
                raise ValueError("salary_max must be >= salary_min")
        if (self.salary_min is not None or self.salary_max is not None) and not (
            self.salary_currency and self.salary_period
        ):
            raise ValueError("salary_currency and salary_period are required with a salary")
        return self


class PreferencesOut(PreferencesIn):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime | None = None
