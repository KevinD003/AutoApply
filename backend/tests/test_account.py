"""Full data export and account deletion (priority B, D77; docs/account-deletion.md).

Two synthetic accounts, each with a profile, a document, jobs, an application submitted to the
local receiver (attempt, evidence, events), a sensitive answer disclosed with a keyed consent,
saved answers and audit events. The export of one holds all of its records and none of the
other's; deletion removes every row that names it, its files and its sessions, and nothing of
the other account. Synthetic data and the local receiver only."""

import hashlib
import io
import json
import uuid
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update

from app.core.config import get_settings
from app.core.db import Base, SessionLocal, utcnow
from app.modules.account import deletion, export, policy
from app.modules.discovery.models import DiscoveryWatch
from app.modules.documents.models import Document
from app.modules.documents.storage import get_storage
from app.modules.execution import runner
from app.modules.execution import service as svc
from app.modules.execution.models import AttemptState, ExecutionAttempt, OutboxMessage
from app.modules.identity.models import User, UserSession
from tests.conftest import Api
from tests.execution_harness import PDF, Receiver, prepared_application, queue
from tests.test_lock_order import claimed, no_errors, race

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
WOMAN = {"label": "Woman"}
CONFIRM = {"password": "correct-horse-1", "confirmation": "delete my account"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def me(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def populated(api, receiver, marker: str) -> dict:
    """One account's worth of synthetic records, with `marker` in its free text."""
    app_id = prepared_application(api, receiver, sensitive={"gender": (WOMAN, "disclose")})
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    api.put("/profile", json={"summary": f"Summary {marker}", "phone": "+1 555 0100"})
    job = api.post(
        "/jobs", json={"url": f"https://careers.example.com/{marker}", "title": f"Role {marker}"}
    ).json()["job"]
    r = api.post("/documents", files={"file": (f"{marker}.txt", f"Notes {marker}".encode(),
                                               "text/plain")})  # fmt: skip
    assert r.status_code == 201, r.text
    return {"app_id": app_id, "job_id": job["id"], "doc_id": r.json()["id"]}


def watch(user_id: uuid.UUID) -> DiscoveryWatch:
    now = utcnow()
    return DiscoveryWatch(user_id=user_id, provider="freehire", query="support",
                          interval_seconds=60, not_before=now - timedelta(minutes=1),
                          not_after=now + timedelta(days=1), retention="keep",
                          next_check_at=now - timedelta(seconds=1))  # fmt: skip


def unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def naming(user_id: uuid.UUID) -> dict[str, int]:
    """Rows that name the account, in every table: by user_id, through a parent that has one,
    and the users row itself. Tables reached only through a parent are listed in PARENT, plus
    the outbox (through its attempt)."""
    out = {}
    parents = export.PARENT | {"outbox_messages": ("attempt_id", "execution_attempts")}
    with SessionLocal() as db:
        for t in Base.metadata.sorted_tables:
            if t.name == "users":
                q = select(func.count()).select_from(t).where(t.c.id == user_id)
            elif "user_id" in t.c:
                q = select(func.count()).select_from(t).where(t.c.user_id == user_id)
            else:
                fk, parent = parents[t.name]
                p = Base.metadata.tables[parent]
                q = (
                    select(func.count())
                    .select_from(t)
                    .where(t.c[fk].in_(select(p.c.id).where(p.c.user_id == user_id)))
                )
            out[t.name] = db.scalar(q)
    return out


# ---------------------------------------------------------------------------- inventory


def test_every_table_and_column_has_an_export_decision():
    """A table or column added later fails here until it is exported or left out with why."""
    assert set(export.EXPORTED) | set(export.EXCLUDED_TABLES) == set(Base.metadata.tables)
    assert not set(export.EXPORTED) & set(export.EXCLUDED_TABLES)
    for name, cols in export.EXPORTED.items():
        table = {c.name for c in Base.metadata.tables[name].columns}
        left_out = set(export.EXCLUDED_COLUMNS.get(name, {}))
        assert set(cols) | left_out == table and not set(cols) & left_out, name
        assert len(cols) == len(set(cols)), name
    assert set(export.EXCLUDED_COLUMNS) <= set(export.EXPORTED)
    for name in export.EXPORTED:
        t = Base.metadata.tables[name]
        assert name == "users" or "user_id" in t.c or name in export.PARENT, name


def test_every_table_that_names_an_account_is_deleted_with_it():
    """In the migrated database (not only the models): every foreign key to users, and every
    key from a table without user_id to its parent, deletes in cascade."""
    rule = text(
        "select tc.table_name, kcu.column_name, ccu.table_name, rc.delete_rule "
        "from information_schema.referential_constraints rc "
        "join information_schema.table_constraints tc on tc.constraint_name = rc.constraint_name "
        "join information_schema.key_column_usage kcu on kcu.constraint_name = rc.constraint_name "
        "join information_schema.constraint_column_usage ccu "
        "on ccu.constraint_name = rc.unique_constraint_name"
    )
    with SessionLocal() as db:
        rules = {(t, c): (target, r) for t, c, target, r in db.execute(rule)}
    for t in Base.metadata.sorted_tables:
        if t.name == "users":
            continue
        if "user_id" in t.c:
            assert rules[(t.name, "user_id")] == ("users", "CASCADE"), t.name
    parents = export.PARENT | {"outbox_messages": ("attempt_id", "execution_attempts")}
    for name, (fk, parent) in parents.items():
        assert rules[(name, fk)] == (parent, "CASCADE"), name


# ---------------------------------------------------------------------------- export


def test_the_export_holds_everything_of_the_account_and_nothing_of_another(
    api, other_api, receiver
):
    mine = populated(api, receiver, "MARKER-MINE-7f3a")
    theirs = populated(other_api, receiver, "MARKER-THEIRS-91c2")
    r = api.get("/account/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["cache-control"] == "no-store"
    files = unzip(r.content)
    data = json.loads(files["noefforts-export.json"])
    assert data["format"] == "noefforts-export" and data["format_version"] == 1
    t = data["tables"]
    # Every kind of record is there.
    for name in ("users", "candidate_profiles", "work_authorizations", "documents", "jobs",
                 "applications", "application_inputs", "application_packages",
                 "package_approvals", "execution_attempts", "attempt_events",
                 "execution_evidence", "application_events", "audit_events",
                 "fact_versions"):  # fmt: skip
        assert t[name], name
    assert {j["id"] for j in t["jobs"]} >= {mine["job_id"]}
    assert t["candidate_profiles"][0]["summary"] == "Summary MARKER-MINE-7f3a"
    assert {a["state"] for a in t["execution_attempts"]} == {"confirmed"}
    # Each document's file, byte for byte, named by its id.
    for doc in t["documents"]:
        assert doc["file"] == f"documents/{doc['id']}{export.EXTENSIONS[doc['content_type']]}"
        assert hashlib.sha256(files[doc["file"]]).hexdigest() == doc["sha256"]
    assert any(files[d["file"]] == PDF for d in t["documents"])
    # Nothing of the other account, anywhere in the archive.
    blob = b"".join(files.values())
    assert b"MARKER-THEIRS" not in blob and b"MARKER-MINE" in blob
    for value in (theirs["app_id"], theirs["job_id"], theirs["doc_id"], str(me(other_api))):
        assert value.encode() not in blob
    assert {u["id"] for u in t["users"]} == {str(me(api))}
    # The export was audited for this account, with counts only.
    with SessionLocal() as db:
        meta = db.execute(
            text("select meta from audit_events where action = 'account.export'")
        ).scalar_one()
    assert set(meta) == {"tables", "rows", "documents"}


def test_the_export_holds_no_secret_and_no_keyed_material(api, receiver):
    populated(api, receiver, "MARKER-S")
    files = unzip(api.get("/account/export").content)
    blob = b"".join(files.values())
    uid = me(api)
    with SessionLocal() as db:
        user = db.get(User, uid)
        secrets = [user.password_hash]
        for s in db.scalars(select(UserSession).where(UserSession.user_id == uid)):
            secrets += [s.token_hash, s.csrf_token]
        secrets += list(db.scalars(select(Document.storage_key).where(Document.user_id == uid)))
        paths = [a.path_ref for a in db.scalars(select(ExecutionAttempt)) if a.path_ref]
        digests = [
            m["value_digest"]
            for m in db.execute(text("select meta from application_inputs")).scalars()
            if m and "value_digest" in m
        ]
        refs = [
            m
            for m in db.scalars(select(text("meta")).select_from(text("audit_events")))
            if "ref:v2:" in json.dumps(m)
        ]
    assert paths and digests and refs  # the account holds keyed material; none is exported
    secrets += paths + digests + [get_settings().audit_ref_key.get_secret_value()]
    for s in secrets:
        assert s.encode() not in blob, "a secret or keyed value is in the export"
    assert b"ref:v2:" not in blob
    # The key names appear once, in `left_out`, which says what was left out; never in a record.
    records = json.dumps(json.loads(files["noefforts-export.json"])["tables"])
    for key in ("value_digest", "consent_digests", "password_hash", "storage_key", "path_ref"):
        assert f'"{key}"' not in records, key


def test_the_scrubber_leaves_out_keyed_values_inside_json():
    keyed = "ref:v2:" + "a" * 32
    value = {
        "field_ref": keyed,
        "value_digest": "x",
        "consent_digests": {"g": "y"},
        "list": [keyed, "ref:" + "b" * 12, "kept"],
        "nested": {"ok": "ref: not a ref"},
    }
    assert export._scrub(value) == {
        "field_ref": "[keyed reference left out]",
        "list": ["kept"],
        "nested": {"ok": "ref: not a ref"},
    }


def test_the_export_needs_a_session(api):
    assert Api().get("/account/export").status_code == 401


def test_a_missing_file_is_reported_not_fatal(api):
    api.post("/documents", files={"file": ("a.txt", b"synthetic", "text/plain")})
    with SessionLocal() as db:
        key = db.scalar(select(Document.storage_key))
    get_storage().delete(key)
    files = unzip(api.get("/account/export").content)
    (doc,) = json.loads(files["noefforts-export.json"])["tables"]["documents"]
    assert doc["file"] is None
    assert b"1 document file(s) could not be read" in files["README.txt"]


# ---------------------------------------------------------------------------- deletion


def test_deletion_needs_the_password_and_the_phrase(api):
    uid = me(api)
    for body, code in (
        ({"password": "correct-horse-1", "confirmation": "yes"}, 400),
        ({"password": "wrong-password-9", "confirmation": "delete my account"}, 403),
    ):
        r = api.post("/account/delete", json=body)
        assert r.status_code == code, r.text
        assert "(reason: deletion_" in r.json()["detail"]
    assert Api().post("/account/delete", json=CONFIRM).status_code == 401  # no session
    assert naming(uid)["users"] == 1


def test_deletion_removes_every_row_file_and_session_of_the_account_only(api, other_api, receiver):
    mine = populated(api, receiver, "MARKER-MINE")
    populated(other_api, receiver, "MARKER-THEIRS")
    uid, other = me(api), me(other_api)
    with SessionLocal() as db:
        db.add(watch(uid))
        db.commit()
        keys = list(db.scalars(select(Document.storage_key).where(Document.user_id == uid)))
        their_keys = list(db.scalars(select(Document.storage_key).where(Document.user_id == other)))
    before, theirs_before = naming(uid), naming(other)
    assert sum(before.values()) > 40 and before["discovery_watches"] == 1
    preview = api.get("/account/deletion").json()
    assert preview["counts"]["applications"] == 1 and preview["blocked_by"] == []
    assert preview["submitted_applications"] == 1
    assert preview["retained_in_database"] == list(policy.RETAINED_IN_DATABASE) == []
    assert {o["what"] for o in preview["outside_noefforts"]} >= {"employers", "backups"}

    token = api.client.cookies.get("ne_session")
    r = api.post("/account/delete", json=CONFIRM)
    assert r.status_code == 204, r.text
    assert "ne_session" in r.headers.get("set-cookie", "")
    assert sum(naming(uid).values()) == 0, {k: v for k, v in naming(uid).items() if v}
    assert naming(other) == theirs_before
    storage = get_storage()
    for key in keys:
        with pytest.raises(FileNotFoundError):
            storage.get(key)
    for key in their_keys:
        storage.get(key)  # the other account's files are untouched
    # Access ends: the old session token is refused, and the old password signs nobody in.
    replay = Api()
    replay.client.cookies.set("ne_session", token)
    assert replay.get("/auth/me").status_code == 401
    assert replay.get(f"/applications/{mine['app_id']}").status_code == 401
    login = Api().client.post("/auth/login", json={"email": "synthetic.user@example.com",
                                                   "password": "correct-horse-1"})  # fmt: skip
    assert login.status_code == 401
    # The address can sign up again, as a new account with nothing in it.
    fresh = Api()
    fresh.register()
    assert fresh.get("/jobs").json()["total"] == 0
    assert fresh.get("/documents").json() == []
    assert me(fresh) != uid


def test_deletion_is_refused_while_a_submission_may_be_in_flight(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    uid = me(api)
    before = naming(uid)
    for state in (AttemptState.sending, AttemptState.awaiting_code):
        with SessionLocal() as db:
            db.execute(
                update(ExecutionAttempt).where(ExecutionAttempt.id == aid).values(state=state)
            )
            db.commit()
        assert api.get("/account/deletion").json()["blocked_by"] == [
            "deletion_submission_in_flight"
        ]
        r = api.post("/account/delete", json=CONFIRM)
        assert r.status_code == 409, r.text
        assert r.json()["detail"].endswith("(reason: deletion_submission_in_flight)")
        assert naming(uid) == before
    assert api.get("/auth/me").status_code == 200


def test_queued_work_stops_a_pending_attempt_and_its_message_do_nothing(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = uuid.UUID(queue(api, app_id))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OutboxMessage)) >= 1
    assert api.post("/account/delete", json=CONFIRM).status_code == 204
    published = []
    assert svc.relay_outbox(published.append) == 0 and published == []
    assert svc.claim(aid, "w1") is None  # a message already in the broker finds nothing
    assert runner.run_attempt(str(aid), "w1") != "confirmed"
    assert receiver.ledger()["accepted"] == 0


def test_a_worker_holding_an_attempt_is_fenced_out_and_never_sends(api, receiver):
    app_id, aid, gen = claimed(api, receiver)
    svc.gate_before_disclosure(aid, "w1", gen)  # it may already have typed into the page
    assert api.post("/account/delete", json=CONFIRM).status_code == 204
    with pytest.raises(svc.LostAuthority):
        svc.gate_before_send(aid, "w1", gen)
    assert svc.unknown(aid, "w1", gen, "x") is False  # every fenced write finds nothing
    assert receiver.ledger()["accepted"] == 0


def test_deletion_waits_for_a_send_gate_and_then_refuses(api, receiver, monkeypatch):
    """A deletion arriving while the send gate holds its locks waits; once the gate has
    authorized the click, the submission may be in flight, so deletion is refused."""
    app_id, aid, gen = claimed(api, receiver)
    svc.gate_before_disclosure(aid, "w1", gen)
    uid = me(api)

    def delete():
        with SessionLocal() as db:
            return deletion.delete_account(db, uid, get_storage())

    gate, second = race(
        monkeypatch,
        "gate",
        svc,
        "_gate_checks",
        lambda: svc.gate_before_send(aid, "w1", gen),
        delete,
        after=True,
    )
    no_errors(gate)
    assert isinstance(second.error, deletion.DeletionRefused)
    assert second.error.code == "deletion_submission_in_flight"
    assert naming(uid)["users"] == 1


def test_deletion_waits_for_a_disclosure_gate_and_then_the_worker_stops(api, receiver, monkeypatch):
    app_id, aid, gen = claimed(api, receiver)
    uid = me(api)

    def delete():
        with SessionLocal() as db:
            return deletion.delete_account(db, uid, get_storage())

    gate, second = race(
        monkeypatch,
        "gate",
        svc,
        "_gate_checks",
        lambda: svc.gate_before_disclosure(aid, "w1", gen),
        delete,
        after=True,
    )
    no_errors(gate, second)
    assert sum(naming(uid).values()) == 0
    with pytest.raises(svc.LostAuthority):
        svc.gate_before_send(aid, "w1", gen)
    assert receiver.ledger()["accepted"] == 0


def test_a_watch_of_a_deleted_account_is_never_checked(api, monkeypatch):
    from app.modules.discovery import service as discovery

    monkeypatch.setattr(get_settings(), "discovery_providers", ["freehire"])
    uid = me(api)
    with SessionLocal() as db:
        db.add(watch(uid))
        db.commit()
    assert api.post("/account/delete", json=CONFIRM).status_code == 204
    assert discovery.check_due_watches() == 0


# ---------------------------------------------------------------------------- documentation


def test_the_deletion_document_lists_exactly_the_reason_codes_and_policy():
    doc = (ROOT / "docs" / "account-deletion.md").read_text()
    listed = set(__import__("re").findall(r"`(deletion_[a-z_]+)`", doc))
    assert listed == set(deletion.REASONS)
    for what, _ in policy.OUTSIDE_NOEFFORTS:
        assert f"`{what}`" in doc, what
    for name in export.EXCLUDED_TABLES:
        assert f"`{name}`" in doc, name
