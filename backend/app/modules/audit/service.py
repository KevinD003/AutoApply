"""Audit events, limited to safe metadata. Application code never updates or deletes them; the
privacy repair migrations (`repair.py`) rewrite legacy metadata once each.

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
    which stores a keyed, user-scoped reference instead of the identifier. A `field` key
    always holds such a key, so it is stored as `field_ref` (an explicit `field_ref` wins);
  * a legacy unkeyed reference (`ref:` + 12 hex characters, written before version 2) is
    enumerable, so it is never kept: it becomes "[omitted]".

`sanitize` is idempotent; `repair.py` applies it to rows stored before it existed.

References (version 2): `ref:v2:` + the first 32 hex characters of HMAC-SHA-256 over a fixed
domain label, the scope (the user's id) and the identifier, keyed by NOEFFORTS_AUDIT_REF_KEY.
The same identifier gives the same reference for the same user and key, and an unrelated one
for another user or another key. Without the key a reference cannot be recomputed from a list
of candidate identifiers."""

import hashlib
import hmac
import re
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
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
_LEGACY_REF = re.compile(r"^ref:[0-9a-f]{12}$")
REF_PREFIX = "ref:v2:"
_REF_DOMAIN = b"noefforts/audit-ref/v2"
MIN_KEY_CHARS = 32
TEST_KEY_PREFIX = "test-only"


class AuditKeyMissing(RuntimeError):
    """The audit reference key is absent or unusable. The message never includes the key."""


def _key() -> bytes:
    s = get_settings()
    key = s.audit_ref_key.get_secret_value()
    if len(key) < MIN_KEY_CHARS:
        raise AuditKeyMissing(
            f"NOEFFORTS_AUDIT_REF_KEY must be set to a secret of at least {MIN_KEY_CHARS} "
            "characters"
        )
    if s.env == "production" and key.startswith(TEST_KEY_PREFIX):
        raise AuditKeyMissing(
            "NOEFFORTS_AUDIT_REF_KEY is a test-only key; production needs its own"
        )
    return key.encode()


def check_ref_key() -> None:
    """Fail fast (at API start-up and before a repair) when the key is missing or unusable."""
    _key()


def ref(value: object, scope: object) -> str:
    """A keyed reference for an external identifier, scoped to `scope` (the user's id)."""
    msg = b"\0".join([_REF_DOMAIN, str(scope).encode(), str(value).encode()])
    return REF_PREFIX + hmac.new(_key(), msg, hashlib.sha256).hexdigest()[:32]


def _denied(key: str) -> bool:
    k = key.lower()
    if k in _ALLOW_EXACT:
        return False
    return k in _DENY_EXACT or bool(set(re.split(r"[^a-z0-9]+", k)) & _DENY_TOKENS)


def _safe_scalar(v: object) -> bool:
    if v is None or isinstance(v, bool | int | float):
        return True
    return isinstance(v, str) and bool(_SAFE_STR.match(v)) and not _LEGACY_REF.match(v)


def _safe_value(v: object) -> object:
    if isinstance(v, list | tuple) and len(v) <= MAX_LIST and all(_safe_scalar(x) for x in v):
        return list(v)
    return v if _safe_scalar(v) else "[omitted]"


def sanitize(meta: dict, scope: object = None) -> dict:
    """`scope` is the user the event belongs to; it scopes any reference made here."""
    out: dict = {}
    for k, v in meta.items():
        if not (isinstance(k, str) and _SAFE_KEY.match(k)):
            continue
        if k in _REFERENCE_KEYS:
            k, v = _REFERENCE_KEYS[k], (ref(v, scope) if isinstance(v, str) else "[omitted]")
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
            meta=sanitize(meta, scope=user_id),
        )
    )
