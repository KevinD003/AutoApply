"""Limits of the widget-inspection detector, against an independent widget model
(fixture mode `gh2_widget_variants`, `_VARIANTS_JS`). That model was written to break the
detector's assumptions: lists outside the control's container, no links, no roles, delays, a
click target that does nothing, data it cannot get, virtualized lists, and a widget that
changes the page without any state. Each variant is a FIXTURE ASSUMPTION, not an observation
of a real page: these tests show what the detector can and cannot tell apart, not how any
real widget behaves.

Outcomes: click_failed, not_opened, undetermined, opened_options_not_observable,
partially_observed, observed_sufficiently (only the last is ever compared)."""

import sys

import pytest

from app.modules.preparation import gh_readonly as ro
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
JOB_PATH = f"/gh2/{BOARD}/jobs/{JOB}"
COUNTRY = "question_8102"  # 14 options in the job data; u1 (phone group) shows the same list


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


def inspect(receiver, variant, delay_ms=0):
    receiver.config(mode="gh2_widget_variants", variant=variant, delay_ms=delay_ms)
    obs = ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api(),
                          inspect_widgets=True)  # fmt: skip
    ins = obs["inspection"]
    assert ins["stopped"] is None and ins["targets"] == 6 and ins["actions"] == 12
    for w in ins["widgets"]:  # protections unchanged in every variant
        assert w["selected_after_open"] == 0 and w["value_changed"] is False
        assert w["submit_attempts"] == 0 and w["url_changed"] is False
        assert w["requests_during"]["blocked_non_get"] == 0
        assert w["click"] == {"completed": True, "error": None}
        assert w["focus_on_target"] is True
    led = receiver.ledger()
    assert [(r["method"], r["path"]) for r in led["requests"]] == [("GET", JOB_PATH)]
    assert led["disclosures"] == [] and led["accepted"] == 0
    return obs, {w["target"]: w for w in ins["widgets"]}


def states(by):
    return {k: w["open_state"] for k, w in by.items()}


@pytest.mark.parametrize(
    "variant,source,reference",
    [
        ("portal_linked", "associated_popup", "aria-controls"),  # list appended to <body>
        ("portal_unlinked", "new_popup", "none"),  # no link; another list visible from start
        ("aria11", "associated_popup", "aria-owns"),  # state and link on a wrapper
    ],
)
def test_lists_outside_the_control_are_found_and_compared(receiver, variant, source, reference):
    obs, by = inspect(receiver, variant)
    assert set(states(by).values()) == {"observed_sufficiently"}
    for w in by.values():
        assert w["options"]["source"] == source and w["popup"]["reference"] == reference
        assert w["closed"] is True
        if w["kind"] == "api_field":
            assert w["options_match_api"] is True
    assert by["u1"]["options_equal_to_fields"] == [COUNTRY]
    if variant == "aria11":
        e = by["question_8101"]["expanded"]
        assert (e["before"], e["after"]) == ("false", "false")  # the input itself never says
        assert (e["wrapper_before"], e["wrapper_after"]) == ("false", "true")
    # Published output stays anonymous (aliases, counts, vocabulary only).
    ro.guard(ro.publishable(api(), {"name": "x"}, JOB, obs),
             ro.sensitive_values(BOARD, JOB, api(), None))  # fmt: skip


def test_options_within_the_window_are_observed_and_their_arrival_recorded(receiver):
    _, by = inspect(receiver, "delayed", delay_ms=300)
    assert set(states(by).values()) == {"observed_sufficiently"}
    assert by[COUNTRY]["options"]["counts_over_time"][0] == 0  # busy, then filled
    assert by[COUNTRY]["options"]["counts_over_time"][-1] == 14


def test_options_after_the_window_are_not_observable_never_absent(receiver):
    """The 600 ms window is not proof of absence: an open, busy list with no options yet."""
    _, by = inspect(receiver, "delayed", delay_ms=2000)
    for w in by.values():
        assert w["open_state"] == "opened_options_not_observable"
        assert {"expanded", "popup"} <= set(w["opening_evidence"])
        assert w["indicators"]["loading"] > 0 and w["options_match_api"] is None


@pytest.mark.parametrize("variant", ["no_roles", "class_hint"])
def test_options_without_roles_are_not_read(receiver, variant):
    """Opened (the control says so), but no role-based list exists: options are not read or
    compared, even when items carry an "option" class (counted only)."""
    _, by = inspect(receiver, variant)
    for w in by.values():
        assert w["open_state"] == "opened_options_not_observable"
        assert "expanded" in w["opening_evidence"] and w["options"]["count"] == 0
        assert w["options_match_api"] is None and w["options_equal_to_fields"] == []
        assert (w["options"]["class_hint_candidates"] > 0) == (variant == "class_hint")


def test_a_widget_without_any_state_is_undetermined_not_unopened(receiver):
    _, by = inspect(receiver, "silent")
    for w in by.values():
        assert w["open_state"] == "undetermined" and w["opening_evidence"] == []
        assert w["added_visible_elements"] > 0
        assert w["expanded"]["after"] == "absent"


