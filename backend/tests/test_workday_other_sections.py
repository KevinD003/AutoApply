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
from tests.test_workday_education import BACHELOR, MASTER, education
from tests.test_workday_education import SENT as EDU_SENT
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


def test_on_the_single_page_each_is_left_empty_on_its_section():
    """D165 review: on the single page a field's page is the page's own section, as for its
    other questions (the generic extractor's `data-step`), so the review page groups them so."""
    got = fields_of(stand_in(mode="wd_other_sections"))
    assert all(left_empty(got.get(f"{k}_section"), LABELS[k]) for k in KINDS)
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


def test_beside_the_education_section_both_read_as_before():
    """D165 review: with D163's Education section on the same page."""
    schema = workday.extract_schema(stand_in("other_sections_and_education"))
    assert [(s.kind, s.step) for s in schema.sections] == [("education", "My Experience")]
    got = {f.key: f for f in schema.fields}
    assert workday.EDUCATION_KEY not in got and workday.WORK_KEY not in got
    assert all(left_empty(got.get(f"{k}_section"), LABELS[k]) for k in KINDS)


def test_a_section_of_a_kind_no_reader_takes_is_still_the_work_history_checkpoint():
    html = stand_in("other_sections").replace('data-wd-section="skills"',
                                              'data-wd-section="certifications"')  # fmt: skip
    got = fields_of(html)
    assert workday.WORK_KEY in got and "skills_section" not in got
    assert left_empty(got["languages_section"], "Languages")


def test_on_a_wizard_refused_each_is_a_checkpoint():
    """D165 review: a wizard NoEfforts does not drive (here, page 1 without its Next) is the
    several-pages checkpoint, and none of its sections is left empty."""
    html = stand_in("other_sections").replace(
        '<button type="button" data-wizard-next>Save and Continue</button>\n</section>\n'
        '<section data-step="My Experience"',
        '</section>\n<section data-step="My Experience"', 1)  # fmt: skip
    got = fields_of(html)
    assert workday.MULTI_STEP_KEY in got
    assert all(checkpoint(got.get(f"{k}_section"), LABELS[k]) for k in KINDS)


def test_a_section_the_page_requires_is_its_own_checkpoint():
    got = fields_of(stand_in("other_sections_required"))
    assert checkpoint(got["languages_section"], "Languages")
    assert left_empty(got["websites_section"], "Websites")
    assert left_empty(got["skills_section"], "Skills")
    assert workday.WORK_KEY not in got


def test_an_entry_already_there_is_its_own_checkpoint_and_never_questions():
    got = fields_of(stand_in("other_sections_entry_at_load"))
    assert checkpoint(got["languages_section"], "Languages")
    assert left_empty(got["skills_section"], "Skills")
    assert not [k for k in got if ENTRY.fullmatch(k)]  # review: the section's, never questions


LANG = '<div id="languages" role="group" aria-labelledby="languages-label" '
LANG_ADD = '<div data-wd-entries></div><button type="button" data-wd-add>Add</button></div>'
LANG_HEAD = '<h3 id="languages-label">Languages</h3>'
ADD = '<button type="button" data-wd-add>Add</button>'


def bounds(html: str) -> tuple[int, int]:
    start = html.index(LANG)
    return start, html.index(LANG_ADD, start) + len(LANG_ADD)


def in_languages(old: str, new: str):
    """A change inside the Languages section (FA10's markup) only."""

    def change(html: str) -> str:
        start, end = bounds(html)
        section = html[start:end]
        assert old in section, old
        return html[:start] + section.replace(old, new, 1) + html[end:]

    return change


def around_languages(before: str, after: str):
    """The Languages section wrapped (FA10's markup)."""

    def change(html: str) -> str:
        start, end = bounds(html)
        return html[:start] + before + html[start:end] + after + html[end:]

    return change


def before_languages(markup: str):
    def change(html: str) -> str:
        start, _ = bounds(html)
        return html[:start] + markup + html[start:]

    return change


def languages_twice(html: str) -> str:
    """A second Languages section after the first, empty as built and named by its own heading,
    but marked required: only the rule of one section of a kind sees it (D165's removal runs)."""
    start, end = bounds(html)
    copy = (html[start:end].replace('id="languages"', 'id="languages-2"')
            .replace("languages-label", "languages-label-2")
            .replace(">Languages</h3>", ">Languages *</h3>"))  # fmt: skip
    return html[:end] + copy + html[end:]


