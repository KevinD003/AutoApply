"""Proposed profile facts from a resume's text (L1, D72). Pure: no database, no LLM, no network.

Only what the text states in a recognisable layout is proposed, as work history, education and
credentials; the user approves each one before anything uses it. Under a section heading
("Experience", "Education", "Certifications" ...):

- a work entry is a line "Title at Employer", or "Title — Employer" with an en or em dash, a
  spaced hyphen or a bar; the bullet lines under it are its description;
- an education entry is one line, with the institution after the same separators (or the whole
  line as the institution);
- a credential is one line: its name, an issuer after a separator or "issued by", and an
  expiry only when written as a full date (YYYY-MM-DD).

Never proposed: dates other than a full credential expiry (a written range stays in the
description, as written), whether studies were completed, anything about work authorization,
sponsorship or immigration status, and any line touching a sensitive topic (classify), which is
skipped and counted. Lines outside the known sections are ignored.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.modules.preparation import classify

SECTIONS = {
    "employment": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "relevant experience"),
    "education": ("education", "education and training", "academic background",
                  "academic history"),
    "credential": ("certifications", "certificates", "certification", "licenses", "licences",
                   "licenses and certifications", "licences and certifications",
                   "certifications and licenses", "certifications and licences", "credentials"),
    "other": ("summary", "profile", "professional summary", "objective", "skills",
              "technical skills", "core skills", "key skills", "projects", "references",
              "languages", "volunteer", "volunteering", "interests", "awards", "publications",
              "contact"),
}  # fmt: skip
_HEADING = {h: kind for kind, names in SECTIONS.items() for h in names}
_SEP = re.compile(r"\s+(?:—|–|-|\|)\s+")
_AT = re.compile(r"^(?P<a>.+?)\s+at\s+(?P<b>.+)$", re.I)
_BULLET = re.compile(r"^[•\-*·▪◦–]\s*")
# A trailing date range as written ("Jan 2019 – Present", "(2019-2022)"): kept, never parsed.
_DATES = re.compile(
    r"[\s,(]*((?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?"
    r"(?:19|20)\d\d\s*(?:—|–|-|to)\s*(?:(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|"
    r"dec)[a-z]*\.?\s+)?(?:19|20)\d\d|present|current|now))\)?\s*$",
    re.I,
)
_ISSUED_BY = re.compile(r"^(?P<a>.+?),?\s+issued by\s+(?P<b>.+)$", re.I)
_EXPIRES = re.compile(
    r"[\s,(]*(?:expires|expiry|valid until|exp\.?)\s*:?\s*(?P<d>\d{4}-\d\d-\d\d)\)?", re.I
)


@dataclass
class Proposals:
    employment: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    credential: list[dict] = field(default_factory=list)
    skipped_sensitive: int = 0


def _heading(line: str) -> str | None:
    key = re.sub(r"[^a-z ]+", "", line.lower().replace("&", " and ")).strip()
    key = re.sub(r"\s+", " ", key)
    return _HEADING.get(key) if len(line) <= 60 else None


def _split(line: str) -> tuple[str, str | None]:
    m = _AT.match(line)
    if m:
        return m.group("a").strip(), m.group("b").strip()
    parts = _SEP.split(line, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return line.strip(), None


def _clip(text: str | None, n: int = 200) -> str | None:
    return text[:n].strip() or None if text else None


def propose(text: str) -> Proposals:
    out = Proposals()
    section = None
    current = None  # the work entry the bullet lines belong to
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = _heading(line)
        if kind is not None:
            section, current = kind, None
            continue
        if section in (None, "other"):
            continue
        if classify.mentions_legal_status(line) or classify.mentions_sensitive(line):
            out.skipped_sensitive += 1
            continue
        bullet = bool(_BULLET.match(line))
        line = _BULLET.sub("", line).strip()
        if section == "employment":
            if bullet and current is not None:
                current["lines"].append(line)
                continue
            dates = _DATES.search(line)
            head = line[: dates.start()].strip(" ,(") if dates else line
            title, employer = _split(head)
            if employer is None:
                if current is not None:
                    current["lines"].append(line)
                continue
            current = {"title": _clip(title), "employer": _clip(employer), "lines": []}
            if dates:
                current["lines"].insert(0, f"Dates as written: {dates.group(1).strip()}")
            out.employment.append(current)
        elif section == "education":
            current = None
            degree, institution = _split(line)
            if institution is None:
                degree, institution = None, line
            out.education.append({"degree": _clip(degree), "institution": _clip(institution)})
        elif section == "credential":
            current = None
            expires = None
            m = _EXPIRES.search(line)
            if m:
                try:
                    expires = date.fromisoformat(m.group("d"))
                except ValueError:
                    expires = None
                line = (line[: m.start()] + line[m.end() :]).strip(" ,")
            m = _ISSUED_BY.match(line)
            name, issuer = (m.group("a"), m.group("b")) if m else _split(line)
            out.credential.append(
                {"name": _clip(name), "issuer": _clip(issuer), "expires_on": expires}
            )
    for e in out.employment:
        e["description"] = _clip("\n".join(e.pop("lines")), 10_000)
    return out
