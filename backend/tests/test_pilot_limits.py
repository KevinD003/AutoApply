"""D161 (rank 28): the Greenhouse pilot (`greenhouse_dom`, `greenhouse_live`) holds an answer to
the length limit its page shows. D158's and D159's limit for the pilot: its capture read no
page limit, so an answer longer than the page's `maxlength` was approved, typed cut by the
browser, and stopped by the readback only after the résumé had been uploaded.

Against the second Greenhouse-style stand-in (fixtures/ats_receiver/greenhouse_v2.py; its limits,
the page's scripts that set them and its saves as you type are FIXTURE ASSUMPTIONS, never seen
on a real page): the capture alone; through the API; through the runner, with the receiver's
ledger as the oracle (its acceptances and disclosures); the browser's own behaviour in Chromium;
and the read-only survey, as it reads a page."""

import json
import sys

import pytest
from playwright.sync_api import sync_playwright

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters import fixture_ats
from app.modules.execution.adapters import greenhouse_dom as adapter
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import gh_readonly as ro
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import FieldType, FormField
from tests.execution_harness import (
    BASE,
    ROOT,
    Receiver,
    attempt,
    pilot_on,
    queue,
    synthetic_candidate,
)

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
NAME = "preferred_name"  # a required typed question, answered by you ("Sammy")
TEAM = "question_8105"  # "Which team did you work in?", shown once you worked there before


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def api_json() -> dict:
    return greenhouse_v2._api_json(BOARD, JOB, BASE)


def page_html(**cfg) -> str:
    return greenhouse_v2._form_page(BOARD, JOB, "t", {"mode": "normal", **cfg}).body.decode()


def recorded(**cfg) -> dict:
    """What the pilot's capture records of each question's limit, from the page as served."""
    schema, _ = dom.build_schema(api_json(), page_html(**cfg), stand_ins=True)
    return {f.key: f.max_length for f in schema.fields}


def without_d161(monkeypatch) -> None:
    """D161's parts switched off: the capture records no limit, and the adapter checks none."""
    monkeypatch.setattr(dom, "control_limit", lambda f, c: None)
    monkeypatch.setattr(adapter.GreenhouseDomAdapter, "_limits_fit", lambda self, page: None)
    monkeypatch.setattr(adapter.GreenhouseDomAdapter, "_cut_at_focus",
                        staticmethod(lambda loc, text: None))  # fmt: skip


def a_job(api) -> str:
    return api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{JOB}",
            "title": "Support Specialist",
            "employer": "Northwind Example (fictional)",
        },
    ).json()["job"]["id"]


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def approve(api, app_id):
    p = package(api, app_id)
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def application(api, *, name="Sammy", worked_before="No", team=None, approve_it=True) -> str:
    """The synthetic candidate's application on the stand-in, read as the receiver now serves it.
    You answer what the resolver must not guess; "Which team" only once it can be shown."""
    synthetic_candidate(api)
    job_id = a_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {NAME: {"text": name}, "question_8101": {"label": "Yes"},
               "question_8104": {"label": worked_before}}  # fmt: skip
    if team is not None:
        answers["question_8105"] = {"text": team}
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    if approve_it:
        assert not package(api, app_id)["content"]["unresolved"]
        assert approve(api, app_id).status_code == 200
    return app_id


def pilot_application(api, **kw) -> str:
    """The same through the Greenhouse pilot (`greenhouse_live`)."""
    pilot_on()
    return application(api, **kw)


MAKE = pytest.mark.parametrize("make", [application, pilot_application], ids=["by_id", "pilot"])


def sent(receiver) -> dict:
    (acc,) = receiver.ledger()["acceptances"]
    return acc["fields"]


def saves(receiver, field: str) -> list[int]:
    """What the page saved of a question as it was typed: lengths only (`autosave`)."""
    return [json.loads(d["detail"])["length"] for d in receiver.ledger()["disclosures"]
            if d["kind"] == "autosave" and json.loads(d["detail"])["field"] == field]  # fmt: skip


def uploads(receiver) -> int:
    return sum(d["kind"] == "upload" for d in receiver.ledger()["disclosures"])


