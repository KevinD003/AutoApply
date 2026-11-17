"""D166: the Workday-style stand-in's Websites section (FIXTURE ASSUMPTION FA11, FA10's section,
fixtures/ats_receiver/workday_like.py) filled from your profile's links. Before D166 NoEfforts
left it empty (D165): your websites never reached an employer through it. Now it is read as a
websites section, its rows your approved profile's links, one each: the web address its entry is
given (with https:// before a link that names no scheme), shown on the review page and diffed,
entered entry by entry and read back as the rest of a section (D149's machinery), or a
checkpoint for a link that is not a web address. Anything about the section NoEfforts does not
read exactly is its own checkpoint, as D165 made it.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real Websites section was
observed). Synthetic candidate data only."""

import re
import uuid
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
from app.modules.profiles.models import Approval, CandidateProfile
from app.modules.providers.routing import form_checkpoint
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_package_contract import SHAPES, paths
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_education import BACHELOR, MASTER, education
from tests.test_workday_education import SENT as EDU_SENT
from tests.test_workday_experience import CURRENT as WORK_CURRENT
from tests.test_workday_experience import employment
from tests.test_workday_other_sections import LANG, LANG_ADD, fields_of, left_empty, moved_into
from tests.test_workday_other_sections import stand_in as _stand_in
from tests.test_workday_wizard import approve, draft_pages, drafts, posts, rows

# Your profile's links (synthetic), as written, and what each entry is given, in order.
LINKS = ["github.com/sam-synthetic", "https://sam.example/portfolio",
         "https://www.linkedin.com/in/sam-synthetic"]  # fmt: skip
ADDRESSES = ["https://github.com/sam-synthetic", "https://sam.example/portfolio",
             "https://www.linkedin.com/in/sam-synthetic"]  # fmt: skip
SENT = {f"web[{i}].url": a for i, a in enumerate(ADDRESSES)}
UNAPPROVED = "https://unapproved.example/"  # FA11: what the page keeps or adds once one is typed
# An entry's control names (FA10's markup): Languages and Skills are never filled.
WEB = re.compile(r"web\[\d+\]\.[a-z_]+")
NEVER = re.compile(r"(lang|skill)\[\d+\]\.[a-z_]+")
PROFILE = {"full_name": "Sam Synthetic", "given_name": "Sam", "family_name": "Synthetic",
           "contact_email": "sam.synthetic@example.com", "phone": "+1 555 0100",
           "residence_country": "US", "residence_city": "Springfield"}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def stand_in(variant: str | None = "other_sections", mode: str = "normal") -> str:
    return _stand_in(variant, mode)


def websites_of(schema) -> list[tuple[str, str, str | None, bool]]:
    return [(s.kind, s.root, s.step, s.required) for s in schema.sections if s.kind == "websites"]


def checkpoint(f: FormField | None) -> bool:
    return f is not None and (f.type, f.required, f.widget, f.label, f.unsupported_reason) == (
        FieldType.unsupported, True, None, "Websites", workday.WEBSITES_REASON)  # fmt: skip


# ---------------------------------------------------------------------------- capture


def test_the_websites_section_is_read_as_one_filled_from_your_links():
    """No longer a field left empty (D165): a websites section on its page, which the page does
    not require; its entries' controls are never questions, and the route has nothing to hold."""
    schema = workday.extract_schema(stand_in())
    assert websites_of(schema) == [("websites", "#websites", "My Experience", False)]
    got = {f.key: f for f in schema.fields}
    assert "websites_section" not in got and workday.WORK_KEY not in got
    assert not [k for k in got if WEB.fullmatch(k)]
    assert left_empty(got["languages_section"], "Languages")
    assert left_empty(got["skills_section"], "Skills")
    assert form_checkpoint(schema.model_dump(mode="json")) == []


def test_on_the_single_page_it_is_read_on_no_page():
    schema = workday.extract_schema(stand_in(None, "wd_other_sections"))
    assert websites_of(schema) == [("websites", "#websites", None, False)]
    assert "websites_section" not in {f.key for f in schema.fields}


def test_one_the_page_requires_is_read_as_required():
    """FA11: the page's own mark of a required section (`aria-required="true"`, and an asterisk
    after the heading's name): NoEfforts then must enter at least one link."""
    schema = workday.extract_schema(stand_in("websites_required"))
    assert websites_of(schema) == [("websites", "#websites", "My Experience", True)]


def test_an_empty_entry_already_there_is_read_as_the_section():
    schema = workday.extract_schema(stand_in("websites_entry_at_load"))
    assert websites_of(schema) == [("websites", "#websites", "My Experience", False)]
    assert not [f.key for f in schema.fields if WEB.fullmatch(f.key)]  # never a question


def test_beside_work_experience_and_education_each_is_read():
    for variant, kind in (("other_sections_and_experience", "employment"),
                          ("other_sections_and_education", "education")):  # fmt: skip
        schema = workday.extract_schema(stand_in(variant))
        assert [s.kind for s in schema.sections] == [kind, "websites"]
        got = {f.key for f in schema.fields}
        assert workday.WORK_KEY not in got and workday.EDUCATION_KEY not in got


