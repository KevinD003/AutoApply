# Implementation status

Last updated: 2026-10-19. Labels: **complete**, **partial**, **blocked**, **not started**,
**untested**.

## Commits

| Commit | Content |
|---|---|
| `37e6646` | Phase A backend |
| `af09822` | Phase A frontend + Playwright |
| `3550c2b` | Docker, `.env.example`, docs |
| `dce67c8` | Corrected Tsenta/Gmail research notes |
| `ffed5c5` | Removed `CONTRIBUTION_TEST.md` (one-off attribution test; no references anywhere) |
| `d5ead14` | Phase B backend + Phase A hardening |
| `29a1960` | Phase B review screen, saved answers, reconciliation UI |

Tests below were run against `29a1960` (plus this documentation update).

## Tests actually run (2026-10-19, cloud sandbox, PostgreSQL 16, Redis 7, Python 3.12, Node 22)

| Command | Result |
|---|---|
| `cd backend && uv run pytest` | **95 passed** |
| `cd backend && uv run ruff check . && uv run ruff format --check .` | clean |
| `cd backend && uv run alembic downgrade base && uv run alembic upgrade head` | full cycle OK (after fixing enum handling) |
| `cd frontend && npx tsc --noEmit && npm run lint` | clean |
| `cd frontend && npx playwright test` | **4 passed**: Phase A + Phase B flows, desktop 1280×800 and mobile 390×844 |
| `celery -A app.worker worker` + `purge_expired_sessions.delay()` | task succeeded (Phase A run; worker module changed since only to import all models) |

Coverage boundary: synthetic data and local fixture forms only. No employer site, ATS, LLM,
Gmail, Freehire or Tsenta was contacted. No real application was prepared for or sent to an
employer.

## Phase A verification (requested checks)

| Check | Result | Test |
|---|---|---|
| Cross-user access to profiles, documents, jobs, applications denied | pass | `test_profile::test_cross_tenant_fact_access_denied`, `test_documents::test_cross_tenant_document_access_denied`, `test_jobs::test_cross_tenant_job_access_denied`, `test_applications::test_cross_tenant_application_access_denied` |
| Auth + CSRF work together | pass; token bound to its session; logout kills cookie and token; GETs need no token, writes do | `test_auth.py`, `test_phase_a_verification.py` (3 tests) |
| Job imports enforce ownership | pass; same file imported by two users creates separate rows and does not count as a sighting for the other | `test_imports_never_touch_another_users_jobs` |
| Document downloads enforce ownership | pass | `test_cross_tenant_document_access_denied` |
| Duplicate jobs have DB protection | pass (unique constraint + `ON CONFLICT`, 8 concurrent writers) | `test_concurrent_upserts_create_one_job` |
| Duplicate applications have DB protection | pass (unique constraint; 6 concurrent API requests → one row) | `test_duplicate_applications_blocked_by_database`, `test_concurrent_application_creation_yields_one` |
| Uncertain submissions cannot be blindly re-queued | **was failing**: the API allowed `submitted_unconfirmed → queued` by the user in one call. **Fixed**: transition removed; reconciliation endpoint requires a written check and explicit confirmation; re-queueing then requires a fresh approval | `test_uncertain_submission_cannot_be_requeued_directly`, `test_unknown_submission_outcome_never_auto_retries` |
| Worker restarts do not lose durable state | pass for what exists: a separate process writes a transition and exits; a fresh process reads it back. Concurrent writers conflict (version column) instead of overwriting. **Limitation:** Phase A/B have no long-running application tasks, so killing a worker mid-task is not yet testable; Phase C must add that test. | `test_application_state_survives_process_restart`, `test_concurrent_writers_conflict_instead_of_overwriting` |
| Worker loads all models | **was a latent bug** (only `UserSession` imported; any task touching applications would fail). Fixed. | covered by the restart test's subprocess |
| Docker | **untested** — no Docker daemon in this sandbox | — |

## Phase A — Local foundation

| Item | Status |
|---|---|
| API, migrations, worker, web app | complete |
| Authentication, sessions, CSRF, login rate limit | complete |
| Profile facts with provenance, approval, versions, history; given/family/preferred names | complete |
| Work authorization and sponsorship (now / later) per country | complete |
| Employment, education, credentials | complete (credentials have no UI) |
| Preferences | complete |
| Manual jobs, CSV/XLSX import/export, duplicates, exclusions | complete |
| Match explanations | partial (preference checks, no scoring) |
| Documents: upload, immutable versions, protected download | complete (no preview) |
| Tracker with durable states, timeline, reconciliation | complete for manual tracking |
| Docker Compose | untested |
| Account deletion / data export | not started |