def pauses(app_id: str) -> list[ApplicationPause]:
    import uuid

    from sqlalchemy import select

    with SessionLocal() as db:
        return db.scalars(
            select(ApplicationPause)
            .where(ApplicationPause.application_id == uuid.UUID(app_id))
            .order_by(ApplicationPause.created_at)
        ).all()


# ---------------------------------------------------------------------------- the capture


@pytest.mark.parametrize(
    "written, want",
    [("3", 3), (" 040 ", 40), (["4", "9"], 4), ("3.0", None), ("+3", None), ("0", None),
     ("-1", None), ("３", None), ("", None), ("2147483648", None)],
)  # fmt: skip
def test_the_pilot_records_a_typed_question_s_limit_as_the_browser_reads_it(written, want):
    """As D158 reads an ordinary question's: ASCII digits, ASCII whitespace around them, the
    first of two attributes; a limit written so that no read records it (a sign, a decimal
    point, another script's digit, 0, more than the browser reads) is not recorded (the adapter
    stops at it, below)."""
    assert recorded(gh2_limits={NAME: written})[NAME] == want


@pytest.mark.parametrize(
    "type_, want",
    [("text", 3), ("search", 3), ("SEARCH", 3), ("url", 3), ("tel", 3), ("email", 3),
     ("number", None)],
)  # fmt: skip
def test_a_limit_is_recorded_only_where_the_browser_holds_typing_to_it(type_, want):
    """The LinkedIn question on another kind of input: `maxlength` limits nothing typed into a
    number input, and the browser reads `type` case-insensitively."""
    got = recorded(gh2_limits={"question_8103": "3"}, gh2_types={"question_8103": type_})
    assert got["question_8103"] == want


@pytest.mark.parametrize(
    "markup, limited",
    [('<input id="c" maxlength="3">', True),
     ('<input id="c" type="foo" maxlength="3">', True),  # a type the browser does not know: text
     ('<input id="c" type="number" type="text" maxlength="3">', False),  # the first type
     ('<input id="c" type="text" type="number" maxlength="3">', True),
     ('<input id="c" type="date" maxlength="3">', False),
     ('<textarea id="c" maxlength="3"></textarea>', True),
     # a locked control too: the page's script may unlock it before anything is typed (below)
     ('<input id="c" maxlength="3" disabled>', True),
     ('<input id="c" maxlength="3" readonly>', True),
     ('<fieldset disabled><input id="c" maxlength="3"></fieldset>', True),
     ('<div inert><input id="c" maxlength="3"></div>', True),
     # except one the page locks and fills itself (D129): nothing is typed into it
     ('<input id="c" maxlength="3" disabled value="x">', False),
     ('<input id="c" maxlength="3" readonly value="x">', False),
     ('<textarea id="c" maxlength="3" readonly>x</textarea>', False),
     ('<input id="c" maxlength="3" inert value="x">', False),
     ('<div inert><input id="c" maxlength="3" value="x"></div>', False),
     ('<fieldset disabled><input id="c" maxlength="3" value="x"></fieldset>', False),
     ('<fieldset disabled><legend><input id="c" maxlength="3" value="x"></legend></fieldset>',
      True),  # inside the first legend: not locked
     ('<input id="c" maxlength="3" value="x">', True),  # filled, not locked
     ('<select id="c" maxlength="3"></select>', False)],
)  # fmt: skip
def test_the_capture_reads_which_controls_hold_typing_to_a_limit(markup, limited):
    (c,) = dom.snapshot(f"<form>{markup}</form>")
    assert (c.limited, c.maxlength) == (limited, "3")
    f = FormField(key="c", label="C", type=FieldType.text, required=False)
    assert dom.control_limit(f, c) == (3 if limited else None)


@pytest.mark.parametrize("ftype", [FieldType.select, FieldType.file, FieldType.number])
def test_only_a_typed_answer_is_held_to_a_limit(ftype):
    (c,) = dom.snapshot('<form><input id="c" maxlength="3"></form>')
    options = [{"value": "1", "label": "One"}] if ftype == FieldType.select else []
    f = FormField(key="c", label="C", type=ftype, required=False, options=options)
    assert dom.control_limit(f, c) is None


