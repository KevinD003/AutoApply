# Provider admission (I2)

Status: 2026-10-22. A reusable, machine-checked process for adding an ATS provider safely,
and where every registered provider stands in it today. Local code, synthetic fixtures and
tests only: no network request was made, nothing real was contacted, and no support state or
capability level changed. The fail-closed changes found on the way are listed in D47.

Code: `backend/app/modules/providers/admission.py`, served read-only at
`GET /api/providers/admission`. Tests: `backend/tests/test_provider_admission.py` (the
computation, on the registry and on a synthetic, never-registered example provider) and
`backend/tests/test_provider_contracts.py` (the repository facts behind the tables, CI only).
Decision: D47.

## What it is

Admission is **computed, never declared**. For each provider it evaluates a fixed set of
checks, one requirement of the provider framework each, from code tables and recorded evidence,
and reports the highest stage of the ladder those checks support, what stops it there, and
whether the next stage needs the owner.

- **Claims are bounded by it.** What a provider claims (its support state,
  `providers/wording.py`) must never rank above what it is admitted to. A registry entry raised
  without the code and the recorded evidence behind it fails CI
  (`test_every_registered_provider_is_admitted_to_what_it_claims`).
- **Advisory upward.** Admission changes no route, label, approval, package or flag. Only the
  providers API imports it (`test_nothing_routes_labels_or_approves_on_admission`).
- **Pure.** It reads no database, file or network and imports no browser code
  (`test_admission_reads_no_database_and_no_repository_file`,
  `test_admission_imports_no_browser_code`). The repository facts it relies on (fixture paths
  exist, scenario tests read the receiver ledger, known gaps still reproduce, identity cases
  cover every ATS) are proved in CI by `test_provider_contracts.py`.
- **Owner boundaries.** Four stages open only with the owner's approval. Code can only point
  at a recorded approval; it can never give one. None is recorded for a new stage today.
- **A cap.** No provider passes `rehearsal_ready`, whatever the tables say: a real disclosure
  or submission stays refused (`real_destinations_refused`,
  `test_nothing_passes_the_real_destination_cap`). Opening it is a reviewed change to the
  live-pilot gate, never a table edit.

## The eleven requirements

| # | requirement | what it covers |
|---|---|---|
| 1 | `identity` | the ATS identity rules (`jobs.canonical.detect_ats`), form sources matching their ATS, the rehearsal path rule, known identity gaps |
| 2 | `capability_matrix` | the spec invariants, the browser capability table agreeing with the registry, observed cells credited by recorded runs |
| 3 | `workflow_traits` | every yes/no trait backed by a fixture's own design or a credited run |
| 4 | `route_logic` | a planned spec's honest refusal, the route reaching the adapter, observation/discovery/manual never routed |
| 5 | `adapter_versioning` | a recorded, safe version; the legacy table never extended |
| 6 | `privacy` | a safe key; registry and capability texts that name no URL, host, address or long number |
| 7 | `audit` | route metadata that survives the audit sanitizer unchanged |
| 8 | `fixtures` | the code registered, the fixture declared, every required scenario shown against the receiver ledger |
| 9 | `manual_evidence` | the owner's public-docs review recorded; the owner's manual observations meeting nothing |
| 10 | `support_state` | texts that claim nothing, a support label, a route label with its evidence, no live label |
| 11 | `pilot_gate` | the readiness profile and its conditions, the rehearsal path rule, permissions C and D |

## Tracks and stages

The ladder: `registered`, `planned`, `public_doc_reviewed`, `fixture_only`, `observed_read_only`,
`rehearsal_ready`, `rehearsed`, `live`. Each provider climbs the track of its kind; a stage is
reached when every check at or before it is met (or does not apply) and every earlier stage was
reached.

| track | stages | chosen when | end code |
|---|---|---|---|
| `ats_execution` | `registered`, `planned`, `public_doc_reviewed`, `fixture_only`, `observed_read_only`, `rehearsal_ready`, `rehearsed`, `live` | a browser or API provider with an ATS identity | – |
| `generic_execution` | `registered`, `fixture_only` | a browser or API provider with none (a generic fixture adapter) | `no_ats_identity` |
| `observation` | `registered`, `public_doc_reviewed`, `fixture_only`, `observed_read_only` | a read-only observation provider | `read_only_by_kind` |
| `discovery` | `registered`, `fixture_only` | a discovery provider | `discovery_by_kind` |
| `manual` | `registered` | the manual handoff | `handoff_by_kind` |

