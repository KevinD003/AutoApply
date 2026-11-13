"""D162: every adapter stops filling at a value its box's limit would cut, naming the limit, and
reads that limit as the browser reads it.

D159 gave every adapter but the Greenhouse pilot a check right before each value is typed: once
its box has focus, the limit it has then. A value it would cut was not typed; filling went on with
the later answers (typed into a page that saves as you type), and the readback stopped the attempt
with "N field(s) did not keep their values": no number to shorten to, and no read of the form
records a limit the page sets only then. D161's reviews found the same in the pilot, which now
stops at once (D161); D162 gives every adapter that check (`FixtureAtsAdapter._cut_at_focus`,
`LimitStopped`), the live limit read through the browser's own definitions where it applies at
all (`forms.LIVE_LIMIT_JS`), and the Workday-style work entries the same read once the control has
focus. After its reviews: a box is typed into only once it has focus for certain (one the page
keeps disabled, hidden or inert, or whose focus it moves, is never typed into: `FocusStopped`); a
number or a date is checked as a text is; a work entry's stop names the limit, the pilot's entries
are checked too, and an entry refused before it was typed is not recorded as entered; every stop
at a box carries the uploads made before it.

The receiver's own ledger is the oracle (its acceptances and what the page saved as you typed),
or Chromium itself. Passing here shows fixture compatibility only, never how a real employer's
page behaves. Synthetic candidate data only."""

import json
import re

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters import greenhouse_sections as gs
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.fixture_ats import (
    FOCUS_LOST,
    LIMIT_AT_FOCUS,
    SECTION_LIMIT_AT_FOCUS,
    FixtureAtsAdapter,
    FocusStopped,
    LimitStopped,
    section_not_typed,
)
from app.modules.preparation import forms
from app.modules.preparation.forms import TEXT_TYPES, UNKNOWN_TRIGGER
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_outside_controls import ADAPTERS, stand_in_html
from tests.test_sent_as_approved import WHY, gh_prepared
from tests.test_workday_experience import (
    _browser,  # noqa: F401  (the module's browser, for `page`)
    draft_pages,
    experience_application,
    page,  # noqa: F401
    rows,
)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def saved(led: dict, field: str) -> list[dict]:
    """What the page saved of a question as it was entered (its name, or its length only)."""
    rows = [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "autosave"]
    return [d for d in rows if d["field"] == field]


def without_d162(monkeypatch):
    """D159's behaviour, for the oracles: a value its box would cut is not typed, and filling goes
    on with the later answers (the readback then stops the attempt)."""
    fill_one = FixtureAtsAdapter._fill_one

    def d159(self, pg, a):
        try:
            return fill_one(self, pg, a)
        except LimitStopped:
            return None

    monkeypatch.setattr(FixtureAtsAdapter, "_fill_one", d159)


# ---------------------------------------------------------------------------- the base stand-in


@pytest.mark.parametrize("mode", ["limit_on_focus", "limit_on_input"])
def test_a_value_its_box_would_cut_stops_filling_there_naming_the_limit(api, receiver, mode):
    """The page lowers "Why us" to 500 as it gets focus (or once the first name is typed), after
    the form was checked, and saves what is typed: "Why us" is never typed, filling stops there,
    naming the limit, and the privacy acknowledgement after it is never entered."""
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode, autosave=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0
    assert saved(led, "why_us") == [] and saved(led, "privacy_ack") == []
    assert saved(led, "first_name") != []  # the answers before it were entered
    assert LIMIT_AT_FOCUS.format(limits=500) in attempt(aid).outcome_detail


