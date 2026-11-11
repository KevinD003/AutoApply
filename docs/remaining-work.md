# Remaining work: the canonical table (2026-10-29; automation loop section 2026-11-06)

This is the one list of what NoEfforts is, what it is not yet, and what each remaining item
depends on. It is reconciled against the original roadmap (`docs/product-evidence.md`, rows 1-23,
including the planned surfaces in row 17), the plan (`docs/implementation-plan.md`), the decisions
(`docs/decisions.md`, D1-D75), the evidence (`docs/evidence-matrix.md`) and the code at the commit
that adds this file. It replaces no other document; where they disagree, this file is the one to
correct first.

**NoEfforts is not a finished product.** Nothing has applied to a real employer. Every
submission so far went to the local receiver (`fixtures/ats_receiver`), whose ledger is the test
oracle, and no reliability against real employers has been measured.

## States used

| State | Meaning |
|---|---|
| **Fixture-tested** | Implemented and tested in this repository against synthetic data and local fixtures (backend tests, Playwright on desktop and mobile, CI). Not shown to work against a real employer or service. |
| **Awaiting deployment verification** | Implemented and tested in CI or the cloud sandbox, but not yet run on the owner's own machine or a real deployment. |
| **Awaiting access or consent** | Implemented (or ready to implement) but kept off until the owner grants a permission, a credential, network access or consent. |
| **Unfinished** | Product functionality that does not exist yet, or exists only as a specification or contract. A specification is not a product surface. |

## What was observed on a real site, exactly

The only contact with a real application site is the owner-authorized, read-only Greenhouse
observation of **one public posting chosen by the owner** (employer and posting deliberately not
named; `docs/greenhouse-readonly-compatibility-proposal.md`, "Runs"). In manual CI runs #2-#9:

- **Read:** the posting's job JSON from Greenhouse's public Job Board API (robots.txt, the job
  post with its questions, the board: 3 GET requests per run), and the hosted application page,
  loaded once per run in the isolated browser (9 to 26 GET requests per run).
- **Touched:** in runs #8 and #9 only, the browser clicked and focused 12 dropdowns to see whether
  their option lists open (24 actions per run). Nothing was selected, typed, changed or saved.
- **Never done:** no candidate data, no typing, no file upload, no consent click, no form
  submission, no account, no login, on any real site. Run #7 made no page action at all.

So "nothing has been used for real" means: nothing has been **filled, uploaded or submitted**
anywhere real. Real pages and APIs **have** been read, as above, under single-use approvals.

## The table

