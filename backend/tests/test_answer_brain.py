"""D115: the answer brain (app/modules/learning). It suggests one of your own saved answers for
a question worded differently; you accept (saved for that wording too, reused deterministically
from then on) or reject (never suggested again for it); each verdict trains your own model.
Synthetic candidate, fictional manual forms."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.learning import engine, features, service
from app.modules.learning.models import LearningLabel, LearningModel
from app.modules.preparation.forms import FormField
from app.modules.preparation.models import AnswerBankEntry
from app.modules.preparation.resolver import answer_shape, option_labels, question_key
from app.modules.profiles.models import Approval
from tests.test_preparation import setup_candidate
from tests.test_question_safety_api import application as _application
from tests.test_question_safety_api import package, radio, rows

LANGS = [
    {"value": "py", "label": "Python"},
    {"value": "go", "label": "Go"},
    {"value": "rs", "label": "Rust"},
]


_N = iter(range(10**6))


def application(api, fields: list[dict]) -> str:
    """A new job and application each time (the same title would reuse the job)."""
    return _application(api, fields, title=f"Synthetic Role {next(_N)}")


def lang(key="lang", label="Which programming language do you use most?") -> dict:
    return {"key": key, "label": label, "type": "select", "required": True, "options": LANGS}


def saved(api, field: dict, value: dict) -> str:
    """An application where `field` is answered and saved for reuse; its id."""
    app_id = application(api, [field])
    body = {"key": field["key"], "value": value, "save_to_bank": True}
    r = api.put(f"/applications/{app_id}/answers", json=body)
    assert r.status_code == 200, r.text
    return app_id


def suggest(api, app_id) -> list[dict]:
    r = api.get(f"/applications/{app_id}/suggestions")
    assert r.status_code == 200, r.text
    return r.json()["suggestions"]


def verdict(api, app_id, s, what) -> object:
    body = {"key": s["key"], "bank_entry_id": s["bank_entry_id"]}
    return api.post(f"/applications/{app_id}/suggestions/{what}", json=body)


def test_a_reworded_question_gets_your_saved_answer_as_a_suggestion_and_accepting_saves_it(api):
    setup_candidate(api)
    saved(api, lang(), {"label": "Python"})
    app2 = application(api, [lang(label="Which programming language do you use the most?")])
    assert rows(package(api, app2))["lang"]["status"] == "needs_user"  # never filled by itself
    (s,) = suggest(api, app2)
    assert (s["key"], s["display"], s["engine"]) == ("lang", "Python", "rules")
    assert s["saved_question"] == "Which programming language do you use most?"
    assert "features" not in s and "question_key" not in s
    r = verdict(api, app2, s, "accept")
    assert r.status_code == 200, r.text
    row = rows(r.json())["lang"]
    assert (row["status"], row["display"]) == ("resolved", "Python")
    assert suggest(api, app2) == []
    with SessionLocal() as db:
        assert len(db.scalars(select(AnswerBankEntry)).all()) == 2  # the new wording is saved
        (lab,) = db.scalars(select(LearningLabel)).all()
        assert lab.accepted is True and len(lab.features) == len(features.NAMES)
    # The new wording is now an exact saved answer: resolved by the resolver, no suggestion.
    app3 = application(api, [lang(label="Which programming language do you use the most?")])
    row = rows(package(api, app3))["lang"]
    assert (row["status"], row["source"]) == ("resolved", "answer_bank")


def test_rejecting_is_remembered_and_never_suggested_again(api):
    setup_candidate(api)
    saved(api, lang(), {"label": "Go"})
    app2 = application(api, [lang(label="Which programming language do you use the most?")])
    (s,) = suggest(api, app2)
    r = verdict(api, app2, s, "reject")
    assert r.status_code == 200 and r.json()["suggestions"] == []
    assert rows(package(api, app2))["lang"]["status"] == "needs_user"
    assert suggest(api, app2) == []
    assert verdict(api, app2, s, "accept").status_code == 409  # gone: nothing is filled
    with SessionLocal() as db:
        (lab,) = db.scalars(select(LearningLabel)).all()
        assert lab.accepted is False
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "answer_brain.rejected"))
        assert ev.one().meta["field_ref"].startswith("ref:")


@pytest.mark.parametrize(
    "saved_label,new_label",
    [
        ("Can you lift 25 pounds?", "Can you lift 50 pounds?"),  # numbers
        ("Do you have a portfolio website?", "Do you not have a portfolio website?"),  # negation
        ("Have you lived in Canada?", "Have you lived in Mexico?"),  # countries
        # D133: a word on one side only
        ("Are you comfortable with animals?", "Are you uncomfortable with animals?"),  # negation
        ("Can you lift 50 lbs?", "Can you lift 50 kg?"),  # unit
        ("Do you speak Spanish?", "Do you speak French?"),  # language
        ("Have you used Salesforce?", "Have you used HubSpot?"),  # proper_noun
        ("have you used salesforce?", "have you used hubspot?"),  # product
    ],
)
def test_similar_wording_that_differs_on_what_matters_is_never_suggested(api, saved_label,
                                                                         new_label):  # fmt: skip
    setup_candidate(api)
    saved(api, radio("q", saved_label), {"label": "Yes"})
    app2 = application(api, [radio("q", new_label)])
    assert rows(package(api, app2))["q"]["bankable"]  # nothing else refuses it
    assert suggest(api, app2) == []


def test_the_veto_rules():
    base = {"shape": "choice", "label": "Do you use Python?", "help": "", "options": ["yes", "no"]}
    new = base | {"labels": []}
    assert features.veto(new, base | {"labels": ["Yes"]}) is None
    assert features.veto(new, base | {"labels": ["Maybe"]}) == "options"
    assert features.veto(new, base | {"shape": "text", "labels": []}) == "shape"
    assert features.veto(new | {"label": "Do you use Python 3?"}, base | {"labels": ["Yes"]}) == (
        "numbers"
    )


def test_sensitive_saved_answers_and_sensitive_questions_get_no_suggestion(api):
    setup_candidate(api)
    saved(api, lang(), {"label": "Python"})
    with SessionLocal() as db:
        for e in db.scalars(select(AnswerBankEntry)):
            e.sensitive = True
        db.commit()
    app2 = application(api, [lang(label="Which programming language do you use the most?")])
    assert suggest(api, app2) == []
    gender = radio("g", "What is your gender?")
    app3 = application(api, [gender])
    assert suggest(api, app3) == []


def test_another_account_sees_nothing_and_never_gets_your_answers(api, other_api):
    setup_candidate(api)
    app1 = saved(api, lang(), {"label": "Python"})
    assert other_api.get(f"/applications/{app1}/suggestions").status_code == 404
    body = {"key": "lang", "bank_entry_id": str(uuid.uuid4())}
    assert other_api.post(f"/applications/{app1}/suggestions/accept", json=body).status_code == 404
    setup_candidate(other_api)
    theirs = application(other_api, [lang(label="Which programming language do you use the most?")])
    assert suggest(other_api, theirs) == []
    assert other_api.get("/answer-brain").json()["verdicts"] == 0


def test_enough_verdicts_train_the_accounts_own_model_which_then_ranks(api):
    """LightGBM (else XGBoost) learns from the account's verdicts; below the minimum, rules."""
    assert engine.available(), "lightgbm or xgboost is a runtime dependency (D115)"
    setup_candidate(api)
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    good = [1.0, 0.9, 1.0, 1.0, 1.0, 0.9, 5.0, 5.0]
    bad = [0.2, 0.3, 0.0, 0.1, 0.0, 0.5, 5.0, 4.0]
    with SessionLocal() as db:
        for i in range(engine.MIN_LABELS - 1):
            db.add(LearningLabel(user_id=me, question_key=f"k{i}", accepted=i % 2 == 0,
                                 features=good if i % 2 == 0 else bad))  # fmt: skip
        db.flush()
        assert service.retrain(db, me) is None  # one short of the minimum
        db.add(LearningLabel(user_id=me, question_key="k-last", accepted=False, features=bad))
        db.flush()
        m = service.retrain(db, me)
        assert m is not None and m.engine in ("lightgbm", "xgboost") and m.samples == 12
        db.commit()
        hi, lo = engine.predict(m.engine, m.blob, [good, bad])
        assert hi > 0.5 > lo
    state = api.get("/answer-brain").json()
    assert state["engine"] in ("lightgbm", "xgboost") and state["needed"] == 0
    saved(api, lang(), {"label": "Rust"})
    app2 = application(api, [lang(label="Which programming language do you use the most?")])
    (s,) = suggest(api, app2)
    assert s["engine"] == state["engine"] and s["display"] == "Rust"
    assert api.delete("/answer-brain").json()["engine"] == "rules"
    with SessionLocal() as db:
        assert db.get(LearningModel, me) is None


