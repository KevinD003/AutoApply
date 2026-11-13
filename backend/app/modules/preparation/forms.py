"""Application-form schemas and HTML schema extraction.

A form is captured once per job version and stored as a list of `FormField`s. Each field keeps
the employer's original wording, help text, real options and a stable key taken from the form
itself (name/id), so answers can be bound to exactly what was asked.
"""

import enum
import hashlib
import json
import re
from html.parser import HTMLParser
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_serializer, model_validator

# v2 (D80): a search-as-you-type control (role=combobox or aria-autocomplete) is unsupported,
# never a text box; with `challenges`, a CAPTCHA or bot check on the page is a required
# unsupported field, so approval waits and the user applies on the employer's site.
# v3 (D81): a password or one-time-code input, and an ARIA widget with no native control in it
# (a custom radio group, switch, dropdown or editable box), are unsupported too: a question the
# extractor cannot operate is never dropped, and a credential is never asked for or kept.
EXTRACTION_VERSION = "html-v3"


class FieldType(enum.StrEnum):
    text = "text"
    textarea = "textarea"
    email = "email"
    tel = "tel"
    url = "url"
    number = "number"
    date = "date"
    radio = "radio"
    checkbox = "checkbox"  # a single yes/no box
    checkbox_group = "checkbox_group"  # several boxes, pick any
    select = "select"
    multiselect = "multiselect"
    file = "file"
    # A control we cannot fill deterministically (e.g. a hidden value a page script sets).
    # Never guessed: required ones block approval, optional ones stay blank.
    unsupported = "unsupported"


CHOICE_TYPES = {FieldType.radio, FieldType.select}
MULTI_TYPES = {FieldType.checkbox_group, FieldType.multiselect}
TEXT_TYPES = {FieldType.text, FieldType.textarea, FieldType.email, FieldType.tel, FieldType.url}
# Condition.key of a question the page shows by its own logic, which NoEfforts cannot see: on
# Greenhouse's id-only pages a question hidden at load, revealed by an answer it cannot name.
UNKNOWN_TRIGGER = "unknown-trigger"
# D135: such a question can be answered only with typed text, and only you (or an approved profile
# fact) answer it; it is entered only if the page shows it after the other answers.
SHOWN_BY_PAGE_TYPES = TEXT_TYPES


def shown_by_page(condition, ftype) -> bool:
    """D135: a typed question the page shows by its own logic (its trigger unknown). `condition`
    is a Condition or its dict form, as in a package's answers."""
    key = condition.get("key") if isinstance(condition, dict) else getattr(condition, "key", None)
    return key == UNKNOWN_TRIGGER and FieldType(ftype) in SHOWN_BY_PAGE_TYPES


class Option(BaseModel):
    value: str = Field(max_length=500)
    label: str = Field(max_length=500)


class Condition(BaseModel):
    """The field is shown (and applies) only when field `key` has one of these option values."""

    key: str = Field(min_length=1, max_length=200)
    any_of: list[str] = Field(min_length=1, max_length=50)


KEY_PATTERN = r"^[A-Za-z0-9_.:\[\]-]+$"  # a field key as extracted from a form

# D104: controls the id-mapping capture recognises only on local stand-ins (greenhouse_dom
# `build_schema(stand_ins=True)`), each answered and filled by its own rule:
#   phone_country        the country picker beside the phone field: chosen only when the
#                        approved phone number's calling code matches exactly one option
#   location_search      a text question asked through the page's search-as-you-type picker
#   location_structured  a hidden value that picker's own script sets (coordinates); never
#                        written by NoEfforts, checked after a suggestion is chosen
STAND_IN_WIDGETS = ("phone_country", "location_search", "location_structured")
# D111 (from a real page, read-only run #11; greenhouse_dom `hidden_search_*`):
#   hidden_search        a search input the page keeps hidden inside one question's group: not
#                        a question while the live page hides it, requires nothing in it and
#                        holds nothing in it; never filled; anything else stops the attempt
# D130 (from a real page's markup; greenhouse_dom `phone_companion`):
#   phone_companion      the one other control inside an OPTIONAL phone question's group, not
#                        required by the page: never touched, because the phone is left blank
#   phone_left_blank     that optional phone: never entered (its second control cannot be set)
WIDGETS = (*STAND_IN_WIDGETS, "hidden_search", "phone_companion", "phone_left_blank")


