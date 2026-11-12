"""D120 execution side: a DOM fill plan for Greenhouse's structured Education and Employment
repeating sections.

Resolution (approved records -> per-row field values, checkpoint-first, no inference) lives in
``app.modules.preparation.structured_sections``. This module turns a resolved, *ready*
``SectionResult`` into an ordered, read-back-checked plan of browser actions. A separate thin
executor (added together with the fixture that proves it) applies the plan with Playwright.

The control-id and row mechanics are REUSED from the owner's own legacy bot
(``autojob-greenhouse/src/apply.py`` -- ``_fill_work_history`` / ``_click_add_another``, lines
~1066-1116; CONFIRMED in that code). That is HISTORICAL evidence recorded by the legacy author
(dated 2026-10), NOT a current real-page observation: the live hosted DOM has not been
re-observed. So every selector here is re-proven on the page by readback before anything is
trusted, and an id that is absent, or a value that does not read back, stops the section rather
than guessing.

The legacy degree inference (``_degree_label``: the first two letters of the degree string ->
"Master's Degree") is deliberately NOT reused. Degrees are resolved upstream only by
``structured_sections.match_degree`` (grounded in the option's own text, exact-or-none); schools
and disciplines by exact text only. This module never maps, guesses or infers a value: it only
enters what resolution already established, and reads it back.
"""

import re
from dataclasses import dataclass

from app.modules.preparation.structured_sections import FieldResult, RowResult, SectionResult


class Refused(Exception):
    """The section cannot be driven and stays a checkpoint (never guessed)."""


# The month combobox's option text convention (HISTORICAL/FIXTURE ASSUMPTION, re-proven by
# readback): the resolved numeric month is entered as its English month name. If the live
# combobox labels months any other way, readback fails and the section stops -- it is never
# forced through.
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def _month_name(month: object) -> str:
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise Refused(f"unusable month value {month!r}")
    return MONTHS[month - 1]


# field name -> (op kind, id template(s)). "{i}" is the 0-based row index. Education renders a
# double dash and employment a single dash, exactly as the legacy form did (module docstring).
_EDUCATION_FIELDS = (
    ("school_name_id", "combobox", "school--{i}"),
    ("degree_id", "combobox", "degree--{i}"),
    ("discipline_id", "combobox", "discipline--{i}"),
    ("start_date", "date", ("start-month--{i}", "start-year--{i}")),
    ("end_date", "date", ("end-month--{i}", "end-year--{i}")),
)
_EMPLOYMENT_FIELDS = (
    ("company_name", "text", "company-name-{i}"),
    ("title", "text", "title-{i}"),
    ("start_date", "date", ("start-date-month-{i}", "start-date-year-{i}")),
    ("current", "checkbox", "current-role-{i}"),
    ("end_date", "date", ("end-date-month-{i}", "end-date-year-{i}")),
)
_ANCHOR = {"education": "school--{i}", "employment": "company-name-{i}"}
_SPEC = {"education": _EDUCATION_FIELDS, "employment": _EMPLOYMENT_FIELDS}

# The only field names each section kind may carry. Anything else in frozen content is unknown and
# is refused rather than silently dropped -- we never trust a field we did not freeze.
_FIELD_NAMES = {kind: frozenset(f[0] for f in spec) for kind, spec in _SPEC.items()}

# A frozen section's DOM root is used live as a Playwright locator (the "Add another" click is
# scoped to it), so it must be the plain "#id" selector capture emits (#education-section /
# #employment-section) -- never an arbitrary CSS or XPath carried through package content.
_ROOT_RE = re.compile(r"^#[A-Za-z][\w-]*$")


def _valid_root(root: object) -> str:
    if not (isinstance(root, str) and _ROOT_RE.match(root)):
        raise Refused(f"unsafe or missing section root {root!r}")
    return root


@dataclass(frozen=True)
class FillOp:
    """One planned control interaction.

    ``readback`` is the exact text expected after the action (a combobox's shown value, a text
    input's value, a date part). For a checkbox it is None and the expected state is ``value``
    (a bool).
    """

    row: int
    field: str
    kind: str  # "combobox" | "text" | "checkbox" | "month" | "year"
    selector: str
    value: object
    readback: str | None
    # D141: a combobox's frozen option id (the captured `data-value`). The chosen option, and the
    # control after choosing, must carry it wherever the page exposes one. None for a month.
    option_id: str | None = None


