# Evidence matrix (Phase C validation)

Baseline before this work: commit `58ac9ea` (clean tree apart from an untracked Redis
`dump.rdb`, since git-ignored), 95 backend tests passed, ruff clean. Environment: cloud sandbox,
Python 3.12.3, PostgreSQL 16.15, Redis 7.0.15, Celery 5.6.3 / kombu 5.6.2 / redis-py 6.4.0
(prefork pool), SQLAlchemy 2.0.55, FastAPI 0.149.0, Alembic 1.20.0, Playwright 1.56.0 (Python)
with Chromium 141.0.7390.37, Node 22.22.0, Next.js 15.5.4.

"Oracle" = the synthetic receiver's own SQLite ledger (`fixtures/ats_receiver`), which shares
no code or database with NoEfforts. "Mock" marks anything simulated.

## A daily check of a job board you choose (D96, 2026-10-31; local stand-ins only)

Tests are in `test_board_daily_check.py`; the oracle for requests is the stand-in's ledger.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Your choice per board; off until chosen | `daily_check`; `board_sync.due` | `test_nothing_is_read_on_its_own_until_you_choose_it_for_a_board` | pass | — |
| Once a day, through the D95 boundary | `check_due` calls `sync` | `test_a_daily_board_is_read_once_a_day_through_the_same_boundary` (ledger: GET only, no cookie, credential or body) | pass | — |
| Never while off, paused, backing off or turned off | `due` filters and `sync` refusals (two layers) | `test_not_when_boards_are_off_paused_backing_off_or_turned_off`, `test_a_failed_daily_read_changes_nothing_and_backs_off` | pass | — |
| New postings noticed, never a job or an email | `notifications/service._boards`; `baseline_at` | `test_new_postings_after_the_first_read_are_one_notice_a_day_never_a_job`, `board-sources.spec.ts` | pass | — |
| Limit per account; account isolation | `daily_check_limit`; scoped queries | `test_the_daily_limit_and_another_account`, `test_every_query_of_the_feed_is_scoped_to_the_account` | pass | — |
| A board being read is skipped | the row lock (`NOWAIT`) | `test_a_board_its_owner_is_reading_is_skipped` | pass | — |
| Export and audit | export columns; `daily_check_on/off`, `daily_check` | `test_your_choice_is_exported`, the once-a-day test (audit) | pass | — |
| Sabotage | 11 single changes, 3 double | 8 caught alone, 3 caught with both layers removed (`implementation-status.md`) | pass | — |

## Employer job boards (D95, 2026-10-30; local stand-ins only, no real board read)

The oracle is the stand-in's own request ledger (`board_requests` in the receiver's SQLite,
`fixtures/ats_receiver/board_feeds.py`): method, path, query, whether a cookie, an
`Authorization` header or a body came. Boards and postings are fictional. Tests are in
`test_board_sources.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Off by default; explicit per-board activation | `board_sources_enabled`; `POST /discovery/sources`; "Read now" | `test_off_by_default_nothing_is_read`, `board-sources.spec.ts` | pass | — |
| A board is an identifier, never a URL | `boards.check_identifier`, encoded path | `test_a_board_is_an_identifier_never_a_url` (URL, `../`, space, unknown provider, unknown region: 400, no request) | pass | — |
| Fixed hosts, HTTPS, public addresses at connect, no redirects | `urlsafety.public_https_opener`, `_NoRedirect` | `test_the_public_opener_refuses_other_hosts_plain_http_and_private_addresses`, `test_outside_tests_the_fixed_public_host_is_used_never_an_override`, the `redirect` case of `test_a_failed_read_changes_nothing_and_backs_off` | pass | the real hosts were never contacted |
| GET only; nothing of the user sent | fixed headers, no cookie jar | `test_a_greenhouse_board_is_read_once_with_nothing_of_yours` (ledger: one GET, no cookie, no credential, no body), `board-sources.spec.ts` (same, through the UI) | pass | — |
| Documented paging and completeness | Greenhouse `meta.total`; Lever short page | `test_a_lever_board_is_paged_until_a_short_page`, `test_only_a_complete_read_says_a_posting_is_no_longer_listed`, `test_an_incomplete_read_never_marks_anything_closed` | pass | completeness rules are inferred from the docs (`docs/research/job-board-apis.md`) |
| Failures, limits, rate limiting, backoff | `BoardError` codes, `backoff`, size cap, `next_allowed_at` | `test_a_failed_read_changes_nothing_and_backs_off` (404, 503, 429 with Retry-After, redirect, oversize, not JSON, Lever page 2 failing), `test_backoff_is_bounded`, `test_two_reads_of_one_board_at_once_are_refused` | pass | no rate limit is documented for either read API |
| Normalization, malformed and missing values | `boards.normalize` | `test_malformed_records_are_skipped`, the two read tests | pass | — |
| Malicious descriptions and links | `plain_summary`, `_safe_url`, links never fetched | `test_untrusted_content_and_links_are_neutralised` (script, `onerror`, `javascript:`, `data:`, metadata and loopback links) | pass | — |
| Duplicates: repeated reads, saves, other sources | one row per board and posting id; `service._existing_job` | `test_repeated_reads_never_duplicate`, `test_a_posting_is_saved_once_and_reconciled_with_your_existing_jobs` | pass | — |
| Pause, resume, rename, remove | `PATCH`, `DELETE` | `test_pause_resume_rename_and_remove`, `board-sources.spec.ts` | pass | — |
| Account isolation | `user_id` on every query; 404 | `test_another_account_never_reaches_your_boards` | pass | — |
| Discovery never touches applications | reads and saves only jobs and discovered rows | `test_discovery_never_creates_an_application_route_or_approval` | pass | — |
| Export, deletion, audit, logs | `board_sources` exported; cascades; audit codes only | `test_export_deletion_audit_and_logs_keep_board_data_where_it_belongs`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Owner settings reach the containers (D94 fix) | `docker-compose.yml` pass-throughs | `test_every_owner_setting_in_the_example_reaches_the_api_and_the_worker` (`test_deployment_config.py`); `docker compose config` with a synthetic `.env` | pass | not run on the owner's machine |
| Sabotage | 12 guards | each caught (`implementation-status.md`) | pass | — |

## Email reminders to the owner (D94, 2026-10-30; local SMTP sink only)

The oracle is the sink's own ledger (`fixtures/ats_receiver/mail_sink.py`), which shares no code
or database with NoEfforts. Tests are in `test_email_reminders.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Off by default; opt-in needs a verified address | `config_problem`, `set_enabled`, `verify_code` | `test_off_by_default_nothing_is_ever_sent`, `test_turning_it_on_needs_a_verified_address_entered_in_the_app`, `test_codes_expire_run_out_and_are_limited_and_addresses_are_checked`, `email.spec.ts` | pass | — |
| Minimal content, safe link, owner only | `digest_message`; recipient from settings only | `test_the_digest_says_only_the_category_and_links_to_the_tracker`, `test_nothing_is_ever_emailed_to_anyone_but_the_verified_owner`, `email.spec.ts` | pass | — |
| Categories, daily digest, deduplication | `digest_items`, dedupe key, emailed keys | `test_attention_items_are_their_own_category_and_choices_are_respected`, `test_one_digest_a_day_and_no_item_is_put_in_a_second_digest`, `test_an_item_read_in_the_app_is_not_emailed`, `test_before_the_hour_nothing_is_sent` | pass | — |
| Opt-out, new address, deletion before dispatch | `cancel_pending`; re-check at claim | `test_opting_out_or_removing_the_address_before_dispatch_cancels`, `test_a_new_address_needs_verifying_again_and_cancels_what_is_pending`, `test_deleting_the_account_before_dispatch_sends_nothing` | pass | an accepted message cannot be recalled |
| Duplicate workers, fencing, recovery | lock + skip-locked claim, `generation`, `recover_stale` | `test_two_workers_for_one_delivery_send_it_once`, `test_a_late_result_after_recovery_is_fenced`, `test_a_worker_lost_while_sending_leaves_it_uncertain` | pass | — |
| Refusal, timeout, uncertain acceptance | `SmtpTransport` classification; bounded retries | `test_a_definite_transient_refusal_is_retried_a_bounded_number_of_times`, `test_a_refusal_then_acceptance_is_sent_once`, `test_a_permanent_refusal_fails_and_is_not_retried`, `test_a_refused_connection_is_a_definite_failure`, `test_a_possible_acceptance_is_uncertain_and_never_resent` | pass | not exactly-once: NoEfforts never resends an uncertain message, but neither it nor SMTP can rule out a duplicate further down the delivery chain |
| No application change; no follow-up marked done | reminders read only | `test_reminders_never_change_an_application_or_mark_a_follow_up_done`, `email.spec.ts` | pass | — |
| Isolation, tokens, privacy of logs, audit, export | `session_only`; sanitized logs; export lists | `test_another_account_and_api_tokens_never_reach_your_email_settings`, `test_logs_and_audit_keep_no_address_code_or_message_and_the_export_keeps_your_settings`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Configuration checked before sending | `config_problem` | `test_the_configuration_is_checked_before_anything_is_sent` | pass | — |
| Honest validation exit codes | `scripts/validate.sh` | `scripts/test_validate.sh` (CI docker-smoke job) | pass | — |
| Sabotage | 13 guards | each caught (`implementation-status.md`) | pass | — |

## Freehire signals, display-only (D93, 2026-10-30; fixture only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Only the documented fields, each with its type | `provider.freehire_signals` | `test_reality_is_read_field_by_field_with_its_documented_type_and_nothing_else` | pass | the fixture's shapes stand in for Freehire's reference |
| Worded in the source's terms, attributed | `provider.describe_signals`; Discover; job page | `test_signals_are_described_in_the_sources_terms_without_a_verdict`, `test_the_listing_and_the_job_page_show_what_freehire_says`, `discovery.spec.ts` | pass | — |
| Refreshed without counting as a change | stored in `normalized`, outside the fingerprint | `test_signals_refresh_on_every_read_without_counting_as_a_change`, `test_counters_and_reality_ticking_are_not_a_change` | pass | — |
| Never an input | code scan of every reader | `test_signals_never_reach_matching_approval_routing_or_execution` | pass | — |
| Sabotage | 4 guards | each caught (`implementation-status.md`) | pass | — |

## Follow-ups (D92, 2026-10-30; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Only after a submission; due after the set days, a chosen day, or from an interview's day | `followups/service.py` `evaluate` | `test_nothing_to_follow_up_before_the_application_is_submitted`, `test_due_seven_days_after_you_applied_and_notified_then`, `test_the_days_are_the_owner_setting`, `test_remind_me_on_a_day_you_choose_within_a_year`, `test_an_interview_you_recorded_starts_the_wait_from_its_day` | pass | — |
| Your actions: done, a day, stop, resume; closed by an outcome | `POST /applications/{id}/follow-up` | `test_saying_you_followed_up_starts_the_next_wait_and_a_new_notification`, `test_stopping_the_reminders_and_resuming_them`, `test_an_outcome_that_closes_the_application_ends_the_reminders`, `test_every_closing_outcome_closes_it`, `follow-ups.spec.ts` | pass | — |
| Due is notified in the app; nothing is sent | `notifications/service.py` `_follow_ups` | the same tests; `follow-ups.spec.ts` | pass | no outside delivery (row 8) |
| The message uses the job, the day and your approved name only | `followups/service.py` `draft` | `test_the_message_uses_the_job_your_approved_name_and_nothing_else_of_yours`, `test_without_a_name_the_message_says_where_yours_goes` | pass | — |
| Account isolation, CSRF, token scope | `_owned`, scoped queries, the `read` allow-list | `test_another_account_never_sees_or_changes_your_follow_up`, `test_a_change_needs_the_csrf_token`, `test_a_read_token_lists_follow_ups_but_never_reads_the_message_or_changes_one`, `follow-ups.spec.ts` | pass | — |
| Audit, export, deletion | `follow_up.update`; `follow_ups` exported; cascades | `test_your_choices_are_audited_by_action_only_and_exported_with_the_account`, `test_deleting_the_application_or_the_account_deletes_your_choices`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Sabotage | 9 guards | 7 caught alone; 2 double layers caught together (`implementation-status.md`) | pass | — |

## Capture-only browser extension (D90, 2026-10-30; local only, Chromium)

The extension (`extension/`) is loaded unpacked into Playwright's Chromium in
`frontend/e2e/extension.spec.ts` (desktop project), against the real web app and API. Postings
are the local receiver's fictional pages; accounts are synthetic.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Least permissions: no page access, NoEfforts on this machine only | `manifest.json`: `activeTab`, `storage`, loopback host permissions, no content scripts | "the extension asks for the least" (manifest and code checked statically) | pass | — |
| Sends the address (no fragment) and title only, with the token, never the browser's cookies | `lib.js` `checkTab`, `saveJob` (`credentials: "omit"`, `redirect: "error"`) | "what is sent" (the request as made, through a stand-in `fetch`) | pass | — |
| Only plain http to 127.0.0.1 or localhost | `checkBase` | "what is sent" (nine addresses) and the options test | pass | — |
| Keeps only an `import:jobs`-only token NoEfforts accepts; never shows it; drops it when the address changes | `checkToken` (`GET /api/token`), `options.js` | "options keep only a token..." (a `read`+`import:jobs` token, an unknown token, a good token, an address change) | pass | — |
| Saves the tab's job once to the token owner's account, not the signed-in browser session's | `background.js` → `POST /api/jobs` | "a fictional posting's tab is saved..." (owner's list has it once with its title; the bystander signed in in that browser does not) | pass | — |
| Cannot read a tab you did not click its button on; refuses a non-web page | `activeTab` only; `checkTab` | "a tab you did not click the button on is never read..." | pass | the `activeTab` grant by a real toolbar click is not automatable in Playwright |
| Sabotage | 7 guards broken one at a time | each caught (`implementation-status.md`) | pass | — |

## Installable web app with an offline page (D89, 2026-10-30; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Installable: manifest, icons, a service worker | `public/manifest.webmanifest`, `layout.tsx`, `public/sw.js` | `pwa.spec.ts` "the app can be installed" (desktop and mobile) | pass | install prompt itself not automated |
| Offline, a page load shows the offline page | `sw.js`: network first for page loads, `offline.html` only when that fails | `pwa.spec.ts` "offline, a page shows the offline page" | pass | — |
| Nothing about you is kept on the device | the worker caches `offline.html` and one icon, nothing else | the same test: after browsing four pages signed in, the caches hold exactly those two files | pass | — |
| The image serves it | `frontend/Dockerfile` copies `public/` | `scripts/docker-smoke.sh` (manifest, offline page) in CI `docker-smoke` | CI | not run in the sandbox (no Docker daemon) |
| Sabotage | 2 guards broken (cache pages; no offline fallback) | each caught (`implementation-status.md`) | pass | — |

