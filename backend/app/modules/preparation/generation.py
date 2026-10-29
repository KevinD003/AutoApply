"""Tailored resumes and cover letters (L2, L3; D73), written only through the drafting provider.

No provider is configured (drafting.get_provider() returns None), so nothing is generated in
any environment yet; L4 adds one, with server-side credentials and a consent screen. What is in
place is everything around it:

- a request is a drafting.DraftRequest built from the user's approved facts and the job's own
  text (quoted as untrusted, drafting.prompt), never from the base resume's text;
- the result passes every C15 and C16 check (numbers and credentials only from cited facts, no
  legal status or sensitive topic) and a length limit per kind;
- it is stored as a DOCX document, `generated`, written for one application, with the ids and
  the hash of the facts it cites, and is used by nothing until the user accepts it;
- it stops being usable when a fact it cites changes, and is never used for another
  application.
"""

import io
import zipfile
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.modules.documents.models import Document, DocumentKind
from app.modules.preparation import drafting

KINDS = {
    # kind: (document kind, character limit, noun)
    "resume": (DocumentKind.resume, 6000, "resume"),
    "cover_letter": (DocumentKind.cover_letter, 3500, "cover letter"),
}

# C18/L2 (D73): why a document cannot be chosen for an application; "(reason: code)".
REFUSALS = {
    "document_not_accepted": "This document was generated and you have not accepted it yet; "
    "nothing was changed.",
    "document_for_another_application": "This document was written for another application; "
    "nothing was changed.",
    "document_facts_changed": "Facts this document relied on have changed; generate a new one. "
    "Nothing was changed.",
}

_CT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships'
    '+xml"/><Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/></Types>'
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(text: str) -> bytes:
    """A minimal DOCX: one paragraph per line, the text escaped (never markup)."""
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
        for line in text.splitlines()
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def request_for(job, kind: str, facts) -> drafting.DraftRequest:
    _, limit, noun = KINDS[kind]
    return drafting.DraftRequest(
        question=f"Write a {noun} for this job, using only the facts given.",
        help_text=None,
        max_chars=limit,
        employer=job.employer,
        job_title=job.title,
        job_text=(job.description or "")[:6000] or None,
        facts=facts,
    )


def is_stale(db: Session, doc: Document) -> bool:
    """A cited fact is no longer an approved fact of this user, or has changed."""
    if doc.origin != "generated" or not doc.grounded_on:
        return False
    used = drafting.cited(drafting.grounding_facts(db, doc.user_id), doc.grounded_on)
    return used is None or drafting.grounding_hash(used) != doc.grounding_hash


def refusal(db: Session, doc: Document, app_id) -> str | None:
    """Why `doc` cannot be used for application `app_id` now, or None. An upload always can."""
    if doc.origin != "generated":
        return None
    if doc.accepted_at is None:
        return "document_not_accepted"
    if doc.made_for_application_id is not None and doc.made_for_application_id != app_id:
        return "document_for_another_application"
    if is_stale(db, doc):
        return "document_facts_changed"
    return None
