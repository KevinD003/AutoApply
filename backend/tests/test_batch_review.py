"""D105: batch review approves only individually identified, immutable packages, each exactly as
its own page would, and never queues, sends or approves anything else. Synthetic data only; the
receiver's ledger shows nothing reached it."""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.execution.models import ExecutionAttempt, OutboxMessage
from app.modules.preparation.models import PackageApproval
from app.modules.preparation.review import MAX_ITEMS
from tests.execution_harness import Receiver, prepared_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def two(api, receiver) -> tuple[str, str]:
    a = prepared_application(api, receiver, approve=False)
    b = prepared_application(api, receiver, url_suffix="?posting=2", approve=False)
    return a, b


def listed(api) -> dict[str, dict]:
    r = api.get("/review/packages")
    assert r.status_code == 200, r.text
    return {i["application_id"]: i for i in r.json()["items"]}


def item(row: dict, scope: str) -> dict:
    return {"application_id": row["application_id"], "version": row["version"],
            "content_hash": row["content_hash"], "scope": scope}  # fmt: skip


def counts() -> tuple[int, int, int]:
    with SessionLocal() as db:
        return (db.query(PackageApproval).count(), db.query(ExecutionAttempt).count(),
                db.query(OutboxMessage).count())  # fmt: skip


def test_each_listed_package_is_approved_on_its_own_and_nothing_is_sent(api, receiver):
    a, b = two(api, receiver)
    rows = listed(api)
    assert {a, b} <= set(rows)
    assert rows[a]["approval"] is None and rows[a]["blocked"] == []
    assert rows[a]["content_hash"] != rows[b]["content_hash"]  # two packages, two identities
    r = api.post("/review/approve", json={"items": [item(rows[a], "submit"),
                                                    item(rows[b], "disclose_only")]})  # fmt: skip
    assert r.status_code == 200, r.text
    res = {x["application_id"]: x for x in r.json()["results"]}
    assert res[a]["status"] == res[b]["status"] == "approved"
    assert (res[a]["scope"], res[b]["scope"]) == ("submit", "disclose_only")
    with SessionLocal() as db:
        appr = {str(x.application_id): x for x in db.scalars(select(PackageApproval))}
        assert set(appr) == {a, b}
        ttl = get_settings().approval_ttl_hours * 3600
        for app_id in (a, b):
            x = appr[app_id]
            assert x.content_hash == rows[app_id]["content_hash"]  # bound to what was shown
            assert x.invalidated_at is None
            assert abs((x.expires_at - x.approved_at).total_seconds() - ttl) < 5  # it expires
        assert db.query(ExecutionAttempt).count() == 0  # approval only: nothing queued
        assert db.query(OutboxMessage).count() == 0
        batches = {e.meta["batch"] for e in db.scalars(select(AuditEvent).where(
            AuditEvent.action == "package.approve_reviewed"))}  # fmt: skip
        assert len(batches) == 1  # recorded as one review, item by item
    for app_id in (a, b):
        assert api.get(f"/applications/{app_id}").json()["state"] != "queued"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # Approved now: the list says so, and approving again changes nothing.
    again = listed(api)
    assert again[a]["approval"]["scope"] == "submit"
    r = api.post("/review/approve", json={"items": [item(again[a], "submit")]})
    assert r.json()["results"][0]["status"] == "approved"
    assert counts()[0] == 2
    # Another scope is never swapped in silently.
    r = api.post("/review/approve", json={"items": [item(again[a], "disclose_only")]})
    assert r.json()["results"][0]["status"] == "refused"


def test_a_package_that_changed_after_it_was_shown_is_refused_and_nothing_replaces_it(
    api, receiver
):
    a, b = two(api, receiver)
    rows = listed(api)
    # The candidate's answer changes after the list was read: a's package is rebuilt.
    r = api.put(f"/applications/{a}/answers", json={"key": "hear_about",
                                                    "value": {"label": "Job board"}})  # fmt: skip
    assert r.status_code == 200, r.text
    r = api.post("/review/approve", json={"items": [item(rows[a], "submit"),
                                                    item(rows[b], "submit")]})  # fmt: skip
    res = {x["application_id"]: x for x in r.json()["results"]}
    assert res[a]["status"] == "refused" and res[a]["reason_code"] == "package_changed"
    assert res[b]["status"] == "approved"  # one refusal leaves the others as they are
    with SessionLocal() as db:
        assert [str(x.application_id) for x in db.scalars(select(PackageApproval))] == [b]
    # A wrong hash for the current version is the same refusal.
    fresh = listed(api)[a]
    wrong = {**item(fresh, "submit"), "content_hash": "0" * 64}
    assert (
        api.post("/review/approve", json={"items": [wrong]}).json()["results"][0]["reason_code"]
        == "package_changed"
    )


