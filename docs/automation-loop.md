# Greenhouse + Workday automation loop: continuation record

One concise, sanitized record of where the loop stands, so work can resume from it. No personal
answers, credentials, employer-identifying evidence, raw pages or unredacted logs belong here. The
canonical backlog is `docs/remaining-work.md` (its "Automation loop" section); decisions are in
`docs/decisions.md`.

**Updated:** 2026-11-10 (UTC).

## Objective

Open an application, identify its questions, sections and controls, and resolve them from approved
facts and saved answers. Fill what is supported and read it back. Find conditional questions and
later pages. Send anything unknown to a separate "Questions needing your answer" tab, where the user
answers and chooses whether to save it (with its meaning, context and reuse scope). Then resume only
after re-checking the page and the permissions, reusing compatible answers. Submit only under
application-specific authorization, record the confirmation, and never duplicate a submission.

The target is Greenhouse and Workday, with the 14 acceptance workflows below for both.

## State

| What | Where |
|---|---|
| `main` | 25d04ea (tree a3054b8, as predicted): #51 D142. Before it, 98fe380 (tree b75d64c): #50 D141; 3df7d0d (tree a625f26): #49 D140; 4585c59 (tree fac890a): #48 D139; a7f8742 (tree af2f25f): #47 D138; e2fd286 (tree 1d69376): #46 D137; 32c8f7c (tree 201ddbd): #45 D136; 53b28af (tree fe5c8c3): #44 D135 (main CI #269 green on all four jobs); 2e10418 (tree 3a18998): #43 D134 (main CI #267 green on all four jobs); da7ac61 (tree d2214b6): #41 D133 (main CI #265 green); ab671e1: #42, the receiver's reset in one transaction (main CI #263: the backend job failed, not investigated; every later run passed); c19c683: #40 D132 (main CI #260 green) |
| D131 follow-up (the review's remaining findings) | merged (#39, bd38529); main CI #254 passed all four jobs |
| D132 form-change pause and questions tab | merged (#40, c19c683); main CI #260 passed all four jobs |
| D133 reuse and suggestion guards | merged (#41, da7ac61); its PR CI passed all four jobs on 360f34c, and main CI #265 on da7ac61 |
| D134 the standing rule respects your pause and revocation | merged (#43, 2e10418); its PR CI passed all four jobs on 118b4b9, and main CI #267 on 2e10418 |
| D135 a question the page shows after an earlier answer | merged (#44, 53b28af); its PR CI passed all four jobs on 2d3c07c, and main CI #269 on 53b28af |
| D136 a control NoEfforts cannot fill is refused when the form is read | merged (#45, 32c8f7c); its PR CI passed all four jobs on 9602bda |
| D137 what reached the employer stays recorded whatever fails after it | merged (#46, e2fd286, tree as predicted); its PR CI passed all four jobs on a9b6880 (CI #276) |
| D138 saved answers on Greenhouse- and Workday-shaped forms | merged (#47, a7f8742, tree as predicted); its PR CI passed all four jobs on ea11c6e |
| D139 your self-identification on Greenhouse- and Workday-shaped forms; a change retires its approvals at once | merged (#48, 4585c59, tree as predicted); its PR CI passed all four jobs on 3df9d9d |
| D140 education and work history reviewable and diffed; a record edit retires its approvals at once | merged (#49, 3df7d0d, tree as predicted); its PR CI passed all four jobs on 48fde99 |
| D141 an employment stand-in; section comboboxes safe on react-select pages | merged (#50, 98fe380, tree as predicted); its PR CI passed all four jobs on 2ead6ff |
| D142 a Workday-style multi-page wizard, filled forward only; never run again once entered | merged (#51, 25d04ea, tree as predicted); its PR CI passed all four jobs on 85e0213 |
| D143 recovery hardening: a run budget, one task time limit and no soft limit, leases that follow progress, verification requests that end with their attempt | branch `recovery-hardening` (from D142's branch, 85e0213, with `main` merged in); reviewed independently, its seven findings fixed (bb94e9f); not merged |
| Outcome state | Not complete. Every item below is at most **synthetic-fixture**. Live verification is **blocked externally** (see Blockers) |

## Acceptance matrix (2026-11-06)

Evidence levels:
- **fx**: synthetic fixture with the receiver ledger.
- **unit**: unit or API tests only.
- **absent**: not built.
- **ext**: blocked externally.

Nothing is **real-observed** except read-only Greenhouse mapping and dropdown opening (runs #4, #6,
#9-#11).

| # | Workflow | Greenhouse | Workday |
|---|---|---|---|
| 1 | Known answer fills and survives readback | fx (gh2 stand-in) | fx, single-page approximation; D142 merged (#51): the five-page wizard stand-in, each page read back before its Next, the unanswered fields included (receiver ledger) |
| 2 | New question → questions tab → saved → resumes | fx (gh2 by id and pilot stand-in), on `main` since D132 (#40) | fx (e2e), on `main` since D132 |
| 3 | Future reuse | unit (resolver), generic form; D133 merged (#41): suggestions judge the saved side, "Use here only"; D138 merged (#47): a saved answer reaches the next gh2 job that asks the same question (receiver ledger) | D138 merged (#47): reused on the next posting (receiver ledger); single page |
| 4 | Unsafe similar question refused | unit; D131 merged (#36); more wordings in #39; D133 merged (#41): word-level vetoes over label and help, a rule floor under the model; D138 merged (#47): a gh2 look-alike naming a country is neither reused nor suggested | D138 merged (#47): "Preferred shift" never saved or reused |
| 5 | Conditional question | fx on the v1 fixture; D135 merged (#44), on the id-only structure (gh2, by id and pilot stand-in, receiver ledger): a typed question the page reveals is answerable, entered only when shown, and a revealed required one pauses; a choice or upload hidden at load is still never filled | absent (no branching fixture) |
| 6 | Unsupported widget → checkpoint | fx at capture; D136 merged (#45): on the id-only structure every control the adapter cannot fill (a native dropdown, a checkbox, a list of several choices) is refused when the form is read, a required one a checkpoint, an optional one left blank (gh2, receiver ledger) | fx at capture |
| 7 | Repeating records | fx education stand-in (D120); D140 merged (#49): the rows sent shown on the review page and diffed by record and field; D141 merged (#50): an employment stand-in (current and past roles, rows in their own sections) and react-select-safe section comboboxes, read back before the send gate (receiver ledger) | absent |
| 8 | Answer edits invalidate approvals | fx; D138 merged (#47): on gh2, editing the saved answer retires the approval that used it; approved again, the new value is sent (receiver ledger); D140 merged (#49): an education or employment edit retires the approval at once; on the education stand-in, approved again, the new degree is sent, and an edit while a worker fills is stopped at the send gate (receiver ledger) | fx (single page) |
| 9 | Recovery without duplicates | fx on the generic form; D143 (branch): on gh2 by id a worker killed before anything was sent is run again once, and one killed after entering data, at the send gate, around the final click or after the employer's receipt is never run again; a run past its budget stops before the final click (gh2 by id and the pilot stand-in; receiver ledger) | partial; D142 merged (#51): on the wizard stand-in a lost or killed worker leaves the record of each page's Next, is never taken over, and the application is never run again (receiver ledger); D143 (branch): the same kills on the single-page form and on the wizard's review page, and a wizard past its budget stops for good (receiver ledger) |
| 10 | Sensitive answers | partial; D131 merged (#36); vaccinations and work documents in #39; D133 merged (#41): a screening job counted by the receiver (by id and pilot stand-in), self-identification across the whole question-safety table and corpus; D139 merged (#48): self-identification on gh2 (by id and pilot) up to the ledger: off or unmatched never sent, a label or a decline label sent, your per-application "Don't disclose" beats it, a required one without a match waits; a change retires its approvals at once (queued, held by a worker, under the standing rule: nothing withdrawn is sent) | partial (never inferred only); no recorded Workday source for "I do not wish to self-identify"; D139 merged (#48): self-identification sent as each option's own value, each question only from the label naming its category, a bare "No" or two labels never used, a decline only where the choices name a category, a required gender without a match waits; withdrawal and change retire the approval (single page; the Workday decline wording is a fixture assumption) |
| 11 | Upload failure preserves evidence | fx for UploadFailed; D137 merged (#46): every disclosure is recorded as it is made (receiver ledger): an unexpected error after an upload keeps its evidence (generic form, gh2 by id, the API route); a killed worker after an upload (generic form); a failure during an upload counts the document as possibly received (generic form, gh2 by id, the first Greenhouse-style page, the API route); a draft or document the API received and answered badly is recorded | fx; D137: a failure during an upload counts it as possibly received (Workday-style page); D142 merged (#51): each page's Next is recorded as disclosure evidence as it is made (wizard stand-in) |
| 12 | Uncertain send quarantined | fx; D143 (branch): at the task's time limit the worker process is ended and the sweeper calls the outcome unknown (a real worker, generic form); the send lease covers the page's own wait for its answer; a code typed late in its wait is still answered under a lease (generic form); on gh2 by id a worker killed around the final click is quarantined (receiver ledger) | fx; D142 merged (#51): on the wizard stand-in, a Next after which the page shows a confirmation or "already applied" is quarantined in `submitted_unconfirmed`, as is an unknown final click; never run again (receiver ledger); D143 (branch): a worker killed around the final click on the single-page form, or before it on the wizard's review page, is quarantined and never run again (receiver ledger) |
| 13 | Cancellation respected | fx on the generic form; D134 merged (#43), on the gh2 stand-in through the pilot (receiver ledger): a pause stops what the standing rule queued, your own queued work runs on, a revocation stands; D143 (branch): a cancel after data was entered says what may have been entered, and a worker whose attempt was cancelled stops between fields (generic form) | partial; D142 merged (#51): a revocation or a profile edit between wizard pages stops at the next page's gate; a cancel there is refused (`wizard_in_progress`), so a Next that submits is still quarantined (receiver ledger) |
| 14 | Tenant isolation | fx (per-application routes) | D142 merged (#51): fx on the wizard stand-in: another account on the same posting is not refused and reaches nothing of the first (404) |
| loop | Durable pause → answer → recheck → continue | fx, on `main` since D132 (#40): pause, read again, answer, one new run (receiver ledger) | fx (e2e), on `main` since D132 |
| tab | "Questions needing your answer" | on `main` since D132 (#40) (`/questions`) | on `main` since D132 |

The full matrix, with test names and file references, was produced on 2026-11-06 by the read-only
acceptance inventory. Ranked slices are in `docs/remaining-work.md`.

## Done in this loop

- **Integration:** #35 (D120), #38 (the exposure-evidence note) and #36 (D131) merged in that order.
  Each tree matched its prediction, and main CI #246 passed all four jobs.
- **D131 (PR #36, merged).** Self-identification answers only EEO categories, and only with options
  that name their own category.
  - Reproduced before the fix: with "No" among the labels, a felony question and an accommodation
    question were answered "No".
  - A follow-up's saved answer is now keyed with its trigger.
  - "Do you meet all minimum qualifications?" is no longer reused.
  - The review page no longer fails on a self-identified answer.
- **D131 follow-up (PR #39).** The review's remaining findings, each reproduced by a probe first:
  - job requirements in more wordings are never reused, and your own skills stay reusable;
  - the documents that let you work are legal-status wording;
  - vaccinations in any wording are sensitive;
  - self-identification labels are one per line, so the standard disability "No, …" stays whole.
- **D132 (PR #40, merged).** A form that no longer matches pauses the application instead of
  dead-ending; "Questions needing your answer"; read the form again; "Try this version again".
  - Three design critiques changed the first build. Only a new question pauses; changes only the
    live page shows stay plain stops; a change found after filling never pauses.
- **D133 (PR #41, merged).** Rank 2, reuse and suggestion guards:
  - a saved answer is suggested only when the question it was given to is still reused (never a
    fact, one employer's question, a sensitive topic or a follow-up's answer), and never when it
    would not fit the field;
  - vetoes read label and help text; a word on one side only vetoes by family (negation, unit,
    language, name, product); the rule score reads the wording only and is a floor under the model;
  - "Use here only" saves nothing; verdicts refuse unknown fields;
  - "I don't wish to self-identify" is a decline; a screening job on the gh2 stand-in shows
    self-identification never answering felony or sponsorship (receiver ledger);
  - an error boundary keeps the app around a page that fails while it is shown.
- **D134 (PR #43, merged).** Rank 3, the standing rule respects the
  owner's pause and revocation for work it already queued:
  - the rule's approvals and attempts are marked as its own (`by_rule`, `queued_by_rule`);
  - pausing cancels the attempts the rule queued (one a worker holds stops at its next step),
    leaves one past the send gate alone and counts it, and retires the rule's approvals; what you
    queued yourself and approvals you gave are never touched;
  - a worker refuses an attempt the rule queued while the rule is switched off or paused;
  - a pause and the rule's step for one job are serialized per account, so a pause during a tick
    reaches that tick's remaining jobs;
  - after you revoke, the rule never approves that application again.
- **D135 (PR #44, merged).** Rank 4, first half, on Greenhouse's id-only structure:
  - a typed question the page hides until an earlier answer reveals it is answerable (your answer
    or a profile fact, never a saved answer or a draft), and entered only if the page shows it;
  - a revealed question the page requires with no approved answer pauses the application after
    filling, with nothing submitted (`conditional_required`); answered and tried again, one new
    attempt sends it.
- **D136 (PR #45, merged).** Rank 5, first half: on Greenhouse's id-only
  structure a control the adapter cannot fill is refused when the form is read, never after you
  approve. One list of what the adapter fills serves both steps. A required native dropdown,
  checkbox or list of several choices is a checkpoint (apply on the employer's site); an optional
  one is left blank and the rest is sent. Before, a native dropdown stopped every attempt as a form
  change ("widget"), and reading the form again read it the same way; the others were refused only
  after approval.
- **D137 (PR #46, merged).** Rank 5, second half: each disclosure is
  recorded the moment it is made, fenced by generation, not after filling ends. An unexpected
  error or a killed worker after an upload no longer loses the evidence that the résumé reached
  the employer; a failure during an upload counts the document as possibly received; through the
  API, a document sent without an answer is recorded too. Attempts that disclosed anything are
  still abandoned and never retried.
- **D138 (PR #47, merged).** Rank 6, tests and fixtures only: a saved answer
  reaches the next Greenhouse-style job that asks the same question, and the employer receives it;
  a look-alike naming a country is neither reused nor suggested; on the Workday-style form the
  education answer is reused and the shift never is; editing a saved answer retires the approval
  that used it until it is approved again.
- **D139 (merged, #48).** Rank 7: your self-identification on
  Greenhouse- and Workday-shaped forms up to the employer (opt-in, decline, scope, your
  per-application choice, a required question without a match), and turning it off or changing it
  now retires the approvals of what it answered at once (before, only a worker's gate kept a
  withdrawn answer from being sent, and you were not told); the profile page says how many
  applications need your approval again.
- **D140 (merged, #49).** Rank 8, first half: the education and work
  history a package sends are shown on the review page as frozen in it, and diffed by record and
  field; an education or employment edit retires the approvals it affects at once and names the
  section in the reason (receiver ledger on the education stand-in).
- **D141 (merged, #50).** Rank 8, second half: an employment stand-in,
  and section comboboxes filled as D108/D109 fill a dropdown (never typed into, their own list
  only, the frozen id, a react-select choice read from its single value); every section control
  is read back before the send gate; `EXTRACTION_VERSION` v6 retires greenhouse_dom and
  greenhouse_live approvals once. Its review's three findings fixed (a stale v5 pin, two checks
  without a test, an overclaim), and a combobox's list is read once open, as real react-select
  names it.
- **D142 (merged, #51).** Rank 9: a Workday-style multi-page wizard
  stand-in, filled forward only. A gate commits `step_authorized` before each page is filled and
  before each Next; each page is read back, unanswered fields included, before its Next; a Next is
  clicked once and its answer recorded. Anything unexpected after disclosure ends the attempt for
  good (a Next that may have submitted is quarantined in `submitted_unconfirmed`), and approve,
  queue, enqueue and claim refuse that application from then on (`wizard_draft_at_employer`).
  Rehearsals and the standing rule are refused on a wizard; per-page pauses are not built
  (continuing needs the owner). Adapter version `fixture-workday-2`. Its adversarial review upheld
  8 minor findings, all fixed: a cancel mid-wizard is refused (revoke stops it), a stopped wizard
  stays where it stopped, and six guards gained a test that fails without them.
- **D143 (branch `recovery-hardening`, not merged).** Rank 10, recovery hardening:
  - the runner bounds its own run: a budget (420 s to reach the final click) it checks between
    steps; past it the run stops as its phase says and the final click is never made;
  - an attempt's task has one time limit (1380 s: the budget, the waits after the click and the
    whole wait for a code) and no soft limit. A run with a real worker showed that a soft limit
    landing inside a browser wait is never handled: the browser cannot close, the handler never
    runs, and the process hangs until the hard limit. At the limit the process is ended and the
    sweeper decides; every other task keeps 240/300;
  - a lease follows progress (evidence, and a hook between fields) and covers each wait for the
    employer's answer, also for a code typed late in its wait;
  - a verification request ends with its attempt: closed and its code erased at any outcome,
    refused once its attempt no longer waits, and swept when stale;
  - a cancel after entry and a stopped wizard say what happened ("sent there with Next", "never
    made the final submit", an unanswered Next "does not know whether that page was saved");
  - a worker killed at each point on the gh2 and Workday-style stand-ins is never run again
    once data was entered; the browser runner's session limit is 1500 s;
  - its independent review found no path to a second submission, to a retry after disclosure
    or sending, or to a wrong outcome, and seven things to change, all fixed: the egress
    proxy's session (900 s) ended inside the longer code wait (now 1500 s); a cancelled attempt
    could still hand over a document (the runner now checks before each document and each
    Next, and the cancel text says what is guaranteed); the Greenhouse watch could outlast the
    figure its lease was sized to (the clock ends it now); the mailbox filler took its locks
    against the order outcomes use since this slice; a code accepted in the last moment of its
    wait was erased unused; two test timings; a missing test that the budget never fires
    after the send gate.
- **Rank 4, second half, needs the owner's decision.** A final click the page's own checks block
  (`CLIENT_BLOCKED`, nothing sent: the request was intercepted) is found after `sending` began.
  Pausing there and later queuing one new attempt is a retry after `sending`, which CLAUDE.md
  forbids ("never add a retry after `disclosure_started_at` or `sending`"). Today it ends
  `failed_terminal` (apply on the employer's site). Not built.
- **Research** (log below):
  - corrected the Workday terms note: the End User Agreement covers scoutrfp.com;
  - Workday saves a draft on every Next;
  - Greenhouse's invisible reCAPTCHA can require an emailed code.

## Hypothesis and next slice

The loop itself (**D132**, #40), the reuse and suggestion guards (**D133**, #41), the standing
rule's respect for the owner's pause and revocation (**D134**, #43), questions the page reveals
after an earlier answer (**D135**, #44) and, when the form is read, the refusal of every control the
adapter cannot fill (**D136**, rank 5's first half, #45) are on `main`. Two remainders need the
owner's decision: the rule continuing after a form-change pause (rank 3), and a final click the
page's own checks block (rank 4, second half: a retry after `sending`). **D137** (rank 5, second
half, #46) keeps the evidence of what reached the employer whatever fails after it.
**D138** (rank 6, #47) shows saved answers on Greenhouse- and Workday-shaped forms up to
the employer. **D139** (rank 7, #48) shows your self-identification there too, and a
change to it retires its approvals at once. **D140** (rank 8, first half, #49) makes
education and work history reviewable and diffed, and **D141** (rank 8, second half, #50) adds an
employment stand-in and react-select-safe section comboboxes. **D142** (rank 9, #51) fills
the Workday-style multi-page wizard stand-in forward only, a gate before every
step, and never runs an application entered there again. **D143** (rank 10, on its branch)
hardens recovery: a run budget the runner checks itself, one task time limit and no soft limit,
leases that follow progress, and verification requests that end with their attempt. Next,
rank 11: attempts on a queue and worker of their own, so two attempts waiting for codes never
hold up the sweeper, the outbox relay and the mailbox reader.

## Unvalidated or partly validated changes

- **D131:** merged; its CI passed on the combined tree.
- **D131 follow-up (#39):** focused suites passed locally (2596 tests) and e2e passed (6 tests). The
  full suites run in its CI.
- **D132:** merged (#40); PR CI passed all four jobs on 564b4f1 and main CI #260 on c19c683. An
  earlier PR run (6b01b2e) errored once in a fixture: the receiver's reset outlasted its 5-second
  wait on a busy runner disk. Not D132's; fixed in its own PR (#42, merged).
- **D133:** merged (#41, da7ac61); its PR CI passed all four jobs on 360f34c (the head with the
  review fixes). Locally: focused suites (2543 passed), the 31 fixture suites (898 passed), the e2e
  that touch it (56 passed) and each sabotage run; with `main` (D132) merged in, 1300 backend and
  51 e2e passed; after the adversarial review's fixes, 2581 passed, each fix's test failing without
  it.
- **D134:** merged (#43, 2e10418); its PR CI passed all four jobs on 118b4b9. Locally: the 17
  suites the change touches, each of its seven changes removed in turn, frontend lint and types;
  with `main` (D133) merged in, the same suites with `test_greenhouse_dom.py`, the resumed held
  attempt, and the Tracker's card in one e2e spec (desktop and mobile).
- **D135:** merged (#44, 53b28af); its PR CI passed all four jobs on 2d3c07c, and main CI #269 on
  53b28af.
- **D136:** merged (#45, 32c8f7c, tree as predicted); its PR CI passed all four jobs on 9602bda.
  Locally: the new tests, their sabotage runs and every suite that touches the second
  Greenhouse-style fixture or reads a Greenhouse form (Tests run below).
- **D137:** merged (#46, e2fd286, tree as predicted); its PR CI passed all four jobs on a9b6880
  (CI #276), and on 929f94b, its last code commit (CI #275). Locally: the new tests, their sabotage
  runs and every suite that runs an attempt or uses an adapter (Tests run below).
- **D138:** merged (#47, a7f8742, tree as predicted); its PR CI passed all four jobs on ea11c6e.
  Locally: the new tests, their sabotage runs and the suites that use the fixtures it extends
  (Tests run below).
- **D139:** merged (#48, 4585c59, tree as predicted); its PR CI passed all four jobs on 3df9d9d.
  Locally: the new tests, their sabotage runs, the e2e spec and the suites that touch
  self-identification, the profile, packages and approvals or the two fixtures (Tests run below).
- **D140:** merged (#49, 3df7d0d, tree as predicted); its PR CI passed all four jobs on 48fde99.
  Locally: the new tests, their sabotage runs, the e2e spec and the suites that touch sections,
  profiles, packages, approvals and diffs (Tests run below).
- **D141:** merged (#50, 98fe380, tree as predicted); its PR CI passed all four jobs on 2ead6ff.
  Locally: the new tests, their sabotage runs and the suites that touch sections, the stand-in
  and the extraction version (Tests run below).
- **D142:** merged (#51, 25d04ea, tree as predicted); its PR CI passed all four jobs on
  85e0213. Locally: the new tests, their sabotage runs and the regression set the build plan
  names (29 files before the review, 27 after it) (Tests run below).
- **D143 (branch `recovery-hardening`):** the new tests, their sabotage runs, a real Celery
  worker run to its time limit and the regression set before the review's fixes, locally
  (Tests run below); the regression set on the fixed code was still running when this was
  committed. The full suites run in its CI. `scripts/validate.sh all` was not run. Not tested:
  the clock's bound on the code step's button wait, a worker process killed on
  `greenhouse_live`, and the runner passing the Greenhouse code-step figure to the lease (the
  figure and the passing are each tested, on different adapters).

## Tests run (this loop)

| Command | Result |
|---|---|
| New D131 tests on a detached `main` worktree | 14 failed (bug reproduced); e2e showed "Application error" |
| D131 focused backend suites (disposable database, JUnit) | 1926 passed, 0 failures |
| `ruff check`, `ruff format --check`, `tsc --noEmit`, `npm run lint` | all clean |
| `playwright test self-identification.spec.ts review-reasons.spec.ts` | 4 passed |
| D131 follow-up: probe of each finding on 65ca027, before the fix | every finding reproduced |
| D131 follow-up focused backend suites (27 files, disposable database, JUnit) | 2596 passed, 0 failures |
| `playwright test self-identification.spec.ts profile-edit.spec.ts` (follow-up) | 6 passed |
| `pytest tests/test_form_change_loop.py` (D132) | 16 passed |
| D133 focused backend suites (14 files, disposable database, JUnit) | 2543 passed, 0 failures |
| D133: the 31 test files that use the second Greenhouse-style fixture | 898 passed |
| D133 sabotage runs (each change removed in turn) | every new test fails without its change |
| D133 e2e (12 specs, desktop and mobile, JUnit) | 56 passed, 0 failures |
| D133 with `main` (D132) merged in: the suites both touch (11 files) | 1300 passed, 0 failures |
| D133 with `main` merged in: 8 e2e specs, desktop and mobile | 51 passed, 1 skipped by design |
| D133 review fixes: the 14 focused files plus the rules, vocabulary and ledger tests (JUnit) | 2581 passed, 0 failures |
| D133 review fixes: each changed file restored to 1b5cc0b in turn | features 39, service 1, resolver 3, classify 1 tests fail |
| D134: `pytest tests/test_auto_apply.py` (disposable database) | 18 passed (8 new) |
| D134: the 17 suites the change touches (JUnit) | 304 tests: 303 passed, 1 failed (the pause's audit row hid its keys), fixed; then `test_audit_inventory.py` and `test_auto_apply.py`: 20 passed |
| D134 sabotage runs (each of seven changes removed in turn) | each fails its tests |
| D134: `npm run lint`, `npx tsc --noEmit`, `ruff check`, `ruff format` | all clean |
| D134 with `main` (D133) merged in: the 17 suites plus `test_greenhouse_dom.py` (JUnit) | 363 passed, 0 failures |
| D134: a held attempt stopped by a pause, then resumed (`test_auto_apply.py`, JUnit) | 18 passed; the resume fails without its change |
| D134: `playwright test e2e/auto-apply-pause.spec.ts` (desktop and mobile, JUnit) | 2 passed |
| D135: `pytest tests/test_conditional_questions.py` (JUnit) | 9 passed |
| D135: every suite that loads the second Greenhouse-style fixture, with the pause, resolution, migration, export and audit suites (47 files, JUnit) | 1079 tests: 1078 passed, 1 failed (an existing test of the old wording for the hidden question, updated); then 22 passed |
| D135 sabotage runs (each of eight changes removed in turn) | each fails its tests |
| D135: `playwright test` conditional-pause, questions, journey and the gh2 submission (desktop and mobile, JUnit) | 10 passed |
| D136: `pytest tests/test_capture_refusals.py` (JUnit) | 6 passed (5 before the optional dropdown's test was added) |
| D136: every suite that loads the second Greenhouse-style fixture or reads a Greenhouse form (48 files, JUnit) | 1373 passed, 0 failures |
| D136 sabotage runs (each of three changes removed in turn) | each fails its tests: 5, 4 and 1 of 6 |
| D136 at its commit, after formatting: the new tests and `test_greenhouse_dom.py` (JUnit) | 65 passed |
| D137: `pytest tests/test_disclosure_evidence.py` (JUnit) | 7 passed |
| D137 sabotage runs (each of four changes removed in turn) | each fails its tests: 4, 1, 1 and 1 of 7 |
| D137: every suite that runs an attempt or uses an adapter, with the Celery and broker-failure suites (63 files, JUnit) | 1500 passed, 0 failures |
| D137 at its commit: the new tests, upload evidence, sections end to end and rehearsal (JUnit) | 31 passed |
| D137 after both review rounds: `pytest tests/test_disclosure_evidence.py` (JUnit) | 24 passed |
| D137 review-fix sabotage runs (each of eight changes removed in turn) | each fails its tests: 2, 1, 1, 1, 1, 1 and 1 of 15; 2 of 24 |
| D137 after both review rounds: the same 63 files (JUnit) | 1508 passed, 0 failures |
| D137 at 929f94b: the new tests, upload evidence, the API route, sections end to end and rehearsal (JUnit) | 64 passed |
| D138: `pytest tests/test_provider_reuse.py` (JUnit) | 4 passed (before and after the review's fixes) |
| D138 sabotage runs at bfba231 (seven changes, each in turn) | reuse off: 3 of 4 fail; scope off: 1; the shift's three rules removed: 1; a 36-character key: 1; any one shift rule alone: 0 (the other two refuse it) |
| D138 before the review: the bank, Greenhouse DOM and live, Workday, answer-brain, API-provider and bank-edit suites (8 files, JUnit) | 1325 passed, 0 failures |
| D138 at bfba231: every suite that loads the gh2 or Workday-style fixture, with the bank and document suites (44 files, JUnit) | 2210 passed, 0 failures |
| D139: `pytest tests/test_self_identification_ledger.py` (JUnit) | 25 passed; then the review's added test, 1 passed |
| D139: the new standing-rule and mutation-table cases, then `test_auto_apply.py`, `test_execution_validation.py`, `test_self_identification.py`, `test_greenhouse_dom.py`, `test_workday_adapter.py` in full (JUnit) | 3 passed; then 154 passed |
| D139 sabotage runs (five changes, each in turn) | the eager retirement removed: 9 fail; the gate's hash check removed: 2; self-identification over "Don't disclose": 3; the Workday decline wording removed: 2; the "names a category" rule removed: 1 |
| D139: `playwright test e2e/self-identification.spec.ts` (desktop and mobile) | 6 passed; with the eager retirement removed, the new test fails on both (2 failed, 4 passed) |
| D139: every suite that touches self-identification, the profile, packages and approvals, or either fixture (70 files, JUnit) | 2637 passed, 0 failures |
| D140: `pytest tests/test_sections_review.py tests/test_greenhouse_sections_package.py tests/test_version_diff.py` (JUnit) | 18 passed; then `test_sections_review.py` with the notice check, 7 passed |
| D140: `pytest tests/test_greenhouse_sections_e2e.py` (JUnit) | 9 passed |
| D140: `pytest tests/test_package_contract.py` with the section packages (JUnit) | 3 passed |
| D140 sabotage runs (four changes, each in turn) | the eager retirement removed: 2 fail; the section diff removed: 3; the section summary removed: 1; the gate's hash check removed: 1 |
| D140: `playwright test e2e/sections-review.spec.ts` (desktop and mobile) | 2 passed; after the review, 2 passed |
| D140 after the review: `pytest tests/test_sections_review.py tests/test_version_diff.py` (JUnit); then six sabotage runs (each route's hook alone, the account scope, the "needs you" status) | 20 passed; each fails its test (1, 2, 1, 1, 1; 1; 2) |
| D140: every suite that touches sections, profiles, packages, approvals or diffs (55 files, JUnit), on edb22b8 | 3252 passed, 0 failures |
| D141: the existing section suites on the new stand-in, then with the new filler (JUnit) | 72 passed; 72 passed |
| D141: `pytest tests/test_section_widgets.py` (JUnit) | 8 passed |
| D141: the new tests with the section, approval-binding and phone-companion suites at v6 (JUnit) | 118 passed |
| D141 sabotage runs (three changes, each in turn) | the old typing filler restored: 3 fail; the section readback removed: 1; both id checks removed: 1 |
| D141: every suite that loads the second Greenhouse-style fixture or binds an approval to an adapter version (66 files, JUnit), on 4cf9efc | 1533 passed, 1 failed: `test_greenhouse_controls.py` still pinned the extraction at v5 (the review's blocker, fixed in 0a7875b; that file passes in the 274 below) |
| D141 after the review: `pytest tests/test_section_widgets.py` (JUnit); then three sabotage runs (the list read before opening, the id check before the click, the check beyond the plan) | 10 passed; each fails its own test (1, 1, 1) |
| D141 after the review: the section suites, the version pins (`test_approval_binding`, `test_greenhouse_controls`, `test_phone_companion`) and `test_form_change_loop` (10 files, JUnit), on 0a7875b | 274 passed, 0 failures |
| D142: non-wizard fingerprints computed on 2dfc956 before any edit (the default Workday-style page, the generic form, `wd_self_identify`, `wd_multi_step`) | four values, unchanged after the build; the first two pinned in `test_non_wizard_fingerprints_are_unchanged` |
| D142: `pytest tests/test_workday_wizard.py -x -k "capture or malformed or fingerprints or each_page_is_sent"` (JUnit), on c649dd4 with the build uncommitted | 4 passed, 1 failed (a test's mutation matched twice in the page); fixed: 9 passed |
| D142: `pytest tests/test_workday_wizard.py` (JUnit) | 29 passed, 2 failed (two test bugs: the batch body lacked its scope; the other account's own capture was counted as the first account's request); fixed: 2 passed |
| D142: `pytest tests/test_package_contract.py tests/test_provider_contracts.py tests/test_provider_admission.py tests/test_workday_adapter.py` (JUnit) | 232 passed |
| D142 sabotage runs on fb26ad9 (42 changes, each in turn, each with its row's test) | 39 fail their test; 3 did not: the page-count rule and the page-order rule dropped (6 passed each), `require_valid_approval`'s check dropped (1 passed) |
| D142: the tests strengthened (two capture cases, `require_valid_approval` called directly), `pytest tests/test_workday_wizard.py -k "malformed or once_entered or another_account"` (JUnit) | 10 passed |
| D142 sabotage runs again on 655cce3 (the three missed, and three whose test changed) | each fails its test (1 of 8, 1 of 8, 1, 1, 1, 1) |
| D142: the regression set (the 28 files the build plan names, with `test_doc_references.py`; JUnit), on 655cce3 with the two doc cells `test_lever.py` and `test_approval_reasons.py` read (committed as 3bc2179) | exit 0; 659 passed, 0 failures (21 min) |
| D142 after the last edit: `ruff format .` (2 files), `ruff check .`, `ruff format --check .`; then `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py tests/test_provider_contracts.py tests/test_workday_wizard.py` (JUnit) | ruff clean, 374 files formatted; 254 passed, 0 failures |
| D142: the same document tests after the last row was written (`test_doc_references`, `test_approval_reasons`, `test_lever`, `test_audit_inventory`; JUnit) | exit 0; 24 passed |
| D142 after the review: `pytest tests/test_workday_wizard.py` (JUnit), with the review fixes uncommitted | 42 passed, 1 failed (test 13 expected the queue check's 409, but the application now stays `needs_user_action` and the state machine refuses first, 400); fixed: 1 passed |
| D142 sabotage runs on 98736d1 (15 changes, each in turn): the six never-again checks again (their test changed), then the nine checks the review added or found untested | each fails its test: the six (1 each); the cancel refusal (2), the settle guard (2), the review list's exclusion (2), the fingerprint's wizard part deleted (2), rule 6's last-page half (1), the next-page check (1), the manual form's refusal (1), the `wizard_adapter` refusal (1), the wizard markers on a single-page package (1) |
| D142 after the review: the regression set again with `test_sections_review.py` and `test_version_diff.py`, without the tests that read documents (27 files, JUnit), on 98736d1 | exit 0; 513 passed, 0 failures (26 min) |
| D142 after the review's documents: `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py` (JUnit) | ruff clean (374 files unchanged); exit 0; 178 passed, 0 failures |
| D143: the nine existing execution suites on the first build (JUnit) | exit 0; 185 passed |
| D143: a probe outside the application: a signal raising during Playwright's synchronous waits | during `time.sleep` handled and the browser closed; during each browser wait the script had not finished after 60 s; with a stack dump, the exception surfaced in the caller and `browser.close()` never returned |
| D143, first build: a real Celery prefork worker, soft limit 6 s and hard 66 s, the receiver answering the final click after 45 s (a temporary test, not committed) | soft limit logged at 13:58:23, no outcome written, killed at the hard limit at 13:59:23; the attempt still `sending` |
| D143 after the redesign: `pytest tests/test_recovery_hardening.py` (JUnit) | 38 passed, 3 failed (equal soft and hard limits still fired the soft one: fixed by removing it; two test bugs); the four fixed or changed rows: 8 passed |
| D143: the new tests with the nine suites and `test_celery_execution` (11 files, JUnit), before the unreachable soft-limit handling was dropped | exit 0; 230 passed |
| D143 sabotage runs on a83b0ce (31 changes, each in turn) | 30 fail their test; 1 did not (a send lease under the submit timeout: bounds too loose for the tests' 4-second timeout) |
| D143: the send-lease test made exact (c307576), then the three lease changes again | each fails its test |
| D143: the 64 test files that run an attempt or touch what changed (every adapter suite, the execution, recovery, rehearsal, evidence, inbox, notification, deployment-configuration and container-runner suites, the Celery and broker-failure suites, `test_doc_references`, `test_audit_inventory`; JUnit), on a83b0ce | exit 0; 1539 passed, 0 failures (54 min) |
| D143 on the merged head 3930850: `pytest tests/test_recovery_hardening.py tests/test_workday_wizard.py tests/test_code_wait_quarantine.py` (JUnit) | exit 0; 87 passed |
| D143: a cancel while a form is filled, a test added after the runs above (`pytest tests/test_recovery_hardening.py -k cancel_`, JUnit) | exit 0; 3 passed |
| D143 before the review: `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents | ruff clean (375 files unchanged); 177 passed, 1 failed (the evidence matrix still cited a test removed with the soft-limit handling; its row removed); then exit 0, 178 passed |
| D143: three earlier changes run again once the cancel-while-filling test existed (no progress hook, each cancel text), on 9c92e54 | each fails its test |
| D143 review fixes: `pytest tests/test_recovery_hardening.py tests/test_inbox.py -k "outlast or never_stops_a_run or last_moment or hands_over_no_document or watch_ends_by_the_clock or send_lease or sweeper_closes_its_request or while_a_form_is_filled or typed_late"` (JUnit) | exit 0; 9 passed |
| D143 review fixes: the code-wait, quarantine and sweeper tests in `test_recovery_hardening.py`, `test_code_wait_quarantine.py` and `test_execution_security.py` (`-k "last_moment or typed_late or then_ends_is_erased or only_while_its_attempt_waits or code_checkpoint or quarantine or unknown_result or sweeper"`, JUnit) | exit 0; 12 passed |
| D143 review fixes removed in turn on bb94e9f (9 changes), then three earlier changes whose code or test the fixes touched | all 12 fail their test |
| D143: the regression set again on the reviewed code (62 of the 64 files, without the two that read the documents; JUnit), on bb94e9f | started 18:33 UTC, still running when this was committed; result in the pull request, recorded here with the next change |
| D143 after the last edit (the documents and one docstring): `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents, `test_lock_order.py` and `test_inbox.py` (JUnit) | ruff clean (375 files unchanged); exit 0; 270 passed |

## Failed approaches and rejected designs

- **Making every conditional follow-up non-reusable.** Rejected: it would lose correct reuse. The
  follow-up is keyed with its trigger instead.
- **Treating a decline as matching when a bare "No" also matched.** Rejected: an ambiguous match is
  never a decline; it becomes a checkpoint.
- **Reusing the `checkpoints` table for form-change pauses.** Rejected for D132's draft: that table is
  attempt-bound for emailed codes (non-null expiry, a code, rounds) and is scanned by the mailbox code
  filler and code routes.
- **Pausing on every drift, and after filling** (D132's first build). Rejected after review. A
  re-read compares the job data and the page without its scripts, so a page-only change, or the
  page's reaction to entered answers, would always end "unexplained" and block approval. Those
  stay plain stops.
- **A longer soft time limit on the attempt's task, handled by phase** (D143's first build).
  Rejected after a run with a real worker: a soft limit that lands inside a browser wait leaves
  the browser unable to close, so the runner's handler never runs and the process hangs until
  the hard limit. The runner checks a run budget itself between steps instead.
- **Equal soft and hard limits on the attempt's task.** Rejected after a run: Celery's prefork
  pool arms the soft limit first whenever one is set and starts the hard one from it, so the
  soft limit still fired. The default has none now, and every other task sets its own.

## Blockers (external; each blocks one action, not the local work)

- **Recorded permissions end 2026-11-06:** the Greenhouse pilot (read, open, disclose, submit; 5
  shared passes) and mailbox codes (`backend/app/core/authorizations.py`). From then on, every real
  capture, rehearsal, submission and D113 action is refused until the owner records new words.
- **A real Greenhouse posting that today's rules can capture**, chosen by the owner, plus a
  single-use disclose-only permission. The only posting observed so far would be refused at capture.
- **The owner's decision on Greenhouse's invisible reCAPTCHA**, before any first real submission:
  - let the page's own scripts run and stop only on a visible challenge; or
  - keep them blocked and treat each submit as "code expected or outcome unknown".

  Never generate, replay or spoof a token.
- **A read-only observation of a real Greenhouse education/employment section.** D120 stays
  stand-in only until then.
- **Workday:**
  - the owner's terms decision, reframed as the employers' own terms and consents and Workday's
    automation signals;
  - a recorded documentation review;
  - a single-use read-only observation;
  - candidate accounts are the user's own: NoEfforts never creates accounts or handles passwords,
    and a resume needs the user's own sign-in.
- **D113 continuing after a form-change pause.** The owner's recorded words say a stopped attempt
  waits for them; continuing needs their decision.
- **A final click the page's own checks block (`CLIENT_BLOCKED`).** Nothing was sent, but it is
  found after `sending` began; making it a pause that later queues a new attempt is a retry after
  `sending`, which CLAUDE.md forbids. Today: `failed_terminal`, apply on the employer's site. Only
  the owner can decide whether an intercepted, never-sent click may be tried again.

## Exact next action

1. D143 (branch `recovery-hardening`, `main` with D142 merged in): open its pull request,
   merge it when its four checks pass, and record here the result of the regression run on
   its reviewed code.
2. Rank 11: attempts on a queue and worker of their own, so two attempts waiting for codes
   never hold up the sweeper, the outbox relay and the mailbox reader. Then ranks 12 and 13
   (`docs/remaining-work.md`).
3. Owner decisions: on a Workday-style wizard (D142), continuing after a stop, rehearsing then
   submitting, a permission per page or one approval, and whether the standing rule may drive
   one; the standing rule's consent text does not name self-identification, which it
   sends since D133 (D139); every recorded permission ended on 2026-11-06 (renewing is the owner's call,
   never extended because work took longer); continuing after a form change (D132); a final click
   the page's own checks block (`CLIENT_BLOCKED`, after `sending`).

## Research log (accessed 2026-11-06)

| URL | Established | Level | Implication |
|---|---|---|---|
| https://www.workday.com/en-us/legal/end-user-agreement.html | "Website" = scoutrfp.com; clause 4.3(b) on automated access applies to it | official (quoted) | Not a career-site rule; reframe the terms decision |
| https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/career-sites.html | Saved on each Next; drafts kept 2 years, max 200, visible to the candidate only | official (quoted) | Per-step disclosure gates; a pause leaves a draft; resume reopens it |
| https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/hnr1671753523279.html | Apply-flow page order | official (reader) | The multi-page stand-in follows it; question pages come after personal data is sent |
| https://doc.workday.com/admin-guide/en-us/manage-workday/tenant-configuration/tenant-setup/lde1511812666156.html | Per-tenant account requirement, verification email, social sign-in, candidate merging, reapply | official (reader) | Sign-in is the user's checkpoint; "already applied" is possibly submitted, never retried |
| https://doc.workday.com/admin-guide/en-us/manage-workday/business-processes/questionnaires/tso1611016403011.html | Up to 6 branching follow-ups; editing an answered question makes a new version | official (reader) | Re-extract after answers; a version change must change the reuse key |
| https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/job-applications/ijz1499291475964.html | My Experience sections, each hideable or required; school list may be tenant-restricted | official (reader) | Repeating records with per-entry readback; school stays a checkpoint |
| https://support.greenhouse.io/hc/en-us/articles/115005448066-Invisible-reCAPTCHA | reCAPTCHA built into job boards; scores mouse and typing; may require an emailed code before submit | official (quoted) | Owner decision before the first real submit; never evade |
| https://docs.greenhouse.io/job-board.html | `questions`, `location_questions`, `compliance`, `demographic_questions` (always optional), `data_compliance`; no documented conditional logic | official (reader) | Conditionals are page logic: handle at run time (rank 4) |
| https://support.greenhouse.io/hc/en-us/articles/7541739987355-U-S-Standard-demographic-questions | Six fixed questions; several "mark all that apply"; self-describe and decline on each | official (reader) | Multi-select and self-describe handling; self-describe is never a decline |
| https://support.greenhouse.io/hc/en-us/articles/43418495049499-MyGreenhouse-FAQ-for-Candidates | Quick Apply creates or uses a profile; sign-in by email codes; identity verification by some employers | official (reader) | Never click Quick Apply; mailbox codes only for application security codes |
| https://playwright.dev/python/docs/api/class-page#page-get-by-role | Name match is a substring unless `exact=True`; strictness throws on several matches | official (reader) | Use exact names; let ambiguity become a checkpoint |
| https://playwright.dev/python/docs/input | `set_input_files` needs a file input; otherwise use the file chooser | official (reader) | A chooser-based upload bound to the approved digest, fixture first |
| https://playwright.dev/python/docs/aria-snapshots | ARIA snapshots include input values | official (reader) | Never use snapshots or traces as evidence |
| https://coreteamgroup.com/workday-release-2026r1-recruiting/ | Employers can collect an automation score, JA4 fingerprint, IP/ASN and time to apply | third-party summary | Applications may be flagged; no stealth, ever |
| https://github.com/berellevy/job_app_filler | Workday DOM shapes (formField containers, button listboxes, typeaheads); selects through React internals | open-source code (BSD-3; facts only) | Button listboxes and typeaheads stay checkpoints by default |
