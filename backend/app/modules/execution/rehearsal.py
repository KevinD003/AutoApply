"""Rehearsal evidence (E5 step 3): what a rehearsal must show, what its record keeps, and
whether that record still holds. Used by the rehearsal stop (service.finish_rehearsal) and by
readiness (providers.readiness, through readiness_evidence). The rehearsal prerequisite (E6,
`prerequisite`, below): a submission through an employer/provider path needs a valid recorded
rehearsal on that path first, unless an earlier submission already established the path.

A rehearsal is an attempt whose approval permits disclosure only. It proves something only if it
ended through the stop, which repeats every gate check and checks the evidence rows below in the
same transaction, and only while its record and those rows still agree. Codes are fixed
identifiers; nothing here keeps or returns a host, URL, board, field key, file or page text.
Playwright-free: the API process imports this module."""

import logging
import re
import uuid
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from typing import NamedTuple
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.urlsafety import is_fixture_origin
from app.modules.execution.models import ACTIVE, Evidence, ExecutionAttempt, RehearsalRecord
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.models import ApplicationPackage, ApprovalScope, PackageApproval
from app.modules.preparation.package import ApprovalError

log = logging.getLogger("noefforts.execution")

# The adapters' acknowledgement values that mean "accepted" (adapters.fixture_ats.ACK_SHOWN and
# the fake API's), and the confirmation strengths bound to one attempt. Pinned by a test rather
# than imported, so this module never imports Playwright.
PAGE_ACK_OK = "attachment_shown"
API_ACK_OK = "digest_matched"
API_ROUTE_ADAPTERS = frozenset({"fake_api"})
ATTEMPT_BOUND_STRENGTHS = frozenset(
    {"employer_receipt", "employer_confirmation_page", "api_receipt"}
)
RECHECK_MATCHED = {"form": "matched"}
API_DRAFT = {"route": "api", "kind": "application_draft"}

# Why a rehearsal does not hold (fixed codes, safe to store, show and record).
CHECK_UNAVAILABLE = "rehearsal_check_unavailable"
REVOKED = "rehearsal_revoked"
MISMATCHED = "rehearsal_mismatched"
STALE = "rehearsal_stale"
EVIDENCE_MISSING = "rehearsal_evidence_missing"
EVIDENCE_INCONSISTENT = "rehearsal_evidence_inconsistent"
MESSAGES = {
    CHECK_UNAVAILABLE: "NoEfforts could not check this rehearsal just now.",
    REVOKED: "This rehearsal was withdrawn, or its evidence was deleted.",
    MISMATCHED: "This rehearsal was for a different kind of destination, or for an earlier "
    "version of how NoEfforts fills this form.",
    STALE: "This rehearsal is too old to count.",
    EVIDENCE_MISSING: "The evidence of this rehearsal is not complete.",
    EVIDENCE_INCONSISTENT: "The evidence of this rehearsal does not show every document "
    "acknowledged, every answer read back and the form checked again.",
}
# The record's fields that must equal what its evidence rows show, whenever it is relied on.
RECORDED = (
    "route",
    "uploads_expected",
    "uploads_acknowledged",
    "readback_mismatched",
    "recheck_matched",
    "egress_proxy_denied",
    "unresolved",
)


def destination_class(origin: str | None) -> str:
    """`fixture` only for an origin configured as a local fixture outside production
    (urlsafety.is_fixture_origin); anything else, a missing origin included, is `real`."""
    return "fixture" if origin and is_fixture_origin(origin) else "real"


def _rows(db: Session, att: ExecutionAttempt) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(
                Evidence.attempt_id == att.id,
                Evidence.user_id == att.user_id,
                Evidence.retain_until > utcnow(),
            )
            .order_by(Evidence.created_at)
        )
    )


