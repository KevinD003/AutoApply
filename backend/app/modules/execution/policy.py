"""Which destinations may be executed, and by which adapter.

Eight adapters exist (`ADAPTER_VERSIONS`): seven browser adapters (`fixture_ats`,
`greenhouse_hosted`, `greenhouse_dom`, `greenhouse_live`, `fixture_lever`, `fixture_ashby`,
`fixture_workday`) and the authorized-API adapter `fake_api`.
All but `greenhouse_live` run only against local synthetic fixtures and only outside production.
`greenhouse_live` (D102, the Greenhouse pilot) runs only for a form captured from a real
Greenhouse job post while the pilot is on (`live.environment_refusal`: the owner's switch,
production, container isolation) and only on Greenhouse's board hosts. Every other real employer
destination is refused by `adapter_for`, whatever the flags below say.
"""

from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin
from app.modules.execution import live
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
            "Greenhouse-style hosted application form (single page). Tested only against a "
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
            "comboboxes (structure observed at load on one real posting). Tested only against "
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
    "greenhouse_live": {
        "description": (
            "The Greenhouse pilot (D102): the id-mapping adapter (greenhouse_dom) on a real "
            "Greenhouse-hosted job post, captured from its public job data, for the owner's "
            "account only, in production with container isolation, when the owner switched it "
            "on. Tested against the second labelled local approximation standing in for a "
            "board host; never yet run on a real page."
        ),
        "environments": ["production", "test"],
        "inspect": True,  # job data from the Job Board API; the page mapped before any entry
        "extract": True,
        "fill": True,  # text, email, phone, textarea, single-choice combobox
        "upload": True,  # attachments uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # unsupported or unlisted controls stop before anything is entered
        "submit": True,  # only after a successful rehearsal on the employer's path (E6)
        "confirm": True,  # the approximation's message; on a real page: unknown until seen
        "real_destinations": True,  # Greenhouse's board hosts only, while the pilot is on
        "unverified": {
            "page": "the real page is mapped by the greenhouse_dom rules, observed read-only on "
            "one posting only; unlisted controls (e.g. a phone country picker) stop the attempt",
            "dropdown_strategies": "synthetic only; run #9 saw no opening evidence on a real page",
            "attachments": "synthetic: a real page's upload acknowledgement has not been seen",
            "submission": "synthetic: how a real form submits has not been seen",
            "confirmation": "synthetic: an unrecognised result is unknown, never resent",
        },
        "unsupported": [
            "CAPTCHA or bot checks (stop, never bypassed)",
            "location search pickers and hidden coordinates",
            "multi-choice comboboxes",
            "controls the job data does not list",
            "security-code steps",
            "pasting text instead of attaching a document",
        ],
        "tested_against": ["fixtures/ats_receiver/greenhouse_v2.py"],
    },
    "fixture_lever": {
        "description": (
            "Lever-style hosted form (a posting page, then its form page), served by a labelled "
            "local approximation (fictional employer). It identifies no Lever posting and is "
            "never used for one: a real Lever job is a manual handoff."
        ),
        "environments": ["development", "test"],
        "inspect": True,  # the posting's form page, read by the generic extractor
        "extract": True,
        "fill": True,  # text, email, phone, url, textarea, select, radio, checkbox group, consent
        "upload": True,  # documents uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # pickers, unknown facts and bot checks stop before approval
        "submit": True,
        "confirm": True,  # a confirmation page with a reference, bound to the attempt
        "real_destinations": False,
        # Each is the approximation's own design; none has been seen on a real Lever form.
        "unverified": {
            "uploads": "synthetic: documents uploaded when chosen, to the fixture's endpoint",
            "resume_prefill": "synthetic: a parsed resume overwriting page fields (one mode)",
            "confirmation": "synthetic: a confirmation page with a reference",
        },
        "unsupported": [
            "CAPTCHA or bot checks (stop, never solved)",
            "location and other search-as-you-type pickers",
            "verification codes after submitting",
            "accounts, passwords or sign-in",
        ],
        "tested_against": ["fixtures/ats_receiver/lever_like.py"],
    },
    "fixture_ashby": {
        "description": (
            "Ashby-style hosted form (a posting, then its application tab), served by a "
            "labelled local approximation (fictional employer). It identifies no Ashby posting "
            "and is never used for one: a real Ashby job is a manual handoff."
        ),
        "environments": ["development", "test"],
        "inspect": True,  # the posting's application page, read by the generic extractor
        "extract": True,
        "fill": True,  # text, email, phone, url, number, textarea, select, Yes/No, checkboxes
        "upload": True,  # files uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # pickers, button-only Yes/No, unknown facts, the spam check
        "submit": True,
        "confirm": True,  # a confirmation page with a reference, bound to the attempt
        "real_destinations": False,
        # Each is the approximation's own design; none has been seen on a real Ashby form.
        "unverified": {
            "uploads": "synthetic: files uploaded when chosen, to the fixture's endpoint",
            "resume_autofill": "synthetic: a resume upload overwriting page fields (one mode)",
            "spam_check": "synthetic marker: Ashby documents a score, no widget",
            "confirmation": "synthetic: a confirmation page with a reference",
        },
        "unsupported": [
            "the spam check or any bot check (stop, never solved or retried)",
            "the candidate-location picker and other search-as-you-type pickers",
            "Yes/No buttons with no native input",
            "the cookie-consent banner (never clicked)",
            "accounts, passwords or sign-in",
        ],
        "tested_against": ["fixtures/ats_receiver/ashby_like.py"],
    },
    "fixture_workday": {
        "description": (
            "Workday-style hosted application (a posting, then its application page), served by "
            "a labelled local approximation (fictional employer), checkpoint-first. It "
            "identifies no Workday posting and is never used for one: a real Workday job is a "
            "manual handoff."
        ),
        "environments": ["development", "test"],
        "inspect": True,  # the application page, read by the generic extractor and its checks
        "extract": True,
        "fill": True,  # a single page only: text, email, phone, Yes/No, radio, select, consent
        "upload": True,  # files uploaded when chosen (counted as disclosures)
        "checkpoint": True,  # accounts, several pages, prefill, location lists, pickers
        "submit": True,
        "confirm": True,  # a confirmation page with a reference, bound to the attempt
        "real_destinations": False,
        # Each is the approximation's own design; none has been seen on a real Workday tenant.
        "unverified": {
            "single_page": "synthetic: an 'apply manually' application on one page",
            "uploads": "synthetic: files uploaded when chosen, to the fixture's endpoint",
            "resume_parse": "synthetic: a resume upload overwriting page fields (one mode)",
            "confirmation": "synthetic: a confirmation page with a reference",
        },
        "unsupported": [
            "candidate accounts, sign-in, passwords and email verification (stop)",
            "applications on several pages (stop; each page would send its own answers)",
            "values the page filled in itself: a parsed resume or a previous application",
            "location lists that depend on another answer, search-as-you-type pickers",
            "custom dropdowns with no native input",
        ],
        "tested_against": ["fixtures/ats_receiver/workday_like.py"],
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
    # D102: the same rules on a real board host, from a form captured as `greenhouse_live`.
    "greenhouse_live": f"greenhouse-live-1+{gdom.EXTRACTION_VERSION}",
    # D85: the Lever-style approximation's form, read by the generic extractor.
    "fixture_lever": f"fixture-lever-1+{forms.EXTRACTION_VERSION}",
    # D87: the Ashby-style approximation's form, read by the generic extractor plus its spam
    # check as the bot-check field (preparation/ashby.py).
    "fixture_ashby": f"fixture-ashby-1+{forms.EXTRACTION_VERSION}",
    # D88: the Workday-style approximation's single application page, read by the generic
    # extractor plus its checkpoints (several pages, prefill, dependent location lists).
    "fixture_workday": f"fixture-workday-1+{forms.EXTRACTION_VERSION}",
    # The internal authorized-API contract, exercised only against the local fake API.
    "fake_api": "fake-api-1",
}
# Approvals given before bindings were recorded meant what the code then did: these routes and
# these versions. They stay valid exactly as long as that is still what would run.
LEGACY_VERSIONS: dict[str, str] = {
    "fixture_ats": "fixture-ats-1+html-v1",
    "greenhouse_hosted": "greenhouse-hosted-1+greenhouse-v1",
}


