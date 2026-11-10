"""D142: the Workday-style stand-in's multi-page wizard, driven forward only.

Every page boundary passes a fenced gate that commits an event before the action; anything
unexpected after disclosure ends the attempt for good (`abandoned`, or `unknown` in
`submitted_unconfirmed` when the employer may hold the application), and NoEfforts never runs
that application again. The receiver's own ledger is the oracle for what reached the employer:
POSTs are counted per page from its request log, values are read from its `draft_page` rows and
acceptances, never from NoEfforts' tables. Every wizard behaviour is a FIXTURE ASSUMPTION
(fixtures/ats_receiver/workday_like.py, FA1-FA5): passing here shows fixture compatibility only,
never how a real Workday tenant behaves. Synthetic candidate data only; rows edited by hand are
labelled simulated."""

import json
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application
from app.modules.applications.states import AppState
from app.modules.autoapply import service as autoapply
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.adapters.workday import ALREADY_APPLIED
from app.modules.execution.models import (
    ApplicationPause,
    AttemptEvent,
    Evidence,
    ExecutionAttempt,
)
from app.modules.identity.models import User
from app.modules.preparation import package as pk
from app.modules.preparation import workday
from app.modules.preparation.forms import extract_form_schema, form_fingerprint
from app.modules.preparation.models import ApprovalScope, PackageApproval
from tests.execution_harness import (
    BASE,
    Receiver,
    attempt,
    queue,
    run_worker_process,
    synthetic_candidate,
)
from tests.test_execution_failures import (
    expire_lease,
    reached,
    release,
    start_blocked_worker,
    wait_for,
)
from tests.test_workday_adapter import (
    REQ,
    TENANT,
    fresh_url,
    uploads,
    workday_application,
    workday_job,
)

# FA2: the pages in order (written here, not imported from the fixture: the oracle's own list).
PAGES = ["My Information", "My Experience", "Voluntary Disclosures", "Application Questions",
         "Review"]  # fmt: skip
CODE = "wizard_draft_at_employer"
WIZARD_RETIRED = svc.RETIRED[CODE]
ALL_STEPS = [(1, "next"), (2, "fill"), (2, "next"), (3, "fill"), (3, "next"), (4, "fill"),
             (4, "next")]  # fmt: skip
# Non-wizard fingerprints, computed on the base commit (2dfc956) before any D142 edit: the
# default Workday-style page (workday.extract_schema) and the generic receiver form
# (extract_form_schema with challenges, as the generic capture reads it).
WORKDAY_FP = "1e3b357fd97a51f2c75bf8d28b8762fbb52cf9422b15afe88b4c4299b536832e"
GENERIC_FP = "f9e4d38de881d9efb3008349816ca626a5c8dd026638e506f7203289a4132422"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


# ---------------------------------------------------------------------------- helpers


def wizard_application(api, receiver, variant="plain", **kw) -> str:
    """The wizard variant switched on, then a Workday-style application on a posting of its
    own, captured, answered and approved (`workday_application`)."""
    receiver.config(wizard=variant)
    return workday_application(api, url=fresh_url(), **kw)


def drafts(led) -> list[dict]:
    """The receiver's draft rows, oldest first: {page, form_token, fields}."""
    return [json.loads(d["detail"]) for d in led["disclosures"] if d["kind"] == "draft_page"]


def draft_pages(led) -> list[int]:
    return [d["page"] for d in drafts(led)]


def posts(led, suffix: str) -> int:
    """POSTs the receiver logged whose path ends with `suffix` ("/apply" is the final submit
    only: drafts end in "/draft/N" and uploads in "/files")."""
    return sum(1 for r in led["requests"] if r["method"] == "POST" and r["path"].endswith(suffix))


def ledger_kinds(led) -> list[tuple[str, object]]:
    out = []
    for d in led["disclosures"]:
        detail = json.loads(d["detail"]) if d["detail"] else {}
        out.append((d["kind"], detail.get("page", detail.get("field"))))
    return out


def events(aid: str, kind: str | None = None) -> list[AttemptEvent]:
    with SessionLocal() as db:
        q = select(AttemptEvent).where(AttemptEvent.attempt_id == uuid.UUID(aid))
        if kind:
            q = q.where(AttemptEvent.kind == kind)
        return list(db.scalars(q.order_by(AttemptEvent.created_at)))


def steps(aid: str) -> list[tuple[int, str]]:
    return [(e.detail["page"], e.detail["phase"]) for e in events(aid, "step_authorized")]


