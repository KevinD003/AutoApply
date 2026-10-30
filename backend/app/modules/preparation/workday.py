"""Workday-shaped postings (D88): which posting a job address names, where its application is,
and how its application page is read, checkpoint-first.

A hosted Workday posting is `https://TENANT.wdN.myworkdayjobs.com/SITE/job/LOCATION/TITLE_REQ`
(search-reported; docs/research/workday.md section 4; `jobs/canonical.py` identifies it). The
local Workday-style approximation serves `/workday/TENANT/REQ` on a fixture origin
(fixtures/ats_receiver/workday_like.py). Only that approximation is ever read or filled: a real
Workday posting is identified so that it can be refused, never fetched.

Checkpoint-first: on top of the generic extractor (which already makes passwords, one-time
codes, search-as-you-type pickers and custom controls unsupported), `extract_schema` adds:

  * a multi-step application (a step marker or a "Save and Continue" button): each page sends
    its answers on its own, which NoEfforts does not do, so it is one required unsupported
    field and the application is yours on the employer's site;
  * values already on the page when it loads (a parsed resume, a previous application): never
    trusted, so a required unsupported field until you review them there;
  * a location list that depends on another answer (`data-cascade-from`): unsupported.

A parsed resume that fills fields after an upload is caught at execution by the readback of
every field NoEfforts leaves unanswered (`hosted_form.HostedFormAdapter`)."""

import re
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import urlsplit

from app.modules.preparation.forms import FieldType, FormField, FormSchema, extract_form_schema

_FIXTURE = re.compile(r"^/workday/(?P<tenant>[a-z0-9-]{1,64})/(?P<req>R-[0-9]{4,12})(?:/apply)?/?$")
_REAL_HOST = re.compile(r"^[a-z0-9-]+\.(?:wd\d+\.myworkdayjobs\.com|myworkdaysite\.com)$")
_REAL_REQ = re.compile(r"_(?P<req>[A-Z]*-?\d[\w-]*)/?$", re.IGNORECASE)
MULTI_STEP_KEY, PREFILLED_KEY = "multi_step", "prefilled_values"
STEP_SELECTOR = "[data-workday-progress], [data-automation-id=pageFooterNextButton]"
_STEP_OF = re.compile(r"\bof\s+(\d+)\b", re.IGNORECASE)
_TEXT_TYPES = {"text", "email", "tel", "url", "number", "date", ""}

MULTI_STEP_REASON = (
    "an application on several pages: each page sends its answers to the employer on its own, "
    "which NoEfforts does not do; apply on the employer's site"
)
PREFILLED_REASON = (
    "the page came with answers already filled in (a parsed resume or a previous application): "
    "NoEfforts never sends values it did not get from you; review them on the employer's site"
)
CASCADE_REASON = "a location list that depends on another answer: NoEfforts does not fill it"


class Posting(NamedTuple):
    tenant: str
    req: str
    fixture: bool


def parse_posting(url: str | None, *, fixture_origin: bool) -> Posting | None:
    """The posting a job address names: a real hosted Workday posting, or the local
    Workday-style approximation on a fixture origin. None for anything else (never a guess)."""
    try:
        p = urlsplit(url or "")
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or p.username or p.password:
        return None
    host = (p.hostname or "").lower()
    if _REAL_HOST.fullmatch(host):
        m = _REAL_REQ.search(p.path)
        return Posting(host.split(".", 1)[0], m["req"], False) if m else None
    if fixture_origin:
        m = _FIXTURE.fullmatch(p.path)
        return Posting(m["tenant"], m["req"], True) if m else None
    return None


def apply_path(posting: Posting) -> str:
    """The application page's path on the fixture origin (the approximation's layout)."""
    return f"/workday/{posting.tenant}/{posting.req}/apply"


def form_url(url: str) -> str:
    """The application page for a posting address. Same scheme and host, no query."""
    p = urlsplit(url)
    path = p.path.rstrip("/")
    if not path.endswith("/apply"):
        path += "/apply"
    return f"{p.scheme}://{p.netloc}{path}"


class _Scan(HTMLParser):
    """What the generic extractor does not look at: step markers, values present at load,
    dependent location lists."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.steps = 0  # the largest "of N" in a step marker; 2+ means several pages
        self.next_button = False
        self.prefilled: set[str] = set()
        self.cascade: set[str] = set()
        self._in_progress = False
        self._select: str | None = None
        self._textarea: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if "data-workday-progress" in a:
            self._in_progress = True
        if a.get("data-automation-id") == "pageFooterNextButton":
            self.next_button = True
        name = a.get("name", "")
        if tag == "input" and a.get("type", "").lower() in _TEXT_TYPES and a.get("value"):
            self.prefilled.add(name)
        elif tag == "select":
            self._select = name
            if "data-cascade-from" in a:
                self.cascade.add(name)
        elif tag == "option" and self._select and "selected" in a and a.get("value"):
            self.prefilled.add(self._select)
        elif tag == "textarea":
            self._textarea = name

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None
        elif tag in ("div", "span", "p"):
            self._in_progress = False

    def handle_data(self, data):
        if self._in_progress:
            for n in _STEP_OF.findall(data):
                self.steps = max(self.steps, int(n))
        if self._textarea and data.strip():
            self.prefilled.add(self._textarea)


def _checkpoint(key: str, label: str, reason: str) -> FormField:
    return FormField(key=key, label=label, type=FieldType.unsupported, required=True,
                     unsupported_reason=reason)  # fmt: skip


_CASCADE = re.compile(r"<select\b([^>]*\bdata-cascade-from\b[^>]*)>.*?</select>", re.I | re.S)


def _as_picker(m: re.Match) -> str:
    """A dependent list has no options until another answer is given, which the generic
    extractor cannot read; it is read as the picker it behaves like (unsupported)."""
    attrs = re.sub(r'\s*data-cascade-from="[^"]*"', "", m.group(1))
    return f'<input type="text" role="combobox" aria-autocomplete="list"{attrs}>'


def extract_schema(html: str) -> FormSchema:
    """The generic extractor (documented CAPTCHAs included), then the Workday-style
    checkpoints above."""
    scan = _Scan()
    scan.feed(html)
    schema = extract_form_schema(_CASCADE.sub(_as_picker, html), challenges=True)
    keys = {f.key for f in schema.fields}
    for f in schema.fields:
        if f.key in scan.cascade:
            f.unsupported_reason = CASCADE_REASON
    if (scan.steps > 1 or scan.next_button) and MULTI_STEP_KEY not in keys:
        schema.fields.append(
            _checkpoint(MULTI_STEP_KEY, "An application on several pages", MULTI_STEP_REASON)
        )
    if scan.prefilled & keys and PREFILLED_KEY not in keys:
        schema.fields.append(
            _checkpoint(PREFILLED_KEY, "Answers the page filled in itself", PREFILLED_REASON)
        )
    return schema
