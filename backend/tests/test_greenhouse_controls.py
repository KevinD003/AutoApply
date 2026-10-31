"""D104: Greenhouse-style controls on LOCAL STAND-INS only (fixtures/ats_receiver/greenhouse_v2.py,
modes gh2_phone_country, gh2_loc_search and gh2_dd late_*): the phone country picker, the
location search and dropdown lists that arrive late. Each structure is a FIXTURE ASSUMPTION; none
has been seen working on a real page, and synthetic coverage here is not evidence that a real
page works. The receiver's ledger is the oracle for what was disclosed and sent."""

import json
import sys

import pytest

from app.modules.execution import policy, runner
from app.modules.execution.adapters import dropdowns
from app.modules.execution.adapters import greenhouse_dom as adapter
from app.modules.preparation import greenhouse as gh
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation import package as pk
from app.modules.preparation.forms import FieldType, FormField, Option
from app.modules.preparation.resolver import Context, question_key, resolve_field
from tests.execution_harness import (
    BASE,
    ROOT,
    Receiver,
    attempt,
    pilot_on,
    queue,
    synthetic_candidate,
)
from tests.test_greenhouse_dom import BOARD, JOB, LOC_JOB, kinds, v2_job
from tests.test_package_contract import SHAPES, paths
from tests.test_resolver import profile

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

