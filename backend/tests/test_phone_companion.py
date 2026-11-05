"""D130: an optional phone whose question holds a second control NoEfforts cannot set.

From the owner-supplied markup of one real form: beside an optional phone (`type=tel`,
`aria-required="false"`), a library combobox (an editable input with opacity 0 behind a visible
control showing the page's own default; no `aria-required`; options only once opened). From
read-only run #11 (another posting): such a combobox inside the group the page names as the
phone question. Its label, options and selection/readback behaviour were never observed, so it
is never set. The rule: when the job data asks the phone as OPTIONAL and that group holds exactly
one other control, unrequired, the phone is left blank and the control is never touched -- only
while the live page requires neither and holds no number in the phone, before anything is
entered and again before submitting. Everything else stays a blocking checkpoint, and opacity
never makes a control hidden.

The structure here is a FIXTURE (fixtures/ats_receiver/greenhouse_v2.py, mode
gh2_phone_companion); the receiver's ledger is the oracle for what was disclosed and sent, and
the page itself counts any touch of the control (`fx_companion_touched`)."""

import sys

import pytest

from app.modules.execution import policy, runner
from app.modules.execution.adapters import greenhouse_dom as adapter
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation import package as pk
from app.modules.preparation.forms import FieldType, FormField
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.providers.routing import form_checkpoint
from tests.execution_harness import BASE, ROOT, Receiver, attempt, pilot_on, queue
from tests.test_approval_binding import approval_of, reapprove, set_approval, try_queue
from tests.test_greenhouse_controls import approve, content, prepare
from tests.test_greenhouse_dom import BOARD, JOB, kinds
from tests.test_package_contract import SHAPES, paths
from tests.test_resolver import profile

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))

import greenhouse_v2  # noqa: E402

MODE = "gh2_phone_companion"
KEY = "phone-cc-input"
UNIQUE = ["", "relabel", "search", "late_required", "prefill", "autofill"]  # recognised
BLOCKING = ["required", "marker", "phone_marker", "group_required", "phone_required_api",
            "two", "outside"]  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def capture(pcm: str = "", *, stand_ins: bool = False) -> dict:
    cfg = {"mode": MODE, "pcm": pcm}
    html = greenhouse_v2._form_page(BOARD, JOB, "t", cfg).body.decode()
    schema, _ = dom.build_schema(greenhouse_v2._api_json(BOARD, JOB, BASE, cfg), html,
                                 stand_ins=stand_ins)  # fmt: skip
    return {f.key: f for f in schema.fields}


# ------------------------------------------------------------------ capture (markup only)


@pytest.mark.parametrize("stand_ins", [False, True], ids=["real_page", "stand_in"])
@pytest.mark.parametrize("pcm", UNIQUE)
def test_the_optional_phone_is_left_blank_and_its_second_control_is_not_a_question(pcm, stand_ins):
    """Markup alone cannot show a script's later changes (late_required, prefill, autofill):
    capture records the structure, and the live page decides (tests below)."""
    f = capture(pcm, stand_ins=stand_ins)
    assert (f["phone"].type, f["phone"].required, f["phone"].widget) == (
        FieldType.tel, False, "phone_left_blank")  # fmt: skip
    c = f[KEY]
    assert (c.type, c.required, c.widget) == (FieldType.unsupported, False, "phone_companion")
    assert (c.label, c.unsupported_reason) == (dom.PHONE_COMPANION_LABEL,
                                               dom.PHONE_COMPANION_REASON)  # fmt: skip
    # Nothing else became a blocking question: the package can be approved.
    assert [k for k, x in f.items() if x.type == FieldType.unsupported and x.required] == []


@pytest.mark.parametrize("pcm", BLOCKING)
def test_anything_else_stays_a_blocking_unlisted_control_and_the_phone_is_asked(pcm):
    """A control the page requires (attribute, ARIA, its own "*", the group's ARIA), a phone
    the page or the job data requires, a second such control, or one outside the phone's group:
    what it asks and whether it is required are never inferred."""
    f = capture(pcm)
    assert f["phone"].widget is None
    blocking = [x for x in f.values() if x.key.startswith("phone-cc")]
    assert blocking and all(
        (x.type, x.required, x.widget, x.unsupported_reason)
        == (FieldType.unsupported, True, None, dom.UNLISTED_REASON)
        for x in blocking
    )


