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

import html
import re
from dataclasses import asdict, dataclass, field

from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import (
    KEY_PATTERN,
    TEXT_TYPES,
    UNKNOWN_TRIGGER,
    Condition,
    ExtractionError,
    FieldType,
    FormField,
    FormSchema,
    Option,
    SectionOptionSpec,
    SectionSpec,
    _Node,
    _TreeBuilder,
    question_limit,
)

# v2: a visible page control the job data does not list becomes a blocking field at capture
# (see `unlisted_controls`), so the route is a checkpoint before anything can be approved.
# v3 (D104): on local stand-ins only (`build_schema(stand_ins=True)`), two structures are
# recognised instead of refused: the country picker beside the phone field
# (`phone_country_field`) and a location search picker whose own script sets the job data's
# hidden values (`location_picker`). Anywhere else they stay checkpoints, as in v2.
# v4 (D130, on main): when the job data asks the phone as optional and the page's phone group
# holds exactly one other control, unrequired (`phone_companion`), the phone is left blank and
# that control is never touched, instead of both being refused.
# v5 (D120 integrated after D130): the extractor also recognises structured Education/Employment
# sections and the adapter fills them. D120's own branch had called this v4 too, so the combined
# build takes a version neither carried: v3 (main before D130) and v4 (main with D130; D120's
# branch) each meant a different behaviour.
# The version rides in `policy.ADAPTER_VERSIONS` for greenhouse_dom and greenhouse_live (the
# adapter_version `check_binding` enforces at queueing, before any page action, and at the
# disclosure and send gates), NOT in the hashed package content: no content hash changes; only
# existing greenhouse_dom/greenhouse_live approvals are retired and must be given again. A worker
# built before this -- one that would skip a section or not re-prove the phone's control -- can
# never claim a package approved under it.
# v6 (D141): the adapter fills a section combobox without typing, from its own list only, checks
# the frozen option id and reads back a react-select-style choice from its single value, and reads
# every section control back before the send gate. A v5 worker would type into it and read back
# its input, which a react-select page leaves empty, so it can never claim a package approved
# under v6.
# D161 (no new version): a typed question's length limit, as its page shows it, is recorded
# (`control_limit`) and the adapter holds each typed answer to the limit its control has now.
# Both only stop more: a v6 worker types an answer that fits whole, and one cut by the page is
# stopped by its readback, as before; an approval given before means what it meant.
EXTRACTION_VERSION = "greenhouse-dom-v6"
# D136: what the DOM adapter (execution/adapters/greenhouse_dom.py) fills, by field type; a choice
# only as an ARIA combobox. Anything else is decided here, at capture, never after an approval:
# a required one is a checkpoint (apply on the employer's site), an optional one stays blank.
DOM_FILLABLE = frozenset({"text", "email", "tel", "url", "textarea", "number", "select", "file"})
NATIVE_DROPDOWN_REASON = "native dropdown (not supported yet)"
_UNFILLABLE_REASONS = {
    FieldType.checkbox: "a checkbox (not supported yet)",
    FieldType.checkbox_group: "a list of several choices (not supported yet)",
    FieldType.multiselect: "a list of several choices (not supported yet)",
    FieldType.radio: "a set of options (not supported yet)",
    FieldType.date: "a date (not supported yet)",
}


def unfillable(f: FormField, c: "Control") -> str | None:
    """D136: why the DOM adapter would refuse to fill `f` on control `c`, or None."""
    if f.type == FieldType.select and c.role != "combobox":
        return NATIVE_DROPDOWN_REASON
    if f.type.value not in DOM_FILLABLE and f.type != FieldType.unsupported:
        return _UNFILLABLE_REASONS.get(
            f.type, "a control NoEfforts cannot fill (not supported yet)"
        )
    return None


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
    group_required: bool = False  # D130: aria-required="true" on the enclosing group
    # D161: its `maxlength` attribute as the browser keeps it (the first of two), and whether
    # the browser holds what is typed into it to that limit (`limits_typing`). A locked control is
    # read the same (the page's script may unlock it before anything is typed: a box read-only
    # until it has focus, a question disabled until shown), except one the page as served both
    # locks and fills itself (`_page_filled`: D129's identity field, never typed).
    maxlength: str | None = None
    limited: bool = False


