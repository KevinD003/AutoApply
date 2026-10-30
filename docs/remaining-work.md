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
| 6 | Browser extension (capture only) | **Unfinished**: not started | — | Real-page form capture is refused today (409); the extension would need it | Yes, before it captures a real page | Specify a capture-only contract (send URL and page to the user's own NoEfforts; never fill) |
| 7 | Mobile | Responsive web only, fixture-tested at 390×844 (`mobile` project). **Unfinished**: no native app, no installable PWA | Playwright `mobile` project | — | No | PWA manifest and a read-only offline view, then decide on native apps |
| 8 | Messaging (notifications: email, push, chat) | **Partial**: an in-app feed (D83) of verification requests, approvals that stop applying, rehearsals, receipts and stops, with read/unread, derived from the records; nothing is sent to the user outside the web app | `test_notifications.py`, `notifications.spec.ts` | Consent, and a sending provider for anything outside the app | Yes for outside providers | None without a decision on outside delivery |
| **Find** | | | | | | |
| 9 | Manual jobs, CSV/XLSX import/export, dedupe, exclusions | Fixture-tested | `test_jobs.py`, `phase-a.spec.ts` | — | No | — |
| 10 | Freehire discovery (documented API, fixture) | Fixture-tested | `test_freehire_discovery.py`, `discovery.spec.ts`, `journey.spec.ts` | — | No | — |
| 11 | Live Freehire read and watched searches | **Awaiting access or consent**: implemented (D55, D56), never run | `test_freehire_live_read.py`, `test_freehire_watch.py` | The owner's run approval; network access to `freehire.me` (this sandbox denies it) | Yes | Owner records an approval and runs it where `freehire.me` is reachable |
| 12 | Freehire `reality` signals (repost, evergreen) | **Unfinished**: not read, by an open owner decision (below) | `test_undocumented_fields_are_not_read` | Owner decision 1 | Yes (decision) | — |
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
| 24 | Importing the owner's ~4,000 old saved answers | **Awaiting access or consent**: a read-only analyzer is ready outside the repository; nothing imported | analyzer tested on synthetic files only | The file, in this environment; the owner's approval of the report and the mapping | Yes | Run the analyzer when the file is supplied; no import before approval |
| **Apply** | | | | | | |
| 25 | Package approval, rehearsal, separate submission approval, submission, receipt | Fixture-tested | `test_execution_*`, `submission.spec.ts`, `journey.spec.ts` | — | No | — |
| 26 | Greenhouse-style adapters | Fixture-tested; real pages read-only only (above) | `test_greenhouse_*.py`, `docs/greenhouse-compatibility-report.md` | Live-pilot permissions 1-4 and a Greenhouse terms review (below) | Yes | — |
| 27 | Lever | **Fixture-tested (local approximation only)**, D85: `fixture_lever` reads a Lever-style posting's form page on the local receiver, fills only approved facts and answers, uploads documents (evidence kept after a partial failure), reads back (a field a parsed resume changed stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. It has **no Lever identity**: a real Lever job stays a manual handoff (`planned_adapter_only`) and the `lever` specification stays `planned`. Not a provider adapter for real Lever pages: nothing was observed on one. Public docs: the Postings API README read; help centre, Data API docs and terms not reachable from this sandbox | `test_lever_adapter.py`, `lever.spec.ts`, `test_lever.py`, `test_lever_fixture.py`; `docs/research/lever.md` | Network access to `hire.lever.co`, `help.lever.co`, `www.lever.co/legal`; the owner's recorded review of Lever's public docs and terms (`public_doc_reviewed`); observing a real page needs the provider-admission approval | Network and approval | Owner: record a Lever docs-and-terms review, or leave Lever at `planned` |
| 28 | Workday | **Fixture-tested (local approximation only, checkpoint-first)**, D88: `fixture_workday` reads a Workday-style single-page application on the local receiver, fills only approved facts and answers, uploads files (evidence kept after a partial failure), reads back (a resume parse that fills a field you left blank stops it), rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. Candidate accounts and passwords, email verification, applications on several pages, values the page filled in itself, dependent location lists, pickers and custom dropdowns are all checkpoints, never automated. It has **no Workday identity**: a real Workday job stays a manual handoff (`planned_adapter_only`) and the `workday` specification stays `planned`. No Workday documentation page could be opened from this sandbox | `test_workday_adapter.py`, `workday.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/workday.md` | Network access to `doc.workday.com` and related hosts; an owner decision on Workday's terms (below) | Yes | Per-page disclosure accounting before several pages could ever be applied |
| 29 | Ashby | **Fixture-tested (local approximation only)**, D87: `fixture_ashby` reads an Ashby-style posting's application page on the local receiver, fills only approved facts and answers (Yes/No questions naming the country from your facts), uploads files (evidence kept after a partial failure), reads back (a field resume autofill changed stops it), never clicks the cookie banner, rehearses without submitting, submits once after its own approval and binds the confirmation to the attempt. The approximation's spam check is a hard stop everywhere: a checkpoint at capture, a stop before anything is entered, an unknown outcome after the final click (as are "already applied" and a confirmation that shows a challenge), never solved, retried or resent. It has **no Ashby identity**: a real Ashby job stays a manual handoff. URL recognition for hosted postings and `?ashby_jid=` embeds as before (D81). No Ashby documentation page could be opened from this sandbox, so every page detail is the fixture's own design | `test_ashby_adapter.py`, `ashby.spec.ts`, `test_workday_ashby_fixtures.py`; `docs/research/ashby.md` | Network access to `developers.ashbyhq.com`, `docs.ashbyhq.com`; an owner's docs-and-terms review before any Ashby specification | Network only | Confirm the shapes from the documentation |
| 30 | Verification codes | Fixture-tested by manual entry (checkpoint) | `test_execution_*`, `submission.spec.ts` | — | No | — |
| 31 | Gmail or inbox access (codes, replies) | **Awaiting access or consent**: not started (D10) | `docs/research/gmail-oauth.md` | A separately scoped inbox permission | Yes | — |
| 32 | Standing approvals (auto-apply with caps) | **Unfinished**: not started; every submission needs its own approval | — | An owner decision that it is wanted at all | Yes (decision) | — |
| 33 | Tsenta as a provider | **Awaiting access**: developer docs not accessible (D8) | `docs/research/tsenta.md` | Public developer docs reachable | Yes | — |
| **Track** | | | | | | |
| 34 | Tracker, timeline, outcomes with sources, funnel | Fixture-tested | `test_funnel.py`, `tracker-outcomes.spec.ts`, `journey.spec.ts` | — | No | — |
| 35 | Inbox classification of replies | **Unfinished**; would need row 31 | — | Row 31 | Yes | — |
| **Platform** | | | | | | |
| 36 | Docker Compose stack | **Awaiting deployment verification**: smoke-tested in CI (`docker-smoke`, `execution-compose`); the API has a health check and the worker and web app start only once it is healthy; secrets checked before start; owner's guide `docs/deployment.md`; **not run on the owner's Mac** | CI jobs, `test_deployment_config.py`, `scripts/check_env.py` | The owner's machine | Yes: run `./scripts/verify-local.sh` (section 9 of the guide) | Record the Mac result in `implementation-status.md` |
| 37 | Full data export | Fixture-tested: one ZIP of every record and document file, column by column; secrets and keyed material left out with reasons | `test_account.py`, `account.spec.ts` | — | No | — |
| 38 | Account deletion | Fixture-tested: everything that names the account, its files and sessions at once; refused while a submission may be in flight; queued work stops and is never retried | `test_account.py`, `account.spec.ts`, `docs/account-deletion.md` | The retention decision (below); the default keeps nothing | Policy only | — |
| 39 | Backups and restore (local stack) | **Awaiting deployment verification**: documented (`docs/deployment.md` sections 5 and 7: `pg_dump`, a storage archive, drop and restore); the CI smoke job runs the same commands on a throwaway stack; not run on the owner's machine; no scheduled or off-machine backup | `scripts/docker-smoke.sh` | The owner's machine; for scheduled or off-site backups, the hosting choice (row 40) | Yes (run it); hosting is the owner's choice | — |
| 40 | Production hosting (TLS, domain, secrets store) | **Unfinished** | — | Hosting choice and any paid commitment | Yes | — |
| 41 | Spend reporting | Partial: the drafting budget only (L4) | `test_drafting_provider.py` | — | No | — |

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

**Next product slices, picked from this table (no owner action needed):** row 7, an installable
web app with an offline page that keeps no personal data; then row 6's safe part, a browser
extension that saves the current tab's job address to your own NoEfforts and never reads or
fills the page.

## "Phase E", defined

`docs/product-evidence.md` assigns Phase **E** ("Expansion") to three rows, and nothing else:

1. **Row 1, monitoring many career pages:** NoEfforts' requirement is bounded, scheduled discovery
   from permitted feeds. It was delivered early as Freehire discovery: watched searches exist in
   code (D56) and have not run live (row 11 above).
2. **Row 2, broad ATS coverage:** claim only tested adapters. Greenhouse-style adapters exist
   (fixture-tested). Lever, Workday and Ashby are rows 27-29.
3. **Row 14, a dedicated inbox with classification and automatic status updates:** row 35, after
   inbox access (row 31).

The other planned surfaces (row 17: apps, extension, messaging, MCP) were given no phase beyond
"responsive web app first". They stay in scope as rows 3-8 above, not as completed work.

## Open owner decisions

Each decision is quoted from the document that raised it. None blocks the priorities A-D.

| Decision (quoted) | Source | Safe default now | Concrete effect | Blocks |
|---|---|---|---|---|
| "Whether to display Freehire's documented `reality` signals (display-only)" | `freehire-first-architecture.md` §12 item 3 | Not read and not shown | No "likely evergreen" or "reposted N times" hint on discovered jobs | Row 12 only |
| "Whether a job-level eligibility view is wanted, and its exact wording" | §12 item 4 | Priority D shows eligibility as its own advisory component, side by side and tri-state, with the §5.4 wording rules and no verdict | The wording of that component can be changed without changing what it computes | Nothing; the wording is a setting of D |
| "Whether 'possible duplicate' should block preparation or only warn" | §12 item 5 (D59) | Never blocks preparation; approval waits for "This is a different role" | One statement per possible duplicate before approving | Nothing |
| "A user move `submitted_unconfirmed → submitted_confirmed` requires stated evidence … (Alternative for the owner: remove the user move and route it through `/reconcile` only.)" | `implementation-plan.md` S2 change 1 (D53) | The user move stays, with at least 15 characters of what was checked, recorded as the user's statement | Confirmed-by-you and confirmed-by-receipt stay separate in the funnel | Nothing |
| "An outcome other than `withdrawn` on an application that never reached a submitted state is refused with a reason code (or flagged, owner decision)." | S2 change 4 (D53) | Refused | Record "I applied myself" first, then the outcome | Nothing |
| "Freehire credit … for the list and export (only if the owner decides it is required)" | `reliability-test-plan.md` R9.9 | Credit on the Discover and job pages only | Jobs list and export carry no Freehire credit | Nothing |
| Live-pilot permissions: "1. Read the public job post … 2. Open the application page … 3. Disclose … 4. Submit … A 'no' at any step stops there." | `live-pilot-gate.md` §2 | None given: real destinations refused in code | No real disclosure or submission | Row 26 live use |
| Who besides the owner may use AI drafting, with which consent wording | D74 | Owner accounts only | Others see "not available for this account" | Row 23 for others |
| Workday's end-user agreement reportedly bars automated access to "the Website" without consent; whether that covers employers' Workday career sites | `docs/research/workday.md` (search-reported, not opened) | Workday stays a manual handoff | No Workday automation beyond fixtures | Row 28 beyond fixtures |
| Whether anything about a deleted account is kept, for how long, and whether deletion can be undone within a grace period; how long backups are kept | Priority B (D77) | Nothing kept in the database (not even audit events); immediate, no grace period; backups are the owner's own files | One log line without any id or address is the only trace; a backup made before deletion still holds the account (`docs/account-deletion.md`) | Nothing; the decision is isolated in `account/policy.py` |

Kept as decided, not open: the bot-check stop (never narrowed; `implementation-plan.md`, "Owner
decisions"); every consent boundary in CLAUDE.md and D74.

## Documentation research limits (2026-10-29)

Public, unauthenticated documentation review for Lever, Workday and Ashby is approved. From this
cloud sandbox:

- **Read:** Lever's official GitHub repositories (`github.com/lever/postings-api` README in full,
  `github.com/lever/integrator-resources`).
- **Not reachable:** `hire.lever.co`, `help.lever.co`, `developers.ashbyhq.com` and
  `doc.workday.com` all failed DNS resolution (`ENOTFOUND`) on 2026-10-29 around 15:23-15:24 UTC.
  This is the environment's network allowlist, not the vendors. Not attempted after that:
  `docs.ashbyhq.com`, `community.workday.com`, `developer.workday.com` and the vendors' legal
  pages.
- **Remedy (the owner's, in the environment settings):** add those hosts under Network access,
  Allowed domains (https://code.claude.com/docs/en/cloud-environments#network-access).

Facts about Workday and Ashby in `docs/research/` come from search-result summaries, labelled
"search-reported". They are leads to confirm, not evidence, and they do not count as a
`public_doc_reviewed` record.
