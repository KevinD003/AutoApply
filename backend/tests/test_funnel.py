"""The per-user funnel (S2, D53): counts computed at read time from the user's own states and
events, never stored, never compared across users, never an outcome. "Submitted" in these
tests comes from the receiver's ledger (the employer's side), never from this view. Synthetic
data and the local receiver only."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Row

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.applications.models import ApplicationEvent
from app.modules.applications.states import Actor, AppState, Outcome
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import ExecutionAttempt
from tests.execution_harness import Receiver, prepared_application, queue

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
EVIDENCE = "Confirmation email REF-1 arrived"  # synthetic


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


# -- pure ----------------------------------------------------------------------------------------


def _app(i, state, outcome=Outcome.none, changed=NOW):
    return Row(id=i, state=state, outcome=outcome, state_changed_at=changed)


def _entry(i, to, actor, source=None, at=NOW - timedelta(days=2), frm=None):
    return Row(
        application_id=i,
        kind="state_change",
        from_state=frm,
        to_state=to,
        actor=actor,
        source=source,
        from_outcome=None,
        to_outcome=None,
        created_at=at,
    )


def _exit(i, frm, to, at):
    return Row(
        application_id=i,
        kind="state_change",
        from_state=frm,
        to_state=to,
        actor=Actor.system,
        source=None,
        from_outcome=None,
        to_outcome=None,
        created_at=at,
    )


def _change(i, frm, to, at):
    return Row(
        application_id=i,
        kind="outcome",
        from_state=None,
        to_state=None,
        actor=Actor.user,
        source="user_reported",
        from_outcome=frm,
        to_outcome=to,
        created_at=at,
    )


def _path(i, *outcomes, start=NOW - timedelta(days=1)):
    rows, prev = [], Outcome.none
    for k, o in enumerate(outcomes):
        rows.append(_change(i, prev, o, start + timedelta(minutes=k)))
        prev = o
    return rows


def _compute(apps, events=(), receipts=(), **sets):
    from app.modules.applications.funnel import compute

    base = dict(prepared=set(), approved=set(), disclosed=set(), form_rejected=set())
    return compute(apps, receipts=set(receipts), events=list(events), now=NOW, **(base | sets))


def _stage(f, name):
    (s,) = [s for s in f["stages"] if s["stage"] == name]
    return s


def test_reached_stages_count_what_was_recorded_and_never_infer_one():
    S, O = AppState, Outcome  # noqa: E741 (as Outcome)
    apps = [
        _app("A", S.submitted_confirmed, O.rejected),
        _app("B", S.submitted_confirmed, O.offer),
        _app("C", S.submitted_unconfirmed),
        _app("D", S.draft, O.interviewing),
        _app("E", S.draft, O.withdrawn),
    ]
    events = [
        _entry("A", S.submitted_confirmed, Actor.worker, "receipt"),
        *_path("A", O.interviewing, O.rejected),
        _entry("B", S.submitted_unconfirmed, Actor.user, "user_claimed"),
        _entry("B", S.submitted_confirmed, Actor.user, "user_claimed"),
        *_path("B", O.offer),
        _entry("C", S.submitted_unconfirmed, Actor.worker),
        *_path("C", O.interviewing, O.none),
        *_path("E", O.withdrawn),
    ]
    f = _compute(apps, sorted(events, key=lambda e: e.created_at), receipts={"A"})
    assert (_stage(f, "interviewing")["count"], _stage(f, "rejected")["count"]) == (1, 1)
    assert (_stage(f, "offer")["count"], _stage(f, "responded")["count"]) == (1, 2)
    assert _stage(f, "interviewing")["of"] == 3  # of submitted: B's offer implies no interview
    assert f["outcome_before_submission"] == 1  # D: recorded before S2, in no stage
    w = _stage(f, "withdrawn_before_submission")
    assert (w["count"], w["of"], w["of_stage"]) == (1, 5, "tracked")
    assert _stage(f, "withdrawn")["count"] == 0
    assert f["tracked"] == 5
    assert f["submitted"] == {
        "total": 3,
        "receipt": 1,
        "user_claimed": 1,
        "unconfirmed": 1,
        "confirmed_by_you": 1,
        "applied_by_you": 0,
    }


def test_a_change_to_none_takes_back_only_the_value_it_replaced():
    from app.modules.applications.funnel import reached

    O = Outcome  # noqa: E741 (as Outcome)
    path = _path("A", O.assessment_received, O.interviewing, O.offer, O.none)
    assert reached(O.none, path) == {O.assessment_received, O.interviewing}
    amend = [*_path("A", O.interviewing), _change("A", O.interviewing, O.interviewing, NOW)]
    assert reached(O.interviewing, amend) == {O.interviewing}
    legacy = [Row(**{**vars(_change("A", None, None, NOW))})]  # before S2: no typed values
    assert reached(O.none, legacy) == set()
    # Review finding: an outcome recorded before S2 stays recorded when the next one is typed.
    later = [*legacy, _change("A", O.interviewing, O.rejected, NOW)]
    assert reached(O.rejected, later) == {O.interviewing, O.rejected}
    gone = [*legacy, _change("A", O.interviewing, O.withdrawn, NOW)]
    f = _compute(
        [_app("A", AppState.submitted_confirmed, O.withdrawn)],
        [_entry("A", AppState.submitted_confirmed, Actor.worker, "receipt"), *gone],
        receipts={"A"},
    )
    assert (_stage(f, "responded")["count"], _stage(f, "withdrawn")["count"]) == (1, 1)
    f = _compute(
        [_app("A", AppState.submitted_confirmed, changed=NOW - timedelta(days=30))],
        [
            _entry(
                "A",
                AppState.submitted_confirmed,
                Actor.worker,
                "receipt",
                at=NOW - timedelta(days=30),
            ),
            *path,
        ],
        receipts={"A"},
    )
    assert _stage(f, "no_response_yet")["count"] == 0  # responses were recorded, then cleared


def test_no_response_yet_is_computed_from_the_current_submission_and_never_stored():
    S = AppState

    def waiting(days, outcome=Outcome.none, extra=()):
        a = _app("A", S.submitted_confirmed, outcome, changed=NOW - timedelta(days=1))
        e = [
            _entry("A", S.submitted_unconfirmed, Actor.worker, at=NOW - timedelta(days=days)),
            _entry(
                "A", S.submitted_confirmed, Actor.user, "user_claimed", at=NOW - timedelta(days=1)
            ),
            *extra,
        ]
        f = _compute([a], sorted(e, key=lambda r: r.created_at))
        return _stage(f, "no_response_yet")["count"], _stage(f, "no_response")["count"]

    assert waiting(30) == (1, 0)
    assert waiting(20) == (0, 0)
    assert waiting(21) == (1, 0)
    assert waiting(30, Outcome.no_response) == (0, 1)
    assert waiting(30, Outcome.interviewing, _path("A", Outcome.interviewing)) == (0, 0)
    # Reconciled as not received, sent again and confirmed 5 days ago: the wait starts again.
    a = _app("A", S.submitted_confirmed, changed=NOW - timedelta(days=5))
    e = [
        _entry("A", S.submitted_unconfirmed, Actor.worker, at=NOW - timedelta(days=40)),
        _exit("A", S.submitted_unconfirmed, S.failed_retryable, NOW - timedelta(days=35)),
        _entry(
            "A",
            S.submitted_confirmed,
            Actor.worker,
            "receipt",
            at=NOW - timedelta(days=5),
            frm=S.submitting,
        ),
    ]
    assert _stage(_compute([a], e, receipts={"A"}), "no_response_yet")["count"] == 0


def test_fewer_than_twenty_submissions_are_too_few_to_compare():
    from app.modules.applications.router import FunnelOut

    def funnel(n, responses):
        apps = [
            _app(
                i,
                AppState.submitted_unconfirmed,
                Outcome.interviewing if i < responses else Outcome.none,
            )
            for i in range(n)
        ]
        events = [
            _entry(i, AppState.submitted_unconfirmed, Actor.user, "user_claimed") for i in range(n)
        ]
        return _compute(apps, events)

    f = funnel(0, 0)
    assert (f["note"], f["too_few_to_compare"]) == ("No submissions yet.", True)
    assert funnel(1, 1)["note"] == "1 submission is too few to compare rates; 1 response so far."
    assert (
        funnel(19, 6)["note"] == "19 submissions is too few to compare rates; 6 responses so far."
    )
    f = funnel(20, 6)
    assert (f["note"], f["too_few_to_compare"]) == (None, False)
    assert set(f) == set(FunnelOut.model_fields)  # counts and denominators only: no rate
    assert not [k for k in f if "rate" in k or "pct" in k or "percent" in k]


def test_sources_follow_receipts_and_who_made_the_move():
    from app.modules.applications.states import Basis, claimed_by_user, submission_basis

    S = AppState
    table = [
        ((S.submitted_confirmed, True, False), Basis.receipt),
        ((S.submitted_confirmed, False, False), Basis.user_claimed),
        ((S.submitted_unconfirmed, False, True), Basis.user_claimed),
        ((S.submitted_unconfirmed, False, False), Basis.unconfirmed),
        ((S.submitted_unconfirmed, True, False), Basis.receipt),
        ((S.failed_retryable, True, False), Basis.receipt),
        ((S.draft, False, False), None),
    ]
    for args, want in table:
        assert submission_basis(*args) == want, args
    assert claimed_by_user("user_claimed", Actor.worker) is True
    assert claimed_by_user(None, Actor.user) is True  # before S2: the recorded actor decides
    assert claimed_by_user(None, Actor.worker) is False
    assert claimed_by_user(None, Actor.system) is False


# -- through the API, with the receiver's ledger as the oracle ------------------------------------


def _funnel(api):
    r = api.get("/applications/funnel")
    assert r.status_code == 200, r.text
    return r.json()


def _gen(aid) -> int:
    with SessionLocal() as db:
        return db.get(ExecutionAttempt, uuid.UUID(aid)).generation


def _into_confirmed(app_id):
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(ApplicationEvent).where(
                    ApplicationEvent.application_id == uuid.UUID(app_id),
                    ApplicationEvent.to_state == AppState.submitted_confirmed,
                )
            )
        )


def test_a_receipt_confirmed_submission_counts_once_and_matches_the_ledger(
    api, other_api, receiver
):
    """R14.5."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    f = _funnel(api)
    assert f["submitted"] == {
        "total": 1,
        "receipt": 1,
        "user_claimed": 0,
        "unconfirmed": 0,
        "confirmed_by_you": 0,
        "applied_by_you": 0,
    }
    for name in ("prepared", "approved", "disclosed"):
        assert (_stage(f, name)["count"], _stage(f, name)["of"]) == (1, 1), name
    assert (_stage(f, "form_rejected")["count"], _stage(f, "form_rejected")["of"]) == (0, 1)
    got = api.get(f"/applications/{app_id}").json()
    assert got["submission"] == "receipt"
    (e,) = [e for e in got["events"] if e["to_state"] == "submitted_confirmed"]
    assert (e["actor"], e["source"]) == ("worker", "receipt")
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert _funnel(api) == f and receiver.ledger()["accepted"] == 1
    assert _funnel(other_api)["tracked"] == 0


