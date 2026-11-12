# Running NoEfforts on your own machine (Docker Compose)

This is the owner's guide to starting, checking, backing up, upgrading and rolling back the local
Docker Compose stack. It is for one person on their own machine; it is not a production
deployment (no TLS, no public address, no managed secrets).

**Verified so far:** the stack is built and started on every push in GitHub Actions (Linux
runners): the `docker-smoke` job (API, migrations, sign-up, web app, both workers, restart, and the
backup and restore commands of sections 5 and 7) and the `execution-compose` job (browser
execution in its isolated containers against the synthetic receiver). On 2026-10-29 the cloud
sandbox validated the Compose file and the secret checks with the Docker CLI (`docker compose
config` with a good file, a file without `AUDIT_REF_KEY`, and `.env.example`), and ran the API
health probe against a running and a stopped API; it did not build images. **It has not been run
on the owner's Mac yet;** section 9 is how to do that.

## 1. What runs

| Service | What it is | Ports (this machine only) |
|---|---|---|
| `postgres` | the database (volume `pgdata`) | 127.0.0.1:5432 |
| `redis` | the job broker | 127.0.0.1:6379 |
| `backend` | the API; applies database migrations every time it starts | 127.0.0.1:8000 |
| `worker` | runs your applications (attempts) and nothing else: one at a time, one browser; starts once the API is healthy | — |
| `scheduler` | every other background job, on its schedule: recovery of stopped attempts, the queue relay, the mailbox, reminders, discovery; starts once the API is healthy | — |
| `browser-runner` | the isolated browser, on internal networks only | — |
| `egress-proxy` | the browser's only way out; no outbound network in this file | — |
| `frontend` | the web app; starts once the API is healthy | 127.0.0.1:3000 |

Every port is bound to 127.0.0.1, so nothing is reachable from another machine. Uploaded files
live in the `storage` volume.

Two workers, on purpose (D144). An application being sent may keep its worker for a long time:
when the employer emails a verification code, it waits for you to enter it (ten minutes by
default). `worker` therefore does only that, and `scheduler` does everything else, so the
mailbox is still read, stopped attempts are still recovered and queued applications are still
published while one waits. A second application queued meanwhile waits its turn: there is one
browser. `scheduler` has neither the browser runner's token nor the egress control socket.

## 2. Secrets and settings

Docker Compose reads `.env` in the repository root (`cp .env.example .env`). Three secrets are
required; `docker-compose.yml` refuses to start without them (`${VAR:?…}`):

| Key | Used by | Rule |
|---|---|---|
| `AUDIT_REF_KEY` | API, worker and scheduler: keys the audit references (`audit/service.py`) | at least 32 characters; the API refuses to start without it, and production refuses a key starting `test-only` |
| `BROWSER_RUNNER_TOKEN` | worker ↔ browser-runner | at least 24 characters; replace the example placeholder |
| `EGRESS_CONTROL_TOKEN` | worker ↔ egress proxy control socket | at least 24 characters; different from the runner token |

Generate each with `openssl rand -hex 32`. `POSTGRES_PASSWORD` defaults to `postgres`, which is
acceptable only because the port is bound to 127.0.0.1.

`.env` is git-ignored: never commit it. The API reads its own settings as `NOEFFORTS_*`
environment variables (`backend/app/core/config.py`). Compose reads `.env` only to fill in
`docker-compose.yml`, so a setting reaches the API, the worker and the scheduler only if that
file names it:
every `NOEFFORTS_*` setting in `.env.example` is named there, except the few Compose sets itself
(database, broker, storage, CORS, browser isolation); `test_deployment_config.py` checks this.
(Before D95 the email, discovery, drafting and session settings were not passed on, so setting
them in `.env` had no effect under Compose.) Running without Docker, the API reads `backend/.env`
instead (README).

**Switches that contact outside services stay off unless you set them on purpose:**
`NOEFFORTS_DISCOVERY_PROVIDERS` (Freehire), `NOEFFORTS_DRAFTING_PROVIDER` and
`NOEFFORTS_ANTHROPIC_API_KEY` (AI drafting, D74), `NOEFFORTS_EMAIL_ENABLED` (email reminders,
D94) and `NOEFFORTS_BOARD_SOURCES_ENABLED` (employer job boards, D95). `scripts/check_env.py`
warns when any is on.

Check the file before starting (prints key names only, never values):

```bash
python3 scripts/check_env.py .env
```

### Email reminders (optional, off by default; D94)

