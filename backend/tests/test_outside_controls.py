"""D160: a control the page gives its application form from outside the form's markup, one the
form would send that no read of the page shows, and a final click that would send another form
(rank 27 of the automation loop; D159's limits).

The browser sends every control in the form's own list (`form.elements`): its form owner decides,
so a control anywhere on the page whose `form` names the form is sent with the application, and
so is one the HTML parser gives the form outside its markup, and what a form-associated custom
element's script sets, under any names. And the click submits the button's own form, to the
button's own address if it names one. Before D160 a read of the page took only the controls
inside the form's markup, the readback checked only the questions read, and nothing compared the
clicked button's form with the form checked: what such a control held was sent unapproved, or
the click sent another form or to another address (`test_before_d160_...`).

Now a control the page gives the form by name is read with the form's own questions, refused
(`GIVEN_FROM_OUTSIDE`: a required one a checkpoint, an optional one left blank), and stops the
attempt before anything is entered when it already holds something; before anything is entered
and again after filling, a control the form would send that the read does not show, a final
click that would send another form or elsewhere, and a form that cannot be singled out or read
each stop the attempt plainly; and a file question's form must send the file alone.

Runs drive the API and the runner against the base stand-in (`cfg["sends"]`), with the
receiver's ledger as the oracle; capture and the passive reads are measured against Chromium's
own list of the form's controls and its own entry list for the same pages; and each adapter's
checks are run on its own stand-in's page."""

import importlib

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters.ashby import AshbyFixtureAdapter
from app.modules.execution.adapters.fixture_ats import (
    _CLICK_TARGET_JS,
    _FORM_CHARSET,
    _REFUSAL_JS,
    CLICK_ELSEWHERE,
    FINAL_CLICK,
    FORM_UNREADABLE,
    REFUSED_HOLDS,
    UNREAD_CONTROLS,
    FixtureAtsAdapter,
    would_refuse,
)
from app.modules.execution.adapters.form_entries import ENTRIES_JS, NAMES_JS, unread
from app.modules.execution.adapters.greenhouse import GreenhouseHostedAdapter
from app.modules.execution.adapters.lever import LeverFixtureAdapter
from app.modules.execution.adapters.workday import WorkdayFixtureAdapter
from app.modules.preparation import forms, workday
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import (
    GIVEN_FROM_OUTSIDE,
    SENT_OTHERWISE,
    FieldType,
    FormField,
    Option,
    extract_form_schema,
)
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_greenhouse_adapter import gh_application
from tests.test_lever_adapter import lever_application
from tests.test_sent_as_approved import gh_page, greenhouse_like, pauses
from tests.test_workday_experience import (
    _browser,  # noqa: F401  (the module's browser, for `page`)
    page,  # noqa: F401
)

PAGE_TEXT = "Text the page wrote (fictional)"
WHY = "I like the clinic."


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


# ---------------------------------------------------------------------------- reading the form

# The application form holds the upload, so it is singled out where the page has another form
# (D118).
FORM = (
    '<form id="application" action="/submit" method="post">'
    '<label for="a">First name</label><input id="a" name="first_name" required>'
    '<label for="cv">CV</label><input type="file" id="cv" name="cv">{inner}</form>'
)
GIVEN = '<label for="x">Anything else?</label><input id="x" name="extra" form="application"{a}>'


def keys(html: str) -> list[str]:
    return [f.key for f in extract_form_schema(html).fields]


@pytest.mark.parametrize(
    "html, order",
    [
        (FORM.format(inner="") + GIVEN.format(a=""), ["first_name", "cv", "extra"]),
        (GIVEN.format(a="") + FORM.format(inner=""), ["extra", "first_name", "cv"]),  # its order
        (
            FORM.format(inner="") + "<div><p>" + GIVEN.format(a="") + "</p></div>",
            ["first_name", "cv", "extra"],
        ),  # fmt: skip
    ],
    ids=["after", "before", "nested"],
)
def test_a_control_given_to_the_form_from_outside_is_read_and_refused(html, order):
    got = {f.key: f for f in extract_form_schema(html).fields}
    assert list(got) == order
    extra = got["extra"]
    assert extra.type == FieldType.unsupported and extra.unsupported_reason == GIVEN_FROM_OUTSIDE
    assert extra.label == "Anything else?" and extra.required is False