def rows(aid: str, kind: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        q = select(Evidence).where(Evidence.attempt_id == uuid.UUID(aid))
        if kind:
            q = q.where(Evidence.kind == kind)
        return [e.data for e in db.scalars(q.order_by(Evidence.created_at))]


def approvals(app_id: str) -> list[PackageApproval]:
    with SessionLocal() as db:
        return list(db.scalars(select(PackageApproval).where(
            PackageApproval.application_id == uuid.UUID(app_id))))  # fmt: skip


def all_retired_for_wizard(app_id: str) -> bool:
    found = approvals(app_id)
    return bool(found) and all(
        a.invalidated_at is not None and a.invalidation_reason == WIZARD_RETIRED for a in found
    )


def package(api, app_id: str) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def approve(api, app_id: str, scope: str | None = None):
    p = package(api, app_id)
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    return api.post(f"/applications/{app_id}/package/approve",
                    json=body | ({"scope": scope} if scope else {}))  # fmt: skip


def outcome_event(aid: str) -> AttemptEvent:
    (ev,) = [e for e in events(aid) if e.kind.startswith("outcome_")]
    return ev


def app_state(api, app_id: str) -> str:
    return api.get(f"/applications/{app_id}").json()["state"]


def reconcile_not_received(api, app_id: str):
    body = {"finding": "not_received", "confirm_not_received": True,
            "evidence": "Checked the employer's portal (synthetic): nothing there"}  # fmt: skip
    return api.post(f"/applications/{app_id}/reconcile", json=body)


def page_values(content: dict, page: str) -> dict:
    """What page `page`'s controls hold for the approved package, as the browser sends them:
    text and lists by value ("" when unanswered), a radio or box only when chosen, a document
    by its hidden handle (checked against the upload separately)."""
    out = {}
    for a in content["answers"]:
        if a["step"] != page:
            continue
        t, v = a["type"], a["value"]
        if t in ("text", "email", "tel", "url", "textarea"):
            out[a["key"]] = v["text"] if v else ""
        elif t == "select":
            out[a["key"]] = v["option"] if v else ""
        elif t == "radio" and v:
            out[a["key"]] = v["option"]
        elif t == "checkbox" and v and v["checked"]:
            out[a["key"]] = "1"
        elif t == "file":
            out[f"{a['key']}_attachment"] = None  # the upload's handle, compared on its own
    return out


def wizard_html(receiver) -> str:
    receiver.config(wizard="plain")
    return httpx.get(f"{BASE}/workday/{TENANT}/{REQ}/apply").text


# ---------------------------------------------------------------------------- capture


def test_capture_reads_every_page_with_its_step(api, receiver):
    receiver.config(wizard="plain")
    synthetic_candidate(api)
    job_id = workday_job(api, url=fresh_url())
    r = api.post(f"/jobs/{job_id}/form/workday")
    assert r.status_code == 201, r.text
    led = receiver.ledger()
    assert [(q["method"], q["path"].rsplit("/", 1)[-1]) for q in led["requests"]] == [
        ("GET", "apply")]  # fmt: skip
    assert led["disclosures"] == [] and led["accepted"] == 0
    schema = r.json()["schema"]
    keys = {f["key"] for f in schema["fields"]}
    assert not keys & {"multi_step", "prefilled_values", "bot_check", "form_token",
                       "resume_attachment", "cover_letter_attachment"}  # fmt: skip
    assert schema["wizard"] == {"pages": PAGES}
    assert {f["step"] for f in schema["fields"]} <= set(PAGES[:-1])
    by_page = {p: {f["key"] for f in schema["fields"] if f["step"] == p} for p in PAGES}
    assert {"legalName--firstName", "email", "aria:source"} <= by_page["My Information"]
    assert by_page["My Experience"] == {"resume", "cover_letter", "exp.details"}
    assert by_page["Voluntary Disclosures"] == {"vd.gender", "terms_ack"}
    assert by_page["Application Questions"] == {"q.work_eligibility", "q.sponsorship",
                                                "q.licence_type", "q.shift"}  # fmt: skip
    assert by_page["Review"] == set()
    route = api.get(f"/jobs/{job_id}/route").json()
    assert route["provider"] == "fixture_workday" and route["route"] != "checkpoint", route
    app_id = api.post("/applications", json={"job_id": job_id}).json()["id"]
    content = package(api, app_id)["content"]
    answers = {a["key"]: a for a in content["answers"]}
    assert answers["exp.details"]["status"] == "blank_optional"
    assert content["wizard"] == {"pages": PAGES}
    assert {a["step"] for a in content["answers"]} <= set(PAGES[:-1])


MUTATIONS = {
    # A question inside the form but on no page.
    "field_outside": (
        '<section data-step="My Information"',
        '<label for="x_out">Outside</label><input id="x_out" name="x.outside" type="text">'
        '<section data-step="My Information"',
    ),
    # The pages are not numbered 1 to 5 in order.
    "page_gap": ('<section data-step="Voluntary Disclosures" data-wizard-page="3" hidden>',
                 '<section data-step="Voluntary Disclosures" data-wizard-page="7" hidden>'),
    # The form says six pages; five are there (caught only if the count is read).
    "page_count": ('data-wizard-pages="5"', 'data-wizard-pages="6"'),
    # Pages 3 and 4 swapped: each page still has its Next (only the order catches it).
    "page_order": (
        '<section data-step="Voluntary Disclosures" data-wizard-page="3" hidden>',
        '<section data-step="Voluntary Disclosures" data-wizard-page="4" hidden>',
    ),
    # The submit button on page 4, none on the review page.
    "submit_not_last": (
        '<button type="submit" data-automation-id="bottom-navigation-next-button">Submit'
        "</button>",
        "",
    ),
    # Two Next buttons on page 2.
    "two_nexts": (
        '<input id="exp_details" name="exp.details" type="text">',
        '<input id="exp_details" name="exp.details" type="text">'
        '<button type="button" data-wizard-next>Next</button>',
    ),
    # A step nested inside a page (with no question in it: only rule 3 can catch it).
    "nested_step": (
        '<label for="vd_gender">Gender</label>',
        '<div data-step="Self Identify"></div><label for="vd_gender">Gender</label>',
    ),
    # The several-pages marker of D88 beside the wizard's.
    "mixed_markers": (
        "<p>Apply Manually</p>",
        "<p>Apply Manually</p><div data-workday-progress>Step 1 of 4: My Information</div>",
    ),
}


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_a_malformed_wizard_is_a_checkpoint(receiver, mutation):
    html = wizard_html(receiver)
    good = workday.extract_schema(html)
    assert good.wizard is not None and good.wizard.pages == PAGES
    assert "multi_step" not in {f.key for f in good.fields}
    old, new = MUTATIONS[mutation]
    assert html.count(old) == 1
    bad = html.replace(old, new)
    if mutation == "page_order":  # ... and page 4 numbered 3
        page4 = '<section data-step="Application Questions" data-wizard-page="4" hidden>'
        assert bad.count(page4) == 1
        bad = bad.replace(page4, page4.replace('"4"', '"3"'))
    if mutation == "submit_not_last":  # ... and put it on page 4, beside its Next
        page4 = '<section data-step="Application Questions" data-wizard-page="4" hidden>'
        assert bad.count(page4) == 1
        bad = bad.replace(page4, page4 + '<button type="submit">Submit</button>')
    schema = workday.extract_schema(bad)
    assert schema.wizard is None
    field = {f.key: f for f in schema.fields}.get("multi_step")
    assert field is not None and field.type.value == "unsupported" and field.required


def test_non_wizard_fingerprints_are_unchanged(receiver):
    receiver.config(wizard=None)
    page = httpx.get(f"{BASE}/workday/{TENANT}/{REQ}/apply").text
    assert form_fingerprint(workday.extract_schema(page)) == WORKDAY_FP
    generic = httpx.get(f"{BASE}/apply/clinic").text
    assert form_fingerprint(extract_form_schema(generic, challenges=True)) == GENERIC_FP
    assert "wizard" not in workday.extract_schema(page).model_dump(mode="json")


# ---------------------------------------------------------------------------- full run


def test_each_page_is_sent_once_in_order_then_submitted(api, receiver):
    app_id = wizard_application(api, receiver)
    content = package(api, app_id)["content"]
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    # Each page once, in order, the document on its own page; then one final submit.
    assert ledger_kinds(led) == [("draft_page", 1), ("upload", "resume"), ("draft_page", 2),
                                 ("draft_page", 3), ("draft_page", 4)]  # fmt: skip
    assert [posts(led, f"/apply/draft/{i}") for i in (1, 2, 3, 4)] == [1, 1, 1, 1]
    assert posts(led, "/apply/draft/5") == 0 and posts(led, "/apply") == 1
    assert led["accepted"] == 1
    # Each draft holds exactly that page's approved values (its document by its handle).
    upload_id = uploads(led)[0]["upload_id"]
    merged = {}
    for d in drafts(led):
        want = page_values(content, PAGES[d["page"] - 1])
        if d["page"] == 2:
            want |= {"resume_attachment": upload_id, "cover_letter_attachment": ""}
        assert d["fields"] == want, d["page"]
        merged |= d["fields"]
    assert merged["legalName--firstName"] == "Sam" and merged["q.licence_type"] == "RN"
    # What was submitted is what the pages saved.
    assert led["acceptances"][0]["fields"] == merged
    # A gate before every step, in order, all before the send gate.
    assert steps(aid) == ALL_STEPS
    kinds = [e.kind for e in events(aid)]
    assert kinds.index("send_authorized") > max(
        i for i, k in enumerate(kinds) if k == "step_authorized")  # fmt: skip
    assert kinds.index("disclosure_authorized") < kinds.index("step_authorized")
    # Evidence: one step row per page before its Next, then one readback and one recheck.
    step_rows = rows(aid, "step")
    assert [s["page"] for s in step_rows] == [1, 2, 3, 4]
    assert all(set(s) == {"page", "checked", "mismatched"} and s["mismatched"] == 0
               for s in step_rows)  # fmt: skip
    assert [s["checked"] for s in step_rows] == sorted(s["checked"] for s in step_rows)
    assert len(rows(aid, "readback")) == 1 and len(rows(aid, "recheck")) == 1
    assert rows(aid, "readback")[0]["mismatched"] == 0
    sent = [d for d in rows(aid, "disclosure") if d.get("kind") == "draft_page"]
    assert sent == [{"kind": "draft_page", "page": i, "ack": "draft_saved"} for i in (1, 2, 3, 4)]
    every = json.dumps(rows(aid))
    assert not [v for v in ("Sam", "Synthetic", "@example.com", "Nights", "+1 555")
                if v in every]  # fmt: skip
    assert app_state(api, app_id) == "submitted_confirmed"


def test_a_page_is_read_back_before_its_next(api, receiver):
    """The contract scenario (each_step_read_back_before_next): a resume upload on page 2 fills
    the optional page-2 field NoEfforts leaves unanswered; the page's readback, which covers
    unanswered fields, stops before its Next."""
    app_id = wizard_application(api, receiver, "parse_current_page")
    aid = queue(api, app_id)
    assert attempt(aid).adapter == "fixture_workday"
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    assert draft_pages(led) == [1] and [u["field"] for u in uploads(led)] == ["resume"]
    assert posts(led, "/apply/draft/2") == 0 and posts(led, "/apply") == 0
    assert led["accepted"] == 0
    by_page = {s["page"]: s for s in rows(aid, "step")}
    assert by_page[1]["mismatched"] == 0 and by_page[2]["mismatched"] >= 1
    assert steps(aid) == ALL_STEPS[:2]  # page 2's Next was never authorized
    a = attempt(aid)
    assert a.state == "abandoned" and "multi-page form" in a.outcome_detail
    assert all_retired_for_wizard(app_id)
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]


