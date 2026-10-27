import pytest

from app.modules.applications.states import (
    TRANSITIONS,
    Actor,
    AppState,
    IllegalTransition,
    check,
)

EVIDENCE = "Confirmation email REF-1 arrived"  # synthetic


def _job(api):
    return api.post("/jobs", json={"title": "Baker", "employer": "Bread Co"}).json()["job"]


def test_create_is_idempotent(api):
    job = _job(api)
    a = api.post("/applications", json={"job_id": job["id"]})
    b = api.post("/applications", json={"job_id": job["id"]})
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]
    assert len(api.get("/applications").json()) == 1


def test_user_transitions_and_timeline(api):
    job = _job(api)
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    r = api.post(
        f"/applications/{app['id']}/transition",
        json={"to": "submitted_unconfirmed", "reason": "I applied on the website"},
    )
    assert r.status_code == 200
    assert r.json()["events"][-1]["source"] == "user_claimed"
    r = api.post(
        f"/applications/{app['id']}/transition",
        json={"to": "submitted_confirmed", "evidence": EVIDENCE},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "submitted_confirmed"
    e = r.json()["events"][-1]
    assert (e["actor"], e["source"], e["evidence_note"], e["reason"]) == (
        "user",
        "user_claimed",
        EVIDENCE,
        "Confirmed by you",
    )
    assert r.json()["submission"] == "user_claimed"
    r = api.patch(f"/applications/{app['id']}", json={"outcome": "interviewing"})
    kinds = [e["kind"] for e in r.json()["events"]]
    assert kinds == ["state_change", "state_change", "state_change", "outcome"]
    o = r.json()["events"][-1]
    assert (o["from_outcome"], o["to_outcome"], o["source"], o["occurred_on"]) == (
        "none",
        "interviewing",
        "user_reported",
        None,
    )
    assert o["reason"] == "outcome: none → interviewing"


def test_users_cannot_perform_worker_transitions(api):
    job = _job(api)
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    api.post(f"/applications/{app['id']}/transition", json={"to": "preparing"})
    r = api.post(f"/applications/{app['id']}/transition", json={"to": "awaiting_approval"})
    assert r.status_code == 400


def test_unknown_submission_outcome_never_auto_retries():
    for actor in Actor:
        for target in (AppState.queued, AppState.running, AppState.failed_retryable):
            with pytest.raises(IllegalTransition):
                check(AppState.submitting, target, actor)
    # Quarantine has no path back to queued for anyone; only reconciliation (system, after an
    # explicit user statement) can make it retryable, and re-queueing then needs approval.
    for actor in Actor:
        with pytest.raises(IllegalTransition):
            check(AppState.submitted_unconfirmed, AppState.queued, actor)
    with pytest.raises(IllegalTransition):
        check(AppState.submitted_unconfirmed, AppState.failed_retryable, Actor.user)
    check(AppState.submitted_unconfirmed, AppState.failed_retryable, Actor.system)
    with pytest.raises(IllegalTransition):
        check(AppState.failed_retryable, AppState.queued, Actor.system)


def test_terminal_states_have_no_exits():
    for s in (
        AppState.submitted_confirmed,
        AppState.failed_terminal,
        AppState.cancelled,
        AppState.expired,
    ):
        assert TRANSITIONS[s] == {}
    assert set(TRANSITIONS) == set(AppState)


def test_cross_tenant_application_access_denied(api, other_api):
    job = _job(api)
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    assert other_api.get(f"/applications/{app['id']}").status_code == 404
    assert (
        other_api.post(
            f"/applications/{app['id']}/transition", json={"to": "cancelled"}
        ).status_code
        == 404
    )
    assert other_api.post("/applications", json={"job_id": job["id"]}).status_code == 404


# -- S2 (D53): what a submission rests on, and outcomes the user reports -------------------------


def _new(api) -> str:
    """A new application for a new job (the same title and employer would be the same job)."""
    import uuid

    job = api.post("/jobs", json={"title": f"Baker {uuid.uuid4().hex[:8]}", "employer": "Bread Co"})
    return api.post("/applications", json={"job_id": job.json()["job"]["id"]}).json()["id"]


def _applied(api) -> str:
    """An application the user marked as applied by hand (synthetic)."""
    app_id = _new(api)
    r = api.post(
        f"/applications/{app_id}/transition",
        json={"to": "submitted_unconfirmed", "reason": "User reported a manual submission"},
    )
    assert r.status_code == 200, r.text
    return app_id


def _confirm(api, app_id, evidence=EVIDENCE):
    return api.post(
        f"/applications/{app_id}/transition",
        json={"to": "submitted_confirmed", "evidence": evidence},
    )


def _audit(action):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.audit.models import AuditEvent

    with SessionLocal() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.action == action)))