def languages_on_the_review_page(html: str) -> str:
    start, end = bounds(html)
    section, html = html[start:end], html[:start] + html[end:]
    last = '<section data-step="Review" data-wizard-page="5" hidden>'
    assert last in html
    return html.replace(last, last + section, 1)


def heading_outside(html: str) -> str:
    """The heading that names the section moved just before it, marked required there."""
    html = in_languages(LANG_HEAD, "")(html)
    return before_languages('<h3 id="languages-label">Languages *</h3>')(html)


def custom_element_section(html: str) -> str:
    start, end = bounds(html)
    section = html[start:end]
    section = "<wd-section" + section[len("<div") : -len("</div>")] + "</wd-section>"
    return html[:start] + section + html[end:]


def after_the_form(markup: str):
    def change(html: str) -> str:
        assert html.count("</form>") == 1
        return html.replace("</form>", "</form>" + markup, 1)

    return change


NOT_LEFT_EMPTY = {
    # a required mark, however the page writes it (review)
    "aria-required": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" aria-required="true"'
    ),
    "required on it": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" required'
    ),
    "data-required on it": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" data-required="true"'
    ),
    "a name of its own": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" aria-label="Languages *"'
    ),
    "a title": in_languages(
        'data-wd-section="languages"', 'data-wd-section="languages" title="Required"'
    ),
    "an asterisk in its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label">Languages *</h3>'
    ),
    "(required) in its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label">Languages (required)</h3>'
    ),
    "another asterisk in its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label">Languages \u2217</h3>'
    ),
    "a mark inside its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label">Languages<abbr title="required"></abbr></h3>'
    ),
    "aria-required on its heading": in_languages(
        LANG_HEAD, '<h3 id="languages-label" aria-required="true">Languages</h3>'
    ),
    "its heading outside it": heading_outside,
    "named by a heading outside it": lambda h: in_languages(
        'aria-labelledby="languages-label"', 'aria-labelledby="languages-required"'
    )(before_languages('<h3 id="languages-required">Languages *</h3>')(h)),
    "a heading that is not one": in_languages(
        LANG_HEAD, '<span id="languages-label">Languages</span>'
    ),
    "another role": in_languages('role="group"', 'role="region"'),
    "its heading's id used twice": before_languages('<span id="languages-label"></span>'),
    "aria-required around it": around_languages('<div aria-required="true">', "</div>"),
    "required around it": around_languages("<fieldset required>", "</fieldset>"),
    "an attribute written twice": in_languages(
        '<button type="button" data-wd-add>', '<button type="submit" type="button" data-wd-add>'
    ),
    # not the empty section NoEfforts reads
    "two of a kind": languages_twice,
    "a custom element": custom_element_section,
    "hidden at load": around_languages("<div hidden>", "</div>"),
    "disabled at load": around_languages('<div aria-disabled="true">', "</div>"),
    "no Add button": in_languages(ADD, ""),
    "a second button": in_languages(LANG_HEAD, LANG_HEAD + '<button type="button">Help</button>'),
    "an Add that is an input": in_languages(ADD, '<input type="button" data-wd-add value="Add">'),
    "an Add that is not a button": in_languages(ADD, '<div type="button" data-wd-add>Add</div>'),
    "an Add with more to it": in_languages(
        ADD, '<button type="button" data-wd-add name="lx">Add</button>'
    ),
    "an Add holding an element": in_languages(
        ADD, '<button type="button" data-wd-add><span>Add</span></button>'
    ),
    "an entries list that is not a div": in_languages(
        "<div data-wd-entries></div>", "<span data-wd-entries></span>"
    ),
    "an entries list with more to it": in_languages(
        "<div data-wd-entries></div>", '<div data-wd-entries data-count="0"></div>'
    ),
    "an Add that submits": in_languages(ADD, ADD.replace('type="button"', 'type="submit"')),
    "Add Another": in_languages(">Add</button>", ">Add Another</button>"),
    "text in it": in_languages(
        "<div data-wd-entries></div>", "<div data-wd-entries>English (fluent)</div>"
    ),
    "a control in it": in_languages(LANG_HEAD, LANG_HEAD + '<input type="hidden" name="lx">'),
    "something editable in it": in_languages(LANG_HEAD, LANG_HEAD + "<div contenteditable></div>"),
    "a custom control in it": in_languages(LANG_HEAD, LANG_HEAD + '<div role="textbox"></div>'),
    "a custom element in it": in_languages(LANG_HEAD, LANG_HEAD + "<wd-picker></wd-picker>"),
    "a frame in it": in_languages(LANG_HEAD, LANG_HEAD + '<iframe src="about:blank"></iframe>'),
    "a script in it": in_languages(LANG_HEAD, LANG_HEAD + "<script>window.x = 1</script>"),
    "a template in it": in_languages(LANG_HEAD, LANG_HEAD + "<template><input></template>"),
    "inside another section": lambda h: moved_into(h, LANG, WEB),
    "on the review page": languages_on_the_review_page,
    # something in the form named as one of its entries, or under its key (review)
    "an entry's hidden value before it": before_languages(
        '<input type="hidden" name="lang[0].language" value="lang-en">'
    ),
    "an entry's empty hidden field": before_languages(
        '<input type="hidden" name="lang[0].language" value="">'
    ),
    "an entry's control beside it": lambda h: before_languages(
        '<label for="l0">Language</label><input id="l0" name="lang[0].language" type="text">'
    )(h),
    "an entry's control given from outside the form": after_the_form(
        '<input type="hidden" form="workday-application" name="lang[0].language" value="x">'
    ),
    "a hidden field under its key": before_languages(
        '<input type="hidden" name="languages_section" value="x">'
    ),
}
# On the wizard a submit button off its last page refuses the whole wizard (D142), every section on
# it then a checkpoint: this case is read on the single page.
ON_THE_SINGLE_PAGE = {"an attribute written twice", "an Add that submits"}


