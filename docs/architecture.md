# Architecture

## Overview

```
Browser (desktop or phone)
   │  same-origin /api/* (session cookie + CSRF header)
   ▼
Next.js frontend ──rewrite──▶ FastAPI backend ──▶ PostgreSQL (durable state)
                                   │      └────▶ Local file storage (documents)
                                   └─ enqueue ─▶ Redis ─▶ Celery worker(s)
                                                          └─ (Phase C) Playwright execution workers
```

- **Frontend** (`frontend/`): Next.js App Router, client components, Tailwind. It never calls the
  API cross-origin: `next.config.mjs` rewrites `/api/*` to the backend, so cookies are first-party.
  The rewrite target (`NOEFFORTS_BACKEND_URL`) is fixed **at build time**.
- **Backend** (`backend/app`): FastAPI with Pydantic validation. One module per domain under
  `app/modules/` (identity, profiles, jobs, documents, applications, audit). Each module owns its
  models, router and service functions.
- **Database**: PostgreSQL via SQLAlchemy 2 and Alembic migrations. All state that matters
  (applications, events, approvals later) is in Postgres; Redis only carries task messages.
- **Worker**: Celery with Redis broker, `acks_late`, prefetch 1, a hard time limit. Phase A has a
  housekeeping task only; application execution arrives in Phase C.
- **Storage**: `Storage` protocol with a local-filesystem backend. Keys are random UUIDs, never
  user filenames. An S3/MinIO backend can implement the same three methods.

## Data model (Phase A)

| Table | Purpose |
|---|---|
| `users`, `user_sessions` | Accounts; sessions store only a SHA-256 of the cookie token plus a CSRF token |
| `candidate_profiles` | Contact details and **actual residence** (facts) |
| `work_authorizations` | Per country: `authorized`, `sponsorship_needed_now`, `sponsorship_needed_future` (each yes/no/unknown/not_applicable) |
| `employment_records`, `education_records`, `credentials` | Dated history |
| `fact_versions` | Immutable snapshot of every change to a fact |
| `job_preferences` | **Targets** (titles, locations, work modes, salary, exclusions) — kept apart from facts |
| `jobs` | One row per canonical posting per user; unique `(user_id, dedupe_key)` |
| `import_batches` | Each CSV/XLSX import with per-row outcomes |
| `documents` | Immutable document versions grouped by `lineage_id` |
| `applications` | One per user and job; state, outcome, optimistic `lock_version` |
| `application_events` | Append-only timeline |
| `audit_events` | Append-only audit trail (sensitive keys redacted) |

Every fact row carries `provenance` (user_entered / resume_parse / import), `approval_status`
(proposed / approved / rejected), `version` and `updated_at`. User edits are approved by
definition; machine-proposed facts (future resume parsing) stay `proposed` until reviewed.

## Job identity and duplicates

`app/modules/jobs/canonical.py`:
1. URLs are canonicalized (lower-case host, https, tracking params removed, no fragment).
2. Known ATS URLs (Greenhouse, Lever, Ashby, Workable, Workday, SmartRecruiters) yield
   `provider + company + requisition id`, which becomes the dedupe key.
3. Otherwise: employer + requisition id, then canonical URL hash, then a fingerprint of
   normalized employer + title + location.

Inserts use `INSERT … ON CONFLICT DO NOTHING` on the unique key, so concurrent imports cannot
create two rows (covered by a threaded test). A duplicate sighting increments `seen_count` and
fills empty fields without overwriting user edits.

## Application state machine

Defined in `app/modules/applications/states.py`. Each transition lists who may perform it
(`user`, `system`, `worker`); the API only permits `user` transitions.

```
draft → preparing → awaiting_approval → queued → running → ready_to_submit → submitting
                         ↑    │                     │  ↕                          │
                         └────┘ (package changed)   needs_user_action             ├→ submitted_confirmed
                                                                                  ├→ submitted_unconfirmed ─(user reconciles)→ queued / confirmed / failed
                                                                                  └→ failed_terminal (only if nothing was sent)
plus: failed_retryable → queued, cancelled, expired (terminal)
```

Rules that matter:
- No path leads from `submitting` back to a retry. An unknown outcome lands in
  `submitted_unconfirmed` and only a **user** who has checked with the employer can re-queue.
