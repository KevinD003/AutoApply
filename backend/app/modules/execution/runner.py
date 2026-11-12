"""Run one execution attempt end to end. Called by the Celery task (or the CLI in tests).

Phases and what a failure in each one means:
  before disclosure  -> failed_safe   (nothing left NoEfforts; may be retried by the sweeper)
  after disclosure   -> abandoned     (data entered/uploaded, not submitted; user decides)
  after send gate    -> unknown       (may have been accepted; reconcile, never auto-retry)
A rehearsal (an approval to disclose only) succeeds as `rehearsed` once the checks after
filling pass, before the send gate: data entered/uploaded, nothing submitted.
D142: a multi-page wizard is filled one page at a time between the disclosure gate and the
send gate (`_wizard_pages`): forward only, each step behind a gate that commits before it, and
anything unexpected ends the attempt for good (`abandoned`, or `unknown` when the employer may
hold the application); NoEfforts never runs that application again.
D154: after a page's answers are entered, what they started is waited for before the checks
(`_settle`), then the submit button (`adapter.final_ready`); and right before the send gate,
what the page itself would refuse at the final click is read without acting on it
(`adapter.page_would_refuse`): a stop with nothing sent. D156: the same before each wizard
page's Next (`adapter.next_ready`, `adapter.next_would_refuse`), that page never sent.
"""

import hashlib
import logging
import time
import traceback
import uuid
from functools import partial
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.urlsafety import destination_category, is_fixture_origin
from app.modules.documents.models import Document
from app.modules.documents.storage import get_storage
from app.modules.execution import live, policy, rehearsal, stopping
from app.modules.execution import service as svc
from app.modules.execution.adapters.ashby import AshbyFixtureAdapter
from app.modules.execution.adapters.fake_api import FakeApiAdapter
from app.modules.execution.adapters.fixture_ats import (
    ACK_DRAFT,
    ACK_ERROR,
    ACK_LEFT_FORM,
    ACK_NONE,
    REFUSAL_UNREAD,
    ConditionalRequired,
    FixtureAtsAdapter,
    FormChanged,
    StoppedAfterDisclosure,
    UploadFailed,
    draft_evidence,
)
from app.modules.execution.adapters.greenhouse import GreenhouseHostedAdapter
from app.modules.execution.adapters.greenhouse_dom import (
    GreenhouseDomAdapter,
    GreenhouseLiveAdapter,
)
from app.modules.execution.adapters.lever import LeverFixtureAdapter
from app.modules.execution.adapters.workday import NEXT_REFUSAL_UNREAD, WorkdayFixtureAdapter
from app.modules.execution.browser import IsolationUnavailable, browser_session
from app.modules.execution.faults import fault, run_clock
from app.modules.execution.models import ExecutionAttempt
from app.modules.execution.stopping import StopRequested
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
    "greenhouse_live": GreenhouseLiveAdapter,  # D102: the Greenhouse pilot
    "fixture_lever": LeverFixtureAdapter,
    "fixture_ashby": AshbyFixtureAdapter,
    "fixture_workday": WorkdayFixtureAdapter,
}

log = logging.getLogger("noefforts.execution")


SETTLE_LOAD_MS = 8000  # how long a form's page may take to finish loading what it needs
SETTLE_ENTRY_MS = 8000  # D154: and what entering a page's answers started
QUIET_MS = 100  # nothing it needs in flight for this long: the page is ready
_POLL_MS = 25
# What a form's own set-up waits on. Not waited on: WebSockets and event streams (open by
# design), images, media and fonts (they change no control's behaviour), pings and beacons.
_TRACKED = frozenset({"document", "script", "stylesheet", "xhr", "fetch"})
NOT_READY = "the form's page was still loading after 8 seconds"
# D154: the requests the page started while the answers were entered never finished.
STILL_LOADING = "the page was still loading 8 seconds after the answers were entered"
# D111: the browser followed a redirect of a request only a path-limited rule admits (the
# pilot's locale files), which the page's fetch guard should have prevented.
LOCALE_REDIRECTED = "a request for one of the page's locale files was redirected"


