"""Greenhouse-hosted adapter against the labelled local approximation
(fixtures/ats_receiver/greenhouse_like.py). The receiver's ledger is the oracle. Passing these
tests shows compatibility with that fixture, not with any real employer's form."""

import json
import sys
import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import FieldType
from tests.execution_harness import (
    BASE,
    ROOT,
    Receiver,
    attempt,
    queue,
    synthetic_candidate,
)
from tests.test_execution_security import open_checkpoint, start_worker, wait_for

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_like  # noqa: E402

BOARD, JOB, LOCATION_JOB = "examplehealth", "4012001", "4012002"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def gh_job(api, job_id=JOB) -> str:
    return api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh/{BOARD}/jobs/{job_id}",
            "title": "Patient Services Coordinator",
            "employer": "Example Health Network (fictional)",
        },
    ).json()["job"]["id"]


def gh_application(api, *, employed="No", site=None, approve=True) -> str:
    """Synthetic candidate, captured form, user answers and consents; approved."""
    synthetic_candidate(api)
    job_id = gh_job(api)
    r = api.post(f"/jobs/{job_id}/form/greenhouse")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {
        "question_7004": {"label": "Referral"},
        "question_7005": {"label": employed},
        "question_7007": {"text": "I enjoy helping patients find their way through care."},
        "question_7008[]": {"labels": ["English", "Spanish"]},
    }
    if site:
        answers["question_7006"] = {"text": site}
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers/{key}", json={"value": value})
        assert r.status_code == 200, (key, r.text)
    api.put(f"/applications/{app_id}/consents/question_7009", json={"choice": "withhold"})
    v = api.put(
        f"/applications/{app_id}/consents/{gh.CONSENT_KEY}", json={"choice": "agree"}
    ).json()
    p = v["package"]
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    if approve:
        r = api.post(
            f"/applications/{app_id}/package/approve",
            json={"version": p["version"], "content_hash": p["content_hash"]},
        )
        assert r.status_code == 200, r.text
    return app_id


def kinds(led):
    out = {}
    for d in led["disclosures"]:
        out[d["kind"]] = out.get(d["kind"], 0) + 1
    return out


# ------------------------------------------------------------------ identity and schema


def test_posting_identity_from_real_and_fixture_urls():
    p = gh.parse_posting("https://job-boards.greenhouse.io/acme/jobs/4567890", fixture_origin=False)
    assert (p.board, p.job_id, p.fixture) == ("acme", "4567890", False)
    p = gh.parse_posting(
        "https://boards.greenhouse.io/embed/job_app?for=acme&token=123", fixture_origin=False
    )
    assert (p.board, p.job_id) == ("acme", "123")
    assert gh.parse_posting("https://example.com/acme/jobs/1", fixture_origin=False) is None
    # A fixture-shaped path on a real host is not a fixture.
    assert gh.parse_posting("https://evil.example/gh/a/jobs/1", fixture_origin=False) is None
    p = gh.parse_posting(f"{BASE}/gh/{BOARD}/jobs/{JOB}", fixture_origin=True)
    assert p == gh.Posting(BOARD, JOB, True)


def test_schema_keeps_exact_wording_help_options_and_required():
    data = greenhouse_like._api_json(BOARD, JOB, BASE)
    s = gh.schema_from_api(data)
    f = {x.key: x for x in s.fields}
    q = f["question_7002"]
    assert q.label == "Are you legally authorized to work in the United States?"
    assert q.type == FieldType.select and q.required
    assert [(o.value, o.label) for o in q.options] == [("1", "Yes"), ("0", "No")]
    assert f["question_7006"].help_text == "For example: Riverside Clinic."
    assert f["email"].type == FieldType.email and f["phone"].type == FieldType.tel
    assert f["resume"].type == FieldType.file and f["resume"].required
    assert "resume_text" not in f  # the paste box is an alternative to the attachment
    assert f["question_7008[]"].type == FieldType.checkbox_group
    assert f[gh.CONSENT_KEY].type == FieldType.checkbox and f[gh.CONSENT_KEY].required


def test_hidden_and_unknown_controls_become_unsupported():
    data = greenhouse_like._api_json(BOARD, LOCATION_JOB, BASE)
    data["questions"].append(
        {
            "label": "Pick a time",
            "required": False,
            "fields": [{"name": "question_9", "type": "time_slot_picker", "values": []}],
        }
    )
    f = {x.key: x for x in gh.schema_from_api(data).fields}
    assert f["latitude"].type == FieldType.unsupported and f["latitude"].required
    assert f["latitude"].unsupported_reason.startswith("hidden")
    assert f["question_9"].type == FieldType.unsupported
    assert "time_slot_picker" in f["question_9"].unsupported_reason


