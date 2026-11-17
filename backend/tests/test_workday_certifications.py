"""D167: the Workday-style stand-in's Certifications section (FIXTURE ASSUMPTION FA12,
fixtures/ats_receiver/workday_like.py) filled from your approved licences and certifications.
Before D167 a Certifications section was a section of a kind no reader took: the work-history
checkpoint for the whole page, so no such page could be applied to. Now it is read as a
certifications section, its rows your approved credentials, one each: the name as written and
the issued and expiration dates as MM/YYYY where your record holds them (never a number: NoEfforts
holds none, and the entry's box for it is left empty), shown on the review page and diffed,
entered entry by entry and read back as the rest of a section (D149's machinery). Anything about
the section NoEfforts does not read exactly is its own checkpoint, as D166 made it for Websites.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (Workday's job application templates
list Certifications among their sections, search-reported; no real Certifications section was
observed). Synthetic candidate data only."""

import re
import uuid
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_sections as gs
from app.modules.execution.adapters import workday as wd_adapter
from app.modules.execution.adapters import workday_sections as ws
from app.modules.execution.adapters.fixture_ats import FORM_CHANGED
from app.modules.preparation import package as pk
from app.modules.preparation import structured_sections as ss
from app.modules.preparation import workday
from app.modules.preparation.forms import FieldType, FormField, form_fingerprint
from app.modules.profiles.models import Approval, Credential
from app.modules.providers.routing import form_checkpoint
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_package_contract import SHAPES, paths
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_education import BACHELOR, MASTER, education
from tests.test_workday_education import SENT as EDU_SENT
from tests.test_workday_experience import CURRENT as WORK_CURRENT
from tests.test_workday_experience import employment
from tests.test_workday_other_sections import LANG, fields_of, left_empty, moved_into
from tests.test_workday_other_sections import stand_in as _stand_in
from tests.test_workday_wizard import approve, draft_pages, drafts, posts, rows

# Your licences and certifications (synthetic), as the profile holds them.
RN = {"name": "Registered Nurse licence (fictional board)", "issued_on": "2019-04-15",
      "expires_on": "2027-04-30"}  # fmt: skip
BLS = {"name": "Basic Life Support (fictional)", "issued_on": "2024-01-10",
       "expires_on": "2026-01-31"}  # fmt: skip  # expired: sent with its expiration date
FORKLIFT = {"name": "Forklift operator certificate (fictional)"}  # no date at all
CREDS = (RN, FORKLIFT, BLS)  # added in this order: sent newest issued first, undated last
NAMES = [BLS["name"], RN["name"], FORKLIFT["name"]]
SENT = {
    "cert[0].name": BLS["name"], "cert[0].number": "", "cert[0].issued": "01/2024",
    "cert[0].expires": "01/2026",
    "cert[1].name": RN["name"], "cert[1].number": "", "cert[1].issued": "04/2019",
    "cert[1].expires": "04/2027",
    "cert[2].name": FORKLIFT["name"], "cert[2].number": "", "cert[2].issued": "",
    "cert[2].expires": "",
}  # fmt: skip
# FA12: what the page keeps, adds or writes once a certification is typed.
UNAPPROVED = "Unapproved Certification (fictional)"
UNAPPROVED_NUMBER = "X-0000 (fictional)"
CERT = re.compile(r"cert\[\d+\]\.[a-z_]+")  # an entry's control names (FA12's markup)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def stand_in(variant: str | None = "certifications_and_other_sections", mode: str = "normal"):
    return _stand_in(variant, mode)


def certs_of(schema) -> list[tuple[str, str, str | None, bool]]:
    return [(s.kind, s.root, s.step, s.required) for s in schema.sections
            if s.kind == "certifications"]  # fmt: skip


def checkpoint(f: FormField | None) -> bool:
    why = workday.CERTIFICATIONS_REASON
    return f is not None and (f.type, f.required, f.widget, f.label, f.unsupported_reason) == (
        FieldType.unsupported, True, None, "Certifications", why)  # fmt: skip


def entry(i: str = "0", n: str = "1") -> str:
    """FA12's entry, the oracle's own copy (`test_the_oracle_s_entry_is_the_stand_in_s`)."""
    return (f'<div data-wd-entry="{i}"><h4>Certifications {n}</h4>'
            f'<label for="cert-{i}-name">Certification</label>'
            f'<input id="cert-{i}-name" name="cert[{i}].name" type="text" required>'
            f'<label for="cert-{i}-number">Certification Number</label>'
            f'<input id="cert-{i}-number" name="cert[{i}].number" type="text">'
            f'<label for="cert-{i}-issued">Issued Date</label>'
            f'<input id="cert-{i}-issued" name="cert[{i}].issued" type="text" '
            'placeholder="MM/YYYY">'
            f'<label for="cert-{i}-expires">Expiration Date</label>'
            f'<input id="cert-{i}-expires" name="cert[{i}].expires" type="text" '
            'placeholder="MM/YYYY"></div>')  # fmt: skip


ENTRY_0 = entry()
CERTS = '<div id="certifications" role="group"'
SKILLS = '<div id="skills" role="group"'
HEAD = '<h3 id="certifications-label">Certifications</h3>'
ADD = '<button type="button" data-wd-add>Add</button>'
NAME_BOX = '<input id="cert-__i__-name" name="cert[__i__].name" type="text" required>'
NUMBER_BOX = '<input id="cert-__i__-number" name="cert[__i__].number" type="text">'
NUMBER_PAIR = '<label for="cert-__i__-number">Certification Number</label>' + NUMBER_BOX
ISSUED_BOX = ('<input id="cert-__i__-issued" name="cert[__i__].issued" type="text" '
              'placeholder="MM/YYYY">')  # fmt: skip


def at0(markup: str) -> str:
    """A template part as entry 0 shows it."""
    return markup.replace("__i__", "0")


# ---------------------------------------------------------------------------- capture


def test_the_oracle_s_entry_is_the_stand_in_s():
    html = stand_in("certifications_entry_at_load")
    assert ENTRY_0 in html
    assert f'<template id="certifications-entry">{entry("__i__", "__n__")}</template>' in html


