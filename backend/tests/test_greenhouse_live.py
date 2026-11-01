"""D102: the Greenhouse pilot (execution/live.py), off by default.

Its fills, uploads and outcomes are the id-mapping adapter's and run against the second local
Greenhouse-style approximation playing a real board host (tests/test_greenhouse_dom.py, the
`pilot` cases, with the receiver's ledger as the oracle). Here: who and where it is on for, what
it reads and from where, that the first application to an employer is a rehearsal, and that
switching it off stops what was approved before anything is sent. No real host is contacted:
in the test environment real Greenhouse hosts are refused before any connection."""

import socket
import uuid

import pytest

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.execution import live, policy, runner
from app.modules.identity.models import User
from app.modules.preparation.models import JobForm
from tests.execution_harness import BASE, Receiver, pilot_on, queue
from tests.test_greenhouse_dom import BOARD, LOC_JOB, live_application, v2_job

GH_REAL = "https://job-boards.greenhouse.io/exampleboard/jobs/4000001"  # a fictional board
OWNER = "synthetic.user@example.com"  # the `api` fixture's account
AT = "@"  # userinfo is built at run time: the repository holds no address-shaped text


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def forms(job_id) -> list[JobForm]:
    with SessionLocal() as db:
        return list(db.query(JobForm).filter(JobForm.job_id == job_id))


def approve(api, app_id, scope="submit"):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"],
                          "scope": scope})  # fmt: skip


# -- off, and for whom and where it is on ---------------------------------------------------------


def test_off_by_default_a_real_greenhouse_post_is_neither_read_nor_routed(api):
    assert live.environment_refusal() == "not_enabled"
    new = {"url": GH_REAL, "title": "Engineer", "employer": "Example Board (fictional)"}
    job = api.post("/jobs", json=new).json()["job"]
    r = api.post(f"/jobs/{job['id']}/form/greenhouse")
    assert r.status_code == 409 and "not enabled" in r.text
    route = api.get(f"/jobs/{job['id']}/route").json()
    assert (route["route"], route["reason"]) == ("manual_handoff", "real_destination_disabled")
    assert forms(job["id"]) == []


def test_the_owner_captures_through_the_pilot_and_no_one_else_can(api, other_api, receiver):
    pilot_on(OWNER)
    mine = v2_job(api)
    assert api.post(f"/jobs/{mine}/form/greenhouse").status_code == 201
    (form,) = forms(mine)
    assert (form.source, form.extraction_version) == ("greenhouse_live", live.EXTRACTION_VERSION)
    route = api.get(f"/jobs/{mine}/route").json()
    assert (route["route"], route["provider"]) == ("browser", "greenhouse_live")
    # Another account: the pilot is the owner's only, and the owner's job is not even visible.
    theirs = v2_job(other_api)
    r = other_api.post(f"/jobs/{theirs}/form/greenhouse")
    assert r.status_code == 409 and "server owner's account only" in r.text
    assert other_api.get(f"/jobs/{theirs}/route").json()["reason"] == "live_not_for_this_account"
    assert forms(theirs) == []
    assert other_api.get(f"/jobs/{mine}/route").status_code == 404
    assert other_api.post(f"/jobs/{mine}/form/greenhouse").status_code == 404


@pytest.mark.parametrize(
    "env,isolation,why",
    [
        ("production", "container", None),
        ("production", "netns", "needs_container"),
        ("development", "container", "needs_production"),
        ("test", "netns", None),  # the local stand-in only (below)
    ],
)
def test_the_pilot_runs_only_in_production_with_the_browsers_own_sandbox(
    monkeypatch, env, isolation, why
):
    pilot_on(OWNER)
    monkeypatch.setattr(get_settings(), "env", env)
    monkeypatch.setattr(get_settings(), "browser_isolation", isolation)
    assert live.environment_refusal() == why
    owner, other = User(email=OWNER.upper()), User(email="someone.else@example.com")
    assert live.refusal(owner) == why
    assert live.refusal(other) == (why or "not_for_this_account")
    get_settings().live_greenhouse_enabled = False
    assert live.refusal(owner) == "not_enabled"


