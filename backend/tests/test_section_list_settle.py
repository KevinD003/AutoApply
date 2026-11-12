"""D151: a section's combobox (Greenhouse education and employment, D120/D141) reads its list
through the dropdown's settle rule (adapters/dropdowns.py, D106 and D145) instead of once on
opening. Its list counts as settled once it is shown and says it is not loading, no data request
made since the click is still in flight, the same options were read three times in a row and the
page has recorded no change to a list for half a second; otherwise the section stops, and no
option is clicked. The section stand-in's list behaviours (`section_widget` late_list, late_fetch,
changing_list, slow_changing_list; cfg section_delay_ms, section_tick_ms) are FIXTURE ASSUMPTIONS:
no real Greenhouse section page has been observed. The receiver's ledger is the oracle for what
was sent. Synthetic data only."""

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


def education_sent(receiver) -> dict:
    got = sent(receiver)
    return {k: got.get(k) for k in EDUCATION}


def section_options_asked(receiver) -> int:
    return sum("/section-options/" in r["path"] for r in receiver.ledger()["requests"])


def run(api, receiver, widget: str, **cfg) -> tuple[str, str]:
    receiver.config(**cfg)
    aid = queue(api, application(api, receiver, widget=widget))
    return aid, runner.run_attempt(aid, "w1")


# ------------------------------------------------------------------- lists that settle late


@pytest.mark.parametrize("widget,delay_ms", [
    ("late_list", 300),  # says it is loading, then shows its options
    ("late_list", 2500),  # ... later than a real page's window, within a stand-in's
    ("late_fetch", 1200),  # one placeholder option, not marked loading, until a GET answers
])  # fmt: skip
def test_a_section_list_that_arrives_late_is_chosen_from_once_it_has_settled(
    api, receiver, widget, delay_ms
):
    """Read once on opening, each of these lists was refused (no option, or only the placeholder,
    read the approved text): the choice now waits for the list to settle, and is the approved
    option."""
    aid, result = run(api, receiver, widget, section_delay_ms=delay_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION
    if widget == "late_fetch":
        assert section_options_asked(receiver) == 5  # each list waited for its own answer


# ------------------------------------------------------------- lists that never settle


@pytest.mark.parametrize("widget,cfg", [
    ("changing_list", {}),  # re-rendered in the other order every 60 ms
    ("slow_changing_list", {}),  # ... every 300 ms: the page's own record of it refuses it
    ("late_list", {"section_delay_ms": 7000}),  # still loading when the wait ends (LATE_MS)
])  # fmt: skip
def test_a_section_list_that_does_not_settle_stops_the_section(api, receiver, widget, cfg):
    aid, result = run(api, receiver, widget, **cfg)
    assert result == "abandoned"
    detail = attempt(aid).outcome_detail
    assert "#school--0: its list did not settle in time" in detail, detail
    assert "State University" not in detail  # the control is named, never the value
    assert receiver.ledger()["accepted"] == 0


# D145, for sections: how often the list is read must not decide whether it counts as settled.
# Read about every 600 ms, a list re-rendered every 300 ms shows the same order at every read.
@pytest.mark.parametrize("sample_ms", [590, 600, 610, 1200])
def test_a_section_list_that_keeps_changing_is_refused_however_slowly_it_is_read(
    api, receiver, monkeypatch, sample_ms
):
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", sample_ms)
    aid, result = run(api, receiver, "slow_changing_list")
    assert result == "abandoned"
    assert "#school--0: its list did not settle in time" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize("widget,cfg", [("plain", {}),
                                        ("late_fetch", {"section_delay_ms": 1200})])  # fmt: skip
def test_a_section_list_that_has_settled_is_chosen_from_when_read_slowly(
    api, receiver, monkeypatch, widget, cfg
):
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", 600)
    aid, result = run(api, receiver, widget, **cfg)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION


@pytest.mark.parametrize("tick_ms", [100, 300])
def test_a_page_busy_elsewhere_does_not_hold_up_a_section_list(
    api, receiver, monkeypatch, tick_ms
):
    """Only changes to a list count (D145's record), not changes elsewhere on the page: with
    something else changing every 100 or 300 ms, each list still settles, in a real page's
    window (SETTLE_MS) rather than a stand-in's."""
    monkeypatch.setattr(dropdowns, "LATE_MS", dropdowns.SETTLE_MS)
    aid, result = run(api, receiver, "plain", section_tick_ms=tick_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert education_sent(receiver) == EDUCATION


# ------------------------------------------------------------------ on the page itself


def _school(page, late: bool) -> None:
    gsections._select_combobox(page, "#school--0", "State University", "sch_state", 3000, late)


def _open_section_page(page) -> None:
    page.goto(f"{BASE}/gh2/{BOARD}/jobs/{JOB}")
    page.locator("#school--0").wait_for(state="attached")


def test_no_option_is_clicked_in_a_section_list_that_never_settles(receiver):
    """In a browser on the stand-in's page: the list is refused and closed, the control still
    shows nothing, and no option in it was ever selected."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="changing_list")
    with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                         allow_private_destination=True) as (page, _log):  # fmt: skip
        _open_section_page(page)
        with pytest.raises(gsections.SectionFillError, match="did not settle in time"):
            _school(page, late=True)
        assert gsections.combobox_shows(page, "#school--0", None, None)
        assert page.locator("#school--0-listbox [aria-selected=true]").count() == 0
        assert page.locator("#school--0").get_attribute("aria-expanded") == "false"


def test_a_real_pages_window_is_shorter_than_a_stand_ins(receiver):
    """The bound is the dropdown's: SETTLE_MS (1.5 s) on any page but a local stand-in, which
    may take LATE_MS (5 s). A list that says it is loading for 2.5 s is refused in the first
    window and chosen from in the second (sections run on stand-ins only today, D120)."""
    receiver.config(mode="gh2_sections", sections="education", section_widget="late_list",
                    section_delay_ms=2500)  # fmt: skip
    with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                         allow_private_destination=True) as (page, _log):  # fmt: skip
        _open_section_page(page)
        with pytest.raises(gsections.SectionFillError, match="did not settle in time"):
            _school(page, late=False)
        assert gsections.combobox_shows(page, "#school--0", None, None)
        _open_section_page(page)  # a fresh page: its list loads afresh
        _school(page, late=True)
        assert gsections.combobox_shows(page, "#school--0", "State University", "sch_state")


def test_the_probe_is_taken_off_the_page_after_each_choice(receiver):
    receiver.config(mode="gh2_sections", sections="education", section_widget="plain")
    with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                         allow_private_destination=True) as (page, _log):  # fmt: skip
        _open_section_page(page)
        _school(page, late=True)
        assert page.evaluate("() => window.__neObs") is None
