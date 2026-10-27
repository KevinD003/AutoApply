"""Unit tests for deterministic question resolution. Synthetic facts; no database, no LLM."""

from types import SimpleNamespace as NS

import pytest

from app.modules.preparation.classify import classify
from app.modules.preparation.fixtures_registry import fixture_html
from app.modules.preparation.forms import FieldType, FormField, Option, extract_form_schema
from app.modules.preparation.resolver import Context, question_key, resolve_field
from app.modules.profiles.models import Approval, TriState

YES_NO = [Option(value="1", label="Yes"), Option(value="0", label="No")]


def radio(label, key="q", options=YES_NO, required=True, help_text=None):
    return FormField(
        key=key,
        label=label,
        type=FieldType.radio,
        options=options,
        required=required,
        help_text=help_text,
    )


def auth(country="US", authorized="unknown", now="unknown", future="unknown", approved=True):
    return NS(
        id="wa-" + country,
        version=1,
        country_code=country,
        authorized=TriState(authorized),
        sponsorship_needed_now=TriState(now),
        sponsorship_needed_future=TriState(future),
        approval_status=Approval.approved if approved else Approval.proposed,
    )


def profile(**kw):
    base = dict(
        id="p1",
        version=1,
        approval_status=Approval.approved,
        given_name=None,
        family_name=None,
        full_name=None,
        preferred_name=None,
        contact_email=None,
        phone=None,
        residence_city=None,
        residence_region=None,
        residence_country=None,
        links=[],
        skills=[],
        summary=None,
    )
    return NS(**(base | kw))


def ctx(**kw):
    return Context(**kw)


def test_authorization_yes_maps_to_yes_option():
    r = resolve_field(
        radio("Are you legally authorized to work in the United States?"),
        ctx(work_auth={"US": auth(authorized="yes")}),
    )
    assert (r.status, r.source, r.display) == ("resolved", "deterministic_mapping", "Yes")
    assert r.fact_refs[0]["field"] == "authorized"


def test_unknown_or_unapproved_facts_never_resolve():
    q = radio("Are you legally authorized to work in the United States?")
    assert resolve_field(q, ctx()).status == "needs_user"
    assert (
        resolve_field(q, ctx(work_auth={"US": auth(authorized="unknown")})).status == "needs_user"
    )
    # A fact proposed by resume parsing is not used until the user approves it.
    r = resolve_field(q, ctx(work_auth={"US": auth(authorized="yes", approved=False)}))
    assert r.status == "needs_user"


def test_authorization_in_another_country_is_not_used():
    r = resolve_field(
        radio("Are you legally authorized to work in the United States?"),
        ctx(work_auth={"CA": auth("CA", authorized="yes")}),
    )
    assert r.status == "needs_user"


@pytest.mark.parametrize(
    "label,now,future,expected",
    [
        (
            "Will you now or in the future require sponsorship to work in the US?",
            "no",
            "yes",
            "Yes",
        ),
        ("Will you now or in the future require sponsorship to work in the US?", "no", "no", "No"),
        (
            "Will you now or in the future require sponsorship to work in the US?",
            "no",
            "unknown",
            None,
        ),
        ("Do you currently require visa sponsorship to work in the US?", "no", "yes", "No"),
        ("Do you require sponsorship to work in the US?", "yes", "no", "Yes"),
        ("Will you require visa sponsorship in the US in the future?", "no", "yes", "Yes"),
        ("Will you require visa sponsorship in the US in the future?", "yes", "no", "No"),
    ],
)
def test_sponsorship_timeframes(label, now, future, expected):
    r = resolve_field(radio(label), ctx(work_auth={"US": auth(now=now, future=future)}))
    if expected is None:
        assert r.status == "needs_user"
    else:
        assert (r.status, r.display) == ("resolved", expected), r.explanation


def test_negated_sponsorship_question_inverts_answer():
    q = radio("Do you not require sponsorship to work in Canada?")
    r = resolve_field(q, ctx(work_auth={"CA": auth("CA", now="no")}))
    assert (r.status, r.display) == ("resolved", "Yes")
    assert "negated" in r.explanation
    r = resolve_field(q, ctx(work_auth={"CA": auth("CA", now="yes")}))
    assert r.display == "No"


