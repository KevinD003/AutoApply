"""Explicit dropdown strategies of the id-mapping adapter (adapters/dropdowns.py), against the
fixture's dropdown behaviours (`gh2_dd`, `_DD_JS`). Every behaviour is a FIXTURE ASSUMPTION:
run #9 saw no opening evidence on the real page, so none of these is known to match it. A
passing test here says the adapter handles that assumed behaviour safely, not that any real
form can be filled or submitted. The receiver's ledger is the oracle for what was sent."""

import http.server
import threading
import time

import pytest

from app.core.config import get_settings
from app.modules.execution import runner
from app.modules.execution.adapters import dropdowns
from app.modules.execution.adapters import greenhouse_dom as gd_adapter
from app.modules.execution.browser import browser_session
from app.modules.preparation import gh_readonly as ro
from app.modules.preparation import greenhouse_dom as dom
from tests.conftest import CANARY_PORT
from tests.execution_harness import BASE, Receiver, attempt, queue, synthetic_candidate
from tests.test_greenhouse_dom import BOARD, JOB, v2_application, v2_job


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def package(api, app_id):
    return api.get(f"/applications/{app_id}/package").json()["package"]["content"]


def run(api, receiver, mode="gh2_dd", **cfg):
    receiver.config(mode=mode, **cfg)
    app_id = v2_application(api)
    aid = queue(api, app_id)
    return app_id, aid, runner.run_attempt(aid, "w1")


@pytest.mark.parametrize(
    "dd,cfg",
    [
        ("click_popup", {}),
        ("type_filter", {}),  # typing would filter; the adapter never types
        ("arrow_down", {}),
        ("trigger_button", {}),
        ("locale_gate", {}),  # opens once a locale file has loaded at page load
        # ... and when that file is slow, as on a busy CI runner (CI #133 failed this way)
        ("locale_gate", {"locale_delay_ms": 2500}),
        ("delayed", {"delay_ms": 300}),
        ("preselect_first", {}),  # the highlighted first option is not what was approved
        # D104 (local stand-ins only): a list that arrives late, within dropdowns.LATE_MS, once
        # nothing loads any more and it has stayed the same: after a delay, after a locale file
        # from the page's own origin, or from a same-origin GET of its own options.
        ("delayed", {"delay_ms": 2500}),
        ("locale_on_open", {}),
        ("late_fetch", {"delay_ms": 1200}),
        # D109: react-select-like markup where only the `select__control` container opens it
        ("container_only", {}),
        # D109: react-select-like markup; the choice is read back from the single-value element
        # (the input keeps only search text), as react-select shows it
        ("react_select", {}),
        # D110: run #11's observed behaviour: react-select markup at load, usable once the page's
        # locale file has loaded (here from the page's own origin, as a local stand-in)
        ("react_locale", {}),
    ],
)
def test_each_strategy_selects_exactly_the_approved_option(api, receiver, dd, cfg):
    app_id, aid, result = run(api, receiver, dd=dd, **cfg)
    assert result == "confirmed", attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    answers = {a["key"]: a["value"] for a in package(api, app_id)["answers"]}
    for key in ("question_8101", "question_8102", "question_8104"):
        assert sent[key] == answers[key]["option"], key
    assert sent["question_8104"] == "0"  # "No": the second option, never the first by default


def test_a_form_still_loading_after_the_allowance_stops_before_anything_is_entered(
    api, receiver, monkeypatch
):
    """The locale file never arrives within the allowance: the runner stops safely instead of
    using a page whose controls may not respond yet. Nothing is typed, disclosed or sent."""
    monkeypatch.setattr(runner, "SETTLE_LOAD_MS", 1000)
    receiver.config(mode="gh2_dd", dd="locale_gate")
    app_id = v2_application(api)
    receiver.config(locale_delay_ms=30000)
    before = len(receiver.ledger()["requests"])
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert runner.NOT_READY in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # The form and its locale file, each requested once: nothing was repeated while it waited.
    paths = [r["path"] for r in led["requests"][before:]]
    assert paths.count("/locales/en/common.json") == 1, paths
    assert all(r["method"] == "GET" for r in led["requests"][before:])


