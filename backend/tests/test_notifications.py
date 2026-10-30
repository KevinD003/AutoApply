"""In-app notifications (priority C, D83): derived from the records they describe, one per
record, tenant-scoped, with read marks only, and never delivered outside the app. Outcomes come
from real attempts against the local synthetic receiver; rows edited by hand are labelled
simulated. Synthetic data only."""

import pathlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.db import SessionLocal, utcnow
from app.modules.execution import runner
from app.modules.execution.models import Checkpoint, ExecutionAttempt
from app.modules.notifications.models import NotificationRead
from tests.conftest import Api
from tests.execution_harness import Receiver, prepared_application, queue

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = "Local test fixture: counts for nothing on a real employer's form"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def feed(api) -> dict:
    r = api.get("/notifications")
    assert r.status_code == 200, r.text
    return r.json()


def by_kind(api, kind) -> list[dict]:
    return [i for i in feed(api)["items"] if i["kind"] == kind]


def run(api, receiver, slug="clinic", mode="normal", **kw) -> tuple[str, str, str]:
    receiver.config(mode=mode)
    app_id = prepared_application(api, receiver, slug=slug, **kw)
    aid = queue(api, app_id)
    return app_id, aid, runner.run_attempt(aid, "w1")


# ---------------------------------------------------------------------------- what is notified


def test_a_receipt_is_notified_once_with_its_evidence_class_and_a_link(api, receiver):
    app_id, aid, state = run(api, receiver)
    assert state == "confirmed"
    (item,) = feed(api)["items"]
    assert item["key"] == f"attempt:{aid}" and item["kind"] == "receipt"
    assert item["title"] == "Employer receipt received" and not item["needs_action"]
    assert item["evidence_label"] == FIXTURE  # a local test form, never called a real employer
    assert item["link"] == f"/applications/{app_id}" and item["application_id"] == app_id
    assert item["job"] == "Clinic Assistant — Example Health Clinic (fictional)"
    assert item["read"] is False
    # Derived, not stored: reading the feed again creates nothing and repeats nothing.
    assert feed(api)["items"] == [item] and feed(api)["unread"] == 1


def test_a_rehearsal_is_one_notification_not_three(api, receiver):
    """A rehearsal ends its attempt `rehearsed`, writes a record and uses up its approval: one
    notification, the rehearsal's, says so."""
    app_id, aid, state = run(api, receiver, slug="e6-a", scope="disclose_only")
    assert state == "rehearsed"
    (item,) = feed(api)["items"]
    assert item["kind"] == "rehearsal" and item["key"].startswith("rehearsal:")
    assert item["title"] == "Rehearsal completed: nothing was submitted"
    assert "nothing was submitted" in item["text"] and item["evidence_label"] == FIXTURE
    assert receiver.ledger()["acceptances"] == []


@pytest.mark.parametrize(
    "mode, state, title, needs_action",
    [
        ("drop_after_accept", "unknown", "Outcome unknown — check before doing anything", True),
        (
            "validation_fail",
            "rejected",
            "Form rejected: the employer's form refused the submission",
            True,
        ),  # fmt: skip
    ],
)
def test_a_failure_says_what_happened_and_never_promises_a_retry(
    api, receiver, mode, state, title, needs_action
):
    app_id, aid, got = run(api, receiver, mode=mode)
    assert got == state
    (item,) = feed(api)["items"]
    assert (item["kind"], item["title"], item["needs_action"]) == ("failure", title, needs_action)
    with SessionLocal() as db:
        detail = db.get(ExecutionAttempt, uuid.UUID(aid)).outcome_detail
    assert item["text"].startswith(detail)  # the attempt's own words, as on the application
    if state == "unknown":
        assert "never sent again automatically" in item["text"]
    assert "retry" not in item["text"].lower() and "will be sent" not in item["text"].lower()


def test_an_approval_that_stops_applying_is_notified_but_not_one_you_revoked(api, receiver):
    app_id = prepared_application(api, receiver)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "hear_about", "value": {"label": "Job board"}})  # fmt: skip
    assert r.status_code == 200, r.text
    (item,) = feed(api)["items"]
    assert item["kind"] == "approval_invalidated" and item["needs_action"]
    assert item["title"] == "Your approval to submit no longer applies"
    assert item["text"].startswith("Package changed in version")
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"]}
                    ).status_code == 200  # fmt: skip
    assert api.post(f"/applications/{app_id}/package/revoke").status_code == 200
    assert [i["key"] for i in feed(api)["items"]] == [item["key"]]  # you did that yourself