PHONE_KEY = "phone-country"
PLACE = {"location": "Springfield", "latitude": "10.2500", "longitude": "20.7500"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def page(job=JOB, **cfg) -> str:
    return greenhouse_v2._form_page(BOARD, job, "t", {"mode": "normal", **cfg}).body.decode()


def job_data(job=JOB) -> dict:
    return greenhouse_v2._api_json(BOARD, job, BASE)


def set_phone(api, phone: str) -> None:
    """The synthetic candidate's profile, with another (fictional) phone number."""
    body = {"full_name": "Sam Synthetic", "given_name": "Sam", "family_name": "Synthetic",
            "contact_email": "sam.synthetic@example.com", "phone": phone,
            "residence_country": "US", "residence_city": "Springfield",
            "links": ["https://www.linkedin.com/in/sam-synthetic"]}  # fmt: skip
    assert api.put("/profile", json=body).status_code == 200


def prepare(api, *, job=JOB, phone=None, answers=None) -> tuple[str, str]:
    """Synthetic candidate, the job captured from the receiver as it is configured now, and an
    application. Returns (job id, application id)."""
    synthetic_candidate(api)
    if phone is not None:
        set_phone(api, phone)
    job_id = v2_job(api, job)
    r = api.post(f"/jobs/{job_id}/form/greenhouse")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    base = {"preferred_name": {"text": "Sammy"}}
    if job == JOB:
        base |= {"question_8101": {"label": "Yes"}, "question_8104": {"label": "No"}}
    for key, value in (base | (answers or {})).items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    return job_id, app_id


def content(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]["content"]


def approve(api, app_id):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip


def d104_application(api, **kw) -> str:
    """Through the id-mapping adapter (greenhouse_dom): prepared and approved."""
    _, app_id = prepare(api, **kw)
    unresolved = content(api, app_id)["unresolved"]
    assert not unresolved, unresolved
    r = approve(api, app_id)
    assert r.status_code == 200, r.text
    return app_id


def d104_live_application(api, **kw) -> str:
    """The same through the Greenhouse pilot (greenhouse_live), the approximation playing a
    board host (test only; conftest turns the pilot off after every test)."""
    pilot_on()
    return d104_application(api, **kw)


MAKE = pytest.mark.parametrize("make", [d104_application, d104_live_application],
                               ids=["by_id", "pilot"])  # fmt: skip


def answer(c: dict, key: str) -> dict:
    return next(a for a in c["answers"] if a["key"] == key)


# ------------------------------------------------------------------ capture: only these structures


def test_capture_recognises_the_phone_country_picker_and_the_location_search_on_stand_ins():
    schema, _ = dom.build_schema(job_data(), page(mode="gh2_phone_country"), stand_ins=True)
    f = {x.key: x for x in schema.fields}
    pc = f[PHONE_KEY]
    assert (pc.type, pc.widget, pc.required) == (FieldType.select, "phone_country", True)
    assert [(o.value, o.label) for o in pc.options] == greenhouse_v2.PHONE_COUNTRIES
    keys = [x.key for x in schema.fields]
    assert keys.index(PHONE_KEY) == keys.index("phone") + 1  # filled right after the number
    assert not any(x.unsupported_reason == dom.UNLISTED_REASON for x in schema.fields)

    schema, maps = dom.build_schema(job_data(LOC_JOB), page(LOC_JOB, mode="gh2_loc_search"),
                                    stand_ins=True)  # fmt: skip
    f = {x.key: x for x in schema.fields}
    assert (f["location"].type, f["location"].widget) == (FieldType.text, "location_search")
    for k in ("latitude", "longitude"):
        assert (f[k].type, f[k].widget, f[k].required) == (
            FieldType.unsupported, "location_structured", True)  # fmt: skip
    assert {m.key: m.status for m in maps}["location"] == "search_picker"


@pytest.mark.parametrize(
    "job,cfg",
    [
        (JOB, {"mode": "gh2_phone_country", "pc": "outside"}),  # beside the group, not in it
        (JOB, {"mode": "gh2_phone_country", "pc": "no_codes"}),  # options state no code
        (JOB, {"mode": "gh2_dd_extras"}),  # no list in the page at load (B3's structure)
        (LOC_JOB, {"mode": "normal"}),  # hidden values outside the picker's group
    ],
)
def test_anything_but_these_structures_stays_a_checkpoint_at_capture(job, cfg):
    schema, _ = dom.build_schema(job_data(job), page(job, **cfg), stand_ins=True)
    assert not any(f.widget for f in schema.fields)
    if job == JOB:
        pc = next(f for f in schema.fields if f.key == PHONE_KEY)
        assert (pc.type, pc.unsupported_reason) == (FieldType.unsupported, dom.UNLISTED_REASON)
    else:
        assert {f.key for f in schema.fields if f.type == FieldType.unsupported} >= {
            "location", "latitude", "longitude"}  # fmt: skip


@pytest.mark.parametrize("job,mode", [(JOB, "gh2_phone_country"), (LOC_JOB, "gh2_loc_search")])
def test_a_page_that_is_not_a_stand_in_never_gets_these_rules(job, mode):
    """The same markup read as a real page (`stand_ins` false, as on every real board and in
    production): the v2 checkpoints, unchanged."""
    schema, _ = dom.build_schema(job_data(job), page(job, mode=mode))
    assert not any(f.widget for f in schema.fields)
    assert any(f.type == FieldType.unsupported and f.required for f in schema.fields)


def test_a_widget_is_never_accepted_from_a_hand_made_form(api):
    job = api.post("/jobs", json={"title": "Manual", "employer": "Example (fictional)"}).json()
    form = {
        "title": "Manual (fictional)",
        "fields": [
            {"key": "where", "label": "Location", "type": "text", "widget": "location_search"}
        ],
    }
    r = api.post(f"/jobs/{job['job']['id']}/form", json={"form": form})
    assert r.status_code == 400 and "set by NoEfforts only" in r.text


# ------------------------------------------------------------------ resolver (no LLM, no database)

PHONE_OPTIONS = [Option(value=v, label=n) for v, n in greenhouse_v2.PHONE_COUNTRIES]
PHONE_FIELD = FormField(key=PHONE_KEY, label="Country code", type=FieldType.select, required=True,
                        options=PHONE_OPTIONS, widget="phone_country")  # fmt: skip


@pytest.mark.parametrize(
    "phone,status,value,why",
    [
        ("+44 20 7946 0000", "resolved", "GB", "matches exactly one"),
        ("+91 98765 43210", "resolved", "IN", "matches exactly one"),
        ("+1 555 0100", "needs_user", None, "Several of the page's options share"),  # US, CA
        ("+15550100", "needs_user", None, "does not state its calling code"),  # not delimited
        ("555 0100", "needs_user", None, "does not state its calling code"),  # no + code
        ("+7 495 000 0000", "needs_user", None, "None of the page's options"),
        (None, "needs_user", None, "no verified phone number"),
    ],
)
def test_phone_country_only_from_a_calling_code_that_names_exactly_one_option(
    phone, status, value, why
):
    # Residence and a target are set and must never decide it (CA residence, +1 number).
    prefs = type("P", (), {"id": "pr", "target_locations": [{"city": "Toronto", "country": "CA"}]})
    p = profile(phone=phone, residence_country="CA", residence_city="Toronto")
    r = resolve_field(PHONE_FIELD, Context(profile=p, prefs=prefs()))
    assert (r.status, (r.value or {}).get("option")) == (status, value), r.explanation
    assert why in r.explanation and not r.bankable and not r.draftable
    assert r.user_input_allowed is (status != "resolved")
    if status != "resolved":
        assert "never inferred from where you live" in r.explanation
    if phone:
        assert [x["field"] for x in r.fact_refs] == ["phone"]  # a changed number re-asks


def test_an_unapproved_phone_number_never_chooses():
    from app.modules.profiles.models import Approval

    r = resolve_field(
        PHONE_FIELD,
        Context(profile=profile(phone="+44 20 7946 0000", approval_status=Approval.proposed)),
    )
    assert r.status == "needs_user" and r.value is None  # e.g. parsed from a resume, unapproved


def test_location_search_text_is_the_residence_fact_or_your_answer_never_saved_or_guessed():
    loc = FormField(key="location", label="Location (City)", type=FieldType.text, required=True,
                    widget="location_search")  # fmt: skip
    # Classified as residence by the existing rules: the approved residence city, only.
    r = resolve_field(loc, Context(profile=profile(residence_city="Springfield")))
    assert (r.status, r.source, r.value) == ("resolved", "profile_fact", {"text": "Springfield"})
    assert "typed into the employer's page search" in r.explanation and not r.bankable
    assert resolve_field(loc, Context(profile=profile())).status == "needs_user"  # unknown
    # Not about where you live: your answer for this application. Neither the residence fact,
    # a target location (a preference) nor a saved answer is ever used.
    pref = loc.model_copy(update={"label": "Which office would you like to work from?"})
    bank_entry = type("E", (), {"answer": {"text": "Riverton"}})()  # a saved answer: never used
    targets = type("P", (), {"id": "pr", "target_locations": [{"city": "Riverton"}]})()
    r = resolve_field(pref, Context(profile=profile(residence_city="Springfield"), prefs=targets,
                                    bank={question_key(pref): bank_entry}))  # fmt: skip
    assert (r.status, r.value, r.user_input_allowed, r.bankable) == ("needs_user", None, True,
                                                                     False)  # fmt: skip
    inp = type("I", (), {"value": {"text": "Riverton"}, "provenance": "user"})()
    r = resolve_field(pref, Context(profile=profile(), inputs={"location": inp}))
    assert (r.status, r.source, r.value) == ("resolved", "user_entered", {"text": "Riverton"})
    hidden = FormField(key="latitude", label="Latitude", type=FieldType.unsupported, required=True,
                       unsupported_reason=dom.LOCATION_STRUCTURED_REASON,
                       widget="location_structured")  # fmt: skip
    r = resolve_field(hidden, Context(profile=profile(residence_city="Springfield")))
    assert (r.status, r.value, r.user_input_allowed) == ("blank_optional", None, False)
    assert "never writes it" in r.explanation


# ------------------------------------------------------------------ phone country (receiver oracle)


@MAKE
def test_a_unique_calling_code_chooses_the_country_and_it_is_read_back(api, receiver, make):
    receiver.config(mode="gh2_phone_country")
    app_id = make(api, phone="+44 20 7946 0000")
    c = content(api, app_id)
    pc = answer(c, PHONE_KEY)
    assert (pc["source"], pc["value"]["option"], pc["widget"]) == (
        "deterministic_mapping", "GB", "phone_country")  # fmt: skip
    assert paths(c) - SHAPES[3] == {".answers[].widget"}  # only this form's package gains it
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    sent = led["acceptances"][0]["fields"]
    assert (sent["phone"], sent[PHONE_KEY]) == ("+44 20 7946 0000", "GB")
    assert led["accepted"] == 1 and kinds(led) == {"upload": 1}
    rb = next(e for e in api.get(f"/applications/{app_id}/attempts").json()[0]["evidence"]
              if e["kind"] == "readback")["data"]  # fmt: skip
    assert rb["mismatched"] == 0


@MAKE
def test_a_shared_calling_code_is_a_checkpoint_until_you_choose(api, receiver, make):
    """+1 is the United States and Canada: never assumed. Nothing can be approved or sent until
    you choose; your choice is what is sent."""
    receiver.config(mode="gh2_phone_country")
    if make is d104_live_application:
        pilot_on()
    _, app_id = prepare(api)  # +1 555 0100, residence US
    c = content(api, app_id)
    pc = answer(c, PHONE_KEY)
    assert (pc["status"], pc["value"], pc["user_input_allowed"]) == ("needs_user", None, True)
    assert PHONE_KEY in c["unresolved"] and "share your calling code (+1)" in pc["explanation"]
    assert approve(api, app_id).status_code != 200
    assert receiver.ledger()["disclosures"] == []
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": PHONE_KEY, "value": {"label": "Canada (+1)"}})  # fmt: skip
    assert r.status_code == 200, r.text
    pc = answer(content(api, app_id), PHONE_KEY)
    assert (pc["source"], pc["value"]["option"]) == ("user_entered", "CA")
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert receiver.ledger()["acceptances"][0]["fields"][PHONE_KEY] == "CA"


@MAKE
def test_no_calling_code_is_a_checkpoint_never_inferred_from_residence(api, receiver, make):
    receiver.config(mode="gh2_phone_country")
    if make is d104_live_application:
        pilot_on()
    _, app_id = prepare(api, phone="555 0100")  # residence US; the list offers United States
    c = content(api, app_id)
    pc = answer(c, PHONE_KEY)
    assert (pc["status"], pc["value"]) == ("needs_user", None)
    assert "does not state its calling code" in pc["explanation"]
    assert PHONE_KEY in c["unresolved"] and approve(api, app_id).status_code != 200
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


# ------------------------------------------------------------------ location search (ledger oracle)


@MAKE
def test_location_exact_or_checkpoint(api, receiver, make):
    """The approved residence city is typed into the page's own search after the disclosure gate
    (the ledger counts it), the one suggestion that is exactly it is chosen (not the first,
    highlighted one), and the page itself sets the hidden coordinates: NoEfforts writes none of
    them. greenhouse_dom's `location_picker` scenario."""
    receiver.config(mode="gh2_loc_search")
    app_id = make(api, job=LOC_JOB)
    c = content(api, app_id)
    loc = answer(c, "location")
    assert (loc["source"], loc["value"], loc["widget"]) == (
        "profile_fact", {"text": "Springfield"}, "location_search")  # fmt: skip
    assert not {"location", "latitude", "longitude"} & set(c["unresolved"])
    assert receiver.ledger()["disclosures"] == []  # nothing typed before approval and the gate
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1 and kinds(led) == {"upload": 1, "location_search": 1}
    searched = [json.loads(d["detail"])["q"] for d in led["disclosures"]
                if d["kind"] == "location_search"]  # fmt: skip
    assert searched == ["Springfield"]  # exactly the approved text, once
    sent = led["acceptances"][0]["fields"]
    assert {k: sent[k] for k in PLACE} == PLACE  # the exact suggestion's, not the first one's
    # Hidden values written by the page's own script only: never by NoEfforts.
    assert sent["fx_hidden_writes_other"] == "0" and int(sent["fx_hidden_writes_page"]) >= 1
    ev = api.get(f"/applications/{app_id}/attempts").json()[0]["evidence"]
    assert {"field": "location", "disclosed": "location_search_text"} in [
        e["data"] for e in ev if e["kind"] == "disclosure"]  # fmt: skip
    assert "Springfield" not in json.dumps(ev)  # evidence keeps no value


@pytest.mark.parametrize(
    "loc,reason",
    [
        ("two", adapter.LOCATION_SEVERAL),  # two suggestions exactly "Springfield"
        ("none", adapter.LOCATION_NONE),  # none exactly it
        ("ignores", adapter.LOCATION_NOT_SET),  # the page never sets the hidden values
        ("label_only", adapter.LOCATION_NOT_SET),  # a matching label alone is not proof
    ],
)
@MAKE
def test_a_location_that_is_not_exactly_one_suggestion_set_by_the_page_stops_the_attempt(
    api, receiver, make, loc, reason
):
    receiver.config(mode="gh2_loc_search", loc=loc)
    aid = queue(api, make(api, job=LOC_JOB))
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert reason in attempt(aid).outcome_detail
    led = receiver.ledger()
    # The search text was disclosed (counted), nothing was submitted, and it is never retried.
    assert led["accepted"] == 0 and kinds(led) == {"upload": 1, "location_search": 1}
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["disclosures"] == led["disclosures"]


@pytest.mark.parametrize(
    "loc,expected,disclosed",
    [
        ("prefill", "failed_safe", {}),  # already set at load: nothing entered at all
        ("prefill_after_upload", "abandoned", {"upload": 1}),  # "from the resume": not typed
    ],
)
@MAKE
def test_a_location_the_page_filled_itself_is_never_trusted(
    api, receiver, make, loc, expected, disclosed
):
    receiver.config(mode="gh2_loc_search", loc=loc)
    aid = queue(api, make(api, job=LOC_JOB))
    assert runner.run_attempt(aid, "w1") == expected
    assert adapter.LOCATION_PREFILLED in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and kinds(led) == disclosed  # no search text sent


@pytest.mark.parametrize(
    "job,approved,now",
    [
        (JOB, {"mode": "gh2_phone_country"}, {"mode": "gh2_phone_country", "pc": "outside"}),
        (LOC_JOB, {"mode": "gh2_loc_search"}, {"mode": "normal"}),
    ],
)
@MAKE
def test_a_changed_structure_after_approval_stops_before_anything_is_entered(
    api, receiver, make, job, approved, now
):
    """Each stand-in structure is re-proven on the live page before the disclosure gate: the
    picker moved out of the phone group, or the hidden values out of the location's group."""
    receiver.config(**approved)
    aid = queue(api, make(api, job=job, phone="+44 20 7946 0000"))
    receiver.config(**now)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "changed since you approved" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


# ------------------------------------------------------------------ late options, pilot as well


@pytest.mark.parametrize(
    "dd,expected", [("late_fetch", "confirmed"), ("late_never", "failed_safe")]
)
@MAKE
def test_late_options_through_both_adapters(api, receiver, make, dd, expected):
    receiver.config(mode="gh2_dd", dd=dd, delay_ms=800)
    aid = queue(api, make(api))
    assert runner.run_attempt(aid, "w1") == expected, attempt(aid).outcome_detail
    led = receiver.ledger()
    if expected == "confirmed":
        sent = led["acceptances"][0]["fields"]
        assert (sent["question_8101"], sent["question_8102"], sent["question_8104"]) == (
            "1", "913", "0")  # fmt: skip
    else:
        assert "its list could not be read completely" in attempt(aid).outcome_detail
        assert led["disclosures"] == [] and led["accepted"] == 0


# ------------------------------------------------------------------ real destinations stay refused


@pytest.mark.parametrize(
    "job,cfg,reason",
    [
        (JOB, {"mode": "gh2_phone_country"}, adapter.STAND_IN_ONLY),
        (LOC_JOB, {"mode": "gh2_loc_search"}, adapter.STAND_IN_ONLY),
        (JOB, {"mode": "gh2_dd", "dd": "late_fetch"},
         "its options load from the network (not verified)"),
    ],
)  # fmt: skip
def test_on_a_destination_that_is_not_a_stand_in_they_stop_before_anything_is_entered(
    api, receiver, monkeypatch, job, cfg, reason
):
    """The adapter's own check, as it runs on a real board (where no origin is a fixture): the
    form stops before the disclosure gate, and late options are refused as before D104."""
    receiver.config(**cfg)
    app_id = d104_application(api, job=job, phone="+44 20 7946 0000")
    aid = queue(api, app_id)
    monkeypatch.setattr(adapter, "stand_ins", lambda content: False)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert reason in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_capabilities_stay_fixture_only_and_real_destinations_refused():
    for k in ("late_loading_options", "phone_country", "location_picker"):
        assert dropdowns.CAPABILITIES[k].startswith("fixture_only"), k
    assert policy.CAPABILITIES["greenhouse_dom"]["real_destinations"] is False
    assert all(v.startswith("synthetic")
               for v in policy.CAPABILITIES["greenhouse_dom"]["unverified"].values())  # fmt: skip
    from app.modules.providers import readiness

    assert not any(c["met"] for c in readiness.conditions())  # fixture evidence meets nothing


# ------------------------------------------------------------------ package content and route


def test_only_forms_with_these_controls_carry_a_widget_so_schema_version_stays(api, receiver):
    """No SCHEMA_VERSION bump: a package gains `.answers[].widget` only for a form with one of
    these stand-in controls (captured under greenhouse-dom-v3). Every other package keeps the
    shape pinned for version 3, and so its content and hash."""
    assert pk.SCHEMA_VERSION == 3
    _, plain = prepare(api)  # the v2 form without them (normal mode)
    assert paths(content(api, plain)) <= SHAPES[3]
    receiver.config(mode="gh2_loc_search")
    job_id, loc = prepare(api, job=LOC_JOB)
    assert paths(content(api, loc)) - SHAPES[3] == {".answers[].widget"}
    route = api.get(f"/jobs/{job_id}/route").json()
    assert (route["route"], route["provider"]) == ("browser", "greenhouse_dom")
    assert gh.EXTRACTION_VERSION == "greenhouse-v1" and dom.EXTRACTION_VERSION.endswith("-v3")
