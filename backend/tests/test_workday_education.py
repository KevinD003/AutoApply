"""D163: the Workday-style stand-in's Education section (FIXTURE ASSUMPTION FA9,
fixtures/ats_receiver/workday_like.py) on the wizard's My Experience page and on the single page.
Capture reads it as an education section on its page, with its lists' options; the package
freezes your approved education into it (D120's rows: each school, degree and field of study
matched to exactly one option, else yours to settle before approval); the adapter enters each
entry on its page, adding one by the section's own button, chooses each list's option by its
value, types the dates, reads every control back, and refuses any entry beyond the approved ones.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real education section was
observed; on a real one the lists may be search prompts, which NoEfforts never fills).
Synthetic candidate data only."""

import re
import sys
from pathlib import Path

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.greenhouse_sections import Refused
from app.modules.execution.adapters.workday import (
    EDUCATION_ENTRIES_BEYOND,
    EDUCATION_NOT_ENTERED,
    EDUCATION_PREFILLED,
    EDUCATION_UNUSABLE,
    SECTION_UNUSABLE,
    WorkdayFixtureAdapter,
)
from app.modules.preparation import workday
from app.modules.preparation.forms import FieldType
from app.modules.preparation.package import SECTION_REQUIRED
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_experience import CURRENT as WORK_CURRENT
from tests.test_workday_experience import (
    _browser,  # noqa: F401  (the module's browser, for `page`)
    employment,
    page,  # noqa: F401
)
from tests.test_workday_wizard import approvals, approve, draft_pages, drafts, posts, rows

ROOT = "#education"  # FA9, the oracle's own copy
# The lists' options as the page offers them (FA9), the oracle's own copy.
SCHOOLS = [("sch-101", "State University"), ("sch-102", "Metro College"),
           ("sch-103", "Riverside Institute of Technology")]  # fmt: skip
DEGREES = [("deg-1", "High School"), ("deg-2", "Associate's Degree"),
           ("deg-3", "Bachelor's Degree"), ("deg-4", "Master's Degree"),
           ("deg-5", "Doctor of Philosophy (Ph.D.)"), ("deg-9", "Other")]  # fmt: skip
DISCIPLINES = [("dis-11", "Computer Science"), ("dis-12", "Mathematics"), ("dis-13", "Nursing"),
               ("dis-14", "Biology")]  # fmt: skip
BACHELOR = {"institution": "State University", "degree": "Bachelor's Degree",
            "field_of_study": "Computer Science", "start_date": "2014-09-01",
            "end_date": "2018-05-01"}  # fmt: skip
MASTER = {"institution": "Metro College", "degree": "Master's Degree",
          "field_of_study": "Mathematics", "start_date": "2019-09-01",
          "end_date": "2021-06-01"}  # fmt: skip
# What the page's controls hold for MASTER then BACHELOR (newest first, D120's order), as the
# browser sends them: each list its option's value, each date MM/YYYY.
SENT = {
    "edu[0].school": "sch-102", "edu[0].degree": "deg-4", "edu[0].discipline": "dis-12",
    "edu[0].from": "09/2019", "edu[0].to": "06/2021",
    "edu[1].school": "sch-101", "edu[1].degree": "deg-3", "edu[1].discipline": "dis-11",
    "edu[1].from": "09/2014", "edu[1].to": "05/2018",
}  # fmt: skip
ENTERED = [
    (i, f)
    for i in (0, 1)
    for f in ("school_name_id", "degree_id", "discipline_id", "start_date", "end_date")
]


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def education(api, record: dict) -> dict:
    r = api.post("/profile/education", json=record)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    return rec