def test_a_follow_up_gets_no_suggestion(api):
    # D131: "Which one?" saved after a language question is not suggested for "Which one?" after
    # an instrument question; the features compare its words, not the question it follows.
    setup_candidate(api)
    langs = radio("lang_q", "Do you speak a language other than English?", required=True)
    music = radio("music_q", "Do you play a musical instrument?", required=True)
    which = {"key": "which", "label": "Which one?", "type": "text", "required": True}
    first = application(api, [langs, which | {"condition": {"key": "lang_q", "any_of": ["1"]}}])
    for key, value in (("lang_q", {"label": "Yes"}), ("which", {"text": "Spanish"})):
        body = {"key": key, "value": value, "save_to_bank": key == "which"}
        r = api.put(f"/applications/{first}/answers", json=body)
        assert r.status_code == 200, r.text
    other = application(api, [music, which | {"condition": {"key": "music_q", "any_of": ["1"]}}])
    body = {"key": "music_q", "value": {"label": "Yes"}}
    assert api.put(f"/applications/{other}/answers", json=body).status_code == 200
    assert rows(package(api, other))["which"]["value"] is None
    assert [s for s in suggest(api, other) if s["key"] == "which"] == []


# ------------------------------------------------------------------ D133: the saved side too


def legacy_entry(api, spec: dict, value: dict) -> str:
    """A saved answer stored before today's rules (as test_question_safety_api does): kept, and
    never used to answer its own wording. Its id."""
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    f = FormField.model_validate(spec)
    with SessionLocal() as db:
        e = AnswerBankEntry(
            user_id=me,
            question_key=question_key(f),
            question_text=f.label,
            help_text="",
            answer_shape=answer_shape(f),
            value=value,
            options_snapshot=option_labels(f),
            sensitive=False,
            version=1,
            provenance="user_entered",
            approval_status=Approval.approved,
        )
        db.add(e)
        db.commit()
        return str(e.id)


