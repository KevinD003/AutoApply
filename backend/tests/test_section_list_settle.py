"""D151: a section's combobox (Greenhouse education and employment, D120/D141) reads its list
through the dropdown's settle rule (adapters/dropdowns.py `_observe`: D104, D106, D108, D145)
instead of once on opening. Read every SAMPLE_MS, its list counts as settled once the probe's
classification says it is observed sufficiently (it opened, its options can be read, nothing new
on the page says it is loading, and no list claims more options than it shows; since D153 without
the whole document's 150 ms check), no data request made since the click is still in flight, the
same options were read three times in a row and the page has recorded no change to a list for
half a second (since D153 counting style sheets and the control's attributes); data requests are
refused as a dropdown's are. Otherwise the section stops, and no option
is clicked. The section stand-in's list behaviours (`section_widget` late_list, late_react,
late_fetch, late_fetch_404, changing_list, slow_changing_list, css_swapping_list, css_ticking,
open_beacon, hidden_duplicate, inert; cfg section_delay_ms, section_tick_ms) are FIXTURE
ASSUMPTIONS: no real
Greenhouse section page has been observed. The receiver's ledger is the oracle for what was sent.
Synthetic data only."""

import time

import pytest

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.execution.adapters import dropdowns
from app.modules.execution.adapters import greenhouse_sections as gsections
from app.modules.execution.browser import browser_session
from tests.execution_harness import BASE, Receiver, attempt, queue
from tests.test_greenhouse_dom import BOARD, JOB
from tests.test_section_widgets import application, sent


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


# The approved education record's controls (tests.test_section_widgets.EDU), as the stand-in
# posts them: the option ids chosen, and the months.
EDUCATION = {"school--0": "sch_state", "degree--0": "deg_bach", "discipline--0": "dis_cs",
             "start-month--0": "9", "end-month--0": "5"}  # fmt: skip
NETWORK = "its options load from the network in a way NoEfforts does not accept"


def education_sent(receiver) -> dict:
    got = sent(receiver)
    return {k: got.get(k) for k in EDUCATION}


def section_options_asked(receiver) -> int:
    return sum("/section-options/" in r["path"] for r in receiver.ledger()["requests"])


def run(api, receiver, widget: str, **cfg) -> tuple[str, str]:
    receiver.config(**cfg)
    aid = queue(api, application(api, receiver, widget=widget))
    return aid, runner.run_attempt(aid, "w1")


def refused(receiver, aid: str, result: str, reason: str) -> None:
    """The section stopped at the first control, saying why, naming the control and never the
    value, and nothing was submitted."""
    assert result == "abandoned"
    detail = attempt(aid).outcome_detail
    assert f"#school--0: {reason}" in detail, detail
    assert "State University" not in detail
    assert receiver.ledger()["accepted"] == 0


# ------------------------------------------------------------------- lists that settle late


