"""Every provider NoEfforts knows, with its operations and evidence-backed capabilities.

Nothing here is enabled for a real destination: `real_destinations_enabled` is false
everywhere, so no capability has live filling or live submission support. "observed" means
seen on one real page under a separately approved read-only scope, never more."""

from dataclasses import replace

from app.modules.jobs.canonical import ATS_NAMES
from app.modules.providers import wording
from app.modules.providers.model import (
    FIXTURE,
    Capability,
    Kind,
    Operation,
    ProviderSpec,
    SpecError,
    Support,
    Trait,
    TraitValue,
    check_spec,
    interface,
    matrix,
    routing_view,
)

C, Op = Capability, Operation
_BROWSER_OPS = frozenset({
    Op.inspect, Op.extract_form, Op.prepare, Op.validate_before_disclosure, Op.fill, Op.upload,
    Op.checkpoint, Op.submit, Op.classify_outcome, Op.collect_evidence,
})  # fmt: skip
_USER_RECONCILES = Support(fixture=True, note="the user states what they checked; never resent")

PROVIDERS: dict[str, ProviderSpec] = {
    "fixture_ats": ProviderSpec(
        name="fixture_ats",
        kind=Kind.browser,
        description="Local synthetic ATS receiver (fictional employer).",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: FIXTURE,
            C.form_extract: FIXTURE,
            C.deterministic_fill: FIXTURE,
            C.file_upload: FIXTURE,
            C.email_verification: Support(fixture=True, note="code entered by the user"),
            # No captcha_checkpoint: this fixture has no CAPTCHA mode and its adapter detects none.
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },
        status="Fixture only.",
    ),
    "greenhouse_hosted": ProviderSpec(
        name="greenhouse_hosted",
        kind=Kind.browser,
        description="Greenhouse-style hosted form with named controls (local approximation).",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: FIXTURE,
            C.form_extract: Support(fixture=True, note="the real page observed had no names"),
            C.deterministic_fill: FIXTURE,
            C.file_upload: FIXTURE,
            C.email_verification: Support(fixture=True, note="code entered by the user"),
            C.captcha_checkpoint: Support(fixture=True, note="stop and hand off; never solved"),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },
        status="Fixture only; the observed real page has a different structure.",
    ),
    "greenhouse_dom": ProviderSpec(
        name="greenhouse_dom",
        kind=Kind.browser,
        description="Greenhouse-style form mapped by id and accessible name (local approximation"
        " of the structure observed read-only on one real posting).",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: Support(
                fixture=True,
                observed=True,
                note="job data read on one real posting (read-only runs)",
            ),
            C.form_extract: Support(
                fixture=True,
                observed=True,
                note="mapping rules applied read-only to one real posting: "
                "19 fields mapped; the posting stays refused",
            ),
            C.deterministic_fill: FIXTURE,
            C.custom_dropdowns: Support(
                fixture=True,
                note="strategies fixture-only; no opening evidence on the real page (run #9); "
                "lists arriving late accepted on local stand-ins only (D104)",
            ),
            # D104: a location search stand-in only. On a real page no location control was
            # seen at all; this is not evidence for one.
            C.location_picker: Support(
                fixture=True,
                note="local stand-in only: the exact suggestion or a stop; never on a real page",
            ),
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(fixture=True, note="stop and hand off; never solved"),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },  # fmt: skip
        status="Fixture filling only. One real posting observed read-only; refused for real"
        " destinations (dropdowns, location, unmatched required controls).",
    ),
    # D102: the Greenhouse pilot. The same rules as greenhouse_dom on a real board host, off
    # unless the owner switches it on (execution/live.py). It claims nothing on real pages: its
    # levels are the fixture's, and only the read-only observations are credited.
    "greenhouse_live": ProviderSpec(
        name="greenhouse_live",
        kind=Kind.browser,
        description="The Greenhouse pilot: the id and accessible-name mapping of greenhouse_dom "
        "on a real Greenhouse board, for the owner's account only, in production with container "
        "isolation, when the owner switched it on.",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: Support(
                fixture=True,
                observed=True,
                note="job data read on one real posting (read-only runs)",
            ),
            C.form_extract: Support(
                fixture=True,
                observed=True,
                note="mapping rules applied read-only to one real posting: 19 fields mapped",
            ),
            C.deterministic_fill: FIXTURE,
            C.custom_dropdowns: Support(
                fixture=True,
                note="strategies fixture-only; no opening evidence on the real page (run #9)",
            ),
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(fixture=True, note="stop and hand off; never solved"),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },  # fmt: skip
        environments=("production", "test"),
        real_destinations_enabled=True,
        status="Pilot, off by default; never yet run on a real page. Each application is "
        "approved by you and rehearsed first per employer; anything not understood stops it.",
    ),
    "fake_api": ProviderSpec(
        name="fake_api",
        kind=Kind.api,
        description="Internal authorized-API adapter contract, exercised against a local fake "
        "API only. No real ATS is claimed to offer this interface.",
        operations=frozenset(
            {
                Op.inspect,
                Op.extract_form,
                Op.validate_before_disclosure,
                Op.prepare,
                Op.upload,
                Op.submit,
                Op.classify_outcome,
                Op.collect_evidence,
                Op.reconcile,
            }
        ),  # fmt: skip
        capabilities={
            C.official_api_submission: Support(
                fixture=True, note="explicit user authorization and configured credentials required"
            ),
            C.posting_read: FIXTURE,
            C.form_extract: FIXTURE,
            C.file_upload: FIXTURE,
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: Support(
                fixture=True, note="read-only status lookup by idempotency key; never resent"
            ),
        },  # fmt: skip
        status="Fixture only (local fake API).",
    ),
    "greenhouse_readonly": ProviderSpec(
        name="greenhouse_readonly",
        kind=Kind.observation,
        description="Read-only compatibility observation of one approved real posting.",
        operations=frozenset({Op.inspect, Op.extract_form, Op.collect_evidence}),
        capabilities={
            C.posting_read: Support(fixture=True, observed=True),
            C.form_extract: Support(fixture=True, observed=True),
            C.custom_dropdowns: Support(
                fixture=True, observed=True, note="structure observed; no opening evidence"
            ),
        },  # fmt: skip
        status="Observed read-only under the single-use approvals recorded in"
        " providers/evidence.py; never fills or submits.",
    ),
    "freehire_mock": ProviderSpec(
        name="freehire_mock",
        kind=Kind.discovery,
        description="Freehire discovery provider interface, backed by a local mock only.",
        operations=frozenset({Op.discover}),
        capabilities={C.discovery: FIXTURE},
        status="Potential future discovery provider; not yet connected or validated.",
    ),
    "freehire": ProviderSpec(
        name="freehire",
        kind=Kind.discovery,
        description="Client for Freehire's documented public read API; fixture base URLs only.",
        operations=frozenset({Op.discover}),
        capabilities={
            C.discovery: Support(
                fixture=True,
                note="local fixture of the documented API; no call to the real service made or "
                "authorized",
            )
        },
        status="Potential future discovery provider; not yet connected or validated.",
    ),
    "fixture_lever": ProviderSpec(
        name="fixture_lever",
        kind=Kind.browser,
        description="Lever-style hosted form (a posting page, then its form page), served by a "
        "labelled local approximation. No Lever identity: it serves no real Lever posting.",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: FIXTURE,
            C.form_extract: FIXTURE,
            C.deterministic_fill: FIXTURE,
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(
                fixture=True, note="stops before anything is entered; never solved"
            ),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },
        status="Fixture only (a local Lever-style approximation); a real Lever job is a manual "
        "handoff.",
    ),
    "fixture_ashby": ProviderSpec(
        name="fixture_ashby",
        kind=Kind.browser,
        description="Ashby-style hosted form (a posting, then its application tab), served by a "
        "labelled local approximation. No Ashby identity: it serves no real Ashby posting.",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: FIXTURE,
            C.form_extract: FIXTURE,
            C.deterministic_fill: FIXTURE,
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(
                fixture=True,
                note="the spam check stops before anything is entered, or as an unknown "
                "outcome after the final click; never solved or retried",
            ),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },
        status="Fixture only (a local Ashby-style approximation); a real Ashby job is a manual "
        "handoff.",
    ),
    "fixture_workday": ProviderSpec(
        name="fixture_workday",
        kind=Kind.browser,
        description="Workday-style hosted application (a posting, then one application page), "
        "served by a labelled local approximation, checkpoint-first. No Workday identity: it "
        "serves no real Workday posting.",
        operations=_BROWSER_OPS,
        capabilities={
            C.posting_read: FIXTURE,
            C.form_extract: FIXTURE,
            C.deterministic_fill: FIXTURE,
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(
                fixture=True, note="stops before anything is entered; never solved"
            ),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },
        status="Fixture only (a local Workday-style approximation); a real Workday job is a "
        "manual handoff.",
    ),
    "workday": ProviderSpec(
        name="workday",
        kind=Kind.browser,
        description="Future Workday adapter: a specification only (docs/provider-architecture.md"
        " §7). No code, no fixture, no observation.",
        operations=frozenset(),
        stage="planned",
        status="Planned only. Workday applications are not supported: no automation exists.",
    ),
    "lever": ProviderSpec(
        name="lever",
        kind=Kind.browser,
        description="Future Lever adapter for real postings: a specification only "
        "(docs/provider-architecture.md §7b). No observation; no Lever page was read. The local "
        "Lever-style approximation has its own fixture adapter, with no Lever identity.",
        operations=frozenset(),
        stage="planned",
        status="Planned only. Lever applications are not supported: no automation exists.",
    ),
    "manual_handoff": ProviderSpec(
        name="manual_handoff",
        kind=Kind.manual,
        description="Nothing automated: the user applies on the employer's site and records it.",
        operations=frozenset({Op.checkpoint}),
        environments=("development", "test", "production"),
        status="Always offered.",
    ),
}

