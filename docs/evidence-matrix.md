# Evidence matrix (Phase C validation)

Baseline before this work: commit `58ac9ea` (clean tree apart from an untracked Redis
`dump.rdb`, since git-ignored), 95 backend tests passed, ruff clean. Environment: cloud sandbox,
Python 3.12.3, PostgreSQL 16.15, Redis 7.0.15, Celery 5.6.3 / kombu 5.6.2 / redis-py 6.4.0
(prefork pool), SQLAlchemy 2.0.55, FastAPI 0.149.0, Alembic 1.20.0, Playwright 1.56.0 (Python)
with Chromium 141.0.7390.37, Node 22.22.0, Next.js 15.5.4.

"Oracle" = the synthetic receiver's own SQLite ledger (`fixtures/ats_receiver`), which shares
no code or database with NoEfforts. "Mock" marks anything simulated.

## Proxy control-plane separation and recovery (2026-10-20)

Scope: local implementation and synthetic tests only. No external posting was retrieved, no
page was opened, and no candidate data was used.

- **Baseline.** Before this work HEAD was `a595795`, docs-only after code `9d6bd7e` (CI #24,
  above; CI #25 on `a595795` passed).
- **Code-tested revision:** `d62bea7`. CI #28
  [39421195994](https://github.com/KevinD003/AutoApply/actions/runs/39421195994) passed all four
  jobs:
  - backend: 234 passed, 1 skipped (the same root-only PID 1 test as before);
  - frontend e2e: passed;
  - docker-smoke: passed;
  - execution-compose: **73/73 checks**
    ([job](https://github.com/KevinD003/AutoApply/actions/runs/39421195994/job/118622270249)).

| Revision | Change | CI | Outcome |
|---|---|---|---|
| `4a0bd5a` | control API moved to a UNIX socket on the `egress_control` volume (proxy rw, worker ro); `exec_proxyctl` removed; new control-plane, recovery and post-OOM checks | #26 | execution-compose 73/73 ✓, frontend ✓, smoke ✓; backend ✗: `test_runner_and_proxy_control_need_their_tokens` got BrokenPipeError instead of 401 |
| `3fb3a9f` | docs (approval request) on the same code | #27 | all ✓ (the race did not trigger) |
| `d62bea7` | control API reads the request body before refusing (reproduced: 10/500 refused requests broke before, 0/500 after) | #28 | all ✓ |

**Proxy management reachability (Compose, CI #28, from inside the browser container)**

| Check | Result |
|---|---|
| TCP connect to every port 1–65535 of `egress-proxy` | only **3128** accepts |
| Control socket path in the browser container | absent |
| Sensitivity control: a listener on `0.0.0.0:3199` started inside the proxy container | found by the same scan (`[3128, 3199]`) |
| Through the proxy with a real session's credentials: `CONNECT egress-proxy:3129`, `egress-proxy:3128`, `127.0.0.1:3128`, `localhost:3129`, `worker:8000`; absolute GET `http://egress-proxy:3129/health`, `http://127.0.0.1:3128/` | all **403** |
| Positive control: `CONNECT receiver:8799` with the same credentials | 200 |
| Worker over the socket: create, inspect, delete own session; no token | 201/200/200, then 404 after delete; 401 without token |
| After `docker compose restart egress-proxy` | only 3128 open; worker reaches control again; approved run confirmed |

**Recovery (Compose, CI #28)**

| Scenario | Result |
|---|---|
| Runner restart with an open session | old endpoint and secret refused; old runner session unknown (404); old proxy session deleted (200); `/tmp` clean; new attempt confirmed |
| Memory hog → OOM kill → restart | hog attempt `failed_safe`, 0 accepted, still one attempt with `retry_count` 0 (not replayed); `/tmp` clean; next attempt confirmed |
| Browser lost after disclosure (local pytest) | `abandoned`, `needs_user_action`, retry 0, 0 accepted; a redelivery is ignored |

**Receiver acceptance counts (CI #28):** 1 each for:
- the approved run after the proxy restart;
- the Greenhouse security-code flow (0 before the code);
- the hostile page;
- the run with interception off;
- the attempt after OOM recovery;
- the attempt after the runner restart.

Interrupted runs:
- unknown with a duplicate delivery: 1;
- runner killed mid-submit: ≤ 1;
- worker killed mid-submit: ≤ 1, never resent.

Stop-safely cases: 0.

**New tests**

| Test | What it checks |
|---|---|
| `test_control_api_is_an_owner_only_unix_socket_not_a_network_listener` | the control API is an owner-only UNIX socket, not a network listener |
| `test_restart_replaces_a_stale_control_socket` | a restart replaces a stale socket |
| `test_refusals_are_delivered_not_broken_pipes` | regression for the CI #26 race |
| `test_browser_lost_after_disclosure_is_abandoned_not_retried` | browser lost after disclosure is abandoned, not retried |
| Compose `s_control_plane_separation` | the reachability checks above |
| Compose `s_runner_restart_recovery` | the restart recovery checks above |
| Compose `s_memory_exhaustion` | extended with the post-OOM checks |

Local runs (`d62bea7` code):
- `tests/test_container_runner.py`: 18 passed;
- `tests/test_browser_isolation.py`: 18 passed (on `4a0bd5a`);
- ruff: clean.

The full local suite was not rerun; CI #28 ran it.

## Isolated Compose execution milestone (2026-10-20)

Scope: the browser runs in its own sandboxed container behind a per-session egress proxy, and
the Compose stack is tested **only against the synthetic receiver**. No real employer pages,
candidate data, external accounts or paid services were used. Architecture and limits:
`docs/execution-service.md`.

**Four statuses, kept separate**

| Status | Result | Evidence |
|---|---|---|
| App-stack Docker smoke (`docker-smoke`) | passed | CI #24 [job](https://github.com/KevinD003/AutoApply/actions/runs/39376203647/job/118474795589) |
| Containerized browser execution (`execution-compose`) | passed, 56/56 checks, synthetic receiver only | CI #24 [job](https://github.com/KevinD003/AutoApply/actions/runs/39376203647/job/118474795553) |
| Fixture adapter compatibility (Greenhouse-shaped fixture) | passed (pytest + Compose security-code flow) | `test_greenhouse_adapter.py` (CI #24 backend), `s_greenhouse_security_code_flow` |
| Actual Greenhouse compatibility | **not tested** (no real page read) | proposal only: `docs/greenhouse-readonly-compatibility-proposal.md` |

**Phase 0 reconciliation**
- **Start state.** HEAD `4683d35` was docs-only on code `cc6c1da`. Its CI run #16 completed
  green, so the documentation follow-up's CI did finish.
- **Final code-tested revision of this milestone:** `9d6bd7e`. CI #24
  [39376203647](https://github.com/KevinD003/AutoApply/actions/runs/39376203647) passed every
  job:
  - backend: 230 passed, 1 skipped (`test_self_check_finds_its_browsers_when_the_runner_is_pid_1`
    needs root; the skip reason is printed, and the Compose job covers the same case);
  - frontend: e2e, desktop and mobile; the step passed (the log tail does not show a count);
  - docker-smoke: passed;
  - execution-compose: 56/56 checks.
- **CI host:** ubuntu-24.04, Docker 28.0.4, kernel 6.17.0-1022-azure. The value of
  `kernel.apparmor_restrict_unprivileged_userns` was 1, i.e. the restriction stayed on and was
  not relaxed for this job.

| Revision | Change | CI | Outcome / cause of failure |
|---|---|---|---|
| `6d1c790` | browser-runner, session proxy, Compose topology, harness | #17 | exec ✗: the host-side test could not reach the receiver on an internal network |
| `0e684e5` | receiver reached via `compose exec`; read-only proposal | #18 | exec ✗: admin reset sent as GET |
| `e29a6b2` | tri-state conditions, attempt-bound confirmation, harness fixes | #19 | backend ✗ (a test race, below); exec ✗ (receiver bound to loopback) |
| `617ec12` | docs only (same code as `e29a6b2`) | #20 | same as #19 |
| `dcc4500` | relay control channel, version check, interception switch, unplaceable conditions, new scenarios | #21 | backend ✗ (canary port reused in the test); exec ✗ (self-check failed with the runner as PID 1; a dependency recreate took the API down) |
| `a073a95` | canary port fix | #22 | backend ✓ frontend ✓ smoke ✓; exec cancelled (still had the PID 1 bug) |
| `992d6b2` | PID 1 self-check fix; `--no-deps`; API check per scenario | #23 | all ✓ |
| `9d6bd7e` | PID 1 regression test (reproduced first: old launcher → "no browser processes found") | #24 | all ✓ |

**Defects found and fixed in this milestone (each now has a test that would fail)**

| Defect | Test |
|---|---|
| A conditional question was marked "not asked" when its trigger was merely unanswered | `test_unanswered_trigger_keeps_its_conditional_question_pending` |
| A condition on a missing, later or circular question was evaluated as false | `test_unplaceable_condition_is_a_checkpoint_not_a_guess` |
| Any confirmation page counted, even one for a different posting | `test_outcome_classification[gh_confirm_other_job]` (→ unknown), `[gh_confirm_redirect]` (→ confirmed) |
| A stale or killed controller could leave a running browser; anyone with the endpoint could attach | `test_control_channel_is_single_use_and_authenticated`, `test_hard_killed_controller_leaves_no_browser`, `test_unused_session_expires`; Compose `s_worker_killed_mid_submit` |
| A runner/worker Playwright mismatch would surface as a confusing protocol error | `test_driver_version_mismatch_is_refused_with_reason` |
| The self-check inspected every Chromium on the host, and found none of its own when it was PID 1 | `test_self_check_finds_its_browsers_when_the_runner_is_pid_1` (local, root); Compose `s_sandbox_selfcheck` |
| A test race: the lease was expired while the worker still held the row lock | `test_no_takeover_while_old_worker_may_have_disclosed` (waits for the fault point's marker) |

**Requirement → implementation → test → result (all on `9d6bd7e`, CI #24 unless noted)**

| Requirement | Implementation | Test(s) | Result | Limitation |
|---|---|---|---|---|
| Unprivileged browser user; Chromium sandbox enabled and verified | uid 10002; `chromiumSandbox: true`; self-check of its own renderers (`Seccomp: 2`, no `--no-sandbox`, no uid 0) | `s_container_configuration`, `s_sandbox_selfcheck`, `test_runner_verified_its_own_sandbox` | pass (renderer uid 10002, seccomp 2, NoNewPrivs 1) | verified on GitHub ubuntu-24.04 only |
| Seccomp + capabilities; no privileged mode, socket, host network or mounts | Docker default seccomp + clone/unshare/setns/chroot; `cap_drop: ALL`; no-new-privileges | `s_container_configuration` (docker inspect), probe (CapEff/CapBnd 0) | pass | seccomp rule provenance in `browser/README.md` |
| Fail closed if isolation cannot start | 503 from runner → `IsolationUnavailable` → failed_safe | `s_sandbox_unavailable` (unmodified Docker seccomp), `s_runner_unavailable`, `test_container_mode_fails_closed_when_the_runner_is_unavailable` | pass, 0 disclosures | — |
| No credentials or app files in the browser environment | minimal env; no volumes | `s_browser_container_probe` + insecure control `s_probe_detects_an_insecure_configuration` | pass; the control flagged fake env, mounted secret, reachable DB/Redis | the runner's own token is present (authenticates the worker only) |
| Default-deny egress at the infrastructure boundary | internal networks; session proxy (exact host:port, public IPs unless fixture, connect to the checked IP, 407 without a session) | probe (DNS EAI_AGAIN; DB/Redis/API/web/receiver/canary unresolvable; metadata/internet ENETUNREACH; worker refused); `s_infrastructure_only_egress`; `test_container_boundary_alone_blocks_egress_without_interception` | pass; with interception off: 0 blocked in-process, canary 0 hits, proxy denied `10.0.0.1:80`, `169.254.169.254:80`, `::1:80`, `canary:8798` | proxy control port reachable from the browser network (token-gated, 401) |
| Narrow control channel; stale authority revoked | loopback browser server; relay needs runner token + session secret; single connection; close on disconnect | runner tests above; `s_worker_killed_mid_submit` | pass: sessions 0 within 20 s after the worker kill | liveness is TCP-based |
| CPU, memory, process and time limits | 1536 MiB / 1.5 CPU / 512 pids / per-session 45 s (test) or 600 s | `s_memory_exhaustion`, `s_session_time_limit` | pass: hog page → failed_safe, 0 accepted, container OOM-killed and restarted; slow page → failed_safe, 0 disclosures | the memory limit is per container, so a hog ends the whole runner (one session at a time) |
| No resend after ambiguous outcomes; duplicate delivery ignored | unchanged state machine | `s_unknown_then_duplicate_delivery`, `s_runner_lost_during_submission`, `s_worker_killed_mid_submit` | pass; receiver acceptances 1 each, attempt `unknown`, `retry_count` 0 | not exactly-once: an uncertain outcome is quarantined, not proven |
| Full approved path | prepare → approve → queue → isolated browser → upload → code checkpoint → submit | `s_greenhouse_security_code_flow` | confirmed; acceptances 0 → 1 (none before the code); 1 upload with the approved digest | synthetic code step (unverified for real Greenhouse) |
| No secrets in logs | logging of ids only | `s_greenhouse_security_code_flow` log scan (code, runner, control, admin tokens across all services) | pass | — |
| Cleanup and evidence retention | session close on exit; `retain_until` on evidence; deletion API | same scenario; `test_evidence_lifecycle.py` | pass: sessions 0, no profile in `/tmp`, evidence deleted (200) | — |

**Receiver counts (Compose, CI #24, receiver ledger)**

| Scenario | Accepted | Other |
|---|---|---|
| Greenhouse security-code flow | 0 before the code, 1 after | 1 upload disclosure, digest = approved document |
| Hostile page | 1 | canary 0 hits; 7 requests blocked in-process |
| Interception off | 1 | canary 0 hits; 4 destinations denied by the proxy |
| Accepted, response dropped, then a duplicate delivery | 1 | attempt `unknown`, delivery ignored |
| Runner killed mid-submit | 1 | attempt `unknown`, never resent |
| Worker killed mid-submit | 1 | swept to `unknown`, `retry_count` 0 |
| Runner down / sandbox unavailable / memory hog / session limit | 0 | 0 disclosures, failed_safe |

Local runs (cloud sandbox, no Docker daemon):
- `uv run pytest` on `dcc4500`: 229 passed, 1 failed. The failure was the canary port reuse,
  fixed in `a073a95`.
- `tests/test_container_runner.py` on `9d6bd7e`: 14 passed (includes the PID 1 test, which runs
  here as root).
- ruff check and format: clean.

## Milestone 2 closeout and first ATS adapter (2026-10-20)

**Revisions and CI** (links: `https://github.com/KevinD003/AutoApply/actions/runs/<id>`)

| Revision | What | CI run (all jobs) | Backend tests | e2e | Docker smoke |
|---|---|---|---|---|---|
| `c7c4109` | milestone 2 as handed over | #13 [39359765119](https://github.com/KevinD003/AutoApply/actions/runs/39359765119): backend, frontend, docker-smoke passed | 188 passed, 0 skipped (CI log) | step passed | passed |
| `0fca81b` | closeout fixes (below) | #14 [39363852006](https://github.com/KevinD003/AutoApply/actions/runs/39363852006): all passed | 193 passed locally; CI step passed | 22 passed locally (see caveat) | passed in CI |
| `cc6c1da` | Greenhouse adapter + docs | #15 [39365659479](https://github.com/KevinD003/AutoApply/actions/runs/39365659479): backend, frontend (e2e), docker-smoke all passed | 212 passed, 0 skipped (local, `pytest -rs`) | 24 passed locally (desktop + mobile) | passed in CI |

Job links for #13: [backend](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422934216),
[frontend](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422933900),
[docker-smoke](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422934152).

Local vs CI:
- **Sandbox (local):** runs as root, so the browser namespaces are created without a user
  namespace for the outer layer. PostgreSQL 16 is a disposable `initdb` cluster. Chromium is
  /opt/pw-browsers build 1194. No Docker daemon.
- **CI:** a non-root runner, using unprivileged user namespaces after the AppArmor sysctl
  (a CI host setting). PostgreSQL and Redis run as service containers (backend Redis from
  apt). Chromium is installed by Playwright. The real Docker daemon is used for the smoke
  test.
- **Caveat:** the local e2e run for `0fca81b` overlapped edits to backend files; its servers
  had loaded most code at start. CI #14 is the authoritative e2e result for that revision.
- **Docker:** Smoke-tested in GitHub CI; not yet verified on the user's Mac.

**Closeout findings (each with a test that failed first or that pins existing behaviour)**

| # | Finding | Kind | Fix | Test |
|---|---|---|---|---|
| C1 | Chromium inherited the worker's working directory (still the hidden backend tree, because a mount does not move a process already inside it) and descriptors above 3/4 | real gap, reproduced (`CWD_LEAK`, `FD_LEAK` before the fix) | chdir to the work dir; close fds ≥ 5 before exec | `test_browser_cannot_see_worker_process_secrets_or_other_attempts` |
| C2 | A browser that fails to start inside the namespaces surfaced as a generic error | behaviour was already a safe stop; made explicit | launch failure → `IsolationUnavailable` → failed_safe, never an unisolated retry | `test_isolation_failure_refuses_instead_of_browsing_unrestricted[unshare_rejects, unshare_missing]` |
| C3 | Work directories of hard-killed workers were left behind | real (observed) | PID-tagged work dirs; the sweep task removes those whose PID is gone | `test_stale_workdirs_of_dead_workers_are_removed` |
| C4 | Proxy DNS and CONNECT had no direct tests | evidence gap | none needed | `test_proxy_checks_every_resolved_address_and_connects_to_the_checked_one`, `test_proxy_connect_and_absolute_http_follow_the_same_policy` |
| C5 | Cancel during a code wait was not tested | evidence gap | none needed (already refused) | code-wait regression: cancel 409, one attempt |
| C6 | Smoke checks had no test of their failure paths | evidence gap | `scripts/smoke_lib.sh` | `scripts/test_smoke_lib.sh` (CI): request failure, HTTP error, wrong content, exited container, docker failing |

**Regression evidence re-verified (implementation · test · result)**

| Area | Implementation | Tests | Limitation |
|---|---|---|---|
| Checkpoint state frozen | `package.execution_owns_state` in `ensure_current` and the user transition route | `test_reads_and_user_actions_during_code_wait_cannot_reopen_submission` (package reads, user transitions incl. cancel → 409, one attempt); e2e reload during the code wait | the code wait reuses `needs_user_action`; the guard, not a separate state, keeps the meanings apart |
| Duplicate POST at teardown | non-GET/HEAD → `route.continue_()`; failed GET fetch → abort | `test_closing_the_browser_mid_submit_never_resends[netns,off]` (fails on the old code; local server counts POSTs) + the receiver-ledger e2e that first showed 2 acceptances | observed with Playwright Python 1.56.0 / Chromium 141, not claimed for Playwright in general. Not exactly-once: an accepted-but-unanswered submit is `unknown` and reconciled; broker redelivery is refused by the claim CAS (`test_redelivery_after_*`) |
| HTTP methods and redirects | GET/HEAD fetched with hops checked; other methods sent by the browser, hops checked by the proxy (host:port); no retries after the send gate; ambiguous responses → unknown | isolation and failure-mode tests | a POST redirect to another path on the same host:port is followed |
| UI state | `ExecutionCard` polls only while active, then refreshes once | e2e: no attempt requests for 4 s after the final state; no Cancel after `unknown`; desktop + mobile for queueing, verification, cancel, unknown, reconciliation | — |
| Protected mutations | send gate rebuilds content under the app row lock in REPEATABLE READ and compares hashes, so every mutation path is checked by the same validated-versioning step whether or not the path locks | `test_every_protected_mutation_stops_a_running_attempt[10 paths]`, approve-vs-edit interleavings, `test_restoring_a_fact_does_not_resurrect_a_revoked_approval` | a mutation committed after the gate does not change what is sent (`test_mutations_after_send_gate_do_not_change_what_was_sent`) |
| Filled values and bytes | readback of every control; disclosure digest = approved digest = receiver digest | tamper tests (4); `test_autosave_and_upload_are_counted_separately_from_acceptance`; Greenhouse full-run test | — |
| Material form change | fingerprint check before disclosure and after fill | `conditional_field` mode; Greenhouse `gh_drift` | — |
| Tenancy of evidence and checkpoints | owner checks | `test_execution_resources_are_tenant_bound`, cross-user code 404, evidence deletion 404 | — |
| Retention and leaks | daily purge; user deletion; leak scans of DB rows and real worker logs | `test_retention_purge`, `test_no_secrets_in_real_worker_logs`, code-checkpoint leak scan | CI debug artifacts (Playwright traces of the *test* browser, uploaded only on failure, 7-day retention) contain what the test typed, including synthetic codes; they are not scanned. Never run e2e with real data |

**First adapter: Greenhouse-hosted (fixture approximation)** — `backend/tests/test_greenhouse_adapter.py`
(19 tests, all real processes against the receiver; nothing simulated except the fixture itself)

| Requirement | Test | Receiver ledger |
|---|---|---|
| Posting identity (real hosts, embed, fixture path; fixture path on a real host is not a fixture) | `test_posting_identity_from_real_and_fixture_urls` | — |
| Exact wording, help, options, required, types | `test_schema_keeps_exact_wording_help_options_and_required` | — |
| Hidden and unknown controls → unsupported | `test_hidden_and_unknown_controls_become_unsupported` | — |
| JSON vs page cross-check (extra field, reworded question) | `test_job_data_and_page_must_agree`, `test_capture_refused_when_page_disagrees_with_job_data` | — |
| Real posts not read | `test_real_greenhouse_posts_are_not_read` | — |
| Unsupported required control is a checkpoint (no input, no approval) | `test_required_unsupported_control_is_a_checkpoint` | — |
| Conditional question not asked / asked and required | `test_conditional_question_follows_its_trigger`, `test_conditional_question_is_filled_when_it_applies` | 1 acceptance with the conditional answer |
| Full run: exact values, withheld sensitive answer blank, attachment disclosed once with the approved digest, confirmation-page evidence | `test_full_run_is_confirmed_and_sends_exactly_the_approved_values` | 1 acceptance, 1 upload |
| Security code: wrong then right; not accepted before the code | `test_security_code_wrong_then_right` (real worker process) | 0 before, 1 after |
| CAPTCHA → stop before disclosure | `test_captcha_stops_before_anything_is_disclosed` | 0 disclosures, 0 accepted |
| Form changed after approval → stop before disclosure | `test_form_changed_after_approval_stops_before_disclosure` | 0, 0 |
| Rejected / unknown / dropped / upload failure; never resent | `test_outcome_classification[5 modes]` | 0 / 0 / 1 / 1 / 0, unchanged after a second delivery |
| Capability flags | `test_capability_flags` | — |
| UI: read form, review exact wording, conditional "not asked", approve, submit | e2e "Greenhouse-style form: …" (desktop + mobile) | +1 acceptance, 1 attempt |

Fixture compatibility only: the fixture is an approximation built from public documentation,
not Greenhouse markup; no real employer form has been tested.

## Validation milestone 2 (submission UI, real failures, isolation)

Each row names the test, whether the failure is **real** (a real process, broker, browser or
namespace really did it) or **simulated** (we edited the database or injected a fault), and
the outcome counted by the receiver's ledger.

**Revision binding**

| Item | Value |
|---|---|
| Baseline | `ad57210` (CI run #4: all jobs green) |
| Final code commit | `bae5120` |
| CI on that commit | run #12 (`bae5120`): backend, frontend (all e2e), docker-smoke **all passed**. Earlier runs on this work: #6 (`e11484d`) backend failed (no `redis-server` binary), #9 (`292ecb9`) backend and frontend passed but docker-smoke failed (web container exited), #10 (`6c850d7`) docker-smoke failed at the worker-ping step (shell pipeline bug), #11 (`416cf70`) all passed |
| Diff since baseline | `git diff --stat ad57210 bae5120`: 35 files changed, 2405 insertions, 134 deletions |
| Local checks on final code | `ruff check` + `ruff format --check` clean; `pytest`: 188 passed; `tsc --noEmit` + `npm run lint` clean; `npx playwright test`: 22 passed (desktop + mobile). Local runs on `292ecb9`; later commits changed only the Next config file type and the smoke script, and CI ran everything on `bae5120` |

**Defects found by this round (all fixed, each with a test that failed first)**

| # | Defect | How it was found | Fix | Regression test |
|---|---|---|---|---|
| B1 | During a verification-code wait, the review page's package read re-settled the application from `needs_user_action` to `awaiting_approval` while the approval was still valid. **Submit was re-enabled after the data had been sent**, and the worker crashed on an illegal transition. | browser test (code flow) | `package.execution_owns_state`: no re-settling and no user transitions (409) while a worker holds the attempt | `test_reads_and_user_actions_during_code_wait_cannot_reopen_submission`; e2e reload during the code wait |
| B2 | A submit POST was sent **twice**. The in-process route used `route.fetch` + `fulfill`; when the worker gave up and closed the browser, Playwright resumed the paused original request. The receiver counted 2 acceptances for 1 attempt. | browser test (unknown outcome); reproduced with a stand-alone script | non-idempotent requests go out once via `continue_()` (hops checked by the egress proxy); a failed GET fetch aborts | `test_closing_the_browser_mid_submit_never_resends[netns,off]` |
| B3 | Submission card re-fetched attempts in a tight loop (the effect depended on its own result) and left the status stale after the final state (Cancel button still shown) | browser test | poll only while an attempt is active; refresh the application once at the end | e2e: no attempt requests in 4 s after the final state; no Cancel button after `unknown` |
| B4 | e2e worker supervisor started Celery in its own session, so Playwright's teardown left the worker running | stale processes after a run | worker stays in the supervisor's process group | — (harness) |
| B6 | Docker web container exited at start: `next.config.ts` needs TypeScript, absent from the production image; the auto-install failed as the non-root user. A global TypeScript in this sandbox had masked it locally | CI docker-smoke logs | `next.config.mjs` | CI `docker-smoke` |
| B5 | CI run #2 Phase A failure (likely cause; traces of that run were not kept): the test filled the login form's identically labelled fields during a slow client-side navigation to /register | reproduced deterministically with a 1.5 s route delay | wait for the URL and the register button before filling | `navigation-race.spec.ts` |

**Matrix**

| Requirement | Test(s) | Real / simulated | Result (receiver ledger) |
|---|---|---|---|
| Approve, queue, double-click | `submission.spec.ts` "approve, double-click submit…" (desktop + mobile) | real UI, API, Celery worker, isolated browser, receiver | 1 acceptance, 1 attempt; polling stops |
| Reload during execution | "reload during execution…" | real | 1 attempt, 1 acceptance |
| Revoked / expired approval | "revoked and expired approvals…" | revoke real; **expiry simulated** (`expires_at` set in the past) | Submit disabled; API 409; 0 attempts |
| Cancel before dispatch | "cancel before dispatch…" (receiver delays the form 10 s) | real | cancelled; 0 accepted, 0 disclosures after a bounded 12 s observation window |
| Cancel refused after dispatch | "cancel refused once the submit step has begun" (receiver delays 8 s) | real | UI shows the refusal; 1 accepted |
| Codes: wrong, replay, other user, right; reload while waiting | "verification codes…" | real | replay 409, other user 404, Submit stays closed after reload; 1 accepted |
| Expired code | "expired verification…" | **expiry simulated** (`expires_at` in the past) | abandoned; 0 accepted |
| Unknown outcome, reconciliation | "unknown outcome is reconciled…" (receiver accepts, never replies) | real timeout | `submitted_unconfirmed` → reconciled; 1 accepted, 1 attempt |
| Readback: text cleared, select changed, checkbox unchecked, file lost | `test_page_altering_a_filled_value_stops_before_submit[text,select,checkbox,file]` (receiver page script alters the control) | real browser and page | abandoned before send; mismatch key recorded (no values); 0 accepted |
| Broker outage | `test_real_broker_outage_around_outbox_publication`, `test_worker_survives_broker_restart` | real: the disposable Redis process (port 6391) is stopped and restarted empty | outbox keeps the message, published once on recovery; 1 accepted |
| Redelivery: accepted, response lost | `test_redelivery_after_accepted_but_response_lost` | real `kill -9` of the worker mid-send; real kombu redelivery after a 5 s visibility timeout (test-only; production 3600 s); **dead worker's lease expiry simulated** before the sweep | redelivered task refused by the claim CAS; 1 accepted; `unknown` → `submitted_unconfirmed` |
| Redelivery: crash after acceptance | `test_redelivery_after_crash_after_acceptance` | worker blocked by an injected fault after the receipt, then really killed; rest as above | 1 accepted, no second send |
| Every protected mutation path while running | `test_every_protected_mutation_stops_a_running_attempt[answer, answer_bank_delete, consent, document_version, draft_accept, form_version, job_destination, preferences, profile_name, work_authorization]` | real worker process paused after filling; mutation through the public API | abandoned at the send gate; 0 accepted |
| Unrelated edit / edit after the send gate | `test_unrelated_edit_does_not_stop_a_running_attempt`, `test_mutations_after_send_gate_do_not_change_what_was_sent` | real | confirmed; the approved snapshot was sent |
| Uploads and autosave counted separately | `test_autosave_and_upload_are_counted_separately_from_acceptance` | real | 1 upload (digest equals the approved document), ≥5 autosaves, 1 acceptance |
| Revoking cannot recall sent data | `test_revoking_after_disclosure_cannot_recall_transmitted_data` | real paused process | abandoned; upload and autosaves stay in the ledger; 0 accepted |
| Stale worker: paused process vs ownership change | `test_stale_worker_with_real_lease_expiry` (3 s lease, **real** wall-clock expiry) vs `test_old_worker_cannot_continue_after_lease_loss` (**simulated** expiry) | as stated | old worker: `lost_authority`; 1 accepted |
| Browser network isolation without interception | `test_isolation_alone_blocks_egress_without_interception`, `test_namespace_alone_has_no_network`, `test_loopback_destination_denied_without_fixture_exception`, `test_proxy_policy_unit`, `test_free_port_helper_is_not_reachable_from_namespace` | real namespaces, real Chromium, real proxy | canary 0 hits; every off-destination host:port in the proxy's deny log |
| Separation from orchestrator credentials | `test_browser_cannot_see_worker_process_secrets_or_other_attempts`, `test_default_hidden_paths_cover_code_config_and_storage`, `test_refuses_a_browser_binary_inside_a_hidden_path` | real namespaces; synthetic marker files only | worker's /proc entry, hidden dirs and files, and other attempts' work dirs invisible; `umount` refused inside |
| Production cannot disable isolation | `test_production_refuses_to_run_without_isolation`; no UI or API setting exists | real | failed_safe; 0 disclosures |
| Full run through the proxy | `test_full_run_goes_through_the_proxy` + every e2e submission | real | confirmed; 1 accepted |
| Evidence retention and deletion | `test_retention_purge`, `test_user_can_delete_evidence_and_others_cannot`, `test_cannot_delete_evidence_while_running` | real (retention date set in the past) | purged; other users get 404; 409 while running |
| Fake secrets not in logs | `test_no_secrets_in_real_worker_logs` (real Celery worker at DEBUG), leak scan in the code-checkpoint test | real | 0 hits |
| CI #2 investigation | `navigation-race.spec.ts` | real slow navigation (route delay) | B5 reproduced deterministically and fixed; run #2's traces were not kept, so it is the likely, not the proven, cause of that run; no retries or sleeps added |
| Docker smoke | CI job `docker-smoke` (`scripts/docker-smoke.sh`) | real Docker on GitHub's runner | **passed** in CI run #12: build, migrations on start, register/session, web pages and API proxy, worker answers a broker ping, data survives a backend restart. Two defects found on the way: the web image could not load `next.config.ts` without TypeScript (fixed with `.mjs`), and a `| grep -q` pipeline failed the step under pipefail. Never run in this sandbox (no Docker daemon) |

## Earlier Phase C rows (commit `ebb3e3b`; superseded cells marked)

| Requirement | Implementation | Tests | Result | Remaining limit |
|---|---|---|---|---|
| Manifest binds owner, destination origin + submit endpoint, form fingerprint, wording/help/options/required, typed answers, document versions + byte digests, consents, policy version | `preparation/package.py` (`SCHEMA_VERSION = 2`) | `test_approval_hardening::test_manifest_binds_owner_destination_documents_and_policy` | pass | Legal text is the field label; no separate legal-document versioning |
| Client-supplied hash cannot approve | `package.approve` recomputes server-side | `test_client_hash_alone_cannot_approve` | pass | — |
| Approval expiry | `PackageApproval.expires_at`, `active_approval` | `test_approval_expires` | pass | Default 72h, not user-configurable |
| Monotonic revocation; restore doesn't resurrect | new version per change; approvals never un-invalidated | `test_restoring_a_fact_does_not_resurrect_a_revoked_approval` | pass | — |
| false / null / decline / blank are distinct | resolver values; hash covers them | `test_false_null_and_decline_are_distinct`, `test_empty_text_is_rejected_not_stored_as_answer` | pass | — |
| Draft dependencies registered | `ApplicationInput.meta`, stale-draft check | `test_accepted_draft_depends_on_its_facts` (**test-only fake provider**) | pass | No real LLM provider exists |
| Approve vs protected edit (deterministic interleaving) | row lock + server rebuild | `test_edit_committed_between_review_and_approve_blocks_approval`, `test_edit_committed_after_approval_invalidates_before_queue` | pass | — |
| Concurrent rebuilds | `lock_application` in `ensure_current` | `test_concurrent_rebuilds_write_one_version` | pass | — |
| Queue/claim vs revocation | claim re-checks approval under lock | `test_revocation_before_claim`, `test_revocation_while_preparing_stops_before_disclosure`, `test_revocation_after_disclosure_stops_before_send` | pass, oracle 0 | — |
| Worker preparing vs document change | send gate rebuilds content | `test_document_change_after_approval_stops_send` | pass, oracle 0 | Documents cannot be deleted at all (no endpoint) |
| Cancellation vs final dispatch | cancel and send gate share locks | `test_cancel_before_send_gate_wins` (oracle 0), `test_cancel_after_send_gate_is_refused` (oracle 1) | pass | After the gate, cancel is refused; data in flight cannot be recalled |
| Form schema change after approval | fingerprint check before and after fill | `test_receiver_failure_modes[conditional_field]` | pass, oracle 0 accepted, 0 disclosures | — |
| Disclosure authority separate from submit | `gate_before_disclosure` / `gate_before_send`; disclosure evidence | `test_crash_after_disclosure_is_not_retried` (oracle: 1 upload, 0 accepted) | pass | Fill on an autosaving form counts as disclosure; we assume any fill may transmit |
| Duplicate deliveries | claim CAS | `test_duplicate_delivery_sequential_is_ignored`, `test_competing_workers_on_one_attempt_send_once` (non-idempotent receiver, 3 processes), Celery `test_duplicate_deliveries_through_celery_send_once` (3 deliveries) | pass, oracle 1 | — |
| One active attempt per application | partial unique index | `test_second_active_attempt_is_blocked_by_database` | pass | — |
| Crash before external write | sweeper re-pends (bounded) | `test_crash_before_any_external_write_is_retried_once_safely`, Celery `test_death_before_any_write_recovers_through_outbox` | pass, oracle 1 | — |
| Crash at final-send boundary | `sending` → sweep → `unknown` | `test_crash_at_final_send_boundary_becomes_unknown`, Celery `test_worker_process_death_at_send_is_not_redelivered` | pass, oracle 0, no redelivery | — |
| Accepted, response dropped | submit timeout → `unknown` | `test_accepted_but_response_dropped` | pass, oracle 1 | — |
| Crash after receipt, before local commit | sweep → `unknown`; reconcile | `test_crash_after_receipt_before_local_commit` | pass, oracle 1 | Receipt lost locally; user reconciles |
| Ambiguous server errors | → `unknown` | `test_receiver_failure_modes[error_before_accept / error_after_accept]` | pass, oracle 0 / 1 | Both look identical from outside, so both stay unknown |
| Validation failure, expired session, upload failure, slow reply | → `rejected` / `abandoned` / `confirmed` | parametrized failure-mode tests, `test_slow_but_successful_response` | pass | — |
| Stale worker after lease loss | fencing generation, heartbeat, gate | `test_old_worker_cannot_continue_after_lease_loss` (oracle 1), `test_no_takeover_while_old_worker_may_have_disclosed` (oracle 0) | pass | Old browser is closed when its worker detects lost authority; no OS-level kill of a hung browser |
| Broker outage after DB commit | transactional outbox | `test_broker_outage_after_commit_loses_nothing` | pass | **Mock** here; superseded by the real outage tests above |
| Celery settings reviewed | `app/worker.py` docstring | Celery tests above | pass | Redelivery now exercised (above), with a 5 s test-only visibility timeout |
| Read back actual control values | `FixtureAtsAdapter.readback` | every confirmed run; oracle field values checked in `test_happy_path_submits_once_with_receipt` | pass | Forced for text, select, checkbox and file (above) |
| Capability flags | `execution/policy.py::CAPABILITIES` | `GET /api/execution/capabilities` (no dedicated test) | implemented | Only `fixture_ats` exists |
| Real employer destinations refused | `policy.adapter_for` | `test_real_employer_destination_is_refused_at_queue` | pass | — |
| Production rejects fixture URLs | `is_fixture_origin` ignores settings in production | `test_production_rejects_fixture_destinations` | pass | — |
| Browser egress | route allow-list, redirect check, service workers blocked, resolver rules, pop-ups closed | `test_browser_cannot_reach_other_origins` (img, iframe, fetch, beacon, single and chained redirects to another port; metadata, RFC1918, IPv6 loopback) | pass, canary 0 hits | **Found and fixed a redirect bypass.** Superseded: network namespace + egress proxy (above) |
| Verification-code checkpoints | `Checkpoint`, `submit_code`, `take_code` | `test_code_checkpoint_wrong_then_right_code_and_replay`, `..._expiry_...`, `test_too_many_wrong_codes` | pass | Worker holds a slot while waiting (bounded by TTL) |
| No secrets in artifacts | evidence minimization; codes erased | leak scan inside the code-checkpoint test (fake OTP + fake secret; evidence, events, audit, timeline, outbox, checkpoints, attempts, worker stdout/stderr) | pass, 0 hits | Broker payloads checked by construction (ids only), not scanned |
| Tenancy for Phase B/C resources | owner checks; worker derives tenant from attempt | `test_tenant_isolation_for_preparation`, `test_execution_resources_are_tenant_bound`, `test_worker_derives_tenant_from_attempt_not_payload`, code checkpoint cross-user check | pass | — |
| Migrations | Alembic | `test_migrations.py`: empty→head, populated Phase A→head with data preserved, downgrade/re-upgrade (disposable DB) | pass | Phase A's downgrade was edited after the fact (not deployed anywhere); future fixes use new migrations |
| Test DB safety | conftest refuses non-`*_test` DBs | — | implemented | — |
| CI | `.github/workflows/ci.yml` | see implementation-status for the run result | — | — |
| Docker | `docker-compose.yml` | CI `docker-smoke` | Smoke-tested in GitHub CI; not yet verified on the user's Mac. | no Docker daemon in this sandbox |

## Not credited

- REA: only `--help` was run; no analysis.
- Tsenta, Gmail, Freehire, LLM providers: no access, no implementation, no tests.
- Execution UI: browser-tested in milestone 2 (above).
- Greenhouse or any other real ATS: proposal only (`docs/first-adapter-proposal.md`).
