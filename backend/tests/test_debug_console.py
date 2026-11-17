"""D168: the owner's console (app/modules/debug) and sole-owner mode.

The console reads what NoEfforts already keeps and changes nothing: one application from
discovery to its outcome (`/debug/applications/{id}`), what happened across the account's jobs
(`/debug/activity`), and the server's switches as they apply to the signed-in account
(`/debug/system`). Every query is scoped to the account (another account's application is a 404),
it is app-only (never an API token), and it never returns a secret: no verification code, token,
key or password, only whether one is set.

Sole-owner mode (the owner's words, 2026-11-17: "treat any account I use new or existing as the
owner"): on by default outside tests, every account is the owner's, for the mailbox and the
standing rule's default; every gate is unchanged. Local stand-ins only, synthetic data only."""

import json
import uuid
from datetime import date, timedelta

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.autoapply.models import AutoApplyEvent
from app.modules.execution import runner
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from app.modules.identity.models import User
from tests.execution_harness import Receiver, queue, synthetic_candidate
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


# ---------------------------------------------------------------- one application, start to finish


def test_a_submitted_application_is_traced_from_capture_to_its_receipt(api, receiver):
    app_id, att = submitted(api, receiver)
    t = trace(api, app_id)
    state = api.get(f"/applications/{app_id}").json()["state"]
    assert t["application"]["state"] == state == "submitted_confirmed"
    assert t["job"]["title"] and t["job"]["url"]
    (capture,) = t["captures"]
    assert capture["fields"] > 0 and capture["checkpoints"] == []
    # The stand-in's optional "How did you hear about us?" combobox: left empty, not a checkpoint.
    assert [c["key"] for c in capture["left_empty"]] == ["aria:source"]
    assert [s["kind"] for s in capture["sections"]] == ["employment"]
    last = t["packages"][-1]
    assert last["unresolved"] == [] and last["validation_errors"] == []
    first = next(a for a in last["answers"] if a["key"] == "legalName--firstName")
    assert first["display"] == "Sam" and first["status"] == "resolved"
    assert "value" not in first  # what the review page shows, never the stored value
    assert last["sections"] == [{"kind": "employment", "step": None, "rows": 2}]
    approval = t["approvals"][-1]
    assert approval["by_rule"] is False and approval["package_version"] == last["version"]
    (attempt,) = t["attempts"]
    assert (attempt["id"], attempt["state"]) == (att, "confirmed")
    assert attempt["disclosure_started_at"] and attempt["send_started_at"]
    assert attempt["finished_at"] and attempt["events"]
    assert "receipt" in {e["kind"] for e in attempt["evidence"]}
    assert "queued" in {s["to_state"] for s in t["state_changes"]}
    assert t["state_changes"][-1]["to_state"] == "submitted_confirmed"


def test_the_timeline_puts_every_step_in_order(api, receiver):
    app_id, _ = submitted(api, receiver)
    tl = trace(api, app_id)["timeline"]
    assert [e["at"] for e in tl] == sorted(e["at"] for e in tl)
    stages = [e["stage"] for e in tl]
    for stage in ("capture", "package", "approval", "state", "attempt", "audit"):
        assert stage in stages, stage
    first = {s: stages.index(s) for s in ("capture", "approval")}
    ended = max(i for i, e in enumerate(tl) if e["what"].startswith("Attempt ended"))
    assert first["capture"] < first["approval"] < ended


def test_what_the_standing_rule_decided_is_in_the_trace_with_its_words(api, receiver):
    app_id = experience_application(api, receiver, single=True, approved=False)
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == ME).one().id
        db.add(AutoApplyEvent(user_id=user_id, job_id=uuid.UUID(job_id),
                              application_id=uuid.UUID(app_id), action="skipped",
                              reason="open_questions"))  # fmt: skip
        db.commit()
    (event,) = trace(api, app_id)["rule"]
    assert (event["action"], event["reason"]) == ("skipped", "open_questions")
    assert event["words"].startswith("Some questions need your answer")


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
    seen = {i["application_id"] for i in other_api.get("/debug/activity").json()["items"]}
    assert app_id not in seen


# ---------------------------------------------------------------- across the account's jobs


def test_activity_lists_this_account_s_steps_newest_first(api, receiver):
    app_id, _ = submitted(api, receiver)
    items = api.get("/debug/activity").json()["items"]
    assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
    mine = [i for i in items if i["application_id"] == app_id]
    assert {"state", "attempt"} <= {i["stage"] for i in mine}
    assert any(i["what"].startswith("Attempt ended: confirmed") for i in mine)
    assert len(api.get("/debug/activity", params={"limit": 2}).json()["items"]) == 2


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
    drafting = next(f for f in v["features"] if f["key"] == "ai_drafting")
    assert drafting["on"] is True and drafting["needs"] == [
        "NOEFFORTS_DRAFTING_DAILY_BUDGET_USD above 0"]  # fmt: skip  # the key is set: only named
    assert v["environment"]["env"] == "test"
    assert len(v["safety"]) >= 6 and any("CAPTCHA" in x for x in v["safety"])


