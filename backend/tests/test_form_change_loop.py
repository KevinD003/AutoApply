"""D132: a form that changes after approval pauses the application instead of ending in a dead
end. Before anything is entered the attempt stops (never resumed or retried), every live
approval is retired, and a pause is recorded; while it is unresolved nothing is approved for the
application. "Questions needing your answer" lists it; reading the form again brings the new
question; once it is answered and approved, exactly one new attempt runs. A change found after
filling never pauses: the attempt is abandoned and every approval retired. The receiver's ledger
is the oracle: what reached the employer, never our own tables. Synthetic, fictional employers
only; nothing real is read or sent."""

import sys
import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import (
    ApplicationPause,
    AttemptEvent,
    AttemptState,
    ExecutionAttempt,
)
from app.modules.preparation.models import PackageApproval
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

BOARD, JOB = "northwind", "5020001"
ADDED = "question_8106"  # greenhouse_v2.ADDED_QUESTION: "Are you available to work weekends?"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def v2_application(api, *, approve=True) -> str:
    synthetic_candidate(api)
    job_id = api.post(
        "/jobs",
        json={
            "url": f"{BASE}/gh2/{BOARD}/jobs/{JOB}",
            "title": "Support Specialist",
            "employer": "Northwind Example (fictional)",
        },
    ).json()["job"]["id"]
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    for key, value in {
        "preferred_name": {"text": "Sammy"},
        "question_8101": {"label": "Yes"},
        "question_8104": {"label": "No"},
    }.items():
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, r.text
    if approve:
        approve_current(api, app_id)
    return app_id


def live_application(api, **kw) -> str:
    pilot_on()
    return v2_application(api, **kw)


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def approve_current(api, app_id):
    p = package(api, app_id)
    return api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )


def pauses(app_id) -> list[ApplicationPause]:
    with SessionLocal() as db:
        return db.scalars(
            select(ApplicationPause)
            .where(ApplicationPause.application_id == uuid.UUID(app_id))
            .order_by(ApplicationPause.created_at)
        ).all()


def live_approvals(app_id) -> list[PackageApproval]:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()


def paused_application(api, receiver, make=v2_application) -> tuple[str, str]:
    """An approved application whose employer added a required question before the worker ran."""
    app_id = make(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_question_added")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    return app_id, aid


# ------------------------------------------------------------------ the pause


@pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])
def test_a_question_added_after_approval_pauses_before_anything_is_sent(api, receiver, make):
    app_id, aid = paused_application(api, receiver, make)
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert "changed since you approved" in attempt(aid).outcome_detail
    (p,) = pauses(app_id)
    assert (p.status, p.kind) == ("open", "form_changed")
    assert p.detail == {"new": 1, "changed": 0, "missing": 0}
    assert p.package_hash == attempt(aid).package_hash and p.attempt_id == uuid.UUID(aid)
    assert live_approvals(app_id) == []  # every approval retired: nothing can send it again
    with SessionLocal() as db:
        retired = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "package.approval_retired")
        ).all()
    assert retired == [{"reason_code": "form_changed"}]
    assert api.get(f"/applications/{app_id}").json()["state"] == "needs_user_action"
    r = approve_current(api, app_id)
    assert r.status_code == 409 and "form_recapture_needed" in r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code in (400, 409)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "running"})
    assert r.status_code == 409 and "form_recapture_needed" in r.text
    with SessionLocal() as db:
        assert db.scalar(
            select(ExecutionAttempt.id).where(
                ExecutionAttempt.application_id == uuid.UUID(app_id),
                ExecutionAttempt.state == "pending",
            )
        ) is None  # fmt: skip


def test_the_pause_is_listed_with_what_to_do(api, receiver):
    app_id, _ = paused_application(api, receiver)
    (item,) = api.get("/questions").json()["items"]
    assert item["application_id"] == app_id
    assert item["pause"]["status"] == "open" and item["pause"]["counts"]["new"] == 1
    assert item["recapture_available"] is True
    assert api.get("/questions/count").json() == {"applications": 1, "paused": 1}
    feed = api.get("/notifications").json()["items"]
    mine = [n for n in feed if n["application_id"] == app_id]
    assert [n["kind"] for n in mine].count("form_changed") == 1
    assert next(n for n in mine if n["kind"] == "form_changed")["link"] == "/questions"
    assert not [n for n in mine if n["key"].startswith("attempt:")]  # the pause is the item


