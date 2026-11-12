"""D153 (rank 19): the probe's record of changes to a list (`gh_readonly._PRE_JS`, D145) also
counts changes to a style sheet, and the adapter's classification leaves out the whole page's
150 ms check (`classify_open(..., whole_page=False)`).

The observer runs in Chromium on the v2 stand-in's page (its markup is a FIXTURE ASSUMPTION, not
a real page's); the classification is tested on its own. The adapter's and the survey's use of
both are tested in `test_dropdown_strategies.py`, `test_section_list_settle.py` and
`test_survey_settle_rule.py`."""

import pytest

from app.core.config import get_settings
from app.modules.execution.browser import browser_session
from app.modules.preparation import gh_readonly as ro
from tests.execution_harness import BASE, Receiver

BOARD, JOB = "northwind", "5020001"
CID = "question_8101"  # a dropdown of the stand-in's page; any element with an id would do


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    receiver.config(mode="gh2_dd", dd="click_popup")


def _probe(**kw):
    base = {"expanded": "false", "wrapper_expanded": "absent", "associated_visible": 0,
            "new_popups": 0, "texts": [], "elsewhere": 0, "hint_popups": 0, "hint_options": 0,
            "setsize": None, "busy": 0, "hint_loading": 0, "quiet_ms": None,
            "added_visible": 0}  # fmt: skip
    return base | kw


def test_the_adapters_classification_leaves_out_the_whole_pages_check():
    post = _probe(expanded="true", texts=["a", "b"], quiet_ms=40)
    state, _, partial = ro.classify_open(_probe(), post, [2, 2], 2, True)
    assert (state, partial) == ("partially_observed", ["still_changing"])  # the survey's own
    state, _, partial = ro.classify_open(_probe(), post, [2, 2], 2, True, False)
    assert (state, partial) == ("observed_sufficiently", [])
    # The reads still decide: a number of options that changed between the last two.
    assert ro.classify_open(_probe(), post, [1, 2], 2, True, False)[2] == ["still_changing"]


# Each counts as a change to a list: a style sheet can hide, show or reorder options.
COUNTED = {
    "a style element added": "document.head.append(Object.assign("
    "document.createElement('style'), {textContent: '#fx-a { color: red; }'}))",
    "a style sheet's text changed": "document.getElementById('fx-sheet').textContent = "
    "'#fx-b { color: blue; }'",
    "a stylesheet link's attribute changed": "document.getElementById('fx-link').media = 'print'",
    "a style element inside an added element": "document.body.append(Object.assign("
    "document.createElement('div'), {innerHTML: '<style>#fx-c { color: red; }</style>'}))",
}
# Neither is one: the whole page's record sees them, the list's does not.
ELSEWHERE = {
    "an element's text elsewhere": "document.getElementById('fx-note').textContent = 'changed'",
    "an inline style elsewhere": "document.getElementById('fx-note').style.color = 'red'",
}


def _session():
    return browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                           allow_private_destination=True)  # fmt: skip


def _record_after(page, change: str) -> dict:
    page.goto(f"{BASE}/gh2/{BOARD}/jobs/{JOB}")
    page.locator(f"[id='{CID}']").wait_for(state="attached")
    page.evaluate("""() => {
      const s = Object.assign(document.createElement('style'),
                              {id: 'fx-sheet', textContent: '#fx-d { color: red; }'});
      const l = Object.assign(document.createElement('link'), {id: 'fx-link', rel: 'stylesheet',
                                                               media: 'all'});
      document.head.append(s, l);
      document.body.append(Object.assign(document.createElement('p'),
                                         {id: 'fx-note', textContent: 'note'}));
    }""")
    assert page.evaluate(ro._PRE_JS, CID) is not None  # the record starts here
    before = page.evaluate(ro._PROBE_JS, CID)
    assert before["list_quiet_ms"] is None and before["quiet_ms"] is None  # nothing changed yet
    page.evaluate("() => { " + change + "; }")
    page.wait_for_timeout(100)
    after = page.evaluate(ro._PROBE_JS, CID)
    page.evaluate(ro._END_PROBE_JS)
    return after


@pytest.mark.parametrize("change", list(COUNTED))
def test_a_change_to_a_style_sheet_is_a_change_to_a_list(receiver, change):
    with _session() as (page, _log):
        after = _record_after(page, COUNTED[change])
    assert after["list_quiet_ms"] is not None and after["list_quiet_ms"] < 500, after


@pytest.mark.parametrize("change", list(ELSEWHERE))
def test_a_change_elsewhere_is_not(receiver, change):
    with _session() as (page, _log):
        after = _record_after(page, ELSEWHERE[change])
    assert after["list_quiet_ms"] is None, after
    assert after["quiet_ms"] is not None and after["quiet_ms"] < 500, after  # the page's record