def test_a_saved_page_that_changes_is_never_sent_on(api, receiver):
    """A resume upload on page 2 overwrites page-1 fields already saved: the readback before
    page 2's Next covers every page so far, so nothing more is sent."""
    app_id = wizard_application(api, receiver, "parse_saved_page")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    led = receiver.ledger()
    (first,) = drafts(led)
    assert first["page"] == 1 and first["fields"]["legalName--firstName"] == "Sam"
    assert posts(led, "/apply/draft/2") == 0 and posts(led, "/apply") == 0
    assert led["accepted"] == 0
    assert {s["page"]: s["mismatched"] for s in rows(aid, "step")}[2] >= 1


# ---------------------------------------------------------------------------- between pages


def _profile_edit(api) -> None:
    prof = api.get("/profile").json()
    keep = {k: prof[k] for k in ("full_name", "given_name", "family_name", "contact_email",
                                 "residence_country", "residence_city", "links")}  # fmt: skip
    r = api.put("/profile", json=keep | {"phone": "+1 555 0199"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    ("change", "point"),
    [("revoke", "before_fill_gate_2"), ("revoke", "before_next_gate_2"),
     ("profile_edit", "before_next_gate_2"), ("cancel", "before_next_gate_2"),
     ("profile_edit", "before_send_gate")],
    ids=["revoke@fill2", "revoke@next2", "profile_edit@next2", "cancel@next2", "profile_edit@send"],
)  # fmt: skip
def test_a_change_between_pages_stops_at_the_next_gate(api, receiver, change, point):
    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    p, gate = start_blocked_worker(aid, "w1", point)
    try:
        wait_for(lambda: reached(gate), timeout=60)
        if change == "revoke":
            r = api.post(f"/applications/{app_id}/package/revoke")
            assert r.status_code == 200 and r.json()["revoke_effect"] == "stopping", r.text
        elif change == "profile_edit":
            _profile_edit(api)
        else:
            r = api.post(f"/applications/{app_id}/transition", json={"to": "cancelled"})
            assert r.status_code == 200, r.text
    finally:
        result = release(p, gate)
    led = receiver.ledger()
    assert led["accepted"] == 0 and posts(led, "/apply") == 0
    if point == "before_fill_gate_2":
        assert draft_pages(led) == [1] and uploads(led) == []
    elif point == "before_next_gate_2":
        assert draft_pages(led) == [1] and [u["field"] for u in uploads(led)] == ["resume"]
        assert posts(led, "/apply/draft/2") == 0
    else:
        assert draft_pages(led) == [1, 2, 3, 4]
    a = attempt(aid)
    if change == "cancel":
        assert result == "lost_authority" and a.state == "cancelled"
        return
    assert result == "abandoned" and a.state == "abandoned"
    assert "multi-page form" in a.outcome_detail
    if change == "profile_edit":
        assert all_retired_for_wizard(app_id)
    assert all(x.invalidated_at is not None for x in approvals(app_id))
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]