# ------------------------------------------------------------------ read again, answer, one run


@pytest.mark.parametrize("make", [v2_application, live_application], ids=["by_id", "pilot"])
def test_reading_the_form_again_brings_the_question_and_one_new_attempt_sends_it(
    api, receiver, make
):
    app_id, _ = paused_application(api, receiver, make)
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["form"]["changed"] is True
    assert out["pause"]["status"] == "resolved" and out["pause"]["resolution"] == "new_form"
    content = package(api, app_id)["content"]
    assert ADDED in content["unresolved"]
    a = {x["key"]: x for x in content["answers"]}
    assert a["question_8101"]["value"]["label"] == "Yes"  # earlier answers kept
    (item,) = api.get("/questions").json()["items"]
    assert [q["key"] for q in item["questions"]] == [ADDED] and item["pause"] is None
    r = api.put(f"/applications/{app_id}/answers", json={"key": ADDED, "value": {"label": "Yes"}})
    assert r.status_code == 200, r.text
    assert approve_current(api, app_id).status_code == 200
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1  # exactly one acceptance, with the new answer
    assert led["acceptances"][0]["fields"][ADDED] == "1"
    assert api.get("/questions").json()["items"] == []


def test_a_recapture_that_finds_no_difference_refuses_any_approval_until_you_try_again(
    api, receiver
):
    app_id, _ = paused_application(api, receiver)
    receiver.config(mode="normal")  # the employer changed it back before it was read again
    out = api.post(f"/applications/{app_id}/form/recapture").json()
    assert out["form"]["changed"] is False and out["pause"]["status"] == "unexplained"
    r = approve_current(api, app_id)
    assert r.status_code == 409 and "form_change_unexplained" in r.text
    # Another answer is another package, but not a way around the pause: still refused.
    r = api.put(
        f"/applications/{app_id}/answers",
        json={"key": "preferred_name", "value": {"text": "Sam"}},
    )
    assert r.status_code == 200, r.text
    r = approve_current(api, app_id)
    assert r.status_code == 409 and "form_change_unexplained" in r.text
    assert api.post(f"/applications/{app_id}/pause/dismiss").status_code == 200
    assert approve_current(api, app_id).status_code == 200
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1


def test_a_form_read_on_the_jobs_page_ends_the_pause_and_so_does_an_older_one_read_again(
    api, receiver
):
    app_id, _ = paused_application(api, receiver)
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201  # any capture route
    (p,) = pauses(app_id)
    assert (p.status, p.resolution, p.recaptured_version) == ("resolved", "new_form", 2)
    # A pause written after that version was stored (its attempt ran an older package): reading
    # again finds the form unchanged since version 2, which still differs from the paused one.
    with SessionLocal() as db:
        row = db.get(ApplicationPause, p.id)
        row.status, row.resolution, row.resolved_at, row.recaptured_version = "open", *[None] * 3
        db.commit()
    out = api.post(f"/applications/{app_id}/form/recapture").json()
    assert out["form"] == {"version": 2, "changed": False}
    assert (out["pause"]["status"], out["pause"]["resolution"]) == ("resolved", "new_form")