@dataclass(frozen=True)
class RowPlan:
    row: int
    record_id: str
    anchor: str  # "#...": the control whose presence proves this row exists on the page
    add_another_first: bool  # row > 0: click a page "Add another" when the anchor is absent
    ops: tuple[FillOp, ...]
    # D141: the controls of an intentionally omitted field (a current role's end date): never
    # entered, and they must still be empty when read back.
    blank: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionPlan:
    kind: str  # "education" | "employment"
    rows: tuple[RowPlan, ...]


def _sel(template: str, i: int) -> str:
    return "#" + template.format(i=i)


def _ops_for_field(kind: str, template, field: str, fr, row: int) -> list[FillOp]:
    if kind in ("text", "combobox"):
        if not isinstance(fr.display, str) or not fr.display.strip():
            raise Refused(f"{field}: resolved value carries no display text")
        oid = None
        if kind == "combobox":
            oid = fr.value.get("id") if isinstance(fr.value, dict) else None
            if not isinstance(oid, str) or not oid:
                raise Refused(f"{field}: combobox value carries no option id")
        return [FillOp(row, field, kind, _sel(template, row), fr.display, fr.display, oid)]
    val = fr.value if isinstance(fr.value, dict) else None
    if kind == "checkbox":
        if val is None or not isinstance(val.get("bool"), bool):
            raise Refused(f"{field}: checkbox value is malformed")
        return [FillOp(row, field, "checkbox", _sel(template, row), val["bool"], None)]
    if kind == "date":
        if val is None:
            raise Refused(f"{field}: date value is malformed")
        month, year = val.get("month"), val.get("year")  # _month_name validates the month
        if not isinstance(year, int) or isinstance(year, bool):
            raise Refused(f"{field}: unusable year value {year!r}")
        month_tpl, year_tpl = template
        return [
            FillOp(row, field, "month", _sel(month_tpl, row), month, _month_name(month)),
            FillOp(row, field, "year", _sel(year_tpl, row), str(year), str(year)),
        ]
    raise Refused(f"unknown field kind {kind!r}")


def plan_section(section: SectionResult) -> SectionPlan:
    """Build a read-back-checked fill plan from a resolved section, or raise ``Refused`` so the
    caller keeps it a checkpoint.

    Only a ``ready()`` section (every field across every row resolved or intentionally omitted) is
    planned. Nothing here maps, fuzzy-matches or infers a value; it only sequences what resolution
    already established, with the exact text to read back for each control.
    """
    if not section.supported:
        raise Refused(section.reason or f"{section.kind} section is not supported")
    if section.kind not in _SPEC:
        raise Refused(f"unknown section kind {section.kind!r}")
    if not section.ready():
        raise Refused(f"{section.kind} section has unresolved fields; it stays a checkpoint")
    spec = _SPEC[section.kind]
    anchor_tpl = _ANCHOR[section.kind]
    rows: list[RowPlan] = []
    for i, row in enumerate(section.rows):
        ops: list[FillOp] = []
        blank: list[str] = []
        for field, kind, template in spec:
            fr = row.fields.get(field)
            if fr is None or fr.status == "omitted":
                templates = template if isinstance(template, tuple) else (template,)
                blank.extend(_sel(t, i) for t in templates)
                continue
            if fr.status != "resolved":  # ready() rules this out; refuse rather than risk a value
                raise Refused(f"{section.kind} field {field} is {fr.status}")
            ops.extend(_ops_for_field(kind, template, field, fr, i))
        rows.append(
            RowPlan(
                row=i,
                record_id=row.record_id,
                anchor=_sel(anchor_tpl, i),
                add_another_first=i > 0,
                ops=tuple(ops),
                blank=tuple(blank),
            )
        )
    return SectionPlan(kind=section.kind, rows=tuple(rows))


# -- package <-> plan bridge -----------------------------------------------------------------
#
# A resolved section is frozen into the package content (what the owner approves and the hash
# covers), then rebuilt at execution time and turned into a plan. Only the resolved values, the
# record order and the section's own DOM root travel in the package -- never the owner's source
# records. build_content emits `section_to_content`; the adapter fills from `plan_content_section`.


