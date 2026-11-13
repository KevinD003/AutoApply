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
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter, number_text
from app.modules.execution.adapters.form_entries import ENTRIES_JS, sends
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import forms
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import SENT_OTHERWISE, FieldType, extract_form_schema, sent_len
from tests.execution_harness import (
    BASE,
    Receiver,
    attempt,
    prepared_application,
    queue,
    synthetic_candidate,
)
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
    ('wrap="off"', False),  # measured in Chromium: none of these hard-wraps
    ('wrap="virtual"', False),
    ('wrap=" hard"', False),
    ('wrap="hard "', False),
    ('wrap="hard" cols="20"', True),
    ('wrap="HARD"', True),
    ('wrap="physical"', True),  # Chromium hard-wraps on these too
    ('wrap="on"', True),
    ('wrap="hard" wrap="soft"', True),  # written twice: the browser keeps the first
    ('wrap="soft" wrap="hard"', False),
], ids=["none", "soft", "soft-capitals", "empty", "off", "virtual", "hard-after-space",
        "hard-before-space", "hard", "hard-capitals", "physical", "on", "twice-hard-first",
        "twice-soft-first"])  # fmt: skip
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
    "unknown-type": '<label for="u">Nickname</label><input id="u" name="nick" type="nick" {a}>',
    "textarea": '<label for="t">Why us?</label><textarea id="t" name="why" {a}></textarea>',
    "number": '<label for="n">Years</label><input id="n" name="years" type="number" {a}>',
    "select": ('<label for="s">Country</label><select id="s" name="country" {a}>'
               '<option value="US">United States</option></select>'),
    "checkbox": '<label><input type="checkbox" name="agree" {a}> I agree</label>',
    "radio": ("<fieldset><legend>Relocate?</legend><label><input type='radio' name='relocate'"
              " value='yes'> Yes</label><label><input type='radio' name='relocate' value='no' {a}>"
              " No</label></fieldset>"),  # only the second choice carries it
    "file": '<label for="r">Resume</label><input id="r" name="resume" type="file" {a}>',
}  # fmt: skip
# Measured in Chromium: `dirname` adds a field for a text area and a typed box (an unknown type is
# a text box), even empty (a field with no name), and none for a number, a choice, a list or a file.
DIRNAME_SENDS = {"text", "email", "unknown-type", "textarea"}


def read_one(kind: str, attr: str):
    (f,) = extract_form_schema("<form>" + CONTROLS[kind].format(a=attr) + "</form>").fields
    return f


@pytest.mark.parametrize("kind", list(CONTROLS))
def test_a_control_given_to_a_form_by_name_is_refused(kind):
    """`form` may give the control to another form, or to none: whatever it names, refused. One
    question each, a choice group's included (one of its choices is enough)."""
    plain, f = read_one(kind, ""), read_one(kind, 'form="elsewhere"')
    assert plain.type != FieldType.unsupported
    assert f.key == plain.key and f.label == plain.label
    assert f.type == FieldType.unsupported and f.unsupported_reason == SENT_OTHERWISE


@pytest.mark.parametrize("value", ["why.dir", ""], ids=["named", "empty"])
@pytest.mark.parametrize("kind", list(CONTROLS))
def test_a_control_whose_dirname_sends_a_field_of_its_own_is_refused(kind, value):
    """`dirname` sends your text's direction as a field of its own, where Chromium sends one."""
    f = read_one(kind, f'dirname="{value}"')
    if kind in DIRNAME_SENDS:
        assert f.type == FieldType.unsupported and f.unsupported_reason == SENT_OTHERWISE
    else:
        assert f.type == read_one(kind, "").type != FieldType.unsupported


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


def gh_page(**cfg) -> tuple[dict, str]:
    api_json = greenhouse_like._api_json("examplehealth", "4012001", BASE)
    page_ = greenhouse_like._form_page("examplehealth", "4012001", "t", {"mode": "normal", **cfg})
    return api_json, page_.body.decode()


