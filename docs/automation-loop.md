# Greenhouse + Workday automation loop: continuation record

One concise, sanitized record of where the loop stands, so work can resume from it. No personal
answers, credentials, employer-identifying evidence, raw pages or unredacted logs belong here. The
canonical backlog is `docs/remaining-work.md` (its "Automation loop" section); decisions are in
`docs/decisions.md`.

**Updated:** 2026-11-06 (UTC).

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
| `main` | a13b3c6 (tree ee316cc2, as predicted): #35 D120 (d42dabd, tree f8b49d21; main CI #246 green on all four jobs), #38 exposure-evidence note (c4503cf), #36 D131 (a13b3c6; 4/4 green on the combined tree) |
| D131 follow-up (the review's remaining findings) | PR #39, branch `answer-safety-followup`; 2596 focused tests passed locally; CI running |
| D132 form-change pause and questions tab | branch `form-change-pause` (d197bb7), built after three design critiques; 16 new tests pass locally; affected suites, an implementation review and the e2e still to finish before its PR |
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
| 1 | Known answer fills and survives readback | fx (gh2 stand-in) | fx, single-page approximation only |
| 2 | New question → questions tab → saved → resumes | fx on the D132 branch (gh2 by id and pilot stand-in), not on `main` | fx on the D132 branch (e2e), not on `main` |
| 3 | Future reuse | unit (resolver), generic form | unit |
| 4 | Unsafe similar question refused | unit; D131 merged (#36); more wordings in #39 | unit |
| 5 | Conditional question | partial: v1 fixture only; id-only real structure cannot answer it | absent (no branching fixture) |
| 6 | Unsupported widget → checkpoint | fx at capture; some types refused only after approval | fx at capture |
| 7 | Repeating records | fx education stand-in (D120); employment unit | absent |
| 8 | Answer edits invalidate approvals | fx | fx (single page) |
| 9 | Recovery without duplicates | fx on the generic form; not run on gh2 | partial |
| 10 | Sensitive answers | partial; D131 merged (#36); vaccinations and work documents in #39 | partial (never inferred only) |
| 11 | Upload failure preserves evidence | fx for UploadFailed; other exceptions lose it | fx (single page) |
| 12 | Uncertain send quarantined | fx | fx (final send only; each Next not modelled) |
| 13 | Cancellation respected | fx on the generic form; D113 ignores revocation and pause for queued work | partial |
| 14 | Tenant isolation | fx (per-application routes) | partial (no Workday-shaped test) |
| loop | Durable pause → answer → recheck → continue | fx on the D132 branch: pause, read again, answer, one new run (receiver ledger) | fx on the D132 branch (e2e) |
| tab | "Questions needing your answer" | built on the D132 branch (`/questions`) | built on the D132 branch |

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
- **D132 (branch, not merged).** A form that no longer matches pauses the application instead of
  dead-ending; "Questions needing your answer"; read the form again; "Try this version again".
  - Three design critiques changed the first build. Only a new question pauses; changes only the
    live page shows stay plain stops; a change found after filling never pauses.
- **Research** (log below):
  - corrected the Workday terms note: the End User Agreement covers scoutrfp.com;
  - Workday saves a draft on every Next;
  - Greenhouse's invisible reCAPTCHA can require an emailed code.

## Hypothesis and next slice

The loop itself (**D132**) is built on its branch: a form change found before anything is entered
becomes a durable, user-scoped pause, listed under "Questions needing your answer". Reading the form
again rechecks the capture route's permissions, the new questions are answered and approved, and
exactly one new attempt runs. The receiver ledger is the oracle, on the gh2 and Workday-style
stand-ins. Next: finish its validation and open its PR. Later ranks:
- D113 notify-and-continue (needs an owner decision);
- answerable conditionals on the id-only structure;
- capture refusing what cannot be filled, and evidence surviving any failure;
- provider-shaped reuse tests;
- EEOC/demographic end to end;
- reviewable sections;
- the Workday multi-page wizard stand-in;
- recovery hardening.

## Unvalidated or partly validated changes

- **D131:** merged; its CI passed on the combined tree.
- **D131 follow-up (#39):** focused suites passed locally (2596 tests) and e2e passed (6 tests). The
  full suites run in its CI.
- **D132:** 16 new tests pass locally. Still to finish: the existing suites it touches, an
  implementation review and its e2e.

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

## Exact next action

1. Merge #39 (D131 follow-up) when its 4 checks pass.
2. D132: record the affected suites and the implementation review, fix what they find, run
   `e2e/questions.spec.ts`, then merge `main` into `form-change-pause` and open its PR.
3. Then the next ranked slice: the owner's decision on D113 continuing after a form change.

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
