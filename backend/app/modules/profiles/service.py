import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from app.modules.profiles.models import Approval, FactVersion, Provenance


def _jsonable(v: object) -> object:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Decimal):
        return float(v)
    return v


def snapshot(obj: object, fields: list[str]) -> dict:
    return {f: _jsonable(getattr(obj, f)) for f in fields}


def apply_fact_update(
    db: Session,
    obj,
    data: dict,
    *,
    entity_type: str,
    provenance: Provenance = Provenance.user_entered,
) -> bool:
    """Apply `data` to a fact row. Bumps version and writes history only if something changed.

    User-entered changes are approved by definition; machine proposals (e.g. resume parsing)
    must go through `provenance=resume_parse`, which leaves the row proposed for review.
    """
    changed = {k: v for k, v in data.items() if getattr(obj, k) != v}
    is_new = obj.id is None
    if not changed and not is_new:
        return False
    for k, v in data.items():
        setattr(obj, k, v)
    obj.provenance = provenance
    obj.approval_status = (
        Approval.approved if provenance == Provenance.user_entered else Approval.proposed
    )
    obj.version = 1 if is_new else (obj.version or 0) + 1
    db.add(obj)
    db.flush()
    db.add(
        FactVersion(
            user_id=obj.user_id,
            entity_type=entity_type,
            entity_id=obj.id,
            version=obj.version,
            snapshot=snapshot(obj, list(data.keys()))
            | {"provenance": provenance.value, "approval_status": obj.approval_status.value},
        )
    )
    return True