## Workday-style adapter against the local receiver (D88, 2026-10-30; local only, checkpoint-first)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Workday-style approximation only, never with a real Workday tenant. Tests are in
`test_workday_adapter.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Account, password and verification steps are checkpoints | password inputs unsupported; `blocked_reason`; verification after the click is unknown | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints`, `test_an_account_gate_or_several_pages_after_approval_stop_before_disclosure`, `test_email_verification_after_the_final_click_is_a_hard_stop`, `workday.spec.ts` | pass | — |
| Several pages are a checkpoint | `multi_step` field at capture; `blocked_reason` | the same tests, `workday.spec.ts` | pass | page-by-page disclosure not built |
| A challenge on the page is a checkpoint, never solved (added after CI #127) | `bot_check` field at capture; `blocked_reason`; registry claims `captcha_checkpoint` | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints[wd_challenge-bot_check]`, `test_a_challenge_that_appears_after_approval_stops_before_disclosure`, `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one` | pass | Workday documents no challenge; the mode is fixture design |
| Résumé-parsing prefill is never trusted | `prefilled_values` at capture; readback of unanswered fields | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints`, `test_resume_parsing_is_never_trusted_without_readback` | pass | — |
| Complex location fields and custom dropdowns are checkpoints | dependent lists read as unsupported pickers; ARIA widgets unsupported | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints` | pass | — |
| Approved values, byte-identical documents | `fixture_workday` fill and upload (hosted-form base) | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `workday.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits; submission needs its own approval | the existing rehearsal stop and scopes | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `workday.spec.ts` | pass | — |
| No duplicate send; an uncertain send is quarantined | claim fencing; unknown outcome | `test_a_duplicate_delivery_never_submits_twice`, `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_workday-*]` | pass | — |
| Upload evidence kept after a partial failure | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Changed inputs cancel the approval; drift stops | package versioning; fingerprint | `test_a_changed_approved_input_invalidates_the_approval`, `test_form_changed_after_approval_stops_before_disclosure` | pass | — |
| Off-site pages and redirects stop; the confirmation is bound | runner same-origin check; egress; `_bound` | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered`, `test_confirmation_bound_to_attempt` | pass | — |
| Real Workday stays a manual handoff | no Workday identity; planned `workday` | `test_a_real_workday_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `workday.spec.ts` | pass | — |
| Sabotage | 8 guards broken one at a time, then 2 for the challenge stop | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Ashby-style adapter against the local receiver (D87, 2026-10-30; local only)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Ashby-style approximation only, never with a real Ashby posting. Tests are in
`test_ashby_adapter.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Approved values, byte-identical documents | `fixture_ashby` fill and upload (hosted-form base) | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `ashby.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits | the existing rehearsal stop | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `ashby.spec.ts` | pass | — |
| Submission needs its own approval | approval scopes (unchanged) | the same tests (the rehearsal's approval is used up) | pass | — |
| A duplicate delivery never submits twice | claim fencing (unchanged) | `test_a_duplicate_delivery_never_submits_twice` (receiver non-idempotent) | pass | — |
| Upload evidence kept after a partial failure | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Unknown required controls block | capture as unsupported; drift check | `test_an_unsupported_required_control_or_the_spam_check_blocks_approval`, `test_form_changed_after_approval_stops_before_disclosure`, `test_unknown_sponsorship_blocks_approval` | pass | — |
| The spam check is a hard stop | bot-check field at capture; `blocked_reason`; unknown after the click | `test_an_unsupported_required_control_or_the_spam_check_blocks_approval`, `test_a_spam_check_that_appears_after_approval_stops_before_disclosure`, `test_the_spam_check_or_a_repeat_after_the_final_click_is_a_hard_stop`, `test_a_confirmation_page_that_also_shows_a_bot_check_is_not_a_confirmation` | pass | — |
| A page value nobody approved is never sent | readback of unanswered fields | `test_a_resume_autofill_that_changes_a_field_stops_before_submit` | pass | — |
| The cookie banner is never clicked | nothing outside the form is clicked | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `ashby.spec.ts` (no `cookie_choice` in the ledger) | pass | — |
| Changed approved inputs cancel the approval | package versioning (unchanged) | `test_a_changed_approved_input_invalidates_the_approval` | pass | — |
| An uncertain final send is quarantined, never retried | unknown outcome (unchanged) | `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_ashby-*]` | pass | — |
| Off-site pages and redirects stop | runner same-origin check; egress | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered` | pass | — |
| Real Ashby stays a manual handoff; fixture evidence enables nothing | no Ashby identity, no specification | `test_a_real_ashby_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `ashby.spec.ts` | pass | — |
| Sabotage | 10 guards broken one at a time | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Fixture-origin boundary (D86, 2026-10-30; local only)

Every public address below comes from a fake resolver; each check refuses before a connection
is opened, so nothing public was contacted. Tests are in `test_fixture_origin_boundary.py`
unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Single-label names only if listed exactly | `urlsafety.FIXTURE_SERVICE_HOSTS` (`receiver`) | `test_only_names_listed_exactly_are_fixture_hosts`, `test_an_unlisted_single_label_name_is_refused`, `test_lever_adapter.py::test_only_the_listed_compose_receiver_name_is_a_fixture_host` | pass | — |
| A listed name resolving publicly is refused | `connect_fixture` (every resolved address); egress proxy `check_destination` | `test_a_listed_name_resolving_to_a_public_address_is_refused_before_connecting`, `test_a_listed_name_is_read_only_while_it_resolves_locally`, `test_execution_through_a_listed_name_follows_where_it_resolves`, `test_the_proxy_refuses_a_fixture_name_resolving_outside_the_test_network` | pass | — |
| The address actually connected to is checked | `connect_fixture` peer check; proxy peer check before relaying | `test_the_address_actually_connected_to_is_checked_again`, `test_the_proxy_checks_the_peer_it_actually_reached` | pass | — |
| Test networks are narrow and private | `parse_fixture_networks`; Settings validator; proxy service startup | `test_a_test_network_must_be_a_narrow_private_network`, `test_test_networks_must_be_given_as_a_list`, `test_the_proxy_service_takes_its_own_test_network_and_refuses_a_wide_one` | pass | — |
| Redirects refused, every hop checked | fixture opener follows none and checks each request's origin; browser hops through the proxy | `test_the_opener_never_follows_a_redirect`, `test_every_request_the_opener_makes_is_checked_by_origin`, `test_a_capture_redirect_off_the_fixture_is_never_followed`, `test_lever_adapter.py::test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered` | pass | — |
| Outside the test environment, refused | `is_fixture_origin` needs `env == "test"` | `test_fixture_origins_are_refused_outside_the_test_environment` (development, staging, production) | pass | — |
| Other spellings of an address; IPv6 loopback and mapped forms | standard-form literals only; `_legacy_ipv4` in `check_url_syntax` | `test_other_spellings_of_a_loopback_address_never_count`, `test_other_spellings_of_a_public_address_are_public_not_fixtures`, `test_ipv6_loopback_and_mapped_forms`, `test_fixture_addresses_are_loopback_or_on_the_test_network` | pass | — |
| A fixture is never browsed without the egress proxy | `browser_session` refuses `isolation=off` (`fixture_needs_proxy`) | `test_a_fixture_is_never_browsed_without_the_egress_proxy` | pass | — |
| In `netns` mode every connection leaves through the proxy | driver never fetches or connects (was: GET/HEAD and WebSockets from the driver) | probe (no proxy decision for the destination with interception on, before the fix); `test_in_netns_mode_the_page_load_itself_passes_the_egress_proxy`, `test_execution_through_a_listed_name_follows_where_it_resolves` (refused at the proxy) | pass | — |
| Compose execution still works | `fixtures` pinned to `10.231.47.0/24`, `NOEFFORTS_ENV=test` on the API and worker, test network on API, worker and proxy | CI `execution-compose` on the commit (no Docker daemon in this sandbox) | see `implementation-status.md` | not run locally |
| Sabotage | 14 guards broken one at a time | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Lever-style adapter against the local receiver (D85, 2026-10-30; local only)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Lever-style approximation only, never with a real Lever posting.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Approved values, byte-identical documents | `fixture_lever` fill and upload | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `lever.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits | the existing rehearsal stop | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `lever.spec.ts` | pass | — |
| Submission needs its own approval | approval scopes (unchanged) | the same tests (the rehearsal's approval is used up) | pass | — |
| A duplicate delivery never submits twice | claim fencing (unchanged) | `test_a_duplicate_delivery_never_submits_twice` (receiver non-idempotent) | pass | — |
| A partial upload failure keeps earlier disclosures' evidence | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Unknown required controls block approval or execution | capture as unsupported; drift check | `test_a_required_picker_or_a_bot_check_on_the_form_blocks_approval`, `test_form_changed_after_approval_stops_before_disclosure`, `test_unknown_authorization_blocks_approval` | pass | — |
| A page value nobody approved is never sent | readback of unanswered fields | `test_a_parsed_resume_that_changes_a_field_stops_before_submit` | pass | — |
| Changed approved inputs invalidate authorization | package versioning (unchanged) | `test_a_changed_approved_input_invalidates_the_approval` | pass | — |
| An uncertain final send is quarantined, never retried | unknown outcome (unchanged) | `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_lever-*]` | pass | — |
| Real Lever stays a manual handoff; fixture evidence enables nothing | no Lever identity; planned `lever` | `test_a_real_lever_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `lever.spec.ts` | pass | — |
| The app never calls it live support | labels from `providers/wording.py` | `test_the_app_never_calls_this_live_support` | pass | — |
| No hostname, redirect or configuration escape | runner same-origin check; egress; local fixture hosts | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered`, `test_listing_a_public_site_as_a_fixture_never_makes_it_one` | pass | — |
| Sabotage | 7 guards broken one at a time | each caught, restored by MD5 | pass | — |

## API tokens, CLI and MCP (D84, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Displayed once, never stored in plaintext | `apitokens.service.create` keeps the SHA-256 only | `test_a_token_is_shown_once_and_only_its_hash_is_kept`, `api-tokens.spec.ts` (gone after "I have copied it" and a reload) | pass | — |
| Expires by default | 30 days default, 1-90 enforced | `test_a_token_always_expires_and_has_known_scopes`, `test_expired_revoked_and_unknown_tokens_read_the_same` | pass | — |
| Revocable, effective at once | `revoked_at`; checked on every request | the same test, `api-tokens.spec.ts` (401 after revoke) | pass | — |
| Scope enforcement, default deny | allow-list per scope in `current_user` | `test_every_route_outside_a_scope_refuses_the_token_before_doing_anything` (every route, both scopes, nothing audited), `test_no_scope_reaches_review_consent_approval_submission_or_your_facts`, `test_an_import_token_adds_a_job_and_nothing_else` | pass | — |
| Session-only for management, export, deletion | `session_only` | `test_session_only_routes_refuse_a_token_even_next_to_a_valid_session` | pass | — |
| Tenant isolation | a token resolves to one user | `test_a_token_reads_its_own_account_only` | pass | — |
| Log redaction | access log by template; no header logged | `test_no_log_line_carries_a_token`, `test_against_a_real_server_the_cli_and_mcp_work_and_no_output_shows_the_token` (uvicorn, CLI and MCP subprocesses) | pass | — |
| Your facts stay in the app | job read by token without eligibility | `test_a_token_reads_a_job_without_the_eligibility_that_shows_your_facts` | pass | Match summaries still name your approved skills and licences the job mentions (documented) |
| No surface bypasses review, consent or approval | no such CLI command or MCP tool; API refuses tokens there | `test_the_mcp_server_offers_read_tools_and_never_a_way_to_apply`, the route sweep | pass | Not tried with a third-party MCP client |
| Sabotage | 8 guards broken one at a time (scope check, expiry, hash comparison, plaintext stored, rate limit, session-only, cookie fallback, eligibility hiding) | each caught, restored by MD5; the hash comparison was missed at first (the tampered token was a revoked one), and a tampered active token was added | pass | — |

## In-app notifications (D83, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Truthful: a notification says what its record says now | `notifications/service.py` derives each one from checkpoints, approvals, rehearsal records and attempts every time | `test_a_failure_says_what_happened_and_never_promises_a_retry` (real unknown and rejected outcomes), `test_a_verification_code_request_needs_you_until_it_ends` (simulated rows) | pass | Expired approvals (not invalidated) are not notified |
| Deduplicated: one per record | keyed by the record; a used-up approval and a rehearsed attempt are not notified apart from their rehearsal | `test_a_rehearsal_is_one_notification_not_three`, `test_a_receipt_is_notified_once_with_its_evidence_class_and_a_link` | pass | — |
| Nothing you did yourself is news | approvals you revoked and attempts you cancelled are left out | `test_an_approval_that_stops_applying_is_notified_but_not_one_you_revoked`, `test_nothing_is_notified_for_what_you_cancelled` | pass | A package you changed yourself still notifies the approval it ended (on purpose: it no longer applies) |
| Tenant-scoped read state | `notification_reads`; another account's key is 404 and nothing is marked | `test_read_marks_are_yours_and_another_account_cannot_see_or_touch_them`, `test_every_query_of_the_feed_is_scoped_to_the_account` | pass | — |
| No delivery outside the app | no mail, network or task library in the module; used by its own routes only | `test_nothing_in_notifications_can_send_anything_anywhere` | pass | — |
| Exported and deleted with the account | export inventory; FK cascade | `test_read_marks_are_exported_and_deleted_with_the_account`, `test_d83_adds_notification_reads_and_downgrade_drops_only_them` | pass | — |
| In the browser: receipt and invalidated approval, read/unread, links, per account | `notifications/page.tsx`, header count | `notifications.spec.ts` (desktop, mobile) against the real worker and receiver | pass | — |

## Jobs-list match summary (D82, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| The list and the job page cannot disagree | `fit.summary(fit.assess(...))` | `test_the_jobs_list_summarises_the_same_assessment_and_hides_nothing` | pass | — |
| No score, verdict or probability; eligibility not summarised | summary keys fixed | `test_the_summary_says_nothing_about_eligibility`, `test_no_text_calls_it_a_prediction_a_score_or_a_verdict`, `match-summary.spec.ts` word checks | pass | — |
| A job without text is "not compared", not "names none" | `compared` flag | `test_a_job_without_text_is_not_compared_rather_than_naming_nothing` | pass | — |

## Workday and Ashby shapes, embeds, credentials, custom widgets (D81, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| An account gate is never passed for the user; no password is asked for or kept | password and one-time-code inputs unsupported | `test_workday_account_gate_and_traps_are_never_filled`, `test_a_credential_input_is_never_a_text_field` | pass | — |
| An unknown required question is never dropped | ARIA widgets without native input → unsupported | `test_a_required_custom_widget_blocks_instead_of_disappearing` (4 widgets), the two fixture tests, `test_a_visible_listbox_owned_by_a_combobox_is_part_of_that_control` | pass | Widgets with no ARIA role at all stay invisible to the extractor (a page script, a canvas) |
| Ashby embeds are recognised, fail-closed | `detect_ats` | positive (3), malformed (4), ambiguity and host-precedence tests, the gap probe | pass | The any-host trust is a recorded gap |
| Sensitive and legal questions on these shapes are never answered for the user | resolver (unchanged) | the two fixture tests | pass | — |
| The owner's verification returns only safe output | `verify-local.sh` summary | `test_verify_local_reports_each_step_and_never_a_value`, `test_verify_local_ends_with_a_safe_summary_when_docker_is_missing` | pass | The Mac run itself is pending |

## Lever-shaped form, checkpoint-first (D80, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| A search-as-you-type picker is never filled as text | `forms.extract_form_schema` (combobox, aria-autocomplete → unsupported) | `test_every_documented_trap_is_a_checkpoint_or_a_blank`, `test_words_alone_are_not_a_bot_check_and_a_plain_input_is_not_a_combobox` | pass | — |
| A CAPTCHA is never solved; the user applies themselves | bot-check field on the generic capture path | `test_the_bot_check_blocks_approval_even_when_everything_else_is_answered`, `test_a_bot_check_is_found_by_its_documented_markup` (6 markups) | pass | The Greenhouse paths rely on their adapters' stop (unchanged) |
| Lever traps from the research are checkpoints | `fixtures/lever.html` | `test_lever_fixture.py` | pass | Shapes search-reported, not observed |
| Unknown authorization stays unknown | resolver (unchanged) | `test_unknown_authorization_stays_unknown` | pass | — |

## Export, deletion, saved-answer editing, preview, explainable match (D77-D79, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Export is complete and scoped to the account | `account/export.py` (explicit column lists) | `test_the_export_holds_everything_of_the_account_and_nothing_of_another`, `test_every_table_and_column_has_an_export_decision`, `account.spec.ts` | pass | — |
| Export holds no secret or keyed material | column and JSON-key exclusions, keyed-reference scrubber | `test_the_export_holds_no_secret_and_no_keyed_material`, `test_the_scrubber_leaves_out_keyed_values_inside_json` | pass | — |
| Deletion removes every row, file and session of the account only | cascade from `users` (checked in the migrated database), files after commit | `test_every_table_that_names_an_account_is_deleted_with_it`, `test_deletion_removes_every_row_file_and_session_of_the_account_only`, `account.spec.ts` | pass | Not run against a real account (by instruction) |
| Deletion never causes a resubmission | refused past the send gate; pending work deleted; a holding worker fenced out | `test_deletion_is_refused_while_a_submission_may_be_in_flight`, `test_queued_work_stops_a_pending_attempt_and_its_message_do_nothing`, `test_a_worker_holding_an_attempt_is_fenced_out_and_never_sends`, the two gate races | pass | — |
| Retention is a decision, not invented policy | `account/policy.py` | `test_the_deletion_document_lists_exactly_the_reason_codes_and_policy` | default: nothing kept | Owner decision open |
| A saved-answer edit keeps provenance and history and invalidates approvals | `preparation/bank_edit.py` | `test_an_edit_is_a_new_version_and_the_application_asks_for_approval_again`, `test_the_history_keeps_every_version`, `test_every_protected_mutation_stops_a_running_attempt[answer_bank_edit]`, `answers-edit.spec.ts` | pass | — |
| Preview introduces no external service or active content | text as JSON, shown in a `<pre>` | `test_the_preview_is_the_text_as_data_never_the_file`, `answers-edit.spec.ts` (markup shown, not run; no request off the machine) | pass | — |
| Match explained by component, unknown stays unknown, never a probability | `jobs/fit.py` | `test_fit.py` (each result, side-by-side eligibility, qualifications from approved facts, the wording scan, the job page API) | pass | No jobs-list summary yet |

## Owner deployment readiness (D76, 2026-10-29; sandbox CLI and CI only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Compose refuses to start without its secrets | `${VAR:?}` for `AUDIT_REF_KEY`, `BROWSER_RUNNER_TOKEN`, `EGRESS_CONTROL_TOKEN` | `docker compose config` exit 1 without `AUDIT_REF_KEY` (sandbox); `test_every_required_compose_variable_is_in_the_example_and_the_checker` | pass | — |
| Secrets checked before start, never printed | `scripts/check_env.py` | `test_the_example_file_is_refused_until_its_secrets_are_set`, `test_a_good_file_passes_and_no_value_is_printed`, `test_a_bad_file_fails_without_printing_its_values`, `test_reused_secrets_missing_keys_and_outbound_switches` | pass | Not run on a Mac's system `python3` |
| Nothing reachable from another machine | every published port on 127.0.0.1 | `test_every_published_port_is_bound_to_this_machine_only`; rendered `docker compose config` | pass | — |
| Worker and web app never start before migrations finish | API health check; `depends_on: service_healthy`; `alembic upgrade head && uvicorn` | `test_the_worker_and_web_app_start_only_once_the_api_is_healthy`; probe exit 1 with no API, 0 with one, even with a dead proxy configured | pass in the sandbox | CI `docker-smoke` exercises it in real containers |
| Backup and rollback restore the data from before the backup, and nothing after | `docs/deployment.md` sections 5 and 7 | CI `docker-smoke`: back up, second account, drop and restore, first session works, second login 401 | see implementation-status for the CI run | Not run on the owner's machine |
| Backups never committed | `.gitignore` `backups/`; hygiene rule for `backups/` and `.dump` | `test_backups_are_never_committed`, `test_the_rules_catch_what_they_are_for` | pass | — |
| Runs on the owner's Mac | `docs/deployment.md` section 10, `scripts/verify-local.sh` | — | **not run** | Needs the owner to run it |

## One synthetic journey through the whole product (D75, 2026-10-29; local only)

Synthetic data, the receiver's stand-in of Freehire's documented API, and the independent
receiver; its ledger is the oracle. `frontend/e2e/journey.spec.ts`, desktop and mobile.

| Requirement | Step in `journey.spec.ts` | Result |
|---|---|---|
| Facts and preferences apart | "register; facts and preferences are kept apart" | work authorization per country; preferences on their own page |
| Proposed facts used only once approved | "a resume proposes facts" | 1 work and 1 education entry proposed, approved one by one |
| Normalization and dedupe | "discovery: normalized, deduplicated, never re-added" | the source's repeated listing links to the same job; a second search adds nothing |
| Preference review apart from eligibility | "job page: preferences explained apart from eligibility" | title and location reasons; "says nothing about eligibility or sponsorship" |
| Unknown becomes a checkpoint | "what is unknown is asked" | 3 questions asked; approval disabled until answered |
| Tailored material reviewed before use | "a tailored resume is read, accepted and chosen" | cited facts shown; offered at once after accepting (fixed) |
| Disclosure-only rehearsal | "a rehearsal fills and checks, and never submits" | ledger: +1 upload, +0 acceptances |
| Stale approvals invalidated | "a separate approval to submit; a fact changed after it invalidates it" | "Approval invalidated", the change shown, submit disabled until approved again |
| Versions consistent | "what arrived is what was approved, exactly once" | ledger: the new phone, the user's answer, the tailored DOCX's SHA-256; attempts `confirmed`, `rehearsed` |
| No blind resubmission | "no blind resubmission" | the same application reopens; queueing again refused; still 1 acceptance |
| Receipt, tracker, outcome timeline | "tracker: receipt, timeline and an outcome" | receipt-sourced state; link back to the application (fixed); outcome on the timeline |
| Fixtures never make a real destination ready | "fixture evidence never makes a real destination ready" | `real_destination_disabled`; no test-only form control (fixed) |

## Claude as the drafting provider, built and off (L4, 2026-10-29; local only, no request to Anthropic)

A stub SDK client (returning the SDK's own `Message` type) and a stub resolver stand in for
Anthropic's API and DNS; no key exists and nothing was sent. Decision D74.

| Requirement | Evidence | Result |
|---|---|---|
| Off unless the owner configures it | `tests/test_drafting_provider.py::test_off_unless_the_owner_configures_it`, `::test_without_a_provider_nothing_changes` | no provider without `anthropic`, NoEfforts' own key and a priced model; an ambient `ANTHROPIC_API_KEY` is ignored; 503 as before |
| The client: the server's key, no retries | `::test_the_client_uses_only_the_servers_key_and_never_retries`, `::test_the_key_never_reaches_a_response` | `max_retries=0`; the key is in no response and no settings dump |
| Owner account and consent to the exact text | `::test_a_draft_needs_the_owners_account_and_consent_to_this_text`, `::test_another_account_is_refused_and_one_consent_never_covers_another`, `::test_a_changed_consent_text_needs_a_new_agreement` | 409 `drafting_consent_needed`, 503 `drafting_not_for_this_account`, 409 `consent_text_changed`; nothing sent before consent or after withdrawal; audit by digest |
| Every sending provider is gated | `::test_every_provider_class_in_the_app_declares_whether_it_sends_anything_out`, `::test_an_unbound_provider_never_sends` | the one class sets `external = True`; an unbound one refuses |
| The request | `::test_the_request_is_the_rules_and_one_json_message_with_no_sampling_or_tools` | the rules as the system prompt; one ASCII JSON user message with the approved facts; JSON output schema; effort `medium`; no sampling, thinking or tool fields |
| The budget | `::test_no_budget_sends_nothing`, `::test_a_request_whose_worst_case_does_not_fit_is_never_sent`, `::test_the_worst_case_is_reserved_before_sending_then_the_reported_cost_is_kept`, `::test_a_settled_request_frees_what_it_did_not_use`, `::test_concurrent_reservations_never_pass_the_budget_together` | reserved before sending, then the reported cost; 6 concurrent reservations with room for 2: 2 reserved |
| Failures keep nothing | `::test_a_failure_keeps_nothing_and_says_why` (9 cases), `::test_an_api_host_resolving_to_a_private_address_is_never_contacted`, `::test_a_provider_draft_is_checked_like_every_draft` | 502 with a fixed code; no draft stored; timeouts, unknown errors and (D97) error replies such as 500 and 400 keep the worst case as `unknown`; only a request refused before it left is `not_sent` at 0; a private address is never contacted; the draft checks still apply |
| Tailored documents | `::test_a_tailored_resume_goes_through_the_same_checks` | the same gates; `document.generation_failed` audited by code |
| Migration | `tests/test_migrations.py::test_l4_adds_drafting_consents_and_usage_and_downgrade_drops_only_them` | one consent per user and provider; rows deleted with the user; downgrade drops only them |
| In the browser | `frontend/e2e/drafting-consent.spec.ts` (desktop, mobile; a synthetic consent view) | not configured said; what is sent and never sent shown; agree and turn off; the review page links to the profile card |
| Sabotage | 17 cases (owner, consent version, withdrawal, budget, lock, reported cost, any version, timeout cost, destination check, `external`, key, retries, refusal, job text in the system prompt, reservation after sending, unbound use, the gate) | 17 caught; the race case caught in 5 of 5 further runs, and passes 8 of 8 when intact |

## Listings by application platform (D100, 2026-10-31; local only)

Synthetic listing addresses, parsed and never fetched. Decision D100.

| Requirement | Evidence | Result |
|---|---|---|
| An import keeps only the chosen platforms | `tests/test_discovery_platforms.py::test_an_import_keeps_only_the_chosen_platforms` | Greenhouse and Lever of five: 2 kept and added to jobs, 3 filtered out and not stored |
| Listed and counted by platform, per account | `::test_postings_are_listed_and_counted_by_platform` | counts per platform with labels; `?platform=` filters; an unknown name is 422; another account sees none |
| Known platforms only | `::test_the_import_route_takes_known_platforms_only` | an unknown platform 422; local fixture addresses are "Other or not recognised" |
| In the browser | `frontend/e2e/discovery-platforms.spec.ts` (desktop, mobile) | Greenhouse only: 5 filtered out, 0 added; Other: 5 added; the list's filter with counts; no sideways scroll |
| Sabotage | 4 cases | 4 caught |

## Saved answers imported from a file (D99, 2026-10-31; local only)

Synthetic rows only. Decision D99.

| Requirement | Evidence | Result |
|---|---|---|
| Each row judged by the saved-answer rules | `tests/test_bank_import.py::test_each_row_is_judged_by_the_rules_for_saved_answers` | 18 rows: 3 importable; protected, sensitive, template, employer, time, credential, place, long text, placeholder, conflict (both rows), duplicate, blank refused; a dry run writes nothing; no row text in the response |
| Proposals, never used until approved | `::test_imported_answers_are_proposals_until_approved`, `::test_a_proposal_answers_nothing_until_you_approve_it` | `import` / `proposed`; a yes/no answer bound to the options Yes and No; history "imported from a file"; a new application uses it only after approval; approving twice is 409; audit counts only |
| Nothing replaced; per account | `::test_nothing_already_saved_is_replaced`, `::test_another_accounts_proposal_is_not_found` | `already_saved`; another account's proposal 404 |
| Limits | `::test_limits` | 0 rows, more than 5,000 rows or a question over 2,000 characters: 422 |
| In the browser | `frontend/e2e/answers-import.spec.ts` (desktop, mobile) | a JSON file checked and one row added; "Approve"; a review sheet keeps only the rows marked yes or edit, with the corrected answer |
| Sabotage | 9 cases | 9 caught |

## Question wordings from the owner's archive (D98, 2026-10-31; local only)

Synthetic paraphrases only; the archive stays private. Decision D98.

| Requirement | Evidence | Result |
|---|---|---|
| New sensitive topics never saved | `tests/test_classify_archive_wordings.py::test_a_sensitive_topic_is_never_saved` (17 wordings, select and text) | sensitive, not bankable, not draftable |
| Equal-opportunity topics in more forms | `::test_an_equal_opportunity_question_is_sensitive` (9) | sensitive `demographic` |
| Legal status in other words | `::test_a_legal_status_question_is_a_checkpoint` (13, select and text) | `legal_status`, protected, no value, not bankable |
| Licences and address parts | `::test_a_licence_or_an_address_part_is_never_saved` (8) | not bankable |
| Nothing nearby changed | `::test_nearby_wordings_are_unchanged` (9), `::test_the_bare_state_of_residence_label_is_still_a_profile_fact` | unchanged; existing suites 2,017 passed |
| Drafts | `::test_a_draft_that_states_a_new_topic_is_refused` | a draft stating first-generation status or a church is refused |
| Sabotage | 17 cases, one pattern each | 17 caught |

## Drafting spend view and ledger (D97, 2026-10-31; local only)

A stub SDK client and a stub resolver stand in for Anthropic; no key, no paid request. Decision D97.

| Requirement | Evidence | Result |
|---|---|---|
| Each amount says its basis | `tests/test_drafting_provider.py::test_the_spend_view_says_what_each_amount_is` | an estimate and a kept worst case shown apart; server total, what is left, tokens, 14 days, 20 requests, the price list; no prompt, draft, job text or key in the response |
| A request left unsettled | `::test_a_reservation_never_settled_is_shown_as_unknown_and_still_counts` | shown as held, then unknown after the timeout; still counted |
| Settled once | `::test_a_request_is_settled_once` | a second settlement returns False and changes nothing, either way round |
| The midnight boundary | `::test_the_budget_resets_at_midnight_utc` | a request reserved at 23:59:59 stays on its day when settled after midnight; the new day starts from 0 |
| Per account | `::test_the_spend_view_is_per_account_and_says_nothing_of_the_budget_to_others`, `::test_the_spend_view_with_drafting_off` | another account sees none of your rows and no server figures; off: nothing offered |
| Export | `::test_the_export_holds_the_usage_records_and_the_budget_settings` | rows with `cost_basis` and `price_version`; a `drafting_budget` block; no key |
| Migration | `tests/test_migrations.py::test_d97_gives_every_drafting_amount_its_basis` | reserved, not_sent, estimated, unknown; an old error row at 0 regains its worst case; downgrade drops only the two columns |
| In the browser | `frontend/e2e/drafting-spend.spec.ts` (desktop, mobile; a synthetic view) | not offered said; budget, reset, what is left, each basis, the price list; no sideways scroll on a phone |
| Sabotage | 10 drafting cases (see `implementation-status.md`, D97) | 10 caught |

## Form readiness wait (D97, 2026-10-31; local only)

| Requirement | Evidence | Result |
|---|---|---|
| A ready page proceeds at once | `tests/test_form_readiness.py::test_a_ready_page_proceeds_at_once` | under 1 s (113 ms median in the adapter tests, 491 ms before) |
| A slow request of the page is waited for | `::test_a_slow_request_of_the_page_is_waited_for`, `tests/test_dropdown_strategies.py` (`locale_delay_ms` 2500) | waited for the 1.2 s request; the slow locale case still selects the approved option |
| Never ready stops safely | `::test_a_page_that_never_finishes_loading_is_not_ready`, `tests/test_dropdown_strategies.py::test_a_form_still_loading_after_the_allowance_stops_before_anything_is_entered` | not ready at the allowance; failed safe; the receiver's ledger: nothing disclosed or accepted, the locale file requested once, GET only |
| Not waited on | `::test_images_and_event_streams_are_not_waited_for` | a hanging image and an open event stream: ready under 1 s |
| Listeners removed | `::test_the_tracker_stops_listening_when_closed` | nothing counted after close |
| Sabotage | 5 readiness cases | 5 caught |

## Public-address check before every real server-side request (R10.5, 2026-10-29; local only)

No request to any real host was made: a stub resolver and a stub opener stand in for the network.

| Requirement | Evidence | Result |
|---|---|---|
| The read-only check's API host must resolve publicly before anything is sent | `tests/test_gh_readonly.py::test_the_real_api_host_must_resolve_publicly_before_anything_is_sent` (private, loopback, metadata) | stopped; nothing sent, nothing counted |
| Checked before every request, not only the first | `::test_a_public_api_host_is_checked_before_every_request` | resolved twice for two requests |
| The local fixture is never resolved | `::test_the_local_fixture_is_not_resolved` and the existing fixture tests | unchanged |
| The other server-side fetches | `test_freehire_live_read.py::test_the_live_address_is_checked_before_the_approval_is_used` (S7); `test_greenhouse_adapter.py::test_real_greenhouse_posts_are_not_read` (capture reads fixtures only) | already covered |
| Sabotage | 4 cases (no check, first request only, fixture resolved, unsafe ignored) | 4 caught |

## Tailored resumes and cover letters (L2, L3, 2026-10-29; local only, no provider)

A labelled test double stands in for the provider; none is configured. Decision D73.

| Requirement | Evidence | Result |
|---|---|---|
| Nothing without a provider | `tests/test_generated_documents.py::test_nothing_is_generated_without_a_provider` | 503; nothing stored |
| Stored unaccepted for one application | `::test_a_tailored_resume_is_stored_unaccepted_for_this_application`, `::test_a_cover_letter_is_generated_without_a_base`, `::test_a_docx_round_trips_and_escapes_markup` | DOCX, `generated`, its application, its cited facts; refused until accepted; then in the package with its provenance |
| Checked like drafts | `::test_a_document_failing_the_draft_checks_is_never_stored`, `::test_the_request_holds_only_approved_facts_and_quoted_job_text` | four codes; nothing stored; audit by code only |
| Diff from the base | `::test_a_tailored_resume_shows_what_changed_from_its_base` | the changed lines |
| Never elsewhere, never stale | `::test_a_document_is_never_used_for_another_application`, `::test_a_changed_fact_makes_it_unusable`, `::test_a_document_whose_facts_changed_cannot_be_accepted` | 409 with its code; the row asks again, never another document in its place |
| Reject; other users | `::test_rejecting_deletes_it_and_its_file`, `::test_another_users_application_and_documents_are_404` | row and file gone; 404 |
| In the browser | `frontend/e2e/generated.spec.ts` (desktop, mobile; a synthetic list) | not configured said; cited facts and changes shown; accepted |
| Sabotage | 9 cases | 9 caught (one after a stale-accept test was added) |

## Facts proposed from a resume (L1, 2026-10-29; local only, no provider)

Synthetic PDF, DOCX and TXT files built in the tests. Decision D72.

| Requirement | Evidence | Result |
|---|---|---|
| Text from PDF, DOCX, TXT | `tests/test_resume_facts.py::test_text_is_read_from_pdf_docx_and_txt`, `::test_only_the_first_pages_of_a_long_pdf_are_read` | the same lines; 10 pages at most |
| Unreadable files | `::test_unreadable_documents_say_why`, `::test_a_docx_whose_document_part_is_too_large_is_refused` | `unreadable`, `no_text`, `unsupported`, `too_large` |
| Only stated facts | `::test_only_stated_facts_are_proposed`, `::test_nothing_is_inferred` | work, education, credentials; dates kept as written; two legal and sensitive lines skipped |
| Proposed until approved | `::test_proposed_facts_wait_for_approval_and_are_not_used_until_then` | `proposed`, `resume_parse`; no grounding fact until approved; audited by count |
| Once only; other users | `::test_proposing_again_adds_nothing_already_there`, `::test_errors_and_other_users` | nothing twice; 404 across users; a cover letter refused |
| In the browser | `frontend/e2e/documents.spec.ts` "a resume's facts are proposed" (desktop, mobile) | proposed, approved one by one |
| Sabotage | 9 cases | 9 caught (one rerun after its edit was a syntax error, which proves nothing) |

## SCHEMA_VERSION 3 (C18, 2026-10-29; local only)

Synthetic data. Decision D71. Every approval given under 2 is invalidated.

| Requirement | Evidence | Result |
|---|---|---|
| Preference facts hashed by value | `tests/test_schema_v3.py::test_changing_only_the_salary_range_is_a_new_version` | the same number sent, a new version and hash |
| The shape | `tests/test_package_contract.py` (shape 3 beside an unchanged shape 2) | equal |
| `accept` enforced | `::test_accepts` (8 cases), `::test_a_txt_resume_into_a_pdf_or_docx_field_is_a_checkpoint` | a checkpoint; no document sent |
| Implicit and chosen resumes | `::test_an_implicit_resume_is_explained_as_proposed_and_a_chosen_one_as_chosen` | two explanations |
| Generated documents | `::test_a_generated_document_is_used_only_once_accepted`, `::test_an_uploaded_document_records_its_origin` | 409 until accepted; provenance in the package |
| An answer awaiting consent | `::test_an_answer_awaiting_consent_is_never_written_into_a_version`, `tests/test_disclosure_ledger.py` | empty in every version; shown from the live answer; included, then withheld |
| Old approvals | `::test_an_approval_given_under_schema_2_is_invalidated` | a new version; not approved |
| Sabotage | 9 cases | 9 caught |

## Deleting documents (C17, 2026-10-29; local only)

Synthetic documents and the generic receiver. Decision D70.

| Requirement | Evidence | Result |
|---|---|---|
| A version, then every version | `tests/test_document_deletion.py::test_deleting_a_version_removes_its_row_and_file_only`, `::test_deleting_a_document_removes_every_version` | download 404; the files gone; the other version kept; audited with scope and count |
| Another user | `::test_another_users_document_is_404_and_untouched` | 404; file and download untouched |
| Never while needed | `::test_a_document_in_an_approved_package_is_not_deleted_until_revoked`, `::test_a_document_a_running_attempt_needs_is_not_deleted` | `document_in_approval` until revoked, then deleted and the package asks again; `document_in_attempt` even after the approval expired |
| Race with an approval | `::test_a_delete_waiting_for_an_approval_in_progress_sees_it` | waits on the application lock, then refuses |
| An application's choice | `::test_an_application_that_chose_a_deleted_version_asks_again`, `::test_a_past_package_version_keeps_only_what_it_recorded` | the choice removed; the new version without it; the diff shows it gone |
| In the browser | `frontend/e2e/documents.spec.ts` (desktop, mobile) | a version, then the document, deleted |
| Sabotage | 8 cases | 8 caught |

## Credentials as grounded facts (C16, 2026-10-29; local only, no provider)

Synthetic credentials; labelled test doubles. Decision D69.

| Requirement | Evidence | Result |
|---|---|---|
| Only approved, unexpired credentials of this user | `tests/test_credentials.py::test_only_approved_unexpired_credentials_of_this_user_ground_a_draft` | expiring today and no expiry kept; expired, proposed, rejected and another user's excluded |
| A credential named only from a cited credential | `::test_a_credential_named_in_a_draft_must_be_a_cited_credential`, `::test_a_draft_cannot_claim_an_expired_credential` | `uncited_credential` for a job title, an employment description or an expired credential |
| Never saved for reuse | `::test_a_licence_answer_is_never_saved_for_reuse`, `::test_a_licence_question_is_never_answered_from_the_profile_or_the_bank`, `tests/test_bank_scope.py` (48 table rows) | 400; nothing saved; answered for each application |
| Only narrows | `::test_the_credential_family_only_narrows`, `tests/test_bank_scope.py::test_every_family_use_is_load_bearing` (four new witness rows) | other categories kept; every family still load-bearing |
| Sabotage | 8 cases | 8 caught |

## Drafting hardening (C15, 2026-10-29; local only, no provider)

Labelled test doubles stand in for a provider; nothing is sent anywhere. Decision D68.

| Requirement | Evidence | Result |
|---|---|---|
| Each rejection code | `tests/test_drafting.py::test_each_rejection_code` (13 cases), `::test_the_codes_are_listed_and_documented` | every code produced; the audit table lists them |
| Numbers from the job text, the question or an uncited fact | `::test_numbers_echoed_from_the_job_text_or_the_question_are_rejected`, `::test_a_number_from_a_fact_the_draft_does_not_cite_is_rejected` | `invented_numbers` |
| Legal status and sensitive topics | the parametrized rows ("never need sponsorship", "as a woman and veteran", citizenship, disability, criminal record) | `legal_status`, `sensitive_topic` |
| Planted instruction (R11.9) | `::test_the_prompt_quotes_employer_text_and_never_lets_it_out`, `::test_a_planted_instruction_never_changes_the_facts_and_obeying_it_is_rejected` | the job text is one quoted string; the facts are the same with or without it; obeying it is rejected |
| Grounding scope | `::test_grounding_uses_only_this_users_approved_records` | proposed, rejected and other users' records excluded |
| Accept checks | `::test_a_fact_edited_between_request_and_accept_is_refused`, `::test_a_question_reworded_before_accept_is_refused`, `::test_a_question_that_can_no_longer_be_drafted_is_refused`, `::test_a_draft_that_no_longer_fits_is_a_409_not_a_500` | 409 with `draft_facts_changed`, `draft_inputs_changed`, `not_draftable`, `draft_does_not_fit` |
| Audit, cited facts, cache, order | `::test_accepting_is_audited_by_reference_and_shows_the_cited_facts`, `::test_drafts_are_listed_in_the_order_they_were_made` | `draft.accepted` with a reference only; an accepted draft returned as accepted; creation order |
| Rejecting | `::test_rejecting_erases_the_text_and_it_is_never_offered_again`, `::test_an_accepted_draft_is_not_rejected_and_another_users_is_404` | text NULL; `by_user`; a new draft next time; 404 across users and applications |
| In the browser | `frontend/e2e/drafts.spec.ts` (desktop, mobile; the package view with one synthetic draft) | cited facts shown; a changed fact flagged; rejected |
| Sabotage | 17 cases | 17 caught (the order test rewritten so that a wrong order is always caught) |

## Freehire contract hardening (S6, 2026-10-28; fixture only, no Freehire API request)

The local stand-in of Freehire's documented API on the receiver; its request table is the
oracle for what was asked. Synthetic listings. Decision D67.

| Requirement | Evidence | Result |
|---|---|---|
| Counters and `reality` are not a change (R9.4) | `tests/test_freehire_discovery.py::test_counters_and_reality_ticking_are_not_a_change` (mode `fh_reality_tick`) | import 0 changed, 5 unchanged; refresh `unchanged`; a real change still counted |
| Tagged and referral URLs (R9.5) | `::test_a_tagged_url_and_its_untagged_form_are_one_posting` | one `dedupe_key`; same ATS |
| Aggregator address (R9.6) | `::test_an_aggregator_url_is_an_unknown_ats_and_a_manual_handoff` | `unknown`; manual handoff |
| Undocumented fields (R9.7) | `::test_the_2026_10_26_undocumented_fields_are_not_read` | same record, same fingerprint |
| Waiting after `Retry-After` (R9.2) | `::test_an_import_before_retry_after_is_refused`, `::test_a_refused_refresh_holds_back_the_next_refresh_and_import`, `::test_without_retry_after_nothing_is_held_back`; `test_freehire_live_read.py::test_a_run_held_back_by_retry_after_does_not_use_its_approval` | 429 with "Nothing was sent", no request in the stand-in's table; another user not held back; no wait without the header; the live approval left unused |
| Migration | `tests/test_migrations.py::test_s6_adds_the_discovery_backoffs_and_downgrade_drops_only_them` | added; dropped alone on downgrade |
| In the browser | `frontend/e2e/discovery.spec.ts` "a listing refreshes from its source; a Retry-After holds the next request back" (desktop, mobile) | unchanged, gone, refused with Retry-After, then held back |
| Sabotage | 8 cases | 8 caught (one after a 429 without `Retry-After` was added) |

## Version diff (C14, 2026-10-28; local only)

The receiver's form and a fictional manual form; synthetic data. Decision D66.

| Requirement | Evidence | Result |
|---|---|---|
| A changed answer by its label | `tests/test_version_diff.py::test_a_changed_answer_is_shown_by_its_label_and_shown_values` | one row; before and after as shown; no fact references |
| Since the approved version | `::test_what_changed_since_the_approved_version` | the approved side marked; consent change shown |
| A new document version | `::test_a_new_document_version_is_shown` | shown by name |
| A reworded question | `::test_a_reworded_question_is_shown_as_a_changed_question` | question and answer changed |
| Read-only | `::test_the_diff_is_read_only`, `::test_the_diff_never_builds_a_version` | no package version or audit row added |
| Unknown version, another user | `::test_unknown_versions_and_other_users_are_404` | 404 |
| In the browser | `frontend/e2e/review-edit.spec.ts` "after an edit, the page shows what changed since the approved version" | the change listed by label |
| Sabotage | 6 cases | 6 caught (one after a test was added for a pending version) |

## Approval reasons and revoking (C13, 2026-10-28; local only)

The generic receiver; its ledger is the oracle. Decision D65.

| Requirement | Evidence | Result |
|---|---|---|
| The document lists exactly the codes | `tests/test_approval_reasons.py::test_the_document_lists_exactly_the_codes` | equal |
| Each code produced by its path | `::test_approval_refusals_carry_their_codes`, `::test_queueing_refusals_carry_their_codes`, `::test_a_recorded_confirmation_is_never_queued_again_with_its_code` | 409 with `(reason: code)` for all nine |
| Revoke before a worker takes the attempt | `::test_revoking_before_a_worker_takes_the_attempt_stops_it_at_once` | cancelled at once; waits for approval; a late delivery ignored; nothing disclosed; approving again submits once |
| Revoke while a worker holds it | `::test_revoking_while_a_worker_holds_the_attempt_leaves_it_to_the_gates`; `test_lock_order.py::test_a_revoke_arriving_while_a_worker_claims_the_attempt_waits_then_leaves_it_to_the_gates` | the gate refuses; nothing disclosed; no deadlock |
| Revoke after the final click | `::test_revoking_after_the_final_click_is_refused` (sending, awaiting a code); `test_lock_order.py::test_a_revoke_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it` | refused with `revoke_in_flight`; the approval unchanged |
| Cross-tenant | `::test_another_users_revoke_is_404` | 404 |
| In the browser | `frontend/e2e/approval-revoke.spec.ts` (desktop, mobile) | the notice says what was stopped; refused while submitting with its code; the ledger counts |
| Sabotage | 6 cases | 6 caught |

## Review page: change, clear, optional answers, cover letter, destination (C12, 2026-10-28; local only)

The Greenhouse-like fixture form and the generic receiver; synthetic data. Decision D64.

| Requirement | Evidence | Result |
|---|---|---|
| Each question says what the page may offer | `tests/test_review_controls.py::test_each_question_says_what_the_page_may_offer`, `::test_the_page_controls_never_change_the_package` | outside the content; a question not asked, a document, an acknowledgment and a profile fact are not answered here |
| Clearing an answer | `::test_clearing_an_answer_removes_it_and_is_audited_without_its_key` | needs an answer again; one audit row with a reference, never the key |
| Cover letter chosen and left out | `::test_an_optional_cover_letter_is_chosen_and_left_out_again` | sent, then not; a resume refused as a cover letter |
| Cross-tenant | `::test_another_users_application_cannot_be_cleared_or_changed` | 404; nothing changed |
| Where the form sends | `::test_the_page_says_where_the_form_sends` | fixture or employer label |
| In the browser | `frontend/e2e/review-edit.spec.ts` (desktop, mobile) | change, clear, answer again, an optional answer; the ledger holds the changed values; a cover letter chosen, then "None" |
| Sabotage | 6 cases | 6 caught |

## Salary units (C9, 2026-10-28; local only)

Synthetic preferences; no database. Decision D63.

| Requirement | Evidence | Result |
|---|---|---|
| Sent only in units the question allows | `tests/test_resolver.py::test_a_salary_is_sent_only_in_units_the_question_allows` (8 cases) | a number only with both units stated; text with its own units |
| Other or unstated units are the user's | `::test_a_salary_in_other_or_unstated_units_is_the_users_answer` (15 cases), `::test_a_bare_dollar_sign_is_not_another_currencys_answer` | needs the user; nothing sent |
| No currency or period in Preferences | `::test_an_expectation_without_its_currency_or_period_is_never_sent` | never sent |
| Sweep | 805 forms × 32 contexts against the C8 tree | 5,476 withdrawals; the only new values are the user's typed answers |
| Sabotage | 8 cases | 8 caught |

## Fixture variants from the legacy notes (S5, 2026-10-28; local only)

FIXTURE ASSUMPTIONS from `legacy-audit.md` R7: they show what the adapters do on such a page,
not that a real page behaves this way. The receiver's ledger is the oracle. Decision D62.

| Requirement | Evidence | Result |
|---|---|---|
| Confirmation bound to the attempt (R6.4, R6.5, §1.0 item 12) | `test_greenhouse_adapter.py::test_confirmation_bound_to_attempt`, `test_greenhouse_dom.py::test_confirmation_bound_to_attempt`, `test_execution_failures.py::test_confirmation_bound_to_attempt`, `test_api_provider.py::test_confirmation_bound_to_attempt` | words on the form, a path saying "confirmation", another posting's page, a message present before the click, another application's acceptance: never confirmed |
| A box the page unticks (R2.9) | `test_greenhouse_adapter.py::test_readback_mismatch_stops_before_submit_when_the_page_unticks_an_approved_box` | abandoned before the send gate; 0 acceptances |
| Autofill after an upload (R2.7) | `test_greenhouse_dom.py::test_readback_mismatch_stops_before_submit_when_an_upload_rewrites_fields` | abandoned; 2 fields counted; the upload kept |
| Code boxes and unknown code steps (R7.4) | `test_greenhouse_adapter.py::test_code_entered_by_user_only_one_character_per_box`, `::test_code_entered_by_user_only_an_unrecognised_code_entry_is_never_filled` | only the user's code; a code that does not fit never typed; unknown code step: nothing typed |
| Bot check after the click (R4.9b) | `test_greenhouse_adapter.py::test_a_challenge_after_the_final_click_is_never_confirmed_or_clicked_again`, the same in `test_greenhouse_dom.py` | unknown, one click in the ledger, never clicked again |
| Banners and "I agree" (R11.8) | `test_greenhouse_adapter.py::test_no_cookie_banner_or_i_agree_button_is_ever_clicked`, `::test_a_submit_button_waiting_for_an_unlisted_click_stops_before_the_final_click` | no click recorded; a disabled submit stops before the send gate |
| A second page (R2.10, §1.0 item 4) | `test_greenhouse_adapter.py::test_each_step_read_back_before_next_a_second_page_stops_before_disclosure`, the same in `test_greenhouse_dom.py` | failed_safe before any disclosure; captured that way, refused |
| An unlisted option (§1.0 item 6) | `test_greenhouse_dom.py::test_unlisted_option_is_checkpoint` | failed_safe before any disclosure, counted, never named |
| Admission scenarios (R3.1) | `test_provider_contracts.py::test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap` | every new pair mapped to a ledger test; no gap |
| Sabotage | 15 cases (each adapter safeguard, the three admission rules) | 15 caught |

## The disclose path, counted by the receiver (C8, 2026-10-28; local only)

The synthetic receiver's own ledger is the oracle; a synthetic candidate. Decision D61. No
external request.

| Requirement | Evidence | Result |
|---|---|---|
| "Include this answer" sends the answer | `tests/test_disclosure_ledger.py::test_include_sends_your_answer` | the ledger holds `gender=w` |
| "Don't disclose" on an optional question sends nothing | `::test_dont_disclose_on_an_optional_question_sends_nothing` | no value in the ledger |
| An answer without a choice is never sent | `::test_an_answer_without_a_choice_is_never_sent`, `::test_a_required_question_without_a_choice_blocks_approval` | approval refused (409); nothing accepted |
| "Don't disclose" on a required question | `::test_dont_disclose_on_a_required_question_sends_the_forms_decline_option`, `::test_the_decline_option_is_shown_for_review_and_never_saved` (receiver mode `required_eeo`) | the ledger holds `gender=decline`; the row says why; never saved |
| Only one exact decline option is used | `::test_the_one_decline_option_is_the_answer`, `::test_without_exactly_one_decline_option_a_required_question_stays_a_checkpoint`, `::test_the_decline_option_is_never_picked_without_dont_disclose`, `::test_an_optional_question_is_left_blank_even_with_a_decline_option`, `::test_a_multi_choice_decline_is_one_selected_option`, `::test_a_text_question_has_no_decline_option` | no option, two, or a looser wording: checkpoint |
| A saved answer needs "Include" on each form | `::test_a_saved_answer_is_proposed_and_sent_only_after_include` | proposed, then sent after the choice |
| In the browser | `frontend/e2e/submission.spec.ts` "a sensitive answer is sent only as chosen" (desktop, mobile) | the ledger holds `w`, then `decline` |
| Sabotage | removing the mapping, taking the first of several, applying it to optional questions, a substring match, saving it | each caught (7, 1, 2, 5 and 5 failures) |

## Answers and consents bound to their question (C7, 2026-10-28; local only)

A fictional manual form recaptured with other wording. Decision D60. No external request.

| Requirement | Evidence | Result |
|---|---|---|
| An answer for another wording is asked again | `tests/test_input_binding.py::test_an_answer_for_another_wording_is_asked_again`, `::test_a_choice_answer_for_other_options_is_asked_again` | the same question recaptured keeps the answer; other wording or options: unanswered, with the reason |
| Agreeing to one statement never agrees to another | `::test_agreeing_to_one_statement_never_agrees_to_another` | the reworded acknowledgment is unanswered and blocks approval until agreed again |
| "Include this answer" covers only the answer it was given for | `::test_a_disclose_choice_covers_only_the_answer_it_was_given_for`, `::test_the_digest_is_scoped_to_the_user_and_the_question` | a changed answer needs the choice again; the row holds a keyed digest, never the answer; "Don't disclose" is kept |
| Rows saved before C7 | `::test_rows_saved_before_binding_use_the_form_version_they_were_saved_against` | compared with the form version current when saved; a "disclose" without a digest asked again |
| Approval | `::test_a_changed_question_invalidates_the_approval_of_its_answer` | invalidated; the changed question unresolved |

## Job signals (S3, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the source; synthetic jobs and
applications. Decision D59. Nothing contacted Freehire or an employer.

| Requirement | Evidence | Result |
|---|---|---|
| Approval waits while you excluded or closed the job (R5.11) | `tests/test_job_signals.py::test_approval_waits_while_you_excluded_or_closed_the_job` | 409 with the reason code; no approval row; the review and job pages carry the message |
| A posting its source closed, or that is gone, waits for "still open" (R9.8) | `::test_a_posting_its_source_closed_waits_for_your_statement` (closed, gone), `::test_a_posting_missing_from_a_listing_is_not_a_closed_posting` | the tracker job unchanged; refused until your statement; the same report repeated keeps it answered; a new closure after it asks again |
| A repost is a possible duplicate, never merged (R5.9) | `::test_a_repost_is_a_possible_duplicate_and_never_merged` (fixture mode `fh_repost`), `::test_the_same_role_is_the_same_employer_title_and_location` (7 cases), `::test_a_draft_application_is_not_a_prior_application`; `frontend/e2e/job-signals.spec.ts` | a new job; the other job's application state and outcome shown; both copies refused until "a different role"; a later application asks again |
| Concurrent approvals of two copies (R12.5) | `::test_concurrent_approvals_of_two_copies_are_both_refused` | both refused, no approval row |
| Another user's applications are never a signal (R13) | `::test_another_users_applications_are_never_a_signal_and_their_jobs_are_not_found` | no duplicate; 404 for their job; nothing audited for them |
| Greenhouse embed URLs (R5.10) | `::test_a_greenhouse_embed_url_is_the_same_posting_as_its_board_url`, `::test_a_job_stored_under_its_url_key_is_found_again` | same identity as the board URL; a job stored under its old key found again |
| Reason codes and migration | `::test_the_reason_codes_are_documented_exactly`; `tests/test_migrations.py::test_s3_adds_the_job_signal_times_and_downgrade_drops_only_them` | `docs/job-signals.md` lists exactly the codes; stale rows backfilled; downgrade drops only the three columns |

## One link of a kind (C10, 2026-10-28; local only)

Resolver tests with synthetic links, and one fictional manual form in the browser. Decision D58.
No external request.

| Requirement | Evidence | Result |
|---|---|---|
| The one link of its kind is the answer, the same address spelled twice being one | `tests/test_resolver.py::test_the_one_link_of_its_kind_is_the_answer` (8 cases: another kind beside it, `www.`, a trailing slash, a LinkedIn subdomain, `/pub/`, a company page beside a profile) | Profile fact, the links fact recorded |
| Several links of one kind are never chosen between | `::test_several_links_of_one_kind_are_never_chosen_between` (4 cases) | nothing sent; the user's typed answer or a saved answer to this exact question; the links fact kept on a typed answer |
| The host decides the kind | `::test_a_link_of_another_kind_is_never_the_answer` (7 cases: a company or jobs page, look-alike hosts, a query string, a LinkedIn link for a website question) | no answer from the profile |
| The review page says why | `frontend/e2e/review-reasons.spec.ts` | the count of LinkedIn profile links and S4's "not a web address" shown under each question, with its answer box |

## State, City and Country lists (C11, 2026-10-28; local only)

Resolver tests with synthetic facts, and one fictional manual form through the API. Decision
D57. No external request.

| Requirement | Evidence | Result |
|---|---|---|
| A list naming every US state gets the profile's state, by name or postal code, for a US residence | `tests/test_resolver.py::test_a_list_of_every_us_state_gets_the_profiles_state` (13 lists); corpus row `r8_6_ctrl_state_select_every_us_state` | Mapped from profile, the fact recorded, never saved |
| Any other State list is the user's answer for this application, never a dead end | `::test_any_other_state_list_is_the_users_answer_for_this_application` (16 lists: not offered, twice, name and code, short, incomplete, near match, part of a name, unknown or another country, an Australian or Kenyan list, yes/no), `::test_one_state_is_not_a_set_of_options`; corpus rows `r8_6_state_select_short_list_has_residence`, `r8_6_state_select_code_shared_by_another_country` | nothing sent; the user may answer; a saved answer never takes its place; the answer keeps the fact, so a profile edit asks again |
| A City list is never picked from the profile | `::test_a_city_list_is_never_picked_from_the_profile`; `frontend/e2e/place-lists.spec.ts` (the review page says why and offers no reuse); corpus rows `r8_3_city_select_residence_offered_required`, `r8_3_location_radio_residence_offered_required` | the offered residence city is not ticked; the user answers it; typed text still gets the profile's city |
| A Country list without exactly one option for the profile's country is answered by the user | `::test_a_country_list_without_one_option_for_your_country_is_answered_for_this_application`; corpus row `r8_6_country_select_without_residence` | no snapped option; the user may answer |
| Through the API: refused reuse, the typed answer kept, a move re-maps the state | `tests/test_answers_that_do_not_fit.py::test_state_city_and_country_lists_are_never_a_dead_end` | 400 for reuse and for typing over the mapped state; 200 for the per-application answer; a new version and an invalidated approval after the profile moves |
| A State list still asks for the state in the profile when there is none | `::test_a_state_list_without_a_verified_state_still_asks_for_it_in_the_profile` | unchanged: no per-application answer for a missing or unapproved state |

## Watched Freehire searches (S8, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the live origin; its request table is the
oracle. Decision D56. Nothing contacted Freehire.

| Requirement | Evidence | Result |
|---|---|---|
| A new posting reaches the job list at the next check, with one request | `tests/test_freehire_watch.py::test_a_new_posting_reaches_the_job_list_at_the_next_check`, `::test_a_check_asks_for_the_newest_postings_first` | the first check reads two pages; the next reads one page, newest first, and stops at a known posting |
| Never more often than the interval; never two checks of one watch at once | `::test_a_watch_is_checked_no_sooner_than_its_interval`, `::test_one_watch_is_never_checked_twice_at_once` | no request inside the interval; a locked watch is skipped |
| Only an owner's active watch reads | `::test_only_an_active_watch_of_an_owner_reads`, `::test_discovery_off_means_no_check`, `::test_another_address_pauses_the_watch`, `::test_the_address_is_checked_before_every_check` | another account or another address: paused, no request; stopped or ended watches: never checked |
| Bounded by Freehire's answers and the daily cap; never retried inside a check | `::test_a_429_waits_for_retry_after_and_nothing_is_retried_inside_a_check`, `::test_a_longer_retry_after_than_the_interval_is_honoured`, `::test_failures_back_off_and_ten_in_a_row_pause_the_watch`, `::test_the_daily_request_cap_is_never_passed` | waits 60, 120 … 3,600 s; at least Retry-After; paused after ten; the cap defers to the next UTC day |
| Watches are the owner's to see and stop; the command bounds them | `::test_watches_are_listed_and_stopped_only_by_their_owner`, `::test_the_watch_command_records_a_bounded_standing_approval`; `tests/test_migrations.py::test_s8_adds_bounded_watches_and_downgrade_drops_only_them` | another user: empty list, 404; 60 s to a day, at most 90 days |
| A deleted posting stays deleted | `::test_a_deleted_posting_is_erased_and_never_pulled_again`, `::test_deleting_a_posting_keeps_a_job_you_applied_to`; `frontend/e2e/discovery.spec.ts` | content erased, id kept, its job removed unless it has an application; a later search does not add it back |

## Owner-approved live Freehire read (S7, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the live origin; its request table is the
oracle for what was asked. Decision D55. Nothing contacted Freehire.

| Requirement | Evidence | Result |
|---|---|---|
| No live read without the owner's approval for the exact search | `tests/test_freehire_live_read.py::test_a_live_read_without_an_approval_is_refused_and_asks_nothing`, `::test_the_approval_binds_the_exact_search`, `::test_an_approval_outside_its_window_is_refused` | 403, no request, the approval left unused |
| One approval, one run, before the first request | `::test_with_its_approval_the_owner_reads_live_once`, `::test_a_failed_run_used_its_approval_and_is_never_rerun`, `::test_the_approved_page_limit_holds` | the second run is refused; a failed run is not re-run; at most the approved pages |
| Owner account only | `::test_only_the_owner_account_reads_live`; `tests/test_freehire_discovery.py::test_a_live_base_url_is_refused_before_any_request` | another account, or no owner configured: 403, nothing looked up or requested |
| The address is public before any request; no other address | `::test_the_live_address_is_checked_before_the_approval_is_used`, `::test_any_other_address_stays_refused_with_an_approval`, `::test_the_live_flag_opens_only_the_live_origin`, `::test_refresh_and_healthcheck_never_read_live` | refused before a request, the approval left unused |
| The approval command records one bounded run | `::test_the_approval_command_records_one_bounded_run`, `::test_the_approval_command_refuses_an_account_that_does_not_exist`; `tests/test_migrations.py::test_s7_adds_bounded_run_approvals_and_downgrade_drops_only_them` | 1-5 pages, 1-24 hours, a search and a retention statement; database checks refuse the rest |

## Legacy collision corpus and static guards (S4, 2026-10-27; local only)

Synthetic wordings and facts with sentinel values; no legacy data. Decision D54; rules in
`docs/answer-policy.md` (rows 1a, 2a, 3, 4 and the S4 rules). "Before" is the previous commit's
resolver on the same rows.

| Requirement | Evidence | Result |
|---|---|---|
| Each legacy wording trap gets only its safe outcome | `tests/test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome` (244 rows of `tests/legacy_collisions.json`, each run through `package.resolve_answers` with sockets refused) | before: 104 of 244 rows wrong (47 of the first 164); now 0. Every control row passes on both |
| The corpus covers each plan row and its legacy finding; the sentinel check sees a leak | `::test_the_corpus_covers_each_plan_row_and_names_its_legacy_finding`, `::test_the_sentinel_check_sees_a_leak` | R8.1-R8.11, R8.16, R2.9 each have rows; the reuse rows have an exact-reuse control |
| A fact that does not fit its field is never sent, and becomes the user's answer | `::test_a_fact_answer_that_does_not_fit_its_field_is_never_resolved`, `::test_a_multi_answer_is_a_non_empty_set_of_offered_options`, `tests/test_answers_that_do_not_fit.py::test_a_fact_that_does_not_fit_is_the_users_answer_never_saved_and_tied_to_the_fact` | before: a link typed into a Yes/No choice, a country as text into a multi-select, "Yes" into a long answer. Now the user answers it for this application only (saving it for reuse is a 400 and writes nothing), and changing the fact it was about invalidates the approval |
| Each new pattern matches what it is for and nothing else | `tests/test_classify_vocabulary.py::test_each_pattern_added_for_the_legacy_corpus_matches_what_it_is_for`, `::test_residence_nationality_and_a_negated_right_to_work_are_protected`, `::test_a_statement_that_names_no_fact_the_grammar_reads_is_never_checked`, `::test_a_statement_about_no_profile_fact_stays_your_consent_choice` | over-narrowing found by the review ("US-based hours", a language row, Workday's "My Experience", a rating scale) pinned as controls |
| A negated right to work with a sensitive help, option or section stays sensitive (review round 3) | `tests/test_resolver.py::test_a_negated_right_to_work_with_a_sensitive_signal_stays_sensitive`; corpus row `r8_10_prevent_work_help_disability`; the third-person preference rows `r8_3_city_help_team_would_like`, `r8_3_country_select_step_we_would_like` | before the round-3 fix: a typed answer resolved with no disclose choice and a Country follow-up filled from residence; a City or Country field whose help says the team would like you somewhere filled from residence. Both as at the previous commit now |
| Page text cannot make one field slow (review round 3) | `tests/test_classify_vocabulary.py::test_residence_nationality_and_a_negated_right_to_work_are_protected` (a list of eleven places); equivalence and timing checked with scratch scripts | before: up to 215 ms for one field and about 60 s for a 300-field form; now about 1.5 ms per field. The windowed negation search equals the old one on 200,000 random help texts |
| A typed number is shown with every digit | `tests/test_resolver.py::test_a_typed_number_is_shown_with_every_digit` | before: 912345678 was shown as "9.12346e+08" (six significant digits) |
| Only narrowing | the sweep in D54 (scratch harness, not in the repository) | 16,359 forms x 432 contexts, 7,080,048 rows against the previous commit's resolver: 0 newly answered automatically, bankable or draftable; the fixture forms unchanged |
| No mailbox client, mail host, mail API or mail program; none as a dependency (R7.5) | `tests/test_forbidden_capabilities.py::test_no_mailbox_client_is_imported_or_addressed_anywhere`, `::test_no_mail_or_capture_package_is_a_dependency_or_installed_by_an_image`, `::test_the_mail_guard_catches_each_sample`, `::test_the_dependency_guard_reads_every_manifest_and_pytest_setting` | clean on the tree; every planted sample caught |
| No screenshot, video, trace, HAR or captured session where a page runs (R11.4) | `::test_no_screenshot_video_trace_har_or_captured_session_in_python`, `::test_no_capture_in_the_browser_runner`, `::test_the_capture_guard_catches_each_sample`, `::test_the_runner_guard_catches_each_sample`, `::test_the_infrastructure_guard_catches_each_sample`, `::test_the_guards_leave_prose_and_ordinary_code_alone`, `::test_the_scanned_tree_is_the_repository` | clean on the tree; every planted sample caught, prose and ordinary code left alone |

## Outcome integrity and funnel (S2, 2026-10-27; local only)

Synthetic applications and the local receiver; its ledger is the oracle for what the employer
accepted. Decision D53; rules in `docs/architecture.md` ("Application state machine", "Refusal
codes").

| Requirement | Evidence | Result |
|---|---|---|
| A user's confirmation needs what they checked and is never a receipt | `tests/test_applications.py::test_a_user_confirmation_needs_stated_evidence`, `::test_a_user_confirmation_is_recorded_as_user_claimed_never_as_a_receipt`, `::test_the_service_refuses_a_user_confirmation_without_evidence`, `::test_only_a_receipt_or_the_users_statement_enters_submitted_confirmed` | before: confirmed with no evidence (200), indistinguishable from a receipt |
| Reconcile evidence is kept apart and never a 500 | `tests/test_applications.py::test_reconcile_evidence_is_kept_apart_from_the_reason_and_never_a_500` | before: 2,000 characters returned 500, 20 spaces were accepted |
| An outcome needs a known submission; Withdrawn always allowed | `::test_an_outcome_before_any_submission_is_refused_with_a_reason_code`, `::test_an_application_closed_before_submission_takes_no_employer_outcome`, `::test_outcome_choices_follow_the_submission_rule`, `tests/test_funnel.py::test_form_rejected_is_not_employer_declined` | before: any outcome on a draft (200) |
| Outcomes are dated, sourced and audited without free text | `::test_assessment_received_is_recordable_with_the_date_and_note_the_user_gives`, `::test_an_outcome_date_and_note_need_an_outcome_and_no_future_date`, `::test_restating_an_outcome_with_a_date_adds_an_event_and_repeating_it_adds_none`, `tests/test_audit_privacy.py::test_an_outcome_is_audited_with_its_value_and_source_only` | before: no date, source, assessment value or audit row |
| Owner switches need no migration | `::test_the_owner_can_switch_the_refusal_to_a_flag_without_a_migration`, `::test_the_owner_can_route_confirmations_through_reconcile_only` | both switch at call time |
| Refusal codes are a fixed, documented set | `::test_outcome_refusal_codes_are_fixed_identifiers_documented_once` | every `Refused(...)` names a literal code; disjoint from route and rehearsal codes |
| Events are insert-only and their provenance is checked in the database | `tests/test_application_events_db.py::test_application_events_are_insert_only_and_their_provenance_is_checked`, `tests/test_migrations.py::test_s2_adds_assessment_received_and_outcome_fields_without_rewriting_a_row`, `::test_disposable_downgrade_and_reupgrade` | UPDATE and a direct DELETE refused; a cascade still deletes; rows written before S2 untouched |
| The funnel counts the user's own applications, from the ledger's point of view | `tests/test_funnel.py::test_a_receipt_confirmed_submission_counts_once_and_matches_the_ledger`, `::test_an_unknown_outcome_is_unconfirmed_until_confirmed_and_a_receipt_outranks_a_claim`, `::test_a_receipt_recorded_while_quarantined_counts_as_a_receipt`, `::test_applied_by_hand_is_user_claimed_and_never_a_receipt` | submitted total equals the ledger's accepted count in each case |
| Funnel rules (pure) | `::test_reached_stages_count_what_was_recorded_and_never_infer_one`, `::test_a_change_to_none_takes_back_only_the_value_it_replaced`, `::test_no_response_yet_is_computed_from_the_current_submission_and_never_stored`, `::test_fewer_than_twenty_submissions_are_too_few_to_compare`, `::test_sources_follow_receipts_and_who_made_the_move` | no rate in the response |
| Per user; reading writes nothing; route order | `::test_outcome_history_and_the_funnel_are_per_user`, `::test_reading_the_funnel_writes_nothing`, `::test_the_funnel_route_is_matched_before_an_application_id` | before: `/applications/funnel` was taken as an application id (422) |
| Races with the worker's receipt (D46) | `tests/test_outcome_races.py` (3 tests; a barrier and lock waiters, no sleeps; the real worker against the receiver in two of them) | before: the PATCH lost the row version (500) |
| The tracker shows what each submission rests on | `frontend/e2e/phase-a.spec.ts`, `submission.spec.ts`, `tracker-outcomes.spec.ts` (desktop and mobile) | exact labels; ledger at 1 accepted where a submission ran |

## Preparation: bank scope (C6, 2026-10-27; local only)

Synthetic facts and wordings; fictional employers. Decision D51; rules in
`docs/answer-policy.md` row 5.

| Requirement | Evidence | Result |
|---|---|---|
| Answers that depend on the employer, the job or the date are never reused | `tests/test_bank_scope.py::test_bank_scope_table` (1,037 rows), `test_no_c6_row_is_ever_answered_from_the_bank`, `tests/test_bank_scope_api.py::test_answers_that_depend_on_the_employer_the_job_or_the_date_are_never_saved` | before: "this company", "previously worked for", "relevant experience", start date, availability, notice, relocation and salary resolved from a saved answer (reproduced against the previous commit). Now never bankable; saving returns 400 with the reason and stores nothing |
| A saved answer is bound to its help text | `test_question_key_*`, `test_a_saved_answer_needs_the_same_help_text`, `test_from_bank_checks_the_stored_help_text`, `test_a_saved_answer_is_reused_only_for_the_same_help_text` | before: reused for other help text or none. Now only for the same normalized help text |
| Saved answers from before C6 are kept, not re-keyed | `test_an_entry_saved_before_c6_answers_only_a_question_without_help_text`, `test_saved_answers_from_before_c6_are_kept_and_answer_only_a_question_without_help_text`, `tests/test_migrations.py::test_c6_saved_answers_keep_their_key_and_gain_no_help_text` | same id, key, value and version; answer only questions without help text; out-of-scope ones listed as "Not reused" |
| Follow-ups, repeated wording, sections | `test_a_follow_up_of_a_question_that_is_not_reused_is_not_reused`, `test_the_same_wording_twice_on_one_form_is_never_answered_from_the_bank`, `test_a_follow_up_or_a_repeated_question_is_never_saved` | never reused, 400 on save |
| Concurrent saves and deletes never fail | `tests/test_bank_races.py` (5 tests, 6 cases; deterministic: a barrier and lock waiters, no sleeps) | run against the previous code: two IntegrityError 23505 (a 500), a lost version increment, StaleDataError, a second delete not refused. Now serialized; the second delete is 404 |
| Only narrowing | `test_positive_controls_behave_exactly_as_before_c3_c5` with `C6_DELTA` (9 controls), `test_each_c6_delta_only_narrows`, the property tests | verified on the working tree against `7669c61` with scratch scripts: 1,315,200 form resolutions, 0 violations |
| Review findings fixed (D51) | `tests/test_bank_scope_api.py::test_saving_and_listing_never_fail_on_unusual_text`, `::test_a_follow_up_in_a_package_built_before_c6_checks_its_parent_again`, 62 more table rows in `tests/bank_scope_wordings.json`, the `E_APPLY` family in `test_every_family_use_is_load_bearing` | a NUL in help text or an answer, a long stored option and NaN no longer return 500; a frozen package's follow-up checks its parent; the missed wordings are refused; 20 deliberate breaks, each caught |
| The stable reuse question reaches the employer | `tests/test_execution_validation.py` (`answer_bank_delete`, receiver mode `bank_question`), `frontend/e2e/phase-b.spec.ts` | a saved education answer is reused for a second application, and deleting it after approval stops the running attempt (receiver ledger); the review page offers the reuse box on the education question and not on "How did you hear about this job?" or Gender, and the Saved answers page shows the help text |

## Preparation: statements, legal facts and sensitive topics (C3-C5, 2026-10-26; local only)

Synthetic facts and wordings; pure resolver tests run the package loop
(`package.resolve_answers`); API tests use fictional manual forms. Decision D49; rules in
`docs/answer-policy.md`.

| Requirement | Evidence | Result |
|---|---|---|
| A statement of a profile fact is checked only with agree and a true approved fact | `tests/test_question_safety.py::test_question_safety_table` (c3 rows), `tests/test_question_safety_api.py::test_a_fact_statement_is_checked_only_while_the_approved_fact_makes_it_true` | before: "I am legally authorized to work in the United States" checked from agree alone for an applicant not authorized (reproduced against the previous commit). Now checked only when the approved fact holds, with the fact recorded; not authorized, unknown, not applicable or not approved: a checkpoint; editing the fact after approval gives a new version, invalidates the approval and unchecks it (before, the approval survived) |
| Statements NoEfforts cannot check are never checked | table rows c3.neg, c3.compound, c3.anyemployer, c3.res.newmexico, c3.please_confirm, c3.help_condition, c3.veteran and others | negated, compound, qualified, regional, help-text-qualified and sensitive statements: a checkpoint agree cannot clear; declining an optional one leaves a box unchecked and a choice blank, never "No" (`test_a_declined_optional_statement_choice_is_left_blank_never_no`) |
| Eligibility misreads become checkpoints | table rows `c4.*` (eligibility, legal status, residence context) | before: a work-permit question answered inverted from the authorization fact, "New Mexico" from Mexico's fact, "for any employer" yes for an employer-tied visa, a saved citizenship answer reused (each reproduced against the previous commit). Now each is a question the user answers for this application, never from the profile or the bank |
| Sensitive topics, by wording, help text, options, section and parent | table rows `c5.*` (topics, EEO structure, help text, follow-ups); `test_a_follow_up_of_a_sensitive_question_needs_its_own_consent`, `test_a_health_question_is_never_drafted` | criminal history, health, accommodations, age variants, salary history, IDs, family, military, political, caste, minority identity: sensitive, never saved, reused or drafted; a follow-up of a sensitive answer needs its own consent |
| Nothing new is saved for reuse; old saved answers are kept, unused | `test_sensitive_and_legal_answers_are_never_saved_for_reuse`, `test_answers_saved_before_c3_c5_are_kept_but_no_longer_used` | saving citizenship, criminal, current-salary, references, generic, work-permit and statement answers: 400, nothing stored; ordinary and legacy EEO answers save as before (C8 decides the EEO policy); entries saved earlier stay listed and answer nothing, for anyone |
| What the adversarial review found | table rows `rv.*`; `tests/test_classify_vocabulary.py::test_each_pattern_added_after_review_matches_what_it_is_for`, `test_a_heading_that_adds_to_its_help_statement`, `test_a_country_whose_name_looks_like_a_region_is_still_a_country`; `test_a_citizenship_statement_is_placed_in_one_country_or_none`, `test_a_dual_citizenship_statement_is_never_checked` | each reported wording probed against the previous commit and the change: a sensitive-and-citizenship checkbox resolved from agree (a regression, fixed); the rest were gaps the change did not close (statements in other words, unplaced citizenship, headings, a declined optional statement answering "No", help text after "Answer for …", other times and held sponsorship, Country fields about work authorization or the job, regions, examples and organisations). Each is now a checkpoint, blank, or checked only on a true fact |
| Only narrowing | `test_positive_controls_behave_exactly_as_before_c3_c5` (46 rows pinned to the previous resolver), `test_no_c3_c5_row_is_ever_answered_from_the_profile_or_the_bank` (9 profiles × 5 consents × 3 bank states), `tests/test_classify_vocabulary.py` (94) | controls identical in every attribute; no other row is ever answered from the profile or the bank or made reusable. Verified once against the previous commit with scratchpad scripts (not in the repository): 117 fixture forms and test wordings, 52,800 rows identical except wrong-kind stored consents; 452,520 resolutions with no new automatic answer and nothing newly reusable or draftable; fixture package hashes 40/40 unchanged |

## Preparation: guards, and only resolved answers sent (C1, C2, 2026-10-23; local only)

Synthetic candidate and fixture forms; execution against the local receiver, whose ledger is
the oracle for what was sent. Decision D48.

| Requirement | Evidence | Result |
|---|---|---|
| An answer that is not resolved is never sent | `tests/test_sending.py::test_a_stale_accepted_draft_is_a_checkpoint_even_when_optional` | before the fix: an optional accepted draft whose fact changed became "blank" but kept its text, the package was approved (200) and the ledger showed the stale text sent, reproduced. Now the question is a checkpoint (`needs_user`, approval 409); the user's own replacement is approved and is what the ledger shows |
| The package builder keeps no value on a blank row | `test_the_builder_clears_a_blank_row_whatever_the_resolver_returns`, `test_every_fixture_package_sends_only_resolved_answers` (7 packages), and the invariant checked in each package test of the file | with a resolver forced to return values on blank rows, none reaches the package; over the fixture, receiver and Greenhouse-fixture packages, a blank row has no value or display, a row with a value is resolved or blocks approval, documents are exactly the resolved document rows |
| A document question that is not asked | `test_a_document_question_that_is_not_asked_attaches_nothing`, `test_a_document_question_that_depends_on_a_missing_question_attaches_nothing` (2) | before the fix: HTTP 500 (TypeError) for the package view and every answer saved, reproduced. Now no document is attached until the question applies; a required one depending on a missing question is a checkpoint |
| The worker refuses a stored package that is not the approved one, before any adapter code | `test_the_runner_refuses_before_anything_is_sent` (8: four adapters; a resolved answer changed in the stored package without its hash; a value on a row that is not resolved with every hash made to agree) | `failed_safe`, no disclosure started; the ledger has no request at all after preparation. Found on the way: nothing compared the stored package with its approval before; with this check removed, the changed resolved answer is sent and confirmed (the gates rebuild the package from current data, which still matches) |
| Each adapter fills only resolved answers (runner check bypassed) | `test_each_adapter_fills_only_resolved_answers` (4), `test_the_adapter_view_drops_only_what_is_not_resolved`, `test_nothing_else_reads_answer_values_for_sending` | with the runner's check bypassed and the stored package changed without its hash (the gates, rebuilding from current data, pass), each adapter confirms and the injected text appears nowhere in the ledger |
| The package shape is pinned to `SCHEMA_VERSION` | `tests/test_package_contract.py` (3) | 96 key paths over six synthetic packages (every fact-reference type, answer value shape, condition and unsupported control) equal the shape recorded for version 2; the hash ignores only fact-reference version counters |
| Cross-tenant routes C1 found untested | `tests/test_preparation.py::test_tenant_isolation_for_revoke_documents_drafts_and_the_bank` | revoke, document selection (with the other user's or the owner's document), draft acceptance (the other user's application or the owner's other application), the document list and versions: 404 or nothing of the owner's; the owner's approval stays live; another user never resolves a question from the owner's saved answer |
| No candidate document, secret or captured session is committed | `tests/test_repo_hygiene.py` (3) | over what a commit would contain (`git ls-files`, tracked plus untracked files that are not ignored): no document, spreadsheet, environment file (other than `.env.example`), key, browser capture (traces, `.auth/`, storage state, cookies) or database file; every email address, in any file whatever its encoding, on a reserved domain, or the owner's own no-reply address. The review found the first version would have failed on its own sample address once committed (it scanned only tracked files); the sample is now built at run time and untracked files are scanned too |

## Provider admission (I2, 2026-10-22; local only, no external request)

Computed from code tables and recorded evidence (`providers/admission.py`,
`docs/provider-admission.md`); a synthetic example provider ("exampleats", `.invalid` hosts)
built into copies of the tables, never registered. Execution scenarios use the local receiver;
its ledger is the oracle.

| Requirement | Evidence | Result |
|---|---|---|
| Every provider's admission is computed, and no claim exceeds it | `tests/test_provider_admission.py`: `test_each_registered_provider_gets_its_computed_admission` (10), `test_every_registered_provider_is_admitted_to_what_it_claims` | all ten within their claims; `greenhouse_dom` and `greenhouse_readonly` at `observed_read_only`, `greenhouse_hosted`, `fixture_ats`, `fake_api` and the two discovery providers at `fixture_only`, `lever` and `workday` at `planned`, `manual_handoff` at `registered`; none `rehearsal_ready` |
| Every requirement has checks; every check is reachable and breakable | `test_every_requirement_has_a_check`, `test_every_check_is_met_on_the_complete_example` (37), `test_every_check_is_caught_by_its_sabotage` (37), `test_the_example_reaches_each_stage_only_when_its_requirements_are_met` (6), `test_a_key_is_safe_only_when_named_after_its_ats_or_kind` (10), `test_text_naming_an_identifier_is_caught` (8), `test_text_naming_no_identifier_passes` (7) | each check met on the complete example and broken by one change that stops it before its stage, breaking exactly that check and its declared dependencies (8 checks have one or two); each stage from `registered` to `rehearsal_ready` reached exactly |
| Owner boundaries and the cap | `test_nothing_passes_the_real_destination_cap`, `test_an_owner_boundary_is_never_passed_without_its_record` (4) | even with every check met the example stops at `rehearsal_ready` (`real_destinations_refused`); with the cap lifted in the test only, the doc review, the read-only runs, permission C and permission D (each its own record) still stop it without their record |
| Waivers keep pre-I2 claims, never advance them | `test_a_waiver_never_advances_a_provider_beyond_its_claim`, `test_waivers_are_frozen_to_the_pre_admission_providers_and_still_real`, `test_a_waiver_for_a_new_provider_has_no_effect`, `test_raising_a_claim_never_raises_a_waiver`, `test_a_new_adapter_under_a_pre_admission_key_inherits_no_waiver`, `test_the_by_ats_view_shows_what_is_held_only_by_a_waiver` | `greenhouse_dom` with every rehearsal condition met in memory still stops at its claim on its waived doc review; three waivers, each covering a check that fails without it, each capped at the claim frozen at I2; `greenhouse_hosted` raised in memory to observed with credited runs stays at `fixture_only` (caught); the by-ATS view shows Greenhouse's waived doc review |
| Recorded runs credit only when single-use and completed | `test_every_observed_cell_is_credited_by_a_completed_single_use_run`, `test_a_run_without_its_own_approval_or_not_completed_credits_nothing`, `test_the_recorded_runs_are_the_documented_runs`, `test_a_structure_only_observation_never_meets_a_rehearsal_condition`, `test_manual_evidence_that_would_change_a_condition_is_caught` | every observed cell, and the Greenhouse providers' "no" traits, credited by runs #4, #6, #8 or #9 (the generic fixture adapters' "no" traits are their fixtures' design); #1-#3 and #7 credit nothing, #5 records nothing to credit; the dropdowns are structure only, so the rehearsal condition stays unmet even if readiness counted the level; Path A recorded with any answers changes no readiness condition (computed) |
| Admission is pure and advisory | `test_admission_reads_no_database_and_no_repository_file`, `test_admission_imports_no_browser_code`, `test_computing_admission_changes_nothing`, `test_nothing_routes_labels_or_approves_on_admission`, `test_served_admission_carries_only_fixed_identifiers`, `test_the_api_serves_admission` | same result with file reads and the database refused; no browser module loaded (subprocess); registry, readiness, versions and support states unchanged, no audit row; only the providers API imports it; served strings are fixed identifiers only; 401 without a session |
| The tables are the code, the tests and the docs | `tests/test_provider_contracts.py` (39); `tests/test_provider_admission.py::test_the_documented_admission_tables_are_the_code` | identity contract for all six ATS names (positive, variants, tracking parameters dropped from the canonical URL, vendor site, non-posting, lookalike, fixture origin, foreign form, bounded parts); five known gaps each still reproduced (a gap with several behaviours while any of them does); fixture paths exist; policy, runner, rehearsal, discovery and observer tables equal the registry's; receipt keys pinned per adapter; every route's metadata survives the sanitizer; the documented capability matrix and support states equal the registry, and the admission doc's tables the code |
| Fixture scenarios | `test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap` | 32 required scenarios, each a ledger test; five were missing and were added: `tests/test_execution_failures.py::test_reconciling_an_unknown_outcome_never_sends_again` (three browser adapters, both findings), `tests/test_greenhouse_adapter.py::test_page_altering_a_filled_value_stops_before_submit`, and the API upload-failure case now reads the ledger |
| An approval sends once (D15) | `test_reconciling_an_unknown_outcome_never_sends_again` (6), `tests/test_execution_security.py::test_a_submission_whose_code_was_never_entered_never_sends_again_on_its_approval`, `test_a_late_receipt_after_a_not_received_reconciliation_still_counts_and_nothing_resends`, `test_not_received_is_refused_once_the_employers_receipt_was_recorded`, `test_an_application_with_a_recorded_receipt_is_never_queued_again` (simulated state) | before the fix: after a "not received" reconciliation, queueing again sent the application a second time with the old approval (ledger: 2 accepted), reproduced; an abandoned code step left its approval live after the final click. Now each retires the approval (`reconciled_not_received`, `verification_not_completed`) and queueing is refused (409) with the ledger unchanged; a late receipt confirms the application (it was lost before); "not received" is refused once a receipt is recorded; a recorded confirmation is never queued again |
| A manual-handoff approval never runs through an adapter (D28) | `tests/test_approval_binding.py::test_an_approval_given_for_a_manual_handoff_never_runs_through_an_adapter`, `tests/test_rehearsal_prerequisite.py::test_an_approval_given_for_a_manual_handoff_is_shown_against_the_route_that_would_run` | before the fix: recorded with no adapter, it read as a pre-binding approval and was queued (200) once the route became an adapter's. Now it records `manual_handoff`, is retired at queueing (409) and nothing is disclosed; the review shows the prerequisite of the route that would run |
| An unlisted form source is refused | `test_an_unknown_form_source_is_refused_not_given_to_the_fixture_adapter`; `tests/test_reason_codes.py::test_no_destination_falls_through_to_the_fallback` | `no_adapter`, a manual handoff, never the generic fixture adapter; the known sources route as before |
| Over-long identities and cells | `test_an_over_long_identity_is_never_a_server_error`, `test_identity_parts_are_bounded` (6), `tests/test_jobs.py::test_an_over_long_cell_is_that_rows_error_never_a_server_error` | before: HTTP 500 (DataError) for an over-long company or posting id, and for an import with an over-long cell; now 201 and recognised again (200), a URL that canonicalizes past its column is a 400, and an over-long cell is its row's error |
| Spec invariants | `tests/test_providers.py`: `test_every_spec_error_branch_has_a_case`, `test_registry_problems_reject_inconsistent_entries` (7), `test_a_side_table_naming_an_unregistered_provider_is_refused` | 20 `raise SpecError` branches, each with its own negative case (6 had none before I2); every cross-provider problem refused at import |

## Lock order and race guarantees (E6 follow-up, 2026-10-22; local only)

Two real PostgreSQL transactions on separate connections per test, synchronized by barriers
at exact lock points and by the waiting side's lock wait read from `pg_stat_activity` (no
timing sleeps); every side must finish within 30 seconds. Synthetic data, the local receiver.

| Requirement | Evidence (`tests/test_lock_order.py`) | Result |
|---|---|---|
| A cancel racing a gate never deadlocks | `test_a_cancel_arriving_while_the_disclosure_gate_holds_its_locks_waits_for_it`, `test_a_cancel_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it` | before the fix: deadlock (40P01), reproduced first. Now the cancel waits: after the disclosure gate it cancels (the worker's next fenced step is refused; nothing reached the receiver here); after the send gate it is refused ("in flight"), the outcome is the worker's (`unknown`, quarantined), never retried |
| A cancel committed before a gate stops it | `test_a_cancel_committed_before_a_gate_checks_stops_that_gate` (disclosure, send) | the gate, waiting for the attempt, finds it cancelled: lost authority (before the fix: a raw serialization error); attempt and application `cancelled`, nothing authorized |
| Worker writes and cancel | `test_a_cancel_racing_the_worker_writing_an_outcome_waits_for_it`, `test_a_cancel_racing_the_worker_recording_evidence_waits_for_it`, `test_a_cancel_arriving_while_a_worker_claims_the_attempt_waits_for_the_claim`, `test_a_duplicate_delivery_while_a_gate_holds_the_attempt_is_ignored_without_waiting` | before the fix the outcome and evidence races deadlocked (the evidence one through the foreign key's key-share lock on the application); now each waits and the worker's write stands. A claim racing a cancel waits for it (the claim locks the attempt first too). A duplicate delivery does not even wait: it is ignored, the first worker keeps its authority (the reported duplicate-claim risk does not exist: the claim matches only a pending attempt) |
| Cancel and a new attempt being queued | `test_a_cancel_waiting_for_a_queueing_transaction_takes_its_new_attempt_too`, `test_a_cancel_never_waits_for_an_attempt_it_finds_after_the_application_lock` | the cancel takes the attempt queued while it waited (before the fix: a stale application copy, `StaleDataError`); if a claim holds that attempt, the cancel is refused ("Try again") instead of deadlocking, the claim proceeds, and a second cancel holds |
| Withdrawal and deletion racing the send gate | `test_a_withdrawal_arriving_while_the_send_gate_relies_on_the_rehearsal_waits`, `test_a_withdrawal_committed_while_the_send_gate_waits_for_the_record_stops_it`, `test_an_evidence_deletion_arriving_while_the_send_gate_relies_on_its_receipt_waits`, `test_an_evidence_deletion_committed_while_the_send_gate_waits_for_the_receipt_stops_it` | arriving while the gate holds the record or receipt: they wait, the gate authorizes the send (`met` / `established`), and the withdrawal or deletion then applies to later submissions only. Committed first: the gate sees it and refuses (`rehearsal_revoked`), nothing is sent (receiver: no new acceptance) |
| A gate checks what is committed, after its locks | `test_an_edit_committed_while_a_gate_waits_stops_that_gate` (answer or profile; disclosure or send gate), `test_a_note_saved_while_a_gate_waits_does_not_stop_it`, `test_a_write_to_the_approval_waits_for_a_gate_that_holds_it` | before the fix (REPEATABLE READ snapshot at the first statement), all four edit cases passed the gate with the content as approved, and a note made it refuse; reproduced first. Now an answer or profile change committed while the gate waits is seen ("changed after approval"), nothing authorized; a note is no reason to refuse; a direct approval write waits for the gate holding the approval row |
| Queueing again with an earlier attempt still pending | `test_queueing_again_stops_an_earlier_attempt_that_can_no_longer_run`, `test_queueing_again_while_the_earlier_attempt_is_being_claimed_never_deadlocks` | before: an uncaught duplicate (HTTP 500). Now the earlier attempt (pending under a stale approval, nothing disclosed) is stopped and the new one queued; while a worker is taking it, queueing is refused ("Try again") instead of waiting, and the claim then stops the earlier attempt; nothing reached the receiver |
| Clearing and saving one input | `test_clearing_an_input_while_it_is_being_saved_serializes_instead_of_deadlocking` (consent, answer) | held the moment its delete is flushed: the clear already holds the application, the save waits, and its value remains. Deleting first (or taking the application only after the delete) deadlocked |
| The rehearsal stop and the sweeper | `test_a_cancel_racing_the_rehearsal_stop_waits_for_it`, `test_a_cancel_racing_the_sweeper_waits_for_it` | the cancel waits; the stop ends `rehearsed`, the sweeper re-pends, and the cancel then cancels; with cancel in the old order both deadlocked (40P01) |
| Sabotage | applied one at a time, each reverted | 17, each caught: cancel in the old order against the rehearsal stop and the sweeper, the clear taking the application only after its delete, a gate skipping a locked attempt instead of waiting; and: cancel in the old order (against a gate, against evidence recording), claim locking the application first, cancel waiting at its re-check, no re-check, no refresh, clearing an answer or a consent before the application lock, the gates reading a REPEATABLE READ snapshot again, no stop of the earlier attempt (against a plain re-queue, against a claim), queueing waiting for the earlier attempt (caught as a bounded 30-second hang), the gates not locking the approval row. The E6 record and receipt lock checks, re-run against the gates' new reads, are caught by the tests in which a withdrawal or deletion must wait |

## Rehearsal prerequisite (E6, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only; the rule is put on fictional `e6-` fixture forms
by the test-only setting (`env == "test"`). Real destinations are refused before it. The
receiver's ledger is the oracle for what reached the synthetic employer. Rows edited by hand
are labelled simulated in the tests.

| Requirement | Evidence (`tests/test_rehearsal_prerequisite.py` unless noted) | Result |
|---|---|---|
| A fixture path without the rule needs nothing | `test_a_fixture_path_without_the_marker_needs_no_rehearsal` | review `not_required`; confirmed; the send gate records `not_required`; ledger 1 accepted, 1 upload |
| The first submission on a path needs a recorded rehearsal | `test_the_first_submission_on_a_path_needs_a_recorded_rehearsal` | review `unmet` / `no_rehearsal` with its fixed message; approve 409 "(reason: no_rehearsal)", no approval row; queueing refused; nothing posted to the receiver |
| A rehearsal is never permission to submit | `test_a_valid_rehearsal_then_a_separate_approval_to_submit` | after the rehearsal: `met`, but queueing without a new approval is 409; the approval to submit names the rehearsal; confirmed, send gate records `met`; ledger 1 accepted, 2 uploads; every attempt labelled `fixture` |
| An established path, and what ends it | `test_a_confirmed_submission_establishes_its_path`, `test_a_submission_made_while_the_rule_did_not_apply_establishes_nothing`, `test_an_established_path_needs_a_new_rehearsal_after_an_adapter_version_change`, `test_a_newer_failed_rehearsal_outvotes_an_established_path` | a confirmed submission after a rehearsal establishes the path (a withdrawal of the older rehearsal changes nothing); the next submission records `established`; once every establishing receipt is deleted, the withdrawn rehearsal decides: `rehearsal_revoked`. A submission made while the rule did not apply establishes nothing; another class (simulated) or an adapter version change ends it; a newer failed rehearsal outvotes it |
| The newest result decides, by when it finished | `test_a_later_failed_rehearsal_supersedes_an_earlier_success`, `test_the_rehearsal_that_finished_last_decides_whatever_the_queue_order`, `test_an_in_progress_rehearsal_never_displaces_a_finished_one` | a newer failure: `rehearsal_failed` (approve 409); a rehearsal queued first and failing last decides; a waiting rehearsal leaves the finished one deciding; only a waiting one: `rehearsal_in_progress` |
| A path is user, provider, origin and board | `test_one_rehearsal_serves_another_posting_on_the_same_path`, `test_a_rehearsal_on_another_board_does_not_count`, `test_a_rehearsal_never_counts_for_another_user`, `test_the_user_filter_holds_even_if_path_references_collided`, `test_the_path_is_user_provider_origin_and_board`, `test_an_attempt_and_its_record_keep_the_path_only_as_a_keyed_reference` | another posting on the board: `met`; another board or user: `no_rehearsal`; another user's withdraw or attempts: 404; the same stored reference asked by another user finds nothing; the reference changes with each component, never contains the board or host, and is never served |
| Each layer refuses alone | `test_each_layer_refuses_with_the_others_bypassed` (approve, enqueue, claim, disclosure, send, none), `test_turning_the_rule_on_after_queueing_is_caught_by_the_worker`, `test_a_claim_refused_after_a_sweeper_repend_leaves_nothing_running` | approve: 409, no approval; enqueue: 409, no attempt or outbox row; claim: `failed_safe`, `claim_refused_rehearsal`, no request at the receiver; disclosure: `failed_safe`, nothing uploaded; send: `abandoned`, 1 upload, 0 accepted, never re-pended; none bypassed: confirmed. A re-claim after a re-pend leaves the application `needs_user_action`, not `running` |
| A withdrawal or deletion racing a gate | `test_withdrawing_the_relied_on_rehearsal_while_the_send_gate_waits`, `test_a_withdrawal_after_the_gate_snapshot_is_refused_not_missed`, `test_deleting_an_establishing_receipt_after_the_gate_snapshot_is_refused` | a worker held before the send gate: `abandoned` with `rehearsal_revoked`, 0 accepted; a withdrawal or receipt deletion committed after the gate took the attempt and before it read (second session): the gate sees it and refuses with `rehearsal_revoked` |
| Fail-closed | `test_a_stale_window_outside_its_bounds_fails_closed`, `test_an_error_while_checking_is_a_refusal_and_leaves_the_session_usable`, `test_a_rehearsal_with_no_record_cannot_be_withdrawn_or_counted`, `test_a_fixture_rehearsal_never_satisfies_a_real_path` | an invalid window: `rehearsal_check_unavailable`; 31 days (simulated): `rehearsal_stale`; a statement the database refuses: `rehearsal_check_unavailable`, the session still usable, approve 409; no record: `rehearsal_evidence_missing`, not withdrawable (404); a fixture record for a real-class check: `rehearsal_mismatched` |
| Real destinations are still refused first; the setting only adds the rule | `test_a_real_destination_is_still_refused_first`, `test_the_marker_only_adds_the_rule_and_only_in_tests` | with the rule on every path: `not_applicable` / `real_destination_disabled` before and after approving; queueing 409 with the manual-handoff message, no attempt. The setting is ignored outside `env == "test"`, never removes the rule, and leaves routing, the adapter and the class unchanged |
| Every code is produced by its own path | `tests/test_rehearsal_codes.py` (17) | each of the 12 codes produced by its own cause; fixed identifiers, safe for audit, apart from the routing codes; messages name no destination; the documented codes, messages and statuses equal the code |
| Readiness counts a real submission only after a held prerequisite | `tests/test_pilot_readiness.py`: `test_a_real_submission_counts_only_after_its_prerequisite_held` | simulated rows: a real-class confirmation counts only once its send gate recorded the prerequisite held; still 0 of 7 met |
| The UI shows the requirement with its code | `frontend/e2e/rehearsal-prerequisite.spec.ts` (desktop, mobile); `frontend/e2e/submission.spec.ts` | `no_rehearsal` shown, approve to submit disabled, the server's 409 with the same code; rehearse: allowed; withdraw (two steps): `rehearsal_revoked` on the row and the attempt; rehearse again, approve, submit: 1 accepted, 3 uploads; an unmarked form shows no code and labels its attempt as fixture evidence |
| Sabotage | applied one at a time, each reverted | 28 checks, each caught (one, an exception read as met, was missed at first; a test was added): each layer removed (5), the rule applied to rehearsals, no user filter, any success instead of the newest, a waiting rehearsal displacing a finished one, no board in the path, no class comparison, no approval binding, no record lock, no receipt lock, the marker outside tests, establishing without a receipt, with any confirmed submission, or ignoring the adapter version, the send gate not recording the prerequisite, readiness without it, an exception as met, no savepoint, no age check, no evidence re-read, queue-time order, an approved manual handoff read through its legacy binding, a refused re-claim left running, withdrawal offered without a record |

## Rehearsal stop, rehearsal records and readiness evidence (E5 step 3, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only. The receiver's ledger is the oracle for what
reached the synthetic employer.

| Requirement | Evidence (`tests/test_rehearsal_stop.py` unless noted) | Result |
|---|---|---|
| A rehearsal records what it proved, at its stop | `test_a_rehearsal_records_what_it_proved_at_its_stop` (browser, API) | one record: class `fixture`, route, adapter and current version, 1 of 1 uploads acknowledged, readback 0 mismatched (API: none), recheck matched, nothing unresolved; it holds; one `package.approval_retired`; ledger 1 upload, 0 accepted |
| The stop repeats the gate | `test_a_revocation_at_the_stop_ends_abandoned_not_rehearsed`, `test_a_change_to_the_profile_at_the_stop_ends_abandoned`, `test_a_cancel_at_the_stop_is_not_a_rehearsal`, `test_a_lost_lease_at_the_stop_is_not_a_rehearsal`, `test_a_revocation_committed_while_the_stop_waits_is_refused` | a worker held at the stop: revoked, edited, cancelled or swept, the attempt ends `abandoned` or `cancelled`, never `rehearsed`, with no record; a revoked approval is shown as revoked and no retirement is recorded for it |
| The stop checks the evidence | `test_the_stop_ends_rehearsed_only_with_complete_evidence`, `test_the_stop_refuses_incomplete_or_contradicting_evidence` (5), `test_the_stop_refuses_an_upload_not_acknowledged` (2), `test_the_stop_refuses_a_document_that_was_not_approved`, `test_the_api_route_reads_the_form_again_before_its_stop` | missing recheck, readback or upload: `rehearsal_evidence_missing`; a readback mismatch, a changed form, an unacknowledged upload or an unapproved document: `rehearsal_evidence_inconsistent`; the code is kept on the outcome event. Requests the egress proxy denied are counted in the record, not disqualifying |
| A record holds only while it is true | `test_a_record_holds_only_while_its_evidence_and_attributes_do`, `test_deleting_an_applications_evidence_revokes_its_rehearsals` | another adapter version or class: mismatched; past 30 days: stale; an invalid window: check unavailable; an edited readback: inconsistent; an expired row: missing; a tampered class: mismatched; evidence deleted: revoked (another user: 404) |
| A destination keeps its class | `test_a_gate_refuses_a_destination_whose_class_changed`, `test_an_attempt_queued_before_classes_were_recorded_is_refused_plainly`, `test_only_a_configured_fixture_origin_outside_production_is_a_fixture` | recorded at queueing; a gate refuses a changed class, and an attempt with no recorded class (queued before this change) with its own plain message, before anything is disclosed; production and unknown origins are `real` |
| A checking error is a refusal | `test_a_failed_statement_while_checking_a_record_is_a_refusal_not_an_error` | a statement the database refuses: `rehearsal_check_unavailable`, and the caller's session stays usable (a savepoint) |
| No identifiers kept | `test_records_events_and_audit_hold_no_external_identifiers`, `test_the_ack_and_strength_vocabulary_matches_the_adapters` | the record, events and audit hold no URL, host, slug, field or name; the shared vocabulary equals the adapters' |
| Readiness counts recorded evidence by class, and nothing meets a real condition | `tests/test_pilot_readiness.py`: `test_recorded_evidence_meets_nothing_while_real_destinations_are_disabled`, `test_a_real_condition_needs_real_destinations_and_evidence_of_its_own_class`, `test_each_condition_is_met_only_by_its_own_evidence_class`, `test_the_documented_evidence_classes_are_the_code`, `test_readiness_reads_only_the_callers_own_records`, `test_the_api_serves_readiness` | every count high: 0 met; with real destinations patched on, fixture evidence meets nothing and each real condition needs its own class; one class per condition; the documented table is the code; the endpoint counts only the caller's records (another user: 0), and a record edited to claim a real destination counts as not holding |

## Gates and concurrent revocation (2026-10-22; local only; mechanism superseded by D46)

| Requirement | Evidence | Result |
|---|---|---|
| A revocation committed while a gate waits for the application lock stops that gate | `tests/test_gate_snapshot_race.py`, `test_a_revocation_committed_while_a_gate_waits_is_refused` (disclosure gate, send gate) | a second session revokes after the gate took the attempt and before its application lock; the gate refuses. At the time (D43, REPEATABLE READ) the refusal was "the approval changed while it was being checked", and removing the approval lock was caught. Since D46 the gate reads after its locks and refuses with "approval revoked, expired or superseded" whether or not the approval row is locked; the approval lock is now tested by `tests/test_lock_order.py::test_a_write_to_the_approval_waits_for_a_gate_that_holds_it` |

## Upload evidence and rehearsal results (E5 step 2, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only (the clinic form, both Greenhouse-style
approximations, the fake API). The receiver's ledger is the oracle for what the synthetic
employer kept.

| Requirement | Evidence (`tests/test_upload_evidence.py` unless noted) | Result |
|---|---|---|
| An upload is kept as its digest and a fixed acknowledgement | `test_an_upload_is_kept_as_its_digest_and_acknowledgement_never_the_pages_id` (3 forms) | `{field, ack: attachment_shown, sha256}`, the digest the receiver stored; the page's own attachment id appears nowhere in the evidence |
| A failed upload keeps the evidence of every upload before it | `test_a_failed_upload_keeps_the_evidence_of_every_upload_before_it` (2 Greenhouse-style forms, resume then cover letter, the cover letter refused) | `abandoned`; evidence: resume `attachment_shown`, cover letter `error_shown`; the receiver kept only the resume; 0 acceptances. Before, both were lost with the exception |
| A refused or unacknowledged upload is kept as such | `test_a_refused_upload_is_kept_as_refused`, `test_an_upload_the_page_never_acknowledges_is_kept_as_unacknowledged` | `error_shown`; `none` when the page hears back too late (the receiver did keep it); both `abandoned`, 0 acceptances |
| The API route keeps the same evidence | `test_the_api_route_keeps_the_same_evidence` (2) | the draft, then the upload with `digest_matched`, or `not_kept` when the API refuses it (`abandoned`) |
| A rehearsal's result is shown as such | `tests/test_rehearsal.py`; `frontend/e2e/submission.spec.ts` | the used approval is `used_by_rehearsal` (version, time), not an invalidation; a revocation is still `invalidated` with its reason; the tracker's `last_attempt` is `rehearsed`, then `confirmed` after an approval to submit; the review page and tracker show "Rehearsal finished: nothing submitted" |

## Rehearsal: disclosure without submission (E5 step 1, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only (the clinic form, the second Greenhouse-style
approximation, the fake API). The receiver's ledger is the oracle.

| Requirement | Evidence (`tests/test_rehearsal.py` unless noted) | Result |
|---|---|---|
| A rehearsal fills and checks, then stops before submitting | `test_a_rehearsal_fills_and_checks_then_stops_without_submitting`; `frontend/e2e/submission.spec.ts` (desktop and mobile) | attempt `rehearsed`; the ledger has one upload whose digest is the approved document's; 0 acceptances and no submit request; disclosure and readback evidence, no receipt; application `needs_user_action`. Removing the runner's stop is caught |
| The approval is used up | same test | the approval is retired ("Used by a rehearsal") in the same transaction; queueing again is refused (409); one `package.approval_retired` event with `rehearsal_completed`. Not retiring it is caught |
| Submitting afterwards needs its own approval and a new attempt | `test_after_a_rehearsal_an_approval_to_submit_submits_once`; the e2e test | after approving to submit: one acceptance, two uploads (each attempt repeats every check), attempts `confirmed` and `rehearsed` |
| The send gate refuses a rehearsal on its own | `test_the_send_gate_refuses_a_rehearsal_even_if_the_runner_did_not_stop`, `test_the_send_gate_itself_refuses_an_approval_to_fill_only` | with the runner's stop bypassed: `abandoned`, 0 acceptances, no send started. Removing the gate's refusal is caught: the attempt then ends `confirmed`. Removing both makes a rehearsal submit, which the first test catches |
| Every route rehearses the same way | `test_a_rehearsal_on_the_greenhouse_style_form`, `test_the_api_route_rehearses_too` | id-mapping adapter: one upload, 0 acceptances. API route: a draft and its upload, no submit call, 0 acceptances. Removing the API route's stop is caught |
| The scope is explicit and never switched silently | `test_the_scope_defaults_to_submit_is_validated_and_is_never_switched_silently` | no scope given: `submit` (existing flows unchanged); same scope again: the same approval; the other scope while approved: 409; an unknown scope: 422; another user: 404; `package.approve` records `scope`. Swapping the scope in silently, or not storing it, is caught |

## Lever as a planned provider (2026-10-22; local only, nothing read from Lever)

The Lever URLs in these tests are fictional (company "acme", a random posting id) and are
never requested.

| Requirement | Evidence (`tests/test_lever.py` unless noted) | Result |
|---|---|---|
| Identity from known hostnames only | `test_lever_postings_are_identified_from_their_hostname_and_path` (4), `test_anything_else_is_not_lever` (5) | posting, `/apply`, tracking query and EU host: `lever`, company and posting id; tracking parameters dropped. Vendor site, company page, non-UUID id, lookalike host and a query parameter: `unknown` |
| A specification only | `test_lever_is_a_specification_only` | planned; no operations or capabilities; every routing capability `none`; CAPTCHA `expected`; login, multi-step and verification `unknown` with "unverified" (never "no"); "Planned only: no automation exists". Claiming login "no", or not expecting a CAPTCHA, is caught |
| An honest route, never another ATS's adapter | `test_a_lever_job_is_shown_unsupported_and_never_routed_to_greenhouse`; `frontend/e2e/routing.spec.ts` | manual handoff, `planned_adapter_only`, "Lever applications are not supported yet"; a Greenhouse form source changes nothing; Greenhouse capture refused (400) with 0 requests; the job page shows it. Unlinking Lever from its ATS is caught |
| The documented vocabulary is the registry | `test_the_documented_routing_vocabulary_is_the_registry` | every column of the routing-vocabulary table, Lever's included, equals `routing_view`; a drifted cell is caught |
| A form-ATS mismatch still has a path | `tests/test_reason_codes.py`, `test_a_form_from_another_ats_is_refused` | shown with a fictional Ashby posting (no specification): `form_ats_mismatch` |

## Greenhouse: page controls the job data does not list (2026-10-22; local only, no external request)

Local fixture (`gh2_dd_extras`: a phone-country selector inside the phone group and a required
dropdown the job data does not list) only. No real page was read.

| Requirement | Evidence (`tests/test_dropdown_strategies.py`) | Result |
|---|---|---|
| A control the job data does not list is a checkpoint from capture | `test_unlisted_dropdowns_are_a_checkpoint_from_capture` | both captured as blocking fields with a fixed reason, never interpreted; route `checkpoint` (`unsupported_required_control`, "2 required controls"); both unresolved in the package; approval refused; 0 disclosures. Not capturing them, or capturing them as optional, is caught |
| One that appears after approval still stops before disclosure | `test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure` | captured and approved without them; the page then shows them: `failed_safe`, "2 new field(s)", counted, never named; 0 disclosures. Dropping the run-time check is caught |

## Greenhouse: Path A record and pilot readiness (2026-10-22; local only, no external request)

No page was visited and no manual observation was recorded: every answer in these tests is
synthetic and labelled so. Results are from the cloud sandbox.

| Requirement | Evidence | Result |
|---|---|---|
| The Path A record ships pending | `tests/test_path_a.py`: `test_the_shipped_record_is_pending` | `docs/evidence/path-a.json` is `{"status": "pending"}`; every assessment is `unknown`; a record filled in for the owner is caught |
| Only the checklist's fixed choices can be recorded | `test_anything_but_the_fixed_choices_is_refused_without_echoing_it` (9 cases), `test_the_questions_follow_the_checklist` | wording, an unknown question, extra fields, another source, a bad date, a third dropdown, no answers, a guessed status and a URL are refused; no refusal echoes the value; the questions follow the checklist's 8 (question 8 for two controls); accepting free text is caught |
| Answers are advisory | `test_a_record_is_assessed_but_never_changes_support`, `test_policy_limits_hold_whatever_the_answers` (6 cases) | a candidate strategy or a blocker per answer; the registry is unchanged; search-as-you-type and partial lists stay unsupported whatever the answers |
| Readiness is derived from evidence | `tests/test_pilot_readiness.py`: `test_no_condition_is_met_today`, `test_a_condition_follows_the_registry_alone` | 0 of 7 met, not proposable, Path A pending; raising one capability to `observed` in a patched registry meets exactly that condition |
| The owner's observation meets no condition | `test_the_owners_manual_observation_meets_no_condition` | even the most favourable answers meet 0 of 7; letting Path A meet one is caught |
| The documented status is the computed one | `test_the_documented_status_equals_the_computed_one` | the table in `docs/greenhouse-readiness-gap.md` equals the computation; a drifted row is caught |
| Served to signed-in users only | `test_the_api_serves_readiness` | `GET /api/providers/greenhouse_dom/readiness` equals the computation; 401 without a session (dropping authentication is caught) |

## Question keys out of URL paths (2026-10-22; local only, no external request)

Synthetic data and local fixtures only. Results are from the cloud sandbox (PostgreSQL 16,
Redis 7); the Compose execution test, which also calls these endpoints, runs in CI only.

| Requirement | Evidence (`tests/test_api_paths.py` unless noted) | Result |
|---|---|---|
| No path carries external text | `test_every_path_parameter_is_an_internal_id_or_one_of_our_own_names` (read from the OpenAPI schema) | every path parameter is a UUID except `name` (NoEfforts' own fixture-form and provider names) |
| The key-in-path routes are gone | `test_the_key_in_path_routes_are_gone` | for an existing application, `PUT`/`DELETE …/answers/{key}`, `PUT …/consents/{key}` and `POST …/answers/{key}/draft` are 404 |
| Answers, consents, clearing and drafts take the key in the body | `test_answers_consents_clearing_and_drafts_take_the_key_in_the_body` | an answer saved, then cleared (back to `needs_user`); a consent choice and a draft refused for a question that takes neither, without echoing the key; an unknown key 404 without echoing it; malformed keys 422 before the handler; another user's application 404 on all four routes |
| Access logs | `tests/test_access_log.py` (3 tests) | the body-keyed route logs as `PUT /api/applications/{app_id}/answers`; the old key-in-path form logs as `PUT unmatched_route` 404; no key, token, e-mail, URL or id on any line, including from a real uvicorn |
| Every caller moved | the application page, `frontend/e2e/submission.spec.ts`, 51 backend test calls, `compose_tests/run_execution_test.py` | full backend suite and Playwright pass on the new routes |

## Support-state wording (2026-10-22; local only, no external request)

Synthetic data and local fixtures only. No support state changed: the wording now follows from
the evidence already recorded. Results are from the cloud sandbox (PostgreSQL 16, Redis 7).

| Requirement | Evidence (`tests/test_support_wording.py` unless noted) | Result |
|---|---|---|
| Support states follow the evidence | `test_each_providers_support_state_follows_its_evidence` | 10 providers: 5 `fixture_only`, 2 `observed_read_only` (`greenhouse_dom`, `greenhouse_readonly`), `workday` and `lever` planned, `manual_handoff` manual; ignoring observed evidence is caught |
| No live label in advance | `test_a_live_level_has_no_label_until_one_is_added_deliberately` | a spec given `live_fill` derives `live`, and its label and route qualifier lookups fail; adding a live label is caught |
| API and browser routes carry their evidence | `test_an_api_or_browser_route_always_carries_its_evidence` | no evidence → refused; every implemented API or browser provider's route reads "(local test fixture only)"; allowing a bare route is caught |
| No label claims more than its evidence | `test_no_label_claims_more_than_its_evidence` | no "live", "supported" (other than "Not supported"), "available", "compatible" or "verified"; every test-source label says "local test" and "(fictional employer)"; a label claiming support is caught |
| Every stored form source is worded | `test_every_form_source_the_capture_code_stores_is_worded` (read from the source) | the 5 sources the capture code assigns equal the label table; a missing one is caught |
| The pages write no support wording of their own | `test_the_frontend_writes_no_support_wording_of_its_own` | no served label and none of the retired qualifiers in `frontend/src`; a page that hard-codes one is caught |
| The API serves the labels | `test_the_api_serves_the_labels` | providers, discovery sources, a job's route (manual, then browser), the form and the package view; the job page and the application page get the same form label; dropping the package view's label is caught |
| Wording never changes a package | `test_wording_never_changes_the_package_or_its_hash` | the label is outside the content; rewording it changes neither the package version nor its hash |
| The same form, the same words, on both pages | `frontend/e2e/submission.spec.ts` (both Greenhouse-style forms), `phase-b.spec.ts`, `discovery.spec.ts`, `routing.spec.ts` | one label on the job page and the application page; the discover page shows the served "Local test fixtures only"; the button reads "Read Greenhouse-style test form" |

## Route reason codes and route truthfulness (2026-10-22; local only, no external request)

Synthetic data and local fixtures only; no employer, ATS or Freehire was contacted. No provider
support state changed. Results are from the cloud sandbox (PostgreSQL 16, Redis 7).

| Requirement | Evidence (`tests/test_reason_codes.py` unless noted) | Result |
|---|---|---|
| Every code but the fallback has a producing path | `test_every_code_but_the_fallback_has_a_path_and_the_fallback_has_none`, `test_each_code_is_produced_by_its_path` (13 paths) | each of the 13 codes produced by its own path: `decide`, `route_for_job` through the API, `policy.check_binding` (`no_adapter`), the discovery view (`source_record_incomplete`, `source_posting_closed`); a code added without a path is caught |
| No decision or refusal relies on the fallback | `test_every_decision_and_refusal_in_the_code_names_a_known_code` (read from the source), `test_no_destination_falls_through_to_the_fallback` (test and production) | every `RouteDecision` names a reason and every `UnsupportedDestination` a fixed code listed in `REASONS`; 576 decisions over sample destinations (origin, submit address, form source, ATS host), with and without an API grant, in test and production: none gets `no_supported_provider`, and only fixture origins outside production get an API or browser route. A refusal left on the default code is caught by all three tests |
| Codes are safe to record | `test_codes_are_fixed_identifiers_that_are_safe_to_record` | lowercase identifiers; each survives the audit sanitizer unchanged |
| The router refuses real destinations on its own | `test_the_router_refuses_a_real_destination_even_if_the_adapter_policy_accepts_it` | with `policy.adapter_for` patched to accept everything, a non-fixture origin is still a manual handoff (`real_destination_disabled`); removing the router's own gate is caught |
| A real destination is told so before any form step | `test_a_real_destination_is_told_so_before_any_form_step`; `test_freehire_imports_are_never_treated_as_form_schemas`; `frontend/e2e/routing.spec.ts` | a job on a non-fixture site: `real_destination_disabled` with the adapter policy's own message, never "Capture the application form first.", and still so after a form is attached; production: `production_disabled` before any form lookup; a fixture job or a job without an address: `no_form_captured`; imported discovery jobs follow the same rule; the job page shows it (desktop and mobile) |
| A browser refusal does not block an authorized API route | `test_a_browser_refusal_does_not_block_an_authorized_api_route` | no submit address, or a cross-origin one: API `fake_api` with the grant and credentials; without a grant the refusal stands (`no_captured_destination`) |
| The documentation lists exactly the codes | `test_the_documentation_lists_exactly_the_reason_codes` | the table in `docs/provider-architecture.md` equals `REASONS` (14 codes); a removed row is caught |
| A route is audited once per change | `test_a_repeated_route_check_is_recorded_once_and_each_change_again` | 3 identical checks → 1 row; form captured, API granted, grant revoked → 4 rows in all, the last equal to the second (a change from the previous one); removing the comparison is caught |
| The discovery view audits a linked record's route like the job page | `test_the_discovery_view_records_a_linked_jobs_route_as_the_job_page_does` | view → 1 row for the tracker job; the job page then shows the same decision and adds none; an unlinked record and another user's view (404) add none. Not auditing the view, or not deduplicating, is caught |
| The audit inventory cannot hide keys | `tests/test_audit_inventory.py` | a `record(**meta)` call fails the scan, so every event's keys stay readable |
| A posting closed before linking says so | `test_each_code_is_produced_by_its_path[source_posting_closed]` | mock feed with the posting closed at its first import: no tracker job; route "This posting was closed at its source, so it was not added to your tracker." (`source_posting_closed`), not "Import this job manually."; removing the branch is caught |
| The job page names the provider and its evidence | `frontend/e2e/routing.spec.ts` | Workday: `planned_adapter_only`, no provider line; no form: `no_form_captured`; a form captured from the local receiver: "Browser adapter (local test fixture only)", `browser_supported`, and (since the support-wording change below) "Provider: fixture_ats — Local test fixtures only", equal to what the API serves |

## Privacy, audit and baseline corrections (2026-10-21; local only, no external request)

Synthetic data and local fixtures only. Results are from the cloud sandbox (PostgreSQL 16,
Redis 7); CI results are in `docs/implementation-status.md`.

| Requirement | Evidence (`tests/test_audit_privacy.py` unless noted) | Result |
|---|---|---|
| Prohibited audit keys are redacted | `test_prohibited_keys_are_redacted` (6 categories) | every value `[redacted]` |
| Unsafe values are omitted under any key | `test_unsafe_values_are_omitted_under_any_key` (12 values) | `[omitted]` |
| Safe metadata kept; external ids become references | `test_safe_metadata_is_kept_and_external_identifiers_become_references`, `test_sanitizing_is_idempotent` | unchanged; `field` → `field_ref`; a second pass changes nothing |
| Sanitizing happens before storage | `test_record_sanitizes_before_anything_is_stored` | stored row redacted and omitted; fails when the sanitizer is bypassed |
| Route decisions audited with safe fields only | `test_route_decisions_are_audited_without_applicant_or_external_data` | 5 decisions, exactly 6 keys each, no synthetic marker |
| Generic route messages | `test_ui_route_messages_are_generic_and_carry_a_reason_code` | no form wording; `unsupported_required_control` |
| A full application leaves no applicant or posting data | `test_a_full_application_leaves_no_applicant_or_posting_data_in_audit_events` | no marker in any audit row |
| Drafts recorded by reference and reason code | `test_a_rejected_draft_records_a_reason_code_not_its_content`, `test_a_created_draft_records_a_field_reference_not_the_question_key` | `field_ref` + `invented_numbers`; no draft text |
| Logs keep the error type, never the payload | `test_unexpected_runner_errors_are_logged_by_type_only`, `test_the_egress_proxy_never_logs_destination_hosts` | type name only, no traceback; destination count only |
| Legacy audit rows repaired once, irreversibly | `tests/test_audit_repair.py`: `test_repair_sanitizes_every_legacy_row_and_a_second_run_changes_nothing`, `test_the_migration_repairs_legacy_rows_reports_counts_only_and_is_irreversible` | 18 synthetic rows: 13 changed, then 0; downgrade restores nothing; output is counts only |
| A failed repair reveals nothing | `tests/test_audit_repair.py`: `test_a_failed_repair_reveals_no_legacy_content` | type name only, nothing chained, transaction rolled back |
| Audit inventory matches the code | `tests/test_audit_inventory.py`: `test_the_inventory_lists_exactly_the_events_the_code_writes`, `test_every_documented_metadata_key_survives_the_sanitizer` | fails on a removed document row or an added code key (both checked) |
| Documents cite only existing tests | `tests/test_doc_references.py`: `test_every_cited_test_exists` | every cited test function or module exists |
| CAPTCHA claimed only where detected | `tests/test_execution_routing.py`: `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one`; `tests/test_greenhouse_dom.py`: `test_a_captcha_on_the_form_stops_before_anything_is_disclosed` | `fixture_ats` claims none; `greenhouse_dom` stops with 0 disclosures |
| Cancel echoes only its own refusal | `tests/test_execution_failures.py`: `test_cancel_reports_only_its_own_refusals` | terminal state 400; any other error stays a server error; fails with the old catch-all |
| Route endpoint is tenant-scoped | `tests/test_execution_routing.py`: `test_another_users_job_route_is_not_found_and_not_audited` | 404; no route decision recorded |
| Keyed references: stable per user and key, unrelated across users and keys | `tests/test_audit_refs.py`: `test_same_user_and_input_give_a_stable_versioned_reference`, `test_different_users_never_share_a_reference_for_the_same_input`, `test_changing_the_key_changes_every_reference`, `test_a_reference_is_not_the_legacy_unkeyed_hash` | `ref:v2:` + 32 hex; no identifier or key in it; a legacy reference becomes `[omitted]` (also inside a list) |
| The key is mandatory and never shown | `tests/test_audit_refs.py`: `test_a_missing_or_short_key_fails_closed_without_showing_it`, `test_production_refuses_a_test_only_key`, `test_the_key_is_not_in_the_settings_repr` | missing or short key: references and API start-up refused; production refuses a test-only key; the key is in no message or repr |
| Stored references are user-scoped | `tests/test_audit_refs.py`: `test_stored_references_are_user_scoped_and_hold_no_raw_key_or_secret` | two users, same question: different `field_ref`; same user: identical; no raw key or secret in the rows |
| Legacy references removed once, irreversibly | `tests/test_audit_refs.py`: `test_the_v2_migration_removes_legacy_references_and_is_idempotent` | 8 synthetic rows from 2 users: 6 changed, then 0; no legacy reference, raw key or secret in the rows or the output; downgrade restores nothing |
| Isolation failures show a code only | `tests/test_error_boundary.py`: `test_an_isolation_failure_reaches_the_user_as_a_code_only`, `test_a_refusing_runner_keeps_neither_its_address_nor_its_body`, `test_a_refusing_egress_proxy_and_failing_namespaces_keep_no_output` | outcome `browser isolation unavailable (runner_refused)`; no address, body, token, question key or traceback in the outcome, API, audit rows or app logs; fails when the raw error is stored |
| Form-capture mismatch is generic | `tests/test_error_boundary.py`: `test_a_form_capture_mismatch_shows_a_generic_message_and_a_code` (3 modes); `test_capture_refused_when_page_disagrees_with_job_data`, `test_capture_refuses_an_ambiguous_page` | 409, "unsupported or incomplete" + reason code; no field key, address or path |
| Form drift, uploads and readback give counts and fixed reasons | `test_form_changed_after_approval_stops_before_disclosure`, `test_combobox_that_does_not_keep_its_choice_is_caught_by_readback`, `test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure`, `test_page_requires_a_field_with_no_approved_answer_stops_before_disclosure`, `test_unverifiable_dropdowns_stop_before_anything_is_disclosed` | "1 new field(s)", "1 field(s) did not keep their values", "2 new field(s)", "required by the page, no approved answer", the dropdown's own refusal reason; no field key |
| Unexpected API errors are a generic 500 | `tests/test_error_boundary.py`: `test_an_unexpected_error_is_a_generic_500_logged_by_type` (route, attempts, authentication); `tests/test_execution_failures.py`: `test_cancel_reports_only_its_own_refusals` | generic body; security headers kept; log is type + method + route template; fails without the boundary |
| Expected errors unchanged | `tests/test_error_boundary.py`: `test_expected_errors_keep_their_status_and_own_messages` | 401 anonymous, 404 cross-tenant, 422 validation, 409 refusal |
| Access logs carry route templates only | `tests/test_access_log.py`: `test_access_lines_carry_the_route_template_never_the_raw_path`, `test_raw_access_records_from_the_server_are_dropped`, `test_the_real_server_prints_route_templates_only` | real uvicorn: `"PUT /api/applications/{app_id}/answers HTTP/1.1"` (the key in the body), the old key-in-path form as `"PUT unmatched_route HTTP/1.1" 404`, health 200; no question key, token, e-mail, URL, id or client address; fails without the filter |
| The web server logs no raw paths | `frontend/e2e/log-privacy.spec.ts` (development request log off; proxy failure without its URL); manual run of `next dev` and `next start` against an unreachable backend | no marker in either log; "Failed to proxy an API request to the backend (ECONNREFUSED)" |
| Retained errors are types only | `tests/test_execution_failures.py`: `test_broker_outage_after_commit_loses_nothing` | outbox `last_error` is `ConnectionError`; the broker URL and its password are not kept |
| Database errors carry no bound values | `tests/test_retained_data_privacy.py`: `test_a_database_error_never_carries_bound_values` | "SQL parameters hidden"; no answer text or e-mail; fails without `hide_parameters` |
| Library logs keep exception types only | `tests/test_retained_data_privacy.py`: `test_a_failed_task_is_logged_by_exception_type_only`, `test_the_filter_reduces_handler_errors_and_reprs_to_types` | a real eager Celery failure is logged as `RuntimeError`, no traceback, no quoted row; fails without the filter |
| Evidence keeps counts and categories | `tests/test_retained_data_privacy.py`: `test_destinations_are_classified_without_a_lookup`; `test_browser_cannot_reach_other_origins`, `test_page_altering_a_filled_value_stops_before_submit`, `test_full_run_sends_exactly_the_approved_values` | blocked: loopback >= 2, link-local >= 1, private >= 1, no host; readback `{"checked": n, "mismatched": k}`; receipt without title or path; fails when hosts are kept |

## Execution routing (2026-10-21; local only, no external request)

These are local fixture tests. The receiver, its Greenhouse-style forms and its fake API are
labelled stand-ins, and nothing claims live API or ATS compatibility.

| Requirement | Evidence (`tests/test_execution_routing.py` unless noted) | Result |
|---|---|---|
| Routing vocabulary, no live claims | `test_every_provider_declares_the_routing_vocabulary_without_live_claims` | 13 names for every provider; no `live_*` level; `greenhouse_dom`: browser_fill and custom_dropdown fixture, location_picker none, public_schema_read observed, CAPTCHA_possible unknown |
| Workday is a specification only | `test_workday_is_a_specification_only` | stage planned; every capability none; traits "expected"; status says not supported |
| Interface only where operations exist | `test_interface_is_implemented_only_where_the_operations_exist` | 9 names; manual handoff only `request_user_action`; Workday and Freehire none |
| API vs browser vs manual | `test_route_selection_api_then_browser_then_manual` | no form: manual; captured: browser `greenhouse_dom`; grant without token: browser; grant plus token: API `fake_api`; real origin: manual |
| API connector needs explicit authorization | `test_a_known_api_connector_is_never_selected_without_explicit_authorization` | token configured, no grant: browser, with the reason "no active authorization"; 0 `/fapi/` requests |
| Unsupported capability: checkpoint before disclosure | `test_an_unsupported_required_control_is_a_checkpoint_before_disclosure` | location job: route `checkpoint`, "Nothing is sent"; coordinates unresolved; approval refused; 0 disclosures. Mutation-checked |
| Adapter version mismatch | `test_an_adapter_version_mismatch_blocks_queueing_and_execution` | 409 at queue; after queueing: `failed_safe` "execution method changed"; 0 disclosures, 0 acceptances |
| Job source is not a form schema | `test_freehire_imports_are_never_treated_as_form_schemas` | after an import: 0 `JobForm` rows; every linked job "Capture the application form first."; only `search` requested; the client has no form method |
| Workday never routed to Greenhouse | `test_a_workday_job_is_shown_unsupported_never_routed_to_greenhouse`, `test_a_form_from_another_ats_is_refused`; `frontend/e2e/routing.spec.ts` | Workday job: manual "Workday applications are not supported yet", even with a Greenhouse form source; Greenhouse capture refused (400) with 0 requests; a Lever job with a Greenhouse form refused; the job page shows it (desktop and mobile). Mutation-checked |
| CAPTCHA is a user action | `test_a_captcha_becomes_a_user_action_never_an_automated_solve` | `failed_safe` "does not solve"; application `needs_user_action`; 0 disclosures; every checkpoint policy non-automated |

## Freehire discovery provider (2026-10-21; fixture only, no Freehire API request)

All of this is local fixture evidence. The oracle is the fixture's own request table
(`freehire_requests`: route, offset, limit, whether an Authorization header was present). It
runs against `fixtures/ats_receiver/freehire_fixture.py`, a stand-in shaped like Freehire's
public API reference as reviewed on 2026-10-21, with synthetic data. **Nothing here shows
compatibility with the live Freehire service.** Personal prototype only (D34).

| Requirement | Evidence (`tests/test_freehire_discovery.py` unless noted) | Result |
|---|---|---|
| Off by default; nothing requested | `test_defaults_are_off_with_no_base_url_and_no_key`, `test_disabled_by_default_and_nothing_is_requested` | default settings: no provider, no base URL, no key, no rate setting; import and healthcheck 409; 0 fixture requests; unknown provider 404 |
| No live access | `test_a_live_base_url_is_refused_before_any_request` | `https://freehire.me` refused before any request (network call patched to fail the test); nothing written |
| Status table honest; key never shown | `test_status_table_and_capabilities_never_claim_external_testing` | external configured/tested/production false; no "600" claimed; attribution "via freehire.me"; only "configured: yes/no" for the key |
| Mock never in production | `test_mock_provider_is_never_enabled_in_production` | refused |
| Documented shapes; pagination; dedup | `test_import_pages_normalizes_and_deduplicates` | 5 open records in 3 pages (offsets 0/2/4, no key); the closed posting is absent from search; top-level `work_mode` read (hybrid/onsite/remote); `enrichment.employment_type`; plain-text summary; tri-state sponsorship with basis "provider enrichment"; duplicate slug linked by job URL; no-URL record incomplete |
| `work_mode` from the top level only | `test_work_mode_is_read_from_the_top_level_only`, `test_undocumented_fields_are_not_read` | the old shape (only `enrichment.work_mode`) gives `unknown`; `last_seen_at` not read; undocumented work-mode or non-boolean sponsorship values stay unknown. Mutation-checked: an enrichment fallback fails the test |
| No raw payload kept | `test_no_raw_payload_is_kept` | stored keys are exactly the normalized fields and `raw_ref` (provider, id, fingerprint, field names); no HTML, enrichment, counters or `reality`; the tracker job gets the plain summary |
| Attribution | `test_every_listing_is_credited_via_freehire`, `test_the_mock_is_never_credited_to_freehire`; `e2e/discovery.spec.ts` | every Freehire listing and job-page source carries `{"text": "via freehire.me", "url": null}` (no documented listing URL); mock credited "local mock data (not from freehire.me)"; UI shows the credit on all 5 listings and on the job page |
| Pacing from documented headers | `test_paging_stops_when_the_documented_budget_is_used_up`, `test_without_rate_headers_nothing_is_assumed_or_waited` | `X-RateLimit-Remaining: 0` stops after 2 pages (truncated, reason quotes the headers); 2 requests; no sleep anywhere (patched to fail); without headers all pages read, no waiting. Mutation-checked: ignoring Remaining fails the test |
| 429 | `test_a_429_is_reported_with_retry_after_and_never_retried` | 503 "Freehire is rate limiting requests (Retry-After: 30 s); not retried. Nothing was changed."; exactly 1 request; no sleep; nothing written |
| Closed and stale | `test_a_posting_closed_since_is_absent_from_search_and_seen_closed_by_detail`, `test_detail_serves_a_closed_posting_and_it_never_creates_a_job`, `test_refresh_marks_a_record_gone` | absent from search: not marked stale (listing never complete); refresh sees `closed_at`: "closed at source", link and tracker job kept; detail serves a closed posting; 404 → "no longer at the source" |
| No `/status` use | `test_healthcheck_makes_no_request_and_never_uses_status` | healthcheck is configuration only (0 requests even during an outage); imports never call `/status`. Mutation-checked: a healthcheck calling `/status` fails the test |
| Unchanged re-import; changed posting; matching | `test_reimport_is_unchanged`, `test_a_changed_posting_is_recorded_and_the_users_job_is_left_alone`, `test_existing_jobs_are_matched_by_url_then_conservatively_and_never_modified` | 5 unchanged; `changed_fields` title, location with the user's edit kept; matched by job URL and by employer/title/location; existing job never modified |
| Filters on supplied data only | `test_filters_use_only_what_the_source_supplied`, `test_sponsorship_filter_matches_only_a_stated_yes`, `test_preferences_are_used_only_when_asked` | missing data = "not enough data"; stated mismatch excludes; sponsorship "offered" matches only a stated yes; preferences only on request |
| Failures change nothing | `test_provider_failures_change_nothing` (outage, bad JSON, pagination loop, timeout) | 503 "Nothing was changed"; 0 rows, 0 jobs |
| Outage never blocks the rest | `test_an_outage_never_blocks_manual_jobs_imports_or_tracking` | manual job 201, CSV import 1 created, application 201 |
| Malformed; bounded paging | `test_malformed_records_are_skipped_and_counted`, `test_paging_is_bounded_and_loops_are_refused`, `test_truncated_listing_is_reported` | 2 skipped, 5 imported; repeated cursor refused; page limit reported as the stop reason; nothing past the 10,000 window |
| Isolation; key; markup | `test_discovered_jobs_are_user_scoped`, `test_the_key_is_sent_by_the_server_only_and_never_shown`, `test_untrusted_markup_becomes_short_plain_text` | other user: empty / 404; key sent only as a server bearer, absent from responses and logs; scripts dropped, 500-character cap |
| UI, desktop + mobile | `frontend/e2e/discovery.spec.ts` | source status, import result, "Source: Freehire" with "via freehire.me" (5), missing fields, sponsorship basis, existing job linked and unchanged with the credit on its page, outage message, manual job still added |

## Submission providers, fake API and discovery (2026-10-21; local only)

All of this is **local fixture evidence**. No external service was contacted. The fake API is
NoEfforts' own contract, and the Freehire provider is a mock with an invented record shape.
The oracle for the API route is the receiver's ledger (drafts, uploads, acceptances keyed by
the idempotency key).

| Requirement | Evidence | Result |
|---|---|---|
| No live claim from a fixture | `test_no_provider_is_enabled_for_real_destinations_or_claims_live_support`, `test_real_page_evidence_is_recorded_only_where_it_exists`, `test_spec_invariants_reject_unsupported_claims` (6) | no `live_fill`/`live_submit` anywhere; `observed` only where run evidence exists; unsupported specs refused on import |
| Capabilities machine-readable | `test_capabilities_are_machine_readable_through_the_api` | `GET /api/providers`, `GET /api/execution/capabilities` → `providers` |
| Routing: real destination, nothing captured | `test_real_destinations_go_to_a_manual_handoff`, `test_no_captured_destination_is_a_manual_handoff` | manual handoff |
| Browser vs API selection | `test_browser_unless_the_api_is_authorized_configured_and_supported`, `test_observation_and_discovery_providers_are_never_routes` | API only with the user's grant + credentials + support; revoke → browser; observation/discovery never chosen |
| Grants are user-scoped and fixture-only | `test_authorizations_are_user_scoped_and_fixture_only` | non-fixture origin 400; non-API provider 400; other user's delete 404; other user still routes to the browser |
| Approval invalidated by a route change | `test_granting_the_api_retires_a_browser_approval_and_revoking_retires_it_again`, `test_missing_credentials_after_approval_stop_before_anything_is_sent` | 409 at queue (approval retired); token removed after approval → failed_safe "execution method changed", 0 API requests |
| No run without authorization | `test_without_authorization_the_api_is_never_contacted` | browser route; 0 `/fapi/` requests |
| No stale approval | `test_a_stale_approval_stops_before_disclosure` | not run; 0 POSTs, 0 disclosures |
| No wrong provider | `test_an_attempt_recorded_for_another_provider_is_refused` | failed_safe; 0 API requests, 0 acceptances |
| API happy path sends exactly the approved package | `test_authorized_api_submission_sends_exactly_the_approved_package` | 1 acceptance, key = attempt id, every value equal, upload digest = approved, no form-page request during the run |
| Refusals before disclosure | `test_refusals_before_disclosure` (schema changed, 401, 429) | failed_safe after the schema GET only; 0 disclosures |
| Outcomes after sending | `test_outcomes_after_sending` (422, 500, 429) | rejected / unknown / unknown; exactly 1 submit; second delivery ignored |
| Accepted but response lost | `test_accepted_but_response_lost_is_unknown_and_never_resent` | unknown; ledger 1 acceptance; reconcile (read-only) = accepted; still 1 submit; state left unknown; event recorded |
| Idempotency at the API | `test_the_fake_api_itself_never_accepts_one_key_twice` | same key → same draft, same receipt, 1 acceptance; incomplete → 422; status lookup by key |
| No leakage | `test_api_evidence_and_logs_carry_no_candidate_data_secrets_or_raw_ids` | email, phone, token, raw receipt, document bytes absent from evidence, events, outcome detail and captured logs; evidence holds `receipt_ref_sha256` |
| Discovery: import, normalization, dedup | `test_import_normalizes_deduplicates_and_keeps_incomplete_records_unlinked`, `test_a_posting_the_user_already_tracks_is_linked_not_duplicated` | 5 records → 3 tracker jobs (tracking-parameter duplicate merged); existing job linked; URLs preserved; ATS "unknown" for the fixture origin |
| Discovery: unknown stays unknown | `test_missing_data_stays_missing_and_source_facts_stay_out_of_the_profile` | sponsorship yes/unknown/no as stated; location `None`; workplace `unknown`; no salary or eligibility; 0 work-authorization rows |
| Discovery: stale, unchanged, scoped | `test_reimport_is_unchanged_and_stale_records_are_marked_not_deleted`, `test_discovered_jobs_are_user_scoped` | re-import 5 unchanged; missing → stale, tracker job kept; closed → stale; relisted → un-staled; other user sees nothing |
| Discovery → application route | `test_application_route_is_a_manual_handoff_until_a_form_is_captured`; `tests/test_reason_codes.py` | incomplete → "Import this job manually." (`source_record_incomplete`); closed before linking → `source_posting_closed`; uncaptured → "Capture the application form first."; real origin → manual; captured fixture form → browser `greenhouse_dom` |
| Checkpoints, never solved | `test_no_checkpoint_is_ever_completed_by_noefforts`, `test_no_solver_or_evasion_code_exists`, `test_manual_handoff_spec_cannot_fill`; existing `test_captcha_stops_before_anything_is_disclosed` and the emailed-code round tests in `test_execution_security.py` | no automated checkpoint; only an emailed code typed by the user resumes; no solver or stealth library in `app/` |

## Id-only page mapping, v2 fixture and adapter, output privacy (2026-10-20)

Everything here is **local fixture evidence**. Nothing in this section touched Greenhouse or
any real employer, and none of it shows that a real page can be filled or submitted.

| Requirement | Evidence | Result |
|---|---|---|
| Unique, labelled, type-suited control per API field | `test_every_api_field_maps_to_exactly_one_labelled_control` | 12/12 mapped on v2 job 5020001 |
| Ambiguous / mislabelled / missing controls refused | `test_ambiguous_or_mismatched_mappings_are_rejected` (3 modes); capture 409 | refused, never guessed |
| Search picker and hidden coordinates not filled | `test_text_question_rendered_as_search_picker_is_unsupported_not_typed`, `test_location_job_is_a_checkpoint` | unsupported → checkpoint |
| Preferred name, unknown conditions not guessed | `test_preferred_name_and_unknown_condition_are_not_guessed` | `needs_user`; conditional value `None` |
| Notice is not consent | `test_notice_is_not_a_field_and_no_consent_is_invented` | no checkbox invented |
| Full run, values verified at the receiver | `test_full_run_sends_exactly_the_approved_values` | combobox values `1`/`913`/`0`, preferred name as typed, upload digest = approved, readback 0 mismatches |
| Combobox value readback | `test_combobox_that_does_not_keep_its_choice_is_caught_by_readback` | abandoned, 0 acceptances |
| Drift after approval stops before disclosure | `test_drift_after_approval_stops_before_anything_is_disclosed` (5 modes: duplicate id, label, missing, new question, swapped options) | failed_safe, 0 disclosures |
| Outcomes, no retry | `test_outcome_classification` (6 modes) | rejected / unknown / abandoned as listed; second delivery ignored |
| Original fixture and routing unchanged | `test_greenhouse_adapter.py`, `test_original_fixture_still_routes_to_the_original_adapter` | passed |
| Output privacy (allowlist, aliases, guard) | `test_success_output_has_aliases_and_no_markers`, `test_failure_paths_print_types_only`, `test_guard_rejects_unknown_strings_and_derived_values` | no marker on success or failure paths; suppressed output on a guard failure |
| Mapping evidence collector (B2 code) | `test_mapping_evidence_on_the_v2_fixture`, `..._reports_ambiguous_and_absent_explicitly`, `test_blocked_dependency_marks_rendering_possibly_incomplete` | per-field ids, labels, roles, visibility; denied script → "may be incomplete" |
| Same collector in the isolated container | Compose `s_readonly_mapping_in_container` | CI #34 (`6d0a437`): passed; execution-compose 80 checks, 0 failed |
| UI, desktop + mobile | e2e "Greenhouse-style v2 form …" | local `submission.spec.ts`: 20 passed; CI #34 full Playwright suite: 26 passed |
| Approval bound to the execution method | `tests/test_approval_binding.py` (9) | new route or version → queue refused and approval retired; change after loading → stopped at the gate; tampered attempt adapter → failed_safe; pre-binding approvals kept while unchanged; 0 disclosures in every refusal |
| B2 limits enforced | `tests/test_gh_readonly.py` limit tests | navigation, redirects, request budget, received-bytes stop, retained DOM, deadline, watchdog, output size; fixtures only |
| Options only on open | `test_options_rendered_only_on_open_are_not_observable_not_a_mismatch` | `not_observable_at_load` |
| Widget inspection (local only; not approved for a real page) | `tests/test_widget_inspection.py` (18), Compose `s_readonly_widget_inspection_in_container` | open/close only, nothing selected; action, time and request budgets; submission cancelled, upload POST and navigation refused before sending, same-origin GET data request refused; challenge, dialog, file chooser, address change stop; receiver saw only the page GET |
| Workflow entry point in a fresh process; explicit outcome | `tests/test_readonly_cli_process.py` (3) | `python -m … --inspect-widgets` against the receiver: navigation through the filter, inspection completed, exit 0; injected filter failure: page never requested, exit 6 within seconds; no browser left behind; public output has no traceback or marker. Mutation-checked (entry point misplaced; filter not fail-closed) |
| Detector limits (independent widget model) | `tests/test_widget_detector.py` | portal, unlinked popup, wrapper state and delayed lists: found and compared. Late lists, lists without roles, and lists waiting on refused data: opened, not observable. Silent widget: undetermined. Wrong click target: not opened. Virtualized list: partial and never compared. Refused data requests published as path shapes only |
| Required signals and execution rule | `tests/test_required_signals.py` | signals recorded separately (attachments included). An unmarked required field runs with its answer. A page-required field with no approved answer is refused before disclosure (ARIA or label marker). Mutation-checked against the old rule |
| Real posting, run #9 (diagnostic re-observation) | run [39612152070](https://github.com/KevinD003/AutoApply/actions/runs/39612152070) on `e1bd9e7` (pinned branch, CI #52) | workflow success; observation `completed`. A 3×200; 1 navigation, 26 GET, 0 non-GET; 24 actions on 12 dropdowns. All 12 `not_opened`: no opening evidence **within the 600 ms window** for a click on the control (not proof that they cannot open); 0 DOM change. Refused data requests all `GET /locales/*/*.json` (4 at load, 7 during actions). Required evidence consistent for 19 of 19 mapped fields; the resume is required by its group |
| Dropdown strategies (adapter, fixture only) | `tests/test_dropdown_strategies.py` | click, ArrowDown, single trigger, locale-at-load, delayed and preselected-first: the exact approved option is submitted. Not opened by any strategy, type-only, two triggers, network-loaded, too slow, virtualized and duplicated: refused before disclosure. Ignored or wrong choice: caught by readback, never submitted. Dropdowns the job data does not list: a checkpoint from capture, or a stop before disclosure if they appear after approval. Mutation-checked (first option; network) |
| Run-#9 signature vs fixtures | `test_run9_signature_is_consistent_with_a_locale_gate_but_does_not_prove_it` | a locale-gated widget under the inspection policy shows run #9's signature; an inert one shows it without the requests. Consistency only |

Fixture assumptions (not observed on any real page): how comboboxes open and select, option
values, the upload endpoint and status element, JSON submission, the confirmation message and
condition triggers.

## Read-only Greenhouse check: code and fixture evidence (2026-10-20)

- **Approval.** The user approved permissions A and B for one posting, on condition that no
  employer or person name goes into the repository. C and D are not approved.
- **Code-tested revision:** `86fa55e`. CI #30
  [39428565520](https://github.com/KevinD003/AutoApply/actions/runs/39428565520) passed all four
  jobs. execution-compose: **76/76**, including `s_readonly_observation_in_container`:
  - the fixture form was read in the isolated browser (15 fields);
  - the page's on-load POST was blocked;
  - 0 disclosures at the receiver.
- **Local:** `tests/test_gh_readonly.py` 10 passed; with `test_greenhouse_adapter.py`, 34
  passed.
- **Not run against Greenhouse yet.** The development sandbox's network policy denied
  `boards-api.greenhouse.io` (403 at the environment proxy, one attempt, not retried). The real
  run is the manual workflow `greenhouse-readonly.yml`, which waits for the repository secret
  `GH_READONLY_POSTING`.

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
| Form capture refuses real posts | `test_real_greenhouse_posts_are_not_read` | — |
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
| Code accepted, reply lost (D50) | the code step's timeout → `unknown`; the worker may move `needs_user_action` → `submitted_unconfirmed` | `test_an_unknown_result_after_the_code_is_quarantined_and_never_sent_again` (receiver `verify_drop`) | pass, oracle 1, no second send in a 3 s window, re-queue refused | Before D50 the transition was refused: the worker crashed and the application stayed "needs your action" although the employer had it |
| Worker died in the code wait (D50) | sweep → `unknown`, checkpoint expired, held code erased | `test_the_sweeper_quarantines_a_worker_that_died_waiting_for_the_code` (another user's stale attempt re-pended in the same sweep) | pass, oracle 0 accepted, the challenge never completed | Before D50 the sweep raised and rolled back every stale attempt in its batch, every 15 s |
| One stale attempt cannot be recovered (D50) | a savepoint per attempt; counted in `errors` | `test_one_row_that_cannot_be_recovered_does_not_stop_the_others` (a database error injected after the row's changes) | pass: the others recovered, the failing one unchanged and recovered by the next sweep | — |
| No transition listed twice (D50) | AST scan of every dict literal in `app/` | `test_no_dict_literal_in_the_backend_repeats_a_key` | pass | ruff checks literal keys only |
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
