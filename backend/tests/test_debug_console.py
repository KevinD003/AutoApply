"""D168: the owner's console (app/modules/debug) and sole-owner mode.

The console reads what NoEfforts already keeps and changes nothing: one application from
discovery to its outcome (`/debug/applications/{id}`), what happened across the account's jobs
(`/debug/activity`), and the server's switches as they apply to the signed-in account
(`/debug/system`), each judged by the gate that decides it. Every query is scoped to the account
(another account's application is a 404), it is app-only (never an API token), and it never
returns a secret: no verification code, token, key, password or keyed reference; which settings
are missing and the recorded permissions go to the server's owner alone.

Sole-owner mode (the owner's words, 2026-11-17: "treat any account I use new or existing as the
owner"): on by default outside tests, every account is served and is the owner's: automatic
applying on unless the account pauses it, one daily cap for all of them, the Gmail features with
each account reading only a mailbox it connected itself. No other gate changes. Local stand-ins
only, synthetic data only."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core import authorizations
from app.core.config import Settings, get_settings
from app.core.db import Base, SessionLocal, utcnow
from app.modules.autoapply.models import AutoApplyEvent
from app.modules.debug import service as console
from app.modules.execution import runner
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from app.modules.identity.models import User
from app.modules.preparation.models import PackageApproval
from tests.authorized import authorize
from tests.execution_harness import Receiver, pilot_on, queue, synthetic_candidate
from tests.test_api_tokens import bearer, make
from tests.test_workday_experience import experience_application

ME, OTHER = "synthetic.user@example.com", "another.synthetic@example.com"  # conftest's accounts


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def submitted(api, receiver) -> tuple[str, str]:
    """A Workday-style application on the single page, approved, run and confirmed by the
    receiver; (its id, its attempt's id)."""
    app_id = experience_application(api, receiver, single=True)
    att = queue(api, app_id)
    assert runner.run_attempt(att, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    return app_id, att


def trace(api, app_id: str) -> dict:
    r = api.get(f"/debug/applications/{app_id}")
    assert r.status_code == 200, r.text
    return r.json()


def user(email: str) -> User:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).one()


def feature(view: dict, key: str) -> dict:
    return next(f for f in view["features"] if f["key"] == key)


# ---------------------------------------------------------------- one application, start to finish


def test_a_submitted_application_is_traced_from_capture_to_its_receipt(api, receiver):
    app_id, att = submitted(api, receiver)
    t = trace(api, app_id)
    state = api.get(f"/applications/{app_id}").json()["state"]
    assert t["application"]["state"] == state == "submitted_confirmed"
    assert t["job"]["title"] and t["job"]["url"]
    (capture,) = t["captures"]
    assert capture["fields"] > 0 and capture["checkpoints"] == []
    assert capture["set_by_the_page"] == []
    # The stand-in's optional "How did you hear about us?" combobox: left empty, not a checkpoint.
    assert [c["key"] for c in capture["left_empty"]] == ["aria:source"]
    assert [s["kind"] for s in capture["sections"]] == ["employment"]
    last = t["packages"][-1]
    assert last["unresolved"] == [] and last["validation_errors"] == []
    first = next(a for a in last["answers"] if a["key"] == "legalName--firstName")
    assert first["display"] == "Sam" and first["status"] == "resolved"
    assert all(set(a) <= set(console._ANSWER_KEYS) for a in last["answers"])  # never `value`
    assert last["sections"] == [{"kind": "employment", "step": None, "rows": 2}]
    assert last["destination"]["origin"] and last["destination"]["submit_url"]
    approval = t["approvals"][-1]
    assert approval["by_rule"] is False and approval["package_version"] == last["version"]
    (attempt,) = t["attempts"]
    assert (attempt["id"], attempt["state"], attempt["rehearsal"]) == (att, "confirmed", False)
    assert attempt["disclosure_started_at"] and attempt["send_started_at"]
    assert attempt["finished_at"] and attempt["events"]
    assert "receipt" in {e["kind"] for e in attempt["evidence"]}
    assert "queued" in {s["to_state"] for s in t["state_changes"]}
    assert t["state_changes"][-1]["to_state"] == "submitted_confirmed"


def test_the_timeline_puts_every_step_in_order(api, receiver):
    app_id, _ = submitted(api, receiver)
    tl = trace(api, app_id)["timeline"]
    stages = [e["stage"] for e in tl]
    for stage in ("discovery", "capture", "package", "approval", "state", "attempt", "audit"):
        assert stage in stages, stage
    what = [e["what"] for e in tl]

    def first(prefix):
        return next(i for i, w in enumerate(what) if w.startswith(prefix))

    steps = ("Job added (", "Form read", "Approved by you", "Filling started on the employer's",
             "Final click (send) started", "Attempt ended: confirmed")  # fmt: skip
    order = [first(p) for p in steps]
    assert order == sorted(order)


def test_the_timeline_orders_by_the_moment_not_by_how_the_time_is_written():
    """Two steps whose times carry different offsets: the earlier moment first, whatever their
    text says (as text, "10:30+02:00" sorts after "09:00+00:00" though it is 08:30 UTC)."""
    late = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
    early = datetime(2026, 11, 17, 10, 30, tzinfo=timezone(timedelta(hours=2)))  # 08:30 UTC
    t = {k: [] for k in ("discovery", "captures", "packages", "drafts", "approvals", "rule",
                         "state_changes", "attempts", "pauses", "emails")}  # fmt: skip
    t["job"] = {"first_seen_at": None, "source": "manual"}
    t["audit"] = [{"at": late.isoformat(), "action": "later"},
                  {"at": early.isoformat(), "action": "earlier"}]  # fmt: skip
    tl = console._timeline(t, utcnow())
    assert [e["what"] for e in tl] == ["earlier", "later"]


def test_what_the_standing_rule_decided_is_in_the_trace_with_its_words(api, receiver):
    app_id = experience_application(api, receiver, single=True, approved=False)
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    with SessionLocal() as db:
        db.add(AutoApplyEvent(user_id=user(ME).id, job_id=uuid.UUID(job_id),
                              application_id=uuid.UUID(app_id), action="skipped",
                              reason="open_questions"))  # fmt: skip
        db.commit()
    (event,) = trace(api, app_id)["rule"]
    assert (event["action"], event["reason"]) == ("skipped", "open_questions")
    assert event["words"].startswith("Some questions need your answer")


def test_a_rehearsal_is_named_by_what_its_approval_allowed(api, receiver):
    """Whether an attempt was a rehearsal is its approval's scope (one that failed leaves no
    rehearsal record), in the trace, its timeline and the activity list."""
    app_id, att = submitted(api, receiver)
    with SessionLocal() as db:
        a = db.get(ExecutionAttempt, uuid.UUID(att))
        db.get(PackageApproval, a.approval_id).scope = "disclose_only"
        db.commit()
    t = trace(api, app_id)
    assert t["attempts"][0]["rehearsal"] is True
    what = [e["what"] for e in t["timeline"]]
    assert any(w.startswith("Rehearsal ended: confirmed") for w in what)
    assert not any(w.startswith("Attempt ") for w in what)
    items = api.get("/debug/activity").json()["items"]
    assert any(i["what"].startswith("Rehearsal ended: confirmed") for i in items)


def test_a_form_read_names_its_checkpoints_what_the_page_sets_and_what_is_left_empty():
    """A required control NoEfforts cannot fill is a checkpoint; a location search's value is
    the page's; an optional control and an optional phone left blank are left empty."""
    from types import SimpleNamespace

    def f(key, required, widget=None):
        return {"key": key, "label": key, "type": "unsupported", "required": required,
                "widget": widget, "unsupported_reason": "r"}  # fmt: skip

    form = SimpleNamespace(version=1, captured_at=None, source="x", extraction_version="v",
                           fingerprint="f" * 64, schema={"fields": [
                               f("custom", True), f("optional", False),
                               f("located", True, "location_structured"),
                               {"key": "phone", "label": "Phone", "type": "tel",
                                "widget": "phone_left_blank", "required": False}]})  # fmt: skip
    c = console._capture(form)
    assert [x["key"] for x in c["checkpoints"]] == ["custom"]
    assert [x["key"] for x in c["set_by_the_page"]] == ["located"]
    assert [x["key"] for x in c["left_empty"]] == ["optional", "phone"]


def test_a_verification_code_never_appears(api, receiver):
    app_id, att = submitted(api, receiver)
    with SessionLocal() as db:
        a = db.get(ExecutionAttempt, uuid.UUID(att))
        db.add(Checkpoint(attempt_id=a.id, application_id=a.application_id, user_id=a.user_id,
                          code="424242", status="submitted",
                          expires_at=utcnow() + timedelta(minutes=10)))  # fmt: skip
        db.commit()
    r = api.get(f"/debug/applications/{app_id}")
    assert "424242" not in r.text
    (cp,) = r.json()["attempts"][0]["checkpoints"]
    assert (cp["kind"], cp["status"]) == ("email_code", "submitted") and "code" not in cp


def test_another_account_s_application_is_a_404(api, other_api, receiver):
    app_id, _ = submitted(api, receiver)
    synthetic_candidate(other_api)
    assert other_api.get(f"/debug/applications/{app_id}").status_code == 404
    assert other_api.get(f"/debug/applications/{uuid.uuid4()}").status_code == 404


def test_a_private_note_and_the_keyed_references_are_never_served(api, receiver):
    """An outcome's note is the owner's (the application's own page shows it); an email's message
    and thread references and an attempt's path reference are keyed digests: none is served."""
    from app.modules.inbox.models import InboxEvent

    app_id, att = submitted(api, receiver)
    note = {"outcome": "interviewing", "evidence_note": "private marker note 7781"}
    r = api.patch(f"/applications/{app_id}", json=note)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        a = db.get(ExecutionAttempt, uuid.UUID(att))
        a.path_ref = "pathrefmarker0001"
        db.add(InboxEvent(user_id=user(ME).id, message_ref="msgrefmarker0002",
                          thread_ref="thrrefmarker3", received_at=utcnow(),
                          sender_domain="example.com", kind="received", state="noted",
                          application_id=uuid.UUID(app_id)))  # fmt: skip
        db.commit()
    r = api.get(f"/debug/applications/{app_id}")
    assert r.status_code == 200, r.text
    for marker in ("private marker note 7781", "pathrefmarker0001", "msgrefmarker0002",
                   "thrrefmarker3"):  # fmt: skip
        assert marker not in r.text, marker
    t = r.json()
    assert t["state_changes"][-1]["to_outcome"] == "interviewing"
    assert [(e["sender_domain"], e["kind"]) for e in t["emails"]] == [("example.com", "received")]
    items = api.get("/debug/activity").json()["items"]
    assert any(i["stage"] == "email" for i in items)
    assert "msgrefmarker0002" not in json.dumps(items)


def test_no_keyed_reference_is_served(api, receiver):
    """The audit log keeps a question's key as a keyed reference (audit/service.ref), and the
    export's scrubbing leaves out any other: opaque, and never served by the console, while the
    step itself is."""
    from app.modules.audit.models import AuditEvent
    from app.modules.audit.service import REF_PREFIX, record

    app_id, att = submitted(api, receiver)
    with SessionLocal() as db:
        record(db, user(ME).id, "application.answer", "application", app_id, field="q_custom_1",
               reason_code="synthetic")  # fmt: skip
        a = db.get(ExecutionAttempt, uuid.UUID(att))
        db.add(AuditEvent(user_id=a.user_id, action="synthetic.legacy", entity_type="attempt",
                          entity_id=att, meta={"nested": {"value_digest": "d" * 64},
                                               "old": "ref:" + "a" * 12}))  # fmt: skip
        db.commit()
        stored = db.query(AuditEvent).filter(AuditEvent.action == "application.answer").all()
        assert any(str(m.meta.get("field_ref", "")).startswith(REF_PREFIX) for m in stored)
    t = trace(api, app_id)
    answered = [e for e in t["audit"] if e["action"] == "application.answer"]
    assert any(e["meta"].get("reason_code") == "synthetic" for e in answered)
    text = json.dumps(t)
    for marker in (REF_PREFIX, "field_ref", "d" * 64, "ref:" + "a" * 12):
        assert marker not in text, marker


def test_the_console_changes_nothing(api, receiver):
    """Reading every page of the console writes no row anywhere."""
    app_id, _ = submitted(api, receiver)

    def counts():
        with SessionLocal() as db:
            return {t.name: db.scalar(select(func.count()).select_from(t))
                    for t in Base.metadata.sorted_tables}  # fmt: skip

    before = counts()
    for url in ("/debug/system", "/debug/activity", f"/debug/applications/{app_id}"):
        assert api.get(url).status_code == 200, url
    assert counts() == before


# ---------------------------------------------------------------- across the account's jobs


def test_activity_lists_this_account_s_steps_newest_first(api, receiver):
    app_id, _ = submitted(api, receiver)
    items = api.get("/debug/activity").json()["items"]
    moments = [datetime.fromisoformat(i["at"]) for i in items]
    assert moments == sorted(moments, reverse=True)
    mine = [i for i in items if i["application_id"] == app_id]
    assert {"state", "attempt", "capture", "approval"} <= {i["stage"] for i in mine}
    assert any(i["what"].startswith("Attempt ended: confirmed") for i in mine)
    # The newest across every kind of step, not the newest of one kind.
    assert api.get("/debug/activity", params={"limit": 1}).json()["items"] == items[:1]
    assert api.get("/debug/activity", params={"limit": 3}).json()["items"] == items[:3]


@pytest.mark.parametrize("sole", [False, True], ids=["one owner", "sole-owner mode"])
def test_another_account_sees_nothing_of_mine_from_any_source(
    api, other_api, receiver, monkeypatch, sole
):
    """Every kind of step the activity list reads, kept for one account, and the other account's
    list stays empty, in sole-owner mode too (every account is the owner's, each its own)."""
    from app.modules.discovery.models import DiscoveredJob
    from app.modules.execution.models import ApplicationPause
    from app.modules.inbox.models import InboxEvent
    from app.modules.preparation.models import AnswerDraft

    monkeypatch.setattr(get_settings(), "sole_owner", sole)
    app_id, att = submitted(api, receiver)
    job_id = uuid.UUID(api.get(f"/applications/{app_id}").json()["job"]["id"])
    me = user(ME).id
    with SessionLocal() as db:
        db.add_all([
            AutoApplyEvent(user_id=me, job_id=job_id, application_id=uuid.UUID(app_id),
                           action="skipped", reason="open_questions"),
            ApplicationPause(user_id=me, application_id=uuid.UUID(app_id),
                             attempt_id=uuid.UUID(att), kind="form_changed", status="closed",
                             resolution="dismissed", package_version=1, package_hash="0" * 64),
            InboxEvent(user_id=me, message_ref="m1", received_at=utcnow(),
                       sender_domain="example.com", kind="received", state="noted",
                       application_id=uuid.UUID(app_id)),
            DiscoveredJob(user_id=me, provider="freehire", source_job_id="synthetic-1",
                          fingerprint="0" * 64, normalized={}, status="linked", job_id=job_id),
            AnswerDraft(application_id=uuid.UUID(app_id), user_id=me, field_key="k",
                        input_hash="0" * 64, provider="fixture", status="proposed"),
        ])  # fmt: skip
        db.commit()
    mine = api.get("/debug/activity").json()["items"]
    stages = {i["stage"] for i in mine}
    assert {"rule", "state", "attempt", "pause", "email", "discovery", "draft", "capture",
            "approval"} <= stages  # fmt: skip
    assert all(i["application_id"] == app_id for i in mine)  # each step linked to its trace
    synthetic_candidate(other_api)
    assert other_api.get("/debug/activity").json()["items"] == []
    assert other_api.get(f"/debug/applications/{app_id}").status_code == 404


# ---------------------------------------------------------------- the server's switches


SECRETS = {
    "anthropic_api_key": "sk-marker-anthropic-0001",
    "inbox_oauth_client_secret": "marker-oauth-secret-0002",
    "email_smtp_password": "marker-smtp-password-0003",
}


def test_every_switch_is_shown_and_never_a_secret(api, monkeypatch):
    s = get_settings()
    for name, value in SECRETS.items():
        monkeypatch.setattr(s, name, SecretStr(value))
    monkeypatch.setattr(s, "freehire_api_key", "marker-freehire-key-0004")
    monkeypatch.setattr(s, "google_drive_api_key", "marker-drive-key-0005")
    monkeypatch.setattr(s, "drafting_provider", "anthropic")
    monkeypatch.setattr(s, "live_owner_emails", [ME])  # the owner: what is missing is shown
    synthetic_candidate(api)
    r = api.get("/debug/system")
    assert r.status_code == 200, r.text
    assert not [m for m in (*SECRETS.values(), "marker-freehire-key-0004",
                            "marker-drive-key-0005") if m in r.text]  # fmt: skip
    v = r.json()
    keys = {f["key"] for f in v["features"]}
    assert {"discovery", "job_boards", "greenhouse_pilot", "auto_apply", "inbox",
            "gmail_connection", "ai_drafting", "email_reminders", "google_drive",
            "autofill"} <= keys  # fmt: skip
    drafting = feature(v, "ai_drafting")
    assert drafting["on"] is True and drafting["needs"] == [
        "NOEFFORTS_DRAFTING_DAILY_BUDGET_USD above 0"]  # fmt: skip  # the key is set: only named
    assert v["environment"]["env"] == "test"
    assert feature(v, "autofill")["ready"] is True  # the stand-ins serve the test environment
    assert len(v["safety"]) >= 6 and any("CAPTCHA" in x for x in v["safety"])


def test_only_the_owner_sees_the_permissions_and_what_each_switch_needs(
    api, other_api, monkeypatch
):
    from tests.conftest import SHIPPED_REGISTER

    s = get_settings()
    monkeypatch.setattr(authorizations, "RECORDED", SHIPPED_REGISTER)
    monkeypatch.setattr(s, "live_owner_emails", [ME])
    monkeypatch.setattr(s, "drafting_provider", "anthropic")
    synthetic_candidate(api)
    synthetic_candidate(other_api)
    mine, theirs = api.get("/debug/system").json(), other_api.get("/debug/system").json()
    assert mine["account"]["owner"] is True and mine["permissions"] and mine["environment"]
    assert feature(mine, "ai_drafting")["needs"]
    assert theirs["account"]["owner"] is False
    assert theirs["permissions"] == [] and theirs["environment"] is None
    assert not any(f["needs"] for f in theirs["features"])
    assert feature(theirs, "ai_drafting")["why"] == console.NOT_SET_UP
    assert "2026-11-06" not in json.dumps(theirs)  # not even when the owner's ended
    # In sole-owner mode every account is the owner's, and sees them.
    monkeypatch.setattr(s, "sole_owner", True)
    assert other_api.get("/debug/system").json()["permissions"]


def test_the_shipped_permissions_are_shown_as_the_gates_read_them(api, monkeypatch):
    """The owner's recorded permissions as reviewed source holds them (conftest empties the
    register in every test; here it is the shipped one): each with its words, its end and its
    state as `authorizations.covers` decides it today; once every one has ended, the warnings
    that nothing real is read, opened, filled or sent and no real mailbox is read."""
    from tests.conftest import SHIPPED_REGISTER

    monkeypatch.setattr(authorizations, "RECORDED", SHIPPED_REGISTER)
    monkeypatch.setattr(get_settings(), "live_owner_emails", [ME])
    synthetic_candidate(api)
    v = api.get("/debug/system").json()
    assert len(v["permissions"]) == len(SHIPPED_REGISTER)
    for p, a in zip(v["permissions"], SHIPPED_REGISTER, strict=True):
        assert (p["what"], p["words"], p["decision"]) == (a.what, a.words, a.decision)
        monkeypatch.setattr(authorizations, "RECORDED", (a,))
        assert p["active"] is any(authorizations.covers(a.what, x) for x in a.actions)
    pilot = [p for p in v["permissions"] if p["what"] == "greenhouse_pilot"]
    assert pilot and all(p["ends_on"] == "2026-11-06" for p in pilot)
    if date.today() > date(2026, 11, 6):
        assert all(p["state"] == "ended" for p in v["permissions"])
        assert any(w.startswith("No recorded permission covers a real employer's site (the last "
                                "ended on 2026-11-06)") for w in v["warnings"])  # fmt: skip
        assert any(w.startswith("Nothing permits reading a real mailbox") for w in v["warnings"])


def test_a_permission_running_or_not_yet_started_is_shown_as_such(api, monkeypatch):
    today = date.today()

    def entry(given_on, ends_on, words):
        return authorizations.Authorization(
            what=authorizations.GREENHOUSE_PILOT, decision="D168", given_on=given_on,
            words=words, actions=frozenset({"read", "open", "disclose"}),
            data="a test's own synthetic posting", ends_on=ends_on, max_attempts=3)  # fmt: skip

    monkeypatch.setattr(authorizations, "RECORDED", (
        entry(today, today + timedelta(days=1), "running"),
        entry(today + timedelta(days=1), None, "tomorrow")))  # fmt: skip
    monkeypatch.setattr(get_settings(), "live_owner_emails", [ME])
    synthetic_candidate(api)
    v = api.get("/debug/system").json()
    assert [(p["words"], p["state"], p["active"]) for p in v["permissions"]] == [
        ("running", "active", True), ("tomorrow", "not_started", False)]  # fmt: skip
    assert [(p["max_attempts"], p["attempts_used"]) for p in v["permissions"]] == [(3, 0), (3, 0)]
    assert not any(w.startswith("No recorded permission covers") for w in v["warnings"])


def test_each_feature_says_why_as_its_own_gate_decides(api, other_api, monkeypatch, tmp_path):
    """The pilot with its attempt limit used, the standing rule never turned on or paused, the
    stand-ins outside the test environment, connecting Gmail for an account not the owner's,
    reading mail with both switches off, drafting with a model it cannot price, a restore."""
    from app.modules.execution import live, restore

    s = get_settings()
    pilot_on(max_attempts=1)  # names the `api` account; every account served below
    monkeypatch.setattr(s, "all_accounts", True)
    monkeypatch.setattr(s, "auto_apply_enabled", True)
    synthetic_candidate(other_api)
    v = other_api.get("/debug/system").json()
    assert feature(v, "greenhouse_pilot")["ready"] is True
    assert feature(v, "auto_apply")["why"].startswith("Off for this account until you turn it on")
    other_api.put("/auto-apply", json={"paused": True})
    v = other_api.get("/debug/system").json()
    assert feature(v, "auto_apply")["why"].startswith("You paused it for this account")
    monkeypatch.setattr(live, "attempts_used", lambda db, since, **kw: 1)
    v = other_api.get("/debug/system").json()
    assert feature(v, "greenhouse_pilot")["why"] == (
        "The recorded permission's attempt limit is used: 1 of 1.")  # fmt: skip
    # Gmail: the web flow set up, for the named owner only (sole-owner mode off).
    for k, val in (("inbox_oauth_enabled", True), ("inbox_oauth_client_id", "client"),
                   ("inbox_oauth_client_secret", SecretStr("x")), ("inbox_enabled", True),
                   ("inbox_owner_emails", [ME]),
                   ("inbox_token_file", str(tmp_path / "server.json"))):  # fmt: skip
        monkeypatch.setattr(s, k, val)
    (tmp_path / "server.json").write_text("{}")
    authorize(monkeypatch, authorizations.INBOX)
    assert feature(other_api.get("/debug/system").json(), "gmail_connection")["why"] == (
        "Connecting Gmail is set up for the server owner's account only.")  # fmt: skip
    mine = api.get("/debug/system").json()
    assert feature(mine, "gmail_connection")["ready"] is True
    assert feature(mine, "inbox")["why"].startswith("Both are off for this account")
    monkeypatch.setattr(s, "sole_owner", True)  # every account the owner's: its own mailbox
    assert feature(other_api.get("/debug/system").json(), "inbox")["why"].startswith(
        "Connect your own Gmail first")  # fmt: skip
    # Drafting with a model NoEfforts cannot price; the stand-ins outside tests; a restore.
    for k, val in (
        ("drafting_provider", "anthropic"),
        ("anthropic_api_key", SecretStr("k")),
        ("drafting_daily_budget_usd", 1.0),
        ("drafting_model", "unpriced-model"),
    ):
        monkeypatch.setattr(s, k, val)
    assert feature(api.get("/debug/system").json(), "ai_drafting")["why"].startswith(
        "The model in NOEFFORTS_DRAFTING_MODEL is not one NoEfforts can price")  # fmt: skip
    monkeypatch.setattr(restore, "held", lambda db: True)
    v = api.get("/debug/system").json()
    assert console.HELD in v["warnings"]
    monkeypatch.setattr(s, "env", "development")
    assert feature(api.get("/debug/system").json(), "autofill")["why"].startswith(
        "Only in the test environment")  # fmt: skip


def test_the_console_is_never_reachable_with_an_api_token(api):
    token = make(api, ["read", "import:jobs"])
    for url in ("/debug/system", "/debug/activity", f"/debug/applications/{uuid.uuid4()}"):
        r = api.client.get(url, headers=bearer(token))
        assert r.status_code == 403, url
        assert r.json()["detail"].endswith("(reason: token_session_only)"), url


# ---------------------------------------------------------------- sole-owner mode


def test_sole_owner_is_on_by_default_outside_tests_and_off_when_set():
    for env in ("development", "production"):
        assert Settings(_env_file=None, env=env).sole_owner is True
    assert Settings(_env_file=None, env="production", sole_owner=False).sole_owner is False
    assert Settings(_env_file=None, env="test").sole_owner is False


def test_in_sole_owner_mode_every_account_is_the_owner_s(api, other_api, monkeypatch):
    from app.core import accounts
    from app.modules.autoapply import service as rule
    from app.modules.inbox import service as inbox

    s = get_settings()
    monkeypatch.setattr(s, "live_owner_emails", [ME])
    synthetic_candidate(other_api)
    other = user(OTHER)
    with SessionLocal() as db:
        assert (accounts.owner(OTHER), accounts.named(OTHER, []), inbox.is_inbox_owner(other)) == (
            False, False, False)  # fmt: skip
        assert rule.paused(db, other) is True  # D114: its own choice, off until it chooses
    monkeypatch.setattr(s, "sole_owner", True)
    with SessionLocal() as db:
        assert (accounts.owner(OTHER), accounts.named(OTHER, []), inbox.is_inbox_owner(other)) == (
            True, True, True)  # fmt: skip
        assert rule.paused(db, other) is False  # the owner's default: on until paused
    v = other_api.get("/debug/system").json()
    assert (v["account"]["owner"], v["account"]["sole_owner"]) == (True, True)
    assert any(w.startswith("Sole-owner mode is on") for w in v["warnings"])


def test_in_sole_owner_mode_an_account_reads_only_a_mailbox_it_connected(
    api, other_api, monkeypatch, tmp_path
):
    """The Gmail features are every account's; the server's own mailbox file stays the named
    owner's: another account has nothing to read until it connects a mailbox of its own."""
    from app.modules.connections import service as connections
    from app.modules.connections.models import GmailConnection
    from app.modules.inbox import service as inbox

    s = get_settings()
    server_file = tmp_path / "server-mailbox.json"
    server_file.write_text("{}")
    for k, v in (("sole_owner", True), ("inbox_enabled", True), ("inbox_owner_emails", [ME]),
                 ("inbox_token_file", str(server_file)),
                 ("inbox_connections_dir", str(tmp_path / "connections"))):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    with SessionLocal() as db:
        me = db.query(User).filter(User.email == ME).one()
        other = db.query(User).filter(User.email == OTHER).one()
        assert inbox.is_inbox_owner(other) is True
        assert inbox.owner_token_file(db, me) == str(server_file)
        assert inbox.owner_token_file(db, other) == ""  # never the server's mailbox
        own = connections.token_path(other.id)
        own.parent.mkdir(parents=True)
        own.write_text("{}")
        db.add(GmailConnection(user_id=other.id, email="own.mailbox@example.com",
                               scope="gmail.readonly", status="connected"))  # fmt: skip
        db.flush()
        assert inbox.owner_token_file(db, other) == str(own)  # its own, once it connected one
        db.rollback()


def test_in_sole_owner_mode_a_mailbox_gone_mid_read_is_never_the_server_s(
    api, other_api, monkeypatch, tmp_path
):
    """The account's own connection is there when its reading is allowed and gone a moment later
    (a disconnect at that moment): nothing is read, and never the server's mailbox in its place,
    by the app's own read or by the worker's."""
    from app.modules.connections import service as connections
    from app.modules.inbox import service as inbox

    s = get_settings()
    server_file, own = tmp_path / "server-mailbox.json", tmp_path / "own.json"
    server_file.write_text("{}")
    own.write_text("{}")
    for k, v in (("sole_owner", True), ("inbox_enabled", True), ("inbox_owner_emails", [ME]),
                 ("inbox_token_file", str(server_file))):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    seen = {"n": 0}

    def flaky(db, account):  # the other account's own mailbox: there once, then gone
        if account.email != OTHER:
            return ""
        seen["n"] += 1
        return str(own) if seen["n"] == 1 else ""

    built = []

    class Recorder:
        def __init__(self, token_file, *a, **k):
            built.append(token_file)

        def received_after(self, *a, **k):
            return []

    monkeypatch.setattr(connections, "connected_token_file", flaky)
    monkeypatch.setattr(inbox, "may_read_applications", lambda db, account: True)
    monkeypatch.setattr(inbox, "GmailReader", Recorder)
    with SessionLocal() as db:
        other = db.query(User).filter(User.email == OTHER).one()
        inbox.settings_of(db, other.id).tracking_enabled = True
        assert inbox.check(db, other) == {"skipped": "not_connected"}
        db.commit()
    assert built == []
    seen["n"] = 0
    out = inbox.inbox_tick()  # the worker: its list says due, then the mailbox is gone
    assert out["reads"] == 0 and built == []
    inbox.reader("")  # and "" is never the server's file
    assert built == [""]


def test_sole_owner_mode_opens_no_gate(api, other_api, receiver, monkeypatch):
    """Every account is the owner's, and nothing real runs without what the pilot needs: the
    recorded permission, production, the container. The standing rule, on, reads nothing."""
    from app.modules.autoapply import service as rule
    from app.modules.execution import live

    s = get_settings()
    pilot_on(permitted=())  # the stand-in plays a real board; no permission recorded
    for k, v in (("sole_owner", True), ("auto_apply_enabled", True)):
        monkeypatch.setattr(s, k, v)
    synthetic_candidate(other_api)
    from tests.test_greenhouse_dom import v2_job

    v2_job(other_api)
    other = user(OTHER)
    assert live.refusal(other) == "not_authorized"
    assert rule.owner_refusal(other) == "not_authorized"
    assert rule.tick() == 0
    assert receiver.ledger()["requests"] == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AutoApplyEvent)) == 0
    pilot = feature(other_api.get("/debug/system").json(), "greenhouse_pilot")
    assert pilot["ready"] is False and pilot["why"]
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "browser_isolation", "netns")
    assert live.refusal(other) == "needs_container"
    monkeypatch.setattr(s, "env", "development")
    assert live.refusal(other) == "needs_production"
