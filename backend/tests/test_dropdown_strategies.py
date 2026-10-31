"""Explicit dropdown strategies of the id-mapping adapter (adapters/dropdowns.py), against the
fixture's dropdown behaviours (`gh2_dd`, `_DD_JS`). Every behaviour is a FIXTURE ASSUMPTION:
run #9 saw no opening evidence on the real page, so none of these is known to match it. A
passing test here says the adapter handles that assumed behaviour safely, not that any real
form can be filled or submitted. The receiver's ledger is the oracle for what was sent."""

import pytest

from app.modules.execution import runner
from app.modules.preparation import greenhouse_dom as dom
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_greenhouse_dom import v2_application, v2_job


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
        # ... and when that file is slow, as on a busy CI runner (CI #133 failed this way)
        ("locale_gate", {"locale_delay_ms": 2500}),
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


def test_a_form_still_loading_after_the_allowance_stops_before_anything_is_entered(
    api, receiver, monkeypatch
):
    """The locale file never arrives within the allowance: the runner stops safely instead of
    using a page whose controls may not respond yet. Nothing is typed, disclosed or sent."""
    monkeypatch.setattr(runner, "SETTLE_LOAD_MS", 1000)
    receiver.config(mode="gh2_dd", dd="locale_gate")
    app_id = v2_application(api)
    receiver.config(locale_delay_ms=30000)
    before = len(receiver.ledger()["requests"])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert runner.NOT_READY in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # The form and its locale file, each requested once: nothing was repeated while it waited.
    paths = [r["path"] for r in led["requests"][before:]]
    assert paths.count("/locales/en/common.json") == 1, paths
    assert all(r["method"] == "GET" for r in led["requests"][before:])


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


def test_unlisted_dropdowns_are_a_checkpoint_from_capture(api, receiver):
    """A phone-country selector inside the phone group and a required dropdown the job data does
    not list: captured as blocking fields whose meaning is never inferred, so the route is a
    checkpoint and the package cannot be approved before anything is queued or disclosed."""
    receiver.config(mode="gh2_dd_extras", dd="click_popup")
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    fields = api.get(f"/jobs/{job_id}/form").json()["schema"]["fields"]
    unlisted = [f for f in fields if f.get("unsupported_reason") == dom.UNLISTED_REASON]
    assert len(unlisted) == 2 and all(f["type"] == "unsupported" and f["required"]
                                      for f in unlisted)  # fmt: skip
    r = api.get(f"/jobs/{job_id}/route").json()
    assert (r["route"], r["reason"]) == ("checkpoint", "unsupported_required_control")
    assert "2 required controls NoEfforts cannot fill" in r["message"]
    assert "extra-1" not in r["message"] and "phone-country" not in r["message"]
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert {f["key"] for f in unlisted} <= set(p["content"]["unresolved"])  # never guessed
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code != 200
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure(api, receiver):
    """Captured and approved without them; the page then shows the same two dropdowns: counted,
    never named, and the attempt stops before anything is disclosed."""
    receiver.config(mode="gh2_dd", dd="click_popup")
    app_id = v2_application(api)
    receiver.config(mode="gh2_dd_extras", dd="click_popup")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "2 new field(s)" in detail  # both unlisted dropdowns, counted, never named
    assert "extra-1" not in detail and "phone-country" not in detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_capabilities_stay_fixture_only_and_real_destinations_refused():
    from app.modules.execution import policy
    from app.modules.execution.adapters import dropdowns

    assert set(dropdowns.STRATEGIES) == {"click_control", "arrow_down", "trigger_button"}
    assert all(dropdowns.CAPABILITIES[s] == "fixture_only" for s in dropdowns.STRATEGIES)
    assert dropdowns.CAPABILITIES["options_loaded_from_network"].startswith("checkpoint")
    assert policy.CAPABILITIES["greenhouse_dom"]["real_destinations"] is False