@pytest.mark.parametrize(
    "dd,cfg,reason",
    [
        ("inert", {}, "no supported action opened it"),
        ("type_only", {}, "no supported action opened it"),  # never types into a dropdown
        ("two_triggers", {}, "several elements could open it"),
        # D104: still loading when the bounded wait ends (dropdowns.LATE_MS), never accepted.
        ("delayed", {"delay_ms": 7000}, "its list could not be read completely"),
        # D104: lists that arrive late are refused unless they settle as exactly the approved
        # one: a different list, one still loading at the deadline, one that keeps changing, a
        # partial one, and one requested in a way that is not a same-origin GET.
        ("late_differ", {}, "its options differ from the approved ones"),
        ("late_never", {}, "its list could not be read completely"),
        ("late_changing", {}, "its list could not be read completely"),
        ("late_slow_changing", {}, "its list could not be read completely"),
        ("late_partial", {"delay_ms": 200}, "its list could not be read completely"),
        ("late_post", {}, "its options load from the network in a way NoEfforts does not accept"),
        ("virtualized", {}, "its list could not be read completely"),  # never scrolled
        ("duplicate_option", {}, "its list shows an option more than once"),
    ],
)
def test_unverifiable_dropdowns_stop_before_anything_is_disclosed(api, receiver, dd, cfg, reason):
    _, aid, result = run(api, receiver, dd=dd, **cfg)
    assert result == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "dropdown" in detail and reason in detail, detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


# D145: how often the list is read must not decide whether it counts as settled. The stand-in's
# `late_slow_changing` list is re-rendered every 300 ms, in alternating order. Read about every
# 600 ms (a busy machine stretches the interval that far), every read used to see the same
# order: at 590 ms it was refused for the wrong reason (judged settled, in the other order), and
# at 610 ms it was accepted. 1200 ms: four re-renders between reads. Which of the two words
# the refusal carries depends on the moment of the last read; both say the list is not settled.
@pytest.mark.parametrize("sample_ms", [590, 600, 610, 1200])
def test_a_list_that_keeps_changing_is_refused_however_slowly_it_is_read(
    api, receiver, monkeypatch, sample_ms
):
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", sample_ms)
    _, aid, result = run(api, receiver, dd="late_slow_changing")
    assert result == "failed_safe", attempt(aid).outcome_detail
    detail = attempt(aid).outcome_detail
    assert "dropdown: its list could not be read completely" in detail, detail
    assert "still_changing" in detail or "list_changed_recently" in detail, detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def _approved_options_sent(api, receiver, app_id) -> None:
    led = receiver.ledger()
    assert led["accepted"] == 1
    sent = led["acceptances"][0]["fields"]
    answers = {a["key"]: a["value"] for a in package(api, app_id)["answers"]}
    for key in ("question_8101", "question_8102", "question_8104"):
        assert sent[key] == answers[key]["option"], key


@pytest.mark.parametrize("dd,cfg", [("click_popup", {}), ("late_fetch", {"delay_ms": 1200})])
def test_a_list_that_has_settled_is_accepted_when_read_slowly(api, receiver, monkeypatch, dd, cfg):
    """D145: the other side. A slow reader still accepts a list that does not change: at once,
    or once it has arrived and stayed the same."""
    monkeypatch.setattr(dropdowns, "SAMPLE_MS", 600)
    app_id, aid, result = run(api, receiver, dd=dd, **cfg)
    assert result == "confirmed", attempt(aid).outcome_detail
    _approved_options_sent(api, receiver, app_id)


