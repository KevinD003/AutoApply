"""D157: a length limit (`maxlength`) on a Workday-style Work Experience entry's typed part
(FIXTURE ASSUMPTION FA7, fixtures/ats_receiver/workday_like.py) is read when the form is read,
and your record held to it: a value longer than the page accepts is yours to shorten (never cut,
never sent cut), one within it is entered whole. Before D157 any such limit made the whole form
one checkpoint (apply on the employer's site). Lengths are counted as the browser counts them
(UTF-16 code units; a line break, as NoEfforts writes it, one).

The receiver's own ledger is the oracle for what reached the employer (its page-2 draft rows and
acceptances). Passing here shows fixture compatibility only, never how a real Workday tenant
behaves. Synthetic candidate data only."""

import re

import pytest
from pydantic import ValidationError

from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_sections as gs
from app.modules.execution.adapters import workday_sections as ws
from app.modules.preparation import structured_sections as ss
from app.modules.preparation import workday
from app.modules.preparation.forms import LIMITED_FIELDS, SectionSpec, form_fingerprint, utf16_len
from tests.execution_harness import Receiver, queue
from tests.test_workday_entry_details import CURRENT_D, PAST_D
from tests.test_workday_experience import (
    CURRENT,
    PAST,
    content,
    entry,
    experience_application,
    form_page,
    frozen,
    frozen_row,
    page_2,
    read,
    section,
    work,
)
from tests.test_workday_wizard import approve

LIMITS = {"title": 40, "company": 40, "location": 30, "from": 7, "to": 7, "description": 200}
FROZEN_LIMITS = {"company_name": 40, "description": 200, "location": 30, "title": 40}


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
        template, n = re.subn(rf'(name="work\[{re.escape(i)}\]\.{part}")', rf"\1{attrs}", template)
        assert n == 1, part
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


@pytest.mark.parametrize("attrs", [
    {"title": ' maxlength="0"'},
    {"title": ' maxlength="abc"'},
    {"title": ' maxlength="1e3"'},
    {"title": ' maxlength="-5"'},
    {"title": ' maxlength="100001"'},
    {"title": ' maxlength="²"'},
    {"current": ' maxlength="3"'},
    {"from": ' maxlength="6"'},
    {"to": ' maxlength="5"'},
    {"title": ' minlength="2"'},
    {"description": ' pattern="[a-z]+"'},
], ids=["zero", "word", "exponent", "negative", "too-large", "superscript", "on-the-box",
        "from-too-short", "to-too-short", "minlength", "pattern"])  # fmt: skip
def test_a_limit_nothing_can_honour_is_one_checkpoint(attrs):
    """A limit NoEfforts cannot read, one on a box, one a date cannot fit, and any other
    constraint on a typed value stay refused when the form is read (D149's rule)."""
    schema, fields = read(form_page(section(), limited(entry(), attrs)))
    assert schema.sections == [] and workday.WORK_KEY in fields


@pytest.mark.parametrize("on_page, same", [
    ({"title": 40}, True),
    ({"title": 39}, False),
    ({}, False),
    ({"title": 40, "location": 30}, False),
], ids=["same", "otherwise", "none", "more"])  # fmt: skip
def test_an_entry_on_the_page_limited_otherwise_is_one_checkpoint(on_page, same):
    """NoEfforts fills an entry already on the page in place, as resolved for the template."""
    at_load = limited(entry("0"), maxlengths(on_page), "0") if on_page else entry("0")
    page = form_page(section(at_load), limited(entry(), maxlengths({"title": 40})))
    schema, fields = read(page)
    if same:
        assert schema.sections[0].limits == {"title": 40} and workday.WORK_KEY not in fields
    else:
        assert schema.sections == [] and workday.WORK_KEY in fields


# ---------------------------------------------------------------------------- the spec


@pytest.mark.parametrize("kw", [
    {"limits": {"start_date": 7}},
    {"limits": {"title": 0}},
    {"limits": {"title": 100_001}},
    {"limits": {"title": True}},
    {"limits": {"title": "40"}},
    {"limits": {"location": 30}},  # the entry does not ask it
    {"kind": "education", "limits": {"title": 40}},
], ids=["date", "zero", "too-large", "bool", "string", "part-not-asked", "education"])  # fmt: skip
def test_a_section_s_limits_are_known_fields_in_range(kw):
    with pytest.raises(ValidationError):
        SectionSpec(**({"kind": "employment", "root": "#w"} | kw))
    ok = SectionSpec(kind="employment", root="#w", parts=["location"],
                     limits={"title": 40, "location": 30})  # fmt: skip
    assert ok.limits == {"title": 40, "location": 30}
    assert tuple(sorted(LIMITED_FIELDS)) == LIMITED_FIELDS


# ---------------------------------------------------------------------------- resolution


class Rec:
    def __init__(self, **kw):
        self.id = "r1"
        self.employer = kw.get("employer", "Example Health")
        self.title = kw.get("title", "Clinic Assistant")
        self.start_date = kw.get("start_date")
        self.end_date = None
        self.is_current = True
        self.location = kw.get("location")
        self.description = kw.get("description")
        self.approval_status = "approved"