@pytest.mark.parametrize("required", [True, False])
def test_a_control_given_from_outside_keeps_whether_the_page_requires_it(required):
    """D136's rule: a required one is a checkpoint, an optional one left blank."""
    html = FORM.format(inner="") + GIVEN.format(a=" required" if required else "")
    assert {f.key: f for f in extract_form_schema(html).fields}["extra"].required is required


def test_a_control_inside_the_form_given_to_another_keeps_d159_s_reason():
    """D160 review: the reason names what happens. Inside the form, `form` naming another form
    sends it elsewhere (D159's reason); outside, given to this form, it is sent with your
    application (D160's)."""
    inner = '<label for="y">Code</label><input id="y" name="code" form="other">'
    got = {f.key: f for f in extract_form_schema(FORM.format(inner=inner)).fields}
    assert got["code"].unsupported_reason == SENT_OTHERWISE


# Each placed after the form, unless it holds a decoy of the form's id, which comes first.
GIVEN_CONTROLS = {
    "textarea": ('<label for="x">Notes</label>'
                 '<textarea id="x" name="extra" form="application"></textarea>'),
    "select": ('<label for="x">Shift</label><select id="x" name="extra" form="application">'
               '<option value="">Select...</option><option value="d">Day</option></select>'),
    "checkbox": ('<label><input type="checkbox" name="extra" form="application"> Keep me '
                 "informed</label>"),
    "radio": ("<fieldset><legend>Shift</legend><label><input type='radio' name='extra' value='d'"
              " form='application'> Day</label><label><input type='radio' name='extra' value='n'"
              " form='application'> Night</label></fieldset>"),
    "in another form": ('<form id="other"><label for="x">Code</label>'
                        '<input id="x" name="extra" form="application"></form>'),
    # D160 reviews: as the browser resolves the name
    "the attribute written twice, the form's first": (
        '<label for="x">Code</label><input id="x" name="extra" form="application" form="other">'),
}  # fmt: skip
DECOYS = {
    "the id first inside a template": '<template><i id="application"></i></template>',
    "the id second on an element": '<div id="other" id="application"></div>',
}  # fmt: skip


def given_page(case: str) -> str:
    if case in DECOYS:
        return DECOYS[case] + FORM.format(inner="") + GIVEN.format(a="")
    return FORM.format(inner="") + GIVEN_CONTROLS[case]


@pytest.mark.parametrize("case", [*GIVEN_CONTROLS, *DECOYS])
def test_every_kind_of_control_given_from_outside_is_refused(case):
    got = {f.key: f for f in extract_form_schema(given_page(case)).fields}
    assert got["extra"].type == FieldType.unsupported
    assert got["extra"].unsupported_reason == GIVEN_FROM_OUTSIDE


NOT_GIVEN = {
    "no form attribute": '<label for="x">Search jobs</label><input id="x" name="extra">',
    "another form named": ('<form id="other"></form><label for="x">Search jobs</label>'
                           '<input id="x" name="extra" form="other">'),
    "a name no form has": ('<label for="x">Search jobs</label>'
                           '<input id="x" name="extra" form="nowhere">'),
    "inside a fieldset given": ('<fieldset form="application"><label for="x">Search jobs</label>'
                                '<input id="x" name="extra"></fieldset>'),
    "a hidden value": '<input type="hidden" name="extra" form="application" value="1">',
    "a button": '<button name="extra" form="application" value="1">Save</button>',
    # D160 reviews: as the browser resolves the name, and only what it can give a form
    "the attribute written twice, another first": (
        '<label for="x">Search jobs</label>'
        '<input id="x" name="extra" form="other" form="application">'),
    "inside a noscript": ('<noscript><label for="x">Search jobs</label>'
                          '<input id="x" name="extra" form="application"></noscript>'),
    "inside a template": ('<template><label for="x">Search jobs</label>'
                          '<input id="x" name="extra" form="application"></template>'),
    "an element that is no control": ('<div role="switch" aria-label="Alerts" aria-required="true"'
                                      ' form="application"></div>'),
}  # fmt: skip


def not_given_page(case: str) -> str:
    if case == "the id first on another element":
        return '<div id="application"></div>' + FORM.format(inner="") + GIVEN.format(a="")
    return FORM.format(inner="") + NOT_GIVEN[case]


@pytest.mark.parametrize("case", [*NOT_GIVEN, "the id first on another element"])
def test_what_the_browser_does_not_give_the_form_is_not_read(case):
    assert keys(not_given_page(case)) == ["first_name", "cv"]


