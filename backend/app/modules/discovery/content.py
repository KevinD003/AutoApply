"""D125 (Slice D): the complete, structured, *safe* job detail.

A posting's description, links and application content are untrusted. This module turns a
posting's HTML into a list of plain blocks — headings, paragraphs and lists with inline text,
emphasis and safe links only. Everything that could run, fetch or submit is dropped: scripts,
styles, images and other media, frames, forms and their controls, and event-handler attributes.
A link survives only when its scheme is http(s) or mailto; anything else keeps its text and
loses the link. Nothing here fetches an embedded asset or follows a link — the blocks are data,
rendered later as text.

Salary is read from a source's own structured fields when it has them, or extracted from the
description text and marked as extracted. It is never invented, never annualized, and currencies
are never converted: the original figures, currency and pay period are preserved as given, and a
figure's provenance (structured / provider enrichment / extracted from text) travels with it.
Missing data stays missing — a field the source does not give is simply absent."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

# ── HTML → safe structured blocks ───────────────────────────────────────────────────────────

# Elements dropped whole, subtree and all: active content, media we would otherwise have to
# fetch, and form controls. Any other unknown tag is simply unwrapped (its text is kept).
_DROP_SUBTREE = frozenset({
    "script", "style", "noscript", "template", "head", "title", "svg", "math",
    "iframe", "object", "embed", "applet", "canvas", "portal",
    "img", "picture", "source", "video", "audio", "track", "map", "area",
    "form", "input", "button", "select", "option", "optgroup", "textarea", "label", "fieldset",
    "legend", "datalist", "output", "progress", "meter",
    "link", "meta", "base",
})  # fmt: skip
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
# Block boundaries: closing or opening one ends the current paragraph.
_PARA_BOUNDARY = frozenset({
    "p", "div", "section", "article", "header", "footer", "main", "aside", "nav",
    "blockquote", "pre", "figure", "figcaption", "address", "hr",
    "table", "thead", "tbody", "tfoot", "tr", "caption", "colgroup", "col",
    "dl", "dt", "dd",
})  # fmt: skip
_CELL = frozenset({"td", "th"})
_LISTS = frozenset({"ul", "ol"})
# Void (empty) elements have no end tag, so a dropped one must not open a "subtree" to close —
# otherwise the drop depth would stick and swallow the rest of the document.
_VOID = frozenset({"img", "input", "source", "track", "area", "embed", "link", "meta", "base",
                   "param", "wbr", "keygen", "col"})  # fmt: skip

MAX_BLOCKS = 400
MAX_LIST_ITEMS = 400
MAX_TEXT = 60_000  # total visible characters kept across the whole document
MAX_SPAN = 8_000
_SAFE_SCHEMES = frozenset({"http", "https", "mailto"})


def safe_link(href) -> str | None:
    """A link kept only if its scheme is http(s) or mailto — never javascript:, data:, vbscript:,
    file: and the like. Returned exactly as given (trimmed); it is only ever shown, not fetched."""
    if not isinstance(href, str):
        return None
    href = href.strip()
    if not href or len(href) > 2048:
        return None
    # A scheme-relative URL (//host/...) inherits the page scheme — treat as https.
    if href.startswith("//"):
        return "https:" + href
    try:
        scheme = urlsplit(href).scheme.lower()
    except ValueError:
        return None
    if scheme == "":
        # A relative/anchor link has no host of its own; drop it rather than guess an origin.
        return None
    return href if scheme in _SAFE_SCHEMES else None


def _merge_spans(spans: list[dict]) -> list[dict]:
    """Collapse adjacent spans with identical formatting, trim the ends, drop empties."""
    out: list[dict] = []
    for s in spans:
        text = s.get("text", "")
        if not text:
            continue
        fmt = (s.get("bold"), s.get("italic"), s.get("href"))
        if out and (out[-1].get("bold"), out[-1].get("italic"), out[-1].get("href")) == fmt:
            out[-1]["text"] += text
        else:
            out.append(dict(s))
    if out:
        out[0]["text"] = out[0]["text"].lstrip()
        out[-1]["text"] = out[-1]["text"].rstrip()
    return [s for s in out if s.get("text")]


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._buf: list[dict] = []  # current inline spans
        self._fmt: list[tuple] = []  # stack: ("b",) | ("i",) | ("a", href)
        self._drop = 0  # >0 while inside a dropped subtree
        self._heading: int | None = None  # heading level for the current buffer, if any
        self._list: dict | None = None  # current {"type":"list","ordered":bool,"items":[...]}
        self._budget = MAX_TEXT

    # -- buffer / block helpers --
    def _add_block(self, block: dict) -> None:
        if len(self.blocks) < MAX_BLOCKS:
            self.blocks.append(block)

    def _flush(self) -> None:
        spans = _merge_spans(self._buf)
        self._buf = []
        level, self._heading = self._heading, None
        if not spans:
            return
        if self._list is not None:
            if len(self._list["items"]) < MAX_LIST_ITEMS:
                self._list["items"].append(spans)
            return
        if level:
            self._add_block({"type": "heading", "level": level, "spans": spans})
        else:
            self._add_block({"type": "paragraph", "spans": spans})

    def _close_list(self) -> None:
        self._flush()  # flush the open item
        if self._list is not None and self._list["items"]:
            self._add_block(self._list)
        self._list = None

    def _append_text(self, text: str) -> None:
        if self._drop or not text or self._budget <= 0:
            return
        if len(text) > self._budget:
            text = text[: self._budget]
        self._budget -= len(text)
        span = {"text": text[:MAX_SPAN]}
        for f in self._fmt:
            if f[0] == "b":
                span["bold"] = True
            elif f[0] == "i":
                span["italic"] = True
            elif f[0] == "a":
                span["href"] = f[1]
        self._buf.append(span)

    # -- parser callbacks --
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_SUBTREE and tag in _VOID:
            return  # an empty element we drop (img, input, …): nothing to open, ignore it
        if self._drop:
            if tag in _DROP_SUBTREE:
                self._drop += 1
            return
        if tag in _DROP_SUBTREE:
            self._drop += 1
            return
        if tag == "br":
            self._append_text("\n")
            return
        if tag in _HEADINGS:
            self._flush()
            self._heading = _HEADINGS[tag]
            return
        if tag in _LISTS:
            self._flush()
            if self._list is not None:
                self._close_list()  # nested list: flatten into one (safe, items preserved)
            self._list = {"type": "list", "ordered": tag == "ol", "items": []}
            return
        if tag == "li":
            self._flush()  # previous item (if any) ends here
            return
        if tag == "a":
            href = safe_link(dict(attrs).get("href"))
            self._fmt.append(("a", href) if href else ("noop",))
            return
        if tag in ("b", "strong"):
            self._fmt.append(("b",))
            return
        if tag in ("i", "em"):
            self._fmt.append(("i",))
            return
        if tag in _PARA_BOUNDARY or tag in _CELL:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self._append_text("\n")
        # other self-closing tags (img etc.) are dropped by having no handler

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._drop:
            if tag in _DROP_SUBTREE:
                self._drop -= 1
            return
        if tag in _HEADINGS:
            self._flush()
            return
        if tag in _LISTS:
            self._close_list()
            return
        if tag == "li":
            self._flush()
            return
        if tag in ("a", "b", "strong", "i", "em"):
            if self._fmt:
                self._fmt.pop()
            return
        if tag in _PARA_BOUNDARY or tag in _CELL:
            self._flush()

    def handle_data(self, data):
        if self._drop:
            return
        self._append_text(re.sub(r"\s+", " ", data))

    def result(self) -> list[dict]:
        self._close_list()
        self._flush()
        return self.blocks


def to_blocks(markup, *, unescape: bool = False) -> list[dict]:
    """Untrusted HTML (or plain text) → a list of safe blocks. `unescape=True` first decodes
    one layer of HTML entities, for a source (Greenhouse) that entity-encodes its HTML body."""
    if not isinstance(markup, str) or not markup.strip():
        return []
    if unescape:
        markup = html.unescape(markup)
    if "<" not in markup and ">" not in markup:
        # Plain text: keep paragraph breaks (blank lines), collapse the rest.
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", markup)]
        blocks = [{"type": "paragraph", "spans": [{"text": p}]} for p in paras if p]
        return blocks[:MAX_BLOCKS]
    p = _Sanitizer()
    try:
        p.feed(markup)
        p.close()
    except Exception:  # noqa: BLE001 - a malformed document yields what parsed so far, never raises
        pass
    return p.result()


def blocks_text(blocks: list[dict]) -> str:
    """The visible text of a block list, for extraction and search. Never rendered as HTML."""
    out = []
    for b in blocks or []:
        if b.get("type") == "list":
            out += [" ".join(s.get("text", "") for s in item) for item in b.get("items", [])]
        else:
            out.append(" ".join(s.get("text", "") for s in b.get("spans", [])))
    return "\n".join(t for t in out if t).strip()


# ── Salary, with its provenance ─────────────────────────────────────────────────────────────

PERIODS = ("year", "month", "week", "day", "hour")
_KINDS = ("base", "bonus", "equity", "ote", "total", "unspecified")

# Currency tokens: distinct "$"-family prefixes first, then symbols, then ISO codes.
_CUR_TOKEN = (
    r"US\$|C\$|CA\$|A\$|AU\$|NZ\$|S\$|HK\$|R\$|"
    r"[$£€¥₹]|"
    r"\b(?:USD|CAD|AUD|NZD|SGD|HKD|GBP|EUR|JPY|CHF|INR|BRL|MXN|ZAR|SEK|NOK|DKK|PLN|AED)\b"
)
_CUR_TO_CODE = {
    "us$": "USD",
    "c$": "CAD",
    "ca$": "CAD",
    "a$": "AUD",
    "au$": "AUD",
    "nz$": "NZD",
    "s$": "SGD",
    "hk$": "HKD",
    "r$": "BRL",
    "£": "GBP",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR",
}
_AMOUNT = r"\d[\d.,]*\s?[kKmM]?"
_RANGE_SEP = r"\s*(?:-|–|—|to|and)\s*"
_MONEY = re.compile(
    rf"(?P<cur>{_CUR_TOKEN})\s?(?P<a1>{_AMOUNT})"
    rf"(?:{_RANGE_SEP}(?:{_CUR_TOKEN})?\s?(?P<a2>{_AMOUNT}))?",
    re.IGNORECASE,
)
_PERIOD_PATTERNS = [
    (
        re.compile(
            r"per\s+annum|per\s+year|/\s?(?:yr|year)\b|\bannual(?:ly)?\b|\bp\.?a\.?\b|\byearly\b",
            re.I,
        ),
        "year",
    ),  # noqa: E501
    (re.compile(r"per\s+hour|/\s?(?:hr|hour)\b|\bhourly\b|\ban\s+hour\b", re.I), "hour"),
    (re.compile(r"per\s+month|/\s?(?:mo|month)\b|\bmonthly\b|\ba\s+month\b", re.I), "month"),
    (re.compile(r"per\s+week|/\s?(?:wk|week)\b|\bweekly\b|\ba\s+week\b", re.I), "week"),
    (re.compile(r"per\s+day|/\s?day\b|\bdaily\b|\ba\s+day\b", re.I), "day"),
]
_KIND_PATTERNS = [
    (re.compile(r"\bOTE\b|on[-\s]target", re.I), "ote"),
    (re.compile(r"\bbase\b", re.I), "base"),
    (re.compile(r"\bbonus\b", re.I), "bonus"),
    (re.compile(r"\bequity\b|\bstock\b|\bRSUs?\b", re.I), "equity"),
]


def _currency_of(token: str) -> tuple[str | None, str | None]:
    """(iso_code, symbol) for a currency token. '$' alone is ambiguous: symbol only, no code."""
    t = token.strip()
    low = t.lower()
    if low in _CUR_TO_CODE:
        sym = t if t in ("£", "€", "¥", "₹") else None
        return _CUR_TO_CODE[low], sym
    if t == "$":
        return None, "$"
    if re.fullmatch(r"[A-Za-z]{3}", t):
        return t.upper(), None
    return None, t or None


def _period_near(text: str, start: int) -> str | None:
    window = text[start : start + 40]
    for pat, period in _PERIOD_PATTERNS:
        if pat.search(window):
            return period
    return None


def _kind_near(text: str, start: int, end: int) -> str:
    window = text[max(0, start - 48) : end + 48]
    for pat, kind in _KIND_PATTERNS:
        if pat.search(window):
            return kind
    return "unspecified"


def salary_from_text(text) -> dict | None:
    """Extract one salary mention from free text, preserving the original. Returns None when no
    currency-anchored figure is found (the caller then says 'Salary not provided'). Nothing is
    annualized or converted; `text` holds the exact snippet as written."""
    if not isinstance(text, str) or not text.strip():
        return None
    m = _MONEY.search(text)
    if not m:
        return None
    code, symbol = _currency_of(m.group("cur"))
    a1, a2 = m.group("a1"), m.group("a2")
    snippet = text[m.start() : m.end()].strip()
    # Append exactly the period phrase the source used (e.g. "per year", "/hr"), so the shown
    # figure keeps its period without the amount regex's lost space or trailing words.
    period = _period_near(text, m.end())
    if period:
        window = text[m.end() : m.end() + 40]
        for pat, p in _PERIOD_PATTERNS:
            mm = pat.search(window)
            if p == period and mm:
                phrase = mm.group().strip()
                snippet = f"{snippet}{'' if phrase.startswith('/') else ' '}{phrase}"
                break
    return {
        "source": "extracted",
        "basis": "found in the description text",
        "currency": code,
        "currency_symbol": symbol,
        "period": period,
        "period_raw": None,
        "kind": _kind_near(text, m.start(), m.end()),
        "min": a1.strip() if a2 else None,
        "max": a2.strip() if a2 else None,
        "amount": None if a2 else a1.strip(),
        "text": snippet[:120],
    }


def _num(value) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return str(int(value)) if value == int(value) else str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()[:40]
    return None


_LEVER_INTERVAL = {
    "per-year-salary": "year", "per-month-salary": "month", "per-week-salary": "week",
    "per-day-salary": "day", "per-day-wage": "day", "per-hour-wage": "hour",
    "per-hour-salary": "hour",
}  # fmt: skip


def salary_from_lever(raw: dict) -> dict | None:
    """Lever's optional structured `salaryRange` ({min, max, currency, interval}); the free-text
    `salaryDescription` is a fallback. A structured range is provenance 'structured'."""
    sr = raw.get("salaryRange")
    if isinstance(sr, dict) and (sr.get("min") is not None or sr.get("max") is not None):
        lo, hi = _num(sr.get("min")), _num(sr.get("max"))
        interval = sr.get("interval") if isinstance(sr.get("interval"), str) else None
        cur = sr.get("currency") if isinstance(sr.get("currency"), str) else None
        code, symbol = _currency_of(cur) if cur else (None, None)
        return {
            "source": "structured",
            "basis": "the posting's structured pay range",
            "currency": code or (cur.upper()[:8] if cur else None),
            "currency_symbol": symbol,
            "period": _LEVER_INTERVAL.get(interval or ""),
            "period_raw": interval,
            "kind": "unspecified",
            "min": lo if hi else lo,
            "max": hi,
            "amount": lo if (lo and not hi) else None,
            "text": None,
        }
    desc = raw.get("salaryDescriptionPlain") or raw.get("salaryDescription")
    if isinstance(desc, str) and desc.strip():
        got = salary_from_text(html.unescape(desc) if "<" in desc else desc)
        if got:
            got["basis"] = "the posting's stated pay"
            return got
    return None


def salary_from_enrichment(enr: dict) -> dict | None:
    """Freehire enrichment pay (`salary_min`/`salary_max`/`salary_currency`/`salary_period`).
    Provenance 'enrichment': the docs say these are model output unless a source/manual figure
    replaced them, so it is attributed to the provider, never treated as the employer's words."""
    if not isinstance(enr, dict):
        return None
    lo, hi = _num(enr.get("salary_min")), _num(enr.get("salary_max"))
    if not lo and not hi:
        return None
    cur = enr.get("salary_currency") if isinstance(enr.get("salary_currency"), str) else None
    period = enr.get("salary_period") if isinstance(enr.get("salary_period"), str) else None
    period = period.lower().strip() if period else None
    code, symbol = _currency_of(cur) if cur else (None, None)
    return {
        "source": "enrichment",
        "basis": "estimated by the discovery source (may be model-produced)",
        "currency": code or (cur.upper()[:8] if cur else None),
        "currency_symbol": symbol,
        "period": period if period in PERIODS else None,
        "period_raw": period if period not in PERIODS else None,
        "kind": "unspecified",
        "min": lo if hi else lo,
        "max": hi,
        "amount": lo if (lo and not hi) else None,
        "text": None,
    }


