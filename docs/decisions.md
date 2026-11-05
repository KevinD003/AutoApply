# Decisions

Short records of choices made, with the reason and how to reverse them.

## D1 — Stack: Next.js + FastAPI + PostgreSQL + Redis/Celery (2026-10-19)
Followed the brief's default because the repository was empty. Python 3.12 managed with `uv`;
Node 22 with npm. Reversible: modules are plain FastAPI routers.

## D2 — Facts and preferences in separate tables
Residence, authorization and sponsorship are facts; target locations and relocation are
preferences. Keeping them in different tables means no code path can answer "where do you live"
from a desired city. Tested in `test_profile.py`.

## D3 — Tri-state answers everywhere
`yes / no / unknown / not_applicable` instead of booleans, so a missing answer is never coerced
to "no".

## D4 — Per-user job rows, not a shared job catalogue
Jobs are stored per user with a per-user dedupe key. Simpler isolation and no cross-tenant
leakage. A shared catalogue can be added later for feeds such as Freehire.

## D5 — Cookie sessions with CSRF header, not JWT
Server-side sessions can be revoked instantly; the token is stored only as a hash. The frontend
proxies `/api` so cookies stay first-party.

## D6 — Tests use a real PostgreSQL database
Duplicate detection relies on `ON CONFLICT` and unique constraints; SQLite would not prove that.
Tests migrate a dedicated database with Alembic, so migrations are tested too.

