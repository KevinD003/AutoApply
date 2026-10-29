"""Account deletion (priority B, D77): everything that names the account, in one transaction.

Every table that names an account references `users` with ON DELETE CASCADE (tested), so
deleting the user row deletes the profile, facts, documents, jobs, applications, packages,
approvals, attempts, evidence, events, watches, sessions and audit events with it. Document files
are removed after the commit, as document deletion does (a failed commit keeps rows and files).

Queued and running work, in the execution lock order (attempt, then application;
execution/service.py):
  * the account's watches are locked first, so a watch check in progress finishes (and a new one
    skips them) before anything is deleted;
  * every active attempt, then every application, is locked: a gate holding one is waited for;
  * an attempt past the send gate (`sending`, `awaiting_code`) may be in flight: deletion is
    refused until its outcome is known, as cancel and revoke are, and nothing is deleted;
  * an attempt not yet claimed is deleted with its outbox message; a queued message that still
    reaches a worker finds no attempt and does nothing (`claim` returns None);
  * an attempt a worker holds before the send gate is deleted too; the worker's next fenced
    write finds no row (LostAuthority), so it never reaches the send gate. What it had already
    entered on the page stays entered there, as after a cancel.
Sessions go with the account, so access ends with the commit.

What is kept, and what deletion cannot reach, is policy.py's (the owner's decision)."""

import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import Base
from app.modules.applications.models import Application
from app.modules.applications.states import AppState
from app.modules.discovery.models import DiscoveryWatch
from app.modules.documents.models import Document
from app.modules.documents.storage import Storage
from app.modules.execution.models import ACTIVE, AttemptState, ExecutionAttempt
from app.modules.identity.models import User

log = logging.getLogger("noefforts.account")
DEADLOCK = "40P01"

# Why a deletion is refused: fixed codes, shown after the message ("(reason: code)").
# docs/account-deletion.md lists exactly these.
REASONS = {
    "deletion_submission_in_flight": "A submission may be in flight, so your account cannot be "
    "deleted yet. Wait for its outcome (or reconcile it in the tracker), then delete.",
    "deletion_busy": "Something else changed your account while it was being deleted. Nothing "
    "was deleted; try again.",
    "deletion_unconfirmed": 'Type "delete my account" to confirm. Nothing was deleted.',
    "deletion_password": "That is not your password. Nothing was deleted.",
}
IN_FLIGHT = (AttemptState.sending, AttemptState.awaiting_code)
SUBMITTED = (
    AppState.submitted_unconfirmed,
    AppState.submitted_confirmed,
)


def refusal(code: str) -> str:
    return f"{REASONS[code]} (reason: {code})"


class DeletionRefused(Exception):
    def __init__(self, code: str):
        super().__init__(refusal(code))
        self.code = code


def _count(db: Session, table: str, user_id: uuid.UUID) -> int:
    t = Base.metadata.tables[table]
    return db.scalar(select(func.count()).select_from(t).where(t.c.user_id == user_id)) or 0


def preview(db: Session, user_id: uuid.UUID) -> dict:
    """What deleting would remove (counts), what blocks it now, and what was already sent."""
    in_flight = db.scalar(
        select(func.count())
        .select_from(ExecutionAttempt)
        .where(ExecutionAttempt.user_id == user_id, ExecutionAttempt.state.in_(IN_FLIGHT))
    )
    sent = db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user_id, Application.state.in_(SUBMITTED))
    )
    return {
        "counts": {
            "jobs": _count(db, "jobs", user_id),
            "applications": _count(db, "applications", user_id),
            "documents": _count(db, "documents", user_id),
            "saved_answers": _count(db, "answer_bank", user_id),
            "watches": _count(db, "discovery_watches", user_id),
        },
        "submitted_applications": sent or 0,
        "blocked_by": ["deletion_submission_in_flight"] if in_flight else [],
    }


def _lock_and_check(db: Session, user_id: uuid.UUID) -> list[str]:
    db.execute(
        select(DiscoveryWatch.id)
        .where(DiscoveryWatch.user_id == user_id)
        .order_by(DiscoveryWatch.id)
        .with_for_update()
    )
    attempts = db.scalars(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.user_id == user_id, ExecutionAttempt.state.in_(ACTIVE))
        .order_by(ExecutionAttempt.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    db.execute(
        select(Application.id)
        .where(Application.user_id == user_id)
        .order_by(Application.id)
        .with_for_update()
    )
    if any(a.state in IN_FLIGHT for a in attempts):
        raise DeletionRefused("deletion_submission_in_flight")
    return list(db.scalars(select(Document.storage_key).where(Document.user_id == user_id)).all())


def delete_account(db: Session, user_id: uuid.UUID, storage: Storage) -> int:
    """Deletes the account and everything that names it; returns how many document files were
    removed. Refused (DeletionRefused, nothing changed) while a submission may be in flight.
    A deadlock with a concurrent write is retried once from the start; a second one is refused
    (`deletion_busy`)."""
    for tried in (1, 2):
        try:
            keys = _lock_and_check(db, user_id)
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
            break
        except DeletionRefused:
            db.rollback()
            raise
        except DBAPIError as e:
            db.rollback()
            if getattr(e.orig, "sqlstate", None) != DEADLOCK:
                raise
            if tried == 2:
                raise DeletionRefused("deletion_busy") from None
    removed = 0
    for key in keys:  # after the commit: a failed commit keeps both the rows and the files
        try:
            storage.delete(key)
            removed += 1
        except (OSError, ValueError) as e:
            log.warning("document file not removed: %s", type(e).__name__)
    log.info("account deleted: %d document file(s) removed", removed)
    return removed
