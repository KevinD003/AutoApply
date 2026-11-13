"""D159: an ordinary answer reaches the employer exactly as it was approved, or nothing is sent.

Before D159 the readback compared what each control shows (`input_value`), not what its form
would send, and the page's own limit was read only when the form was read. So:
  * a text area made to hard-wrap sent line breaks you never wrote, a control given to another
    form or disabled sent nothing, and a second control of the same name sent two values, each
    after a readback that passed (the base stand-in's ledger, below);
  * a limit the page lowered after the form was read cut your answer as it was typed, where a
    page that saves as you type kept it cut, and reading the form again stored nothing new (a
    form's limits were in neither its fingerprint nor its version).
Now a control whose form would not send what is typed is refused when the form is read; the
limit each control has now is read before anything is entered and again before each value is
typed; a form whose limits changed is a new version; and the readback reads what the
application form would send.

The receiver's own ledger is the oracle. Passing here shows fixture compatibility only, never how
a real employer's page behaves. Synthetic candidate data only."""

import json
import sys
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import forms
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import SENT_OTHERWISE, FieldType, extract_form_schema, sent_len
from tests.execution_harness import BASE, Receiver, prepared_application, queue
from tests.execution_harness import ROOT as REPO
from tests.test_preparation import answers
from tests.test_workday_entry_details import LOCATION, frozen_parts
from tests.test_workday_experience import (
    ROOT,
    _browser,  # noqa: F401  (the module's browser, for `page`)
    page,  # noqa: F401
    section_page,
)

sys.path.insert(0, str(REPO / "fixtures" / "ats_receiver"))
import greenhouse_like  # noqa: E402

WHY = ("I kept the front desk of a busy clinic running for three years. " * 9).strip()
SHORT = "I kept the front desk of a busy clinic running for three years."
assert 500 < sent_len(WHY) <= 1000  # fits the page's 1000, never its lowered 500


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def pauses(app_id: str) -> list[ApplicationPause]:
    with SessionLocal() as db:
        return db.scalars(
            select(ApplicationPause)
            .where(ApplicationPause.application_id == uuid.UUID(app_id))
            .order_by(ApplicationPause.created_at)
        ).all()


def why_saves(led: dict) -> list[dict]:
    """What the page saved of "Why us" as it was typed (`limit_on_input`): lengths only."""
    saved = [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "autosave"]
    return [d for d in saved if d["field"] == "why_us"]


