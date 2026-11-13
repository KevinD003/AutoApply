"""D157: a length limit (`maxlength`) on a Workday-style Work Experience entry's typed part
(FIXTURE ASSUMPTION FA7, fixtures/ats_receiver/workday_like.py) is read when the form is read,
and your record held to it: a value longer than the page accepts is yours to shorten (never cut,
never sent cut), one within it is entered whole. Before D157 any such limit made the whole form
one checkpoint (apply on the employer's site). A limit is read only as the browser reads it, and
a length counted as the form sends it (`forms.sent_len`: UTF-16 code units, each line break the
two the form sends), never less than the browser's own count.

The receiver's own ledger is the oracle for what reached the employer (its page-2 draft rows and
acceptances). Passing here shows fixture compatibility only, never how a real Workday tenant
behaves. Synthetic candidate data only."""

import datetime
import sys

import pytest
from pydantic import ValidationError

from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_sections as gs
from app.modules.execution.adapters import workday_sections as ws
from app.modules.preparation import structured_sections as ss
from app.modules.preparation import workday
from app.modules.preparation.forms import (
    LIMITED_FIELDS,
    MAX_LIMIT,
    SectionSpec,
    _Node,
    extract_form_schema,
    form_fingerprint,
    sent_len,
)
from tests.execution_harness import ROOT as REPO
from tests.execution_harness import Receiver, queue, synthetic_candidate
from tests.test_workday_entry_details import CURRENT_D, PAST_D, frozen_parts, lines
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
from tests.test_workday_wizard import approve

sys.path.insert(0, str(REPO / "fixtures" / "ats_receiver"))
import workday_like  # noqa: E402

LIMITS = {"title": 40, "company": 40, "location": 30, "from": 7, "to": 7, "description": 200}
FROZEN_LIMITS = {"company_name": 40, "description": 200, "location": 30, "title": 40}
assert workday_like.WORK_LIMITS == LIMITS  # the oracle's own copy


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def limited(template: str, limits: dict, i: str = "__i__") -> str:
    """The entry with these attributes on its parts' controls ({part: attrs})."""
    for part, attrs in limits.items():
        name = f'name="work[{i}].{part}"'
        assert template.count(name) == 1, part
        template = template.replace(name, name + attrs)
    return template


def maxlengths(limits: dict) -> dict:
    return {part: f' maxlength="{v}"' for part, v in limits.items()}


# ---------------------------------------------------------------------------- capture


def test_an_entry_s_length_limits_are_read_with_the_section():
    """Before D157 any `maxlength` on an entry's control made the form one checkpoint."""
    schema, fields = read(form_page(section(), limited(entry(), maxlengths(LIMITS))))
    (sec,) = schema.sections
    assert sec.limits == FROZEN_LIMITS  # by the frozen row's names; a date's never recorded
    assert workday.WORK_KEY not in fields
    assert sec.model_dump()["limits"] == dict(sorted(FROZEN_LIMITS.items()))


def test_limits_are_written_and_fingerprinted_only_when_set():
    plain, _ = read(form_page(section()))
    assert plain.sections[0].limits == {} and "limits" not in plain.sections[0].model_dump()
    one, _ = read(form_page(section(), limited(entry(), maxlengths({"title": 40}))))
    other, _ = read(form_page(section(), limited(entry(), maxlengths({"title": 41}))))
    dates, _ = read(form_page(section(), limited(entry(), maxlengths({"from": 7, "to": 9}))))
    assert one.sections[0].limits == {"title": 40} and other.sections[0].limits == {"title": 41}
    assert dates.sections[0].limits == {}  # a date that fits MM/YYYY: nothing to hold a record to
    prints = {form_fingerprint(s) for s in (plain, one, other)}
    assert len(prints) == 3 and form_fingerprint(dates) == form_fingerprint(plain)