def test_a_form_without_an_id_is_given_nothing():
    html = FORM.format(inner="").replace(' id="application"', "") + GIVEN.format(a="")
    assert keys(html) == ["first_name", "cv"]


def test_greenhouse_classic_refuses_a_page_that_gives_its_form_a_control_the_job_data_lacks():
    """The job data and the page are compared as the page reads: a control given from outside
    is on the page only, a difference (the capture stops, nothing guessed)."""
    api_json, html = gh_page()
    given = ('<label for="fx-extra">Anything else?</label>'
             '<input id="fx-extra" name="fx_extra" form="application_form">')  # fmt: skip
    assert "</form>" in html
    with pytest.raises(gh.SchemaMismatch, match="1 only on the page"):
        gh.build_schema(api_json, html.replace("</form>", "</form>" + given, 1))


def test_greenhouse_classic_adopts_the_refusal_of_a_question_given_from_outside():
    """A question the job data lists whose control the page puts outside the form and gives to
    it: the same question as the page reads it (compared without the refusal), refused as the
    page reads it, so never filled."""
    api_json, html = gh_page()
    textarea = html[html.index('<textarea id="question_7007"') :]
    textarea = textarea[: textarea.index("</textarea>") + len("</textarea>")]
    label = html[html.index('<label for="question_7007"') :]
    label = label[: label.index("</label>") + len("</label>")]
    helper = html[html.index('<p class="help" id="question_7007_help"') :]
    helper = helper[: helper.index("</p>") + len("</p>")]
    given = label + helper + textarea.replace("<textarea ", '<textarea form="application_form" ')
    moved = html.replace(label, "").replace(helper, "").replace(textarea, "")
    moved = moved.replace("</form>", "</form>" + given, 1)
    q = {f.key: f for f in gh.build_schema(api_json, moved).fields}["question_7007"]
    assert q.type == FieldType.unsupported and q.unsupported_reason == GIVEN_FROM_OUTSIDE


def test_a_work_entry_control_given_from_outside_is_the_work_history_checkpoint():
    """D160 review: an entry's control given to the form from outside is never in its section;
    read at capture as work history NoEfforts cannot fill exactly (D149's checkpoint), where it
    was skipped and every attempt stopped."""
    html = ('<form id="workday-application" action="/submit" method="post">'
            '<label for="a">First name</label><input id="a" name="first_name"></form>'
            '<label for="w">Job title</label><input id="w" name="work[0].title"'
            ' form="workday-application">')  # fmt: skip
    assert workday.WORK_KEY in {f.key for f in workday.extract_schema(html).fields}


# ---------------------------------------------------------------------------- what no read shows


def field(key: str, t: FieldType) -> FormField:
    options = [Option(value="d", label="Day")] if t == FieldType.radio else []
    return FormField(key=key, label=key, type=t, required=False, options=options)


@pytest.mark.parametrize(
    "counts, custom, stray, n",
    [
        ({"first_name": 1}, 0, 0, 0),
        ({"first_name": 1, "extra": 2}, 0, 0, 2),  # a name the read does not show
        ({"first_name": 2}, 0, 0, 1),  # a second control under a typed answer's name
        ({"cv": 2}, 0, 0, 1),  # ... under a file's
        ({"shift": 3}, 0, 0, 0),  # a group's choices
        ({"refused": 2}, 0, 0, 0),  # a refused question (a group, maybe): nothing sent there
        ({}, 2, 1, 3),  # custom elements, the parser's
    ],
)
def test_what_the_read_does_not_show_is_counted(counts, custom, stray, n):
    fields = [field("first_name", FieldType.text), field("cv", FieldType.file),
              field("shift", FieldType.radio), field("refused", FieldType.unsupported)]  # fmt: skip
    assert unread({"counts": counts, "custom": custom, "stray": stray}, fields) == n


# ---------------------------------------------------------------------------- what is sent


def without_d160(monkeypatch):
    monkeypatch.setattr(forms, "given_from_outside", lambda *a: False)
    for part in ("_unread_controls", "_click_target", "_refused_holding"):
        monkeypatch.setattr(FixtureAtsAdapter, part, lambda *_, **__: None)
    monkeypatch.setattr(fixture_ats, "file_alone", lambda *_: True)


