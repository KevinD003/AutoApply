"""D102: the Greenhouse pilot (execution/live.py), off by default.

Its fills, uploads and outcomes are the id-mapping adapter's and run against the second local
Greenhouse-style approximation playing a real board host (tests/test_greenhouse_dom.py, the
`pilot` cases, with the receiver's ledger as the oracle). Here: who and where it is on for, what
it reads and from where, that the first application to an employer is a rehearsal, and that
switching it off stops what was approved before anything is sent. No real host is contacted:
in the test environment real Greenhouse hosts are refused before any connection."""

import socket

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


def test_the_browser_may_load_only_greenhouses_static_assets_on_a_real_board():
    (rule,) = live.subresources("https://job-boards.greenhouse.io")
    assert rule.origin == "https://job-boards.cdn.greenhouse.io"
    assert rule.methods == frozenset({"GET", "HEAD"})
    assert rule.resource_types == frozenset({"script", "stylesheet"})
    assert live.subresources(BASE) == ()


# -- applying ------------------------------------------------------------------------------------


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
