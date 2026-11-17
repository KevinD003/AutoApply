"""D168: the owner's console. The whole automatic application process, start to finish, for one
application (`trace`), what happened across the account's jobs (`activity`), and the server's
switches as they apply to the signed-in account (`system`).

It only reads what NoEfforts already keeps, every query scoped to the signed-in account (another
account's application is a 404, as everywhere). It stores nothing and changes nothing: no switch
is turned and no step is run from here. It never returns a secret. A verification code (a
checkpoint's `code`), a token, key or password is never read out, only whether one is set. A keyed
reference (an attempt's path, an email's message) is never served. There is no screenshot, trace
or raw page to show: execution keeps none (CLAUDE.md), and capture keeps only the form's schema.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import authorizations
from app.core.accounts import owner
from app.core.config import get_settings
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import REF_PREFIX
from app.modules.autoapply.models import AutoApplyEvent
from app.modules.discovery.models import DiscoveredJob
from app.modules.execution.models import (
    ApplicationPause,
    AttemptEvent,
    Checkpoint,
    Evidence,
    ExecutionAttempt,
    OutboxMessage,
    RehearsalRecord,
)
from app.modules.inbox.models import InboxEvent
from app.modules.jobs.models import Job
from app.modules.preparation.models import ApplicationPackage, JobForm, PackageApproval

# The stages of the process, in order, as the console names them.
STAGES = ("discovery", "capture", "package", "approval", "rule", "state", "attempt",
          "pause", "email", "audit")  # fmt: skip

# What a package's answer shows here: what the review page shows, never its stored value.
_ANSWER_KEYS = ("key", "label", "status", "source", "display", "required", "sensitive",
                "explanation")  # fmt: skip


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _short(digest: str | None) -> str | None:
    return digest[:12] if digest else None


def _val(x):
    """An enum's value, else the thing itself."""
    return getattr(x, "value", x)


def _meta(meta: dict | None) -> dict:
    """An audit record's metadata (already free of personal values, audit/service.sanitize)
    without its keyed references: opaque digests, and never served here."""
    return {
        k: v
        for k, v in (meta or {}).items()
        if not k.endswith("_ref") and not (isinstance(v, str) and v.startswith(REF_PREFIX))
    }


# -- one application, start to finish -------------------------------------------------------


def _job(job: Job) -> dict:
    return {
        "id": str(job.id),
        "title": job.title,
        "employer": job.employer,
        "location": job.location,
        "url": job.url,
        "ats_provider": job.ats_provider,
        "source": _val(job.source),
        "status": _val(job.status),
        "exclusion_reason": job.exclusion_reason,
        "posted_on": job.posted_on.isoformat() if job.posted_on else None,
        "first_seen_at": _iso(job.first_seen_at),
        "last_seen_at": _iso(job.last_seen_at),
        "open_confirmed_at": _iso(job.open_confirmed_at),
        "distinct_confirmed_at": _iso(job.distinct_confirmed_at),
    }


def _discovery(db: Session, user_id, job_id) -> list[dict]:
    rows = db.scalars(
        select(DiscoveredJob)
        .where(DiscoveredJob.user_id == user_id, DiscoveredJob.job_id == job_id)
        .order_by(DiscoveredJob.first_seen_at)
    ).all()
    return [
        {
            "provider": r.provider,
            "source_job_id": r.source_job_id,
            "status": r.status,
            "link_basis": r.link_basis,
            "first_seen_at": _iso(r.first_seen_at),
            "last_seen_at": _iso(r.last_seen_at),
            "stale": r.stale,
            "stale_reason": r.stale_reason,
            "changed_fields": list(r.changed_fields or []),
            "changed_at": _iso(r.changed_at),
            "filter_result": r.filter_result,
        }
        for r in rows
    ]