def test_the_section_is_part_of_the_form():
    """Made required, or added or taken away since approval: another form (the fingerprint),
    D132's pause before anything is entered. An empty entry shown since is the same form, as for
    D149's work history: it is filled in place, or, with no link for it, a stop."""
    base = form_fingerprint(workday.extract_schema(stand_in()))
    assert form_fingerprint(workday.extract_schema(stand_in("websites_required"))) != base
    assert form_fingerprint(workday.extract_schema(stand_in("websites_entry_at_load"))) == base
    html = stand_in()
    start = html.index(WEBSITES)
    end = html.index(LANG_ADD, start) + len(LANG_ADD)
    assert form_fingerprint(workday.extract_schema(html[:start] + html[end:])) != base


WEBSITES = '<div id="websites" role="group"'
SKILLS = '<div id="skills" role="group"'
WEB_HEAD = '<h3 id="websites-label">Websites</h3>'
ADD = '<button type="button" data-wd-add>Add</button>'
ENTRY_0 = ('<div data-wd-entry="0"><h4>Websites 1</h4><label for="web-0-url">URL</label>'
           '<input id="web-0-url" name="web[0].url" type="url" required></div>')  # fmt: skip
BOX = '<input id="web-__i__-url" name="web[__i__].url" type="url" required>'


def bounds(html: str) -> tuple[int, int]:
    start = html.index(WEBSITES)
    return start, html.index("</button></div>", start) + len("</button></div>")


def in_websites(old: str, new: str):
    """A change inside the Websites section (FA10's markup) only."""

    def change(html: str) -> str:
        start, end = bounds(html)
        section = html[start:end]
        assert old in section, old
        return html[:start] + section.replace(old, new, 1) + html[end:]

    return change


def around_websites(before: str, after: str):
    def change(html: str) -> str:
        start, end = bounds(html)
        return html[:start] + before + html[start:end] + after + html[end:]

    return change


def before_websites(markup: str):
    def change(html: str) -> str:
        start, _ = bounds(html)
        return html[:start] + markup + html[start:]

    return change


def in_template(old: str, new: str):
    """A change inside the section's entry template (outside the form)."""

    def change(html: str) -> str:
        start = html.index('<template id="websites-entry">')
        end = html.index("</template>", start)
        part = html[start:end]
        assert old in part, old
        return html[:start] + part.replace(old, new, 1) + html[end:]

    return change


def with_entry(entry: str, add: str = "Add Another"):
    """An entry already in the section at load, and its button's text."""
    return lambda html: in_websites(
        "<div data-wd-entries></div>" + ADD,
        f"<div data-wd-entries>{entry}</div>" + ADD.replace(">Add<", f">{add}<"),
    )(html)


def after_the_form(markup: str):
    def change(html: str) -> str:
        assert html.count("</form>") == 1
        return html.replace("</form>", "</form>" + markup, 1)

    return change


def websites_twice(html: str) -> str:
    """A second Websites section after the first, exactly as built: only the rule of one section
    of a kind sees it."""
    start, end = bounds(html)
    copy = (html[start:end].replace('id="websites"', 'id="websites-2"')
            .replace("websites-label", "websites-label-2"))  # fmt: skip
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
    html = in_websites(WEB_HEAD, "")(html)
    return before_websites('<h3 id="websites-label">Websites</h3>')(html)


def template_in_a_noscript(html: str) -> str:
    start = html.index('<template id="websites-entry">')
    end = html.index("</template>", start) + len("</template>")
    return html[:start] + "<noscript>" + html[start:end] + "</noscript>" + html[end:]


def template_inside_the_form(html: str) -> str:
    start = html.index('<template id="websites-entry">')
    end = html.index("</template>", start) + len("</template>")
    template, html = html[start:end], html[:start] + html[end:]
    return before_websites(template)(html)


