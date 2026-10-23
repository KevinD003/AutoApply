"""Upload evidence (E5 step 2). Every upload is recorded with the digest of the approved
document and how the destination acknowledged it, as a fixed value: never the page's own
attachment id or wording. When an upload fails, the evidence of every upload the attempt made,
the failed one included, is kept before the attempt stops: that data may already have reached
the employer. Local fixtures and synthetic data only; the receiver's ledger is the oracle."""

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import Evidence
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_api_provider import TOKEN, grant
from tests.test_greenhouse_adapter import gh_application
from tests.test_greenhouse_dom import v2_application

COVER = b"%PDF-1.4\n% synthetic cover letter for upload-evidence tests\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def disclosures(aid: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(Evidence)
            .where(Evidence.attempt_id == uuid.UUID(aid), Evidence.kind == "disclosure")
            .order_by(Evidence.created_at)
        ).all()
        return [r.data for r in rows]


def stored_uploads(receiver) -> list[dict]:
    """What the synthetic employer kept, from its own ledger."""
    led = receiver.ledger()
    return [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "upload"]


def approve(api, app_id) -> dict:
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 200, r.text
    return p["content"]


def with_cover_letter(api, app_id) -> dict:
    doc = api.post("/documents", files={"file": ("cover.pdf", COVER, "application/pdf")},
                   data={"kind": "cover_letter"}).json()  # fmt: skip
    r = api.put(f"/applications/{app_id}/documents", json={"cover_letter_document_id": doc["id"]})
    assert r.status_code == 200, r.text
    return approve(api, app_id)


@pytest.mark.parametrize(
    "make,page_id",
    [
        (lambda api, receiver: prepared_application(api, receiver), "upload_id"),
        (lambda api, receiver: gh_application(api), "attachment_id"),
        (lambda api, receiver: v2_application(api), "attachment_id"),
    ],
    ids=["fixture_form", "greenhouse_style", "greenhouse_style_by_id"],
)
def test_an_upload_is_kept_as_its_digest_and_acknowledgement_never_the_pages_id(
    api, receiver, make, page_id
):
    app_id = make(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    digest = api.get(f"/applications/{app_id}/package").json()["package"]["content"]["documents"][
        0
    ]["sha256"]
    assert disclosures(aid) == [{"field": "resume", "ack": "attachment_shown", "sha256": digest}]
    (stored,) = stored_uploads(receiver)
    assert stored["sha256"] == digest
    # The page's own id for the attachment (the employer's reference) is never kept.
    assert stored[page_id] not in json.dumps(disclosures(aid))


@pytest.mark.parametrize("make", [gh_application, v2_application],
                         ids=["greenhouse_style", "greenhouse_style_by_id"])  # fmt: skip
def test_a_failed_upload_keeps_the_evidence_of_every_upload_before_it(api, receiver, make):
    app_id = make(api, approve=False)
    content = with_cover_letter(api, app_id)
    aid = queue(api, app_id)
    receiver.config(upload_fail_field="cover_letter")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "an attachment was not accepted" in attempt(aid).outcome_detail
    digests = {d["field"]: d["sha256"] for d in content["documents"]}
    assert disclosures(aid) == [
        {"field": "resume", "ack": "attachment_shown", "sha256": digests["resume"]},
        {"field": "cover_letter", "ack": "error_shown", "sha256": digests["cover_letter"]},
    ]
    assert [u["sha256"] for u in stored_uploads(receiver)] == [digests["resume"]]
    assert receiver.ledger()["accepted"] == 0


def test_a_refused_upload_is_kept_as_refused(api, receiver):
    aid = queue(api, prepared_application(api, receiver))
    receiver.config(mode="upload_fail")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert [(d["field"], d["ack"]) for d in disclosures(aid)] == [("resume", "error_shown")]
    assert stored_uploads(receiver) == [] and receiver.ledger()["accepted"] == 0


def test_an_upload_the_page_never_acknowledges_is_kept_as_unacknowledged(
    api, receiver, monkeypatch
):
    aid = queue(api, prepared_application(api, receiver))
    monkeypatch.setattr(get_settings(), "navigation_timeout_seconds", 3)
    receiver.config(upload_delay_s=8)  # the receiver keeps it; the page hears back too late
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "not acknowledged" in attempt(aid).outcome_detail
    assert [(d["field"], d["ack"]) for d in disclosures(aid)] == [("resume", "none")]
    assert len(stored_uploads(receiver)) == 1 and receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize(
    "mode,outcome,ack",
    [
        ("normal", "confirmed", "digest_matched"),
        ("upload_fail", "abandoned", "not_kept"),
    ],  # fmt: skip
)
def test_the_api_route_keeps_the_same_evidence(api, receiver, monkeypatch, mode, outcome, ack):
    monkeypatch.setattr(get_settings(), "fake_api_token", TOKEN)
    app_id = v2_application(api, approve=False)
    grant(api)
    content = approve(api, app_id)
    aid = queue(api, app_id)
    assert attempt(aid).adapter == "fake_api"
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == outcome
    draft, *uploads = disclosures(aid)
    assert draft == {"route": "api", "kind": "application_draft"}
    assert uploads == [{"field": "resume", "sha256": content["documents"][0]["sha256"],
                        "route": "api", "ack": ack}]  # fmt: skip
    kept = 1 if outcome == "confirmed" else 0  # the employer's own ledger: kept and accepted
    assert len(stored_uploads(receiver)) == kept and receiver.ledger()["accepted"] == kept