The support states map onto the ladder: `not_supported` and `manual` claim `registered`,
`planned` claims `planned`, `fixture_only` and `observed_read_only` claim their own stage, and
`live` (which has no label) claims `live`.

## Owner boundaries

| stage | approval | what the owner approves | recorded in |
|---|---|---|---|
| `public_doc_reviewed` | `doc_review` | a scoped read of the vendor's public documentation and terms (an external read), recorded as a decision | `providers/evidence.py` `DOC_REVIEWS` (empty) |
| `observed_read_only` | `read_only_run` | each read-only run, approved for that one run, on a pinned revision after green CI | `providers/evidence.py` `READ_ONLY_RUNS` |
| `rehearsed` | `disclosure_permission` | live-pilot gate permission C, plus a reviewed change enabling exactly one destination | `providers/readiness.py` `DISCLOSURE_PERMISSION_RECORDED` (false) |
| `live` | `submission_permission` | live-pilot gate permission D, after the rehearsal's result | `providers/readiness.py` `SUBMISSION_PERMISSION_RECORDED` (false) |

A record is necessary, never sufficient: that the owner really gave an approval is not
machine-checked. C and D are recorded separately (the readiness pilot-gate condition needs
both). `test_an_owner_boundary_is_never_passed_without_its_record` lifts the cap in the test only
and shows each of the four boundaries still stops the complete example without its record.

## Checks

Each check is a fixed code (shown when it blocks), the requirement it evaluates, the first
stage that needs it, and its basis: `code`, an evidence class
(`docs/upload-and-submission-evidence.md`) or a readiness prerequisite. No stage needs evidence
that only a later stage can produce (`test_no_stage_needs_evidence_only_a_later_stage_produces`);
`traits_evidenced` is exempt as a claim guard: it applies only when a provider states a yes/no
trait, and bounds that claim at any stage.

