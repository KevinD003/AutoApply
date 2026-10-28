"""S3 (D59): a job its source says is closed, a job you excluded or closed, and a role that looks
like one you already have an application for are shown before any disclosure, and approval waits
for your statement. Discovery runs against the local stand-in of Freehire's documented API
(fixtures/ats_receiver/freehire_fixture.py); nothing contacts Freehire or an employer. Synthetic
data only."""

import pathlib
import re
import threading
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.applications.models import Application
from app.modules.audit.models import AuditEvent
from app.modules.discovery.models import DiscoveredJob
from app.modules.jobs import signals
from app.modules.jobs.canonical import canonicalize_url, dedupe_key, url_key
from app.modules.jobs.models import Job, JobSource
from app.modules.jobs.service import upsert_job
from app.modules.preparation import package as pk
from app.modules.preparation.models import PackageApproval
from tests.test_freehire_discovery import (
    ANALYST,
    TECH,
    me,
    receiver,  # noqa: F401
    rows,
    run,
)
from tests.test_freehire_discovery import _settings as _fh_settings  # noqa: F401
from tests.test_preparation import setup_candidate

DOC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "job-signals.md"
REPOST = "fx-contoso-analyst-repost-78"


def prepare(api, job_id) -> str:
    """Attach the fictional basic form and answer it: the application is past draft and ready."""
    assert api.post(f"/jobs/{job_id}/form", json={"fixture": "basic"}).status_code == 201
    aid = api.post("/applications", json={"job_id": str(job_id)}).json()["id"]
    api.put(
        f"/applications/{aid}/answers", json={"key": "hear_about", "value": {"label": "Job board"}}
    )
    api.put(f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"})
    v = api.get(f"/applications/{aid}/package").json()
    assert v["package"]["content"]["unresolved"] == [] and v["state"] != "draft", v["state"]
    return aid


def approve(api, aid):
    p = api.get(f"/applications/{aid}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    return api.post(f"/applications/{aid}/package/approve", json=body)


def refused(r, code):
    assert r.status_code == 409 and f"(reason: {code})" in r.json()["detail"], r.text


def approvals(aid) -> int:
    with SessionLocal() as db:
        q = select(PackageApproval).where(PackageApproval.application_id == uuid.UUID(aid))
        return len(db.scalars(q).all())


def events(user_id, action) -> int:
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.user_id == user_id, AuditEvent.action == action)
        return len(db.scalars(q).all())


def manual_job(api, title="Data Analyst", employer="Contoso Example (fictional)", location=None,
               url=None):  # fmt: skip
    body = {"title": title, "employer": employer}
    body |= ({"location": location} if location else {}) | ({"url": url} if url else {})
    return api.post("/jobs", json=body).json()["job"]["id"]


# -- excluded and closed by you (R5.11) --------------------------------------------------------


def test_approval_waits_while_you_excluded_or_closed_the_job(api):
    setup_candidate(api)
    job = manual_job(api, "Clinic Assistant", "Example Health")
    aid = prepare(api, job)
    for status, code in (("excluded", "job_excluded"), ("closed", "job_closed_by_you")):
        assert api.patch(f"/jobs/{job}", json={"status": status}).status_code == 200
        refused(approve(api, aid), code)
        assert approvals(aid) == 0
        blocked = api.get(f"/applications/{aid}/package").json()["job_signals"]["approval_blocked"]
        assert blocked["code"] == code and blocked["message"] == signals.REASONS[code]
        assert api.get(f"/jobs/{job}").json()["signals"]["approval_blocked"]["code"] == code
    assert api.patch(f"/jobs/{job}", json={"status": "shortlisted"}).status_code == 200
    assert approve(api, aid).status_code == 200


# -- source says closed (R9.8) -----------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,reason", [("fh_closed_now", "closed at source"), ("fh_gone", "no longer at the source")]
)
def test_a_posting_its_source_closed_waits_for_your_statement(api, receiver, mode, reason):  # noqa: F811
    setup_candidate(api)
    run(api)
    row = rows(me(api))[TECH]
    before = api.get(f"/jobs/{row.job_id}").json()
    aid = prepare(api, row.job_id)
    receiver.config(fh_mode=mode)
    assert api.post(f"/discovery/jobs/{row.id}/refresh").json()["job"]["stale_reason"] == reason
    job = api.get(f"/jobs/{row.job_id}").json()
    assert job["signals"]["source_closed"]["reason"] == reason
    assert job["signals"]["source_closed"]["provider"] == "freehire"
    # The tracker job itself is never changed by discovery.
    assert {k: job[k] for k in ("title", "status", "url")} == {
        k: before[k] for k in ("title", "status", "url")
    }
    refused(approve(api, aid), "job_source_closed")
    assert approvals(aid) == 0
    # Your statement that it is still open answers it, and is audited.
    r = api.post(f"/jobs/{row.job_id}/still-open")
    assert r.status_code == 200 and r.json()["signals"]["source_closed"] is None
    assert events(me(api), "job.confirm_open") == 1
    # The source repeating the same report does not undo your statement.
    assert api.post(f"/discovery/jobs/{row.id}/refresh").status_code == 200
    assert api.get(f"/jobs/{row.job_id}").json()["signals"]["approval_blocked"] is None
    assert approve(api, aid).status_code == 200
    # Open again at the source, then closed again: a new report after your statement asks again.
    receiver.config(fh_mode="normal")
    assert api.post(f"/discovery/jobs/{row.id}/refresh").json()["job"]["stale"] is False
    receiver.config(fh_mode=mode)
    api.post(f"/discovery/jobs/{row.id}/refresh")
    assert (
        api.get(f"/jobs/{row.job_id}").json()["signals"]["approval_blocked"]["code"]
        == "job_source_closed"
    )