def education_application(api, receiver, variant="education", *, records=(MASTER, BACHELOR),
                          single=False, approved=True, work=()) -> str:  # fmt: skip
    """The section's variant switched on (a wizard variant, or the single page's mode), your
    approved education (and work history), then a Workday-style application on a posting of its
    own, captured, answered and, when `approved`, approved."""
    receiver.config(**({"mode": "wd_education"} if single else {"wizard": variant}))
    synthetic_candidate(api)
    for record in records:
        education(api, record)
    for record in work:
        employment(api, record)
    job_id = workday_job(api, url=fresh_url())
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {"legalName--firstName": {"text": "Sam"}, "q.licence_type": {"label": "RN"},
               "q.shift": {"label": "Nights"}}  # fmt: skip
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    r = api.put(f"/applications/{app_id}/consents", json={"key": "terms_ack", "choice": "agree"})
    assert r.status_code == 200, r.text
    if approved:
        assert not r.json()["package"]["content"]["unresolved"]
        assert approve(api, app_id).status_code == 200
    return app_id


def content(api, app_id: str) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]["content"]


def page_2(led) -> dict:
    (d,) = [d for d in drafts(led) if d["page"] == 2]
    return d["fields"]


def edu(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if k.startswith("edu[")}


def accepted(receiver) -> dict:
    (row,) = receiver.ledger()["acceptances"]
    return row["fields"]


def entered(aid) -> list[tuple[int, str]]:
    return [(d["row"], d["field"]) for d in rows(aid, "disclosure")
            if d.get("kind") == "section_field" and d.get("section") == "education"]  # fmt: skip


def stand_in(variant: str | None = None, mode: str = "normal") -> str:
    """The stand-in's page as served, built by its own module (FA9)."""
    here = str(Path(__file__).resolve().parents[2] / "fixtures" / "ats_receiver")
    if here not in sys.path:
        sys.path.insert(0, here)
    import workday_like as wl

    cfg = {"mode": mode, "tamper": None, "wizard": variant, "page_check": None,
           "page_check_delay_ms": 800, "sends": None, "autosave": False}  # fmt: skip
    build = wl._wizard_page if variant else wl._form_page
    return build("examplehealth", "R-100001", "t", cfg).body.decode()


# ---------------------------------------------------------------------------- capture


def test_capture_reads_the_section_with_its_lists_and_never_its_controls_as_questions():
    schema = workday.extract_schema(stand_in("education"))
    (sec,) = schema.sections
    assert (sec.kind, sec.root, sec.step, sec.required) == ("education", ROOT, "My Experience",
                                                            False)  # fmt: skip
    assert [(o.id, o.text) for o in sec.schools] == SCHOOLS
    assert [(o.id, o.text) for o in sec.degrees] == DEGREES
    assert [(o.id, o.text) for o in sec.disciplines] == DISCIPLINES
    assert not [f for f in schema.fields if f.key.startswith("edu[")]
    assert workday.EDUCATION_KEY not in {f.key for f in schema.fields}


def test_the_single_page_s_section_has_no_page_and_a_required_one_is_read_as_required():
    (sec,) = workday.extract_schema(stand_in(mode="wd_education")).sections
    assert (sec.kind, sec.step, sec.required) == ("education", None, False)
    (sec,) = workday.extract_schema(stand_in("education_required")).sections
    assert sec.required


def test_both_sections_on_one_page_are_read_each_as_its_own():
    schema = workday.extract_schema(stand_in("education_and_experience"))
    assert [(s.kind, s.step) for s in schema.sections] == [
        ("employment", "My Experience"), ("education", "My Experience")]  # fmt: skip
    keys = {f.key for f in schema.fields}
    assert workday.WORK_KEY not in keys and workday.EDUCATION_KEY not in keys


def test_an_empty_entry_already_there_offering_the_template_s_options_is_read():
    (sec,) = workday.extract_schema(stand_in("education_entry_at_load")).sections
    assert sec.kind == "education"


TEMPLATE = re.compile(r'<template id="education-entry">.*?</template>', re.S)


def in_template(old: str, new: str, count: int = 1):
    """A change to the entry's template only (FA9's markup)."""

    def change(html: str) -> str:
        tpl = TEMPLATE.search(html)[0]
        assert old in tpl, old
        return html.replace(tpl, tpl.replace(old, new, count))

    return change


