"""D138: saved answers on Greenhouse- and Workday-shaped forms. A saved answer reaches the next
application that asks the same question; a question that only looks the same never reuses it; an
answer that depends on when you apply is never saved or reused; editing a saved answer asks again
for approval of every application that used it. Local fixtures only (the jobs and the Workday mode
are FIXTURE ASSUMPTIONS); what reached the employer is read from the receiver's own ledger."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.preparation.models import PackageApproval
from tests.execution_harness import BASE, Receiver, queue, synthetic_candidate
from tests.test_workday_adapter import workday_job

BOARD = "northwind"
SAVE, REUSE, LOOKALIKE = "5020004", "5020005", "5020006"
EDU = {SAVE: "question_8121", REUSE: "question_8131", LOOKALIKE: "question_8141"}
TITLES = {SAVE: "Warehouse Associate", REUSE: "Inventory Clerk", LOOKALIKE: "Dispatch Coordinator"}
BACHELOR, MASTER = "Bachelor's degree", "Master's degree or higher"
OPTION_VALUE = {BACHELOR: "23", MASTER: "24"}  # the fixture's own option values


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def put_answer(api, app_id: str, key: str, value: dict, save: bool = False):
    body = {"key": key, "value": value} | ({"save_to_bank": True} if save else {})
    return api.put(f"/applications/{app_id}/answers", json=body)


def package(api, app_id: str) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def row(api, app_id: str, key: str) -> dict:
    return next(a for a in package(api, app_id)["content"]["answers"] if a["key"] == key)


def approve(api, app_id: str):
    p = package(api, app_id)
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def gh_application(api, job: str) -> str:
    """A Greenhouse-shaped (id-only) application: the form read, the preferred name answered."""
    r = api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{job}",
            "title": TITLES[job],
            "employer": "Northwind Example (fictional)",
        },
    )
    job_id = r.json()["job"]["id"]
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    assert put_answer(api, app_id, "preferred_name", {"text": "Sammy"}).status_code == 200
    return app_id


def saved_entries(api) -> list[dict]:
    return api.get("/answer-bank").json()


# ------------------------------------------------------------------ Greenhouse-shaped


def test_on_greenhouse_pages_a_saved_answer_reaches_the_next_application(api, receiver):
    synthetic_candidate(api)
    first = gh_application(api, SAVE)
    r = put_answer(api, first, EDU[SAVE], {"label": BACHELOR}, save=True)
    assert r.status_code == 200, r.text
    assert approve(api, first).status_code == 200
    assert runner.run_attempt(queue(api, first), "w1") == "confirmed"

    second = gh_application(api, REUSE)  # another job, its own question id, the same question
    used = row(api, second, EDU[REUSE])
    assert used["source"] == "answer_bank" and used["status"] == "resolved"
    assert approve(api, second).status_code == 200
    assert runner.run_attempt(queue(api, second), "w1") == "confirmed"
    acc = receiver.ledger()["acceptances"]
    assert [a["fields"].get(EDU[SAVE]) or a["fields"].get(EDU[REUSE]) for a in acc] == [
        OPTION_VALUE[BACHELOR]
    ] * 2


def test_a_question_that_only_looks_the_same_never_reuses_the_saved_answer(api, receiver):
    synthetic_candidate(api)
    first = gh_application(api, SAVE)
    assert put_answer(api, first, EDU[SAVE], {"label": BACHELOR}, save=True).status_code == 200
    assert approve(api, first).status_code == 200
    assert any(
        e["question_text"] == "Highest level of education completed" for e in saved_entries(api)
    )

    third = gh_application(api, LOOKALIKE)  # "... completed in Canada"
    q = row(api, third, EDU[LOOKALIKE])
    assert q["source"] != "answer_bank" and q["status"] == "needs_user" and q["value"] is None
    assert EDU[LOOKALIKE] in package(api, third)["content"]["unresolved"]
    # Nor is it offered as a suggestion: a country named on one side only vetoes it (D133).
    offered = api.get(f"/applications/{third}/suggestions").json()["suggestions"]
    assert not [x for x in offered if x["key"] == EDU[LOOKALIKE]], offered
    assert approve(api, third).status_code == 409  # nothing approved, so nothing can be sent
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []


def test_editing_a_saved_answer_asks_again_before_anything_is_sent(api, receiver):
    synthetic_candidate(api)
    first = gh_application(api, SAVE)
    assert put_answer(api, first, EDU[SAVE], {"label": BACHELOR}, save=True).status_code == 200
    assert approve(api, first).status_code == 200
    second = gh_application(api, REUSE)
    assert approve(api, second).status_code == 200

    (entry,) = [e for e in saved_entries(api) if e["question_text"].startswith("Highest level")]
    new = next(o for o in entry["options_snapshot"] if o == MASTER.lower())
    r = api.put(f"/answer-bank/{entry['id']}", json={"value": {"labels": [new]}})
    assert r.status_code == 200, r.text
    assert r.json()["applications_to_approve_again"] >= 1
    with SessionLocal() as db:
        live = db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(second),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()
    assert live == []  # the approval of the old answer no longer sends anything
    q = api.post(f"/applications/{second}/transition", json={"to": "queued"})
    assert q.status_code in (400, 409) and "approval_needed" in q.text
    assert receiver.ledger()["accepted"] == 0

    assert row(api, second, EDU[REUSE])["display"].lower() == new
    assert approve(api, second).status_code == 200  # approved again, with the new answer
    assert runner.run_attempt(queue(api, second), "w1") == "confirmed"
    (acc,) = receiver.ledger()["acceptances"]
    assert acc["fields"][EDU[REUSE]] == OPTION_VALUE[MASTER]


# ------------------------------------------------------------------ Workday-shaped


def wd_application(api, req: str, title: str, *, education_saved: bool) -> str:
    job_id = workday_job(api, f"{BASE}/workday/examplehealth/{req}", title)
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "legalName--firstName": {"text": "Sam"},
        "q.licence_type": {"label": "RN"},
    }.items():
        assert put_answer(api, app_id, key, value).status_code == 200, key
    # A shift depends on when you apply: it is answered for this application, never saved.
    r = put_answer(api, app_id, "q.shift", {"label": "Nights"}, save=True)
    if r.status_code != 200:  # the save is refused outright: answer it for this application only
        assert put_answer(api, app_id, "q.shift", {"label": "Nights"}).status_code == 200
    if education_saved:
        r = put_answer(api, app_id, "q.education", {"label": BACHELOR}, save=True)
        assert r.status_code == 200, r.text
    r = api.put(f"/applications/{app_id}/consents", json={"key": "terms_ack", "choice": "agree"})
    assert r.status_code == 200, r.text
    return app_id


def test_on_workday_pages_a_saved_answer_is_reused_and_a_shift_never_is(api, receiver):
    receiver.config(mode="wd_bank_question")
    synthetic_candidate(api)
    first = wd_application(api, "R-100001", "Registered Nurse, Night Shift", education_saved=True)
    assert approve(api, first).status_code == 200
    assert runner.run_attempt(queue(api, first), "w1") == "confirmed"
    assert not any("shift" in e["question_text"].lower() for e in saved_entries(api))

    job_id = workday_job(api, f"{BASE}/workday/examplehealth/R-100002", "Charge Nurse")
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    second = api.post("/applications", json={"job_id": job_id}).json()["id"]
    used = row(api, second, "q.education")
    assert used["source"] == "answer_bank" and used["status"] == "resolved"
    shift = row(api, second, "q.shift")
    assert shift["source"] != "answer_bank" and shift["status"] == "needs_user"
    assert "q.shift" in package(api, second)["content"]["unresolved"]

    for key, value in {
        "legalName--firstName": {"text": "Sam"},
        "q.licence_type": {"label": "RN"},
        "q.shift": {"label": "Days"},
    }.items():
        assert put_answer(api, second, key, value).status_code == 200, key
    assert (
        api.put(
            f"/applications/{second}/consents", json={"key": "terms_ack", "choice": "agree"}
        ).status_code
        == 200
    )
    assert approve(api, second).status_code == 200
    assert runner.run_attempt(queue(api, second), "w1") == "confirmed"
    first_sent, second_sent = (a["fields"] for a in receiver.ledger()["acceptances"])
    assert first_sent["q.education"] == second_sent["q.education"] == BACHELOR
    assert (first_sent["q.shift"], second_sent["q.shift"]) == ("Nights", "Days")