NOT_READ = {
    # a required mark the stand-in does not write, or written otherwise (D165's lesson)
    "required on it": in_websites('data-wd-section="websites"',
                                  'data-wd-section="websites" required'),
    "data-required on it": in_websites('data-wd-section="websites"',
                                       'data-wd-section="websites" data-required="true"'),
    "aria-required false": in_websites('data-wd-section="websites"',
                                       'data-wd-section="websites" aria-required="false"'),
    "aria-required in capitals": lambda h: in_websites(
        'data-wd-section="websites"', 'data-wd-section="websites" aria-required="TRUE"')(
        in_websites(WEB_HEAD, '<h3 id="websites-label">Websites *</h3>')(h)),
    "aria-required without its asterisk": in_websites(
        'data-wd-section="websites"', 'data-wd-section="websites" aria-required="true"'),
    "an asterisk without aria-required": in_websites(
        WEB_HEAD, '<h3 id="websites-label">Websites *</h3>'),
    "(required) in its heading": in_websites(
        WEB_HEAD, '<h3 id="websites-label">Websites (required)</h3>'),
    "another asterisk in its heading": in_websites(
        WEB_HEAD, '<h3 id="websites-label">Websites \u2217</h3>'),
    "a mark inside its heading": in_websites(
        WEB_HEAD, '<h3 id="websites-label">Websites<abbr title="required"></abbr></h3>'),
    "aria-required on its heading": in_websites(
        WEB_HEAD, '<h3 id="websites-label" aria-required="true">Websites</h3>'),
    "its heading outside it": heading_outside,
    "named by a heading outside it": lambda h: in_websites(
        'aria-labelledby="websites-label"', 'aria-labelledby="websites-required"')(
        before_websites('<h3 id="websites-required">Websites *</h3>')(h)),
    "aria-required around it": around_websites('<div aria-required="true">', "</div>"),
    "required around it": around_websites("<fieldset required>", "</fieldset>"),
    "a name of its own": in_websites('data-wd-section="websites"',
                                     'data-wd-section="websites" aria-label="Websites *"'),
    "a title": in_websites('data-wd-section="websites"',
                           'data-wd-section="websites" title="Required"'),
    # not the section as the stand-in builds it
    "another role": in_websites('role="group"', 'role="region"'),
    "a heading that is not one": in_websites(WEB_HEAD,
                                             '<span id="websites-label">Websites</span>'),
    "a heading of another text": in_websites(WEB_HEAD,
                                             '<h3 id="websites-label">Web sites</h3>'),
    "its heading's id used twice": before_websites('<span id="websites-label"></span>'),
    "its id used twice": before_websites('<span id="websites"></span>'),
    "an id it cannot be found by": lambda h: h.replace('id="websites" role="group"',
                                                       'id="web sites" role="group"', 1),
    "two of a kind": websites_twice,
    "a custom element": custom_element_section,
    "hidden at load": around_websites("<div hidden>", "</div>"),
    # review: never rendered, or inert
    "inside a template in the form": around_websites("<template>", "</template>"),
    "inside a noscript in the form": around_websites("<noscript>", "</noscript>"),
    "under an inert element": around_websites("<div inert>", "</div>"),
    "its template inside a noscript": template_in_a_noscript,
    "named by an empty id": lambda h: in_websites('aria-labelledby="websites-label"',
                                                  'aria-labelledby=""')(
        in_websites('<h3 id="websites-label">', '<h3 id="">')(h)),
    "disabled at load": around_websites('<div aria-disabled="true">', "</div>"),
    "no Add button": in_websites(ADD, ""),
    "a second button": in_websites(WEB_HEAD, WEB_HEAD + '<button type="button">Help</button>'),
    "an Add that is an input": in_websites(ADD,
                                           '<input type="button" data-wd-add value="Add">'),
    "an Add that is not a button": in_websites(ADD, '<div type="button" data-wd-add>Add</div>'),
    "an Add with more to it": in_websites(
        ADD, '<button type="button" data-wd-add name="wx">Add</button>'),
    "an Add holding an element": in_websites(
        ADD, '<button type="button" data-wd-add><span>Add</span></button>'),
    "an Add that submits": in_websites(ADD, ADD.replace('type="button"', 'type="submit"')),
    "Add Another with no entry": in_websites(">Add</button>", ">Add Another</button>"),
    "an entries list that is not a div": in_websites("<div data-wd-entries></div>",
                                                     "<span data-wd-entries></span>"),
    "an entries list with more to it": in_websites(
        "<div data-wd-entries></div>", '<div data-wd-entries data-count="0"></div>'),
    "text in it": in_websites("<div data-wd-entries></div>",
                              "<div data-wd-entries>https://x.example</div>"),
    "a control in it": in_websites(WEB_HEAD, WEB_HEAD + '<input type="hidden" name="wx">'),
    "something editable in it": in_websites(WEB_HEAD, WEB_HEAD + "<div contenteditable></div>"),
    "a custom control in it": in_websites(WEB_HEAD, WEB_HEAD + '<div role="textbox"></div>'),
    "a frame in it": in_websites(WEB_HEAD, WEB_HEAD + '<iframe src="about:blank"></iframe>'),
    "a script in it": in_websites(WEB_HEAD, WEB_HEAD + "<script>window.x = 1</script>"),
    "a template in it": in_websites(WEB_HEAD, WEB_HEAD + "<template><input></template>"),
    "an attribute written twice": in_websites(
        '<button type="button" data-wd-add>', '<button type="submit" type="button" data-wd-add>'),
    "inside another section": lambda h: moved_into(h, WEBSITES, SKILLS),
    "on the review page": on_the_review_page,
    # an entry at load not exactly as its template builds it
    "an entry holding a value": with_entry(ENTRY_0.replace(
        'type="url" required>', 'type="url" required value="https://x.example">')),
    "an entry numbered from 1": with_entry(ENTRY_0.replace("0", "1").replace("Websites 1",
                                                                             "Websites 2")),
    "an entry numbered 1 shown as 2": with_entry(ENTRY_0.replace("Websites 1", "Websites 2")),
    "an entry with a length limit": with_entry(ENTRY_0.replace("required>",
                                                               'required maxlength="40">')),
    "an entry of another type": with_entry(ENTRY_0.replace('type="url"', 'type="text"')),
    "an entry not required": with_entry(ENTRY_0.replace(" required>", ">")),
    "an entry with more to it": with_entry(ENTRY_0.replace("required>",
                                                           'required autocomplete="url">')),
    "an entry with another label": with_entry(ENTRY_0.replace(">URL<", ">Website<")),
    "an entry with a second control": with_entry(ENTRY_0.replace(
        "required></div>", 'required><input type="hidden" name="web[0].kind"></div>')),
    "an entry and Add": with_entry(ENTRY_0, add="Add"),
    "an entry's box written twice": with_entry(ENTRY_0.replace('type="url"',
                                                               'type="text" type="url"')),
    "an entry with an attribute of its own": with_entry(ENTRY_0.replace(
        '<div data-wd-entry="0">', '<div data-wd-entry="0" class="wx">')),
    "an entry heading of another kind": with_entry(ENTRY_0.replace(
        "<h4>Websites 1</h4>", "<h5>Websites 1</h5>")),
    "an entry heading with an attribute": with_entry(ENTRY_0.replace(
        "<h4>Websites 1</h4>", '<h4 id="w1">Websites 1</h4>')),
    "an entry's label for another box": with_entry(ENTRY_0.replace(
        '<label for="web-0-url">', '<label for="web-9-url">')),
    "an entry's box a text area": with_entry(ENTRY_0.replace(
        '<input id="web-0-url" name="web[0].url" type="url" required>',
        '<textarea id="web-0-url" name="web[0].url" required></textarea>')),
    # its template not exactly the entry the stand-in builds
    "no template": in_websites('data-wd-entry-template="websites-entry"',
                               'data-wd-entry-template="websites-missing"'),
    "a template inside the form": template_inside_the_form,
    "two templates of its id": after_the_form('<template id="websites-entry"></template>'),
    "the template's id used twice": after_the_form('<div id="websites-entry"></div>'),
    "a template whose box has a limit": in_template(BOX, BOX.replace("required>",
                                                                     'required maxlength="40">')),
    "a template whose box takes text": in_template(BOX, BOX.replace('type="url"',
                                                                    'type="text"')),
    "a template whose box has a pattern": in_template(BOX, BOX.replace(
        "required>", 'required pattern="https://.*">')),
    "a template with a second control": in_template(BOX, BOX + '<input name="web[__i__].kind">'),
    # something in the form named as one of its entries, or under its key
    "an entry's hidden value before it": before_websites(
        '<input type="hidden" name="web[0].url" value="https://x.example">'),
    "an entry's empty hidden field": before_websites(
        '<input type="hidden" name="web[0].url" value="">'),
    "an entry's control beside it": before_websites(
        '<label for="w0">Website</label><input id="w0" name="web[0].url" type="url">'),
    "an entry's control given from outside the form": after_the_form(
        '<input type="hidden" form="workday-application" name="web[0].url" value="x">'),
    "a hidden field under its key": before_websites(
        '<input type="hidden" name="websites_section" value="x">'),
    "a name first written as an entry's": before_websites(
        '<input type="hidden" name="web[0].url" name="wx" value="x">'),
}  # fmt: skip
# On the wizard a submit button off its last page refuses the whole wizard (D142): read on the
# single page.
ON_THE_SINGLE_PAGE = {"an attribute written twice", "an Add that submits"}


