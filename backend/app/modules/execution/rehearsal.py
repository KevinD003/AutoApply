"""Rehearsal evidence (E5 step 3): what a rehearsal must show, what its record keeps, and
whether that record still holds. Used by the rehearsal stop (service.finish_rehearsal) and by
readiness (providers.readiness, through readiness_evidence).

A rehearsal is an attempt whose approval permits disclosure only. It proves something only if it
ended through the stop, which repeats every gate check and checks the evidence rows below in the
same transaction, and only while its record and those rows still agree. Codes are fixed
identifiers; nothing here keeps or returns a host, URL, board, field key, file or page text.
Playwright-free: the API process imports this module."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.urlsafety import is_fixture_origin
from app.modules.execution.models import Evidence, ExecutionAttempt, RehearsalRecord
from app.modules.preparation.models import ApplicationPackage

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
        if att.destination_class != "real":
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
