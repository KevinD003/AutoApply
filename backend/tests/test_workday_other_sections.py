"""D165: the Workday-style stand-in's sections of a kind NoEfforts does not fill (FIXTURE
ASSUMPTION FA10, fixtures/ats_receiver/workday_like.py: Languages, Websites and Skills) on the
wizard's My Experience page and on the single page. Before D165 any of them made the page's work
history one required checkpoint ("Work Experience"), so no such page could be applied to. Now one
the page does not require and that holds nothing is left empty: an optional field on its page
(`left_empty_section`), shown in the package as left empty, never touched; anything else about it
is that section's own checkpoint. What the page shows or asks there after approval is read again
with the rest of the form (D132) before anything is entered, before each Next and before the final
click.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real page was observed).
Synthetic candidate data only."""

import re
import sys
from pathlib import Path

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters.fixture_ats import FORM_CHANGED
from app.modules.preparation import package as pk
from app.modules.preparation import workday
from app.modules.preparation.forms import FieldType, FormField, form_fingerprint
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.providers.routing import form_checkpoint
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_package_contract import SHAPES, paths
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_experience import CURRENT as WORK_CURRENT
from tests.test_workday_experience import employment
from tests.test_workday_wizard import approve, draft_pages, drafts, posts, rows

KINDS = ("languages", "websites", "skills")  # FA10, the oracle's own copy
KEYS = [f"{k}_section" for k in KINDS]
LABELS = {"languages": "Languages", "websites": "Websites", "skills": "Skills"}
# An entry's control names (FA10's markup): what must never reach the employer here.
ENTRY = re.compile(r"(lang|web|skill)\[\d+\]\.[a-z_]+")


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def stand_in(variant: str | None = None, mode: str = "normal") -> str:
    """The stand-in's page as served, built by its own module (FA10)."""
    here = str(Path(__file__).resolve().parents[2] / "fixtures" / "ats_receiver")
    if here not in sys.path:
        sys.path.insert(0, here)
    import workday_like as wl

    cfg = {"mode": mode, "tamper": None, "wizard": variant, "page_check": None,
           "page_check_delay_ms": 800, "sends": None, "autosave": False}  # fmt: skip
    build = wl._wizard_page if variant else wl._form_page
    return build("examplehealth", "R-100001", "t", cfg).body.decode()


def fields_of(html: str) -> dict[str, FormField]:
    return {f.key: f for f in workday.extract_schema(html).fields}


def left_empty(f: FormField | None, label: str, step: str | None = "My Experience") -> bool:
    return f is not None and (f.type, f.required, f.widget, f.label, f.step) == (
        FieldType.unsupported, False, workday.LEFT_EMPTY, label, step)  # fmt: skip


def checkpoint(f: FormField | None, label: str) -> bool:
    why = workday.OTHER_REASON.format(label=label)
    return f is not None and (f.type, f.required, f.widget, f.label, f.unsupported_reason) == (
        FieldType.unsupported, True, None, label, why)  # fmt: skip


# ---------------------------------------------------------------------------- capture


def test_each_section_the_page_does_not_require_is_left_empty_on_its_page():
    schema = workday.extract_schema(stand_in("other_sections"))
    got = {f.key: f for f in schema.fields}
    assert all(left_empty(got.get(f"{k}_section"), LABELS[k]) for k in KINDS)
    assert schema.sections == [] and workday.WORK_KEY not in got
    assert not [k for k in got if ENTRY.fullmatch(k)]  # no entry, so no entry's control
    assert form_checkpoint(schema.model_dump(mode="json")) == []  # nothing for the route


def test_on_the_single_page_each_is_left_empty_with_no_page():
    got = fields_of(stand_in(mode="wd_other_sections"))
    assert all(left_empty(got.get(f"{k}_section"), LABELS[k], None) for k in KINDS)
    assert workday.WORK_KEY not in got


def test_these_sections_never_make_the_work_history_a_checkpoint():
    """Before D165 any of them was read as a work history section of another kind: the Work
    Experience checkpoint, on a page with no work history at all. Beside the Work Experience
    section, that section reads as before."""
    schema = workday.extract_schema(stand_in("other_sections_and_experience"))
    assert [(s.kind, s.step) for s in schema.sections] == [("employment", "My Experience")]
    got = {f.key: f for f in schema.fields}
    assert workday.WORK_KEY not in got
    assert all(left_empty(got.get(f"{k}_section"), LABELS[k]) for k in KINDS)


