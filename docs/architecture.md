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
| `application_events` | Append-only timeline; insert-only in the database (a trigger refuses UPDATE, and DELETE unless it cascades from the application or user). `source`, `from_outcome`/`to_outcome`, `occurred_on`, `evidence_note` (D53) |
| `api_tokens` | Personal access tokens (D84): public id, the token's SHA-256 hash (never the token), label, scopes, expiry, last used (to the hour), revoked; `docs/api-tokens.md` |
| `notification_reads` | That you read a notification, by its key (D83). Notifications themselves are derived from the records they describe, never stored |
| `audit_events` | Audit trail; `meta` sanitized before storage (`docs/audit-events.md`). Application code never updates or deletes rows; the privacy repair migration `c303eee5a3c9` rewrote legacy `meta` once |

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
                         └────┘ (package changed)   needs_user_action             ├→ submitted_confirmed (worker: its attempt's employer receipt; source receipt)
                                                                                  ├→ submitted_unconfirmed ─(user, saying what they checked: /reconcile received or /transition)→ submitted_confirmed (user_claimed)
                                                                                  │                        ─(reconciled not received)→ failed_retryable; ─(user)→ failed_terminal
                                                                                  └→ failed_terminal (only if nothing was sent)
plus: needs_user_action → submitted_unconfirmed (an unknown outcome in the verification-code
step, recorded by the worker or the sweeper; or the user applied by hand);
draft, awaiting_approval → submitted_unconfirmed (the user applied by hand; user_claimed);
failed_retryable → queued (the user, with a valid approval), cancelled, expired (terminal)
```

Rules that matter:
- No path leads from `submitting` back to a retry. An unknown outcome lands in
  `submitted_unconfirmed` and only a **user** who has checked with the employer can re-queue.
- `lock_version` is SQLAlchemy's version column, so two concurrent writers conflict instead of
  silently overwriting each other.
- Every state or outcome change writes an insert-only `application_events` row; editing the
  notes writes none.
- **What a submission rests on (D53).** An event's `source` is set by
  `applications/service.py` from the move and its actor, never by a client: `receipt` (the
  worker observed the employer's receipt), `user_claimed` (the user applied by hand, or
  confirmed it saying what they checked, kept in `evidence_note`), `user_reported` (an outcome).
  A user's confirmation needs 15 to 2,000 characters of what they checked. An application's
  `submission` (receipt, user_claimed, unconfirmed) is computed when read; a receipt recorded on
  one of its attempts counts even when it arrived after the application was quarantined.
- **Outcomes (D53).** Recorded by the user only (`PATCH /applications/{id}`), with an optional
  date and private note; never inferred. An outcome other than `none` or `withdrawn` needs a
  submission NoEfforts knows of: a submitted state now or before, or a recorded receipt. Under
  this rule an application cancelled, expired or failed before any submission can never take an
  employer outcome. The funnel (`GET /applications/funnel`, `applications/funnel.py`) is counted
  per user when read: counts and denominators, no rate, and a note below 20 submissions.

**Refusal codes**

| Code | Refused when | Message |
|---|---|---|
| `evidence_required` | the user confirms a submission without at least 15 characters of what they checked | To confirm this submission yourself, say what you checked, in at least 15 characters (for example the reference in the employer's confirmation email). It is recorded as your statement, not as an employer receipt. |
| `outcome_before_submission` | an outcome other than none or withdrawn, on an application with no submission NoEfforts knows of | NoEfforts has no record that this application reached the employer, so an employer's outcome cannot be recorded for it. Withdrawn can always be recorded. |
| `confirm_through_reconcile` | the owner's switch routes confirmations through reconciliation only (off by default) | Confirm a submission by reconciling it: say what you checked and choose It was received. |

Each is a 400 whose detail ends `(reason: <code>)`; refusals write nothing and are not audited.

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
| `drafting.py` | Optional `DraftProvider` interface with grounding validation; `get_provider()` returns the owner-configured provider or `None` (the default), `provider_for()` adds the owner, consent and budget checks (D74). |
| `anthropic_provider.py`, `drafting_access.py` | Claude through Anthropic's API, off by default; the owner account, the user's consent to the exact text, and the daily budget reserved at each request's worst case (L4, D74). |
| `router.py` | Form capture, package review, answers, consents, document selection, approve/revoke, drafts, answer bank (one upsert per save, D51). |
| `bankscope.py` | Which answers are never saved to or reused from the answer bank, and why (D51); the bank key. Pure. |

New tables: `job_forms` (versioned schemas per job), `answer_bank`, `application_inputs`
(per-application answers, consent choices, document selections), `application_packages`
(immutable versions), `package_approvals`, `answer_drafts`.

Packages are rebuilt only while nothing can have been sent (`draft` … `queued`,
`failed_retryable`); later states keep their history frozen.

Reconciliation: `POST /api/applications/{id}/reconcile` is the only way out of
`submitted_unconfirmed` towards a retry. It requires a written description of what the user
checked plus explicit confirmation, moves to `failed_retryable`, and re-queueing still needs a
fresh approval: the approval that sent it is retired in the same transaction (D15, enforced
since I2), as is an approval whose final click waited for a verification code that never came.
Reconciliation locks the application's attempts first (D46) and refuses "not received" once
the employer's receipt is recorded; a recorded confirmation is never queued again.

## Execution (Phase C, local fixtures only)

Module `app/modules/execution/`. Only destinations whose origin is listed in
`NOEFFORTS_FIXTURE_ORIGINS` can be executed, and that setting is honoured only when
`NOEFFORTS_ENV=test`; a listed name must also resolve, at every connection, to loopback or the
configured test network (D86).

```
user queues ──(same txn)──> attempt(pending) + outbox row
relay ── publishes attempt id ──> Redis ──> Celery task ──> claim (CAS, generation+1, lease)
  → open isolated browser (origin allow-list) → load form → re-extract schema, compare
  → GATE 1 (before disclosure): attempt, app and approval row locks, then reads at READ
    COMMITTED (D46): approval live, unexpired, same package hash, freshly rebuilt content
    identical; for an approval to submit, the rehearsal prerequisite (E6) →
    disclosure_started_at
  → fill + upload (evidence: disclosures) → read every control back, compare → re-extract
  → a rehearsal (approval scope `disclose_only`) stops here, through a gate: every gate check
    again under the same locks, and the evidence rows checked; then, in one commit, its record,
    attempt `rehearsed`, approval used up. Refused: `abandoned`. Nothing submitted
  → GATE 2 (before send) — the linearization point; refuses any scope but `submit`, and an
    unmet rehearsal prerequisite (E6) → attempt `sending` (prerequisite recorded), app
    `submitting`
  → click submit → classify: receipt → confirmed | code requested → checkpoint
    | refusal → rejected | timeout/error/unrecognised → unknown (submitted_unconfirmed);
    after a code: accepted → confirmed | unknown → unknown (submitted_unconfirmed)
sweeper (beat): expired leases → claimed & nothing disclosed: re-pend (≤2) |
  claimed & disclosed: abandoned | sending/awaiting_code: unknown (its open checkpoint expires,
  a held code is erased). Each attempt in its own savepoint: one that fails is counted
  (`errors`), stays for the next sweep and never stops the others (D50). Never re-sends.
```

Key properties and their limits are in the `service.py` docstring. In short: one active
attempt per application (partial unique index); one worker per attempt can pass gate 2
(fencing generation); nothing after gate 2 is retried; this is duplicate suppression on our
side, not exactly-once delivery at the employer.

### Lock order (D46)

Every transaction that locks more than one of these rows takes them in this order:

1. the execution attempt (FOR UPDATE; the claim's compare-and-swap UPDATE);
2. its application (FOR UPDATE);
3. its approval (FOR SHARE in the gates, FOR UPDATE at the rehearsal stop; the UPDATE of
   approve, revoke and package rebuilds);
4. the application's inputs (answers and consents: saved, and cleared, after the application);
5. what the rehearsal prerequisite relies on: a rehearsal record or a receipt (FOR SHARE in the
   gates; FOR UPDATE or DELETE by a withdrawal or an evidence deletion).
6. a saved answer (`answer_bank` row): after the application and its input when an answer is
   saved for reuse (one upsert), or alone when it is deleted (one DELETE). Package rebuilds and
   the gates read the bank without locking it (D51).

Outcomes and confirmations (D53): an outcome or notes (`PATCH /applications/{id}`) locks only the
application and re-reads it before deciding; a user's confirmation (`/transition` to
`submitted_confirmed`, `/reconcile`) locks the application's attempts by id, then the
application (`applications/service.py` `lock_submission`), the order the worker's receipt takes.
`tests/test_outcome_races.py` races both against the worker.

Account deletion (D77, `account/deletion.py`) locks the account's watches, then all of its
active attempts by id, then all of its applications by id, and only then deletes the account
row (whose cascade removes everything else). The account row is never locked first: a worker
holding an attempt inserts evidence that key-share locks it. A deadlock with a concurrent write
the order does not cover is retried once, then refused. `tests/test_account.py` races deletion
against both gates.

Inserting a row that references an application (evidence, events) key-share locks the
application too; that happens after the attempt, in the same order. Paths that never lock an
attempt (approve, revoke, answers, consents, withdrawal, evidence deletion) start at the
application. A checkpoint row is locked only alone (the user entering a code) or while its
attempt is held (the worker). Cancel locks the active attempt, then the application. Two locks
are taken against the order, and only without waiting (NOWAIT), so they can never be part of
a deadlock: cancel's look again, after the application lock, for an attempt queued while it
waited; and queueing's lock of an earlier pending attempt it stops (below). If either row is
locked (being claimed), the request is refused with "try again". `tests/test_lock_order.py`
races these paths on separate connections. Before this order, a cancel racing either gate,
the rehearsal stop, an outcome, evidence recording or the sweeper deadlocked (each reproduced
by putting cancel back in the old order); a claim racing a cancel, checkpoints and the other
outcome writers follow the same order and are covered by it, the claim with a test.

### Race guarantees

- **How a gate checks:** it takes its locks (the attempt, the application, the approval, then
  what the prerequisite relies on), and only then reads, at READ COMMITTED. Every check sees
  what was committed before it ran. (The gates used to read a REPEATABLE READ snapshot taken
  at their first statement, before they waited for the application: an answer or profile
  change committed during that wait was not seen, and a change to the application's notes made
  the gate refuse. Both reproduced, then fixed.)
- **Committed before a gate's check:** a cancel, revocation, withdrawal, evidence deletion or an
  edit of the package's inputs (answers, consents, chosen documents, profile facts) stops that
  gate: it sees the change and refuses, and nothing it would have authorized happens.
- **Arriving while a gate holds its locks:** a cancel, revocation, withdrawal, evidence deletion,
  a change to the application's answers, consents or chosen documents, or a write to the
  approval waits for that gate (each takes a row the gate locks). A change to inputs the gate
  does not lock (profile facts, work authorizations, the document library, the answer bank,
  the job and its form, API authorizations) does not wait: committed after the gate read it,
  it does not stop that gate, and counts for later packages. What is sent is always the
  approved package, so such a change is never sent half-applied. After the gate:
  - After the **disclosure gate**, filling may start. A cancel still cancels the attempt, and the
    worker stops at its next fenced step, but what it had already entered or uploaded may have
    reached the employer. Nothing is undone.
  - After the **send gate**, the submission may be in flight. A cancel is refused; a revocation,
    withdrawal or deletion does not recall it. The outcome is recorded as observed; an uncertain
    one quarantines the application in `submitted_unconfirmed`, and nothing is retried.
- A withdrawal or evidence deletion after a submission was authorized counts for later
  submissions only. A database rollback can undo NoEfforts' own records, never a disclosure or
  a submission already sent.
- **Queueing again** while an earlier attempt is still pending under an approval no longer valid
  (queued, then edited before a worker took it) stops that attempt (`failed_safe`: it has
  disclosed nothing and could never run). If a worker is taking it at that moment, queueing is
  refused ("try again"); one that is running is never stopped this way.

Disclosure vs submission: gate 1 authorizes sending the approved data to the named
destination (filling can transmit via autosave, uploads always do). Gate 2 authorizes the
final submit. An approval to disclose only (a rehearsal, D41) passes gate 1 and never gate 2. A form that changes (new fields, new submit target) stops the attempt before
disclosing anything new.

Rehearsal prerequisite (E6, D45, `docs/rehearsal-prerequisite.md`): before the first submission
through an employer/provider path (user, adapter, origin, board), a valid recorded rehearsal
on that path is required, checked at approve, enqueue, claim and both gates. Every real
destination has the rule; fixtures only through a test-only setting. Real destinations are
still refused before it (manual handoff).

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

Evidence policy: receipt id, final origin, HTTP status (no page title or path); a readback
summary (how many fields were checked and how many did not keep their values; never which,
never values); disclosures (field, how the page acknowledged it as a fixed value, digest; for a
failed upload too, never the page's own attachment id); blocked egress destinations counted by
address category (loopback, link-local, private, named, public, other), never the hosts. No
screenshots, traces, cookies, storage state, codes or answer values. Evidence has
a retention date (`NOEFFORTS_EVIDENCE_RETENTION_DAYS`); a daily beat task purges expired
evidence, and users can delete an application's evidence (`DELETE
/api/applications/{id}/evidence`, refused while an attempt is active).

Browser isolation has two modes, both enforced outside the browser:

- **`container`** (used by Docker Compose; `docs/execution-service.md`): a separate
  browser-runner container with its own uid, Chromium's own sandbox on and self-checked at
  startup, seccomp, no capabilities, a read-only root, resource limits, internal networks only
  and a per-session egress proxy. It is Compose-tested in CI against the synthetic receiver
  only.
- **`netns`** (local development on Linux; `browser.py`, `sandbox/`), described below.

The `netns` mode:

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
without isolation (`NOEFFORTS_BROWSER_ISOLATION` must be `netns` or `container`; no user-facing switch); if the
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
uses the `container` mode instead. On macOS there
are no Linux namespaces; development there can run everything except execution, or execution
against fixtures with `NOEFFORTS_BROWSER_ISOLATION=off`, which only non-production accepts.

Limits of the `netns` mode:
- Hiding is a deny-list on a shared filesystem under the same OS user, not a minimal root
  filesystem: other files readable by that user stay readable.
- Chromium runs with Playwright's default `--no-sandbox` as uid 0 of a nested user namespace
  (full capabilities inside it, none outside); there is no seccomp profile or cgroup limit.
- The `container` mode addresses these; the live pilot gate requires it
  (`docs/live-pilot-gate.md` §7).

Adapters (`execution/adapters/`, chosen by `providers.routing.decide` and recorded on the
attempt with their version):

- browser: `fixture_ats` for the generic synthetic form, `greenhouse_hosted` for forms captured
  from a Greenhouse-style job post (`docs/greenhouse-adapter.md`), and `greenhouse_dom` for the
  second Greenhouse-style structure (controls with ids but no names, ARIA comboboxes);
- API: `fake_api`, the internal authorized-API contract, exercised only against a local fake.

All four run only against fixture origins; no real destination is enabled for any of them.
Capability flags are served at `GET /api/execution/capabilities`.

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
    `real_destinations_enabled` is false; since I2 it refuses `real_destinations_enabled`
    itself, and `registry.check_registry` the inconsistencies across providers;
  - no provider has live support.
- **Admission** (`providers/admission.py`, `GET /api/providers/admission`, D47): each
  provider's stage on one ladder, computed from code tables and recorded evidence; its support
  state never ranks above it; owner boundaries open a stage only with a record; capped at
  `rehearsal_ready`. Advisory: nothing routes, labels or approves on it
  (`docs/provider-admission.md`).
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
- Account export/deletion
- A real API provider (needs an agreement, secret storage, its own adapter and capability entry).
- Multi-page adapters with a disclosure boundary per step (Workday: see provider-architecture.md).
- A live discovery provider (Freehire is fixture-only; see `docs/discovery.md`).
- Optional Gmail OAuth and spend tracking (Phase D). Manual entry of an emailed verification
  code is built: a checkpoint the user answers (`providers/checkpoints.py`).

## Deployment, backup and recovery (current guidance)

- Single host: `docker compose up`. Put a TLS reverse proxy in front and set
  `NOEFFORTS_COOKIE_SECURE=true`.
- Back up Postgres with `pg_dump` and the storage volume together; documents reference storage
  keys, so restore both from the same point in time.
- Migrations: `alembic upgrade head` runs on backend start. Review any destructive migration
  before deploying.
