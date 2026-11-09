"""D115: what the answer brain compares between a new question and a saved answer's question.

Numbers only: similarities of the wording, the help text and the options, and whether the two
agree on what must never differ. A pair that disagrees on numbers, negation, countries or the
kind of answer is vetoed outright, whatever the model would score: similar wording is not the
same question ("Are you authorized to work in the US?" vs "...in Canada?").

D133: the vetoes read each side's label and help text together, and a word on one side only
vetoes the pair when it is a negation, a unit, a language, a product or a proper noun ("Have you
used Salesforce?" vs "...HubSpot?", "In pounds" vs "In kilograms" in the help text)."""

import functools
import math
import re
import unicodedata
from typing import NamedTuple

from app.modules.preparation.classify import COUNTRIES, find_countries
from app.modules.preparation.forms import normalize

NAMES = (
    "token_jaccard",
    "char3_cosine",
    "help_jaccard",
    "options_jaccard",
    "same_first_word",
    "len_ratio",
    "tokens_new",
    "tokens_saved",
)
_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "you",
    "your", "do", "does", "this", "that", "with", "at", "as", "by", "please", "if", "we", "our",
}  # fmt: skip
# D133: what the vetoes read. Answering instructions say nothing about the question.
_INSTRUCTIONS = re.compile(
    r"[\[(]\s*(?:yes\s*/\s*no|no\s*/\s*yes|y\s*/\s*n|optional|required)\s*[\])]|"
    r"\b(?:yes\s*/\s*no|no\s*/\s*yes)\b|\byes or no\b|"
    r"\bif\s+(?:yes|no|not|so)\b[^.?!]*[.?!]?|"  # "If not, please explain.": what to do next
    r"\b(?:select|choose) one\b|\bselect all that apply\b",
    re.IGNORECASE,
)
_NO_ABBREVIATION = re.compile(r"\bno\.(?=\s*(?:[?:)\]]|$))", re.IGNORECASE)  # "phone no.?"
_APOSTROPHES = str.maketrans(dict.fromkeys("\u2018\u2019\u02bc\u00b4\u0060\u2032", "'"))
_NEG = re.compile(
    r"\b(?:not|no|never|none|nor|neither|without|cannot|lack(?:s|ed|ing)?|unable)\b|n't\b"
)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.'-]*[A-Za-z0-9+#]|[A-Za-z0-9]")
_NOT_CONTENT = {"i", "i'm", "i've", "yes", "no", "ok", "n/a"}
_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "million", "dozen", "half", "twice",
}  # fmt: skip
_NUMBER = re.compile(
    r"(\d+(?:[.,]\d+)?)(\s*[ap]\.?\s*m\b\.?)?|\b("
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")\b"
)
# Countries are compared on their own (find_countries); their names are never content words.
_COUNTRY_NAMES = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(
        re.escape(n)
        for n in sorted({n for ns in COUNTRIES.values() for n in ns if n != "us"}, key=len)[::-1]
    )
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
_US = re.compile(r"(?<![A-Za-z])U\.?S\.?(?:A\.?)?(?![A-Za-z])")  # "us" only as written US/U.S.
# Written in capitals, these are countries; find_countries misses them before a "?" or bare. "US" in
# an all-capitals label ("CONTACT US") is a pronoun.
_ABBREVIATED = re.compile(r"(?<![A-Za-z.])(U\.S\.A\.?|U\.S\.?|USA|US|U\.K\.?|UK)(?![A-Za-z])")

