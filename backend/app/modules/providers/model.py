"""The submission-provider model: what a provider is, which operations it implements, and on
what evidence each capability rests (docs/provider-architecture.md).

Five kinds of provider exist:
  browser      fills and submits an employer's application form in the isolated browser
  api          submits through an officially authorized API (never without the user's
               explicit authorization and valid credentials)
  discovery    finds jobs; never fills or submits anything
  observation  reads a real page under a separately approved, read-only scope; never fills
  manual       the handoff when nothing else is supported: the user applies themselves

A capability is never advertised because a fixture supports it. Its support level records the
evidence separately (`Support`): implemented against a local fixture, observed on a real page,
supported for live filling, supported for live submission. Each level requires the previous
one (`check_spec`).

Workflow traits are kept apart from capabilities: whether an ATS needs a login, a manual
verification step, may show a CAPTCHA or spans several pages says what the workflow demands,
not what NoEfforts can do. A trait is "yes"/"no" only with evidence; "expected" for a planned
adapter's specification; "unknown" otherwise.

The routing vocabulary (`ROUTING_CAPABILITIES`) and the execution interface (`INTERFACE`) are
the names used in docs/provider-architecture.md; both are views over the capabilities and
operations below, never separate claims."""

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


class Trait(enum.StrEnum):
    login_required = "login_required"
    manual_verification_required = "manual_verification_required"
    captcha_possible = "captcha_possible"
    multi_step = "multi_step"


TRAIT_VALUES = ("yes", "no", "expected", "unknown", "not_applicable")


@dataclass(frozen=True)
class TraitValue:
    value: str = "unknown"  # one of TRAIT_VALUES
    note: str = ""


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
    traits: dict[Trait, TraitValue] = field(default_factory=dict)
    stage: str = "implemented"  # "implemented" | "planned" (a specification only: no code)
    ats: str | None = None  # the ATS identity (jobs.canonical.detect_ats) this provider serves
    # Repository paths of the local fixtures its `fixture` levels were tested against (never
    # served; tests/test_provider_contracts.py checks they exist).
    tested_against: tuple[str, ...] = ()

    def support(self, cap: Capability) -> Support:
        return self.capabilities.get(cap, Support())

    def can(self, op: Operation) -> bool:
        return op in self.operations

    def trait(self, t: Trait) -> TraitValue:
        return self.traits.get(t, TraitValue())


# D102: providers that may name real destinations as a pilot, by the owner's decision: off by
# default, never claiming live support (their levels stay the fixture's and the read-only
# observations'), gated in code (execution/live.py). Nothing else may.
PILOTS = frozenset({"greenhouse_live"})


class SpecError(ValueError):
    pass


Op = Operation
# The operations that can implement each capability (any one of them). A capability nothing
# implements is a claim without code.
CAPABILITY_OPERATIONS: dict[Capability, frozenset[Operation]] = {
    Capability.discovery: frozenset({Op.discover}),
    Capability.posting_read: frozenset({Op.inspect}),
    Capability.form_extract: frozenset({Op.extract_form}),
    Capability.deterministic_fill: frozenset({Op.fill}),
    Capability.custom_dropdowns: frozenset({Op.fill, Op.extract_form}),
    Capability.file_upload: frozenset({Op.upload}),
    Capability.location_picker: frozenset({Op.fill, Op.extract_form}),
    Capability.login_required: frozenset({Op.checkpoint}),
    Capability.email_verification: frozenset({Op.checkpoint}),
    Capability.mobile_verification: frozenset({Op.checkpoint}),
    Capability.captcha_checkpoint: frozenset({Op.checkpoint}),
    Capability.final_submit: frozenset({Op.submit}),
    Capability.confirmation_detection: frozenset({Op.classify_outcome}),
    Capability.reconciliation: frozenset({Op.reconcile, Op.checkpoint}),
    Capability.official_api_submission: frozenset({Op.submit}),
}
# The capability (any one of them) an implemented operation must declare, so an operation is
# never present without its evidence level. Operations not listed need none of their own.
OPERATION_CAPABILITIES: dict[Operation, frozenset[Capability]] = {
    Op.inspect: frozenset({Capability.posting_read}),
    Op.extract_form: frozenset({Capability.form_extract}),
    Op.fill: frozenset({Capability.deterministic_fill}),
    Op.upload: frozenset({Capability.file_upload}),
    Op.submit: frozenset({Capability.final_submit, Capability.official_api_submission}),
    Op.classify_outcome: frozenset({Capability.confirmation_detection}),
    Op.reconcile: frozenset({Capability.reconciliation}),
    Op.discover: frozenset({Capability.discovery}),
}