def test_greenhouse_classic_keeps_its_cross_check_where_the_page_refuses_a_question():
    """D159 review: the refusal was adopted before the job data and the page were compared, so a
    page control of another type (a list where the job data says text area) passed. They are
    compared as the page reads without D159's rule, then the refusal is taken. The list keeps
    the question's wording, help and requirement, so its type is the only difference."""
    api_json, html = gh_page()
    textarea = html[html.index('<textarea id="question_7007"') :]
    textarea = textarea[: textarea.index("</textarea>") + len("</textarea>")]
    as_list = ('<select id="question_7007" name="question_7007" form="elsewhere" '
               'aria-describedby="question_7007_help"><option value="1">One</option></select>')  # fmt: skip
    listed = html.replace(textarea, as_list)
    page_q = {f.key: f for f in gh.rendered_schema(listed, sent_rule=False).fields}["question_7007"]
    api_q = {f.key: f for f in gh.schema_from_api(api_json).fields}["question_7007"]
    assert page_q.type == FieldType.select and api_q.type == FieldType.textarea
    assert (page_q.label, page_q.help_text, page_q.required) == (
        api_q.label, api_q.help_text, api_q.required)  # fmt: skip
    with pytest.raises(gh.SchemaMismatch, match="1 different"):
        gh.build_schema(api_json, listed)


def test_greenhouse_classic_holds_an_answer_to_its_page_s_own_limit():
    """D159 review: the job data states no limit, and the page's own was never read, so an answer
    the page would cut was approved and the attempt paused for a form a read could never show.
    The page's limit is now recorded where the job data states none."""
    api_json, html = gh_page(sends="gh_limit_served")
    assert 'maxlength="20" id="question_7007"' in html
    q = {f.key: f for f in gh.build_schema(api_json, html).fields}["question_7007"]
    assert q.type == FieldType.textarea and q.max_length == 20
    api_json, plain = gh_page()
    plain_q = {f.key: f for f in gh.build_schema(api_json, plain).fields}["question_7007"]
    assert plain_q.max_length is None


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
    # D159 review: the limit is named (a number, never the question), so you can shorten it
    assert "500 characters as the form sends them" in attempt(str(p.attempt_id)).outcome_detail


def test_a_limit_no_read_of_the_form_would_record_stops_plainly_naming_it(api, receiver):
    """D159 review: written "500.0", the browser reads 500 and the form reader nothing, so a
    pause could never be ended by reading the form again. A plain stop, nothing entered."""
    receiver.config(sends="limit_unreadable", autosave=True)
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert pauses(app_id) == []
    assert fixture_ats.LIMIT_UNREADABLE.format(limits=500) in attempt(aid).outcome_detail


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