def test_opacity_never_makes_a_control_hidden():
    """The library input sits at opacity 0 behind its visible control: it is a control like
    any other (what made it acceptable is the phone question it belongs to, not its looks)."""
    html = greenhouse_v2._form_page(BOARD, JOB, "t", {"mode": MODE, "pcm": ""}).body.decode()
    c = next(x for x in dom.snapshot(html) if x.id == KEY)
    assert (c.hidden, c.in_form, c.role) == (False, True, "combobox")
    loose = dom.snapshot('<form><input id="x" role="combobox" style="opacity:0"></form>')
    assert [x.hidden for x in loose] == [False]


def test_a_recognised_stand_in_picker_still_takes_precedence():
    """D104 on a stand-in (a required phone with a listed picker): unchanged."""
    html = greenhouse_v2._form_page(BOARD, JOB, "t", {"mode": "gh2_phone_country"}).body.decode()
    schema, _ = dom.build_schema(greenhouse_v2._api_json(BOARD, JOB, BASE), html,
                                 stand_ins=True)  # fmt: skip
    f = {x.key: x for x in schema.fields}
    assert f["phone"].widget is None and f["phone-country"].widget == "phone_country"
    assert not any(x.widget in ("phone_left_blank", "phone_companion") for x in f.values())


FORM = """<form>
<div role="group" aria-labelledby="g"><span id="g">%GROUP%</span>
 <label for="phone">Phone</label><input type="tel" id="phone">
 %OTHER%
</div></form>"""
TEL = FormField(key="phone", label="Phone", type=FieldType.tel)
COMBO = '<span id="l">Country</span><input id="c" role="combobox" aria-labelledby="l">'


@pytest.mark.parametrize(
    "group,other,field,found",
    [
        ("Phone", COMBO, TEL, True),
        ("Contact", COMBO, TEL, False),  # the group is not named as the phone question
        ("Phone", COMBO, TEL.model_copy(update={"required": True}), False),
        ("Phone", '<select id="c"><option>1</option></select>', TEL, False),  # no combobox
        ("Phone", COMBO.replace('role="combobox"', 'role="combobox" hidden'), TEL, False),
        ("Phone", COMBO + COMBO, TEL, False),  # two of them (and the same id twice)
        ("Phone", "", TEL, False),  # nothing beside the phone
    ],
)  # fmt: skip
def test_every_property_of_the_structure_is_needed(group, other, field, found):
    controls = dom.snapshot(FORM.replace("%GROUP%", group).replace("%OTHER%", other))
    c = dom.phone_companion([field], controls)
    assert (c.id if c else None) == ("c" if found else None)


@pytest.mark.parametrize(
    "state,ok",
    [
        ({"value": "", "signals": {"aria": False}, "phone_signals": {"aria": False}}, True),
        ({"value": "+1 555", "signals": {"aria": False}, "phone_signals": {"aria": False}},
         False),
        ({"value": "", "signals": {"aria": True}, "phone_signals": {"aria": False}}, False),
        ({"value": "", "signals": {"aria": False}, "phone_signals": {"label_marker": True}},
         False),
        ({"value": "", "signals": None, "phone_signals": {"aria": False}}, False),
        (None, False),
    ],
)  # fmt: skip
def test_the_live_state_must_show_every_condition(state, ok):
    assert dom.phone_companion_ok(state) is ok


# ------------------------------------------------------------------ resolver and route


