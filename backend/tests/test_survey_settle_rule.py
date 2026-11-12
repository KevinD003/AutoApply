"""D152 (rank 18): the read-only survey publishes, for each list it opens, whether the list met
the adapter's settle rule at the survey's last read (local only; no run is approved for a real
page). Since D145 the adapter counts a list as settled only when, besides the survey's own test
and equal reads, the page has recorded no change to a list for half a second (STABLE_MS). The
survey judged lists by its own, weaker test and published nothing of that record, so no run
showed whether a real page meets the rule.

Through the real browser path against the v2 fixture's dropdowns (`gh2_dd`). Its variants are
FIXTURE ASSUMPTIONS, not observations of a real page; the receiver's request log is the oracle
for what was sent."""

import re
import sys
import urllib.request
from dataclasses import replace

import pytest

from app.modules.execution.adapters import dropdowns
from app.modules.execution.browser import SubresourceRule
from app.modules.preparation import gh_readonly as ro
from tests.conftest import RECEIVER_PORT
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
CDN = f"http://localhost:{RECEIVER_PORT}"  # the CDN stand-in: same receiver, another host name
B3 = SubresourceRule(CDN, frozenset({"GET", "HEAD"}), frozenset({"script", "stylesheet"}),
                     allow_private=True)  # fmt: skip
RULE_B = ro._locale_rule(CDN, allow_private=True)
RULE_C = ro._locale_rule_c(CDN, allow_private=True)
N = 3  # the stand-in page's dropdowns, all acted on
PATH_A = ro.LIMITS  # the survey's own window (600 ms), shorter than the adapter's
PATH_B = ro.LOCALE_LIMITS  # the adapter's window (1.5 s)
PATH_C = replace(ro.LOCALE_C_LIMITS, widget_actions=4 * N)  # each with its container's click
NOT_JUDGED = {"list_quiet": None, "equal_reads": None, "pending": None, "met": None}
SETTLED = {"list_quiet": True, "equal_reads": True, "pending": False, "met": True}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")


def api():
    return greenhouse_v2._api_json(BOARD, JOB, BASE)


def inspection(receiver, dd, limits=PATH_A, rule=None, **cfg):
    receiver.config(**{"mode": "gh2_dd", "dd": dd, "locale_origin": CDN,
                       "locale_path": "/locales/en/common.json", **cfg})  # fmt: skip
    obs = ro.observe_page(
        BOARD, JOB, base=BASE, prefix="gh2", api_json=api(), subresources=(B3,),
        inspect_widgets=True, locale_rule=rule, limits=limits,
        container_fallback=rule is RULE_C,
    )  # fmt: skip
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # Published as it is: anonymous, from the vocabulary only.
    text = ro.guard(ro.publishable(api(), {"name": "x"}, JOB, obs),
                    ro.sensitive_values(BOARD, JOB, api(), None))  # fmt: skip
    assert '"settle_rule"' in text and '"settle_rule_counts"' in text
    return obs["inspection"]


def observe(receiver, dd, limits=PATH_A, rule=None, **cfg):
    ins = inspection(receiver, dd, limits, rule, **cfg)
    assert ins["stopped"] is None and ins["targets"] == N
    widgets = [w for w in ins["widgets"] if "skipped" not in w]
    assert len(widgets) == N
    return ins, widgets


def counts(ins) -> tuple[int, int, int]:
    c = ins["settle_rule_counts"]
    return c["met"], c["not_met"], c["not_applicable"]


# ---- the rule, on its own ---------------------------------------------------------------------


def test_the_quiet_time_and_the_window_are_the_adapters():
    assert ro._LIST_QUIET_MS == dropdowns.STABLE_MS == 500
    assert ro._ADAPTER_SETTLE_MS == dropdowns.SETTLE_MS == ro.LOCALE_LIMITS.widget_settle_ms
    assert ro.LIMITS.widget_settle_ms < ro._ADAPTER_SETTLE_MS  # path A: never judged


def _post(list_quiet_ms):
    return {"list_quiet_ms": list_quiet_ms}


