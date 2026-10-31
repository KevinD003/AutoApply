"""Evidence-based mapping between Greenhouse job-post fields and the controls of a page whose
controls have ids but no `name` attributes (the "v2" structure; see
docs/greenhouse-compatibility-report.md and fixtures/ats_receiver/greenhouse_v2.py).

A field is mapped only when ALL of these hold:
  * exactly one control has `id` equal to the field name;
  * its element/role suits the field type (text input, textarea, file input, combobox, ...);
  * its accessible name equals the field's label (whitespace, case and a trailing required
    marker ignored), or, for an attachment only, its enclosing group's accessible name does
    and that group contains no other file input ("mapped_via_group").
Anything else is reported as absent / ambiguous / type mismatch / label mismatch and the form
is refused; nothing is guessed. Hidden-at-load questions are flagged; this structure exposes
no trigger, so their condition is recorded as unknown (never filled; a checkpoint if
required)."""

import re
from dataclasses import asdict, dataclass, field

from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import (
    KEY_PATTERN,
    Condition,
    ExtractionError,
    FieldType,
    FormField,
    FormSchema,
    Option,
    _Node,
    _TreeBuilder,
)

# v2: a visible page control the job data does not list becomes a blocking field at capture
# (see `unlisted_controls`), so the route is a checkpoint before anything can be approved.
# v3 (D104): on local stand-ins only (`build_schema(stand_ins=True)`), two structures are
# recognised instead of refused: the country picker beside the phone field
# (`phone_country_field`) and a location search picker whose own script sets the job data's
# hidden values (`location_picker`). Anywhere else they stay checkpoints, as in v2.
EXTRACTION_VERSION = "greenhouse-dom-v3"
UNKNOWN_TRIGGER = "unknown-trigger"  # Condition.key for "shown by page logic we cannot see"
UNLISTED_REASON = (
    "a control on the page that the job data does not list: what it asks, and whether it is "
    "required, are never inferred"
)


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
    # Internal: identity of the enclosing group (document order) and the group's own
    # accessible name (aria-labelledby / aria-label / legend). Never printed as text.
    group_key: int | None = None
    group_name: str | None = None


@dataclass
class FieldMapping:
    key: str
    type: str
    required: bool
    # mapped | mapped_via_group | search_picker | protocol | absent | ambiguous |
    # type_mismatch | label_mismatch
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
    order = {id(n): i for i, n in enumerate(nodes)}
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
        gname = None
        if grp is not None:
            if grp.attrs.get("aria-labelledby"):
                gname = text_of(grp.attrs["aria-labelledby"]) or None
            if not gname and grp.attrs.get("aria-label"):
                gname = grp.attrs["aria-label"]
            if not gname:
                legend = next(
                    (c for c in grp.children if isinstance(c, _Node) and c.tag == "legend"), None
                )
                gname = legend.all_text() if legend is not None else None
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
                group_key=order[id(grp)] if grp is not None else None,
                group_name=gname,
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
    file_groups: dict[int, int] = {}
    for c in controls:
        by_id.setdefault(c.id, []).append(c)
        if c.tag == "input" and c.type == "file" and c.group_key is not None:
            file_groups[c.group_key] = file_groups.get(c.group_key, 0) + 1
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
                # One validated exception (observed on a real page in B3): an attachment input
                # whose own label differs but whose enclosing group is named exactly as the
                # question, and that group holds no other file input.
                m.status = (
                    "mapped_via_group"
                    if f.type == FieldType.file
                    and c.group_key is not None
                    and _norm(c.group_name) == _norm(f.label)
                    and file_groups.get(c.group_key, 0) == 1
                    else "label_mismatch"
                )
            else:
                m.status = "mapped"
        out.append(m)
    return out


def unmatched_controls(fields: list[FormField], controls: list[Control]) -> list[Control]:
    """Page controls that no API field names (alternatives such as resume_text included)."""
    keys = {f.key.removesuffix("[]") for f in fields}
    return [c for c in controls if c.id not in keys]


def unlisted_controls(fields: list[FormField], controls: list[Control]) -> list[Control]:
    """Visible controls in the form that no field names, a file field's text alternative
    excepted. They are never filled or interpreted: blocking fields at capture
    (`build_schema`) and, if one appears later, a stop before disclosure (the adapter)."""
    alternatives = {f"{f.key}_text" for f in fields if f.type == FieldType.file}
    return [c for c in unmatched_controls(fields, controls)
            if c.in_form and not c.hidden and c.id not in alternatives]  # fmt: skip


ACCEPTED = ("mapped", "mapped_via_group", "protocol", "search_picker")

# -- D104: companion structures recognised on local stand-ins only --------------------------
# FIXTURE ASSUMPTIONS (fixtures/ats_receiver/greenhouse_v2.py, modes gh2_phone_country and
# gh2_loc_search): neither structure has been seen working on a real page. Each is recognised
# only exactly as described; anything else stays a checkpoint (unlisted, or unsupported).

# How the country picker beside the phone field may be labelled (normalised, exact).
PHONE_COUNTRY_LABELS = frozenset({"country", "country code", "phone country",
                                  "country calling code"})  # fmt: skip
