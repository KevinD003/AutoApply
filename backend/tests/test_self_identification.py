"""D122: the owner's own voluntary self-identification (EEOC/demographic), opt-in auto-fill.

When enabled, an EEOC/demographic question is answered from the owner's saved option labels, by
exact match only. It is never inferred, never saved for reuse, never used to train the answer
brain, and anything not matched exactly stays a checkpoint. Enabling it is the owner's standing
choice to include it, but an explicit per-application choice (a "withhold") takes precedence. A
multi-answer question is never submitted as a partial set, and a decline option is exclusive.

Synthetic candidate, fictional manual forms; the option labels below are the standard public EEOC
labels, not a real person's data."""

from tests.test_preparation import setup_candidate
from tests.test_question_safety_api import application, package, rows

GENDER = {"key": "gender", "label": "Gender", "type": "select", "required": False,
          "options": [{"value": "1", "label": "Male"}, {"value": "2", "label": "Female"},
                      {"value": "3", "label": "Decline To Self Identify"}]}  # fmt: skip
GENDER_REQ = {**{"key": "g2", "label": "What is your gender?", "type": "select",
                 "required": True},
              "options": [{"value": "1", "label": "Male"}, {"value": "2", "label": "Female"},
                          {"value": "3", "label": "Decline To Self Identify"}]}  # fmt: skip
RACE = {"key": "race", "label": "Race / Ethnicity", "type": "multiselect", "required": False,
        "options": [{"value": "1", "label": "Asian"}, {"value": "2", "label": "White"},
                    {"value": "3", "label": "Black or African American"},
                    {"value": "4", "label": "Decline To Self Identify"}]}  # fmt: skip


def set_self_id(api, enabled, labels):
    r = api.put("/profile/self-identification", json={"enabled": enabled, "labels": labels})
    assert r.status_code == 200, r.text
    return r.json()


def row(api, fields, key):
    app_id = application(api, fields)
    return rows(package(api, app_id))[key], app_id


def consent(api, app_id, key, choice):
    r = api.put(f"/applications/{app_id}/consents", json={"key": key, "choice": choice})
    assert r.status_code == 200, r.text


def test_off_by_default_an_eeoc_question_is_left_to_you(api):
    setup_candidate(api)
    assert api.get("/profile/self-identification").json() == {
        "enabled": False,
        "labels": [],
        "updated_at": None,
    }
    r, _ = row(api, [GENDER], "gender")  # optional: left blank, not auto-filled
    assert r["status"] == "blank_optional" and r["sensitive"] is True and r["value"] is None
    req, _ = row(api, [GENDER_REQ], "g2")  # required: a checkpoint for you
    assert req["status"] == "needs_user" and req["value"] is None


def test_enabled_fills_a_single_select_exact_choice_with_a_dependency_ref(api):
    setup_candidate(api)
    set_self_id(api, True, ["Male", "Asian", "White"])
    g, _ = row(api, [GENDER], "gender")
    assert (g["status"], g["source"], g["display"]) == ("resolved", "self_identification", "Male")
    assert g["sensitive"] is True and g["bankable"] is False
    # The established dependency: the answer references the self-identification record, so
    # changing or disabling the labels that produced it invalidates an approval of it.
    assert g["fact_refs"] == [
        {"type": "self_identification", "id": g["fact_refs"][0]["id"], "field": "labels",
         "value": ["Male"]}
    ]  # fmt: skip
    # Never saved to the answer bank (sensitive).
    assert api.get("/answer-bank").json() == []


def test_a_multi_select_with_a_partial_match_is_a_checkpoint_not_a_partial_answer(api):
    # The owner cannot prove, from a flat label list, that a multi-answer set is complete, so a
    # partial self-identification is never submitted: the owner answers it.
    setup_candidate(api)
    set_self_id(api, True, ["Asian", "White"])
    rc, _ = row(api, [RACE], "race")
    assert rc["status"] == "blank_optional"  # optional -> left for the owner
    assert rc["value"] is None and rc["source"] != "self_identification"


def test_a_decline_choice_fills_the_forms_decline_option(api):
    setup_candidate(api)
    set_self_id(api, True, ["Decline To Self Identify"])
    g, _ = row(api, [GENDER], "gender")
    assert g["status"] == "resolved" and g["display"] == "Decline To Self Identify"


def test_decline_on_a_multi_select_fills_only_the_decline_option(api):
    # Decline is exclusive and complete, so a multi-select decline is unambiguous.
    setup_candidate(api)
    set_self_id(api, True, ["Decline To Self Identify"])
    rc, _ = row(api, [RACE], "race")
    assert rc["status"] == "resolved" and rc["source"] == "self_identification"
    assert [o["label"] for o in rc["value"]["options"]] == ["Decline To Self Identify"]


def test_decline_mixed_with_a_substantive_choice_is_a_checkpoint(api):
    # Declining and naming a race contradict; never send both.
    setup_candidate(api)
    set_self_id(api, True, ["Asian", "Decline To Self Identify"])
    rc, _ = row(api, [RACE], "race")
    assert rc["value"] is None and rc["source"] != "self_identification"


def test_a_per_application_withhold_overrides_standing_self_id(api):
    # The standing preference never replaces an explicit per-application disclosure choice.
    setup_candidate(api)
    set_self_id(api, True, ["Male"])
    app_id = application(api, [GENDER_REQ])
    consent(api, app_id, "g2", "withhold")
    g = rows(package(api, app_id))["g2"]
    assert g["source"] != "self_identification"  # not "Male"
    assert g["display"] == "Decline To Self Identify"  # the form's own decline option


def test_disabling_self_id_turns_a_filled_question_back_into_a_checkpoint(api):
    # Disabling (or changing) the preference re-resolves the question: the answer is no longer
    # produced, so any approval bound to it is invalidated by the package's content hash.
    setup_candidate(api)
    set_self_id(api, True, ["Male"])
    g, _ = row(api, [GENDER_REQ], "g2")
    assert g["status"] == "resolved" and g["source"] == "self_identification"
    set_self_id(api, False, ["Male"])
    g2, _ = row(api, [GENDER_REQ], "g2")
    assert g2["status"] == "needs_user" and g2["source"] != "self_identification"


def test_no_exact_match_stays_a_checkpoint(api):
    setup_candidate(api)
    set_self_id(api, True, ["Nonbinary"])  # not an option on this form
    g, _ = row(api, [GENDER_REQ], "g2")  # required: a checkpoint, never guessed
    assert (
        g["status"] == "needs_user" and g["value"] is None and g["source"] != "self_identification"
    )


def test_an_ambiguous_single_choice_is_never_guessed(api):
    setup_candidate(api)
    set_self_id(api, True, ["Male", "Female"])  # two options match one single-select
    g, _ = row(api, [GENDER_REQ], "g2")
    assert g["status"] == "needs_user" and g["value"] is None  # never one-of-two


def test_a_label_never_lands_on_the_wrong_question(api):
    setup_candidate(api)
    set_self_id(api, True, ["Male"])  # "Male" is not a race option
    rc, _ = row(api, [RACE], "race")  # optional: left blank, not "Male"
    assert rc["value"] is None and rc["source"] != "self_identification"


def test_each_account_has_its_own_and_another_sees_nothing(api, other_api):
    setup_candidate(api)
    setup_candidate(other_api)
    set_self_id(api, True, ["Male"])
    assert other_api.get("/profile/self-identification").json()["enabled"] is False
    g, _ = row(other_api, [GENDER_REQ], "g2")
    assert g["status"] == "needs_user"  # the other account's self-ID never applies here
