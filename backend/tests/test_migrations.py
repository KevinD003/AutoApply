"""Migration tests on a separate, disposable database (name must end in _migration_test).

1. empty -> head
2. populated Phase A snapshot -> head, data preserved
3. disposable downgrade-to-base and re-upgrade
4. C6: answer_bank.help_text added without touching a saved answer
5. S7: discovery_run_approvals added, bounded by its checks, dropped on downgrade
6. S8: discovery_watches added, bounded by its checks, dropped on downgrade
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
        funcs = c.execute(
            text("select count(*) from pg_proc where proname='application_events_insert_only'")
        )
        assert funcs.scalar() == 0
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


BEFORE_S2 = "b29cba6e1f6e"
S2 = "e3a91c5d7b20"
OUTCOMES = [
    "none",
    "assessment_received",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
    "no_response",
]


def test_s2_adds_assessment_received_and_outcome_fields_without_rewriting_a_row(disposable):
    """S2 (D53) adds the outcome assessment_received and five nullable event columns without
    touching a row: events written before it keep their kind, actor, reason and time, with
    NULL in every new column. Events become insert-only. A downgrade is refused while an
    application holds the new outcome; otherwise it drops only what S2 added."""
    from sqlalchemy.exc import IntegrityError

    command.upgrade(_cfg(), PHASE_A)
    uid, jid, aid, e1, e2 = (uuid.uuid4() for _ in range(5))
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
                "(:a,:u,:j,'submitted_confirmed',now(),'interviewing',3,now(),now())"
            ),
            {"a": aid, "u": uid, "j": jid},
        )
        c.execute(
            text(
                "insert into application_events (id,application_id,kind,from_state,to_state,actor,"
                "reason,created_at) values (:e,:a,'state_change','submitted_unconfirmed',"
                "'submitted_confirmed','user','Reconciled as received: synthetic email',now())"
            ),
            {"e": e1, "a": aid},
        )
        c.execute(
            text(
                "insert into application_events (id,application_id,kind,actor,reason,created_at) "
                "values (:e,:a,'outcome','user','outcome: none → interviewing',now())"
            ),
            {"e": e2, "a": aid},
        )
    command.upgrade(_cfg(), BEFORE_S2)
    rows = text(
        "select id, kind, actor::text, reason, created_at from application_events "
        "where application_id=:a order by id"
    )
    new_cols = text(
        "select from_outcome, to_outcome, source, occurred_on, evidence_note "
        "from application_events where application_id=:a"
    )
    with disposable.connect() as c:
        before = [tuple(r) for r in c.execute(rows, {"a": aid})]
    command.upgrade(_cfg(), S2)  # S2's own revision: later migrations do not change this test
    with disposable.connect() as c:
        assert [tuple(r) for r in c.execute(rows, {"a": aid})] == before
        assert all(tuple(r) == (None,) * 5 for r in c.execute(new_cols, {"a": aid}))
        labels = (
            c.execute(
                text(
                    "select enumlabel from pg_enum e join pg_type t on "
                    "t.oid=e.enumtypid where t.typname='app_outcome' "
                    "order by e.enumsortorder"
                )
            )
            .scalars()
            .all()
        )
        assert labels == OUTCOMES
    with pytest.raises(Exception, match="insert-only"), disposable.begin() as c:
        c.execute(text("update application_events set reason='x' where id=:e"), {"e": e1})
    with pytest.raises(IntegrityError), disposable.begin() as c:
        c.execute(
            text(
                "insert into application_events (id,application_id,kind,to_state,actor,source,"
                "created_at) values (:e,:a,'state_change','submitted_unconfirmed','user',"
                "'employer_email',now())"
            ),
            {"e": uuid.uuid4(), "a": aid},
        )
    with disposable.begin() as c:  # simulated: the user recorded the new outcome
        c.execute(
            text("update applications set outcome='assessment_received' where id=:a"), {"a": aid}
        )
    with pytest.raises(RuntimeError, match="1 application"):
        command.downgrade(_cfg(), BEFORE_S2)
    with disposable.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == S2
    with disposable.begin() as c:
        c.execute(text("update applications set outcome='interviewing' where id=:a"), {"a": aid})
    command.downgrade(_cfg(), BEFORE_S2)
    with disposable.connect() as c:
        assert [tuple(r) for r in c.execute(rows, {"a": aid})] == before
        gone = c.execute(
            text(
                "select (select count(*) from information_schema.columns where "
                "table_name='application_events' and column_name in ('from_outcome','to_outcome',"
                "'source','occurred_on','evidence_note')) + (select count(*) from pg_trigger where "
                "tgname='application_events_insert_only') + (select count(*) from pg_proc where "
                "proname='application_events_insert_only')"
            )
        ).scalar()
        assert gone == 0
        labels = (
            c.execute(
                text(
                    "select enumlabel from pg_enum e join pg_type t on "
                    "t.oid=e.enumtypid where t.typname='app_outcome'"
                )
            )
            .scalars()
            .all()
        )
        assert "assessment_received" in labels  # PostgreSQL cannot drop an enum value
    command.upgrade(_cfg(), "head")


def test_s7_adds_bounded_run_approvals_and_downgrade_drops_only_them(disposable):
    """S7 (D55): a new table only. Its checks refuse a run of more than five pages, an empty
    search, an empty retention statement and a window that ends before it starts; deleting the
    account deletes its approvals; a downgrade drops the table and nothing else."""
    from sqlalchemy.exc import IntegrityError

    command.upgrade(_cfg(), S2)
    uid = uuid.uuid4()
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'owner.synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
    command.upgrade(_cfg(), "head")
    insert = text(
        "insert into discovery_run_approvals (id,user_id,provider,query,max_pages,not_before,"
        "not_after,retention,created_at) values (:i,:u,'freehire',:q,:p,now(),"
        "now() + make_interval(hours => :h),:r,now())"
    )
    good = {"u": uid, "q": "financial analyst", "p": 1, "h": 2, "r": "kept until deleted"}
    for bad in ({"p": 6}, {"p": 0}, {"q": " "}, {"r": ""}, {"h": -1}):
        with pytest.raises(IntegrityError), disposable.begin() as c:
            c.execute(insert, {**good, **bad, "i": uuid.uuid4()})
    with disposable.begin() as c:
        c.execute(insert, {**good, "i": uuid.uuid4()})
        c.execute(text("delete from users where id=:u"), {"u": uid})
        assert c.execute(text("select count(*) from discovery_run_approvals")).scalar() == 0
    command.downgrade(_cfg(), S2)
    with disposable.connect() as c:
        assert c.execute(text("select to_regclass('discovery_run_approvals')")).scalar() is None
        assert c.execute(text("select version_num from alembic_version")).scalar() == S2


S7 = "4bc9c342d34c"
S8 = "29588d78e7e1"
S3 = "269ea4b8bc0c"


def test_s8_adds_bounded_watches_and_downgrade_drops_only_them(disposable):
    """S8 (D56): a new table only. Its checks refuse an interval under a minute or over a day,
    a watch longer than 90 days, an empty search or retention statement and negative counts;
    deleting the account deletes its watches; a downgrade drops the table and nothing else."""
    from sqlalchemy.exc import IntegrityError

    command.upgrade(_cfg(), S7)
    uid = uuid.uuid4()
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'owner.synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
    command.upgrade(_cfg(), S8)
    insert = text(
        "insert into discovery_watches (id,user_id,provider,query,interval_seconds,not_before,"
        "not_after,retention,created_at,next_check_at,failures,found_total,requests_on_day) "
        "values (:i,:u,'freehire',:q,:s,now(),now() + make_interval(days => :d),:r,now(),now(),"
        ":f,0,0)"
    )
    good = {"u": uid, "q": "financial analyst", "s": 60, "d": 30, "r": "kept until deleted", "f": 0}
    for bad in ({"s": 59}, {"s": 86401}, {"d": 91}, {"q": " "}, {"r": ""}, {"f": -1}):
        with pytest.raises(IntegrityError), disposable.begin() as c:
            c.execute(insert, {**good, **bad, "i": uuid.uuid4()})
    with disposable.begin() as c:
        c.execute(insert, {**good, "i": uuid.uuid4()})
        c.execute(text("delete from users where id=:u"), {"u": uid})
        assert c.execute(text("select count(*) from discovery_watches")).scalar() == 0
    command.downgrade(_cfg(), S7)
    with disposable.connect() as c:
        assert c.execute(text("select to_regclass('discovery_watches')")).scalar() is None
        assert c.execute(text("select to_regclass('discovery_run_approvals')")).scalar()
        assert c.execute(text("select version_num from alembic_version")).scalar() == S7


def test_s3_adds_the_job_signal_times_and_downgrade_drops_only_them(disposable):
    """S3 (D59): three nullable timestamps. A discovered row already stale gets the time it was
    last seen as the time its source first said so; a fresh one gets none; the jobs keep every
    value; a downgrade drops the three columns and nothing else."""
    command.upgrade(_cfg(), S8)
    uid, jid = uuid.uuid4(), uuid.uuid4()
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'s3.synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
        c.execute(
            text(
                "insert into jobs (id,user_id,dedupe_key,title,source,status,ats_provider,"
                "first_seen_at,last_seen_at,seen_count,created_at,updated_at) values (:j,:u,"
                "'fp:s3','Analyst','manual','new','unknown',now(),now(),1,now(),now())"
            ),
            {"j": jid, "u": uid},
        )
        for sid, stale in (("closed-1", True), ("open-1", False)):
            c.execute(
                text(
                    "insert into discovered_jobs (id,user_id,provider,source_job_id,fingerprint,"
                    "normalized,source_facts,status,job_id,stale,first_seen_at,last_seen_at,"
                    "imported_at,changed_fields) values (:i,:u,'freehire',:s,'f','{}','{}',"
                    "'linked',:j,:st,now(),'2026-10-20T10:00:00Z',now(),'[]')"
                ),
                {"i": uuid.uuid4(), "u": uid, "s": sid, "j": jid, "st": stale},
            )
    command.upgrade(_cfg(), S3)
    with disposable.connect() as c:
        got = dict(c.execute(text("select source_job_id, stale_since from discovered_jobs")).all())
        assert got["open-1"] is None and got["closed-1"].isoformat().startswith("2026-10-20T10:00")
        assert c.execute(
            text("select open_confirmed_at, distinct_confirmed_at, title from jobs")
        ).one() == (None, None, "Analyst")
    command.downgrade(_cfg(), S8)
    with disposable.connect() as c:
        cols = {
            r[0]
            for r in c.execute(
                text(
                    "select column_name from information_schema.columns where table_name in "
                    "('jobs','discovered_jobs')"
                )
            )
        }
        assert not cols & {"stale_since", "open_confirmed_at", "distinct_confirmed_at"}
        assert {"stale", "stale_reason", "employer_key"} <= cols
        assert c.execute(text("select count(*) from discovered_jobs")).scalar() == 2
        assert c.execute(text("select version_num from alembic_version")).scalar() == S8


def test_s6_adds_the_discovery_backoffs_and_downgrade_drops_only_them(disposable):
    """S6 (D67): one table, one row per user and provider, deleted with the user; a downgrade
    drops it and nothing else."""
    command.upgrade(_cfg(), S3)
    uid = uuid.uuid4()
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into users (id,email,password_hash,created_at,updated_at) "
                "values (:u,'s6.synthetic@example.com','x',now(),now())"
            ),
            {"u": uid},
        )
    command.upgrade(_cfg(), "head")
    with disposable.begin() as c:
        c.execute(
            text(
                "insert into discovery_backoffs (user_id,provider,not_before,updated_at) "
                "values (:u,'freehire',now() + interval '1 minute',now())"
            ),
            {"u": uid},
        )
        c.execute(text("delete from users where id = :u"), {"u": uid})
        assert c.execute(text("select count(*) from discovery_backoffs")).scalar() == 0
    command.downgrade(_cfg(), S3)
    with disposable.connect() as c:
        tables = set(c.execute(text("select tablename from pg_tables")).scalars())
    assert "discovery_backoffs" not in tables and {"users", "discovered_jobs"} <= tables