def test_a_limit_only_the_page_s_script_sets_is_not_recorded():
    """The capture reads the page as served, without its scripts (the adapter checks the live
    page before anything is entered, below)."""
    assert recorded(gh2_limit_js={NAME: 3})[NAME] is None


def test_a_locked_control_s_limit_is_recorded_unless_the_page_fills_it():
    """D161 reviews: a control served locked and unlocked by the page's script (disabled until
    shown, read-only until it has focus) is typed into, and held to the limit it was served
    with; skipping every locked control left a pause no read of the form could end. One the page
    locks and fills itself is never typed (D129's pre-filled email): no answer of yours is held
    to its limit."""
    assert recorded(gh2_unlock=[NAME], gh2_limits={NAME: "3"})[NAME] == 3
    assert recorded(gh2_readonly_focus=[NAME], gh2_limits={NAME: "3"})[NAME] == 3
    assert recorded(mode="gh2_email_locked_match", gh2_limits={"email": "4"})["email"] is None
    assert recorded(mode="gh2_email_locked_empty", gh2_limits={"email": "4"})["email"] == 4


def test_the_limit_of_a_question_the_page_shows_later_is_recorded():
    """D135: "Which team" is hidden at load (its trigger unknown) and answerable: its limit is
    held to before you approve, as any other."""
    schema, _ = dom.build_schema(api_json(), page_html(gh2_limits={"question_8105": "8"}),
                                 stand_ins=True)  # fmt: skip
    (f,) = [f for f in schema.fields if f.key == "question_8105"]
    assert f.max_length == 8 and f.condition is not None


# ---------------------------------------------------------------------------- the API


@MAKE
def test_an_answer_longer_than_the_page_s_limit_is_yours_to_shorten_before_approval(
    api, receiver, make
):
    """Before D161 it was approved (below). Now it is refused when saved, naming the limit, and
    a shorter one is sent whole."""
    receiver.config(gh2_limits={NAME: "3"})
    app_id = make(api, name="Sam")
    r = api.put(f"/applications/{app_id}/answers", json={"key": NAME, "value": {"text": "Sammy"}})
    assert r.status_code == 400 and "5/3 characters as the form sends them" in r.text
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[NAME] == "Sam"


