"""Which destinations may be executed, and by which adapter.

Two adapters exist, both for local synthetic fixtures only and only outside production. Every
real employer destination is refused: no adapter has been verified against a real employer.
"""

from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin

# Capability flags per adapter. A job *source* (e.g. a discovery feed) implies none of these.
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
}


class UnsupportedDestination(ValueError):
    pass


def adapter_for(destination: dict) -> str:
    origin, submit = destination.get("origin"), destination.get("submit_url")
    if get_settings().env == "production":
        raise UnsupportedDestination("Automatic submission is not available in production yet.")
    if not origin or not submit:
        raise UnsupportedDestination(
            "This job has no captured destination to submit to. Apply on the employer's site "
            "and record it in the tracker."
        )
    if not is_fixture_origin(origin):
        raise UnsupportedDestination(
            "Automatic submission is only supported for local test fixtures in this version. "
            "Apply on the employer's site and record it in the tracker."
        )
    sp = urlsplit(submit)
    if f"{sp.scheme}://{sp.netloc}".lower() != origin.lower():
        raise UnsupportedDestination("The form submits to a different site than the job page.")
    if destination.get("form_source") == "greenhouse_api":
        return "greenhouse_hosted"
    return "fixture_ats"