# D161: the input types whose `maxlength` limits what is typed (a text area's does too); on any
# other (a number, a date, a file) the browser ignores it. A `type` the browser does not know,
# or none, is a text input.
LIMITED_INPUTS = frozenset({"text", "search", "url", "tel", "email", "password"})
_INPUT_TYPES = LIMITED_INPUTS | {
    "hidden", "date", "month", "week", "time", "datetime-local", "number", "range", "color",
    "checkbox", "radio", "file", "submit", "image", "reset", "button",
}  # fmt: skip
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


# D161: a control's length limit now, read in the page (the adapter, before anything is entered and
# before each value is typed; the read-only survey): its limit as the browser reads it
# (`maxLength`, -1 for none), whatever set it (the page's markup or its script); its `maxlength`
# attribute as written (the first of two, which the browser keeps), which is what a read of the
# form records (`question_limit`); and whether the browser holds what is typed into it to a limit
# at all (`limits_typing`; `type` read as the browser normalises it).
# Read through the browser's own definitions, as D160's reads of the form: a page that redefines
# `maxLength`, `getAttribute` or `type` on the element itself cannot change what is read.
LIVE_LIMIT_JS = """(e) => {
  const get = (P, k) => Object.getOwnPropertyDescriptor(P, k).get.call(e);
  const tag = Object.getOwnPropertyDescriptor(Element.prototype, 'localName').get.call(e);
  const P = tag === 'textarea' ? HTMLTextAreaElement.prototype
    : tag === 'input' ? HTMLInputElement.prototype : null;
  if (P === null) return [-1, null, false];
  const written = Element.prototype.getAttribute.call(e, 'maxlength');
  const applies = tag === 'textarea'
    || %s.includes(get(HTMLInputElement.prototype, 'type'));
  return [get(P, 'maxLength'), written, applies];
}""" % ("[" + ", ".join(f"'{t}'" for t in sorted(LIMITED_INPUTS)) + "]")


def limits_typing(tag: str, type_attr: str | None) -> bool:
    """D161: whether the browser holds what is typed into this control to its `maxlength`: a text
    area, or an input whose `type` (the first of two, matched ASCII case-insensitively, as the
    browser reads it) is a text type, or one the browser does not know."""
    if tag == "textarea":
        return True
    if tag != "input":
        return False
    t = (type_attr or "").translate(_ASCII_LOWER)
    return (t if t in _INPUT_TYPES else "text") in LIMITED_INPUTS


def _locked(n: _Node) -> bool:
    """D161: a control nothing can be typed into, as the browser reads the page: `disabled` or
    `readonly` on it, `inert` on it or around it, or a disabled fieldset around it (outside that
    fieldset's first legend)."""
    if "disabled" in n.attrs or "readonly" in n.attrs or "inert" in n.attrs:
        return True
    up = list(n.ancestors())
    for a in up:
        if "inert" in a.attrs:
            return True
        if a.tag == "fieldset" and "disabled" in a.attrs:
            legend = next((c for c in a.children if isinstance(c, _Node) and c.tag == "legend"),
                          None)  # fmt: skip
            if legend is None or legend not in up:
                return True
    return False


def _page_filled(n: _Node) -> bool:
    """D161 review: a control the page as served locks and fills itself (an input's `value`, the
    first of two; a text area's text), as D129's pre-filled identity field: nothing is typed
    into it, so its limit holds no answer of yours."""
    filled = n.all_text() if n.tag == "textarea" else n.twice.get("value", n.attrs.get("value"))
    return bool(filled) and _locked(n)


def control_limit(f: FormField, c: "Control | None") -> int | None:
    """D161: the length limit a typed question's page shows on its control, read as the browser
    reads it (`forms.question_limit`, D158), where the browser applies it to what is typed; None
    otherwise (no limit, one written so that no read records it, or a control it limits nothing
    on). Recorded as the question's `max_length`, which your answer is held to before you approve
    (D158) and which the form's version holds (D159)."""
    if c is None or f.type not in TEXT_TYPES or not c.limited:
        return None
    return question_limit(c.maxlength)


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
                group_required=grp is not None and grp.attrs.get("aria-required") == "true",
                maxlength=n.twice.get("maxlength", n.attrs.get("maxlength")),  # D161
                limited=limits_typing(n.tag, n.twice.get("type", n.attrs.get("type")))
                and not _page_filled(n),
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


