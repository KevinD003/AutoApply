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
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin
from app.modules.jobs.canonical import canonicalize_url, detect_ats
from app.modules.providers import registry
from app.modules.providers.model import Capability, Kind

# Reason codes: fixed, safe to record (no content, no identifiers). Messages are for the user.
# Every code but FALLBACK_REASON is produced by a known path (tests/test_reason_codes.py);
# FALLBACK_REASON is the fail-closed default that no path is expected to produce.
FALLBACK_REASON = "no_supported_provider"
REASONS = {
    "api_authorized": "authorized API: the user's grant, credentials and declared support",
    "browser_supported": "a browser adapter supports this form source and origin",
    "planned_adapter_only": "the job's ATS has only a planned (specification-only) adapter",
    "form_ats_mismatch": "the captured form belongs to a different ATS than the job",
    "no_form_captured": "no application form has been captured from the employer's page",
    "unsupported_required_control": "a required control NoEfforts cannot fill",
    "real_destination_disabled": "real destinations are not enabled for any provider",
    "production_disabled": "automatic submission is not available in production",
    "no_captured_destination": "no destination to submit to",
    "submit_origin_mismatch": "the form submits to a different site than the job page",
    "no_adapter": "no adapter may execute this destination",
    "no_supported_provider": "no provider supports this destination",
    "source_record_incomplete": "the discovery record is incomplete",
    "source_posting_closed": "the posting was closed at its source before it was linked",
}
AUTHORIZATION_STATES = ("granted", "none", "not_applicable")


@dataclass
class RouteDecision:
    route: str  # "api" | "browser" | "checkpoint" | "manual_handoff"
    provider: str
    steps: list[str] = field(default_factory=list)  # why, in order (no content, no secrets)
    message: str = ""  # for the user when the route is a manual handoff
    reason: str = FALLBACK_REASON  # a REASONS code
    authorization: str = "not_applicable"  # the API grant state, when an API provider applies


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
                             "and record it in the tracker.", "planned_adapter_only")  # fmt: skip
    if form_ats and ats != "unknown" and ats != form_ats:
        steps.append(f"identity: the form was captured as {form_ats} but the job is on {ats}")
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             "The captured form does not belong to this job's application "
                             "system. Apply on the employer's site.",
                             "form_ats_mismatch")  # fmt: skip
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
        browser, refusal, refusal_code = None, str(e), e.code
    else:
        refusal, refusal_code = "", FALLBACK_REASON
    real = not is_fixture_origin(origin) or s.env == "production"
    if real:
        steps.append("enabled: no provider is enabled for real destinations")
        code = refusal_code if refusal else "real_destination_disabled"
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             refusal or "Apply on the employer's site.", code)  # fmt: skip
    authorization = "not_applicable"
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
            authorization = "none" if authorization != "granted" else authorization
            steps.append(f"api {spec.name}: no active authorization from the user")
            continue
        authorization = "granted"
        if not api_credentials_configured(spec.name):
            steps.append(f"api {spec.name}: credentials not configured")
            continue
        steps.append(f"api {spec.name}: authorized, credentials configured, supported")
        return RouteDecision("api", spec.name, steps, "", "api_authorized", authorization)
    if browser is not None:
        steps.append(f"browser {browser}: supported for this destination")
        return RouteDecision("browser", browser, steps, "", "browser_supported", authorization)
    steps.append("no provider supports this destination")
    return RouteDecision("manual_handoff", "manual_handoff", steps, refusal, refusal_code,
                         authorization)  # fmt: skip


def form_checkpoint(schema: dict | None) -> list[str]:
    """The keys of the required controls NoEfforts cannot fill deterministically (never turned
    into a guessed answer). Keys and labels come from the employer's form: they are counted in
    route messages and steps, never quoted there or recorded in audit events."""
    return [f.get("key") or "" for f in (schema or {}).get("fields", [])
            if f.get("type") == "unsupported" and f.get("required")]  # fmt: skip