def test_an_unknown_outcome_is_unconfirmed_until_confirmed_and_a_receipt_outranks_a_claim(
    api, receiver
):
    receiver.config(mode="drop_after_accept")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1
    f = _funnel(api)
    assert (f["submitted"]["total"], f["submitted"]["unconfirmed"]) == (1, 1)
    r = api.post(
        f"/applications/{app_id}/reconcile", json={"finding": "received", "evidence": EVIDENCE}
    )
    assert r.status_code == 200 and r.json()["events"][-1]["source"] == "user_claimed"
    f = _funnel(api)
    assert (f["submitted"]["user_claimed"], f["submitted"]["confirmed_by_you"]) == (1, 1)
    assert svc.confirmed(uuid.UUID(aid), "w1", _gen(aid), [])  # the slow worker's late receipt
    f = _funnel(api)
    assert (f["submitted"]["receipt"], f["submitted"]["user_claimed"]) == (1, 0)
    assert f["submitted"]["total"] == receiver.ledger()["accepted"] == 1
    (only,) = _into_confirmed(app_id)  # the user's statement; the receipt is on the attempt
    assert (only.actor, only.source) == (Actor.user, "user_claimed")


def test_a_receipt_recorded_while_quarantined_counts_as_a_receipt(api, receiver):
    receiver.config(mode="drop_after_accept")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert svc.confirmed(uuid.UUID(aid), "w1", _gen(aid), [])
    got = api.get(f"/applications/{app_id}").json()
    assert got["state"] == "submitted_unconfirmed" and got["submission"] == "receipt"
    f = _funnel(api)
    assert (f["submitted"]["receipt"], f["submitted"]["unconfirmed"]) == (1, 0)
    r = api.post(
        f"/applications/{app_id}/reconcile", json={"finding": "received", "evidence": EVIDENCE}
    )
    assert (
        r.json()["submission"] == "receipt" and r.json()["events"][-1]["source"] == "user_claimed"
    )
    assert receiver.ledger()["accepted"] == 1