@pytest.mark.parametrize("tick_ms", [300, 600])
def test_a_page_that_keeps_changing_elsewhere_does_not_hold_up_a_settled_list(
    api, receiver, tick_ms
):
    """D145: the page's record of changes to a list does not count changes elsewhere. Something
    else on the page changes every 300 ms, or every 600 ms: in a stand-in's window each
    dropdown's list is still read as settled, at the check and at the choice, and the
    application is submitted with the approved options. (On the whole document's record the
    300 ms page would never settle. Since D153 the classification's own check of the whole
    document, no change for 150 ms, is left out by the adapter too: see the tests below in a
    real page's window.)"""
    app_id, aid, result = run(api, receiver, dd="click_popup", dd_tick_ms=tick_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    _approved_options_sent(api, receiver, app_id)


def test_a_page_busy_elsewhere_passes_every_check_in_a_real_pages_window(
    api, receiver, monkeypatch
):
    """D145 was first built on the whole document's record. With something else changing every
    600 ms, an opening then settled only if its moment was right: 64% of them within the 1.5
    seconds a real page gets (the review's arithmetic), so a check could pass and the choice
    fail after data had been entered. A stand-in's own window (5 seconds) hides that, so this
    one is given a real page's: the three checks and the three choices all pass, and the
    application is submitted with the approved options."""
    monkeypatch.setattr(dropdowns, "LATE_MS", dropdowns.SETTLE_MS)
    app_id, aid, result = run(api, receiver, dd="click_popup", dd_tick_ms=600)
    assert result == "confirmed", attempt(aid).outcome_detail
    _approved_options_sent(api, receiver, app_id)


@pytest.mark.parametrize("tick_ms", [100, 250, 300])
def test_a_page_busy_elsewhere_has_its_lists_settle_in_a_real_pages_window(
    api, receiver, monkeypatch, tick_ms
):
    """D153 (rank 19): until D153 a read within 150 ms of any change on the page could not settle
    (the classification's check of the whole document, D106), so a page changing something
    every 250 to 300 ms had a list refused in a real page's window depending on the reading
    pace, and one changing every 100 ms had every list refused. The adapter judges the list by
    the page's record of changes to a list instead: the checks and the choices pass, and the
    application is submitted with the approved options."""
    monkeypatch.setattr(dropdowns, "LATE_MS", dropdowns.SETTLE_MS)
    app_id, aid, result = run(api, receiver, dd="click_popup", dd_tick_ms=tick_ms)
    assert result == "confirmed", attempt(aid).outcome_detail
    _approved_options_sent(api, receiver, app_id)


def test_a_page_whose_style_sheet_keeps_changing_has_its_lists_refused(api, receiver):
    """D153: a change to a style sheet counts as a change to a list, since a style sheet can hide,
    show or reorder options without touching the list (the whole document's check used to see
    such a change within 150 ms of a read). A page that changes one every 300 ms, here a rule
    that matches nothing, never has a list settle: refused before anything is entered."""
    _, aid, result = run(api, receiver, dd="click_popup", dd_style_tick_ms=300)
    assert result == "failed_safe", attempt(aid).outcome_detail
    detail = attempt(aid).outcome_detail
    assert "dropdown: its list could not be read completely" in detail, detail
    assert "list_changed_recently" in detail, detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_a_list_that_starts_changing_after_the_check_stops_the_attempt_before_sending(
    api, receiver
):
    """D145: each list is stable when it is checked, before anything is entered, and keeps
    being re-rendered from its second opening, which is the choice. The choice is not made (its
    list never settles), the readback finds the dropdowns unanswered, and the attempt stops
    after data was entered and before the send gate. Nothing is submitted."""
    _, aid, result = run(api, receiver, dd="changing_on_reopen")
    assert result == "abandoned", attempt(aid).outcome_detail
    assert "did not keep their values" in attempt(aid).outcome_detail
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] != []