class _Loading:
    """The page's own requests still in flight, counted from before the form is opened."""

    def __init__(self, page):
        self.page, self.pending = page, set()
        page.on("request", self._start)
        page.on("requestfinished", self._end)
        page.on("requestfailed", self._end)

    def _start(self, request) -> None:
        if request.resource_type in _TRACKED:
            self.pending.add(request)

    def _end(self, request) -> None:
        self.pending.discard(request)

    def close(self) -> None:
        for event, fn in (
            ("request", self._start),
            ("requestfinished", self._end),
            ("requestfailed", self._end),
        ):
            self.page.remove_listener(event, fn)


def _settle(
    page, loading: _Loading, honour_stop: bool = False, limit_ms: int | None = None
) -> bool:
    """Wait until the page has finished the requests it made by itself (its scripts, a locale
    file): a control may only respond once they have arrived, and on a busy machine they come
    late (CI #133). True as soon as none has been in flight for QUIET_MS; False if the page is
    still loading after SETTLE_LOAD_MS, and the caller stops safely. It only waits: nothing is
    typed, clicked, sent or repeated. D150: with `honour_stop` (the first page, before anything
    is entered) a stop request ends the wait (StopRequested); never after a page's Next, whose
    outcome the reads after this wait decide."""
    deadline = time.monotonic() + (SETTLE_LOAD_MS if limit_ms is None else limit_ms) / 1000
    quiet_since = None
    while True:
        if honour_stop:
            stopping.raise_if_requested()
        now = time.monotonic()
        if loading.pending:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = now
        elif now - quiet_since >= QUIET_MS / 1000:
            return True
        if now >= deadline:
            return False
        page.wait_for_timeout(_POLL_MS)


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


