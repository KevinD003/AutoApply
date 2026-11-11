"""D149: the Workday-style stand-in's Work Experience entries (FIXTURE ASSUMPTION FA7 in
fixtures/ats_receiver/workday_like.py), entered from a frozen employment section and read back.

What an entry holds is resolved and frozen exactly as on Greenhouse (D120: your approved work
history, `structured_sections.resolve_employment_row`, frozen by
`greenhouse_sections.section_to_content`, shown on the review page and diffed by D140). Only the
page's controls differ, and they are the stand-in's own, never an observation of a real Workday
page: entry i's controls are named `work[i].<part>` inside the section, and an entry is added by
the section's one "Add" (then "Add Another") button.

  * Job Title and Company are typed as approved; From and To as MM/YYYY from the frozen month and
    year; "I currently work here" ticked or not as approved. A current role's To is never entered
    and must stay empty. Location and Role Description are never entered and must stay empty.
  * An entry is added only when its controls are not on the page yet, by one click of the
    section's own button; one that does not appear stops the attempt.
  * Each control is read back as it is entered; before the page's Next, every planned control
    must still hold what was approved, every one left empty must be empty, and the page must
    show no entry beyond the plan (an entry a parsed resume added, or an empty one): it would be
    sent unapproved, or refused by the page's own checks.
Nothing here maps, guesses or infers a value: it only enters what resolution established."""

import re

from app.modules.execution.adapters.greenhouse_sections import (
    FillOp,
    Refused,
    RowPlan,
    SectionFillError,
    SectionPlan,
    _empty,
    _fill_text,
    _present,
    _set_checkbox,
    section_from_content,
    section_root,
)

KIND = "employment"
# A frozen employment field -> how it is entered, and the part of the control's name.
_FIELDS = (
    ("title", "text", "title"),
    ("company_name", "text", "company"),
    ("start_date", "month_year", "from"),
    ("current", "checkbox", "current"),
    ("end_date", "month_year", "to"),
)
_NEVER_FILLED = ("location", "description")  # never entered; must stay empty
_ADD = re.compile(r"^\s*add(\s+another)?\s*$", re.IGNORECASE)
_ENTRY_NAME = re.compile(r"^work\[(\d+)\]\.")


def _control(root: str, i: int, part: str) -> str:
    return f'{root} [name="work[{i}].{part}"]'


def _op(i: int, field: str, kind: str, selector: str, fr) -> FillOp:
    if kind == "text":
        if not isinstance(fr.display, str) or not fr.display.strip():
            raise Refused(f"{field}: resolved value carries no display text")
        return FillOp(i, field, "text", selector, fr.display, fr.display)
    val = fr.value if isinstance(fr.value, dict) else {}
    if kind == "checkbox":
        if not isinstance(val.get("bool"), bool):
            raise Refused(f"{field}: checkbox value is malformed")
        return FillOp(i, field, "checkbox", selector, val["bool"], None)
    month, year = val.get("month"), val.get("year")
    if not (isinstance(month, int) and not isinstance(month, bool) and 1 <= month <= 12):
        raise Refused(f"{field}: unusable month value {month!r}")
    if not (isinstance(year, int) and not isinstance(year, bool) and 1000 <= year <= 9999):
        raise Refused(f"{field}: unusable year value {year!r}")
    text = f"{month:02d}/{year}"
    return FillOp(i, field, "text", selector, text, text)


def plan(data: object) -> SectionPlan:
    """The entries to make from a frozen section (validated first, as on Greenhouse), or Refused:
    an employment section only, every field resolved or intentionally omitted."""
    section = section_from_content(data)  # refuses malformed or unknown content
    if section.kind != KIND:
        raise Refused(f"a {section.kind} section is not entered on this form")
    if not section.ready():
        raise Refused("the section has unresolved fields; it stays a checkpoint")
    root = section_root(data)
    rows = []
    for i, row in enumerate(section.rows):
        ops: list[FillOp] = []
        blank = [_control(root, i, part) for part in _NEVER_FILLED]
        for field, kind, part in _FIELDS:
            fr = row.fields.get(field)
            selector = _control(root, i, part)
            if fr is None or fr.status == "omitted":
                blank.append(selector)
                continue
            if fr.status != "resolved":
                raise Refused(f"{KIND} field {field} is {fr.status}")
            ops.append(_op(i, field, kind, selector, fr))
        rows.append(
            RowPlan(
                row=i,
                record_id=row.record_id,
                anchor=_control(root, i, "title"),
                add_another_first=True,
                ops=tuple(ops),
                blank=tuple(blank),
            )
        )
    return SectionPlan(kind=KIND, rows=tuple(rows))


def _click_add(page, root: str, timeout_ms: int) -> None:
    buttons = page.locator(root).get_by_role("button", name=_ADD)
    if buttons.count() != 1:
        raise SectionFillError(f"{KIND}: the section has no single Add button")
    buttons.first.click(timeout=timeout_ms)


def apply(page, entries: SectionPlan, root: str, *, timeout_ms: int = 3000, on_entered=None,
          progress=None) -> list[dict]:  # fmt: skip
    """Enter every planned entry in order, each control read back as entered; return what was
    entered (row and field, never a value), reporting each one at once (`on_entered`, D137).
    SectionFillError (a Refused) when an entry will not appear or a control does not take its
    value: what was entered before is on the error (`entered`)."""
    entered: list[dict] = []
    try:
        for row in entries.rows:
            if progress is not None:
                progress()
            if not _present(page, row.anchor):
                _click_add(page, root, timeout_ms)
                if not _present(page, row.anchor, wait_ms=timeout_ms):
                    raise SectionFillError(f"{KIND} entry {row.row} did not appear after Add")
            for op in row.ops:
                if progress is not None:
                    progress()
                if op.kind == "checkbox":
                    _set_checkbox(page, op.selector, bool(op.value), timeout_ms)
                else:
                    _fill_text(page, op.selector, op.value, op.readback, timeout_ms)
                entered.append({"row": row.row, "field": op.field})
                if on_entered is not None:
                    on_entered(entered[-1])
    except SectionFillError as e:
        e.entered = entered
        raise
    return entered


def _holds(page, op: FillOp) -> bool:
    loc = page.locator(op.selector)
    if loc.count() != 1:
        return False
    if op.kind == "checkbox":
        return loc.first.is_checked() == bool(op.value)
    return (loc.first.input_value() or "").strip() == (op.readback or "")


_ENTRY_NAMES = """(root) => [...document.querySelectorAll(`${root} [name]`)].map(e => e.name)"""


def readback(page, entries: SectionPlan, root: str) -> list[str]:
    """Every planned control holds what was approved, every one left empty is empty, and the
    section shows no entry beyond the plan. What does not match, as "section:<kind>:<row>:<field
    or part>" (never a value)."""
    bad: list[str] = []
    for row in entries.rows:
        for op in row.ops:
            if not _holds(page, op):
                bad.append(f"section:{KIND}:{row.row}:{op.field}")
        for selector in row.blank:
            if not _empty(page, selector):
                part = selector.rsplit(".", 1)[-1].rstrip('"]')
                bad.append(f"section:{KIND}:{row.row}:{part}")
    names = page.evaluate(_ENTRY_NAMES, root) if page.locator(root).count() == 1 else []
    beyond = {int(m[1]) for n in names if (m := _ENTRY_NAME.match(n or ""))} - set(
        range(len(entries.rows))
    )
    bad.extend(f"section:{KIND}:{i}:entry" for i in sorted(beyond))
    if page.locator(root).count() != 1:
        bad.append(f"section:{KIND}:root")
    return bad
