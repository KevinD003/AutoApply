"""What an email from an employer or its application system says, by fixed wording rules (no LLM,
spec §2), and which of your applications it is about, by multiple deterministic signals (spec §1).

Two confidences are kept apart (spec): the CLASSIFICATION band (how clearly the wording names one
recruitment event) and the MATCH band (how strongly the message identifies one application). A
classification is only ever proposed to you as an outcome; you confirm it (D53: outcomes are what
you report, never inferred). When either is weak or ambiguous, nothing is proposed — the message
becomes a "review" item for you to resolve.

A verification code is taken only when the message reads as a code email and exactly one
code-shaped token follows the word "code"; otherwise there is no code (unchanged, D117)."""

import re
from dataclasses import dataclass

from app.modules.preparation.forms import normalize

# ── Verification codes (D117, unchanged) ──────────────────────────────────────────────────────
_CODE_MAIL = re.compile(
    r"\b(security|verification|one[- ]time|confirmation|access) code\b|\bpasscode\b|"
    r"\bverify your (email|identity|application)\b|\bcode to (verify|confirm|continue)\b"
)
_TOKEN = re.compile(r"(?<![\w-])([A-Z0-9]{4,10}|\d{4,10})(?![\w-])")
_STATED = re.compile(
    r"(?i)\bcode(?:\s+is)?\s*[:\-]\s*([A-Za-z0-9]{6,10})\b"
    r"|\bcode\s+is\s+([A-Za-z0-9]{6,10})\b"
    r"|\b(?:security|verification) code\b[^:\n]{0,80}:\s*([A-Za-z0-9]{6,10})\b"
)
_LINKS = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+")
_NOT_CODES = {
    "security", "verified", "response", "question", "position", "download", "feedback",
    "regarded", "personal", "complete", "continue", "resubmit", "applying", "required",
    "district", "business", "expires", "minutes", "application", "below", "please",
}  # fmt: skip