def _simulate_state(app_id, state):
    import uuid

    from app.core.db import SessionLocal
    from app.modules.applications.models import Application

    with SessionLocal() as db:  # simulated: no worker ran
        db.get(Application, uuid.UUID(app_id)).state = state
        db.commit()


def test_a_user_confirmation_needs_stated_evidence(api):
    """R6.7: confirming a submission yourself needs what you checked; the reason alone, blanks
    or a few characters are refused with a reason code, and nothing is written."""
    app_id = _applied(api)
    events = len(api.get(f"/applications/{app_id}").json()["events"])
    for body in (
        {},
        {"reason": "confirmation email"},
        {"evidence": "   short text   "},
        {"evidence": " " * 20},
    ):
        r = api.post(
            f"/applications/{app_id}/transition", json={"to": "submitted_confirmed", **body}
        )
        assert r.status_code == 400, (body, r.text)
        assert r.json()["detail"].endswith("(reason: evidence_required)"), r.text
    after = api.get(f"/applications/{app_id}").json()
    assert after["state"] == "submitted_unconfirmed" and len(after["events"]) == events
    assert not [
        a for a in _audit("application.transition") if a.meta == {"to": "submitted_confirmed"}
    ]
    assert _confirm(api, app_id, "x" * 2001).status_code == 422
    draft = _new(api)
    r = _confirm(api, draft)
    assert r.status_code == 400 and "Cannot move from draft to submitted_confirmed" in r.text


def test_a_user_confirmation_is_recorded_as_user_claimed_never_as_a_receipt(api):
    app_id = _applied(api)
    r = _confirm(api, app_id, f"  {EVIDENCE}  ")
    assert r.status_code == 200, r.text
    e = r.json()["events"][-1]
    assert (e["kind"], e["from_state"], e["to_state"], e["actor"]) == (
        "state_change",
        "submitted_unconfirmed",
        "submitted_confirmed",
        "user",
    )
    assert (e["source"], e["evidence_note"], e["reason"]) == (
        "user_claimed",
        EVIDENCE,
        "Confirmed by you",
    )
    got = api.get(f"/applications/{app_id}").json()
    assert got["submission"] == "user_claimed" and got["reached_submission"] is True
    f = api.get("/applications/funnel").json()
    assert f["submitted"]["receipt"] == 0 and f["submitted"]["confirmed_by_you"] == 1
    other = _applied(api)
    r = api.post(
        f"/applications/{other}/reconcile", json={"finding": "received", "evidence": EVIDENCE}
    )
    assert r.status_code == 200, r.text
    e = r.json()["events"][-1]
    assert (e["source"], e["reason"], e["evidence_note"]) == (
        "user_claimed",
        "Reconciled as received",
        EVIDENCE,
    )


def test_only_a_receipt_or_the_users_statement_enters_submitted_confirmed():
    from app.modules.applications.states import Source, event_source

    actors = {a for nxt in TRANSITIONS.values() for a in nxt.get(AppState.submitted_confirmed, ())}
    assert actors == {Actor.worker, Actor.user}
    assert TRANSITIONS[AppState.submitted_unconfirmed][AppState.submitted_confirmed] == {Actor.user}
    assert TRANSITIONS[AppState.submitting][AppState.submitted_confirmed] == {Actor.worker}
    for start in (AppState.submitted_unconfirmed, AppState.submitting):
        with pytest.raises(IllegalTransition):
            check(start, AppState.submitted_confirmed, Actor.system)
    S = AppState
    assert event_source(S.submitted_confirmed, Actor.worker) == Source.receipt
    assert event_source(S.submitted_confirmed, Actor.user) == Source.user_claimed
    assert event_source(S.submitted_unconfirmed, Actor.user) == Source.user_claimed
    assert event_source(S.submitted_unconfirmed, Actor.worker) is None
    assert event_source(S.submitted_unconfirmed, Actor.system) is None
    for target in set(S) - {S.submitted_confirmed, S.submitted_unconfirmed}:
        for actor in Actor:
            assert event_source(target, actor) is None, (target, actor)


