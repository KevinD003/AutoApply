"""D115: what the answer brain compares between a new question and a saved answer's question.

Numbers only: similarities of the wording, the help text and the options, and whether the two
agree on what must never differ. A pair that disagrees on numbers, negation, countries or the
kind of answer is vetoed outright, whatever the model would score: similar wording is not the
same question ("Are you authorized to work in the US?" vs "...in Canada?")."""

import math
import re

from app.modules.preparation.classify import find_countries
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
_NEG = re.compile(r"\b(not|no|never|without|none|nor|cannot|can't|don't|won't|isn't|aren't)\b")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


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


def veto(new: dict, saved: dict) -> str | None:
    """Why this saved answer can never answer the new question, or None."""
    if new["shape"] != saved["shape"]:
        return "shape"
    a, b = new["label"], saved["label"]
    if set(_NUM.findall(a)) != set(_NUM.findall(b)):
        return "numbers"
    if len(_NEG.findall(a.lower())) % 2 != len(_NEG.findall(b.lower())) % 2:
        return "negation"
    if set(find_countries(a)) != set(find_countries(b)):
        return "countries"
    if new["shape"] in ("choice", "multi"):
        options = {normalize(o) for o in new["options"]}
        if not saved["labels"] or not all(normalize(x) in options for x in saved["labels"]):
            return "options"
    return None


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
    """Before an account has taught its own model: a fixed blend of the similarities."""
    tj, c3, hj, oj, fw, lr = f[0], f[1], f[2], f[3], f[4], f[5]
    return 0.35 * tj + 0.35 * c3 + 0.1 * hj + 0.1 * oj + 0.05 * fw + 0.05 * lr