class FormField(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=2000)
    help_text: str | None = Field(default=None, max_length=4000)
    type: FieldType
    required: bool = False
    options: list[Option] = Field(default_factory=list, max_length=500)
    step: str | None = Field(default=None, max_length=200)
    max_length: int | None = Field(default=None, ge=1, le=100_000)
    accept: str | None = Field(default=None, max_length=200)
    condition: Condition | None = None
    unsupported_reason: str | None = Field(default=None, max_length=300)
    widget: str | None = Field(default=None, max_length=50)  # D104/D111/D130: one of WIDGETS

    @model_validator(mode="after")
    def _options(self):
        if self.type in CHOICE_TYPES | MULTI_TYPES and not self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} needs options")
        if self.type not in CHOICE_TYPES | MULTI_TYPES and self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} cannot have options")
        shape = {"phone_country": FieldType.select, "location_search": FieldType.text,
                 "location_structured": FieldType.unsupported,
                 "hidden_search": FieldType.unsupported,
                 "phone_companion": FieldType.unsupported,
                 "phone_left_blank": FieldType.tel}  # fmt: skip
        if self.widget is not None and shape.get(self.widget) != self.type:
            raise ValueError(f"field '{self.key}' cannot be a {self.widget} control")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        # D104: written only for a field that has one, so every other stored form keeps its
        # exact content.
        out = handler(self)
        if isinstance(out, dict) and out.get("widget") is None:
            out.pop("widget", None)
        return out


class SectionOptionSpec(BaseModel):
    """One ``{id, text}`` option a captured structured section offers (from the Greenhouse
    education endpoints, or -- on a local stand-in -- read from the rendered option list)."""

    id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500)


# D155: the parts a work history entry may ask beyond those always entered (the Workday-style
# stand-in's Location and Role Description), sorted: the one list every layer uses.
ENTRY_PARTS = ("description", "location")
EntryPart = Literal["description", "location"]
assert ENTRY_PARTS == tuple(sorted(EntryPart.__args__))
# D157: the frozen employment fields whose text an entry's page may limit in length (`maxlength`
# on its control), by the frozen row's names, sorted; a date is always MM/YYYY (capture refuses a
# date control that limits it below 7).
LIMITED_FIELDS = ("company_name", "description", "location", "title")
# The largest `maxlength` Chromium reads (a 32-bit signed integer); a larger one it ignores, and
# capture refuses.
MAX_LIMIT = 2_147_483_647


_ASCII_WHITESPACE = " \t\n\f\r"  # what the browser skips before a number, and nothing else


def read_maxlength(raw: str | None) -> int | None | bool:
    """A control's `maxlength` as the browser reads it (D157; D158 for every question): None when
    it has none, the number when it is written in ASCII digits (ASCII whitespace around them),
    from 1 to MAX_LIMIT; False otherwise, a limit NoEfforts cannot read as the browser does and
    never guesses (a sign, any other character, another script's digits, 0, or more than the
    browser reads)."""
    if raw is None:
        return None
    digits = raw.strip(_ASCII_WHITESPACE)
    if not (digits.isascii() and digits.isdigit()):
        return False
    digits = digits.lstrip("0")
    if not digits or len(digits) > len(str(MAX_LIMIT)) or int(digits) > MAX_LIMIT:
        return False  # 0, or more than the browser reads
    return int(digits)