T, V = Trait, TraitValue
_NA = {t: V("not_applicable") for t in Trait}
# What each workflow demands, with the evidence for it. "yes"/"no" only where it was seen (a
# fixture's own design counts only for that fixture); "expected" only for a specification.
_TRAITS: dict[str, dict[Trait, TraitValue]] = {
    "fixture_ats": {
        T.login_required: V("no", "fixture design"),
        T.manual_verification_required: V("yes", "fixture design: an emailed code, entered by "
                                                 "the user"),
        T.captcha_possible: V("no", "fixture design: no CAPTCHA mode"),
        T.multi_step: V("no", "fixture design"),
    },
    "greenhouse_hosted": {
        T.login_required: V("unknown", "fixture approximation only"),
        T.manual_verification_required: V("unknown", "the emailed-code step is the fixture's "
                                                     "own design"),
        T.captcha_possible: V("unknown", "handled as a checkpoint if it appears"),
        T.multi_step: V("unknown", "fixture approximation only"),
    },
    "greenhouse_dom": {
        T.login_required: V("no", "the observed posting loaded without an account (single-use "
                                  "read-only runs, providers/evidence.py)"),
        T.manual_verification_required: V("unknown", "never submitted; not observed"),
        T.captcha_possible: V("unknown", "none seen in read-only runs #3-#9; a checkpoint if it "
                                         "appears, never solved"),
        T.multi_step: V("no", "the observed posting was one page"),
    },
    "greenhouse_live": {
        T.login_required: V("no", "the observed posting loaded without an account (single-use "
                                  "read-only runs, providers/evidence.py)"),
        T.manual_verification_required: V("unknown", "never submitted; not observed"),
        T.captcha_possible: V("unknown", "none seen in read-only runs #3-#9; a checkpoint if it "
                                         "appears, never solved"),
        T.multi_step: V("no", "the observed posting was one page"),
    },
    "greenhouse_readonly": {
        T.login_required: V("no", "the observed posting loaded without an account (single-use "
                                  "read-only runs, providers/evidence.py)"),
        T.manual_verification_required: V("not_applicable", "never fills or submits"),
        T.captcha_possible: V("unknown", "none seen; the observation stops on a challenge"),
        T.multi_step: V("no", "the observed posting was one page"),
    },
    "fixture_lever": {
        T.login_required: V("no", "fixture design: no account"),
        T.manual_verification_required: V("no", "fixture design: a verification step after "
                                                "submitting is not handled (one mode shows it)"),
        T.captcha_possible: V("yes", "fixture design: a mode puts a bot check on the form"),
        T.multi_step: V("no", "fixture design: one form page after the posting page"),
    },
    "fixture_ashby": {
        T.login_required: V("no", "fixture design: no account"),
        T.manual_verification_required: V("no", "fixture design: no verification step"),
        T.captcha_possible: V("yes", "fixture design: a mode puts a spam check on the form; "
                                     "Ashby documents a score with no widget"),
        T.multi_step: V("no", "fixture design: one application page after the posting page"),
    },
    "fixture_workday": {
        T.login_required: V("no", "fixture design: applying manually needs no account; a mode "
                                  "requires one, which stops before anything is entered"),
        T.manual_verification_required: V("no", "fixture design: a mode asks for email "
                                                "verification after the final click (unknown)"),
        T.captcha_possible: V("yes", "fixture design: a mode puts a challenge on the page; "
                                     "Workday documents none"),
        T.multi_step: V("no", "fixture design: one application page; a mode has several, "
                              "which stops before anything is entered"),
    },
    "fake_api": {
        T.login_required: V("no", "credentials, not a login: the user's grant plus a token"),
        T.manual_verification_required: V("no", "fixture design"),
        T.captcha_possible: V("no", "an API; fixture design"),
        T.multi_step: V("no", "draft, documents, submit: API calls, not form pages"),
    },
    "freehire": _NA,
    "freehire_mock": _NA,
    "manual_handoff": _NA,
    # Lever: the specification's expectations, none observed (nothing was read from Lever).
    "lever": {
        T.login_required: V("unknown", "a hosted form without a candidate account is "
                                       "expected; unverified"),
        T.manual_verification_required: V("unknown", "not specified; unverified"),
        T.captcha_possible: V("expected", "a checkpoint for the user, never solved"),
        T.multi_step: V("unknown", "a single page is expected; unverified"),
    },
    "workday": {
        T.login_required: V("expected", "employer-scoped candidate accounts and sessions"),
        T.manual_verification_required: V("expected", "email verification, security prompts"),
        T.captcha_possible: V("expected", "a checkpoint for the user, never solved"),
        T.multi_step: V("expected", "multi-step forms with per-step validation"),
    },
}  # fmt: skip
# The ATS identity each provider serves (jobs.canonical.detect_ats names). Fixture origins are
# identified as "unknown", so fixture adapters are chosen by the captured form, not by host.
_ATS = {"greenhouse_hosted": "greenhouse", "greenhouse_dom": "greenhouse",
        "greenhouse_live": "greenhouse",
        "greenhouse_readonly": "greenhouse", "lever": "lever", "workday": "workday"}  # fmt: skip