# The word families a difference vetoes on (_differ).
_NEGATORS = {
    "not", "never", "none", "nor", "neither", "without", "cannot", "lack", "lacks", "lacked",
    "lacking", "unable", "fail", "fails", "failed", "refuse", "refuses", "refused", "except",
    "besides", "excluding", "afraid", "dislike", "dislikes", "avoid", "avoids", "prevent",
    "prevents", "prohibited", "forbidden", "restricted",
}  # fmt: skip
_RESTRICTIVE = {"only", "solely", "exclusively"}
_LEVELS = {"basic", "beginner", "intermediate", "advanced", "expert"}
# Words that name one of several alternatives: one side naming none says nothing, but naming a
# different one changes the question ("more than" / "less than", "any" / "all").
ALTERNATIVES = {
    "bound": {
        "more", "less", "fewer", "greater", "least", "most", "above", "below", "over", "under",
        "minimum", "maximum", "max", "exceed", "exceeds", "higher", "lower", "faster", "slower",
    },
    "quantity": {"any", "all", "every", "either", "both"},
    "schedule": {
        "day", "days", "daytime", "night", "nights", "overnight", "evening", "evenings", "morning",
        "mornings", "afternoon", "afternoons", "weekday", "weekdays", "weekend", "weekends",
    },
    "workplace": {"remote", "remotely", "on-site", "onsite", "in-person", "hybrid"},
    "employment": {
        "full-time", "part-time", "fulltime", "parttime", "temporary", "permanent", "contract",
        "seasonal", "freelance", "internship",
    },
}  # fmt: skip
_NEGATED = {
    "unable", "unwilling", "unfamiliar", "uncomfortable", "unaware", "unlicensed",
    "unqualified", "ineligible", "incapable",
}  # fmt: skip
_NEGATING_PREFIXES = ("non-", "non", "dis", "un", "in", "im")
# Never m, g, l or in: one letter is too often something else.
_UNITS = {
    "pound", "pounds", "lb", "lbs", "kilogram", "kilograms", "kg", "kgs", "gram", "grams", "ounce",
    "ounces", "oz", "ton", "tons", "tonne", "tonnes", "foot", "feet", "ft", "inch", "inches", "cm",
    "mm", "meter", "meters", "metre", "metres", "km", "kilometer", "kilometers", "kilometre",
    "kilometres", "mile", "miles", "liter", "liters", "litre", "litres", "gallon", "gallons",
    "second", "seconds", "minute", "minutes", "hour", "hours", "day", "days", "week", "weeks",
    "month", "months", "year", "years", "hr", "hrs", "min", "mins", "wpm", "cpm", "mph", "kph",
    "words", "characters", "keystrokes", "percent", "degrees", "celsius", "fahrenheit",
}  # fmt: skip
_LANGUAGES = {
    "english", "spanish", "french", "german", "mandarin", "cantonese", "chinese", "hindi",
    "urdu", "arabic", "portuguese", "russian", "japanese", "korean", "italian", "dutch",
    "tagalog", "vietnamese", "bengali", "punjabi", "tamil", "telugu", "swahili", "turkish",
    "greek", "hebrew", "farsi", "persian", "python", "java", "javascript", "typescript", "c++",
    "c#", "ruby", "php", "kotlin", "scala", "sql", "perl", "golang", "matlab", "haskell",
    "elixir", "lua", "cobol", "fortran",
}  # fmt: skip
_LANGUAGES_CAPITALISED = {"go", "r", "c", "rust", "swift", "dart", "bash", "polish"}
# Never a word with an ordinary meaning (word, excel, office, teams, zoom ...).
_PRODUCTS = {
    "salesforce", "hubspot", "quickbooks", "tableau", "jira", "figma", "photoshop", "autocad",
    "kubernetes", "servicenow", "zendesk", "netsuite", "marketo", "mailchimp", "shopify", "trello",
    "docker", "terraform", "ansible", "jenkins", "splunk", "databricks", "looker", "sharepoint",
    "wordpress", "magento", "xero", "canva", "solidworks", "revit", "spss", "stata", "mysql",
    "postgresql", "mongodb", "elasticsearch", "kafka", "hadoop", "bigquery",
}  # fmt: skip
_NOT_PROPER = {"URL", "ID", "CV", "PDF", "FAQ", "GPA"}
_ABBREVIATIONS = {"e.g", "i.e", "a.m", "p.m", "etc", "vs"}


def _words(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower().replace("’", "'"))


def _tokens(text: str | None) -> set[str]:
    return {w for w in _words(text) if w not in _STOP}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else (1.0 if not a and not b else 0.0)


def _grams(text: str | None) -> dict[str, int]:
    t = " ".join(_words(text))
    out: dict[str, int] = {}
    for i in range(max(len(t) - 2, 0)):
        g = t[i : i + 3]
        out[g] = out.get(g, 0) + 1
    return out


