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

from pydantic import BaseModel, Field, model_serializer, model_validator

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
WIDGETS = ("phone_country", "location_search", "location_structured")


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
    widget: str | None = Field(default=None, max_length=50)  # D104: one of WIDGETS

    @model_validator(mode="after")
    def _options(self):
        if self.type in CHOICE_TYPES | MULTI_TYPES and not self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} needs options")
        if self.type not in CHOICE_TYPES | MULTI_TYPES and self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} cannot have options")
        shape = {"phone_country": FieldType.select, "location_search": FieldType.text,
                 "location_structured": FieldType.unsupported}  # fmt: skip
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


class FormSchema(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    # The form's own submission target as written in the page (may be relative).
    action: str | None = Field(default=None, max_length=2048)
    method: str | None = Field(default=None, max_length=10)
    fields: list[FormField] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def _unique(self):
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("field keys must be unique")
        return self


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
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


# ----------------------------------------------------------------------------------------------
# HTML extraction. Supports the common accessible patterns: <label for>, wrapping <label>,
# <fieldset><legend> groups for radios/checkboxes, aria-describedby help text, and data-step /
# <section> headings for multi-step forms. Unknown structures raise rather than guess.


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[_Node | str] = []

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


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

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


def extract_form_schema(html: str, *, challenges: bool = False) -> FormSchema:
    """`challenges`: also report a CAPTCHA or bot check on the page as a required unsupported
    field (the generic capture path). The Greenhouse paths leave it to their adapters, which
    stop when one appears."""
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
        if n.attrs.get("aria-label"):
            return n.attrs["aria-label"]
        raise ExtractionError(f"no label for field '{n.attrs.get('name')}'")

    fields: list[FormField] = []
    seen_groups: set[str] = set()
    for n in nodes:
        name = n.attrs.get("name")
        if n.tag not in ("input", "select", "textarea") or not name:
            continue
        itype = n.attrs.get("type", "text").lower() if n.tag == "input" else n.tag
        if itype in ("hidden", "submit", "button", "reset", "image"):
            continue
        required = "required" in n.attrs or n.attrs.get("aria-required") == "true"
        common = dict(key=name, step=step_of(n))
        if itype in ("radio", "checkbox"):
            group = next((a for a in n.ancestors() if a.tag == "fieldset"), None)
            members = [m for m in nodes if m.tag == "input" and m.attrs.get("name") == name]
            if itype == "checkbox" and len(members) == 1 and group is None:
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
        ftype = (
            FieldType.textarea
            if n.tag == "textarea"
            else FieldType(itype)
            if itype in {t.value for t in FieldType}
            else FieldType.text
        )
        maxlen = n.attrs.get("maxlength")
        fields.append(
            FormField(
                label=label_of(n),
                help_text=help_of(n),
                type=ftype,
                required=required,
                max_length=int(maxlen) if maxlen and maxlen.isdigit() else None,
                accept=n.attrs.get("accept") if ftype == FieldType.file else None,
                **common,
            )
        )
    fields += _aria_widgets(nodes, by_id, step_of, {f.key for f in fields})
    if not fields:
        raise ExtractionError("no form fields found")
    if challenges and _CHALLENGE.search(html) and all(f.key != BOT_CHECK_KEY for f in fields):
        fields.append(_bot_check())
    form_node = next((n for n in nodes if n.tag == "form"), None)
    return FormSchema(
        title=title_node.all_text() if title_node else None,
        action=form_node.attrs.get("action") if form_node else None,
        method=(form_node.attrs.get("method") or "get").lower() if form_node else None,
        fields=fields,
    )


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