@pytest.mark.parametrize(
    "state,quiet_ms,reads,pending,want",
    [
        # no change to a list recorded at all counts as quiet, as in the adapter
        ("observed_sufficiently", None, [["a"]] * 3, False, (True, True, False, True)),
        ("observed_sufficiently", 500, [["a"]] * 3, False, (True, True, False, True)),
        ("observed_sufficiently", 499, [["a"]] * 3, False, (False, True, False, False)),
        # every read is compared: the adapter needs three equal reads in a row
        ("observed_sufficiently", 900, [["b"], ["a"], ["a"]], False, (True, False, False, False)),
        ("observed_sufficiently", 900, [["a", "b"], ["a", "b"], ["b", "a"]], False,
         (True, False, False, False)),
        ("observed_sufficiently", 900, [["a"]] * 3, True, (True, True, True, False)),
        # the survey's own test comes first
        ("partially_observed", 900, [["a"]] * 3, False, (True, True, False, False)),
        ("opened_options_not_observable", 900, [[]] * 3, False, (True, True, False, False)),
    ],
)  # fmt: skip
def test_the_rule_at_the_last_read(state, quiet_ms, reads, pending, want):
    got = ro.settle_rule(state, _post(quiet_ms), reads, pending, 1500)
    assert (got["list_quiet"], got["equal_reads"], got["pending"], got["met"]) == want


def test_a_window_shorter_than_the_adapters_publishes_the_parts_but_no_verdict():
    got = ro.settle_rule("observed_sufficiently", _post(900), [["a"]] * 3, False, 1499)
    assert got == {"list_quiet": True, "equal_reads": True, "pending": False, "met": None}


@pytest.mark.parametrize("state", ["not_opened", "undetermined", "click_failed"])
def test_nothing_is_judged_where_no_list_opened(state):
    assert ro.settle_rule(state, _post(900), [["a"]] * 3, False, 1500) == NOT_JUDGED


def test_a_request_is_pending_until_it_has_finished():
    done, waiting = {"outcome": "2xx", "done": True}, {"outcome": "2xx"}
    assert ro._pending([done, waiting], 0) is True  # answered, its body not yet finished
    assert ro._pending([waiting, done], 1) is False  # only those made since the action began
    assert ro._pending(None, 0) is False


@pytest.mark.parametrize(
    "own_state,own,container,want",
    [
        ("observed_sufficiently", True, None, True),
        ("partially_observed", False, None, False),
        ("not_opened", None, True, True),  # the adapter tries the container next
        ("not_opened", None, False, False),
        ("undetermined", None, True, None),  # the adapter refuses here and tries nothing else
        ("not_opened", None, None, None),
    ],
)
def test_a_list_is_counted_as_the_adapter_would_reach_it(own_state, own, container, want):
    attempt = {"settle_rule": None if container is None else {"met": container}}
    w = {"open_state": own_state, "settle_rule": {"met": own}, "container_attempt": attempt}
    assert ro._judged(w) is want


# ---- through the survey, against the stand-in ---------------------------------------------------


def test_a_settled_list_meets_the_rule_in_the_adapters_window(receiver):
    ins, widgets = observe(receiver, "click_popup", limits=PATH_B)
    for w in widgets:
        assert w["open_state"] == "observed_sufficiently" and w["settle_rule"] == SETTLED
    assert counts(ins) == (N, 0, 0)


def test_path_a_publishes_the_parts_but_never_a_verdict(receiver):
    """The survey's own window (600 ms) ends before the adapter could count any list as settled
    (its third read, 750 ms): the parts are published, the verdict is not."""
    ins, widgets = observe(receiver, "click_popup")
    for w in widgets:
        assert w["settle_rule"] == {**SETTLED, "met": None}
    assert counts(ins) == (0, 0, N)


@pytest.mark.parametrize("limits", [PATH_A, PATH_B], ids=["window_600", "window_1500"])
def test_a_list_that_keeps_changing_never_meets_it(receiver, limits):
    """Re-rendered every 300 ms: whatever the survey's own test says of it (the same number of
    options at every read, and quiet pauses longer than its 150 ms), the page's record says a
    list changed less than half a second before the last read."""
    ins, widgets = observe(receiver, "slow_changing", limits=limits)
    for w in widgets:
        assert w["settle_rule"]["list_quiet"] is False and w["settle_rule"]["met"] is not True
    assert counts(ins) == ((0, N, 0) if limits is PATH_B else (0, 0, N))


