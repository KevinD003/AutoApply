# NoEfforts

NoEfforts is a job-discovery and application platform for any profession. You keep a single
reviewed profile, collect jobs (links, spreadsheets, later feeds), and NoEfforts prepares
applications that you approve before anything is sent.

**Current state:** profile, jobs, deterministic answer preparation with approval, and
automatic submission **to local synthetic test forms only**. No real employer system is
supported for automatic submission. See
[`docs/implementation-status.md`](docs/implementation-status.md) and
[`docs/evidence-matrix.md`](docs/evidence-matrix.md).

## Repository layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI API, Celery worker, SQLAlchemy models, Alembic migrations, pytest suite |
| `frontend/` | Next.js (TypeScript, Tailwind) web app, Playwright end-to-end tests |
| `docs/` | Architecture, decisions, status, product evidence and research notes |
| `docker-compose.yml` | Local stack: Postgres, Redis, API, worker, web |

## Run it on macOS with VS Code (no Docker)

1. **Install the tools** (one time). With [Homebrew](https://brew.sh):
   ```bash
   brew install postgresql@16 redis node@22 uv
   brew services start postgresql@16
   brew services start redis
   createdb noefforts
   ```
   VS Code extensions that help: Python, Pylance, ESLint, Tailwind CSS IntelliSense.

2. **Configure** — copy the example settings and adjust the database user if needed:
   ```bash
   cp .env.example backend/.env
   ```
   On Homebrew Postgres the user is usually your macOS username with no password, e.g.
   `NOEFFORTS_DATABASE_URL=postgresql+psycopg://YOURNAME@127.0.0.1:5432/noefforts`.
   Set `NOEFFORTS_AUDIT_REF_KEY` to a secret of your own (e.g. the output of
   `openssl rand -hex 32`); the API refuses to start without it. For Docker Compose set
   `AUDIT_REF_KEY` in `.env` the same way.

3. **Start the API** (terminal 1):
   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload --port 8000
   ```
   API docs: http://127.0.0.1:8000/api/docs

4. **Start the worker** (terminal 2, optional in Phase A):
   ```bash
   cd backend && uv run celery -A app.worker worker --beat --loglevel=info
   ```

5. **Start the web app** (terminal 3):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open http://localhost:3000 and create an account.

## Run it with Docker

```bash
cp .env.example .env              # then set AUDIT_REF_KEY, BROWSER_RUNNER_TOKEN and
                                  # EGRESS_CONTROL_TOKEN, each from `openssl rand -hex 32`
python3 scripts/check_env.py .env # names any missing or placeholder secret (never prints values)
docker compose up -d --build
```
Then open http://localhost:3000. Data lives in the `pgdata` and `storage` volumes. Health
checks, backups, upgrades, rollback and a safe verification run (`./scripts/verify-local.sh`)
are in [docs/deployment.md](docs/deployment.md). It has been run in CI on Linux, not yet on a Mac.

Your own scripts, the `noefforts` command line and a local MCP client read your data with an
API token (Account → API tokens): [docs/api-tokens.md](docs/api-tokens.md). Tokens can read,
or add jobs; they can never answer, approve or submit.

## Tests

```bash
# Backend: needs PostgreSQL and Redis on localhost. The suite drops and recreates its database's
# schema, so it runs only on a disposable database of its own: no default, never a shared one
# (D103, backend/tests/isolation.py). Execution tests start the synthetic receiver (port 8799)
# and a real Celery worker themselves; each run holds its ports and Redis database.
cd backend && uv run playwright install chromium   # first time only
eval "$(uv run python -m tests.isolation create --export)"   # owned by the test-only role, marked
uv run pytest
uv run python -m tests.isolation drop --run "$NOEFFORTS_TEST_RUN_ID"   # only this run's databases
uv run ruff check .

# Frontend: typecheck, lint, then end-to-end (on a disposable database named noefforts_e2e_test)
(cd backend && uv run python -m tests.isolation create --name noefforts_e2e_test --run e2e)
cd frontend
npx tsc --noEmit && npm run lint
npx playwright install chromium   # first time only
npx playwright test
```
`scripts/validate.sh all` does all of this with a database of its own per suite. A second run
on the same database, Redis database or port is refused before anything is dropped
([docs/test-isolation.md](docs/test-isolation.md)).

## Safety defaults

- Nothing is submitted without your explicit approval. Submission works only to the local
  synthetic test receiver; real employer sites are refused (apply there yourself, then record
  the application with "Track application").
- Unknown facts stay unknown. NoEfforts never guesses authorization, sponsorship, residence,
  salary or demographic answers.
- Secrets go in `.env` files, which are git-ignored. Never commit resumes or real candidate data.