def test_double_negation_or_odd_negation_asks_user():
    for label in (
        "Is it not true that you do not require sponsorship in the US?",
        "Are you never going to need visa sponsorship in the US, now or in the future?",
    ):
        r = resolve_field(radio(label), ctx(work_auth={"US": auth(now="no", future="no")}))
        assert r.status == "needs_user", label


def test_without_sponsorship_needs_both_facts():
    q = radio("Are you authorized to work in Canada without sponsorship?")
    yes = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes", now="no")}))
    assert yes.display == "Yes"
    no = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes", now="yes")}))
    assert no.display == "No"
    unk = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes")}))
    assert unk.status == "needs_user"


def test_vague_or_country_less_questions_need_user():
    w = {"US": auth(authorized="yes", now="no", future="no")}
    for label in (
        "Will you require sponsorship?",
        "Are you legally eligible to work in the country where this job is located?",
        "Are you authorized to work in the US or Canada?",
        "Are you authorized to work in the US and will you require sponsorship?",
    ):
        assert resolve_field(radio(label), ctx(work_auth=w)).status == "needs_user", label


def test_option_mismatch_is_not_guessed():
    q = radio(
        "What is your work authorization status in the United States?",
        options=[
            Option(value="c", label="U.S. citizen or permanent resident"),
            Option(value="v", label="Visa holder"),
        ],
    )
    r = resolve_field(q, ctx(work_auth={"US": auth(authorized="yes")}))
    assert r.status == "needs_user"
    # Yes/No question whose options are not a clean pair.
    q2 = radio(
        "Are you legally authorized to work in the United States?",
        options=[
            Option(value="a", label="Yes"),
            Option(value="b", label="Yes, with visa"),
            Option(value="c", label="Maybe"),
        ],
    )
    assert resolve_field(q2, ctx(work_auth={"US": auth(authorized="yes")})).status == "needs_user"


def test_residence_and_target_location_stay_separate():
    prefs = NS(
        id="pr",
        willing_to_relocate=TriState.yes,
        salary_min=None,
        target_locations=[{"city": "Toronto", "country": "CA"}],
    )
    city = FormField(key="city", label="Location (City)", type=FieldType.text, required=True)
    r = resolve_field(city, ctx(profile=profile(), prefs=prefs))
    assert r.status == "needs_user"  # residence unknown; target city never used
    r = resolve_field(city, ctx(profile=profile(residence_city="Lagos"), prefs=prefs))
    assert (r.source, r.display) == ("profile_fact", "Lagos")
    pref_q = FormField(
        key="pl",
        label="Preferred work location",
        type=FieldType.select,
        required=True,
        options=[Option(value="t", label="Toronto")],
    )
    assert (
        resolve_field(pref_q, ctx(profile=profile(residence_city="Lagos"), prefs=prefs)).status
        == "needs_user"
    )


def test_country_select_mapping():
    q = FormField(
        key="c",
        label="Country of residence",
        type=FieldType.select,
        required=True,
        options=[
            Option(value="ca", label="Canada"),
            Option(value="us", label="United States of America"),
        ],
    )
    r = resolve_field(q, ctx(profile=profile(residence_country="US")))
    assert (r.source, r.display) == ("deterministic_mapping", "United States of America")
    r = resolve_field(q, ctx(profile=profile(residence_country="IN")))
    assert r.status == "needs_user"


def test_acknowledgments_are_never_checked_automatically():
    box = FormField(
        key="ack",
        label="I have read and agree to the privacy notice.",
        type=FieldType.checkbox,
        required=True,
    )
    assert resolve_field(box, ctx()).status == "needs_consent"
    assert resolve_field(box, ctx(consents={"ack": "decline"})).status == "needs_consent"
    r = resolve_field(box, ctx(consents={"ack": "agree"}))
    assert (r.status, r.value) == ("resolved", {"checked": True})
    bg = radio("Do you consent to a background check?", key="bg")
    assert resolve_field(bg, ctx()).status == "needs_consent"


def test_sensitive_needs_answer_and_disclosure_consent():
    q = FormField(
        key="g",
        label="Gender",
        type=FieldType.select,
        required=False,
        options=[Option(value="w", label="Woman"), Option(value="d", label="Decline")],
    )
    assert resolve_field(q, ctx()).status == "blank_optional"
    inp = NS(value={"option": "w", "label": "Woman"}, provenance="user_entered")
    r = resolve_field(q, ctx(inputs={"g": inp}))
    assert r.status == "needs_consent"
    assert resolve_field(q, ctx(inputs={"g": inp}, consents={"g": "disclose"})).status == "resolved"
    assert (
        resolve_field(q, ctx(inputs={"g": inp}, consents={"g": "withhold"})).status
        == "blank_optional"
    )


