"""D133: which of your saved answers the answer brain may suggest for another wording at all
(learning.service._suggestible), judged once from the question each one was given to, rebuilt
from what was stored; and which rewordings are vetoed outright (learning.features.veto), label
and help text together. No database, no server; synthetic wordings."""

from types import SimpleNamespace as NS

import pytest

from app.modules.learning import features, service
from app.modules.preparation.forms import Condition, FieldType, FormField, Option
from app.modules.preparation.resolver import answer_shape, option_labels, question_key, reuse_key

TYPES = {"choice": FieldType.select, "text": FieldType.text, "date": FieldType.date}


def field(label, shape="choice", options=("Yes", "No"), help_text=None, key="q", condition=None):
    return FormField(
        key=key,
        label=label,
        type=TYPES[shape],
        options=[Option(value=str(i), label=x) for i, x in enumerate(options)]
        if shape == "choice"
        else [],
        help_text=help_text,
        condition=condition,
    )


def stored(f, key=None, **kw):
    """A saved answer to `f` as the app stores it (_save_to_bank): under its wording's key unless
    told otherwise."""
    return NS(
        question_key=key or question_key(f),
        question_text=f.label,
        help_text=(f.help_text or "").strip(),
        answer_shape=answer_shape(f),
        options_snapshot=option_labels(f),
        **kw,
    )


@pytest.mark.parametrize(
    "f",
    [
        field("Do you have the necessary documents to work in Canada?"),  # a fact (D131)
        field("Have you worked for Acme before?"),  # about one employer
        field("Can you start immediately?"),  # time-bound
        field("When can you start?", shape="date"),  # time-bound, a date
        field("Have you received the COVID-19 vaccine?"),  # sensitive since D131's follow-up
        field("Gender", options=("Woman", "Man")),  # sensitive, whatever the stored flag says
        field("Are you a protected veteran?"),
    ],
    ids=lambda f: f.label,
)
def test_an_answer_to_a_question_the_bank_never_reuses_is_never_suggested(f):
    assert service._suggestible(stored(f)) is False


@pytest.mark.parametrize(
    "f",
    [
        field("Which programming language do you use most?", options=("Python", "Go")),
        field("Which software tools are you familiar with?", shape="text"),
        field("Portfolio URL", shape="text", help_text="A link to your work samples"),
    ],
    ids=lambda f: f.label,
)
def test_an_answer_to_an_ordinary_question_may_be_suggested(f):
    assert service._suggestible(stored(f)) is True


def test_an_imported_answer_may_be_suggested():
    # bank_import stores no help text and keys the wording alone (D99).
    f = field("Do you have experience with Salesforce?")
    assert service._suggestible(stored(f, provenance="import")) is True


def test_an_answer_that_cannot_be_rebuilt_into_a_question_is_never_suggested():
    f = field("Which programming language do you use most?", options=("Python", "Go"))
    long_option = stored(f)
    long_option.options_snapshot = ["python", "x" * 501]  # no longer fits an option
    assert service._suggestible(long_option) is False
    blank = stored(f)
    blank.question_text = ""  # stored after "\x00" was stripped from the wording
    assert service._suggestible(blank) is False


def test_a_follow_up_saved_under_the_question_it_follows_is_never_suggested():
    """D131: "Which language?" saved after "Do you speak another language?" is keyed with that
    question; its wording alone does not say what it answered. Keyed under its own wording, the
    same row may be suggested: the key is what refuses it."""
    parent = field("Do you speak a language other than English?", key="lang_q")
    child = field(
        "Which language?",
        shape="text",
        key="which",
        condition=Condition(key="lang_q", any_of=["0"]),
    )
    key = reuse_key(child, {"lang_q": parent, "which": child})
    assert key is not None and key != question_key(child)
    assert service._suggestible(stored(child, key=key)) is False
    assert service._suggestible(stored(child)) is True


# ------------------------------------------------------------------ the vetoes (features.veto)


def side(label, help_="", shape="choice"):
    """One side of a pair, as the answer brain compares it (service._new and _saved)."""
    return {"shape": shape, "label": label, "help": help_, "options": ["yes", "no"]}


def veto(saved_label, new_label, saved_help="", new_help="", shape="choice"):
    saved = side(saved_label, saved_help, shape) | {"labels": ["Yes"]}
    return features.veto(side(new_label, new_help, shape) | {"labels": []}, saved)


