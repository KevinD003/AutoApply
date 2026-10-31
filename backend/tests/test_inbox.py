"""D101: reading the owner's own Gmail, read-only, against a local stand-in of the API
(fixtures/ats_receiver/inbox_fixture.py): verification codes for a waiting step, and application
emails proposed as outcomes you confirm. Synthetic messages only; nothing contacts Google."""

import json
import os

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.applications.models import ApplicationEvent
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.execution.models import Checkpoint
from app.modules.identity.models import User
from app.modules.inbox import connect, rules, service
from app.modules.inbox.models import InboxEvent
from app.modules.inbox.provider import SCOPE, GmailReader, InboxUnavailable
from tests.execution_harness import BASE, Receiver, prepared_application, queue
from tests.test_execution_security import open_checkpoint, start_worker, wait_for

OWNER = "synthetic.user@example.com"  # the `api` fixture's account
# A code sender under a reserved domain (the repository holds no real addresses); the default
# senders are checked by domain in test_code_senders_are_matched_by_domain_suffix.
CODE_SENDER = "Careers <no-reply@us.codes.example>"
EMPLOYER = "Example Health Clinic Careers <talent@examplehealth.test>"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


@pytest.fixture
def connected(monkeypatch, tmp_path):
    token = tmp_path / "inbox-token.json"
    token.write_text(json.dumps({"client_id": "test-client", "client_secret": "test-only",
                                 "refresh_token": "test-only-refresh"}))  # fmt: skip
    s = get_settings()
    for k, v in (("inbox_enabled", True), ("inbox_owner_emails", [OWNER]),
                 ("inbox_token_file", str(token)), ("inbox_api_base", f"{BASE}/inbox-fixture"),
                 ("inbox_token_url", f"{BASE}/inbox-fixture/token"),
                 ("inbox_code_senders", ["codes.example"])):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    return token


def deliver(receiver, sender, subject, text):
    import httpx

    r = httpx.post(f"{BASE}/_admin/inbox", headers=receiver._h(),
                   json={"sender": sender, "subject": subject, "text": text})  # fmt: skip
    r.raise_for_status()


def user() -> User:
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == OWNER))
        db.expunge(u)
        return u


def events() -> list[InboxEvent]:
    with SessionLocal() as db:
        rows = db.scalars(select(InboxEvent).order_by(InboxEvent.received_at)).all()
        for r in rows:
            db.expunge(r)
        return rows


def fill() -> int:
    with SessionLocal() as db:
        n = service.fill_codes(db, db.get(User, user().id))
        db.commit()
        return n


# -- rules ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject,text,kind",
    [
        ("Your application", "Unfortunately we have decided to move forward with other "
         "candidates for this role.", "rejected"),
        ("Next steps", "We would like to schedule an interview with you next week.", "interview"),
        ("Assessment", "Please complete the online assessment on HackerRank within 5 days.",
         "assessment"),
        ("Thank you", "Thank you for applying! We have received your application.", "received"),
        ("Your security code", "Copy and paste this code into the application: 482915.", "code"),
        ("Update", "We are not moving forward with this role, but we would like to schedule an "
         "interview for another.", "unclear"),  # never guessed
        ("Newsletter", "Ten tips for a better weekend.", "other"),
    ],
)  # fmt: skip
def test_messages_are_sorted_by_fixed_wording(subject, text, kind):
    assert rules.classify(subject, text) == kind


def test_a_code_is_taken_only_when_exactly_one_follows_the_word():
    assert rules.extract_code("Security code", "Your code is 482915. It expires in 10 minutes.") \
        == "482915"  # fmt: skip
    assert rules.extract_code("Security code", "Use code 111111 or code 222222.") is None
    assert rules.extract_code("Security code", "Your code is on its way.") is None
    assert rules.extract_code("Interview", "Your code is 482915.") is None  # not a code email
    assert rules.mentions("Example Health Clinic (fictional)", "Example Health Clinic Careers",
                          "", "")  # fmt: skip
    assert not rules.mentions("Clinic", "", "", "a clinical trial")


# -- availability ----------------------------------------------------------------------------


def test_nothing_is_read_until_the_owner_connects_it(api):
    v = api.get("/inbox").json()
    assert v["available"] is False and "switched off" in v["why_not"]
    r = api.put("/inbox", json={"codes_enabled": True, "tracking_enabled": False})
    assert r.status_code == 409
    assert api.post("/inbox/check").status_code == 409


