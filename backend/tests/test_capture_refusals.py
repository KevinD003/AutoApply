"""D136: a Greenhouse page control that the DOM adapter cannot fill is refused when the form is
read -- a checkpoint if it is required, left blank if not -- never after you approved an answer
for it. Local fixtures only (fixtures/ats_receiver/greenhouse_v2.py and markup added here):
this shows the rule against them, not that real Greenhouse pages use these controls."""

import copy
import sys
from types import SimpleNamespace

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_dom as adapter
from app.modules.preparation import greenhouse as gh
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import CHOICE_TYPES, MULTI_TYPES, FieldType, FormField, Option
from tests.execution_harness import BASE, ROOT, Receiver, queue, synthetic_candidate

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
SUBMIT = '<button type="submit" id="submit_app">'


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def job_data() -> dict:
    return copy.deepcopy(greenhouse_v2._api_json(BOARD, JOB, BASE))  # never the shared JOBS


def form_page(mode="normal", extra="") -> str:
    page = greenhouse_v2._form_page(BOARD, JOB, "t", {"mode": mode}).body.decode()
    assert page.count(SUBMIT) == 1
    return page.replace(SUBMIT, extra + SUBMIT)


def fields(api: dict, page: str) -> dict:
    schema, _ = dom.build_schema(api, page)
    return {f.key: f for f in schema.fields}


def test_capture_lets_through_exactly_what_the_adapter_fills():
    assert adapter.FILLABLE is dom.DOM_FILLABLE  # one list, not two that can drift apart
    for t in FieldType:
        if t == FieldType.unsupported:
            continue
        opts = [Option(value="1", label="Yes")] if t in CHOICE_TYPES | MULTI_TYPES else []
        f = FormField(key="q", label="Q", type=t, options=opts)
        as_combobox = dom.unfillable(f, SimpleNamespace(role="combobox"))
        as_native = dom.unfillable(f, SimpleNamespace(role=None))
        assert (as_combobox is None) == (t.value in adapter.FILLABLE), t
        # A choice is filled only through an ARIA combobox (D108/D109), never a native one.
        assert (as_native is None) == (t.value in adapter.FILLABLE and t != FieldType.select), t
        assert as_native is None or as_native.endswith("(not supported yet)"), t


def test_a_native_dropdown_is_refused_when_the_form_is_read():
    by = fields(job_data(), form_page("gh2_native_select"))
    q = by["question_8104"]
    assert q.type == FieldType.unsupported and q.required
    assert q.unsupported_reason == dom.NATIVE_DROPDOWN_REASON and q.options == []
    assert by["question_8101"].type == FieldType.select  # a combobox there: filled as before
    # The same question as the page's combobox stays a choice you answer.
    assert fields(job_data(), form_page())["question_8104"].type == FieldType.select


def test_a_list_of_several_choices_is_refused_when_the_form_is_read():
    api = job_data()
    shifts = [{"value": 1, "label": "Days"}, {"value": 2, "label": "Nights"}]
    api["questions"].append(
        {
            "label": "Which shifts can you work?",
            "required": False,
            "description": None,
            "fields": [
                {"name": "question_8199", "type": "multi_value_multi_select", "values": shifts}
            ],
        }
    )
    control = (
        '<div class="field"><label for="question_8199">Which shifts can you work?</label>'
        '<select id="question_8199" multiple><option value="1">Days</option>'
        '<option value="2">Nights</option></select></div>'
    )
    q = fields(api, form_page(extra=control))["question_8199[]"]
    assert q.type == FieldType.unsupported and not q.required and q.options == []
    assert q.unsupported_reason == "a list of several choices (not supported yet)"


def test_a_consent_checkbox_is_refused_when_the_form_is_read():
    api = job_data()
    api["data_compliance"][0]["requires_consent"] = True
    # Labelled with the field's own label so that it maps; a page whose wording differs is
    # refused as a whole when it is read (label_mismatch), as before.
    control = (
        f'<div class="field"><label for="{gh.CONSENT_KEY}">{gh.CONSENT_LABEL}</label>'
        f'<input type="checkbox" id="{gh.CONSENT_KEY}"></div>'
    )
    q = fields(api, form_page(extra=control))[gh.CONSENT_KEY]
    assert q.type == FieldType.unsupported and q.required
    assert q.unsupported_reason == "a checkbox (not supported yet)"


def v2_job(api) -> str:
    return api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{JOB}",
            "title": "Support Specialist",
            "employer": "Northwind Example (fictional)",
        },
    ).json()["job"]["id"]


def test_a_required_native_dropdown_is_a_checkpoint_and_nothing_is_sent(api, receiver):
    receiver.config(mode="gh2_native_select")
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    row = {a["key"]: a for a in p["content"]["answers"]}["question_8104"]
    assert row["status"] == "needs_user" and row["value"] is None
    assert row["user_input_allowed"] is False  # not something to answer here
    assert row["unsupported_reason"] == dom.NATIVE_DROPDOWN_REASON
    assert "apply on the employer's site" in row["explanation"]
    assert "question_8104" in p["content"]["unresolved"]
    r = api.put(
        f"/applications/{app_id}/answers",
        json={"key": "question_8104", "value": {"label": "No"}},
    )
    assert r.status_code == 400
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )
    assert r.status_code == 409, r.text
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []


def test_an_optional_native_dropdown_is_left_blank_and_the_application_is_sent(api, receiver):
    # Before D136 it was read as a choice you could leave blank, and the attempt stopped before
    # anything was entered: "the form has changed since you approved it (1 changed: widget)".
    # Reading the form again read it the same way.
    receiver.config(mode="gh2_native_select_optional")
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "preferred_name": {"text": "Sammy"},
        "question_8101": {"label": "Yes"},
    }.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    row = {a["key"]: a for a in p["content"]["answers"]}["question_8104"]
    assert row["status"] == "blank_optional" and row["value"] is None
    assert row["explanation"].endswith("Left blank.")
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )
    assert r.status_code == 200, r.text
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    assert sent["question_8101"] == "1" and "question_8104" not in sent
