"""Editing a saved answer, with its history (priority C, D78).

An edit changes only the answer: the question it is bound to (its wording, help text and, for
choices, the options seen when it was saved) stays as it was, so the edited answer is reused for
exactly the questions the saved one was. Each change is a new version, and each version is kept
as a `fact_versions` row (entity type `answer_bank`), whether it came from an application
("saved from an application") or from this page ("edited by you"). A version saved before
history was recorded is written as "as first recorded" the first time it is edited.

Packages cite the saved answer by id and version (resolver `_from_bank`), so an edit changes the
content hash of every package that used it. The edit commits first; then each of the account's
applications whose current package cites the entry is rebuilt (package.ensure_current), which
invalidates its approvals with the reason. Rebuilding locks applications only after the saved
answer's row is released, keeping the lock order (application, then saved answer; D46 item 6).
An application that execution owns is not rebuilt; its gates refuse the stale hash."""

import math
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.applications.models import Application
from app.modules.audit.service import record
from app.modules.preparation import package as pk
from app.modules.preparation.forms import normalize
from app.modules.preparation.models import AnswerBankEntry
from app.modules.profiles.models import Approval, FactVersion, Provenance

ENTITY = "answer_bank"
SAVED, EDITED, FIRST = "saved from an application", "edited by you", "as first recorded"
IMPORTED = "imported from a file"  # D99
MAX_TEXT = 5000


class EditRefused(ValueError):
    pass


def _value(entry: AnswerBankEntry, raw: dict) -> dict:
    """The new value in the stored shape (`_save_to_bank`), checked against the answer's own
    shape and, for choices, the options saved with it. A field's own limits (length, pattern)
    are checked again when the answer is reused; one that no longer fits becomes a checkpoint
    there (resolver `_from_bank`), never a guess."""
    shape = entry.answer_shape
    if shape in ("choice", "multi"):
        labels = raw.get("labels")
        if not (isinstance(labels, list) and labels and all(isinstance(x, str) for x in labels)):
            raise EditRefused("Choose one or more of the options saved with this answer.")
        offered = set(entry.options_snapshot or [])
        chosen = [normalize(x) for x in labels]
        if any(x not in offered for x in chosen) or len(set(chosen)) != len(chosen):
            raise EditRefused("Choose only options saved with this answer, each once.")
        if shape == "choice" and len(chosen) != 1:
            raise EditRefused("Choose exactly one option.")
        return {"labels": chosen}
    if shape == "boolean":
        if not isinstance(raw.get("checked"), bool):
            raise EditRefused("Expected checked: true or false.")
        return {"checked": raw["checked"]}
    if shape == "number":
        try:
            n = float(raw.get("number"))
        except (TypeError, ValueError):
            raise EditRefused("Expected a number.") from None
        if not math.isfinite(n):
            raise EditRefused("Expected a number.")
        return {"number": n}
    if shape == "date":
        try:
            return {"date": date.fromisoformat(str(raw.get("date"))).isoformat()}
        except ValueError:
            raise EditRefused("Expected a date as YYYY-MM-DD.") from None
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise EditRefused("Expected non-empty text.")
    if len(text) > MAX_TEXT:
        raise EditRefused(f"At most {MAX_TEXT} characters.")
    return {"text": text.strip().replace("\x00", "")}


def _snapshot(entry: AnswerBankEntry, how: str) -> dict:
    return {
        "value": entry.value,
        "options_snapshot": entry.options_snapshot,
        "how": how,
        "provenance": Provenance(entry.provenance).value,
        "approval_status": Approval(entry.approval_status).value,
        "source_application_id": str(entry.source_application_id)
        if entry.source_application_id
        else None,
    }


def keep_version(db: Session, entry: AnswerBankEntry, how: str) -> None:
    """Write this version of the entry to its history, once."""
    exists = db.scalar(
        select(FactVersion.id).where(
            FactVersion.entity_type == ENTITY,
            FactVersion.entity_id == entry.id,
            FactVersion.version == entry.version,
        )
    )
    if exists is None:
        db.add(
            FactVersion(
                user_id=entry.user_id,
                entity_type=ENTITY,
                entity_id=entry.id,
                version=entry.version,
                snapshot=_snapshot(entry, how),
            )
        )


def _citing(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID) -> list[Application]:
    out = []
    for app in db.scalars(select(Application).where(Application.user_id == user_id)):
        pkg = pk.latest_package(db, app.id)
        if pkg is None:
            continue
        for a in pkg.content.get("answers", []):
            if any(
                r.get("type") == ENTITY and r.get("id") == str(entry_id)
                for r in a.get("fact_refs") or []
            ):
                out.append(app)
                break
    return out


def edit(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID, raw: dict):
    """Returns (entry, changed, applications whose approvals the edit invalidated), or None when
    the entry is not this account's. Raises EditRefused for a value that does not fit."""
    entry = db.scalar(
        select(AnswerBankEntry)
        .where(AnswerBankEntry.id == entry_id, AnswerBankEntry.user_id == user_id)
        .with_for_update()
    )
    if entry is None:
        return None
    value = _value(entry, raw)
    current = entry.value
    if "labels" in current:  # saved from a form with its labels as shown: compare normalized
        current = {"labels": [normalize(x) for x in current["labels"]]}
    if value == current:
        db.rollback()
        return entry, False, 0
    keep_version(db, entry, FIRST)
    entry.value = value
    entry.version += 1
    entry.provenance, entry.approval_status = Provenance.user_entered, Approval.approved
    keep_version(db, entry, EDITED)
    record(db, user_id, "answer_bank.edit", "answer_bank", entry.id, version=entry.version)
    db.commit()  # the saved answer's lock is released before any application is locked
    invalidated = 0
    for app in _citing(db, user_id, entry_id):
        before = pk.active_approval(db, pk.latest_package(db, app.id)) is not None
        pk.ensure_current(db, app)
        db.commit()
        if before and pk.active_approval(db, pk.latest_package(db, app.id)) is None:
            invalidated += 1
    db.refresh(entry)
    return entry, True, invalidated


def history(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID) -> list[dict] | None:
    entry = db.scalar(
        select(AnswerBankEntry).where(
            AnswerBankEntry.id == entry_id, AnswerBankEntry.user_id == user_id
        )
    )
    if entry is None:
        return None
    rows = db.scalars(
        select(FactVersion)
        .where(
            FactVersion.user_id == user_id,
            FactVersion.entity_type == ENTITY,
            FactVersion.entity_id == entry_id,
        )
        .order_by(FactVersion.version.desc())
    ).all()
    out = [
        {
            "version": r.version,
            "value": r.snapshot["value"],
            "how": r.snapshot["how"],
            "recorded_at": r.created_at,
        }
        for r in rows
    ]
    if not any(r["version"] == entry.version for r in out):  # saved before history was kept
        out.insert(
            0,
            {
                "version": entry.version,
                "value": entry.value,
                "how": IMPORTED if entry.provenance == Provenance.import_ else FIRST,
                "recorded_at": entry.updated_at,
            },
        )
    return out
