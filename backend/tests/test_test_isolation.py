"""D103: no test run can reset another run's database, Redis database or port, and no run's
cleanup can remove what another run created (tests/isolation.py). Disposable databases only:
each case creates its own, marked with a run id of its own, and drops it afterwards.

The entry point is checked as a contributor would use it: a second `pytest` process, with the
environment it would have."""

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from tests import isolation
from tests.conftest import RECEIVER_PORT, TEST_DB

BACKEND = Path(__file__).resolve().parents[1]
ADMIN = os.environ.get("NOEFFORTS_TEST_ADMIN_URL",
                       "postgresql+psycopg://postgres@127.0.0.1:5432/postgres")  # fmt: skip


def _pytest(env_update: dict, drop: tuple = ()) -> subprocess.CompletedProcess:
    """A second pytest run (collection only: everything that happens before any test)."""
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_update)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "tests/test_providers.py"], cwd=BACKEND, env=env, capture_output=True, text=True,
        timeout=120,
    )  # fmt: skip


def _tables(url: str) -> set[str]:
    eng = create_engine(url, poolclass=NullPool)
    with eng.connect() as c:
        return set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
                   .scalars())  # fmt: skip


@pytest.fixture
def other_run():
    """A second, separate disposable database of a run of its own (dropped afterwards)."""
    run = "o" + secrets.token_hex(4)
    env = isolation.create(ADMIN, run=run)
    yield run, env["NOEFFORTS_TEST_DATABASE_URL"]
    isolation.drop_run(ADMIN, run)


def test_two_runs_cannot_reset_one_database():
    before = _tables(TEST_DB)
    assert "alembic_version" in before  # this run migrated it
    with pytest.raises(isolation.Refused, match="another test run is using"):
        isolation.claim(TEST_DB)  # this session holds the claim
    p = _pytest({"NOEFFORTS_TEST_DATABASE_URL": TEST_DB})
    assert p.returncode != 0 and "another test run is using" in p.stdout + p.stderr
    assert _tables(TEST_DB) == before  # nothing dropped, nothing migrated


def test_a_missing_database_setting_is_refused_before_any_database_work():
    before = _tables(TEST_DB)
    # Even with the application's own database setting pointing somewhere, nothing is implied.
    p = _pytest({"NOEFFORTS_DATABASE_URL": TEST_DB}, drop=("NOEFFORTS_TEST_DATABASE_URL",))
    assert p.returncode != 0 and "NOEFFORTS_TEST_DATABASE_URL is not set" in p.stdout + p.stderr
    assert _tables(TEST_DB) == before


def test_an_owner_or_production_database_is_refused_before_any_drop():
    """An unmarked database, as an owner's or production one is, with a table and a row in it:
    a run pointed at it refuses, and the row is still there."""
    run = "u" + secrets.token_hex(4)
    name = f"noefforts_{run}_test"  # a test-like name: the mark decides, never the name
    admin = create_engine(ADMIN, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" OWNER {isolation.ROLE}'))
    url = make_url(TEST_DB).set(database=name).render_as_string(hide_password=False)
    try:
        eng = create_engine(url, poolclass=NullPool)
        with eng.begin() as c:
            c.execute(text("CREATE TABLE owner_data (v text)"))
            c.execute(text("INSERT INTO owner_data VALUES ('keep me')"))
        p = _pytest({"NOEFFORTS_TEST_DATABASE_URL": url})
        assert p.returncode != 0 and "not marked as a disposable" in p.stdout + p.stderr
        with eng.connect() as c:
            assert c.execute(text("SELECT v FROM owner_data")).scalar() == "keep me"
        with pytest.raises(isolation.Refused, match="not a test database name"):
            isolation.create(ADMIN, name="noefforts", run=run)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_a_superuser_connection_is_refused_even_to_a_marked_database(other_run):
    _, url = other_run
    as_admin = make_url(ADMIN).set(database=make_url(url).database)
    with pytest.raises(isolation.Refused, match="superuser"):
        isolation.claim(as_admin.render_as_string(hide_password=False))


def test_cleanup_drops_only_its_own_runs_databases(other_run):
    theirs_run, theirs = other_run
    mine_run = "m" + secrets.token_hex(4)
    mine = isolation.create(ADMIN, run=mine_run)["NOEFFORTS_TEST_DATABASE_URL"]
    # An interrupted run's cleanup with its own id: only its own database goes.
    assert isolation.drop_run(ADMIN, mine_run) == [make_url(mine).database]
    assert _tables(theirs) == set()  # still there, reachable
    # Another run's database is never taken over under the same name either.
    with pytest.raises(isolation.Refused, match="not this run's"):
        isolation.create(ADMIN, name=make_url(theirs).database, run=mine_run)
    assert isolation.drop_run(ADMIN, mine_run) == []
    assert theirs_run  # dropped by its own fixture


def test_a_sibling_name_held_by_another_run_is_never_dropped(other_run):
    theirs_run, theirs = other_run
    # A database under this run's sibling name, but marked by another run.
    target = make_url(isolation.sibling(TEST_DB, "probe")).database
    admin = create_engine(ADMIN, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{target}" OWNER {isolation.ROLE}'))
        c.execute(text(f"COMMENT ON DATABASE \"{target}\" IS '{isolation.mark_for(theirs_run)}'"))
    try:
        with pytest.raises(isolation.Refused, match="not this run's"):
            isolation.recreate_sibling(TEST_DB, "probe")
        isolation.drop_sibling(TEST_DB, "probe")  # not ours: left alone
        with admin.connect() as c:
            exists = c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target})
            assert exists.scalar() == 1
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)'))