def test_a_recapture_refused_by_the_capture_route_leaves_the_pause_open(api, receiver):
    app_id, _ = paused_application(api, receiver, live_application)
    pilot_on(permitted=())  # the recorded permission to read is gone: the route's check refuses
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 409, r.text
    assert receiver.ledger()["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_reading_again_needs_a_pause_and_no_attempt_holding_the_application(api, receiver):
    app_id = v2_application(api)
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 409 and "no_pause" in r.text  # nothing to read it again for
    app_id, _ = paused_application(api, receiver)
    with SessionLocal() as db:  # an attempt holding it (pending), however it got there
        att = db.scalar(
            select(ExecutionAttempt).where(ExecutionAttempt.application_id == uuid.UUID(app_id))
        )
        att.state = AttemptState.pending
        db.commit()
    r = api.post(f"/applications/{app_id}/form/recapture")
    assert r.status_code == 409 and "recapture_not_available" in r.text
    assert receiver.ledger()["disclosures"] == []


# ------------------------------------------------------------------ boundaries


def test_a_stale_worker_writes_no_pause(api, receiver):
    app_id = v2_application(api)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    assert gen is not None
    stale = svc.pause_for_form_change(aid, "w1", gen + 1, "the form has changed", {"new": 1})
    assert stale is False
    assert pauses(app_id) == [] and len(live_approvals(app_id)) == 1
    assert attempt(aid).state == "claimed"


def test_no_pause_is_written_once_data_was_entered(api, receiver):
    # The runner asks for a pause only before filling; the service judges from the row, never
    # from the caller, and writes nothing once the disclosure gate was passed.
    app_id = v2_application(api)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    with SessionLocal() as db:
        from app.core.db import utcnow

        db.get(ExecutionAttempt, uuid.UUID(aid)).disclosure_started_at = utcnow()
        db.commit()
    assert svc.pause_for_form_change(aid, "w1", gen, "the form has changed", {"new": 1}) is False
    assert attempt(aid).state == "claimed" and pauses(app_id) == []
    assert len(live_approvals(app_id)) == 1


def test_a_change_after_filling_is_abandoned_with_every_approval_retired_and_no_pause(
    api, receiver
):
    from tests.test_hidden_search import MODE, by_id

    receiver.config(mode=MODE, hs="late")  # the page shows a search box once the phone is in
    app_id = by_id(api)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    assert attempt(aid).outcome_detail.startswith("Stopped after entering data")
    assert pauses(app_id) == [] and live_approvals(app_id) == []
    with SessionLocal() as db:
        reasons = db.scalars(
            select(PackageApproval.invalidation_reason).where(
                PackageApproval.application_id == uuid.UUID(app_id)
            )
        ).all()
    assert reasons == [svc.RETIRED["stopped_after_entry"]]  # entering it again is a new approval
    api.get(f"/applications/{app_id}/package")  # settles the state: it waits for an approval
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409, r.text
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []


def test_trying_this_version_again_runs_it_again_and_a_change_still_there_stops_it(api, receiver):
    app_id, _ = paused_application(api, receiver)
    r = api.post(f"/applications/{app_id}/pause/dismiss")
    assert r.status_code == 200, r.text
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("closed", "dismissed")
    assert approve_current(api, app_id).status_code == 200  # the same package, your decision
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "failed_safe"  # the change is still there
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["disclosures"] == []
    assert [x.status for x in pauses(app_id)] == ["closed", "open"]


def test_options_only_the_page_changed_pause_and_a_read_finds_no_difference(api, receiver):
    # A dropdown offering other options is a change a read could show; here only the page has
    # it (the job data a read compares is the same), so the read ends unexplained.
    app_id = v2_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_options_changed")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert receiver.ledger()["disclosures"] == []
    (p,) = pauses(app_id)
    assert p.status == "open" and p.detail == {"new": 0, "changed": 1, "missing": 0}
    out = api.post(f"/applications/{app_id}/form/recapture").json()
    assert out["form"]["changed"] is False and out["pause"]["status"] == "unexplained"


def test_what_only_the_running_page_shows_stays_a_plain_stop(api, receiver):
    # A requirement only the running page marks: a read (no scripts) could not show it, so no
    # pause and no retirement; the stop is what it always was.
    app_id = v2_application(api)
    aid = queue(api, app_id)
    receiver.config(mode="gh2_required_cover_group")
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    assert "required by the page" in attempt(aid).outcome_detail
    assert pauses(app_id) == [] and receiver.ledger()["disclosures"] == []


def test_an_approval_given_while_the_attempt_ran_is_retired_by_the_pause(api, receiver):
    app_id = v2_application(api)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), "w1")
    assert gen is not None
    r = api.post(f"/applications/{app_id}/package/revoke")
    assert r.status_code == 200, r.text
    assert approve_current(api, app_id).status_code == 200  # approving does not wait for it
    assert len(live_approvals(app_id)) == 1
    assert svc.pause_for_form_change(aid, "w1", gen, "the form has changed", {"new": 1}) is True
    assert live_approvals(app_id) == []
    assert receiver.ledger()["disclosures"] == []


