# Evidence matrix (Phase C validation)

Baseline before this work: commit `58ac9ea` (clean tree apart from an untracked Redis
`dump.rdb`, since git-ignored), 95 backend tests passed, ruff clean. Environment: cloud sandbox,
Python 3.12.3, PostgreSQL 16.15, Redis 7.0.15, Celery 5.6.3 / kombu 5.6.2 / redis-py 6.4.0
(prefork pool), SQLAlchemy 2.0.55, FastAPI 0.149.0, Alembic 1.20.0, Playwright 1.56.0 (Python)
with Chromium 141.0.7390.37, Node 22.22.0, Next.js 15.5.4.

"Oracle" = the synthetic receiver's own SQLite ledger (`fixtures/ats_receiver`), which shares
no code or database with NoEfforts. "Mock" marks anything simulated.

## Validation milestone 2 (submission UI, real failures, isolation)

Each row names the test, whether the failure is **real** (a real process, broker, browser or
namespace really did it) or **simulated** (we edited the database or injected a fault), and
the outcome counted by the receiver's ledger.

**Revision binding**

| Item | Value |
|---|---|
| Baseline | `ad57210` (CI run #4: all jobs green) |
| Final code commit | `{{FINAL}}` |
| CI on that commit | {{CI}} |
| Diff since baseline | `git diff --stat ad57210 {{FINAL}}`: {{DIFFSTAT}} |
| Local checks on final code | {{LOCAL}} |

**Defects found by this round (all fixed, each with a test that failed first)**

| # | Defect | How it was found | Fix | Regression test |
|---|---|---|---|---|
| B1 | During a verification-code wait, the review page's package read re-settled the application from `needs_user_action` to `awaiting_approval` while the approval was still valid. **Submit was re-enabled after the data had been sent**, and the worker crashed on an illegal transition. | browser test (code flow) | `package.execution_owns_state`: no re-settling and no user transitions (409) while a worker holds the attempt | `test_reads_and_user_actions_during_code_wait_cannot_reopen_submission`; e2e reload during the code wait |
| B2 | A submit POST was sent **twice**. The in-process route used `route.fetch` + `fulfill`; when the worker gave up and closed the browser, Playwright resumed the paused original request. The receiver counted 2 acceptances for 1 attempt. | browser test (unknown outcome); reproduced with a stand-alone script | non-idempotent requests go out once via `continue_()` (hops checked by the egress proxy); a failed GET fetch aborts | `test_closing_the_browser_mid_submit_never_resends[netns,off]` |
| B3 | Submission card re-fetched attempts in a tight loop (the effect depended on its own result) and left the status stale after the final state (Cancel button still shown) | browser test | poll only while an attempt is active; refresh the application once at the end | e2e: no attempt requests in 4 s after the final state; no Cancel button after `unknown` |
| B4 | e2e worker supervisor started Celery in its own session, so Playwright's teardown left the worker running | stale processes after a run | worker stays in the supervisor's process group | — (harness) |
| B5 | CI run #2 Phase A failure: the test filled the login form's identically labelled fields during a slow client-side navigation to /register | reproduced deterministically with a 1.5 s route delay | wait for the URL and the register button before filling | `navigation-race.spec.ts` |

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
| CI #2 investigation | `navigation-race.spec.ts` | real slow navigation (route delay) | root cause B5; no retries or sleeps added |
| Docker smoke | CI job `docker-smoke` (`scripts/docker-smoke.sh`) | real Docker on GitHub's runner | {{DOCKER}} |

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
| Docker | `docker-compose.yml` | CI `docker-smoke` | see the milestone table above | no Docker daemon in this sandbox |

## Not credited

- REA: only `--help` was run; no analysis.
- Tsenta, Gmail, Freehire, LLM providers: no access, no implementation, no tests.
- Execution UI: browser-tested in milestone 2 (above).
- Greenhouse or any other real ATS: proposal only (`docs/first-adapter-proposal.md`).
