# Running NoEfforts on your own machine (Docker Compose)

This is the owner's guide to starting, checking, backing up, upgrading and rolling back the local
Docker Compose stack. It is for one person on their own machine; it is not a production
deployment (no TLS, no public address, no managed secrets).

**Verified so far:** the stack is built and started on every push in GitHub Actions (Linux
runners): the `docker-smoke` job (API, migrations, sign-up, web app, worker, restart, and the
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
| `worker` | background jobs (Celery with its scheduler); starts once the API is healthy | — |
| `browser-runner` | the isolated browser, on internal networks only | — |
| `egress-proxy` | the browser's only way out; no outbound network in this file | — |
| `frontend` | the web app; starts once the API is healthy | 127.0.0.1:3000 |

Every port is bound to 127.0.0.1, so nothing is reachable from another machine. Uploaded files
live in the `storage` volume.

## 2. Secrets and settings

Docker Compose reads `.env` in the repository root (`cp .env.example .env`). Three secrets are
required; `docker-compose.yml` refuses to start without them (`${VAR:?…}`):

| Key | Used by | Rule |
|---|---|---|
| `AUDIT_REF_KEY` | API and worker: keys the audit references (`audit/service.py`) | at least 32 characters; the API refuses to start without it, and production refuses a key starting `test-only` |
| `BROWSER_RUNNER_TOKEN` | worker ↔ browser-runner | at least 24 characters; replace the example placeholder |
| `EGRESS_CONTROL_TOKEN` | worker ↔ egress proxy control socket | at least 24 characters; different from the runner token |

Generate each with `openssl rand -hex 32`. `POSTGRES_PASSWORD` defaults to `postgres`, which is
acceptable only because the port is bound to 127.0.0.1.

`.env` is git-ignored: never commit it. The API reads its own settings as `NOEFFORTS_*`
environment variables (`backend/app/core/config.py`); Compose passes them from `.env`. Running
without Docker, the API reads `backend/.env` instead (README).

**Switches that contact outside services stay off unless you set them on purpose:**
`NOEFFORTS_DISCOVERY_PROVIDERS` (Freehire), `NOEFFORTS_DRAFTING_PROVIDER` and
`NOEFFORTS_ANTHROPIC_API_KEY` (AI drafting, D74). `scripts/check_env.py` warns when any is set.

Check the file before starting (prints key names only, never values):

```bash
python3 scripts/check_env.py .env
```

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
docker compose exec -T worker celery -A app.worker inspect ping   # "pong": worker on the broker
docker compose ps                                                # every service "running"; backend "healthy"
```

Logs: `docker compose logs --tail 100 backend worker`. They are written to carry no applicant
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

## 7. Roll back

Restoring the backup taken before the upgrade is the supported rollback: it brings the code,
the schema and the data back together. Anything done after that backup is lost.

```bash
docker compose stop backend worker frontend       # nothing writes while you restore
git checkout <the commit you ran before>
docker compose build
docker compose up -d postgres redis
docker compose exec -T postgres dropdb -U postgres --force noefforts
docker compose exec -T postgres createdb -U postgres noefforts
docker compose exec -T postgres pg_restore -U postgres -d noefforts --no-owner < backups/noefforts-<stamp>.dump
docker compose run --rm --no-deps -T backend \
  sh -c 'find /data/storage -mindepth 1 -delete && tar xzf - -C /data/storage' < backups/storage-<stamp>.tgz
docker compose up -d
```

The database is dropped and recreated rather than restored over (`pg_restore --clean` would
leave tables that only the newer version had, and the older version's migrations would then
fail). The CI smoke test runs these same commands on a throwaway stack: it backs up, creates a
second account, restores, and checks that the first account's session works and the second
account no longer exists.

`alembic downgrade` exists for each migration, but some refuse while data depends on the newer
schema (for example, the C18/L2 downgrade refuses while a generated document awaits
acceptance). Use it only when release notes say so, and only after a backup.

## 8. Stop and remove

```bash
docker compose stop           # keeps all data
docker compose down           # removes containers, keeps the pgdata and storage volumes
docker compose down -v        # ALSO DELETES YOUR DATA (database and documents)
```

## 9. Verify (safe, throwaway)

```bash
docker compose stop           # the check uses the same local ports
./scripts/verify-local.sh
```

It checks `.env`, validates `docker-compose.yml` with it, and runs the smoke test as a separate,
throwaway Compose project (`noefforts_smoke`) with its own volumes, removed at the end. Your
stack's data is never read or changed, and nothing contacts an employer, Freehire or an AI
provider.

## 10. On a Mac (not yet verified)

Expected, to be confirmed by running section 9 on the Mac:

- Docker Desktop with at least 4 GB of memory for containers (the browser runner alone is
  limited to 1.5 GB).
- Apple silicon: the base images (`python`, `node`, `postgres`, `redis`) are multi-architecture;
  the browser runner installs Chromium for Linux on arm64. Not yet built on arm64.
- The browser runner's seccomp profile (`browser/seccomp.json`) is passed by path; Docker
  Desktop's Linux VM applies it.

Record the result (pass or the first failing line) in `docs/implementation-status.md`.
