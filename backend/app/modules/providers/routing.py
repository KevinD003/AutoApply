"""Which provider would execute a destination now, and why (docs/provider-architecture.md).

  1. Identify the destination and its ATS (job host, form source, origin). A job on an ATS with
     only a planned adapter (Workday) is a manual handoff; a captured form whose source names a
     different ATS than the job's host is refused, never routed to the wrong adapter.
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
from app.modules.jobs.canonical import canonicalize_url, detect_ats
from app.modules.providers import registry
from app.modules.providers.model import Capability, Kind


@dataclass
class RouteDecision:
    route: str  # "api" | "browser" | "checkpoint" | "manual_handoff"
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


# The ATS a captured form's source belongs to (None: the generic fixture form).
FORM_SOURCE_ATS = {"greenhouse_api": "greenhouse", "greenhouse_api_dom": "greenhouse"}


def ats_of(url: str | None) -> str:
    """The ATS identity of a job URL, from known hostnames only ("unknown" otherwise)."""
    if not url:
        return "unknown"
    try:
        return detect_ats(canonicalize_url(url)).provider
    except Exception:  # noqa: BLE001 - an unparseable URL identifies nothing
        return "unknown"


def _identity_refusal(destination: dict, steps: list[str]) -> RouteDecision | None:
    ats = destination.get("ats_provider") or ats_of(destination.get("url"))
    form_ats = FORM_SOURCE_ATS.get(destination.get("form_source") or "")
    steps.append(f"identity: ATS {ats}; form source {destination.get('form_source') or 'html'}")
    planned = registry.planned_for_ats(ats)
    if planned is not None:
        steps.append(f"{planned.name}: planned adapter only (no automation exists)")
        label = ats.capitalize()
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             f"{label} applications are not supported yet: NoEfforts has only a "
                             f"specification for a {label} adapter. Apply on the employer's site "
                             "and record it in the tracker.")  # fmt: skip
    if form_ats and ats != "unknown" and ats != form_ats:
        steps.append(f"identity: the form was captured as {form_ats} but the job is on {ats}")
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             "The captured form does not belong to this job's application "
                             "system. Apply on the employer's site.")  # fmt: skip
    return None


def decide(destination: dict, user_id=None) -> RouteDecision:
    from app.modules.execution import policy

    s = get_settings()
    origin = (destination.get("origin") or "").lower()
    steps: list[str] = []
    refused = _identity_refusal(destination, steps)
    if refused is not None:
        return refused
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


def form_checkpoint(schema: dict | None) -> list[str]:
    """Why a captured form needs the user before anything is disclosed: each required control
    NoEfforts cannot fill deterministically (never turned into a guessed answer)."""
    reasons = []
    for f in (schema or {}).get("fields", []):
        if f.get("type") == "unsupported" and f.get("required"):
            why = f.get("unsupported_reason") or "unsupported control"
            reasons.append(f"{f.get('label') or f.get('key')}: {why}")
    return reasons


def route_for_job(db, job) -> RouteDecision:
    """How NoEfforts could apply to a tracked job now, before any package exists.

      * the job's ATS has only a planned adapter          → manual handoff (says so)
      * no application form captured                      → manual handoff
      * the form has required controls NoEfforts cannot fill → checkpoint (the user's step)
      * otherwise                                         → decide() on the captured destination
    A job source (e.g. Freehire) never supplies the form: only a capture does."""
    from urllib.parse import urljoin, urlsplit

    from sqlalchemy import select as _select

    from app.modules.preparation.models import JobForm

    steps: list[str] = []
    refused = _identity_refusal({"url": job.url, "ats_provider": job.ats_provider}, steps)
    if refused is not None:
        return refused
    form = db.scalar(_select(JobForm).where(JobForm.job_id == job.id,
                                            JobForm.user_id == job.user_id)
                     .order_by(JobForm.version.desc()))  # fmt: skip
    if form is None:
        steps.append("no application form captured yet")
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             "Capture the application form first.")  # fmt: skip
    reasons = form_checkpoint(form.schema)
    if reasons:
        steps.append("required controls NoEfforts cannot fill: " + "; ".join(reasons))
        return RouteDecision("checkpoint", "manual_handoff", steps,
                             "This form has required controls NoEfforts cannot fill ("
                             + "; ".join(reasons) + "). Nothing is sent; complete the "
                             "application on the employer's site.")  # fmt: skip
    p = urlsplit(job.url or "")
    action = (form.schema or {}).get("action")
    destination = {
        "origin": f"{p.scheme}://{p.netloc}" if p.netloc else None,
        "url": job.url,
        "submit_url": urljoin(job.url, action) if job.url and action else None,
        "form_source": form.source,
        "ats_provider": job.ats_provider,
    }
    d = decide(destination, job.user_id)
    return RouteDecision(d.route, d.provider, steps + d.steps, d.message)
