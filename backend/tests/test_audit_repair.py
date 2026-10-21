"""The one-way audit metadata repair (audit/repair.py, migration c303eee5a3c9).

Legacy rows are seeded with synthetic content directly in SQL, bypassing write-time sanitizing,
as rows written before it existed would be. The migration runs through the Alembic command line
against a disposable database (name ending in _migration_test), so its real output is checked.
Nothing here contacts anything external."""

import json
import logging
import os
import subprocess
import sys
import traceback
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text

from app.core.db import engine
from app.modules.audit import repair
from app.modules.audit.repair import AuditRepairError, repair_meta
from app.modules.audit.service import ref

ADMIN = os.environ.get(
    "NOEFFORTS_TEST_ADMIN_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/postgres"
)
NAME = "noefforts_audit_repair_migration_test"
URL = ADMIN.rsplit("/", 1)[0] + f"/{NAME}"
BEFORE = "955a3214d25a"  # the revision before the repair
BACKEND = os.path.join(os.path.dirname(__file__), "..")

RD = "[redacted]"
OM = "[omitted]"
# (meta as stored before write-time sanitizing, meta after the repair). The column is NOT NULL;
# None is a stored JSON null, which holds nothing and is left as it is.
LEGACY = [
    # application answers, and the question keys stored with them
    ({"field": "question_8101"}, {"field_ref": ref("question_8101", None)}),
    ({"field": "question_8104", "choice": "yes"},
     {"field_ref": ref("question_8104", None), "choice": "yes"}),
    ({"answer": "Yes", "value": "Sammy", "text": "I led a team"},
     {"answer": RD, "value": RD, "text": RD}),
    # raw draft-rejection and other free-text reasons
    ({"field": "why_us", "reason": "Draft mentions 40 nurses and 12 years not in your facts."},
     {"field_ref": ref("why_us", None), "reason": OM}),
    ({"reason": "execution method changed"}, {"reason": OM}),
    # resume / attachment contents and filenames
    ({"filename": "resume.pdf", "content": "%PDF-1.4", "attachment": "resume.pdf"},
     {"filename": RD, "content": RD, "attachment": RD}),
    # contact data and other PII
    ({"email": "sam.synthetic@example.com", "phone": "555 0100", "full_name": "Sam Synthetic",
      "address": "1 Main St Springfield", "contact": "sam.synthetic@example.com"},
     {"email": RD, "phone": RD, "full_name": RD, "address": RD, "contact": OM}),
    # credentials, headers, sessions, codes
    ({"token": "fixture-api-token", "cookie": "sid=abc", "headers": "Authorization: Bearer x",
      "password": "p", "session_id": "s1", "code": "123456"},
     {"token": RD, "cookie": RD, "headers": RD, "password": RD, "session_id": RD, "code": RD}),
    # employer names, posting titles, posting URLs and other external identifiers
    ({"employer": "Northwind", "title": "Support Specialist",
      "posting_url": "http://127.0.0.1:8799/gh2/jobs/1", "source": "http://127.0.0.1:8799/gh2/jobs/1"},
     {"employer": RD, "title": RD, "posting_url": RD, "source": OM}),
    # raw exception payloads and raw page content
    ({"exception": "ZeroDivisionError: synthetic legacy failure",
      "detail": "<div>Support Specialist</div>",
      "note": "RuntimeError: locator('#question_8101') timed out"},
     {"exception": RD, "detail": RD, "note": OM}),
    ({"weird key!": "x", "ok": 1}, {"ok": 1}),
    ("Sam Synthetic resume.pdf", {}),  # not an object at all
    (["Northwind"], {}),
    # safe metadata is kept exactly
    ({"version": 3, "provider": "greenhouse_dom", "fields": ["title", "notes"],
      "content_hash": "a" * 64, "flag": True, "rows": 2, "cost_usd": 0.0, "nothing": None},
     {"version": 3, "provider": "greenhouse_dom", "fields": ["title", "notes"],
      "content_hash": "a" * 64, "flag": True, "rows": 2, "cost_usd": 0.0, "nothing": None}),
    ({"field_ref": ref("question_8101", None)}, {"field_ref": ref("question_8101", None)}),
    # a legacy unkeyed reference (enumerable) is never kept
    ({"field_ref": "ref:" + "a1b2c3d4e5f6"}, {"field_ref": OM}),
    ({"route": "browser", "provider": "greenhouse_dom", "adapter_version": "greenhouse-dom-3+x",
      "reason_code": "browser_supported", "evidence": "fixture", "api_grant": "none"},
     {"route": "browser", "provider": "greenhouse_dom", "adapter_version": "greenhouse-dom-3+x",
      "reason_code": "browser_supported", "evidence": "fixture", "api_grant": "none"}),
    ({}, {}),
    (None, None),
]  # fmt: skip
CHANGED = sum(before != after for before, after in LEGACY)
# Raw legacy content that must not survive anywhere: rows, output, logs or exceptions.
MARKERS = ["question_8101", "question_8104", "why_us", "Sammy", "I led a team", "40 nurses",
           "execution method changed", "resume.pdf", "%PDF", "sam.synthetic@example.com",
           "555 0100", "Sam Synthetic", "Springfield", "fixture-api-token", "sid=abc", "Bearer",
           "123456", "Northwind", "Support Specialist", "/gh2/", "127.0.0.1:8799",
           "synthetic legacy", "locator(", "weird key"]  # fmt: skip