def _capture(form: JobForm) -> dict:
    from app.modules.providers.routing import form_checkpoint

    schema = form.schema or {}
    fields = schema.get("fields") or []
    blocking = set(form_checkpoint(schema))  # required controls NoEfforts cannot fill
    return {
        "version": form.version,
        "captured_at": _iso(form.captured_at),
        "source": form.source,
        "extraction_version": form.extraction_version,
        "fingerprint": _short(form.fingerprint),
        "fields": len(fields),
        "required": sum(1 for f in fields if f.get("required")),
        # A required control NoEfforts cannot fill makes the form a checkpoint (apply on the
        # employer's site); an optional one is left empty.
        "checkpoints": [
            {"key": f.get("key"), "label": f.get("label"), "reason": f.get("unsupported_reason")}
            for f in fields
            if f.get("type") == "unsupported" and f.get("key") in blocking
        ],
        "left_empty": [
            {"key": f.get("key"), "label": f.get("label"), "reason": f.get("unsupported_reason")}
            for f in fields
            if f.get("type") == "unsupported" and f.get("key") not in blocking
        ],
        "sections": [
            {"kind": s.get("kind"), "step": s.get("step"), "required": bool(s.get("required"))}
            for s in schema.get("sections") or []
        ],
        "wizard_pages": list((schema.get("wizard") or {}).get("pages") or []),
    }


def _package(pkg: ApplicationPackage) -> dict:
    content = pkg.content or {}
    return {
        "version": pkg.version,
        "created_at": _iso(pkg.created_at),
        "content_hash": _short(pkg.content_hash),
        "change_summary": list(pkg.change_summary or []),
        "unresolved": list(content.get("unresolved") or []),
        "validation_errors": list(content.get("validation_errors") or []),
        "answers": [
            {k: a.get(k) for k in _ANSWER_KEYS if k in a}
            for a in content.get("answers") or []
            if isinstance(a, dict)
        ],
        "sections": [
            {"kind": s.get("kind"), "step": s.get("step"), "rows": len(s.get("rows") or [])}
            for s in content.get("sections") or []
            if isinstance(s, dict)
        ],
    }


def _approval(a: PackageApproval, versions: dict) -> dict:
    return {
        "id": str(a.id),
        "package_version": versions.get(a.package_id),
        "scope": _val(a.scope),
        "by_rule": a.by_rule,
        "content_hash": _short(a.content_hash),
        "adapter": a.adapter,
        "adapter_version": a.adapter_version,
        "approved_at": _iso(a.approved_at),
        "expires_at": _iso(a.expires_at),
        "invalidated_at": _iso(a.invalidated_at),
        "invalidation_reason": a.invalidation_reason,
    }


def _rule_event(e: AutoApplyEvent) -> dict:
    from app.modules.autoapply.service import REASONS

    return {"at": _iso(e.created_at), "action": e.action, "reason": e.reason,
            "words": REASONS.get(e.reason)}  # fmt: skip


def _state_event(e: ApplicationEvent) -> dict:
    # Never its evidence note: the owner's private note, kept off every other surface.
    return {
        "at": _iso(e.created_at),
        "kind": e.kind,
        "from_state": _val(e.from_state),
        "to_state": _val(e.to_state),
        "from_outcome": _val(e.from_outcome),
        "to_outcome": _val(e.to_outcome),
        "actor": _val(e.actor),
        "source": e.source,
        "reason": e.reason,
        "occurred_on": e.occurred_on.isoformat() if e.occurred_on else None,
    }


