"""D148: a Workday-style follow-up question, one the page shows after an earlier answer by its own
logic (FIXTURE ASSUMPTION FA6, fixtures/ats_receiver/workday_like.py), on a wizard's page and on
the single page. Capture reads it hidden inside its page as `Condition(UNKNOWN_TRIGGER)`; only
you (or an approved profile fact) answer it; it is entered only when the page shows it, and what
the page shows after filling must be what was entered.

The receiver's own ledger is the oracle for what reached the employer: its `draft_page` rows (a
wizard page's Next) and its acceptances, never NoEfforts' tables. Passing here shows fixture
compatibility only, never how a real Workday tenant behaves (no real follow-up was observed).
Synthetic candidate data only."""

import time
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.adapters.fixture_ats import (
    CONDITIONAL_REQUIRED,
    ConditionalRequired,
    FormChanged,
)
from app.modules.execution.adapters.workday import (
    FOLLOW_UP_CHANGED,
    FOLLOW_UP_HIDDEN_REQUIRED,
    FOLLOW_UP_NOT_FILLED,
    UNSEEN_LOGIC,
    WorkdayFixtureAdapter,
)
from app.modules.execution.models import ApplicationPause
from app.modules.preparation import package as pk
from app.modules.preparation import workday
from app.modules.preparation.forms import UNKNOWN_TRIGGER, FieldType, form_fingerprint
from tests.execution_harness import Receiver, attempt, queue, synthetic_candidate
from tests.test_workday_adapter import fresh_url, workday_job
from tests.test_workday_wizard import PAGES, approve, draft_pages, drafts, posts, rows, steps

FOLLOW_UP = "q.nights_detail"  # FA6, the oracle's own copy
UNKNOWN = {"key": UNKNOWN_TRIGGER, "any_of": ["?"]}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def follow_up_application(api, receiver, shape: str, *, shift: str = "Nights",
                          detail: str | None = None, single: bool = False,
                          approved: bool = True) -> str:  # fmt: skip
    """The follow-up `shape` switched on (a wizard variant, or the single page's mode), then a
    Workday-style application on a posting of its own, captured, answered (the preferred shift,
    and the follow-up when `detail` is given) and, when `approved`, approved."""
    receiver.config(**({"mode": f"wd_{shape}"} if single else {"wizard": shape}))
    synthetic_candidate(api)
    job_id = workday_job(api, url=fresh_url())
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    answers = {"legalName--firstName": {"text": "Sam"}, "q.licence_type": {"label": "RN"},
               "q.shift": {"label": shift}}  # fmt: skip
    if detail is not None:
        answers[FOLLOW_UP] = {"text": detail}
    for key, value in answers.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, (key, r.text)
    r = api.put(f"/applications/{app_id}/consents", json={"key": "terms_ack", "choice": "agree"})
    assert r.status_code == 200, r.text
    if approved:
        assert not r.json()["package"]["content"]["unresolved"]
        assert approve(api, app_id).status_code == 200
    return app_id


def row(api, app_id: str) -> dict:
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return next(a for a in content["answers"] if a["key"] == FOLLOW_UP)


def page_4(led) -> dict:
    (d,) = [d for d in drafts(led) if d["page"] == 4]
    return d["fields"]


# ---------------------------------------------------------------------------- capture

FORM = """<form id="workday-application" action="/apply" method="post">
<section data-step="Application Questions">
<label for="shift">Preferred shift</label>
<select id="shift" name="q.shift" required><option value="">Select One</option>
<option value="Nights">Nights</option></select>
{follow}
</section><button type="submit">Submit</button></form>"""
DETAIL = '<label for="d">Which nights?</label><input id="d" name="q.d" type="text">'


