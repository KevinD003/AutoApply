"""Path C (D109, `--inspect-dropdowns`; local only, nothing approved for a real page): path B
with a locale rule that keeps run #10's observed shape (/locales/*/*.json, no query) but allows
segments of 1-128 characters with single dots, the outcome of each allowed locale request
(status class only: an allowed request is not a loaded one), and one click on a react-select
style control container when the click on the control showed no opening.

Through the real browser path against the v2 fixture (`gh2_dd`). The locale-gated and
container-only dropdowns are FIXTURE ASSUMPTIONS, not observations of a real page; the CDN is the
same receiver under another host name, so its request log is the oracle for what was sent."""

import json
import sys
from dataclasses import replace

import pytest

from app.modules.execution.browser import SubresourceRule
from app.modules.preparation import gh_readonly as ro
from tests.conftest import RECEIVER_PORT
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
JOB_PATH = f"/gh2/{BOARD}/jobs/{JOB}"
CDN = f"http://localhost:{RECEIVER_PORT}"
REAL = "https://job-boards.cdn.greenhouse.io"
HASHED = "/locales/en/common.6f8a2c1d.json"  # a content hash in the name: path B refuses it
AT = "@"  # written so the repository's address scan does not read a path as an address
B3 = SubresourceRule(CDN, frozenset({"GET", "HEAD"}), frozenset({"script", "stylesheet"}),
                    allow_private=True)  # fmt: skip
RULE_B = ro._locale_rule(CDN, allow_private=True)
RULE_C = ro._locale_rule_c(CDN, allow_private=True)
ONE = replace(ro.LOCALE_C_LIMITS, widget_actions=4)  # one dropdown, with its fallback


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


def observe(receiver, rule=RULE_C, limits=ONE, dd="locale_gate", **cfg):
    receiver.config(**{"mode": "gh2_dd", "dd": dd, "locale_origin": CDN,
                       "locale_path": "/locales/en/common.json", **cfg})  # fmt: skip
    return ro.observe_page(
        BOARD, JOB, base=BASE, prefix="gh2", api_json=api(), subresources=(B3,),
        inspect_widgets=True, locale_rule=rule, limits=limits,
        container_fallback=rule is RULE_C,
    )  # fmt: skip


def sent(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]]


def nothing_disclosed(receiver):
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert {m for m, _ in sent(receiver)} == {"GET"}, sent(receiver)


# ---- the rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/locales/en/common.json", HASHED, f"/locales/en-US/{'a' * 128}.json",
     "/locales/zh_Hant/job.board.v2.json", f"/locales/en~x/a+b{AT}c.json"],
)  # fmt: skip
def test_path_c_allows_the_observed_shape_with_longer_and_dotted_names(path):
    assert ro.locale_refusal(ro._locale_rule_c(), f"{REAL}{path}", "GET", "fetch") is None
    assert ro._locale_rule_c().permits(f"{REAL}{path}", "GET", "fetch")


@pytest.mark.parametrize(
    "url,why",
    [
        (f"{REAL}/locales/en/x..json", "path"),
        (f"{REAL}/locales/../en/x.json", "path"),
        (f"{REAL}/locales/.en/x.json", "path"),
        (f"{REAL}/locales/en/.json", "path"),
        (f"{REAL}/locales/en/{'a' * 129}.json", "path"),
        (f"{REAL}/locales/en/x%2e.json", "path"),
        (f"{REAL}/locales/en/x y.json", "path"),
        (f"{REAL}/locales/en/x/y.json", "path"),
        (f"{REAL}/locales/en.json", "path"),
        (f"{REAL}/locales/en/x.js", "path"),
        (f"{REAL}/locales/en/x.json?v=1", "query"),
        (f"{REAL}/locales/en/x.json?", "query"),
        ("https://job-boards.greenhouse.io/locales/en/x.json", "origin"),
        ("https://my.greenhouse.io/locales/en/x.json", "origin"),
    ],
)
def test_path_c_refuses_everything_outside_that_shape(url, why):
    rule = ro._locale_rule_c()
    assert ro.locale_refusal(rule, url, "GET", "fetch") == why
    for kw, w in (
        ({"method": "POST"}, "method"),
        ({"resource_type": "xhr"}, "resource_type"),
        ({"main_frame": False}, "initiator"),
        ({"redirect_hop": True}, "redirect"),
    ):
        args = {"method": "GET", "resource_type": "fetch"} | kw
        assert ro.locale_refusal(rule, f"{REAL}{HASHED}", **args) == w  # fmt: skip


