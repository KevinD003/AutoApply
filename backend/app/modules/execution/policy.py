"""Which destinations may be executed, and by which adapter.

Four adapters exist (`ADAPTER_VERSIONS`): three browser adapters (`fixture_ats`,
`greenhouse_hosted`, `greenhouse_dom`) and the authorized-API adapter `fake_api`. All run only
against local synthetic fixtures and only outside production. Every real employer destination is
refused by `adapter_for`, whatever the flags below say: no adapter has been verified against a
real employer.
"""

from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin
from app.modules.preparation import forms
from app.modules.preparation import greenhouse as gh
from app.modules.preparation import greenhouse_dom as gdom

# Capability flags per browser adapter (the API adapter's are in providers/registry.py). A job
# *source* (e.g. a discovery feed) implies none of these. `real_destinations` is stated on the
# Greenhouse entries because their forms are modelled on real ones; it is false for every
# adapter, since `adapter_for` refuses any origin that is not a local fixture.
CAPABILITIES: dict[str, dict] = {
    "fixture_ats": {
        "description": "Local synthetic ATS receiver (fictional employer). Test/development only.",
        "environments": ["development", "test"],
        "inspect": True,
        "extract": True,
        "fill": True,
        "upload": True,
        "checkpoint": True,
        "submit": True,
        "confirm": True,
        "tested_against": ["fixtures/ats_receiver"],
    },
    "greenhouse_hosted": {
        "description": (
            "Greenhouse-style hosted application form (single page). Verified only against a "
            "labelled local approximation, not against any real employer's form."
        ),
        "environments": ["development", "test"],
        "inspect": True,  # job post JSON + rendered page, cross-checked
        "extract": True,
        "fill": True,  # text, email, phone, textarea, select, multi-select, consent checkbox
        "upload": True,  # attachments uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # emailed security code; unsupported controls stop at preparation
        "submit": True,
        "confirm": True,  # confirmation page (no application id is shown)
        "real_destinations": False,
        # Each is modelled on public descriptions only; none has been seen on a real form.
        "unverified": {
            "security_code": "synthetic: the emailed-code step is the fixture's own design",
            "confirmation": "synthetic: real confirmation pages and redirects are not observed",
            "attachments": "synthetic: the upload endpoint and attachment ids are the fixture's",
        },
        "unsupported": [
            "CAPTCHA or bot checks (stop, never bypassed)",
            "location pickers with hidden coordinates",
            "multi-page or login-gated applications",
            "pasting text instead of attaching a document",
        ],
        "tested_against": ["fixtures/ats_receiver/greenhouse_like.py"],
    },
    "greenhouse_dom": {
        "description": (
            "Greenhouse-style hosted form whose controls have ids but no names, with ARIA "
            "comboboxes (structure observed at load on one real posting). Verified only against "
            "a second labelled local approximation, not against any real employer's form."
        ),
        "environments": ["development", "test"],
        "inspect": True,  # job post JSON mapped to page controls by id + accessible name
        "extract": True,
        "fill": True,  # text, email, phone, textarea, single-choice combobox
        "upload": True,  # attachments uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # unsupported controls and unknown conditions stop at preparation
        "submit": True,
        "confirm": True,  # confirmation message (no application id is shown)
        "real_destinations": False,
        # Each is a fixture assumption; none has been seen working on a real form.
        "unverified": {
            "combobox": "synthetic: opened by click, options in the DOM, value read back",
            "dropdown_strategies": "synthetic only: click, ArrowDown or a single trigger, with "
            "post-action evidence and readback (adapters/dropdowns.py CAPABILITIES); run #9 saw "
            "no opening evidence on the real page within its window",
            "attachments": "synthetic: upload endpoint, status element and attachment ids",
            "submission": "synthetic: JSON POST to the form's submit path",
            "confirmation": "synthetic: a status message replacing the form",
            "conditions": "synthetic: hidden-at-load questions with no visible trigger",
        },
        "unsupported": [
            "CAPTCHA or bot checks (stop, never bypassed)",
            "location search pickers and hidden coordinates",
            "multi-choice comboboxes",
            "questions shown by page logic NoEfforts cannot see",
            "security-code steps",
            "pasting text instead of attaching a document",
        ],
        "tested_against": ["fixtures/ats_receiver/greenhouse_v2.py"],
    },
}


