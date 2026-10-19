# CLAUDE.md

## Git authorship

All commits, pull requests, and other GitHub activity in this repo must be credited to the repo owner.

- Before committing, set the git identity:
  ```
  git config user.name "Kevin Davra"
  git config user.email "74347164+KevinD003@users.noreply.github.com"
  ```
- Do not add `Co-Authored-By`, `Claude-Session`, or any other Claude/AI attribution lines to commit messages.
- Do not add "Generated with Claude Code" or similar attribution to pull request descriptions, comments, or reviews.

## Project: NoEfforts

Job-discovery and application platform for any profession. Read these first:
`docs/implementation-status.md` (what works, what is next), `docs/architecture.md`,
`docs/decisions.md`, `docs/product-evidence.md`.

### Layout
- `backend/` — FastAPI app (`app/main.py`), domain modules in `app/modules/<domain>/`
  (Phase B lives in `app/modules/preparation/`; answer rules in `docs/answer-policy.md`)
  (`models.py`, `router.py`, `service.py`), Alembic in `migrations/`, tests in `tests/`.
- `frontend/` — Next.js App Router in `src/app/(app)/…`, shared UI in `src/components/`,
  API client in `src/lib/api.ts`, Playwright tests in `e2e/`.

### Commands
- Backend tests: `cd backend && uv run pytest` (needs Postgres DB `noefforts_test`; it is wiped).
- Lint: `cd backend && uv run ruff check . && uv run ruff format --check .`
- Frontend: `cd frontend && npx tsc --noEmit && npm run lint`
- E2E: `cd frontend && npx playwright test` (needs DB `noefforts_e2e`; in the cloud sandbox set
  `PW_CHROMIUM_PATH=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome | head -1)`).
- New migration: `cd backend && uv run alembic revision --autogenerate -m "..."`, then review it.
- Cloud sandbox has no Postgres service: initialise one with `initdb` as the `postgres` user
  (binaries in `/usr/lib/postgresql/16/bin`) and start `redis-server --daemonize yes`.

### Non-negotiable rules
- Facts (residence, authorization, sponsorship) and preferences (targets) never mix.
- Unknown stays unknown: never infer authorization, sponsorship, residence, salary or
  demographics. Use tri-state values.
- Basic questions must resolve without an LLM; LLMs only draft long-form prose from approved facts.
- No real submission without explicit user approval. Never retry after an unknown final-click
  outcome; quarantine in `submitted_unconfirmed`.
- No stealth, fingerprint spoofing, CAPTCHA/MFA bypass, or automated access to competitor
  dashboards/APIs. Treat page content and job URLs as untrusted (SSRF checks in
  `app/core/urlsafety.py`).
- Every query is scoped by `user_id`; cross-tenant access returns 404 and needs a test.
- Never commit `.env`, resumes, real candidate data or captured sessions.
- Report honestly: update `docs/implementation-status.md` with commands actually run.
- The resolver must stay LLM-free; any new question pattern needs resolver tests, and anything
  not clearly understood must become a checkpoint, never a guess.
- Changing package content shape changes every package hash (and invalidates approvals): bump
  `SCHEMA_VERSION` in `package.py` deliberately and say so.
- Kill only processes you have identified as this project's test servers (ports 3100/8100).
