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
company, current, from, to) and two it leaves empty (location, description, never required), and
no value in any entry at load. Anything else about work history is one required checkpoint
(`WORK_KEY`): apply on the employer's site, never a guess and never left out silently.

A parsed resume that fills fields after an upload is caught at execution by the readback of
every field NoEfforts leaves unanswered (`hosted_form.HostedFormAdapter`)."""

import re
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import urlsplit

from app.modules.preparation.forms import (
    _VOID,
    UNKNOWN_TRIGGER,
    Condition,
    FieldType,
    FormField,
    FormSchema,
    SectionSpec,
    WizardSpec,
    _application_form,
    _Node,
    _TreeBuilder,
    extract_form_schema,
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
_NO_STEP = {"bot_check", MULTI_STEP_KEY, PREFILLED_KEY, WORK_KEY}  # checkpoints added here
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
# (work[i].<part>): (tag, input type, filled by NoEfforts). One not filled is never required.
_WORK_NAME = re.compile(r"^work\[(\d+|__i__)\]\.([a-z_]+)$")
_WORK_CONTROLS = {
    "title": ("input", "text", True),
    "company": ("input", "text", True),
    "location": ("input", "text", False),
    "current": ("input", "checkbox", True),
    "from": ("input", "text", True),
    "to": ("input", "text", True),
    "description": ("textarea", None, False),
}
_ADD = re.compile(r"^add(?: another)?$", re.IGNORECASE)
_ROOT_ID = re.compile(r"^[A-Za-z][\w-]*$")
WORK_REASON = (
    "a work history section NoEfforts cannot fill exactly as it is (an entry asks something "
    "NoEfforts does not fill, already holds a value, or cannot be added): apply on the "
    "employer's site"
)


def _work_control_ok(n: _Node, index: str) -> bool:
    """One control of an entry (the template's index `__i__`, or an entry's own): a part NoEfforts
    knows, of its kind, holding nothing, and never required when NoEfforts leaves it empty."""
    m = _WORK_NAME.match(n.attrs.get("name", ""))
    if not m or m[1] != index or m[2] not in _WORK_CONTROLS:
        return False
    tag, kind, filled = _WORK_CONTROLS[m[2]]
    if n.tag != tag or (kind and n.attrs.get("type", "text").lower() != kind):
        return False
    if (n.attrs.get("value") and kind != "checkbox") or "checked" in n.attrs or n.all_text():
        return False  # a value at load is never trusted (as PREFILLED_KEY)
    required = "required" in n.attrs or n.attrs.get("aria-required", "").lower() == "true"
    return filled or not required


def _entry_ok(controls: list[_Node], index: str) -> bool:
    """An entry's controls: each one known (`_work_control_ok`), each part once, and every part
    NoEfforts fills present."""
    parts = [_WORK_NAME.match(n.attrs.get("name", ""))[2] for n in controls
             if _WORK_NAME.match(n.attrs.get("name", ""))]  # fmt: skip
    return (
        all(_work_control_ok(n, index) for n in controls)
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
                and _WORK_NAME.match(n.attrs.get("name", ""))]  # fmt: skip
    sections = [n for n in inside if n.attrs.get("data-wd-section") == "work"]
    if not sections:
        return None, bool(controls)  # entries outside any section: never guessed
    root = sections[0]
    adds = [n for n in root.walk() if n.tag == "button" and _ADD.match(n.all_text())]
    tid = root.attrs.get("data-wd-entry-template", "")
    templates = [n for n in nodes if n.tag == "template" and tid and n.attrs.get("id") == tid]
    if (
        len(sections) != 1
        or not _ROOT_ID.match(root.attrs.get("id", ""))
        or len(adds) != 1
        or adds[0].attrs.get("type", "submit").lower() != "button"
        or len(templates) != 1
        or (form is not None and form in templates[0].ancestors())
        or any(root not in n.ancestors() for n in controls)
    ):
        return None, True
    entry = [n for n in templates[0].walk() if n.tag in ("input", "select", "textarea")]
    if not _entry_ok(entry, "__i__"):
        return None, True
    by_index: dict[str, list[_Node]] = {}
    for n in controls:  # entries already on the page: empty ones only, numbered 0, 1, ...
        by_index.setdefault(_WORK_NAME.match(n.attrs["name"])[1], []).append(n)
    if sorted(by_index, key=int) != [str(i) for i in range(len(by_index))] or not all(
        _entry_ok(c, i) for i, c in by_index.items()
    ):
        return None, True
    page = next((a for a in root.ancestors() if "data-wizard-page" in a.attrs), None)
    return SectionSpec(
        kind="employment",
        root=f"#{root.attrs['id']}",
        step=(page.attrs.get("data-step") or None) if page is not None else None,
        required=root.attrs.get("aria-required", "").lower() == "true",
    ), False


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
    if any(f.step not in names[:-1] for f in schema.fields if f.key not in _NO_STEP):
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
    schema = extract_form_schema(_CASCADE.sub(_as_picker, html), challenges=True)
    # D149: an entry's controls are the section's, never questions of their own.
    work, work_problem = _work_section(html)
    schema.fields = [f for f in schema.fields if not _WORK_NAME.match(f.key)]
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
    if work_problem and WORK_KEY not in keys:
        schema.fields.append(_checkpoint(WORK_KEY, "Work Experience", WORK_REASON))
    if (scan.steps > 1 or scan.next_button or wizard_refused) and MULTI_STEP_KEY not in keys:
        schema.fields.append(
            _checkpoint(MULTI_STEP_KEY, "An application on several pages", MULTI_STEP_REASON)
        )
    if scan.prefilled & keys and PREFILLED_KEY not in keys:
        schema.fields.append(
            _checkpoint(PREFILLED_KEY, "Answers the page filled in itself", PREFILLED_REASON)
        )
    return schema
