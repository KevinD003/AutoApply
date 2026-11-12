"""D149: the Workday-style stand-in's Work Experience section (FIXTURE ASSUMPTION FA7,
fixtures/ats_receiver/workday_like.py) on the wizard's My Experience page and on the single page.
Capture reads it as an employment section on its page; the package freezes your approved work
history into it (D120's rows); the adapter enters each entry on its page, adding one by the
section's own button, reads every control back, and refuses any entry beyond the approved ones.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real work-history section was
observed). Synthetic candidate data only."""

import hashlib
import uuid

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.workday import (
    SECTION_ENTRIES_BEYOND,
    SECTION_NOT_ENTERED,
    SECTION_UNUSABLE,
    WorkdayFixtureAdapter,
)
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import workday
from app.modules.preparation.forms import (
    FieldType,
    FormField,
    FormSchema,
    SectionSpec,
    WizardSpec,
    field_fingerprint,
    form_fingerprint,
)
from app.modules.preparation.package import SECTION_REQUIRED
from tests.execution_harness import BASE, Receiver, attempt, queue, synthetic_candidate
from tests.test_workday_adapter import REQ, TENANT, fresh_url, workday_job
from tests.test_workday_wizard import (
    WORKDAY_FP,
    approvals,
    approve,
    draft_pages,
    drafts,
    posts,
    rows,
    wizard_html,
)

ROOT = "#work-experience"  # FA7, the oracle's own copy
CURRENT = {"employer": "Example Health", "title": "Clinic Assistant", "start_date": "2019-01-01",
           "end_date": None, "is_current": True}  # fmt: skip
PAST = {"employer": "River Clinic", "title": "Night Nurse", "start_date": "2015-03-01",
        "end_date": "2018-12-01", "is_current": False}  # fmt: skip
# What the page's controls hold for CURRENT then PAST (newest first, D120's order), as the
# browser sends them: a box only when ticked, a hidden To as an empty value.
SENT = {
    "work[0].title": "Clinic Assistant", "work[0].company": "Example Health",
    "work[0].location": "", "work[0].current": "1", "work[0].from": "01/2019",
    "work[0].to": "", "work[0].description": "",
    "work[1].title": "Night Nurse", "work[1].company": "River Clinic", "work[1].location": "",
    "work[1].from": "03/2015", "work[1].to": "12/2018", "work[1].description": "",
}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def employment(api, record: dict) -> dict:
    r = api.post("/profile/employment", json=record)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert api.post(f"/profile/employment/{rec['id']}/approve").status_code == 200
    return rec


def experience_application(api, receiver, variant="experience", *, records=(CURRENT, PAST),
                           single=False, approved=True) -> str:  # fmt: skip
    """The section's variant switched on (a wizard variant, or the single page's mode), your
    approved work history, then a Workday-style application on a posting of its own, captured,
    answered and, when `approved`, approved."""
    receiver.config(**({"mode": "wd_experience"} if single else {"wizard": variant}))
    synthetic_candidate(api)
    for record in records:
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


def work(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if k.startswith("work[")}


def accepted(receiver) -> dict:
    (row,) = receiver.ledger()["acceptances"]
    return row["fields"]


# ---------------------------------------------------------------------------- capture

ENTRY = """<div data-wd-entry="{i}">
<label for="t{i}">Job Title</label><input id="t{i}" name="work[{i}].title" type="text" required>
<label for="c{i}">Company</label><input id="c{i}" name="work[{i}].company" type="text" required>
<label for="l{i}">Location</label><input id="l{i}" name="work[{i}].location" type="text"{loc}>
<label><input name="work[{i}].current" type="checkbox" value="1"{checked}> Current</label>
<label for="f{i}">From</label><input id="f{i}" name="work[{i}].from" type="text"{value} required>
<label for="o{i}">To</label><input id="o{i}" name="work[{i}].to" type="text" required>
<label for="d{i}">Role Description</label><textarea id="d{i}" name="work[{i}].description">
</textarea>{extra}</div>"""


def entry(i="__i__", *, loc="", checked="", value="", extra="") -> str:
    return ENTRY.format(i=i, loc=loc, checked=checked, value=value, extra=extra)


def section(entries="", *, add='<button type="button">Add</button>', attrs="", tid="tpl") -> str:
    return (f'<div id="work-experience" data-wd-section="work" data-wd-entry-template="{tid}"'
            f"{attrs}><h3>Work Experience</h3><div>{entries}</div>{add}</div>")  # fmt: skip


def form_page(sec: str, template: str | None = None, *, inside: str = "") -> str:
    template = entry() if template is None else template
    return (f'<form id="workday-application" action="/apply" method="post">'
            f'<section data-step="My Experience"><label for="r">Resume/CV</label>'
            f'<input id="r" name="resume" type="file" required>{sec}{inside}</section>'
            f'<button type="submit">Submit</button></form>'
            f'<template id="tpl">{template}</template>')  # fmt: skip