def _binding_refusal(attempt_id) -> tuple[str, str | None] | None:
    """Why this attempt may not run with its recorded adapter now (a message and a reason code,
    when there is one), or None. Checked before any adapter code touches a page; the gates
    re-check it under lock."""
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, attempt_id)
        appr = db.get(PackageApproval, att.approval_id)
        dest = db.get(ApplicationPackage, att.package_id).content["destination"]
        try:
            policy.check_binding(appr, dest, att.adapter)
        except policy.BindingChanged:
            return "the execution method changed after approval", None
        except policy.UnsupportedDestination as e:
            return str(e), e.code
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
    fault("before_claim")
    if stopping.requested():
        # D150: a worker asked to stop claims nothing. The attempt stays queued, with a new
        # message the relay publishes within seconds for the next worker (its own republish,
        # D146, would wait five minutes).
        log.info("attempt %s: not claimed, the worker was asked to stop", aid)
        svc.publish_again(aid)
        return "stopping"
    gen = svc.claim(aid, worker)
    if gen is None:
        log.info("attempt %s: delivery ignored (already claimed, finished or not eligible)", aid)
        return "ignored"
    fault("after_claim")
    s = get_settings()
    phase = "before_disclosure"
    started = run_clock()
    last_beat = [time.monotonic()]
    honour_stop = [True]  # D150: off once a rehearsal has filled (nothing protected is left)

    def stop_if_requested():
        if honour_stop[0]:
            stopping.raise_if_requested()

    def within_budget():
        # D143: the run's own time limit, checked between steps and so never raised inside a
        # browser wait. Past it the run stops as its phase says: before the final click that
        # is always "nothing was submitted". D150: a stop request is honoured at the same
        # checks, and first.
        stop_if_requested()
        if run_clock() - started > s.attempt_run_budget_seconds:
            raise RunBudgetExceeded()

    def beat():
        within_budget()
        svc.heartbeat(aid, worker, gen)
        last_beat[0] = time.monotonic()
        stop_if_requested()  # D150: again after the round trip, right before the step it guards

    def lost_browser(reason: str) -> str:
        # D150: before anything was entered, a browser lost or a page not ready while the worker
        # is being stopped (the whole stack stopping with it, Ctrl-C) ends as the stop does.
        if stopping.requested():
            return _stopped(aid, worker, gen, "before_disclosure")
        svc.fail_safe(aid, worker, gen, reason)
        return "failed_safe"

    def progress():
        # D143: between fields. Renews the lease at most every quarter of it, so a long fill or
        # readback is not taken for a lost worker; LostAuthority here (cancelled, swept, taken
        # away) stops the worker between fields.
        within_budget()
        if time.monotonic() - last_beat[0] >= s.lease_seconds / 4:
            beat()

    try:
        content, docs, adapter_name = _snapshot(aid)
        refusal = _content_refusal(aid, content)
        if refusal:
            svc.fail_safe(aid, worker, gen, refusal)
            return "failed_safe"
        if adapter_name in API_ADAPTERS:
            bound = _binding_refusal(aid)
            if bound:
                svc.fail_safe(aid, worker, gen, bound[0], code=bound[1])
                return "failed_safe"
            return _run_api(aid, worker, gen, API_ADAPTERS[adapter_name](content, docs, str(aid)))
        adapter = ADAPTERS[adapter_name](content, docs)
        adapter.on_progress = progress
        adapter.on_hand_over = beat  # D143: before each document and each page's Next
        dest = content["destination"]
        if s.browser_isolation not in ("netns", "container") and s.env == "production":
            svc.fail_safe(aid, worker, gen, "browser network isolation is required")
            return "failed_safe"
        intercept = not s.execution_test_disable_interception
        if not intercept and s.env not in ("development", "test"):
            svc.fail_safe(aid, worker, gen, "request interception cannot be disabled here")
            return "failed_safe"
        if adapter_name == live.ADAPTER and live.permission_refusal(("open", "disclose")):
            # D103: before the page is opened (the pilot's permission 2) or anything entered.
            svc.fail_safe(aid, worker, gen, live.WHY["not_authorized"], code="live_not_authorized")
            return "failed_safe"
        bound = _binding_refusal(aid)
        if bound:
            svc.fail_safe(aid, worker, gen, bound[0], code=bound[1])
            return "failed_safe"
        try:
            session = browser_session(
                dest["origin"],
                s.navigation_timeout_seconds * 1000,
                isolation=s.browser_isolation,
                intercept=intercept,
                # Local fixture receivers live on loopback; only they get this exception.
                allow_private_destination=is_fixture_origin(dest["origin"]),
                # D102: on a real Greenhouse board, its static scripts and stylesheets only.
                subresources=live.subresources(dest["origin"])
                if adapter_name == live.ADAPTER
                else (),
            )
            page, eg = session.__enter__()
        except IsolationUnavailable as e:
            # The fixed code only: the message is for developers reading the code, never stored.
            log.warning("attempt %s: browser isolation unavailable (%s)", aid, e.code)
            return lost_browser(f"browser isolation unavailable ({e.code})")
        with _Closing(session):
            beat()
            fault("before_navigate")
            within_budget()  # D150: a stop requested while the browser started; never opened
            url = adapter.form_url()
            if rehearsal.normalize_origin(_origin_of(url)) != rehearsal.normalize_origin(
                dest["origin"]
            ):
                svc.fail_safe(aid, worker, gen, "the form is not on the destination's site")
                return "failed_safe"
            if adapter_name == live.ADAPTER:  # D110: before any page script runs
                for js in live.init_scripts(dest["origin"]):
                    page.add_init_script(script=js)
            loading = _Loading(page)
            try:
                page.goto(url)
                ready = _settle(page, loading, honour_stop=True)
            except StopRequested:
                raise
            except Exception as e:  # noqa: BLE001 - any navigation failure is a safe stop
                return lost_browser(f"could not open the form ({type(e).__name__})")
            finally:
                loading.close()
            if not ready:  # a stop request during the wait ended it above (StopRequested)
                svc.fail_safe(aid, worker, gen, NOT_READY)
                return "failed_safe"
            reason = (
                (LOCALE_REDIRECTED if eg.redirected else None)
                or adapter.blocked_reason(page)
                or adapter.schema_matches(page)
            )
            if reason:
                _stop(aid, worker, gen, reason, svc.fail_safe)
                return "failed_safe"
            beat()
            try:
                svc.gate_before_disclosure(aid, worker, gen)
            except svc.GateRefused as e:
                svc.fail_safe(aid, worker, gen, str(e), code=e.code)
                return "failed_safe"
            phase = "after_disclosure"
            fault("after_disclosure_gate")
            recorded = _record_as_made(aid, worker, gen, adapter)
            settled = True
            try:
                if content.get("wizard"):  # D142: page by page, up to the review page
                    stopped = _wizard_pages(
                        aid, worker, gen, adapter, page, eg, recorded, beat, stop_if_requested
                    )
                    if stopped:
                        return stopped
                    disclosures = []  # every page's evidence is recorded as it was made
                else:
                    # D154: what the page itself starts while the answers are entered (a
                    # question it shows after a request) is waited for before anything is
                    # read back or checked, as when the form opened (`_settle`).
                    loading = _Loading(page)
                    adapter.on_settle = partial(_settle, page, loading, limit_ms=SETTLE_ENTRY_MS)
                    try:
                        disclosures = adapter.fill(page)
                        settled = _settle(page, loading, limit_ms=SETTLE_ENTRY_MS)
                    finally:
                        adapter.on_settle = None
                        loading.close()
            except StoppedAfterDisclosure as e:  # an upload, D104's search, or a page's Next
                _log_cause(aid, e)
                _record_disclosures(aid, worker, gen, _not_yet(e.disclosures, recorded))
                svc.abandon(aid, worker, gen, str(e))
                return "abandoned"
            if _rehearsal(aid):
                # D150: a rehearsal has filled; reading back, re-checking and ending it enter
                # nothing more, so a stop request no longer cuts it short (it ends rehearsed).
                honour_stop[0] = False
            for d in _not_yet(disclosures, recorded):
                svc.record_evidence(aid, worker, gen, "disclosure", d)
            if not settled:
                svc.abandon(aid, worker, gen, STILL_LOADING, retire_every="stopped_after_entry")
                return "abandoned"
            # D154: the submit button, waited for now (before the readback and the check after
            # filling, so what the page changed meanwhile is read back and checked as well).
            refused = adapter.final_ready(page)
            if refused:
                return _refused(aid, worker, gen, refused, stop_if_requested)
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
            # Conditional fields appear after filling; D111: a followed redirect stops it too.
            # D132: never a form-change pause here. Before filling the same page matched, so what
            # changed is the page's own reaction to the answers, which no re-read can show. Every
            # live approval is retired with the stop: entering the same data again is a new
            # approval. D135: the one exception, a question the page revealed and requires with no
            # approved answer, pauses so you can answer it (nothing was submitted either way).
            reason = (LOCALE_REDIRECTED if eg.redirected else None) or adapter.schema_matches(page)
            if reason:
                if isinstance(reason, ConditionalRequired) and svc.pause_after_entry(
                    aid, worker, gen, str(reason), reason.count
                ):
                    return "abandoned"
                svc.abandon(aid, worker, gen, str(reason), retire_every="stopped_after_entry")
                return "abandoned"
            # D154: what the page itself would refuse at the final click (the browser's own
            # validation of the form, fields the page marks as not valid, a submit button it
            # keeps hidden or disabled), read without acting on it: a stop with nothing sent,
            # where the click would have been refused after the send gate (an unknown outcome,
            # or a rejection after `sending`). Before the recheck evidence, so a rehearsal of a
            # page that would refuse the click is never recorded.
            refused = adapter.page_would_refuse(page)
            if refused:
                return _refused(aid, worker, gen, refused, stop_if_requested)
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
            within_budget()  # D143: a run past its budget never starts the send
            submit_ms = s.submit_timeout_seconds * 1000
            try:
                svc.gate_before_send(aid, worker, gen, adapter.send_watch_seconds(submit_ms))
            except svc.GateRefused as e:
                svc.abandon(aid, worker, gen, str(e), code=e.code)
                return "abandoned"
            phase = "after_send"
            fault("before_click")
            out = adapter.submit(page, submit_ms)
            fault("after_click")
            if out.kind == "otp":
                return _verification_loop(aid, worker, gen, adapter, page, s)
            return _conclude(aid, worker, gen, adapter, page, out)
    except svc.LostAuthority:
        # Browser is already closed by the context manager. If we had passed the send gate the
        # sweeper will mark the attempt unknown; we never act on it again from here.
        log.warning("attempt %s: lost authority in phase %s; stopped", aid, phase)
        return "lost_authority"
    except StopRequested:
        return _stopped(aid, worker, gen, phase)
    except Exception as e:  # noqa: BLE001
        # The exception type only: browser errors can quote URLs, selectors or page text, so
        # neither the message nor the traceback is logged (same as the API route below).
        log.warning(
            "attempt %s failed in phase %s (%s) at %s",
            aid, phase, type(e).__name__, _origin_frames(e),
        )  # fmt: skip
        if phase != "after_send" and honour_stop[0] and stopping.requested():
            # D150: an error while the worker is being stopped (its browser closed with the
            # stack, Ctrl-C) ends as the stop does; past the send gate, as before.
            return _stopped(aid, worker, gen, phase)
        reason = _failure_reason(e)
        if phase == "before_disclosure":
            svc.fail_safe(aid, worker, gen, reason)
        elif phase == "after_disclosure":
            svc.abandon(aid, worker, gen, reason)
        else:
            svc.unknown(aid, worker, gen, reason)
        return "error"


