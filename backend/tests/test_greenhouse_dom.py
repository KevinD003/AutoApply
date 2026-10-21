"""Greenhouse "v2" structure (id-only controls, ARIA comboboxes) against the second local
fixture (fixtures/ats_receiver/greenhouse_v2.py). Passing these shows compatibility with that
fixture only; widget behaviour there is a labelled fixture assumption."""

import json
import sys
import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import FieldType
from tests.execution_harness import BASE, ROOT, Receiver, attempt, queue, synthetic_candidate

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB, LOC_JOB = "northwind", "5020001", "5020002"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def page_html(job=JOB, mode="normal") -> str:
    return greenhouse_v2._form_page(BOARD, job, "t", {"mode": mode}).body.decode()


def api(job=JOB) -> dict:
    return greenhouse_v2._api_json(BOARD, job, BASE)


def v2_job(api_client, job=JOB) -> str:
    return api_client.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{job}",
            "title": "Support Specialist",
            "employer": "Northwind Example (fictional)",
        },
    ).json()["job"]["id"]


# ------------------------------------------------------------------ mapping


def test_every_api_field_maps_to_exactly_one_labelled_control():
    from app.modules.preparation import greenhouse as gh

    fields = gh.schema_from_api(api()).fields
    maps = {m.key: m for m in dom.map_fields(fields, dom.snapshot(page_html()))}
    assert {m.status for m in maps.values()} == {"mapped"}, {
        k: m.status for k, m in maps.items() if m.status != "mapped"
    }
    assert maps["question_8101"].control.role == "combobox"
    assert maps["question_8101"].control.controls_listbox is True
    assert maps["resume"].control.type == "file" and maps["resume"].control.group
    assert maps["question_8105"].hidden_at_load is True  # conditional, trigger not exposed
    unmatched = {c.id for c in dom.unmatched_controls(fields, dom.snapshot(page_html()))}
    assert unmatched == {"resume_text", "cover_letter_text"}  # the textarea alternatives


@pytest.mark.parametrize(
    "mode,key,status",
    [
        ("gh2_duplicate_id", "question_8101", "ambiguous"),
        ("gh2_label_mismatch", "question_8101", "label_mismatch"),
        ("gh2_missing_control", "question_8103", "absent"),
    ],
)
def test_ambiguous_or_mismatched_mappings_are_rejected(mode, key, status):
    from app.modules.preparation import greenhouse as gh

    maps = {
        m.key: m
        for m in dom.map_fields(
            gh.schema_from_api(api()).fields, dom.snapshot(page_html(mode=mode))
        )
    }
    assert maps[key].status == status
    with pytest.raises(gh.SchemaMismatch, match=f"{key}: {status}"):
        dom.build_schema(api(), page_html(mode=mode))


def test_text_question_rendered_as_search_picker_is_unsupported_not_typed():
    schema, maps = dom.build_schema(api(LOC_JOB), page_html(LOC_JOB))
    f = {x.key: x for x in schema.fields}
    assert (
        f["location"].type == FieldType.unsupported and "search" in f["location"].unsupported_reason
    )
    assert f["latitude"].type == FieldType.unsupported and f["latitude"].required
    by = {m.key: m.status for m in maps}
    assert by["location"] == "search_picker" and by["latitude"] == "protocol"


def test_notice_is_not_a_field_and_no_consent_is_invented():
    schema, _ = dom.build_schema(api(), page_html())
    keys = {f.key for f in schema.fields}
    assert "ai-disclaimer" not in keys
    assert not any(f.type == FieldType.checkbox for f in schema.fields)  # requires_consent false
    assert schema.action == f"/gh2/{BOARD}/jobs/{JOB}/submit"


# ------------------------------------------------------------------ capture and preparation


def test_capture_routes_v2_structure_to_the_dom_mapper(api, receiver):
    r = api.post(f"/jobs/{v2_job(api)}/form/greenhouse")
    assert r.status_code == 201, r.text
    form = r.json()
    assert form["source"] == "greenhouse_api_dom"
    assert form["extraction_version"] == dom.EXTRACTION_VERSION