def _attempt(db: Session, a: ExecutionAttempt, versions: dict) -> dict:
    events = db.scalars(
        select(AttemptEvent)
        .where(AttemptEvent.attempt_id == a.id)
        .order_by(AttemptEvent.created_at)
    ).all()
    evidence = db.scalars(
        select(Evidence)
        .where(Evidence.attempt_id == a.id, Evidence.user_id == a.user_id)
        .order_by(Evidence.created_at)
    ).all()
    checkpoints = db.scalars(
        select(Checkpoint)
        .where(Checkpoint.attempt_id == a.id, Checkpoint.user_id == a.user_id)
        .order_by(Checkpoint.created_at)
    ).all()
    outbox = db.scalars(
        select(OutboxMessage)
        .where(OutboxMessage.attempt_id == a.id)
        .order_by(OutboxMessage.created_at)
    ).all()
    rehearsal = db.scalar(select(RehearsalRecord).where(RehearsalRecord.attempt_id == a.id))
    return {
        "id": str(a.id),
        "created_at": _iso(a.created_at),
        "state": a.state,
        "adapter": a.adapter,
        "package_version": versions.get(a.package_id),
        "package_hash": _short(a.package_hash),
        "approval_id": str(a.approval_id),
        "queued_by_rule": a.queued_by_rule,
        "destination_class": a.destination_class,
        "rehearsal_prerequisite": a.rehearsal_prerequisite,
        "generation": a.generation,
        "retry_count": a.retry_count,
        "cancel_requested": a.cancel_requested,
        "worker": a.lease_owner,
        "heartbeat_at": _iso(a.heartbeat_at),
        "disclosure_started_at": _iso(a.disclosure_started_at),
        "send_started_at": _iso(a.send_started_at),
        "finished_at": _iso(a.finished_at),
        "outcome_detail": a.outcome_detail,
        # Already free of codes, cookies and answer values (models.AttemptEvent, Evidence).
        "events": [
            {
                "at": _iso(e.created_at),
                "generation": e.generation,
                "kind": e.kind,
                "detail": e.detail,
            }
            for e in events
        ],  # fmt: skip
        "evidence": [
            {
                "at": _iso(v.created_at),
                "kind": v.kind,
                "strength": v.strength,
                "data": v.data,
                "retain_until": _iso(v.retain_until),
            }
            for v in evidence
        ],  # fmt: skip
        # Never the code itself (held only until the worker uses it).
        "checkpoints": [
            {
                "at": _iso(c.created_at),
                "kind": c.kind,
                "status": c.status,
                "round": c.round,
                "wrong_attempts": c.wrong_attempts,
                "max_attempts": c.max_attempts,
                "expires_at": _iso(c.expires_at),
            }
            for c in checkpoints
        ],  # fmt: skip
        "outbox": [
            {
                "at": _iso(m.created_at),
                "topic": m.topic,
                "dispatched_at": _iso(m.dispatched_at),
                "publish_attempts": m.publish_attempts,
                "last_error": m.last_error,
            }
            for m in outbox
        ],  # fmt: skip
        "rehearsal": None
        if rehearsal is None
        else {
            "destination_class": rehearsal.destination_class,
            "route": rehearsal.route,
            "adapter_version": rehearsal.adapter_version,
            "uploads_expected": rehearsal.uploads_expected,
            "uploads_acknowledged": rehearsal.uploads_acknowledged,
            "readback_mismatched": rehearsal.readback_mismatched,
            "recheck_matched": rehearsal.recheck_matched,
            "egress_proxy_denied": rehearsal.egress_proxy_denied,
        },
    }


def _pause(p: ApplicationPause) -> dict:
    return {
        "at": _iso(p.created_at),
        "kind": p.kind,
        "status": p.status,
        "resolution": p.resolution,
        "resolved_at": _iso(p.resolved_at),
        "package_version": p.package_version,
        "form_version": p.form_version,
        "recaptured_version": p.recaptured_version,
        "detail": p.detail,
    }


def _email(e: InboxEvent) -> dict:
    # Never its keyed message or thread reference.
    return {
        "at": _iso(e.received_at),
        "sender_domain": e.sender_domain,
        "kind": e.kind,
        "state": e.state,
        "match_band": e.match_band,
        "class_band": e.class_band,
        "match_basis": e.match_basis,
        "proposed_outcome": e.proposed_outcome,
        "applied_outcome": e.applied_outcome,
    }


