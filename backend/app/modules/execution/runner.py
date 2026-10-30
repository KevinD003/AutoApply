"""Run one execution attempt end to end. Called by the Celery task (or the CLI in tests).

Phases and what a failure in each one means:
  before disclosure  -> failed_safe   (nothing left NoEfforts; may be retried by the sweeper)
  after disclosure   -> abandoned     (data entered/uploaded, not submitted; user decides)
  after send gate    -> unknown       (may have been accepted; reconcile, never auto-retry)
A rehearsal (an approval to disclose only) succeeds as `rehearsed` once the checks after
filling pass, before the send gate: data entered/uploaded, nothing submitted.
"""

import hashlib
import logging
import time
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.urlsafety import destination_category, is_fixture_origin
from app.modules.documents.models import Document
from app.modules.documents.storage import get_storage
from app.modules.execution import policy, rehearsal
from app.modules.execution import service as svc
from app.modules.execution.adapters.fake_api import FakeApiAdapter
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter, UploadFailed
from app.modules.execution.adapters.greenhouse import GreenhouseHostedAdapter
from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter
from app.modules.execution.adapters.lever import LeverFixtureAdapter
from app.modules.execution.browser import IsolationUnavailable, browser_session
from app.modules.execution.faults import fault
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import package as pk
from app.modules.preparation import sending
from app.modules.preparation.models import ApplicationPackage, ApprovalScope, PackageApproval

# API providers (providers.registry kind "api"): no browser; same attempt, lease and gates.
API_ADAPTERS = {"fake_api": FakeApiAdapter}
# Keyed by the adapter recorded on the attempt when it was queued (policy.adapter_for).
ADAPTERS = {
    "fixture_ats": FixtureAtsAdapter,
    "greenhouse_hosted": GreenhouseHostedAdapter,
    "greenhouse_dom": GreenhouseDomAdapter,
    "fixture_lever": LeverFixtureAdapter,
}

log = logging.getLogger("noefforts.execution")


def _snapshot(attempt_id):
    """Everything the browser needs comes from the immutable approved package, never from
    live profile data, so what is sent is what was approved."""
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, attempt_id)
        pkg = db.get(ApplicationPackage, att.package_id)
        content = pkg.content
        docs = {}
        for d in content["documents"]:
            doc = db.scalar(
                select(Document).where(
                    Document.id == uuid.UUID(d["document_id"]), Document.user_id == att.user_id
                )
            )
            data = get_storage().get(doc.storage_key)
            if hashlib.sha256(data).hexdigest() != d["sha256"]:
                raise RuntimeError("stored document does not match the approved digest")
            docs[d["field"]] = (doc.original_filename, doc.content_type, data)
        return content, docs, att.adapter


def _content_refusal(attempt_id, content: dict) -> str | None:
    """Why the stored package may not be sent, or None. Checked before any adapter code runs,
    on both routes: what is filled is exactly what was approved, and only its resolved answers
    (sending.py). The gates then check the package against current data under lock."""
    with SessionLocal() as db:
        approved = db.get(ExecutionAttempt, attempt_id).package_hash
    if pk.content_hash(content) != approved:
        return "the stored package does not match the approved one"
    if sending.unsendable(content):
        return "the approved package has an answer that is not resolved"
    return None


def _binding_refusal(attempt_id) -> str | None:
    """Why this attempt may not run with its recorded adapter now, or None. Checked before any
    adapter code touches a page; the gates re-check it under lock."""
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, attempt_id)
        appr = db.get(PackageApproval, att.approval_id)
        dest = db.get(ApplicationPackage, att.package_id).content["destination"]
        try:
            policy.check_binding(appr, dest, att.adapter)
        except policy.BindingChanged:
            return "the execution method changed after approval"
        except policy.UnsupportedDestination as e:
            return str(e)
        return None


def _rehearsal(attempt_id) -> bool:
    """True unless the attempt's approval permits submitting. A rehearsal (an approval to
    disclose only) stops after filling and checking, before the send gate; the gate refuses
    it as well (service.gate_before_send)."""
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, attempt_id)
        return db.get(PackageApproval, att.approval_id).scope != ApprovalScope.submit