@pytest.mark.parametrize("mode", ["limit_on_input", "limit_on_focus"])
def test_a_limit_lowered_while_the_answers_are_typed_never_gets_a_cut_answer(api, receiver, mode):
    """The page lowers the limit once the first name is typed, after the form was checked, and
    saves "Why us" as it is typed: it is never typed (no save of it at all), and nothing is
    sent. Before D159 the page saved it cut (500 of its characters). D159 review: the same when
    the page lowers it as the box gets focus, so it is read once the box has focus."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode)
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
    monkeypatch.setattr(fixture_ats, "sends", lambda entries, key, want: True)
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


def test_a_page_that_sends_from_formdata_receives_nothing_from_the_readback(api, receiver):
    """D159 review: the readback built `new FormData(form)`, which fires the form's `formdata`
    event; a page sending from it (scripts that submit a form themselves do) received your whole
    application in a rehearsal, which must never submit. The form is now read passively."""
    app_id = prepared_application(api, receiver, scope="disclose_only")
    receiver.config(sends="on_formdata")
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0
    assert not [r for r in led["requests"] if r["path"].endswith("/submit")]


def test_a_stop_after_filling_sends_nothing_through_the_page_s_formdata(api, receiver):
    """The same page, approved to submit, and a value the page changes (the country): the
    readback stops the attempt before the send gate, and the page received nothing (before the
    fix: an acceptance holding the country you never chose)."""
    app_id = prepared_application(api, receiver)
    receiver.config(sends="on_formdata", tamper="select")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_a_choice_the_page_disables_once_chosen_is_never_taken_as_sent(api, receiver):
    """D159 review: a choice was read back by what it shows (the radio ticked), so a group the
    page disables once chosen was confirmed and sent without your answer. It is read as its form
    would send it too."""
    app_id = prepared_application(api, receiver, approve=False)
    r = api.put(f"/applications/{app_id}/answers", json={"key": "relocate",
                                                         "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200, r.text
    approve_current(api, app_id)
    receiver.config(sends="choice_disabled")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize("mode", ["optional_box_form", "optional_group_form"])
def test_an_optional_choice_refused_when_the_form_is_read_is_left_blank(api, receiver, mode):
    """D159 review: a box or a group refused when the form is read was read back as text (a box
    holds "on", a group is two controls), so every attempt stopped after its data was entered.
    Left blank, and the rest sent."""
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver)
    key = "updates" if mode == "optional_box_form" else "contact"
    a = answers(api.get(f"/applications/{app_id}/package").json())[key]
    assert a["value"] is None and SENT_OTHERWISE in a["explanation"]
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert key not in row["fields"] and row["fields"]["first_name"]


def test_a_form_in_another_character_set_never_sends_an_answer_changed(api, receiver):
    """D159 review: a form sending ISO-8859-1 sends "☕" as "&#9749;", whatever the readback reads.
    An answer outside ASCII stops there, with nothing entered; plain text is sent."""
    receiver.config(sends="latin1_form", autosave=True)
    app_id = prepared_application(api, receiver, why_text="Coffee ☕ and patients.")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert "windows-1252" in attempt(aid).outcome_detail  # the browser's name for ISO-8859-1
    r = api.put(f"/applications/{app_id}/answers", json={"key": "why_us", "value": {"text": SHORT}})
    assert r.status_code == 200, r.text
    approve_current(api, app_id)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert receiver.ledger()["acceptances"][0]["fields"]["why_us"] == SHORT


# ---------------------------------------------------------------------------- Greenhouse classic

GH_TEXT = "I enjoy helping patients find their way through care."


def gh_prepared(api, *, answer_7007=True) -> tuple[str, str]:
    """A Greenhouse classic application on the stand-in, approved (as test_greenhouse_adapter's,
    "Why are you interested" answered or not). Returns the application and its job."""
    synthetic_candidate(api)
    job_id = api.post("/jobs", json={"url": f"{BASE}/gh/examplehealth/jobs/4012001",
                                     "title": "Patient Services Coordinator",
                                     "employer": "Example Health Network (fictional)"}
                      ).json()["job"]["id"]  # fmt: skip
    r = api.post(f"/jobs/{job_id}/form/greenhouse")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    given = {"question_7004": {"label": "Referral"}, "question_7005": {"label": "No"},
             "question_7008[]": {"labels": ["English"]}}  # fmt: skip
    if answer_7007:
        given["question_7007"] = {"text": GH_TEXT}
    for key, value in given.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    api.put(f"/applications/{app_id}/consents", json={"key": "question_7009", "choice": "withhold"})
    api.put(f"/applications/{app_id}/consents", json={"key": gh.CONSENT_KEY, "choice": "agree"})
    approve_current(api, app_id)
    return app_id, job_id


def test_greenhouse_classic_pauses_on_a_limit_its_page_lowers_and_a_read_records_it(api, receiver):
    """D159 review: its own check of the page's limit was never run by a test. The page lowers
    "Why are you interested" to 20: D132's pause with nothing entered; reading the form again
    records the limit, ends the pause, and makes the answer yours to shorten."""
    app_id, job_id = gh_prepared(api)
    receiver.config(sends="gh_limit_served")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    (p,) = pauses(app_id)
    assert p.status == "open" and "20 characters" in attempt(str(p.attempt_id)).outcome_detail
    assert api.post(f"/applications/{app_id}/form/recapture").status_code == 200
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("resolved", "new_form")
    q = answers(api.get(f"/applications/{app_id}/package").json())["question_7007"]
    assert q["status"] == "needs_user" and f"{len(GH_TEXT)}/20" in q["explanation"]


def test_greenhouse_classic_pauses_on_a_limit_its_page_s_script_sets(api, receiver):
    app_id, _ = gh_prepared(api)
    receiver.config(sends="gh_limit_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_greenhouse_classic_never_sends_page_text_in_a_question_it_refused(api, receiver):
    """D159 review: its readback skipped unsupported questions, so a text area refused for
    hard-wrapping, into which the page wrote its own text, was sent with it. It must hold
    nothing, as on every other adapter."""
    receiver.config(sends="gh_wrap_page_text")
    app_id, _ = gh_prepared(api, answer_7007=False)
    q = answers(api.get(f"/applications/{app_id}/package").json())["question_7007"]
    assert q["value"] is None and SENT_OTHERWISE in q["explanation"]
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


# ---------------------------------------------------------------------------- what the form sends


def test_sends_is_exact():
    assert sends({"q": ["a"]}, "q", "a") and not sends({"q": ["a", "a"]}, "q", "a")
    assert not sends({"q": ["a\r\nb"]}, "q", "ab") and not sends({"q": [None]}, "q", "a")
    assert sends({}, "q", "") and sends({"q": [""]}, "q", "") and sends({"q": ["", ""]}, "q", "")
    assert not sends({"q": ["", "page text"]}, "q", "")  # an unanswered one: nothing but empty
    assert sends({"q": ["b", "a"]}, "q", ["a", "b"]) and not sends({"q": ["a"]}, "q", ["a", "b"])
    assert sends({}, "q", []) and not sends(None, "q", "") and not sends(None, "q", [])


def test_a_number_is_typed_exactly():
    """D159 review: `f"{n:g}"` kept six significant digits (12345678 was sent as 1.23457e+07)."""
    assert number_text(12345678) == "12345678" and number_text(12345678.0) == "12345678"
    assert number_text(1234567.5) == "1234567.5" and number_text(0.1) == "0.1"
    assert float(number_text(98765.4321)) == 98765.4321


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


# A page holding every way a form sends otherwise than its controls show (measured in Chromium's
# own FormData below), and a listener counting `formdata` events.
ENTRIES_PAGE = """<form id="app">
<input name="plain" value="typed">
<input name="off" value="x" disabled>
<fieldset disabled><input name="in_disabled_set" value="x"></fieldset>
<input name="given_away" value="x" form="other">
<input name="twin" value="one"><input type="hidden" name="twin" value="two">
<textarea name="soft" cols="5">a long line of text</textarea>
<textarea name="hard" cols="5" wrap="hard">a long line of text</textarea>
<input name="dir" value="x" dirname="dir.name">
<input type="checkbox" name="box_on" checked><input type="checkbox" name="box_off">
<input type="radio" name="pick" value="a"><input type="radio" name="pick" value="b" checked>
<select name="list"><option value="1">One</option><option value="2" selected>Two</option></select>
<select name="many" multiple><option value="1" selected>1</option><option value="2" selected
 disabled>2</option><option value="3" selected>3</option></select>
