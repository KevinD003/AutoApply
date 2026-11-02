"""D115: the answer brain. For a question the package still leaves to you, it looks through your
own saved answers (the answer bank, D51) for one given to a question worded differently but
meaning the same, and suggests it. You decide: "Use this" saves it as your answer here and for
this exact wording from then on (the resolver reuses it deterministically, `_from_bank`); "Not
this" is remembered so the same pair is never suggested again. Every verdict is a training label
for your own model (LightGBM, else XGBoost; engine.py), retrained after each one; until there
are enough verdicts the fixed rule score ranks the candidates.

What never happens: an answer is filled in without your choice; a suggestion crosses accounts;
a saved answer is suggested where wording disagrees on numbers, negation, countries or the kind
of answer (features.veto); a sensitive or protected answer, a fact about authorization,
sponsorship, residence or pay, or anything the bank rules refuse to reuse (D51, `bankable`) is
suggested at all. Labels hold numbers only, never question or answer text."""

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
from app.modules.preparation import package as pk
from app.modules.preparation.forms import FieldType, FormField, normalize
from app.modules.preparation.models import AnswerBankEntry
from app.modules.preparation.resolver import (
    answer_shape,
    display_value,
    option_labels,
    question_key,
)
from app.modules.profiles.models import Approval

log = logging.getLogger(__name__)

RULE_THRESHOLD = 0.5  # the fixed blend (features.rule_score)
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


def _rejected(db: Session, user_id, qkey: str) -> set:
    return set(
        db.scalars(
            select(LearningLabel.bank_entry_id).where(
                LearningLabel.user_id == user_id,
                LearningLabel.question_key == qkey,
                LearningLabel.accepted.is_(False),
            )
        )
    )


def _fields(db: Session, app: Application) -> dict[str, FormField]:
    form = pk.latest_form(db, app.job_id)
    return {x["key"]: FormField.model_validate(x) for x in form.schema["fields"]}


def _candidates(db: Session, user: User, shape: str) -> list[AnswerBankEntry]:
    return list(
        db.scalars(
            select(AnswerBankEntry).where(
                AnswerBankEntry.user_id == user.id,
                AnswerBankEntry.answer_shape == shape,
                AnswerBankEntry.sensitive.is_(False),
                AnswerBankEntry.approval_status == Approval.approved,
            )
        )
    )


def _best(db: Session, user: User, f: FormField, model: LearningModel | None) -> dict | None:
    """The one saved answer to suggest for this field, or None."""
    shape = answer_shape(f)
    if shape not in SHAPES:
        return None
    new, qkey = _new(f), question_key(f)
    rejected = _rejected(db, user.id, qkey)
    pairs = []
    for e in _candidates(db, user, shape):
        if e.id in rejected or features.veto(new, _saved(e)):
            continue
        proposal = _proposal(f, e)
        if proposal is None:
            continue
        pairs.append((e, proposal, features.pair(new, _saved(e))))
    if not pairs:
        return None
    if model is not None:
        try:
            scores = engine.predict(model.engine, model.blob, [p[2] for p in pairs])
            threshold, how = MODEL_THRESHOLD, model.engine
        except Exception:  # noqa: BLE001 - a model that cannot load: the rules stand in
            log.exception("answer brain: the trained model could not be used")
            model = None
    if model is None:
        scores = [features.rule_score(p[2]) for p in pairs]
        threshold, how = RULE_THRESHOLD, "rules"
    i = max(range(len(pairs)), key=lambda k: scores[k])
    if scores[i] < threshold:
        return None
    e, proposal, feats = pairs[i]
    return {
        "key": f.key,
        "label": f.label,
        "bank_entry_id": str(e.id),
        "saved_question": e.question_text,
        "value": proposal,
        "display": display_value(f, _shown(f, proposal)),
        "score": round(scores[i], 3),
        "engine": how,
        "features": feats,
    }


def _shown(f: FormField, proposal: dict) -> dict:
    """The proposal in the stored shape display_value reads (options carry value and label)."""
    from app.modules.preparation.resolver import normalize_input

    try:
        return normalize_input(f, proposal)
    except ValueError:
        return proposal


def suggestions(db: Session, user: User, app: Application) -> list[dict]:
    from app.modules.preparation.router import _current, _reuse_refusal

    pkg = _current(db, app)
    fields = _fields(db, app)
    model = _model(db, user.id)
    out = []
    for a in pkg.content["answers"]:
        f = fields.get(a["key"])
        if f is None or not _eligible(a):
            continue
        s = _best(db, user, f, model)
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


def accept(db: Session, user: User, app: Application, key: str, entry_id: uuid.UUID) -> dict:
    """Use the suggested saved answer: your answer here, saved for this exact wording too."""
    from app.modules.preparation.router import AnswerIn, put_answer

    s = _find(db, user, app, key, entry_id)
    s["question_key"] = question_key(_fields(db, app)[key])
    view = put_answer(
        app.id, AnswerIn(key=key, value=s["value"], save_to_bank=True), user=user, db=db
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