def test_a_real_page_takes_path_b_or_path_c_and_nothing_wider():
    for wider in (replace(ro._locale_rule_c(), path=r"/locales/.*"),
                  replace(ro._locale_rule_c(), methods=frozenset({"GET", "HEAD"})),
                  replace(ro._locale_rule_c(), origin="https://example.com")):  # fmt: skip
        with pytest.raises(ro.NotApproved, match="approved locale rule"):
            ro.observe_page(BOARD, JOB, subresources=ro._b3_rules(), inspect_widgets=True,
                            locale_rule=wider)  # fmt: skip
    with pytest.raises(ro.NotApproved, match="path C only"):  # the fallback needs path C
        ro.observe_page(BOARD, JOB, subresources=ro._b3_rules(), inspect_widgets=True,
                        locale_rule=ro._locale_rule(), container_fallback=True)  # fmt: skip


# ---- in the browser ----------------------------------------------------------------------------


def test_a_hashed_locale_name_refused_by_path_b_loads_under_path_c_and_the_list_opens(receiver):
    """The question run #10 could not answer, on a fixture: a locale-gated dropdown whose locale
    file has a content hash in its name stays closed under path B and opens under path C, at the
    first click on the control; the file is counted as allowed AND loaded (2xx)."""
    obs = observe(receiver, rule=RULE_B, limits=replace(ro.LOCALE_LIMITS, widget_actions=2),
                  locale_path=HASHED)  # fmt: skip
    ins = obs["inspection"]
    assert {w["open_state"] for w in ins["widgets"]} == {"not_opened"}
    assert ins["locale_requests_allowed"]["total"] == 0
    assert ins["locale_path_refusals"]["properties"] == {"dots": ins["locale_refusals"]["path"]}
    receiver.reset()
    obs = observe(receiver, locale_path=HASHED, limits=replace(ONE, widget_actions=2))
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["open_state"] == "observed_sufficiently" and w["options_match_api"] is True
    assert w["opened_by"] == "control" and w["container_attempt"] is None
    assert ins["locale_requests_allowed"]["total"] == 1
    assert ins["locale_requests_allowed"]["outcomes"] == {"2xx": 1}
    assert ins["opened_by"] == {"control": 1, "container": 0}
    assert sent(receiver) == [("GET", JOB_PATH), ("GET", HASHED)]
    nothing_disclosed(receiver)


def test_an_allowed_locale_request_that_fails_is_not_counted_as_loaded(receiver):
    """D109: allowed is not loaded. The file answers 404: the request was sent, its outcome is
    4xx, and the dropdown stays closed (no container on this fixture, so no second click)."""
    obs = observe(receiver, locale_path="/locales/missing/common.json",
                  limits=replace(ONE, widget_actions=2))  # fmt: skip
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["open_state"] == "not_opened" and w["opened_by"] is None
    assert w["container_attempt"] == {"present": False, "click": None, "open_state": None,
                                      "opening_evidence": [], "visible_option_list": False,
                                      "options_match_api": None,
                                      "settle_rule": None}  # fmt: skip
    out = ins["locale_requests_allowed"]
    assert out["total"] >= 1 and out["outcomes"] == {"4xx": out["total"]}
    nothing_disclosed(receiver)


