"""Every provider NoEfforts knows, with its operations and evidence-backed capabilities.

Nothing here is enabled for a real destination: `real_destinations_enabled` is false
everywhere, so no capability has live filling or live submission support. "observed" means
seen on one real page under a separately approved read-only scope, never more."""

from app.modules.providers.model import (
    FIXTURE,
    Capability,
    Kind,
    Operation,
    ProviderSpec,
    Support,
    check_spec,
    matrix,
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
            C.captcha_checkpoint: Support(fixture=True, note="stop and hand off; never solved"),
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
                note="strategies fixture-only; no opening evidence on the real page (run #9)",
            ),
            C.file_upload: FIXTURE,
            C.captcha_checkpoint: Support(fixture=True, note="stop and hand off; never solved"),
            C.final_submit: FIXTURE,
            C.confirmation_detection: FIXTURE,
            C.reconciliation: _USER_RECONCILES,
        },  # fmt: skip
        status="Fixture filling only. One real posting observed read-only; refused for live use"
        " (dropdowns, location, unmatched required controls).",
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
        status="Ran 9 times under separate approvals; never fills or submits.",
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
                note="local fixture of the documented API; no live call made or authorized",
            )
        },
        status="Potential future discovery provider; not yet connected or validated.",
    ),
    "manual_handoff": ProviderSpec(
        name="manual_handoff",
        kind=Kind.manual,
        description="Nothing supported: the user applies on the employer's site and records it.",
        operations=frozenset({Op.checkpoint}),
        environments=("development", "test", "production"),
        status="Always available.",
    ),
}

for _spec in PROVIDERS.values():
    check_spec(_spec)


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
        }
        for p in PROVIDERS.values()
    }
