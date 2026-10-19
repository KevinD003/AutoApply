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

from pydantic import BaseModel, Field, model_validator

EXTRACTION_VERSION = "html-v1"


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


CHOICE_TYPES = {FieldType.radio, FieldType.select}
MULTI_TYPES = {FieldType.checkbox_group, FieldType.multiselect}
TEXT_TYPES = {FieldType.text, FieldType.textarea, FieldType.email, FieldType.tel, FieldType.url}


class Option(BaseModel):
    value: str = Field(max_length=500)
    label: str = Field(max_length=500)


class FormField(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:\[\]-]+$")
    label: str = Field(min_length=1, max_length=2000)
    help_text: str | None = Field(default=None, max_length=4000)
    type: FieldType
    required: bool = False
    options: list[Option] = Field(default_factory=list, max_length=500)
    step: str | None = Field(default=None, max_length=200)
    max_length: int | None = Field(default=None, ge=1, le=100_000)
    accept: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _options(self):
        if self.type in CHOICE_TYPES | MULTI_TYPES and not self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} needs options")
        if self.type not in CHOICE_TYPES | MULTI_TYPES and self.options:
            raise ValueError(f"field '{self.key}' of type {self.type} cannot have options")
        return self


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


def extract_form_schema(html: str) -> FormSchema:
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
    if not fields:
        raise ExtractionError("no form fields found")
    form_node = next((n for n in nodes if n.tag == "form"), None)
    return FormSchema(
        title=title_node.all_text() if title_node else None,
        action=form_node.attrs.get("action") if form_node else None,
        method=(form_node.attrs.get("method") or "get").lower() if form_node else None,
        fields=fields,
    )
