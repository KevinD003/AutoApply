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
focus.

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
    LIMIT_AT_FOCUS,
    FixtureAtsAdapter,
    LimitStopped,
)
from app.modules.preparation import forms
from app.modules.preparation.forms import TEXT_TYPES
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_outside_controls import ADAPTERS, stand_in_html
from tests.test_sent_as_approved import WHY, gh_prepared
from tests.test_workday_experience import (
    _browser,  # noqa: F401  (the module's browser, for `page`)
    page,  # noqa: F401
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
        '<form id="application"><textarea name="why" maxlength="3"></textarea></form><script>'
        "const w = document.querySelector('[name=why]');"
        "Object.defineProperty(w, 'maxLength', {get: () => -1});"
        "w.getAttribute = () => null;</script>"
    )
    adapter = FixtureAtsAdapter({"answers": [answer("why", "abcdef")], "documents": []}, {})
    over = adapter._limits_fit(page)
    assert isinstance(over, fixture_ats.FormChanged) and "3 characters" in str(over)
    assert FixtureAtsAdapter._cut_at_focus(page.locator("[name=why]"), "abcdef") == 3


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
    assert dom.LIMITED_INPUTS == forms.LIMITED_INPUTS == set(forms._DIRNAME_TYPES)
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
