"""C7 (D60): an answer or a consent applies only to the question it was given for, and a
"disclose" choice only to the exact answer it covered. A fictional manual form, recaptured with
other wording; synthetic data only."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.preparation.binding import value_digest
from app.modules.preparation.models import ApplicationInput
from app.modules.preparation.resolver import CHANGED_ANSWER, CHANGED_QUESTION
from tests.test_preparation import setup_candidate

YEARS = {
    "key": "years",
    "label": "How many years of bookkeeping experience do you have?",
    "type": "text",
    "required": True,
}
ACK = {
    "key": "ack",
    "label": "I confirm the information I provided is accurate",
    "type": "checkbox",
    "required": True,
}
GENDER = {
    "key": "gender",
    "label": "Gender",
    "type": "select",
    "required": False,
    "options": [
        {"value": "f", "label": "Female"},
        {"value": "m", "label": "Male"},
        {"value": "d", "label": "Decline to answer"},
    ],
}


def form(*fields):
    return {"form": {"title": "Synthetic form", "fields": list(fields)}}


def start(api, *fields):
    job = api.post("/jobs", json={"title": "Bookkeeper", "employer": "Example Books (fictional)"})
    job_id = job.json()["job"]["id"]
    assert api.post(f"/jobs/{job_id}/form", json=form(*fields)).status_code == 201
    return job_id, api.post("/applications", json={"job_id": job_id}).json()["id"]


def recapture(api, job_id, *fields):
    assert api.post(f"/jobs/{job_id}/form", json=form(*fields)).status_code == 201


def rows(api, app_id):
    v = api.get(f"/applications/{app_id}/package").json()
    return {a["key"]: a for a in v["package"]["content"]["answers"]}, v


def answer(api, app_id, key, value):
    r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
    assert r.status_code == 200, r.text


def consent(api, app_id, key, choice):
    r = api.put(f"/applications/{app_id}/consents", json={"key": key, "choice": choice})
    assert r.status_code == 200, r.text


def inputs(app_id) -> dict:
    with SessionLocal() as db:
        q = select(ApplicationInput).where(ApplicationInput.application_id == uuid.UUID(app_id))
        return {(i.kind, i.field_key): i for i in db.scalars(q)}


def test_an_answer_for_another_wording_is_asked_again(api):
    setup_candidate(api)
    job_id, app_id = start(api, YEARS)
    answer(api, app_id, "years", {"text": "5"})
    assert rows(api, app_id)[0]["years"]["status"] == "resolved"
    # The answer records the question it was given for (not only the form's capture time).
    assert set(inputs(app_id)[("answer", "years")].meta) == {"field_fp"}
    recapture(api, job_id, YEARS)  # the same question again: kept
    assert rows(api, app_id)[0]["years"]["display"] == "5"
    reworded = {**YEARS, "label": "How many years of payroll experience do you have?"}
    recapture(api, job_id, reworded)
    row = rows(api, app_id)[0]["years"]
    assert (row["status"], row["value"]) == ("needs_user", None)
    assert row["explanation"].startswith(CHANGED_QUESTION)
    answer(api, app_id, "years", {"text": "2"})
    assert rows(api, app_id)[0]["years"]["display"] == "2"


def test_a_choice_answer_for_other_options_is_asked_again(api):
    setup_candidate(api)
    q = {
        "key": "shift",
        "label": "Which shift do you prefer?",
        "type": "select",
        "required": True,
        "options": [{"value": "d", "label": "Day"}, {"value": "n", "label": "Night"}],
    }
    job_id, app_id = start(api, q)
    answer(api, app_id, "shift", {"label": "Day"})
    # "Day" is still offered, but the question now offers something else too.
    recapture(api, job_id, {**q, "options": [*q["options"], {"value": "w", "label": "Weekend"}]})
    row = rows(api, app_id)[0]["shift"]
    assert (row["status"], row["value"]) == ("needs_user", None)


def test_agreeing_to_one_statement_never_agrees_to_another(api):
    setup_candidate(api)
    job_id, app_id = start(api, ACK)
    consent(api, app_id, "ack", "agree")
    assert rows(api, app_id)[0]["ack"]["status"] == "resolved"
    other = {**ACK, "label": "I confirm the information I provided is accurate and may be shared"}
    recapture(api, job_id, other)
    row, v = rows(api, app_id)
    assert row["ack"]["status"] != "resolved" and row["ack"]["value"] is None
    assert row["ack"]["explanation"].startswith(CHANGED_QUESTION)
    assert "ack" in v["package"]["content"]["unresolved"]
    consent(api, app_id, "ack", "agree")
    assert rows(api, app_id)[0]["ack"]["status"] == "resolved"


def test_a_disclose_choice_covers_only_the_answer_it_was_given_for(api):
    setup_candidate(api)
    _, app_id = start(api, GENDER)
    answer(api, app_id, "gender", {"label": "Female"})
    consent(api, app_id, "gender", "disclose")
    row = rows(api, app_id)[0]["gender"]
    assert (row["status"], row["display"]) == ("resolved", "Female")
    # The stored choice holds a keyed digest of the answer, never the answer.
    meta = inputs(app_id)[("consent", "gender")].meta
    assert set(meta) == {"field_fp", "value_digest"} and len(meta["value_digest"]) == 32
    assert "female" not in str(meta).lower() and "Female" not in str(meta)
    answer(api, app_id, "gender", {"label": "Decline to answer"})
    row = rows(api, app_id)[0]["gender"]
    assert row["status"] == "needs_consent" and row["explanation"].startswith(CHANGED_ANSWER)
    consent(api, app_id, "gender", "disclose")
    row = rows(api, app_id)[0]["gender"]
    assert (row["status"], row["display"]) == ("resolved", "Decline to answer")
    # "Don't disclose" is not tied to the answer: changing it keeps the choice.
    consent(api, app_id, "gender", "withhold")
    answer(api, app_id, "gender", {"label": "Male"})
    assert rows(api, app_id)[0]["gender"]["status"] == "blank_optional"


def test_the_digest_is_scoped_to_the_user_and_the_question():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    v = {"option": "f", "label": "Female"}
    assert value_digest(a, "gender", v) == value_digest(a, "gender", dict(reversed(v.items())))
    assert value_digest(a, "gender", v) != value_digest(b, "gender", v)
    assert value_digest(a, "gender", v) != value_digest(a, "sex", v)


def test_rows_saved_before_binding_use_the_form_version_they_were_saved_against(api):
    """An answer or a choice stored before C7 has no fingerprint: the form version current when
    it was last saved stands in. A "disclose" stored without a digest is asked again."""
    setup_candidate(api)
    job_id, app_id = start(api, YEARS, ACK, GENDER)
    answer(api, app_id, "years", {"text": "5"})
    consent(api, app_id, "ack", "agree")
    answer(api, app_id, "gender", {"label": "Female"})
    consent(api, app_id, "gender", "disclose")
    with SessionLocal() as db:
        for i in db.scalars(
            select(ApplicationInput).where(ApplicationInput.application_id == uuid.UUID(app_id))
        ):
            i.meta = None  # as stored before C7
        db.commit()
    got = rows(api, app_id)[0]
    assert (got["years"]["display"], got["ack"]["status"]) == ("5", "resolved")
    assert got["gender"]["status"] == "needs_consent"  # no digest: confirm again
    recapture(
        api,
        job_id,
        {**YEARS, "label": "How many years of audit experience do you have?"},
        ACK,
        GENDER,
    )
    got = rows(api, app_id)[0]
    assert (got["years"]["status"], got["years"]["value"]) == ("needs_user", None)
    assert got["ack"]["status"] == "resolved"  # its question did not change


def test_a_changed_question_invalidates_the_approval_of_its_answer(api):
    setup_candidate(api)
    job_id, app_id = start(api, YEARS, ACK)
    answer(api, app_id, "years", {"text": "5"})
    consent(api, app_id, "ack", "agree")
    p = rows(api, app_id)[1]["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 200
    recapture(api, job_id, {**YEARS, "label": "How many years of tax experience do you have?"}, ACK)
    _, v = rows(api, app_id)
    assert v["approval"]["status"] == "invalidated"
    assert v["package"]["content"]["unresolved"] == ["years"]
