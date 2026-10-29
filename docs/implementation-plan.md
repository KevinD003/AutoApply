# Implementation plan after the legacy audit

Status: 2026-10-27; code references are to NoEfforts `3af29f0` (Q1, D50) unless marked; C6 (D51) landed afterwards as `b6e4cf4`; completeness-critic follow-through (G1, G4-G7, G9-G11, G17) applied.

Finding ids (gh-/la-/ans-/pl-/sec-), "map Qn" and "critic Gn/Ln/Cn" refer to the review's working notes, which are not committed. C1-C18 and L1-L4 are the preparation steps listed in `implementation-plan.md` (§0 and "Remaining preparation steps"); `docs/implementation-status.md` names the ones already implemented or referenced.

Slices are prioritised and independently testable. Each one reuses existing NoEfforts work,
fits the provider-admission framework (`backend/app/modules/providers/admission.py`) and can
proceed while live access is blocked.

Inputs: `legacy-audit.md`, `freehire-first-architecture.md`, `reliability-test-plan.md`,
`outcome-diagnostics.md`, the Phase C critic list (steps C1-C18) and the C6 final spec, implemented
as D51 in `b6e4cf4` (the critic list and the spec are working notes of the review and are not
committed).

## 0. State of play (CONFIRMED)

| Item | State | Evidence |
|---|---|---|
| C1, C2 (guards; only resolved answers are sent) | Done | `35aa0c5` |
| C3-C5 (fact statements, legal misreads, sensitive topics become checkpoints) | Done | `7669c61` (D49) |
| Q1 (an unknown outcome in the code step is quarantined; the sweeper recovers each attempt alone) | Done | `3af29f0` (D50; `backend/tests/test_code_wait_quarantine.py`). Found by the static code map made for this review |
| C6 (answer-bank scope) | Done | `b6e4cf4` (D51; the narrowing-only check, 1,315,200 form resolutions with 0 violations; the wording table of 1,037 rows; the five race tests failing against `3af29f0`'s code as described; the full results in `docs/implementation-status.md`); new `backend/app/modules/preparation/bankscope.py`, `backend/migrations/versions/b29cba6e1f6e_answer_bank_help_text.py`, `backend/tests/test_bank_scope.py`, `backend/tests/test_bank_scope_api.py`, `backend/tests/test_bank_races.py`; `backend/tests/test_migrations.py::test_c6_saved_answers_keep_their_key_and_gain_no_help_text` |
| S2 (outcome integrity and funnel) | Done | D53; `backend/tests/test_funnel.py`, `test_outcome_races.py`, `test_application_events_db.py`, migration `e3a91c5d7b20`; results in `docs/implementation-status.md` |
| S4 (legacy collision corpus and static guards) | Done | D54; `backend/tests/legacy_collisions.json` (244 rows) driven by `test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome`, `backend/tests/test_forbidden_capabilities.py`; the rows that resolved wrongly became checkpoints in `classify.py`/`resolver.py` (narrowing only); results in `docs/implementation-status.md` |
| C7-C18 | Not started | "Remaining preparation steps" below |
| S7 (live-read gate) | Done in code, not yet run | D55; `backend/app/modules/discovery/approve.py`, migration `4bc9c342d34c`, `backend/tests/test_freehire_live_read.py`; owner statement on the competitor rule recorded |
| S8 (watched searches, delete) | Done in code, not yet run against Freehire | D56; `backend/app/modules/discovery/watch.py`, migration `29588d78e7e1`, `backend/tests/test_freehire_watch.py`; the worker task `noefforts.check_discovery_watches` |
| Live discovery | Possible for the owner: one approved run (D55) or a watched search checked as often as once a minute (D56); not yet run (the sandbox proxy refuses `freehire.me`) | `freehire-first-architecture.md` §11; `docs/discovery.md` "Live read", "Watched searches" |
| Live execution | Blocked (pilot permissions 1-4; admission capped at `rehearsal_ready`) | `docs/live-pilot-gate.md:22-35`; `admission.py:86-87` |

**Coordination (done).** The C6 spec cited decision D50, which Q1 took. C6 is recorded as
**D51** (`docs/decisions.md`), and its receiver change (the `bank_question` mode)
is applied on top of `3af29f0`'s `fixtures/ats_receiver/receiver.py`.

## 1. Rules every slice follows (CLAUDE.md)

- Set the owner's git identity before committing; no AI attribution lines.
- Fixtures only; real destinations stay refused; no live request without its own approval.
- The resolver stays LLM-free; a new question pattern needs resolver tests; anything not clearly
  understood becomes a checkpoint. A preparation slice may only *narrow* (turn a resolved answer
  into a checkpoint), never make a new answer resolve, unless the slice says so explicitly.
- Every new query is scoped by `user_id`, with a cross-tenant 404 test.
- Outcomes in tests come from the receiver ledger, never from NoEfforts' tables.
- A change to package content shape bumps `SCHEMA_VERSION` deliberately (all in C18).
- No tracing or screenshots in execution; no retry after `disclosure_started_at` or `sending`;
  every worker write fenced by `generation`.
- Run `uv run ruff format .` after the last edit; record the commands actually run in
  `docs/implementation-status.md`; kill only this project's test servers (3100/8100, 8799, 8798).
- Write the failing test first; record the failure and the pass.

## 2. Slices

Sizes: S (≤ 1 day of focused work, a few files), M (several modules or a migration), L (new
capability).

### Owner decisions this plan asks the owner to record (no code)

- **Keep the bot-check stop** (`legacy-audit.md` R5, H13). NoEfforts stops on any reCAPTCHA or
  other challenge element, which the legacy bot deliberately ignored. Never narrow
  `CHALLENGE_SELECTORS` (`backend/app/modules/execution/adapters/greenhouse.py:29-33`) as a side
  effect of other work, and never change anything with the aim of affecting a score. Any change to
  the stop needs a recorded decision in `docs/decisions.md` and the Greenhouse terms review
  (`docs/live-pilot-gate.md:19`). The possible cost, that real forms stop at load or after the
  final click (HYPOTHESIS, `legacy-audit.md` H13), is accepted; the S5 fixture `gh_challenge_after_submit` pins
  the after-click behaviour.
- The decisions already listed in `freehire-first-architecture.md` §12, and the S2 choices
  (1) and (4) below (S2 uses safe defaults until the owner chooses).

### S1. C6 answer-bank scope — **done** (`b6e4cf4`)

- **Goal:** a saved answer is reused only where it stays true. Employer-relative ("this company",
  "previously worked for", "applied before"), time-bound (start date, availability), place-bound
  (relocation), pay (salary) and repeated or follow-up wordings are never saved or reused; help
  text joins the bank key; concurrent saves never return 500.
- **Status:** done in `b6e4cf4` on top of `3af29f0` (decision D51); results in
  `docs/implementation-status.md`.
- **Files:** new `backend/app/modules/preparation/bankscope.py`; modified
  `preparation/resolver.py` (`bankscope.reason()` after `_base()`; `relocation` and
  `salary_expectation` join `NO_BANK`), `preparation/router.py` (refusal before the typed answer is
  written; one `INSERT … ON CONFLICT … DO UPDATE … RETURNING`; delete by id and user),
  `preparation/models.py` (nullable `answer_bank.help_text`), `preparation/package.py` (the same
  question twice on one form never takes a saved answer), `preparation/fixtures/tricky.html`; new
  migration `backend/migrations/versions/b29cba6e1f6e_answer_bank_help_text.py`;
  `fixtures/ats_receiver/receiver.py` (`bank_question` mode); frontend
  `src/app/(app)/answers/page.tsx`, `src/app/(app)/applications/[id]/page.tsx`,
  `src/components/AnswerInput.tsx`, `src/lib/api.ts`; docs `answer-policy.md`, `decisions.md`
  (D51), `implementation-status.md`, `evidence-matrix.md`, `architecture.md`.
- **Tests:** `tests/bank_scope_wordings.json` with `tests/test_bank_scope.py`
  (pure; for example `::test_bank_scope_table`, `::test_relocation_and_salary_are_never_bankable`,
  `::test_a_saved_answer_needs_the_same_help_text`); `tests/test_bank_scope_api.py` (save refusals
  return 400 with a reason; `::test_saved_answers_stay_per_user` for tenancy);
  `tests/test_bank_races.py` (five deterministic race tests: no 500, one row, both changes
  counted, a second delete is 404); `tests/test_migrations.py::test_c6_saved_answers_keep_their_key_and_gain_no_help_text`;
  updated `test_question_safety.py`, `test_question_safety_api.py`, `test_resolver.py`,
  `test_preparation.py`, `test_package_contract.py`, `test_sending.py`,
  `test_execution_validation.py`, `execution_harness.py`; Playwright `frontend/e2e/phase-b.spec.ts`.
  Receiver: in the `bank_question` mode a stable required question is answered from the bank on a
  second application, and deleting that saved answer while an attempt runs stops it with the
  ledger at 0 accepted (`test_execution_validation.py::test_every_protected_mutation_stops_a_running_attempt`).
- **Proves:** `reliability-test-plan.md` R8.12, R8.13, R12.4 (R8.11's NEW rows come with S4);
  legacy LD-26, LD-30, LD-31, LD-39 are guarded for the wordings `bankscope.py` recognises (D51
  lists known misses, such as a named employer without deixis; a question it does not recognise
  may still be offered for saving, `docs/answer-policy.md` row 5).
- **Unchanged:** `SCHEMA_VERSION` (2) and `RESOLVER_VERSION` ("deterministic-1") did not move
  (`backend/app/modules/preparation/package.py:47-48` at `b6e4cf4`; D51: "no content key added"). No bank row deleted or re-keyed. Packages containing
  a narrowed row get a new version at the next rebuild and lose their approval (intended; local
  packages only).
- **Blockers:** none.
- **Size:** M (done).

### S2. O1 outcome integrity and funnel — **done** (D53)

- **Goal:** the tracker can tell a receipt-confirmed submission from a user claim, records
  outcomes with a source and a date, and can record an assessment.
- **Changes:**
  1. A user move `submitted_unconfirmed → submitted_confirmed` requires stated evidence (the same
     15-character rule as `/reconcile`, `backend/app/modules/applications/router.py:42-46`) and is
     recorded with `source=user_claimed`; the worker's receipt keeps `source=receipt`.
     (Alternative for the owner: remove the user move and route it through `/reconcile` only.)
  2. `Outcome.assessment_received` (PostgreSQL enum `app_outcome`: `ALTER TYPE … ADD VALUE`
     migration; the UI label "Assessment received").
  3. Outcome events gain nullable `occurred_on`, `source`, `evidence_note`; an audit `record()`
     with the value and source only.
  4. An outcome other than `withdrawn` on an application that never reached a submitted state is
     refused with a reason code (or flagged, owner decision).
  5. `GET /applications/funnel`: per-user counts from states and events, with denominators and a
     "too few to compare" note (`outcome-diagnostics.md` §1.2); tracker page section.
- **Status:** done (D53); results in `docs/implementation-status.md`. The owner's choices (1)
  and (4) use the safe defaults (keep the user move with evidence; refuse), each a code switch.
- **Files:** `backend/app/modules/applications/{states,service,router,models}.py`, new
  `backend/app/modules/applications/funnel.py`, migration
  `backend/migrations/versions/e3a91c5d7b20_outcome_integrity.py`,
  `frontend/src/app/(app)/tracker/page.tsx`, `frontend/src/app/(app)/applications/[id]/page.tsx`,
  `frontend/src/components/ExecutionCard.tsx`, `frontend/src/lib/api.ts`; docs `audit-events.md`,
  `decisions.md` (D53), `architecture.md`, `outcome-diagnostics.md`, `reliability-test-plan.md`,
  `evidence-matrix.md`, `implementation-status.md`, `legacy-audit.md`.
- **Tests:** `tests/test_applications.py` (R6.7, R14.1-R14.4), new `tests/test_funnel.py`
  (R13, R14.5), new `tests/test_outcome_races.py`, new `tests/test_application_events_db.py`,
  `tests/test_audit_privacy.py` (no free text in outcome audit rows), `tests/test_migrations.py`;
  Playwright `frontend/e2e/phase-a.spec.ts`, `submission.spec.ts` and new
  `tracker-outcomes.spec.ts`. Receiver ledger: a receipt-confirmed
  submission counts once in the funnel and matches the ledger's single acceptance.
- **Proves:** legacy LD-50 to LD-52 cannot recur; future diagnostics have trustworthy inputs.
- **Blockers:** none. Choices (1) and (4) use the safe defaults in §4 until the owner
  chooses otherwise.
- **Size:** M. No package content change, no approval invalidation.

### S3. J1 job state and prior-application signals — **done** (D59)

- **Goal:** a job whose source says it is closed, an excluded job, or a role that looks like one
  the user already applied to is visible as such before preparation and approval.
- **Changes:** a discovery refresh that finds `closed_at` or a 404 on a linked job sets a
  "source says closed" flag on the job (the user's own `status` is not overwritten); approval is
  refused with a reason code while that flag or `excluded` holds, until the user states it is
  still open (an audited user action); "possible duplicate" when another job of the same user
  with the same `employer_key` and normalized title (and location when both have one) has an
  application past `draft`, which also catches a Freehire repost (a new slug for the same
  employer and title, `freehire-first-architecture.md` §2.2); the job page and Discover row show
  the existing application's state and outcome.
- **Files:** `backend/app/modules/discovery/service.py`, `backend/app/modules/jobs/{router,service}.py`,
  the approval path in `backend/app/modules/preparation/` (a check outside package content),
  `frontend/src/app/(app)/jobs/[id]/page.tsx`, `discover/page.tsx`, reason-code docs;
  `fixtures/ats_receiver/freehire_fixture.py` (the `fh_repost` mode).
- **Tests:** R5.9 (including the `fh_repost` fixture mode), R5.10, R5.11, R9.8, R12.5, R13 rows of `reliability-test-plan.md`; `tests/test_reason_codes.py`
  for the new codes; cross-tenant (B never sees A's applications in either signal).
- **Proves:** legacy LD-11 and the wrong-posting part of LD-41 are visible before any disclosure.
- **Blockers:** owner decision "warn or block" for possible duplicates (`freehire-first-architecture.md` §12, item 5).
- **Size:** M.

### S4. T1 legacy collision corpus and static guards (tests first) — **done** (D54)

- **Goal:** the wording traps the legacy bot fell into are permanent regression tests, plus guards
  for capabilities NoEfforts must never gain.
- **Changes:** `tests/legacy_collisions.json` (synthetic wordings and option lists from
  `reliability-test-plan.md` R8.1-R8.11, plus R8.16: degree strings are never mapped by prefix,
  and the R2.9 resolver row: a "select all that apply" question resolves only to an exact approved
  set) driven from `tests/test_resolver.py`; a static test
  that no module under `backend/app` imports a mailbox or IMAP client (R7.5); a static test that
  no execution or browser code calls `screenshot(`, `tracing.start` or `record_video` (R11.4).
  Any row that fails is fixed only by turning the wrong resolution into a checkpoint.
- **Files:** tests only, unless a row fails (then `preparation/classify.py`/`resolver.py`, narrowing).
- **Status:** done (D54). Rows failed on the previous resolver (47 of the first 164; 104 of the
  final 244, the rest pinning behaviour that already held), so `classify.py` and `resolver.py`
  changed, each change a checkpoint where an answer was given; the guards cover the whole
  repository outside the frontend, not only `backend/app` and execution. Results in
  `docs/implementation-status.md`.
- **Proves:** LD-23 to LD-28, LD-30, LD-47, LD-48 (answer side), U8, U9; U1, U11 guards.
- **Blockers:** none. Run after S1 so the C6 tables are not edited twice.
- **Size:** S as planned; M as built (the failing rows).

### S5. X1 fixture variants from legacy hints (admission framework) — **done** (D62, 2026-10-28)

Done as planned, with `gh2_option_unlisted`, `gh_security_code_other`, `gh_consent_blocking`,
`gh2_phrase_no_confirmation`, `fapi_receipt_other` and the generic `accepted_elsewhere` added
while mapping each scenario to a test; a second page is a stop, not filled.

- **Goal:** turn the legacy author's real-page notes (`legacy-audit.md` R7, HYPOTHESIS) into
  fixture variants that the Greenhouse adapters must handle by stopping or by verified success,
  without claiming the real pages behave that way; and give admission a required scenario for
  every capability that changes what is sent.
- **Changes (fixtures):** receiver modes `gh_phrase_in_body`, `gh2_phrase_in_body`, a fixture job
  slug containing "confirmation"/"thanks", `gh_security_code_boxes` (8 one-character inputs and a
  disabled button; filled only with the code the user typed), `gh2_autofill_overwrite`,
  a consent banner plus an in-form "I agree" control, `gh_challenge_after_submit` and the same mode for v2 (a form that loads clean and shows a challenge
  only after the final click: never `submitted_confirmed`, never re-clicked, ledger acceptances
  asserted; `reliability-test-plan.md` R4.9b), `gh_group_untick` (the page unticks one approved box of a checkbox group;
  `reliability-test-plan.md` R2.9) and a two-page mode such as `gh2_two_steps` (`reliability-test-plan.md` R2.10). Each mode is marked FIXTURE
  ASSUMPTION in `fixtures/ats_receiver/README.md`, and each test is named after the admission
  scenario it exercises (`rejection_is_not_confirmation`, `readback_mismatch_stops_before_submit`,
  `code_entered_by_user_only`, `challenge_stops_before_disclosure`).
- **Changes (admission, NEW scenarios):** add to `CAPABILITY_SCENARIOS`
  (`backend/app/modules/providers/admission.py:176-184`) `custom_dropdowns` →
  `unlisted_option_is_checkpoint`, `location_picker` → `location_exact_or_checkpoint`,
  `confirmation_detection` → `confirmation_bound_to_attempt`; and require
  `each_step_read_back_before_next` for any provider whose `multi_step` trait is not "no". Today
  `required_scenarios` reads capabilities only (`admission.py:342-344`), so the trait rule is a
  small extension. Each new entry makes
  `tests/test_provider_contracts.py::test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap`
  demand a ledger test for every implemented provider that claims the capability (gaps are allowed
  only for pre-I2 providers), so each entry lands together with its tests in
  `tests/provider_contracts.py` (`SCENARIO_TESTS`).
- **Files:** `fixtures/ats_receiver/greenhouse_like.py`, `greenhouse_v2.py`, `README.md`;
  `backend/app/modules/providers/admission.py`; `tests/test_greenhouse_adapter.py`,
  `tests/test_greenhouse_dom.py`, `tests/provider_contracts.py`.
- **Proves:** `reliability-test-plan.md` §1.0 items 4, 6 and 12, R2.7-R2.10, R4.9b, R6.4, R6.5, R7.4, R11.8; LD-01,
  LD-02, LD-36, LD-48 (readback), F15, U10.
- **Unchanged:** no admission stage changes (`fixture_only` stays the ceiling of what fixtures
  prove; `tests/test_provider_admission.py::test_nothing_passes_the_real_destination_cap`); the
  challenge stop is not narrowed (owner decision above).
- **Blockers:** none. **Size:** M-L (L with the two-page fixture).

### S6. F1 Freehire contract hardening and documentation refresh (fixture-only)

- **Goal:** the discovery client matches the 2026-10-26 Freehire facts and avoids false
  "updated" churn; the docs stop stating superseded terms.
- **Changes:** fingerprint only the documented fields NoEfforts reads (exclude `reality` and
  counters) with a fixture mode `fh_reality_tick` (R9.4); tests for a tagged URL and an
  aggregator URL (R9.5, R9.6); the undocumented-field test extended (R9.7); backoff across runs:
  a per-user "not before" time stored from `Retry-After` after a 429, with imports refused until
  then by a typed `DiscoveryError` and no automatic re-run (R9.2,
  test_an_import_before_retry_after_is_refused (NEW); `freehire-first-architecture.md` §7);
  imports moved to a background job with the same budget; a refresh control on Discover; a per-user delete of
  discovered rows; discovery restricted to an owner allow-list in config (`freehire-first-architecture.md` §10); doc refresh of
  `docs/research/freehire.md` and `docs/discovery.md` (terms date, the removed 30-day deletion,
  the published 600/min keyless figure and the pending strict mode, the `ab47628` pin) and D34's
  retention wording. The doc refresh is done (D34 amendment of 2026-10-26).
- **Files:** `backend/app/modules/discovery/{provider,service,router,models}.py`, a migration
  for the "not before" time, `backend/app/core/config.py`,
  `fixtures/ats_receiver/freehire_fixture.py`, `frontend/src/app/(app)/discover/page.tsx`, docs.
- **Tests:** `tests/test_freehire_discovery.py` additions; cross-tenant for delete; outage tests
  unchanged.
- **Blockers:** none for code; the doc refresh quotes the review's saved page copies
  (working notes, not committed) and must be re-checked on the day of any live run.
- **Size:** M.
- **Status (D67, 2026-10-28): done.** The fingerprint reads only the documented fields
  NoEfforts uses; a `Retry-After` holds the user's next import or refresh back, before any
  request or approval; referral codes are dropped for deduplication; Discover has a refresh
  control. Imports stay inside the request (D67 says why); the owner allow-list covers the
  reads that reach Freehire (S7, S8).

### S7. F2 live-read readiness — **done in code** (D55); no live read made yet

- **Goal:** everything a single approved live read needs, except the approval.
- **Changes:** call `resolve_public_destination` before any non-fixture fetch (R10.5); a
  single-use run approval stored as data (exact query, page limit, time window, retention
  statement), consumed once, modelled on the read-only run approvals
  (`tests/test_gh_readonly.py::test_refused_unless_this_exact_posting_is_approved`); the base-URL
  check accepts the live origin only with such an approval and only for the allow-listed owner.
- **Blockers to *running* it:** the owner's competitor-rule statement, retention statement,
  reachability and a same-day terms re-read (`freehire-first-architecture.md` §11). Writing the code needs none of them, but
  the change to the base-URL check must be reviewed.
- **Size:** M.
- **Status (D55, 2026-10-28):** done in code, ahead of S6 at the owner's request. The owner gave
  the competitor-rule statement; each run's approval names its retention statement. Left to
  run it: reachability (the cloud sandbox refuses `freehire.me`) and the same-day terms
  re-read. From S6, only the owner allow-list for *live* reads was taken; S6 is otherwise open.
  S8 (D56) then added watched searches and, from S6, the per-user delete of discovered rows.

### Remaining preparation steps (critic C7-C18), placed

| Step | What | Size | Depends on | Placement and note |
|---|---|---|---|---|
| C11 | Protected-fact choice dead ends: a "State" select with the profile's state maps by unique exact option; otherwise a per-application answer that is never banked | S | C6 (bank refusals) | **Done (D57, 2026-10-28):** only a list naming every US state is mapped, for a US residence; a City list is never picked from the profile; any other State, City or Country list is the user's answer for this application, never saved, tied to the fact |
| C10 | Fact values must fit the field (length, email, URL scheme; one candidate link) | S | — | **Done (D54, D58, 2026-10-28):** a fact answer that fails `validate_value` is never sent (S4); a link question gets the profile's link only when exactly one is of its kind, read from the host; several are the user's to give; the review page shows why |
| C7 | Consents and answers tied to the field fingerprint and a keyed value digest | M | C6 | **Done (D60, 2026-10-28):** each answer and consent stores its question's fingerprint; a changed question asks again; "disclose" covers a keyed digest of the exact answer |
| C8 | Disclose path end to end with the receiver ledger; "decline to self-identify" mapping | M | C7 | **Done (D61, 2026-10-28):** the receiver ledger shows "Include" sends the answer and "Don't disclose" sends nothing (optional) or the form's one decline option (required); one bank policy for the equal-opportunity topics. Closes R3.4 |
| C9 | Salary and relocation period and currency | S | C6 (they are no longer bankable) | **Done (D63, 2026-10-28):** a salary is sent only in the units the question allows (currency by code, sign or help text; period); a bare number only when both are stated; relocation unchanged (S4). The `version` key fix is [shape] → C18 |
| C12 | Review UI edit, clear, optional answers, cover-letter selection, destination shown | M | C10, C11 | **Done (D64, 2026-10-28):** change, clear and optional answers where the resolver allows input; cover letter chosen or left out; "Sends to …" with a fixture or employer label; controls outside the package content |
| C13 | Audit and approval wording, reason codes, revoke-while-queued | M | — | **Done (D65, 2026-10-28):** nine approval reason codes listed in `approval-reasons.md`; revoking cancels an attempt no worker has taken, leaves a held one to the gates, is refused after the send gate, and is audited with what it did |
| C14 | Read-only version diff | M | — | **Done (D66, 2026-10-28):** two stored versions compared by label and shown value (answer, question or basis changed); on each history row and since the approved version; never builds or records |
| C15 | Drafting hardening before any provider | M | C4/C5 regexes | **Done (D68, 2026-10-29):** numbers only from cited facts; legal-status and sensitive mentions refused; job text and questions quoted as untrusted data in the one prompt shape (R11.9); accept compares the cited facts and the request, re-checks the question, and gives reason codes; the user can reject a draft, which erases its text |
| C16 | Credentials as grounded facts | M | C15 | **Done (D69, 2026-10-29):** approved, unexpired credentials ground a draft; a draft names a licence only by citing one; licence and certification wording is never saved for reuse (400) |
| C17 | Retention and deletion of documents | M | — | **Done (D70, 2026-10-29):** delete a version or every version with its files; refused while a live approval or a running attempt needs it, under the application locks; an application's choice of it removed; retention rows updated. The `needs_consent` display change is [shape] → C18 |
| C18 | The one `SCHEMA_VERSION=3` bump bundling every [shape] change | S | C9, C12, C15 | **Done (D71, 2026-10-29), announced: every approval given before it is invalidated.** Preference facts hashed by value; document origin and provenance; `accept` enforced; implicit and chosen resumes explained apart; an answer awaiting consent never kept in a version |
| L1 | Resume text extraction into proposed facts | L | C16, C18 | **Done (D72, 2026-10-29):** PDF, DOCX and TXT text; work, education and credentials proposed, approved one by one; nothing inferred, legal and sensitive lines skipped |
| L2, L3 | Tailored resumes and grounded cover letters | L | C15, C16, C18 | **Done in code (D73, 2026-10-29):** generated only through the drafting provider (none configured: 503), from approved facts; checked like drafts; a DOCX for one application, used only once accepted and while its facts are unchanged; diff from the base resume |
| L4 | A real draft provider | L | L2, L3 | **Owner decision:** server-side credentials, a cost budget and a consent screen showing what leaves NoEfforts; not started |

### Blocked or owner-only (not slices to implement now)

| Item | Blocked by |
|---|---|
| Live Freehire read | Owner decisions and a per-run approval (`freehire-first-architecture.md` §11) |
| Live pilot (rehearsal, then submission on a real destination) | Pilot permissions 1-4; Greenhouse terms review; admission evidence (`docs/live-pilot-gate.md`) |
| Historical diagnostics (legacy tracker, spreadsheet, logs counts) | The owner's historical-data permission; run by the owner, counts only (`outcome-diagnostics.md` §2) |
| Confirmation-email or reply counts | A separate inbox permission; owner-run, never automated here |
| Posting-sample review | A real-postings permission |
| Lever, Ashby or Workday adapters | Public-documentation review (owner boundary `public_doc_reviewed`); Lever is specification-only, Ashby identity-only; a multi-step provider also needs the S5 scenario `each_step_read_back_before_next` |
| Legacy credential and session hygiene: revoke the legacy Gmail OAuth grant, remove the IMAP app password, delete the local token file, delete code-bearing logs and screenshots once any tally is done | Owner only, at the owner's choice; never done by an agent; nothing from the legacy repository is imported (`legacy-audit.md` §3.3; `outcome-diagnostics.md` §6) |
| Employer-side data (asking an employer, or a statutory data-access request where one applies) | Owner decision per employer; never automated (`outcome-diagnostics.md` §2) |

## 3. Order

```
done: C1 C2 → C3-C5 → Q1 (D50) → S1 (C6, D51) → S2 (outcome integrity, D53) → S4 (D54)
      → S7 in code (live-read gate, D55, at the owner's request; not yet run)
      → S8 in code (watched searches and delete, D56, at the owner's request; not yet run)
      → C11 (State, City and Country lists, D57) → C10 (one link of a kind, D58)
      → S3 (job signals, D59) → C7 (answers tied to their question, D60)
      → C8 (the disclose path, D61) → S5 (fixture variants, D62) → C9 (salary units, D63)
      → C12 (review UI, D64) → C13 (approval reasons and revoking, D65) → C14 (version diff, D66)
      → S6 (Freehire hardening, D67) → C15 (drafting hardening, D68)
      → C16 (credentials as grounded facts, D69) → C17 (deleting documents, D70)
      → C18 (SCHEMA_VERSION 3, D71)
      → L1 (facts proposed from a resume, D72) → L2, L3 in code (tailored documents, D73)
next: L4 waits for the owner (a provider, credentials, a cost budget, a consent screen)
later: L1-L4; live steps only with the owner's recorded permissions
```

S2, S4 and S5 touch different modules from the C-steps and can be reordered without conflict;
S4 follows S1, so the bank-scope tables are edited once.

## 4. Recommendation

**S1 (C6, answer-bank scope, D51) is done** (`b6e4cf4`; results in
`docs/implementation-status.md`). It closed, for the wordings `bankscope.py` recognises, the one
legacy defect class NoEfforts still had in what it would send: answers reused across employers
and employer-relative or time-bound answers fixed once (LD-26, LD-30, LD-31, LD-39). A question
it does not recognise may still be offered for saving (`docs/answer-policy.md` row 5; D51
records the known misses).

**S2 (outcome integrity and funnel, D53) is done.** A submission now says what it rests on (a
receipt, the user's statement, or nothing known), outcomes carry a source and the date the user
gives, "assessment received" exists, an outcome before any known submission is refused, and the
funnel counts the user's own applications with denominators and no rate. It gives future
diagnostics trustworthy inputs for new applications only (`outcome-diagnostics.md` §3-§4).

**S4 (legacy collision corpus and static guards, D54) is done.** The wording traps the legacy bot
fell into are permanent resolver tests (244 rows); those that still resolved wrongly are
checkpoints now (someone else's details, preferences read as residence, residence and
nationality in other words, placed or negated relocation, a negated right to work, consent
options under a neutral label, facts that do not fit the field); static guards refuse a mailbox
client and page capture anywhere outside the frontend.

**C11 (State, City and Country lists, D57) is done.** A required US "State" list is mapped
from the profile when it names every state; a City list, another country's list and a Country
list without the profile's country are the user's answer for this application, never saved and
tied to the fact, so none is a dead end any more.

**C10 (one link of a kind, D58) is done.** A LinkedIn or website question is answered from the
profile only when exactly one link is of that kind, read from its host; with several the user
gives the one for that question, and the review page says why.

**S3 (job signals, D59) is done.** A posting its source says is closed, a job you excluded or
closed, and a role that looks like one you already have an application for are shown on the
job, Discover and review pages, and approval waits for your statement; Greenhouse embed URLs
now have their board URL's identity.

**C7 (answers tied to their question, D60), C8 (the disclose path, D61) and S5 (fixture
variants, D62) are done.** An answer or a choice applies only to the question as shown, and
"Include this answer" only to that answer; the receiver's ledger shows a sensitive answer sent
only as chosen; the legacy notes' page traps are fixtures each adapter stops on or handles, and
every provider's confirmation is bound to its own attempt.

**C9 (salary units, D63) is done.** A salary is sent only in the currency and period the
question allows.

**C12 (review UI, D64) is done.** Answers can be changed, cleared and added where the resolver
allows the user's input, a cover letter chosen or left out, and the page says where the form
sends.

**C13 (approval reasons and revoking, D65) is done.** Every refusal to approve, queue or revoke
has a fixed code, and revoking stops a queued submission at once and says what it stopped.

**C14 (version diff, D66) is done.** The review page shows what changed between versions, and
since the approved one, by label and shown value.

**S6 (Freehire hardening, D67) is done.** Counters no longer count as changes, a source's
`Retry-After` holds the user's next request back, and each listing can be refreshed.

**C15 (drafting hardening, D68) is done.** A draft can use only numbers from the facts it
cites, never states a legal status or a sensitive attribute, treats job text as quoted data,
and is accepted only if nothing it was made from has changed; the user can reject one.

**C16 (credentials, D69) is done.** A draft names a licence only from an approved, unexpired
credential it cites, and licence answers are never saved for reuse.

**C17 (deleting documents, D70) is done.** A version, or every version, of a document is
deleted with its file, never while an approval or a running submission needs it.

**C18 (SCHEMA_VERSION 3, D71) is done and announced: every approval given before it must be
given again.**

**L1 (facts proposed from a resume, D72) is done.** A resume's work history, education and
licences are proposed into the profile and used only once approved.

**L2 and L3 (tailored resumes and cover letters, D73) are done in code.** They run only
through a drafting provider, and none is configured, so nothing is generated yet.

**Next: L4, an owner decision.** A real provider needs server-side credentials, a cost budget
and a consent screen that shows what leaves NoEfforts; nothing is sent to an external AI
service until the owner decides them.

## 5. Never in any slice

Stealth, fingerprint changes, a browser User-Agent to pass as a person, proxy rotation, timing
jitter or human-like typing, anything aimed at a bot or risk score, narrowing the challenge stop
to let more forms through, CAPTCHA or OTP solving, automated mailbox reading, automated login to candidate portals, automated
access to competitor dashboards, clicking cookie or consent controls on the user's behalf,
importing any legacy data file, or running legacy code.