CANNOT_FILL = {
    "an entry asks something more": lambda h: stand_in("education_unknown_control"),
    "a list of several choices": in_template(
        'name="edu[__i__].school" required', 'name="edu[__i__].school" required multiple'
    ),
    "an option chosen at load": in_template(
        '<option value="sch-101">', '<option value="sch-101" selected>'
    ),
    "an empty option disabled": in_template(
        '<option value="">Select One</option>', '<option value="" disabled>Select One</option>'
    ),
    "no empty option first": in_template('<option value="">Select One</option>', ""),
    "an option without a value": in_template('<option value="deg-9">', "<option>"),
    "an option disabled": in_template(
        '<option value="dis-13">', '<option value="dis-13" disabled>'
    ),
    "an option labelled otherwise": in_template(
        '<option value="sch-103">', '<option value="sch-103" label="RIT">'
    ),
    "two options of one value": in_template('<option value="deg-2">', '<option value="deg-1">'),
    "a group of options": in_template(
        '<option value="dis-11">', '<optgroup label="Sciences"><option value="dis-11">'
    ),
    "a typed school": in_template(
        '<select id="edu-__i__-school" name="edu[__i__].school" required>',
        '<input id="edu-__i__-school" name="edu[__i__].school" type="text" required><select>',
    ),
    "a date not MM/YYYY": in_template(
        'name="edu[__i__].from" type="text" placeholder="MM/YYYY"',
        'name="edu[__i__].from" type="text" placeholder="YYYY"',
    ),
    "a date too short to hold MM/YYYY": in_template(
        'name="edu[__i__].to" type="text"', 'name="edu[__i__].to" type="text" maxlength="4"'
    ),
    "a list sent with another form": in_template(
        'name="edu[__i__].degree" required', 'name="edu[__i__].degree" required form="x"'
    ),
    "a part missing": in_template(
        '<label for="edu-__i__-to">To (Actual or Expected)</label>\n<input id="edu-__i__-to" '
        'name="edu[__i__].to" type="text" placeholder="MM/YYYY" required>',
        "",
    ),
    "a button in an entry": in_template("</div>", '<button type="button">Remove</button></div>'),
    "a second section": lambda h: h.replace(
        "</form>",
        '<div id="education-2" data-wd-section="education" '
        'data-wd-entry-template="education-entry"><button type="button">Add</button></div>'
        "</form>",
        1,
    ),
    "a control outside the section": lambda h: h.replace(
        "</form>", '<input name="edu[0].school" type="text"></form>', 1
    ),
    "the section hidden at load": lambda h: h.replace(
        '<div id="education" role="group"', '<div id="education" hidden role="group"', 1
    ),
    "no Add button": lambda h: h.replace(
        '<button type="button" data-wd-add>Add</button></div>', "</div>", 1
    ),
}


@pytest.mark.parametrize("change", list(CANNOT_FILL))
def test_any_other_education_is_one_required_checkpoint(change):
    """Never a guess, never left out silently: an education section NoEfforts cannot fill
    exactly as it is, apply on the employer's site."""
    schema = workday.extract_schema(CANNOT_FILL[change](stand_in("education")))
    assert not [s for s in schema.sections if s.kind == "education"]
    (cp,) = [f for f in schema.fields if f.key == workday.EDUCATION_KEY]
    assert cp.required and cp.type == FieldType.unsupported
    assert cp.unsupported_reason == workday.EDUCATION_REASON


def test_an_education_section_never_makes_the_work_history_a_checkpoint():
    """Before D163 an education section was read as a work history section of another kind:
    the work history checkpoint. Now the Work Experience section reads as before beside it."""
    keys = {f.key for f in workday.extract_schema(stand_in("education")).fields}
    assert workday.WORK_KEY not in keys


