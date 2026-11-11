# Greenhouse + Workday automation loop: continuation record

One concise, sanitized record of where the loop stands, so work can resume from it. No personal
answers, credentials, employer-identifying evidence, raw pages or unredacted logs belong here. The
canonical backlog is `docs/remaining-work.md` (its "Automation loop" section); decisions are in
`docs/decisions.md`.

**Updated:** 2026-11-11 (UTC).

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
| `main` | 099642c (tree 33b8b0d, as predicted): #53 D144. Before it, 9346c8e (tree fd09e77): #52 D143; 25d04ea (tree a3054b8): #51 D142; 98fe380 (tree b75d64c): #50 D141; 3df7d0d (tree a625f26): #49 D140; 4585c59 (tree fac890a): #48 D139; a7f8742 (tree af2f25f): #47 D138; e2fd286 (tree 1d69376): #46 D137; 32c8f7c (tree 201ddbd): #45 D136; 53b28af (tree fe5c8c3): #44 D135 (main CI #269 green on all four jobs); 2e10418 (tree 3a18998): #43 D134 (main CI #267 green on all four jobs); da7ac61 (tree d2214b6): #41 D133 (main CI #265 green); ab671e1: #42, the receiver's reset in one transaction (main CI #263: the backend job failed, not investigated; every later run passed); c19c683: #40 D132 (main CI #260 green) |
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
| D143 recovery hardening: a run budget, one task time limit and no soft limit, leases that follow progress, verification requests that end with their attempt | merged (#52, 9346c8e, tree as predicted); its PR CI passed all four jobs on fa36039 |
| D144 attempts on a queue and a worker of their own; the schedule and the periodic tasks on another | merged (#53, 099642c, tree as predicted); its PR CI passed all four jobs on e40ee72, the Compose layout's first run |
| D145 a dropdown's list settled by the page's own record of its last change to a list | merged (#54, 45c8229, tree as predicted); its PR CI passed all four jobs on 9315953 |
| D146 an attempt still waiting to be taken is published again | merged (#55, 688c776, tree as predicted); its PR CI passed all four jobs on e1fb40a |
| D147 a restored database comes up held, and nothing it restored runs | branch `restore-hold` (D146's branch merged in); reviewed twice; not merged |
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
| 6 | Unsupported widget → checkpoint | fx at capture; D136 merged (#45): on the id-only structure every control the adapter cannot fill (a native dropdown, a checkbox, a list of several choices) is refused when the form is read, a required one a checkpoint, an optional one left blank (gh2, receiver ledger); D145 (branch): a dropdown whose list keeps being re-rendered is refused however slowly it is read (the page's own record of its last change to a list), before anything is entered, and a location search whose suggestions keep changing chooses no place (gh2 stand-ins; receiver ledger) | fx at capture |
| 7 | Repeating records | fx education stand-in (D120); D140 merged (#49): the rows sent shown on the review page and diffed by record and field; D141 merged (#50): an employment stand-in (current and past roles, rows in their own sections) and react-select-safe section comboboxes, read back before the send gate (receiver ledger) | absent |
| 8 | Answer edits invalidate approvals | fx; D138 merged (#47): on gh2, editing the saved answer retires the approval that used it; approved again, the new value is sent (receiver ledger); D140 merged (#49): an education or employment edit retires the approval at once; on the education stand-in, approved again, the new degree is sent, and an edit while a worker fills is stopped at the send gate (receiver ledger) | fx (single page) |
| 9 | Recovery without duplicates | fx on the generic form; D143 merged (#52): on gh2 by id a worker killed before anything was sent is run again once, and one killed after entering data, at the send gate, around the final click or after the employer's receipt is never run again; a run past its budget stops before the final click (gh2 by id and the pilot stand-in; receiver ledger); D144 merged (#53): the sweeper runs on a worker of its own, so it is not held up by attempts waiting for codes (real workers, generic form; receiver ledger) | partial; D142 merged (#51): on the wizard stand-in a lost or killed worker leaves the record of each page's Next, is never taken over, and the application is never run again (receiver ledger); D143 merged (#52): the same kills on the single-page form and on the wizard's review page, and a wizard past its budget stops for good (receiver ledger) |
| 10 | Sensitive answers | partial; D131 merged (#36); vaccinations and work documents in #39; D133 merged (#41): a screening job counted by the receiver (by id and pilot stand-in), self-identification across the whole question-safety table and corpus; D139 merged (#48): self-identification on gh2 (by id and pilot) up to the ledger: off or unmatched never sent, a label or a decline label sent, your per-application "Don't disclose" beats it, a required one without a match waits; a change retires its approvals at once (queued, held by a worker, under the standing rule: nothing withdrawn is sent) | partial (never inferred only); no recorded Workday source for "I do not wish to self-identify"; D139 merged (#48): self-identification sent as each option's own value, each question only from the label naming its category, a bare "No" or two labels never used, a decline only where the choices name a category, a required gender without a match waits; withdrawal and change retire the approval (single page; the Workday decline wording is a fixture assumption) |
| 11 | Upload failure preserves evidence | fx for UploadFailed; D137 merged (#46): every disclosure is recorded as it is made (receiver ledger): an unexpected error after an upload keeps its evidence (generic form, gh2 by id, the API route); a killed worker after an upload (generic form); a failure during an upload counts the document as possibly received (generic form, gh2 by id, the first Greenhouse-style page, the API route); a draft or document the API received and answered badly is recorded | fx; D137: a failure during an upload counts it as possibly received (Workday-style page); D142 merged (#51): each page's Next is recorded as disclosure evidence as it is made (wizard stand-in) |
| 12 | Uncertain send quarantined | fx; D143 merged (#52): at the task's time limit the worker process is ended and the sweeper calls the outcome unknown (a real worker, generic form); the send lease covers the page's own wait for its answer; a code typed late in its wait is still answered under a lease (generic form); on gh2 by id a worker killed around the final click is quarantined (receiver ledger) | fx; D142 merged (#51): on the wizard stand-in, a Next after which the page shows a confirmation or "already applied" is quarantined in `submitted_unconfirmed`, as is an unknown final click; never run again (receiver ledger); D143 merged (#52): a worker killed around the final click on the single-page form, or before it on the wizard's review page, is quarantined and never run again (receiver ledger) |
| 13 | Cancellation respected | fx on the generic form; D134 merged (#43), on the gh2 stand-in through the pilot (receiver ledger): a pause stops what the standing rule queued, your own queued work runs on, a revocation stands; D143 merged (#52): a cancel after data was entered says what may have been entered, and a worker whose attempt was cancelled stops between fields (generic form) | partial; D142 merged (#51): a revocation or a profile edit between wizard pages stops at the next page's gate; a cancel there is refused (`wizard_in_progress`), so a Next that submits is still quarantined (receiver ledger) |
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
- **D143 (merged, #52).** Rank 10, recovery hardening:
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
- **D144 (merged, #53).** Rank 11, attempts on a queue and worker of
  their own:
  - measured first: one worker taking every task, both of its processes held by attempts
    waiting for codes, did not take a periodic task until a code was entered (20 s watched;
    taken 0.6 s after the code). Since D143 such a wait may last ten minutes;
  - an attempt's task goes to its own queue (`attempts`), every other task to the default one;
    each queue is declared with its own exchange, so a message reaches one queue only;
  - the Compose stack runs two workers: `worker` (attempts only, one process for the one
    browser slot) and `scheduler` (the schedule and the periodic tasks; no runner token, no
    control socket). A second application waits in the queue instead of failing after 40 s,
    and a stopped worker's attempt is recovered while that worker is still down;
  - a message for an attempt on another queue (one waiting at an upgrade) is passed on once
    and never run there; a worker started without `-Q` still takes both (development, tests);
  - the smoke test asks both workers by name; the deployment guide and the owner's stop
    controls name both;
  - an independent review (read-only, on 4788880) found no blocker. Fixed or recorded from
    it: the mailbox guide mounted the token into `worker`, and the mailbox is now read by
    `scheduler`; queued applications now wait in the broker while the worker is busy or
    stopped, and `docker compose down` discards them (rank 15 is the fix); the cleanup before
    the claim could fail the task and strand its attempt (guarded, tested); a Compose check
    that would fail now and then; and the owner's "stop everything now", which named
    `docker compose stop`: measured, a worker told to stop finishes and submits the
    application in progress, so the table names `docker compose kill` now.
- **D145 (merged, #54).** Rank 14, a dropdown's list settled by the
  page's own record of its last change to a list:
  - found by D143's regression run under load, then reproduced without it: three identical
    reads fall in step with a list re-rendered every 300 ms once the reading interval reaches
    about 600 ms (at 610 ms the list was judged settled every time, and once the application
    was then submitted);
  - a list now also needs the page's own record of the last change to a list (the probe's
    observer) to be half a second old, a fixed time, or absent: one whose changes come faster
    is refused however slowly it is read, before anything is entered; a settled one is still
    accepted when read slowly; changes elsewhere on the page do not count;
  - the location search takes its suggestions as settled by the same record, so "exactly one
    suggestion" is judged on a list the page has not changed for half a second;
  - built twice: first on the whole document's record. An independent review (read-only, on
    15c5e36) found no blocker and showed that a page busy elsewhere would then pass a check
    only now and then, so the record was narrowed. From the same review: a test of its own for
    the three equal reads, one for a list that starts changing after its check, a refusal word
    of its own, a control gone when the observer is installed, and the limits said as they are;
  - a second independent review (read-only, on a080d3d) found no blocker. Acted on: a test for
    the narrower race the new guard closes, and the location search's error before typing no
    longer counts the text as disclosed. Recorded: changes elsewhere still count through the
    classification's 150 ms check (since D106; rank 19), and what the record does not count;
  - the read-only survey keeps its own, weaker test and publishes nothing of the new record
    (rank 18); a section's combobox still reads its list once (rank 17); no adapter version
    changes, and a rehearsal earned under the weaker test still counts (D145).
- **D146 (merged, #55).** Rank 15, an attempt still waiting to be
  taken is published again:
  - three ways an attempt stayed "queued" for good: the broker lost its message (`docker
    compose down`, a crash); a worker process died after receiving the message and before the
    claim (Celery acknowledges it, and the sweeper recovers only claimed attempts: shown with
    a real worker); a task that failed before the claim. D144 made the first more likely;
  - the relay's task now publishes again, every five minutes and without a limit, for an
    attempt still `pending` (no cancel requested, nothing entered), and the claim itself now
    refuses an attempt that entered data;
  - a second message for an attempt whose first was not lost ends at the claim (shown with a
    real worker and a receiver told to accept a repeat: one acceptance);
  - an independent review (read-only, on c3f9c00) found no way for a second message to run an
    attempt twice, and one real hazard: **after a database restore, what the backup shows as
    queued is published again and run, even if it already ran after the backup**. Recorded,
    the deployment guide's restore given a step between starting the app and starting the
    workers, and ranked slice 20 (a restore that holds everything by itself) put next. Its other
    findings fixed or recorded (D146);
  - a second review (read-only, on f3cd566) found no code blocker and that the restore step
    as drafted missed applications shown as running, pointed to the wrong page for Cancel,
    could be pasted past, and wrongly called a rollback to a version before D146 safe: the
    step was rewritten. It also found that revoking an attempt the sweeper put back failed
    (there before D146): fixed, with a test.

- **D147 (branch `restore-hold`, not merged).** Rank 20, a restored database comes up held:
  - the hazard D146's review found: a restored database cannot know what happened after its
    backup, and since D146 an application it shows as queued is published again and run, even
    if it was sent after the backup; one it shows as approved could be queued again, and the
    standing rule could continue an application it had already submitted;
  - the database carries stamps of identity: the oid PostgreSQL gave it and its server's
    cluster identifier (every new cluster gives its first database the same oid, measured). A
    restore brings back another's. While a stamp names another database, the claim refuses
    every attempt, queueing and approving are refused and the standing rule does nothing;
  - the scheduler resolves it by itself before publishing anything: every attempt still active
    ended as an unknown outcome (a rehearsal too: the submission after it may have been sent),
    its application `submitted_unconfirmed` for you to reconcile, every live approval retired,
    every account's standing rule paused, every account told; the rule then leaves to you every
    application that began before the restore. Until then the sweeper does nothing, and
    cancelling and revoking are refused, pausing only pauses: each would have recorded nothing
    sent for what may have been;
  - the guide checks after every restore (`restore-status` must show it held), `--force` for
    what NoEfforts cannot recognize; a rollback to a version before D147 keeps the step by hand;
  - two independent reviews: the first found the guide's case list unsafe and five weaknesses (rework e365797); the second found the stamp table's missing export decision (CI) and that the sweeper, cancelling, revoking and pausing could escape the quarantine (a6c1444).

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
step, and never runs an application entered there again. **D143** (rank 10, #52)
hardens recovery: a run budget the runner checks itself, one task time limit and no soft limit,
leases that follow progress, and verification requests that end with their attempt. **D144**
(rank 11, #53) gives attempts a queue and a worker of their own, so two attempts
waiting for codes never hold up the sweeper, the outbox relay and the mailbox reader.
**D145** (rank 14, #54) settles a dropdown's list by the page's own record of its
last change to a list, and **D146** (rank 15, #55) publishes again an attempt still
waiting to be taken: two defects found on the way. Its review found that a restored database
would then run again what it shows as queued: **D147** (rank 20, on its branch) makes a
restored database come up held and end, without running it, everything it shows as queued
or in progress. Next, ranks 12 and 13 (the Workday-style follow-up question and repeating
records).

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
- **D143:** merged (#52, 9346c8e, tree as predicted); its PR CI passed all four jobs on
  fa36039. Locally: the new tests, their sabotage runs, a real Celery
  worker run to its time limit and the regression set before the review's fixes, locally
  (Tests run below); the regression set on the fixed code ended after its last commit: 1541
  passed, 1 failed, a dropdown case in a suite it does not touch (rank 14). `scripts/validate.sh
  all` was not run. Not tested:
  the clock's bound on the code step's button wait, a worker process killed on
  `greenhouse_live`, and the runner passing the Greenhouse code-step figure to the lease (the
  figure and the passing are each tested, on different adapters).
- **D144:** merged (#53, 099642c, tree as predicted); its PR CI passed all four jobs on
  e40ee72. Locally: the new tests with real workers, their removal runs and
  the suites that start workers (Tests run below). The Compose layout (two workers,
  the smoke test's ping, the new and the tightened scenario) cannot be started here: there is
  no Docker daemon, so the `docker-smoke` and `execution-compose` jobs of its pull request were
  its first run, and both passed. `scripts/validate.sh all` was not run. Not tested: a stop request in
  Docker itself (the worker's reaction to the signal was measured without Docker; the ten
  seconds are Docker's default); the pass-on's own publish failing; a rollback across versions.
- **D145:** merged (#54, 45c8229, tree as predicted); its PR CI passed all four jobs on
  9315953. Locally: the new cases, both files, 18 removal runs and the regression set
  (Tests run below). `scripts/validate.sh all` was not run.
  Not tested: a list whose changes come half a second or more apart, a page whose own timers
  stall, a list that changes while its record stays empty (a style sheet's change, options
  through a shadow root), a page busy elsewhere every 250 to 300 ms in a real page's window
  (the classification's 150 ms check, rank 19), a change between the location search's last
  read and its click, the observer's cost on a large page, what a real react-select list does
  while it is open, and anything on a real page.

- **D146:** merged (#55, 688c776, tree as predicted); its PR CI passed all four jobs on
  e1fb40a. Locally: the new tests (three with a real worker and broker),
  the removal runs and the regression set, locally (Tests run below). `scripts/validate.sh
  all` was not run. Not tested: the Compose stack (none of its files change; no scenario loses
  a message there), a restore (ranked slice 20), the pass-on's own publish failing (the same rule
  would publish that attempt again; only the rule is tested), and a broker that hangs instead
  of refusing.

- **D147 (branch `restore-hold`):** the new tests (one with a real worker and broker, one with
  a real copy of a migrated database), the removal runs and the regression set, locally (Tests
  run below). The real dump and restore, and the guide's check, run only in CI
  (`scripts/docker-smoke.sh`). Not tested: a restore NoEfforts cannot recognize (by design:
  the guide's check and `--force`), a PostgreSQL major upgrade or a move to another server
  (treated as a restore), the web app's display of the new feed item (its label only), a
  rollback across versions, two schedulers resolving at once on separate hosts (one advisory
  lock; tested with two connections), and anything real.

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
| D143: the regression set on the reviewed code, finished after that commit (62 files, JUnit), on bb94e9f | exit 1; 1541 passed, 1 failed in 57 min: `test_dropdown_strategies.py`, the `late_slow_changing` case, refused for the wrong reason ("its options differ": the list had been judged settled), while two other test runs shared the machine |
| D143: that failure's cause, without load (a temporary test, not committed): the same case with the adapter's reading interval set | 250 ms: refused as still changing; 590 ms: the same wrong reason; 610 ms: accepted and submitted (the approved option, read back); 600 and 900 ms: refused as still changing |
| D143: the dropdown suite alone on the pull request's head (fa36039, JUnit) | exit 0; 43 passed |
| D143's pull request (#52): CI on fa36039 | all four jobs passed (`docker-smoke`, `execution-compose`, `frontend`, `backend` in 78 min); merged as 9346c8e, tree fd09e77 as predicted |
| D144: the Compose files after the split (`pytest tests/test_deployment_config.py`, JUnit) | exit 0; 17 passed |
| D144: the smoke check on Celery's real reply (`-k smoke_check`, two real workers); `scripts/test_smoke_lib.sh` | exit 0, 1 passed; the script's 12 cases as expected |
| D144: `pytest tests/test_attempt_queue.py` (JUnit), first full runs | 6 passed, 4 errors (the module's own fixture had the name of the suite's database cleanup and replaced it; renamed); 9 passed, 1 failed (an assertion that counted the test's own reading of the form); then exit 0, 10 passed |
| D144: the baseline (a temporary test, not committed): one worker taking both queues, both processes held in the code wait, a sweep published | not received in 20 s; received 0.6 s after the first code was entered |
| D144: the suites that start real workers or read the Compose files (5 files, JUnit) | exit 0; 38 passed |
| D144: `pytest tests/test_recovery_hardening.py` (JUnit) | exit 0; 43 passed |
| D144 removal runs on 7f53f71 (26 changes, each in turn) | all 26 fail their test |
| D144: a probe outside the application, one process per case: two queues declared by name only, then each with its own exchange; a routed publish, a default one, one to exchange `celery` and key `celery` by name | by name only: 1 and 1, then 2 and 2; own exchange: 1 and 1, then 2 and 1 |
| D144: the bindings test added; the by-name declaration against it | 3 passed; changed: 2 of the 3 fail |
| D144 after the last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; `scripts/test_smoke_lib.sh`; the tests that read the documents, `test_deployment_config.py` and `test_attempt_queue.py` (JUnit) | ruff clean (376 files unchanged); the script's 12 cases as expected; exit 0; 206 passed |
| D144, independent review (read-only, on 4788880; nothing run) | no blocker; seven findings, each checked against the code, fixed or recorded (D144) |
| D144: what a stop request does to an application in progress (a temporary test, not committed; a real worker; the signal `docker compose stop` sends first), before the send gate and before the final click | both times still running 3 s later, then `confirmed`, receiver accepted 1; the worker exited after it |
| D144: a private `redis-server` 7.0.15, default settings: two items pushed, the stop signal, a restart | a snapshot saved before exiting; 2 items after the restart |
| D144, the review's fixes: the tests that need no real worker (three files, `-k` as in `docs/implementation-status.md`; JUnit) | exit 0; 24 passed |
| D144, the review's code fixes removed in turn on f62e72d (3 changes) | all 3 fail their test |
| D144, the review's fixes: the suites that start real workers, `test_browser_isolation.py` and `test_recovery_hardening.py` (7 files, JUnit), on f62e72d | exit 0; 102 passed |
| D144 after the review's last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; `scripts/test_smoke_lib.sh`; the tests that read the documents, `test_deployment_config.py` and `test_attempt_queue.py` (JUnit) | ruff clean (376 files unchanged); the script's 12 cases as expected; exit 0; 208 passed |
| D144's pull request (#53): CI on e40ee72 | all four jobs passed (`docker-smoke` in 3 min, `execution-compose` in 8 min, `frontend` in 14 min, `backend` in 72 min): the first run of the two-worker Compose layout; merged as 099642c, tree 33b8b0d as predicted |
| D145, first version (the whole document's record; superseded): the seven cases with the rule removed, before it was committed (`pytest tests/test_dropdown_strategies.py -k "however_slowly or accepted_when_read_slowly or pages_own_record"`, JUnit) | 3 failed (the 590 and 610 ms cases and the rule's own test), 4 passed |
| D145, first version: the seven cases, on the tree committed seconds later as e81bfeb (JUnit) | exit 0; 7 passed |
| D145, first version: `pytest tests/test_dropdown_strategies.py` on e81bfeb (JUnit) | exit 0; 50 passed |
| D145, first version: removal runs on e81bfeb (6 changes, each in turn) | all 6 fail a test; with a page that records nothing refused, 49 of the file's 50 still pass |
| D145, first version: the regression set (63 files, JUnit), on 15c5e36; the only test run on the machine, with the reviewer's read-only commands during part of it | exit 0; 1564 passed in 55 min |
| D145, first version, after its last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents and `test_dropdown_strategies.py` (JUnit) | ruff clean (376 files unchanged); exit 0; 228 passed |
| D145 rework (the record of changes to a list): `pytest tests/test_dropdown_strategies.py tests/test_greenhouse_controls.py` (JUnit), on the tree committed seconds later as 76da079 | exit 0; 112 passed (55 and 57) |
| D145 rework: the observer's own test in a real browser, then it with the three cases on a stand-in for the probe (`-k pages_record_tells`, then `-k "pages_record_tells or pages_own_record or three_equal or gone_before"`; JUnit), on the tree committed a second later as fe9582c | exit 0; 1 passed, then 4 passed |
| D145 rework: removal runs on fe9582c (18 changes, each in turn) | all 18 fail a test; with a page that records no change to a list refused, the two cases on a stand-in for the probe fail and the dropdown file's other 54 pass (no stand-in leaves that record empty) |
| D145 rework: the case that gives the busy page a real page's window, with its two neighbours (`-k "changing_elsewhere or real_pages_window"`; JUnit); then alone, six times, with the whole page's record put back (the file restored after, identical); committed as a080d3d about two minutes later | exit 0, 3 passed; with that record: failed in 6 of 6 runs |
| D145 rework: the regression set, the only test run on the machine (63 files, JUnit), on a080d3d | exit 0; 1575 passed in 59 min |
| D145, the second review's fixes: `pytest tests/test_dropdown_strategies.py tests/test_greenhouse_controls.py` (JUnit), on ae54f21 | exit 0; 116 passed (58 and 58) |
| D145, the second review's fixes, removal runs on ae54f21 (2 changes) | both fail their test |
| D145 rework, after the last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents (JUnit) | ruff clean (376 files unchanged); exit 0; 178 passed |
| D146: `pytest tests/test_republish_queued.py` (JUnit), on the tree committed as 41e1d6d | exit 0; 11 passed |
| D146 removal runs on 41e1d6d (15 changes, each in turn) | all 15 fail a test |
| D146 after its review: `pytest tests/test_republish_queued.py` (JUnit), on the tree committed as 7424916 | exit 0; 15 passed |
| D146 after its review: removal runs on f3cd566 (21 changes, each in turn) | all 21 fail a test (a first attempt on the same tree was refused before any test ran: the database server had stopped with a restart of the session's machine; rerun once it was started) |
| D146: the regression set, the only test run on the machine (64 files, JUnit), on f3cd566 | exit 0; 1590 passed in 63 min |
| D146 after its second review: `pytest tests/test_republish_queued.py` (JUnit) on cc836b5, then the revoke fix undone and its test run | exit 0; 25 passed (16 and 9); with the revoke fix undone its test fails (a 500) |
| D146 after the last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents and `test_deployment_config.py` (JUnit) | ruff clean (377 files unchanged); exit 0; 195 passed |
| D147, the new tests and the migration's: `pytest tests/test_restore_hold.py` and the migration's test (JUnit), on c9eaf56 (D146's branch merged in) | exit 0; 16 passed |
| D147, the files the change touches: `pytest` on `test_migrations.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_doc_references.py`, `test_notifications.py`, `test_auto_apply.py`, `test_republish_queued.py`, `test_test_isolation.py`, `test_deployment_config.py` (JUnit), on c9eaf56 | exit 1; 105 passed, 1 failed: the feed's scoping test counts the feed's queries, and the restore item adds one. The test was corrected (the count, and what that query is), committed as 08b0237; then `tests/test_notifications.py`: exit 0, 12 passed |
| D147, each part changed in turn: 17 changes, one at a time on 08b0237, the named tests run, the file restored | all 17 fail a test |
| D147, an oid is not enough across servers (a measurement): two throwaway clusters (`initdb` in the scratchpad, a private port), a database created first in each | both databases had oid 16384; the clusters' identifiers differed. Hence the cluster's identifier in the stamp (fcfa4f5) |
| D147, after the cluster's identifier and the relay's check: `pytest tests/test_restore_hold.py tests/test_notifications.py` and the migration's test (JUnit), on the tree committed a minute later as fcfa4f5 | exit 0; 29 passed (16, 12 and 1) |
| D147, each part changed in turn, again: 22 changes, one at a time on fcfa4f5 (the 17, three with moved targets, and five new) | all 22 fail a test (a first start stopped at the script's own check, before any change: one target had moved) |
| D147, the regression set on fcfa4f5: `pytest` on 67 files (D146's 64, `test_restore_hold.py`, `test_migrations.py`, `test_audit_inventory.py`; JUnit) | stopped by me after the independent review, before it finished: the rework below superseded that tree; its databases dropped |
| D147, the rework after the review, while it was written: `pytest tests/test_restore_hold.py tests/test_notifications.py`, the migration's test, `test_applications.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_code_wait_quarantine.py` (JUnit) | exit 1; 72 passed, 2 failed, both from the rework: the held test approved an application after the restore, which is now refused (it is prepared before the restore now), and the audit inventory needs the restore's pause in a row of its own |
| D147, the same, after both corrections: `pytest tests/test_restore_hold.py tests/test_audit_inventory.py tests/test_auto_apply.py tests/test_republish_queued.py`, then the document tests (`test_audit_inventory.py`, `test_doc_references.py`, `test_approval_reasons.py`; JUnit) | exit 1; 58 passed, 1 failed (the inventory: a row per key set); then, with the second row, exit 0; 12 passed |
| D147, the reworked tests: `pytest tests/test_restore_hold.py`, the migration's test, `tests/test_deployment_config.py` (JUnit), on the tree committed a minute later as e365797 | exit 0; 40 passed (22, 1 and 17) |
| D147, each part changed in turn, after the rework: 31 changes, one at a time on e365797 | 30 of 31 fail a test; the 31st (the standing rule's own check) failed once its test required the rule to do nothing at all (6064a83) |
| D147, the rework's test of the standing rule made stricter: the rule's test, then its own check removed (JUnit), on 6064a83 | exit 0, 1 passed; with the check removed, it fails |
| D147, the regression set on 6064a83: the same 67 files (JUnit) | stopped by me after the second review, a few minutes in: its fixes superseded that tree; its databases dropped |
| D147, the second review's blocker reproduced: the review's static comparison of every table with the export's decisions, read on e365797 | `instance_stamp` the only table without one (`tests/test_account.py` was not in any earlier run) |
| D147, after the second review's fixes: `pytest tests/test_restore_hold.py tests/test_account.py tests/test_applications.py tests/test_approval_reasons.py tests/test_audit_inventory.py tests/test_doc_references.py tests/test_auto_apply.py tests/test_republish_queued.py tests/test_notifications.py` and the migration's test (JUnit), on the tree committed a minute later as a6c1444 | exit 0; 127 passed (26, 16, 24, 9, 2, 1, 20, 16, 12 and 1) |
| D147, each part changed in turn, after the second review: 39 changes, one at a time on a6c1444 | all 39 fail a test |
| D147, the regression set, the only test run on the machine: `pytest` on 67 files (D146's 64, `test_restore_hold.py`, `test_migrations.py`, `test_audit_inventory.py`; JUnit), on c0dd87b (with D146's branch as it now stands merged in) | exit 0; 1637 passed in 62 min |
| D147, after the last edit: `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents and the account export's (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`; JUnit); the frontend's `npx tsc --noEmit` and `npm run lint` | ruff clean (380 files unchanged); exit 0, 45 passed; `tsc` and lint exit 0 |

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
- **Declaring the attempts' queue by name only** (D144's first draft). A queue declared without
  an exchange is bound to the default exchange and routing key, with the default queue. I first
  took that to mean every message would reach both queues; a probe showed otherwise: Celery's
  own publishing addresses a queue directly, so each message still reaches one queue. Only a
  message published to the default exchange and key by name reaches both. Each queue names its
  own exchange and key all the same (as a queue Celery creates itself has), and a test reads
  the broker's bindings.
- **Passing a misplaced attempt message on through the outbox** (D144). Durable, but a message
  passed on that way cannot be told from a new one, so a broker naming the queue differently
  would pass it on for ever. It is published directly, marked, and passed on once.
- **Counting the page's changes between the reads instead of timing the last one** (D145). The
  probe already counts them, and an unchanged count over three reads says the same where the
  reads are 250 ms apart. The time was kept: a fixed half second does not depend on the
  reading interval at all, slower or faster.
- **A heartbeat in the page, so that a stalled page cannot look quiet** (D145). It would leave
  a timer of ours running in the employer's page; the probes only read. A page whose own
  timers stall did not change in that time, and D145 says so as a limit.
- **The whole document's record as the rule** (D145, its first version). Built, reviewed and
  dropped. On a page that changes anything, anywhere, every 500 to 750 ms a check would pass
  only now and then, each opening at its own moment, so a check could pass and the choice then
  fail after data had been entered (the review's arithmetic: with one change every 600 ms, 64%
  of openings settle within the real window). The record was narrowed to changes that touch a
  list, found by the marks the probe already reads lists by.
- **A new adapter version for the stricter rule** (D145). Every live approval of the
  Greenhouse adapter would stop matching, for a rule that decides only whether a list is read:
  an approval is for the same options, entered the same way. D108 and D109 changed how a list
  is opened and judged without one. Kept at 4; what that leaves is recorded (a rehearsal
  earned under the weaker test still counts).

- **Looking in the broker for an attempt's message before publishing it again** (D146). It
  would spare the extra message of an attempt only waiting its turn. It is particular to one
  broker, and a message a worker holds sits in another structure. Not built.
- **A named volume for the broker** (suggested by D144's review for `docker compose down`). It
  keeps what waits across `down`; it does nothing for a crash, a lost worker process or a task
  that fails before the claim. Publishing again covers all of them. Not added.
- **A growing wait, or a cap, between publications** (D146). Fewer extra messages behind a
  long wait or a stopped worker; a fixed five minutes is easier to state, and an extra message
  ends at the claim. Recorded as a limit (about 285 a day per attempt while the worker is
  stopped). Not built.

- **Recognizing a restore by the database's oid alone, or by the cluster's identifier alone**
  (D147). The guide's restore on the same server changes only the oid; a restore onto another
  server can keep it (two new clusters gave their first database the same oid, 16384) and
  changes only the cluster's identifier. Both are stamped.
- **One stamp row with a fixed key** (D147, the first version). A stamp the new server wrote
  for itself before the backup's arrived (a backend that migrated the empty database first, a
  scheduler left running) won, and the restore went unrecognized; found by the review. Stamps
  are keyed by identity now.
- **Ending what was queued as "stopped before sending anything"** (D147, the first version).
  It may have run and been sent after the backup; approved again, it would have been sent with
  no reconciliation, and the resumed standing rule could have approved it by itself. Found by
  the review: it is quarantined as an unknown outcome now.
- **Refusing every request while held** (D147). The owner needs the app to see what was
  restored; refused are what could send (the claim, queueing, approving, the standing rule)
  and what would record nothing sent for what the backup shows in progress (cancelling,
  revoking; pausing only pauses, and the sweeper waits).
- **Ending a rehearsal in progress as the sweeper would** (D147, before the second review). A
  rehearsal never submits, but the submission that follows it may have been sent after the
  backup, and its application would have waited for approval again: quarantined too now.
- **`--single-transaction` for the guide's `pg_restore`** (suggested by D147's review). A restore
  that fails part way would then leave nothing instead of a partial database. Not changed:
  CI's smoke test runs the guide's commands and this one could not be tried locally, and the
  guide's check finds a restore whose stamp did not load.

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

1. D147 (branch `restore-hold`, rank 20): its pull request (D146 merged as #55), so that
   `main` carries the deployment guide's restore step by hand only briefly. Then ranks 12
   and 13 (the Workday-style follow-up question and repeating records), rank 16 (a stop
   request honoured before the next step) and ranks 17 to 19 (the dropdown rule's
   neighbours).
2. Owner decisions: on a Workday-style wizard (D142), continuing after a stop, rehearsing then
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
