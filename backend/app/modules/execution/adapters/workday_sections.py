"""D149: the Workday-style stand-in's Work Experience entries (FIXTURE ASSUMPTION FA7 in
fixtures/ats_receiver/workday_like.py), entered from a frozen employment section and read back.

What an entry holds is resolved and frozen exactly as on Greenhouse (D120: your approved work
history, `structured_sections.resolve_employment_row`, frozen by
`greenhouse_sections.section_to_content`, shown on the review page and diffed by D140). Only the
page's controls differ, and they are the stand-in's own, never an observation of a real Workday
page: entry i's controls are named `work[i].<part>` inside the section, and an entry is added by
the section's one button, "Add" (then "Add Another"), found by its text as capture reads it.

  * Job Title and Company are typed exactly as approved (one that holds a line break, which a
    text box cannot, is refused before anything is entered); From and To as MM/YYYY from the
    frozen month and year; "I currently work here" ticked or not as approved. A current role's
    To is never entered and must stay empty. Location and Role Description are never entered
    and must stay empty.
  * An entry is added only when its controls are not on the page yet, by one click of the
    section's button; one that does not appear stops the attempt.
  * Each control is reported as entered as soon as the page was given its value (D137), then
    read back; one that does not hold exactly the approved value stops the attempt. A browser
    error while entering is the same stop, never an internal error.
  * Before the page's Next, every planned control must still hold what was approved, every one
    left empty must be empty, and the page must show no entry beyond the plan (an entry a
    parsed resume added, or an empty one): it would be sent unapproved, or refused by the
    page's own checks. Before anything is entered, `entry_indices` lets the adapter refuse a
    page that already shows more entries than were approved.
Nothing here maps, guesses or infers a value: it only enters what resolution established."""

import re

from playwright.sync_api import Error as PWError

