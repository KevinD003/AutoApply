"""A daily check of a job board you chose (D96), against the local stand-ins of the documented
feeds (fixtures/ats_receiver/board_feeds.py) and their own request ledger. Synthetic boards and
accounts only; no real board is contacted."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.models import AuditEvent
from app.modules.discovery import board_sync
from app.modules.discovery.models import BoardSource
from app.modules.mail.models import EmailSettings
from app.modules.mail.service import digest_items
from tests.execution_harness import Receiver
from tests.test_account import unzip
from tests.test_board_sources import _settings, add, jobs, requests_made, sync  # noqa: F401

DAY = timedelta(days=1, minutes=1)


@pytest.fixture(scope="module")
def receiver():  # `_settings` (autouse, from the D95 tests) points the boards at it
    r = Receiver()
    yield r
    r.stop()


def daily(api, sid: str, on: bool = True):
    return api.patch(f"/discovery/sources/{sid}", json={"daily_check": on})


def board_notices(api) -> list[dict]:
    return [i for i in api.get("/notifications").json()["items"] if i["kind"] == "board_postings"]


def test_nothing_is_read_on_its_own_until_you_choose_it_for_a_board(api, receiver):
    sid = add(api).json()["id"]
    assert board_sync.check_due(utcnow() + DAY) == 0
    assert requests_made(receiver) == []
    view = daily(api, sid).json()
    assert view["daily_check"] is True and view["next_check_after"] is None  # due now
    assert board_sync.check_due() == 1
    assert len(requests_made(receiver)) == 1


def test_a_daily_board_is_read_once_a_day_through_the_same_boundary(api, receiver):
    sid = add(api).json()["id"]
    daily(api, sid)
    assert board_sync.check_due() == 1
    assert board_sync.check_due() == 0  # read less than a day ago
    assert board_sync.check_due(utcnow() + timedelta(hours=23)) == 0
    assert board_sync.check_due(utcnow() + DAY) == 1
    reqs = requests_made(receiver)
    assert len(reqs) == 2 and all(
        (r["method"], r["cookie"], r["auth"], r["body_len"]) == ("GET", False, False, 0)
        for r in reqs
    )
    view = api.get("/discovery/sources").json()["items"][0]
    assert view["next_check_after"] and view["last_status"] == "ok"
    with SessionLocal() as db:
        metas = [e.meta for e in db.scalars(select(AuditEvent).where(
            AuditEvent.action == "board_source.update"))]  # fmt: skip
    assert {"change": "daily_check", "outcome": "ok"} in metas
    assert {"change": "daily_check_on", "provider": "greenhouse"} in metas


def test_not_when_boards_are_off_paused_backing_off_or_turned_off(api, receiver, monkeypatch):
    sid = add(api).json()["id"]
    daily(api, sid)
    monkeypatch.setattr(get_settings(), "board_sources_enabled", False)
    assert board_sync.check_due() == 0
    monkeypatch.setattr(get_settings(), "board_sources_enabled", True)
    api.patch(f"/discovery/sources/{sid}", json={"paused": True})
    assert board_sync.check_due() == 0
    api.patch(f"/discovery/sources/{sid}", json={"paused": False})
    with SessionLocal() as db:
        db.execute(update(BoardSource).values(next_allowed_at=utcnow() + timedelta(days=2)))
        db.commit()
    assert board_sync.check_due(utcnow() + DAY) == 0  # a backoff or Retry-After still holds
    with SessionLocal() as db:
        db.execute(update(BoardSource).values(next_allowed_at=None))
        db.commit()
    daily(api, sid, on=False)
    assert board_sync.check_due(utcnow() + DAY) == 0
    assert requests_made(receiver) == []


def test_a_failed_daily_read_changes_nothing_and_backs_off(api, receiver):
    sid = add(api).json()["id"]
    sync(api, sid)
    daily(api, sid)
    receiver.config(board_mode="rate_limited")
    assert board_sync.check_due(utcnow() + DAY) == 1
    view = api.get("/discovery/sources").json()["items"][0]
    assert (view["last_status"], view["listed"]) == ("failed", 2)
    assert board_sync.check_due() == 0  # attempted just now
    assert board_notices(api) == []


def test_new_postings_after_the_first_read_are_one_notice_a_day_never_a_job(api, receiver):
    sid = add(api).json()["id"]
    daily(api, sid)
    board_sync.check_due()
    assert board_notices(api) == []  # what it listed at the first read is not "new"
    receiver.config(board_mode="added")
    board_sync.check_due(utcnow() + DAY)
    (n,) = board_notices(api)
    assert n["text"].startswith("1 new posting on the Greenhouse job board")
    assert (n["job"], n["link"], n["needs_action"], n["application_id"]) == (
        "Northwind (fictional)", "/discover", False, None)  # fmt: skip
    assert jobs(api) == [] and api.get("/applications").json() == []
    assert api.post("/notifications/read", json={"keys": [n["key"]]}).status_code == 200
    assert board_notices(api)[0]["read"] is True
    # Never in an email digest: it needs nothing of you and is not a follow-up.
    with SessionLocal() as db:
        user_id = db.scalar(select(BoardSource.user_id))
        row = EmailSettings(attention=True, follow_ups=True)
        assert digest_items(db, user_id, row) == []


def test_the_daily_limit_and_another_account(api, other_api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "board_daily_check_limit", 1)
    a = add(api).json()["id"]
    b = add(api, provider="lever", board="contoso-example", employer="Contoso (fictional)")
    assert daily(api, a).status_code == 200
    r = daily(api, b.json()["id"])
    assert r.status_code == 409 and "(reason: daily_check_limit)" in r.text
    assert daily(other_api, a).status_code == 404
    other = add(other_api, board="fabrikam-example", employer="Fabrikam (fictional)").json()["id"]
    assert daily(other_api, other).status_code == 200  # the limit is per account
    receiver.config(board_mode="normal")
    assert board_sync.check_due() == 2
    receiver.config(board_mode="added")
    assert board_sync.check_due(utcnow() + DAY) == 2
    assert len(board_notices(api)) == 1 and len(board_notices(other_api)) == 1
    assert board_notices(api)[0]["job"] == "Northwind (fictional)"
    assert board_notices(other_api)[0]["job"] == "Fabrikam (fictional)"


def test_a_board_its_owner_is_reading_is_skipped(api, receiver):
    sid = add(api).json()["id"]
    daily(api, sid)
    with SessionLocal() as held:
        held.execute(select(BoardSource).with_for_update())  # the owner's read holds the row
        assert board_sync.check_due() == 0
        held.rollback()
    assert requests_made(receiver) == []
    assert board_sync.check_due() == 1


def test_your_choice_is_exported(api, receiver):
    sid = add(api).json()["id"]
    daily(api, sid)
    board_sync.check_due()
    tables = json.loads(unzip(api.get("/account/export").content)["noefforts-export.json"])[
        "tables"
    ]
    (src,) = tables["board_sources"]
    assert src["daily_check"] is True and src["baseline_at"]
