"""The Freehire discovery client (discovery/provider.FreehireApiProvider) against the local
stand-in of Freehire's documented read API (fixtures/ats_receiver/freehire_fixture.py, shapes
as in the API reference reviewed on 2026-10-21). Nothing here contacts Freehire; the fixture's
own request table is the oracle for what was asked."""

import dataclasses
import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.modules.discovery import service
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import (
    DiscoveryError,
    DiscoveryFilters,
    FreehireApiProvider,
    NormalizedJob,
    Page,
    enabled,
    plain_summary,
)
from app.modules.jobs.models import Job
from app.modules.providers import wording
from tests.execution_harness import BASE, Receiver

FIXTURE = f"{BASE}/freehire-fixture"
SUPPORT, TECH, ANALYST = (
    "fx-northwind-support-5020001",
    "fx-northwind-tech-5020002",
    "fx-contoso-analyst-77",
)
COORDINATOR, COURIER, COPY = (
    "fx-fabrikam-coordinator-12",
    "fx-tailspin-courier-31",
    "fx-northwind-support-copy-9",
)
KEY = "fixture-freehire-key-do-not-use"
CREDIT = {"text": "via freehire.me", "url": None}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _settings(receiver, monkeypatch):
    receiver.reset()
    s = get_settings()
    monkeypatch.setattr(s, "discovery_providers", ["freehire"])
    monkeypatch.setattr(s, "freehire_base_url", FIXTURE)
    monkeypatch.setattr(s, "freehire_api_key", "")
    monkeypatch.setattr(s, "freehire_page_size", 2)
    monkeypatch.setattr(s, "freehire_max_pages", 10)
    monkeypatch.setattr(s, "freehire_timeout_seconds", 2)


@pytest.fixture
def no_sleep(monkeypatch):
    """Fails the test if the client waits: pacing never sleeps, and nothing is retried."""

    def boom(*a, **k):
        raise AssertionError("the client slept")

    monkeypatch.setattr("time.sleep", boom)


def run(api, **body):
    return api.post("/discovery/import", json={"provider": "freehire", **body})


def fh_requests(receiver, route=None):
    reqs = receiver.ledger()["freehire_requests"]
    return [r for r in reqs if route is None or r["route"] == route]


def rows(user_id) -> dict[str, DiscoveredJob]:
    with SessionLocal() as db:
        found = db.scalars(select(DiscoveredJob).where(DiscoveredJob.user_id == user_id))
        return {r.source_job_id: r for r in found}


