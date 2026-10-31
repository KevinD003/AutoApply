# Test isolation (D103)

The backend suite drops and recreates its database's schema at the start of every run and empties
every table after each test. Before D103, it fell back to a shared database (`noefforts_test`)
whenever `NOEFFORTS_TEST_DATABASE_URL` was unset. Two runs started at once, for example a
validation run and a subset run, then reset each other's database mid-run. That happened
repeatedly.

D103 makes this impossible through every supported entry point: a direct `pytest`, a direct
`npx playwright test`, `scripts/validate.sh` and CI. The code is `backend/tests/isolation.py`,
used by `tests/conftest.py`, the migration tests, `frontend/playwright.config.ts`,
`scripts/validate.sh` and `.github/workflows/ci.yml`.

## What is enforced

| Requirement | How | Refused with |
|---|---|---|
| The test database is explicit | `NOEFFORTS_TEST_DATABASE_URL` has no default. `conftest.py` refuses before importing the application, so nothing has connected, dropped or migrated yet. | `NOEFFORTS_TEST_DATABASE_URL is not set, and there is no default` |
| It is disposable, whatever its name | `python -m tests.isolation create` makes a database owned by the test-only role and marks it with `COMMENT ON DATABASE … 'noefforts-disposable-test run=<id>'`. An owner's or production database carries no such mark. A name ending `_test` proves nothing. | `… is not marked as a disposable test database` |
| Test-only credentials | The role `noefforts_tester` has `LOGIN CREATEDB NOSUPERUSER`. PostgreSQL itself refuses it any drop, truncate or write on a database it does not own. A superuser connection is refused even to a marked database. | `… is reached as a superuser` |
| One run per database | `pg_try_advisory_lock` on a connection held for the whole session (`claim`), taken before any DROP or migration. Advisory locks end with their connection, so a killed run blocks nothing afterwards. | `another test run is using …` |
| Bounded waits | Every DROP and TRUNCATE the suite issues runs after `SET lock_timeout = '15s'` on the same connection, so none queues indefinitely behind another session. | a lock-timeout error, not a hang |
| Unique identities | Each `create` picks a new run id and database (`noefforts_<run>_test`). Databases a run creates itself, the migration tests' siblings, are named after its own database (`<base>_<purpose>_migration_test`) and marked with the same run id. | `… exists and is not this run's` |
| Cleanup only of the run's own resources | `drop --run <id>` and the sibling cleanup drop only databases whose mark names that run, never by name. An interrupted run's cleanup cannot reach another run's database. | nothing is dropped |
| Redis | Each backend run takes its own Redis database index (1–15) under an exclusive OS file lock (`fcntl`). The e2e API holds the index it is given. | `… is held by another test run` |
| Ports | The backend run holds its receiver and SMTP port (`NOEFFORTS_TEST_RECEIVER_PORT`, default 8799), its canary port (`NOEFFORTS_TEST_CANARY_PORT`, 8798) and its disposable broker's port (`NOEFFORTS_TEST_BROKER_PORT`, 6391). Each Playwright server holds its own ports (3100, 8100, 8797, 8799, 8796) through `python -m tests.isolation hold`. The locks are released when the process ends. | `port … is held by another test run` |
| The e2e database | The default is `noefforts_tester@…/noefforts_e2e_test`, never a superuser. The API's server claims the database (`hold …,db`) before `alembic upgrade`, so it is refused if the database is unmarked or in use. | as above |

The e2e mail sink fails loudly when it cannot listen (`fixtures/ats_receiver/mail_sink.py`). It
never silently serves from a port another run holds.

## How to run

```bash
cd backend
eval "$(uv run python -m tests.isolation create --export)"   # NOEFFORTS_TEST_DATABASE_URL, _RUN_ID
uv run pytest
uv run python -m tests.isolation drop --run "$NOEFFORTS_TEST_RUN_ID"

# A second suite at the same time: its own database and ports (a clash is refused, not raced).
eval "$(uv run python -m tests.isolation create --export)"
NOEFFORTS_TEST_RECEIVER_PORT=8791 NOEFFORTS_TEST_CANARY_PORT=8792 NOEFFORTS_TEST_BROKER_PORT=6392 \
  uv run pytest tests/test_providers.py
```

`scripts/validate.sh backend` and `scripts/validate.sh e2e` each create a database of their own.
They drop only those databases on exit, including on failure or interruption (an `EXIT` trap).
CI creates `noefforts_test` and `noefforts_e2e_test` the same way, with run ids `ci` and `e2e`.

The administrator connection that `create` and `drop` use is `NOEFFORTS_TEST_ADMIN_URL`. Its
default is `postgresql+psycopg://postgres@127.0.0.1:5432/postgres`, the local sandbox's
superuser. It is used only to create the role and the disposable databases, and to drop
databases marked with a given run id. The tests themselves never run as it.

## Regression tests

`backend/tests/test_test_isolation.py` runs a second `pytest` process where a contributor would,
with the environment it would have:

- two runs cannot reset one database: an in-process claim and a second `pytest` are both refused,
  and the tables are unchanged;
- a missing setting is refused before any database work, even with `NOEFFORTS_DATABASE_URL`
  pointing at a database;
- an owner's or production database, unmarked but with a test-like name and a row in it, is
  refused, and the row is still there;
- a superuser connection is refused even to a marked database;
- the test role cannot drop, truncate, delete from, insert into or drop an owner's database;
  PostgreSQL refuses each statement;
- cleanup drops only its own run's databases, and an interrupted run's cleanup cannot remove
  another run's, even under the same name;
- a sibling name already held by another run is never dropped;
- ports, Redis database indexes, the e2e database claim and the e2e Redis database are held by
  one run at a time;
- every e2e server starts under a hold, with no superuser default;
- every DROP and TRUNCATE is preceded by a `lock_timeout`.

## Limits

- **The guard covers this project's entry points.** Someone who connects as a superuser by hand
  can still drop anything. The test role cannot.
- **Other databases are reachable for connection.** By default PostgreSQL grants `CONNECT` on
  every database to `PUBLIC`, so the test role can connect to an owner's database. It cannot
  read, change or drop anything there that it does not own (tested above). An owner who wants
  even connection refused can run `REVOKE CONNECT ON DATABASE <name> FROM PUBLIC`.
- **Port locks are advisory.** They stop another test run of this project, not an unrelated
  program. Such a program makes the receiver, the mail sink or the broker fail loudly at start;
  none of them serves from a port it did not bind.
