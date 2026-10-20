"""Evidence-based mapping between Greenhouse job-post fields and the controls of a page whose
controls have ids but no `name` attributes (the "v2" structure; see
docs/greenhouse-compatibility-report.md and fixtures/ats_receiver/greenhouse_v2.py).

A field is mapped only when ALL of these hold:
  * exactly one control has `id` equal to the field name;
  * its element/role suits the field type (text input, textarea, file input, combobox, ...);
  * its accessible name equals the field's label (whitespace, case and a trailing required
    marker ignored).
Anything else is reported as absent / ambiguous / type mismatch / label mismatch and the form
is refused; nothing is guessed. Hidden-at-load questions are flagged; this structure exposes
no trigger, so their condition is recorded as unknown (never filled; a checkpoint if
required)."""

import re
from dataclasses import asdict, dataclass, field

from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import (
    Condition,
    ExtractionError,
    FieldType,
    FormField,
    FormSchema,
    _Node,
    _TreeBuilder,
)

EXTRACTION_VERSION = "greenhouse-dom-v1"
UNKNOWN_TRIGGER = "unknown-trigger"  # Condition.key for "shown by page logic we cannot see"


@dataclass
class Control:
    id: str
    tag: str
    type: str | None
    role: str | None
    name_attr: bool
    accessible_name: str | None
    name_source: str | None  # labelledby | label_for | label_wrap | aria_label | None
    required: bool
    hidden: bool  # hidden attribute, aria-hidden or type=hidden on it or an ancestor
    in_form: bool
    group: str | None  # role=group / fieldset container id (or "anonymous")
    controls: str | None  # aria-controls target id
    controls_listbox: bool  # aria-controls points at role=listbox
    describedby: bool


@dataclass
class FieldMapping:
    key: str
    type: str
    required: bool
    # mapped | search_picker | protocol | absent | ambiguous | type_mismatch | label_mismatch
    status: str
    candidates: int
    control: Control | None = None
    hidden_at_load: bool = False
    notes: list[str] = field(default_factory=list)


_CTRL_TAGS = {"input", "select", "textarea"}
_TEXTLIKE = {FieldType.text, FieldType.email, FieldType.tel, FieldType.url, FieldType.number}


def _norm(s: str | None) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip().lower()
    return s.rstrip("*").strip()


def snapshot(html: str) -> list[Control]:
    """Structural snapshot of every form control (and role=combobox element) in the page."""
    if len(html) > 2_000_000:
        raise ExtractionError("HTML too large")
    b = _TreeBuilder()
    b.feed(html)
    nodes = [n for n in b.root.walk() if isinstance(n, _Node)]
    by_id: dict[str, list[_Node]] = {}
    for n in nodes:
        if n.attrs.get("id"):
            by_id.setdefault(n.attrs["id"], []).append(n)
    label_for = {n.attrs["for"]: n for n in nodes if n.tag == "label" and n.attrs.get("for")}

    def text_of(ids: str) -> str:
        parts = []
        for i in ids.split():
            targets = by_id.get(i) or []
            if len(targets) == 1:
                parts.append(targets[0].all_text())
        return " ".join(p for p in parts if p)

    out = []
    for n in nodes:
        role = n.attrs.get("role")
        if n.tag not in _CTRL_TAGS and role != "combobox":
            continue
        cid = n.attrs.get("id")
        if not cid:
            continue
        name, src = None, None
        if n.attrs.get("aria-labelledby"):
            name, src = text_of(n.attrs["aria-labelledby"]) or None, "labelledby"
        if not name and cid in label_for:
            name, src = label_for[cid].all_text(), "label_for"
        if not name:
            wrap = next((a for a in n.ancestors() if a.tag == "label"), None)
            if wrap is not None:
                name, src = wrap.all_text(), "label_wrap"
        if not name and n.attrs.get("aria-label"):
            name, src = n.attrs["aria-label"], "aria_label"
        chain = [n, *n.ancestors()]
        hidden = n.attrs.get("type", "").lower() == "hidden" or any(
            "hidden" in a.attrs or a.attrs.get("aria-hidden") == "true" for a in chain
        )
        grp = next(
            (a for a in n.ancestors() if a.tag == "fieldset" or a.attrs.get("role") == "group"),
            None,
        )
        target = n.attrs.get("aria-controls")
        tnodes = by_id.get(target or "", [])
        out.append(
            Control(
                id=cid,
                tag=n.tag,
                type=(n.attrs.get("type") or "text").lower() if n.tag == "input" else None,
                role=role,
                name_attr=bool(n.attrs.get("name")),
                accessible_name=name,
                name_source=src,
                required="required" in n.attrs or n.attrs.get("aria-required") == "true",
                hidden=hidden,
                in_form=any(a.tag == "form" for a in n.ancestors()),
                group=(grp.attrs.get("id") or "anonymous") if grp is not None else None,
                controls=target,
                controls_listbox=len(tnodes) == 1 and tnodes[0].attrs.get("role") == "listbox",
                describedby=bool(n.attrs.get("aria-describedby")),
            )
        )
    return out


