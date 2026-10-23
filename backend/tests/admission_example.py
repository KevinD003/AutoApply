"""A synthetic provider for the admission tests (tests/test_provider_admission.py): an ATS
called "exampleats", fictional and never registered, built into copies of the admission tables
stage by stage, plus one sabotage per check that breaks that check alone. Nothing here names
a real ATS, employer or host, and nothing is ever added to registry.PROVIDERS."""

from dataclasses import replace

from app.modules.providers import admission
from app.modules.providers.model import (
    FIXTURE,
    Capability,
    Kind,
    Operation,
    ProviderSpec,
    Support,
    Trait,
    TraitValue,
)

C, Op, T, V = Capability, Operation, Trait, TraitValue
KEY, ATS, SOURCE = "exampleats_form", "exampleats", "example_form"
FEED = "example_feed"  # a discovery variant, for the checks only other kinds have
PROVENANCE = "example_owner_observation"
VERSION = "exampleats-form-1"
FIXTURE_PATH = "fixtures/ats_receiver/receiver.py"  # any existing path; never served
OPS = frozenset({Op.inspect, Op.extract_form, Op.prepare, Op.validate_before_disclosure, Op.fill,
                 Op.upload, Op.checkpoint, Op.submit, Op.classify_outcome,
                 Op.collect_evidence})  # fmt: skip
SEEN = Support(fixture=True, observed=True)
REACHABLE = ("registered", "planned", "public_doc_reviewed", "fixture_only",
             "observed_read_only", "rehearsal_ready")  # fmt: skip


def spec(stage: str) -> ProviderSpec:
    """The example as it would be registered at `stage` (a planned spec until fixture_only)."""
    if admission._rank(stage) < admission._rank("fixture_only"):
        return ProviderSpec(
            name=KEY, kind=Kind.browser, description="Synthetic example adapter specification.",
            operations=frozenset(), stage="planned", ats=ATS, status="Planned only.",
            traits={t: V("unknown", "unverified") for t in Trait},
        )  # fmt: skip
    observed = admission._rank(stage) >= admission._rank("observed_read_only")
    level = SEEN if observed else FIXTURE
    return ProviderSpec(
        name=KEY,
        kind=Kind.browser,
        description="Synthetic example adapter (fictional employer).",
        operations=OPS,
        capabilities={
            C.posting_read: level, C.form_extract: level, C.deterministic_fill: FIXTURE,
            C.custom_dropdowns: level, C.location_picker: level, C.file_upload: FIXTURE,
            C.captcha_checkpoint: FIXTURE, C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE, C.reconciliation: FIXTURE,
        },
        status="Synthetic example; fixture only.",
        traits={
            T.login_required: V("no", "seen in the example run") if observed
            else V("unknown", "not observed"),
            T.manual_verification_required: V("unknown", "never submitted"),
            T.captcha_possible: V("unknown", "a checkpoint if it appears"),
            T.multi_step: V("unknown", "not observed"),
        },
        ats=ATS,
        tested_against=(FIXTURE_PATH,),
    )  # fmt: skip


def feed() -> ProviderSpec:
    return ProviderSpec(
        name=FEED, kind=Kind.discovery, description="Synthetic example job feed.",
        operations=frozenset({Op.discover}), capabilities={C.discovery: FIXTURE},
        status="Fixture only.", traits={t: V("not_applicable") for t in Trait},
        tested_against=(FIXTURE_PATH,),
    )  # fmt: skip


def _policy_entry(s: ProviderSpec) -> dict:
    flags = {f: (s.can(r) if isinstance(r, Operation) else s.support(r).level() != "none")
             for f, r in admission.POLICY_FLAGS.items()}  # fmt: skip
    return {"description": "Example-style form (fictional employer).",
            "environments": list(s.environments), "real_destinations": False, **flags,
            "tested_against": list(s.tested_against)}  # fmt: skip


def _ready_rows(met: bool = True, *, but: str | None = None):
    from app.modules.providers.readiness import MEETS_BY

    return lambda: [{"id": c, "met": met and c != but} for c in MEETS_BY]


