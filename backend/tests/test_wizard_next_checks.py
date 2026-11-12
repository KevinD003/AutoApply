"""D156: before each Workday-style wizard page's Next, what D154 reads before the final click.
After the page's answers have settled its Next is waited for (shown and enabled), before the
readback; right before the gate for the Next, what the page itself would refuse at that click is
read without acting on it (D154's one read of the button's form: for a script's button, as the
stand-in's, only the page's own marks on fields shown, never on the one that has focus). Either
stops the attempt with that page never sent.

Through the runner against the Workday-style stand-in's wizard (FIXTURE ASSUMPTIONS FA1-FA8 in
fixtures/ats_receiver/workday_like.py, cfg page_check), never a real page: the receiver's own
ledger is the oracle for what reached the employer (its draft rows, acceptances and the POSTs it
logged). The last cases drive the two checks on pages set in Chromium (synthetic markup only).

Before D156: a page whose script marks a field was sent with Next, and the attempt was stopped
only before the final click, every page saved at the employer as a draft; a Next the page
refused by its own script was clicked (the page "showed an error"); a Next it kept disabled was
waited for until the navigation time limit and recorded as a click the page "did not answer"."""

import pytest

from app.modules.execution import runner, stopping
from app.modules.execution.adapters import fixture_ats as fa
from app.modules.execution.adapters import workday as wd
from app.modules.execution.adapters.workday import WorkdayFixtureAdapter
from tests.execution_harness import Receiver, attempt, queue
from tests.test_workday_wizard import (
    all_retired_for_wizard,
    draft_pages,
    posts,
    rows,
    steps,
    wizard_application,
)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def checked(api, receiver, check: str) -> tuple[str, str, str]:
    """The plain wizard with this page check, captured, answered, approved and run."""
    receiver.config(page_check=check)
    app_id = wizard_application(api, receiver, "plain")
    aid = queue(api, app_id)
    return runner.run_attempt(aid, "w1"), aid, app_id


def sent_with_next(aid: str) -> list[dict]:
    """NoEfforts' own record of each Next it clicked (never the oracle for what was sent)."""
    return [d for d in rows(aid, "disclosure") if d.get("kind") == "draft_page"]


def nothing_sent(led) -> bool:
    return not draft_pages(led) and posts(led, "/apply") == 0 and led["accepted"] == 0


# ---------------------------------------------------------------------------- through the runner


def test_a_field_the_page_marks_stops_the_wizard_before_that_pages_next(api, receiver):
    """The page's script marks page 1's phone (written with spaces) as not valid, but its Next,
    a script's button, sends the page all the same: before D156 every page was saved at the
    employer, then the final click was found refused (D154). Now page 1 is never sent."""
    out, aid, app_id = checked(api, receiver, "custom_error")
    assert out == "abandoned"
    led = receiver.ledger()
    assert nothing_sent(led) and posts(led, "/apply/draft/1") == 0
    detail = attempt(aid).outcome_detail
    assert wd.NEXT_WOULD_REFUSE in detail and "1 field(s) it marks as not valid" in detail
    assert fa.PAGE_WOULD_REFUSE not in detail  # not the final click's
    assert "up to 0 page(s) were sent there with Next" in detail
    assert "phone" not in detail.lower() and "555" not in detail  # counts only
    assert steps(aid) == [] and sent_with_next(aid) == []  # no gate for it, no click
    assert all_retired_for_wizard(app_id)


def test_a_next_the_page_refuses_while_a_field_is_marked_is_never_clicked(api, receiver):
    """The page marks the phone `aria-invalid` and its own Next refuses while a field of its
    page is marked (nothing sent either way): before D156 the Next was clicked and the page
    "showed an error"; now it is never clicked."""
    out, aid, app_id = checked(api, receiver, "next_aria")
    assert out == "abandoned"
    assert nothing_sent(receiver.ledger())
    detail = attempt(aid).outcome_detail
    assert wd.NEXT_WOULD_REFUSE in detail and "1 field(s) it marks as not valid" in detail
    assert runner.NEXT_NOT_SAVED[fa.ACK_ERROR] not in detail
    assert steps(aid) == [] and sent_with_next(aid) == []
    assert all_retired_for_wizard(app_id)


def test_a_next_the_page_keeps_disabled_stops_before_its_gate(api, receiver, monkeypatch):
    """Page 2's Next stays disabled: page 1 was sent, page 2 never is, and its Next is never
    clicked. Before D156 the click waited until the navigation time limit and was recorded as a
    Next the page did not answer ("does not know whether that page was saved")."""
    monkeypatch.setattr(fa, "FINAL_READY_MS", 2000, raising=False)
    out, aid, app_id = checked(api, receiver, "next_disabled")
    assert out == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and posts(led, "/apply/draft/2") == 0
    assert posts(led, "/apply") == 0 and led["accepted"] == 0
    detail = attempt(aid).outcome_detail
    assert wd.NEXT_UNAVAILABLE in detail and "up to 1 page(s) were sent there with Next" in detail
    assert runner.NEXT_NOT_SAVED[fa.ACK_NONE] not in detail
    assert steps(aid) == [(1, "next"), (2, "fill")]  # page 2's Next never authorized
    assert [d["page"] for d in sent_with_next(aid)] == [1]
    assert all_retired_for_wizard(app_id)