def route_for_job(db, job) -> RouteDecision:
    """How NoEfforts could apply to a tracked job now, before any package exists.

      * the job's ATS has only a planned adapter          → manual handoff (says so)
      * no application form captured                      → manual handoff
      * the form has required controls NoEfforts cannot fill → checkpoint (the user's step)
      * otherwise                                         → decide() on the captured destination
    A job source (e.g. Freehire) never supplies the form: only a capture does."""
    from app.modules.preparation.models import JobForm

    steps: list[str] = []
    refused = _identity_refusal({"url": job.url, "ats_provider": job.ats_provider}, steps)
    if refused is not None:
        return refused
    form = db.scalar(select(JobForm).where(JobForm.job_id == job.id,
                                           JobForm.user_id == job.user_id)
                     .order_by(JobForm.version.desc()))  # fmt: skip
    if form is None:
        steps.append("no application form captured yet")
        return RouteDecision("manual_handoff", "manual_handoff", steps,
                             "Capture the application form first.", "no_form_captured")  # fmt: skip
    blocked = form_checkpoint(form.schema)
    if blocked:
        n = len(blocked)
        steps.append(f"required controls NoEfforts cannot fill: {n}")
        return RouteDecision("checkpoint", "manual_handoff", steps,
                             f"This form has {n} required control{'s' if n != 1 else ''} "
                             "NoEfforts cannot fill (see the application's open questions). "
                             "Nothing is sent; complete the application on the employer's "
                             "site.", "unsupported_required_control")  # fmt: skip
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
    return RouteDecision(d.route, d.provider, steps + d.steps, d.message, d.reason,
                         d.authorization)  # fmt: skip


AUDIT_ROUTE = {"api": "api", "browser": "browser", "checkpoint": "checkpoint",
               "manual_handoff": "manual"}  # fmt: skip
EVIDENCE_CAPABILITY = {"api": Capability.official_api_submission,
                       "browser": Capability.deterministic_fill}  # fmt: skip


def evidence_level(d: RouteDecision) -> str:
    """The evidence behind a route: the chosen provider's support level for what the route does
    (API submission or browser filling); "none" for a checkpoint or a manual handoff."""
    spec = registry.PROVIDERS.get(d.provider)
    cap = EVIDENCE_CAPABILITY.get(d.route)
    return spec.support(cap).level() if spec and cap else "none"


def audit_route(db, user_id, job_id, d: RouteDecision) -> bool:
    """Record a route decision with safe metadata only: the internal job id, the decision, the
    provider key and adapter version, the reason code, the evidence level behind the route and
    the authorization state. Never messages, steps, URLs, labels or applicant data.

    A decision identical to the job's last recorded one is not recorded again: checking the same
    route twice changes nothing, so only changes reach the audit trail (two concurrent first
    checks may each record one). Returns whether a row was added."""
    from app.modules.audit.models import AuditEvent
    from app.modules.audit.service import record, sanitize
    from app.modules.execution.policy import ADAPTER_VERSIONS

    route = AUDIT_ROUTE.get(d.route, "manual")
    version = ADAPTER_VERSIONS.get(d.provider)
    reason = d.reason if d.reason in REASONS else FALLBACK_REASON
    evidence = evidence_level(d)
    grant = d.authorization if d.authorization in AUTHORIZATION_STATES else "not_applicable"
    meta = {"route": route, "provider": d.provider, "adapter_version": version,
            "reason_code": reason, "evidence": evidence, "api_grant": grant}  # fmt: skip
    last = db.scalar(
        select(AuditEvent.meta)
        .where(
            AuditEvent.user_id == user_id,
            AuditEvent.action == "route.decision",
            AuditEvent.entity_type == "job",
            AuditEvent.entity_id == str(job_id),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    if last == sanitize(meta, scope=user_id):
        return False
    # Explicit keywords: the audit inventory (tests/test_audit_inventory.py) reads them.
    record(db, user_id, "route.decision", "job", job_id, route=route, provider=d.provider,
           adapter_version=version, reason_code=reason, evidence=evidence,
           api_grant=grant)  # fmt: skip
    return True