def test_a_record_longer_than_the_page_accepts_is_yours_to_shorten():
    import datetime

    rec = Rec(title="T" * 41, start_date=datetime.date(2019, 1, 1), description="d" * 10)
    row = ss.resolve_employment_row(rec, ("description",), (), {"title": 40, "description": 10})
    title = row.fields["title"]
    assert title.status == "needs_user" and "40" in title.explanation and "41" in title.explanation
    assert "T" * 5 not in title.explanation  # its length, never its text
    assert row.fields["description"].status == "resolved"  # exactly at its limit
    assert row.fields["company_name"].status == "resolved"  # no limit on it here


@pytest.mark.parametrize("text, limit, ok", [
    ("ab\r\ncd", 5, True),  # one LF once written as a text area holds it
    ("a\U0001f600cd", 5, True),  # outside the Basic Multilingual Plane: 2
    ("a\U0001f600cde", 5, False),
    ("abcdef", 5, False),
], ids=["crlf", "emoji-fits", "emoji-over", "plain-over"])  # fmt: skip
def test_length_is_counted_as_the_browser_counts_it(text, limit, ok):
    import datetime

    rec = Rec(start_date=datetime.date(2019, 1, 1), description=text)
    row = ss.resolve_employment_row(rec, ("description",), (), {"description": limit})
    assert (row.fields["description"].status == "resolved") is ok
    assert utf16_len("a\U0001f600") == 3 and utf16_len("a\nb") == 3


@pytest.mark.parametrize("kind, kw", [
    ("employment", {"limits": {"start_date": 7}}),
    ("employment", {"limits": {"location": 30}}),  # not asked
    ("employment", {"limits": {"title": True}}),
    ("employment", {"limits": {"title": 0}}),
    ("education", {"limits": {"title": 40}}),
], ids=["date", "part-not-asked", "bool", "zero", "education"])  # fmt: skip
def test_a_section_with_limits_never_named_is_not_supported(kind, kw):
    assert ss.resolve_section(kind, [], **kw).supported is False
    assert ss.resolve_section("employment", [], limits={"title": 40}).supported is True


# ---------------------------------------------------------------------------- frozen content


def with_limits(limits, **row) -> dict:
    return frozen([frozen_row(**row)], limits=limits)


@pytest.mark.parametrize("data", [
    with_limits([40]),
    with_limits({}),
    with_limits({"start_date": 7}),
    with_limits({"title": True}),
    with_limits({"title": 0}),
    with_limits({"location": 30}),  # no part named
    with_limits({"title": 40}, title="T" * 41),  # a value longer than its limit
    {**with_limits({"title": 40}), "kind": "education", "rows": []},
], ids=["list", "empty", "date", "bool", "zero", "part-not-named", "too-long",
        "education"])  # fmt: skip
def test_frozen_limits_are_checked_before_anything_is_entered(data):
    with pytest.raises(gs.Refused):
        gs.section_from_content(data)


def test_a_frozen_value_within_its_limit_is_planned_and_greenhouse_never_plans_one():
    data = with_limits({"title": 16, "company_name": 14})  # "Clinic Assistant", "Example Health"
    (row,) = ws.plan(data).rows
    assert ("title", "Clinic Assistant") in [(op.field, op.value) for op in row.ops]
    with pytest.raises(gs.Refused):
        gs.plan_content_section(data)


def test_the_executor_refuses_a_value_its_page_would_cut():
    """Defence in depth, past the frozen content's own check."""
    fr = ss.FieldResult("title", "resolved", value={"text": "T" * 41}, display="T" * 41)
    with pytest.raises(gs.Refused):
        ws._op(0, "title", "text", "#w [x]", fr, 40)
    assert ws._op(0, "title", "text", "#w [x]", fr, 41).value == "T" * 41


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


def test_a_value_at_the_page_s_limit_is_sent_whole(api, receiver):
    """40 UTF-16 units: 38 letters and one character outside the Basic Multilingual Plane."""
    title = "N" * 38 + "\U0001f600"
    assert utf16_len(title) == 40
    app_id = experience_application(api, receiver, "experience_limits",
                                    records=(CURRENT | {"title": title},))  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert work(page_2(receiver.ledger()))["work[0].title"] == title


def test_a_record_longer_than_the_page_accepts_blocks_approval(api, receiver):
    long_role = "Night shift lead. " * 12  # 216 characters, the page accepts 200
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


def test_the_stand_in_refuses_a_part_longer_than_its_limit():
    """The oracle's own check: a part longer than WORK_LIMITS is refused, within it accepted."""
    import sys

    from tests.execution_harness import ROOT as REPO

    sys.path.insert(0, str(REPO / "fixtures" / "ats_receiver"))
    import workday_like

    ok = {"work[0].title": "T" * 40, "work[0].company": "C", "work[0].from": "01/2019",
          "work[0].current": "1"}  # fmt: skip
    assert workday_like._work_errors(ok, False, False, workday_like.WORK_LIMITS) == []
    over = ok | {"work[0].title": "T" * 41}
    assert workday_like._work_errors(over, False, False, workday_like.WORK_LIMITS) == [
        "Work Experience 1: title is too long"]  # fmt: skip
    assert workday_like._work_errors(over, False) == []  # no limit: accepted