_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def sent_len(text: str) -> int:
    """D157: a text's length as its form sends it, which a limit (`maxlength`) is held to: UTF-16
    code units, as the browser counts them (a character outside the Basic Multilingual Plane
    counts 2), and each line break as the two the form sends (CRLF), where the browser counts
    one. Never less than the browser's own count, so a value within a limit by this count is kept
    whole by the page, and fits a server that counts what it receives. D158: a line break written
    as CRLF or as a lone CR is one line break too (the form sends each as CRLF)."""
    return len(_LINE_BREAK.sub("\r\n", text).encode("utf-16-le", "surrogatepass")) // 2


def one_line_breaks(text: str) -> str:
    """D158: every line break written as one LF, as a text area holds it."""
    return _LINE_BREAK.sub("\n", text)


# D159: why a question's control is refused when the form is read (`sent_otherwise`).
SENT_OTHERWISE = (
    "a control whose form would not send exactly what is typed into it (it adds line breaks of "
    "its own, sends your text's direction as a field of its own, or belongs to another form): "
    "NoEfforts does not fill it"
)


def sent_otherwise(n: "_Node") -> bool:
    """D155 (a work entry's controls), D159 (every question's): the control's form would not send
    exactly what is typed into it, read from its tag as the browser reads it (an attribute written
    twice, by its first value):
      * a text area that hard-wraps: the form inserts line breaks you never wrote where the text
        wraps on the screen (the browser does on `wrap="hard"`; every value but soft, empty or
        none is refused rather than read);
      * `dirname`: the form sends your text's direction as a field of its own;
      * `form`: the control may belong to another form, or to none, and the application form
        would not send it."""
    wrap = n.twice.get("wrap", n.attrs.get("wrap"))
    if n.tag == "textarea" and wrap is not None and wrap.strip().lower() not in ("", "soft"):
        return True
    return "dirname" in n.attrs or "form" in n.attrs


class SectionSpec(BaseModel):
    """D120: a captured structured education/employment section -- its kind, the DOM container the
    executor scopes 'Add another' to, and (for education) the option lists its comboboxes offer.

    Carried only for a form that actually has such a section, which today is a local stand-in only
    (the hosted DOM is legacy-evidence-only, unobserved). A form without one has no ``sections``,
    so no ordinary form's schema, fingerprint or package hash changes.
    """

    kind: str = Field(pattern="^(education|employment)$")
    root: str = Field(min_length=1, max_length=200)  # CSS selector of the section container
    schools: list[SectionOptionSpec] = Field(default_factory=list, max_length=5000)
    degrees: list[SectionOptionSpec] = Field(default_factory=list, max_length=500)
    disciplines: list[SectionOptionSpec] = Field(default_factory=list, max_length=5000)
    # D149 (the Workday-style stand-in's Work Experience): the wizard page the section is on, and
    # whether the page requires at least one entry. Written only when set, so a Greenhouse
    # section's stored schema and fingerprint are unchanged.
    step: str | None = Field(default=None, min_length=1, max_length=200)
    required: bool = False
    # D155: the parts an entry asks beyond those always entered, which NoEfforts enters from your
    # record when it holds them (the Workday-style stand-in's Location and Role Description),
    # and those of them the page requires; sorted, each once. Written only when set, so every
    # other section's stored schema and fingerprint are unchanged.
    parts: list[EntryPart] = Field(default_factory=list, max_length=2)
    required_parts: list[EntryPart] = Field(default_factory=list, max_length=2)
    # D157: the longest text the page accepts in an entry's typed parts (`maxlength`), by frozen
    # field name (LIMITED_FIELDS); a Location or Role Description limit only where the entry
    # asks it. Written only when set, so every other section's stored schema and fingerprint are
    # unchanged.
    limits: dict[str, StrictInt] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _limits_known(self):
        if self.limits and (
            self.kind != "employment"
            or not set(self.limits) <= set(LIMITED_FIELDS)
            or not set(self.limits) & set(ENTRY_PARTS) <= set(self.parts)
            or any(not 1 <= v <= MAX_LIMIT for v in self.limits.values())
        ):
            raise ValueError("an entry's limits are an employment section's, on its typed parts")
        return self

    @model_validator(mode="after")
    def _parts_known(self):
        if (self.parts != sorted(set(self.parts))
                or self.required_parts != sorted(set(self.required_parts))
                or not set(self.required_parts) <= set(self.parts)
                or (self.parts and self.kind != "employment")):  # fmt: skip
            raise ValueError("an entry's parts are an employment section's, sorted and each once")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        out = handler(self)
        if isinstance(out, dict):
            if out.get("step") is None:
                out.pop("step", None)
            if not out.get("required"):
                out.pop("required", None)
            if not out.get("parts"):
                out.pop("parts", None)
            if not out.get("required_parts"):
                out.pop("required_parts", None)
            if out.get("limits"):  # D157: sorted, so the same limits always dump the same
                out["limits"] = dict(sorted(out["limits"].items()))
            else:
                out.pop("limits", None)
        return out