def test_the_pages_record_tells_a_change_to_a_list_from_a_change_elsewhere(receiver):
    """D145, the observer itself, in a real browser on the stand-in page with one list open:
    what it takes for a change to a list (and so holds a list back from counting as settled),
    and what it does not."""
    receiver.config(mode="gh2_dd", dd="click_popup")
    cid = "question_8101"
    with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                         allow_private_destination=True) as (page, _log):  # fmt: skip
        page.goto(f"{BASE}/gh2/{BOARD}/jobs/{JOB}")
        page.locator(f'[id="{cid}"]').click()
        assert page.evaluate(ro._PROBE_JS, cid)["texts"], "the list did not open"

        def touched(js: str) -> bool:
            assert page.evaluate(ro._PRE_JS, cid) is not None  # a fresh record
            page.evaluate(js)
            return page.evaluate(ro._PROBE_JS, cid)["list_quiet_ms"] is not None

        note = "document.getElementById('fx-note')"
        option, listbox = "document.querySelector('[role=option]')", "[role=listbox]"
        # Elsewhere on the page: an element arrives, its text changes, an attribute of it.
        assert not touched("const n = document.createElement('p'); n.id = 'fx-note';"
                           " n.textContent = 'a'; document.body.append(n)")  # fmt: skip
        assert not touched(f"{note}.textContent = 'b'")
        assert not touched(f"{note}.setAttribute('data-x', '1')")
        # A list: text inside an option, an attribute of one, a child of the list, an attribute
        # of an element holding it, an element holding an option arriving, the list going.
        assert touched(f"{option}.firstChild.data += '!'")
        assert touched(f"{option}.setAttribute('data-x', '1')")
        assert touched(f"document.querySelector('{listbox}').append(document.createElement('li'))")
        assert touched("document.body.toggleAttribute('data-x')")
        holder = "const u = document.createElement('div'); u.innerHTML = '<i role=option>x</i>';"
        assert touched(holder + " document.body.append(u)")
        assert touched(f"document.querySelector('{listbox}').remove()")
        # More changes at once than are looked at one by one: taken for the list's.
        assert touched(f"for (let i = 0; i < 250; i++) {note}.setAttribute('data-n', String(i))")


class _ProbePage:
    """The probe's answers without a browser: closed before the action, then the open list at
    each read, with the page's record of the last change to a list (`list_quiet`), of the last
    change anywhere (`quiet`) and the option texts read."""

    def __init__(self, list_quiet, *, quiet=None, texts=None):
        self.list_quiet, self.quiet, self.texts, self.reads = list(list_quiet), quiet, texts, -1

    def evaluate(self, script, arg=None):
        if script is ro._PRE_JS:
            return {}
        self.reads += 1
        if self.reads == 0:
            return _probe(None, is_open=False)
        i = self.reads - 1  # past the end of either list, its last entry goes on
        texts = self.texts[min(i, len(self.texts) - 1)] if self.texts else ["Yes", "No"]
        list_quiet = self.list_quiet[min(i, len(self.list_quiet) - 1)]
        return _probe(list_quiet, quiet_ms=self.quiet, texts=texts)

    def wait_for_timeout(self, ms): ...
    def on(self, *a): ...
    def remove_listener(self, *a): ...


def _probe(list_quiet_ms, *, quiet_ms=None, texts=("Yes", "No"), is_open: bool = True) -> dict:
    """What the page probe returns: a closed control, or its open list with nothing loading."""
    whole = list_quiet_ms if quiet_ms is None else quiet_ms
    return {
        "expanded": "true" if is_open else "false", "wrapper_expanded": "absent",
        "associated_visible": int(is_open), "new_popups": int(is_open),
        "texts": list(texts) if is_open else [], "elsewhere": 0, "hint_popups": 0,
        "hint_options": 0, "added_visible": 2 * is_open, "busy": 0, "hint_loading": 0,
        "setsize": None, "quiet_ms": whole, "list_quiet_ms": list_quiet_ms, "mutations": 0,
    }  # fmt: skip


def test_settled_means_unchanged_by_the_pages_own_record(monkeypatch):
    """D145, the rule itself, on a stand-in for the page's probe: three equal reads are not
    enough while the page reports a change to a list in the last half second, whatever the
    reading interval; they are once it reports none for that long, or none at all since before
    the action. A change elsewhere on the page, however recent the classification allows, does
    not count."""
    monkeypatch.setattr(dropdowns, "_act", lambda *a: True)
    for list_quiet, quiet, state, word in (
        ([200, 120, 280, 90, 260, 140], None, "partially_observed", None),  # re-rendered
        ([10, 260, 499, 499, 499, 499], None, "partially_observed", "list_changed_recently"),
        ([10, 260, 500], None, "observed_sufficiently", None),  # exactly the half second
        ([None, None, None], None, "observed_sufficiently", None),  # no change to a list
        ([600, 850, 1100], 200, "observed_sufficiently", None),  # the page is busy elsewhere
    ):
        got = dropdowns._observe(_ProbePage(list_quiet, quiet=quiet), "c", "click_control", 2)
        assert got["state"] == state, (list_quiet, got)
        if word:
            assert got["partial"][-1] == word, got