def test_the_reader_contacts_no_other_host(tmp_path):
    token = tmp_path / "t.json"
    token.write_text(json.dumps({"client_id": "a", "client_secret": "b", "refresh_token": "c"}))
    with pytest.raises(InboxUnavailable) as e:
        GmailReader(str(token), "https://mail.attacker.example").received_after(
            __import__("datetime").datetime.now()
        )
    assert e.value.code == "refused_host"


# -- verification codes ------------------------------------------------------------------------


def test_code_senders_are_matched_by_domain_suffix():
    """The default senders: an application system's sending domain or a subdomain of it, never
    a look-alike."""
    assert service._code_sender("us.greenhouse-mail.io")
    assert service._code_sender("greenhouse-mail.io")
    assert service._code_sender("hire.lever.co")
    assert not service._code_sender("greenhouse-mail.io.attacker.example")
    assert not service._code_sender("notgreenhouse-mail.io")
    assert not service._code_sender("")


def test_a_waiting_code_step_is_filled_from_the_mail_once(api, receiver, connected):
    app_id = prepared_application(api, receiver)
    assert api.put("/inbox", json={"codes_enabled": True, "tracking_enabled": False}).status_code \
        == 200  # fmt: skip
    aid = queue(api, app_id)
    receiver.config(mode="otp", email_codes=CODE_SENDER)
    w = start_worker(aid)
    open_checkpoint(api, app_id, 1)
    wait_for(lambda: receiver.ledger()["challenges"])
    assert fill() == 1
    out, err = w.communicate(timeout=60)
    assert out.strip() == "confirmed", err[-800:]
    led = receiver.ledger()
    assert led["accepted"] == 1 and led["challenges"][-1]["done"]
    assert {r["bearer"] for r in led["inbox_requests"] if r["route"] != "token"} == {True}
    (e,) = events()
    assert (e.kind, e.state, str(e.application_id)) == ("code", "code_used", app_id)
    code = led["challenges"][-1]["code"]
    with SessionLocal() as db:
        assert all(c.code is None for c in db.scalars(select(Checkpoint)))
        stored = json.dumps([[a.action, a.meta] for a in db.scalars(select(AuditEvent))])
    assert code not in stored and e.sender_domain == "us.codes.example"
    assert fill() == 0  # the message is used once; nothing waits now


def test_a_code_from_another_sender_or_two_codes_are_left_to_you(api, receiver, connected):
    app_id = prepared_application(api, receiver)
    api.put("/inbox", json={"codes_enabled": True, "tracking_enabled": False})
    aid = queue(api, app_id)
    receiver.config(mode="otp")  # the code is not mailed by the form here
    w = start_worker(aid)
    cp = open_checkpoint(api, app_id, 1)
    real = wait_for(lambda: receiver.ledger()["challenges"])[-1]["code"]
    deliver(receiver, "Someone <someone@else.example>", "Your security code",
            f"Your code is {real}.")  # fmt: skip
    assert fill() == 0 and events() == []  # not a code sender: not even read as one
    deliver(receiver, CODE_SENDER, "Your security code", "Your code is 123456.")
    deliver(receiver, CODE_SENDER, "Your security code", f"Your code is {real}.")
    assert fill() == 0  # two codes: never guessed
    assert {(e.kind, e.state) for e in events()} == {("code", "code_unclear")}
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                 json={"round": 1, "code": real})  # fmt: skip
    assert r.status_code == 202
    out, err = w.communicate(timeout=60)
    assert out.strip() == "confirmed", err[-800:]


def test_codes_are_never_read_while_turned_off(api, receiver, connected):
    app_id = prepared_application(api, receiver)  # codes are off by default
    aid = queue(api, app_id)
    receiver.config(mode="otp", email_codes=CODE_SENDER)
    w = start_worker(aid)
    cp = open_checkpoint(api, app_id, 1)
    real = wait_for(lambda: receiver.ledger()["challenges"])[-1]["code"]
    assert fill() == 0
    assert receiver.ledger()["inbox_requests"] == [] and events() == []  # nothing even asked
    r = api.post(f"/applications/{app_id}/checkpoints/{cp['id']}/code",
                 json={"round": 1, "code": real})  # fmt: skip
    assert r.status_code == 202
    out, err = w.communicate(timeout=60)
    assert out.strip() == "confirmed", err[-800:]


