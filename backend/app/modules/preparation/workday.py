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

D142: a multi-page wizard (`data-wizard-*` markers; the stand-in's mode, FIXTURE ASSUMPTIONS in
fixtures/ats_receiver/workday_like.py) is read as one form whose pages are all in the document,
and recorded as `FormSchema.wizard`, only when its structure is exactly what the executor drives
page by page (`_wizard_problem`): pages 1 to N in order with unique names, no step nested in a
page, one Next on each page before the last and none elsewhere, the only submit on the last
page, every question on a page before it, and no other step marker. Anything else is the
several-pages checkpoint above (fail closed), so each field's `step` is exactly its page.

D148: a question of the application form hidden at load inside its page (the control, or an
element between it and the form, is `hidden`, `aria-hidden="true"` or styled `display: none` /
`visibility: hidden`) is one the page shows by its own logic, after an answer NoEfforts cannot
name: `Condition(UNKNOWN_TRIGGER)`, as D135 reads Greenhouse's. A typed one is answered only by
you or an approved profile fact and entered only if the page shows it
(execution/adapters/workday.py); any other is never filled. A wizard page's own `hidden` (every
page but the first, FA1) says nothing about its questions. The markup is read as the generic
extractor parses it, never run.

D149: the stand-in's Work Experience section (FIXTURE ASSUMPTION FA7 in
fixtures/ats_receiver/workday_like.py) is read as an employment section, D120's rows filled from
your approved work history: `SectionSpec(kind="employment")` with its page and whether the page
requires an entry, and its entries' controls are not questions of their own. Only that exact
structure is read (`_work_section`): one section with an id and one "Add" button, entries built
from a template outside the form whose controls are exactly the ones NoEfforts fills (title,
company, current, from, to) and, D155, any of Location and Role Description (entered from your
record when it holds them: `parts`, and those the page requires, `required_parts`), every entry
already on the page asking them as the template does, and no value in any entry at load.
Anything else about work history is one required checkpoint (`WORK_KEY`): apply on the
employer's site, never a guess and never left out silently.