def test_the_survey_s_own_test_and_the_adapter_s_rule_can_differ(receiver):
    """Options shown 250 ms after the opening: by the survey's own test they are observed
    sufficiently at its last read (600 ms), but the page changed a list only about 350 ms
    before it. In the adapter's window (1.5 s, paths B and C) the rule is met."""
    ins, widgets = observe(receiver, "delayed", delay_ms=250)
    for w in widgets:
        assert w["open_state"] == "observed_sufficiently"
        assert w["settle_rule"]["list_quiet"] is False and w["settle_rule"]["met"] is None
    receiver.reset()
    ins, widgets = observe(receiver, "delayed", limits=PATH_B, delay_ms=250)
    assert all(w["settle_rule"] == SETTLED for w in widgets)
    assert counts(ins) == (N, 0, 0)


@pytest.mark.parametrize("tick_ms", [100, 300])
def test_changes_elsewhere_on_the_page_are_not_a_lists(receiver, tick_ms):
    """Something that is no part of a list changes every 100 or 300 ms: the page's record of
    changes to a list stays quiet, and, as the adapter's classification leaves out the whole
    page's 150 ms check since D153, every list meets the rule. (The survey's own `open_state`
    keeps that check, so it may say still changing.)"""
    ins, widgets = observe(receiver, "click_popup", limits=PATH_B, dd_tick_ms=tick_ms)
    assert all(w["settle_rule"] == SETTLED for w in widgets)
    assert counts(ins) == (N, 0, 0)


def test_a_style_sheet_that_keeps_changing_holds_the_rule(receiver):
    """D153: a style sheet whose text changes every 300 ms (its rule matches nothing) counts as a
    change to a list, as it can hide or show options: no list is quiet, none meets the rule."""
    ins, widgets = observe(receiver, "click_popup", limits=PATH_B, dd_style_tick_ms=300)
    for w in widgets:
        assert w["settle_rule"]["list_quiet"] is False and w["settle_rule"]["met"] is False
    assert counts(ins) == (0, N, 0)


@pytest.mark.parametrize("delay_ms,pending", [(3000, True), (0, False)])
def test_an_answer_still_awaited_at_the_last_read_holds_the_rule(receiver, delay_ms, pending):
    """Path B: opening also asks for a locale file, which path B allows. Not finished by the last
    read, the list does not meet the rule, as in the adapter (no data request in flight); once
    finished, it does. The adapter on a real page refuses such a list all the same (any data
    request, D104/D108): that is published apart (`requests_during`)."""
    ins, widgets = observe(receiver, "open_locale_fetch", limits=PATH_B, rule=RULE_B,
                           locale_delay_ms=delay_ms)  # fmt: skip
    for w in widgets:
        assert w["requests_during"]["locale_allowed"] == 1
        assert w["settle_rule"]["pending"] is pending
        assert w["settle_rule"]["met"] is (not pending)
    assert counts(ins) == ((0, N, 0) if pending else (N, 0, 0))


def test_only_the_actions_own_requests_count_as_pending(receiver):
    """The page's first opening asks for a locale file, answered after 8 s. Still awaited at the
    first list's last read, that list does not meet the rule. The second list asks for nothing:
    the first one's request, still awaited, is not its own, as in the adapter (which counts only
    the requests made since its own action), and the second list meets the rule."""
    ins, widgets = observe(receiver, "locale_on_first_open", limits=PATH_B, rule=RULE_B,
                           locale_delay_ms=8000)  # fmt: skip
    first, second = widgets[0], widgets[1]
    assert first["requests_during"]["locale_allowed"] == 1
    assert first["settle_rule"]["pending"] is True and first["settle_rule"]["met"] is False
    assert second["requests_during"]["locale_allowed"] == 0
    assert second["settle_rule"] == SETTLED
    assert counts(ins) == (N - 1, 1, 0)


def test_a_list_opened_by_its_container_is_judged_on_that_action(receiver):
    """Path C: the click on the control shows nothing, the click on its container opens the
    list. The control's own action is not judged; the container's is, and is counted."""
    ins, widgets = observe(receiver, "container_only", limits=PATH_C, rule=RULE_C)
    for w in widgets:
        assert w["opened_by"] == "container" and w["settle_rule"] == NOT_JUDGED
        assert w["container_attempt"]["settle_rule"] == SETTLED
    assert counts(ins) == (N, 0, 0)


def test_a_containers_list_that_keeps_changing_does_not_meet_it(receiver):
    ins, widgets = observe(receiver, "container_slow_changing", limits=PATH_C, rule=RULE_C)
    for w in widgets:
        rule = w["container_attempt"]["settle_rule"]
        assert w["opened_by"] == "container"
        assert rule["list_quiet"] is False and rule["met"] is False
    assert counts(ins) == (0, N, 0)