def test_cancelling_closes_the_pause(api, receiver):
    app_id, _ = paused_application(api, receiver)
    r = api.post(f"/applications/{app_id}/transition", json={"to": "cancelled"})
    assert r.status_code == 200, r.text
    (p,) = pauses(app_id)
    assert (p.status, p.resolution) == ("closed", "cancelled")
    assert api.get("/questions/count").json()["paused"] == 0


def test_another_account_cannot_read_the_form_again_or_see_the_pause(api, other_api, receiver):
    app_id, _ = paused_application(api, receiver)
    assert other_api.post(f"/applications/{app_id}/form/recapture").status_code == 404
    assert other_api.post(f"/applications/{app_id}/pause/dismiss").status_code == 404
    assert other_api.get("/questions").json()["items"] == []
    assert other_api.get("/questions/count").json() == {"applications": 0, "paused": 0}
    (p,) = pauses(app_id)
    assert p.status == "open"


def test_the_count_never_builds_or_writes_a_package(api, receiver, monkeypatch):
    # The navigation reads the count on every page: it must never rebuild a package (which
    # writes versions, retires approvals and moves states). A rebuild is refused outright here,
    # and nothing at all is written while it counts.
    from app.modules.preparation import package as pk
    from app.modules.preparation.models import ApplicationPackage

    app_id, _ = paused_application(api, receiver)
    # An input changes without a rebuild: the next rebuild would write a new version.
    r = api.put("/profile", json={"full_name": "Sam Q. Synthetic", "given_name": "Sam",
                                  "family_name": "Synthetic"})  # fmt: skip
    assert r.status_code == 200, r.text

    def refuse(*a, **k):
        raise AssertionError("the count rebuilt a package")

    def written(db):
        return (
            db.scalar(select(func.count()).select_from(ApplicationPackage)),
            db.scalar(select(func.count()).select_from(AuditEvent)),
            db.scalar(select(func.count()).select_from(PackageApproval)),
        )

    with SessionLocal() as db:
        before = written(db)
    with monkeypatch.context() as m:
        m.setattr(pk, "ensure_current", refuse)
        for _ in range(3):
            assert api.get("/questions/count").json() == {"applications": 1, "paused": 1}
    with SessionLocal() as db:
        assert written(db) == before
    package(api, app_id)  # what a rebuild does write, so the check above can fail
    with SessionLocal() as db:
        assert written(db)[0] == before[0] + 1


def test_a_document_to_choose_is_chosen_on_the_applications_page(api, receiver):
    # Two resumes: which one to send is your choice, made on the application's page; it is
    # never "apply on the employer's site".
    from tests.execution_harness import PDF

    synthetic_candidate(api)
    r = api.post("/documents", files={"file": ("second-resume.pdf", PDF, "application/pdf")})
    assert r.status_code in (200, 201), r.text
    v2_application(api, approve=False)
    (item,) = api.get("/questions").json()["items"]
    rows = {q["key"]: q for q in item["questions"]}
    assert rows["resume"]["category"] == "document"
    assert {q["category"] for q in item["questions"]} <= {"answer", "consent", "document"}


def test_no_question_key_or_label_in_the_pause_its_events_or_the_audit(api, receiver):
    app_id, aid = paused_application(api, receiver)
    api.post(f"/applications/{app_id}/form/recapture")
    (p,) = pauses(app_id)
    assert set(p.detail) == {"new", "changed", "missing"}
    with SessionLocal() as db:
        events = db.scalars(
            select(AttemptEvent.detail).where(AttemptEvent.attempt_id == uuid.UUID(aid))
        ).all()
        audits = db.scalars(
            select(AuditEvent.meta).where(AuditEvent.action == "application.form_recaptured")
        ).all()
    blob = repr(events) + repr(audits) + repr(p.detail) + attempt(aid).outcome_detail
    assert "question_" not in blob and "weekends" not in blob.lower()
    assert audits and set(audits[-1]) == {"form_version", "new_version", "pause"}


# ------------------------------------------------------------------ races (two real transactions)