def _cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    return dot / (na * math.sqrt(sum(v * v for v in b.values())))


class _Token(NamedTuple):
    raw: str
    low: str
    in_label: bool
    first: bool  # the label's first word


class _Side(NamedTuple):
    """One side of a pair as the vetoes read it: its label and help text together."""

    text: str  # lower case, apostrophes folded, answering instructions removed
    numbers: tuple  # in the order written (_numbers)
    negations: tuple  # (in the label, in the help text): compared part by part
    countries: frozenset
    words: frozenset  # content words: not stop words, not countries
    tokens: tuple  # the content words in order, as written (_Token)
    capital_label: bool  # a Title Case or all-capitals label
    foreign: bool  # letters of a script these word lists cannot read


def _fold(text: str | None) -> str:
    folded = _NO_ABBREVIATION.sub("number", (text or "").translate(_APOSTROPHES))
    return _INSTRUCTIONS.sub(" ", folded)


def _numbers(low: str) -> tuple:
    """The numbers in the order written, each with its a.m. or p.m.: "7am-7pm" is not "7pm-7am",
    and "twenty-five" is twenty and five."""
    return tuple(
        word or digits + ("" if not meridiem else "am" if "a" in meridiem else "pm")
        for digits, meridiem, word in _NUMBER.findall(low)
    )


def _abbreviated(text: str) -> set[str]:
    capitals = any(c.isalpha() for c in text) and text.upper() == text
    return {
        "GB" if "K" in m else "US"
        for m in _ABBREVIATED.findall(text)
        if not (m == "US" and capitals)
    }


def _foreign(text: str) -> bool:
    """Letters outside the Latin script: none of these word lists can read them."""
    return any(c.isalpha() and not unicodedata.name(c, "").startswith("LATIN") for c in text)


def _content(text: str, in_label: bool) -> list[_Token]:
    text = _US.sub(" ", _COUNTRY_NAMES.sub(" ", text))
    out = []
    for i, raw in enumerate(_TOKEN.findall(text)):
        low = raw.lower()
        if low not in _STOP and low not in _NOT_CONTENT:
            out.append(_Token(raw, low, in_label, in_label and i == 0))
    return out


def _side(label: str, help_: str) -> _Side:
    # Long inputs are read afresh: the cache holds the short labels forms repeat.
    if len(label) + len(help_) > 1000:
        return _read_side(label, help_)
    return _cached_side(label, help_)


def _read_side(label: str, help_: str) -> _Side:
    label, help_ = _fold(label), _fold(help_)
    text = f"{label} {help_}"
    low = text.lower()
    tokens = _content(label, True) + _content(help_, False)
    # A heading such as "Epic Analyst Certification": its capitals say nothing about names. A
    # question ("Experience with Salesforce?") is a sentence, never a heading.
    named = [t for t in _TOKEN.findall(label) if t.lower() not in _STOP and t[:1].isalpha()]
    title = (
        not label.rstrip().endswith("?")
        and len([t for t in named if len(t) > 1]) >= 2
        and all(t[:1].isupper() for t in named if len(t) > 1)
    )
    capitals = any(c.isalpha() for c in label) and label.upper() == label
    return _Side(
        text=low,
        numbers=_numbers(low),
        negations=(len(_NEG.findall(label.lower())), len(_NEG.findall(help_.lower()))),
        countries=frozenset(find_countries(text)) | _abbreviated(label) | _abbreviated(help_),
        words=frozenset(t.low for t in tokens),
        tokens=tuple(tokens),
        capital_label=title or capitals,
        foreign=_foreign(text),
    )


_cached_side = functools.lru_cache(maxsize=8192)(_read_side)


def _negation(t: _Token, side: _Side, other: _Side) -> bool:
    if t.low in _NEGATORS or t.low.endswith("n't") or t.low in _NEGATED:
        return True
    return any(
        t.low.startswith(p) and len(t.low) > len(p) + 2 and t.low[len(p) :] in other.words
        for p in _NEGATING_PREFIXES
    )


def _unit(t: _Token, side: _Side, other: _Side) -> bool:
    return t.low in _UNITS


def _language(t: _Token, side: _Side, other: _Side) -> bool:
    return t.low in _LANGUAGES or (t.low in _LANGUAGES_CAPITALISED and t.raw[:1].isupper())