# ── Assembling a posting's content block, per source ─────────────────────────────────────────

MAX_SECTIONS = 40


def _clean(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] or None


def _section_text(sections: list[dict]) -> str:
    return "\n".join(
        (s.get("heading") or "") + "\n" + blocks_text(s.get("blocks", [])) for s in sections
    )


def pack_content(
    *,
    description_blocks: list[dict] | None = None,
    sections: list[dict] | None = None,
    salary: dict | None = None,
    seniority: str | None = None,
    department: str | None = None,
    locations: list[str] | None = None,
) -> dict:
    """A posting's rich detail as a plain dict, with only the keys the source actually gave.
    This is stored verbatim inside `DiscoveredJob.normalized['content']` (schemaless JSON), so a
    field a source omits is simply absent — never guessed, never defaulted."""
    out: dict = {}
    if description_blocks:
        out["description_blocks"] = description_blocks
    if sections:
        out["sections"] = sections[:MAX_SECTIONS]
    if salary:
        out["salary"] = salary
    if seniority:
        out["seniority"] = seniority
    if department:
        out["department"] = department
    if locations:
        out["locations"] = locations
    return out


def _fallback_salary(blocks: list[dict], sections: list[dict] | None, structured) -> dict | None:
    if structured:
        return structured
    text = blocks_text(blocks)
    if sections:
        text = (text + "\n" + _section_text(sections)).strip()
    return salary_from_text(text)