def test_the_service_refuses_a_user_confirmation_without_evidence(api):
    import uuid

    from app.core.db import SessionLocal
    from app.modules.applications.models import Application
    from app.modules.applications.service import transition

    app_id = _applied(api)
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        with pytest.raises(IllegalTransition):
            transition(db, app, AppState.submitted_confirmed, Actor.user, "x")
        db.rollback()
        app = db.get(Application, uuid.UUID(app_id))
        transition(
            db,
            app,
            AppState.submitted_confirmed,
            Actor.user,
            "x",
            evidence_note="Confirmation email ref 1234 seen",
        )
        db.commit()
    e = api.get(f"/applications/{app_id}").json()["events"][-1]
    assert (
        e["source"] == "user_claimed" and e["evidence_note"] == "Confirmation email ref 1234 seen"
    )


@pytest.mark.parametrize("finding", ["received", "not_received"])
def test_reconcile_evidence_is_kept_apart_from_the_reason_and_never_a_500(api, finding):
    app_id = _applied(api)
    body = {"finding": finding, "evidence": "x" * 2000, "confirm_not_received": True}
    r = api.post(f"/applications/{app_id}/reconcile", json=body)
    assert r.status_code == 200, r.text
    e = r.json()["events"][-1]
    want = (
        ("Reconciled as received", "user_claimed")
        if finding == "received"
        else ("Reconciled as not received", None)
    )
    assert (e["reason"], e["source"]) == want and e["evidence_note"] == "x" * 2000
    other = _applied(api)
    r = api.post(f"/applications/{other}/reconcile", json=body | {"evidence": " " * 20})
    assert r.status_code == 422
    assert api.get(f"/applications/{other}").json()["state"] == "submitted_unconfirmed"


OUTCOME_REFUSED = "(reason: outcome_before_submission)"


def test_an_outcome_before_any_submission_is_refused_with_a_reason_code(api):
    """R14.3: an employer's outcome needs a submission NoEfforts knows of; Withdrawn, and
    clearing back to none, can always be recorded."""
    app_id = _new(api)
    for outcome in ("assessment_received", "interviewing", "offer", "rejected", "no_response"):
        r = api.patch(f"/applications/{app_id}", json={"outcome": outcome})
        assert r.status_code == 400 and r.json()["detail"].endswith(OUTCOME_REFUSED), r.text
    r = api.patch(f"/applications/{app_id}", json={"outcome": "interviewing", "notes": "x"})
    assert r.status_code == 400
    got = api.get(f"/applications/{app_id}").json()
    assert got["outcome"] == "none" and got["notes"] is None
    assert not [e for e in got["events"] if e["kind"] == "outcome"]
    assert not _audit("application.outcome")
    r = api.patch(f"/applications/{app_id}", json={"outcome": "withdrawn"})
    assert r.status_code == 200 and [e["kind"] for e in r.json()["events"]].count("outcome") == 1
    assert len(_audit("application.outcome")) == 1
    assert api.patch(f"/applications/{app_id}", json={"outcome": "none"}).status_code == 200
    waiting = _new(api)
    _simulate_state(waiting, AppState.awaiting_approval)
    assert (
        api.patch(f"/applications/{waiting}", json={"outcome": "interviewing"}).status_code == 400
    )
    retry = _applied(api)
    r = api.post(
        f"/applications/{retry}/reconcile",
        json={
            "finding": "not_received",
            "evidence": "Called the employer (synthetic)",
            "confirm_not_received": True,
        },
    )
    assert r.json()["state"] == "failed_retryable"
    assert api.patch(f"/applications/{retry}", json={"outcome": "rejected"}).status_code == 200


@pytest.mark.parametrize("state", ["cancelled", "expired", "failed_terminal"])
def test_an_application_closed_before_submission_takes_no_employer_outcome(api, state):
    """Under the owner's "refuse" choice, an application that ended before any submission can
    never take an employer outcome (D53); the message names only what is possible."""
    app_id = _new(api)
    _simulate_state(app_id, AppState(state))
    r = api.patch(f"/applications/{app_id}", json={"outcome": "offer"})
    assert r.status_code == 400 and r.json()["detail"].endswith(OUTCOME_REFUSED)
    assert "never submitted" not in r.text and "mark it as applied" not in r.text
    assert api.patch(f"/applications/{app_id}", json={"outcome": "withdrawn"}).status_code == 200


