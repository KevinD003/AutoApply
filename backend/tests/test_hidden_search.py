"""D111: a search input the page keeps hidden inside one question's group.

Observed on a real page (read-only run #11, `u2`): a `search` input with the combobox role, no
hidden attribute but not visible, no required signal, inside the group of a control that a
job-data question maps to. What it is for was not observed and is never inferred. The rule:
it is not an unanswered question, and is never touched, only while the live page hides it,
requires nothing in it, holds nothing in it and shows the question whose group it is in.
Anything else stops the attempt; every other unlisted control stays a blocking checkpoint.

The structure here is a FIXTURE (fixtures/ats_receiver/greenhouse_v2.py, mode
gh2_hidden_search) built from that one observation; the receiver's ledger is the oracle for
what was disclosed and sent."""

import sys

import pytest

from app.modules.execution import runner
from app.modules.execution.adapters import greenhouse_dom as adapter
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import FieldType, FormField
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.providers.routing import form_checkpoint
from tests.execution_harness import ROOT, Receiver, attempt, pilot_on, queue
from tests.test_greenhouse_controls import approve, content, job_data, page, prepare
from tests.test_greenhouse_dom import kinds
from tests.test_resolver import profile

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))

KEY = "phone-search"
MODE = "gh2_hidden_search"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def schema_of(hs: str = "", *, stand_ins: bool = False):
    schema, _ = dom.build_schema(job_data(), page(mode=MODE, hs=hs), stand_ins=stand_ins)
    return {f.key: f for f in schema.fields}


# ------------------------------------------------------------------ capture (markup only)


@pytest.mark.parametrize("stand_ins", [False, True], ids=["real_page", "stand_in"])
@pytest.mark.parametrize("hs", ["", "shown", "value", "late", "group_required"])
def test_the_shape_is_captured_as_not_a_question_on_real_pages_too(hs, stand_ins):
    """The page's markup alone cannot show whether a control is hidden, so capture records the
    shape with its condition; the live page decides (tests below)."""
    f = schema_of(hs, stand_ins=stand_ins)[KEY]
    assert (f.type, f.required, f.widget) == (FieldType.unsupported, False, "hidden_search")
    assert (f.label, f.unsupported_reason) == (dom.HIDDEN_SEARCH_LABEL, dom.HIDDEN_SEARCH_REASON)
    assert not f.options


@pytest.mark.parametrize("hs", ["required", "outside"])
def test_anything_else_stays_a_blocking_unlisted_control(hs):
    """Required by the page, or in no group: what it asks and whether it is required are never
    inferred, exactly as for any control the job data does not list."""
    f = schema_of(hs)[KEY]
    assert (f.type, f.required, f.widget) == (FieldType.unsupported, True, None)
    assert f.unsupported_reason == dom.UNLISTED_REASON


def test_a_control_the_page_adds_later_is_not_in_the_captured_form():
    assert KEY not in schema_of("js")


FORM = """<form>
<div role="group" aria-labelledby="g-label"><span id="g-label">Contact</span>
 <label for="first_name">First Name</label><input type="text" id="first_name">
 %SECOND%
 <input %SEARCH%>
</div></form>"""


@pytest.mark.parametrize(
    "second,search,shape",
    [
        ("", 'type="search" id="s" role="combobox"', True),
        # Two job-data questions share the group: whose group it is in is not established.
        ('<label for="last_name">Last Name</label><input type="text" id="last_name">',
         'type="search" id="s" role="combobox"', False),
        ("", 'type="text" id="s" role="combobox"', False),  # not a search input
        ("", 'type="search" id="s"', False),  # no combobox role
        ("", 'type="search" id="s" role="combobox" required', False),  # required by HTML
    ],
)  # fmt: skip
def test_the_shape_needs_every_property_and_exactly_one_question_in_the_group(
    second, search, shape
):
    fields = [FormField(key="first_name", label="First Name", type=FieldType.text),
              FormField(key="last_name", label="Last Name", type=FieldType.text)]  # fmt: skip
    controls = dom.snapshot(FORM.replace("%SECOND%", second).replace("%SEARCH%", search))
    s = next(c for c in controls if c.id == "s")
    assert dom.hidden_search_shape(fields, controls, s) is shape
    assert [c.id for c in dom.hidden_search_candidates(fields, controls)] == (["s"] if shape
                                                                              else [])  # fmt: skip