def read(html: str):
    schema = workday.extract_schema(html)
    return schema, {f.key: f for f in schema.fields}


def test_capture_reads_the_section_and_never_its_controls_as_questions():
    schema, fields = read(form_page(section()))
    (sec,) = schema.sections
    assert sec.model_dump() == {"kind": "employment", "root": ROOT, "schools": [],
                                "degrees": [], "disciplines": []}  # fmt: skip
    assert set(fields) == {"resume"}  # no work[...] control is a question
    schema, fields = read(form_page(section(entry("0") + entry("1"))))  # empty entries at load
    assert len(schema.sections) == 1 and set(fields) == {"resume"}
    schema, _ = read(form_page(section(attrs=' aria-required="true"')))
    assert schema.sections[0].required is True


@pytest.mark.parametrize(
    "html",
    [
        form_page(section(), entry(extra='<input name="work[__i__].reason" type="text">')),
        form_page(section(), entry(loc=" required")),  # a control NoEfforts leaves empty, required
        form_page(section(), entry().replace('name="work[__i__].current"', 'name="work[__i__].x"')),
        form_page(section(), entry().replace('type="checkbox"', 'type="text"')),
        form_page(section(), entry(value=' value="01/2020"')),  # a template that fills every entry
        form_page(section(entry("0", value=' value="01/2020"'))),  # a value already on the page
        form_page(section(entry("0", checked=" checked"))),
        form_page(section(entry("1"))),  # entries not numbered from 0
        form_page(section(add="")),  # no way to add an entry
        form_page(section(add='<button type="button">Add</button>' * 2)),
        form_page(section(add="<button>Add</button>")),  # a submit button
        form_page(section(tid="none")),  # no template
        form_page(section(), inside=entry("0")),  # an entry outside the section
        form_page(section() + section()),  # two sections
        form_page(section()).replace('<template id="tpl">', '<template id="tpl2">'),
        form_page(section(), "").replace("</form>", "") + "</form>",  # the template inside the form
        form_page(section().replace('id="work-experience"', 'id="1bad"')),
        form_page(section(), entry(extra='<div role="textbox" aria-label="Start"></div>')),
        form_page(section(entry("0").replace('name="work[0].from"', 'name="work[0].from.month"'))),
        form_page(section(f'<template id="t2">{entry()}</template>')),  # a template inside the form
        form_page(section(), entry().replace(
            '<label><input name="work[__i__].current" type="checkbox" value="1"> Current</label>',
            "")),  # fmt: skip
        form_page(section(add='<button type="button">Add</button><input type="button" value="+">')),
        form_page(section(add='<button type="button">Add</button><span role="button">x</span>')),
        form_page(section(), entry(extra='<button type="button">Delete</button>')),
        form_page(section(), inside='<a id="work-experience"></a>'),  # an id used twice
        form_page(section(), entry().replace('type="text" required>', 'type="text" readonly>', 1)),
        form_page(section(), entry().replace('type="text" required>', 'type="text" disabled>', 1)),
        form_page(section(), entry().replace('<label for="c', '<label hidden for="c').replace(
            'name="work[__i__].company"', 'hidden name="work[__i__].company"')),  # fmt: skip
        form_page(section(attrs=" hidden")),
        form_page(f'<div style="display:none">{section()}</div>'),
        form_page(section(), entry(extra='<input name="work[__i__].title" type="text">')),
        form_page(section(entry("0").replace("</textarea>", "Text at load</textarea>"))),
        form_page(section(add='<button type="button">Add</button><div role="textbox"></div>')),
        form_page(section(), entry().replace('type="text">\n<label><input name="work[__i__].c',
                                             'type="text" aria-required="true">\n<label><input '
                                             'name="work[__i__].c')),  # fmt: skip
        form_page(section().replace('id="work-experience"', 'id="work-experience\n"')),
        form_page(section().replace('id="work-experience"', f'id="w{"x" * 200}"')),
        form_page(f'<div data-wizard-page="2" data-step="{"P" * 201}">{section()}</div>'),
    ],
    ids=["unknown-control", "left-empty-required", "a-part-missing", "a-part-of-another-kind",
         "template-value", "entry-value", "entry-ticked", "numbering", "no-add", "two-adds",
         "add-submits", "no-template", "entry-outside", "two-sections", "template-unfound",
         "template-in-form", "root-id", "custom-control", "a-part-split",
         "template-in-section", "a-part-absent", "an-input-button", "a-role-button",
         "a-button-in-an-entry", "id-used-twice", "readonly", "disabled", "a-hidden-control",
         "section-hidden", "section-wrapper-hidden", "a-part-twice",
         "description-text-at-load", "custom-control-in-section", "left-empty-aria-required",
         "id-with-newline", "id-too-long", "page-name-too-long"],  # fmt: skip
)
def test_any_other_work_history_is_one_required_checkpoint(html):
    """Anything about work history that is not the structure NoEfforts enters is one required
    checkpoint (apply on the employer's site): never a guess, never left out silently, and its
    controls are never questions of their own."""
    schema, fields = read(html)
    assert schema.sections == []
    assert not any(k.startswith("work[") for k in fields)
    cp = fields[workday.WORK_KEY]
    assert cp.type == FieldType.unsupported and cp.required
    assert cp.unsupported_reason == workday.WORK_REASON