# -- what it reads, and from where ----------------------------------------------------------------


@pytest.mark.parametrize(
    "url,ok",
    [
        (GH_REAL, ("exampleboard", "4000001")),
        ("https://boards.greenhouse.io/exampleboard/jobs/4000001/", ("exampleboard", "4000001")),
        ("https://job-boards.eu.greenhouse.io/exampleboard/jobs/4000001", ("exampleboard",
                                                                           "4000001")),
        ("https://boards.greenhouse.io/embed/job_app?for=exampleboard&token=4000001",
         ("exampleboard", "4000001")),
        ("http://job-boards.greenhouse.io/exampleboard/jobs/4000001", None),  # not https
        ("https://job-boards.greenhouse.io:8443/exampleboard/jobs/4000001", None),  # a port
        (f"https://user{AT}job-boards.greenhouse.io/exampleboard/jobs/4000001", None),  # userinfo
        ("https://greenhouse.io.example/exampleboard/jobs/4000001", None),  # a look-alike
        ("https://job-boards.greenhouse.io/exampleboard/jobs/x", None),
        ("https://job-boards.greenhouse.io/exampleboard/jobs/4000001/apply", None),
        ("https://boards.greenhouse.io/embed/job_app?for=../x&token=4000001", None),
        (None, None),
    ],
)  # fmt: skip
def test_only_a_job_post_on_a_greenhouse_board_host_is_the_pilots(url, ok):
    p = live.posting(url)
    assert (p and (p.board, p.job_id)) == (ok or None)


