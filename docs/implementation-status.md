# Implementation status

Last updated: 2026-10-21 (privacy and audit hardening, legacy audit repair, baseline corrections and a documentation-consistency pass; nothing supported for real use; no external request, credential, permission or live-status change). For requirement-by-requirement evidence see
`docs/evidence-matrix.md`. Labels: **complete**, **partial**, **blocked**, **not started**,
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

| `ec9b9b7` | Research notes: environment-specific Tsenta access, Gmail classification unconfirmed |
| `c79a6d4`, `d5d8baf` | Approval hardening (manifest v2, expiry, row locks, draft deps) + migration tests |
| `05e45a1` | Synthetic ATS receiver (test oracle) |
| `8fdeef0` | Durable execution (attempts, outbox, leases, fencing, gates, adapter, checkpoints) |
| `ebb3e3b` | Failure-injection, race, egress, leak, tenancy and real Celery tests + redirect egress fix |
| `64a560a` | Submission card in the review UI; CI workflow |
| `289e0b0` | Formatting fix caught by CI |

| `c6fa7ce` | Readback tampering, disclosure counting, real lease expiry, every mutation path |
| `ffe00f7` | Real broker outage and real Redis redelivery |
| `b4c3023` | Browser in its own network namespace behind an egress proxy |
| `f5bd82f` | Evidence retention purge and deletion; secret scan of real worker logs |
| `7ce41ff` | Reproduced likely cause of CI run #2 (navigation race in the Phase A test) + regression spec |
| `e11484d` | Docker Compose smoke test in CI |
| `d87ef12` | Application state frozen while a worker holds an attempt (B1) |
| `e066c1a` | No re-send on browser close (B2); PID/mount namespaces hide orchestrator files and processes |
| `7da9a29`, `292ecb9` | Submission UI browser tests; card polling fix (B3); e2e worker supervisor (B4) |
| `2d3d3c1`, `6c850d7`, `416cf70`, `bae5120` | CI: redis-server, submission e2e, compose logs; Docker web config (B6); smoke script |

Phase A/B tests below were run against `29a1960`. Phase C results are in the next sections.

## Privacy and audit hardening, baseline corrections (2026-10-21; local only, no external request)

- **Nothing changed outside the repository:** no external request, credential, permission,
  provider configuration or live-support change. Routing order and support states are
  unchanged; one unevidenced fixture claim was removed (below).
- **Commits on `main`:**
  - `6b534f6` – audit events and logs carry safe metadata only:
    - `audit.record` sanitizes every event's metadata (sensitive keys redacted, non-identifier
      values omitted, external identifiers stored as references);
    - every route decision carries a fixed reason code and an API grant state, is returned by
      `GET /api/jobs/{id}/route`, shown on the job page and recorded as `route.decision`;
    - checkpoint route messages no longer repeat the form's own labels;
    - draft rejections record a reason code, not their text;
    - the browser runner logs unexpected errors by type only, and the egress proxy logs
      destination counts, never hosts;
    - Alembic's logging setup no longer disables the app's loggers (log assertions in tests
      had observed nothing).
  - `24d8bb9` – migration `c303eee5a3c9`, a one-way repair of audit metadata stored before
    sanitizing existed (irreversible; a second run changes nothing; counts-only output). Also:
    `draft.created` stored a raw question key and now stores a reference; `content_hash` was
    over-redacted and is kept again.
  - `991ed1d` – baseline corrections from the Phase 0 review:
    - `fixture_ats` no longer claims a CAPTCHA checkpoint or trait (its receiver has no
      CAPTCHA mode and its adapter detects none);
    - `greenhouse_dom`'s CAPTCHA checkpoint gained an execution test (labelled static
      `gh2_captcha` fixture mode);
    - cancelling reports only NoEfforts' own refusal, never another error's text;
    - a cross-tenant test for `GET /api/jobs/{id}/route`.
  - The documentation-consistency pass that adds this entry: `docs/audit-events.md` (every
    audit event and its allowed metadata, logs, retention and disposal), with
    `tests/test_audit_inventory.py` and `tests/test_doc_references.py` keeping the documents
    in line with the code.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `6b534f6`: `tests/test_audit_privacy.py` 26 passed; full backend 511 passed; Playwright
    30 passed; frontend typecheck and lint clean;
  - `24d8bb9`: audit repair, privacy and migration tests 38 passed; full backend 520 passed;
  - `991ed1d`: affected modules 95 passed; full backend 524 passed;
  - mutation checks: bypassing the sanitizer, logging the runner's full exception and
    catching every exception on cancel were each caught.
- **CI:**
  - **CI #75** ([39667481752](https://github.com/KevinD003/AutoApply/actions/runs/39667481752))
    (`f16ce8f`, status document): passed;
  - **CI #76** ([39676548834](https://github.com/KevinD003/AutoApply/actions/runs/39676548834))
    (`6b534f6`): passed;
  - **CI #77** ([39681835330](https://github.com/KevinD003/AutoApply/actions/runs/39681835330))
    (`24d8bb9`): passed;
  - **CI #78** ([39687972651](https://github.com/KevinD003/AutoApply/actions/runs/39687972651))
    (`991ed1d`): passed;
  - **CI #79** ([39691935177](https://github.com/KevinD003/AutoApply/actions/runs/39691935177))
    (`c54596e`, Phase 1 documentation consistency): passed;
  - **CI #80** ([39695296112](https://github.com/KevinD003/AutoApply/actions/runs/39695296112))
    (`3d99467`, keyed audit references): failed in the backend job only (536 passed,
    1 skipped, 1 failed); frontend, Docker smoke and Compose execution passed. The failing
    test, `test_a_rejected_draft_records_a_reason_code_not_its_content`, checked that the
    bare string "40" (a number from the rejected draft) was absent from the whole row, whose
    random UUID and reference digits contain such pairs by chance (about one run in five; it
    is also the earlier unexplained local failure of this test). Fixed in the following
    commit: whole-number tokens are checked in the metadata only, next to the existing
    exact-metadata assertion; the check still catches a leaked number. 25 repeated runs
    passed. **CI #81** ([39698542143](https://github.com/KevinD003/AutoApply/actions/runs/39698542143))
    (`3cc68fd`, that fix): passed;
  - **CI #82** ([39704738837](https://github.com/KevinD003/AutoApply/actions/runs/39704738837))
    (`f5bb30f`, Phase 11A error boundaries): passed;
  - **CI #83** ([39719684839](https://github.com/KevinD003/AutoApply/actions/runs/39719684839))
    (`051b200`, Phase 11B access logs): passed.

  Per-job test counts were not recorded for these runs.
- **Keyed audit references (separate security commit after `c54596e`):**
  - references are `ref:v2:` + HMAC-SHA-256 (truncated to 32 hex characters) over a domain
    label, the user's id and the identifier, keyed by the server-held
    `NOEFFORTS_AUDIT_REF_KEY`. The same user and identifier give the same reference; another
    user or another key gives an unrelated one;
  - the key is mandatory: the API refuses to start without one of at least 32 characters, and
    production refuses a `test-only` key. No key is committed; tests use a test-only key from
    their own configuration, and the Compose test scripts generate a throwaway one;
  - migration `7a1e4c2b9d30` (repair version 2, irreversible, idempotent, counts-only output)
    replaces every legacy unkeyed reference with `[omitted]`, since its source identifier is
    no longer stored; a raw `field` value still present becomes a keyed reference;
  - new `tests/test_audit_refs.py` (10 tests); mutation checks: removing the user scope from
    the HMAC input and keeping legacy references were each caught.
