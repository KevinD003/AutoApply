"""D153 (rank 19): the probe's record of changes to a list (`gh_readonly._PRE_JS`, D145) also
counts what can decide, without touching a list, which list the probe reads or which of its
options are shown (any attribute of the control; on an element holding it, an attribute the
probe finds its list by; the control moved; any id; a style sheet), and the adapter's
classification leaves out the whole page's 150 ms check (`classify_open(..., whole_page=False)`).

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
    state, _, partial = ro.classify_open(_probe(), post, [2, 2], 2, True, whole_page=False)
    assert (state, partial) == ("observed_sufficiently", [])
    # The reads still decide: a number of options that changed between the last two.
    got = ro.classify_open(_probe(), post, [1, 2], 2, True, whole_page=False)
    assert got[2] == ["still_changing"]


CTL = f"document.getElementById('{CID}')"
# Each counts as a change to a list: a style sheet can hide, show or reorder options, and the
# control (and what holds it) names the list the probe reads.
COUNTED = {
    "a style element added": "document.head.append(Object.assign("
    "document.createElement('style'), {textContent: '#fx-a { color: red; }'}))",
    "a style sheet's text changed": "document.getElementById('fx-sheet').textContent = "
    "'#fx-b { color: blue; }'",
    "a style sheet's text node edited": "document.getElementById('fx-sheet').firstChild.data = "
    "'#fx-e { color: blue; }'",
    "a style element removed": "document.getElementById('fx-sheet').remove()",
    "a stylesheet link's attribute changed": "document.getElementById('fx-link').media = 'print'",
    "a stylesheet link's rel set away": "document.getElementById('fx-link').rel = 'preload'",
    "a style element inside an added element": "document.body.append(Object.assign("
    "document.createElement('div'), {innerHTML: '<style>#fx-c { color: red; }</style>'}))",
    "the control's aria-controls": f"{CTL}.setAttribute('aria-controls', 'fx-note')",
    "a class on the control": f"{CTL}.classList.add('fx-alt')",
    "aria-owns on an element holding the control": f"{CTL}.parentElement.setAttribute("
    "'aria-owns', 'fx-note')",
    "the control moved into another element": f"const c = {CTL}; "
    "const w = document.createElement('span'); c.before(w); w.append(c)",
    "an id elsewhere": "document.getElementById('fx-note').id = 'fx-note-2'",
}
# None is one: the whole page's record sees them, the list's does not. The last is the record's
# limit (D153): a class elsewhere that a style sheet reads can still hide an option; the choice
# reads the list again (`test_dropdown_choice.py`).
ELSEWHERE = {
    "an element's text elsewhere": "document.getElementById('fx-note').textContent = 'changed'",
    "an inline style elsewhere": "document.getElementById('fx-note').style.color = 'red'",
    "an attribute of an element holding a style sheet": "document.getElementById('fx-holder')"
    ".dataset.x = '1'",
    "another attribute of an element holding the control": f"{CTL}.parentElement.dataset.x = '1'",
    "a class elsewhere, even one a style sheet reads": "document.getElementById('fx-note')"
    ".className = 'z'",
}


def _ids(cases: dict) -> list[str]:
    return [c.replace(" ", "_").replace("'", "") for c in cases]


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
      const has = Object.assign(document.createElement('style'), {textContent:
        'body:has(#fx-note.z) [role=listbox] > [role=option]:first-child { display: none; }'});
      document.head.append(s, l, has);
      document.body.append(Object.assign(document.createElement('p'),
                                         {id: 'fx-note', textContent: 'note'}),
                           Object.assign(document.createElement('div'), {id: 'fx-holder',
                             innerHTML: '<svg><style>#fx-g { fill: red; }</style></svg>'}));
    }""")
    assert page.evaluate(ro._PRE_JS, CID) is not None  # the record starts here
    before = page.evaluate(ro._PROBE_JS, CID)
    assert before["list_quiet_ms"] is None and before["quiet_ms"] is None  # nothing changed yet
    page.evaluate("() => { " + change + "; }")
    page.wait_for_timeout(100)
    after = page.evaluate(ro._PROBE_JS, CID)
    page.evaluate(ro._END_PROBE_JS)
    return after


@pytest.mark.parametrize("change", list(COUNTED), ids=_ids(COUNTED))
def test_a_change_to_a_style_sheet_is_a_change_to_a_list(receiver, change):
    with _session() as (page, _log):
        after = _record_after(page, COUNTED[change])
    assert after["list_quiet_ms"] is not None and after["list_quiet_ms"] < 500, after


@pytest.mark.parametrize("change", list(ELSEWHERE), ids=_ids(ELSEWHERE))
def test_a_change_elsewhere_is_not(receiver, change):
    with _session() as (page, _log):
        after = _record_after(page, ELSEWHERE[change])
    assert after["list_quiet_ms"] is None, after
    assert after["quiet_ms"] is not None and after["quiet_ms"] < 500, after  # the page's record