@MAKE
def test_an_answer_at_the_page_s_limit_is_sent_whole(api, receiver, make):
    receiver.config(gh2_limits={NAME: "5"})
    app_id = make(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[NAME] == "Sammy"


# ---------------------------------------------------------------------------- the runner


@MAKE
def test_before_d161_an_answer_past_the_page_s_limit_was_typed_cut_after_the_upload(
    api, receiver, make, monkeypatch
):
    """The oracle: with D161's parts off, "Sammy" was approved on a page whose limit is 3; the
    page held it cut as it was typed, after the résumé had been uploaded; the readback stopped
    the attempt then."""
    without_d161(monkeypatch)
    receiver.config(gh2_limits={NAME: "3"}, gh2_autosave=[NAME])
    app_id = make(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and uploads(receiver) == 1
    assert saves(receiver, NAME) == [3]


@MAKE
def test_a_limit_the_page_s_script_lowers_pauses_before_anything_is_entered(api, receiver, make):
    """Approved under no limit; the page's script then sets 3 as it loads. Before anything is
    entered (no upload, nothing typed): D132's pause, naming the limit (never the question)."""
    app_id = make(api)
    receiver.config(gh2_limit_js={NAME: 3}, gh2_autosave=[NAME])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open" and p.detail == {"new": 0, "changed": 1, "missing": 0}
    assert "3 characters as the form sends them" in attempt(aid).outcome_detail


@MAKE
def test_a_limit_written_so_no_read_records_it_stops_plainly_naming_it(api, receiver, make):
    """Written "3.0", the browser reads 3 and a read of the form nothing: a pause could never be
    ended by reading the form again. A plain stop, nothing entered."""
    app_id = make(api)
    receiver.config(gh2_limits={NAME: "3.0"})
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and pauses(app_id) == []
    assert fixture_ats.LIMIT_UNREADABLE.format(limits=3) in attempt(aid).outcome_detail


def test_reading_the_form_again_records_the_limit_the_page_now_shows(api, receiver):
    """The employer added a limit to the page after you approved: the attempt pauses with nothing
    entered; reading the form again records it (a new version), your answer is then yours to
    shorten, and the shorter one is sent."""
    app_id = application(api)
    receiver.config(gh2_limits={NAME: "3"})
    assert runner.run_attempt(queue(api, app_id), "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    out = api.post(f"/applications/{app_id}/form/recapture")
    assert out.status_code == 200, out.text
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("resolved", "new_form")
    c = package(api, app_id)["content"]
    assert NAME in c["unresolved"]
    r = api.put(f"/applications/{app_id}/answers", json={"key": NAME, "value": {"text": "Sam"}})
    assert r.status_code == 200, r.text
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[NAME] == "Sam"


@MAKE
def test_a_limit_lowered_as_the_control_gets_focus_is_never_typed_cut(api, receiver, make):
    """The page lowers the limit as the box gets focus, after the form was checked, and saves it
    as it is typed: it is never typed (no save of it at all), and nothing is sent."""
    app_id = make(api)
    receiver.config(gh2_limit_on_focus={NAME: 3}, gh2_autosave=[NAME])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, NAME) == []
    # D161 review: filling stops there, naming the limit, so you know what to shorten
    assert adapter.LIMIT_AT_FOCUS.format(limits=3) in attempt(aid).outcome_detail


def test_before_d161_a_limit_lowered_on_focus_left_the_page_holding_it_cut(
    api, receiver, monkeypatch
):
    """The oracle: the page saved 3 of its characters."""
    without_d161(monkeypatch)
    app_id = application(api)
    receiver.config(gh2_limit_on_focus={NAME: 3}, gh2_autosave=[NAME])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert saves(receiver, NAME) == [3]


def test_a_question_the_page_shows_is_not_entered_when_its_limit_is_lowered_on_focus(api, receiver):
    """D135: "Which team" is shown by your earlier answer and entered last; the page lowers its
    limit as it gets focus: it is not entered (no save of it), and filling stops there, naming
    the limit."""
    app_id = application(api, worked_before="Yes", team="Support team")
    receiver.config(gh2_limit_on_focus={TEAM: 3}, gh2_autosave=[TEAM])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, TEAM) == []
    assert adapter.LIMIT_AT_FOCUS.format(limits=3) in attempt(aid).outcome_detail


def test_before_d161_the_question_the_page_shows_was_typed_cut(api, receiver, monkeypatch):
    without_d161(monkeypatch)
    app_id = application(api, worked_before="Yes", team="Support team")
    receiver.config(gh2_limit_on_focus={TEAM: 3}, gh2_autosave=[TEAM])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert saves(receiver, TEAM) == [3]


@MAKE
def test_a_limit_lowered_once_the_answer_is_typed_stops_before_the_send_gate(api, receiver, make):
    """Typed whole, then the page lowers the limit: the check after filling stops the attempt
    before the send gate; nothing is sent."""
    app_id = make(api)
    receiver.config(gh2_limit_on_input={NAME: 3}, gh2_autosave=[NAME])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, NAME) == [5]


UNLOCKS = [{"gh2_unlock": [NAME]}, {"gh2_readonly_focus": [NAME]}]


@MAKE
@pytest.mark.parametrize("lock", UNLOCKS, ids=["disabled_until_loaded", "readonly_until_focus"])
def test_a_control_the_page_unlocks_is_held_to_the_limit_it_was_served_with(
    api, receiver, make, lock
):
    """D161 reviews: served disabled (enabled by the page's script) or read-only until it has
    focus (a common guard against autofill), with a limit of 3. Before the fix the capture
    recorded no limit, "Sammy" was approved, and the attempt paused for a form no read of it
    could change. Now the limit is yours before approval."""
    receiver.config(**lock, gh2_limits={NAME: "3"}, gh2_autosave=[NAME])
    app_id = make(api, name="Sam")
    r = api.put(f"/applications/{app_id}/answers", json={"key": NAME, "value": {"text": "Sammy"}})
    assert r.status_code == 400 and "5/3 characters as the form sends them" in r.text
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[NAME] == "Sam" and saves(receiver, NAME) == [3]


