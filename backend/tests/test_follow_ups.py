"""Follow-ups (D92): a reminder to check on an application you submitted, derived from its own
records, with a message to copy. Synthetic accounts only; nothing is sent anywhere."""

import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.followups import service
from app.modules.followups.models import FollowUp
from tests.conftest import Api
from tests.test_account import unzip

TODAY = service.today()


def _on(monkeypatch, day: date) -> None:
    monkeypatch.setattr(service, "today", lambda: day)


def _application(
    api: Api, *, title="Pastry Chef", employer="Bread Co (fictional)", url=None
) -> str:
    body = {"title": title, "employer": employer} | ({"url": url} if url else {})
    job = api.post("/jobs", json=body).json()["job"]
    return api.post("/applications", json={"job_id": job["id"]}).json()["id"]


def _applied(api: Api, app_id: str) -> None:
    applied = {"to": "submitted_unconfirmed", "reason": "I applied on the website"}
    r = api.post(f"/applications/{app_id}/transition", json=applied)
    assert r.status_code == 200, r.text


def _follow_up(api: Api, app_id: str) -> dict:
    r = api.get(f"/applications/{app_id}/follow-up")
    assert r.status_code == 200, r.text
    return r.json()


def _act(api: Api, app_id: str, action: str, **extra):
    return api.post(f"/applications/{app_id}/follow-up", json={"action": action, **extra})


def _notified(api: Api) -> set[str]:
    return {i["key"] for i in api.get("/notifications").json()["items"] if i["kind"] == "follow_up"}


# ------------------------------------------------------------------------------ when it is due


def test_nothing_to_follow_up_before_the_application_is_submitted(api):
    app_id = _application(api)
    assert _follow_up(api, app_id) == {"status": "not_submitted", "draft": None}
    r = _act(api, app_id, "done")
    assert r.status_code == 409 and "(reason: not_submitted)" in r.text
    assert api.get("/follow-ups").json()["items"] == []
    assert _notified(api) == set()


def test_due_seven_days_after_you_applied_and_notified_then(api, monkeypatch):
    app_id = _application(api)
    _applied(api, app_id)
    f = _follow_up(api, app_id)
    due = TODAY + timedelta(days=7)
    assert (f["status"], f["submitted_on"], f["due_on"], f["days"]) == (
        "scheduled", TODAY.isoformat(), due.isoformat(), 7)  # fmt: skip
    assert _notified(api) == set()
    _on(monkeypatch, due - timedelta(days=1))
    assert _follow_up(api, app_id)["status"] == "scheduled" and _notified(api) == set()
    _on(monkeypatch, due)
    assert _follow_up(api, app_id)["status"] == "due"
    assert _notified(api) == {f"follow_up:{app_id}:{due.isoformat()}"}
    listed = api.get("/follow-ups").json()
    assert listed["due"] == 1 and listed["items"][0]["job"] == "Pastry Chef — Bread Co (fictional)"
    item = next(i for i in api.get("/notifications").json()["items"] if i["kind"] == "follow_up")
    assert item["needs_action"] and item["link"] == f"/applications/{app_id}"
    assert "sends nothing" in item["text"]


def test_the_days_are_the_owner_setting(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "follow_up_days", 3)
    app_id = _application(api)
    _applied(api, app_id)
    assert _follow_up(api, app_id)["due_on"] == (TODAY + timedelta(days=3)).isoformat()


def test_saying_you_followed_up_starts_the_next_wait_and_a_new_notification(api, monkeypatch):
    app_id = _application(api)
    _applied(api, app_id)
    first = TODAY + timedelta(days=7)
    _on(monkeypatch, first)
    assert _notified(api) == {f"follow_up:{app_id}:{first.isoformat()}"}
    r = _act(api, app_id, "done")
    assert r.status_code == 200, r.text
    f = r.json()
    nxt = first + timedelta(days=7)
    assert (f["status"], f["followed_up_on"], f["due_on"]) == (
        "scheduled", first.isoformat(), nxt.isoformat())  # fmt: skip
    assert _notified(api) == set()
    _on(monkeypatch, nxt)
    assert _notified(api) == {f"follow_up:{app_id}:{nxt.isoformat()}"}