def test_the_certifications_section_is_read_as_one_filled_from_your_licences_and_certifications():
    """No longer the work-history checkpoint for the whole page: a certifications section on its
    page, which the page does not require; its entries' controls are never questions, the
    sections beside it read as before, and the route has nothing to hold."""
    schema = workday.extract_schema(stand_in())
    assert certs_of(schema) == [("certifications", "#certifications", "My Experience", False)]
    assert [s.kind for s in schema.sections] == ["websites", "certifications"]
    got = {f.key: f for f in schema.fields}
    assert "certifications_section" not in got and workday.WORK_KEY not in got
    assert not [k for k in got if CERT.fullmatch(k)]
    assert left_empty(got["languages_section"], "Languages")
    assert left_empty(got["skills_section"], "Skills")
    assert form_checkpoint(schema.model_dump(mode="json")) == []


def test_on_the_single_page_it_is_read_on_no_page():
    schema = workday.extract_schema(stand_in(None, "wd_certifications"))
    assert certs_of(schema) == [("certifications", "#certifications", None, False)]
    assert "certifications_section" not in {f.key for f in schema.fields}


def test_one_the_page_requires_is_read_as_required():
    """FA12: the page's own mark of a required section (`aria-required="true"`, and an asterisk
    after the heading's name): NoEfforts then must enter at least one."""
    schema = workday.extract_schema(stand_in("certifications_required"))
    assert certs_of(schema) == [("certifications", "#certifications", "My Experience", True)]


def test_an_empty_entry_already_there_is_read_as_the_section():
    schema = workday.extract_schema(stand_in("certifications_entry_at_load"))
    assert certs_of(schema) == [("certifications", "#certifications", "My Experience", False)]
    assert not [f.key for f in schema.fields if CERT.fullmatch(f.key)]


def test_beside_work_experience_and_education_each_is_read():
    schema = workday.extract_schema(stand_in("certifications_and_experience"))
    assert [(s.kind, s.step) for s in schema.sections] == [
        ("employment", "My Experience"), ("education", "My Experience"),
        ("certifications", "My Experience")]  # fmt: skip
    got = {f.key for f in schema.fields}
    assert not {workday.WORK_KEY, workday.EDUCATION_KEY, "certifications_section"} & got


def test_the_section_is_part_of_the_form():
    """Made required, or added or taken away since approval: another form (the fingerprint),
    D132's pause before anything is entered. An empty entry shown since is the same form, as for
    D149's work history: it is filled in place, or, with nothing for it, a stop."""
    base = form_fingerprint(workday.extract_schema(stand_in("certifications")))
    assert form_fingerprint(workday.extract_schema(stand_in("certifications_required"))) != base
    assert form_fingerprint(workday.extract_schema(stand_in("certifications_entry_at_load"))) == (
        base)  # fmt: skip
    html = stand_in("certifications")
    start, end = bounds(html)
    assert form_fingerprint(workday.extract_schema(html[:start] + html[end:])) != base


def bounds(html: str) -> tuple[int, int]:
    start = html.index(CERTS)
    return start, html.index("</button></div>", start) + len("</button></div>")


def in_certs(old: str, new: str):
    """A change inside the Certifications section (FA12's markup) only."""

    def change(html: str) -> str:
        start, end = bounds(html)
        section = html[start:end]
        assert old in section, old
        return html[:start] + section.replace(old, new, 1) + html[end:]

    return change


def around_certs(before: str, after: str):
    def change(html: str) -> str:
        start, end = bounds(html)
        return html[:start] + before + html[start:end] + after + html[end:]

    return change


def before_certs(markup: str):
    def change(html: str) -> str:
        start, _ = bounds(html)
        return html[:start] + markup + html[start:]

    return change


def in_template(old: str, new: str):
    """A change inside the section's entry template (outside the form)."""

    def change(html: str) -> str:
        start = html.index('<template id="certifications-entry">')
        end = html.index("</template>", start)
        part = html[start:end]
        assert old in part, old
        return html[:start] + part.replace(old, new, 1) + html[end:]

    return change


def with_entry(markup: str, add: str = "Add Another"):
    """An entry already in the section at load, and its button's text."""
    return lambda html: in_certs(
        "<div data-wd-entries></div>" + ADD,
        f"<div data-wd-entries>{markup}</div>" + ADD.replace(">Add<", f">{add}<"),
    )(html)


def changed_entry(old: str, new: str, *, count: int = 1):
    """Entry 0, at load, with one change."""
    assert ENTRY_0.count(old) >= count, old
    return with_entry(ENTRY_0.replace(old, new, count))


def after_the_form(markup: str):
    def change(html: str) -> str:
        assert html.count("</form>") == 1
        return html.replace("</form>", "</form>" + markup, 1)

    return change


def certs_twice(html: str) -> str:
    """A second Certifications section after the first, exactly as built: only the rule of one
    section of a kind sees it."""
    start, end = bounds(html)
    copy = (html[start:end].replace('id="certifications"', 'id="certifications-2"')
            .replace("certifications-label", "certifications-label-2"))  # fmt: skip
    return html[:end] + copy + html[end:]


def on_the_review_page(html: str) -> str:
    start, end = bounds(html)
    section, html = html[start:end], html[:start] + html[end:]
    last = '<section data-step="Review" data-wizard-page="5" hidden>'
    assert last in html
    return html.replace(last, last + section, 1)


def custom_element_section(html: str) -> str:
    start, end = bounds(html)
    section = html[start:end]
    section = "<wd-section" + section[len("<div") : -len("</div>")] + "</wd-section>"
    return html[:start] + section + html[end:]


def heading_outside(html: str) -> str:
    html = in_certs(HEAD, "")(html)
    return before_certs(HEAD)(html)


def template_in_a_noscript(html: str) -> str:
    start = html.index('<template id="certifications-entry">')
    end = html.index("</template>", start) + len("</template>")
    return html[:start] + "<noscript>" + html[start:end] + "</noscript>" + html[end:]


def template_inside_the_form(html: str) -> str:
    start = html.index('<template id="certifications-entry">')
    end = html.index("</template>", start) + len("</template>")
    template, html = html[start:end], html[:start] + html[end:]
    return before_certs(template)(html)


def dates_swapped(markup: str) -> str:
    """The Issued and Expiration Dates' labels and boxes in the other order."""
    i = markup.index('<label for="cert-0-issued">')
    j = markup.index('<label for="cert-0-expires">')
    k = markup.index("</div>", j)
    return markup[:i] + markup[j:k] + markup[i:j] + markup[k:]


