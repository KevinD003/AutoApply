# Implementation status

Last updated: 2026-10-19. Labels: **complete**, **partial**, **blocked**, **not started**.

## Phase A — Local foundation

| Item | Status | Evidence |
|---|---|---|
| Runnable API, DB migrations, worker | complete | `uvicorn` + `alembic upgrade head`; Celery task ran (`purge_expired_sessions` succeeded) |
| Runnable web app | complete | `next build` succeeds; Playwright e2e passes |
| Authentication (register/login/logout, sessions, CSRF, rate limit) | complete | `tests/test_auth.py` |
| Profile facts with provenance, approval, versions, history | complete | `tests/test_profile.py` |
| Work authorization / sponsorship per country | complete | `tests/test_profile.py` |
| Employment, education, credentials | complete (credentials API only, no UI) | `tests/test_profile.py` |
| Preferences (titles, fields, industries, seniority, types, modes, locations, relocation, salary, exclusions) | complete | `tests/test_profile.py`, e2e |
| Manual job creation from URL or fields | complete | `tests/test_jobs.py`, e2e |
| CSV/XLSX import with row-level errors, stable row IDs; export | complete | `tests/test_jobs.py`, e2e |
| Duplicate detection across imports and concurrent workers | complete | `tests/test_jobs.py::test_concurrent_upserts_create_one_job` |
| Exclusion reasons and simple match explanations | partial (preference checks only, no scoring) | `tests/test_jobs.py` |
| Document upload, immutable versions, protected download | complete (preview not built) | `tests/test_documents.py`, e2e |
| Application tracker with durable states and timeline | complete for manual tracking | `tests/test_applications.py`, e2e |
| Docker Compose stack | **untested** — no Docker daemon in the build sandbox | `docker-compose.yml` |
| Account deletion / data export | not started | |

## Phase B — Preparation: not started
Deterministic resolver, answer bank, schema extraction, grounded long-form drafting, package
preview and approval binding.

## Phase C — Controlled execution: not started
Adapter contract, local fixture ATS, first real adapter, confirmation evidence, pause/resume.

## Phase D — Verification and integrations: not started
Manual code entry, optional Gmail OAuth, optional managed provider, spend reporting.

## Phase E — Expansion: not started

## Tests actually run (2026-10-19)

| Command | Result | Covers |
|---|---|---|
| `cd backend && uv run pytest` | 44 passed | API + DB against PostgreSQL 16 |
| `cd backend && uv run ruff check .` | clean | lint |
| `cd frontend && npx tsc --noEmit && npm run lint` | clean | types, lint |
| `cd frontend && npx playwright test` | 2 passed (desktop 1280×800, mobile 390×844) | register → profile → work auth → preferences → add/duplicate job → import CSV → explanations → track → outcome → upload document → reload persistence |

Coverage boundary: all data synthetic; no employer site, ATS, LLM, Gmail or Freehire was
contacted by any test. No real application has been submitted.

## Acceptance tests from the brief

| Brief requirement | Status |
|---|---|
| Basic profile questions resolve without any LLM call | not started (Phase B) |
| Missing facts park the application | not started (Phase B) |
| Sponsorship, authorization, residence, desired location remain distinct | **done** at data level (`test_profile.py`) |
| Negation / future tense / changed options cannot invert answers | not started (Phase B) |
| Long-form drafting preserves facts and length | not started (Phase B) |
| Approval invalidated when the package changes | not started (Phase B) |
| Cross-tenant profile, resume, session and OTP access denied | **done** for profile, documents, jobs, applications; OTP in Phase D |
| Duplicate imports and concurrent workers do not duplicate attempts | **done** for jobs and application identity |
| Failed uploads / incomplete required fields cannot proceed to submit | not started (Phase C) |
| Unknown final outcomes do not trigger blind retry | **done** in the state machine (`test_applications.py`); enforcement in workers comes with Phase C |
| Checkpoint expiry, cancellation, crash, session loss recover safely | not started (Phase C) |
| Redirects and untrusted URLs cannot reach internal targets | partial: URL and DNS checks done and tested; per-redirect enforcement arrives with the first fetcher |
| Models disabled gracefully without credentials | not started (no LLM code yet) |
| Spreadsheet parsing/export is safe | **done** (`test_jobs.py`) |

## Blocked / needs you

- **Freehire API and live ATS pages** are blocked by this cloud sandbox's network policy. Develop
  those parts locally, or allow `freehire.me` in the environment's network settings.
- **LLM key** for Phase B drafting (optional; drafting stays off without it).
- **Docker** verification must be done on your machine.