<datalist id="dl"><input name="in_datalist" value="x"></datalist>
<button type="submit" name="go" value="1">Go</button>
</form>
<form id="other"></form>
<input name="joined" value="from outside" form="app">
<script>window.fd = 0; document.getElementById('app').addEventListener('formdata', () => {
  window.fd++; });</script>"""


def test_the_form_is_read_as_the_browser_would_send_it_without_its_formdata_event(page):  # noqa: F811
    page.set_content(ENTRIES_PAGE)
    got = page.locator("#app").evaluate(ENTRIES_JS)
    assert page.evaluate("() => window.fd") == 0  # nothing the page could act on
    assert got == {
        "plain": ["typed"],
        "twin": ["one", "two"],
        "soft": ["a long line of text"],
        "hard": [None],
        "dir": ["x"],
        "dir.name": [None],
        "box_on": ["on"],
        "pick": ["b"],
        "list": ["2"],
        "many": ["1", "3"],
        "in_datalist": ["x"],
        "joined": ["from outside"],
    }
    # Chromium's own entry list, for the same page: the same names, the same values (where the
    # passive read records None it cannot know them; the hard wrap's line breaks among them)
    real = page.evaluate("""() => { const out = {};
      for (const [k, v] of new FormData(document.getElementById('app'))) {
        (out[k] = out[k] || []).push(v); }
      return out; }""")
    assert set(real) == set(got)
    for name, values in got.items():
        assert [v for v in values if v is not None] == [
            v for v, mine in zip(real[name], values, strict=True) if mine is not None
        ]
    assert real["hard"] != ["a long line of text"] and real["dir.name"] == ["ltr"]


def test_a_work_entry_is_read_back_without_its_form_s_formdata_event(page):  # noqa: F811
    """D155's readback built a FormData too (the Workday-style wizard's work entries)."""
    count = (
        "<script>window.fd = 0; document.querySelector('form')"
        ".addEventListener('formdata', () => { window.fd++; });</script>"
    )
    page.set_content(section_page(extra=count))
    entries = ws.plan(frozen_parts())
    ws.apply(page, entries, ROOT)
    assert ws.readback(page, entries, ROOT) == []
    assert page.evaluate("() => window.fd") == 0


def test_a_number_is_typed_and_read_back_exactly_in_the_browser(page):  # noqa: F811
    page.set_content(
        '<form id="application"><label for="s">Salary</label><input id="s" '
        'name="salary" type="number" step="any"><button type="submit">Go</button>'
        "</form>"
    )
    adapter = FixtureAtsAdapter.__new__(FixtureAtsAdapter)
    adapter.content = {"answers": [{"key": "salary", "type": "number",
                                    "value": {"number": 12345678}}]}  # fmt: skip
    adapter.documents = {}
    adapter._fill_one(page, adapter.content["answers"][0])
    assert page.locator("#s").evaluate("e => e.valueAsNumber") == 12345678
    assert adapter.readback(page) == []