def test_after_filling_a_question_the_page_did_not_show_is_not_held_to_its_limit(api, receiver):
    """D161 review: "Which team" is answered but not shown (you never worked there), so it is
    never entered and nothing is sent for it; the page lowers its limit once anything is typed.
    The check after filling leaves it alone, as the readback does."""
    app_id = application(api, worked_before="No", team="Support team")
    receiver.config(gh2_limit_once_typed={TEAM: 3})
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert TEAM not in sent(receiver)


def test_a_locked_prefilled_email_is_not_held_to_a_limit_the_page_sets(api, receiver):
    """D129: the page pre-fills a disabled email with the approved one, and its script then sets
    a limit shorter than it. Nothing is typed into it, so it is not checked: sent as the page
    holds it."""
    receiver.config(mode="gh2_email_locked_match", gh2_limit_js={"email": 4})
    app_id = application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert sent(receiver)["email"] == "sam.synthetic@example.com"


# ---------------------------------------------------------------------------- the survey


@pytest.fixture
def survey(monkeypatch):
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")

    def run():
        obs = ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api_json())
        text = ro.guard(ro.publishable(api_json(), {"name": "x"}, JOB, obs),
                        ro.sensitive_values(BOARD, JOB, api_json(), None))  # fmt: skip
        assert '"length_limit"' in text  # published as it is: numbers and the vocabulary only
        return {f["key"]: f["length_limit"] for f in obs["mapping"]["fields"]}

    return run


def test_the_survey_reports_each_typed_question_s_limit_as_the_browser_and_capture_read_it(
    receiver, survey
):
    limits = {NAME: "3", "first_name": "3.0", "last_name": "3"}
    receiver.config(gh2_limits=limits, gh2_types={"last_name": "number"},
                    gh2_limit_js={"question_8103": 7})  # fmt: skip
    got = survey()
    assert got[NAME] == {"browser_reads": 3, "capture_records": 3}
    assert got["first_name"] == {"browser_reads": 3, "capture_records": None}  # no read records
    assert got["question_8103"] == {"browser_reads": 7, "capture_records": None}  # its script's
    assert got["last_name"] == {"browser_reads": None, "capture_records": None}  # a number box
    assert got["question_8101"] == "not_applicable"  # a list
    assert got["resume"] == "not_applicable"  # a file
    assert receiver.ledger()["disclosures"] == []


def test_the_survey_says_which_typed_question_has_no_control_to_read(receiver, survey):
    receiver.config(mode="gh2_missing_control")
    assert survey()["question_8103"] == "not_observable"


def test_the_survey_says_what_it_could_not_read_of_the_page_as_served(
    receiver, survey, monkeypatch
):
    monkeypatch.setattr(ro, "_served_html", lambda resp: None)
    receiver.config(gh2_limits={NAME: "3"})
    got = survey()
    assert got[NAME] == {"browser_reads": 3, "capture_records": "not_observable"}


# ---------------------------------------------------------------------------- Chromium


CASES = [  # (markup, a value to type): the browser's own behaviour is the oracle
    ('<input id="c" maxlength="3">', "abcdef"),
    ('<input id="c" type="TEXT" maxlength="3">', "abcdef"),
    ('<input id="c" type="foo" maxlength="3">', "abcdef"),
    ('<input id="c" type="search" maxlength="3">', "abcdef"),
    ('<input id="c" type="url" maxlength="3">', "abcdef"),
    ('<input id="c" type="tel" maxlength="3">', "abcdef"),
    ('<input id="c" type="email" maxlength="3">', "abcdef"),
    ('<input id="c" type="password" maxlength="3">', "abcdef"),
    ('<input id="c" type="number" maxlength="3">', "123456"),
    ('<input id="c" type="number" type="text" maxlength="3">', "123456"),
    ('<input id="c" type="text" type="number" maxlength="3">', "abcdef"),
    ('<textarea id="c" maxlength="3"></textarea>', "abcdef"),
]


@pytest.fixture(scope="module")
def chromium():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.mark.parametrize("markup, value", CASES)
def test_a_limit_is_recorded_exactly_where_the_browser_cuts_what_is_typed(chromium, markup, value):
    page = chromium.new_page()
    try:
        page.set_content(f"<form>{markup}</form>")
        loc = page.locator("#c")
        loc.fill(value)
        cut = loc.input_value() != value
        (c,) = dom.snapshot(f"<form>{markup}</form>")
        assert c.limited == cut
        limit, written, applies = loc.evaluate(dom.LIVE_LIMIT_JS)
        assert (applies, limit, written) == (cut, 3, "3")
    finally:
        page.close()