## Phase B — Preparation (this milestone)

| Item | Status | Evidence |
|---|---|---|
| Form schema model: text, textarea, email, tel, url, number, date, radio, checkbox, checkbox group, select, multiselect, file; required, help text, original wording, options, step, stable key | complete | `forms.py`, `test_resolver::test_fixture_classification_table` |
| HTML schema extraction | complete for accessible standard markup; unusual markup is rejected, not guessed | `test_attaching_unreadable_html_is_rejected` |
| Local ATS-like fixture forms (fictional employers) | complete (`basic`, `tricky`) | e2e + API tests |
| Deterministic resolver, zero LLM calls | complete | `test_full_workflow_with_zero_llm_calls` (spy provider fails if called), 18 resolver unit tests |
| Residence / target location / authorization / sponsorship now / later kept separate | complete | resolver tests |
| Negation, future tense, vague wording, missing country, compound questions | complete for the patterns listed in `docs/answer-policy.md`; anything else becomes a checkpoint | resolver tests |
| Changed options and wording | complete | `test_answer_bank_reuse_across_jobs_and_wording_changes`, `test_form_option_change_invalidates_saved_choice` |
| Answer bank with provenance, approval, version, timestamps | complete (edit-in-place UI not built; delete and re-save instead) | `test_answer_bank_*` |
| Acknowledgments never auto-checked; sensitive answers need consent | complete | resolver + API tests |
| Missing facts park the application; profile fix resolves | complete | `test_missing_fact_parks_application_and_profile_fix_resolves` |
| Immutable package versions; approval bound to content hash | complete | `test_package_versions_are_immutable` |
| Invalidation on fact, document, answer, consent, destination change; unrelated edits keep approval | complete | `test_protected_fact_change_invalidates_approval`, `test_other_material_changes_invalidate_approval` (4 cases), `test_unrelated_fact_change_keeps_approval` |
| Queueing requires live approval | complete | API tests |
| Review screen | complete | Playwright `phase-b.spec.ts` |
| Long-form drafting interface with grounding validation | partial: interface, validation, caching, acceptance flow done and tested with a **test-only fake provider**; **no real LLM provider is implemented**, so drafting shows as unavailable | `test_fake_provider_draft_is_validated_and_needs_acceptance`, `test_drafting_unavailable_without_provider` |
| Tenant isolation for forms, packages, answers, consents, documents, answer bank | complete | `test_tenant_isolation_for_preparation` |
| Resume parsing into proposed facts | not started (resolver already ignores proposed facts) | — |
| Capturing forms from live ATS pages | not started (Phase C; network-blocked here) | — |

## Phase C — Controlled execution: not started
Adapter contract, browser execution against the local fixtures, one narrowly scoped real
adapter, confirmation evidence, pause/resume, worker-crash tests.

## Phase D — Verification and integrations: not started
Manual code entry, optional Gmail OAuth (personal/testing first; see `docs/research/gmail-oauth.md`),
optional Tsenta provider (disabled by default; docs inaccessible from this environment),
spend reporting.

## Phase E — Expansion: not started

## External services status

| Service | Docs | Access | Implemented | Tested |
|---|---|---|---|---|
| Tsenta | product + MCP docs read; developer docs inaccessible from this environment | none | no | no |
| Freehire API | read in code and public docs | network-blocked here | no | no |
| Gmail API | requirements documented | none | no | no |
| LLM provider | — | no key configured | interface only | fake provider in tests only |
| REA | README/docs read | `--help` ran once | not used for any analysis | — |

## Known limitations

- Classification covers English wording and the patterns in `docs/answer-policy.md`;
  everything else becomes a checkpoint (safe but more manual work).
- The country list in `classify.py` is partial (24 countries); unlisted countries are asked.
- Login rate limiting is per process.
- Next.js resolves the API address at build time; rebuild after changing
  `NOEFFORTS_BACKEND_URL`.
- Fixture forms are reachable without login outside production (they contain no user data).