def test_remind_me_on_a_day_you_choose_within_a_year(api, monkeypatch):
    app_id = _application(api)
    _applied(api, app_id)
    day = TODAY + timedelta(days=2)
    f = _act(api, app_id, "remind", remind_on=day.isoformat()).json()
    assert (f["status"], f["due_on"], f["remind_on"]) == (
        "scheduled",
        day.isoformat(),
        day.isoformat(),
    )
    _act(api, app_id, "remind", remind_on=TODAY.isoformat())
    assert _follow_up(api, app_id)["status"] == "due" and len(_notified(api)) == 1
    for bad, code in [
        ({}, "remind_on_required"),
        ({"remind_on": (TODAY - timedelta(days=1)).isoformat()}, "remind_on_range"),
        ({"remind_on": (TODAY + timedelta(days=366)).isoformat()}, "remind_on_range"),
    ]:
        r = _act(api, app_id, "remind", **bad)
        assert r.status_code == 409 and f"(reason: {code})" in r.text
    # Following up clears the chosen day: the next one is derived again.
    _on(monkeypatch, TODAY + timedelta(days=1))
    f = _act(api, app_id, "done").json()
    assert f["remind_on"] is None and f["due_on"] == (TODAY + timedelta(days=8)).isoformat()


def test_stopping_the_reminders_and_resuming_them(api, monkeypatch):
    app_id = _application(api)
    _applied(api, app_id)
    _on(monkeypatch, TODAY + timedelta(days=7))
    assert _act(api, app_id, "stop").json()["status"] == "stopped"
    assert _notified(api) == set() and api.get("/follow-ups").json()["due"] == 0
    assert _act(api, app_id, "resume").json()["status"] == "due"
    assert len(_notified(api)) == 1


def test_an_outcome_that_closes_the_application_ends_the_reminders(api, monkeypatch):
    app_id = _application(api)
    _applied(api, app_id)
    _on(monkeypatch, TODAY + timedelta(days=9))
    assert api.patch(f"/applications/{app_id}", json={"outcome": "rejected"}).status_code == 200
    f = _follow_up(api, app_id)
    assert f["status"] == "closed" and f["due_on"] is None
    assert _notified(api) == set()
    for action in ("done", "remind", "resume"):
        r = _act(api, app_id, action, remind_on=TODAY.isoformat())
        assert r.status_code == 409 and "(reason: outcome_closed)" in r.text
    assert _act(api, app_id, "stop").status_code == 200  # stopping is always allowed


def test_an_interview_you_recorded_starts_the_wait_from_its_day(api):
    app_id = _application(api)
    _applied(api, app_id)
    day = TODAY - timedelta(days=1)
    r = api.patch(f"/applications/{app_id}",
                  json={"outcome": "interviewing", "occurred_on": day.isoformat()})  # fmt: skip
    assert r.status_code == 200, r.text
    f = _follow_up(api, app_id)
    # The interview was before the submission day here, so the later day counts.
    assert f["due_on"] == (TODAY + timedelta(days=7)).isoformat()
    assert f["draft"]["subject"] == "Following up on my interview: Pastry Chef"
    assert "opportunity to interview" in f["draft"]["body"]


# ------------------------------------------------------------------------------ the message


def test_the_message_uses_the_job_your_approved_name_and_nothing_else_of_yours(api):
    api.put("/profile", json={"full_name": "Sam Synthetic", "contact_email": "sam@example.com",
                              "phone": "+1 555 0100", "links": []})  # fmt: skip
    app_id = _application(api)
    _applied(api, app_id)
    d = _follow_up(api, app_id)["draft"]
    assert d["subject"] == "Following up on my application: Pastry Chef"
    assert "Pastry Chef position at Bread Co (fictional)" in d["body"]
    assert f"on {TODAY.day} {TODAY:%B %Y}" in d["body"]
    assert d["body"].endswith("Kind regards,\nSam Synthetic") and not d["name_missing"]
    for not_sent in ("sam@example.com", "555"):
        assert not_sent not in d["body"]


