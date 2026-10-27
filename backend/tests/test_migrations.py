"""Migration tests on a separate, disposable database (name must end in _migration_test).

1. empty -> head
2. populated Phase A snapshot -> head, data preserved
3. disposable downgrade-to-base and re-upgrade
4. C6: answer_bank.help_text added without touching a saved answer
"""

import hashlib
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ADMIN = os.environ.get(
    "NOEFFORTS_TEST_ADMIN_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/postgres"
)
NAME = "noefforts_migration_test"
URL = ADMIN.rsplit("/", 1)[0] + f"/{NAME}"
PHASE_A = "c7b625a61ac2"
HERE = os.path.dirname(__file__)


def _recreate():
    assert NAME.endswith("_migration_test")  # never touch anything else
    eng = create_engine(ADMIN, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {NAME}"))
    eng.dispose()


def _cfg():
    cfg = Config(os.path.join(HERE, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "..", "migrations"))
    cfg.attributes["db_url"] = URL
    return cfg


@pytest.fixture
def disposable():
    _recreate()
    eng = create_engine(URL)
    yield eng
    eng.dispose()


def test_empty_to_head(disposable):
    command.upgrade(_cfg(), "head")
    with disposable.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar()


def test_populated_phase_a_upgrades_with_data_preserved(disposable):
    command.upgrade(_cfg(), PHASE_A)
    uid, jid, aid, pid = (uuid.uuid4() for _ in range(4))
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
        c.execute(
            text(
                "insert into candidate_profiles (id,user_id,full_name,residence_country,"
                "links,skills,"
                "provenance,approval_status,version,updated_at) values "
                "(:p,:u,'Sam Synthetic','US','[]','[]','user_entered','approved',3,now())"
            ),
            {"p": pid, "u": uid},
        )
        c.execute(
            text(
                "insert into jobs (id,user_id,dedupe_key,employer,title,ats_provider,source,status,"
                "first_seen_at,last_seen_at,seen_count,created_at,updated_at) values "
                "(:j,:u,'fp:1','Acme','Cook','unknown','manual','new',now(),now(),1,now(),now())"
            ),
            {"j": jid, "u": uid},
        )
        c.execute(
            text(
                "insert into applications (id,user_id,job_id,state,state_changed_at,outcome,"
                "lock_version,created_at,updated_at) values "
                "(:a,:u,:j,'submitted_unconfirmed',now(),'none',4,now(),now())"
            ),
            {"a": aid, "u": uid, "j": jid},
        )
    command.upgrade(_cfg(), "head")
    with disposable.connect() as c:
        row = c.execute(
            text(
                "select full_name, residence_country, version, given_name "
                "from candidate_profiles where id=:p"
            ),
            {"p": pid},
        ).one()
        assert tuple(row) == ("Sam Synthetic", "US", 3, None)  # new column defaults to unknown
        app = c.execute(
            text("select state, lock_version from applications where id=:a"), {"a": aid}
        ).one()
        assert tuple(app) == ("submitted_unconfirmed", 4)
        assert c.execute(text("select title from jobs where id=:j"), {"j": jid}).scalar() == "Cook"


def test_disposable_downgrade_and_reupgrade(disposable):
    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), "base")
    with disposable.connect() as c:
        enums = c.execute(
            text(
                "select count(*) from pg_type t join pg_namespace n on "
                "n.oid=t.typnamespace where n.nspname='public' and t.typtype='e'"
            )
        )
        assert enums.scalar() == 0
    command.upgrade(_cfg(), "head")


BEFORE_C6 = "33c1622938ba"


def test_c6_saved_answers_keep_their_key_and_gain_no_help_text(disposable):
    """C6 (D51) adds answer_bank.help_text without touching a row: same id, key, value and
    version, help_text NULL (saved before help text was recorded); a downgrade drops only the
    column."""
    command.upgrade(_cfg(), BEFORE_C6)
    uid, bid = uuid.uuid4(), uuid.uuid4()
    key = hashlib.sha256(b"highest level of education completed|choice").hexdigest()
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
        c.execute(
            text(
                "insert into answer_bank (id,user_id,question_key,question_text,answer_shape,"
                "value,options_snapshot,sensitive,provenance,approval_status,version,updated_at) "
                "values (:b,:u,:k,'Highest level of education completed','choice',"
                "'{\"labels\": [\"Bachelor''s degree\"]}','[\"bachelor''s degree\"]',false,"
                "'user_entered','approved',3,now())"
            ),
            {"b": bid, "u": uid, "k": key},
        )
    row_sql = text("select question_key, value::text, version from answer_bank where id=:b")
    with disposable.connect() as c:
        before = tuple(c.execute(row_sql, {"b": bid}).one())
    command.upgrade(_cfg(), "head")
    with disposable.connect() as c:
        assert tuple(c.execute(row_sql, {"b": bid}).one()) == before
        assert before[0] == key and before[2] == 3
        help_ = c.execute(text("select help_text from answer_bank where id=:b"), {"b": bid})
        assert help_.scalar() is None
    command.downgrade(_cfg(), BEFORE_C6)
    with disposable.connect() as c:
        assert tuple(c.execute(row_sql, {"b": bid}).one()) == before
        cols = c.execute(
            text(
                "select count(*) from information_schema.columns "
                "where table_name='answer_bank' and column_name='help_text'"
            )
        )
        assert cols.scalar() == 0
    command.upgrade(_cfg(), "head")