# The local fixtures each provider's `fixture` levels were tested against (repository paths).
_RECEIVER = "fixtures/ats_receiver"
_TESTED_AGAINST = {
    "fixture_ats": (_RECEIVER,),  # the generic form, served by its receiver
    "greenhouse_hosted": (f"{_RECEIVER}/greenhouse_like.py",),
    "greenhouse_dom": (f"{_RECEIVER}/greenhouse_v2.py",),
    "greenhouse_live": (f"{_RECEIVER}/greenhouse_v2.py",),
    "fake_api": (f"{_RECEIVER}/fake_api.py",),
    "fixture_lever": (f"{_RECEIVER}/lever_like.py",),
    "fixture_ashby": (f"{_RECEIVER}/ashby_like.py",),
    "fixture_workday": (f"{_RECEIVER}/workday_like.py",),
    "greenhouse_readonly": (f"{_RECEIVER}/greenhouse_like.py", f"{_RECEIVER}/greenhouse_v2.py"),
    "freehire_mock": ("fixtures/discovery/freehire_mock.json",),
    "freehire": (f"{_RECEIVER}/freehire_fixture.py",),
}
PROVIDERS = {k: replace(v, traits=_TRAITS.get(k, {}), ats=_ATS.get(k),
                        tested_against=_TESTED_AGAINST.get(k, ()))
             for k, v in PROVIDERS.items()}  # fmt: skip