# -- D111: a search input the page keeps hidden inside one question's group ------------------
# Observed on a real page (read-only run #11, `u2`): a `search` input with the combobox role,
# no hidden attribute but not visible, no required signal of any kind, inside the group of a
# control that a job-data question maps to. What it is for is not known and never inferred
# (not from its position, its label or what else is in the group). What is established is
# narrower: the applicant is not shown it, the page does not require it, and nothing is in it.
# So it is not treated as an unanswered question, and NoEfforts never touches it, but only
# while the live page shows exactly that: anything else stops the attempt before anything is
# entered (and again before submitting, after filling). Any other unlisted control, a
# standalone hidden search input included, stays a blocking checkpoint.
HIDDEN_SEARCH_LABEL = "Search box inside another question's group (hidden by the page)"
HIDDEN_SEARCH_REASON = (
    "not a question while the page keeps it hidden, unrequired and empty; never filled; "
    "the attempt stops if the page shows it, requires it or puts a value in it"
)
HIDDEN_SEARCH_CHANGED = "a hidden search box is shown, required or holds a value"


def group_owner(fields: list[FormField], controls: list[Control], c: Control) -> Control | None:
    """The one control in `c`'s group that a job-data question maps to, else None (no group,
    none, or several). Unsupported fields (page-managed values, NoEfforts' own) do not count."""
    if c.group_key is None:
        return None
    asked = [f for f in fields if f.type != FieldType.unsupported]
    owners = [m.control for m in map_fields(asked, controls)
              if m.status in ("mapped", "mapped_via_group") and m.control is not c
              and m.control.group_key == c.group_key]  # fmt: skip
    return owners[0] if len(owners) == 1 else None


def hidden_search_shape(fields: list[FormField], controls: list[Control], c: Control) -> bool:
    """The markup half of the D111 rule: a search input with the combobox role, in the form, no
    required attribute, in a group with exactly one job-data control. Whether the page hides
    it, requires it or fills it is read only from the live page (`hidden_search_state`)."""
    return (c.tag == "input" and c.type == "search" and c.role == "combobox" and c.in_form
            and not c.required and group_owner(fields, controls, c) is not None)  # fmt: skip


def hidden_search_candidates(fields: list[FormField], controls: list[Control]) -> list[Control]:
    """Unlisted controls with the D111 shape (see `hidden_search_shape`)."""
    return [c for c in unlisted_controls(fields, controls)
            if hidden_search_shape(fields, controls, c)]  # fmt: skip


# What the live page shows for one control and its group's job-data control: visibility as
# Playwright and the read-only check judge it (rendered box, not visibility:hidden), the
# value, and the required signals (REQUIRED_SIGNALS_JS).
HIDDEN_SEARCH_STATE_JS = (
    """([id, owner]) => {
  const el = document.getElementById(id), own = document.getElementById(owner);
  if (!el || !own) return null;
  const shown = (n) => {
    const s = getComputedStyle(n), r = n.getBoundingClientRect();
    return s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const signals = ("""
    + REQUIRED_SIGNALS_JS
    + """)(id);
  return {shown: shown(el), owner_shown: shown(own), value: el.value, signals};
}"""
)


def hidden_search_ok(state: dict | None) -> bool:
    """True only when the live page hides the control, requires nothing in it, holds nothing
    in it, and shows the question whose group it is in."""
    return (
        isinstance(state, dict)
        and state.get("shown") is False
        and state.get("owner_shown") is True
        and state.get("value") == ""
        and page_marks_required(state.get("signals")) is False
    )


# -- D130: the optional phone question's own second control ----------------------------------
# From the owner-supplied markup of one real form: beside an optional phone (`type=tel`,
# `aria-required="false"`), a library combobox -- an editable input with opacity 0 behind a
# visible control that shows the page's own default, no `aria-required`, options only once
# opened -- and, from read-only run #11 (another posting), such a combobox inside the group the
# page names as the phone question. Its label, its options and how a choice is shown and read
# back were never observed, so NoEfforts never sets it. What is established is narrower: by the
# page's own grouping it is part of the phone question, and the page does not require it. A
# number entered without it might not reach the employer as approved, so when the job data asks
# the phone as OPTIONAL, the phone is left blank (`phone_left_blank`) and the control is never
# touched (`phone_companion`). The live page must show the same structure, require neither, and
# hold no number in the phone -- before anything is entered and again before submitting --
# otherwise the attempt stops. A required phone, a control the page requires, a second such
# control, or one outside the group stays a blocking checkpoint. An input's opacity never makes
# it hidden (`snapshot`): this rule is about the phone question, not about how a control looks.
PHONE_COMPANION_LABEL = "Second control of the phone question (left as the page shows it)"
PHONE_COMPANION_REASON = (
    "inside the optional phone question's group and not required by the page; the phone is "
    "left blank, so it is never touched; the attempt stops if the page requires either or the "
    "phone holds a number"
)
PHONE_COMPANION_CHANGED = (
    "the phone question's second control is not as approved or is required, or the phone "
    "holds a number"
)


