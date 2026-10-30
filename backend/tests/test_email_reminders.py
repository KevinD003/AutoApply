"""Email reminders to the account owner (D94), against a local SMTP sink whose own ledger
(fixtures/ats_receiver/mail_sink.py) is the oracle for what was handed over. Synthetic
accounts and example.com recipients only; no real mail server is contacted."""

import json
import logging
import pathlib
import sys
import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.audit.models import AuditEvent
from app.modules.followups import service as followups
from app.modules.followups.models import FollowUp
from app.modules.mail import service
from app.modules.mail.models import EmailDelivery, EmailSettings
from tests.conftest import Api
from tests.test_account import unzip

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
from mail_sink import MailSink  # noqa: E402

ADDRESS = "sam.synthetic@example.com"


@pytest.fixture(scope="module")
def sink():
    s = MailSink()
    s.start()
    return s


@pytest.fixture(autouse=True)
def mail_on(sink, monkeypatch):
    sink.reset()
    s = get_settings()
    for k, v in {
        "email_enabled": True, "email_smtp_host": "127.0.0.1", "email_smtp_port": sink.port,
        "email_smtp_starttls": False, "email_from": "noefforts@example.com",
        "email_timeout_seconds": 1.0, "email_max_attempts": 3,
        "email_recipient_domains": ["example.com"], "public_base_url": "http://127.0.0.1:3100",
    }.items():  # fmt: skip
        monkeypatch.setattr(s, k, v)
    return sink