def registry_problems(
    providers: dict[str, ProviderSpec],
    *,
    ats_names: frozenset[str] = ATS_NAMES,
    side_tables: tuple[dict, ...] = (),
) -> list[tuple[str, str]]:
    """What is inconsistent across the registry, as (key, problem): each spec on its own is
    `check_spec`'s. `side_tables`: tables keyed by provider that must name registered ones."""
    out = []
    for table in side_tables:
        out += [(k, "a side table names an unregistered provider") for k in table
                if k not in providers]  # fmt: skip
    planned: dict[str, list[str]] = {}
    for k, p in providers.items():
        if p.name != k:
            out.append((k, "registered under another name"))
        if p.ats is not None and p.ats not in ats_names:
            out.append((k, "its ATS is not a detect_ats name"))
        if p.ats is not None and p.kind in (Kind.discovery, Kind.manual):
            out.append((k, "a discovery or manual provider serves no ATS"))
        if p.ats is None and (p.kind == Kind.observation or p.stage == "planned"):
            out.append((k, "a planned or observation provider names its ATS"))
        if set(p.traits) != set(Trait):
            out.append((k, "every workflow trait is stated"))
        if p.stage == "planned" and p.ats is not None:
            planned.setdefault(p.ats, []).append(k)
    for ats, keys in planned.items():
        if len(keys) > 1:
            out += [(k, "one planned specification per ATS") for k in keys]
        implemented = [k for k, p in providers.items() if p.ats == ats and p.stage == "implemented"
                       and p.kind in (Kind.browser, Kind.api)]  # fmt: skip
        if implemented:
            out += [(k, "a planned specification beside an implemented adapter") for k in keys]
    return out