def text_q(key, label, **kw) -> dict:
    return {"key": key, "label": label, "type": "text", "required": True} | kw


# A saved answer to a question the bank never reuses (a fact, one employer, a sensitive topic),
# and a reworded question the resolver reads as ordinary: only the saved side says what it is.
WITNESSES = [
    (
        radio("x", "Do you have the necessary documents to work in Canada?"),
        radio("q", "Do you have the necessary forms to work in Canada?", required=True),
        {"labels": ["Yes"]},
    ),
    (
        radio("x", "Have you received the COVID-19 vaccine?"),
        radio("q", "Have you received the COVID-19 booster?", required=True),
        {"labels": ["Yes"]},
    ),
    (
        radio("x", "Have you worked for Acme before?"),
        radio("q", "Have you worked for Acme?", required=True),
        {"labels": ["No"]},
    ),
    (
        radio("x", "Do you have proof of vaccination?"),
        radio("q", "Do you have proof of immunity?", required=True),
        {"labels": ["Yes"]},
    ),
    (text_q("x", "What is your race?"), text_q("q", "What is your pace?"), {"text": "Steady"}),
]


@pytest.mark.parametrize(
    ("saved_spec", "asked", "value"), WITNESSES, ids=[w[1]["label"] for w in WITNESSES]
)
def test_an_answer_saved_for_a_question_never_reused_is_never_suggested(
    api, monkeypatch, saved_spec, asked, value
):
    """D133: the question asked now looks ordinary, but the saved answer was given to a fact, an
    employer's question or a sensitive one: it is not suggested. With that check off it would be,
    so the check is what refuses it (not a veto or the threshold)."""
    setup_candidate(api)
    entry_id = legacy_entry(api, saved_spec, value)
    app_id = application(api, [asked])
    row = rows(package(api, app_id))["q"]
    assert row["bankable"] and row["status"] == "needs_user", row
    assert suggest(api, app_id) == []
    monkeypatch.setattr(service, "_suggestible", lambda e: True)
    assert [s["bank_entry_id"] for s in suggest(api, app_id)] == [entry_id]


def test_a_follow_up_answer_is_never_suggested_for_a_question_on_its_own(api, monkeypatch):
    """D131/D133: "Which language?" saved after "Do you speak another language?" is kept under
    that question; asked on its own elsewhere, it is not suggested. With the check off it would
    be, word for word."""
    setup_candidate(api)
    langs = radio("lang_q", "Do you speak a language other than English?", required=True)
    which = text_q("which", "Which language?")
    first = application(api, [langs, which | {"condition": {"key": "lang_q", "any_of": ["1"]}}])
    for key, value in (("lang_q", {"label": "Yes"}), ("which", {"text": "Spanish"})):
        body = {"key": key, "value": value, "save_to_bank": key == "which"}
        r = api.put(f"/applications/{first}/answers", json=body)
        assert r.status_code == 200, r.text
    other = application(api, [which])
    assert rows(package(api, other))["which"]["value"] is None  # never reused for it either
    assert suggest(api, other) == []
    monkeypatch.setattr(service, "_suggestible", lambda e: True)
    (s,) = suggest(api, other)
    assert (s["display"], s["score"]) == ("Spanish", 1.0)


def test_a_saved_answer_that_would_not_fit_the_field_is_never_suggested(api):
    """D133: a saved text longer than the field allows (accepting it would be refused) is not
    suggested; on the same wording without the limit it is."""
    setup_candidate(api)
    tools = ", ".join(f"Synthetic Tool {i}" for i in range(1, 21))  # 369 characters
    saved(api, text_q("tools", "Which software tools are you familiar with?"), {"text": tools})
    asked = text_q("q", "Which software tools are you most familiar with?")
    limited = application(api, [asked | {"max_length": 100}])
    assert suggest(api, limited) == []
    open_ = application(api, [asked])
    (s,) = suggest(api, open_)
    assert s["display"] == tools
