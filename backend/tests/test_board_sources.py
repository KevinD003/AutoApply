"""Public employer job boards (D95) against local stand-ins of the documented feeds
(fixtures/ats_receiver/board_feeds.py), whose own request ledger records what was asked and
whether anything of the user came with it. Synthetic boards and accounts only; no real board
is contacted."""

import json
import logging
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core import urlsafety
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.models import AuditEvent
from app.modules.discovery import boards
from app.modules.discovery.models import BoardSource, DiscoveredJob
from app.modules.preparation.models import PackageApproval
from tests.conftest import Api
from tests.execution_harness import BASE, Receiver
from tests.test_account import unzip

GH, LV = "northwind-example", "contoso-example"  # fictional boards


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _settings(receiver, monkeypatch):
    receiver.reset()
    s = get_settings()
    for k, v in {"board_sources_enabled": True, "board_min_interval_seconds": 0,
                 "board_page_size": 2, "board_max_pages": 10, "board_timeout_seconds": 3,
                 "board_api_overrides": {"greenhouse": f"{BASE}/gh-board",
                                         "lever": f"{BASE}/lever-board"}}.items():  # fmt: skip
        monkeypatch.setattr(s, k, v)


def add(api: Api, provider="greenhouse", board=GH, employer="Northwind (fictional)", **kw):
    body = {"provider": provider, "board": board, "employer": employer} | kw
    return api.post("/discovery/sources", json=body)


def sync(api: Api, sid: str):
    return api.post(f"/discovery/sources/{sid}/sync")


def postings(api: Api, sid: str) -> list[dict]:
    return api.get(f"/discovery/sources/{sid}/postings").json()["items"]


def requests_made(receiver) -> list[dict]:
    return receiver.ledger()["board_requests"]


def jobs(api: Api) -> list[dict]:
    return api.get("/jobs").json()["items"]


# ------------------------------------------------------------------------------ adding a board


def test_off_by_default_nothing_is_read(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "board_sources_enabled", False)
    sid = add(api).json()["id"]
    r = sync(api, sid)
    assert r.status_code == 409 and "(reason: board_sources_disabled)" in r.text
    assert (
        requests_made(receiver) == [] and api.get("/discovery/sources").json()["enabled"] is False
    )


@pytest.mark.parametrize(("body", "code"), [
    ({"board": "https://boards.example.com/x"}, "board_invalid"),
    ({"board": "../../admin"}, "board_invalid"),
    ({"board": "a b"}, "board_invalid"),
    ({"provider": "ashby"}, "provider_unknown"),
    ({"provider": "workday"}, "provider_unknown"),
    ({"provider": "lever", "region": "us"}, "region_unknown"),
])  # fmt: skip
def test_a_board_is_an_identifier_never_a_url(api, receiver, body, code):
    r = add(api, **body)
    assert r.status_code == 400 and f"(reason: {code})" in r.text
    assert requests_made(receiver) == []


def test_ashby_says_why_it_is_not_built_and_a_duplicate_is_refused(api):
    r = add(api, provider="ashby")
    assert "documentation could not be opened" in r.text
    assert add(api).status_code == 201
    r = add(api)
    assert r.status_code == 409 and "(reason: source_exists)" in r.text


# ------------------------------------------------------------------------------ reading


def test_a_greenhouse_board_is_read_once_with_nothing_of_yours(api, receiver):
    api.put("/profile", json={"full_name": "Sam Synthetic", "contact_email": "sam@example.com",
                              "links": []})  # fmt: skip
    sid = add(api).json()["id"]
    out = sync(api, sid).json()
    assert (out["status"], out["complete"], out["listed"], out["new"]) == ("ok", True, 2, 2)
    (req,) = requests_made(receiver)
    assert req == {
        "method": "GET",
        "path": f"/gh-board/v1/boards/{GH}/jobs",
        "query": "content=true",
        "cookie": False,
        "auth": False,
        "body_len": 0,
    }
    items = postings(api, sid)
    first = next(i for i in items if i["title"] == "Support Specialist (fictional)")
    assert first["location"] == "Springfield (fictional)" and first["source_lists_it"] is True
    assert first["description_summary"].startswith("Help customers by email and chat")
    assert "<" not in first["description_summary"]
    assert first["attribution"]["text"] == "from Greenhouse job board"
    assert first["job_id"] is None and jobs(api) == []  # nothing added to your jobs by a read
    # The same match summary as the jobs list (jobs/fit.py), computed without saving anything.
    assert set(first["match"]) == {
        "preferences_met",
        "preferences_checked",
        "label",
        "compared",
        "skills_named",
        "licences_named",
        "unknown",
    }