def evidence_facts(db: Session, att: ExecutionAttempt, content: dict) -> tuple[dict, str | None]:
    """What the attempt's evidence rows show, as the counts a record keeps, and the reason they
    do not show a complete rehearsal (None when they do). Read in the caller's transaction."""
    rows = _rows(db, att)
    api = att.adapter in API_ROUTE_ADAPTERS
    ok = API_ACK_OK if api else PAGE_ACK_OK
    disclosures = [r.data for r in rows if r.kind == "disclosure"]
    uploads = [d for d in disclosures if "sha256" in d]
    readbacks = [r.data for r in rows if r.kind == "readback"]
    rechecks = [r.data for r in rows if r.kind == "recheck"]
    egress = [r.data for r in rows if r.kind == "egress"]
    docs = content.get("documents") or []
    facts = {
        "route": "api" if api else "browser",
        "uploads_expected": len(docs),
        "uploads_acknowledged": sum(1 for u in uploads if u.get("ack") == ok),
        "readback_mismatched": None
        if api or len(readbacks) != 1
        else readbacks[0].get("mismatched"),
        "recheck_matched": rechecks == [RECHECK_MATCHED],
        "egress_proxy_denied": sum(sum((e.get("proxy_denied") or {}).values()) for e in egress),
        "unresolved": len(content.get("unresolved") or [])
        + len(content.get("validation_errors") or []),
    }
    approved = sorted((d.get("field"), d.get("sha256")) for d in docs)
    sent = sorted((u.get("field"), u.get("sha256")) for u in uploads)
    if (
        not rechecks
        or (not api and not readbacks)
        or (api and API_DRAFT not in disclosures)
        or not set(approved) <= set(sent)
    ):
        return facts, EVIDENCE_MISSING
    if (
        sent != approved  # an upload of something not approved, or twice
        or facts["uploads_acknowledged"] != len(docs)  # refused, unacknowledged or not kept
        or not facts["recheck_matched"]
        or (not api and facts["readback_mismatched"] != 0)
        or (api and disclosures.count(API_DRAFT) != 1)
        or facts["unresolved"]
    ):
        # Requests the egress controls blocked or denied are counted, not disqualifying: a
        # denial means the control held (the browser's own background requests are denied too).
        return facts, EVIDENCE_INCONSISTENT
    return facts, None