def test_three_equal_reads_are_still_needed(monkeypatch):
    """The older half of the rule (D106), which the page's record does not replace: with no
    change to a list recorded at all, a list is settled at its third equal read and not before,
    and one whose reads differ in turn is never settled."""
    monkeypatch.setattr(dropdowns, "_act", lambda *a: True)
    page = _ProbePage([None])
    assert dropdowns._observe(page, "c", "click_control", 2)["state"] == "observed_sufficiently"
    assert page.reads == dropdowns.STABLE_SAMPLES == 3
    in_turn = _ProbePage([None], texts=[["Yes", "No"], ["No", "Yes"]] * 3)
    got = dropdowns._observe(in_turn, "c", "click_control", 2)
    assert got["state"] == "partially_observed", got
    assert got["partial"][-1] == "still_changing_or_loading", got
    assert in_turn.reads == dropdowns.SETTLE_MS // dropdowns.SAMPLE_MS


def test_a_control_that_is_gone_before_the_action_is_refused():
    """Without the control the probe installs no observer, and whatever an earlier dropdown
    left recorded would be read as this one's."""

    class Gone:
        def evaluate(self, script, arg=None):
            return None

    with pytest.raises(dropdowns.Refused, match="the control disappeared"):
        dropdowns._observe(Gone(), "c", "click_control", 2)


def test_a_control_absent_only_when_the_observer_is_installed_is_refused():
    """The narrower race (D145 review): the control is absent at the instant the observer is
    installed and back for every read after it. The reads would then see an earlier dropdown's
    record, old and quiet, and take the list as settled; the control is refused instead."""

    class Flickers(_ProbePage):
        def evaluate(self, script, arg=None):
            return None if script is ro._PRE_JS else super().evaluate(script, arg)

    with pytest.raises(dropdowns.Refused, match="the control disappeared"):
        dropdowns._observe(Flickers([5000]), "c", "click_control", 2)


class _Canary(http.server.BaseHTTPRequestHandler):
    """An independent listener on another origin: anything that reaches it is recorded."""

    hits: list[tuple[str, str]] = []

    def do_GET(self):  # noqa: N802
        _Canary.hits.append((self.command, self.path))
        self.send_response(204)
        self.end_headers()

    do_POST = do_PUT = do_OPTIONS = do_GET

    def log_message(self, *a):
        pass


@pytest.fixture
def canary():
    _Canary.hits = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", CANARY_PORT), _Canary)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield _Canary.hits
    srv.shutdown()
    srv.server_close()


@pytest.mark.parametrize("via", ["fetch", "sendbeacon"])
@pytest.mark.parametrize("stand_in", [True, False], ids=["stand_in", "real_destination"])
def test_a_dropdown_that_posts_to_another_origin_when_opened_stops_the_attempt(
    api, receiver, canary, monkeypatch, via, stand_in
):
    """D108 (run #10 saw a real page POST to another host when a dropdown was clicked): opening
    a synthetic dropdown also POSTs to another origin, by fetch() or navigator.sendBeacon, while
    its list opens normally. The POST never arrives (an independent listener on that origin
    records nothing), the attempt stops at the dropdown check, and nothing is filled, uploaded
    or submitted afterwards (the receiver saw only GETs)."""
    if not stand_in:  # as on a real board, where no origin is a fixture
        monkeypatch.setattr(gd_adapter, "stand_ins", lambda content: False)
    _, aid, result = run(api, receiver, dd="open_beacon", beacon_via=via,
                         beacon=f"http://127.0.0.1:{CANARY_PORT}/beacon")  # fmt: skip
    assert result == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "dropdown" in detail and "its options load from the network" in detail, detail
    time.sleep(0.5)  # anything in flight would have arrived by now
    assert canary == [], canary
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert {r["method"] for r in led["requests"]} == {"GET"}, led["requests"]


