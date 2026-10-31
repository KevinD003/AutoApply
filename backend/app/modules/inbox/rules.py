"""D101: what an email from an employer or its application system says, by fixed wording rules (no
LLM). A message is `code`, `rejected`, `interview`, `assessment`, `received`, `unclear` (it reads
as more than one of these: never guessed) or `other`. A classification is only ever proposed to
you as an outcome; you confirm it (D53: outcomes are what you report, never inferred).

A verification code is taken only when the message reads as a code email and exactly one
code-shaped token follows the word "code"; otherwise there is no code."""

import re

from app.modules.preparation.forms import normalize

_CODE_MAIL = re.compile(
    r"\b(security|verification|one[- ]time|confirmation|access) code\b|\bpasscode\b|"
    r"\bverify your (email|identity|application)\b|\bcode to (verify|confirm|continue)\b"
)
_REJECTED = re.compile(
    r"\b(not (be )?(moving|move|proceed\w*) forward|decided (not )?to (move|proceed) forward with "
    r"other|move forward with other candidates|pursue other candidates|other candidates whose|"
    r"regret to inform|will not be (moving|proceeding)|unable to offer you|not been selected|"
    r"were not selected|position has (been filled|been closed)|no longer under consideration)\b"
)
_INTERVIEW = re.compile(
    r"\b(schedule (an|a|your) (interview|call|phone screen|conversation)|invite you to (an |a )?"
    r"(interview|phone screen|call)|interview invitation|invitation to interview|like to (speak|"
    r"talk|chat|meet) with you|availability for (an|a) (interview|call)|phone screen|"
    r"next (step|round) (is|will be) (an|a) (interview|call))\b"
)
_ASSESSMENT = re.compile(
    r"\b(online assessment|skills? assessment|coding (challenge|assessment|test)|take[- ]home|"
    r"hackerrank|codility|codesignal|testgorilla|hirevue|assessment link|complete (the|an|this) "
    r"assessment|case study)\b"
)
_RECEIVED = re.compile(
    r"\b(thank you for (applying|your application|submitting)|thanks for applying|we('ve| have) "
    r"received your application|your application (has been|was) (received|submitted)|"
    r"application (received|confirmation))\b"
)
_TOKEN = re.compile(r"(?<![\w-])([A-Z0-9]{4,10}|\d{4,10})(?![\w-])")


def classify(subject: str, text: str) -> str:
    t = normalize(f"{subject} . {text}")
    if _CODE_MAIL.search(t):
        return "code"
    hits = [k for k, p in (("rejected", _REJECTED), ("interview", _INTERVIEW),
                           ("assessment", _ASSESSMENT)) if p.search(t)]  # fmt: skip
    if len(hits) > 1:
        return "unclear"
    if hits:
        return hits[0]
    return "received" if _RECEIVED.search(t) else "other"


def extract_code(subject: str, text: str) -> str | None:
    """The one code in a code email, or None (none, or more than one candidate)."""
    if classify(subject, text) != "code":
        return None
    found = set()
    for m in re.finditer(r"(?i)\b(code|passcode)\b", text):
        window = text[m.end() : m.end() + 120]
        found |= {c for c in _TOKEN.findall(window) if any(ch.isdigit() for ch in c)}
    return found.pop() if len(found) == 1 else None


def mentions(employer: str, sender_name: str, subject: str, text: str) -> bool:
    """The employer's name, as you saved it, appears as whole words in the sender's name, the
    subject or the text."""
    name = normalize(employer or "")
    name = re.sub(r"\s*\((fictional|example)\)$", "", name).strip()
    if len(name) < 3:
        return False
    pat = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")
    return any(pat.search(normalize(x)) for x in (sender_name, subject, text))