@pytest.mark.parametrize("change", sorted(NOT_READ))
def test_a_websites_section_not_exactly_as_built_is_its_own_checkpoint(change):
    """Never filled on a guess: anything about the Websites section NoEfforts does not read
    exactly (a required mark the stand-in does not write, or written otherwise; a name, heading
    or role of another kind; two of them; not shown; anything in it but its heading, its entries
    as its template builds them and its plain Add; nested, or on a page it cannot be filled on;
    an entry at load holding anything or built otherwise; a template not exactly the entry; and
    anything in the form named as one of its entries or under its key) is its own checkpoint:
    apply on the employer's site. Languages, beside it, reads as before."""
    html = stand_in(None, "wd_other_sections") if change in ON_THE_SINGLE_PAGE else stand_in()
    changed = NOT_READ[change](html)
    schema = workday.extract_schema(changed)
    got = {f.key: f for f in schema.fields}
    assert checkpoint(got.get("websites_section")), got.get("websites_section")
    assert websites_of(schema) == []
    assert left_empty(got.get("languages_section"), "Languages"), change
    assert workday.WORK_KEY not in got and workday.MULTI_STEP_KEY not in got
    assert not [k for k in got if WEB.fullmatch(k)]


def test_an_entry_s_control_with_no_section_is_its_checkpoint():
    """A control named as a Websites entry's on a page that shows no Websites section is never a
    question of its own, nor left out silently: the checkpoint."""
    html = stand_in(None, "normal").replace(
        "</form>", '<input type="hidden" name="web[0].url" value="x"></form>', 1
    )
    got = fields_of(html)
    assert checkpoint(got.get("websites_section")) and "web[0].url" not in got


@pytest.mark.parametrize(
    "inner, outer, keys",
    [(LANG, WEBSITES, ("languages_section", "websites_section")),
     (WEBSITES, LANG, ("languages_section", "websites_section"))],
    ids=["languages-inside-websites", "websites-inside-languages"],
)  # fmt: skip
def test_a_section_inside_another_is_both_checkpoints(inner, outer, keys):
    schema = workday.extract_schema(moved_into(stand_in(), inner, outer))
    got = {f.key: f for f in schema.fields}
    assert websites_of(schema) == []
    for key in keys:
        assert got[key].required and got[key].type == FieldType.unsupported, key


def test_websites_inside_work_experience_is_both_checkpoints():
    schema = workday.extract_schema(
        moved_into(stand_in("other_sections_and_experience"), WEBSITES, '<div id="work-experience"')
    )
    got = {f.key for f in schema.fields}
    assert schema.sections == [] and {"websites_section", workday.WORK_KEY} <= got


def test_a_page_question_under_its_key_never_hides_it():
    question = ('<label for="ws">Websites</label>'
                '<input id="ws" name="websites_section" type="text">')  # fmt: skip
    at = '<label for="exp_details">'
    html = stand_in().replace(at, question + at, 1)
    schema = workday.extract_schema(html)
    assert websites_of(schema) == []
    assert [checkpoint(f) for f in schema.fields if f.key == "websites_section"] == [True]