- `lock_version` is SQLAlchemy's version column, so two concurrent writers conflict instead of
  silently overwriting each other.
- Every change writes an `application_events` row.

## Security

- **Sessions**: HttpOnly, SameSite=Lax cookie; server-side session table; CSRF token required in
  `X-CSRF-Token` for every non-GET request. Passwords hashed with Argon2.
- **Tenant isolation**: every query filters by `user_id`; cross-tenant IDs return 404 (tests cover
  profile facts, jobs, documents and applications).
- **SSRF**: `app/core/urlsafety.py` accepts only http(s), no credentials in URLs, no
  localhost/internal hostnames or private/loopback/link-local/metadata IPs.
  `resolve_public_destination` must be called before any server-side fetch and again on every
  redirect hop (Phase A stores URLs but never fetches them).
- **Uploads**: extension allow-list (PDF, DOCX, TXT) plus magic-byte check, size limit, random
  storage keys, `Content-Disposition: attachment`, `nosniff`, `no-store`.
- **Spreadsheets**: XLSX formula cells are rejected per row (never evaluated); exports prefix
  `= + - @ \t \r` with an apostrophe and write XLSX cells as plain strings.
- **Login**: rate-limited per IP and email (in-process; move to Redis when running more than one
  API process).

## Preparation (Phase B)

Module `app/modules/preparation/`:

| File | Responsibility |
|---|---|
| `forms.py` | `FormField` / `FormSchema` models (text, textarea, email, tel, url, number, date, radio, checkbox, checkbox_group, select, multiselect, file) and HTML schema extraction (`<label for>`, wrapping labels, `<fieldset><legend>` groups, `aria-describedby` help, `data-step` sections). Field and form fingerprints detect wording/option changes. |
| `fixtures/*.html`, `fixtures_registry.py` | Local ATS-like test forms with fictional employers (`basic`, `tricky`). Served at `/api/fixtures/forms/{name}` outside production for Phase C browser tests. |
| `classify.py` | Deterministic intent classification (what a question asks), including country, sponsorship time frame, negation, and explicit ambiguity reasons. |
| `resolver.py` | Resolution order and value validation — see `docs/answer-policy.md`. |
| `package.py` | Builds package content, hashes it, writes immutable versions, binds and invalidates approvals, and moves the application between `preparing`, `needs_user_action`, `awaiting_approval` and back out of `queued` when content changes. |
| `drafting.py` | Optional `DraftProvider` interface with grounding validation; `get_provider()` returns `None` (no provider configured). |
| `router.py` | Form capture, package review, answers, consents, document selection, approve/revoke, drafts, answer bank. |

New tables: `job_forms` (versioned schemas per job), `answer_bank`, `application_inputs`
(per-application answers, consent choices, document selections), `application_packages`
(immutable versions), `package_approvals`, `answer_drafts`.

Packages are rebuilt only while nothing can have been sent (`draft` … `queued`,
`failed_retryable`); later states keep their history frozen.

Reconciliation: `POST /api/applications/{id}/reconcile` is the only way out of
`submitted_unconfirmed` towards a retry. It requires a written description of what the user
checked plus explicit confirmation, moves to `failed_retryable`, and re-queueing still needs a
fresh approval.

## Execution (Phase C, local fixtures only)

Module `app/modules/execution/`. Only destinations whose origin is listed in
`NOEFFORTS_FIXTURE_ORIGINS` can be executed, and that setting is ignored in production.

```
user queues ──(same txn)──> attempt(pending) + outbox row
relay ── publishes attempt id ──> Redis ──> Celery task ──> claim (CAS, generation+1, lease)
  → open isolated browser (origin allow-list) → load form → re-extract schema, compare
  → GATE 1 (before disclosure): REPEATABLE READ + app/attempt row locks; approval live,
    unexpired, same package hash, freshly rebuilt content identical → disclosure_started_at
  → fill + upload (evidence: disclosures) → read every control back, compare → re-extract
  → GATE 2 (before send) — the linearization point → attempt `sending`, app `submitting`
  → click submit → classify: receipt → confirmed | code requested → checkpoint
    | refusal → rejected | timeout/error/unrecognised → unknown (submitted_unconfirmed)
sweeper (beat): expired leases → claimed & nothing disclosed: re-pend (≤2) |
  claimed & disclosed: abandoned | sending/awaiting_code: unknown. Never re-sends.
```

