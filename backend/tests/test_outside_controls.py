"""D160: a control the page gives its application form from outside the form's markup, and one
the form would send that no read of the page shows (rank 27 of the automation loop; D159's
limits).

The browser sends every control in the form's own list (`form.elements`): its form owner decides,
so a control anywhere on the page whose `form` names the form is sent with the application, and
so is what a form-associated custom element's script sets, under any names. Before D160 a read of
the page took only the controls inside the form's markup, and the readback checked only the
questions read: what such a control held was sent unapproved (`test_before_d160_...`).

Now a control the page gives the form by name is read with the form's own questions, refused as
D159 refuses `form` (a required one a checkpoint, an optional one left blank, and the readback
stops the attempt when it holds anything); and before anything is entered (and again after
filling) a control the form would send that the read does not show stops the attempt plainly.

Runs drive the API and the runner against the base stand-in (`cfg["sends"]`: "outside_*",
"custom_*"), with the receiver's ledger as the oracle; capture is read against Chromium's own
list of the form's controls for the same pages."""

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter
from app.modules.execution.adapters.form_entries import ENTRIES_JS, NAMES_JS
from app.modules.preparation import forms
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import SENT_OTHERWISE, FieldType, extract_form_schema
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_sent_as_approved import gh_page, pauses
from tests.test_workday_experience import (
    _browser,  # noqa: F401  (the module's browser, for `page`)
    page,  # noqa: F401
)

PAGE_TEXT = "Text the page wrote (fictional)"


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
    assert extra.type == FieldType.unsupported and extra.unsupported_reason == SENT_OTHERWISE
    assert extra.label == "Anything else?" and extra.required is False


@pytest.mark.parametrize("required", [True, False])
def test_a_control_given_from_outside_keeps_whether_the_page_requires_it(required):
    """D136's rule: a required one is a checkpoint, an optional one left blank."""
    html = FORM.format(inner="") + GIVEN.format(a=" required" if required else "")
    assert {f.key: f for f in extract_form_schema(html).fields}["extra"].required is required


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
}  # fmt: skip


@pytest.mark.parametrize("control", list(GIVEN_CONTROLS))
def test_every_kind_of_control_given_from_outside_is_refused(control):
    html = FORM.format(inner="") + GIVEN_CONTROLS[control]
    got = {f.key: f for f in extract_form_schema(html).fields}
    assert got["extra"].type == FieldType.unsupported
    assert got["extra"].unsupported_reason == SENT_OTHERWISE


NOT_GIVEN = {
    "no form attribute": '<label for="x">Search jobs</label><input id="x" name="extra">',
    "another form named": ('<form id="other"></form><label for="x">Search jobs</label>'
                           '<input id="x" name="extra" form="other">'),
    "a name no form has": ('<label for="x">Search jobs</label>'
                           '<input id="x" name="extra" form="nowhere">'),
    "the id first on another element": None,  # built below
    "inside a fieldset given": ('<fieldset form="application"><label for="x">Search jobs</label>'
                                '<input id="x" name="extra"></fieldset>'),
    "a hidden value": '<input type="hidden" name="extra" form="application" value="1">',
    "a button": '<button name="extra" form="application" value="1">Save</button>',
}  # fmt: skip


def not_given_page(case: str) -> str:
    if case == "the id first on another element":
        return ('<div id="application"></div>' + FORM.format(inner="") + '<label for="x">Search'
                ' jobs</label><input id="x" name="extra" form="application">')  # fmt: skip
    return FORM.format(inner="") + NOT_GIVEN[case]


@pytest.mark.parametrize("case", list(NOT_GIVEN))
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


# ---------------------------------------------------------------------------- what is sent


BEFORE_D160 = {  # mode: (field the stand-in received, what it held)
    "outside_text": ("extra", PAGE_TEXT),
    "outside_on_input": ("extra", PAGE_TEXT),
    "custom_control": ("note", PAGE_TEXT),
    "custom_entries": ("why_us", None),  # a second "Why us"
}


@pytest.mark.parametrize("mode", list(BEFORE_D160))
def test_before_d160_the_employer_received_what_the_page_wrote(api, receiver, monkeypatch, mode):
    """The oracle's side: as before D160 (a read of the form takes only the controls inside its
    markup, and nothing checks the rest), the application is confirmed and the stand-in
    received the page's own text with it."""
    monkeypatch.setattr(forms, "given_from_outside", lambda *a: False)
    monkeypatch.setattr(FixtureAtsAdapter, "_unread_controls", lambda *_: None)
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text="I like the clinic.")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    field, held = BEFORE_D160[mode]
    if held is None:
        assert row["fields"][field] == ["I like the clinic.", PAGE_TEXT]
    else:
        assert row["fields"][field] == held


def test_a_control_given_from_outside_holding_page_text_is_never_sent(api, receiver):
    """Read with the form's questions, refused and left blank: the page's text in it stops the
    attempt at the readback, before the send gate."""
    receiver.config(sends="outside_text")
    app_id = prepared_application(api, receiver)
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


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
    app_id = prepared_application(api, receiver, why_text="I like the clinic.")
    receiver.config(sends="outside_on_input")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize("mode", ["custom_control", "custom_entries"])
def test_a_custom_control_stops_the_attempt_before_anything_is_entered(api, receiver, mode):
    """A form-associated custom element of the page's own making: no read of the page shows it,
    so reading the form again would not either. A plain stop (no pause) with nothing entered,
    naming how many, never which."""
    receiver.config(sends=mode)
    app_id = prepared_application(api, receiver, why_text="I like the clinic.")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert pauses(app_id) == []
    detail = attempt(aid).outcome_detail
    assert fixture_ats.UNREAD_CONTROLS.format(n=1) in detail and "note" not in detail


# ------------------------------------------- in Chromium (last: the module's browser stays open)

CHROMIUM_PAGES = [
    FORM.format(inner="") + GIVEN.format(a=""),
    GIVEN.format(a=" required") + FORM.format(inner=""),
    *(FORM.format(inner="") + c for c in GIVEN_CONTROLS.values()),
    *(not_given_page(c) for c in NOT_GIVEN),
]  # fmt: skip


@pytest.mark.parametrize("html", CHROMIUM_PAGES)
def test_the_form_is_read_as_chromium_gives_it_its_controls(page, html):  # noqa: F811
    """Measured: the questions a read of the page takes are exactly the controls Chromium lists
    as the form's own (what it would send when filled), hidden values and buttons aside."""
    page.set_content(html)
    names = page.locator("form#application").evaluate(NAMES_JS, [])
    assert names["custom"] == 0
    assert sorted(names["names"]) == sorted(set(keys(html)))


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
    assert sorted(got["names"]) == ["box", "given", "off", "typed"] and got["custom"] == 2
    # Chromium's own entry list for the same page: the custom elements' entries are there, one
    # under the name its attribute gives, one under a name of its script's choosing
    real = page.evaluate("""() => [...new FormData(document.getElementById('app'))]""")
    assert ["note", "from the page"] in real and ["typed", "a second value"] in real


def test_a_custom_control_is_read_by_its_name_attribute(page):  # noqa: F811
    """D159's passive read named a form-associated custom element by a `name` property it does
    not have (unless its script defines one), so it read nothing of it; it is named by its
    attribute now, its value unknown (None)."""
    page.set_content(CONTROLS_PAGE)
    got = page.locator("#app").evaluate(ENTRIES_JS)
    assert got["note"] == [None]