def test_no_real_greenhouse_host_is_contacted_from_tests(monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr(socket, "create_connection", refuse)
    for url in ("https://boards-api.greenhouse.io/v1/boards/x/jobs/1?questions=true", GH_REAL,
                "https://example.com/x"):  # fmt: skip
        with pytest.raises(live.LiveError) as e:
            live.fetch(url)
        assert e.value.code == "host_refused"
    assert not live.page_origin_allowed("https://job-boards.greenhouse.io")
    pilot_on(OWNER)
    assert live.page_origin_allowed(BASE) and not live.page_origin_allowed("http://127.0.0.2:1")


def test_in_production_only_greenhouse_hosts_at_public_addresses_are_read(monkeypatch):
    pilot_on(OWNER)
    monkeypatch.setattr(get_settings(), "env", "production")
    # The stand-in is never honoured outside tests.
    assert not live.page_origin_allowed(BASE)
    assert live.page_origin_allowed("https://job-boards.greenhouse.io")
    with pytest.raises(live.LiveError) as e:
        live.fetch(f"{BASE}/gh2-api/robots.txt")
    assert e.value.code == "host_refused"

    def private(host, *a, **kw):  # a Greenhouse name that resolves to this machine
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", private)
    with pytest.raises(live.LiveError) as e:
        live.fetch("https://boards-api.greenhouse.io/robots.txt")
    assert e.value.code == "unavailable"


def test_robots_and_the_posts_own_identity_are_checked_before_a_form_is_kept(
    api, receiver, monkeypatch
):
    pilot_on(OWNER)
    job = v2_job(api)
    receiver.config(mode="gh2_robots_disallow")
    r = api.post(f"/jobs/{job}/form/greenhouse")
    assert r.status_code == 409 and "robots_disallowed" in r.text
    receiver.config(mode="")
    # The data of another job post on the board, answered for this one's address.
    other = f"{BASE}/gh2-api/v1/boards/{BOARD}/jobs/{LOC_JOB}?questions=true"
    monkeypatch.setattr(live, "api_url", lambda p: other)
    r = api.post(f"/jobs/{job}/form/greenhouse")
    assert r.status_code == 409 and "not_this_post" in r.text
    assert forms(job) == []


def test_a_redirect_is_never_followed():
    handler = live._NoRedirect()
    with pytest.raises(live.LiveError) as e:
        handler.redirect_request(None, None, 302, "Found", {}, f"{BASE}/elsewhere")
    assert e.value.code == "redirected"


def test_the_browser_may_load_only_greenhouses_static_assets_and_locale_files_on_a_real_board():
    """D110 (prepared for the owner's approval with the first rehearsal): B3's scripts and
    stylesheets, and read-only path C's exact locale rule, which run #11 used; nothing else."""
    from app.modules.preparation import gh_readonly as ro

    assets, locales = live.subresources("https://job-boards.greenhouse.io")
    assert assets.origin == locales.origin == "https://job-boards.cdn.greenhouse.io"
    assert assets.methods == frozenset({"GET", "HEAD"})
    assert assets.resource_types == frozenset({"script", "stylesheet"}) and assets.path is None
    assert locales == ro._locale_rule_c()
    assert locales.methods == frozenset({"GET"}) and locales.resource_types == frozenset({"fetch"})
    cdn = "https://job-boards.cdn.greenhouse.io"
    assert locales.permits(f"{cdn}/locales/en/common.6f8a2c1d.json", "GET", "fetch")
    for url, method, rtype in [(f"{cdn}/locales/en/x.json?v=1", "GET", "fetch"),
                               (f"{cdn}/locales/en/x.json", "POST", "fetch"),
                               (f"{cdn}/locales/en/x.json", "GET", "xhr"),
                               (f"{cdn}/gh/data.json", "GET", "fetch"),
                               (f"{cdn}/locales/../x.json", "GET", "fetch")]:  # fmt: skip
        assert not locales.permits(url, method, rtype), (url, method, rtype)
    assert live.subresources(BASE) == ()


def test_a_locale_file_passes_only_from_the_pages_main_frame(receiver):
    """D110: in the browser the pilot uses, a request admitted only by the path-limited locale
    rule passes from the page's main frame (where the fetch redirect guard runs) and is refused
    from a child frame, as read-only path C refused it. The receiver's log is the oracle."""
    from app.modules.execution.browser import browser_session
    from app.modules.preparation import gh_readonly as ro
    from tests.conftest import RECEIVER_PORT
    from tests.test_locale_observation import JOB_PATH

    cdn = f"http://localhost:{RECEIVER_PORT}"  # the CDN stand-in: same receiver, another name
    hashed = "/locales/en/common.6f8a2c1d.json"
    rule = ro._locale_rule_c(cdn, allow_private=True)
    try:
        for via, reached in (("fetch", True), ("iframe", False)):
            receiver.reset()
            receiver.config(mode="gh2_dd", dd="locale_gate", locale_origin=cdn,
                            locale_path=hashed, locale_via=via)  # fmt: skip
            with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                                 allow_private_destination=True,
                                 subresources=(rule,)) as (page, log):  # fmt: skip
                page.goto(f"{BASE}{JOB_PATH}")
                page.wait_for_timeout(1500)
            paths = [r["path"] for r in receiver.ledger()["requests"]]
            assert (hashed in paths) is reached, (via, paths)
            assert all(r["method"] == "GET" for r in receiver.ledger()["requests"])
    finally:
        receiver.config(locale_origin=None, locale_path=None, locale_via=None)