- **API and error boundaries (Phase 11A, commit after `3cc68fd`):**
  - isolation failures carry a fixed code (`runner_refused`, `runner_unreachable`,
    `proxy_refused`, `proxy_unreachable`, `namespaces_unavailable`, …); attempt outcomes and
    logs show only that code, never the runner's address, its response body or command
    output;
  - form-capture mismatches return a generic "unsupported or incomplete" message with a
    code (`form_sources_disagree`, `controls_do_not_match`, `no_submittable_form`);
    form-drift, upload and readback outcomes give counts and NoEfforts' own fixed reasons
    (for example "required by the page, no approved answer"), never field keys;
  - a global boundary turns any unexpected API error into a generic 500, logged as type,
    method and route template only;
  - new `tests/test_error_boundary.py` (10 tests); 11 existing tests that expected field keys
    (or runner versions) in messages now assert they are absent, and 3 more follow the new
    wording. Sabotage checks: removing the boundary and storing the raw isolation error were
    each caught.
- **Access logs (Phase 11B, commit after `f5bb30f`):**
  - the API writes one access line per request with the method, the route template (or
    `unmatched_route`) and the status, and drops uvicorn's own raw-path line, whatever command
    starts the server; no client address, query string or body;
  - the Next.js development request log is off, and the `/api` proxy's failure line no longer
    carries the URL (checked by running `next dev` and `next start` locally against an
    unreachable backend: no marker in either log);
  - new `tests/test_access_log.py` (3 tests, one starting a real uvicorn) and
    `e2e/log-privacy.spec.ts`; removing the filter was caught.
- **Retained errors, evidence and library logs (Phase A5-A7, commit after `051b200`):**
  - a failed outbox publish stores the exception's type only;
  - the database engine hides bound parameters in error text;
  - a filter reduces Celery's own logging of a failed task to the exception's type, with no
    message or traceback (checked with a real eager Celery task whose error quotes a row);
  - Compose's PostgreSQL logs errors without DETAIL (`log_error_verbosity=terse`; checked on
    the local server: the DETAIL line quoting a key value is gone);
  - receipts no longer keep the confirmation page's title or path; readback evidence keeps
    counts, not field keys; egress evidence counts blocked destinations by address category,
    not hosts;
  - new `tests/test_retained_data_privacy.py` (20 tests); five existing tests and one Compose
    check now assert the counts and categories. Sabotage checks: hosts kept in egress evidence, the Celery filter
    removed and parameters not hidden were each caught.
- **Known, not fixed here:** four API paths still carry a posting's question key (answers,
  consents, drafts), which a proxy in front of the app could log. The CI test database logs
  errors with DETAIL (synthetic data only). An error raised inside a migration is printed with
  its DETAIL by the Alembic command line.

## Execution routing and capabilities (2026-10-21; local only, no external request)

- **Routing rule:** every application receives exactly one route, in this order:
  1. an authorized API connector;
  2. a supported browser adapter;
  3. a stop for the user: a checkpoint or a manual handoff.

  The ATS is identified from the job URL before any adapter is selected, and the route is
  computed per job. The routing order is implemented, tested and documented.
- **Fails closed:** unsupported or uncertain flows become a checkpoint or a manual handoff.
  CAPTCHA, emailed-code verification and every other user-action requirement stay
  user-controlled.
- **Nothing changed outside the repository:** no external request, credential change,
  permission change or live activation occurred.
- **This milestone does not request or grant submission approval.** No real destination is
  supported for live use. NoEfforts cannot submit applications to real employers.
- **Commits on `main`:**
  - `6fc61df` – implementation:
    - a nine-operation provider interface, and the agreed capability names as views over the
      existing evidence levels;
    - workflow traits (login, manual verification, CAPTCHA possible, multi-step) recorded
      separately from capabilities;
    - Workday registered as planned only;
    - routing that identifies the ATS from the job URL first, then selects a per-job route;
    - `GET /api/jobs/{id}/route`;
    - a "How NoEfforts could apply" card on the job page.

    This commit initially had two over-long lines because a pipe hid Ruff's exit code, so
    CI #69 failed at lint.
  - `93200b4` – fixed the lint issue; CI #70 passed.
  - `1eae3d5` – documentation:
    - `docs/provider-architecture.md` §2b and §6–§9: the provider interface and evidence
      matrix, the routing order and provider roles, the Freehire plan, the Workday
      specification, the Greenhouse status, and the safety rules with their tests;
    - the roles table in `docs/architecture.md`;
    - decision D35;
    - evidence-matrix rows.
  - `7fead79` – status document.
- **Code changed:**
  - `providers/model.py`, `providers/registry.py`, `providers/routing.py`;
  - `discovery/service.py`, `jobs/router.py`;
  - the job page;
  - new `tests/test_execution_routing.py` and `e2e/routing.spec.ts`.
- **Tests run locally:**
  - new routing tests: 11 passed;
  - full backend suite: 485 passed;
  - Playwright: 30 passed;
  - frontend typecheck and lint: clean.
- **The routing tests cover:**
  - API versus browser versus manual routing;
  - unsupported controls triggering a checkpoint before anything is sent;
  - an adapter-version mismatch blocking queueing and execution;
  - API connectors never selected without explicit authorization;
  - Freehire imports never becoming form schemas;
  - Workday jobs unsupported and never sent to the Greenhouse adapter;
  - CAPTCHA producing `needs_user_action`, never automated solving.
- **Mutation checks:**
  - removing ATS-identity verification was caught;
  - removing the unsupported-control checkpoint was caught.
- **CI:**
  - CI #69 failed only at lint: two over-long lines slipped through after a pipe hid Ruff's
    exit code;
  - CI #70 passed after `93200b4`;
  - CI #71 ([39656190937](https://github.com/KevinD003/AutoApply/actions/runs/39656190937))
    passed:
    - backend 484 passed, 1 skipped (the normal CI-only skip);
    - Playwright 30 passed;
    - Compose and Docker smoke jobs passed;
  - **CI #73** ([39663628144](https://github.com/KevinD003/AutoApply/actions/runs/39663628144))
    (`81d9965`, status-document update): passed. Per-job test counts were not recorded;
  - **CI #74** ([39664127329](https://github.com/KevinD003/AutoApply/actions/runs/39664127329))
    (`fa019a3`, manual dropdown checklist questions 7 and 8): passed. Per-job test counts were
    not recorded.
- **Manual dropdown check (Path A):** chosen by the owner; pending the owner's own
  observations with `docs/manual-dropdown-checklist.md`. No activity on the approved posting is
  authorized in the meantime. Path B remains unapproved.

**Evidence and capability matrix.** `fixture` = local fixture only; `observed` = seen
read-only on one real page; `none` = not implemented. No capability cell is live.

| Capability | fixture_ats | greenhouse_dom | fake_api | greenhouse_readonly | freehire | workday | manual |
|---|---|---|---|---|---|---|---|
| public_schema_read | fixture | observed | fixture | observed | none | none | none |
| API_submission | none | none | fixture | none | none | none | none |
| browser_inspection | fixture | observed | none | observed | none | none | none |
| browser_fill / document_upload | fixture | fixture | none / fixture | none | none | none | none |
| custom_dropdown / location_picker | none | fixture / none | none | observed (structure only) / none | none | none | none |
| confirmation_detection | fixture | fixture | fixture | none | none | none | none |
| login / verification / CAPTCHA / multi-step traits | no / yes / no / no | no / unknown / unknown / no | no / no / no / no | no / n/a / unknown / no | n/a | expected ×4 | n/a |

**Support states.** Fixture behaviour and read-only observations are not live operational
support.

- **Supported for real use:** nothing.
- **Fixture-only:**
  - `fixture_ats`;
  - `greenhouse_hosted` and `greenhouse_dom`, including the fixture-only dropdown strategies;
  - the fake authorized API;
  - Freehire discovery;
  - the CAPTCHA and emailed-code checkpoints.
