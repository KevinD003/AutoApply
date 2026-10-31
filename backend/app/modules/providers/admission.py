"""Provider admission (I2, docs/provider-admission.md): how far each provider's code tables and
recorded evidence take it on the admission ladder. Computed, never declared.

  * The ladder (`STAGES`) runs from registered to live. Each provider climbs the track of its
    kind (`TRACKS`): an execution provider for an ATS climbs all of it; a generic fixture
    adapter, an observation, a discovery provider and the manual handoff end earlier, each
    with its own fixed end code.
  * A stage is reached when every check (`CHECKS`) at or before it is met, and every earlier
    stage was reached. Each check evaluates one of the eleven framework requirements
    (`REQUIREMENTS`) from code tables or recorded evidence; a check that does not apply to a
    provider is "not_applicable".
  * The owner approves four boundaries (`OWNER_BOUNDARIES`): a public-docs and terms review,
    each read-only run, permission to disclose (C) and permission to submit (D). Code can only
    point at a recorded approval (providers/evidence.py; readiness.DISCLOSURE_PERMISSION_RECORDED
    and SUBMISSION_PERMISSION_RECORDED);
    it can never give one. None is recorded for a new stage today.
  * Nothing passes `MAX_REACHABLE`: a real disclosure or submission stays refused whatever the
    tables say (`real_destinations_refused`).
  * What a provider claims (its support state, providers/wording.py) must never rank above
    what it is admitted to (tests/test_provider_admission.py). A provider registered before
    I2 keeps its claim through frozen waivers (`GRANDFATHERED`), shown as waived, never met,
    and never counted above that claim.

Advisory upward: admission changes no route, label, approval, package or flag, and only the
providers API imports it. It reads no database, file or network, and never imports browser
code: everything it needs is a Python constant (`current_tables`). The CI-only repository
facts behind its tables (fixture paths exist, scenario tests read the receiver ledger, known
gaps still reproduce, identity cases cover every ATS) are checked by
tests/test_provider_contracts.py."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.modules.providers import wording
from app.modules.providers.model import (
    PILOTS,
    Capability,
    Kind,
    Operation,
    ProviderSpec,
    SpecError,
    Trait,
    check_spec,
)

C = Capability

# The provider framework's eleven requirements, in its order.
REQUIREMENTS = (
    "identity",
    "capability_matrix",
    "workflow_traits",
    "route_logic",
    "adapter_versioning",
    "privacy",
    "audit",
    "fixtures",
    "manual_evidence",
    "support_state",
    "pilot_gate",
)
STAGES = (
    "not_admitted",
    "registered",
    "planned",
    "public_doc_reviewed",
    "fixture_only",
    "observed_read_only",
    "rehearsal_ready",
    "rehearsed",
    "live",
)
TRACKS: dict[str, tuple[str, ...]] = {
    "ats_execution": STAGES[1:],
    "generic_execution": ("registered", "fixture_only"),
    "observation": ("registered", "public_doc_reviewed", "fixture_only", "observed_read_only"),
    "discovery": ("registered", "fixture_only"),
    "manual": ("registered",),
}
# Why a track ends where it does (shown once a provider reaches its last stage).
TRACK_ENDS = {
    "generic_execution": "no_ats_identity",
    "observation": "read_only_by_kind",
    "discovery": "discovery_by_kind",
    "manual": "handoff_by_kind",
}
MAX_REACHABLE = "rehearsal_ready"
CAP = "real_destinations_refused"
# The stages only the owner's approval can open, and what the owner approves.
OWNER_BOUNDARIES = {
    "public_doc_reviewed": "doc_review",  # a scoped read of the vendor's public docs and terms
    "observed_read_only": "read_only_run",  # each run approved once, on a pinned revision
    "rehearsed": "disclosure_permission",  # live-pilot gate permission C
    "live": "submission_permission",  # live-pilot gate permission D, after the rehearsal
}
# The stage each support state (providers/wording.py) claims.
CLAIM_STAGE = {
    "not_supported": "registered",
    "manual": "registered",
    "planned": "planned",
    "fixture_only": "fixture_only",
    "observed_read_only": "observed_read_only",
    "live": "live",
}
# The stage at which each Greenhouse readiness condition (providers/readiness.py) is required,
# and the stage that can first produce the evidence that meets it (a condition is never required
# before its evidence can exist: tests/test_provider_admission.py).
READINESS_STAGE = {
    "dropdowns": "rehearsal_ready",
    "unmatched_required_controls": "rehearsal_ready",
    "location": "rehearsal_ready",
    "real_upload": "rehearsed",
    "real_submission": "live",
    "pilot_gate": "live",
    "capability_entry": "live",
}
EVIDENCE_PRODUCED_AT = {
    "fixture": "fixture_only",
    "public_doc_expectation": "public_doc_reviewed",
    "read_only_observation": "observed_read_only",
    "rehearsal": "rehearsed",
    "real_submission": "live",
    "mapping_rule": "fixture_only",
    "owner_permission": "registered",
    "reviewed_change": "registered",
}
# Readiness conditions the readiness module meets by a capability level alone; admission also
# needs a behaviour credit for that capability, so a structure-only observation never counts.
BEHAVIOUR_CREDIT = {"dropdowns": C.custom_dropdowns, "location": C.location_picker}
# What a read-only run can see at all; an observed level anywhere else cannot be from one.
READ_ONLY_OBSERVABLE = frozenset({C.posting_read, C.form_extract, C.custom_dropdowns,
                                  C.location_picker})  # fmt: skip
# policy.CAPABILITIES flags and the registry entry each must agree with.
POLICY_FLAGS: dict[str, Capability | Operation] = {
    "inspect": C.posting_read,
    "extract": C.form_extract,
    "fill": C.deterministic_fill,
    "upload": C.file_upload,
    "submit": C.final_submit,
    "confirm": C.confirmation_detection,
    "checkpoint": Operation.checkpoint,
}
KEY_FORMAT = re.compile(r"[a-z][a-z0-9_]{1,31}")
VERSION_FORMAT = re.compile(r"[a-z0-9][a-z0-9.+-]{0,63}")
# Adapters whose approvals predate recorded bindings (policy.LEGACY_VERSIONS); never extended.
ORIGINAL_LEGACY = frozenset({"fixture_ats", "greenhouse_hosted"})
# The ATS names whose identity rules have the full identity contract in CI
# (tests/provider_contracts.py IDENTITY_CASES; tests/test_provider_contracts.py).
IDENTITY_CONTRACT = frozenset(
    {"greenhouse", "lever", "ashby", "workable", "workday", "smartrecruiters"}
)
# Text that looks like an identifier (`names_identifier`): a URL, an e-mail address, a dotted
# host name, a UUID, or a long number or requisition-style id. A dotted name ending in a
# repository file suffix ("provider-architecture.md", "evidence.py") is a path, not a host.
_URL = re.compile(r"[a-z][a-z0-9+.-]*://", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DOTTED = re.compile(r"\b(?:[a-z0-9-]+\.)+([a-z]{2,24})\b", re.I)
_UUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)
_LONG_ID = re.compile(r"\b[a-z]{0,4}-?\d{5,}\b", re.I)
FILE_SUFFIXES = frozenset(
    "md py json js ts tsx jsx html css txt yml yaml toml csv pdf sh lock cfg ini".split()
)


def names_identifier(text: str) -> bool:
    if any(p.search(text) for p in (_URL, _EMAIL, _UUID, _LONG_ID)):
        return True
    return any(m.group(1).lower() not in FILE_SUFFIXES for m in _DOTTED.finditer(text))


# What a fixture-tested execution provider's tests must show against the receiver ledger.
BASE_SCENARIOS = (
    "full_run_matches_ledger",
    "changed_form_stops_before_disclosure",
    "unknown_outcome_never_resent",
)
CAPABILITY_SCENARIOS = {
    C.deterministic_fill: "readback_mismatch_stops_before_submit",
    C.file_upload: "upload_failure_stops_with_evidence",
    C.captcha_checkpoint: "challenge_stops_before_disclosure",
    C.email_verification: "code_entered_by_user_only",
    C.final_submit: "rejection_is_not_confirmation",
    C.official_api_submission: "no_grant_never_contacted",
    C.reconciliation: "reconcile_never_resends",
    # S5 (D62): capabilities that change what is sent or what counts as sent.
    C.custom_dropdowns: "unlisted_option_is_checkpoint",
    C.location_picker: "location_exact_or_checkpoint",
    C.confirmation_detection: "confirmation_bound_to_attempt",
}
# S5 (D62): a workflow trait that is anything but "no" (or not applicable) needs its scenario.
TRAIT_SCENARIOS = {
    Trait.multi_step: "each_step_read_back_before_next",
}
# Required scenarios with no ledger test yet (tests/test_provider_contracts.py proves this is
# exactly what the mapping lacks). Only pre-I2 providers may appear here.
SCENARIO_GAPS: frozenset[tuple[str, str]] = frozenset()
# Known identity gaps, each still reproduced by a probe in CI (tests/test_provider_contracts.py)
# and closed before a provider it applies to reaches `rehearsal_ready`. Members are provider
# keys, ATS names, or ANY_ATS for every provider serving an ATS.
ANY_ATS = "any_ats"
KNOWN_GAPS: dict[str, frozenset[str]] = {
    # gh_jid on any host (or a host merely containing the vendor's domain) is Greenhouse, and
    # ashby_jid (a UUID) is Ashby (D81): an embed's id is believed on any host.
    "identity_jid_any_host": frozenset({"greenhouse", "ashby"}),
    # The posting parser and the identity rules accept different Greenhouse URL forms.
    "identity_rules_disagree": frozenset({"greenhouse"}),
    # An unidentified job with a Greenhouse-captured form skips the form/ATS mismatch check.
    "identity_unknown_skips_form_check": frozenset({"greenhouse_hosted", "greenhouse_dom"}),
    # A job stored as "unknown" is not identified again when the rules change.
    "identity_stored_unknown_not_redetected": frozenset({"any_ats"}),
    # A Workday posting with an /apply suffix is not identified.
    "identity_variant_unrecognised": frozenset({"workday"}),
}
# The checks a pre-I2 provider may have waived, and why (a fixed code).
WAIVABLE = {
    "doc_review_recorded": "terms_review_unrecorded",
    "fixture_scenarios_complete": "scenario_untested",
}
# The ten providers registered before I2, each with the stage its claim had then. A waiver
# counts only up to the lower of that frozen claim and the current one: raising a claim never
# raises a waiver, and a new provider under one of these keys inherits nothing past it.
PRE_ADMISSION: dict[str, str] = {
    "fixture_ats": "fixture_only", "greenhouse_hosted": "fixture_only",
    "greenhouse_dom": "observed_read_only", "fake_api": "fixture_only",
    "greenhouse_readonly": "observed_read_only", "freehire_mock": "fixture_only",
    "freehire": "fixture_only", "workday": "planned", "lever": "planned",
    "manual_handoff": "registered",
}  # fmt: skip
# Built before any public-docs review was recorded (docs/first-adapter-proposal.md lists the
# terms review as "to verify" and records no outcome).
GRANDFATHERED: dict[tuple[str, str], str] = {
    (k, "doc_review_recorded"): WAIVABLE["doc_review_recorded"]
    for k in ("greenhouse_hosted", "greenhouse_dom", "greenhouse_readonly")
} | {(k, "fixture_scenarios_complete"): WAIVABLE["fixture_scenarios_complete"]
     for k, _ in SCENARIO_GAPS}  # fmt: skip
MET, NOT_MET, WAIVED, NA = "met", "not_met", "waived", "not_applicable"
# Checks that apply only to a claim a provider chooses to state (a yes/no trait): they bound the
# claim at any stage and never require evidence to progress.
CLAIM_GUARDS = frozenset({"traits_evidenced"})
STATUSES = (MET, NOT_MET, WAIVED, NA)


@dataclass(frozen=True)
class Tables:
    """Everything admission reads, as plain data (`current_tables`; tests replace parts)."""

    providers: Mapping[str, ProviderSpec]
    ats_names: frozenset[str]
    ats_display: Mapping[str, str]
    identity_contract: frozenset[str]
    form_source_adapters: Mapping[str, str]
    generic_form_sources: frozenset
    generic_adapter: str
    form_source_ats: Mapping[str, str]
    form_source_labels: Mapping[str, str | None]
    adapter_versions: Mapping[str, str]
    legacy_versions: Mapping[str, str]
    browser_capabilities: Mapping[str, dict]
    api_identity: frozenset[str]
    api_credentials: frozenset[str]
    api_route_adapters: frozenset[str]
    path_rules: Mapping[str, str | None]
    discovery_code: frozenset[str]
    observers: frozenset[str]
    audit_route: Mapping[str, str]
    support_labels: frozenset[str]
    credited_cells: Mapping[tuple[str, str], frozenset[str]]
    credited_traits: frozenset[tuple[str, str, str]]
    doc_reviews: frozenset[str]  # ATS names with a recorded review
    readiness: Mapping[str, Callable[[], list[dict]]]
    disclosure_permission_recorded: bool  # live-pilot gate permission C
    submission_permission_recorded: bool  # permission D
    manual_evidence: Mapping[str, tuple[str, ...]]  # provider -> provenances (Path A)
    # provider -> whether its manual evidence changes no readiness condition (computed, no I/O)
    manual_evidence_inert: Mapping[str, Callable[[], bool]]
    scenario_gaps: frozenset[tuple[str, str]]
    known_gaps: Mapping[str, frozenset[str]]
    waivers: Mapping[tuple[str, str], str]


def current_tables() -> Tables:
    """The tables as the code has them now. Imports only modules the API process loads."""
    from app.modules.discovery import provider as discovery
    from app.modules.execution import policy, rehearsal
    from app.modules.jobs import canonical
    from app.modules.preparation import gh_readonly
    from app.modules.providers import evidence, path_a, readiness, registry, routing

    return Tables(
        providers=registry.PROVIDERS,
        ats_names=canonical.ATS_NAMES,
        ats_display=canonical.ATS_DISPLAY,
        identity_contract=IDENTITY_CONTRACT,
        form_source_adapters=policy.FORM_SOURCE_ADAPTERS,
        generic_form_sources=policy.GENERIC_FORM_SOURCES,
        generic_adapter=policy.GENERIC_ADAPTER,
        form_source_ats=routing.FORM_SOURCE_ATS,
        form_source_labels=wording.FORM_SOURCE_LABELS,
        adapter_versions=policy.ADAPTER_VERSIONS,
        legacy_versions=policy.LEGACY_VERSIONS,
        browser_capabilities=policy.CAPABILITIES,
        api_identity=frozenset(routing.API_IDENTITY),
        api_credentials=frozenset(routing.API_CREDENTIALS),
        api_route_adapters=rehearsal.API_ROUTE_ADAPTERS,
        path_rules=rehearsal.PATH_RULES,
        discovery_code=frozenset(discovery.PROVIDERS),
        observers=frozenset({gh_readonly.PROVIDER}),
        audit_route=routing.AUDIT_ROUTE,
        support_labels=frozenset(wording.SUPPORT_LABELS),
        credited_cells=evidence.credited_cells(),
        credited_traits=evidence.credited_traits(),
        doc_reviews=frozenset(r.ats for r in evidence.DOC_REVIEWS),
        # Path A meets no condition, so passing no observation changes nothing and reads no file.
        readiness={readiness.PROVIDER: lambda: readiness.conditions(None)},
        disclosure_permission_recorded=readiness.DISCLOSURE_PERMISSION_RECORDED,
        submission_permission_recorded=readiness.SUBMISSION_PERMISSION_RECORDED,
        manual_evidence={readiness.PROVIDER: (path_a.PROVENANCE,)},
        manual_evidence_inert={readiness.PROVIDER: _path_a_changes_no_condition},
        scenario_gaps=SCENARIO_GAPS,
        known_gaps=KNOWN_GAPS,
        waivers=GRANDFATHERED,
    )


@dataclass(frozen=True)
class Ctx:
    key: str
    spec: ProviderSpec
    t: Tables


@dataclass(frozen=True)
class Check:
    id: str  # a fixed code, reported when it blocks
    requirement: str  # one of REQUIREMENTS
    stage: str  # the first stage that needs it
    basis: str  # "code", an evidence class or a readiness prerequisite
    applies: Callable[[Ctx], bool]
    met: Callable[[Ctx], bool]


def track_of(spec: ProviderSpec) -> str:
    if spec.kind == Kind.manual:
        return "manual"
    if spec.kind == Kind.discovery:
        return "discovery"
    if spec.kind == Kind.observation:
        return "observation"
    return "ats_execution" if spec.ats else "generic_execution"


def required_scenarios(spec: ProviderSpec) -> tuple[str, ...]:
    extra = [s for cap, s in CAPABILITY_SCENARIOS.items() if spec.support(cap).level() != "none"]
    extra += [s for t, s in TRAIT_SCENARIOS.items()
              if spec.trait(t).value not in ("no", "not_applicable")]  # fmt: skip
    return (*BASE_SCENARIOS, *extra)


def _rank(stage: str) -> int:
    return STAGES.index(stage)


# -- the evaluations behind the checks ------------------------------------------------------------


def _texts(x: Ctx) -> list[str]:
    s = x.spec
    out = [s.description, s.status]
    out += [v.note for v in s.capabilities.values()] + [v.note for v in s.traits.values()]
    if s.kind == Kind.browser:
        out += _strings({k: v for k, v in x.t.browser_capabilities.get(x.key, {}).items()
                         if k != "tested_against"})  # fmt: skip
    return out


def _strings(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for item in v.values() for s in _strings(item)]
    if isinstance(v, list | tuple):
        return [s for item in v for s in _strings(item)]
    return []


def _spec_invariants(x: Ctx) -> bool:
    from app.modules.providers.registry import registry_problems

    try:
        check_spec(x.spec)
    except SpecError:
        return False
    problems = registry_problems(dict(x.t.providers), ats_names=x.t.ats_names)
    return not any(k == x.key for k, _ in problems)


def _sanitized(meta: dict) -> bool:
    from app.modules.audit.service import sanitize

    return sanitize(meta) == meta


def _key_is_safe(x: Ctx) -> bool:
    k, s = x.key, x.spec
    if s.name != k or not KEY_FORMAT.fullmatch(k) or not _sanitized({"provider": k}):
        return False
    if s.ats:
        return k == s.ats or k.startswith(f"{s.ats}_")
    if s.kind in (Kind.browser, Kind.api):
        return k.startswith(("fixture_", "fake_"))
    if s.kind == Kind.manual:
        return k.startswith("manual_")
    return True


def _traits_evidenced(x: Ctx) -> bool:
    s = x.spec
    own_design = (s.ats is None and s.stage == "implemented"
                  and any(v.fixture for v in s.capabilities.values()))  # fmt: skip
    return all(own_design or (x.key, t.value, v.value) in x.t.credited_traits
               for t, v in s.traits.items() if v.value in ("yes", "no"))  # fmt: skip


def _yes_no_traits(x: Ctx) -> bool:
    return any(v.value in ("yes", "no") for v in x.spec.traits.values())


def _never_routed(x: Ctx) -> bool:
    t = x.t
    routed = (set(t.adapter_versions) | set(t.form_source_adapters.values()) | {t.generic_adapter}
              | t.api_identity | t.api_credentials | t.api_route_adapters
              | set(t.path_rules))  # fmt: skip
    return x.key not in routed


def _manual_evidence_meets_nothing(x: Ctx) -> bool:
    """Its provenance is the basis of no check or condition, and recording it changes none."""
    from app.modules.providers import readiness

    provenances = set(x.t.manual_evidence.get(x.key, ()))
    bases = {c.basis for c in CHECKS} | set(readiness.MEETS_BY.values())
    inert = x.t.manual_evidence_inert.get(x.key)
    return bool(provenances) and not provenances & bases and inert is not None and inert()


def _path_a_changes_no_condition() -> bool:
    """Readiness with the first and with the last answer to every Path A question, against
    readiness with none: the same conditions met (synthetic observations; no file is read)."""
    from app.modules.providers import path_a, readiness

    def met(observation) -> list[bool]:
        return [r["met"] for r in readiness.conditions(observation)]

    answers = [{q: options[i] for q, options in path_a.QUESTIONS.items()} for i in (0, -1)]
    return all(met(path_a.Observation(a, "2026-01-01", 2)) == met(None) for a in answers)


def _code_registered(x: Ctx) -> bool:
    t, k = x.t, x.key
    return {Kind.browser: k in t.browser_capabilities, Kind.api: k in t.api_route_adapters,
            Kind.discovery: k in t.discovery_code,
            Kind.observation: k in t.observers}.get(x.spec.kind, False)  # fmt: skip


def _fixture_target(x: Ctx) -> bool:
    s = x.spec
    fixture = any(v.level() != "none" for v in s.capabilities.values())
    return s.stage == "implemented" and fixture and bool(s.tested_against)


def _capability_tables_agree(x: Ctx) -> bool:
    s, entry = x.spec, x.t.browser_capabilities.get(x.key)
    if entry is None:
        return False
    for flag, ref in POLICY_FLAGS.items():
        has = s.can(ref) if isinstance(ref, Operation) else s.support(ref).level() != "none"
        if bool(entry.get(flag)) != has:
            return False
    return (list(entry.get("environments", [])) == list(s.environments)
            and bool(entry.get("real_destinations", False)) == s.real_destinations_enabled
            and list(entry.get("tested_against", [])) == list(s.tested_against))  # fmt: skip


def _version_recorded(x: Ctx) -> bool:
    v = x.t.adapter_versions.get(x.key)
    return bool(v) and bool(VERSION_FORMAT.fullmatch(v)) and _sanitized({"adapter_version": v})


def _sources_of(x: Ctx) -> list:
    t = x.t
    out = [s for s, a in t.form_source_adapters.items() if a == x.key]
    return out + (sorted(s for s in t.generic_form_sources if s) if x.key == t.generic_adapter
                  else [])  # fmt: skip


def _route_reaches(x: Ctx) -> bool:
    t, s = x.t, x.spec
    if "production" in s.environments and x.key not in PILOTS:
        return False  # D102: only a pilot's route reaches it in production (execution/live.py)
    if s.kind == Kind.api:
        return x.key in t.api_identity & t.api_credentials & t.api_route_adapters
    return bool(_sources_of(x))


def _sources_match_identity(x: Ctx) -> bool:
    t = x.t
    for source in _sources_of(x):
        if t.form_source_ats.get(source) != x.spec.ats or source not in t.form_source_labels:
            return False
        label = t.form_source_labels[source]
        # D102: a pilot's source is a real job post read through it, never a test stand-in.
        pilot = t.form_source_adapters.get(source) in PILOTS
        test_stand_in = (source in t.form_source_adapters and not pilot) or source == "fixture"
        if test_stand_in and not (label and "local test" in label.lower()
                                  and "(fictional employer)" in label):  # fmt: skip
            return False
    return True


def _route_label(x: Ctx) -> bool:
    from app.modules.providers.routing import EVIDENCE_CAPABILITY

    route = "api" if x.spec.kind == Kind.api else "browser"
    try:
        wording.route_label(route, x.spec.support(EVIDENCE_CAPABILITY[route]).level())
    except (KeyError, ValueError):
        return False
    return True


def _audit_round_trip(x: Ctx) -> bool:
    from app.modules.providers.routing import RouteDecision, route_meta

    route = "api" if x.spec.kind == Kind.api else "browser"
    if route not in x.t.audit_route:
        return False
    reason = "api_authorized" if route == "api" else "browser_supported"
    meta = route_meta(RouteDecision(route, x.key, reason=reason), dict(x.t.adapter_versions))
    return meta["adapter_version"] is not None and _sanitized(meta)


def _observed(x: Ctx) -> list[Capability]:
    return [c for c, v in x.spec.capabilities.items() if v.level() != "fixture"
            and v.level() != "none"]  # fmt: skip


def _observed_credited(x: Ctx) -> bool:
    cells = _observed(x)
    return bool(cells) and all((x.key, c.value) in x.t.credited_cells for c in cells)


def _readiness_row(x: Ctx, condition: str) -> bool:
    rows = {r["id"]: r for r in x.t.readiness[x.key]()}
    if not rows.get(condition, {}).get("met"):
        return False
    cap = BEHAVIOUR_CREDIT.get(condition)
    return cap is None or "behaviour" in x.t.credited_cells.get((x.key, cap.value), ())


def _gaps_of(key: str, spec: ProviderSpec, t: Tables) -> list[str]:
    def applies(members: frozenset[str]) -> bool:
        return key in members or bool(spec.ats and (spec.ats in members or ANY_ATS in members))

    return sorted(code for code, members in t.known_gaps.items() if applies(members))


def _kinds(*kinds: Kind) -> Callable[[Ctx], bool]:
    return lambda x: x.spec.kind in kinds


def _ALL(x: Ctx) -> bool:
    return True


def _HAS_ATS(x: Ctx) -> bool:
    return x.spec.ats is not None


_EXEC = _kinds(Kind.browser, Kind.api)


def _readiness_checks() -> list[Check]:
    from app.modules.providers.readiness import MEETS_BY

    return [Check(f"readiness_{c}", "pilot_gate", READINESS_STAGE[c], MEETS_BY[c],
                  lambda x: x.key in x.t.readiness, lambda x, c=c: _readiness_row(x, c))
            for c in MEETS_BY]  # fmt: skip


CHECKS: tuple[Check, ...] = (
    Check("spec_invariants", "capability_matrix", "registered", "code", _ALL, _spec_invariants),
    Check("key_is_safe", "privacy", "registered", "code", _ALL, _key_is_safe),
    Check("text_names_nothing", "privacy", "registered", "code", _ALL,
          lambda x: not any(names_identifier(s) for s in _texts(x))),
    Check("text_claims_nothing", "support_state", "registered", "code", _ALL,
          lambda x: not any(wording.CLAIMS.search(s) for s in _texts(x))),
    Check("support_state_labelled", "support_state", "registered", "code", _ALL,
          lambda x: wording.support_state(x.spec) in wording.SUPPORT_LABELS),
    Check("traits_evidenced", "workflow_traits", "registered", "read_only_observation",
          _yes_no_traits, _traits_evidenced),
    Check("identity_contract", "identity", "registered", "code", _HAS_ATS,
          lambda x: x.spec.ats in x.t.identity_contract & x.t.ats_names),
    Check("never_routed_by_kind", "route_logic", "registered", "code",
          _kinds(Kind.discovery, Kind.observation, Kind.manual), _never_routed),
    Check("manual_evidence_meets_nothing", "manual_evidence", "registered", "code",
          lambda x: x.key in x.t.manual_evidence, _manual_evidence_meets_nothing),
    # The refusal names the ATS by its display name (routing._identity_refusal).
    Check("planned_route_refuses", "route_logic", "planned", "code",
          lambda x: x.spec.stage == "planned",
          lambda x: _planned_for(x) is x.spec and x.spec.ats in x.t.ats_display),
    Check("doc_review_recorded", "manual_evidence", "public_doc_reviewed",
          "public_doc_expectation", _HAS_ATS, lambda x: x.spec.ats in x.t.doc_reviews),
    Check("code_registered", "fixtures", "fixture_only", "code",
          _kinds(Kind.browser, Kind.api, Kind.discovery, Kind.observation), _code_registered),
    Check("fixture_target_declared", "fixtures", "fixture_only", "fixture",
          _kinds(Kind.browser, Kind.api, Kind.discovery, Kind.observation), _fixture_target),
    Check("capability_tables_agree", "capability_matrix", "fixture_only", "code",
          _kinds(Kind.browser), _capability_tables_agree),
    Check("version_recorded", "adapter_versioning", "fixture_only", "code", _EXEC,
          _version_recorded),
    Check("legacy_versions_frozen", "adapter_versioning", "fixture_only", "code", _EXEC,
          lambda x: x.key not in x.t.legacy_versions or x.key in ORIGINAL_LEGACY),
    Check("route_reaches_provider", "route_logic", "fixture_only", "code", _EXEC,
          _route_reaches),
    Check("form_sources_match_identity", "identity", "fixture_only", "code",
          _kinds(Kind.browser), _sources_match_identity),
    Check("rehearsal_path_fits_identity", "identity", "fixture_only", "code", _EXEC,
          lambda x: x.key not in x.t.path_rules
          or x.spec.ats in (x.t.path_rules[x.key], None)),
    Check("route_label_has_evidence", "support_state", "fixture_only", "code", _EXEC,
          _route_label),
    Check("audit_meta_round_trips", "audit", "fixture_only", "code", _EXEC, _audit_round_trip),
    Check("fixture_scenarios_complete", "fixtures", "fixture_only", "fixture", _EXEC,
          lambda x: not any(k == x.key for k, _ in x.t.scenario_gaps)),
    Check("observed_cells_credited", "capability_matrix", "observed_read_only",
          "read_only_observation", _ALL, _observed_credited),
    Check("observed_only_where_read_only_can_see", "capability_matrix", "observed_read_only",
          "code", _ALL, lambda x: set(_observed(x)) <= READ_ONLY_OBSERVABLE),
    Check("readiness_profile_defined", "pilot_gate", "rehearsal_ready", "code", _ALL,
          lambda x: x.key in x.t.readiness),
    *_readiness_checks(),
    Check("rehearsal_path_rule", "pilot_gate", "rehearsal_ready", "code", _ALL,
          lambda x: x.t.path_rules.get(x.key, "") == x.spec.ats),
    Check("known_gaps_closed", "identity", "rehearsal_ready", "code", _ALL,
          lambda x: not _gaps_of(x.key, x.spec, x.t)),
    Check("disclosure_permission_recorded", "pilot_gate", "rehearsed", "owner_permission",
          _ALL, lambda x: x.t.disclosure_permission_recorded),
    Check("submission_permission_recorded", "pilot_gate", "live", "owner_permission",
          _ALL, lambda x: x.t.submission_permission_recorded),
    Check("live_label_exists", "support_state", "live", "code", _ALL,
          lambda x: "live" in x.t.support_labels),
)  # fmt: skip


def _planned_for(x: Ctx) -> ProviderSpec | None:
    from app.modules.providers.registry import planned_for_ats

    return planned_for_ats(x.spec.ats, dict(x.t.providers)) if x.spec.ats else None


# -- the computation ------------------------------------------------------------------------------


def _status(c: Check, x: Ctx, track: tuple[str, ...]) -> str:
    if c.stage not in track or not c.applies(x):
        return NA
    if c.met(x):
        return MET
    waived = x.key in PRE_ADMISSION and c.id in WAIVABLE and (x.key, c.id) in x.t.waivers
    return WAIVED if waived else NOT_MET


def _passes(status: str, stage: str, ceiling: str) -> bool:
    if status == WAIVED:  # a waiver keeps a pre-I2 claim; it never takes a provider beyond it
        return _rank(stage) <= _rank(ceiling)
    return status in (MET, NA)


def evaluate(key: str, tables: Tables | None = None) -> dict:
    """One provider's admission: where it is on its track, why it stops there."""
    t = tables or current_tables()
    spec = t.providers[key]
    x = Ctx(key, spec, t)
    track_name = track_of(spec)
    track = TRACKS[track_name]
    claimed = wording.support_state(spec)
    claim_stage = CLAIM_STAGE[claimed]
    statuses = {c.id: _status(c, x, track) for c in CHECKS}
    stage_of = {c.id: c.stage for c in CHECKS}
    frozen = PRE_ADMISSION.get(key, "not_admitted")
    ceiling = min(claim_stage, frozen, key=_rank)  # how far a waiver may count

    def blocking(stage: str) -> list[str]:
        due = [i for i in statuses if _rank(stage_of[i]) <= _rank(stage)]
        out = [i for i in due if not _passes(statuses[i], stage, ceiling)]
        return out + ([CAP] if _rank(stage) > _rank(MAX_REACHABLE) else [])

    admitted = "not_admitted"
    for stage in track:
        if blocking(stage):
            break
        admitted = stage
    at = track.index(admitted) if admitted in track else -1
    nxt = track[at + 1] if at + 1 < len(track) else None
    return {
        "kind": spec.kind.value,
        "track": track_name,
        "claimed": claimed,
        "claim_stage": claim_stage,
        "admitted": admitted,
        "next": nxt,
        "owner_boundary_next": OWNER_BOUNDARIES.get(nxt) if nxt else None,
        "blocking": blocking(nxt) if nxt else [],
        "waived": [i for i, st in statuses.items() if st == WAIVED],
        "known_gaps": _gaps_of(key, spec, t),
        "end": TRACK_ENDS.get(track_name) if nxt is None else None,
        "within_claim": claim_stage in track
        and admitted in track
        and _rank(claim_stage) <= _rank(admitted),
        "checks": [{"id": i, "status": st} for i, st in statuses.items()],
    }