def tables(stage: str, base: admission.Tables | None = None) -> admission.Tables:
    """The current tables with the example added as far as `stage` needs (and no further)."""
    t = base or admission.current_tables()
    r = admission._rank
    s = spec(stage)
    providers = {**t.providers, KEY: s, FEED: feed()}
    t = replace(t, providers=providers, ats_names=t.ats_names | {ATS},
                identity_contract=t.identity_contract | {ATS},
                ats_display={**t.ats_display, ATS: "ExampleATS"} if r(stage) >= r("planned")
                else t.ats_display,
                discovery_code=t.discovery_code | {FEED})  # fmt: skip
    if r(stage) >= r("public_doc_reviewed"):
        t = replace(t, doc_reviews=t.doc_reviews | {ATS})
    if r(stage) >= r("fixture_only"):
        t = replace(
            t,
            browser_capabilities={**t.browser_capabilities, KEY: _policy_entry(s)},
            adapter_versions={**t.adapter_versions, KEY: VERSION},
            form_source_adapters={**t.form_source_adapters, SOURCE: KEY},
            form_source_ats={**t.form_source_ats, SOURCE: ATS},
            form_source_labels={**t.form_source_labels,
                                SOURCE: "Example-style form: local test approximation "
                                "(fictional employer)"},
            manual_evidence={**t.manual_evidence, KEY: (PROVENANCE,)},
            manual_evidence_inert={**t.manual_evidence_inert, KEY: lambda: True},
        )  # fmt: skip
    if r(stage) >= r("observed_read_only"):
        cells = {
            (KEY, c.value): frozenset({"behaviour"})
            for c in (C.posting_read, C.form_extract, C.custom_dropdowns, C.location_picker)
        }
        t = replace(t, credited_cells={**t.credited_cells, **cells},
                    credited_traits=t.credited_traits
                    | {(KEY, "login_required", "no")})  # fmt: skip
    if r(stage) >= r("rehearsal_ready"):
        gaps = {code: m - {admission.ANY_ATS} for code, m in t.known_gaps.items()}  # closed
        t = replace(t, readiness={**t.readiness, KEY: _ready_rows()},
                    path_rules={**t.path_rules, KEY: ATS}, known_gaps=gaps)  # fmt: skip
    return t


def complete() -> admission.Tables:
    """Every check met for the example, including the stages past the cap."""
    t = tables("rehearsal_ready")
    return replace(t, disclosure_permission_recorded=True, submission_permission_recorded=True,
                   support_labels=t.support_labels | {"live"})  # fmt: skip


def _with_spec(t: admission.Tables, **changes) -> admission.Tables:
    return replace(t, providers={**t.providers, KEY: replace(t.providers[KEY], **changes)})


def _without(mapping, key):
    return {k: v for k, v in mapping.items() if k != key}


def _readiness_but(condition: str):
    return lambda t: replace(t, readiness={**t.readiness, KEY: _ready_rows(but=condition)})


def _cells_kind(kind: str):
    def f(t):
        cells = {**t.credited_cells, (KEY, "custom_dropdowns"): frozenset({kind}),
                 (KEY, "location_picker"): frozenset({kind})}  # fmt: skip
        return replace(t, credited_cells=cells)

    return f


