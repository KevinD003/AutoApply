"""Text from an uploaded document (L1, D72): PDF, DOCX or TXT, never more than a bounded amount.

The file is the user's own upload and still untrusted input: a PDF is read for at most
MAX_PAGES pages, a DOCX's document part for at most MAX_XML_BYTES once unzipped (a zip bomb
stops there), and the text kept is cut at MAX_CHARS. Nothing here runs a macro, follows a link
or fetches anything; no text is stored by this module.
"""

import io
import re
import zipfile
from xml.etree import ElementTree

MAX_PAGES = 10
MAX_XML_BYTES = 5_000_000
MAX_CHARS = 60_000
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ExtractError(ValueError):
    """`code` is a fixed reason code, safe to record and show."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def extract_text(content_type: str, data: bytes) -> str:
    if content_type == "text/plain":
        text = data.decode("utf-8", errors="replace")
    elif content_type == DOCX:
        text = _docx(data)
    elif content_type == "application/pdf":
        text = _pdf(data)
    else:
        raise ExtractError("NoEfforts reads text from PDF, DOCX and TXT files only.", "unsupported")
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    out = "\n".join(line for line in lines if line)[:MAX_CHARS]
    if not out:
        raise ExtractError("No text could be read from this document.", "no_text")
    return out


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise ExtractError("This document is too large to read.", "too_large")
            with z.open(info) as f:
                xml = f.read(MAX_XML_BYTES + 1)
    except (zipfile.BadZipFile, KeyError):
        raise ExtractError("This file is not a readable DOCX document.", "unreadable") from None
    if len(xml) > MAX_XML_BYTES:
        raise ExtractError("This document is too large to read.", "too_large")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise ExtractError("This file is not a readable DOCX document.", "unreadable") from None
    paragraphs = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append(" ")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractError("This PDF is password-protected; NoEfforts does not open it.",
                               "encrypted")  # fmt: skip
        return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
    except ExtractError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError):
        raise ExtractError("This file is not a readable PDF.", "unreadable") from None
