"""D115: the answer brain. For a question the package still leaves to you, it looks through your
own saved answers (the answer bank, D51) for one given to a question worded differently but
meaning the same, and suggests it. You decide: "Use and save" makes it your answer here and for
this exact wording from then on (the resolver reuses it deterministically, `_from_bank`); "Use
here only" (D133) answers this application alone; "Not this" is remembered so the same pair is
never suggested again. Every verdict is a training label
for your own model (LightGBM, else XGBoost; engine.py), retrained after each one; until there
are enough verdicts the fixed rule score ranks the candidates. D133: the rule score is also a
floor a model cannot lower; a model only ranks and narrows what the rules let through.

What never happens: an answer is filled in without your choice; a suggestion crosses accounts;
a saved answer is suggested where wording disagrees on numbers, negation, countries or the kind
of answer (features.veto); a sensitive or protected answer, a fact about authorization,
sponsorship, residence or pay, or anything the bank rules refuse to reuse (D51, `bankable`) is
suggested at all, whether it is the question asked now or the one the saved answer was given to
(D133, `_suggestible`); nor is an answer that would not fit the field it is suggested for. Labels
hold numbers only, never question or answer text."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.applications.models import Application
from app.modules.identity.models import User
from app.modules.learning import engine, features
from app.modules.learning.models import LearningLabel, LearningModel
from app.modules.preparation import bankscope
from app.modules.preparation import package as pk
from app.modules.preparation.forms import FieldType, FormField, normalize
from app.modules.preparation.models import AnswerBankEntry
from app.modules.preparation.resolver import (
    Context,
    answer_shape,
    display_value,
    normalize_input,
    option_labels,
    question_key,
    resolve_field,
    saved_question,
)
from app.modules.profiles.models import Approval

log = logging.getLogger(__name__)

RULE_THRESHOLD = 0.6  # the fixed blend (features.rule_score); D133: also a floor under a model
MODEL_THRESHOLD = 0.5  # a trained model's probability that you would accept
TRAIN_LIMIT = 5000  # the newest verdicts a model learns from
SHAPES = ("choice", "multi", "boolean", "text", "number", "date")
OPEN_STATUSES = ("needs_user", "blank_optional")


class NoSuggestion(Exception):
    """The suggestion asked about no longer stands (answered, changed, or never made)."""


def _eligible(a: dict) -> bool:
    """A package row the brain may suggest for: still yours to answer, reusable by the bank
    rules, and nothing sensitive, protected, a consent, or from your profile."""
    return (
        a["status"] in OPEN_STATUSES
        and a.get("user_input_allowed")
        and a.get("bankable")
        and not a.get("sensitive")
        and not a.get("protected")
        and not a.get("acknowledgment")
        and a.get("source") not in ("profile_fact", "deterministic_mapping")
        and a.get("type") not in (FieldType.file.value, FieldType.unsupported.value)
        and not (a["status"] == "blank_optional" and a.get("explanation") == pk.NOT_ASKED)
    )


def _new(f: FormField) -> dict:
    return {
        "shape": answer_shape(f),
        "label": f.label,
        "help": f.help_text or "",
        "options": option_labels(f),
        "labels": [],
    }


def _saved(e: AnswerBankEntry) -> dict:
    return {
        "shape": e.answer_shape,
        "label": e.question_text,
        "help": e.help_text or "",
        "options": list(e.options_snapshot or []),
        "labels": list((e.value or {}).get("labels", [])),
    }


def _proposal(f: FormField, e: AnswerBankEntry) -> dict | None:
    """The saved answer as an input for this field (what PUT .../answers takes), or None."""
    shape = answer_shape(f)
    value = e.value or {}
    if shape in ("choice", "multi"):
        by_norm: dict[str, list] = {}
        for o in f.options:
            by_norm.setdefault(normalize(o.label), []).append(o)
        hits = [by_norm.get(normalize(lbl), []) for lbl in value.get("labels", [])]
        if not hits or any(len(h) != 1 for h in hits):
            return None
        labels = [h[0].label for h in hits]
        if shape == "choice":
            return {"label": labels[0]} if len(labels) == 1 else None
        return {"labels": labels}
    return dict(value)


def _model(db: Session, user_id) -> LearningModel | None:
    return db.get(LearningModel, user_id)


def _rejections(db: Session, user_id) -> set[tuple[str, uuid.UUID]]:
    """Every (wording key, saved answer) pair you said "Not this" to."""
    return {
        (qkey, entry_id)
        for qkey, entry_id in db.execute(
            select(LearningLabel.question_key, LearningLabel.bank_entry_id).where(
                LearningLabel.user_id == user_id,
                LearningLabel.accepted.is_(False),
            )
        )
    }


def _fields(db: Session, app: Application) -> dict[str, FormField]:
    form = pk.latest_form(db, app.job_id)
    return {x["key"]: FormField.model_validate(x) for x in form.schema["fields"]}


def _suggestible(e: AnswerBankEntry) -> bool:
    """D133: whether a saved answer may be suggested for another wording at all, judged from the
    question it was given to, rebuilt from what was stored: one the bank rules reuse (D51), and
    nothing sensitive, protected or a consent. The question asked now is judged the same way
    (_eligible), but a wording that differs in one word ("necessary documents to work in Canada"
    against "necessary forms") is only as safe as both sides. Also never a row stored under
    another key than its own wording's: a D131 follow-up is saved under the questions it follows,
    so its wording alone ("Which one?") does not say what it answered."""
    f = saved_question(e)
    if f is None or e.question_key != bankscope.question_key(f, e.answer_shape):
        return False
    r = resolve_field(f, Context())
    return r.bankable and not (r.sensitive or r.protected or r.acknowledgment)


def _usable(db: Session, user: User) -> dict[str, list[tuple[AnswerBankEntry, dict]]]:
    """Your saved answers that may be suggested at all, by answer shape, each judged once per
    request (_suggestible) with the form the features compare (_saved)."""
    out: dict[str, list[tuple[AnswerBankEntry, dict]]] = {}
    entries = db.scalars(
        select(AnswerBankEntry).where(
            AnswerBankEntry.user_id == user.id,
            AnswerBankEntry.sensitive.is_(False),
            AnswerBankEntry.approval_status == Approval.approved,
        )
    )
    for e in entries:
        if e.answer_shape in SHAPES and _suggestible(e):
            out.setdefault(e.answer_shape, []).append((e, _saved(e)))
    return out


def _best(f: FormField, usable: dict, rejected: set, model: LearningModel | None) -> dict | None:
    """The one saved answer to suggest for this field, or None."""
    shape = answer_shape(f)
    if shape not in SHAPES:
        return None
    if f.condition is not None:
        # D131: a follow-up means what the question before it asked, which these features do
        # not compare ("Which one?" after a language or an instrument question); a saved answer
        # after the same questions is already reused exactly by the resolver.
        return None
    new, qkey = _new(f), question_key(f)
    pairs = []
    for e, saved in usable.get(shape, []):
        if (qkey, e.id) in rejected or features.veto(new, saved):
            continue
        proposal = _proposal(f, e)
        if proposal is None:
            continue
        try:  # D133: never suggest what accepting would refuse (too long, not an email ...)
            shown = normalize_input(f, proposal)
        except ValueError:
            continue
        pairs.append((e, proposal, shown, features.pair(new, saved)))
    # D133: the rule score is a floor. A pair below it is never suggested, whatever a trained
    # model would say: the model only ranks and narrows what the rules let through.
    rules = [features.rule_score(feats) for *_, feats in pairs]
    pairs = [p for p, r in zip(pairs, rules, strict=True) if r >= RULE_THRESHOLD]
    rules = [r for r in rules if r >= RULE_THRESHOLD]
    if not pairs:
        return None
    scores, threshold, how = rules, RULE_THRESHOLD, "rules"
    if model is not None:
        try:
            scores = engine.predict(model.engine, model.blob, [feats for *_, feats in pairs])
            threshold, how = MODEL_THRESHOLD, model.engine
        except Exception:  # noqa: BLE001 - a model that cannot load: the rules stand in
            log.exception("answer brain: the trained model could not be used")
            scores, threshold, how = rules, RULE_THRESHOLD, "rules"
    # Equal scores (two saved answers with the same wording): the one whose help text and options
    # match wins, then the same one every time, never the database's row order.
    i = max(
        range(len(pairs)),
        key=lambda k: (scores[k], pairs[k][3][2], pairs[k][3][3], str(pairs[k][0].id)),
    )
    if scores[i] < threshold:
        return None
    e, proposal, shown, feats = pairs[i]
    return {
        "key": f.key,
        "label": f.label,
        "bank_entry_id": str(e.id),
        "saved_question": e.question_text,
        "value": proposal,
        "display": display_value(f, shown),
        "score": round(scores[i], 3),
        "engine": how,
        "features": feats,
    }


def suggestions(db: Session, user: User, app: Application) -> list[dict]:
    from app.modules.preparation.router import _current, _reuse_refusal

    pkg = _current(db, app)
    fields = _fields(db, app)
    model = _model(db, user.id)
    usable, rejected = _usable(db, user), _rejections(db, user.id)
    out = []
    for a in pkg.content["answers"]:
        f = fields.get(a["key"])
        if f is None or not _eligible(a):
            continue
        s = _best(f, usable, rejected, model)
        if s is None or _reuse_refusal(db, app, a, f) is not None:
            continue
        out.append(s)
    return out


def _find(db: Session, user: User, app: Application, key: str, entry_id: uuid.UUID) -> dict:
    for s in suggestions(db, user, app):
        if s["key"] == key and s["bank_entry_id"] == str(entry_id):
            return s
    raise NoSuggestion


def _label(db: Session, user: User, s: dict, accepted: bool) -> None:
    db.add(
        LearningLabel(
            user_id=user.id,
            question_key=s["question_key"],
            bank_entry_id=uuid.UUID(s["bank_entry_id"]),
            accepted=accepted,
            features=s["features"],
        )
    )
    db.flush()
    retrain(db, user.id)


def accept(
    db: Session,
    user: User,
    app: Application,
    key: str,
    entry_id: uuid.UUID,
    save_to_bank: bool = True,
) -> dict:
    """Use the suggested saved answer: your answer here, saved for this exact wording too, or
    (D133, "Use here only") for this application alone. Either way your verdict is a yes."""
    from app.modules.preparation.router import AnswerIn, put_answer

    s = _find(db, user, app, key, entry_id)
    s["question_key"] = question_key(_fields(db, app)[key])
    view = put_answer(
        app.id, AnswerIn(key=key, value=s["value"], save_to_bank=save_to_bank), user=user, db=db
    )
    _label(db, user, s, True)
    db.commit()
    return view


def reject(db: Session, user: User, app: Application, key: str, entry_id: uuid.UUID) -> None:
    """Not this one: never suggested again for this wording, and the model learns from it."""
    from app.modules.audit.service import record, ref

    s = _find(db, user, app, key, entry_id)
    s["question_key"] = question_key(_fields(db, app)[key])
    _label(db, user, s, False)
    record(db, user.id, "answer_brain.rejected", "application", app.id, field_ref=ref(key, user.id))
    db.commit()


def retrain(db: Session, user_id) -> LearningModel | None:
    """Fit the account's model on its own verdicts; below the minimum, the rules stand in."""
    rows = db.execute(
        select(LearningLabel.features, LearningLabel.accepted)
        .where(LearningLabel.user_id == user_id)
        .order_by(LearningLabel.created_at.desc())
        .limit(TRAIN_LIMIT)
    ).all()
    good = [(f, a) for f, a in rows if isinstance(f, list) and len(f) == len(features.NAMES)]
    fitted = engine.fit([f for f, _ in good], [a for _, a in good])
    if fitted is None:
        db.execute(delete(LearningModel).where(LearningModel.user_id == user_id))
        return None
    name, blob = fitted
    m = db.get(LearningModel, user_id)
    if m is None:
        m = LearningModel(user_id=user_id, engine=name, samples=len(good), blob=blob)
        db.add(m)
    else:
        m.engine, m.samples, m.blob, m.trained_at = name, len(good), blob, utcnow()
    db.flush()
    return m


def status(db: Session, user: User) -> dict:
    counts = dict(
        db.execute(
            select(LearningLabel.accepted, func.count())
            .where(LearningLabel.user_id == user.id)
            .group_by(LearningLabel.accepted)
        ).all()
    )
    accepted, rejected = counts.get(True, 0), counts.get(False, 0)
    m = _model(db, user.id)
    saved = db.scalar(
        select(func.count()).select_from(AnswerBankEntry).where(AnswerBankEntry.user_id == user.id)
    )
    return {
        "engine": m.engine if m else "rules",
        "installed": engine.available(),
        "verdicts": accepted + rejected,
        "accepted": accepted,
        "rejected": rejected,
        "needed": max(0, engine.MIN_LABELS - accepted - rejected),
        "trained_at": m.trained_at.isoformat() if m else None,
        "trained_on": m.samples if m else 0,
        "saved_answers": saved or 0,
    }


def forget(db: Session, user: User) -> None:
    """Delete the account's verdicts and model; saved answers stay (edit them in Answers)."""
    db.execute(delete(LearningLabel).where(LearningLabel.user_id == user.id))
    db.execute(delete(LearningModel).where(LearningModel.user_id == user.id))
    db.commit()