def _applied(api) -> str:
    job = api.post("/jobs", json={"title": "Baker", "employer": "Bread Co"}).json()["job"]
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    r = api.post(f"/applications/{app_id}/transition", json={"to": "submitted_unconfirmed"})
    assert r.status_code == 200, r.text
    return app_id


def test_applied_by_hand_is_user_claimed_and_never_a_receipt(api, receiver):
    app_id = _applied(api)
    f = _funnel(api)
    assert (
        f["submitted"]["total"],
        f["submitted"]["user_claimed"],
        f["submitted"]["applied_by_you"],
    ) == (1, 1, 1)
    assert f["submitted"]["receipt"] == 0 and _stage(f, "prepared")["count"] == 0
    assert receiver.ledger()["accepted"] == 0
    r = api.post(
        f"/applications/{app_id}/transition",
        json={"to": "submitted_confirmed", "evidence": EVIDENCE},
    )
    assert r.status_code == 200, r.text
    s = _funnel(api)["submitted"]
    assert (s["confirmed_by_you"], s["applied_by_you"]) == (1, 0)


def test_form_rejected_is_not_employer_declined(api, receiver):
    receiver.config(mode="validation_fail")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "rejected"
    assert receiver.ledger()["accepted"] == 0
    assert api.get(f"/applications/{app_id}").json()["state"] == "failed_terminal"
    f = _funnel(api)
    fr = _stage(f, "form_rejected")
    assert (fr["count"], fr["of"], fr["of_stage"]) == (1, 1, "disclosed")
    assert _stage(f, "rejected")["count"] == 0 and f["submitted"]["total"] == 0
    r = api.patch(f"/applications/{app_id}", json={"outcome": "rejected"})
    assert r.status_code == 400 and r.json()["detail"].endswith(
        "(reason: outcome_before_submission)"
    )
    assert api.patch(f"/applications/{app_id}", json={"outcome": "withdrawn"}).status_code == 200
    w = _stage(_funnel(api), "withdrawn_before_submission")
    assert (w["count"], w["of"]) == (1, 1)