def run_attempt(attempt_id: str, worker: str) -> str:
    aid = uuid.UUID(attempt_id)
    gen = svc.claim(aid, worker)
    if gen is None:
        log.info("attempt %s: delivery ignored (already claimed, finished or not eligible)", aid)
        return "ignored"
    fault("after_claim")
    s = get_settings()
    phase = "before_disclosure"

    def beat():
        svc.heartbeat(aid, worker, gen)

    try:
        content, docs, adapter_name = _snapshot(aid)
        refusal = _content_refusal(aid, content)
        if refusal:
            svc.fail_safe(aid, worker, gen, refusal)
            return "failed_safe"
        if adapter_name in API_ADAPTERS:
            refusal = _binding_refusal(aid)
            if refusal:
                svc.fail_safe(aid, worker, gen, refusal)
                return "failed_safe"
            return _run_api(aid, worker, gen, API_ADAPTERS[adapter_name](content, docs, str(aid)))
        adapter = ADAPTERS[adapter_name](content, docs)
        dest = content["destination"]
        if s.browser_isolation not in ("netns", "container") and s.env == "production":
            svc.fail_safe(aid, worker, gen, "browser network isolation is required")
            return "failed_safe"
        intercept = not s.execution_test_disable_interception
        if not intercept and s.env not in ("development", "test"):
            svc.fail_safe(aid, worker, gen, "request interception cannot be disabled here")
            return "failed_safe"
        refusal = _binding_refusal(aid)
        if refusal:
            svc.fail_safe(aid, worker, gen, refusal)
            return "failed_safe"
        try:
            session = browser_session(
                dest["origin"],
                s.navigation_timeout_seconds * 1000,
                isolation=s.browser_isolation,
                intercept=intercept,
                # Local fixture receivers live on loopback; only they get this exception.
                allow_private_destination=is_fixture_origin(dest["origin"]),
            )
            page, eg = session.__enter__()
        except IsolationUnavailable as e:
            # The fixed code only: the message is for developers reading the code, never stored.
            log.warning("attempt %s: browser isolation unavailable (%s)", aid, e.code)
            svc.fail_safe(aid, worker, gen, f"browser isolation unavailable ({e.code})")
            return "failed_safe"
        with _Closing(session):
            beat()
            fault("before_navigate")
            url = adapter.form_url()
            if rehearsal.normalize_origin(_origin_of(url)) != rehearsal.normalize_origin(
                dest["origin"]
            ):
                svc.fail_safe(aid, worker, gen, "the form is not on the destination's site")
                return "failed_safe"
            try:
                page.goto(url)
            except Exception as e:  # noqa: BLE001 - any navigation failure is a safe stop
                svc.fail_safe(aid, worker, gen, f"could not open the form ({type(e).__name__})")
                return "failed_safe"
            reason = adapter.blocked_reason(page) or adapter.schema_matches(page)
            if reason:
                svc.fail_safe(aid, worker, gen, reason)
                return "failed_safe"
            beat()
            try:
                svc.gate_before_disclosure(aid, worker, gen)
            except svc.GateRefused as e:
                svc.fail_safe(aid, worker, gen, str(e), code=e.code)
                return "failed_safe"
            phase = "after_disclosure"
            fault("after_disclosure_gate")
            try:
                disclosures = adapter.fill(page)
            except UploadFailed as e:
                _record_disclosures(aid, worker, gen, e.disclosures)
                svc.abandon(aid, worker, gen, str(e))
                return "abandoned"
            for d in disclosures:
                svc.record_evidence(aid, worker, gen, "disclosure", d)
            mismatches = adapter.readback(page)
            # How many fields kept their values, never which (the posting's field keys).
            svc.record_evidence(
                aid,
                worker,
                gen,
                "readback",
                {"checked": len(content["answers"]), "mismatched": len(mismatches)},
            )
            if mismatches:
                n = len(mismatches)  # which fields is kept in the readback evidence, not here
                svc.abandon(aid, worker, gen, f"{n} field(s) did not keep their values")
                return "abandoned"
            reason = adapter.schema_matches(page)  # conditional fields appear after filling
            if reason:
                svc.abandon(aid, worker, gen, reason)
                return "abandoned"
            svc.record_evidence(aid, worker, gen, "recheck", rehearsal.RECHECK_MATCHED)
            denied = eg.proxy_denied()
            if eg.blocked or denied:
                # Distinct blocked destinations by address category, never the hosts.
                svc.record_evidence(
                    aid,
                    worker,
                    gen,
                    "egress",
                    {
                        "blocked_requests": len(eg.blocked),
                        "blocked_destinations": _categories(
                            {_origin_of(u) for u in eg.blocked}, _host_of_origin
                        ),
                        "proxy_denied": _categories(set(denied), _host_of_hostport),
                    },
                )
            beat()
            if _rehearsal(aid):
                return _stop_rehearsal(aid, worker, gen)
            fault("before_send_gate")
            try:
                svc.gate_before_send(aid, worker, gen)
            except svc.GateRefused as e:
                svc.abandon(aid, worker, gen, str(e), code=e.code)
                return "abandoned"
            phase = "after_send"
            fault("before_click")
            out = adapter.submit(page, s.submit_timeout_seconds * 1000)
            fault("after_click")
            if out.kind == "otp":
                return _verification_loop(aid, worker, gen, adapter, page, s)
            return _conclude(aid, worker, gen, adapter, page, out)
    except svc.LostAuthority:
        # Browser is already closed by the context manager. If we had passed the send gate the
        # sweeper will mark the attempt unknown; we never act on it again from here.
        log.warning("attempt %s: lost authority in phase %s; stopped", aid, phase)
        return "lost_authority"
    except Exception as e:  # noqa: BLE001
        # The exception type only: browser errors can quote URLs, selectors or page text, so
        # neither the message nor the traceback is logged (same as the API route below).
        log.warning("attempt %s failed in phase %s (%s)", aid, phase, type(e).__name__)
        reason = f"internal error ({type(e).__name__})"
        if phase == "before_disclosure":
            svc.fail_safe(aid, worker, gen, reason)
        elif phase == "after_disclosure":
            svc.abandon(aid, worker, gen, reason)
        else:
            svc.unknown(aid, worker, gen, reason)
        return "error"


