"""Test-run isolation (D103): no test run can reset a database, a Redis database or a port another
run is using, and no run's cleanup can remove what another run created.

* **The database is explicit.** NOEFFORTS_TEST_DATABASE_URL has no default: the suite drops and
  recreates its schema, so it never falls back to a shared database.
* **It is disposable.** `python -m tests.isolation create` makes one owned by the test-only role
  `noefforts_tester` (no superuser, so it cannot touch a database it does not own) and marks it
  with `COMMENT ON DATABASE … 'noefforts-disposable-test run=<id>'`. An owner's or production
  database carries no such mark; the suite refuses it before any DROP or migration.
* **A run claims it.** `pg_try_advisory_lock` on a connection held for the whole session (`claim`);
  a second run finds it held and refuses, again before any DROP or migration. Advisory locks end
  with their connection, so a killed run blocks nothing afterwards.
* **Destructive statements wait a bounded time** for a lock (`LOCK_TIMEOUT`), never indefinitely.
* **Siblings carry the run.** Databases a run creates itself (the migration tests) are named after
  its own test database and marked with its run id; cleanup drops only databases marked with the
  caller's run id (`drop_run`), never by name alone.
* **Redis and ports.** Each run takes its own Redis database index (1-15) and holds its ports under
  exclusive OS file locks (`fcntl`), released when the process ends; a second run refuses. The
  end-to-end servers hold theirs the same way (`python -m tests.isolation hold`, in
  frontend/playwright.config.ts), with a claim on their database.
"""

import argparse
import fcntl
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.pool import NullPool

MARK = "noefforts-disposable-test"
ROLE = "noefforts_tester"
LOCK_KEY = 7_316_028_403_102  # this suite's advisory-lock key (any fixed bigint)
LOCK_TIMEOUT = "15s"
NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}_test$")
RUN = re.compile(r"^[a-z0-9]{1,16}$")
LOCK_DIR = Path(os.environ.get("NOEFFORTS_LOCK_DIR", tempfile.gettempdir())) / "noefforts-locks"
_HELD: list = []  # open lock files and connections, kept for the life of the process


class Refused(SystemExit):
    """Isolation refused the run; nothing was dropped, migrated or created."""

    def __init__(self, message: str):
        super().__init__(f"Refusing to run tests: {message}")


def mark_for(run: str) -> str:
    return f"{MARK} run={run}"


def _engine(url: str):
    return create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")


def _connect(url: str) -> Connection:
    try:
        return _engine(url).connect()
    except Exception as e:  # noqa: BLE001 - say which database, never the password
        db = make_url(url).database
        raise Refused(f"cannot connect to {db!r} ({type(e).__name__})") from None


def _db_mark(conn: Connection, name: str | None = None) -> str | None:
    return conn.execute(
        text(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = "
            "coalesce(:n, current_database())"
        ),
        {"n": name},  # fmt: skip
    ).scalar()


def claim(url: str) -> Connection:
    """Check and claim the run's database before anything touches it. Returns the connection that
    holds the claim; it must stay open for the whole run. Raises Refused."""
    conn = _connect(url)
    name = conn.execute(text("SELECT current_database()")).scalar()
    if conn.execute(text("SELECT current_setting('is_superuser')")).scalar() == "on":
        conn.close()
        raise Refused(f"{name!r} is reached as a superuser; use the test-only role {ROLE!r} "
                      "(python -m tests.isolation create)")  # fmt: skip
    mark = _db_mark(conn) or ""
    if not mark.startswith(MARK + " run="):
        conn.close()
        raise Refused(f"{name!r} is not marked as a disposable test database "
                      "(create one with python -m tests.isolation create)")  # fmt: skip
    if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
        conn.close()
        raise Refused(f"another test run is using {name!r}")
    _HELD.append(conn)
    return conn


def run_of(conn: Connection) -> str:
    return (_db_mark(conn) or "").removeprefix(MARK + " run=")


def sibling(url: str, purpose: str) -> str:
    """The URL of a disposable database for `purpose`, named after the run's own test database."""
    u = make_url(url)
    name = f"{u.database.removesuffix('_test')}_{purpose}_migration_test"
    if len(name) > 63 or not re.fullmatch(r"[a-z0-9_]+", name):
        raise Refused(f"cannot name a sibling database for {purpose!r}")
    return u.set(database=name).render_as_string(hide_password=False)


def recreate_sibling(url: str, purpose: str) -> str:
    """Drop (only if it is this run's) and create the sibling database; returns its URL. Run as the
    test role, which owns what it creates."""
    target = sibling(url, purpose)
    name = make_url(target).database
    with _connect(url) as c:
        run = run_of(c)
        existing = c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
        if existing.scalar():
            if _db_mark(c, name) != mark_for(run):
                raise Refused(f"{name!r} exists and is not this run's")
            c.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
        c.execute(text(f"COMMENT ON DATABASE \"{name}\" IS '{mark_for(run)}'"))
    return target


