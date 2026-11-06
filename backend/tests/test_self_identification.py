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


def _choice(key, label, options, required=True, typ="select"):
    opts = [{"value": str(i), "label": o} for i, o in enumerate(options, 1)]
    return {"key": key, "label": label, "type": typ, "required": required, "options": opts}


def test_i_dont_wish_to_self_identify_declines_only_where_the_options_name_a_category(api):
    """D133: "I don't wish to self-identify" is a decline option. It answers an EEO question
    whose other options name a category, never a Yes/No question and never a question that is
    not self-identification (a felony question offering it stays yours)."""
    setup_candidate(api)
    wish = "I don't wish to self-identify"
    set_self_id(api, True, [wish])
    g, _ = row(api, [_choice("gender", "Gender", ["Male", "Female", wish], required=False)],
               "gender")  # fmt: skip
    assert (g["status"], g["source"], g["display"]) == ("resolved", "self_identification", wish)
    h, _ = row(api, [_choice("hisp", "Are you Hispanic or Latino?", ["Yes", "No", wish])],
               "hisp")  # fmt: skip
    assert h["status"] == "needs_user" and h["value"] is None
    fel, _ = row(api, [_choice("felony", "Have you ever been convicted of a felony?",
                               ["Yes", "No", wish])], "felony")  # fmt: skip
    assert fel["status"] == "needs_user" and fel["source"] != "self_identification"
    race = _choice("race", "Race / Ethnicity", ["Asian", "White", "Black or African American",
                   wish], required=False, typ="multiselect")  # fmt: skip
    rc, _ = row(api, [race], "race")
    assert rc["status"] == "resolved" and rc["source"] == "self_identification"
    assert [o["label"] for o in rc["value"]["options"]] == [wish]


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


# D131: what your self-identification may answer, and with which options. Fictional questions;
# the option labels are the standard public EEOC wordings.
def _select(key, label, *labels, required=True):
    options = [{"value": str(i), "label": x} for i, x in enumerate(labels)]
    return {"key": key, "label": label, "type": "select", "required": required, "options": options}


FELONY = _select("felony", "Have you ever been convicted of a felony?", "Yes", "No")
ACCOMMODATION = _select(
    "accommodation", "Will you require a reasonable accommodation for the interview?", "Yes", "No"
)
MARRIED = _select("married", "Are you married?", "Yes", "No")
MILITARY = _select("military", "Have you served in the military?", "Yes", "No")
AGE = _select("age", "How old are you?", "18-24", "25-34")
HISPANIC = _select("hispanic", "Are you Hispanic/Latino?", "Yes", "No", "Decline To Self Identify")
DISABILITY = _select(
    "disability",
    "Disability status",
    "Yes, I have a disability, or have had one in the past",
    "No, I do not have a disability and have not had one in the past",
    "I do not want to answer",
)
VETERAN = _select(
    "veteran",
    "Veteran status",
    "I identify as one or more of the classifications of protected veteran",
    "I am not a protected veteran",
    "I don't wish to answer",
)


def test_self_identification_never_answers_a_question_outside_its_categories(api):
    # The defect D131 fixes: with "No" among your labels, a criminal-history or accommodation
    # question was answered "No" from your self-identification. Only the EEO self-identification
    # categories are answered from it; every other sensitive question is yours, whatever matches.
    setup_candidate(api)
    set_self_id(api, True, ["Male", "No", "25-34"])
    got = rows(package(api, application(api, [FELONY, ACCOMMODATION, MARRIED, MILITARY, AGE])))
    for key in ("felony", "accommodation", "married", "military", "age"):
        r = got[key]
        assert r["sensitive"] is True, key
        assert (r["status"], r["value"]) == ("needs_user", None), (key, r)
        assert r["source"] != "self_identification" and r["fact_refs"] == [], key


def test_a_bare_yes_or_no_label_answers_no_question(api):
    # A flat list of labels cannot say which question a bare "No" answered, so even an EEO
    # question whose options are only Yes, No and a decline (Hispanic or Latino) is yours.
    setup_candidate(api)
    set_self_id(api, True, ["No"])
    req, _ = row(api, [HISPANIC], "hispanic")
    assert (req["status"], req["value"], req["source"]) == ("needs_user", None, "unresolved")
    assert "names no category" in req["explanation"]
    opt, _ = row(api, [HISPANIC | {"required": False}], "hispanic")
    assert (opt["status"], opt["value"]) == ("blank_optional", None)
    assert "names no category" in opt["explanation"]