# ---------------------------------------------------------------------------- resolution


@pytest.mark.parametrize(
    "link, address",
    [("https://sam.example", "https://sam.example"),
     ("http://sam.example/a?b=1#c", "http://sam.example/a?b=1#c"),
     ("github.com/sam", "https://github.com/sam"),
     ("  https://sam.example/x  ", "https://sam.example/x"),
     ("HTTPS://SAM.EXAMPLE", "https://SAM.EXAMPLE"),
     ("Https://sam.example/A", "https://sam.example/A"),
     ("https://sam.example:8443/p", "https://sam.example:8443/p"),
     ("sam.example:65535/p", "https://sam.example:65535/p"),
     ("\thttps://sam.example\n", "https://sam.example"),
     ("https://xn--80ak6aa92e.xn--p1ai/", "https://xn--80ak6aa92e.xn--p1ai/"),
     ("https://sam.example/a%20b;c=d", "https://sam.example/a%20b;c=d"),
     ("my portfolio", None),
     ("mailto:sam@sam.example", None),
     ("javascript:alert(1)", None),
     ("ftp://sam.example", None),
     ("http://localhost:3000", None),
     ("https://192.0.2.1/x", None),
     ("https://user@sam.example", None),
     ("https://sam.example/a b", None),
     ('https://sam.example/"q"', None),
     ("https://sam.example/<x>", None),
     ("https://ex\u00e4mple.com", None),
     ("http\u017f://sam.example", None),
     ("https://sam.example\u212a", None),
     ("https://sam.example.", None),
     ("sam.example:65536/p", None),
     ("https://sam.example:99999", None),
     ("https://sam.example\u3000", None),
     ("https://sam.example\x1c", None),
     ("\u00a0https://sam.example", None),
     ("https://-sam.example", None),
     ("https://sam.example/" + "a" * 2000, None)],
)  # fmt: skip
def test_a_link_is_entered_as_the_web_address_it_names(link, address):
    """D166: what an entry is given for a link, or None (the checkpoint): the link as written,
    without the ASCII spaces around it, with https:// before one that names no scheme and
    (review) its scheme in lower case, and nothing else changed or guessed; only http or https,
    a host of DNS labels, a port the browser takes (review: none above 65535), and characters a
    web address writes as they are, read in ASCII (a long s or a Kelvin sign is never read as a
    letter, and no other space is dropped)."""
    assert ss.web_address(link) == address


def profile(*links, approved: bool = True, version: int = 3):
    status = Approval.approved if approved else Approval.proposed
    return SimpleNamespace(id=uuid4(), version=version, links=list(links), approval_status=status)


def test_each_link_is_one_row_in_your_profile_s_order():
    p = profile(*LINKS)
    rows_ = ss.resolve_website_rows(p)
    assert [r.fields["url"].display for r in rows_] == ADDRESSES
    assert [r.fields["url"].value for r in rows_] == [{"text": a} for a in ADDRESSES]
    assert all(r.fields["url"].status == "resolved" for r in rows_)
    assert all(r.record_type == "websites" and r.record_id.startswith("link-") for r in rows_)
    assert len({r.record_id for r in rows_}) == 3
    first = rows_[0].fields["url"]
    assert first.explanation == (
        "From your profile's links (with https:// before it, as a web address has)."
    )
    assert rows_[1].fields["url"].explanation == "From your profile's links."
    assert first.fact_refs == [{"type": "profile", "id": str(p.id), "version": 3, "field": "links",
                                "value": LINKS[0]}]  # fmt: skip


def test_a_row_is_named_by_its_address_so_a_change_moves_only_its_own():
    a = [r.record_id for r in ss.resolve_website_rows(profile(*LINKS))]
    b = [r.record_id for r in ss.resolve_website_rows(profile(LINKS[2], LINKS[0]))]
    assert b == [a[2], a[0]]


def test_the_same_address_twice_is_one_row_and_a_blank_link_none():
    got = ss.resolve_website_rows(profile("github.com/sam", " ", "https://github.com/sam", ""))
    assert [r.fields["url"].display for r in got] == ["https://github.com/sam"]
    # review: its scheme and host in any case are the same address; another path is another
    links = ("https://github.com/sam", "HTTPS://GitHub.com/sam", "https://github.com/sam/",
             "https://github.com/Sam")  # fmt: skip
    got = ss.resolve_website_rows(profile(*links))
    assert [r.fields["url"].display for r in got] == [
        "https://github.com/sam", "https://github.com/sam/", "https://github.com/Sam"]  # fmt: skip


def test_a_link_that_is_not_a_web_address_is_a_checkpoint_naming_it():
    (row,) = ss.resolve_website_rows(profile("my portfolio"))
    fr = row.fields["url"]
    assert (fr.status, fr.value, fr.display, fr.source) == ("needs_user", None, None, "unresolved")
    assert "“my portfolio”" in fr.explanation and "Fix it in your profile" in fr.explanation


def test_only_an_approved_profile_s_links_are_rows():
    assert ss.resolve_section("websites", [profile(*LINKS, approved=False)]).rows == []
    assert len(ss.resolve_section("websites", [profile(*LINKS)]).rows) == 3
    assert ss.resolve_section("websites", []).rows == []
    unsupported = ss.resolve_section("websites", [profile(*LINKS)], parts=("location",))
    assert not unsupported.supported