def test_ports_and_redis_databases_are_held_by_one_run_at_a_time():
    held = subprocess.run(
        [sys.executable, "-c", "import sys; from tests import isolation; "
         f"isolation.hold_port({RECEIVER_PORT})"],
        cwd=BACKEND, capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert held.returncode != 0 and f"port {RECEIVER_PORT} is held" in held.stderr
    theirs = subprocess.run(
        [sys.executable, "-c", "from tests import isolation; print(isolation.redis_url())"],
        cwd=BACKEND, capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert theirs.returncode == 0
    assert theirs.stdout.strip() != os.environ["NOEFFORTS_REDIS_URL"]


def test_every_destructive_statement_waits_a_bounded_time():
    """Every DROP and TRUNCATE the suite issues is preceded, in the same connection, by a
    lock_timeout; none can queue indefinitely behind another session."""
    for path in (BACKEND / "tests" / "conftest.py", BACKEND / "tests" / "isolation.py"):
        src = path.read_text()
        for m in re.finditer(r"(?i)\b(drop (schema|database)|truncate)\b", src):
            if 'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)' in src[m.start() : m.start() + 60]:
                continue  # test cleanup of databases this file created
            before = src[max(0, m.start() - 400) : m.start()]
            assert "lock_timeout" in before, (path.name, src[m.start() : m.start() + 40])


def _hold(entries: str, env_update: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_update}
    return subprocess.run(
        [sys.executable, "-m", "tests.isolation", "hold", entries, "--", "true"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )  # fmt: skip


def test_the_e2e_servers_hold_their_database_and_redis_database(other_run):
    """`hold` (what each Playwright server runs under) claims the database the API will migrate
    and the Redis database it will use, from the environment the server gets."""
    _, theirs = other_run
    busy = _hold("db", {"NOEFFORTS_DATABASE_URL": TEST_DB})  # this session's claim
    assert busy.returncode != 0 and "another test run is using" in busy.stderr
    unset = _hold("db", {"NOEFFORTS_DATABASE_URL": ""})
    assert unset.returncode != 0 and "NOEFFORTS_DATABASE_URL is not set" in unset.stderr
    assert _hold("db", {"NOEFFORTS_DATABASE_URL": theirs}).returncode == 0  # free and marked
    redis = _hold("redis", {"NOEFFORTS_REDIS_URL": os.environ["NOEFFORTS_REDIS_URL"]})
    assert redis.returncode != 0 and "is held by another test run" in redis.stderr
    port = _hold(str(RECEIVER_PORT), {})
    assert port.returncode != 0 and f"port {RECEIVER_PORT} is held" in port.stderr


def test_every_e2e_server_starts_under_a_hold():
    """A direct `npx playwright test` is covered, not only scripts/validate.sh: each webServer
    command runs under `hold`, and the API's holds its database and Redis database too."""
    config = (BACKEND.parent / "frontend" / "playwright.config.ts").read_text()
    servers = config.split("webServer:", 1)[1]
    commands = re.findall(r"command: (.*)", servers)
    assert len(commands) == 4 and all(c.startswith("hold(") for c in commands), commands
    assert any('"8100,redis,db"' in c for c in commands)
    assert "noefforts_tester@" in config and "/noefforts_e2e_test" in config
    assert "postgres@" not in config  # never a superuser default


def test_the_test_role_cannot_change_an_owners_database():
    """Even with the guards bypassed, the credentials the suite runs with cannot drop, empty or
    write an owner's database: PostgreSQL refuses each statement for want of ownership."""
    name = "noefforts_owner_" + secrets.token_hex(4)
    admin = create_engine(ADMIN, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))  # owned by the administrator, as an owner's is
    owner = make_url(ADMIN).set(database=name).render_as_string(hide_password=False)
    tester = make_url(TEST_DB).set(database=name).render_as_string(hide_password=False)
    try:
        with create_engine(owner, poolclass=NullPool).begin() as c:
            c.execute(text("CREATE TABLE owner_data (v text)"))
            c.execute(text("INSERT INTO owner_data VALUES ('keep me')"))
        eng = create_engine(tester, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        for statement in ("DROP SCHEMA public CASCADE", "TRUNCATE owner_data",
                          "DELETE FROM owner_data", "INSERT INTO owner_data VALUES ('x')",
                          "DROP TABLE owner_data", f'DROP DATABASE "{name}"'):  # fmt: skip
            with eng.connect() as c, pytest.raises(Exception, match="(?i)permission|owner|must be"):
                c.execute(text(statement))
        with create_engine(owner, poolclass=NullPool).connect() as c:
            assert c.execute(text("SELECT array_agg(v) FROM owner_data")).scalar() == ["keep me"]
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