NOT_READ = {
    # a required mark the stand-in does not write, or written otherwise (D165's lesson)
    "required on it": in_certs('data-wd-section="certifications"',
                               'data-wd-section="certifications" required'),
    "data-required on it": in_certs('data-wd-section="certifications"',
                                    'data-wd-section="certifications" data-required="true"'),
    "aria-required false": in_certs('data-wd-section="certifications"',
                                    'data-wd-section="certifications" aria-required="false"'),
    "aria-required in capitals": lambda h: in_certs(
        'data-wd-section="certifications"',
        'data-wd-section="certifications" aria-required="TRUE"')(
        in_certs(HEAD, '<h3 id="certifications-label">Certifications *</h3>')(h)),
    "aria-required without its asterisk": in_certs(
        'data-wd-section="certifications"',
        'data-wd-section="certifications" aria-required="true"'),
    "an asterisk without aria-required": in_certs(
        HEAD, '<h3 id="certifications-label">Certifications *</h3>'),
    "(required) in its heading": in_certs(
        HEAD, '<h3 id="certifications-label">Certifications (required)</h3>'),
    "another asterisk in its heading": in_certs(
        HEAD, '<h3 id="certifications-label">Certifications \u2217</h3>'),
    "a mark inside its heading": in_certs(
        HEAD, '<h3 id="certifications-label">Certifications<abbr title="required"></abbr></h3>'),
    "aria-required on its heading": in_certs(
        HEAD, '<h3 id="certifications-label" aria-required="true">Certifications</h3>'),
    "its heading outside it": heading_outside,
    "named by a heading outside it": lambda h: in_certs(
        'aria-labelledby="certifications-label"', 'aria-labelledby="certifications-required"')(
        before_certs('<h3 id="certifications-required">Certifications *</h3>')(h)),
    "aria-required around it": around_certs('<div aria-required="true">', "</div>"),
    "required around it": around_certs("<fieldset required>", "</fieldset>"),
    "a name of its own": in_certs('data-wd-section="certifications"',
                                  'data-wd-section="certifications" aria-label="Certifications *"'),
    "a title": in_certs('data-wd-section="certifications"',
                        'data-wd-section="certifications" title="Required"'),
    # not the section as the stand-in builds it
    "another role": in_certs('role="group"', 'role="region"'),
    "a heading that is not one": in_certs(HEAD,
                                          '<span id="certifications-label">Certifications</span>'),
    "a heading of another text": in_certs(HEAD,
                                          '<h3 id="certifications-label">Certificates</h3>'),
    "its heading's id used twice": before_certs('<span id="certifications-label"></span>'),
    "its id used twice": before_certs('<span id="certifications"></span>'),
    "an id it cannot be found by": lambda h: h.replace('id="certifications" role="group"',
                                                       'id="certi fications" role="group"', 1),
    "two of a kind": certs_twice,
    "a custom element": custom_element_section,
    "hidden at load": around_certs("<div hidden>", "</div>"),
    # never rendered, or inert (D166's review)
    "inside a template in the form": around_certs("<template>", "</template>"),
    "inside a noscript in the form": around_certs("<noscript>", "</noscript>"),
    "under an inert element": around_certs("<div inert>", "</div>"),
    "its template inside a noscript": template_in_a_noscript,
    "named by an empty id": lambda h: in_certs('aria-labelledby="certifications-label"',
                                               'aria-labelledby=""')(
        in_certs('<h3 id="certifications-label">', '<h3 id="">')(h)),
    "disabled at load": around_certs('<div aria-disabled="true">', "</div>"),
    "no Add button": in_certs(ADD, ""),
    "a second button": in_certs(HEAD, HEAD + '<button type="button">Help</button>'),
    "an Add that is an input": in_certs(ADD, '<input type="button" data-wd-add value="Add">'),
    "an Add that is not a button": in_certs(ADD, '<div type="button" data-wd-add>Add</div>'),
    "an Add with more to it": in_certs(
        ADD, '<button type="button" data-wd-add name="cx">Add</button>'),
    "an Add holding an element": in_certs(
        ADD, '<button type="button" data-wd-add><span>Add</span></button>'),
    "an Add that submits": in_certs(ADD, ADD.replace('type="button"', 'type="submit"')),
    "Add Another with no entry": in_certs(">Add</button>", ">Add Another</button>"),
    "an entries list that is not a div": in_certs("<div data-wd-entries></div>",
                                                  "<span data-wd-entries></span>"),
    "an entries list with more to it": in_certs(
        "<div data-wd-entries></div>", '<div data-wd-entries data-count="0"></div>'),
    "text in it": in_certs("<div data-wd-entries></div>",
                           "<div data-wd-entries>Registered Nurse</div>"),
    "a control in it": in_certs(HEAD, HEAD + '<input type="hidden" name="cx">'),
    "something editable in it": in_certs(HEAD, HEAD + "<div contenteditable></div>"),
    "a custom control in it": in_certs(HEAD, HEAD + '<div role="textbox"></div>'),
    "a frame in it": in_certs(HEAD, HEAD + '<iframe src="about:blank"></iframe>'),
    "a script in it": in_certs(HEAD, HEAD + "<script>window.x = 1</script>"),
    "a template in it": in_certs(HEAD, HEAD + "<template><input></template>"),
    "an attribute written twice": in_certs(
        '<button type="button" data-wd-add>', '<button type="submit" type="button" data-wd-add>'),
    "inside another section": lambda h: moved_into(h, CERTS, SKILLS),
    "on the review page": on_the_review_page,
    # an entry at load not exactly as its template builds it
    "an entry holding a value": changed_entry(
        'name="cert[0].name" type="text" required>',
        'name="cert[0].name" type="text" required value="Registered Nurse">'),
    "an entry whose number holds a value": changed_entry(
        'name="cert[0].number" type="text">', 'name="cert[0].number" type="text" value="123">'),
    "an entry whose date holds a value": changed_entry(
        'name="cert[0].issued" type="text"', 'name="cert[0].issued" type="text" value="01/2020"'),
    "an entry numbered from 1": with_entry(entry("1", "2")),
    "an entry numbered 1 shown as 2": with_entry(entry("0", "2")),
    "an entry whose name has a length limit": changed_entry(
        'type="text" required>', 'type="text" required maxlength="40">'),
    "an entry whose date has a length limit": changed_entry(
        'name="cert[0].issued" type="text"', 'name="cert[0].issued" type="text" maxlength="7"'),
    "an entry whose name is of another type": changed_entry(
        'name="cert[0].name" type="text"', 'name="cert[0].name" type="search"'),
    "an entry whose date is a date box": changed_entry(
        'name="cert[0].issued" type="text"', 'name="cert[0].issued" type="date"'),
    "an entry whose name is not required": changed_entry(
        'type="text" required>', 'type="text">'),
    "an entry whose number is required": changed_entry(
        'name="cert[0].number" type="text">', 'name="cert[0].number" type="text" required>'),
    "an entry whose issued date is required": changed_entry(
        'name="cert[0].issued" type="text"', 'name="cert[0].issued" type="text" required'),
    "an entry whose expiration date is required": changed_entry(
        'name="cert[0].expires" type="text"', 'name="cert[0].expires" type="text" required'),
    "an entry whose date says another format": changed_entry(
        'name="cert[0].issued" type="text" placeholder="MM/YYYY"',
        'name="cert[0].issued" type="text" placeholder="DD/MM/YYYY"'),
    "an entry whose date says no format": changed_entry(
        'name="cert[0].issued" type="text" placeholder="MM/YYYY"',
        'name="cert[0].issued" type="text"'),
    "an entry with more to it": changed_entry(
        'type="text" required>', 'type="text" required autocomplete="off">'),
    "an entry with another label": changed_entry(">Certification<", ">Licence<"),
    "an entry with its dates in another order": with_entry(dates_swapped(ENTRY_0)),
    "an entry without its number": changed_entry(at0(NUMBER_PAIR), ""),
    "an entry with a fifth box": changed_entry(
        "</div>", '<label for="cert-0-issuer">Issuer</label>'
        '<input id="cert-0-issuer" name="cert[0].issuer" type="text"></div>'),
    "an entry and Add": with_entry(ENTRY_0, add="Add"),
    "an entry with no box": with_entry(  # only an entry without its boxes
        '<div data-wd-entry="0"><h4>Certifications 1</h4></div>'),
    "an entry's box written twice": changed_entry(
        'name="cert[0].name" type="text"', 'name="cert[0].name" type="search" type="text"'),
    "an entry with an attribute of its own": changed_entry(
        '<div data-wd-entry="0">', '<div data-wd-entry="0" class="cx">'),
    "an entry heading of another kind": changed_entry(
        "<h4>Certifications 1</h4>", "<h5>Certifications 1</h5>"),
    "an entry heading with an attribute": changed_entry(
        "<h4>Certifications 1</h4>", '<h4 id="c1">Certifications 1</h4>'),
    "an entry heading holding an element": changed_entry(
        "<h4>Certifications 1</h4>", "<h4><span>Certifications 1</span></h4>"),
    "an entry's label for another box": changed_entry(
        '<label for="cert-0-name">', '<label for="cert-9-name">'),
    "an entry's box a text area": changed_entry(
        '<input id="cert-0-name" name="cert[0].name" type="text" required>',
        '<textarea id="cert-0-name" name="cert[0].name" type="text" required></textarea>'),
    "an entry of another element": with_entry(
        ENTRY_0.replace('<div data-wd-entry="0">', '<li data-wd-entry="0">')
        .replace("</div>", "</li>")),
    "an entry's label of another kind": changed_entry(
        '<label for="cert-0-name">Certification</label>',
        '<span for="cert-0-name">Certification</span>'),
    "an entry's label holding an element": changed_entry(
        '<label for="cert-0-name">Certification</label>',
        '<label for="cert-0-name"><b>Certification</b></label>'),
    # its template not exactly the entry the stand-in builds
    "no template": in_certs('data-wd-entry-template="certifications-entry"',
                            'data-wd-entry-template="certifications-missing"'),
    "a template inside the form": template_inside_the_form,
    "two templates of its id": after_the_form('<template id="certifications-entry"></template>'),
    "the template's id used twice": after_the_form('<div id="certifications-entry"></div>'),
    "a template whose name has a limit": in_template(
        NAME_BOX, NAME_BOX.replace("required>", 'required maxlength="40">')),
    "a template whose date takes a date": in_template(
        ISSUED_BOX, ISSUED_BOX.replace('type="text"', 'type="date"')),
    "a template whose name has a pattern": in_template(
        NAME_BOX, NAME_BOX.replace("required>", 'required pattern="[A-Z].*">')),
    "a template with a fifth box": in_template(
        NUMBER_BOX, NUMBER_BOX + '<input name="cert[__i__].issuer" type="text">'),
    "a template whose number is required": in_template(
        NUMBER_BOX, NUMBER_BOX.replace('type="text">', 'type="text" required>')),
    "a template whose issued date is required": in_template(
        ISSUED_BOX, ISSUED_BOX.replace('"MM/YYYY">', '"MM/YYYY" required>')),
    "a template without its number": in_template(NUMBER_PAIR, ""),
    # something in the form named as one of its entries, or under its key
    "an entry's hidden value before it": before_certs(
        '<input type="hidden" name="cert[0].name" value="Registered Nurse">'),
    "an entry's empty hidden field": before_certs(
        '<input type="hidden" name="cert[0].name" value="">'),
    "an entry's number given before it": before_certs(
        '<input type="hidden" name="cert[0].number" value="123">'),
    "an entry's control beside it": before_certs(
        '<label for="c0">Certification</label><input id="c0" name="cert[0].name" type="text">'),
    "an entry's control given from outside the form": after_the_form(
        '<input type="hidden" form="workday-application" name="cert[0].name" value="x">'),
    "a hidden field under its key": before_certs(
        '<input type="hidden" name="certifications_section" value="x">'),
    "a name first written as an entry's": before_certs(
        '<input type="hidden" name="cert[0].name" name="cx" value="x">'),
}  # fmt: skip
# On the wizard a submit button off its last page refuses the whole wizard (D142): read on the
# single page.
ON_THE_SINGLE_PAGE = {"an attribute written twice", "an Add that submits"}


