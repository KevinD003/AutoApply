"""Which destinations may be executed, and by which adapter.

Phase C supports exactly one adapter, for local synthetic fixture receivers, and only outside
production. Every real employer destination is refused: there is no tested live adapter.
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
    return "fixture_ats"