def _proper_noun(t: _Token, side: _Side, other: _Side) -> bool:
    """A name: by its shape anywhere (AWS, HubSpot, C++, Node.js); in the label also a capital
    after its first word, or any word of a Title Case or all-capitals label. A capitalised first
    word, and a capital in the help text (sentence starts, boilerplate), count only by shape."""
    if t.raw in _NOT_PROPER or t.low in _ABBREVIATIONS:
        return False
    if sum(c.isalpha() for c in t.raw) >= 2 and t.raw.isupper():
        return True
    if re.search(r"[a-z][A-Z]", t.raw) or re.search(r"[+#.]", t.raw):
        return True
    return t.in_label and (side.capital_label or (t.raw[:1].isupper() and not t.first))


def _product(t: _Token, side: _Side, other: _Side) -> bool:
    return t.low in _PRODUCTS


def _restrictive(t: _Token, side: _Side, other: _Side) -> bool:
    return t.low in _RESTRICTIVE


def _level(t: _Token, side: _Side, other: _Side) -> bool:
    return t.low in _LEVELS


# D133: in this order, the first family a word on one side only belongs to names the veto.
FAMILIES = [
    ("negation", _negation),
    ("unit", _unit),
    ("language", _language),
    ("proper_noun", _proper_noun),
    ("product", _product),
    ("restrictive", _restrictive),
    ("level", _level),
]


def _differ(a: _Side, b: _Side) -> str | None:
    """The family of a word only one side has, or None."""
    if ("other than" in a.text) != ("other than" in b.text):
        return "negation"
    only = a.words ^ b.words
    if not only:
        return None
    for code, family in FAMILIES:
        for side, other in ((a, b), (b, a)):
            if any(t.low in only and family(t, side, other) for t in side.tokens):
                return code
    return None


def _alternative(a: _Side, b: _Side) -> str | None:
    """The kind of alternative each side names differently, or None."""
    for code, group in ALTERNATIVES.items():
        x, y = a.words & group, b.words & group
        if x and y and x != y:
            return code
    return None


def veto(new: dict, saved: dict) -> str | None:
    """Why this saved answer can never answer the new question, or None."""
    if new["shape"] != saved["shape"]:
        return "shape"
    a = _side(new["label"], new.get("help") or "")
    b = _side(saved["label"], saved.get("help") or "")
    if a.foreign or b.foreign:
        return "script"
    if a.numbers != b.numbers:
        return "numbers"
    if any(x % 2 != y % 2 for x, y in zip(a.negations, b.negations, strict=True)):
        return "negation"
    if a.countries != b.countries:
        return "countries"
    if new["shape"] in ("choice", "multi"):
        options = {normalize(o) for o in new["options"]}
        if not saved["labels"] or not all(normalize(x) in options for x in saved["labels"]):
            return "options"
    return _differ(a, b) or _alternative(a, b)


def pair(new: dict, saved: dict) -> list[float]:
    """The numeric features of one (new question, saved answer) pair, in NAMES order."""
    ta, tb = _tokens(new["label"]), _tokens(saved["label"])
    wa, wb = _words(new["label"]), _words(saved["label"])
    return [
        _jaccard(ta, tb),
        _cosine(_grams(new["label"]), _grams(saved["label"])),
        _jaccard(_tokens(new.get("help")), _tokens(saved.get("help"))),
        _jaccard({o.lower() for o in new["options"]}, {o.lower() for o in saved["options"]}),
        1.0 if wa[:1] == wb[:1] else 0.0,
        min(len(wa), len(wb)) / max(len(wa), len(wb), 1),
        float(len(ta)),
        float(len(tb)),
    ]


def rule_score(f: list[float]) -> float:
    """Before an account has taught its own model: a fixed blend of the wording's similarities.
    D133: the help-text and option similarities are left out of it; for the many questions with
    neither, they were a constant 1 (two empty sets) and lifted every pair alike."""
    tj, c3, fw, lr = f[0], f[1], f[4], f[5]
    return (0.35 * tj + 0.35 * c3 + 0.05 * fw + 0.05 * lr) / 0.8