@pytest.mark.parametrize("change", sorted(NOT_READ))
def test_a_certifications_section_not_exactly_as_built_is_its_own_checkpoint(change):
    """Never filled on a guess: anything about the Certifications section NoEfforts does not read
    exactly (a required mark the stand-in does not write, or written otherwise; a name, heading
    or role of another kind; two of them; not shown, never rendered or inert; anything in it but
    its heading, its entries as its template builds them and its plain Add; nested, or on a page
    it cannot be filled on; an entry at load holding anything or built otherwise, its boxes
    limited, required or asking otherwise; a template not exactly the entry; and anything in the
    form named as one of its entries or under its key) is its own checkpoint: apply on the
    employer's site. Languages, beside it, reads as before."""
    single = change in ON_THE_SINGLE_PAGE
    html = stand_in(None, "wd_certifications") if single else stand_in()
    schema = workday.extract_schema(NOT_READ[change](html))
    got = {f.key: f for f in schema.fields}
    assert checkpoint(got.get("certifications_section")), got.get("certifications_section")
    assert certs_of(schema) == []
    if not single:
        assert left_empty(got.get("languages_section"), "Languages"), change
    assert workday.WORK_KEY not in got and workday.MULTI_STEP_KEY not in got
    assert not [k for k in got if CERT.fullmatch(k)]