def _stop_rehearsal(aid, worker, gen) -> str:
    """End a rehearsal through its stop (service.finish_rehearsal): `rehearsed` only if every
    gate check and the evidence check pass there; otherwise `abandoned` with the stop's reason.
    Nothing is ever submitted. LostAuthority propagates to the caller."""
    fault("before_rehearsal_stop")
    try:
        svc.finish_rehearsal(aid, worker, gen)
    except svc.GateRefused as e:
        svc.abandon(aid, worker, gen, str(e), code=e.code)
        return "abandoned"
    return "rehearsed"


def _record_disclosures(aid, worker, gen, disclosures: list[dict]) -> None:
    """Evidence of every upload made before an upload failed, the failed one included: data
    may have reached the employer even though the attempt stops."""
    for d in disclosures:
        svc.record_evidence(aid, worker, gen, "disclosure", d)


class _Closing:
    """Exit an already-entered context manager when the block ends."""

    def __init__(self, cm):
        self.cm = cm

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc)


def _host_of_origin(origin: str) -> str:
    return urlsplit(origin).hostname or ""


def _host_of_hostport(hostport: str) -> str:
    return hostport.rsplit(":", 1)[0]


def _categories(destinations: set[str], host_of) -> dict[str, int]:
    """{address category: number of distinct destinations}; no host is kept."""
    out: dict[str, int] = {}
    for d in destinations:
        c = destination_category(host_of(d))
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items()))