def test_another_accounts_application_is_not_found_item_by_item(api, other_api, receiver):
    mine = prepared_application(api, receiver, approve=False)
    theirs = prepared_application(other_api, receiver, approve=False)
    assert theirs not in listed(api) and mine not in listed(other_api)
    t = listed(other_api)[theirs]
    m = listed(api)[mine]
    r = api.post("/review/approve", json={"items": [item(t, "submit"), item(m, "submit")]})
    res = {x["application_id"]: x for x in r.json()["results"]}
    assert res[theirs] == {"application_id": theirs, "version": t["version"],
                           "status": "not_found"}  # fmt: skip
    assert res[mine]["status"] == "approved"
    with SessionLocal() as db:
        assert [str(x.application_id) for x in db.scalars(select(PackageApproval))] == [mine]
    unknown = {**item(m, "submit"), "application_id": str(uuid.uuid4())}
    assert (
        api.post("/review/approve", json={"items": [unknown]}).json()["results"][0]["status"]
        == "not_found"
    )


def test_a_batch_names_each_item_fully_and_once(api, receiver):
    a = prepared_application(api, receiver, approve=False)
    row = listed(api)[a]
    no_scope = {k: v for k, v in item(row, "submit").items() if k != "scope"}
    for body in (
        {"items": []},  # nothing named: nothing approved, and not "everything"
        {"items": [no_scope]},  # never "submit" by omission
        {"items": [item(row, "submit"), item(row, "disclose_only")]},  # once per application
        {"items": [{**item(row, "submit"), "content_hash": "abc"}]},
        {"items": [{**item(row, "submit"), "version": 0}]},
        {
            "items": [item(row, "submit")] * 1
            + [
                {**item(row, "submit"), "application_id": str(uuid.uuid4())}
                for _ in range(MAX_ITEMS)
            ]
        },  # over the limit
        {"all": True},
    ):
        assert api.post("/review/approve", json=body).status_code == 422, body
    assert counts() == (0, 0, 0)


def test_an_approval_to_submit_still_needs_the_employers_path_rehearsed(api, receiver, monkeypatch):
    """E6 holds in a batch as on the package's own page: submitting is refused until a rehearsal
    on that path succeeded; a rehearsal approval is given."""
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths",
                        ["fixture_ats:e6-*"])  # fmt: skip
    a = prepared_application(api, receiver, slug="e6-review", approve=False)
    b = prepared_application(api, receiver, slug="e6-review", url_suffix="?posting=2",
                             approve=False)  # fmt: skip
    rows = listed(api)
    assert rows[a]["rehearsal_prerequisite"]["status"] != "met"
    r = api.post("/review/approve", json={"items": [item(rows[a], "submit"),
                                                    item(rows[b], "disclose_only")]})  # fmt: skip
    res = {x["application_id"]: x for x in r.json()["results"]}
    assert res[a]["status"] == "refused" and res[a]["reason_code"]
    assert res[b]["status"] == "approved" and res[b]["scope"] == "disclose_only"


def test_unanswered_questions_show_why_and_cannot_be_approved(api, receiver):
    from tests.execution_harness import BASE, synthetic_candidate

    receiver.config(mode="bank_question")  # a question only you can answer, left open
    synthetic_candidate(api)
    new = {"url": f"{BASE}/apply/clinic", "title": "Clinic Assistant",
           "employer": "Example Health Clinic (fictional)"}  # fmt: skip
    job = api.post("/jobs", json=new).json()
    job_id = job["job"]["id"]
    assert api.post(
        f"/jobs/{job_id}/form", json={"html": receiver.form_html("clinic")}
    ).status_code in (200, 201)
    a = api.post("/applications", json={"job_id": job_id}).json()["id"]
    row = listed(api)[a]
    assert row["blocked"] and "need your answer" in row["blocked"][0]
    r = api.post("/review/approve", json={"items": [item(row, "submit")]})
    assert r.json()["results"][0]["status"] == "refused"
    assert counts()[0] == 0