def test_an_entry_s_control_with_no_section_is_its_checkpoint():
    """A control named as a Certifications entry's on a page that shows no Certifications section
    is never a question of its own, nor left out silently: the checkpoint."""
    html = stand_in(None, "normal").replace(
        "</form>", '<input type="hidden" name="cert[0].name" value="x"></form>', 1
    )
    got = fields_of(html)
    assert checkpoint(got.get("certifications_section")) and "cert[0].name" not in got


@pytest.mark.parametrize(
    "inner, outer",
    [(LANG, CERTS), (CERTS, LANG)],
    ids=["languages-inside-certifications", "certifications-inside-languages"],
)  # fmt: skip
def test_a_section_inside_another_is_both_checkpoints(inner, outer):
    schema = workday.extract_schema(moved_into(stand_in(), inner, outer))
    got = {f.key: f for f in schema.fields}
    assert certs_of(schema) == []
    for key in ("languages_section", "certifications_section"):
        assert got[key].required and got[key].type == FieldType.unsupported, key


def test_certifications_inside_work_experience_is_both_checkpoints():
    html = moved_into(stand_in("certifications_and_experience"), CERTS,
                      '<div id="work-experience"')  # fmt: skip
    schema = workday.extract_schema(html)
    got = {f.key for f in schema.fields}
    assert certs_of(schema) == [] and {"certifications_section", workday.WORK_KEY} <= got


def test_a_page_question_under_its_key_never_hides_it():
    question = ('<label for="cs">Certifications</label>'
                '<input id="cs" name="certifications_section" type="text">')  # fmt: skip
    at = '<label for="exp_details">'
    html = stand_in().replace(at, question + at, 1)
    schema = workday.extract_schema(html)
    assert certs_of(schema) == []
    assert [checkpoint(f) for f in schema.fields if f.key == "certifications_section"] == [True]


# ---------------------------------------------------------------------------- resolution


def credential(name, issued=None, expires=None, *, approved: bool = True, version: int = 2):
    status = Approval.approved if approved else Approval.proposed
    return SimpleNamespace(id=uuid4(), version=version, name=name, issuer=None, issued_on=issued,
                           expires_on=expires, approval_status=status)  # fmt: skip


def test_each_licence_or_certification_is_one_row_as_written():
    rn = credential(RN["name"], date(2019, 4, 15), date(2027, 4, 30))
    (row,) = ss.resolve_section("certifications", [rn]).rows
    assert (row.record_id, row.record_type) == (str(rn.id), "credential")
    assert {k: (f.status, f.value, f.display) for k, f in row.fields.items()} == {
        "name": ("resolved", {"text": RN["name"]}, RN["name"]),
        "issued_on": ("resolved", {"month": 4, "year": 2019}, "04/2019"),
        "expires_on": ("resolved", {"month": 4, "year": 2027}, "04/2027"),
    }
    assert row.fields["name"].fact_refs == [{"type": "credential", "id": str(rn.id), "version": 2,
                                             "field": "name", "value": RN["name"]}]  # fmt: skip
    assert row.fields["issued_on"].fact_refs[0]["value"] == "2019-04-15"
    assert row.fields["expires_on"].explanation == "From your record's expiration date."


def test_a_date_the_record_does_not_hold_is_not_sent():
    (row,) = ss.resolve_section("certifications", [credential(FORKLIFT["name"])]).rows
    dates = [row.fields["issued_on"], row.fields["expires_on"]]
    assert [(f.status, f.value, f.display) for f in dates] == [("omitted", None, None)] * 2
    assert dates[0].explanation == "No issued date on this record: none is sent."


def test_an_expired_one_is_sent_with_its_expiration_date():
    """The entry asks the expiration date: the employer sees it (and you, before you approve)."""
    (row,) = ss.resolve_section(
        "certifications", [credential(BLS["name"], date(2024, 1, 10), date(2026, 1, 31))]
    ).rows
    assert (row.fields["expires_on"].status, row.fields["expires_on"].display) == (
        "resolved", "01/2026")  # fmt: skip


def test_an_issued_date_after_the_expiration_date_is_yours_to_fix():
    bad = credential("Phlebotomy (fictional)", date(2022, 5, 1), date(2021, 1, 1))
    (row,) = ss.resolve_section("certifications", [bad]).rows
    assert [row.fields[k].status for k in ("name", "issued_on", "expires_on")] == [
        "resolved", "needs_user", "needs_user"]  # fmt: skip
    assert row.fields["issued_on"].explanation == ss._BAD_CERT_DATES


@pytest.mark.parametrize("name", ["Line\nbreak", "Carriage\rreturn", "   "],
                         ids=["a line break", "a carriage return", "spaces only"])  # fmt: skip
def test_a_name_a_form_cannot_hold_is_yours_to_fix(name):
    (row,) = ss.resolve_section("certifications", [credential(name)]).rows
    assert row.fields["name"].status == "needs_user"


def test_only_approved_ones_are_rows_in_record_order():
    rows_ = ss.resolve_section(
        "certifications", [credential("A"), credential("B", approved=False), credential("C")]
    ).rows
    assert [r.fields["name"].display for r in rows_] == ["A", "C"]


def test_parts_or_limits_are_never_ignored():
    for kw in ({"parts": ("location",)}, {"limits": {"title": 40}}):
        assert not ss.resolve_section("certifications", [credential("A")], **kw).supported


def frozen(*creds) -> dict:
    return gs.section_to_content(ss.resolve_section("certifications", list(creds)),
                                 root="#certifications")  # fmt: skip