def _origin_of(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.netloc else p.scheme


def _run_api(aid, worker, gen, adapter) -> str:
    """The API route: the same phases and fencing as the browser route, no browser."""
    s = get_settings()
    phase = "before_disclosure"
    try:
        reason = adapter.validate_before_disclosure()
        if reason:
            svc.fail_safe(aid, worker, gen, reason)
            return "failed_safe"
        try:
            svc.gate_before_disclosure(aid, worker, gen)
        except svc.GateRefused as e:
            svc.fail_safe(aid, worker, gen, str(e), code=e.code)
            return "failed_safe"
        phase = "after_disclosure"
        fault("after_disclosure_gate")
        try:
            draft = adapter.prepare()
            svc.record_evidence(aid, worker, gen, "disclosure",
                                {"route": "api", "kind": "application_draft"})  # fmt: skip
            for d in adapter.upload(draft):
                svc.record_evidence(aid, worker, gen, "disclosure", d)
        except UploadFailed as e:
            _record_disclosures(aid, worker, gen, e.disclosures)
            svc.abandon(aid, worker, gen, str(e))
            return "abandoned"
        if _rehearsal(aid):
            # Rehearsals only: read the job's schema again (read-only) after the uploads, so the
            # stop can check the form was still the approved one. A submission is unchanged.
            svc.heartbeat(aid, worker, gen)
            reason = adapter.validate_before_disclosure()
            if reason:
                svc.abandon(aid, worker, gen, reason)
                return "abandoned"
            svc.record_evidence(aid, worker, gen, "recheck", rehearsal.RECHECK_MATCHED)
            return _stop_rehearsal(aid, worker, gen)
        fault("before_send_gate")
        try:
            svc.gate_before_send(aid, worker, gen)
        except svc.GateRefused as e:
            svc.abandon(aid, worker, gen, str(e), code=e.code)
            return "abandoned"
        phase = "after_send"
        fault("before_click")
        out = adapter.submit(draft, s.submit_timeout_seconds * 1000)
        fault("after_click")
        if out.kind == "accepted":
            ev = adapter.receipt_evidence(out)
            fault("after_receipt_before_commit")
            svc.confirmed(aid, worker, gen,
                          [{"kind": "receipt", "data": ev,
                            "strength": adapter.confirmation_strength}])  # fmt: skip
            return "confirmed"
        if out.kind == "rejected":
            svc.rejected(aid, worker, gen, out.detail)
            return "rejected"
        svc.unknown(aid, worker, gen, out.detail)
        return "unknown"
    except svc.LostAuthority:
        log.warning("attempt %s: lost authority in phase %s; stopped", aid, phase)
        return "lost_authority"
    except Exception as e:  # noqa: BLE001
        log.warning("attempt %s failed in phase %s (%s)", aid, phase, type(e).__name__)
        reason = f"internal error ({type(e).__name__})"
        if phase == "before_disclosure":
            svc.fail_safe(aid, worker, gen, reason)
        elif phase == "after_disclosure":
            svc.abandon(aid, worker, gen, reason)
        else:
            svc.unknown(aid, worker, gen, reason)
        return "error"


def reconcile_api(attempt_id: str) -> str:
    """For an API attempt with an unknown outcome: ask the API, read-only, whether its
    idempotency key was accepted, and record the finding as an event. Never resubmits and never
    changes the outcome by itself: the user reconciles the application (applications router)."""
    aid = uuid.UUID(attempt_id)
    content, docs, name = _snapshot(aid)
    if name not in API_ADAPTERS:
        raise ValueError("not an API attempt")
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, aid)
        if att.state != svc.S.unknown:
            raise ValueError("only an attempt with an unknown outcome is reconciled")
    finding = API_ADAPTERS[name](content, docs, str(aid)).reconcile()
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, aid)
        svc.event(db, att, "reconciliation_checked", finding=finding, route="api")
        db.commit()
    return finding


def _conclude(aid, worker, gen, adapter, page, out) -> str:
    if out.kind == "accepted":
        ev = adapter.receipt_evidence(page, out)
        fault("after_receipt_before_commit")
        svc.confirmed(
            aid,
            worker,
            gen,
            [{"kind": "receipt", "data": ev, "strength": adapter.confirmation_strength}],
        )
        return "confirmed"
    if out.kind == "rejected":
        svc.rejected(aid, worker, gen, out.detail)
        return "rejected"
    svc.unknown(aid, worker, gen, out.detail)
    return "unknown"


def _verification_loop(aid, worker, gen, adapter, page, s) -> str:
    cp = svc.open_checkpoint(aid, worker, gen, "Enter the code the employer emailed you.")
    deadline = time.monotonic() + s.checkpoint_ttl_seconds
    while True:
        if time.monotonic() > deadline:
            svc.abandon(aid, worker, gen, "no code was entered in time")
            return "abandoned"
        code, status = svc.take_code(cp, aid, worker, gen)
        if status in ("expired", "failed"):
            svc.abandon(aid, worker, gen, f"verification {status}")
            return "abandoned"
        if code is None:
            time.sleep(0.3)
            continue
        out = adapter.enter_code(page, code, s.submit_timeout_seconds * 1000)
        del code
        if out.kind == "wrong_code":
            if svc.code_result(cp, aid, worker, gen, accepted=False) == "failed":
                svc.abandon(aid, worker, gen, "too many incorrect codes")
                return "abandoned"
            continue
        if out.kind == "accepted":
            svc.code_result(cp, aid, worker, gen, accepted=True)
        return _conclude(aid, worker, gen, adapter, page, out)