def test_a_greenhouse_section_reads_and_fingerprints_as_before():
    """A section with no page and no requirement (Greenhouse's) is stored and fingerprinted
    exactly as before D149: the formula below is the one before it (the oracle's own copy)."""
    spec = SectionSpec(kind="employment", root="#employment-section")
    field = FormField(key="nickname", label="Nickname", type=FieldType.text)
    schema = FormSchema(fields=[field], sections=[spec])
    before = ["action=", "method=", field_fingerprint(field),
              "section|employment|#employment-section"]  # fmt: skip
    assert form_fingerprint(schema) == hashlib.sha256("|".join(before).encode()).hexdigest()
    assert spec.model_dump() == {"kind": "employment", "root": "#employment-section",
                                 "schools": [], "degrees": [], "disciplines": []}  # fmt: skip


def test_the_section_s_page_and_requirement_are_part_of_the_form():
    wizard = WizardSpec(pages=["My Information", "My Experience", "Review"])
    field = FormField(key="resume", label="Resume", type=FieldType.file, step="My Experience")

    def schema(**kw) -> FormSchema:
        sec = SectionSpec(kind="employment", root=ROOT, **kw)
        return FormSchema(fields=[field], sections=[sec], wizard=wizard)

    fingerprints = {form_fingerprint(schema(step="My Experience")),
                    form_fingerprint(schema(step="My Information")),
                    form_fingerprint(schema(step="My Experience", required=True))}  # fmt: skip
    assert len(fingerprints) == 3
    with pytest.raises(ValidationError):
        schema(step="Review")  # the review page holds no question
    with pytest.raises(ValidationError):  # a page on a form with no pages
        FormSchema(fields=[field], sections=[SectionSpec(kind="employment", root=ROOT,
                                                         step="My Experience")])  # fmt: skip


CHECKPOINT_COLLISIONS = [
    (workday.WORK_KEY, form_page(section(), entry(extra='<input name="work[__i__].x" type="text">'),
                                 inside='<label for="we">Years of work experience</label>'
                                        '<input id="we" name="work_experience" type="text">')),
    (workday.MULTI_STEP_KEY, form_page("", inside='<div data-workday-progress>Step 1 of 4</div>'
                                       '<label for="ms">Steps</label>'
                                       '<input id="ms" name="multi_step" type="text">')),
    (workday.PREFILLED_KEY, form_page("", inside='<label for="fi">First</label>'
                                      '<input id="fi" name="first" type="text" value="Sam">'
                                      '<label for="pv">Values</label>'
                                      '<input id="pv" name="prefilled_values" type="text">')),
]  # fmt: skip


@pytest.mark.parametrize("key, html", CHECKPOINT_COLLISIONS, ids=lambda x: str(x)[:20])
def test_a_page_question_named_like_a_checkpoint_never_hides_it(key, html):
    """D149 review: a page question that happens to share a checkpoint's key is replaced by the
    checkpoint, never kept in its place (the checkpoint blocks approval either way)."""
    _, fields = read(html)
    assert fields[key].type == FieldType.unsupported and fields[key].required
    assert fields[key].unsupported_reason


@pytest.mark.parametrize("key", [workday.WORK_KEY, workday.MULTI_STEP_KEY, workday.PREFILLED_KEY])
def test_a_page_question_named_like_a_checkpoint_is_on_its_page_like_any_other(receiver, key):
    """D149 review: on a wizard, such a question is held to D142's rule that every question is
    on a page before the review page, as any other is."""
    html = wizard_html(receiver).replace(
        '<button type="submit" data-automation-id="bottom-navigation-next-button">',
        f'<label for="cx">Collides</label><input id="cx" name="{key}" type="text" required>'
        '<button type="submit" data-automation-id="bottom-navigation-next-button">')  # fmt: skip
    schema, fields = read(html)
    assert schema.wizard is None and workday.MULTI_STEP_KEY in fields


