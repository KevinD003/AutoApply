"""Discovery providers find jobs. They never fill or submit anything, and a discovered job
implies nothing about whether NoEfforts can apply to it (that is providers.routing's question,
asked only once an application form has been captured).

A normalized record keeps the source's statements apart from the candidate's facts: whatever
the source says about sponsorship or work authorization is stored as a *source fact* with the
source named, tri-state, and never copied into the candidate's profile. Missing data stays
missing: nothing about sponsorship, authorization, salary, location or eligibility is inferred
from incomplete job data."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from app.modules.jobs.canonical import canonicalize_url, detect_ats

WORKPLACE = ("remote", "hybrid", "onsite", "unknown")


@dataclass
class NormalizedJob:
    source_provider: str
    source_job_id: str
    title: str | None
    employer: str | None
    location: str | None  # as the source gave it; None when absent (never guessed)
    workplace: str  # remote | hybrid | onsite | unknown
    job_url: str | None  # exactly as the source gave it
    application_url: str | None  # exactly as the source gave it
    ats_provider: str  # from the URL only; "unknown" otherwise
    published_on: date | None
    description_summary: str | None
    # Statements by the source, tri-state: "yes" / "no" only when the source states it.
    source_facts: dict = field(default_factory=dict)
    raw_fingerprint: str = ""
    closed_at_source: bool = False
    missing: list[str] = field(default_factory=list)  # why it cannot be linked automatically

    def as_dict(self) -> dict:
        d = asdict(self)
        d["published_on"] = self.published_on.isoformat() if self.published_on else None
        return d


def fingerprint(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()


def tri(value) -> str:
    return "yes" if value is True else "no" if value is False else "unknown"


class DiscoveryProvider:
    name: str

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> NormalizedJob:
        raise NotImplementedError


class FreehireMockProvider(DiscoveryProvider):
    """Potential future discovery provider; not yet connected or validated. Reads only a local
    synthetic file whose record shape is NoEfforts' own (FIXTURE ASSUMPTION), not Freehire's."""

    name = "freehire_mock"
    DEFAULT = Path(__file__).resolve().parents[4] / "fixtures" / "discovery" / "freehire_mock.json"

    def __init__(self, path: Path | None = None):
        self.path = path or self.DEFAULT

    def fetch(self) -> list[dict]:
        return json.loads(self.path.read_text())["jobs"]

    def normalize(self, raw: dict) -> NormalizedJob:
        job_url, apply_url = raw.get("url") or None, raw.get("apply_url") or None
        ats = detect_ats(canonicalize_url(apply_url or job_url)).provider if (
            apply_url or job_url) else "unknown"  # fmt: skip
        published = None
        if raw.get("published"):
            try:
                published = date.fromisoformat(raw["published"])
            except ValueError:
                published = None
        missing = []
        if not (job_url or apply_url):
            missing.append("no job or application URL")
        if not raw.get("title"):
            missing.append("no title")
        if not raw.get("company"):
            missing.append("no employer")
        workplace = raw.get("workplace") if raw.get("workplace") in WORKPLACE else "unknown"
        return NormalizedJob(
            source_provider=self.name,
            source_job_id=str(raw["id"]),
            title=raw.get("title"),
            employer=raw.get("company"),
            location=raw.get("location") or None,
            workplace=workplace,
            job_url=job_url,
            application_url=apply_url,
            ats_provider=ats,
            published_on=published,
            description_summary=(raw.get("summary") or None),
            source_facts={
                "sponsorship_offered": {
                    "value": tri(raw.get("visa_sponsorship")),
                    "stated_by": self.name,
                },
            },  # fmt: skip
            raw_fingerprint=fingerprint(raw),
            closed_at_source=bool(raw.get("closed")),
            missing=missing,
        )


PROVIDERS: dict[str, type[DiscoveryProvider]] = {"freehire_mock": FreehireMockProvider}
