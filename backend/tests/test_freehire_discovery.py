"""The Freehire discovery client (discovery/provider.FreehireApiProvider) against the local
stand-in of Freehire's documented read API (fixtures/ats_receiver/freehire_fixture.py). Nothing
here contacts Freehire; the fixture's own request table is the oracle for what was asked."""

import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.discovery import service
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import (
    DiscoveryError,
    DiscoveryFilters,
    FreehireApiProvider,
    Page,
    enabled,
    plain_summary,
)
from app.modules.jobs.models import Job
from tests.execution_harness import BASE, Receiver

FIXTURE = f"{BASE}/freehire-fixture"
SUPPORT, TECH, ANALYST = (
    "fx-northwind-support-5020001",
    "fx-northwind-tech-5020002",
    ("fx-contoso-analyst-77"),
)
COORDINATOR, COURIER, COPY = (
    "fx-fabrikam-coordinator-12",
    "fx-tailspin-courier-31",
    "fx-northwind-support-copy-9",
)
KEY = "fixture-freehire-key-do-not-use"


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
    monkeypatch.setattr(s, "freehire_min_interval_ms", 0)
    monkeypatch.setattr(s, "freehire_timeout_seconds", 2)


def run(api, **body):
    return api.post("/discovery/import", json={"provider": "freehire", **body})


def searches(receiver):
    return [r for r in receiver.ledger()["freehire_requests"] if r["route"] == "search"]


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


# -- feature flag and live access -------------------------------------------------------------