def test_controls_named_as_entries_without_a_section_are_a_checkpoint():
    html = form_page("", inside=entry("0"))
    schema, fields = read(html)
    assert schema.sections == [] and workday.WORK_KEY in fields


def test_on_a_wizard_the_section_is_on_its_page(api, receiver):
    receiver.config(wizard="experience")
    synthetic_candidate(api)
    job_id = workday_job(api, url=fresh_url())
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 201, r.text
    schema = r.json()["schema"]
    assert schema["sections"] == [{"kind": "employment", "root": ROOT, "schools": [],
                                   "degrees": [], "disciplines": [],
                                   "step": "My Experience"}]  # fmt: skip
    assert not any(f["key"].startswith("work") for f in schema["fields"])
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_a_page_without_the_section_reads_as_before(api, receiver):
    """No work history, no section and no checkpoint; the default page's fingerprint is the one
    pinned before D142 (tests/test_workday_wizard.py)."""
    receiver.config(wizard=None)
    default = httpx.get(f"{BASE}/workday/{TENANT}/{REQ}/apply").text
    assert form_fingerprint(workday.extract_schema(default)) == WORKDAY_FP
    for cfg in ({"wizard": "plain"}, {"mode": "normal"}):
        receiver.config(**cfg)
        synthetic_candidate(api)
        job_id = workday_job(api, url=fresh_url())
        r = api.post(f"/jobs/{job_id}/form/workday")
        assert r.status_code == 201, r.text
        assert "sections" not in r.json()["schema"] or r.json()["schema"]["sections"] == []
        keys = {f["key"] for f in r.json()["schema"]["fields"]}
        assert workday.WORK_KEY not in keys


# ---------------------------------------------------------------------------- package


def test_the_package_freezes_your_work_history_on_its_page(api, receiver):
    app_id = experience_application(api, receiver, approved=False)
    (sec,) = content(api, app_id)["sections"]
    assert sec["kind"] == "employment" and sec["root"] == ROOT and sec["step"] == "My Experience"
    got = [{k: f["display"] for k, f in r["fields"].items()} for r in sec["rows"]]
    assert got == [
        {"company_name": "Example Health", "title": "Clinic Assistant", "start_date": "01/2019",
         "current": "Current", "end_date": None},
        {"company_name": "River Clinic", "title": "Night Nurse", "start_date": "03/2015",
         "current": "Not current", "end_date": "12/2018"},
    ]  # fmt: skip
    assert sec["rows"][0]["fields"]["end_date"]["status"] == "omitted"


def test_a_section_the_page_requires_needs_your_approved_work_history(api, receiver):
    app_id = experience_application(api, receiver, "experience_required", records=(),
                                    approved=False)  # fmt: skip
    c = content(api, app_id)
    assert c["unresolved"] == ["section:employment"]
    assert {"key": "section:employment",
            "message": SECTION_REQUIRED["employment"]} in c["validation_errors"]  # fmt: skip
    assert approve(api, app_id).status_code == 409
    employment(api, PAST)
    c = content(api, app_id)
    assert not c["unresolved"] and len(c["sections"][0]["rows"]) == 1
    assert approve(api, app_id).status_code == 200


def test_work_history_the_section_cannot_take_blocks_approval(api, receiver):
    app_id = experience_application(api, receiver, "experience_unknown_control", approved=False)
    c = content(api, app_id)
    assert workday.WORK_KEY in c["unresolved"] and "sections" not in c
    assert approve(api, app_id).status_code == 409


# ---------------------------------------------------------------------------- the ledger


def test_each_entry_is_added_entered_on_its_page_and_sent(api, receiver):
    app_id = experience_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 1
    assert work(page_2(led)) == SENT
    assert work(accepted(receiver)) == SENT
    for d in drafts(led):
        if d["page"] != 2:
            assert not work(d["fields"])  # only its own page sends the entries
    entered = [(d["row"], d["field"]) for d in rows(aid, "disclosure")
               if d.get("kind") == "section_field"]  # fmt: skip
    assert entered == [(0, "title"), (0, "company_name"), (0, "start_date"), (0, "current"),
                       (1, "title"), (1, "company_name"), (1, "start_date"), (1, "current"),
                       (1, "end_date")]  # fmt: skip
    assert all(r["mismatched"] == 0 for r in rows(aid, "step"))


def test_with_no_approved_work_history_no_entry_is_sent(api, receiver):
    app_id = experience_application(api, receiver, records=())
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert work(page_2(led)) == {} and work(accepted(receiver)) == {}