def test_a_section_of_a_kind_no_reader_takes_is_still_the_work_history_checkpoint():
    html = stand_in("other_sections").replace('data-wd-section="skills"',
                                              'data-wd-section="certifications"')  # fmt: skip
    got = fields_of(html)
    assert workday.WORK_KEY in got and "skills_section" not in got
    assert left_empty(got["languages_section"], "Languages")


def test_a_section_the_page_requires_is_its_own_checkpoint():
    got = fields_of(stand_in("other_sections_required"))
    assert checkpoint(got["languages_section"], "Languages")
    assert left_empty(got["websites_section"], "Websites")
    assert left_empty(got["skills_section"], "Skills")
    assert workday.WORK_KEY not in got


def test_an_entry_already_there_is_its_own_checkpoint():
    got = fields_of(stand_in("other_sections_entry_at_load"))
    assert checkpoint(got["languages_section"], "Languages")
    assert left_empty(got["skills_section"], "Skills")


LANG = '<div id="languages" role="group" aria-labelledby="languages-label" '
LANG_ADD = '<div data-wd-entries></div><button type="button" data-wd-add>Add</button></div>'
LANG_HEAD = '<h3 id="languages-label">Languages</h3>'


def in_languages(old: str, new: str):
    """A change inside the Languages section (FA10's markup) only."""

    def change(html: str) -> str:
        start = html.index(LANG)
        end = html.index(LANG_ADD, start) + len(LANG_ADD)
        section = html[start:end]
        assert old in section, old
        return html[:start] + section.replace(old, new, 1) + html[end:]

    return change


def languages_twice(html: str) -> str:
    start = html.index(LANG)
    end = html.index(LANG_ADD, start) + len(LANG_ADD)
    copy = html[start:end].replace('id="languages"', 'id="languages-2"')
    return html[:end] + copy + html[end:]


def languages_on_the_review_page(html: str) -> str:
    start = html.index(LANG)
    end = html.index(LANG_ADD, start) + len(LANG_ADD)
    section, html = html[start:end], html[:start] + html[end:]
    last = '<section data-step="Review" data-wizard-page="5" hidden>'
    assert last in html
    return html.replace(last, last + section, 1)


def languages_inside_websites(html: str) -> str:
    start = html.index(LANG)
    end = html.index(LANG_ADD, start) + len(LANG_ADD)
    section, html = html[start:end], html[:start] + html[end:]
    web = '<div data-wd-entries></div><button type="button" data-wd-add>Add</button></div>'
    at = html.index('data-wd-section="websites"')
    w = html.index(web, at)
    return html[:w] + section + html[w:]


NOT_LEFT_EMPTY = {
    "aria-required": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" aria-required="true"'
    ),
    "an asterisk in its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label">Languages *</h3>'
    ),
    "an asterisk anywhere in it": in_languages(
        LANG_ADD,
        LANG_ADD.replace(
            "<div data-wd-entries></div>", "<div data-wd-entries></div><span>*</span>"
        ),
    ),
    "two of a kind": languages_twice,
    "no id": in_languages('<div id="languages" role="group"', '<div role="group"'),
    "an id used twice": lambda h: in_languages(
        LANG_HEAD, LANG_HEAD + '<span id="languages"></span>'
    )(h),
    "hidden at load": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" hidden'
    ),
    "disabled at load": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" aria-disabled="true"'
    ),
    "no Add button": in_languages('<button type="button" data-wd-add>Add</button>', ""),
    "a second button": in_languages(LANG_HEAD, LANG_HEAD + '<button type="button">Help</button>'),
    "an Add that submits": in_languages(
        '<button type="button" data-wd-add>', '<button type="submit" data-wd-add>'
    ),
    "an Add that is an input": in_languages(
        '<button type="button" data-wd-add>Add</button>',
        '<input type="button" data-wd-add value="Add">',
    ),
    "an Add saying something else": in_languages(">Add</button>", ">Add a language</button>"),
    "a control in it": in_languages(LANG_HEAD, LANG_HEAD + '<input type="hidden" name="lang_x">'),
    "a text area in it": in_languages(
        LANG_HEAD,
        LANG_HEAD + '<label for="n1">Note</label><textarea id="n1" name="note"></textarea>',
    ),
    "something editable in it": in_languages(LANG_HEAD, LANG_HEAD + "<div contenteditable></div>"),
    "a custom control in it": in_languages(LANG_HEAD, LANG_HEAD + '<div role="textbox"></div>'),
    "a custom element in it": in_languages(LANG_HEAD, LANG_HEAD + "<wd-picker></wd-picker>"),
    "a frame in it": in_languages(LANG_HEAD, LANG_HEAD + '<iframe src="about:blank"></iframe>'),
    "a template in it": in_languages(LANG_HEAD, LANG_HEAD + "<template><input></template>"),
    "inside another section": languages_inside_websites,
    "on the review page": languages_on_the_review_page,
}


