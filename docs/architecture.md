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

The browser gets PATH/HOME/TMPDIR only, starts in its own work directory (not the worker's),
and inherits no descriptors beyond stdio and the DevTools pipes. Production refuses to run
without this isolation (`NOEFFORTS_BROWSER_ISOLATION=netns`, no user-facing switch); if the
namespaces or the browser cannot be started, the attempt stops before disclosure (no fallback
to an unisolated browser). Work directories are named after the worker PID; the sweep task
removes those whose worker is gone (a hard-killed worker cannot clean up).

Proxy policy: HTTPS arrives as CONNECT, plain HTTP as absolute-form requests; both are checked
against the exact destination host:port, every resolved address must be public (unless that
exact host:port is a fixture origin, which production ignores), and the proxy connects to the
address it checked, so a later DNS answer cannot redirect it. Redirect hops, subresources and
WebSockets reach the proxy as new requests and get the same check.

In-process layers (route allow-list, redirect checks, resolver rules, service workers blocked,
pop-ups closed) remain as defence in depth. GET/HEAD are fetched by the route handler with
redirects checked hop by hop and aborted on any fetch error; other methods are passed to the
browser (`continue_`) and sent once by Chromium. Reason: with Playwright Python 1.56.0 and
Chromium 141 (the pinned versions), a POST answered through `route.fetch` + `fulfill` was sent
a second time when the browser closed while that fetch was pending or had timed out (paused
original resumed). This is observed behaviour of that version and workflow, not a claim about
Playwright in general; `test_closing_the_browser_mid_submit_never_resends` pins it. None of
this guarantees exactly-once delivery: a response lost after the employer accepted, or an
employer-side duplicate, stays possible, which is why an unanswered submit becomes `unknown`
and is reconciled, never resent (broker redelivery is refused by the claim CAS).

Platform requirements: Linux with `unshare` (util-linux) and user, network, PID and mount
namespaces. Unprivileged workers need unprivileged user namespaces; Ubuntu 24.04 restricts
them through AppArmor, which CI lifts with `sysctl kernel.apparmor_restrict_unprivileged_userns=0`
on its throwaway runner. That is a CI host setting, not the supported deployment configuration:
a deployment should give browser workers a host or container profile that permits these
namespaces for that service only (Docker's default seccomp profile does not). The Compose stack
does not support execution yet: the image has no browser, so attempts fail safe. On macOS there
are no Linux namespaces; development there can run everything except execution, or execution
against fixtures with `NOEFFORTS_BROWSER_ISOLATION=off`, which only non-production accepts.

Limits:
- Hiding is a deny-list on a shared filesystem under the same OS user, not a minimal root
  filesystem: other files readable by that user stay readable.
- Chromium runs with Playwright's default `--no-sandbox` as uid 0 of a nested user namespace
  (full capabilities inside it, none outside); there is no seccomp profile or cgroup limit.
- Before untrusted live browsing, run browser workers as a dedicated user in a container that
  mounts no secrets, and evaluate enabling Chromium's own sandbox.

Adapters (`execution/adapters/`, chosen at queue time by `policy.adapter_for`, recorded on the
attempt): `fixture_ats` for the generic synthetic form and `greenhouse_hosted` for forms captured
from a Greenhouse-style job post (`docs/greenhouse-adapter.md`). Both run only against fixture
origins; capability flags are served at `GET /api/execution/capabilities`.

Test oracle: `fixtures/ats_receiver/` (never deployed) with its own ledger and failure modes,
including the labelled Greenhouse approximation `greenhouse_like.py`.

## Execution routing and provider roles

Each application takes the safest supported path:

1. an authorized API (user grant, credentials, declared support);
2. else a supported browser adapter for that form and origin;
3. else a checkpoint for the user, or a manual handoff.

The job's ATS is identified first. An ATS with only a planned adapter (Workday) is a manual
handoff that says so, and a form captured as another ATS is refused. The full order, the
capability matrix and the safety rules with their tests are in `docs/provider-architecture.md`
§2b and §9. The route is served at `GET /api/jobs/{id}/route` and shown on the job page.

| Component | Primary role | Not responsible for |
|---|---|---|
| Freehire or other job source | Discover/import job listings and URLs | Filling or submitting employer applications |
| ATS adapter | Read, map, fill and verify a specific ATS workflow | Broad compatibility claims without evidence |
| Browser worker | Execute approved browser steps in isolation | Guessing facts or bypassing restrictions |
| Authorized API connector | Structured retrieval/submission where permitted | Replacing browser support everywhere |
| Candidate profile and answer bank | Approved facts and reusable answers | Inferring missing legal/sensitive answers |
| User | Approval, verification, manual checkpoints, final scope decisions | Repeatedly re-entering already approved facts |

## Submission providers and discovery (local only)

Details: `docs/provider-architecture.md` (decision D32).

- **Model** (`app/modules/providers/`):
  - every provider has a kind (`browser`, `api`, `discovery`, `observation`, `manual`), the
    operations it implements and capability flags;
  - each capability is at a support level: `fixture`, `observed`, `live_fill` or
    `live_submit`;
  - `check_spec` refuses live claims without real-page evidence, and anything live while
    `real_destinations_enabled` is false;
  - no provider has live support.
- **Routing** (`routing.decide`, used by `policy.execution_binding`):
  - real destination → manual handoff;
  - authorized API → only with the user's grant (`api_authorizations`), configured
    credentials and declared API submission;
  - else the browser adapter;
  - else manual handoff.
  - The chosen provider and version are part of the approval binding (D28). A route change
    retires the approval at queueing and stops the worker before disclosure.
- **API route** (`adapters/fake_api.py`, `runner._run_api`): the same attempt, lease, gates
  and fencing as the browser route.

  ```
  schema check → gate 1 → draft + documents (disclosures) → gate 2 → submit once (idempotency
  key = attempt id) → confirmed | rejected | unknown → reconcile_api (read-only, never resends)
  ```

  It is exercised only against the receiver's fake API (`fixtures/ats_receiver/fake_api.py`),
  which is NoEfforts' own contract, not any real ATS's.
- **Discovery** (`app/modules/discovery/`):
  - providers normalize records into `discovered_jobs` (source facts kept apart, tri-state);
  - they deduplicate through `jobs.upsert_job` and mark stale records;
  - they never touch the profile;
  - `application_route` is a manual handoff until a form is captured.
  - Providers: a Freehire client for its documented public read API (fixture base URLs only)
    and a local mock file. Both are off by default (`docs/discovery.md`).
- **Checkpoints** (`providers/checkpoints.py`):
  - CAPTCHA, bot checks, login/MFA, SMS codes and identity checks stop the attempt and send
    the user to the employer's site;
  - only an emailed code entered by the user can resume an attempt;
  - nothing is solved or bypassed.

## Planned components (not built)

- Live ATS adapters (each needs its own capability entry and receiver-style tests)
- Dedicated-user / container sandbox for browser workers (see limits above)
- Account export/deletion
- A real API provider (needs an agreement, secret storage, its own adapter and capability entry).
- Multi-page adapters with a disclosure boundary per step (Workday: see provider-architecture.md).
- A live discovery provider (Freehire is fixture-only; see `docs/discovery.md`).
- Manual verification-code entry, optional Gmail OAuth, spend tracking (Phase D).

## Deployment, backup and recovery (current guidance)

- Single host: `docker compose up`. Put a TLS reverse proxy in front and set
  `NOEFFORTS_COOKIE_SECURE=true`.
- Back up Postgres with `pg_dump` and the storage volume together; documents reference storage
  keys, so restore both from the same point in time.
- Migrations: `alembic upgrade head` runs on backend start. Review any destructive migration
  before deploying.
