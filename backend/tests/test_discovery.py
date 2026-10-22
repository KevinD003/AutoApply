"""Discovery through the local mock provider (fixtures/discovery/freehire_mock.json): import,
normalization, deduplication, stale handling and linking to an application route. The mock's
record shape is NoEfforts' own; nothing here contacts Freehire or claims its real format."""

import json
import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.discovery import service
from app.modules.discovery.models import DiscoveredJob
from app.modules.discovery.provider import FreehireMockProvider
from app.modules.jobs.models import Job
from app.modules.profiles.models import WorkAuthorization
from tests.execution_harness import BASE, Receiver


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


def me(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def run_import(user_id, path=None):
    with SessionLocal() as db:
        res = service.import_from(db, user_id, FreehireMockProvider(path))
        db.commit()
        return res


def rows(user_id) -> dict[str, DiscoveredJob]:
    with SessionLocal() as db:
        found = db.scalars(select(DiscoveredJob).where(DiscoveredJob.user_id == user_id)).all()
        return {r.source_job_id: r for r in found}


def feed_copy(tmp_path, transform) -> object:
    data = json.loads(FreehireMockProvider.DEFAULT.read_text())
    data["jobs"] = transform(data["jobs"])
    path = tmp_path / "feed.json"
    path.write_text(json.dumps(data))
    return path


def test_import_normalizes_deduplicates_and_keeps_incomplete_records_unlinked(api):
    uid = me(api)
    res = run_import(uid)
    assert (res.created, res.incomplete, res.stale) == (5, 1, 0)
    # fh-1001 and fh-1005 are one posting (tracking parameter): one tracker job, two records.
    assert (res.linked_new_jobs, res.linked_existing_jobs) == (3, 1)
    r = rows(uid)
    assert r["fh-1001"].job_id == r["fh-1005"].job_id is not None
    assert r["fh-1004"].status == "incomplete" and r["fh-1004"].job_id is None
    assert r["fh-1004"].normalized["missing"] == ["no job or application URL"]
    # URLs are preserved exactly as the source gave them.
    assert r["fh-1005"].normalized["job_url"].endswith("5020001?utm_source=feed")
    # The ATS comes from known hostnames only: a fixture origin is not claimed to be Greenhouse.
    assert {x.normalized["ats_provider"] for x in r.values()} == {"unknown"}
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Job.id)).where(Job.user_id == uid)) == 3


def test_missing_data_stays_missing_and_source_facts_stay_out_of_the_profile(api):
    uid = me(api)
    run_import(uid)
    r = rows(uid)
    assert r["fh-1001"].source_facts["sponsorship_offered"] == {
        "value": "yes",
        "stated_by": "freehire_mock",
        "basis": "source field",
    }
    assert r["fh-1002"].source_facts["sponsorship_offered"]["value"] == "unknown"  # not stated
    assert r["fh-1003"].source_facts["sponsorship_offered"]["value"] == "no"
    assert r["fh-1003"].normalized["location"] is None  # never guessed
    assert r["fh-1004"].normalized["workplace"] == "unknown"
    for row in r.values():
        assert "salary" not in row.normalized and "eligible" not in json.dumps(row.normalized)
    with SessionLocal() as db:  # nothing reaches the candidate's facts
        assert db.scalar(select(func.count(WorkAuthorization.id))) == 0


def test_a_posting_the_user_already_tracks_is_linked_not_duplicated(api):
    uid = me(api)
    existing = api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/northwind/jobs/5020002",
            "title": "Field Technician",
            "employer": "Northwind Example (fictional)",
        },
    ).json()
    res = run_import(uid)
    assert res.linked_existing_jobs == 2  # fh-1002 (already tracked) and fh-1005
    assert str(rows(uid)["fh-1002"].job_id) == existing["job"]["id"]


def test_reimport_is_unchanged_and_stale_records_are_marked_not_deleted(api, tmp_path):
    uid = me(api)
    run_import(uid)
    again = run_import(uid)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 5)
    gone = feed_copy(tmp_path, lambda jobs: [j for j in jobs if j["id"] != "fh-1002"])
    res = run_import(uid, gone)
    assert res.stale == 1
    r = rows(uid)
    assert r["fh-1002"].stale and r["fh-1002"].stale_reason == "not in the latest source listing"
    with SessionLocal() as db:  # the tracker job is left for the user to decide
        assert db.get(Job, r["fh-1002"].job_id) is not None
    closed = feed_copy(tmp_path, lambda jobs: [{**j, "closed": True} if j["id"] == "fh-1003"
                                               else j for j in jobs])  # fmt: skip
    res = run_import(uid, closed)
    r = rows(uid)
    assert res.updated == 1 and r["fh-1003"].stale_reason == "closed at source"
    assert not r["fh-1002"].stale and r["fh-1002"].stale_reason is None  # listed again


def test_discovered_jobs_are_user_scoped(api, other_api):
    run_import(me(api))
    other = me(other_api)
    assert rows(other) == {}
    assert other_api.get("/jobs").json()["total"] == 0
    assert run_import(other).created == 5  # their own rows, not the first user's


def test_application_route_is_a_manual_handoff_until_a_form_is_captured(api, receiver):
    uid = me(api)
    run_import(uid)
    r = rows(uid)
    with SessionLocal() as db:
        incomplete = service.application_route(db, db.get(DiscoveredJob, r["fh-1004"].id))
        uncaptured = service.application_route(db, db.get(DiscoveredJob, r["fh-1001"].id))
        external = service.application_route(db, db.get(DiscoveredJob, r["fh-1003"].id))
    assert (incomplete.route, incomplete.message) == ("manual_handoff", "Import this job manually.")
    assert incomplete.reason == "source_record_incomplete"
    assert uncaptured.message == "Capture the application form first."
    assert external.route == "manual_handoff"
    job_id = str(r["fh-1001"].job_id)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    with SessionLocal() as db:
        d = service.application_route(db, db.get(DiscoveredJob, r["fh-1001"].id))
    assert (d.route, d.provider) == ("browser", "greenhouse_dom")  # fixture origin only