def test_outcome_choices_follow_the_submission_rule(api):
    app_id = _new(api)
    got = api.get(f"/applications/{app_id}").json()
    assert got["outcome_choices"] == ["none", "withdrawn"] and got["reached_submission"] is False
    api.post(f"/applications/{app_id}/transition", json={"to": "submitted_unconfirmed"})
    got = api.get(f"/applications/{app_id}").json()
    assert got["outcome_choices"] == [
        "none",
        "assessment_received",
        "interviewing",
        "offer",
        "rejected",
        "withdrawn",
        "no_response",
    ]
    (item,) = api.get("/applications").json()
    assert item["submission"] == "user_claimed" and item["reached_submission"] is True


def test_the_owner_can_switch_the_refusal_to_a_flag_without_a_migration(api, monkeypatch):
    from app.modules.applications import states

    monkeypatch.setattr(states, "OUTCOME_BEFORE_SUBMISSION", "flag")
    app_id = _new(api)
    r = api.patch(f"/applications/{app_id}", json={"outcome": "interviewing"})
    assert r.status_code == 200, r.text
    assert r.json()["reached_submission"] is False and len(r.json()["outcome_choices"]) == 7
    f = api.get("/applications/funnel").json()
    assert f["outcome_before_submission"] == 1 and f["submitted"]["total"] == 0
    monkeypatch.undo()
    assert api.get(f"/applications/{app_id}").json()["outcome"] == "interviewing"
    assert api.get("/applications/funnel").json()["outcome_before_submission"] == 1
    other = _new(api)
    assert api.patch(f"/applications/{other}", json={"outcome": "interviewing"}).status_code == 400


def test_the_owner_can_route_confirmations_through_reconcile_only(api, monkeypatch):
    from app.modules.applications import states

    monkeypatch.setattr(states, "USER_CONFIRMS_THROUGH_TRANSITION", False)
    app_id = _applied(api)
    events = len(api.get(f"/applications/{app_id}").json()["events"])
    r = _confirm(api, app_id)
    assert r.status_code == 400 and r.json()["detail"].endswith(
        "(reason: confirm_through_reconcile)"
    )
    assert len(api.get(f"/applications/{app_id}").json()["events"]) == events
    r = api.post(
        f"/applications/{app_id}/reconcile", json={"finding": "received", "evidence": EVIDENCE}
    )
    assert r.status_code == 200 and r.json()["events"][-1]["source"] == "user_claimed"


def test_assessment_received_is_recordable_with_the_date_and_note_the_user_gives(api):
    """R14.2, R14.4."""
    import datetime
    import uuid

    from app.core.db import SessionLocal
    from app.modules.applications.models import Application
    from app.modules.applications.states import Outcome

    app_id = _applied(api)
    assert _confirm(api, app_id).status_code == 200
    d = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    r = api.patch(
        f"/applications/{app_id}",
        json={
            "outcome": "assessment_received",
            "occurred_on": d,
            "evidence_note": " Online test from the employer ",
        },
    )
    assert r.status_code == 200, r.text
    e = r.json()["events"][-1]
    assert (e["kind"], e["actor"], e["from_outcome"], e["to_outcome"], e["source"]) == (
        "outcome",
        "user",
        "none",
        "assessment_received",
        "user_reported",
    )
    assert (e["occurred_on"], e["evidence_note"]) == (d, "Online test from the employer")
    with SessionLocal() as db:
        assert db.get(Application, uuid.UUID(app_id)).outcome == Outcome.assessment_received
    assert [a.meta for a in _audit("application.outcome")] == [
        {"to": "assessment_received", "source": "user_reported"}
    ]
    e = api.patch(f"/applications/{app_id}", json={"outcome": "interviewing"}).json()["events"][-1]
    assert e["to_outcome"] == "interviewing" and (e["occurred_on"], e["evidence_note"]) == (
        None,
        None,
    )


def test_an_outcome_date_and_note_need_an_outcome_and_no_future_date(api):
    import datetime

    app_id = _applied(api)
    events = len(api.get(f"/applications/{app_id}").json()["events"])
    today = datetime.datetime.now(datetime.UTC).date()
    for body in (
        {"occurred_on": "2026-10-20"},
        {"evidence_note": "a note"},
        {"outcome": "none", "occurred_on": "2026-10-20"},
        {
            "outcome": "interviewing",
            "occurred_on": (today + datetime.timedelta(days=2)).isoformat(),
        },
        {"outcome": "offer", "source": "employer_email"},
    ):
        r = api.patch(f"/applications/{app_id}", json=body)
        assert r.status_code == 422, (body, r.text)
    assert len(api.get(f"/applications/{app_id}").json()["events"]) == events
    assert not _audit("application.outcome")
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    r = api.patch(
        f"/applications/{app_id}", json={"outcome": "interviewing", "occurred_on": tomorrow}
    )
    assert r.status_code == 200, r.text
    r = api.patch(
        f"/applications/{app_id}", json={"outcome": "none", "evidence_note": "set by mistake"}
    )
    assert r.status_code == 200, r.text