def test_a_required_section_is_sent_with_your_entry(api, receiver):
    app_id = experience_application(api, receiver, "experience_required", records=(CURRENT,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert work(page_2(receiver.ledger()))["work[0].title"] == "Clinic Assistant"


@pytest.mark.parametrize("records", [(CURRENT,), ()], ids=["one-record", "no-record"])
def test_an_entry_a_parsed_resume_adds_is_never_sent(api, receiver, records):
    """The resume's parse adds an entry with values of its own (a description NoEfforts leaves
    empty; with no record, the whole entry): page 2 is read back before its Next, which is never
    clicked."""
    app_id = experience_application(api, receiver, "experience_parse", records=records)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    (step,) = [r for r in rows(aid, "step") if r["page"] == 2]
    assert step["mismatched"] >= 1


@pytest.mark.parametrize("records, sent", [((CURRENT,), 1), ((CURRENT, PAST), 2)],
                         ids=["filled-in-place", "one-added"])  # fmt: skip
def test_an_empty_entry_already_there_is_filled_in_place(api, receiver, records, sent):
    app_id = experience_application(api, receiver, "experience_entry_at_load", records=records)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    got = work(page_2(receiver.ledger()))
    assert {k.split("]")[0] for k in got} == {f"work[{i}" for i in range(sent)}
    assert got["work[0].title"] == "Clinic Assistant"


def test_an_empty_entry_with_no_record_for_it_stops_before_anything_is_entered(api, receiver):
    """D149 review: known before anything is entered, so it stops then (nothing saved at the
    employer, nothing uploaded), never after page 1 was saved."""
    app_id = experience_application(api, receiver, "experience_entry_at_load", records=())
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert SECTION_ENTRIES_BEYOND in attempt(aid).outcome_detail
    assert attempt(aid).disclosure_started_at is None


def test_a_page_showing_an_entry_after_approval_stops_before_anything_is_entered(api, receiver):
    """Approved with no entry on the page and no work history; the page now shows an empty one:
    the same form (an empty entry is read as before), stopped before anything is entered."""
    app_id = experience_application(api, receiver, records=())
    receiver.config(wizard="experience_entry_at_load")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    assert SECTION_ENTRIES_BEYOND in attempt(aid).outcome_detail


def test_a_stop_after_an_entry_keeps_what_was_entered(api, receiver):
    """The page adds the first entry and no other: the first entry's controls are recorded as
    entered, the attempt stops before page 2's Next."""
    app_id = experience_application(api, receiver, "experience_add_once")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert SECTION_NOT_ENTERED in attempt(aid).outcome_detail
    entered = [(d["row"], d["field"]) for d in rows(aid, "disclosure")
               if d.get("kind") == "section_field"]  # fmt: skip
    assert entered == [(0, "title"), (0, "company_name"), (0, "start_date"), (0, "current")]


def test_an_entry_changed_after_its_page_was_saved_is_never_sent_on(api, receiver):
    """Page 2 is saved, then the page changes its first entry: page 3 is read back with every
    page before it, and its Next is never clicked."""
    app_id = experience_application(api, receiver, "experience_changed_after_next")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2] and posts(led, "/apply") == 0
    (step,) = [r for r in rows(aid, "step") if r["page"] == 3]
    assert step["mismatched"] == 1


def test_a_build_that_cannot_read_the_section_pauses_before_anything_is_entered(
    api, receiver, monkeypatch
):
    """Why no version change is needed: approved with the section, then read by a build that
    cannot see it (simulated), the live form is not the approved one, so the attempt pauses
    before anything is entered (D132), as for an approval given before D149."""
    app_id = experience_application(api, receiver)
    monkeypatch.setattr(workday, "_work_section", lambda html: (None, False))
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    with SessionLocal() as db:
        pause = db.scalars(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id))).one()  # fmt: skip
        assert pause.resolved_at is None


def test_an_entry_that_will_not_appear_stops_the_attempt(api, receiver):
    app_id = experience_application(api, receiver, "experience_add_broken", records=(CURRENT,))
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert SECTION_NOT_ENTERED in attempt(aid).outcome_detail
    assert not [d for d in rows(aid, "disclosure") if d.get("kind") == "section_field"]


def test_a_section_changed_after_approval_pauses_before_anything_is_entered(api, receiver):
    app_id = experience_application(api, receiver)
    receiver.config(wizard="experience_unknown_control")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    with SessionLocal() as db:
        pause = db.scalars(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id))).one()  # fmt: skip
        assert pause.resolved_at is None


def test_a_work_history_edit_retires_the_approval(api, receiver):
    """D140, unchanged: an edit to a record a package sends as an entry retires its approval at
    once; approved again, the new value is sent."""
    app_id = experience_application(api, receiver, records=())
    rec = employment(api, CURRENT)
    assert all(a.invalidated_at is not None for a in approvals(app_id))
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert work(page_2(receiver.ledger()))["work[0].title"] == "Clinic Assistant"
    assert rec["title"] == "Clinic Assistant"