def assess_record(
    db: Session,
    rec: RehearsalRecord,
    *,
    adapter_version: str,
    destination_class: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """None if the record still holds for `adapter_version` (and, if given, for a destination
    of that class); otherwise why not. Never raises: an unexpected error is a refusal. Runs in
    a savepoint, so a failed statement leaves the caller's transaction usable."""
    try:
        with db.begin_nested():
            return _assess(db, rec, adapter_version, destination_class, now)
    except Exception as e:  # noqa: BLE001 - fail closed; the type only, never the message
        log.warning("rehearsal record check failed (%s)", type(e).__name__)
        return CHECK_UNAVAILABLE


def _assess(db: Session, rec: RehearsalRecord, adapter_version, destination_class, now):
    if rec.revoked_at is not None:
        return REVOKED
    att = db.get(ExecutionAttempt, rec.attempt_id)
    if (
        att is None
        or att.user_id != rec.user_id
        or att.state != "rehearsed"
        or att.adapter != rec.adapter
        or att.path_ref != rec.path_ref
        or att.destination_class != rec.destination_class
        or (destination_class is not None and destination_class != rec.destination_class)
        or rec.adapter_version != adapter_version
    ):
        return MISMATCHED
    s = get_settings()
    if not 1 <= s.rehearsal_max_age_days <= s.evidence_retention_days:
        return CHECK_UNAVAILABLE
    if (now or utcnow()) - rec.recorded_at > timedelta(days=s.rehearsal_max_age_days):
        return STALE
    facts, code = evidence_facts(db, att, db.get(ApplicationPackage, att.package_id).content)
    if code is not None:
        return code
    if any(facts[k] != getattr(rec, k) for k in RECORDED):
        return EVIDENCE_INCONSISTENT
    return None


def readiness_evidence(db: Session, user_id, adapter: str = "greenhouse_dom"):
    """This user's own records for `adapter`, counted in the class each was recorded in:
    rehearsal records that still hold (assess_record), and confirmed attempts. A record or an
    attempt with no recorded class counts nowhere. Returns readiness.RecordedEvidence."""
    from app.modules.execution.policy import ADAPTER_VERSIONS
    from app.modules.providers.readiness import RecordedEvidence

    version = ADAPTER_VERSIONS[adapter]
    counts = dict(fixture=0, valid=0, with_upload=0, not_valid=0)
    for rec in db.scalars(
        select(RehearsalRecord).where(
            RehearsalRecord.user_id == user_id, RehearsalRecord.adapter == adapter
        )
    ):
        holds = assess_record(db, rec, adapter_version=version) is None
        if rec.destination_class == "fixture" and holds:
            counts["fixture"] += 1
        elif rec.destination_class == "real":
            counts["valid" if holds else "not_valid"] += 1
            if holds and rec.uploads_acknowledged > 0:
                counts["with_upload"] += 1
    confirmed = db.scalars(
        select(ExecutionAttempt).where(
            ExecutionAttempt.user_id == user_id,
            ExecutionAttempt.adapter == adapter,
            ExecutionAttempt.state == "confirmed",
        )
    ).all()
    real = 0
    for att in confirmed:
        # A real submission counts only if its send gate found the rehearsal prerequisite held.
        if att.destination_class != "real" or att.rehearsal_prerequisite not in HELD:
            continue
        if any(
            r.kind == "receipt" and r.strength in ATTEMPT_BOUND_STRENGTHS for r in _rows(db, att)
        ):
            real += 1
    return RecordedEvidence(
        scope="user",
        fixture_rehearsals=counts["fixture"],
        fixture_submissions=sum(a.destination_class == "fixture" for a in confirmed),
        rehearsals_valid=counts["valid"],
        rehearsals_valid_with_upload=counts["with_upload"],
        rehearsals_not_valid=counts["not_valid"],
        real_submissions=real,
    )


# ============================================================================================
# E6: the rehearsal prerequisite
#
# A path is (user, adapter, origin, board): the same employer board, reached by the same
# provider, for the same user. A submission through a path needs, first, a valid recorded
# rehearsal on it (`met`), or an earlier confirmed submission on it whose own send gate found
# the prerequisite held (`established`: the first submission has been made). Whichever of
# those is newest decides, so an older success never outvotes a newer failed or cancelled
# rehearsal. Every real destination has the rule; local fixtures have it only where the
# test-only setting adds it. A rehearsal is never permission to submit: the prerequisite is
# checked only for approvals to submit, which the user gives separately.

PATH_PREFIX = "path:v1:"
_PATH_DOMAIN = b"noefforts/rehearsal-path/v1"
_FIXTURE_SLUG = re.compile(r"/apply/([A-Za-z0-9_-]{1,100})/?")
BOARD_ADAPTERS = frozenset({"greenhouse_hosted", "greenhouse_dom", "fake_api"})
MET, ESTABLISHED, UNMET, NOT_REQUIRED = "met", "established", "unmet", "not_required"
HELD = frozenset({MET, ESTABLISHED})  # what a send gate may record as having held

# Why the prerequisite is not met, in the order the checks run (fixed codes, safe to store,
# show and record; their own vocabulary, apart from providers.routing.REASONS). Messages are
# fixed text and never name an employer, host, board or field.
PATH_UNKNOWN = "rehearsal_path_unknown"
NO_REHEARSAL = "no_rehearsal"
IN_PROGRESS = "rehearsal_in_progress"
FAILED = "rehearsal_failed"
INCOMPLETE = "rehearsal_incomplete"
APPROVAL_BEFORE = "approval_before_rehearsal"
REASONS = {
    CHECK_UNAVAILABLE: "NoEfforts could not check the rehearsal requirement just now, so "
    "nothing was submitted. Try again later.",
    PATH_UNKNOWN: "NoEfforts cannot tell which employer form and submission method this is, so "
    "no rehearsal can count for it. Apply on the employer's site.",
    NO_REHEARSAL: "Before the first submission to this employer's form by this method, a "
    "rehearsal must succeed: NoEfforts fills and checks the form, then stops before sending. "
    "Approve the package for a rehearsal first.",
    IN_PROGRESS: "A rehearsal of this employer's form is waiting or running. Let it finish, "
    "then approve to submit.",
    FAILED: "The latest rehearsal of this employer's form stopped before every check passed. "
    "Rehearse again.",
    INCOMPLETE: "The latest rehearsal of this employer's form was cancelled before it "
    "finished. Rehearse again.",
    REVOKED: "You withdrew the latest rehearsal of this employer's form, or deleted its "
    "evidence. Rehearse again.",
    MISMATCHED: "The latest rehearsal was for a different kind of destination, or for an "
    "earlier version of how NoEfforts fills this form. Rehearse again.",
    STALE: "The latest rehearsal of this employer's form is too old to count. Rehearse again.",
    EVIDENCE_MISSING: "The evidence of the latest rehearsal is no longer complete. Rehearse again.",
    EVIDENCE_INCONSISTENT: "The evidence of the latest rehearsal does not show every document "
    "acknowledged, every answer read back and the form checked again. Rehearse again.",
    APPROVAL_BEFORE: "Your approval to submit was not given with the latest rehearsal in view. "
    "Review the rehearsal's result and approve again.",
}
STATUS_MESSAGES = {
    MET: "A rehearsal of this employer's form by this method passed every check. Submitting "
    "still needs your separate approval to submit.",
    ESTABLISHED: "An earlier submission to this employer's form by this method was confirmed "
    "after a rehearsal, so no new rehearsal is required.",
    NOT_REQUIRED: "Local test form: no rehearsal is required before submitting.",
}


class Path(NamedTuple):
    adapter: str
    origin: str
    board: str


class Verdict(NamedTuple):
    status: str  # met | established | unmet | not_required
    code: str | None = None  # a REASONS code, only when unmet
    basis: uuid.UUID | None = None  # the rehearsal (met) or submission (established) relied on


class RehearsalRequired(ApprovalError):
    """An approval to submit, or a queueing, refused because the prerequisite is not met."""

    def __init__(self, code: str):
        super().__init__(refusal(code))
        self.code = code


def refusal(code: str) -> str:
    return f"{REASONS[code]} (reason: {code})"


def normalize_origin(origin: str | None) -> str | None:
    """`scheme://host[:port]`, lowercased, default ports dropped; None unless an http(s) origin
    and nothing else (no path, query, fragment or credentials)."""
    if not isinstance(origin, str):
        return None
    try:
        p = urlsplit(origin.strip())
        port = p.port
    except ValueError:
        return None
    if (
        p.scheme not in ("http", "https")
        or not p.hostname
        or p.path not in ("", "/")
        or p.query
        or p.fragment
        or p.username is not None
        or p.password is not None
    ):
        return None
    host = f"[{p.hostname}]" if ":" in p.hostname else p.hostname
    default = 443 if p.scheme == "https" else 80
    return f"{p.scheme}://{host}" if port in (None, default) else f"{p.scheme}://{host}:{port}"


def execution_path(destination: dict, adapter: str) -> Path | None:
    """The path a destination is reached through by `adapter`, or None when it cannot be told
    (then no rehearsal can count for it). Never raises."""
    try:
        origin = normalize_origin(destination.get("origin"))
        url = destination.get("url")
        if origin is None or not isinstance(url, str):
            return None
        u = urlsplit(url)
        if normalize_origin(f"{u.scheme}://{u.netloc}") != origin:
            return None  # the page is not on the destination's origin
        if adapter in BOARD_ADAPTERS:
            posting = gh.parse_posting(url, fixture_origin=is_fixture_origin(origin))
            board = posting.board if posting else None
        elif adapter == "fixture_ats":
            m = _FIXTURE_SLUG.fullmatch(u.path)
            board = m.group(1) if m else None
        else:
            board = None  # an adapter with no path rule: unknown, so it fails closed
        return Path(adapter, origin, board) if board else None
    except Exception:  # noqa: BLE001 - an unparseable destination has no path
        return None


def path_ref(user_id, path: Path | None) -> str | None:
    """The stored form of a path: a keyed digest (audit.service.keyed_digest, its own domain
    label), so a path cannot be recomputed from public board names without the key. Computed in
    the API only; the worker matches stored references and never needs the key."""
    if path is None:
        return None
    from app.modules.audit.service import keyed_digest

    digest = keyed_digest(_PATH_DOMAIN, user_id, path.adapter, path.origin, path.board)
    return PATH_PREFIX + digest[:32]


def rule_applies(destination_class: str | None, path: Path | None) -> bool:
    """Every destination that is not a local fixture has the rule. A fixture path has it only
    when the test-only setting names it, and only when env == "test"; the setting can only add
    the rule, and nothing that routes or classifies a destination reads it."""
    if destination_class != "fixture":
        return True
    s = get_settings()
    if s.env != "test" or path is None:
        return False
    key = f"{path.adapter}:{path.board}"
    return any(fnmatchcase(key, p) for p in s.execution_test_rehearsal_rule_paths)


_COMPUTE = object()


def prerequisite(
    db: Session,
    *,
    layer: str,
    user_id,
    destination: dict,
    adapter: str,
    adapter_version: str,
    destination_class: str | None,
    path_ref_value=_COMPUTE,
    approval: PackageApproval | None = None,
    lock: bool = False,
) -> Verdict:
    """Whether a submission through this destination may go ahead now. Checked at five layers
    (approve, enqueue, claim, the disclosure gate and the send gate) and for the review view;
    `layer` names the caller. `path_ref_value`: the attempt's stored reference (computed here
    when not given). `approval`: the approval to submit in use, which must have been given with
    the rehearsal relied on. `lock`: inside a gate, lock what is relied on (FOR SHARE), so a
    withdrawal or deletion committed after the gate's snapshot is a refusal, not missed.

    Never raises: anything unexpected is `rehearsal_check_unavailable`, never met. Runs in a
    savepoint, so a failed statement leaves the caller's transaction usable."""
    try:
        with db.begin_nested():
            path = execution_path(destination, adapter)
            if not rule_applies(destination_class, path):
                return Verdict(NOT_REQUIRED)
            ref = path_ref(user_id, path) if path_ref_value is _COMPUTE else path_ref_value
            return _verdict(
                db, user_id, path, ref, destination_class, adapter_version, approval, lock
            )
    except Exception as e:  # noqa: BLE001 - fail closed; the type only, never the message
        log.warning("rehearsal prerequisite check failed at %s (%s)", layer, type(e).__name__)
        return Verdict(UNMET, CHECK_UNAVAILABLE)


def _verdict(db, user_id, path, ref, cls, version, approval, lock) -> Verdict:
    s = get_settings()
    if not 1 <= s.rehearsal_max_age_days <= s.evidence_retention_days:
        return Verdict(UNMET, CHECK_UNAVAILABLE)
    if path is None:
        return Verdict(UNMET, PATH_UNKNOWN)
    if not (isinstance(ref, str) and ref.startswith(PATH_PREFIX)):
        return Verdict(UNMET, CHECK_UNAVAILABLE)  # e.g. queued before paths were recorded
    rows = db.execute(
        select(ExecutionAttempt, PackageApproval)
        .join(PackageApproval, PackageApproval.id == ExecutionAttempt.approval_id)
        .where(
            ExecutionAttempt.user_id == user_id,
            PackageApproval.user_id == user_id,
            ExecutionAttempt.path_ref == ref,
        )
        # Newest by when each finished (a result reached later is newer evidence about the
        # path, whatever the queueing order); one still running sorts by when it was queued.
        .order_by(
            func.coalesce(ExecutionAttempt.finished_at, ExecutionAttempt.created_at).desc(),
            ExecutionAttempt.id.desc(),
        )
    ).all()
    in_progress = False
    for att, appr in rows:  # newest first; the first finished rehearsal or establishing
        if appr.scope == ApprovalScope.disclose_only:  # submission decides
            if att.state in ACTIVE:
                in_progress = True  # never displaces a finished one
                continue
            return _from_rehearsal(db, att, user_id, path, ref, cls, version, approval, lock)
        if _establishes(db, att, appr, path, cls, version, lock):
            return Verdict(ESTABLISHED, None, att.id)
    return Verdict(UNMET, IN_PROGRESS if in_progress else NO_REHEARSAL)


def _from_rehearsal(db, att, user_id, path, ref, cls, version, approval, lock) -> Verdict:
    if att.state in ("failed_safe", "abandoned"):
        return Verdict(UNMET, FAILED)
    if att.state != "rehearsed":
        return Verdict(UNMET, INCOMPLETE)
    q = select(RehearsalRecord).where(
        RehearsalRecord.attempt_id == att.id, RehearsalRecord.user_id == user_id
    )
    rec = db.scalar(q.with_for_update(read=True) if lock else q)
    if rec is None:
        return Verdict(UNMET, EVIDENCE_MISSING)  # e.g. rehearsed before records existed
    if rec.path_ref != ref or rec.adapter != path.adapter:
        return Verdict(UNMET, MISMATCHED)
    code = _assess(db, rec, version, cls, None)
    if code is not None:
        return Verdict(UNMET, code)
    if approval is not None and approval.prerequisite_attempt_id != att.id:
        return Verdict(UNMET, APPROVAL_BEFORE)
    return Verdict(MET, None, att.id)


def _establishes(db, att, appr, path, cls, version, lock) -> bool:
    """A confirmed submission on the path, by the same adapter version and class, whose own send
    gate found the prerequisite held, with its attempt-bound receipt still retained."""
    if (
        att.state != "confirmed"
        or att.rehearsal_prerequisite not in HELD
        or att.destination_class != cls
        or att.adapter != path.adapter
        or appr.adapter_version != version
    ):
        return False
    q = select(Evidence.id).where(
        Evidence.attempt_id == att.id,
        Evidence.user_id == att.user_id,
        Evidence.kind == "receipt",
        Evidence.strength.in_(ATTEMPT_BOUND_STRENGTHS),
        Evidence.retain_until > utcnow(),
    )
    return db.scalar((q.with_for_update(read=True) if lock else q).limit(1)) is not None


# -- served views (wording from providers.wording; no host, board or path is ever served) ------


def view(db: Session, app, pkg, approval: PackageApproval | None) -> dict:
    """Where the prerequisite stands for this package, for its review page. A manual handoff (no
    execution binding) is `not_applicable`, with its route's own reason code."""
    from app.modules.execution.policy import approved_binding, execution_binding
    from app.modules.providers import routing, wording

    dest = pkg.content["destination"]
    submit = approval if approval is not None and approval.scope == ApprovalScope.submit else None
    current = execution_binding(dest, app.user_id)
    # A manual handoff stays one whatever an approval recorded (an approval given for it has no
    # execution method, which approved_binding would read as a pre-binding one).
    binding = (
        None
        if current is None
        else ((approved_binding(submit, dest) if submit else None) or current)
    )
    if binding is None:
        d = routing.decide(dest, app.user_id)
        status, code, message = "not_applicable", d.reason, d.message
    else:
        v = prerequisite(
            db,
            layer="view",
            user_id=app.user_id,
            destination=dest,
            adapter=binding["adapter"],
            adapter_version=binding["adapter_version"],
            destination_class=destination_class(dest.get("origin")),
            approval=submit,
        )
        status, code = v.status, v.code
        message = REASONS[code] if code else STATUS_MESSAGES[status]
    return {
        "status": status,
        "reason_code": code,
        "message": message,
        "label": wording.PREREQUISITE_LABELS[status],
    }


def evidence_class(att: ExecutionAttempt) -> str | None:
    """The evidence class an attempt's result belongs to, from its recorded destination class
    (providers/evidence.py). None when it counts as none (yet)."""
    if att.destination_class == "fixture":
        return "fixture"
    if att.destination_class != "real":
        return None
    if att.state == "rehearsed":
        return "rehearsal"
    if att.state == "confirmed" and att.rehearsal_prerequisite in HELD:
        return "real_submission"
    return None


def record_status(db: Session, att: ExecutionAttempt) -> dict:
    """For a rehearsed attempt: whether its own record still holds ("valid") or why not. Whether
    a submission may go ahead is the prerequisite's (the newest result on the path decides)."""
    from app.modules.execution.policy import ADAPTER_VERSIONS

    rec = db.scalar(
        select(RehearsalRecord).where(
            RehearsalRecord.attempt_id == att.id, RehearsalRecord.user_id == att.user_id
        )
    )
    if rec is None:  # e.g. rehearsed before records existed: nothing to withdraw
        return {"status": EVIDENCE_MISSING, "revoked_at": None, "withdrawable": False}
    code = assess_record(db, rec, adapter_version=ADAPTER_VERSIONS.get(rec.adapter, ""))
    return {
        "status": code or "valid",
        "revoked_at": rec.revoked_at,
        "withdrawable": rec.revoked_at is None,
    }
