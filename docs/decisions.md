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
and keyless with a documented 600 req/min/IP limit, and its terms forbid scraping beyond the
documented API. Plan: a throttled discovery adapter that re-verifies postings at the source ATS.
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
gate 2, cancellation is refused because data may already be in flight.

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