# ── Recruitment-event wording (spec §2). Each is a fixed, conservative pattern. ────────────────
_REJECTED = re.compile(
    r"\b(not (be )?(moving|move|proceed\w*) forward|decided (not )?to (move|proceed) forward with "
    r"other|move forward with other candidates|pursue other candidates|other candidates whose|"
    r"regret to inform|will not be (moving|proceeding)|unable to offer you|not been selected|"
    r"were not selected|not (be )?selected for|position has (been filled|been closed)|"
    r"no longer under consideration|not to proceed with your application|"
    r"decided not to move forward)\b"
)
_OFFER = re.compile(
    r"\b(pleased to (make|extend|offer) you|would like to (make|extend) you an offer|"
    r"offer you the (position|role|job)|offer of employment|formal (job )?offer|"
    r"(thrilled|pleased|excited|happy) to offer you|extend (an|our|you an) offer|"
    r"(a |your )?job offer\b|letter of offer|offer letter)\b"
)
_INTERVIEW = re.compile(
    r"\b(schedule (an|a|your) (interview|call|phone screen|conversation)|invite you to (an |a )?"
    r"(interview|phone screen|call)|interview invitation|invitation to interview|like to (speak|"
    r"talk|chat|meet) with you|availability for (an|a) (interview|call)|phone screen|"
    r"set up (an?|a time for an?) (interview|call)|next (step|round) (is|will be) (an|a) "
    r"(interview|call)|would like to interview you)\b"
)
_INTERVIEW_SCHEDULED = re.compile(
    r"\b(your interview (is|has been|was) (scheduled|confirmed|booked|set)|"
    r"interview (is |has been )?confirmed|confirming your interview|"
    r"you are (scheduled|booked|confirmed) for (an?|your) (interview|call|phone screen)|"
    r"your interview is on\b|this confirms your interview)\b"
)
_INTERVIEW_RESCHEDULED = re.compile(
    r"\b(reschedul\w*|moved your interview|new time for (your|the) interview|"
    r"change the time of (your|the) interview)\b"
)
_INTERVIEW_CANCELLED = re.compile(
    r"\b(cancel\w* (your|the|this) interview|your interview (has been|is|was) cancel\w*|"
    r"(have|had|need) to cancel (your|the|our) (interview|call|meeting))\b"
)
_ASSESSMENT = re.compile(
    r"\b(online assessment|skills? assessment|coding (challenge|assessment|test)|take[- ]home|"
    r"hackerrank|codility|codesignal|testgorilla|hirevue|assessment link|complete (the|an|this) "
    r"assessment|case study|technical (screen|assessment|challenge))\b"
)
_ASSESSMENT_REMINDER = re.compile(
    r"\b(reminder[^.]{0,40}(assessment|test|challenge)|(assessment|test|challenge)[^.]{0,40}"
    r"reminder|don'?t forget[^.]{0,40}(assessment|test)|your assessment (is )?(still )?(pending|"
    r"outstanding|due|waiting)|complete your assessment before|final reminder)\b"
)
_NEXT_ROUND = re.compile(
    r"\b(next round|move you (forward|to the next)|advance you to|invite you to the next "
    r"(stage|round|step)|final round|second (round|interview)|next stage of (the|our) "
    r"(process|interview)|progress to the next)\b"
)
_INFO_REQUESTED = re.compile(
    r"\b(additional (information|documents|details)[^.]{0,30}(required|requested|needed)|"
    r"please (provide|send|upload|complete|share) (your|the|a|this|us)|we (need|require) "
    r"(a few|some|more|the following|additional|further)|to (proceed|continue),? we "
    r"(need|require)|could you (please )?(provide|send|share) (us |your )|background check "
    r"(form|information|authorization))\b"
)
_UNDER_REVIEW = re.compile(
    r"\b(under review|being reviewed|currently review\w*|review\w* your application|in review|"
    r"your application is (now )?(being|under)|reviewing applications|has been received and is "
    r"(being|under)|team is reviewing)\b"
)
_TALENT_POOL = re.compile(
    r"\b(talent (pool|community|network)|keep your (resume|cv|application|details) on file|"
    r"future (roles|openings|opportunities)|consider you for (future|other|upcoming)|added you "
    r"to our (talent|candidate)|join our talent)\b"
)
_POSITION_CLOSED = re.compile(
    r"\b(position (has been|is now|was) (cancelled|canceled|put on hold|withdrawn|placed on "
    r"hold)|role (has been|is now|was) (cancelled|canceled|withdrawn|put on hold)|requisition "
    r"[^.]{0,20}(cancelled|canceled|closed|withdrawn)|this (position|role|opening) is no longer "
    r"(open|available|being filled)|no longer accepting applications|job posting (has been|was) "
    r"(removed|closed|cancelled))\b"
)
_WITHDRAWN = re.compile(
    r"\b(your application (has been|was) withdrawn|you (have )?withdrawn your application|"
    r"withdrawal of your application|we have withdrawn your)\b"
)
_RECOMMENDATION = re.compile(
    r"\b(jobs? (you might|we think you)|recommended (jobs?|roles?|for you)|new (jobs?|roles?|"
    r"openings?) (match\w*|for you|that match)|jobs? matching your|based on your (profile|search|"
    r"preferences)|we found \d+ (jobs?|new|roles?)|your job alert|top (picks|jobs) for you|"
    r"apply to these (jobs?|roles?)|recommended for your)\b"
)
_RECEIVED = re.compile(
    r"\b(thank you for (applying|your application|submitting)|thanks for applying|we('ve| have) "
    r"received your application|your application (has been|was) (received|submitted)|"
    r"application (received|confirmation)|successfully (applied|submitted))\b"
)

# Events that map to a reportable application Outcome (service.OUTCOME_OF). Every other event is
# recognised and shown, but changes no status on its own (spec §2: do not invent an internal
# stage; an assessment invite is not completion; a scheduling link is not a booked interview).
OUTCOME_EVENTS = frozenset({
    "rejected", "offer", "withdrawn",
    "interview", "interview_scheduled", "interview_rescheduled", "next_round",
    "assessment", "assessment_reminder",
})  # fmt: skip
# Informational events: recognised and surfaced, never an automatic outcome.
NOTED_EVENTS = frozenset({
    "received", "under_review", "info_requested", "interview_cancelled",
    "position_closed", "talent_pool", "recommendation", "other",
})  # fmt: skip


def classify(subject: str, text: str) -> str:
    """The recognised recruitment event (backward-compatible: the D101 values code/rejected/
    interview/assessment/received/unclear/other are still returned for those inputs)."""
    return classify_detail(subject, text)[0]