TIME_LIMIT = "the run reached its time limit and was stopped"
STOP_REQUESTED = "the worker was asked to stop"


class RunBudgetExceeded(Exception):
    """D143: the attempt took longer than its run budget (attempt_run_budget_seconds) to reach
    the final click. Raised by the runner between steps, never inside a browser wait."""


def _stopped(aid, worker, gen, phase: str) -> str:
    """D150: where a run asked to stop ends. Before anything was entered the attempt goes back
    in the queue for the next worker (service.requeue_on_stop); after, it is abandoned like any
    stop there, never retried. Never reached after the send gate."""
    log.info("attempt %s: stopped in phase %s, the worker was asked to stop", aid, phase)
    if phase == "before_disclosure":
        out = svc.requeue_on_stop(aid, worker, gen)
        if out is not None:
            return {"requeued": "requeued", "failed": "failed_safe"}[out]
        # None: no longer held (a cancel, the sweeper), or data was entered after all
    return "abandoned" if svc.abandon(aid, worker, gen, STOP_REQUESTED) else "lost_authority"


def _failure_reason(e: BaseException) -> str:
    """D143: the run budget is said as what it is, not as an internal error. The outcome is the
    one the phase gives any failure there (the budget is only checked before the send gate):
    nothing is retried after disclosure."""
    if isinstance(e, RunBudgetExceeded):
        return TIME_LIMIT
    return f"internal error ({type(e).__name__})"


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