def test_a_frozen_certifications_section_is_never_planned_on_greenhouse():
    f = frozen(credential(RN["name"], date(2019, 4, 15), date(2027, 4, 30)),
               credential(FORKLIFT["name"]))  # fmt: skip
    assert gs.section_from_content(f).rows[0].fields["name"].display == RN["name"]
    with pytest.raises(gs.Refused, match="unknown section kind"):
        gs.plan_content_section(f)
    plan = ws.plan(f)  # the Workday-style stand-in's: the name and dates typed, never the number
    box = '#certifications [name="cert[{}].{}"]'.format
    got = [(r.anchor, [(o.field, o.kind, o.value) for o in r.ops], r.blank) for r in plan.rows]
    assert got == [
        (box(0, "name"), [("name", "text", RN["name"]), ("issued_on", "text", "04/2019"),
                          ("expires_on", "text", "04/2027")], (box(0, "number"),)),
        (box(1, "name"), [("name", "text", FORKLIFT["name"])],
         (box(1, "number"), box(1, "issued"), box(1, "expires"))),
    ]  # fmt: skip


def _f(s: dict, field: str, row: int = 0, **kw) -> None:
    s["rows"][row]["fields"][field].update(kw)


TAMPERED = {
    "another field": lambda s: s["rows"][0]["fields"].update(
        {"number": {"status": "resolved", "value": {"text": "1"}, "display": "1"}}),
    "parts": lambda s: s.update({"parts": ["location"]}),
    "limits": lambda s: s.update({"limits": {"title": 40}}),
    "two rows of one identity": lambda s: s["rows"][1].update(
        {"record_id": s["rows"][0]["record_id"]}),
    "no name": lambda s: s["rows"][0]["fields"].pop("name"),
    "a date missing": lambda s: s["rows"][0]["fields"].pop("issued_on"),
    "a name omitted": lambda s: _f(s, "name", status="omitted", value=None, display=None),
    "a name other than shown": lambda s: _f(s, "name", value={"text": "Other"}),
    "a blank name": lambda s: _f(s, "name", value={"text": " "}, display=" "),
    "a name with a line break": lambda s: _f(s, "name", value={"text": "a\nb"}, display="a\nb"),
    "a name with a carriage return": lambda s: _f(s, "name", value={"text": "a\rb"},
                                                  display="a\rb"),
    "a name needing you": lambda s: _f(s, "name", status="needs_user"),
    "a date other than shown": lambda s: _f(s, "issued_on", display="05/2019"),
    "a date shown without its zero": lambda s: _f(s, "issued_on", display="4/2019"),
    "a month that is none": lambda s: _f(s, "issued_on", value={"month": 13, "year": 2019},
                                         display="13/2019"),
    "a month that is a boolean": lambda s: _f(s, "issued_on", value={"month": True, "year": 2019},
                                              display="01/2019"),
    "a date with more to it": lambda s: _f(s, "issued_on",
                                           value={"month": 4, "year": 2019, "day": 15}),
    "an omitted date with a value": lambda s: _f(s, "issued_on", row=1,
                                                 value={"month": 1, "year": 2020}),
    "an omitted date with a display": lambda s: _f(s, "expires_on", row=1, display="01/2020"),
    "a date needing you": lambda s: _f(s, "issued_on", status="needs_user"),
    "issued after it expires": lambda s: _f(s, "issued_on", value={"month": 5, "year": 2028},
                                            display="05/2028"),
}  # fmt: skip


@pytest.mark.parametrize("tamper", sorted(TAMPERED))
def test_frozen_certifications_content_holds_only_what_resolution_writes(tamper):
    """Never anything resolution does not write (D166 review's rule): a field of another kind,
    parts or limits, a repeated row, a name or date missing, other than shown, not one line, or
    needing you, a date other than a month and year as MM/YYYY, and an issued date after the
    expiration date are refused before anything is entered."""
    f = frozen(credential(RN["name"], date(2019, 4, 15), date(2027, 4, 30)),
               credential(FORKLIFT["name"]))  # fmt: skip
    TAMPERED[tamper](f)
    with pytest.raises(gs.Refused):
        ws.plan(f)


def test_a_stop_names_your_licences_and_certifications():
    assert wd_adapter._stops({"kind": "certifications"}) == (
        wd_adapter.CERTIFICATIONS_UNUSABLE, wd_adapter.CERTIFICATIONS_ENTRIES_BEYOND,
        wd_adapter.CERTIFICATIONS_PREFILLED, wd_adapter.CERTIFICATIONS_NOT_ENTERED)  # fmt: skip
    op = ws.plan(frozen(credential("A"))).rows[0].ops[0]
    assert ws._what(op) == "certifications: name"


# ---------------------------------------------------------------------------- the package


def with_credentials(api, creds) -> list[dict]:
    """Each licence or certification added to your profile and approved."""
    out = []
    for cred in creds:
        r = api.post("/profile/credentials", json=cred)
        assert r.status_code in (200, 201), r.text
        made = r.json()
        assert api.post(f"/profile/credentials/{made['id']}/approve").status_code == 200
        out.append(made)
    return out


def application(api, receiver, variant="certifications", *, mode=None, approved=True,
                creds=CREDS, work=(), schooling=()) -> str:  # fmt: skip
    """The variant switched on (a wizard variant, or the single page's mode), your licences and
    certifications (and work history or education, when given), then a Workday-style
    application on a posting of its own, captured, answered and, when `approved`, approved."""
    receiver.config(**({"mode": mode} if mode else {"wizard": variant}))
    synthetic_candidate(api)
    with_credentials(api, creds)
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


def frozen_certs(c: dict) -> dict | None:
    return next((s for s in c.get("sections") or [] if s["kind"] == "certifications"), None)


def mine(api, name: str) -> dict:
    return next(c for c in api.get("/profile/credentials").json() if c["name"] == name)


def test_the_package_shows_each_one_as_an_entry_and_needs_nothing_from_you(api, receiver):
    app_id = application(api, receiver, approved=False)
    c = content(api, app_id)
    assert not c["unresolved"] and not c["validation_errors"]
    sec = frozen_certs(c)
    assert (sec["root"], sec["step"]) == ("#certifications", "My Experience")
    assert "parts" not in sec and "limits" not in sec
    assert [r["fields"]["name"]["display"] for r in sec["rows"]] == NAMES  # newest issued first
    assert [(r["fields"]["issued_on"]["display"], r["fields"]["expires_on"]["display"])
            for r in sec["rows"]] == [("01/2024", "01/2026"), ("04/2019", "04/2027"),
                                      (None, None)]  # fmt: skip
    assert "certifications_section" not in {a["key"] for a in c["answers"]}
    assert pk.SCHEMA_VERSION == 3 and paths(c) - SHAPES[3] <= {".answers[].widget", ".wizard"}
    assert approve(api, app_id).status_code == 200


