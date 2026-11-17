"""D168: the owner's console. The whole automatic application process, start to finish, for one
application (`trace`), what happened across the account's jobs (`activity`), and the server's
switches as they apply to the signed-in account (`system`).

It only reads what NoEfforts already keeps, every query scoped to the signed-in account (another
account's application is a 404, as everywhere). It stores nothing and changes nothing: no switch
is turned and no step is run from here. It never returns a secret. A verification code (a
checkpoint's `code`), a token, key or password is never read out, only whether one is set. A keyed
reference (an attempt's path, an email's message or thread, the audit log's `ref:v2:`) is never
served, and every stored JSON value passes the data export's own scrubbing (`export._scrub`).
There is no screenshot, trace or raw page to show: execution keeps none (CLAUDE.md), and capture
keeps only the form's schema. What only the server's owner may read (the recorded permissions,
which settings are missing, how the server runs) is shown to the owner's account alone
(`accounts.owner`; every account in sole-owner mode).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import authorizations
from app.core.accounts import owner
from app.core.config import get_settings
from app.core.db import utcnow
from app.modules.account.export import _scrub as scrub
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import REF_PREFIX
from app.modules.autoapply.models import AutoApplyEvent, AutoApplyPrefs
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
from app.modules.inbox.models import InboxConsent, InboxEvent, InboxSettings
from app.modules.jobs.models import Job
from app.modules.preparation.models import (
    AnswerDraft,
    ApplicationPackage,
    JobForm,
    PackageApproval,
)

# The stages of the process, in order, as the console names them.
STAGES = ("discovery", "capture", "package", "draft", "approval", "rule", "state", "attempt",
          "pause", "email", "audit")  # fmt: skip

# What a package's answer shows here: what the review page shows, never its stored value.
_ANSWER_KEYS = ("key", "label", "status", "source", "display", "required", "sensitive",
                "explanation")  # fmt: skip
_DESTINATION_KEYS = ("origin", "submit_url", "submit_method", "ats_provider", "form_version",
                     "form_source")  # fmt: skip
_DOCUMENT_KEYS = ("field", "display", "version", "content_type", "size_bytes", "origin")
# One board or Freehire import (up to 250 postings) must not fill the activity list.
DISCOVERY_SHOWN = 25
REHEARSAL_SCOPE = "disclose_only"


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
        for k, v in (scrub(meta) or {}).items()
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
            "filter_result": scrub(r.filter_result),
        }
        for r in rows
    ]


def _capture(form: JobForm) -> dict:
    from app.modules.providers.routing import form_checkpoint

    schema = form.schema or {}
    fields = schema.get("fields") or []
    blocking = set(form_checkpoint(schema))  # required controls NoEfforts cannot fill

    def item(f, reason=None):
        return {"key": f.get("key"), "label": f.get("label"),
                "reason": reason or f.get("unsupported_reason")}  # fmt: skip

    unsupported = [f for f in fields if f.get("type") == "unsupported"]
    located = [f for f in unsupported if f.get("widget") == "location_structured"]
    return {
        "version": form.version,
        "captured_at": _iso(form.captured_at),
        "source": form.source,
        "extraction_version": form.extraction_version,
        "fingerprint": _short(form.fingerprint),
        "fields": len(fields),
        "required": sum(1 for f in fields if f.get("required")),
        # A required control NoEfforts cannot fill makes the form a checkpoint (apply on the
        # employer's site). A value a location search sets is the page's: checked after the
        # search, never filled (D104). Any other control NoEfforts does not operate is optional
        # and left empty, as is an optional phone whose second control cannot be set (D130).
        "checkpoints": [item(f) for f in unsupported if f.get("key") in blocking],
        "set_by_the_page": [item(f) for f in located],
        "left_empty": [
            item(f) for f in unsupported if f.get("key") not in blocking and f not in located
        ]
        + [
            item(f, "an optional phone left blank: its second control cannot be set (D130)")
            for f in fields
            if f.get("widget") == "phone_left_blank"
        ],
        "sections": [
            {"kind": s.get("kind"), "step": s.get("step"), "required": bool(s.get("required"))}
            for s in schema.get("sections") or []
        ],
        "wizard_pages": list((schema.get("wizard") or {}).get("pages") or []),
    }


def _package(pkg: ApplicationPackage) -> dict:
    content = pkg.content or {}
    dest = content.get("destination") or {}
    return {
        "version": pkg.version,
        "created_at": _iso(pkg.created_at),
        "content_hash": _short(pkg.content_hash),
        "change_summary": list(pkg.change_summary or []),
        "unresolved": list(content.get("unresolved") or []),
        "validation_errors": scrub(list(content.get("validation_errors") or [])),
        "destination": {k: dest.get(k) for k in _DESTINATION_KEYS},
        "documents": [
            {k: d.get(k) for k in _DOCUMENT_KEYS}
            for d in content.get("documents") or []
            if isinstance(d, dict)
        ],
        "consents": scrub(dict(content.get("consents") or {})),
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


def _draft(d: AnswerDraft) -> dict:
    # Never its text: what was drafted is on the review page, where it is accepted or not.
    return {"at": _iso(d.created_at), "provider": d.provider, "model": d.model,
            "status": _val(d.status)}  # fmt: skip


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
    # Not its evidence note: the owner's private note (the application's own page shows it).
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


def _attempt(db: Session, a: ExecutionAttempt, versions: dict, scopes: dict) -> dict:
    from app.modules.execution import rehearsal as rehearsals

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
    rec = db.scalar(
        select(RehearsalRecord).where(
            RehearsalRecord.attempt_id == a.id, RehearsalRecord.user_id == a.user_id
        )
    )
    return {
        "id": str(a.id),
        "created_at": _iso(a.created_at),
        "state": a.state,
        "adapter": a.adapter,
        # What its approval allowed: a rehearsal fills and checks, never submits (whatever came
        # of it; only one that held leaves a rehearsal record).
        "rehearsal": scopes.get(a.approval_id) == REHEARSAL_SCOPE,
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
                "detail": scrub(e.detail),
            }
            for e in events
        ],  # fmt: skip
        "evidence": [
            {
                "at": _iso(v.created_at),
                "kind": v.kind,
                "strength": v.strength,
                "data": scrub(v.data),
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
        "rehearsal_record": None
        if rec is None
        else {
            "recorded_at": _iso(rec.recorded_at),
            "destination_class": rec.destination_class,
            "route": rec.route,
            "adapter_version": rec.adapter_version,
            "uploads_expected": rec.uploads_expected,
            "uploads_acknowledged": rec.uploads_acknowledged,
            "readback_mismatched": rec.readback_mismatched,
            "recheck_matched": rec.recheck_matched,
            "egress_proxy_denied": rec.egress_proxy_denied,
            # Whether it still holds, as the review page's attempts view says (D62's checks).
            "status": rehearsals.record_status(db, a)["status"],
            "revoked_at": _iso(rec.revoked_at),
            "revoked_reason": rec.revoked_reason,
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
        "detail": scrub(p.detail),
    }


def _email(e: InboxEvent) -> dict:
    # Never its keyed message or thread reference, never its text.
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


def _timeline(trace: dict, now: datetime) -> list[dict]:
    """Every step of the trace in one list, oldest first by the moment it happened (never by
    the text of its time: offsets may differ), then by stage."""
    out: list[tuple[datetime, int, str, str]] = []

    def add(at, stage, what):
        if at:
            out.append((datetime.fromisoformat(at), STAGES.index(stage), stage, what))

    job = trace["job"]
    add(job["first_seen_at"], "discovery", f"Job added ({job['source']})")
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
    for d in trace["drafts"]:
        add(d["at"], "draft", f"AI draft ({d['provider']}): {d['status']}")
    for a in trace["approvals"]:
        who = "your standing rule" if a["by_rule"] else "you"
        add(a["approved_at"], "approval", f"Approved by {who} ({a['scope']}), package version "
            f"{a['package_version']}")  # fmt: skip
        add(a["invalidated_at"], "approval", f"Approval retired: {a['invalidation_reason']}")
        expires = a["expires_at"]
        if expires and not a["invalidated_at"] and datetime.fromisoformat(expires) <= now:
            add(expires, "approval", "Approval expired")
    for r in trace["rule"]:
        add(r["at"], "rule", f"Standing rule: {r['action']} ({r['reason']})")
    for s in trace["state_changes"]:
        if s["to_state"]:
            add(s["at"], "state", f"{s['from_state'] or '—'} → {s['to_state']}"
                + (f": {s['reason']}" if s["reason"] else ""))  # fmt: skip
        elif s["to_outcome"]:
            add(s["at"], "state", f"Outcome: {s['from_outcome'] or '—'} → {s['to_outcome']}")
    for a in trace["attempts"]:
        kind = "Rehearsal" if a["rehearsal"] else "Attempt"
        add(a["created_at"], "attempt", f"{kind} queued ({a['adapter']})")
        for e in a["events"]:
            add(e["at"], "attempt", f"{kind}: {e['kind']}")
        add(a["disclosure_started_at"], "attempt", "Filling started on the employer's form")
        add(a["send_started_at"], "attempt", "Final click (send) started")
        add(a["finished_at"], "attempt", f"{kind} ended: {a['state']}"
            + (f": {a['outcome_detail']}" if a["outcome_detail"] else ""))  # fmt: skip
        for c in a["checkpoints"]:
            add(c["at"], "attempt", f"Waited for a {c['kind']} ({c['status']})")
        rec = a["rehearsal_record"]
        if rec and rec["revoked_at"]:
            add(
                rec["revoked_at"],
                "attempt",
                f"Rehearsal record withdrawn ({rec['revoked_reason']})",
            )
    for p in trace["pauses"]:
        add(p["at"], "pause", f"Paused: {p['kind']} ({p['status']})")
        add(p["resolved_at"], "pause", f"Pause ended: {p['resolution']}")
    for e in trace["emails"]:
        add(e["at"], "email", f"Email from {e['sender_domain']}: {e['kind']}")
    for e in trace["audit"]:
        add(e["at"], "audit", e["action"])
    out.sort(key=lambda t: (t[0], t[1]))
    return [{"at": at.isoformat(), "stage": stage, "what": what} for at, _, stage, what in out]


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
    scopes = {a.id: _val(a.scope) for a in approvals}
    drafts = db.scalars(
        select(AnswerDraft)
        .where(AnswerDraft.application_id == app.id, AnswerDraft.user_id == user.id)
        .order_by(AnswerDraft.created_at)
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
        "drafts": [_draft(d) for d in drafts],
        "approvals": [_approval(a, versions) for a in approvals],
        "rule": [_rule_event(e) for e in rule],
        "state_changes": [_state_event(e) for e in states],
        "attempts": [_attempt(db, a, versions, scopes) for a in attempts],
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
    out["timeline"] = _timeline(out, utcnow())
    return out


# -- across the account's jobs --------------------------------------------------------------


def activity(db: Session, user, limit: int = 100) -> list[dict]:
    """What happened across this account's jobs, newest first: the newest `limit` steps of every
    kind (at most DISCOVERY_SHOWN postings found), each named by its job, with its application
    where it has one. Reads only the columns it shows, and job titles only for those steps."""
    rows: list[tuple[datetime, str, str, object, object]] = []  # (when, stage, what, app, job)

    def add(at, stage, what, app_id=None, job_id=None):
        if at:
            rows.append((at, stage, what, app_id, job_id))

    mine = (Application.user_id == user.id,)
    for at, action, reason, app_id, job_id in db.execute(
        select(AutoApplyEvent.created_at, AutoApplyEvent.action, AutoApplyEvent.reason,
               AutoApplyEvent.application_id, AutoApplyEvent.job_id)
        .where(AutoApplyEvent.user_id == user.id)
        .order_by(AutoApplyEvent.created_at.desc()).limit(limit)
    ):  # fmt: skip
        add(at, "rule", f"Standing rule: {action} ({reason})", app_id, job_id)
    for e, job_id in db.execute(
        select(ApplicationEvent, Application.job_id)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(*mine).order_by(ApplicationEvent.created_at.desc()).limit(limit)
    ):  # fmt: skip
        if e.to_state:
            what = f"{_val(e.from_state) or '—'} → {_val(e.to_state)}"
        elif e.to_outcome:
            what = f"Outcome: {_val(e.from_outcome) or '—'} → {_val(e.to_outcome)}"
        else:
            continue  # a note that changes neither
        add(e.created_at, "state", what, e.application_id, job_id)
    for at, version, job_id in db.execute(
        select(JobForm.captured_at, JobForm.version, JobForm.job_id)
        .where(JobForm.user_id == user.id).order_by(JobForm.captured_at.desc()).limit(limit)
    ):  # fmt: skip
        add(at, "capture", f"Form read, version {version}", None, job_id)
    for at, scope, by_rule, app_id in db.execute(
        select(PackageApproval.approved_at, PackageApproval.scope, PackageApproval.by_rule,
               PackageApproval.application_id)
        .where(PackageApproval.user_id == user.id)
        .order_by(PackageApproval.approved_at.desc()).limit(limit)
    ):  # fmt: skip
        who = "your standing rule" if by_rule else "you"
        add(at, "approval", f"Approved by {who} ({_val(scope)})", app_id)
    attempts = (
        select(ExecutionAttempt.created_at, ExecutionAttempt.finished_at, ExecutionAttempt.state,
               ExecutionAttempt.adapter, ExecutionAttempt.application_id, Application.job_id,
               PackageApproval.scope)
        .join(Application, Application.id == ExecutionAttempt.application_id)
        .outerjoin(PackageApproval, PackageApproval.id == ExecutionAttempt.approval_id)
        .where(ExecutionAttempt.user_id == user.id, *mine)
    )  # fmt: skip
    for created, _, _, adapter, app_id, job_id, scope in db.execute(
        attempts.order_by(ExecutionAttempt.created_at.desc()).limit(limit)
    ):
        kind = "Rehearsal" if _val(scope) == REHEARSAL_SCOPE else "Attempt"
        add(created, "attempt", f"{kind} queued ({adapter})", app_id, job_id)
    for _, finished, state, _, app_id, job_id, scope in db.execute(
        attempts.where(ExecutionAttempt.finished_at.is_not(None))
        .order_by(ExecutionAttempt.finished_at.desc()).limit(limit)
    ):  # fmt: skip
        kind = "Rehearsal" if _val(scope) == REHEARSAL_SCOPE else "Attempt"
        add(finished, "attempt", f"{kind} ended: {state}", app_id, job_id)
    for at, kind, app_id, job_id in db.execute(
        select(ApplicationPause.created_at, ApplicationPause.kind, ApplicationPause.application_id,
               Application.job_id)
        .join(Application, Application.id == ApplicationPause.application_id)
        .where(ApplicationPause.user_id == user.id, *mine)
        .order_by(ApplicationPause.created_at.desc()).limit(limit)
    ):  # fmt: skip
        add(at, "pause", f"Paused: {kind}", app_id, job_id)
    for at, domain, kind, app_id, job_id in db.execute(
        select(InboxEvent.received_at, InboxEvent.sender_domain, InboxEvent.kind,
               InboxEvent.application_id, Application.job_id)
        .outerjoin(Application, (Application.id == InboxEvent.application_id)
                   & (Application.user_id == user.id))
        .where(InboxEvent.user_id == user.id)
        .order_by(InboxEvent.received_at.desc()).limit(limit)
    ):  # fmt: skip
        add(at, "email", f"Email from {domain}: {kind}", app_id, job_id)
    for at, provider, status, app_id in db.execute(
        select(AnswerDraft.created_at, AnswerDraft.provider, AnswerDraft.status,
               AnswerDraft.application_id)
        .where(AnswerDraft.user_id == user.id)
        .order_by(AnswerDraft.created_at.desc()).limit(limit)
    ):  # fmt: skip
        add(at, "draft", f"AI draft ({provider}): {_val(status)}", app_id)
    for at, provider, status, job_id in db.execute(
        select(DiscoveredJob.first_seen_at, DiscoveredJob.provider, DiscoveredJob.status,
               DiscoveredJob.job_id)
        .where(DiscoveredJob.user_id == user.id)
        .order_by(DiscoveredJob.first_seen_at.desc()).limit(min(limit, DISCOVERY_SHOWN))
    ):  # fmt: skip
        add(at, "discovery", f"Found by {provider} ({status})", None, job_id)
    rows.sort(key=lambda r: r[0], reverse=True)
    rows = rows[:limit]
    app_ids = {r[3] for r in rows if r[3]}
    job_ids = {r[4] for r in rows if r[4]}
    pairs = (
        db.execute(
            select(Application.id, Application.job_id).where(
                *mine, or_(Application.id.in_(app_ids), Application.job_id.in_(job_ids))
            )
        ).all()
        if app_ids or job_ids
        else []
    )
    job_of = {a: j for a, j in pairs}
    app_of = {j: a for a, j in pairs}
    job_ids |= set(job_of.values())
    titles = (
        {
            j: title or employer or "a job"
            for j, title, employer in db.execute(
                select(Job.id, Job.title, Job.employer).where(
                    Job.user_id == user.id, Job.id.in_(job_ids)
                )
            )
        }
        if job_ids
        else {}
    )
    items = []
    for at, stage, what, app_id, job_id in rows:
        job_id = job_id or job_of.get(app_id)
        app_id = app_id or app_of.get(job_id)
        items.append({
            "at": _iso(at), "stage": stage,
            "what": f"{what} — {titles[job_id]}" if job_id in titles else what,
            "application_id": str(app_id) if app_id else None,
            "job_id": str(job_id) if job_id else None,
        })  # fmt: skip
    return items


# -- the server's switches, as they apply to this account ------------------------------------

HELD = ("This database was restored from a backup and is held: nothing is approved, queued or "
        "started until the scheduler resolves the restore (D147).")  # fmt: skip
NOT_SET_UP = "Not set up on this server yet."


def _feature(key, name, switch, on, why=None, needs=(), note=None) -> dict:
    return {"key": key, "name": name, "switch": switch, "on": bool(on),
            "ready": bool(on) and why is None and not needs, "why": why,
            "needs": list(needs), "note": note}  # fmt: skip


def _permission(db: Session, a, today: date) -> dict:
    """A recorded permission as `authorizations.covers` reads it today, and, where it sets an
    attempt limit, how much of it the pilot's attempts have used (every account's: D112)."""
    from app.modules.execution import live

    if a.given_on > today:
        state = "not_started"
    elif a.ends_on is not None and today > a.ends_on:
        state = "ended"
    else:
        state = "active"
    used = None
    if a.max_attempts is not None and a.what == authorizations.GREENHOUSE_PILOT:
        used = live.attempts_used(db, a.given_on)
    return {"what": a.what, "decision": a.decision, "given_on": a.given_on.isoformat(),
            "words": a.words, "actions": sorted(a.actions), "data": a.data,
            "ends_on": a.ends_on.isoformat() if a.ends_on else None, "state": state,
            "active": state == "active", "max_attempts": a.max_attempts,
            "attempts_used": used}  # fmt: skip


def _consents(db: Session, user) -> list[dict]:
    """The account's own consents in the app (reading its application emails, D127): its words,
    when given, its end, whether it is in force; the newest ten."""
    today = utcnow().date()  # as inbox._active_consent reads it
    rows = db.scalars(
        select(InboxConsent).where(InboxConsent.user_id == user.id)
        .order_by(InboxConsent.granted_at.desc()).limit(10)
    ).all()  # fmt: skip
    return [
        {"action": c.action, "words": c.attestation, "granted_at": _iso(c.granted_at),
         "ends_on": c.ends_on.isoformat() if c.ends_on else None,
         "revoked_at": _iso(c.revoked_at),
         "active": c.revoked_at is None and (c.ends_on is None or today <= c.ends_on)}
        for c in rows
    ]  # fmt: skip


def system(db: Session, user) -> dict:
    """Every switch: whether it is on, whether it works for this account now, and if not, why
    or what it still needs, each judged by the gate that decides it. Never a secret's value:
    only whether one is set, and that only to the server's owner."""
    from app.modules.autoapply import service as rule
    from app.modules.autoapply.router import WHY as RULE_WHY
    from app.modules.connections import service as connections
    from app.modules.connections.router import WHY as GMAIL_WHY
    from app.modules.discovery.service import may_discover
    from app.modules.execution import live, restore
    from app.modules.inbox import service as inbox
    from app.modules.inbox.router import ERRORS as INBOX_ERRORS
    from app.modules.inbox.router import WHY as INBOX_WHY
    from app.modules.mail.router import REASONS as MAIL_WHY
    from app.modules.mail.service import config_problem
    from app.modules.preparation import drafting

    s = get_settings()
    is_owner = owner(user.email)
    held = restore.held(db)
    today = date.today()  # as authorizations.covers reads it
    cap = authorizations.limit(authorizations.GREENHOUSE_PILOT, "disclose", today)
    used = live.attempts_used(db, cap[1]) if cap else None
    spent = (f"The recorded permission's attempt limit is used: {used} of {cap[0]}."
             if cap and used >= cap[0] else None)  # fmt: skip
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
    pilot_note = None
    if why is None and live.permission_refusal(("submit",)) is not None:
        pilot_note = ("Your recorded permission covers rehearsals (filling and checking), not "
                      "the final submit.")  # fmt: skip
    features.append(_feature(
        "greenhouse_pilot", "Applying to real Greenhouse jobs (fill and submit)",
        "NOEFFORTS_LIVE_GREENHOUSE_ENABLED", s.live_greenhouse_enabled,
        (live.WHY.get(why, why) if why else None) or spent or (HELD if held else None),
        note=pilot_note))  # fmt: skip
    why = rule.owner_refusal(user)
    chosen = db.get(AutoApplyPrefs, user.id) is not None
    off = None
    if rule.paused(db, user) and chosen:
        off = "You paused it for this account (Account → Automatic applying)."
    elif rule.paused(db, user):
        off = "Off for this account until you turn it on (Account → Automatic applying)."
    every = " across every account (sole-owner mode)" if s.sole_owner else " for this account"
    features.append(_feature(
        "auto_apply", "Automatic applying (your standing rule)", "NOEFFORTS_AUTO_APPLY_ENABLED",
        s.auto_apply_enabled,
        (RULE_WHY.get(why, why) if why else None) or off or spent or (HELD if held else None),
        note=f"At most {s.auto_apply_daily_cap} automatic approvals a day{every} "
        f"(NOEFFORTS_AUTO_APPLY_DAILY_CAP); {rule.cap_used(db, user.id)} today.",
    ))  # fmt: skip
    why = inbox.available_for(db, user)
    if why == "not_connected" and s.sole_owner and not inbox.named_inbox_owner(user):
        mail_why = ("Connect your own Gmail first (Account → Connections): each account reads "
                    "only a mailbox it connected itself.")  # fmt: skip
    else:
        mail_why = INBOX_WHY.get(why, why) if why else None
    if mail_why is None:
        st = db.get(InboxSettings, user.id)
        if st is not None and st.last_error in ("revoked", "token_unreadable"):
            mail_why = INBOX_ERRORS[st.last_error]
        elif st is None or not (st.codes_enabled or st.tracking_enabled):
            mail_why = ("Both are off for this account: turn on verification codes or "
                        "application emails (Account).")  # fmt: skip
    features.append(_feature(
        "inbox", "Reading your email (verification codes, application updates)",
        "NOEFFORTS_INBOX_ENABLED", s.inbox_enabled, mail_why,
        note="Codes: " + ("permitted" if inbox.codes_authorized() else
                          "not permitted (no recorded permission)")
        + "; application emails: " + ("permitted" if inbox.may_read_applications(db, user) else
                                      "not permitted (no recorded permission or consent)") + ".",
    ))  # fmt: skip
    why = connections.available()
    gmail_why = (GMAIL_WHY.get(why, why) if why else
                 None if inbox.is_inbox_owner(user) else GMAIL_WHY["not_owner"])  # fmt: skip
    features.append(_feature(
        "gmail_connection", "Connecting Gmail from the app", "NOEFFORTS_INBOX_OAUTH_ENABLED",
        s.inbox_oauth_enabled, gmail_why,
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
    status = drafting.provider_for(db, user)[1] if drafting_on and not needs else "available"
    features.append(_feature(
        "ai_drafting", "AI drafting of long answers (Anthropic)", "NOEFFORTS_DRAFTING_PROVIDER",
        drafting_on, {"available": None,
                      "not_configured": "The model in NOEFFORTS_DRAFTING_MODEL is not one "
                      "NoEfforts can price, so none is used.",
                      "not_for_this_account": "AI drafting is set up for named accounts only.",
                      "consent_needed": "Agree to the AI drafting consent on a review page first.",
                      "budget_reached": "Today's AI drafting budget is used up."}.get(
                          status, status),
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
    features.append(_feature(
        "autofill", "Filling forms on the local stand-ins (Greenhouse, Lever, Ashby and Workday "
        "style)", None, True,
        None if s.env == "test" else "Only in the test environment: the local stand-ins are "
        "refused everywhere else (real Greenhouse jobs go through the pilot above)."))  # fmt: skip
    for key, name in (("answers", "Saved answers and answer suggestions"),
                      ("extension", "Browser extension: save the current tab's job"),
                      ("api_tokens", "API tokens, CLI and MCP (read-only)"),
                      ("tracker", "Tracker, follow-ups and notifications")):  # fmt: skip
        features.append(_feature(key, name, None, True))
    if not is_owner:  # which settings the server lacks is its owner's business
        for f in features:
            if f["needs"]:
                f["why"], f["needs"] = f["why"] or NOT_SET_UP, []
    warnings = []
    if s.sole_owner:
        warnings.append(
            "Sole-owner mode is on (NOEFFORTS_SOLE_OWNER): every account on this server is "
            "treated as you, the owner: every feature, and automatic applying on unless that "
            "account pauses it, with one daily cap for all of them. Each account reads only a "
            "mailbox it connected itself (the server's own mailbox file stays the named "
            "owner's). Anyone who can open this server can sign up: keep it private (the "
            "shipped Compose file binds to 127.0.0.1) or turn sole-owner mode off before anyone "
            "else can reach it."
        )
    if held:
        warnings.append(HELD)
    if live.permission_refusal(live.TO_APPLY) is not None:
        ended = [a.ends_on for a in authorizations.RECORDED if a.ends_on and a.ends_on < today]
        last = f" (the last ended on {max(ended).isoformat()})" if ended and is_owner else ""
        warnings.append(
            f"No recorded permission covers a real employer's site{last}: nothing is read, "
            "opened, filled or submitted there until you record one in your own words, with its "
            "steps, end date and attempt limit."
        )
    if not (inbox.codes_authorized() or inbox.may_read_applications(db, user)):
        warnings.append(
            "Nothing permits reading a real mailbox (no recorded permission, and no consent of "
            "yours in the app): none is read."
        )
    return {
        "account": {
            "email": user.email,
            "owner": is_owner,
            "sole_owner": s.sole_owner,
            "all_accounts": s.all_accounts,
        },  # fmt: skip
        "environment": (
            {"env": s.env, "browser_isolation": s.browser_isolation} if is_owner else None
        ),
        "warnings": warnings,
        "features": features,
        "permissions": (
            [_permission(db, a, today) for a in authorizations.RECORDED] if is_owner else []
        ),
        "consents": _consents(db, user),
        "safety": [
            "Nothing is submitted without your approval of the exact package, or your standing "
            "rule's within its limits (every answer from your approved facts and answers).",
            "On a real employer's site the first application to each employer is a rehearsal: "
            "it fills and checks, and never submits.",
            f"At most {s.auto_apply_daily_cap} automatic approvals a day{every}.",
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