def test_without_a_name_the_message_says_where_yours_goes(api):
    app_id = _application(api, title=None, url="https://jobs.example.com/careers/42")
    _applied(api, app_id)
    d = _follow_up(api, app_id)["draft"]
    assert d["name_missing"] and d["body"].endswith("[Your name]")
    assert "the role position at Bread Co (fictional)" in d["body"]


# ------------------------------------------------------------------------------ the boundary


def test_another_account_never_sees_or_changes_your_follow_up(api, other_api):
    app_id = _application(api)
    _applied(api, app_id)
    assert other_api.get(f"/applications/{app_id}/follow-up").status_code == 404
    assert _act(other_api, app_id, "stop").status_code == 404
    assert _act(other_api, str(uuid.uuid4()), "stop").status_code == 404
    assert other_api.get("/follow-ups").json()["items"] == []
    assert _follow_up(api, app_id)["status"] == "scheduled"
    with SessionLocal() as db:
        assert db.scalars(select(FollowUp)).all() == []


def test_a_change_needs_the_csrf_token(api):
    app_id = _application(api)
    _applied(api, app_id)
    r = api.client.post(f"/applications/{app_id}/follow-up", json={"action": "stop"})
    assert r.status_code == 403


def test_a_read_token_lists_follow_ups_but_never_reads_the_message_or_changes_one(api):
    app_id = _application(api)
    _applied(api, app_id)
    token = api.post("/account/tokens", json={"label": "laptop", "scopes": ["read"]}).json()[
        "token"
    ]
    bare = Api()
    h = {"Authorization": f"Bearer {token}"}
    r = bare.client.get("/follow-ups", headers=h)
    assert r.status_code == 200 and r.json()["items"][0]["application_id"] == app_id
    assert "draft" not in r.json()["items"][0]
    r = bare.client.get(f"/applications/{app_id}/follow-up", headers=h)
    assert r.status_code == 403 and "token_scope" in r.text
    r = bare.client.post(f"/applications/{app_id}/follow-up", headers=h, json={"action": "stop"})
    assert r.status_code == 403 and "token_scope" in r.text


def test_your_choices_are_audited_by_action_only_and_exported_with_the_account(api):
    app_id = _application(api)
    _applied(api, app_id)
    _act(api, app_id, "remind", remind_on=(TODAY + timedelta(days=3)).isoformat())
    with SessionLocal() as db:
        (ev,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "follow_up.update"))
        assert ev.meta == {"change": "remind"}  # never the day you chose
    tables = json.loads(unzip(api.get("/account/export").content)["noefforts-export.json"])[
        "tables"
    ]
    (row,) = tables["follow_ups"]
    assert (
        row["application_id"] == app_id
        and row["remind_on"] == (TODAY + timedelta(days=3)).isoformat()
    )


def test_deleting_the_application_or_the_account_deletes_your_choices(api):
    app_id = _application(api)
    _applied(api, app_id)
    _act(api, app_id, "stop")
    confirm = {"password": "correct-horse-1", "confirmation": "delete my account"}
    r = api.post("/account/delete", json=confirm)
    assert r.status_code == 204, r.text
    with SessionLocal() as db:
        assert db.scalars(select(FollowUp)).all() == []


@pytest.mark.parametrize("outcome", ["offer", "withdrawn", "no_response"])
def test_every_closing_outcome_closes_it(api, outcome):
    app_id = _application(api)
    _applied(api, app_id)
    assert api.patch(f"/applications/{app_id}", json={"outcome": outcome}).status_code == 200
    assert _follow_up(api, app_id)["status"] == "closed"
