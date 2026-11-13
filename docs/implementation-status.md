# Implementation status

Last updated: 2026-11-12 (D154: before the send gate, what the page itself would refuse at the final click (the browser's own validation of the form, fields the page marks as not valid, a submit button it keeps hidden or disabled) stops the attempt with nothing sent, read without acting on the page; after a page's answers, what they started is waited for before the checks; reviewed independently twice, one blocker fixed; stand-ins only. Before that, D153: the adapter judges a list by the page's record of changes to a list, which now also counts style sheets, the control's attributes, what names its list and ids, and no longer by changes anywhere on the page (the whole-document 150 ms check, which the survey's own classification keeps); a dropdown's option is chosen from one read of the list, which must still be the approved list, and its text is read again before the click; reviewed independently twice, two blockers fixed; stand-ins only. Before that, D152: the read-only survey publishes, for each list it opens, whether the list met the adapter's settle rule at its last read (no change to a list for half a second, all reads equal, nothing pending, observed sufficiently), and how many did; no verdict in path A's window, shorter than the adapter's; nothing a run does changes; the receiver's reset clears every setting of the stand-in; reviewed independently twice, the findings fixed; code only, no run. Before that, D151: a section's combobox (school, degree, discipline, the months of the education and employment rows) chooses only from a list that has settled, by the dropdown's own rule: the probe and its classification, requests recorded and refused as a dropdown's, three equal reads and half a second with no change to a list; it clicks the one shown option reading the approved text, after reading the whole list again in one go; a list that keeps changing, posts or fails to load stops the section before its control is entered; reviewed independently twice, the findings fixed; local stand-ins only. Before that, D150: a request to stop the worker (`docker compose stop`, an upgrade, Ctrl-C) is honoured before the next protected step: the worker's processes share a flag Celery's shutdown sets, read before the claim, between steps, inside each gate and in the code wait; before anything is entered the attempt goes back in the queue, after it is abandoned and never retried, and past the send gate the click is completed and its outcome read; the worker is stopped before the browser runner and the egress proxy, with 150 seconds for a click's answer; reviewed independently twice, the findings fixed; local only. Before that, D149: on the Workday-style stand-in, the Work Experience section on My Experience is filled from your approved work history, entry by entry, on its own page: an entry added only by the section's own button, each control typed exactly as approved and read back, and before the page's Next no entry beyond the approved ones and nothing left empty that the page requires; anything about work history NoEfforts cannot fill exactly is one checkpoint, and what is known before anything is entered stops there, with nothing at the employer; a required section waits for your approved work history; reviewed independently twice, the findings fixed; local only. Before that, 2026-11-11 (D148: on the Workday-style stand-in, a question the page shows only after an earlier answer, hidden inside its page when the form is read, is answered only by you or an approved profile fact and entered only when the page shows it, never waited for; after filling, what the page shows must be what was entered: a shown one it requires with no answer pauses a single page and stops a wizard page before its Next, and a hidden one it still requires, or one it removed, stops the attempt; reviewed independently twice, the findings fixed; local only. Before that, 2026-11-11 (D147: a database restored from a backup comes up held: it carries a stamp of its own identity (its oid and its server's cluster identifier), and until the scheduler has dealt with a restore nothing is taken, queued or applied to; then everything the backup shows as queued or in progress is ended without being run, every approval retired, every standing rule paused and every account told; a restore into the same database or a copy of the server's files is not recognized (`restore-resolve --force`); reviewed independently twice, the findings fixed; local only. Before that, 2026-11-11 (D146: an application still queued five minutes after its message went out is published again, every five minutes while it waits, so it no longer stays queued for good when the broker loses its message or a worker process dies before taking it; the claim itself refuses an attempt that entered data, and a second message ends there; after a database restore this would run again what the backup shows as queued, so the deployment guide's restore has a step for it until rank 20 is built; reviewed independently; local only. Before that, 2026-11-11 (D145: a dropdown's list counts as settled only when, besides three identical reads, the page itself has recorded no change to a list for half a second, so a list that keeps being re-rendered is refused however slowly a busy machine reads it, while changes elsewhere on the page do not count; the location search's suggestions follow the same record; found by D143's regression run under load and reproduced without it; reviewed independently, rebuilt on a narrower record and reviewed again before its pull request; local only. Before that, 2026-11-10 (D144: attempts on a queue and a worker of their own: an attempt may keep its worker for the whole wait for a verification code, so its task has its own queue and, in the Compose stack, its own worker with one process for the one browser; the schedule and every periodic task run on a second worker, which holds no runner token and no control socket; measured first: one shared worker with both processes waiting for codes did not take a periodic task until a code was entered; the Compose layout itself runs only in CI; local only. Before that, 2026-11-10 (D143: recovery hardening: the runner bounds its own run with a budget it checks between steps, an attempt's task has one time limit that covers the whole wait for a verification code and no soft limit (a real-worker run showed one that lands inside a browser wait is never handled), a lease follows progress and covers each wait for the employer's answer, a verification request ends with its attempt, and a worker killed on the Greenhouse-style and Workday-style stand-ins is never run again once data was entered; reviewed independently before its pull request, the seven findings fixed; local only. Before that, 2026-11-10 (D142: a Workday-style multi-page wizard stand-in, filled forward only: a gate that commits before every page's fill and Next, each page read back before its Next, anything unexpected after disclosure ends the attempt for good (a Next that may have submitted is quarantined in submitted_unconfirmed), and NoEfforts never runs that application again; adapter version fixture-workday-2; local only. Before that, 2026-11-10 (D141: an employment stand-in, and section comboboxes filled as D109 fills a dropdown: never typed into, their own list only, the frozen id, a react-select choice read back from its single value; every section control read back before the send gate; EXTRACTION_VERSION greenhouse-dom-v6 retires greenhouse_dom and greenhouse_live approvals once; local only. Before that, 2026-11-10 (D140: the education and work history a package sends are shown on the review page as frozen in it and diffed by record and field, the history names a section change instead of "metadata changed", and an education or employment edit retires the approvals it affects at once; shown on the education stand-in's receiver ledger; local only. Before that, 2026-11-10 (D139: your self-identification on Greenhouse- and Workday-shaped forms, shown up to the employer: what you opt into is sent, a decline sends the form's own decline only where the other choices name a category, a question it cannot tell apart is left blank, your per-application "Don't disclose" beats it, and turning it off or changing it retires the approvals of what it answered at once (the profile page says how many), so nothing you withdrew is sent, also while queued, while a worker holds the attempt and under the standing rule; local only. Before that, 2026-11-10 (D138: saved answers on Greenhouse- and Workday-shaped forms, shown up to the employer: an answer saved on one job is reused on the next job that asks the same question and the employer receives it; a look-alike that names a country is neither reused nor suggested, and nothing is approved or sent until it is answered; on the Workday-style form a shift is never saved or reused; editing a saved answer retires the approval that used it until it is approved again; tests and fixtures only, no product code changed; local only. Before that, 2026-11-10 (D137: what reached the employer stays recorded whatever fails after it: each disclosure is recorded the moment it is made, fenced by generation, so an unexpected error or a killed worker after an upload keeps the record that the résumé reached the employer, and a failure during an upload records the document as possibly received, on a page and through the API; attempts that disclosed anything are still abandoned and never retried; local only. Before that, 2026-11-10 (D136: on Greenhouse's id-only pages a control NoEfforts cannot fill (a native dropdown, a checkbox, a list of several choices) is refused when the form is read: a required one means applying on the employer's site, an optional one is left blank and the rest is sent; before, a native dropdown stopped every attempt as a form change and the others were refused only after you approved; local only. Before that, 2026-11-09 (D135: on Greenhouse's id-only pages, a typed question the page shows only after an earlier answer is yours to answer, never from a saved answer or a draft, and entered only if the page shows it; a shown one the page requires, unanswered, pauses the application after filling with nothing submitted, listed under Questions, and once answered and tried again one new attempt sends it; a choice or upload hidden at load is still never filled; local only. Before that, 2026-11-09 (D134: your pause and your revocation reach what the standing rule already queued: pausing cancels the attempts it queued that have not started sending (one a worker holds stops at its next step), counts one being sent and retires the approvals it gave; a worker refuses an attempt the rule queued while the rule is switched off or paused; after you revoke an approval the rule never approves that application again; what you queued yourself and approvals you gave are never touched; the Tracker says what a pause stopped; local only. Before that, 2026-11-06 (D133: reuse and suggestion guards: a saved answer is suggested only when the question it was given to is still reused and it fits the field; word-level vetoes over label and help text; a rule floor under the model; "Use here only"; the "wish to self-identify" declines; a screening job counted by the receiver; an error boundary. Before that, 2026-11-06 (D132: a form that no longer matches before anything is entered pauses the application: every live approval is retired and nothing is approved until the form is read again or you choose to try the same version again; Questions needing your answer lists what each application waits for; the standing rule never continues a paused application; local only). Before that, 2026-11-06 (D131: answer safety: your saved self-identification answers only the EEO self-identification categories and only with options that name their category, never a criminal-history, accommodation or other sensitive question; a follow-up's saved answer is reused only after the question it followed; job requirements are never reused; the review page no longer fails on a self-identified answer; its follow-up: job requirements in more wordings are never reused while your own skills stay reusable, the documents that let you work and vaccinations in any wording are never saved, and self-identification labels are one per line; local only; earlier, 2026-11-05: D129/D130: the section-free Greenhouse path, a locked identity verified and an optional phone left blank beside a control NoEfforts cannot set, on unmerged branches with exact local results — see its section; earlier, 2026-11-02: D115: the answer brain suggests your own saved answers for reworded questions, you choose, and each choice trains your own LightGBM/XGBoost model; D116: Greenhouse real-page mechanics rebuilt from the legacy bot (security code, formless submit bound to the job page, uploads acknowledged by file name, confirmation page), local only; D117: verification codes read from the owner's own mailbox, recorded from the owner's words, codes only; D113: Freehire discovery, the Greenhouse pilot switch and the owner's standing rule to apply automatically are on by default outside tests; the owner's own Discover search is the Freehire run approval and is re-checked daily; the rule applies only to fully answered Greenhouse packages, rehearsal first per employer, at most 5 a day, within the recorded permission, never retrying a stopped attempt, pausable on the Tracker; D112: the owner's permission for the Greenhouse pilot is recorded from their own words: all four steps until 2026-11-06, at most 5 attempts past the disclosure gate, each application still approved in the app; the limit is enforced under one lock; tests never run under it; `verify-local.sh --pilot` checks the pilot's settings and overlay; readiness 1 of 7 (condition 6); nothing real run from here; D111: the pilot's narrow locale exception is integrated after review, with two protections path C had added (a followed redirect of a locale request stops the attempt; such requests are capped per session at 150); run #11 is recorded as not compliant with the approved stop on any non-GET request (a page-load POST was blocked but did not stop it), with dated corrections that keep the approval as given; that stop is now enforced at page load and between actions, tested against an independent listener; a search input the page hides inside a question's group is no longer turned into an unanswered question, only while the live page shows it hidden, unrequired and empty; u1, u3 and location stay blocking, each gap named; an in-app milestone-B handoff per application; still 0 of 7; nothing real run; D110: read-only run C (run #11) completed: once the page's two locale files loaded, all 12 real dropdowns opened at a plain click and the 7 mapped ones showed exactly their job-data options; the pilot's matching locale exception is prepared on a branch, not merged; milestone B needs a posting without the two unmapped required dropdowns and the location this one has; still 0 of 7; D109: Greenhouse first: a dropdown choice on react-select markup is now read back from its displayed value (the earlier readback of the input would have abandoned a real react-select form), a react-select container click is a dropdown strategy, and read-only path C is built to test whether the real dropdowns open once their locale files load, not approved; D108: any request a dropdown sends while opening stops the attempt, and widget observations are kept apart; D107: read-only path B ran once, as run #10, with the owner's single-use approval: a policy stop; the exact rule allowed none of the real locale files, so whether the dropdowns wait on them is still untested; the summary now names which properties of a refused locale path failed; no further run approved; still 0 of 7; D106: the activation checklist is computed for the pilot adapter, the only one whose real evidence could ever be recorded; the owner's permissions are read from one register; each of the seven conditions says what it needs and the smallest next step; still 0 of 7; read-only path B (the locale exception) built and tested, not run; one owner handoff in docs/activation-status.md; D105: a Review page lists the packages you can approve and approves the ones you tick, each on its own, for the version and content hash shown and the scope you chose; a changed package is refused, nothing is queued or sent, and nothing approves future applications; D104: on the local Greenhouse-style stand-in only, a phone country picker chosen by a unique calling code or by you, a location search typed after the disclosure gate with the exact suggestion and the page's own coordinates, and dropdown lists that arrive late accepted within a bounded wait once settled and exact; every real page unchanged, synthetic coverage no evidence for one, `SCHEMA_VERSION` 3; D103: built is not authorized: reading the owner's Gmail, entering a code from it and each of the Greenhouse pilot's steps (read, open, disclose, submit) now also need the owner's recorded authorization, which no setting can supply; none exists, so with every switch on nothing is read, opened or sent; a code you type yourself works as before; a "received" email settles an unknown submission only when it names the role too, arrived after the final click and is the only one proposed; the backend suite runs only on a disposable database of its own, claimed for the run, with its ports and Redis database held, so two runs can no longer reset each other's database; D102: the Greenhouse pilot, built and off: once the owner switches it on, real Greenhouse job posts are read and applied to through `greenhouse_live`, each application approved, the first to each employer a rehearsal that never submits, never yet run on a real page; Greenhouse's public terms reviewed; D101: your own Gmail, read-only and off until you connect it: verification codes entered for a waiting step when exactly one arrives, application emails proposed as outcomes you confirm; D100: Discover keeps and lists listings by application platform, read from each listing's address; D99: saved answers can be imported from a JSON or CSV file, checked by the saved-answer rules and added as proposals you approve one by one; D98: religion, tax, prohibited-person and other sensitive questions, work status, residence-state and export-control questions, licences and address parts found in the owner's archive of real questions are no longer saved as reusable answers; earlier: D97: a form's page is used as soon as its own requests are done, and a page still loading after 8 seconds stops the attempt before anything is entered; Account shows what AI drafting used against the daily budget, each amount marked estimated, worst case kept, held or nothing sent, never as an invoice; an error reply from the provider keeps its worst case and each request is settled once; earlier: execution: the runner lets a page finish its own loading, at most 8 seconds, before reading or touching the form, so a control wired up after the page's own requests is not missed on a busy machine (CI #133); earlier: discovery: a daily check of a job board you choose: tick "Check daily" and the worker reads it once a day through the same boundary; new postings become one in-app notice per board per day, never a job and never an email, D96; earlier: discovery: employer job boards: add a Greenhouse or Lever board by its identifier and read its public postings when you choose; GET only to the provider's fixed host, nothing of yours sent; only a complete read says a posting is no longer listed; saving one adds it to your jobs; Ashby not built (documentation unreachable); no real board read, D95; deployment: Compose now passes the owner's settings from `.env` to the API and worker, which it did not for email, discovery or drafting; earlier: email: opt-in daily email reminders to the account owner only, after a verified address; category and a safe link only; uncertain sends never repeated, D94; earlier: discovery: what Freehire says about a posting (age, reposts, its class) shown display-only, never an input, D93; earlier: follow-ups: a submitted application reminds you in the app to follow up 7 days after you applied, followed up, or recorded an interview or assessment, or on a day you choose; closed by an outcome; a message to copy, never sent, D92; decisions: the open questions resolved in one decision register, external permissions isolated, D91; earlier: extension: a capture-only browser extension saves the current tab's address and title to your own NoEfforts with an `import:jobs`-only token, never the session cookie, never reading or filling a page, D90; web app: NoEfforts installs as a web app, and offline shows a static page that keeps nothing about you, D89; earlier: Workday: a Workday-style adapter, checkpoint-first, fills, rehearses and submits a single-page application on the local approximation only; accounts, verification, several pages, prefill and complex location fields are checkpoints; no Workday identity, D88; earlier: Ashby: an Ashby-style adapter fills, rehearses and submits the local Ashby-style approximation only, with its spam check a hard stop everywhere; it has no Ashby identity, so a real Ashby job stays a manual handoff, D87; earlier: fixture-origin boundary: fixture origins honoured only in the test environment, names only if listed exactly, and every connection to one, server-side and through the egress proxy, must reach loopback or the configured test network; in `netns` mode the driver no longer fetches page loads outside the proxy, D86; earlier: Lever: a Lever-style adapter fills, rehearses and submits the local Lever-style approximation only; it has no Lever identity, so a real Lever job stays a manual handoff, and a public site listed as a fixture origin is never one, D85; earlier: API tokens: personal access tokens, hashed, shown once, expiring and revocable, scoped `read` or `import:jobs` with default deny, and a standard-library CLI and MCP server over them; nothing reaches review, consent, approval or submission, nothing exposed beyond this machine, D84; earlier: notifications: an in-app feed of verification requests, approvals that stop applying, rehearsals, receipts and stops, read and unread per account, derived from the records, nothing sent outside the app, D83; earlier: jobs: each jobs-list row summarises its match explanation (preferences counted, approved skills and licences named, unknowns counted) and links to it; no score, D82; earlier: providers: Workday- and Ashby-shaped forms, Ashby embeds recognised fail-closed, passwords and custom widgets never filled or dropped, a provider evidence ladder; the owner's Mac runbook with a summary safe to share, Mac still unverified, D81; earlier: providers: a Lever-shaped form, checkpoint-first; the generic extractor never types into a search-as-you-type picker and stops at a bot check, D80; earlier: account: a full export of your data and account deletion that takes effect at once, refused while a submission may be in flight, with the retention decision isolated, D77; saved answers edited as versions with their history, a document's text previewed as plain text, profile records edited in place, D78; the job page explains a match by preferences, eligibility side by side and qualifications, never as a probability, D79; earlier: deployment: an API health check gates the worker and web app, secrets are checked before start, and an owner's guide covers start, health, backup, upgrade, rollback and a safe verification run; backup and restore run in the CI smoke job; not run on the owner's Mac, D76; earlier: scope: one canonical remaining-work table, `docs/remaining-work.md`; one synthetic journey through the whole product, desktop and mobile, which found and fixed three broken transitions, D75; earlier: drafting: Claude can write drafts, tailored resumes and cover letters, built and off: only for the owner's account, only after you agree in your profile to the exact text of what is sent and to whom, and only within a daily budget reserved before each request; no key, no request made, D74; earlier: security: the owner-run read-only Greenhouse check now checks that its API host resolves to public addresses only before every request, so every server-side fetch of a real host is checked, R10.5; earlier: documents: a resume's work history, education and licences are proposed into your profile and used only once approved, D72; tailored resumes and cover letters are built to be generated only through a drafting provider, none configured, so none is generated, D73; preparation: SCHEMA_VERSION 3, which invalidates every earlier approval: preference facts hashed by value, document provenance and `accept` enforced, an answer awaiting consent never kept in a version, D71; documents can be deleted, one version or all, never while an approval or a submission needs them, D70; a draft names a licence only from an approved, unexpired credential, and licence answers are never saved for reuse, D69; drafts take numbers only from the facts they cite, never state a legal status or a sensitive attribute, quote job text as untrusted data, and are accepted only if nothing they were made from changed, D68; earlier: discovery: Freehire counters no longer count as changes, a source's Retry-After holds back your next request, each listing can be refreshed, D67; preparation: the review page shows what changed between versions, D66; every refusal to approve, queue or revoke has a reason code, and revoking stops a queued submission at once, D65; answers can be changed, cleared and added on the review page where your input is allowed, with a cover-letter choice and where the form sends, D64; a salary is sent only in the units the question allows, D63; execution: fixture variants for the legacy page traps, and every confirmation bound to its own attempt, D62; earlier: preparation: a sensitive answer reaches the employer only as you chose, shown by the receiver's ledger; "Don't disclose" on a required question sends the form's one decline option, D61; an answer or a choice applies only to the question as shown, and "Include this answer" only to the answer shown, D60; jobs: a posting its source says is closed, a job you excluded or closed, and a role that looks like one you already have an application for wait for your statement before approval, D59; earlier: preparation: a LinkedIn or website question gets the profile's link only when exactly one is of its kind, read from the host, D58; earlier: a State list naming every US state gets the profile's state; a City list is never picked from the profile; any other State, City or Country list is your answer for this application, never saved, D57; earlier: discovery: watched Freehire searches for the owner, checked as often as once a minute, and a delete for discovered postings that keeps them deleted, D56; a live Freehire read for the owner, one approved run at a time, D55; none made, the cloud sandbox refuses freehire.me; earlier: preparation: the legacy collision corpus (244 wording traps) is a permanent test; someone else's details, preferences read as residence, residence and nationality in other words, any relocation question but the plain one, a negated right to work, agree/decline options under a neutral label and facts that do not fit their field are checkpoints; static guards refuse a mailbox client and page capture; earlier: tracking: a submission says what it rests on (an employer receipt, your statement, or nothing known), a confirmation by you needs what you checked, outcomes are dated, sourced and audited, assessment received exists, an outcome before any known submission is refused, events are insert-only in the database, and a per-user funnel counts with denominators and no rate; earlier: documentation: the Freehire-first review published, with the Freehire re-check of 2026-10-26, an amendment to D34 and D52; earlier: preparation: a saved answer is reused only where it stays true, bound to its help text, never for answers that depend on the employer, the job or the date, and saves and deletes never fail; execution: an unknown outcome in the verification-code step reaches `submitted_unconfirmed` again, and the sweeper recovers each stale attempt in its own savepoint; earlier: preparation: a statement of a profile fact is checked only with agree and a true approved fact, eligibility misreads and legal-status questions become checkpoints, sensitive topics found in wording, help text, options, sections and follow-ups are never saved, reused or drafted; earlier: only resolved answers are sent, a stale accepted draft is a checkpoint, a document question that is not asked attaches nothing, the package shape pinned, cross-tenant and repository-hygiene guards; earlier: a provider-admission framework: each provider's stage computed from code and recorded evidence, claims bounded by it, owner stops and a cap; a manual-handoff approval and a reconciled-as-not-received approval can no longer send; one lock order for every execution path, gates reading what is committed after their locks, deterministic race tests; a recorded, valid rehearsal is required before the first submission through each employer/provider path, at five layers, fixtures only; the rehearsal stop is a gate and writes a rehearsal record; readiness counts the caller's recorded evidence by class; each gate locks the approval row, so a revocation committed while it waits is refused; upload evidence kept as a digest and a fixed acknowledgement, also for failed uploads; rehearsal results on the review page and tracker; rehearsal: an approval to disclose only, which stops before the send gate; Lever as a planned provider; location design without hidden coordinates; page controls the job data does not list become checkpoints at capture; Greenhouse pilot readiness computed from evidence and the Path A record format; real-destination jobs get the truthful route before any form step; question keys moved out of URL paths; support-state wording derived from evidence and served from one place; route reason-code contract, discovery route explanations, route-audit deduplication and the provider on the route card; earlier: privacy and audit hardening, legacy audit repair, baseline corrections and a documentation-consistency pass; nothing supported for real use; no external request, credential, permission or live-status change). For requirement-by-requirement evidence see
`docs/evidence-matrix.md`. Labels: **complete**, **partial**, **blocked**, **not started**,
**untested**.

## Premium UX pass (Slices A–D)

A focused product-layout and interaction pass over the JavaScript frontend (not a rewrite).
The JS/JSX migration is complete; this pass makes the experience jobs-first and mobile-first.

| Slice | Scope | Status |
|---|---|---|
| A | Navigation/layout defect investigation (real browser defect vs full-page screenshot artifact), with a maintained layout regression guard | in progress — the two reported nav defects (bottom nav over the import card; header mid-Profile) are **full-page screenshot artifacts**, verified with ordinary viewport captures at top/middle/bottom on both viewports; no production layout change (`docs/ux-layout-investigation.md`, `frontend/e2e/layout-regression.spec.ts`) |
| B | Jobs-first list/swipe/detail: heading → search/filters + prominent List/Swipe → jobs/swipe → secondary Add/Import in sheets; premium cards with available salary/work-arrangement/description from the backend; representative synthetic fixtures | not started |
| C | Profile & Account restructuring (section nav, summaries, expand-to-edit; grouped settings) | not started |
| D | Maintained theme (real toggle)/motion/layout coverage + swipe/motion polish | not started |

Verified facts, not invented: the list API (`JobOut`) carries title/employer/location/status/
match; the detail API (`JobDetail.content`) carries salary-with-provenance, the source facts
and the sanitized description. Slice B surfaces the available detail fields on cards through a
compact summary built from the same consolidation, so list and detail never disagree.

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

## Every other adapter stops at a value its box would cut, naming the limit, and types only into a box that has focus (D162, 2026-11-13; local only)

Rank 29 of the automation loop (D161's "Not built"). Product changes:

- `app/modules/execution/adapters/fixture_ats.py`: `_type` for a text, a number and a date;
  `_cut_at_focus` reads the limit once the box has focus for certain (`limit_at_focus`);
  `LimitStopped` and `LIMIT_AT_FOCUS` (moved from the pilot's adapter), `FocusStopped`,
  `FOCUS_LOST`, `SECTION_LIMIT_AT_FOCUS`, `section_not_typed`; `_limits_fit` reads the live limit
  as the browser does; the stop at a box carries the uploads made before it (`fill`).
- `app/modules/preparation/forms.py`: `LIVE_LIMIT_JS` and `LIMITED_INPUTS` (moved from the
  pilot's capture, `preparation/greenhouse_dom.py`, which imports them).
- `app/modules/execution/adapters/greenhouse_sections.py`: `check_at_focus` and `NotTyped`, before
  each entry's box is typed; a box refused before typing is not recorded as entered.
- `app/modules/execution/adapters/workday_sections.py`: `_give` uses `check_at_focus`; `apply`
  records no box refused before typing.
- `app/modules/execution/adapters/workday.py`, `greenhouse_dom.py`: a refused entry is the stop
  that names it (`section_not_typed`); `hosted_form.py`, `greenhouse.py`, `workday.py` and
  `greenhouse_dom.py`: the stop at a box carries the uploads made before it.
- The stand-ins: `fixtures/ats_receiver/greenhouse_like.py` (`gh_limit_on_focus`),
  `workday_like.py` (`wd_limit_on_focus`; `receiver.py` resets it).

No migration, no new state, reason code or gate. `SCHEMA_VERSION` stays 3, and so do
`EXTRACTION_VERSION` and the adapter versions (D162 says why). Nothing was run against a real
page. `scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `base-limits`, from D161's branch at a6bea08) | Command | Result |
|---|---|---|
| The first version's tests | `test_limit_stops.py` (JUnit) on fc4caf3; the suites the change touches; ruff | on the working tree: four suites the change touches first (`test_pilot_limits.py`, `test_sent_as_approved.py`, `test_workday_entry_limits.py`, `test_question_limits.py`): exit 0, 315 passed; `test_limit_stops.py` twice: exit 0, 17 passed; on fc4caf3, the suites the change touches, 87 files in two runs: exit 0, 1661 and 1810 passed; ruff clean |
| Two independent reviews | on fc4caf3 | no blocker; both: a work entry's stop named no limit and gave a false reason, the box recorded as entered though nothing was typed; the second: the limit read "at focus" without the box having it (a value typed cut or into another box); the first: a number unchecked; see D162 |
| After the reviews | `test_limit_stops.py` (JUnit) on the working tree as the fixes grew; 12 suites the fixes touch (`test_workday_entry_limits.py`, `test_workday_experience.py`, `test_greenhouse_sections_e2e.py`, `test_greenhouse_sections_hardening.py`, `test_pilot_limits.py`, `test_sent_as_approved.py`, `test_outside_controls.py`, `test_workday_wizard.py`, `test_workday_entry_details.py`, `test_workday_follow_up.py`, `test_section_widgets.py`, `test_question_limits.py`) on the working tree; on a52cc10, the 22 touched suites the regression set does not run; ruff | exit 1 (2 failed: the two Workday-style runner tests started their browser while the module's own was open; moved before those tests), then exit 0: 29, 36, 40 and 43 passed; the 12 suites: exit 1, 762 passed and 1 failed (D149's browser-error test: a box disabled before typing is now refused, not recorded; split in two, both pass); on a52cc10, the 22 suites: exit 0, 1083 passed; ruff clean |
| Each part changed in turn | 25 changes on a52cc10, one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 25 fail the tests named for their part (52 of the 72 named tests, over the runs); each file restored, the tree clean after. Nothing left out: the uploads a stop carries are observed by calling each adapter's own `fill` |
| The regression set | `pytest` on 89 files (D161's 88 with `test_limit_stops.py`; JUnit), in a copy of the branch at a52cc10 | exit 0, 2840 passed (87 minutes) |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_limit_stops.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 88 passed in 75 s; ruff formatted nothing, found nothing, and the format check passed |
| After the pull request was opened | `test_greenhouse_sections_browser.py` among D163's related suites on d8d4abe (D162 unchanged in it); after the fix (`NotChosen`), the Greenhouse section suites, `test_section_widgets.py`, `test_section_list_settle.py`, `test_limit_stops.py` and `test_pilot_limits.py` (9 files, JUnit); ruff | exit 1: 1 failed (a pilot's education list recorded as entered when none of its options was chosen; D162 says why); then exit 0, 254 passed; ruff clean |

## The Greenhouse pilot holds an answer to the length limit its page shows (D161, 2026-11-13; local only)

Rank 28 of the automation loop (D158's and D159's limit for the pilot). Product changes:

- `app/modules/preparation/greenhouse_dom.py`: `Control.maxlength` and `Control.limited`
  (`snapshot`), `limits_typing`, `_locked`, `_page_filled`, `control_limit`, `LIVE_LIMIT_JS`;
  `build_schema` records a typed question's limit as its `max_length`.
- `app/modules/execution/adapters/greenhouse_dom.py`: `_limits_fit` last in `schema_matches`
  (before anything is entered, and after filling); `_cut_at_focus` before each value is typed
  (`fill`, `_fill_shown_by_page`), `LimitStopped` and `LIMIT_AT_FOCUS`.
- `app/modules/execution/adapters/fixture_ats.py`: `limits_verdict`, D159's verdict, shared.
- `app/modules/preparation/gh_readonly.py`: each typed question's `length_limit` in
  `mapping_evidence` (`_length_limit`, `_served_limits`, `_served_html`); three words added to
  the published vocabulary; `docs/greenhouse-readonly-compatibility-proposal.md` documents them.
- The stand-in (`fixtures/ats_receiver/greenhouse_v2.py`: the `gh2_` limit, lock, type,
  autosave and byte settings and the autosave route; `receiver.py` resets them).

No migration, no new state, reason code or gate. `SCHEMA_VERSION` stays 3, and so do
`EXTRACTION_VERSION` (greenhouse-dom-v6) and the adapter versions (D161 says why). Nothing was
run against a real page. `scripts/validate.sh all` was not run (it runs the whole backend and
e2e suites); ruff was.

| Check (branch `pilot-limits`, from D160's branch at 9838d26) | Command | Result |
|---|---|---|
| The first version's tests | the capture's tests (`pytest tests/test_pilot_limits.py -k ...`, JUnit) on the working tree before 566cf9f and d05d9da; the file on 8f9fcdb's working tree, three times; ruff | exit 0: 34 and 37 passed; exit 1: 13 failed (the stand-in's new settings leaked into later tests, its reset not knowing them; the Chromium tests' browser running around the others' own), then 2 (a rename that reached the stop's wording), then exit 0: 79 passed (42852a2); ruff clean |
| Two independent reviews | on 42852a2 | no blocker; both: a locked control's limit not recorded, leaving a pause no read ends; filling going on after a withheld value, the stop naming no limit; see D161 |
| After the reviews | `test_pilot_limits.py` (JUnit) on the working tree before 017d9ff and e71bbea, and on 29cc94f; the suites the change touches, 65 files in two runs on e71bbea; ruff | exit 0: 75 and 85 passed (the working tree before 017d9ff and e71bbea), 86 on 29cc94f and 90 on c8cdc59; the 65 files on e71bbea: exit 0 for both, 977 and 1224 passed; the 15 of them the regression set does not run, on c8cdc59: exit 0, 407 passed; ruff clean |
| Each part changed in turn | 30 changes on c8cdc59, one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 30 fail the tests named for their part (84 of the 296 named tests, over the runs); each file restored. A first run, on 29cc94f, of 29 changes found two that failed none: the capture's ASCII case-folding of `type` (the tests' types read alike unfolded) and the survey's decoding (Chromium hands Playwright a document's body already decoded); cases added (c8cdc59), and a 30th change, Unicode's lowercasing for ASCII's, run with them. Left out: a stop before typing carrying the uploads made before it, which no run can observe (D137 records each as it is made) |
| The regression set | `pytest` on 88 files (D160's 87 with `test_pilot_limits.py`; JUnit), in a copy of the branch at c8cdc59 | exit 0, 2797 passed (87 minutes) |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_pilot_limits.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 135 passed in 137 s; ruff formatted nothing, found nothing, and the format check passed |

## A control the page gives its application form from outside its markup is read as a question, and the form must send nothing NoEfforts did not read, by the click on its own button (D160, 2026-11-13; local only)

Rank 27 of the automation loop (D159's limit). Product changes:

- `app/modules/preparation/forms.py`: `given_from_outside` and `owned_nodes` (a listed control
  outside the application form's markup whose `form` names the form, resolved as the browser
  resolves it), read with the form's questions and refused as `GIVEN_FROM_OUTSIDE`;
  `FORM_REFUSALS`.
- `app/modules/preparation/greenhouse.py`: Greenhouse classic adopts either refusal from its
  page. `app/modules/preparation/workday.py`: an entry's control given from outside counted in
  the work history (D149's checkpoint).
- `app/modules/execution/adapters/form_entries.py`: `NAMES_JS` (the form's own controls,
  counted per name, the parser's and custom ones apart), `unread`; `ELEMENTS` (the form's
  controls through the browser's definitions); a custom element named by its attribute.
- `app/modules/execution/adapters/fixture_ats.py`: `_sendable_now` now first `_unread_controls`
  (`UNREAD_CONTROLS`, `FORM_UNREADABLE`), `_click_target` (`CLICK_ELSEWHERE`, again in
  `page_would_refuse`, where a final button that cannot be read still fails closed, 9838d26) and
  `_refused_holding` (`REFUSED_HOLDS`); the runner's own read failing
  is a plain stop; `file_alone` in the readback; the character set and D154's read through the
  browser's definitions; `form_selector`.
- `app/modules/execution/adapters/hosted_form.py`, `greenhouse.py`: their form selector, the
  file readback (`file_alone`), Greenhouse classic's own read failing a plain stop.
  `greenhouse_dom.py`: the pilot keeps its own reads (no check of the final button's form).
- The stand-ins (`fixtures/ats_receiver/receiver.py`: `cfg["sends"]` and the page's
  `before_form`, `form_tail`, `button_attrs`, `outside` slots; `lever_like.py`,
  `greenhouse_like.py`: `hidden_twin`, Greenhouse classic's `outside_unlabelled` and
  `gh_wrap_text_on_input`).

No migration, no new state; one new refusal reason (`GIVEN_FROM_OUTSIDE`); `SCHEMA_VERSION` stays
3 (the content's shape is unchanged), and so do `EXTRACTION_VERSION` and the adapter versions
(D160 says why). Nothing was run against a real page. `scripts/validate.sh all` was not run (it
runs the whole backend and e2e suites); ruff was.

| Check (branch `outside-controls`, from D159's branch at 0ba83e0) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_outside_controls.py` (JUnit) on the working tree before 515fe33; the adapter suites (`test_execution`, `test_lever_adapter`, `test_ashby_adapter`, `test_greenhouse_adapter`, `test_workday_adapter`, `test_workday_wizard`, `test_sent_as_approved`); ruff | exit 0, 45 passed; exit 0, 255 passed; ruff clean |
| Two independent reviews | on 515fe33 | a blocker in the second (the final click sent its button's own form or address; since D154); both: controls compared by name, the capture resolving `form` unlike the browser, the check failing open; see D160 |
| After the reviews | `test_outside_controls.py` (JUnit) on the working tree before 70e0ee3; 37 files in two runs (D159's 36 and `test_outside_controls`) on e86abb9; the files that failed, again on the working tree before 937cc2f; the 37 files on 937cc2f; ruff | exit 0, 98 passed; exit 1 for both on e86abb9: 33 and 14 failed (the Greenhouse pilot stopped at every final click by the new check of the button's form, which it inherited from the base adapter; D159's Greenhouse classic test now stopped before anything is entered), fixed in 937cc2f; those files again on the working tree before 937cc2f: exit 0, 312 and 140 passed; the 37 files on 937cc2f: exit 0 for both, 564 and 1173 passed; ruff clean |
| Each part changed in turn | 25 changes on 787e337, one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 25 fail the tests named for their part (52 of the 72 named tests, over the runs); each file restored. A first run, on 937cc2f, found four to correct: three named no test (their cases' ids hold spaces), and the base readback's file check passed the test named for it (a hidden value there at load stops the attempt before the upload): a case added, the value added once "Why us" is typed (787e337) |
| The regression set | `pytest` on 87 files (D159's 86 with `test_outside_controls.py`; JUnit), in a copy of the branch at 937cc2f (since then one test case and its stand-in mode added; the file is run in full with the records) | exit 1; 2641 passed, 65 failed in 81.9 min (all in `test_page_refusal_read.py`; fixed in 9838d26, next row) |
| After the regression set | the fix (9838d26): `test_page_refusal_read.py`, `test_page_own_checks.py` and `test_outside_controls.py` (JUnit) on the working tree; the change removed again in a worktree of its own, the test named for it run; the 37 files with `test_page_refusal_read.py` in two runs on 9838d26 | exit 0, 194 passed; without the fix, exit 1 (the test named for it fails); exit 0 for both on 9838d26: 633 and 1173 passed |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_outside_controls.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 147 passed in 104 s; ruff formatted nothing, found nothing, and the format check passed |

## An ordinary answer is read back as its form would send it, and a control whose form would send something else is refused when the form is read (D159, 2026-11-13; local only)

Rank 26 of the automation loop (D158's limits). Product changes:

- `app/modules/preparation/forms.py`: `sent_otherwise` (D155's rule, now read as Chromium reads
  the tag: `wrap` hard, physical or on; `dirname` where Chromium sends a field, even empty;
  `form` always) refuses a question as `SENT_OTHERWISE` in every branch of
  `extract_form_schema` (typed, list, group, box), after the reasons read before it;
  `sent_rule` switches it off for Greenhouse classic's cross-check; `question_limit` is public.
- `app/modules/preparation/greenhouse.py`: the job data compared with the page as read without
  the rule, then the page's refusal and its own length limit adopted (`_as_on_page`).
- `app/modules/preparation/workday.py`: a work entry's control read by the same `sent_otherwise`.
- `app/modules/preparation/router.py`: a form whose limits changed is a new version, and ends a
  pause (`_option_values`).
- `app/modules/execution/adapters/form_entries.py` (new): what a form would send, read passively
  as Chromium's submission picks it (`ENTRIES_JS`), and the exact comparison (`sends`).
- `app/modules/execution/adapters/fixture_ats.py`: `_sendable_now` (`_charset_refused`,
  `_limits_fit`, naming the limit; readable: a changed form, otherwise `LIMIT_UNREADABLE`) from
  `schema_matches`; `_fits_now` (D162: `_cut_at_focus`) before each value is typed, once the
  control has focus;
  `number_text`; the readback reads every answer as the form would send it (`_form_entries`,
  `APPLICATION_FORM`), a refused question by what it holds (`_HOLDS`).
- `app/modules/execution/adapters/hosted_form.py`, `greenhouse.py`: their application form;
  the hosted adapters read a refused question through the base readback; Greenhouse classic reads
  one D159 refused, and checks the character set and limits.
- `app/modules/execution/adapters/workday_sections.py`: a work entry read by the passive read,
  its control in the form it is in.
- The stand-ins (`fixtures/ats_receiver/receiver.py`: `cfg["sends"]`, `page_limits`, autosave
  lengths; `greenhouse_like.py`: `gh_limit_served`, `gh_limit_at_load`, `gh_wrap_page_text`).

No migration, no new state or reason code; `SCHEMA_VERSION` stays 3 (the content's shape is
unchanged), and so do `EXTRACTION_VERSION` and the adapter versions (D159 says why). Nothing was
run against a real page. `scripts/validate.sh all` was not run (it runs the whole backend and e2e
suites); ruff was.

| Check (branch `sent-as-approved`, from D158's branch at cfb83f9) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_sent_as_approved.py` (JUnit) on the working tree before b8512c9; `ruff check .`, `ruff format --check .` | exit 0, 43 passed; ruff clean |
| The suites the first version touches | 36 files in two runs on the content of b8512c9 (`test_execution`, `test_execution_failures`, `test_execution_validation`, `test_execution_security`, `test_execution_routing`, `test_question_limits`, `test_greenhouse_adapter`, `test_lever_adapter`, `test_ashby_adapter`, `test_lever_fixture`, `test_workday_ashby_fixtures`, `test_disclosure_evidence`, `test_upload_evidence`, `test_rehearsal`, `test_recovery_hardening`, `test_provider_reuse`, `test_self_identification_ledger`, `test_sent_as_approved`; `test_workday_adapter`, `test_workday_wizard`, `test_workday_follow_up`, `test_workday_experience`, `test_workday_entry_details`, `test_workday_entry_limits`, `test_wizard_next_checks`, `test_form_change_loop`, `test_capture_refusals`, `test_page_own_checks`, `test_conditional_questions`, `test_preparation`, `test_package_contract`, `test_version_diff`, `test_schema_v3`, `test_greenhouse_api_coverage`, `test_form_scope_labels`, `test_resolver`) | exit 0 for both: 427 and 1169 passed |
| Two independent reviews | on b8512c9 | a blocker in both (the readback's `FormData` let a page send the application) and one more in the second (Greenhouse classic sending page text in a refused question); see D159 |
| After the reviews | `test_sent_as_approved.py` (JUnit) on the working tree before 5468717; then the same 36 files in two runs on its content; ruff | exit 0, 78 passed; exit 0 for both: 462 and 1173 passed; `ruff check .` clean, and `ruff format .` then reformatted 2 files (f616163: a docstring and the new tests reindented, no code change) |
| The first removal run | 28 changes on f616163, one at a time, as below | 27 fail the tests named for their part. m07 (`sent_rule=False` removed) passed the test first named for it, `test_greenhouse_classic_keeps_its_cross_check_where_the_page_refuses_a_question`, which, read again, passed with the first version's order too: its list lost the question's help, so the help was the difference. The list now keeps it, and the test checks that the type alone differs (15a8560, 0ba83e0); m07 now names `test_greenhouse_classic_refuses_it_as_its_page_reads_it`, and m29 (the first version's order) the strengthened test; both tests on 0ba83e0: exit 0, 2 passed |
| Each part changed in turn | 29 changes on 0ba83e0 (5468717's code, formatted, with the test above strengthened; merging main in changed no file), one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 29 fail the tests named for their part (69 of the 110 named tests, over the runs); each file restored |
| The regression set | `pytest` on 86 files (D158's 85 with `test_sent_as_approved.py`; JUnit), in a copy of the branch at f616163 (since then only one test in `test_sent_as_approved.py` changed; the file is run in full with the records) | exit 0; 2604 passed in 88.5 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_sent_as_approved.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 123 passed in 99 s; ruff formatted nothing, found nothing, and the format check passed |

## An ordinary question's length limit is read as the browser reads it, and your answer held to it as its form sends it (D158, 2026-11-13; local only)

Rank 25 of the automation loop (D157's limit). Product changes:

- `app/modules/preparation/forms.py`: `read_maxlength` (one reading of `maxlength`, as the
  browser reads it, shared with D157's Workday reader), `_question_limit` (an ordinary
  question's limit, recorded from 1 to 100,000), `sent_len` counting a line break however it is
  written (LF, CR, CRLF) as two and never failing on a broken character, `one_line_breaks`;
  `_Node.twice` holds each repeated attribute's first value, which the reader takes.
- `app/modules/preparation/resolver.py`: `validate_value` holds a text answer to its limit as
  its form sends it and refuses a line break in a one-line box; `normalize_input` keeps a text
  area's line breaks as LF and refuses half a surrogate pair; `_no_longer_fits` makes an answer
  you gave that no longer fits a checkpoint, optional or not.
- `app/modules/preparation/router.py`: `_fit_to_field` fits a draft to its field before it is
  offered; a cached draft that no longer fits is replaced.
- `frontend/src/components/AnswerInput.jsx`: `sentLength`, the answer box's count.
- The base stand-in (`fixtures/ats_receiver/receiver.py`): `LIMITS`, `too_long`, its server's
  own check at submit.

No migration, no new state or reason code; `SCHEMA_VERSION` stays 3 (the content's shape is
unchanged). Nothing was run against a real page. `scripts/validate.sh all` was not run (it runs
the whole backend and e2e suites); ruff, `tsc --noEmit` and `npm run lint` were.

| Check (branch `question-limits`, from D157's branch at 1bba52c) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_question_limits.py tests/test_workday_entry_limits.py` (JUnit), on the working tree before f5422e9; `ruff check .`, `ruff format .`; `npx tsc --noEmit`, `npm run lint`; `npx playwright test e2e/question-limits.spec.ts` (desktop and mobile) | exit 0, 121 passed in 37 s; clean; exit 0, exit 0; exit 0, 2 passed |
| Two independent reviews | on f5422e9 | no blocker in either; both found the draft check counting characters, a lone CR counted short and a `maxlength` written twice read as its last value; see D158 |
| After the reviews | the same two files (JUnit) on the working tree before 8f7cc1d; ruff; then 29 suites (`test_answer_brain`, `test_answer_brain_rules`, `test_answers_that_do_not_fit`, `test_approval_reasons`, `test_auto_apply`, `test_bank_edit`, `test_bank_import`, `test_bank_races`, `test_bank_scope`, `test_bank_scope_api`, `test_capture_refusals`, `test_drafting`, `test_drafting_provider`, `test_execution_failures`, `test_execution_validation`, `test_fixture_provider`, `test_form_scope_labels`, `test_generated_documents`, `test_greenhouse_dom`, `test_input_binding`, `test_package_contract`, `test_preparation`, `test_question_limits`, `test_resolver`, `test_sections_review`, `test_sending`, `test_workday_entry_details`, `test_workday_entry_limits`, `test_workday_experience`) on its content; `tsc --noEmit`, `npm run lint` and the browser test on 8f7cc1d | exit 0, 146 passed; clean; exit 0, 2565 passed in 18.3 min; exit 0, exit 0, exit 0 (2 passed) |
| Each part changed in turn | 15 changes on 8f7cc1d, one at a time (a worktree of its own), the named tests run, the file restored; and the answer box's count changed back to `text.length` with the browser test run | exit 1 for each: all 15 fail the test named for their part; the browser test fails ("5/1000" where "6/1000" is expected); each file restored |
| The regression set | `pytest` on 85 files (D157's 84 with `test_question_limits.py`; JUnit), in a copy of the branch at 8f7cc1d | exit 0; 2522 passed in 75.6 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_question_limits.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 89 passed in 45 s; ruff formatted nothing, found nothing, and the format check passed |

## A Workday-style work entry's length limits are read, and your record held to them (D157, 2026-11-13; local only)

Rank 24 of the automation loop (D155's limit). Product changes:

- `app/modules/preparation/forms.py`: `SectionSpec.limits` (validated, written sorted and
  fingerprinted only when set), `LIMITED_FIELDS`, `MAX_LIMIT`, `sent_len` (the length as the
  form sends it); `_Node.twice` (attributes a tag writes twice); the generic reader's
  `maxlength` read without failing (`_whole_number`).
- `app/modules/preparation/workday.py`: a typed part's `maxlength` read as the browser reads
  it (`_limit`, `_limits`), refused where nothing can honour it; any attribute written twice
  on an entry control, and `minlength` or `pattern` on an entry already on the page, refused.
- `app/modules/preparation/structured_sections.py` (`_within`, `resolve_section`),
  `package.py` (passes and freezes the limits), `router.py` (refuses hand-set limits).
- `app/modules/execution/adapters/greenhouse_sections.py` (frozen limits validated, a value
  past its limit refused, Greenhouse never plans a limited section) and `workday_sections.py`
  (the plan's own check; the control's live limit read before each value is typed).
- The stand-in (FIXTURE ASSUMPTION FA7): `experience_limits`, `experience_limits_at_load`.

No migration, no new state or reason code; `SCHEMA_VERSION` stays 3 (the new paths recorded
under it, as D142, D149 and D155). Nothing was run against a real page.
`scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `workday-entry-limits`, from D156's branch at 9c9788c) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_workday_entry_limits.py` (JUnit), on the working tree before 36be30b; then with `test_package_contract.py`, `test_workday_entry_details.py`, `test_workday_experience.py`, `test_structured_sections.py`, `test_greenhouse_sections.py`; then `test_workday_experience.py` after its `maxlength` case became `minlength` | exit 0, 49 passed in 17 s; exit 1, 254 passed and the one case D157 changes; exit 0, 117 passed |
| Two independent reviews | on 36be30b | no blocker in either; both found the line-break count and capture reading a `maxlength` otherwise than the browser; see D157 |
| After the reviews | `pytest tests/test_workday_entry_limits.py` (JUnit) on the working tree before a5870b5; `ruff check .`, `ruff format .`; then 21 files (`test_capture_refusals`, `test_form_change_loop`, `test_form_scope_labels`, `test_greenhouse_dom`, `test_greenhouse_sections`, `test_greenhouse_sections_hardening`, `test_greenhouse_sections_package`, `test_package_contract`, `test_resolver`, `test_section_free_route`, `test_sections_review`, `test_structured_sections`, `test_workday_adapter`, `test_workday_ashby_fixtures`, `test_workday_entry_details`, `test_workday_entry_limits`, `test_workday_experience`, `test_workday_follow_up`, `test_workday_wizard`, `test_greenhouse_sections_browser`, `test_section_widgets`); then the limits and experience files on a5870b5 | exit 0, 87 passed in 31 s; clean; exit 0, 1235 passed in 12.8 min; exit 0, 214 passed in 1.9 min |
| Each part changed in turn | 37 changes on a5870b5, one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 37 fail a test, each the one named for its part; the worktree clean after |
| The generic reader's bounds (45937de) | `pytest` on `test_workday_entry_limits`, `test_resolver`, `test_greenhouse_dom`, `test_capture_refusals`, `test_form_scope_labels` (JUnit), on the working tree before 45937de; `ruff check .`, `ruff format .`; then 4 changes on 45937de, one at a time, the named tests run, the file restored | exit 0, 783 passed in 4.3 min; clean; exit 1 for each: all 4 fail the test named for their part |
| The regression set | `pytest` on 84 files (D156's 83 with `test_workday_entry_limits.py`; JUnit), in a copy of the branch at a5870b5 | exit 0; 2473 passed in 74.8 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_workday_entry_limits.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 147 passed in 61 s; ruff formatted nothing, found nothing, and the format check passed |

## Before each wizard page's Next, what the page itself would refuse stops the attempt with that page never sent (D156, 2026-11-13; local only)

Rank 23 of the automation loop (D154's limit). Product changes:

- `app/modules/execution/adapters/fixture_ats.py`: D154's two checks shared (`button_ready`,
  `would_refuse`, a `ClickChecks` bundle of reasons; `FINAL_CLICK` for the final click, which
  keeps its behaviour), the wait timed by time elapsed; the one read of the button's form
  (`_REFUSAL_JS`) can be kept to parts of the form (`within`), and the focus exemption covers
  what a control or widget holds, never a focused container.
- `app/modules/execution/adapters/workday.py`: `next_button` (also `click_next`'s),
  `next_ready` (the navigation time limit, a Next not drawn yet waited for too, the lease
  renewed), `next_would_refuse` (at that click, then `_final_would_refuse`: the final click's
  own validation over the pages filled so far), `_leave_focus` after each page is filled; the
  reasons `NEXT_*`, `NextRefusal`, `EarlyFinalRefusal`.
- `app/modules/execution/runner.py`: `_wizard_pages` waits for the Next before the readback
  (D148's reason preferred when it is not usable) and reads right before the gate for the
  Next; `_refused` honours a stop request for the Next's unread page too; `NEXT_READY_MS`.
- The stand-in (FIXTURE ASSUMPTION FA8): `next_disabled`, `next_late_enable`,
  `next_late_rewrite`, `next_needs_answers`, `next_aria`, `next_aria_last`; `focus_validation`
  on the wizard.

No migration, no new state or reason code, no package change (`SCHEMA_VERSION` unchanged).
Nothing was run against a real page. `scripts/validate.sh all` was not run (it runs the whole
backend and e2e suites); ruff was.

| Check (branch `wizard-next-checks`, from D155's branch at 756a401) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_wizard_next_checks.py` (JUnit), on the working tree before 5050ad0; then the late-rewrite case added | exit 0, 17 passed in 37 s; exit 0, 2 passed |
| The suites it touches | `pytest` on 11 files (`test_wizard_next_checks`, `test_page_own_checks`, `test_page_refusal_read`, `test_recovery_hardening`, `test_workday_wizard`, `test_worker_stop`, `test_workday_follow_up`, `test_workday_experience`, `test_workday_entry_details`, `test_workday_adapter`, `test_greenhouse_adapter`; JUnit), on the working tree that became 5050ad0 | exit 0; 549 passed in 18.2 min |
| Each part changed in turn, the first version | 9 changes on 5050ad0, one at a time (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 9 fail a test, each the one named for its part |
| Two independent reviews | on 5050ad0 | no blocker in either. The safety review: an existing D143 test passing for the wrong reason, an invalid escape in the stand-in, a mark on the field filled last never counted, values the final click's validation refuses not counted at a Next, the read's place unpinned, D148's reason hidden, records; the second review: the same first two and the values the final click refuses, the Next waited for 10 s where its click had waited 20 s, marks inside a focused section never counted, the native Next unreachable yet described as supported, test gaps, wording. Fixed (04350e6, f75f728), each with a test; the rest recorded in D156 |
| 04350e6 (the first two) | the click-failure test and the `next_aria` case (JUnit) | exit 0; 2 passed |
| After the reviews | `pytest tests/test_wizard_next_checks.py` (JUnit), on the working tree before f75f728; `ruff check --fix .` (import order), `ruff format .`, `ruff check .`; then the 11 files on f75f728 | exit 0, 26 passed in 52 s; clean; exit 0, 557 passed in 15.4 min |
| Each part changed in turn | 17 changes on f75f728, one at a time, the named tests run, the file restored (the 9 again, adjusted; 8 for the review fixes) | exit 1 for each: all 17 fail a test, each the one named for its part; the worktree clean after |
| The regression set | `pytest` on 83 files (D155's 82 with `test_wizard_next_checks.py`; JUnit), in a copy of the branch at f75f728 | exit 0; 2376 passed in 73.6 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_wizard_next_checks.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 71 passed in 79 s; ruff formatted nothing, found nothing, and the format check passed |

## A Workday-style work entry's Location and Role Description come from your record (D155, 2026-11-12; local only)

Rank 22 of the automation loop (D149's limit). Product changes:

- `app/modules/preparation/forms.py`: `SectionSpec.parts` and `required_parts` (written, and
  fingerprinted, only when set); `ENTRY_PARTS`, the one list of the two parts.
- `app/modules/preparation/workday.py`: capture names the parts the entry template asks and
  which the page requires; refuses a hard-wrapping text area, `dirname` or `form` on an entry's
  control, and an entry already on the page asking the parts otherwise than the template.
- `app/modules/preparation/structured_sections.py`: `resolve_employment_row(record, parts,
  required_parts)`: your record's own text (blank: not sent, or yours to add when required; a
  location with a line break, or a description still holding the resume reader's note: yours to
  fix); `resolve_section` refuses unknown parts and parts on education.
- `app/modules/preparation/package.py`: the parts passed to resolution and frozen with the
  section; `app/modules/preparation/router.py`: hand-set parts refused.
- `app/modules/execution/adapters/greenhouse_sections.py`: frozen content accepts the two fields
  only in a section that names them; Greenhouse's executor refuses such a section.
- `app/modules/execution/adapters/workday_sections.py`: the two parts entered and read back;
  focus leaves each typed control; the readback also reads what each control's form would send.
- `app/modules/execution/adapters/workday.py`: the section's entries read again after the page's
  uploads, before anything is typed into it.
- `app/modules/profiles/resume_parse.py`: `DATES_NOTE`, the note it writes first in a parsed
  role's description.
- The review page labels the two fields and keeps line breaks in the version diff
  (`frontend/src/app/(app)/applications/[id]/page.jsx`).
- The stand-in (FIXTURE ASSUMPTION FA7): `experience_parts_required`.

No migration, no new state or reason code; `SCHEMA_VERSION` stays 3, deliberately: the new
package paths are recorded under it in `tests/test_package_contract.py` (only a section whose
entry asks the parts carries them). Every Workday-style form with a Work Experience section
captured before D155 reads as changed at its next run (D132's pause). Nothing was run against a
real page. `scripts/validate.sh all` was not run (it runs the whole backend and e2e suites);
ruff, `tsc --noEmit` and `npm run lint` were.

| Check (branch `workday-entry-details`, from D154's branch at e687fff) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_workday_entry_details.py` (JUnit), then the 11 suites it touches most (`test_greenhouse_sections`, `_browser`, `_hardening`, `test_structured_sections`, `test_workday_experience`, `test_worker_stop`, `test_sections_review`, `test_workday_wizard`, `test_workday_adapter`, `test_workday_follow_up`, `test_workday_entry_details`), on the working tree before 35cfa5f; `npx tsc --noEmit`, `npm run lint` | exit 0, 44 passed; exit 0, 428 passed in 10.7 min (5 expectations of `test_workday_experience.py` updated first: the spec names its parts, a required Location is read, the frozen rows carry the two fields); exit 0; exit 0 |
| Each part changed in turn, the first version | 22 changes, one at a time on 35cfa5f (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 22 fail a test, each the one named for its part |
| Two independent reviews | on 35cfa5f | the safety review: three blockers (the package-shape pin not updated, so CI would fail; a hard-wrapping Role Description sending line breaks never approved; entries already on the page asking the parts otherwise, stopping after values were entered); the second review: the first two, and the entries as a weakness; both: gaps in tests and records. Fixed (756a401), each with a test; the rest recorded in D155 |
| After the reviews | `pytest` on 14 files (the 11 above, `test_package_contract`, `test_version_diff`, `test_resume_facts`; JUnit), on the working tree before 756a401; `ruff check .`, `ruff format --check .`, `npx tsc --noEmit`, `npm run lint`; then `test_workday_entry_details.py` and `test_package_contract.py` after ruff's import order | exit 0; 470 passed in 13.8 min; all clean; exit 0, 66 passed |
| Each part changed in turn | 33 changes, one at a time on 756a401 (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 33 fail a test, each the one named for its part (the 22 above, on the revised code, and 11 for the reviews' fixes: the hard wrap, `dirname` and `form` refused; the entries already on the page; what the form would send; focus leaving each control; the section read again after the uploads, for each reason; the resume reader's note; parts set by hand; parts on an education section); the worktree clean after |
| The regression set | `pytest` on 82 files (D154's 81 with `test_workday_entry_details.py`; JUnit), in a copy of the branch at 756a401, restarted once (the container restarted during the first run) | exit 0; 2350 passed in 73.4 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_workday_entry_details.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 108 passed in 63 s; ruff formatted nothing, found nothing, and the format check passed |

## Before the send gate, what the page itself would refuse at the final click stops the attempt; filling waits for what the answers started (D154, 2026-11-12; local only)

Rank 21 of the automation loop (D148's proposal). Product changes:

- `app/modules/execution/runner.py`:
  - after a single page's answers, and after each wizard page's, the page's own requests are
    waited for (`_settle`, at most `SETTLE_ENTRY_MS`, 8 s); a page still loading stops the
    attempt there (`STILL_LOADING`, nothing sent);
  - then the submit button (`adapter.final_ready`), before the readback;
  - right before the send gate, after the check after filling and before the recheck evidence,
    what the page would refuse at the final click (`adapter.page_would_refuse`); a finding
    abandons the attempt with nothing sent, every live approval retired (`_refused`); a page
    unreadable while the worker is being stopped ends as the stop (D150);
  - an adapter can wait for the page in the middle of filling (`on_settle`).
- `app/modules/execution/adapters/fixture_ats.py`: `final_button`, `leave_out`, `final_ready`,
  `page_would_refuse`, the read (`_REFUSAL_JS`, passive, counts only), `PageRefusal` and the
  reasons; `submit` clicks `final_button`.
- `hosted_form.py`, `greenhouse.py`, `greenhouse_dom.py`: each adapter's `final_button` (the
  control its click takes); the Greenhouse DOM adapter leaves out exactly the security-code
  boxes its click takes for the checkpoint (`_shown_code_box_ids`).
- `workday.py`: the page's reaction to the other answers is waited for before the follow-up
  questions are entered (D148).
- `service.py`: the `stopped_after_entry` wording covers the new stops; `docs/audit-events.md`
  likewise.
- The stand-ins (FIXTURE ASSUMPTIONS): `cfg page_check` and `page_check_delay_ms` (cleared by the
  receiver's reset), `GET /_fx/wait`; FA8 in `fixtures/ats_receiver/workday_like.py`, the
  `page_check` settings of `greenhouse_v2.py` and the receiver's own form.

No migration, no new state, reason code or package change (`SCHEMA_VERSION` unchanged), no
adapter version change. Nothing was run against a real page. `scripts/validate.sh all` was
not run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `page-own-checks`, from D153's branch at 2d53b77, then `main` with #62 (1976010; the tree unchanged), then 5db60c8 and e687fff) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_page_refusal_read.py` (JUnit), then `pytest tests/test_page_own_checks.py tests/test_page_refusal_read.py tests/test_greenhouse_real_mechanics.py`, before committing cc3c49e | exit 0; 51 passed; exit 0; 75 passed in 104.7 s (the D116 code checkpoint stopped by the button's wait at first: fixed before the commit, with a test) |
| Against the code before it | `test_page_own_checks.py` (17) on 64842b4's tests and stand-ins with the product files as they were at 2d53b77 | exit 1: 13 of 17 fail (`unknown`, `rejected`, `confirmed` or `rehearsed` where D154 stops before the send gate); the 4 that pass are the pages that go through |
| Each part changed in turn, the first version | 30 changes, one at a time on 64842b4 (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 30 fail a test, each the one named for its part |
| Two independent reviews | on cc3c49e | the safety review: one blocker (a stale mark on the field that has focus counted, so a page that checks a field when focus leaves it would have every application ending on a dropdown stopped); the second review: no blocker; both: gaps in tests and records. Fixed (539d1b7, 9fa81bc, 2e95220), each with a test; the rest recorded in D154 |
| The new tests and the suites they touch most, after the reviews | `pytest tests/test_page_own_checks.py tests/test_page_refusal_read.py tests/test_greenhouse_real_mechanics.py tests/test_workday_follow_up.py tests/test_workday_wizard.py tests/test_execution.py` (JUnit), on the working tree before 539d1b7 | exit 0; 190 passed in 6.0 min |
| Against the code before it, and its first version | `test_page_own_checks.py` (23, JUnit) on 2e95220's tests and stand-ins with the seven product files as they were at 2d53b77 (before D154); then it and `test_page_refusal_read.py` (91) with the five as at cc3c49e (its first version); the case 5db60c8 adds, against both | exit 1: 18 of 23 fail against 2d53b77 (`unknown` where the browser refused the click, a wizard's review page refused an earlier page, or a button stayed disabled; `rejected` where the page's own script refused it or a follow-up shown after a request was missed, answered or not; `confirmed` where the page was still loading, or rewrote a field while it kept Submit disabled; `rehearsed`; an internal error with two submit buttons; the two unreadable-page cases patch a read that did not exist); the 5 that pass are pages that go through. exit 1: 28 of 91 fail against cc3c49e: 5 through the runner (the stale mark on the focused field stopped a page that checks a field when focus leaves it, the safety review's blocker; both answered follow-ups shown after a request stopped; the field rewritten while Submit was disabled was sent unread; a page unreadable during a stop retired every approval) and 23 of the read's (the markup's constraints counted where the script decides, `aria-invalid` values other than "true", marks not shown, the checkpoint's wrapper, a form-associated element missed, the button's wait, a closed page, the reason's wording). The case 5db60c8 adds passes against both (exit 0, 1 passed each): it pins what is never stopped |
| The suites the change touches | `pytest` on the 14 of the 84 files the change touches that are not in the regression set (`test_after_send_diagnostics`, `test_b3_policy`, `test_batch_review`, `test_dropdown_observation_c`, `test_form_readiness`, `test_gh_readonly`, `test_greenhouse_sections_hardening`, `test_lever_fixture`, `test_locale_observation`, `test_readonly_cli_process`, `test_reason_codes`, `test_receiver_reset`, `test_widget_detector`, `test_widget_inspection`; JUnit), on 5db60c8; the 84 are the 80 that import a changed module and 4 that drive the changed receiver or pin the fixture adapter's version; the other 70 are in the regression set | exit 0; 368 passed in 14.2 min |
| Each part changed in turn | 49 changes, one at a time on 2e95220 (a worktree of its own), the named tests run, the file restored | exit 1 for 48, each failing the test named for its part; the 49th (the receiver's own form's button locator widened to any button in the form) passed, as that form had a single button: 5db60c8 gives the stand-in's form a button that does not submit it, with its test, and run again there that change fails it (exit 1). Every file restored, the tree clean after |
| The regression set | `pytest` on 81 files (D153's 79, `test_page_refusal_read.py` and `test_page_own_checks.py`; JUnit), in a copy of the branch at 2e95220 (the tree of 1976010) | exit 1; 2 failed, 2286 passed in 85.0 min: both tests e687fff updates, neither in the product (a computed `getattr` in a new read test, which the capture guard R11.4 refuses where a page runs; R11.8's expected wording, now D154's reason since 539d1b7 waits for the button before the readback); both files run again in full on e687fff: exit 0, 247 passed with `test_page_refusal_read.py` |
| Two tests the regression set found (e687fff: a computed `getattr` in a new read test, refused by the capture guard R11.4 where a page runs; R11.8's expected wording, now D154's reason) | `pytest tests/test_forbidden_capabilities.py tests/test_greenhouse_adapter.py` on 5db60c8 (JUnit), then with `tests/test_page_refusal_read.py` after the fix; `tests/test_bank_edit.py` (the one other file that sets the receiver's modes) | exit 1, 2 failed, 177 passed (both reproduced); exit 0, 247 passed; exit 0, 15 passed |
| The suites that read the repository, outside both runs above | `pytest` on the 14 files that scan the repository and are in neither the regression set nor the related run (`test_api_tokens`, `test_applications`, `test_authorizations`, `test_drafting`, `test_drafting_provider`, `test_email_reminders`, `test_fit`, `test_freehire_discovery`, `test_job_signals`, `test_lever`, `test_path_a`, `test_repo_hygiene`, `test_resolver`, `test_runtime_dependencies`; JUnit), on e687fff | exit 0; 875 passed in 3.9 min |
| A form's other buttons (5db60c8: a test and a stand-in variant, after a removal run on 2e95220 passed) | the new case and the second-submit case, then `test_receiver_reset.py` and the receiver's form's happy path (JUnit), on the working tree before 5db60c8 | exit 0; 2 passed; exit 0; 3 passed |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_page_refusal_read.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 113 passed; ruff formatted nothing, found nothing, and the format check passed |

## A list is judged by the page's record of changes to a list, and the option is chosen from one read (D153, 2026-11-12; local only)

Rank 19 of the automation loop. Product changes:

- `app/modules/preparation/gh_readonly.py`:
  - `classify_open(..., whole_page=True)`: the adapter passes False and leaves out the whole
    page's 150 ms check; the survey's own `open_state` keeps it;
  - the probe's record of changes to a list (`_PRE_JS`) also counts any attribute of the
    control, an attribute the probe finds its list by on an element holding the control, an
    element holding the control added or removed, any id, and style sheets (for an attribute
    change, only the sheet itself);
  - the probe's read returns the option elements its texts came from (`_PROBE_READ_JS`;
    `_PROBE_JS` returns what it did);
  - the survey judges its settle rule by the adapter's classification and compares the options
    once either classification found the list observed sufficiently.
- `app/modules/execution/adapters/dropdowns.py`: the classification without the whole page's
  check; the choice takes the list and its option from one read (`_CHOICE_JS`), requires the
  list to be exactly the approved one, and reads the option's text again just before the
  click.
- `app/modules/execution/adapters/greenhouse_sections.py`: the classification without the
  whole page's check; a refusal names `list_changed_recently` when only the record held the
  list back.
- `app/modules/execution/adapters/greenhouse_dom.py`: a comment (the location search's new
  refusals).
- The stand-in (`fixtures/ats_receiver/greenhouse_v2.py`): cfg `dd_style_tick_ms`, dd
  `controls_flip` and `class_flip`, loc `style_tick`, section_widget `css_ticking` (FIXTURE
  ASSUMPTIONS); the receiver's reset clears `dd_style_tick_ms`.
- `docs/greenhouse-readonly-compatibility-proposal.md`: the D152 note brought up to D153.

No migration, no new state, reason code or package change (`SCHEMA_VERSION` unchanged), no
adapter version change. Nothing was run against a real page. `scripts/validate.sh all` was
not run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `whole-page-check`, from D152's branch at 7a29fdc, then D152's records and `main` with #61 (bb37b6f)) | Command | Result |
|---|---|---|
| The first version's tests | `pytest` on `test_list_record.py` and the new cases of `test_dropdown_strategies.py`, `test_section_list_settle.py`, `test_survey_settle_rule.py` (JUnit), on 1f897c3 | exit 0; 27 passed |
| Against the code before it | the same 27, with the three product files as they were at 7a29fdc | exit 1: 13 of 27 fail (the classification, the four style-sheet cases of the record, the dropdowns busy at 100 and 250 ms, the style ticker accepted, the section busy at 100 ms, the section's style-sheet list accepted, the survey busy at 100 and 300 ms, the survey's style ticker) |
| Two independent reviews | on 1f897c3 | the safety review: two blockers (B1, a list relinked or reclassed through its control alone could be judged settled and a wrong option clicked at the choice; B2, an attribute change on any element holding a `<style>` counted as a list's); the second review: no blocker, gaps in tests and records. Fixed (5e42918); the rest recorded in D153 |
| The new tests, after the reviews | `pytest` on the 25 new and changed cases (`test_list_record.py`, `test_dropdown_choice.py`, the two flips, the engine's 20 ms case, the section's word; JUnit), then `test_dropdown_choice.py` with its two last cases | exit 0; 25 passed; exit 0, 5 passed |
| The changed test files | `pytest tests/test_list_record.py tests/test_dropdown_choice.py tests/test_dropdown_strategies.py tests/test_section_list_settle.py tests/test_survey_settle_rule.py tests/test_greenhouse_controls.py` (JUnit) | exit 0; 221 passed in 22.9 min (started on the working tree before the choice's last two cases, which passed on their own) |
| Against the code before it | the 45 new and changed cases (JUnit), on 5e42918's tests and stand-in with the four product files as they were at 7a29fdc (before D153), then as at 1f897c3 (its first version) | exit 1, 31 of 45 fail against 7a29fdc, among them the three lists changed after they were judged, from which the choice clicked an option at the approved position that was not the approved one; exit 1, 17 of 45 fail against 1f897c3, among them both lists switched through their control, which it accepted (the attempt confirmed), and the same three choices |
| The suites the change touches | `pytest` on the 12 of the 38 files the change touches that are not in the regression set (`test_b3_policy`, `test_dropdown_observation_c`, `test_gh_readonly`, `test_greenhouse_sections`, `test_greenhouse_sections_browser`, `test_greenhouse_sections_hardening`, `test_locale_observation`, `test_path_a`, `test_readonly_cli_process`, `test_sections_review`, `test_widget_detector`, `test_widget_inspection`; JUnit), on 5e42918; the other 26 are in the regression set | exit 0; 354 passed in 14.3 min (a first run of all 38 was stopped at its time limit at 58%: 720 passed, none failed) |
| Each part changed in turn | 21 changes, one at a time on 5e42918 (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 21 fail a test, each the one named for its part |
| The regression set | `pytest` on 79 files (D152's 77, `test_list_record.py` and `test_dropdown_choice.py`; JUnit), in a copy of the branch at 5e42918 | exit 0; 2197 passed in 80.3 min |
| `main` with #61 merged in (bb37b6f; the code as at 5e42918) | `pytest tests/test_list_record.py tests/test_dropdown_choice.py tests/test_survey_settle_rule.py tests/test_section_list_settle.py` (JUnit) | exit 0; 99 passed in 10.5 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_list_record.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 63 passed; ruff formatted nothing, found nothing, and the format check passed |

## The read-only survey publishes whether each list met the adapter's settle rule (D152, 2026-11-12; local only)

Rank 18 of the automation loop. Product changes:

- `app/modules/preparation/gh_readonly.py`: each widget-inspection action that opened a list
  publishes `settle_rule` (`list_quiet`, `equal_reads`, `pending`, `met`), judged at its last
  read, on the control's own action and on path C's container action; the inspection publishes
  `settle_rule_counts`. A locale request allowed on paths B and C is marked finished when it
  finishes or fails (never published). The quiet time and the adapter's window are numbers here,
  held equal to `dropdowns.STABLE_MS` and `SETTLE_MS` by a test. No new request, action, wait or
  budget.
- The dropdown stand-in (`fixtures/ats_receiver/greenhouse_v2.py`): ten variants (FIXTURE
  ASSUMPTIONS). The receiver's reset (`receiver.py`) clears every setting of the v2 stand-in.
- `docs/greenhouse-readonly-compatibility-proposal.md`: a dated note on what a run would now
  publish, and what it does not mean.

No migration, no new state, reason code or package change; the execution adapter is unchanged.
Code only: nothing was run against a real page, and no run is requested. `scripts/validate.sh
all` was not run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `survey-settle-rule`, from D151's branch at 3322027, then with D151's records and `main` with #60) | Command | Result |
|---|---|---|
| The new tests, first | `pytest tests/test_survey_settle_rule.py` (JUnit), on the tree committed as 9b8043f; then with `tests/test_widget_inspection.py` | exit 1 (8 of 20: the browser cases expected two dropdowns, the stand-in has three); corrected, exit 0, 20 passed; with two more tests and `test_widget_inspection.py`, exit 0, 48 passed |
| Two independent reviews | on 9b8043f | one blocker (both): an existing path C test pinned the container record's keys; weaknesses: the equal reads weaker than the adapter's, pending ending at a response's status, a verdict on path A, a container's list counted after an undetermined click, key names a posting's label could match, test gaps. Fixed (26e6cdc, 30766a5); the rest recorded in D152 |
| After the reviews | `pytest tests/test_survey_settle_rule.py tests/test_dropdown_observation_c.py` (JUnit), on the tree committed as 26e6cdc | exit 1 first: 58 of 63, the five after the ticker test failing (D145's ticker was not cleared by the receiver's reset and went on changing later pages); with the reset fixed, exit 0, 64 passed |
| The last two tests | `pytest tests/test_survey_settle_rule.py -k "cancels or skipped_widget or reset_clears"` (JUnit), on the tree committed as 30766a5 | exit 0; 3 passed |
| The final tests | `pytest tests/test_survey_settle_rule.py` (JUnit), on 30766a5 (a worktree of its own) | exit 0; 39 passed |
| The suites the change touches | `pytest` on 15 files (`test_b3_policy`, `test_dropdown_observation_c`, `test_dropdown_strategies`, `test_forbidden_capabilities`, `test_gh_readonly`, `test_greenhouse_controls`, `test_greenhouse_live`, `test_locale_observation`, `test_provider_contracts`, `test_readonly_cli_process`, `test_required_signals`, `test_survey_settle_rule`, `test_widget_detector`, `test_widget_inspection`, `test_workday_ashby_fixtures`; JUnit), on 26e6cdc | exit 0; 677 passed in 31.5 min |
| Each part changed in turn | 22 changes, one at a time on 30766a5 (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 22 fail a test |
| The regression set | `pytest` on 77 files (D151's 76 and `test_survey_settle_rule.py`; JUnit), in a copy of the branch at 7a29fdc | exit 0; 2159 passed in 79.7 min |
| `main` with #60 merged in (f188b4e) | `pytest tests/test_survey_settle_rule.py tests/test_dropdown_observation_c.py tests/test_widget_inspection.py tests/test_section_list_settle.py` (JUnit) | exit 0; 122 passed in 13.7 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`) and `test_survey_settle_rule.py` (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 84 passed; ruff formatted nothing, found nothing, and the format check passed |

## A section's combobox chooses only from a list that has settled (D151, 2026-11-12; local only)

Rank 17 of the automation loop. Product changes:

- `app/modules/execution/adapters/greenhouse_sections.py`: a section combobox reads its own list
  through the dropdown's settle rule (`_settled_list`: the probe and `classify_open`, requests
  recorded and refused by `dropdowns._data_refusal`, three equal reads, the page's record of list
  changes, SETTLE_MS or LATE_MS, a list nothing opened given up early), chooses the one option of
  the list, shown or not, reading the approved text (it must be shown), and reads the whole list
  and the option to click in one go before the click; the list closed within the dropdown's action
  time on a refusal.
- `app/modules/execution/adapters/greenhouse_dom.py`: the section plan gets the stand-in flag.
- The section stand-in (`fixtures/ats_receiver/greenhouse_v2.py`, `receiver.py`): list behaviours
  and a section-options route (FIXTURE ASSUMPTIONS).
- `tests/test_worker_stop.py`: D150's stand-in for the function that enters a section control
  passes on any further arguments.

No migration, no new state, reason code or package change, no adapter version change (as D145).
Nothing real was run; sections run on local stand-ins only. `scripts/validate.sh all` was not
run (it runs the whole backend and e2e suites); ruff was.

| Check (branch `section-list-settle`, from D150's branch at 1b955aa, then with its later commits and `main` with #59) | Command | Result |
|---|---|---|
| The new tests, first | `pytest tests/test_section_list_settle.py` (JUnit), on the tree committed as 5559514 | exit 0; 17 passed |
| Against the adapter before D151 | the same 17, with `greenhouse_sections.py` and `greenhouse_dom.py` as on 1b955aa (a worktree of its own) | exit 1; 14 of 17 failed: lists still loading or waiting refused ("0 options read the approved text exactly"); a list re-rendered every 300 ms chosen from and the application submitted ("confirmed"), also when read slowly; one re-rendered every 60 ms chosen from until a read missed the approved text; the three on-the-page tests could not call it. Three passed, as they must either way: a settled list read slowly, and a page busy elsewhere (2) |
| Two independent reviews | on 5559514 | one blocker (both): D150's section stop test broke (its stand-in took three arguments); and the first version followed the location search's loop, not the dropdown's rule it cited. Fixed (abcd4dd, 21e2289), with the weaknesses (D151) |
| After the reviews | `pytest tests/test_section_list_settle.py tests/test_section_widgets.py` and D150's two section stop tests (JUnit), on the tree committed as abcd4dd | exit 0; 39 passed |
| The final tests | `pytest tests/test_section_list_settle.py` (JUnit), on the tree committed as 21e2289 | exit 0; 30 passed |
| Against the adapter before D151, again | the 30, with the two files as on 1b955aa | exit 1; 25 of 30 failed: lists still loading or waiting refused, also when read slowly; lists re-rendered every 300 ms (read at any pace) or changed by a style sheet chosen from and the application submitted; one re-rendered every 60 ms chosen from until a read missed the approved text; a list whose opening posted (fetch, sendBeacon), or whose GET was answered 404, chosen from and the application submitted; the click on an approved option the list hid timed out (an internal error); the eight on-the-page tests could not call it. Five passed, as they must either way: a settled list read slowly, a page busy elsewhere (3), and a hidden copy of the approved option (refused before as now) |
| The suites the change touches | `pytest` on 15 files (`test_section_list_settle`, `test_approval_binding`, `test_disclosure_evidence`, `test_dropdown_strategies`, `test_form_change_loop`, `test_greenhouse_dom`, `test_greenhouse_live`, `test_greenhouse_sections`, `test_greenhouse_sections_browser`, `test_greenhouse_sections_e2e`, `test_greenhouse_sections_hardening`, `test_greenhouse_sections_package`, `test_section_widgets`, `test_sections_review`, `test_worker_stop`; JUnit), on 21e2289 | exit 0; 423 passed in 24.2 min |
| Each part changed in turn | 20 changes, one at a time on 21e2289 (a worktree of its own), the named tests run, the file restored | exit 1 for each: all 20 fail a test |
| The regression set | `pytest` on 76 files (D150's 75 and `test_section_list_settle.py`; JUnit), in a copy of the branch at 21e2289 | exit 0; 2,120 passed in 73.8 min |
| D150's last two commits merged in (3322027), then `main` with #59 (ca0eba9) | `pytest tests/test_worker_stop.py tests/test_forbidden_capabilities.py tests/test_section_list_settle.py tests/test_greenhouse_live.py` (JUnit), on the merge | exit 0; 266 passed in 7.9 min |
| After its records | the document tests (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`; JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 75 passed (the 45 document tests and the new file's 30, after ruff formatted one of its test signatures); ruff clean (386 files), on the records committed with this result |

## A request to stop the worker honoured before the next protected step (D150, 2026-11-12; local only)

Rank 16 of the automation loop. Product changes:

- `app/modules/execution/stopping.py` (new): the stop flag, one byte shared by the worker's
  processes (mapped at import, backed by a file named in the environment at `worker_init`).
- `app/worker.py`: `worker_init` shares the flag, `worker_shutting_down` sets it (and logs one
  line), `worker_shutdown` removes its file.
- `app/modules/execution/runner.py`: the request read before the claim (a new message, nothing
  claimed), at D143's checks and after each heartbeat, before the first page is opened and in
  its readiness wait, in the code wait, and on the API route as it starts, before its draft and
  before each document; before the disclosure gate the attempt goes back in the queue, after it
  is abandoned; a browser lost while stopping is the stop's; a rehearsal that has filled
  completes.
- `app/modules/execution/service.py`: each gate reads the request last; `requeue_on_stop`
  (generation-fenced, counted with the sweeper's re-queues); `publish_again`.
- `app/modules/execution/adapters/`: a check before each Greenhouse section control and "Add
  another" (`greenhouse_sections.py`), after an upload's settle (`greenhouse_dom.py`), after the
  hosted form's wait for a shown question (`greenhouse.py`), before each API document
  (`fake_api.py`).
- `app/modules/execution/browser.py`: Playwright launched without its own signal handling.
- `app/modules/execution/faults.py`: a test-only fault action, `stop`.
- `docker-compose.yml`: `worker` depends on `browser-runner` and `egress-proxy`, and has a
  `stop_grace_period` of 150 s.
- The owner's table (`docs/activation-status.md` §8) and the deployment guide (§6, §8).

No migration, no new state or reason code, no package change. `scripts/validate.sh all` was not
run (it runs the whole backend and e2e suites); ruff was. Nothing real was run.

| Check (branch `worker-stop-request`, from `main` at D148, then `main` with #58) | Command | Result |
|---|---|---|
| The new tests, first | `pytest tests/test_worker_stop.py` (JUnit), on the tree committed as 109ca88 | exit 1; 25 of 28 passed: the API route's tests did not set the fake API's token (that suite sets it in a fixture of its own), so the application went to the browser route |
| Again | the same, on the tree committed as d95856c (the token set; the API route checks as it starts) | exit 0; 28 passed; the five real-worker runs exited 2.3 to 2.5 s after release |
| After the two reviews' fixes | the same, on the working tree before 300b87e | exit 1 first: 45 of 46 passed (the sections test lacked the receiver mode that serves the section); and the readiness-wait test passed for the wrong reason (its stand-in called a static method with two arguments, and that error ended the run as the stop). Both corrected; exit 0, 50 passed, on the tree committed as 300b87e |
| On the tree merged with `main` (D149) | the same, with a Workday section case added, on the tree committed as f8a08b4 | exit 0; 51 passed; the real-worker runs exited 2.3 to 2.5 s after release |
| After the removal runs and the suites below | the same with `test_greenhouse_live.py`, on 4b456c7: two tests added to the new file (aeab20d: an error on the API route while stopping, 2 cases; the requeue never asked for after entry, in the after-entry tests of both routes), and D111's source-order test repointed (4b456c7, below) | exit 0; 95 passed (the new file's 53 and `test_greenhouse_live.py`'s 42) |
| The suites the change touches | `pytest` on 23 files (`test_worker_stop`, `test_recovery_hardening`, `test_celery_execution`, `test_execution_failures`, `test_execution`, `test_code_wait_quarantine`, `test_api_provider`, `test_greenhouse_dom`, `test_greenhouse_live`, `test_greenhouse_sections_e2e`, `test_greenhouse_adapter`, `test_workday_wizard`, `test_workday_experience`, `test_rehearsal`, `test_rehearsal_stop`, `test_disclosure_evidence`, `test_deployment_config`, `test_republish_queued`, `test_lock_order`, `test_gate_snapshot_race`, `test_browser_isolation`, `test_upload_evidence`, `test_attempt_queue`; JUnit), on f8a08b4 | exit 1; 636 of 637 passed in 30.0 min. The one failure was D111's source-order test (`test_greenhouse_live.py`): it found the rehearsal's stop by the first `_rehearsal(aid)` in `run_attempt`, and since D150 the run asks that right after filling too, for its stop requests. The order the test protects held. It now names the rehearsal's stop and the send gate (4b456c7); with the re-check moved after the rehearsal's stop it fails (checked in the removal runs' worktree) |
| Each part changed in turn | 46 changes, one at a time on f8a08b4 (a worktree of its own), the named tests run, the file restored | exit 1 for 43 (each fails a test). Three passed: r3, the budget check's own read of the request, had only the after-entry tests, which the send gate's read ends the same way; the API route's own handler of the request, and its branch for an error while stopping, passed every test named for them. Two tests were added (aeab20d; D150) |
| The three again | the same three changes against the whole of `test_worker_stop.py`, on aeab20d | exit 1 for each: r3 fails 10 of 53 (the four re-queue cases, both adapters' section tests, the upload's settle, the hosted form's question, and a real worker stopped before opening the form); the API route's handler 2 (its after-gate stops, which must never ask for the requeue); its error branch 2 (both new cases) |
| The regression set | `pytest` on 75 files (D149's 74 and `test_worker_stop.py`; JUnit), in a copy of the branch at f8a08b4, alongside the runs above | exit 1; 2,086 of 2,088 passed in 72.8 min. Two failures, both since fixed on the branch: D111's source-order test (above, 4b456c7), and the capture guard (`test_forbidden_capabilities.py`, R11.4), which refuses an attribute looked up by a name built at run time in any file where a page runs: the stop tests' recorder of page actions did that (below) |
| The recorder fixed | the same file's recorder names each page action with its class and method (0e6dc26); `pytest tests/test_forbidden_capabilities.py tests/test_worker_stop.py` (JUnit), on the tree committed as 0e6dc26; then the five removals whose failing tests use the recorder (a1 to a5), run again on 0e6dc26 | exit 0; 194 passed (141 and 53); each of the five removals still fails the same tests |

## Workday-style Work Experience: your approved work history entered on My Experience (D149, 2026-11-12; local only)

Rank 13 of the automation loop. Product changes:

- `app/modules/preparation/workday.py`: the stand-in's Work Experience section (FA7) is read as
  an employment section on its page (`SectionSpec` with `step` and `required`), only when it is
  exactly the structure NoEfforts enters; its entries' controls are never questions and never
  read by the generic extractor; any other work history is one required checkpoint
  (`work_experience`); a checkpoint replaces a page question that shares its key, and only the
  extractor's own challenge field is exempt from the wizard's page rule.
- `app/modules/preparation/forms.py`: `SectionSpec.step` and `.required`, written and
  fingerprinted (as one value) only when set; a section's page must be one of the wizard's pages
  before the last; the generic extractor can skip controls by name.
- `app/modules/preparation/package.py`: the frozen section carries its page; a section the page
  requires with no approved work history blocks approval (`section:employment`).
- `app/modules/preparation/structured_sections.py`: a title or employer holding a line break or
  only spaces is a checkpoint (on Greenhouse too).
- `app/modules/execution/adapters/workday_sections.py` (new): the entries planned from the frozen
  section, added by the section's own button when absent, entered and read back control by
  control (exactly), each reported as it is given; the readback refuses any entry beyond the
  approved ones and any control left empty that the page requires.
- `app/modules/execution/adapters/workday.py`: the section entered on its page after the page's
  other answers; read back with its page; before anything is entered, a frozen section it cannot
  place, more entries than approved, or entries it cannot type into or that already hold values,
  stop the attempt with nothing at the employer.
- `app/modules/execution/policy.py`: the Workday stand-in's capability text brought up to date.
- `fixtures/ats_receiver/workday_like.py`: FIXTURE ASSUMPTION FA7 and its variants.

No migration, no new state or reason code; `SCHEMA_VERSION` (3) and the adapter version
(`fixture-workday-2`) unchanged, deliberately (D149 says why; `.sections[].step` recorded under
version 3 in `tests/test_package_contract.py`). `scripts/validate.sh all` was not run (it runs the
whole backend and e2e suites); ruff was. Nothing real was run.

| Check (branch `wizard-experience`, from D148's branch) | Command | Result |
|---|---|---|
| What capture reads from the stand-in | each wizard variant's and the single page's HTML through `workday.extract_schema` (a snippet, no database), before any test | `experience`, `_required`, `_parse`, `_entry_at_load`, `_add_broken`: one employment section on "My Experience" (required for `_required`), no `work…` question; `_unknown_control`: no section, the `work_experience` checkpoint; the single page: the section with no page; the plain wizard: nothing |
| The new tests | `pytest tests/test_workday_experience.py` (JUnit), on the tree committed as 9fc9734 | exit 1 first (a blocked approval answers 409, not 400, as the test assumed); corrected, exit 0, 45 passed |
| The package contract | `pytest tests/test_package_contract.py` (JUnit), on the same tree | exit 0; 3 passed (`.sections[].step` recorded) |
| The suites the change touches | `pytest` on 21 files (`test_workday_*.py`, `test_greenhouse_sections*.py`, `test_sections_review.py`, `test_structured_sections.py`, `test_section_widgets.py`, `test_section_free_route.py`, `test_form_change_loop.py`, `test_provider_contracts.py`, `test_conditional_questions.py`, `test_disclosure_evidence.py`, `test_self_identification_ledger.py`, `test_sending.py`, `test_package_contract.py`; JUnit), on the tree committed as 9fc9734 | exit 0; 473 passed in 11.9 min |
| Capture's further refusals and the browser checks | the new tests (JUnit), on the tree committed as 26efad8 | exit 1 first (a helper named like the browser fixture); renamed, exit 0, 57 passed |
| The fingerprint, the validator, a missing section, an absent part | the new tests (JUnit), on the tree committed as 5e891ad | exit 0; 61 passed |
| Each part changed in turn | 43 changes, one at a time on 5e891ad (a worktree of its own), the named tests run, the file restored | all 43 fail a test |
| After the first review's fixes | the new tests (JUnit), on the tree committed as d282574 | exit 1 first: new test pages missing labels the extractor needs, and the read of a filled page treated the page's hiding of a current role's To as a broken entry (presentation checks moved to the template, the section and a check of the entries before anything is entered); then exit 0, 94 passed |
| The suites the change touches, on d282574 | the same 21 files (JUnit) | exit 0; 522 passed in 12.7 min |
| The tests tightened | the new tests (JUnit), on the tree committed as e30ba41 | exit 0; 96 passed |
| Each part changed in turn, after the first review | 64 changes, one at a time on e30ba41 | 63 fail a test; one made the module fail to compile and so showed nothing (replaced in the next round) |
| After the second review's fixes | the new tests (JUnit), on the tree committed as ac5b48b, then bdb5311 (one case added) | exit 1 first (the test page kept a ticked role's To required, unlike the stand-in; the page corrected); then exit 0, 118 passed; the 63 capture cases, 63 passed |
| The suites the change touches, on bdb5311 | the same 21 files (JUnit) | exit 0; 547 passed in 12.9 min (the new file's 119 cases among them) |
| Each part changed in turn, after the second review | 83 changes, one at a time on bdb5311 | all 83 fail a test |
| The regression set | `pytest` on 74 files (D148's 73 and `test_workday_experience.py`; JUnit), in a copy of the branch at bdb5311, alongside the runs above | exit 0; 2037 passed in 68 min |

## A Workday-style follow-up question, entered only when the page shows it (D148, 2026-11-11; local only)

Rank 12 of the automation loop. Product changes:

- `app/modules/preparation/workday.py`: a question of the application form hidden at load inside
  its page (every control of it hidden, by `hidden`, `aria-hidden="true"` or an inline
  `display: none` / `visibility: hidden`, on itself or an element between it and the form) is
  captured as one the page shows by its own logic, `Condition(UNKNOWN_TRIGGER)`, read on the
  generic extractor's own tree and form; a wizard page's own `hidden` does not count; a
  checkpoint and a file input are never marked.
- `app/modules/execution/adapters/workday.py`: every other answer first, then each such typed
  question only if the page shows it and it can be typed into; one it does not show is never
  touched or waited for and is read back empty; one the page removed is never waited for;
  after filling, what the page shows must be what was entered (`follow_ups`); before anything
  is entered, a follow-up's requirement is compared as approved, and an approved value for a
  hidden choice is refused; once answers were entered, the page's reaction (what it requires,
  what it hides) is not a changed form; a wizard rechecks, after each Next and before the send
  gate, the follow-ups its filled pages left empty.
- `app/modules/execution/runner.py`: before a wizard page's Next gate, that page's follow-ups and
  the live form against the approved one (`page_follow_ups`); a shown one it requires with no
  approved answer ends the attempt there. On a single page the check after filling pauses for
  your answer (D135's pause).
- `fixtures/ats_receiver/workday_like.py`: FIXTURE ASSUMPTION FA6, the follow-up question in five
  shapes, on page 4 of the wizard and on the single page.

No migration, no new state, reason code or approval text; `SCHEMA_VERSION` (3) and the adapter
version (`fixture-workday-2`) unchanged, deliberately (D148 says why). Decision, limits and the
two reviews in D148, evidence in `docs/evidence-matrix.md`. `scripts/validate.sh all` was not
run (it runs the whole backend and e2e suites); ruff was. Nothing real was run.

| Check (branch `wizard-follow-up`, from D147's branch) | Command | Result |
|---|---|---|
| What capture reads from the stand-in | the wizard's and the single page's HTML through `workday.extract_schema` (a snippet, no database), before any test | the follow-up alone carries the condition, on page 4, optional (required in the markup for `follow_up_required`); pages 2 to 5 unmarked; the wizard still recognised |
| The new tests | `pytest tests/test_workday_follow_up.py` (JUnit), on the uncommitted tree | exit 0; 31 passed on the first run |
| The suites the change touches | `pytest` on `test_workday_wizard.py`, `test_workday_adapter.py`, `test_workday_ashby_fixtures.py`, `test_self_identification_ledger.py`, `test_disclosure_evidence.py`, `test_package_contract.py`, `test_sending.py`, `test_provider_contracts.py`, `test_conditional_questions.py` (JUnit), on the same tree | exit 0; 234 passed in 6.7 min |
| After formatting and naming the cases | `pytest tests/test_workday_follow_up.py` (JUnit), on the tree committed a minute later as 9c3bf1c | exit 0; 31 passed |
| Each part changed in turn | 23 changes, one at a time on 9c3bf1c, the named tests run, the file restored | all 23 fail a test |
| A question the page hides after entry (found while the first review ran) | `pytest tests/test_workday_follow_up.py` (JUnit), on the tree committed as f65c551 | exit 1 first: 31 passed, 1 failed, an older unit test whose package held one of the page's two questions (a real package holds every question read); with that corrected, exit 0, 32 passed |
| The regression set on f65c551 | `pytest` on 73 files (D147's 67, `test_workday_follow_up.py`, `test_workday_ashby_fixtures.py`, `test_package_contract.py`, `test_provider_admission.py`, `test_provider_contracts.py`, `test_support_wording.py`; JUnit), in a copy of the branch, alongside the runs below | exit 0; 1901 passed in 64 min |
| After the first review's fixes | `pytest tests/test_workday_follow_up.py` (JUnit), on the tree committed a minute later as 4f90edc | exit 0; 39 passed |
| The suites the change touches, on 4f90edc | the same files and `test_form_change_loop.py` (JUnit) | exit 0; 302 passed in 8.8 min |
| Each part changed in turn, after the first review | 30 changes, one at a time on 4f90edc | all 30 fail a test |
| After the second review's fixes | `pytest tests/test_workday_follow_up.py` (JUnit), on the tree committed as 67e382f | exit 0; 49 passed; then the recheck's test made to go through filling: its 5 neighbours, exit 0, 5 passed |
| The suites the change touches, on 67e382f | the same files (JUnit) | exit 0; 312 passed in 9.8 min |
| Each part changed in turn, after the second review | 38 changes, one at a time on 67e382f (the 30, two retargeted, and eight new) | 37 of 38 fail a test; the 38th (controls outside the form counted) failed none, as the group rule made the test's cases pass anyway; with the test covering a visible control of the same name outside the form (a9f4222), it and its neighbour (the form's bound) both fail it |
| The regression set on 67e382f | the same 73 files (JUnit), in a copy of the branch, alongside the removal runs | exit 0; 1918 passed in 64 min |
| The form's bounds, rechecked | the capture test with a visible control of the same name outside the form, committed as a9f4222; then those two changes in turn | exit 0, 1 passed; both changes fail it |
| Main merged in (D146 as #55, D147 as #56) | `git merge origin/main`: two documents conflicted (D146's records), main's version taken (D148 had changed no document); the branch then differs from main in D148's five files only (bec4c5e) | — |
| D147 recorded as merged, then the document tests | `pytest` on `test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py` (JUnit), on bec4c5e and the records, committed as 414bfd3 | exit 0; 45 passed |
| After D148's records | the same document tests (JUnit); `ruff format .`, `ruff check .`, `ruff format --check .` | exit 0; 45 passed; ruff clean (381 files), on the records committed with this result |

## A restored database comes up held, and nothing it restored runs (D147, 2026-11-11; local only)

Rank 20 of the automation loop, found by D146's review. Product changes:

- `app/modules/execution/models.py` and migration `d147a0c2e5f1`: `instance_stamp`, stamps keyed
  by the oid PostgreSQL gave the database and its server's cluster identifier; the upgrade
  writes this database's; the downgrade refuses while the database is held.
- `app/modules/execution/restore.py`: `held` (a stamp names another database), `resolve` (in
  three steps, one resolver at a time: every active attempt ended as an unknown outcome, its
  application `submitted_unconfirmed` (a rehearsal's too), its verification requests closed,
  and every live approval retired; every account's standing rule paused; the other stamps removed), `status` and
  `restored_at`; `--force` holds the database first.
- `app/modules/applications/states.py`: the system's move to `submitted_unconfirmed` from
  `queued` and `running`, for a restore.
- `app/modules/execution/service.py`: while held, the claim refuses every attempt, queueing,
  cancelling and revoking are refused (`restored_backup_held`) and the sweeper does nothing; a
  retirement reason (`restored_from_backup`).
- `app/modules/account/export.py` and `docs/account-deletion.md`: the stamp table is left out of
  the account export (it names no account).
- `app/modules/preparation/package.py`: approving is refused while held; the refusal's text
  (`docs/approval-reasons.md`).
- `app/worker.py` and `cli.py` (`relay`): a hold is resolved before anything is published, and
  nothing is published while another resolver is at work; `restore-status`, `restore-resolve
  [--force]` (exits 1 when another resolver is at work).
- `app/modules/autoapply/service.py`: the standing rule does nothing while held, and pausing it
  then only pauses it; it leaves to the owner every application that began before the restore,
  and its pause by the restore is audited with its reason.
- `app/modules/notifications/service.py` and the notifications page: every account told
  (`restored_backup`), but one made after the restore was resolved.
- `scripts/docker-smoke.sh`: after its restore, starts the app alone, checks that the database
  shows as held, then starts the rest and waits for the restore to be resolved.
- Tests: `tests/isolation.py` can copy this run's database (`CREATE DATABASE ... TEMPLATE`).
- Documents: the deployment guide's §6 (the upgrade; what else looks like a restore) and §7
  (a check after every restore instead of cases: held, not held, or a version before D147),
  the architecture page, the audit events.

One migration (it creates the table and stamps the database; the downgrade drops it); no new
attempt state, no retry; `SCHEMA_VERSION` and every adapter version unchanged. Decision, limits
and the review in D147, evidence in `docs/evidence-matrix.md`.

What a restore still cannot do: know what was sent after its backup. The owner compares the
Tracker with the confirmation emails received since, and records what they find, before
approving, queueing or resuming anything (§7). Not recognized: a restore into the same
database, a copy of the server's files, a backup taken before D147; §7's check finds them and
`restore-resolve --force` resolves them. Held without a restore: a PostgreSQL major upgrade or a
move to another server (§6). `scripts/validate.sh all` was not run (it runs the whole backend
and e2e suites); ruff was. Nothing real was run.

| Check (branch `restore-hold`, from D146's branch) | Command | Result |
|---|---|---|
| The new tests and the migration's | `pytest tests/test_restore_hold.py` and the migration's test (JUnit), on c9eaf56 (D146's branch merged in) | exit 0; 16 passed |
| The files the change touches | `pytest` on `test_migrations.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_doc_references.py`, `test_notifications.py`, `test_auto_apply.py`, `test_republish_queued.py`, `test_test_isolation.py`, `test_deployment_config.py` (JUnit), on c9eaf56 | exit 1; 105 passed, 1 failed: the feed's scoping test counts the feed's queries, and the restore item adds one. The test was corrected (the count, and what that query is), committed as 08b0237; then `tests/test_notifications.py`: exit 0, 12 passed |
| Each part changed in turn | 17 changes, one at a time on 08b0237, the named tests run, the file restored | all 17 fail a test |
| An oid is not enough across servers (a measurement) | two throwaway clusters (`initdb` in the scratchpad, a private port), a database created first in each | both databases had oid 16384; the clusters' identifiers differed. Hence the cluster's identifier in the stamp (fcfa4f5) |
| After the cluster's identifier and the relay's check | `pytest tests/test_restore_hold.py tests/test_notifications.py` and the migration's test (JUnit), on the tree committed a minute later as fcfa4f5 | exit 0; 29 passed (16, 12 and 1) |
| Each part changed in turn, again | 22 changes, one at a time on fcfa4f5 (the 17, three with moved targets, and five new) | all 22 fail a test (a first start stopped at the script's own check, before any change: one target had moved) |
| The regression set on fcfa4f5 | `pytest` on 67 files (D146's 64, `test_restore_hold.py`, `test_migrations.py`, `test_audit_inventory.py`; JUnit) | stopped by me after the independent review, before it finished: the rework below superseded that tree; its databases dropped |
| The rework after the review, while it was written | `pytest tests/test_restore_hold.py tests/test_notifications.py`, the migration's test, `test_applications.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_code_wait_quarantine.py` (JUnit) | exit 1; 72 passed, 2 failed, both from the rework: the held test approved an application after the restore, which is now refused (it is prepared before the restore now), and the audit inventory needs the restore's pause in a row of its own |
| The same, after both corrections | `pytest tests/test_restore_hold.py tests/test_audit_inventory.py tests/test_auto_apply.py tests/test_republish_queued.py`, then the document tests (`test_audit_inventory.py`, `test_doc_references.py`, `test_approval_reasons.py`; JUnit) | exit 1; 58 passed, 1 failed (the inventory: a row per key set); then, with the second row, exit 0; 12 passed |
| The reworked tests | `pytest tests/test_restore_hold.py`, the migration's test, `tests/test_deployment_config.py` (JUnit), on the tree committed a minute later as e365797 | exit 0; 40 passed (22, 1 and 17) |
| Each part changed in turn, after the rework | 31 changes, one at a time on e365797 | 30 of 31 fail a test; the 31st (the standing rule's own check) failed once its test required the rule to do nothing at all (6064a83) |
| The rework's test of the standing rule made stricter | the rule's test, then its own check removed (JUnit), on 6064a83 | exit 0, 1 passed; with the check removed, it fails |
| The regression set on 6064a83 | the same 67 files (JUnit) | stopped by me after the second review, a few minutes in: its fixes superseded that tree; its databases dropped |
| The second review's blocker reproduced | the review's static comparison of every table with the export's decisions, read on e365797 | `instance_stamp` the only table without one (`tests/test_account.py` was not in any earlier run) |
| After the second review's fixes | `pytest tests/test_restore_hold.py tests/test_account.py tests/test_applications.py tests/test_approval_reasons.py tests/test_audit_inventory.py tests/test_doc_references.py tests/test_auto_apply.py tests/test_republish_queued.py tests/test_notifications.py` and the migration's test (JUnit), on the tree committed a minute later as a6c1444 | exit 0; 127 passed (26, 16, 24, 9, 2, 1, 20, 16, 12 and 1) |
| Each part changed in turn, after the second review | 39 changes, one at a time on a6c1444 | all 39 fail a test |
| The regression set, the only test run on the machine | `pytest` on 67 files (D146's 64, `test_restore_hold.py`, `test_migrations.py`, `test_audit_inventory.py`; JUnit), on c0dd87b (with D146's branch as it now stands merged in) | exit 0; 1637 passed in 62 min |
| After the last edit | `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents and the account export's (`test_doc_references.py`, `test_approval_reasons.py`, `test_audit_inventory.py`, `test_deployment_config.py`, `test_account.py`; JUnit); the frontend's `npx tsc --noEmit` and `npm run lint` | ruff clean (380 files unchanged); exit 0, 45 passed; `tsc` and lint exit 0 |

## An attempt still waiting to be taken is published again (D146, 2026-11-11; local only)

Rank 15 of the automation loop. Product changes:

- `app/modules/execution/service.py`: `republish_waiting` publishes again for an attempt still
  `pending`, with no cancel requested and nothing entered, whose newest message went out more
  than `outbox_republish_seconds` ago; it locks the messages only, ends at its first failed
  publish, and repeats for as long as the attempt waits. The claim's compare-and-swap now also
  requires that nothing was disclosed.
- `app/worker.py`: the relay's task calls it after the new messages.
- `app/core/config.py`: the setting (300, at least 60).
- `app/modules/execution/runner.py`: a fault point before the claim (honoured in tests only).
- `app/modules/execution/cli.py`: `relay` publishes again too.
- `stop_for_revoke` in `service.py`: revoking an attempt the sweeper put back no longer fails
  (the second review's finding; there before D146).
- Comments and docstrings: `models.py` (the message's time is now its last publication),
  `worker.py`.
- Documents: the deployment guide's §6 (the upgrade), §7 (a restore now needs a step between
  starting the app and starting the workers) and §8 (`docker compose down`), and the
  architecture page.

No migration, no new state, no retry of anything started; `SCHEMA_VERSION` and every adapter
version unchanged. Decision, limits and the review in D146, evidence in
`docs/evidence-matrix.md`.

Why now: D144's review showed that more is exposed to a lost message since the relay moved to
the scheduler. Measured by the first halves of the new end-to-end tests: with its message gone
from the broker, a running worker did not take the attempt in the three seconds watched; a worker process lost before the
claim leaves the message acknowledged and the attempt `pending`, and a sweep recovers nothing.
**After a database restore this change runs again what the backup shows as queued** (D146):
until ranked slice 20 is built, the deployment guide's §7 has a step for it.
`scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.
Nothing real was run.

| Check (branch `republish-queued`, from D145's branch) | Command | Result |
|---|---|---|
| The first version's tests | `pytest tests/test_republish_queued.py` (JUnit), on the tree committed as 41e1d6d | exit 0; 11 passed |
| The first version, each part changed in turn | 15 changes, one at a time on 41e1d6d, the file's tests run, the file restored | all 15 fail a test |
| After the review: the file's tests | the same command, on the tree committed as 7424916 | exit 0; 15 passed |
| After the second review: the file's tests, and the revoke fix undone | `pytest tests/test_republish_queued.py` (JUnit), on cc836b5; then the fix undone, the new test run, the file restored | exit 0; 25 passed (16 and 9); with the revoke fix undone its test fails (a 500) |
| After the review, each part changed in turn | 21 changes, one at a time on f3cd566 (D145 merged in), the file's tests run, the file restored | all 21 fail a test (a first attempt on the same tree was refused before any test ran: the database server had stopped with a restart of the session's machine; rerun once it was started) |
| The regression set, the only test run on the machine | `pytest` on 64 files (D145's 63 and `test_republish_queued.py`; JUnit), on f3cd566 | exit 0; 1590 passed in 63 min |
| After the last edit | `ruff format .`, `ruff check .`, `ruff format --check .`; the tests that read the documents and `tests/test_deployment_config.py` (JUnit) | ruff clean (377 files unchanged); exit 0; 195 passed |

The full backend and e2e suites, the Docker smoke test and the Compose execution test run in the
pull request's CI.

## A dropdown's list settled by the page's own record of its last change to a list (D145, 2026-11-11; local only)

Rank 14 of the automation loop. Product changes:

- `app/modules/preparation/gh_readonly.py`: the probe's observer also notes when a change last
  touched a list, and the probe returns it (`list_quiet_ms`). The read-only survey neither uses
  nor publishes it.
- `app/modules/execution/adapters/dropdowns.py`: one more condition before a list counts as
  settled (that record at least half a second old, `STABLE_MS`, or absent), at the check before
  anything is disclosed and at the reading again when an option is chosen; a refusal word of
  its own (`list_changed_recently`); a control that is gone when the observer is installed is
  refused.
- `app/modules/execution/adapters/greenhouse_dom.py`: the location search takes its
  suggestions as settled by the same record.
- `app/modules/execution/policy.py`: a comment only (what version 4 now means; no new version).
- The stand-in (`fixtures/ats_receiver/greenhouse_v2.py`): a list re-rendered only from its
  second opening, an element outside every list that keeps changing, suggestions shown in turn.

No migration, no state, no retry; `SCHEMA_VERSION` and every adapter version unchanged.
Decision, limits and the reviews in D145, evidence in `docs/evidence-matrix.md`.

Found by D143's regression run on a machine shared with two other runs, then reproduced without
load by setting the adapter's reading interval (the rows under D143 below): three identical
reads fall in step with a list re-rendered every 300 ms once the interval reaches about 600 ms.
Built twice: first on the whole document's record (to e81bfeb), then, after an independent
review, on the record of changes that touch a list (from 76da079). The first version's runs are
kept below and marked; they are not evidence for the rule as it now is.
`scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.
Nothing real was run.

| Check (branch `dropdown-settle`) | Command | Result |
|---|---|---|
| First version: the seven cases with the rule removed (before the rule was committed) | `pytest tests/test_dropdown_strategies.py -k "however_slowly or accepted_when_read_slowly or pages_own_record"` (JUnit) | 3 failed (the 590 and 610 ms cases and the rule's own test), 4 passed |
| First version: the seven cases | the same command, on the tree committed seconds later as e81bfeb | exit 0; 7 passed |
| First version: the whole dropdown file | `pytest tests/test_dropdown_strategies.py` (JUnit), on e81bfeb | exit 0; 50 passed |
| First version: each part of the rule changed in turn | 6 changes, one at a time on a committed tree (e81bfeb), the tests run, the file restored | all 6 fail a test; with a page that records nothing refused, 49 of the file's 50 still pass (no stand-in leaves the record empty) |
| First version: the regression set | `pytest` on 63 files (the 62 of D143's set that do not read the documents, and `test_attempt_queue.py`; JUnit), on 15c5e36; the only test run on the machine, with the reviewer's read-only commands during part of it | exit 0; 1564 passed in 55 min |
| The rework: both files | `pytest tests/test_dropdown_strategies.py tests/test_greenhouse_controls.py` (JUnit), on the tree committed seconds later as 76da079 | exit 0; 112 passed (55 and 57) |
| The rework: the observer in a real browser, then it with the three cases on a stand-in for the probe | `pytest tests/test_dropdown_strategies.py -k pages_record_tells`, then `-k "pages_record_tells or pages_own_record or three_equal or gone_before"` (JUnit), on the tree committed a second later as fe9582c | exit 0; 1 passed, then 4 passed |
| The rework: each part of the rule changed in turn | 18 changes, one at a time on a committed tree (fe9582c), the named tests run, the file restored | all 18 fail a test; with a page that records no change to a list refused, the two cases on a stand-in for the probe fail and the dropdown file's other 54 pass (no stand-in leaves that record empty) |
| The rework: a page busy elsewhere within a real page's window (added after the removal runs) | `pytest tests/test_dropdown_strategies.py -k "changing_elsewhere or real_pages_window"` (JUnit); then the new case alone, six times, with the whole page's record put back in the rule and the file restored after (identical); then committed as a080d3d, about two minutes later | exit 0, 3 passed; with that record: failed in 6 of 6 runs (`failed_safe` at a check each time; not independent draws) |
| The rework: the regression set, the only test run on the machine | `pytest` on the same 63 files (JUnit), on a080d3d | exit 0; 1575 passed in 59 min |
| The second review's fixes: both files whole | `pytest tests/test_dropdown_strategies.py tests/test_greenhouse_controls.py` (JUnit), on ae54f21 | exit 0; 116 passed (58 and 58) |
| The second review's fixes, each changed in turn | 2 changes, one at a time on ae54f21, the named tests run, the file restored | both fail their test |
| After the last edit | `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py` (JUnit) | ruff clean (376 files unchanged); exit 0; 178 passed |

The full backend and e2e suites, the Docker smoke test and the Compose execution test run in the
pull request's CI.

## Attempts on a queue and a worker of their own (D144, 2026-11-10; local only)

Rank 11 of the automation loop. Product changes: in `app/worker.py` the two declared queues
(each with its own exchange), the route of `noefforts.execute_attempt` to `attempts`, the rule
that passes on (once) a message for it that arrived on another queue, and the attempts'
worker's own cleanup of stale browser directories; in `docker-compose.yml` the `worker` service
narrowed to the attempts' queue with one process and a new `scheduler` service for the schedule
and the periodic tasks (the API's environment, no runner token, no control socket); the same
for both overlays (`docker-compose.execution-test.yml`, `docker-compose.pilot.yml`);
`scripts/smoke_lib.sh` and `scripts/docker-smoke.sh` (the ping asks both workers by name; the
restore stops both); `compose_tests/run_execution_test.py` (one new scenario, one tightened).
Documents: the deployment guide (two workers, upgrade, rollback with `--remove-orphans`), the
owner's stop controls (`docs/activation-status.md` §8), the architecture and execution-service
pages. No migration, no state, no retry; `SCHEMA_VERSION` and every adapter version unchanged.
Decision and residuals in D144, evidence in `docs/evidence-matrix.md`.

Measured before building: one worker taking every task, both processes held by attempts waiting
for codes, did not take a periodic task for the 20 seconds watched and took it 0.6 seconds after
a code was entered. A probe outside the application: declared by name only, both queues share
the default exchange and key; Celery's own publishing still reaches one queue (it addresses the
queue directly), a publish to that exchange and key by name reaches both, and with an exchange
of its own for each queue it reaches one.
The Compose layout cannot be started here (no Docker daemon): its two CI jobs are its only run;
both passed on the pull request (#53).
`scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.
Nothing real was run.

| Check (branch `attempt-queue`, from D143's branch fa36039) | Command | Result |
|---|---|---|
| The Compose files after the split | `pytest tests/test_deployment_config.py` (JUnit) | exit 0; 17 passed |
| The routing tests that need no worker | `pytest tests/test_attempt_queue.py -k "only_an_attempts_task or marked_as_passed_on or called_directly or stale_browser or one_queue_only"` (JUnit) | exit 0; 5 passed |
| The smoke check on Celery's real reply | `pytest tests/test_attempt_queue.py -k smoke_check` (two real workers named as in the Compose file; JUnit); `scripts/test_smoke_lib.sh` | exit 0, 1 passed; the script: its 12 cases as expected |
| The output the Compose scenario parses (a temporary test, not committed) | the same two workers; `celery -A app.worker inspect active_queues --json --timeout 5` | one line of JSON, one entry per worker: `attempts@…` takes `attempts`, `scheduler@…` takes `celery` |
| The new tests, first full runs | `pytest tests/test_attempt_queue.py` (JUnit) | 6 passed, 4 errors: the module's own fixture had the name of the suite's database cleanup and replaced it, so the second test found the first one's account (renamed); then 9 passed, 1 failed (my assertion counted the test's own reading of the form; it now compares the request log before and after); then exit 0, 10 passed |
| The baseline (a temporary test, not committed) | one real worker taking both queues, two processes, both held in the code wait; a sweep published | not received in the 20 s watched; received 0.6 s after the first code was entered (20.6 s after it was sent) |
| The suites that start real workers or read the Compose files | `pytest tests/test_celery_execution.py tests/test_broker_failures.py tests/test_evidence_lifecycle.py tests/test_deployment_config.py tests/test_attempt_queue.py` (JUnit) | exit 0; 38 passed |
| The recovery suite (its broker checks changed) | `pytest tests/test_recovery_hardening.py` (JUnit) | exit 0; 43 passed |
| Each check removed in turn | 26 changes, one at a time on a committed tree (7f53f71), its test run, the file restored | all 26 fail their test |
| How messages reach queues declared by name only (a probe outside the application, one process per case) | a private Redis; two queues declared by name only, then each with its own exchange; one routed publish, one default, then one to exchange `celery` and key `celery` by name | by name only: 1 and 1, then 2 and 2 (the last reached both; the broker binds both queues under exchange `celery`); own exchange: 1 and 1, then 2 and 1. Celery's own publishes carry no exchange and the queue's name as the key |
| The bindings test, and the by-name declaration against it | `pytest tests/test_attempt_queue.py -k "one_queue_only or only_an_attempts_task or own_exchange_only"` (JUnit); then the declaration changed to names only | exit 0, 3 passed; changed: 2 of the 3 fail (the message test passes either way, as the probe says it should) |
| Lint, format, the smoke-library script, the tests that read the documents and the slice's own, after the last edit | `ruff format .`, `ruff check .`, `ruff format --check .`; `scripts/test_smoke_lib.sh`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py tests/test_deployment_config.py tests/test_attempt_queue.py` (JUnit) | ruff clean (376 files unchanged); the script's 12 cases as expected; exit 0, 206 passed, 0 failures |
| The independent review (a separate reviewer, read-only, on 4788880; nothing run) | every changed file, the installed Celery and kombu sources, the scripts and the Compose harness that only CI runs | no blocker; seven findings, all checked against the code: fixed or recorded (D144) |
| What a stop request does to an application in progress (a temporary test, not committed; a real worker; the signal `docker compose stop` sends first) | the worker told to stop while an application waited before its send gate, and while one waited before its final click | both times the worker was still running 3 s later and the application then finished: `confirmed`, receiver accepted 1; the worker exited after it |
| Whether Redis keeps what waits in it across a stop request (a private `redis-server` 7.0.15 with default settings, outside the application) | two items pushed, the server sent the stop signal, then started again | it saved a snapshot before exiting; the list held 2 items after the restart |
| The review's fixes, the tests that need no real worker | `pytest tests/test_attempt_queue.py tests/test_browser_isolation.py tests/test_deployment_config.py -k "cleanup_that_fails or vanishes_under or stale_browser or called_directly or only_an_attempts_task or marked_as_passed_on or stale_workdirs or test_deployment_config"` (JUnit) | exit 0; 24 passed |
| Each of the review's code fixes removed in turn | 3 changes, one at a time on a committed tree (f62e72d): the cleanup unguarded in the task; the error's text logged instead of its type; a vanished directory an error again | all 3 fail their test |
| The review's fixes, the suites that start real workers, the browser isolation tests and the recovery suite | `pytest tests/test_celery_execution.py tests/test_broker_failures.py tests/test_evidence_lifecycle.py tests/test_deployment_config.py tests/test_attempt_queue.py tests/test_browser_isolation.py tests/test_recovery_hardening.py` (JUnit), on f62e72d | exit 0; 102 passed |
| After the review's last edit | `ruff format .`, `ruff check .`, `ruff format --check .`; `scripts/test_smoke_lib.sh`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py tests/test_deployment_config.py tests/test_attempt_queue.py` (JUnit) | ruff clean (376 files unchanged); the script's 12 cases as expected; exit 0, 208 passed |
| The pull request's CI (#53), on e40ee72 | GitHub Actions: `docker-smoke`, `execution-compose`, `frontend`, `backend` | all four passed (3, 8, 14 and 72 min): the first run of the two-worker Compose layout, with the new scenario and the tightened one; merged as 099642c, tree as predicted |

The full backend and e2e suites, the Docker smoke test and the Compose execution test run in the
pull request's CI.

## Recovery hardening: a run budget, one task time limit, leases that follow progress (D143, 2026-11-10; local only)

Rank 10 of the automation loop. Product changes: the run budget and its checks in
`execution/runner.py` (`within_budget`, `RunBudgetExceeded`, the progress hook); the settings
`attempt_run_budget_seconds` (420) and `attempt_after_send_seconds` (360) and the derived
`attempt_time_limit_seconds` in `core/config.py`; in `app/worker.py` the attempt task's own time
limit, no default soft limit, and the 240-second soft limit set on every other task; in
`execution/service.py` the lease renewal in `record_evidence`, the send lease sized to the
adapter's wait (`_watch_covered`), the lease extension in `take_code`, `close_checkpoints` in
every outcome, the state check in `submit_code`, the sweeper's `close_stale_checkpoints` pass and
the cancel and wizard texts; `send_watch_seconds` and the progress hook in the adapters; the
browser runner's session limit 1500 s (`browser/launcher.js`, `docker-compose.yml`). After the
review (below): the egress proxy's session limit 1500 s (`sandbox/proxy_service.py`,
`docker-compose.yml`); the runner's unthrottled check before each document is handed over and
each wizard page's Next (`on_hand_over`); the Greenhouse watch ended by the clock and
`code_watch_seconds`; `take_code` handing over a code accepted in time and the code wait counted
from the request; the mailbox filler's lock order and its commit per code (`inbox/service.py`);
the cancel text. Test-only: the fault action `elapse`, the points `in_code_wait` and
`between_fields`, the receiver option `verify_delay_s`. No migration, no new state, no retry;
`SCHEMA_VERSION` and every adapter version unchanged. Decision and residuals in D143, evidence
in `docs/evidence-matrix.md`.

The first build kept a soft time limit and handled it by phase. A run with a real worker showed
that a soft limit landing inside a browser wait is never handled (the browser cannot close, the
handler never runs, the process hangs until the hard limit), so the design changed to a budget
the runner checks itself; a second run showed that equal soft and hard limits still fire the
soft one. One independent reviewer then read the build (read-only, on a copy of a83b0ce, whose
product code is what was pushed; told the scope and the rules, not the author's conclusions). It
found no path to a second submission, to a retry after disclosure or sending, or to an outcome
wrong for its phase, and seven things to change: the egress proxy's session (900 s) ended inside
the longer code wait this slice allows; a cancel was seen only at the next throttled renewal,
so a document could still be handed over after it, and the cancel text said more than that;
the Greenhouse watch could outlast the figure its lease was sized to; the mailbox filler locked
a request before its application, the reverse of every outcome since this slice; a code
accepted in the last moment of its wait was erased unused; two tests used leases too short for
a slow machine; nothing pinned that the budget never fires after the send gate. Each was
checked against the code and fixed (bb94e9f), each fix with a test that fails without it.
`scripts/validate.sh all` was not run (it runs the whole backend and e2e suites); ruff was.
Nothing real was run.

| Check (branch `recovery-hardening`, from D142's branch 85e0213) | Command | Result |
|---|---|---|
| The existing execution suites on the first build | `pytest` on 9 files (`test_execution`, `test_execution_failures`, `test_execution_security`, `test_code_wait_quarantine`, `test_workday_wizard`, `test_lock_order`, `test_execution_validation`, `test_disclosure_evidence`, `test_greenhouse_real_mechanics`; JUnit) | exit 0; 185 passed |
| A signal that raises during a browser wait (outside the application) | a script: Playwright's synchronous API, SIGUSR1 raising after 3 s, during `time.sleep`, `wait_for_timeout`, `wait_for_function` and `expect_response` | during `time.sleep`: handled, the browser closed in 0.1 s; during each of the three browser waits the script had not finished after 60 s; for `wait_for_function`, run again with a stack dump: the exception surfaced in the caller at 3.0 s, then `browser.close()` never returned (`_sync_base.py`, `_sync`) |
| The same in the application, first build | a temporary test (not committed): a real Celery prefork worker, soft limit 6 s and hard 66 s, the receiver answering the final click after 45 s | "Soft time limit (6s) exceeded" at 13:58:23, no outcome written, "Hard time limit (66s) exceeded" and SIGKILL at 13:59:23; the attempt still `sending`; receiver ledger: accepted 1 |
| The new tests, first run after the redesign | `pytest tests/test_recovery_hardening.py` (JUnit) | 38 passed, 3 failed: with equal soft and hard limits the worker still logged "Soft time limit (32s) exceeded" (fixed: no soft limit at all); two test bugs (the reply delay was longer than the tests' 4-second submit timeout; four attempts on one posting) |
| The new tests with the existing execution suites and the Celery suite, before the soft-limit handling was dropped | `pytest` on 11 files (the 9 above, `test_recovery_hardening`, `test_celery_execution`; JUnit) | exit 0; 230 passed |
| The new and changed tests on the merged head | `pytest tests/test_recovery_hardening.py tests/test_workday_wizard.py tests/test_code_wait_quarantine.py` (JUnit), on 3930850 | exit 0; 87 passed (38, 44, 5) |
| A cancel while a form is filled (a test added after the runs above) | `pytest tests/test_recovery_hardening.py -k cancel_` (JUnit), on 3930850 with the test uncommitted | exit 0; 3 passed |
| Each check removed in turn | one change at a time on a committed tree (a83b0ce), its test run, the file restored | 31 changes, one at a time: 30 failed their test on the first pass; one did not (a send lease shorter than the submit timeout: the test's bounds were too loose for the tests' 4-second timeout), caught once the test compared the lease exactly (c307576); the three lease changes again: each fails |
| The regression set | `pytest` on the 64 test files that run an attempt or touch what changed (every adapter suite, the execution, recovery, rehearsal, evidence, inbox, notification, deployment-configuration and container-runner suites, the Celery and broker-failure suites, `test_doc_references`, `test_audit_inventory`; JUnit), on a83b0ce | exit 0; 1539 passed, 0 failures (54 min) |
| Lint, format and the tests that read the documents, before the review | `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py` (JUnit) | ruff clean (375 files unchanged); 177 passed, 1 failed (`test_doc_references`: the evidence matrix still cited a test removed with the soft-limit handling; its row removed); then exit 0, 178 passed, 0 failures |
| An independent review of the build | one reviewer, read-only, on a copy of a83b0ce (the later commits before the review changed tests, documents and one docstring) | no blocker; 1 finding to fix (the egress proxy's session), 6 minor; all seven fixed in bb94e9f |
| The review's fixes: the new and changed tests | `pytest tests/test_recovery_hardening.py tests/test_inbox.py -k "outlast or never_stops_a_run or last_moment or hands_over_no_document or watch_ends_by_the_clock or send_lease or sweeper_closes_its_request or while_a_form_is_filled or typed_late"` (JUnit), on the tree then committed as bb94e9f | exit 0; 9 passed |
| The code-wait, quarantine and sweeper tests around the changed `take_code` | `pytest tests/test_recovery_hardening.py tests/test_code_wait_quarantine.py tests/test_execution_security.py -k "last_moment or typed_late or then_ends_is_erased or only_while_its_attempt_waits or code_checkpoint or quarantine or unknown_result or sweeper"` (JUnit), same tree | exit 0; 12 passed |
| Each fix removed in turn | 9 changes, one at a time on the committed tree (bb94e9f): the proxy session's default and its Compose value, the check before a hand-over, the clock's end of the watch, the button wait in the code step's figure, the mailbox's lock order, each half of the last-moment code, a budget check after the send gate; then, again, the three earlier changes whose code or test the fixes touched (the runner not passing the adapter's wait, a code taken without a lease, the Greenhouse figure). Before the review, on 9c92e54, the three changes that the cancel test added after the first pass also covers (no progress hook, each cancel text) | all 15 fail their test |
| The regression set again, on the reviewed code | `pytest` on 62 of the 64 files (without `test_doc_references` and `test_audit_inventory`, which read the documents; JUnit), on bb94e9f, in a worktree left untouched while it runs | started 18:33 UTC and still running when D143's last commit was made. Recorded with D144: exit 1; 1541 passed, 1 failed in 57 min: `test_dropdown_strategies.py`, the `late_slow_changing` case, refused for the wrong reason while two other test runs shared the machine; its cause reproduced without load (rank 14 of the loop); the suite alone on fa36039: 43 passed |
| Lint, format, the tests that read the documents, the lock-order tests and the mailbox tests, after the last edit (the documents and the lock-order note in `execution/service.py`'s docstring) | `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py tests/test_lock_order.py tests/test_inbox.py` (JUnit) | ruff clean (375 files unchanged); exit 0; 270 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI.

## A Workday-style multi-page wizard, filled forward only; never run again once entered (D142, 2026-11-10; local only)

Rank 9 of the automation loop. Product changes: wizard capture (`preparation/workday.py`,
`FormSchema.wizard`, a fingerprint part for wizards only), the package's `wizard` key
(`SCHEMA_VERSION` stays 3: no existing package changes), the step gate and the wizard outcomes in
`execution/service.py` (`gate_before_step`, `quarantine_after_step`, the abandon text and
retirement, the never-again check in approve, queue, enqueue and claim, the sweeper), the page
loop in `execution/runner.py` (`_wizard_pages`, fault points `before_fill_gate_i`,
`before_next_gate_i`, `after_next_ack_i`), the Workday adapter's page methods, adapter version
`fixture-workday-2` (every live `fixture_workday` approval retired once) and the
`multi_step` trait "yes". Two approval reason codes: `wizard_draft_at_employer`,
`wizard_rehearsal_unsupported`. Fixture: the five-page wizard and its variants (FIXTURE
ASSUMPTIONS FA1-FA5). Decision and residuals in D142, evidence in `docs/evidence-matrix.md`.
Sabotage showed three checks no test caught (the page-count rule, the page-order rule,
`require_valid_approval`'s check); two capture cases and a direct call were added, and each
now fails without its check. `scripts/validate.sh all` was not run (it runs the whole backend
and e2e suites); ruff was. After its adversarial review (8 minor findings upheld, all fixed):
a cancel of a wizard attempt past its disclosure gate is refused (`wizard_in_progress`; revoke
stops it), an application entered on a wizard is never re-settled to "Ready for your approval"
or listed for review, and the per-page fingerprint, a question on the review page, the next-page
check, the manual form's refusal, the `wizard_adapter` refusal and the wizard markers on a
single-page package each have a test (fixture variants `page_shift`, `next_stays`). Tests run
are listed in `docs/automation-loop.md`. Nothing real was run.

| Check (branch `workday-wizard`, from D141's branch 2dfc956) | Command | Result |
|---|---|---|
| Non-wizard fingerprints before any edit | `workday.extract_schema` / `extract_form_schema` on the receiver's default Workday-style page and generic form, on 2dfc956 | recorded; pinned in `test_non_wizard_fingerprints_are_unchanged` |
| The new tests | `pytest tests/test_workday_wizard.py` (disposable database, JUnit) | 29 passed, 2 failed (test bugs), fixed: 2 passed; after strengthening, the changed rows: 10 passed |
| Package contract, provider contracts and admission, the existing Workday-style suite | `pytest tests/test_package_contract.py tests/test_provider_contracts.py tests/test_provider_admission.py tests/test_workday_adapter.py` (JUnit) | exit 0; 232 passed |
| Each check removed in turn (42 sabotages, then 6 again) | one change at a time on a committed tree, its row's test run, the file restored | 39 of 42 failed their test; the 3 missed (the page-count rule, the page-order rule, `require_valid_approval`'s check) fail once two cases and a direct call were added (655cce3), as do 3 whose test changed |
| The regression set the build plan names, with the document references | `pytest` on 29 files (`test_workday_wizard`, `test_workday_adapter`, `test_execution_failures`, `test_execution_security`, `test_execution`, `test_disclosure_evidence`, `test_upload_evidence`, `test_form_change_loop`, `test_conditional_questions`, `test_code_wait_quarantine`, `test_lock_order`, `test_gate_snapshot_race`, the four rehearsal suites, `test_approval_reasons`, `test_approval_binding`, `test_approval_hardening`, `test_batch_review`, `test_auto_apply`, `test_evidence_lifecycle`, `test_package_contract`, `test_greenhouse_controls`, `test_provider_contracts`, `test_provider_admission`, `test_lever`, `test_celery_execution`, `test_doc_references`; JUnit), on 655cce3 with the two doc cells of 3bc2179 | exit 0; 659 passed, 0 failures |
| Lint, format, the tests that read the documents and the new tests (after the last edit, before the review) | `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py tests/test_provider_contracts.py tests/test_workday_wizard.py` (JUnit), on 3bc2179 with the docs and the formatting | ruff: 2 files reformatted, all checks passed, 374 files formatted; exit 0; 254 passed (1, 9, 12, 2, 154, 43, 33), 0 failures |
| After the review: the new tests | `pytest tests/test_workday_wizard.py` (JUnit) | 42 passed, 1 failed (test 13's queue call, now refused by the state machine first), fixed: 1 passed |
| After the review: each new or changed check removed in turn (15 sabotages on 98736d1) | one change at a time on a committed tree, its test run, the file restored | every one failed its test |
| After the review: the regression set again | `pytest` on 27 files (the plan's set without the tests that read documents, with `test_sections_review` and `test_version_diff`; JUnit), on 98736d1 | exit 0; 513 passed, 0 failures (26 min) |
| After the review's documents: lint, format and the tests that read the documents | `ruff format .`, `ruff check .`, `ruff format --check .`; `pytest tests/test_doc_references.py tests/test_approval_reasons.py tests/test_lever.py tests/test_audit_inventory.py tests/test_provider_admission.py` (JUnit) | ruff clean (374 files unchanged); exit 0; 178 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI.

## An employment stand-in, and section comboboxes safe on react-select pages (D141, 2026-11-10; local only)

Rank 8 of the automation loop, second half. Product changes: the section combobox filler and the
section readback (`execution/adapters/greenhouse_sections.py`, called from the
`greenhouse_dom` adapter's readback), and `EXTRACTION_VERSION` `greenhouse-dom-v6`, which retires
every live `greenhouse_dom` and `greenhouse_live` approval once (no package hash changes;
`SCHEMA_VERSION` stays 3). Fixture: the employment stand-in and the `section_widget` variants
(FIXTURE ASSUMPTIONS). Decision and residuals in D141, evidence in `docs/evidence-matrix.md`.
After its review a combobox's list is read once it is open (the one real react-select recorded
names none before, D130), the id check before the click and the check of rows beyond the plan
each have a test that fails without them, and a section's refusal names the control, never the
value. Tests run are listed in `docs/automation-loop.md`. Nothing real was run.

| Check (branch `section-widgets`, from D140's branch 08cd8bd) | Command | Result |
|---|---|---|
| The existing section suites on the new stand-in, then with the new filler | `pytest tests/test_greenhouse_sections_e2e.py tests/test_greenhouse_sections_browser.py tests/test_greenhouse_sections_hardening.py tests/test_greenhouse_sections.py` (disposable database, JUnit) | exit 0; 72 passed; 72 passed |
| The new tests | `pytest tests/test_section_widgets.py` (JUnit) | exit 0; 8 passed |
| The new tests with the version-pinned suites at v6 | `pytest tests/test_section_widgets.py tests/test_greenhouse_sections_e2e.py tests/test_approval_binding.py tests/test_phone_companion.py tests/test_greenhouse_sections_browser.py` (JUnit) | exit 0; 118 passed |
| Each change removed in turn (3 cases) | one change at a time, the new tests run, the file restored | the old typing filler restored: 3 fail; the section readback removed: 1; both id checks removed: 1 |
| Every suite that loads the second Greenhouse-style fixture or binds an approval to an adapter version | `pytest` on the files in the run's list (JUnit) | to run; recorded here when it ends |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 373 files formatted; JUnit 49 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI.

## Education and work history reviewable and diffed; a record edit retires its approvals at once (D140, 2026-11-10; local only)

Rank 8 of the automation loop, first half. Product changes: the review page's "Education and
work history" card and the section rows of the version diff (`package.diff_contents`,
`_summarize`), and the eager retirement after an education or employment edit
(`package.retire_after_section_record`, called by the profile record routes). `SCHEMA_VERSION`
stays 3: no package content changes. The gap was mapped read-only on D139's branch (84af539)
before building; decision and residuals in D140, evidence in `docs/evidence-matrix.md`. Nothing
real was run.

| Check (branch `sections-review`, from D139's branch 84af539) | Command | Result |
|---|---|---|
| The new API tests with the section-package and diff suites | `pytest tests/test_sections_review.py tests/test_greenhouse_sections_package.py tests/test_version_diff.py` (disposable database, JUnit) | exit 0; 18 passed; then `test_sections_review.py` with the notice check: 7 passed |
| The section stand-in end to end, with the two new ledger tests | `pytest tests/test_greenhouse_sections_e2e.py` (JUnit) | exit 0; 9 passed |
| The package contract with section packages | `pytest tests/test_package_contract.py` (JUnit) | exit 0; 3 passed |
| Each change removed in turn (4 cases) | one change at a time, the four files run, the file restored | the eager retirement removed: 2 fail; the section diff removed: 3; the section summary removed: 1; the gate's hash check removed: 1 |
| The review page | `npx playwright test e2e/sections-review.spec.ts` (desktop and mobile; `noefforts_e2e_test`) | exit 0; 2 passed; after the review, 2 passed |
| After the review: the new route, scope and status tests | `pytest tests/test_sections_review.py tests/test_version_diff.py` (JUnit) | exit 0; 20 passed |
| The review's fixes removed in turn (6 cases) | each route's hook alone, the account scope, the "needs you" status | each fails its test: create 2, update 1, approve 1, delete 1; scope 1; status 2 |
| Frontend checks | `npx tsc --noEmit`, `npm run lint` | exit 0, exit 0 |
| Every suite that touches sections, profiles, packages, approvals or diffs, with the standing-rule, mutation-table and document suites (55 files), on edb22b8 (the review's fixes, 9d0066d, ran in their own rows above) | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 3252 tests, 3252 passed, 0 failures (32 min 34 s) |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 372 files formatted; JUnit 49 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI.

## Your self-identification on Greenhouse- and Workday-shaped forms; a change retires its approvals at once (D139, 2026-11-10; local only)

Rank 7 of the automation loop. One product change: `PUT /profile/self-identification` retires
the approvals of what a change alters at once (`package.retire_after_self_identification`) and
returns `applications_to_approve_again`, which the profile page shows; `SCHEMA_VERSION` stays 3.
The rest is fixtures and tests. The gap was mapped read-only on D138's branch (e3e584a) before
building; decision, fixture assumptions and residuals in D139, evidence in
`docs/evidence-matrix.md`. Nothing real was run.

| Check (branch `self-id-ledger`, from D138's branch e3e584a) | Command | Result |
|---|---|---|
| The new tests | `pytest tests/test_self_identification_ledger.py` (disposable database, JUnit) | exit 0; 25 passed; the review's added test (a save also retires an approval already out of date): 1 passed |
| The standing-rule and mutation-table cases, then the neighbouring suites in full | `pytest tests/test_auto_apply.py tests/test_execution_validation.py -k self_identification`; then those two with `test_self_identification.py`, `test_greenhouse_dom.py`, `test_workday_adapter.py` (JUnit) | exit 0; 3 passed; then 154 passed |
| Each change removed in turn (5 cases) | one change at a time, the D139 tests and the selected cases of the two suites run, the file restored | the eager retirement removed: 9 fail; the gate's hash check removed: 2; self-identification run before "Don't disclose": 3; "I do not wish to answer" removed from the decline wordings: 2; the "names a category" rule removed: 1 |
| The profile page | `npx playwright test e2e/self-identification.spec.ts` (desktop and mobile; `noefforts_e2e_test`) | exit 0; 6 passed; with the eager retirement removed, the new test fails on both projects (2 failed, 4 passed); after the review (its title corrected): 6 passed |
| Frontend checks | `npx tsc --noEmit`, `npm run lint` | exit 0, exit 0 |
| Every suite that touches self-identification, the profile, packages and approvals, or either fixture, with the documents suites (70 files), on the code committed as 71b659d | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 2637 tests, 2637 passed, 0 failures (54 min 59 s) |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 371 files already formatted; JUnit 49 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI.

## Saved answers on Greenhouse- and Workday-shaped forms, shown up to the employer (D138, 2026-11-10; local only)

Rank 6 of the automation loop. Tests and fixtures only; no product code changed and `SCHEMA_VERSION`
stays 3. Decision, fixture assumptions and residuals in D138, evidence in `docs/evidence-matrix.md`.
Nothing real was run.

| Check (branch `provider-reuse`, from D137's branch 035a085; D137's later commits merged in; merged as #47, a7f8742, its PR CI green on all four jobs at ea11c6e) | Command | Result |
|---|---|---|
| The new tests | `pytest tests/test_provider_reuse.py` (disposable database, JUnit) | exit 0; 4 passed (before and after the review's fixes) |
| Each check removed in turn, at bfba231 (7 cases) | one change at a time, the 4 tests run, the file restored | reuse from saved answers switched off: 3 of 4 fail; the saved-answer scope check switched off: 1 (the shift test); all three of the shift's rules removed: 1 (the shift test); reuse keyed on the first 36 characters of the wording: 1 (the look-alike test); any one of the shift's three rules removed alone: 0, as D138 states |
| The suites that use the fixtures it extends, before the review (8 files) | `pytest` on the bank, Greenhouse DOM and live, Workday, answer-brain, API-provider and bank-edit suites with the new tests (JUnit) | exit 0; JUnit 1325 tests, 1325 passed, 0 failures |
| Every suite that loads the Greenhouse-style id-only or Workday-style fixture, with the bank, answer-brain, bank-edit and document suites, at bfba231 (44 files) | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 2210 tests, 2210 passed, 0 failures (41 min 44 s) |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 370 files already formatted; JUnit 49 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI. No frontend file changed.

## What reached the employer stays recorded whatever fails after it (D137, 2026-11-10; local only)

Rank 5 of the automation loop, second half; merged as #46 (e2fd286), its PR CI green on all four
jobs (a9b6880, CI #276). The gap was mapped on D136's branch (9602bda, the same
code as `main` 53b28af) before building; decision and residuals in D137, evidence in
`docs/evidence-matrix.md`. Nothing real was run.

| Check (branch `disclosure-evidence`, from 9602bda) | Command | Result |
|---|---|---|
| The new tests | `pytest tests/test_disclosure_evidence.py` (disposable database) | exit 0; 7 passed |
| Each change removed in turn (4 cases) | one change at a time, the 7 tests run, the file restored | the recorder not installed: 4 of 7 fail; an interrupted upload not converted: 1; the API's unanswered upload not converted: 1; disclosures recorded again after filling: 1 |
| Every suite that runs an attempt or uses an adapter, with the Celery and broker-failure suites (63 files) | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 1500 tests, 1500 passed, 0 failures (40 min 34 s) |
| At the commit (7972e4b) | `pytest tests/test_disclosure_evidence.py tests/test_upload_evidence.py tests/test_greenhouse_sections_e2e.py tests/test_rehearsal.py` (JUnit) | exit 0; JUnit 31 tests, 31 passed, 0 failures |
| After both review rounds: the new tests | `pytest tests/test_disclosure_evidence.py` (JUnit) | exit 0; JUnit 24 tests, 24 passed, 0 failures |
| Each review fix removed in turn (8 cases) | one change at a time, the tests run, the file restored | a followed API redirect counted as refused: 2 of 15 fail; a draft the API answered with an error left unrecorded: 1 of 15; an interrupted upload converted before the hand-over: 1 of 15; the hand-over mark removed from the id-only page, the hosted form and the first Greenhouse-style page: 1 of 15 each; the cause's log removed: 1 of 15; the generic form's hand-over mark removed: 2 of 24 |
| The same 63 files, after both review rounds | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 1508 tests, 1508 passed, 0 failures (49 min 15 s) |
| At the commit (929f94b) | `pytest tests/test_disclosure_evidence.py tests/test_upload_evidence.py tests/test_api_provider.py tests/test_greenhouse_sections_e2e.py tests/test_rehearsal.py` (JUnit) | exit 0; JUnit 64 tests, 64 passed, 0 failures |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 369 files already formatted; JUnit 49 passed, 0 failures |

The full backend and e2e suites run in the pull request's CI. No frontend file changed.

## A control NoEfforts cannot fill is refused when the form is read (D136, 2026-11-10; local only)

Rank 5 of the automation loop, first half. The gaps were mapped on `main` 53b28af before building;
decision, residuals and fixture assumptions in D136, evidence in `docs/evidence-matrix.md`. Nothing
real was run.

| Check (branch `capture-refusals`, from `main` 53b28af) | Command | Result |
|---|---|---|
| The new tests | `pytest tests/test_capture_refusals.py` (disposable database, alternate ports) | exit 0; 5 passed, then 6 with the optional dropdown's test |
| The optional native dropdown before the change | the sixth test with the reading step's refusal removed, printing the attempt | `failed_safe`: "Stopped before sending anything: the form has changed since you approved it (1 changed: widget)"; no disclosure in the receiver's ledger |
| Each change removed in turn (3 cases) | one change at a time, the 6 tests run, the file restored | the reading step's refusal removed: 5 of 6 fail; the native-dropdown rule removed: 4 of 6; the adapter given its own list, with the checkbox added: 1 of 6 (the shared-list test) |
| Every suite that loads the second Greenhouse-style fixture or reads a Greenhouse form (48 files; the new file with its first 5 tests) | `pytest` on the files in the run's list (JUnit) | exit 0; JUnit 1373 tests, 1373 passed, 0 failures (39 min 38 s) |
| At the commit (f406fe8), after formatting | `pytest tests/test_capture_refusals.py tests/test_greenhouse_dom.py` (JUnit) | exit 0; JUnit 65 tests, 65 passed, 0 failures |
| Lint, format, the tests that read the documents (after the last edit) | `ruff check .`, `ruff format --check .`, `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_provider_contracts.py tests/test_package_contract.py` | exit 0; ruff: all checks passed, 368 files already formatted; JUnit 49 passed, 0 failures |

Merged as #45 (32c8f7c, tree as predicted); its CI passed all four jobs on 9602bda. No frontend file
changed.

## A question the page shows after an earlier answer (D135, 2026-11-09; local only)

Rank 4 of the automation loop, first half. The gaps were mapped on `main` 2e10418 before building;
decision, residuals and fixture assumptions in D135, evidence in `docs/evidence-matrix.md`. Nothing
real was run.

| Check (branch `conditional-pauses`, from `main` 2e10418) | Command | Result |
|---|---|---|
| The new tests | `pytest tests/test_conditional_questions.py` (disposable database, alternate ports) | exit 0; 9 passed |
| Every suite that loads the second Greenhouse-style fixture, with the pause, resolution, migration, export and audit suites (47 files) | `pytest` on the files in the run's list (JUnit) | JUnit 1079 tests: 1078 passed, 1 failed: `test_preferred_name_and_unknown_condition_are_not_guessed` checked the old wording for the hidden question (now: still never guessed, answerable, explained as shown only after an earlier answer); after updating it, with the new tests and `test_notifications.py`: exit 0, 22 passed |
| Each change removed in turn (8 cases) | one change at a time, its tests run, the file restored (checksum compared) | each fails its tests: never answerable; a saved answer or draft kept; no late fill pass; filled even when hidden (the fill times out); a revealed required one a plain stop; the runner never pausing; trying again unguarded; the pause never asking |
| The pause cards (Questions and the application's page), with the specs that use the same form or cards | `npx playwright test e2e/conditional-pause.spec.ts e2e/questions.spec.ts e2e/journey.spec.ts e2e/submission.spec.ts --grep "reveals and requires\|form that changes\|another account\|journey\|Greenhouse-style v2"` (desktop and mobile, a fresh build) | exit 0; JUnit 10 tests, 10 passed, 0 failures |
| Lint, format, types, the tests that read the documents (after the last edit) | `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_authorizations.py tests/test_provider_contracts.py tests/test_provider_admission.py tests/test_package_contract.py`, `ruff check .`, `ruff format --check .`, `npx tsc --noEmit`, `npm run lint` | exit 0; JUnit 218 passed, 0 failures (the new tests again, after formatting); ruff: all checks passed, 367 files already formatted; tsc exit 0; eslint exit 0 |

The full backend and e2e suites run in the pull request's CI.

## Your pause and your revocation reach what the standing rule queued (D134, 2026-11-09; local only)

Rank 3 of the automation loop. Each gap was found by a read-only map of the code before building;
decision, residuals and owner decisions in D134, evidence in `docs/evidence-matrix.md`. Nothing real
was run: every recorded permission ended on 2026-11-06.

| Check (branch `rule-respects-owner`, from `main` ab671e1) | Command | Result |
|---|---|---|
| The rule's tests | `pytest tests/test_auto_apply.py` (disposable database, alternate ports) | exit 0; 18 passed (8 new) |
| Suites the change touches (17 files) | `pytest tests/test_auto_apply.py tests/test_account.py tests/test_audit_inventory.py tests/test_migrations.py tests/test_lock_order.py tests/test_execution_failures.py tests/test_execution_validation.py tests/test_form_change_loop.py tests/test_notifications.py tests/test_rehearsal.py tests/test_rehearsal_prerequisite.py tests/test_rehearsal_stop.py tests/test_approval_reasons.py tests/test_gate_snapshot_race.py tests/test_document_deletion.py tests/test_deployment_config.py tests/test_preparation.py` | JUnit 304 tests: 303 passed, 1 failed (`test_audit_inventory.py`: the pause's audit row hid its keys); fixed, then `test_audit_inventory.py` and `test_auto_apply.py`: exit 0, 20 passed |
| Each change removed in turn (7 cases) | one change restored at a time, its tests run | each fails its tests: the pause stopping nothing (2 tests), no check when a worker takes an attempt (2), no re-check per step (1), the revocation overridden (1), never continuing after a pause (1), the pause stopping your own work (1), the pause reaching other accounts (1) |
| Frontend | `npm run lint`, `npx tsc --noEmit` | exit 0, exit 0 |
| After merging `main` (D133, da7ac61): the 17 suites plus `test_greenhouse_dom.py` (D133's screening job goes through approval, queueing and a worker's claim) | `pytest` (JUnit, disposable database, alternate ports) | exit 0; JUnit 363 tests, 363 passed, 0 failures (14 min) |
| A held attempt stopped by a pause, then resumed (added after the merge) | `pytest tests/test_auto_apply.py` (disposable database, alternate ports) | exit 0; JUnit 18 passed, 0 failures |
| The resume fails without its change | `_paused_before_entry` made to return False, that test run alone, the file restored after (checksum compared) | exit 1: fails at the resume, the rule queueing nothing (0, not 1) |
| The Tracker's card | `npx playwright test e2e/auto-apply-pause.spec.ts` (desktop and mobile) | exit 0; JUnit 2 tests, 2 passed, 0 failures (a fresh build of this tree) |
| The tests that read the documents, lint, format, types (after the last edit) | `pytest tests/test_doc_references.py tests/test_audit_inventory.py tests/test_authorizations.py tests/test_provider_contracts.py tests/test_provider_admission.py tests/test_package_contract.py`, `ruff check .`, `ruff format --check .`, `npx tsc --noEmit`, `npm run lint` | exit 0; JUnit 209 passed, 0 failures; ruff: all checks passed, 365 files already formatted; tsc exit 0; eslint exit 0 |

The full backend and e2e suites ran in the pull request's CI and passed on all four jobs at
118b4b9; merged as #43 (2e10418).

## Reuse and suggestion guards (D133, 2026-11-06; local only)

Rank 2 of the automation loop. Each finding was reproduced on `main` (bd38529) by a probe or a test
before fixing; decision and residuals in D133, rules in `docs/answer-policy.md` rows 2 and 5,
evidence in `docs/evidence-matrix.md`. Nothing real was run; the screening job is a local fixture
assumption.

| Check (branch `suggestion-guards`, from `main` bd38529) | Command | Result |
|---|---|---|
| Focused backend suites | `pytest tests/test_answer_brain.py tests/test_answer_brain_rules.py tests/test_bank_scope.py tests/test_bank_scope_api.py tests/test_disclosure_ledger.py tests/test_self_identification.py tests/test_question_safety.py tests/test_question_safety_api.py tests/test_resolver.py tests/test_greenhouse_dom.py tests/test_bank_edit.py tests/test_bank_import.py tests/test_preparation.py tests/test_classify_vocabulary.py` (disposable database, alternate ports) | exit 0; JUnit 2543 tests, 2543 passed, 0 failures (9 min) |
| Every suite that uses the second Greenhouse-style fixture, with the screening job added | `pytest` on the 31 test files that load `greenhouse_v2` | exit 0; 898 passed (30 min) |
| Each test fails without its change | step 1's row with `resolver.py` at bd38529; steps 2-3 with the six app files D131 changed restored to c4503cf; step 4 with the previous `learning/service.py`; step 5 with the previous `features.py`; step 6 with step 5's scoring; step 7 with the previous router; step 9 without `error.jsx` | each fails: the decline row; the self-identification test (47 rows in a per-row copy), three `c5.selfid` rows, corpus row `r8_10_prevent_work_help_disability`, both screening runs; 7 suggestion tests; 44 veto tests; 5 score tests; 2 verdict tests; the error-boundary spec |
| E2E | `npx playwright test e2e/answer-suggestions.spec.ts e2e/error-boundary.spec.ts e2e/phase-b.spec.ts e2e/answers-edit.spec.ts e2e/review-reasons.spec.ts e2e/review-edit.spec.ts e2e/journey.spec.ts e2e/self-identification.spec.ts e2e/drafts.spec.ts e2e/drafting-consent.spec.ts e2e/submission.spec.ts e2e/profile-edit.spec.ts` (desktop and mobile, disposable database) | exit 0; JUnit 56 tests, 56 passed, 0 failures |
| Lint, format, types | `scripts/validate.sh quick` | exit 0 (ruff: all checks passed; 360 files already formatted; tsc; eslint) |
| After merging `main` (D132, c19c683): the suites both touch | `pytest tests/test_form_change_loop.py tests/test_greenhouse_dom.py tests/test_greenhouse_adapter.py tests/test_answer_brain.py tests/test_answer_brain_rules.py tests/test_auto_apply.py tests/test_self_identification.py tests/test_disclosure_ledger.py tests/test_notifications.py tests/test_question_safety.py tests/test_resolver.py` | exit 0; JUnit 1300 passed, 0 failures |
| After merging `main`: e2e | `npx playwright test e2e/answer-suggestions.spec.ts e2e/error-boundary.spec.ts e2e/questions.spec.ts e2e/review-edit.spec.ts e2e/submission.spec.ts e2e/layout-regression.spec.ts e2e/self-identification.spec.ts e2e/phase-b.spec.ts` (desktop and mobile) | exit 0; 51 passed, 1 skipped by design |
| Adversarial review fixes (D133, "Adversarial review"): the 14 focused files plus `test_classify_vocabulary.py` | `pytest` (disposable database, alternate ports) | exit 0; JUnit 2581 passed, 0 failures |
| Each review fix's test fails without it | `features.py`, `service.py`, `resolver.py` and `classify.py` restored to 1b5cc0b in turn | 39, 1, 3 and 1 tests fail |

The full backend and e2e suites ran in the pull request's CI and passed on all four jobs at 360f34c;
merged as #41 (da7ac61).

## A form that no longer matches pauses the application; Questions needing your answer (D132, 2026-11-06; local only)

**partial** — built and tested on local fixtures only (the gh2 Greenhouse-style approximation by id
and through the pilot path, the Workday-style approximation in the e2e). No real page was read,
opened, filled or submitted. Decision: D132.

What it does:
- A change a fresh read of the form can show (a question added, gone, reworded or retyped, other
  options, a section gone) now pauses the application. The run stops before anything is sent,
  every live approval is retired, and the pause is recorded. Nothing is approved for the
  application until it is resolved.
- "Questions needing your answer" (`/questions`) lists it. "Read the form again" brings the new
  question through the same capture route (and its permission checks). Once you answer and
  approve, exactly one new run fills it.
- "Try this version again" ends the pause; the page is checked again before anything is entered.
- What only the running page shows about the questions the form lists stays a plain stop, as
  before. A control the form does not list pauses however it appeared; one added only by the page's
  script cannot be seen by a read, so the read ends "unexplained". A change found after filling is
  abandoned as before, now with every approval retired, so entering the data again is a new
  approval.

| Check (branch `form-change-pause`) | Command | Result |
|---|---|---|
| Existing suites that cover drift stops, approval, notifications, auto-apply, contracts and migrations, first build (d197bb7) | `pytest` on test_account, test_approval_hardening, test_approval_reasons, test_ashby_adapter, test_audit_inventory, test_auto_apply, test_batch_review, test_dropdown_strategies, test_error_boundary, test_execution_failures, test_execution_security, test_form_change_loop, test_greenhouse_adapter, test_greenhouse_controls, test_greenhouse_dom, test_greenhouse_live, test_greenhouse_sections_e2e, test_hidden_search, test_lever_adapter, test_migrations, test_notifications, test_phone_companion, test_preparation, test_rehearsal_stop, test_required_signals, test_section_free_route, test_workday_adapter (disposable database) | JUnit 665 tests, 663 passed, 2 failed: `test_auto_apply.py::test_a_stopped_attempt_is_never_retried_automatically` (a form-change stop now has its own skip reason; the test now covers a plain stop and a pause apart) and `test_notifications.py::test_every_query_of_the_feed_is_scoped_to_the_account` (its guard now counts D132's three account-scoped queries) |
| The same suites plus test_api_provider and test_rehearsal, after the rework (730f1b6) | the same, 29 files | exit 0; JUnit 693 tests, 693 passed, 0 failures, 0 errors (1637 s) |
| After merging `main` (f7a54e4): D132 and contract suites | `pytest tests/test_form_change_loop.py tests/test_auto_apply.py tests/test_notifications.py tests/test_migrations.py tests/test_account.py tests/test_audit_inventory.py tests/test_approval_reasons.py` | exit 0, 85 passed |
| Full e2e on the merged tree (f7a54e4) | `npx playwright test` (desktop and mobile, disposable database) | exit 0; JUnit 173 tests, 170 passed, 0 failures, 3 skipped by design (the bottom-nav check runs on mobile only, the two log-privacy configuration checks on desktop only); 777.9 s |
| Race fixes (fb00d8c): the two two-connection race tests, then the same with the pause's row lock removed | `pytest tests/test_form_change_loop.py -k during` | exit 0 with the lock; without it both fail ("the read did not wait for the pause's lock") |
| Head (76588f8) | `pytest tests/test_form_change_loop.py tests/test_auto_apply.py tests/test_notifications.py tests/test_lock_order.py`; `npx playwright test e2e/questions.spec.ts e2e/layout-regression.spec.ts e2e/notifications.spec.ts e2e/tracker-outcomes.spec.ts` | exit 0, 74 passed; exit 0, 15 passed, 1 skipped by design |
| PR #40 CI on d2851c6 | the backend job | 2 failed, 4828 passed: `test_audit_repair` (the migration's message named "the employer's form", a word that test keeps out of migration output) and `test_phase_a_verification::test_concurrent_writers_conflict_instead_of_overwriting` (the conflict now surfaces at `transition()`'s flush); both reproduced locally on d2851c6, both pass after 6b01b2e |
| The rework review's open findings (sensitive rows decided on the application's page; the tracker's refused actions hidden while an attempt holds the application; tests for structural drift, a missing section, the pre-read refusal, the job page's dedupe commit, the ever-paused guard after a rehearsal, the waiting state and batch review, a script-added control) | `pytest tests/test_form_change_loop.py tests/test_auto_apply.py tests/test_greenhouse_adapter.py tests/test_phase_a_verification.py tests/test_audit_repair.py tests/test_notifications.py tests/test_migrations.py tests/test_greenhouse_dom.py tests/test_greenhouse_sections_e2e.py` (disposable database); each new test run once with its mutation (sensitive rows answerable, no pre-read attempt check, no dedupe commit, guard only while unresolved); `npx playwright test e2e/questions.spec.ts e2e/submission.spec.ts e2e/follow-ups.spec.ts e2e/tracker-outcomes.spec.ts` | exit 0; JUnit 181 passed; each mutation fails its test; e2e JUnit 34 passed, 0 failures |
| Lint and format | `uv run ruff check .`, `uv run ruff format --check .` | exit 0 ("All checks passed!"), exit 0 (362 files already formatted) |
| Frontend | `npx tsc --noEmit`, `npm run lint` | exit 0, exit 0 |

Reviews: three independent design critiques and a reconciling lead (the design was changed: the
gate holds the application, structural drift pauses, approvals are retired after entry); a three-lens
implementation review of the first build (five confirmed findings, all fixed); a four-lens review of
the rework (its verifiers were cut off by a usage limit; each finding was checked against the code:
four fixed, one narrowed in the docs as an open owner decision). The full backend suite runs in the
pull request's CI.

## Answer safety: self-identification scope, follow-up reuse, job requirements (D131, 2026-11-06; local only)

Found by the first acceptance inventory of the Greenhouse + Workday loop and reproduced on `main`
(b194438) before fixing: with self-identification on and "No" among its labels, a required felony
question and an accommodation question resolved to "No" from it; "Which one?" saved after a language
question answered "Which one?" after another question; "Do you meet all minimum qualifications?" was
reusable; the review page failed on a self-identified answer. Decision and rules: D131,
`docs/answer-policy.md` rows 2 and 5.

| Check (branch `answer-safety-self-id`, on `main` b194438) | Command | Result |
|---|---|---|
| New tests fail on `main` without the fix | the new and changed backend test files copied onto a detached `main` worktree; `pytest tests/test_self_identification.py tests/test_bank_scope.py tests/test_bank_scope_api.py` | 14 failed: the felony/accommodation, bare-label, five requirement-wording and follow-up reuse tests, and the key tests because `main` has no follow-up trigger (the worktree was then removed) |
| Review page on `main` | `npx playwright test e2e/self-identification.spec.ts --project=desktop` on that worktree | failed: the page showed "Application error: a client-side exception has occurred" |
| Focused backend suites with the fix | `pytest tests/test_self_identification.py tests/test_bank_scope.py tests/test_bank_scope_api.py tests/test_question_safety.py tests/test_question_safety_api.py tests/test_resolver.py tests/test_answer_brain.py tests/test_bank_edit.py tests/test_bank_import.py tests/test_preparation.py` (disposable database) | first commit: exit 0, JUnit 1926 passed; after the adversarial review's fixes (scope, decline rule, chain keys, second-level saves, no follow-up suggestions): exit 0, JUnit 1934 tests, 1934 passed, 0 failures, 0 errors, 0 skipped |
| Lint and format | `uv run ruff check .`, `uv run ruff format --check .` | all checks passed; 353 files already formatted |
| Frontend | `npx tsc --noEmit`, `npm run lint` | exit 0, exit 0 |
| Review page with the fix | `npx playwright test e2e/self-identification.spec.ts e2e/review-reasons.spec.ts` (desktop and mobile) | 4 passed |

The full backend and e2e suites run in the pull request's CI. Nothing real was run; no employer page
was read or touched.

### D131 follow-up: the review's remaining findings (branch `answer-safety-followup`)

The review's verifiers stopped at a usage limit, so each remaining finding was reproduced by a probe
on the D131 branch (65ca027) before fixing:
- 9 of 13 job-requirement wordings were still reusable ("all of the", "met", "the education
  requirements", "the selection criteria", "the required degree" …);
- "basic skills in Microsoft Excel", "key skills", "essential skills" and "experience meeting
  requirements for SOX compliance" were refused as about the job;
- four "documents / paperwork to work in ‹country›" wordings were reusable;
- five vaccination wordings were neither sensitive nor refused.

Decision: D131's follow-up bullet. Rules: `docs/answer-policy.md` rows 2, 2a and 5.

| Check | Command | Result |
|---|---|---|
| Probe after the fix | the same probe script | every requirement wording refused (`employer`), the four skill wordings reusable, the work-document wordings `fact` and legal status, the vaccination wordings health; with a saved answer stored under each wording's own key, none of the refused ones was answered from it |
| Focused backend suites | `pytest tests/test_self_identification.py tests/test_bank_scope.py tests/test_bank_scope_api.py tests/test_question_safety.py tests/test_question_safety_api.py tests/test_resolver.py tests/test_answer_brain.py tests/test_bank_edit.py tests/test_bank_import.py tests/test_preparation.py tests/test_classify_vocabulary.py tests/test_classify_archive_wordings.py tests/test_drafting.py tests/test_credentials.py tests/test_hidden_search.py tests/test_package_contract.py tests/test_sending.py tests/test_greenhouse_api_coverage.py tests/test_widget_detector.py tests/test_approval_hardening.py tests/test_disclosure_ledger.py tests/test_after_send_diagnostics.py tests/test_inbox.py tests/test_inbox_tracking.py tests/test_greenhouse_controls.py tests/test_greenhouse_sections_package.py tests/test_phone_companion.py` (every suite that exercises the classifier, the bank rules or the resolver) (disposable database) | exit 0; JUnit 2596 tests, 2596 passed, 0 failures, 0 errors, 0 skipped; 861.4 s |
| Lint and format | `uv run ruff check .`, `uv run ruff format --check .` | exit 0 ("All checks passed!"), exit 0 (359 files already formatted) |
| Frontend | `npx tsc --noEmit`, `npm run lint` | exit 0, exit 0 |
| E2E | `npx playwright test e2e/self-identification.spec.ts e2e/profile-edit.spec.ts` (desktop and mobile) | exit 0, 6 passed |

## Section-free Greenhouse path: locked identity (D129), optional phone left blank (D130), configured test ports (2026-11-05; local only, nothing real run)

**partial** — complete locally on three unmerged branches; nothing is on `main`. GitHub Actions has
not run since 2026-11-05 00:40 UTC (runs #232 and #233 ended 4–5 s after starting, no step
executed); none was triggered. No real page was read, opened, filled or submitted, and no
operational permission was used or requested.

| Branch | Head | Content | Local validation (commands actually run) |
|---|---|---|---|
| `greenhouse-identity-prefill` (D129) | `a4bdbd0` | a locked, pre-filled identity is verified before disclosure | `scripts/validate.sh lint format backend` with test ports 8891–8893: lint 0, format 0, backend 1 — JUnit 4603 tests, 4602 passed, 1 failure (`test_container_runner.py::test_proxy_requires_a_session_and_keeps_sessions_apart`, HTTP 502: the test hard-coded receiver port 8799; reproduced — passes at default ports, fails at overridden ones; fixed on `test-ports-configured`; the suite was not re-run to change the tally). E2E: exit 0 — JUnit 165 tests, 162 passed, 0 failures, 0 errors, 3 skipped (the same three); 694.1 s |
| `test-ports-configured` (from `main`) | `0049b05` | the container-runner tests use the run's configured receiver and canary ports (test-only) | Before (`9a7f390`, ports 8891–8893): the proxy test fails (502); with 8798 occupied the two canary tests fail. After: default ports 18/18; ports 8891–8893 with 8798 and 8799 occupied by idle listeners 18/18 (JUnit). Repo-wide `ruff check .` / `ruff format --check .` clean |
| `greenhouse-phone-companion` (D130, on D129) | `df752d6` | an optional phone is left blank beside a second control NoEfforts cannot set; extraction v4; version tripwire | `scripts/validate.sh lint format backend` (default test ports, clean tree): lint 0, format 0, backend 0, validator 0 ("validation passed") — JUnit 4671 tests, 4671 passed, 0 failures, 0 errors, 0 skipped, 4127.2 s (D129's 4603 plus D130's 68). E2E: exit 0 — JUnit 165 tests, 162 passed, 0 failures, 0 errors, 3 skipped by design — each a project-conditional skip: the bottom-nav check runs on the mobile project only, the two log-privacy configuration checks on desktop only; 704.6 s (`50f25e0`, code identical to `df752d6`) |

`greenhouse-structured-sections` (D120) stays at `c9e7b8e` as reported (4675/4675). E2E (same command): exit 0 — JUnit 165 tests, 162 passed, 0 failures, 0 errors, 3 skipped (the same three by-design skips); 699.1 s.

**Integration order** (only through the repository's checks, once Actions runs; nothing merged on
a red or missing CI): D129 → `test-ports-configured` (independent) → D130 (merge `main` first,
re-run backend and e2e) → D120 updated against the resulting `main`: its `EXTRACTION_VERSION`
must move to v5 (git merges the two identical v4 lines silently; D130's
`test_one_extraction_version_never_names_two_behaviours` fails until it moves), then backend and
e2e on the integrated head before merging. A discarded trial merge forecast five mechanical
conflict hunks: `preparation/greenhouse_dom.py` (version comment; the `unlisted` list in
`build_schema`), `adapters/greenhouse_dom.py` (the `new` filter), `tests/test_greenhouse_controls.py`
(docstring; version assertion).

## Complete job information: structured, sanitized ingestion with salary provenance (D126, 2026-11-03; local only)

The D125 premium pass asked that a job's full detail be preserved and presented, not reduced to a
500-character teaser. This is the backend slice (branch `feature/complete-job-information`, off
`main`/`cb4dc5e`); the premium job-detail view that renders it is a separate frontend change that
lands after the motion/palette PR.

- **New `app/modules/discovery/content.py`:** an HTML→safe-blocks sanitizer (stdlib `html.parser`,
  no new dependency, no network) and a salary reader. HTML becomes a list of plain blocks (heading /
  paragraph / list) with inline text, emphasis and safe links only; scripts, styles, images and
  other media, frames, `svg`, forms and controls, and every attribute but a link's `href` are
  dropped; a link survives only for http(s)/mailto. Blocks render later as elements, never as raw
  HTML, so no embedded asset is fetched and nothing executes. Output is bounded.
- **Salary with provenance, never invented:** Lever `salaryRange`/`salaryDescription` →
  `structured` (the pay fields D95 left "until there is a design for it" — this is that design);
  Freehire enrichment pay → `enrichment`, attributed to the provider as possibly model-produced;
  otherwise one figure is `extracted` from text. Currency, pay period and figures are kept exactly;
  nothing is annualized or currency-converted; base is distinguished from bonus/equity/OTE when the
  text separates them; when none is known the value is null and the page shows "Salary not provided."
- **Wiring:** `NormalizedJob.content` (new field, stored in the schemaless `DiscoveredJob.normalized`
  JSON — **no migration**) populated by the Freehire and Greenhouse/Lever normalizers. `GET /jobs/{id}`
  gains a `content` object consolidated from the richest discovery record that lists the job (freshest
  with a real description; stale ranked below), falling back to the job's own saved text; it carries
  the full description, the source's own sections, salary, and availability-dependent facts
  (employment type, seniority, department, locations, dates, source link). Model-written enrichment
  prose (Freehire `summary`, `requirements`) is not used.
- **Tests (commands actually run):** `cd backend && eval "$(uv run python -m tests.isolation create
  --export)"` then `uv run pytest tests/test_discovery_content.py tests/test_jobs_content_detail.py`
  → **35 passed**; the wider regression `-k "discovery or board or jobs or audit_inventory or
  deployment or freehire or watch"` → **312 passed**, exit 0. No new audit event and no new
  `NOEFFORTS_` setting, so the audit-inventory and deployment-config guards are unaffected.
- **Frontend detail view (follow-up, on `main` after D125/D126 landed):** `jobs/[id]` migrated
  `.tsx`→`.jsx` on the premium primitives, rendering the consolidated `content` in an "About this
  role" card — salary with its provenance line (or "Salary not provided."), the availability
  facts as chips, and the full description + the source's own sections as React elements (never
  `dangerouslySetInnerHTML`), with `Reveal`/`Stagger` entrance. Validated: `tsc`/eslint/`next
  build` clean; `frontend/e2e/job-detail-content.spec.ts` (sanitized structure renders, salary
  provenance shows, an injected `<script>`/`<img>` neither runs nor reaches the DOM, salary-absent
  case) on desktop + mobile.

## Answer brain (D115), Greenhouse real-page mechanics (D116), codes from the owner's mailbox (D117), 2026-11-02; local only, nothing real run

- **D115, the answer brain** (`app/modules/learning`, migration `6c2e9a4f1d38`): suggestions of
  the account's own saved answers for reworded questions; "Use this" answers and saves for that
  wording, "Not this" is remembered; each verdict retrains the account's model (LightGBM 4.7.0,
  else XGBoost 3.4.1; rules below 12 verdicts); vetoes on kind of answer, numbers, negation,
  countries and options; suggestion card on the application page; "Reuse for this exact
  question" ticked by default where allowed; "Questions are waiting for your answers"
  notification for automatic applying. **complete (local)**.
- **D116, Greenhouse real-page mechanics** rebuilt from the legacy bot's notes (see
  `docs/decisions.md`): formless submit bound to the job page, the security-code step (also
  before the click), upload acknowledged by file name, confirmation page, the page's own
  validation, raised click watched, attachments first, firewall page stop. Tested on the
  receiver's `gh2_live_like` mode (FIXTURE ASSUMPTIONS). **untested on a real page**.
- **D117, codes from the owner's mailbox**: recorded in `authorizations.py` (read and enter codes
  only, through 2026-11-06); Greenhouse's mixed-case codes and its "…security code field on your
  application: CODE" wording; the email naming the employer is used when applications overlap;
  mail since the attempt began filling in; on by default for the owner, needs the owner's
  Gmail token (`python -m app.modules.inbox.connect`). **untested against the real mailbox**
  (this session has no Gmail search tool and no deployed instance).
- Commands run (each exit 0 unless stated):
  - `tests/test_answer_brain.py` (model test with LightGBM installed: see below),
    `tests/test_auto_apply.py`, `tests/test_notifications.py`, `tests/test_audit_inventory.py`,
    the export tests;
  - `tests/test_greenhouse_real_mechanics.py` (7 passed, after fixing a status race, a test
    whose receiver settings leaked from the previous test, a stale wrong-code message, and an
    edit that had dropped the code typing);
  - `tests/test_inbox.py tests/test_authorizations.py tests/test_audit_inventory.py`;
  - `tests/test_forbidden_capabilities.py tests/test_rehearsal_handoff.py` (after the fix);
  - 18 suites together (answer brain, forbidden capabilities, Greenhouse dom/live/controls/
    adapter/real mechanics, hidden search, rehearsal handoff, auto-apply, deployment config,
    inbox, authorizations, audit inventory, notifications, dropdown strategies, account,
    migrations): 544 passed, exit 0;
  - `ruff check`, `ruff format --check`; `npx tsc --noEmit`, `npm run lint`.

## Freehire discovery and automatic applying on by default (D113, 2026-11-02)

- **The owner's choice:** "Fully automatic" and "Search + daily auto-check", quoted in D113.
  CLAUDE.md's submission rule was updated to match.
- **Defaults (complete, tested):** outside tests, Freehire (`["freehire"]`,
  `https://freehire.me`), the pilot switch and the rule are on, in `Settings._d113_defaults`,
  Compose and `.env.example`. Explicit settings win. Tests stay off.
- **Freehire (complete, tested against the stand-in):**
  - The owner's own Discover search is its run approval (the D55 row and audit). A search with
    words gets a daily watch (D56) for 90 days.
  - The owner falls back to the pilot's owner. D55 is still available behind
    `discovery_search_approves=false`.
- **Automatic applying (complete, tested against the stand-in board, receiver ledger):**
  - `app/modules/autoapply` runs a worker task every 5 minutes, for the owner, where the pilot
    may act.
  - It handles only Greenhouse job posts: not closed or excluded, no checked preference unmet.
  - It approves fully resolved packages only: the first application to an employer is a
    rehearsal, then the submission.
  - Limits: 5 approvals a day, and the recorded permission's shared limit (5 attempts until
    2026-11-06). It never retries a stopped attempt.
  - The Tracker's "Automatic applying" card shows the state and each action, with Pause and
    Resume. The new tables are in the account export and deleted with the account
    (migration `51e5cd3d9c4d`).
- **Not verified:** nothing has run on a real employer page. Most Freehire listings point to an
  employer's own page, which the pilot cannot apply to (the job page says which address it
  needs).
- **Commands actually run:**
  - `pytest tests/test_auto_apply.py` (7 passed);
  - `tests/test_freehire_live_read.py tests/test_freehire_watch.py tests/test_freehire_discovery.py
    tests/test_discovery_platforms.py tests/test_deployment_config.py` (exit 0);
  - `tests/test_account.py tests/test_authorizations.py tests/test_deployment_config.py
    tests/test_auto_apply.py tests/test_migrations.py` (exit 0);
  - sabotage: dropping the pause check and dropping the no-retry check each failed a test
    (reverted);
  - `ruff check`, `ruff format`; `npx tsc --noEmit`, `npm run lint` (exit 0);
  - `scripts/validate.sh lint format frontend backend` on the D113/D114 working tree (exit 1:
    8 failed, 4,403 passed, 76 min). The tree was being edited during the run (D115-D117), so it
    is not a clean measurement of one commit. Each failure was re-run against the current tree:
    `test_audit_inventory` (seven events D113 wrote were missing from `docs/audit-events.md`:
    documented) and `test_notifications` scoping (the D115 notification query: count updated)
    were real and are fixed; `test_forbidden_capabilities` was the D115 engine's computed import
    (fixed: plain imports); the five `test_rehearsal_handoff` failures came from edits landing
    mid-run and pass when re-run. A clean full run is still owed.

## The owner's pilot permission recorded and limited; production pilot check (D112, 2026-11-01)

- **Recorded** (`app/core/authorizations.py`, from the owner's own words, quoted in D112):
  - all four pilot steps, until 2026-11-06;
  - at most 5 attempts past the disclosure gate;
  - postings the owner approves in the app, one at a time, and only what each package contains.
- **Enforced (complete, tested):**
  - **The limit:** checked at the disclosure gate under one advisory lock; beyond it the attempt
    stops with nothing entered (`live_limit_reached`).
  - **The end date:** checked at every gate.
  - **The handoff** shows "Attempts left".
- **Tests never run under the owner's permission:** conftest empties the register for every
  test. `test_authorizations.py` checks the shipped entry and its days.
- **Production check (complete, tested; Docker not started here):**
  - `scripts/check_env.py --pilot` needs the switch on and exactly one owner account, and
    prints key names only.
  - `scripts/verify-local.sh --pilot` adds that check and validates the pilot overlay.
  - The overlay was also validated here with a synthetic `.env`
    (`docker compose ... config --quiet`, exit 0).
  - This sandbox has no Docker daemon, so the stack was not started. CI's Docker smoke job
    builds and starts the base stack.
- **Readiness:** 1 of 7 (condition 6, while the entry holds).
- **Not done:** nothing real was read, opened, filled or submitted. That runs only on the owner's
  server, for packages the owner approves there.
- **Commands actually run (exit codes from the commands):**
  - `uv run pytest tests/test_authorizations.py tests/test_greenhouse_live.py
    tests/test_rehearsal_handoff.py tests/test_reason_codes.py tests/test_pilot_readiness.py`:
    passed, exit 0.
  - Sabotage: removing the limit check failed `test_the_owners_attempt_limit_...` (reverted).
  - `uv run pytest tests/test_deployment_config.py`: 15 passed, exit 0.
  - `python3 scripts/check_env.py --pilot <synthetic .env>`: exit 0; on `.env.example`: exit 1.
  - `docker compose --env-file <synthetic .env> -f docker-compose.yml -f docker-compose.pilot.yml
    config --quiet`: exit 0.
  - `scripts/validate.sh lint format frontend backend` on `83fa400`: lint, format, typecheck and eslint ok; backend **4,400 passed** (1:11:47); exit 0.
- **CI on the merged commit:** CI #155 (run 41360331095, `192815a`) passed.
- **Follow-up (owner's first local try):** the job page now explains a Greenhouse job's manual
  handoff. It says either that the pilot is switched off on this server, or, for an address on
  the employer's own page (Greenhouse's id in `gh_jid`), which Greenhouse address the pilot
  needs. The board is never guessed and nothing is fetched. Reason codes are unchanged.
  Commands: `pytest tests/test_greenhouse_live.py tests/test_reason_codes.py
  tests/test_execution_routing.py tests/test_ashby_adapter.py tests/test_rehearsal_prerequisite.py
  tests/test_execution_security.py` (160 passed, exit 0), `npx tsc --noEmit`, `npm run lint`
  (exit 0).

## Locale exception integrated; run #11 corrected; hidden search inputs; milestone-B handoff (D111, 2026-11-01; local only, nothing real run)

- **Authorized:** a code change only (the owner, 2026-11-01): "This authorizes a code change, not a
  live rehearsal, upload or submission." No live run, rehearsal, upload or submission was made.
- **Locale exception (complete, in code; never run for real):**
  - The reviewed diff gives the pilot read-only path C's exact rule and its fetch redirect guard.
  - **Review fixes before integration:**
    - main frame only;
    - a redirect the browser follows for a locale request is detected and stops the attempt,
      before anything is entered and before submitting;
    - at most 150 such requests per session (path C's page-request budget).
  - **Unchanged:** the pilot is off by default; permissions 1-4 are unrecorded, so every gate
    still refuses.
- **Run #11 (corrected, not rewritten):**
  - It did not comply with the approved stop on any non-GET request: a page-load POST was
    reported blocked but did not stop it.
  - The approval and the proposal's approved Stops row are kept as approved, with dated
    corrections in the proposal, the compatibility report and D110.
  - Locale loading and opening were observed together; causation is not established.
- **The stop (complete, local):** in every widget-inspection mode a non-GET request is blocked
  before sending and latches the stop. No later request is sent and no action is taken; the
  reason is kept; nothing is retried. Tested with a page-load beacon and a dropdown beacon
  against an independent listener, and through the CLI process.
- **Hidden search input** (run #11's `u2`; complete, local, fixture built from that one
  observation):
  - **Before:** an attribute-only read would have made it a required, blocking question.
  - **Now:** it is not a question, and never touched, only while the live page shows it hidden,
    unrequired, empty and inside the group of one shown question.
  - **Where it is checked:** before anything is entered and after filling. Anything else stops
    the attempt.
  - **Still blocking:** standalone or shared-group ones.
  - **Package shape:** `SCHEMA_VERSION` stays 3; only such forms gain `.answers[].widget`.
- **`u3` (blocked, by design):**
  - Regressions: a list needing another host stops before disclosure, and an independent
    listener gets nothing; a required unlisted dropdown stays a checkpoint; no pilot rule admits
    another Greenhouse host or a data endpoint.
- **`u1` (blocked: three facts missing):** its label, whether its options state calling codes,
  and its options at capture (react-select lists need the page's scripts and a click).
  - Next step: a private, in-app browser read under permission 2. Not built yet.
- **Location (blocked):** the required `location` has no control on the page at load or after
  the 24 actions, so capture refuses the posting. How the page asks for it is unknown.
- **Milestone-B handoff (complete, local):**
  - Where: `GET /api/applications/{id}/rehearsal-handoff` and a panel on the application page,
    shown for a real Greenhouse job or a form read through the pilot.
  - **What it shows:**
    - the destination;
    - the exact answers and documents that filling and uploading would disclose, and what that
      exposes;
    - the enforced stop before submit;
    - each prerequisite read from the system now: switch, production, container, owner account,
      Greenhouse posting, permissions 1-3, pilot capture, no open question, rehearsal approval;
    - permission 4, kept separate;
    - the evidence a rehearsal leaves.
  - It grants nothing and is 404 for anyone else.
- **CI on main before this change:** CI #152 (`f36f92c`) and CI #153 (`205db94`) passed.
- **CI on the merged commit:** CI #154 (run 41349419984, `c838316`) passed all four jobs:
  backend, frontend (typecheck, lint, end-to-end desktop and mobile), docker-smoke and
  execution-compose.
- **Commands actually run (exit codes from the commands, never a `| tail`):**
  - `uv run pytest tests/test_hidden_search.py tests/test_greenhouse_controls.py
    tests/test_greenhouse_dom.py`: passed.
  - `uv run pytest tests/test_dropdown_strategies.py`: 43 passed.
  - `uv run pytest tests/test_rehearsal_handoff.py`: 5 passed, exit 0.
  - `uv run pytest tests/test_greenhouse_live.py`: 39 passed, exit 0.
  - **Sabotage checks** (each change reverted afterwards):
    - dropping the hidden-search visibility condition failed the "shown" cases;
    - dropping the redirect listener failed the browser-fetch case.
  - `npx tsc --noEmit`, `npm run lint`: exit 0.
  - `uv run ruff format .`, `uv run ruff check .`: clean.
  - `scripts/validate.sh lint format frontend backend` (exit 1):
    - lint, format, typecheck and eslint ok;
    - backend: **1 failed, 4,393 passed** (1:15:15).
    - **The failure:** `test_locale_observation.py::test_a_post_is_refused_before_it_is_sent`
      still expected the behaviour before D111 (a POST at load recorded and passed over, the stop
      at the first action). It now expects the corrected stop, at load, with the POST never sent.
  - **A flake found while checking that, root-caused:** the new page-load beacon test failed 2
    of 6 repeated runs.
    - **Cause:** with a page that names no icon, Chromium itself may GET the page origin's
      `/favicon.ico` after the load, outside Playwright's request routing. The latch refuses every
      routed request, and this one still arrived.
    - **What it is:** the browser's own GET to the page's own origin, carrying nothing of the
      applicant. Read-only summaries never counted it, so earlier real runs may have made it
      unrecorded.
    - **Fix:** request lists in the three read-only test files leave exactly that request out
      (`execution_harness.BROWSER_OWN`) and compare everything else exactly. After it: 6 of 6
      repeated runs passed.
  - **Re-run after both fixes:** `test_locale_observation.py`, `test_widget_inspection.py`,
    `test_readonly_cli_process.py` and `test_dropdown_observation_c.py`: 174 passed, exit 0. The rest of the
    suite was unchanged by the fixes (test files only); CI runs it in full on the merged commit.

## Run C (run #11): the real dropdowns open once their locale files load (D110, 2026-11-01)

- **What happened:** with the owner's single-use approval, read-only run #11 (Actions run
  41330028697) ran on `efceea4`, where CI #151 passed all four jobs. It completed with no stop.
  Record: `docs/greenhouse-compatibility-report.md`.
- **Verified before dispatch:**
  - the branch and the run's head SHA were `efceea434cf50111f78a17c271da94cbb28a4d36`;
  - only `inspect_dropdowns` was enabled;
  - the limits in code matched the approval.
- **On the real form:**
  - The 2 locale files were loaded (2xx).
  - All 12 dropdowns opened at the control's own click; the container click was never needed.
  - 11 lists were read completely, and the 7 mapped to job-data questions equal their job data.
  - React-select markup was confirmed on all 12.
- **Still open:**
  - `u1` (required, phone group, 244 options): unmapped.
  - `u3` (required): no readable options, while a request to `my.greenhouse.io` was refused.
  - Location: absent at load.
  - Selection, typing, upload and submission were not tested.
- **A correction:** a telemetry POST at page load was blocked before sending and did not stop
  the run. That is how the code has always worked; the request's stop list had not said so. The
  proposal now does.
- **CI:**
  - #150 on `9fb5cf1`: failed, fixed as recorded below.
  - **#151 on `efceea4`: passed, all four jobs** (the revision run #11 used).
- **Prepared, not merged:** the pilot's locale exception (branch, see D110). It awaits the
  owner's approval with the first rehearsal.
- **Next executable step:** the owner's milestone-B request (D110), on a posting without
  location or unmapped required controls.

## Greenhouse first: the dropdown blocker (D109) and two evidence gaps (D108), 2026-11-01; local only

- **On observed real forms (one posting, read-only):** the job data, the page load and the
  mapping of 19 fields work, and they did so in runs #3-#10.
  - Dropdowns have never been seen opening: clicks reached page code that asked for locale files,
    and those were refused.
  - Nothing has been filled, uploaded or submitted on a real page.
- **Still fixture-only:** opening and reading real dropdowns, `u1` and `u2`, location, uploads,
  the final submit and confirmation.
- **The precise blocker:** whether the real dropdowns open once their locale files load, or only
  from the react-select container. Run #10's rule allowed none of the real files.
- **Implemented to remove it (D109):**
  - **A defect fixed:** the readback of a chosen dropdown read the input's value. On react-select
    markup (what the owner's previous bot found on Greenhouse) that is search text, so a real
    form would have been abandoned after correct choices. It now reads the single displayed
    value, strictly. Shown by sabotage on a react-select-like fixture.
  - **`click_container`:** one click on the react-select container, tried after the control's
    own click, with the same verification.
  - **Read-only path C** (`--inspect-dropdowns`, workflow input `inspect_dropdowns`; not
    approved):
    - locale files in run #10's observed shape are allowed, and each allowed file's outcome is
      recorded (2xx, 4xx, failed), so an allowed file is never counted as loaded;
    - one container click where the control's click shows nothing;
    - react-select markup recorded as booleans.
  - The pilot's network rules and readiness are unchanged (still 0 of 7).
- **D108 (the owner's two local evidence gaps):**
  - A dropdown that POSTs to another origin when opened, by fetch or `sendBeacon`, stops the
    attempt. An independent listener on that origin received nothing, and nothing was filled,
    uploaded or submitted.
  - Sabotage showed a real gap: before D108 a beacon POST was not counted, and the attempt went
    on to submit.
  - The read-only inspection keeps apart an existing value changing, a control added or
    removed, focus moving, a class-name hint and a visible option list. A class hint alone is
    `undetermined`.
- **The legacy uploads:** the newer legacy version was reviewed statically
  (`docs/legacy-audit.md`, addendum). Its private data files were not opened or committed.
- **CI:**
  - #148 on `df3962b`: passed, all four jobs.
  - #149 on `d40df2f` (D107): passed, all four jobs. D107 is closed.
  - **#150 on `9fb5cf1` (D108 + D109): failed.**
    - frontend, docker-smoke and execution-compose passed. Backend: 4,329 passed, 1 skipped,
      2 failed.
    - (1) `test_repo_hygiene`: a path in a new test read as an email address. Fixed by writing
      the `@` as in the other locale tests.
    - (2) `test_test_isolation::test_a_runs_own_leftover_session_does_not_block_its_cleanup`
      failed as in CI #146, "permission denied to terminate process". The cleanup's
      `WITH (FORCE)` fallback must terminate every session on the database, and an autovacuum
      worker was there.
    - Fixed in `tests/isolation.py` `_drop`: never FORCE. While sessions remain, only the
      connecting role's own and the test role's sessions on that database are ended, and the
      plain drop is retried (3 tries).
    - Locally: `test_test_isolation.py`, `test_repo_hygiene.py` and `test_migrations.py` passed.
      Neither failure was in the dropdown code.
- **Validation (this sandbox, each run on its own disposable database and ports):**
  - **D108** (`b999d8c`): `scripts/validate.sh lint backend` passed, exit 0. Lint was clean, and
    the full backend suite gave **4,302 passed**, 0 failed (1 h 12 min). Sabotage checks:
    - without the non-GET rule, both beacon cases ended `confirmed`;
    - without the class-hint rule, 3 tests failed;
    - with an added control counted as a change, 2 tests failed.
  - **D109** (the files it touches): the first run of 16 files gave 659 passed and 3 failed. It
    ran while two other suites shared the machine.
    - Two were real expectations to update: path B's summary now carries `outcomes`, and the
      response tripwire was tightened (one `response` subscription whose handler reads only
      status and request; header accessors are now forbidden too).
    - The third, `test_widget_detector::test_options_within_the_window_are_observed_and_their_arrival_recorded`,
      is load-sensitive (its first sample came after the fixture's 300 ms delay). It passed 3 of
      3 on its own. Not changed.
  - After the fixes, each passed in full on its own: `test_locale_observation.py`,
    `test_dropdown_observation_c.py`, `test_widget_inspection.py`, `test_widget_detector.py`,
    `test_dropdown_strategies.py`, `test_greenhouse_controls.py`, `test_readonly_cli_process.py`.
    Sabotage: with the old input-value readback, the react-select-like cases were abandoned.
  - Not run locally on the merged tree: the full suite and Playwright. CI runs them on the
    merged commit, and the run request names that commit only after its CI passes.
- **Next executable step:** the owner's single-use approval of run C, on the pinned revision
  named in the request (after CI passes on it).

## Read-only path B run once (run #10); path refusals made explainable (D107, 2026-11-01)

- **What happened:** with the owner's single-use approval, the read-only check ran once in
  `inspect_widgets_locales` mode as manual run #10 (Actions run 41279694718).
  - Full record: `docs/greenhouse-compatibility-report.md`, "Locale observation, path B (manual
    run #10)". Decision: D107.
- **Before dispatch (verified):**
  - `readonly-inspect-a8d07af` resolved to `a8d07af8d32f97e8ada8ee187017ca958bddc8b2`
    (`git ls-remote`), the revision on which CI #147 passed all four jobs. The run record's head
    SHA is the same.
  - The workflow checks out the dispatched ref.
  - Inputs: only `inspect_widgets_locales` was true; `observe`, `mapping`, `b3`,
    `inspect_widgets` and `identify_only` were false.
  - `GH_READONLY_POSTING`: no tool here can list repository secrets. The workflow's first step,
    which fails before any external request if the secret is missing or malformed, passed. The
    value was never displayed.
  - The pinned branch was not moved, and the code it ran was not changed.
- **Result:**
  - A policy stop (exit 7, workflow "failure"), with 0 internal errors.
  - 3 API GETs, all 200; 1 page load; 41 requests.
  - The locale rule allowed **0** requests. All 12 real locale requests failed its `path`
    element and were refused before sending.
  - 7 of 12 dropdowns were reached, with 14 actions. 6 were `not_opened` within 1.5 s; `q11`
    showed only a class-name hint.
  - During `q11` the page tried a POST to another Greenhouse host. It was blocked before
    sending and stopped the inspection. Not retried.
  - **Language files loaded: no. Dropdowns opened: not shown.** The language-file explanation
    is untested, neither confirmed nor ruled out.
  - Ordinary connection metadata reached Greenhouse and its CDN, as for any public page load;
    no candidate or form data was sent.
- **Next local task chosen from the evidence:** "path" alone could not say why the real locale
  paths failed.
  - `gh_readonly.locale_path_detail` now records, for each path refusal, which properties
    failed (`unprintable`, `prefix`, `segments`, `extension`, `dots`, `characters`, `length`)
    and a bucket of the longest segment's length. It never records the path, a segment or an
    exact length.
  - The summary key is `inspection.locale_path_refusals`.
  - It allows nothing: the rule, the context layer, every limit and the pilot are unchanged.
    No further run is approved.
- **Tests (`tests/test_locale_observation.py`):**
  - each property and bucket on its own, and the detail explaining exactly the path refusals,
    never another;
  - in the browser, a hashed name, a long name and both together are refused before sending,
    counted by property, with no path text in the published summary;
  - every rule-element case reports detail only for `path`;
  - the guard accepts the new keys.
  - Sabotage: removing the `dots` check failed the detail tests; restored and re-run, they
    passed.
- **Also updated:** `readiness.PATHS` (conditions 1, 2, 7: run B is used; Path A remains), the
  activation guide, the readiness-gap handoff and the proposal.
- **Validation (this sandbox, each run on a disposable database of its own):**
  - `ruff check .` and `ruff format --check .`: clean.
  - The files that exercise `gh_readonly`: `test_locale_observation`, `test_gh_readonly`,
    `test_readonly_cli_process`, `test_widget_inspection`, `test_b3_policy`,
    `test_widget_detector`, `test_required_signals`, `test_forbidden_capabilities`,
    `test_provider_contracts`, `test_workday_ashby_fixtures` and `test_pilot_readiness`.
    **450 passed** (exit 0).
  - After the `readiness.PATHS` text change, `test_pilot_readiness`, `test_provider_admission`
    and `test_provider_contracts`: **211 passed** (exit 0).
  - Not run locally: the full backend suite and Playwright. CI runs them on this commit.
- **CI #148 on `df3962b`** (the FORCE wording correction): frontend, docker-smoke and
  execution-compose passed. The backend job was still running when this was written; its result
  will be recorded with the next change.

## Activation reconciled; read-only path B built (D106, 2026-11-01; local only, nothing real run)

- **What you can do now:**
  - Read `docs/activation-status.md`, the one owner handoff. For each of the seven conditions it
    gives:
    - why it is not met;
    - what it needs;
    - the smallest next action;
    - what NoEfforts can do and what only you can do;
    - what stops a real attempt meanwhile.

    It also has the permission form, startup, the rehearsal and submission plans, and how to
    stop, revoke and reconcile.
  - `GET /api/providers/greenhouse_live/readiness` serves the pilot's checklist with each
    condition's path.
- **Defects found and fixed:**
  - The checklist was computed for `greenhouse_dom`, which never runs on a real destination, so
    conditions 4, 5 and 7 could never be met. It is now the pilot's (`greenhouse_live`).
  - The owner's permissions had two sources (constants beside D103's register). The register
    is now the only one.
  - Condition 7 now shows its two parts.
  - Read-only inspections gave a dropdown 600 ms; the adapter accepts one that settles within
    1.5 s. Path B uses the adapter's window.
- **Computed readiness: 0 of 7** (`docs/activation-status.md` §3 gives each reason).
  Condition 7's first part is done (D102's reviewed real-destination entry). Nothing was
  relaxed, and no synthetic evidence counts.
- **Code:**
  - `providers/readiness.py`: pilot provider, register-derived permissions, condition paths,
    condition 7 in two parts.
  - `providers/admission.py`: reads the register; keeps `greenhouse_dom`'s row.
  - `providers/router.py`: `/providers/{greenhouse_live|greenhouse_dom}/readiness`.
  - `adapters/dropdowns.py`: its timing documented.
  - Path B (written by a subagent in a separate worktree, reviewed here): `gh_readonly.py`
    (`--inspect-widgets-locales`, `locale_refusal`, `LOCALE_LIMITS`); `execution/browser.py`
    (`SubresourceRule.path`, several rules per origin; the pilot's rule unchanged); the fixture's
    locale gate; the workflow input, default off; the proposal's path-B section.
- **Tests:**
  - `test_pilot_readiness.py`:
    - each condition's path is complete and names existing test files;
    - the gate condition follows the register;
    - condition 7 needs both parts;
    - the API serves both checklists and 404s others.
  - `test_greenhouse_live.py`: an authorization that ends while an attempt is queued stops it
    before the page opens, in the running process.
  - `test_batch_review.py`: the same batch sent twice creates nothing new, and each approval
    keeps its own expiry.
  - Run here: readiness, admission, contracts, providers, doc references, authorizations,
    pilot and batch tests, **300 passed**.
  - Path B (the subagent's runs, on its own disposable database):
    - widget inspection and detector, `gh_readonly`, locale observation (73 new), the CLI
      process, B3 policy, forbidden capabilities, hygiene and doc references: **317 passed**;
    - dropdown strategies, controls and doc references: **80 passed**;
    - 25 guards sabotaged one at a time: each made a test fail.
- **CI recorded:** **CI #145** on `9dcd8b4` (run 41253512210), D105, passed on all four jobs.
- **Full validation** (`VALIDATE_LOG_DIR=/tmp/v106 scripts/validate.sh all`, the tree of `f79dc4a`,
  each suite on a disposable database the script created and dropped):
  - lint, format, typecheck and eslint: ok;
  - backend: **4,237 passed** (1h04m35s);
  - Playwright: **131 passed, 2 skipped** (11.9 min).
- **CI #146 on `3ddfce5` (run 41266709102): failed, now fixed.**
  - frontend, docker-smoke and execution-compose passed. Backend: **4,235 passed, 1 skipped,
    1 error**.
  - The error was in the clean-up of `test_migrations.py`.
    `DROP DATABASE … WITH (FORCE)` must terminate every session on that database. Since D103 the
    suite runs as a test role without `pg_signal_backend`, and the session was a PostgreSQL
    autovacuum worker (the server log shows autovacuum busy), so the drop failed: "permission
    denied to terminate process". It depends on autovacuum timing, so CI #143-#145 did not
    hit it.
  - Fix (`tests/isolation.py` `_drop`): a plain `DROP DATABASE` first, which ends autovacuum
    workers itself. `WITH (FORCE)` is used only if sessions remain (SQLSTATE 55006). Any other
    error is raised. The role is not given `pg_signal_backend`: that would let test credentials
    end other roles' sessions.
  - Correction (2026-11-01): FORCE is not limited to "this run's own sessions", as this entry
    first said. It ends every session on that database. As the shared test role (siblings)
    that covers any test run's session there; as the administrator (`drop --run`), anyone's.
    PostgreSQL refuses it, dropping nothing, if a session belongs to a role the connecting role
    may not signal. Other runs are protected by which database is dropped. Only a database
    marked with this run's id, named after its own database and owned by the test role, is
    dropped, and that is unchanged. Inspection found no case where another run's session is on
    such a database, so nothing else was changed. Only docstrings and docs changed. Checked with
    ruff check and format (clean) and, on a disposable database,
    `pytest tests/test_test_isolation.py tests/test_migrations.py`: **28 passed** (exit 0).
  - Tests: the order and the fallback, with statements recorded (the old code fails it); a run's
    own leftover session does not block its clean-up (real database).
    `test_test_isolation.py`, `test_migrations.py` and `test_audit_repair.py`: **32 passed**.
- **CI #147 on `a8d07af` (run 41271405216): passed.** All four jobs succeeded: frontend,
  docker-smoke, backend and execution-compose. This closes the CI #146 repair.
- **Not run:** path B, a rehearsal, or anything on a real page. Run #9 remains the last
  external activity.

## Review several packages, approve each on its own (D105, 2026-10-31; local only)

- **What you can do now:** open **Review** in the menu. It lists every application you could
  approve now, with its package version, the start of its content hash, its destination and
  anything holding it back. For each one you tick "Rehearsal: fill and check, never submit" or
  "Submit once", then approve the ticked ones together.
  - Each is approved on its own, exactly as on its own page, until it expires.
  - A package that changed after the list was loaded is refused, not replaced.
  - Submitting is offered only once the employer's path has been rehearsed.
  - Nothing is queued or sent; you start each application from its page.
- **Code:** `app/modules/preparation/review.py` (list and approve), the router in `app/main.py`,
  `frontend/src/app/(app)/review/page.tsx`, the menu link (`AppShell.tsx`), and the
  `package.approve_reviewed` row in `docs/audit-events.md`.
- **Tests** (run here, each on a disposable database):
  - `tests/test_batch_review.py`: **6 passed**. Two packages approved on their own with their
    own scopes, hashes and expiry; nothing queued or disclosed; approving again changes nothing;
    another scope is refused. A package changed after listing is refused while the other is
    approved. A wrong hash is refused. Another account's or an unknown application is "not
    found". Empty, scope-less, duplicate, malformed, over-limit and "all" batches are refused
    (422) with nothing written. An approval to submit before the rehearsal is refused, while the
    rehearsal approval is given. Open questions are shown and block approval.
  - `frontend/e2e/review.spec.ts`: **2 passed** (desktop, mobile). Nothing is approved by
    default; the two ticked packages are approved with their scopes; each application's page
    shows its approval; the receiver's ledger has no disclosure or acceptance.
  - `test_audit_inventory.py`, `test_doc_references.py`: **22 passed**.
  - `test_api_paths.py`, `test_api_tokens.py` (the new routes refuse API tokens),
    `test_preparation.py`, `test_repo_hygiene.py`, `test_forbidden_capabilities.py`:
    **197 passed**.
- **CI recorded:** **CI #144** on `f9a6f56` (run 41243717835), D104, passed on all four jobs.
- **Full validation** (`VALIDATE_LOG_DIR=/tmp/v105 scripts/validate.sh all`, the tree of `71fb66b`,
  each suite on a disposable database the script created and dropped): lint, format, typecheck
  and eslint ok; backend **4,158 passed** (1h01m46s); Playwright **131 passed, 2 skipped**
  (12.2 min, the new review spec included).

## Greenhouse controls on local stand-ins: phone country, location search, late options (D104, 2026-10-31; local stand-ins only)

- **Review page:** a hidden value that the page's own location search sets is labelled "set by
  the page's location search, never by NoEfforts", not "left blank" (`applications/[id]/page.tsx`).
- **What changed for you:** on the local Greenhouse-style stand-in only (never on a real page,
  where each of these still stops the attempt before anything is entered):
  - **Phone country.** The country picker beside the phone number is a question of its own. It
    is chosen for you only when your approved phone number states its calling code and exactly
    one of the page's options has it ("+44 …" → "United Kingdom (+44)"). A shared code (+1:
    United States and Canada), no code, or no approved number: you choose one of the page's
    options for this application. It is never taken from where you live.
  - **Location search.** "Location (City)" is answered with your approved city of residence (the
    existing residence rule) or, for a question that is not about where you live, your answer
    for this application. It is typed into the page's own search only after the disclosure
    gate, the one suggestion that is exactly it is chosen, and the page must set its hidden
    coordinates itself. Anything else stops the attempt, after the search text was sent and
    before submitting, with its reason; it is never retried.
  - **Late dropdown options.** A list that arrives after opening is accepted within 5 seconds
    once nothing is loading and it has stayed exactly the approved list; otherwise the attempt
    stops before anything is entered.
- **Decided on my own:**
  - the text typed into a location search for a residence question is the profile's approved
    city exactly as stored; when the page's suggestion is longer ("Springfield, Northshire") the
    attempt stops after the search, and you change the profile, not the application (residence
    stays profile-only);
  - a calling code counts only when the number writes it with a separator ("+44 20 …"); "+4420…"
    gives no code and asks you;
  - "exactly" compares whitespace-collapsed, case-folded text;
  - one input event with the whole approved text, so each attempt discloses it once;
  - the bounded waits: 5 s for a late list or for suggestions, 5 s for the page's hidden values,
    three identical reads (now required of every list, also on real pages: stricter, never
    looser);
  - a page-set hidden value is shown on the review page as a blank row with its explanation
    (the frontend was not changed; its badge reads "Blank (optional)");
  - `greenhouse_dom`'s registry level `location_picker` raised to `fixture` with its ledger
    scenario; `greenhouse_live`'s left at `none`, because on its real hosts the control is
    refused.
- **`SCHEMA_VERSION` stays 3:** only a package of a form with one of these controls gains
  `.answers[].widget`; every other package's content and hash are unchanged
  (`test_only_forms_with_these_controls_carry_a_widget_so_schema_version_stays`). Adapter versions
  `greenhouse-dom-4` and `greenhouse-live-2`, extraction `greenhouse-dom-v3`.
- **Tests added** (`backend/tests/test_greenhouse_controls.py`, 50 cases; the receiver's ledger the
  oracle; the execution cases through both `greenhouse_dom` and the pilot, `greenhouse_live`):
  capture recognises exactly the two structures and only on stand-ins (4 refusals: picker beside
  the group, options without codes, no list at load, hidden values outside the group); a
  hand-made form cannot carry a widget; the phone-country resolver (unique code, +1, undelimited,
  no code, unknown code, no number, an unapproved number; residence and targets set and never
  used); the location text source; a unique code chosen and read back; +1 and no code
  checkpoints, approval refused and nothing disclosed until you choose; the exact suggestion,
  one search disclosure, the page's coordinates and no write to a hidden value but the page's
  (`test_location_exact_or_checkpoint`, now `greenhouse_dom`'s `location_exact_or_checkpoint`
  scenario); two, none, a page that sets nothing and a label alone stop after the search, never
  retried; a location prefilled at load (before disclosure) or after the résumé upload (before
  typing) never trusted; each structure re-proven before disclosure; late options through both
  adapters; on a destination that is not a stand-in each control stops before anything is
  entered and late options are refused as before; capabilities fixture-only and 0 readiness
  conditions met; package shape. `test_dropdown_strategies.py`: late lists accepted (`late_fetch`,
  `locale_on_open`, `delayed` 2.5 s) and refused (`late_differ`, `late_never`, `late_changing`,
  `late_slow_changing`, `late_partial`, `late_post`, `delayed` 7 s).
- **Changed tests:** `locale_on_open` moved from refused to accepted (a same-origin GET on a
  stand-in); `delayed` 3 s refused became 7 s (beyond the 5 s bound); the registry
  (`location_picker` fixture for `greenhouse_dom`) and adapter-version assertions; the receiver
  now resets its v2 per-mode settings (`dd`, `delay_ms`, `locale_delay_ms`, `loc`, `pc`) between
  tests.
- **Full validation** (`VALIDATE_LOG_DIR=/tmp/v104 scripts/validate.sh all`, on `b010e1b` rebased
  onto `d65e976`, each suite on a disposable database the script created and dropped):
  - lint, format, typecheck and eslint: ok;
  - backend: **4,152 passed** (1h03m29s);
  - Playwright: **129 passed, 2 skipped** (11.5 min).

  The one failure of the subagent's run below (`test_no_mailbox_client_is_imported_or_addressed_anywhere`)
  was D103's, fixed on `main` in `d65e976` before this run.
- **Validation:** commands actually run, in the worktree `d104-controls` on its own disposable database
  (`eval "$(uv run python -m tests.isolation create --export)"`, ports
  `NOEFFORTS_TEST_RECEIVER_PORT=8790 NOEFFORTS_TEST_CANARY_PORT=8791 NOEFFORTS_TEST_BROKER_PORT=6390`,
  each with `-q -p no:cacheprovider -o addopts=`), while another validation run used the main
  checkout:
  - baseline before any change, `uv run pytest tests/test_greenhouse_dom.py`: **56 passed**;
  - final, after the last edit and `uv run ruff format .`: `uv run pytest
    tests/test_greenhouse_controls.py tests/test_dropdown_strategies.py tests/test_greenhouse_dom.py
    tests/test_greenhouse_live.py tests/test_resolver.py tests/test_package_contract.py
    tests/test_forbidden_capabilities.py tests/test_repo_hygiene.py tests/test_reason_codes.py
    tests/test_providers.py tests/test_execution_routing.py tests/test_provider_contracts.py
    tests/test_provider_admission.py tests/test_pilot_readiness.py tests/test_required_signals.py
    tests/test_audit_privacy.py tests/test_lever.py tests/test_form_readiness.py
    tests/test_b3_policy.py tests/test_path_a.py tests/test_doc_references.py
    tests/test_approval_binding.py tests/test_sending.py tests/test_upload_evidence.py
    tests/test_error_boundary.py tests/test_gh_readonly.py tests/test_widget_detector.py
    tests/test_widget_inspection.py tests/test_execution_failures.py tests/test_api_provider.py
    tests/test_support_wording.py tests/test_rehearsal_stop.py`: **1,296 passed, 1 failed**
    (33m12s). The failure, `test_no_mailbox_client_is_imported_or_addressed_anywhere`, is not
    D104's: it flags `gmail.googleapis.com` in `tests/test_http_properties.py:55`, a file D104
    does not touch, and it fails the same way on an export of the base commit `3eb9789`
    (1 failed, run here);
  - `uv run ruff check .` and `uv run ruff format --check .`: clean.
  - **Sabotage**, one guard at a time (the file restored after each), each run against the tests
    that cover it: **26 changes, all caught** (25 on the first run). Caught: the phone group
    check, the rule that every option states a calling code,
    the location group check, `stand_ins` defaulting on, a hand-made widget, "exactly one" code,
    residence used for a missing code, an undelimited code, an unapproved number, the location
    text source widened to a preference, "exactly one" suggestion, NoEfforts writing a hidden
    value (both the positive and the label-only test fail), the page-set check, the prefill
    check, the stand-in guard, late lists on a real destination, a POST for options, a
    changing list (with both stability layers removed), the deadline for a list still loading,
    a different list, `widget` written for every answer, the route counting page-set values,
    a capability raised above `fixture_only`, the phone readback, the structure re-proof, and
    the three-read stability rule alone. That last one was missed on the first run:
    `late_changing` changes every 60 ms, which the probes' quiet-time check also catches, so it
    still passed; `late_slow_changing` (every 300 ms) was added, and with the rule removed it
    failed. (Since D145 the page's own record refuses that list by itself, so it no longer
    holds the three-read rule: `test_three_equal_reads_are_still_needed` does.)
- **Not verified:** any of it on a real page (none was visited); the review page's wording for
  a page-set hidden value (no frontend change, no Playwright run); the full backend suite (not
  run here, by instruction).

## Built is not authorized; disposable test databases (D103, 2026-10-31; local only)

- **What changed for you:** nothing reads your mail or acts on a real Greenhouse page on a switch
  alone. Each use needs your explicit, recorded authorization (`app/core/authorizations.py`), and
  there is none. Account says so for email, and a Greenhouse job's route says so
  (`live_not_authorized`). Typing a verification code yourself works as before.
  `docs/activation-status.md` lists, feature by feature: implemented, fixture-tested, consent
  configured, operationally authorized, real-service verified. It also gives the one checklist
  of what activation still needs.
- **Authorization history** (D103, verbatim). Inbox reading: not authorized. Automatic code
  retrieval and entry: not authorized. Greenhouse pilot permissions 1-4: none given. D102's
  statement that the owner's switch replaced the gate's permissions was wrong. It is corrected
  in `docs/live-pilot-gate.md`, `docs/greenhouse-live.md`, `docs/inbox.md` and
  `docs/remaining-work.md`.
- **Gates** (code): the inbox checks each use in `available_for`, `fill_codes`, `check`, `due`
  and the API. The pilot checks:
  - capture (read);
  - the route (read, open, disclose);
  - queueing (open and disclose, plus submit for an approval to submit);
  - the worker before the page opens (open, disclose);
  - the disclosure gate (open, disclose);
  - the send gate (submit).
- **Gmail correlation:** a "received" email is proposed as the reconciliation of an unknown
  submission only when all of these hold:
  - it names the application's employer and its job title;
  - it arrived after the final click;
  - no other such proposal is open.

  Confirming it changes the state only: no attempt, no outbox message and no request to the
  employer (`tests/test_inbox.py`).
- **HTTP clients** (`tests/test_http_properties.py`, real sockets):
  - certificates and hostnames are verified: a live TLS server with an untrusted certificate is
    refused, and the same server trusted answers;
  - no environment proxy is used;
  - a silent server is given up on within the timeout;
  - every request has an explicit timeout;
  - redirects are refused and their target receives nothing;
  - oversized answers are refused;
  - errors are fixed codes;
  - no token, `Authorization`/`Bearer`, secret or message content reaches the logs or output.

  One defect found and fixed in the token exchange (`connect.py`): a non-JSON answer raised a
  parse error instead of the fixed refusal, and an answer over 1 MB was parsed truncated. The
  old code fails 3 of the 4 new cases.
- **Production dependencies:** a production-only install (`uv sync --frozen --no-dev`, in a
  separate environment) imports the API, the worker, the connect command and the register, with
  neither `pytest` nor `httpx` installed (run here; also a CI step now). The static guard
  `test_runtime_dependencies.py` stays.
- **Test isolation** (`docs/test-isolation.md`, `tests/isolation.py`, 11 regression tests in
  `tests/test_test_isolation.py`):
  - an explicit, marked, disposable database owned by a test-only role (`noefforts_tester`; a
    superuser is refused);
  - an advisory-lock claim held for the run, taken before any DROP or migration;
  - every DROP and TRUNCATE waits at most 15 s;
  - run-scoped sibling databases, and cleanup only of the run's own;
  - Redis index and port locks for the receiver, canary, broker and every Playwright server;
  - the e2e database claimed by the API before it migrates.

  `scripts/validate.sh` and CI create their own databases. Two suites ran side by side here on
  separate databases and ports.
- **CI recorded:** **CI #141** on `be16318` (run 41193378664) and **CI #142** on `f70f435` (run
  41196286997) passed on all four jobs (backend, frontend, docker-smoke, execution-compose).
  **CI #143** on `d65e976` (run 41236104409), D103 itself, passed on all four jobs, including:
  - the new steps that create the disposable test and e2e databases with `tests/isolation.py`;
  - importing the API and worker with production dependencies only;
  - the backend tests (34 min).
- **Validation** (`VALIDATE_LOG_DIR=/tmp/v103 scripts/validate.sh all`, on `3eb9789`, each suite on
  a disposable database the script created and dropped):
  - lint, format, typecheck and eslint: ok;
  - Playwright: **129 passed, 2 skipped** (12.8 min), with every server under the isolation
    hold and the e2e database claimed;
  - backend: **4,093 passed, 1 failed** (1h03m27s). The failure was my new HTTP-property test
    naming the Gmail API host, which `test_forbidden_capabilities.py` allows only in the reader.
    It now takes the host from the reader's own constant. Afterwards
    `test_forbidden_capabilities.py`, `test_http_properties.py` and `test_repo_hygiene.py`:
    **161 passed**.

  Before the full run, the gates' own files ran on a second disposable database alongside
  another run:
  - `test_greenhouse_live.py` and `test_inbox.py`: **53 passed**;
  - `test_reason_codes.py`, `test_discovery*.py` and `test_freehire_discovery.py`: **86 passed**,
    on receiver port 8793. The mock feed's 8799 addresses are rewritten for a run on another
    port: `conftest.py`.
- **Sabotage checks:**
  - the token exchange's old code: 3 of the 4 new cases fail;
  - the old "received" rule (state only): both new correlation tests fail.

## The Greenhouse pilot: real Greenhouse applications, built and off (D102, 2026-10-31)

- **What you can do now:** nothing changes until you switch it on (docs/greenhouse-live.md:
  `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`, your account in `NOEFFORTS_LIVE_OWNER_EMAILS`, and the
  stack started with `docker-compose.pilot.yml`, which runs in production mode with container
  isolation). Then a real Greenhouse job post's job page offers "Read the Greenhouse form"; you
  review and approve the package as always; the first application to each employer is a
  rehearsal that fills and checks and never submits; after it, a separate approval submits once.
  Anything not understood stops the attempt with its reason; nothing is retried after the final
  click.
- **Decided on my own:** keeping one approval per application (the owner's choice between batch
  approval and none is still open); the first application per employer as a rehearsal (E6, as for
  every real destination); reading only Greenhouse's own hosts, where robots.txt allows; recording
  a review of Greenhouse's public terms as mine (D91), with its findings stated plainly
  (MyGreenhouse forbids automated use; NoEfforts never uses MyGreenhouse); a new adapter name
  rather than switching `greenhouse_dom` on, so evidence and approvals say which ran.
- **Tests (commands actually run, in a separate worktree and test database):**
  - `uv run pytest tests/test_greenhouse_live.py`: 25 passed (off by default; the owner's
    account only, and another account's job 404; production with the container sandbox; board
    hosts only, https, no port or userinfo; no real host contacted from tests, and in production
    a Greenhouse name resolving to this machine refused; robots.txt and the post's own id; no
    redirect; only Greenhouse's static assets; the first application to an employer a rehearsal,
    then one acceptance in the receiver's ledger; switching it off stops a queued application
    with nothing disclosed).
  - The receiver-ledger scenarios through the pilot: `tests/test_greenhouse_dom.py -k pilot`
    18 passed; with the failed-upload and reconcile cases and the provider, admission and
    reason-code contracts, 61 passed.
  - A wider set (Greenhouse, execution security, routing, rehearsal, readiness, dropdowns,
    providers, admission, reason codes, uploads, failures, documentation, guards, hygiene,
    deployment, read-only check, fixture boundary, audit inventory): 806 passed, 2 failed. One
    was the known port artefact of the discovery reason-code test (its fixture data names port
    8799; this run used another), the other the D101 test address since fixed on `main`; after
    merging it, hygiene, inbox, documentation and pilot tests 50 passed and 1 failed (a
    userinfo test URL that read as an address, now built at run time), then 28 passed.
  - `tests/test_deployment_config.py`: 12 passed (the pilot's Compose override changes only
    production mode and the egress proxy's outbound network).
  - Sabotage, one change at a time against `test_greenhouse_live.py`: 14 of 15 caught (on by
    default, any account, production without the sandbox, outside production, any board path,
    real hosts from tests, robots ignored, another post's data, a redirect followed, the CDN
    for any origin, a switched-off pilot still running, others capturing, the route ignoring
    the account, the stand-in in production). Missed: removing the https check alone, because
    the board origins themselves are https only and refuse a plain-http address too.
  - `npx playwright test e2e/greenhouse-pilot.spec.ts e2e/routing.spec.ts e2e/journey.spec.ts
    e2e/account.spec.ts` (desktop and mobile): 8 passed.
  - `scripts/validate.sh all` on `d4cf276` (before the two fixes below): lint, format,
    typecheck, eslint ok; Playwright **129 passed, 2 skipped**; backend **4,038 passed, 8 failed,
    3 errors** (1h02m44s). Five failures were contracts not yet taught the pilot: the support
    wording tests (expected states, the form-source label rule for test stand-ins, the capture
    sources read from the code, the labels the API serves) and the sending test's list of
    adapters; fixed, `test_support_wording.py` and `test_sending.py` then **37 passed**. The
    other three failures and three errors were in `test_greenhouse_adapter.py`, caused by me:
    two guard runs started in another worktree without a test-database override reset the shared
    test database while it ran; that file alone then **37 passed**.
  - Merged from `main`: the Gmail reader's move to the standard library (CI #140's Docker jobs);
    on the merged tree the new runtime-import guard and `test_inbox.py` **23 passed**.
- **Not verified:** any real Greenhouse page filled, uploaded to or submitted to; what the first
  real rehearsal will stop on (the one real posting observed read-only had dropdowns with no
  opening evidence, unlisted controls such as a phone country picker, and a location search).

## Your Gmail, read-only, for codes and application emails (D101, 2026-10-31; local only)

- **What you can do now:** once you connect your own Gmail on your machine (docs/inbox.md: a
  Google Cloud "Desktop app" OAuth client, one `connect` run, three settings), Account →
  "Email (your Gmail, read-only)" has two switches. Codes: while an application waits at a
  verification step, a code is entered for you when exactly one new email from its application
  system holds exactly one code. Application emails: rejections, interviews and assessments that
  name one of your submitted applications wait for you to confirm (then recorded on the
  application as your outcome) or dismiss. A "we received your application" email naming an
  application whose submission has an unknown outcome waits for you too: confirming it settles
  the submission as received. Nothing is sent, deleted or changed in your mail, and no email's
  text is kept.
- **By your instruction:** this reverses "NoEfforts never reads an inbox" (D10, R7.5) for these
  two uses only; the guard now allows one read-only Gmail reader and still forbids every other
  mail client (D101).
- **Tests (commands actually run, in a separate worktree and test database, receiver on 8797):**
  - `uv run pytest tests/test_inbox.py`: 22 passed (fixed wording rules; one code only; a real
    code step on the receiver filled from the stand-in mailbox and confirmed, the message used
    once and no code stored or audited; another sender or two codes left to you; nothing read
    while codes are off; rejection proposed for the one named application, interview from
    another employer unlinked, a newsletter not kept, your confirmation recorded as
    `user_reported` with the email's day, once; another account sees and does nothing; a revoked
    connection reported by code; the worker reads when due; no other host contacted; connecting
    asks for read-only mail with PKCE and keeps the token readable by you only; a submission
    the receiver accepted but whose answer was lost waits as `submitted_unconfirmed`, its
    "received" email is proposed, and your confirmation settles it through the reconcile
    transition with the email as evidence, once, never by another account and never once it was
    settled another way; after a receipt such an email is only noted).
  - `uv run pytest tests/test_forbidden_capabilities.py`: 141 passed (one new case: reading is
    allowed only in the reader and only its names).
  - Audit inventory, export decisions, document references, deployment configuration: passed.
  - Sabotage, one change at a time: 10 of 10 caught (several codes, any sender, mixed wording
    guessed, an outcome recorded without you, acceptance across accounts, any host, any
    authorization server, a token readable by others, any scope, codes read while off; the
    last was missed at first and a test was added for it); then 4 of 4 for the "received"
    path (proposed whatever the state, accepted once settled, confirmed without you, no
    evidence).
  - `npx playwright test e2e/inbox.spec.ts e2e/account.spec.ts` (desktop and mobile): 4 passed
    (the card says reading is off on this server; with a synthetic connected view it shows a
    proposed rejection and a code entered for you, and Confirm records it; no horizontal
    overflow).
- **Full validation** (`scripts/validate.sh all` on the first D101 commit, `5beb7da`): lint,
  format, typecheck, eslint ok; backend **3,991 passed, 1 failed** (1h11m22s): the repository's
  address rule (`test_repo_hygiene`) found a real sending domain in a test's sender address; it
  now uses a reserved domain, with the default senders checked by domain in a new test, and
  `test_inbox.py` plus `test_repo_hygiene.py` then **25 passed**. Playwright **125 passed, 2
  failed, 2 skipped** (14.2 min): both failures were the email-reminders spec, whose local mail
  sink could not start because its port (8796) was held by a backend test run I had started in
  another worktree on that port; run alone afterwards, `e2e/email.spec.ts` **2 passed**. The
  pushed commits differ from `5beb7da` only in that test and in documentation.
- **CI #140 on `5581439` (run 41190056397): failed.** Backend and frontend passed; both Docker
  jobs (`docker-smoke`, `execution-compose`) failed because the API could not start in the
  image: the Gmail reader and its connect command imported `httpx`, which only the development
  dependencies install (the image runs `uv sync --no-dev`). Every local and CI test run had it,
  so nothing else caught it. Fixed: both use the standard library, through the same
  public-address and fixture openers as the other server-side reads (`public_https_opener`,
  `fixture_opener`), and a new guard, `tests/test_runtime_dependencies.py`, fails when any module
  under `app/` imports a package only the `dev` group provides (put back, `import httpx` fails
  it). After the fix: `test_inbox.py`, `test_forbidden_capabilities.py`, `test_repo_hygiene.py`
  **166 passed**; the new guard **1 passed**.
- **Not verified:** a real mailbox, a real application system's code email or a real employer's
  reply (a local stand-in of Gmail's API only); the wording rules against real mail.
- **Earlier commit, recorded here:** D100 (`3b6d370`), through `scripts/validate.sh all`: lint,
  format, typecheck and eslint ok; backend **3,970 passed** (1h05m25s); Playwright **125 passed,
  2 skipped** (desktop and mobile); 4,710 s, exit 0. CI #139 (run 41183202758) passed on all
  four jobs.

## Listings by application platform (D100, 2026-10-31; local only)

- **What you can do now:** in Discover, "Find jobs" has "Application platform" boxes
  (Greenhouse, Lever, Ashby, Workday, Workable, SmartRecruiters, Other or not recognised). Tick
  Greenhouse to keep only Greenhouse listings; each one kept is added to your jobs. The
  Discovered list has a platform filter with counts, and every listing shows its platform. The
  platform is read from the listing's address; it says nothing about whether NoEfforts can
  apply there.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_discovery_platforms.py`: 3 passed (an import keeps
    only the chosen platforms and links them; the list and counts by platform, per account; the
    import route takes known platforms only).
  - `cd frontend && npx playwright test e2e/discovery-platforms.spec.ts e2e/discovery.spec.ts`:
    8 passed (desktop and mobile).
  - Sabotage, one change at a time: 4 of 4 caught (the import ignoring the platform, the list
    ignoring it, counts across accounts, any platform name accepted).
- **Not verified:** Freehire itself (refused from this environment) and real listing addresses
  (synthetic ones only, parsed and never fetched).
- **Earlier commits, recorded here:**
  - D98 and D99 (`e633b37`), through `scripts/validate.sh all`: lint, format, typecheck and
    eslint ok; backend **3,967 passed** in 1h03m41s; Playwright **114 passed, 1 failed, 8 did
    not run, 2 skipped**. The failure: a mobile submission test's read of the receiver's ledger
    ended in "socket hang up" (the same test passed on desktop in that run, and both its
    submissions were confirmed). Root cause: the receiver's server closed idle keep-alive
    connections after 5 s, and the test's request reused one at about that moment. Reproduced
    (8 of 20 requests dropped after a 4.99 s idle gap, none after 3 s) and fixed in `d210f58`
    (the receiver keeps idle connections 75 s; 0 of 20 at 4.99 s). On `d210f58`: Playwright
    **123 passed, 2 skipped**; lint, format, typecheck and eslint ok; the backend tests that
    use the receiver most (board sources and daily check, dropdown strategies, email
    reminders, form readiness, Freehire discovery) **138 passed**. CI on `d210f58`: CI #138 (run
    41177544654) passed on all four jobs.
  - D97 (`05011ed`): CI #137 (run 41170899686) passed on all four jobs.

## Saved answers imported from a file (D99, 2026-10-31; local only)

- **What you can do now:** on Saved answers, "Import saved answers" takes a JSON or CSV file of
  questions and answers (for example the old bot's answers, or the review sheet returned to you
  with rows marked yes, no or edit). NoEfforts checks it first and says how many rows can be
  added and why the others cannot (sensitive, work authorization or residence, one employer or
  job, dates, pay, places, licences, long text, `{company}` templates, placeholders, a
  question you already saved, the same question with different answers). The rest are added
  as proposals marked "Imported": each answers nothing until you press "Approve".
- **Tests (commands actually run, in a separate worktree and test database):**
  - `uv run pytest tests/test_bank_import.py`: 6 passed (each row's verdict and reason, a dry
    run writes nothing, proposals unused until approved and then used by a new application,
    nothing replaced, another account's proposal 404, limits; no row text in the response or
    the audit).
  - Sabotage, one change at a time: 9 of 9 caught (sensitive or protected rows imported, a
    conflict resolved by choosing one, a saved answer replaced, an import approved at once, an
    approval across accounts, a dry run that writes, a template imported, row text in the
    response).
  - The suites that touch saved answers, tokens and audit (19 files plus the audit inventory,
    document references, reason codes and API tokens), on a separate database with the test
    receiver moved to port 8797 so as not to disturb another run: 2,230 passed, 2 failed, both
    from the moved port (`test_browser_isolation.py` expects 8799 by name; the discovery
    reason-code test failed the same way on the D97 tree and passed in D97's full run on the
    usual port). The full run on the usual ports is recorded below once made.
  - `frontend/e2e/answers-import.spec.ts`: run in the full validation of this commit.
- **Not done:** the owner's own answers are not imported; that is theirs to do on their own
  NoEfforts after reviewing the private file.

## Question wordings from the owner's archive (D98, 2026-10-31; local only)

- **What changed for you:** a question NoEfforts did not recognise could be saved as a
  reusable answer and filled in again on another form. Run against the 3,364 real questions in
  the owner's old answers (privately, outside the repository), that included religion, tax and
  prohibited-person questions, "Work Status", "state of residence", export-control status,
  "VeteranStatus" and CPA or NMLS licences. Those are now sensitive (never saved, or saved only
  as a sensitive answer you include per form), legal-status checkpoints you answer per
  application, or never saved (licences, address parts). Decision D98.
- **Measured on the archive (wording only, private):** before D98, 51 sensitive, legal-status or
  licence wordings and 12 address parts were still saveable; after it, 5 sensitive-looking ones
  remain by choice (military programs or community, two notices, an option list read by its
  options) and 1 in another language. 77 of 3,364 wordings changed resolution; none was a
  skills or experience question.
- **Tests (commands actually run, in a separate worktree and test database):**
  - `uv run pytest tests/test_classify_archive_wordings.py tests/test_doc_references.py`: 89
    passed (synthetic paraphrases; controls for nearby wordings, the bare "State of residence"
    label still a profile fact, and drafts that state a new topic refused).
  - `uv run pytest tests/test_question_safety.py tests/test_resolver.py
    tests/test_classify_vocabulary.py tests/test_bank_scope.py tests/test_credentials.py
    tests/test_sending.py`: 2,017 passed (the C3-C5 table, its pinned positive controls and the
    legacy collision corpus unchanged).
  - Sabotage, one pattern removed at a time: 17 of 17 caught (three of the first attempts
    changed only part of a pattern and were redone).
- **Not verified:** any real form; wordings in other languages.

## Form readiness and what AI drafting used (D97, 2026-10-31; local only)

- **What you can do now:** on Account, "AI drafting spend" shows the server's daily drafting
  budget and when it resets (00:00 UTC), today's total for the server and what is left, your
  requests and tokens today, the last 14 days and your last 20 requests, each amount marked
  "estimated", "unknown: worst case kept", "in progress: worst case held" or "nothing sent",
  and the list prices an estimate used. It says the amounts are NoEfforts' own accounting, not
  an invoice. Without drafting configured for your account it says nothing is counted.
- **Form readiness:** a form's page is used as soon as its own scripts, styles and data requests
  have finished (no request in flight for 100 ms); a page still loading after 8 seconds stops
  the attempt safely before anything is entered. Images, event streams and WebSockets are not
  waited on.
- **CI baseline closed:** CI #136 (run 41160743875, `650d2f8`) first attempt: backend, frontend
  and docker-smoke passed; execution-compose failed 14 s in, before any test, when Docker Hub
  answered `502 Bad Gateway` for the `node:22-slim` image metadata. Its one re-run of the failed
  job passed: all four jobs green on `650d2f8`. CI #133 (`ded5af1`) is the dropdown failure fixed
  in `79f12d3` (below).
- **Measured, the wait only** (`runner._settle` timed by a pytest plugin outside the
  repository; the same test files before and after):
  - Before (networkidle): 271 waits over the execution tests, about 135 s in all; median
    489-491 ms (the 500 ms quiet floor), max 3.0 s (the 2.5 s locale case), none at 8 s.
  - After, on the five adapter test files (90 waits before: 46.6 s): 91 waits, 13.8 s in all; median 113 ms, p90 116 ms; the 2.5 s locale
    case 2.6 s (waited for, as it must), the new never-ready case 1.0 s (its test allowance) and
    not ready. Those five files: 152 passed in 484 s before, 153 passed in 464 s after (one new
    test). Across all 271 execution-test waits this would save about 100 s (an estimate from the
    median, not measured on the other files).
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_form_readiness.py tests/test_drafting_provider.py`:
    39 passed (5 new readiness cases, 7 new drafting cases, the failure table now 9 cases).
  - `uv run pytest tests/test_dropdown_strategies.py tests/test_account.py tests/test_migrations.py`:
    51 passed (the new never-ready case: failed safe, nothing disclosed or accepted, the locale
    file requested once); `test_migrations.py -k d97`: the backfill case passed.
  - Sabotage, one change at a time (script outside the repository), 15 of 15 caught: the wait
    returning at once, nothing tracked, images tracked, a not-ready page used anyway, listeners
    never removed, a second settlement applied, an error reply recorded as free, a refused request
    counted as sent, a stale reservation shown as running, the server total shown to every
    account, other accounts' rows in the view, a worst case counted as an estimate, the budget
    settings left out of the export, old error rows left at 0 by the migration, the day's total
    counting yesterday.
  - `cd frontend && npx playwright test e2e/drafting-spend.spec.ts e2e/account.spec.ts
    e2e/drafting-consent.spec.ts`: first run 7 passed, 1 failed (desktop `account.spec.ts`: the
    deletion list had not appeared within 5 s, as the first page of a cold server; it was there in
    the failure snapshot, and the run took 1.6 minutes); run again: 8 passed (desktop and mobile)
    in 38.8 s. `npx tsc --noEmit` and `npm run lint`: ok.
- **Full validation** (commit `05011ed`, through `scripts/validate.sh all`, run sequentially):
  lint, format, typecheck and eslint ok; backend **3,873 passed** in 56m45s; Playwright **121
  passed, 2 skipped** (desktop and mobile) in 11.5 minutes; 4,107 s in all. The backend run was
  shared with other work on the machine for part of the time, so its duration is not a clean
  comparison with the 1h00m20s before.
- **Not verified:** any real provider bill or usage (stub client only; no key, no paid request),
  any real employer page (local pages and the receiver only).

## CI #133: a dropdown on a slowly loading page (2026-10-31; local and CI only)

- **What failed:** CI #133 (run 41148189871, `ded5af1`, a commit that changed one document),
  backend job: `test_dropdown_strategies.py::test_each_strategy_selects_exactly_the_approved_option[locale_gate]`,
  1 failed, 3,847 passed. The attempt stopped safely ("no supported action opened it"); nothing
  was sent. The same test passed in CI #132 and #134 and in both local full runs.
- **Root cause:** on that fixture page a dropdown responds only after a locale file the page
  fetches at load time has arrived. The runner acted on the form as soon as the page's `load`
  event fired; on a busy runner the file came later, so the first click (the only action that
  opens this control) was spent before the control listened, and the other two actions do not
  apply. A real page that wires its controls up after its own requests would fail the same way.
- **Fix:** after opening the form, the runner waits until the page's own requests have finished
  (`networkidle`, at most 8 seconds) before reading or touching it (`runner._settle`). It only
  waits: nothing is sent, repeated or retried, and a page that never goes quiet is used as it is
  after the wait. The safe stop for a control that cannot be opened is unchanged.
- **Reproduced first, then fixed:** a new case with the locale file delayed by 2.5 seconds
  (`locale_delay_ms`, fixture only) failed exactly as in CI before the change (`1 failed, 7
  passed`) and passes after it; `tests/test_dropdown_strategies.py`: 20 passed.
- **Full validation on the final tree** (commit `79f12d3`, tree `e2de773`, through
  `scripts/validate.sh all`, run sequentially): lint, format, typecheck and eslint ok; backend
  **3,858 passed** in 1h00m20s (about 8 minutes longer than before; D97 measured the wait at
  about 2 of those minutes, see below); Playwright **119 passed, 2 skipped** (desktop and mobile) in 12.1 minutes. CI #135
  (run 41155083813, `79f12d3`) passed on all four jobs.

## A daily check of a job board you choose (D96, 2026-10-31; local stand-ins only)

- **What you can do now:** on a board in Discover, tick "Check daily". The worker reads it once
  a day (when job boards are switched on), and new postings, ones first seen after the board's
  first successful read, appear in Notifications as one notice per board per day ("2 new
  postings on the Greenhouse job board you added"), linking to Discover. At most 10 boards per
  account. Untick it, pause the board or remove it to stop.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_board_daily_check.py tests/test_board_sources.py
    tests/test_notifications.py tests/test_migrations.py tests/test_account.py
    tests/test_audit_inventory.py tests/test_reason_codes.py tests/test_doc_references.py`:
    108 passed, 8 of them new (nothing read until you choose it; once a day, through the same
    request boundary per the stand-in's ledger; not while off, paused, backing off or turned off;
    a failed daily read changes nothing; new postings after the first read are one notice a day,
    never a job, an application or an email; the per-account limit; another account's boards
    and notices; a board its owner is reading is skipped; exported);
  - one existing guard changed deliberately: the count of account-scoped queries in the feed
    (`test_every_query_of_the_feed_is_scoped_to_the_account`) now includes the board query,
    which filters both tables it joins by the account;
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test
    e2e/board-sources.spec.ts e2e/notifications.spec.ts`: 4 passed (desktop and mobile). The
    first run failed: the "Check daily" box changed only after the server answered, so a click
    showed nothing; it now changes at once and returns to the server's state on a refusal;
  - sabotage (11 single changes, files restored by MD5): 8 caught alone (the daily choice
    ignored, more than once a day, the baseline moved every read, the first read announced,
    notices not scoped to the account, no per-account limit, a notice that needs you (so
    emailed), a board being read breaking the tick); 3 not caught alone because `sync` refuses
    the same reads (paused, backing off, switched off); each caught with both layers removed.
- **Full validation on the final tree** (commit `b815d04`, tree `8523cf6`, through
  `scripts/validate.sh all`, run sequentially): lint, format, typecheck and eslint ok; backend
  **3,857 passed** in 52m15s; Playwright **119 passed, 2 skipped** (desktop and mobile) in 11.0
  minutes. CI #134 (run 41148946538, `b815d04`) passed on all four jobs.
- **Not verified:** any real board (as D95).

## Employer job boards (D95, 2026-10-30; local stand-ins only, no real board read)

- **What you can do now:** in Discover, Employer job boards: add a Greenhouse board (its board
  token) or a Lever site (global or EU) with the employer's name, press "Read now", show its
  postings (what the board lists, "No longer listed by the board since …" after a complete read,
  the match summary, a link to the posting at the source), save one to your jobs (or see it is
  already there), pause, resume and remove a board. A failed read shows "last read failed" with
  a safe reason and changes nothing. Only when the owner sets
  `NOEFFORTS_BOARD_SOURCES_ENABLED=true`; otherwise boards can be added and none is read. Ashby
  shows why it is not available.
- **Research:** `docs/research/job-board-apis.md`. Greenhouse's Job Board API pages read from
  Greenhouse's documentation repository (the rendered site failed DNS here); Lever's Postings API
  README read in full; Ashby's documentation unreachable (DNS) on 2026-10-29 and 2026-10-30, so
  no Ashby connector. Completeness rules (Greenhouse `meta.total`, Lever's short page) are my
  inference from the documented shapes, recorded as such.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_board_sources.py`: 31 passed, against the receiver's
    stand-ins of the two documented feeds and their own request ledger (off by default; an
    identifier never a URL; one GET with no cookie, credential or body; Lever paged until a short
    page; repeated reads and saves never duplicate; reconciliation with a job you have; only a
    complete read marks "no longer listed"; an incomplete read (Greenhouse total mismatch,
    Lever page limit) closes nothing; 404, 503, 429 with Retry-After, redirect to a metadata
    address, oversize, not JSON and a failing second page change nothing and back off; two reads
    at once refused; scripts, handlers and `javascript:`, `data:`, metadata and loopback links
    neutralised and never fetched; malformed records skipped; pause, resume, rename, remove;
    another account gets 404; no application, route or approval created; outside tests the
    fixed host only; the public opener refuses other hosts, plain HTTP, other ports, a login in
    the address and a private address at connect; export, deletion, audit and logs);
  - `tests/test_repo_hygiene.py` with it: 34 passed (the first run flagged a test's
    `u:p@host` literal as an email address; it is now built from parts);
  - `tests/test_deployment_config.py`: 11 passed, including
    `test_every_owner_setting_in_the_example_reaches_the_api_and_the_worker`; with one
    pass-through removed from `docker-compose.yml` it fails (restored by MD5);
    `docker compose config` with a synthetic `.env` shows a value set there reaching both the
    API and the worker;
  - `cd frontend && npx playwright test e2e/board-sources.spec.ts e2e/discovery.spec.ts`: 8 passed
    (desktop and mobile; add, read, save, pause, remove through the UI; the stand-in's ledger
    shows one GET of the documented path with no cookie, credential or body);
  - sabotage (12, each caught, files restored by MD5): an incomplete read closes postings, the
    Greenhouse total ignored, a failed read closes postings, an override honoured outside tests,
    redirects followed, links kept as given, descriptions kept as HTML, a read adding jobs, no
    ownership check, Lever stopping after one page, no address check at connect, a credential
    header sent.
- **Found on the way (D94 configuration):** Compose passes a container only the variables
  `docker-compose.yml` names, and it named none of the email, discovery, drafting or session
  settings: setting `NOEFFORTS_EMAIL_*` in `.env` had no effect under Compose, contrary to the
  deployment guide. Fixed by naming each owner setting (no `env_file`, so the runner and proxy
  secrets stay out of the API container); the guide is corrected; a test keeps `.env.example`
  and Compose in step; `check_env.py` warns when email or boards are on.
- **D94 wording corrected:** "never sent twice" claims narrowed to what the code guarantees:
  NoEfforts never resends an uncertain message and never puts an item in a second digest; a
  duplicate further down the delivery chain cannot be ruled out; server acceptance is not inbox
  delivery; turning reminders off stops only what no worker has claimed; an accepted message
  cannot be recalled (settings page, decision D94, deployment guide, evidence matrix, a test
  name). The export keeps your address, its verification time and your preferences, and leaves
  out the code's keyed digest and the delivery's keyed recipient digest (credential material),
  as D94 now says.
- **Full validation on the final tree** (commit `a41c59e`, tree `9718e05`, through
  `scripts/validate.sh all`, run sequentially after a container restart stopped the first run):
  lint, format, typecheck and eslint ok; backend **3,849 passed** in 52m14s; Playwright **119
  passed, 2 skipped** (desktop and mobile) in 11.5 minutes.
- **CI for this commit:** #132 (run 41135046717, `a41c59e`) passed on all four jobs: backend,
  frontend, docker-smoke and execution-compose.
- **Not verified:** any real Greenhouse or Lever board (none read; the live hosts were never
  contacted, and this sandbox's network policy was not tested against them); Ashby (not built).
- **CI for the previous commit:** #131 (run 41122842515, `af49cd2`, D94 results) passed on all
  four jobs: backend, frontend, docker-smoke and execution-compose.

## Email reminders to the account owner (D94, 2026-10-30; local SMTP sink only, synthetic accounts)

- **What you can do now:** in Account, Email reminders: save your address, ask for a code, type
  it in, choose what to be reminded of (applications that need your attention, follow-ups due)
  and the hour of the daily digest, then turn reminders on (and off with one click, or remove
  the address). Each digest says how many of each and links to your tracker; it never names a
  job or employer and never emails anyone else. Recent emails show what happened to each:
  accepted by the mail server, cancelled, not sent, or "may or may not have been accepted
  (NoEfforts never sends it again)". Only when the owner configures a mail server
  (`NOEFFORTS_EMAIL_*`); otherwise the page says email is not set up.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_email_reminders.py`: 25 passed, against the local
    SMTP sink's own ledger (default off; opt-in needs a verified address; codes expire, run out
    and are limited; a new address cancels what is pending; digest content and links; categories;
    one digest a day and no item put in a second digest; read items not emailed; before the hour nothing; opting
    out and account deletion before dispatch send nothing; two workers send once; transient
    refusals retried at most three times; refusal then acceptance sent once; permanent refusal
    not retried; a refused connection; a lost or slow answer after the message is uncertain and
    never resent; a lost worker leaves it uncertain; a late result after recovery is fenced;
    another account and API tokens refused; no application or follow-up changed; nothing sent
    but to the verified owner; logs and audit without address, code or message, and the export with your address, its verification time and your preferences but no code digest; the
    configuration checks);
  - `tests/test_account.py tests/test_api_tokens.py tests/test_audit_inventory.py
    tests/test_reason_codes.py tests/test_doc_references.py tests/test_repo_hygiene.py
    tests/test_migrations.py tests/test_deployment_config.py tests/test_audit_privacy.py`:
    134 passed;
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test
    e2e/email.spec.ts`: 2 passed (desktop and mobile; the code and the digest read from the
    sink's ledger through the receiver; the link changes nothing);
  - sabotage (13, each caught, files restored by MD5): an uncertain send retried, unbounded
    retries, a claim ignoring status, opting out not cancelling (alone, and with the re-check at
    claim removed too), a new address not cancelling (alone, and with the recipient re-check
    removed too), read items emailed, an item put in a second digest, a lost worker's mail resent, any
    code verifying, no fencing, any domain;
  - `scripts/test_validate.sh`: 6 checks pass; with `finish` made to always succeed it fails
    (exit 1); `scripts/validate.sh quick` then caught 7 real lint errors and one formatting
    difference in this change (exit 1) before they were fixed.
  - two earlier static guards changed deliberately, each narrowly: R7.5's mail scan now lets
    exactly `smtplib` and `email.message` in the mail module, `email` in the test sink and the
    sink's import in the receiver and its test (`OUTBOUND_MAIL`); IMAP, POP, a mailbox or any
    provider API stay forbidden everywhere, those files included
    (`test_outbound_mail_is_allowed_only_where_listed_and_reading_mail_never`); and the feed's
    allowed readers add `mail/service.py`, which builds the digest (the notifications module
    still sends nothing). Found by the first full backend run on this change: 2 failed, 3,814
    passed; fixed, then those suites 177 passed. While the wrapper's Playwright step ran I also
    started those suites, which share the receiver's port: they errored (12) against the wrong
    receiver. That concurrent run is void and was repeated alone.
- **Full validation on the final tree** (commit `336b1c9`, tree `a075d2e`, through
  `scripts/validate.sh`, run sequentially): lint, format, typecheck and eslint ok; backend
  **3,817 passed** in 54m51s; Playwright **117 passed, 2 skipped** (desktop and mobile) in
  10.7 minutes. The first wrapper run on the earlier tree reported `validation FAILED: backend`
  (exit 1) for the two guards above: the wrapper did its job.
- **Not verified:** a real mail server (none configured or authorized); delivery to an inbox
  (acceptance by a server is all any sender can know).
- **CI for the previous commit:** #130 (run 41076244019, 43d0d30, D93 results) passed on all four
  jobs: backend, frontend, docker-smoke and execution-compose.

## Freehire's own signals, display-only (D93, 2026-10-30; fixture only, no Freehire request)

- **What you can do now:** on Discover and on a job found through Freehire, read what Freehire
  says about the posting, in its terms: its class ("likely evergreen", or "classified as
  “fresh”"), how long it has been listed, how often it was reposted, its mass-posting count and
  a fake-freshness flag. Marked "not checked by NoEfforts"; nothing uses it to match, approve
  or apply.
- **Tests (commands actually run):** `cd backend && uv run pytest tests/test_freehire_discovery.py`:
  48 passed (5 new: field-by-field types, the wording, the listing and job page, refresh without
  a change, and a code scan that only the provider and the two display routes read the signals;
  `test_no_raw_payload_is_kept` now asserts exactly what the signals hold, and its raw-only
  marker is a raw value never stored); `cd frontend && npx tsc --noEmit && npm run lint` clean;
  `npx playwright test e2e/discovery.spec.ts`: 6 passed (desktop and mobile); sabotage 4/4
  caught (a boolean as a count, any class text, matching reading them, signals in the
  fingerprint), files restored by MD5.
- **Full suites on the final tree** (commit `678f397`, tree `b8b4544`, run sequentially):
  backend **3,791 passed** in 39m41s; Playwright **115 passed, 2 skipped** (desktop and mobile)
  in 9.6 minutes.
- **Not done:** filtering or sorting by a signal. Live Freehire reads stay row 11.
- **CI for the previous commit:** #129 (run 41067938580, 879e02e, D91-D92) passed: backend,
  frontend, docker-smoke and execution-compose.

## Follow-ups and the decision register (D91, D92, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** once an application is submitted (or you record "I applied
  myself"), the tracker panel and the application page show when to follow up (7 days later by
  default, `NOEFFORTS_FOLLOW_UP_DAYS`), let you say "I followed up" (the next one is 7 days on),
  choose a day, or stop and resume the reminders. When it is due, the tracker list says
  "Follow up due" and a notification appears. "A message you can copy" holds a short follow-up
  message with the job, the day you applied and your name from your profile; NoEfforts never
  sends it. An offer, a rejection, a withdrawal or "no response" closes the follow-up; an
  interview or assessment you record starts the wait again from its day.
- **Decisions made (D91):** every open question in `docs/remaining-work.md` is decided in its
  "Decision register", or marked **external** where it is the owner's permission (live pilot,
  inbox, Claude key, hosting). Standing approvals are decided against (owner default).
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_follow_ups.py`: 18 passed (before submission;
    due day; the owner setting; done; a chosen day and its range; stop and resume; closing
    outcomes; an interview's day; the message's content and what it leaves out; another
    account 404; CSRF; a `read` token lists but never reads the message or changes one;
    audit with the change only; export; deletion);
  - `tests/test_account.py tests/test_api_tokens.py tests/test_audit_inventory.py
    tests/test_notifications.py tests/test_reason_codes.py tests/test_doc_references.py
    tests/test_repo_hygiene.py tests/test_migrations.py`: 104 passed (every table has an export
    decision, every route is swept by token scope, the audit inventory, the migration);
  - `cd frontend && npx tsc --noEmit && npm run lint`: clean; `npx playwright test
    e2e/follow-ups.spec.ts`: 4 passed (desktop and mobile);
  - sabotage (9 guards): 7 caught alone; the account scoping of the list and the
    before-submission guard are each double (the second layer re-checks the first), and each
    was caught with both layers removed. Files restored by MD5.
- **Full suites on the final tree** (commit `234d03c`, tree `46fa6a0`, run sequentially):
  backend `uv run pytest tests -o addopts= -q -p no:cacheprovider` **3,786 passed** in 37m54s;
  `npx playwright test` **115 passed, 2 skipped** (desktop and mobile) in 9.9 minutes.
- **Not done:** sending a follow-up (external messaging is opt-in work, row 8); per-user days.
- **CI for the previous commit:** #128 (run 41041268796, fe68b74) passed: backend, frontend,
  docker-smoke and execution-compose.

## Full suites on the final tree of D88-D90 (2026-10-30; local only)

Run sequentially on commit `b04d31d` (tree `d0452b2`: D89, D90 and the D88 correction after
CI #127), with nothing else using the test ports, databases or Redis:

- `cd backend && uv run pytest tests -o addopts= -q -p no:cacheprovider`: **3,768 passed**, 0
  failed, 0 skipped, in 42m40s.
- `cd frontend && npx playwright test`: **111 passed, 2 skipped** (desktop and mobile), in
  9.7 minutes.
- An earlier full backend run on the tree before the D88 correction was **stopped at 57%**
  (interrupted, not a result) once CI #127 showed the failure it was about to repeat.
- CI on the pushed commit is recorded in the next update.

## A capture-only browser extension (D90, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** load `extension/` unpacked in a Chromium browser, give it your
  NoEfforts address and an API token with only the `import:jobs` scope, then on a job page click
  its button and "Save this job": the job is added to your Jobs list (or it says it is already
  there). Steps in `extension/README.md`.
- **What it never does:** read, fill, upload to or submit a page; see a tab you did not click its
  button on; send your browser's NoEfforts session cookie; talk to anything but NoEfforts on
  this machine; keep a token with any other scope, show a saved token, or send a token to an
  address it was not checked against.
- **Tests (commands actually run):**
  - `cd frontend && npx playwright test e2e/extension.spec.ts`: 5 passed (desktop; the mobile
    project ignores this spec), once with `PW_CHROMIUM_PATH` and once without it (the
    `chromium` channel, as CI runs it): the manifest and code checked statically, the request as
    made (address without fragment, title, Bearer token, `credentials: "omit"`, no redirect),
    nine addresses checked, the options page refusing a broader token and an unknown token and
    dropping the token when the address changes, a fictional posting saved once to the token
    owner's account and not to the account signed in in that browser, a tab without the click
    unreadable, the popup refusing a page that is not a web page;
  - sabotage (7, each caught, files restored): cookies sent, fragment kept, any scope accepted,
    a `tabs` permission added, a non-loopback address accepted, the token kept when the address
    changes, a duplicate reported as new;
  - `npx tsc --noEmit && npm run lint`: clean.
- **Not tested:** the `activeTab` grant from a real toolbar click (not automatable in
  Playwright; the background reads a tab only through the extension APIs that grant governs);
  any browser but Chromium.

## An installable web app with an offline page (D89, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** install NoEfforts from the browser ("Install app" or "Add to Home
  Screen"); it opens on Jobs. Offline, a page you open shows "You are offline" instead of a
  browser error.
- **What it never does:** keep a page, an API response or a document on the device. The service
  worker's cache holds the offline page and one icon only.
- **Tests (commands actually run):**
  - `cd frontend && npx playwright test e2e/pwa.spec.ts`: 4 passed (desktop and mobile): the
    manifest, its icons and the worker; offline after browsing four pages signed in, the offline
    page, no email shown, the cache exactly those two files, and the real page again online;
  - sabotage (2, each caught, files restored): the worker caching pages, no offline fallback;
  - `scripts/docker-smoke.sh` gains the manifest and offline-page checks through the web
    container (the image did not ship `public/` before); not run here (no Docker daemon in the
    sandbox): the CI `docker-smoke` job runs it.

## A Workday-style adapter against the local receiver, checkpoint-first (D88, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** on a job whose posting is on the local receiver's Workday-style
  approximation, press "Read Workday-style test form", answer what NoEfforts cannot know (your
  given name, as "Given Name(s)" is not a wording the resolver knows; the licence; the shift;
  the terms acknowledgement), rehearse, then approve to submit: it submits once and shows the
  confirmation's reference.
- **Checkpoints, never automated:** a sign-in or create-account gate, email verification after
  the final click (an unknown outcome, quarantined), an application on several pages, answers
  the page filled in itself (on load, or after a resume upload), a location list that depends
  on another answer, pickers and custom dropdowns. The account gate and several pages also stop
  an approved attempt before anything is entered if they appear later.
- **Adapter versus fixture:** `fixture_workday` has no Workday identity: a real Workday job is a
  manual handoff and the `workday` specification stays `planned`; the owner's terms decision is
  untouched. This ends the `fixture_<ats>` series.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_workday_adapter.py`: 30 passed, all against the
    receiver ledger; the provider contract, admission, wording, sending, reconcile and
    doc-reference suites with it: 323 passed;
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test
    e2e/workday.spec.ts`: 6 passed (desktop and mobile);
  - sabotage (8, each caught, files restored and checked by MD5): several pages, prefill and a
    dependent location list as checkpoints at capture; an account gate and several pages
    stopping an approved attempt; email verification kept unknown; real Workday host
    recognition; the capture refusal of a real posting;
  - the full backend and Playwright suites are run once on the final tree of this series of
    slices and recorded there; CI on this commit is its full-suite result.
- **CI for the previous commit:** #126 (run 41021787874, c88171f, D87) passed: backend,
  frontend, docker-smoke and execution-compose.
- **CI #127 (run 41028190736, 9e81c51, this slice): failed**, backend only: 1 failed, 3,764
  passed, 1 skipped. `test_execution_routing.py::test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one`:
  `fixture_workday` stops on a challenge but did not claim `captcha_checkpoint`; I had not run
  that module with the slice's targeted suites. Frontend, docker-smoke and execution-compose
  passed. **Fixed in the next commit** (D88 "Correction"): a `wd_challenge` mode, a capture
  checkpoint case and `test_a_challenge_that_appears_after_approval_stops_before_disclosure`,
  then the claim. Commands actually run: `uv run pytest tests/test_workday_adapter.py
  tests/test_execution_routing.py tests/test_provider_contracts.py tests/test_provider_admission.py
  tests/test_providers.py tests/test_lever.py tests/test_doc_references.py
  tests/test_support_wording.py tests/test_workday_ashby_fixtures.py`: 327 passed
  (`test_workday_adapter.py` now 32); sabotage 2/2 caught (the adapter ignoring challenges; the
  fixture never showing one), files restored by MD5.

## An Ashby-style adapter against the local receiver (D87, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** on a job whose posting is on the local receiver's Ashby-style
  approximation, press "Read Ashby-style test form", answer what NoEfforts cannot know (the
  analysis tool, the data consent; authorization and sponsorship come from your facts because
  the questions name the country), approve a rehearsal (it uploads your resume, then stops
  before sending), then approve to submit: it submits once and shows the confirmation's
  reference. The cookie banner is never clicked, the location picker never typed into, the
  EEOC survey never chosen for you.
- **Hard stops:** the approximation's spam check blocks approval when it is on the form, stops
  the attempt before anything is entered if it appears later, and after the final click is an
  unknown outcome, quarantined, never solved, retried or resent; so are "you already applied"
  and a confirmation page that also shows a challenge.
- **Adapter versus fixture:** `fixture_ashby` is for the local approximation only, with no
  Ashby identity: a real Ashby job is a manual handoff, and passing its tests is no evidence
  about real Ashby pages (no Ashby documentation page could be opened from this sandbox).
- **Shared code:** the Lever-style adapter's mechanics moved, unchanged, into
  `execution/adapters/hosted_form.py`, which both adapters use; its tests (30) pass unchanged.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_ashby_adapter.py`: 32 tests, all against the
    receiver ledger (capture, facts versus your answers, unknown sponsorship, unsupported
    required controls and the spam check, real Ashby never read, the full run with
    byte-identical files, rehearsal, duplicate delivery, quarantine, every outcome after the
    final click, the bound confirmation, a partial upload failure, autofill, the spam check
    after approval, drift, a changed input, off-site pages and redirects);
    `test_lever_adapter.py` unchanged after the shared base: 30 passed;
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test
    e2e/ashby.spec.ts`: 4 passed (desktop and mobile; one assertion fixed first: an empty
    survey select is sent as an empty value, not left out); the full `npx playwright test` on
    the final tree: 96 passed, 2 skipped (9.1 min);
  - full backend `uv run pytest tests -o addopts= -q -p no:cacheprovider` on the final code
    tree (this change plus the proxy fix d38ddc6): 3,729 passed, 0 failed (38 min). An earlier
    full run of this change was stopped at 44% when CI #124 failed (interrupted, not counted);
  - sabotage (10, each caught, files restored and checked by MD5): the spam check as a
    checkpoint at capture, the spam check after approval, "flagged" and "already applied" kept
    unknown, real Ashby host recognition, the capture refusal of a real posting, readback of
    unanswered fields, the bound confirmation, a challenge after the click, upload-error
    evidence. The challenge guard was missed at first (the fallback also gave "unknown"); the
    new `test_a_confirmation_page_that_also_shows_a_bot_check_is_not_a_confirmation` catches it;
  - `ruff check` and `ruff format --check` clean. Only this entry changed after these runs.
- **CI:** #124 (1dfcf33, D86) failed on one backend test, fixed by d38ddc6 (see D86 below).
  #125 (run 41016757090, d38ddc6): frontend, docker-smoke and execution-compose passed;
  backend 3,688 passed, 1 skipped, 1 failed: `test_doc_references.py::
  test_every_cited_test_exists`, because d38ddc6's status entry cited `test_ashby_adapter`, a
  module first committed here (my error). The proxy fix's target test passed there. This
  commit adds the module.

## The fixture-origin boundary (D86, 2026-10-30; local only)

- **What changed:** a fixture origin counts only with `NOEFFORTS_ENV=test`, only as an exact
  plain-http origin in `NOEFFORTS_FIXTURE_ORIGINS`, and only on a loopback or test-network
  address literal or the one listed name `receiver` (the Compose service). No general
  single-label rule, no `localhost`. Every connection to a fixture checks what the name
  resolves to and the address actually reached: server-side through the new fixture opener
  (capture, discovery fixture, the read-only check's fixture base, the fake API adapter), in
  the browser through the egress proxy, which now refuses a fixture host:port resolving to a
  public or link-local address (it used to accept any address for one). Redirects: the
  server-side opener follows none and checks every request's origin; in the browser every hop
  goes through the proxy. A fixture is never browsed without the proxy (`isolation=off`).
- **Found while testing, fixed:**
  - In `netns` mode the Playwright driver itself fetched GET/HEAD page loads to the destination
    (and opened its WebSockets) from the worker's network, outside the egress proxy and its
    address checks. Shown with a probe: with interception on, the proxy logged no decision for
    the destination; with it off, it did. The driver now never fetches or connects in `netns`,
    as already in `container` mode.
  - In `netns` mode Chromium could not reach its own proxy relay for a named destination
    (the `MAP * ~NOTFOUND` resolver rule also covered 127.0.0.1); only 127.0.0.1 destinations
    ever worked. The relay address is now kept, as the container launcher keeps its proxy.
- **Compose:** the test override runs the API and worker as `NOEFFORTS_ENV=test`, pins the
  `fixtures` network to `10.231.47.0/24` and names it on the API, worker and egress proxy. Not
  run here: this sandbox has no Docker daemon. CI's `execution-compose` job is the evidence.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_fixture_origin_boundary.py`: 74 tests (which hosts
    count, other spellings and IPv6 forms, test-only, test networks, the opener, the proxy,
    execution through a named host). Every public answer comes from a fake resolver and is
    refused before a connection is opened;
  - every browser-backed module (the 39 files that run an attempt, open a browser session or
    observe a page) after the `netns` driver change: 869 passed;
  - full backend `uv run pytest tests -o addopts= -q -p no:cacheprovider` on the final code
    tree: 3,687 passed, 0 failed (34 min);
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; full `npx playwright test` on the
    final code tree: 92 passed, 2 skipped (8.8 min). The suites ran one after the other, never
    at the same time;
  - sabotage (14, each caught, files restored and checked by MD5): exact names, every resolved
    address, the connected peer, the proxy's fixture-address rule, the proxy's peer check, no
    redirect followed, every request's origin checked, test environment only, other spellings
    of an address, IPv4-mapped forms, narrow private test networks, no fixture without the
    proxy, the driver never fetching in `netns`, the relay kept resolvable. A guard whose
    breakage could reach a public address was exercised only by a test with a fake resolver;
  - two existing tests changed with the rule, not weakened: the Lever host test now expects
    `localhost` to be refused, and the `off` case of the mid-submit resend test no longer sets
    the fixture flag, which `off` now refuses and which changes nothing else in that mode;
  - `ruff check` and `ruff format --check` clean. Only documentation changed after these runs
    (this entry).
- **CI for the previous commit:** #123 (run 40995862833, 75cb2c3, D85) passed: backend,
  frontend, docker-smoke and execution-compose; it stands as the full-suite result for that
  commit.
- **CI #124 (run 41011885378, 1dfcf33, this change) failed, then fixed:** frontend,
  docker-smoke and execution-compose passed (the Compose stack with the pinned test network
  works); backend: 3,685 passed, 1 skipped, 1 failed,
  `test_audit_privacy.py::test_unexpected_runner_errors_are_logged_by_type_only`. Cause, in
  this change's path: with every `netns` request now going through the egress proxy, a browser
  closing while the proxy wrote a refusal made `writer.drain()` raise `ConnectionResetError`
  out of the connection handler, and asyncio logged it with a traceback (the test forbids any
  traceback in logs). It was not reproduced by the local full run (a race). Fix: a client
  hanging up ends its connection without an error; a relayed connection reset by either side
  ends quietly; stopping the proxy finishes its open connections instead of leaving tasks to
  be destroyed later (they logged into whichever test ran next). Reproduced first,
  deterministically, by `test_a_client_that_hangs_up_never_crashes_the_proxy` (a slow refusal
  to a client that has already gone: failed before, passes after); the failing test and every
  proxy-backed suite (`test_audit_privacy`, `test_browser_isolation`, `test_b3_policy`,
  `test_container_runner`, `test_gh_readonly`, `test_execution_security`,
  `test_fixture_origin_boundary`, `test_lever_adapter`, `test_ashby_adapter`): 265 passed;
  sabotage of the hang-up handling and of the clean shutdown: each caught
  (`test_stopping_the_proxy_finishes_its_open_connections`). CI #125 on that fix: the target
  test passed; one documentation check failed (see D87 above).

## A Lever-style adapter against the local receiver (D85, 2026-10-30; local only, synthetic accounts)

- **What you can do now:** on a job whose posting is on the local receiver's Lever-style
  approximation, press "Read Lever-style test form", answer what NoEfforts cannot know (the
  shift, sponsorship asked without a country, the consents), approve a rehearsal (it fills and
  uploads, then stops before sending), then approve to submit: it submits once and shows the
  confirmation's reference. The tracker and Notifications show both, through the existing
  contracts.
- **Adapter versus fixture:** `fixture_lever` is a provider-specific adapter for the local
  approximation only. It has no Lever identity, so it never serves a real Lever posting: a real
  Lever job is a manual handoff and the `lever` specification stays `planned` (no docs-and-terms
  review is recorded). Passing its tests is no evidence about real Lever pages.
- **Hardening found while testing the boundary:** a public site listed in
  `NOEFFORTS_FIXTURE_ORIGINS` used to count as a fixture; a listed origin now counts only on a
  local host (loopback, `localhost` or a single-label internal name); tightened in D86.
- **Tests (commands actually run):**
  - `cd backend && uv run pytest tests/test_lever_adapter.py` (isolated database, receiver
    port and Redis database): 30 passed, all against the receiver ledger; the provider suites
    (`test_provider_contracts.py`, `test_provider_admission.py`, `test_support_wording.py`,
    `test_providers.py`, `test_lever.py`, `test_urlsafety.py`, `test_doc_references.py`) with
    it: 294 passed; `test_reconciling_an_unknown_outcome_never_sends_again` for all four browser
    adapters: 8 passed;
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test
    e2e/lever.spec.ts`: 4 passed; then the full `npx playwright test` on the final tree: 92
    passed, 2 skipped;
  - full backend `uv run pytest tests -o addopts= -q -p no:cacheprovider`: 3,609 passed and
    1 failed (`test_sending.py::test_nothing_else_reads_answer_values_for_sending`, a guard
    pinning the set of adapters that the new one was missing from). The fix is test-only: the
    guard and the sending tests now cover `fixture_lever` (`test_sending.py`: 23 passed). The
    full suite on the exact commit is CI's run;
  - sabotage (7, each caught, restored by MD5): unanswered fields not read back, bot check not
    detected, confirmation not bound to the attempt, a form page off the destination's site,
    a public host listed as a fixture, a real Lever host not recognised, an approximation's
    form on a job of an identified ATS;
  - `ruff check` and `ruff format --check` clean.
- **CI for the previous commit:** #122 (run 40953466919, 65adc39, D84) passed: backend,
  frontend, docker-smoke and execution-compose.

## API tokens, a CLI and an MCP server (priority D, D84, 2026-10-29; local only, synthetic accounts)

- **What you can do now:**
  - make a token in Account → API tokens (label, scopes, expiry of 1 to 90 days), copy it
    once, see when it was last used, and revoke it;
  - `NOEFFORTS_TOKEN=ne_… python3 scripts/noefforts.py jobs` (also `job ID`, `applications`,
    `application ID`, `notifications`, `whoami`, and `import-job URL` with `import:jobs`);
  - point a local MCP client at `scripts/noefforts_mcp.py` (configuration example in
    `docs/api-tokens.md`).
- **What a token can never do:** answer, consent, approve, queue, cancel or submit; enter a
  code; read profile facts, documents or saved answers; export or delete the account; manage
  tokens. A token reads a job without the eligibility side by side.
- **Not there:** a versioned public API, third-party clients, any exposure beyond this
  machine; the MCP server has not been tried with a real MCP client.
- **Found by the full Playwright run, fixed:** the job-statement routes ("still open", "a
  different role") called the job page's route function positionally, which the new
  `request` parameter broke (`job-signals.spec.ts`, both projects; `test_job_signals.py`
  covers it too). Both now share one helper, `_job_detail`.
- **Tests (commands actually run):**
  - `cd frontend && npx playwright test`: 86 passed, 2 failed (the defect above), 2 skipped;
    after the fix, `job-signals.spec.ts` and `api-tokens.spec.ts`: 4 passed (desktop and
    mobile); `npx tsc --noEmit && npm run lint` clean;
  - `cd backend && uv run pytest tests -o addopts= -q -p no:cacheprovider` after the fix: it
    was stopped by the sandbox's 30-minute background limit at 3,512 of 3,576 tests with no
    failure; the remaining files (`test_resolver.py` to `test_workday_ashby_fixtures.py`,
    13 files) were then run whole: 538 passed;
  - the tests that read the documents edited during that run, again: 313 passed and 1 failed
    in the isolated environment (`test_reason_codes.py`, whose discovery fixture expects
    receiver port 8799), 24 passed with the default port;
  - sabotage (8, each caught, restored by MD5): scope check, expiry, hash comparison (missed
    at first: the tampered token was a revoked one; a tampered active token was added),
    plaintext stored, rate limit, session-only, cookie fallback, eligibility hiding;
  - `alembic check`: no new upgrade operations; `ruff check` and `ruff format --check` clean.
- **CI for the slices before this one:** #119 (run 40942966270, 59ffe13, D81), #120 (run
  40944295751, 697a58a, D82) and #121 (run 40945627807, b575c45, D83) passed: backend,
  frontend, docker-smoke and execution-compose.

## In-app notifications (priority C, D83, 2026-10-29; local only, synthetic accounts)

- **What you can do now:** open Notifications (header link, with the unread count) and see,
  newest first, every verification code request, approval that stopped applying, completed
  rehearsal, employer receipt and stopped submission of your applications, each linked to its
  application; mark one read or unread, or all read. Opening one marks it read.
- **How it stays truthful:** nothing is stored but read marks; each notification is built
  from its record every time and says what that record says now. Local test forms are
  labelled "Local test fixture: counts for nothing on a real employer's form".
- **Not there:** no email, text message, push or any other delivery outside the app; no
  notification for an approval that merely expired (not invalidated).
- **Tests (commands actually run):**
  - `cd frontend && npx tsc --noEmit && npm run lint` clean; `npx playwright test`: 86 passed,
    2 skipped (`notifications.spec.ts` on desktop and mobile: a real receipt through the
    Celery worker and the receiver, an invalidated approval, read and unread, links, a second
    account that sees only its own);
  - `cd backend && uv run pytest tests/test_notifications.py tests/test_account.py
    tests/test_audit_inventory.py tests/test_migrations.py tests/test_rehearsal.py
    tests/test_rehearsal_stop.py tests/test_deployment_config.py tests/test_repo_hygiene.py`
    (isolated database, receiver port and Redis database): 87 passed; then the new migration
    test `test_d83_adds_notification_reads_and_downgrade_drops_only_them`: passed;
    `alembic check`: no new upgrade operations; `ruff check` and `ruff format --check` clean;
  - sabotage (3, each caught, restored by MD5): used-up approvals notified apart, attempts not
    scoped to the account, any key markable;
  - the full backend suite on this commit is CI's run.

## The jobs list summarises each match (priority B, D82, 2026-10-29; local only, synthetic accounts)

- **What you can do now:** see on every jobs-list row how the job compares, from the same
  assessment as the job page: "Your preferences: m of n checked preferences met", the approved
  skills and licences of yours its text names (or "Skills and licences not compared" when it
  has no text), how many things are unknown, and a "Why" link to the full explanation
  (`/jobs/{id}#match`).
- **Not there, on purpose:** no score, eligibility verdict or probability; eligibility stays
  side by side on the job page; nothing is filtered, hidden or reordered.
- **Tests (commands actually run):**
  - `cd frontend && npx playwright test`: 84 passed, 2 skipped (the new `match-summary.spec.ts`
    on desktop and mobile among them); `npx tsc --noEmit && npm run lint` clean;
  - `cd backend && uv run pytest tests/test_fit.py tests/test_jobs.py` (isolated database):
    33 passed; `ruff check` and `ruff format --check` clean;
  - sabotage: the summary's unknown count set to 0, caught (2 failed), restored by MD5;
  - the full backend suite on this commit is CI's run.

## Workday- and Ashby-shaped forms; Ashby embeds; credentials and custom widgets fail closed; owner Mac runbook (D81, 2026-10-29; local only, no request to any vendor)

- **Changed:**
  - The generic extractor (`html-v3`) reads password and one-time-code inputs as unsupported:
    an account gate blocks approval, and no password is ever asked for or kept.
  - It keeps custom ARIA widgets with no native input as unsupported questions, never dropping
    them.
  - The fixture adapter detects a bot check at execution too.
  - `?ashby_jid=<uuid>` embeds are Ashby, fail-closed: a non-UUID or two embedded ids are
    unknown, and the any-host trust is recorded as a gap for Ashby.
  - New preparation fixtures "workday" (a one-page rendering of the account-gated wizard) and
    "ashby".
  - Provider evidence ladder added to `docs/remaining-work.md`.
- **Owner Mac runbook:** `docs/owner-mac-verification.md`. `scripts/verify-local.sh` now ends
  with a summary block that is safe to share: step results and versions, never a value, path
  or log line. Tested with no Docker, and with a stand-in Docker CLI and a good `.env`; no
  secret value appears. **The Mac itself is still unverified.**
- **Sabotage (5, each caught, restored by MD5):**
  - passwords read as text;
  - custom widgets dropped;
  - an owned listbox counted twice (first missed: the hidden rule masked it; a test that
    isolates it was added, then it was caught);
  - two embedded ids believed;
  - any `ashby_jid` believed.
- **Found by the full backend run, fixed:**
  - the provider-admission document still listed only Greenhouse under the
    `identity_jid_any_host` gap (`test_provider_admission.py`);
  - a real defect: a custom widget's key comes from the page's own markup (`aria:<id>`), and the
    read-only Greenhouse check listed it among keys only on the page, so its leak guard refused
    to publish the whole summary (`test_widget_detector.py`, the `portal_unlinked` decoy list).
    The comparison now counts such controls (`page_custom_controls`) and never names them.
- **Tests (commands actually run):**
  - before the fix: `cd frontend && npx playwright test`: 82 passed, 2 skipped; then
    `cd backend && uv run pytest tests -o addopts= -q -p no:cacheprovider`: 3,524 passed,
    2 failed (the two above), 32 min 49 s;
  - after the fix: `uv run pytest tests/test_widget_detector.py tests/test_gh_readonly.py
    tests/test_provider_admission.py tests/test_workday_ashby_fixtures.py
    tests/test_lever_fixture.py`: 253 passed; `ruff check` and `ruff format --check` clean;
    the full suite on this commit is CI's run.
- **CI:** #118 (run 40927851828, 52e1c4c, the Lever commit) passed: backend, frontend,
  docker-smoke and execution-compose.
- **What this is not:** a provider-shaped fixture is not a provider adapter. Workday and Ashby
  stay a manual handoff (planned adapter only) and real hosts stay refused; test counts and
  passing CI are no evidence of live support.

## A Lever-shaped form, checkpoint-first (D80, 2026-10-29; local only, no request to Lever)

- **Changed:**
  - The generic extractor (now `html-v2`) reads a search-as-you-type picker (`role=combobox`,
    `aria-autocomplete`) as unsupported, never as a text box.
  - On the generic capture path, a CAPTCHA or bot check found by its documented markup becomes
    a required unsupported field, so approval waits and the user applies on the employer's
    site.
  - A Lever-shaped fixture ("lever") carries the search-reported shapes from
    `docs/research/lever.md`.
- **Proved:**
  - Pickers stay blank; the licence number and preferred shift wait for the user.
  - Both consents need the user's choice; EEO answers are never inferred.
  - Authorization comes from the approved fact only, and unknown stays unknown.
  - The bot check blocks approval with everything else answered.
  - The route stays a manual handoff. Words like "captcha" in text are not a bot check.
- **Deliberate version change:** `fixture-ats-1+html-v1` → `fixture-ats-1+html-v2`; approvals
  bound to the earlier version ask again (D80).
- **Sabotage (4, each caught, restored by MD5):**
  - pickers read as text;
  - CAPTCHA ignored;
  - capture without challenge detection;
  - the bot check made optional.
- **Tests:** `tests/test_lever_fixture.py` 11 passed. With `test_preparation.py`,
  `test_provider_contracts.py`, `test_greenhouse_adapter.py` and `test_execution_routing.py`:
  118 passed. `test_sending.py` and `test_package_contract.py` (every fixture, the Lever one
  included): 23 passed.
  - Full Playwright: 82 passed, 2 skipped (7.9 min).
  - Full backend: 3,501 passed, 0 failed (35 min 8 s).
  - `ruff check`, `ruff format --check` and `tsc --noEmit`: clean.
- **CI for the previous change:** CI #117 (run `40919870404`, `efd9559`, priorities B, C and D)
  passed.

## Data export and account deletion; saved-answer editing and document preview; explainable match (priorities B, C, D: D77-D79, 2026-10-29; local only, synthetic accounts)

- **B, export (D77):** Account → "Download all my data" is one ZIP:
  - every record that names the account, column by column, from an explicit list;
  - every document file, byte for byte, named by its id;
  - a README of what was left out and why.

  Left out: login and session secrets, keyed references and digests (also inside JSON values),
  worker lease internals, a verification code, storage locations, two internal tables. A table
  or column added later fails a test until it is listed or left out with a reason. Audited as
  `account.export`, with counts only.
- **B, deletion (D77):** Account → "Delete my account" needs the password and the phrase. It
  deletes everything that names the account in one transaction, files after the commit, and
  sessions at once.
  - The cascade is checked in the migrated database.
  - A submission past the send gate refuses deletion, and nothing is deleted.
  - Queued work is deleted and finds nothing. A worker holding an attempt is fenced out
    before the send gate. Nothing is retried.
  - Lock order: watches, attempts, applications, then the account row; raced against both
    gates.
  - The retention decision is isolated in `account/policy.py`. Default: nothing kept in the
    database, no grace period. Not reachable from NoEfforts: employers, backups, logs, an AI
    provider; all are listed before deletion and in `docs/account-deletion.md`.
  - **No deletion was run against a real account.**
- **C (D78):**
  - **Saved answers:** an edit is a new version, bound to the same question; every version is
    kept and listed.
  - Applications whose package used the earlier version are rebuilt, and their approvals
    invalidated with the reason. A running submission stops at its gate (added to the
    protected-mutation tests).
  - **Documents:** "Preview text" shows the extracted text as plain text only (20,000
    characters at most): no viewer, no HTML, no external request.
  - **Profile:** work history, education and licences can be edited in place.
- **D (D79):** the job page's "Why this job matches (or doesn't)" shows, kept apart:
  - your preferences, each met, not met, not stated or not set, with "m of n checked
    preferences met";
  - eligibility side by side (what a source says next to your approved facts, tri-state, no
    verdict, the job's country never derived);
  - your approved skills and valid licences that the job's text names;
  - what is unknown.

  Never a probability or an ATS score; nothing filters, ranks down or submits.
- **Sabotage, each caught by a failing test, files restored and checked by MD5:**
  - B (4): in-flight not refused; export not scoped; keyed values kept; password hash
    exported.
  - C (5): no rebuild after an edit; no history kept; any option accepted; edit not scoped;
    preview untruncated.
- **Tests:**
  - `tests/test_account.py` 16 passed; `tests/test_bank_edit.py` 15 passed; `tests/test_fit.py`
    15 passed.
  - `test_every_protected_mutation_stops_a_running_attempt` now covers `answer_bank_edit`;
    11 passed.
  - Full backend (`uv run pytest tests`): 3,490 passed, 0 failed (32 min 54 s).
  - Full Playwright (`npx playwright test`): 78 passed, 2 failed, 2 skipped (7.9 min). Both
    failures were `account.spec.ts`, desktop and mobile, a selector error in my test:
    `getByRole("alert")` also matched Next's empty route announcer, while the expected
    "That is not your password" alert was shown.
  - After that fix, `account.spec.ts`, `answers-edit.spec.ts` and the new
    `profile-edit.spec.ts`: 8 passed, desktop and mobile (30 s).
  - `ruff check`, `ruff format --check`, `tsc --noEmit`, `npm run lint`: clean.
- **CI for the previous change:** CI #116 (run `40911697501`, `bc805be`) passed all four jobs.
  `docker-smoke` was the first real-container run of the health-gated start and of the
  backup and restore round trip.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; no new outbound path.

## Owner deployment readiness (priority A, D76, 2026-10-29; local and CI only, not run on the owner's Mac)

- **State:** awaiting deployment verification. The Compose stack is built and started in CI on
  Linux; it has **not** been run on the owner's Mac, and the images have not been built on arm64.
- **Changed:**
  - The API has a health check, and the worker and web app start only once it is healthy.
    Healthy implies migrated, because the API starts only after `alembic upgrade head`.
  - `scripts/check_env.py` refuses missing, placeholder, short or reused secrets, and prints key
    names only.
  - `scripts/verify-local.sh` is the safe local check (a throwaway project, never the owner's
    data).
  - `docs/deployment.md` is the owner's guide: start, health, backup, upgrade, rollback, stop,
    verify, Mac notes.
  - The CI smoke job also backs up and restores.
  - `backups/` is ignored and refused by the hygiene test.
  - README Docker steps corrected. Its stale "submission is not implemented yet at all" now says
    what is true: submission works only to the local synthetic receiver.
- **Found while writing the guide:** the obvious rollback, `pg_restore --clean`, leaves tables
  that only the newer version had. The guide drops and recreates the database instead, and CI
  runs exactly those commands.
- **Run in the cloud sandbox (Docker Compose v5.6.0 CLI, no images built):**
  - `python3 scripts/check_env.py <good file>` exit 0. Without `AUDIT_REF_KEY`: exit 1, "missing".
    On `.env.example`: exit 1, three errors and one warning.
  - `docker compose --env-file <good file> config --quiet` exit 0; with the execution overlay,
    exit 0.
  - Without `AUDIT_REF_KEY`, and with `.env.example`: exit 1, "required variable AUDIT_REF_KEY is
    missing a value".
  - The rendered config shows `service_healthy` for worker and frontend, and every published
    port on 127.0.0.1.
  - The health probe command: exit 1 with no API; exit 0 against a running API (uvicorn on
    127.0.0.1:8000, stopped afterwards), even with a dead proxy in `HTTP(S)_PROXY`.
  - `bash -n` on `docker-smoke.sh` and `verify-local.sh`: OK.
- **Tests:** `tests/test_deployment_config.py` 8 passed, and `tests/test_repo_hygiene.py`; the
  full backend run is in the journey entry below. The CI `docker-smoke` job is the first run
  of the health-gated start and of the backup and restore in real containers. Each safeguard
  was broken once and a test failed:
  - worker no longer waiting for health;
  - a port on all interfaces;
  - the checker printing a value;
  - placeholders accepted;
  - `backups/` not ignored.

  Files were restored and checked by MD5.
- **Mistake during this work, and its effect:**
  - One sabotage run used the shared test database while the full backend suite was running on
    it, and reset its schema mid-run (`FEF` at 35%).
  - That run was stopped and discarded, and the full suite was run again: results in the
    journey entry below.
  - Stopping it left its disposable Redis running, which caused that rerun's one failure.

## Scope reconciled; one synthetic journey through the whole product (D75, 2026-10-29; local only, no external request)

- **Scope:** `docs/remaining-work.md` is now the canonical list of what remains, with each item's
  state, evidence, dependency and next step. It covers every planned surface (web, API, CLI,
  MCP, extension, mobile, messaging) and defines "Phase E". NoEfforts is **not** a finished
  product: rows marked Unfinished are product functionality that does not exist yet.
- **Journey:** `frontend/e2e/journey.spec.ts` runs one synthetic journey through the real UI, API,
  worker and receiver (desktop and mobile). The steps are listed in D75: from Freehire-shaped
  discovery to receipt, timeline and outcome, with the receiver's ledger as the oracle.
- **Proved by it:** unknowns become checkpoints and block approval. A fact changed after approval
  invalidates it, and the change is shown. What arrived is what was approved, byte for byte for
  the tailored resume. Preparing again opens the same application, and the API refuses to queue
  it again. A real Greenhouse host is refused and offered no test-only control. The
  unknown-outcome path stays covered by `submission.spec.ts` ("unknown outcome is reconciled in
  the tracker, never resubmitted").
- **Broken transitions found by the journey and fixed:**
  1. The job page's route card stayed "Capture the application form first" after capture.
  2. An accepted tailored resume was missing from the resume choice until a reload.
  3. The tracker offered no link back to a submitted application.
- **Also fixed:** a real employer's job no longer offers test-only form controls.
- **Open UX gap found:** work history, education and licences cannot be edited in the page
  (remaining-work row 16).
- **Test-only provider:** `preparation/fixture_provider.py` (D75): labelled, local, used only in
  env `test` for `NOEFFORTS_DRAFTING_TEST_FIXTURE_USERS`; nothing leaves NoEfforts.
- **Documentation research (approved, read-only):** Lever's Postings API README and integrator
  repository read on GitHub. `hire.lever.co`, `help.lever.co`, `developers.ashbyhq.com` and
  `doc.workday.com` are outside this sandbox's network allowlist (DNS `ENOTFOUND`), so no Workday
  or Ashby page was opened. The notes are in `docs/research/{lever,workday,ashby}.md`, with
  Workday and Ashby facts labelled "search-reported". No employer posting was opened.
- **Read-only Greenhouse observations, stated exactly** (remaining-work "What was observed"):
  - one posting's public job JSON and its page were read in owner-authorized runs;
  - in two runs, 12 dropdowns were clicked open, and nothing was selected;
  - nothing was ever typed, uploaded or submitted on any real site.
- **Tests:**
  - `journey.spec.ts`: 1 test, passed on desktop (35.7 s) and mobile (35.2 s);
    `tests/test_fixture_provider.py` 4 passed; `tests/test_drafting_provider.py` 26 passed (the
    static guard now names the two provider classes).
  - Full Playwright (`npx playwright test`, both projects): 74 passed, 2 skipped (7.8 min).
  - Full backend (`uv run pytest tests`, together with the deployment slice below):
    3,442 passed and 1 failed (32 min 53 s). The failure,
    `test_real_broker_outage_around_outbox_publication`, was caused by my own mistake:
    - The run I stopped (below) left its disposable Redis on port 6391 running.
    - This run's broker fixture could not bind the port, and its "outage" stopped nothing.
    - With that orphan stopped, `tests/test_broker_failures.py` passed: 4 of 4 (50 s).
  - `ruff check` and `ruff format --check` clean; `tsc --noEmit` and `npm run lint` clean.
- **CI for the previous change:** CI #115 (run `40872211758`, commit `4d2aca7`, docs only)
  passed.

## Claude as the drafting provider, built and off (L4, 2026-10-29; local only, no request to Anthropic)

- **Scope:** plan step L4, decision D74. **Done in code and off**: no key exists in the
  repository or the sandbox, the default budget is 0, and no request was made to Anthropic.
  Turning it on is the owner's step (provider, key, owner account and budget on the server,
  then agreeing in the app).
- **Now:** drafts, tailored resumes and cover letters can be written by Claude
  (`claude-opus-5-5`, Anthropic's Messages API, the official SDK), only for an account named by
  the owner, only after that user agrees in the profile to the exact consent text (what each
  request holds and never holds), and only within a daily budget that each request reserves at
  its worst case before it is sent (migration `452ae3b5aec9`). A failed request keeps nothing
  it returned and says why with a fixed code; the review page says why drafting is off and
  links to the profile card.
- **New dependency:** `anthropic` 2.3.0 (Apache-2.0) and five small transitive packages (D74).
- **Found while checking the docs:** the answer policy still said a draft's numbers could come
  from the job text, which C15 had already removed; corrected.
- **Tests:** `tests/test_drafting_provider.py` 26 passed; `drafting-consent.spec.ts`; the L4
  migration test. Sabotage 17 cases, 17 caught (the race case also caught in 5 of 5 further
  runs; intact, it passed 8 of 8).
- **Changed test:** `drafts.spec.ts` serves a synthetic view that now also says
  `drafting_status: "available"`, the field the page reads since L4.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):** full backend 3431 passed, exit
  0, 37 min 25 s; full Playwright 72 passed, 2 skipped, exit 0, 7.6 min; `ruff check`,
  `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: exit 0. Migration `452ae3b5aec9`:
  `alembic check` clean, downgrade and upgrade run.
- **CI for the previous change:** CI #113 (run `40811156649`, `0de419c`, R10.5) passed.

## Public-address check in the read-only Greenhouse check (R10.5, 2026-10-29; local only, no external request)

- **Scope:** reliability rows R10.5 and R11.6 (`docs/reliability-test-plan.md`), the last open
  rows that need no owner decision. No request was made to Greenhouse or any real host.
- **Found:** the owner-run read-only check (`gh_readonly.Budget`, run by
  `scripts/greenhouse-readonly-check.sh`) fetched `boards-api.greenhouse.io` without
  `resolve_public_destination`, the one real server-side fetch left unchecked (the Freehire client
  has checked since S7; the in-app capture reads fixtures only and refuses a real post).
- **Now:** before every request to a base that is not a test fixture, the host must resolve to
  public addresses only; otherwise the check stops with a fixed message before anything is sent
  or counted. Fixture origins are never resolved. R11.6 (discovered-row deletion) was already
  done in S8 (D56); its row is updated.
- **Tests:** `tests/test_gh_readonly.py` 42 passed (5 new);
  `tests/test_readonly_cli_process.py`, `test_urlsafety.py`, `test_freehire_live_read.py` 27
  passed. Sabotage 4 cases, 4 caught, file restored and verified by MD5.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):** full backend 3404 passed, exit
  0, 36 min 25 s; `ruff check`, `ruff format --check`: exit 0. No frontend change.
- **CI for the previous change:** CI #112 (run `40806647437`, `32b2948`, C15-C18 and L1-L3)
  passed: backend, frontend, docker-smoke and execution-compose.

## Tailored resumes and cover letters (L2, L3, 2026-10-29; local only, no provider)

- **Scope:** plan steps L2 and L3, decision D73. **Done in code; nothing is generated yet**:
  generation runs only through the drafting provider, and none is configured (503 "not
  configured"). L4, a real provider, needs the owner's decisions (server-side credentials, a cost
  budget, a consent screen showing what leaves NoEfforts) and is not started.
- **Now:** a tailored resume or a cover letter is written from approved facts and the job's
  quoted text, checked like every draft, stored as a DOCX for one application (migration
  `60e18e9115c8`), shown with its cited facts and, for a resume, the lines changed from its
  base; usable only once accepted, for that application, while its facts are unchanged.
- **Found by a test and fixed:** when a chosen tailored resume stopped being usable, the
  package fell back to the user's only uploaded resume, so a document the user had not chosen
  would have been sent; an unusable choice is now a checkpoint that says why.
- **Tests:** `tests/test_generated_documents.py` 12 passed; `generated.spec.ts`. Sabotage 9
  cases, 8 caught at first (accepting a stale document was not tested; added, then 9 caught).

## Facts proposed from a resume (L1, 2026-10-29; local only, no provider)

- **Scope:** plan step L1, decision D72. New dependency `pypdf` (locked at 6.21.4).
- **Now:** text from a PDF (first 10 pages), DOCX or TXT resume; work entries, education and
  licences it states in a recognisable layout are proposed into the profile, each used by
  nothing until approved there; nothing inferred (dates kept as written, completion unknown, an
  expiry only from a full date); legal-status and sensitive lines skipped and counted. The
  profile page shows proposals with Approve, and gains the Licences and certifications card.
- **Tests:** `tests/test_resume_facts.py` 13 passed (synthetic PDF, DOCX and TXT built in the
  test); `documents.spec.ts` "a resume's facts are proposed". Sabotage 9 cases, 9 caught (one
  rerun after its first edit was a syntax error, which proves nothing).

## SCHEMA_VERSION 3 (C18, 2026-10-29; local only, no external request)

- **Announced: every approval given before this change is invalidated.** `SCHEMA_VERSION` is
  3; every package is rebuilt at its next load with a new hash and needs approval again. Only
  synthetic test data exists. Decision D71.
- **Now:** preference facts (relocation, salary) are hashed by their value; each package
  document records its origin and, for a generated one, its base, grounding and acceptance
  (migration `c14a371a79e8`); a file field's `accept` attribute is enforced (a TXT resume in a
  ".pdf,.docx" field is a checkpoint); an implicit resume is explained as proposed; a
  generated document nobody accepted is never used; an answer awaiting consent is never written
  into a package version (the review page reads it from the live answer).
- **Changed tests:** `test_package_contract.py` records shape 3 beside shape 2 (unchanged);
  `test_disclosure_ledger.py` reads the proposed saved answer from the review controls, since
  the content no longer holds it; the C3-C5 pinned salary control records its reference by
  value (`C18_DELTA`; the answer sent is unchanged).
- **Tests:** `tests/test_schema_v3.py` 16 passed. Sabotage 9 cases, 9 caught.

## Deleting documents (C17, 2026-10-29; local only)

- **Now:** a version, or every version, of a document is deleted with its file; refused while a
  live approval or a running attempt needs it (checked under the application locks, with a race
  test); an application's choice of it is removed. Retention rows updated. Decision D70.
- **Tests:** `tests/test_document_deletion.py` 8 passed; `documents.spec.ts` (the delete test).
  Sabotage 8 cases, 8 caught. Found while writing the browser test: the confirmation counted
  versions by the latest version number, wrong once a version is deleted; it no longer counts.

## Credentials as grounded facts (C16, 2026-10-29; local only, no provider)

- **Now:** approved, unexpired credentials ground a draft; a draft names a licence or
  certification only by citing one; licence and certification wording is never saved for
  reuse (48 rows of the wording table now `credential`; four witness rows added so each other
  family's use is still proven). Decision D69.
- **Changed tests:** `test_bank_scope_api.py::test_saving_and_listing_never_fail_on_unusual_text`
  used a certifications question as its reusable example; it now uses a programming-languages
  question (its point, unusual characters, is unchanged). A first version of the credential
  family also caught "accreditation", which is about institutions; it was removed.
- **Older tests changed, found by the first full run below:** five tests used a licence as a
  reusable example. The C3-C5 cardiac control now carries a C16 delta beside C6's (checked by
  the same only-narrows test); the C6 driver's licence and CPR controls are now C16 controls
  that are never reused; the resolver's bound-to-its-question example and two legacy-corpus
  controls (R8.11) are reworded to experience questions, keeping what they test.
- **Tests:** `tests/test_credentials.py` 6 passed. Sabotage 8 cases, 8 caught.

## Drafting hardened before any provider (C15, 2026-10-29; local only, no provider)

- **Now:** numbers only from the facts a draft cites; legal-status and sensitive mentions
  refused; one prompt shape with employer text quoted as untrusted data (R11.9); accepting
  compares the cited facts and the whole request, re-checks the question, and answers with
  reason codes; the user can reject a draft, which erases its text (migration
  `d1e3ab560050`); an accepted draft asked for again is said to be accepted. Decision D68.
- **Changed test:** the test double in `test_preparation.py` now cites every fact it was given.
- **Tests:** `tests/test_drafting.py` 27 passed; `drafts.spec.ts`. Sabotage 17 cases, 17 caught
  (the order test rewritten so a wrong order is always caught).

- **Tests run locally for C15-C18 and L1-L3 (cloud sandbox, PostgreSQL 16, Redis 7):**
  - full backend for C15-C18: 3366 passed, 7 failed, exit 1, 33 min 26 s. All seven were older
    tests holding a licence as a reusable example (C16) or the pinned salary reference (C18),
    changed as described in those entries; those two files then 731 passed;
  - full backend for C15-C18 and L1-L3 together: 3399 passed, exit 0, 34 min 56 s;
  - full Playwright: 68 passed, 2 skipped, exit 0, 7.6 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** CI #111 (run `40796945758`, `3151231`, S5-S6) passed.

## Freehire contract hardening (S6, 2026-10-29; fixture only, no Freehire request)

- **Scope:** plan step S6, decision D67; evidence: `docs/evidence-matrix.md` ("Freehire contract
  hardening"). R9.2, R9.4-R9.7. No live read, live-status, pilot-gate or package-shape change.
- **Now:** the record fingerprint reads only the documented fields NoEfforts uses, so
  `reality`, counters and enrichment metadata never count as a change (fixture mode
  `fh_reality_tick`); a `Retry-After` in seconds holds back that user's next import or
  refresh (429, "Nothing was sent.") before any request and before a live run approval is
  used (`discovery_backoffs`, migration `f150c66c69e3`); referral codes are dropped for
  deduplication; Discover has "Refresh from source" on each listing. Manual imports stay inside
  the request (D67 says why).
- **One-time effect:** a record stored before S6 counts once as changed on its next read (test
  data only).
- **Tests:** 10 new in `tests/test_freehire_discovery.py` and `tests/test_freehire_live_read.py`,
  1 migration test; the Freehire files 73 passed; Playwright "a listing refreshes from its
  source" 2 passed (desktop and mobile). Sabotage 8 cases, 7 caught at first: a 429 without
  `Retry-After` was not tested; added, then 8 caught. A container restart interrupted the
  sabotage run once and left one change in place; it was found and restored before anything
  else ran.

## Version diff (C14, 2026-10-28; local only)

- **Scope:** plan step C14, decision D66. No package-shape change (`SCHEMA_VERSION` 2).
- **Now:** `GET /applications/{id}/package/diff` compares two stored versions in the review
  page's words; "What changed in vN" on each history row and "What changed since you approved
  vN" on an invalidated approval. It never builds, approves or records anything.
- **Tests:** `tests/test_version_diff.py` 7 passed; `review-edit.spec.ts` "after an edit, the
  page shows what changed" 2 passed. Sabotage 6 cases, 5 caught at first ("the diff builds the
  current version" was missed); a test for a pending version was added, then 6 caught.

## Approval reasons and revoking (C13, 2026-10-28; local only)

- **Scope:** plan step C13, decision D65; `docs/approval-reasons.md`. No package-shape change.
- **Now:** nine fixed reason codes for every refusal to approve, queue or revoke; revoking
  cancels an attempt no worker has taken (the application waits for approval again), leaves one
  a worker holds to the gates, is refused after the send gate (`revoke_in_flight`), and is
  audited with what it did.
- **Changed test:** `test_execution_failures.py::test_revocation_before_claim` now expects the
  attempt cancelled by the revocation itself; it still asserts nothing was disclosed or
  accepted.
- **Tests:** `tests/test_approval_reasons.py` 9 passed, two new races in
  `tests/test_lock_order.py`; `approval-revoke.spec.ts` 4 passed (desktop and mobile).
  Sabotage 6 cases, 6 caught.

## Review page: change, clear, optional answers, cover letter, destination (C12, 2026-10-28; local only)

- **Scope:** plan step C12, decision D64. The controls sit outside the package content
  (no hash or `SCHEMA_VERSION` change).
- **Now:** where the resolver allows your input you can change or clear an answer and answer
  an optional question; a protected fact links to the profile; a cover letter can be chosen or
  left out; "Where this goes" names the address and whether it is a fixture or the employer's
  own site. Clearing and document changes are audited by reference.
- **Tests:** `tests/test_review_controls.py` 6 passed; `review-edit.spec.ts` 6 passed
  (desktop and mobile; the ledger holds the changed values). Sabotage 7 cases, 6 caught: the
  acknowledgment rule was redundant (an acknowledgment never allows input) and was removed;
  then 6 of 6.

## Salary units (C9, 2026-10-28; local only)

- **Scope:** plan step C9, decision D63; `docs/answer-policy.md` row 3. The fact-reference
  `version` key change is [shape] and waits for C18.
- **Now:** a salary is sent only in the currency and period the question allows (currency by
  code, sign or help text; period); a bare number only when both are stated in your
  Preferences and match; anything else is your answer for this application.
- **Tests:** 26 new resolver tests (17 fail on the previous code). A sweep of 805 synthetic
  forms in 32 contexts: 5,476 values withdrawn and nothing new sent except your own typed
  answers; 1,244 earlier values carried no currency or said "per None". Sabotage 8 cases,
  8 caught.

## Fixture variants and admission scenarios (S5, 2026-10-28; fixtures only, no external request)

- **Scope:** plan step S5, decision D62. R2.7, R2.9, R2.10, R4.9b, R6.4, R6.5, R7.4, R11.8. No
  admission stage, live-status or pilot-gate change; the challenge stop is not narrowed.
- **Now:** fixture modes for the legacy notes' page traps (confirmation words in the page,
  code boxes, a challenge after the final click, an unticked group, cookie and consent
  banners, two steps, an unlisted option, an autofill overwrite, a receipt for another
  posting); each adapter stops on or handles them, and every provider's confirmation is bound
  to its own attempt. Three capability scenarios and the multi-step trait scenario in
  admission.
- **Tests:** 8 new Greenhouse adapter tests, 5 DOM tests, one each in the execution-failure
  and API-provider files, 6 new scenario entries. Sabotage 15 cases, 15 caught.

- **Tests run locally for S5, C9, C12, C13, C14 and S6 together (cloud sandbox, PostgreSQL 16,
  Redis 7):**
  - a first full backend run for S5 and C9 alone was stopped by a container restart at 81 %
    with no failure so far; it was not repeated on its own;
  - full backend (all six): 3310 passed, 1 failed, exit 1, 31 min 22 s. The failure was
    `test_support_wording.py::test_the_api_serves_the_labels`, which pins the labels the review
    page is served and did not yet list C12's `destination`; the expected labels now include it
    (and check that a fixture destination is labelled as one); that file then 8 passed;
  - full Playwright, first run: 52 passed, 4 failed, 4 did not run, 2 skipped, exit 1, 8.0 min.
    Two causes, both in tests: `phase-b.spec.ts` looked up the "Profile" link by a name that
    C12's "Change it in your profile" links now also contain (now matched exactly), and the new
    `review-edit.spec.ts` asserted that First Name offers no change, which was wrong: the
    resolver lets you give a non-protected fact differently for one application; the rule meant
    is that a protected fact (work authorization) is changed in the profile, which the test now
    checks. Those two files then 8 passed (desktop and mobile);
  - full Playwright again: 60 passed, 2 skipped, exit 0, 7.4 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** CI #110 (run `40785089351`, `38079e6`, C8) passed.

## The disclose path, counted by the receiver (C8, 2026-10-28; local only, no external request)

- **Scope:** plan step C8, decision D61; evidence: `docs/evidence-matrix.md` ("The disclose
  path"). Closes R3.4. No support state, real employer destination, pilot-gate, execution or
  package-shape change (`SCHEMA_VERSION` 2).
- **Now:** "Don't disclose" on a required select, radio or multi-choice sensitive question
  selects the form's one decline option (exact wording from a fixed list), shown with its
  reason and never saved; no such option, two, a looser wording or a text question stay a
  checkpoint; an optional question is still left blank. One bank policy for the
  equal-opportunity topics: a saved answer is proposed and sent only after "Include this
  answer" on that form. Receiver mode `required_eeo`.
- **Also in this commit (S3 follow-up):** the possible-duplicate wording and the test harness
  titles (see the S3 entry).
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - with the mapping removed (the previous behaviour), 7 of the 19 first ledger and resolver
    tests failed;
  - after: the rehearsal, lock-order, sending, code-wait, execution-validation, job-signal and
    ledger files 158 passed, 1 failed after the harness fix (the saved-answer ledger test: its
    second application rightly waits for a choice the harness does not give; rewritten with
    its own helper); then `tests/test_disclosure_ledger.py` 20 passed. One first version of the
    required-without-a-choice test passed for the wrong reason (a refused consent call) and was
    rewritten to check the approval refusal itself;
  - Playwright `submission.spec.ts` "a sensitive answer is sent only as chosen" 2 passed
    (desktop and mobile; the ledger holds `w`, then `decline`);
  - sabotage: 5 cases (no mapping, the first of several options, optional questions too, a
    substring match, saved for reuse); 5 caught; checksum matched after each restore;
  - C7's 12 sabotage cases run again on this tree: 12 caught;
  - full backend (S3, C7 and C8 together): 3231 passed, exit 0, 46 min 36 s;
  - full Playwright (S3, C7 and C8 together): 48 passed, 2 skipped, exit 0, 6.5 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** CI #109 (`cad4e7d`, C10) passed (in the S3 entry).

## Answers and consents bound to their question (C7, 2026-10-28; local only, no external request)

- **Scope:** plan step C7, decision D60; evidence: `docs/evidence-matrix.md` ("Answers and
  consents bound to their question"). No support state, execution or package-shape change; no
  migration (the binding lives in `application_inputs.meta`).
- **Now:** each answer and consent stores its question's fingerprint (wording, help text,
  type, requirement, options, condition); a changed question asks again, with the reason; an
  "Include this answer" choice stores a keyed digest of the exact answer it covered (HMAC under
  the server's reference key, scoped to the user and the question; never the answer); rows
  saved before C7 are compared with the form version current when they were saved.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - `tests/test_input_binding.py` 7 passed;
  - sabotage: 12 cases (changed answers or consents still used, no fingerprint stored, no
    digest stored or checked, a missing digest accepted, legacy rows never compared or
    compared with the latest form, the digest not scoped to the user or to the question, the
    answer stored with the choice, no reason shown); 12 caught, run again on the C8 tree;
    checksums matched after each restore;
  - full backend, full Playwright and lint: one run for S3, C7 and C8 together (C8 entry).

## Job signals before approval (S3, 2026-10-28; local only, no external request)

- **Scope:** plan slice S3, decision D59; evidence: `docs/evidence-matrix.md` ("Job signals");
  reason codes in `docs/job-signals.md`. The owner's open "block or warn" decision taken as a
  default (approval waits for one click; preparation never blocked). No support state, real
  employer destination, pilot-gate or execution change; no package-shape change.
- **Now:** `backend/app/modules/jobs/signals.py` (source says closed, excluded or closed by you,
  possible duplicate); approval refused with `job_excluded`, `job_closed_by_you`,
  `job_source_closed` or `job_possible_duplicate`; `POST /api/jobs/{id}/still-open` and
  `/different-role` (audited `job.confirm_open`, `job.confirm_distinct`); signals on the job
  page, the review page (approval disabled) and Discover rows; migration `269ea4b8bc0c`
  (`jobs.open_confirmed_at`, `jobs.distinct_confirmed_at`, `discovered_jobs.stale_since`);
  Greenhouse embed URLs recognised (an old URL key still found); fixture mode `fh_repost`.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change: `tests/test_job_signals.py` could not be collected (no signals module);
  - after: `test_job_signals.py` 18 passed (one of my first cases compared two jobs that are
    one job without a URL, so it got distinct URLs); `test_migrations.py` 8 passed (the S8 test
    now pinned to its own revision); the audit, jobs, discovery, Freehire, reason-code,
    preparation and application files 172 passed;
  - migration: upgrade, `alembic check` (no difference), downgrade, upgrade;
  - sabotage: 15 cases (no approval check, each status, "still open" never or always
    answering, a listing absence as a closure, a repeated report resetting the time, location
    or title ignored, draft applications counted, "different role" covering later
    applications, another user's applications, embed URLs, the old key, a non-numeric token);
    15 caught; checksums matched after each restore;
  - Playwright `e2e/job-signals.spec.ts` 2 passed (desktop and mobile; one first failure was my
    text match catching two lines);
  - a full backend run of the S3 commit alone, in a second checkout, failed 33 of 3204. 13
    were real: tests that apply twice for one user to the receiver's forms, which share one
    synthetic employer and title, so the new check refused the second approval as a possible
    duplicate. Fixed in the C8 commit: the test harness gives each form or posting other than
    the default its own title (no assertion changed), and the reason now says "a role you
    already have an application for", since an application past draft need not have been
    submitted. The other 20 (container runner, browser isolation, four discovery tests, one
    reason-code test) pass in this checkout and in the full run below; they were specific to
    the second checkout;
  - full backend for S3, C7 and C8 together (one run, this tree): 3231 passed, exit 0,
    46 min 36 s;
  - full Playwright: S3 alone 46 passed, 2 skipped, exit 0, 6.1 min; S3, C7 and C8 together:
    in the C8 entry;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: in the C8 entry.
- **CI for the previous change:** **CI #109**
  ([40768810295](https://github.com/KevinD003/AutoApply/actions/runs/40768810295)) (`cad4e7d`,
  C10): passed (all four jobs).

## One link of a kind (C10, 2026-10-28; local only)

- **Scope:** plan step C10 (its fit check was done in S4, D54), decision D58; evidence:
  `docs/evidence-matrix.md` ("One link of a kind"). No support state, real employer
  destination, pilot-gate, execution or package-shape change.
- **Now:** link kinds are read from the host (a LinkedIn member profile, `/in/` or `/pub/` on
  `linkedin.com` or a subdomain; any other address is a website; other LinkedIn pages are
  neither); the same address spelled twice is one; exactly one link of the kind answers from
  the profile; several are never chosen between: the user gives the one for that question
  (typed, or a saved answer to that exact question), and the review page says why.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change: 9 of the 19 new link tests failed (the 10 that passed are unchanged
    behaviour: one link, a link of the other kind beside it);
  - after: the resolver, question-safety, bank-scope, preparation, approval and
    execution-validation files 1872 passed;
  - sweep against `f377276` (18,739 forms, 756 contexts including three new synthetic link
    profiles; 14,189,364 rows): nothing became bankable or draftable; the changed automatic
    answers are all corrections, each grouped by script: a LinkedIn company page replaced by
    the member profile beside it (4,536 rows), a look-alike host (`notlinkedin.com`) replaced
    by the real LinkedIn link (1,836), and for several links of one kind the user's saved
    answer to that exact question instead of the first link (1,377);
  - sabotage: 9 cases (the kind read from a substring, any LinkedIn page a profile, a LinkedIn
    page a website, the first of several sent, no merging of one address, `www.` kept, a
    subdomain not LinkedIn, no answer allowed, the links fact dropped); 9 caught; checksum
    matched after each restore;
  - full backend: 3185 passed, exit 0, 42 min 45 s;
  - full Playwright (with the new `e2e/review-reasons.spec.ts`): 44 passed, 2 skipped, exit 0,
    5.9 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **Outside NoEfforts, at the owner's request (2026-10-28):** searches for finance roles near
  Dallas through the Freehire connector the owner connected to this session (role titles and
  city names only, no profile data); the shortlist was given to the owner and is not stored in
  NoEfforts or in the repository.
- **CI for the previous change:** **CI #108**
  ([40755171960](https://github.com/KevinD003/AutoApply/actions/runs/40755171960)) (`f377276`,
  C11): passed (all four jobs).

## State, City and Country lists are never a dead end (C11, 2026-10-28; local only, no external request)

- **Scope:** plan step C11, decision D57; evidence: `docs/evidence-matrix.md` ("State, City and
  Country lists"). No support state, real employer destination, pilot-gate, execution or package
  shape change (no `SCHEMA_VERSION` bump).
- **Now:** a State (Province, Region) list gets the profile's state only for a US residence and a
  list naming all 50 states, by name or postal code, as its one exact option; any other State
  list, any City list (never picked from the profile, even when it offers your city) and a
  Country list without exactly one option for your country are your answer for this
  application: nothing sent until you answer, never saved for reuse, no saved answer in its
  place, tied to the profile fact so that changing it asks again. Typed fields are unchanged.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change: the new resolver tests failed (24 of 32 selected; the 8 that passed were
    unchanged behaviour: a missing state, typed text, and corpus rows);
  - after: `tests/test_resolver.py` 314 passed (the corpus now 250 rows, `user_input_allowed`
    checked by its loop); `tests/test_answers_that_do_not_fit.py` 2 passed; the preparation,
    question-safety, bank-scope, approval and execution-validation files 1562 passed;
  - narrowing sweep against `ba2a6d4` (18,613 forms, 2,214 of them new State/City/Country lists,
    times 432 fact, saved-answer, input and consent contexts; 8,053,776 rows): no row became
    bankable or draftable; the only new automatic answers (10,584) are State, Province, Region
    and State of residence lists naming every US state, mapped to Texas for the US-resident
    profile (each checked by script); 219,564 rows that were dead ends now accept the user's
    answer;
  - sabotage: 14 cases, each breaking one safeguard (a short list mapped, the US table outside
    the US, two hits, a near match, the dead ends back, several boxes, the facts not recorded,
    an unapproved or missing state, the city picked, a typed state); 13 caught at once; the
    several-boxes case was held by the S4 backstop, so its test now pins its own reason, and it
    is caught; the file checksum matched after each restore;
  - full backend: 3166 passed, exit 0, 41 min 31 s;
  - full Playwright (with the new `e2e/place-lists.spec.ts`): 42 passed, 2 skipped, exit 0,
    6.2 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** **CI #107**
  ([40694274168](https://github.com/KevinD003/AutoApply/actions/runs/40694274168)) (`ba2a6d4`,
  S8): passed (all four jobs).

## Watched Freehire searches and deleting discovered postings (S8, 2026-10-28; local only, no external request)

- **Scope:** decision D56, at the owner's request ("Get the new job posting within a minute");
  evidence: `docs/evidence-matrix.md` ("Watched Freehire searches"). NoEfforts made no request to
  Freehire (the sandbox refuses `freehire.me`). No support state, real employer destination,
  pilot-gate or execution change.
- **Now:** table `discovery_watches` (migration `29588d78e7e1`); `python -m
  app.modules.discovery.watch create|list|stop`; the worker task `noefforts.check_discovery_watches`
  every 10 s (no-op unless Freehire is enabled): owner, address, daily cap
  (`NOEFFORTS_FREEHIRE_DAILY_REQUEST_BUDGET`, 1,440), public-address check, at most two requests
  newest first, stop at a known posting; backoff, Retry-After, pause after ten failures; SKIP
  LOCKED; `GET /api/discovery/watches`, `POST .../{id}/stop`; `DELETE /api/discovery/jobs/{id}`
  (content erased, id kept; the job it created goes too unless something depends on it);
  Discover lists and stops watches, deletes postings and reloads every 20 s while a watch is
  active; five audit events; the fixture gained `fh_new_posting` and a configurable Retry-After.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change: `tests/test_freehire_watch.py` could not be collected (no watch model or
    command);
  - after: `test_freehire_watch.py` 16 passed (two added after the first sabotage plan found
    gaps: the newest-first request and a Retry-After longer than the interval); the wider
    discovery, audit, migration and doc set 330 passed with the audit inventory failing first
    (five undocumented events, now documented); `test_migrations.py` 7 passed (S8's bounds and
    downgrade added);
  - migration: upgrade, `alembic check` (no difference), downgrade, upgrade;
  - sabotage: 22 cases; 20 caught directly; 2 single-layer removals (the per-watch address
    check, the "stopped" filter in the due query) are covered by a second layer (the client's
    per-request address check, the re-check under the lock), and removing both layers is
    caught; one case first failed on my own syntax error and was re-run correctly;
  - Playwright `e2e/discovery.spec.ts` 4 passed (one first failure was my assertion matching the
    deletion notice);
  - full backend: 3125 passed, exit 0, 37 min 2 s;
  - full Playwright: 40 passed, 2 skipped, exit 0, 5.8 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** **CI #106**
  ([40613937853](https://github.com/KevinD003/AutoApply/actions/runs/40613937853)) (`35c1eda`,
  S7): passed (all four jobs).

## Owner-approved live Freehire read (S7, 2026-10-28; local only, no external request)

- **Scope:** plan slice S7 (`docs/implementation-plan.md`), decision D55, at the owner's request
  ("Go ahead, because I want to fetch the job postings from the freehire"); evidence:
  `docs/evidence-matrix.md` ("Owner-approved live Freehire read"). NoEfforts made no request to
  Freehire: the sandbox's network proxy refused `freehire.me` (`connect_rejected`), so the
  installer the owner pointed to could not be read and was not run. Separately, through the
  Freehire MCP connector the owner then connected, the assistant ran one search for the owner
  (20 of 5,679 results shown; nothing from the profile sent, nothing stored in NoEfforts). No support state,
  capability level, real employer destination, pilot-gate or execution change.
- **Now:** `NOEFFORTS_DISCOVERY_OWNER_EMAILS`; table `discovery_run_approvals` (migration
  `4bc9c342d34c`); `python -m app.modules.discovery.approve` records one approval (exact search,
  1-5 pages, at most 24 hours, retention statement); an import with base
  `https://freehire.me` checks the owner, then the approval, then the public address, marks the
  approval used and commits before the first request, and reads at most the approved pages;
  refresh and health check never read live; audit events `discovery.run_approval.create` and
  `.use`; `docs/discovery.md` "Live read" gives the steps.
- **Unchanged:** fixture imports, the existing discovery API for fixtures, `SCHEMA_VERSION`,
  `RESOLVER_VERSION`, every execution rule.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change: `tests/test_freehire_live_read.py` could not be collected (no approval
    model or command);
  - after: `test_freehire_live_read.py` 13 passed; with `test_audit_inventory.py`,
    `test_freehire_discovery.py`, `test_migrations.py`, `test_discovery.py`,
    `test_doc_references.py` 63 passed (one test file added since); first run of the wider set
    3 failed, each expected: the audit inventory lacked the two new events (documented), the
    old "live base refused" test expected 409 and the old message (now 403 with no owner or
    approval; it also now forbids a name lookup, which caught my own first ordering, where the
    address was looked up before the owner and approval checks), and the S2 migration test
    pinned the head revision (now pinned to S2's own revision);
  - migration: upgrade, `alembic check` (no difference), downgrade, upgrade;
  - sabotage: 10 cases (owner check, approval marked used, exact search, window, commit before
    the run, lookup order, address check, live flag, page limit, other live origin), 9 caught on
    the first run; the miss (any address once the flag is set, unreachable today) now has its
    own test, and is caught;
  - full backend: 3108 passed, exit 0, 30 min 42 s;
  - full Playwright: 38 passed, 2 skipped, exit 0, 5.7 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0.
- **CI for the previous change:** **CI #105**
  ([40605713542](https://github.com/KevinD003/AutoApply/actions/runs/40605713542)) (`a1b086c`,
  S4): passed (all four jobs).

## Legacy collision corpus and static guards (S4, 2026-10-27; local only, no external request)

- **Scope:** plan slice S4 (`docs/implementation-plan.md`), decision D54; evidence:
  `docs/evidence-matrix.md` ("Legacy collision corpus and static guards"). Tests first; the
  rows that failed were fixed only by turning the wrong resolution into a checkpoint. Nothing
  contacted; no support state, capability level, real destination, pilot-gate or execution
  change (`git diff --stat -- backend/app/modules/execution` is empty).
- **Found (each reproduced by a corpus row on the previous resolver first) and fixed:** someone
  else's name, email, phone or link filled from the profile; a City or Country field asking for
  a preference answered from residence; residence and nationality in other words reused from a
  saved answer, or ticked on agree on a single box; relocation answered "Yes" when negated or tied
  to a place, a time or a cost; "I cannot / am unable to work in ‹country›" ticked on agree;
  agree/decline options under a neutral label reused from a saved answer; "Yes" typed into a long
  answer or several boxes, a country as text into a multi-select, a link into a choice; a
  user's own answer to such a field tied to no fact, so it survived a change of that fact with
  the approval still valid; a saved label mapped onto one of two options that share it; a typed
  number shown with six significant digits.
- **Now:** `backend/tests/legacy_collisions.json` (244 rows) driven by
  `test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome`; the narrowing rules in
  `classify.py` (other-person sections and help, preference help, residence and nationality
  forms, the plain relocation form, a negated right to work, consent options) and `resolver.py`
  (`_does_not_fit`: a fact that does not fit is the user's answer for this application, never
  sent, never replaced by a saved answer, never saved; exact-one option for a saved label;
  `validate_value` refuses an empty or repeated set; the row keeps the fact it was about, so a
  change of it invalidates the approval, `tests/test_answers_that_do_not_fit.py`);
  `backend/tests/test_forbidden_capabilities.py` (R7.5, R11.4). Policy text: `docs/answer-policy.md` (rows 1a, 2a, 3, 4 and the S4 rules).
- **Kept, by the answer policy:** a box no profile fact records ("I am unable to travel") is
  still checked on the user's explicit agree (row 1, D49); the reliability plan's R8.10 wording
  that said otherwise is corrected. Narrowing it is a one-rule owner choice.
- **Unchanged:** `SCHEMA_VERSION` (2), `RESOLVER_VERSION`, no migration, no saved answer deleted
  or re-keyed, every retry rule, route reason codes. Packages with a narrowed row get a new
  version at their next rebuild, their approval is invalidated, and a queued attempt is refused at
  the gate before anything is disclosed (as in D49).
- **Design and review:** three mappers (the resolver, existing coverage, the legacy traps and the
  guard targets), three independent corpus designs run against the real resolver, a merge and a
  completeness critic (61 corrections); then three adversarial reviews of the code, each
  finding checked by a skeptic: round 1 (5 reviewers) 47 findings, 2 refuted; round 2 (3
  reviewers, on the round-1 fixes) 32 findings, 1 refuted; round 3 (3 reviewers: widening, slow
  paths, CI; after the sweep had passed) 6 findings, 0 refuted (one only partly: a docs note), the
  CI lens none. The rest were confirmed or partly confirmed and
  fixed (D54 lists them; the first other-person rule had kept those fields bankable, a widening;
  round 2 found a typed answer to a protected fact that did not fit tied to no fact; round 3
  found two widenings the sweep's generated forms did not reach, a third-person "would like"
  read as residence and a negated right to work that lost C5's sensitivity). A mutation
  check of the guard file (44 single-rule mutations, each run against every guard test) then
  killed 43 of the 44; the survivor (a list-form `addopts` not joined before the search) is
  equivalent, since the flag is still found in the list's text.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before any fix (the corpus and its driver on the unchanged code, alone on `noefforts_test`):
    164 rows, 47 failed, 117 passed; each failure was a wrong answer (listed in D54);
  - after the first fixes: `test_resolver.py` 190 passed; the preparation files (11, including
    `test_question_safety.py`, `test_bank_scope.py` and the API tests) 1704 passed, exit 0;
    `test_resolver.py`, `test_classify_vocabulary.py`, `test_forbidden_capabilities.py`,
    `test_repo_hygiene.py`, `test_doc_references.py` 379 passed, exit 0;
  - the first narrowing sweep (15,678 forms x 432 contexts, 6,785,856 rows, against the previous
    commit's resolver) showed 1,593 rows answered from a saved answer where the profile answered
    before: 945 were someone else's details (a widening, fixed by never saving them) and 648 an
    invalid answer replaced by a saved one (fixed by `_does_not_fit`);
  - after the round-1 review fixes, the 11 preparation files: 2002 passed, 4 failed, all my
    regression (three C3 citizenship statements and C6's "Do you have a passport?" row, caught by
    the new statement and passport rules), fixed by keeping C3's citizenship rule and requiring a
    country for a passport;
  - after the round-2 review fixes: `test_question_safety.py`, `test_bank_scope.py`,
    `test_classify_vocabulary.py`, `test_resolver.py`, `test_answers_that_do_not_fit.py`,
    `test_question_safety_api.py`, `test_bank_scope_api.py` 1904 passed, exit 0, 5 min 8 s; the
    narrowing sweep (16,335 forms x 432 contexts, 7,069,680 rows) 0 violations;
  - round 3's two widenings, reproduced first: the three new corpus rows failed on the round-2
    code (3 of 244) and the follow-up test failed there; on the final tree both pass; the
    reviewer's four probe sets (543 forms) give nothing newly answered automatically, bankable
    or draftable against the previous commit;
  - after the round-3 fixes, on the final application code: the same seven files plus
    `test_forbidden_capabilities.py` 2048 passed, exit 0, 6 min 43 s;
  - corpus on the previous resolver: 244 rows, 104 failed; on the final tree: 0 failed; every
    control row passes on both;
  - narrowing sweep on the final application code (against the previous commit's resolver):
    16,359 forms x 432 contexts, 7,080,048 rows, 0 violations (nothing newly answered
    automatically, bankable or draftable); the two fixture forms unchanged;
  - full backend on the final tree: 3094 passed, exit 0, 44 min 25 s (a first run was stopped
    by the sandbox's 30-minute background limit before reporting, so it counts as not run);
  - full Playwright: 38 passed, 2 skipped, exit 0, 6.6 min;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: all exit 0;
  - sabotage checks: 47 cases on the round-2 code, 46 caught; the one missed (the refusal for a
    fact that does not fit no longer saying why) showed the API test checked only "never saved
    for reuse", so it now checks each refusal's reason, and the case is caught; on the final code
    50 cases (three more for the round-3 fixes: third-person "would like" not read, the negated
    right-to-work rule before the C5 signals, a long place list read part by part), 50 caught,
    every file restored (116 checksums compared).
- **CI for the previous change:** **CI #104**
  ([40532442772](https://github.com/KevinD003/AutoApply/actions/runs/40532442772)) (`9f4ffa3`,
  S2): passed (all four jobs).

## Outcome integrity and funnel (S2, 2026-10-27; local only, no external request)

- **Scope:** plan slice S2 (`docs/implementation-plan.md`), decision D53; evidence:
  `docs/evidence-matrix.md` ("Outcome integrity and funnel"). The owner's two choices use the
  safe defaults (a user's confirmation stays, with what they checked; an outcome before any known
  submission is refused), each a code switch. Nothing contacted; no support state, capability
  level, real destination, pilot-gate or execution change (`git diff --stat --
  backend/app/modules/execution` is empty).
- **Found (each reproduced by a test first) and fixed:** a user confirmed a submission with no
  evidence and it looked like a receipt; reconcile evidence of about 970 characters or more
  returned 500, and blanks passed as evidence; outcomes were accepted on drafts, with no date,
  source, assessment value or audit row; a PATCH racing the worker's receipt returned 500; the
  review page called every confirmation a receipt; `/applications/funnel` was taken as an id.
- **Now:** event sources (`receipt`, `user_claimed`, `user_reported`) set by the server;
  `Outcome.assessment_received`; dated outcomes with a private note and the audit row
  `application.outcome {to, source}`; a refusal code set documented in `docs/architecture.md`;
  insert-only events enforced by a trigger and two checks (migration `e3a91c5d7b20`, no row
  rewritten); the per-user funnel with denominators and no rate; tracker labels that say what
  each submission rests on, a funnel card and an outcome form.
- **Unchanged:** `SCHEMA_VERSION` (2), `RESOLVER_VERSION`, package content (no hash changes, no
  approval invalidated), every retry rule, D15, D50, route reason codes.
- **Design and review:** three independent designs (minimal state, integrity first, user first),
  a judge and a completeness critic (13 corrections applied; the first judge and critic were
  stopped by a usage limit and a container restart, and resumed from the cached designs); then
  an adversarial review of the code (4 reviewers, a skeptic each): 8 findings confirmed (one
  reported twice) and fixed, 7 refuted. Fixed: a NULL target let a source pass the database
  check; pydantic's strip and Python's strip measured evidence differently (a 500 on
  `/reconcile`), and a NUL in user text was a 500; an outcome recorded before S2 dropped out of
  the funnel when the next one was recorded; the outcome form sent a hidden date; the Withdrawn
  warning named a Cancel button the card does not have; the reconcile panel kept text across
  applications; the retention table lacked the new notes.
- **Tests run locally (cloud sandbox, PostgreSQL 16, Redis 7):**
  - before the change (the new and updated tests on the unchanged code, alone on
    `noefforts_test`): 38 failed, 6 passed (the 6 are earlier tests in the same files); each
    failure was the one targeted (no `source` key, 200 without evidence, 500 from
    `StaleDataError`, 422 for `/funnel`, no migration);
  - after the change, first run of the S2 files: 42 passed, 7 failed, all from three test
    defects (jobs with the same title are one job, so a "second" application was the first; an
    attempt state is a plain string; the refusal-code scan matched rehearsal's own `refusal()`);
    fixed, the two files re-run: 26 passed;
  - full backend before the review fixes: 2652 passed, exit 0, 32 min 47 s;
  - after the review fixes: the S2 files 81 passed;
  - full backend after the review fixes: 2651 passed, 3 failed, exit 1. My review fix to
    `/reconcile` (a try around the two moves) had left the D15 approval retirement after a
    `raise`, unreachable: after "not received" the approval that sent the submission stayed
    live and re-queueing returned 200 instead of 409. Caught by
    `test_execution_failures.py::test_reconciling_an_unknown_outcome_never_sends_again`
    (the three `not_received` cases); fixed (the retirement runs again for "not received"),
    then those files and the S2 files: 77 passed;
  - full backend on the final tree: 2654 passed, exit 0, 34 min 17 s;
  - full Playwright: after the review fixes 38 passed, 2 skipped (the desktop-only log checks
    on mobile), exit 0, 6.0 min; on the final tree 38 passed, 2 skipped, exit 0, 5.6 min; the new
    `tracker-outcomes.spec.ts` runs on desktop and mobile;
  - `ruff check`, `ruff format --check`, `npx tsc --noEmit`, `npm run lint`: clean, each exit 0;
  - sabotage checks: 36, each caught by the test aimed at it (among them: no evidence check, a
    system actor confirming, a receipt for any actor, receipts ignored, the refusal or the lock
    removed, the lock order reversed, extra client keys, a date in the audit row, the
    migration's value, guard or trigger removed, a NULL target, evidence back in the reason,
    pydantic's strip, NUL accepted, the funnel's history, wait, scope or route order broken, an
    undocumented message, the owner switch read at import, the model and migration checks
    differing); every source compared identical to its backup afterwards. After the `/reconcile`
    fix, case 23 again and a 37th case (the D15 retirement skipped after "not received") were run:
    both caught. `git diff --stat -- backend/app/modules/execution` is empty.
- **CI for the previous changes:** **CI #102**
  ([40444320612](https://github.com/KevinD003/AutoApply/actions/runs/40444320612)) (`b6e4cf4`,
  C6) and **CI #103** ([40448472163](https://github.com/KevinD003/AutoApply/actions/runs/40448472163))
  (`532ae0a`, the review documents): both passed (all four jobs).

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
| Employment, education, credentials | complete (credentials card on the profile page since C16, D69) |
| Preferences | complete |
| Manual jobs, CSV/XLSX import/export, duplicates, exclusions | complete |
| Match explanations | partial (preference checks, no scoring) |
| Documents: upload, immutable versions, protected download | complete (no preview) |
| Tracker with durable states, timeline, reconciliation | complete for manual tracking |
| Docker Compose | Smoke-tested in GitHub CI; not yet verified on the user's Mac. Execution inside Compose runs in the separate browser-runner container, against the synthetic receiver only (CI job `execution-compose`) |
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
| Acknowledgments never auto-checked; sensitive answers need consent | partial: never auto-checked and consent required; a statement of a profile fact checked only with a true approved fact (C3); sensitive detection covers more topics and the help text, options, section and follow-ups (C5); answers and consents apply only to the question as shown, and "include this answer" only to the answer shown (C7, D60); the disclose path has no end-to-end ledger test yet (C8) | `test_question_safety.py`, `test_question_safety_api.py`, resolver + API tests |
| Missing facts park the application; profile fix resolves | complete | `test_missing_fact_parks_application_and_profile_fix_resolves` |
| Immutable package versions; approval bound to content hash | complete | `test_package_versions_are_immutable` |
| Invalidation on fact, document, answer, consent, destination change; unrelated edits keep approval | complete | `test_protected_fact_change_invalidates_approval`, `test_other_material_changes_invalidate_approval` (4 cases), `test_unrelated_fact_change_keeps_approval` |
| Queueing requires live approval | complete | API tests |
| Review screen | complete | Playwright `phase-b.spec.ts` |
| Long-form drafting interface with grounding validation | complete in code, **off by default**: validation hardened (C15, C16), one provider (Claude, L4, D74) used only for an owner account after consent to the exact text and within a daily budget; no key configured and no request made, so drafting shows as unavailable | `test_drafting.py`, `test_drafting_provider.py` |
| Tenant isolation for forms, packages, answers, consents, documents, answer bank, revoke, document selection, draft acceptance | complete | `test_tenant_isolation_for_preparation`, `test_tenant_isolation_for_revoke_documents_drafts_and_the_bank` |
| Resume parsing into proposed facts | complete (L1, D72): PDF, DOCX, TXT; proposed records approved one by one; no LLM | `test_resume_facts.py` |
| Only resolved answers are sent; stale accepted drafts are checkpoints | complete (C2, D48) | `tests/test_sending.py` |
| Package content shape pinned to `SCHEMA_VERSION` | complete (C1) | `tests/test_package_contract.py` |
| Truthful resume tailoring | complete in code (L2, D73): only through the drafting provider (off), from approved facts, accepted before use, with a diff from the base | `test_generated_documents.py` |
| Cover letters | upload and choose on the review page (C12); generation complete in code through the drafting provider (L3, D73; off) | `test_generated_documents.py`, `review-edit.spec.ts` |
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
| LLM provider (Anthropic, Claude) | Python SDK reference read | no key configured; no request made | provider built, off by default (L4, D74) | stub client in tests only |
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
