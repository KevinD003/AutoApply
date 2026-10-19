import uuid

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent

_REDACT_KEYS = {"password", "token", "code", "otp", "cookie", "secret", "authorization"}


def _redact(meta: dict) -> dict:
    return {k: ("[redacted]" if k.lower() in _REDACT_KEYS else v) for k, v in meta.items()}


def record(
    db: Session,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    **meta: object,
) -> None:
    db.add(
        AuditEvent(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            meta=_redact(meta),
        )
    )
