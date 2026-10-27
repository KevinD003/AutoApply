# Implementation status

Last updated: 2026-10-27 (documentation: the Freehire-first review published, with the Freehire re-check of 2026-10-26, an amendment to D34 and D52; earlier: preparation: a saved answer is reused only where it stays true, bound to its help text, never for answers that depend on the employer, the job or the date, and saves and deletes never fail; execution: an unknown outcome in the verification-code step reaches `submitted_unconfirmed` again, and the sweeper recovers each stale attempt in its own savepoint; earlier: preparation: a statement of a profile fact is checked only with agree and a true approved fact, eligibility misreads and legal-status questions become checkpoints, sensitive topics found in wording, help text, options, sections and follow-ups are never saved, reused or drafted; earlier: only resolved answers are sent, a stale accepted draft is a checkpoint, a document question that is not asked attaches nothing, the package shape pinned, cross-tenant and repository-hygiene guards; earlier: a provider-admission framework: each provider's stage computed from code and recorded evidence, claims bounded by it, owner stops and a cap; a manual-handoff approval and a reconciled-as-not-received approval can no longer send; one lock order for every execution path, gates reading what is committed after their locks, deterministic race tests; a recorded, valid rehearsal is required before the first submission through each employer/provider path, at five layers, fixtures only; the rehearsal stop is a gate and writes a rehearsal record; readiness counts the caller's recorded evidence by class; each gate locks the approval row, so a revocation committed while it waits is refused; upload evidence kept as a digest and a fixed acknowledgement, also for failed uploads; rehearsal results on the review page and tracker; rehearsal: an approval to disclose only, which stops before the send gate; Lever as a planned provider; location design without hidden coordinates; page controls the job data does not list become checkpoints at capture; Greenhouse pilot readiness computed from evidence and the Path A record format; real-destination jobs get the truthful route before any form step; question keys moved out of URL paths; support-state wording derived from evidence and served from one place; route reason-code contract, discovery route explanations, route-audit deduplication and the provider on the route card; earlier: privacy and audit hardening, legacy audit repair, baseline corrections and a documentation-consistency pass; nothing supported for real use; no external request, credential, permission or live-status change). For requirement-by-requirement evidence see
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

## Freehire-first review published; Freehire re-check recorded (2026-10-27; documentation only)

- **Scope:** the deliverables of the Freehire-first and legacy-repository review, published as
  `docs/legacy-audit.md` (A), `docs/freehire-first-architecture.md` (B),
  `docs/reliability-test-plan.md` (C), `docs/outcome-diagnostics.md` (D) and
  `docs/implementation-plan.md` (E); the Freehire re-check of 2026-10-26 in
  `docs/research/freehire.md` and `docs/discovery.md`; an amendment to D34; D52 (Freehire first
  for discovery, execution kept separate). No code, support state, capability level, real
  destination, live permission or pilot-gate change.
- **External access, all read-only and public:** on 2026-10-26 five freehire.me pages (terms,
  Jobs API, pricing, API reference, OpenAPI document) and a shallow `git fetch` of Freehire's
  public source; for this review a shallow clone of the same public repository, read with
  `git show` only. No Freehire API endpoint, login or key; no Freehire code run. The legacy
  repository was read only: nothing was copied from it and no record imported; its recollected
  results are described as unverified, never as success rates.
- **Review of the published text:** an adversarial review (3 reviewers: Freehire facts against
  the page captures and the source; the decision and plan against the owner's brief and the
  code; consistency of line references, cross-references and cited tests), each finding checked
  by a skeptic. 33 confirmed and fixed, among them: enrichment fields overstated as
  deterministic; the strict anonymous budget is per IP, not shared by all callers; the
  `utm_source` tag is already dropped before deduplication and ATS identification (a referral
  code is not); auto-apply was not new on 2026-10-26; D52 had claimed stale, suspicious and
  ambiguous records already stop (they do not; S3) and had put the checkpoint after the API and
  browser routes (D35 decides it first); C6 described as closing what it narrows; letter
  abbreviations of the drafts and line references off by one. 8 refuted.