def approve_current(api, app_id: str):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert not p["content"]["unresolved"], p["content"]["unresolved"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------- reading the form


def textarea_page(attrs: str, required: str = "") -> str:
    return (f'<form><label for="w">Why us?</label><textarea id="w" name="why" {attrs}{required}>'
            "</textarea></form>")  # fmt: skip


@pytest.mark.parametrize("attrs, refused", [
    ("", False),
    ('wrap="soft"', False),
    ('wrap="SOFT"', False),
    ('wrap=""', False),
    ('wrap="hard" cols="20"', True),
    ('wrap="HARD"', True),
    ('wrap="physical"', True),  # the browser hard-wraps on it too
    ('wrap="off"', True),  # not soft: refused rather than read
    ('wrap="hard" wrap="soft"', True),  # written twice: the browser keeps the first
    ('wrap="soft" wrap="hard"', False),
], ids=["none", "soft", "soft-capitals", "empty", "hard", "hard-capitals", "physical", "off",
        "twice-hard-first", "twice-soft-first"])  # fmt: skip
def test_a_text_area_that_hard_wraps_is_refused_when_the_form_is_read(attrs, refused):
    (f,) = extract_form_schema(textarea_page(attrs)).fields
    if refused:
        assert f.type == FieldType.unsupported and f.unsupported_reason == SENT_OTHERWISE
    else:
        assert f.type == FieldType.textarea and f.unsupported_reason is None


@pytest.mark.parametrize("required", [True, False])
def test_a_refused_question_keeps_whether_the_page_requires_it(required):
    """D136's rule: a required one is a checkpoint, an optional one left blank."""
    html = textarea_page('wrap="hard"', " required" if required else "")
    (f,) = extract_form_schema(html).fields
    assert f.type == FieldType.unsupported and f.required is required


CONTROLS = {
    "text": '<label for="c">City</label><input id="c" name="city" {a}>',
    "email": '<label for="e">Email</label><input id="e" name="email" type="email" {a}>',
    "textarea": '<label for="t">Why us?</label><textarea id="t" name="why" {a}></textarea>',
    "select": ('<label for="s">Country</label><select id="s" name="country" {a}>'
               '<option value="US">United States</option></select>'),
    "checkbox": '<label><input type="checkbox" name="agree" {a}> I agree</label>',
    "radio": ("<fieldset><legend>Relocate?</legend><label><input type='radio' name='relocate'"
              " value='yes'> Yes</label><label><input type='radio' name='relocate' value='no' {a}>"
              " No</label></fieldset>"),  # only the second choice carries it
    "file": '<label for="r">Resume</label><input id="r" name="resume" type="file" {a}>',
}  # fmt: skip


@pytest.mark.parametrize("attr", ['form="elsewhere"', 'dirname="why.dir"'], ids=["form", "dirname"])
@pytest.mark.parametrize("kind", list(CONTROLS))
def test_a_control_of_another_form_or_sending_its_direction_is_refused(kind, attr):
    """`form` may give the control to another form, or to none; `dirname` sends your text's
    direction as a field of its own. One question each, a choice group's included."""
    (plain,) = extract_form_schema("<form>" + CONTROLS[kind].format(a="") + "</form>").fields
    (f,) = extract_form_schema("<form>" + CONTROLS[kind].format(a=attr) + "</form>").fields
    assert plain.type != FieldType.unsupported
    assert f.key == plain.key and f.label == plain.label
    assert f.type == FieldType.unsupported and f.unsupported_reason == SENT_OTHERWISE


def test_a_reason_read_before_keeps_its_wording():
    """A password is refused as a password, whatever else its tag says (its fingerprint, which
    approvals and answers are bound to, is unchanged)."""
    html = ('<form><label for="p">Password</label>'
            '<input id="p" name="pw" type="password" form="x"></form>')  # fmt: skip
    (f,) = extract_form_schema(html).fields
    assert f.type == FieldType.unsupported and "password" in f.unsupported_reason


def test_greenhouse_classic_refuses_it_as_its_page_reads_it():
    """Greenhouse's job data says "text area"; its page's control hard-wraps. The job data and
    the page are still compared (wording, requirement), and the question is refused."""
    api_json = greenhouse_like._api_json("examplehealth", "4012001", BASE)
    page_ = greenhouse_like._form_page("examplehealth", "4012001", "t", {"mode": "normal"})
    html = page_.body.decode()
    before = {f.key: f for f in gh.build_schema(api_json, html).fields}["question_7007"]
    assert before.type == FieldType.textarea
    hard = html.replace('<textarea id="question_7007"',
                        '<textarea wrap="hard" cols="20" id="question_7007"')  # fmt: skip
    assert hard != html
    q = {f.key: f for f in gh.build_schema(api_json, hard).fields}["question_7007"]
    assert q.type == FieldType.unsupported and q.unsupported_reason == SENT_OTHERWISE
    assert (q.label, q.required) == (before.label, before.required)
    with pytest.raises(gh.SchemaMismatch):  # a difference beyond it is still one
        gh.build_schema(api_json, hard.replace("Why are you interested", "Why do you apply"))


# ---------------------------------------------------------------------------- the form's version


def a_job(api) -> str:
    body = {"title": "Clinic Assistant (versions)", "employer": "Example Health Clinic (fictional)"}
    job = api.post("/jobs", json=body).json()
    return job["job"]["id"]


def stored(api, job_id: str, html: str) -> int:
    r = api.post(f"/jobs/{job_id}/form", json={"html": html})
    assert r.status_code in (200, 201), r.text
    return r.json()["version"]


def test_a_form_whose_limit_changed_is_a_new_version(api, receiver):
    """Neither the fingerprint nor the options hold a limit: before D159, reading the form again
    after the page lowered one kept the stored version, and its old limit."""
    job_id = a_job(api)
    html = receiver.form_html()
    v1 = stored(api, job_id, html)
    assert stored(api, job_id, receiver.form_html()) == v1  # read again unchanged: kept
    lowered = html.replace('maxlength="1000"', 'maxlength="500"')
    assert lowered != html
    assert stored(api, job_id, lowered) == v1 + 1
    schema = api.get(f"/jobs/{job_id}/form").json()["schema"]
    assert {f["key"]: f.get("max_length") for f in schema["fields"]}["why_us"] == 500


# ---------------------------------------------------------------------------- through the runner


def test_an_answer_longer_than_the_page_now_accepts_pauses_before_anything_is_entered(
    api, receiver
):
    """The page's script lowers the limit when it loads, after the form was read: before
    anything is entered (no document, no answer saved), D132's pause."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends="limit_at_load", autosave=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    (p,) = pauses(app_id)
    assert p.status == "open" and p.detail == {"new": 0, "changed": 1, "missing": 0}


def test_reading_the_form_again_records_the_new_limit_and_your_shorter_answer_is_sent(
    api, receiver
):
    """The employer lowered the limit in the page itself: the attempt pauses with nothing
    entered; the form read again is a new version, which ends the pause and makes your answer
    yours to shorten (D158); the shorter one is sent."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends="limit_served")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open"
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    stored(api, job_id, receiver.form_html())
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("resolved", "new_form")
    why = answers(api.get(f"/applications/{app_id}/package").json())["why_us"]
    assert why["status"] == "needs_user" and f"{sent_len(WHY)}/500" in why["explanation"]
    r = api.put(f"/applications/{app_id}/answers", json={"key": "why_us", "value": {"text": SHORT}})
    assert r.status_code == 200, r.text
    approve_current(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert row["fields"]["why_us"] == SHORT


def test_a_limit_lowered_while_the_answers_are_typed_never_gets_a_cut_answer(api, receiver):
    """The page lowers the limit once the first name is typed, after the form was checked, and
    saves "Why us" as it is typed: it is never typed (no save of it at all), and nothing is
    sent. Before D159 the page saved it cut (500 of its characters)."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends="limit_on_input")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and why_saves(led) == []


SENT_OTHERWISE_MODES = ["hard_wrap_on_input", "other_form_on_input", "disabled_on_input",
                        "twin_on_input"]  # fmt: skip


@pytest.mark.parametrize("mode", SENT_OTHERWISE_MODES)
def test_what_the_form_would_send_is_read_back_and_nothing_else_is_sent(api, receiver, mode):
    """Once "Why us" is typed the page makes its form send something else: line breaks of its
    own, nothing (another form, disabled), or a second value. The control still shows the
    approved text; the readback reads what the form would send, and nothing is sent."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode)
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize("mode", ["hard_wrap_on_input", "other_form_on_input", "disabled_on_input"])
def test_before_d159_the_employer_received_something_else(api, receiver, monkeypatch, mode):
    """The oracle's side: as before D159 (the readback reading only what the control shows, and
    the form read again after filling without D159's rule), the application is confirmed and the
    stand-in received something you never approved. (A second control of the name made the
    readback fail before D159 too, by the browser's strict mode.)"""
    monkeypatch.setattr(FixtureAtsAdapter, "_sends", staticmethod(lambda entries, key, want: True))
    monkeypatch.setattr(forms, "sent_otherwise", lambda n: False)
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    got = row["fields"].get("why_us")
    assert got != WHY
    if mode == "hard_wrap_on_input":  # your text, with line breaks it added where it wrapped
        assert "\r\n" in got and got.replace("\r\n", "") == WHY
    else:  # given to another form, or disabled: not sent at all
        assert got is None


def test_a_value_the_page_puts_under_an_unanswered_question_s_name_is_never_sent(api, receiver):
    """Left unanswered, "Why us" gets a second control of its name from the page, holding the
    page's own text. The readback reads its form's values under that name: nothing but empty
    ones, so that text is never sent."""
    app_id = prepared_application(api, receiver)
    receiver.config(sends="twin_unanswered")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_a_text_area_made_to_hard_wrap_when_the_page_loads_pauses_before_anything_is_entered(
    api, receiver
):
    """The page's script makes it hard-wrap at load: the form the attempt reads is not the
    approved one (the question is refused there), so D132's pause, with nothing entered."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends="hard_wrap_at_load", autosave=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_a_text_area_that_hard_wraps_when_the_form_is_read_is_left_blank(api, receiver):
    """Optional, so left blank (D136); everything else is sent."""
    receiver.config(sends="hard_wrap_served")
    app_id = prepared_application(api, receiver, why_text=WHY)
    why = answers(api.get(f"/applications/{app_id}/package").json())["why_us"]
    assert why["value"] is None and SENT_OTHERWISE in why["explanation"]
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert not row["fields"].get("why_us") and row["fields"]["first_name"]


# ---------------------------------------------------------------------------- a work entry (D155)
# Last in the module: its browser (module-scoped) holds Playwright's synchronous API until the
# module ends, and the runner opens its own.


def test_an_entry_control_given_to_another_form_on_the_page_is_found(page):  # noqa: F811
    """D155 read the control's own form's data, so a control given to another form that exists
    passed, though the application form would not send it."""
    page.set_content(section_page())
    entries = ws.plan(frozen_parts())
    ws.apply(page, entries, ROOT)
    assert ws.readback(page, entries, ROOT) == []
    page.evaluate("""() => { const f = document.createElement('form'); f.id = 'elsewhere';
      document.body.append(f);
      document.querySelector('[name="work[0].location"]').setAttribute('form', 'elsewhere'); }""")
    assert page.locator('[name="work[0].location"]').input_value() == LOCATION
    assert "section:employment:0:location" in ws.readback(page, entries, ROOT)