def test_a_next_enabled_a_second_after_the_pages_last_answer_is_waited_for(api, receiver):
    out, aid, _ = checked(api, receiver, "next_late_enable")
    assert out == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and led["accepted"] == 1


def test_what_the_page_changes_while_it_keeps_its_next_disabled_is_read_back(api, receiver):
    """Page 1's Next is enabled a second after its last answer, when the page also rewrites a
    field left empty: the Next is waited for before the readback, which so sees the change, and
    page 1 is never sent (with the wait after it, page 1 went with the rewritten field)."""
    out, aid, _ = checked(api, receiver, "next_late_rewrite")
    assert out == "abandoned"
    assert "1 field(s) did not keep their values" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert nothing_sent(led) and posts(led, "/apply/draft/1") == 0
    assert steps(aid) == [] and sent_with_next(aid) == []


def test_a_mark_the_page_would_clear_when_focus_leaves_the_field_is_not_counted(
    api, receiver, monkeypatch
):
    """The page focuses page 1's City at load and marks a field `aria-invalid` when focus leaves
    it empty; a page's Next refuses while a field of its page is marked. City is marked when the
    first answer is typed, then filled last, and keeps focus (so its mark) until the click,
    when the page checks it again and clears it: never counted."""
    seen = []
    read = WorkdayFixtureAdapter.next_would_refuse

    def spy(self, page, i):
        if i == 1:
            seen.append(page.evaluate("""() => {
              const c = document.getElementById('city');
              return [c.getAttribute('aria-invalid'), document.activeElement === c, !!c.value];
            }"""))  # fmt: skip
        return read(self, page, i)

    monkeypatch.setattr(WorkdayFixtureAdapter, "next_would_refuse", spy)
    out, aid, _ = checked(api, receiver, "focus_validation")
    assert seen == [["true", True, True]]  # marked, focused and filled when read
    assert out == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and led["accepted"] == 1


def test_a_value_only_the_browsers_own_validation_refuses_is_left_to_the_final_click(api, receiver):
    """The phone breaks the markup's pattern. The wizard's Next is a script's button, which the
    browser never validates, so the markup's constraints are not counted at a Next (a page
    whose script decides may not apply them, D154); the final click, the browser's own
    validated submission, is refused before the send gate as before."""
    out, aid, _ = checked(api, receiver, "pattern")
    assert out == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and posts(led, "/apply") == 0
    detail = attempt(aid).outcome_detail
    assert fa.PAGE_WOULD_REFUSE in detail and "1 value(s) it does not accept" in detail
    assert wd.NEXT_WOULD_REFUSE not in detail


@pytest.mark.parametrize("stopping_now", [True, False], ids=["worker_stopping", "not_stopping"])
def test_a_next_unreadable_while_the_worker_is_being_stopped_ends_as_the_stop(
    api, receiver, monkeypatch, stopping_now
):
    """D150, as D154's: stopping the worker closes its browser, so the read before a Next can
    fail then; that is the stop's. Otherwise an unreadable page is a refusal (fail closed)."""

    def unread(self, page, i):
        if stopping_now:
            stopping.request()
        return wd.NEXT_REFUSAL_UNREAD

    monkeypatch.setattr(WorkdayFixtureAdapter, "next_would_refuse", unread)
    receiver.config(page_check=None)
    app_id = wizard_application(api, receiver, "plain")
    aid = queue(api, app_id)
    try:
        out = runner.run_attempt(aid, "w1")
    finally:
        stopping.clear()
    assert out == "abandoned" and nothing_sent(receiver.ledger())
    detail = attempt(aid).outcome_detail
    if stopping_now:
        assert runner.STOP_REQUESTED in detail and wd.NEXT_REFUSAL_UNREAD not in detail
    else:
        assert wd.NEXT_REFUSAL_UNREAD in detail and all_retired_for_wizard(app_id)


# ---------------------------------------------------------------------------- on a page


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


NEXT = '<button type="button" data-wizard-next>Save and Continue</button>'


def shim():
    """The Workday adapter's own code for a page's Next (`next_button`, its form selector)."""

    class Shim:
        FORM = WorkdayFixtureAdapter.FORM
        next_button = WorkdayFixtureAdapter.next_button

    return Shim()


def ready(page, i=1):
    return WorkdayFixtureAdapter.next_ready(shim(), page, i)


def read(page, i=1):
    return WorkdayFixtureAdapter.next_would_refuse(shim(), page, i)


def wizard(one: str, two: str = "", *, next1: str = NEXT, attrs: str = "") -> str:
    """Two pages in one form, page 1 shown."""
    return (
        f'<form id="workday-application"{attrs}>'
        f'<section data-wizard-page="1">{one}{next1}</section>'
        f'<section data-wizard-page="2" hidden>{two}{NEXT}</section></form>'
    )