@pytest.mark.parametrize(
    "follow, marked",
    [
        (f"<div hidden>{DETAIL}</div>", True),
        (f'<div aria-hidden="true">{DETAIL}</div>', True),
        (f'<div style="display: none">{DETAIL}</div>', True),
        (f'<div style="color: red; visibility:hidden !important">{DETAIL}</div>', True),
        (f"<div><span>{DETAIL.replace('type=', 'hidden type=')}</span></div>", True),
        (f"<div><div hidden></div>{DETAIL}</div>", False),  # a hidden sibling, closed before it
        (f'<div style="display:block">{DETAIL}</div>', False),
        (f'<div aria-hidden="false">{DETAIL}</div>', False),
    ],
    ids=[
        "hidden",
        "aria-hidden",
        "display-none",
        "visibility-hidden-important",
        "the-control-itself",
        "a-hidden-sibling",
        "display-block",
        "aria-hidden-false",
    ],
)
def test_capture_marks_a_question_hidden_inside_its_page(follow, marked):
    fields = {f.key: f for f in workday.extract_schema(FORM.format(follow=follow)).fields}
    assert fields["q.shift"].condition is None
    got = fields["q.d"].condition
    assert (got.model_dump() == UNKNOWN) if marked else got is None


def test_capture_never_marks_a_checkpoint_and_marks_a_hidden_choice():
    """A picker hidden inside its page stays the checkpoint it is (never conditional); a hidden
    radio group is marked, and so is never filled (D135: only typed text is answerable)."""
    follow = ('<div hidden><label for="loc">Location</label><input id="loc" name="q.loc" '
              'type="text" role="combobox" aria-autocomplete="list">'
              '<fieldset><legend>Weekends too?</legend><label><input type="radio" name="q.w" '
              'value="Yes"> Yes</label></fieldset></div>')  # fmt: skip
    fields = {f.key: f for f in workday.extract_schema(FORM.format(follow=follow)).fields}
    assert fields["q.loc"].type == FieldType.unsupported and fields["q.loc"].condition is None
    assert fields["q.w"].type == FieldType.radio and fields["q.w"].condition.model_dump() == UNKNOWN


def test_capture_reads_only_the_application_form():
    """Hidden-ness is read between a control and its form: a hidden wrapper around the whole
    form, and a hidden control of the same name outside it (a template, outside the form), mark
    none of its questions."""
    html = (f"<div hidden>{FORM.format(follow=DETAIL)}</div>"
            '<template><div hidden><select name="q.shift"></select></div></template>'
            '<div hidden><input name="q.d" type="text"></div>')  # fmt: skip
    fields = workday.extract_schema(html).fields
    assert {f.key for f in fields} == {"q.shift", "q.d"}
    assert all(f.condition is None for f in fields)


def test_a_wizard_page_hidden_at_load_marks_none_of_its_questions(api, receiver):
    """Pages 2 to 5 are hidden at load (FA1); only the follow-up's own wrapper says anything."""
    receiver.config(wizard="follow_up")
    synthetic_candidate(api)
    job_id = workday_job(api, url=fresh_url())
    schema = api.post(f"/jobs/{job_id}/form/workday").json()["schema"]
    assert schema["wizard"] == {"pages": PAGES}
    marked = {f["key"]: f for f in schema["fields"] if f.get("condition")}
    assert list(marked) == [FOLLOW_UP]
    assert marked[FOLLOW_UP]["condition"] == UNKNOWN
    assert marked[FOLLOW_UP]["step"] == "Application Questions"
    assert not marked[FOLLOW_UP]["required"]
    assert {f["step"] for f in schema["fields"]} >= set(PAGES[1:4])  # hidden pages, unmarked


# ---------------------------------------------------------------------------- package