| id | requirement | stage | basis | met when |
|---|---|---|---|---|
| `spec_invariants` | capability_matrix | `registered` | `code` | `check_spec` passes and the registry reports no cross-provider problem for it |
| `key_is_safe` | privacy | `registered` | `code` | the key is its name, a short lowercase identifier the sanitizer keeps, and named after its ATS (or `fixture_`/`fake_`/`manual_`) |
| `text_names_nothing` | privacy | `registered` | `code` | no URL, e-mail address, dotted host name (any ending but a repository file suffix), UUID, or 5+ digit or requisition-style number in its description, status, notes or capability table |
| `text_claims_nothing` | support_state | `registered` | `code` | none of those texts uses a support claim (`wording.CLAIMS`) |
| `support_state_labelled` | support_state | `registered` | `code` | its support state has a label (a live state has none) |
| `traits_evidenced` | workflow_traits | `registered` | `read_only_observation` | each yes/no trait is its own fixture's design (no ATS) or credited by a run |
| `identity_contract` | identity | `registered` | `code` | its ATS is a `detect_ats` name with the full identity contract in CI |
| `never_routed_by_kind` | route_logic | `registered` | `code` | a discovery, observation or manual provider is in no execution table |
| `manual_evidence_meets_nothing` | manual_evidence | `registered` | `code` | its manual evidence (Path A) is the basis of no check and no readiness condition, and recording it (any answers, computed) changes no condition |
| `planned_route_refuses` | route_logic | `planned` | `code` | a planned spec is the one routing finds for its ATS, and its ATS has a display name |
| `doc_review_recorded` | manual_evidence | `public_doc_reviewed` | `public_doc_expectation` | the owner's public-docs and terms review of its ATS is recorded |
| `code_registered` | fixtures | `fixture_only` | `code` | its code is registered (browser capability table, API adapters, discovery or observer) |
| `fixture_target_declared` | fixtures | `fixture_only` | `fixture` | implemented, with a capability at `fixture` or above and the fixture it was tested against |
| `capability_tables_agree` | capability_matrix | `fixture_only` | `code` | the browser capability table's flags, environments, real-destination switch and fixture equal the registry's |
| `version_recorded` | adapter_versioning | `fixture_only` | `code` | an adapter version exists, is a safe identifier and survives the sanitizer |
| `legacy_versions_frozen` | adapter_versioning | `fixture_only` | `code` | it is not added to the legacy-version table (the two original adapters only) |
| `route_reaches_provider` | route_logic | `fixture_only` | `code` | a form source routes to it (browser) or it has identity, credentials and a route (API), never in production |
| `form_sources_match_identity` | identity | `fixture_only` | `code` | every form source routed to it names its ATS and has a label saying it is a local test stand-in |
| `rehearsal_path_fits_identity` | identity | `fixture_only` | `code` | its rehearsal path rule, if any, reads its own ATS's boards |
| `route_label_has_evidence` | support_state | `fixture_only` | `code` | its route label can be shown with its evidence |
| `audit_meta_round_trips` | audit | `fixture_only` | `code` | its route metadata survives the audit sanitizer unchanged |
| `fixture_scenarios_complete` | fixtures | `fixture_only` | `fixture` | no required scenario is recorded as a gap |
| `observed_cells_credited` | capability_matrix | `observed_read_only` | `read_only_observation` | it has observed cells and each is credited by a completed, single-use run |
| `observed_only_where_read_only_can_see` | capability_matrix | `observed_read_only` | `code` | observed cells only where a read-only run can see anything |
| `readiness_profile_defined` | pilot_gate | `rehearsal_ready` | `code` | it has a readiness profile (only `greenhouse_dom` today) |
| `readiness_dropdowns` | pilot_gate | `rehearsal_ready` | `read_only_observation` | the readiness condition is met, and dropdown behaviour (not only structure) is credited |
| `readiness_unmatched_required_controls` | pilot_gate | `rehearsal_ready` | `mapping_rule` | the readiness condition is met |
| `readiness_location` | pilot_gate | `rehearsal_ready` | `read_only_observation` | the readiness condition is met, and location behaviour is credited |
| `readiness_real_upload` | pilot_gate | `rehearsed` | `rehearsal` | the readiness condition is met |
| `readiness_real_submission` | pilot_gate | `live` | `real_submission` | the readiness condition is met |
| `readiness_pilot_gate` | pilot_gate | `live` | `owner_permission` | the readiness condition is met |
| `readiness_capability_entry` | pilot_gate | `live` | `reviewed_change` | the readiness condition is met |
| `rehearsal_path_rule` | pilot_gate | `rehearsal_ready` | `code` | a rehearsal path rule reads its ATS's boards (without one, its prerequisite fails closed) |
| `known_gaps_closed` | identity | `rehearsal_ready` | `code` | no known gap applies to it |
| `disclosure_permission_recorded` | pilot_gate | `rehearsed` | `owner_permission` | permission C is recorded |
| `submission_permission_recorded` | pilot_gate | `live` | `owner_permission` | permission D is recorded, on its own |
| `live_label_exists` | support_state | `live` | `code` | a live support label was added deliberately |

The readiness conditions are Greenhouse's (`providers/readiness.py`, unchanged); a new ATS
needs its own profile before it can reach `rehearsal_ready`. Each condition is required at the
stage whose evidence can meet it (dropdowns, unmatched controls and location before a
rehearsal; a real upload only for `rehearsed`; a real submission, the gate permissions and the
reviewed capability entry only for `live`). For dropdowns and location, admission is stricter
than readiness: a structure-only observation never counts
(`test_a_structure_only_observation_never_meets_a_rehearsal_condition`).

Every check is reachable and breakable: on a complete synthetic example
(`tests/admission_example.py`, an ATS called "exampleats", never registered) every check is met,
and one change per check makes it not met and stops the example before its stage
(`test_every_check_is_caught_by_its_sabotage`). Eight of those changes also break a check that
reads the same input (for example, a key that is not its spec's name is a registry problem
too); each such dependency is declared (`ALSO_BREAKS`) and the test requires exactly the target
and its declared dependencies to break, nothing else. `key_is_safe`'s own rules are tested case
by case (`test_a_key_is_safe_only_when_named_after_its_ats_or_kind`), and so is the identifier
detector behind `text_names_nothing` (`test_text_naming_an_identifier_is_caught`,
`test_text_naming_no_identifier_passes`).

## Admission today

