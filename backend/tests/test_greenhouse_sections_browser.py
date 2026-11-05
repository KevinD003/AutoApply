"""D120: the Playwright executor for Greenhouse structured sections
(`greenhouse_sections.apply_section_plan`), driven against a controlled repeating-section DOM.

The DOM here models the legacy-observed structure (per-row ids `school--N` / `degree--N` / ..., a
page "Add another" that creates the next row, type-ahead comboboxes with an aria-controls listbox).
The DOM itself is the oracle: after a fill, each control must hold exactly the resolved value. The
end-to-end receiver-ledger proof (through the real runner and the gh2 fixture) is a later increment;
this isolates the executor's mechanics — no database, Playwright only.
"""

import pytest

from app.modules.execution.adapters.greenhouse_sections import (
    Refused,
    apply_section_plan,
    plan_section,
)
from app.modules.preparation.structured_sections import FieldResult, RowResult, SectionResult

_TEMPLATE = """<!doctype html><html><body>
<form id="application-form">
  <div id="education-section">
    <h2>Education</h2>
    <div id="edu-rows"></div>
    <button type="button" id="edu-add">Add another</button>
  </div>
</form>
<script>
const SCHOOLS = ["State University", "Other University", "Metro College"];
const DEGREES = ["Bachelor's Degree", "Master's Degree", "Doctorate (PhD)"];
const DISCIPLINES = ["Computer Science", "Mathematics", "Physics"];
const MONTHS = ["January","February","March","April","May","June","July","August",
                "September","October","November","December"];
function combo(id, options) {
  const lis = options.map(o => `<li role="option">${o}</li>`).join("");
  return `<input type="text" id="${id}" role="combobox" aria-controls="${id}-listbox"
            aria-expanded="false" autocomplete="off">
          <ul id="${id}-listbox" role="listbox" style="display:none">${lis}</ul>`;
}
function rowHTML(i) {
  return `<div class="edu-row">
    ${combo("school--" + i, SCHOOLS)}
    ${combo("degree--" + i, DEGREES)}
    ${combo("discipline--" + i, DISCIPLINES)}
    ${combo("start-month--" + i, MONTHS)}
    <input type="text" id="start-year--${i}">
    ${combo("end-month--" + i, MONTHS)}
    <input type="text" id="end-year--${i}">
  </div>`;
}
function wire(root) {
  root.querySelectorAll('input[role=combobox]').forEach(function (inp) {
    const lb = document.getElementById(inp.getAttribute('aria-controls'));
    inp.addEventListener('click', function () { if (lb) lb.style.display = 'block'; });
    if (lb) {
      lb.querySelectorAll('[role=option]').forEach(function (op) {
        op.addEventListener('click', function () {
          inp.value = op.textContent.trim();
          lb.style.display = 'none';
        });
      });
    }
  });
}
let eduRows = 0;
function addRow() {
  const holder = document.createElement('div');
  holder.innerHTML = rowHTML(eduRows);
  document.getElementById('edu-rows').appendChild(holder);
  wire(holder);
  eduRows++;
}
addRow();  // row 0 exists at load
document.getElementById('edu-add').addEventListener('click', function () { __ADD_ACTION__ });
</script>
</body></html>"""


def _html(*, broken_add=False):
    return _TEMPLATE.replace("__ADD_ACTION__", "/* broken */" if broken_add else "addRow();")


def _res(name, value, display):
    return FieldResult(name, "resolved", value=value, display=display)


def _edu_row(rid, school, degree, disc, start, end):
    return RowResult(
        rid,
        "education",
        {
            "school_name_id": _res("school_name_id", {"id": rid + "s"}, school),
            "degree_id": _res("degree_id", {"id": rid + "d"}, degree),
            "discipline_id": _res("discipline_id", {"id": rid + "x"}, disc),
            "start_date": _res(
                "start_date", {"month": start[0], "year": start[1]}, f"{start[0]:02d}/{start[1]}"
            ),
            "end_date": _res(
                "end_date", {"month": end[0], "year": end[1]}, f"{end[0]:02d}/{end[1]}"
            ),
        },
    )


@pytest.fixture(scope="module")
def _browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield browser
        browser.close()


@pytest.fixture
def section_page(_browser):
    pg = _browser.new_page()
    yield pg
    pg.close()


def test_two_education_rows_fill_their_own_controls_with_no_overwrite(section_page):
    section_page.set_content(_html())
    section = SectionResult(
        "education",
        [
            _edu_row(
                "r1",
                "State University",
                "Bachelor's Degree",
                "Computer Science",
                (5, 2018),
                (5, 2022),
            ),
            _edu_row(
                "r2", "Other University", "Master's Degree", "Mathematics", (9, 2022), (6, 2024)
            ),
        ],
    )
    apply_section_plan(section_page, plan_section(section), "#education-section")
    v = lambda sel: section_page.locator(sel).input_value()  # noqa: E731
    # Row 1 came from "Add another"; row 0 keeps its own values (no cross-row overwrite).
    assert v("#school--0") == "State University"
    assert v("#school--1") == "Other University"
    assert v("#degree--0") == "Bachelor's Degree" and v("#degree--1") == "Master's Degree"
    assert v("#discipline--0") == "Computer Science" and v("#discipline--1") == "Mathematics"
    assert v("#start-month--0") == "May" and v("#start-year--0") == "2018"
    assert v("#end-month--1") == "June" and v("#end-year--1") == "2024"


def test_a_value_with_no_matching_option_refuses_rather_than_near_matches(section_page):
    section_page.set_content(_html())
    section = SectionResult(
        "education",
        [
            _edu_row(
                "r1",
                "Nonexistent College",
                "Bachelor's Degree",
                "Computer Science",
                (5, 2018),
                (5, 2022),
            )
        ],
    )
    with pytest.raises(Refused):
        apply_section_plan(section_page, plan_section(section), "#education-section")


def test_a_mid_fill_failure_preserves_what_was_already_disclosed(section_page):
    # Row 0 is valid; row 1's school has no matching option. Row 0 fills (is disclosed on the form),
    # then row 1 stops -- the error must carry what was already entered, so the attempt is never
    # logged as "nothing disclosed" once applicant data has reached the page.
    section_page.set_content(_html())
    section = SectionResult(
        "education",
        [
            _edu_row(
                "r1",
                "State University",
                "Bachelor's Degree",
                "Computer Science",
                (5, 2018),
                (5, 2022),
            ),
            _edu_row(
                "r2", "Nonexistent College", "Master's Degree", "Mathematics", (9, 2022), (6, 2024)
            ),
        ],
    )
    with pytest.raises(Refused) as ei:
        apply_section_plan(section_page, plan_section(section), "#education-section")
    entered = getattr(ei.value, "entered", None)
    assert entered, "a mid-fill stop must preserve the disclosures already made"
    # Row 1 failed at its first control (school), so only row 0's controls were disclosed.
    assert {e["row"] for e in entered} == {0}
    assert section_page.locator("#school--0").input_value() == "State University"


def test_a_planned_row_that_never_appears_refuses(section_page):
    section_page.set_content(_html(broken_add=True))  # "Add another" does nothing
    section = SectionResult(
        "education",
        [
            _edu_row(
                "r1",
                "State University",
                "Bachelor's Degree",
                "Computer Science",
                (5, 2018),
                (5, 2022),
            ),
            _edu_row(
                "r2", "Other University", "Master's Degree", "Mathematics", (9, 2022), (6, 2024)
            ),
        ],
    )
    with pytest.raises(Refused):
        apply_section_plan(
            section_page, plan_section(section), "#education-section", timeout_ms=800
        )
