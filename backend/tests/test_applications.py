import pytest

from app.modules.applications.states import (
    TRANSITIONS,
    Actor,
    AppState,
    IllegalTransition,
    check,
)


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
    r = api.post(
        f"/applications/{app['id']}/transition",
        json={"to": "submitted_confirmed", "reason": "confirmation email"},
    )
    assert r.json()["state"] == "submitted_confirmed"
    r = api.patch(f"/applications/{app['id']}", json={"outcome": "interviewing"})
    kinds = [e["kind"] for e in r.json()["events"]]
    assert kinds == ["state_change", "state_change", "state_change", "outcome"]


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
    # From quarantine only an explicit user reconciliation may re-queue.
    with pytest.raises(IllegalTransition):
        check(AppState.submitted_unconfirmed, AppState.queued, Actor.system)
    with pytest.raises(IllegalTransition):
        check(AppState.submitted_unconfirmed, AppState.queued, Actor.worker)
    check(AppState.submitted_unconfirmed, AppState.queued, Actor.user)


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
