"""Keyed audit references (audit/service.ref, version 2) and the v2 repair (migration 7a1e4c2b9d30).

References are HMAC-SHA-256 over a domain label, the user's id and the identifier, keyed by the
server-held NOEFFORTS_AUDIT_REF_KEY (a test-only key here, set in conftest). Synthetic data
only; nothing contacts anything external."""

import json
import re
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit import service
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditKeyMissing, record, ref, sanitize
from tests.test_audit_repair import alembic, disposable, repair_line  # noqa: F401 (fixture)

KEY = get_settings().audit_ref_key.get_secret_value()
LEGACY = re.compile(r"ref:[0-9a-f]{12}(?![0-9a-f])")
U1, U2 = uuid.UUID(int=1), uuid.UUID(int=2)


@pytest.fixture
def key(monkeypatch):
    def use(value: str, env: str = "test"):
        monkeypatch.setattr(get_settings(), "audit_ref_key", SecretStr(value))
        monkeypatch.setattr(get_settings(), "env", env)

    return use


# -- the reference itself -----------------------------------------------------------------------


def test_same_user_and_input_give_a_stable_versioned_reference():
    r = ref("question_8101", U1)
    assert r == ref("question_8101", U1) and re.fullmatch(r"ref:v2:[0-9a-f]{32}", r)
    assert "8101" not in r and KEY not in r
    assert ref("question_8102", U1) != r


def test_different_users_never_share_a_reference_for_the_same_input():
    assert ref("question_8101", U1) != ref("question_8101", U2)
    assert ref("question_8101", U1) != ref("question_8101", None)


def test_changing_the_key_changes_every_reference(key):
    before = ref("question_8101", U1)
    key("another-key-of-at-least-thirty-two-characters")
    assert ref("question_8101", U1) != before


def test_a_reference_is_not_the_legacy_unkeyed_hash():
    import hashlib

    legacy = "ref:" + hashlib.sha256(b"question_8101").hexdigest()[:12]
    assert legacy[4:] not in ref("question_8101", U1)
    assert sanitize({"field_ref": legacy}, U1) == {"field_ref": "[omitted]"}
    assert sanitize({"refs": ["ok", legacy]}, U1) == {"refs": "[omitted]"}


# -- the key is mandatory, server-held and never shown ------------------------------------------


@pytest.mark.parametrize("value", ["", "too-short"])
def test_a_missing_or_short_key_fails_closed_without_showing_it(key, value):
    key(value)
    with pytest.raises(AuditKeyMissing) as e:
        ref("question_8101", U1)
    assert "NOEFFORTS_AUDIT_REF_KEY" in str(e.value)
    assert (not value or value not in str(e.value)) and KEY not in str(e.value)
    from app.main import create_app

    with pytest.raises(AuditKeyMissing):  # the API refuses to start
        create_app()


def test_production_refuses_a_test_only_key(key):
    key("test-only-but-long-enough-to-pass-the-length-check", env="production")
    with pytest.raises(AuditKeyMissing) as e:
        service.check_ref_key()
    assert "test-only-but" not in str(e.value)
    key("a-production-key-that-is-at-least-32-characters-long", env="production")
    service.check_ref_key()


def test_the_key_is_not_in_the_settings_repr():
    s = get_settings()
    assert KEY not in repr(s) and KEY not in str(s.model_dump())


# -- end to end: stored rows ---------------------------------------------------------------------