def uid(api: Api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def deliveries(user_id, kind="digest") -> list[EmailDelivery]:
    with SessionLocal() as db:
        return db.scalars(
            select(EmailDelivery).where(EmailDelivery.user_id == user_id,
                                        EmailDelivery.kind == kind)
            .order_by(EmailDelivery.created_at)
        ).all()  # fmt: skip


def code_from(sink: MailSink) -> str:
    body = sink.received()[-1]["body"]
    return body.split("verification code is ", 1)[1][:6]


def verified(api: Api, sink: MailSink, *, enable=True, hour=0) -> None:
    assert api.put("/account/email/address", json={"address": ADDRESS}).status_code == 200
    assert api.post("/account/email/code").status_code == 200
    service.tick()
    r = api.post("/account/email/verify", json={"code": code_from(sink)})
    assert r.status_code == 200 and r.json()["verified"], r.text
    prefs = {"attention": True, "follow_ups": True, "digest_hour_utc": hour}
    assert api.put("/account/email/preferences", json=prefs).status_code == 200
    if enable:
        assert api.post("/account/email/enable").json()["enabled"] is True
    sink.reset()


def due_follow_up(api: Api, title="Pastry Chef (fictional)", employer="Bread Co (fictional)"):
    job = api.post("/jobs", json={"title": title, "employer": employer}).json()["job"]
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    applied = {"to": "submitted_unconfirmed", "reason": "I applied on the website"}
    assert api.post(f"/applications/{app_id}/transition", json=applied).status_code == 200
    remind = {"action": "remind", "remind_on": followups.today().isoformat()}
    assert api.post(f"/applications/{app_id}/follow-up", json=remind).status_code == 200
    return app_id


# ------------------------------------------------------------------------------ opting in


def test_off_by_default_nothing_is_ever_sent(api, sink, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_enabled", False)
    view = api.get("/account/email").json()
    assert (view["configured"], view["enabled"], view["address"]) == (False, False, None)
    assert api.put("/account/email/address", json={"address": ADDRESS}).status_code == 200
    for path in ("/account/email/code", "/account/email/enable"):
        r = api.post(path)
        assert r.status_code == 409 and "(reason: email_not_configured)" in r.text
    due_follow_up(api)
    assert service.tick() == {"recovered": 0, "enqueued": 0, "dispatched": 0}
    assert sink.connections == 0 and deliveries(uid(api)) == []


def test_turning_it_on_needs_a_verified_address_entered_in_the_app(api, sink):
    r = api.post("/account/email/enable")
    assert r.status_code == 409 and "(reason: address_unverified)" in r.text
    api.put("/account/email/address", json={"address": ADDRESS})
    assert "(reason: address_unverified)" in api.post("/account/email/enable").text
    assert api.post("/account/email/code").status_code == 200
    service.tick()
    (msg,) = sink.received()
    assert msg["to"] == [ADDRESS] and msg["subject"] == "NoEfforts: your verification code"
    wrong = "000000" if code_from(sink) != "000000" else "111111"
    r = api.post("/account/email/verify", json={"code": wrong})
    assert r.status_code == 400 and "(reason: code_wrong)" in r.text
    assert api.post("/account/email/verify", json={"code": code_from(sink)}).json()["verified"]
    assert api.post("/account/email/enable").json()["enabled"] is True


def test_codes_expire_run_out_and_are_limited_and_addresses_are_checked(api, sink):
    for bad, code in [("not an address", "address_invalid"),
                      (f"{ADDRESS}\r\nBcc: someone@example.com", "address_invalid"),
                      ("sam@real-mail.test", "address_domain")]:  # fmt: skip
        r = api.put("/account/email/address", json={"address": bad})
        assert r.status_code == 409 and f"(reason: {code})" in r.text
    api.put("/account/email/address", json={"address": ADDRESS})
    api.post("/account/email/code")
    service.tick()
    with SessionLocal() as db:
        db.execute(update(EmailSettings).values(code_expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    r = api.post("/account/email/verify", json={"code": code_from(sink)})
    assert "(reason: code_expired)" in r.text
    api.post("/account/email/code")
    service.tick()
    for _ in range(service.MAX_CODE_ATTEMPTS):
        api.post("/account/email/verify", json={"code": "999999x"})
    r = api.post("/account/email/verify", json={"code": code_from(sink)})
    assert "(reason: code_attempts)" in r.text
    for _ in range(service.MAX_CODE_SENDS_PER_DAY - 2):
        assert api.post("/account/email/code").status_code == 200
    assert "(reason: code_limit)" in api.post("/account/email/code").text


def test_a_new_address_needs_verifying_again_and_cancels_what_is_pending(api, sink):
    verified(api, sink)
    api.post("/account/email/code")  # pending, not sent yet
    r = api.put("/account/email/address", json={"address": "other.synthetic@example.com"})
    view = r.json()
    assert (view["verified"], view["enabled"]) == (False, False)
    (d,) = [d for d in deliveries(uid(api), "verification") if d.status != "sent"]
    assert (d.status, d.outcome_code) == ("cancelled", "recipient_changed")
    service.tick()
    assert sink.received() == []


# ------------------------------------------------------------------------------ the digest


def test_the_digest_says_only_the_category_and_links_to_the_tracker(api, sink):
    api.put("/profile", json={"full_name": "Sam Synthetic", "links": []})
    verified(api, sink)
    app_id = due_follow_up(api)
    assert service.tick()["enqueued"] == 1
    (msg,) = sink.received()
    assert msg["to"] == [ADDRESS]
    assert msg["subject"] == "NoEfforts reminders: 1 due"
    assert "Follow-ups due: 1" in msg["body"]
    assert f"A follow-up is due: http://127.0.0.1:3100/tracker?highlight={app_id}" in msg["body"]
    for private in ("Pastry Chef", "Bread Co", "Sam Synthetic", "Kind regards", "Following up"):
        assert private not in msg["body"] + msg["subject"], private
    assert "never emails employers or recruiters" in msg["body"]


def test_attention_items_are_their_own_category_and_choices_are_respected(api, sink, monkeypatch):
    verified(api, sink)
    app_id = str(uuid.uuid4())
    items = [
        {"key": "attempt:1", "kind": "failure", "needs_action": True, "read": False,
         "application_id": app_id},
        {"key": "rehearsal:2", "kind": "rehearsal", "needs_action": False, "read": False,
         "application_id": app_id},
        {"key": "follow_up:3", "kind": "follow_up", "needs_action": True, "read": False,
         "application_id": app_id},
        {"key": "attempt:4", "kind": "failure", "needs_action": True, "read": True,
         "application_id": app_id},
    ]  # fmt: skip
    monkeypatch.setattr("app.modules.notifications.service.feed", lambda db, user_id: items)
    with SessionLocal() as db:
        row = service.settings_for(db, uid(api))

        def keys():
            return [i["key"] for i in service.digest_items(db, uid(api), row)]

        assert keys() == ["attempt:1", "follow_up:3"]
        row.follow_ups = False
        assert keys() == ["attempt:1"]
        row.attention, row.follow_ups = False, True
        assert keys() == ["follow_up:3"]


def test_one_digest_a_day_and_an_item_is_never_emailed_twice(api, sink):
    verified(api, sink)
    first = due_follow_up(api)
    service.tick()
    service.tick()
    assert len(sink.received()) == 1
    tomorrow = utcnow() + timedelta(days=1)
    assert service.tick(now=tomorrow)["enqueued"] == 0  # the same item: already emailed
    second = due_follow_up(api, title="Baker (fictional)")
    service.tick(now=tomorrow)
    assert len(sink.received()) == 2
    body = sink.received()[-1]["body"]
    assert second in body and first not in body


def test_an_item_read_in_the_app_is_not_emailed(api, sink):
    verified(api, sink)
    due_follow_up(api)
    keys = [i["key"] for i in api.get("/notifications").json()["items"]]
    api.post("/notifications/read", json={"keys": keys})
    assert service.tick()["enqueued"] == 0 and sink.received() == []


def test_before_the_hour_nothing_is_sent(api, sink):
    verified(api, sink, hour=23)
    due_follow_up(api)
    early = utcnow().replace(hour=0, minute=5)
    assert service.tick(now=early)["enqueued"] == 0 and sink.received() == []


# ------------------------------------------------------------------------------ opting out


def test_opting_out_or_removing_the_address_before_dispatch_cancels(api, sink):
    verified(api, sink)
    due_follow_up(api)
    with SessionLocal() as db:
        assert service.enqueue_digests(db) == 1
        db.commit()
    api.post("/account/email/disable")
    (d,) = deliveries(uid(api))
    assert (d.status, d.outcome_code) == ("cancelled", "opted_out")
    service.tick()
    assert sink.received() == [] and sink.connections == 0


def test_deleting_the_account_before_dispatch_sends_nothing(api, sink):
    verified(api, sink)
    due_follow_up(api)
    with SessionLocal() as db:
        service.enqueue_digests(db)
        db.commit()
    (d,) = deliveries(uid(api))
    confirm = {"password": "correct-horse-1", "confirmation": "delete my account"}
    assert api.post("/account/delete", json=confirm).status_code == 204
    assert service.dispatch_one(d.id) == "skipped"
    service.tick()
    assert sink.received() == [] and sink.connections == 0
    with SessionLocal() as db:
        assert db.scalars(select(EmailSettings)).all() == []
        assert db.scalars(select(EmailDelivery)).all() == []


# ------------------------------------------------------------------------------ delivery


def _queued(api, sink) -> uuid.UUID:
    verified(api, sink)
    due_follow_up(api)
    with SessionLocal() as db:
        service.enqueue_digests(db)
        db.commit()
    (d,) = deliveries(uid(api))
    return d.id


def _status(delivery_id) -> EmailDelivery:
    with SessionLocal() as db:
        return db.get(EmailDelivery, delivery_id)


def test_two_workers_for_one_delivery_send_it_once(api, sink):
    did = _queued(api, sink)
    out, barrier = [], threading.Barrier(2)

    def worker(name):
        barrier.wait()
        out.append(service.dispatch_one(did, name))

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(out) == ["sent", "skipped"]
    assert service.dispatch_one(did, "w3") == "skipped"
    assert len(sink.received()) == 1 and _status(did).attempts == 1


def test_a_definite_transient_refusal_is_retried_a_bounded_number_of_times(api, sink):
    did = _queued(api, sink)
    sink.mode = "tempfail_rcpt"
    later = utcnow()
    for n in range(1, 4):
        later += timedelta(hours=1)
        service.dispatch_one(did, now=later)
        d = _status(did)
        assert d.attempts == n and d.outcome_code == "rcpt_4xx"
    assert d.status == "failed"
    assert service.dispatch_one(did, now=later + timedelta(days=1)) == "skipped"
    assert sink.received() == []


def test_a_refusal_then_acceptance_is_sent_once(api, sink):
    did = _queued(api, sink)
    sink.mode = "tempfail_once"
    assert service.dispatch_one(did) == "pending"
    assert service.dispatch_one(did) == "skipped"  # backing off: not yet
    assert service.dispatch_one(did, now=utcnow() + timedelta(minutes=5)) == "sent"
    assert len(sink.received()) == 1


@pytest.mark.parametrize(("mode", "code"), [("permfail_rcpt", "rcpt_5xx")])
def test_a_permanent_refusal_fails_and_is_not_retried(api, sink, mode, code):
    did = _queued(api, sink)
    sink.mode = mode
    assert service.dispatch_one(did) == "failed"
    assert _status(did).outcome_code == code
    service.tick(now=utcnow() + timedelta(days=1))
    assert sink.received() == [] and _status(did).attempts == 1


def test_a_refused_connection_is_a_definite_failure(api, sink):
    did = _queued(api, sink)
    sink.mode = "refuse_connect"
    assert service.dispatch_one(did) == "pending"
    assert _status(did).outcome_code in ("before_data", "connect_failed")
    assert sink.received() == []


@pytest.mark.parametrize("mode", ["drop_after_data", "slow_after_data"])
def test_a_possible_acceptance_is_uncertain_and_never_resent(api, sink, mode):
    did = _queued(api, sink)
    sink.mode = mode  # the sink keeps the message, but NoEfforts gets no answer in time
    assert service.dispatch_one(did) == "uncertain"
    assert _status(did).outcome_code == "lost_after_data"
    sink.mode = "normal"
    for days in (0, 1, 2):
        service.tick(now=utcnow() + timedelta(days=days, minutes=5))
    assert len(sink.received()) == 1  # the one the server may have accepted, never a second


def test_a_worker_lost_while_sending_leaves_it_uncertain(api, sink):
    did = _queued(api, sink)
    with SessionLocal() as db:
        db.execute(update(EmailDelivery).where(EmailDelivery.id == did).values(
            status="sending", lease_until=utcnow() - timedelta(seconds=1)))  # fmt: skip
        db.commit()
    assert service.tick()["recovered"] == 1
    d = _status(did)
    assert (d.status, d.outcome_code) == ("uncertain", "worker_lost")
    assert sink.received() == []


def test_a_late_result_after_recovery_is_fenced(api, sink, monkeypatch):
    did = _queued(api, sink)

    class Slow:
        def send(self, message, recipient):
            service.recover_stale(utcnow() + timedelta(hours=1))  # the lease ran out meanwhile
            return service.SendResult("accepted", "accepted")

    monkeypatch.setattr(service, "transport", lambda: Slow())
    assert service.dispatch_one(did) == "fenced"
    assert _status(did).status == "uncertain"


# ------------------------------------------------------------------------------ boundaries


def test_another_account_and_api_tokens_never_reach_your_email_settings(api, other_api, sink):
    verified(api, sink)
    assert other_api.get("/account/email").json()["address"] is None
    made = api.post("/account/tokens", json={"label": "laptop", "scopes": ["read"]})
    token = made.json()["token"]
    bare = Api()
    for method, path in [("get", "/account/email"), ("post", "/account/email/disable"),
                         ("delete", "/account/email")]:  # fmt: skip
        r = getattr(bare.client, method)(path, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403 and "token_session_only" in r.text, path
    assert api.client.post("/account/email/disable").status_code == 403  # no CSRF token
    assert api.get("/account/email").json()["enabled"] is True


def test_reminders_never_change_an_application_or_mark_a_follow_up_done(api, sink):
    verified(api, sink)
    app_id = due_follow_up(api)

    def snapshot():
        with SessionLocal() as db:
            a = db.get(Application, uuid.UUID(app_id))
            events = db.scalars(select(ApplicationEvent.id).where(
                ApplicationEvent.application_id == a.id)).all()  # fmt: skip
            f = db.scalar(select(FollowUp).where(FollowUp.application_id == a.id))
            return a.state, a.outcome, a.lock_version, sorted(map(str, events)), f.followed_up_on

    before = snapshot()
    service.tick()
    api.get(f"/applications/{app_id}")  # what the emailed link's page reads
    api.get("/follow-ups")
    assert snapshot() == before and before[-1] is None
    assert len(sink.received()) == 1


def test_nothing_is_ever_emailed_to_anyone_but_the_verified_owner():
    """The only send is in mail/service.py, to the address read from your settings; the
    follow-up draft is never handed to the mail module."""
    app = ROOT / "backend" / "app"
    senders = [p for p in app.rglob("*.py") if ".send(message" in p.read_text()]
    assert [str(p.relative_to(app)) for p in senders] == ["modules/mail/service.py"]
    mail = "\n".join(p.read_text() for p in (app / "modules" / "mail").glob("*.py"))
    # Never the follow-up module (its draft is for you to copy) or a job's records.
    assert "modules.followups" not in mail and "modules.jobs" not in mail


def test_logs_audit_and_export_keep_no_address_code_or_message(api, sink, caplog):
    caplog.set_level(logging.DEBUG)
    verified(api, sink)
    code_mail = None  # the code was in the email only
    due_follow_up(api)
    service.tick()
    text = caplog.text
    for secret in (ADDRESS, "verification code", "NoEfforts reminders", "tracker?highlight"):
        assert secret not in text, secret
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.action == "email.update")
        metas = [e.meta for e in db.scalars(q)]
    assert metas and all(set(m) == {"change"} for m in metas) and ADDRESS not in json.dumps(metas)
    files = unzip(api.get("/account/export").content)
    tables = json.loads(files["noefforts-export.json"])["tables"]
    (s,) = tables["email_settings"]
    assert s["address"] == ADDRESS and "code_digest" not in s
    assert tables["email_deliveries"] and all(
        "recipient_ref" not in d and "generation" not in d for d in tables["email_deliveries"]
    )
    stored = json.dumps(tables["email_deliveries"])
    assert "NoEfforts reminders" not in stored and code_mail is None


def test_the_configuration_is_checked_before_anything_is_sent(monkeypatch):
    s = get_settings()
    assert service.config_problem() is None
    monkeypatch.setattr(s, "email_from", "not an address")
    assert service.config_problem() == "email_config_incomplete"
    monkeypatch.setattr(s, "email_from", "noefforts@example.com")
    monkeypatch.setattr(s, "public_base_url", "http://127.0.0.1:3100/some/path")
    assert service.config_problem() == "email_base_url_invalid"
    monkeypatch.setattr(s, "public_base_url", "http://127.0.0.1:3100")
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "email_smtp_host", "relay.example.com")
    assert service.config_problem() == "email_tls_required"
    monkeypatch.setattr(s, "email_smtp_starttls", True)
    assert service.config_problem() is None