- **Read-only observed:** Greenhouse structure on one posting.
  - 19 fields map consistently.
  - The attachments map through their groups.
  - The dropdowns exist but have never been observed opening.
- **Planned:** Workday, a specification only. No automation.
- **Unsupported:**
  - location pickers and page-managed coordinates;
  - SMS codes;
  - login-gated and multi-page forms;
  - CAPTCHA solving;
  - every real destination.

**Remaining blockers before one approved Greenhouse pilot:**

1. For every required dropdown, evidence that it opens via one bounded strategy with a
   complete option list, following either approved path A or path B.
2. The required controls `u1` and `u2` understood and mapped. Otherwise that posting must
   remain refused.
3. A location answer set without writing the page-managed hidden coordinate fields.
4. Real upload evidence: attachments uploaded to a real form, proven on their own.
5. Real submission evidence: a real final submit and its confirmation, proven separately from
   uploads.
6. `docs/live-pilot-gate.md` met, including separate permissions for disclosure (C,
   permission 3 there) and submission (D, permission 4), plus a reviewed change that raises
   the relevant capability evidence.

## Freehire personal prototype (2026-10-21; no Freehire API request)

- **Product model:** personal prototype only (owner's choice, D34). Multi-user use, plan
  storage and 30-day deletion are **not implemented**; they wait on a plan or written
  clarification from Freehire.
- **Documentation review:** `468742e` (research note, D34). Public pages only; no `/api/v1`
  request.
- **Corrections in code** (`7465f64`):
  - `work_mode` is read from the top-level field; `last_seen_at` is no longer read;
  - the fixed 1-second spacing and its setting are removed. Paging stops when
    `X-RateLimit-Remaining` is 0 (truncated, with the reason shown). A 429 reports
    `Retry-After` and is never retried. Nothing sleeps;
  - the healthcheck makes no request: `/status` is crawler health;
  - "via freehire.me" appears on every listing and on the job page. No listing-page URL is
    documented, so it is text, not a link;
  - no raw payload is kept (tested);
  - the fixture follows the documented shapes: closed postings are absent from search and
    served by the detail endpoint, and every response carries rate-limit headers.
- **Docs** (`f487626`):
  - D7 no longer calls 600/min documented;
  - `docs/discovery.md` follows the reviewed documentation;
  - D34 lists the applied items;
  - new evidence rows.
- **Unchanged:**
  - off by default (`NOEFFORTS_DISCOVERY_PROVIDERS=[]`), fixture origins only;
  - no account, no key, no live request;
  - a future live test needs its own approval naming the query, page limit, time window and
    data-retention statement.
- **Commands actually run (cloud sandbox):**
  - `ruff format .`, `ruff check .`: clean;
  - `tests/test_freehire_discovery.py`: 36 passed (it had 27);
  - with `test_discovery.py`, `test_providers.py` and `test_jobs.py`: 74 passed;
  - three mutations, each failing its test and then reverted:
    - falling back to `enrichment.work_mode`;
    - ignoring `X-RateLimit-Remaining`;
    - a healthcheck calling `/status`;
  - full backend suite: 474 passed, exit 0. A first attempt had collected with a global
    pytest outside the backend virtualenv and stopped at collection with no test run; it was
    re-run with `backend/.venv/bin/python -m pytest tests`;
  - frontend: `npx tsc --noEmit` and `npm run lint` clean;
  - `e2e/discovery.spec.ts`: 2 passed;
  - full Playwright suite: 28 passed.
- **CI:**
  - CI #66 on `7465f64`: success;
  - CI #67 ([39647705737](https://github.com/KevinD003/AutoApply/actions/runs/39647705737))
    on `f487626`: all four jobs passed. Backend 473 passed, 1 skipped (the same CI-only skip);
    frontend Playwright 28 passed; execution-compose and docker-smoke passed.

## Greenhouse readiness gap and Freehire discovery (2026-10-21; no external request)

- **Greenhouse (docs only):** `docs/greenhouse-readiness-gap.md` separates five things:
  - what is confirmed on the one real posting;
  - what is confirmed only on fixtures;
  - assumed fixture behaviour;
  - unknown or unsupported behaviour;
  - what a live filling pilot would need.

  It holds the support matrix. Status: "Greenhouse fixture support exists; one real posting
  has been structurally observed, but real filling and submission remain disabled." No
  identical dropdown observation will be requested again.
- **Freehire discovery: implemented locally.** External API not configured and not tested;
  not production-ready. Details in `docs/discovery.md`.
  - **Contract:** taken from the existing review of Freehire's documented API
    (`docs/research/freehire.md`, 2026-10-19). Not re-fetched; no Freehire request in this
    task.
  - **Code:**
    - the interface: `provider_capabilities`, `healthcheck`, `list_jobs(filters, cursor)`,
      `get_job`, `normalize_job`;
    - the `freehire` client, which only accepts fixture base URLs;
    - the local stand-in `fixtures/ats_receiver/freehire_fixture.py`;
    - import, filters, dedup and the merge policy;
    - `/api/discovery/*`;
    - the Discover page and source attribution on jobs;
    - migration `955a3214d25a`;
    - D33.
  - **Off by default:** `NOEFFORTS_DISCOVERY_PROVIDERS=[]`. The key, if ever set, stays
    server-side.
- **Commits:**
  - `b1d2f5b`: Greenhouse handoff;
  - `eecc2ed`: backend;
  - `db7d4d8`: frontend;
  - `6c88490`: docs.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7, Node 22):**
  - `ruff format .`, `ruff check .`: clean;
  - migration on a scratch DB: `alembic upgrade head` (with an existing row),
    `alembic check` ("No new upgrade operations detected"), `downgrade -1`, `upgrade head`;
  - `tests/test_freehire_discovery.py`: 27 passed;
  - with `test_discovery.py`, `test_providers.py`, `test_jobs.py`, `test_migrations.py` and
    `test_api_provider.py`: 83 passed;
  - two mutations, each failing its test and then reverted:
    - unknown sponsorship treated as a match;
    - discovery merging into an existing job;
  - full backend suite: 465 passed, exit 0;
  - frontend: `npx tsc --noEmit` and `npm run lint` clean;
  - `e2e/discovery.spec.ts`: 2 passed (desktop, mobile), after two locator fixes in the spec
    itself;
  - full Playwright suite: 28 passed;
  - not run here: the Compose scenarios (no Docker daemon).
- **CI #63** ([39641708598](https://github.com/KevinD003/AutoApply/actions/runs/39641708598))
  on `6c88490`, all four jobs passed:
  - backend 464 passed, 1 skipped (the same CI-only skip as before);
  - frontend: typecheck, lint, Playwright 28 passed;
  - execution-compose passed;
  - docker-smoke passed.
- **Limitations:**
  - the Freehire contract may have changed since 2026-10-19;
  - the `enrichment` keys and the single-job wrapper are assumptions;
  - imports run inside the request (bounded);
  - Freehire listings are never treated as complete, so "missing from the listing" does not
    mark them stale.

## Submission-provider architecture (2026-10-21; local only, no external request)

- **No external service was contacted:** no Greenhouse, Workday, Freehire, Gmail or Tsenta
  request, and no real candidate data, upload or submission.
  - Run #9 stays evidence only.
  - C and D stay unapproved.
  - `real_destinations_enabled` is false for every provider.