@pytest.mark.parametrize("widget,delay_ms", [
    ("late_list", 300),  # says it is loading (aria-busy, a progressbar), then shows its options
    ("late_list", 2500),  # ... later than a real page's window, within a stand-in's
    ("late_react", 1500),  # an empty menu, a "Loading..." notice and a loading indicator only
    ("late_fetch", 1200),  # one placeholder option, not marked loading, until a GET answers
])  # fmt: skip
def test_a_section_list_that_arrives_late_is_chosen_from_once_it_has_settled(
    api, receiver, widget, delay_ms
):
    """Read once on opening, each of these lists was refused: no option, or only the placeholder,
    read the approved text (the run against the code before D151 is recorded in D151). The choice
    now waits for the list to settle, and is the approved option."""
    aid, result = run(api, receiver, widget, section_delay_ms=delay_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION
    if widget == "late_fetch":
        assert section_options_asked(receiver) == 5  # each list waited for its own answer


# ------------------------------------------------------------- lists that never settle


@pytest.mark.parametrize("widget,cfg", [
    ("changing_list", {}),  # re-rendered in the other order every 60 ms
    ("slow_changing_list", {}),  # ... every 300 ms
    ("css_swapping_list", {}),  # a style sheet hides another option every 300 ms: no list
    # changes, but since D153 the page's record counts the style sheet's
    ("late_list", {"section_delay_ms": 600_000}),  # still loading when the wait ends
])  # fmt: skip
def test_a_section_list_that_does_not_settle_stops_the_section(api, receiver, widget, cfg):
    aid, result = run(api, receiver, widget, **cfg)
    refused(receiver, aid, result, "its list did not settle in time")


# D145, for sections: how often the list is read must not decide whether it counts as settled.
# Read about every 600 ms, a list re-rendered every 300 ms shows the same order at every read.
@pytest.mark.parametrize("sample_ms", [590, 600, 610, 1200])
def test_a_section_list_that_keeps_changing_is_refused_however_slowly_it_is_read(
    api, receiver, monkeypatch, sample_ms
):
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", sample_ms)
    aid, result = run(api, receiver, "slow_changing_list")
    refused(receiver, aid, result, "its list did not settle in time")


@pytest.mark.parametrize("widget,cfg", [("plain", {}),
                                        ("late_fetch", {"section_delay_ms": 1200})])  # fmt: skip
def test_a_section_list_that_has_settled_is_chosen_from_when_read_slowly(
    api, receiver, monkeypatch, widget, cfg
):
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", 600)
    aid, result = run(api, receiver, widget, **cfg)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION


@pytest.mark.parametrize("tick_ms,window", [(300, "stand-in"), (600, "stand-in"),
                                            (600, "real page"), (300, "real page"),
                                            (100, "real page")])  # fmt: skip
def test_a_page_busy_elsewhere_does_not_hold_up_a_section_list(
    api, receiver, monkeypatch, tick_ms, window
):
    """As D145's dropdown tests: changes elsewhere on the page are not changes to a list, so each
    list still settles, in a stand-in's window and in a real page's (SETTLE_MS). D153: the
    classification's own check of the whole document (no change for 150 ms) is left out, as for
    the dropdown, so a page changing something every 300 or even 100 ms holds up no list."""
    if window == "real page":
        monkeypatch.setattr(dropdowns, "LATE_MS", dropdowns.SETTLE_MS)
    aid, result = run(api, receiver, "plain", section_tick_ms=tick_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION


def test_a_list_changed_only_by_a_style_sheet_is_refused_however_slowly_it_is_read(
    api, receiver, monkeypatch
):
    """D153: the style sheet hiding the 2nd, then the 3rd, option every 300 ms, read every 600 ms,
    in step with it: every read saw the same options, and until D153 nothing else looked at the
    style sheet but the whole document's 150 ms check, so the list could be read as settled
    (D151's stated limit). A change to a style sheet now counts as a change to a list."""
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", 600)
    aid, result = run(api, receiver, "css_swapping_list")
    refused(receiver, aid, result, "its list did not settle in time")


def test_a_list_held_back_only_by_the_pages_record_says_so(api, receiver):
    """D153: the list never changes, but a style sheet does, every 300 ms (its rule matches
    nothing): every read is the same, and only the page's record of changes to a list holds it
    back. The refusal names that, as a dropdown's does (`list_changed_recently`)."""
    aid, result = run(api, receiver, "css_ticking")
    refused(
        receiver,
        aid,
        result,
        "its list did not settle in time (observed_sufficiently: list_changed_recently)",
    )


# ------------------------------------------------- what the page sends, and what it hides


@pytest.mark.parametrize("widget,cfg", [
    ("open_beacon", {}),  # opening a list posts to the page's own server
    ("open_beacon", {"section_beacon_via": "sendbeacon"}),  # ... with navigator.sendBeacon
    ("late_fetch_404", {}),  # its options wait for a GET that is not answered with a 2xx
])  # fmt: skip
def test_a_section_list_whose_opening_sends_or_fails_to_load_is_refused(api, receiver, widget, cfg):
    """As a dropdown's (D104, D108): on a stand-in only a same-origin GET answered with a 2xx may
    bring a list's options; anything that sends, or fails, refuses the list."""
    aid, result = run(api, receiver, widget, **cfg)
    refused(receiver, aid, result, NETWORK)


def test_an_approved_option_the_list_does_not_show_is_never_clicked(api, receiver):
    aid, result = run(api, receiver, "hidden_approved")
    refused(receiver, aid, result, "the approved option is not shown")


def test_a_hidden_copy_of_the_approved_option_refuses_the_list(api, receiver):
    """Exactly one option of the list, shown or not, may read the approved text (as before D151:
    the list was counted whole)."""
    aid, result = run(api, receiver, "hidden_duplicate")
    refused(receiver, aid, result, "2 options read the approved text exactly")


# ------------------------------------------------------------------ on the page itself


def _school(page, late: bool) -> None:
    gsections._select_combobox(page, "#school--0", "State University", "sch_state", 3000, late)


def _open_section_page(page) -> None:
    page.goto(f"{BASE}/gh2/{BOARD}/jobs/{JOB}")
    page.locator("#school--0").wait_for(state="attached")


def _session():
    return browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                           allow_private_destination=True)  # fmt: skip


def _request_listeners(page) -> int:
    return len(page._impl_obj.listeners("request"))


def _nothing_chosen(page) -> None:
    assert gsections.combobox_shows(page, "#school--0", None, None)
    assert page.locator("#school--0-listbox [aria-selected=true]").count() == 0


def test_no_option_is_clicked_in_a_section_list_that_never_settles(receiver):
    """In a browser on the stand-in's page: the list is refused and closed, the control still
    shows nothing, no option in it was ever selected, and neither the probe's observer nor the
    request listeners are left behind."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="changing_list")
    with _session() as (page, _log):
        _open_section_page(page)
        listeners = _request_listeners(page)
        with pytest.raises(gsections.SectionFillError, match="did not settle in time"):
            _school(page, late=True)
        _nothing_chosen(page)
        assert page.locator("#school--0").get_attribute("aria-expanded") == "false"
        assert page.evaluate("() => window.__neObs") is None
        assert _request_listeners(page) == listeners


def test_a_real_pages_window_is_shorter_than_a_stand_ins(receiver):
    """The bound is the dropdown's: SETTLE_MS (1.5 s) on any page but a local stand-in, which
    may take LATE_MS (5 s). A list that says it is loading for 3.5 s is refused in the first
    window and chosen from in the second (sections run on stand-ins only today, D120)."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="late_list",
                    section_delay_ms=3500)  # fmt: skip
    with _session() as (page, _log):
        _open_section_page(page)
        with pytest.raises(gsections.SectionFillError, match="did not settle in time"):
            _school(page, late=False)
        _nothing_chosen(page)
        _open_section_page(page)  # a fresh page: its list loads afresh
        _school(page, late=True)
        assert gsections.combobox_shows(page, "#school--0", "State University", "sch_state")