def test_outcome_history_and_the_funnel_are_per_user(api, other_api):
    """R13: another user can neither read nor change an application's outcome history, and
    each funnel counts only its owner's applications."""
    app_id = _applied(api)
    assert (
        api.post(
            f"/applications/{app_id}/transition",
            json={"to": "submitted_confirmed", "evidence": EVIDENCE},
        ).status_code
        == 200
    )
    assert api.patch(f"/applications/{app_id}", json={"outcome": "interviewing"}).status_code == 200
    before = api.get(f"/applications/{app_id}").json()
    audited = _audit_count()
    assert other_api.get(f"/applications/{app_id}").status_code == 404
    assert other_api.patch(f"/applications/{app_id}", json={"outcome": "offer"}).status_code == 404
    assert (
        other_api.post(
            f"/applications/{app_id}/transition",
            json={"to": "submitted_confirmed", "evidence": EVIDENCE},
        ).status_code
        == 404
    )
    assert (
        other_api.post(
            f"/applications/{app_id}/reconcile", json={"finding": "received", "evidence": EVIDENCE}
        ).status_code
        == 404
    )
    theirs = _funnel(other_api)
    assert theirs["tracked"] == 0 and all(s["count"] == 0 for s in theirs["stages"])
    mine = _funnel(api)
    assert mine["tracked"] == 1
    assert (_stage(mine, "interviewing")["count"], _stage(mine, "interviewing")["of"]) == (1, 1)
    assert api.get(f"/applications/{app_id}").json() == before
    assert _audit_count() == audited  # the refused calls wrote nothing, for either user


def _audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(AuditEvent))


def test_reading_the_funnel_writes_nothing(api):
    _applied(api)

    def counts():
        with SessionLocal() as db:
            return (
                db.scalar(select(func.count()).select_from(ApplicationEvent)),
                db.scalar(select(func.count()).select_from(AuditEvent)),
            )

    before = counts()
    f1, f2 = _funnel(api), _funnel(api)
    assert counts() == before and f1 == f2
    assert _stage(f1, "no_response")["count"] == 0
    assert api.get("/applications").json()[0]["outcome"] == "none"


def test_the_funnel_route_is_matched_before_an_application_id(api):
    f = _funnel(api)
    assert f["tracked"] == 0 and f["note"] == "No submissions yet."
    assert api.get("/applications/not-a-uuid").status_code == 422