def drop_sibling(url: str, purpose: str) -> None:
    target = make_url(sibling(url, purpose)).database
    with _connect(url) as c:
        if _db_mark(c, target) == mark_for(run_of(c)):
            c.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            c.execute(text(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)'))


def create(admin_url: str, name: str | None = None, run: str | None = None) -> dict[str, str]:
    """A new disposable test database owned by the test role (created if missing). Never takes
    over an existing database that is not marked with this run."""
    run = run or secrets.token_hex(4)
    if not RUN.fullmatch(run):
        raise Refused("a run id is lowercase letters and digits, up to 16")
    name = name or f"noefforts_{run}_test"
    if not NAME.fullmatch(name):
        raise Refused(f"{name!r} is not a test database name")
    with _connect(admin_url) as c:
        if not c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar():
            c.execute(text(f"CREATE ROLE {ROLE} LOGIN CREATEDB NOSUPERUSER"))
        if c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).scalar():
            if _db_mark(c, name) != mark_for(run):
                raise Refused(f"{name!r} already exists and is not this run's")
        else:
            c.execute(text(f'CREATE DATABASE "{name}" OWNER {ROLE}'))
            c.execute(text(f"COMMENT ON DATABASE \"{name}\" IS '{mark_for(run)}'"))
    u = make_url(admin_url).set(username=ROLE, password=None, database=name)
    return {"NOEFFORTS_TEST_DATABASE_URL": u.render_as_string(hide_password=False),
            "NOEFFORTS_TEST_RUN_ID": run}  # fmt: skip


def drop_run(admin_url: str, run: str) -> list[str]:
    """Drop every database marked with this run id, and nothing else. Returns their names."""
    if not RUN.fullmatch(run):
        raise Refused("a run id is lowercase letters and digits, up to 16")
    with _connect(admin_url) as c:
        names = list(c.execute(
            text("SELECT datname FROM pg_database "
                 "WHERE shobj_description(oid, 'pg_database') = :m"),
            {"m": mark_for(run)}).scalars())  # fmt: skip
        for n in names:
            c.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            c.execute(text(f'DROP DATABASE "{n}" WITH (FORCE)'))
    return names


def _lock(name: str):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    f = open(LOCK_DIR / f"{name}.lock", "a+")  # noqa: SIM115 - held for the life of the process
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    _HELD.append(f)
    return f


def hold_port(port: int) -> None:
    """Hold `port` for this run; another run holding it is refused."""
    if _lock(f"port-{int(port)}") is None:
        raise Refused(f"port {port} is held by another test run")


def _redis_key(host: str, port: int, n: int) -> str:
    return f"redis-{host}-{port}-{n}"


def redis_url(base: str = "redis://127.0.0.1:6379") -> str:
    """A Redis URL with a database index (1-15) no other run holds."""
    u = urlsplit(base)
    host, port = u.hostname or "127.0.0.1", u.port or 6379
    for n in range(1, 16):
        if _lock(_redis_key(host, port, n)) is not None:
            return f"redis://{host}:{port}/{n}"
    raise Refused(f"every Redis database index on {host}:{port} is held by another run")


def hold_redis(url: str) -> None:
    """Hold the Redis database `url` names (its index, 0 when none) for this run."""
    u = urlsplit(url)
    host, port = u.hostname or "127.0.0.1", u.port or 6379
    n = int(u.path.strip("/") or 0)
    if _lock(_redis_key(host, port, n)) is None:
        raise Refused(f"Redis database {n} on {host}:{port} is held by another test run")


def hold(entries: str) -> None:
    """Hold each entry for this run: a port number; `redis`, the database NOEFFORTS_REDIS_URL
    names; `db`, a claim (as `claim`) on NOEFFORTS_DATABASE_URL. Taken from the environment the
    command will get, so what is held is what it uses. Raises Refused before anything runs."""
    for e in (x.strip() for x in entries.split(",") if x.strip()):
        if e.isdigit():
            hold_port(int(e))
        elif e == "redis":
            hold_redis(os.environ.get("NOEFFORTS_REDIS_URL") or "redis://127.0.0.1:6379/0")
        elif e == "db":
            url = os.environ.get("NOEFFORTS_DATABASE_URL", "")
            if not url:
                raise Refused("NOEFFORTS_DATABASE_URL is not set, and there is no default")
            claim(url)
        else:
            raise Refused(f"cannot hold {e!r} (a port, 'redis' or 'db')")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["hold"]:  # hold 3100,8100,redis,db [--cwd DIR] -- command...
        if len(argv) < 2:
            raise Refused("hold needs a comma-separated list: ports, 'redis', 'db'")
        hold(argv[1])
        rest, cwd = argv[2:], None
        if rest[:1] == ["--cwd"]:
            cwd, rest = rest[1], rest[2:]
        cmd = rest[1:] if rest[:1] == ["--"] else rest
        return subprocess.call(cmd, cwd=cwd) if cmd else 0
    ap = argparse.ArgumentParser(description="Disposable test resources (D103).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="print KEY=VALUE lines for a new disposable test database")
    c.add_argument("--name")
    c.add_argument("--run")
    c.add_argument("--export", action="store_true", help="print shell export lines")
    d = sub.add_parser("drop", help="drop the databases marked with one run id")
    d.add_argument("--run", required=True)
    sub.add_parser("hold", help="hold 3100,redis,db -- command: hold them while it runs")
    a = ap.parse_args(argv)
    admin = os.environ.get("NOEFFORTS_TEST_ADMIN_URL",
                           "postgresql+psycopg://postgres@127.0.0.1:5432/postgres")  # fmt: skip
    if a.cmd == "create":
        for k, v in create(admin, a.name, a.run).items():
            print(f"export {k}={v}" if a.export else f"{k}={v}")
    elif a.cmd == "drop":
        for n in drop_run(admin, a.run):
            print(f"dropped {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
