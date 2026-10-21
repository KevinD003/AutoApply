"""The submission-provider model: what a provider is, which operations it implements, and on
what evidence each capability rests (docs/provider-architecture.md).

Four kinds of provider exist:
  browser      fills and submits an employer's application form in the isolated browser
  api          submits through an officially authorized API (never without the user's
               explicit authorization and valid credentials)
  discovery    finds jobs; never fills or submits anything
  observation  reads a real page under a separately approved, read-only scope; never fills
  manual       the handoff when nothing else is supported: the user applies themselves

A capability is never advertised because a fixture supports it. Its support level records the
evidence separately (`Support`): implemented against a local fixture, observed on a real page,
supported for live filling, supported for live submission. Each level requires the previous
one (`check_spec`)."""

import enum
from dataclasses import dataclass, field


class Kind(enum.StrEnum):
    browser = "browser"
    api = "api"
    discovery = "discovery"
    observation = "observation"
    manual = "manual"


class Operation(enum.StrEnum):
    inspect = "inspect"
    extract_form = "extract_form"
    prepare = "prepare"
    validate_before_disclosure = "validate_before_disclosure"
    fill = "fill"
    upload = "upload"
    checkpoint = "checkpoint"
    submit = "submit"
    classify_outcome = "classify_outcome"
    collect_evidence = "collect_evidence"
    reconcile = "reconcile"
    discover = "discover"


class Capability(enum.StrEnum):
    discovery = "discovery"
    posting_read = "posting_read"
    form_extract = "form_extract"
    deterministic_fill = "deterministic_fill"
    custom_dropdowns = "custom_dropdowns"
    file_upload = "file_upload"
    location_picker = "location_picker"
    login_required = "login_required"
    email_verification = "email_verification"
    mobile_verification = "mobile_verification"
    captcha_checkpoint = "captcha_checkpoint"
    final_submit = "final_submit"
    confirmation_detection = "confirmation_detection"
    reconciliation = "reconciliation"
    official_api_submission = "official_api_submission"


@dataclass(frozen=True)
class Support:
    """Evidence for one capability. Absent from a spec = not implemented at all."""

    fixture: bool = False  # implemented and tested against a local fixture
    observed: bool = False  # seen on a real page or service (read-only, approved scope)
    live_fill: bool = False  # supported for filling a real destination
    live_submit: bool = False  # supported for submitting to a real destination
    note: str = ""

    def level(self) -> str:
        if self.live_submit:
            return "live_submit"
        if self.live_fill:
            return "live_fill"
        if self.observed:
            return "observed"
        return "fixture" if self.fixture else "none"


FIXTURE = Support(fixture=True)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: Kind
    description: str
    operations: frozenset[Operation]
    capabilities: dict[Capability, Support] = field(default_factory=dict)
    environments: tuple[str, ...] = ("development", "test")
    real_destinations_enabled: bool = False
    status: str = ""  # one line, honest about the evidence

    def support(self, cap: Capability) -> Support:
        return self.capabilities.get(cap, Support())

    def can(self, op: Operation) -> bool:
        return op in self.operations


class SpecError(ValueError):
    pass


def check_spec(spec: ProviderSpec) -> None:
    """Invariants every registered provider must satisfy."""
    for cap, s in spec.capabilities.items():
        if s.live_submit and not s.live_fill and cap != Capability.official_api_submission:
            raise SpecError(f"{spec.name}.{cap}: live submission without live filling")
        if (s.live_fill or s.live_submit) and not s.observed:
            raise SpecError(f"{spec.name}.{cap}: live support without real-page evidence")
        if s.observed and not s.fixture and spec.kind != Kind.observation:
            raise SpecError(f"{spec.name}.{cap}: observed but never implemented locally")
    live = any(s.live_fill or s.live_submit for s in spec.capabilities.values())
    if live and not spec.real_destinations_enabled:
        raise SpecError(f"{spec.name}: live capabilities while real destinations are disabled")
    if spec.real_destinations_enabled and "production" not in spec.environments:
        raise SpecError(f"{spec.name}: real destinations outside production make no sense")
    fills = {Operation.fill, Operation.upload, Operation.submit} & spec.operations
    if spec.kind in (Kind.discovery, Kind.observation, Kind.manual) and fills:
        raise SpecError(f"{spec.name}: a {spec.kind} provider cannot fill, upload or submit")
    if spec.kind == Kind.api and Capability.official_api_submission not in spec.capabilities:
        raise SpecError(f"{spec.name}: an API provider must declare official_api_submission")
    if spec.kind == Kind.browser and Capability.official_api_submission in spec.capabilities:
        raise SpecError(f"{spec.name}: a browser provider cannot claim API submission")


def matrix(spec: ProviderSpec) -> dict[str, str]:
    """{capability: level} for every capability (machine-readable; "none" when absent)."""
    return {c.value: spec.support(c).level() for c in Capability}