def test_a_verification_code_request_needs_you_until_it_ends(api, receiver):
    """Simulated rows: a checkpoint on a queued attempt, moved through its statuses by hand."""
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, uuid.UUID(aid))
        cp = Checkpoint(attempt_id=att.id, application_id=att.application_id, user_id=att.user_id,
                        expires_at=utcnow() + timedelta(minutes=10))  # fmt: skip
        db.add(cp)
        db.commit()
        cp_id = cp.id

    def item():
        (i,) = by_kind(api, "checkpoint")
        return i

    def move(**values):
        with SessionLocal() as db:
            db.execute(update(Checkpoint).where(Checkpoint.id == cp_id).values(**values))
            db.commit()

    first = item()
    assert first["key"] == f"checkpoint:{cp_id}:1" and first["needs_action"]
    assert "Enter it on the application" in first["text"]
    api.post("/notifications/read", json={"keys": [first["key"]]})
    move(status="submitted")  # you entered it: the same notification, no longer needing you
    assert item()["key"] == first["key"] and item()["read"] and not item()["needs_action"]
    move(status="open", round=2)  # the form rejected it: a new request, unread
    second = item()
    assert second["key"] == f"checkpoint:{cp_id}:2" and not second["read"]
    assert "rejected the last one" in second["text"] and second["needs_action"]
    move(expires_at=utcnow() - timedelta(seconds=1))  # still "open", but past its time
    ended = item()
    assert ended["key"] == f"checkpoint:{cp_id}:2:ended" and not ended["needs_action"]
    assert ended["title"] == "Verification not completed" and "expired" in ended["text"]


def test_nothing_is_notified_for_what_you_cancelled(api, receiver):
    app_id = prepared_application(api, receiver)
    queue(api, app_id)
    assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    assert feed(api)["items"] == []


# ---------------------------------------------------------------------------- read state


def test_read_marks_are_yours_and_another_account_cannot_see_or_touch_them(
    api, other_api, receiver
):
    _, aid, _ = run(api, receiver)
    key = f"attempt:{aid}"
    assert other_api.get("/notifications").json() == {"items": [], "total": 0, "unread": 0}
    # Another account's key is "not found", exactly like a key that never existed.
    for keys in ([key], [f"attempt:{uuid.uuid4()}"]):
        r = other_api.post("/notifications/read", json={"keys": keys})
        assert r.status_code == 404 and r.json()["detail"] == "Notification not found"
    assert api.post("/notifications/read", json={"keys": [key, "attempt:x"]}).status_code == 404
    assert feed(api)["unread"] == 1  # a refused request marked nothing
    assert api.post("/notifications/read", json={"keys": [key]}).json() == {"unread": 0}
    assert api.post("/notifications/read", json={"keys": [key]}).json() == {"unread": 0}
    assert api.get("/notifications/unread").json() == {"unread": 0}
    assert feed(api)["items"][0]["read"] is True
    assert api.post("/notifications/unread", json={"keys": [key]}).json() == {"unread": 1}
    assert api.post("/notifications/read-all").json() == {"unread": 0}
    assert api.post("/notifications/read-all").json() == {"unread": 0}
    with SessionLocal() as db:
        rows = db.scalars(select(NotificationRead)).all()
    assert [(r.item_key, str(r.user_id)) for r in rows] == [
        (key, api.get("/auth/me").json()["user_id"])
    ]


def test_reading_needs_a_session_and_its_csrf_token(api):
    assert Api().get("/notifications").status_code == 401
    r = api.client.post("/notifications/read-all")  # no CSRF header
    assert r.status_code == 403
    assert api.post("/notifications/read", json={"keys": []}).status_code == 422


def test_read_marks_are_exported_and_deleted_with_the_account(api, receiver):
    import io
    import json
    import zipfile

    _, aid, _ = run(api, receiver)
    api.post("/notifications/read-all")
    z = zipfile.ZipFile(io.BytesIO(api.get("/account/export").content))
    data = json.loads(z.read("noefforts-export.json"))
    (row,) = data["tables"]["notification_reads"]
    assert row["item_key"] == f"attempt:{aid}"
    confirm = {"password": "correct-horse-1", "confirmation": "delete my account"}
    r = api.post("/account/delete", json=confirm)
    assert r.status_code == 204, r.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(NotificationRead)) == 0


# ---------------------------------------------------------------------------- no delivery


def test_nothing_in_notifications_can_send_anything_anywhere():
    """No email, text message, push or webhook: the module imports no network, mail or task
    library, and the feed is only ever read by its own routes."""
    banned = ("smtplib", "email.", "httpx", "requests", "urllib", "socket", "celery", "twilio",
              "webpush", "firebase", "apns", "send_", ".delay(", "apply_async")  # fmt: skip
    for path in (ROOT / "backend/app/modules/notifications").glob("*.py"):
        src = path.read_text()
        hits = [b for b in banned if b in src]
        assert not hits, (path.name, hits)
    users = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "backend/app").rglob("*.py")
        if "modules.notifications" in p.read_text() and "notifications" not in p.parent.name
    ]
    # D94: the owner's email digest reads the feed; sending lives in the mail module, never here.
    assert sorted(users) == [
        "backend/app/main.py",
        "backend/app/models.py",
        "backend/app/modules/mail/service.py",
    ]


def test_every_query_of_the_feed_is_scoped_to_the_account():
    """A check on service.py's source, on top of the API tests above: each select filters by
    the account."""
    src = (ROOT / "backend/app/modules/notifications/service.py").read_text()
    assert src.count("select(") == src.count("user_id == user_id") == 6