def classify_detail(subject: str, text: str) -> tuple[str, str]:
    """(event, classification band). band: 'explicit' (one event named by a decisive phrase),
    'ambiguous' (conflicting events in one message — never guessed), or 'tentative' (no decisive
    recruitment wording). Only an 'explicit' outcome event is ever eligible for an automatic
    update (service.py); everything else is proposed for your review."""
    t = normalize(f"{subject} . {text}")
    if _CODE_MAIL.search(t):
        return "code", "explicit"
    if _RECOMMENDATION.search(t):
        return "recommendation", "explicit"  # a job suggestion is never an application update

    primary = {
        "rejected": bool(_REJECTED.search(t)),
        "offer": bool(_OFFER.search(t)),
        "interview": bool(_INTERVIEW.search(t)),
        "assessment": bool(_ASSESSMENT.search(t)),
        "next_round": bool(_NEXT_ROUND.search(t)),
    }
    hits = {k for k, v in primary.items() if v}
    cancelled = bool(_INTERVIEW_CANCELLED.search(t))
    rescheduled = bool(_INTERVIEW_RESCHEDULED.search(t))
    scheduled = bool(_INTERVIEW_SCHEDULED.search(t))
    reminder = bool(_ASSESSMENT_REMINDER.search(t))
    progress = hits & {"offer", "interview", "assessment", "next_round"}

    # Genuine conflicts in one message are never guessed: they become a review item (spec §2/§3).
    if "rejected" in hits and (progress or scheduled or rescheduled):
        return "unclear", "ambiguous"
    if "offer" in hits and (progress - {"offer"}):
        return "unclear", "ambiguous"

    if cancelled and "rejected" not in hits:
        return "interview_cancelled", "explicit"  # a cancellation is not a rejection (spec §2)
    if rescheduled:
        return "interview_rescheduled", "explicit"
    if "offer" in hits:
        return "offer", "explicit"
    if "rejected" in hits:
        return "rejected", "explicit"
    if "next_round" in hits:
        return "next_round", "explicit"
    if scheduled:
        return "interview_scheduled", "explicit"
    if "interview" in hits:
        return "interview", "explicit"  # an invitation, not a booked interview (spec §2)
    if reminder:
        return "assessment_reminder", "explicit"
    if "assessment" in hits:
        return "assessment", "explicit"  # an invitation, not a completion (spec §2)
    if _WITHDRAWN.search(t):
        return "withdrawn", "explicit"
    if _INFO_REQUESTED.search(t):
        return "info_requested", "explicit"
    if _UNDER_REVIEW.search(t):
        return "under_review", "explicit"
    if _TALENT_POOL.search(t):
        return "talent_pool", "explicit"
    if _POSITION_CLOSED.search(t):
        return "position_closed", "explicit"
    if _RECEIVED.search(t):
        return "received", "explicit"
    return "other", "tentative"


def extract_code(subject: str, text: str) -> str | None:
    """The one code in a code email, or None (none, or more than one candidate). D117, unchanged."""
    if classify(subject, text) != "code":
        return None
    plain = _LINKS.sub(" ", text)
    stated = {a or b or c for a, b, c in _STATED.findall(plain)} - {""}
    stated = {c for c in stated if c.lower() not in _NOT_CODES}
    if len(stated) == 1:
        return stated.pop()
    if len(stated) > 1:
        return None
    found = set()
    for m in re.finditer(r"(?i)\b(code|passcode)\b", plain):
        window = plain[m.end() : m.end() + 120]
        found |= {c for c in _TOKEN.findall(window) if any(ch.isdigit() for ch in c)}
    return found.pop() if len(found) == 1 else None


# ── Employer / title matching helpers (spec §1) ───────────────────────────────────────────────

# Known application-system sending domains. A message from one of these is a legitimate
# application email although its domain is not the employer's own (spec §1: never require the
# sender domain to equal the employer's). Corroborating only — never identifies WHICH application.
ATS_DOMAINS = frozenset({
    "greenhouse-mail.io", "greenhouse.io", "us.greenhouse-mail.io",
    "hire.lever.co", "lever.co",
    "ashbyhq.com", "app.ashbyhq.com",
    "myworkday.com", "myworkdayjobs.com", "workday.com",
    "smartrecruiters.com", "icims.com", "jobvite.com", "bamboohr.com", "successfactors.com",
    "taleo.net", "workable.com", "breezy.hr", "teamtailor.com", "recruitee.com", "rippling.com",
})  # fmt: skip
_TITLE_STOP = {
    "the",
    "and",
    "for",
    "with",
    "job",
    "role",
    "position",
    "opening",
    "team",
    "of",
    "to",
    "at",
    "an",
    "our",
    "your",
    "new",
    "a",
    "in",
    "on",
    "we",
    "are",
    "is",
}
_SENIORITY = re.compile(
    r"\b(senior|sr|junior|jr|lead|principal|staff|associate|entry[- ]level|mid[- ]level|"
    r"i{1,3}|iv|v|intern|internship|contract|contractor|temporary|temp|remote|hybrid|on[- ]?site|"
    r"full[- ]time|part[- ]time)\b"
)


