"""C14 (D66): what changed between two versions of a package, read-only, in the review page's
own words. The receiver's form and a fictional manual form; synthetic data only."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.preparation.models import ApplicationPackage
from tests.execution_harness import PDF, Receiver, prepared_application
from tests.test_input_binding import YEARS, answer, recapture, start
from tests.test_preparation import setup_candidate


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def diff(api, app_id, **q):
    r = api.get(f"/applications/{app_id}/package/diff", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def version(api, app_id) -> int:
    return api.get(f"/applications/{app_id}/package").json()["package"]["version"]


def counts(app_id) -> tuple[int, int]:
    with SessionLocal() as db:
        pkgs = db.scalar(select(func.count()).select_from(ApplicationPackage).where(
            ApplicationPackage.application_id == uuid.UUID(app_id)))  # fmt: skip
        return pkgs, db.scalar(select(func.count()).select_from(AuditEvent))


def test_a_changed_answer_is_shown_by_its_label_and_shown_values(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    before = version(api, app_id)
    api.put(f"/applications/{app_id}/answers", json={"key": "hear_about",
                                                      "value": {"label": "Job board"}})  # fmt: skip
    d = diff(api, app_id)  # by default: the latest version and the one before it
    assert (d["from"]["version"], d["to"]["version"]) == (before, before + 1)
    (row,) = d["answers"]
    assert row["label"] == "How did you hear about this job?" and row["changed"] == ["value"]
    assert row["before"]["display"] == "Referral" and row["after"]["display"] == "Job board"
    assert d["documents"] == d["consents"] == d["destination"] == []
    assert "fact_refs" not in str(d)


def test_what_changed_since_the_approved_version(api, receiver):
    app_id = prepared_application(api, receiver)
    approved = version(api, app_id)
    api.put(f"/applications/{app_id}/answers", json={"key": "hear_about",
                                                      "value": {"label": "Other"}})  # fmt: skip
    api.put(f"/applications/{app_id}/consents", json={"key": "privacy_ack", "choice": "decline"})
    v = api.get(f"/applications/{app_id}/package").json()
    assert v["approval"]["status"] == "invalidated"
    d = diff(api, app_id, from_version=approved)
    assert d["from"]["was_approved"] is True and d["to"]["was_approved"] is False
    assert {r["label"] for r in d["answers"]} >= {"How did you hear about this job?"}
    (c,) = d["consents"]
    assert (c["before"], c["after"]) == ("agree", "decline") and "privacy" in c["label"]


def test_a_new_document_version_is_shown(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    resume = api.get("/documents").json()[0]
    r = api.post("/documents", data={"lineage_id": resume["lineage_id"]},
                 files={"file": ("resume-v2.pdf", PDF + b"% v2\n", "application/pdf")})  # fmt: skip
    assert r.status_code == 201, r.text
    api.put(f"/applications/{app_id}/documents", json={"resume_document_id": r.json()["id"]})
    d = diff(api, app_id)
    (doc,) = d["documents"]
    assert doc["field"] == "resume" and doc["before"] != doc["after"]


def test_a_reworded_question_is_shown_as_a_changed_question(api):
    setup_candidate(api)
    job_id, app_id = start(api, YEARS)
    answer(api, app_id, "years", {"text": "5"})
    recapture(api, job_id, {**YEARS, "label": "How many years of payroll experience do you have?"})
    version(
        api, app_id
    )  # the review page loads the current version first; the diff never builds one
    (row,) = diff(api, app_id)["answers"]
    assert "question" in row["changed"] and "value" in row["changed"]
    assert row["label"] == "How many years of payroll experience do you have?"
    assert row["before"]["display"] == "5" and row["after"]["display"] is None


def test_the_diff_is_read_only(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    api.put(f"/applications/{app_id}/answers", json={"key": "hear_about",
                                                      "value": {"label": "Other"}})  # fmt: skip
    before = counts(app_id)
    diff(api, app_id)
    diff(api, app_id, from_version=1)
    assert counts(app_id) == before


def test_unknown_versions_and_other_users_are_404(api, other_api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    assert (
        api.get(f"/applications/{app_id}/package/diff", params={"from_version": 99}).status_code
        == 404
    )
    assert other_api.get(f"/applications/{app_id}/package/diff").status_code == 404


def test_the_diff_never_builds_a_version(api):
    """A recaptured form leaves a new version to be built when the page is next loaded; looking
    at the diff in between builds nothing."""
    setup_candidate(api)
    job_id, app_id = start(api, YEARS)
    answer(api, app_id, "years", {"text": "5"})
    recapture(api, job_id, {**YEARS, "label": "How many years of audit experience do you have?"})
    before = counts(app_id)
    diff(api, app_id)
    assert counts(app_id) == before