def test_answer_bank_reuse_requires_same_wording_and_options():
    q = FormField(
        key="e",
        label="Highest level of education completed",
        type=FieldType.select,
        required=True,
        options=[
            Option(value="1", label="High school diploma"),
            Option(value="2", label="Bachelor's degree"),
        ],
    )
    entry = NS(
        id="b1",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Bachelor's degree"]},
        options_snapshot=["bachelor's degree", "high school diploma"],
    )
    r = resolve_field(q, ctx(bank={question_key(q): entry}))
    assert (r.source, r.display) == ("answer_bank", "Bachelor's degree")
    reworded = q.model_copy(
        update={"label": "What is the highest level of education you have completed?"}
    )
    assert resolve_field(reworded, ctx(bank={question_key(q): entry})).status == "needs_user"
    changed = q.model_copy(update={"options": q.options + [Option(value="3", label="Doctorate")]})
    r = resolve_field(changed, ctx(bank={question_key(changed): entry}))
    assert r.status == "needs_user" and "options have changed" in r.explanation
    # C6 (D51): a question about the employer or the job never takes a saved answer.
    hear = FormField(
        key="h",
        label="How did you hear about this job?",
        type=FieldType.select,
        required=True,
        options=[Option(value="1", label="Referral"), Option(value="2", label="Job board")],
    )
    saved = NS(
        id="b3",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Referral"]},
        options_snapshot=["job board", "referral"],
    )
    r = resolve_field(hear, ctx(bank={question_key(hear): saved}))
    assert (r.status, r.source, r.bankable) == ("needs_user", "unresolved", False)


def test_yes_no_bank_answers_are_bound_to_their_question():
    """A saved 'Yes' to one question is never reused for a differently worded one."""
    asked = radio("Do you have a driver's license?", key="dl")
    entry = NS(
        id="b2",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Yes"]},
        options_snapshot=["no", "yes"],
    )
    bank = {question_key(asked): entry}
    assert resolve_field(asked, ctx(bank=bank)).display == "Yes"
    negated = radio("Do you not have a driver's license?", key="dl2")
    assert resolve_field(negated, ctx(bank=bank)).status == "needs_user"
    # C6 (D51): "valid" is about now, so the answer is never reused, even under its own key.
    valid = radio("Do you have a valid driver's license?", key="dl3")
    r = resolve_field(valid, ctx(bank={question_key(valid): entry}))
    assert (r.status, r.source, r.bankable) == ("needs_user", "unresolved", False)


def test_names_are_not_split_from_full_name():
    first = FormField(key="fn", label="First Name", type=FieldType.text, required=True)
    r = resolve_field(first, ctx(profile=profile(full_name="Ada Lovelace")))
    assert r.status == "needs_user"
    r = resolve_field(first, ctx(profile=profile(given_name="Ada")))
    assert (r.source, r.display) == ("profile_fact", "Ada")


def test_long_form_is_unresolved_without_draft():
    q = FormField(key="why", label="Why do you want to work here?", type=FieldType.textarea)
    r = resolve_field(q, ctx())
    assert r.status == "blank_optional" and r.draftable


def test_fixture_classification_table():
    """Every question in the tricky fixture lands where we expect."""
    schema = extract_form_schema(fixture_html("tricky"))
    got = {f.key: (classify(f).kind, classify(f).ambiguity is not None) for f in schema.fields}
    assert got["ca_auth_without"] == ("authorized_without_sponsorship", False)
    assert got["ca_sponsor_negated"] == ("sponsorship", False)
    assert got["ca_sponsor_future"] == ("sponsorship", False)
    assert got["sponsor_vague"][1] is True
    assert got["eligible_here"][1] is True
    assert got["us_status"] == ("authorization_status", True)
    assert got["preferred_location"] == ("location_preference", True)
    assert got["background_check"][0] == "acknowledgment"
    assert got["veteran"][0] == "demographic"
    assert got["residence_country"] == ("residence_country", False)
