"""D133: which of your saved answers the answer brain may suggest for another wording at all
(learning.service._suggestible), judged once from the question each one was given to, rebuilt
from what was stored. No database, no server; synthetic wordings."""

from types import SimpleNamespace as NS

import pytest

from app.modules.learning import service
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
