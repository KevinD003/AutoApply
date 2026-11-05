"""D120: the execution-side fill planner for Greenhouse structured education/employment sections
(`app.modules.execution.adapters.greenhouse_sections`). Pure logic: no browser, no database.

These prove the reused legacy row/id mechanics are applied safely — each row fills its own
controls (no overwrite), a checkpoint refuses the whole section, a current role sends no end date,
and an unusable value refuses rather than guesses.
"""

from datetime import date

import pytest

from app.modules.execution.adapters.greenhouse_sections import Refused, plan_section
from app.modules.preparation.structured_sections import (
    FieldResult,
    RowResult,
    SectionResult,
    resolve_employment_row,
)


def _resolved(name, value, display):
    return FieldResult(name, "resolved", value=value, display=display)


def _edu_row(rid, *, start=(5, 2018), end=(5, 2022)):
    return RowResult(
        rid,
        "education",
        {
            "school_name_id": _resolved("school_name_id", {"id": "s1"}, "State University"),
            "degree_id": _resolved("degree_id", {"id": "d1"}, "Bachelor's Degree"),
            "discipline_id": _resolved("discipline_id", {"id": "x1"}, "Computer Science"),
            "start_date": _resolved(
                "start_date", {"month": start[0], "year": start[1]}, f"{start[0]:02d}/{start[1]}"
            ),
            "end_date": _resolved(
                "end_date", {"month": end[0], "year": end[1]}, f"{end[0]:02d}/{end[1]}"
            ),
        },
    )


def _emp_row(rid, *, current):
    fields = {
        "company_name": _resolved("company_name", {"text": "Acme"}, "Acme"),
        "title": _resolved("title", {"text": "Engineer"}, "Engineer"),
        "start_date": _resolved("start_date", {"month": 1, "year": 2020}, "01/2020"),
        "current": _resolved("current", {"bool": current}, "Current" if current else "Not current"),
    }
    if current:
        fields["end_date"] = FieldResult("end_date", "omitted")
    else:
        fields["end_date"] = _resolved("end_date", {"month": 2, "year": 2023}, "02/2023")
    return RowResult(rid, "employment", fields)


def test_each_education_row_fills_its_own_controls_never_another_rows():
    plan = plan_section(SectionResult("education", [_edu_row("r1"), _edu_row("r2")]))
    assert plan.kind == "education"
    assert [r.row for r in plan.rows] == [0, 1]
    assert plan.rows[0].add_another_first is False  # row 0 is already on the page
    assert plan.rows[1].add_another_first is True  # later rows need an "Add another" click
    assert (plan.rows[0].anchor, plan.rows[1].anchor) == ("#school--0", "#school--1")

    row0 = {op.selector for op in plan.rows[0].ops}
    expected = {
        "#school--0",
        "#degree--0",
        "#discipline--0",
        "#start-month--0",
        "#start-year--0",
        "#end-month--0",
        "#end-year--0",
    }
    assert expected <= row0
    # Row 1 touches only its own --1 controls, so filling row 1 can never overwrite row 0.
    assert all(sel.endswith("--1") for sel in {op.selector for op in plan.rows[1].ops})


def test_combobox_and_date_readback_values():
    plan = plan_section(SectionResult("education", [_edu_row("r1")]))
    ops = {op.selector: op for op in plan.rows[0].ops}
    school = ops["#school--0"]
    assert school.kind == "combobox" and school.value == "State University"
    assert school.readback == "State University"  # read back the resolved option text, exactly
    month = ops["#start-month--0"]
    assert month.kind == "month" and month.value == 5 and month.readback == "May"
    year = ops["#start-year--0"]
    assert year.kind == "year" and year.value == "2018" and year.readback == "2018"


def test_a_checkpoint_field_refuses_the_whole_section():
    row = _edu_row("r1")
    row.fields["discipline_id"] = FieldResult("discipline_id", "needs_user", explanation="choose")
    with pytest.raises(Refused):
        plan_section(SectionResult("education", [row]))


def test_an_unsupported_section_refuses():
    section = SectionResult("education", [], supported=False, reason="no option lists captured")
    with pytest.raises(Refused):
        plan_section(section)


def test_current_role_ticks_current_and_sends_no_end_date():
    plan = plan_section(SectionResult("employment", [_emp_row("e1", current=True)]))
    ops = {op.selector: op for op in plan.rows[0].ops}
    assert "#company-name-0" in ops and "#title-0" in ops
    assert "#start-date-month-0" in ops and "#start-date-year-0" in ops
    current = ops["#current-role-0"]
    assert current.kind == "checkbox" and current.value is True and current.readback is None
    assert not any("end-date" in sel for sel in ops)  # a current role never sends an end date


def test_past_role_fills_its_end_date():
    plan = plan_section(SectionResult("employment", [_emp_row("e2", current=False)]))
    sels = {op.selector for op in plan.rows[0].ops}
    assert {"#end-date-month-0", "#end-date-year-0"} <= sels


def test_an_unusable_month_refuses_rather_than_guesses():
    row = _edu_row("r1")
    row.fields["start_date"] = _resolved("start_date", {"month": 13, "year": 2020}, "13/2020")
    with pytest.raises(Refused):
        plan_section(SectionResult("education", [row]))


def test_resolution_to_plan_bridge_for_employment():
    """The real resolver output (not a hand-built section) drives the planner end to end."""

    class _Rec:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    rec = _Rec(
        id=7,
        version=1,
        employer="Acme Corp",
        title="Software Engineer",
        start_date=date(2020, 1, 1),
        end_date=date(2023, 2, 1),
        is_current=False,
    )
    plan = plan_section(SectionResult("employment", [resolve_employment_row(rec)]))
    ops = {op.selector: op for op in plan.rows[0].ops}
    assert ops["#company-name-0"].value == "Acme Corp"
    assert ops["#title-0"].value == "Software Engineer"
    assert ops["#start-date-month-0"].readback == "January"
    assert ops["#end-date-year-0"].value == "2023"