- **Tests run locally (cloud sandbox, PostgreSQL 16):** every test file that reads `docs/`
  (`test_doc_references.py`, `test_repo_hygiene.py`, `test_audit_inventory.py`, `test_lever.py`,
  `test_package_contract.py`, `test_path_a.py`, `test_pilot_readiness.py`,
  `test_provider_admission.py`, `test_provider_contracts.py`, `test_question_safety.py`,
  `test_reason_codes.py`, `test_rehearsal_codes.py`): 653 passed, exit 0. The full suites were
  not re-run: no code changed since `b6e4cf4` (2616 and 36 passed there, CI #102 green).
- **CI for the previous change:** **CI #102**
  ([40444320612](https://github.com/KevinD003/AutoApply/actions/runs/40444320612)) (`b6e4cf4`,
  C6): passed (all four jobs).

## Bank scope: a saved answer is reused only where it stays true (C6, 2026-10-27; local only, no external request)

- **Scope:** step C6 of the preparation platform, and the first slice of the plan from the
  Freehire-first and legacy-repository review (the legacy project reused fixed employer-relative
  and time-bound answers everywhere). Decision D51; rules in `docs/answer-policy.md` row 5;
  evidence: `docs/evidence-matrix.md` ("Preparation: bank scope"). Nothing contacted; no
  support state, capability level, real destination or Path A change.
- **Found (each reproduced first) and fixed:** answers about the employer, the job or the date
  (how you heard about the job, previously worked here, relevant experience, start date,
  availability, notice, relocation, salary) were saved and reused for other employers; an
  answer was reused for a question with other help text; concurrent saves returned 500 and lost
  the typed answer, a save racing a delete returned 500, two updates lost a version, a second
  delete returned 204.
- **Design:** three independent designs and a judge (a read-only workflow with mapping probes;
  two container restarts interrupted the judge, which resumed from its files); ported verbatim
  from the judge's verified prototype, renumbered D51. `bankscope.py` (pure) decides; the
  resolver only clears `bankable`; the key adds help text only when a question has help text
  (no row re-keyed); one nullable column, one upsert, one DELETE … RETURNING.
- **Unchanged:** `SCHEMA_VERSION` (2), `RESOLVER_VERSION`; no bank row deleted or re-keyed.
  Packages of the basic, tricky, receiver, greenhouse_like 4012001 and greenhouse_v2 5020001
  forms get a new version at their next rebuild (`bankable` false on the narrowed rows), so
  their approvals are invalidated; a queued attempt is refused at the gate before disclosure.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - new: `tests/test_bank_scope.py` with `tests/bank_scope_wordings.json` (1,037 rows),
    `tests/test_bank_scope_api.py`, `tests/test_bank_races.py`, the migration test in
    `tests/test_migrations.py`; moved off "How did you hear about this job?" to the education
    question: `test_preparation.py`, `test_resolver.py`, `test_package_contract.py`,
    `test_question_safety.py` (`C6_DELTA`), `test_question_safety_api.py`, `execution_harness.py`,
    `test_execution_validation.py`, `frontend/e2e/phase-b.spec.ts`;
  - the race and API tests run against the previous code (`3af29f0`, a temporary worktree):
    11 failed, 2 passed; the five race tests failed exactly as described (two IntegrityError
    23505, version 2 instead of 3, StaleDataError, no 404);
  - focused files on the C6 tree: 1644 passed, 1 failed (`test_sending.py`: its resolver stub
    lacked the new `repeated` argument, a test defect; the stub now forwards it), then
    `test_sending.py` 20 passed;
  - narrowing on the working tree against `7669c61`'s resolver: 1,315,200 form resolutions,
    1,424,000 rows, 0 violations;
  - full backend (`pytest tests`): 2616 passed, exit 0, in 28 min 30 s (1491 at Q1; the
    wording table runs one test per row). An earlier full run was stopped as contaminated
    (below);
  - full Playwright: 36 passed, 2 skipped (the desktop-only log checks on mobile), exit 0, 5.4 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: clean, each exit 0;
  - adversarial review: 5 reviewers (wordings, storage and the API, the resolver, the pages and
    documents, the tests), each finding checked by a skeptic. Fixed, each with a test or table
    rows: missed wordings (the job applied for, what made you apply, a rate or total comp, years
    of experience written differently, trailing "(optional)", a recruiter by name, "submitted an
    application here", "unavailable", class standing, Unicode dashes; a degree's length in its
    options no longer counts as time); 500s on a NUL in page text or an answer, on a stored
    option label too long to rebuild, and on NaN or infinity as a number (the last older than
    C6); a follow-up in a package built before C6 trusting its parent's stored row; a repeated
    sensitive question refused with the sensitive message; three page wording faults. Refuted:
    two documentation items and one explanation-wording item. Accepted, not changed: some stable
    wordings are refused (over-narrowing only costs a re-answer);
  - after the fixes: the narrowing check re-run (1,315,200 form resolutions, 0 violations); the
    review's scenarios probed one by one;
  - sabotage checks: 20, each caught (9 for the review fixes, 9 for the database design: no
    upsert, version always bumped, help text not copied on update, delete without user scope,
    no "not reused" flag, the package row trusted, a non-nullable column, no repeat check, no
    receiver mode; 2 for the pure rules); the source compared identical to the backup
    afterwards. One was invalid at first (a missing import) and was re-run correctly;
  - infrastructure interruption (mine): the first full run was contaminated because review
    agents ran "pure" test files at the same time, and the conftest of every pytest run drops
    and recreates the shared `noefforts_test` database. It was stopped, not counted, and re-run
    with nothing else on the database (the 2616 above).
- **CI for the previous change:** **CI #101**
  ([40431426083](https://github.com/KevinD003/AutoApply/actions/runs/40431426083)) (`3af29f0`,
  Q1): passed (all four jobs).

## Verification-code outcomes quarantined; the sweeper recovers each attempt alone (Q1, 2026-10-27; local only, no external request)

- **Scope:** a defect in uncertain-outcome quarantine, found by the static map made for the
  Freehire-first and legacy-repository review (that review is in progress; C6 is paused for it).
  Decision D50. Nothing contacted; no support state, capability level, real destination or Path
  A change.
- **Found and reproduced first** (5 new tests failing before the fix, the worker and sweeper
  ones with `IllegalTransition`): `needs_user_action -> submitted_unconfirmed` was listed twice
  in the transition table and only the user's entry survived.
  - The employer accepted the verification code but its reply was lost: the worker crashed, the
    receiver's ledger showed 1 accepted, and the application stayed "needs your action".
  - A worker died in the code wait: the sweep raised and rolled back every stale attempt in its
    batch, other users' included, on every run.
- **Now:** the move is allowed for the worker, the system and the user; the sweeper recovers
  each attempt in its own savepoint (a failure is counted in `errors`, logged with the attempt id
  and exception type only, and retried by the next sweep); a code wait it quarantines expires its
  checkpoint and erases a code typed for the dead worker. The receiver gains `verify_drop` (the
  code accepted, the reply never sent). A test refuses any repeated key in a dict literal in
  `app/` (one existed; ruff checks literal keys only).
- **Unchanged:** no re-send or retry path, gates, lock order, `SCHEMA_VERSION`, reason codes,
  migrations, frontend.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_code_wait_quarantine.py` (5): before the fix 5 failed; after it 4 passed and 1
    failed on the test's own assumption (an illegal re-queue answers 400, not 409), corrected in
    the test; then 5 passed;
  - with `test_execution_security.py`, `test_execution_failures.py`, `test_applications.py`,
    `test_lock_order.py`: 84 passed, exit 0;
  - full backend (`pytest tests`): 1491 passed, exit 0 (first run on the final tree);
  - `ruff check`, `ruff format --check`: clean (the frontend is unchanged);
  - sabotage checks: 7, each caught; one ("no savepoint per row") was missed at first because
    the injected failure fired before the row changed anything; the test now injects a database
    error after the row's changes and catches it. Source compared identical afterwards.
- **CI for the previous change:** **CI #100**
  ([40397484524](https://github.com/KevinD003/AutoApply/actions/runs/40397484524)) (`7669c61`,
  C3-C5): passed (all four jobs).

## Statements, legal facts and sensitive topics (C3-C5, 2026-10-26; local only, no external request)

- **Scope:** steps C3-C5 of the preparation platform. Nothing contacted; no support state,
  capability level, real destination or Path A change. Decision D49; rules in
  `docs/answer-policy.md` (rows 1, 1a, 2, 2a, 3-5 and the eligibility rules); evidence:
  `docs/evidence-matrix.md` ("Preparation: statements, legal facts and sensitive topics").
- **Found (each reproduced against the previous commit) and fixed:**
  - a checkbox stating "I am legally authorized to work in the United States" was checked from
    agree alone for an applicant not authorized; such a statement is now checked only when the
    approved fact makes it true, and the fact is recorded (editing it invalidates the approval);
  - "Do you require a work permit to work in Germany?" was answered inverted from the
    authorization fact; a question about New Mexico was answered with Mexico's facts; "for any
    employer" was answered yes for an employer-tied visa; a saved answer to "Are you a US
    citizen?" was reused for every employer; each is now a question the user answers;
  - criminal history, health, accommodations, current salary and similar were ordinary questions
    whose answers were saved and reused without consent, and an accommodations text box could be
    drafted; they are now sensitive, never saved, reused or drafted.
- **Design:** three independent designs and a judge (a read-only workflow with mapping probes),
  ported verbatim from the judge's verified prototype; `_classify_eligibility` unchanged byte for
  byte; `package.resolve_answers` extracted from `build_content` (same loop) so tests run it. One
  change to the prototype: the place rule names no organisation (any "... of America" except the
  United States of America).
- **Unchanged:** `SCHEMA_VERSION` (2), `RESOLVER_VERSION`, migrations, the frontend, the bank
  rows. Packages with a changed row re-hash at their next rebuild; their approvals are
  invalidated (a queued attempt is refused at the gate before disclosure).
- **Found by the adversarial review (4 reviewers; a usage limit stopped two reviewers and every
  skeptic, so each finding was checked by hand with probes against both commits):** one
  regression, a checkbox mixing a sensitive topic with citizenship resolving from agree (fixed:
  sensitive again, not reusable), and ten gaps the change had not closed, all fixed and each a
  table row (`rv.*`): statements of a right to work in other words; the citizenship guard missing
  "a US citizen", demonyms and green cards (and never checking one it cannot place); headings
  over a help-text statement; a declined optional statement choice answering "No"; help text
  after "Answer for ..."; sponsorship at other times, held sponsorship and green cards; Country
  and Location fields about work authorization or the job; regions as adjectives, example
  countries and organisations named after a country.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_question_safety.py` (366: 348 table rows, the 46 pinned controls, the property
    test in 9 profiles, the citizenship placement), `tests/test_classify_vocabulary.py` (94),
    `tests/test_question_safety_api.py` (6); `test_sending.py`'s resolver stub takes the parent;
  - verification against the previous commit (scratchpad scripts, not in the repository), before
    and after the review fixes: 52,800 fixture and test rows identical except wrong-kind stored
    consents; 308 design rows as specified; 452,520 resolutions with no new automatic answer and
    nothing newly reusable or draftable; fixture package hashes 40/40; the review's scenarios
    probed one by one;
  - full backend (`pytest tests`): before the review fixes 1424 passed, exit 0; on the final tree
    1486 passed, exit 0;
  - full Playwright: 36 passed, 2 skipped, exit 0 (the frontend is unchanged);
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: clean;
  - sabotage checks: 40, each caught; four were missed at first (each fix covered only together
    with another rule, or a pattern with no example of its own) and caught after the tests were
    strengthened; the source compared identical to the backup afterwards.
- **CI for the previous change:** **CI #99**
  ([39894454491](https://github.com/KevinD003/AutoApply/actions/runs/39894454491)) (`35aa0c5`,
  C1, C2): passed (all four jobs).

## Preparation guards and only resolved answers sent (C1, C2, 2026-10-23; local only, no external request)

- **Scope:** the first two steps of the preparation platform (the CTO's phase C; the table
  "Phase B — Preparation" below), from an independent map of the preparation code and its
  gaps. Nothing contacted; no support state, capability level, real destination or Path A
  change. Decision D48; evidence: `docs/evidence-matrix.md` ("Preparation: guards, and only
  resolved answers sent").
- **C2, only a resolved answer is sent** (`preparation/sending.py`), each defect reproduced
  first:
  - an optional accepted draft whose fact changed became "blank" but kept its text; the
    package could be approved and the receiver's ledger showed the stale draft sent. It is now
    a checkpoint, optional or not;
  - a document question that is not asked (in a block not shown, or depending on a missing
    question) made the package view and every answer saved a 500. It now attaches nothing;
  - nothing compared the stored package the worker fills with its approval: a stored package
    changed without its hash was sent (shown with the new check removed: confirmed, because the
    gates rebuild the package from current data, which still matches);
  - now the package builder gives every blank row no value; before any adapter code runs, the
    worker refuses a stored package that is not the approved one, or that has a value on a row
    that is not resolved; each adapter fills, uploads and reads back only resolved answers.
    Each layer is tested with the others bypassed.
- **C1, guards:** the package content shape (96 key paths) pinned to `SCHEMA_VERSION`
  (unchanged at 2); cross-tenant tests for revoke, document selection, draft acceptance, the
  document list and the answer bank; no candidate document, secret or captured session
  committed (tracked or untracked and not ignored), and email addresses on reserved domains
  only. The Phase B table below is corrected:
  sensitive consent and the answer bank are partial, tailoring is not started, cover letters
  are upload only. The saved-answers page no longer says such questions are "never saved"; it
  says which questions NoEfforts recognises.
- **Unchanged:** `SCHEMA_VERSION` (2), `ADAPTER_VERSIONS`, reason codes, migrations. Only a
  package with a stale accepted draft gets a new hash (its approval is invalidated).
- **Deferred (found by the review, fail-closed today):** a stale accepted draft on an optional
  question can be cleared only through the API (`/answers/clear`); the review page has no clear
  control yet (C12), so the user saves their own text or requests a new draft. Requesting a
  draft again for the same facts returns the cached draft even when already accepted, which the
  page does not show; reachable only with a draft provider, none of which is configured (C15).
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_sending.py` (20), `tests/test_package_contract.py` (3),
    `tests/test_repo_hygiene.py` (3), the new tenancy test in `tests/test_preparation.py`;
    `test_approval_hardening.py` (a stale draft is a checkpoint) and `test_execution_routing.py`
    (an adapter is given package-shaped content) updated;
  - full backend (`pytest tests`): first run 1019 passed, 1 failed, exit 1: a test defect from
    this change (the routing test built adapters with empty content `{}`, which the constructor
    now reads), fixed in the test; second run on the final tree 1020 passed, exit 0;
  - full Playwright: 36 passed, 2 skipped, exit 0;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: clean;
  - sabotage checks: 26, each caught, every file restored and compared afterwards (the hash
    check's sabotage, with a resolved answer changed, confirmed and sent before it was caught);
  - an adversarial read-only review (4 reviewers, 2 skeptics per finding): 13 findings. Fixed:
    the hygiene test would have failed on its own sample address once committed (it scanned
    only tracked files), it missed Playwright's capture paths, skipped files that are not
    UTF-8 and allowed any no-reply address; two doc counts; one policy row. Deferred: the two
    above. Refuted: the rest.
- **CI for the previous change:** **CI #98**
  ([39882681236](https://github.com/KevinD003/AutoApply/actions/runs/39882681236)) (`8038d4a`,
  I2 provider admission): passed (all four jobs).

## Provider admission (I2, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository**: no network request, no support state or
  capability level raised, no real destination enabled, Path A still pending. Decision D47;
  `docs/provider-admission.md`; evidence: `docs/evidence-matrix.md` ("Provider admission").
- **What exists:** `providers/admission.py` computes each provider's stage on one ladder from
  code tables and recorded evidence, with 37 checks over the framework's eleven requirements,
  four owner boundaries and a cap at `rehearsal_ready`; served read-only at
  `GET /api/providers/admission`. Every provider's support state is bounded by it (tested). New
  import-time rules (`check_spec`: capability/operation agreement, trait evidence, fixture
  declared, a CAPTCHA checkpoint where one may appear, `real_destinations_enabled` refused;
  `registry.check_registry`: names, ATS identities, one planned spec per ATS). The read-only
  runs are recorded as evidence (`evidence.READ_ONLY_RUNS`); no public-docs review is recorded.
- **Computed today:** `greenhouse_dom` and `greenhouse_readonly` at `observed_read_only`;
  `greenhouse_hosted`, `fixture_ats`, `fake_api`, `freehire`, `freehire_mock` at
  `fixture_only`; `lever` and `workday` at `planned` (next: the owner's public-docs review);
  `manual_handoff` at `registered`. None `rehearsal_ready`. Three waivers (the unrecorded
  Greenhouse terms review), five known identity gaps pinned with probes.
- **Found and fixed on the way** (each reproduced first):
  - D15 was not enforced: after a "not received" reconciliation the old approval was still live
    and queueing again sent the application a second time (receiver ledger: 2 accepted). The
    reconciliation now retires it (`reconciled_not_received`);
  - found by the review: a submission whose verification code was never entered left its
    approval live after the final click; it is now retired (`verification_not_completed`). A
    slow worker's receipt after a "not received" reconciliation was lost (an illegal
    transition); it now confirms the application, reconciliation locks the attempts first and
    refuses "not received" once a receipt is recorded, and a recorded confirmation is never
    queued again;
  - an approval given for a manual handoff was stored with no adapter, read as a pre-binding
    approval, and was queued for an adapter once the route changed. It now records
    `manual_handoff`;
  - an over-long ATS company or posting id was a 500 (DataError); the dedupe key is bounded, the
    posting id not stored, a URL that canonicalizes past its column refused (400); an over-long
    spreadsheet cell (found by the review) is its row's error instead of a 500;
  - an unlisted form source ran on the generic fixture adapter; it is refused (`no_adapter`);
  - five required fixture scenarios had no ledger test (reconciliation on the three browser
    adapters, a readback mismatch on `greenhouse_hosted`, the API upload failure); each has one.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_provider_admission.py` (150): the ten registered providers pinned; each of the
    37 checks met on a synthetic, never-registered example and broken by its own sabotage,
    which breaks exactly that check and its declared dependencies; every reachable stage
    reached exactly; the cap and four owner boundaries; frozen waivers; reads nothing,
    changes nothing, imports no browser code (subprocess); served values are fixed identifiers;
    the doc's tables equal the code;
  - `tests/test_provider_contracts.py` (39): identity contract for six ATS names, known-gap
    probes, fixture paths, code tables, receipt keys, route metadata, the recorded runs against
    the Runs table, the scenario mapping, the documented matrix and support states;
  - new or extended: `test_providers.py` (every `raise SpecError` has a case; registry
    problems), `test_approval_binding.py`, `test_execution_failures.py` (reconciliation on three
    adapters; the late receipt), `test_execution_security.py` (the abandoned code step),
    `test_rehearsal_prerequisite.py`, `test_greenhouse_adapter.py` (readback), `test_upload_evidence.py`,
    `test_jobs.py` (over-long cells), `test_reason_codes.py` (an unlisted source);
  - full backend (`pytest tests`): 993 passed, exit 0, after the review fixes (a run before
    them: 955 passed, exit 0);
  - full Playwright: 36 passed, 2 skipped, exit 0, both before and after the review fixes;
  - `ruff check` and `ruff format --check` clean; the frontend is unchanged;
  - sabotage checks: 51 (38 for the framework and the first fixes, 13 for the review's), each
    caught, every file restored and compared afterwards;
  - an adversarial read-only review (4 reviewers, 2 skeptics per finding): 20 findings, 9
    confirmed and fixed, among them one high (the abandoned code step's approval); 11 refuted,
    of which 5 were hardened anyway (waivers capped at the claim frozen at I2, the by-ATS view
    showing waivers, C and D as separate records, Path A's effect computed, the late receipt).
- **CI for the previous change:** **CI #97**
  ([39856144334](https://github.com/KevinD003/AutoApply/actions/runs/39856144334)) (`c385ce0`,
  the E6 lock-order follow-up): passed (all four jobs).

## Lock order and race guarantees (E6 follow-up, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository**; no support state, route or real destination
  changed, and no retry was added anywhere. Decision D46; `docs/architecture.md` ("Lock order",
  "Race guarantees"); evidence: `docs/evidence-matrix.md` ("Lock order and race guarantees").
- **The reported risk was real, and wider.** The worker paths locked the attempt, then the
  application; cancel locked the application, then the attempt (and recording evidence takes
  the application's key-share lock after the attempt). A cancel racing either gate, an
  outcome, evidence recording, the rehearsal stop or the sweeper deadlocked (PostgreSQL aborted
  one side). Fixed by one order: attempt, application, approval, the application's inputs,
  then the rehearsal record or receipt. Cancel and claim now follow it.
- **Also found and fixed** (an independent lock map and an adversarial review beside our own
  reading):
  - clearing an answer or consent deleted the input before taking the application (deadlock
    against a save);
  - cancel updated an application copy loaded before its wait (`StaleDataError`, a 500);
  - the gates read a REPEATABLE READ snapshot taken at their first statement: an answer or
    profile change committed while a gate waited was not seen, and a notes change made it
    refuse. They now take their locks and read at READ COMMITTED;
  - queueing again with an earlier attempt pending under a stale approval failed as a
    duplicate (a 500); that attempt (nothing disclosed) is now stopped, locked without waiting.
- **Disproved:** a duplicate delivery while a gate holds the attempt never waits or deadlocks
  (kept as a regression test).
- **Guarantees, stated precisely:** a change committed before a gate's check stops it; one
  arriving later waits if it writes a row the gate locks; a profile, document-library,
  answer-bank, form or API-authorization change committed after the gate read it does not
  wait and counts for later packages (what is sent is always the approved package). A per-user
  lock for those writers is deferred.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_lock_order.py` (26): two transactions on separate connections, barriers at
    exact lock points, lock waits read from `pg_stat_activity`, every side bounded to 30 s.
    On the old code: 4 deadlocks, 2 raw serialization errors, 1 stale copy (first 12 tests);
    then 4 missed edits, 1 spurious refusal and 1 duplicate 500 (the later tests); the
    duplicate-claim expectation was disproved. `test_gate_snapshot_race.py`,
    `test_rehearsal_stop.py` and `test_rehearsal_prerequisite.py` updated for read-after-locks
    (the refusal now names its reason);
  - focused: the execution, cancel, rehearsal, preparation and approval modules, all passed;
  - full backend (`pytest tests`): 767 passed, exit 0, after the review fixes (a run before
    them: 765 passed);
  - full Playwright, after the fixes (before the docstring and explicit-isolation edits): 36
    passed, 2 skipped, exit 0;
  - `ruff check` and `ruff format --check` clean; `npx tsc --noEmit` and `npm run lint` clean;
  - sabotage checks, 17 for this change, each caught (one only as a bounded 30-second hang);
    the E6 record and receipt lock checks re-run against the new reads, caught;
  - an adversarial read-only review (4 reviewers, 2 skeptics per finding): 10 findings
    confirmed, 3 refuted; all confirmed ones were wording or test-strength issues, fixed
    (the guarantee narrowed to what holds, tests that now prove the wait, the stop and
    sweeper races added).
- **CI for the previous change:** **CI #96**
  ([39829073076](https://github.com/KevinD003/AutoApply/actions/runs/39829073076)) (`b5ab47b`,
  E6): passed (all four jobs).

## Rehearsal prerequisite (E6, 2026-10-22; fixtures only, no external request)

- **Nothing changed outside the repository**, no support state changed, and no real
  destination is enabled: real destinations are still refused before the rule is reached
  (manual handoff, `real_destination_disabled`). Decision D45; `docs/rehearsal-prerequisite.md`;
  evidence: `docs/evidence-matrix.md` ("Rehearsal prerequisite").
- **The rule:** before the first submission through an employer/provider path (user, adapter,
  normalised origin, board), a successful, recorded, disclosure-only rehearsal on that path is
  required. The newest result on the path decides, by when it finished: a valid rehearsal
  record named by the approval to submit (`met`), or a confirmed submission whose own send gate
  found the prerequisite held, with its receipt retained (`established`). A rehearsal is never
  permission to submit.
- **Five layers:** approve, enqueue, claim, the disclosure gate and the send gate; in the gates
  what is relied on is locked FOR SHARE. Fail-closed; 12 fixed reason codes in their own
  vocabulary, shown on the review page; a rehearsal can be withdrawn.
- **Path stored only as a keyed reference** (migration `33c1622938ba`): never served, logged or
  audited. Fixture paths get the rule only through a test-only setting (`env == "test"`), which
  can only add it; the e2e backend now runs with `env` `test` for it.
- **Fixed on the way:** a claim that refused a re-pended attempt (application already
  `running`) left the application `running`, also for the existing approval refusal; it now
  waits for the user. The test harness's `queue()` returned an arbitrary attempt of the
  application, now the newest.
- **Package content unchanged** (`SCHEMA_VERSION` unchanged, no package hash changes).
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_rehearsal_prerequisite.py` (33), `tests/test_rehearsal_codes.py` (17),
    `tests/test_pilot_readiness.py` (+1), `tests/test_support_wording.py` (the new labels);
    first run of the new modules: 10 failed and 32 passed. Causes, all in the tests: a default
    slug that put rehearsals on another path, the wrong upload-failure switch for the clinic
    form, a missing candidate profile, `queue()` returning an arbitrary attempt, and the doc
    not yet written;
  - an adversarial read-only review (6 reviewers, 2 skeptics per finding): 20 findings
    confirmed, 3 refuted. Fixed: "newest" ordered by queue time instead of finish time (a
    rehearsal failing last could be outvoted); an approved manual handoff shown as needing a
    rehearsal; the re-claim left `running`; withdrawal offered for a rehearsal with no record;
    submitting not disabled while unmet; card wording; missing tests (adapter version and
    class on an established path, a newer failure after it, the receipt lock, a submission made
    before the rule applied); an e2e wait that did not wait; doc wording (D45's 30 days, the
    status header);
  - focused: the rehearsal, rehearsal-stop, prerequisite and codes modules, 80 passed;
  - full backend (`pytest tests`): 741 passed, exit 0 (a first run was stopped by the
    sandbox's 30-minute background limit at 97% with no failure, and re-run in full);
  - full Playwright: 36 passed, 2 skipped (the desktop-only configuration checks), exit 0, run
    after the review fixes; the new `rehearsal-prerequisite.spec.ts` on desktop and mobile;
  - `ruff check` and `ruff format --check` clean; `npx tsc --noEmit` and `npm run lint` clean;
  - sabotage checks, 28, each caught (an exception read as met was missed at first; a test
    was added): see the evidence matrix.
- **CI for the previous change:** **CI #95**
  ([39802170059](https://github.com/KevinD003/AutoApply/actions/runs/39802170059)) (`122903a`,
  E5 step 3): passed.

## Rehearsal stop, rehearsal records and readiness evidence (E5 step 3, 2026-10-22; fixtures only, no external request)

- **Nothing changed outside the repository**, no support state changed, and no real
  destination is enabled. Evidence: `docs/evidence-matrix.md` ("Rehearsal stop, rehearsal
  records and readiness evidence"); decision D44; `docs/upload-and-submission-evidence.md`.
- **Fixed: a rehearsal ended `rehearsed` without any check.** A revocation, a content change
  or a lost lease after the disclosure gate still let it end as a successful rehearsal, and
  a retirement was recorded for an approval already revoked. Now the stop
  (`service.finish_rehearsal`) is a gate: every gate check again under the attempt,
  application and approval locks, then the evidence rows checked. Only then, in one commit,
  the rehearsal record, `rehearsed` and the approval used up. A refusal ends `abandoned`; an
  evidence refusal carries a fixed reason code on its event.
- **Rehearsal record** (`rehearsal_records`, migration `0b1c00a7e222`): counts and fixed values
  only. It holds only while its evidence rows agree with it, it is younger than 30 days, its
  adapter version is current and it is not revoked. Deleting an application's evidence
  revokes its records.
- **New evidence row** `recheck` (`{"form": "matched"}`) after the post-fill form check; the
  API route reads its schema again before a rehearsal's stop.
- **Destination class** (`fixture` or `real`) recorded on each attempt at queueing; each gate
  refuses an attempt whose destination is no longer that class.
- **Readiness** (`GET /api/providers/greenhouse_dom/readiness`) now counts the signed-in
  user's own records by evidence class (`fixture`, `public_doc_expectation`,
  `read_only_observation`, `rehearsal`, `real_submission`, kept apart in
  `providers/evidence.py`). Each condition names the one class that can meet it. Fixture
  evidence meets nothing; with real destinations disabled, `real_upload` and
  `real_submission` stay not met whatever is recorded. Still 0 of 7.
- **Package content unchanged** (`SCHEMA_VERSION` unchanged, no package hash changes).
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_rehearsal_stop.py` (25 tests) and `tests/test_pilot_readiness.py` (10, of which 5
    new), with the rehearsal, upload-evidence, gate-race, audit-inventory, doc-reference,
    evidence-lifecycle, API-provider and migration modules: 76 passed before the review fixes;
    first run of the new modules: 7 failed and 29 passed. Two causes, both fixed:
    - the stop refused every browser rehearsal: it treated requests the egress proxy denied
      as disqualifying (the browser's own background requests are denied), which is now
      counted, not disqualifying;
    - four tests acted before the worker reached the stop: they now wait for it;
  - an adversarial read-only review (5 reviewers, 2 skeptics per finding): 11 findings, 9
    confirmed and fixed, 2 refuted (one of them, the savepoint, kept: a test shows it matters);
  - full backend (`pytest tests`): 690 passed;
  - full Playwright: 34 passed, 2 skipped (the desktop-only configuration checks);
  - `ruff check` and `ruff format --check` clean; no frontend change;
  - sabotage checks, 12, each caught:
    - the stop without the gate;
    - the evidence check skipped;
    - no recheck row;
    - no API re-read;
    - `real_upload` met by real destinations alone;
    - fixture records counted as rehearsal evidence;
    - other users' records counted;
    - no savepoint;
    - records not revoked on evidence deletion;
    - no class check;
    - age ignored;
    - the record not compared with its rows (missed at first; a test was added, then caught).
- **CI for the previous change:** **CI #94**
  ([39794330555](https://github.com/KevinD003/AutoApply/actions/runs/39794330555)) (`97e4cfd`,
  gate approval lock): passed.

## Gates and concurrent revocation (2026-10-22; local only, no external request)

- **Fixed (approval gating, fail-open):** a gate's REPEATABLE READ snapshot is taken at the
  attempt lock, before the application lock. A revocation committed while the gate waited for
  the application lock was not in that snapshot. The disclosure gate then allowed filling, and
  the send gate allowed the submit, after the user had revoked. Found while designing E5 step
  3; reproduced first by a deterministic test (2 failed), then fixed.
- **Now:** each gate also locks the attempt's approval row. A change to it after the snapshot
  is a serialization failure, and the gate refuses ("the approval changed while it was being
  checked"). Decision D43; evidence: `docs/evidence-matrix.md` ("Gates and concurrent
  revocation").
- **Noted from reading the code, not reproduced, not changed here:** the gates lock the
  attempt, then the application; cancel locks the application, then the attempt. By that lock
  order, a cancel racing a gate can end in a PostgreSQL deadlock, which aborts one side. The
  gate side would stop the attempt as an internal error (`failed_safe` before disclosure,
  `abandoned` after), and the cancel side would return an error the user can retry. Both fail
  closed.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_gate_snapshot_race.py` (2 tests): 2 failed on the code before the fix
    (reproduction), 2 passed after it; with the core execution modules (`test_execution`,
    `test_execution_validation`, `test_execution_failures`, `test_rehearsal`): 57 passed;
  - full backend (`pytest tests`): 660 passed;
  - `ruff check` and `ruff format --check` clean; no frontend change;
  - sabotage check, caught: the approval lock removed (both tests fail).
- **CI for the previous change:** **CI #93**
  ([39780495364](https://github.com/KevinD003/AutoApply/actions/runs/39780495364)) (`1b06bd4`,
  E5 step 2): passed.

## Upload evidence and rehearsal results (E5 step 2, 2026-10-22; fixtures only, no external request)

- **Nothing changed outside the repository**, no support state changed, and no real
  destination is enabled. Evidence: `docs/evidence-matrix.md` ("Upload evidence and rehearsal
  results"); decision D42; `docs/upload-and-submission-evidence.md`.
- **Fixed: a failed upload lost its evidence.** When an upload was refused, every upload
  evidence row of that attempt was dropped with the exception, including uploads that had
  already reached the employer. A form with a resume and a cover letter whose cover letter
  failed kept no disclosure evidence at all. Now the evidence of each upload, the failed one
  included, is recorded before the attempt stops (`abandoned`, as before), on every browser
  adapter and the API route. An upload the page never acknowledges (before, an internal
  error) is now its own outcome, with `ack: none`.
- **Upload evidence:** the field, the digest of the approved document sent, and the
  acknowledgement as a fixed value:
  - page: `attachment_shown`, `error_shown`, `none`;
  - API: `digest_matched`, `not_kept`.

  The page's own attachment id is no longer kept.
- **Rehearsal results:** an approval a rehearsal used up is shown as `used_by_rehearsal`
  (derived from its `rehearsed` attempt), not as an invalidation. Applications carry their
  latest attempt (`last_attempt`), so the tracker shows "Rehearsal finished: nothing
  submitted".
- **Fixtures:** the receiver can refuse one field's upload (`upload_fail_field`) and answer an
  upload late (`upload_delay_s`); the fake API honours `upload_fail` for documents.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - upload-evidence and rehearsal modules (2 files, 16 tests): 16 passed;
  - full backend (`pytest tests`): 658 passed (a first full run was lost to a container
    restart and was run again from the start);
  - rehearsal e2e (desktop and mobile): 2 passed; full Playwright: 34 passed, 2 skipped (the
    desktop-only configuration checks);
  - `ruff check` and `ruff format --check` clean; `tsc --noEmit` and `npm run lint` clean;
  - sabotage checks, each caught: earlier uploads dropped (id-mapping and hosted adapters),
    the runner ignoring the evidence (browser and API routes), the page's own id kept, an
    unacknowledged upload not caught, an API failure without evidence, and a used rehearsal
    shown as an invalidation.
- **CI for the previous change:** **CI #92**
  ([39764334996](https://github.com/KevinD003/AutoApply/actions/runs/39764334996)) (`b0f31e7`,
  E5 step 1): passed, the Compose execution test included.

## Rehearsal: disclosure without submission (E5 step 1, 2026-10-22; fixtures only, no external request)

- **Nothing changed outside the repository**, no support state changed, and no real
  destination is enabled. Evidence: `docs/evidence-matrix.md` ("Rehearsal: disclosure without
  submission"); decision D41; `docs/upload-and-submission-evidence.md`.
- **Before:** every approval covered filling and submitting. Permission C (disclosure) could
  not be given, or proven, without permission D (submission).
- **Now:**
  - an approval has a scope: `submit`, the default, or `disclose_only`, a rehearsal;
  - a rehearsal runs exactly like an attempt to submit up to the send gate (disclosure gate,
    filling, uploads, readback, the form re-checked), then ends `rehearsed`: nothing was
    submitted;
  - it uses its approval up in the same transaction. Submitting afterwards needs an approval
    to submit and a new attempt, which repeats every check;
  - the send gate refuses any approval that is not `submit`, so a rehearsal cannot submit
    even if the runner's stop were bypassed;
  - approving with the other scope while an approval is active is refused: revoke first;
  - the review page offers "Approve a rehearsal" and shows the result on the attempt. The
    tracker does not show it yet (step 2 in `docs/upload-and-submission-evidence.md`).
- **No package hash changed:** the scope is on the approval, not in the package content
  (`SCHEMA_VERSION` unchanged). Migration `9597307f950d` adds the column, with `submit` for
  every existing approval, which is what each was given for.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - rehearsal module (`tests/test_rehearsal.py`, 7 tests): 7 passed;
  - full backend (`pytest tests`): 649 passed;
  - rehearsal e2e (desktop and mobile) with the submission specs: 22 passed; full Playwright:
    34 passed, 2 skipped (the desktop-only configuration checks);
  - `ruff check` and `ruff format --check` clean; `tsc --noEmit` and `npm run lint` clean;
  - sabotage checks, each caught: the runner's stop removed (browser route, API route), the
    send gate's refusal removed, both removed (a rehearsal then submits), the approval not
    used up, the scope not stored, and the other scope swapped in silently.
- **CI for the previous change:** **CI #91**
  ([39757737713](https://github.com/KevinD003/AutoApply/actions/runs/39757737713)) (`8de730a`,
  Lever): passed.

## Lever as a planned provider (F1, F2, F4, F5, 2026-10-22; local only, nothing read from Lever)

- **Nothing changed outside the repository.** No Lever page, API or documentation was read,
  and no support state was raised: `lever` is a planned specification with nothing
  implemented. Evidence: `docs/evidence-matrix.md` ("Lever as a planned provider"); decision
  D40; `docs/provider-architecture.md` §7b.
- **Identity (F1):** Lever postings are identified from known hostnames and a UUID posting id
  only. Identity variants and lookalikes are tested.
- **Traits (F2):** CAPTCHA `expected`; login, multi-step and verification `unknown`, noted as
  unverified expectations.
- **Route (F4):** a Lever job is a manual handoff that says Lever is not supported yet
  (`planned_adapter_only`). Before, it got the general real-destination refusal (B7). It is
  never routed to another ATS's adapter.
- **Support state (F5):** "Planned only: no automation exists". The routing-vocabulary table
  in the architecture doc gained a Lever column and is now tested against the registry, column
  by column.
- **Moved:** the form-ATS mismatch tests use a fictional Ashby posting, since Lever's own
  planned refusal now comes first.
- **Not done here:** a Lever fixture (F3) and a pilot-readiness framework (F6); each needs its
  own step, starting with an approved review of Lever's public documentation.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - Lever, reason-code, execution-routing and support-wording modules (4 files): 57 passed;
  - full backend (`pytest tests`): 642 passed;
  - Playwright: 32 passed, 2 skipped (the desktop-only configuration checks);
  - `ruff check` and `ruff format --check` clean;
  - sabotage checks, each caught: login claimed "no", no CAPTCHA expected, Lever unlinked
    from its ATS, and a drifted cell in the documented table.
- **CI for the previous change:** **CI #90**
  ([39752326150](https://github.com/KevinD003/AutoApply/actions/runs/39752326150)) (`e67a6ca`,
  E3, E4): passed.

## Greenhouse: location without hidden coordinates (E4, 2026-10-22; design only)

- **Design only, no behaviour change:** `docs/location-handling.md`.
- **Rules that do not change:**
  - hidden coordinates are never written;
  - nothing is typed into a search picker;
  - a location question's meaning (residence fact or target preference) is never inferred.
- **Options:** the four options, and the evidence each would need. Only a visible plain-text
  control could change the outcome without a change of policy.
- **Decision:** location postings stay a checkpoint, as tested today.

## Greenhouse: page controls the job data does not list (E3, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository**, and no support state changed. Evidence:
  `docs/evidence-matrix.md` ("Greenhouse: page controls the job data does not list").
- **Before:** the id-mapping extractor ignored visible controls that no job-data question
  names (on the real page, `u1`–`u5`). A form with them got a normal route, and the user could
  approve and queue it. Only the attempt then stopped before disclosure ("N new field(s)").
- **Now** (`preparation/greenhouse_dom.py`, extraction version `greenhouse-dom-v2`):
  - each such control is captured as a blocking field (`unsupported`, required, with a fixed
    reason). What it asks, and whether it is required, are never inferred;
  - so the route is a checkpoint (`unsupported_required_control`), the package lists them as
    unresolved, and approval is refused before anything is queued;
  - capture and the adapter share one filter (`unlisted_controls`). A control that appears
    only after approval still stops the attempt before disclosure;
  - the extractor version is part of the adapter version, so an approval given before this
    change is retired by the existing binding check when it is queued.
- **Tests:** the dropdown-strategy test for such controls is now two:
  - from capture: a checkpoint, unresolved, approval refused, 0 disclosures;
  - after approval: a stop before disclosure.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - dropdown-strategy, id-mapping, required-signal and first-fixture adapter modules (4
    files): 88 passed;
  - full backend (`pytest tests`): 630 passed;
  - Playwright: 32 passed, 2 skipped (the desktop-only configuration checks);
  - `ruff check` and `ruff format --check` clean;
  - sabotage checks, each caught: the controls not captured, captured as optional, and the
    run-time check dropped.
- **CI for the previous change:** **CI #89**
  ([39746591121](https://github.com/KevinD003/AutoApply/actions/runs/39746591121)) (`530939d`,
  E7, E8): passed.

## Greenhouse: Path A record and pilot readiness (E7, E8, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository.** No page was visited, no support state changed,
  and no manual observation was recorded: the Path A record ships `pending`, and every answer
  in the tests is synthetic. Evidence: `docs/evidence-matrix.md` ("Greenhouse: Path A record
  and pilot readiness"); decision D39.
- **Path A (E7):**
  - `providers/path_a.py` keeps the owner's optional manual dropdown check
    (`docs/manual-dropdown-checklist.md`) only as its fixed choices, with the date and the
    owner as source, in `docs/evidence/path-a.json`. Wording, names, links and free text are
    refused without echoing them;
  - its assessment is advisory: a bounded strategy a fixture would have to prove next, the
    blockers that stay, and the profile a mirroring fixture must reproduce. It never changes
    support, a route or an approval.
- **Pilot readiness (E8):**
  - `providers/readiness.py` derives the seven conditions of `docs/greenhouse-readiness-gap.md`
    from evidence of their own kind: registry levels, `real_destinations`, and the gate's
    permissions (recorded nowhere yet). Path A is shown beside the conditions it bears on and
    meets none of them;
  - it is served at `GET /api/providers/greenhouse_dom/readiness` to signed-in users. The
    documented status table is tested against it;
  - today: 0 of 7 met, not proposable.
- **Tests:** new `tests/test_path_a.py` (18 tests) and `tests/test_pilot_readiness.py` (5
  tests).
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - Path A, readiness, API-path, provider, doc-reference, routing and wording modules (7
    files): 67 passed;
  - full backend (`pytest tests`): 629 passed;
  - `ruff check` and `ruff format --check` clean. No frontend file changed, so Playwright was
    not rerun (its last run, for B7, passed);
  - sabotage checks, each caught: free text accepted, the record filled in for the owner,
    Path A allowed to meet a condition, a drifted documented status row, and the readiness
    endpoint without authentication.
- **CI for the previous change:** **CI #88**
  ([39742542513](https://github.com/KevinD003/AutoApply/actions/runs/39742542513)) (`4c603ae`,
  B7): passed.

## Real destinations are told the truth before any form step (B7, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository**, and no route changed: every affected job was a
  manual handoff before and still is. Only the reason and the message changed.
- **Before:** a job on a real employer's site, or any job in production, was told "Capture the
  application form first." But reading real postings is refused, and no provider is enabled
  for real destinations, so a captured form could not have changed the route.
- **Now** (`routing.route_for_job`): the enabled gate comes before the form step. Such a job
  gets `real_destination_disabled` or `production_disabled`, with the adapter policy's own
  wording (now shared constants in `execution/policy.py`). A local fixture, or a job without
  an address, still goes on to the form. `decide` keeps its own gate for captured
  destinations.
- **Tests:** `test_a_real_destination_is_told_so_before_any_form_step` (new, in
  `tests/test_reason_codes.py`). The Freehire import test now expects the real-destination
  reason for imported jobs on non-fixture sites, and `routing.spec.ts` shows it on the job page.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - routing, discovery, provider, audit and wording modules (7 files): 137 passed;
  - full backend (`pytest tests`): 606 passed;
  - Playwright: 32 passed, 2 skipped (the desktop-only configuration checks);
  - frontend typecheck and lint clean; `ruff check` and `ruff format --check` clean;
  - sabotage: removing the gate from `route_for_job` fails the new test.
- **CI for the previous change:** **CI #87**
  ([39738067184](https://github.com/KevinD003/AutoApply/actions/runs/39738067184)) (`5bbe641`,
  A8): passed, including the Compose execution test against the body-keyed routes, which could
  not run locally.

## Question keys out of URL paths (A8, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository.** Evidence: `docs/evidence-matrix.md` ("Question
  keys out of URL paths"); decision D38.
- **Before:** four routes put a posting's question key in the URL path:
  - `PUT` and `DELETE /api/applications/{app_id}/answers/{key}`;
  - `PUT /api/applications/{app_id}/consents/{key}`;
  - `POST /api/applications/{app_id}/answers/{key}/draft`.

  NoEfforts' own logs recorded route templates only, but a proxy placed in front of the app
  would have logged the keys.
- **Now:**
  - the key travels in the request body: `PUT …/answers`, `POST …/answers/clear`,
    `PUT …/consents` and `POST …/drafts`;
  - keys are validated with the form-field key pattern, so a malformed key is refused before
    any handler runs;
  - the old routes are removed, and a request that still uses one is `unmatched_route` 404;
  - every caller moved: the application page, the e2e submission spec, the backend tests and
    the Compose execution test.
- **Tests:** new `tests/test_api_paths.py` (3 tests). It reads the OpenAPI schema and fails on
  any path parameter that is not a UUID or one of NoEfforts' own names. `tests/test_access_log.py`
  now shows the body-keyed route as its plain template and the old form as unmatched.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - the new and rewritten modules (12 files): 151 passed;
  - full backend (`pytest tests`): 605 passed;
  - Playwright: 32 passed, 2 skipped (the desktop-only configuration checks);
  - frontend typecheck and lint clean; `ruff check` and `ruff format --check` clean; the
    Compose execution test compiles and passes `ruff check`, but needs Docker and runs in CI
    only;
  - sabotage checks, each caught: a key-in-path route re-added, the key pattern dropped, and
    the ownership check dropped from the new clear route.

## Support-state wording (B6, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository**, and no support state changed: the wording now
  follows from the evidence already recorded. Evidence: `docs/evidence-matrix.md`
  ("Support-state wording").
- **Before:** support wording came from three unconnected places. The registry's status lines,
  the discovery router's own status table, and badges hard-coded on two pages. The two pages
  described the same captured form in different words, and nothing stopped a page from
  writing a claim with no evidence behind it.
- **Now** (`providers/wording.py`, decision D37):
  - a provider's support state is derived from its stage and capability levels (`manual`,
    `planned`, `fixture_only`, `observed_read_only`, `not_supported`). A live level has no
    label, so no page can show one until it is added deliberately;
  - an API or browser route is always labelled with the evidence behind it ("Browser adapter
    (local test fixture only)"), and is refused if it has none;
  - a captured form from a local test stand-in says so, in one wording on both pages;
  - the API serves every label: providers, discovery sources, job and discovery routes
    (`label`, `provider_support`), forms (`source_label`) and the package view (`labels`,
    outside the package content, so no hash or approval changes);
  - the pages show the served labels and write none of their own. The job page no longer
    promises that reading live employer forms "arrives later", and its button reads "Read
    Greenhouse-style test form";
  - the registry's status lines and the discovery sources' notes remain as fuller
    descriptions next to the labels; the badges show the labels.
- **Tests:** new `tests/test_support_wording.py` (8 tests). It reads the frontend sources for
  hard-coded labels and the capture code for every stored form source. Four e2e specs assert
  the served wording, and the job and application pages show the same form label.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - wording, routing, discovery, provider, preparation, application, job, Greenhouse,
    audit-inventory, doc-reference and approval-binding modules (14 files): 209 passed;
  - full backend (`pytest tests`): 602 passed;
  - Playwright: 32 passed, 2 skipped (the desktop-only configuration checks);
  - frontend typecheck and lint clean; `ruff check` and `ruff format --check` clean;
  - sabotage checks, each caught: a page hard-coding a qualifier, observed evidence ignored,
    a live label added, a bare API or browser route allowed, a label claiming support, a
    stored form source without wording, the package view dropping its label.
- **CI:** **CI #86** ([39733244668](https://github.com/KevinD003/AutoApply/actions/runs/39733244668))
  (`aa06a85`): passed.

## Route reason codes and route truthfulness (Group B, 2026-10-22; local only, no external request)

- **Nothing changed outside the repository:** no external request, credential, permission or
  provider configuration. No support state, routing order or live gate changed. Evidence:
  `docs/evidence-matrix.md` ("Route reason codes and route truthfulness").
- **Reason-code contract (B1):**
  - `routing.REASONS` is the canonical list of 14 codes. `docs/provider-architecture.md`
    ("Reason codes") lists each with its route and the path that produces it;
  - `no_supported_provider` is the named fail-closed fallback (`routing.FALLBACK_REASON`): the
    default of `RouteDecision` and `UnsupportedDestination`, and what an unknown code is
    recorded as. No path produces it;
  - new `tests/test_reason_codes.py` (23 tests). Every other code is produced through its own
    path; every decision and refusal in the source names a listed code (read from the
    source); 576 sample decisions never reach the fallback; the documentation table equals
    `REASONS`.
- **Route cleanup (B2):**
  - redundant local imports removed from `route_for_job`;
  - the evidence level behind a route is computed in one place (`routing.evidence_level`) for
    the API responses and the audit row;
  - the router's own real-destination gate, which holds even if `policy.adapter_for` were
    changed to accept a real origin, is kept on purpose and now has its own test;
  - a browser refusal (no submit address, or a cross-origin one) does not block an authorized
    API route, because the API adapter sends only to the authorized origin's own API. This is
    now documented and tested.
- **Discovery routes (B3):**
  - a posting closed at its source before it was linked was told "Import this job manually."
    with `source_record_incomplete`. It now says it was closed and not added to the tracker
    (`source_posting_closed`);
  - `GET /api/discovery/jobs/{id}` returns the route's reason code, grant state and evidence
    level, and records a linked record's route like the job page does.
- **Route-audit deduplication (B4):** a `route.decision` event is recorded only when the
  decision differs from the job's last recorded one; a route shown again unchanged adds
  nothing. Two concurrent first checks may each record one. The audit inventory test now fails
  on `record(**...)`, which would hide an event's keys.
- **Provider on the route card (B5):** for an API or browser route the job page shows
  "Provider: <key> · evidence: <level>" (`fixture` today); a checkpoint or manual route shows
  no provider.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_reason_codes.py` with the audit-inventory and doc-reference tests: 26 passed;
  - routing, discovery, audit, provider, job and approval-binding modules (11 files): 169
    passed;
  - full backend (`pytest tests`): 594 passed;
  - Playwright (`npx playwright test`): 32 passed, 2 skipped (the desktop-only configuration
    checks of `log-privacy.spec.ts`), including the extended `routing.spec.ts` on desktop and
    mobile;
  - frontend typecheck and lint clean; `ruff check` and `ruff format --check` clean;
  - sabotage checks, each caught: removing the deduplication, a refusal left on the default
    code, removing the router's own real-destination gate, a missing documentation row,
    `record(**meta)`, removing the closed-posting branch, not auditing the discovery view, and
    a code added without a path.
- **Not done here:** support-state wording (B6, the entry above). The deduplication reads the
  job's last route row through the per-user index; no composite index was added.
- **CI:** **CI #85** ([39728771798](https://github.com/KevinD003/AutoApply/actions/runs/39728771798))
  (`02e0be4`): passed.

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
    (`051b200`, Phase 11B access logs): passed;
  - **CI #84** ([39724014142](https://github.com/KevinD003/AutoApply/actions/runs/39724014142))
    (`8447c79`, Phase A5-A7 retained errors, evidence and library logs): passed.

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
- **Known, not fixed here:** four API paths still carried a posting's question key (answers,
  consents, drafts), which a proxy in front of the app could log; fixed on 2026-10-22 (A8,
  "Question keys out of URL paths" above). The CI test database logs
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
| Answer bank with provenance, approval, version, timestamps | partial: an answer is approved when saved (the approval status is nominal); edit-in-place UI not built (delete and re-save); bound to its help text; answers that depend on the employer, the job or the date (employer, time, pay, place, fact, section, follow-up, repeated wording) are never saved or reused; concurrent saves and deletes serialize (C6, D51) | `test_answer_bank_*` |
| Acknowledgments never auto-checked; sensitive answers need consent | partial: never auto-checked and consent required; a statement of a profile fact checked only with a true approved fact (C3); sensitive detection covers more topics and the help text, options, section and follow-ups (C5); consent is tied to the question key, not its wording or value (C7); the disclose path has no end-to-end ledger test yet (C8) | `test_question_safety.py`, `test_question_safety_api.py`, resolver + API tests |
| Missing facts park the application; profile fix resolves | complete | `test_missing_fact_parks_application_and_profile_fix_resolves` |
| Immutable package versions; approval bound to content hash | complete | `test_package_versions_are_immutable` |
| Invalidation on fact, document, answer, consent, destination change; unrelated edits keep approval | complete | `test_protected_fact_change_invalidates_approval`, `test_other_material_changes_invalidate_approval` (4 cases), `test_unrelated_fact_change_keeps_approval` |
| Queueing requires live approval | complete | API tests |
| Review screen | complete | Playwright `phase-b.spec.ts` |
| Long-form drafting interface with grounding validation | partial: interface, validation, caching, acceptance flow done and tested with a **test-only fake provider**; **no real LLM provider is implemented**, so drafting shows as unavailable | `test_fake_provider_draft_is_validated_and_needs_acceptance`, `test_drafting_unavailable_without_provider` |
| Tenant isolation for forms, packages, answers, consents, documents, answer bank, revoke, document selection, draft acceptance | complete | `test_tenant_isolation_for_preparation`, `test_tenant_isolation_for_revoke_documents_drafts_and_the_bank` |
| Resume parsing into proposed facts | not started (resolver already ignores proposed facts) | — |
| Only resolved answers are sent; stale accepted drafts are checkpoints | complete (C2, D48) | `tests/test_sending.py` |
| Package content shape pinned to `SCHEMA_VERSION` | complete (C1) | `tests/test_package_contract.py` |
| Truthful resume tailoring | not started | — |
| Cover letters | upload only: no generation, and the review page cannot select one (C12) | — |
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