def _clean_employer(employer: str) -> str:
    name = normalize(employer or "")
    name = re.sub(r"\s*\((fictional|example)\)\s*$", "", name).strip()
    # Drop a trailing company suffix so "Acme" matches "Acme Inc." mail and vice versa.
    name = re.sub(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|gmbh|plc|"
                  r"careers|recruiting|talent|hr)\.?\s*$", "", name).strip()  # fmt: skip
    return name


def names_employer(employer: str, subject: str) -> bool:
    """D117: Greenhouse's code email is "Security code for your application to <employer>", so
    overlapping applications are told apart by the employer in the subject."""
    return mentions(employer, "", subject, "")


def mentions(employer: str, sender_name: str, subject: str, text: str) -> bool:
    """The employer's name (as saved, minus a fictional/suffix tail) appears as whole words in the
    sender's name, the subject or the text. By itself this is a WEAK signal (spec §1: never match
    on a company name alone) — see match()."""
    name = _clean_employer(employer)
    if len(name) < 3:
        return False
    pat = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")
    return any(pat.search(normalize(x)) for x in (sender_name, subject, text))


# Generic words that do not distinguish an employer inside a sending domain (and are common in
# the fictional test domains *.example / *.test), so they never, on their own, match a domain.
_DOMAIN_STOP = {
    "example", "test", "fictional", "inc", "corp", "group", "global", "the", "mail", "careers",
    "jobs", "hr", "talent", "team", "company", "co", "ltd", "llc",
}  # fmt: skip


def employer_domain_match(employer: str, sender_domain: str) -> bool:
    """The sender's domain is the employer's own: a DISTINCTIVE employer word is in the domain's
    registrable label, or the whole name is. This is employer identification by the sender's own
    address — stronger than a bare company-name mention in the body (spec §1)."""
    name = _clean_employer(employer)
    dom = (sender_domain or "").lower()
    if len(name) < 3 or not dom:
        return False
    labels = dom.split(".")
    reg = labels[-2] if len(labels) >= 2 else labels[0]
    toks = {w for w in re.split(r"[^a-z0-9]+", name) if len(w) >= 4 and w not in _DOMAIN_STOP}
    if any(t in reg for t in toks):
        return True
    flat = re.sub(r"[^a-z0-9]", "", name)
    return len(flat) >= 6 and flat in re.sub(r"[^a-z0-9]", "", dom)


def _title_core(title: str) -> tuple[str, set[str]]:
    n = _SENIORITY.sub(" ", normalize(title or ""))
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    toks = {w for w in n.split() if len(w) >= 3 and w not in _TITLE_STOP}
    return n, toks