def test_a_list_that_opens_only_from_its_container_is_opened_by_the_fallback(receiver):
    """React-select-like markup where only a press on the `select__control` container opens the
    list: the click on the control shows nothing; the one fallback click opens it, and it is read
    and compared like any list. The class name is only how the target is found."""
    obs = observe(receiver, dd="container_only")
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["open_state"] == "not_opened"  # the control's own click
    c = w["container_attempt"]
    assert c["present"] and c["click"] == {"completed": True, "error": None}
    assert c["open_state"] == "observed_sufficiently" and c["options_match_api"] is True
    assert c["visible_option_list"] is True and w["opened_by"] == "container"
    assert ins["actions"] == 4 and len(ins["widgets"]) == 1  # the next one no longer fits
    assert ins["stopped"] == "action budget reached"
    assert ins["opened_by"] == {"control": 0, "container": 1}
    assert w["observations"]["existing_value_changed"] is False
    pub = ro.publishable(api(), {"name": "x"}, JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(BOARD, JOB, api(), None))
    assert "select__control" not in text and "css-fx" not in text
    assert json.loads(text)["inspection"]["opened_by"] == {"control": 0, "container": 1}
    assert sent(receiver) == [("GET", JOB_PATH)]
    nothing_disclosed(receiver)


def test_without_a_container_or_budget_there_is_no_second_click(receiver):
    """A list that never opens and has no container: one click and one Escape only. A container
    whose fallback would not fit the action budget is reported as skipped, not clicked."""
    obs = observe(receiver, dd="inert", limits=replace(ONE, widget_actions=2))
    (w,) = obs["inspection"]["widgets"]
    assert w["container_attempt"]["present"] is False and obs["inspection"]["actions"] == 2
    receiver.reset()
    obs = observe(receiver, dd="container_only", limits=replace(ONE, widget_actions=2))
    (w,) = obs["inspection"]["widgets"]
    assert w["container_attempt"]["skipped"] == "budget" and w["opened_by"] is None
    assert obs["inspection"]["actions"] == 2
    nothing_disclosed(receiver)


def test_no_second_click_after_a_first_that_changed_something(receiver):
    """The control's own click adds a hidden control without opening anything: that change stops
    the inspection, and the container is never clicked."""
    obs = observe(receiver, dd="container_noisy")
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["open_state"] == "not_opened" and w["container_attempt"] is None
    assert w["observations"]["controls_added"] == 1
    assert w["observations"]["existing_value_changed"] is False
    assert ins["actions"] == 2 and ins["stopped"] == ro.CONTROLS_ADDED_OR_REMOVED
    nothing_disclosed(receiver)


def test_react_select_markup_is_recorded_as_booleans_only(receiver):
    """D109: whether a control sits in react-select-style markup decides how a choice is read
    back. Recorded per dropdown as booleans; no class name reaches the summary. The list opens
    from the control's own click, as react-select's does, so there is no second click."""
    obs = observe(receiver, dd="react_select", limits=replace(ONE, widget_actions=2))
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["markup"] == {"select_control": True, "placeholder": True, "single_value": False,
                           "indicator": True, "in_value_container": True}  # fmt: skip
    assert w["open_state"] == "observed_sufficiently" and w["opened_by"] == "control"
    assert ins["react_select_markup"] == 1
    pub = ro.publishable(api(), {"name": "x"}, JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(BOARD, JOB, api(), None))
    assert "select__" not in text and "css-fx" not in text
    receiver.reset()
    obs = observe(receiver, dd="click_popup", limits=replace(ONE, widget_actions=2))
    (w,) = obs["inspection"]["widgets"]
    assert w["markup"]["select_control"] is False and obs["inspection"]["react_select_markup"] == 0
    nothing_disclosed(receiver)


def test_path_c_limits_differ_from_path_b_only_where_stated():
    b, c = ro.LOCALE_LIMITS, ro.LOCALE_C_LIMITS
    assert c.widget_settle_ms == b.widget_settle_ms == 1500
    changed = {k for k, v in vars(c).items() if vars(b)[k] != v}
    assert changed == {"widget_actions", "widget_seconds", "observe_seconds", "run_seconds"}
    assert c.run_seconds < 200  # inside the script's outer kill
    assert c.widget_seconds < c.observe_seconds < c.run_seconds