@pytest.mark.parametrize("change", sorted(NOT_LEFT_EMPTY))
def test_a_section_not_exactly_one_that_holds_nothing_is_its_own_checkpoint(change):
    """Never left out on a guess: anything about a section NoEfforts does not fill that it does
    not read exactly (required, two of a kind, not shown, holding anything but its Add, nested,
    on a page it cannot be left empty on) is that section's checkpoint: apply on the employer's
    site. The other sections are read as before."""
    got = fields_of(NOT_LEFT_EMPTY[change](stand_in("other_sections")))
    assert checkpoint(got.get("languages_section"), "Languages"), got.get("languages_section")
    assert workday.WORK_KEY not in got


def test_a_page_question_under_a_section_s_key_never_hides_it():
    """D165 review: the field left empty never replaces a question of the page that has its key
    (that question would then be left unread): the section's checkpoint replaces both."""
    html = in_languages(LANG_HEAD, LANG_HEAD)(stand_in("other_sections"))
    html = html.replace('<label for="exp_details">',
                        '<label for="ls">Languages</label><input id="ls" name="languages_section" '
                        'type="text"><label for="exp_details">', 1)  # fmt: skip
    got = fields_of(html)
    assert checkpoint(got["languages_section"], "Languages")
    assert len([f for f in workday.extract_schema(html).fields
                if f.key == "languages_section"]) == 1  # fmt: skip


def test_the_sections_are_part_of_the_form():
    """A section added, made required or given an entry since approval is another form (the
    fingerprint): D132's pause before anything is entered."""
    base = form_fingerprint(workday.extract_schema(stand_in("other_sections")))
    for variant in ("other_sections_required", "other_sections_entry_at_load"):
        assert form_fingerprint(workday.extract_schema(stand_in(variant))) != base
    without = workday.extract_schema(stand_in(None, "normal"))
    assert form_fingerprint(without) != form_fingerprint(
        workday.extract_schema(stand_in(mode="wd_other_sections")))  # fmt: skip


def test_a_field_left_empty_is_never_one_the_page_requires():
    with pytest.raises(ValueError, match="a section the page requires"):
        FormField(key="languages_section", label="Languages", type=FieldType.unsupported,
                  required=True, widget=workday.LEFT_EMPTY)  # fmt: skip
    with pytest.raises(ValueError, match="cannot be a left_empty_section control"):
        FormField(key="languages_section", label="Languages", type=FieldType.text,
                  widget=workday.LEFT_EMPTY)  # fmt: skip


# ---------------------------------------------------------------------------- the resolver


def test_a_section_left_empty_resolves_to_nothing_whatever_your_profile_holds():
    f = FormField(key="skills_section", label="Skills", type=FieldType.unsupported,
                  unsupported_reason=workday.LEFT_EMPTY_REASON.format(label="Skills"),
                  widget=workday.LEFT_EMPTY)  # fmt: skip
    from tests.test_resolver import profile

    r = resolve_field(f, Context(profile=profile(skills=["Phlebotomy (fictional)"])))
    assert (r.status, r.value, r.display, r.source) == ("blank_optional", None, None, "unresolved")
    assert (r.user_input_allowed, r.bankable, r.draftable) == (False, False, False)
    assert r.fact_refs == [] and "Phlebotomy" not in r.explanation
    assert r.explanation.startswith(
        "Left empty: NoEfforts does not fill this form's Skills section"
    )
    assert "apply on the employer's site" in r.explanation


