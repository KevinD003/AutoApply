"""Explicit dropdown strategies of the id-mapping adapter (adapters/dropdowns.py), against the
fixture's dropdown behaviours (`gh2_dd`, `_DD_JS`). Every behaviour is a FIXTURE ASSUMPTION:
run #9 saw no opening evidence on the real page, so none of these is known to match it. A
passing test here says the adapter handles that assumed behaviour safely, not that any real
form can be filled or submitted. The receiver's ledger is the oracle for what was sent."""

import pytest

from app.modules.execution import runner
from tests.execution_harness import Receiver, attempt, queue
from tests.test_greenhouse_dom import v2_application


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def package(api, app_id):
    return api.get(f"/applications/{app_id}/package").json()["package"]["content"]


def run(api, receiver, mode="gh2_dd", **cfg):
    receiver.config(mode=mode, **cfg)
    app_id = v2_application(api)
    aid = queue(api, app_id)
    return app_id, aid, runner.run_attempt(aid, "w1")


@pytest.mark.parametrize(
    "dd,cfg",
    [
        ("click_popup", {}),
        ("type_filter", {}),  # typing would filter; the adapter never types
        ("arrow_down", {}),
        ("trigger_button", {}),
        ("locale_gate", {}),  # opens once a locale file has loaded at page load
        ("delayed", {"delay_ms": 300}),
        ("preselect_first", {}),  # the highlighted first option is not what was approved
    ],
)
def test_each_strategy_selects_exactly_the_approved_option(api, receiver, dd, cfg):
    app_id, aid, result = run(api, receiver, dd=dd, **cfg)
    assert result == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    answers = {a["key"]: a["value"] for a in package(api, app_id)["answers"]}
    for key in ("question_8101", "question_8102", "question_8104"):
        assert sent[key] == answers[key]["option"], key
    assert sent["question_8104"] == "0"  # "No": the second option, never the first by default


@pytest.mark.parametrize(
    "dd,cfg,reason",
    [
        ("inert", {}, "no supported action opened it"),
        ("type_only", {}, "no supported action opened it"),  # never types into a dropdown
        ("two_triggers", {}, "several elements could open it"),
        ("locale_on_open", {}, "its options load from the network (not verified)"),
        ("delayed", {"delay_ms": 3000}, "its list could not be read completely"),
        ("virtualized", {}, "its list could not be read completely"),  # never scrolled
        ("duplicate_option", {}, "its list shows an option more than once"),
    ],
)
def test_unverifiable_dropdowns_stop_before_anything_is_disclosed(api, receiver, dd, cfg, reason):
    _, aid, result = run(api, receiver, dd=dd, **cfg)
    assert result == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "dropdown" in detail and reason in detail, detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@pytest.mark.parametrize("dd", ["ignores_choice", "wrong_value"])
def test_a_choice_that_does_not_read_back_is_never_submitted(api, receiver, dd):
    _, aid, result = run(api, receiver, dd=dd)
    assert result == "abandoned"
    assert "did not keep their values" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_unmatched_dropdowns_are_refused_not_interpreted(api, receiver):
    """A phone-country selector inside the phone group and a required dropdown the job data does
    not list: their meaning is never inferred; the form is refused before disclosure."""
    _, aid, result = run(api, receiver, mode="gh2_dd_extras", dd="click_popup")
    assert result == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "new fields" in detail and "extra-1" in detail and "phone-country" in detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_capabilities_stay_fixture_only_and_real_destinations_refused():
    from app.modules.execution import policy
    from app.modules.execution.adapters import dropdowns

    assert set(dropdowns.STRATEGIES) == {"click_control", "arrow_down", "trigger_button"}
    assert all(dropdowns.CAPABILITIES[s] == "fixture_only" for s in dropdowns.STRATEGIES)
    assert dropdowns.CAPABILITIES["options_loaded_from_network"].startswith("checkpoint")
    assert policy.CAPABILITIES["greenhouse_dom"]["real_destinations"] is False