from app.modules.execution.adapters.greenhouse_sections import (
    FillOp,
    Refused,
    RowPlan,
    SectionFillError,
    SectionPlan,
    _present,
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
_ADD = re.compile(r"\s*add(?:\s+another)?\s*", re.IGNORECASE)  # read whole (fullmatch)
_ENTRY_NAME = re.compile(r"^work\[(\d+)\]\.")
# Every control in the section that a click could act on (capture allows exactly one: its Add).
_BUTTONS = ("button", "input[type=button]", "input[type=submit]", "input[type=reset]",
            "input[type=image]", "[role=button]")  # fmt: skip


def _control(root: str, i: int, part: str) -> str:
    return f'{root} [name="work[{i}].{part}"]'


def _op(i: int, field: str, kind: str, selector: str, fr) -> FillOp:
    if kind == "text":
        text = fr.display
        if not isinstance(text, str) or not text.strip():
            raise Refused(f"{field}: resolved value carries no display text")
        if "\n" in text or "\r" in text:
            raise Refused(f"{field}: a text box cannot hold a line break")
        return FillOp(i, field, "text", selector, text, text)
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
    """The section's one button, by its text (as capture reads it, never its accessible name):
    exactly one control in the section can be clicked, and it reads Add or Add Another."""
    buttons = page.locator(", ".join(f"{root} {b}" for b in _BUTTONS))
    if buttons.count() != 1 or not _ADD.fullmatch(buttons.first.inner_text() or ""):
        raise SectionFillError(f"{KIND}: the section has no single Add button")
    buttons.first.click(timeout=timeout_ms)


def _give(page, op: FillOp, timeout_ms: int) -> None:
    loc = page.locator(op.selector).first
    if op.kind == "checkbox":
        loc.set_checked(bool(op.value), timeout=timeout_ms)
    else:
        loc.fill(str(op.value), timeout=timeout_ms)


def _holds(page, op: FillOp) -> bool:
    """The control holds exactly what was approved (a box: ticked as approved)."""
    try:
        loc = page.locator(op.selector)
        if loc.count() != 1:
            return False
        if op.kind == "checkbox":
            return loc.first.is_checked() == bool(op.value)
        return loc.first.input_value() == op.readback
    except PWError:
        return False


def _empty(page, selector: str) -> bool:
    """The control holds nothing (a box: not ticked); one the page does not have holds nothing."""
    try:
        loc = page.locator(selector)
        if loc.count() == 0:
            return True
        if loc.count() != 1:
            return False
        if (loc.first.get_attribute("type") or "") == "checkbox":
            return not loc.first.is_checked()
        return loc.first.input_value() == ""
    except PWError:
        return False


def apply(page, entries: SectionPlan, root: str, *, timeout_ms: int = 3000, on_entered=None,
          progress=None) -> list[dict]:  # fmt: skip
    """Enter every planned entry in order; return what was entered (row and field, never a
    value). Each control is reported as entered (`on_entered`, D137) as soon as the page was
    given its value, or the attempt to give it ended, then read back. SectionFillError (a
    Refused) when an entry will not appear, a control does not hold exactly its value, or the
    browser fails: what was entered before is on the error (`entered`)."""
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
                try:
                    _give(page, op, timeout_ms)
                finally:  # the page may hold it, or part of it, whatever happened
                    entered.append({"row": row.row, "field": op.field})
                    if on_entered is not None:
                        on_entered(entered[-1])
                if not _holds(page, op):
                    raise SectionFillError(f"{KIND} entry {row.row}: {op.field} did not keep it")
    except SectionFillError as e:
        e.entered = entered
        raise
    except PWError as e:
        failed = SectionFillError(f"{KIND}: the browser failed ({type(e).__name__})")
        failed.entered = entered
        raise failed from e
    return entered


_ENTRY_NAMES = """(root) => [...document.querySelectorAll(`${root} [name]`)].map(e => e.name)"""
# Each entry control the section has now, by its markup (hidden pages included): one hidden by
# its own attributes or an element's between it and the section, or one that cannot be edited.
_INOPERABLE = """(root) => {
  const top = document.querySelector(root);
  const hiding = /(^|;)\\s*(display\\s*:\\s*none|visibility\\s*:\\s*hidden)/i;
  const hides = (e) => e.hidden || e.getAttribute('aria-hidden') === 'true'
    || hiding.test(e.getAttribute('style') || '');
  return [...top.querySelectorAll('[name^="work["]')].filter((c) => {
    if (c.readOnly || c.disabled) return true;
    for (let e = c; e && e !== top; e = e.parentElement) if (hides(e)) return true;
    return false;
  }).length;
}"""


def entries_operable(page, root: str) -> bool:
    """Before anything is entered: every control of the entries already on the page can be
    typed into as their markup stands (D148's signals, never computed style: on a wizard the
    section's page is not shown yet)."""
    try:
        return page.locator(root).count() == 1 and page.evaluate(_INOPERABLE, root) == 0
    except PWError:
        return False


def entry_indices(page, root: str) -> set[int] | None:
    """The entries the section shows now, by index (hidden pages included); None when the page
    does not have exactly one such section."""
    try:
        if page.locator(root).count() != 1:
            return None
        names = page.evaluate(_ENTRY_NAMES, root)
    except PWError:
        return None
    return {int(m[1]) for n in names if (m := _ENTRY_NAME.match(n or ""))}


def readback(page, entries: SectionPlan, root: str) -> list[str]:
    """Every planned control holds exactly what was approved, every one left empty is empty, and
    the section shows no entry beyond the plan. What does not match, as "section:<kind>:<row>:
    <field or part>" (never a value)."""
    bad: list[str] = []
    for row in entries.rows:
        for op in row.ops:
            if not _holds(page, op):
                bad.append(f"section:{KIND}:{row.row}:{op.field}")
        for selector in row.blank:
            if not _empty(page, selector):
                part = selector.rsplit(".", 1)[-1].rstrip('"]')
                bad.append(f"section:{KIND}:{row.row}:{part}")
    found = entry_indices(page, root)
    if found is None:
        bad.append(f"section:{KIND}:root")
        return bad
    beyond = found - set(range(len(entries.rows)))
    bad.extend(f"section:{KIND}:{i}:entry" for i in sorted(beyond))
    return bad
