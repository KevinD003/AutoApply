"""C6 (D51): which answers are saved for reuse, under which key, and what a saved answer may
answer. Pure: no database, no LLM. The wording table is tests/bank_scope_wordings.json
(fictional employers only): its verdicts were adjudicated from three designs and held-out
wordings, then probed; the category of a row never reused is the message it gets."""

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.modules.preparation import bankscope
from app.modules.preparation import package as pk
from app.modules.preparation.classify import Intent, classify
from app.modules.preparation.forms import Condition, FieldType, FormField, Option, normalize
from app.modules.preparation.resolver import (
    NO_BANK,
    SCOPE_EXPLANATION,
    Context,
    _base,
    option_labels,
    question_key,
    resolve_field,
    saved_answer_scope,
)
from app.modules.profiles.models import Approval, SalaryPeriod, TriState

T = FieldType
ROWS = [
    tuple(r) for r in json.loads(Path(__file__).with_name("bank_scope_wordings.json").read_text())
]
# Stable by meaning, refused on purpose (narrowing: the user answers again). Widening any of
# these is a decision, not a fix: it needs its own reason in D51 and a probe against HEAD.
ACCEPTED_OVER_NARROWING = {
    "time.is_your_portfolio_available_online",
    "time.have_you_ever_worked_at_night",
    "time.do_you_have_experience_with_night_",
    "employer.are_you_able_to_work_as_part_of_th",
    "time.are_you_physically_active",
    "place.which_countries_have_you_lived_in",
    "time.do_you_have_experience_with_night__2",
    "employer.what_should_we_call_you",
}
EDU = "Highest level of education completed"
EDU_HELP = "Choose the highest level you have finished."
VALUES = {
    "url": {"text": "https://example.com/profile"},
    "email": {"text": "sam.synthetic@example.com"},
    "tel": {"text": "+1 555 0100"},
    "number": {"number": 1},
    "date": {"date": "2026-11-02"},
    "checkbox": {"checked": True},
}


def O(*labels):  # noqa: E743 - options, as in the table
    return [Option(value=str(i), label=x) for i, x in enumerate(labels)]


def field(label, typ="radio", options=(), help_text=None, step=None, key="q", **kw):
    return FormField(
        key=key,
        label=label,
        type=T(typ),
        options=O(*options),
        help_text=help_text,
        step=step,
        required=kw.pop("required", True),
        **kw,
    )


def entry(f, *, key=None, help_text="", sensitive=False, value=None):
    """An approved saved answer for `f`, stored as _save_to_bank stores it (C6 key, help text)."""
    if value is None:
        value = (
            {"labels": [f.options[0].label]}
            if f.options
            else VALUES.get(f.type.value, {"text": "Synthetic answer"})
        )
    e = NS(
        id="b-" + f.key,
        version=1,
        approval_status=Approval.approved,
        value=value,
        options_snapshot=option_labels(f),
        sensitive=sensitive,
    )
    if help_text is not None:  # None: a row saved before C6 (no help text recorded)
        e.help_text = help_text
    return {key or question_key(f): e}


def table_field(label, typ, opts, help_, step):
    return field(label, typ, opts, help_, step)


IDS = [r[0] for r in ROWS]
assert len(IDS) == len(set(IDS)), "row ids must be unique"


@pytest.mark.parametrize(("rid", "label", "typ", "opts", "help_", "step", "exp"), ROWS, ids=IDS)
def test_bank_scope_table(rid, label, typ, opts, help_, step, exp):
    """A row C6 never reuses is never bankable and never answered from an approved saved answer
    stored under its own key; a row that stays reusable is answered from it."""
    f = table_field(label, typ, opts, help_, step)
    r = resolve_field(f, Context(bank=entry(f, help_text=f.help_text or "")))
    if exp == "head":  # never reused before C6 either
        assert not r.bankable and r.source != "answer_bank", (r.status, r.source)
        return
    code = bankscope.refusal_code(f, classify(f))
    assert code == exp, (code, r.explanation)
    if exp is None:
        assert r.bankable and r.source == "answer_bank", (r.status, r.source, r.explanation)
    else:
        assert not r.bankable and r.source != "answer_bank", (r.status, r.source)


def test_accepted_over_narrowing_is_listed_and_still_refused():
    by_id = {r[0]: r for r in ROWS}
    for rid in ACCEPTED_OVER_NARROWING:
        assert by_id[rid][6] not in (None, "head"), rid


