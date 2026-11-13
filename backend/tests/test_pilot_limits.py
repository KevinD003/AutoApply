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
    monkeypatch.setattr(adapter.GreenhouseDomAdapter, "_fits_here",
                        staticmethod(lambda loc, text: True))  # fmt: skip


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
    assert recorded(limits={NAME: written})[NAME] == want


def test_before_d161_the_pilot_recorded_no_limit(monkeypatch):
    monkeypatch.setattr(dom, "control_limit", lambda f, c: None)
    assert recorded(limits={NAME: "3"})[NAME] is None


@pytest.mark.parametrize(
    "type_, want",
    [("text", 3), ("search", 3), ("SEARCH", 3), ("url", 3), ("tel", 3), ("email", 3),
     ("number", None)],
)  # fmt: skip
def test_a_limit_is_recorded_only_where_the_browser_holds_typing_to_it(type_, want):
    """The LinkedIn question on another kind of input: `maxlength` limits nothing typed into a
    number input, and the browser reads `type` case-insensitively."""
    got = recorded(limits={"question_8103": "3"}, types={"question_8103": type_})
    assert got["question_8103"] == want


@pytest.mark.parametrize(
    "markup, limited",
    [('<input id="c" maxlength="3">', True),
     ('<input id="c" type="foo" maxlength="3">', True),  # a type the browser does not know: text
     ('<input id="c" type="number" type="text" maxlength="3">', False),  # the first type
     ('<input id="c" type="text" type="number" maxlength="3">', True),
     ('<input id="c" type="date" maxlength="3">', False),
     ('<textarea id="c" maxlength="3"></textarea>', True),
     ('<input id="c" maxlength="3" disabled>', False),  # nothing is typed into a locked control
     ('<input id="c" maxlength="3" readonly>', False),
     ('<textarea id="c" maxlength="3" readonly></textarea>', False),
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
    assert recorded(limit_js={NAME: 3})[NAME] is None


def test_a_locked_prefilled_email_records_no_limit():
    """D129: a real account pre-fills a disabled email; nothing is typed into it."""
    assert recorded(mode="gh2_email_locked_match", limits={"email": "4"})["email"] is None


def test_the_limit_of_a_question_the_page_shows_later_is_recorded():
    """D135: "Which team" is hidden at load (its trigger unknown) and answerable: its limit is
    held to before you approve, as any other."""
    schema, _ = dom.build_schema(api_json(), page_html(limits={"question_8105": "8"}),
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
    receiver.config(limits={NAME: "3"})
    app_id = make(api, name="Sam")
    r = api.put(f"/applications/{app_id}/answers", json={"key": NAME, "value": {"text": "Sammy"}})
    assert r.status_code == 400 and "5/3 characters as the form sends them" in r.text
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert sent(receiver)[NAME] == "Sam"


@MAKE
def test_an_answer_at_the_page_s_limit_is_sent_whole(api, receiver, make):
    receiver.config(limits={NAME: "5"})
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
    receiver.config(limits={NAME: "3"}, autosave=[NAME])
    app_id = make(api)
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and uploads(receiver) == 1
    assert saves(receiver, NAME) == [3]


@MAKE
def test_a_limit_the_page_s_script_lowers_pauses_before_anything_is_entered(api, receiver, make):
    """Approved under no limit; the page's script then sets 3 as it loads. Before anything is
    entered (no upload, nothing typed): D132's pause, naming the limit (never the question)."""
    app_id = make(api)
    receiver.config(limit_js={NAME: 3}, autosave=[NAME])
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
    receiver.config(limits={NAME: "3.0"})
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == [] and pauses(app_id) == []
    assert fixture_ats.LIMIT_UNREADABLE.format(limits=3) in attempt(aid).outcome_detail


def test_reading_the_form_again_records_the_limit_the_page_now_shows(api, receiver):
    """The employer added a limit to the page after you approved: the attempt pauses with nothing
    entered; reading the form again records it (a new version), your answer is then yours to
    shorten, and the shorter one is sent."""
    app_id = application(api)
    receiver.config(limits={NAME: "3"})
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
    receiver.config(limit_on_focus={NAME: 3}, autosave=[NAME])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, NAME) == []


def test_before_d161_a_limit_lowered_on_focus_left_the_page_holding_it_cut(
    api, receiver, monkeypatch
):
    """The oracle: the page saved 3 of its characters."""
    without_d161(monkeypatch)
    app_id = application(api)
    receiver.config(limit_on_focus={NAME: 3}, autosave=[NAME])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert saves(receiver, NAME) == [3]


TEAM = "question_8105"  # "Which team did you work in?", shown once you worked there before


def test_a_question_the_page_shows_is_not_entered_when_its_limit_is_lowered_on_focus(api, receiver):
    """D135: "Which team" is shown by your earlier answer and entered last; the page lowers its
    limit as it gets focus: it is not entered (no save of it), and the check after filling stops
    the attempt (shown, and not entered)."""
    app_id = application(api, worked_before="Yes", team="Support team")
    receiver.config(limit_on_focus={TEAM: 3}, autosave=[TEAM])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, TEAM) == []


def test_before_d161_the_question_the_page_shows_was_typed_cut(api, receiver, monkeypatch):
    without_d161(monkeypatch)
    app_id = application(api, worked_before="Yes", team="Support team")
    receiver.config(limit_on_focus={TEAM: 3}, autosave=[TEAM])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert saves(receiver, TEAM) == [3]


@MAKE
def test_a_limit_lowered_once_the_answer_is_typed_stops_before_the_send_gate(api, receiver, make):
    """Typed whole, then the page lowers the limit: the check after filling stops the attempt
    before the send gate; nothing is sent."""
    app_id = make(api)
    receiver.config(limit_on_input={NAME: 3}, autosave=[NAME])
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    assert receiver.ledger()["accepted"] == 0 and saves(receiver, NAME) == [5]


def test_a_locked_prefilled_email_is_not_held_to_a_limit_the_page_sets(api, receiver):
    """D129: the page pre-fills a disabled email with the approved one, and its script then sets
    a limit shorter than it. Nothing is typed into it, so it is not checked: sent as the page
    holds it."""
    receiver.config(mode="gh2_email_locked_match", limit_js={"email": 4})
    app_id = application(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed", attempt(aid).outcome_detail
    assert sent(receiver)["email"] == "sam.synthetic@example.com"


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


def test_the_check_before_typing_reads_the_limit_once_the_control_has_focus(chromium):
    page = chromium.new_page()
    try:
        page.set_content(
            '<input id="a"><input id="b" type="number"><script>'
            'a.addEventListener("focus", () => { a.maxLength = 3; });'
            'b.addEventListener("focus", () => { b.maxLength = 3; });</script>'
        )
        assert adapter.GreenhouseDomAdapter._fits_here(page.locator("#a"), "abc")
        assert not adapter.GreenhouseDomAdapter._fits_here(page.locator("#a"), "abcd")
        # counted as the form sends it (D158): an emoji counts two
        assert not adapter.GreenhouseDomAdapter._fits_here(page.locator("#a"), "ab\U0001f600")
        assert adapter.GreenhouseDomAdapter._fits_here(page.locator("#b"), "123456")
    finally:
        page.close()


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
    receiver.config(limits={NAME: "3", "first_name": "3.0"}, limit_js={"question_8103": 7})
    got = survey()
    assert got[NAME] == {"browser_reads": 3, "capture_records": 3}
    assert got["first_name"] == {"browser_reads": 3, "capture_records": None}  # no read records
    assert got["question_8103"] == {"browser_reads": 7, "capture_records": None}  # its script's
    assert got["last_name"] == {"browser_reads": None, "capture_records": None}
    assert got["question_8101"] == "not_applicable"  # a list
    assert got["resume"] == "not_applicable"  # a file
    assert receiver.ledger()["disclosures"] == []


def test_the_survey_says_what_it_could_not_read_of_the_page_as_served(
    receiver, survey, monkeypatch
):
    monkeypatch.setattr(ro, "_served_html", lambda resp: None)
    receiver.config(limits={NAME: "3"})
    got = survey()
    assert got[NAME] == {"browser_reads": 3, "capture_records": "not_observable"}