def test_the_phone_is_left_blank_whatever_the_profile_holds():
    f = FormField(key="phone", label="Phone", type=FieldType.tel, widget="phone_left_blank")
    r = resolve_field(f, Context(profile=profile(phone="+44 20 7946 0000")))
    assert (r.status, r.value, r.source) == ("blank_optional", None, "unresolved")
    assert (r.user_input_allowed, r.bankable, r.draftable) == (False, False, False)
    assert r.fact_refs == [] and "+44" not in r.explanation
    assert "apply on the employer's site" in r.explanation
    c = FormField(
        key=KEY,
        label=dom.PHONE_COMPANION_LABEL,
        type=FieldType.unsupported,
        unsupported_reason=dom.PHONE_COMPANION_REASON,
        widget="phone_companion",
    )
    rc = resolve_field(c, Context(profile=profile(phone="+44 20 7946 0000")))
    assert (rc.status, rc.value, rc.user_input_allowed) == ("blank_optional", None, False)
    assert form_checkpoint({"fields": [x.model_dump(mode="json") for x in (f, c)]}) == []


def test_each_widget_is_bound_to_its_field_type():
    with pytest.raises(ValueError, match="cannot be a phone_left_blank control"):
        FormField(key="phone", label="Phone", type=FieldType.text, widget="phone_left_blank")
    with pytest.raises(ValueError, match="cannot be a phone_companion control"):
        FormField(key=KEY, label="Country", type=FieldType.tel, widget="phone_companion")


def test_the_package_leaves_the_phone_blank_and_needs_nothing_more(api, receiver):
    """The synthetic profile has a phone number; it is not used, nothing can be typed in its
    place, and the package keeps the version-3 shape (a widget only where one applies)."""
    receiver.config(mode=MODE, pcm="")
    _, app_id = prepare(api)
    c = content(api, app_id)
    assert not c["unresolved"], c["unresolved"]
    rows = {a["key"]: a for a in c["answers"]}
    assert (rows["phone"]["status"], rows["phone"]["value"], rows["phone"]["widget"]) == (
        "blank_optional", None, "phone_left_blank")  # fmt: skip
    assert (rows[KEY]["status"], rows[KEY]["value"], rows[KEY]["widget"]) == (
        "blank_optional", None, "phone_companion")  # fmt: skip
    assert pk.SCHEMA_VERSION == 3 and paths(c) - SHAPES[3] == {".answers[].widget"}
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "phone", "value": {"text": "+1 555 0100"}})  # fmt: skip
    assert r.status_code == 400
    assert approve(api, app_id).status_code == 200


@pytest.mark.parametrize("pcm", BLOCKING)
def test_when_the_structure_does_not_hold_nothing_can_be_approved(api, receiver, pcm):
    receiver.config(mode=MODE, pcm=pcm)
    _, app_id = prepare(api)
    assert any(k.startswith("phone-cc") for k in content(api, app_id)["unresolved"])
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []


# ------------------------------------------------------------------ the adapter (ledger oracle)