def section_to_content(section: SectionResult, *, root: str) -> dict:
    """Freeze a *ready* section into the package shape. An unready or unsupported section is a
    checkpoint and is never written into a package version (raise ``Refused``), so approval can
    never bind to a section with an unresolved field."""
    if not section.supported:
        raise Refused(section.reason or f"{section.kind} section is not supported")
    if section.kind not in _SPEC:
        raise Refused(f"unsupported section kind {section.kind!r}")
    if not section.ready():
        raise Refused(f"{section.kind} section has unresolved fields; it stays a checkpoint")
    return {
        "kind": section.kind,
        "root": _valid_root(root),
        "rows": [
            {
                "record_id": row.record_id,
                "fields": {
                    name: {"status": fr.status, "value": fr.value, "display": fr.display}
                    for name, fr in row.fields.items()
                },
            }
            for row in section.rows
        ],
    }


def section_root(data: object) -> str:
    """The validated container selector of a frozen section. The executor uses it live (Add-another
    scoping), so an arbitrary selector carried through package content is refused, never trusted."""
    if not isinstance(data, dict):
        raise Refused("section content is not an object")
    return _valid_root(data.get("root"))


def validate_content_section(data: object) -> None:
    """Reject a frozen section dict that could not have come from our own freeze, before it is
    rebuilt or planned. Guards the execution path against malformed package content: a non-object,
    an unknown section kind or field name (we never drive a control we did not freeze), a bad or
    missing ``#id`` root, a malformed row, or two rows sharing a record identity. Runs on every
    rebuild, so neither the fill nor the pre-disclosure re-check trusts section content blindly."""
    if not isinstance(data, dict):
        raise Refused("section content is not an object")
    kind = data.get("kind")
    if kind not in _SPEC:
        raise Refused(f"unsupported section kind {kind!r}")
    section_root(data)  # a frozen section always carries its validated #id root
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        raise Refused("section rows are not a list")
    allowed = _FIELD_NAMES[kind]
    seen: set[str] = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise Refused(f"section row {idx} is not an object")
        rid = row.get("record_id")
        if not (isinstance(rid, str) and rid):
            raise Refused(f"section row {idx} has no record identity")
        if rid in seen:
            raise Refused(f"duplicate section row identity {rid!r}")
        seen.add(rid)
        fields = row.get("fields")
        if not isinstance(fields, dict):
            raise Refused(f"section row {idx} fields are not an object")
        for name, f in fields.items():
            if name not in allowed:
                raise Refused(f"unsupported {kind} field {name!r}")
            if not (isinstance(f, dict) and isinstance(f.get("status"), str)):
                raise Refused(f"malformed section field {name!r}")


def section_from_content(data: dict) -> SectionResult:
    """Rebuild a ``SectionResult`` from the frozen package shape (the inverse of
    ``section_to_content``). The content is validated first (``validate_content_section``) so a
    malformed or tampered section is refused, not driven. Only status/value/display are carried;
    nothing is re-resolved, so the plan reflects exactly what was approved, not current data."""
    validate_content_section(data)
    kind = data["kind"]
    rows = [
        RowResult(
            r["record_id"],
            kind,
            {
                name: FieldResult(name, f["status"], value=f.get("value"), display=f.get("display"))
                for name, f in r["fields"].items()
            },
        )
        for r in data.get("rows", [])
    ]
    return SectionResult(kind, rows)


def plan_content_section(data: dict) -> SectionPlan:
    """Plan directly from a package content section (rebuild then plan)."""
    return plan_section(section_from_content(data))


# -- browser executor ------------------------------------------------------------------------
#
# Applies a plan to a live page, reading back every control. The repeating-row and "Add another"
# mechanics mirror the legacy bot (module docstring); here each value is read back after entry, so
# a selector that has drifted since the legacy evidence fails loudly rather than silently entering
# the wrong thing. "Add another" is scoped to the section's own container, so a page carrying both
# an education and an employment section never clicks the other section's button. The executor
# only enters what the plan carries; detecting an *unexpected* required control is the adapter's
# job (it already compares the live page against the captured field set before disclosure).


class SectionFillError(Refused):
    """A control did not read back as planned, or a planned row would not appear: stop, never
    force a value onto a form that no longer matches what was approved."""


def _present(page, selector: str, wait_ms: int = 0) -> bool:
    loc = page.locator(selector)
    if wait_ms:
        try:
            loc.first.wait_for(state="attached", timeout=wait_ms)
        except Exception:  # noqa: BLE001
            return False
    return loc.count() > 0


def _click_add_another(page, section_root: str, timeout_ms: int) -> None:
    btn = page.locator(section_root).get_by_role("button", name=re.compile("add another", re.I))
    btn.first.click(timeout=timeout_ms)