# -- application emails ----------------------------------------------------------------------------


def submitted(api, receiver) -> str:
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    return app_id


def test_application_emails_are_proposed_and_confirmed_by_you(api, other_api, receiver, connected):
    app_id = submitted(api, receiver)
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    deliver(receiver, EMPLOYER, "Your application to Example Health Clinic",
            "Unfortunately we have decided to move forward with other candidates.")  # fmt: skip
    deliver(receiver, "Other Corp <jobs@other.example>", "Interview",
            "We would like to schedule an interview with you.")  # fmt: skip
    deliver(receiver, "Shop <news@shop.example>", "Weekend sale", "Ten tips for the weekend.")
    v = api.post("/inbox/check").json()
    assert v["result"] == {"proposed": 1, "unlinked": 1}
    by_kind = {e["kind"]: e for e in v["events"]}
    assert set(by_kind) == {"rejected", "interview"}  # the newsletter is not kept at all
    rej = by_kind["rejected"]
    assert (rej["state"], rej["application_id"], rej["sender_domain"]) == (
        "proposed", app_id, "examplehealth.test")  # fmt: skip
    assert by_kind["interview"]["state"] == "unlinked"
    body = json.dumps(v)
    assert "Unfortunately" not in body and "Example Health Clinic Careers" not in body
    # Another account sees none of it and cannot act on it.
    assert other_api.get("/inbox").json()["events"] == []
    assert other_api.post(f"/inbox/events/{rej['id']}/accept").status_code == 404
    # You confirm: recorded as your statement, dated the day the email arrived.
    v = api.post(f"/inbox/events/{rej['id']}/accept").json()
    assert api.get(f"/applications/{app_id}").json()["outcome"] == "rejected"
    with SessionLocal() as db:
        ev = db.scalars(select(ApplicationEvent).where(ApplicationEvent.kind == "outcome")).all()
    assert [(e.source, e.to_outcome.value) for e in ev] == [("user_reported", "rejected")]
    assert "examplehealth.test" in ev[0].evidence_note
    assert api.post(f"/inbox/events/{rej['id']}/accept").status_code == 409  # once
    unl = by_kind["interview"]["id"]
    assert api.post(f"/inbox/events/{unl}/dismiss").status_code == 200
    # The next read starts where this one ended: nothing is read twice.
    assert api.post("/inbox/check").json()["result"] == {}
    assert len(events()) == 2


def test_a_received_email_settles_a_submission_of_unknown_outcome_when_you_confirm(
    api, other_api, receiver, connected
):
    """The employer accepted the application but its answer never reached NoEfforts: the
    submission waits in submitted_unconfirmed. Their "we received your application" email is
    proposed as its reconciliation; you confirm it, never NoEfforts alone (D53)."""
    app_id = prepared_application(api, receiver)
    receiver.config(mode="error_after_accept")
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "unknown"
    assert receiver.ledger()["accepted"] == 1
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    deliver(receiver, EMPLOYER, "Thank you for applying to Example Health Clinic",
            "We have received your application and will review it shortly.")  # fmt: skip
    v = api.post("/inbox/check").json()
    assert v["result"] == {"proposed": 1}
    (e,) = v["events"]
    assert (e["kind"], e["state"], e["application_id"]) == ("received", "proposed", app_id)
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_unconfirmed"  # not yet
    assert other_api.post(f"/inbox/events/{e['id']}/accept").status_code == 404
    api.post(f"/inbox/events/{e['id']}/accept").raise_for_status()
    assert api.get(f"/applications/{app_id}").json()["state"] == "submitted_confirmed"
    with SessionLocal() as db:
        (ev,) = db.scalars(select(ApplicationEvent).where(
            ApplicationEvent.application_id == app_id,
            ApplicationEvent.to_state == "submitted_confirmed"))  # fmt: skip
    assert (ev.actor.value, ev.reason) == ("user", "Reconciled as received")
    assert "examplehealth.test" in ev.evidence_note
    assert api.post(f"/inbox/events/{e['id']}/accept").status_code == 409  # once
    assert receiver.ledger()["accepted"] == 1  # reading mail never sends anything