def _timeline(trace: dict) -> list[dict]:
    """Every step of the trace in one list, oldest first: (when, stage, what)."""
    out: list[tuple[str, int, str, str]] = []

    def add(at, stage, what):
        if at:
            out.append((at, STAGES.index(stage), stage, what))

    for d in trace["discovery"]:
        add(d["first_seen_at"], "discovery", f"Found by {d['provider']} ({d['status']})")
    for c in trace["captures"]:
        n = len(c["checkpoints"])
        add(c["captured_at"], "capture", f"Form read, version {c['version']}: {c['fields']} "
            f"questions, {n} checkpoint{'' if n == 1 else 's'}")  # fmt: skip
    for p in trace["packages"]:
        n = len(p["unresolved"])
        add(p["created_at"], "package", f"Package version {p['version']} built "
            f"({p['content_hash']}): {n} waiting for you")  # fmt: skip
    for a in trace["approvals"]:
        who = "your standing rule" if a["by_rule"] else "you"
        add(a["approved_at"], "approval", f"Approved by {who} ({a['scope']}), package version "
            f"{a['package_version']}")  # fmt: skip
        add(a["invalidated_at"], "approval", f"Approval retired: {a['invalidation_reason']}")
    for r in trace["rule"]:
        add(r["at"], "rule", f"Standing rule: {r['action']} ({r['reason']})")
    for s in trace["state_changes"]:
        if s["to_state"]:
            add(s["at"], "state", f"{s['from_state'] or '—'} → {s['to_state']}"
                + (f": {s['reason']}" if s["reason"] else ""))  # fmt: skip
        elif s["to_outcome"]:
            add(s["at"], "state", f"Outcome: {s['from_outcome'] or '—'} → {s['to_outcome']}")
    for a in trace["attempts"]:
        kind = "rehearsal" if a["rehearsal"] else "attempt"
        add(a["created_at"], "attempt", f"Attempt queued ({a['adapter']})")
        for e in a["events"]:
            add(e["at"], "attempt", f"Attempt: {e['kind']}")
        add(a["disclosure_started_at"], "attempt", "Filling started on the employer's form")
        add(a["send_started_at"], "attempt", "Final click (send) started")
        add(a["finished_at"], "attempt", f"Attempt ended: {a['state']}"
            + (f" ({kind})" if a["rehearsal"] else "")
            + (f": {a['outcome_detail']}" if a["outcome_detail"] else ""))  # fmt: skip
        for c in a["checkpoints"]:
            add(c["at"], "attempt", f"Waited for a {c['kind']} ({c['status']})")
    for p in trace["pauses"]:
        add(p["at"], "pause", f"Paused: {p['kind']} ({p['status']})")
    for e in trace["emails"]:
        add(e["at"], "email", f"Email from {e['sender_domain']}: {e['kind']}")
    for e in trace["audit"]:
        add(e["at"], "audit", e["action"])
    out.sort(key=lambda t: (t[0], t[1]))
    return [{"at": at, "stage": stage, "what": what} for at, _, stage, what in out]


def trace(db: Session, user, app_id: uuid.UUID) -> dict | None:
    """One application, start to finish; None if it is not this account's."""
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        return None
    job = db.get(Job, app.job_id)
    if job is None or job.user_id != user.id:
        return None
    forms = db.scalars(
        select(JobForm).where(JobForm.job_id == job.id, JobForm.user_id == user.id)
        .order_by(JobForm.version)
    ).all()  # fmt: skip
    packages = db.scalars(
        select(ApplicationPackage)
        .where(ApplicationPackage.application_id == app.id, ApplicationPackage.user_id == user.id)
        .order_by(ApplicationPackage.version)
    ).all()
    versions = {p.id: p.version for p in packages}
    approvals = db.scalars(
        select(PackageApproval)
        .where(PackageApproval.application_id == app.id, PackageApproval.user_id == user.id)
        .order_by(PackageApproval.approved_at)
    ).all()
    rule = db.scalars(
        select(AutoApplyEvent)
        .where(
            AutoApplyEvent.user_id == user.id,
            or_(AutoApplyEvent.application_id == app.id, AutoApplyEvent.job_id == job.id),
        )
        .order_by(AutoApplyEvent.created_at)
    ).all()
    states = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.created_at)
    ).all()
    attempts = db.scalars(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.application_id == app.id, ExecutionAttempt.user_id == user.id)
        .order_by(ExecutionAttempt.created_at)
    ).all()
    pauses = db.scalars(
        select(ApplicationPause)
        .where(ApplicationPause.application_id == app.id, ApplicationPause.user_id == user.id)
        .order_by(ApplicationPause.created_at)
    ).all()
    emails = db.scalars(
        select(InboxEvent)
        .where(InboxEvent.application_id == app.id, InboxEvent.user_id == user.id)
        .order_by(InboxEvent.received_at)
    ).all()
    entity_ids = [str(app.id), str(job.id), *(str(a.id) for a in attempts)]
    audit = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == user.id, AuditEvent.entity_id.in_(entity_ids))
        .order_by(AuditEvent.created_at)
    ).all()
    out = {
        "application": {
            "id": str(app.id),
            "state": _val(app.state),
            "state_changed_at": _iso(app.state_changed_at),
            "outcome": _val(app.outcome),
        },
        "job": _job(job),
        "discovery": _discovery(db, user.id, job.id),
        "captures": [_capture(f) for f in forms],
        "packages": [_package(p) for p in packages],
        "approvals": [_approval(a, versions) for a in approvals],
        "rule": [_rule_event(e) for e in rule],
        "state_changes": [_state_event(e) for e in states],
        "attempts": [_attempt(db, a, versions) for a in attempts],
        "pauses": [_pause(p) for p in pauses],
        "emails": [_email(e) for e in emails],
        "audit": [
            {
                "at": _iso(e.created_at),
                "action": e.action,
                "entity_type": e.entity_type,
                "meta": _meta(e.meta),
            }
            for e in audit
        ],  # fmt: skip
    }
    out["timeline"] = _timeline(out)
    return out