@pytest.mark.parametrize("written, limit", [
    (" 40 ", 40),
    ("\t40\n", 40),
    ("040", 40),
    ("0" * 5000 + "40", 40),
    ("524288", 524288),  # as some page frameworks write "no practical limit"
    (str(MAX_LIMIT), MAX_LIMIT),
], ids=["spaces", "ascii-whitespace", "leading-zero", "thousands-of-leading-zeros", "large",
        "largest"])  # fmt: skip
def test_a_limit_is_read_as_the_browser_reads_it(written, limit):
    schema, _ = read(form_page(section(), limited(entry(), {"title": f' maxlength="{written}"'})))
    assert schema.sections[0].limits == {"title": limit}


@pytest.mark.parametrize("attrs", [
    {"title": ' maxlength="0"'},
    {"title": ' maxlength=""'},
    {"title": ' maxlength="abc"'},
    {"title": ' maxlength="1e3"'},
    {"title": ' maxlength="-5"'},
    {"title": ' maxlength="+40"'},  # the browser reads 40
    {"title": ' maxlength="40abc"'},  # the browser reads 40
    {"title": ' maxlength="4 0"'},  # the browser reads 4
    {"title": ' maxlength=" 40"'},  # the browser reads no limit
    {"title": ' maxlength="　40"'},
    {"title": ' maxlength="٤٠"'},  # another script's digits: no limit for the browser
    {"title": ' maxlength="²"'},
    {"title": f' maxlength="{MAX_LIMIT + 1}"'},  # more than the browser reads
    {"title": ' maxlength="' + "9" * 5000 + '"'},  # more digits than Python converts
    {"title": ' maxlength="10" maxlength="40"'},  # the browser keeps the first
    {"title": ' maxlength="40" maxlength="10"'},
    {"title": ' type="text"'},  # any attribute written twice on an entry's control
    {"current": ' maxlength="3"'},
    {"from": ' maxlength="6"'},
    {"to": ' maxlength="5"'},
    {"title": ' minlength="2"'},
    {"description": ' pattern="[a-z]+"'},
], ids=["zero", "empty", "word", "exponent", "negative", "plus", "trailing-text", "inner-space",
        "no-break-space", "ideographic-space", "other-digits", "superscript", "too-large",
        "thousands-of-digits", "twice-smaller-first", "twice-larger-first", "an-attribute-twice",
        "on-the-box", "from-too-short", "to-too-short", "minlength", "pattern"])  # fmt: skip
def test_a_limit_nothing_can_honour_is_one_checkpoint(attrs):
    """A limit NoEfforts cannot read as the browser does, one on a box, one a date cannot fit,
    and any other constraint on a typed value stay refused when the form is read (D149's rule),
    never an error of capture."""
    schema, fields = read(form_page(section(), limited(entry(), attrs)))
    assert schema.sections == [] and workday.WORK_KEY in fields


@pytest.mark.parametrize("written, read_as", [
    (None, None),
    ("40", 40),
    (" 40\t", 40),
    (str(MAX_LIMIT), MAX_LIMIT),
    ("0", False),
    ("000", False),
    (str(MAX_LIMIT + 1), False),
    ("9" * 5000, False),
    ("\u0664\u0660", False),
    ("+40", False),
], ids=["none", "digits", "whitespace", "largest", "zero", "zeros", "too-large",
        "thousands-of-digits", "other-digits", "plus"])  # fmt: skip
def test_a_control_s_limit_is_its_number_none_or_unreadable(written, read_as):
    """`_limit` itself: the number, None (no limit), or False (a limit never guessed at)."""
    got = workday._limit(_Node("input", {} if written is None else {"maxlength": written}, None))
    if read_as is None or isinstance(read_as, bool):
        assert got is read_as
    else:
        assert got == read_as and not isinstance(got, bool)