def test_a_lever_board_is_paged_until_a_short_page(api, receiver):
    sid = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    out = sync(api, sid).json()
    assert (out["complete"], out["listed"], out["requests"]) == (True, 5, 3)
    queries = [r["query"] for r in requests_made(receiver)]
    assert queries == [f"mode=json&skip={k}&limit=2" for k in (0, 2, 4)]
    items = {i["title"]: i for i in postings(api, sid)}
    assert items["Nurse 1 (fictional)"]["workplace"] == "onsite"
    assert items["Nurse 2 (fictional)"]["workplace"] == "remote"
    assert items["Nurse 4 (fictional)"]["workplace"] == "unknown"
    assert items["Nurse 1 (fictional)"]["employment_type"] == "Full-time"


def test_repeated_reads_never_duplicate(api, receiver):
    sid = add(api).json()["id"]
    sync(api, sid)
    out = sync(api, sid).json()
    assert (out["new"], out["listed"]) == (0, 2) and len(postings(api, sid)) == 2


def test_a_posting_is_saved_once_and_reconciled_with_your_existing_jobs(api, receiver):
    mine = api.post(
        "/jobs",
        json={
            "url": "https://example.com/careers?gh_jid=4100002",
            "title": "My own title",
            "employer": "Northwind (fictional)",
        },
    )
    sid = add(api).json()["id"]
    out = sync(api, sid).json()
    assert out["in_your_jobs"] == 1  # the same link: linked, nothing new added
    items = {i["title"]: i for i in postings(api, sid)}
    assert items["Data Analyst (fictional)"]["job_id"] == mine.json()["job"]["id"]
    assert len(jobs(api)) == 1
    pid = items["Support Specialist (fictional)"]["id"]
    r = api.post(f"/discovery/sources/postings/{pid}/save").json()
    assert r["outcome"] == "added" and len(jobs(api)) == 2
    again = api.post(f"/discovery/sources/postings/{pid}/save").json()
    assert again == {"job_id": r["job_id"], "outcome": "already_in_your_jobs"}
    sync(api, sid)
    assert len(jobs(api)) == 2


def test_only_a_complete_read_says_a_posting_is_no_longer_listed(api, receiver):
    sid = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    sync(api, sid)
    receiver.config(board_mode="removed")
    out = sync(api, sid).json()
    assert out["no_longer_listed"] == 1
    gone = [i for i in postings(api, sid) if not i["source_lists_it"]]
    assert [g["title"] for g in gone] == ["Nurse 1 (fictional)"] and gone[0][
        "no_longer_listed_since"
    ]
    receiver.config(board_mode="normal")
    assert sync(api, sid).json()["listed_again"] == 1
    assert all(i["source_lists_it"] for i in postings(api, sid))


def test_an_incomplete_read_never_marks_anything_closed(api, receiver, monkeypatch):
    sid = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    sync(api, sid)
    monkeypatch.setattr(get_settings(), "board_max_pages", 1)  # stops after one page
    receiver.config(board_mode="removed")
    out = sync(api, sid).json()
    assert (out["complete"], out["no_longer_listed"]) == (False, 0)
    assert all(i["source_lists_it"] for i in postings(api, sid))
    gh = add(api).json()["id"]
    sync(api, gh)
    receiver.config(board_mode="total_mismatch")  # meta.total disagrees: not complete
    assert sync(api, gh).json()["complete"] is False