def test_the_beacon_dropdown_is_otherwise_an_ordinary_one(api, receiver, canary):
    """The control for the test above: without a beacon address the same dropdown is verified
    and the application goes through, so the stop above comes from the POST alone."""
    _, aid, result = run(api, receiver, dd="open_beacon", beacon="")  # (config persists)
    assert result == "confirmed", attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 1 and canary == []


def _controls(*pairs):
    return {"ids": [i for i, _ in pairs], "values": [v for _, v in pairs]}


def test_the_adapter_names_what_an_opening_changed_and_refuses_each():
    """D108: a control added or removed is refused as such, never reported as a value change."""
    before = _controls(("a", "1"), ("b", "2"))
    assert dropdowns._changed(before, before, "opening it") is None
    assert dropdowns._changed(before, _controls(("a", "9"), ("b", "2")),
                              "opening it") == "opening it changed a value"  # fmt: skip
    assert dropdowns._changed(before, _controls(("a", "1"), ("b", "2"), ("h", "")),
                              "opening it") == "opening it added or removed a control"  # fmt: skip
    assert dropdowns._changed(before, _controls(("a", "1")), "an attempt to open it") == (
        "an attempt to open it added or removed a control"
    )
    assert dropdowns._changed(_controls(("", "x")), _controls(("", "y")), "opening it") == (
        "opening it changed a control that cannot be identified"
    )


def test_react_select_markup_whose_locale_file_never_arrives_stops_before_disclosure(api, receiver):
    """D110: run #11's model with the locale file refused (as the pilot refuses it today): the
    react-select controls are there but nothing opens, and the attempt stops before anything is
    entered or sent. (The receiver's settings persist across tests: restored afterwards.)"""
    try:
        _, aid, result = run(api, receiver, dd="react_locale",
                             locale_path="/locales/missing/common.json")  # fmt: skip
    finally:
        receiver.config(locale_path=None)
    assert result == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "dropdown" in detail and "no supported action opened it" in detail, detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


@pytest.mark.parametrize("dd", ["ignores_choice", "wrong_value"])
def test_a_choice_that_does_not_read_back_is_never_submitted(api, receiver, dd):
    _, aid, result = run(api, receiver, dd=dd)
    assert result == "abandoned"
    assert "did not keep their values" in attempt(aid).outcome_detail
    assert receiver.ledger()["accepted"] == 0


def test_unlisted_dropdowns_are_a_checkpoint_from_capture(api, receiver):
    """A phone-country selector inside the phone group and a required dropdown the job data does
    not list: captured as blocking fields whose meaning is never inferred, so the route is a
    checkpoint and the package cannot be approved before anything is queued or disclosed."""
    receiver.config(mode="gh2_dd_extras", dd="click_popup")
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    fields = api.get(f"/jobs/{job_id}/form").json()["schema"]["fields"]
    unlisted = [f for f in fields if f.get("unsupported_reason") == dom.UNLISTED_REASON]
    assert len(unlisted) == 2 and all(f["type"] == "unsupported" and f["required"]
                                      for f in unlisted)  # fmt: skip
    r = api.get(f"/jobs/{job_id}/route").json()
    assert (r["route"], r["reason"]) == ("checkpoint", "unsupported_required_control")
    assert "2 required controls NoEfforts cannot fill" in r["message"]
    assert "extra-1" not in r["message"] and "phone-country" not in r["message"]
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert {f["key"] for f in unlisted} <= set(p["content"]["unresolved"])  # never guessed
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code != 200
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure(api, receiver):
    """Captured and approved without them; the page then shows the same two dropdowns: counted,
    never named, and the attempt stops before anything is disclosed."""
    receiver.config(mode="gh2_dd", dd="click_popup")
    app_id = v2_application(api)
    receiver.config(mode="gh2_dd_extras", dd="click_popup")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert "2 new field(s)" in detail  # both unlisted dropdowns, counted, never named
    assert "extra-1" not in detail and "phone-country" not in detail
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_capabilities_stay_fixture_only_and_real_destinations_refused():
    from app.modules.execution import policy
    from app.modules.execution.adapters import dropdowns

    assert set(dropdowns.STRATEGIES) == {"click_control", "click_container", "arrow_down",
                                         "trigger_button"}  # fmt: skip
    assert all(dropdowns.CAPABILITIES[s] == "fixture_only" for s in dropdowns.STRATEGIES)
    assert dropdowns.CAPABILITIES["options_loaded_from_network"].startswith("checkpoint")
    assert policy.CAPABILITIES["greenhouse_dom"]["real_destinations"] is False