def test_a_frozen_websites_section_is_never_planned_on_greenhouse():
    section = ss.resolve_section("websites", [profile(*LINKS)])
    frozen = gs.section_to_content(section, root="#websites")
    assert gs.section_from_content(frozen).rows[0].fields["url"].display == ADDRESSES[0]
    with pytest.raises(gs.Refused, match="unknown section kind"):
        gs.plan_content_section(frozen)
    plan = ws.plan(frozen)  # the Workday-style stand-in's: one typed box an entry
    assert [(r.anchor, [(o.field, o.kind, o.value) for o in r.ops]) for r in plan.rows] == [
        (f'#websites [name="web[{i}].url"]', [("url", "text", a)]) for i, a in enumerate(ADDRESSES)
    ]


def _url(s: dict, **kw) -> None:
    s["rows"][0]["fields"]["url"].update(kw)


@pytest.mark.parametrize(
    "tamper",
    [lambda s: s["rows"][0]["fields"].update({"title": {"status": "resolved"}}),
     lambda s: s.update({"parts": ["location"]}),
     lambda s: s.update({"limits": {"url": 40}}),
     lambda s: s["rows"][1].update({"record_id": s["rows"][0]["record_id"]}),
     # review: never anything resolution does not write
     lambda s: _url(s, status="omitted"),
     lambda s: s["rows"][0].update({"fields": {}}),
     lambda s: _url(s, value={"text": "https://other.example"}),
     lambda s: _url(s, value={"text": "javascript:alert(1)"}, display="javascript:alert(1)"),
     lambda s: _url(s, value={"text": "HTTPS://sam.example"}, display="HTTPS://sam.example"),
     lambda s: _url(s, value=None),
     lambda s: _url(s, value={"text": None}, display=None)],
    ids=["another field", "parts", "limits", "two rows of one identity", "omitted",
         "no url", "a value other than shown", "not a web address", "not as written",
         "no value", "no display"],
)  # fmt: skip
def test_frozen_websites_content_holds_only_what_resolution_writes(tamper):
    frozen = gs.section_to_content(ss.resolve_section("websites", [profile(*LINKS)]),
                                   root="#websites")  # fmt: skip
    tamper(frozen)
    with pytest.raises(gs.Refused):
        ws.plan(frozen)


def test_a_line_break_or_carriage_return_is_never_typed_into_its_box():
    frozen = gs.section_to_content(ss.resolve_section("websites", [profile(LINKS[1])]),
                                   root="#websites")  # fmt: skip
    for bad in ("https://sam.example/\nx", "https://sam.example/\rx", " "):
        frozen["rows"][0]["fields"]["url"]["display"] = bad
        with pytest.raises(ws.Refused):
            ws.plan(frozen)


def test_a_stop_names_your_websites():
    assert wd_adapter._stops({"kind": "websites"}) == (
        wd_adapter.WEBSITES_UNUSABLE, wd_adapter.WEBSITES_ENTRIES_BEYOND,
        wd_adapter.WEBSITES_PREFILLED, wd_adapter.WEBSITES_NOT_ENTERED)  # fmt: skip
    op = ws.plan(gs.section_to_content(ss.resolve_section("websites", [profile(LINKS[1])]),
                                       root="#websites")).rows[0].ops[0]  # fmt: skip
    assert ws._what(op) == "websites: url"


# ---------------------------------------------------------------------------- the package


def with_links(api, links: list[str]) -> None:
    """The synthetic candidate's profile (`synthetic_candidate`), its links replaced."""
    r = api.put("/profile", json=PROFILE | {"links": links})
    assert r.status_code == 200, r.text


def application(api, receiver, variant="other_sections", *, mode=None, approved=True,
                links=LINKS, work=(), schooling=()) -> str:  # fmt: skip
    """The variant switched on (a wizard variant, or the single page's mode), your profile's
    links (and work history or education, when given), then a Workday-style application on a
    posting of its own, captured, answered and, when `approved`, approved."""
    receiver.config(**({"mode": mode} if mode else {"wizard": variant}))
    synthetic_candidate(api)
    with_links(api, list(links))
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


def frozen_websites(c: dict) -> dict | None:
    return next((s for s in c.get("sections") or [] if s["kind"] == "websites"), None)


def test_the_package_shows_each_link_as_an_entry_and_needs_nothing_from_you(api, receiver):
    app_id = application(api, receiver, approved=False)
    c = content(api, app_id)
    assert not c["unresolved"] and not c["validation_errors"]
    sec = frozen_websites(c)
    assert (sec["root"], sec["step"]) == ("#websites", "My Experience") and "parts" not in sec
    assert [r["fields"]["url"] for r in sec["rows"]] == [
        {"status": "resolved", "value": {"text": a}, "display": a} for a in ADDRESSES]  # fmt: skip
    assert "websites_section" not in {a["key"] for a in c["answers"]}
    assert pk.SCHEMA_VERSION == 3 and paths(c) - SHAPES[3] <= {".answers[].widget", ".wizard"}
    assert approve(api, app_id).status_code == 200


def test_with_no_link_the_section_holds_no_entry(api, receiver):
    app_id = application(api, receiver, approved=False, links=())
    c = content(api, app_id)
    assert not c["unresolved"] and frozen_websites(c)["rows"] == []
    assert approve(api, app_id).status_code == 200