class WizardSpec(BaseModel):
    """D142: a captured multi-page application (the Workday-style stand-in's wizard): its pages'
    names in order, the last one the review page that holds the only submit. Each field's `step`
    is the page it is on (preparation/workday.py checks that before setting this). Set only by
    that capture, never by hand (the manual form endpoint refuses it)."""

    pages: list[str] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def _names(self):
        if any(not p.strip() or len(p) > 200 for p in self.pages):
            raise ValueError("a wizard page needs a name of at most 200 characters")
        if len(set(self.pages)) != len(self.pages):
            raise ValueError("wizard page names must be unique")
        return self


class FormSchema(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    # The form's own submission target as written in the page (may be relative).
    action: str | None = Field(default=None, max_length=2048)
    method: str | None = Field(default=None, max_length=10)
    fields: list[FormField] = Field(min_length=1, max_length=300)
    # D120: stand-in-only structured sections; empty for every ordinary/real form.
    sections: list[SectionSpec] = Field(default_factory=list, max_length=4)
    # D142: stand-in-only multi-page wizard; None for every other form.
    wizard: WizardSpec | None = None

    @model_validator(mode="after")
    def _unique(self):
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("field keys must be unique")
        if len({s.kind for s in self.sections}) != len(self.sections):
            raise ValueError("a section kind may appear at most once")
        # D149: a section on a page is on one of a wizard's pages before its review page.
        pages = self.wizard.pages[:-1] if self.wizard else []
        if any(s.step is not None and s.step not in pages for s in self.sections):
            raise ValueError("a section's page must be one of the wizard's pages before the last")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        # D142: written only for a form that has one, so every other stored form keeps its
        # exact content (as FormField's `widget`).
        out = handler(self)
        if isinstance(out, dict) and out.get("wizard") is None:
            out.pop("wizard", None)
        return out


def normalize(s: str | None) -> str:
    s = (s or "").replace("’", "'").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip(" *:?.").strip()


def field_fingerprint(f: FormField) -> str:
    """Changes whenever the wording, type, requirement or options change."""
    payload = [
        f.key,
        normalize(f.label),
        normalize(f.help_text),
        f.type.value,
        f.required,
        [normalize(o.label) for o in f.options],
    ]
    # Added only when present, so fingerprints of forms without them are unchanged.
    if f.condition:
        payload.append(["if", f.condition.key, sorted(f.condition.any_of)])
    if f.type == FieldType.unsupported:
        payload.append(["unsupported", f.unsupported_reason or ""])
    if f.widget:  # D104
        payload.append(["widget", f.widget])
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:24]