def test_a_containers_own_request_still_awaited_holds_the_rule(receiver):
    ins, widgets = observe(receiver, "container_open_locale", limits=PATH_C, rule=RULE_C,
                           locale_delay_ms=3000)  # fmt: skip
    for w in widgets:
        rule = w["container_attempt"]["settle_rule"]
        assert rule["pending"] is True and rule["met"] is False
    assert counts(ins) == (0, N, 0)


def test_a_containers_action_counts_only_its_own_requests(receiver):
    """Path C: the click on the control opens nothing but asks for a locale file (answered after
    8 s); the click on its container opens the list. That request belongs to the control's own
    action, not the container's, whose list meets the rule."""
    ins, widgets = observe(receiver, "container_locale", limits=PATH_C, rule=RULE_C,
                           locale_delay_ms=8000)  # fmt: skip
    for w in widgets:
        assert w["opened_by"] == "container" and w["settle_rule"] == NOT_JUDGED
        assert w["requests_during"]["locale_allowed"] == 1
        assert w["container_attempt"]["settle_rule"] == SETTLED
    assert counts(ins) == (N, 0, 0)


def test_a_list_after_an_undetermined_click_is_not_counted(receiver):
    """The click on the control shows a tooltip and no list: undetermined, which the adapter
    refuses without trying the container. The survey still clicks the container (path C) and
    publishes that action's rule, but does not count it."""
    ins, widgets = observe(receiver, "container_tooltip", limits=PATH_C, rule=RULE_C)
    for w in widgets:
        assert w["open_state"] == "undetermined"
        assert w["container_attempt"]["settle_rule"] == SETTLED
    assert counts(ins) == (0, 0, N)


def test_a_list_that_never_opens_is_not_judged(receiver):
    ins, widgets = observe(receiver, "inert", limits=PATH_B)
    for w in widgets:
        assert w["open_state"] == "not_opened" and w["settle_rule"] == NOT_JUDGED
    assert counts(ins) == (0, 0, N)


def test_a_control_that_leaves_the_page_is_not_judged(receiver):
    """The control and its list are removed 1.2 s after the list opened, after two reads that
    saw it settled: the control is gone, so nothing is judged, and the inspection stops there
    (a control was removed)."""
    ins = inspection(receiver, "vanish_after_open", limits=PATH_B)
    first = ins["widgets"][0]
    assert first["control_gone"] is True and first["settle_rule"] == NOT_JUDGED
    assert counts(ins)[:2] == (0, 0)


def test_a_reset_clears_the_page_busy_elsewhere(receiver):
    """D145's ticker (`dd_tick_ms`) was not among the settings the receiver's reset clears, so it
    went on changing the page of every later test of a module (found by this file's own order).
    The page the stand-in serves after a reset has no ticker."""

    def tick() -> str:
        page = urllib.request.urlopen(f"{BASE}/gh2/{BOARD}/jobs/{JOB}", timeout=10).read()
        return re.search(r"TICK = (\d+)", page.decode()).group(1)

    receiver.config(mode="gh2_dd", dd="click_popup", dd_tick_ms=300)
    assert tick() == "300"
    receiver.reset()
    receiver.config(mode="gh2_dd", dd="click_popup")
    assert tick() == "0"


def test_a_request_the_page_cancels_is_no_longer_pending(receiver):
    """Opening asks for a locale file (which would answer after 3 s) and the page cancels it
    100 ms later: it failed, so nothing is pending at the last read, and the list meets the rule."""
    ins, widgets = observe(receiver, "open_locale_abort", limits=PATH_B, rule=RULE_B,
                           locale_delay_ms=3000)  # fmt: skip
    for w in widgets:
        assert w["requests_during"]["locale_allowed"] == 1 and w["settle_rule"] == SETTLED
    assert ins["locale_requests_allowed"]["outcomes"] == {"failed": N}
    assert counts(ins) == (N, 0, 0)


def test_a_skipped_widget_is_not_counted(receiver):
    """A dropdown hidden at load is skipped (never acted on): it is published as skipped, and the
    counts cover only the lists acted on."""
    ins = inspection(receiver, "hidden_one", limits=PATH_B)
    assert [w.get("skipped") for w in ins["widgets"]] == [None] * (N - 1) + [
        "not_visible_or_not_unique"]  # fmt: skip
    assert counts(ins) == (N - 1, 0, 0)