BEFORE_D160 = {  # mode: what the stand-in received
    "outside_text": ("extra", PAGE_TEXT),
    "outside_on_input": ("extra", PAGE_TEXT),
    "custom_control": ("note", PAGE_TEXT),
    "custom_on_input": ("note", PAGE_TEXT),
    "custom_entries": ("why_us", [WHY, PAGE_TEXT]),  # a second "Why us"
    "stray_hidden": ("extra", PAGE_TEXT),  # one the parser gives the form, hidden
}


@pytest.mark.parametrize("mode", list(BEFORE_D160))
def test_before_d160_the_employer_received_what_the_page_wrote(api, receiver, monkeypatch, mode):
    """The oracle's side: as before D160 (a read of the form takes only the controls inside its
    markup, and nothing checks the rest), the application is confirmed and the stand-in
    received the page's own text with it."""
    without_d160(monkeypatch)
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text=WHY)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    name, held = BEFORE_D160[mode]
    assert row["fields"][name] == held


@pytest.mark.parametrize("mode, path", [("button_formaction", "/apply/clinic/elsewhere"),
                                        ("button_other_form", "/apply/clinic/submit")])  # fmt: skip
def test_before_d160_the_final_click_sent_elsewhere(api, receiver, monkeypatch, mode, path):
    """The oracle's side: with the submit button's own `formaction`, the click sent your
    application to another address of the page's choosing; given to another form of the
    page's, it sent that form (the page's own value, none of yours), which the employer refused.
    Every check before the click passed."""
    without_d160(monkeypatch)
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    outcome = runner.run_attempt(aid, "w1")
    led = receiver.ledger()
    detail = (outcome, attempt(aid).outcome_detail, [r["path"] for r in led["requests"]][-6:])
    assert [r for r in led["requests"] if r["path"] == path] and led["accepted"] == 0, detail


def stopped_before_anything(receiver, app_id, aid, why: str):
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert not [r for r in led["requests"] if r["path"].endswith(("/submit", "/elsewhere"))]
    assert pauses(app_id) == []  # a plain stop: no read of the form would change it
    assert why in attempt(aid).outcome_detail


def test_a_control_given_from_outside_holding_page_text_stops_before_anything_is_entered(
    api, receiver
):
    """Read with the form's questions, refused and left blank: the page's text already in it
    stops the attempt with nothing entered (D160 review: the readback found it only after every
    answer was entered, the résumé uploaded)."""
    receiver.config(sends="outside_text")
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, REFUSED_HOLDS)


def test_an_empty_optional_control_given_from_outside_is_left_blank(api, receiver):
    receiver.config(sends="outside_empty")
    app_id = prepared_application(api, receiver)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert row["fields"].get("extra") in ("", None)


