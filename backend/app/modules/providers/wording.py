"""What NoEfforts tells the user about support, in one place (docs/provider-architecture.md,
"Support states and wording").

Every label follows from evidence, never from a hand-written claim:

  * a provider's support state is derived from its stage and capability levels
    (`support_state`);
  * a route's qualifier comes from the evidence level behind it (`routing.evidence_level`);
  * a captured form's label says whether its source is a local test stand-in.

There is no label for a live state. Before any page could show one, it would have to be added
here deliberately, with its evidence, tests and documentation; until then a live level makes
the lookup fail (tests/test_support_wording.py). The frontend shows these labels as served and
writes none of its own."""

import re

from app.modules.providers.model import Kind, ProviderSpec

LIVE_LEVELS = frozenset({"live_fill", "live_submit"})
# Words that would claim support ("Not supported" states its absence). No label and no registry
# text may contain one (tests/test_support_wording.py, providers/admission.py).
CLAIMS = re.compile(r"\blive\b|(?<!not )\bsupported\b|\bavailable\b|\bcompatible\b|\bverified\b",
                    re.I)  # fmt: skip

SUPPORT_LABELS = {
    "manual": "Manual: you apply on the employer's site",
    "planned": "Planned only: no automation exists",
    "not_supported": "Not supported",
    "fixture_only": "Local test fixtures only",
    "observed_read_only": "Local test fixtures only; seen read-only on a real page, never "
    "filled there",
}

ROUTE_LABELS = {
    "api": "Authorized API",
    "browser": "Browser adapter",
    "checkpoint": "Needs you: a step NoEfforts cannot do",
    "manual_handoff": "Manual: apply on the employer's site",
}

# The qualifier a route carries for the evidence behind it ("" for a checkpoint or a manual
# handoff, which have none).
EVIDENCE_LABELS = {
    "none": "",
    "fixture": "local test fixture only",
    "observed": "local test fixture only; seen read-only on a real page",
}

# A captured form's source. Test sources say so; a form read from page HTML the user provided,
# or entered by hand, carries no qualifier (None): the route card says how it could be applied.
FORM_SOURCE_LABELS: dict[str, str | None] = {
    "fixture": "Local test fixture (fictional employer)",
    "greenhouse_api": "Greenhouse-style form: local test approximation (fictional employer)",
    "greenhouse_api_dom": "Greenhouse-style form mapped by id and label: second local test "
    "approximation (fictional employer)",
    "fixture_lever": "Lever-style form: local test approximation (fictional employer)",
    "fixture_ashby": "Ashby-style form: local test approximation (fictional employer)",
    "html": None,
    "manual": None,
}

# C12 (D64): where a package's form sends, shown on its review page.
DESTINATION_LABELS = {
    "fixture": "Local test fixture (fictional employer): nothing reaches a real employer",
    "employer": "The employer's own site",
}


def destination_label(origin: str | None) -> str | None:
    from app.core.urlsafety import is_fixture_origin

    if not origin:
        return None
    return DESTINATION_LABELS["fixture" if is_fixture_origin(origin) else "employer"]


# What an attempt's result counts as (one of providers/evidence.py's classes), shown beside it.
EVIDENCE_CLASS_LABELS = {
    "fixture": "Local test fixture: counts for nothing on a real employer's form",
    "public_doc_expectation": "Expected from public descriptions only; never seen",
    "read_only_observation": "Seen read-only on a real page; never filled there",
    "rehearsal": "Rehearsal on a real employer's form: filled and checked, nothing submitted",
    "real_submission": "Submitted to a real employer's form after a rehearsal",
}

# Where the rehearsal prerequisite stands for a package (execution/rehearsal.py), on its review.
PREREQUISITE_LABELS = {
    "met": "Rehearsal passed",
    "established": "Submitted here before, after a rehearsal",
    "unmet": "Rehearsal needed before the first submission",
    "not_required": "No rehearsal needed (local test form)",
    "not_applicable": "Not applicable: you apply on the employer's site",
}


def support_state(spec: ProviderSpec) -> str:
    """The strongest evidence behind any of the provider's capabilities."""
    if spec.kind == Kind.manual:
        return "manual"
    if spec.stage == "planned":
        return "planned"
    levels = {s.level() for s in spec.capabilities.values()}
    if levels & LIVE_LEVELS:
        return "live"  # deliberately unlabelled: see the module docstring
    if "observed" in levels:
        return "observed_read_only"
    if "fixture" in levels:
        return "fixture_only"
    return "not_supported"


def support_label(spec: ProviderSpec) -> str:
    return SUPPORT_LABELS[support_state(spec)]


def route_label(route: str, evidence: str) -> str:
    """An API or browser route always says what its evidence is; it is never shown bare."""
    qualifier = EVIDENCE_LABELS[evidence]
    if route in ("api", "browser") and not qualifier:
        raise ValueError(f"an {route} route needs evidence behind it, not {evidence!r}")
    return f"{ROUTE_LABELS[route]} ({qualifier})" if qualifier else ROUTE_LABELS[route]


def form_source_label(source: str) -> str | None:
    return FORM_SOURCE_LABELS[source]
