"""Importing saved answers from a file you supply (D99): question/answer pairs from another
tool, added to your saved answers as proposals.

Every row passes the same rules as an answer saved from an application, judged on its wording
alone (no form, no help text, no section): what the resolver would not save for reuse is refused
with its reason, and so is anything sensitive, a template naming the employer, a placeholder,
and a question given twice with different answers (never chosen silently). A yes/no answer is
saved for the question with exactly the options Yes and No; any other answer as text. Nothing
already saved is replaced.

An imported answer is `proposed`: it answers nothing until you approve it on the Saved answers
page (the resolver uses approved answers only). No LLM, no network; nothing is inferred.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.preparation import bankscope
from app.modules.preparation.classify import classify
from app.modules.preparation.forms import FieldType, FormField, Option, normalize
from app.modules.preparation.models import AnswerBankEntry
from app.modules.preparation.resolver import Context, option_labels, question_key, resolve_field
from app.modules.profiles.models import Approval, Provenance

MAX_ROWS = 5000
_PLACEHOLDER = re.compile(
    r"^\s*(n/?a|none|null|nil|-+|\.+|x+|tbd|todo|test|asdf|lorem.*|\?+|\[.*\]|<.*>)\s*$", re.I
)
_YES_NO = {"yes": "Yes", "no": "No", "y": "Yes", "n": "No"}
_TEMPLATE = re.compile(r"\{[a-z_]+\}", re.I)  # "{company}" and the like
YN = [Option(value="yes", label="Yes"), Option(value="no", label="No")]

REASONS = {
    "blank": "no question or no answer",
    "placeholder": "a placeholder answer (N/A, TBD, test, ...)",
    "template": "a template naming the employer, such as {company}",
    "conflict": "the same question with different answers in the file",
    "duplicate": "the same question and answer earlier in the file",
    "already_saved": "you already have a saved answer for this question",
    "sensitive": "a sensitive topic: answered on each form, never imported",
    "protected": "work authorization, sponsorship, citizenship or residence: from your profile",
    "not_saved": "never saved for reuse",
}


@dataclass
class Row:
    question: str
    answer: str


@dataclass
class Decision:
    outcome: str  # "import" | "refused"
    reason: str | None = None  # a REASONS key, or a bankscope category ("employer", "time", ...)
    field: FormField | None = None
    value: dict | None = None


def _field(question: str, answer: str) -> tuple[FormField, dict]:
    yn = _YES_NO.get(answer.strip().lower())
    if yn:
        return FormField(key="q", label=question, type=FieldType.select, options=YN), {
            "labels": [yn]
        }
    typ = FieldType.textarea if len(answer) > 200 else FieldType.text
    return FormField(key="q", label=question, type=typ), {"text": answer.strip()}


def _judge(row: Row) -> Decision:
    q, a = (row.question or "").strip(), (row.answer or "").strip()
    if not q or not a:
        return Decision("refused", "blank")
    if _TEMPLATE.search(q) or _TEMPLATE.search(a):
        return Decision("refused", "template")
    if _PLACEHOLDER.match(a):
        return Decision("refused", "placeholder")
    f, value = _field(q, a)
    r = resolve_field(f, Context())
    if r.sensitive:
        return Decision("refused", "sensitive")
    if r.protected:
        return Decision("refused", "protected")
    if not r.bankable:
        return Decision("refused", bankscope.refusal_code(f, classify(f)) or "not_saved")
    return Decision("import", field=f, value=value)


def plan(db: Session, user_id: uuid.UUID, rows: list[Row]) -> list[Decision]:
    """What importing `rows` would do, row by row. Reads only."""
    out = [_judge(r) for r in rows]
    by_key: dict[str, list[int]] = {}
    for i, d in enumerate(out):
        if d.outcome == "import":
            by_key.setdefault(question_key(d.field), []).append(i)
    saved = set(
        db.scalars(
            select(AnswerBankEntry.question_key).where(
                AnswerBankEntry.user_id == user_id,
                AnswerBankEntry.question_key.in_(list(by_key)),
            )
        )
    )
    for key, idx in by_key.items():
        if key in saved:
            for i in idx:
                out[i] = Decision("refused", "already_saved")
            continue
        answers = {normalize(str(out[i].value)) for i in idx}
        if len(answers) > 1:  # never choose between them
            for i in idx:
                out[i] = Decision("refused", "conflict")
            continue
        for i in idx[1:]:
            out[i] = Decision("refused", "duplicate")
    return out


def apply(db: Session, user_id: uuid.UUID, decisions: list[Decision]) -> int:
    """Add the importable rows as proposals. The caller commits."""
    now = utcnow()
    n = 0
    for d in decisions:
        if d.outcome != "import":
            continue
        f = d.field
        db.add(
            AnswerBankEntry(
                user_id=user_id,
                question_key=question_key(f),
                question_text=f.label.replace("\x00", ""),
                help_text="",
                answer_shape="choice" if f.type == FieldType.select else "text",
                value=d.value,
                options_snapshot=option_labels(f),
                sensitive=False,
                source_application_id=None,
                provenance=Provenance.import_,
                approval_status=Approval.proposed,
                version=1,
                updated_at=now,
            )
        )
        n += 1
    db.flush()
    return n


def approve(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID) -> AnswerBankEntry | None:
    """An imported proposal becomes a saved answer you approved. None: not yours (404)."""
    e = db.scalar(
        select(AnswerBankEntry)
        .where(AnswerBankEntry.id == entry_id, AnswerBankEntry.user_id == user_id)
        .with_for_update()
    )
    if e is None:
        return None
    if e.approval_status != Approval.proposed:
        raise ValueError("not_a_proposal")
    e.approval_status = Approval.approved
    e.updated_at = utcnow()
    db.flush()
    return e