# What each adapter does with an approved package (how it locates, fills, verifies and submits),
# including the extraction/mapping rules its live checks rely on. An approval is bound to the
# adapter and version current when it was given; bump a version whenever that meaning changes,
# and only the approvals bound to that adapter stop matching.
ADAPTER_VERSIONS: dict[str, str] = {
    "fixture_ats": f"fixture-ats-1+{forms.EXTRACTION_VERSION}",
    "greenhouse_hosted": f"greenhouse-hosted-1+{gh.EXTRACTION_VERSION}",
    # 2: required is checked by every page signal; only a page-required field the package
    # leaves empty blocks (the job data's requirement is never lowered).
    # 3: dropdowns without a list at load are handled by explicit, evidence-checked strategies
    # (adapters/dropdowns.py), verified before disclosure.
    "greenhouse_dom": f"greenhouse-dom-3+{gdom.EXTRACTION_VERSION}",
    # The internal authorized-API contract, exercised only against the local fake API.
    "fake_api": "fake-api-1",
}
# Approvals given before bindings were recorded meant what the code then did: these routes and
# these versions. They stay valid exactly as long as that is still what would run.
LEGACY_VERSIONS: dict[str, str] = {
    "fixture_ats": "fixture-ats-1+html-v1",
    "greenhouse_hosted": "greenhouse-hosted-1+greenhouse-v1",
}


class UnsupportedDestination(ValueError):
    """`code` is a fixed reason code (providers.routing.REASONS), safe to record."""

    def __init__(self, message: str, code: str = "no_supported_provider"):
        super().__init__(message)
        self.code = code


class BindingChanged(ValueError):
    """The way NoEfforts would execute this package differs from what was approved."""


def execution_binding(destination: dict, user_id=None) -> dict | None:
    """{"adapter", "adapter_version"} of the provider that would execute this destination now
    (providers.routing.decide: authorized API, else browser), or None for a manual handoff
    (then nothing can be queued anyway). The route follows from the provider's kind."""
    from app.modules.providers import routing

    d = routing.decide(destination, user_id)
    if d.route == "manual_handoff":
        return None
    return {"adapter": d.provider, "adapter_version": ADAPTER_VERSIONS[d.provider]}


def approved_binding(approval, destination: dict) -> dict | None:
    """What an approval was given for. Approvals without a recorded binding predate it: they
    meant the route the code had then (greenhouse_api -> greenhouse_hosted, else fixture_ats)."""
    if approval.adapter is not None:
        return {"adapter": approval.adapter, "adapter_version": approval.adapter_version}
    name = "greenhouse_hosted" if destination.get("form_source") == "greenhouse_api" else (
        "fixture_ats" if destination.get("form_source") != "greenhouse_api_dom" else None
    )  # fmt: skip
    if name is None:
        return None  # that source did not exist before bindings: nothing was approved for it
    return {"adapter": name, "adapter_version": LEGACY_VERSIONS[name]}


def check_binding(approval, destination: dict, adapter: str | None = None) -> dict:
    """The current binding, if it is what the user approved; otherwise BindingChanged.
    `adapter`: the one recorded on a queued attempt, which must also still match."""
    now = execution_binding(destination, getattr(approval, "user_id", None))
    if now is None:
        raise UnsupportedDestination("No adapter may execute this destination.", "no_adapter")
    if approved_binding(approval, destination) != now or (adapter and adapter != now["adapter"]):
        raise BindingChanged(
            "The way NoEfforts would fill and submit this form changed after you approved it. "
            "Review the package and approve it again."
        )
    return now


def adapter_for(destination: dict) -> str:
    origin, submit = destination.get("origin"), destination.get("submit_url")
    if get_settings().env == "production":
        raise UnsupportedDestination(
            "Automatic submission is not available in production yet.", "production_disabled"
        )
    if not origin or not submit:
        raise UnsupportedDestination(
            "This job has no captured destination to submit to. Apply on the employer's site "
            "and record it in the tracker.",
            "no_captured_destination",
        )
    if not is_fixture_origin(origin):
        raise UnsupportedDestination(
            "Automatic submission is only supported for local test fixtures in this version. "
            "Apply on the employer's site and record it in the tracker.",
            "real_destination_disabled",
        )
    sp = urlsplit(submit)
    if f"{sp.scheme}://{sp.netloc}".lower() != origin.lower():
        raise UnsupportedDestination(
            "The form submits to a different site than the job page.", "submit_origin_mismatch"
        )
    if destination.get("form_source") == "greenhouse_api":
        return "greenhouse_hosted"
    if destination.get("form_source") == "greenhouse_api_dom":
        return "greenhouse_dom"
    return "fixture_ats"
