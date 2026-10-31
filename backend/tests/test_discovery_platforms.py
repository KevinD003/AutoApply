"""D100: discovered postings by application platform, read from each posting's URL (the job's
canonical ATS identity). An import can keep only the platforms you choose; every posting it keeps
becomes a job as before. The URLs below are synthetic and are only parsed, never fetched."""

import json

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.discovery import service
from app.modules.discovery.provider import DiscoveryFilters, FreehireMockProvider
from tests.test_discovery import me, rows

URLS = {
    "fx-gh": "https://boards.greenhouse.io/examplecorp/jobs/1234567",
    "fx-lever": "https://jobs.lever.co/examplecorp/0f0e0d0c-0000-4000-8000-000000000001",
    "fx-ashby": "https://jobs.ashbyhq.com/examplecorp/0f0e0d0c-0000-4000-8000-000000000002",
    "fx-workday": "https://examplecorp.wd5.myworkdayjobs.com/External/job/Remote/Analyst_R-12345",
    "fx-other": "https://jobs.example.test/examplecorp/analyst-1",
}


def feed(tmp_path):
    jobs = [
        {"id": k, "title": f"Analyst {i}", "company": "Example Corp (fictional)",
         "location": "Riverton", "workplace": "remote", "url": u, "apply_url": u,
         "published": "2026-10-01", "summary": "Synthetic posting."}
        for i, (k, u) in enumerate(URLS.items())
    ]  # fmt: skip
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps({"jobs": jobs}))
    return path


def run(uid, path, platforms=()):
    with SessionLocal() as db:
        res = service.import_from(
            db, uid, FreehireMockProvider(path), DiscoveryFilters(platforms=list(platforms))
        )
        db.commit()
        return res


def test_an_import_keeps_only_the_chosen_platforms(api, tmp_path):
    uid = me(api)
    res = run(uid, feed(tmp_path), ["greenhouse", "lever"])
    assert (res.created, res.excluded_by_filters, res.linked_new_jobs) == (2, 3, 2)
    r = rows(uid)
    assert set(r) == {"fx-gh", "fx-lever"} and all(x.job_id for x in r.values())
    assert {x.filter_result["result"] for x in r.values()} == {"match"}


def test_postings_are_listed_and_counted_by_platform(api, other_api, tmp_path):
    uid = me(api)
    res = run(uid, feed(tmp_path))
    assert (res.created, res.excluded_by_filters) == (5, 0)
    listed = api.get("/discovery/platforms").json()
    counts = {p["platform"]: (p["label"], p["count"]) for p in listed}
    assert counts == {"ashby": ("Ashby", 1), "greenhouse": ("Greenhouse", 1),
                      "lever": ("Lever", 1), "workday": ("Workday", 1),
                      "unknown": ("Other or not recognised", 1)}  # fmt: skip
    wd = api.get("/discovery/jobs", params={"platform": "workday"}).json()
    assert [(x["source_job_id"], x["platform_label"]) for x in wd] == [("fx-workday", "Workday")]
    other = api.get("/discovery/jobs", params={"platform": "unknown"}).json()
    assert [x["source_job_id"] for x in other] == ["fx-other"]
    assert api.get("/discovery/jobs", params={"platform": "myspace"}).status_code == 422
    assert len(api.get("/discovery/jobs").json()) == 5
    assert other_api.get("/discovery/platforms").json() == []  # per account
    assert other_api.get("/discovery/jobs", params={"platform": "workday"}).json() == []


def test_the_import_route_takes_known_platforms_only(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_providers", ["freehire_mock"])
    r = api.post("/discovery/import", json={"provider": "freehire_mock", "platforms": ["myspace"]})
    assert r.status_code == 422
    # The bundled mock's postings are on local fixture addresses: no known platform.
    r = api.post("/discovery/import", json={"provider": "freehire_mock",
                                            "platforms": ["greenhouse"]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert (r.json()["created"], r.json()["excluded_by_filters"]) == (0, 5)
    r = api.post("/discovery/import", json={"provider": "freehire_mock", "platforms": ["unknown"]})
    assert r.json()["created"] == 5
