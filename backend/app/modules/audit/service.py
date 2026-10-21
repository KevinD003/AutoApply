"""Append-only audit events, limited to safe metadata.

`meta` may carry only short identifier-like values: internal ids, provider keys, adapter
versions, route decisions, reason codes, evidence levels, authorization states, counts and
flags. Anything else is dropped before it is stored:

  * a key naming sensitive material (password, token, cookie, session, email, phone, name,
    title, url, employer, filename, answer, content, raw payloads, exceptions, ...) is
    replaced by "[redacted]";
  * a value that is not a bool, a number, None, or a short identifier-like string (letters,
    digits, `_ . : - +`, at most 64 characters), or a short list of those, is replaced by
    "[omitted]": free text, URLs, e-mail addresses, exception messages and nested objects
    never reach the table;
  * external identifiers (for example a posting's question key) are passed through `ref()`,
    which stores a short one-way reference instead of the identifier. A `field` key always
    holds such a key, so it is stored as `field_ref` (an explicit `field_ref` wins).

`sanitize` is idempotent; `repair.py` applies it to rows stored before it existed."""

import hashlib
import re
import uuid

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent

_DENY_TOKENS = {
    "password", "passwd", "token", "secret", "cookie", "cookies", "authorization", "auth",
    "header", "headers", "session", "otp", "email", "phone", "address", "name", "title", "url",
    "uri", "origin", "host", "employer", "company", "filename", "file", "files", "attachment",
    "attachments", "answer", "value", "text", "content", "resume", "cv", "body", "payload",
    "raw", "exception", "traceback", "message", "detail",
}  # fmt: skip
_DENY_EXACT = {"code"}  # a verification code; "reason_code" stays allowed
_ALLOW_EXACT = {"content_hash"}  # a package's one-way hash, not its content
_SAFE_STR = re.compile(r"^[A-Za-z0-9_.:+\-]{0,64}$")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{0,64}$")
MAX_LIST = 20
_REFERENCE_KEYS = {"field": "field_ref"}


def ref(value: object) -> str:
    """A short one-way reference for an external identifier (never reversible to it)."""
    return "ref:" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _denied(key: str) -> bool:
    k = key.lower()
    if k in _ALLOW_EXACT:
        return False
    return k in _DENY_EXACT or bool(set(re.split(r"[^a-z0-9]+", k)) & _DENY_TOKENS)


def _safe_scalar(v: object) -> bool:
    if v is None or isinstance(v, bool | int | float):
        return True
    return isinstance(v, str) and bool(_SAFE_STR.match(v))


def _safe_value(v: object) -> object:
    if isinstance(v, list | tuple) and len(v) <= MAX_LIST and all(_safe_scalar(x) for x in v):
        return list(v)
    return v if _safe_scalar(v) else "[omitted]"


def sanitize(meta: dict) -> dict:
    out: dict = {}
    for k, v in meta.items():
        if not (isinstance(k, str) and _SAFE_KEY.match(k)):
            continue
        if k in _REFERENCE_KEYS:
            k, v = _REFERENCE_KEYS[k], (ref(v) if isinstance(v, str) else "[omitted]")
            if k in meta:
                continue
        out[k] = "[redacted]" if _denied(k) else _safe_value(v)
    return out


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
            meta=sanitize(meta),
        )
    )