def test_it_is_yours_to_answer_and_never_saved_for_reuse(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up", approved=False)
    r = row(api, app_id)
    assert (r["status"], r["value"], r["user_input_allowed"]) == ("blank_optional", None, True)
    assert not r["bankable"] and not r["draftable"]
    assert pk.SHOWN_BY_PAGE in r["explanation"]


def test_one_required_in_the_markup_waits_for_your_answer(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up_required", approved=False)
    content = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    assert FOLLOW_UP in content["unresolved"]
    assert row(api, app_id)["status"] == "needs_user"
    assert approve(api, app_id).status_code != 200
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": FOLLOW_UP, "value": {"text": "Monday to Wednesday"}})  # fmt: skip
    assert r.status_code == 200 and not r.json()["package"]["content"]["unresolved"]


# ---------------------------------------------------------------------------- the wizard


def test_shown_it_is_entered_on_its_page_and_sent(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up", detail="Monday to Wednesday")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4]
    assert page_4(led)[FOLLOW_UP] == "Monday to Wednesday"
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][FOLLOW_UP] == (
        "Monday to Wednesday")  # fmt: skip
    assert [s["mismatched"] for s in rows(aid, "step")] == [0, 0, 0, 0]
    assert len(rows(aid, "recheck")) == 1


@pytest.mark.parametrize("detail", [None, "Monday to Wednesday"])
def test_not_shown_it_is_never_entered_or_waited_for(api, receiver, detail):
    """Days hides it: an approved answer is not entered (the page never asked), and filling never
    waits for a question the page does not show."""
    app_id = follow_up_application(api, receiver, "follow_up", shift="Days", detail=detail)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert page_4(led)[FOLLOW_UP] == "" and page_4(led)["q.shift"] == "Days"
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][FOLLOW_UP] == ""


def test_shown_optional_and_unanswered_it_stays_empty(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert page_4(led)[FOLLOW_UP] == "" and led["acceptances"][0]["fields"][FOLLOW_UP] == ""


def test_shown_required_and_unanswered_stops_before_its_next(api, receiver):
    """The page marks it required once shown, with no approved answer: the attempt ends with
    page 4 filled and read back, its Next never clicked (a wizard never pauses, D142)."""
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3] and posts(led, "/draft/4") == 0
    assert posts(led, "/apply") == 0 and led["accepted"] == 0
    assert (4, "fill") in steps(aid) and (4, "next") not in steps(aid)
    assert [s["page"] for s in rows(aid, "step")] == [1, 2, 3, 4]
    att = attempt(aid)
    assert att.state == "abandoned" and CONDITIONAL_REQUIRED in att.outcome_detail
    assert FOLLOW_UP not in att.outcome_detail
    with SessionLocal() as db:
        assert not db.scalars(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id))).all()  # fmt: skip


def test_required_once_shown_and_answered_it_is_sent(api, receiver):
    """The page marks it required only once shown: the live form still matches the approved one
    after the page-4 Next (whether it is required then is the page's reaction)."""
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required",
                                   detail="Friday")  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert page_4(led)[FOLLOW_UP] == "Friday"
    assert led["acceptances"][0]["fields"][FOLLOW_UP] == "Friday"


def test_required_in_the_markup_and_answered_is_entered_only_when_shown(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up_required", shift="Days",
                                   detail="Friday")  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert page_4(led)[FOLLOW_UP] == "" and led["acceptances"][0]["fields"][FOLLOW_UP] == ""