@pytest.mark.parametrize("on_page, same", [
    ({"title": 40}, True),
    ({"title": 39}, False),
    ({}, False),
    ({"title": 40, "location": 30}, False),
    ({"title": 40, "from": 10}, True),  # a date's limit, which MM/YYYY fits, never binds
], ids=["same", "otherwise", "none", "more", "a-date-limit-that-fits"])  # fmt: skip
def test_an_entry_on_the_page_limited_otherwise_is_one_checkpoint(on_page, same):
    """NoEfforts fills an entry already on the page in place, as resolved for the template."""
    at_load = limited(entry("0"), maxlengths(on_page), "0") if on_page else entry("0")
    html = form_page(section(at_load), limited(entry(), maxlengths({"title": 40})))
    schema, fields = read(html)
    if same:
        assert schema.sections[0].limits == {"title": 40} and workday.WORK_KEY not in fields
    else:
        assert schema.sections == [] and workday.WORK_KEY in fields


@pytest.mark.parametrize("attrs", [
    {"title": ' pattern="[A-Z]+"'},
    {"company": ' minlength="5"'},
], ids=["pattern", "minlength"])  # fmt: skip
def test_an_entry_on_the_page_with_another_constraint_is_one_checkpoint(attrs):
    """D157, found by its review: minlength and pattern were refused on the template only, never
    on an entry already on the page, which NoEfforts fills in place."""
    html = form_page(section(limited(entry("0"), attrs, "0")))
    schema, fields = read(html)
    assert schema.sections == [] and workday.WORK_KEY in fields


@pytest.mark.parametrize("written, read_as", [
    ("40", 40),
    ("040", 40),
    ("100000", 100_000),
    ("²", None),
    ("٤٠", None),
    ("9" * 5000, None),
    ("0", None),
    ("100001", None),
    ("524288", None),
], ids=["digits", "leading-zero", "largest", "superscript", "other-digits", "thousands-of-digits",
        "zero", "too-large", "framework-default"])  # fmt: skip
def test_an_ordinary_question_s_limit_never_breaks_reading_the_form(written, read_as):
    """D157, found by its review: `int()` failed on a superscript two and on more digits than
    Python converts, and read other scripts' digits the browser does not; a limit of 0 or above
    `FormField`'s bound failed the whole form. Such a limit is not recorded."""
    html = (f'<form><label for="n">Nickname</label><input id="n" name="nickname" type="text" '
            f'maxlength="{written}"></form>')  # fmt: skip
    (field,) = extract_form_schema(html).fields
    assert field.max_length == read_as


# ---------------------------------------------------------------------------- the spec


@pytest.mark.parametrize("kw", [
    {"limits": {"start_date": 7}},
    {"limits": {"title": 0}},
    {"limits": {"title": MAX_LIMIT + 1}},
    {"limits": {"title": True}},
    {"limits": {"title": "40"}},
    {"limits": {"location": 30}},  # the entry does not ask it
    {"kind": "education", "limits": {"title": 40}},
], ids=["date", "zero", "too-large", "bool", "string", "part-not-asked", "education"])  # fmt: skip
def test_a_section_s_limits_are_known_fields_in_range(kw):
    with pytest.raises(ValidationError):
        SectionSpec(**({"kind": "employment", "root": "#w"} | kw))
    ok = SectionSpec(kind="employment", root="#w", parts=["location"],
                     limits={"title": MAX_LIMIT, "location": 1})  # fmt: skip
    assert ok.limits == {"title": MAX_LIMIT, "location": 1}
    assert list(ok.model_dump()["limits"]) == ["location", "title"]  # always written sorted
    assert tuple(sorted(LIMITED_FIELDS)) == LIMITED_FIELDS


# ---------------------------------------------------------------------------- resolution


class Rec:
    def __init__(self, **kw):
        self.id = "r1"
        self.employer = kw.get("employer", "Example Health")
        self.title = kw.get("title", "Clinic Assistant")
        self.start_date = kw.get("start_date", datetime.date(2019, 1, 1))
        self.end_date = None
        self.is_current = True
        self.location = kw.get("location")
        self.description = kw.get("description")
        self.approval_status = "approved"