# -- across the account's jobs --------------------------------------------------------------


def activity(db: Session, user, limit: int = 100) -> list[dict]:
    """What happened across this account's jobs, newest first: what the standing rule did,
    each state change, each attempt's start and end, each pause and each email read."""
    items: list[dict] = []

    def add(at, stage, what, app_id=None, job_id=None):
        if at:
            items.append({"at": _iso(at), "stage": stage, "what": what,
                          "application_id": str(app_id) if app_id else None,
                          "job_id": str(job_id) if job_id else None})  # fmt: skip

    titles = {
        j.id: j.title or j.employer or "a job"
        for j in db.scalars(select(Job).where(Job.user_id == user.id)).all()
    }
    apps = {
        a.id: a.job_id
        for a in db.scalars(select(Application).where(Application.user_id == user.id)).all()
    }
    for e in db.scalars(
        select(AutoApplyEvent).where(AutoApplyEvent.user_id == user.id)
        .order_by(AutoApplyEvent.created_at.desc()).limit(limit)
    ).all():  # fmt: skip
        add(e.created_at, "rule", f"Standing rule: {e.action} ({e.reason}) — "
            f"{titles.get(e.job_id, 'a job')}", e.application_id, e.job_id)  # fmt: skip
    if apps:
        for e in db.scalars(
            select(ApplicationEvent).where(ApplicationEvent.application_id.in_(list(apps)))
            .order_by(ApplicationEvent.created_at.desc()).limit(limit)
        ).all():  # fmt: skip
            job_id = apps.get(e.application_id)
            if e.to_state:
                what = f"{_val(e.from_state) or '—'} → {_val(e.to_state)}"
            else:
                what = f"Outcome: {_val(e.from_outcome) or '—'} → {_val(e.to_outcome)}"
            add(e.created_at, "state", f"{what} — {titles.get(job_id, 'a job')}",
                e.application_id, job_id)  # fmt: skip
    for a in db.scalars(
        select(ExecutionAttempt).where(ExecutionAttempt.user_id == user.id)
        .order_by(ExecutionAttempt.created_at.desc()).limit(limit)
    ).all():  # fmt: skip
        job_id = apps.get(a.application_id)
        title = titles.get(job_id, "a job")
        add(a.created_at, "attempt", f"Attempt queued ({a.adapter}) — {title}",
            a.application_id, job_id)  # fmt: skip
        add(a.finished_at, "attempt", f"Attempt ended: {a.state} — {title}",
            a.application_id, job_id)  # fmt: skip
    for p in db.scalars(
        select(ApplicationPause).where(ApplicationPause.user_id == user.id)
        .order_by(ApplicationPause.created_at.desc()).limit(limit)
    ).all():  # fmt: skip
        job_id = apps.get(p.application_id)
        add(p.created_at, "pause", f"Paused: {p.kind} — {titles.get(job_id, 'a job')}",
            p.application_id, job_id)  # fmt: skip
    for e in db.scalars(
        select(InboxEvent).where(InboxEvent.user_id == user.id)
        .order_by(InboxEvent.received_at.desc()).limit(limit)
    ).all():  # fmt: skip
        add(e.received_at, "email", f"Email from {e.sender_domain}: {e.kind}", e.application_id,
            apps.get(e.application_id))  # fmt: skip
    for d in db.scalars(
        select(DiscoveredJob).where(DiscoveredJob.user_id == user.id)
        .order_by(DiscoveredJob.first_seen_at.desc()).limit(limit)
    ).all():  # fmt: skip
        add(d.first_seen_at, "discovery", f"Found by {d.provider} ({d.status})", None, d.job_id)
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


