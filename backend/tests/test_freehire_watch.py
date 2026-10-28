"""S8 (D56): watched Freehire searches. The owner's standing approval names a search, an interval
of at least a minute, an end date and a retention statement; a worker task checks each due watch,
newest postings first, and stops at the first posting it already has, so a new posting reaches
the job list within about a minute of appearing on Freehire. Bounded: a daily request cap, the
rate headers, Retry-After, backoff and a pause after ten failures in a row; nothing is retried
inside a check. A deleted posting keeps only its id, so a watch never brings it back. The local
stand-in of Freehire's documented API plays the live origin; its request table is the oracle."""

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.urlsafety import UnsafeURL
from app.modules.discovery import provider as fh
from app.modules.discovery import service, watch
from app.modules.discovery.models import DiscoveredJob, DiscoveryWatch
from app.modules.jobs.models import Job
from tests.execution_harness import BASE, Receiver
from tests.test_freehire_discovery import fh_requests, me

FIXTURE = f"{BASE}/freehire-fixture"
OWNER = "synthetic.user@example.com"
WHY = "Discovered postings are kept until I delete them."
NEW = "fx-contoso-finance-liaison-88"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def checked(receiver, monkeypatch):
    receiver.reset()
    s = get_settings()
    for k, v in (("discovery_providers", ["freehire"]), ("freehire_base_url", FIXTURE),
                 ("freehire_api_key", ""), ("freehire_page_size", 2),
                 ("freehire_timeout_seconds", 2), ("discovery_owner_emails", [OWNER]),
                 ("freehire_daily_request_budget", 1440)):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(fh, "LIVE_ORIGIN", FIXTURE)
    monkeypatch.setattr(fh, "is_fixture_origin", lambda url: False)
    seen = []
    monkeypatch.setattr(fh, "resolve_public_destination", lambda url: seen.append(url) or ["x"])
    return seen


def add_watch(user_id, query="i", every=60, days=30, start=-1) -> uuid.UUID:
    now = utcnow()
    with SessionLocal() as db:
        w = DiscoveryWatch(
            user_id=user_id,
            provider="freehire",
            query=query,
            interval_seconds=every,
            not_before=now + timedelta(seconds=start),
            not_after=now + timedelta(days=days),
            retention=WHY,
            next_check_at=now + timedelta(seconds=start),
        )
        db.add(w)
        db.commit()
        return w.id


def tick(seconds=0) -> int:
    return service.check_due_watches(now=utcnow() + timedelta(seconds=seconds))


def noon_tomorrow():
    t = utcnow() + timedelta(days=1)
    return t.replace(hour=12, minute=0, second=0, microsecond=0)


def state(watch_id) -> DiscoveryWatch:
    with SessionLocal() as db:
        w = db.get(DiscoveryWatch, watch_id)
        db.expunge(w)
        return w


def jobs(user_id) -> set[str]:
    with SessionLocal() as db:
        return set(db.scalars(select(Job.title).where(Job.user_id == user_id)))


def test_a_new_posting_reaches_the_job_list_at_the_next_check(api, receiver):
    uid = me(api)
    w = add_watch(uid)
    assert tick() == 1
    first = fh_requests(receiver)
    assert len(first) == 2 and {r["q"] for r in first} == {"i"}  # the bounded first look
    assert "Support Specialist" in jobs(uid)
    receiver.config(fh_mode="fh_new_posting")  # Freehire receives a new posting
    assert tick(61) == 1
    assert len(fh_requests(receiver)) == 3  # one request: stopped at a posting it already had
    assert "Finance Liaison" in jobs(uid)
    s = state(w)
    assert (s.found_total, s.failures, s.last_outcome) == (5, 0, "ok")
    listed = {r["source_job_id"] for r in api.get("/discovery/jobs").json()}
    assert NEW in listed and all(r["attribution"]["text"] == "via freehire.me"
                                 for r in api.get("/discovery/jobs").json())  # fmt: skip


def test_a_watch_is_checked_no_sooner_than_its_interval(api, receiver):
    add_watch(me(api), every=300)
    assert tick() == 1
    assert tick(30) == 0 and tick(299) == 0
    assert len(fh_requests(receiver)) == 2
    assert tick(301) == 1