| # | Feature | Actual state | Evidence / tests | Concrete dependency | Human action required? | Next safe step |
|---|---|---|---|---|---|---|
| **Surfaces** (`product-evidence.md` row 17) | | | | | | |
| 1 | Web app (Next.js, responsive) | Fixture-tested | `frontend/e2e/*.spec.ts` (desktop and mobile projects), including `journey.spec.ts` | — | No | Keep every new feature in the journey |
| 2 | HTTP API for the web app (FastAPI, cookie session + CSRF) | Fixture-tested | `backend/tests/` (3,400+ tests) | — | No | — |
| 3 | Public or third-party API (tokens, versioned contract) | **Partial** (D84): personal access tokens for your own scripts on this machine: hashed, shown once, 30-day default and 90-day maximum expiry, revocable, scopes `read` and `import:jobs` as route allow-lists with default deny (`docs/api-tokens.md`). No versioned public contract and no third-party clients; nothing exposed beyond 127.0.0.1 | `test_api_tokens.py`, `api-tokens.spec.ts` | A decision that third-party clients are wanted | Yes before exposing it | None without that decision |
| 4 | CLI | **Fixture-tested** (D84): `scripts/noefforts.py` (standard library) reads jobs, a job, applications, an application, notifications and its own token, and adds a job with `import:jobs`; no command can answer, consent, approve, queue or submit. Operator tools exist too (`execution.cli`, `discovery.approve`, `discovery.watch`, `gh_readonly`) | `test_api_tokens.py` (in process, and as a subprocess against a real uvicorn) | — | No | None planned |
| 5 | MCP server | **Fixture-tested** (D84): `scripts/noefforts_mcp.py`, stdio only, read tools for jobs, applications and notifications, and `import_job` only for an `import:jobs` token; never a submit, approve, answer or consent tool. Not tried with a third-party MCP client | `test_api_tokens.py` (in process, and as a subprocess against a real uvicorn) | — | No | Try it with the owner's MCP client (owner's machine) |
| 6 | Browser extension (capture only) | **Partial** (D90): fixture-tested in Chromium, loaded unpacked, not published. `extension/` saves the current tab's address and title to your own NoEfforts on this machine with an `import:jobs` token (`activeTab` and `storage` only; no content scripts; never the session cookie). It never reads, fills or submits a page. **Unfinished**: sending the page itself, Firefox/Safari builds, a store listing | `frontend/e2e/extension.spec.ts` | Real-page form capture is refused today (409); sending a page would need it | Yes, before it captures a real page or is published | None without that decision; keep the address-only contract |
| 7 | Mobile | Responsive web, fixture-tested at 390×844 (`mobile` project), and **installable** (D89): a web app manifest and a service worker whose only offline content is a static offline page that shows nothing about you (no page, API response or document is cached). **Unfinished**: no native app, no offline data, no push notifications | Playwright `mobile` project, `frontend/e2e/pwa.spec.ts`, `scripts/docker-smoke.sh` | A decision on native apps | Yes, for native apps | Decide on native apps; offline data only with its own export and deletion design |
| 8 | Messaging (notifications: email, push, chat) | **Partial**: the in-app feed (D83) is the source of truth. **Email reminders to the account owner (D94), fixture-tested**: off by default; on only after you verify your address with a code typed in the app and turn them on; at most one daily digest naming only the category (needs attention, follow-up due) with a link to the tracker; never to an employer or recruiter. Tested against a local SMTP sink only. No push or chat | `test_email_reminders.py`, `email.spec.ts` | A real mail server, configured by the owner | Yes, to configure a real mail server | Push and chat only if wanted |
| **Find** | | | | | | |
| 9 | Manual jobs, CSV/XLSX import/export, dedupe, exclusions | Fixture-tested | `test_jobs.py`, `phase-a.spec.ts` | — | No | — |
| 10 | Freehire discovery (documented API, fixture) | Fixture-tested; by application platform (D100): an import can keep only chosen platforms (read from each listing's address) and adds every listing kept to your jobs; the list filters and counts by platform | `test_freehire_discovery.py`, `test_discovery_platforms.py`, `discovery.spec.ts`, `discovery-platforms.spec.ts`, `journey.spec.ts` | — | No | — |
| 10a | Employer job boards (Greenhouse, Lever public postings feeds) | **Fixture-tested** (D95, D96): add a board by identifier, read it when you choose or once a day if you tick "Check daily" (new postings noted in your notifications), see what it lists, save a posting to your jobs; pause, remove; only a complete read says a posting is no longer listed; GET only to the provider's fixed host, nothing of yours sent. Off by default (`NOEFFORTS_BOARD_SOURCES_ENABLED`). **No real board read**: local stand-ins of the documented shapes only. Ashby **not built**: its documentation could not be opened | `test_board_sources.py`, `board-sources.spec.ts`; `docs/research/job-board-apis.md` | Network access from where NoEfforts runs to `boards-api.greenhouse.io`, `api.lever.co` / `api.eu.lever.co`; for Ashby, `developers.ashbyhq.com` reachable to read its docs | The owner turns it on and adds a board | Ashby from its documentation, once reachable |
| 11 | Live Freehire read and watched searches | **Awaiting access or consent**: implemented (D55, D56), never run | `test_freehire_live_read.py`, `test_freehire_watch.py` | The owner's run approval; network access to `freehire.me` (this sandbox denies it) | Yes | Owner records an approval and runs it where `freehire.me` is reachable |
| 12 | Freehire `reality` signals (repost, evergreen) | **Fixture-tested** (D93): the five documented fields read with their types, shown display-only on Discover and the job page as "Freehire says: …", refreshed on every read, never part of the fingerprint, never read by matching, approval, routing or execution | `test_freehire_discovery.py` (D93 tests), `discovery.spec.ts` | Live Freehire reads (row 11) | No | — |
| 13 | Explainable match scoring | Fixture-tested (D79): preferences (met / not met / not stated / not set, counted as "m of n checked preferences met"), eligibility shown side by side and never decided, approved qualifications the job names, missing information; never a probability or an ATS score. Since D82 each jobs-list row summarises the same assessment (preferences counted, approved skills and licences named, unknowns counted) and links to the explanation | `test_fit.py`, `journey.spec.ts`, `match-summary.spec.ts` | — | No | None planned |
| 14 | Job signals (closed, excluded, possible duplicate) | Fixture-tested | `test_job_signals.py`, `job-signals.spec.ts` | — | No | — |
| **Prep** | | | | | | |
| 15 | Profile facts, work authorization, preferences kept apart | Fixture-tested | `test_profile.py`, resolver tests, `journey.spec.ts` | — | No | — |
| 16 | Editing work history, education and licences in the page | Fixture-tested (D78): "Edit" loads the record into its form, "Save changes" updates it through the existing `PUT` as a new version | `test_profile.py`, `profile-edit.spec.ts` | — | No | — |
| 17 | Resume text → proposed facts | Fixture-tested (L1, D72) | `test_resume_facts.py`, `journey.spec.ts` | — | No | — |
| 18 | Deterministic resolver and checkpoints | Fixture-tested | `test_resolver.py`, `legacy_collisions.json` (244), `journey.spec.ts` | — | No | — |
| 19 | Saved answers | Fixture-tested: save, reuse, delete, and editing (D78) as a new version with its history kept; applications that used the earlier version ask for approval again; a running submission stops | `test_bank_edit.py`, `test_bank_scope*.py`, `test_execution_validation.py`, `answers-edit.spec.ts` | — | No | — |
| 20 | Document versions, deletion | Fixture-tested | `test_documents.py`, `documents.spec.ts` | — | No | — |
| 21 | Document preview | Fixture-tested (D78): the text NoEfforts reads from the file, as plain text only (no viewer, no HTML, no external request), at most 20,000 characters | `test_bank_edit.py` (preview tests), `answers-edit.spec.ts` | — | No | — |
| 22 | Long-form drafts, tailored resume, cover letter | Fixture-tested with labelled test doubles, end to end in `journey.spec.ts` with the local fixture provider (D75) | `test_drafting*.py`, `test_generated_documents.py`, `test_fixture_provider.py` | — | No | — |
| 23 | Claude as the drafting provider | **Awaiting access or consent** (L4, D74): built, off | `test_drafting_provider.py` | The owner's key, owner account and daily budget; consent text for anyone else is a legal decision | Yes | — |
| 24 | Importing the owner's ~4,000 old saved answers | **Ready for the owner** (D99): Saved answers → "Import saved answers" checks a JSON or CSV file by the saved-answer rules and adds what passes as proposals that answer nothing until approved one by one. The owner's files were supplied 2026-10-31 and reviewed privately outside the repository (report, candidate answers, facts to confirm, sent statements to check); **nothing of theirs imported**. Their review also led to D98 (wordings now recognised) | `test_bank_import.py`, `answers-import.spec.ts`, `test_classify_archive_wordings.py` | The owner's marked review file, imported on their own NoEfforts; facts confirmed on the Profile page | Yes | — |
| **Apply** | | | | | | |
| 25 | Package approval, rehearsal, separate submission approval, submission, receipt | Fixture-tested | `test_execution_*`, `submission.spec.ts`, `journey.spec.ts` | — | No | — |
| 26 | Greenhouse-style adapters | Fixture-tested; real pages read-only only (above). **The Greenhouse pilot (D102), built and off by default; authorized by the owner (D112) for all four steps until 2026-11-06, at most 5 attempts:** `greenhouse_live` applies to real Greenhouse-hosted job posts for the owner's account (production, container isolation), each application approved in the app, the first to each employer a rehearsal. The pilot may load the page's locale files under read-only path C's rule (D111). It runs only on the owner's server once switched on (`scripts/verify-local.sh --pilot`, `docs/activation-status.md` §5). Greenhouse's terms reviewed (`docs/research/greenhouse-terms-review.md`). **Never yet run on a real page** | `test_greenhouse_*.py`, `test_greenhouse_live.py`, `docs/greenhouse-compatibility-report.md`, `docs/greenhouse-live.md`, `docs/activation-status.md` | The owner's written permission for each step, recorded; readiness evidence (computed for the pilot: 1 of 7 since D112, each condition's next step in `docs/activation-status.md`); the first rehearsals on their machine, on a posting whose required controls are all mapped | Yes | Whatever the first real rehearsals stop on (expected: dropdowns, unlisted controls such as the phone country picker, location search, upload acknowledgement). **D104:** local stand-ins of a phone country picker, a location search and late-loading dropdown options are fixture-tested (`test_greenhouse_controls.py`); on a real page each still stops the attempt before anything is entered, and synthetic coverage is not evidence for one |
| 27 | Lever | **Fixture-tested (local approximation only)**, D85: `fixture_lever` reads a Lever-style posting's form page on the local receiver, fills only approved facts and answers, uploads documents (evidence kept after a partial failure), reads back (a field a parsed resume changed stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. It has **no Lever identity**: a real Lever job stays a manual handoff (`planned_adapter_only`) and the `lever` specification stays `planned`. Not a provider adapter for real Lever pages: nothing was observed on one. Public docs: the Postings API README read; help centre, Data API docs and terms not reachable from this sandbox | `test_lever_adapter.py`, `lever.spec.ts`, `test_lever.py`, `test_lever_fixture.py`; `docs/research/lever.md` | Network access to `hire.lever.co`, `help.lever.co`, `www.lever.co/legal`; the owner's recorded review of Lever's public docs and terms (`public_doc_reviewed`); observing a real page needs the provider-admission approval | Network and approval | Owner: record a Lever docs-and-terms review, or leave Lever at `planned` |
| 28 | Workday | **Fixture-tested (local approximation only, checkpoint-first)**, D88: `fixture_workday` reads a Workday-style single-page application on the local receiver, fills only approved facts and answers, uploads files (evidence kept after a partial failure), reads back (a resume parse that fills a field you left blank stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. Candidate accounts and passwords, email verification, applications on several pages, values the page filled in itself, dependent location lists, pickers and custom dropdowns are all checkpoints, never automated. It has **no Workday identity**: a real Workday job stays a manual handoff (`planned_adapter_only`) and the `workday` specification stays `planned`. No Workday documentation page could be opened from this sandbox | `test_workday_adapter.py`, `workday.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/workday.md` | Network access to `doc.workday.com` and related hosts; Workday's terms (the decision register below keeps it a manual handoff) | Yes | Per-page disclosure accounting before several pages could ever be applied |
| 29 | Ashby | **Fixture-tested (local approximation only)**, D87: `fixture_ashby` reads an Ashby-style posting's application page on the local receiver, fills only approved facts and answers (Yes/No questions naming the country from your facts), uploads files (evidence kept after a partial failure), reads back (a field resume autofill changed stops it), never clicks the cookie banner, rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. The approximation's spam check is a hard stop everywhere: a checkpoint at capture, a stop before anything is entered, an unknown outcome after the final click (as are "already applied" and a confirmation that shows a challenge), never solved, retried or resent. It has **no Ashby identity**: a real Ashby job stays a manual handoff. URL recognition for hosted postings and `?ashby_jid=` embeds as before (D81). No Ashby documentation page could be opened from this sandbox, so every page detail is the fixture's own design | `test_ashby_adapter.py`, `ashby.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/ashby.md` | Network access to `developers.ashbyhq.com`, `docs.ashbyhq.com`; an owner's docs-and-terms review before any Ashby specification | Network only | Confirm the shapes from the documentation |
| 30 | Verification codes | Fixture-tested by manual entry (checkpoint); from the owner's Gmail only once authorized (row 31; D101, D103: not authorized) | `test_execution_*`, `submission.spec.ts`, `test_inbox.py` | — | No | — |
| 31 | Gmail or inbox access (codes, replies) | **Fixture-tested; codes authorized (D117), on by default for the owner; replies not authorized** (D101, D103, D117). Read-only Gmail for verification codes (entered only when exactly one code reads as this application's, the email naming its employer when applications overlap; Greenhouse's mixed-case codes read as written) and application emails proposed as outcomes the user confirms; the text is never kept. Codes: recorded through 2026-11-06 from the owner's words; application emails stay unread. Typing a code yourself is unaffected | `test_inbox.py`, `inbox.spec.ts`, `docs/inbox.md`, `docs/activation-status.md` | The owner's written authorization of each use, recorded; then their Google Cloud credentials and one connect run on their machine | Yes | Verify with the owner's real mailbox |
| 32 | Standing approvals (auto-apply with caps) | **Fixture-tested; built and on by default outside tests** (D113, D114; replaces D91's "not built"): the owner's recorded standing rule applies automatically to fully answered Greenhouse pilot packages only, rehearsal first per employer, within a daily cap and the recorded permission (which ends 2026-11-06), never retrying a stopped attempt, pausable; each account turns it on for itself. Gaps found 2026-11-06 (pausing did not stop work it had already queued; it re-approved after an owner revocation when no attempt was held) are closed by D134 (#43): a pause stops what the rule queued, a revocation stands, and the rule's approvals and attempts are marked as its own | `test_auto_apply.py` | The recorded permission (ended 2026-11-06) | Yes, for real use | Automation loop rank 3: continuing after a form change needs the owner's decision |
| 33 | Tsenta as a provider | **Awaiting access**: developer docs not accessible (D8) | `docs/research/tsenta.md` | Public developer docs reachable | Yes | — |
| **Track** | | | | | | |
| 34 | Tracker, timeline, outcomes with sources, funnel | Fixture-tested | `test_funnel.py`, `tracker-outcomes.spec.ts`, `journey.spec.ts` | — | No | — |
| 34a | Follow-ups | **Fixture-tested** (D92): due a set number of days (7 by default) after you applied, followed up, or recorded an interview or assessment, or on a day you choose; closed by an outcome; an in-app notification when due; a message to copy, never sent | `test_follow_ups.py`, `follow-ups.spec.ts` | — | No | Sending it by email only behind row 8's opt-in |
| 35 | Inbox classification of replies | **Fixture-tested** (D101): fixed wording rules (rejected, interview, assessment, received, unclear); proposals only, confirmed by the user | `test_inbox.py` | Row 31 | Yes | — |
| **Platform** | | | | | | |
| 36 | Docker Compose stack | **Awaiting deployment verification**: smoke-tested in CI (`docker-smoke`, `execution-compose`); the API has a health check and the worker and web app start only once it is healthy; secrets checked before start; owner's guide `docs/deployment.md`; **not run on the owner's Mac** | CI jobs, `test_deployment_config.py`, `scripts/check_env.py` | The owner's machine | Yes: run `./scripts/verify-local.sh` (section 9 of the guide) | Record the Mac result in `implementation-status.md` |
| 37 | Full data export | Fixture-tested: one ZIP of every record and document file, column by column; secrets and keyed material left out with reasons | `test_account.py`, `account.spec.ts` | — | No | — |
| 38 | Account deletion | Fixture-tested: everything that names the account, its files and sessions at once; refused while a submission may be in flight; queued work stops and is never retried | `test_account.py`, `account.spec.ts`, `docs/account-deletion.md` | The retention decision (below); the default keeps nothing | Policy only | — |
| 39 | Backups and restore (local stack) | **Awaiting deployment verification**: documented (`docs/deployment.md` sections 5 and 7: `pg_dump`, a storage archive, drop and restore); the CI smoke job runs the same commands on a throwaway stack; not run on the owner's machine; no scheduled or off-machine backup | `scripts/docker-smoke.sh` | The owner's machine; for scheduled or off-site backups, the hosting choice (row 40) | Yes (run it); hosting is the owner's choice | — |
| 40 | Production hosting (TLS, domain, secrets store) | **Unfinished** | — | Hosting choice and any paid commitment | Yes | — |
| 41 | Spend reporting | **Fixture-tested** (D97): Account → "AI drafting spend": the server's daily budget and reset, today's total and what is left, your requests, tokens and last 14 days, each amount marked estimated, worst case kept, held or nothing sent; an error reply keeps its worst case; each request settled once; exported with the budget settings. Not an invoice | `test_drafting_provider.py`, `drafting-spend.spec.ts` | — | No | Real provider usage only once the owner configures drafting (row 23) |

## Automation loop: Greenhouse + Workday (2026-11-06)

The loop builds the full application path for both providers. It runs from opening and reading the
form, through resolving, filling and reading back, to a durable pause that sends unknown questions to
a separate "Questions needing your answer" tab. It then resumes only after re-checking the page and
the permissions, and submits once under application-specific authorization.

The acceptance matrix (14 workflows by provider, with evidence levels), the tests run, rejected
designs, blockers and the research log are in `docs/automation-loop.md`, the loop's continuation
record. Nothing in it is real-observed beyond read-only Greenhouse mapping. Workday exists only as a
single-page approximation.

Ranked slices. Each is shippable through its own PR, with the receiver ledger as the oracle:

| Rank | Slice | Acceptance items | Status |
|---|---|---|---|
| — | D131 answer safety: self-identification scope, follow-up keys, job requirements, review-page crash | 4, 10, 3 | Merged (#36); the review's remaining findings merged too (#39) |
| 1 | D132: a form change becomes a durable pause; "Questions needing your answer"; read the form again; answer; approve; one new attempt (gh2 and Workday-style stand-ins) | loop, tab, 2, 6, 14 | Merged (#40) |
| 2 | Finish the reuse and suggestion guards: D115 veto, "use here only", Workday decline wordings, an error boundary | 4, 10, 3 | Merged (#41, D133): the saved side judged too, word-level vetoes over label and help, a rule floor under the model, "Use here only", the "wish to self-identify" declines, a screening job counted by the receiver, an error boundary. No recorded Workday source for a new decline wording; residuals in D133 |
| 3 | Standing rule: notify and continue after the owner answers; respect revocation and pause; approval provenance | loop, 13, 2, 14 | Merged (#43, D134): the rule's approvals and attempts marked as its own; a pause stops what the rule queued (one a worker holds at its next step; one being sent is counted, never stopped) and retires the rule's approvals; a worker refuses the rule's attempt while it is switched off or paused; a revocation stands. Continuing after a form change needs the owner's decision |
| 4 | Conditional and page-required questions on Greenhouse's id-only structure become answerable pauses; a click the page blocks is not terminal | 5, 2, 6 | First half merged (#44, D135): a typed question the page reveals is answerable (your answer or a profile fact, never a saved answer or a draft) and entered only when shown; a revealed one the page requires pauses after filling with nothing submitted; choices and uploads hidden at load still never filled. Second half (a click the page blocks is not terminal): needs the owner's decision, because it is found after `sending` began and CLAUDE.md forbids a retry after `sending`; today it ends `failed_terminal` (apply on the employer's site) |
| 5 | Capture refuses what the DOM adapter cannot fill; disclosure evidence survives any failure after an upload | 6, 11, 1 | First half merged (#45, D136): every control the DOM adapter cannot fill (a native dropdown, a checkbox, a list of several choices) is refused when the form is read, a required one a checkpoint and an optional one left blank, never after you approve. Second half merged (#46, D137): each disclosure is recorded the moment it is made, so an unexpected error or a killed worker after an upload keeps its evidence, and a failure during an upload counts the document as possibly received (page and API) |
| 6 | Saved-answer reuse and unsafe-reuse refusal on Greenhouse- and Workday-shaped forms (ledger) | 3, 4, 8 | Merged (#47, D138; fixtures and tests): a saved answer reaches the next Greenhouse-style job asking the same question; a look-alike naming a country is neither reused nor suggested; on the Workday-style form education is reused and the shift never is; editing a saved answer retires the approval that used it |
| 7 | EEOC, demographic and Workday self-identification end to end (opt-in, decline, scope, withdrawal) | 10, 4, 6 | Merged (#48, D139): shown on the receiver's ledger on gh2 (by id and pilot) and the Workday-style form (opt-in, decline, scope, your per-application choice, a required question without a match, withdrawal and change); a change to your self-identification now retires its approvals at once and the profile page says how many. Not modelled: Greenhouse's own `compliance[]` and demographic survey, the disability form's name and date; the standing rule's consent text is the owner's decision |
| 8 | Structured sections reviewable and diffed; employment stand-in; section comboboxes react-select-safe | 7, 8 | First half merged (#49, D140): the rows sent shown on the review page and diffed by record and field; an education or employment edit retires its approvals at once (receiver ledger on the education stand-in). Second half merged (#50, D141): an employment stand-in, and section comboboxes filled as D109 fills a dropdown (never typed into, their own list only, the frozen id, a react-select choice read back from its single value), every section control read back before the send gate; extraction v6. Real pages wait on the section observation |
| 9 | Workday-style multi-page wizard stand-in: per-step disclosure gates and per-page pauses | 1, 2, 5, 7, 9, 11, 12, 13, loop | Merged (#51, D142; fixture only): the five-page stand-in filled forward only, a gate that commits before each page's fill and Next, each page read back before its Next, a Next clicked once; anything unexpected after disclosure ends the attempt for good (a Next that may have submitted is quarantined in `submitted_unconfirmed`) and the application is never run again; a cancel mid-wizard is refused (revoke stops it). Per-page pauses are not built: continuing after a stop, rehearsing a wizard and the standing rule on one need the owner. Branching follow-ups (5) and repeating My Experience records (7) not built |
| 10 | Recovery hardening: task time limits, lease renewal, checkpoint cleanup, crash tests on both providers | 9, 12, 13, 11 | Merged (#52, D143; stand-ins only): the runner bounds its own run (a budget checked between steps; past it the final click is never made); an attempt's task has one time limit that covers the whole wait for a code, and no soft limit (measured: one that lands inside a browser wait cannot be handled); a lease follows progress and covers each wait for the employer's answer, also for a code typed late; a verification request ends with its attempt and keeps no code; cancel and wizard texts say what happened; a worker killed at each point on the gh2 and Workday-style forms is never run again once data was entered. Attempts sharing the worker pool with the periodic tasks: rank 11 |
| 11 | Attempts on a queue and worker of their own, so two attempts waiting for codes never hold up the sweeper, the outbox relay and the mailbox reader | 9, 12 | Merged (#53, D144; stand-ins only): an attempt's task has a queue of its own and, in the Compose stack, a worker that takes nothing else (one process: one browser slot); the schedule and every periodic task run on a second worker, `scheduler`, with no runner token or control socket. Measured before: with one shared worker and both processes waiting for codes, a periodic task was not taken until a code was entered. A message for an attempt on another queue is passed on once, never run there. A worker without `-Q` still takes both (development, tests). The Compose layout itself runs only in CI, where it passed. An independent review found no blocker; what it found is fixed or recorded in D144 (the mailbox token belongs in `scheduler` now; `docker compose down` discards what waits in the broker; `stop` is not immediate, `kill` is) |
| 12 | A Workday-style follow-up question the page shows after an earlier answer: answerable when the form is read, entered only when shown | 5 | Unfinished |
| 13 | Workday-style repeating My Experience records | 7 | Unfinished |
| 14 | A dropdown's list counts as settled only when the page itself has recorded no change to a list for half a second, besides three equal reads | 1, 6 | Merged (#54, D145; stand-ins only). Found by D143's regression run under load: the adapter read the list every 250 ms and called it settled after three equal reads; when that interval stretched to about twice a periodic re-render (the stand-in's `late_slow_changing`, every 300 ms) every read saw the same order, and at 610 ms the list was judged settled. Now the page's own record of the last change to a list must also be half a second old, or absent: such a list is refused however slowly it is read, a settled one is still accepted when read slowly, and changes elsewhere on the page do not count in the new record (the classification's 150 ms check still counts them: rank 19). The location search follows the same record. Limits in D145: changes half a second or more apart, a page whose timers stall, a list that changes without the observer seeing it; never seen on a real page |
| 15 | A queued attempt whose broker message is lost is published again | 9 | D146 on branch `republish-queued` (stand-ins only). Nothing published a dispatched message a second time, so an attempt stayed queued until it was cancelled when the broker lost its message (`docker compose down`, a crash), when a worker process died between receiving the message and claiming the attempt, or when the task failed before the claim; more exposed since D144. The relay's task now publishes again, every five minutes, for an attempt still `pending` (no cancel requested, nothing entered), and the claim refuses an attempt that entered data. A second message is ignored by the claim (shown with a real worker and a receiver told to accept a repeat). Found by its review: after a database restore, what the backup shows as queued now runs, even if it already ran (ranked slice 20; until then the deployment guide's §7 has a step for it) |
| 16 | A stop request to the worker is honoured before the next protected step | 13, 12 | Unfinished. Found by D144's review and measured: `docker compose stop` asks, and ends the worker ten seconds later; an application in progress goes on meanwhile and can still be submitted. The owner's table names `docker compose kill` for "now" (ends it at once; what a killed worker leaves is tested). Not built: a worker that, once asked to stop, takes no further protected step |
| 17 | A section's combobox (education, employment) reads its list through the dropdown's settle rule | 7, 6 | Unfinished. Found by D145's review: it reads its list once, with no test of settling at all (`greenhouse_sections.py`), the weakest of the three paths that choose from a list. Stand-ins only |
| 18 | The read-only survey reports whether each list met the adapter's settle rule | 1 | Unfinished. Found by D145's review: the survey's window was set equal to the adapter's so that it shows what the adapter would accept; since D145 the adapter also asks for no change to a list for half a second, which the survey neither tests nor publishes (one yes or no per dropdown would do). Until then no survey run, run #11 included, shows whether a real page meets the rule. Code only; a new run needs the owner's permission |
| 19 | The classification's whole-document check judged, in the adapter, by the list's own record | 1, 6 | Unfinished. Found by D145's second review: a read within 150 ms of any change on the page cannot settle (since D106), so a page that changes something every 250 to 300 ms can still have a list refused in a real page's window, depending on the reading pace (4% to 55% of openings by the review's arithmetic). Refusals only, before or after disclosure, never a wrong choice. The fix would use the list's record there too and count changes to style sheets, which that record does not; it needs its own tests on a page busy elsewhere in a real window. Stand-ins only |
| 20 | A restored database comes up held: nothing it shows as queued or in progress runs by itself | 9, 12 | Unfinished; next after D146. Found by D146's review: a restored database cannot know what ran after its backup, and since D146 an attempt it shows as queued is published again and run, so an application sent after the backup can be sent a second time. Narrower ways existed before (a message not yet published at the backup; an attempt claimed and not yet disclosing, which the sweeper puts back). Planned: a step in the restore that ends what was queued or claimed before disclosure (never re-queued), treats one that was sending or waiting for a code as unknown, pauses the standing rule and tells the owner, run by the deployment guide and the smoke test. Until then the guide's §7 has the owner do this by hand |

**External, for the loop:**
- The recorded pilot and mailbox permissions end 2026-11-06.
- A capturable real Greenhouse posting is needed, with a single-use disclose-only permission.
- The owner must decide on Greenhouse's invisible reCAPTCHA before a first real submission.
- A real section observation is needed (D120).
- Workday needs:
  - the owner's terms decision, reframed: the End User Agreement covers scoutrfp.com, not career
    sites;
  - a recorded documentation review;
  - a read-only observation;
  - the user's own candidate sign-in.
- D113 continuing after a pause needs the owner's decision.
- A final click the page's own checks block (rank 4, second half) needs the owner's decision: a
  retry after `sending`, which CLAUDE.md forbids.

## Provider evidence ladder

Each rung is separate evidence; a lower rung never stands in for a higher one. "Fixture" means a
local synthetic page or service; nothing on this ladder implies live support.

| Provider | URL recognition | Synthetic form coverage | Provider-specific adapter | Observed real-page behaviour | Approved disclosure rehearsal (real) | Confirmed submission (real) |
|---|---|---|---|---|---|---|
| Greenhouse | Yes (hosted, embed `gh_jid`, `/embed/job_app`); gaps recorded (`identity_jid_any_host`, `identity_rules_disagree`) | Yes: receiver v1 and v2 forms, failure modes; D104 stand-ins of a phone country picker, a location search and late dropdown options | Yes, against local fixtures (`greenhouse_hosted`, `greenhouse_dom`) and a stand-in board host (`greenhouse_live`, D102) | Read-only only (above): job data and page read; dropdowns opened in two runs; never typed | Built, off (the pilot's rehearsal, D102); none run | Built, off (D102); none run |
| Lever | Yes (hosted, EU) | Yes (D85): the receiver's Lever-style posting, form, uploads, submit and confirmation, with failure modes | **Fixture only, no Lever identity** (`fixture_lever`, D85): it never serves a real Lever posting. Missing for real Lever: the owner's docs-and-terms review, a read-only observation, an identity-bearing adapter | None | None | None |
| Workday | Yes, except the `/apply` variant (gap `identity_variant_unrecognised`) | Yes (D88): the receiver's Workday-style posting and single-page application, uploads, submit and confirmation, with checkpoint modes (account gate, several pages, prefill, resume parse, dependent location list, custom dropdown, email verification) | **Fixture only, checkpoint-first, no Workday identity** (`fixture_workday`, D88). Missing for real Workday: documentation access, the owner's terms decision, per-page disclosure accounting, a read-only observation | None | None | None |
| Ashby | Yes (hosted; embeds since D81, gap recorded) | Yes (D87): the receiver's Ashby-style posting, application page, file uploads, submit and confirmation, with failure modes (spam check on the form or after the click, already applied, autofill, drift, a confirmation on another posting) | **Fixture only, no Ashby identity** (`fixture_ashby`, D87): it never serves a real Ashby posting. Missing for real Ashby: documentation access, a specification, the owner's docs-and-terms review, a read-only observation | None | None | None |
| Workable, SmartRecruiters | Yes | None | None | None | None | None |

**Lever-style adapter milestone: done (D85), with one deliberate change.** The adapter is
`fixture_lever`, registered with no Lever identity, not an identity-bearing `lever_hosted`:
the admission framework admits an ATS-identified adapter to `fixture_only` only after the
owner's recorded review of that ATS's public docs and terms, and none is recorded for Lever.
So real Lever jobs keep the planned specification's manual handoff (`planned_adapter_only`),
fixture evidence counts for nothing on Lever, and a listed fixture origin must be a local host:
naming a public site there never makes it a fixture.

**Fixture-origin boundary: tightened (D86).** Fixture origins are honoured only with
`NOEFFORTS_ENV=test`; a name counts only if listed exactly (`receiver`, the Compose service),
and every connection to one (server-side and through the egress proxy) must reach loopback or
the configured test network. Found and fixed on the way: in `netns` mode the driver fetched
page loads itself, outside the egress proxy.

**Ashby-style adapter milestone: done (D87).** `fixture_ashby`, with no Ashby identity, on a
shared hosted-form base it shares with `fixture_lever`. Its spam check, and anything after the
final click that is not this posting's confirmation, is a hard stop: never solved, retried or
resent; an uncertain outcome is quarantined. Real Ashby jobs keep the manual handoff.

**Workday-style adapter milestone: done (D88), checkpoint-first.** Accounts, verification,
several pages, prefill (never trusted without readback and review) and complex location fields
are checkpoints. This ends the `fixture_<ats>` series.

**Product slices after the series: done.** Row 7 (D89): NoEfforts installs as a web app, and
offline it shows a static page that keeps nothing about you. Row 6's safe part (D90): a
capture-only browser extension saves the current tab's address and title to your own NoEfforts
with an `import:jobs` token, and never reads or fills the page.

**What is left, and what it blocks.** Each missing input blocks one action, not the work
around it: a Claude key and budget block paid AI drafting only (row 23; built and tested with
the fixture provider); the answer archive blocks that import only (row 24; the answer bank is
built); live-pilot consent blocks real employer activity only (row 26; local development
continues); hosting is local-first by default, and paid or public deployment is not a pending
routine decision (row 40); the owner's Mac and a real MCP client are environment checks of
features already built (rows 5, 36, 39), not missing backend work; a real mail server is needed
only to send reminders for real (row 8). Reading the owner's Gmail, read-only, for codes and
application emails is built and off until the owner connects it on their machine (rows 31, 35;
D101).

## "Phase E", defined

`docs/product-evidence.md` assigns Phase **E** ("Expansion") to three rows, and nothing else:

1. **Row 1, monitoring many career pages:** NoEfforts' requirement is bounded, scheduled discovery
   from permitted feeds. It was delivered early as Freehire discovery: watched searches exist in
   code (D56) and have not run live (row 11 above). Employer job boards (row 10a, D95, D96) read
   an employer's public postings feed one board at a time, on request or once a day for the
   boards you choose, with a notice of new postings; never a crawl.
2. **Row 2, broad ATS coverage:** claim only tested adapters. Greenhouse-style adapters exist
   (fixture-tested). Lever, Workday and Ashby are rows 27-29.
3. **Row 14, a dedicated inbox with classification and automatic status updates:** row 35, with
   inbox access (row 31), both D101. Status updates are proposed from an email and recorded only
   when you confirm them (D53), never automatically.

The other planned surfaces (row 17: apps, extension, messaging, MCP) were given no phase beyond
"responsive web app first". They stay in scope as rows 3-8 above, not as completed work.

## Decision register (D91)

The open questions, resolved under the owner's standing authorization (2026-10-30). One row per
question; a decided row is final until a demonstrated need changes it. This is not an approval
queue: only the rows marked **external** wait on someone else, and each blocks only its action.

| Question | Decision | Status |
|---|---|---|
| Show Freehire's documented `reality` signals? | Yes, display-only, attributed to Freehire; never used in matching, approval or routing | Decided; built (D93) |
| A job-level eligibility view, and its wording | The advisory component of D79: tri-state, side by side, no verdict | Decided |
| Should "possible duplicate" block preparation? | No: it warns; approval waits for "This is a different role" (D59) | Decided |
| The user move `submitted_unconfirmed → submitted_confirmed` | Kept, with at least 15 characters of what you checked, recorded as your statement (D53) | Decided |
| An outcome before any known submission | Refused with a reason code; record "I applied myself" first (D53) | Decided |
| Freehire credit on the list and export | Discover and job pages only; the source stays on each record | Decided |
| Who besides the owner may use AI drafting | Owner accounts only (single-owner deployment), each behind its disclosure consent (D74) | Decided |
| What is kept of a deleted account; a grace period | Nothing in the database; immediate; no grace period. Backups are the owner's own files (D77) | Decided |
| Standing approvals (auto-apply with caps) | Built (D113, D114, 2026-11-02): the owner chose "Fully automatic" within limits; superseded the earlier "not built" | Decided; built (row 32) |
| Follow-ups | In the app, derived, with a message to copy; nothing sent (D92) | Decided; built |
| Workday's terms and employers' Workday sites | Workday stays a manual handoff; a review of public terms would be mine, recorded as such, never the owner's acceptance. Corrected 2026-11-06: Workday's End User Agreement covers scoutrfp.com, not employers' career sites; the decision concerns each employer's own terms and consents and Workday's automation signals (`docs/research/workday.md`) | Decided |
| Live-pilot permissions 1-4 | Not given (D103 corrects D102, which wrongly said the owner's switch replaced them). Each is recorded separately, from the owner's own words, in `app/core/authorizations.py` (empty), and checked at every step; your approval of each package is needed as well; every other real destination stays refused | **External**: the owner's permission (row 26; `docs/activation-status.md`) |
| Inbox access for codes and replies | Built at the owner's request (D101). D117 (2026-11-02): the owner lifted "Do not: Read my inbox or retrieve OTPs" for verification codes ("read my email ... the most recent otp ... paste it in the greenhouse applications"); application emails stay unread. Manual code entry is unchanged | **External**: the owner's authorization (rows 31, 35; `docs/activation-status.md`) |
| Approval mode | Per application, by default (owner, 2026-10-31). The batch review is built (D105, `/review`): it approves individually identified, immutable packages, each on its own, never future applications; each approval stays bound to the user, application, destination, package version, scope, expiry and revocation, and is used once where that matters (D103) | Decided; built (D105) |
| Email reminders | To the owner only, opt-in after a verified address, a daily digest of categories with a safe link, off by default (D94) | Decided; built |
| A Claude key and daily budget | The owner's credential and spending decision | **External** (row 23) |
| Hosting, a domain, paid provisioning, public launch | Local-first; paid or public deployment only when the owner chooses to (designed, nothing provisioned or exposed) | Decided; provisioning **external** (row 40) |
| A real mail server for reminders | The owner's SMTP host and credentials, in `.env` | **External** (row 8, to send for real) |
| Which public job boards to read | Greenhouse and Lever public postings feeds, added and read one board at a time by the user; no crawl; no employer credentials (D95) | Decided; built (row 10a) |
| Ashby job boards | Not built until its public posting API documentation can be read | **External**: `developers.ashbyhq.com` blocked by this environment's network allowlist |

Kept as decided, not open: the bot-check stop (never narrowed; `implementation-plan.md`, "Owner
decisions"); every consent boundary in CLAUDE.md and D74.

## Documentation research limits (2026-10-29)

Public, unauthenticated documentation review for Lever, Workday and Ashby is approved. From this
cloud sandbox:

- **Read:** Lever's official GitHub repositories (`github.com/lever/postings-api` README in full,
  `github.com/lever/integrator-resources`).
- **Not reachable:** `hire.lever.co`, `help.lever.co`, `developers.ashbyhq.com` and
  `doc.workday.com` all failed DNS resolution (`ENOTFOUND`) on 2026-10-29 around 15:23-15:24 UTC.
  On 2026-10-30 (D95), `developers.greenhouse.io` and `developers.ashbyhq.com` failed the same
  way; Greenhouse's Job Board API pages were read from Greenhouse's own documentation repository
  (`github.com/grnhse/greenhouse-api-docs`) instead (`docs/research/job-board-apis.md`).
  This is the environment's network allowlist, not the vendors. Not attempted after that:
  `docs.ashbyhq.com`, `community.workday.com`, `developer.workday.com` and the vendors' legal
  pages.
- **Remedy (the owner's, in the environment settings):** add those hosts under Network access,
  Allowed domains (https://code.claude.com/docs/en/cloud-environments#network-access).

Facts about Workday and Ashby in `docs/research/` come from search-result summaries, labelled
"search-reported". They are leads to confirm, not evidence, and they do not count as a
`public_doc_reviewed` record.
