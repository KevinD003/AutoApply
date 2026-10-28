"""C8 (D61): a sensitive answer reaches the employer only as you chose, counted by the receiver's
own ledger. "Include" sends your answer; "Don't disclose" sends nothing on an optional question
and the form's one "decline" option on a required one. Synthetic candidate and form only."""

import pytest

from app.modules.execution import runner
from app.modules.preparation.forms import FieldType, FormField, Option
from app.modules.preparation.resolver import Context, map_decline, resolve_field
from tests.execution_harness import (
    BASE,
    Receiver,
    prepared_application,
    queue,
    synthetic_candidate,
)

WOMAN = {"label": "Woman"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset_receiver(receiver):
    receiver.reset()


def sent(api, receiver, **kw) -> dict:
    """Prepare, approve, queue and run one application; the fields the receiver accepted."""
    app_id = prepared_application(api, receiver, **kw)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    return led["acceptances"][0]["fields"]


def unfinished(api, receiver, slug="clinic") -> str:
    """An application to the receiver's form with everything answered but the gender question."""
    synthetic_candidate(api)
    job_id = api.post(
        "/jobs", json={"url": f"{BASE}/apply/{slug}", "title": f"Clinic Assistant ({slug})"}
    ).json()["job"]["id"]
    r = api.post(f"/jobs/{job_id}/form", json={"html": receiver.form_html(slug)})
    assert r.status_code in (200, 201), r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    r = api.put(
        f"/applications/{app_id}/answers",
        json={"key": "hear_about", "value": {"label": "Referral"}},
    )
    assert r.status_code == 200, r.text
    r = api.put(f"/applications/{app_id}/consents", json={"key": "privacy_ack", "choice": "agree"})
    assert r.status_code == 200, r.text
    return app_id


def gender_row(api, app_id) -> dict:
    v = api.get(f"/applications/{app_id}/package").json()
    return next(a for a in v["package"]["content"]["answers"] if a["key"] == "gender")


def test_include_sends_your_answer(api, receiver):
    fields = sent(api, receiver, sensitive={"gender": (WOMAN, "disclose")})
    assert fields["gender"] == "w"


def test_dont_disclose_on_an_optional_question_sends_nothing(api, receiver):
    fields = sent(api, receiver, sensitive={"gender": (WOMAN, "withhold")})
    assert fields.get("gender", "") == ""


def test_an_answer_without_a_choice_is_never_sent(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    r = api.put(f"/applications/{app_id}/answers", json={"key": "gender", "value": WOMAN})
    assert r.status_code == 200, r.text
    row = gender_row(api, app_id)
    assert row["status"] == "needs_consent"
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert "gender" in p["content"]["unresolved"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 409
    assert receiver.ledger()["accepted"] == 0


def test_dont_disclose_on_a_required_question_sends_the_forms_decline_option(api, receiver):
    receiver.config(mode="required_eeo")
    # Your answer is kept for review, but "Don't disclose" decides what is sent.
    fields = sent(api, receiver, sensitive={"gender": (WOMAN, "withhold")})
    assert fields["gender"] == "decline"


def test_the_decline_option_is_shown_for_review_and_never_saved(api, receiver):
    receiver.config(mode="required_eeo")
    app_id = prepared_application(
        api, receiver, sensitive={"gender": (None, "withhold")}, approve=False
    )
    row = gender_row(api, app_id)
    assert (row["status"], row["display"]) == ("resolved", "Decline to self-identify")
    assert row["sensitive"] is True and row["bankable"] is False
    assert "chose not to disclose" in row["explanation"]


def test_a_required_question_without_a_choice_blocks_approval(api, receiver):
    receiver.config(mode="required_eeo")
    app_id = unfinished(api, receiver)
    r = api.put(f"/applications/{app_id}/answers", json={"key": "gender", "value": WOMAN})
    assert r.status_code == 200, r.text
    assert gender_row(api, app_id)["status"] == "needs_consent"
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert p["content"]["unresolved"] == ["gender"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 409
    assert receiver.ledger()["accepted"] == 0


def select(*labels, required=True, typ=FieldType.select):
    return FormField(
        key="gender",
        label="Gender",
        type=typ,
        required=required,
        options=[Option(value=str(i), label=x) for i, x in enumerate(labels)],
    )


@pytest.mark.parametrize(
    "labels,want",
    [
        (("Woman", "Man", "Decline to self-identify"), "Decline to self-identify"),
        (("Woman", "Man", "I don't wish to answer"), "I don't wish to answer"),
        (("Female", "Male", "Prefer not to say"), "Prefer not to say"),
        (("Female", "Male", "  DECLINE TO ANSWER  "), "  DECLINE TO ANSWER  "),
    ],
)
def test_the_one_decline_option_is_the_answer(labels, want):
    f = select(*labels)
    assert map_decline(f).label == want
    r = resolve_field(f, Context(consents={"gender": "withhold"}))
    assert (r.status, r.source, r.display, r.bankable) == ("resolved", "consent", want, False)
    assert r.value == {"option": str(labels.index(want)), "label": want}


@pytest.mark.parametrize(
    "labels",
    [
        ("Woman", "Man"),  # no decline option
        ("Woman", "Man", "Decline to answer", "Prefer not to say"),  # two: never chosen between
        ("Woman", "Man", "Other / decline"),  # not clearly a decline
        ("Woman", "Man", "Decline"),  # one word could mean anything
        ("Woman", "Man", "I identify as declining"),
    ],
)
def test_without_exactly_one_decline_option_a_required_question_stays_a_checkpoint(labels):
    r = resolve_field(select(*labels), Context(consents={"gender": "withhold"}))
    assert (r.status, r.value) == ("needs_user", None)
    assert "chose not to disclose" in r.explanation


def test_the_decline_option_is_never_picked_without_dont_disclose():
    f = select("Woman", "Man", "Decline to self-identify")
    for consents in ({}, {"gender": "disclose"}):
        r = resolve_field(f, Context(consents=consents))
        assert r.status != "resolved" and r.value is None


def test_an_optional_question_is_left_blank_even_with_a_decline_option():
    r = resolve_field(
        select("Woman", "Decline to self-identify", required=False),
        Context(consents={"gender": "withhold"}),
    )
    assert (r.status, r.value) == ("blank_optional", None)


def test_a_multi_choice_decline_is_one_selected_option():
    f = select("Woman", "Man", "Decline to self-identify", typ=FieldType.checkbox_group)
    r = resolve_field(f, Context(consents={"gender": "withhold"}))
    assert (r.status, r.value) == (
        "resolved",
        {"options": [{"option": "2", "label": "Decline to self-identify"}]},
    )


def test_a_text_question_has_no_decline_option():
    f = FormField(key="gender", label="Gender", type=FieldType.text, required=True)
    assert map_decline(f) is None
    r = resolve_field(f, Context(consents={"gender": "withhold"}))
    assert (r.status, r.value) == ("needs_user", None)


def test_a_saved_answer_is_proposed_and_sent_only_after_include(api, receiver):
    """One policy for the equal-opportunity topics (D61): an answer you saved is proposed on the
    next form, and is sent only after "Include this answer" there."""
    first = prepared_application(api, receiver, approve=False)
    r = api.put(
        f"/applications/{first}/answers",
        json={"key": "gender", "value": WOMAN, "save_to_bank": True},
    )
    assert r.status_code == 200, r.text
    assert len(api.get("/answer-bank").json()) == 1
    second = unfinished(api, receiver, slug="clinic2")
    row = gender_row(api, second)
    assert (row["status"], row["source"], row["display"]) == (
        "needs_consent",
        "answer_bank",
        "Woman",
    )
    r = api.put(f"/applications/{second}/consents", json={"key": "gender", "choice": "disclose"})
    assert r.status_code == 200, r.text
    p = api.get(f"/applications/{second}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{second}/package/approve", json=body).status_code == 200
    assert runner.run_attempt(queue(api, second), "w1") == "confirmed"
    assert receiver.ledger()["acceptances"][0]["fields"]["gender"] == "w"