def test_a_control_that_never_opens_stops_the_wait_after_a_real_pages_window(receiver):
    """As a dropdown's: when nothing opened and nothing is loading, the wait ends after SETTLE_MS
    of reads even on a stand-in, whose window is LATE_MS."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="inert")
    with _session() as (page, _log):
        _open_section_page(page)
        reads, wait = [], page.wait_for_timeout

        def counted(ms):
            reads.append(ms)
            return wait(ms)

        page.wait_for_timeout = counted
        with pytest.raises(gsections.SectionFillError, match="its list did not open"):
            _school(page, late=True)
        assert reads.count(dropdowns.SAMPLE_MS) == dropdowns.SETTLE_MS // dropdowns.SAMPLE_MS
        _nothing_chosen(page)


def test_a_control_that_leaves_the_page_while_its_list_is_read_stops_at_once(receiver):
    """The section stops at the next read, and closing the list takes the dropdown's action time
    (2 s), never the page's own wait (8 s here, the navigation timeout in the runner)."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="vanishing")
    with _session() as (page, _log):
        _open_section_page(page)
        started = time.monotonic()
        with pytest.raises(gsections.SectionFillError, match="is no longer on the page"):
            _school(page, late=True)
        assert time.monotonic() - started < 6


# Changed after it settled, just before the click: the list in the other order, the approved
# option re-keyed, or a second option reading the approved text added at the end.
CHANGED = {
    "reversed": "for (const o of Array.from(lb.children).reverse()) lb.appendChild(o);",
    "re-keyed": "lb.querySelector('[data-value=sch_state]').dataset.value = 'sch_other';",
    "copied": "lb.append(lb.querySelector('[data-value=sch_state]').cloneNode(true));",
}


@pytest.mark.parametrize("change", list(CHANGED))
def test_a_list_changed_after_it_settled_is_not_chosen_from(receiver, monkeypatch, change):
    """The whole list is read again just before the click and must be the one that settled, and
    the option at its place must still read the approved text and id: otherwise nothing is
    clicked."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="plain")
    real = gsections._settled_list

    def settled_then_changed(page, *a, **k):
        out = real(page, *a, **k)
        page.evaluate("() => { const lb = document.getElementById('school--0-listbox'); "
                      + CHANGED[change] + " }")  # fmt: skip
        return out

    monkeypatch.setattr(gsections, "_settled_list", settled_then_changed)
    with _session() as (page, _log):
        _open_section_page(page)
        with pytest.raises(gsections.SectionFillError, match="its list changed before the choice"):
            _school(page, late=True)
        _nothing_chosen(page)


def test_the_probe_is_set_for_the_choice_and_taken_off_after(receiver):
    receiver.config(mode="gh2_sections", sections="education", section_widget="plain")
    with _session() as (page, _log):
        _open_section_page(page)
        listeners = _request_listeners(page)
        _school(page, late=True)
        assert page.evaluate("() => !!window.__neMut")  # it recorded the page's changes
        assert page.evaluate("() => window.__neObs") is None  # and stopped
        assert _request_listeners(page) == listeners