@pytest.mark.parametrize(
    "state,ok",
    [
        ({"shown": False, "owner_shown": True, "value": "", "signals": {"aria": False}}, True),
        ({"shown": True, "owner_shown": True, "value": "", "signals": {"aria": False}}, False),
        ({"shown": False, "owner_shown": False, "value": "", "signals": {"aria": False}}, False),
        ({"shown": False, "owner_shown": True, "value": "x", "signals": {"aria": False}}, False),
        ({"shown": False, "owner_shown": True, "value": "", "signals": {"aria": True}}, False),
        ({"shown": False, "owner_shown": True, "value": "", "signals": None}, False),
        (None, False),
    ],
)
def test_the_live_state_must_show_every_condition(state, ok):
    assert dom.hidden_search_ok(state) is ok


# ------------------------------------------------------------------ resolver and route


def test_it_is_never_asked_answered_saved_or_counted_as_a_checkpoint():
    f = FormField(key=KEY, label=dom.HIDDEN_SEARCH_LABEL, type=FieldType.unsupported,
                  unsupported_reason=dom.HIDDEN_SEARCH_REASON, widget="hidden_search")  # fmt: skip
    r = resolve_field(f, Context(profile=profile(residence_country="CA")))
    assert (r.status, r.value, r.source) == ("blank_optional", None, "unresolved")
    assert (r.user_input_allowed, r.bankable, r.draftable) == (False, False, False)
    assert r.explanation.startswith("Not a question") and "stops" in r.explanation
    assert form_checkpoint({"fields": [f.model_dump(mode="json")]}) == []


def test_a_hidden_search_widget_must_be_unsupported():
    with pytest.raises(ValueError, match="cannot be a hidden_search control"):
        FormField(key=KEY, label="Search", type=FieldType.text, widget="hidden_search")


# ------------------------------------------------------------------ the adapter (ledger oracle)


def by_id(api, **kw) -> str:
    _, app_id = prepare(api, **kw)
    c = content(api, app_id)
    assert not c["unresolved"], c["unresolved"]
    assert approve(api, app_id).status_code == 200
    return app_id


def pilot(api, **kw) -> str:
    pilot_on()
    return by_id(api, **kw)


MAKE = pytest.mark.parametrize("make", [by_id, pilot], ids=["by_id", "pilot"])


@pytest.mark.parametrize("hs", ["", "js"])
@MAKE
def test_hidden_unrequired_and_empty_it_is_left_alone_and_the_application_goes_through(
    api, receiver, make, hs
):
    """Also when the page adds it after load (absent from the captured form, `js`): on the live
    page it is shown to be the same hidden, unrequired, empty search box, so it is not a new
    question."""
    receiver.config(mode=MODE, hs=hs)
    app_id = make(api)
    a = next((x for x in content(api, app_id)["answers"] if x["key"] == KEY), None)
    if hs == "":
        assert (a["status"], a["value"], a["widget"]) == ("blank_optional", None,
                                                          "hidden_search")  # fmt: skip
    else:
        assert a is None
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1 and kinds(led) == {"upload": 1}
    assert KEY not in led["acceptances"][0]["fields"]  # never typed into, nothing sent for it


@pytest.mark.parametrize("hs", ["shown", "value", "group_required"])
@MAKE
def test_shown_required_or_holding_a_value_it_stops_before_anything_is_entered(api, receiver, make, hs):
    receiver.config(mode=MODE, hs=hs)
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "changed since you approved" in attempt(aid).outcome_detail
    assert dom.HIDDEN_SEARCH_CHANGED in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@MAKE
def test_shown_after_filling_it_stops_before_submitting(api, receiver, make):
    """The runner re-checks the form after filling: the page shows the box once the phone
    number is entered, so nothing is submitted (what was filled is recorded as disclosed)."""
    receiver.config(mode=MODE, hs="late")
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert dom.HIDDEN_SEARCH_CHANGED in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []


@pytest.mark.parametrize("hs", ["required", "outside"])
def test_required_or_outside_a_group_nothing_can_be_approved(api, receiver, hs):
    receiver.config(mode=MODE, hs=hs)
    _, app_id = prepare(api)
    assert KEY in content(api, app_id)["unresolved"]
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []


def test_on_a_real_board_the_rule_applies_and_the_stand_ins_stay_refused(
    api, receiver, monkeypatch
):
    """The adapter as it runs on a real board (no origin is a fixture): this rule comes from a
    real page, so it is not one of the stand-in-only structures."""
    receiver.config(mode=MODE, hs="")  # the receiver keeps cfg between tests
    aid = queue(api, by_id(api))
    monkeypatch.setattr(adapter, "stand_ins", lambda content: False)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 1