def me(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def counts(user_id) -> tuple[int, int]:
    with SessionLocal() as db:
        d = db.scalar(select(func.count(DiscoveredJob.id)).where(DiscoveredJob.user_id == user_id))
        j = db.scalar(select(func.count(Job.id)).where(Job.user_id == user_id))
        return d, j


# -- disabled by default, fixture only ---------------------------------------------------------


def test_defaults_are_off_with_no_base_url_and_no_key():
    s = Settings(_env_file=None)
    assert (s.discovery_providers, s.freehire_base_url, s.freehire_api_key) == ([], "", "")
    assert not hasattr(s, "freehire_min_interval_ms")  # no invented request rate


def test_disabled_by_default_and_nothing_is_requested(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_providers", [])
    listed = {p["name"]: p for p in api.get("/discovery/providers").json()}
    assert listed["freehire"]["enabled"] is False and listed["freehire_mock"]["enabled"] is False
    r = run(api)
    assert r.status_code == 409 and "disabled" in r.json()["detail"]
    assert api.post("/discovery/providers/freehire/healthcheck").status_code == 409
    assert fh_requests(receiver) == []
    assert api.post("/discovery/import", json={"provider": "nope"}).status_code == 404


def test_a_live_base_url_is_refused_before_any_request(api, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("a request was attempted")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", no_network)
    monkeypatch.setattr("socket.getaddrinfo", no_network)  # not even a name lookup
    monkeypatch.setattr(get_settings(), "freehire_base_url", "https://freehire.me")
    r = run(api)  # D55: no owner is configured and no run approval exists
    assert r.status_code == 403 and "nothing was requested" in r.json()["detail"], r.text
    health = api.post("/discovery/providers/freehire/healthcheck").json()
    assert health["ok"] is False and "not enabled" in health["detail"]
    assert counts(me(api)) == (0, 0)


def test_status_table_and_capabilities_never_claim_external_testing(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_api_key", KEY)
    body = api.get("/discovery/providers").json()
    fh = next(p for p in body if p["name"] == "freehire")
    assert fh["status"]["implemented_locally"] is True
    assert not any(fh["status"][k] for k in ("external_api_configured", "external_api_tested",
                                             "production_ready"))  # fmt: skip
    caps = fh["capabilities"]
    assert caps["submits_applications"] is False and caps["attribution"] == "via freehire.me"
    assert "600" not in str(caps)  # no undocumented rate is claimed
    assert fh["configured"] == {"base_url": True, "api_key": True}
    assert KEY not in str(body)


def test_mock_provider_is_never_enabled_in_production(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "discovery_providers", ["freehire_mock", "freehire"])
    assert enabled("freehire_mock")
    monkeypatch.setattr(s, "env", "production")
    assert not enabled("freehire_mock")


# -- documented response shapes ----------------------------------------------------------------


def test_import_pages_normalizes_and_deduplicates(api, receiver):
    r = run(api)
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["fetched"], res["pages"], res["truncated"], res["stop_reason"]) == (
        5, 3, False, None)  # fmt: skip
    assert (res["created"], res["incomplete"], res["malformed"]) == (5, 1, 0)
    assert (res["linked_new_jobs"], res["linked_existing_jobs"]) == (3, 1)
    got = [(s["offset"], s["limit"]) for s in fh_requests(receiver, "search")]
    assert got == [(0, 2), (2, 2), (4, 2)]
    assert not any(s["auth_present"] for s in fh_requests(receiver))  # public read, no key

    r = rows(me(api))
    assert COURIER not in r  # closed at the source: never in search results
    support = r[SUPPORT].normalized
    assert support["job_url"].endswith("/gh2/northwind/jobs/5020001?utm_source=freehire.me")
    assert (support["workplace"], support["employment_type"]) == ("hybrid", "full_time")
    assert r[TECH].normalized["workplace"] == "onsite"
    assert r[ANALYST].normalized["workplace"] == "remote"
    assert support["description_summary"] == "Help customers by email and chat."
    assert support["published_on"] == "2026-10-01" and support["source_platform"] == "greenhouse"
    assert support["source_updated_at"] == "2026-10-02T10:00:00Z"
    assert support["ats_provider"] == "unknown"  # a fixture origin is not claimed to be an ATS
    assert r[SUPPORT].source_facts["sponsorship_offered"] == {
        "value": "yes", "stated_by": "freehire", "basis": "provider enrichment"}  # fmt: skip
    assert r[TECH].source_facts["sponsorship_offered"]["value"] == "unknown"
    assert r[ANALYST].source_facts["sponsorship_offered"]["value"] == "no"
    assert r[ANALYST].normalized["location"] is None  # never guessed
    assert r[COPY].job_id == r[SUPPORT].job_id and r[COPY].link_basis == "job_url"
    assert r[COORDINATOR].status == "incomplete" and r[COORDINATOR].job_id is None
    assert counts(me(api)) == (5, 3)


def test_work_mode_is_read_from_the_top_level_only(api, receiver):
    receiver.config(fh_mode="fh_legacy_shape")  # work mode only under enrichment
    run(api)
    support = rows(me(api))[SUPPORT].normalized
    assert support["workplace"] == "unknown"  # the old assumption is not read
    assert support["employment_type"] == "full_time"  # documented under enrichment


def test_undocumented_fields_are_not_read():
    raw = {"public_slug": "a-1", "title": "T", "company": "C", "url": f"{BASE}/x",
           "last_seen_at": "2026-10-20T08:00:00Z", "work_mode": "satellite",
           "enrichment": {"work_mode": "remote", "visa_sponsorship": "maybe"}}  # fmt: skip
    n = FreehireApiProvider(base_url=FIXTURE).normalize_job(raw)
    assert n.source_last_seen_at is None
    assert n.workplace == "unknown"  # not a documented value, and enrichment is not consulted
    assert n.source_facts["sponsorship_offered"]["value"] == "unknown"  # not a boolean


def test_no_raw_payload_is_kept(api):
    run(api)
    row = rows(me(api))[SUPPORT]
    assert set(row.normalized) == {f.name for f in dataclasses.fields(NormalizedJob)}
    assert set(row.raw_ref) == {"provider", "source_job_id", "fingerprint", "fields"}
    stored = str(row.normalized) + str(row.raw_ref) + str(row.source_facts)
    for raw_only in ("<script>", "<p>", "Customer support.", "fake_freshness", "'view_count': 3"):
        assert raw_only not in stored, raw_only
    with SessionLocal() as db:  # the tracker job gets the plain summary, not the source HTML
        assert db.get(Job, row.job_id).description == "Help customers by email and chat."


def test_reimport_is_unchanged(api):
    run(api)
    res = run(api).json()
    assert (res["created"], res["updated"], res["unchanged"]) == (0, 0, 5)
    assert counts(me(api)) == (5, 3)


def test_existing_jobs_are_matched_by_url_then_conservatively_and_never_modified(api):
    mine = {"url": f"{BASE}/gh2/northwind/jobs/5020002", "title": "My own title",
            "location": "My notes"}  # fmt: skip
    tech = api.post("/jobs", json=mine).json()
    no_url = {"title": "Data Analyst", "employer": "Contoso Example (fictional)"}
    analyst = api.post("/jobs", json=no_url).json()
    res = run(api).json()
    assert (res["linked_new_jobs"], res["linked_existing_jobs"]) == (1, 3)
    r = rows(me(api))
    assert str(r[TECH].job_id) == tech["job"]["id"] and r[TECH].link_basis == "job_url"
    assert str(r[ANALYST].job_id) == analyst["job"]["id"]
    assert r[ANALYST].link_basis == "employer_title_location"
    job = api.get(f"/jobs/{tech['job']['id']}").json()
    assert (job["title"], job["location"]) == ("My own title", "My notes")  # untouched
    assert job["description"] is None  # not filled in by discovery either


def test_a_changed_posting_is_recorded_and_the_users_job_is_left_alone(api, receiver):
    run(api)
    job_id = str(rows(me(api))[SUPPORT].job_id)
    api.patch(f"/jobs/{job_id}", json={"title": "Edited by me"})
    receiver.config(fh_mode="fh_changed")
    res = run(api).json()
    assert (res["updated"], res["unchanged"]) == (1, 4)
    changed = next(x for x in res["records"] if x["source_job_id"] == SUPPORT)
    assert changed["changed_fields"] == ["title", "location"]
    assert api.get(f"/jobs/{job_id}").json()["title"] == "Edited by me"
    row = rows(me(api))[SUPPORT]
    assert row.normalized["title"] == "Senior Support Specialist" and row.changed_at is not None


# -- attribution -------------------------------------------------------------------------------


def test_every_listing_is_credited_via_freehire(api):
    run(api)
    listed = api.get("/discovery/jobs").json()
    assert listed and all(x["attribution"] == CREDIT for x in listed)
    assert all(r.normalized["attribution"] == CREDIT for r in rows(me(api)).values())
    job_id = str(rows(me(api))[SUPPORT].job_id)
    sources = api.get(f"/jobs/{job_id}").json()["discovered_from"]
    assert len(sources) == 2 and {s["label"] for s in sources} == {"Freehire"}  # both records
    assert all(s["attribution"] == CREDIT and s["source_url"] for s in sources)


def test_the_mock_is_never_credited_to_freehire(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_providers", ["freehire_mock"])
    r = api.post("/discovery/import", json={"provider": "freehire_mock"})
    assert r.status_code == 200, r.text
    texts = {x["attribution"]["text"] for x in api.get("/discovery/jobs").json()}
    assert texts == {"local mock data (not from freehire.me)"}


# -- pacing from documented headers, 429 -------------------------------------------------------


def test_paging_stops_when_the_documented_budget_is_used_up(api, receiver, no_sleep):
    receiver.config(fh_rate_limit=2)  # the fixture reports Remaining 1, then 0
    res = run(api).json()
    assert (res["fetched"], res["pages"], res["truncated"]) == (4, 2, True)
    sent = "X-RateLimit-Remaining: 0, X-RateLimit-Reset: 60"
    assert res["stop_reason"] == (
        f"Freehire's rate budget is used up ({sent}); stopped without waiting or retrying."
    )
    assert len(fh_requests(receiver, "search")) == 2  # no request past the budget
    assert res["created"] == 4  # what was read is kept, marked incomplete (truncated)


def test_without_rate_headers_nothing_is_assumed_or_waited(api, receiver, no_sleep):
    receiver.config(fh_mode="fh_no_rate_headers")
    res = run(api).json()
    assert (res["fetched"], res["pages"], res["truncated"]) == (5, 3, False)


def test_a_429_is_reported_with_retry_after_and_never_retried(api, receiver, no_sleep):
    receiver.config(fh_mode="fh_rate_limited")
    r = run(api)
    assert r.status_code == 503
    assert ("Freehire is rate limiting requests (Retry-After: 30 s); not retried. "
            "Nothing was changed.") == r.json()["detail"]  # fmt: skip
    assert len(fh_requests(receiver)) == 1
    assert counts(me(api)) == (0, 0)


# -- stale and closed postings -----------------------------------------------------------------


def test_a_posting_closed_since_is_absent_from_search_and_seen_closed_by_detail(api, receiver):
    run(api)
    tech = rows(me(api))[TECH]
    receiver.config(fh_mode="fh_closed_now")
    res = run(api).json()
    assert res["fetched"] == 4 and TECH not in [x["source_job_id"] for x in res["records"]]
    # A query-scoped listing is never complete: absence alone does not mark it stale.
    assert rows(me(api))[TECH].stale is False
    r = api.post(f"/discovery/jobs/{tech.id}/refresh").json()
    assert r["outcome"] == "updated" and r["job"]["stale_reason"] == "closed at source"
    assert r["job"]["job_id"] == str(tech.job_id)  # still linked; the tracker job is kept as is
    assert api.get(f"/jobs/{tech.job_id}").json()["title"] == "Field Technician"


def test_detail_serves_a_closed_posting_and_it_never_creates_a_job(api):
    p = FreehireApiProvider(base_url=FIXTURE)
    raw = p.get_job(COURIER)
    assert raw["closed_at"] and p.normalize_job(raw).closed_at_source is True
    assert p.get_job("fx-unknown-1") is None  # 404


def test_refresh_marks_a_record_gone(api, receiver):
    run(api)
    row_id = str(rows(me(api))[SUPPORT].id)
    receiver.config(fh_mode="fh_changed")
    r = api.post(f"/discovery/jobs/{row_id}/refresh").json()
    assert r["outcome"] == "updated" and r["job"]["changed_fields"] == ["title", "location"]
    receiver.config(fh_mode="fh_gone")
    r = api.post(f"/discovery/jobs/{row_id}/refresh").json()
    assert r["outcome"] == "gone" and r["job"]["stale_reason"] == "no longer at the source"
    receiver.config(fh_mode="fh_outage")
    assert api.post(f"/discovery/jobs/{row_id}/refresh").status_code == 503


# -- filters -----------------------------------------------------------------------------------


def test_filters_use_only_what_the_source_supplied(api):
    res = run(api, titles=["support"]).json()
    assert res["excluded_by_filters"] == 3 and res["created"] == 2  # support + its copy
    res = run(api, cities=["Riverton"]).json()
    by = {x["source_job_id"]: x["filter"] for x in res["records"]}
    assert by[SUPPORT]["result"] == "match" and by[TECH]["result"] == "match"
    # The analyst has no location: not enough data, never "excluded" or "matched" by guess.
    assert by[ANALYST] == {"result": "insufficient", "fields": ["location"]}
    assert COORDINATOR not in by  # Lakeside: excluded by what the source says
    res = run(api, workplaces=["onsite"]).json()
    by = {x["source_job_id"]: x["filter"] for x in res["records"]}
    assert by[TECH]["result"] == "match" and ANALYST not in by and SUPPORT not in by
    assert by[COORDINATOR] == {"result": "insufficient", "fields": ["workplace"]}


def test_sponsorship_filter_matches_only_a_stated_yes(api):
    res = run(api, sponsorship="offered", include_insufficient=False).json()
    assert [x["source_job_id"] for x in res["records"]] == [SUPPORT]
    assert res["insufficient_data"] == 3  # no statement: unknown, not "no"
    assert res["excluded_by_filters"] == 1  # the analyst: the source says no


def test_preferences_are_used_only_when_asked(api):
    r = api.put("/profile/preferences", json={"titles": ["Technician"], "work_modes": ["onsite"]})
    assert r.status_code == 200, r.text
    assert run(api).json()["created"] == 5  # not applied implicitly
    res = run(api, use_preferences=True).json()
    matched = [x["source_job_id"] for x in res["records"] if x["filter"]["result"] == "match"]
    assert matched == [TECH]


# -- failures change nothing -------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,message",
    [
        ("fh_outage", "Freehire is unavailable (HTTP 503)"),
        ("fh_bad_json", "response was not JSON"),
        ("fh_loop", "returned a different page than requested"),
        ("fh_slow", "Freehire did not respond"),
    ],
)
def test_provider_failures_change_nothing(api, receiver, mode, message):
    receiver.config(fh_mode=mode, fh_slow_s=4)
    r = run(api)
    assert r.status_code == 503 and message in r.json()["detail"], r.text
    assert "Nothing was changed" in r.json()["detail"]
    assert counts(me(api)) == (0, 0)


def test_an_outage_never_blocks_manual_jobs_imports_or_tracking(api, receiver):
    receiver.config(fh_mode="fh_outage")
    assert run(api).status_code == 503
    r = api.post("/jobs", json={"title": "Analyst", "employer": "Example Co (fictional)"})
    assert r.status_code == 201
    csv = "job_url,title,employer\n,Clerk,Example Two (fictional)\n"
    imp = api.post("/jobs/import", files={"file": ("jobs.csv", csv.encode(), "text/csv")})
    assert imp.status_code == 200 and imp.json()["created"] == 1
    app = api.post("/applications", json={"job_id": r.json()["job"]["id"]})
    assert app.status_code == 201, app.text


def test_malformed_records_are_skipped_and_counted(api, receiver):
    receiver.config(fh_mode="fh_malformed")
    res = run(api).json()
    assert res["malformed"] == 2 and res["created"] == 5


def test_paging_is_bounded_and_loops_are_refused():
    class Looping:
        name = "loop"

        def list_jobs(self, filters, cursor):
            return Page([{"public_slug": "a"}], "same")

    with pytest.raises(DiscoveryError) as e:
        service.fetch_all(Looping(), DiscoveryFilters(), max_pages=50)
    assert e.value.kind == "pagination_loop"

    class Endless:
        def list_jobs(self, filters, cursor):
            return Page([{}], str(int(cursor or 0) + 1))

    records, pages, stop = service.fetch_all(Endless(), DiscoveryFilters(), max_pages=3)
    assert (len(records), pages, stop) == (3, 3, "page limit reached (3 pages)")
    # The documented window: no page beyond offset + limit = 10000 is requested.
    p = FreehireApiProvider(base_url=FIXTURE)
    assert p.list_jobs(DiscoveryFilters(), "9999").records == []


def test_truncated_listing_is_reported(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_max_pages", 2)
    res = run(api).json()
    assert (res["fetched"], res["pages"], res["truncated"]) == (4, 2, True)
    assert res["stop_reason"] == "page limit reached (2 pages)"


# -- health, isolation, secrets ----------------------------------------------------------------


def test_healthcheck_makes_no_request_and_never_uses_status(api, receiver):
    receiver.config(fh_mode="fh_outage")
    h = api.post("/discovery/providers/freehire/healthcheck").json()
    assert h["ok"] is True and "no request made" in h["detail"]
    assert fh_requests(receiver) == []  # neither /status nor anything else
    run(api)  # an import does not touch /status either
    assert fh_requests(receiver, "status") == []


def test_incomplete_records_wait_for_a_manual_import(api):
    run(api)
    row_id = str(rows(me(api))[COORDINATOR].id)
    d = api.get(f"/discovery/jobs/{row_id}").json()
    assert d["missing"] == ["no job or application URL"]
    assert d["route"] == {"route": "manual_handoff", "provider": "manual_handoff",
                          "message": "Import this job manually.",
                          "reason": "source_record_incomplete",
                          "authorization": "not_applicable", "evidence": "none",
                          "label": "Manual: apply on the employer's site",
                          "provider_support": wording.SUPPORT_LABELS["manual"]}  # fmt: skip


def test_discovered_jobs_are_user_scoped(api, other_api):
    run(api)
    row = rows(me(api))[SUPPORT]
    assert other_api.get("/discovery/jobs").json() == []
    assert other_api.get(f"/discovery/jobs/{row.id}").status_code == 404
    assert other_api.post(f"/discovery/jobs/{row.id}/refresh").status_code == 404
    assert other_api.get(f"/jobs/{row.job_id}").status_code == 404
    assert len(api.get("/discovery/jobs").json()) == 5


def test_the_key_is_sent_by_the_server_only_and_never_shown(api, receiver, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(get_settings(), "freehire_api_key", KEY)
    res = run(api)
    assert res.status_code == 200
    assert all(s["auth_present"] for s in fh_requests(receiver, "search"))
    text = res.text + api.get("/discovery/jobs").text + api.get("/discovery/providers").text
    text += caplog.text
    assert KEY not in text


def test_untrusted_markup_becomes_short_plain_text():
    assert plain_summary("<p>a &amp; b</p><script>alert(1)</script><style>x{}</style>") == "a & b"
    assert plain_summary("x" * 900).endswith("…") and len(plain_summary("x" * 900)) == 500
    assert plain_summary(None) is None


# -- S6 (D67): contract hardening --------------------------------------------------------------


def test_counters_and_reality_ticking_are_not_a_change(api, receiver):
    """R9.4: between reads only `reality`, the view and application counters and the
    enrichment metadata change; nothing NoEfforts reads did, so nothing is "updated"."""
    run(api)
    receiver.config(fh_mode="fh_reality_tick")
    res = run(api).json()
    assert (res["created"], res["updated"], res["unchanged"]) == (0, 0, 5)
    row = rows(me(api))[SUPPORT]
    r = api.post(f"/discovery/jobs/{row.id}/refresh")
    assert r.status_code == 200 and r.json()["outcome"] == "unchanged"
    receiver.config(fh_mode="fh_changed")  # a real change is still seen
    assert run(api).json()["updated"] == 1


def test_a_tagged_url_and_its_untagged_form_are_one_posting():
    """R9.5: Freehire's own tag and a referral parameter never make another posting."""
    from app.modules.jobs.canonical import canonicalize_url, dedupe_key, detect_ats

    plain = "https://boards.greenhouse.io/acme/jobs/4000001"
    for tagged in (
        f"{plain}?utm_source=freehire.me",
        f"{plain}?gh_src=feed&utm_medium=board",
        f"{plain}?referral-code=SYNTH42",
        f"{plain}?referral_code=SYNTH42&ref=x",
    ):
        c, p = canonicalize_url(tagged), canonicalize_url(plain)
        key = dict(employer="Acme Example (fictional)", title="Engineer", location=None)
        assert dedupe_key(canonical_url=c, **key) == dedupe_key(canonical_url=p, **key)
        assert detect_ats(c).provider == detect_ats(p).provider == "greenhouse"


def test_an_aggregator_url_is_an_unknown_ats_and_a_manual_handoff(api):
    """R9.6: a posting address on a host that is not an ATS NoEfforts knows."""
    job = api.post("/jobs", json={"url": "https://jobs.aggregator-example.test/listing/77",
                                  "title": "Data Analyst"}).json()["job"]  # fmt: skip
    assert job["ats_provider"] == "unknown"
    route = api.get(f"/jobs/{job['id']}/route").json()
    assert route["route"] == "manual_handoff", route


def test_the_2026_10_26_undocumented_fields_are_not_read():
    """R9.7: fields seen in Freehire's responses but not documented change nothing NoEfforts
    keeps or compares."""
    from app.modules.discovery.provider import freehire_fingerprint

    base = {"public_slug": "a-1", "title": "T", "company": "C", "url": f"{BASE}/x"}
    extra = {"last_seen_at": "2026-10-20T08:00:00Z", "ghost": True,
             "auto_apply_available": True, "direct_apply": True}  # fmt: skip
    p = FreehireApiProvider(base_url=FIXTURE)
    a, b = p.normalize_job(base), p.normalize_job({**base, **extra})
    assert dataclasses.replace(b, raw_keys=a.raw_keys) == a
    assert freehire_fingerprint({**base, **extra}) == freehire_fingerprint(base)
    assert b.source_last_seen_at is None and set(b.source_facts) == {"sponsorship_offered"}


def test_an_import_before_retry_after_is_refused(api, other_api, receiver, no_sleep):
    """R9.2: after a 429 with Retry-After, this user's next import waits until then: refused
    with a typed error before any request, and nothing re-runs by itself. Others are not
    held back."""
    from datetime import timedelta

    from app.modules.discovery.models import DiscoveryBackoff

    receiver.config(fh_mode="fh_rate_limited", fh_retry_after=120)
    assert run(api).status_code == 503
    sent = len(fh_requests(receiver))
    receiver.config(fh_mode="normal")
    r = run(api)
    assert r.status_code == 429 and "Nothing was sent" in r.json()["detail"]
    assert len(fh_requests(receiver)) == sent  # no request at all
    assert run(other_api).status_code == 200  # another user's imports are not held back
    sent = len(fh_requests(receiver))
    row = rows(me(other_api))[SUPPORT]
    assert api.post(f"/discovery/jobs/{row.id}/refresh").status_code == 404  # not theirs
    with SessionLocal() as db:  # the wait ends
        b = db.get(DiscoveryBackoff, (me(api), "freehire"))
        b.not_before = b.not_before - timedelta(seconds=121)
        db.commit()
    assert run(api).status_code == 200
    assert len(fh_requests(receiver)) > sent


def test_without_retry_after_nothing_is_held_back(api, receiver, no_sleep):
    """A refusal without a Retry-After in seconds, or an outage, assumes no wait."""
    for mode, extra in (("fh_outage", {}), ("fh_rate_limited", {"fh_retry_after": ""})):
        receiver.config(fh_mode=mode, **extra)
        assert run(api).status_code == 503
        receiver.config(fh_mode="normal")
        assert run(api).status_code == 200, mode


def test_a_refused_refresh_holds_back_the_next_refresh_and_import(api, receiver, no_sleep):
    """R9.2: a Retry-After met on a single-record refresh holds back this user's next refresh
    and import alike; neither sends anything."""
    run(api)
    row = rows(me(api))[SUPPORT]
    receiver.config(fh_mode="fh_rate_limited", fh_retry_after=120)
    r = api.post(f"/discovery/jobs/{row.id}/refresh")
    assert r.status_code == 503 and "not retried" in r.json()["detail"]
    sent = len(fh_requests(receiver))
    receiver.config(fh_mode="normal")
    r = api.post(f"/discovery/jobs/{row.id}/refresh")
    assert r.status_code == 429 and "Nothing was sent" in r.json()["detail"]
    assert run(api).status_code == 429
    assert len(fh_requests(receiver)) == sent