@pytest.mark.parametrize("change", sorted(NOT_LEFT_EMPTY))
def test_a_section_not_exactly_its_empty_self_is_its_own_checkpoint(change):
    """Never left out on a guess: anything about a section NoEfforts does not fill that it does
    not read exactly (a required mark however written, a name or a heading of another text,
    two of a kind, not shown, anything in it but its heading, empty list and plain Add, nested,
    on a page it cannot be left empty on, anything in the form named as one of its entries or
    under its key) is that section's checkpoint: apply on the employer's site. A section the
    change leaves alone is read as before."""
    html = stand_in(mode="wd_other_sections") if change in ON_THE_SINGLE_PAGE else stand_in(
        "other_sections")  # fmt: skip
    got = fields_of(NOT_LEFT_EMPTY[change](html))
    assert checkpoint(got.get("languages_section"), "Languages"), got.get("languages_section")
    assert left_empty(got.get("skills_section"), "Skills")
    assert workday.WORK_KEY not in got and workday.MULTI_STEP_KEY not in got
    assert not [k for k in got if ENTRY.fullmatch(k)]


def test_a_kind_named_with_no_section_is_its_checkpoint():
    """D165 review: a control named as an entry of a kind whose section the page does not show
    is never a question of its own, nor left out silently: that kind's checkpoint."""
    html = stand_in(mode="normal").replace(
        "</form>", '<input type="hidden" name="skill[0].name" value="x"></form>', 1
    )
    got = fields_of(html)
    assert checkpoint(got.get("skills_section"), "Skills")
    assert "languages_section" not in got and "skill[0].name" not in got


WEB = '<div id="websites" role="group"'
WORK = '<div id="work-experience"'


def moved_into(html: str, inner: str, outer: str) -> str:
    """The section that starts `inner` moved inside the one that starts `outer`, before its
    entries (FA7's and FA10's markup: each section ends LANG_ADD)."""
    start = html.index(inner)
    end = html.index(LANG_ADD, start) + len(LANG_ADD)
    moved, html = html[start:end], html[:start] + html[end:]
    at = html.index(LANG_ADD, html.index(outer))
    return html[:at] + moved + html[at:]


