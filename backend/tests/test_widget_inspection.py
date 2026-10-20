"""Widget inspection (local only; not approved for any real page): after the one observe-only
page load, open and close each combobox present at load, and nothing else. Exercised through
the real browser path (Chromium in its network namespace behind the egress proxy) against the
v2 fixture's `gh2_widgets` mode, whose widgets build their option lists only when opened and,
with `widget_bad`, misbehave when the first standalone combobox opens. Those behaviours are
FIXTURE ASSUMPTIONS, not observations of a real page. The receiver's request log is the oracle
for what was sent."""

import dataclasses
import json
import sys

import pytest

from app.modules.preparation import gh_readonly as ro
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
JOB_PATH = f"/gh2/{BOARD}/jobs/{JOB}"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")
    receiver.config(mode="gh2_widgets")


def api():
    return greenhouse_v2._api_json(BOARD, JOB, BASE)


def inspect(receiver, bad="", limits=ro.LIMITS, inspect_widgets=True):
    receiver.config(mode="gh2_widgets", widget_bad=bad)
    return ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api(), limits=limits,
                           inspect_widgets=inspect_widgets)  # fmt: skip


def sent(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]]


def only_the_page_was_requested(receiver):
    assert sent(receiver) == [("GET", JOB_PATH)], sent(receiver)
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def widgets(obs):
    return {w["target"]: w for w in obs["inspection"]["widgets"]}


def test_opening_reveals_options_without_selecting_anything(receiver):
    obs = inspect(receiver)
    ins = obs["inspection"]
    assert ins["stopped"] is None
    assert ins["actions"] == 2 * ins["targets"] <= ins["action_limit"]
    by = widgets(obs)
    assert {"question_8101", "u1", "u2", "u3"} <= set(by)
    for w in by.values():
        assert w["opened"] and w["closed"] and w["options_count"]
        assert w["selected_after_open"] == 0 and w["value_changed"] is False
        assert w["submit_attempts"] == 0 and w["url_changed"] is False
        assert w["changes"] == {"controls": 0, "required": 0, "hidden": 0, "invalid": 0,
                                "alerts": 0}  # fmt: skip
        if w["kind"] == "api_field":
            assert w["options_match_api"] is True
    # The phone group's combobox shows the country question's list; the standalone ones match
    # no API question. Required signals are kept apart (HTML, ARIA, group, label marker).
    assert by["u1"]["options_equal_to_fields"] == ["question_8102"]
    assert by["u2"]["options_count"] == 3 and by["u2"]["options_equal_to_fields"] == []
    assert by["u2"]["required_signals"] == {"html": False, "aria": True, "group_aria": False,
                                            "label_marker": False}  # fmt: skip
    assert by["u3"]["required_signals"]["aria"] is False
    assert ins["location_control_present"] is False
    assert ins["data_requests_refused"]["during_actions"] == 0
    assert ins["requests_during_actions"] == 0
    only_the_page_was_requested(receiver)


def test_without_the_flag_nothing_is_clicked(receiver):
    obs = inspect(receiver, inspect_widgets=False)
    assert obs["inspection"] is None
    by = {f["key"]: f for f in obs["mapping"]["fields"]}
    assert by["question_8101"]["checks"]["options"] == "not_observable_at_load"
    only_the_page_was_requested(receiver)


def test_action_budget_is_enforced(receiver):
    obs = inspect(receiver, limits=dataclasses.replace(ro.LIMITS, widget_actions=5))
    ins = obs["inspection"]
    assert ins["actions"] == 4 and ins["stopped"] == "action budget reached"
    assert len(ins["widgets"]) == 2  # never half a widget: open and close, or neither


def test_time_budget_is_enforced(receiver):
    obs = inspect(receiver, limits=dataclasses.replace(ro.LIMITS, widget_seconds=1.0))
    assert obs["inspection"]["stopped"] == "inspection time budget reached"
    assert obs["inspection"]["actions"] == 0


def test_page_request_budget_still_applies_to_requests_a_widget_starts(receiver):
    obs = inspect(receiver, "images", limits=dataclasses.replace(ro.LIMITS, page_requests=3))
    assert obs["inspection"]["stopped"] == "page request budget reached"
    assert sum(1 for _, p in sent(receiver) if p == "/gh2-api/robots.txt") <= 2


def test_a_submission_started_by_a_widget_is_cancelled_and_stops(receiver):
    obs = inspect(receiver, "submit")
    ins = obs["inspection"]
    assert ins["stopped"] == "a submission was attempted"
    assert widgets(obs)["u2"]["submit_attempts"] >= 1
    only_the_page_was_requested(receiver)