@pytest.mark.parametrize("driver_fetch", [False, True], ids=["browser_fetches", "driver_fetches"])
def test_a_redirect_of_a_locale_request_is_never_followed_unseen(receiver, driver_fetch):
    """D111, in case the page's fetch guard is bypassed: with the browser fetching (netns and
    container modes, where redirects are not routed) a followed redirect is recorded, and the
    runner stops on it; with the driver fetching, the redirect is refused before its target is
    requested. The receiver's log is the oracle."""
    from playwright.sync_api import sync_playwright

    from app.modules.execution.browser import EgressLog, _install_interception
    from app.modules.execution.runner import LOCALE_REDIRECTED
    from app.modules.preparation import gh_readonly as ro
    from tests.conftest import RECEIVER_PORT
    from tests.test_locale_observation import JOB_PATH

    cdn = f"http://localhost:{RECEIVER_PORT}"  # the CDN stand-in: same receiver, another name
    moved, target = "/locales/moved/common.json", "/locales/en/common.json"
    log = EgressLog()
    receiver.config(mode="gh2_dd", dd="locale_gate", locale_origin=cdn, locale_path=moved,
                    locale_via="fetch")  # fmt: skip
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                ctx = browser.new_context()
                rule = ro._locale_rule_c(cdn, allow_private=True)
                _install_interception(ctx, BASE, log, driver_fetch=driver_fetch,
                                      subresources=(rule,))  # fmt: skip
                page = ctx.new_page()  # no fetch guard: the case it would prevent
                page.goto(f"{BASE}{JOB_PATH}")
                page.wait_for_timeout(1500)
            finally:
                browser.close()
    finally:
        receiver.config(locale_origin=None, locale_path=None, locale_via=None)
    paths = [r["path"] for r in receiver.ledger()["requests"]]
    if driver_fetch:
        assert target not in paths and log.redirected == [], (paths, log.redirected)
    else:
        assert moved in paths and log.redirected == [f"{cdn}{moved}"], (paths, log.redirected)
    assert LOCALE_REDIRECTED == "a request for one of the page's locale files was redirected"


def test_locale_requests_are_bounded_by_path_cs_request_budget(receiver, monkeypatch):
    """D111: requests passed by the path-limited locale rule are capped per session at read-only
    path C's page-request budget; beyond it they are refused before sending (here the cap is
    lowered to 0, so the one locale file is refused). The receiver's log is the oracle."""
    from playwright.sync_api import sync_playwright

    from app.modules.execution import browser as br
    from app.modules.preparation import gh_readonly as ro
    from tests.conftest import RECEIVER_PORT
    from tests.test_locale_observation import JOB_PATH

    assert br.PATH_LIMITED_REQUESTS == ro.LIMITS.page_requests == 150
    cdn = f"http://localhost:{RECEIVER_PORT}"
    hashed = "/locales/en/common.6f8a2c1d.json"
    try:
        for cap, reached in ((1, True), (0, False)):
            receiver.reset()
            receiver.config(mode="gh2_dd", dd="locale_gate", locale_origin=cdn,
                            locale_path=hashed, locale_via="fetch")  # fmt: skip
            monkeypatch.setattr(br, "PATH_LIMITED_REQUESTS", cap)
            log = br.EgressLog()
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    ctx = browser.new_context()
                    br._install_interception(ctx, BASE, log, driver_fetch=False, subresources=(
                        ro._locale_rule_c(cdn, allow_private=True),))  # fmt: skip
                    page = ctx.new_page()
                    page.goto(f"{BASE}{JOB_PATH}")
                    page.wait_for_timeout(1500)
                finally:
                    browser.close()
            paths = [r["path"] for r in receiver.ledger()["requests"]]
            assert (hashed in paths) is reached, (cap, paths, log.blocked)
            assert (f"{cdn}{hashed}" in log.blocked) is (not reached)
    finally:
        receiver.config(locale_origin=None, locale_path=None, locale_via=None)


def test_the_runner_stops_on_a_followed_locale_redirect_before_entering_and_before_submitting():
    import inspect

    from app.modules.execution import runner as rn

    src = inspect.getsource(rn.run_attempt)
    first = src.index("LOCALE_REDIRECTED if eg.redirected")
    assert first < src.index("svc.gate_before_disclosure(")  # before anything is entered
    second = src.index("LOCALE_REDIRECTED if eg.redirected", first + 1)
    assert src.index("adapter.fill(page)") < second < src.index("_rehearsal(aid)")


def test_a_pilot_page_never_follows_a_redirect_of_its_own_fetches():
    """D110: on a real board the page gets path C's fetch guard before its own scripts run, and
    the runner applies it before navigating; the stand-in gets nothing."""
    import ast
    import inspect

    from app.modules.execution import runner as rn
    from app.modules.preparation import gh_readonly as ro

    assert live.init_scripts("https://job-boards.greenhouse.io") == (ro._NO_REDIRECT_JS,)
    assert live.init_scripts(BASE) == ()
    src = inspect.getsource(rn)
    assert src.index("live.init_scripts(") < src.index("page.goto(url)")
    assert "add_init_script" in src
    ast.parse(src)