def test_a_lost_worker_mid_wizard_is_never_taken_over(api, receiver):
    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    p, gate = start_blocked_worker(aid, "w1", "before_next_gate_2")
    try:
        wait_for(lambda: reached(gate), timeout=60)
        expire_lease(aid)
        assert svc.sweep()["abandoned"] == 1
    finally:
        result = release(p, gate)
    assert result == "lost_authority"
    a = attempt(aid)
    assert a.state == "abandoned" and a.retry_count == 0
    assert a.outcome_detail == svc.WIZARD_SWEPT
    assert all_retired_for_wizard(app_id)
    led = receiver.ledger()
    assert posts(led, "/apply/draft/2") == 0 and led["accepted"] == 0
    assert draft_pages(led) == [1]


def test_a_worker_killed_after_a_next_leaves_its_record(api, receiver):
    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    r = run_worker_process(aid, "w1", fault="after_next_ack_2=exit")
    assert r.returncode == 137
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2] and led["accepted"] == 0
    # The gate's event was committed before the click; the page's evidence never was.
    assert (2, "next") in steps(aid)
    assert [d["page"] for d in rows(aid, "disclosure") if d.get("kind") == "draft_page"] == [1]
    expire_lease(aid)
    assert svc.sweep()["abandoned"] == 1
    assert attempt(aid).state == "abandoned"
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    assert runner.run_attempt(aid, "w2") == "ignored"
    assert receiver.ledger()["requests"] == led["requests"]


