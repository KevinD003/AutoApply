"""D155: a Workday-style Work Experience entry's Location and Role Description (FIXTURE
ASSUMPTION FA7, fixtures/ats_receiver/workday_like.py) are entered from your own employment
record when it holds them, and left empty when it does not; a page that requires one your record
lacks blocks approval instead of being refused when the form is read. Greenhouse's sections, and
every other form, are unchanged.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves. Synthetic candidate data only."""

import datetime
import re
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_sections as gs
from app.modules.execution.adapters import workday_sections as ws
from app.modules.preparation import structured_sections as ss
from app.modules.preparation import workday
from app.modules.preparation.forms import (
    FieldType,
    FormField,
    FormSchema,
    SectionSpec,
    WizardSpec,
    form_fingerprint,
)
from app.modules.preparation.package import SCHEMA_VERSION
from tests.execution_harness import Receiver, queue
from tests.test_workday_experience import (
    CURRENT,
    PAST,
    ROOT,
    _browser,  # noqa: F401  (the module's browser, for `page`)
    content,
    entry,
    experience_application,
    form_page,
    frozen,
    frozen_row,
    page,  # noqa: F401
    page_2,
    read,
    section,
    section_page,
    work,
)
from tests.test_workday_wizard import approvals, approve

LOCATION = "Springfield (fictional)"
ROLE = "Triage and intake.\r\nNight rota lead (fictional)."  # as a record may hold it
ROLE_SENT = "Triage and intake.\nNight rota lead (fictional)."  # as a text area holds it
CURRENT_D = CURRENT | {"location": LOCATION, "description": ROLE}
PAST_D = PAST | {"location": "River Town (fictional)"}  # no role description


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def lines(text: str) -> str:
    """A text area's value as a form sends it (CRLF) or holds it (LF), compared as LF."""
    return text.replace("\r\n", "\n")


# ---------------------------------------------------------------------------- capture

DESCRIPTION_REQUIRED = entry().replace(
    'name="work[__i__].description">', 'name="work[__i__].description" required>'
)


def without(template: str, part: str) -> str:
    """The template without one part's label and control."""
    return re.sub(rf'<label for="[a-z]__i__">[^<]*</label><(input|textarea)[^>]*name="work\[__i__\]'
                  rf'\.{part}"[^>]*>(\s*</textarea>)?', "", template)  # fmt: skip


def test_the_entry_s_location_and_role_description_are_named_with_the_section():
    schema, fields = read(form_page(section()))
    (sec,) = schema.sections
    assert sec.parts == ["description", "location"] and sec.required_parts == []
    assert workday.WORK_KEY not in fields and set(fields) == {"resume"}


@pytest.mark.parametrize("template, required", [
    (entry(loc=" required"), ["location"]),
    (entry(loc=' aria-required="true"'), ["location"]),
    (DESCRIPTION_REQUIRED, ["description"]),
], ids=["location-required", "location-aria-required", "description-required"])  # fmt: skip
def test_a_page_that_requires_them_is_read_not_refused(template, required):
    """Before D155 such a page was one required checkpoint (apply on the employer's site)."""
    schema, fields = read(form_page(section(), template))
    (sec,) = schema.sections
    assert sec.required_parts == required and workday.WORK_KEY not in fields


def test_an_entry_that_asks_neither_names_neither():
    template = without(without(entry(), "location"), "description")
    assert "location" not in template and "description" not in template
    schema, _ = read(form_page(section(), template))
    (sec,) = schema.sections
    assert sec.parts == [] and "parts" not in sec.model_dump()
    schema, _ = read(form_page(section(), without(entry(), "description")))
    assert schema.sections[0].parts == ["location"]


@pytest.mark.parametrize("kw", [
    {"kind": "education", "parts": ["location"]},
    {"parts": ["location", "description"]},  # not sorted
    {"parts": ["location", "location"]},
    {"parts": ["location"], "required_parts": ["description"]},
    {"parts": ["title"]},
], ids=["education", "unsorted", "twice", "required-not-asked", "unknown"])  # fmt: skip
def test_a_section_names_only_known_parts_sorted_and_once(kw):
    with pytest.raises(ValidationError):
        SectionSpec(**({"kind": "employment", "root": ROOT} | kw))


def test_the_parts_are_part_of_the_form_and_written_only_when_named():
    wizard = WizardSpec(pages=["My Information", "My Experience", "Review"])
    field = FormField(key="resume", label="Resume", type=FieldType.file, step="My Experience")

    def fp(**kw) -> str:
        sec = SectionSpec(kind="employment", root=ROOT, step="My Experience", **kw)
        return form_fingerprint(FormSchema(fields=[field], sections=[sec], wizard=wizard))

    fps = {fp(), fp(parts=["location"]), fp(parts=["description", "location"]),
           fp(parts=["location"], required_parts=["location"])}  # fmt: skip
    assert len(fps) == 4
    plain = SectionSpec(kind="employment", root=ROOT)
    assert plain.model_dump() == {"kind": "employment", "root": ROOT, "schools": [],
                                  "degrees": [], "disciplines": []}  # fmt: skip