| provider | track | claimed | admitted | next | blocking | end |
|---|---|---|---|---|---|---|
| `fixture_ats` | `generic_execution` | `fixture_only` | `fixture_only` | – | – | `no_ats_identity` |
| `greenhouse_hosted` | `ats_execution` | `fixture_only` | `fixture_only` | `observed_read_only` | `doc_review_recorded`, `observed_cells_credited` | – |
| `greenhouse_dom` | `ats_execution` | `observed_read_only` | `observed_read_only` | `rehearsal_ready` | `doc_review_recorded`, `readiness_dropdowns`, `readiness_unmatched_required_controls`, `readiness_location`, `known_gaps_closed` | – |
| `fake_api` | `generic_execution` | `fixture_only` | `fixture_only` | – | – | `no_ats_identity` |
| `greenhouse_readonly` | `observation` | `observed_read_only` | `observed_read_only` | – | – | `read_only_by_kind` |
| `freehire_mock` | `discovery` | `fixture_only` | `fixture_only` | – | – | `discovery_by_kind` |
| `freehire` | `discovery` | `fixture_only` | `fixture_only` | – | – | `discovery_by_kind` |
| `workday` | `ats_execution` | `planned` | `planned` | `public_doc_reviewed` | `doc_review_recorded` | – |
| `lever` | `ats_execution` | `planned` | `planned` | `public_doc_reviewed` | `doc_review_recorded` | – |
| `manual_handoff` | `manual` | `manual` | `registered` | – | – | `handoff_by_kind` |

Every provider is within its claim. No provider is `rehearsal_ready`. By ATS: Greenhouse is at
`observed_read_only` (its execution adapters' best) with `doc_review_recorded` waived (the by-ATS
view shows the waiver), Lever and Workday at `planned`, and Ashby, Workable and SmartRecruiters
are identified only (`not_admitted`: no provider exists).

## Waivers

The ten providers registered before I2 keep their claims through frozen waivers. A waiver
shows as `waived`, never as `met`. It counts only up to the lower of the provider's current
claim and the claim it had at I2 (`PRE_ADMISSION`, pinned), so it can never advance one, and
raising a claim never raises a waiver (`test_raising_a_claim_never_raises_a_waiver`); a new
adapter registered under a pre-I2 key inherits nothing past that key's frozen claim
(`test_a_new_adapter_under_a_pre_admission_key_inherits_no_waiver`). It is allowed only for
these keys and only for `doc_review_recorded` and `fixture_scenarios_complete`, and each covers a
check that really fails without it
(`test_waivers_are_frozen_to_the_pre_admission_providers_and_still_real`). A waiver for any other
provider has no effect.

| provider | check | reason |
|---|---|---|
| `greenhouse_hosted` | `doc_review_recorded` | `terms_review_unrecorded` |
| `greenhouse_dom` | `doc_review_recorded` | `terms_review_unrecorded` |
| `greenhouse_readonly` | `doc_review_recorded` | `terms_review_unrecorded` |

The Greenhouse adapters were built before any public-docs and terms review was recorded:
`docs/first-adapter-proposal.md` lists it as "to verify" and records no outcome. If the owner
did one outside the repository, recording it as a decision lets `doc_review_recorded` be met.
No scenario waiver exists: the mapping found five required scenarios without a ledger test
(reconciliation on the three browser adapters, a readback mismatch on `greenhouse_hosted`, an
upload failure on the API route), and each now has one.

## Known gaps

Identity behaviour that is truthful today (real destinations are refused before any of it
matters) but must be resolved before a provider it applies to reaches `rehearsal_ready`. Each is
reproduced by a probe in CI (`tests/provider_contracts.py` `PROBES`;
`test_every_known_gap_is_still_real` fails on a fix without its removal, or a removal without a
fix). They are pinned, not fixed: fixing them changes stored `ats_provider` values and package
hashes. `any_ats` means every provider serving an ATS.

| code | applies to | what is reproduced |
|---|---|---|
| `identity_jid_any_host` | `greenhouse` | a `gh_jid` parameter on any host, or on a host merely containing the vendor's domain, is identified as Greenhouse (the probe holds while either does) |
| `identity_rules_disagree` | `greenhouse` | the posting parser and the identity rules disagree on Greenhouse URL forms (an embed URL, a suffix after the posting id, an over-long board; the probe holds while any does) |
| `identity_unknown_skips_form_check` | `greenhouse_dom`, `greenhouse_hosted` | a job with no identified ATS and a Greenhouse-captured form skips the form/ATS mismatch check |
| `identity_stored_unknown_not_redetected` | `any_ats` | a job stored as `unknown` is not identified again when the rules change |
| `identity_variant_unrecognised` | `workday` | a Workday posting URL with an `/apply` suffix is not identified |

