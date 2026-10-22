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

## D15 — Uncertain submissions leave quarantine only through reconciliation
Removed the direct `submitted_unconfirmed → queued` transition. Reconciliation requires a
written statement of what was checked and explicit confirmation, and re-queueing then requires a
fresh approval. System actors may not re-queue `failed_retryable` until Phase C defines
provider-specific retry policies for failures known to have sent nothing.

## D16 — Transactional outbox + claim CAS instead of trusting queue semantics
The attempt and its outbox row are written in the queue transaction. A relay publishes ids;
a crash between publish and marking dispatched yields a duplicate delivery, which the claim
compare-and-swap ignores. Celery's `acks_late` / `reject_on_worker_lost=False` only decide
whether Celery repeats a *task*; they never make an external submission idempotent.

## D17 — Two gates; the send gate is the linearization point
Gate 1 authorizes disclosure, gate 2 authorizes the click. Both run in REPEATABLE READ under
the application row lock and recheck approval, expiry, package hash and freshly rebuilt
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

## D41 — A rehearsal is an approval to disclose only, used once (2026-10-22; stop amended by D44)
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

## D43 — Each gate locks the approval row too (2026-10-22)
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

## D44 — A rehearsal ends through a gate; readiness counts recorded evidence by class (2026-10-22)
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