def test_a_record_longer_than_the_page_accepts_is_yours_to_shorten():
    rec = Rec(title="T" * 41, description="d" * 10)
    row = ss.resolve_employment_row(rec, ("description",), (), {"title": 40, "description": 10})
    title = row.fields["title"]
    assert title.status == "needs_user" and "40" in title.explanation and "41" in title.explanation
    assert "a line break or an emoji counts as two" in title.explanation
    assert "T" * 5 not in title.explanation  # its length, never its text
    assert row.fields["description"].status == "resolved"  # exactly at its limit
    assert row.fields["company_name"].status == "resolved"  # no limit on it here


@pytest.mark.parametrize("text, limit, ok", [
    ("ab\r\ncd", 6, True),  # one line break, held as LF, sent as CRLF: 6
    ("ab\ncd", 5, False),  # the browser would keep it (5), its form sends 6
    ("a\U0001f600cd", 5, True),  # outside the Basic Multilingual Plane: 2
    ("a\U0001f600cde", 5, False),
    ("abcdef", 5, False),
], ids=["line-break-fits", "line-break-over", "emoji-fits", "emoji-over",
        "plain-over"])  # fmt: skip
def test_length_is_counted_as_the_form_sends_it(text, limit, ok):
    rec = Rec(description=text)
    row = ss.resolve_employment_row(rec, ("description",), (), {"description": limit})
    assert (row.fields["description"].status == "resolved") is ok
    assert sent_len("a\U0001f600") == 3 and sent_len("a\nb") == 4 and sent_len("") == 0


OPTIONS = ss.EducationOptions(degrees=(ss.SectionOption("d1", "Bachelor's Degree"),))


@pytest.mark.parametrize("kind, kw", [
    ("employment", {"limits": {"start_date": 7}}),
    ("employment", {"limits": {"location": 30}}),  # not asked
    ("employment", {"limits": {"title": True}}),
    ("employment", {"limits": {"title": 0}}),
    ("employment", {"limits": {"title": MAX_LIMIT + 1}}),
    ("education", {"limits": {"title": 40}, "options": OPTIONS}),
], ids=["date", "part-not-asked", "bool", "zero", "too-large", "education"])  # fmt: skip
def test_a_section_with_limits_never_named_is_not_supported(kind, kw):
    assert ss.resolve_section(kind, [], **kw).supported is False
    assert ss.resolve_section(kind, [], **(kw | {"limits": {}})).supported is True
    assert ss.resolve_section("employment", [], limits={"title": 40}).supported is True


# ---------------------------------------------------------------------------- frozen content


def with_limits(limits, **row) -> dict:
    return frozen([frozen_row(**row)], limits=limits)


def described(description: str, limit: int) -> dict:
    return frozen_parts(description=description, parts=("description",)) | {
        "limits": {"description": limit}
    }


def unlocated(limit) -> dict:
    """An entry asking Location, which the row does not hold (omitted): only the limit's own
    shape can refuse it."""
    return frozen_parts(location=None, parts=("location",)) | {"limits": {"location": limit}}


@pytest.mark.parametrize("data", [
    with_limits([40]),
    with_limits({}),
    with_limits({"start_date": 7}),
    unlocated(True),
    unlocated(0),
    unlocated(MAX_LIMIT + 1),
    unlocated("30"),
    with_limits({"location": 30}),  # no part named
    with_limits({"title": 40}, title="T" * 41),  # a value longer than its limit
    with_limits({"title": 40}, title="T" * 39 + "\U0001f600"),  # 41 as the browser counts
    described("abcd\nefghi", 10),  # 11 as its form sends it (the browser counts 10)
    {**with_limits({"title": 40}), "kind": "education", "rows": []},
], ids=["list", "empty", "date", "bool", "zero", "too-large", "string", "part-not-named",
        "too-long", "too-long-emoji", "too-long-line-break", "education"])  # fmt: skip
