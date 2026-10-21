# Implementation status

Last updated: 2026-10-21 (widget inspection run #7 failed before any widget action because of a script-mode defect; fixed locally; a new run needs a new authorization). For requirement-by-requirement evidence see
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
  - CI runs the full suite on the commit (recorded below once it has run).

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
| ATS adapter | Greenhouse-hosted, **fixture-verified only** (`docs/greenhouse-adapter.md`); real destinations refused |
| Real employer execution | **not started** — all real destinations are refused; pilot gate proposed, not approved |
| Execution UI | browser-tested, desktop and mobile, receiver as oracle |
| Readback mismatch | forced for text, select, checkbox, file |

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
| Real ATS (Greenhouse, Lever, …) | Greenhouse public Job Board API docs read | none | Greenhouse-hosted adapter against a local approximation only; real posts not read, real destinations refused | fixture only |
| REA | README/docs read | `--help` ran once | not used for any analysis | — |

## Known limitations

- Classification covers English wording and the patterns in `docs/answer-policy.md`;
  everything else becomes a checkpoint (safe but more manual work).
- The country list in `classify.py` is partial (24 countries); unlisted countries are asked.
- Login rate limiting is per process.
- Next.js resolves the API address at build time; rebuild after changing
  `NOEFFORTS_BACKEND_URL`.
- Fixture forms are reachable without login outside production (they contain no user data).