def test_the_section_s_options_are_part_of_the_form():
    """An option relabelled since approval is another form (the fingerprint): D132's pause."""
    from app.modules.preparation.forms import form_fingerprint

    html = stand_in("education")
    other = html.replace(">Metro College<", ">Metro Community College<")
    assert form_fingerprint(workday.extract_schema(html)) != form_fingerprint(
        workday.extract_schema(other))  # fmt: skip


# ---------------------------------------------------------------------------- the package


def test_the_package_freezes_your_education_with_the_page_s_options(api, receiver):
    app_id = education_application(api, receiver)
    (sec,) = content(api, app_id)["sections"]
    assert (sec["kind"], sec["root"], sec["step"]) == ("education", ROOT, "My Experience")
    got = [{k: (f["value"], f["display"]) for k, f in row["fields"].items()} for row in sec["rows"]]
    assert got[0] == {"school_name_id": ({"id": "sch-102"}, "Metro College"),
                      "degree_id": ({"id": "deg-4"}, "Master's Degree"),
                      "discipline_id": ({"id": "dis-12"}, "Mathematics"),
                      "start_date": ({"month": 9, "year": 2019}, "09/2019"),
                      "end_date": ({"month": 6, "year": 2021}, "06/2021")}  # fmt: skip
    assert got[1]["school_name_id"] == ({"id": "sch-101"}, "State University")


def test_a_record_no_option_matches_is_yours_to_settle_before_approval(api, receiver):
    app_id = education_application(
        api, receiver, records=(BACHELOR | {"institution": "Unlisted Academy"},), approved=False
    )
    unresolved = content(api, app_id)["unresolved"]
    assert [k for k in unresolved if k.startswith("section:education:")] and all(
        k.endswith(":school_name_id") for k in unresolved if k.startswith("section:education:")
    )
    assert approve(api, app_id).status_code != 200


def test_a_section_the_page_requires_needs_your_approved_education(api, receiver):
    app_id = education_application(api, receiver, "education_required", records=(),
                                   approved=False)  # fmt: skip
    pkg = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert "section:education" in pkg["unresolved"]
    assert {"key": "section:education", "message": SECTION_REQUIRED["education"]} in pkg[
        "validation_errors"
    ]
    assert approve(api, app_id).status_code != 200


# ---------------------------------------------------------------------------- the ledger


def test_each_entry_is_added_chosen_on_its_page_and_sent(api, receiver):
    app_id = education_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 1
    assert edu(page_2(led)) == SENT
    assert edu(accepted(receiver)) == SENT
    for d in drafts(led):
        if d["page"] != 2:
            assert not edu(d["fields"])  # only its own page sends the entries
    assert entered(aid) == ENTERED
    assert all(r["mismatched"] == 0 for r in rows(aid, "step"))


def test_on_the_single_page_each_entry_is_chosen_and_sent(api, receiver):
    app_id = education_application(api, receiver, single=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert edu(accepted(receiver)) == SENT
    assert entered(aid) == ENTERED


def test_both_sections_on_one_page_are_each_sent(api, receiver):
    app_id = education_application(api, receiver, "education_and_experience",
                                   work=(WORK_CURRENT,))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = page_2(receiver.ledger())
    assert edu(fields) == SENT
    assert fields["work[0].title"] == "Clinic Assistant"


def test_with_no_approved_education_no_entry_is_sent(api, receiver):
    app_id = education_application(api, receiver, records=())
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger())) == {} and edu(accepted(receiver)) == {}


def test_a_required_section_is_sent_with_your_entry(api, receiver):
    app_id = education_application(api, receiver, "education_required", records=(BACHELOR,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger()))["edu[0].school"] == "sch-101"