NEXT_NOT_SAVED = {
    ACK_ERROR: "the employer's page showed an error after a page's Next",
    ACK_NONE: "the employer's page did not answer a page's Next in time, so NoEfforts does not "
    "know whether that page was saved",
}
NOT_NEXT_PAGE = "the employer's form did not show the next page after a page's Next"
LEFT_FORM = {
    "confirmation": "the page showed a confirmation",
    "already_applied": "the page said you have already applied",
}


def _wizard_pages(
    aid, worker, gen, adapter, page, eg, recorded, beat, stop_if_requested
) -> str | None:
    """D142: pages 1 to N-1 of a multi-page wizard, forward only, after the disclosure gate (which
    authorized filling page 1). For each page: a gate before filling it (from page 2), filling it
    (documents first), a readback of every page so far recorded as evidence `step`, a gate before
    its Next, one click of its Next, the page's answer recorded as disclosure evidence, then the
    checks that the form now shows the next page and is still the approved form. Each gate commits
    its `step_authorized` event before the action, so a worker lost after a click leaves the
    record. D148: before the gate for a page's Next, the questions that page shows by its own
    logic must be what was entered (`page_follow_ups`). D154: what filling a page started is
    waited for before its checks (`_settle`); a page still loading ends the attempt there, its
    Next never clicked. D156: then its Next, shown and enabled, before the readback
    (`adapter.next_ready`), and right before the gate for its Next, what the page itself would
    refuse at that click (`adapter.next_would_refuse`), as D154 before the final click: either
    ends the attempt with that page never sent (`_refused`). Returns None when the review page
    is reached, or the runner's result once the attempt has ended: `abandoned` (any refusal or
    finding; `svc.abandon` says pages may be saved at the employer and retires every approval),
    `unknown` (the page left the form after a Next: quarantined, the employer may hold the
    application) or `lost_authority`. Never a pause, never `fail_safe`, never a second click.
    LostAuthority and StoppedAfterDisclosure propagate to the runner, which ends the attempt as
    for any other step."""
    s = get_settings()
    pages = len(adapter.content["wizard"]["pages"])

    def gate(i: int, phase: str) -> str | None:
        try:
            svc.gate_before_step(aid, worker, gen, i, phase)
        except svc.GateRefused as e:
            svc.abandon(aid, worker, gen, str(e), code=e.code)
            return "abandoned"
        return None

    for i in range(1, pages):
        if i >= 2:
            beat()
            fault(f"before_fill_gate_{i}")
            if gate(i, "fill"):
                return "abandoned"
            beat()
        loading = _Loading(page)  # D154: what the page's answers started, before its checks
        adapter.on_settle = partial(_settle, page, loading, limit_ms=SETTLE_ENTRY_MS)
        try:
            filled = adapter.fill_page(page, i)
            settled = _settle(page, loading, limit_ms=SETTLE_ENTRY_MS)
        finally:
            adapter.on_settle = None
            loading.close()
        for d in _not_yet(filled, recorded):
            svc.record_evidence(aid, worker, gen, "disclosure", d)
        if not settled:
            svc.abandon(aid, worker, gen, STILL_LOADING)
            return "abandoned"
        # D156: its Next, waited for now (before the readback, as D154's submit button).
        refused = adapter.next_ready(page, i)
        if refused:
            return _refused(aid, worker, gen, refused, stop_if_requested)
        mismatches = adapter.readback_through(page, i)
        # How many fields so far kept their values, never which (the posting's field keys).
        checked = len(adapter.page_answers(*range(1, i + 1)))
        step = {"page": i, "checked": checked, "mismatched": len(mismatches)}
        svc.record_evidence(aid, worker, gen, "step", step)
        if mismatches:
            svc.abandon(aid, worker, gen, f"{len(mismatches)} field(s) did not keep their values")
            return "abandoned"
        # D148: what the page shows after an earlier answer is what was entered; one it requires
        # with no approved answer ends the attempt here, its Next never clicked (never a pause).
        follow_up = adapter.page_follow_ups(page, i)
        if follow_up:
            svc.abandon(aid, worker, gen, follow_up)
            return "abandoned"
        # D156: what the page itself would refuse at this Next (a field it marks as not valid, a
        # Next it keeps hidden or disabled), read without acting on it: this page never sent.
        refused = adapter.next_would_refuse(page, i)
        if refused:
            return _refused(aid, worker, gen, refused, stop_if_requested)
        beat()
        fault(f"before_next_gate_{i}")
        if gate(i, "next"):
            return "abandoned"
        beat()
        loading = _Loading(page)  # before the click: what the Next starts is waited for
        try:
            ack = adapter.click_next(page, i, s.navigation_timeout_seconds * 1000)
            fault(f"after_next_ack_{i}")
            adapter._disclosed(draft_evidence(i, ack))  # recorded at once, fenced (D137)
            settled = _settle(page, loading)
        finally:
            loading.close()
        kind = adapter.body_kind(page)
        if ack == ACK_LEFT_FORM or kind != "form":
            what = LEFT_FORM.get(kind or "", "the page was no longer the application form")
            if svc.quarantine_after_step(aid, worker, gen, what):
                return "unknown"
            return "lost_authority"  # the fence refused: another writer ended it first
        if ack != ACK_DRAFT:
            svc.abandon(aid, worker, gen, NEXT_NOT_SAVED.get(ack, NEXT_NOT_SAVED[ACK_NONE]))
            return "abandoned"
        if not settled:
            svc.abandon(aid, worker, gen, NOT_READY)
            return "abandoned"
        if not adapter.on_page(page, i + 1):
            svc.abandon(aid, worker, gen, NOT_NEXT_PAGE)
            return "abandoned"
        reason = (
            (LOCALE_REDIRECTED if eg.redirected else None)
            or adapter.blocked_reason(page)
            or adapter.schema_matches(page)
        )
        if reason:
            svc.abandon(aid, worker, gen, str(reason))
            return "abandoned"
    return None