def test_protocol_hidden_fields_are_not_questions_and_declared_hidden_ones_block():
    """Page-managed hidden inputs (session token, attachment ids) are protocol, not questions:
    never in the schema, never answered by us. A hidden input the job data declares as a
    question is unsupported: never guessed, and a checkpoint when required."""
    api_json = greenhouse_like._api_json(BOARD, LOCATION_JOB, BASE)
    page = greenhouse_like._form_page(BOARD, LOCATION_JOB, "t", {"mode": "normal"}).body.decode()
    assert 'name="form_token"' in page and 'name="resume_attachment_id"' in page
    f = {x.key: x for x in gh.build_schema(api_json, page).fields}
    for protocol in ("form_token", "resume_attachment_id", "cover_letter_attachment_id"):
        assert protocol not in f
    assert f["resume"].type == FieldType.file  # the question is the attachment itself
    lat = f["latitude"]
    assert lat.type == FieldType.unsupported and lat.required
    assert lat.unsupported_reason.startswith("hidden")


def test_job_data_and_page_must_agree():
    api_json = greenhouse_like._api_json(BOARD, JOB, BASE)
    page = greenhouse_like._form_page(BOARD, JOB, "t", {"mode": "normal"}).body.decode()
    s = gh.build_schema(api_json, page)
    cond = {f.key: f.condition for f in s.fields if f.condition}
    assert cond["question_7006"].key == "question_7005" and cond["question_7006"].any_of == ["1"]
    drift = greenhouse_like._form_page(BOARD, JOB, "t", {"mode": "gh_drift"}).body.decode()
    with pytest.raises(gh.SchemaMismatch, match="only on the page: question_7099"):
        gh.build_schema(api_json, drift)
    reworded = page.replace("How did you hear about this job?", "Who referred you?")
    with pytest.raises(gh.SchemaMismatch, match="different: question_7004"):
        gh.build_schema(api_json, reworded)


# ------------------------------------------------------------------ capture and preparation


def test_real_greenhouse_posts_are_not_read(api):
    job = api.post(
        "/jobs",
        json={"url": "https://job-boards.greenhouse.io/acme/jobs/4567890", "title": "Any role"},
    ).json()["job"]
    assert job["ats_provider"] == "greenhouse"
    r = api.post(f"/jobs/{job['id']}/form/greenhouse")
    assert r.status_code == 409 and "not enabled" in r.text


def test_capture_refused_when_page_disagrees_with_job_data(api, receiver):
    receiver.config(mode="gh_drift")
    r = api.post(f"/jobs/{gh_job(api)}/form/greenhouse")
    assert r.status_code == 409 and "question_7099" in r.text


def test_required_unsupported_control_is_a_checkpoint(api, receiver):
    synthetic_candidate(api)
    job_id = gh_job(api, LOCATION_JOB)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    v = api.get(f"/applications/{app_id}/package").json()["package"]
    c = v["content"]
    assert {"latitude", "longitude"} <= set(c["unresolved"])
    lat = next(a for a in c["answers"] if a["key"] == "latitude")
    assert lat["user_input_allowed"] is False and "cannot fill" in lat["explanation"]
    r = api.put(f"/applications/{app_id}/answers/latitude", json={"value": {"text": "39.8"}})
    assert r.status_code in (400, 409, 422)
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": v["version"], "content_hash": v["content_hash"]},
    )
    assert r.status_code in (400, 409)


def test_conditional_question_follows_its_trigger(api, receiver):
    app_id = gh_application(api, employed="No", approve=False)
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    q = next(a for a in c["answers"] if a["key"] == "question_7006")
    assert (
        q["status"] == "blank_optional" and q["value"] is None and "Not asked" in q["explanation"]
    )
    api.put(f"/applications/{app_id}/answers/question_7005", json={"value": {"label": "Yes"}})
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert "question_7006" in c["unresolved"]  # now asked, required, and not guessed