def test_an_empty_entry_already_there_is_filled_in_place(api, receiver):
    app_id = education_application(api, receiver, "education_entry_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger())) == SENT


def test_an_entry_a_parsed_resume_adds_is_never_sent(api, receiver):
    """The resume's parse adds an entry with values of its own: the section is read again after
    the page's uploads, so the attempt stops before anything is chosen in it, naming your
    education, and page 2's Next is never clicked."""
    app_id = education_application(api, receiver, "education_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert EDUCATION_PREFILLED in attempt(aid).outcome_detail
    assert entered(aid) == []


def test_an_entry_a_parsed_resume_adds_beyond_your_education_stops_naming_it(api, receiver):
    app_id = education_application(api, receiver, "education_parse", records=())
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert EDUCATION_ENTRIES_BEYOND in attempt(aid).outcome_detail
    assert posts(receiver.ledger(), "/apply") == 0


def test_a_choice_the_page_changes_after_its_page_was_saved_is_never_sent_on(api, receiver):
    """Page 2 is saved, then the page changes the first entry's school: page 3 is read back with
    every page before it, and its Next is never clicked."""
    app_id = education_application(api, receiver, "education_changed_after_next")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2] and posts(led, "/apply") == 0
    (step,) = [r for r in rows(aid, "step") if r["page"] == 3]
    assert step["mismatched"] == 1


def test_a_section_changed_after_approval_pauses_before_anything_is_entered(api, receiver):
    app_id = education_application(api, receiver)
    receiver.config(wizard="education_unknown_control")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_education_edit_retires_the_approval(api, receiver):
    """D140, unchanged: an edit to a record a package sends as an entry retires its approval at
    once; approved again, the new choice is sent."""
    app_id = education_application(api, receiver, records=(BACHELOR,))
    (rec,) = api.get("/profile/education").json()
    r = api.put(f"/profile/education/{rec['id']}", json=BACHELOR | {"degree": "Master's Degree"})
    assert r.status_code == 200, r.text
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    assert approvals(app_id) and all(a.invalidated_at is not None for a in approvals(app_id))
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger()))["edu[0].degree"] == "deg-4"


# ---------------------------------------------------------------------------- the plan


FROZEN = {
    "kind": "education", "root": ROOT,
    "rows": [{"record_id": "r1", "fields": {
        "school_name_id": {"status": "resolved", "value": {"id": "sch-101"},
                           "display": "State University"},
        "degree_id": {"status": "resolved", "value": {"id": "deg-3"},
                      "display": "Bachelor's Degree"},
        "discipline_id": {"status": "resolved", "value": {"id": "dis-11"},
                          "display": "Computer Science"},
        "start_date": {"status": "resolved", "value": {"month": 9, "year": 2014},
                       "display": "09/2014"},
        "end_date": {"status": "resolved", "value": {"month": 5, "year": 2018},
                     "display": "05/2018"}}}],
}  # fmt: skip


def test_the_plan_chooses_each_list_by_value_and_types_the_dates():
    (row,) = ws.plan(FROZEN).rows
    assert row.anchor == f'{ROOT} [name="edu[0].school"]'
    assert [(op.field, op.kind, op.selector.split('"')[1], op.value, op.readback)
            for op in row.ops] == [
        ("school_name_id", "select", "edu[0].school", "sch-101", "State University"),
        ("degree_id", "select", "edu[0].degree", "deg-3", "Bachelor's Degree"),
        ("discipline_id", "select", "edu[0].discipline", "dis-11", "Computer Science"),
        ("start_date", "text", "edu[0].from", "09/2014", "09/2014"),
        ("end_date", "text", "edu[0].to", "05/2018", "05/2018"),
    ]  # fmt: skip
    assert row.blank == ()


def test_an_education_section_with_a_field_unresolved_is_never_planned():
    data = {**FROZEN, "rows": [{**FROZEN["rows"][0], "fields": {
        **FROZEN["rows"][0]["fields"], "degree_id": {"status": "needs_user"}}}]}  # fmt: skip
    with pytest.raises(Refused):
        ws.plan(data)