# What an approval records as its adapter when the route was a manual handoff: never no adapter,
# which `approved_binding` reads as an approval given before bindings were recorded.
MANUAL_BINDING = "manual_handoff"


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
    source = destination.get("form_source")
    name = "greenhouse_hosted" if source == "greenhouse_api" else (
        "fixture_ats"
        if source not in ("greenhouse_api_dom", "fixture_lever", "fixture_ashby",
                          "fixture_workday")
        else None
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


# Shown wherever these refusals apply (here and in providers.routing.route_for_job).
PRODUCTION_DISABLED = "Automatic submission is not available in production yet."
REAL_DESTINATION_DISABLED = (
    "Automatic submission is only supported for local test fixtures in this version. "
    "Apply on the employer's site and record it in the tracker."
)


# Which adapter executes a captured form, by the form's source. The generic sources are the local
# fixture form and forms read from page HTML or entered by hand (and a destination that names
# none); every other source is refused, never handed to the generic adapter.
FORM_SOURCE_ADAPTERS = {
    "greenhouse_api": "greenhouse_hosted",
    "greenhouse_api_dom": "greenhouse_dom",
    # D102: only adapter_for's pilot branch reaches this entry (it checks the pilot first).
    "greenhouse_live": "greenhouse_live",
    "fixture_lever": "fixture_lever",
    "fixture_ashby": "fixture_ashby",
    "fixture_workday": "fixture_workday",
}
GENERIC_FORM_SOURCES = frozenset({None, "fixture", "html", "manual"})
GENERIC_ADAPTER = "fixture_ats"
NO_ADAPTER_FOR_SOURCE = (
    "No adapter fills forms captured this way. Apply on the employer's site and record it in "
    "the tracker."
)


def _live_adapter(destination: dict) -> str:
    """D102: a form captured from a real Greenhouse job post, on its board host, while the
    pilot is on; refused otherwise (never handed to another adapter)."""
    why = live.environment_refusal()
    if why == "not_enabled":
        raise UnsupportedDestination(live.WHY[why], "live_not_enabled")
    if why == "needs_production":
        raise UnsupportedDestination(live.WHY[why], "live_needs_production")
    if why:  # "needs_container", the only other environment refusal
        raise UnsupportedDestination(live.WHY[why], "live_needs_container")
    origin, submit = destination.get("origin"), destination.get("submit_url")
    if not origin or not submit:
        raise UnsupportedDestination(
            "This job has no captured destination to submit to. Apply on the employer's site "
            "and record it in the tracker.",
            "no_captured_destination",
        )
    if not live.page_origin_allowed(origin) or live.posting(destination.get("url")) is None:
        raise UnsupportedDestination(REAL_DESTINATION_DISABLED, "real_destination_disabled")
    sp = urlsplit(submit)
    if f"{sp.scheme}://{sp.netloc}".lower() != origin.lower():
        raise UnsupportedDestination(
            "The form submits to a different site than the job page.", "submit_origin_mismatch"
        )
    return live.ADAPTER


def adapter_for(destination: dict) -> str:
    origin, submit = destination.get("origin"), destination.get("submit_url")
    if destination.get("form_source") == live.FORM_SOURCE:
        return _live_adapter(destination)
    if get_settings().env == "production":
        raise UnsupportedDestination(PRODUCTION_DISABLED, "production_disabled")
    if not origin or not submit:
        raise UnsupportedDestination(
            "This job has no captured destination to submit to. Apply on the employer's site "
            "and record it in the tracker.",
            "no_captured_destination",
        )
    if not is_fixture_origin(origin):
        raise UnsupportedDestination(REAL_DESTINATION_DISABLED, "real_destination_disabled")
    sp = urlsplit(submit)
    if f"{sp.scheme}://{sp.netloc}".lower() != origin.lower():
        raise UnsupportedDestination(
            "The form submits to a different site than the job page.", "submit_origin_mismatch"
        )
    source = destination.get("form_source")
    if source in FORM_SOURCE_ADAPTERS:
        return FORM_SOURCE_ADAPTERS[source]
    if source in GENERIC_FORM_SOURCES:
        return GENERIC_ADAPTER
    raise UnsupportedDestination(NO_ADAPTER_FOR_SOURCE, "no_adapter")