# ---------------------------------------------------------------------------- after a Next


@pytest.mark.parametrize("variant", ["step_error", "step_timeout", "late_question"])
def test_a_next_is_never_clicked_twice(api, receiver, monkeypatch, variant):
    app_id = wizard_application(api, receiver, variant)
    aid = queue(api, app_id)
    if variant == "step_timeout":
        monkeypatch.setattr(get_settings(), "navigation_timeout_seconds", 3)
        receiver.config(delay_s=10)
    assert runner.run_attempt(aid, "w1") == "abandoned"
    if variant == "step_timeout":
        time.sleep(3)  # a window for any late second click to show in the ledger
    led = receiver.ledger()
    assert posts(led, "/apply/draft/2") == 1 and posts(led, "/apply/draft/3") == 0
    assert posts(led, "/apply") == 0 and led["accepted"] == 0
    a = attempt(aid)
    assert a.state == "abandoned"  # never rejected, confirmed or unknown
    assert steps(aid) == ALL_STEPS[:3]
    ack = {"step_error": "error_shown", "step_timeout": "none", "late_question": "draft_saved"}
    assert [d for d in rows(aid, "disclosure") if d.get("kind") == "draft_page"][-1] == {
        "kind": "draft_page", "page": 2, "ack": ack[variant]}  # fmt: skip
    with SessionLocal() as db:
        assert db.scalars(select(ApplicationPause).where(
            ApplicationPause.application_id == uuid.UUID(app_id))).all() == []  # fmt: skip
    assert all_retired_for_wizard(app_id)