def greenhouse_content(raw: dict) -> dict:
    """Greenhouse Job Board API (content=true): `content` (entity-encoded HTML), `departments`,
    `offices`. No pay field is documented, so salary is only ever extracted from the text."""
    blocks = to_blocks(raw.get("content"), unescape=True)
    depts = [_clean(d.get("name"), 120) for d in raw.get("departments") or []
             if isinstance(d, dict)]  # fmt: skip
    offices = [_clean(o.get("name"), 120) for o in raw.get("offices") or []
               if isinstance(o, dict)]  # fmt: skip
    depts = [d for d in depts if d]
    offices = [o for o in offices if o]
    return pack_content(
        description_blocks=blocks,
        salary=_fallback_salary(blocks, None, None),
        department=depts[0] if depts else None,
        locations=offices or None,
    )


def lever_content(raw: dict) -> dict:
    """Lever Postings API: `description`/`descriptionBody` (opening HTML), `lists` (the posting's
    own labelled sections), `additional` (closing HTML), `categories`, and optional structured
    `salaryRange`/`salaryDescription`."""
    opening = to_blocks(raw.get("descriptionBody") or raw.get("description"))
    sections: list[dict] = []
    for item in raw.get("lists") or []:
        if not isinstance(item, dict):
            continue
        sec_blocks = to_blocks(item.get("content"))
        if sec_blocks:
            sections.append({"heading": _clean(item.get("text"), 160), "blocks": sec_blocks})
    additional = to_blocks(raw.get("additional"))
    if additional:
        sections.append({"heading": None, "blocks": additional})
    cats = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    locs = [_clean(c, 120) for c in cats.get("allLocations") or [] if isinstance(c, str)]
    locs = [c for c in locs if c]
    if not locs and _clean(cats.get("location"), 120):
        locs = [_clean(cats.get("location"), 120)]
    return pack_content(
        description_blocks=opening,
        sections=sections,
        salary=_fallback_salary(opening, sections, salary_from_lever(raw)),
        department=_clean(cats.get("department"), 120) or _clean(cats.get("team"), 120),
        locations=locs if len(locs) > 1 else None,
    )