CURLY = "’"  # a typographic apostrophe
ACUTE = "\u00b4"  # an acute accent typed for one (Spanish, Portuguese, German keyboards)
VETOED = [
    ("proper_noun", "Have you used Salesforce?", "Have you used HubSpot?"),
    ("proper_noun", "Do you have experience with AWS?", "Do you have experience with Azure?"),
    ("proper_noun", "Are you a member of IEEE?", "Are you a member of ACM?"),
    ("proper_noun", "Have you lived in California?", "Have you lived in Texas?"),
    ("proper_noun", "Have you used Epic EHR?", "Have you used Cerner EHR?"),
    (
        "proper_noun",
        "Are you proficient in Microsoft Excel?",
        "Are you proficient in Google Sheets?",
    ),
    ("language", "Do you speak Spanish?", "Do you speak French?"),
    ("language", "Are you fluent in Mandarin?", "Are you fluent in Cantonese?"),
    ("language", "Do you speak Hindi?", "Do you speak Urdu?"),
    ("language", "Do you have experience with Python?", "Do you have experience with Java?"),
    ("language", "Do you know C++?", "Do you know C#?"),
    ("product", "have you used salesforce?", "have you used hubspot?"),
    ("proper_noun", "Epic Analyst Certification", "Cerner Analyst Certification"),  # a heading
    ("unit", "Can you lift 50 lbs?", "Can you lift 50 kg?"),
    ("unit", "Can you lift 50 pounds?", "Can you lift 50 kilograms?"),
    ("unit", "Can you stand for 8 hours?", "Can you stand for 8 minutes?"),
    ("unit", "Can you type 60 words per minute?", "Can you type 60 characters per minute?"),
    ("numbers", "Can you lift twenty pounds?", "Can you lift fifty pounds?"),
    ("negation", "Do you have experience with Python?", "Do you lack experience with Python?"),
    ("negation", "Are you able to lift 50 pounds?", "Are you unable to lift 50 pounds?"),
    ("negation", "Are you comfortable with animals?", "Are you uncomfortable with animals?"),
    ("negation", "Have you managed a team?", "Haven't you managed a team?"),
    ("negation", "Does the role involve travel?", "Doesn't the role involve travel?"),
    ("negation", "Can you lift 50 pounds?", f"Can{CURLY}t you lift 50 pounds?"),
    ("negation", "Do you drive?", f"Don{CURLY}t you drive?"),
    ("negation", "Did you pass the bar exam?", "Did you fail the bar exam?"),
    ("negation", "Do you speak English?", "Do you speak a language other than English?"),
    (
        "negation",
        "Are you eligible for the bonus scheme?",
        "Are you ineligible for the bonus scheme?",
    ),
    # D133 review: what the first build missed.
    ("negation", "Can you lift 50 pounds?", f"Can{ACUTE}t you lift 50 pounds?"),
    ("negation", "Can you lift 50 pounds?", "Can`t you lift 50 pounds?"),
    (
        "negation",
        "Are you comfortable working at heights?",
        "Are you afraid of working at heights?",
    ),
    ("negation", "Do you enjoy working with customers?", "Do you dislike working with customers?"),
    ("numbers", "Can you lift twenty-five pounds?", "Can you lift seventy-five pounds?"),
    ("numbers", "Have you used three-phase power?", "Have you used single-phase power?"),
    ("numbers", "Can you work 7am-7pm?", "Can you work 7pm-7am?"),
    ("numbers", "Can you work from 9 a.m. to 5 p.m.?", "Can you work from 9 p.m. to 5 a.m.?"),
    (
        "numbers",
        "Can you lift 50 pounds and carry 25 pounds?",
        "Can you lift 25 pounds and carry 50 pounds?",
    ),
    (
        "countries",
        "Do you have payroll experience in the U.K.?",
        "Do you have payroll experience in the U.S.?",
    ),
    ("countries", "Do you have payroll experience?", "Do you have US payroll experience?"),
    ("bound", "Can you lift more than 50 pounds?", "Can you lift less than 50 pounds?"),
    ("bound", "Can you lift at least 50 pounds?", "Can you lift at most 50 pounds?"),
    ("bound", "Do you have a GPA above 3.5?", "Do you have a GPA below 3.5?"),
    ("quantity", "Have you used any of these tools?", "Have you used all of these tools?"),
    ("restrictive", "Do you speak English?", "Do you speak only English?"),
    ("level", "Do you have basic Excel skills?", "Do you have advanced Excel skills?"),
    ("schedule", "Can you work evening shifts?", "Can you work weekend shifts?"),
    ("workplace", "Are you able to work remotely?", "Are you able to work on-site?"),
    (
        "employment",
        "Are you available for full-time work?",
        "Are you available for part-time work?",
    ),
    ("script", "У вас есть опыт работы с Excel?", "Вы никогда не работали с Excel?"),
    ("script", "您有Salesforce经验吗？", "您有Salesforce认证吗？"),
]