def form_fingerprint(schema: FormSchema) -> str:
    parts = [f"action={schema.action or ''}", f"method={(schema.method or '').lower()}"]
    parts += [field_fingerprint(f) for f in schema.fields]
    for s in schema.sections:  # D120: added only when present, so forms without one are unchanged
        opts = [
            f"{o.id}={normalize(o.text)}"
            for group in (s.schools, s.degrees, s.disciplines)
            for o in group
        ]
        # D149: its page and requirement only when set, so a Greenhouse section's is unchanged;
        # as one JSON value, so no page name can read as another page and requirement.
        extra = ([json.dumps({"required": s.required, "step": s.step})]
                 if s.step or s.required else [])  # fmt: skip
        if s.parts:  # D155: only when set, so every other section's is unchanged
            extra.append(json.dumps({"parts": s.parts, "required_parts": s.required_parts}))
        if s.limits:  # D157: likewise
            extra.append(json.dumps({"limits": s.limits}, sort_keys=True))
        parts.append("|".join(["section", s.kind, s.root, *opts, *extra]))
    if schema.wizard:  # D142: added only for a wizard, so every other form's is unchanged
        # The pages' names in order and which question is on which page: never which page is
        # shown, so the same form reads the same before and after a Next.
        parts.append("|".join(["wizard", *(
            f"{n}=" + ",".join(f.key for f in schema.fields if f.step == n)
            for n in schema.wizard.pages)]))  # fmt: skip
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


# ----------------------------------------------------------------------------------------------
# HTML extraction. Supports the common accessible patterns: <label for>, wrapping <label>,
# <fieldset><legend> groups for radios/checkboxes, aria-describedby help text, and data-step /
# <section> headings for multi-step forms. Unknown structures raise rather than guess.


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text", "twice")

    def __init__(
        self,
        tag: str,
        attrs: dict[str, str],
        parent: "_Node | None",
        twice: dict[str, str] | None = None,
    ) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[_Node | str] = []
        # D157: the attributes written more than once on the tag, each with the value written
        # first (D158), which the browser keeps where `attrs` keeps the last: a check that must
        # read the tag as the browser does refuses such a tag, or reads that first value.
        self.twice = twice or {}

    def all_text(self) -> str:
        out = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            elif c.tag not in ("input", "select", "textarea", "option", "script", "style"):
                out.append(c.all_text())
        return re.sub(r"\s+", " ", " ".join(out)).strip()

    def walk(self):
        for c in self.children:
            if isinstance(c, _Node):
                yield c
                yield from c.walk()

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent


_VOID = {"input", "br", "hr", "img", "meta", "link", "area", "base", "col", "source", "wbr"}


def _twice(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    """D157: the attribute names a tag writes more than once, each with the value written first,
    the one the browser keeps (D158; `_Node.twice`)."""
    names = [k for k, _ in attrs]
    if len(set(names)) == len(names):
        return {}
    first: dict[str, str] = {}
    for k, v in attrs:
        if names.count(k) > 1:
            first.setdefault(k, v if v is not None else "")
    return first


def _question_limit(raw: str | None, top: int = 100_000) -> int | None:
    """An ordinary question's `maxlength` (`FormField.max_length`), read as the browser reads it
    (`read_maxlength`; D158: ASCII whitespace around the digits too, as the browser skips it)
    and recorded only from 1 to `top` (`FormField`'s own bounds), None otherwise: never an error
    of reading the form, whatever the page writes (D157: a superscript digit, more digits than
    Python converts, another script's digits, 0, or above `top` as some page frameworks write).
    A limit not recorded is not checked before approval; the readback still stops a value the
    browser cut."""
    limit = read_maxlength(raw)
    if isinstance(limit, bool) or limit is None or limit > top:
        return None
    return limit


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur,
                     _twice(attrs))  # fmt: skip
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(
            _Node(tag, {k: (v or "") for k, v in attrs}, self.cur, _twice(attrs))
        )

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.children.append(data)


class ExtractionError(ValueError):
    pass