def test_stored_references_are_user_scoped_and_hold_no_raw_key_or_secret(api, other_api):
    u1 = uuid.UUID(api.get("/auth/me").json()["user_id"])
    u2 = uuid.UUID(other_api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        for uid in (u1, u1, u2):
            record(db, uid, "test.event", "job", None, field="question_8101")
        db.commit()
        rows = db.query(AuditEvent).filter_by(action="test.event").order_by(AuditEvent.user_id)
        by_user = {}
        for r in rows:
            by_user.setdefault(r.user_id, set()).add(r.meta["field_ref"])
    assert by_user[u1] == {ref("question_8101", u1)} and by_user[u2] == {ref("question_8101", u2)}
    assert by_user[u1] != by_user[u2]
    dump = json.dumps({str(k): sorted(v) for k, v in by_user.items()})
    assert "question_8101" not in dump and KEY not in dump


# -- the v2 repair migration, through the Alembic command line -----------------------------------

V1_HEAD = "c303eee5a3c9"


def seed_users(conn) -> tuple[uuid.UUID, uuid.UUID]:
    ids = (uuid.uuid4(), uuid.uuid4())
    for i, uid in enumerate(ids):
        conn.execute(
            text(
                "insert into users (id, email, password_hash, created_at, updated_at) "
                "values (:u, :e, 'x', now(), now())"
            ),
            {"u": uid, "e": f"repair.{i}@example.com"},
        )
    return ids


def test_the_v2_migration_removes_legacy_references_and_is_idempotent(disposable):  # noqa: F811
    import hashlib

    def legacy(v: str) -> str:
        return "ref:" + hashlib.sha256(v.encode()).hexdigest()[:12]

    alembic("upgrade", V1_HEAD)
    with disposable.begin() as c:
        u1, u2 = seed_users(c)
        rows = [  # (user, stored meta, expected meta)
            (u1, {"field_ref": legacy("question_8101")}, {"field_ref": "[omitted]"}),
            (u2, {"field_ref": legacy("question_8101"), "reason_code": "invented_numbers"},
             {"field_ref": "[omitted]", "reason_code": "invented_numbers"}),
            (u1, {"other_ref": legacy("why_us"), "version": 2},
             {"other_ref": "[omitted]", "version": 2}),
            (u1, {"refs": [legacy("question_8104"), "ok"]}, {"refs": "[omitted]"}),
            (u1, {"field": "question_8101"}, {"field_ref": ref("question_8101", u1)}),
            (u2, {"field": "question_8101"}, {"field_ref": ref("question_8101", u2)}),
            (u1, {"field_ref": ref("question_8105", u1)}, {"field_ref": ref("question_8105", u1)}),
            (u2, {"route": "manual", "reason_code": "no_form_captured"},
             {"route": "manual", "reason_code": "no_form_captured"}),
        ]  # fmt: skip
        ids = []
        for uid, meta, _ in rows:
            i = uuid.uuid4()
            c.execute(
                text(
                    "insert into audit_events (id, user_id, action, entity_type, meta, "
                    "created_at) values (:i, :u, 'legacy.event', 'application', "
                    "cast(:m as json), now())"
                ),
                {"i": i, "u": uid, "m": json.dumps(meta)},
            )
            ids.append(i)
    changed = sum(m != e for _, m, e in rows)

    out = alembic("upgrade", "head")
    expected_line = f"audit reference repair v2: {len(rows)} row(s) scanned, {changed} changed"
    assert repair_line(out, "audit reference repair") == expected_line

    def stored():
        with disposable.connect() as c:
            got = dict(c.execute(text("select id, meta from audit_events")).all())
        return [got[i] for i in ids]

    after = stored()
    assert after == [e for _, _, e in rows]
    blob = json.dumps(after) + out
    assert not LEGACY.search(blob), "a legacy reference was left in place"
    for raw in ("question_8101", "question_8104", "question_8105", "why_us", KEY):
        assert raw not in blob, raw
    assert after[4]["field_ref"] != after[5]["field_ref"]  # two users, same question

    # Irreversible and idempotent: stepping back restores nothing; running again changes nothing.
    alembic("downgrade", V1_HEAD)
    assert stored() == after
    out = alembic("upgrade", "head")
    assert repair_line(out, "audit reference repair") == (
        f"audit reference repair v2: {len(rows)} row(s) scanned, 0 changed")  # fmt: skip
    assert stored() == after and KEY not in out