def test_a_bare_label_never_turns_into_a_decline(api):
    # "No" and the decline both match: that is not a decline you chose for this question.
    setup_candidate(api)
    set_self_id(api, True, ["No", "Decline To Self Identify"])
    r, _ = row(api, [HISPANIC], "hispanic")
    assert (r["status"], r["value"]) == ("needs_user", None)


def test_labels_that_name_their_category_still_answer_their_own_questions(api):
    setup_candidate(api)
    set_self_id(
        api,
        True,
        [
            "No, I do not have a disability and have not had one in the past",
            "I am not a protected veteran",
            "Male",
        ],
    )
    got = rows(package(api, application(api, [DISABILITY, VETERAN, GENDER, FELONY])))
    for key, shown in (
        ("disability", "No, I do not have a disability and have not had one in the past"),
        ("veteran", "I am not a protected veteran"),
        ("gender", "Male"),
    ):
        assert (got[key]["status"], got[key]["source"]) == ("resolved", "self_identification"), key
        assert got[key]["display"] == shown, key
    assert got["felony"]["source"] != "self_identification"


def test_a_question_that_also_names_another_sensitive_topic_is_yours(api):
    # An EEO word in the label ("sex", "disability") does not make a criminal-history or an
    # accommodation question a self-identification one, even for a decline.
    setup_candidate(api)
    set_self_id(api, True, ["Prefer not to say", "I don't wish to answer"])
    offender = _select("offender", "Are you required to register as a sex offender?", "Yes", "No",
                       "Prefer not to say")  # fmt: skip
    accom = _select("accom", "Do you have a disability that requires a reasonable accommodation "
                    "during the interview?", "Yes", "No", "I don't wish to answer")  # fmt: skip
    got = rows(package(api, application(api, [offender, accom])))
    for key in ("offender", "accom"):
        assert (got[key]["status"], got[key]["value"]) == ("needs_user", None), key
        assert got[key]["source"] != "self_identification", key


def test_options_alone_never_make_a_question_self_identification(api):
    # "White" is your race label, not a uniform colour; a decline option does not make a
    # caregiver question one either. A self-identification section does.
    setup_candidate(api)
    set_self_id(api, True, ["Male", "White", "I don't wish to answer"])
    colour = _select("colour", "Which uniform colour would you prefer?", "Black", "White", "Navy")
    carer = _select(
        "carer", "Are you a parent or caregiver?", "Yes", "No", "I don't wish to answer"
    )
    race = _select("race_s", "Please select", "Asian", "White", "Two or More Races")
    race_in_section = race | {"key": "race_v", "step": "Voluntary Self-Identification"}
    got = rows(package(api, application(api, [colour, carer, race, race_in_section])))
    for key in ("colour", "carer", "race_s"):
        assert got[key]["source"] != "self_identification" and got[key]["value"] is None, key
    assert (got["race_v"]["source"], got["race_v"]["display"]) == ("self_identification", "White")


def test_a_decline_is_taken_only_where_the_other_options_name_a_category(api):
    # On Yes / No / decline nothing says which question your decline was for; on Gender it does.
    setup_candidate(api)
    set_self_id(api, True, ["Decline To Self Identify"])
    got = rows(package(api, application(api, [HISPANIC, GENDER_REQ])))
    assert (got["hispanic"]["status"], got["hispanic"]["value"]) == ("needs_user", None)
    assert (got["g2"]["source"], got["g2"]["display"]) == (
        "self_identification",
        "Decline To Self Identify",
    )


def test_a_follow_up_is_never_answered_from_self_identification(api):
    setup_candidate(api)
    set_self_id(api, True, ["I don't wish to answer"])
    crime = _select("crime", "Have you ever been convicted of a crime?", "Yes", "No")
    offense = _select(
        "offense", "What was the offense?", "Theft", "Assault", "I don't wish to answer"
    ) | {"condition": {"key": "crime", "any_of": ["0"]}}
    app_id = application(api, [crime, offense])
    r = api.put(f"/applications/{app_id}/answers", json={"key": "crime", "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    got = rows(package(api, app_id))
    assert got["offense"]["source"] != "self_identification" and got["offense"]["value"] is None
