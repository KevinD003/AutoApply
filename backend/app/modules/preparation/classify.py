"""Deterministic question classification. No LLM is involved.

The classifier decides *what a question means* (intent + parameters). When wording is
negated, tense is unclear, or a country is not named, it returns an explicit `ambiguity`
instead of guessing, and the resolver turns that into a user checkpoint.
"""

import re
from dataclasses import dataclass, field

from app.modules.preparation.forms import FieldType, FormField, normalize

# ISO code -> lowercase names/aliases used in questions and option labels.
COUNTRIES: dict[str, tuple[str, ...]] = {
    "US": ("united states", "united states of america", "usa", "u.s.", "u.s.a.", "us", "america"),
    "CA": ("canada",),
    "GB": ("united kingdom", "uk", "u.k.", "great britain", "britain", "england"),
    "IN": ("india",),
    "AU": ("australia",),
    "NZ": ("new zealand",),
    "IE": ("ireland",),
    "DE": ("germany", "deutschland"),
    "FR": ("france",),
    "NL": ("netherlands", "the netherlands"),
    "ES": ("spain",),
    "IT": ("italy",),
    "SE": ("sweden",),
    "CH": ("switzerland",),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae"),
    "MX": ("mexico",),
    "BR": ("brazil",),
    "PH": ("philippines",),
    "NG": ("nigeria",),
    "ZA": ("south africa",),
    "JP": ("japan",),
    "PL": ("poland",),
    "PT": ("portugal",),
}

_NEG = re.compile(r"\b(not|never|no longer)\b|n't\b")
_SENSITIVE = re.compile(
    r"\b(gender|sex|pronouns?|race|racial|ethnicity|ethnic|hispanic|latin[oax]|veteran|"
    r"disabilit(y|ies)|disabled|sexual orientation|transgender|lgbt\w*|religion|religious|"
    r"marital|date of birth|birth ?date|age)\b"
)
_ACK = re.compile(
    r"\b(i (hereby )?(certify|attest|acknowledge|agree|consent|understand|confirm|declare)|"
    r"i have read|terms (of|and)|privacy (policy|notice|statement)|background (check|screening)|"
    r"(do you )?consent to|drug (test|screen)|credit check|by checking this box)\b"
)
_LONG_FORM = re.compile(
    r"^(why|describe|tell us|explain|what (interests|excites|motivates)|how would you|"
    r"please (describe|explain|share|tell)|cover letter)\b"
)
_AUTH = re.compile(
    r"\b(authori[sz]ed|eligible|legally (able|permitted)|right) to work\b|"
    r"\bwork (authori[sz]ation|permit|eligibility)\b"
)
_SPONSOR = re.compile(r"\bsponsor(ship)?\b|\bvisa\b")
_WITHOUT_SPONSOR = re.compile(
    r"\bwithout (the need for |requiring |needing )?(any )?"
    r"(visa |employment |immigration )?sponsorship\b"
)
_NOW_OR_FUTURE = re.compile(
    r"\b(now|currently|presently) or (at any time )?in the future\b|"
    r"\bnow or future\b|\bnow,? or will you\b|\bat any (point|time)\b"
)
_FUTURE = re.compile(r"\b(in the future|future|later|eventually)\b")
_NOW = re.compile(r"\b(now|currently|presently|at this time|at present|today)\b")
_PRESENT_REQUIRE = re.compile(r"\b(do|does) you (not )?(currently )?(require|need)\b")
_WHERE_JOB_IS = re.compile(
    r"\b(this|the) (country|location|position|role|job)\b|"
    r"where (this|the) (job|role|position) is"
)


@dataclass
class Intent:
    kind: str
    params: dict = field(default_factory=dict)
    sensitive: bool = False
    acknowledgment: bool = False
    ambiguity: str | None = None  # set => must ask the user


def find_countries(text: str) -> list[str]:
    t = f" {normalize(text)} "
    found = []
    for code, names in COUNTRIES.items():
        for n in names:
            # word-boundary match; short codes like "us" only when written as a country token
            pat = rf"(?<![a-z]){re.escape(n)}(?![a-z])"
            if n == "us":
                pat = r"(?<![a-z])(the )?u\.?s\.?(?![a-z])"
                if not re.search(r"\b(in|the) us\b|\bu\.s\.", t):
                    continue
            if re.search(pat, t):
                found.append(code)
                break
    return found


def _negation_count(text: str) -> int:
    return len(_NEG.findall(text))