def test_a_required_control_given_from_outside_is_a_checkpoint(api, receiver):
    """A question left to you on the employer's site: the package is never approvable."""
    receiver.config(sends="outside_required")
    with pytest.raises(AssertionError) as e:  # the harness requires nothing left unresolved
        prepared_application(api, receiver, approve=False)
    assert e.value.args[0] == ["extra"]
    (item,) = api.get("/applications").json()
    p = api.get(f"/applications/{item['id']}/package").json()["package"]
    assert p["content"]["unresolved"] == ["extra"]
    r = api.post(f"/applications/{item['id']}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code != 200


def test_a_control_given_once_an_answer_is_typed_stops_before_the_send_gate(api, receiver):
    """The page gives its form a control holding its own text once "Why us" is typed: the read
    of the form after filling shows a new question, and nothing is sent."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends="outside_on_input")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize(
    "mode", ["custom_control", "custom_entries", "custom_clobbered", "stray_twin", "stray_hidden"]
)
def test_a_control_no_read_shows_stops_the_attempt_before_anything_is_entered(api, receiver, mode):
    """A form-associated custom element of the page's own making (even beside a control named
    as the form's own property, `elements`), or a control the HTML parser gives the form
    outside its markup (under the résumé's name, or hidden): no read of the page shows it, so
    reading the form again would not either. A plain stop with nothing entered, naming how
    many, never which."""
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, UNREAD_CONTROLS.format(n=1))
    detail = attempt(aid).outcome_detail
    assert "note" not in detail and "resume" not in detail


def test_a_custom_control_added_once_an_answer_is_typed_stops_before_the_send_gate(api, receiver):
    """D160 reviews: the check after filling (no read shows a custom element, so the form read
    after filling is unchanged): nothing is sent."""
    receiver.config(sends="custom_on_input")
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert UNREAD_CONTROLS.format(n=1) in attempt(aid).outcome_detail


def test_a_second_control_under_a_read_question_s_name_stops_where_a_read_misses_it(
    api, receiver, monkeypatch
):
    """D160 reviews: controls were compared by name, so one the read missed under the name of a
    question it reads (the résumé's) passed. Counted per name now: with the rule that reads a
    given control switched off (standing for any way a read can miss one), the second control
    under the résumé's name still stops the attempt with nothing entered."""
    monkeypatch.setattr(forms, "given_from_outside", lambda *a: False)
    receiver.config(sends="given_twin")
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, UNREAD_CONTROLS.format(n=1))


@pytest.mark.parametrize("mode", ["hidden_twin", "hidden_twin_on_input"])
def test_a_hidden_value_under_the_file_question_s_name_is_never_sent(api, receiver, mode):
    """D160 reviews (since D159): the file readback checked only the upload, so a hidden input
    of the page's under the résumé's name was sent with it. Its form must send the file alone:
    the readback stops one the page adds once "Why us" is typed, after the upload (one there at
    load already makes the upload's own control ambiguous, so nothing is uploaded)."""
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    detail = attempt(aid).outcome_detail
    if mode == "hidden_twin_on_input":  # entered, uploaded, read back: the file not alone
        assert "did not keep their values" in detail, detail
    else:
        assert "did not keep their values" not in detail, detail


@pytest.mark.parametrize(
    "prepare", [lever_application, gh_application], ids=["Lever-style", "Greenhouse classic"]
)
def test_a_hosted_file_question_s_form_must_send_the_file_alone(api, receiver, prepare):
    """D160 reviews: the hosted adapters' and Greenhouse classic's file readbacks checked only
    the upload's handle, so a value of the page's under the résumé's name was sent with it."""
    app_id = prepare(api)
    receiver.config(sends="hidden_twin")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


def test_greenhouse_classic_s_form_it_cannot_read_is_a_plain_stop(api, receiver):
    """D160 review: Greenhouse classic's own read of the page, failing, was an internal error."""
    app_id = gh_application(api)
    receiver.config(sends="outside_unlabelled")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, FORM_UNREADABLE)


@pytest.mark.parametrize("mode", ["button_other_form", "button_formaction"])
def test_a_final_click_that_would_send_elsewhere_stops_before_anything_is_entered(
    api, receiver, mode
):
    """D160 review: the click submits the button's own form, to the button's own address if it
    names one; it must be the form checked, sent as it is."""
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, CLICK_ELSEWHERE)


def test_a_form_that_cannot_be_singled_out_stops_before_anything_is_entered(api, receiver):
    """D160 review: with a second form of the application's id, the checks left it to the
    readback, after every answer was entered."""
    receiver.config(sends="two_forms")
    app_id = prepared_application(api, receiver, why_text=WHY)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, FORM_UNREADABLE)