# -- the server's switches, as they apply to this account ------------------------------------


def _feature(key, name, switch, on, why=None, needs=(), note=None) -> dict:
    return {"key": key, "name": name, "switch": switch, "on": bool(on),
            "ready": bool(on) and why is None and not needs, "why": why,
            "needs": list(needs), "note": note}  # fmt: skip


def system(db: Session, user) -> dict:
    """Every switch: whether it is on, whether it works for this account now, and if not, why
    or what it still needs. Never a secret's value: only whether one is set."""
    from app.modules.autoapply import service as rule
    from app.modules.autoapply.router import WHY as RULE_WHY
    from app.modules.connections import service as connections
    from app.modules.connections.router import WHY as GMAIL_WHY
    from app.modules.discovery.service import may_discover
    from app.modules.execution import live
    from app.modules.inbox import service as inbox
    from app.modules.inbox.router import WHY as INBOX_WHY
    from app.modules.mail.router import REASONS as MAIL_WHY
    from app.modules.mail.service import config_problem
    from app.modules.preparation import drafting_access

    s = get_settings()
    features = []
    freehire = "freehire" in s.discovery_providers
    features.append(_feature(
        "discovery", "Job search (Freehire)", "NOEFFORTS_DISCOVERY_PROVIDERS", freehire,
        None if may_discover(user.email) else "Live search is set up for the owner's account.",
        note="An optional key (NOEFFORTS_FREEHIRE_API_KEY) is "
        + ("set." if s.freehire_api_key else "not set; it works without one."),
    ))  # fmt: skip
    features.append(_feature(
        "job_boards", "Employer job boards (Greenhouse, Lever, Ashby)",
        "NOEFFORTS_BOARD_SOURCES_ENABLED", s.board_sources_enabled))  # fmt: skip
    why = live.refusal(user)
    features.append(_feature(
        "greenhouse_pilot", "Applying to real Greenhouse jobs (fill and submit)",
        "NOEFFORTS_LIVE_GREENHOUSE_ENABLED", s.live_greenhouse_enabled,
        live.WHY.get(why, why) if why else None))  # fmt: skip
    why = rule.owner_refusal(user)
    paused = rule.paused(db, user)
    features.append(_feature(
        "auto_apply", "Automatic applying (your standing rule)", "NOEFFORTS_AUTO_APPLY_ENABLED",
        s.auto_apply_enabled,
        (RULE_WHY.get(why, why) if why else None)
        or ("You paused it for this account (Account → Automatic applying)." if paused else None),
        note=f"At most {s.auto_apply_daily_cap} automatic approvals a day "
        "(NOEFFORTS_AUTO_APPLY_DAILY_CAP).",
    ))  # fmt: skip
    why = inbox.available_for(db, user)
    features.append(
        _feature(
            "inbox",
            "Reading your email (verification codes, application updates)",
            "NOEFFORTS_INBOX_ENABLED",
            s.inbox_enabled,
            INBOX_WHY.get(why, why) if why else None,
        )
    )
    why = connections.available()
    features.append(_feature(
        "gmail_connection", "Connecting Gmail from the app", "NOEFFORTS_INBOX_OAUTH_ENABLED",
        s.inbox_oauth_enabled, GMAIL_WHY.get(why, why) if why else None,
        needs=[n for n, ok in (
            ("NOEFFORTS_INBOX_OAUTH_CLIENT_ID", bool(s.inbox_oauth_client_id)),
            ("NOEFFORTS_INBOX_OAUTH_CLIENT_SECRET",
             bool(s.inbox_oauth_client_secret.get_secret_value())),
        ) if not ok and s.inbox_oauth_enabled]))  # fmt: skip
    drafting_on = s.drafting_provider == "anthropic"
    needs = [n for n, ok in (
        ("NOEFFORTS_ANTHROPIC_API_KEY", bool(s.anthropic_api_key.get_secret_value())),
        ("NOEFFORTS_DRAFTING_DAILY_BUDGET_USD above 0", s.drafting_daily_budget_usd > 0),
    ) if not ok] if drafting_on else []  # fmt: skip
    why = drafting_access.refusal(db, user, "anthropic") if drafting_on and not needs else None
    features.append(_feature(
        "ai_drafting", "AI drafting of long answers (Anthropic)", "NOEFFORTS_DRAFTING_PROVIDER",
        drafting_on, {"not_for_this_account": "AI drafting is set up for named accounts only.",
                      "consent_needed": "Agree to the AI drafting consent on a review page first.",
                      "budget_reached": "Today's AI drafting budget is used up."}.get(why, why),
        needs=needs, note="It spends money: only within the daily budget you set."))  # fmt: skip
    why = config_problem() if s.email_enabled else None
    features.append(_feature(
        "email_reminders", "Email reminders to you", "NOEFFORTS_EMAIL_ENABLED", s.email_enabled,
        MAIL_WHY.get(why, why) if why else None))  # fmt: skip
    features.append(_feature(
        "google_drive", "Google Drive import", "NOEFFORTS_GOOGLE_DRIVE_ENABLED",
        s.google_drive_enabled,
        needs=[n for n, ok in (
            ("NOEFFORTS_GOOGLE_DRIVE_CLIENT_ID", bool(s.google_drive_client_id)),
            ("NOEFFORTS_GOOGLE_DRIVE_API_KEY", bool(s.google_drive_api_key)),
        ) if not ok and s.google_drive_enabled]))  # fmt: skip
    for key, name in (("autofill", "Filling forms on the local stand-ins (Greenhouse, Lever, "
                       "Ashby and Workday style)"),
                      ("answers", "Saved answers and answer suggestions"),
                      ("extension", "Browser extension: save the current tab's job"),
                      ("api_tokens", "API tokens, CLI and MCP (read-only)"),
                      ("tracker", "Tracker, follow-ups and notifications")):  # fmt: skip
        features.append(_feature(key, name, None, True))
    latest_end = max((a.ends_on for a in authorizations.RECORDED if a.ends_on), default=None)
    today = date.today()  # as authorizations.covers reads it
    permissions = [
        {"what": a.what, "decision": a.decision, "given_on": a.given_on.isoformat(),
         "words": a.words, "actions": sorted(a.actions), "data": a.data,
         "ends_on": a.ends_on.isoformat() if a.ends_on else None,
         "active": a.ends_on is None or a.ends_on >= today}
        for a in authorizations.RECORDED
    ]  # fmt: skip
    warnings = []
    if s.sole_owner:
        warnings.append(
            "Sole-owner mode is on (NOEFFORTS_SOLE_OWNER): every account on this server is "
            "treated as you, the owner: every feature, and automatic applying on unless that "
            "account pauses it. Each account reads only a mailbox it connected itself (the "
            "server's own mailbox file stays the named owner's). Anyone who can open this "
            "server can sign up: keep it private (the shipped Compose file binds to 127.0.0.1) "
            "or turn sole-owner mode off before anyone else can reach it."
        )
    if not any(p["active"] for p in permissions):
        warnings.append(
            "No recorded permission is active"
            + (f" (the last ended on {latest_end.isoformat()})" if latest_end else "")
            + ": nothing is read, opened, filled or submitted on a real employer's site, and no "
            "real mailbox is read, until you record a new one with its steps, end date and limit."
        )
    return {
        "account": {
            "email": user.email,
            "owner": owner(user.email),
            "sole_owner": s.sole_owner,
            "all_accounts": s.all_accounts,
        },  # fmt: skip
        "environment": {"env": s.env, "browser_isolation": s.browser_isolation},
        "warnings": warnings,
        "features": features,
        "permissions": permissions,
        "safety": [
            "Nothing is submitted without your approval of the exact package, or your standing "
            "rule's within its limits (every answer from your approved facts and answers).",
            "The first application to each employer is a rehearsal: it fills and checks, and "
            "never submits.",
            f"At most {s.auto_apply_daily_cap} automatic approvals a day.",
            "Real employer sites also need your recorded permission for each step (read, open, "
            "fill, submit), with its end date and attempt limit.",
            "A CAPTCHA or an MFA prompt stops the run for you: NoEfforts never solves or "
            "bypasses one. A verification code is entered from your own mailbox only when your "
            "recorded permission covers it; otherwise the run waits for you to type it.",
            "An unknown result after the final click is never retried: it waits in Submitted, "
            "unconfirmed.",
            "Each account sees only its own records.",
        ],
    }
