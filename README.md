# NoEfforts

NoEfforts is a job-discovery and application platform for any profession. You keep a single
reviewed profile, collect jobs (links, spreadsheets, later feeds), and NoEfforts prepares
applications that you approve before anything is sent.

**Current state:** Phase A (local foundation) works end to end: accounts, profile facts,
preferences, jobs with duplicate detection, CSV/XLSX import and export, document versions, and
an application tracker. Automated form filling and submission are **not built yet**. See
[`docs/implementation-status.md`](docs/implementation-status.md).

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
cp .env.example .env
docker compose up --build
```
Then open http://localhost:3000. Data lives in the `pgdata` and `storage` volumes.

## Tests

```bash
# Backend: needs a PostgreSQL database for tests (it is wiped on each run)
createdb noefforts_test
cd backend && uv run pytest
uv run ruff check .

# Frontend: typecheck, lint, then end-to-end (needs Postgres + a database named noefforts_e2e)
cd frontend
npx tsc --noEmit && npm run lint
createdb noefforts_e2e
npx playwright install chromium   # first time only
npx playwright test
```
Override test databases with `NOEFFORTS_TEST_DATABASE_URL` / `NOEFFORTS_E2E_DATABASE_URL`.

## Safety defaults

- Nothing is submitted to an employer without your explicit approval (submission is not
  implemented yet at all).
- Unknown facts stay unknown. NoEfforts never guesses authorization, sponsorship, residence,
  salary or demographic answers.
- Secrets go in `.env` files, which are git-ignored. Never commit resumes or real candidate data.
