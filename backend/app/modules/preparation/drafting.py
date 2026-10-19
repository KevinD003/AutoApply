"""Optional long-form drafting interface.

No real LLM provider is wired in yet: `get_provider()` returns None, the API reports drafting as
unavailable, and users write long answers themselves. Tests inject a clearly labelled fake
provider to exercise the validation path. A real provider must implement `DraftProvider`, be
enabled only with server-side credentials, and report cost.

Grounding rules enforced on every draft, whatever the provider:
  * inputs are only approved profile facts and the job's own text, passed as data;
  * the output must cite at least one provided fact id and only provided ids;
  * every number in the draft must appear in the provided facts or job text (no invented
    metrics, years or headcounts);
  * the draft must fit the field's length limit and contain no template placeholders.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class GroundingFact:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class DraftRequest:
    question: str
    help_text: str | None
    max_chars: int
    employer: str | None
    job_title: str | None
    job_text: str | None
    facts: tuple[GroundingFact, ...]

    def input_hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass
class DraftResult:
    text: str
    evidence: list[str]
    provider: str
    model: str | None = None
    cost_usd: float | None = None
    raw: dict = field(default_factory=dict)


class DraftProvider(Protocol):
    name: str

    def draft(self, request: DraftRequest) -> DraftResult: ...


class DraftingUnavailable(RuntimeError):
    pass


class InvalidDraft(ValueError):
    pass


def get_provider() -> DraftProvider | None:
    """Return the configured provider, or None when drafting is not available."""
    return None


_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_PLACEHOLDER = re.compile(r"\[[A-Z][^\]]{0,40}\]|\{\{|\}\}|<[A-Z_ ]+>")


def validate_draft(req: DraftRequest, result: DraftResult) -> str:
    text = (result.text or "").strip()
    if not text:
        raise InvalidDraft("empty draft")
    if len(text) > req.max_chars:
        raise InvalidDraft(f"draft is {len(text)} characters; the limit is {req.max_chars}")
    if _PLACEHOLDER.search(text):
        raise InvalidDraft("draft contains template placeholders")
    ids = {f.id for f in req.facts}
    if not result.evidence or not set(result.evidence) <= ids:
        raise InvalidDraft("draft must cite only the facts it was given")
    source = " ".join([f.text for f in req.facts] + [req.job_text or "", req.question])
    known = {n.replace(",", "") for n in _NUM.findall(source)}
    invented = [n for n in _NUM.findall(text) if n.replace(",", "") not in known]
    if invented:
        raise InvalidDraft(f"draft contains numbers not found in your facts: {invented}")
    return text