- **Built:**
  - Provider model and registry (`app/modules/providers/`):
    - kinds and operations;
    - 15 capability flags plus `real_destinations_enabled`, each at an evidence level
      (`fixture` / `observed` / `live_fill` / `live_submit`);
    - invariants checked on import;
    - served at `GET /api/providers`.
  - Routing (`routing.decide`): real → manual handoff; authorized API; browser; manual. The
    provider and its version are part of the approval binding, so a route change retires the
    approval.
  - User-scoped API authorizations (`/api/api-authorizations`, fixture origins only).
  - The API route (`adapters/fake_api.py`, `runner._run_api`, `runner.reconcile_api`) and the
    local fake API on the receiver (`fixtures/ats_receiver/fake_api.py`, own ledger). It is an
    internal contract; no real ATS is claimed to offer it.
  - Checkpoint policy (`providers/checkpoints.py`): nothing automated; only an emailed code
    typed by the user can resume. No solver, no bypass, no mailbox integration.
  - Discovery (`app/modules/discovery/`, table `discovered_jobs`):
    - the Freehire mock reads `fixtures/discovery/freehire_mock.json`, a shape invented by
      NoEfforts;
    - normalization, tri-state source facts, dedup through `upsert_job`, stale marking;
    - the application route is a manual handoff until a form is captured.
    - Status: "Potential future discovery provider; not yet connected or validated."
  - Migration `8b41c0d7e2f5`: `api_authorizations`, `discovered_jobs`, and the `discovery` job
    source.
  - Docs: `docs/provider-architecture.md` (capability matrix, routing, API contract, browser
    lifecycle and disclosure boundaries, checkpoints, Freehire, Workday sequence, Greenhouse
    status), the architecture section, D32, and evidence-matrix rows.