A parsed resume that fills fields after an upload is caught at execution by the readback of
every field NoEfforts leaves unanswered (`hosted_form.HostedFormAdapter`)."""

import re
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.modules.preparation.forms import (
    _ARIA_WIDGETS,
    _VOID,
    ENTRY_PARTS,
    UNKNOWN_TRIGGER,
    Condition,
    FieldType,
    FormField,
    FormSchema,
    SectionSpec,
    WizardSpec,
    _application_form,
    _bot_check,
    _Node,
    _TreeBuilder,
    extract_form_schema,
    read_maxlength,
)

_FIXTURE = re.compile(r"^/workday/(?P<tenant>[a-z0-9-]{1,64})/(?P<req>R-[0-9]{4,12})(?:/apply)?/?$")
_REAL_HOST = re.compile(r"^[a-z0-9-]+\.(?:wd\d+\.myworkdayjobs\.com|myworkdaysite\.com)$")
_REAL_REQ = re.compile(r"_(?P<req>[A-Z]*-?\d[\w-]*)/?$", re.IGNORECASE)
MULTI_STEP_KEY, PREFILLED_KEY = "multi_step", "prefilled_values"
WORK_KEY = "work_experience"  # D149: work history NoEfforts cannot fill exactly as it is
STEP_SELECTOR = "[data-workday-progress], [data-automation-id=pageFooterNextButton]"
# D142: the stand-in wizard's markers (any one of them makes the page a wizard to check).
WIZARD_MARKERS = ("data-wizard-pages", "data-wizard-page", "data-wizard-next",
                  "data-wizard-progress")  # fmt: skip
WIZARD_SELECTOR = ", ".join(f"[{m}]" for m in WIZARD_MARKERS)
# D149 review: the generic extractor's own challenge field belongs to no page; it alone is exempt
# from the wizard's page rule, by what it is (`_bot_check()`), never by its key, so a page
# question that happens to share a key is checked like any other. The checkpoints added here are
# appended after the wizard is checked.
_STEP_OF = re.compile(r"\bof\s+(\d+)\b", re.IGNORECASE)
_TEXT_TYPES = {"text", "email", "tel", "url", "number", "date", ""}
# D148: what hides an element in raw HTML (no script or stylesheet is run or read).
_HIDING_STYLE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!\s*important\s*)?(?:;|$)",
    re.IGNORECASE,
)
# Input types that are not questions (as forms.py), and a file input: a page commonly hides
# its native file input behind a button of its own, and an upload never needs it shown.
_NOT_MARKED = {"hidden", "submit", "button", "reset", "image", "file"}


def _hides(a: dict[str, str]) -> bool:
    """D148: the element is hidden at load by its own markup. A wizard page's section is not
    counted: its `hidden` is the page's (FA1), never its questions'."""
    if "data-wizard-page" in a:
        return False
    return ("hidden" in a or a.get("aria-hidden", "").strip().lower() == "true"
            or bool(_HIDING_STYLE.search(a.get("style", ""))))  # fmt: skip


def _hidden_in_page(html: str) -> set[str]:
    """D148: the names of the application form's questions hidden at load inside their page:
    every control of the name (each radio of a group) is hidden, by its own markup or an
    element's between it and the form (`_hides`). Read on the generic extractor's own tree and
    its choice of form, so a control outside that form (another form, a template) never marks
    one of its questions. A file input is never marked (`_NOT_MARKED`)."""
    b = _TreeBuilder()
    b.feed(html)
    nodes = list(b.root.walk())
    form = _application_form(nodes)
    seen: dict[str, list[bool]] = {}
    for n in nodes:
        name = n.attrs.get("name")
        if n.tag not in ("input", "select", "textarea") or not name:
            continue
        if n.tag == "input" and n.attrs.get("type", "text").lower() in _NOT_MARKED:
            continue
        chain = [n, *n.ancestors()]
        if form is not None:
            if form not in chain:
                continue  # outside the application form: not one of its questions
            chain = chain[: chain.index(form)]
        seen.setdefault(name, []).append(any(_hides(a.attrs) for a in chain))
    return {name for name, hidden in seen.items() if all(hidden)}


# D149: the Work Experience section (FA7). An entry's controls, by the last part of their name
# (work[i].<part>): (tag, input type, always entered). D155: Location and Role Description are
# entered when your record holds them (`_OPTIONAL_PARTS`); the page may require them, and then a
# record without one blocks approval. Any other part is always entered.
_WORK_NAME = re.compile(r"work\[(\d+|__i__)\]\.([a-z_]+)")  # always read whole (fullmatch)
_WORK_ANY = re.compile(r"^work\[")  # any control named as an entry's
_WORK_CONTROLS = {
    "title": ("input", "text", True),
    "company": ("input", "text", True),
    "location": ("input", "text", False),
    "current": ("input", "checkbox", True),
    "from": ("input", "text", True),
    "to": ("input", "text", True),
    "description": ("textarea", None, False),
}
_OPTIONAL_PARTS = ENTRY_PARTS  # sorted, as SectionSpec.parts
_ADD = re.compile(r"^add(?: another)?$", re.IGNORECASE)
_ROOT_ID = re.compile(r"[A-Za-z][\w-]{0,99}")  # always read whole (fullmatch)
WORK_REASON = (
    "a work history section NoEfforts cannot fill exactly as it is (an entry asks something "
    "NoEfforts does not fill, already holds a value, or cannot be added): apply on the "
    "employer's site"
)


def _button_like(n: _Node) -> bool:
    return (n.tag == "button" or (n.attrs.get("role") or "").lower() == "button"
            or (n.tag == "input" and n.attrs.get("type", "").lower()
                in ("button", "submit", "reset", "image")))  # fmt: skip


def _usable_within(n: _Node, top: _Node | None) -> bool:
    """Nothing between the control and `top` (the form, the section or the template) hides it at
    load (D148's markup signals) or disables it (a disabled fieldset, `aria-disabled`): the
    executor clicks and types only into what the page shows and accepts."""
    a = n
    while a is not None and a is not top:
        if (_hides(a.attrs) or a.attrs.get("aria-disabled", "").lower() == "true"
                or (a.tag == "fieldset" and "disabled" in a.attrs)):  # fmt: skip
            return False
        a = a.parent
    return True


# Constraints on a typed value NoEfforts would not honour (it types the approved value whole).
# D157: a length limit (`maxlength`) is read instead (`_limit`), and your record held to it.
_CONSTRAINTS = ("minlength", "pattern")
# D157: an entry's typed parts whose limit is recorded, by the frozen row's field names; a date
# is always MM/YYYY, so its control must accept 7 characters and its limit is not recorded.
_LIMITED = {"title": "title", "company": "company_name", "location": "location",
            "description": "description"}  # fmt: skip
_MONTH_YEAR_LEN = len("MM/YYYY")


def _limit(n: _Node) -> int | None | bool:
    """D157: a control's `maxlength` as the browser reads it (`forms.read_maxlength`): None, the
    number, or False for one NoEfforts never guesses at; one written twice is refused with its
    control (`_work_control_ok`)."""
    return read_maxlength(n.attrs.get("maxlength"))


def _limits(controls: list[_Node]) -> dict[str, int]:
    """D157: the length limits an entry's typed parts hold your record to, by the frozen row's
    field names (`_LIMITED`); a date's, which MM/YYYY fits (`_work_control_ok`), never binds."""
    out = {}
    for n in controls:
        limit = _limit(n)
        part = _WORK_NAME.fullmatch(n.attrs.get("name", ""))[2]
        if isinstance(limit, int) and not isinstance(limit, bool) and part in _LIMITED:
            out[_LIMITED[part]] = limit
    return out


def _work_control_ok(n: _Node, index: str, template: _Node | None) -> bool:
    """One control of an entry (the template's index `__i__`, or an entry's own): a part NoEfforts
    knows, of its kind, holding nothing, sending exactly what is typed into it, and never
    required when NoEfforts may leave it empty (a past role's box; D155: a Location or Role
    Description may be, as it is entered from your record or blocks approval). In the template,
    also shown and editable. An entry on the page is not held to that here: the
    page hides a current role's To once its box is ticked, and capture cannot tell an entry the
    page showed at load from one NoEfforts added; the adapter checks the entries already on the
    page before anything is entered (execution/adapters/workday_sections.py)."""
    if template is not None and ("readonly" in n.attrs or "disabled" in n.attrs
                                 or not _usable_within(n, template)):  # fmt: skip
        return False
    # A constraint on a typed value NoEfforts would not honour, on the template and on an entry
    # already on the page alike (D157, found by its review: an entry's were never read).
    if any(c in n.attrs for c in _CONSTRAINTS):
        return False
    m = _WORK_NAME.fullmatch(n.attrs.get("name", ""))
    if not m or m[1] != index or m[2] not in _WORK_CONTROLS:
        return False
    if m[2] in ("from", "to") and n.attrs.get("placeholder") != "MM/YYYY":
        return False  # the page says how a date is written, and it is the way NoEfforts writes it
    tag, kind, filled = _WORK_CONTROLS[m[2]]
    if n.tag != tag or (kind and n.attrs.get("type", "text").lower() != kind):
        return False
    if n.twice:  # D157: an attribute written twice, which the browser reads as its first
        return False
    # D157: a length limit only on a typed part, one NoEfforts can read, and on a date one that
    # lets MM/YYYY be typed whole.
    limit = _limit(n)
    if limit is False or (limit is not None and (kind == "checkbox" or (
            m[2] in ("from", "to") and limit < _MONTH_YEAR_LEN))):  # fmt: skip
        return False
    if (n.attrs.get("value") and kind != "checkbox") or "checked" in n.attrs or n.all_text():
        return False  # a value at load is never trusted (as PREFILLED_KEY)
    # D155: what the browser sends is what was typed: no hard wrapping (line breaks you never
    # wrote), no direction field (`dirname`) and no other form (`form`).
    wrap = n.attrs.get("wrap")
    if (n.tag == "textarea" and wrap is not None and wrap.strip().lower() not in ("", "soft")
            or "dirname" in n.attrs or "form" in n.attrs):  # fmt: skip
        return False
    # A box left unticked for a past role must never be required (the browser would block the
    # final click). D155: a required Location or Role Description is entered from your record,
    # or the package cannot be approved without it (`required_parts`).
    return not _required(n) or (filled and m[2] != "current") or m[2] in _OPTIONAL_PARTS


def _required(n: _Node) -> bool:
    return "required" in n.attrs or n.attrs.get("aria-required", "").lower() == "true"


def _optional_parts(controls: list[_Node]) -> dict[str, bool]:
    """D155: an entry's Location and Role Description, each with whether the page requires it."""
    out = {}
    for n in controls:
        part = _WORK_NAME.fullmatch(n.attrs.get("name", ""))[2]
        if part in _OPTIONAL_PARTS:
            out[part] = _required(n)
    return out


def _entry_ok(controls: list[_Node], index: str, template: _Node | None) -> bool:
    """An entry's controls: each one known (`_work_control_ok`), each part once, and every part
    NoEfforts fills present."""
    parts = [_WORK_NAME.fullmatch(n.attrs.get("name", ""))[2] for n in controls
             if _WORK_NAME.fullmatch(n.attrs.get("name", ""))]  # fmt: skip
    return (
        all(_work_control_ok(n, index, template) for n in controls)
        and len(parts) == len(set(parts)) == len(controls)
        and {p for p, (_, _, filled) in _WORK_CONTROLS.items() if filled} <= set(parts)
    )


def _work_section(html: str) -> tuple[SectionSpec | None, bool]:
    """D149: the Work Experience section (FA7) as an employment section, or whether the page
    has work history NoEfforts cannot fill exactly (True: `WORK_KEY`'s checkpoint). (None,
    False): no work history at all. Read on the generic extractor's own tree and form."""
    b = _TreeBuilder()
    b.feed(html)
    nodes = list(b.root.walk())
    form = _application_form(nodes)
    inside = [n for n in nodes if form is None or n is form or form in n.ancestors()]
    controls = [n for n in inside if n.tag in ("input", "select", "textarea")
                and _WORK_ANY.match(n.attrs.get("name", ""))]  # fmt: skip
    sections = [n for n in inside if "data-wd-section" in n.attrs]
    markers = [n for n in inside if "data-wd-add" in n.attrs or "data-wd-entry-template" in n.attrs]
    if not sections:
        return None, bool(controls or markers)  # entries outside any section: never guessed
    root = sections[0]
    rid = root.attrs.get("id", "")
    buttons = [n for n in root.walk() if _button_like(n)]  # the section's Add, and nothing else
    tid = root.attrs.get("data-wd-entry-template", "")
    templates = [n for n in nodes if n.tag == "template" and tid and n.attrs.get("id") == tid]
    if (
        len(sections) != 1
        or root.attrs["data-wd-section"] != "work"  # another kind of section: never read as one
        or any(n is not root and root not in n.ancestors() for n in markers)
        or not _ROOT_ID.fullmatch(rid)
        or sum(1 for n in nodes if n.attrs.get("id") == rid) != 1
        or len(buttons) != 1
        or buttons[0].attrs.get("type", "submit").lower() != "button"
        or "disabled" in buttons[0].attrs
        or not _usable_within(buttons[0], root)
        or not _ADD.match(buttons[0].all_text())
        or len(templates) != 1
        or any(_button_like(n) for n in templates[0].walk())
        or any(root not in n.ancestors() for n in controls)
        or not _usable_within(root, form)  # hidden or disabled at load (a wizard page is not)
    ):
        return None, True
    entry = [n for n in templates[0].walk() if n.tag in ("input", "select", "textarea")]
    if not _entry_ok(entry, "__i__", templates[0]):
        return None, True
    if any((n.attrs.get("role") or "").lower() in _ARIA_WIDGETS
           for n in (*root.walk(), *templates[0].walk())):  # fmt: skip
        return None, True  # a custom control in an entry: nothing NoEfforts can operate
    if any(not (m := _WORK_NAME.fullmatch(n.attrs["name"])) or not m[1].isdigit()
           for n in controls):  # fmt: skip
        return None, True  # a control named as an entry's but not one, or a template inside
    by_index: dict[str, list[_Node]] = {}
    for n in controls:  # entries already on the page: empty ones only, numbered 0, 1, ...
        by_index.setdefault(_WORK_NAME.fullmatch(n.attrs["name"])[1], []).append(n)
    if sorted(by_index, key=int) != [str(i) for i in range(len(by_index))] or not all(
        _entry_ok(c, i, None) for i, c in by_index.items()
    ):
        return None, True
    # D155: an entry already on the page asks Location and Role Description exactly as the
    # template does, each required only where the template's is (NoEfforts fills that entry in
    # place, from what the template's parts resolved to).
    if any(_optional_parts(c) != _optional_parts(entry) for c in by_index.values()):
        return None, True
    # D157: and limits each part's length exactly as the template does.
    if any(_limits(c) != _limits(entry) for c in by_index.values()):
        return None, True
    page = next((a for a in root.ancestors() if "data-wizard-page" in a.attrs), None)
    # D155: the template's Location and Role Description (each once, `_entry_ok`), and which of
    # them the page requires.
    asked = _optional_parts(entry)
    parts = [p for p in _OPTIONAL_PARTS if p in asked]
    try:
        spec = SectionSpec(
            kind="employment",
            root=f"#{rid}",
            step=(page.attrs.get("data-step") or None) if page is not None else None,
            required=root.attrs.get("aria-required", "").lower() == "true",
            parts=parts,
            required_parts=[p for p in parts if asked[p]],
            limits=_limits(entry),
        )
    except ValidationError:  # a page name too long to record: never an error of capture
        return None, True
    return spec, False


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
        # D142: the wizard's structure, as written in the page.
        self.wizard_seen = False
        self.wizard_pages: list[str] = []  # data-wizard-pages, as written (normally one)
        self.wizard_sections: list[tuple[str, str]] = []  # (data-wizard-page, data-step)
        self.nexts: dict[str, int] = {}  # Next buttons per page
        self.nexts_outside = 0
        self.submits: list[str | None] = []  # the page each submit button is on (None: none)
        self.nested_steps = 0  # a data-step inside a wizard page
        self._stack: list[tuple[str, str | None]] = []  # (tag, wizard page) of open elements

    def _page(self) -> str | None:
        return next((p for _, p in reversed(self._stack) if p is not None), None)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if any(m in a for m in WIZARD_MARKERS):
            self.wizard_seen = True
        if "data-wizard-pages" in a:
            self.wizard_pages.append(a["data-wizard-pages"])
        current = self._page()
        if "data-step" in a and current is not None:
            self.nested_steps += 1
        if "data-wizard-next" in a:
            if current is None:
                self.nexts_outside += 1
            else:
                self.nexts[current] = self.nexts.get(current, 0) + 1
        if tag == "button" and a.get("type", "submit").lower() == "submit":
            self.submits.append(current)
        elif tag == "input" and a.get("type", "").lower() in ("submit", "image"):
            self.submits.append(current)
        page = a.get("data-wizard-page") if "data-wizard-page" in a else None
        if page is not None:
            self.wizard_sections.append((page, a.get("data-step", "")))
            if current is not None:
                self.nested_steps += 1  # a page inside a page
        if tag not in _VOID:
            self._stack.append((tag, page))
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
        for i in range(len(self._stack) - 1, -1, -1):  # as the form extractor closes elements
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
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


def _add_checkpoint(schema: FormSchema, key: str, label: str, reason: str) -> None:
    """D149 review: a checkpoint replaces a page question that happens to share its key, so such
    a question can never hide it (the checkpoint blocks approval either way)."""
    schema.fields = [f for f in schema.fields if f.key != key]
    schema.fields.append(_checkpoint(key, label, reason))


_CASCADE = re.compile(r"<select\b([^>]*\bdata-cascade-from\b[^>]*)>.*?</select>", re.I | re.S)


def _as_picker(m: re.Match) -> str:
    """A dependent list has no options until another answer is given, which the generic
    extractor cannot read; it is read as the picker it behaves like (unsupported)."""
    attrs = re.sub(r'\s*data-cascade-from="[^"]*"', "", m.group(1))
    return f'<input type="text" role="combobox" aria-autocomplete="list"{attrs}>'


def _wizard_problem(scan: _Scan, schema: FormSchema) -> str | None:
    """D142: why a page with wizard markers is not a wizard the executor drives page by page
    (any reason: the several-pages checkpoint), or None. The rules, each one checked:"""
    # 1. The number of pages, written once, from 2 to 10.
    if len(scan.wizard_pages) != 1 or not scan.wizard_pages[0].isdigit():
        return "page count"
    n = int(scan.wizard_pages[0])
    if not 2 <= n <= 10:
        return "page count"
    # 2. Exactly N pages numbered 1 to N in order, each with its own non-empty name.
    names = [step for _, step in scan.wizard_sections]
    if [p for p, _ in scan.wizard_sections] != [str(i) for i in range(1, n + 1)]:
        return "page numbers"
    if not all(x.strip() and len(x) <= 200 for x in names) or len(set(names)) != n:
        return "page names"
    # 3. No step inside a page: a field's step is then exactly its page.
    if scan.nested_steps:
        return "nested step"
    # 4. One Next on each page before the last, none on the last and none outside a page.
    if scan.nexts_outside or scan.nexts != {str(i): 1 for i in range(1, n)}:
        return "next buttons"
    # 5. The form's only submit button is on the last page.
    if scan.submits != [str(n)]:
        return "submit button"
    # 6. Every question is on a page before the last.
    if any(f.step not in names[:-1] for f in schema.fields if f != _bot_check()):
        return "field outside a page"
    # 7. No other several-pages marker at the same time.
    if scan.steps > 1 or scan.next_button:
        return "mixed markers"
    return None


def extract_schema(html: str) -> FormSchema:
    """The generic extractor (documented CAPTCHAs included), then the Workday-style
    checkpoints above. D142: a wizard that passes `_wizard_problem` is recorded as
    `schema.wizard`; one that does not is the several-pages checkpoint."""
    scan = _Scan()
    scan.feed(html)
    # D149: an entry's controls are the section's, never questions of their own, and never read
    # by the generic extractor (however many entries, labelled or not).
    schema = extract_form_schema(_CASCADE.sub(_as_picker, html), challenges=True,
                                 skip=_WORK_ANY.match)  # fmt: skip
    work, work_problem = _work_section(html)
    keys = {f.key for f in schema.fields}
    hidden = _hidden_in_page(html)
    for f in schema.fields:
        if f.key in scan.cascade:
            f.unsupported_reason = CASCADE_REASON
        if f.key in hidden and f.type != FieldType.unsupported and f.condition is None:
            # D148: shown by the page's own logic, after an answer NoEfforts cannot name.
            f.condition = Condition(key=UNKNOWN_TRIGGER, any_of=["?"])
    wizard_refused = False
    if scan.wizard_seen:
        if _wizard_problem(scan, schema) is None:
            schema.wizard = WizardSpec(pages=[step for _, step in scan.wizard_sections])
        else:
            wizard_refused = True
    if work is not None:  # D149: on a wizard's page before its review page, or on a single page
        pages = schema.wizard.pages[:-1] if schema.wizard else []
        if (work.step in pages) if schema.wizard else work.step is None:
            schema.sections = [*schema.sections, work]
        else:
            work_problem = True
    if work_problem:
        _add_checkpoint(schema, WORK_KEY, "Work Experience", WORK_REASON)
    if scan.steps > 1 or scan.next_button or wizard_refused:
        _add_checkpoint(schema, MULTI_STEP_KEY, "An application on several pages",
                        MULTI_STEP_REASON)  # fmt: skip
    if scan.prefilled & keys:
        _add_checkpoint(schema, PREFILLED_KEY, "Answers the page filled in itself",
                        PREFILLED_REASON)  # fmt: skip
    return schema