def _starred(s: str | None) -> bool:
    """A trailing "*" (a label's required marker, which `_norm` removes)."""
    return (s or "").strip().endswith("*")


def phone_companion(fields: list[FormField], controls: list[Control]) -> Control | None:
    """The one control the D130 rule recognises, from markup only (capture reads the page
    without its scripts; the adapter adds the live checks), else None:
    - the job data asks exactly one phone (tel) question, and it is optional;
    - its control is the only one with that id, not hidden, with no required attribute and no
      "*" on its own label or its group's name, in a group the page names exactly as the
      question and does not mark required;
    - apart from the phone, that group holds exactly one control that is neither hidden (hidden
      controls are never questions, as in `unlisted_controls`) nor of the D111 hidden-search
      shape: an input with the combobox role, in the form, the only control with its id, with no
      required attribute and no "*" on its label.
    What that control asks is never inferred (its label is not read for meaning): it belongs to
    the phone question by the page's own grouping, and only a number in the phone would make it
    matter -- which NoEfforts then never enters."""
    tel = [f for f in fields if f.type == FieldType.tel]
    if len(tel) != 1 or tel[0].required:
        return None
    phone = [c for c in controls if c.id == tel[0].key.removesuffix("[]")]
    if len(phone) != 1:
        return None
    p = phone[0]
    if (
        p.group_key is None
        or p.hidden
        or p.required
        or p.group_required
        or _starred(p.accessible_name)
        or _starred(p.group_name)
        or _norm(p.group_name) != _norm(tel[0].label)
    ):
        return None
    others = [c for c in controls if c.group_key == p.group_key and c is not p and not c.hidden
              and not hidden_search_shape(fields, controls, c)]  # fmt: skip
    if len(others) != 1:
        return None
    c = others[0]
    ok = (
        c.tag == "input"
        and c.role == "combobox"
        and c.in_form
        and not c.hidden
        and not c.required
        and not _starred(c.accessible_name)
        and sum(x.id == c.id for x in controls) == 1
    )
    return c if ok else None


# What the live page shows for the phone and its second control: the number in the phone, and
# each one's required signals (REQUIRED_SIGNALS_JS: attribute, ARIA, group, label markers).
PHONE_COMPANION_STATE_JS = (
    """([id, phone]) => {
  const el = document.getElementById(id), ph = document.getElementById(phone);
  if (!el || !ph) return null;
  const signals = ("""
    + REQUIRED_SIGNALS_JS
    + """);
  return {value: ph.value, signals: signals(id), phone_signals: signals(phone)};
}"""
)


def phone_companion_ok(state: dict | None) -> bool:
    """True only when the live page requires neither the phone nor its second control, by any
    signal, and holds no number in the phone."""
    return (
        isinstance(state, dict)
        and state.get("value") == ""
        and page_marks_required(state.get("signals")) is False
        and page_marks_required(state.get("phone_signals")) is False
    )


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


_SECTION_OPTION_RE = re.compile(
    r'<li[^>]*role="option"[^>]*data-value="([^"]+)"[^>]*>(.*?)</li>', re.S
)


def _section_options(page_html: str, control_id: str) -> list[SectionOptionSpec]:
    m = re.search(rf'<ul id="{re.escape(control_id)}-listbox"[^>]*>(.*?)</ul>', page_html, re.S)
    if not m:
        return []
    out = []
    for value, text in _SECTION_OPTION_RE.findall(m.group(1)):
        label = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
        if label:
            out.append(SectionOptionSpec(id=value, text=label))
    return out


def detect_sections(page_html: str) -> list[SectionSpec]:
    """D120 (stand-ins only): recognise a structured education/employment section rendered in the
    legacy-evidence shape -- per-row ids ``school--0`` / ``company-name-0`` and option lists as
    ``<li role=option data-value=ID>``. The real hosted structure is unobserved; this reads the
    synthetic stand-in's own structure (container ids education-section / employment-section)."""
    sections: list[SectionSpec] = []
    if 'id="school--0"' in page_html:
        sections.append(
            SectionSpec(
                kind="education",
                root="#education-section",
                schools=_section_options(page_html, "school--0"),
                degrees=_section_options(page_html, "degree--0"),
                disciplines=_section_options(page_html, "discipline--0"),
            )
        )
    if 'id="company-name-0"' in page_html:
        sections.append(SectionSpec(kind="employment", root="#employment-section"))
    return sections