@pytest.mark.parametrize(("code", "saved_label", "new_label"), VETOED, ids=[v[2] for v in VETOED])
def test_wording_that_differs_on_what_matters_is_vetoed(code, saved_label, new_label):
    assert veto(saved_label, new_label) == code
    assert veto(new_label, saved_label) == code  # either way round


HELP_ONLY = [
    ("unit", "In pounds", "In kilograms"),
    ("language", "For example Python", "For example Java"),
    ("numbers", "Up to 25 lbs", "Up to 75 lbs"),
    ("countries", "For work in Canada", "For work in Mexico"),
]


@pytest.mark.parametrize(
    ("code", "saved_help", "new_help"), HELP_ONLY, ids=[h[0] for h in HELP_ONLY]
)
def test_help_text_that_differs_on_what_matters_vetoes_identical_labels(code, saved_help, new_help):
    label = "What is the heaviest load you can carry?"
    assert veto(label, label, saved_help, new_help, shape="text") == code


def test_an_answering_instruction_in_the_help_text_cancels_no_negation():
    # D133 review: "If not, please explain." on one side once cancelled the other label's "not".
    got = veto(
        "Can you work in a climate-controlled warehouse?",
        "Can you work in a warehouse that is not climate-controlled?",
        saved_help="If not, please explain.",
    )
    assert got == "negation"
    got = veto(
        "Are you comfortable working with supervision?",
        "Are you comfortable working with no supervision?",
        saved_help="If no, please explain in the next question.",
    )
    assert got == "negation"
    label = "Do you have a driver's license?"  # the instruction itself changes nothing
    assert veto(label, label, saved_help="If not, please explain.") is None


def test_a_product_named_only_in_the_help_text_vetoes():
    label = "Which customer relationship tool have you used?"
    got = veto(label, label, "For example Salesforce", "For example HubSpot", shape="text")
    assert got in ("proper_noun", "product")
    got = veto(label, label, "for example salesforce", "for example zendesk", shape="text")
    assert got == "product"


CONTROLS = [
    (
        "Which programming language do you use most?",
        "Which programming language do you use the most?",
    ),
    ("Do you have experience with Python?", "Do you have Python experience?"),
    ("Have you used Salesforce?", "Have you ever used Salesforce?"),
    ("Do you speak Spanish?", "Can you speak Spanish?"),
    ("Do you own a car?", "Do you have your own car?"),
    ("Can you lift 50 pounds?", "Are you able to lift 50 pounds?"),
    ("Do you have a portfolio?", "Do you have a portfolio website?"),
    ("What is your GitHub username?", "GitHub username"),
    ("Do you have a bachelor's degree?", "Do you hold a bachelor's degree?"),
    ("Do you speak Spanish?", "Do you speak Spanish? (Yes/No)"),
    ("Do you speak Spanish?", "Do you speak Spanish? Yes/No"),
    ("Do you speak Spanish?", "Do you speak Spanish? [Yes/No]"),
    ("What is your phone number?", "What is your phone no.?"),
    ("Portfolio website", "Portfolio URL"),
    ("Experience with Salesforce?", "Have you used Salesforce?"),
    ("Are you proficient in Microsoft Excel?", "How proficient are you in Microsoft Excel?"),
    ("Have you lived in the United States?", "Have you lived in the US?"),
    (
        "Which software tools are you familiar with?",
        "Which software tools are you most familiar with?",
    ),
]


@pytest.mark.parametrize(("saved_label", "new_label"), CONTROLS, ids=[c[1] for c in CONTROLS])
def test_a_rewording_that_changes_nothing_that_matters_is_not_vetoed(saved_label, new_label):
    assert veto(saved_label, new_label) is None
    assert veto(new_label, saved_label) is None


# One witness each that only that family vetoes: neutralised, the pair is no longer vetoed.
WITNESS = {
    "negation": ("Are you comfortable with animals?", "Are you uncomfortable with animals?"),
    "unit": ("Can you lift 50 lbs?", "Can you lift 50 kg?"),
    "language": ("do you speak spanish?", "do you speak french?"),
    "proper_noun": ("Do you have experience with AWS?", "Do you have experience with Azure?"),
    "product": ("have you used salesforce?", "have you used hubspot?"),
    "restrictive": ("Do you speak English?", "Do you speak only English?"),
    "level": ("Do you have basic Excel skills?", "Do you have advanced Excel skills?"),
}


@pytest.mark.parametrize("code", sorted(WITNESS))
def test_every_word_family_is_load_bearing(code, monkeypatch):
    assert [c for c, _ in features.FAMILIES] == list(WITNESS)  # every family has a witness
    assert veto(*WITNESS[code]) == code
    families = [(c, (lambda *a: False) if c == code else f) for c, f in features.FAMILIES]
    monkeypatch.setattr(features, "FAMILIES", families)
    assert veto(*WITNESS[code]) is None