def summary(tables: Tables | None = None) -> dict:
    """The framework and every registered provider's admission, as fixed identifiers only."""
    t = tables or current_tables()
    rows = {k: evaluate(k, t) for k in t.providers}
    by_ats = {}
    for ats in sorted(t.ats_names):
        keys = sorted(k for k, p in t.providers.items() if p.ats == ats)
        reached = [rows[k]["admitted"] for k in keys if rows[k]["track"] == "ats_execution"]
        best = max(reached, key=_rank) if reached else "not_admitted"
        # What the best of them holds only through a waiver is shown as such, never as met.
        waived = sorted({i for k in keys if rows[k]["track"] == "ats_execution"
                         and rows[k]["admitted"] == best for i in rows[k]["waived"]})  # fmt: skip
        by_ats[ats] = {"providers": keys, "admitted": best, "waived": waived}
    return {
        "requirements": list(REQUIREMENTS),
        "stages": list(STAGES),
        "tracks": {k: list(v) for k, v in TRACKS.items()},
        "track_ends": dict(TRACK_ENDS),
        "owner_boundaries": dict(OWNER_BOUNDARIES),
        "max_reachable": MAX_REACHABLE,
        "checks": [
            {"id": c.id, "requirement": c.requirement, "stage": c.stage, "basis": c.basis}
            for c in CHECKS
        ],  # fmt: skip
        "known_gaps": {code: sorted(m) for code, m in t.known_gaps.items()},
        "ats": by_ats,
        "providers": rows,
    }