# CAPTCHA and bot-check widgets, by the markup their vendors document (the execution adapters
# stop at the same ones: execution/adapters/greenhouse.py).
_CHALLENGE = re.compile(
    r"""class\s*=\s*["'][^"']*\b(g-recaptcha|h-captcha|cf-turnstile)\b"""
    r"""|<(iframe|script)\b[^>]*\bsrc\s*=\s*["'][^"']*(recaptcha|hcaptcha\.com|challenges\.cloudflare\.com)""",
    re.IGNORECASE,
)
BOT_CHECK_KEY = "bot_check"
_AUTOCOMPLETE = ("list", "both", "inline")
_NATIVE = {"input", "select", "textarea"}
_ARIA_WIDGETS = {"radiogroup", "listbox", "combobox", "switch", "checkbox", "radio", "slider",
                 "spinbutton", "textbox", "searchbox"}  # fmt: skip
_UNSUPPORTED_INPUT = {
    "password": "a password: signing in or creating an account is yours, on the employer's "
    "site; NoEfforts never asks for or keeps a password",
    "one-time-code": "a verification code: you enter codes yourself when the employer sends "
    "one; NoEfforts never keeps them",
}


def _bot_check() -> "FormField":
    return FormField(
        key=BOT_CHECK_KEY,
        label="A bot check (CAPTCHA) on this form",
        type=FieldType.unsupported,
        required=True,
        unsupported_reason="a CAPTCHA or bot check: NoEfforts never solves one; apply on the "
        "employer's site yourself",
    )