def test_restating_an_outcome_with_a_date_adds_an_event_and_repeating_it_adds_none(api):
    app_id = _applied(api)

    def outcomes():
        return [
            e for e in api.get(f"/applications/{app_id}").json()["events"] if e["kind"] == "outcome"
        ]

    api.patch(f"/applications/{app_id}", json={"outcome": "interviewing"})
    assert len(outcomes()) == 1 and len(_audit("application.outcome")) == 1
    api.patch(f"/applications/{app_id}", json={"outcome": "interviewing"})
    assert len(outcomes()) == 1 and len(_audit("application.outcome")) == 1
    first = outcomes()[0]
    api.patch(
        f"/applications/{app_id}", json={"outcome": "interviewing", "occurred_on": "2026-10-21"}
    )
    got = outcomes()
    assert len(got) == 2 and len(_audit("application.outcome")) == 2
    assert got[0] == first
    assert (got[1]["from_outcome"], got[1]["to_outcome"], got[1]["occurred_on"]) == (
        "interviewing",
        "interviewing",
        "2026-10-21",
    )


def test_outcome_refusal_codes_are_fixed_identifiers_documented_once():
    import ast
    import pathlib
    import re

    from app.modules.applications import states
    from app.modules.audit.service import sanitize
    from app.modules.execution import rehearsal
    from app.modules.providers import routing

    root = pathlib.Path(__file__).resolve().parents[2]
    doc = (root / "docs" / "architecture.md").read_text()
    block = doc.split("**Refusal codes**", 1)[1].split("\n\n", 2)[1]
    rows = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \| ([^|]+) \|$", block, re.M)
    assert [r[0] for r in rows] == list(states.REFUSALS)
    for code, _when, shown in rows:
        assert shown.strip() == states.REFUSALS[code], code
    for code in states.REFUSALS:
        assert re.fullmatch(r"[a-z][a-z_]{2,40}", code)
        assert sanitize({"reason_code": code}) == {"reason_code": code}
        assert states.refusal(code).endswith(f"(reason: {code})")
    assert not set(states.REFUSALS) & (set(routing.REASONS) | set(rehearsal.REASONS))
    produced = set()  # applications.states.Refused / refusal; rehearsal has its own refusal()
    for path in (root / "backend" / "app" / "modules" / "applications").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(
                node.func, "id", getattr(node.func, "attr", None)
            ) in ("Refused", "refusal"):
                if path.name == "states.py" and isinstance(node.args[0], ast.Name):
                    continue  # Refused builds its message with refusal(code)
                arg = node.args[0]
                assert isinstance(arg, ast.Constant) and arg.value in states.REFUSALS, (
                    path,
                    ast.dump(arg),
                )
                produced.add(arg.value)
    assert produced == set(states.REFUSALS)


def test_every_layer_measures_the_evidence_the_same_way_and_never_answers_500(api):
    """Review finding: pydantic's strip keeps U+001F, Python's strip removes it, so 14 visible
    characters passed the request and failed transition() (a 500 on /reconcile). One strip now
    applies everywhere, and a NUL (which PostgreSQL text cannot hold) is refused."""
    short = "\x1f" + "a" * 14
    app_id = _applied(api)
    r = api.post(
        f"/applications/{app_id}/reconcile", json={"finding": "received", "evidence": short}
    )
    assert r.status_code == 422, r.text
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={"finding": "not_received", "evidence": short, "confirm_not_received": True},
    )
    assert r.status_code == 422, r.text
    r = _confirm(api, app_id, short)
    assert r.status_code == 400 and r.json()["detail"].endswith("(reason: evidence_required)")
    for body in (
        {"to": "submitted_confirmed", "evidence": EVIDENCE + "\x00"},
        {"to": "cancelled", "reason": "nul \x00 here"},
    ):
        assert api.post(f"/applications/{app_id}/transition", json=body).status_code == 422
    r = api.post(
        f"/applications/{app_id}/reconcile",
        json={"finding": "received", "evidence": EVIDENCE + "\x00"},
    )
    assert r.status_code == 422
    for body in ({"notes": "a \x00 note"}, {"outcome": "offer", "evidence_note": "a \x00 note"}):
        assert api.patch(f"/applications/{app_id}", json=body).status_code == 422
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