def by_id(api, pcm: str = "", scope: str | None = None) -> str:
    _, app_id = prepare(api)
    c = content(api, app_id)
    assert not c["unresolved"], c["unresolved"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    if scope:
        body["scope"] = scope
    r = api.post(f"/applications/{app_id}/package/approve", json=body)
    assert r.status_code == 200, r.text
    return app_id


def pilot(api, pcm: str = "", scope: str | None = None) -> str:
    pilot_on()
    return by_id(api, pcm, scope)


MAKE = pytest.mark.parametrize("make", [by_id, pilot], ids=["by_id", "pilot"])


def sent(receiver) -> dict:
    led = receiver.ledger()
    assert led["accepted"] == 1, led
    return led["acceptances"][0]["fields"]


@pytest.mark.parametrize("pcm", ["", "relabel", "search"])
@MAKE
def test_the_application_goes_through_with_the_phone_empty_and_the_control_untouched(
    api, receiver, make, pcm
):
    receiver.config(mode=MODE, pcm=pcm)
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert kinds(receiver.ledger()) == {"upload": 1}  # the resume; nothing for the phone
    fields = sent(receiver)
    assert "phone" not in fields  # nothing typed, nothing sent
    assert fields[KEY] == "US"  # the page's own default, as it was
    assert fields["fx_companion_touched"] == "0"  # the page saw no focus, click, key or input
    assert "phone-search" not in fields


def test_a_rehearsal_stops_before_submitting(api, receiver):
    receiver.config(mode=MODE, pcm="")
    aid = queue(api, by_id(api, scope="disclose_only"))
    assert runner.run_attempt(aid, "w1") == "rehearsed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []


@pytest.mark.parametrize("pcm", ["late_required", "prefill"])
@MAKE
def test_required_or_holding_a_number_on_the_live_page_it_stops_before_anything_is_entered(
    api, receiver, make, pcm
):
    receiver.config(mode=MODE, pcm=pcm)
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "changed since you approved" in detail and dom.PHONE_COMPANION_CHANGED in detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@MAKE
def test_a_number_the_page_puts_in_after_the_upload_stops_it_before_submitting(api, receiver, make):
    """The page fills the phone "from the resume" after the upload: the readback (an empty
    phone was approved) stops the attempt before the send; the upload was disclosed."""
    receiver.config(mode=MODE, pcm="autofill")
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert "did not keep their values" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == [] and kinds(led) == {"upload": 1}


@pytest.mark.parametrize("pcm", ["two", "outside", "group_required", "required"])
def test_a_page_that_changed_after_approval_stops_before_anything_is_entered(api, receiver, pcm):
    """Approved on the plain structure; the live page then differs."""
    receiver.config(mode=MODE, pcm="")
    app_id = by_id(api)
    receiver.config(mode=MODE, pcm=pcm)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "changed since you approved" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_a_library_id_that_differs_from_the_captured_one_is_the_same_structure(api, receiver):
    """Re-proven by structure, not by id: the page library's ids may differ between loads."""
    receiver.config(mode=MODE, pcm="")
    app_id = by_id(api)
    receiver.config(mode=MODE, pcm="renumber")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    fields = sent(receiver)
    assert "phone" not in fields and fields["phone-cc7-input"] == "US"
    assert fields["fx_companion_touched"] == "0"


def test_on_a_real_board_the_rule_applies(api, receiver, monkeypatch):
    """The adapter as it runs on a real board (no origin is a fixture): the rule comes from a
    real page's markup, so it is not a stand-in-only structure."""
    receiver.config(mode=MODE, pcm="")
    aid = queue(api, by_id(api))
    monkeypatch.setattr(adapter, "stand_ins", lambda content: False)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert "phone" not in sent(receiver)


# ------------------------------------------------------------------ worker compatibility

PRE_D130 = {
    "greenhouse_dom": "greenhouse-dom-4+greenhouse-dom-v3",
    "greenhouse_live": "greenhouse-live-2+greenhouse-dom-v3",
}


@pytest.mark.parametrize("adapter_name", sorted(PRE_D130))
def test_an_approval_from_before_the_extraction_bump_is_retired_never_renewed(
    api, receiver, adapter_name
):
    """v4 is part of adapter_version (check_binding), not of the hashed package: an approval
    recorded at v3 -- by a worker that would not re-prove the phone's control -- is retired and
    must be given again explicitly; nothing renews it."""
    receiver.config(mode=MODE, pcm="")
    app_id = pilot(api) if adapter_name == "greenhouse_live" else by_id(api)
    assert approval_of(app_id).adapter == adapter_name
    assert policy.ADAPTER_VERSIONS[adapter_name].endswith("+greenhouse-dom-v4")
    before = api.get(f"/applications/{app_id}/package").json()["package"]
    set_approval(app_id, adapter_version=PRE_D130[adapter_name])
    r = try_queue(api, app_id)
    assert r.status_code == 409 and "changed after you approved" in r.text
    retired = approval_of(app_id)
    assert retired.invalidated_at is not None
    after = api.get(f"/applications/{app_id}/package").json()["package"]
    assert (after["version"], after["content_hash"]) == (before["version"], before["content_hash"])
    assert try_queue(api, app_id).status_code != 200 and approval_of(app_id).id == retired.id
    assert reapprove(api, app_id).status_code == 200
    assert approval_of(app_id).adapter_version == policy.ADAPTER_VERSIONS[adapter_name]
    assert receiver.ledger()["disclosures"] == []