# ---------------------------------------------------------------------------- resolution


def record(**kw) -> SimpleNamespace:
    return SimpleNamespace(**({"id": uuid.uuid4(), "version": 1, "employer": "Example Health",
                               "title": "Clinic Assistant", "start_date": datetime.date(2019, 1, 1),
                               "end_date": None, "is_current": True, "location": LOCATION,
                               "description": ROLE} | kw))  # fmt: skip


def test_your_record_s_location_and_role_description_are_resolved_as_written():
    row = ss.resolve_employment_row(record(), ("description", "location"))
    loc, role = row.fields["location"], row.fields["description"]
    assert (loc.status, loc.display, loc.value) == ("resolved", LOCATION, {"text": LOCATION})
    assert (role.status, role.display) == ("resolved", ROLE_SENT)  # line breaks as one LF
    assert loc.fact_refs[0]["field"] == "location" and role.fact_refs[0]["field"] == "description"


def test_a_section_that_does_not_ask_them_resolves_as_before():
    """Greenhouse's sections, and a Workday entry without the two parts."""
    row = ss.resolve_employment_row(record())
    assert set(row.fields) == {"company_name", "title", "start_date", "current", "end_date"}
    assert set(ss.resolve_employment_row(record(), ("location",)).fields) == {
        "company_name", "title", "start_date", "current", "end_date", "location"}  # fmt: skip


@pytest.mark.parametrize("blank", [None, "", "   ", "\n"])
def test_nothing_on_your_record_is_never_sent_and_never_guessed(blank):
    row = ss.resolve_employment_row(record(location=blank, description=blank),
                                    ("description", "location"))  # fmt: skip
    assert {row.fields[k].status for k in ("location", "description")} == {"omitted"}
    assert all(row.fields[k].display is None for k in ("location", "description"))


def test_a_part_the_page_requires_and_your_record_lacks_is_yours_to_add():
    row = ss.resolve_employment_row(record(location=None, description=None),
                                    ("description", "location"), ("location",))  # fmt: skip
    assert row.fields["location"].status == "needs_user"
    assert "requires a location" in row.fields["location"].explanation
    assert row.fields["description"].status == "omitted"


def test_a_location_with_a_line_break_is_yours_to_fix():
    row = ss.resolve_employment_row(record(location="Spring\nfield"), ("location",))
    assert row.fields["location"].status == "needs_user"
    assert "line break" in row.fields["location"].explanation


def test_a_section_asking_a_part_never_named_is_not_supported():
    result = ss.resolve_section("employment", [], parts=("salary",))
    assert not result.supported
    result = ss.resolve_section("employment", [], parts=("location",), required_parts=("title",))
    assert not result.supported


# ---------------------------------------------------------------------------- frozen content


def frozen_parts(location=LOCATION, description=ROLE_SENT, parts=("description", "location")):
    row = frozen_row()

    def part(text):
        if text is None:
            return {"status": "omitted", "value": None, "display": None}
        return {"status": "resolved", "value": {"text": text}, "display": text}

    row["fields"] |= {"location": part(location), "description": part(description)}
    row["fields"] = {k: v for k, v in row["fields"].items()
                     if k not in ("location", "description") or k in parts}  # fmt: skip
    return frozen([row], parts=list(parts))


def test_the_plan_enters_the_parts_your_record_holds():
    (row,) = ws.plan(frozen_parts()).rows
    ops = {op.field: op.value for op in row.ops}
    assert ops["location"] == LOCATION and ops["description"] == ROLE_SENT
    assert set(row.blank) == {f'{ROOT} [name="work[0].to"]'}


def test_the_plan_leaves_empty_what_your_record_does_not_hold():
    (row,) = ws.plan(frozen_parts(location=None, description=None)).rows
    assert not {"location", "description"} & {op.field for op in row.ops}
    assert set(row.blank) == {f'{ROOT} [name="work[0].{p}"]' for p in ("to", "location",
                                                                     "description")}  # fmt: skip


def test_a_section_frozen_before_d155_is_planned_as_before():
    (row,) = ws.plan(frozen([frozen_row()])).rows
    assert set(row.blank) == {f'{ROOT} [name="work[0].{p}"]' for p in ("to", "location",
                                                                     "description")}  # fmt: skip


@pytest.mark.parametrize("data", [
    {**frozen_parts(), "kind": "education"},
    frozen_parts() | {"parts": ["location", "description"]},
    frozen_parts() | {"parts": ["salary"]},
    frozen_parts() | {"parts": []},
    frozen_parts() | {"parts": "location"},
    frozen_parts() | {"parts": [1]},
    frozen_parts(parts=("location",)) | {"parts": []},
    frozen([frozen_parts()["rows"][0]]),  # the fields without the section naming them
    frozen_parts(parts=("description", "location")) | {"parts": ["location"]},
    frozen_parts(location="Spring\nfield"),
    frozen_parts(description="Carriage\rreturn"),
], ids=["education", "unsorted", "unknown", "empty", "not-a-list", "not-text", "empty-named",
        "unnamed", "description-unnamed", "location-line-break", "description-cr"])  # fmt: skip
