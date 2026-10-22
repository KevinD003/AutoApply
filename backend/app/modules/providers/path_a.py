"""Path A: the owner's optional manual check of how one real posting's dropdowns behave
(docs/manual-dropdown-checklist.md), recorded as evidence without any page content.

The checklist's questions have fixed answers, so a record holds only those choices. No
wording, names, links, screenshots or free text can be stored: anything else is refused, and
a refusal names the question, never the value given. A record is the owner's own observation
in their own browser. NoEfforts never fills one in, and the record in the repository says
"pending" until the owner answers.

What the answers imply is advisory (`assess`): which bounded dropdown strategy a fixture would
have to prove next, and which blockers remain. An answer never changes a capability level,
`real_destinations`, a route or an approval. Those need their own evidence, tests, docs and
approval (docs/live-pilot-gate.md)."""

import json
import pathlib
from dataclasses import dataclass
from datetime import date

RECORD = pathlib.Path(__file__).resolve().parents[4] / "docs" / "evidence" / "path-a.json"
PROVENANCE = "owner_manual_observation"
PENDING = {"status": "pending"}

# The checklist's questions, in its order, with their fixed answers. Question 8 asks about the
# two required controls no job-data question matches: (a) the one beside the phone number
# (`u1` in docs/greenhouse-compatibility-report.md) and (b) the other one (`u2`).
QUESTIONS: dict[str, tuple[str, ...]] = {
    "q1_single_click_opens": ("yes", "no", "arrow_only", "keyboard_only"),
    "q2_typing_filters": ("yes", "no", "not_tried"),
    "q3_opening_speed": ("immediately", "noticeable_delay"),
    "q4_appearance": ("popup", "dialog", "inline", "other"),
    "q5_option_count": ("under_10", "dozens", "hundreds"),
    "q6_locale_requests_load": ("yes", "no", "not_checked"),
    "q7_options_shown": ("all_at_once", "loads_on_scroll", "needs_typing"),
    "q8a_phone_group_control": ("dialling_code", "yes_no", "places", "other"),
    "q8b_other_required_control": ("dialling_code", "yes_no", "places", "other"),
}
_FIELDS = {"status", "provenance", "observed_on", "dropdowns_checked", "answers"}
# The bounded strategy (execution/adapters/dropdowns.py) each way of opening corresponds to.
_STRATEGY = {"yes": "click_control", "arrow_only": "trigger_button", "keyboard_only": "arrow_down"}
_KIND = {"dialling_code": "a dialling-code choice", "yes_no": "a yes/no choice",
         "places": "a list of places", "other": "another kind of choice"}  # fmt: skip
# What a fixture mirroring the observation must reproduce (recorded answers, else "unknown").
PROFILE = ("q3_opening_speed", "q4_appearance", "q5_option_count", "q6_locale_requests_load")


class InvalidRecord(ValueError):
    """The message names the field or question, never the value given."""


@dataclass(frozen=True)
class Observation:
    answers: dict[str, str]  # answered questions only
    observed_on: str  # ISO date
    dropdowns_checked: int  # the checklist asks about one or two dropdowns


def validate(record: object) -> Observation | None:
    """None for the pending record, otherwise the checked observation."""
    if record == PENDING:
        return None
    if not isinstance(record, dict) or set(record) - _FIELDS:
        raise InvalidRecord("unexpected fields")
    if record.get("status") != "recorded":
        raise InvalidRecord("status must be pending or recorded")
    if record.get("provenance") != PROVENANCE:
        raise InvalidRecord("provenance must be the owner's manual observation")
    try:
        date.fromisoformat(str(record.get("observed_on")))
    except ValueError:
        raise InvalidRecord("observed_on must be an ISO date") from None
    if record.get("dropdowns_checked") not in (1, 2):
        raise InvalidRecord("dropdowns_checked must be 1 or 2")
    answers = record.get("answers")
    if not isinstance(answers, dict) or not answers:
        raise InvalidRecord("answers must be a non-empty object")
    for question, answer in answers.items():
        if question not in QUESTIONS:
            raise InvalidRecord("unknown question")
        if answer not in QUESTIONS[question]:
            raise InvalidRecord(f"{question}: not one of the fixed answers")
    return Observation(dict(answers), record["observed_on"], record["dropdowns_checked"])


def load(path: pathlib.Path = RECORD) -> Observation | None:
    return validate(json.loads(path.read_text()))


def assess(obs: Observation | None) -> dict[str, dict[str, str]]:
    """Advisory only. For each blocker the answers bear on: a state (`unknown`, `blocked`,
    `candidate` or `unsupported`) and the reason, in NoEfforts' own words; and the profile a
    fixture mirroring the observation must reproduce."""
    a = obs.answers if obs else {}

    def item(state: str, reason: str) -> dict[str, str]:
        return {"state": state, "reason": reason}

    opening = a.get("q1_single_click_opens")
    if opening is None:
        dropdowns = item("unknown", "no manual observation of how the dropdowns open")
    elif opening == "no":
        dropdowns = item("blocked", "no way of opening them was seen")
    else:
        dropdowns = item("candidate", f"{_STRATEGY[opening]} must be proven on a fixture that "
                         "mirrors this, then observed read-only")  # fmt: skip
    shown = a.get("q7_options_shown")
    if a.get("q2_typing_filters") == "yes" or shown == "needs_typing":
        options = item("unsupported", "search-as-you-type selection is unsupported by policy")
    elif shown == "loads_on_scroll":
        options = item("unsupported", "partial or virtualized lists are unsupported by policy")
    elif shown == "all_at_once":
        options = item("candidate", "the complete list must still equal the job data's options")
    else:
        options = item("unknown", "not observed whether every option is shown at once")
    unmatched = {}
    for question, control in (("q8a_phone_group_control", "u1"),
                              ("q8b_other_required_control", "u2")):  # fmt: skip
        kind = a.get(question)
        unmatched[control] = (
            item("unknown", "its kind of choice was not observed")
            if kind is None
            else item(
                "blocked",
                f"seen as {_KIND[kind]}; it maps to no question until a rule is proven on a "
                "fixture",
            )
        )
    profile = {q: a.get(q, "unknown") for q in PROFILE}
    return {"dropdowns": dropdowns, "options": options, **unmatched, "fixture_profile": profile}
