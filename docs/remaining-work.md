# Remaining work: the canonical table (2026-10-29)

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
| 10 | Freehire discovery (documented API, fixture) | Fixture-tested | `test_freehire_discovery.py`, `discovery.spec.ts`, `journey.spec.ts` | — | No | — |
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
| 26 | Greenhouse-style adapters | Fixture-tested; real pages read-only only (above) | `test_greenhouse_*.py`, `docs/greenhouse-compatibility-report.md` | Live-pilot permissions 1-4 and a Greenhouse terms review (below) | Yes | — |
| 27 | Lever | **Fixture-tested (local approximation only)**, D85: `fixture_lever` reads a Lever-style posting's form page on the local receiver, fills only approved facts and answers, uploads documents (evidence kept after a partial failure), reads back (a field a parsed resume changed stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. It has **no Lever identity**: a real Lever job stays a manual handoff (`planned_adapter_only`) and the `lever` specification stays `planned`. Not a provider adapter for real Lever pages: nothing was observed on one. Public docs: the Postings API README read; help centre, Data API docs and terms not reachable from this sandbox | `test_lever_adapter.py`, `lever.spec.ts`, `test_lever.py`, `test_lever_fixture.py`; `docs/research/lever.md` | Network access to `hire.lever.co`, `help.lever.co`, `www.lever.co/legal`; the owner's recorded review of Lever's public docs and terms (`public_doc_reviewed`); observing a real page needs the provider-admission approval | Network and approval | Owner: record a Lever docs-and-terms review, or leave Lever at `planned` |
| 28 | Workday | **Fixture-tested (local approximation only, checkpoint-first)**, D88: `fixture_workday` reads a Workday-style single-page application on the local receiver, fills only approved facts and answers, uploads files (evidence kept after a partial failure), reads back (a resume parse that fills a field you left blank stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. Candidate accounts and passwords, email verification, applications on several pages, values the page filled in itself, dependent location lists, pickers and custom dropdowns are all checkpoints, never automated. It has **no Workday identity**: a real Workday job stays a manual handoff (`planned_adapter_only`) and the `workday` specification stays `planned`. No Workday documentation page could be opened from this sandbox | `test_workday_adapter.py`, `workday.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/workday.md` | Network access to `doc.workday.com` and related hosts; Workday's terms (the decision register below keeps it a manual handoff) | Yes | Per-page disclosure accounting before several pages could ever be applied |
| 29 | Ashby | **Fixture-tested (local approximation only)**, D87: `fixture_ashby` reads an Ashby-style posting's application page on the local receiver, fills only approved facts and answers (Yes/No questions naming the country from your facts), uploads files (evidence kept after a partial failure), reads back (a field resume autofill changed stops it), never clicks the cookie banner, rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. The approximation's spam check is a hard stop everywhere: a checkpoint at capture, a stop before anything is entered, an unknown outcome after the final click (as are "already applied" and a confirmation that shows a challenge), never solved, retried or resent. It has **no Ashby identity**: a real Ashby job stays a manual handoff. URL recognition for hosted postings and `?ashby_jid=` embeds as before (D81). No Ashby documentation page could be opened from this sandbox, so every page detail is the fixture's own design | `test_ashby_adapter.py`, `ashby.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/ashby.md` | Network access to `developers.ashbyhq.com`, `docs.ashbyhq.com`; an owner's docs-and-terms review before any Ashby specification | Network only | Confirm the shapes from the documentation |
| 30 | Verification codes | Fixture-tested by manual entry (checkpoint) | `test_execution_*`, `submission.spec.ts` | — | No | — |
| 31 | Gmail or inbox access (codes, replies) | **Disabled by design** (D10, D94): NoEfforts does not read an inbox or retrieve verification codes; you type codes in the app. Not an owner action | `docs/research/gmail-oauth.md` | — | No | None |
| 32 | Standing approvals (auto-apply with caps) | **Decided: not built** (D91): every submission needs its own approval, by the owner's standing default | — | — | No | None |
| 33 | Tsenta as a provider | **Awaiting access**: developer docs not accessible (D8) | `docs/research/tsenta.md` | Public developer docs reachable | Yes | — |
| **Track** | | | | | | |
| 34 | Tracker, timeline, outcomes with sources, funnel | Fixture-tested | `test_funnel.py`, `tracker-outcomes.spec.ts`, `journey.spec.ts` | — | No | — |
| 34a | Follow-ups | **Fixture-tested** (D92): due a set number of days (7 by default) after you applied, followed up, or recorded an interview or assessment, or on a day you choose; closed by an outcome; an in-app notification when due; a message to copy, never sent | `test_follow_ups.py`, `follow-ups.spec.ts` | — | No | Sending it by email only behind row 8's opt-in |
| 35 | Inbox classification of replies | **Deferred**: a separate optional integration, only if separately authorized; not bundled with outbound reminders | — | A separate authorization | Yes (only if wanted) | — |
| **Platform** | | | | | | |
| 36 | Docker Compose stack | **Awaiting deployment verification**: smoke-tested in CI (`docker-smoke`, `execution-compose`); the API has a health check and the worker and web app start only once it is healthy; secrets checked before start; owner's guide `docs/deployment.md`; **not run on the owner's Mac** | CI jobs, `test_deployment_config.py`, `scripts/check_env.py` | The owner's machine | Yes: run `./scripts/verify-local.sh` (section 9 of the guide) | Record the Mac result in `implementation-status.md` |
| 37 | Full data export | Fixture-tested: one ZIP of every record and document file, column by column; secrets and keyed material left out with reasons | `test_account.py`, `account.spec.ts` | — | No | — |
| 38 | Account deletion | Fixture-tested: everything that names the account, its files and sessions at once; refused while a submission may be in flight; queued work stops and is never retried | `test_account.py`, `account.spec.ts`, `docs/account-deletion.md` | The retention decision (below); the default keeps nothing | Policy only | — |
| 39 | Backups and restore (local stack) | **Awaiting deployment verification**: documented (`docs/deployment.md` sections 5 and 7: `pg_dump`, a storage archive, drop and restore); the CI smoke job runs the same commands on a throwaway stack; not run on the owner's machine; no scheduled or off-machine backup | `scripts/docker-smoke.sh` | The owner's machine; for scheduled or off-site backups, the hosting choice (row 40) | Yes (run it); hosting is the owner's choice | — |
| 40 | Production hosting (TLS, domain, secrets store) | **Unfinished** | — | Hosting choice and any paid commitment | Yes | — |
| 41 | Spend reporting | **Fixture-tested** (D97): Account → "AI drafting spend": the server's daily budget and reset, today's total and what is left, your requests, tokens and last 14 days, each amount marked estimated, worst case kept, held or nothing sent; an error reply keeps its worst case; each request settled once; exported with the budget settings. Not an invoice | `test_drafting_provider.py`, `drafting-spend.spec.ts` | — | No | Real provider usage only once the owner configures drafting (row 23) |

## Provider evidence ladder

Each rung is separate evidence; a lower rung never stands in for a higher one. "Fixture" means a
local synthetic page or service; nothing on this ladder implies live support.

| Provider | URL recognition | Synthetic form coverage | Provider-specific adapter | Observed real-page behaviour | Approved disclosure rehearsal (real) | Confirmed submission (real) |
|---|---|---|---|---|---|---|
| Greenhouse | Yes (hosted, embed `gh_jid`, `/embed/job_app`); gaps recorded (`identity_jid_any_host`, `identity_rules_disagree`) | Yes: receiver v1 and v2 forms, failure modes | Yes, against local fixtures only (`greenhouse_hosted`, `greenhouse_dom`) | Read-only only (above): job data and page read; dropdowns opened in two runs; never typed | None (needs live-pilot permission 3) | None (needs permission 4) |
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
only to send reminders for real (row 8). Inbox reading and code retrieval stay disabled (row 31),
and reply classification is deferred unless separately authorized (row 35).

## "Phase E", defined

`docs/product-evidence.md` assigns Phase **E** ("Expansion") to three rows, and nothing else:

1. **Row 1, monitoring many career pages:** NoEfforts' requirement is bounded, scheduled discovery
   from permitted feeds. It was delivered early as Freehire discovery: watched searches exist in
   code (D56) and have not run live (row 11 above). Employer job boards (row 10a, D95, D96) read
   an employer's public postings feed one board at a time, on request or once a day for the
   boards you choose, with a notice of new postings; never a crawl.
2. **Row 2, broad ATS coverage:** claim only tested adapters. Greenhouse-style adapters exist
   (fixture-tested). Lever, Workday and Ashby are rows 27-29.
3. **Row 14, a dedicated inbox with classification and automatic status updates:** row 35, after
   inbox access (row 31).

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
| Standing approvals (auto-apply with caps) | Not built: every submission needs its own approval (owner default) | Decided (row 32) |
| Follow-ups | In the app, derived, with a message to copy; nothing sent (D92) | Decided; built |
| Workday's terms and employers' Workday sites | Workday stays a manual handoff; a review of public terms would be mine, recorded as such, never the owner's acceptance | Decided |
| Live-pilot permissions 1-4 for one real employer | The owner's to give (`live-pilot-gate.md` §2); real destinations refused in code until then | **External** (row 26) |
| Inbox access for codes and replies | Inbox reading and automated code retrieval stay disabled; codes are typed in the app. Reply classification is a separate optional integration, deferred unless separately authorized | Decided (rows 31, 35) |
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
