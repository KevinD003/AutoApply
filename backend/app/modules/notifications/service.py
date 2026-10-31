"""In-app notifications (priority C, D83): what happened to your applications while you were not
watching, derived every time from the records that are the truth, so a notification can never
say more than they do, and changes when they change.

One notification per record, by a key that names it:
  * `checkpoint:<id>:<round>`: a form asked for a verification code (one per request round;
    a rejected code opens a new round). It needs you while it is open and not expired;
    `checkpoint:<id>:<round>:ended` when it expired or failed;
  * `approval:<id>`: an approval stopped applying (the package or the execution method
    changed). Not when you revoked it, and not when an outcome used it up: that outcome has
    its own notification;
  * `rehearsal:<id>`: a rehearsal completed; nothing was submitted;
  * `attempt:<id>`: a submission ended with an employer receipt, an unknown outcome, a refusal,
    or a stop. Not a rehearsal (its own notification) and not one you cancelled;
  * `follow_up:<id>:<day>`: following up on a submitted application is due (followups/service.py);
    a new day (after you followed up, or a day you chose) is a new notification;
  * `board:<source id>:<day>`: a job board you added listed postings new to you that day (UTC),
    first seen after the board's first successful read (D96); the last 30 days. It concerns no
    application and asks nothing of you.
Read marks (models.NotificationRead) are the only stored state. Nothing here sends anything:
no email, text message, push or any other delivery outside this app."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.applications.models import Application
from app.modules.discovery.models import BoardSource, DiscoveredJob
from app.modules.execution import rehearsal
from app.modules.execution.models import (
    AttemptState,
    Checkpoint,
    ExecutionAttempt,
    RehearsalRecord,
)
from app.modules.execution.service import RETIRED
from app.modules.followups import service as followups
from app.modules.jobs.models import Job
from app.modules.notifications.models import NotificationRead
from app.modules.preparation.models import ApprovalScope, PackageApproval
from app.modules.preparation.package import REVOKED_BY_YOU
from app.modules.providers import wording

# Approvals that ended by your own action, or were used up by an outcome notified on its own.
_NOT_NEWS = {REVOKED_BY_YOU, *RETIRED.values()}

# Same wording as the application page (components/ExecutionCard.tsx).
_ATTEMPT = {
    AttemptState.confirmed: ("receipt", "Employer receipt received", False),
    AttemptState.unknown: ("failure", "Outcome unknown — check before doing anything", True),
    AttemptState.rejected: (
        "failure",
        "Form rejected: the employer's form refused the submission",
        True,
    ),
    AttemptState.failed_safe: ("failure", "Stopped before sending anything", False),
    AttemptState.abandoned: ("failure", "Stopped after entering data, not submitted", True),
}
_UNKNOWN_NOTE = (
    "It is never sent again automatically: check with the employer, then record what happened "
    "on the application."
)
_REVOKED = {
    "withdrawn_by_user": "You withdrew it, so it no longer counts before a first submission.",
    "evidence_deleted": "Its evidence was deleted, so it no longer counts before a first "
    "submission.",
}


def _item(key, kind, at, app_id, title, text, *, needs_action=False, evidence=None,
          link=None) -> dict:  # fmt: skip
    return {
        "key": key,
        "kind": kind,
        "at": at,
        "application_id": str(app_id) if app_id is not None else None,
        "title": title,
        "text": text,
        "needs_action": needs_action,
        "evidence_label": evidence,
        "link": link or f"/applications/{app_id}",
    }


def _checkpoints(db: Session, user_id, now: datetime) -> list[dict]:
    out = []
    for c in db.scalars(select(Checkpoint).where(Checkpoint.user_id == user_id)):
        key = f"checkpoint:{c.id}:{c.round}"
        expired = c.status == "expired" or (
            c.status in ("open", "submitted") and c.expires_at <= now
        )
        if expired or c.status == "failed":
            text = (
                "The verification code request expired. Nothing more is sent for it."
                if expired
                else "The verification code was refused too many times. Nothing more is sent "
                "for it."
            )
            out.append(_item(f"{key}:ended", "checkpoint", c.expires_at if expired else
                             c.created_at, c.application_id, "Verification not completed",
                             text))  # fmt: skip
            continue
        if c.status == "open":
            text = (
                "The form asked for a verification code sent to you"
                + (" again: it rejected the last one" if c.round > 1 else "")
                + ". Enter it on the application before it expires."
            )
        elif c.status == "done":
            text = "The verification code was accepted."
        else:  # submitted, consumed: yours, on its way
            text = "Your code was passed on; waiting for the form's answer."
        out.append(_item(key, "checkpoint", c.created_at, c.application_id,
                         "Verification code requested", text,
                         needs_action=c.status == "open"))  # fmt: skip
    return out


def _approvals(db: Session, user_id) -> list[dict]:
    out = []
    for a in db.scalars(
        select(PackageApproval).where(
            PackageApproval.user_id == user_id, PackageApproval.invalidated_at.is_not(None)
        )
    ):
        if a.invalidation_reason in _NOT_NEWS:
            continue
        what = "rehearse" if a.scope == ApprovalScope.disclose_only else "submit"
        text = (
            f"{a.invalidation_reason or 'It no longer matches the package'}. Nothing is sent "
            "under it; review the application and approve again if you still want to go ahead."
        )
        out.append(_item(f"approval:{a.id}", "approval_invalidated", a.invalidated_at,
                         a.application_id, f"Your approval to {what} no longer applies", text,
                         needs_action=True))  # fmt: skip
    return out


def _rehearsals(db: Session, user_id) -> list[dict]:
    out = []
    for r in db.scalars(select(RehearsalRecord).where(RehearsalRecord.user_id == user_id)):
        text = (
            "The form was filled, uploaded and checked, then stopped before the submit step: "
            "nothing was submitted. Approve again to submit."
        )
        if r.revoked_at is not None:
            text += " " + _REVOKED.get(r.revoked_reason or "", "It no longer counts.")
        evidence = "fixture" if r.destination_class == "fixture" else "rehearsal"
        out.append(_item(f"rehearsal:{r.id}", "rehearsal", r.recorded_at, r.application_id,
                         "Rehearsal completed: nothing was submitted", text,
                         evidence=wording.EVIDENCE_CLASS_LABELS[evidence]))  # fmt: skip
    return out


def _attempts(db: Session, user_id) -> list[dict]:
    out = []
    for a in db.scalars(
        select(ExecutionAttempt).where(
            ExecutionAttempt.user_id == user_id,
            ExecutionAttempt.state.in_([s.value for s in _ATTEMPT]),
        )
    ):
        kind, title, needs_action = _ATTEMPT[AttemptState(a.state)]
        text = a.outcome_detail or title
        if a.state == AttemptState.unknown:
            text = f"{text} {_UNKNOWN_NOTE}"
        label = wording.EVIDENCE_CLASS_LABELS.get(rehearsal.evidence_class(a) or "")
        out.append(_item(f"attempt:{a.id}", kind, a.finished_at or a.created_at,
                         a.application_id, title, text, needs_action=needs_action,
                         evidence=label))  # fmt: skip
    return out


def _follow_ups(db: Session, user_id) -> list[dict]:
    out = []
    for f in followups.for_user(db, user_id):  # its own day (followups.today), as on its page
        if f["status"] != "due":
            continue
        out.append(
            _item(
                f"follow_up:{f['application_id']}:{f['due_on'].isoformat()}",
                "follow_up",
                followups.due_at(f),
                f["application_id"],
                "Time to follow up",
                "You applied on "
                f"{f['submitted_on'].isoformat()}. The application page has a message you can "
                "copy; NoEfforts sends nothing itself.",
                needs_action=True,
            )
        )
    return out


def _boards(db: Session, user_id, now: datetime) -> list[dict]:
    rows = db.execute(
        select(BoardSource.id, BoardSource.employer, BoardSource.provider,
               DiscoveredJob.first_seen_at)
        .join(DiscoveredJob, DiscoveredJob.board_source_id == BoardSource.id)
        .where(BoardSource.user_id == user_id, DiscoveredJob.user_id == user_id,
               BoardSource.baseline_at.is_not(None),
               DiscoveredJob.first_seen_at > BoardSource.baseline_at,
               DiscoveredJob.first_seen_at > now - timedelta(days=30),
               DiscoveredJob.status != "dismissed")
    ).all()  # fmt: skip
    days: dict[tuple, list] = {}
    for sid, employer, provider, seen in rows:
        days.setdefault((sid, seen.astimezone(UTC).date()), [employer, provider, []])[2].append(
            seen
        )
    out = []
    for (sid, day), (employer, provider, seen) in days.items():
        n = len(seen)
        item = _item(
            f"board:{sid}:{day.isoformat()}", "board_postings", max(seen), None,
            "New postings on a job board you added",
            f"{n} new posting{'s' if n != 1 else ''} on the {provider.title()} job board you"
            " added. They are in Discover; none was added to your jobs.",
            link="/discover",
        )  # fmt: skip
        item["job"] = employer
        out.append(item)
    return out


def feed(db: Session, user_id, now: datetime | None = None) -> list[dict]:
    """Every notification of the account, newest first, each with its read mark and the job
    it concerns. Scoped to the account in every query."""
    now = now or utcnow()
    items = (
        _checkpoints(db, user_id, now)
        + _approvals(db, user_id)
        + _rehearsals(db, user_id)
        + _attempts(db, user_id)
        + _follow_ups(db, user_id)
        + _boards(db, user_id, now)
    )
    read = set(
        db.scalars(select(NotificationRead.item_key).where(NotificationRead.user_id == user_id))
    )
    jobs = {}
    if any(i["application_id"] for i in items):
        rows = db.execute(
            select(Application.id, Job.title, Job.employer)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.user_id == user_id,
                Application.id.in_({i["application_id"] for i in items if i["application_id"]}),
            )
        )
        jobs = {str(app_id): (title, employer) for app_id, title, employer in rows}
    for i in items:
        if i["application_id"] is None:  # a board's postings: `job` names the employer you gave
            i["read"] = i["key"] in read
            continue
        title, employer = jobs.get(i["application_id"], (None, None))
        i["job"] = " — ".join(x for x in (title or "Untitled role", employer) if x)
        i["read"] = i["key"] in read
    return sorted(items, key=lambda i: (i["at"], i["key"]), reverse=True)


def unread(items: list[dict]) -> int:
    return sum(1 for i in items if not i["read"])