# An option names a country and its calling code, e.g. "Canada (+1)". A code is never taken
# to identify a country on its own: several options may share it.
_CALLING_OPTION = re.compile(r"^(?P<name>\S.*?)\s*\(\+(?P<code>\d{1,4})\)$")
LOCATION_STRUCTURED_REASON = (
    "hidden value set by the page's own location search when a suggestion is chosen; never "
    "written by NoEfforts"
)


def option_calling_code(label: str) -> str | None:
    """The calling code an option label states ("Canada (+1)" -> "1"), or None."""
    m = _CALLING_OPTION.match(" ".join((label or "").split()))
    return m.group("code") if m else None


def listbox_options(html: str, listbox_id: str | None) -> list[tuple[str | None, str]] | None:
    """(data-value, text) of each role=option inside the one role=listbox with this id in the
    static page, or None when there is not exactly one such listbox."""
    if not listbox_id:
        return None
    b = _TreeBuilder()
    b.feed(html)
    boxes = [n for n in b.root.walk()
             if isinstance(n, _Node) and n.attrs.get("id") == listbox_id]  # fmt: skip
    if len(boxes) != 1 or boxes[0].attrs.get("role") != "listbox":
        return None
    return [(n.attrs.get("data-value"), " ".join(n.all_text().split()))
            for n in boxes[0].walk() if n.attrs.get("role") == "option"]  # fmt: skip


def phone_country_control(fields: list[FormField], controls: list[Control],
                          cid: str | None = None) -> Control | None:  # fmt: skip
    """The country picker beside the phone field, only in this structure: the job data has one
    phone question, its control sits in a group named exactly as that question, and the group
    holds exactly one other control: a visible combobox in the form, labelled as a country (code)
    picker, whose option list is in the page (`aria-controls` -> role=listbox). `cid`: it must be
    this control (re-proven on the live page)."""
    tel = [f for f in fields if f.type == FieldType.tel]
    if len(tel) != 1:
        return None
    phone = [c for c in controls if c.id == tel[0].key.removesuffix("[]")]
    if len(phone) != 1 or phone[0].group_key is None:
        return None
    p = phone[0]
    if _norm(p.group_name) != _norm(tel[0].label):
        return None
    members = [c for c in controls if c.group_key == p.group_key and c is not p]
    if len(members) != 1:
        return None
    c = members[0]
    ok = (
        (cid is None or c.id == cid)
        and c.role == "combobox"
        and c.tag == "input"
        and c.controls_listbox
        and c.in_form
        and not c.hidden
        and _norm(c.accessible_name) in PHONE_COUNTRY_LABELS
    )
    return c if ok else None


def phone_country_field(fields: list[FormField], controls: list[Control], html: str,
                        taken: set[str]) -> FormField | None:  # fmt: skip
    """The phone country picker as a question of its own (`widget="phone_country"`), with the
    options read from the page: at least two, each with its own value and label, and every label
    stating a calling code. Otherwise None, and the control stays an unlisted checkpoint."""
    c = phone_country_control(fields, controls)
    if c is None or c.id in taken or not re.fullmatch(KEY_PATTERN, c.id):
        return None
    opts = listbox_options(html, c.controls)
    if not opts or len(opts) < 2:
        return None
    values, labels = [v for v, _ in opts], [_norm(t) for _, t in opts]
    if not all(values) or len(set(values)) != len(values) or len(set(labels)) != len(labels):
        return None
    if any(option_calling_code(t) is None for _, t in opts) or not (c.accessible_name or ""):
        return None
    return FormField(
        key=c.id,
        label=c.accessible_name[:2000],
        type=FieldType.select,
        required=True,  # it is always answered: by a unique calling code, or by you
        options=[Option(value=str(v)[:500], label=t[:500]) for v, t in opts],
        widget="phone_country",
    )


def location_candidates(api: dict) -> tuple[str, list[str]] | None:
    """From the job data: its one text location question and the hidden values beside it."""
    found = [(fl.get("name"), fl.get("type")) for q in api.get("location_questions") or []
             for fl in q.get("fields") or []]  # fmt: skip
    text = [n for n, t in found if t == "input_text"]
    hidden = [n for n, t in found if t == "input_hidden"]
    return (text[0], hidden) if len(text) == 1 and hidden else None


def location_picker(fields: list[FormField], controls: list[Control], text_key: str,
                    structured: list[str]) -> bool:  # fmt: skip
    """True only for this structure: the question `text_key` is one visible combobox in the form
    whose list is in the page, labelled exactly as the question, inside a group named exactly as
    the question; each hidden value in `structured` is one hidden input in that same group; and
    the group holds nothing else. The page's own script is what sets those hidden values."""
    f = next((x for x in fields if x.key == text_key), None)
    by: dict[str, list[Control]] = {}
    for c in controls:
        by.setdefault(c.id, []).append(c)
    pick = by.get(text_key, [])
    if f is None or not structured or len(pick) != 1:
        return False
    c = pick[0]
    if not (
        c.role == "combobox"
        and c.tag == "input"
        and c.controls_listbox
        and c.in_form
        and not c.hidden
        and c.group_key is not None
        and _norm(c.accessible_name) == _norm(f.label)
        and _norm(c.group_name) == _norm(f.label)
    ):
        return False
    for k in structured:
        h = by.get(k, [])
        if len(h) != 1 or (h[0].tag, h[0].type, h[0].group_key) != ("input", "hidden",
                                                                      c.group_key):  # fmt: skip
            return False
    return sum(1 for x in controls if x.group_key == c.group_key) == 1 + len(structured)


