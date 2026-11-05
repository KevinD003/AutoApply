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

from dataclasses import dataclass

from app.modules.preparation.structured_sections import SectionResult


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


@dataclass(frozen=True)
class RowPlan:
    row: int
    record_id: str
    anchor: str  # "#...": the control whose presence proves this row exists on the page
    add_another_first: bool  # row > 0: click a page "Add another" when the anchor is absent
    ops: tuple[FillOp, ...]


@dataclass(frozen=True)
class SectionPlan:
    kind: str  # "education" | "employment"
    rows: tuple[RowPlan, ...]


def _sel(template: str, i: int) -> str:
    return "#" + template.format(i=i)


def _ops_for_field(kind: str, template, field: str, fr, row: int) -> list[FillOp]:
    if kind in ("text", "combobox"):
        return [FillOp(row, field, kind, _sel(template, row), fr.display, fr.display)]
    if kind == "checkbox":
        return [FillOp(row, field, "checkbox", _sel(template, row), bool(fr.value["bool"]), None)]
    if kind == "date":
        month_tpl, year_tpl = template
        month, year = fr.value["month"], fr.value["year"]
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
        for field, kind, template in spec:
            fr = row.fields.get(field)
            if fr is None or fr.status == "omitted":
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
            )
        )
    return SectionPlan(kind=section.kind, rows=tuple(rows))