def test_a_posting_missing_from_a_listing_is_not_a_closed_posting(api):
    """Only the source's own statement (closed, or gone at its address) counts; a record that is
    stale because a complete listing left it out is shown as stale, not as closed."""
    setup_candidate(api)
    run(api)
    row = rows(me(api))[TECH]
    with SessionLocal() as db:
        r = db.get(DiscoveredJob, row.id)
        r.stale, r.stale_reason = True, "not in the latest source listing"
        db.commit()
    assert api.get(f"/jobs/{row.job_id}").json()["signals"]["source_closed"] is None


# -- possible duplicates (R5.9) ----------------------------------------------------------------


def test_a_repost_is_a_possible_duplicate_and_never_merged(api, receiver):  # noqa: F811
    setup_candidate(api)
    run(api)
    first = rows(me(api))[ANALYST]
    first_aid = prepare(api, first.job_id)
    receiver.config(fh_mode="fh_repost")
    run(api)
    again = rows(me(api))[REPOST]
    assert again.job_id is not None and again.job_id != first.job_id  # a new job, never merged
    assert again.link_basis == "new_job"
    dup = api.get(f"/jobs/{again.job_id}").json()["signals"]["possible_duplicates"]
    assert [(d["job_id"], d["application_id"], d["state"], d["outcome"]) for d in dup] == [
        (str(first.job_id), first_aid, "awaiting_approval", "none")
    ]
    listed = {x["source_job_id"]: x["job_signals"] for x in api.get("/discovery/jobs").json()}
    assert listed[REPOST] == {"application": None, "possible_duplicates": 1}
    assert listed[ANALYST] == {
        "application": {"state": "awaiting_approval", "outcome": "none"},
        "possible_duplicates": 0,
    }
    aid = prepare(api, again.job_id)
    refused(approve(api, aid), "job_possible_duplicate")
    # And the first one now sees the repost's application too.
    refused(approve(api, first_aid), "job_possible_duplicate")
    r = api.post(f"/jobs/{again.job_id}/different-role")
    assert r.status_code == 200 and r.json()["signals"]["possible_duplicates"] == []
    assert events(me(api), "job.confirm_distinct") == 1
    assert approve(api, aid).status_code == 200
    # A later application to the same role asks again.
    third = manual_job(api, "Data Analyst")
    prepare(api, third)
    dup = api.get(f"/jobs/{again.job_id}").json()["signals"]["possible_duplicates"]
    assert [d["job_id"] for d in dup] == [third]


@pytest.mark.parametrize(
    "other,same",
    [
        (
            {"employer": "Contoso Example (fictional), Inc."},
            True,
        ),  # the employer key, not the spelling
        ({"title": "data  analyst"}, True),
        ({"title": "Senior Data Analyst"}, False),
        ({"employer": "Fabrikam Example (fictional)"}, False),
        ({"location": "Riverton"}, True),  # one location missing: same role
        ({"location": "Riverton", "mine": "Lakeside"}, False),  # two different locations
        ({"location": "Riverton", "mine": "riverton"}, True),
    ],
)
def test_the_same_role_is_the_same_employer_title_and_location(api, other, same):
    setup_candidate(api)
    kw = {"title": "Data Analyst", "employer": "Contoso Example (fictional)"}
    mine_loc = other.pop("mine", None)
    # Two postings (two URLs): the same employer, title and location without a URL is one job.
    theirs = manual_job(api, **(kw | other), url="https://jobs.example.test/contoso/1")
    prepare(api, theirs)
    mine = manual_job(api, **kw, location=mine_loc, url="https://jobs.example.test/contoso/2")
    found = api.get(f"/jobs/{mine}").json()["signals"]["possible_duplicates"]
    assert bool(found) is same