@pytest.mark.parametrize(("mode", "code"), [
    ("not_found", "board_not_found"), ("unavailable", "unavailable"),
    ("rate_limited", "rate_limited"), ("redirect", "redirected"), ("oversize", "too_large"),
    ("not_json", "bad_response"), ("page2_fails", "unavailable"),
])  # fmt: skip
def test_a_failed_read_changes_nothing_and_backs_off(api, receiver, monkeypatch, mode, code):
    monkeypatch.setattr(get_settings(), "board_max_bytes", 1_000_000)
    sid = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    sync(api, sid)
    before = postings(api, sid)
    receiver.config(board_mode=mode)
    out = sync(api, sid).json()
    assert (out["status"], out["error_code"]) == ("failed", code)
    assert postings(api, sid) == before
    src = api.get("/discovery/sources").json()["items"][0]
    assert src["last_status"] == "failed" and src["last_error"] and src["listed"] == 5
    r = sync(api, sid)
    assert r.status_code == 409 and "(reason: too_soon)" in r.text
    if mode == "rate_limited":
        with SessionLocal() as db:
            s = db.get(BoardSource, uuid.UUID(sid))
            assert s.next_allowed_at - s.last_attempt_at >= timedelta(seconds=119)
    if mode == "redirect":
        assert all("169.254" not in r["path"] for r in requests_made(receiver))


def test_two_reads_of_one_board_at_once_are_refused(api, receiver):
    sid = add(api).json()["id"]
    with SessionLocal() as db:  # hold the source's lock as a read in progress would
        db.scalar(select(BoardSource).where(BoardSource.id == uuid.UUID(sid)).with_for_update())
        r = sync(api, sid)
        assert r.status_code == 409 and "(reason: sync_in_progress)" in r.text
    assert requests_made(receiver) == []


def test_untrusted_content_and_links_are_neutralised(api, receiver):
    receiver.config(board_mode="malicious")
    gh = add(api).json()["id"]
    sync(api, gh)
    lv = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    sync(api, lv)
    text = json.dumps(postings(api, gh) + postings(api, lv))
    for bad in ("<script", "onerror", "alert(1)", "javascript:", "data:text", "169.254.169.254",
                "127.0.0.1:8100"):  # fmt: skip
        assert bad not in text, bad
    assert requests_made(receiver)[-1]["path"].startswith("/lever-board/")
    assert (
        len(requests_made(receiver)) == 4
    )  # one board read each (+ Lever pages); no link followed


def test_malformed_records_are_skipped(api, receiver):
    receiver.config(board_mode="malformed")
    gh = add(api).json()["id"]
    assert sync(api, gh).json()["malformed"] == 4
    lv = add(api, provider="lever", board=LV, employer="Contoso (fictional)").json()["id"]
    assert sync(api, lv).json()["malformed"] == 3


# ------------------------------------------------------------------------------ your control


def test_pause_resume_rename_and_remove(api, receiver):
    sid = add(api).json()["id"]
    sync(api, sid)
    pid = postings(api, sid)[0]["id"]
    job_id = api.post(f"/discovery/sources/postings/{pid}/save").json()["job_id"]
    assert api.patch(f"/discovery/sources/{sid}", json={"paused": True}).json()["paused"]
    r = sync(api, sid)
    assert r.status_code == 409 and "(reason: source_paused)" in r.text
    api.patch(f"/discovery/sources/{sid}", json={"paused": False, "employer": "Renamed"})
    assert sync(api, sid).json()["status"] == "ok"
    assert api.delete(f"/discovery/sources/{sid}").json() == {"removed": True}
    with SessionLocal() as db:
        assert (
            db.scalars(
                select(DiscoveredJob).where(DiscoveredJob.board_source_id.is_not(None))
            ).all()
            == []
        )
    assert [j["id"] for j in jobs(api)] == [job_id]  # the job you saved stays yours