def classify(f: FormField) -> Intent:
    label = normalize(f.label)
    context = normalize(f"{f.label} {f.help_text or ''}")

    if _SENSITIVE.search(label) and not _AUTH.search(label):
        return Intent("demographic", {"topic": _SENSITIVE.search(label).group(0)}, sensitive=True)

    if f.type == FieldType.checkbox or _ACK.search(label):
        if _ACK.search(label) or f.type == FieldType.checkbox:
            return Intent("acknowledgment", acknowledgment=True)

    if f.type == FieldType.file:
        if re.search(r"cover letter", label):
            return Intent("cover_letter_upload")
        if re.search(r"\b(resume|résumé|cv|curriculum)\b", label):
            return Intent("resume_upload")
        return Intent("file_other")

    if _AUTH.search(label) or _SPONSOR.search(label):
        return _classify_eligibility(f, label, context)

    simple = [
        (r"^(legal )?first name$|^given name$", "given_name"),
        (r"^(legal )?last name$|^(family name|surname)$", "family_name"),
        (r"^(legal )?(full )?name$", "full_name"),
        (r"^preferred (first )?name$", "preferred_name"),
        (r"^e-?mail( address)?$", "email"),
        (r"^(phone|mobile|telephone)( number)?$", "phone"),
        (r"^linkedin( profile| url| profile url)?$", "linkedin"),
        (r"^(website|portfolio|personal website)( url)?$", "website"),
        (
            r"^(current )?(city|location \(city\)|location|city of residence|current location)$",
            "residence_city",
        ),
        (r"^(state|province|region)( of residence)?$", "residence_region"),
        (
            r"^(country|country of residence|current country|country you live in)$",
            "residence_country",
        ),
        (r"\b(willing|able|open) to relocate\b", "relocation"),
        (
            r"\b(desired|expected|expectation|target)\b.*\b(salary|compensation|pay)\b|"
            r"\bsalary (expectation|requirement)s?\b",
            "salary_expectation",
        ),
    ]
    for pat, kind in simple:
        if re.search(pat, label):
            if kind == "salary_expectation":
                return Intent(kind, {"currencies": re.findall(r"\b[a-z]{3}\b", label)})
            return Intent(kind)

    if re.search(r"\b(preferred|desired|which) (work |office )?(location|office|city)\b", label):
        return Intent(
            "location_preference",
            ambiguity="Asks which location you want — a choice for this job, not your residence.",
        )

    if f.type == FieldType.textarea or _LONG_FORM.search(label):
        return Intent("long_form")
    return Intent("unknown")


def _classify_eligibility(f: FormField, label: str, context: str) -> Intent:
    countries = find_countries(context)
    country = countries[0] if len(countries) == 1 else None
    params: dict = {"country": country}
    if len(countries) > 1:
        return Intent("eligibility", params, ambiguity="Mentions more than one country.")
    if country is None and _WHERE_JOB_IS.search(label):
        return Intent(
            "eligibility",
            params,
            ambiguity="Refers to 'the country where this job is' without naming it.",
        )
    if country is None:
        return Intent("eligibility", params, ambiguity="Does not say which country it is about.")

    if _WITHOUT_SPONSOR.search(label):
        rest = _WITHOUT_SPONSOR.sub(" ", label)
        if _negation_count(rest):
            return Intent(
                "authorized_without_sponsorship",
                params,
                ambiguity="Negated wording around 'without sponsorship'.",
            )
        return Intent("authorized_without_sponsorship", params)

    negations = _negation_count(label)
    if _SPONSOR.search(label) and _AUTH.search(label):
        return Intent(
            "eligibility",
            params,
            ambiguity="Asks about authorization and sponsorship in one question.",
        )
    if _SPONSOR.search(label):
        if _NOW_OR_FUTURE.search(label):
            timeframe = "now_or_future"
        elif _FUTURE.search(label) and not _NOW.search(label):
            timeframe = "future"
        elif _NOW.search(label) or _PRESENT_REQUIRE.search(label):
            timeframe = "now"
        else:
            return Intent(
                "sponsorship",
                params,
                ambiguity="Unclear whether it asks about sponsorship now or later.",
            )
        params["timeframe"] = timeframe
        if negations == 0:
            return Intent("sponsorship", params | {"negated": False})
        if negations == 1 and re.search(
            r"\b(do|does|will|would) you not (require|need)\b|"
            r"\b(don't|won't) you (require|need)\b",
            label,
        ):
            return Intent("sponsorship", params | {"negated": True})
        return Intent(
            "sponsorship", params, ambiguity="Negated wording that cannot be read safely."
        )

    if _AUTH.search(label):
        if f.type in (FieldType.radio, FieldType.select) and not _looks_yes_no(f):
            return Intent(
                "authorization_status",
                params,
                ambiguity="Asks for a status category, not yes/no; choose the option "
                "that matches your situation.",
            )
        if negations == 0:
            return Intent("work_authorization", params | {"negated": False})
        if negations == 1 and re.search(
            r"\b(are|is) you not (legally )?(authori[sz]ed|eligible)\b", label
        ):
            return Intent("work_authorization", params | {"negated": True})
        return Intent(
            "work_authorization", params, ambiguity="Negated wording that cannot be read safely."
        )
    return Intent("eligibility", params, ambiguity="Unrecognised eligibility wording.")


YES_WORDS = {
    "yes",
    "y",
    "true",
    "i am",
    "i do",
    "i will",
    "i agree",
    "agree",
    "accept",
    "i accept",
    "i consent",
    "consent",
}
NO_WORDS = {
    "no",
    "n",
    "false",
    "i am not",
    "i do not",
    "i don't",
    "i will not",
    "i won't",
    "i do not agree",
    "decline",
    "i decline",
    "i do not consent",
}


def _looks_yes_no(f: FormField) -> bool:
    labels = {normalize(o.label) for o in f.options}
    return bool(labels & YES_WORDS) and bool(labels & NO_WORDS)