# -- applying ------------------------------------------------------------------------------------


def test_the_owners_attempt_limit_stops_the_next_attempt_before_anything_is_entered(api, receiver):
    """D112: the recorded permission's limit (here 1) counts attempts that passed the disclosure
    gate; the next one stops at that gate with nothing entered. The ledger is the oracle."""
    app1 = live_application(api, approve=False)
    pilot_on(max_attempts=1)
    assert approve(api, app1, "disclose_only").status_code == 200
    assert runner.run_attempt(queue(api, app1), "w1") == "rehearsed"
    before = receiver.ledger()
    assert before["disclosures"] and before["accepted"] == 0
    assert approve(api, app1, "disclose_only").status_code == 200  # a second rehearsal
    aid = queue(api, app1)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    with SessionLocal() as db:
        from app.modules.execution.models import ExecutionAttempt

        att = db.get(ExecutionAttempt, uuid.UUID(aid))
        assert att.disclosure_started_at is None
        assert "at most 1 attempts" in (att.outcome_detail or "")
    after = receiver.ledger()
    assert after["disclosures"] == before["disclosures"] and after["accepted"] == 0


def test_the_first_application_to_an_employer_is_a_rehearsal(api, receiver, monkeypatch):
    """E6 on the pilot's path (the board): an approval to submit is refused until a rehearsal on
    that path succeeded; the rehearsal fills and checks and never submits."""
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths",
                        ["greenhouse_live:*"])  # fmt: skip
    app_id = live_application(api, approve=False)
    assert approve(api, app_id).status_code == 409  # no rehearsal yet: not even approvable
    assert approve(api, app_id, "disclose_only").status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"]  # filled and uploaded, never submitted
    assert approve(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_switching_the_pilot_off_stops_an_approved_application_before_anything_is_sent(
    api, receiver
):
    aid = queue(api, live_application(api))
    get_settings().live_greenhouse_enabled = False
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for({"form_source": "greenhouse_live", "origin": BASE,
                            "submit_url": f"{BASE}/x", "url": f"{BASE}/gh2/b/jobs/1"})  # fmt: skip
    assert e.value.code == "live_not_enabled"


# -- D103: switched on is not authorized ----------------------------------------------------------


def _reason(aid) -> str | None:
    """The reason code kept on the attempt's outcome event."""
    import uuid

    from app.modules.execution.models import AttemptEvent

    with SessionLocal() as db:
        (e,) = db.query(AttemptEvent).filter(AttemptEvent.attempt_id == uuid.UUID(aid),
                                             AttemptEvent.kind.like("outcome_%")).all()  # fmt: skip
        return e.detail.get("reason_code")


def test_the_switch_alone_reads_opens_and_sends_nothing(api, receiver, monkeypatch):
    """The owner's switch, the owner's account and the stand-in board, but no recorded
    permission: the job post is not read, the route says why, and nothing reaches the board."""
    pilot_on(OWNER, permitted=())
    called = []
    monkeypatch.setattr(live, "fetch", lambda url: called.append(url) or b"")
    job = v2_job(api)
    r = api.post(f"/jobs/{job}/form/greenhouse")
    assert r.status_code == 409 and "recorded permission" in r.text
    assert called == [] and forms(job) == []
    route = api.get(f"/jobs/{job}/route").json()
    assert (route["route"], route["reason"]) == ("manual_handoff", "live_not_authorized")
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for({"form_source": "greenhouse_live", "origin": BASE,
                            "submit_url": f"{BASE}/x", "url": f"{BASE}/gh2/b/jobs/1"})  # fmt: skip
    assert e.value.code == "live_not_authorized"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_permission_to_read_is_not_permission_to_open_or_fill(api, receiver):
    """Reading the job post (permission 1) captures the form; nothing can be queued on it."""
    pilot_on(OWNER, permitted=("read",))
    job = v2_job(api)
    assert api.post(f"/jobs/{job}/form/greenhouse").status_code == 201
    assert api.get(f"/jobs/{job}/route").json()["reason"] == "live_not_authorized"
    app_id = live_application(api, approve=False)
    pilot_on(OWNER, permitted=("read",))  # live_application turned every permission on
    assert approve(api, app_id, "disclose_only").status_code == 200  # your approval: yours
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "recorded permission" in r.text  # but nothing can run
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0


def test_a_permission_that_ends_after_queueing_stops_before_the_page_is_opened(api, receiver):
    aid = queue(api, live_application(api))  # every permission, at queueing
    pilot_on(OWNER, permitted=("read",))  # then only reading
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert _reason(aid) == "live_not_authorized"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0  # the page never even got a value


def test_permission_to_disclose_is_not_permission_to_submit(api, receiver):
    """A rehearsal may run with permissions 1-3; an approval to submit cannot be queued without
    permission 4, and permission 4 withdrawn after queueing stops at the send gate: the page was
    filled (that was permitted), the final click never happened."""
    app_id = live_application(api, approve=False)
    pilot_on(OWNER, permitted=("read", "open", "disclose"))
    assert approve(api, app_id, "disclose_only").status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "rehearsed"
    led = receiver.ledger()
    assert led["disclosures"] and led["accepted"] == 0
    assert approve(api, app_id).status_code == 200  # your approval to submit: still needed too
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and "recorded permission" in r.text
    pilot_on(OWNER)  # permission 4 recorded: it queues
    aid = queue(api, app_id)
    pilot_on(OWNER, permitted=("read", "open", "disclose"))  # and withdrawn before the click
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert _reason(aid) == "live_not_authorized"
    assert receiver.ledger()["accepted"] == 0


@pytest.mark.parametrize(
    "destination",
    [
        # A real employer's own site, captured from its page: no adapter, pilot or not.
        {"form_source": "html", "origin": "https://careers.example.com",
         "submit_url": "https://careers.example.com/apply", "url": "https://careers.example.com/j/1"},
        # A real Greenhouse board in the test environment: real hosts are production-only.
        {"form_source": "greenhouse_live", "origin": "https://job-boards.greenhouse.io",
         "submit_url": "https://job-boards.greenhouse.io/exampleboard/jobs/4000001",
         "url": GH_REAL},
        # The pilot's form source on another host than a Greenhouse board.
        {"form_source": "greenhouse_live", "origin": "https://careers.example.com",
         "submit_url": "https://careers.example.com/apply", "url": "https://careers.example.com/j/1"},
    ],
)  # fmt: skip
def test_every_permission_recorded_still_refuses_every_other_real_destination(destination):
    """D103: the register widens nothing: with all four permissions recorded and the switch on,
    a destination that is not the pilot's stand-in (here) or a Greenhouse board (production) is
    refused as before."""
    pilot_on(OWNER)
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for(destination)
    assert e.value.code in ("real_destination_disabled", "no_captured_destination")


def test_an_authorization_that_ends_while_queued_stops_before_the_page_opens(
    api, receiver, monkeypatch
):
    """D106: the register is read at every protected step, with today's date: an authorization
    that ends while an attempt waits stops it at the next step, in the same running process.
    (Removing an entry from the code takes effect when the API and worker restart: a running
    process keeps the register it imported. See docs/activation-status.md, "Stop".)"""
    from datetime import date, timedelta

    from app.core import authorizations as a

    aid = queue(api, live_application(api))  # every permission, no end date
    today = date.today()
    pilot_on(OWNER, permitted=())
    a.RECORDED += (a.Authorization(
        what=a.GREENHOUSE_PILOT, decision="TEST", given_on=today - timedelta(days=1),
        words="(synthetic: tests only)", actions=a.ACTIONS[a.GREENHOUSE_PILOT],
        data="synthetic test data only", ends_on=today),)  # fmt: skip
    assert live.permission_refusal(("open", "disclose")) is None  # still valid today

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return today + timedelta(days=1)

    monkeypatch.setattr(a, "date", Tomorrow)
    assert live.permission_refusal(("open", "disclose")) == "not_authorized"
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert _reason(aid) == "live_not_authorized"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