NEVER = re.compile(r"(?!x)x")
# One row per family use that only that use catches: switching the use off must make the row
# reusable (so no family is dead code). Probed with judge/family_m.py (D51).
ONLY = {
    ("LABEL", "P_PAY"): "pay.compensation_expectations",
    ("LABEL", "L_PLACE"): "place.will_you_need_relocation_accommoda",
    ("LABEL", "E_DEIXIS"): "employer.do_you_understand_the_physical_dem",
    ("LABEL", "E_WE"): "employer.which_of_our_values_matters_most_t",
    ("LABEL", "E_HERE"): "employer.is_a_job_here_your_first_choice",
    ("LABEL", "E_PRIOR"): "employer.have_you_worked_for_northwind_exam",
    ("LABEL", "E_RELATION"): "employer.are_you_eligible_for_rehire",
    ("LABEL", "E_SOURCE"): "employer.who_referred_you",
    ("LABEL", "E_PEOPLE"): "employer.do_any_of_your_relatives_work_for_",
    ("LABEL", "E_FIT"): "employer.do_you_have_relevant_experience",
    ("LABEL", "E_IDS"): "employer.job_reference_number",
    ("LABEL", "E_PROCESS"): "employer.can_you_attend_an_orientation_sess",
    ("LABEL", "E_APPLY"): "employer.position_applied_for",
    ("LABEL", "T_START"): "time.can_you_start_immediately",
    ("LABEL", "T_SCHEDULE"): "time.can_you_work_weekends",
    ("LABEL", "T_DURATION"): "time.years_of_experience",
    ("LABEL", "T_VALID"): "time.do_you_have_valid_first_aid_training",
    ("LABEL", "T_STUDY"): "time.have_you_graduated",
    ("LABEL", "T_NOW"): "time.who_is_your_current_employer",
    ("LABEL", "T_HISTORY"): "time.job_title",
    ("LABEL", "T_WHEN"): "time.date_2",
    ("LABEL", "E_WILLING"): "employer.would_you_like_to_receive_text_mes",
    ("HELP", "P_PAY"): "pay.expectations",
    ("HELP", "L_PLACE"): "place.can_you_operate_a_pallet_jack",
    ("HELP", "E_DEIXIS"): "employer.do_you_have_experience_with_patien",
    ("HELP", "E_PRIOR"): "employer.any_comments",
    ("HELP", "E_RELATION"): "employer.your_status",
    ("HELP", "E_SOURCE"): "employer.channel_2",
    ("HELP", "E_PEOPLE"): "employer.connections",
    ("HELP", "E_FIT"): "employer.experience_3",
    ("HELP", "E_IDS"): "employer.code_2",
    ("HELP", "E_PROCESS"): "employer.format",
    ("HELP", "T_START"): "time.timing_2",
    ("HELP", "T_SCHEDULE"): "time.pattern",
    ("HELP", "T_DURATION"): "time.experience",
    ("HELP", "T_VALID"): "time.can_you_operate_a_pallet_jack",
    ("HELP", "T_STUDY"): "time.education",
    ("OPTIONS", "P_PAY"): "pay.what_range_are_you_targeting",
    ("OPTIONS", "O_PLACE"): "place.your_setup",
    ("OPTIONS", "E_RELATION"): "employer.relationship_2",
    ("OPTIONS", "E_SOURCE"): "employer.channel",
    ("OPTIONS", "O_START"): "time.timing",
    ("OPTIONS", "T_SCHEDULE"): "time.employment_type",
    ("OPTIONS", "O_DURATION"): "time.clinical_experience",
    ("OPTIONS", "T_VALID"): "time.first_aid_training",
    ("OPTIONS", "T_NOW"): "time.your_situation",
}
BY_ID = {r[0]: r for r in ROWS}


def _verdict(rid):
    _, label, typ, opts, help_, step, _ = BY_ID[rid]
    f = table_field(label, typ, opts, help_, step)
    return bankscope.refusal_code(f, classify(f))


@pytest.mark.parametrize(("where", "name"), sorted(ONLY), ids=[f"{a}:{b}" for a, b in sorted(ONLY)])
def test_every_family_use_is_load_bearing(where, name):
    rid = ONLY[(where, name)]
    assert _verdict(rid) is not None
    uses = getattr(bankscope, where)
    pat = getattr(bankscope, name)
    n = next(i for i, (_, p) in enumerate(uses) if p is pat)
    saved = uses[n]
    uses[n] = (saved[0], NEVER)
    try:
        assert _verdict(rid) is None, rid
    finally:
        uses[n] = saved