def _fill_text(page, selector: str, value, readback, timeout_ms: int) -> None:
    loc = page.locator(selector).first
    loc.fill(str(value), timeout=timeout_ms)
    got = (loc.input_value() or "").strip()
    if got != (readback or ""):
        raise SectionFillError(f"{selector}: does not read back the approved value")


def _set_checkbox(page, selector: str, want: bool, timeout_ms: int) -> None:
    loc = page.locator(selector).first
    loc.set_checked(bool(want), timeout=timeout_ms)
    if loc.is_checked() != bool(want):
        raise SectionFillError(f"{selector}: checkbox did not take state {want}")


_COMBO_JS = """(sel) => {
  const cb = document.querySelector(sel);
  if (!cb) return null;
  const box = cb.closest('.select__control');
  return {
    react: !!box,
    single: box ? [...box.querySelectorAll('.select__single-value')]
      .map(e => e.textContent.trim()) : [],
    multi: box ? box.querySelectorAll('.select__multi-value').length : 0,
    input: (cb.value || '').trim(),
    id: cb.hasAttribute('data-value') ? cb.getAttribute('data-value') : null,
  };
}"""
_LIST_ID = re.compile(r"[A-Za-z][A-Za-z0-9_\-:.]*")


def combobox_shows(page, selector: str, want_text: str | None, want_id: str | None) -> bool:
    """D141 (as D109 does for a top-level dropdown): on a react-select-style control the choice is
    the one `select__single-value` shown, with no search text left and no chips; otherwise the
    input's own value. Where the control exposes the chosen option's id, it must be the frozen one.
    `want_text` None: the control must be empty."""
    got = page.evaluate(_COMBO_JS, selector)
    if got is None:
        return False
    if want_text is None:
        return got["input"] == "" and not got["single"] and not got["id"]
    if got["react"]:
        if got["multi"] or got["input"] or got["single"] != [want_text]:
            return False
    elif got["input"] != want_text:
        return False
    return want_id is None or got["id"] is None or got["id"] == want_id


def _own_list(page, loc):
    """The list a combobox names as its own right now (aria-controls / aria-owns), or None."""
    ac = loc.get_attribute("aria-controls") or loc.get_attribute("aria-owns") or ""
    return page.locator(f"[id='{ac}']") if _LIST_ID.fullmatch(ac) else None


def _close_list(page, loc) -> None:
    try:
        loc.press("Escape")
    except Exception:  # noqa: BLE001
        pass


def _select_combobox(page, selector: str, want_text: str, want_id: str | None,
                     timeout_ms: int) -> None:  # fmt: skip
    """Open a section combobox and choose the one option whose text is exactly ``want_text``.

    D141, following D108/D109: nothing is ever typed into it; it is opened by a click on the
    control, then (a react-select-style control) on its container; options are read only from the
    list the control names as its own (aria-controls / aria-owns) once it is open (a react-select
    control names none until then, D130), never from the rest of the page, and a control that
    names none when open is refused; exactly one option may read ``want_text`` and, where it
    exposes an id, that id must be the frozen one; the choice is then proven by readback
    (``combobox_shows``). No near match is ever accepted."""
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed(timeout=timeout_ms)
    loc.click(timeout=timeout_ms)
    listbox = _own_list(page, loc)
    if listbox is None or not listbox.first.is_visible():
        box = loc.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
                          "' select__control ')][1]")  # fmt: skip
        if box.count():
            box.first.click(timeout=timeout_ms)
            listbox = _own_list(page, loc)
    if listbox is None:
        _close_list(page, loc)
        raise SectionFillError(f"{selector}: names no list of its own")
    try:
        listbox.first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:  # noqa: BLE001
        raise SectionFillError(f"{selector}: its list did not open") from None
    opts = listbox.first.locator("[role=option]")
    hits = []
    for k in range(opts.count()):
        option = opts.nth(k)
        try:
            text = (option.inner_text() or "").strip()
        except Exception:  # noqa: BLE001
            text = ""
        if text == want_text:
            hits.append(option)
    if len(hits) != 1:
        _close_list(page, loc)
        raise SectionFillError(f"{selector}: {len(hits)} options read the approved text exactly")
    exposed = hits[0].get_attribute("data-value")
    if want_id is not None and exposed is not None and exposed != want_id:
        _close_list(page, loc)
        raise SectionFillError(f"{selector}: the approved option records another id")
    hits[0].click(timeout=timeout_ms)
    page.wait_for_timeout(50)
    if not combobox_shows(page, selector, want_text, want_id):
        raise SectionFillError(f"{selector}: does not show the approved option after choosing")