def test_the_shipped_permissions_are_shown_with_their_words_and_end(api, monkeypatch):
    """The owner's recorded permissions as reviewed source holds them (conftest empties the
    register in every test; here it is the shipped one): each with its words and its end, and,
    once every one has ended, the warning that nothing real is read, opened, filled or sent."""
    from app.core import authorizations
    from tests.conftest import SHIPPED_REGISTER

    monkeypatch.setattr(authorizations, "RECORDED", SHIPPED_REGISTER)
    synthetic_candidate(api)
    v = api.get("/debug/system").json()
    pilot = [p for p in v["permissions"] if p["what"] == "greenhouse_pilot"]
    assert pilot and all(p["ends_on"] == "2026-11-06" for p in pilot)
    assert all(p["words"] and p["decision"] for p in v["permissions"])
    today = date.today()
    assert all(p["active"] is (date.fromisoformat(p["ends_on"]) >= today) for p in pilot)
    if today > date(2026, 11, 6):
        assert not any(p["active"] for p in v["permissions"])
        assert any(w.startswith("No recorded permission is active (the last ended on "
                                "2026-11-06)") for w in v["warnings"])  # fmt: skip


def test_a_permission_still_running_is_active_and_raises_no_warning(api, monkeypatch):
    from app.core import authorizations

    entry = authorizations.Authorization(
        what=authorizations.GREENHOUSE_PILOT, decision="D168", given_on=date.today(),
        words="synthetic words for a test", actions=frozenset({"read"}),
        data="a test's own synthetic posting", ends_on=date.today() + timedelta(days=1),
    )  # fmt: skip
    monkeypatch.setattr(authorizations, "RECORDED", (entry,))
    synthetic_candidate(api)
    v = api.get("/debug/system").json()
    assert [p["active"] for p in v["permissions"]] == [True]
    assert not any(w.startswith("No recorded permission") for w in v["warnings"])


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
    with SessionLocal() as db:
        other = db.query(User).filter(User.email == OTHER).one()
        assert (accounts.owner(other.email), inbox.is_inbox_owner(other)) == (False, False)
        assert rule.paused(db, other) is True  # D114: its own choice, off until it chooses
    monkeypatch.setattr(s, "sole_owner", True)
    with SessionLocal() as db:
        other = db.query(User).filter(User.email == OTHER).one()
        assert (accounts.owner(other.email), inbox.is_inbox_owner(other)) == (True, True)
        assert rule.paused(db, other) is False  # the owner's default: on until paused
    v = other_api.get("/debug/system").json()
    assert (v["account"]["owner"], v["account"]["sole_owner"]) == (True, True)
    assert any(w.startswith("Sole-owner mode is on") for w in v["warnings"])
    # Still its own records only.
    assert other_api.get("/debug/activity").json()["items"] == []


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


def test_sole_owner_mode_changes_no_gate(api, monkeypatch):
    """Every account is the owner's, and the pilot still refuses without production, the
    container and a recorded permission: the mode opens no step by itself."""
    from app.modules.execution import live

    monkeypatch.setattr(get_settings(), "sole_owner", True)
    monkeypatch.setattr(get_settings(), "live_greenhouse_enabled", True)
    synthetic_candidate(api)
    with SessionLocal() as db:
        me = db.query(User).filter(User.email == ME).one()
        assert live.refusal(me) is not None
    pilot = next(f for f in api.get("/debug/system").json()["features"]
                 if f["key"] == "greenhouse_pilot")  # fmt: skip
    assert pilot["ready"] is False and pilot["why"]


def test_the_trace_is_plain_json(api, receiver):
    app_id, _ = submitted(api, receiver)
    assert json.loads(json.dumps(trace(api, app_id)))


def test_no_keyed_reference_is_served(api, receiver):
    """The audit log keeps a question's key as a keyed reference (audit/service.ref): opaque,
    and never served by the console, while the step itself is."""
    from app.modules.audit.models import AuditEvent
    from app.modules.audit.service import REF_PREFIX, record

    app_id, _ = submitted(api, receiver)
    with SessionLocal() as db:
        me = db.query(User).filter(User.email == ME).one()
        record(db, me.id, "application.answer", "application", app_id, field="q_custom_1",
               reason_code="synthetic")  # fmt: skip
        db.commit()
        stored = db.query(AuditEvent).filter(AuditEvent.action == "application.answer").all()
        assert any(str(m.meta.get("field_ref", "")).startswith(REF_PREFIX) for m in stored)
    t = trace(api, app_id)
    answered = [e for e in t["audit"] if e["action"] == "application.answer"]
    assert any(e["meta"].get("reason_code") == "synthetic" for e in answered)
    assert REF_PREFIX not in json.dumps(t) and "field_ref" not in json.dumps(t)
