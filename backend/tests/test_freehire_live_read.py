"""S7 (D55): a live Freehire read, for the owner's account only, with a single-use run approval
that names the exact search, the page limit, a time window and a retention statement. The
approval is used before any request, so a failed run needs a new one; the live address is checked
to resolve to a public host first. Here the local stand-in of Freehire's documented API plays the
live origin (fixtures/ats_receiver/freehire_fixture.py); its request table is the oracle for what
was asked, and nothing contacts Freehire."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.urlsafety import UnsafeURL
from app.modules.audit.models import AuditEvent
from app.modules.discovery import approve
from app.modules.discovery import provider as fh
from app.modules.discovery.models import DiscoveryRunApproval
from tests.execution_harness import BASE, Receiver
from tests.test_freehire_discovery import counts, fh_requests, me, run

FIXTURE = f"{BASE}/freehire-fixture"
OWNER = "synthetic.user@example.com"  # the `api` fixture's account
WHY = "Discovered postings are kept until I delete them."


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def checked(receiver, monkeypatch):
    """The stand-in plays Freehire: it is the live origin and not a fixture origin. The public
    destination check is recorded instead of resolving a local address."""
    receiver.reset()
    s = get_settings()
    for k, v in (("discovery_providers", ["freehire"]), ("freehire_base_url", FIXTURE),
                 ("freehire_api_key", ""), ("freehire_page_size", 2), ("freehire_max_pages", 10),
                 ("freehire_timeout_seconds", 2), ("discovery_owner_emails", [OWNER])):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(fh, "LIVE_ORIGIN", FIXTURE)
    monkeypatch.setattr(fh, "is_fixture_origin", lambda url: False)
    seen = []
    monkeypatch.setattr(fh, "resolve_public_destination", lambda url: seen.append(url) or ["x"])
    return seen


def approval(user_id, query="i", pages=5, start=-60, end=3600) -> uuid.UUID:
    now = utcnow()
    with SessionLocal() as db:
        a = DiscoveryRunApproval(
            user_id=user_id,
            provider="freehire",
            query=query,
            max_pages=pages,
            not_before=now + timedelta(seconds=start),
            not_after=now + timedelta(seconds=end),
            retention=WHY,
        )
        db.add(a)
        db.commit()
        return a.id


def used(approval_id) -> bool:
    with SessionLocal() as db:
        return db.get(DiscoveryRunApproval, approval_id).consumed_at is not None


def test_a_live_read_without_an_approval_is_refused_and_asks_nothing(api, receiver):
    r = run(api, query="i")
    assert r.status_code == 403 and "run approval" in r.json()["detail"], r.text
    assert fh_requests(receiver) == [] and counts(me(api)) == (0, 0)


def test_with_its_approval_the_owner_reads_live_once(api, receiver, checked):
    a = approval(me(api))
    r = run(api, query="i")
    assert r.status_code == 200, r.text
    assert r.json()["fetched"] == 4 and used(a)
    assert {x["q"] for x in fh_requests(receiver)} == {"i"}
    assert checked and all(u == FIXTURE for u in checked)  # checked before the requests
    again = run(api, query="i")  # single use: the same search needs a new approval
    assert again.status_code == 403
    assert len(fh_requests(receiver)) == 2  # the first run's two pages only
    with SessionLocal() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))]
    assert "discovery.run_approval.use" in actions and "discovery.import" in actions


def test_the_approval_binds_the_exact_search(api, receiver):
    a = approval(me(api), query="analyst")
    for q in ("i", "Analyst ", None):
        r = run(api, **({"query": q} if q is not None else {}))
        assert r.status_code == 403, (q, r.text)
    assert not used(a) and fh_requests(receiver) == []
    assert run(api, query="analyst").status_code == 200 and used(a)


def test_the_approved_page_limit_holds(api, receiver):
    approval(me(api), pages=1)
    r = run(api, query="i").json()
    assert (r["pages"], r["fetched"], r["truncated"]) == (1, 2, True)
    assert len(fh_requests(receiver)) == 1


def test_an_approval_outside_its_window_is_refused(api, receiver):
    late = approval(me(api), start=-7200, end=-60)
    early = approval(me(api), start=600, end=3600)
    assert run(api, query="i").status_code == 403
    assert not used(late) and not used(early) and fh_requests(receiver) == []


def test_only_the_owner_account_reads_live(api, other_api, receiver, monkeypatch):
    other = approval(me(other_api))
    r = run(other_api, query="i")
    assert r.status_code == 403 and "owner" in r.json()["detail"]
    assert not used(other)
    mine = approval(me(api))  # another account's approval is never used for mine
    monkeypatch.setattr(get_settings(), "discovery_owner_emails", [])
    assert run(api, query="i").status_code == 403  # no owner configured: nobody reads live
    assert not used(mine) and fh_requests(receiver) == []


def test_a_failed_run_used_its_approval_and_is_never_rerun(api, receiver):
    a = approval(me(api))
    receiver.config(fh_mode="fh_outage")
    r = run(api, query="i")
    assert r.status_code == 503 and used(a)
    receiver.config(fh_mode="normal")
    assert run(api, query="i").status_code == 403
    assert len(fh_requests(receiver)) == 1


def test_the_live_address_is_checked_before_the_approval_is_used(api, receiver, monkeypatch):
    def private(url):
        raise UnsafeURL("Host resolves to a blocked address")

    monkeypatch.setattr(fh, "resolve_public_destination", private)
    a = approval(me(api))
    r = run(api, query="i")
    assert r.status_code == 409 and "public" in r.json()["detail"]
    assert not used(a) and fh_requests(receiver) == []


def test_any_other_address_stays_refused_with_an_approval(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_base_url", "https://jobs.example.org")
    a = approval(me(api))
    r = run(api, query="i")
    assert r.status_code == 409 and "Live Freehire access is not enabled" in r.json()["detail"]
    assert not used(a) and fh_requests(receiver) == []


def test_refresh_and_healthcheck_never_read_live(api, receiver):
    approval(me(api), query="analyst")
    assert run(api, query="analyst").status_code == 200
    row = api.get("/discovery/jobs").json()[0]
    before = len(fh_requests(receiver))
    assert api.post(f"/discovery/jobs/{row['id']}/refresh").status_code == 409
    health = api.post("/discovery/providers/freehire/healthcheck").json()
    assert health["ok"] is False
    assert len(fh_requests(receiver)) == before


def test_the_approval_command_records_one_bounded_run(api, capsys):
    uid = me(api)
    ok = ["--email", OWNER, "--query", "financial analyst", "--pages", "2", "--hours", "3",
          "--retention", WHY]  # fmt: skip
    for bad, why in (
        (["--email", "another.synthetic@example.com"], "owner"),
        (["--pages", "6"], "pages"),
        (["--hours", "25"], "hours"),
        (["--retention", " "], "retention"),
        (["--query", " "], "query"),
    ):
        args = ok.copy()
        args[args.index(bad[0]) + 1] = bad[1]
        assert approve.main(args) == 2, bad
        assert why in capsys.readouterr().err
    assert approve.main(ok) == 0
    with SessionLocal() as db:
        (a,) = db.scalars(select(DiscoveryRunApproval)).all()
    assert (a.user_id, a.query, a.max_pages, a.retention) == (uid, "financial analyst", 2, WHY)
    assert timedelta(hours=2, minutes=59) < a.not_after - a.not_before <= timedelta(hours=3)
    assert a.consumed_at is None


def test_the_approval_command_refuses_an_account_that_does_not_exist(capsys, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_owner_emails", ["nobody@example.com"])
    args = ["--email", "nobody@example.com", "--query", "x", "--retention", WHY]
    assert approve.main(args) == 2 and "no account" in capsys.readouterr().err


def test_the_live_flag_opens_only_the_live_origin(monkeypatch):
    """Defence in depth: even with the flag set, any other address is refused before a request."""

    def no_network(*a, **k):
        raise AssertionError("a request was attempted")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", no_network)
    p = fh.FreehireApiProvider(base_url="https://jobs.example.org")
    p.live = True
    with pytest.raises(fh.DiscoveryError, match="not enabled"):
        p.list_jobs(fh.DiscoveryFilters(query="i"), None)


def test_a_run_held_back_by_retry_after_does_not_use_its_approval(api, receiver):
    """S6 (D67): the wait is checked before the approval, so the approval survives it."""
    from app.modules.discovery.models import DiscoveryBackoff

    first = approval(me(api))
    receiver.config(fh_mode="fh_rate_limited", fh_retry_after=120)
    assert run(api, query="i").status_code == 503 and used(first)
    sent = len(fh_requests(receiver))
    second = approval(me(api))
    receiver.config(fh_mode="normal")
    assert run(api, query="i").status_code == 429
    assert not used(second) and len(fh_requests(receiver)) == sent
    with SessionLocal() as db:
        b = db.get(DiscoveryBackoff, (me(api), "freehire"))
        b.not_before = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run(api, query="i").status_code == 200 and used(second)