# Legacy key names, which the output must not list either.
KEYS = ["field", "employer", "posting_url", "filename", "password", "cookie", "full_name"]


def assert_clean(text_: str, keys: bool = False):
    for m in [*MARKERS, *(KEYS if keys else [])]:
        assert m not in text_, m


def seed(conn) -> list[uuid.UUID]:
    ids = []
    for before, _ in LEGACY:
        i = uuid.uuid4()
        conn.execute(
            text(
                "insert into audit_events (id, user_id, action, entity_type, entity_id, meta, "
                "created_at) values (:i, null, 'legacy.event', 'application', null, "
                "cast(:m as json), now())"
            ),
            {"i": i, "m": json.dumps(before)},
        )
        ids.append(i)
    return ids


def metas(conn, ids) -> list:
    got = dict(conn.execute(text("select id, meta from audit_events")).all())
    return [got[i] for i in ids]


# -- the repair step itself ---------------------------------------------------------------------


def test_repair_sanitizes_every_legacy_row_and_a_second_run_changes_nothing(caplog):
    caplog.set_level(logging.DEBUG)
    with engine.begin() as c:
        ids = seed(c)
    with engine.begin() as c:
        assert repair_meta(c, batch=4) == (len(LEGACY), CHANGED)  # several batches
    with engine.connect() as c:
        after = metas(c, ids)
    assert after == [a for _, a in LEGACY]
    assert_clean(json.dumps(after))
    with engine.begin() as c:
        assert repair_meta(c, batch=4) == (len(LEGACY), 0)
    with engine.connect() as c:
        assert metas(c, ids) == after
    assert_clean(caplog.text)


@pytest.mark.parametrize(
    "error",
    [
        lambda meta: ValueError(f"cannot sanitize {meta!r}"),
        lambda meta: sa.exc.StatementError(
            "update failed", "UPDATE audit_events SET meta=%(meta)s", {"meta": meta}, None
        ),
    ],
)
def test_a_failed_repair_reveals_no_legacy_content(error, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    with engine.begin() as c:
        ids = seed(c)

    def broken(meta, scope=None):
        raise error(meta)

    monkeypatch.setattr(repair, "sanitize", broken)
    with pytest.raises(AuditRepairError) as exc, engine.begin() as c:
        repair_meta(c)
    e = exc.value
    assert e.__cause__ is None and e.__context__ is None  # the original is not chained
    shown = "".join(traceback.format_exception(e)) + str(e) + repr(e.args) + caplog.text
    assert_clean(shown)
    assert type(error({})).__name__ in str(e)
    with engine.connect() as c:  # the transaction rolled back: nothing half-repaired
        assert metas(c, ids) == [b for b, _ in LEGACY]


# -- the migration, through the Alembic command line --------------------------------------------


def alembic(*args: str) -> str:
    env = dict(os.environ, NOEFFORTS_DATABASE_URL=URL)
    p = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    out = p.stdout + p.stderr
    assert p.returncode == 0, "alembic failed"  # the output itself is checked by the callers
    return out


@pytest.fixture
def disposable():
    assert NAME.endswith("_migration_test")  # never touch anything else
    admin = create_engine(ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {NAME}"))
    eng = create_engine(URL)
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)"))
    admin.dispose()


def repair_line(out: str, what: str = "audit metadata repair") -> str:
    (line,) = [x for x in out.splitlines() if what in x]
    return line.split("] ", 1)[-1]


def test_the_migration_repairs_legacy_rows_reports_counts_only_and_is_irreversible(disposable):
    alembic("upgrade", BEFORE)
    with disposable.begin() as c:
        ids = seed(c)

    out = alembic("upgrade", "head")
    n = len(LEGACY)
    assert repair_line(out) == f"audit metadata repair v1: {n} row(s) scanned, {CHANGED} changed"
    assert repair_line(out, "audit reference repair") == (
        f"audit reference repair v2: {n} row(s) scanned, 0 changed")  # fmt: skip
    assert_clean(out, keys=True)
    with disposable.connect() as c:
        after = metas(c, ids)
    assert after == [a for _, a in LEGACY]
    assert_clean(json.dumps(after))

    # Irreversible: stepping back restores nothing.
    assert_clean(alembic("downgrade", BEFORE), keys=True)
    with disposable.connect() as c:
        assert metas(c, ids) == after

    # Idempotent: running the repair again changes no row.
    out = alembic("upgrade", "head")
    assert repair_line(out) == f"audit metadata repair v1: {n} row(s) scanned, 0 changed"
    with disposable.connect() as c:
        assert metas(c, ids) == after