def _refused(aid, worker, gen, reason: str, stop_if_requested) -> str:
    """D154: a stop before the send gate for what the page itself would refuse at the final
    click (`adapter.final_ready`, `adapter.page_would_refuse`): abandoned with nothing sent,
    every live approval retired (D132), never a pause or a retry. A page that could not be read
    while the worker is being stopped (its browser closed with it) ends as the stop does (D150,
    StopRequested), where the stop is honoured. D156: the same before a wizard page's Next
    (`adapter.next_ready`, `adapter.next_would_refuse`), that page never sent."""
    if reason in (REFUSAL_UNREAD, NEXT_REFUSAL_UNREAD):
        stop_if_requested()
    svc.abandon(aid, worker, gen, str(reason), retire_every="stopped_after_entry")
    return "abandoned"


def _stop(aid, worker, gen, reason: str, plain) -> None:
    """End the attempt, before anything is entered, for a live page that is not the approved
    one. D132: a change a fresh read can show (`FormChanged`) pauses the application, with
    every live approval retired; any other reason, or a pause the fence refused, is the plain
    stop it always was (`plain`). Either way the runner returns the same result."""
    if isinstance(reason, FormChanged):
        if svc.pause_for_form_change(aid, worker, gen, str(reason), reason.counts):
            return
    plain(aid, worker, gen, str(reason))


