"""Reduce a message to the text of its CURRENT message (spec §6): drop quoted reply history and
keep the forwarded body of a forward, so a classification reads what this message says and not,
for example, a rejection quoted from an earlier reply in the thread.

Deterministic and content-free in result: it only trims the already-extracted plain text
(provider._text_of), which has had its whitespace collapsed to single spaces (so quoted blocks
are detected by inline markers, never by leading ">"/line prefixes). Nothing here is stored; the
caller passes the trimmed text to the fixed-wording classifier and keeps no message text."""

import re

# A reply's quoted history begins at one of these inline markers (Gmail / Outlook / Apple Mail).
# Everything from the FIRST such marker on is prior history, not this message.
_REPLY_QUOTE = re.compile(
    r"(?i)\bon\s.{0,160}?\bwrote:"  # "On Tue, 3 Nov 2026 at 09:00, Acme <x@acme> wrote:"
    r"|-{2,}\s*original message\s*-{2,}"  # "----- Original Message -----"
    r"|\bfrom:\s.{0,120}?\bsent:\s"  # a quoted Outlook header run "From: … Sent: …"
    r"|\breply\s+above\s+this\s+line\b"  # ticketing/ATS reply-above-the-line separators
)

# A forward wraps another message; its real content is the forwarded body. The wrapper ("FYI",
# "see below") carries no recruitment meaning, so for a forward we keep what follows the marker.
_FORWARD = re.compile(
    r"(?i)-{2,}\s*forwarded message\s*-{2,}"
    r"|\bbegin forwarded message:"
    r"|\bforwarded message\b"
)
_FWD_SUBJECT = re.compile(r"(?i)^\s*(fwd?|fw)\s*:")


def current_text(subject: str, text: str) -> str:
    """The text of the current message: the forwarded body when this is a forward, else the new
    reply text above the quoted history. Falls back to the whole text if trimming would empty it
    (never classify nothing because a boundary was over-eager)."""
    if not isinstance(text, str) or not text:
        return text or ""

    start = 0
    is_forward = bool(_FWD_SUBJECT.search(subject or ""))
    fwd = _FORWARD.search(text)
    if fwd:
        is_forward = True
        start = fwd.end()  # keep the forwarded body, drop the "FYI" wrapper

    body = text[start:]
    # Cut the reply-quoted history. In a forward we also cut any quote nested inside the
    # forwarded body, so a forwarded reply is read by its newest forwarded message.
    q = _REPLY_QUOTE.search(body)
    if q:
        body = body[: q.start()]

    trimmed = body.strip()
    if trimmed:
        return trimmed
    # Over-eager boundary (e.g. a forward whose body was itself one quoted block): rather than
    # classify an empty string, fall back to the portion before the first reply-quote of the
    # whole message, and finally to the whole message.
    whole_q = _REPLY_QUOTE.search(text)
    if whole_q and text[: whole_q.start()].strip() and not is_forward:
        return text[: whole_q.start()].strip()
    return text.strip()