def _suits(f: FormField, c: Control) -> bool:
    t = f.type
    if t in (FieldType.select, FieldType.multiselect, FieldType.checkbox_group):
        return c.role == "combobox" or c.tag == "select"
    if c.role == "combobox":
        return False
    if t == FieldType.textarea:
        return c.tag == "textarea"
    if t == FieldType.file:
        return c.tag == "input" and c.type == "file"
    if t == FieldType.checkbox:
        return c.tag == "input" and c.type == "checkbox"
    if t == FieldType.unsupported:
        return True
    return c.tag == "input" and c.type in ("text", "email", "tel", "url", "number", "search")


def map_fields(fields: list[FormField], controls: list[Control]) -> list[FieldMapping]:
    by_id: dict[str, list[Control]] = {}
    for c in controls:
        by_id.setdefault(c.id, []).append(c)
    out = []
    for f in fields:
        key = f.key.removesuffix("[]")
        cands = by_id.get(key, [])
        m = FieldMapping(f.key, f.type.value, f.required, "absent", len(cands))
        if f.type == FieldType.unsupported:
            # Page-managed hidden values: never filled; present or not, it is not a question.
            m.status = "protocol"
            m.control = cands[0] if len(cands) == 1 else None
        elif len(cands) > 1:
            m.status = "ambiguous"
        elif len(cands) == 1:
            c = cands[0]
            m.control, m.hidden_at_load = c, c.hidden
            if f.type in _TEXTLIKE and c.role == "combobox":
                # A text question rendered as search-as-you-type (e.g. a location picker):
                # its value comes from a search we do not perform.
                m.status = (
                    "search_picker"
                    if _norm(c.accessible_name) == _norm(f.label)
                    else "label_mismatch"
                )
            elif not _suits(f, c):
                m.status = "type_mismatch"
            elif _norm(c.accessible_name) != _norm(f.label):
                m.status = "label_mismatch"
            else:
                m.status = "mapped"
        out.append(m)
    return out


def unmatched_controls(fields: list[FormField], controls: list[Control]) -> list[Control]:
    """Page controls that no API field names (alternatives such as resume_text included)."""
    keys = {f.key.removesuffix("[]") for f in fields}
    return [c for c in controls if c.id not in keys]


ACCEPTED = ("mapped", "protocol", "search_picker")


def build_schema(api: dict, page_html: str) -> tuple[FormSchema, list[FieldMapping]]:
    """Job-post fields, verified against the page's controls. Raises gh.SchemaMismatch unless
    every field is mapped (or is a page-managed hidden value)."""
    from_api = gh.schema_from_api(api)
    controls = snapshot(page_html)
    mappings = map_fields(from_api.fields, controls)
    bad = [m for m in mappings if m.status not in ACCEPTED]
    if bad:
        detail = "; ".join(f"{m.key}: {m.status}" for m in bad)
        raise gh.SchemaMismatch(f"page controls do not match the job data ({detail})")
    form = _form_attrs(page_html)
    fields = []
    for f, m in zip(from_api.fields, mappings, strict=True):
        if m.status == "search_picker":
            f = f.model_copy(
                update={
                    "type": FieldType.unsupported,
                    "unsupported_reason": "search picker (its value comes from a search "
                    "NoEfforts does not perform)",
                }
            )
        elif m.status == "mapped" and m.control.role == "combobox" and f.type != FieldType.select:
            # Multi-choice comboboxes were neither observed nor modelled: never guessed at.
            f = f.model_copy(
                update={
                    "type": FieldType.unsupported,
                    "unsupported_reason": "multi-choice dropdown (not supported yet)",
                    "options": [],
                }
            )
        elif m.hidden_at_load and f.type != FieldType.unsupported:
            # Shown by page logic we cannot see: its condition is unknown, never a guess.
            f = f.model_copy(update={"condition": Condition(key=UNKNOWN_TRIGGER, any_of=["?"])})
        fields.append(f)
    return (
        FormSchema(
            title=from_api.title,
            action=form.get("data-submit-path"),
            method="post" if form.get("data-submit-path") else None,
            fields=fields,
        ),
        mappings,
    )


def _form_attrs(page_html: str) -> dict:
    b = _TreeBuilder()
    b.feed(page_html)
    forms = [n for n in b.root.walk() if isinstance(n, _Node) and n.tag == "form"]
    return dict(forms[0].attrs) if len(forms) == 1 else {}


def as_dict(c: Control | None) -> dict | None:
    return asdict(c) if c else None