def test_on_the_single_page_each_entry_is_entered_and_sent(api, receiver):
    app_id = experience_application(api, receiver, single=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert work(accepted(receiver)) == SENT


# ---------------------------------------------------------------------------- the executor


def frozen(rows_: list[dict], **extra) -> dict:
    return {"kind": "employment", "root": ROOT, "rows": rows_, **extra}


def frozen_row(rid="r1", *, current=True, start=(1, 2019), end=(12, 2018),
               title="Clinic Assistant", company="Example Health") -> dict:  # fmt: skip
    fields = {
        "company_name": {"status": "resolved", "value": {"text": company}, "display": company},
        "title": {"status": "resolved", "value": {"text": title}, "display": title},
        "start_date": {"status": "resolved", "value": {"month": start[0], "year": start[1]},
                       "display": f"{start[0]:02d}/{start[1]}"},
        "current": {"status": "resolved", "value": {"bool": current},
                    "display": "Current" if current else "Not current"},
        "end_date": ({"status": "omitted", "value": None, "display": None} if current else
                     {"status": "resolved", "value": {"month": end[0], "year": end[1]},
                      "display": f"{end[0]:02d}/{end[1]}"}),
    }  # fmt: skip
    return {"record_id": rid, "fields": fields}


def test_the_plan_enters_what_was_approved_and_leaves_the_rest_empty():
    entries = ws.plan(frozen([frozen_row(), frozen_row("r2", current=False)]))
    first, second = entries.rows
    assert [(op.field, op.value) for op in first.ops] == [
        ("title", "Clinic Assistant"), ("company_name", "Example Health"),
        ("start_date", "01/2019"), ("current", True)]  # fmt: skip
    assert set(first.blank) == {f'{ROOT} [name="work[0].{p}"]'
                                for p in ("location", "description", "to")}  # fmt: skip
    assert ("end_date", "12/2018") in [(op.field, op.value) for op in second.ops]
    assert all(op.selector.startswith(f'{ROOT} [name="work[1].') for op in second.ops)


@pytest.mark.parametrize(
    "data",
    [
        frozen([frozen_row(start=(13, 2019))]),
        frozen([frozen_row(start=(1, 19))]),
        {**frozen([frozen_row()]), "kind": "education"},
        {**frozen([frozen_row()]), "root": "body > form"},
        frozen([frozen_row(), frozen_row()]),  # one record twice
        frozen([{"record_id": "r1", "fields": {"salary": {"status": "resolved"}}}]),
        frozen([{"record_id": "r1", "fields": {**frozen_row()["fields"],
                 "title": {"status": "needs_user"}}}]),  # fmt: skip
    ],
    ids=["month", "year", "education", "root", "twice", "unknown-field", "unresolved"],
)
def test_a_frozen_section_it_cannot_enter_exactly_is_refused(data):
    with pytest.raises(ws.Refused):
        ws.plan(data)


def test_before_anything_is_entered_a_section_off_its_page_stops_the_attempt():
    def usable(sec: dict, wizard: dict | None) -> bool:
        content_ = {"answers": [], "documents": [], "destination": {"url": "http://x/"},
                    **({"wizard": wizard} if wizard else {})}  # fmt: skip
        return WorkdayFixtureAdapter(content_, {})._section_usable(sec)

    wizard = {"pages": ["My Information", "My Experience", "Review"]}
    sec = frozen([frozen_row()])
    assert usable({**sec, "step": "My Experience"}, wizard)
    assert not usable({**sec, "step": "Review"}, wizard)
    assert not usable(sec, wizard)
    assert usable(sec, None)
    assert not usable({**sec, "step": "My Experience"}, None)
    assert not usable({**frozen([frozen_row(start=(0, 2019))]), "step": "My Experience"}, wizard)


# ---------------------------------------------------------------------------- in the browser

SECTION_PAGE = """<!doctype html><html><body>
<form id="workday-application" action="http://fixture.test/apply" method="post">
<section data-step="My Experience">
<label for="r">Resume/CV</label><input id="r" name="resume" type="file">
<div id="work-experience" data-wd-section="work" data-wd-entry-template="tpl">
<div data-entries>{entries}</div><button type="button" id="add">Add</button>{extra}</div>
</section><button type="submit">Submit</button></form>
<template id="tpl">{template}</template>
<script>
const entries = document.querySelector('[data-entries]');
function wire(e) {{
  const box = e.querySelector('[name$=".current"]'), to = e.querySelector('[name$=".to"]');
  box.addEventListener('change', () => {{
    to.hidden = box.checked;
    if (box.checked) to.value = '';
  }});
}}
for (const e of entries.children) wire(e);
document.getElementById('add').addEventListener('click', () => {{
  if (window.broken) return;
  const i = entries.children.length;
  entries.insertAdjacentHTML('beforeend',
    document.getElementById('tpl').innerHTML.replaceAll('__i__', String(i)));
  wire(entries.lastElementChild);
}});
</script></body></html>"""
CURRENT_OPS = ("title", "company_name", "start_date", "current")


def section_page(entries: str = "", extra: str = "") -> str:
    return SECTION_PAGE.format(entries=entries, extra=extra, template=entry())


def section_adapter(captured: str, sections: list[dict], wizard=None) -> WorkdayFixtureAdapter:
    dest = {"url": "http://fixture.test/workday/t/R-1000", "submit_url": "http://fixture.test/apply",
            "form_fingerprint": form_fingerprint(workday.extract_schema(captured))}  # fmt: skip
    return WorkdayFixtureAdapter({"answers": [], "documents": [], "destination": dest,
                                  "sections": sections, **({"wizard": wizard} if wizard else {})},
                                 {})  # fmt: skip


@pytest.fixture(scope="module")
def _browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield browser
        browser.close()


@pytest.fixture
def page(_browser):
    pg = _browser.new_page()
    yield pg
    pg.close()


def test_entries_are_added_entered_and_read_back(page):
    page.set_content(section_page())
    entries = ws.plan(frozen([frozen_row(), frozen_row("r2", current=False)]))
    got = ws.apply(page, entries, ROOT)
    assert got == [{"row": 0, "field": f} for f in CURRENT_OPS] + [
        {"row": 1, "field": f} for f in (*CURRENT_OPS, "end_date")]  # fmt: skip
    assert ws.readback(page, entries, ROOT) == []
    assert page.locator('[name="work[0].current"]').is_checked()
    assert page.locator('[name="work[0].to"]').input_value() == ""  # never entered
    assert page.locator('[name="work[1].to"]').input_value() == "12/2018"
    assert page.locator('[name="work[1].from"]').input_value() == "01/2019"


def test_the_readback_finds_every_difference_and_any_entry_beyond_the_plan(page):
    page.set_content(section_page())
    entries = ws.plan(frozen([frozen_row(), frozen_row("r2", current=False)]))
    ws.apply(page, entries, ROOT)
    page.evaluate("""() => {
      document.querySelector('[name="work[0].description"]').value = 'Parsed (fictional)';
      document.querySelector('[name="work[0].to"]').value = '01/2020';
      document.querySelector('[name="work[1].title"]').value = 'Another title';
      document.querySelector('[name="work[1].current"]').checked = true;
      document.getElementById('add').click();
    }""")
    assert sorted(ws.readback(page, entries, ROOT)) == sorted([
        "section:employment:0:description", "section:employment:0:to",
        "section:employment:1:title", "section:employment:1:current",
        "section:employment:2:entry"])  # fmt: skip


def test_an_empty_entry_beyond_the_plan_is_found_too(page):
    page.set_content(section_page(entries=entry("0")))
    assert ws.readback(page, ws.plan(frozen([])), ROOT) == ["section:employment:0:entry"]


def test_a_section_the_page_no_longer_has_is_found(page):
    page.set_content("<!doctype html><html><body><form></form></body></html>")
    assert ws.readback(page, ws.plan(frozen([])), ROOT) == ["section:employment:root"]


def test_an_entry_that_does_not_appear_stops_with_what_was_entered(page):
    page.set_content(section_page(entries=entry("0")))
    page.evaluate("() => { window.broken = true; }")
    entries = ws.plan(frozen([frozen_row(), frozen_row("r2", current=False)]))
    with pytest.raises(ws.SectionFillError) as e:
        ws.apply(page, entries, ROOT, timeout_ms=500)
    assert e.value.entered == [{"row": 0, "field": f} for f in CURRENT_OPS]


def test_a_section_without_one_add_button_is_never_clicked(page):
    page.set_content(section_page(extra='<button type="button">Add Another</button>'))
    with pytest.raises(ws.SectionFillError) as e:
        ws.apply(page, ws.plan(frozen([frozen_row()])), ROOT, timeout_ms=500)
    assert e.value.entered == []
    assert page.locator('[name="work[0].title"]').count() == 0


def test_a_control_that_does_not_keep_its_value_stops_the_entry(page):
    page.set_content(section_page(entries=entry("0")))
    page.evaluate("""() => document.querySelector('[name="work[0].company"]')
      .addEventListener('input', e => { e.target.value = 'Changed'; })""")
    with pytest.raises(ws.SectionFillError) as e:
        ws.apply(page, ws.plan(frozen([frozen_row()])), ROOT, timeout_ms=500)
    # The company was given to the page (whose script saw it) even though it was not kept.
    assert e.value.entered == [{"row": 0, "field": "title"}, {"row": 0, "field": "company_name"}]


def test_a_value_is_entered_and_read_back_exactly(page):
    """D149 review: an approved title or employer is typed and read back exactly, spaces and
    all; one holding a line break (which a text box cannot hold) is refused before entry."""
    page.set_content(section_page())
    entries = ws.plan(frozen([frozen_row(title="Night Nurse ", company=" River Clinic")]))
    ws.apply(page, entries, ROOT)
    assert page.locator('[name="work[0].title"]').input_value() == "Night Nurse "
    assert page.locator('[name="work[0].company"]').input_value() == " River Clinic"
    assert ws.readback(page, entries, ROOT) == []
    with pytest.raises(ws.Refused):
        ws.plan(frozen([frozen_row(title="Night\nNurse")]))


def test_the_add_button_is_found_by_its_text(page):
    """As capture reads it: an accessible name of its own changes nothing."""
    page.set_content(section_page().replace('id="add">', 'id="add" aria-label="New entry">'))
    assert len(ws.apply(page, ws.plan(frozen([frozen_row()])), ROOT)) == 4


def test_a_browser_error_while_entering_is_the_section_s_stop(page):
    """D149 review: a control the page made uneditable fails in the browser; that is the
    section's stop, with the control reported as entered, never an internal error."""
    page.set_content(section_page(entries=entry("0")))
    page.evaluate("""() => document.querySelector('[name="work[0].title"]').disabled = true""")
    with pytest.raises(ws.SectionFillError) as e:
        ws.apply(page, ws.plan(frozen([frozen_row()])), ROOT, timeout_ms=300)
    assert e.value.entered == [{"row": 0, "field": "title"}]


@pytest.mark.parametrize("change", [
    "document.querySelector('[data-wd-entry]').hidden = true",
    "document.querySelector('[name=\"work[0].from\"]').readOnly = true",
    "document.querySelector('[name=\"work[0].company\"]').disabled = true",
], ids=["hidden", "readonly", "disabled"])  # fmt: skip
def test_before_anything_is_entered_an_entry_it_cannot_type_into_stops_it(page, change):
    """D149 review: an entry already on the page that cannot be typed into, as its markup stands
    (hidden pages included), is a plain stop before anything is entered."""
    html = section_page(entries=entry("0"))
    page.set_content(html)
    page.evaluate(f"() => {{ {change}; }}")
    assert section_adapter(html, [frozen([frozen_row()])]).schema_matches(page) == SECTION_UNUSABLE


def test_before_anything_is_entered_entries_beyond_the_approved_ones_stop_it(page):
    html = section_page(entries=entry("0"))
    page.set_content(html)
    assert section_adapter(html, [frozen([])]).schema_matches(page) == SECTION_ENTRIES_BEYOND
    assert section_adapter(html, [frozen([frozen_row()])]).schema_matches(page) is None


def test_the_adapter_enters_a_single_page_s_section_and_reads_it_back(page):
    html = section_page()
    page.set_content(html)
    adapter = section_adapter(html, [frozen([frozen_row()])])
    assert adapter.schema_matches(page) is None
    sent = adapter.fill(page)
    assert [(d["kind"], d["row"], d["field"]) for d in sent] == [
        ("section_field", 0, f) for f in CURRENT_OPS]  # fmt: skip
    assert adapter.readback(page) == []
    page.evaluate("""() => document.querySelector('[name="work[0].location"]').value = 'x'""")
    assert adapter.readback(page) == ["section:employment:0:location"]


def test_before_anything_is_entered_a_section_it_cannot_enter_is_a_plain_stop(page):
    html = section_page()
    page.set_content(html)
    adapter = section_adapter(html, [frozen([frozen_row(start=(13, 2019))])])
    assert adapter.schema_matches(page) == SECTION_UNUSABLE
    assert page.locator('[name="work[0].title"]').count() == 0


def test_on_a_wizard_a_section_is_entered_and_read_back_with_its_own_page(page):
    html = section_page()
    page.set_content(html)
    wizard = {"pages": ["My Information", "My Experience", "Review"]}
    sec = {**frozen([frozen_row()]), "step": "My Experience"}
    adapter = section_adapter(html, [sec], wizard)
    assert adapter.fill_page(page, 1) == []
    assert page.locator('[name="work[0].title"]').count() == 0
    assert adapter.readback_through(page, 1) == []  # its page is not read back yet
    assert adapter.readback_through(page, 2) == [f"section:employment:0:{f}" for f in CURRENT_OPS]
    assert [d["field"] for d in adapter.fill_page(page, 2)] == list(CURRENT_OPS)
    assert adapter.readback_through(page, 2) == [] and adapter.readback(page) == []