@pytest.mark.parametrize("variant", ["next_submits", "already_applied_after_next"])
def test_a_next_that_may_have_submitted_is_quarantined(api, receiver, variant):
    receiver.config(idempotent=False)  # every acceptance counts: a second one would show
    app_id = wizard_application(api, receiver, variant)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    led = receiver.ledger()
    assert led["accepted"] == (1 if variant == "next_submits" else 0)
    assert posts(led, "/apply") == 0
    assert draft_pages(led) == ([1, 2, 3, 4] if variant == "next_submits" else [1])
    a = attempt(aid)
    assert a.state == "unknown" and "may hold this application" in a.outcome_detail
    assert outcome_event(aid).detail["reason_code"] == "wizard_possibly_submitted"
    assert app_state(api, app_id) == "submitted_unconfirmed"
    assert all_retired_for_wizard(app_id)
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = reconcile_not_received(api, app_id)
    assert r.status_code == 200 and r.json()["state"] == "failed_retryable", r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    after = receiver.ledger()
    assert after["accepted"] == led["accepted"] and after["requests"] == led["requests"]


# ---------------------------------------------------------------------------- before disclosure


@pytest.mark.parametrize("case", ["drift", "already_applied", "rehearsal"])
def test_stops_before_disclosure_leave_no_mark(api, receiver, case):
    if case == "rehearsal":
        app_id = wizard_application(api, receiver, approve=False)
        r = approve(api, app_id, scope="disclose_only")
        assert r.status_code == 409
        assert "(reason: wizard_rehearsal_unsupported)" in r.json()["detail"]
        assert approve(api, app_id).status_code == 200
        with SessionLocal() as db:  # simulated: a scope no approval route gives a wizard
            db.execute(update(PackageApproval)
                       .where(PackageApproval.application_id == uuid.UUID(app_id))
                       .values(scope=ApprovalScope.disclose_only))  # fmt: skip
            db.commit()
        aid = queue(api, app_id)
    else:
        app_id = wizard_application(api, receiver)
        aid = queue(api, app_id)
        receiver.config(wizard=case)
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert [q for q in led["requests"] if q["method"] == "POST"] == []
    a = attempt(aid)
    assert a.state == "failed_safe" and a.disclosure_started_at is None
    assert steps(aid) == []
    if case == "drift":
        with SessionLocal() as db:
            pause = db.scalar(select(ApplicationPause).where(
                ApplicationPause.application_id == uuid.UUID(app_id)))  # fmt: skip
        assert pause is not None and pause.kind == "form_changed" and pause.status == "open"
        r = approve(api, app_id)
        assert r.status_code == 409 and "(reason: form_recapture_needed)" in r.json()["detail"]
    elif case == "already_applied":
        assert ALREADY_APPLIED in a.outcome_detail
        assert approve(api, app_id).status_code == 200  # nothing was entered: not refused
    else:
        assert outcome_event(aid).detail["reason_code"] == "wizard_rehearsal"


def test_once_entered_it_never_runs_again(api, receiver, monkeypatch):
    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "after_disclosure_gate=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    monkeypatch.delenv("NOEFFORTS_FAULT")
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert [q for q in led["requests"] if q["method"] == "POST"] == []
    assert attempt(aid).state == "abandoned" and attempt(aid).disclosure_started_at is not None
    assert all_retired_for_wizard(app_id)
    # 1. Approving, on its own page and on the review page.
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    p = package(api, app_id)
    item = {"application_id": app_id, "version": p["version"], "content_hash": p["content_hash"],
            "scope": "submit"}  # fmt: skip
    batch = api.post("/review/approve", json={"items": [item]})
    assert batch.status_code == 200, batch.text
    assert batch.json()["results"][0]["status"] == "refused"
    assert batch.json()["results"][0].get("reason_code") == CODE
    assert all(a.invalidated_at is not None for a in approvals(app_id))
    # The record is the attempt and its package, never the evidence: deleting it changes nothing.
    assert api.delete(f"/applications/{app_id}/evidence").status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(Evidence).where(
            Evidence.application_id == uuid.UUID(app_id))).all() == []  # fmt: skip
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    # 2. An approval restored by hand (simulated): approving is still refused, before the
    # shortcut that returns a live approval, and queueing is refused, on the route and in
    # enqueue itself.
    with SessionLocal() as db:
        restored = db.scalars(select(PackageApproval).where(
            PackageApproval.application_id == uuid.UUID(app_id))).first()  # fmt: skip
        restored.invalidated_at, restored.invalidation_reason = None, None
        restored.expires_at = utcnow() + timedelta(hours=1)
        restored_id = restored.id
        db.commit()
    r = approve(api, app_id)
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(app_id))
        with pytest.raises(pk.ApprovalError) as e:
            svc.enqueue(db, app)
        assert e.value.code == CODE
        db.rollback()
        # The standing rule's queueing calls this check itself (autoapply/service.py).
        with pytest.raises(pk.ApprovalError) as e:
            pk.require_valid_approval(db, app)
        assert e.value.code == CODE
        db.rollback()
    # 3. A pending attempt inserted by hand (simulated) is refused when a worker claims it.
    before = receiver.ledger()["requests"]
    with SessionLocal() as db:
        old = db.get(ExecutionAttempt, uuid.UUID(aid))
        new = ExecutionAttempt(
            application_id=old.application_id,
            user_id=old.user_id,
            package_id=old.package_id,
            package_hash=old.package_hash,
            approval_id=restored_id,
            adapter=old.adapter,
            destination_class=old.destination_class,
            path_ref=old.path_ref,
        )
        db.add(new)
        db.get(Application, uuid.UUID(app_id)).state = AppState.queued
        db.commit()
        new_id = str(new.id)
    assert runner.run_attempt(new_id, "w2") == "ignored"
    assert attempt(new_id).state == "failed_safe"
    assert [e.kind for e in events(new_id)] == ["claim_refused_wizard_draft"]
    assert receiver.ledger()["requests"] == before