def test_one_the_page_requires_with_no_link_blocks_approval(api, receiver):
    app_id = application(api, receiver, "websites_required", approved=False, links=())
    c = content(api, app_id)
    assert c["unresolved"] == ["section:websites"] and frozen_websites(c) is None
    assert {e["key"]: e["message"] for e in c["validation_errors"]}["section:websites"] == (
        pk.SECTION_REQUIRED["websites"])  # fmt: skip
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []


def test_a_link_that_is_not_a_web_address_blocks_approval_naming_it(api, receiver):
    app_id = application(api, receiver, approved=False, links=[LINKS[1], "my portfolio"])
    c = content(api, app_id)
    ((key, why),) = [(e["key"], e["message"]) for e in c["validation_errors"]]
    assert key.startswith("section:websites:link-") and key.endswith(":url")
    assert c["unresolved"] == [key] and "“my portfolio”" in why
    assert frozen_websites(c) is None and approve(api, app_id).status_code != 200


def test_a_profile_not_yet_approved_sends_no_link(api, receiver):
    app_id = application(api, receiver, approved=False)
    with SessionLocal() as db:
        prof = db.get(CandidateProfile, uuid.UUID(api.get("/profile").json()["id"]))
        prof.approval_status = Approval.proposed
        db.commit()
    assert frozen_websites(content(api, app_id))["rows"] == []


def test_changing_your_links_retires_the_approval_at_once_and_says_what_changed(api, receiver):
    """D140's rule for a record's change, for your links: an approval of the old ones is retired
    when you save, and the version diff names the entry added or removed."""
    app_id = application(api, receiver)
    with_links(api, LINKS[:2])
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is None
    version = api.get(f"/applications/{app_id}/package").json()["package"]["version"]
    diff = api.get(f"/applications/{app_id}/package/diff",
                   params={"from_version": version - 1, "to_version": version}).json()  # fmt: skip
    (sec,) = diff["sections"]
    assert sec["kind"] == "websites" and sec["status"] == "changed"
    assert [(r["label"], r["change"]) for r in sec["rows"]] == [(ADDRESSES[2], "removed")]


def test_another_account_s_links_never_reach_your_application(api, other_api, receiver):
    """D166 review (every query by user_id; another account's access is a 404): another account's
    links are never your package's, a change to them retires nothing of yours, and your package
    is not theirs to read."""
    app_id = application(api, receiver)
    before = api.get(f"/applications/{app_id}/package").json()["package"]
    synthetic_candidate(other_api)
    with_links(other_api, ["https://other.example/them"])
    after = api.get(f"/applications/{app_id}/package").json()["package"]
    assert (after["version"], after["content_hash"]) == (before["version"], before["content_hash"])
    with SessionLocal() as db:
        assert pk.active_approval(db, pk.latest_package(db, uuid.UUID(app_id))) is not None
    assert [r["fields"]["url"]["display"] for r in frozen_websites(after["content"])["rows"]] == (
        ADDRESSES)  # fmt: skip
    assert other_api.get(f"/applications/{app_id}/package").status_code == 404


def test_a_section_that_now_waits_for_you_is_said_so_in_the_diff(api, receiver):
    """D140's diff for a websites section the form gains, required, with no link: a checkpoint in
    the new version only, frozen in neither, said as such, never "nothing changed"."""
    app_id = application(api, receiver, "plain", approved=False, links=())
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    receiver.config(wizard="websites_required")
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    c = content(api, app_id)
    assert "section:websites" in c["unresolved"]
    diff = api.get(f"/applications/{app_id}/package/diff").json()
    assert [(s["kind"], s["status"]) for s in diff["sections"]] == [("websites", "needs_you")]


# ---------------------------------------------------------------------------- the ledger


def accepted(receiver) -> dict:
    (row,) = receiver.ledger()["acceptances"]
    return row["fields"]


def sent_web(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if WEB.fullmatch(k)}


def never(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if NEVER.fullmatch(k)}


def page_2(receiver) -> dict:
    (fields,) = [d["fields"] for d in drafts(receiver.ledger()) if d["page"] == 2]
    return fields


def test_your_links_are_entered_and_sent_as_approved(api, receiver):
    app_id = application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 1
    assert sent_web(page_2(receiver)) == SENT and never(page_2(receiver)) == {}
    assert sent_web(accepted(receiver)) == SENT and never(accepted(receiver)) == {}
    assert all(r["mismatched"] == 0 for r in rows(aid, "step"))
    entered = [(d["section"], d["row"], d["field"]) for d in rows(aid, "disclosure")
               if d.get("kind") == "section_field"]  # fmt: skip
    assert entered == [("websites", i, "url") for i in range(3)]


def test_on_the_single_page_they_are_sent(api, receiver):
    app_id = application(api, receiver, mode="wd_other_sections")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(accepted(receiver)) == SENT and never(accepted(receiver)) == {}


def test_with_no_link_nothing_is_entered_and_it_is_sent(api, receiver):
    app_id = application(api, receiver, links=())
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(page_2(receiver)) == {} and sent_web(accepted(receiver)) == {}


def test_one_the_page_requires_is_filled_and_sent(api, receiver):
    app_id = application(api, receiver, "websites_required", links=LINKS[1:2])
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(accepted(receiver)) == {"web[0].url": ADDRESSES[1]}