def extract_form_schema(html: str, *, challenges: bool = False, skip=None) -> FormSchema:
    """`challenges`: also report a CAPTCHA or bot check on the page as a required unsupported
    field (the generic capture path). The Greenhouse paths leave it to their adapters, which
    stop when one appears. `skip` (D149): a control whose name it accepts is not read at all
    (the Workday-style capture reads its Work Experience entries itself)."""
    if len(html) > 2_000_000:
        raise ExtractionError("HTML too large")
    b = _TreeBuilder()
    b.feed(html)
    nodes = list(b.root.walk())
    by_id = {n.attrs["id"]: n for n in nodes if n.attrs.get("id")}
    labels_for = {n.attrs["for"]: n for n in nodes if n.tag == "label" and n.attrs.get("for")}
    title_node = next((n for n in nodes if n.tag in ("h1", "title")), None)

    def step_of(n: _Node) -> str | None:
        for a in n.ancestors():
            if a.attrs.get("data-step"):
                return a.attrs["data-step"]
        return None

    def help_of(n: _Node) -> str | None:
        ids = (n.attrs.get("aria-describedby") or "").split()
        texts = [by_id[i].all_text() for i in ids if i in by_id]
        return " ".join(t for t in texts if t) or None

    def label_of(n: _Node) -> str:
        if n.attrs.get("id") in labels_for:
            return labels_for[n.attrs["id"]].all_text()
        for a in n.ancestors():
            if a.tag == "label":
                return a.all_text()
        # D118 (legacy notes: Recruitee, SmartRecruiters): the question's text is linked by
        # aria-labelledby, with no <label>. Only text the page itself links counts; a missing
        # label still stops the capture (nothing guessed from siblings or ancestors).
        ids = (n.attrs.get("aria-labelledby") or "").split()
        linked = " ".join(t for t in (by_id[i].all_text() for i in ids if i in by_id) if t)
        if linked.strip():
            return linked.strip()
        if n.attrs.get("aria-label"):
            return n.attrs["aria-label"]
        raise ExtractionError(f"no label for field '{n.attrs.get('name')}'")

    # D118 (legacy notes: Recruitee, Breezy, Workable): a page can hold another form, such as a
    # job-alert sign-up with its own email field and button. Only the application form is read:
    # the single form, or of several the one with a file upload; more than one such form, or
    # none, is refused rather than guessed.
    app_form = _application_form(nodes)
    if app_form is not None:
        nodes = [n for n in nodes if n is app_form or app_form in n.ancestors()]

    fields: list[FormField] = []
    seen_groups: set[str] = set()
    for n in nodes:
        name = n.attrs.get("name")
        if n.tag not in ("input", "select", "textarea") or not name:
            continue
        if skip is not None and skip(name):
            continue
        itype = n.attrs.get("type", "text").lower() if n.tag == "input" else n.tag
        if itype in ("hidden", "submit", "button", "reset", "image"):
            continue
        required = "required" in n.attrs or n.attrs.get("aria-required") == "true"
        common = dict(key=name, step=step_of(n))

        def refused(label: str, help_text: str | None, req: bool, common=common) -> FormField:
            """D159: a question whose control's form would not send exactly what is typed into
            it (`sent_otherwise`): never filled, a required one a checkpoint (D136)."""
            return FormField(label=label, help_text=help_text, type=FieldType.unsupported,
                             required=req, unsupported_reason=SENT_OTHERWISE, **common)  # fmt: skip

        if itype in ("radio", "checkbox"):
            group = next((a for a in n.ancestors() if a.tag == "fieldset"), None)
            members = [m for m in nodes if m.tag == "input" and m.attrs.get("name") == name]
            if itype == "checkbox" and len(members) == 1 and group is None:
                if sent_otherwise(n):
                    fields.append(refused(label_of(n), help_of(n), required))
                    continue
                fields.append(
                    FormField(
                        label=label_of(n),
                        help_text=help_of(n),
                        type=FieldType.checkbox,
                        required=required,
                        **common,
                    )
                )
                continue
            if name in seen_groups:
                continue
            seen_groups.add(name)
            if group is None:
                raise ExtractionError(f"option group '{name}' has no fieldset/legend")
            legend = next(
                (c for c in group.children if isinstance(c, _Node) and c.tag == "legend"), None
            )
            if legend is None:
                raise ExtractionError(f"option group '{name}' has no legend")
            options = [Option(value=m.attrs.get("value", ""), label=label_of(m)) for m in members]
            req = (
                required or "required" in group.attrs or group.attrs.get("aria-required") == "true"
            )
            if any(sent_otherwise(m) for m in members):  # D159: one choice is enough
                fields.append(refused(legend.all_text(), help_of(group) or help_of(n), req))
                continue
            fields.append(
                FormField(
                    label=legend.all_text(),
                    help_text=help_of(group) or help_of(n),
                    type=FieldType.radio if itype == "radio" else FieldType.checkbox_group,
                    required=req,
                    options=options,
                    **common,
                )
            )
            continue
        if n.tag == "select":
            if sent_otherwise(n):  # D159
                fields.append(refused(label_of(n), help_of(n), required))
                continue
            opts = [
                Option(value=o.attrs.get("value", o.all_text()), label=o.all_text())
                for o in n.walk()
                if o.tag == "option"
            ]
            opts = [o for o in opts if o.value != ""]  # drop "Select…" placeholders
            ftype = FieldType.multiselect if "multiple" in n.attrs else FieldType.select
            fields.append(
                FormField(
                    label=label_of(n),
                    help_text=help_of(n),
                    type=ftype,
                    required=required,
                    options=opts,
                    **common,
                )
            )
            continue
        credential = (
            "password"
            if itype == "password"
            else "one-time-code"
            if (n.attrs.get("autocomplete") or "").lower() == "one-time-code"
            else None
        )
        if credential:
            fields.append(
                FormField(
                    label=label_of(n),
                    help_text=help_of(n),
                    type=FieldType.unsupported,
                    required=required,
                    unsupported_reason=_UNSUPPORTED_INPUT[credential],
                    **common,
                )
            )
            continue
        if n.tag == "input" and (
            (n.attrs.get("role") or "").lower() == "combobox"
            or (n.attrs.get("aria-autocomplete") or "").lower() in _AUTOCOMPLETE
        ):
            fields.append(
                FormField(
                    label=label_of(n),
                    help_text=help_of(n),
                    type=FieldType.unsupported,
                    required=required,
                    unsupported_reason="a search-as-you-type control (combobox): NoEfforts "
                    "does not operate it",
                    **common,
                )
            )
            continue
        if sent_otherwise(n):  # D159: after the reasons above, which keep their fingerprints
            fields.append(refused(label_of(n), help_of(n), required))
            continue
        ftype = (
            FieldType.textarea
            if n.tag == "textarea"
            else FieldType(itype)
            if itype in {t.value for t in FieldType}
            else FieldType.text
        )
        maxlen = n.twice.get("maxlength", n.attrs.get("maxlength"))  # D158: as the browser
        fields.append(
            FormField(
                label=label_of(n),
                help_text=help_of(n),
                type=ftype,
                required=required,
                max_length=_question_limit(maxlen),
                accept=n.attrs.get("accept") if ftype == FieldType.file else None,
                **common,
            )
        )
    fields += _aria_widgets(nodes, by_id, step_of, {f.key for f in fields})
    if not fields:
        raise ExtractionError("no form fields found")
    if challenges and _CHALLENGE.search(html) and all(f.key != BOT_CHECK_KEY for f in fields):
        fields.append(_bot_check())
    form_node = app_form or next((n for n in nodes if n.tag == "form"), None)
    return FormSchema(
        title=title_node.all_text() if title_node else None,
        action=form_node.attrs.get("action") if form_node else None,
        method=(form_node.attrs.get("method") or "get").lower() if form_node else None,
        fields=fields,
    )


