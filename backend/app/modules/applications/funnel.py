"""Per-user funnel (S2, D53): counts computed when read, from the user's own application states
and events, packages, approvals and attempts. Never stored, never compared across users, never
an outcome, and never a rate. Tests take "submitted" from the receiver's ledger, never from this
view."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.modules.applications import states
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.states import AppState, Basis, Outcome
from app.modules.execution.models import AttemptState, ExecutionAttempt
from app.modules.preparation.models import ApplicationPackage, PackageApproval

MIN_SUBMISSIONS_TO_COMPARE = 20
NO_RESPONSE_AFTER_DAYS = 21
STAGED = (Outcome.assessment_received, Outcome.interviewing, Outcome.offer, Outcome.rejected)


def for_user(db: Session, user_id, now: datetime) -> dict:
    A, E, X = Application, ApplicationEvent, ExecutionAttempt
    apps = db.execute(
        select(A.id, A.state, A.outcome, A.state_changed_at).where(A.user_id == user_id)
    ).all()

    def ids(model, *conds) -> set:
        return set(
            db.scalars(
                select(model.application_id)
                .join(A, A.id == model.application_id)
                .where(A.user_id == user_id, model.user_id == user_id, *conds)
                .distinct()
            )
        )

    events = db.execute(
        select(
            E.application_id,
            E.kind,
            E.from_state,
            E.to_state,
            E.actor,
            E.source,
            E.from_outcome,
            E.to_outcome,
            E.created_at,
        )  # fmt: skip
        .join(A, A.id == E.application_id)
        .where(
            A.user_id == user_id,
            or_(
                E.kind == "outcome",
                and_(
                    E.kind == "state_change",
                    or_(E.to_state.in_(states.SUBMITTED), E.from_state.in_(states.SUBMITTED)),
                ),
            ),
        )
        .order_by(E.created_at, E.id)
    ).all()
    return compute(
        apps,
        prepared=ids(ApplicationPackage),
        approved=ids(PackageApproval),
        disclosed=ids(X, X.disclosure_started_at.is_not(None)),
        form_rejected=ids(X, X.state == AttemptState.rejected),
        receipts=ids(X, X.state == AttemptState.confirmed),
        events=events,
        now=now,
    )


def reached(current: Outcome, changes) -> set:
    """From typed outcome changes in order, plus the current outcome. A typed change's
    from_outcome is a recorded value too (it may have been recorded before S2 typed the rows). An
    amendment (from == to) adds nothing; a change to none takes back the value it replaced;
    nothing is implied."""
    path: list[Outcome] = []
    for c in changes:
        if c.to_outcome is None or c.to_outcome == c.from_outcome:
            continue  # before S2 a change had no typed value: unknown stays unknown
        if c.to_outcome == Outcome.none:
            if c.from_outcome in path:
                del path[len(path) - 1 - path[::-1].index(c.from_outcome)]
        else:
            earlier = c.from_outcome
            if earlier not in (None, Outcome.none) and (not path or path[-1] != earlier):
                path.append(earlier)
            path.append(c.to_outcome)
    return (set(path) | {current}) - {Outcome.none}


def note(n: int, responses: int) -> str | None:
    if n == 0:
        return "No submissions yet."
    if n >= MIN_SUBMISSIONS_TO_COMPARE:
        return None
    s = "submission" if n == 1 else "submissions"
    r = "response" if responses == 1 else "responses"
    return f"{n} {s} is too few to compare rates; {responses} {r} so far."


def compute(apps, *, prepared, approved, disclosed, form_rejected, receipts, events, now) -> dict:
    """Pure. `apps`: rows (id, state, outcome, state_changed_at); `events`: rows ordered by
    created_at (outcome events, and state changes into or out of a submitted state)."""
    mine = {a.id for a in apps}
    prepared, approved, disclosed, form_rejected, receipts = (
        s & mine for s in (prepared, approved, disclosed, form_rejected, receipts)
    )
    entered: set = set()
    since: dict = {}  # the start of its current stretch in a submitted state
    last_unconfirmed: dict = {}
    changes = defaultdict(list)
    for e in events:
        if e.application_id not in mine:
            continue
        if e.kind == "state_change":
            into = e.to_state in states.SUBMITTED
            if into:
                entered.add(e.application_id)
                since.setdefault(e.application_id, e.created_at)
                if e.to_state == AppState.submitted_unconfirmed:
                    last_unconfirmed[e.application_id] = e  # the latest wins
            elif getattr(e, "from_state", None) in states.SUBMITTED:
                since.pop(e.application_id, None)  # it left: a later entry starts a new wait
        elif e.kind == "outcome":
            changes[e.application_id].append(e)

    def by_user(a) -> bool:
        e = last_unconfirmed.get(a.id)
        return e is not None and states.claimed_by_user(e.source, e.actor)

    basis = {a.id: states.submission_basis(a.state, a.id in receipts, by_user(a)) for a in apps}
    got = {a.id: reached(a.outcome, changes[a.id]) for a in apps}
    sub = [a for a in apps if basis[a.id] is not None]
    never = [a for a in apps if not states.reached_submission(a.state, a.id in entered,
                                                               a.id in receipts)]  # fmt: skip
    n, tracked = len(sub), len(apps)

    def count(pred, rows) -> int:
        return sum(1 for a in rows if pred(a))

    def waiting(a) -> bool:
        start = since.get(a.id) or (a.state_changed_at if a.state in states.SUBMITTED else None)
        return (
            a.outcome == Outcome.none
            and not got[a.id] & states.RESPONSES
            and start is not None
            and now - start >= timedelta(days=NO_RESPONSE_AFTER_DAYS)
        )

    def stage(name, c, of, of_stage) -> dict:
        return {"stage": name, "count": c, "of": of, "of_stage": of_stage}

    responded = count(lambda a: bool(got[a.id] & states.RESPONSES), sub)
    stages = [
        stage("prepared", len(prepared), tracked, "tracked"),
        stage("approved", len(approved), len(prepared), "prepared"),
        stage("disclosed", len(disclosed), len(approved), "approved"),
        stage("form_rejected", len(form_rejected), len(disclosed), "disclosed"),
        stage("submitted", n, tracked, "tracked"),
        stage("responded", responded, n, "submitted"),
        *(
            stage(o.value, count(lambda a, o=o: o in got[a.id], sub), n, "submitted")
            for o in STAGED
        ),  # fmt: skip
        stage(
            "no_response", count(lambda a: a.outcome == Outcome.no_response, sub), n, "submitted"
        ),  # fmt: skip
        stage("no_response_yet", count(waiting, sub), n, "submitted"),
        stage("withdrawn", count(lambda a: Outcome.withdrawn in got[a.id], sub), n, "submitted"),
        stage(
            "withdrawn_before_submission",
            count(lambda a: a.outcome == Outcome.withdrawn, never),
            tracked,
            "tracked",
        ),  # fmt: skip
    ]
    claimed = [a for a in sub if basis[a.id] == Basis.user_claimed]
    return {
        "tracked": tracked,
        "stages": stages,
        "submitted": {
            "total": n,
            "receipt": count(lambda a: basis[a.id] == Basis.receipt, sub),
            "user_claimed": len(claimed),
            "unconfirmed": count(lambda a: basis[a.id] == Basis.unconfirmed, sub),
            "confirmed_by_you": count(lambda a: a.state == AppState.submitted_confirmed, claimed),
            "applied_by_you": count(lambda a: a.state == AppState.submitted_unconfirmed, claimed),
        },
        "no_response_after_days": NO_RESPONSE_AFTER_DAYS,
        "min_submissions_to_compare": MIN_SUBMISSIONS_TO_COMPARE,
        "too_few_to_compare": n < MIN_SUBMISSIONS_TO_COMPARE,
        "note": note(n, responded),
        "outcome_before_submission": count(
            lambda a: a.outcome not in states.OUTCOMES_BEFORE_SUBMISSION, never
        ),
    }