def test_an_empty_entry_already_there_is_filled_in_place(api, receiver):
    app_id = application(api, receiver, "websites_entry_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(page_2(receiver)) == SENT and sent_web(accepted(receiver)) == SENT


def test_with_fewer_links_than_the_empty_entries_shown_it_stops_before_anything_is_entered(
    api, receiver
):
    """An empty entry already on the page and no link to put in it: NoEfforts never removes one,
    and the page's own checks would refuse it empty, so the attempt stops before anything is
    entered."""
    app_id = application(api, receiver, "websites_entry_at_load", links=())
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert wd_adapter.WEBSITES_ENTRIES_BEYOND in attempt(aid).outcome_detail
    assert attempt(aid).disclosure_started_at is None


def test_beside_them_your_work_history_is_sent(api, receiver):
    app_id = application(api, receiver, "other_sections_and_experience", work=(WORK_CURRENT,))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert page_2(receiver)["work[0].title"] == "Clinic Assistant"
    assert sent_web(page_2(receiver)) == SENT


def test_beside_them_your_education_is_sent(api, receiver):
    app_id = application(api, receiver, "other_sections_and_education",
                         schooling=(MASTER, BACHELOR))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert {k: v for k, v in page_2(receiver).items() if k.startswith("edu[")} == EDU_SENT
    assert sent_web(page_2(receiver)) == SENT


def test_an_entry_a_parsed_resume_adds_stops_before_its_page_is_sent(api, receiver):
    """The resume's parse adds a Websites entry with a value of its own after approval: the
    entry would be sent unapproved, so the attempt stops before anything of the section is
    entered, page 2 never sent."""
    app_id = application(api, receiver, "websites_parse")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert wd_adapter.WEBSITES_PREFILLED in attempt(aid).outcome_detail
    assert not [d for d in rows(aid, "disclosure") if d.get("kind") == "section_field"]


def test_a_section_the_page_requires_since_approval_pauses_before_anything_is_entered(
    api, receiver
):
    app_id = application(api, receiver)
    receiver.config(wizard="websites_required")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_empty_entry_shown_since_approval_is_filled_in_place(api, receiver):
    """The same form (an empty entry is read as before, D149): your first link goes in it."""
    app_id = application(api, receiver)
    receiver.config(wizard="websites_entry_at_load")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(page_2(receiver)) == SENT


# ---------------------------------------------------------------------------- review: after typing


def nowhere(receiver, value: str) -> bool:
    """The value reached the employer nowhere: no page's draft, no acceptance."""
    led = receiver.ledger()
    return not [d for d in drafts(led) if value in d["fields"].values()] and not [
        a for a in led["acceptances"] if value in a["fields"].values()]  # fmt: skip


def test_a_value_the_page_keeps_once_a_website_is_typed_stops_before_its_page_is_sent(
    api, receiver
):
    """D166 review: once a website is typed the page keeps a value of its own in a hidden field
    outside the section, named as an entry's: the form read again before page 2's Next is no
    longer the approved one (the section is then its checkpoint), so the attempt stops with page 2
    never sent, and the value reaches the employer nowhere."""
    app_id = application(api, receiver, "websites_hidden_after_typing")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert FORM_CHANGED in attempt(aid).outcome_detail
    assert nowhere(receiver, UNAPPROVED)


def test_on_the_single_page_a_value_kept_once_typed_stops_before_the_final_click(api, receiver):
    app_id = application(api, receiver, mode="wd_websites_hidden_after_typing")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") not in ("confirmed", "unknown")
    led = receiver.ledger()
    assert led["accepted"] == 0 and posts(led, "/apply") == 0
    assert FORM_CHANGED in attempt(aid).outcome_detail
    assert nowhere(receiver, UNAPPROVED)


def test_an_entry_the_page_adds_once_a_website_is_typed_stops_before_its_page_is_sent(
    api, receiver
):
    """D166 review: once your one link is typed the page adds an entry holding a value of its
    own: the section shows an entry beyond the plan when its page is read back, so the attempt
    stops with page 2 never sent."""
    app_id = application(api, receiver, "websites_added_after_typing", links=LINKS[1:2])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply") == 0
    assert nowhere(receiver, UNAPPROVED)


def test_an_entry_the_page_adds_is_given_your_next_link_and_holds_nothing_else(api, receiver):
    """With more links, the entry the page adds is where your next link goes (an entry already
    there is filled in place, D149): the page's own value is replaced, and only your links are
    sent."""
    app_id = application(api, receiver, "websites_added_after_typing")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(page_2(receiver)) == SENT and sent_web(accepted(receiver)) == SENT
    assert nowhere(receiver, UNAPPROVED)


def test_a_scheme_in_capitals_is_sent_in_lower_case_and_accepted(api, receiver):
    """D166 review: "Https://", as a phone writes it, approved as written was refused by the
    page's own check after it was sent; it is now shown and sent in lower case."""
    app_id = application(api, receiver, mode="wd_other_sections",
                         links=["Https://sam.example/portfolio"])  # fmt: skip
    rows_ = frozen_websites(content(api, app_id))["rows"]
    assert [r["fields"]["url"]["display"] for r in rows_] == ["https://sam.example/portfolio"]
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent_web(accepted(receiver)) == {"web[0].url": "https://sam.example/portfolio"}