def _application_form(nodes: list["_Node"]) -> "_Node | None":
    """D118: the one application form among several, or None when it cannot be singled out.
    The application form is the form that holds a file upload (a résumé), else the only form on
    the page. Several forms with an upload, or none and more than one form, is ambiguous: None,
    and the caller falls back to reading the whole page (and refuses on the usual grounds)."""
    forms = [n for n in nodes if n.tag == "form"]
    if len(forms) <= 1:
        return forms[0] if forms else None

    def has_upload(form: "_Node") -> bool:
        return any(
            d.tag == "input" and d.attrs.get("type", "").lower() == "file"
            for d in form.walk()
            if isinstance(d, _Node)
        )

    with_upload = [f for f in forms if has_upload(f)]
    return with_upload[0] if len(with_upload) == 1 else None


def _aria_widgets(nodes, by_id, step_of, taken: set[str]) -> list[FormField]:
    """Controls built from ARIA roles with no native control inside (D81): each one is a
    question NoEfforts cannot operate, so it becomes an unsupported field (required when
    aria-required is "true") rather than disappearing. A listbox that a combobox owns, and a
    widget inside one already counted, are part of that control. Hidden ones are skipped, as
    hidden inputs are."""
    owned: set[str] = set()
    for n in nodes:
        for attr in ("aria-controls", "aria-owns"):
            owned |= set((n.attrs.get(attr) or "").split())
    counted: list = []
    out: list[FormField] = []
    for n in nodes:
        role = (n.attrs.get("role") or "").lower()
        if role not in _ARIA_WIDGETS or n.tag in _NATIVE:
            continue
        if "hidden" in n.attrs or n.attrs.get("aria-hidden") == "true":
            continue
        if n.attrs.get("id") in owned or any(d.tag in _NATIVE for d in n.walk()):
            continue
        if any(a in counted for a in n.ancestors()):
            continue
        counted.append(n)
        ids = (n.attrs.get("aria-labelledby") or "").split()
        label = (
            n.attrs.get("aria-label")
            or " ".join(by_id[i].all_text() for i in ids if i in by_id).strip()
            or n.all_text()[:200]
            or "An interactive control NoEfforts does not recognise"
        )
        raw = re.sub(r"[^A-Za-z0-9_.:\[\]-]", "_", n.attrs.get("id") or "") or str(len(out) + 1)
        key = f"aria:{raw}"
        while key in taken:
            key += "_"
        taken.add(key)
        out.append(
            FormField(
                key=key,
                label=label[:2000],
                type=FieldType.unsupported,
                required=n.attrs.get("aria-required") == "true",
                unsupported_reason=f"a custom control (role={role}) with no native input: "
                "NoEfforts does not operate it",
                step=step_of(n),
            )
        )
    return out