@pytest.mark.parametrize("mode", ["outside_unlabelled", "given_twin"])
def test_a_form_the_runner_cannot_read_is_a_plain_stop(api, receiver, mode):
    """D160 review: a control given to the form after it was captured that no read can take (no
    label; the name of a question already read) made the runner's own read fail, an internal
    error. A plain stop now, with nothing entered."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    stopped_before_anything(receiver, app_id, aid, FORM_UNREADABLE)


# ------------------------------------------- in Chromium (last: the module's browser stays open)

CHROMIUM_PAGES = [
    FORM.format(inner="") + GIVEN.format(a=""),
    GIVEN.format(a=" required") + FORM.format(inner=""),
    *(given_page(c) for c in [*GIVEN_CONTROLS, *DECOYS]),
    *(not_given_page(c) for c in [*NOT_GIVEN, "the id first on another element"]),
]


@pytest.mark.parametrize("html", CHROMIUM_PAGES)
def test_the_form_is_read_as_chromium_gives_it_its_controls(page, html):  # noqa: F811
    """Measured: the questions a read of the page takes are exactly the controls Chromium lists
    as the form's own (what it would send when filled), hidden values and buttons aside: none
    left unread, none read that it does not send."""
    page.set_content(html)
    got = page.locator("form#application").evaluate(NAMES_JS, [])
    assert got["custom"] == 0 and got["stray"] == 0
    fields = extract_form_schema(html).fields
    assert sorted(got["counts"]) == sorted(f.key for f in fields)
    assert unread(got, fields) == 0


CONTROLS_PAGE = """<form id="app">
<label for="t">T</label><input id="t" name="typed">
<input type="hidden" name="token" value="1">
<input type="checkbox" name="box">
<input name="off" disabled>
<button name="go" value="1">Go</button><input type="submit" name="send" value="Send">
<div class="entries"><input name="entry-1-title"></div>
<fx-named name="note"></fx-named><fx-entries></fx-entries>
</form>
<input name="given" form="app"><input name="elsewhere">
<script>
window.fd = 0;
document.getElementById('app').addEventListener('formdata', () => { window.fd += 1; });
for (const [tag, value] of [['fx-named', 'from the page'], ['fx-entries', null]]) {
  customElements.define(tag, class extends HTMLElement {
    static formAssociated = true;
    connectedCallback() {
      const d = new FormData(); d.append('typed', 'a second value');
      this.attachInternals().setFormValue(value === null ? d : value);
    }
  });
}
</script>"""


def test_the_form_s_controls_are_counted_passively(page):  # noqa: F811
    """Every control the form would send, whatever it holds now (unchecked, disabled, empty),
    by name; not its hidden values or buttons, nor a section's entries (read by their own
    checks); a custom element counted, not named. No `formdata` event is fired."""
    page.set_content(CONTROLS_PAGE)
    got = page.locator("#app").evaluate(NAMES_JS, [".entries"])
    assert page.evaluate("() => window.fd") == 0
    assert got == {"counts": {"typed": 1, "box": 1, "off": 1, "given": 1}, "custom": 2,
                   "stray": 0}  # fmt: skip
    # Chromium's own entry list for the same page: the custom elements' entries are there, one
    # under the name its attribute gives, one under a name of its script's choosing
    real = page.evaluate("""() => [...new FormData(document.getElementById('app'))]""")
    assert ["note", "from the page"] in real and ["typed", "a second value"] in real


def test_a_control_the_parser_gives_the_form_outside_its_markup_is_counted(page):  # noqa: F811
    """D160 reviews: the div holding the form closes inside it, so what follows is outside the
    form's markup and names no form, yet Chromium gives it to the form (measured: its entry
    list holds it). A hidden one too: no read of the markup can show either."""
    page.set_content('<div><form id="app"><input name="typed"></div><input name="twin" value="x">'
                     '<input type="hidden" name="h" value="y"></form>')  # fmt: skip
    got = page.locator("#app").evaluate(NAMES_JS, [])
    assert got == {"counts": {"typed": 1}, "custom": 0, "stray": 2}
    real = page.evaluate("""() => [...new FormData(document.getElementById('app'))]""")
    assert ["twin", "x"] in real and ["h", "y"] in real


def test_a_custom_control_is_read_by_its_name_attribute(page):  # noqa: F811
    """D159's passive read named a form-associated custom element by a `name` property it does
    not have (unless its script defines one), so it read nothing of it; it is named by its
    attribute now, its value unknown (None)."""
    page.set_content(CONTROLS_PAGE)
    got = page.locator("#app").evaluate(ENTRIES_JS)
    assert got["note"] == [None]


CLOBBERED = """<form id="f" accept-charset="windows-1252">
<label for="a">A</label><input id="a" name="typed" required>
<label for="b">B</label><select id="b" name="elements"><option value="1">One</option></select>
<label for="c">C</label><input id="c" name="getAttribute">
<label for="d">D</label><input id="d" name="noValidate">
<label for="e">E</label><input id="e" name="querySelectorAll">
<button type="submit">Send</button><fx-c></fx-c></form>
<script>customElements.define('fx-c', class extends HTMLElement { static formAssociated = true; });
</script>"""


def test_the_form_is_read_whatever_its_controls_are_named(page):  # noqa: F811
    """D160 review: a form's named controls shadow its own properties (`f.elements` was a
    select of the page's, `f.getAttribute` an input), so the reads saw nothing (the custom
    element passed), or threw. They read through the browser's definitions now."""
    page.set_content(CLOBBERED)
    form = page.locator("#f")
    got = form.evaluate(NAMES_JS, [])
    assert got["custom"] == 1
    assert set(got["counts"]) == {"typed", "elements", "getAttribute", "noValidate",
                                  "querySelectorAll"}  # fmt: skip
    assert form.evaluate(ENTRIES_JS)["elements"] == ["1"]
    assert form.evaluate(_FORM_CHARSET) == "windows-1252"
    # D154's read of the final click's form: the required box counted, as the browser would
    got = page.locator("#f button").evaluate(_REFUSAL_JS, [])
    assert got == {"native": True, "required": 1, "refused": 0, "marked": 0}
    # (Playwright's own check that the button is enabled fails on such a page, a control named
    # "getAttribute" in the button's form: the read before the click then stops it, unread.)
    assert would_refuse(lambda: page.locator("#f button"), lambda: [], FINAL_CLICK) == (
        FINAL_CLICK.unread
    )