def counts(r) -> dict | None:
    assert r is None or isinstance(r, wd.NextRefusal), r
    return None if r is None else {k: v for k, v in r.counts.items() if v}


def test_the_next_is_its_own_pages_one_button(page):
    page.set_content(wizard('<input name="a" value="x">'))
    assert ready(page, 1) is None and read(page, 1) is None
    page.set_content(wizard("", next1=NEXT + NEXT))  # two on its page
    assert ready(page) == wd.NEXT_UNIDENTIFIED and read(page) == wd.NEXT_UNIDENTIFIED
    page.set_content(wizard("", next1=""))  # none on its page (page 2's is not it)
    assert ready(page) == wd.NEXT_UNIDENTIFIED and read(page) == wd.NEXT_UNIDENTIFIED
    # in the form's markup but owned by no form (`form` naming none): never read as the form's
    owned_by_none = NEXT.replace("data-wizard-next", 'data-wizard-next form="x"')
    page.set_content(wizard("", next1=owned_by_none))
    assert read(page) == wd.NEXT_UNIDENTIFIED


@pytest.mark.parametrize("button", [
    NEXT.replace("<button", "<button disabled"),
    NEXT.replace("<button", '<button aria-disabled="true"'),
    NEXT.replace("<button", "<button hidden"),
], ids=["disabled", "aria_disabled", "hidden"])  # fmt: skip
def test_a_next_hidden_or_disabled_is_unavailable(page, monkeypatch, button):
    monkeypatch.setattr(fa, "FINAL_READY_MS", 300, raising=False)
    page.set_content(wizard('<input name="a" value="x">', next1=button))
    assert ready(page) == wd.NEXT_UNAVAILABLE and read(page) == wd.NEXT_UNAVAILABLE


def test_a_next_the_page_enables_later_is_waited_for(page):
    page.set_content(wizard('<input name="a" value="x">',
                            next1=NEXT.replace("<button", "<button disabled")))  # fmt: skip
    page.evaluate("""() => setTimeout(() => {
      document.querySelector('[data-wizard-next]').disabled = false; }, 700)""")
    assert ready(page) is None


def test_on_a_scripts_next_only_the_pages_marks_on_fields_shown_count(page):
    """A Next of type=button: the browser never validates its click, so required and empty
    fields, and values the markup does not accept, are the page's script's to judge (not
    counted); its own marks (a custom error, `aria-invalid="true"`) are, on fields shown."""
    page.set_content(wizard(
        '<input name="req" required>'
        '<input name="pat" pattern="[0-9]+" value="abc">'
        '<input name="flag" aria-invalid="true" value="x">'
        '<input name="custom" value="x">',
        '<input name="later" aria-invalid="true" required>',  # page 2, not shown
    ))  # fmt: skip
    page.evaluate("() => document.querySelector('[name=custom]').setCustomValidity('No')")
    assert counts(read(page)) == {"marked": 2}
    page.evaluate("""() => {
      document.querySelector('[name=flag]').removeAttribute('aria-invalid');
      document.querySelector('[name=custom]').setCustomValidity(''); }""")
    assert read(page) is None


def test_a_mark_on_the_field_that_has_focus_is_not_counted(page):
    page.set_content(wizard('<input name="a" aria-invalid="true" value="x"><input name="b">'))
    page.focus("[name=a]")
    assert read(page) is None
    page.focus("[name=b]")
    assert counts(read(page)) == {"marked": 1}


def test_a_next_that_is_the_browsers_validated_submission_counts_every_page(page):
    """A Next of type=submit in a form the browser validates: every control it would refuse
    counts, the pages not shown included (the browser refuses the click for them too); with
    `formnovalidate`, only the page's own marks, as a script's button."""
    submit = NEXT.replace('type="button"', 'type="submit"')
    page.set_content(wizard('<input name="a" value="x">', '<input name="later" required>',
                            next1=submit))  # fmt: skip
    assert counts(read(page)) == {"required": 1}
    page.set_content(wizard('<input name="a" value="x">', '<input name="later" required>',
                            next1=submit.replace("<button", "<button formnovalidate")))  # fmt: skip
    assert read(page) is None
    page.set_content(wizard('<input name="a" value="x">', '<input name="later" required>',
                            next1=submit, attrs=" novalidate"))  # fmt: skip
    assert read(page) is None


def test_the_read_is_passive_and_names_counts_only(page):
    page.set_content(wizard('<input name="phone" value="555 0100" aria-invalid="true">'))
    page.evaluate("""() => {
      window.fired = 0;
      document.addEventListener('invalid', () => { window.fired++; }, true);
      document.addEventListener('focusin', () => { window.fired++; }, true); }""")
    r = read(page)
    assert counts(r) == {"marked": 1} and page.evaluate("window.fired") == 0
    assert str(r).startswith(wd.NEXT_WOULD_REFUSE) and "555" not in r and "phone" not in r
    # the final click's own refusal keeps its own words (D154)
    assert str(fa.PageRefusal(marked=1)).startswith(fa.PAGE_WOULD_REFUSE)