# ------------------------------------------------------------------ D111: options from another host
# After run #11's `u3`: a required dropdown opened, no option appeared, and a data request to
# another Greenhouse host was refused during that action. What the request was for is not
# known; nothing here assumes it. The rule stays: no host or endpoint is allowed because a
# widget asks for it, and a dropdown whose list needs one is never verified.

OTHER = f"http://127.0.0.1:{CANARY_PORT}"


@pytest.mark.parametrize("stand_in", [True, False], ids=["stand_in", "as_on_a_real_board"])
def test_a_list_that_needs_another_host_stops_before_disclosure_and_the_host_never_hears(
    api, receiver, canary, monkeypatch, stand_in
):
    """Mapped dropdowns whose options come from another host: the request is refused before
    sending (an independent listener receives nothing), the list is never verified, and the
    attempt stops before anything is entered."""
    if not stand_in:  # as on a real board, where no origin is a fixture
        monkeypatch.setattr(gd_adapter, "stand_ins", lambda content: False)
    try:
        _, aid, result = run(api, receiver, dd="late_other_host", other_origin=OTHER,
                             delay_ms=0)  # fmt: skip
    finally:
        receiver.config(other_origin="")  # the receiver keeps cfg between tests
    assert result == "failed_safe", attempt(aid).outcome_detail
    detail = attempt(aid).outcome_detail
    assert "dropdown: its options load from the network" in detail, detail
    time.sleep(0.5)  # anything in flight would have arrived by now
    assert canary == [], canary
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_a_required_unlisted_dropdown_that_needs_another_host_is_a_checkpoint(
    api, receiver, canary
):
    """The `u3` shape itself: a required dropdown the job data does not list. Capture makes it a
    blocking checkpoint (what it asks is never inferred), so nothing can be approved, and
    no request reaches the other host."""
    receiver.config(mode="gh2_dd_extras", dd="late_other_host", other_origin=OTHER)
    try:
        synthetic_candidate(api)
        job_id = v2_job(api)
        assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
        app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
        p = api.get(f"/applications/{app_id}/package").json()["package"]
    finally:
        receiver.config(other_origin="")
    extra = next(a for a in p["content"]["answers"] if a["key"] == "extra-1")
    assert (extra["status"], extra["value"]) == ("needs_user", None)
    assert "extra-1" in p["content"]["unresolved"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code != 200
    assert canary == [] and receiver.ledger()["disclosures"] == []


def test_no_pilot_rule_admits_another_greenhouse_host_or_a_data_endpoint():
    """The pilot's subresource rules are read-only path B3's assets plus path C's locale rule;
    the hosts refused in run #11 stay refused (a widget asking for them changes nothing)."""
    from app.modules.execution import live

    rules = live.subresources("https://job-boards.greenhouse.io")
    assert {r.origin for r in rules} == {"https://job-boards.cdn.greenhouse.io"}
    for url in ("https://my.greenhouse.io/x.json", "https://boards.greenhouse.io/x/jobs/1.json",
                "https://job-boards.cdn.greenhouse.io/x/options.json",
                "https://job-boards.cdn.greenhouse.io/locales/en/x.json?q=1"):  # fmt: skip
        for rtype in ("fetch", "xhr"):
            assert not any(r.permits(url, "GET", rtype) for r in rules), (url, rtype)