@pytest.mark.parametrize(
    "button, two_forms, ok",
    [
        ("", False, True),
        (' form="other"', False, False),
        (' formaction="/elsewhere"', False, False),
        (' formmethod="get"', False, False),
        (' formenctype="text/plain"', False, False),
        (' formtarget="_blank"', False, False),
        ("", True, False),
    ],
    ids=[
        "its own form",
        "another form",
        "formaction",
        "formmethod",
        "formenctype",
        "formtarget",
        "two forms of the id",
    ],  # fmt: skip
)
def test_the_final_click_must_send_the_form_checked(page, button, two_forms, ok):  # noqa: F811
    page.set_content(f'<form id="application"><button type="submit"{button}>Send</button></form>'
                     '<form id="other"></form>'
                     + ('<form id="application"></form>' if two_forms else ""))  # fmt: skip
    btn = page.locator("button")
    assert btn.evaluate(_CLICK_TARGET_JS, "form#application") is ok


ADAPTERS = {  # adapter, its stand-in's page, the form's selector
    "base": (FixtureAtsAdapter, None, "#application"),
    "Lever-style": (LeverFixtureAdapter, "lever_like", "#application-form"),
    "Ashby-style": (AshbyFixtureAdapter, "ashby_like", "#ashby-application-form"),
    "Workday-style": (WorkdayFixtureAdapter, "workday_like", "#workday-application"),
    "Greenhouse classic": (GreenhouseHostedAdapter, "greenhouse_like", "#application_form"),
}
POSTINGS = {  # stand-in: its posting, as its own adapter's tests use it
    "lever_like": ("examplehealth", "00000000-0000-4000-8000-00000000a001"),
    "ashby_like": ("examplehealth", "00000000-0000-4000-8000-00000000c001"),
    "workday_like": ("examplehealth", "R-100001"),
    "greenhouse_like": ("examplehealth", "4012001"),
}
CFG = {"mode": "normal", "tamper": None, "wizard": None, "page_check": None,
       "page_check_delay_ms": 800, "sends": None, "autosave": False}  # fmt: skip


def stand_in_html(receiver, module: str | None) -> str:
    if module is None:
        return receiver.form_html("clinic")
    a, b = POSTINGS[module]  # beside greenhouse_like, on the path already
    return importlib.import_module(module)._form_page(a, b, "t", CFG).body.decode()


def adapter_of(cls):
    adapter = cls.__new__(cls)
    adapter.content = {"answers": []}
    adapter._shown_by_page, adapter._filled = {}, False  # the Workday-style adapter's state
    return adapter


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_each_adapter_reads_its_own_page_without_a_stop_and_stops_what_no_read_shows(
    page,  # noqa: F811
    receiver,
    name,
):
    """D160 reviews: each adapter, on its own stand-in's page as served: its form singled out,
    every control read, its final click on that form. Then the same page given a custom element,
    or a final button that sends elsewhere: stopped."""
    cls, module, form = ADAPTERS[name]
    assert greenhouse_like  # the stand-ins' directory is on the path
    page.set_content(stand_in_html(receiver, module))
    adapter = adapter_of(cls)
    assert adapter._unread_controls(page, adapter.extract(page)) is None
    assert adapter._click_target(page, adapter.final_button(page), required=True) is None
    page.evaluate(
        """(sel) => {
      customElements.define('fx-probe',
        class extends HTMLElement { static formAssociated = true; });
      document.querySelector(sel).append(document.createElement('fx-probe')); }""",
        form,
    )
    assert adapter._unread_controls(page, adapter.extract(page)) == UNREAD_CONTROLS.format(n=1)
    adapter.final_button(page).evaluate("(b) => b.setAttribute('formaction', '/elsewhere')")
    assert adapter._click_target(page, adapter.final_button(page)) == CLICK_ELSEWHERE
    assert adapter.page_would_refuse(page) == CLICK_ELSEWHERE  # and right before the send gate