Key properties and their limits are in the `service.py` docstring. In short: one active
attempt per application (partial unique index); one worker per attempt can pass gate 2
(fencing generation); nothing after gate 2 is retried; this is duplicate suppression on our
side, not exactly-once delivery at the employer.

Disclosure vs submission: gate 1 authorizes sending the approved data to the named
destination (filling can transmit via autosave, uploads always do). Gate 2 authorizes the
final submit. A form that changes (new fields, new submit target) stops the attempt before
disclosing anything new.

Verification codes: after the submit step, an employer may ask for an emailed code. The
attempt moves to `awaiting_code`, the application to `needs_user_action`, and a checkpoint
bound to user, application, attempt and round is opened. The code is stored only until the
worker reads it, then erased. Wrong codes open a new round (max 3); old rounds are replays.
The worker keeps its browser open while waiting, bounded by `NOEFFORTS_CHECKPOINT_TTL_SECONDS`.
While a worker holds an attempt (claimed, sending, awaiting a code) only the execution service
may change the application's state: package reads do not re-settle it and user transitions
return 409 (`package.execution_owns_state`). Without this, the review page's package read
moved a code-waiting application back to `awaiting_approval` with a valid approval, which
re-enabled Submit after the data had been sent (found by the browser test, now covered).

Evidence policy: receipt id, final origin/path, page title, HTTP status; a readback summary
(which keys mismatched, never values); disclosures (field, upload id, digest); blocked egress
origins. No screenshots, traces, cookies, storage state, codes or answer values. Evidence has
a retention date (`NOEFFORTS_EVIDENCE_RETENTION_DAYS`); a daily beat task purges expired
evidence, and users can delete an application's evidence (`DELETE
/api/applications/{id}/evidence`, refused while an attempt is active).

Browser isolation (`browser.py`, `sandbox/`), enforced outside the browser:

```
worker ──launch──> unshare -n -p -f --mount-proc [-r] ──> netns_boot.py ──exec──> Chromium
                   (own netns: loopback only;            1. lo up
                    own PID ns + /proc)                  2. fork relay 127.0.0.1:P → unix sock
                                                         3. new mount ns: hide code, .env,
                                                            storage, $HOME credential files;
                                                            /tmp = this workdir only
                                                         4. nested user+mount ns (mounts locked)
Chromium --proxy-server=127.0.0.1:P ─> relay ─> EgressProxy (outside): exact host:port of the
destination only; resolves, refuses non-public IPs (fixture exception is test/dev only)
```

The browser gets PATH/HOME/TMPDIR only. Production refuses to run without this isolation
(`NOEFFORTS_BROWSER_ISOLATION=netns`, no user-facing switch). In-process layers (route
allow-list, redirect checks, resolver rules, service workers blocked, pop-ups closed) remain as
defence in depth; non-idempotent requests are passed to the browser (`continue_`), never
fetched and fulfilled, because Playwright resumes a paused request whose fetch is still
pending when the browser closes, and the employer then receives it twice (reproduced; covered
by `test_closing_the_browser_mid_submit_never_resends`).
Limits: hiding is a deny-list on a shared filesystem under the same OS user; there is no
seccomp profile or cgroup limit. Before untrusted live browsing, run browser workers as a
dedicated user in a container that mounts no secrets.

Test oracle: `fixtures/ats_receiver/` (never deployed) with its own ledger and failure modes.

## Planned components (not built)

- Live ATS adapters (each needs its own capability entry and receiver-style tests)
- Dedicated-user / container sandbox for browser workers (see limits above)
- Account export/deletion
- Execution-provider contract, local fixture ATS, first real adapter, evidence store (Phase C).
- Manual verification-code entry, optional Gmail OAuth, spend tracking (Phase D).

## Deployment, backup and recovery (current guidance)

- Single host: `docker compose up`. Put a TLS reverse proxy in front and set
  `NOEFFORTS_COOKIE_SECURE=true`.
- Back up Postgres with `pg_dump` and the storage volume together; documents reference storage
  keys, so restore both from the same point in time.
- Migrations: `alembic upgrade head` runs on backend start. Review any destructive migration
  before deploying.
