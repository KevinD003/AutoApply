"""Reading one job board you added, and saving one of its postings to your jobs (D95).

A read is one user action on one source. It locks that source (a second read of it at the same
time is refused, never queued), reads it with discovery/boards.py and then, in one commit:
  * stores each posting as a discovered posting of that source (provenance: the source, the
    provider, the posting's id; deduplicated within the source by that id);
  * links a posting to one of your jobs only when that job already exists (the same link, or
    the same employer and title: `service._existing_job`, as for Freehire). Nothing new is added
    to your jobs until you save a posting;
  * after a complete read only, marks a posting it no longer lists as "no longer listed by the
    board", and one listed again as listed. A failed or incomplete read changes no posting.
A failed read backs off (doubling from 5 minutes, at most a day; a 429's Retry-After within 1
minute and 1 day) and a successful one waits `board_min_interval_seconds` before the next.
Nothing here touches an application, an approval, a package or a route: a posting's source
saying it is open is not a match, not eligibility and not a way to apply."""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.modules.discovery import boards
from app.modules.discovery.models import BoardSource, DiscoveredJob
from app.modules.discovery.provider import MalformedRecord, NormalizedJob
from app.modules.discovery.service import COMPARED, ImportResult, _existing_job, _link

log = logging.getLogger("noefforts.discovery.boards")
NO_LONGER_LISTED = "no longer listed by the board"


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _lock(db: Session, user_id, source_id) -> BoardSource:
    try:
        src = db.scalar(
            select(BoardSource)
            .where(BoardSource.id == source_id, BoardSource.user_id == user_id)
            .with_for_update(nowait=True)
        )
    except OperationalError:
        db.rollback()
        raise Refused("sync_in_progress", "This board is being read already.") from None
    if src is None:
        raise LookupError
    return src


def sync(db: Session, user_id, source_id) -> dict:
    src = _lock(db, user_id, source_id)
    now = utcnow()
    s = get_settings()
    if not s.board_sources_enabled:
        raise Refused("board_sources_disabled",
                      "Reading job boards is not switched on for this NoEfforts.")  # fmt: skip
    if src.paused:
        raise Refused("source_paused", "This board is paused; resume it to read it.")
    if src.next_allowed_at and src.next_allowed_at > now:
        raise Refused("too_soon", "This board was read moments ago or is backing off after a "
                      "failure; try again later.")  # fmt: skip
    src.last_attempt_at = now
    try:
        fetched = boards.fetch(src.provider, src.region, src.board)
    except boards.BoardError as e:
        src.failures += 1
        src.last_status, src.last_error_code = "failed", e.code
        src.next_allowed_at = now + boards.backoff(src.failures, e.retry_after)
        db.commit()
        log.info("board source %s: failed (%s)", src.id, e.code)
        return {"status": "failed", "error_code": e.code, "message": e.message}
    out = {"status": "ok", "complete": fetched.complete, "requests": fetched.requests,
           "listed": 0, "new": 0, "changed": 0, "malformed": 0, "duplicates": 0,
           "in_your_jobs": 0, "no_longer_listed": 0, "listed_again": 0}  # fmt: skip
    seen: set[str] = set()
    for raw in fetched.records:
        try:
            n = boards.normalize(src.provider, src.id, src.employer, raw)
        except MalformedRecord:
            out["malformed"] += 1
            continue
        if n.source_job_id in seen:
            out["duplicates"] += 1
            continue
        seen.add(n.source_job_id)
        _store(db, src, n, now, out)
    if fetched.complete:
        q = select(DiscoveredJob).where(DiscoveredJob.board_source_id == src.id,
                                        DiscoveredJob.user_id == user_id)  # fmt: skip
        if seen:
            q = q.where(DiscoveredJob.source_job_id.not_in(seen))
        for row in db.scalars(q):
            if not row.stale:
                row.stale, row.stale_reason, row.stale_since = True, NO_LONGER_LISTED, now
                out["no_longer_listed"] += 1
    src.last_success_at, src.last_status, src.last_error_code = now, "ok", None
    src.failures, src.last_count = 0, len(seen)
    src.next_allowed_at = now + timedelta(seconds=s.board_min_interval_seconds)
    db.commit()
    out["listed"] = len(seen)
    log.info("board source %s: ok (%d listed, complete=%s)", src.id, len(seen), fetched.complete)
    return out


def _store(db: Session, src: BoardSource, n: NormalizedJob, now, out: dict) -> None:
    row = db.scalar(select(DiscoveredJob).where(
        DiscoveredJob.user_id == src.user_id, DiscoveredJob.provider == n.source_provider,
        DiscoveredJob.source_job_id == n.source_job_id))  # fmt: skip
    if row is not None and row.status == "dismissed":
        return  # you deleted it: it stays deleted
    if row is None:
        row = DiscoveredJob(user_id=src.user_id, board_source_id=src.id,
                            provider=n.source_provider, source_job_id=n.source_job_id,
                            first_seen_at=now, changed_fields=[], status="listed")  # fmt: skip
        db.add(row)
        out["new"] += 1
    elif row.fingerprint != n.raw_fingerprint:
        old, new = row.normalized or {}, n.as_dict()
        row.changed_fields = [k for k in COMPARED if old.get(k) != new.get(k)]
        row.changed_at = now
        out["changed"] += 1
    if row.stale and row.stale_reason == NO_LONGER_LISTED:
        row.stale, row.stale_reason, row.stale_since = False, None, None
        out["listed_again"] += 1
    row.fingerprint = n.raw_fingerprint
    row.source_facts = n.source_facts
    row.raw_ref = {"provider": n.source_provider, "source_job_id": n.source_job_id,
                   "fingerprint": n.raw_fingerprint, "fields": n.raw_keys}  # fmt: skip
    row.last_seen_at = row.imported_at = now
    if row.job_id is None:
        job, basis = _existing_job(db, src.user_id, n)
        if job is not None:  # reconciled with a job you already have; nothing new is added
            row.job_id, row.link_basis, row.status = job.id, basis, "linked"
    if row.job_id is not None:
        out["in_your_jobs"] += 1
    row.normalized = n.as_dict()
    db.flush()


def _normalized(row: DiscoveredJob) -> NormalizedJob:
    d = dict(row.normalized or {})
    d["published_on"] = date.fromisoformat(d["published_on"]) if d.get("published_on") else None
    d["missing"] = list(d.get("missing") or [])
    return NormalizedJob(**d)


def save(db: Session, user_id, row_id) -> dict:
    """Add one posting to your jobs (or link it to the job you already have). Never more."""
    row = db.scalar(
        select(DiscoveredJob)
        .where(DiscoveredJob.id == row_id, DiscoveredJob.user_id == user_id,
               DiscoveredJob.board_source_id.is_not(None))
        .with_for_update()
    )  # fmt: skip
    if row is None or row.status == "dismissed":
        raise LookupError
    if row.job_id is not None:
        return {"job_id": str(row.job_id), "outcome": "already_in_your_jobs"}
    n = _normalized(row)
    outcome = _link(db, user_id, row, n, ImportResult())
    if row.job_id is None:
        db.rollback()
        raise Refused("posting_incomplete", "This posting lacks what a job needs (a usable "
                      "link, title and employer); add it by hand from the Jobs page.")  # fmt: skip
    row.status = "linked"
    row.normalized = n.as_dict()
    db.commit()
    return {"job_id": str(row.job_id), "outcome": "added" if outcome == "new" else "linked"}