def test_frozen_limits_are_checked_before_anything_is_entered(data):
    with pytest.raises(gs.Refused):
        gs.section_from_content(data)
    gs.section_from_content(unlocated(30))  # the same shape, a limit in range: accepted


def test_a_frozen_value_within_its_limit_is_planned_and_greenhouse_never_plans_one():
    data = with_limits({"title": 16, "company_name": 14})  # "Clinic Assistant", "Example Health"
    (row,) = ws.plan(data).rows
    assert ("title", "Clinic Assistant") in [(op.field, op.value) for op in row.ops]
    (row,) = ws.plan(described("abcd\nefghi", 11)).rows
    assert ("description", "abcd\nefghi") in [(op.field, op.value) for op in row.ops]
    with pytest.raises(gs.Refused):
        gs.plan_content_section(data)


def test_the_plan_holds_each_value_to_its_limit_past_the_content_check(monkeypatch):
    """Defence in depth: with the frozen content's own check out of the way, the plan still
    refuses a value its page would cut."""
    monkeypatch.setattr(gs, "validate_content_section", lambda data: None)
    with pytest.raises(gs.Refused, match="title: longer than the page accepts"):
        ws.plan(with_limits({"title": 15}))
    with pytest.raises(gs.Refused, match="description: longer than the page accepts"):
        ws.plan(described("abcd\nefghi", 10))


@pytest.mark.parametrize("field, kind, text, limit", [
    ("title", "text", "T" * 41, 40),
    ("title", "text", "T" * 39 + "\U0001f600", 40),
    ("description", "lines", "abcd\nefghi", 10),
], ids=["plain", "emoji", "line-break"])  # fmt: skip
def test_the_executor_refuses_a_value_its_page_would_cut(field, kind, text, limit):
    fr = ss.FieldResult(field, "resolved", value={"text": text}, display=text)
    with pytest.raises(gs.Refused):
        ws._op(0, field, kind, "#w [x]", fr, limit)
    assert ws._op(0, field, kind, "#w [x]", fr, limit + 1).value == text


# ---------------------------------------------------------------------------- through the runner


def test_your_work_history_within_the_page_s_limits_is_sent(api, receiver):
    """Before D157 the form was refused when it was read (apply on the employer's site)."""
    app_id = experience_application(api, receiver, "experience_limits",
                                    records=(CURRENT_D, PAST_D))  # fmt: skip
    (sec,) = content(api, app_id)["sections"]
    assert sec["limits"] == dict(sorted(FROZEN_LIMITS.items()))
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    sent = work(page_2(receiver.ledger()))
    assert sent["work[0].title"] == CURRENT["title"] and sent["work[1].title"] == PAST["title"]
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize("part, value", [
    ("title", "N" * 38 + "\U0001f600"),  # 40: one character outside the BMP counts 2
    ("description", "x" * 197 + "\n" + "y"),  # 200 as its form sends it (CRLF), 199 for the browser
], ids=["title-with-emoji", "description-with-a-line-break"])  # fmt: skip
def test_a_value_at_the_page_s_limit_is_sent_whole(api, receiver, part, value):
    """Exactly at its limit as the form sends it: kept whole by the page, accepted by its own
    checks on what they receive."""
    assert sent_len(value) == LIMITS[part]
    record = {"title": value} if part == "title" else {"description": value}
    app_id = experience_application(api, receiver, "experience_limits",
                                    records=(CURRENT_D | record,))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert lines(work(page_2(receiver.ledger()))[f"work[0].{part}"]) == value
    assert receiver.ledger()["accepted"] == 1


