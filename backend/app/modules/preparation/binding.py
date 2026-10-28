"""C7 (D60): what an answer or a consent was given for.

Each answer and consent records the fingerprint of the question as it was when you gave it
(`forms.field_fingerprint`: wording, help text, type, requirement, options, condition). A
"disclose" choice also records a keyed digest of the exact answer it covers, so a changed answer
needs the choice again; the digest is an HMAC under the server's reference key, scoped to you and
the question, so the stored row never holds a copy of the sensitive answer."""

import json

from app.modules.audit.service import keyed_digest
from app.modules.preparation.forms import FormField, field_fingerprint

_VALUE_DOMAIN = b"noefforts.consent-value.v1"


def question_fp(f: FormField) -> str:
    return field_fingerprint(f)


def value_digest(owner: object, key: str, value: dict | None) -> str:
    return keyed_digest(_VALUE_DOMAIN, owner, key, json.dumps(value, sort_keys=True))[:32]


def input_meta(f: FormField, meta: dict | None = None) -> dict:
    """The meta stored with an answer or consent: anything it already carries (an accepted
    draft's evidence) plus the question's fingerprint."""
    return {**(meta or {}), "field_fp": question_fp(f)}