def _apply_op(page, op: FillOp, timeout_ms: int) -> None:
    if op.kind in ("text", "year"):
        _fill_text(page, op.selector, op.value, op.readback, timeout_ms)
    elif op.kind in ("combobox", "month"):
        _select_combobox(page, op.selector, op.readback, op.option_id, timeout_ms)
    elif op.kind == "checkbox":
        _set_checkbox(page, op.selector, bool(op.value), timeout_ms)
    else:
        raise SectionFillError(f"unknown op kind {op.kind!r}")


def apply_section_plan(
    page,
    plan: SectionPlan,
    section_root: str,
    *,
    timeout_ms: int = 3000,
    on_entered=None,
    before_op=None,
) -> list[dict]:
    """Fill a planned section on ``page``, reading back every control, and return a per-row/field
    record of what was entered (field names only -- never the applicant's values) for the attempt
    log. Raises ``SectionFillError`` (a ``Refused``) on any readback mismatch or a planned row that
    will not appear, so nothing is forced onto a form that no longer matches the approval.
    ``before_op`` (D150: the runner's check between fields) is called before each "Add another"
    and each control; what it raises passes through, with what was entered already reported."""
    entered: list[dict] = []
    try:
        for row in plan.rows:
            if row.add_another_first and not _present(page, row.anchor):
                if before_op is not None:
                    before_op()
                _click_add_another(page, section_root, timeout_ms)
                if not _present(page, row.anchor, wait_ms=timeout_ms):
                    raise SectionFillError(
                        f"{plan.kind} row {row.row}: {row.anchor} did not appear after Add another"
                    )
            for op in row.ops:
                if before_op is not None:
                    before_op()
                _apply_op(page, op, timeout_ms)
                entered.append({"row": row.row, "field": op.field})
                if on_entered is not None:  # D137: reported as soon as it is entered
                    on_entered(entered[-1])
    except SectionFillError as e:
        # Preserve what was already entered (disclosed on the form) so a mid-fill stop is never
        # reported as "nothing disclosed": the caller records these and abandons the attempt.
        e.entered = entered
        raise
    return entered


_MAX_EXTRA_ROWS = 20


def _op_holds(page, op: FillOp) -> bool:
    loc = page.locator(op.selector)
    if loc.count() != 1:
        return False
    if op.kind in ("combobox", "month"):
        return combobox_shows(page, op.selector, op.readback, op.option_id)
    if op.kind == "checkbox":
        return loc.first.is_checked() == bool(op.value)
    return (loc.first.input_value() or "").strip() == (op.readback or "")


def _empty(page, selector: str) -> bool:
    loc = page.locator(selector)
    if loc.count() == 0:
        return True
    if loc.count() != 1:
        return False
    if (loc.first.get_attribute("role") or "") == "combobox":
        return combobox_shows(page, selector, None, None)
    if (loc.first.get_attribute("type") or "") == "checkbox":
        return not loc.first.is_checked()
    return (loc.first.input_value() or "") == ""


def readback_section(page, plan: SectionPlan) -> list[str]:
    """D141: after filling, before the send gate, read back every control of a filled section:
    each planned control holds what was approved, each intentionally omitted one is still empty,
    and a row the page shows beyond the plan holds nothing. Returns what does not match, as
    "section:<kind>:<row>:<field or selector>" (never a value)."""
    bad: list[str] = []
    for row in plan.rows:
        for op in row.ops:
            if not _op_holds(page, op):
                bad.append(f"section:{plan.kind}:{row.row}:{op.field}")
        for sel in row.blank:
            if not _empty(page, sel):
                bad.append(f"section:{plan.kind}:{row.row}:{sel.lstrip('#')}")
    spec = _SPEC[plan.kind]
    for i in range(len(plan.rows), len(plan.rows) + _MAX_EXTRA_ROWS):
        if page.locator(_sel(_ANCHOR[plan.kind], i)).count() == 0:
            break
        for _field, _kind, template in spec:
            for t in template if isinstance(template, tuple) else (template,):
                if not _empty(page, _sel(t, i)):
                    bad.append(f"section:{plan.kind}:{i}:{t.format(i=i)}")
    return bad