Reminders go to the account owner only, never to an employer. To use them, set
`NOEFFORTS_EMAIL_ENABLED=true`, an SMTP server (`NOEFFORTS_EMAIL_SMTP_HOST`, `_PORT`,
`_STARTTLS`, `_USERNAME`, `_PASSWORD`) and a sender (`NOEFFORTS_EMAIL_FROM`) in `.env`, and
`NOEFFORTS_PUBLIC_BASE_URL` to the address you open NoEfforts at (the links point there). In
production STARTTLS is required unless the server is on this machine. Then, in Account, Email
reminders: verify your address with the code, choose what to be reminded of, turn them on. A
message the server accepted cannot be recalled; one whose acceptance is uncertain is never sent
again by NoEfforts. Turning reminders off stops what no worker has claimed yet. Server acceptance
is not inbox delivery.

| State | How you know | Now |
|---|---|---|
| Feature implemented | this guide | yes (tested against a local test mail server only) |
| Transport configured | the settings page no longer says "not set up" | only when you set `NOEFFORTS_EMAIL_*` |
| Recipient verified | "Verified" on the settings page | per account, by the emailed code |
| Email enabled | "Reminders on" on the settings page | per account, after verification |
| Real delivery verified | a reminder in your own inbox | not yet: never run against a real mail server |

### Employer job boards (optional, off by default; D95)

`NOEFFORTS_BOARD_SOURCES_ENABLED=true` lets each account read the public job boards it added in
Discover (Greenhouse and Lever postings feeds), one board at a time, when its owner presses
"Read now". Requests go only to `boards-api.greenhouse.io`, `api.lever.co` or `api.eu.lever.co`
over HTTPS, GET only, without cookies or credentials, at most once every 5 minutes per board.
Nothing reads a board on a schedule. Off, boards can be
added but none is read. Never run against a real board while building this (local stand-ins only).

## 3. Start

```bash
cp .env.example .env            # first time only; then set the three secrets above
python3 scripts/check_env.py .env
docker compose up -d --build   # returns once the API is healthy and the rest has started
docker compose ps               # backend shows "healthy" once migrations have run
```

Then open http://localhost:3000 and create an account.

- **Migrations** run automatically when `backend` starts (`alembic upgrade head`, see
  `backend/Dockerfile`); the API starts only if they succeed. The worker and the web app wait for
  the API to report healthy, so they never start on a database that is still being migrated.
- **If the API does not become healthy** within about three minutes (a minute's grace, then 24
  probes 5 seconds apart), `docker compose up` stops with "dependency failed to start" and the
  worker and web app stay down. `docker compose logs backend` shows why: usually a missing
  secret or a failed migration.
- **First build** downloads the base images and every dependency; later starts reuse them.

## 4. Check that it is healthy

```bash
curl -fsS http://127.0.0.1:8000/api/health                       # {"status":"ok"}: API and database
docker compose exec -T backend alembic current                   # ends with "(head)": schema current
docker compose exec -T worker celery -A app.worker inspect ping   # "pong" twice: attempts@… and scheduler@… on the broker
docker compose ps                                                # every service "running"; backend "healthy"
```

Logs: `docker compose logs --tail 100 backend worker scheduler`. They are written to carry no applicant
data (type-only error logging, route templates only), but treat them as private anyway.

## 5. Back up

Back up before every upgrade. With the stack running:

```bash
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M%S)
docker compose exec -T postgres pg_dump -U postgres -Fc noefforts > "backups/noefforts-$stamp.dump"
docker compose exec -T backend tar czf - -C /data/storage . > "backups/storage-$stamp.tgz"
```

`backups/` holds your real data (profile, documents, applications): keep it outside any shared
folder, and never commit it. `.gitignore` excludes `backups/`, and a repository test fails if a
backup folder or a `.dump` file is ever committed.

## 6. Upgrade

```bash
# 1. back up (section 5)
git pull                      # or check out the release you want
python3 scripts/check_env.py .env
docker compose up -d --build  # the API applies new migrations as it starts
# 2. check (section 4)
```

With an application in progress, stop the worker first (`docker compose stop worker`), then
`up -d --build`. Since D150 a stopped worker ends its application at its next step: one that
had entered nothing goes back in the queue and the new worker runs it. `up -d --build` alone
may replace the egress proxy, built from the same code, before it stops the worker: the
application then loses its way to the employer mid-step and stops with an error instead.