def _record_as_made(aid, worker, gen, adapter) -> list[dict]:
    """D137: the adapter reports each disclosure the moment it makes it (an acknowledged upload,
    a location search, a section control), and it is recorded at once, fenced by generation. So
    a failure later in filling, or a worker lost after it, never loses the evidence that it
    reached the employer; a worker that lost its authority stops at its next disclosure (the
    fence raises LostAuthority). Not covered: a worker killed while a disclosure is still in
    flight (a document handed over, its acknowledgement not yet read). Returns what was
    recorded, which is never recorded again."""
    recorded: list[dict] = []

    def record(d: dict) -> None:
        svc.record_evidence(aid, worker, gen, "disclosure", d)
        recorded.append(d)

    adapter.on_disclosure = record
    return recorded


def _log_cause(aid, e: BaseException) -> None:
    """D137: a stop that wraps another error keeps its diagnostics: the type and where it was
    raised, never the message (browser errors can quote URLs, selectors or page text)."""
    cause = e.__cause__
    if cause is not None:
        log.warning(
            "attempt %s stopped after disclosure by %s at %s",
            aid, type(cause).__name__, _origin_frames(cause),
        )  # fmt: skip


def _not_yet(disclosures: list[dict], recorded: list[dict]) -> list[dict]:
    """The disclosures not already recorded as they were made (the same objects, not equal
    ones: two uploads may carry the same evidence)."""
    return [d for d in disclosures if not any(d is r for r in recorded)]


def _record_disclosures(aid, worker, gen, disclosures: list[dict]) -> None:
    """Evidence of every disclosure made before filling stopped (an upload that failed, a
    location search that could not be completed), the last one included: data may have reached
    the employer even though the attempt stops."""
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


def _origin_frames(e: BaseException, limit: int = 15) -> str:
    """Where an exception came from, as code locations only: `file:line:function` for the last
    frames, never `str(e)`. A browser error can quote a URL, selector or page text in its
    message, so the message and arguments are never logged — but a traceback frame carries only
    source positions (locals and source lines are not looked up here), which name our own code
    and leak nothing about the page or the applicant. This turns an opaque "internal error
    (TypeError)" into the exact line to look at. Diagnostics must never themselves raise."""
    try:
        summary = traceback.StackSummary.extract(
            traceback.walk_tb(e.__traceback__), lookup_lines=False, capture_locals=False
        )
        parts = [
            f"{fr.filename.rsplit('/', 1)[-1]}:{fr.lineno}:{fr.name}"
            for fr in list(summary)[-limit:]
        ]
        return " > ".join(parts) or "-"
    except Exception:  # noqa: BLE001
        return "-"


