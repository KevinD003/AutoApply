"""Which provider would execute a destination now, and why (docs/provider-architecture.md).

  1. Identify the destination and its ATS (form source, origin).
  2. Is any provider enabled for it? Real destinations are not (no provider has live support).
  3. The approval binding (provider + version) is checked by `policy.check_binding` against
     this decision, so a change of provider, version or route retires the approval.
  4. An authorized API route is chosen only with the user's active authorization for that
     provider and origin, configured credentials, and declared API-submission support.
  5. Otherwise the isolated-browser adapter, if one is explicitly supported.
  6. Otherwise a manual handoff: the user applies on the employer's site.

Observation and discovery providers are never routes: a read-only observation can never become
filling, and finding a job never implies being able to apply to it."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin
from app.modules.providers import registry
from app.modules.providers.model import Capability, Kind


@dataclass
class RouteDecision:
    route: str  # "api" | "browser" | "manual_handoff"
    provider: str
    steps: list[str] = field(default_factory=list)  # why, in order (no content, no secrets)
    message: str = ""  # for the user when the route is a manual handoff


# Which destinations an API provider can serve (identity only; authorization comes later).
def _fake_api_applies(destination: dict) -> bool:
    p = urlsplit(destination.get("url") or "")
    parts = [x for x in p.path.split("/") if x]
    return (
        destination.get("form_source") in ("greenhouse_api_dom", "greenhouse_api")
        and len(parts) == 4
        and parts[0] in ("gh", "gh2")
        and parts[2] == "jobs"
    )


API_IDENTITY = {"fake_api": _fake_api_applies}


def api_credentials_configured(provider: str) -> bool:
    if provider == "fake_api":
        return bool(get_settings().fake_api_token)
    return False


def active_authorization(user_id, provider: str, origin: str) -> bool:
    if user_id is None:
        return False
    from app.core.db import SessionLocal
    from app.modules.providers.models import ApiAuthorization

    with SessionLocal() as db:
        return (
            db.scalar(
                select(ApiAuthorization.id).where(
                    ApiAuthorization.user_id == user_id,
                    ApiAuthorization.provider == provider,
                    ApiAuthorization.origin == origin.lower(),
                    ApiAuthorization.scope == "submit",
                    ApiAuthorization.revoked_at.is_(None),
                )
            )
            is not None
        )


def decide(destination: dict, user_id=None) -> RouteDecision:
    from app.modules.execution import policy

    s = get_settings()
    origin = (destination.get("origin") or "").lower()
    steps = [f"identity: form source {destination.get('form_source') or 'html'}"]
    try:
        browser = policy.adapter_for(destination)  # also: production / real origins refused
    except policy.UnsupportedDestination as e:
        browser, refusal = None, str(e)
    else:
        refusal = ""
    real = not is_fixture_origin(origin) or s.env == "production"
    if real:
        steps.append("enabled: no provider is enabled for real destinations")
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             refusal or "Apply on the employer's site.")  # fmt: skip
    for spec in registry.of_kind(Kind.api):
        applies = API_IDENTITY.get(spec.name, lambda d: False)(destination)
        if not applies:
            continue
        if s.env not in spec.environments:
            steps.append(f"api {spec.name}: not enabled in this environment")
            continue
        if not spec.support(Capability.official_api_submission).fixture:
            steps.append(f"api {spec.name}: API submission not supported")
            continue
        if not active_authorization(user_id, spec.name, origin):
            steps.append(f"api {spec.name}: no active authorization from the user")
            continue
        if not api_credentials_configured(spec.name):
            steps.append(f"api {spec.name}: credentials not configured")
            continue
        steps.append(f"api {spec.name}: authorized, credentials configured, supported")
        return RouteDecision("api", spec.name, steps)
    if browser is not None:
        steps.append(f"browser {browser}: supported for this destination")
        return RouteDecision("browser", browser, steps)
    steps.append("no provider supports this destination")
    return RouteDecision("manual_handoff", "manual_handoff", steps, refusal)