@pytest.mark.parametrize(
    ("attr", "replacement", "rid"),
    [
        ("S_STEP", NEVER, "section.amount"),
        ("_has_us", lambda raw: False, "employer.anything_else_you_want_us_to_know"),
        ("fact_words", lambda text: False, "fact.i_am_permitted_to_work_in_germany"),
    ],
)
def test_the_section_us_and_fact_rules_are_load_bearing(monkeypatch, attr, replacement, rid):
    assert _verdict(rid) is not None
    monkeypatch.setattr(bankscope, attr, replacement)
    assert _verdict(rid) is None


def test_a_date_answer_is_never_reused():
    f = field("Signed on", "date")
    assert bankscope.refusal_code(f, classify(f)) == "time"
    assert (
        bankscope.refusal_code(field("Signed on", "text"), classify(field("Signed on", "text")))
        is None
    )


def test_question_key_without_help_text_is_unchanged():
    """The formula before C6, literally: no saved answer is re-keyed (D51)."""
    f = field(EDU, "select", ["High school diploma", "Bachelor's degree"])
    old = hashlib.sha256(f"{normalize(f.label)}|choice".encode()).hexdigest()
    assert question_key(f) == old
    assert old == "f710066914ce03f195f45d8494bf7e36a573a679a2f44c22a9bda5599eb6e53b"


def test_question_key_with_help_text_is_bound_and_unambiguous():
    f = field(EDU, "select", ["High school diploma", "Bachelor's degree"], help_text=EDU_HELP)
    assert question_key(f) == "8bdbcc0b247722c20e0fd44b55512165698a9e7716eac8902eb8e155301d4baf"
    other = f.model_copy(update={"help_text": "Choose the highest level you have started."})
    none = f.model_copy(update={"help_text": None})
    assert len({question_key(f), question_key(other), question_key(none)}) == 3
    cosmetic = f.model_copy(update={"help_text": "  CHOOSE the highest level you have   finished "})
    assert question_key(cosmetic) == question_key(f)
    pipe = field("x|text", "text")
    assert question_key(pipe) != question_key(field("x", "text", help_text="text"))


def test_a_saved_answer_needs_the_same_help_text():
    f = field(EDU, "select", ["High school diploma", "Bachelor's degree"], help_text=EDU_HELP)
    bank = entry(f, help_text=EDU_HELP)
    assert resolve_field(f, Context(bank=bank)).source == "answer_bank"
    cosmetic = f.model_copy(update={"help_text": EDU_HELP.upper() + "  "})
    assert resolve_field(cosmetic, Context(bank=bank)).source == "answer_bank"
    for other in ("Choose the highest level you have started.", None):
        g = f.model_copy(update={"help_text": other})
        r = resolve_field(g, Context(bank=bank))
        assert (r.status, r.source) == ("needs_user", "unresolved"), other


def test_an_entry_saved_before_c6_answers_only_a_question_without_help_text():
    plain = field(EDU, "select", ["High school diploma", "Bachelor's degree"])
    legacy = entry(plain, help_text=None)  # no help text attribute, the key before C6
    assert resolve_field(plain, Context(bank=legacy)).source == "answer_bank"
    helped = plain.model_copy(update={"help_text": EDU_HELP})
    r = resolve_field(helped, Context(bank=legacy))
    assert (r.status, r.source) == ("needs_user", "unresolved")


def test_from_bank_checks_the_stored_help_text():
    """Defense in depth: an entry found under the field's own key but recorded for other help
    text answers nothing."""
    f = field(EDU, "select", ["High school diploma", "Bachelor's degree"], help_text=EDU_HELP)
    r = resolve_field(f, Context(bank=entry(f, help_text="Something else entirely")))
    assert (r.status, r.source) == ("needs_user", "unresolved")
    g = field(EDU, "select", ["High school diploma", "Bachelor's degree"])
    assert (
        resolve_field(g, Context(bank=entry(g, help_text="Recorded help"))).source == "unresolved"
    )


def prefs(**kw):
    base = dict(
        id="pr1",
        willing_to_relocate=TriState.yes,
        salary_min=85000,
        salary_max=95000,
        salary_currency="USD",
        salary_period=SalaryPeriod.year,
        target_locations=[],
    )
    return NS(**(base | kw))