@pytest.mark.parametrize("mode", ["limit_on_focus", "limit_on_input"])
def test_before_d162_filling_went_on_past_a_withheld_value_naming_no_limit(
    api, receiver, monkeypatch, mode
):
    """The oracle: with D159's check alone, the privacy acknowledgement after "Why us" was entered
    (and saved by the page) for an attempt certain to stop, and the stop named no limit."""
    without_d162(monkeypatch)
    app_id = prepared_application(api, receiver, why_text=WHY)
    receiver.config(sends=mode, autosave=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert led["accepted"] == 0 and saved(led, "why_us") == []
    assert saved(led, "privacy_ack") != []
    assert "500" not in attempt(aid).outcome_detail


# ---------------------------------------------------------------------------- Greenhouse classic


def test_greenhouse_classic_stops_at_a_value_its_box_would_cut_naming_the_limit(api, receiver):
    """D162: its page lowers "Why are you interested" to 20 as it gets focus: never typed, and
    the stop names the limit."""
    app_id, _ = gh_prepared(api)
    receiver.config(sends="gh_limit_on_focus")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert LIMIT_AT_FOCUS.format(limits=20) in attempt(aid).outcome_detail


def test_before_d162_greenhouse_classic_s_stop_named_no_limit(api, receiver, monkeypatch):
    without_d162(monkeypatch)
    app_id, _ = gh_prepared(api)
    receiver.config(sends="gh_limit_on_focus")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0
    assert "20 characters" not in attempt(aid).outcome_detail


# ------------------------------------------------------------------------- Workday-style runner
# (before any test of this module that opens a browser of its own: the runner starts its own)


def test_a_work_entry_its_box_would_cut_stops_naming_the_limit_and_records_nothing(api, receiver):
    """D162 reviews: a work entry's Job Title box lowers its limit to 5 as it gets focus. The
    stop said the entry "did not appear or did not keep its value", naming no limit, and the
    title was recorded as entered though nothing was typed. Now it names the limit, and nothing
    of the entry is recorded; the wizard's page with the entries is never sent."""
    app_id = experience_application(api, receiver)
    receiver.config(wd_limit_on_focus={'input[name$="].title"]': 5})
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert SECTION_LIMIT_AT_FOCUS.format(limits=5) in attempt(aid).outcome_detail
    assert [d for d in rows(aid, "disclosure") if d.get("kind") == "section_field"] == []
    led = receiver.ledger()
    assert led["accepted"] == 0 and draft_pages(led) == [1]


def test_a_wizard_page_s_answer_its_box_would_cut_stops_before_the_page_is_sent(api, receiver):
    """D162: on the Workday-style wizard, the first page's first name lowers its limit to 2 as it
    gets focus: never typed, the stop names the limit, and no page is sent."""
    app_id = experience_application(api, receiver)
    receiver.config(wd_limit_on_focus={'[name="legalName--firstName"]': 2})
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert LIMIT_AT_FOCUS.format(limits=2) in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and draft_pages(led) == []


# ---------------------------------------------------------------------------- each adapter


def typed_pair(pg, adapter) -> tuple[str, str]:
    """The first two typed questions the page shows (its own stand-in's), in page order."""
    keys = [f.key for f in adapter.extract(pg).fields if f.type in TEXT_TYPES]
    shown = [k for k in keys if pg.locator(f'[name="{k}"]').first.is_visible()]
    assert len(shown) >= 2, shown
    return shown[0], shown[1]


def answer(key: str, text: str) -> dict:
    return {"key": key, "type": "text", "status": "resolved", "required": False,
            "value": {"text": text}}  # fmt: skip


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_each_adapter_stops_filling_at_a_value_its_box_would_cut(page, receiver, name):  # noqa: F811
    """On its own stand-in's page, the first typed question's box lowers its limit to 3 as it
    gets focus: the value is never typed, the stop names the limit, and the question after it is
    never entered (each adapter's own filling: the base's, Greenhouse classic's, the hosted
    ones', the Workday-style one's)."""
    cls, module, _ = ADAPTERS[name]
    page.set_content(stand_in_html(receiver, module))
    first, second = typed_pair(page, cls({"answers": [], "documents": []}, {}))
    page.locator(f'[name="{first}"]').evaluate(
        "(e) => e.addEventListener('focus', () => { e.maxLength = 3; })"
    )
    adapter = cls({"answers": [answer(first, "abcdef"), answer(second, "xyz")], "documents": []},
                  {})  # fmt: skip
    with pytest.raises(LimitStopped, match=re.escape(LIMIT_AT_FOCUS.format(limits=3))):
        adapter.fill(page)
    assert page.locator(f'[name="{first}"]').input_value() == ""
    assert page.locator(f'[name="{second}"]').input_value() == ""


SENT = {"kind": "upload", "field": "resume", "ack": "attachment_shown"}  # an upload's evidence
RESUME = {"key": "resume", "type": "file", "status": "resolved", "required": False,
          "value": {"document": "resume"}}  # fmt: skip


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_each_adapter_s_stop_at_a_box_hands_back_the_uploads_made_before_it(
    page,  # noqa: F811
    receiver,
    name,
    monkeypatch,
):
    """D162 review: a stop carries every disclosure the attempt made (`StoppedAfterDisclosure`),
    as an upload's own stop does; the stop at a box carried none. The runner records each one as
    it is made (D137), so it lost nothing; a caller without that record lost the uploads."""
    cls, module, _ = ADAPTERS[name]
    page.set_content(stand_in_html(receiver, module))
    first, _ = typed_pair(page, cls({"answers": [], "documents": []}, {}))
    page.locator(f'[name="{first}"]').evaluate(
        "(e) => e.addEventListener('focus', () => { e.maxLength = 3; })"
    )
    monkeypatch.setattr(cls, "_upload", lambda self, key, attach: dict(SENT))
    adapter = cls({"answers": [RESUME, answer(first, "abcdef")], "documents": []}, {})
    with pytest.raises(LimitStopped) as e:
        adapter.fill(page)
    assert e.value.disclosures == [SENT]


def shown_by_the_page(a: dict) -> dict:
    """The answer to a question the page shows by its own logic (D135, D148): entered last."""
    return {**a, "condition": {"key": UNKNOWN_TRIGGER, "values": []}}


def test_a_workday_style_question_the_page_shows_hands_back_the_uploads_before_its_stop(
    page,  # noqa: F811
    receiver,
    monkeypatch,
):
    cls, module, _ = ADAPTERS["Workday-style"]
    page.set_content(stand_in_html(receiver, module))
    first, _ = typed_pair(page, cls({"answers": [], "documents": []}, {}))
    page.locator(f'[name="{first}"]').evaluate(
        "(e) => e.addEventListener('focus', () => { e.maxLength = 3; })"
    )
    monkeypatch.setattr(cls, "_upload", lambda self, key, attach: dict(SENT))
    adapter = cls({"answers": [RESUME, shown_by_the_page(answer(first, "abcdef"))],
                   "documents": []}, {})  # fmt: skip
    with pytest.raises(LimitStopped) as e:
        adapter.fill(page)
    assert e.value.disclosures == [SENT]
    assert page.locator(f'[name="{first}"]').input_value() == ""


@pytest.mark.parametrize("where", ["in turn", "shown by the page"])
@pytest.mark.parametrize("how", ["its limit", "no focus"])
def test_the_pilot_s_stop_at_a_box_hands_back_the_uploads_made_before_it(
    page,  # noqa: F811
    how,
    where,
    monkeypatch,
):
    """The pilot's stop at its limit carried the uploads (D161); its stop at a box that never got
    focus (D162 review) did not, until both went one way: for an answer entered in turn, and for
    one the page shows by its own logic (entered last)."""
    from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter

    js = "w.inert = true;" if how == "no focus" else (
        "w.addEventListener('focus', () => { w.maxLength = 3; });")  # fmt: skip
    page.set_content('<form id="application_form"><textarea id="why"></textarea></form><script>'
                     "const w = document.getElementById('why');" + js + "</script>")  # fmt: skip
    monkeypatch.setattr(GreenhouseDomAdapter, "_upload", lambda self, key, attach: dict(SENT))
    why = answer("why", "abcdef")
    why = why if where == "in turn" else shown_by_the_page(why)
    adapter = GreenhouseDomAdapter({"answers": [RESUME, why], "documents": []}, {})
    page.set_default_timeout(1500)
    try:
        with pytest.raises(FocusStopped if how == "no focus" else LimitStopped) as e:
            adapter.fill(page)
    finally:
        page.set_default_timeout(30_000)
    assert e.value.disclosures == [SENT]
    assert page.locator("#why").input_value() == ""


def test_a_value_that_fits_once_its_box_has_focus_is_typed(page):  # noqa: F811
    page.set_content('<form id="application"><textarea name="why"></textarea>'
                     '<input name="city"></form><script>document.querySelector("[name=why]")'
                     '.addEventListener("focus", (e) => { e.target.maxLength = 3; });'
                     "</script>")  # fmt: skip
    adapter = FixtureAtsAdapter({"answers": [answer("why", "abc"), answer("city", "Elm")],
                                 "documents": []}, {})  # fmt: skip
    assert adapter.fill(page) == []
    assert page.locator("[name=why]").input_value() == "abc"
    assert page.locator("[name=city]").input_value() == "Elm"


# ---------------------------------------------------------------------------- reading the limit


def test_the_live_limit_is_read_through_the_browser_s_own_definitions(page):  # noqa: F811
    """A page that redefines `maxLength`, `getAttribute` or `type` on the box itself changes
    nothing the checks read: before anything is entered (`_limits_fit`) and before typing."""
    page.set_content(
        '<form id="application"><textarea name="why" maxlength="3"></textarea>'
        '<input name="city" maxlength="3"></form><script>'
        "const w = document.querySelector('[name=why]');"
        "Object.defineProperty(w, 'maxLength', {get: () => -1});"
        "Object.defineProperty(w, 'localName', {get: () => 'div'});"
        "w.getAttribute = () => null;"
        "Object.defineProperty(document.querySelector('[name=city]'), 'type',"
        " {get: () => 'number'});</script>"
    )
    adapter = FixtureAtsAdapter({"answers": [answer("why", "abcdef")], "documents": []}, {})
    over = adapter._limits_fit(page)
    assert isinstance(over, fixture_ats.FormChanged) and "3 characters" in str(over)
    assert FixtureAtsAdapter._cut_at_focus(page.locator("[name=why]"), "abcdef") == 3
    assert FixtureAtsAdapter._cut_at_focus(page.locator("[name=city]"), "abcdef") == 3


def test_a_box_whose_type_the_browser_holds_to_no_limit_is_not_held_to_one(page):  # noqa: F811
    """The page made the box a number box after the form was read: the browser holds nothing
    typed into it to its `maxlength`, so neither check does (it would stop a page that is
    fine); what it then holds is the readback's."""
    page.set_content('<form id="application"><input name="why" type="number" maxlength="3">'
                     "</form>")  # fmt: skip
    adapter = FixtureAtsAdapter({"answers": [answer("why", "123456")], "documents": []}, {})
    assert adapter._limits_fit(page) is None
    assert FixtureAtsAdapter._cut_at_focus(page.locator("[name=why]"), "123456") is None


def test_every_adapter_and_the_survey_read_the_limit_one_way():
    """D162: one read of the live limit, the browser's, for the pilot, the read-only survey and
    every other adapter; its types are the capture's."""
    from app.modules.preparation import greenhouse_dom as dom

    assert dom.LIVE_LIMIT_JS is forms.LIVE_LIMIT_JS
    assert dom.LIMITED_INPUTS is forms.LIMITED_INPUTS  # measured in Chromium by D161's tests
    for t in forms.LIMITED_INPUTS:
        assert f"'{t}'" in forms.LIVE_LIMIT_JS


# ---------------------------------------------------------------------------- Workday-style entries


def entry_op(selector: str, value: str) -> gs.FillOp:
    return gs.FillOp(row=0, field="title", kind="text", selector=selector, value=value,
                     readback=value)  # fmt: skip


def test_a_work_entry_s_limit_is_read_once_its_box_has_focus_and_named(page):  # noqa: F811
    """D157 read an entry's limit before giving its box focus: a page that lowers it then cut the
    value as it was typed. D162: read once the box has focus, and the stop names the limit."""
    page.set_content('<input id="t"><script>document.getElementById("t").addEventListener('
                     '"focus", (e) => { e.target.maxLength = 3; });</script>')  # fmt: skip
    with pytest.raises(gs.SectionFillError, match=re.escape("(3 characters as the form sends")):
        ws._give(page, entry_op("#t", "abcdef"), 5000)
    assert page.locator("#t").input_value() == ""


def test_a_work_entry_s_limit_is_read_as_the_browser_reads_it(page):  # noqa: F811
    page.set_content('<input id="t" maxlength="3"><input id="n" type="number" maxlength="3">'
                     "<script>Object.defineProperty(document.getElementById('t'), 'maxLength',"
                     " {get: () => -1});</script>")  # fmt: skip
    with pytest.raises(gs.SectionFillError, match="title is longer than the page now accepts"):
        ws._give(page, entry_op("#t", "abcdef"), 5000)
    ws._give(page, entry_op("#n", "123456"), 5000)  # a number box: no limit the browser applies
    assert page.locator("#n").input_value() == "123456"


# ---------------------------------------------------------------------------- focus, for certain

FIRST_THEN_WHY = (
    '<form id="application"><input name="first"><textarea name="why"></textarea></form>'
)


def first_then_why(why: str) -> FixtureAtsAdapter:
    return FixtureAtsAdapter({"answers": [answer("first", "Sam"), answer("why", why)],
                              "documents": []}, {})  # fmt: skip


def once_first_is_typed(js: str) -> str:
    return ("<script>const w = document.querySelector('[name=why]');"
            "document.querySelector('[name=first]').addEventListener('input', () => {"
            + js + "}, {once: true});</script>")  # fmt: skip


LOCKS = {
    "disabled": "w.disabled = true; setTimeout(() => { w.disabled = false; }, 400);",
    "hidden": "w.hidden = true; setTimeout(() => { w.hidden = false; }, 400);",
}


@pytest.mark.parametrize("lock", list(LOCKS))
def test_a_box_locked_for_a_moment_is_read_once_it_has_focus(page, lock):  # noqa: F811
    """D162 review: the page locks "Why us" for a moment once the first answer is typed (say
    until an upload ends), and lowers its limit as it gets focus. `focus()` did nothing then, the
    limit was read without focus, and `fill` focused it and typed it cut. Now the check waits for
    focus, as filling waits for a box, and reads the limit then: never typed cut."""
    page.set_content(FIRST_THEN_WHY + once_first_is_typed(
        LOCKS[lock] + " w.addEventListener('focus', () => { w.maxLength = 3; });"))  # fmt: skip
    with pytest.raises(LimitStopped, match=re.escape(LIMIT_AT_FOCUS.format(limits=3))):
        first_then_why("abcdef").fill(page)
    assert page.locator("[name=why]").input_value() == ""


@pytest.mark.parametrize("lock", list(LOCKS))
def test_a_box_locked_for_a_moment_is_typed_once_it_has_focus(page, lock):  # noqa: F811
    page.set_content(FIRST_THEN_WHY + once_first_is_typed(LOCKS[lock]))
    assert first_then_why("abc").fill(page) == []
    assert page.locator("[name=why]").input_value() == "abc"


TAKES_FOCUS = {
    "inert": "w.inert = true;",  # never focusable
    "moved at once": (  # the page moves focus back as soon as the box gets it
        "w.addEventListener('focus', () => queueMicrotask(() =>"
        " document.querySelector('[name=first]').focus()));"
    ),
    "a dialog's": (  # the page opens a dialog and keeps focus in it
        "const d = document.createElement('dialog'); d.innerHTML = '<input id=promo>';"
        " document.body.append(d); d.show();"
        " document.addEventListener('focusin', (e) => {"
        " if (!d.contains(e.target)) document.getElementById('promo').focus(); });"
    ),
}


@pytest.mark.parametrize("how", list(TAKES_FOCUS))
def test_a_box_that_never_gets_focus_is_never_typed_into(page, how):  # noqa: F811
    """D162 review: "Why us" never keeps focus once the first answer is typed (made inert, focus
    moved back as soon as it gets it, or kept in a dialog the page opened). Before, `fill` typed
    the value into whichever box had focus: the first answer's ("Samabc"), or the dialog's own
    box. Now filling stops there, nothing typed."""
    page.set_content(FIRST_THEN_WHY + once_first_is_typed(TAKES_FOCUS[how]))
    page.set_default_timeout(1500)
    try:
        with pytest.raises(FocusStopped, match=re.escape(FOCUS_LOST)):
            first_then_why("abc").fill(page)
    finally:
        page.set_default_timeout(30_000)
    assert page.locator("[name=first]").input_value() == "Sam"
    assert page.locator("[name=why]").input_value() == ""
    if how == "a dialog's":
        assert page.locator("#promo").input_value() == ""


def test_a_number_is_typed_only_into_a_box_that_holds_it_whole(page):  # noqa: F811
    """D162 review: a number answer went in unchecked; a page that makes its box a text box with
    a limit as it gets focus cut it, and filling went on. A real number box holds nothing typed to
    its `maxlength`: no limit, typed whole."""
    page.set_content('<form id="application"><input name="years" type="number" maxlength="3">'
                     '<input name="age" type="number"><input name="city"></form><script>'
                     "const a = document.querySelector('[name=age]');"
                     "a.addEventListener('focus', () => { a.type = 'text'; a.maxLength = 3; });"
                     "</script>")  # fmt: skip
    number = {"type": "number", "status": "resolved", "required": False}
    adapter = FixtureAtsAdapter({"answers": [
        {**number, "key": "years", "value": {"number": 123456}},
        {**number, "key": "age", "value": {"number": 123456}},
        answer("city", "Elm")], "documents": []}, {})  # fmt: skip
    with pytest.raises(LimitStopped, match=re.escape(LIMIT_AT_FOCUS.format(limits=3))):
        adapter.fill(page)
    assert page.locator("[name=years]").input_value() == "123456"
    assert page.locator("[name=age]").input_value() == ""
    assert page.locator("[name=city]").input_value() == ""


def test_a_date_is_typed_only_into_a_box_that_holds_it_whole(page):  # noqa: F811
    """The same for a date (D162 review): a real date box holds nothing to its `maxlength`; one
    the page makes a text box with a limit as it gets focus is never filled with it cut."""
    page.set_content('<form id="application"><input name="since" type="date" maxlength="3">'
                     '<input name="start" type="date"><input name="city"></form><script>'
                     "const s = document.querySelector('[name=start]');"
                     "s.addEventListener('focus', () => { s.type = 'text'; s.maxLength = 3; });"
                     "</script>")  # fmt: skip
    date = {"type": "date", "status": "resolved", "required": False}
    adapter = FixtureAtsAdapter({"answers": [
        {**date, "key": "since", "value": {"date": "2026-01-31"}},
        {**date, "key": "start", "value": {"date": "2026-01-31"}},
        answer("city", "Elm")], "documents": []}, {})  # fmt: skip
    with pytest.raises(LimitStopped, match=re.escape(LIMIT_AT_FOCUS.format(limits=3))):
        adapter.fill(page)
    assert page.locator("[name=since]").input_value() == "2026-01-31"
    assert page.locator("[name=start]").input_value() == ""
    assert page.locator("[name=city]").input_value() == ""


# ---------------------------------------------------------------------------- section entries


def test_a_section_entry_s_box_is_checked_once_it_has_focus(page):  # noqa: F811
    """D162 reviews: the pilot's education and employment entries typed with no check at all: a
    box that lowers its limit as it gets focus held the title cut, and the page saved it."""
    page.set_content('<input id="t"><script>document.getElementById("t").addEventListener('
                     '"focus", (e) => { e.target.maxLength = 5; });</script>')  # fmt: skip
    with pytest.raises(gs.NotTyped) as e:
        gs._fill_text(page, "#t", "Example Title", "Example Title", 5000)
    assert e.value.limit == 5 and page.locator("#t").input_value() == ""


def test_a_refused_entry_is_never_recorded_as_entered_and_a_failed_one_is(page):  # noqa: F811
    """D162 reviews: a control refused before anything was typed is not recorded (nothing of it
    reached the page); one that failed after it was typed is (the page may hold it, D137)."""
    page.set_content('<div id="s"><input id="a"><input id="b"></div><script>'
                     "document.getElementById('b').addEventListener('input', (e) => {"
                     " e.target.value = 'something else'; });</script>")  # fmt: skip

    def plan(*fields):
        ops = tuple(gs.FillOp(row=0, field=f, kind="text", selector=f"#{f}", value=v,
                              readback=v) for f, v in fields)  # fmt: skip
        return gs.SectionPlan(kind="employment", rows=(gs.RowPlan(
            row=0, record_id="r", anchor="#a", add_another_first=False, ops=ops),))  # fmt: skip

    page.locator("#a").evaluate("(e) => e.addEventListener('focus', () => { e.maxLength = 3; })")
    with pytest.raises(gs.NotTyped) as e:
        gs.apply_section_plan(page, plan(("a", "abcdef")), "#s")
    assert e.value.entered == []
    with pytest.raises(gs.SectionFillError) as e:
        gs.apply_section_plan(page, plan(("a", "abc"), ("b", "xyz")), "#s")
    assert e.value.entered == [{"row": 0, "field": "a"}, {"row": 0, "field": "b"}]


@pytest.mark.parametrize("how", ["its limit", "no focus"])
def test_the_pilot_s_entry_its_box_refuses_is_the_stop_that_names_it(page, how):  # noqa: F811
    """D162 reviews: the pilot's (and the live adapter's) education and employment entries are
    checked once their box has focus, as the Workday-style entries are: the stop names the limit
    (or the focus), not "does not read back the approved value", and carries what was disclosed
    before it."""
    from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter

    js = "w.inert = true;" if how == "no focus" else (
        "w.addEventListener('focus', () => { w.maxLength = 3; });")  # fmt: skip
    page.set_content('<div id="employment-section"><input id="company-name-0"></div>'
                     "<script>const w = document.getElementById('company-name-0');"
                     + js + "</script>")  # fmt: skip
    company = {"status": "resolved", "value": {"text": "Example Clinic"},
               "display": "Example Clinic"}  # fmt: skip
    sec = {"kind": "employment", "root": "#employment-section",
           "rows": [{"record_id": "r1", "fields": {"company_name": company}}]}  # fmt: skip
    adapter = GreenhouseDomAdapter({"answers": [], "documents": [], "sections": [sec]}, {})
    with pytest.raises(FocusStopped if how == "no focus" else LimitStopped) as e:
        adapter._fill_sections(page, [dict(SENT)])
    named = FOCUS_LOST if how == "no focus" else SECTION_LIMIT_AT_FOCUS.format(limits=3)
    assert str(e.value) == named and e.value.disclosures == [SENT]
    assert page.locator("#company-name-0").input_value() == ""


def test_a_section_s_refusal_before_typing_is_the_stop_that_names_it():
    stop = section_not_typed(gs.NotTyped("x", 5), [{"kind": "upload"}])
    assert isinstance(stop, LimitStopped) and stop.disclosures == [{"kind": "upload"}]
    assert str(stop) == SECTION_LIMIT_AT_FOCUS.format(limits=5)
    stop = section_not_typed(gs.NotTyped("x"), [])
    assert isinstance(stop, FocusStopped) and str(stop) == FOCUS_LOST