def test_frozen_parts_it_cannot_enter_exactly_are_refused(data):
    with pytest.raises(gs.Refused):
        ws.plan(data)


def test_greenhouse_never_plans_a_section_that_names_parts():
    with pytest.raises(gs.Refused):
        gs.plan_content_section(frozen_parts() | {"root": "#employment-section"})


def test_the_package_schema_version_is_unchanged():
    """Only a section whose entry asks the parts carries them: every other package's content and
    hash are as before (SCHEMA_VERSION stays 3, as D149 left it)."""
    assert SCHEMA_VERSION == 3


# ---------------------------------------------------------------------------- through the runner


def test_your_location_and_role_description_are_sent_on_their_page(api, receiver):
    app_id = experience_application(api, receiver, records=(CURRENT_D, PAST_D))
    (sec,) = content(api, app_id)["sections"]
    assert sec["parts"] == ["description", "location"]
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = work(page_2(receiver.ledger()))
    assert sent["work[0].location"] == LOCATION and lines(sent["work[0].description"]) == ROLE_SENT
    assert sent["work[1].location"] == "River Town (fictional)"
    assert sent["work[1].description"] == ""  # not on the record: never sent


def test_a_page_that_requires_them_sends_yours(api, receiver):
    app_id = experience_application(
        api,
        receiver,
        "experience_parts_required",
        records=(CURRENT_D, PAST_D | {"description": "Ward rounds."}),
    )
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = work(page_2(receiver.ledger()))
    assert lines(sent["work[1].description"]) == "Ward rounds."
    assert receiver.ledger()["accepted"] == 1


def test_a_page_that_requires_one_your_record_lacks_blocks_approval(api, receiver):
    """Before D155 the form was refused when it was read (apply on the employer's site)."""
    app_id = experience_application(api, receiver, "experience_parts_required",
                                    records=(CURRENT_D, PAST_D), approved=False)  # fmt: skip
    c = content(api, app_id)
    keys = [k for k in c["unresolved"] if k.startswith("section:employment:")]
    assert len(keys) == 1 and keys[0].endswith(":description")
    assert approve(api, app_id).status_code != 200
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_edit_to_your_location_retires_the_approval(api, receiver):
    app_id = experience_application(api, receiver, records=(CURRENT_D,))
    (rec,) = api.get("/profile/employment").json()
    r = api.put(f"/profile/employment/{rec['id']}", json=CURRENT_D | {"location": "Elsewhere"})
    assert r.status_code == 200, r.text
    assert api.post(f"/profile/employment/{rec['id']}/approve").status_code == 200
    assert approvals(app_id) and all(a.invalidated_at is not None for a in approvals(app_id))
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert work(page_2(receiver.ledger()))["work[0].location"] == "Elsewhere"


def test_on_the_single_page_they_are_sent_too(api, receiver):
    app_id = experience_application(api, receiver, records=(CURRENT_D,), single=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert row["fields"]["work[0].location"] == LOCATION
    assert lines(row["fields"]["work[0].description"]) == ROLE_SENT


# ---------------------------------------------------------------------------- the page
# Last in the module: its browser (module-scoped) holds Playwright's synchronous API until the
# module ends, and the runner opens its own.


def test_both_are_entered_and_read_back_exactly(page):  # noqa: F811
    page.set_content(section_page())
    entries = ws.plan(frozen_parts())
    got = ws.apply(page, entries, ROOT)
    assert {"row": 0, "field": "location"} in got and {"row": 0, "field": "description"} in got
    assert ws.readback(page, entries, ROOT) == []
    assert page.locator('[name="work[0].location"]').input_value() == LOCATION
    assert page.locator('[name="work[0].description"]').input_value() == ROLE_SENT


def test_a_role_description_the_page_changes_is_found(page):  # noqa: F811
    page.set_content(section_page())
    entries = ws.plan(frozen_parts())
    ws.apply(page, entries, ROOT)
    page.evaluate("""() => { document.querySelector('[name="work[0].description"]').value
                             = 'Triage and intake.'; }""")  # fmt: skip
    assert ws.readback(page, entries, ROOT)


def test_one_your_record_does_not_hold_stays_empty_and_is_checked(page):  # noqa: F811
    page.set_content(section_page())
    entries = ws.plan(frozen_parts(location=None))
    ws.apply(page, entries, ROOT)
    assert page.locator('[name="work[0].location"]').input_value() == ""
    assert ws.readback(page, entries, ROOT) == []
    page.evaluate("""() => { document.querySelector('[name="work[0].location"]').value
                             = 'Parsed (fictional)'; }""")  # fmt: skip
    assert ws.readback(page, entries, ROOT)