## Fixture scenarios

An execution provider's `fixture` levels require these scenarios, each shown by a test that
reads the receiver's ledger and builds an application for that provider
(`tests/provider_contracts.py` `SCENARIO_TESTS`, checked structurally by
`test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap`):

- always: `full_run_matches_ledger`, `changed_form_stops_before_disclosure`,
  `unknown_outcome_never_resent`;
- by capability: `deterministic_fill` → `readback_mismatch_stops_before_submit`; `file_upload` →
  `upload_failure_stops_with_evidence`; `captcha_checkpoint` →
  `challenge_stops_before_disclosure`; `email_verification` → `code_entered_by_user_only`;
  `final_submit` → `rejection_is_not_confirmation`; `official_api_submission` →
  `no_grant_never_contacted`; `reconciliation` → `reconcile_never_resends`.

The check is structural (the test exists, reads the ledger, names the provider or its builder),
not semantic: what a mapped test asserts was checked by an adversarial review when it was mapped,
and must never be weakened to reach a stage.

## Recorded evidence

- **Read-only runs** (`evidence.READ_ONLY_RUNS`) restate the Runs table of
  `docs/greenhouse-readonly-compatibility-proposal.md` as run numbers, outcomes and fixed names
  only (`test_the_recorded_runs_are_the_documented_runs`). A run credits a capability or a trait
  only if it was approved for that one run ("authorized once") and completed. Runs #1-#3 (an
  earlier or general approval) and #7 (no page evidence) credit nothing; #5 was completed and
  single-use but identified hosts only, so it records nothing to credit. Runs #4, #6, #8 and #9
  credit every observed cell in the registry and every "no" trait of the Greenhouse providers;
  the dropdown cell is credited as structure only. The "no" traits of `fixture_ats` and
  `fake_api` are their own fixtures' design (no ATS), never a run.
- **Public-docs reviews** (`evidence.DOC_REVIEWS`) are empty and pinned so
  (`test_no_doc_review_is_recorded_today`).
- **The owner's manual observation (Path A)** changes no admission
  (`test_the_owners_manual_observation_changes_no_admission`).

## How to admit the next ATS

1. **No approval needed.** An identity pattern in `jobs.canonical` with its display name, and
   `IDENTITY_CASES` covering every category with fictional URLs (`.invalid` lookalikes). A
   planned spec with `expected`/`unknown` traits and notes, `ats` set, a column in the routing
   vocabulary table. Pin its computed row (`planned`). Routing then hands its jobs off honestly
   (`planned_adapter_only`).
2. **Stop: the owner.** A scoped review of the vendor's public documentation and terms (an
   external read), recorded as a decision `D<n>` and as `DocReview(ats, "D<n>")`.
3. **A reviewed change, no external contact.** A fictional fixture in `fixtures/ats_receiver`;
   the adapter and its runner entry; `ADAPTER_VERSIONS` and `policy.CAPABILITIES`; the form
   source in `FORM_SOURCE_ADAPTERS`, `FORM_SOURCE_ATS` and `FORM_SOURCE_LABELS` and the capture
   code; a ledger test for every required scenario; the spec implemented, at `fixture`, with
   `tested_against`, replacing the planned spec. A rehearsal path rule is optional: without one
   its rehearsal prerequisite fails closed.
4. **Stop: the owner, per run.** Each read-only observation run, single use, on a pinned
   revision after green CI, recorded in a Runs table and in `READ_ONLY_RUNS`. Raise only credited
   cells a read-only run can see. Any rework of the adapter bumps its version.
5. **Derived.** Its own readiness profile (Greenhouse's conditions do not transfer), a path rule,
   its known gaps closed. This reaches `rehearsal_ready`, which enables nothing.
6. **Stop: the owner (C), then (D).** Unreachable in this version: the cap.

## Not machine-checked

- that an owner approval was really given (a record is necessary, never sufficient);
- the content of a public-docs review;
- what a mapped scenario test asserts beyond reading the ledger and building for its provider;
- whether an adapter's meaning changed without a version bump;
- which cells a recorded run credits (the transcription is reviewed, its approval and outcome
  words are tested).

Consistency is not truth: a change that edits a table, the registry and the pinned expectations
together passes. Every raise still needs records, and records need the owner.
