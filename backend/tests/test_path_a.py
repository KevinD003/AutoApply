"""Path A (providers/path_a.py): the owner's manual dropdown check is recorded as fixed choices
only, ships as pending, and stays advisory. Every answer here is synthetic, written for the
test: none is an observation of any page."""

import json
import pathlib
import re

import pytest

from app.modules.execution.adapters import dropdowns
from app.modules.providers import path_a, registry
from app.modules.providers.model import matrix

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / "docs" / "manual-dropdown-checklist.md"
SYNTHETIC = {  # invented for this test; not observed anywhere
    "status": "recorded",
    "provenance": path_a.PROVENANCE,
    "observed_on": "2026-10-22",
    "dropdowns_checked": 1,
    "answers": {
        "q1_single_click_opens": "yes",
        "q7_options_shown": "all_at_once",
        "q8a_phone_group_control": "dialling_code",
        "q8b_other_required_control": "other",
    },  # fmt: skip
}


def test_the_shipped_record_is_pending():
    assert json.loads(path_a.RECORD.read_text()) == path_a.PENDING
    assert path_a.load() is None
    advice = path_a.assess(None)
    assert {k: v["state"] for k, v in advice.items() if k != "fixture_profile"} == {
        "dropdowns": "unknown", "options": "unknown", "u1": "unknown", "u2": "unknown"}  # fmt: skip


def test_the_questions_follow_the_checklist():
    numbered = re.findall(r"^(\d)\. ", CHECKLIST.read_text(), re.M)
    assert numbered == [str(i) for i in range(1, 9)]
    asked = [re.match(r"q(\d)", q).group(1) for q in path_a.QUESTIONS]
    assert asked == [str(i) for i in range(1, 8)] + ["8", "8"]  # question 8 asks about two
    assert set(path_a._STRATEGY.values()) <= set(dropdowns.STRATEGIES)


@pytest.mark.parametrize(
    "bad, named",
    [
        ({**SYNTHETIC, "answers": {"q1_single_click_opens": "Acme's arrow"}}, "q1_single_click"),
        ({**SYNTHETIC, "answers": {"q9_wording": "yes"}}, "unknown question"),
        ({**SYNTHETIC, "note": "Acme Corp, Senior Engineer"}, "unexpected fields"),
        ({**SYNTHETIC, "provenance": "assistant_guess"}, "provenance"),
        ({**SYNTHETIC, "observed_on": "yesterday"}, "observed_on"),
        ({**SYNTHETIC, "dropdowns_checked": 3}, "dropdowns_checked"),
        ({**SYNTHETIC, "answers": {}}, "answers"),
        ({**SYNTHETIC, "status": "guessed"}, "status"),
        ("https://boards.example.com/acme/jobs/1", "unexpected fields"),
    ],
)
def test_anything_but_the_fixed_choices_is_refused_without_echoing_it(bad, named):
    with pytest.raises(path_a.InvalidRecord) as e:
        path_a.validate(bad)
    assert named in str(e.value)
    for marker in ("Acme", "Senior Engineer", "yesterday", "assistant", "guessed", "example.com"):
        assert marker not in str(e.value), marker


def test_a_record_is_assessed_but_never_changes_support(tmp_path):
    before = {n: (matrix(p), p.real_destinations_enabled) for n, p in registry.PROVIDERS.items()}
    record = tmp_path / "path-a.json"
    record.write_text(json.dumps(SYNTHETIC))
    advice = path_a.assess(path_a.load(record))
    assert advice["dropdowns"] == {"state": "candidate", "reason": "click_control must be "
                                   "proven on a fixture that mirrors this, then observed "
                                   "read-only"}  # fmt: skip
    assert advice["options"]["state"] == "candidate"
    assert (advice["u1"]["state"], advice["u2"]["state"]) == ("blocked", "blocked")
    assert "a dialling-code choice" in advice["u1"]["reason"]
    assert "another kind of choice" in advice["u2"]["reason"]
    assert advice["fixture_profile"] == dict.fromkeys(path_a.PROFILE, "unknown")
    after = {n: (matrix(p), p.real_destinations_enabled) for n, p in registry.PROVIDERS.items()}
    assert after == before


@pytest.mark.parametrize(
    "answers, blocker, state",
    [
        ({"q1_single_click_opens": "no"}, "dropdowns", "blocked"),
        ({"q1_single_click_opens": "keyboard_only"}, "dropdowns", "candidate"),
        ({"q1_single_click_opens": "arrow_only"}, "dropdowns", "candidate"),
        ({"q2_typing_filters": "yes", "q7_options_shown": "all_at_once"}, "options", "unsupported"),
        ({"q7_options_shown": "loads_on_scroll"}, "options", "unsupported"),
        ({"q7_options_shown": "needs_typing"}, "options", "unsupported"),
    ],
)
def test_policy_limits_hold_whatever_the_answers(answers, blocker, state):
    advice = path_a.assess(path_a.validate({**SYNTHETIC, "answers": answers}))
    assert advice[blocker]["state"] == state