@pytest.mark.parametrize("single", [False, True], ids=["wizard", "single-page"])
def test_one_the_page_now_requires_stops_before_anything_is_entered(api, receiver, single):
    """Approved optional and unanswered; the page now marks it required in its markup. Before
    anything is entered that is a changed form (D132's pause: a fresh read shows it), never the
    page's reaction to answers: nothing reaches the employer."""
    app_id = follow_up_application(api, receiver, "follow_up", single=single)
    if single:
        receiver.config(mode="wd_follow_up_required")
    else:
        receiver.config(wizard="follow_up_required")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert attempt(aid).disclosure_started_at is None
    with SessionLocal() as db:
        pause = db.scalar(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert (pause.kind, pause.status) == ("form_changed", "open")


def test_an_approval_from_before_d148_pauses_and_a_fresh_read_marks_it(api, receiver,
                                                                         monkeypatch):  # fmt: skip
    """An approval given before the follow-up was read as one (simulated: the capture without
    its condition) no longer matches the live form: a pause before anything is entered; reading
    the form again finds the condition, which ends the pause."""
    real = workday.extract_schema

    def before_d148(html):
        schema = real(html)
        for f in schema.fields:
            f.condition = None
        return schema

    monkeypatch.setattr(workday, "extract_schema", before_d148)
    app_id = follow_up_application(api, receiver, "follow_up")
    monkeypatch.undo()
    assert "condition" not in row(api, app_id)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        pause = db.scalar(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert pause.status not in ("open", "unexplained")
    assert row(api, app_id)["condition"] == UNKNOWN


# ---------------------------------------------------------------------------- the single page


def test_single_page_shown_it_is_entered_and_sent(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required", single=True,
                                   detail="Friday")  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][FOLLOW_UP] == "Friday"


def test_single_page_not_shown_it_is_never_waited_for(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required", single=True,
                                   shift="Days", detail="Friday")  # fmt: skip
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["acceptances"][0]["fields"][FOLLOW_UP] == ""


def test_single_page_shown_required_and_unanswered_pauses_for_your_answer(api, receiver):
    app_id = follow_up_application(api, receiver, "follow_up_revealed_required", single=True)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert posts(led, "/apply") == 0 and led["accepted"] == 0
    with SessionLocal() as db:
        pause = db.scalar(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert (pause.kind, pause.status, pause.detail) == (
            "conditional_required", "open", {"required": 1})  # fmt: skip
    att = attempt(aid)
    assert att.disclosure_started_at is not None and att.send_started_at is None
    assert FOLLOW_UP not in att.outcome_detail
    assert row(api, app_id)["status"] == "needs_user"  # asked while the pause is open


# ---------------------------------------------------------------------------- after filling

PAGE = """<!doctype html><html><body>
<form id="workday-application" action="http://fixture.test/apply" method="post">
<section data-step="Application Questions">
<label for="d">Which nights?</label><input id="d" name="q.d" type="text"{d}>
<fieldset><legend>Weekends too?</legend>
<label><input type="radio" name="q.w" value="Yes"{w}> Yes</label></fieldset>
</section><button type="submit">Submit</button></form></body></html>"""


def _answer(key, ftype, value, required=False) -> dict:
    return {"key": key, "label": key, "type": ftype, "required": required, "value": value,
            "status": "resolved" if value is not None else "blank_optional", "options": [],
            "step": "Application Questions", "condition": UNKNOWN}  # fmt: skip


def _adapter(answers: list[dict], captured: str) -> WorkdayFixtureAdapter:
    schema = workday.extract_schema(captured)
    dest = {"url": "http://fixture.test/workday/t/R-1000", "submit_url": "http://fixture.test/apply",
            "form_fingerprint": form_fingerprint(schema)}  # fmt: skip
    return WorkdayFixtureAdapter({"answers": answers, "documents": [], "destination": dest}, {})


@pytest.fixture(scope="module")
def _browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield browser
        browser.close()


@pytest.fixture
def page(_browser):
    pg = _browser.new_page()
    yield pg
    pg.close()


HIDDEN = PAGE.format(d=" hidden", w=" hidden")
TEXT = _answer("q.d", "text", {"text": "Friday"})


AFTER_FILLING = [
    ("entered, then hidden", " hidden", " hidden", [TEXT], {"q.d"}, FOLLOW_UP_CHANGED),
    ("shown, answered, not entered", "", " hidden", [TEXT], set(), FOLLOW_UP_CHANGED),
    (
        "shown, required, unanswered",
        " required",
        " hidden",
        [_answer("q.d", "text", None)],
        set(),
        ConditionalRequired(1),
    ),
    (
        "shown required choice",
        " hidden",
        " required",
        [_answer("q.w", "radio", None)],
        set(),
        FOLLOW_UP_NOT_FILLED,
    ),
    ("shown, optional, unanswered", "", " hidden", [_answer("q.d", "text", None)], set(), None),
    ("hidden, not entered", " hidden", " hidden", [TEXT], set(), None),
    (
        "hidden, required, not entered",
        " hidden required",
        " hidden",
        [_answer("q.d", "text", None)],
        set(),
        FOLLOW_UP_HIDDEN_REQUIRED,
    ),
    ("shown and entered", "", " hidden", [TEXT], {"q.d"}, None),
]


@pytest.mark.parametrize("case, d, w, answers, entered, expected", AFTER_FILLING,
                         ids=[c[0] for c in AFTER_FILLING])  # fmt: skip
def test_after_filling_what_the_page_shows_is_what_was_entered(page, case, d, w, answers,
                                                                entered, expected):  # fmt: skip
    page.set_content(PAGE.format(d=d, w=w))
    adapter = _adapter(answers, HIDDEN)
    adapter._entered = set(entered)
    got = adapter.follow_ups(page, adapter.content["answers"])
    assert got == expected, case
    if isinstance(expected, ConditionalRequired):
        assert got.count == expected.count


def test_before_filling_a_shown_one_is_left_to_the_fill(page):
    """At open nothing is entered yet: a follow-up the page already shows is entered by the fill,
    not a finding. Once filled, the same page is one."""
    page.set_content(PAGE.format(d="", w=" hidden"))
    adapter = _adapter([TEXT, _answer("q.w", "radio", None)], HIDDEN)  # every question read
    assert adapter.schema_matches(page) is None
    adapter._filled = True
    assert adapter.schema_matches(page) == FOLLOW_UP_CHANGED


def test_a_question_the_page_hides_once_answers_were_entered_is_its_reaction(page):
    """Visible when approved, hidden now: before anything is entered, the form has changed (a
    fresh read shows it, D132); once answers were entered, it is the page's reaction to them."""
    shown = PAGE.format(d="", w="")
    plain = [{**_answer("q.d", "text", None), "condition": None},
             {**_answer("q.w", "radio", None), "condition": None}]  # fmt: skip
    adapter = _adapter(plain, shown)
    page.set_content(PAGE.format(d=" hidden", w=""))
    assert adapter.schema_matches(page)  # before filling: the form has changed
    adapter._filled = True
    assert adapter.schema_matches(page) is None


def test_the_live_form_reads_as_approved_shown_or_hidden_and_once_filled_required_or_not(page):
    adapter = _adapter([TEXT, _answer("q.w", "radio", None)], HIDDEN)
    page.set_content(PAGE.format(d="", w=""))
    assert adapter.schema_matches(page) is None  # shown now, hidden when approved
    page.set_content(PAGE.format(d=" required", w=""))
    assert isinstance(adapter.schema_matches(page), FormChanged)  # required before entry
    adapter._filled, adapter._entered = True, {"q.d"}
    assert adapter.schema_matches(page) is None  # once filled, the page's reaction
    page.set_content(PAGE.format(d=" hidden", w=" hidden").replace("Which nights?", "Which days?"))
    assert adapter.schema_matches(page) is not None  # its wording still has to match


def test_readback_never_waits_for_a_question_the_page_removed(page):
    page.set_content(
        PAGE.format(d=" hidden", w=" hidden").replace(
            '<label for="d">Which nights?</label><input id="d" name="q.d" type="text" hidden>', ""
        )
    )
    adapter = _adapter([TEXT], HIDDEN)
    started = time.monotonic()
    assert adapter.readback(page) == []  # not entered: nothing to read
    adapter._entered = {"q.d"}
    assert adapter.readback(page) == ["q.d"]  # entered: it did not keep its value
    assert time.monotonic() - started < 5  # never waited for (a wait lasts 30 s here)


def test_an_approved_answer_to_a_choice_the_page_shows_by_itself_is_refused(page):
    """As D135: a choice the page shows by its own logic is never filled; an approved value for
    one (which nothing can approve today) is refused before anything is entered."""
    page.set_content(HIDDEN)
    adapter = _adapter([TEXT, _answer("q.w", "radio", {"option": "Yes"})], HIDDEN)
    assert adapter.schema_matches(page) == UNSEEN_LOGIC
    adapter = _adapter([TEXT, _answer("q.w", "radio", None)], HIDDEN)
    assert adapter.schema_matches(page) is None