def test_only_an_active_watch_of_an_owner_reads(api, other_api, receiver, monkeypatch):
    stranger = add_watch(me(other_api))
    stopped = add_watch(me(api))
    with SessionLocal() as db:
        db.get(DiscoveryWatch, stopped).revoked_at = utcnow()
        db.commit()
    ended = add_watch(me(api), days=1)
    assert tick(2 * 86400) == 1  # only the stranger's: stopped and ended watches are skipped
    assert state(stranger).paused_reason == "not_owner"
    assert fh_requests(receiver) == []
    assert state(ended).last_checked_at is None and state(stopped).last_checked_at is None
    mine = add_watch(me(api))
    monkeypatch.setattr(get_settings(), "discovery_owner_emails", [])
    tick(5)
    assert state(mine).paused_reason == "not_owner" and fh_requests(receiver) == []


def test_a_429_waits_for_retry_after_and_nothing_is_retried_inside_a_check(api, receiver):
    w = add_watch(me(api), every=60)
    receiver.config(fh_mode="fh_rate_limited")  # Retry-After: 30
    assert tick() == 1 and len(fh_requests(receiver)) == 1
    s = state(w)
    assert s.last_outcome == "rate_limited" and s.failures == 1
    assert s.next_check_at >= utcnow() + timedelta(seconds=55)  # max(interval, Retry-After)
    assert tick(30) == 0 and len(fh_requests(receiver)) == 1


def test_failures_back_off_and_ten_in_a_row_pause_the_watch(api, receiver):
    w = add_watch(me(api), every=60)
    receiver.config(fh_mode="fh_outage")
    gaps, t = [], 0
    for _ in range(10):
        before = state(w).next_check_at
        t = max(t, (before - utcnow()).total_seconds() + 1)
        assert tick(t) == 1
        gaps.append((state(w).next_check_at - before).total_seconds())
    s = state(w)
    assert (s.failures, s.paused_reason) == (10, "unavailable")
    expected = [min(60 * 2**k, 3600) for k in range(9)]  # 60, 120, ... capped at an hour
    assert all(abs(g - 1 - e) < 5 for g, e in zip(gaps[:9], expected, strict=True)), gaps
    count = len(fh_requests(receiver))
    assert tick(t + 7200) == 0 and len(fh_requests(receiver)) == count  # paused: no request