def test_a_draft_application_is_not_a_prior_application(api):
    setup_candidate(api)
    theirs = manual_job(api)
    assert api.post(f"/jobs/{theirs}/form", json={"fixture": "basic"}).status_code == 201
    aid = api.post("/applications", json={"job_id": theirs}).json()["id"]
    with SessionLocal() as db:
        assert db.get(Application, uuid.UUID(aid)).state.value == "draft"
    mine = manual_job(api, location="Riverton")
    assert api.get(f"/jobs/{mine}").json()["signals"]["possible_duplicates"] == []


def test_concurrent_approvals_of_two_copies_are_both_refused(api):
    """R12.5: two copies of one role, both prepared; two approvals at once each see the other's
    application, so neither is approved."""
    setup_candidate(api)
    a, b = manual_job(api), manual_job(api, location="Riverton")
    aids = [prepare(api, a), prepare(api, b)]
    views = [api.get(f"/applications/{x}/package").json()["package"] for x in aids]
    barrier, out = threading.Barrier(2), {}

    def go(i):
        with SessionLocal() as db:
            app = db.get(Application, uuid.UUID(aids[i]))
            barrier.wait()
            try:
                pk.approve(db, app, views[i]["version"], views[i]["content_hash"])
                db.commit()
                out[i] = "approved"
            except pk.ApprovalError as e:
                db.rollback()
                out[i] = str(e)

    threads = [threading.Thread(target=go, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert all("(reason: job_possible_duplicate)" in out[i] for i in (0, 1)), out
    assert approvals(aids[0]) == approvals(aids[1]) == 0


# -- tenancy (R13) -----------------------------------------------------------------------------


def test_another_users_applications_are_never_a_signal_and_their_jobs_are_not_found(api, other_api):
    setup_candidate(api)
    setup_candidate(other_api)
    theirs = manual_job(other_api)
    prepare(other_api, theirs)
    mine = manual_job(api)
    assert api.get(f"/jobs/{mine}").json()["signals"]["possible_duplicates"] == []
    for action in ("still-open", "different-role"):
        assert api.post(f"/jobs/{theirs}/{action}").status_code == 404
    other_id = uuid.UUID(other_api.get("/auth/me").json()["user_id"])
    assert events(other_id, "job.confirm_open") == events(other_id, "job.confirm_distinct") == 0
    with SessionLocal() as db:
        job = db.get(Job, uuid.UUID(theirs))
        assert job.open_confirmed_at is None and job.distinct_confirmed_at is None


# -- Greenhouse embed URLs (R5.10) -------------------------------------------------------------


def test_a_greenhouse_embed_url_is_the_same_posting_as_its_board_url():
    hosted = canonicalize_url("https://boards.greenhouse.io/acme/jobs/4012345")
    embed = canonicalize_url("https://boards.greenhouse.io/embed/job_app?for=acme&token=4012345")
    key = lambda u, employer="Acme Inc.": dedupe_key(  # noqa: E731
        canonical_url=u, employer=employer, title="Analyst", location=None
    )
    assert key(hosted) == key(embed) == "ats:greenhouse:acme:4012345"
    # Without for= the board is not in the URL: the employer's name stands in, so it matches
    # the board URL only when the board's name is the employer's (documented in D59).
    bare = canonicalize_url("https://boards.greenhouse.io/embed/job_app?token=4012345")
    assert key(bare) == key(hosted)
    assert key(bare, "Acme Holdings") != key(hosted, "Acme Holdings")
    # Anything else on that path is not a Greenhouse identity.
    odd = canonicalize_url("https://boards.greenhouse.io/embed/job_app?for=acme&token=abc")
    assert key(odd).startswith("url:")


def test_a_job_stored_under_its_url_key_is_found_again(api):
    """A job stored before embed URLs were recognised keeps its URL key; importing the same URL
    again finds it instead of adding a second job."""
    url = "https://boards.greenhouse.io/embed/job_app?for=acme&token=4012345"
    uid = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        job, created = upsert_job(db, uid, source=JobSource.manual, url=url, title="Analyst")
        job.dedupe_key = url_key(canonicalize_url(url))  # as stored before S3
        db.commit()
        again, created = upsert_job(db, uid, source=JobSource.url, url=url)
        assert (again.id, created) == (job.id, False)
        db.commit()


# -- documentation -----------------------------------------------------------------------------


def test_the_reason_codes_are_documented_exactly():
    doc = DOC.read_text()
    listed = set(re.findall(r"^\| `(job_[a-z_]+)` \|", doc, re.M))
    assert listed == set(signals.REASONS)
    for code, message in signals.REASONS.items():
        assert message in doc, code