def test_a_click_target_that_does_not_open_the_widget(receiver):
    """The click completes and focus reaches the control, but nothing opens (only a separate
    toggle would): not opened, nothing added. The toggle is never clicked."""
    _, by = inspect(receiver, "wrong_target")
    for w in by.values():
        assert w["open_state"] == "not_opened" and w["added_visible_elements"] == 0
        assert (w["expanded"]["before"], w["expanded"]["after"]) == ("false", "false")


def test_a_widget_that_needs_a_blocked_data_request(receiver):
    """It opens, asks a data endpoint (refused, never reached), and shows an error: opened,
    options not observable, the refused request and the alert recorded for that action."""
    _, by = inspect(receiver, "data_dependent")
    for w in by.values():
        assert w["open_state"] == "opened_options_not_observable"
        assert w["requests_during"]["data_refused"] == 1
        assert w["indicators"]["alerts_added"] == 1


def test_a_virtualized_list_is_partially_observed_and_not_compared(receiver):
    _, by = inspect(receiver, "virtualized")
    for key in (COUNTRY, "u1"):
        w = by[key]
        assert w["open_state"] == "partially_observed"
        assert "setsize_larger" in w["partial_reasons"]
        assert w["options"]["count"] == 5 and w["options"]["setsize"] == 14
        assert w["options_match_api"] is None and w["options_equal_to_fields"] == []
    assert "fewer_than_api" in by[COUNTRY]["partial_reasons"]
    assert by["question_8101"]["open_state"] == "observed_sufficiently"  # 2 of 2 rendered


def _probe(**kw):
    base = {"expanded": "false", "wrapper_expanded": "absent", "associated_visible": 0,
            "new_popups": 0, "texts": [], "elsewhere": 0, "hint_popups": 0, "hint_options": 0,
            "setsize": None, "busy": 0, "hint_loading": 0, "quiet_ms": None,
            "added_visible": 0}  # fmt: skip
    return base | kw


@pytest.mark.parametrize(
    "post,series,api_count,expected",
    [
        (_probe(), [0, 0, 0], 2, ("not_opened", [])),
        (_probe(added_visible=3), [0, 0, 0], 2, ("undetermined", [])),
        (_probe(expanded="true"), [0, 0, 0], 2, ("opened_options_not_observable", [])),
        (_probe(expanded="true", texts=["a", "b"], quiet_ms=40), [0, 2, 2], 2,
         ("partially_observed", ["still_changing"])),
        (_probe(expanded="true", texts=["a"], quiet_ms=400), [0, 1, 2], 2,
         ("partially_observed", ["still_changing", "fewer_than_api"])),
        (_probe(expanded="true", texts=["a", "b"], busy=1, quiet_ms=400), [2, 2, 2], 2,
         ("partially_observed", ["loading"])),
        (_probe(new_popups=1, texts=["a", "b", "c"], quiet_ms=400), [3, 3, 3], 2,
         ("observed_sufficiently", [])),  # more than the job data: compared (and differs)
    ],
)  # fmt: skip
def test_classification_rules(post, series, api_count, expected):
    state, _, partial = ro.classify_open(_probe(), post, series, api_count, True)
    assert (state, partial) == expected


def test_a_click_that_did_not_happen_is_its_own_outcome():
    assert ro.classify_open(_probe(), _probe(), [], 2, False)[0] == "click_failed"


def test_refused_request_paths_are_published_as_shapes_only(receiver):
    """Purpose evidence without identifiers: a refused data request is published as host
    (printable names only), method, type and a path shape of generic words and placeholders."""
    obs, by = inspect(receiver, "data_dependent")
    shapes = by["question_8101"]["requests_during"]["refused_shapes"]
    # The fixture's endpoint /gh2/northwind/jobs/5020001/options.json: board and job id never
    # appear; "options" and "jobs" are generic words.
    assert shapes == [{"host": "other", "method": "GET", "resource_type": "fetch",
                       "path_shape": "/*/*/jobs/*num/options.json", "query_params": 0,
                       "count": 1}]  # fmt: skip
    text = ro.guard(ro.publishable(api(), {"name": "x"}, JOB, obs),
                    ro.sensitive_values(BOARD, JOB, api(), None))  # fmt: skip
    assert "northwind" not in text and JOB not in text


@pytest.mark.parametrize(
    "path,shape",
    [
        ("/", "/"),
        ("/assets/locales/en-US/translation.json", "/assets/locales/*/*.json"),
        ("/api/v1/boards/acme/jobs/12345", "/api/v1/boards/*/jobs/*num"),
        ("/static/chunks/0123abcd4567.js", "/static/chunks/*hex.js"),
        ("/" + "x/" * 20, "/" + "/".join(["*"] * 12) + "/..."),
    ],
)
def test_path_shapes(path, shape):
    assert ro.path_shape(path) == shape and ro._allowed(shape)
    assert not ro._allowed("/acme/jobs")  # a non-generic word is never printable