Upgrading from a version with one worker (before D144): `up -d --build` starts `scheduler` and
restarts `worker` with its new role. An application queued but not yet started at that moment is
passed on to the new worker. One thing may need doing by hand: a `docker-compose.override.yml`
of your own that names `worker` for something the periodic tasks use must name `scheduler` now.
The case known is the mailbox token of `docs/inbox.md`: mounted into `worker` only, the mailbox
still shows as connected and no verification code is entered.

Upgrading to a version with D146: an application stuck as queued since an earlier version lost
its message, or shown as running after its worker stopped before entering anything, is
published within five minutes of the new `scheduler` starting. If its approval still stands it
then runs; otherwise it ends without being sent and waits for you. If it must not run, open it
and press Cancel in its Submission card before you upgrade.

Upgrading to a version with D147: its migration stamps the database with its own identity
(its oid and its server's cluster identifier), which is how a later restore is recognized
(section 7). A backup taken before this upgrade has no stamp, so a restore of it is not
recognized; section 7's check finds that, and says what to do.

Upgrading PostgreSQL itself to a new major version (`pg_upgrade`, or a dump and reload), a
move to another server by a dump and reload, or a dump and reload for any other reason changes
that identity, so a version with D147 treats the database as restored: it ends what was in
progress (each waits for you as an unknown outcome), retires every approval, pauses automatic
applying and tells every account that the server was restored from a backup. Automatic
applying then leaves to you every application that existed before. Do these with nothing
queued or in progress, then approve again and resume automatic applying. (A move that copies
the server's files keeps the identity, and is not treated as a restore.)

## 7. Roll back

Read this section to the end before you start: the `git checkout` below replaces this guide
with the older version's, which may not have the step after the restore.

Restoring the backup taken before the upgrade is the supported rollback: it brings the code,
the schema and the data back together. Anything done after that backup is lost.

```bash
docker compose stop backend worker scheduler frontend   # nothing writes while you restore
git checkout <the commit you ran before>
docker compose build
docker compose up -d postgres redis
docker compose exec -T postgres dropdb -U postgres --force noefforts
docker compose exec -T postgres createdb -U postgres noefforts
docker compose exec -T postgres pg_restore -U postgres -d noefforts --no-owner < backups/noefforts-<stamp>.dump
docker compose run --rm --no-deps -T backend \
  sh -c 'find /data/storage -mindepth 1 -delete && tar xzf - -C /data/storage' < backups/storage-<stamp>.tgz
docker compose up -d backend frontend     # the app alone: nothing is run or queued yet
```

**Before you start the workers** (after every restore, and every rollback whatever version it
goes back to). The restored database knows nothing of what happened after the backup was
taken: an application it shows as queued or running may have been sent since, and one it
shows as approved may have been queued and sent since. Messages for them may still wait in
the broker, which a restore does not empty and an older worker reads as well. With only
`backend` and `frontend` up, ask the version you are running what it knows:

```bash
docker compose exec -T backend python -m app.modules.execution.cli restore-status
```

- **It shows `"held": true`:** this version (D147 or later) recognized the restore. Until the
  scheduler has dealt with it, nothing is approved, queued, cancelled, revoked or run, and
  pausing automatic applying only pauses it: leave the applications alone until then. Once
  started, the scheduler ends, without running them, the applications the backup shows as
  queued or in progress (each then waits for you as an unknown outcome), retires every
  approval, pauses automatic applying, and says so in every account's notifications.
- **It shows `"held": false` and no `"restored_at"` from today:** this version did not
  recognize the restore: a restore into the same database (`pg_restore --clean`), a copy of
  the server's files (its volume, a snapshot, a physical backup, a promoted replica), or a
  backup taken before D147. Treat it as restored before anything else, then check again (it
  must now show a `"restored_at"` from now):
  `docker compose exec -T backend python -m app.modules.execution.cli restore-resolve --force`
- **It prints nothing:** this version is older than D147 and does none of this. Pause
  "Automatically submit applications" in the Tracker, then open every application shown as
  Queued or Running and press Cancel in its Submission card.

Then start the rest:

```bash
docker compose up -d --remove-orphans
```

With D147 or later, run `restore-status` once more within a minute: it must show `"held":
false` and a `"restored_at"` from now. If it still shows the database held, the scheduler
cannot resolve it: its log (`docker compose logs scheduler`) names the error's type, and
nothing runs until it is resolved.

Whatever the version, before you approve or queue anything again, compare what the Tracker
shows with the confirmation emails you received after the backup, and record on each
application what you find: reconcile one waiting as an unknown outcome ("It was received" or
"It was not received"), record one you find sent with "I applied myself" where the Tracker
offers it, and never approve one you find sent. Resume automatic applying only after that: the
restored database does not know what it applied to after the backup, and it could apply to the
same job again. (A version with D147 leaves to you every application that began before the
restore; a new one for the same job is the risk.)

`--remove-orphans` matters when the older version had fewer services: rolling back to before
D144, `scheduler` no longer exists in the file, and a leftover one must not keep running next
to the older `worker` (it would take queued applications off the old queue and pass them to a
queue the older worker does not read). Anything still waiting in the newer version's own queue
is not read by the older worker either. After the restore most of it names applications the
backup does not have; for the rest, see the step above (a version before D147 needs it done by
hand).

The database is dropped and recreated rather than restored over (`pg_restore --clean` would
leave tables that only the newer version had, and the older version's migrations would then
fail). The CI smoke test runs these same commands on a throwaway stack: it backs up, creates a
second account, restores, and checks that the first account's session works and the second
account no longer exists. It restores onto the same version, so no leftover service exists
there and a rollback across versions is not exercised. It starts the app alone first and checks
that the restored database shows as held, then starts the rest and waits for the scheduler to
deal with the restore (`restore-status`). It queues nothing, so nothing is ended.

`alembic downgrade` exists for each migration, but some refuse while data depends on the newer
schema (for example, the C18/L2 downgrade refuses while a generated document awaits
acceptance). Use it only when release notes say so, and only after a backup.

## 8. Stop and remove

```bash
docker compose stop           # keeps all data
docker compose down           # removes containers, keeps the pgdata and storage volumes
docker compose down -v        # ALSO DELETES YOUR DATA (database and documents)
```

`down` also discards what is waiting in the broker (`redis` keeps nothing in a named volume):
the messages of applications that were queued and not yet started. Since D144 that can be more
than a moment's worth: the scheduler goes on handing queued applications to the broker while
`worker` is busy or stopped. The applications are not lost with their messages (D146): one
that is still queued five minutes after its message went out is published again by the
scheduler, and again every five minutes while it waits. After the next `up` it is taken up
within about five minutes, once `worker` is free, if its approval still stands. `stop` and an
upgrade (`up -d --build`) keep the broker's container: Redis writes what waits in it to that
container's disk when it is asked to stop, and reads it back when it starts. If the broker is
killed, or the machine loses power, what was queued since its last snapshot is published again
the same way. While `worker` is stopped the messages add up in the broker (12 an hour for each
waiting application); all but one are ignored when they are taken.

`stop` asks each service to finish and ends it ten seconds later; `worker` gets 150 seconds.
Since D150 the worker's application in progress takes no further step at the employer once
it is asked: one that had entered nothing goes back in the queue, one that had entered data
is left for you, and one past its send gate reads the employer's answer to its click before
the worker exits. Before D150 it went on and could be submitted (measured 2026-11-11). To end
the processes at once, use `docker compose kill worker` (`docs/activation-status.md` §8).

## 9. Verify (safe, throwaway)

```bash
docker compose stop           # the check uses the same local ports
./scripts/verify-local.sh
```

It checks `.env`, validates `docker-compose.yml` with it, runs the smoke test as a separate,
throwaway Compose project (`noefforts_smoke`) with its own volumes, removed at the end. Your
stack's data is never read or changed, and nothing contacts an employer, Freehire or an AI
provider. It ends with a summary block that is safe to share (step results and versions, never a
value or a log line).

Before starting the Greenhouse pilot (`docs/activation-status.md` §5), run
`./scripts/verify-local.sh --pilot`. It also checks that `.env` switches the pilot on and names
exactly your account, and that `docker-compose.pilot.yml` is valid with it (D112).

## 10. On a Mac (not yet verified)

The runbook, and what to send back (the summary block only), is
[docs/owner-mac-verification.md](owner-mac-verification.md).

Expected, to be confirmed by running section 9 on the Mac:

- Docker Desktop with at least 4 GB of memory for containers (the browser runner alone is
  limited to 1.5 GB).
- Apple silicon: the base images (`python`, `node`, `postgres`, `redis`) are multi-architecture;
  the browser runner installs Chromium for Linux on arm64. Not yet built on arm64.
- The browser runner's seccomp profile (`browser/seccomp.json`) is passed by path; Docker
  Desktop's Linux VM applies it.

Record the result (pass or the first failing line) in `docs/implementation-status.md`.