# How a page marks a control as required, kept apart (any of them may be used, or none): the
# HTML attribute, the ARIA attribute, ARIA on the enclosing group, and a trailing "*" on the
# control's own label or on its group's label. Read from the live page (labels can be built
# by scripts). The job data's own requirement is never lowered by any of these.
REQUIRED_SIGNALS_JS = """(id) => {
  const el = document.getElementById(id);
  if (!el) return null;
  const grp = el.closest('fieldset, [role=group], [role=radiogroup]');
  const refs = (n) => ((n && n.getAttribute('aria-labelledby')) || '').split(/\\s+/)
    .filter(Boolean).map((i) => document.getElementById(i)).filter(Boolean);
  const own = refs(el).concat(Array.from(document.querySelectorAll('label'))
    .filter((l) => l.htmlFor === id || l.contains(el)));
  const glab = grp ? refs(grp).concat(Array.from(grp.children)
    .filter((c) => c.tagName === 'LEGEND')) : [];
  const star = (ls) => ls.some((l) => /\\*\\s*$/.test((l.textContent || '').trim()));
  return {html: el.required === true, aria: el.getAttribute('aria-required') === 'true',
          group_aria: !!(grp && grp.getAttribute('aria-required') === 'true'),
          label_marker: star(own), group_label_marker: star(glab)};
}"""


def page_marks_required(signals: dict | None) -> bool | None:
    """Any required signal at all (None: the control could not be read)."""
    return None if signals is None else any(signals.values())


def required_evidence(api_required: bool, signals: dict | None) -> str:
    """How the page's marking relates to the job data's requirement (for review, never to
    change it): consistent, api_required_page_unmarked (still required), page_required_api_
    optional (needs an answer to be safe), or not_observable."""
    page = page_marks_required(signals)
    if page is None:
        return "not_observable"
    if api_required == page:
        return "consistent"
    return "api_required_page_unmarked" if api_required else "page_required_api_optional"


def build_schema(api: dict, page_html: str, *, stand_ins: bool = False
                 ) -> tuple[FormSchema, list[FieldMapping]]:  # fmt: skip
    """Job-post fields, verified against the page's controls. Raises gh.SchemaMismatch unless
    every field is mapped (or is a page-managed hidden value). `stand_ins` (D104): the page is a
    local stand-in (a fixture origin), the only place the phone country picker and the location
    search are recognised; on any other page they stay checkpoints."""
    from_api = gh.schema_from_api(api)
    controls = snapshot(page_html)
    mappings = map_fields(from_api.fields, controls)
    bad = [m for m in mappings if m.status not in ACCEPTED]
    if bad:
        statuses = sorted({m.status for m in bad})  # fixed mapping statuses, never field keys
        raise gh.SchemaMismatch(
            f"page controls do not match the job data ({len(bad)} field(s): {', '.join(statuses)})",
            "controls_do_not_match",
        )
    form = _form_attrs(page_html)
    loc = location_candidates(api) if stand_ins else None
    if loc and not location_picker(from_api.fields, controls, *loc):
        loc = None
    fields = []
    for f, m in zip(from_api.fields, mappings, strict=True):
        if m.status == "search_picker" and loc and f.key == loc[0] and f.type == FieldType.text:
            # D104: asked through the page's own search; the text is typed only after the
            # disclosure gate, and only a suggestion that is exactly it is chosen.
            f = f.model_copy(update={"widget": "location_search"})
        elif loc and f.key in loc[1] and f.type == FieldType.unsupported:
            f = f.model_copy(update={"widget": "location_structured",
                                     "unsupported_reason": LOCATION_STRUCTURED_REASON})  # fmt: skip
        elif m.status == "search_picker":
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
    taken = {f.key for f in fields}
    phone = phone_country_field(from_api.fields, controls, page_html, taken) if stand_ins else None
    if phone is not None:  # D104: right after the phone question, so it is filled after it
        at = next(i for i, f in enumerate(fields) if f.type == FieldType.tel)
        fields.insert(at + 1, phone)
        taken.add(phone.key)
    unlisted = [c for c in unlisted_controls(from_api.fields, controls)
                if phone is None or c.id != phone.key]  # fmt: skip
    for n, c in enumerate(unlisted, 1):
        valid = bool(c.id) and re.fullmatch(KEY_PATTERN, c.id) and c.id not in taken
        key = c.id if valid else f"page_control_{n}"
        taken.add(key)
        fields.append(
            FormField(
                key=key,
                label=(c.accessible_name or "")[:2000] or "Unlabelled page control",
                type=FieldType.unsupported,
                required=True,
                unsupported_reason=UNLISTED_REASON,
            )  # fmt: skip
        )
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