def test_another_account_on_the_same_posting_is_not_refused(api, other_api, receiver,
                                                             monkeypatch):  # fmt: skip
    url = fresh_url()
    receiver.config(wizard="plain")
    app_id = workday_application(api, url=url)
    aid = queue(api, app_id)
    monkeypatch.setenv("NOEFFORTS_FAULT", "after_disclosure_gate=raise")
    assert runner.run_attempt(aid, "w1") == "error"
    monkeypatch.delenv("NOEFFORTS_FAULT")
    assert attempt(aid).disclosure_started_at is not None
    led = receiver.ledger()
    # Another account, the same posting: its own application is not refused.
    theirs = workday_application(other_api, url=url, approve=False)
    assert approve(other_api, theirs).status_code == 200
    # The same account, another posting: its own application is not refused.
    second = workday_application(api, url=fresh_url(), title="Charge Nurse", approve=False)
    assert approve(api, second).status_code == 200
    # ... and it reaches nothing of the first account's.
    p = package(api, app_id)
    body = {"version": p["version"], "content_hash": p["content_hash"]}
    assert other_api.post(f"/applications/{app_id}/package/approve", json=body).status_code == 404
    assert other_api.get(f"/applications/{app_id}/attempts").status_code == 404
    r = other_api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 404
    # Nothing more was sent to the first account's posting (the other account's capture of it is
    # one GET of its own).
    after = receiver.ledger()
    sent = [q for q in after["requests"] if q["method"] != "GET"]
    assert sent == [q for q in led["requests"] if q["method"] != "GET"] == []
    assert after["disclosures"] == led["disclosures"] == [] and after["accepted"] == 0


def test_an_unknown_final_click_on_a_wizard_is_quarantined_and_never_rerun(api, receiver):
    app_id = wizard_application(api, receiver)
    receiver.config(mode="drop_after_accept")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    led = receiver.ledger()
    assert draft_pages(led) == [1, 2, 3, 4] and led["accepted"] == 1
    assert attempt(aid).state == "unknown"
    assert app_state(api, app_id) == "submitted_unconfirmed"
    assert runner.run_attempt(aid, "w2") == "ignored"
    r = reconcile_not_received(api, app_id)
    assert r.status_code == 200, r.text
    r = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert r.status_code == 409 and f"(reason: {CODE})" in r.json()["detail"]
    assert receiver.ledger()["accepted"] == 1