def test_a_received_email_is_only_noted_once_the_submission_is_settled(api, receiver, connected):
    submitted(api, receiver)  # the employer's receipt already confirmed it
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    deliver(receiver, EMPLOYER, "Application received: Example Health Clinic",
            "Thank you for applying. We have received your application.")  # fmt: skip
    v = api.post("/inbox/check").json()
    (e,) = v["events"]
    assert (e["kind"], e["state"]) == ("received", "noted")
    assert api.post(f"/inbox/events/{e['id']}/accept").status_code == 409


def test_a_proposed_reconciliation_is_refused_once_settled_another_way(api, receiver, connected):
    app_id = prepared_application(api, receiver)
    receiver.config(mode="error_after_accept")
    assert runner.run_attempt(queue(api, app_id), "w1") == "unknown"
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    deliver(receiver, EMPLOYER, "Example Health Clinic", "We have received your application.")
    (e,) = api.post("/inbox/check").json()["events"]
    assert e["state"] == "proposed"
    api.post(f"/applications/{app_id}/reconcile", json={
        "finding": "received", "evidence": "Checked the employer's careers portal"},
    ).raise_for_status()  # fmt: skip
    r = api.post(f"/inbox/events/{e['id']}/accept")
    assert r.status_code == 409 and "already settled" in r.text
    with SessionLocal() as db:
        n = db.scalars(select(ApplicationEvent).where(
            ApplicationEvent.application_id == app_id,
            ApplicationEvent.to_state == "submitted_confirmed")).all()  # fmt: skip
    assert len(n) == 1


def test_a_refused_connection_is_reported_by_its_code(api, receiver, connected):
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    receiver.config(inbox_mode="revoked")
    v = api.post("/inbox/check").json()
    assert v["result"] == {"error": "revoked"} and "Connect again" in v["last_error"]
    with SessionLocal() as db:
        (a,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "inbox.read_failed"))
    assert a.meta == {"reason_code": "revoked"}


def test_the_worker_reads_when_due(api, receiver, connected):
    submitted(api, receiver)
    api.put("/inbox", json={"codes_enabled": False, "tracking_enabled": True})
    deliver(receiver, EMPLOYER, "Interview", "We would like to schedule an interview with you.")
    assert service.inbox_tick() == {"codes": 0, "reads": 1, "errors": 0}
    assert [(e.kind, e.state) for e in events()] == [("interview", "proposed")]
    assert service.inbox_tick()["reads"] == 0  # not due again yet


# -- connecting -----------------------------------------------------------------------------------

CREDS = {"installed": {"client_id": "test-client.apps", "client_secret": "test-only",
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token"}}  # fmt: skip


class _Reply:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


def test_connecting_asks_for_read_only_mail_and_keeps_the_token_private(tmp_path):
    client = connect.client_of(CREDS)
    verifier, challenge = connect.pkce()
    url = connect.auth_url(client, "http://127.0.0.1:5000/", "state-1", challenge)
    assert "gmail.readonly" in url and "code_challenge_method=S256" in url
    assert "access_type=offline" in url and verifier not in url
    with pytest.raises(connect.ConnectError):
        bad = {**CREDS["installed"], "auth_uri": "https://login.attacker.example/auth"}
        connect.client_of({"installed": bad})
    sent = []

    def post(url, **kw):
        sent.append((url, kw["data"]))
        return _Reply({"refresh_token": "test-only-refresh", "scope": SCOPE})

    token = connect.exchange(client, "code-1", "http://127.0.0.1:5000/", verifier, post=post)
    assert sent[0][1]["code_verifier"] == verifier
    out = tmp_path / "secret" / "inbox-token.json"
    connect.save(token, out)
    assert oct(os.stat(out).st_mode & 0o777) == "0o600"
    assert set(json.loads(out.read_text())) == {"client_id", "client_secret", "refresh_token"}
    with pytest.raises(connect.ConnectError):  # anything but read-only mail is refused
        connect.exchange(client, "c", "r", verifier, post=lambda *a, **k: _Reply(
            {"refresh_token": "x", "scope": SCOPE.replace("readonly", "modify")}))  # fmt: skip


def test_an_unknown_id_is_never_requested(connected):
    with pytest.raises(InboxUnavailable):
        service.reader().read("../../other")