def test_capture_refuses_an_ambiguous_page(api, receiver):
    receiver.config(mode="gh2_duplicate_id")
    r = api.post(f"/jobs/{v2_job(api)}/form/greenhouse")
    assert r.status_code == 409 and "question_8101: ambiguous" in r.text


def test_preferred_name_and_unknown_condition_are_not_guessed(api, receiver):
    synthetic_candidate(api)  # has a given name, no preferred name
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    a = {x["key"]: x for x in c["answers"]}
    assert a["preferred_name"]["status"] == "needs_user"  # not copied from the given name
    assert a["question_8105"]["value"] is None
    assert "cannot tell when" in a["question_8105"]["explanation"]


def test_location_job_is_a_checkpoint(api, receiver):
    synthetic_candidate(api)
    job_id = v2_job(api, LOC_JOB)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    c = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert {"location", "latitude", "longitude"} <= set(c["unresolved"])
    loc = next(x for x in c["answers"] if x["key"] == "location")
    assert loc["user_input_allowed"] is False


# ------------------------------------------------------------------ execution (receiver oracle)


def v2_application(api, *, worked_before="No", approve=True) -> str:
    """Synthetic candidate; the user answers what the resolver must not guess."""
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {
        "preferred_name": {"text": "Sammy"},
        "question_8101": {"label": "Yes"},
        "question_8104": {"label": worked_before},
    }
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers/{key}", json={"value": value})
        assert r.status_code == 200, (key, r.text)
    p = api.get(f"/applications/{app_id}/package").json()["package"]
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


def test_full_run_sends_exactly_the_approved_values(api, receiver):
    app_id = v2_application(api)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        assert db.get(ExecutionAttempt, uuid.UUID(aid)).adapter == "greenhouse_dom"
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["first_name"] == "Sam" and sent["preferred_name"] == "Sammy"
    assert sent["email"] == "sam.synthetic@example.com" and sent["phone"] == "+1 555 0100"
    # Comboboxes: the option's value reached the employer, chosen by exact value.
    assert sent["question_8101"] == "1" and sent["question_8102"] == "913"
    assert sent["question_8104"] == "0"
    assert "question_8105" not in sent  # its trigger was not met; never filled
    assert "cover_letter_attachment_id" not in sent and "resume_text" not in sent
    assert kinds(led) == {"upload": 1}
    up = json.loads(led["disclosures"][0]["detail"])
    approved = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert up["sha256"] == approved["documents"][0]["sha256"] and up["field"] == "resume"
    assert sent["resume_attachment_id"] == up["attachment_id"]
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    rb = next(e for e in att["evidence"] if e["kind"] == "readback")["data"]
    assert rb["mismatches"] == [] and rb["checked"] == len(approved["answers"])
    rc = next(e for e in att["evidence"] if e["kind"] == "receipt")
    assert rc["strength"] == "employer_confirmation_page" and rc["data"]["receipt_id"] is None
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"


def test_trigger_answer_reveals_a_question_that_is_left_alone(api, receiver):
    # Answering "Yes" shows the conditional question; it was approved as blank and stays so.
    app_id = v2_application(api, worked_before="Yes")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = receiver.ledger()["acceptances"][0]["fields"]
    assert sent["question_8104"] == "1" and "question_8105" not in sent


@pytest.mark.parametrize(
    "mode",
    ["gh2_duplicate_id", "gh2_label_mismatch", "gh2_missing_control", "gh2_new_question",
     "gh2_options_changed"],
)  # fmt: skip
def test_drift_after_approval_stops_before_anything_is_disclosed(api, receiver, mode):
    app_id = v2_application(api)
    aid = queue(api, app_id)
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert "changed since you approved" in attempt(aid).outcome_detail