def title_match(title: str, subject: str, text: str) -> bool:
    """The job title identifies the message: its core phrase (seniority words removed) appears, or
    at least two of its significant words do. Guards against a one-common-word coincidence."""
    core, toks = _title_core(title)
    if len(toks) == 0:
        return False
    hay = normalize(f"{subject} . {text}")
    hay = re.sub(r"[^a-z0-9 ]+", " ", hay)
    if len(core) >= 6 and re.search(rf"(?<![\w]){re.escape(core)}(?![\w])", hay):
        return True
    present = {w for w in toks if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", hay)}
    # One significant word is a coincidence; a single-word title must appear in full (above).
    return len(present) >= 2


def _id_tokens(req_id: str | None, url: str | None) -> set[str]:
    """Strong, unique id tokens for an application: its requisition id and the numeric/req id
    segments of its posting URL. These identify exactly one application (spec §1)."""
    ids: set[str] = set()
    if req_id:
        ids |= {t for t in re.findall(r"[a-z0-9][a-z0-9-]{3,}", req_id.lower()) if len(t) >= 4}
    if url:
        low = url.lower()
        ids |= set(re.findall(r"/(\d{5,})(?=/|\b)", low))  # numeric posting id in the path
        ids |= set(re.findall(r"\b(req-?\d{3,}|r\d{4,}|jr\d{4,})\b", low))
    return {i for i in ids if len(i) >= 4 and not i.isalpha()}


def _id_in(idtok: str, subject: str, text: str) -> bool:
    hay = f"{subject} . {text}".lower()
    return re.search(rf"(?<![\w]){re.escape(idtok)}(?![\w])", hay) is not None


@dataclass(frozen=True)
class Candidate:
    """One of the user's submitted applications, as the matcher sees it (no stored message data)."""

    application_id: str
    employer: str
    title: str
    req_id: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class MatchResult:
    application_id: str | None  # the single matched application, or None (abstain → review)
    band: str  # 'strong' | 'good' | 'weak' | 'ambiguous' | 'none'
    basis: tuple[str, ...] = ()  # short codes only (e.g. "requisition_id", "employer+title")
    suggestions: tuple[str, ...] = ()  # candidate application ids for a review item to offer


def match(
    candidates: list[Candidate],
    sender_name: str,
    sender_domain: str,
    subject: str,
    text: str,
    thread_application_id: str | None = None,
) -> MatchResult:
    """Identify the single application a message is about, using several signals together (spec
    §1). Prefers an exact application/requisition id and an established thread link; an employer
    name plus the job title is a good match; an employer name ALONE, a title alone, or two equally
    plausible applications are never chosen (abstain → review). `text` should be the CURRENT
    message (parsing.current_text), not quoted history."""
    ats = (sender_domain or "").lower() in ATS_DOMAINS
    scored = []
    for c in candidates:
        sig: set[str] = set()
        if thread_application_id and c.application_id == thread_application_id:
            sig.add("thread")
        if any(_id_in(tok, subject, text) for tok in _id_tokens(c.req_id, c.url)):
            sig.add("id")
        emp_dom = employer_domain_match(c.employer, sender_domain)
        if mentions(c.employer, sender_name, subject, text) or emp_dom:
            sig.add("employer")  # identified by name in the message, or by the sender's own domain
            if emp_dom:
                sig.add("emp_domain")
        if title_match(c.title, subject, text):
            sig.add("title")
        if sig:
            scored.append((c, sig))
    if not scored:
        return MatchResult(None, "none")

    def basis(sig: set[str]) -> tuple[str, ...]:
        order = ["id", "thread", "employer", "emp_domain", "title"]
        names = {"id": "requisition_id", "thread": "email_thread", "employer": "employer",
                 "emp_domain": "employer_domain", "title": "job_title"}  # fmt: skip
        out = [names[s] for s in order if s in sig]
        if ats:
            out.append("ats_sender")
        return tuple(out)

    # Tier 1 — a unique strong identifier (id or established thread).
    strong = [(c, s) for c, s in scored if s & {"id", "thread"}]
    if len({c.application_id for c, _ in strong}) == 1:
        c, s = strong[0]
        return MatchResult(c.application_id, "strong", basis(s))
    if len({c.application_id for c, _ in strong}) > 1:
        ids = tuple(dict.fromkeys(c.application_id for c, _ in strong))
        return MatchResult(None, "ambiguous", suggestions=ids)

    # Tier 2 — the employer, corroborated. A matching job TITLE identifies a specific application
    # even among several at the same employer, so it is tried first; otherwise the employer's own
    # sending domain, or (for the sole application there) a known ATS sender, corroborates it. An
    # employer name on its own is never enough (spec §1).
    emp = [(c, s) for c, s in scored if "employer" in s]
    titled = [(c, s) for c, s in emp if "title" in s]
    picked = titled or [(c, s) for c, s in emp if ("emp_domain" in s) or (ats and len(emp) == 1)]
    uniq = {c.application_id for c, _ in picked}
    if len(uniq) == 1:
        c, s = picked[0]
        return MatchResult(c.application_id, "good", basis(s))
    if len(uniq) > 1:
        return MatchResult(None, "ambiguous", suggestions=tuple(sorted(uniq)))

    # Tier 3 — only a company name (no corroboration), or only a title: too weak to choose (spec
    # §1). Abstain to a review item that offers the candidates; never pick on a company name alone.
    return MatchResult(
        None, "weak", suggestions=tuple(dict.fromkeys(c.application_id for c, _ in scored))
    )