def test_relocation_and_salary_are_never_bankable():
    assert {"relocation", "salary_expectation"} <= NO_BANK
    neutral = field("Q", "radio", ["Yes", "No"])
    for kind in ("relocation", "salary_expectation"):
        assert not _base(neutral, Intent(kind)).bankable, kind
        assert bankscope.refusal_code(neutral, Intent(kind)) == bankscope.KIND_REASON[kind]
    reloc = field("Are you willing to relocate?", "radio", ["Yes", "No"])
    salary = field("Desired annual salary (USD)", "number")
    for f in (reloc, salary):
        for p in (
            None,
            prefs(willing_to_relocate=TriState.unknown, salary_min=None),
            prefs(salary_currency="EUR"),
            prefs(salary_period=SalaryPeriod.month),
        ):
            r = resolve_field(f, Context(prefs=p, bank=entry(f)))
            assert not r.bankable and r.source != "answer_bank", (f.label, p, r.source)
    r = resolve_field(reloc, Context(prefs=prefs(), bank=entry(reloc)))
    assert (r.status, r.source, r.display, r.bankable) == (
        "resolved",
        "deterministic_mapping",
        "Yes",
        False,
    )
    r = resolve_field(salary, Context(prefs=prefs(), bank=entry(salary)))
    assert (r.status, r.source, r.value, r.bankable) == (
        "resolved",
        "deterministic_mapping",
        {"number": 85000.0},
        False,
    )
    r = resolve_field(reloc, Context(bank=entry(reloc)))
    assert r.explanation == "Your preferences do not say whether you would relocate."


def _form(*fields, inputs=None, bank=None):
    ctx = Context(
        bank=bank or {},
        inputs={
            k: NS(value=v, provenance="user_entered", meta=None) for k, v in (inputs or {}).items()
        },
    )
    return {f.key: r for f, r in pk.resolve_answers(list(fields), ctx)}


def test_a_follow_up_of_a_question_that_is_not_reused_is_not_reused():
    child = field("Spanish level", "text", key="lvl", condition=Condition(key="p", any_of=["0"]))
    for parent_label, reused in (
        ("Have you worked for us before?", False),
        ("Do you speak Spanish?", True),
    ):
        parent = field(parent_label, "radio", ["Yes", "No"], key="p")
        bank = entry(child)
        rows = _form(parent, child, inputs={"p": {"option": "0", "label": "Yes"}}, bank=bank)
        assert rows["p"].status == "resolved"  # the follow-up is asked
        r = rows["lvl"]
        if reused:
            assert r.bankable and r.source == "answer_bank"
        else:
            assert not r.bankable and (r.status, r.source) == ("needs_user", "unresolved")
            assert r.explanation == SCOPE_EXPLANATION["followup"]


def test_the_same_wording_twice_on_one_form_is_never_answered_from_the_bank():
    a = field("Languages", "multiselect", ["English", "Spanish"], key="l1")
    b = field("Languages", "multiselect", ["English", "Spanish"], key="l2")
    edu = field(EDU, "select", ["High school diploma", "Bachelor's degree"], key="edu")
    rows = _form(a, b, edu, bank=entry(a) | entry(edu))
    for k in ("l1", "l2"):
        assert not rows[k].bankable and rows[k].source == "unresolved", k
        assert rows[k].explanation == SCOPE_EXPLANATION["repeated"], k
    assert rows["edu"].bankable and rows["edu"].source == "answer_bank"
    rows = _form(a, edu, bank=entry(a))
    assert rows["l1"].source == "answer_bank"  # once on the form: reused


def test_a_question_that_is_not_reused_says_why():
    for label, typ, opts, code in (
        ("How did you hear about this job?", "select", ["Job board", "Referral"], "employer"),
        ("When can you start?", "text", [], "time"),
        ("Expected CTC", "text", [], "pay"),
        ("Street address", "text", [], "place"),
        ("I am based in the U.S.", "radio", ["Yes", "No"], "fact"),
    ):
        r = resolve_field(field(label, typ, opts), Context())
        assert r.explanation == SCOPE_EXPLANATION[code], label
    step = field("Amount", "number", step="Compensation")
    assert resolve_field(step, Context()).explanation == SCOPE_EXPLANATION["section"]


def test_only_rows_c6_narrowed_get_its_explanation():
    generic = field(
        "If yes, please specify", "text", key="g", condition=Condition(key="p", any_of=["0"])
    )
    parent = field("Have you worked for us before?", "radio", ["Yes", "No"], key="p")
    rows = _form(parent, generic)
    assert rows["g"].explanation.startswith(
        "No verified fact or saved answer matches this question."
    )
    where = field("Preferred work location", "select", ["North", "South"])
    assert resolve_field(where, Context()).explanation.startswith("Needs your answer:")
    hear = field("How did you hear about this job?", "select", ["Job board", "Referral"])
    assert resolve_field(hear, Context()).explanation == SCOPE_EXPLANATION["employer"]