## D7 — Freehire: optional discovery source only (not yet integrated)
Pinned `strelov1/freehire@ec6e65f7`, MIT. Its public API (`https://freehire.me/api/v1`) is live
and keyless for documented reads, "limited per address". No keyless rate figure is documented
(corrected 2026-10-21, D34: an earlier version of this entry called a 600 req/min/IP limit
"documented"; that figure was read in Freehire's source, not in its documentation). Its terms
forbid scraping beyond the documented API and bypassing rate limits, and limit keyless use to
personal, non-commercial use (D34). Plan: a discovery adapter that paces only from Freehire's
`X-RateLimit-*` headers and re-verifies postings at the source ATS.
Do **not** reuse its TLS-fingerprint spoofing or LinkedIn guest-API harvesting. Its ideas for
public form-schema endpoints and "unconfirmed ⇒ never resubmit" match our design; no code copied.
Not reachable from the current cloud sandbox (proxy 403), so integration must be tested locally.
Details: `docs/research/freehire.md`.

## D8 — Tsenta: optional, disabled by default; public docs only
Tsenta's developer documentation was readable in an external reviewer's environment (reported:
bearer keys, server-side API, status reporting) but was not served to this environment's fetcher
(redirect to the product intro; `/api-reference/*` → docs sign-in). Accessibility is
environment-specific. No
Tsenta account, credential, code or test exists. Its terms (eff. 2025-09-23, §3(c)) prohibit
automated access "in ways not intended" and scraping, so the evidence matrix uses public pages
only. A Tsenta execution provider may be added later behind the provider interface,
**disabled by default**, only after its documented contract, approval semantics and confirmation
evidence are verified, and never with spending, account creation or real submissions without
explicit approval. Details: `docs/research/tsenta.md`.

## D9 — REA: optional development aid
`rea-agents@6.7.0` (MIT, `morluto/rea@b4938ae`) runs headless with no credentials. Usable for
static analysis of public JS or our own HAR captures. Not a dependency of the product and not
used against logged-in competitor surfaces. Details: `docs/research/rea.md`.

## D10 — Gmail: manual code entry first; Gmail OAuth personal/testing only at first
Every Gmail scope that can read mail (including `gmail.metadata`) is restricted. Personal-use and
testing projects are exempt from verification (testing: ≤100 users, 7-day tokens). Public
server-side access needs restricted-scope verification plus an annual CASA assessment, and
reading verification codes for job applications is not an explicitly listed approved Gmail use
case. That absence neither prohibits nor approves it: classification and approval are unconfirmed. Details: `docs/research/gmail-oauth.md`.

## D11 — Execution adapters before any "universal agent"
Order per the brief: documented API with valid credentials → tested deterministic browser
adapter → optional managed provider → manual handoff. Greenhouse and Lever public *submit*
endpoints need the employer's API key, so the first real adapter will be a browser adapter.

## D12 — Deterministic resolution; LLM only for opt-in long-form drafts
Standard questions resolve from approved facts, deterministic option mapping and saved answers
bound to exact wording. Anything ambiguous becomes a user checkpoint. The resolver has no LLM
dependency at all, which is stronger than "avoid calls" and is covered by a spy-provider test.
See `docs/answer-policy.md`.

## D13 — Approval bound to a content hash of fact *values*
Package answers reference the specific fact values used rather than record version counters, so
editing an unrelated field (e.g. profile summary) does not invalidate an approval, while any
change to a used value, document, answer, consent or destination does.

## D14 — Protected facts are corrected in the profile, not per application
Work authorization, sponsorship and residence answers cannot be overridden on one application
when the profile already answers them. This keeps answers consistent across employers. Where the
question itself is ambiguous (e.g. "eligible in the country where this job is located"), the user
answers per application and that answer is never saved for reuse.

## D15 — Uncertain submissions leave quarantine only through reconciliation (enforced by I2, D47)
Removed the direct `submitted_unconfirmed → queued` transition. Reconciliation requires a
written statement of what was checked and explicit confirmation, and re-queueing then requires a
fresh approval. System actors may not re-queue `failed_retryable` until Phase C defines
provider-specific retry policies for failures known to have sent nothing.
- **Amended (I2):** "requires a fresh approval" was not enforced: after a "not received"
  reconciliation the approval that sent the application was still live, so queueing again sent
  it a second time with no new approval (reproduced: the receiver ledger counted two
  acceptances). The reconciliation now retires the application's live approvals in the same
  transaction (`reconciled_not_received`, audit `package.approval_retired`), under the
  application lock; queueing again is refused until the user approves again
  (`test_reconciling_an_unknown_outcome_never_sends_again`).
- **Amended (I2 review):** the same held for a submission whose verification code was never
  entered: the final click was made, the attempt ended `abandoned` and its approval stayed live,
  so the review page offered to submit again on it. That approval is now retired too
  (`verification_not_completed`; `test_a_submission_whose_code_was_never_entered_never_sends_again_on_its_approval`).
  An approval to submit sends once.
- **Amended (I2 review):** a slow worker may still record the employer's receipt after the
  sweeper gave up on the attempt. Reconciliation now locks the application's attempts first
  (D46 order) and refuses "not received" once a confirmation is recorded; a receipt arriving
  after a "not received" reconciliation confirms the application (a worker may move
  `failed_retryable` to `submitted_confirmed`; before, the transition was illegal and the
  receipt was lost); and an application with a recorded confirmation is never queued again,
  whatever its state (`test_a_late_receipt_after_a_not_received_reconciliation_still_counts_and_nothing_resends`,
  `test_not_received_is_refused_once_the_employers_receipt_was_recorded`,
  `test_an_application_with_a_recorded_receipt_is_never_queued_again`).

## D16 — Transactional outbox + claim CAS instead of trusting queue semantics
The attempt and its outbox row are written in the queue transaction. A relay publishes ids;
a crash between publish and marking dispatched yields a duplicate delivery, which the claim
compare-and-swap ignores. Celery's `acks_late` / `reject_on_worker_lost=False` only decide
whether Celery repeats a *task*; they never make an external submission idempotent.

## D17 — Two gates; the send gate is the linearization point
Gate 1 authorizes disclosure, gate 2 authorizes the click. Both run (since D46: under their
locks, reading at READ COMMITTED; before, in REPEATABLE READ) under the application row lock and recheck approval, expiry, package hash and freshly rebuilt
content. Revocation, cancellation or edits that commit before gate 2 stop the send; after
gate 2, cancellation is refused because data may already be in flight. (Amended by D43: each
gate also locks the approval row.)

## D18 — No automatic retry after disclosure or send
Crashes before disclosure are re-pended (max 2). After disclosure: `abandoned`, the user
decides. After the send gate: `unknown` → `submitted_unconfirmed` → reconciliation.

## D19 — Minimal evidence, no traces
Playwright tracing and screenshots are off. Evidence stores receipt ids and summaries only.

## D20 — Destination policy: fixtures only
Every real employer destination is refused at queue time until a live adapter has its own
tested capability entry. Fixture origins are ignored in production.

## D21 — Migration history
Phase A's downgrade was edited earlier to drop enum types. That migration was never deployed,
so editing it harmed nothing, but from now on fixes go into new migrations. Migration tests run
on a disposable `*_migration_test` database; the main test suite refuses any database not
named `*_test`.

## D22 — Browser isolation outside the browser
Chromium runs in its own network, PID and mount namespaces (plus a nested user namespace that
locks the hiding mounts); its only way out is a relay to an egress proxy that allows exactly
the destination host:port and refuses non-public addresses. Playwright interception, origin
allow-lists or ordinary Docker networking alone were not accepted as sufficient. The localhost
fixture exception exists only for fixture origins, which production ignores; production refuses
`browser_isolation != netns`. No user-facing switch exists.

## D23 — Non-idempotent requests are never fetched and fulfilled
`route.fetch` + `fulfill` sent a submit twice when the browser closed with the fetch pending
(Playwright resumed the paused original). POST/PUT/… now go out once, from the browser; their
redirect hops are checked by the egress proxy. GET/HEAD keep the fetch-based redirect check
and abort on any fetch error.

## D24 — Execution owns the application state while an attempt is held
While an attempt is claimed, sending or awaiting a code, preparation may not re-settle the
application and users may not transition it (409). The code wait reuses `needs_user_action`,
which preparation treats as rebuildable; the guard keeps the two meanings apart without a
schema change.

## D25 — First ATS adapter: Greenhouse-hosted forms, two views cross-checked
Greenhouse's public job post JSON documents each question's wording, description, required flag,
types and options; the rendered page gives the submit target and show-if conditions. A form is
captured only if both agree, and execution re-checks the page against the approved package.
Verified against a labelled local approximation only; real posts are neither read nor submitted.
Public read access is not treated as permission to submit.

## D26 — Conditional and unsupported fields without a package schema bump
`FormField.condition` and `FieldType.unsupported` are new. They enter field fingerprints and
package answers (`condition`, `unsupported_reason`) only when present, so the content and hash of
every existing package are unchanged and `SCHEMA_VERSION` stays 2. A condition that is not met
makes the question "not asked" (nothing entered or sent); an unsupported required control blocks
approval; neither is ever guessed.

## D27 — Id-only Greenhouse pages: map by evidence, refuse anything ambiguous
A real posting (read-only run #3) rendered controls with ids but no `name` attributes, and ARIA
comboboxes instead of native selects. When the original extractor finds no named fields, the
job post JSON is mapped to the page instead (`greenhouse_dom`). A field counts only if exactly
one control has its name as `id`, the element or role suits the type, and the accessible name
equals the label. Absent, ambiguous or mismatched fields refuse the form. Execution re-proves
every mapping, the combobox options and the submit path before disclosing anything.
Unobservable behaviour is never guessed:
- a question hidden at load has an unknown trigger (`Condition(key="unknown-trigger")`), so it
  is never filled, and a checkpoint if required;
- a text question rendered as a search picker is unsupported;
- multi-choice comboboxes are unsupported.
The package shape is unchanged: only a new `form_source` value and existing condition fields
are used, so `SCHEMA_VERSION` stays 2. That alone does not make approvals safe across adapter
changes; see D28. Fixture-only, with `real_destinations: false`.

## D28 — Approvals are bound to the execution method, not only to the content
- **Not enough on its own:** the package hash covers the destination (origin, submit URL and
  method, form id, version, fingerprint and source), the document digests and the answers. It
  does not cover *how* an adapter locates, fills, verifies and submits. A routing change or a
  change in an adapter's semantics would otherwise run an old approval with a new meaning.
- **What is recorded:** each approval stores `adapter` and `adapter_version`
  (`execution.policy.ADAPTER_VERSIONS`). The version embeds the extraction or mapping rules the
  adapter's live checks rely on.
- **Where it is checked:**
  - at queueing: a mismatch is refused, and that one approval is retired so the same content
    can be approved again under the method that would now run;
  - when the runner loads the attempt, before any adapter code touches a page;
  - inside both gates, under lock.
- **Approvals given before bindings existed:** they mean the route and versions the code had
  then (`LEGACY_VERSIONS`). They stay valid exactly while that is still what would run, so this
  change invalidates none of them. A later version bump retires only the approvals bound to
  that adapter. Migration `5d2e7a91c4b0` adds the two nullable columns.
- **Amended (I2):** an approval given while the route was a manual handoff was recorded with no
  adapter, which reads as an approval given before bindings existed: had the same package later
  routed to an adapter (for example, once its origin was a test fixture), it ran with that
  approval (reproduced). It now records `manual_handoff` (`policy.MANUAL_BINDING`), which never
  matches an adapter's binding: the approval is retired and nothing is sent
  (`test_an_approval_given_for_a_manual_handoff_never_runs_through_an_adapter`). Approvals stored
  with no adapter keep their meaning and expire as before.

## D29 — Widget inspection: open and close only, no data endpoint, GET is not harmless
- **Purpose:** observe how a page's dropdowns relate to its questions. Opening a widget is
  interaction, so it is a separate mode (`--inspect-widgets`) that needs its own approval.
  It is never part of B or B3.
- **Actions allowed:** one click to open and one Escape to close, on comboboxes present at
  load, within a fixed action budget. Nothing else is clicked, typed, focused, selected or
  uploaded.
- **Network:**
  - every data request type (xhr, fetch, eventsource, websocket, ping) is refused at every
    origin, GET and the page origin included;
  - a widget that needs a data endpoint is reported as such, and the endpoint is never
    approved automatically;
  - destinations and methods are otherwise exactly B3's.
- **Defence in depth:** form submission is cancelled in the page, non-GET is blocked in the
  network layer, file choosers are intercepted, and dialogs are dismissed.
- **Stops:** the first navigation attempt, address change, challenge, submission, non-GET,
  file chooser, dialog, value change or selection ends the inspection. It is reported and not
  retried. Structural and required changes are recorded, not acted on.
- **Output:** aliases and counts through the existing allowlist and guard. Option texts are
  compared inside the worker only.
- **Run #7 lesson:** the request filter now fails closed (any internal error aborts the request
  and stops the run). The CLI's script entry point must stay the module's last statement,
  because the tests import the module and cannot see definitions that script mode skips.
- **Outcome is explicit (after run #7):** the read-only CLI reports `outcome`:
  - `completed` (exit 0);
  - `policy_stop` (exit 7): an expected stop, so the evidence is partial and is not a
    compatibility result;
  - `internal_error` (exit 6): any unexpected error, a failed handler, or the filter-failure
    stop. It fails the check even when a sanitized summary was printed.
  An incomplete inspection is never `completed`. In script mode the process's stderr goes to
  a raw file in the out directory, so the log carries only the guarded summary. A
  fresh-process test runs the workflow's exact `python -m` entry point against the synthetic
  receiver (a test-only target, accepted only for listed fixture origins outside production).

## D30 — A widget inspection reports what it could tell apart; required evidence never lowers a requirement
- **Open state per widget:**
  - `click_failed`;
  - `not_opened`;
  - `undetermined`;
  - `opened_options_not_observable`;
  - `partially_observed`;
  - `observed_sufficiently`.
  It is decided from structural diagnostics sampled within the unchanged settle window. Only
  `observed_sufficiently` is compared with the job data. No state means "absent", and a
  short window is never proof of absence.
- **The detector must not be validated only against fixtures built on its own assumptions:**
  `gh2_widget_variants` is an independent model. Each variant is a fixture assumption.
- **Refused data requests** are reported as path shapes, built from generic words and
  placeholders, so their purpose can be judged without publishing identifiers. Access is
  never widened because some requests were refused.
- **Required:** the job data's requirement stands. The page's signals (HTML, ARIA, group ARIA,
  label marker, group label marker) are recorded separately and reviewed as `consistent`,
  `api_required_page_unmarked` or `page_required_api_optional`.
  - Execution is blocked only where it would be unsafe: a page-required field the package
    leaves empty, or an unreadable control.
  - An unmarked required field keeps its approved answer.
  - The adapter `greenhouse_dom` moved to version 2 for this. Approvals bound to version 1
    are retired at queueing (D28). Package content is unchanged, so `SCHEMA_VERSION` stays 2.

## D31 — Dropdowns are handled by explicit strategies with evidence, never by guessing
- **Approach:** a dropdown without a list in the page at load is handled only by a named
  strategy (`adapters/dropdowns.py`). Each strategy is one bounded action:
  - a click on the control;
  - ArrowDown;
  - a click on the single trigger beside it.
- **Trigger candidates** are found separately from the input: buttons and popup triggers in
  the largest container holding no other form control. More than one candidate is refused.
- **Opened** only with post-action evidence (the inspection probes, `classify_open`): a
  stable, complete list equal to the approved options. Verification happens before the
  disclosure gate, and nothing is selected then.
- **Selected** only by the exact approved label, plus the value where the option exposes
  one. Never the first, highlighted or default option. No Enter, no typing, no scrolling.
  Proven by readback.
- **Refused before disclosure:**
  - no strategy opened it;
  - the list is partial, changing, loading or virtualized;
  - options duplicated or different from the approved ones;
  - options loaded from the network during the action (a checkpoint until verified);
  - a failed attempt changed a value.
- **Unmatched dropdowns** (for example a phone-country selector) are never interpreted; the
  form is refused as having new fields. Location pickers and coordinates stay unsupported.
- **Status:** every strategy is fixture-only (`CAPABILITIES`). `real_destinations` stays
  false. The adapter moved to `greenhouse-dom-3`, so earlier approvals are retired at
  queueing (D28).


## D32 — One provider model for browser, API, discovery, observation and manual routes
- **Approach:** each provider (`app/modules/providers/registry.py`) declares:
  - its kind;
  - the operations it implements;
  - a support level per capability: `fixture`, `observed`, `live_fill` or `live_submit`.
- **Invariants,** enforced on import by `check_spec`:
  - no live level without real-page evidence;
  - nothing live while `real_destinations_enabled` is false;
  - discovery, observation and manual providers never fill, upload or submit;
  - only API providers claim API submission.
- **Routing** (`routing.decide`) is deterministic:
  - a real destination is a manual handoff;
  - the authorized API route needs the user's grant, configured credentials and declared
    support;
  - else the browser adapter;
  - else a manual handoff.
  - The chosen provider and its version are part of the approval binding (D28). So a grant, a
    revocation, a missing credential or a version change retires the approval, or stops the
    worker before disclosure. Nothing switches silently.
- **API route:** same attempt, gates and fencing as the browser. The idempotency key is the
  attempt id. Anything ambiguous after sending is `unknown`. Reconciliation is a read-only
  lookup that never resends and never changes the state by itself. Evidence holds a hash of
  the receipt, not the receipt.
- **Contract status:** the contract is NoEfforts' own, tested only against the receiver's fake
  API. No real ATS is claimed to offer it.
- **Discovery:**
  - finds jobs only;
  - source statements are tri-state source facts, never candidate facts;
  - incomplete records stay unlinked for manual import;
  - Freehire is a mock: "Potential future discovery provider; not yet connected or
    validated."
- **Why:**
  - adding a route (API, a new ATS, discovery) must not weaken the guarantees the browser
    route already has;
  - a fixture pass must never read as live support.
- **Status:** no provider has live support. C and D remain unapproved.

## D33 — Freehire is an optional, replaceable discovery provider; fixture-only until authorized
- **Approach:** a discovery interface:
  - `provider_capabilities`, `healthcheck`, `list_jobs(filters, cursor)`, `get_job`,
    `normalize_job`;
  - a Freehire client built to the documented public read API (research of 2026-10-19);
  - the feature flag `NOEFFORTS_DISCOVERY_PROVIDERS`, empty by default.
- **Base URL:** the client refuses any base URL that is not a fixture origin. No live call
  is made or possible without a reviewed code change.
- **Import:**
  - fetches every (bounded) page before writing, so failures change nothing;
  - filters only on what the source supplied ("not enough data" is never a match or an
    exclusion);
  - deduplicates by application URL, then job URL, then one conservative
    employer/title/location match;
  - **never modifies an existing tracker job**: changes at the source are shown, not applied;
  - never creates a job from a posting already closed at the source.
- **Sponsorship:** from provider enrichment, it is a tri-state source fact with basis
  "provider enrichment". It never touches the candidate's facts.
- **Why:**
  - discovery data is third-party and possibly machine-derived;
  - the user's own records and facts must not be overwritten or inferred from it;
  - a provider outage must never affect manual entry or tracking.
- **Status:** implemented locally. External API not configured and not tested; not
  production-ready. Details: `docs/discovery.md`.

## D34 — Freehire documentation review (2026-10-21): what changes before any live use
- **Evidence:** documentation and terms only (`docs/research/freehire.md`, review of
  2026-10-21). No API endpoint was called.
- **Terms ("Last updated: October 19, 2026"):**
  - **Without a plan**, the API is for personal and non-commercial use. Showing postings in a
    product or service offered to others, paid or not, needs an API plan.
  - **A plan** allows storing and showing postings. Each posting must link to its freehire.me
    page or carry "via freehire.me". No redistribution of the raw data. Stored data must be
    deleted within 30 days after the plan ends.
  - **Whether NoEfforts' use is "a tool you run for yourself" or "a service offered to
    others"** is the owner's decision. It is not inferred here.
- **Contract corrections against D7, D33 and `docs/discovery.md`:**
  - **Rate limits:** D7 called the 600/min keyless limit "documented", which was wrong. No
    keyless figure is documented (`GET /plans` reports it). The documented plan rates are
    1,200/min (API) and 6,000/min (Data).
  - **Work mode:** `work_mode` is a top-level job field, not `enrichment.work_mode`.
  - **`/status`:** it reports ingest-fleet health, not API availability.
  - **Undocumented fields:** `last_seen_at` and the `utm_source` suffix appear in no
    documentation.
- **Not applied yet** (no code change was in scope). Before any live call is proposed, the
  client and `docs/discovery.md` need:
  1. `work_mode` read from the top level;
  2. no reliance on `/status` for health, or relabel it as ingest health;
  3. pacing from `X-RateLimit-*` headers instead of an assumed figure;
  4. the attribution and retention rules above, if a plan is used;
  5. no use of undocumented fields as facts.
- **Applied 2026-10-21; personal prototype chosen by the owner:**
  - corrections 1, 2, 3 and 5;
  - a "via freehire.me" credit on every listing (no listing-page URL is documented, so it is
    text);
  - no raw payload kept.

  The integration stays off by default and limited to fixture origins. Item 4's retention
  (deletion within 30 days after a plan ends) is **not implemented** until there is a plan or
  written clarification from Freehire.
- **Status unchanged:** a live API call remains unapproved. A future live test needs its own
  approval with the exact query, page limit, time window and data-retention statement.
  Freehire stays a discovery source only, never an execution destination.
- **Re-checked 2026-10-26** (public pages, OpenAPI document and source at `ab47628c`;
  `docs/research/freehire.md`, "Re-check, 2026-10-26"; no API endpoint was called):
  - **Terms dated October 26, 2026.** The 30-day deletion after a plan ends is gone: "stop
    showing the postings in your product; you may keep what you stored for your own internal
    analysis". Item 4's retention therefore becomes **stop showing Freehire postings when a
    plan lapses**, still not implemented. Attribution, no resale and the keyless
    personal-use rule are unchanged.
  - **Rate limits:** the Jobs API and pricing pages now state 600 requests a minute per
    address without a key, and Freehire's code holds a pending strict mode (120/min and
    2,000/day) that an environment switch turns on. Pacing stays header-only; no figure is
    configured.
  - **Data quality, not yet handled:** for aggregator sources `url` is a tracking redirect
    rather than the employer's page; direct-apply jobs have an empty `url`; some sources append
    a referral code when configured (whether it is set in production is UNKNOWN), and not every
    form of it is dropped before deduplication; whole-record fingerprints would make nearly
    every refresh look "updated" (unmeasured). The `utm_source=freehire.me` tag on every
    non-empty `url` is already dropped with the other `utm_*` parameters before deduplication
    and ATS identification. Recorded in `docs/discovery.md` "Limitations".
  - **Owner question (not raised before):** Freehire sells auto-apply (Pro, $5/month: 3
    background applications a day, already on the pricing page on 2026-10-21; since 2026-10-26
    the page also lists an extension that fills applications). The 2026-10-19 notes already
    record its paid `POST /jobs/:slug/auto-apply`. Whether it still counts as a discovery
    provider under CLAUDE.md's rule against "automated access to competitor dashboards/APIs"
    needs an explicit owner statement before any live read. Not inferred.

## D35 — Route by ATS identity first; traits apart from capabilities; Workday planned only
- **ATS identity first:** routing identifies the job's ATS from known hostnames before choosing
  a route.
  - An ATS with only a planned adapter is a manual handoff that names the reason.
  - A form captured as one ATS for a job on another is refused.
  - So no job can reach another ATS's adapter by its form source alone.
- **Per job** (`route_for_job`, `GET /api/jobs/{id}/route`):
  - no captured form gives a manual handoff;
  - a required control NoEfforts cannot fill gives a **checkpoint** before any disclosure;
  - otherwise the existing order applies: authorized API (grant + credentials + support),
    then the browser adapter, then a manual handoff.
  - A job source never supplies a form.
- **Workflow traits** (login, manual verification, CAPTCHA possible, multi-step) describe what
  a workflow demands. They are recorded apart from capabilities: "yes"/"no" only with
  evidence, "expected" only for a planned specification, "unknown" otherwise.
- **Vocabulary and interface:** the routing vocabulary and the nine-operation interface are
  views over the existing capabilities and operations, never separate claims.
- **Workday:** registered as `planned` with no operations or capabilities. No Workday
  automation exists.
- **Status:** nothing became live. `real_destinations` is false everywhere; C and D remain
  unapproved.

## D36 — Route reason codes are a closed set; the route audit records changes only (2026-10-22)
- **Closed set:** `routing.REASONS` lists every reason a route decision or a destination
  refusal can carry; each code is a fixed identifier, safe to record. Every code but one is
  produced by a known, tested path (`tests/test_reason_codes.py`), and the table in
  `docs/provider-architecture.md` lists exactly these codes.
- **Named fallback:** `no_supported_provider` is the fail-closed default, never a path's own
  answer. It is what an unknown code is recorded as. A decision or refusal that would rely on
  it fails the tests, so a new path must name its own code.
- **Truthful explanations:** a discovery record without a tracker job says why: incomplete
  (`source_record_incomplete`) or closed at its source before it was linked
  (`source_posting_closed`).
- **Audit of changes, not views:** a `route.decision` event is recorded when the decision
  differs from the job's last recorded one, from the job page or the discovery view of a linked
  record. Before, every check recorded a row, so the audit trail mostly repeated itself. What
  is no longer recorded is when an unchanged route was shown again; the decision itself is
  already there. Two concurrent first checks may each record one.
- **Status:** no support state, routing order or live gate changed.

## D37 — Support wording is derived from evidence and served from one place (2026-10-22)
- **One source:** every user-visible support label (provider support states, routes and the
  evidence behind them, captured-form sources) lives in `providers/wording.py`. The API serves
  the labels; the pages write none of their own (checked against the frontend sources).
- **Derived, not declared:** a provider's support state follows from its stage and capability
  levels. A hand-written line cannot raise it.
- **No live label in advance:** a live level has no label, so a page cannot show one until it
  is added deliberately, with its evidence, tests and documentation. An API or browser route
  is never shown without the evidence behind it.
- **Wording is not content:** labels are served next to a package, never inside it, so a
  wording change never changes a package hash or invalidates an approval.
- **Status:** no support state changed. The wording on two pages that described the same form
  differently is now one label.

## D38 — A posting's question keys never appear in a URL path (2026-10-22)
- **Rule:** a path carries only internal ids (UUIDs) and NoEfforts' own names. A posting's
  question key is the employer's identifier, so it travels in the request body.
- **Why:** NoEfforts' own access logs already record route templates only, but any proxy
  placed in front of the app logs raw paths.
- **Change:** `PUT /api/applications/{app_id}/answers`, `POST …/answers/clear` (replacing
  `DELETE …/answers/{key}`, which no page used), `PUT …/consents` and `POST …/drafts`, each
  with `{"key": …}` in the body. The key-in-path routes were removed rather than kept beside
  them. `tests/test_api_paths.py` fails on any new path parameter that is not a UUID or one of
  NoEfforts' own names.

## D39 — Manual observations are fixed choices and advisory; pilot readiness is derived (2026-10-22)
- **Path A record:** the owner's optional manual dropdown check
  (`docs/manual-dropdown-checklist.md`) is stored only as its fixed answers, with the date and
  the owner as source, in `docs/evidence/path-a.json`. Wording, names, links and free text are
  refused, and refusals never echo the value given. The record ships as `pending`;
  NoEfforts never fills it in.
- **Advisory, not evidence of support:** the answers say which bounded strategy a fixture
  would have to prove next and which blockers stay. They never change a capability level,
  `real_destinations`, a route or an approval.
- **Pilot readiness:** the seven conditions of `docs/greenhouse-readiness-gap.md` are computed
  from evidence of their own kind:
  - registry levels, where reaching `observed` needs an approved read-only run;
  - `real_destinations`;
  - the gate's separate permissions, recorded nowhere yet.

  The documented status table is tested against the computation. Today none of the seven is
  met.

## D40 — Lever is a planned provider: identity, an honest route, and expectations only (2026-10-22)
- **Planned, like Workday (D35):** `lever` is registered with no operations or capabilities,
  and nothing was read from Lever to define it. Its identity comes from known hostnames only.
- **Route:** a Lever job is a manual handoff that says Lever is not supported yet
  (`planned_adapter_only`), before any other step. A form captured as another ATS cannot
  pull it into that ATS's adapter.
- **Traits are expectations, never observations.** CAPTCHA is expected; login, multiple steps
  and verification are "unknown" with the expectation noted as unverified. They are never
  "no", which would need evidence.
- **Docs held to the registry:** the routing-vocabulary table in
  `docs/provider-architecture.md` is tested column by column against the registry, so a
  planned provider can never be documented with more than it has.
- **A form-ATS mismatch** is now shown with an ATS that has no specification (Ashby), since
  Lever's own planned refusal comes first.

## D41 — A rehearsal is an approval to disclose only, used once (2026-10-22; stop amended by D44; prerequisite D45)
- **Permission C alone:** an approval has a scope.
  - `submit`, the default and what every earlier approval meant, permits filling and the
    final click.
  - `disclose_only` permits filling, uploads and the checks, never the click.

  The scope is fixed when the approval is given and is not package content, so no package
  hash changes.
- **Where it stops:** after readback and the re-check of the form after filling, before the
  send gate. The attempt ends `rehearsed`: nothing was submitted. It is never retried and
  never continues into a submit.
- **Used once:** the rehearsal retires its approval in the same transaction that ends the
  attempt. Submitting afterwards needs an approval to submit and a new attempt, which repeats
  every check. Rehearsing again needs a new approval to rehearse.
- **Two independent stops:** the runner stops at the rehearsal point, and the send gate (D17)
  refuses any approval whose scope is not `submit`. Each is tested with the other bypassed
  or removed.
- **Never switched silently:** approving with another scope while an approval is active is
  refused; the user revokes first.
- **Fixtures only:** no support state changes and no real destination is enabled. A
  rehearsal against a real page would still need the live-pilot gate's permissions.

## D42 — Upload evidence is a digest and a fixed acknowledgement, kept even when an upload fails (2026-10-22)
- **What is kept:** for each upload, the field, the digest of the approved document that was
  sent, and how the destination acknowledged it, as a fixed value.
  - A page: `attachment_shown`, `error_shown` or `none` (nothing shown in time).
  - The API route: `digest_matched` or `not_kept`.
- **What is never kept:** the page's own attachment id or wording. On a real page, that id
  would be the employer's storage reference.
- **A failed upload keeps its evidence.** When an upload is refused or never acknowledged,
  the attempt stops (`abandoned`, as before). The evidence of that upload, and of every
  upload made before it in the attempt, is recorded first, because that data may already
  have reached the employer. Before, it was dropped with the exception.
- **A rehearsal's result is shown as such:** an approval a rehearsal used up appears as
  "rehearsal finished", derived from its `rehearsed` attempt, not as an invalidation. The
  tracker shows the latest attempt.

## D43 — Each gate locks the approval row too (2026-10-22; the snapshot it patched replaced by D46)
- **Fixed:** a gate's REPEATABLE READ snapshot is taken at its first statement, the attempt
  lock, and the application lock comes after it. A revocation that committed while the gate
  waited for the application lock (revoking takes that lock too) was not in the snapshot. The
  gate then read the approval as still valid: the disclosure gate let filling start, and the
  send gate let the submit go ahead after the user had revoked.
- **Now:** after the application lock, each gate locks the attempt's approval row (`FOR
  SHARE`). If the row changed after the snapshot (a revocation, or a new package version that
  invalidated it), PostgreSQL refuses the lock with a serialization failure, and the gate
  refuses: "the approval changed while it was being checked". The attempt then stops as any
  refused gate does: before disclosure `failed_safe`, after it `abandoned`.
- **Test:** `tests/test_gate_snapshot_race.py` commits a revocation in a second session
  inside that window, deterministically, for both gates. It failed on the code before the
  fix (the gate did not refuse) and passes now.

## D44 — A rehearsal ends through a gate; readiness counts recorded evidence by class (2026-10-22; isolation amended by D46)
- **The stop is a gate.** A rehearsal ended `rehearsed` without any check: a revocation, a
  content change or a lost lease after the disclosure gate still let it end as a successful
  rehearsal (and wrote a `package.approval_retired` row for an approval already revoked). Now
  `service.finish_rehearsal` repeats every gate check in one REPEATABLE READ transaction,
  under the attempt, application and approval locks (D43): authority, the approval still live,
  the content and the execution method unchanged, the destination's class. It then checks the
  evidence rows (`execution/rehearsal.py` `evidence_facts`):
  - every approved document uploaded once with its digest and acknowledged;
  - the readback with no mismatch (on the API route, the draft);
  - the form checked again after filling (`recheck`; the API route reads its schema again);
  - nothing unresolved. Requests the egress controls blocked or denied are counted in the
    record, not disqualifying: a denial means the control held (the browser's own background
    requests are denied too).
- **Recorded in the same commit:** the rehearsal record (counts, route, adapter and version,
  destination class; no host, board, field or file), the `rehearsed` state and the approval
  used up. A refusal ends the attempt `abandoned`; an evidence refusal carries a fixed
  reason code on its event (`rehearsal_evidence_missing`, `rehearsal_evidence_inconsistent`),
  the other gate refusals their fixed message.
- **A record holds only while it is true:** not revoked, its attempt and class unchanged, its
  adapter version current, younger than `rehearsal_max_age_days` (30), and its evidence rows
  still present and in agreement. Deleting an application's evidence revokes its records.
  Any error while checking is a refusal (`rehearsal_check_unavailable`).
- **Destination class recorded at queueing:** `fixture` only for a configured fixture origin
  outside production, otherwise `real`. Each gate refuses an attempt whose destination is no
  longer the class it was queued as, so a recorded class can be trusted.
- **Readiness reads the caller's own records** (per user, counts only), each in the class it
  was recorded in. The five evidence classes are kept apart (`providers/evidence.py`, pinned
  in `docs/upload-and-submission-evidence.md`). `real_upload` needs real destinations enabled
  and a holding rehearsal record of class `real` with an upload; `real_submission` needs real
  destinations and a confirmed real attempt with an attempt-bound confirmation. Fixture
  evidence meets nothing. With real destinations disabled, nothing recorded can meet either.

## D45 — A recorded rehearsal before the first submission through each path (2026-10-22; isolation amended by D46)
- **Rule (CTO decision):** a successful, recorded, disclosure-only rehearsal is required before
  the first real submission through a new employer/provider execution path. Built and tested
  on the local fixtures only (`docs/rehearsal-prerequisite.md`); nothing is enabled for a real
  employer, and real destinations are still refused first.
- **Path:** user, adapter, normalised origin and board (the posting URL's board token, or the
  fixture form's slug), stored only as a keyed reference (HMAC under the audit reference key,
  its own domain label). No path, no rehearsal can count (`rehearsal_path_unknown`).
- **"First":** the newest result on the path decides, by when it finished: a finished
  rehearsal, or an establishing submission. Met by a valid rehearsal record (D44) named by the
  approval to submit. Established by a confirmed submission, by the same adapter version and
  class, whose own send gate found the prerequisite held, with its attempt-bound receipt
  retained. A newer failed or cancelled rehearsal, or an adapter version change, needs a new
  rehearsal. A withdrawal or deletion of the evidence relied on makes it no longer count, and
  the next newest result decides. A rehearsal record counts for 30 days
  (`rehearsal_max_age_days`). An established path has no age limit of its own: it lasts while
  an establishing submission's receipt is retained (`evidence_retention_days`, 365), and each
  established submission renews it. Chosen over "a rehearsal before every submission": each
  rehearsal on a real page is another real disclosure, and every submission still repeats
  every check of its own. Making it stricter is one branch and its tests.
- **Five layers:** approve, enqueue, claim, the disclosure gate and the send gate, each tested
  with the others bypassed. In the gates what is relied on is locked FOR SHARE and read after
  the locks (D46): a withdrawal committed before the read is seen; one arriving after it waits. Fail-closed: any error or ambiguity
  is `rehearsal_check_unavailable`, never met.
- **Twelve fixed codes** in their own vocabulary (`rehearsal.REASONS`, pinned in the doc), each
  with fixed text shown to the user; the review page shows the status and code, and the user
  can withdraw a rehearsal.
- **A rehearsal is never permission to submit.** The prerequisite applies only to approvals to
  submit, which the user gives separately after seeing the rehearsal's result.
- **Fixture paths** get the rule only through a TEST-ONLY setting, honoured only when
  `env == "test"`; it can only add the rule. Readiness counts a real submission only if its
  send gate found the prerequisite held.

## D46 — One lock order: the attempt, the application, the approval, then what is relied on (2026-10-22)
- **Found and reproduced:** the worker paths (both gates, the rehearsal stop, outcomes,
  checkpoints, the sweeper) locked the attempt, then the application; cancel locked the
  application, then the attempt. Recording evidence also takes the application's key-share lock
  (the foreign key) after the attempt. Races between them deadlocked: PostgreSQL aborted one
  side (`tests/test_lock_order.py`). Reproduced on the old code: a cancel against either gate,
  the `fail_safe` outcome and evidence recording; then, with cancel put back in the old order,
  against the rehearsal stop and the sweeper. Checkpoints and the other outcome writers take
  the same locks in the same order and are covered by the order, without a race test of their
  own.
- **Order:** the attempt, then the application, then the approval, then the application's inputs,
  then what the rehearsal prerequisite relies on (record or receipt). Cancel and claim now
  follow it; nothing else changed order. Clearing an answer or consent now takes the
  application before deleting the input (it deleted first, against a save that took the
  application first).
- **Cancel** looks again after the application lock, for an attempt queued while it waited,
  taking it without waiting; if that attempt is locked (being claimed), the cancel is refused
  ("try again") rather than risk a deadlock. It updates the application as locked, not as it
  was loaded before the wait.
- **The gates read what is committed, after their locks** (READ COMMITTED). Their REPEATABLE
  READ snapshot was taken at the first statement, before they waited for the application, so
  an answer, consent or profile change committed during that wait was not seen (the gate
  passed with the content as approved), and a change to the application's notes made the gate
  refuse. Both reproduced first. D43's serialization-failure refusal is replaced by reading
  after the locks: the approval row lock stays and still makes a writer wait for the gate.
  A cancel committed while a gate waits for the attempt is seen as such: lost authority.
- **Queueing again** with an earlier attempt still pending under an approval no longer valid
  (queued, then edited before a worker took it) stops that attempt instead of failing as a
  duplicate (an uncaught 500); the attempt is locked without waiting, and if a worker is
  taking it, queueing is refused ("try again"). Without this, the claim (now attempt first)
  and the queueing transaction could deadlock on the attempt's uniqueness check.
- **Two locks against the order, never waiting:** cancel's look again for a newly queued
  attempt, and queueing's lock of an earlier pending attempt it stops. Both are NOWAIT and
  refuse ("try again") when the row is locked, so neither can be part of a deadlock.
- **Guarantees, stated precisely** (`docs/architecture.md`, "Race guarantees"): a change
  committed before a gate's check stops it. One arriving later waits if it writes a row the
  gate locks (cancel, revocation, withdrawal, evidence deletion, the application's answers,
  consents and chosen documents, the approval); a profile, work-authorization, document-library,
  answer-bank, form or API-authorization change does not wait, and counts for later packages.
  Nothing can recall what an authorized step already sent, and what is sent is always the
  approved package. No retry was added anywhere. A per-user lock that would make those writers
  wait too is possible (deferred).

## D47 — Provider admission is computed and advisory (I2, 2026-10-22)
- **What:** `providers/admission.py` computes, for every provider, the highest stage of one
  ladder (`registered`, `planned`, `public_doc_reviewed`, `fixture_only`, `observed_read_only`,
  `rehearsal_ready`, `rehearsed`, `live`) that its code tables and recorded evidence support,
  from 37 fixed checks, one framework requirement each (`docs/provider-admission.md`). Served
  read-only at `GET /api/providers/admission`, fixed identifiers only.
- **Claims are bounded by it:** a provider's support state never ranks above its admission
  (tested for every registered provider). A registry raise without its code and records fails
  CI.
- **Advisory upward:** it changes no route, label, approval, package or flag; only the
  providers API imports it. It reads no database, file or network and imports no browser code;
  the repository facts behind its tables are tested in CI (`tests/test_provider_contracts.py`).
- **The owner's four boundaries** (a public-docs and terms review, each read-only run,
  permissions C and D, now recorded separately) open a stage only with a record; code can point
  at a record, never give an approval. None is recorded for a new stage: no public-docs review is recorded for any ATS,
  so Lever and Workday stop at `planned`.
- **A cap:** nothing passes `rehearsal_ready`, whatever the tables say. The import-time rules
  now refuse `real_destinations_enabled` outright; opening either is a reviewed change to the
  live-pilot gate.
- **Recorded runs credit only when single-use and completed** (`evidence.READ_ONLY_RUNS`,
  transcribed from the Runs table and tested against it). Every observed cell in the registry,
  and every "no" trait of the Greenhouse providers, is credited by runs #4, #6, #8 or #9; runs
  #1-#3 (an earlier or general approval) and #7 credit nothing, and #5 recorded nothing to
  credit. The "no" traits of the two generic fixture adapters are their fixtures' own design. The dropdown cell is credited as structure only, so a
  rehearsal's dropdown condition is not met even if readiness counted the level.
- **Waivers keep pre-I2 claims, never advance them:** frozen to the ten providers registered
  before I2, to the claim each had then, and to two checks; today only the unrecorded
  Greenhouse terms review
  (`terms_review_unrecorded`). Known identity gaps are pinned with probes, not fixed (fixing
  them changes stored identities and package hashes), and block `rehearsal_ready`.
- **Fixture scenarios:** each execution provider's fixture levels require ledger tests; the
  mapping found five missing (reconciliation on the three browser adapters, a readback
  mismatch on `greenhouse_hosted`, an upload failure on the API route) and each now has one.
- **Fail-closed changes found on the way:** a captured form whose source no adapter executes is
  refused (`no_adapter`) instead of running on the generic fixture adapter (known sources run
  as before, so no adapter version or package changes); D15 and D28 amended above; an
  over-long ATS company or posting id parsed from a URL (and a URL that canonicalizes past its
  column) no longer fails with a server error: the dedupe key is bounded by a digest of the whole
  key, an over-long posting id is not stored, the URL is refused as too long; a spreadsheet cell
  longer than its column is that row's error instead of a 500 for the whole import.
- **Unchanged:** every support state and capability level, `ADAPTER_VERSIONS`,
  `LEGACY_VERSIONS`, the package `SCHEMA_VERSION`, the route reason codes, the readiness
  conditions and their 0 of 7 (the gate permission is now two records, C and D, both false),
  `detect_ats`, stored identities, migrations. Path A stays pending.

## D48 — Only a resolved answer is sent (C2, 2026-10-23)

- **Rule** (`preparation/sending.py`): an answer is filled, uploaded or sent only when its status
  is `resolved`. The package builder gives every blank optional row no value and no display.
  A row that still shows a proposed value for review (a sensitive answer waiting for the
  user's choice, an accepted draft whose facts changed) blocks approval. A document question
  that is not asked attaches no document.
- **An accepted draft whose facts changed is a checkpoint, optional or not.** Before, an
  optional one became "blank" but kept its text, so the package could be approved and the
  stale draft was sent (reproduced with the receiver's ledger). Now the user saves the text as
  their own answer or requests a new draft.
- **Two layers on the send path, each tested with the other bypassed:**
  - Before any adapter code runs, on both routes, the worker refuses (`failed_safe`, nothing
    disclosed) a stored package whose hash is not the attempt's approved hash, or that has a
    value on a row that is not resolved. Nothing compared the stored package with its approval
    before: the gates check a package rebuilt from current data, so a stored package changed
    without its hash was filled as stored.
  - Every adapter takes `sendable_view` of the package in its constructor, so none fills,
    uploads or reads back a row that is not resolved.
- **Not a shape change:** `SCHEMA_VERSION` stays 2 (the shape is pinned by
  `tests/test_package_contract.py`). Only a package with a stale accepted draft gets a new hash
  (its approval is invalidated, as intended). A form with a document question that is not asked
  could not be prepared at all before (a server error), so it had no package to change.

## D49 — A statement of a profile fact needs agree and the fact; legal and sensitive questions only narrow (C3-C5, 2026-10-26)

- **C3, statements.** A single checkbox, or "I certify / I confirm …" wording on a yes/no choice,
  that states work authorization, a sponsorship need or residence is checked only when the user
  agrees **and** the approved profile makes it true, in one of a closed set of sentence forms
  naming exactly one country (`classify._STMT`). Before, any checkbox was checked from consent
  alone, whatever the facts (an applicant not authorized to work had "I am legally authorized to
  work in the United States" checked once they clicked agree). The facts used are recorded as
  fact references, so changing them invalidates the approval (before, the approval survived).
  Everything else that looks like such a statement (negated, compound, qualified, a region, help
  text that adds a condition, a sensitive topic) is a checkpoint that agree cannot clear.
  Declining an optional statement leaves a box unchecked and a choice blank; it never answers
  "No", which would state the opposite fact. Statements with no profile fact (a licence, being
  over 18, never convicted) stay consent-only; a citizenship statement contradicted by the
  approved authorization facts is not checked. Only agree or decline count as a choice for a
  statement (N7). Statement wording on a text, multi-choice or country-list field is answered by
  the user, never typed as "Yes".
- **C4, legal-fact misreads.** Today's eligibility classifier runs unchanged; on a question it
  would answer from the profile, a veto (`classify._c4_veto`) can only add an ambiguity: not a
  strict yes/no pair, the country only in help text or not exactly one country (regions, "New
  Mexico", "Northern Ireland", "... of America", the EU, "other than", "us" as a pronoun), help
  text that adds a condition, negations (unable, cannot, ineligible), a visa type or status,
  residence in the same question, mixed time frames, conjunctions; authorization only in a
  closed allowlist of question forms (`_AUTH_Q`), so "Do you require a work permit to work in
  Germany?" (answered inverted before), "for any employer", "without restrictions" and similar
  are asked. Citizenship, visa and residence wording that fell to a reusable "unknown" before is
  now a protected question the user answers for each application (`legal_status`).
- **C5, sensitive topics.** Criminal history, health, accommodations, age in any wording,
  national origin, salary history, government IDs, family status, military service, political or
  union membership, caste and minority identity are sensitive; so is a question whose help text,
  options or section is demographic, and a follow-up shown only after an answer to a sensitive
  question (N6). A sensitive topic with an eligibility fact is one sensitive checkpoint. None of
  these is saved, reused or drafted (an accommodations text box is no longer draftable, N9).
  References and generic wording ("If yes, please specify") are never saved.
- **Only narrowing, verified:** against the previous commit, with the very package loop
  (`package.resolve_answers`, extracted from `build_content` so tests run it), over 117 fixture
  forms and test wordings (52,800 rows), every row is identical except stored consents of the
  wrong kind; over 419 fields × 9 profiles × 4 residences × 5 consents × 3 bank states, with and
  without a typed answer (452,520 resolutions), nothing that was not answered automatically is
  answered now, and nothing became newly reusable or draftable. The fixture packages keep their
  hashes (40/40). Recorded as tests: `tests/test_question_safety.py` (the table, controls pinned
  to the previous resolver, a property test), `tests/test_classify_vocabulary.py`.
- **Found by the adversarial review and fixed (each probed against the previous commit):** a
  checkbox mixing a sensitive topic with citizenship ("at least 18 … and a U.S. citizen") lost its
  sensitivity and resolved from agree (a regression; it is a sensitive checkpoint again, not
  reusable); statements in other words ("entitled to work", "can legally work", "eligible for
  employment", "I do not need a visa") stayed consent-only; the citizenship guard missed "a US
  citizen", demonyms and green cards (now placed, and never checked when not placed in exactly
  one country); a "Check this box to confirm …" help text ignored its heading; declining an
  optional statement choice answered "No"; "Answer for the US." followed by a condition passed as
  harmless help; sponsorship at other times ("when your OPT expires"), sponsorship held and
  green-card sponsorship were answered from "needs sponsorship now"; Country or Location fields
  about work authorization or the job's location were filled from residence; regions written as
  adjectives, countries given as examples and organisations named after a country were read as
  that country. Every fix only narrows (verified again: the controls, the 452,520 resolutions and
  the fixture hashes as above).
- **The legacy EEO topics keep their bank policy** (a saved answer is proposed, consent needed
  each time) until C8 decides one policy; changing it would re-hash every package with a gender
  or veteran question.
- **Unchanged:** `SCHEMA_VERSION` (2: no content key added; the new fact references reuse the
  existing types), `RESOLVER_VERSION` (a bump would invalidate every approval for nothing), no
  migration, no bank row deleted or re-keyed. Packages with a changed row get a new version at
  their next rebuild and their approval is invalidated; a queued attempt is refused at the gate
  before anything is disclosed.

## D50 — An unknown outcome in the verification-code step is quarantined; the sweeper recovers each attempt alone (2026-10-27)

- **Found** by the static map of the Freehire-first review (not by a test, a user or CI):
  `TRANSITIONS[needs_user_action]` listed `submitted_unconfirmed` twice, `{worker, system}`
  (durable execution, `8fdeef0`) and `{user}` (Phase A, `37e6646`). A dict literal keeps only
  the last of two equal keys, so only the user could make the move. Reproduced with the receiver
  before the fix:
  - the employer accepted the code but its reply never arrived: the worker's `unknown()` was
    refused (`IllegalTransition`), its error handler was refused again and the worker crashed.
    The receiver's ledger showed the application accepted while NoEfforts showed "needs your
    action", which invites the user to apply again (a duplicate);
  - a worker died while waiting for the code: the sweeper's recovery was refused, and because
    the sweep was one transaction, every stale attempt in its batch (other users' included) was
    rolled back, every 15 seconds.
  - Nothing was ever sent twice by NoEfforts; the failure was a quarantine that never happened.
- **Now:** the move is listed once, for the worker, the system and the user. The sweeper
  recovers each attempt in its own savepoint: one that fails is rolled back alone, counted in
  `errors`, logged with the attempt id and the exception type only, and tried again by the next
  sweep. A code wait quarantined by the sweeper expires its open checkpoint and erases a code
  that was typed for the dead worker (codes are held only until a worker reads them).
- **Guard:** a test parses every dict literal in `app/` and refuses a repeated key (ruff checks
  literal keys only, not `S.x` attributes).
- **Unchanged:** no re-send path, no retry after disclosure or the final click, the gates, the
  lock order (D46; the savepoint takes the same locks in the same order), `SCHEMA_VERSION`,
  reason codes, migrations, support states. Fixtures only; nothing contacted.

## D51 — A saved answer is reused only where it stays true; saves never fail (C6, 2026-10-27)

- **Why.** Risk H (truthfulness): answers that depend on the employer, the job or the date were
  reused from the answer bank ("How did you hear about this job?" → a referral claimed for
  another employer; "previously worked for this company", "relevant experience", start date,
  availability, notice, relocation and salary all resolved from a saved answer), and the bank
  key ignored help text (an answer given for help text H1 was reused for H2). The legacy
  project made the same class of mistake at scale (fixed employer-relative and time-bound
  answers reused everywhere; see the legacy audit). Concurrent saves returned 500: two first
  saves of one question from two applications (unique violation, the second typed answer lost),
  a save racing the deletion of its entry (StaleDataError); two concurrent updates lost a
  version increment and a double delete returned 204 twice. The wording cases were reproduced
  with pure probes against `7669c61`; the five race tests, run against `3af29f0`'s code, fail
  exactly as described (two IntegrityError 23505, version 2 instead of 3, StaleDataError, no 404).
- **Scope rules** (`preparation/bankscope.py`, pure, no LLM): `reason()` returns fact, pay,
  place, employer, time, section, repeated or followup, read from the normalized label (the raw
  label only to tell "us" from "US"), the help text (minus pronoun, "here", willingness, "now",
  history-noun and date families, which are boilerplate there), the option labels (a closed
  subset), the step heading, a date answer, the parent row (a follow-up of a question that is
  not reused) and the form (the same question twice). `resolve_field` clears `bankable` right
  after `_base()`; it never sets it. Relocation and salary join `NO_BANK`. Exempt: the identity
  kinds skip the label families (anchored labels); the legacy EEO topics keep their bank policy
  until C8 (D49). Accepted over-narrowing (8 wordings) and known misses (a named employer
  without deixis) are listed in the test table.
- **Help text in the key without re-keying.** `question_key` keeps the old formula for a
  question without help text and uses `sha256(json.dumps(["c6", label, shape, help]))` for one
  with help text. So no row is re-keyed or deleted, and a row saved before C6 answers only a
  question without help text. `answer_bank.help_text` (nullable; NULL = saved before C6, '' =
  none) is a second check in `_from_bank` and is shown on the Saved answers page. A legacy
  Gender entry is no longer proposed for Gender questions with equal-opportunity help text (the
  policy, proposed and consent each time, is unchanged; only the matching narrows).
- **Saves and deletes.** One `INSERT … ON CONFLICT (user_id, question_key) DO UPDATE …
  RETURNING`, version bumped in SQL only when the value or options change (compared as the
  stored JSON text: `json` has no `=` and `jsonb` refuses a `\u0000`);
  `DELETE … WHERE id AND user_id RETURNING id`, so a second delete is 404 and recorded once.
  The refusal is decided before the typed answer is written, so a refused save changes nothing.
  Lock order (D46) item 6: a bank row after the application and its input, or alone. Rejected:
  select-then-insert, FOR UPDATE alone (no row to lock on a first save), advisory or per-user
  locks, catching IntegrityError and retrying.
- **Tests moved off "How did you hear about this job?"** to "Highest level of education
  completed" (a required select with help text) in `tricky.html` and in the receiver's new mode
  `bank_question`; `basic.html` and the receiver's default form are unchanged.
- **Only narrowing, verified** on the working tree against `7669c61`'s resolver (read with
  `git show`) with scratch scripts: 2,055 forms × 640 contexts = 1,315,200 form resolutions,
  1,424,000 rows, 0 violations (nothing newly bankable, resolved, proposed or draftable; intent,
  sensitivity, protection, acknowledgment, input and drafting unchanged; 192 follow-ups of a
  required trigger that lost its saved answer show their own typed answer while the package
  stays blocked, as for any unanswered trigger); the wording table (975 rows from the design, 1,037 after the review); 9 of the 46 pinned
  controls change, each only by losing reuse (`C6_DELTA`).
- **Unchanged:** `SCHEMA_VERSION` (2: no content key added), `RESOLVER_VERSION`; no bank row
  deleted or re-keyed. A package containing a narrowed row (`bankable` and, for rows without a
  more specific explanation, `explanation` change) gets a new version at its next rebuild and
  its approval is invalidated; a queued attempt is refused at the gate before anything is
  disclosed. Fixture packages that change: basic, tricky, the receiver (both modes),
  greenhouse_like 4012001, greenhouse_v2 5020001; 4012002 and 5020002 keep their hash.
- **Found by the adversarial review** (5 reviewers, each verified by a skeptic) and fixed:
  - wordings C6 meant to cover but missed: the job applied for ("Position applied for",
    "Which role are you applying to?", "Position sought"), what made you apply (a single-line
    field), a rate or "total comp", years of experience written differently ("Years
    experience", "two years' experience"), labels ending in "(optional)" or "(if applicable)",
    the recruiter or hiring manager by name, "submitted an application here", "unavailable",
    class standing, and Unicode dashes; a degree's length in its options ("4 Year Degree") no
    longer counts as time;
  - a NUL in page text or an answer, a stored option label too long to rebuild, and NaN or
    infinity as a number returned 500 (the last was older than C6);
  - a follow-up in a package built before C6 trusted its parent's stored row; a repeated
    sensitive question was refused with the sensitive message;
  - the Saved answers page repeated "Not reused", showed a contradicting line on old rows and
    said the profile holds citizenship (it does not).
  - Accepted, not changed: some stable wordings are refused (over-narrowing only costs a
    re-answer); refuted: two documentation items and one explanation-wording item.

## D52 — Freehire first for discovery; execution stays separate and earns its own evidence (2026-10-27)
- **Direction (owner):** Freehire is the primary job-discovery and job-information source.
  The workflow is discovery → normalized records → dedup and eligibility → matching and
  ranking → preparation and review → ATS-specific execution → confirmation and tracking
  (`docs/freehire-first-architecture.md`).
- **Boundaries kept:**
  - **Discovery is not execution.** A Freehire record never proves that an ATS form is
    understood, supported or safe to submit. It never supplies a form (D35), never names the
    route (the ATS is identified from known hostnames and paths of the job's URL, Freehire's
    `url`; a Freehire record has no apply URL, D35), and is never an execution destination
    (D34).
  - **Only a user action** turns a discovered job into an application. Today a malformed
    record is skipped; an incomplete one, or one closed before it was linked, stays unlinked
    with a manual-handoff route; an unsupported destination is a manual handoff. A record
    closed or gone after linking, a suspicious one and an ambiguous one (more than one dedup
    candidate, so a new job is created) are not stopped yet: the user can still prepare and
    approve them (residual gap, `docs/freehire-first-architecture.md` §4.1). S3 (not started)
    adds a refusal at approval for a job its source says is closed, or one the user excluded,
    and a possible-duplicate signal; suspicious records have no detection.
  - **Job text is untrusted data:** plain text, truncated, never instructions, and it never
    decides which approved facts are used.
  - **Route order** per job (D35, `route_for_job`): a planned-only ATS, a real destination
    or production, or no captured form is a manual handoff; a required control NoEfforts
    cannot fill is a checkpoint before any disclosure; otherwise an authorized API connector,
    then a supported browser adapter, then a manual handoff. Provider order for adapters:
    Greenhouse, then Lever, then Workday.
  - **Unchanged:** the live-pilot gate, the rehearsal prerequisite, per-application approval,
    admission stages, lock ordering, quarantine and no blind retry. No support state is
    raised from legacy code, public documentation or fixtures.
- **Not authorized by this decision:** a live or multi-user Freehire integration, any live
  application, any reading of the owner's inbox or historical application data, or sending
  applicant information to an external AI service outside the product's data-processing
  configuration and consent. Each needs its own approval, and the exact blockers are listed
  elsewhere: for a live Freehire read, `docs/freehire-first-architecture.md` §11 (with D34 and
  the re-check above); for a live application, `docs/live-pilot-gate.md`; for inbox and
  historical data, `docs/outcome-diagnostics.md` §2; for an external drafting provider, steps
  C15 and L4 in `docs/implementation-plan.md`.
- **Legacy project (`autojob-greenhouse`):** reviewed read-only as untrusted input
  (`docs/legacy-audit.md`). Its recollected results (Greenhouse "approximately 85-90%",
  500-700 applications, confirmation emails, no interviews) are not verified reliability
  metrics and are never presented as success rates. No code, data, credentials or sessions
  were copied; its lessons become fixtures and tests (`docs/reliability-test-plan.md`,
  `docs/outcome-diagnostics.md`), never imported records.
- **Rejected:** treating `auto_apply_available`, `source` or Freehire's apply-form preview as
  evidence of support; ranking or eligibility from Freehire's model-extracted fields as facts;
  porting the legacy answer engine (guessing, fuzzy reuse, LLM fallback for basic questions).
- **Plan:** `docs/implementation-plan.md` (slices S1-S7 and steps C7-C18). S1 (C6, D51) is done.

## D53 — A submission says what it rests on; outcomes are reported, dated and never inferred; the funnel is computed (S2, 2026-10-27)
- **Found by reading, each reproduced by a test first:**
  - a user could move `submitted_unconfirmed → submitted_confirmed` through `/transition` with no
    evidence at all, and it looked exactly like an employer receipt;
  - `/reconcile` evidence longer than about 970 characters returned 500 (it was concatenated
    into the 1,000-character `reason`), and 20 spaces passed as evidence;
  - an outcome could be recorded on a draft, there was no "assessment" outcome, no date, no
    source and no audit row;
  - a PATCH racing the worker's receipt lost the row version and returned 500;
  - the review page called every confirmed submission an "employer receipt"; the tracker list did
    not reload after reconciling; `GET /applications/funnel` would have been taken as an
    application id (422).
- **What a submission rests on.** Each application event gets a `source`, set by
  `applications/service.py` from the move and its actor, never by a client: `receipt` (the worker
  observed the employer's receipt), `user_claimed` (the user applied by hand, or confirmed it,
  saying what they checked: 15 to 2,000 characters after stripping, kept in `evidence_note`),
  `user_reported` (an outcome). Event reasons become fixed text ("Confirmed by you", "Reconciled
  as received", "Reconciled as not received"). The unused system actor is removed from both moves
  into `submitted_confirmed`. An application's `submission` (receipt, user_claimed, unconfirmed)
  is computed when read: a receipt recorded on one of its attempts counts even when it arrived
  while the application was quarantined, where the application stays `submitted_unconfirmed` for
  the user to confirm (`execution/service.py` `confirmed()`, unchanged).
- **Outcomes** are recorded by the user only (`PATCH /applications/{id}`): one insert-only event
  with `from_outcome`, `to_outcome`, an optional `occurred_on` (no later than UTC today + 1) and an
  optional private note, plus the audit row `application.outcome {to, source}`; repeating the same
  outcome with nothing new writes nothing. `Outcome.assessment_received` is added. "No response
  yet" (21 days or more in the current submitted stretch, outcome none) is computed, never stored.
- **Before a submission.** An outcome other than none or withdrawn needs a submission NoEfforts
  knows of: a submitted state now or before, or a recorded receipt. Otherwise 400 `(reason:
  outcome_before_submission)`, and nothing is written, not even the notes. Consequence, accepted:
  under this rule an application that was cancelled, expired or failed before any submission can
  never take an employer outcome; the message says NoEfforts has no record that it reached the
  employer, and the page offers "I applied myself" only where that move exists (a draft). A final
  click whose verification code was never completed ends in `needs_user_action`: the state machine
  lets the user record it as submitted from there, but no page offers that move yet, so until one
  does it takes no employer outcome through the page (a known gap, below).
- **Owner switches (code only, reversible without a data migration):**
  `states.USER_CONFIRMS_THROUGH_TRANSITION` (True; False refuses `/transition` with `(reason:
  confirm_through_reconcile)` and leaves `/reconcile`) and `states.OUTCOME_BEFORE_SUBMISSION`
  ("refuse"; "flag" accepts and shows the outcome as recorded before a submission). Tests switch
  each one.
- **Database.** Migration `e3a91c5d7b20`: the enum value, five nullable columns, two CHECK
  constraints that bind each source to its kind, actor and target (valid at once, also for rows
  written before S2, which keep NULL everywhere and are never back-filled), and a trigger that
  makes events insert-only: UPDATE is refused, and DELETE unless it cascades from the application
  or user. A future data repair must drop and recreate the trigger deliberately. Trade-off,
  accepted for now: a note the user regrets cannot be edited or removed (the page says so);
  redaction to a fixed marker would be a later slice with its own trigger exception. Downgrade is
  refused while an application holds `assessment_received`.
- **Locks (D46).** PATCH locks the application and re-reads it before deciding; a user's
  confirmation (`/transition`, `/reconcile`) locks the application's attempts by id, then the
  application (`service.lock_submission`), the same order as the worker's receipt.
- **The funnel** (`GET /applications/funnel`, `applications/funnel.py`): per user, computed when
  read, counts with their denominators and no rate; below 20 submissions it says the numbers are
  too few to compare. It is a view for the user; tests take "submitted" from the receiver ledger.
- **Recording Withdrawn does not stop a submission in progress** (Cancel does); the page says so
  while one is queued or running.
- **Found by the code review (4 reviewers, each checked by a skeptic) and fixed:** a NULL target
  let a `receipt` or `user_claimed` row pass the database check (a CHECK passes on NULL); the
  request and `transition()` stripped evidence differently (pydantic keeps U+001F, Python removes
  it), so 14 visible characters passed the request and failed later with a 500 on `/reconcile`;
  one strip now applies everywhere, and a NUL in user text (which PostgreSQL text cannot hold,
  also in the older `notes` and `reason` fields) is refused with 422; an outcome recorded before
  S2 dropped out of the funnel when the next one was typed (a typed change's `from_outcome` now
  counts as recorded); the outcome form sent a date it no longer showed; the Withdrawn warning
  named a Cancel button the card does not have (and in `submitting` a cancel is refused); the
  reconcile panel kept typed text across applications. Refuted: 7, among them a lock race in the
  downgrade guard (it needs the API to serve writes during a downgrade).
- **Unchanged:** `execution/service.py`, every retry rule (no retry after `sending`), D15, D50,
  `SCHEMA_VERSION` 2, `RESOLVER_VERSION`, route reason codes, support states and the pilot gate.
  No package hash changes and no approval is invalidated.
- **Known gap, out of scope:** after a final click whose verification code was never completed
  (`needs_user_action`), no page offers "it reached the employer" yet; the move must not be offered
  while an attempt still holds the application (claimed, sending, awaiting a code), and needs its
  own wording and e2e step.
- **Known gap, out of scope:** a late receipt arriving after the user marked the application
  `failed_terminal`, or after a "not received" reconciliation was queued again, makes
  `confirmed()` refuse the move; the attempt keeps its earlier state and the funnel cannot count
  that receipt. It needs its own slice with receiver tests.
- **Rejected:** a separate outcome endpoint (PATCH already carried outcomes); storing the
  submission basis (it is derived from attempts and events); back-filling sources or typed values
  into rows written before S2 (unknown stays unknown); a NOT VALID constraint; percentages.

## D54 — The legacy collisions are permanent tests; each that still resolved is a checkpoint; no mailbox client and no page capture (S4, 2026-10-27)

- **The corpus.** `backend/tests/legacy_collisions.json`: 244 synthetic rows for reliability
  plan R8.1-R8.11, R8.16 and the R2.9 resolver row, each naming the legacy finding it
  reproduces, traps and controls (a control pins an answer that must stay, so a fix cannot
  over-narrow it). A row is one field resolved through `package.resolve_answers` (the loop that
  builds packages) against "rich" facts whose values are sentinels (a wrong mapping shows up as
  a sentinel in the answer) or no facts, with saved answers stored as `_save_to_bank` stores
  them and an optional explicit choice. `expect` is the safe outcome, never what a matcher
  happens to do. Driven by `test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome`,
  with sockets refused while it resolves (the resolver stays LLM-free).
- **The previous resolver gave a wrong answer on 47 of the first 164 rows, and on 104 of the
  final 244** (the others pin behaviour that already held). Each is now a checkpoint
  (`docs/answer-policy.md`, the S4 rules):
  1. someone else's name, email, phone or link (an emergency contact, a reference, a referee, a
     recommender, a manager, a parent, an agency, an employer) filled from the profile: now asked
     and never saved, by section or by help text naming them or an organisation's own;
  2. a preference read as residence (a City field with help "Where would you like to work?");
  3. residence or nationality in other words ("Are you Portugal-based?", "Portugal resident?",
     "Are you a US resident?", "Are you in Lisbon?", "Are you Portuguese?", "Are you an EU/EEA
     national?") answered from a saved answer or drafted as long text, and the same wordings on a
     single box (with or without a preamble, or in a heading's help) ticked on agree against the
     residence fact: now protected questions and never-checked statements;
  4. relocation answered from the general preference when negated ("Are you not willing to
     relocate?" was answered Yes), placed, timed, costed or conditional, in the label or the
     help: now only the plain question with no help beyond an answering instruction (closed
     forms, as C4 did for authorization);
  5. a right to work stated negatively ("I cannot / am unable to / would not be able to work in
     Portugal", "ineligible for employment in …") ticked on agree: never checked now, and
     protected as a question;
  6. agree/decline options under a neutral label ("I do not agree" / "I agree", "Yes, I agree",
     "Agreed", "I affirm", "I understand") answered from a saved answer: never saved now, and a
     stored consent does not pick one (no new automatic path);
  7. a fact answer that does not fit its field ("Yes" typed into a long answer or several boxes,
     a country as text into a multi-select, a link into a choice): never sent now (any fact
     answer that fails `validate_value`); the user answers it for this application, no saved
     answer takes its place, nothing is saved, and the row keeps the fact it was about, so
     changing that fact invalidates the approval of what was typed (`_does_not_fit`);
     `validate_value` requires a non-empty set with no option twice, as `normalize_input`
     already did; a typed number is shown with every digit (`:g` kept six);
  8. a saved answer naming an option that two current options share after normalising, or the
     same option twice: refused.
- **Kept, by the answer policy:** a box no profile fact records ("I am unable to travel", "I am
  not willing to relocate") is still checked on the user's explicit agree, with no fact behind it
  (row 1, D49). Reliability plan R8.10 first said such statements need an approved fact; that
  wording contradicted row 1 and is corrected. Narrowing it would be one rule; it is the owner's
  call, not a defect. Citizenship statements keep C3's rule ("I am a U.S. citizen" is checked on
  agree unless the authorization facts contradict it), and "Do you have a passport?" stays a
  reusable question (C6's table).
- **Adversarial review, three rounds (5 reviewers, then 3, then 3; each checked by a skeptic).** Round 1
  (47 findings, 2 refuted) found that the first other-person rule kept those fields bankable, so
  someone else's details could be saved and reused (a widening; the narrowing sweep showed it as
  answers moving from the profile to the bank), that a refused fact answer fell through to a
  saved answer and kept the profile as its source, so the router refused the user's own typed
  answer, many variants of each trap and some over-narrowing ("US-based hours", "a medical
  resident", a language row named "Portuguese", Workday's "My Experience", "a recruiter will
  call you", a rating scale, now control rows); and in the guards, code inside strings, a JS
  comment stripper that ate code, the compose form `DEBUG: pw:api`, installs over several lines,
  CI workflows, list-form `addopts` (a crash), more mail APIs and import forms, and self-tests
  that did not prove their scope. Round 2 (32 findings, 1 refuted) found that a typed answer to a
  protected fact that did not fit was tied to no fact (it survived a profile change with the
  approval still valid), residence questions as text boxes being drafted, residence statements
  behind a preamble or in help text, a "not" anywhere in help text reopening the other-person
  rule, relocation help still a denylist, more variants, and in the guards f-string scripts,
  regex literals defeating the comment stripper (comments are no longer stripped), inline code
  and mail hosts in compose and CI files, JS imports of mail packages, more capture APIs
  (a browser CDP session, `page.pdf()`, cookie export) and fourteen rule mutations no
  self-test caught. Round 3 (widening, slow paths and CI only; 6 findings, 0 refuted, after
  the sweep below had passed) found two widenings the sweep's generated forms did not reach: narrowing
  HEAD's "would like" to "would you like" let a City or Country field with help or a section
  such as "the team would like you to work from" be filled from residence again, and the
  negated right-to-work rule ran before C5's help, option and section signals, so "Is there
  anything that would prevent you from working in Portugal?" with help naming a disability lost
  its sensitivity (a typed answer went without a disclose choice and a Country follow-up was
  filled from residence). Both are fixed ("would like" is back; the rule runs after the C5
  signals) with corpus rows and a follow-up test that fail without the fix. It also found three
  slow paths on untrusted page text (an "Are you in A/B/…?" list read part by part, up to 60 s
  for a 300-field form; a help-text negation searched over the whole prefix; a saved answer
  matched against every option pair): a list of more than ten places is now read as residence
  (narrowing), the negation is searched in its 42-character window (identical on 200,000
  random texts) and options are indexed once. All confirmed findings are fixed; a mutation
  check of the guard file now kills every single-rule mutation but one equivalent one.
- **What remains, by construction:** the classifier reads lists of wordings, and wordings none
  of its rules reads are still ordinary questions. The cost is bounded: such a question is
  answered only by a saved answer the user chose to keep for that exact wording, help text and
  options (row 5), never from a fact. The corpus is the place to add the next one. The static
  guards are tripwires for capabilities added by accident; code written to evade them (a name
  built from data outside the code that drives a page, a mail protocol over a raw socket) is not
  seen, and the test says so.
- **Only narrowing, verified** against the previous commit's resolver with the same package
  loop, with scratch scripts (not in the repository), on the final code: 16,359 synthetic forms
  (every wording in the corpus, the C3-C6 tables and the vocabulary tests, each also as text,
  Yes/No, a single box, a set, optional, under a reference step, under an application step and
  with place or preference help, plus the two fixture forms) x 432 contexts (four profiles,
  three sets of authorization facts, three preferences, no consent, agree or decline, with and
  without saved answers, with and without typed answers), 7,080,048 rows: 0 newly answered
  automatically (a typed answer or an accepted draft is the user's own), 0 newly bankable, 0
  newly draftable; the fixture forms (32 fields, 13,824 rows) unchanged. Every change is an
  answer that became a checkpoint or the user's input, or one no longer saved or drafted. Round
  3's reviewers' probe forms (543) give the same result.
- **The guards** (`backend/tests/test_forbidden_capabilities.py`; R7.5, R11.4): read with `ast`,
  never imported; every Python, JavaScript and shell file outside the frontend, the images,
  compose files, CI workflows, every dependency manifest and the pytest configuration; for mail,
  the frontend's own source too. Mail: no mail module or SDK (or one whose name says mail), no
  mail host, API, scope or protocol, no mail program, no mail package installed or imported by a
  script, and no import named at run time in `backend/app`. Capture: no screenshot, video,
  trace, HAR, PDF, CDP session or captured session (storage state, a persistent profile, cookie
  export), no capture keyword or Chromium flag, no in-page capture, no Playwright debug logging;
  where a page runs, no attribute or code named at run time. Each rule has planted samples that
  must be caught and prose that must not be.
- **Unchanged:** `SCHEMA_VERSION` 2 (no content key added), `RESOLVER_VERSION` (a bump would
  invalidate every approval for nothing), no migration, no saved answer deleted or re-keyed,
  execution unchanged. Packages with a narrowed row get a new version at their next rebuild and
  their approval is invalidated; a queued attempt is refused at the gate before anything is
  disclosed (as in D49). So do packages holding a number with more than six significant digits:
  its shown value is part of the hashed content, so the new version's reason is "metadata
  changed" (nothing new is answered).
- **C10 is partly done:** a fact that does not fit its field is refused here; choosing among
  several links of one kind (the first is used) and saying why on the review page remain C10's.
- **Known gap, before S4:** C4's affirmative right-to-work wordings ("Can you legally work in
  Portugal?") are read before C5's help, option and section signals, as at the previous commit:
  with help naming a disability such a question is a protected legal question, not a sensitive
  one, and a fact-kind follow-up of it can be filled from the profile. S4 did not change it
  (only the negated wordings it added run after the signals); making it sensitive is a separate
  narrowing with its own tests.
- **Known gap, out of scope:** the fixture adapter fills and reads back a number with `:g`
  (`execution/adapters/fixture_ats.py:110,144`), which keeps six significant digits, so a typed
  1,234,567 would be filled as "1.23457e+06" and read back the same way. Fixture-only (no real
  destination); it belongs with C10 or a small execution change with its own receiver test.
- **Rejected:** answering the narrowed rows from a different fact (that would widen); turning
  agree/decline options into acknowledgments (a stored consent would then answer them, a new
  automatic path); a denylist for relocation (closed forms instead); stripping JavaScript
  comments (a stripper can be fooled; a comment naming a capture call fails instead).

## D55 — A live Freehire read for the owner only, one approved run at a time (S7, 2026-10-28)
- **Owner statement (2026-10-28):** "Go ahead, because I want to fetch the job postings from the
  freehire", after being told that Freehire sells auto-apply and that CLAUDE.md forbids
  automated access to competitor APIs. Recorded as: reading postings through Freehire's
  documented API for the owner's own job search is allowed under that rule. Personal use only
  (D34): showing Freehire postings to anyone else still needs a Freehire plan and its own
  statement.
- **What changed:**
  - `NOEFFORTS_DISCOVERY_OWNER_EMAILS` names the accounts that may read live (empty: nobody);
  - table `discovery_run_approvals` (migration `4bc9c342d34c`): one approval per run, naming the
    exact search, the page limit (1 to 5), the window (at most 24 hours) and the retention
    statement, recorded by the owner on the backend host with
    `python -m app.modules.discovery.approve`;
  - an import whose base URL is exactly `https://freehire.me` checks, in this order and with
    nothing looked up or requested before the first two: the account is an owner (else 403);
    an unused approval for this exact search is inside its window (locked; else 403);
    `freehire.me` resolves to public addresses only (`resolve_public_destination`, else 409).
    It then marks the approval used and commits before the first request, and reads at most
    the approved pages. A failed run (429, outage) has used its approval; nothing re-runs;
  - any other non-fixture base URL stays refused, even with an approval; refreshes and health
    checks never read live;
  - audit events `discovery.run_approval.create` and `.use` (counts and the provider key only;
    the search and the retention statement stay in the approval row).
- **Not done here:** no request to Freehire was made. The sandbox's network proxy refused
  `freehire.me` (`connect_rejected`), so the installer the owner pointed to
  (`https://freehire.me/install.sh`) could not be read, and it is never run unread; the
  `freehire` CLI and the MCP endpoint (`https://freehire.me/api/v1/mcp`) are not used by
  NoEfforts, which reads the same documented API with its own client (no Freehire code is
  installed or ported, `THIRD_PARTY_NOTICES.md`). Separately, after the owner connected
  Freehire's MCP connector to the assistant session, the assistant ran one search through it
  for the owner (titles "financial analyst", "finance analyst", "FP&A", last 30 days; 20 of
  5,679 results shown to the owner, nothing sent from the profile, nothing stored in NoEfforts).
- **Still open:** a per-user delete of discovered rows and the owner allow-list for fixture
  imports (S6); multi-user use, scheduled runs and live refreshes (each needs its own
  decision); the terms re-read on the day of each run.
- **Rejected:** a standing permission (each run is approved separately); reusing an approval
  after a failed run (that would be an automatic re-run); a looser match than the exact search
  (the approval names what is read); approving from the same web session that runs the import
  (for now the approval is a separate act on the backend host).

## D56 — Watched Freehire searches for the owner, checked as often as once a minute; deleted postings stay deleted (S8, 2026-10-28)
- **Owner direction (2026-10-28):** "Make the pulling from freehire on live. As soon as the
  freehire receives the job posting in his portal it should be om our portal too", then "Get
  the new job posting within a minute", after being told that Freehire offers no push or
  webhook (its change feed is announced as "the next thing we are building"), so the only way
  is to check it, and that showing the postings to anyone else needs a Freehire plan.
  Recorded as: a standing approval per watched search replaces D55's one approval per run for
  those searches, for the owner's own use only (D34).
- **What changed:**
  - table `discovery_watches` (migration `29588d78e7e1`): the exact search, an interval of 60 s
    to a day, an end date at most 90 days on, the retention statement, and the bookkeeping
    (next check, last outcome, failures in a row, the pause reason, found postings, requests
    per UTC day); recorded, listed and stopped with `python -m app.modules.discovery.watch`;
    listed and stopped on `GET /api/discovery/watches` and `POST .../{id}/stop` (the owner's
    only; another user's is 404);
  - the worker task `noefforts.check_discovery_watches` runs every 10 s and does nothing unless
    Freehire is an enabled provider. Each due watch is locked with SKIP LOCKED (never checked
    twice at once) and checked in order: the account is an owner (else paused), the address
    is the live origin or a fixture (else paused), the daily cap
    (`NOEFFORTS_FREEHIRE_DAILY_REQUEST_BUDGET`, default 1,440: one request a minute for a day,
    and under Freehire's pending strict mode of 2,000 a day per address) leaves room for a
    check (else it waits for the next UTC day), the address resolves to public hosts only; then
    at most two requests, newest first (`sort=created_at&order=desc`, documented), stopping at
    the first page holding a posting already stored;
  - a failure (a 429, an outage, a refused address, anything unexpected) is never retried
    inside the check: the next check waits the interval doubled per failure in a row, at most
    an hour, and at least the 429's Retry-After; ten in a row pause the watch; an exhausted
    `X-RateLimit-Remaining` waits at least a minute;
  - deleting a discovered posting (`DELETE /api/discovery/jobs/{id}`) erases its content and
    keeps only its id (status `dismissed`), so no import or watch adds it again; its tracker
    job goes too when discovery created it, nothing else links to it and it has no
    application (otherwise the answer says why it stays). The Discover page lists the watches,
    stops them, deletes postings and reloads every 20 s while a watch is active;
  - audit events `discovery.watch.create`, `.found` (only when a check added postings),
    `.pause`, `.stop` and `discovery.job.delete` (counts, reasons and the provider key only).
- **Timing, honestly:** a posting reaches the job list within about a minute of appearing in
  Freehire's search (the interval plus up to 10 s), not of appearing on the employer's site:
  Freehire crawls job boards on its own schedule. Only while NoEfforts and its worker run.
- **Not done here:** no request to Freehire was made (the sandbox refuses `freehire.me`);
  multi-user use and showing postings to others (a Freehire plan and its own statement);
  any application (D55, the live-pilot gate).
- **Rejected:** checking more often than once a minute (the budget, and no faster source
  exists); following the employers' boards directly (not this decision, and the boards' own
  terms); retrying a failed check sooner than its backoff; deleting a posting's id with its
  content (it would come back on the next check).

## D57 — A State, City or Country list is never a dead end; only a list of every US state is mapped (C11, 2026-10-28)
- **Problem:** residence is a protected fact (PROFILE_ONLY): the user may not answer it per
  application, so that every application stays consistent with the profile. On a choice field,
  though, NoEfforts mapped only the country. A required "State" list returned "The form offers
  fixed options; choose one", a City list did the same, and a Country list without the
  profile's country said "Choose one": the user was told to choose and was not allowed to, so
  preparation stopped there for any form asking for a US state.
- **What changed (`resolver.py`):**
  - **State:** a list gets the profile's state only when the profile's country of residence is
    the US, the list names all 50 states (by name or postal code; DC and the territories may be
    there too, and so may placeholders or Canadian provinces), and exactly one option is the
    profile's state by name or code (`US_STATES`, `map_region`). Source **Mapped from profile**,
    the fact recorded.
  - **Anything else is the user's answer for this application** (`_does_not_fit`, D54): another
    country, an unknown country, a short or incomplete list, the state twice, a near match, a
    part of a name, several boxes. Nothing is sent until the user answers; a saved answer never
    takes its place; it is never saved for reuse; the row keeps the profile fact it was about,
    so changing that fact invalidates the approval of what was answered.
  - **City:** a list of cities is never picked from the profile, even when it offers the
    profile's city: a fixed list of cities is usually where the job is, not where you live
    (LD-28, R8.3: the legacy bot filled such lists with the home city). Always the user's answer
    for this application, tied to the profile's city when there is one. Typed text is still the
    profile's city.
  - **Country:** a list with exactly one option for the profile's country is mapped as before;
    otherwise (none, or two) it is the user's answer for this application.
  - Typed State, City and Country fields are unchanged. A State list with no verified state in
    the profile still asks for it in Profile.
- **Why only a full US list:** an exact option is not enough. Another country's list shares
  names and codes ("WA" is Western Australia; "Central", "Western", "Punjab", "Limburg",
  "Córdoba" are first-level regions in several countries), and a short list of states is usually
  where the employer hires. A list naming every US state is an address list, and the US table
  is closed and exact. Other countries' lists have no table here, so they are the user's.
- **Effect on approvals:** a rebuilt package differs only on such rows (a newly mapped state,
  a new explanation), so an approval of a package with such a row is invalidated when the
  package is rebuilt; nothing approved before could have been sent with a required one (it
  blocked approval). No change in package shape: `SCHEMA_VERSION` (2) and `RESOLVER_VERSION`
  stay (a bump would invalidate every approval for nothing).
- **Evidence:** `tests/test_resolver.py` (C11 section: 13 mapped lists, 16 refused lists, a
  missing state, several boxes, typed text, city lists, country lists),
  `tests/legacy_collisions.json` (six rows, `r8_3_*` and `r8_6_*`, with `user_input_allowed`
  now checked by the corpus loop), `tests/test_answers_that_do_not_fit.py::
  test_state_city_and_country_lists_are_never_a_dead_end` (through the API: refused reuse, the
  typed answer kept, a move re-maps the state and invalidates the approval). The narrowing sweep
  against `ba2a6d4` is in `docs/implementation-status.md`.
- **Rejected:** mapping exact names on any list (cross-country collisions); prefix, substring or
  fuzzy matching; picking a city from the profile; letting the user answer a protected fact the
  profile already answers on a field it fits (unchanged: fix the profile); asking the user to add
  a city to the profile first for a list that never uses it.

## D58 — A link question gets the profile's link only when exactly one is of its kind (C10, 2026-10-28)
- **Problem:** a LinkedIn question took the first profile link containing "linkedin.com"
  anywhere, and a website question the first link that did not. So a second LinkedIn profile,
  or a portfolio after a GitHub link, was never offered and the first was sent unasked; a
  LinkedIn company or jobs page answered "LinkedIn profile"; and an address that only mentions
  "linkedin.com" (another host, a query string) counted as LinkedIn and was never a website.
- **What changed (`resolver.py`, `_link`, `_link_kind`, `_link_key`):**
  - the kind is read from the host, never from a substring: a LinkedIn member profile is a
    `linkedin.com` host (or a subdomain such as `uk.linkedin.com`) with an `/in/` or `/pub/`
    path; any other LinkedIn page is neither kind; every other address is a website;
  - the same address spelled twice (with or without `www.`, a trailing slash or a scheme) is
    one link;
  - exactly one link of the kind is answered from the profile, as before; **several are never
    chosen between**: the row says how many there are and that NoEfforts does not choose, and
    the user gives the one for this question (typed here, or a saved answer to this exact
    question); the row keeps the links fact, so editing the links asks again; keeping one link
    of the kind in Profile answers it from the profile again.
- **The review page says why:** the row's explanation is shown under the question, with the
  answer box (`frontend/e2e/review-reasons.spec.ts`: two LinkedIn profiles, and a website with
  no scheme in a web-address field, S4's fit check).
- **Effect on approvals:** rows change only for profiles with several links of one kind, a
  LinkedIn page that is not a profile, or an address that merely mentions LinkedIn; such a
  package gets a new version when it is rebuilt, and its approval is invalidated. No change in
  package shape: `SCHEMA_VERSION` (2) and `RESOLVER_VERSION` stay.
- **Evidence:** `tests/test_resolver.py` (C10 section: one link of its kind, several, another
  kind), the Playwright spec above, and the sweep against `f377276` in
  `docs/implementation-status.md`.
- **Rejected:** choosing by order, by words in the question ("Portfolio" → GitHub) or by
  recency; matching hosts by substring or by similarity; asking for a "primary" link flag in
  the profile (a shape change, left to C18 if ever wanted).

## D59 — Closed, excluded and possibly duplicate jobs wait for the user before approval (S3, 2026-10-28)
- **Problem:** nothing stopped an approval for a posting its source had closed (LD-41's wrong
  postings), for a job the user had excluded or closed, or for a second copy of a role already
  applied to (LD-11: a Freehire repost gets a new slug; another board gets another URL).
- **What changed:**
  - `backend/app/modules/jobs/signals.py` reads three signals, user-scoped: **source says
    closed** (a linked discovered posting reported `closed_at`, or gone at its address on a
    refresh; never a listing that merely left it out), **excluded or closed by you** (the job's
    status), **possible duplicate** (another of your jobs with the same employer key, the same
    normalized title, the same location when both have one, and an application past draft);
  - approval (`package.approve`, every scope) is refused with a fixed reason code
    (`job_excluded`, `job_closed_by_you`, `job_source_closed`, `job_possible_duplicate`,
    `docs/job-signals.md`) until the user answers it; preparation is never blocked, and the
    check is outside the package content, so answering it changes no package;
  - the user's audited statements: "It is still open" (`POST /api/jobs/{id}/still-open`,
    `job.confirm_open`) holds until the source reports it closed again after it (the time the
    source first said so is kept: `discovered_jobs.stale_since`); "This is a different role"
    (`POST /api/jobs/{id}/different-role`, `job.confirm_distinct`) answers the applications
    known then, so a later application to the same role asks again; a status is changed on the
    job page;
  - shown on the job page ("Before you apply", the other job, its application's state and
    outcome), on the review page (the message, the reason code, approval disabled) and on each
    Discover row (your application's state and outcome, "possible duplicate");
  - migration `269ea4b8bc0c`: the three timestamps; rows already stale get `last_seen_at` as
    the time their source said so;
  - Greenhouse embed URLs (`/embed/job_app?for=<board>&token=<id>`, R5.10) are read as the
    Greenhouse posting, so they have the board URL's identity; without `for=` the employer's
    name stands in for the board; a job stored before under its URL identity is found again by
    the same URL instead of adding a second job;
  - fixture mode `fh_repost` (the same employer and title under a new slug, id and URL).
- **Owner decision taken as a default (`freehire-first-architecture.md` §12 item 5, "block or
  warn"):** a possible duplicate never blocks preparation and never merges anything; approval
  waits for one click ("This is a different role"). This is the plan's own proposal (a
  checkpoint the user confirms); switching to warn-only is one line in `approval_refusal`.
- **Not done:** an approval given before a signal appeared is not withdrawn (a new one is
  refused, and the pages show the signal); Freehire's copy groups (`/jobs/{slug}/copies`) are not
  fetched; real employer destinations stay refused anyway.
- **Rejected:** writing a closed flag onto the job (discovery never edits a tracker job);
  merging or auto-linking duplicates; matching roles by similarity; counting a draft
  application as applied.

## D60 — Answers and consents apply only to the question they were given for (C7, 2026-10-28)
- **Problem:** an answer or a consent was stored by the question's key alone. When an
  employer's form was captured again with the same key and other wording (an acknowledgment
  that now also lets the employer share data, a question about other experience, a choice with
  new options that kept the old one), the earlier answer or "I agree" carried over unasked. A
  "disclose" choice covered whatever answer the field held later, not the one the user saw.
- **What changed (`preparation/binding.py`, `package.load_context`, `resolver.resolve_field`):**
  - each answer and consent stores the fingerprint of the question as it was shown
    (`forms.field_fingerprint`: wording, help text, type, requirement, options, condition) in
    `application_inputs.meta.field_fp`; an accepted draft keeps its evidence beside it;
  - when the question's current fingerprint differs, the answer or choice is left out (it is
    kept in the database, never sent) and the question says why ("This question changed since
    you answered it …"); the user answers or chooses again;
  - a "disclose" choice stores a keyed digest of the exact answer it covered
    (`meta.value_digest`: HMAC-SHA-256 under the server's reference key, domain-separated,
    scoped to the user and the question; never a copy of the answer); a changed answer, typed or
    saved, needs "Include this answer" again ("Your answer changed since you chose to include
    it …"); "Don't disclose" is not tied to the answer;
  - rows saved before C7 have no fingerprint: the form version current when the row was last
    saved stands in, so an unchanged question keeps its answer; a "disclose" saved before C7 has
    no digest and is asked again once.
- **Effect on approvals:** a recaptured form already gives a new package version (the form is
  part of the destination); now the changed question is unresolved, so the package cannot be
  approved until it is answered again. No change in package shape: `SCHEMA_VERSION` (2) and
  `RESOLVER_VERSION` stay; no migration (the binding lives in the existing `meta` column).
- **Rejected:** keeping the answer when only the wording "looks similar" (not deterministic);
  storing the disclosed answer beside the choice (a second copy of sensitive data); tying
  "Don't disclose" to the answer (withholding stays right whatever the answer is).

## D61 — "Don't disclose" on a required question sends the form's own decline option (C8, 2026-10-28)
- **Problem:** R3.4 had no end-to-end evidence: nothing showed, from the employer's side, that a
  withheld sensitive answer stays out and an included one goes in. "Don't disclose" on a
  required self-identification question was a dead end even when the form offered its own
  "Decline to self-identify", and the bank policy for the equal-opportunity topics was left to
  this step (D49).
- **What changed (`resolver.map_decline`, `_resolve_sensitive`):**
  - "Don't disclose" on a **required** select, radio or multi-choice sensitive question is the
    form's one option whose normalized label is in a fixed list of decline wordings
    (`DECLINE_WORDS`: "Decline to self-identify", "I don't wish to answer", "Prefer not to
    say" …, exact after normalization). It is shown on the review page with its reason, sent as
    that option, and never saved. Your typed answer is kept for review and is not sent;
  - no such option, two of them, a looser wording ("Decline", "Other / decline") or a text
    question: the checkpoint stays ("Pick an answer …"); NoEfforts never chooses between
    two decline options;
  - an **optional** question is still left blank, even when it offers a decline option: no
    answer discloses least.
- **One bank policy for the equal-opportunity topics:** unchanged and now the policy. An answer
  you saved for one of the original topics, found in the wording, is proposed on a later form
  and is sent only after "Include this answer" there, for that exact answer (C7's digest). A
  decline option chosen by "Don't disclose" is never saved. Narrowing further would re-hash
  every package with a gender or veteran question and would not change what is sent: nothing
  reaches an employer without the per-application choice.
- **Evidence:** `tests/test_disclosure_ledger.py` counts with the receiver's own ledger:
  "Include" sends the answer, "Don't disclose" sends nothing on the optional question and
  `decline` on the required one (receiver mode `required_eeo`), an answer without a choice
  blocks approval, a saved answer is sent only after "Include". The Playwright test
  `submission.spec.ts` clicks both buttons on desktop and mobile and reads the ledger.
- **Effect on approvals:** only packages that could not be approved before change (a required
  sensitive question with "Don't disclose" now resolves). No new content key: `SCHEMA_VERSION`
  (2) and `RESOLVER_VERSION` stay; no migration.
- **Rejected:** choosing the decline option on an optional question (it discloses a choice the
  form does not need); matching any label containing "decline" (an "Other / decline" option is
  not clearly a refusal); choosing between two decline options; sending a required question
  blank (the employer's form refuses it, or worse, reads it as an answer).

## D62 — Fixture variants from the legacy notes; confirmation bound to the attempt everywhere (S5, 2026-10-28)
- **Problem:** the legacy author's notes on real pages (`legacy-audit.md` R7, HYPOTHESIS:
  phrases that look like a confirmation, code boxes, autofill after an upload, bot checks after
  the click, consent banners, multi-page forms) had no fixture, so nothing showed what the
  adapters do on such a page. Admission required no scenario for dropdowns, location pickers,
  confirmation detection or multi-step forms, and two adapters accepted a confirmation without
  binding it to the attempt (the generic fixture took any page with a receipt; the v2 adapter
  took a status message even when it was on the page before the click; the API adapter took
  any acceptance).
- **What changed (fixtures, FIXTURE ASSUMPTION each, `fixtures/ats_receiver/README.md`):**
  sixteen modes and a posting path holding "thanks" and "confirmation"; each click on a
  banner, an "I agree" button or a submit that meets a bot check is recorded in the ledger.
- **What changed (adapters, fixture-only):**
  - confirmation is bound to the attempt in every adapter: the generic one now needs its own
    POST to this posting and the receipt shown on this posting's pages; v2 ignores a
    confirmation-like message present before the click (unknown); the API adapter needs the
    reply to name the application this attempt created; words on a page never confirm;
  - a bot check after the final click is unknown with a fixed reason, never solved or
    clicked again (`submitted_unconfirmed`, reconciled by the user);
  - the Greenhouse-like adapter types the user's code into one input or one character per box
    (four to twelve one-character inputs); a code that does not fit is never typed and is asked
    again; a code step it does not recognise is unknown, nothing typed;
  - nothing outside the approved answers is clicked; a submit button still disabled after
    filling stops before the send gate (abandoned); a form that continues on another page
    stops before disclosure (its first page lacks approved questions).
- **What changed (admission):** `CAPABILITY_SCENARIOS` gains `custom_dropdowns` →
  `unlisted_option_is_checkpoint`, `location_picker` → `location_exact_or_checkpoint`,
  `confirmation_detection` → `confirmation_bound_to_attempt`; `TRAIT_SCENARIOS` requires
  `each_step_read_back_before_next` for a `multi_step` trait that is not "no" or "not
  applicable" (`greenhouse_hosted`, "unknown"). Each required pair has a ledger test; no gap
  is recorded.
- **Unchanged:** no admission stage moves (`fixture_only` remains what fixtures prove); the
  challenge stop is not narrowed (the owner decision in `implementation-plan.md`); filling a
  second page stays unsupported; real employer destinations stay refused; no package-shape
  change (`SCHEMA_VERSION` 2).
- **Rejected:** treating a bot check after the click as a rejection (the data may have
  arrived); typing part of a code into the boxes; clicking "I agree" or a cookie banner for
  the user; recording a scenario gap instead of a test.

## D63 — A salary is sent only in the units the question allows (C9, 2026-10-28)
- **Problem:** the salary expectation was sent whenever a question looked like one: a number
  field got the bare amount in whatever currency and period the question meant; currency was
  read only from three-letter words in the label (not "€", "£", "₹", "C$", nor the help text);
  only an annual period was checked; an expectation with no currency or no period was sent as
  "85,000–95,000  per year" or "… USD per None".
- **What changed (`resolver.salary_units`, `_salary`):** the question's currencies (codes,
  signs; a bare "$" names no particular dollar) and periods (year, month, week, day, hour) are
  read from its wording and help text. The expectation needs both its currency and its period
  in Preferences. A question naming another currency, two currencies, another period or two
  periods is the user's answer for this application. A number field gets the amount only when
  the question states both the same currency and the same period; a text field gets the range
  with its own units. Choice lists stay the user's. Never saved (C6).
- **Relocation:** unchanged; only the plain yes/no question is answered from Preferences (S4);
  a question with a place, time, cost or condition is the user's.
- **Sweep (805 forms: the 529 corpus forms with a field about pay, kept to those fields, plus
  276 generated wordings; × 32 contexts, 25,760 rows, against the C8 tree):** 5,476 rows changed, every one a withdrawal of
  a preference-derived answer; the only new values are the user's own typed answers (2,738
  rows); nothing became bankable or draftable. The old code produced 1,244 values with no
  currency or "per None".
- **Unchanged:** `SCHEMA_VERSION` (2) and `RESOLVER_VERSION`; the salary fact reference keeps
  its `version` string (its shape changes once, in C18). Packages with a changed row get a new
  version at their next rebuild and their approval is invalidated.
- **Rejected:** converting currencies or periods (an exchange rate or working hours would be a
  guess); assuming a bare "$" means US dollars; sending a bare number when the question names
  only one of the two units.

## D64 — The review page can change, clear and add answers, and says where the form sends (C12, 2026-10-28)
- **Problem:** once an answer was saved it could not be changed or removed from the review
  page (only answered while unresolved); an optional question nothing in the profile answers
  could not be answered at all; only a resume could be chosen, though the API already took a
  cover letter; and the page did not say where the form would send.
- **What changed:**
  - the package view gains `review` (outside the content, so no hash or approval changes):
    per question `answer_here` (the resolver allows the user's input, it is not a document or
    an unsupported control, and it is asked), `clear` (an answer for this application is
    stored), `document_role`, `not_asked`; and `labels.destination` (a local test fixture, or
    the employer's own site);
  - the page offers "Change answer", "Answer this optional question" and "Clear my answer"
    where those hold, and "Change it in your profile" for a fact that belongs there; sensitive
    questions keep their own card (now with "Clear my answer"); a cover letter can be chosen,
    or "None" for an optional one; the destination card says "Sends to …" and where the form
    itself is when that differs;
  - `PUT /applications/{id}/documents` takes `clear` (`resume`, `cover_letter`); clearing an
    answer and choosing or clearing a document are audited (`application.answer_cleared`
    with a reference to the question, `application.document` with the role and the change).
- **Unchanged:** what can be answered (the resolver decides; protected facts stay in the
  profile), every approval rule (a changed answer is a new package version), `SCHEMA_VERSION`
  (2), no migration.
- **Rejected:** editing a protected fact on this page (one profile, every application stays
  consistent); adding the controls to the package content (a wording change would re-hash
  every package).

## D65 — Approval refusals carry reason codes; revoking stops what it can and says so (C13, 2026-10-28)
- **Problem:** refusals to approve or queue were free text with no fixed code (only the job
  signals and the rehearsal prerequisite had codes). Revoking an approval while its attempt
  waited for a worker left the application "Approved and queued" until a worker picked the
  attempt up and the gate failed it safe (and stuck there while no worker ran); revoking after
  the final click had begun was accepted and recorded as "Revoked by you" on an approval that
  had already sent; and the page said only "Approval revoked." whatever had happened.
- **What changed:**
  - `package.APPROVAL_REASONS`: nine fixed codes (`package_changed`, `package_unresolved`,
    `approval_other_scope`, `approval_needed`, `already_confirmed`, `submission_in_progress`,
    `attempt_running`, `attempt_being_claimed`, `revoke_in_flight`), each message ending
    "(reason: code)"; `docs/approval-reasons.md` lists exactly these (checked by a test);
  - `execution.service.stop_for_revoke`, under the cancel lock order (the attempt, then the
    application): an attempt no worker has taken is cancelled at once and the application
    waits for an approval again; one a worker holds before the send gate is left to the gates,
    which refuse the revoked approval; after the send gate revoking is refused
    (`revoke_in_flight`) and the approval stays as it was;
  - `package.revoke` is audited with `queued_attempt` (`none`, `cancelled`, `stopping`); the
    revoke reply carries `revoke_effect`, and the page says what was stopped. The approval note
    says what revoking can and cannot stop.
- **Evidence:** `tests/test_approval_reasons.py` (each code produced by its path; revoke before
  a worker, while a worker holds the attempt, after the final click; cross-tenant), two
  deterministic races in `tests/test_lock_order.py` (a revoke waiting for a claim, and for the
  send gate), and `frontend/e2e/approval-revoke.spec.ts`.
- **Changed test:** `test_execution_failures.py::test_revocation_before_claim` now expects the
  attempt cancelled by the revocation itself rather than failed safe later by the gate; it still
  asserts that nothing was disclosed or accepted, and now also that a late delivery does nothing.
- **Unchanged:** the gates and their lock order; nothing after the send gate is ever retried or
  recalled; `SCHEMA_VERSION` (2); no migration.
- **Rejected:** letting a revocation cancel an attempt a worker already holds (the worker would
  lose its fence mid-step; the gates already stop it at the next one); accepting a revocation
  after the send gate (it would claim to stop what may already have been sent).

## D66 — A read-only diff between package versions (C14, 2026-10-28)
- **Problem:** the version history listed "answers changed: question_7004" (the posting's own
  field keys) and an invalidated approval said only why; the user could not see what changed
  since they approved.
- **What changed:** `GET /api/applications/{id}/package/diff?from_version=&to_version=` (by
  default the latest stored version and the one before it) compares two stored versions in the
  review page's words: each question by its label, with the shown value before and after and
  what changed (the answer, the question itself, or only the facts behind it; added or
  removed); documents by their shown name; consent choices; the destination's title, employer,
  addresses and form version. Fact references, hashes of facts and record versions are never
  shown. The review page offers "What changed in vN" on each history row and "What changed
  since you approved vN" on an invalidated approval.
- **Read-only:** the diff never builds, approves or records anything (tested by counting
  package versions and audit rows, including when a version is pending); it compares only
  stored versions, and the review page loads the current one first. Owner-scoped: another
  user's application is 404.
- **Unchanged:** the package content and its hash, the history's own summary, approvals.
- **Rejected:** diffing the raw JSON (fact references and keys are not the user's words);
  building the current version from the diff endpoint (a read would then write).

## D67 — Freehire contract hardening: what counts as a change, and waiting when asked (S6, 2026-10-28)
- **Problem:** the record fingerprint covered Freehire's whole response, including `reality`,
  view and application counters and enrichment metadata that change between reads, so nearly
  every refresh counted as "updated". A `429` ended a run but nothing stopped the user's next
  request from arriving before the source's `Retry-After`. A referral code (`referral-code`)
  survived URL canonicalization and could defeat URL deduplication. Discover had no refresh
  control.
- **What changed:**
  - `provider.freehire_fingerprint` covers only the documented fields NoEfforts reads
    (`FREEHIRE_READ`, and from `enrichment` only `FREEHIRE_ENRICHMENT_READ`); `reality`,
    counters, enrichment metadata and undocumented fields (`last_seen_at`, `ghost`,
    `auto_apply_available`, `direct_apply`) never make a change. The local mock is unchanged.
  - A per-user "not before" time (`discovery_backoffs`, keyed by user and provider) is stored
    from a `429`'s `Retry-After` in seconds (at most a day). Until then that user's imports and
    single-record refreshes are refused with `429` and a typed `rate_limited_wait`
    ("… Nothing was sent."), before any request and before a live run approval is used. Nothing
    re-runs by itself; without a `Retry-After` in seconds, or after an outage, no wait is
    assumed. Other users are not held back. Watches keep their own backoff (D56).
  - `referral-code` and `referral_code` join the tracking parameters dropped for deduplication;
    the stored job address keeps them.
  - Discover offers "Refresh from source" on each listing: it re-reads that one record (never a
    live read, D55) and says whether it is unchanged, changed (the user's job is not changed) or
    no longer at the source.
- **One-time effect:** a record stored before this change carries a whole-record fingerprint, so
  its first read afterwards counts once as changed (with no changed fields listed). Only test
  data exists; no record outside tests is affected.
- **Kept as is:** manual imports stay inside the request, bounded by the page limit and
  timeout, rather than moving to a background job. Watched searches already run in the
  background (D56); a background manual import would add a second path to the same budget and
  approval checks for no gain at the page limits in force.
- **Discovery access:** the owner allow-list (D55) limits the reads that reach Freehire (live
  runs and watches). Fixture and mock providers serve local synthetic data and stay available
  to every account in development and tests.
- **Evidence:** `tests/test_freehire_discovery.py` (`fh_reality_tick` refresh and import
  unchanged while a real change is still seen; tagged and referral URLs give one key; an
  aggregator address is an unknown ATS and a manual handoff; the 2026-10-26 undocumented
  fields change nothing; an import or refresh before `Retry-After` is refused and sends
  nothing; no wait without `Retry-After`), `tests/test_freehire_live_read.py` (a held-back run
  leaves its approval unused), `tests/test_migrations.py` (the table added and dropped alone),
  `frontend/e2e/discovery.spec.ts` (the refresh control and the wait).
- **Unchanged:** never waiting or retrying inside a run; the live-read gate (D55); watches (D56);
  `SCHEMA_VERSION` (2).
- **Rejected:** sleeping until `Retry-After` and retrying (a retry the user did not ask for);
  a global backoff shared by all users (one user's refusal would block everyone).

## D68 — Drafting hardened before any provider exists (C15, 2026-10-29)
- **Problem:** no drafting provider is configured, but the checks a future one would face had
  gaps. A number in the job text or the question counted as grounded, although the employer
  wrote it. Nothing stopped a draft from stating authorization or sponsorship ("I will never
  need sponsorship") or a sensitive attribute ("as a woman and veteran"). Accepting a draft
  checked only that the cited facts still existed: a fact edited in place, a reworded question
  or a question that had become sensitive did not stop it, and a bad stored value was a 500.
  A rejected draft could not be rejected by the user at all, an accepted cached draft was
  returned without saying so, and the page did not show what a draft relied on.
- **What changed:**
  - `drafting.validate_draft`: numbers only from the facts the draft cites; a mention of work
    authorization, sponsorship or immigration status is `legal_status`, and a demographic or
    sensitive topic (the C5 vocabulary, the legacy list, and self-descriptions such as "as a
    woman") is `sensitive_topic`, through `classify.mentions_legal_status` and
    `classify.mentions_sensitive`. Both err towards refusing: "in the age of AI" is refused,
    and the user writes the answer.
  - `drafting.prompt` is the only presentation a provider may use (R11.9): fixed rules, then one
    JSON document in which the question, help text, employer, title and job text are quoted
    strings under `untrusted`. The facts are the user's approved facts, chosen before the job
    text is read.
  - A draft records the hash of its cited facts (`answer_drafts.grounding_hash`). Accepting
    refuses, with a reason code, a rejected draft (`draft_rejected`), a question that can no
    longer be drafted (`not_draftable`), cited facts that changed or were withdrawn
    (`draft_facts_changed`), any other change to what the draft was made from: the question,
    its help text or length, the job text or the facts (`draft_inputs_changed`), and a value
    that no longer fits (`draft_does_not_fit`, a 409, not a 500). Accepting is audited
    (`draft.accepted`, by reference).
  - `POST /applications/{id}/drafts/{draft_id}/reject`: the text is erased at once, the row
    kept only so the draft is never offered again (audited `draft.rejected`, `by_user`). An
    accepted draft is the user's answer and is changed or cleared instead.
  - Requesting a draft for unchanged inputs returns an accepted one with its status, and the
    page says so. Drafts are listed in the order they were made, each with the facts it cites
    as they are now (a changed one is shown without its text).
- **Unchanged:** `get_provider()` returns None: nothing is drafted in any environment, and
  nothing leaves NoEfforts. Drafting stays unavailable for sensitive and legal-status questions
  and their follow-ups; `SCHEMA_VERSION` (2).
- **Migration:** `d1e3ab560050` adds the nullable `grounding_hash` and makes `text` nullable;
  downgrade deletes the erased rows first.
- **Evidence:** `tests/test_drafting.py`; the test double in `tests/test_preparation.py` now
  cites every fact it was given (numbers must come from cited facts);
  `frontend/e2e/drafts.spec.ts`.
- **Rejected:** allowing a sensitive or legal-status mention when a cited fact contains it (it
  would let prose disclose what only a consented answer or a protected fact may); comparing only
  the cited facts at accept (a reworded question would pass).

## D69 — Credentials as grounded facts (C16, 2026-10-29)
- **Problem:** the profile's credentials (name, issuer, issued and expiry dates, approval) were
  never offered to a draft, so a draft naming a licence could rest only on an employment title
  or description ("Licensed Practical Nurse at …") or on nothing. Answers to licence and
  certification questions were saved for reuse like any durable fact, although a licence can
  lapse and the profile records when it expires.
- **What changed:**
  - `drafting.grounding_facts` adds the user's approved credentials that have not expired (no
    expiry date: not expiring), as `credential:<id>` facts with the name, issuer and expiry.
    Proposed, rejected, expired and other users' credentials are never offered.
  - `validate_draft` refuses a draft that names a licence, certification or credential unless
    it cites a credential fact (`uncited_credential`): never one read into a job title, an
    employment description or the job text.
  - The bank scope gains `credential` (`bankscope.C_CREDENTIAL`: licence, licensed,
    certification, certified, certificate, credential, board-certified in the label or help
    text). It is checked after every other family, so it only narrows: a wording another
    family refuses keeps its category, and 48 wordings of the table that were reusable are now
    answered for each application ("Do you have a driver's license?", "Which certifications do
    you hold?"). Saving one returns 400, and a saved answer to one is shown as not reused.
  - Accreditation is not in the family: it is about institutions, not the candidate.
- **Tests:** `tests/test_credentials.py`; `tests/bank_scope_wordings.json` (48 rows now
  `credential`, four witness rows added so that each family's use stays proven without a
  credential word, since the old witnesses for T_VALID and L_PLACE were licence questions).
- **Older tests that used a licence as a reusable example**, found by the full run: the C3-C5
  control "Are you certified in managing cardiac arrest?" now carries a C16 delta beside C6's
  (`C16_DELTA`, checked by the same only-narrows test); the C6 controls "Do you have a driver's
  license?" and "Are you CPR certified?" are now C16 controls that are never reused; the
  resolver's "bound to its question" example and two legacy-corpus controls (R8.11) are
  reworded to questions about experience, which keep what they test (exact wording reused,
  capitals and option order ignored, another wording not reused), and the licence wording is
  checked as refused beside them.
- **Unchanged:** the resolver answers no licence question from the profile (a credential is not
  matched to a question by name), `SCHEMA_VERSION` (2), no migration.
- **Rejected:** answering "Do you hold a … licence?" from the credentials list (matching a
  posting's name for a credential to the user's needs its own rules and tests; the user answers
  until then); allowing a credential named in an employment description (the description is
  the user's prose, not a dated, approved credential).

## D70 — Deleting documents (C17, 2026-10-29)
- **Problem:** an uploaded document could never be deleted: every version stayed, with its
  file, until the account was gone, and there is no account deletion yet.
- **What changed:** `DELETE /api/documents/{id}` deletes that version, and with
  `scope=lineage` every version of the document. The rows go, with any application's choice
  of them (that application's package is rebuilt without the document and asks for one
  again), and then the files, after the commit (a failed commit keeps both). Audited as
  `document.delete` with the scope and the count. The Documents page offers "Delete" (with a
  confirmation) and "delete this version" in the history.
- **Never while needed:** refused with a reason code while a live approval's package names one
  of the versions (`document_in_approval`: revoke it first) or an attempt still running on such
  a package (`document_in_attempt`). The check runs under the locks of every application whose
  package names one of them, in id order, the lock that approve, revoke, claim and the gates
  take: an approval in progress makes the deletion wait and then refuse (a race test).
- **Retention limit:** package versions are immutable approval evidence, so a past one keeps
  what it recorded: the id, version, size, type, digest and the name it showed. The file and
  the document row are gone.
- **Deferred to C18:** a `needs_consent` row still carries its proposed display in the
  package content; removing it changes content and belongs in the one schema bump.
- **Unchanged:** uploads, versions and downloads; `SCHEMA_VERSION` (2); no migration.
- **Rejected:** deleting a document an approval names and invalidating the approval (an
  approval the user gave should end only by the user's revocation or a change they see);
  scrubbing names from past package versions (it would rewrite evidence approvals were given
  on).

## D71 — The one SCHEMA_VERSION=3 change (C18, 2026-10-29)
- **Announced:** `SCHEMA_VERSION` is now 3. Every package is rebuilt at its next load with a new
  hash, so **every approval given before this change is invalidated** and must be given again.
  Only synthetic test data exists; no real application is affected.
- **Why one bump:** each of these changes the package content; together they cost one round of
  re-approval instead of five.
- **What changed:**
  - Preference facts are referenced by their value: relocation and salary carry it under
    `value`, which the content hash covers. Under 2 it sat under `version`, which the hash
    leaves out, so a salary range change that left the sent minimum alone kept the approval.
  - Each package document says where it came from: `origin`, and for a generated document its
    `base_document_id`, `grounding_hash` and `accepted_at` (new nullable columns, migration
    `c14a371a79e8`). A generated document nobody accepted is never chosen (409
    `document_not_accepted`), proposed or sent.
  - A file field's `accept` attribute is enforced: a document it does not take (a TXT file in a
    ".pdf,.docx" field) is a checkpoint that asks for another one.
  - The only resume, proposed by NoEfforts, is explained as proposed; a chosen one as chosen.
  - An answer awaiting consent is never written into a package version: its value and display
    are empty there, and the review page reads the proposal from the live answer or saved
    answer (`review[key].proposed`, outside the content). "Include this answer" digests that
    live proposal (C7's binding). Package versions are kept, so a sensitive answer the user
    never included no longer stays in their history.
- **Evidence:** `tests/test_schema_v3.py`; `tests/test_package_contract.py` (shape 3 recorded
  beside shape 2, which is unchanged); `tests/test_disclosure_ledger.py` reads the proposal from
  the review controls; the C3-C5 pinned salary control records its reference by value
  (`C18_DELTA` in `tests/test_question_safety.py`; the answer sent is unchanged).
- **Unchanged:** what is sent for a resolved answer; resolver and classification; execution.
- **Rejected:** several smaller bumps (each would invalidate every approval again); rewriting
  stored versions in place (they are the evidence approvals were given on).

## D72 — Profile facts proposed from a resume (L1, 2026-10-29)
- **Problem:** a user with a resume retyped their work history, education and licences into the
  profile by hand; the `resume_parse` provenance existed but nothing produced it.
- **What changed:**
  - `documents/extract.py` reads text from a PDF (`pypdf`, at most 10 pages), a DOCX (the
    standard library: the document part only, refused above 5 MB unzipped) or a TXT file, cut
    at 60,000 characters. An encrypted, unreadable or empty file gets a reason code
    (`encrypted`, `unreadable`, `no_text`, `too_large`, `unsupported`). The text is not kept.
  - `profiles/resume_parse.py` (pure, no LLM) proposes only what the text states in a
    recognisable layout under a section heading: work entries ("Title at Employer",
    "Title — Employer") with their bullet lines, education entries, and licences or
    certifications with an issuer and an expiry written as a full date.
  - `POST /api/documents/{id}/propose-facts` creates each as a `proposed` record
    (`resume_parse`); one already in the profile is not proposed again. Audited as
    `document.facts_proposed` with counts. The profile page marks proposed records ("Proposed
    from your resume … Not used until you approve it") with an Approve button, and gains the
    Licences and certifications card C16 needed.
- **Never proposed:** work and education dates (a written range stays in the description, as
  written), whether studies were completed (unknown), an expiry not written as a full date,
  anything about work authorization, sponsorship or immigration status, and any line touching
  a sensitive topic (classify, as for drafts): such lines are skipped and counted.
- **Nothing uses a proposal:** answers, drafts and packages read approved records only (C15,
  C16), so a proposal changes nothing until the user approves it.
- **New dependency:** `pypdf` (pure Python, BSD), `>=5.1,<7`, locked at 6.21.4. Chosen over
  writing a PDF parser; it reads only the first pages of a user's own upload.
- **Evidence:** `tests/test_resume_facts.py` (synthetic PDF, DOCX and TXT files built in the
  test); `frontend/e2e/documents.spec.ts`.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.
- **Rejected:** an LLM to read resumes (a resume is applicant information, and no provider or
  consent screen exists, L4); guessing month and day for "2019 – 2022".

## D73 — Tailored resumes and cover letters, through the provider only (L2, L3, 2026-10-29)
- **Problem:** the plan's L2 (a resume tailored to each application, with a diff, accepted
  before use) and L3 (a grounded cover letter, reviewed before use) had nowhere to live, and
  C18 had only prepared the document fields.
- **What changed:**
  - `POST /api/applications/{id}/generated-documents` (`resume` or `cover_letter`) asks the
    drafting provider for the text, built by `generation.request_for` from the user's approved
    facts and the job's own text (C15's quoted, untrusted data), never from the base resume's
    text. The result passes every draft check (C15, C16) and a length limit (6,000 or 3,500
    characters); one that fails is discarded and audited with its code only.
  - It is stored as a DOCX (`generation.docx_bytes`, the text escaped), `generated`, written
    for this application, with the ids and the hash of the facts it cites, and its base resume
    for a tailored resume. The review page shows its text, the facts it cites, and for a
    tailored resume the lines changed from that base; Accept or Reject (reject deletes it and
    its file).
  - It can be chosen only once accepted, only for the application it was written for, and only
    while the facts it cites are unchanged (`generation.refusal`: `document_not_accepted`,
    `document_for_another_application`, `document_facts_changed`). A chosen document that stops
    being usable makes the row a checkpoint that says why: another document is never put in
    its place (found by a test: the only uploaded resume used to be proposed instead).
- **No provider:** `drafting.get_provider()` still returns None, so the endpoint answers 503
  ("not configured") and nothing is generated or sent anywhere. L4 adds a provider; it needs
  server-side credentials, a cost budget and a consent screen showing what leaves the system,
  which are the owner's decisions.
- **Evidence:** `tests/test_generated_documents.py` (a labelled test double as the provider);
  `frontend/e2e/generated.spec.ts`.
- **Unchanged:** `SCHEMA_VERSION` (3); migration `60e18e9115c8` adds two nullable columns.
- **Rejected:** feeding the base resume's text to the provider (it is not an approved fact and
  could carry claims the profile does not hold); a PDF writer (a DOCX is enough for the fields
  that take documents, and is read back by L1's extractor).

## D74 — Claude as the drafting provider, built and off: owner account, consent to the exact text, a daily budget (L4, 2026-10-29)
- **Problem:** L4 (a real drafting provider) was the last plan step. Drafts, tailored resumes
  and cover letters (C15, L2, L3) had every check in place but nothing to write them, and the
  brief forbids sending applicant information to an external AI service unless the product's
  explicit configuration and consent cover it. Credentials, a cost budget and the consent
  screen were recorded as the owner's decisions.
- **Decision:** build the provider and every gate around it, with each of the owner's decisions
  left as a switch that is off by default, as S7 (D55) did for the live Freehire read. Nothing
  is sent until the owner turns it on and the user agrees in the app.
- **What changed:**
  - `preparation/anthropic_provider.py`: Claude through Anthropic's Messages API and the official
    SDK. One request per draft: `drafting.prompt`'s rules as the system
    prompt (plus one sentence naming the two output fields), the facts and the quoted employer
    text as one JSON user message, the answer constrained to JSON `{text, evidence}`, then
    checked like every draft. Model `claude-opus-5-5`, effort `medium`, `max_tokens` 16,000; no
    sampling parameters, tools or retries (`max_retries=0`). The API host must resolve to
    public addresses only before each request (R10.5).
  - `get_provider()` returns it only when `NOEFFORTS_DRAFTING_PROVIDER=anthropic`,
    `NOEFFORTS_ANTHROPIC_API_KEY` is set (a `SecretStr`; an ambient `ANTHROPIC_API_KEY` is never
    used) and the model's price is listed. `provider_for(db, user)` then hands it out only when
    (`drafting_access`): the account is in `NOEFFORTS_DRAFTING_OWNER_EMAILS` (a personal
    prototype, never multi-user); the user agreed to `CONSENT_TEXT` exactly as it is now (its
    digest is stored; a changed text needs a new agreement) and has not withdrawn; and the
    day's spend is under `NOEFFORTS_DRAFTING_DAILY_BUDGET_USD` (default 0: nothing is sent).
  - The budget: each request reserves its worst case (every input character as a token, since
    the JSON is ASCII, plus `max_tokens` of output, at the listed price) under one advisory
    lock before it is sent, in its own committed transaction; the reservation becomes the cost
    the API reports. A timeout or a lost connection keeps the worst case (the work may have
    been done); an API error status costs nothing. Ledger: `drafting_usage` (numbers and codes
    only). Migration `452ae3b5aec9` adds it and `drafting_consents`.
  - The consent screen is the profile page's AI drafting card: what each request holds (approved
    summary and skills, approved work history, education and unexpired credentials, the
    question, the employer, the title and up to 6,000 characters of the job description), what
    it never holds (contact details unless the user wrote them into a fact, work authorization,
    sponsorship, residence, nationality, salary, relocation, demographic answers, documents,
    anything unapproved), that Anthropic's handling follows the owner's API account, and the
    day's spend. `GET/PUT/DELETE /api/drafting/consent`; audit `drafting.consent_given`
    (the digest) and `drafting.consent_withdrawn`.
  - A provider failure keeps nothing it returned: 502 with a fixed code (`provider_refused`,
    `provider_incomplete`, `provider_unparseable`, `provider_timeout`, `provider_unreachable`,
    `provider_error`, `provider_destination_refused`), audited as `draft.provider_failed` or
    `document.generation_failed`. Refusals before sending: 409 `drafting_consent_needed`,
    503 `drafting_not_for_this_account` or `drafting_budget_reached`; the review page says
    which, with a link to the profile card.
  - Any class in `app/` with a `draft` method must set `external = True`, which puts it behind
    these checks (a static test); local test doubles do not, and send nothing.
- **Not turned on:** no key exists in the repository or the sandbox, no request was made to
  Anthropic, and the defaults send nothing. Turning it on is the owner's step: set the provider,
  the key, the owner account and a budget, then agree in the app. The consent wording is
  written for the owner's own use; showing it to anyone else is a legal and consent decision
  that stays with the owner.
- **Evidence:** `tests/test_drafting_provider.py` (a stub SDK client returning the SDK's own
  `Message` type, and a stub resolver); `frontend/e2e/drafting-consent.spec.ts`;
  `tests/test_migrations.py::test_l4_adds_drafting_consents_and_usage_and_downgrade_drops_only_them`.
- **New dependency:** `anthropic` (Apache-2.0), `>=2.3,<3`, locked at 2.3.0, with `httpx2` and
  `httpcore2` (BSD-3-Clause), `jiter`, `docstring-parser`, `truststore` (MIT) and `sniffio`
  (MIT or Apache-2.0). Imported only when the provider is configured and a request is made.
- **Unchanged:** `SCHEMA_VERSION` (3): nothing in a package changes.
- **Rejected:** Anthropic's server-side fallback to another model (the budget is priced for the
  configured model, and a declined draft means the user writes it); SDK retries (a timed-out
  request may already have been billed); a per-request estimate from the token-counting
  endpoint (a second request that also sends the applicant's facts); multi-user access (D34,
  D55).

## D75 — One synthetic journey through the whole product; a test-only local drafting provider (2026-10-29)
- **Problem:** each step had its own tests, but nothing showed that the steps join up through
  the real UI: a broken hand-off between two pages would pass every module test. Tailored
  documents could not be part of such a journey either, because the only real provider is off
  (D74) and the e2e server cannot be patched like a backend test.
- **Decision:**
  - `frontend/e2e/journey.spec.ts` walks one synthetic journey through the real UI, API, Celery
    worker and receiver (desktop and mobile):
    - register;
    - facts and preferences kept apart;
    - a TXT resume proposes facts, approved one by one;
    - Freehire-shaped discovery from the receiver's stand-in, where a listing repeated by the
      source becomes one job and a second search adds nothing;
    - the job page explains preferences apart from eligibility;
    - the form is captured;
    - the three unknowns become checkpoints and approval is impossible until they are answered;
    - a tailored resume is read, accepted and chosen;
    - a disclosure-only rehearsal (one upload, nothing accepted);
    - a separate approval to submit;
    - a profile fact changed after that approval invalidates it and shows the change;
    - approve again, submit, receipt;
    - the receiver's ledger shows exactly one acceptance, with the changed fact and the tailored
      DOCX byte for byte;
    - preparing again opens the same application, and the API refuses to queue it again;
    - the tracker shows the receipt, links back to the application, and records an outcome on
      the timeline;
    - a job on a real Greenhouse host (never contacted) is refused and offered no test-only form
      control.
  - `preparation/fixture_provider.py`: a labelled local test double that writes the cited facts'
    own text, used only when `NOEFFORTS_ENV=test` and the account matches
    `NOEFFORTS_DRAFTING_TEST_FIXTURE_USERS` (fnmatch; the e2e server sets `journey.*@example.com`).
    It sends nothing anywhere, and its drafts pass every draft check. The static guard now allows
    exactly two provider classes: the external one (`external = True`) and this one.
- **Found by the journey and fixed:**
  1. After a form was captured, the job page's "How NoEfforts could apply" still said "Capture
     the application form first" until "Check again" was pressed. It now reloads whenever a form
     is captured.
  2. After a tailored resume was accepted, the page said "Choose it above", but the resume
     choice did not list it until the page was reloaded. Documents are now read again with the
     package.
  3. The tracker gave a submitted application no link back to its review page, where the
     package that was sent and its receipt are. It now links every application past the
     tracked-only state.
  4. Also changed: a job on a real employer's site no longer offers the test-only form controls,
     which could only fail. It says to apply on the employer's site and track it.
- **Not changed:** an invalidated approval shows "Submit approved package" disabled, not hidden;
  that is the existing design, and the journey asserts that it is disabled.
- **Open UX gaps found:** work history, education and licences can be added and removed in the
  page but not edited (the API can; `docs/remaining-work.md` row 16).
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.

## D76 — Owner deployment readiness: checked secrets, a health-gated start, a tested backup and restore (priority A, 2026-10-29)
- **Problem:**
  - Compose started the worker and the web app as soon as the API container existed, possibly
    while migrations were still running.
  - The API had no health check, so "running" did not mean "migrated and answering".
  - `.env.example` holds placeholder runner and proxy tokens that would start a stack.
  - There was no written backup, upgrade or rollback procedure. The obvious restore
    (`pg_restore --clean`) leaves tables that only a newer version had, and the older version's
    migrations then fail.
- **Decision:**
  - `docker-compose.yml`:
    - The API has a health check (`/api/health`, which reads the database; probed without any
      proxy so a Docker Desktop proxy setting cannot route it).
    - The worker and the web app start only once the API is healthy. The API starts only after
      `alembic upgrade head` succeeds (`backend/Dockerfile`), so healthy implies migrated.
  - `scripts/check_env.py` (standard library only, so it runs with a Mac's system `python3`):
    - refuses a missing, empty, placeholder, too short or reused secret;
    - warns about the default database password and about every switch that contacts an
      outside service;
    - prints key names only, never a value.
  - `scripts/verify-local.sh`: the checker, `docker compose config`, then the smoke test as a
    throwaway Compose project. It stops if the stack's ports are in use, so the owner's own stack
    and data are never touched.
  - `docs/deployment.md`: the owner's guide to start, health, backup, upgrade, rollback, stop
    and verify. Rollback drops and recreates the database before restoring.
  - The CI smoke job runs the same backup and restore commands: back up, create a second
    account, restore, then the first session works and the second account is gone.
  - `backups/` is git-ignored, and the repository hygiene test refuses a backup folder or a
    `.dump` file.
- **Not claimed:** the stack has not been run on the owner's Mac or on arm64. The sandbox did not
  build images: they need a TLS proxy certificate that the real images must not carry. The CI
  jobs are the build evidence.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; no new outbound path.

## D77 — Full data export and account deletion; the retention decision isolated (priority B, 2026-10-29)
- **Problem:** the only export was the jobs list, and an account could not be deleted. Deletion
  touches queued and running submissions, document files, sessions, audit events and backups.
  Whether anything should be kept afterwards is a policy decision NoEfforts has not been given.
- **Decision (export):**
  - `GET /api/account/export` returns one ZIP: every record that names the account, table by
    table, every document file named by its id, and a README of what was left out and why.
  - Only columns listed in `account/export.py` are read. A table or column added later is not
    exported until it is listed or left out with a reason, and a test fails until then.
  - Left out:
    - login and session secrets;
    - keyed references and digests (HMACs under the server's key), also inside JSON values;
    - worker lease and fencing internals, and a verification code;
    - where files are stored, and two internal tables.
  - Scoped to the account; audited as `account.export` with counts only.
- **Decision (deletion):**
  - `POST /api/account/delete` needs the password and the phrase "delete my account". It
    deletes the account row; the cascade, checked in the migrated database, removes every row
    that names the account. Files are removed after the commit, and the session ends at once.
  - Lock order (`docs/architecture.md`): the account's watches, then its active attempts, then
    its applications, and the account row last. A deadlock is retried once.
  - A submission past the send gate (`sending`, `awaiting_code`) refuses deletion
    (`deletion_submission_in_flight`) and nothing is deleted. Earlier work is deleted: a queued
    message finds no attempt, and a worker holding an attempt is fenced out before the send
    gate. Nothing is retried.
  - `account/policy.py` isolates the retention decision. Default: nothing kept in the database
    (not even audit events), no grace period. Outside NoEfforts' reach, and listed before
    deleting: the employer's copies, backups, logs (no applicant data by design), an AI
    provider's copies.
- **Not done:** no deletion was run against a real account; the tests use synthetic accounts. No
  legal retention policy was written.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.

## D78 — Saved answers edited as versions with their history; a document's text previewed as data; profile records edited in place (priority C, 2026-10-29)
- **Problem:**
  - A saved answer could only be deleted and saved again from an application, which lost what
    it had been.
  - A document could only be downloaded, not checked in the page.
  - Work history, education and licences could be added and removed, but not edited (D75 gap).
- **Decision (saved answers):**
  - `PUT /api/answer-bank/{id}` changes only the answer. The question it is bound to (wording,
    help text, options seen) stays, so the edit is reused exactly where the saved answer was.
  - The value is checked against the answer's shape and, for choices, against the options saved
    with it. A field's own limits are checked when it is reused; if it no longer fits, it
    becomes a checkpoint there, never a guess.
  - Each change is a new version, and each version is kept in `fact_versions` (entity
    `answer_bank`): "saved from an application", "edited by you", or "as first recorded" for a
    version saved before history was kept. `GET /api/answer-bank/{id}/history` lists them.
  - Packages cite the saved answer by id and version. After the edit commits, every
    application whose current package cites it is rebuilt, and its approvals are invalidated
    with the reason. That keeps the lock order: the saved answer's row is released before any
    application is locked.
  - An application that execution owns is not rebuilt; its gates refuse the stale hash
    (`test_every_protected_mutation_stops_a_running_attempt[answer_bank_edit]`). Audited as
    `answer_bank.edit` with the version only.
- **Decision (preview):**
  - `GET /api/documents/{id}/preview` returns the text NoEfforts reads from the file (the
    bounded extractor of L1), at most 20,000 characters, as JSON.
  - The page shows it in a `<pre>` as text. No viewer, no HTML, no external request; a file's
    markup is shown, never run.
- **Decision (profile records):** "Edit" loads a work history, education or licence record into
  its form, and "Save changes" updates it through the existing `PUT`. The record gets a new
  version and history, and becomes yours (user-entered, approved).
- **Unchanged:** `SCHEMA_VERSION` (3). A package already citing an answer by version changes
  hash on an edit, as intended; no migration.

## D79 — Explainable match: preferences, eligibility and qualifications kept apart (priority D, 2026-10-29)
- **Problem:** the job page listed only title and location checks against preferences. There
  was no way to see what was checked, what the source says next to your own facts, which of
  your qualifications a job names, or what is unknown. A single "score" would invite reading it
  as a prediction, or mixing facts with preferences.
- **Decision (`jobs/fit.py`, on `GET /api/jobs/{id}` as `fit`):**
  - **Preferences:** title, location, work mode, employment type and pay, and the excluded
    employer. Each is met, not met, not stated by the job, or not set by you. Pay is always
    "not stated": NoEfforts has no pay data and never estimates it. The one number is "m of n
    checked preferences met": a count of your own targets, not a prediction, an interview
    probability or an application-system score.
  - **Eligibility (advisory):** what a source states (sponsorship offered: yes / no / not
    stated, who said it and on what basis), next to your approved tri-state facts per country.
    The job's country is never worked out from its text, and nothing is decided or compared.
    It never changes the preference count (tested).
  - **Qualifications:** your approved skills and approved, unexpired licences that the job's
    text names word for word. It says what is mentioned, never that you qualify.
  - **Missing information** is listed.
  - Nothing filters, hides, ranks down or submits a job because of this. A test reads every
    sentence the module can show and refuses words such as probability, chance, likely,
    eligible, qualified, guarantee or interview.
- **Kept:** the older `explanations` list stays in the API for existing clients; the page shows
  `fit`.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; no new data source.

## D80 — A Lever-shaped form, checkpoint-first; the generic extractor never types into a picker or past a bot check (2026-10-29)
- **Problem:** `docs/research/lever.md` documents traps the generic HTML extractor did not
  see. The Current location field is a search-as-you-type picker that can raise an hCaptcha,
  and the university field is a picker too. The extractor read such inputs as text boxes the
  resolver could fill, and it did not see a CAPTCHA on the page at all.
- **Decision:**
  - The generic extractor (`forms.extract_form_schema`, now `html-v2`) reads an input with
    `role="combobox"` or `aria-autocomplete` as unsupported. A required one blocks approval;
    an optional one stays blank.
  - On the generic capture path (fixtures and pasted HTML), a CAPTCHA or bot-check widget
    found by its vendors' documented markup (`g-recaptcha`, `h-captcha`, `cf-turnstile`, and
    their script or iframe sources) adds a required unsupported field, "A bot check (CAPTCHA)
    on this form". Approval then waits, and the user applies on the employer's site.
  - The Greenhouse paths keep leaving CAPTCHAs to their adapters, which stop when one appears.
  - A new fixture, `preparation/fixtures/lever.html` ("lever"), carries the search-reported
    Lever shapes. Its tests check each trap the research lists:
    - location and university pickers stay blank;
    - the licence number and preferred shift wait for the user;
    - both consents need the user's choice;
    - EEO answers are never inferred;
    - authorization comes only from an approved fact, and unknown stays unknown;
    - the bot check blocks approval even with everything else answered;
    - the route stays a manual handoff ("Lever: planned adapter only").
- **Deliberate version change:** `forms.EXTRACTION_VERSION` `html-v1` → `html-v2`, and with it
  the fixture adapter's version (`fixture-ats-1+html-v2`). An approval bound to the earlier
  version asks again; the historical `LEGACY_VERSIONS` entry is unchanged.
  `greenhouse-hosted-1+greenhouse-v1` is unchanged: its DOM side can now only refuse more (a
  picker no longer matches a text field), never accept more.
- **Not done:** no Lever adapter, no request to any Lever host; the shapes stay search-reported
  until a real page is observed under the provider-admission rules.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.

## D81 — Workday- and Ashby-shaped forms, checkpoint-first; Ashby embeds recognised fail-closed; passwords and custom widgets never dropped or filled (2026-10-29)
- **Problem:**
  - Workday's search-reported wizard has an account gate (password fields), custom dropdowns
    and switches built from ARIA roles, pickers and legal attestations.
  - Ashby renders Yes/No questions as buttons, uses a location picker, and embeds postings on
    employer sites as `?ashby_jid=<uuid>`.
  - The generic extractor read a password input as a text box, which an answer could fill and
    store. It dropped ARIA widgets with no native input entirely: a required question could
    vanish from the package. It also did not recognise Ashby embeds.
- **Decision:**
  - The generic extractor (`html-v3`) reads a password input and an `autocomplete=one-time-code`
    input as unsupported: NoEfforts never asks for or keeps a password or a code. A required
    one blocks approval, so an account gate means you apply yourself.
  - An ARIA widget (`radiogroup`, `switch`, `combobox`, `listbox`, `textbox` and others) with
    no native control inside becomes an unsupported field, required when
    `aria-required="true"`. It is never dropped.
    - A listbox that a combobox owns (`aria-controls` / `aria-owns`), and a radio inside a
      counted group, are part of that one control.
    - Hidden widgets are skipped, as hidden inputs are.
  - The fixture adapter re-extracts at execution with bot-check detection, so a CAPTCHA that
    appears after approval is a changed form and stops the attempt.
  - `detect_ats`:
    - `ashby_jid=<UUID>` on a non-ATS host is Ashby (company unknown).
    - A non-UUID value, or `gh_jid` and `ashby_jid` together, is unknown: two ids cannot be
      told apart, so neither is believed.
    - Vendor host rules still win.
    - Believing an embedded id on any host is recorded for Ashby under the existing
      `identity_jid_any_host` gap, so no admission stage can be claimed past it.
  - New preparation fixtures `workday` and `ashby` (search-reported shapes). Their tests:
    - the account gate and pickers block or stay blank;
    - eligibility wording that names no country waits for you;
    - sensitive questions are never inferred;
    - both routes stay a manual handoff.
  - `docs/remaining-work.md` gains a provider evidence ladder that names the missing
    integration work per provider.
  - The read-only Greenhouse check's comparison counts custom controls
    (`page_custom_controls`) instead of listing their keys: such a key comes from the page's
    own markup, and its leak guard refused to publish the whole summary when one was listed.
- **Deliberate version change:** `html-v2` → `html-v3`, so the fixture adapter version becomes
  `fixture-ats-1+html-v3`; approvals bound to the earlier version ask again.
- **Not done:** no Workday or Ashby adapter or receiver route; no request to any vendor host.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.

## D82 — The jobs list summarises each job's match explanation (priority B, 2026-10-29)
- **Problem:** the match explanation (D79) was on the job page only; the list gave no sign of
  how a job compares with your preferences and approved qualifications.
- **Decision:**
  - `GET /api/jobs` gives each listed job a `match`: `jobs/fit.summary` of the very
    assessment the job page shows (`fit.assess`), so the two cannot disagree. It holds the
    preference count and its label ("m of n checked preferences met"), which of your approved
    skills and valid licences the job's text names, whether there was text to compare, and how
    many things are unknown.
  - Eligibility is not summarised: shown side by side is the only honest way to show it, on
    the job page. No score, eligibility verdict or probability, and nothing is filtered,
    hidden or reordered.
  - Each row of the jobs list shows that line and links to `/jobs/{id}#match`, the full
    explanation. The account's inputs are read once per page of jobs, not once per job.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration.

## D83 — In-app notifications, derived from the records they describe (priority C, 2026-10-29)
- **Problem:** what happens to an application while you are away (a verification code asked
  for, an approval that stops applying, a rehearsal, a receipt, a stop) was visible only on
  that application's page.
- **Decision:**
  - A feed (`GET /api/notifications`, page `/notifications`, a count in the header), derived
    every time from the authoritative rows: checkpoints, approvals with `invalidated_at`,
    rehearsal records and finished attempts. A notification therefore says what its record
    says now: a code request past its time reads "expired", an attempt's text is its own
    `outcome_detail`, a local test form is labelled as one.
  - One notification per record, by a key that names it. A rejected code opens a new round,
    which is a new notification; an expired or failed request is one too. An approval used up
    by an outcome, a rehearsed attempt, an approval you revoked and an attempt you cancelled are
    not notified apart (their outcome is, or you did it yourself).
  - Read marks are the only stored state: `notification_reads (user_id, item_key, read_at)`,
    unique per user and key, deleted with the user, in the export. Marking a key that is not
    one of your current notifications is 404 and marks nothing.
  - Nothing is emailed, texted, pushed or sent anywhere; a test checks that the module imports
    no network, mail or task library.
- **Small refactor:** `package.REVOKED_BY_YOU`, the one text an approval revoked by you carries.
- **Migration:** `7d2c4e9a1b60` (one table; downgrade drops it alone). `SCHEMA_VERSION`
  unchanged (3).

## D84 — API tokens, then a CLI and an MCP server, read-only first (priority D, 2026-10-29)
- **Problem:** your own scripts and an MCP client could reach NoEfforts only by copying a
  browser session; there was no CLI or MCP surface for an ordinary user.
- **Decision** (design and threat model in `docs/api-tokens.md`):
  - Personal access tokens `ne_<public id>_<secret>`: made in Account → API tokens, shown once,
    stored as a SHA-256 hash, 30 days by default and at most 90, revocable, "last used" to the
    hour. Read from `Authorization: Bearer` only; a request with that header is decided by the
    token alone, never by a cookie next to it.
  - Scopes are allow-lists of (method, route template), checked in `current_user`, default
    deny: `read` (jobs, a job without its eligibility side by side, applications, the funnel,
    an application, notifications) and `import:jobs` (add a job, import a file). Any token may
    read itself (`GET /api/token`). Token management, export and deletion refuse any request
    with an `Authorization` header. Invalid tokens are rate-limited like logins.
  - `scripts/noefforts.py` (CLI) and `scripts/noefforts_mcp.py` (MCP over stdio), standard
    library only, talk to `http://127.0.0.1:8000/api` by default, refuse plain http to any
    other host, take the token from the environment or a `chmod 600` file only, check ids are
    UUIDs before putting them in a path, and never echo what was typed.
  - Nothing reaches review, answers, consent, approval, queueing, submission or codes.
- **Migration:** `9e1f3a7c2d84` (one table; downgrade drops it alone). `SCHEMA_VERSION`
  unchanged (3). Audit: `api_token.create` (scopes, days) and `api_token.revoke`.
- **Not done:** no versioned public API, no third-party clients, nothing exposed beyond this
  machine.

## D85 — A Lever-style adapter against the local receiver, with no Lever identity (2026-10-30)
- **Problem:** the selected milestone was a provider-specific Lever adapter against the local
  receiver. The admission framework admits an adapter that carries an ATS identity to
  `fixture_only` only after the owner's recorded review of that ATS's public documentation and
  terms (`public_doc_reviewed`); none is recorded for Lever (Lever's terms were never seen, see
  `docs/research/lever.md` §5), and only providers registered before the framework may waive it.
- **Decision:**
  - Receiver: `fixtures/ats_receiver/lever_like.py`, a labelled Lever-style approximation (a
    posting page, its form at `/apply`, documents uploaded when chosen, submit, a confirmation
    page with a reference) on the shared ledger, with failure modes: a bot check on the form or
    after the final click, a required location picker, a resume prefill, a changed form, a
    confirmation on another posting, a verification step, validation, errors, a dropped reply,
    and upload failures.
  - Capture: `POST /api/jobs/{id}/form/lever` reads the posting's form page, on a fixture
    origin only, with the generic extractor (Lever's public API lists no custom questions); a
    real Lever posting is refused before any request. Source `fixture_lever`.
  - Adapter `fixture_lever` (`execution/adapters/lever.py`) on the existing framework: opens
    the posting's `/apply` page (the runner refuses a form page off the destination's site),
    uploads documents first, fills only resolved answers, reads back every value and checks
    every field it leaves unanswered is still empty (a parsed resume changing one stops the
    attempt), stops on a bot check, binds the confirmation to its own POST and posting, and
    treats anything else after the final click as an unknown outcome, never resent. All the
    existing approval, rehearsal, cancellation, fencing and quarantine paths apply unchanged.
  - Registered as `fixture_lever` with **no Lever identity** (the generic fixture track, end
    `no_ats_identity`): real Lever jobs keep the `lever` specification's manual handoff
    (`planned_adapter_only`), its rehearsal path is the approximation's site, and a form it
    captured is foreign on any job of an identified ATS (`form_ats_mismatch`).
  - A listed fixture origin counts only when its host is local (loopback, `localhost` or a
    single-label internal name, such as the Compose receiver): listing a public site in
    `NOEFFORTS_FIXTURE_ORIGINS` never makes it a fixture (`urlsafety.local_fixture_host`).
    Superseded by D86: names only if listed exactly, checked again at every connection.
  - The job page gains "Read Lever-style test form".
- **Not done:** no Lever host was contacted; no docs review, observation, credential, real
  upload or submission. The `lever` specification stays `planned`.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration. New adapter version
  `fixture-lever-1+html-v3`.


## D86 — The fixture-origin boundary: exact names, connection-time address checks, test only (2026-10-30)

- **Why:** D85 accepted any single-label host on a listed fixture origin. A DNS search suffix
  can resolve a bare name to a host that is not local, so a name alone proves nothing.
- **Decision:**
  - A fixture origin counts only when `NOEFFORTS_ENV=test` (before: anywhere but production),
    is plain `http`, is listed exactly in `NOEFFORTS_FIXTURE_ORIGINS`, and its host is an
    address literal in standard form that is loopback or on a configured test network, or
    exactly one name in `urlsafety.FIXTURE_SERVICE_HOSTS` (today only `receiver`, the Compose
    service). There is no general single-label rule; `localhost` is not listed.
  - Other spellings of an address (decimal, hex, octal, shortened such as `127.1`) are never
    fixture hosts, and as job addresses they are checked as the address they spell
    (`check_url_syntax`). IPv6 loopback in any standard notation and an IPv4-mapped address
    count as the address they are: mapped loopback is loopback, mapped public is public.
  - Test networks (`NOEFFORTS_FIXTURE_NETWORKS`, and the egress-proxy service's own
    `EGRESS_FIXTURE_NETWORKS`) must lie inside RFC 1918 or IPv6 unique-local space and be at
    most /16 or /48; anything else stops startup. Compose pins the `fixtures` network to
    `10.231.47.0/24` and names it on the API, the worker and the proxy.
  - At connection time every address a fixture host resolves to, and the peer actually
    reached, must be loopback or on a test network: server-side through
    `urlsafety.fixture_opener` / `connect_fixture` (capture, discovery fixture, the read-only
    check's fixture base, the fake API adapter), in the browser through the egress proxy
    (in-process and the service), which now also refuses a fixture host:port resolving to a
    public or link-local address (before: any address was accepted for one) and re-checks the
    peer it reached before relaying a byte.
  - Redirects: the server-side fixture opener follows none and checks every request's origin
    as it is opened; it has no file, ftp or data handler. In the browser every hop leaves
    through the egress proxy, which allows only the destination host:port.
  - A fixture is never browsed without the egress proxy: `isolation=off` refuses it
    (`fixture_needs_proxy`).
- **Found while testing it, fixed:**
  - In `netns` mode the Playwright driver fetched GET and HEAD requests to the destination,
    and opened its WebSockets, itself, from the worker's network: those connections bypassed
    the egress proxy and its address checks (probe: no proxy decision for the destination
    with interception on; one with it off). The driver now never fetches or connects in
    `netns` mode, as already in `container` mode; the browser sends everything through the
    proxy.
  - In `netns` mode Chromium's resolver rule (`MAP * ~NOTFOUND`) also covered its own proxy
    relay on 127.0.0.1, so a named destination could never be reached; only a 127.0.0.1
    destination worked. The relay address is now kept, as the container launcher keeps its
    proxy host.
- **Unchanged:** the browser-egress block, the receiver-only Compose network, the in-process
  interception, every adapter and gate. No migration; `SCHEMA_VERSION` 3.

## D87 — An Ashby-style adapter against the local receiver, with no Ashby identity (2026-10-30)

- **Why:** the next bounded adapter after D85, on the local fixture track only.
- **Decision:**
  - Receiver: a labelled Ashby-style approximation (`fixtures/ats_receiver/ashby_like.py`,
    `/ashby/BOARD/POSTING` with its form on `/application`), built from search-reported
    summaries of Ashby's documentation (no Ashby page could be opened; docs/research/ashby.md):
    `_systemfield_*` system fields, Yes/No questions naming the country, a candidate-location
    picker, files uploaded when chosen, resume autofill (one mode), a cookie banner whose clicks
    are recorded, an optional EEOC survey, a required data consent, and a confirmation page with
    a reference. Every one of those page details is the fixture's own design.
  - Ashby documents a spam score but no widget, so nothing can detect it on a real page. The
    approximation marks its own check (`data-ashby-spam-check`), and `preparation.ashby
    .extract_schema` turns it into the bot-check field: a checkpoint at capture. If it appears
    after approval, the attempt stops before anything is entered. After the final click, a page
    saying the application was flagged, one saying you already applied, a confirmation page
    that also shows a challenge, and anything else that is not this posting's confirmation are
    unknown outcomes: quarantined in `submitted_unconfirmed`, never solved, retried or resent.
  - Capture: `POST /api/jobs/{id}/form/ashby`, on a fixture origin only; a real Ashby posting
    (`jobs.ashbyhq.com`) is refused before any request, and an embed (`?ashby_jid=`) names no
    board. Source `fixture_ashby`. The job page gains "Read Ashby-style test form".
  - Adapter `fixture_ashby` (`execution/adapters/ashby.py`) on a new shared base,
    `execution/adapters/hosted_form.py`, which now also carries the Lever-style adapter's
    mechanics unchanged (files first, readback of unanswered fields, upload evidence after a
    partial failure, the confirmation bound to its own POST and posting, a challenge after the
    click is unknown). The Lever adapter's behaviour and version are unchanged.
  - Registered as `fixture_ashby` with no Ashby identity (generic fixture track, end
    `no_ats_identity`). Ashby has no specification in the registry, so a real Ashby job is a
    manual handoff (`real_destination_disabled`) and nothing the adapter proves counts for
    Ashby.
- **Not done:** no Ashby host was contacted; no docs review, observation, credential, real
  upload or submission.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; `forms.EXTRACTION_VERSION`. New adapter
  version `fixture-ashby-1+html-v3`.

## D88 — A Workday-style adapter against the local receiver, checkpoint-first, with no Workday identity (2026-10-30)

- **Why:** the last bounded adapter of this series (the owner's direction after D87), before
  the next product slice.
- **Decision:**
  - Receiver: a labelled Workday-style approximation (`fixtures/ats_receiver/workday_like.py`,
    `/workday/TENANT/REQ` with its application at `/apply`), built from search-reported
    summaries of Workday's documentation (no Workday page could be opened;
    docs/research/workday.md): an "apply manually" application on one page, files uploaded when
    chosen, a custom dropdown, eligibility and sponsorship naming the country, a licence
    question, voluntary disclosures and a terms acknowledgement, and a confirmation page with a
    reference. Every page detail is the fixture's own design.
  - Checkpoint-first: these never become automation. At capture (`preparation.workday
    .extract_schema`, on top of the generic extractor): a candidate account (passwords), an
    application on several pages (a step marker or "Save and Continue"), values already on the
    page when it loads (a parsed resume or a previous application), a location list that depends
    on another answer, search-as-you-type pickers and custom dropdowns are required unsupported
    fields. After approval, an account gate or several pages stop the attempt before anything
    is entered; a resume parse that fills a field NoEfforts left blank stops it at readback;
    email verification after the final click is an unknown outcome, quarantined, never resent.
  - Capture: `POST /api/jobs/{id}/form/workday`, fixture origins only; a real Workday posting
    (`*.myworkdayjobs.com`, `*.myworkdaysite.com`) is refused before any request. Source
    `fixture_workday`. The job page gains "Read Workday-style test form".
  - Adapter `fixture_workday` (`execution/adapters/workday.py`) on the shared hosted-form base
    (D87). Registered with no Workday identity (generic fixture track, end `no_ats_identity`):
    the `workday` specification stays `planned`, real Workday jobs keep its manual handoff
    (`planned_adapter_only`), and the owner's terms decision on Workday is untouched.
  - This ends the `fixture_<ats>` series: the next work is a product slice from
    `docs/remaining-work.md`.
- **Not done:** no Workday host was contacted; no docs review, observation, account, credential,
  real upload or submission; no page-by-page disclosure (several pages stay a checkpoint).
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; `forms.EXTRACTION_VERSION`. New adapter
  version `fixture-workday-1+html-v3`.
- **Correction (CI #127):** the adapter stops on a challenge on the page (a CAPTCHA or bot
  check), but the registry did not claim `captcha_checkpoint`, which
  `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one` requires. The stop
  is kept: the approximation gains a `wd_challenge` mode (Workday documents none; the mode makes
  the stop tested), the capture turns it into the bot-check checkpoint, an attempt that meets
  it after approval stops before anything is entered
  (`test_a_challenge_that_appears_after_approval_stops_before_disclosure`), and the registry
  claims the checkpoint at fixture level with `captcha_possible` "yes" (fixture design).

## D89 — An installable web app whose offline page keeps nothing about you (2026-10-30)

- **Why:** remaining-work row 7, the first product slice after the `fixture_<ats>` series
  (D88): "PWA manifest and a read-only offline view".
- **Decision:**
  - A web app manifest (`frontend/public/manifest.webmanifest`: name NoEfforts, start `/jobs`,
    standalone, 192, 512 and maskable icons) and Apple web-app metadata in `layout.tsx`, so the
    app can be installed on a phone or desktop.
  - A service worker (`public/sw.js`, registered by `components/ServiceWorker.tsx`) that keeps
    exactly two files for offline use: a static offline page (`public/offline.html`) and one
    icon. It never caches a page of the app, an API response or a document. Every request goes
    to the network as before; only a page load that fails because you are offline gets the
    offline page, which says so and shows nothing about you.
  - "Read-only offline view" is the offline page alone: showing your jobs or applications
    offline would mean keeping your data on the device, outside the account's export and
    deletion (D77), so it is not done.
  - The Docker web image now ships `public/` (it did not before), and the smoke test checks the
    manifest and the offline page through the running container.
  - Playwright blocks service workers in every spec except `pwa.spec.ts`, so request routing in
    the other specs still sees every request.
- **Not done:** no offline data, no push notifications, no background sync, no store listing,
  no native app (row 7 keeps "then decide on native apps").
- **Unchanged:** the backend, `SCHEMA_VERSION` (3), no migration.

## D90 — A capture-only browser extension: the tab's address and title, to your own NoEfforts (2026-10-30)

- **Why:** remaining-work row 6, its safe part: "send URL ... to the user's own NoEfforts;
  never fill". Page capture stays refused (409 for real pages), so the extension sends no page.
- **Decision:**
  - `extension/`, Chromium Manifest V3, loaded unpacked (not published). Permissions
    `activeTab` and `storage` only; host permissions `http://127.0.0.1/*` and
    `http://localhost/*` only; no content scripts, no `scripting`, `tabs`, cookies or history.
  - It sends `POST /api/jobs` with `{url, title}` (the address without its fragment, the title
    cut to 300 characters) with an API token (D84) as `Authorization: Bearer`, with
    `credentials: "omit"` (never the browser's NoEfforts session) and redirects refused.
  - The token must have exactly the `import:jobs` scope: the options page checks it with
    `GET /api/token` before keeping it and refuses any other scope set. It is never shown
    again, and changing the NoEfforts address removes it, so it is never sent to an address it
    was not checked against. The address must be plain http to 127.0.0.1 or localhost, with no
    path, query or login.
  - The background worker completes a save only for a message from the extension's own pages,
    for a tab it reads itself; without your click on its button (`activeTab`), it cannot see
    another site's tab.
  - No backend change: the existing `import:jobs` allow-list already covers `POST /api/jobs`.
- **Not done:** no page text or form capture, no filling, no Firefox or Safari build, no store
  listing, no access from anywhere but this machine.
- **Unchanged:** the backend, `SCHEMA_VERSION` (3), no migration.

## D91 — Decision register: the open questions resolved under the standing authorization (2026-10-30)

- **Why:** the owner delegated ordinary product and engineering decisions ("Resolve existing
  questions yourself") and set standing defaults: local-first single owner, PWA first, in-app
  notifications first, external messaging and AI drafting only behind explicit opt-in, no
  standing permission to submit, per-application approval. Each open question in
  `docs/remaining-work.md` is now decided, or isolated as an external permission. The register
  itself is the table in that file ("Decision register"); it is not an approval queue.
- **Decided (defaults kept, now final until a demonstrated need changes them):** eligibility
  shown as its own advisory, tri-state component; a possible duplicate never blocks preparation
  but approval waits for "This is a different role"; the user move to `submitted_confirmed`
  stays, with what you checked; an outcome before any known submission is refused; Freehire
  credit on the Discover and job pages; AI drafting for owner accounts only; account deletion
  immediate, nothing kept, no grace period; no standing approvals (every submission needs its
  own approval: an owner default, not a missing feature); follow-ups in the app (D92).
- **Decided, to build:** Freehire's documented `reality` signals are shown display-only,
  attributed to Freehire, never used in matching, approval or routing (row 12).
- **Not mine to decide (external permission, isolated):** live-pilot permissions 1-4 for a
  real employer (row 26); the inbox scope (row 31); a key and budget for Claude (row 23);
  hosting and any paid provisioning (row 40). Each blocks only its own action.
- **Workday terms:** Workday stays a manual handoff. A review I make of public terms would be
  my own reading, recorded as such; it would not be the owner's acceptance or a legal
  permission, and no automation of real Workday sites follows from it.

## D92 — Follow-ups: when to check on a submitted application, in the app, with a message to copy (2026-10-30)

- **Why:** the target list names "receipts, tracker, follow-ups and notifications"; receipts,
  the tracker and notifications existed, follow-ups did not.
- **Decision:**
  - Derived, like notifications (D83): a follow-up exists only once the application entered a
    submitted state (an employer receipt, or your statement that you applied yourself). It is
    due `NOEFFORTS_FOLLOW_UP_DAYS` (default 7, 1-60) after the latest of the first submission,
    the day you last followed up, and the day of an assessment or interview you recorded; or on
    a day you choose (today to a year ahead). An offer, a rejection, a withdrawal or "no
    response" closes it.
  - Stored (`follow_ups`, migration `b6d41f8e2a93`): only your choices, the day you followed
    up, a chosen day, stopped. Deleted with the application and the account; exported.
  - `GET /api/follow-ups`, `GET /api/applications/{id}/follow-up` (with the message),
    `POST /api/applications/{id}/follow-up` (`done`, `remind`, `stop`, `resume`), each scoped
    to the signed-in account (404 otherwise); refusals carry reason codes. A `read` token may
    list follow-ups, not read the message (it names you) and not change one.
  - A due follow-up is an in-app notification (`follow_up:<application>:<day>`); a new day is a
    new notification. The tracker list marks "Follow up due"; the tracker panel and the
    application page show the follow-up and its actions.
  - The message is a deterministic template: the job's title and employer, the day you applied
    and your name as approved in your profile ("[Your name]" otherwise); for an interview or an
    assessment you recorded, it says so. No other fact of yours, no LLM, never sent.
  - Audit `follow_up.update` with the change only (never the chosen day or the message).
- **Not done:** sending anything (email, text, push): external messaging stays opt-in work
  (row 8); per-user follow-up days (one owner setting, single-owner default).
- **Unchanged:** `SCHEMA_VERSION` (3); the execution path and the worker (nothing written there).

## D93 — Freehire's `reality` signals, shown display-only (2026-10-30)

- **Why:** decided in D91 (row 12): show what Freehire says about a posting's age and reposts,
  attributed to Freehire, never as a fact and never as an input.
- **Decision:**
  - `provider.freehire_signals` reads only the five documented fields of `reality`, each with
    its documented type (a lowercase class token; whole counts from 0 to 100,000, never a
    boolean; a boolean flag); anything else in the object is not read, and an object with
    nothing usable gives no signal. Stored in the record's normalized data (`source_signals`),
    so no migration, refreshed on every read, and never part of the fingerprint: a ticking
    `age_days` is not a change.
  - `describe_signals` words them in Freehire's own terms ("likely evergreen", "listed for 3
    days", "reposted twice", "mass-posting count 5", "flagged for fake freshness"): no verdict on
    the posting and nothing about the employer. Discover and the job page show "Freehire says:"
    with "not checked by NoEfforts".
  - Display-only, enforced: a test reads the code and allows the signals in the discovery
    provider and the two routes that show them only.
- **Not done:** filtering or sorting by a signal (it would make an unverified claim an input).
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; the fingerprint.

## D94 — Email reminders to the account owner, opt-in, one daily digest (2026-10-30)

- **Why:** remaining-work row 8, with the owner's definition: reminders to the account owner
  that an application needs attention or a follow-up is due, with a link back; never an email to
  an employer or recruiter, and the follow-up message stays a draft to copy.
- **Decision:**
  - Off by default at two levels: the owner's switch (`NOEFFORTS_EMAIL_ENABLED` and an SMTP
    server; `mail/service.config_problem` refuses an incomplete setup, a link address with a
    path, or production without STARTTLS to a non-loopback server) and each account's opt-in.
    Opting in needs an authenticated session (API tokens refused), an address verified with a
    6-digit code typed in the app (keyed digest stored, 30 minutes, 5 tries, 5 codes a day),
    then "Turn email reminders on". `NOEFFORTS_EMAIL_RECIPIENT_DOMAINS` can restrict domains.
  - One daily digest at the hour you choose (UTC): unread items of the in-app feed in the
    categories you chose, never an item emailed before. It says only the category and links to
    `/tracker?highlight=<application>`, a page that only reads. No job, employer, answer,
    document, token or action link; following it changes nothing.
  - Delivery (`email_deliveries`): `pending`, claimed under a lock (settings, then delivery: the
    same order as opting out), re-checked (opted in, the same verified address, an allowed
    domain, something new), marked `sending` in its own commit, then the transport decides, with
    every write fenced by `generation`. Accepted -> `sent`; a definite transient refusal (before
    the message, or an explicit 4xx after it) -> `pending`, at most `NOEFFORTS_EMAIL_MAX_ATTEMPTS`
    (3) with backoff, then `failed`; permanent -> `failed`; a possible acceptance (connection
    lost or timed out after the message started) -> `uncertain`, final, never resent; a worker
    that dies while `sending` -> `uncertain`. Not exactly-once: SMTP cannot promise it, so an
    uncertain message is never retried rather than risk a duplicate.
  - Opting out, a new address or removing it cancels everything still `pending`; deleting the
    account deletes every row, and a worker finds nothing to send. That is the boundary: a
    delivery a worker has already claimed (`sending`) is with the transport and may still go out,
    and a message the mail server accepted cannot be recalled. Acceptance by the server is not
    delivery to an inbox. NoEfforts never resends an uncertain message and never puts an item in
    a second digest; it cannot promise that no duplicate appears further down the delivery chain.
  - Five separate states, none implying the next: the feature is implemented (yes, local sink
    only); a transport is configured (the owner's `NOEFFORTS_EMAIL_*`; the settings page shows
    "not set up" otherwise); the recipient is verified (per account, by code); email is enabled
    (per account, after verification); real delivery is verified (no: never run against a real
    mail server or inbox).
  - Export: your address, when it was verified and your preferences are in your export (they are
    yours); the pending code's keyed digest is not (credential material), nor are a delivery's
    keyed recipient digest and worker internals. No message content is stored, so none is
    exported. Keeping addresses out of logs and audit records is a separate rule.
  - Logs and audit carry the delivery id, a fixed outcome code and the kind of change only:
    never the address, a code, a message or an exception's text. The export holds your settings
    and deliveries without keyed digests or worker internals; no message content is stored.
  - A local SMTP sink (`fixtures/ats_receiver/mail_sink.py`, also served by the receiver with
    `--smtp-port`) with its own ledger and failure modes is the test oracle. No real mail server
    or recipient is used.
- **Also (tooling):** `scripts/validate.sh` runs each validation step with its output in a log
  and its own exit status deciding (a `ruff check | tail` once passed on `tail`'s status);
  `scripts/test_validate.sh` proves a failing step fails the wrapper and runs in CI.
- **Register corrections (D91):** inbox reading and automated code retrieval stay disabled and
  are not an owner action; reply classification is a separate optional integration, deferred.
- **Not done:** push or chat; per-item immediate emails; a real mail server.
- **Unchanged:** `SCHEMA_VERSION` (3); the execution path. Migration `c4e8a2d17b55`.

## D95 — Employer job boards: read-only connectors for published postings, one board at a time (2026-10-30)

- **Why:** the owner's next milestone: discovery from documented public posting feeds
  (Greenhouse, Lever, Ashby), without employer credentials and without turning a board setting
  into a way to fetch arbitrary addresses. Research: `docs/research/job-board-apis.md`.
- **Decision:**
  - **Connectors.** Greenhouse's Job Board API list (`GET /v1/boards/{board_token}/jobs
    ?content=true`) and Lever's Postings API list (`GET /v0/postings/{site}?mode=json&skip&limit`,
    global or EU host). Both are documented as public, read-only and unauthenticated for GET.
    Their application POSTs (employer key), Greenhouse Harvest and Lever's Data API are never
    called: no candidate endpoint, form, upload, login or submission exists in this code.
  - **Ashby: not built.** Its documentation host could not be opened (DNS, the environment's
    allowlist) on two days; a connector is not built from search snippets. The app says why.
  - **Activation.** Off at two levels: the owner's `NOEFFORTS_BOARD_SOURCES_ENABLED` (default
    false; Compose now passes it) and each board, which a user adds by provider, region and
    board identifier, and reads by pressing "Read now". Nothing reads a board on a schedule or
    crawls employers; a board can be paused or removed.
  - **Network boundary.** The request URL is built from the provider's fixed host and the board
    identifier (letters, digits, `-`, `_`, up to 100; then percent-encoded): a user never gives
    a URL. GET only; no cookies, credentials or anything of the user (headers are `Accept` and a
    fixed `User-Agent`). HTTPS to that one host only; every resolved address must be public,
    checked when connecting (`urlsafety.public_https_opener`, the existing checks); redirects are
    refused, never followed; 10-second timeout, 10 MB per response, Lever at most 20 pages of
    100. Test stand-ins come only from `NOEFFORTS_BOARD_API_OVERRIDES`, honoured only with
    `NOEFFORTS_ENV=test` and a listed fixture origin (D86); production rules are unchanged.
  - **Rate and failures.** One read per board at a time (a row lock), at most one every 5
    minutes; a `429` holds the board for its `Retry-After` (bounded 1 minute to 1 day); other
    failures back off 5 minutes doubling to 1 day. A failed read changes no posting; the board
    shows when it last read successfully and a fixed error code with a safe message.
  - **Completeness.** Only a complete read may say a posting is no longer listed: Greenhouse
    when `meta.total` equals the jobs received, Lever when a page comes back short. A read that
    fails, or stops at the page limit, closes nothing.
  - **Postings stay apart from your jobs.** A read stores postings for that board only
    (`discovered_jobs` with `board_source_id`); it adds nothing to your jobs. "Save to my jobs"
    adds one, or links it to an existing job with the same posting address, or (for a job
    entered without a link) the one job with the same employer, title and location: the
    existing dedupe (`service._existing_job`), so a role listed on two boards or added by hand
    is not added twice. Repeated reads update the same rows (one per board and posting id).
  - **Distinct states, never merged:** the posting exists (it was read); the source lists it
    ("Source lists it" / "No longer listed by the board since …"); it matches your preferences
    (the existing match explanation, D79); you meet a requirement (never decided here); an
    application route is supported (unchanged: a saved job gets the usual route, a manual
    handoff for a real destination). Discovery changes no approval, route, permission or
    submission state.
  - **Untrusted content.** Descriptions are reduced to plain text (entities decoded once, tags
    and scripts dropped) and rendered as text; links are kept only if they are `http(s)` and
    syntactically safe, shown as links with `noopener noreferrer nofollow`, and never fetched.
    Attribution: "from Greenhouse job board" / "from Lever job board" and the employer name you
    gave.
  - **Privacy.** Board identities and postings live only in the application database, per
    account (cross-account access is 404). Logs carry the source's id, a fixed outcome code and
    counts; audit records the kind of change, the provider or the outcome; never the board, the
    employer, a posting or a URL. Your
    boards and their postings are in your export and are deleted with your account; removing a
    board deletes its postings, and jobs you saved from it stay.
- **Also (D94 configuration fix):** Compose passed only the settings it named, so the email,
  discovery, drafting and session settings in `.env` never reached the containers.
  `docker-compose.yml` now names every owner setting in `.env.example` (no `env_file`, so the
  runner and proxy secrets stay out of the API container), `scripts/check_env.py` warns when
  email or boards are on, and `test_deployment_config.py` keeps the two files in step.
- **Not verified:** any real board. Every request in tests went to local stand-ins of the
  documented shapes (`fixtures/ats_receiver/board_feeds.py`), whose ledger is the oracle.
- **Unchanged:** `SCHEMA_VERSION` (3); execution, routing and admission. Migration `d7f3b9e41c26`.

## D96 — A daily check of a job board you choose, with a notice of new postings (2026-10-31)

- **Why:** the canonical Phase E row 1 (`product-evidence.md`): bounded, scheduled discovery from
  permitted feeds, with freshness. D95 reads a board only when you press "Read now".
- **Decision:**
  - **Your choice, per board.** "Check daily" on a board you added; off for every board until
    you tick it, and nothing runs while the owner's `NOEFFORTS_BOARD_SOURCES_ENABLED` is off.
    At most `NOEFFORTS_BOARD_DAILY_CHECK_LIMIT` (10) boards per account; no crawl, no board you
    did not add, no other provider.
  - **Same boundary as D95.** The worker (`noefforts.check_board_sources`, every 5 minutes, at
    most 5 boards a tick) calls the same `board_sync.sync`: the fixed host, GET only, nothing of
    yours, public addresses at connect, no redirects, the same limits, the same lock (a board
    you are reading at that moment is skipped), the same backoff and `Retry-After`, and the
    same rule that only a complete read says a posting is no longer listed. A board is read at
    most once in 24 hours, and never while paused or backing off.
  - **Freshness and new postings.** A board's first successful read is its baseline; postings
    first seen after it are new to you. The notifications feed shows one notice per board per
    day (UTC), for the last 30 days: how many new postings, the board and the employer you gave,
    a link to Discover. It needs nothing of you, so it never reaches the email digest (D94's
    categories are "needs your attention" and follow-ups). Nothing is added to your jobs;
    matching stays the posting's match summary; no application, route or approval changes.
  - **Audit and export.** Turning it on or off is `daily_check_on` / `daily_check_off`; a
    worker read is `daily_check` with `ok` or `failed`. `daily_check` and `baseline_at` are in
    your export and deleted with the board or the account.
- **Not verified:** any real board (local stand-ins only, as D95).
- **Unchanged:** `SCHEMA_VERSION` (3); execution, routing and admission. Migration `e5a1c3f80d47`.

## D97 — A form's page is ready when its own requests are done; what AI drafting used, with its basis (2026-10-31)

- **Why:** the owner's D97 milestone: inspect the form-readiness wait added for CI #133, then
  show drafting usage against the budget without presenting estimates as a bill, and fix what
  the budget ledger got wrong.
- **Form readiness (runner):**
  - **Before:** after opening the form the runner called Playwright's `networkidle` (no
    connection for 500 ms, at most 8 s) and used the page as it was if that never came. It is
    a condition, but every page paid the 500 ms quiet floor, any long-lived connection (an
    event stream, a hanging tracking pixel) held it to the full 8 s, and a page still loading
    after 8 s was used anyway.
  - **Now:** a tracker attached before the page opens counts the page's own document, script,
    stylesheet, fetch and XHR requests in flight. The page is ready as soon as none has been in
    flight for 100 ms (`QUIET_MS`), polled every 25 ms. Images, media, fonts, event streams and
    WebSockets are not waited on. Still loading after 8 s (`SETTLE_LOAD_MS`, unchanged): the
    attempt stops safely before anything is entered ("the form's page was still loading after
    8 seconds"). The wait only waits: nothing is typed, clicked, sent or repeated.
  - **Kept:** the slow-locale-file reproduction (2.5 s), now with a never-ready case through
    the receiver's ledger (failed safe, nothing disclosed or accepted, the locale file
    requested once) and unit cases on a local page server (ready at once, a slow request waited
    for, never ready, ignored resources, listeners removed).
  - **Measured** (see `implementation-status.md`): the old wait took a median of 489-491 ms
    per form (271 waits over the execution tests, about 135 s in all, max 3.0 s, none at 8 s).
    That is the 500 ms floor. It accounts for about 2 of the roughly 8 minutes the full local
    backend run grew by (52m15s to 1h00m20s); the rest was not traced to a cause.
- **Drafting spend (Account → "AI drafting spend"):**
  - **One ledger.** `drafting_usage` stays the only record: the view, the export and the
    budget all read it. No second budget system.
  - **Every amount says what it is** (`cost_basis`): `estimated` (from the tokens the provider
    reported, at the list prices named by `price_version`, `anthropic-list-2026-10-06`),
    `unknown` (the worst case kept: the provider may have charged and nothing says what),
    `reserved` (the worst case held while the request runs; shown as unknown once it is older
    than the request timeout plus 2 minutes, because the worker stopped) or `not_sent` (refused
    before it left: 0). The card says the amounts are NoEfforts' own accounting, not an invoice.
  - **Shown:** the server's daily budget and its reset (00:00 UTC, every account together),
    today's total for the server and what is left, your requests and tokens today, the last
    14 days and your last 20 requests with their outcome and basis, the model and the price
    list. The server total and what is left are shown only to an account drafting is offered
    to; everyone else sees only their own records. Session only: an API token cannot read it.
- **Ledger fixes:**
  - **An error reply keeps its worst case.** An HTTP error from the provider (500, 400, ...)
    was settled at $0, as if certainly free. Whether such a reply is charged is not reported,
    so it now keeps its worst case as `unknown`. Only a request refused before it left (the API
    host failed the public-address check) is recorded as `not_sent` at 0. This can use the day's
    budget faster after errors; it never under-counts.
  - **Settled once.** A second settlement of the same request (a retried task, a late reply)
    changes nothing: the first stands, so an estimate cannot become a worst case or a kept worst
    case become 0.
  - **Migration `a4c8e2d61f93`:** existing rows get their basis; a provider error recorded at 0
    before D97 regains its worst case. Downgrade drops both columns; restored worst cases stay.
- **Checked and unchanged:** concurrent reservations (one advisory lock; the existing race test),
  the midnight boundary (a request reserved before midnight stays on its day, settled after it;
  the new day starts from 0), per-account isolation of the view, timeouts and unknown errors
  keeping their worst case, a budget of 0 sending nothing.
- **Not promised:** a hard ceiling on the provider's billing. The budget bounds what NoEfforts
  sends, using worst cases; the provider bills its own way. Deleting an account deletes its
  usage rows, so that day's server total drops by what they held (retention rules, D77).
- **Export:** your `drafting_usage` rows with `cost_basis` and `price_version`, and a
  `drafting_budget` block (provider, model, daily budget, reset, price list). Never the key, a
  prompt, a draft or a provider error's text.
- **No paid request was made and no key exists in the repository:** every test uses a stub
  client and a stub resolver.
- **Unchanged:** `SCHEMA_VERSION` (3); routing, admission, discovery. Migration `a4c8e2d61f93`.

## D98 — Question wordings found in the owner's archive of real applications (2026-10-31)

- **Why:** the owner supplied the old bot's answers (row 24): 3,364 distinct real application
  questions. Run through NoEfforts' own resolver (read-only, outside the repository), dozens of
  them would have been saved as reusable answers and filled in again elsewhere although they
  are sensitive, about work authorization, citizenship or residence, a licence or an address.
  The answer policy already said NoEfforts recognises known wordings only; these are now known.
- **Decision** (LLM-free, patterns only; tests use synthetic paraphrases, never the archive):
  - **Never saved, sensitive (added to the C5 topics):** religion in other words (church,
    pastor, place of worship, statement of faith, "the community to which you belong"),
    first-generation status, financial history (tax returns filed, taxes owed, a payment
    agreement with the IRS, bankruptcy, your credit), public office (you or family as a
    government official, politically exposed), the prohibited-person questions (fugitive from
    justice, unlawful drug use or addiction, a mental institution, subject to a restraining or
    protection order, dishonourable discharge), neurodivergence, and "served in the U.S.
    military".
  - **The original equal-opportunity topics in more forms** (still sensitive, saved only as a
    sensitive answer that needs "include this answer" on each form, D61): plurals ("protected
    veterans", "races", "ethnicities", "genders", "religions", "2SLGBTQIA+"), run-together
    labels ("VeteranStatus", "DisabilityStatus"), pronoun labels ("He/him", "Xe/xem") and an
    option shown as its own question ("Asexual").
  - **Legal status, a checkpoint you answer for each application:** work status, employment
    eligibility, working rights, proof of (legal) employment authorization, alien, residency or
    resident status, non-resident, ITAR, export control, deemed export, U.S. person, eligibility
    for a security clearance, home state or state of residence in a sentence (the bare label
    "State of residence" is still answered from your profile), resident "as defined" by a law,
    CCPA. Checked after the sensitive signals, so a sensitive question stays sensitive.
  - **Not saved:** a licence named by its acronym (CPA, CFA, CFP, CMA, FRM, PMP, NMLS,
    chartered accountant: a credential in your profile, D69) and the parts of an address
    (apartment, suite, unit, zipcode, PIN code: they go stale, C6).
- **Measured on the archive** (private, wording only): 77 of 3,364 wordings changed; none of
  them a skills or experience question. Left as they were, on purpose: questions about military
  programs or the military community (about the job, not you), drug-free-workplace and
  lie-detector notices (statements), and wordings in other languages.
- **Effect on saved answers:** an answer saved earlier for one of these wordings is kept and
  listed as "Not reused" (the existing rule); nothing is deleted. Package content keeps its
  shape: `SCHEMA_VERSION` stays 3. A package rebuilt after D98 may resolve such a question
  differently, and its approval then follows the usual rules.
- **Not done here:** importing the owner's answers. That waits for the owner's marked review
  (row 24); only rows marked yes would be imported, each through the same resolver check.

## D99 — Saved answers imported from a file, as proposals you approve (2026-10-31)

- **Why:** the owner wants their old bot's answers in NoEfforts (row 24), and the established
  rule is that nothing is imported before they approve it. Approving in the product, row by
  row, is that approval, and it works for any file of questions and answers, not only theirs.
- **Decision:**
  - **Saved answers → "Import saved answers":** a JSON (`[{question, answer}]`, also
    `{answers: [...]}`) or CSV file (`question`, `answer` columns). A review sheet with an
    `approve` column keeps only the rows marked yes or edit, and an edit uses "your corrected
    answer". The file is read in the browser; only questions and answers are sent, to your own
    NoEfforts (`POST /answer-bank/import`, session only).
  - **Every row is judged by the rules for saved answers**, on its wording alone: refused,
    with its reason, when the resolver would not save it (employer, time, pay, place, a
    credential, long free text), when it is sensitive or about work authorization,
    sponsorship, citizenship or residence (never imported, even the topics that can be saved
    as sensitive from a form), a template naming the employer (`{company}`), a placeholder
    answer, a blank row, a question you already have a saved answer for (nothing is
    replaced), and a question given twice with different answers (all of them refused: never
    chosen silently; the same answer twice is imported once).
  - **A check first:** the file is checked without writing anything and the page says how many
    rows can be added and why the others cannot; you then add them.
  - **Proposals:** an imported answer is saved as `proposed` with provenance `import`; the
    resolver uses approved answers only, so it answers nothing until you press "Approve" on it.
    A yes/no answer is saved for that question with exactly the options Yes and No; any other
    answer as text. Its history says "imported from a file".
  - **Privacy:** the response names rows by position and reason codes, never their text; the
    audit keeps counts (`answer_bank.import`) and each approval (`answer_bank.approve`).
    Another account's proposal is 404.
- **Not done:** the owner's own file has not been imported (it is theirs to import, after their
  review); profile facts (authorization, sponsorship, residence, education) are entered on the
  Profile page, never from an import.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration (the provenance and approval columns
  already existed).

## D100 — Listings by application platform (2026-10-31)

- **Why:** the owner wants Freehire's listings filtered by the platform they apply through
  (Greenhouse, Workday, ...) and every listing on a chosen platform added at once.
- **Decision:**
  - **The platform is read from the listing's address**, by the same rule as a job's ATS
    identity (`jobs/canonical.py`: Greenhouse, Lever, Ashby, Workday, Workable,
    SmartRecruiters), and is "Other or not recognised" otherwise. Freehire's documented API has
    no reliable field for it (`docs/research/freehire.md`), so its `source` is not used. The
    address is never fetched to decide.
  - **Find jobs → "Application platform":** tick one or more platforms to keep only those
    listings. Every listing kept that has a link, a title and an employer is added to your
    jobs, as any import does (the existing dedupe links one you already have); a listing on
    another platform is counted as "filtered out" and not stored. None ticked: every platform.
    Freehire's search cannot be asked for a platform, so the filter applies to what the search
    returned (the documented 1,000-result window still bounds one search).
  - **Discovered → "Application platform":** the list filtered to one platform, with how many of
    your listings are on each (`GET /discovery/platforms`, `GET /discovery/jobs?platform=`), per
    account. Each listing shows its platform.
  - **A platform says nothing about applying.** Whether NoEfforts can apply on a listing is its
    route, unchanged: a real employer's form stays a manual handoff until a live adapter exists.
- **Not built here:** the owner's other requests (automatic submission on Greenhouse, Gmail for
  codes and status) are separate milestones; see the status document.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration (the platform was already stored with each
  listing as `ats_provider`); watches keep their single query.

## D101 — Your Gmail, read-only, for verification codes and application emails (2026-10-31)

- **Why:** the owner asked, on 2026-10-31, for NoEfforts to use their Gmail (through their own
  Google Cloud credentials) for verification codes and for tracking what employers reply. This
  reverses R7.5 (S4, D54: "no mailbox or Gmail client") and D10/D94's "NoEfforts does not read an
  inbox", for this purpose only, by the owner's instruction.
- **Decision:**
  - **Read-only, the owner's own account, off by default.** Google's REST API with the
    `gmail.readonly` scope, granted by the owner in their own browser (`app/modules/inbox/
    connect.py`: the installed-app flow, a loopback redirect, state and PKCE); the token file is
    written readable by the owner only and never printed, stored in the database or committed.
    Enabled only with `NOEFFORTS_INBOX_ENABLED`, for the accounts in `NOEFFORTS_INBOX_OWNER_EMAILS`,
    and then each use only when the owner turns it on in Account.
  - **The guard is narrowed, not removed.** `tests/test_forbidden_capabilities.py` allows the
    Gmail message path, host and read-only scope in `backend/app/modules/inbox/provider.py` and
    the stand-in only; every mail library, IMAP, POP and other provider stays forbidden
    everywhere, these files included.
  - **Codes:** entered for a waiting code step only from a new email of a code sender
    (`NOEFFORTS_INBOX_CODE_SENDERS`) that holds exactly one code; otherwise the step stays the
    user's. Each email is used once; a rejected code is not entered again (the step reopens for
    the user, as before).
  - **Application emails:** sorted by fixed wording (rules.py, no LLM). A rejection, interview or
    assessment naming exactly one submitted application is proposed; the user confirms it, and it
    is recorded through the same `record_outcome` as the tracker (source `user_reported`, the
    email's day, a note naming the sender's domain). Never recorded without the user (D53).
    Mixed wording is "unclear"; an email naming no single application is "unlinked".
  - **"We received your application":** when it names exactly one application whose submission
    has an unknown outcome (`submitted_unconfirmed`), it is proposed as that submission's
    reconciliation. The user's confirmation takes the same transition as reconciling it by hand
    (`submitted_confirmed`, actor the user, "Reconciled as received", the email's sender and day
    as what was checked), under the same locks (D46). Refused once the submission is settled
    another way. Otherwise such an email is only noted.
  - **Kept:** per email, a keyed reference, the arrival time, the sender's domain, its kind, the
    application and what happened. Never the text, subject, sender's name or a code. Exported
    (except the keyed reference) and deleted with the account; audit by counts and fixed codes.
  - **Hosts:** Google's API and token hosts only (public-address check); a fixture origin only in
    the test environment.
- **Not verified:** any real mailbox or real code email (a local stand-in of the API only).
- **Unchanged:** `SCHEMA_VERSION` (3); execution's code checkpoint (codes still go through
  `submit_code`, bound to the user, the application, the step and its round). Migration
  `b7d2f4a91c05`.

## D102 — The Greenhouse pilot: real Greenhouse applications, off by default (2026-10-31)

- **Why:** the owner asked, on 2026-10-31, to "enable the automatic application totally for the
  greenhouse". Until now every real employer destination was refused in code, and CLAUDE.md
  keeps them refused "until a live adapter has its own capability entry and receiver-style
  tests". This is that adapter, entry and tests; it changes no other rule.
- **Decision:**
  - **`greenhouse_live`**, a new adapter name for the id-mapping rules of `greenhouse_dom`,
    unchanged (`adapters/greenhouse_dom.py` `GreenhouseLiveAdapter`), with its own capability
    entry (`policy.CAPABILITIES`, `real_destinations: True`), version (`greenhouse-live-1`),
    registry spec and form source (`greenhouse_live`). Approvals, rehearsals and evidence name it.
  - **Off unless all hold** (`execution/live.py`, one place, checked at capture, routing,
    approval, queueing, both gates and in the worker): `NOEFFORTS_LIVE_GREENHOUSE_ENABLED`, the
    account in `NOEFFORTS_LIVE_OWNER_EMAILS`, `NOEFFORTS_ENV=production` and the `container`
    browser isolation (Chromium's own sandbox on). Switching it off stops a queued application
    before anything is entered. In the test environment the same code runs only against a local
    stand-in named by two test-only settings; real hosts are refused there.
  - **Hosts are fixed in code:** a job post on `boards.greenhouse.io`, `job-boards.greenhouse.io`
    or their EU hosts (https, no port, no userinfo); its data from `boards-api.greenhouse.io`;
    GETs only, public addresses only, no redirects, robots.txt honoured, 2 MB, nothing of the
    user's sent. The browser may reach the one board host of its session plus Greenhouse's static
    scripts and stylesheets (the B3 rule, `job-boards.cdn.greenhouse.io`, GET/HEAD).
  - **Capture** reads the job data and the page and keeps the form only if the page's controls
    map one for one to the job data (`greenhouse_dom.build_schema`); the job data must name the
    same job. Otherwise nothing is kept and the reason code is shown.
  - **Unchanged for every application:** your approval of the exact package, revocable; the
    rehearsal first on each employer's path (E6: `PATH_RULES["greenhouse_live"]`, the board); the
    page re-checked before anything is entered; anything not understood stops it; one final click,
    never a retry after it (`submitted_unconfirmed`); no CAPTCHA or login is ever passed.
    Approval stays per application: the owner's choice between batch approval and none is still
    open and nothing here decides it.
  - **Registry and admission.** `model.PILOTS = {"greenhouse_live"}` is the only provider allowed
    `real_destinations_enabled`, and only while it claims no live support (its levels are the
    fixture's plus the read-only observations of greenhouse_dom's rules, credited to it in
    `evidence.py` because the rules are the same). Admission stays advisory; the pilot is
    admitted to `observed_read_only`, its claim.
  - **Greenhouse's public documentation and terms reviewed** (`docs/research/greenhouse-terms-review.md`,
    `evidence.DOC_REVIEWS`): no candidate terms for hosted boards were found; Greenhouse's privacy
    policy leaves hosted-board applications to the employer; the MyGreenhouse User Agreement
    forbids automated use of MyGreenhouse, which NoEfforts never uses. The review is mine, as D91
    decided for terms reviews; it is not legal advice and not the owner's acceptance. It meets
    `doc_review_recorded` for every Greenhouse provider, so their I2 waivers are no longer used
    (still tested on tables without it).
  - **Deployment:** `docker-compose.pilot.yml` sets production mode and gives the egress proxy
    an outbound network (as the read-only check's override does); the switch and the owner list
    come from `.env`.
- **Not verified:** any real Greenhouse page filled, uploaded to or submitted to. The one real
  posting observed read-only had dropdowns with no opening evidence, controls the job data does not
  list and a location search: on such a page the pilot stops before entering anything. Real
  uploads, submission and confirmation are the stand-in's design.
- **Unchanged:** `SCHEMA_VERSION` (3); every other adapter and route; no migration.

## D103 — Built is not authorized; disposable test databases (2026-10-31)

- **Why:** the owner, on 2026-10-31 (17:42 UTC): "Before recommending activation, inspect the
  actual authorization history … General permission to develop independently is not proof of
  consent to read a mailbox, disclose applicant data or submit an application. Record only
  authorization that actually exists. Do not invent it." They added: "A feature toggle or
  deployment file must not bypass the existing consent and readiness gates." And: "The
  accidental shared-database reset has happened repeatedly. Make it impossible through the
  supported test entry points."
- **The authorization history, as written.**
  - 2026-10-30, the standing authorization, §7: "This is development delegation, not unlimited
    real-world authorization. Do not: Read my inbox or retrieve OTPs. … Disclose applicant data or
    submit real applications outside the existing gates."
  - 2026-10-31 04:55 UTC, the request D101 and D102 were built for: "Make sure we enable the
    automatic application totally for the greenhouse. … do not cause any problems in filling,
    select, dropdown, typing, submitting, OTP, email credentials.json from google cloud
    console(I will provide). … tracking the application from that email … check all the emails
    form the last time the portal checked".
  - 2026-10-31 17:42 UTC: "Unless there is a later explicit instruction clearly superseding the
    earlier rule: Keep inbox access and automatic OTP entry disabled. Preserve manual OTP entry.
    Keep real Greenhouse disclosure/upload/submission disabled until the existing pilot
    permissions are satisfied."

  | Question | Finding | What it covers |
  |---|---|---|
  | Was reading the inbox explicitly authorized? | **No.** The 04:55 message asked for the feature to be built and to work end to end. It did not address §7's "Do not: Read my inbox or retrieve OTPs". The credentials it would use were never provided, and the later message (17:42) keeps reading disabled. | Nothing operational. D101 is built and off. |
  | Was automatic OTP retrieval and entry explicitly authorized? | **No**, for the same reasons. | Nothing. Typing a code yourself at the checkpoint is unchanged. |
  | Were the Greenhouse pilot permissions granted? | **No.** No posting was named under docs/live-pilot-gate.md §1, and none of the separate permissions in §2 was given: 1 read, 2 open, 3 disclose, 4 submit. D102 said the owner's switch "replaces §1's single named employer". That was wrong and is withdrawn: a request to build the feature is not the gate's permissions. | Nothing. D102 is built and off. |
  | What did the standing authorization cover? | Development: code, tests, documentation, configuration templates, reviews of public documentation, commits and pushes. | Not inbox reading, codes, or real disclosure or submission outside the gates. |

- **Decision:**
  - **One register of operational authorizations** (`backend/app/core/authorizations.py`). It is
    reviewed source code: no setting, deployment file or environment variable can add to it
    (`tests/test_authorizations.py` checks that it imports neither settings nor `os`). Each entry
    must quote the owner's words, the actions and the data they cover, the date given and the
    date it ends, and name its decision here. It is **empty**.
  - **Inbox (D101)** needs `read_codes` and `enter_codes` for codes, and
    `read_application_email` for replies, each on its own. Without them nothing is read. The
    Account view says why ("not_authorized"). Turning a use on is refused (409). The worker and
    direct calls read nothing: `tests/test_inbox.py`, with the stand-in's request ledger showing
    no request. A code typed at the checkpoint still completes the step (same test).
  - **The Greenhouse pilot (D102)** needs each permission for its step, checked independently:
    - capture: `read`;
    - the route: `read`, `open` and `disclose`;
    - queueing: `open` and `disclose`, plus `submit` for an approval to submit;
    - the worker, before the page is opened: `open` and `disclose`;
    - the disclosure gate: `open` and `disclose`;
    - the send gate: `submit`.

    The reason code is `live_not_authorized`. The switch, the owner's account and production
    mode without a record: the post is not read, nothing is queued and nothing reaches the
    board (`tests/test_greenhouse_live.py`, the receiver ledger as the oracle). A permission
    withdrawn after queueing stops the attempt before the page opens, or at the send gate after
    a permitted fill, with no final click.
  - **Implementation is kept.** D101 and D102 are unchanged apart from these checks; nothing was
    deleted. `readiness.DISCLOSURE_PERMISSION_RECORDED` and `SUBMISSION_PERMISSION_RECORDED`
    stay false. The computed checklist (`providers/readiness.py`) shows 0 of 7 conditions met
    today, and nothing here claims otherwise.
- **Approval mode (resolved by the owner; not reopened).** Each application's submission needs
  its own approval, by default. A future batch-review screen may approve several individually
  identified packages at once, each immutable; it is never approval of future applications.
  Each approval is bound to:
  - the user (`user_id`; another account's is 404);
  - the application and destination (the destination is in the hashed content and the binding);
  - the exact package version and content hash;
  - its scope (`disclose_only` or `submit`);
  - an expiry and revocation (`expires_at`, `invalidated_at`);
  - one use where it matters. A rehearsal approval is retired after it runs. An approval to submit
    sends at most once: a confirmed submission refuses another queue (`already_confirmed`), and an
    uncertain one is quarantined, never resent.

  Changed content or destination needs a new approval (the gates compare the hash and the
  binding). A disclosure-only rehearsal is never an approval to submit.
- **Test isolation** (`docs/test-isolation.md`). The suite runs only on a disposable database:
  - named explicitly, with no default;
  - marked as disposable and owned by the test-only role `noefforts_tester`; a superuser is
    refused;
  - claimed for the whole run with a PostgreSQL advisory lock taken before any DROP or migration;
    a second run is refused.

  Every DROP and TRUNCATE waits at most 15 s. A run's own databases are named after it and marked
  with its id, and cleanup drops only those. Ports, the run's Redis database index and the
  disposable broker's port are held under OS file locks. The end-to-end servers hold theirs, and
  claim their database, through the same tool. `scripts/validate.sh` and CI create their
  databases with it.
- **Not verified:** any of it against a real mailbox or a real Greenhouse page (nothing is
  authorized to be).
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; every other route, adapter and approval rule.

## D104 — Greenhouse controls on local stand-ins: phone country, location search, late options (2026-10-31)

- **Why:** the owner, on 2026-10-31: "Then continue Greenhouse control support. Proceed with local
  stand-ins for: Phone country selection. Location search. Late-loading dropdown options. Use
  deterministic matching against approved facts. Country calling code alone must not be assumed
  to identify a unique country. Location labels must not be treated as proof of a selected
  structured location. Do not manufacture hidden coordinates or trust résumé-parsing/prefill
  blindly. Ambiguous or unsupported choices become checkpoints. Synthetic control coverage is not
  evidence that the real page works. No real rehearsal or submission is authorized by this
  message." It is also the owner's policy change that `docs/location-handling.md` asked for
  before typing into a page's own location search, **for local stand-ins only**.
- **Decision:**
  - **Local stand-ins only.** Each structure is recognised at capture only when the page is a
    fixture origin (`greenhouse_dom.build_schema(stand_ins=True)`; there is none in production),
    and the adapter stops before anything is entered on any other destination
    (`STAND_IN_ONLY`). Late lists are accepted only there too (`dropdowns`, `late=True`).
    Elsewhere every rule of D102 and earlier stands. The stand-ins are in
    `fixtures/ats_receiver/greenhouse_v2.py` (`gh2_phone_country`, `gh2_loc_search`,
    `gh2_dd` `late_*`), each a FIXTURE ASSUMPTION.
  - **Phone country** (`widget: phone_country`). Capture recognises exactly one structure: the
    phone question's control in a group named as that question, with exactly one other control,
    a combobox labelled as a country (code) picker, its list in the page, every option stating a
    calling code ("Canada (+1)"). Anything else stays an unlisted checkpoint. NoEfforts chooses
    only when the approved phone number states its code (a "+", digits, then a separator) and
    exactly one option has it. +1 (several options), no code, or no approved number: you choose
    one of the captured options for this application. Never residence, nationality or anything
    else; never saved. The choice is proven by readback.
  - **Location search** (`widget: location_search`, its hidden values `location_structured`).
    The text is the approved residence fact only where the existing rules already classify the
    question as residence, otherwise your answer for this application; never a saved answer, a
    draft, résumé parsing or page prefill. It is typed only after the disclosure gate (the
    ledger counts it as a disclosure; NoEfforts' evidence records that it was disclosed, never
    the text). Exactly one settled suggestion must equal it (whitespace and case aside); then
    the page itself must have set every hidden value and still show the text. A label alone,
    none or several suggestions, a page that sets nothing, or a location already filled in by
    the page stop the attempt, never retried. NoEfforts never writes a hidden value.
  - **Late options.** A list that arrives after opening (a delay, and/or GET requests to the
    page's own origin that finished with a 2xx answer) counts only within `LATE_MS` (5 s), once
    nothing is loading, the same list has been read three times in a row (`STABLE_SAMPLES`,
    now for every list) and it is exactly the approved one in order. Still loading at the
    deadline, changing, partial, different, or fetched any other way: refused before
    disclosure.
  - **Versions:** extraction `greenhouse-dom-v3`; adapters `greenhouse-dom-4` and
    `greenhouse-live-2`, so approvals given under the earlier rules are refused at queueing.
    `dropdowns.CAPABILITIES` names each of the three as `fixture_only`.
  - **`SCHEMA_VERSION` stays 3.** Only a package of a form with one of these controls gains a
    key (`.answers[].widget`); every other package keeps its exact content and hash, so no
    approval changes meaning. Such forms could not be captured before D104.
  - **Registry:** `greenhouse_dom`'s `location_picker` is now `fixture` (the stand-in), with its
    required ledger scenario `location_exact_or_checkpoint`. `greenhouse_live`'s stays `none`:
    on its real hosts the control is refused. Readiness is unchanged: 0 of 7 conditions met;
    fixture evidence meets none.
- **Not verified:** any of it on a real page. Run #9 saw no location control and no dropdown
  opening on the one real posting observed; its phone-group control (`u1`) remains not
  understood. Nothing was rehearsed or submitted for real.
- **Unchanged:** `SCHEMA_VERSION` (3); no migration; every other adapter, route and approval rule.

## D105 — Review several packages, approve each on its own (2026-10-31)

- **Why:** the owner, on 2026-10-31: "A future batch-review interface may approve individually
  identified, immutable packages, but it must not mean unrestricted approval for future
  applications. Each approval must remain bound to: the user; the application and destination;
  the exact package/version; its permitted scope; expiry and revocation; one-time consumption
  where required. Changed content or destination requires renewed approval."
- **Decision:** a review page, `/review`, and two API routes (`app/modules/preparation/review.py`):
  - `GET /review/packages` lists your applications that can be approved now, each with its
    current package. Each row shows the version, the start of its content hash, its destination
    and what holds it back, if anything.
  - `POST /review/approve` approves a list of items. Each item names its application, the
    package version and that version's content hash as shown, and its own scope. The scope is
    required, so never "submit" by omission.
  - Each item goes through the same `package.approve` as the package's own page, in its own
    transaction. A changed package is refused (`package_changed`), never replaced. An approval
    to submit still needs the path rehearsed first (E6). Another account's application is "not
    found". One refused item leaves the others as they are.
  - At most 25 items, each application once, and no "all" or filter. Approving queues, sends and
    submits nothing.
  - API tokens cannot use these routes (default deny, D84). An audit event
    `package.approve_reviewed` records the batch identifier beside each `package.approve`.
- **Unchanged:** every binding of a single approval (user, application, destination, adapter
  and version, package hash, scope, expiry, revocation, use once where that matters);
  per-application approval as the default; `SCHEMA_VERSION` (3); no migration.

## D106 — Activation reconciled with the checklist; authorization at run time (2026-11-01)

- **Why:** the owner, on 2026-11-01: "reconcile the computed readiness checklist with the
  implementation and produce an actionable path to meeting each condition … Do not relax a
  condition just to raise the count. Do not keep a completed condition falsely unmet. Do not
  count synthetic proof as real-page evidence."
- **Found and fixed:**
  - **The checklist measured the wrong adapter.** It was computed for `greenhouse_dom`, the
    fixture-only rules provider. That provider never runs on a real destination, so conditions
    4 (real upload), 5 (real submission) and 7 (capability entry) could never be met however the
    pilot went. It is now computed for the pilot, `greenhouse_live`, the only adapter whose real
    rehearsals and submissions could be recorded (`GET /api/providers/greenhouse_live/readiness`).
    Provider admission keeps computing `greenhouse_dom`'s own row, unchanged.
  - **Two sources of truth for the owner's permissions.** `readiness.DISCLOSURE_PERMISSION_RECORDED`
    and `SUBMISSION_PERMISSION_RECORDED` (constants) existed beside D103's register. They are
    replaced by functions that read the register, and `pilot_gate` follows it.
  - **Condition 7 split into its two parts.** The pilot's reviewed real-destination entry exists
    (D102). The capabilities a real application uses are still at fixture, and only their own
    real evidence can raise them. It stays unmet, with both parts shown.
  - **Each condition now carries its path:** what it needs (code, observation, configuration,
    consent, owner machine), why it is unmet, the smallest next action, what NoEfforts can do,
    what the owner must do, what stops a real attempt meanwhile, and which tests verify it.
- **Read-only path B built, not run** (the first independent step for conditions 1 and 2). Run #9
  found all 12 dropdowns `not_opened`. All 11 data requests it refused were
  `GET /locales/*/*.json` on `job-boards.cdn.greenhouse.io`.
  - `--inspect-widgets-locales` (workflow input `inspect_widgets_locales`, default off) is
    `--inspect-widgets` with exactly one exception. It allows GET `fetch` requests from the
    page's main frame to `https://job-boards.cdn.greenhouse.io:443` for
    `/locales/<segment>/<segment>.json`, each segment 1-32 of `[A-Za-z0-9_-]`. A query string or
    a redirect is refused.
  - It is enforced twice: by the page's request filter, which counts the first failing element,
    and by the browser context's interception layer (`SubresourceRule.path`).
  - In this mode only, the page's `fetch()` is given `redirect: 'error'` before any page script
    runs. A followed redirect of a locale request stops the observation. The owner's approval
    should know this changes the page's environment slightly.
  - Timing, this mode only: a 1500 ms settle window, equal to the adapter's `SETTLE_MS`, and a
    50 s inspection. Every earlier mode and limit is unchanged.
  - Locale responses are never read, kept or printed.
  - Known limit: a locale file whose name has a dot (`common.3f2a.json`), or a segment over 32
    characters, would be refused and counted as such.
  - **The run needs the owner's single-use approval and a pinned revision with passing CI.**
    Nothing was run against any real site. The pilot's own rule (`live.subresources`) is
    unchanged: it does not get the locale exception.
- **Result: still 0 of 7, each for a stated reason** (`docs/activation-status.md`). Nothing was
  relaxed. No synthetic evidence counts, and no observation or consent was recorded.
- **Authorization at run time:**
  - The register is read at every protected step, with today's date. An authorization that ends
    while an attempt waits stops it at the next step, in the running process (tested).
  - Removing an entry is a code change. A running API or worker keeps the register it imported,
    so a withdrawal takes effect when they restart. To stop at once: stop the worker
    (`docker compose stop worker`), or revoke an application's approval in the app. Both take
    effect immediately (D65, tested).
  - Per-application approvals live in the database, never in code, so no ordinary approval needs
    a code change.
- **Production configuration** means `NOEFFORTS_ENV=production` on the owner's own machine, ports
  bound to `127.0.0.1`. It needs no public hosting, domain, TLS or paid infrastructure. It is
  required because it is where fixture origins are refused, real Greenhouse hosts are reachable,
  and container isolation is enforced.
- **D104 timing:**
  - A list is read every 250 ms. It counts as settled after three identical reads (at least
    500 ms unchanged) with nothing loading, within 1.5 s, or 5 s on a stand-in.
  - Three reads are not proof that the list cannot change later. The re-read at selection, the
    readback before the send gate and the drift checks before the disclosure gate catch later
    changes.
- **D105 semantics:**
  - Each item is approved in its own transaction. A refused item leaves the others, and the
    answer lists each result.
  - The same batch sent twice creates nothing new: the existing approval is returned, with its
    own expiry.
  - Items approved at different times expire at different times.
  - Nothing is ever all-or-nothing, and nothing is queued (tested).
- **Unchanged:** every gate; `SCHEMA_VERSION` (3); no migration.

## D107 — Read-only path B run once (run #10): no locale file allowed; path refusals made explainable (2026-11-01)

- **Why:** the owner, on 2026-11-01: "I approve one read-only run B (inspect_widgets_locales)
  of the Greenhouse read-only check on branch readonly-inspect-a8d07af, single use, within the
  Path B limits in docs/greenhouse-readonly-compatibility-proposal.md." It also said: "This
  approval does not authorize another live run, applicant-data disclosure, uploads,
  submission, or a live-support upgrade."
- **Run:** manual run #10 (Actions run 41279694718), from `readonly-inspect-a8d07af`.
  - Head SHA `a8d07af`, verified before dispatch and in the run record; CI #147 passed on it.
  - Only `inspect_widgets_locales` was enabled.
  - Result: a policy stop, exit 7. Record: `docs/greenhouse-compatibility-report.md`.
- **What it showed:**
  - The approved rule allowed **no** locale request: all 12 failed its `path` element. So the
    run did not test whether the dropdowns wait on the language files, and that explanation
    stays open.
  - 6 of the 7 dropdowns reached were `not_opened` within the adapter's 1.5 s.
  - On `q11` the page reacted, with a class-name hint, a hidden control and requests to other
    Greenhouse hosts. Its POST was blocked before sending and stopped the inspection, as the
    approved scope says.
  - Readiness is unchanged: 0 of 7.
- **Decided:**
  - **No retry and no wider rule.** The run is used up. A rule that fits the real locale paths
    would be a new reviewed change, and running it a new approval. Neither is requested.
  - **The next justified local work is diagnostic.** "path" alone could not say why the real
    paths failed. A refused locale path now records which properties failed (`unprintable`,
    `prefix`, `segments`, `extension`, `dots`, `characters`, `length`) and a bucket of its
    longest segment's length (`0-32`, `33-64`, `65-128`, `129+`). It never records the path, a
    segment or an exact length (`gh_readonly.locale_path_detail`; summary key
    `inspection.locale_path_refusals`).
    - It allows nothing: `locale_refusal` and the context layer's path rule are unchanged.
    - The pinned branch was not moved.
  - **The pilot is unaffected.** It never gets the locale exception (`live.subresources`).
    `dropdowns.verify` refuses any data request made during a dropdown action. So `q11`'s
    behaviour on a real rehearsal would stop the attempt before anything is entered.
    `_data_refusal` refuses any data request during the action, whatever its origin or method.
    The test is `test_greenhouse_controls.py`,
    `test_on_a_destination_that_is_not_a_stand_in_they_stop_before_anything_is_entered`, with
    a same-origin GET; the code makes no exception for other origins.

## D108 — A dropdown that sends is refused whatever it sends with; widget observations kept apart (2026-11-01)

- **Why:** the owner, on 2026-11-01, after D107: resolve two local evidence gaps, "A. A
  synthetic dropdown that attempts a cross-origin POST when opened … B. Separate widget
  observations", without repeating the experiment or widening its network permissions.
- **A. A dropdown that sends when opened.**
  - **Coverage before:** `late_post` (a same-origin POST fetch) and the `hostile` page (beacons
    and fetches at page load, `test_browser_cannot_reach_other_origins`). Nothing covered a
    POST that opening a dropdown sends to another origin.
  - **Gap found:** the adapter counted only XHR, fetch, event-source and WebSocket requests made
    during a dropdown action. A `navigator.sendBeacon` POST is none of these. The browser's
    isolation blocked it, so it never arrived, but the attempt went on and submitted. That was
    shown by sabotage: both beacon cases ended `confirmed`.
  - **Fix:** any request that is not a GET, of any type, made during a dropdown action now
    counts like a data request (`dropdowns._observe`). The existing reasons apply: "its options
    load from the network (not verified)" on a real destination, "… in a way NoEfforts does not
    accept" on a stand-in. Nothing is allowed that was refused before.
  - **Tests:** the fixture dropdown `open_beacon` opens normally and also POSTs to another
    origin, by fetch or by beacon. Each way, on a stand-in and as on a real destination:
    - an independent listener on that origin records nothing;
    - the attempt ends `failed_safe` at the dropdown check;
    - the receiver saw only GETs, with no disclosure and no acceptance.
    A control without the POST goes through.
- **B. Widget observations kept apart** (the read-only inspection, `gh_readonly`):
  - Each widget now carries `observations`:
    - `existing_value_changed`: true, false, or null for unknown;
    - `controls_added` and `controls_removed`;
    - `focus_left_target`;
    - `class_hint_appeared`;
    - `visible_option_list`.
    They replace `value_changed`, which was true whenever the list of control values differed,
    so a control merely added set it.
  - `compare_controls` compares only controls present before and after under an id used once.
    A control without an id, or with an id used twice, whose value differs gives "unknown". A
    control added or removed is counted as such and never as a value change.
  - **A class-name hint alone is not an opening:** `classify_open` returns `undetermined` (with
    evidence `class_hint`). With an expanded state or a popup it is unchanged. The adapter
    shares the classifier and refuses either way.
  - **Each change still stops the inspection, now with its own reason:** "opening changed a
    value or selected an option"; "opening added or removed a control"; "opening changed a
    control that cannot be identified". The adapter refuses each with the matching reason.
  - Values, identifiers and class names are compared inside the worker. The summary carries
    only booleans and counts (tested: none of the fixture's values, ids or class names appears
    in the published text).
- **Not done, deliberately:**
  - No live run, no wider rule, and no reclassification of run #10. Its `q11` record was made by
    the earlier code, and these categories do not explain it after the fact.
  - The pilot's network rules are unchanged.

## D109 — Greenhouse first: the dropdown blocker, react-select readback, and read-only path C (2026-11-01)

- **Why:** the owner, on 2026-11-01: make NoEfforts work on real employer application flows,
  Greenhouse first. "Identify the smallest concrete change needed to advance real compatibility.
  Separate implementation defects from restrictions imposed by the inspection harness. Do not
  relax production safeguards merely to make an inspection succeed." No live run, applicant
  data, upload, login or submission is authorized by that message.
- **The blocker, from the evidence:**
  - Runs #9 and #10 clicked each real dropdown's input (`role=combobox`, `aria-haspopup`,
    `aria-autocomplete=list`, a box under 8 px). No list opened.
  - Those clicks made the page request locale files: 7 in run #9 and 8 in run #10, all refused.
    So the clicks reached live page code, and the page asked for translations when a dropdown
    was used. This is the strongest single indication, still unconfirmed, that the lists wait on
    those files.
  - Run #10's exact rule matched none of them: all failed `path`.
- **The owner's previous bot** (static review of its newer version, uploaded 2026-11-01;
  `docs/legacy-audit.md`, addendum) points the same way and adds two concrete differences:
  - it clicked the react-select wrapper `.select__control`, not the input;
  - it read a choice from the wrapper's displayed text, never from the input's value.
  It ran with nothing refused, so its locale files loaded. Which difference mattered cannot be
  told statically.
- **Defects separated from harness restrictions:**
  - **A real defect in the adapter (fixed):** the readback of a chosen dropdown read the
    input's value. On react-select markup the input holds only typed search text; the choice is
    a `select__single-value` element.
    - The previous readback would have abandoned a real react-select form after correct choices.
      Shown on a react-select-like fixture by sabotage: "3 field(s) did not keep their values".
    - Now, when the control sits in a `select__control` container, readback requires exactly
      one single value whose text is the approved label, no leftover search text and no
      multi-value chips. Elsewhere it is unchanged. The adapter's "did opening change a value"
      check and the inspection's state include the displayed choice too.
  - **A missing strategy (added):** `click_container`, one click on the control's react-select
    container, tried after `click_control`. It is not applicable without such a container, and
    the same verification applies (exact list, nothing changed, no data request).
  - **A harness restriction, kept:** the pilot (`live.subresources`) and the read-only check
    refuse locale files. It is not relaxed. Allowing them in the pilot would be a reviewed change,
    made only if a read-only run shows they are needed and sufficient.
- **Read-only path C** (`--inspect-dropdowns`, workflow input `inspect_dropdowns`, default off,
  NOT APPROVED). It is path B with:
  - **A rule that keeps run #10's observed shape:** GET `fetch` from the main frame to
    `job-boards.cdn.greenhouse.io:443`, `/locales/<segment>/<segment>.json`, no query, no
    redirect. Each segment is 1-128 characters of `[A-Za-z0-9_~+@-]` plus single dots, never
    first and never doubled. A hashed or long name passes; `..`, `%`, a leading dot, another
    segment count or a query do not. The context layer enforces the same pattern.
  - **Outcomes of allowed locale requests,** by status class (`2xx`, `4xx`, `failed`, …) from
    the response status only. The body is never read. An allowed request is not a loaded one.
  - **One click on the react-select container** when the control's own click showed no
    opening, then Escape. It is recorded separately (`container_attempt`, `opened_by`).
  - **Whether each control sits in react-select markup,** as booleans (`markup`). The adapter's
    readback depends on it. No class name is published.
  - **Limits:** 40 actions, 80 s inspection, 120 s observation, 180 s run (inside the 200 s
    outer kill); everything else is path B's.
  - Every stop is unchanged (any non-GET request, a value change, a control added or removed,
    a submission attempt, a dialog, a file chooser, a challenge, a navigation, a redirected
    locale request), and nothing is retried.
- **Not done:**
  - No live run.
  - No change to the pilot's network rules or to readiness.
  - No reclassification of runs #9 and #10.
  - Every forbidden legacy behaviour (addendum) is excluded.

## D110 — Read-only run C (run #11): the real dropdowns open once their locale files load (2026-11-01)

- **Why:** the owner, on 2026-11-01: "I approve one read-only run C (inspect_dropdowns) of the
  Greenhouse read-only check on branch readonly-inspect-efceea4, single use, within the Path C
  limits." The approval excludes any further live run, disclosure, upload, submission and pilot
  network change without a new approval.
- **Run:** manual run #11 (Actions run 41330028697), on `efceea4`, where CI #151 passed all four
  jobs. It completed with no stop. Record: `docs/greenhouse-compatibility-report.md`.
- **Result:**
  - The 2 locale files the page requested at load were allowed and loaded (2xx).
  - All 12 dropdowns inspected opened at the control's own click, and 11 lists were read
    completely. The container fallback was never needed.
  - The 7 dropdowns mapped to job-data questions show exactly the job data's options.
  - All 12 sit in react-select markup.
  - Still open:
    - `u1` (required, in the phone group): a 244-option list, read but not mapped;
    - `u3` (required, standalone): opened without readable options, while a request to
      `my.greenhouse.io` was refused;
    - location: absent at load.
- **Interpretation:** with run #10 (same click and window, locale files refused, nothing
  opened), this strongly supports the locale gate. It is one combined observation on one
  posting, and the page also changed between the runs, so it does not prove causation alone.
- **Correction:** the request said the run would stop on "any POST or other non-GET request".
  The code, unchanged since path B, blocks and records a non-GET made at page load and stops only
  on one made during an inspection action. One telemetry POST at load was blocked, never sent,
  and did not stop the run. The proposal now states the distinction. Any future request will
  quote it exactly.
- **Decided:**
  - **No further live dropdown experiment.** The question it was for is answered on this
    posting.
  - **The pilot is not changed on main.** The same narrow locale exception for the pilot
    (`live.subresources` gains path C's rule, and pilot pages get the fetch redirect guard) is
    prepared on a branch for the owner's approval as part of milestone B. It is not merged.
  - **Readiness is unchanged (0 of 7):**
    - condition 1 needs every required dropdown's complete list (`u3`'s was not readable) and
      the pilot able to open them;
    - condition 2 needs `u1` and `u3` mapped by evidence.
  - **Milestone B cannot use this posting:** it requires a location (with page-managed
    coordinates) and two unmapped required dropdowns, so capture would stop it. A first
    disclosure-only rehearsal needs a posting without them; the request lists every remaining
    prerequisite.
- **Corrected 2026-11-01 by D111:** run #11 did not comply with the authorized stop on any
  non-GET request. Its result shows locale loading and ordinary-click opening observed together,
  not causation.

## D111 — Locale exception integrated; run #11's stop discrepancy corrected and fixed; hidden search inputs; the milestone-B handoff (2026-11-01)

- **Why:** the owner, on 2026-11-01: "I authorize integrating the narrow locale exception and
  redirect guard prepared on milestone-b-pilot-locale, subject to review and validation. …
  This authorizes a code change, not a live rehearsal, upload or submission." The same message
  required a dated correction of run #11's compliance claim, the promised non-GET stop in code,
  local work on `u1`, `u3`, location and hidden search inputs, and one in-app handoff.

### 1. The locale exception, integrated after review

- **Reviewed diff** (`5230841`, `2d17597`, plus this entry's commits): `live.subresources`
  gains read-only path C's exact rule, and pilot pages get its fetch redirect guard.
  - **The rule:** GET `fetch` only, from the page's main frame, on
    `https://job-boards.cdn.greenhouse.io:443`, path `/locales/<segment>/<segment>.json`, no
    query, no `..`.
  - **Init script:** `live.init_scripts` adds `redirect: 'error'` to every page `fetch()`, and
    the runner installs it before navigating.
- **Review findings, fixed before integration:**
  - **Main frame:** a request admitted only by the path-limited rule now passes only from the
    page's main frame, where the guard runs (`2d17597`).
  - **Followed redirects:** a redirect the browser follows for such a request (netns and
    container modes do not route redirect hops) is detected (`EgressLog.redirected`). It stops
    the attempt before anything is entered and again before submitting
    (`LOCALE_REDIRECTED`). Path C stopped on the same thing.
  - **Request cap:** such requests are capped per session at path C's page-request budget (150);
    beyond it they are refused before sending.
- **Unchanged:**
  - The pilot is off by default.
  - Every gate still needs the owner's recorded permissions (none are recorded) and the
    per-application approval.
  - The stand-in gets no rule and no init script.

### 2. Run #11: what was authorized and what the code did (dated correction)

- **Authorized** (run C approval): the run stops on "Any POST or other non-GET request", among
  other stops.
- **Implemented at `efceea4`:**
  - a non-GET request during an inspection action stopped the run;
  - one during page load was blocked before sending and recorded, but did not stop the run.
  That had been the behaviour since path B; the request did not say so.
- **What happened:** the run's own summary reports one POST fetch to `c.spl.greenhouse.io` at
  page load as blocked. The run continued and took its 24 actions.
- **Limits on the compliance claim:**
  - Run #11 did not comply with the authorized stop condition. The actions after that POST
    were outside the approved protocol.
  - "Not transmitted" rests on the run's own record of what it blocked, not on an independent
    observer.
- **What the observations still show:** on this posting, locale loading and opening at an
  ordinary click were observed together. The experiment did not establish that one caused the
  other.
- **History is kept:**
  - The proposal's Stops row is restored to the approved wording. D110 had edited it in place,
    and its "Correction" bullet says the proposal states the distinction; that edit is reverted.
  - Dated corrections are added to the proposal, the compatibility report and D110.

### 3. The stop, fixed locally

- In every widget-inspection mode, a non-GET request now stops the run wherever it happens:
  - **Blocked before sending.**
  - **Latched at once:** every later request is refused.
  - **No inspection action follows,** at load or between actions.
  - **The sanitized reason is kept** ("a non-GET request was attempted").
  - **Never retried.**
- **Tests:**
  - a page-load beacon and a dropdown beacon, each against an independent listener that
    receives nothing;
  - the CLI process (`test_widget_inspection.py`, `test_readonly_cli_process.py`).
- No live run was needed or made.

### 4. The remaining gaps, worked from the evidence

- **Hidden search input (run #11's `u2`):** observed as
  - a `search` input with the combobox role;
  - no hidden attribute, but not visible;
  - no required signal of any kind;
  - in the group of a control that a job-data question maps to.
  - **The finding:** capture and the adapter read only attributes, so they would have made it
    a required, blocking "unanswered question" (and, on the live page, a new field).
  - **The rule:** it is not an unanswered question, and NoEfforts never touches it, only while
    the live page shows all of these:
    - it is hidden, unrequired and empty;
    - the question whose group it is in is shown.
    - **Where the live page is checked:** before anything is entered, and after filling (the
      runner's re-check).
  - **Anything else stops the attempt:** shown, required by the control or its group, or holding
    a value. A standalone hidden search input, or one whose group holds two questions, stays a
    blocking checkpoint.
  - **Never inferred:** what it is for, its position or its label.
  - **Implementation:** `widget="hidden_search"`; the fixture `gh2_hidden_search`, built from
    that one observation; `tests/test_hidden_search.py` (receiver ledger).
  - **Package shape:** unchanged, so `SCHEMA_VERSION` stays 3. Only a form with such an input
    carries `.answers[].widget`, as for D104.
- **`u3` (required, standalone, no readable options; a request to `my.greenhouse.io` refused
  during its action):**
  - No host or endpoint is added because a widget asks for one.
  - **New regressions:**
    - mapped dropdowns whose options need another host stop before disclosure, and an
      independent listener receives nothing;
    - a required unlisted dropdown with that dependency is a checkpoint, and nothing can be
      approved;
    - no pilot rule admits another Greenhouse host or a data endpoint.
  - What the request was for is not known; `u3` stays blocking.
- **`u1` (required, in the phone group, 244 options):**
  - The existing rule already meets the owner's conditions: an approved phone number that
    states its calling code, and exactly one option with that code; never a shared code, never
    residence.
  - **It cannot apply to `u1` yet. Three facts are missing:**
    - its label (the rule accepts four exact names, and the label was not recorded);
    - whether its option texts state calling codes (not recorded);
    - its options at capture: react-select lists exist only once opened, and capture reads
      the page without its scripts.
  - Recognising it by its position or its 244 options is refused.
  - **The gap is specific:** a private, in-app read of that one control's label and options on
    the live page. That needs a browser-based capture under permission 2 (open), which does not
    exist yet. That is the next implementation step for `u1`; it needs no public experiment.
  - Until then, `u1` stays an unlisted, blocking control.
- **Location:**
  - The job data requires `location` (text), with page-managed `latitude`/`longitude`.
  - No location control was at load, and none appeared after the 24 actions.
  - Capture therefore refuses this posting (`controls_do_not_match`, an absent required
    field).
  - Nothing shows whether the page asks for a location at all, or how. Nothing is changed:
    filling a value the page does not show would be a guess.
  - **The gap:** how and whether the page presents the location question.

### 5. The milestone-B handoff, in the app

- **Where:** `GET /api/applications/{id}/rehearsal-handoff` and a panel on the application's
  page.
- **What it shows, for a real Greenhouse job (or a form read through the pilot):**
  - the destination;
  - the exact answers and documents of the current package, and which of them filling and
    uploading would disclose;
  - what that exposes;
  - the stop before submit and what enforces it;
  - every prerequisite, read from the system as it is now: switch, production mode, container
    isolation, owner account, a Greenhouse posting, permissions 1-3 each, capture through the
    pilot, no open or blocking question, and the per-application rehearsal approval;
  - permission 4, kept separate;
  - the evidence a rehearsal leaves, including that a real employer has no independent ledger.
- **Limits:**
  - It reads and grants nothing.
  - It is 404 for anyone else.
  - It is never logged.
- **No personal facts were entered or derived.** Tests use synthetic data
  (`tests/test_rehearsal_handoff.py`).

### Found while validating

- **Chromium's favicon request:** when a page names no icon, Chromium itself may GET the page
  origin's `/favicon.ico` after the load, outside Playwright's request routing. It happened in 2
  of 6 local runs that stopped right after the load: the latch had refused every routed request,
  and this one still arrived.
- **What it is:** a GET to the page's own origin that carries nothing of the applicant.
- **Effect on earlier records:** read-only summaries count routed requests only, so a real run
  may have made this request without recording it. Their request counts are counts of routed
  requests.
- **Tests:** request lists leave out exactly that request (`BROWSER_OWN`) and compare everything
  else exactly.

### Decided

- **Readiness is unchanged (0 of 7):**
  - condition 1: `u3`'s list was not readable, and the pilot has not run;
  - condition 2: `u1` and `u3` are not mapped;
  - condition 3: location.
- **Milestone B on the observed posting** is blocked by its absent location control, `u1` and
  `u3`, at capture, before anything is sent.
- **Permissions:** 1-3 and an application-specific rehearsal approval must exist before any
  rehearsal; permission 4 stays separate.
- **Not authorized and not done:** no live run, rehearsal, upload or submission.

## D112 — The owner's permission for the Greenhouse pilot, recorded; its limit enforced (2026-11-01)

- **The owner's words (2026-11-01, verbatim):**
  - "I have all my approval. Do and make it production ready."
  - Asked which steps, until when and how many (the §4 form's blanks), the owner chose
    "Everything before next week end." and "5 applications (Recommended)".
- **Recorded** (`app/core/authorizations.py`, one entry):
  - **Steps:** all four pilot steps: 1 read, 2 open, 3 disclose (rehearsal), 4 submit.
  - **Postings and data:** only postings the owner approves in the NoEfforts app, one at a time,
    and only what each approved package contains.
  - **Ends:** 2026-11-06. "Before next week end" is read conservatively, as the last weekday
    before next weekend. If the owner meant through the weekend, a new entry with their words
    extends it.
  - **Limit:** at most 5 attempts that pass the disclosure gate, rehearsals and submissions
    alike, counted from 2026-11-01.
- **Enforced:**
  - The limit is checked at the disclosure gate, under one advisory lock, so two attempts
    cannot both take the last place.
  - Beyond it, an attempt stops with nothing entered (`live_limit_reached`).
  - The end date is checked at every gate. After it, the pilot refuses again on its own.
  - The in-app handoff shows "Attempts left".
- **Unchanged:**
  - Every application still needs the owner's in-app approval of its exact package.
  - The first application to each employer path is a rehearsal (E6).
  - Anything not understood stops the attempt, and nothing is retried after the final click.
  - The inbox stays unauthorized.
  - The server must still be switched on, in production mode, with container isolation and the
    owner's account named (`docs/activation-status.md` §5). That happens on the owner's
    machine; nothing was started from this repository.
- **Tests:**
  - conftest empties the real register for every test, so tests never run under the owner's
    permission.
  - `test_authorizations.py` checks the shipped entry against these words and its days.
  - `test_greenhouse_live.py` checks that the limit stops the next attempt before anything is
    entered (receiver ledger).
  - `test_rehearsal_handoff.py` checks the count.
- **Production check:** `scripts/verify-local.sh --pilot` (with `scripts/check_env.py --pilot`)
  checks that the switch is on, exactly one owner account is named and the pilot overlay is
  valid, printing key names only. The overlay was validated here with a synthetic `.env`; this
  sandbox has no Docker daemon, so the stack was not started.
- **Readiness:** 1 of 7: condition 6 (the recorded permissions) is met by this entry, and only
  while it holds. The other six still need their own evidence: a real rehearsal, a real
  submission, and the controls of the chosen posting.
- **Not done by NoEfforts:** no posting was read, opened, filled or submitted. Those run only on
  the owner's server, for packages the owner approves there.

## D113 — Freehire discovery and automatic applying, on by default (2026-11-02)

- **The owner's words (2026-11-02, verbatim):**
  - "enable freehire job discovery on default and also enable auto job apply on default."
  - Asked what "auto job apply on by default" should mean, given that two of the options change
    rules the owner set earlier, the owner chose **"Fully automatic"**: "Discover, fill and
    submit without asking you, for fully answered packages only, within a daily cap and your
    recorded permission. This drops the rule that every real submission needs your explicit
    approval."
  - For Freehire, the owner chose **"Search + daily auto-check"**: "Freehire is on by default
    for your account: typing a search on Discover and importing reads freehire.me directly, with
    no command-line approval. Nothing runs on its own." and "your Discover searches are also
    re-checked automatically once a day, with new postings added to your jobs and noted in
    notifications."
- **What changes:**
  - **Defaults:** outside tests (`Settings._d113_defaults`, Compose and `.env.example`):
    Freehire discovery (`["freehire"]`, `https://freehire.me`), the Greenhouse pilot switch and
    automatic applying are on. Anything set explicitly keeps its value; tests keep every outside
    service off.
  - **Freehire:**
    - The owner's own search on Discover is the run approval for that read. It is recorded as
      one, with the D55 row and audit, and used at once.
    - A search with words is re-checked once a day for 90 days, as a D56 watch.
    - The owner is `DISCOVERY_OWNER_EMAILS`, or the pilot's owner when that is empty.
    - `discovery_search_approves=false` restores D55 exactly.
  - **The rule changes:** CLAUDE.md's "No real submission without explicit user approval" now
    reads "without the owner's explicit approval: per application, or the owner's recorded
    standing rule (D113) within its limits".
- **The owner's standing rule to apply automatically** (`app/modules/autoapply`):
  - **When it runs:** a worker task every 5 minutes, for the pilot's owner only.
  - **Where it may act:** only where the pilot may: switch, production, container isolation,
    the owner's account, and every step of the recorded permission. That permission is D112's
    end (2026-11-06) and limit (5 attempts past the disclosure gate, shared), with D113's
    register entry for packages the rule approves.
  - **For each Greenhouse job post** among the owner's jobs that is not closed, excluded or a
    possible duplicate, and with no checked preference unmet, it:
    1. reads the post (once a day at most);
    2. makes the application;
    3. builds the package.
  - **It approves only a package with nothing open or awaiting consent, no validation error and
    no control NoEfforts cannot fill.** The approval is the same one the owner gives in the app
    (exact version and content hash).
  - **The first application to each employer path is a rehearsal (E6);** the submission follows
    once it held.
  - **Caps:** at most `auto_apply_daily_cap` (5) approvals a day.
  - **No retries:** an attempt that stopped, failed or ended unknown is never retried.
  - **Every gate still applies:** live re-checks, readback, the rehearsal stop, the send gate,
    no retry after the final click, `submitted_unconfirmed`.
  - **What the owner sees:** each action or skip is an event with a fixed reason code, on the
    Tracker's "Automatic applying" card. The owner pauses or resumes it there.
- **Unchanged:**
  - Facts and preferences stay apart. Unknown stays unknown: anything not resolved from the
    owner's own approved facts and answers waits for the owner.
  - No CAPTCHA or MFA bypass. OTP stays a manual checkpoint.
  - Inbox reading stays unauthorized.
  - Applying runs only on the owner's server; nothing was applied to from this repository.
- **Tests:**
  - `tests/test_auto_apply.py`: the whole rule against the stand-in board, with the receiver
    ledger as oracle:
    - it waits for open questions, then rehearses, then submits once, then stops;
    - pause; the daily cap and the permission limit; never retrying a stopped attempt;
    - another account; the defaults.
  - Sabotage checks: dropping the pause check failed, and so did dropping the no-retry check.
  - `tests/test_freehire_live_read.py`: D55 kept behind the setting; the search as the approval
    and its daily watch; another account refused.

## D114 — Every account served; each account's own choice to apply automatically (2026-11-02)

- **The owner's words (2026-11-02, verbatim):**
  "It should fill the stuffs perfect and enable all the stuffs for everyone. enable each and everything on default regardless of the user hierarchy."
- **Every account is served** (`Settings.all_accounts`, on by default outside tests;
  `app/core/accounts.py`). Features that served only the accounts named in a setting now serve
  every account:
  - the Greenhouse pilot;
  - live Freehire discovery, its search approval and daily watches;
  - AI drafting, where each account still gives its own consent and the server's daily budget
    is shared;
  - employer job boards (`board_sources_enabled`), now on by default.
- **Automatic applying is open to every account, but each account turns it on for itself.** It
  is on by default for the server owner (`NOEFFORTS_LIVE_OWNER_EMAILS`), who chose it (D113).
  Every other account starts off, with the consent text shown, until that account turns it on.
  - **Why not on for everyone:** submitting applications in someone's name, with their personal
    data, needs that person's own choice. The server owner's words cannot give it for them.
  - The worker examines every account and acts only for those whose choice is on.
- **Not opened:** the mailbox (D101). The server holds one Gmail token, the owner's, and reading
  it stays unauthorized (D103).
- **Recorded** (`authorizations.py`, D114): the pilot's four steps for every account's own
  packages, each approved by that account or by that account's own standing rule.
  - Same end date (2026-11-06).
  - Same **shared** limit of 5 attempts past the disclosure gate, now counting every account's
    attempts. It needs renewing for wider use.
- **Tests** (`tests/test_auto_apply.py`):
  - another account is served by the pilot, starts off, never has anything done in its name
    before it chooses, and once it turns the rule on is rehearsed like the owner;
  - the mailbox stays the owner's;
  - `test_authorizations.py` checks the register.

## D115 — The answer brain: your saved answers suggested for reworded questions, learned per account (2026-11-02)

- **The owner's words (2026-11-02, verbatim):**
  "Older application was using self learning, whatever question shown on the application gets me the pop up, then I select the answer from it and then it was storing that answer into the anaswer_brain and then whenever the same question appear, it writes the answer from that. I have used some self learning XGBoost and LightGBM. Make sure we use it here too."
- **The same question:** the answer you give is saved for that exact question by default
  ("Reuse for this exact question" starts ticked where reuse is allowed, D51) and the resolver
  reuses it without asking (`_from_bank`), as the earlier bot did.
- **A reworded question** (`app/modules/learning`): one of your own saved answers is suggested.
  Nothing is filled in until you choose "Use this" (answered here, and saved for this wording
  too) or "Not this" (never suggested again for it).
  - Ranking: your own model, LightGBM, else XGBoost, trained on your verdicts only, after each
    one. Below 12 verdicts with both kinds, a fixed blend of similarities ranks instead.
  - Never suggested: a different kind of answer; wording that differs on numbers, negation or
    countries ("…in the US?" vs "…in Canada?"); options the form no longer has; sensitive,
    protected or legal questions; anything the bank rules never reuse (D51: authorization,
    sponsorship, pay, place, the employer, time-bound).
  - A verdict keeps numbers only (similarities), never question or answer text. Both tables are
    in the account export and deleted with the account; "Forget" deletes them.
- **The "pop-up":** when automatic applying (D113) is held by open questions, the notification
  "Questions are waiting for your answers" links to the application, where the suggestions are.
- **Not found in the shared legacy files:** the XGBoost/LightGBM code itself (only the `.py`
  files shared were read); this is written fresh.

## D116 — Greenhouse real-page mechanics rebuilt from the legacy bot (2026-11-02)

- **The owner's words (2026-11-02, verbatim):**
  "I want you to make it 100% working for greenhouse. Because my previous application was working perfect. I want to improve that one into this."
- **Why:** a review of the legacy `apply.py` found that the live Greenhouse adapter relied on
  three details only the local approximation has (a declared submit path, an upload status
  element, a confirmation element) and had no security-code step. The legacy author's notes,
  from about 700 real applications, describe the real behaviour. Each is rebuilt as a
  fail-closed recognition, never copied, and is still unobserved by NoEfforts itself:
  - a form that declares no submit address is bound to its own job page: only a POST to that
    page, on the same host, counts as this attempt's answer;
  - the emailed security code is a checkpoint, also when its boxes appear before the click;
    typed as keystrokes, read back, sent with one click; a wrong code is reported by the page;
  - an upload is acknowledged by the approved file name in the control's own group, with no
    upload error there; attachments are uploaded first, then the page settles;
  - a confirmation page (`…/confirmation`) or text on the same posting, absent before the click;
  - the page's own validation blocking the click is `rejected` only when no request left the
    page; a click that raised is watched, never repeated; a firewall block page stops before
    anything is entered; answer shapes the page type cannot fill are refused before disclosure.
- **Not ported:** stealth, behaviour imitation, CAPTCHA handling, automatic consent, clicking
  again after a rejection, guessing answers.
- **Tested** against the receiver's `gh2_live_like` mode (FIXTURE ASSUMPTIONS).

## D117 — Verification codes read from the owner's own mailbox (2026-11-02)

- **The owner's words (2026-11-02, verbatim):**
  "I want you to read my email and search for the greenhouse the most recent otp copy it and paste it in the greenhouse applications. And what about the rest greenhouse applications." and "Continue and you are approved for all."
- **What changes:** this lifts the owner's earlier "Do not: Read my inbox or retrieve OTPs" for
  verification codes only. Recorded (`authorizations.py`, D117): `read_codes` and `enter_codes`
  for the owner's own mailbox and the owner's own applications, through 2026-11-06 (the owner's
  words set no end; read with the pilot permission the codes serve). Application emails are
  still not read (`read_application_email` is not recorded).
- **How** (D101's code reader, `inbox/service.fill_codes`, every 15 seconds): while one of the
  owner's applications waits at a code step, mail from the code senders received since that
  attempt began filling in is read; a code is entered only when exactly one reads as a code.
  When several applications overlap, the email naming this application's employer in its
  subject is used ("Security code for your application to <employer>", legacy notes).
  Greenhouse's letters-only, mixed-case codes are read exactly as written. A message is used
  once; a rejected code is never entered again; Resend is never clicked.
- **Defaults:** outside tests the inbox *server* is on (`inbox_enabled`) for the owner
  (`inbox_owner_emails` defaults to `live_owner_emails`), but every per-account mailbox-processing
  option is opt-in — off by default, including codes (see the 2026-11-04 amendment below; this
  supersedes the original "codes on" default). It still needs the owner's Gmail token, made once
  with `python -m app.modules.inbox.connect` on the owner's machine. Other accounts type their own
  codes: the server's mailbox is the owner's (D114).
- **Not kept:** a code is never stored, logged, put in audit or evidence, or shown.
- **Amendment (2026-11-04) — the code toggle is now opt-in (default off).** Every
  mailbox-processing option starts **off** for a new account: verification codes
  (`codes_enabled`), application-email tracking (`tracking_enabled`) and automatic status
  updates (`auto_apply`). Only the *toggle default* moved from on to off; the D117
  *authorization* above (what the owner's recorded words permit) is unchanged, so this needs no
  new recorded authorization. The owner turns each option on separately; connecting Gmail, or
  turning one on, never turns on another.
  - **New-account defaults:** all three off. `inbox/service.settings_of` creates
    `InboxSettings(user_id=...)` with no explicit values, so each falls to the model column
    `default=False` (`inbox/models.py`).
  - **Existing accounts: unaffected, never reset.** `settings_of` creates a row only when none
    exists (`if st is None`); an existing owner's stored choices are read back as-is. An owner who
    had codes on keeps codes on.
  - **DB default / service fallback / UI initialization agree on off.** The model columns are
    `default=False` (ORM-level); `auto_apply` additionally carries a DB `server_default=false`
    (migration `c3f1a7e5b921`); `codes_enabled`/`tracking_enabled` are `NOT NULL` with no
    `server_default` and no raw-insert path, so the ORM default is the only creation path. The UI
    (`InboxCard.jsx`) renders each checkbox from the server value, with the `auto_apply` box
    disabled until tracking is on. All three surfaces initialize off.
  - **Data migration: none.** No migration changes a default or rewrites a row. The only
    migration in this change (`d4e8f1a2b3c7`) adds the additive `inbox_events.applied_outcome`
    column; it does not touch `inbox_settings`.

## D118 — The generic extractor reads only the application form and its aria-labelledby labels (2026-11-02)

- Ported from the legacy ATS adapters' page handling (their `.py` sources only; rebuilt).
- **One application form.** A page may hold a job-alert sign-up or newsletter form with its own
  email field and button (Recruitee, Breezy, Workable). `forms.extract_form_schema` now reads
  only the application form: the form holding a file upload, or the single form on the page.
  Two upload-bearing forms, or several forms and none with an upload, is ambiguous and falls
  back to the whole page, so nothing is dropped silently. The chosen form's action is recorded.
- **aria-labelledby labels.** A question whose text is linked by `aria-labelledby`, with no
  `<label>` (Recruitee, SmartRecruiters), is read, joining several ids in order. Only text the
  page links counts; a field with no label of any kind still stops the capture.
- Tests: `tests/test_form_scope_labels.py`. No real markup.

## D119 — The Greenhouse field catalogue is the official Job Board API; every documented field type is filled (2026-11-02)

- **The owner's request (2026-11-02):** use the official Greenhouse API docs
  (`grnhse/greenhouse-api-docs`) so the DOM filler covers every field, down to the minor ones.
- **Source of truth.** NoEfforts already builds the Greenhouse field catalogue from the
  official Job Board API, `GET /boards/{token}/jobs/{id}?questions=true`
  (`greenhouse.schema_from_api`): the API's own `questions`, `location_questions` and the
  `data_compliance` consent. The docs confirm the field types, and every documented question
  field type is mapped and filled by the DOM adapter (Playwright/Chromium), by the field's
  exact `name`/`id`:
  - `input_text` → text (email and phone by name), `textarea` → textarea, `input_file` → file,
    `multi_value_single_select` → a dropdown, `multi_value_multi_select` → checkboxes,
    `input_hidden` → a value the page itself sets (map coordinates): never typed, a checkpoint.
  - A field type the docs add later is an unsupported checkpoint, never silently dropped
    (`tests/test_greenhouse_api_coverage.py` pins the documented set to the mapper).
- **Not auto-filled, by rule.** The docs also describe `demographic_questions` and the
  government-contractor `compliance` section (EEOC: gender, race, veteran, disability) and the
  structured `educations[]` / `employments[]` history. These are not auto-answered:
  - demographics and legal attestations are **never inferred** (a non-negotiable rule); an EEOC
    answer is the applicant's own explicit per-application choice and is never saved for reuse;
  - education and employment history are filled from the applicant's own approved records, which
    is separate structured-field work.
  On the hosted page these appear as controls the job data's standard questions do not cover, so
  the adapter stops before disclosure (a checkpoint) rather than guessing. Surfacing them as
  questions the applicant answers is the next step, not auto-filling.
- **No API key, no API submission.** The pilot fills and submits through the browser only
  (D102/D116). The API is read-only here, for the catalogue; submitting through it would need
  the employer's key and is out of scope.

## D121 — EEOC and demographic questions surfaced as the applicant's own answers (2026-11-02)

- **The owner's request (2026-11-02):** "EEOC" — handle the EEOC questions.
- **What changes:** `greenhouse.schema_from_api` now extracts the Job Board API's `compliance[]`
  (EEOC: gender, race, veteran status, disability status) and `demographic_questions{}`
  (Greenhouse Inclusion) sections, which it skipped before. On the hosted page these would
  otherwise be controls the standard questions do not cover, so the adapter stopped the whole
  application (a blocking checkpoint). Now they are proper questions the applicant can answer.
- **Always the applicant's explicit choice, by rule:** every such field classifies as sensitive
  (`classify`: EEOC labels already do; demographic questions are keyed `demographic_question_<id>`
  and a classify rule marks them sensitive even when neutrally worded, e.g. "Favorite Color").
  Sensitive means: never inferred, never auto-filled, never saved for reuse, never drafted
  (C5/C15, a non-negotiable rule). The resolver leaves them for the applicant; the adapter fills
  only the exact option the applicant chose. The exact EEOC option labels, including the two
  decline options ("Decline To Self Identify", "I don't wish to answer"), come straight from the
  API and match our decline mapping (D79).
- **Consequence for automatic applying:** an application with EEOC/demographic questions is not
  fully resolved until the applicant answers them, so the standing rule (D113) does not
  auto-submit it — it waits (open_questions). That is correct: a demographic answer is never
  given without the person's own choice.
- **Fail-closed:** a `compliance`/`demographic` entry whose shape does not parse is skipped, so
  the section stays a page checkpoint rather than being guessed. A demographic question that
  offers a free-form ("type your own") option is shown as unsupported for the applicant to
  answer, never auto-filled.
- **Tests:** `tests/test_greenhouse_api_coverage.py` (extraction, sensitivity, decline options,
  malformed-entry skip). The end-to-end fill of an EEOC react-select on a real Greenhouse page
  is unobserved, so like the D104 location stand-ins it stays checkpoint-first until the pilot
  sees one.

## D122 — Self-identification: the owner's own EEOC/demographic answers, opt-in auto-fill (2026-11-02)

- **The owner's words (2026-11-02):** gave their own self-identification ("Male", "Asian, South
  Asian") and, asked, confirmed they want it filled automatically as their previous tool did
  ("My previous code use to select from the dropdown, type in the information").
- **Why this is allowed where inference is not.** The non-negotiable rule is that NoEfforts never
  *infers* demographics. This does not infer anything: it fills only the exact option labels the
  owner themselves recorded, and only when one matches the form exactly. D121 already surfaces
  EEOC/demographic questions as the applicant's explicit choice; D122 lets the owner make that
  choice once, in advance, for their own applications.
- **How** (`app/modules/profiles/models.py` `SelfIdentification`, `resolver._self_id_match`):
  a per-account row with `enabled` and `labels` (the option labels the owner identifies with).
  When enabled, a sensitive choice/multi question resolves from `labels` by exact (normalized)
  option match — a single-choice question only when exactly one option matches (never one of
  two), a multi-select fills every matching option. Source `self_identification`.
- **Safeguards (all kept):**
  - opt-in; off by default; off for every other account, scoped per user (cross-tenant 404).
  - the owner's typed values only — never inferred, never fuzzy-matched; anything not matched
    exactly stays a checkpoint (required) or blank (optional).
  - never saved to the answer bank, never drafted, never used for a decision or for anyone else.
  - "Decline to self-identify" is always still selectable, and the owner can record *that* as
    their value too.
  - enabling it is the owner's standing choice to include it, so a matched answer resolves
    directly (no per-application disclosure prompt); the audit event records only whether it is
    on and how many labels are saved, never the labels (demographic data).
  - the real values are entered in the app (Profile → Self-identification), never in the repo,
    tests or fixtures.
- **API:** `GET`/`PUT /profile/self-identification`. **Export/deletion:** the table is in the
  account export (`user_id`, `enabled`, `labels`, `updated_at`) and deleted with the account.
- **Tests:** `tests/test_self_identification.py` (off → left to you; on → exact fill, never
  saved; decline; no match → checkpoint; ambiguous → never guessed; wrong-question guard;
  per-account isolation). **UI:** a Self-identification card on the Profile page.

### D122 amendment (2026-11-03) — acceptance-review hardening

A review against explicit acceptance conditions found three gaps in the first cut; all are
fixed in `resolver._self_id_outcome` / `_resolve_sensitive`:

- **A per-application choice takes precedence over the standing preference.** The self-ID block
  now runs *after* the per-application consent handling, so an explicit `withhold` (declining
  this employer's question) is honoured and the standing preference never replaces it. The
  standing preference applies only where the owner has made no explicit per-application choice.
- **A multi-answer question is never submitted as a partial set.** A flat label list cannot
  prove a multi-select set is complete (e.g. the owner is "Asian, South Asian" but the form
  offers only "Asian"), so a substantive multi-select now becomes a **checkpoint**, not a
  silently partial answer. A multi-select *decline* is exclusive and complete, so it still
  auto-fills; a decline mixed with a substantive value is a checkpoint (never both). Single
  selects are unchanged: exactly one match fills, else a checkpoint.
- **The dependency is explicit.** A self-ID answer now carries a `self_identification`
  `fact_ref`, so changing or disabling the labels that produced it invalidates an approval
  through the established content-hash dependency (over and above the re-resolution that already
  changes the package when the preference changes).

Confirmed, not changed: self-ID values never enter the answer bank (`bankable = False`), the
answer-brain training set (`learning.service` vetoes `sensitive`/non-`bankable`), logs or
notifications; the **audit event** records only `enabled` + label count, while the **owner
export** includes the full `labels` (it is the owner's own data — "all my data" must be
complete); the row cascade-deletes with the account. Known limitation: substantive multi-select
self-ID (e.g. race/ethnicity with several values) is a checkpoint until the self-ID data model
is structured per category — deferred, not built speculatively.

## D120 — Education and employment structured sections: resolution layer (2026-11-03)

- **Context.** Education and employment are the last common "fill every field" gap on
  Greenhouse. They are **not** in the Job Board API `questions` array: they are a separate,
  documented submission contract. Verified 2026-11-03 against the official Greenhouse Job Board
  API docs (`grnhse/greenhouse-api-docs`, `source/includes/job-board/_educations.md` and
  `_applications.md`) — this corrected two errors in the earlier field note (the degree option
  texts are the full strings such as "Bachelor's Degree" / "Master of Business Administration
  (M.B.A.)", not abbreviations; the option `id`s are per-organization, so matching must be by
  text, never by id).
- **Contract (authoritative).**
  - `educations[]`: `school_name_id`, `degree_id`, `discipline_id`, `start_date{month,year}`,
    `end_date{month,year}`. The `*_id`s come from `GET /v1/boards/{token}/education/{schools|
    degrees|disciplines}` (`{items:[{id,text}], meta:{per_page:100}}`, `?term=` search).
  - `employments[]`: `company_name`, `title`, `start_date{month,year}`, `current` ("true"/
    "false"); `end_date{month,year}` required only when `current` is false; start before end.
- **What was built (the independently-implementable layers): `structured_sections.py`.** A
  deterministic resolution layer that maps the owner's **approved** education/employment records
  onto a section's own option lists:
  - degree matched by exact text or a defensible variant grounded in the option's own text (a
    trailing "Degree"; a parenthetical abbreviation, so "MBA"/"M.B.A." ↔ "Master of Business
    Administration (M.B.A.)"); discipline and school matched by **exact** text only (large
    per-organization lists; two hits or none → checkpoint).
  - explicit handling of current employment (`current=true`, `end_date` omitted — never
    invented) and missing/incomplete dates and reversed start/end (→ checkpoint).
  - stable row identity (the record id) and field-level provenance (a `fact_ref` per field to
    the exact record field used), the same shape the package uses for its approval dependency.
  - section reconciliation: an unsupported section kind, or an education section whose option
    lists were not captured, is an explicit checkpoint (`supported=False`), never guessed.
- **Deliberately out of scope (the isolated remaining gaps).**
  - The **rendered hosted-form DOM** — the real control selectors and the repeating-row indexing
    of a Greenhouse education/employment section are **unobserved** and are not invented. The
    option lists are supplied by the caller (at capture, from the education endpoints) or, in
    tests, by a clearly-labelled **synthetic** contract fixture
    (`fixtures/greenhouse_education.synthetic.json`), which is documented-contract data, not
    observed page output.
  - **Live package wiring.** No real captured form carries these sections (capture still fails
    closed), so this is not wired into `package.build_content`; `SCHEMA_VERSION` is unchanged
    (no existing package content changes, so no re-approval is forced). Each field result
    already carries package-shaped `fact_refs`, so wiring is a thin, reviewable step once a real
    section is observed.
- **Tests:** `tests/test_structured_sections.py` (degree/discipline/school matching, full and
  partial education rows, current vs past employment, reversed dates, approved-only, unsupported
  and un-captured sections → checkpoints, provenance).
- **Remaining for D120:** one observed Greenhouse education/employment section (a captured page,
  or an approved read-only inspection) to pin the rendered controls and repeating-row indexing;
  then the DOM filler + live package wiring.

## D123 — Rehearsal runbook + the dynamic-control stop, made explicit (2026-11-03)

- **Runbook.** `docs/rehearsal-runbook.md`: the exact disclosure-only Greenhouse rehearsal
  workflow for the owner's own deployment, verified against the code. It corrects two earlier
  inaccuracies: real rehearsal evidence lives in `execution_evidence` (kind
  disclosure/readback/recheck, strength `none`), **not** the synthetic fixture receiver ledger,
  and an upload acknowledgement is **not** a confirmed submission; and it states the pilot
  authorization accurately (recorded in `authorizations.py`, valid through the server-local
  calendar date 2026-11-06 inclusive, 5 shared attempts, no extension).
- **No circular gate.** The rehearsal prerequisite (E6) is checked only for `submit` approvals,
  so a `disclose_only` rehearsal does not require the evidence it establishes. A rehearsal is
  executable only when the route resolves to `greenhouse_live` (pilot on for the account); a
  `manual_handoff` route names the exact missing prerequisite and nothing is queued.
- **Dynamic-control stop, now explicit.** Capture uses a no-JavaScript GET; execution reads the
  fully rendered DOM and `adapter.schema_matches` (before `fill`) flags any unlisted/new or
  page-required control and stops before disclosure. Added
  `tests/test_greenhouse_adapter.py::test_a_required_control_added_only_by_javascript_stops_before_disclosure`
  and a `gh_js_late_required` fixture mode (a required control injected by JS after load): the
  package captures clean, but the attempt ends `failed_safe` with nothing disclosed. A zero-error
  package never hides a control the live page shows.

## D124 — Premium redesign (Liquid-Glass UI, mobile swipe, editorial type) + Google Drive import

- **Frontend identity (unslop):** new React `.jsx` + Node `.js` (no new TypeScript app code).
  Self-hosted editorial type via `next/font` (Fraunces display + Hanken Grotesk body); a semantic
  design-token system (`globals.css`) with the iris brand used as an accent, layered shadows, full
  light/dark (default light during migration; a pre-paint script honours a stored choice) and a
  Liquid-Glass navigation with an opaque `@supports` fallback and reduced-motion support. The shared
  `components/ui.tsx` primitives were restyled onto the tokens, so every page adopts the look at once.
- **Vertical slice (`src/ui/*`, migrated pages):** Jobs + mobile **swipe discovery** (right = Apply
  *intent* → the role is shortlisted to prepare, never a disclosure/submission, never an "Applied"
  state; left = Pass → excluded), both persisted account-scoped (`PATCH /jobs/{id}`), both undoable,
  passed roles kept in the Excluded collection; a shortlisted job's **Start application** creates the
  draft (`POST /applications`). Review/approve and Tracker migrated with every e2e contract preserved.
- **Phase F — Google Drive import (`app/modules/drive/`):** owner-activated, narrowest scope
  (`drive.file`). The browser Picker hands the server one picked file id + a short-lived token; the
  server downloads that one file and stores it as a new document **snapshot**, validated by the same
  type allowlist (PDF/DOCX/TXT; Google Docs exported to PDF). It never lists/scans Drive, never
  modifies or deletes anything there, never reuses the token, and never sends content to an AI
  provider. Off by default (`NOEFFORTS_GOOGLE_DRIVE_ENABLED`); needs only the PUBLIC OAuth client id +
  API key — no secret in the repo or chat. No new DB table: imports are ordinary document versions.
- **Tests:** `frontend/e2e/jobs-swipe.spec.ts` (swipe → shortlist/exclude, undo, persistence, no
  "Applied" state), `frontend/e2e/drive.spec.ts` (status-gated UI), `backend/tests/test_drive.py`
  (off-by-default, versioned-snapshot import, Drive read-only, type/magic-byte rejection, tenancy).
  Every existing e2e contract preserved; verified on desktop + mobile; `tsc`/eslint/`ruff` clean.
- **Remaining:** full `.jsx` migration of `applications/[id]` (functional + visually unslopped via the
  restyled primitives today) and a dark-mode colour pass on the un-migrated page bodies.

## D126 — Complete job information: structured, sanitized ingestion with salary provenance (2026-11-03)

The premium pass (D125) asked that a job's full detail be preserved and presented, not reduced to
a 500-character plain-text teaser. This is the backend slice; the premium job-detail view that
renders it is a separate frontend change.

- **One place, no migration (`app/modules/discovery/content.py`):** a discovery record already
  carries a schemaless `DiscoveredJob.normalized` JSON column, so the full detail is stored there
  under a new `content` key. Nothing in the schema changes. `NormalizedJob.content` holds only the
  keys a source actually gave — `description_blocks`, `sections`, `salary`, `seniority`,
  `department`, `locations` — so a field a source omits is simply absent, never guessed.
- **HTML → safe structured blocks (untrusted-in, data-out):** a posting's description, links and
  application content are untrusted. The sanitizer (stdlib `html.parser`, no network, no new
  dependency) turns HTML into a list of plain blocks — headings, paragraphs and lists with inline
  text, emphasis and safe links only. Everything that could run, fetch or submit is dropped whole:
  scripts, styles, `img`/media, `iframe`/frames, `svg`, forms and controls, and every attribute but
  a link's `href`. A link survives only when its scheme is http(s) or mailto (`javascript:`,
  `data:`, `vbscript:`, `file:` and relative/anchor links lose the link, keep the text). The blocks
  are rendered later as elements — never as raw HTML — so no embedded asset is ever fetched and
  nothing executes. Output is bounded (blocks, list items, total characters). This replaces the
  "reduce to plain text" rule from D95; the 500-char `description_summary` stays for the list, dedupe
  and export.
- **Salary with its provenance, never invented:** structured source fields are read when present
  (Lever `salaryRange`/`salaryDescription` — the pay fields D95 deliberately left out "until there
  is a design for it"; this is that design) and tagged `structured`; Freehire enrichment pay is
  tagged `enrichment` and attributed to the provider as possibly model-produced, never the
  employer's words; otherwise one figure is `extracted` from the description text and marked as such.
  The original currency, pay period and figures are preserved exactly — an hourly figure is never
  annualized and currencies are never converted. Base is distinguished from bonus/equity/OTE when
  the text separates them. When no salary is known the value is null and the page shows
  "Salary not provided."
- **The sources' own structure, not invented sections:** Greenhouse (`content`, entity-decoded) and
  Freehire (`description`) keep their own headings inside the description blocks; Lever's documented
  `lists` become labelled `sections` (Responsibilities, Requirements, …) exactly as the posting
  labelled them. NoEfforts never fabricates a responsibilities/qualifications split.
- **Exposed through the job page (`GET /jobs/{id}` → `content`):** the detail endpoint consolidates
  the richest discovery record that lists the job (freshest, with a real description; stale records
  rank below fresh), falling back to the job's own saved text and fields, into one `content` object:
  `{description: {blocks, sections}, salary, facts: {employment_type, seniority, department,
  locations, posted_on, source_url}, origin}`. `facts` carries only what a source gave; `origin` is
  `discovery` / `your_entry` / `none`. Model-written enrichment prose (Freehire `summary`,
  `requirements`) is **not** used — only the posting's own content or clearly attributed estimates.
- **Tests:** `backend/tests/test_discovery_content.py` (sanitizer drops scripts/media/forms, keeps
  safe links, decodes entity-encoded HTML, caps output; salary structured/enrichment/extracted with
  currency/period/kind preserved and nothing annualized; missing fields stay absent) and
  `backend/tests/test_jobs_content_detail.py` (the job page surfaces the full description not the
  summary, the source's sections, structured salary, and says "Salary not provided." when none is
  known). No new audit event and no new `NOEFFORTS_` setting, so the inventory and deployment-config
  guards are unaffected.
- **Frontend (the premium detail view):** `jobs/[id]` migrated from `.tsx` to `.jsx` on the D125
  premium primitives, and now renders the consolidated `content` in an "About this role" card:
  salary with a plain-language provenance line (from the posting / estimated by the source / found
  in the description) shown exactly as given — never annualized or converted — or "Salary not
  provided."; the availability-dependent facts as chips; the full description and the source's own
  sections as **React elements, never `dangerouslySetInnerHTML`**, so the sanitizer's guarantee
  reaches the DOM (no script runs, no embedded asset is fetched). A safe link keeps `target=_blank
  rel="noopener noreferrer nofollow"`. Entrance uses the D125 motion (`Reveal`/`Stagger`),
  reduced-motion-aware; correct in light and dark. `frontend/e2e/job-detail-content.spec.ts`
  asserts the structure renders, the salary provenance shows, an injected `<script>`/`<img>` neither
  runs nor reaches the DOM, and the salary-absent case says so.

## D127 — Email-tracking activation: the owner's own in-app authenticated consent (2026-11-04)

**Context.** Reading application emails (`read_application_email`) is gated by D103: it needs the
owner's *recorded* authorization, which by design lives only in reviewed source
(`app/core/authorizations.py`), never in a config switch or a toggle. D117 recorded
`read_codes`/`enter_codes`, but not `read_application_email`. So — as the email-tracking build
itself documented — the *only* way to activate tracking was to edit source code and ship it. That
is a poor activation story for the owner of a running instance: it asks them to change code (or ask
an engineer to) to use a feature that only ever reads their *own* mailbox. It is also the one real
remaining dependency for the finished email-tracking work (PR #27).

**Decision.** Add a second, equally-gated authorization path: the inbox owner's **own
authenticated, auditable, revocable in-app consent**, recorded while signed in as the owner. It
needs no code change and is the ordinary activation path. The reviewed-source register
(`RECORDED`) stays exactly as it was — unchanged, still the only server-wide grant, still never
written from config or a request — and is **not** widened by this decision.

**What it is, and is not.**
- **Owner-scoped.** Only an account whose email is in `inbox_owner_emails` (`is_inbox_owner`) can
  grant or hold it; any other account is refused (`not_for_this_account`). It authorizes reading
  that owner's **own** mailbox and nothing else.
- **Capability-scoped.** It covers `read_application_email` **only**. It never authorizes reading
  verification codes (`read_codes`/`enter_codes` keep their own separate gate and their own
  recorded authorization), and it has no bearing whatever on email **sending** or application
  **submission**, which are different subsystems with their own gates. The inbox authorization
  vocabulary still contains no send/modify action (R7.5 static guard unchanged).
- **Authenticated and auditable.** The owner types their consent in their own words; the verbatim
  text is stored on an `inbox_consents` row (`attestation`), with `granted_at`. Granting and
  revoking each write an audit event (`inbox.authorization_granted` / `inbox.authorization_revoked`,
  metadata `capability` [+ `ends_on` on grant]; the attestation text is **not** copied into the
  audit metadata). The append-only consent table is a history.
- **Time-boundable and revocable.** An optional `ends_on` expires the consent automatically
  (an expired row no longer authorizes); the owner can revoke at once in Account → Email
  (`POST /inbox/authorize/revoke`), which re-gates reading immediately. This is independent of, and
  weaker than, disconnecting the Gmail token or removing NoEfforts in the Google account — the
  scope note still points to those stronger steps.

**Mechanism.**
- Model: `InboxConsent` (`inbox_consents`), migration `e5b9c1f3a2d8`. Columns: `user_id`
  (cascade), `action`, `attestation` (≤500 chars), `granted_at`, `ends_on` (date, nullable),
  `revoked_at` (nullable). Exported by `account/export.py` and deleted with the account.
- Gate: `service.may_read_applications(db, user)` returns true when **either** the recorded
  register covers `read_application_email` (D103) **or** an active (granted, not revoked, not past
  `ends_on`) in-app consent exists. Every reader entry point (`available_for`, `put_inbox`,
  `check_now`, the due-scan) uses it; `may()` (recorded-only) still gates codes, unchanged.
- API: `POST /inbox/authorize` (owner records consent, optional `ends_on`), `POST
  /inbox/authorize/revoke`. `GET /inbox` now reports `tracking_authorized`, `is_inbox_owner`,
  `first_read_days`, and an `authorization` block that distinguishes `recorded` (server-wide, not
  revocable in-app) from `in_app` (the owner's own, revocable).
- UI: Account → Email shows an owner-only "Authorize reading my application emails" control
  (attestation + optional end date), the active authorization with a Revoke button when it is
  in-app, and gates the tracking toggle on `tracking_authorized`.

**Tests.** `backend/tests/test_inbox.py` adds: in-app consent authorizes tracking with no code
change and revoke re-gates it; an expired consent no longer authorizes; only the owner can grant or
use it; the consent never authorizes codes, sending or submission; grant and revoke are audited.
The audit-inventory and sanitizer guards cover the two new events; `frontend/e2e/inbox.spec.ts`
exercises the authorized view. The static capability guard (R7.5) and the recorded-register test
(`test_authorizations.py`, which asserts the shipped register's exact contents) are unchanged and
still pass — confirming the source register was not widened.

## D128 — Connect Gmail from the app with a browser OAuth flow (2026-11-04)

**Context.** D101's `connect.py` is a CLI the owner runs on the server machine: it does a desktop
(installed-app) OAuth loopback flow and writes a 0600 token file, after which env vars point the
inbox reader at it. That remained the only way to connect, which is a poor activation story — it
asks the owner to run a command to use a feature that only reads their own mailbox — and the
"server-side secret ⇒ must be a CLI" framing in the earlier handoff was wrong: a backend can run a
standard web authorization-code flow and keep the tokens server-side without any CLI.

**Decision.** Add a supported **browser OAuth authorization-code flow** (`app/modules/connections`)
as the normal path: Account → Connections → Connect Gmail. The CLI stays as an operator fallback.
Off by default (`inbox_oauth_enabled` + a configured **web** OAuth client). The flow:

- **Start** (`GET /connections/gmail/start`, a top-level navigation): records a single-use,
  account-bound, expiring `OAuthFlow` state with a PKCE (S256) verifier and 302-redirects the
  owner's browser to Google's consent page (the system browser, never an embedded view). Only the
  read-only scope is requested; the redirect URI is one fixed, allowlisted value under
  `public_base_url`.
- **Callback** (`GET /connections/gmail/callback`): validates the state — it must exist, belong to
  the account whose session presents it (so another account's callback cannot complete it), be
  unused (consumed on first use) and unexpired (≤10 min) — then exchanges the code (a confidential
  web client whose secret stays server-side), **verifies exactly the read-only scope was granted**
  (any added send/modify scope is refused and nothing is stored), learns which mailbox was
  connected via `users.getProfile`, writes the refresh token to a **0600 file per account**
  (`inbox_connections_dir/<user_id>.json`, never the database, an image, logs, the frontend or
  chat), records the connection (mailbox address, scope, status) and redirects back to a fixed
  in-app page with a result code. No open redirect: both the Google redirect target and the return
  URL are built from settings, never from the request.
- **Status / disconnect** (`GET /connections`, `POST /connections/gmail/disconnect`): the UI shows
  not-connected / connected / reconnect-required, the connected mailbox identity, the access scope
  in plain words, last error; disconnect deletes the token file and marks the connection revoked
  (revoking at Google is the separate, stronger step the UI points to). A stored token that stops
  working (revoked at Google) moves the connection to "reconnect required".

**Storage & security.** The refresh token lives only in the 0600 file, exactly as the CLI's does;
the DB holds non-secret binding/status facts (`gmail_connections`) and the transient flow state
(`oauth_flows`, excluded from the export as a short-lived nonce). The inbox reader
(`inbox.service.reader`) prefers the web connection's token file, falling back to the CLI's
configured file. `users.getProfile` is added to the one allowlisted reader file (`provider.py`)
and permitted in the forbidden-capabilities guard's allowlist for that file and the fixture only —
transparently, not by evading the scanner; all Google URLs come from `provider.py`/settings, never
new literals, and the `gmail.readonly` scope is never written outside `provider.py`.

**Independence.** Connecting enables nothing. Reading application emails still needs the owner's own
D127/D103 authorization and the per-use D101 toggles; verification-code reading keeps its own
separate gate; and no API-token scope reaches any inbox or connection route (the routers are
`session_only`). An email status update still queues no execution and sends nothing.

**Deployment.** Real activation needs the owner to create a Web-application OAuth client in their
Google Cloud project and register the one callback URI, set `inbox_oauth_enabled`,
`inbox_oauth_client_id/secret` and `inbox_connections_dir`, and deploy at a URL Google can redirect
back to (a phone's localhost is not the server's localhost; cross-device use needs a reachable
`public_base_url`). Google's own verification requirements for a read-only Gmail scope still apply.
Implemented and tested entirely against a local Google-OAuth stand-in
(`fixtures/ats_receiver/inbox_fixture.py`); no real mailbox or Google client is contacted.

**Tests.** `backend/tests/test_connections.py` drives the flow end to end: successful connect binds
the mailbox and writes a 0600 token; connecting enables no processing; denied consent, unknown,
expired and replayed state, another account's state, a scope beyond read-only, and a reply without
a refresh token are each refused with nothing stored; non-owner and flow-off are refused; disconnect
then reconnect; a revoked token → reconnect-required; and the web token is what the reader reads.
`frontend/e2e/connections.spec.ts` covers the card's states. The forbidden-capabilities,
audit-inventory and export-completeness guards are updated and pass.

## D129 — Section-free Greenhouse path: prefilled-identity verification; phone-country + upload + answers reuse (2026-11-05)

- **Context.** The owner shared one real Greenhouse apply form (section-free: no Education/Employment
  section). Priority shifted to making that common path operational, reusing existing machinery, not
  rebuilding. An audit mapped what already exists against the path's needs.
- **Already built (verified, reused unchanged).**
  - **Document upload (D116).** `_attach` binds the sha256-verified approved bytes; the independent
    receiver records the content digest (byte-identity assertable); the ack is checked; no retry
    after disclosure + generation fencing prevent a duplicate upload. No new code.
  - **Answers + profile links.** A link question (LinkedIn `question_<digits>`) resolves from the
    profile's host-matched link (`_link_kind`: linkedin.com `/in|/pub` → "linkedin"), exactly one or
    a checkpoint — from the profile, not restricted to the answer bank.
  - **Self-identification (D122).** Standing consent fills only an exact option match of the owner's
    own stated labels; it never overrides a per-application choice and never replaces a
    per-application disclosure consent for other sensitive questions.
  - **Phone-country (D104).** Exact calling-code match → fill + readback; a shared `+1` → checkpoint;
    no code → checkpoint, never from residence; stand-in only.
- **New: prefilled-identity verification.** A real Greenhouse page pre-fills the applicant's email
  into a **disabled** field. Before D129 the adapter neither read nor compared it, and `fill()` would
  time out on it (an abandoned attempt after disclosure). Now, mirroring the location-prefill guard,
  `GreenhouseDomAdapter._identity_prefill_refusal` runs **before disclosure**: for a mapped identity
  answer (fact_ref `contact_email`/names) whose live control is locked (disabled or read-only), it
  reads the live value and (a) trusts + skips it when it equals the approved value (never overwritten),
  (b) refuses (`IDENTITY_MISMATCH`) when it differs — NoEfforts never applies under a different
  account, (c) refuses (`IDENTITY_UNREADABLE`) when a required locked identity is empty/unreadable.
  `fill()` skips a trusted locked field. The only new DOM read is of a locked field's own value at
  execution time; nothing prefilled is written into package content or git. Tests (receiver oracle):
  `test_greenhouse_controls.py::test_a_locked_prefilled_email_that_matches_is_trusted_and_submits`
  (match → confirmed, résumé byte-identical in the ledger, readback clean, email never disclosed),
  `..._that_differs_refuses_before_disclosure`, `..._locked_required_identity_that_cannot_be_read`.
  Fixture: `gh2_email_locked_{match,mismatch,empty}` (synthetic email only).
- **Remaining real-page gap (unobserved, not invented).** The real phone-country and EEO controls are
  react-select with unstable `react-select-N-input` ids and a listbox that renders only on open; the
  closed-state snapshot does not show their options. Current behaviour fails closed (checkpoint),
  never a wrong fill. Real enablement stays behind the pilot/admission process and the first
  rehearsal/submission evidence (`providers/readiness.py`: 1 of 7). The prepared, not executed,
  handoff is `docs/greenhouse-section-free-handoff.md`; the operational permission (D112) lapses
  2026-11-06 and is never silently renewed.