def test_disabled_by_default_and_nothing_is_requested(api, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_providers", [])
    listed = {p["name"]: p for p in api.get("/discovery/providers").json()}
    assert listed["freehire"]["enabled"] is False and listed["freehire_mock"]["enabled"] is False
    r = run(api)
    assert r.status_code == 409 and "disabled" in r.json()["detail"]
    assert api.post("/discovery/providers/freehire/healthcheck").status_code == 409
    assert receiver.ledger()["freehire_requests"] == []
    assert api.post("/discovery/import", json={"provider": "nope"}).status_code == 404


def test_a_live_base_url_is_refused_before_any_request(api, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("a request was attempted")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", no_network)
    monkeypatch.setattr(get_settings(), "freehire_base_url", "https://freehire.me")
    r = run(api)
    assert r.status_code == 409 and "Live Freehire access is not enabled" in r.json()["detail"]
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
    assert fh["capabilities"]["submits_applications"] is False
    assert fh["configured"] == {"base_url": True, "api_key": True}
    assert KEY not in str(body)


def test_mock_provider_is_never_enabled_in_production(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "discovery_providers", ["freehire_mock", "freehire"])
    assert enabled("freehire_mock")
    monkeypatch.setattr(s, "env", "production")
    assert not enabled("freehire_mock")


# -- import, normalization, deduplication ------------------------------------------------------


def test_import_pages_normalizes_and_deduplicates(api, receiver):
    r = run(api)
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["fetched"], res["pages"], res["truncated"]) == (6, 3, False)
    assert (res["created"], res["incomplete"], res["malformed"]) == (6, 1, 0)
    assert (res["linked_new_jobs"], res["linked_existing_jobs"]) == (3, 1)
    assert [(s["offset"], s["limit"]) for s in searches(receiver)] == [(0, 2), (2, 2), (4, 2)]
    assert not any(s["auth_present"] for s in searches(receiver))  # public read, no key

    r = rows(me(api))
    support = r[SUPPORT].normalized
    assert support["job_url"].endswith("/gh2/northwind/jobs/5020001?utm_source=freehire.me")
    assert (support["workplace"], support["employment_type"]) == ("hybrid", "full_time")
    assert support["description_summary"] == "Help customers by email and chat."
    assert support["published_on"] == "2026-10-01" and support["source_platform"] == "greenhouse"
    assert support["ats_provider"] == "unknown"  # a fixture origin is not claimed to be an ATS
    assert r[SUPPORT].source_facts["sponsorship_offered"] == {
        "value": "yes", "stated_by": "freehire", "basis": "provider enrichment"}  # fmt: skip
    assert r[TECH].source_facts["sponsorship_offered"]["value"] == "unknown"
    assert r[ANALYST].source_facts["sponsorship_offered"]["value"] == "no"
    assert r[ANALYST].normalized["location"] is None  # never guessed
    assert r[COPY].job_id == r[SUPPORT].job_id and r[COPY].link_basis == "job_url"
    assert r[COORDINATOR].status == "incomplete" and r[COORDINATOR].job_id is None
    assert r[COURIER].status == "closed" and r[COURIER].stale_reason == "closed at source"
    assert r[COURIER].job_id is None  # a closed posting never creates a tracker job
    # The raw reference names fields, never their content.
    assert "description" in r[SUPPORT].raw_ref["fields"]
    assert "Help customers" not in str(r[SUPPORT].raw_ref)
    assert counts(me(api)) == (6, 3)


def test_reimport_is_unchanged(api):
    run(api)
    res = run(api).json()
    assert (res["created"], res["updated"], res["unchanged"]) == (0, 0, 6)
    assert counts(me(api)) == (6, 3)


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
    assert (res["updated"], res["unchanged"]) == (1, 5)
    changed = next(x for x in res["records"] if x["source_job_id"] == SUPPORT)
    assert changed["changed_fields"] == ["title", "location"]
    assert api.get(f"/jobs/{job_id}").json()["title"] == "Edited by me"
    row = rows(me(api))[SUPPORT]
    assert row.normalized["title"] == "Senior Support Specialist" and row.changed_at is not None


def test_source_is_attributed_on_the_job(api):
    run(api)
    job_id = str(rows(me(api))[SUPPORT].job_id)
    sources = api.get(f"/jobs/{job_id}").json()["discovered_from"]
    assert {s["label"] for s in sources} == {"Freehire"} and len(sources) == 2  # both records
    assert all(s["source_url"] for s in sources)


# -- filters -----------------------------------------------------------------------------------


def test_filters_use_only_what_the_source_supplied(api):
    res = run(api, titles=["support"]).json()
    assert res["excluded_by_filters"] == 4 and res["created"] == 2  # support + its copy
    res = run(api, cities=["Riverton"]).json()
    by = {x["source_job_id"]: x["filter"] for x in res["records"]}
    assert by[SUPPORT]["result"] == "match" and by[TECH]["result"] == "match"
    # The analyst has no location: not enough data, never "excluded" or "matched" by guess.
    assert by[ANALYST] == {"result": "insufficient", "fields": ["location"]}
    assert COORDINATOR not in by  # Lakeside: excluded by what the source says
    res = run(api, cities=["Riverton"], workplaces=["hybrid", "onsite"]).json()
    by = {x["source_job_id"]: x["filter"] for x in res["records"]}
    assert ANALYST not in by  # remote: a stated mismatch excludes, whatever else is missing
    assert by[COURIER] == {"result": "insufficient", "fields": ["workplace"]}


def test_sponsorship_filter_matches_only_a_stated_yes(api):
    res = run(api, sponsorship="offered", include_insufficient=False).json()
    assert [x["source_job_id"] for x in res["records"]] == [SUPPORT]
    assert res["insufficient_data"] == 4  # no statement: unknown, not "no"
    assert res["excluded_by_filters"] == 1  # the analyst: the source says no


def test_preferences_are_used_only_when_asked(api):
    r = api.put("/profile/preferences", json={"titles": ["Technician"], "work_modes": ["onsite"]})
    assert r.status_code == 200, r.text
    assert run(api).json()["created"] == 6  # not applied implicitly
    res = run(api, use_preferences=True).json()
    matched = [x["source_job_id"] for x in res["records"] if x["filter"]["result"] == "match"]
    assert matched == [TECH]


# -- errors: nothing is written ----------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,message",
    [
        ("fh_rate_limited", "rate limiting requests (retry after 30 s); not retried"),
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
    if mode == "fh_rate_limited":
        assert len(searches(receiver)) == 1  # never retried


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
    receiver_jobs = run(api).json()
    assert receiver_jobs["malformed"] == 2 and receiver_jobs["created"] == 6


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

    records, pages, truncated = service.fetch_all(Endless(), DiscoveryFilters(), max_pages=3)
    assert (len(records), pages, truncated) == (3, 3, True)
    # The documented window: no page beyond offset + limit = 10000 is requested.
    p = FreehireApiProvider(base_url=FIXTURE)
    assert p.list_jobs(DiscoveryFilters(), "9999").records == []


def test_truncated_listing_is_reported(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "freehire_max_pages", 2)
    res = run(api).json()
    assert (res["fetched"], res["pages"], res["truncated"]) == (4, 2, True)


# -- single records, health, isolation, secrets -----------------------------------------------


def test_refresh_reads_one_record_and_marks_it_gone(api, receiver):
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


def test_healthcheck(api, receiver):
    assert api.post("/discovery/providers/freehire/healthcheck").json()["ok"] is True
    receiver.config(fh_mode="fh_outage")
    h = api.post("/discovery/providers/freehire/healthcheck").json()
    assert h == {"ok": False, "detail": "Freehire is unavailable (HTTP 503)."}


def test_incomplete_records_wait_for_a_manual_import(api):
    run(api)
    row_id = str(rows(me(api))[COORDINATOR].id)
    d = api.get(f"/discovery/jobs/{row_id}").json()
    assert d["missing"] == ["no job or application URL"]
    assert d["route"] == {"route": "manual_handoff", "provider": "manual_handoff",
                          "message": "Import this job manually."}  # fmt: skip


def test_discovered_jobs_are_user_scoped(api, other_api):
    run(api)
    row = rows(me(api))[SUPPORT]
    assert other_api.get("/discovery/jobs").json() == []
    assert other_api.get(f"/discovery/jobs/{row.id}").status_code == 404
    assert other_api.post(f"/discovery/jobs/{row.id}/refresh").status_code == 404
    assert other_api.get(f"/jobs/{row.job_id}").status_code == 404
    assert len(api.get("/discovery/jobs").json()) == 6


def test_the_key_is_sent_by_the_server_only_and_never_shown(api, receiver, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(get_settings(), "freehire_api_key", KEY)
    res = run(api)
    assert res.status_code == 200
    assert all(s["auth_present"] for s in searches(receiver))
    text = res.text + api.get("/discovery/jobs").text + api.get("/discovery/providers").text
    text += caplog.text
    assert KEY not in text


def test_untrusted_markup_becomes_short_plain_text():
    assert plain_summary("<p>a &amp; b</p><script>alert(1)</script><style>x{}</style>") == "a & b"
    assert plain_summary("x" * 900).endswith("…") and len(plain_summary("x" * 900)) == 500
    assert plain_summary(None) is None