@pytest.mark.parametrize(
    "variant, inner, outer, keys",
    [("other_sections", LANG, WEB, ("languages_section", "websites_section")),
     ("other_sections_and_experience", LANG, WORK, ("languages_section", workday.WORK_KEY)),
     ("other_sections_and_experience", WORK, LANG, ("languages_section", workday.WORK_KEY))],
    ids=["languages-inside-websites", "languages-inside-work", "work-inside-languages"],
)  # fmt: skip
def test_a_section_inside_another_is_both_checkpoints(variant, inner, outer, keys):
    """As D163 for Education: no reader takes a section nested in another, either way, and no
    work history is filled inside a section NoEfforts leaves empty."""
    schema = workday.extract_schema(moved_into(stand_in(variant), inner, outer))
    got = {f.key: f for f in schema.fields}
    assert schema.sections == []
    for key in keys:
        assert got[key].required and got[key].type == FieldType.unsupported, key
        assert got[key].widget is None


def test_a_page_question_under_a_section_s_key_never_hides_it():
    """The field left empty never replaces a question of the page that has its key (that question
    would then be left unread): a control named so is that kind's checkpoint, which replaces the
    question. (A page question's key is its control's name, or `aria:` and an id: no other can
    have the field's key.)"""
    html = stand_in("other_sections").replace('<label for="exp_details">',
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


def application(api, receiver, variant="other_sections", *, mode=None, approved=True,
                work=(), schooling=()) -> str:  # fmt: skip
    """The sections' variant switched on (a wizard variant, or the single page's mode), your
    approved work history when given, then a Workday-style application on a posting of its own,
    captured, answered and, when `approved`, approved."""
    receiver.config(**({"mode": mode} if mode else {"wizard": variant}))
    synthetic_candidate(api)
    for record in work:
        employment(api, record)
    for record in schooling:
        education(api, record)
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
    app_id = application(api, receiver, mode="wd_other_sections")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert entries(accepted(receiver)) == {}


def test_beside_them_your_work_history_is_sent(api, receiver):
    app_id = application(api, receiver, "other_sections_and_experience", work=(WORK_CURRENT,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (page_2,) = [d["fields"] for d in drafts(receiver.ledger()) if d["page"] == 2]
    assert page_2["work[0].title"] == "Clinic Assistant" and entries(page_2) == {}
    assert entries(accepted(receiver)) == {}


def test_beside_them_your_education_is_sent(api, receiver):
    """D165 review: with D163's Education section on the same page."""
    app_id = application(api, receiver, "other_sections_and_education",
                         schooling=(MASTER, BACHELOR))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (page_2,) = [d["fields"] for d in drafts(receiver.ledger()) if d["page"] == 2]
    assert {k: v for k, v in page_2.items() if k.startswith("edu[")} == EDU_SENT
    assert entries(page_2) == {} and entries(accepted(receiver)) == {}


def test_a_hidden_value_the_parse_keeps_outside_a_section_stops_before_its_page_is_sent(
    api, receiver
):
    """D165 review (the blocker): the resume's parse keeps a Skills value in a hidden field of
    its own, outside the section. No question shows it (a hidden field is none) and the form's
    own reads of what it sends leave hidden fields alone (D160): only D165's rule, that nothing
    in the form is named as one of the section's entries, read again before page 2's Next,
    sees it. The attempt stops, page 2 never sent."""
    app_id = application(api, receiver, "other_sections_hidden_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert attempt(aid).outcome_detail.endswith(f"Why: {FORM_CHANGED}")


def test_on_the_single_page_a_hidden_value_the_parse_keeps_stops_before_the_final_click(
    api, receiver
):
    """D165 review: the same on the single page, read again after filling, before the final
    click: nothing is submitted."""
    app_id = application(api, receiver, mode="wd_other_sections_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") not in ("confirmed", "unknown")
    led = receiver.ledger()
    assert led["accepted"] == 0 and posts(led, "/apply") == 0
    assert FORM_CHANGED in attempt(aid).outcome_detail


def test_an_entry_a_parsed_resume_adds_stops_before_its_page_is_sent(api, receiver):
    """The resume's parse adds a Skills entry with a value of its own: the form read again before
    page 2's Next is no longer the approved one, so the attempt stops with page 2 never sent.
    (Review: the entry's controls are never new questions; D165's own rule makes the section
    that kind's checkpoint, so the stop names no new field.)"""
    app_id = application(api, receiver, "other_sections_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert attempt(aid).outcome_detail.endswith(f"Why: {FORM_CHANGED}")


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