def test_the_standing_rule_never_drives_a_wizard(api, receiver, monkeypatch):
    app_id = wizard_application(api, receiver)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "synthetic.user@example.com"))
        job_id = db.get(Application, uuid.UUID(app_id)).job_id
        assert job_id not in {j.id for j in autoapply._candidates(db, user)}
    # The rule switched on for this account (test settings), so only the wizard guard stops it.
    monkeypatch.setattr(get_settings(), "auto_apply_enabled", True)
    monkeypatch.setattr(autoapply, "paused", lambda db, user: False)
    aid = queue(api, app_id)
    with SessionLocal() as db:  # simulated: as if the standing rule had queued it
        db.execute(update(ExecutionAttempt).where(ExecutionAttempt.id == uuid.UUID(aid))
                   .values(queued_by_rule=True))  # fmt: skip
        db.commit()
    before = receiver.ledger()["requests"]
    assert svc.claim(uuid.UUID(aid), "w1") is None
    assert runner.run_attempt(aid, "w1") == "ignored"
    assert attempt(aid).state == "failed_safe"
    assert "claim_refused_rule_wizard" in [e.kind for e in events(aid)]
    assert receiver.ledger()["requests"] == before


# ---------------------------------------------------------------------------- the step gate


def _claimed_and_disclosed(api, receiver, worker: str, **kw) -> tuple[str, str, int]:
    app_id = wizard_application(api, receiver, **kw)
    aid = queue(api, app_id)
    gen = svc.claim(uuid.UUID(aid), worker)
    assert gen is not None
    svc.gate_before_disclosure(uuid.UUID(aid), worker, gen)
    return app_id, aid, gen


def test_the_step_gate_is_fenced_and_ordered(api, receiver):
    app_id = wizard_application(api, receiver)
    aid = queue(api, app_id)
    a = uuid.UUID(aid)
    gen = svc.claim(a, "w1")
    with pytest.raises(svc.GateRefused) as e:  # before the disclosure gate
        svc.gate_before_step(a, "w1", gen, 1, "next")
    assert e.value.code == "wizard_step_order"
    svc.gate_before_disclosure(a, "w1", gen)
    stamped = attempt(aid).disclosure_started_at
    for worker, g in (("w1", gen - 1), ("w2", gen)):  # a stale generation, another worker
        with pytest.raises(svc.LostAuthority):
            svc.gate_before_step(a, worker, g, 1, "next")
    for page, phase in ((2, "fill"), (1, "fill"), (1, "skip")):  # out of order
        with pytest.raises(svc.GateRefused) as e:
            svc.gate_before_step(a, "w1", gen, page, phase)
        assert e.value.code == "wizard_step_order"
    svc.gate_before_step(a, "w1", gen, 1, "next")
    with pytest.raises(svc.GateRefused) as e:  # page 1 twice
        svc.gate_before_step(a, "w1", gen, 1, "next")
    assert e.value.code == "wizard_step_order"
    assert steps(aid) == [(1, "next")]
    assert [e.detail for e in events(aid, "step_authorized")] == [
        {"page": 1, "phase": "next", "pages": 5}]  # fmt: skip
    with SessionLocal() as db:  # an expired lease
        db.get(ExecutionAttempt, a).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    with pytest.raises(svc.LostAuthority):
        svc.gate_before_step(a, "w1", gen, 2, "fill")
    with SessionLocal() as db:
        db.get(ExecutionAttempt, a).lease_expires_at = utcnow() + timedelta(minutes=5)
        db.commit()
    assert svc.pause_after_entry(a, "w1", gen, "a question", 1) is False
    svc.gate_before_send(a, "w1", gen)
    with pytest.raises(svc.LostAuthority):  # after the send gate
        svc.gate_before_step(a, "w1", gen, 2, "fill")
    assert steps(aid) == [(1, "next")]
    assert attempt(aid).disclosure_started_at == stamped
    # A package that is not a wizard: the step gate refuses it.
    receiver.config(wizard=None)
    plain = workday_application(api, url=fresh_url(), title="Charge Nurse")
    pa = uuid.UUID(queue(api, plain))
    pgen = svc.claim(pa, "w3")
    svc.gate_before_disclosure(pa, "w3", pgen)
    with pytest.raises(svc.GateRefused) as e:
        svc.gate_before_step(pa, "w3", pgen, 1, "next")
    assert e.value.code == "wizard_step_order"
    assert steps(str(pa)) == []
    # fail_safe on a disclosed wizard never says "before sending anything": it abandons.
    _, other, ogen = _claimed_and_disclosed(api, receiver, "w4", title="Clinic Nurse")
    assert svc.fail_safe(uuid.UUID(other), "w4", ogen, "a late check") is True
    o = attempt(other)
    assert o.state == "abandoned" and not o.outcome_detail.startswith("Stopped before sending")
    assert "multi-page form" in o.outcome_detail
    # Nothing but the captures reached the receiver.
    reqs = receiver.ledger()["requests"]
    assert reqs and all(q["method"] == "GET" and q["path"].endswith("/apply") for q in reqs)