# One change per check that breaks it and nothing else needed before its stage.
SABOTAGE = {
    "spec_invariants": lambda t: _with_spec(t, operations=OPS - {Op.fill}),
    "key_is_safe": lambda t: _with_spec(t, name="ExampleATS"),
    "text_names_nothing": lambda t: _with_spec(t, status="Tested on careers.example.invalid."),
    "text_claims_nothing": lambda t: _with_spec(t, status="Supported live."),
    "support_state_labelled": lambda t: replace(t, providers={**t.providers, KEY: replace(
        t.providers[KEY], capabilities={**t.providers[KEY].capabilities, C.posting_read: Support(
            fixture=True, observed=True, live_fill=True)})}),
    "traits_evidenced": lambda t: replace(t, credited_traits=frozenset()),
    "identity_contract": lambda t: replace(t, identity_contract=t.identity_contract - {ATS}),
    "manual_evidence_meets_nothing": lambda t: replace(
        t, manual_evidence={**t.manual_evidence, KEY: ("code",)}),
    "planned_route_refuses": lambda t: replace(t, ats_display=_without(t.ats_display, ATS)),
    "doc_review_recorded": lambda t: replace(t, doc_reviews=t.doc_reviews - {ATS}),
    "code_registered": lambda t: replace(
        t, browser_capabilities=_without(t.browser_capabilities, KEY)),
    "fixture_target_declared": lambda t: _with_spec(t, tested_against=()),
    "capability_tables_agree": lambda t: replace(t, browser_capabilities={
        **t.browser_capabilities, KEY: {**t.browser_capabilities[KEY], "upload": False}}),
    "version_recorded": lambda t: replace(t, adapter_versions={**t.adapter_versions,
                                                               KEY: "Example Form/1"}),
    "legacy_versions_frozen": lambda t: replace(t, legacy_versions={**t.legacy_versions,
                                                                    KEY: VERSION}),
    "route_reaches_provider": lambda t: replace(
        t, form_source_adapters=_without(t.form_source_adapters, SOURCE)),
    "form_sources_match_identity": lambda t: replace(t, form_source_ats={**t.form_source_ats,
                                                                         SOURCE: "greenhouse"}),
    "rehearsal_path_fits_identity": lambda t: replace(t, path_rules={**t.path_rules,
                                                                     KEY: "greenhouse"}),
    "route_label_has_evidence": lambda t: _with_spec(t, capabilities=_without(
        t.providers[KEY].capabilities, C.deterministic_fill), operations=OPS - {Op.fill}),
    "audit_meta_round_trips": lambda t: replace(t, audit_route=_without(t.audit_route,
                                                                        "browser")),
    "fixture_scenarios_complete": lambda t: replace(
        t, scenario_gaps=t.scenario_gaps | {(KEY, "full_run_matches_ledger")}),
    "observed_cells_credited": lambda t: replace(
        t, credited_cells=_without(t.credited_cells, (KEY, "form_extract"))),
    "observed_only_where_read_only_can_see": lambda t: _with_spec(t, capabilities={
        **t.providers[KEY].capabilities, C.file_upload: SEEN}),
    "readiness_profile_defined": lambda t: replace(t, readiness=_without(t.readiness, KEY)),
    "rehearsal_path_rule": lambda t: replace(t, path_rules=_without(t.path_rules, KEY)),
    "known_gaps_closed": lambda t: replace(t, known_gaps={**t.known_gaps,
                                                          "identity_example": frozenset({ATS})}),
    "disclosure_permission_recorded": lambda t: replace(t, disclosure_permission_recorded=False),
    "submission_permission_recorded": lambda t: replace(t, submission_permission_recorded=False),
    "live_label_exists": lambda t: replace(t, support_labels=t.support_labels - {"live"}),
    # The discovery variant's check: it must never appear in an execution table.
    "never_routed_by_kind": lambda t: replace(t, adapter_versions={**t.adapter_versions,
                                                                   FEED: VERSION}),
}  # fmt: skip
SABOTAGE |= {f"readiness_{c}": _readiness_but(c) for c in admission.READINESS_STAGE}
# The other checks a sabotage breaks because they read the same input: declared, and tested to
# be exactly these (tests/test_provider_admission.py), so no sabotage passes by breaking another.
ALSO_BREAKS = {
    "key_is_safe": {"spec_invariants"},  # a name that is not its key is a registry problem too
    "support_state_labelled": {"spec_invariants"},  # a live level is refused by check_spec too
    "code_registered": {"capability_tables_agree"},  # no capability table entry to agree with
    "fixture_target_declared": {"capability_tables_agree", "spec_invariants"},
    "version_recorded": {"audit_meta_round_trips"},  # the version is part of the route metadata
    "rehearsal_path_fits_identity": {"rehearsal_path_rule"},  # the same path rule
    "route_label_has_evidence": {"capability_tables_agree"},  # filling removed from both
    "observed_only_where_read_only_can_see": {"observed_cells_credited"},  # uncredited, too
}
# A structure-only observation of dropdowns and location breaks those two conditions too.
STRUCTURE_ONLY = _cells_kind("structure")
_SUBJECTS = {
    "never_routed_by_kind": (FEED, complete),  # a discovery provider's check
    "planned_route_refuses": (KEY, lambda: tables("public_doc_reviewed")),  # a planned spec's
}


def subject(check: str) -> tuple[str, admission.Tables]:
    """The provider and tables on which `check` applies and is met (default: the complete
    example adapter)."""
    key, make = _SUBJECTS.get(check, (KEY, complete))
    return key, make()