def check_registry(providers: dict[str, ProviderSpec], **kw) -> None:
    for spec in providers.values():
        check_spec(spec)
    problems = registry_problems(providers, **kw)
    if problems:
        key, problem = problems[0]
        raise SpecError(f"{key}: {problem}")


check_registry(PROVIDERS, side_tables=(_TRAITS, _ATS, _TESTED_AGAINST))


def get(name: str) -> ProviderSpec:
    return PROVIDERS[name]


def of_kind(kind: Kind) -> list[ProviderSpec]:
    return [p for p in PROVIDERS.values() if p.kind == kind]


def summary() -> dict:
    """The registry as plain data (for the API and the docs)."""
    return {
        p.name: {
            "kind": p.kind.value,
            "operations": sorted(o.value for o in p.operations),
            "capabilities": matrix(p),
            "real_destinations_enabled": p.real_destinations_enabled,
            "status": p.status,
            "support_state": wording.support_state(p),
            "support_label": wording.support_label(p),
            "stage": p.stage,
            "ats": p.ats,
            "traits": {t.value: {"value": v.value, "note": v.note} for t, v in p.traits.items()},
            "routing_capabilities": routing_view(p),
            "interface": interface(p),
        }
        for p in PROVIDERS.values()
    }


def planned_for_ats(
    ats: str, providers: dict[str, ProviderSpec] | None = None
) -> ProviderSpec | None:
    """The planned (specification-only) adapter for an ATS identity, if any."""
    specs = (PROVIDERS if providers is None else providers).values()
    return next((p for p in specs if p.stage == "planned" and p.ats == ats), None)


def implemented_for_ats(ats: str) -> list[ProviderSpec]:
    return [p for p in PROVIDERS.values() if p.stage == "implemented" and p.ats == ats]