def _run_api(aid, worker, gen, adapter) -> str:
    """The API route: the same phases and fencing as the browser route, no browser."""
    s = get_settings()
    phase = "before_disclosure"
    try:
        stopping.raise_if_requested()  # D150: before the API is asked anything
        reason = adapter.validate_before_disclosure()
        if reason:
            svc.fail_safe(aid, worker, gen, reason)
            return "failed_safe"
        try:
            svc.gate_before_disclosure(aid, worker, gen)  # D150: it reads the stop request last
        except svc.GateRefused as e:
            svc.fail_safe(aid, worker, gen, str(e), code=e.code)
            return "failed_safe"
        phase = "after_disclosure"
        fault("after_disclosure_gate")
        recorded = _record_as_made(aid, worker, gen, adapter)
        adapter.before_document = stopping.raise_if_requested  # D150: before each document
        try:
            stopping.raise_if_requested()  # D150: the draft and the uploads below disclose
            draft = adapter.prepare()
            svc.record_evidence(aid, worker, gen, "disclosure",
                                {"route": "api", "kind": "application_draft"})  # fmt: skip
            for d in _not_yet(adapter.upload(draft), recorded):
                svc.record_evidence(aid, worker, gen, "disclosure", d)
        except UploadFailed as e:
            _log_cause(aid, e)
            _record_disclosures(aid, worker, gen, _not_yet(e.disclosures, recorded))
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
            svc.gate_before_send(aid, worker, gen)  # D150: it reads the stop request last
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
    except StopRequested:
        return _stopped(aid, worker, gen, phase)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "attempt %s failed in phase %s (%s) at %s",
            aid, phase, type(e).__name__, _origin_frames(e),
        )  # fmt: skip
        if phase != "after_send" and stopping.requested():  # D150, as on the browser route
            return _stopped(aid, worker, gen, phase)
        reason = _failure_reason(e)
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


def _abandoned(aid, worker, gen, reason: str) -> str:
    return "abandoned" if svc.abandon(aid, worker, gen, reason) else "lost_authority"


def _verification_loop(aid, worker, gen, adapter, page, s) -> str:
    cp = svc.open_checkpoint(aid, worker, gen, "Enter the code the employer emailed you.")
    submit_ms = s.submit_timeout_seconds * 1000
    deadline = run_clock() + s.checkpoint_ttl_seconds  # from the request, not from the first look
    fault("in_code_wait")
    while True:
        if stopping.requested():
            # D150: entering a code is a protected step, so the verification is left unfinished;
            # a code typed meanwhile is erased with the request.
            return _abandoned(aid, worker, gen, STOP_REQUESTED)
        # D143: a code is looked for before the wait's own end is judged, so one accepted in the
        # wait's last moment is still entered.
        code, status = svc.take_code(cp, aid, worker, gen, adapter.code_watch_seconds(submit_ms))
        if status in ("expired", "failed"):
            svc.abandon(aid, worker, gen, f"verification {status}")
            return "abandoned"
        if code is not None and stopping.requested():  # D150: taken, never entered
            del code
            return _abandoned(aid, worker, gen, STOP_REQUESTED)
        if code is None:
            if run_clock() > deadline:
                svc.abandon(aid, worker, gen, "no code was entered in time")
                return "abandoned"
            time.sleep(0.3)
            continue
        out = adapter.enter_code(page, code, submit_ms)
        del code
        if out.kind == "wrong_code":
            if svc.code_result(cp, aid, worker, gen, accepted=False) == "failed":
                svc.abandon(aid, worker, gen, "too many incorrect codes")
                return "abandoned"
            continue
        if out.kind == "accepted":
            svc.code_result(cp, aid, worker, gen, accepted=True)
        return _conclude(aid, worker, gen, adapter, page, out)