@pytest.mark.parametrize("long_role", [
    "Night shift lead. " * 12,  # 216 characters, the page accepts 200
    "x" * 198 + "\n" + "y",  # 200 for the browser, 201 as its form sends it
], ids=["plain", "a-line-break-counted-as-sent"])  # fmt: skip
def test_a_record_longer_than_the_page_accepts_blocks_approval(api, receiver, long_role):
    app_id = experience_application(api, receiver, "experience_limits",
                                    records=(CURRENT_D | {"description": long_role}, PAST_D),
                                    approved=False)  # fmt: skip
    c = content(api, app_id)
    keys = [k for k in c["unresolved"] if k.startswith("section:employment:")]
    assert len(keys) == 1 and keys[0].endswith(":description")
    assert approve(api, app_id).status_code == 409
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_an_entry_on_the_page_limited_otherwise_is_refused_when_the_form_is_read(api, receiver):
    app_id = experience_application(api, receiver, "experience_limits_at_load", approved=False)
    c = content(api, app_id)
    assert c.get("sections", []) == [] and workday.WORK_KEY in c["unresolved"]
    assert approve(api, app_id).status_code == 409
    assert receiver.ledger()["disclosures"] == []


def test_a_form_given_by_hand_never_names_limits(api):
    synthetic_candidate(api)
    job = api.post("/jobs", json={"title": "Manual", "employer": "Example Health"}).json()["job"]
    sec = {"kind": "employment", "root": "#w", "limits": {"title": 40}}
    form = {"title": "Manual (fictional)", "sections": [sec],
            "fields": [{"key": "nickname", "label": "Nickname", "type": "text"}]}  # fmt: skip
    r = api.post(f"/jobs/{job['id']}/form", json={"form": form})
    assert r.status_code == 400 and "'limits' is set by NoEfforts only" in r.text


def test_the_stand_in_refuses_a_part_longer_than_its_limit():
    """The oracle's own check, on what the page receives: a part longer than WORK_LIMITS is
    refused, within it accepted; a line break arrives as CRLF and counts 2."""
    ok = {"work[0].title": "T" * 40, "work[0].company": "C", "work[0].from": "01/2019",
          "work[0].current": "1", "work[0].description": "x" * 198 + "\r\n"}  # fmt: skip
    assert workday_like._work_errors(ok, False, False, workday_like.WORK_LIMITS) == []
    over = ok | {"work[0].title": "T" * 41, "work[0].description": "x" * 199 + "\r\n"}
    assert workday_like._work_errors(over, False, False, workday_like.WORK_LIMITS) == [
        "Work Experience 1: title is too long",
        "Work Experience 1: description is too long",
    ]
    assert workday_like._work_errors(over, False) == []  # no limit: accepted


# ---------------------------------------------------------------------------- the page
# Last in the module: its browser (module-scoped) holds Playwright's synchronous API until the
# module ends, and the runner opens its own.

LIMIT_ON_ADD = """<script>new MutationObserver(() => {
  for (const e of document.querySelectorAll('[name$=".title"]')) e.maxLength = 5;
}).observe(document.querySelector('[data-entries]'), {childList: true});</script>"""


@pytest.mark.parametrize("extra, kept", [(LIMIT_ON_ADD, ""), ("", "Clinic Assistant")],
                         ids=["limited-on-add", "no-limit"])  # fmt: skip
def test_a_limit_the_page_sets_on_the_entry_it_adds_stops_before_anything_is_cut(
    page,  # noqa: F811
    extra,
    kept,
):
    """D157, found by its review: a page's script may limit the entry it adds, after the form was
    read; the control's own limit is read before each value is typed, so nothing cut is ever
    entered (a page that saves as you type would save it cut)."""
    page.set_content(section_page(extra=extra))
    entries = ws.plan(frozen([frozen_row()]))
    if kept:
        ws.apply(page, entries, ROOT)
    else:
        with pytest.raises(gs.Refused, match="title is longer than the page now accepts"):
            ws.apply(page, entries, ROOT)
    assert page.locator('[name="work[0].title"]').input_value() == kept