# One witness per kind of alternative: emptied, the pair is no longer vetoed.
ALTERNATIVE_WITNESS = {
    "bound": ("Can you lift more than 50 pounds?", "Can you lift less than 50 pounds?"),
    "quantity": ("Have you used any of these tools?", "Have you used all of these tools?"),
    "schedule": ("Can you work evening shifts?", "Can you work weekend shifts?"),
    "workplace": ("Are you able to work remotely?", "Are you able to work on-site?"),
    "employment": (
        "Are you available for full-time work?",
        "Are you available for part-time work?",
    ),
}


@pytest.mark.parametrize("code", sorted(ALTERNATIVE_WITNESS))
def test_every_kind_of_alternative_is_load_bearing(code, monkeypatch):
    assert sorted(features.ALTERNATIVES) == sorted(ALTERNATIVE_WITNESS)
    assert veto(*ALTERNATIVE_WITNESS[code]) == code
    monkeypatch.setitem(features.ALTERNATIVES, code, set())
    assert veto(*ALTERNATIVE_WITNESS[code]) is None


def test_a_long_label_is_read_afresh_not_cached():
    # D133 review: the cache holds the short labels forms repeat, never a long one.
    before = features._cached_side.cache_info().currsize
    features._side("Do you have experience " + "with these tools " * 100, "")
    assert features._cached_side.cache_info().currsize == before


def test_equal_scores_prefer_the_matching_help_text_whatever_the_row_order():
    # D133 review: two saved answers with the same wording score the same; the database's row
    # order once chose between them.
    label, work = "Which programming language do you use most?", "At work, in your current team."
    langs = ("Python", "Go")
    plain = stored(field(label, options=langs), value={"labels": ["Python"]}, id="a")
    at_work = stored(field(label, options=langs, help_text=work), value={"labels": ["Go"]}, id="b")
    new = field("Which programming language do you use the most?", options=langs, help_text=work)
    for order in ([plain, at_work], [at_work, plain]):
        usable = {"choice": [(e, service._saved(e)) for e in order]}
        assert service._best(new, usable, set(), None)["value"] == {"label": "Go"}


# ------------------------------------------------------------------ the rule score (D133)


def test_the_rule_score_reads_the_wording_only():
    # Help and options similarity are left out: two questions with neither once scored 0.30.
    assert features.rule_score([0, 0, 1, 1, 1, 1, 0, 0]) == pytest.approx(0.125)


def score(saved_label, new_label):
    return features.rule_score(features.pair(side(new_label), side(saved_label)))


REWORDED = [
    (
        "Which programming language do you use most?",
        "Which programming language do you use the most?",
    ),
    ("Do you have experience with Python?", "Do you have Python experience?"),
    ("Have you used Salesforce?", "Have you ever used Salesforce?"),
    ("Do you speak Spanish?", "Can you speak Spanish?"),
    ("Are you comfortable working with animals?", "Are you comfortable around animals?"),
    ("Do you own a car?", "Do you have your own car?"),
    ("Can you lift 50 pounds?", "Are you able to lift 50 pounds?"),
    ("Do you have a portfolio?", "Do you have a portfolio website?"),
    ("Have you managed a team?", "Have you ever managed a team?"),
    ("Are you proficient in Microsoft Excel?", "How proficient are you in Microsoft Excel?"),
    ("What is your GitHub username?", "GitHub username"),
    ("Do you have a bachelor's degree?", "Do you hold a bachelor's degree?"),
]
# A common noun swapped is invisible to the vetoes; the score keeps these below the threshold.
# "Can you operate a forklift?" vs "...a crane?" still scores above it (0.656): stated in D133.
UNRELATED = [
    ("Do you own a car?", "Do you own a laptop?"),
    ("Do you have a portfolio?", "Do you have a pet?"),
    ("Are you comfortable with public speaking?", "Are you comfortable with heights?"),
    ("Which programming language do you use most?", "Which colour do you like best?"),
]


@pytest.mark.parametrize(("saved_label", "new_label"), REWORDED, ids=[r[1] for r in REWORDED])
def test_a_rewording_scores_at_or_above_the_threshold(saved_label, new_label):
    assert score(saved_label, new_label) >= service.RULE_THRESHOLD


@pytest.mark.parametrize(("saved_label", "new_label"), UNRELATED, ids=[u[1] for u in UNRELATED])
def test_an_unrelated_question_scores_below_the_threshold(saved_label, new_label):
    assert score(saved_label, new_label) < service.RULE_THRESHOLD
