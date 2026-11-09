"""D135: a typed question Greenhouse's id-only page hides until an earlier answer reveals it (its
trigger unknown) is yours to answer, entered only if the page shows it, and never taken from a
saved answer or a draft. After filling, a revealed question the page requires with no approved
answer pauses the application with nothing submitted; once you answer it, one new attempt sends
it. Against the second Greenhouse-style fixture (question_8105, shown when question_8104 is
"Yes"); the receiver's ledger is the oracle. Synthetic data only: local fixture behaviour, never
evidence of a real page."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import ApplicationPause, AttemptEvent
from app.modules.preparation import package as pk
from app.modules.preparation.forms import UNKNOWN_TRIGGER, Condition, FieldType, FormField, Option
from app.modules.preparation.models import PackageApproval
from app.modules.preparation.resolver import Context, Resolution
from tests.execution_harness import Receiver, attempt, queue
from tests.test_greenhouse_dom import live_application, v2_application

COND = "question_8105"  # "Which team did you work in?": hidden until question_8104 is "Yes"
LABEL = "Which team did you work in?"
MAKERS = pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def answer(api, app_id, key, value):
    r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
    assert r.status_code == 200, r.text


def approve(api, app_id):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    r = api.post(f"/applications/{app_id}/package/approve", json=body)
    assert r.status_code == 200, r.text


def row(api, app_id, key=COND) -> dict:
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return next(a for a in p["content"]["answers"] if a["key"] == key)


def shown_late(key="q1", ftype=FieldType.text, required=False, **kw) -> FormField:
    cond = Condition(key=UNKNOWN_TRIGGER, any_of=["?"])
    return FormField(key=key, label=LABEL, type=ftype, required=required, condition=cond, **kw)


# ------------------------------------------------------------------ preparation


def test_a_question_the_page_reveals_is_yours_to_answer(api, receiver):
    app_id = v2_application(api, worked_before="Yes", approve=False)
    a = row(api, app_id)
    assert (a["status"], a["user_input_allowed"], a["bankable"]) == ("blank_optional", True, False)
    assert pk.SHOWN_BY_PAGE in a["explanation"]
    answer(api, app_id, COND, {"text": "Platform"})
    a = row(api, app_id)
    assert (a["status"], a["source"], a["value"]) == ("resolved", "user_entered",
                                                      {"text": "Platform"})  # fmt: skip


def test_a_saved_answer_or_a_draft_is_never_used_for_it():
    for source in ("answer_bank", "draft"):
        r = Resolution(key="q1", status="resolved", source=source, value={"text": "Platform"},
                       display="Platform", explanation="From your saved answer.")  # fmt: skip
        pk._shown_by_page(shown_late(), r, Context())
        assert (r.status, r.source, r.value, r.display) == (
            "blank_optional", "unresolved", None, None)  # fmt: skip
        assert r.explanation == pk.SHOWN_BY_PAGE and not (r.bankable or r.draftable)
        r = Resolution(key="q1", status="resolved", source=source, value={"text": "Platform"})
        pk._shown_by_page(shown_late(required=True), r, Context())
        assert (r.status, r.value) == ("needs_user", None)  # approval waits for your answer
    for source in ("user_entered", "profile_fact"):  # yours, or an approved profile fact
        r = Resolution(key="q1", status="resolved", source=source, value={"text": "Platform"})
        pk._shown_by_page(shown_late(), r, Context())
        assert (r.status, r.value) == ("resolved", {"text": "Platform"})


def test_while_paused_on_such_a_question_every_one_you_can_answer_asks():
    r = Resolution(key="q1", status="blank_optional", source="unresolved")
    pk._shown_by_page(shown_late(), r, Context(conditional_required=True))
    assert r.status == "needs_user" and pk.PAGE_REQUIRED_IT in r.explanation
    r = Resolution(key="q1", status="blank_optional", source="unresolved", user_input_allowed=False)
    pk._shown_by_page(shown_late(), r, Context(conditional_required=True))
    assert r.status == "blank_optional"  # one you cannot answer here is never forced


def test_a_choice_the_page_reveals_is_still_never_filled():
    yes_no = [Option(value="1", label="Yes"), Option(value="0", label="No")]
    trigger = FormField(key="t1", label="Have you worked here before?", type=FieldType.select,
                        options=yes_no)  # fmt: skip
    offices = [Option(value="a", label="North"), Option(value="b", label="South")]
    choice = shown_late("q2", FieldType.select, required=True, options=offices)
    (_, _), (_, r) = pk.resolve_answers([trigger, choice], Context())
    assert (r.status, r.user_input_allowed, r.value) == ("needs_user", False, None)
    assert "apply on the employer's site" in r.explanation


# ------------------------------------------------------------------ execution (receiver ledger)


@MAKERS
def test_an_answer_is_entered_when_the_page_shows_the_question(api, receiver, make):
    app_id = make(api, worked_before="Yes", approve=False)
    answer(api, app_id, COND, {"text": "Platform"})
    approve(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = receiver.ledger()["acceptances"][0]["fields"]
    assert sent["question_8104"] == "1" and sent[COND] == "Platform"


def test_an_answer_is_never_entered_when_the_page_never_shows_the_question(api, receiver):
    app_id = v2_application(api, worked_before="No", approve=False)
    answer(api, app_id, COND, {"text": "Platform"})
    approve(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = receiver.ledger()["acceptances"][0]["fields"]
    assert sent["question_8104"] != "1" and COND not in sent


@MAKERS
def test_a_revealed_question_the_page_requires_pauses_then_one_attempt_sends_it(
    api, receiver, make
):
    receiver.config(mode="gh2_conditional_required")
    app_id = make(api, worked_before="Yes")  # approved with the question left blank
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0  # entered on the page, nothing submitted
    app_uuid = uuid.UUID(app_id)
    with SessionLocal() as db:
        pause = db.scalar(
            select(ApplicationPause).where(ApplicationPause.application_id == app_uuid)
        )
        assert (pause.kind, pause.status, pause.detail) == ("conditional_required", "open",
                                                            {"required": 1})  # fmt: skip
        approvals = db.scalars(
            select(PackageApproval).where(PackageApproval.application_id == app_uuid)
        ).all()
        assert approvals and all(a.invalidated_at is not None for a in approvals)
        events = db.scalars(
            select(AttemptEvent).where(AttemptEvent.attempt_id == uuid.UUID(aid))
        ).all()
    att = attempt(aid)
    assert att.state == "abandoned" and att.disclosure_started_at is not None
    assert att.send_started_at is None
    # Counts only: never the question's key or label.
    for text in (str(pause.detail), att.outcome_detail, *(str(e.detail) for e in events)):
        assert COND not in text and LABEL not in text
    # Listed under Questions, to be answered there; until then nothing can be approved.
    item = next(i for i in api.get("/questions").json()["items"] if i["application_id"] == app_id)
    assert item["pause"]["kind"] == "conditional_required"
    assert item["pause"]["counts"]["required"] == 1
    q = next(q for q in item["questions"] if q["key"] == COND)
    assert (q["status"], q["category"]) == ("needs_user", "answer")
    # The feed says what happened: never "the form no longer matches", never "nothing was sent".
    note = next(n for n in api.get("/notifications").json()["items"]
                if n["kind"] == "conditional_required")  # fmt: skip
    assert note["application_id"] == app_id and "stopped before submitting" in note["text"]
    r = api.post(f"/applications/{app_id}/pause/dismiss")
    assert r.status_code == 409 and "questions_open" in r.text
    answer(api, app_id, COND, {"text": "Platform"})
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    approve(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][COND] == "Platform"