# ---------------------------------------------------------------------------- the package


def application(api, receiver, variant="other_sections", *, single=False, approved=True,
                work=()) -> str:  # fmt: skip
    """The sections' variant switched on (a wizard variant, or the single page's mode), your
    approved work history when given, then a Workday-style application on a posting of its own,
    captured, answered and, when `approved`, approved."""
    receiver.config(**({"mode": "wd_other_sections"} if single else {"wizard": variant}))
    synthetic_candidate(api)
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


def test_the_package_shows_each_section_left_empty_and_needs_nothing_from_you(api, receiver):
    """Nothing to settle: each section is a row left empty, in the version-3 shape (a widget only
    where one applies), and nothing can be answered in its place."""
    app_id = application(api, receiver, approved=False)
    c = content(api, app_id)
    assert not c["unresolved"] and not c["validation_errors"]
    got = {a["key"]: a for a in c["answers"]}
    for k in KINDS:
        row = got[f"{k}_section"]
        assert (row["status"], row["value"], row["widget"], row["step"]) == (
            "blank_optional", None, workday.LEFT_EMPTY, "My Experience")  # fmt: skip
        assert row["explanation"].startswith(f"Left empty: NoEfforts does not fill this form's "
                                             f"{LABELS[k]} section")  # fmt: skip
    assert pk.SCHEMA_VERSION == 3 and paths(c) - SHAPES[3] <= {".answers[].widget", ".wizard"}
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "languages_section", "value": {"text": "English"}})  # fmt: skip
    assert r.status_code == 400
    assert approve(api, app_id).status_code == 200


def test_a_section_the_page_requires_blocks_approval(api, receiver):
    app_id = application(api, receiver, "other_sections_required", approved=False)
    c = content(api, app_id)
    assert "languages_section" in c["unresolved"]
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []


# ---------------------------------------------------------------------------- the ledger


def entries(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if ENTRY.fullmatch(k)}


def accepted(receiver) -> dict:
    (row,) = receiver.ledger()["acceptances"]
    return row["fields"]


def test_the_sections_are_left_empty_and_the_application_is_sent(api, receiver):
    app_id = application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 1
    assert all(entries(d["fields"]) == {} for d in drafts(led))
    assert entries(accepted(receiver)) == {}
    assert all(r["mismatched"] == 0 for r in rows(aid, "step"))


def test_on_the_single_page_they_are_left_empty_and_it_is_sent(api, receiver):
    app_id = application(api, receiver, single=True)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert entries(accepted(receiver)) == {}


def test_beside_them_your_work_history_is_sent(api, receiver):
    app_id = application(api, receiver, "other_sections_and_experience", work=(WORK_CURRENT,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (page_2,) = [d["fields"] for d in drafts(receiver.ledger()) if d["page"] == 2]
    assert page_2["work[0].title"] == "Clinic Assistant" and entries(page_2) == {}
    assert entries(accepted(receiver)) == {}


def test_an_entry_a_parsed_resume_adds_stops_before_its_page_is_sent(api, receiver):
    """The resume's parse adds a Skills entry with a value of its own: the form read again before
    page 2's Next is no longer the approved one, so the attempt stops with page 2 never sent."""
    app_id = application(api, receiver, "other_sections_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert attempt(aid).outcome_detail.endswith(f"Why: {FORM_CHANGED} (1 new field(s))")


def test_a_section_the_page_requires_once_the_resume_is_in_stops_before_its_page_is_sent(
    api, receiver
):
    """The page marks Languages required once the resume is uploaded: read again before page
    2's Next, the section is no longer one left empty, so the attempt stops, page 2 never sent."""
    app_id = application(api, receiver, "other_sections_required_late")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert attempt(aid).outcome_detail.endswith(f"Why: {FORM_CHANGED}")


@pytest.mark.parametrize("now", ["other_sections_required", "other_sections_entry_at_load"])
def test_a_section_changed_after_approval_pauses_before_anything_is_entered(api, receiver, now):
    app_id = application(api, receiver)
    receiver.config(wizard=now)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