_EDU_CTL_RE = re.compile(
    r"^(school|degree|discipline|start-month|start-year|end-month|end-year)--\d+$"
)
_EMP_CTL_RE = re.compile(
    r"^(company-name|title|start-date-month|start-date-year|current-role|"
    r"end-date-month|end-date-year)-\d+$"
)


def _section_control_id(cid: str, kinds: set) -> bool:
    """True when cid is a per-row control of a detected section, so capture represents it inside the
    section rather than as an unlisted unsupported question."""
    return bool(
        ("education" in kinds and _EDU_CTL_RE.match(cid))
        or ("employment" in kinds and _EMP_CTL_RE.match(cid))
    )


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
        elif m.status == "mapped" and (reason := unfillable(f, m.control)) is not None:
            # D136: refused at capture, not after you approved it (the adapter would stop there).
            f = f.model_copy(
                update={"type": FieldType.unsupported, "unsupported_reason": reason, "options": []}
            )
        elif m.hidden_at_load and f.type != FieldType.unsupported:
            # Shown by page logic we cannot see: its condition is unknown, never a guess.
            f = f.model_copy(update={"condition": Condition(key=UNKNOWN_TRIGGER, any_of=["?"])})
        page_limit = control_limit(f, m.control) if m.status == "mapped" else None
        if page_limit is not None:
            # D161: the limit its page shows, read as the browser reads it (the job data states
            # none): your answer is held to it before you approve (D158), as its form sends it.
            f = f.model_copy(update={"max_length": min(page_limit, f.max_length or page_limit)})
        fields.append(f)
    taken = {f.key for f in fields}
    phone = phone_country_field(from_api.fields, controls, page_html, taken) if stand_ins else None
    if phone is not None:  # D104: right after the phone question, so it is filled after it
        at = next(i for i, f in enumerate(fields) if f.type == FieldType.tel)
        fields.insert(at + 1, phone)
        taken.add(phone.key)
    # D130: the optional phone's second control (never beside a recognised stand-in picker).
    companion = phone_companion(from_api.fields, controls) if phone is None else None
    if companion is not None and (
        companion.id in taken or not re.fullmatch(KEY_PATTERN, companion.id)
    ):
        companion = None
    if companion is not None:  # the phone is then left blank (resolver: `phone_left_blank`)
        fields = [f.model_copy(update={"widget": "phone_left_blank"})
                  if f.type == FieldType.tel else f for f in fields]  # fmt: skip
    sections = detect_sections(page_html) if stand_ins else []  # D120
    section_kinds = {s.kind for s in sections}
    unlisted = [
        c
        for c in unlisted_controls(from_api.fields, controls)
        if (phone is None or c.id != phone.key) and not _section_control_id(c.id, section_kinds)
    ]
    hidden_search = {c.id for c in hidden_search_candidates(from_api.fields, controls)}
    for n, c in enumerate(unlisted, 1):
        valid = bool(c.id) and re.fullmatch(KEY_PATTERN, c.id) and c.id not in taken
        key = c.id if valid else f"page_control_{n}"
        taken.add(key)
        if valid and c.id in hidden_search:
            # D111: not an unanswered question, on condition that the live page hides it,
            # requires nothing in it and holds nothing in it (re-proven by the adapter).
            fields.append(
                FormField(
                    key=key,
                    label=HIDDEN_SEARCH_LABEL,
                    type=FieldType.unsupported,
                    required=False,
                    unsupported_reason=HIDDEN_SEARCH_REASON,
                    widget="hidden_search",
                )  # fmt: skip
            )
            continue
        if valid and companion is not None and c.id == companion.id:
            # D130: part of the optional phone question, which is left blank; never touched,
            # and re-proven on the live page by the adapter.
            fields.append(
                FormField(
                    key=key,
                    label=PHONE_COMPANION_LABEL,
                    type=FieldType.unsupported,
                    required=False,
                    unsupported_reason=PHONE_COMPANION_REASON,
                    widget="phone_companion",
                )
            )
            continue
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
            action=form.get("data-submit-path") or form.get("action"),
            method="post" if (form.get("data-submit-path") or form.get("action")) else None,
            fields=fields,
            sections=sections,
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