def test_with_none_approved_the_section_holds_no_entry(api, receiver):
    app_id = application(api, receiver, approved=False, creds=())
    c = content(api, app_id)
    assert not c["unresolved"] and frozen_certs(c)["rows"] == []
    assert approve(api, app_id).status_code == 200


def test_one_the_page_requires_with_none_blocks_approval(api, receiver):
    app_id = application(api, receiver, "certifications_required", approved=False, creds=())
    c = content(api, app_id)
    assert c["unresolved"] == ["section:certifications"] and frozen_certs(c) is None
    assert {e["key"]: e["message"] for e in c["validation_errors"]}["section:certifications"] == (
        pk.SECTION_REQUIRED["certifications"])  # fmt: skip
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []


def test_an_issued_date_after_its_expiration_blocks_approval_naming_it(api, receiver):
    bad = {"name": "Phlebotomy (fictional)", "issued_on": "2022-05-01", "expires_on": "2021-01-01"}
    app_id = application(api, receiver, approved=False, creds=(RN, bad))
    c = content(api, app_id)
    keys = sorted(e["key"] for e in c["validation_errors"])
    rid = mine(api, bad["name"])["id"]
    assert keys == [f"section:certifications:{rid}:expires_on",
                    f"section:certifications:{rid}:issued_on"]  # fmt: skip
    assert sorted(c["unresolved"]) == keys
    assert frozen_certs(c) is None and approve(api, app_id).status_code != 200


def test_one_not_yet_approved_is_not_sent(api, receiver):
    app_id = application(api, receiver, approved=False, creds=(RN, FORKLIFT))
    with SessionLocal() as db:
        cred = db.get(Credential, uuid.UUID(mine(api, FORKLIFT["name"])["id"]))
        cred.approval_status = Approval.proposed
        db.commit()
    assert [r["fields"]["name"]["display"] for r in frozen_certs(content(api, app_id))["rows"]] == [
        RN["name"]]  # fmt: skip


def test_changing_one_retires_the_approval_at_once_and_says_what_changed(api, receiver):
    """D140's rule for a record's change, for a licence or certification: an approval of the old
    one is retired when you save, and the version diff names the entry and what changed."""
    app_id = application(api, receiver, creds=(RN, FORKLIFT))
    r = api.put(f"/profile/credentials/{mine(api, RN['name'])['id']}",
                json=RN | {"expires_on": "2029-04-30"})  # fmt: skip
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is None
    version = api.get(f"/applications/{app_id}/package").json()["package"]["version"]
    diff = api.get(f"/applications/{app_id}/package/diff",
                   params={"from_version": version - 1, "to_version": version}).json()  # fmt: skip
    (sec,) = diff["sections"]
    assert (sec["kind"], sec["status"]) == ("certifications", "changed")
    assert [(x["label"], x["change"], [(f["field"], f["before"]["display"], f["after"]["display"])
                                       for f in x["fields"]]) for x in sec["rows"]] == [
        (RN["name"], "changed", [("expires_on", "04/2027", "04/2029")])]  # fmt: skip


def test_deleting_one_retires_the_approval_at_once(api, receiver):
    app_id = application(api, receiver, creds=(RN, FORKLIFT))
    assert (
        api.delete(f"/profile/credentials/{mine(api, FORKLIFT['name'])['id']}").status_code == 204
    )
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is None
    assert [r["fields"]["name"]["display"] for r in frozen_certs(content(api, app_id))["rows"]] == [
        RN["name"]]  # fmt: skip


def test_another_account_s_credentials_never_reach_your_application(api, other_api, receiver):
    """Every query by user_id; another account's access is a 404: another account's licences and
    certifications are never your package's, a change to them retires nothing of yours, and your
    package and records are not theirs to read or change."""
    app_id = application(api, receiver, creds=(RN,))
    before = api.get(f"/applications/{app_id}/package").json()["package"]
    synthetic_candidate(other_api)
    with_credentials(other_api, [{"name": "Another account's licence (fictional)"}])
    after = api.get(f"/applications/{app_id}/package").json()["package"]
    assert (after["version"], after["content_hash"]) == (before["version"], before["content_hash"])
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is not None
    assert [r["fields"]["name"]["display"] for r in frozen_certs(after["content"])["rows"]] == [
        RN["name"]]  # fmt: skip
    assert other_api.get(f"/applications/{app_id}/package").status_code == 404
    rn_id = mine(api, RN["name"])["id"]
    assert other_api.put(f"/profile/credentials/{rn_id}", json=RN).status_code == 404
    assert other_api.delete(f"/profile/credentials/{rn_id}").status_code == 404
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is not None


def test_a_section_that_now_waits_for_you_is_said_so_in_the_diff(api, receiver):
    """D140's diff for a certifications section the form gains, required, with none approved: a
    checkpoint in the new version only, frozen in neither, said as such, never "nothing
    changed"."""
    app_id = application(api, receiver, "plain", approved=False, creds=())
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    receiver.config(wizard="certifications_required")
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    c = content(api, app_id)
    assert "section:certifications" in c["unresolved"]
    diff = api.get(f"/applications/{app_id}/package/diff").json()
    assert [(s["kind"], s["status"]) for s in diff["sections"]] == [
        ("certifications", "needs_you")]  # fmt: skip


# ---------------------------------------------------------------------------- the ledger


def accepted(receiver) -> dict:
    (row,) = receiver.ledger()["acceptances"]
    return row["fields"]


def sent_certs(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if CERT.fullmatch(k)}


def page_2(receiver) -> dict:
    (fields,) = [d["fields"] for d in drafts(receiver.ledger()) if d["page"] == 2]
    return fields


def test_your_licences_and_certifications_are_entered_and_sent_as_approved(api, receiver):
    app_id = application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 1
    assert sent_certs(page_2(receiver)) == SENT and sent_certs(accepted(receiver)) == SENT
    assert all(r["mismatched"] == 0 for r in rows(aid, "step"))
    entered = [(d["section"], d["row"], d["field"]) for d in rows(aid, "disclosure")
               if d.get("kind") == "section_field"]  # fmt: skip
    assert entered == [("certifications", 0, "name"), ("certifications", 0, "issued_on"),
                       ("certifications", 0, "expires_on"), ("certifications", 1, "name"),
                       ("certifications", 1, "issued_on"), ("certifications", 1, "expires_on"),
                       ("certifications", 2, "name")]  # fmt: skip