def test_unanswered_trigger_keeps_its_conditional_question_pending(api, receiver):
    """False, true and unresolved are distinct: an unanswered trigger never makes the question
    'not asked'."""
    synthetic_candidate(api)
    job_id = gh_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    by_key = {a["key"]: a for a in c["answers"]}
    assert by_key["question_7005"]["status"] == "needs_user"
    q = by_key["question_7006"]
    assert q["status"] == "needs_user" and "Not asked" not in q["explanation"]
    assert "depends on an unanswered question" in q["explanation"]
    assert {"question_7005", "question_7006"} <= set(c["unresolved"])


# ------------------------------------------------------------------ execution


def test_full_run_is_confirmed_and_sends_exactly_the_approved_values(api, receiver):
    app_id = gh_application(api)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "greenhouse_hosted"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["first_name"] == "Sam" and sent["email"] == "sam.synthetic@example.com"
    assert sent["question_7002"] == "1" and sent["question_7004"] == "12"
    assert sent["question_7005"] == "0" and "question_7006" not in sent
    assert sent["question_7008"] == ["21", "22"]
    assert sent[gh.CONSENT_KEY] == "1"
    assert not sent.get("question_7009")  # withheld sensitive answer stays blank
    assert not sent.get("cover_letter_attachment_id")
    # The attachment left the browser before submit, as its own disclosure, with our bytes.
    assert kinds(led) == {"upload": 1}
    up = json.loads(led["disclosures"][0]["detail"])
    approved = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert up["sha256"] == approved["documents"][0]["sha256"]
    assert sent["resume_attachment_id"] == up["attachment_id"]
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    rc = next(e for e in att["evidence"] if e["kind"] == "receipt")
    assert rc["strength"] == "employer_confirmation_page" and rc["data"]["receipt_id"] is None
    rb = next(e for e in att["evidence"] if e["kind"] == "readback")["data"]
    assert rb["mismatches"] == []
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_conditional_question_is_filled_when_it_applies(api, receiver):
    app_id = gh_application(api, employed="Yes", site="Riverside Clinic")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = receiver.ledger()["acceptances"][0]["fields"]
    assert sent["question_7005"] == "1" and sent["question_7006"] == "Riverside Clinic"


def test_security_code_wrong_then_right(api, receiver):
    app_id = gh_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh_security_code")
    w = start_worker(aid, "w-gh")
    cp = open_checkpoint(api, app_id, 1)
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    assert receiver.ledger()["accepted"] == 0  # not accepted until the code is entered
    r = api.post(
        f"/applications/{app_id}/checkpoints/{cp['id']}/code",
        json={"round": 1, "code": "WRONG000"},
    )
    assert r.status_code == 202
    cp2 = open_checkpoint(api, app_id, 2)
    real = wait_for(lambda: receiver.ledger()["challenges"])[-1]["code"]
    r = api.post(
        f"/applications/{app_id}/checkpoints/{cp2['id']}/code", json={"round": 2, "code": real}
    )
    assert r.status_code == 202
    out, err = w.communicate(timeout=60)
    assert out.strip() == "confirmed", err[-800:]
    assert receiver.ledger()["accepted"] == 1
    assert real not in out + err


def test_captcha_stops_before_anything_is_disclosed(api, receiver):
    app_id = gh_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="captcha")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "CAPTCHA" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_form_changed_after_approval_stops_before_disclosure(api, receiver):
    app_id = gh_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh_drift")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "question_7099" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@pytest.mark.parametrize(
    "mode,expected,accepted",
    [
        ("validation_fail", "rejected", 0),
        ("error_before_accept", "unknown", 0),
        ("error_after_accept", "unknown", 1),
        ("drop_after_accept", "unknown", 1),
        ("upload_fail", "abandoned", 0),
        ("gh_confirm_redirect", "confirmed", 1),
        # A confirmation page for a different posting is not evidence for this attempt.
        ("gh_confirm_other_job", "unknown", 1),
    ],
)
def test_outcome_classification(api, receiver, mode, expected, accepted):
    app_id = gh_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == expected
    assert receiver.ledger()["accepted"] == accepted
    # Never resent: a second delivery of the same attempt is ignored.
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == accepted


def test_capability_flags(api):
    caps = api.get("/execution/capabilities").json()
    g = caps["adapters"]["greenhouse_hosted"]
    for flag in ("inspect", "extract", "fill", "upload", "checkpoint", "submit", "confirm"):
        assert g[flag] is True
    assert g["real_destinations"] is False
    assert g["unverified"]["security_code"].startswith("synthetic")