def test_another_account_never_reaches_your_boards(api, other_api, receiver):
    sid = add(api).json()["id"]
    sync(api, sid)
    pid = postings(api, sid)[0]["id"]
    assert other_api.get("/discovery/sources").json()["items"] == []
    for method, path in [("post", f"/discovery/sources/{sid}/sync"),
                         ("get", f"/discovery/sources/{sid}/postings"),
                         ("patch", f"/discovery/sources/{sid}"),
                         ("delete", f"/discovery/sources/{sid}"),
                         ("post", f"/discovery/sources/postings/{pid}/save")]:  # fmt: skip
        kw = {"json": {"paused": True}} if method == "patch" else {}
        assert getattr(other_api, method)(path, **kw).status_code == 404, path
    # A board posting is not reachable through the Freehire routes either.
    assert api.get(f"/discovery/jobs/{pid}").status_code == 404
    assert api.get("/discovery/jobs").json() == []


def test_discovery_never_creates_an_application_route_or_approval(api, receiver):
    sid = add(api).json()["id"]
    sync(api, sid)
    pid = next(i["id"] for i in postings(api, sid) if "Support" in i["title"])
    job_id = api.post(f"/discovery/sources/postings/{pid}/save").json()["job_id"]
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["route"] in ("manual_handoff", "checkpoint") and "live" not in json.dumps(route)
    assert api.get("/applications").json() == []
    with SessionLocal() as db:
        assert db.scalars(select(PackageApproval)).all() == []


# ------------------------------------------------------------------------------ the boundary


def test_outside_tests_the_fixed_public_host_is_used_never_an_override(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    base, _ = boards._base("greenhouse", "global")
    assert base == "https://boards-api.greenhouse.io"
    monkeypatch.setattr(s, "env", "test")
    monkeypatch.setattr(s, "board_api_overrides", {"lever": "http://evil.example.com/x"})
    assert boards._base("lever", "eu")[0] == "https://api.eu.lever.co"  # not a fixture origin


def test_the_public_opener_refuses_other_hosts_plain_http_and_private_addresses(monkeypatch):
    opener = urlsafety.public_https_opener("boards-api.greenhouse.io", boards._NoRedirect)
    for url in (
        "https://evil.example.com/x",
        "http://boards-api.greenhouse.io/x",
        "https://boards-api.greenhouse.io:8443/x",
        "https://u:p" + "@" + "boards-api.greenhouse.io/x",
    ):  # a login in the address
        with pytest.raises(urlsafety.UnsafeURL):
            opener.open(url, timeout=1)
    monkeypatch.setattr(
        urlsafety._PublicHTTPSConnection,
        "resolver",
        staticmethod(lambda *a, **k: [(2, 1, 6, "", ("169.254.169.254", 443))]),
    )
    with pytest.raises(urlsafety.UnsafeURL):
        opener.open("https://boards-api.greenhouse.io/v1/boards/x/jobs", timeout=1)


def test_export_deletion_audit_and_logs_keep_board_data_where_it_belongs(api, receiver, caplog):
    caplog.set_level(logging.DEBUG)
    sid = add(api).json()["id"]
    sync(api, sid)
    assert GH not in caplog.text and "Northwind" not in caplog.text
    with SessionLocal() as db:
        metas = [e.meta for e in db.scalars(select(AuditEvent).where(
            AuditEvent.action == "board_source.update"))]  # fmt: skip
    assert metas and GH not in json.dumps(metas) and "Northwind" not in json.dumps(metas)
    tables = json.loads(unzip(api.get("/account/export").content)["noefforts-export.json"])[
        "tables"
    ]
    (src,) = tables["board_sources"]
    assert (src["board"], src["employer"]) == (GH, "Northwind (fictional)")  # yours: exported
    assert len([d for d in tables["discovered_jobs"] if d["board_source_id"] == sid]) == 2
    confirm = {"password": "correct-horse-1", "confirmation": "delete my account"}
    assert api.post("/account/delete", json=confirm).status_code == 204
    with SessionLocal() as db:
        assert db.scalars(select(BoardSource)).all() == []


def test_backoff_is_bounded():
    assert boards.backoff(1, None) == timedelta(minutes=5)
    assert boards.backoff(20, None) == timedelta(days=1)
    assert boards.backoff(1, 5) == timedelta(minutes=1) and boards.backoff(1, 10**9) == timedelta(
        days=1
    )
    with SessionLocal() as db:
        db.execute(update(BoardSource).values(next_allowed_at=utcnow()))