def test_an_upload_started_by_a_widget_is_blocked_and_stops(receiver):
    obs = inspect(receiver, "upload")
    assert obs["inspection"]["stopped"] == "a non-GET request was attempted"
    assert {"method": "POST", "path": f"{JOB_PATH}/attachments"} in obs["blocked_non_get"]
    only_the_page_was_requested(receiver)


def test_a_file_chooser_is_recorded_and_stops_without_any_file(receiver):
    obs = inspect(receiver, "filechooser")
    assert obs["inspection"]["stopped"] == "file_chooser"
    only_the_page_was_requested(receiver)


def test_a_widget_data_request_is_refused_even_as_a_same_origin_get(receiver):
    """GET is not assumed harmless: no data endpoint is approved, so a widget that needs one
    stays closed and the boundary is reported; the endpoint is never reached."""
    obs = inspect(receiver, "fetch")
    ins = obs["inspection"]
    assert ins["stopped"] is None  # a refused request is a finding, not a reason to stop
    u2 = widgets(obs)["u2"]
    assert u2["opened"] is False and u2["data_requests_refused"] == 1
    assert ins["data_requests_refused"] == {"at_load": 0, "during_actions": 1,
                                            "same_origin": 1, "by_type": {"fetch": 1}}  # fmt: skip
    only_the_page_was_requested(receiver)


def test_a_navigation_started_by_a_widget_is_refused_and_stops(receiver):
    obs = inspect(receiver, "nav")
    ins = obs["inspection"]
    assert ins["stopped"] == "a second top-level navigation was attempted"
    assert ins["controls_at_end"] is None  # the page may have been replaced: not measured
    only_the_page_was_requested(receiver)


def test_an_address_change_stops(receiver):
    obs = inspect(receiver, "hash")
    assert obs["inspection"]["stopped"] == "the page address changed"
    only_the_page_was_requested(receiver)


def test_a_challenge_stops(receiver):
    assert inspect(receiver, "captcha")["inspection"]["stopped"] == "challenge"
    only_the_page_was_requested(receiver)


def test_a_dialog_is_dismissed_and_stops(receiver):
    assert inspect(receiver, "dialog")["inspection"]["stopped"] == "dialog"
    only_the_page_was_requested(receiver)


def test_a_widget_that_selects_on_open_stops(receiver):
    obs = inspect(receiver, "select")
    assert obs["inspection"]["stopped"] == "opening changed a value or selected an option"
    assert widgets(obs)["u2"]["selected_after_open"] == 1
    only_the_page_was_requested(receiver)


def test_a_required_change_is_recorded(receiver):
    obs = inspect(receiver, "required")
    assert obs["inspection"]["stopped"] is None
    assert widgets(obs)["u2"]["changes"]["required"] == 1
    only_the_page_was_requested(receiver)


def test_a_covered_widget_is_not_clicked_through_its_cover(receiver):
    """Only the targeted element is acted on: if something else would receive the click,
    nothing is clicked, the widget is reported as not opened and the inspection continues."""
    obs = inspect(receiver, "covered")
    u2 = widgets(obs)["u2"]
    assert u2["opened"] is False and u2["error"] == "pointer_intercepted"
    assert u2["value_changed"] is False and obs["inspection"]["stopped"] is None
    assert widgets(obs)["u3"]["opened"] is True
    only_the_page_was_requested(receiver)


def test_published_inspection_is_anonymous(receiver):
    obs = inspect(receiver)
    pub = ro.publishable(api(), {"name": "x"}, JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(BOARD, JOB, api(), None))
    data = json.loads(text)
    targets = [w["target"] for w in data["inspection"]["widgets"]]
    assert all(t.startswith(("q", "u")) and t[1:].isdigit() for t in targets), targets
    for raw in ("question_8101", "phone-country", "extra-1", "hear about", "Country code",
                "Morning"):  # fmt: skip
        assert raw not in text
    # A stop reason outside the allowlist would fail the guard (and suppress the output).
    pub["inspection"]["stopped"] = "opened https://example.test/x"
    with pytest.raises(ro.Leak):
        ro.guard(pub, set())


def test_a_real_page_is_inspected_only_under_the_b3_policy(monkeypatch):
    with pytest.raises(ro.NotApproved, match="B3 policy"):
        ro.observe_page(BOARD, JOB, inspect_widgets=True)