def test_on_the_single_page_they_are_sent(api, receiver):
    app_id = application(api, receiver, mode="wd_certifications")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(accepted(receiver)) == SENT


def test_with_none_nothing_is_entered_and_it_is_sent(api, receiver):
    app_id = application(api, receiver, creds=())
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(page_2(receiver)) == {} and sent_certs(accepted(receiver)) == {}


def test_one_the_page_requires_is_filled_and_sent(api, receiver):
    app_id = application(api, receiver, "certifications_required", creds=(RN,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(accepted(receiver)) == {
        "cert[0].name": RN["name"], "cert[0].number": "", "cert[0].issued": "04/2019",
        "cert[0].expires": "04/2027"}  # fmt: skip


def test_an_empty_entry_already_there_is_filled_in_place(api, receiver):
    app_id = application(api, receiver, "certifications_entry_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(page_2(receiver)) == SENT and sent_certs(accepted(receiver)) == SENT


def test_with_none_for_the_empty_entry_shown_it_stops_before_anything_is_entered(api, receiver):
    """An empty entry already on the page and nothing to put in it: NoEfforts never removes one,
    and the page's own checks would refuse it empty, so the attempt stops before anything is
    entered."""
    app_id = application(api, receiver, "certifications_entry_at_load", creds=())
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert wd_adapter.CERTIFICATIONS_ENTRIES_BEYOND in attempt(aid).outcome_detail
    assert attempt(aid).disclosure_started_at is None


def test_beside_them_your_work_history_and_education_are_sent(api, receiver):
    app_id = application(api, receiver, "certifications_and_experience", work=(WORK_CURRENT,),
                         schooling=(MASTER, BACHELOR))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = page_2(receiver)
    assert fields["work[0].title"] == "Clinic Assistant"
    assert {k: v for k, v in fields.items() if k.startswith("edu[")} == EDU_SENT
    assert sent_certs(fields) == SENT


def test_beside_them_your_websites_are_sent_and_languages_and_skills_left_empty(api, receiver):
    app_id = application(api, receiver, "certifications_and_other_sections")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = page_2(receiver)
    assert sent_certs(fields) == SENT
    assert {k: v for k, v in fields.items() if k.startswith("web[")} == {
        "web[0].url": "https://www.linkedin.com/in/sam-synthetic"}  # fmt: skip
    assert not [k for k in fields if k.startswith(("lang[", "skill["))]


def test_an_entry_a_parsed_resume_adds_stops_before_its_page_is_sent(api, receiver):
    """The resume's parse adds a Certifications entry with values of its own after approval: the
    entry would be sent unapproved, so the attempt stops before anything of the section is
    entered, page 2 never sent."""
    app_id = application(api, receiver, "certifications_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert wd_adapter.CERTIFICATIONS_PREFILLED in attempt(aid).outcome_detail
    assert not [d for d in rows(aid, "disclosure") if d.get("kind") == "section_field"]


def test_a_section_the_page_requires_since_approval_pauses_before_anything_is_entered(
    api, receiver
):
    app_id = application(api, receiver)
    receiver.config(wizard="certifications_required")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_empty_entry_shown_since_approval_is_filled_in_place(api, receiver):
    """The same form (an empty entry is read as before, D149): your first one goes in it."""
    app_id = application(api, receiver)
    receiver.config(wizard="certifications_entry_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(page_2(receiver)) == SENT


# ---------------------------------------------------------------------------- after typing


def nowhere(receiver, value: str) -> bool:
    """The value reached the employer nowhere: no page's draft, no acceptance."""
    led = receiver.ledger()
    return not [d for d in drafts(led) if value in d["fields"].values()] and not [
        a for a in led["acceptances"] if value in a["fields"].values()]  # fmt: skip


def test_a_value_the_page_keeps_once_one_is_typed_stops_before_its_page_is_sent(api, receiver):
    """Once a certification is typed the page keeps a value of its own in a hidden field outside
    the section, named as an entry's: the form read again before page 2's Next is no longer the
    approved one (the section is then its checkpoint), so the attempt stops with page 2 never
    sent, and the value reaches the employer nowhere."""
    app_id = application(api, receiver, "certifications_hidden_after_typing")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert FORM_CHANGED in attempt(aid).outcome_detail
    assert nowhere(receiver, UNAPPROVED)


def test_on_the_single_page_a_value_kept_once_typed_stops_before_the_final_click(api, receiver):
    app_id = application(api, receiver, mode="wd_certifications_hidden_after_typing")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") not in ("confirmed", "unknown")
    led = receiver.ledger()
    assert led["accepted"] == 0 and posts(led, "/apply") == 0
    assert FORM_CHANGED in attempt(aid).outcome_detail
    assert nowhere(receiver, UNAPPROVED)


def test_an_entry_the_page_adds_once_one_is_typed_stops_before_its_page_is_sent(api, receiver):
    """Once your one licence is typed the page adds an entry holding a value of its own: the
    section shows an entry beyond the plan when its page is read back, so the attempt stops with
    page 2 never sent."""
    app_id = application(api, receiver, "certifications_added_after_typing", creds=(RN,))
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert nowhere(receiver, UNAPPROVED)


def test_an_entry_the_page_adds_is_given_your_next_one_and_holds_nothing_else(api, receiver):
    """With more of them, the entry the page adds is where your next one goes (an entry already
    there is filled in place, D149): the page's own value is replaced, and only yours are sent."""
    app_id = application(api, receiver, "certifications_added_after_typing")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_certs(page_2(receiver)) == SENT and sent_certs(accepted(receiver)) == SENT
    assert nowhere(receiver, UNAPPROVED)


def test_a_number_the_page_writes_once_a_name_is_typed_stops_before_its_page_is_sent(api, receiver):
    """NoEfforts never fills the number, and reads its box back empty: once a name is typed the
    page writes a number of its own into that entry, so the readback before page 2's Next stops
    the attempt, page 2 never sent and the number reaching the employer nowhere."""
    app_id = application(api, receiver, "certifications_number_after_typing", creds=(RN,))
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert nowhere(receiver, UNAPPROVED_NUMBER)