def check_spec(spec: ProviderSpec) -> None:
    """Invariants every registered provider must satisfy (registry.check_registry adds the ones
    across providers; providers/admission.py computes what the evidence admits)."""
    if spec.stage not in ("implemented", "planned"):
        raise SpecError(f"{spec.name}: unknown stage {spec.stage}")
    if spec.stage == "planned" and (spec.operations or spec.capabilities):
        raise SpecError(f"{spec.name}: a planned adapter has no operations or capabilities")
    for t, v in spec.traits.items():
        if v.value not in TRAIT_VALUES:
            raise SpecError(f"{spec.name}.{t}: unknown trait value {v.value}")
        if v.value == "expected" and spec.stage != "planned":
            raise SpecError(f"{spec.name}.{t}: 'expected' is only for a planned specification")
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
    for cap in spec.capabilities:
        if not CAPABILITY_OPERATIONS[cap] & spec.operations:
            raise SpecError(f"{spec.name}.{cap}: capability without the operation behind it")
    if spec.stage == "implemented":
        for op in spec.operations:
            if op in OPERATION_CAPABILITIES and not OPERATION_CAPABILITIES[op] & set(
                spec.capabilities
            ):
                raise SpecError(f"{spec.name}.{op}: operation without the capability it implements")
    for t, v in spec.traits.items():
        if v.value in ("yes", "no") and not v.note.strip():
            raise SpecError(f"{spec.name}.{t}: a yes/no trait needs its evidence (a note)")
        if spec.stage == "planned" and v.value not in ("expected", "unknown"):
            raise SpecError(f"{spec.name}.{t}: a planned specification states expectations only")
        if v.value == "not_applicable" and spec.kind in (Kind.browser, Kind.api):
            raise SpecError(f"{spec.name}.{t}: not_applicable is not for a browser or API provider")
    if (
        spec.stage == "implemented"
        and any(s.fixture for s in spec.capabilities.values())
        and not spec.tested_against
    ):
        raise SpecError(f"{spec.name}: fixture support without the fixture it was tested against")
    if (
        spec.kind == Kind.browser
        and spec.stage == "implemented"
        and spec.trait(Trait.captcha_possible).value != "no"
        and Capability.captcha_checkpoint not in spec.capabilities
    ):
        raise SpecError(f"{spec.name}: a CAPTCHA may appear but no checkpoint is declared")
    if spec.real_destinations_enabled and spec.name not in PILOTS:
        raise SpecError(
            f"{spec.name}: real destinations stay refused until the live-pilot gate is opened by a "
            "reviewed change to this rule"
        )
    if spec.real_destinations_enabled and live:
        raise SpecError(f"{spec.name}: a pilot claims no live support (its evidence is its own)")


def matrix(spec: ProviderSpec) -> dict[str, str]:
    """{capability: level} for every capability (machine-readable; "none" when absent)."""
    return {c.value: spec.support(c).level() for c in Capability}


# The execution interface, as named in docs/provider-architecture.md. Each name is implemented by
# the operations listed (the runner drives them; adapters keep their own method names).
INTERFACE: dict[str, tuple[Operation, ...]] = {
    "inspect_application": (Operation.inspect,),
    "extract_form_schema": (Operation.extract_form,),
    "prepare_application": (Operation.prepare,),
    "validate_application": (Operation.validate_before_disclosure,),
    "request_user_action": (Operation.checkpoint,),
    "upload_documents": (Operation.upload,),
    "submit_application": (Operation.submit,),
    "collect_confirmation_evidence": (Operation.classify_outcome, Operation.collect_evidence),
    "reconcile_unknown_outcome": (Operation.reconcile,),
}


def interface(spec: ProviderSpec) -> dict[str, bool]:
    """{interface operation: implemented} — implemented only when every operation behind it is."""
    return {name: all(spec.can(op) for op in ops) for name, ops in INTERFACE.items()}


# The routing vocabulary: capability names → the evidence-levelled capability behind each (or
# the workflow trait). A view, never a separate claim.
ROUTING_CAPABILITIES: dict[str, Capability | Trait] = {
    "discovery": Capability.discovery,
    "public_schema_read": Capability.posting_read,
    "API_submission": Capability.official_api_submission,
    "browser_inspection": Capability.form_extract,
    "browser_fill": Capability.deterministic_fill,
    "document_upload": Capability.file_upload,
    "login_required": Trait.login_required,
    "manual_verification_required": Trait.manual_verification_required,
    "CAPTCHA_possible": Trait.captcha_possible,
    "multi_step": Trait.multi_step,
    "location_picker": Capability.location_picker,
    "custom_dropdown": Capability.custom_dropdowns,
    "confirmation_detection": Capability.confirmation_detection,
}


def routing_view(spec: ProviderSpec) -> dict[str, str]:
    """{routing name: support level, or trait value}. Browser inspection is reported only for
    providers that read pages in a browser (browser and observation kinds)."""
    out = {}
    for name, ref in ROUTING_CAPABILITIES.items():
        if isinstance(ref, Trait):
            out[name] = spec.trait(ref).value
        elif name == "browser_inspection" and spec.kind not in (Kind.browser, Kind.observation):
            out[name] = "none"
        else:
            out[name] = spec.support(ref).level()
    return out