def test_the_daily_request_cap_is_never_passed(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_daily_request_budget", 3)
    w = add_watch(me(api), every=60)
    day = noon_tomorrow()  # one UTC day whatever time the test runs
    assert service.check_due_watches(now=day) == 1 and len(fh_requests(receiver)) == 2
    # A check could need two more requests: deferred to the next UTC day, nothing asked.
    assert service.check_due_watches(now=day + timedelta(seconds=61)) == 1
    assert len(fh_requests(receiver)) == 2 and state(w).last_outcome == "daily_budget"
    n = state(w).next_check_at
    assert (n.date(), n.hour, n.minute) == ((day + timedelta(days=1)).date(), 0, 0)


def test_the_address_is_checked_before_every_check(api, receiver, monkeypatch):
    def private(url):
        raise UnsafeURL("blocked")

    monkeypatch.setattr(fh, "resolve_public_destination", private)
    w = add_watch(me(api))
    assert tick() == 1
    assert state(w).last_outcome == "address_refused" and fh_requests(receiver) == []


def test_another_address_pauses_the_watch(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_base_url", "https://jobs.example.org")
    w = add_watch(me(api))
    assert tick() == 1
    assert state(w).paused_reason == "address_refused" and fh_requests(receiver) == []


def test_discovery_off_means_no_check(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_providers", [])
    add_watch(me(api))
    assert tick() == 0 and fh_requests(receiver) == []


def test_one_watch_is_never_checked_twice_at_once(api, receiver):
    w = add_watch(me(api))
    held, release = threading.Event(), threading.Event()

    def hold():
        with SessionLocal() as db:
            db.execute(text("select id from discovery_watches where id=:w for update"), {"w": w})
            held.set()
            release.wait(10)
            db.rollback()

    t = threading.Thread(target=hold)
    t.start()
    held.wait(10)
    try:
        assert tick() == 0  # locked by another worker: skipped, not waited for
    finally:
        release.set()
        t.join()
    assert fh_requests(receiver) == []
    assert tick() == 1


def test_watches_are_listed_and_stopped_only_by_their_owner(api, other_api, receiver):
    w = add_watch(me(api), query="analyst")
    listed = api.get("/discovery/watches").json()
    assert [x["id"] for x in listed] == [str(w)] and listed[0]["query"] == "analyst"
    assert other_api.get("/discovery/watches").json() == []
    assert other_api.post(f"/discovery/watches/{w}/stop").status_code == 404
    assert api.post(f"/discovery/watches/{w}/stop").status_code == 200
    assert state(w).revoked_at is not None
    assert tick() == 0 and fh_requests(receiver) == []


def test_a_deleted_posting_is_erased_and_never_pulled_again(api, other_api, receiver):
    uid = me(api)
    add_watch(uid, query="analyst")
    tick()
    (row,) = api.get("/discovery/jobs").json()
    assert other_api.delete(f"/discovery/jobs/{row['id']}").status_code == 404
    r = api.delete(f"/discovery/jobs/{row['id']}")
    assert r.status_code == 200 and r.json()["job_deleted"] is True, r.text
    assert api.get("/discovery/jobs").json() == []
    assert api.get(f"/discovery/jobs/{row['id']}").status_code == 404
    assert "Data Analyst" not in jobs(uid)
    with SessionLocal() as db:
        kept = db.get(DiscoveredJob, uuid.UUID(row["id"]))
        assert (kept.status, kept.normalized, kept.source_facts, kept.raw_ref) == (
            "dismissed",
            {},
            {},
            None,
        )
    tick(61)  # the posting is still listed by Freehire: it stays deleted
    assert api.get("/discovery/jobs").json() == [] and "Data Analyst" not in jobs(uid)


def test_deleting_a_posting_keeps_a_job_you_applied_to(api, receiver):
    add_watch(me(api), query="analyst")
    tick()
    (row,) = api.get("/discovery/jobs").json()
    assert api.post("/applications", json={"job_id": row["job_id"]}).status_code == 201
    r = api.delete(f"/discovery/jobs/{row['id']}").json()
    assert r["job_deleted"] is False and r["job_kept_because"] == "it has an application"
    assert "Data Analyst" in jobs(me(api))


def test_the_watch_command_records_a_bounded_standing_approval(api, capsys):
    uid = me(api)
    ok = ["create", "--email", OWNER, "--query", "financial analyst", "--every", "60",
          "--days", "30", "--retention", WHY]  # fmt: skip
    for bad, why in (
        (["--email", "another.synthetic@example.com"], "owner"),
        (["--every", "59"], "every"),
        (["--days", "91"], "days"),
        (["--retention", " "], "retention"),
        (["--query", " "], "query"),
    ):
        args = ok.copy()
        args[args.index(bad[0]) + 1] = bad[1]
        assert watch.main(args) == 2, bad
        assert why in capsys.readouterr().err
    assert watch.main(ok) == 0
    with SessionLocal() as db:
        (w,) = db.scalars(select(DiscoveryWatch)).all()
    assert (w.user_id, w.query, w.interval_seconds, w.retention) == (
        uid,
        "financial analyst",
        60,
        WHY,
    )
    assert timedelta(days=29, hours=23) < w.not_after - w.not_before <= timedelta(days=30)
    capsys.readouterr()
    assert watch.main(["list", "--email", OWNER]) == 0
    assert "financial analyst" in capsys.readouterr().out
    assert watch.main(["stop", "--id", str(w.id)]) == 0
    assert state(w.id).revoked_at is not None


def test_a_longer_retry_after_than_the_interval_is_honoured(api, receiver):
    w = add_watch(me(api), every=60)
    receiver.config(fh_mode="fh_rate_limited", fh_retry_after=900)
    assert tick() == 1
    assert state(w).next_check_at >= utcnow() + timedelta(seconds=890)
    assert tick(600) == 0 and len(fh_requests(receiver)) == 1


def test_a_check_asks_for_the_newest_postings_first(monkeypatch):
    sent = []

    def fake_get(self, path, params=None):
        sent.append(params)
        return 200, {"data": [], "meta": {"offset": 0, "total": 0}}

    monkeypatch.setattr(fh.FreehireApiProvider, "_get", fake_get)
    p = fh.FreehireApiProvider(base_url=FIXTURE)
    p.list_jobs(fh.DiscoveryFilters(query="analyst"), None)
    p.newest_first = True
    p.list_jobs(fh.DiscoveryFilters(query="analyst"), None)
    assert "sort" not in sent[0]  # an ordinary import keeps Freehire's own order
    assert (sent[1]["sort"], sent[1]["order"], sent[1]["q"]) == ("created_at", "desc", "analyst")
