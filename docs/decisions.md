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