def freehire_content(raw: dict, enr: dict) -> dict:
    """Freehire job object: `description` (HTML) and the enrichment block (`seniority`,
    `category`, salary_*). Model-written enrichment prose (`summary`, `requirements`) is not
    used — only fields that are the posting's own content or clearly attributed estimates."""
    blocks = to_blocks(raw.get("description"))
    cities = [_clean(c, 100) for c in raw.get("cities") or [] if isinstance(c, str)]
    cities = [c for c in cities if c]
    return pack_content(
        description_blocks=blocks,
        salary=_fallback_salary(blocks, None, salary_from_enrichment(enr)),
        seniority=_clean(enr.get("seniority"), 80),
        department=_clean(enr.get("category"), 120),
        locations=cities if len(cities) > 1 else None,
    )


# ── Consolidating one job's detail for the API ───────────────────────────────────────────────

SALARY_ABSENT = "Salary not provided."


def _has_description(normalized: dict) -> bool:
    return bool((normalized.get("content") or {}).get("description_blocks"))


def consolidate_detail(*, own_description, own: dict, discovered: list[dict]) -> dict:
    """One job's complete detail, as its page shows it, drawn from the discovery records that
    list it (preferring the freshest with a real description) and falling back to the job's own
    saved text and fields. Availability-dependent and provenance-preserving: a field no source
    gave is absent, salary keeps where it came from, and `salary` is null when none is known
    (the page then shows "Salary not provided.").

    `own` holds the tracker job's own fields: employer, location, workplace, employment_type,
    posted_on, url. `discovered` is [{normalized, stale, last_seen_at}] for this job."""
    ordered = sorted(
        discovered,
        key=lambda d: (not d.get("stale", False), d.get("last_seen_at") or ""),
        reverse=True,
    )
    normals = [d.get("normalized") or {} for d in ordered]
    best = next((n for n in normals if _has_description(n)), None)
    content = (best or {}).get("content") or {}

    blocks = content.get("description_blocks")
    sections = content.get("sections")
    origin = "discovery"
    if not blocks:
        blocks = to_blocks(own_description) if own_description else []
        sections = None
        origin = "your_entry" if blocks else "none"

    salary = content.get("salary")
    if not salary:
        for n in normals:  # a sibling record may carry a figure even if its description is thin
            cand = (n.get("content") or {}).get("salary")
            if cand:
                salary = cand
                break
    if not salary and own_description:
        salary = salary_from_text(own_description)

    def pick(key, *, from_content=False):
        for n in normals:
            src = (n.get("content") or {}) if from_content else n
            v = src.get(key)
            if v:
                return v
        return None

    locations = (content.get("locations") or pick("locations", from_content=True)
                 or pick("cities"))  # fmt: skip
    facts = {
        "employment_type": pick("employment_type") or own.get("employment_type"),
        "workplace": next(
            (w for w in (pick("workplace"), own.get("workplace")) if w and w != "unknown"), None
        ),  # fmt: skip
        "seniority": content.get("seniority") or pick("seniority", from_content=True),
        "department": content.get("department") or pick("department", from_content=True),
        "locations": locations or None,
        "posted_on": pick("published_on") or own.get("posted_on"),
        "source_url": pick("job_url") or pick("application_url") or own.get("url"),
    }
    out = {
        "description": {"blocks": blocks, "sections": sections or []},
        "salary": salary,
        "facts": {k: v for k, v in facts.items() if v},
        "origin": origin,
    }
    return out