@pytest.mark.parametrize(
    "mode,expected,accepted",
    [
        ("gh2_validation_fail", "rejected", 0),
        ("error_before_accept", "unknown", 0),
        ("error_after_accept", "unknown", 1),
        ("drop_after_accept", "unknown", 1),
        ("gh2_no_confirmation", "unknown", 1),  # accepted by the server, nothing shown
        ("upload_fail", "abandoned", 0),
    ],
)
def test_outcome_classification(api, receiver, mode, expected, accepted):
    aid = queue(api, v2_application(api))
    receiver.config(mode=mode)
    assert runner.run_attempt(aid, "w1") == expected
    assert receiver.ledger()["accepted"] == accepted
    # Never retried: a second delivery of the same attempt does nothing.
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["accepted"] == accepted


def test_a_captcha_on_the_form_stops_before_anything_is_disclosed(api, receiver):
    aid = queue(api, v2_application(api))
    receiver.config(mode="gh2_captcha")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "does not solve or bypass" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_combobox_that_does_not_keep_its_choice_is_caught_by_readback(api, receiver):
    aid = queue(api, v2_application(api))
    receiver.config(mode="gh2_combobox_ignores")
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "question_8102" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_capability_entry_is_fixture_only(api):
    g = api.get("/execution/capabilities").json()["adapters"]["greenhouse_dom"]
    assert g["real_destinations"] is False and g["environments"] == ["development", "test"]
    assert all(v.startswith("synthetic") for v in g["unverified"].values())
    assert g["tested_against"] == ["fixtures/ats_receiver/greenhouse_v2.py"]


def test_original_fixture_still_routes_to_the_original_adapter():
    from app.modules.execution.policy import adapter_for

    d = {"origin": BASE, "submit_url": f"{BASE}/gh/examplehealth/jobs/4012001"}
    assert adapter_for({**d, "form_source": "greenhouse_api"}) == "greenhouse_hosted"
    assert adapter_for({**d, "form_source": "greenhouse_api_dom"}) == "greenhouse_dom"
    real = {"origin": "https://job-boards.greenhouse.io",
            "submit_url": "https://job-boards.greenhouse.io/x/jobs/1/submit"}  # fmt: skip
    with pytest.raises(ValueError):
        adapter_for({**real, "form_source": "greenhouse_api_dom"})


# ------------------------------------------------------------------ attachment groups (B3 evidence)


def test_attachment_named_by_its_group_is_mapped_via_the_group():
    from app.modules.preparation import greenhouse as gh

    fields = gh.schema_from_api(api()).fields
    maps = {
        m.key: m for m in dom.map_fields(fields, dom.snapshot(page_html(mode="gh2_attach_group")))
    }
    assert maps["resume"].status == maps["cover_letter"].status == "mapped_via_group"
    assert {m.status for k, m in maps.items() if k not in ("resume", "cover_letter")} == {"mapped"}


@pytest.mark.parametrize("mode", ["gh2_attach_group_wrong", "gh2_attach_group_shared"])
def test_attachment_group_must_be_named_exactly_and_hold_one_file_input(mode):
    from app.modules.preparation import greenhouse as gh

    maps = {m.key: m for m in dom.map_fields(gh.schema_from_api(api()).fields,
                                             dom.snapshot(page_html(mode=mode)))}  # fmt: skip
    assert maps["resume"].status == "label_mismatch"
    with pytest.raises(gh.SchemaMismatch, match="resume: label_mismatch"):
        dom.build_schema(api(), page_html(mode=mode))


def test_full_run_with_group_named_attachments(api, receiver):
    receiver.config(mode="gh2_attach_group")  # before capture: the page structure is read then
    app_id = v2_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_attach_group")  # reset() between steps would not apply here
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    up = json.loads(led["disclosures"][0]["detail"])
    approved = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert up["field"] == "resume" and up["sha256"] == approved["documents"][0]["sha256"]
    assert led["acceptances"][0]["fields"]["resume_attachment_id"] == up["attachment_id"]