def test_a_control_served_locked_and_unlocked_by_the_page_is_cut_as_typed(chromium):
    """The oracle for recording a locked control's limit: once the page's script unlocks it, the
    browser holds what is typed to the limit it was served with."""
    html = '<form><input id="c" maxlength="3" disabled></form><script>c.disabled = false;</script>'
    page = chromium.new_page()
    try:
        page.set_content(html)
        page.locator("#c").fill("abcdef")
        assert page.locator("#c").input_value() == "abc"
        (c,) = dom.snapshot(html)
        assert (c.limited, c.maxlength) == (True, "3")
    finally:
        page.close()


def test_the_live_read_goes_through_the_browser_s_own_definitions(chromium):
    """D161 review: a page that redefines `maxLength`, `getAttribute` or `type` on the element
    itself cannot change what the check before typing reads."""
    page = chromium.new_page()
    try:
        page.set_content(
            '<input id="c" maxlength="3"><div id="d"></div><script>'
            "Object.defineProperty(c, 'maxLength', {get: () => -1});"
            "c.getAttribute = () => null;"
            "Object.defineProperty(c, 'type', {get: () => 'number'});</script>"
        )
        assert page.locator("#c").evaluate(dom.LIVE_LIMIT_JS) == [3, "3", True]
        assert page.locator("#d").evaluate(dom.LIVE_LIMIT_JS) == [-1, None, False]
    finally:
        page.close()


def limits_fit(page, answers, filled=False, shown=()):
    a = object.__new__(adapter.GreenhouseDomAdapter)
    a.content = {"answers": answers}
    a._trusted_prefill, a._filled, a._shown_filled = set(), filled, set(shown)
    return a._limits_fit(page)


def answer(key, value, kind="text", **kw):
    return {"key": key, "type": kind, "value": value, **kw}


def test_what_the_check_holds_to_the_live_limit(chromium):
    """Typed text only: a text area as an input; not a number, not a box whose type the browser
    holds to no limit, not the location search's text (a search the page answers with its own
    suggestion, D104); after filling, not a question the page did not show (D135)."""
    page = chromium.new_page()
    try:
        page.set_content('<form><input id="a" maxlength="3"><textarea id="b" maxlength="3">'
                         '</textarea><input id="location" maxlength="3">'
                         '<input id="n" type="number" maxlength="3"></form>')  # fmt: skip
        over = {"text": "abcd"}
        assert limits_fit(page, [answer("a", over)])
        assert limits_fit(page, [answer("b", over, "textarea")])
        assert limits_fit(page, [answer("a", {"number": 12345})]) is None
        assert limits_fit(page, [answer("n", over)]) is None  # a number box limits nothing
        assert limits_fit(page, [answer("location", over, widget="location_search")]) is None
        hidden = answer("a", over, condition={"key": "unknown-trigger", "any_of": ["?"]})
        assert limits_fit(page, [hidden])  # before filling: it may be shown and typed
        assert limits_fit(page, [hidden], filled=True) is None  # not shown: never entered
        assert limits_fit(page, [hidden], filled=True, shown=["a"])
    finally:
        page.close()


def test_the_check_before_typing_reads_the_limit_once_the_control_has_focus(chromium):
    page = chromium.new_page()
    try:
        page.set_content(
            '<input id="a"><input id="b" type="number"><script>'
            'a.addEventListener("focus", () => { a.maxLength = 3; });'
            'b.addEventListener("focus", () => { b.maxLength = 3; });</script>'
        )
        cut = adapter.GreenhouseDomAdapter._cut_at_focus
        assert cut(page.locator("#a"), "abc") is None
        assert cut(page.locator("#a"), "abcd") == 3
        # counted as the form sends it (D158): an emoji counts two
        assert cut(page.locator("#a"), "ab\U0001f600") == 3
        assert cut(page.locator("#b"), "123456") is None
    finally:
        page.close()