def test_before_anything_is_entered_an_education_section_off_its_page_stops_naming_it():
    adapter = WorkdayFixtureAdapter.__new__(WorkdayFixtureAdapter)
    adapter.content = {
        "answers": [],
        "sections": [{**FROZEN, "step": "Elsewhere"}],
        "wizard": {"pages": ["My Information", "My Experience", "Review"]},
    }
    assert not adapter._section_usable(adapter.content["sections"][0])
    assert EDUCATION_UNUSABLE != SECTION_UNUSABLE and "education" in EDUCATION_UNUSABLE


# ---------------------------------------------------------------------------- in Chromium


def section_page(entries: str = "") -> str:
    """FA9's section on a page of its own, with its template and script."""
    html = stand_in(mode="wd_education")
    start = html.index('<div id="education"')
    section = html[start : html.index("</div>", html.index("data-wd-add", start)) + 6]
    template = TEMPLATE.search(html)[0]
    script = html[html.index("const eduSection"):html.index(
        "eduAdd.addEventListener('click', () => window.addEducationEntry());")]  # fmt: skip
    script += "eduAdd.addEventListener('click', () => window.addEducationEntry());"
    section = section.replace("<div data-wd-entries></div>", f"<div data-wd-entries>{entries}"
                              "</div>")  # fmt: skip
    return f"<form>{section}</form>{template}<script>{script}</script>"


def test_entries_are_added_chosen_and_read_back(page):  # noqa: F811
    page.set_content(section_page())
    got = ws.apply(page, ws.plan(FROZEN), ROOT)
    assert got == [
        {"row": 0, "field": f}
        for f in ("school_name_id", "degree_id", "discipline_id", "start_date", "end_date")
    ]
    assert page.locator('[name="edu[0].degree"]').input_value() == "deg-3"
    assert ws.readback(page, ws.plan(FROZEN), ROOT) == []


def test_the_readback_holds_each_list_to_its_value_and_its_shown_text(page):  # noqa: F811
    """A page that relabels the chosen option keeps its value but shows another school: found,
    as is one that chooses another option."""
    page.set_content(section_page())
    ws.apply(page, ws.plan(FROZEN), ROOT)
    page.locator('[name="edu[0].school"] option[value="sch-101"]').evaluate(
        "(o) => { o.text = 'Another University'; }"
    )
    page.locator('[name="edu[0].degree"]').select_option("deg-2")
    assert ws.readback(page, ws.plan(FROZEN), ROOT) == [
        "section:education:0:school_name_id", "section:education:0:degree_id"]  # fmt: skip


def test_an_option_the_list_no_longer_has_stops_with_what_was_entered(page):  # noqa: F811
    page.set_content(section_page())
    page.evaluate("""() => { const add = window.addEducationEntry;
      window.addEducationEntry = () => { const i = add();
        document.querySelector(`[name="edu[${i}].degree"] option[value="deg-3"]`).remove();
        return i; }; }""")
    with pytest.raises(ws.SectionFillError) as e:
        ws.apply(page, ws.plan(FROZEN), ROOT, timeout_ms=500)
    assert e.value.entered == [{"row": 0, "field": "school_name_id"},
                               {"row": 0, "field": "degree_id"}]  # fmt: skip


def test_before_anything_is_entered_an_education_entry_holding_a_choice_is_found(page):  # noqa: F811
    page.set_content(section_page())
    page.evaluate("() => window.addEducationEntry()")
    assert ws.entries_now(page, ROOT, "education") == {"inoperable": 0, "holding": 0}
    assert ws.entry_indices(page, ROOT, "education") == {0}
    page.locator('[name="edu[0].school"]').select_option("sch-102")
    assert ws.entries_now(page, ROOT, "education")["holding"] == 1
    # the work history's reading finds none of them
    assert ws.entry_indices(page, ROOT) == set()


def test_the_stops_name_education():
    for stop in (EDUCATION_UNUSABLE, EDUCATION_ENTRIES_BEYOND, EDUCATION_PREFILLED,
                 EDUCATION_NOT_ENTERED):  # fmt: skip
        assert "education" in stop and "work history" not in stop