def _sides(app_id):
    """The application's owner and job, and the two request bodies the races run, each in its
    own session (its own connection), as tests/test_bank_races.py does."""
    from app.modules.identity.models import User
    from app.modules.preparation import router as prep

    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        user_id, job_id = app.user_id, app.job_id

    def call(fn, *args, **kw):
        with SessionLocal() as db:
            return fn(*args, user=db.get(User, user_id), db=db, **kw)

    return {
        "dismiss": lambda: call(prep.dismiss_pause, uuid.UUID(app_id)),
        "recapture": lambda: call(prep.recapture_form, uuid.UUID(app_id)),
        "read": lambda: call(prep.capture_greenhouse_form, job_id),
    }


def _race(hold, first_name, first, start_second):
    """`first` runs in thread `first_name` and is held by `hold`; then `start_second()` starts
    the other side, which must wait on a row lock; then `first` is released. Both finish."""
    from tests.test_lock_order import TIMEOUT, Side, lock_waiters, no_errors, wait_until

    try:
        a = Side(first_name, first)
        assert hold.reached.wait(TIMEOUT), f"{first_name} never reached its hold"
        before = lock_waiters()
        b = start_second()
        wait_until(lambda: lock_waiters() > before or not b.thread.is_alive(), "the read waits")
        assert b.thread.is_alive(), (b.error, "the read did not wait for the pause's lock")
    finally:
        hold.go.set()
    a.join(), b.join()
    no_errors(a, b)


def test_a_form_read_during_try_again_waits_and_never_overwrites_it(api, receiver, monkeypatch):
    """"Try this version again" reads the pause under its row lock, as it is now. A form read
    that would resolve it meanwhile waits, then finds it closed: one outcome, never a lost
    resolution (before, the read's "new_form" was overwritten with "dismissed")."""
    from app.modules.preparation import package as pk
    from tests.test_lock_order import Hold, Side

    app_id, _ = paused_application(api, receiver)  # the page still has the added question
    sides = _sides(app_id)
    hold = Hold("dismiss")  # held once it has read the pause (and, now, locked it)
    monkeypatch.setattr(pk, "unresolved_pause", hold.wrap(pk.unresolved_pause, after=True))
    _race(hold, "dismiss", sides["dismiss"], lambda: Side("read", sides["read"]))
    (p,) = pauses(app_id)
    assert (p.status, p.resolution, p.recaptured_version) == ("closed", "dismissed", None)
    assert receiver.ledger()["disclosures"] == []


def test_a_form_read_during_another_read_is_never_marked_unexplained(api, receiver, monkeypatch):
    """Reading the form again marks the pause it read for unexplained only as the pause is now,
    under its row lock. A second read that finds a new form waits, then resolves it (before, the
    first read's "unexplained" overwrote that resolution)."""
    from app.modules.preparation import package as pk
    from tests.test_lock_order import Hold, Side

    app_id, _ = paused_application(api, receiver)
    receiver.config(mode="normal")  # the first read finds the form as approved: no difference
    sides = _sides(app_id)
    hold = Hold("recapture")  # held after marking the pause, before its rebuild and commit
    monkeypatch.setattr(pk, "ensure_current", hold.wrap(pk.ensure_current))

    def second():
        receiver.config(mode="gh2_question_added")  # the second read finds the added question
        return Side("read", sides["read"])

    _race(hold, "recapture", sides["recapture"], second)
    (p,) = pauses(app_id)
    assert (p.status, p.resolution, p.recaptured_version) == ("resolved", "new_form", 2)


def test_a_paused_application_says_why_it_waits(api, receiver):
    # Fully answered and paused: its timeline says the form changed, never "0 question(s)".
    from app.modules.preparation import package as pk

    app_id, _ = paused_application(api, receiver)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "preferred_name", "value": {"text": "Sam"}})  # fmt: skip
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        reasons = db.scalars(
            select(ApplicationEvent.reason)
            .where(ApplicationEvent.application_id == uuid.UUID(app_id))
            .order_by(ApplicationEvent.created_at.desc())
        ).all()
    assert reasons[0] == pk.PAUSED_REASON
    assert not any("0 question(s)" in (x or "") for x in reasons)