- **Greenhouse status (unchanged; no request made):**
  - 19 of 19 mapped fields have a consistent required state;
  - dropdowns unresolved (no opening evidence within run #9's window);
  - the location controls and the unmatched required controls (`u1`, `u2`) are blockers;
  - `greenhouse_dom` refuses that posting for live use;
  - fixture success is not real-site compatibility.
- **Workday:** documentation and fixture strategy only (`provider-architecture.md` §7).
  Nothing is built.
- **Package content shape unchanged:** `SCHEMA_VERSION` stays 2. The binding gains the
  `fake_api` provider (`fake-api-1`). Browser approvals are unaffected unless the user grants
  an API authorization.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `ruff format .`, then `ruff check .` and `ruff format --check .`: clean;
  - migration on a scratch DB: `alembic upgrade head`, `alembic check` ("No new upgrade
    operations detected"), `downgrade -1`, `upgrade head`;
  - focused suites, 134 passed:
    - `test_providers.py` 18, `test_api_provider.py` 15, `test_discovery.py` 6 (new);
    - `test_approval_binding.py` 9, `test_greenhouse_dom.py` 30, `test_greenhouse_adapter.py`
      24, `test_dropdown_strategies.py` 18, `test_required_signals.py` 14;
  - full backend suite: 438 passed, exit 0 (399 before this task, plus the 39 new tests);
  - frontend unchanged, so no frontend checks were run here;
  - not run here: the Compose scenarios (no Docker daemon); CI runs them.
- **CI #58** ([39635232058](https://github.com/KevinD003/AutoApply/actions/runs/39635232058))
  on `4c3ec01`, all four jobs passed:
  - backend: 437 passed, 1 skipped (the same CI-only skip as CI #56);
  - frontend: typecheck, lint and the full Playwright suite passed;
  - execution-compose passed;
  - docker-smoke passed.

## Local readiness for dropdown support (2026-10-21; local only, no external request)

- **Run #9 closed.**
  - Run [39612152070](https://github.com/KevinD003/AutoApply/actions/runs/39612152070) on
    `e1bd9e7` (pinned branch, CI #52). Workflow success; observation `completed`, 0 internal
    errors.
  - A 3×200; 1 navigation, 26 GET, 0 non-GET; 24 actions on 12 dropdowns.
  - `not_opened` means no opening evidence within the 600 ms window for a click on the
    control. It does not mean the widgets cannot open.
  - Required evidence is consistent for all 19 mapped fields; the resume is required by its
    group.
  - Refused data requests: `GET /locales/*/*.json` only (evidence, not permission).
- **Remaining unknowns on the real page:**
  - how the dropdowns open, if they do;
  - their options;
  - what `u1`–`u5` ask (`u1` and `u2` are required);
  - the missing location control and the page-managed coordinates;
  - whether the widgets depend on the refused locale files.
- **Built:**
  - fixture dropdown behaviours `gh2_dd` / `gh2_dd_extras` (`_DD_JS`, each a labelled
    assumption);
  - the strategy engine `adapters/dropdowns.py` (click, ArrowDown, single trigger;
    post-action evidence; exact selection; readback);
  - adapter `greenhouse_dom` version 3;
  - decision D31;
  - the optional manual checklist `docs/manual-dropdown-checklist.md`;
  - decision point A/B in the proposal doc (neither authorized).
- **Unchanged:** `real_destinations` false for filling and submission. Location picker and
  coordinates unsupported. C and D unapproved.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - ruff check and format: clean;
  - `tests/test_dropdown_strategies.py`: 18 passed;
  - `tests/test_required_signals.py`: 14 passed;
  - the run-#9 signature test in `tests/test_widget_detector.py`: passed;
  - mutation: selecting the first option fails 2 strategy tests; ignoring network activity
    during opening fails the network test;
  - full backend suite: 399 passed.
  - Not run here: the Compose scenarios (no Docker daemon); CI runs them.
- **CI #56** ([39621845104](https://github.com/KevinD003/AutoApply/actions/runs/39621845104))
  on `b38631e`, all four jobs passed:
  - backend 398 passed, 1 skipped, including `test_dropdown_strategies.py` (18),
    `test_required_signals.py` (14) and `test_widget_detector.py` (26);
  - frontend: full Playwright passed;
  - execution-compose passed;
  - docker-smoke passed.

## Diagnostic re-observation, run #9 (2026-10-21)

- **Revision and result:** run #9 on `e1bd9e7` (pinned branch; CI #52 passed). The workflow
  succeeded; the observation outcome is `completed`, with 0 internal errors.
- **Requests and actions:** A 3×200; 1 navigation, 26 GET requests; 24 actions on 12
  dropdowns.
- **Findings:**
  - all 12 dropdowns `not_opened` within the 600 ms window: the click completed and focus
    reached the control, but there was 0 DOM change;
  - the 11 refused data requests are all `GET /locales/*/*.json`;
  - required evidence is consistent for all 19 mapped fields, and the resume is required by
    its group.
- **External activity:** stopped. No unchanged rerun is proposed.

## Detector diagnosis after run #8 (2026-10-21; local only, no external request)

- **Run-#8 detector limits** (details in the compatibility report):
  - the expanded state was not compared;
  - only the input's own `aria-controls`/`aria-owns`, or a sole visible `role=listbox`;
  - `role=listbox` and `role=option` were assumed;
  - one snapshot at 600 ms;
  - `opened: false` covered 5 different situations, shown against an independent widget
    model.
- **Built:**
  - structural per-action diagnostics and an `open_state` classification, with the same
    actions and window;
  - path shapes for refused data requests;
  - an explicit `control_gone` case;
  - required signals recorded separately for every control;
  - adapter `greenhouse_dom` version 2: a page-required field with no approved answer
    blocks; an unmarked field required by the job data keeps its requirement and runs.
  - Decision D30.
- **Tests:**
  - `tests/test_widget_detector.py`: 11 variants of the independent model, classification
    rules, path shapes;
  - `tests/test_required_signals.py`: mutation-checked against the old rule;
  - updated `tests/test_widget_inspection.py` and `tests/test_readonly_cli_process.py`.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - ruff check and format: clean;
  - focused (`test_widget_detector`, `test_required_signals`, `test_widget_inspection`,
    `test_readonly_cli_process`, `test_gh_readonly`, `test_b3_policy`, `test_greenhouse_dom`,
    `test_approval_binding`): 139 passed, 2 failed. The 2 were fixed: a test expecting the
    old summary keys, and a crash when a refused navigation removed the control, now
    `control_gone`. After the fixes, `test_widget_inspection.py`: 20 passed;
  - full backend suite: 376 passed;
  - run #8's detector (`181b7c3`) against the variants, in a scratch copy: `opened: false`
    for `portal_unlinked`, `no_roles`, `class_hint`, `silent` and `wrong_target`;
  - mutation: the old required rule fails 3 of the 4 execution tests.
  - Not run here: the Compose scenarios (no Docker daemon); CI runs them.
- **CI #52** ([39602660714](https://github.com/KevinD003/AutoApply/actions/runs/39602660714))
  on `e1bd9e7`, all four jobs passed:
  - backend 375 passed, 1 skipped, including `test_widget_detector.py` (25) and
    `test_required_signals.py` (10);
  - frontend: full Playwright passed;
  - execution-compose 89 checks, 0 failed;
  - docker-smoke passed.
- **Not done:** no external request. A diagnostic re-observation is proposed in the
  proposal doc and is not authorized.

## Replacement widget inspection, run #8 (2026-10-21)

- **Revision and result:** run #8 on `181b7c3` (pinned branch; CI #49 passed). The workflow
  succeeded; the printed outcome is `completed`, with 0 internal errors.
- **Requests and actions:** A 3×200; 1 navigation, 26 GET requests; 24 actions on 12
  dropdowns.
- **Findings:**
  - no option list was observable for any dropdown;
  - 7 CDN data requests were refused during the openings;
  - nothing was selected or changed;
  - required is represented by `aria-required` plus a label marker;
  - attachments are unique through the group rule but still lack a required signal.
  Details: `docs/greenhouse-compatibility-report.md`.
- **Not done:** no further external request. C and D remain unapproved.

## Before the replacement run (2026-10-21): fresh-process regression, explicit outcome

- **Fresh-process regression** (`tests/test_readonly_cli_process.py`, 3 tests): runs the
  workflow's exact entry point, `python -m app.modules.preparation.gh_readonly --out DIR
  --inspect-widgets`, against the synthetic receiver through the netns browser. The
  test-only target `NOEFFORTS_READONLY_FIXTURE_BASE` is accepted only for listed fixture
  origins outside production. It shows:
  - the navigation passes the filter (one page GET) and the inspection completes (exit 0);
  - an injected filter failure ends the run within seconds (exit 6), and the page is never
    requested;
  - no browser work directory or process is left;
  - stdout is the guarded summary only, and stderr is empty: no traceback, no marker
    values.
  - Mutation-checked: an entry point placed as in run #7, and a filter that is not fail-closed,
    both make it fail.
- **Explicit outcome:**
  - `completed` (exit 0);
  - `policy_stop` (exit 7; partial evidence, not compatibility);
  - `internal_error` (exit 6): any unexpected error, a failed handler, or a filter failure,
    even when a summary was printed;
  - an incomplete inspection is never `completed`;
  - script-mode stderr goes to a raw file in the out directory.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - ruff check and format: clean;
  - full backend suite: 339 passed, 2 failed. The 2 were in-process CLI tests whose stub
    `fetch` lacked the new `base` argument. After fixing the stub:
    `pytest tests/test_gh_readonly.py tests/test_widget_inspection.py
    tests/test_readonly_cli_process.py tests/test_b3_policy.py`: 67 passed.
  - **CI #49** ([39543318002](https://github.com/KevinD003/AutoApply/actions/runs/39543318002))
    on `181b7c3`, all four jobs passed:
    - backend 340 passed, 1 skipped;
    - Playwright full suite passed;
    - execution-compose 89/0;
    - docker-smoke passed.
    The replacement run uses this revision, from the pinned branch
    `readonly-inspect-181b7c3`.

## Widget inspection run #7 (2026-10-21): authorized once, failed before any widget action

- **Run:** manual run #7 (39535843106) on `2b0bcbb` (`1fc58b2` + docs; CI #45 and #46 passed).
  - A: 3×200.
  - The page navigation was held by a failing request filter and timed out (60 s).
  - 0 widget actions; no page evidence.
  - Authorization used; not rerun.
  Details: `docs/greenhouse-compatibility-report.md`.
- **Cause:** the script entry point stood before code that `main()` needs, so in
  `python -m` mode `DATA_REQUEST_TYPES` was undefined. The tests import the module, which
  hides this.
- **Fix (local):**
  - the entry point is last (test-enforced);
  - the request filter fails closed;
  - two regression tests, mutation-checked against `1fc58b2`.
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `uv run ruff check .` and `uv run ruff format --check .`: clean;
  - `pytest tests/test_widget_inspection.py`: 20 passed;
  - the two new tests against the run-#7 module (`1fc58b2`): both failed, as intended;
  - `uv run pytest` (full backend): 338 passed.
- **CI #47** ([39538552333](https://github.com/KevinD003/AutoApply/actions/runs/39538552333))
  on `5f47409`: all four jobs passed (backend, frontend including full Playwright,
  execution-compose, docker-smoke).
- **External activity:** stopped. Another run needs a new authorization.

## Widget inspection mode, local only (2026-10-20; not approved for a real page, not run)

- **B3 closed:** the evidence record is in `docs/greenhouse-compatibility-report.md`, "B3
  evidence record".
  - Final tested revision: `ee35b49`, CI #43, all jobs passed.
  - The attachment rule has not been validated by any later real run.
- **Existing evidence analysed without new requests** (same report, "Dropdowns: what the
  retained evidence shows"):
  - 7 mapped dropdown questions, 1 combobox in the phone group, 4 standalone unmatched;
  - the recorded required signal merges HTML and ARIA;
  - group and label-marker signals were not recorded.
- **Built** (`gh_readonly.inspect_comboboxes`, `--inspect-widgets`, workflow input
  `inspect_widgets`, decision D29):
  - opens and closes each combobox present at load (click, Escape), at most 24 actions;
  - every data request type is refused at every origin, GET included;
  - submissions are cancelled in the page, non-GET is blocked, file choosers are intercepted,
    dialogs are dismissed;
  - it stops at a navigation, address change, challenge, submission, non-GET, file chooser,
    dialog, value change or selection, or when the action, time (30 s) or request budget runs
    out;
  - a covered widget is not clicked;
  - anonymous output only: aliases `q01…` and `u1…`, counts and flags.
  - A real page is accepted only under the fixed B3 policy.
- **Fixture:** `gh2_widgets`. Widget behaviour is a FIXTURE ASSUMPTION; variants are selected
  with `widget_bad`.
- **Tests:**
  - `tests/test_widget_inspection.py`, 18 tests through the netns browser path;
  - Compose `s_readonly_widget_inspection_in_container` (container path; it runs only in CI
    here, because this sandbox has no Docker daemon).
- **Not done:** no external request of any kind. The approval request is in
  `docs/greenhouse-readonly-compatibility-proposal.md`, "Widget inspection".
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `uv run ruff check .` and `uv run ruff format --check .`: clean;
  - focused: `pytest tests/test_widget_inspection.py tests/test_b3_policy.py
    tests/test_gh_readonly.py tests/test_greenhouse_dom.py tests/test_approval_binding.py`:
    104 passed;
  - `uv run pytest` (full backend): 336 passed.
  - An earlier full run was stopped and is not counted: it had started before the last code
    change.
  - Not run here: the Compose scenarios (no Docker daemon in this sandbox) and Playwright
    (frontend unchanged). CI runs both.
- **CI #45** ([39506321962](https://github.com/KevinD003/AutoApply/actions/runs/39506321962))
  on `1fc58b2`, all four jobs passed:
  - backend 335 passed, 1 skipped, including the 18 widget-inspection tests;
  - frontend: full Playwright suite passed;
  - execution-compose 89 checks, 0 failed, including the 4 checks of
    `s_readonly_widget_inspection_in_container`;
  - docker-smoke passed.
  This is the revision the approval request refers to.

## Id-only Greenhouse mapping and output privacy (2026-10-20)

- **Real posting (read-only run #3, `e2a8d97`):**
  - API retrieval succeeded; page observation succeeded;
  - DOM extraction failed (id-only controls, ARIA comboboxes);
  - filling and submission untested.
  Posting-specific. Details: `docs/greenhouse-compatibility-report.md`.
- **Built, local only** (commit `835c34a`):
  - the evidence-based mapper `preparation/greenhouse_dom.py`;
  - the second fixture `fixtures/ats_receiver/greenhouse_v2.py`, whose widget behaviour is a
    labelled assumption;
  - the adapter `greenhouse_dom` (fixture-only, `real_destinations: false`);
  - the read-only CLI's allowlisted, aliased, guarded output;
  - the mapping-evidence collector (off by default);
  - the Compose scenario `s_readonly_mapping_in_container`;
  - v2 badges in the UI and a v2 e2e test.
- **Not done:** no new real-page load. The follow-up observation needs a new approval
  (`docs/greenhouse-readonly-compatibility-proposal.md`, "Follow-up observation B2").
- **Commands actually run (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `uv run pytest tests/test_greenhouse_dom.py`: 26 passed;
  - `uv run pytest tests/test_gh_readonly.py`: 17 passed;
  - `uv run pytest` (full backend): 278 collected, 278 passed;
  - `uv run ruff check .` and `uv run ruff format --check .`: clean;
  - `npx tsc --noEmit` and `npm run lint`: clean;
  - `npx playwright test e2e/submission.spec.ts` (desktop + mobile): 20 passed, including the new v2 test on both projects.
  - One earlier full run was invalid and is not counted: it ran at the same time as a focused
    run and both used the shared test database and receiver port 8799.
- **CI #34** ([39444820135](https://github.com/KevinD003/AutoApply/actions/runs/39444820135)),
  tested SHA `6d0a43796b96613e5651c29dd623327d2e4447a0`, all four jobs passed:

  | Job | What it ran | Result |
  |---|---|---|
  | backend | full backend suite (`pytest`) | 277 passed, 1 skipped (a `test_container_runner.py` test that skips on CI's runner; it ran locally, which is why the local count is 278 passed) |
  | frontend | `tsc`, lint, **full** Playwright suite (`npx playwright test`, desktop + mobile) | 26 passed |
  | execution-compose | container-mode scenarios, including `s_readonly_observation_in_container` and `s_readonly_mapping_in_container` | 80 checks, 0 failed |
  | docker-smoke | Compose smoke test | passed |

  The local Playwright run above was the targeted `submission.spec.ts` only (20 passed); it is
  not the full frontend suite.

## B3 observation with approved dependencies (2026-10-20)

- **Policy:** `SubresourceRule`, enforced by:
  - the browser's resolver rules;
  - the in-browser filter, including redirect targets;
  - the egress-proxy session allow-list;
  - the runner's resolver exemptions;
  - WebSockets routed and never connected.
  - Method policy: GET only for the page; GET/HEAD only for the CDN's scripts and
    stylesheets.
  - The rule is fixed in code.
- **Tests:**
  - `tests/test_b3_policy.py` (7, netns browser path, mutation-checked);
  - Compose `s_readonly_b3_dependency_policy_in_container` (container path; canary silent).
- **CI #42** on `bf6642b`: all four jobs passed, with execution-compose at 85 checks,
  0 failed. Local full backend suite on `bf6642b`: 314 passed.
- **Run:** manual run #6 (39490684255) on `bf6642b`, once.
  - Requests: A 3×200; 1 navigation; 19 GET requests.
  - CDN scripts and stylesheets loaded; refused: 4 data requests, 6 fonts, 1 image.
  - **Mapping unchanged from B2.** New evidence: attachment inputs sit in groups named by
    their question.
- **Local change from that evidence:** the `mapped_via_group` rule for attachments (exact
  group name, one file input per group), with tests. The posting stays refused for its other
  gaps.
- **Final code revision `ee35b49`:**
  - local full backend suite: 318 passed;
  - focused mapper/adapter, B3-policy and read-only suites: 74 passed;
  - **CI #43** ([39492067001](https://github.com/KevinD003/AutoApply/actions/runs/39492067001)):
    - backend 317 passed, 1 skipped;
    - full Playwright suite 26 passed;
    - execution-compose 85 checks, 0 failed, including the B3 policy scenario and its
      attachment-group check;
    - docker-smoke passed.
- **External activity:** stopped after run #6. No further run is proposed without a new
  request.

## B2 real-page mapping observation (2026-10-20)

- **Run:** authorized once by the user and run once: manual run #4
  ([39455167671](https://github.com/KevinD003/AutoApply/actions/runs/39455167671)) on
  `151e7a0` (the `a11c71d` code plus docs). Success.
- **Requests:** A: 3 GETs, all 200. B: 1 navigation, 9 browser requests, 0 non-GET, 43,185
  bytes. No limit reached.
- **Blocked dependencies:** 8 of the 9 requests went to 2 other greenhouse.io hosts and were
  blocked (5 scripts, 2 stylesheets, 1 image). Observed: the page as served, without those
  scripts.
- **Mapping:** 17 of 22 fields unique. `resume` and `cover_letter` incompatible (label
  mismatch); `location` absent; `latitude` and `longitude` not observable (page-managed).
  7 dropdowns: options not observable at load. 5 comboboxes are named by no API field.
- **Execution:** none. The adapter would refuse this posting before disclosure, and it stays
  refused for real destinations. Filling and submission remain unauthorized and untested.
- **Log cleanup:** run #3's logs were deleted with authorization; the run record was kept.
- Details: `docs/greenhouse-compatibility-report.md` ("B2").

## Approval binding, enforced read-only limits, precise observations (2026-10-20)

- **Approval binding (D28):**
  - approvals record the adapter and adapter version they were given for;
  - a mismatch is refused at queueing (and that approval retired), at runner load and in both
    gates;
  - approvals given before bindings existed stay valid while their meaning is unchanged.
  - Migration `5d2e7a91c4b0`. Tests: `tests/test_approval_binding.py`.
- **Enforced limits for B2** (`gh_readonly.Limits`):
  - 3 API requests;
  - 1 top-level navigation (later ones aborted before sending);
  - ≤ 3 same-origin redirect hops;
  - 150 browser requests;
  - a 20 MB received-bytes **stop condition** (not a transfer cap);
  - 2 M-character retained DOM;
  - a 90 s in-process observation deadline;
  - a 150 s whole-run watchdog (exit 5) plus a 200 s outer kill;
  - 256 KiB printed output.
  Each is tested locally against fixtures. No external request was made.
- **Observations:**
  - one per API field: `unique` / `absent` / `ambiguous` / `incompatible` / `not_observable`;
  - each check true, false, `not_observable_at_load` or `not_applicable`;
  - options rendered only on open are `not_observable_at_load`, not a mismatch.
- **Log cleanup:** prepared in `docs/greenhouse-compatibility-report.md`; nothing deleted.
- **B2:** request text in the proposal; not authorized, not run.
- **Results:**
  - **CI #35** on `b6f9eec`: **failed**, in the `backend` job only. The new load-time
    binding check replaced the production isolation and interception refusal reasons in 2
    tests. The local full run showed the same: 2 failed, 300 passed.
  - **Fixed in `a11c71d`:** the binding check now runs after those refusals, still before any
    browser work. The assertions were not changed.
  - **Local, on `a11c71d`** (sandbox, run one at a time):
    - full backend `uv run pytest`: 302 passed, none skipped;
    - targeted `npx playwright test e2e/submission.spec.ts` (desktop + mobile): 20 passed.
      This is not the full frontend suite.
  - **CI #36** ([39450274605](https://github.com/KevinD003/AutoApply/actions/runs/39450274605)),
    tested SHA `a11c71d53a083a4b3a998a2916c7a981e2fece25`, all four jobs passed:
    - backend, full suite: 301 passed, 1 skipped;
    - frontend: `tsc`, lint and the **full** Playwright suite, 26 passed;
    - execution-compose (container-mode scenarios, including both read-only observation
      scenarios): 80 checks, 0 failed;
    - docker-smoke: passed.
- **Still unsupported:**
  - location search pickers (the hidden coordinates come from a search NoEfforts does not
    perform);
  - multi-choice comboboxes;
  - questions shown by page logic NoEfforts cannot see;
  - security-code steps on this page type;
  - pasted text instead of an attachment.

## Proxy control-plane separation (2026-10-20)

- **Code-tested revision:** `d62bea7`. CI #28
  [39421195994](https://github.com/KevinD003/AutoApply/actions/runs/39421195994) passed:
  - backend: 234 passed, 1 skipped;
  - e2e, docker-smoke: passed;
  - execution-compose: 73/73.
  Details are in `docs/evidence-matrix.md` (top section).
- **Commits:**
  - `4a0bd5a`: control API on a UNIX socket; control-plane and recovery tests;
  - `3fb3a9f`: docs and the approval request;
  - `d62bea7`: request body read before refusing (CI #26 race).
- **Proxy management:** no longer on any network. From the browser container, only port 3128
  of the proxy accepts a connection.
- **Read-only Greenhouse check:** at this revision the approval request was ready and no
  posting had been chosen; it has since run (see the section above).

Release blockers for any real use (updated):
- no real-page verification of the Greenhouse mapping (needs permissions A/B);
- legal review of automated submission;
- the pilot permissions in `docs/live-pilot-gate.md`;
- one browser at a time per runner, with no scheduler;
- not verified outside GitHub's ubuntu-24.04 runners.

## Isolated Compose execution milestone (2026-10-20)

Final code-tested revision `9d6bd7e`. CI #24
[39376203647](https://github.com/KevinD003/AutoApply/actions/runs/39376203647) passed all four
jobs. Evidence, the requirement mapping and receiver counts are in `docs/evidence-matrix.md`
(top section). Architecture, the Compose command and limits are in
`docs/execution-service.md`.

| Commit | Content |
|---|---|
| `6d1c790` | browser-runner container (Playwright 1.56.0 / Chromium 141, uid 10002, sandbox on, seccomp, limits), per-session egress proxy service, Compose topology on internal networks, worker container mode, Compose execution test |
| `0e684e5`, `e29a6b2` | harness fixes; tri-state conditional triggers; confirmation tied to this attempt's POST and job path; hidden-field regression; unverified labels on the Greenhouse capability |
| `617ec12` | `docs/execution-service.md`, `browser/README.md` (seccomp provenance) |
| `dcc4500` | single-use authenticated control channel (browser closed when its controller disconnects), one session per runner, driver-version check, bounded slot wait, test-only interception switch, unplaceable conditions → checkpoint, receiver host binding, new Compose scenarios |
| `a073a95`, `992d6b2`, `9d6bd7e` | canary port fix; self-check as PID 1; `--no-deps` in the harness; PID 1 regression test |

| Command (actually run) | Where | Result |
|---|---|---|
| `uv run pytest -p no:warnings -v` | CI #24 on `9d6bd7e` | 230 passed, 1 skipped (root-only PID 1 test; the Compose job covers the same case) |
| `npx playwright test` (desktop + mobile) | CI #24 | step passed |
| `scripts/docker-smoke.sh` (app stack) | CI #24 | passed |
| `./scripts/compose-execution-test.sh` | CI #24 (Docker 28.0.4, kernel 6.17.0-1022-azure, AppArmor userns restriction left at 1) | 56/56 checks |
| `uv run pytest tests/test_container_runner.py` | local, `9d6bd7e` | 14 passed |
| `uv run pytest` (full) | local, `dcc4500` | 229 passed, 1 failed (canary port reuse; fixed in `a073a95`, green in CI #22 and #24) |
| `uv run ruff check . && uv run ruff format --check .` | local and CI | clean |

Not run here: the Compose test locally (this sandbox has no Docker daemon), and anything on
macOS or Docker Desktop.

Release blockers that remain for any real use:
- no real-page verification of the Greenhouse mapping;
- legal review of automated submission;
- the separate pilot permissions in `docs/live-pilot-gate.md`;
- the proxy control port is reachable (token-gated) from the browser network;
- one browser at a time per runner, with no scheduler for more;
- not verified outside GitHub's ubuntu-24.04 runners.

## Milestone 2 closeout and first ATS adapter (2026-10-20)

Evidence, revisions and CI links: `docs/evidence-matrix.md` (top section). Adapter:
`docs/greenhouse-adapter.md`. Live pilot gate (not executed): `docs/live-pilot-gate.md`.

| Commit | Content |
|---|---|
| `0fca81b` | Closeout: browser cwd/fd isolation fix (C1), explicit launch-failure refusal (C2), crash work-dir cleanup (C3), proxy DNS/CONNECT tests (C4), cancel during the code wait (C5), smoke-check failure tests (C6) |
| `cc6c1da` | Greenhouse-hosted adapter + labelled fixture, 19 backend tests, desktop + mobile e2e |

| Command (on `cc6c1da` code) | Result |
|---|---|
| `cd backend && uv run ruff check . && uv run ruff format --check .` | clean |
| `cd backend && uv run pytest -rs` | **212 passed, 0 skipped** (399 s) |
| `cd frontend && npx tsc --noEmit && npm run lint` | clean |
| `cd frontend && npx playwright test` | **24 passed** (desktop + mobile) |
| `./scripts/test_smoke_lib.sh` | 7/7 checks behave as expected (locally and in CI) |
| GitHub Actions | #14 on `0fca81b`: all jobs passed; #15 [39365659479](https://github.com/KevinD003/AutoApply/actions/runs/39365659479): backend, frontend (e2e), docker-smoke all passed |

Docker: Smoke-tested in GitHub CI; not yet verified on the user's Mac.

Release blockers for any real use:
- the browser sandbox limits (deny-list hiding under the same OS user, Chromium's own sandbox
  off, no seccomp or cgroup limits);
- no real-page verification of the Greenhouse mapping;
- legal review of automated submission;
- the separate pilot permissions in `docs/live-pilot-gate.md`.

## Phase C validation milestone 2 (2026-10-19/20)

Full evidence, real vs simulated, and the six defects this round found:
`docs/evidence-matrix.md` (top section).

| Command (final code, `bae5120`) | Result |
|---|---|
| `cd backend && uv run ruff check . && uv run ruff format --check .` | clean |
| `cd backend && uv run pytest` | **188 passed** (includes 4 real-broker, 13 isolation, 19 validation, 4 evidence tests) |
| `cd frontend && npx tsc --noEmit && npm run lint` | clean |
| `cd frontend && npx playwright test` | **22 passed**: Phase A, Phase B, navigation race, 8 submission tests; desktop and mobile |
| GitHub Actions run #12 on `bae5120` | **backend, frontend, docker-smoke all passed** |

Not done or not proven:
- **Docker:** Smoke-tested in GitHub CI; not yet verified on the user's Mac. Never run in this sandbox (no daemon).
- **Browser sandbox:** hiding is a deny-list under the same OS user. There is no seccomp
  profile, cgroup limit or dedicated user, and those are required before untrusted live
  browsing.
- **Simulated expiries:** approval and checkpoint expiry in the browser tests, and the dead
  worker's lease in the redelivery tests, are set in the database rather than waited out.
- **No real ATS** (first adapter proposed in `docs/first-adapter-proposal.md`), no live
  application, no real candidate data.

## Phase C validation run (2026-10-19)

| Command | Result |
|---|---|
| Baseline at `58ac9ea`: `uv run pytest`, `ruff check`, `ruff format --check` | 95 passed; clean |
| `cd backend && uv run pytest` at `ebb3e3b` | **145 passed** (158 s) — includes 25 failure-injection, 8 security/egress/checkpoint, 3 real-Celery, 3 migration, 11 approval-hardening tests |
| `uv run ruff check . && uv run ruff format --check .` at `289e0b0` | clean (`64a560a` failed CI's format check; fixed in `289e0b0`) |
| `cd frontend && npx tsc --noEmit && npm run lint` | clean |
| `cd frontend && npx playwright test` | 4 passed (Phase A + B, desktop + mobile); execution UI not covered |
| GitHub Actions CI | run #1 (`64a560a`): failed, backend formatting. Run #2 (`289e0b0`): backend **passed** (lint + full pytest); frontend e2e **failed** — Phase A desktop and mobile timed out waiting for the profile page after registration, Phase B passed. Run #3 (`400f3c0`, same code + docs) and run #4 (`ad57210`): **all jobs passed**. Most likely cause later reproduced and fixed in `7ce41ff` (the run's traces were not kept, so this is strong supporting evidence, not a forensic certainty about that run): the test typed into the login form's identically labelled fields while a slow client-side navigation to /register was still in progress (reproduced deterministically with a 1.5 s route delay; regression spec `navigation-race.spec.ts`). |
| Docker Compose | at the time untested here (no Docker daemon). Now: Smoke-tested in GitHub CI; not yet verified on the user's Mac. |

Receiver-counted outcomes (independent ledger), all from `tests/test_execution_failures.py`,
`tests/test_execution_security.py`, `tests/test_celery_execution.py`:

| Injected event | Attempt / application result | Receiver accepted |
|---|---|---|
| Duplicate deliveries (sequential, 3 competing processes, 3 Celery deliveries) on a non-idempotent receiver | 1 confirmed, others ignored | 1 |
| Crash before any external write | re-pended by sweeper, then confirmed | 1 |
| Crash after disclosure, before send gate | abandoned, not retried | 0 (1 upload disclosed) |
| Crash at final-send boundary (process and Celery child) | unknown / submitted_unconfirmed; Celery did not redeliver | 0 |
| Accepted, response dropped | unknown / submitted_unconfirmed | 1 |
| Crash after receipt, before local commit | unknown → reconciled as received | 1 |
| Server error after acceptance / before acceptance | unknown (indistinguishable) | 1 / 0 |
| Validation failure, expired session | rejected | 0 |
| Upload failure | abandoned | 0 |
| Form changed after approval | failed_safe before any disclosure | 0 |
| Lease loss: old worker resumes after replacement confirmed | old worker: lost_authority | 1 |
| Lease loss after old worker disclosed | abandoned; no replacement | 0 |
| Revocation before claim / while preparing / after disclosure | failed_safe / failed_safe / abandoned | 0 |
| Document or protected fact changed while running | abandoned at send gate | 0 |
| Cancel before send gate / after send gate | cancelled / refused (409), completes | 0 / 1 |
| Broker outage after commit (**simulated** publish failure) | outbox retained, later published once | 1 |
| Code checkpoint: wrong then right, replayed round, other user | confirmed; replay 409; other user 404 | 1 |
| Code checkpoint expired / 3 wrong codes | abandoned | 0 |
| Hostile page: img/iframe/fetch/beacon/redirects to another port, metadata IP, RFC1918, IPv6 loopback | confirmed; canary server received 0 requests | 1 |

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
| Docker | Smoke-tested in GitHub CI; not yet verified on the user's Mac. | CI job `docker-smoke` |

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
| Docker Compose | Smoke-tested in GitHub CI; not yet verified on the user's Mac. Execution inside Compose is not supported (no browser in the image; attempts fail safe) |
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

## Phase C — Controlled execution: partial (local fixtures only)

| Item | Status |
|---|---|
| Durable attempts, outbox, leases, fencing, gates, sweeper | complete for the fixture adapter |
| Fixture adapter (inspect, extract, fill, upload, readback, checkpoint, submit, confirm) | complete, fixture-only |
| Verification-code checkpoints | complete (worker holds a slot while waiting, bounded) |
| Minimal evidence | complete; daily retention purge; user deletion (refused while running) |
| Browser isolation (container, `NOEFFORTS_BROWSER_ISOLATION=container`, used by Compose) | separate browser-runner container: uid 10002, Chromium sandbox on and self-checked, seccomp, no capabilities, read-only root, CPU/memory/pids/time limits, internal networks only, per-session egress proxy, single-use authenticated control channel. Compose-tested in CI against the synthetic receiver only |
| Browser isolation (netns, local development) | network + PID + mount namespaces, egress proxy, locked hiding mounts; Chromium's own sandbox off in this mode. Limit: same OS user, deny-list |
| ATS adapter | `greenhouse_hosted` and `greenhouse_dom`, **fixture-verified only** (`docs/greenhouse-adapter.md`); real destinations refused |
| Real employer execution | **not started** — all real destinations are refused; pilot gate proposed, not approved |
| Execution UI | browser-tested, desktop and mobile, receiver as oracle |
| Readback mismatch | forced for text, select, checkbox, file |

## Phase D — Verification and integrations: partial
Built: manual entry of an emailed verification code, as a checkpoint the user answers
(fixture-tested; see "Verification-code checkpoints" above). Not started: optional Gmail OAuth
(personal/testing first; see `docs/research/gmail-oauth.md`), optional Tsenta provider (disabled
by default; docs inaccessible from this environment), spend reporting.

## Phase E — Expansion: not started

## External services status

| Service | Docs | Access | Implemented | Tested |
|---|---|---|---|---|
| Tsenta | product + MCP docs read; developer docs inaccessible from this environment | none | no | no |
| Freehire API | read in code and public docs | none (no live call has been made or approved) | discovery client implemented locally: off by default, fixture origins only, never an execution destination (D33, D34) | fixture only |
| Gmail API | requirements documented | none | no | no |
| LLM provider | — | no key configured | interface only | fake provider in tests only |
| Real ATS (Greenhouse, Lever, …) | Greenhouse public Job Board API docs read | read-only only: one public Greenhouse posting observed in owner-authorized manual runs (`docs/greenhouse-compatibility-report.md`) | Greenhouse-style adapters against local approximations only; nothing filled, uploaded or submitted on a real page; real destinations refused | fixture only (structure observed read-only) |
| REA | README/docs read | `--help` ran once | not used for any analysis | — |

## Known limitations

- Classification covers English wording and the patterns in `docs/answer-policy.md`;
  everything else becomes a checkpoint (safe but more manual work).
- The country list in `classify.py` is partial (24 countries); unlisted countries are asked.
- Login rate limiting is per process.
- Next.js resolves the API address at build time; rebuild after changing
  `NOEFFORTS_BACKEND_URL`.
- Fixture forms are reachable without login outside production (they contain no user data).
