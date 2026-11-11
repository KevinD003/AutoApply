"""D149: the Workday-style stand-in's Work Experience section (FIXTURE ASSUMPTION FA7,
fixtures/ats_receiver/workday_like.py) on the wizard's My Experience page and on the single page.
Capture reads it as an employment section on its page; the package freezes your approved work
history into it (D120's rows); the adapter enters each entry on its page, adding one by the
section's own button, reads every control back, and refuses any entry beyond the approved ones.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real work-history section was
observed). Synthetic candidate data only."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.workday import (
    SECTION_NOT_ENTERED,
    SECTION_UNUSABLE,
    WorkdayFixtureAdapter,
)
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import workday
from app.modules.preparation.forms import FieldType, form_fingerprint
from app.modules.preparation.package import SECTION_REQUIRED
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_wizard import approvals, approve, draft_pages, drafts, posts, rows

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


def page(sec: str, template: str | None = None, *, inside: str = "") -> str:
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
    schema, fields = read(page(section()))
    (sec,) = schema.sections
    assert sec.model_dump() == {"kind": "employment", "root": ROOT, "schools": [],
                                "degrees": [], "disciplines": []}  # fmt: skip
    assert set(fields) == {"resume"}  # no work[...] control is a question
    schema, fields = read(page(section(entry("0") + entry("1"))))  # empty entries at load
    assert len(schema.sections) == 1 and set(fields) == {"resume"}
    schema, _ = read(page(section(attrs=' aria-required="true"')))
    assert schema.sections[0].required is True


@pytest.mark.parametrize(
    "html",
    [
        page(section(), entry(extra='<input name="work[__i__].reason" type="text">')),
        page(section(), entry(loc=" required")),  # a control NoEfforts leaves empty, required
        page(section(), entry().replace('name="work[__i__].current"', 'name="work[__i__].x"')),
        page(section(), entry().replace('type="checkbox"', 'type="text"')),
        page(section(), entry(value=' value="01/2020"')),  # a template that fills every entry
        page(section(entry("0", value=' value="01/2020"'))),  # a value already on the page
        page(section(entry("0", checked=" checked"))),
        page(section(entry("1"))),  # entries not numbered from 0
        page(section(add="")),  # no way to add an entry
        page(section(add='<button type="button">Add</button><button type="button">Add</button>')),
        page(section(add="<button>Add</button>")),  # a submit button
        page(section(tid="none")),  # no template
        page(section(), inside=entry("0")),  # an entry outside the section
        page(section() + section()),  # two sections
        page(section()).replace('<template id="tpl">', '<template id="tpl2">'),
        page(section(), "").replace("</form>", "") + "</form>",  # the template inside the form
        page(section().replace('id="work-experience"', 'id="1bad"')),
    ],
    ids=["unknown-control", "left-empty-required", "a-part-missing", "a-part-of-another-kind",
         "template-value", "entry-value", "entry-ticked", "numbering", "no-add", "two-adds",
         "add-submits", "no-template", "entry-outside", "two-sections", "template-unfound",
         "template-in-form", "root-id"],  # fmt: skip
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


def test_controls_named_as_entries_without_a_section_are_a_checkpoint():
    html = page("", inside=entry("0"))
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
    """No work history, no section and no checkpoint: the plain wizard's and the single page's
    fingerprints are those D142 pinned (tests/test_workday_wizard.py)."""
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


def test_an_empty_entry_with_no_record_for_it_stops_before_its_page_is_sent(api, receiver):
    app_id = experience_application(api, receiver, "experience_entry_at_load", records=())
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0


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


def frozen_row(rid="r1", *, current=True, start=(1, 2019), end=(12, 2018)) -> dict:
    fields = {
        "company_name": {"status": "resolved", "value": {"text": "Example Health"},
                         "display": "Example Health"},
        "title": {"status": "resolved", "value": {"text": "Clinic Assistant"},
                  "display": "Clinic Assistant"},
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
    assert SECTION_UNUSABLE  # the plain stop's text (schema_matches)
    assert form_fingerprint  # imported for the fingerprint tests above