def test_identity_and_legacy_eeo_rows_keep_their_policy():
    for label, typ in (
        ("First Name", "text"),
        ("Preferred First Name", "text"),
        ("Last Name", "text"),
        ("Email address", "email"),
        ("Phone", "tel"),
        ("LinkedIn Profile", "url"),
    ):
        f = field(label, typ)
        r = resolve_field(f, Context(bank=entry(f)))
        assert r.bankable and r.source == "answer_bank", label
    for f in (
        field("Gender", "select", ["Woman", "Man"]),
        field("Date of birth", "date"),
        field("I confirm I am 18 years of age or older", "checkbox"),
    ):
        r = resolve_field(f, Context(bank=entry(f)))
        assert r.bankable and (r.status, r.source) == ("needs_consent", "answer_bank"), f.label
    emergency = field("Phone", "tel", step="Emergency contact")
    r = resolve_field(emergency, Context(bank=entry(emergency)))
    assert not r.bankable and r.source != "answer_bank"


PROFILES = {
    "none": None,
    "full": NS(
        id="p1",
        version=1,
        approval_status=Approval.approved,
        given_name="Ann",
        family_name="Lee",
        full_name="Ann Lee",
        preferred_name=None,
        contact_email="ann@example.com",
        phone="+1 555 0100",
        residence_city="Springfield",
        residence_region="Texas",
        residence_country="US",
        links=["https://www.linkedin.com/in/x"],
        skills=[],
        summary=None,
    ),
}
PREFS = {
    "none": None,
    "full": prefs(),
    "unknown": prefs(willing_to_relocate=TriState.unknown, salary_min=None, salary_max=None),
    "eur": prefs(salary_currency="EUR", salary_period=SalaryPeriod.month),
}


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_no_c6_row_is_ever_answered_from_the_bank(profile):
    """Every row C6 never reuses, with every preference state, every consent and every kind of
    saved answer (none, before C6, before C6 sensitive, C6 with the same help text, C6 with
    other help text): never answered from the bank, never bankable."""
    for rid, label, typ, opts, help_, step, exp in ROWS:
        if exp in (None, "head"):
            continue
        f = table_field(label, typ, opts, help_, step)
        legacy_key = hashlib.sha256(f"{normalize(f.label)}|{_shape(f)}".encode()).hexdigest()
        banks = {
            "none": {},
            "legacy": entry(f, key=legacy_key, help_text=None),
            "legacy_sensitive": entry(f, key=legacy_key, help_text=None, sensitive=True),
            "c6_same": entry(f, help_text=f.help_text or ""),
            "c6_other": entry(
                f.model_copy(update={"help_text": "Other help."}), help_text="Other help."
            ),
        }
        for pname, p in PREFS.items():
            for bname, bank in banks.items():
                for consent in (None, "agree", "disclose", "withhold"):
                    ctx = Context(
                        profile=PROFILES[profile],
                        prefs=p,
                        bank=bank,
                        consents={f.key: consent} if consent else {},
                    )
                    r = resolve_field(f, ctx)
                    where = (rid, pname, bname, consent, r.status, r.source)
                    assert r.source != "answer_bank" and not r.bankable, where
                    assert r.status != "resolved" or r.source in (
                        "deterministic_mapping",
                        "profile_fact",
                        "consent",
                    ), where


def _shape(f):
    from app.modules.preparation.resolver import answer_shape

    return answer_shape(f)


def test_saved_answer_scope_marks_what_is_no_longer_reused():
    def saved(label, shape, options=(), help_text=None):
        return NS(
            question_text=label,
            answer_shape=shape,
            options_snapshot=list(options),
            help_text=help_text,
        )

    assert (
        saved_answer_scope(
            saved("How did you hear about this job?", "choice", ["job board", "referral"])
        )
        == "employer"
    )
    assert saved_answer_scope(saved(EDU, "choice", ["bachelor's degree", "other"])) is None
    assert saved_answer_scope(saved(EDU, "choice", ["bachelor's degree"], EDU_HELP)) is None
    assert (
        saved_answer_scope(saved("Are you willing to relocate?", "choice", ["no", "yes"]))
        == "place"
    )
    assert saved_answer_scope(saved("Desired annual salary (USD)", "number")) == "pay"
    assert saved_answer_scope(saved("Are you a US citizen?", "choice", ["no", "yes"])) == "fact"
    assert (
        saved_answer_scope(
            saved("Have you ever been convicted of a felony?", "choice", ["no", "yes"])
        )
        == "other"
    )
    assert saved_answer_scope(saved("Gender", "choice", ["man", "woman"])) is None  # D49 until C8
