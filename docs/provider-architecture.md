# Submission-provider architecture

Status: 2026-10-21. Local architecture, fixtures and tests only. No provider is enabled for a
real destination, and no live filling or live submission is supported anywhere. Candidate
disclosure (C) and final submission (D) on a real page remain unapproved.

NoEfforts reaches an employer in one of three ways, chosen per destination and bound to the
user's approval:

1. an **isolated-browser adapter** for the ATS's application form (the primary route);
2. an **authorized API** route, only where the employer or ATS authorizes it, the user has
   granted it, credentials are configured, and the provider declares API submission;
3. a **manual handoff**: the user applies on the employer's site.

**Discovery providers** (for example a future Freehire integration) only find jobs. A
discovered job tells us nothing about whether NoEfforts can apply to it. **Observation
providers** (the read-only Greenhouse collector) only read pages. Neither kind is ever an
execution route.

Code: `backend/app/modules/providers/` (model, registry, routing, checkpoints, API
authorizations), `backend/app/modules/execution/adapters/fake_api.py`, `runner._run_api`,
and `backend/app/modules/discovery/`. Fixtures: `fixtures/ats_receiver/fake_api.py` and
`fixtures/discovery/freehire_mock.json`.

## 1. Provider model

`providers/model.py` defines three things.

**Kinds:** `browser`, `api`, `discovery`, `observation`, `manual`.

**Operations** that a provider may implement. None has to implement all of them:

- `inspect`, `extract_form`, `prepare`, `validate_before_disclosure`;
- `fill`, `upload`, `checkpoint`, `submit`;
- `classify_outcome`, `collect_evidence`, `reconcile`, `discover`.

**Capabilities**, each with an evidence-backed support level:

| Level | Meaning |
|---|---|
| `fixture` | implemented and tested against a local fixture only |
| `observed` | its structure was seen on a real page under an approved read-only run |
| `live_fill` | supported for filling on a real destination |
| `live_submit` | supported for final submission on a real destination |

The capability flags are:

- reading and forms: `discovery`, `posting_read`, `form_extract`, `deterministic_fill`,
  `custom_dropdowns`, `file_upload`, `location_picker`;
- verification: `login_required`, `email_verification`, `mobile_verification`,
  `captcha_checkpoint`;
- sending: `final_submit`, `confirmation_detection`, `reconciliation`,
  `official_api_submission`;
- `real_destinations_enabled`, a per-provider switch.

`check_spec` runs on import and rejects a spec that claims support it cannot have:

- live support without real-page evidence (`observed`);
- `observed` without a local implementation (observation providers excepted, because they
  implement nothing that sends);
- live submission without live filling (API submission excepted);
- live support while `real_destinations_enabled` is false, or real destinations outside
  production;
- a discovery, observation or manual provider that fills, uploads or submits;
- an API provider without `official_api_submission`, or a browser provider claiming it;
- (I2) a capability no operation implements, or an implemented operation without the
  capability it implements (`model.CAPABILITY_OPERATIONS`, `OPERATION_CAPABILITIES`);
- (I2) a yes/no trait without its evidence note, a planned spec stating anything but `expected`
  or `unknown`, `not_applicable` on a browser or API provider;
- (I2) fixture support without the fixture it was tested against (`tested_against`, repository
  paths, never served; their existence is checked in CI);
- (I2) a browser adapter where a CAPTCHA may appear (`captcha_possible` not `no`) without a
  CAPTCHA checkpoint;
- (I2) `real_destinations_enabled` at all: real destinations stay refused until the live-pilot
  gate is opened by a reviewed change to this rule.

`registry.check_registry` adds the rules across providers: each key is its spec's name, every
ATS is a `detect_ats` name, discovery and manual providers serve none, planned and observation
providers name theirs, every trait is stated, one planned spec per ATS and none beside an
implemented adapter, and the side tables name registered providers only. Every `raise SpecError`
has its own negative case (`test_every_spec_error_branch_has_a_case`).

So a fixture success can never become a live claim by accident. Reaching `observed`,
`live_fill` or `live_submit` requires an edit to the registry and a review. The registry is
served at `GET /api/providers` and inside `GET /api/execution/capabilities` (`providers`).

**Support states and wording** (`providers/wording.py`). What a page says about support comes
from this one module and follows from evidence. The pages show it as served and write none of
their own; `tests/test_support_wording.py` reads the frontend sources to check.

| Support state | Derived when | Label |
|---|---|---|
| `manual` | the provider is the manual handoff | Manual: you apply on the employer's site |
| `planned` | the provider is a planned specification | Planned only: no automation exists |
| `fixture_only` | the strongest capability level is `fixture` | Local test fixtures only |
| `observed_read_only` | some capability is `observed` | Local test fixtures only; seen read-only on a real page, never filled there |
| `not_supported` | the provider has no capability at all | Not supported |
| `live` | some capability is `live_fill` or `live_submit` | none. The lookup fails until a label is added deliberately, with its evidence, tests and docs |

- **Today:** `fixture_ats`, `greenhouse_hosted`, `fake_api`, `freehire` and `freehire_mock`
  are `fixture_only`; `greenhouse_dom` and `greenhouse_readonly` are `observed_read_only`;
  `workday` and `lever` are `planned`; `manual_handoff` is
  `manual` (`tests/test_provider_contracts.py` checks this list).
- **Routes:** a route's label is its kind and the evidence behind it, for example "Browser
  adapter (local test fixture only)". An API or browser route is never shown without its
  evidence: the lookup refuses one that has none.
- **Captured forms:** a form from a local test stand-in says so: "Local test fixture (fictional
  employer)" and the two Greenhouse-style approximations. A form read from page HTML the user
  provided, or entered by hand, carries no qualifier; the route card says how it could be
  applied.
- **Where it is served:**
  - `GET /api/providers`: `support_state`, `support_label`;
  - `GET /api/discovery/providers`: `support_label`;
  - the route of a job or of a discovery record: `label`, `provider_support`;
  - `GET /api/jobs/{id}/form`: `source_label`;
  - `GET /api/applications/{id}/package`: `labels`, outside the package content, so wording
    never changes a package or its hash.
- The registry's one-line `status` notes remain as fuller descriptions; they are not labels.

### Capability matrix (registry as committed)

Columns: FA = `fixture_ats`, GH = `greenhouse_hosted`, GD = `greenhouse_dom`, API =
`fake_api`, RO = `greenhouse_readonly` (observation), FH = `freehire_mock` and `freehire`
(discovery; identical rows), MH = `manual_handoff`. A dash means none. The planned providers
(`workday`, `lever`) have no capabilities, so they have no column here.

| Capability | FA | GH | GD | API | RO | FH | MH |
|---|---|---|---|---|---|---|---|
| discovery | – | – | – | – | – | fixture | – |
| posting_read | fixture | fixture | **observed** | fixture | **observed** | – | – |
| form_extract | fixture | fixture | **observed** | fixture | **observed** | – | – |
| deterministic_fill | fixture | fixture | fixture | – | – | – | – |
| custom_dropdowns | – | – | fixture | – | **observed** | – | – |
| file_upload | fixture | fixture | fixture | fixture | – | – | – |
| location_picker | – | – | – | – | – | – | – |
| login_required | – | – | – | – | – | – | – |
| email_verification | fixture | fixture | – | – | – | – | – |
| mobile_verification | – | – | – | – | – | – | – |
| captcha_checkpoint | – | fixture | fixture | – | – | – | – |
| final_submit | fixture | fixture | fixture | fixture | – | – | – |
| confirmation_detection | fixture | fixture | fixture | fixture | – | – | – |
| reconciliation | fixture | fixture | fixture | fixture | – | – | – |
| official_api_submission | – | – | – | fixture | – | – | – |
| real_destinations_enabled | no | no | no | no | no | no | no |

Notes on the matrix:

- `observed` means the structure was seen at load (controls, labels, required state). For
  `custom_dropdowns` on the observation provider, it means the dropdown controls exist on the
  real page. It does not mean they were opened: run #9 found no opening evidence.
- No cell is `live_fill` or `live_submit`. A test pins this
  (`test_no_provider_is_enabled_for_real_destinations_or_claims_live_support`), and another
  pins the exact set of `observed` cells.
- Every `observed` cell is credited by a completed read-only run approved for that one run
  (`providers/evidence.py` `READ_ONLY_RUNS`; `docs/provider-admission.md`). This table is the
  registry (`test_the_documented_capability_matrix_is_the_registry`).

## 2. Routing (`providers/routing.decide`)

1. **Identity:** the captured form source and the destination origin.
2. **Enabled:** a real origin, or production, gives a manual handoff with the adapter's
   refusal message. No provider is enabled for real destinations.
3. **Approval binding:** the approval records the chosen provider and its version (D28).
   - `policy.execution_binding` calls `decide`.
   - `check_binding` compares it with the approval at queueing (409, approval retired) and
     again in the worker before anything is sent (`failed_safe`, "execution method changed").
   - The package hash already binds the destination, the form id, version and fingerprint,
     the answers, the consents, the documents (sha256) and the policy versions (resolver and
     package schema). A change to any of them changes the hash and invalidates the
     approval.
4. **API route,** only if all of these hold:
   - the provider's identity rule matches the destination;
   - the environment allows it;
   - `official_api_submission` is declared;
   - the user holds an active, unrevoked authorization for that provider and origin
     (`api_authorizations`, user-scoped, fixture origins only);
   - credentials are configured.
5. **Browser route,** if `policy.adapter_for` names an adapter for this destination.
6. **Otherwise a manual handoff.** Observation and discovery providers are never returned.

The route never changes silently:

- **Adapter to adapter, or browser to API:** the provider name is part of the binding.
  - Granting an API authorization retires a browser approval at queueing, and revoking it
    does the same.
  - A token removed after approval makes the worker stop before disclosure.
- **Fixture to real:** real origins never route anywhere but the manual handoff.
- **Read-only to filling:** observation providers are not routes, and their spec cannot
  declare fill, upload or submit.

## 2b. Execution routing: interface, vocabulary, per-job route (2026-10-21)

Each application takes the safest supported path:

1. an employer-authorized API, when one is genuinely available and permitted;
2. a validated browser adapter, when there is no authorized API;
3. a checkpoint for the user, or a manual handoff, when the workflow is unsupported, ambiguous,
   needs a CAPTCHA, a login or verification, or risks disclosure outside the approved scope.

**Execution interface** (`model.INTERFACE`). These are the names used here. Each maps to the
operations an adapter implements; the runner drives them, and adapters keep their own method
names.

| Interface operation | Implemented by | Where |
|---|---|---|
| `inspect_application` | `inspect` | capture: job data plus page, cross-checked |
| `extract_form_schema` | `extract_form` | `preparation/forms.py`, `greenhouse.py`, `greenhouse_dom.py` |
| `prepare_application` | `prepare` | package build: deterministic answers, approval |
| `validate_application` | `validate_before_disclosure` | re-extract and compare before gate 1 |
| `request_user_action` | `checkpoint` | `checkpoints.py`; emailed code; `needs_user_action` |
| `upload_documents` | `upload` | after gate 1; the digest is checked |
| `submit_application` | `submit` | after gate 2, once |
| `collect_confirmation_evidence` | `classify_outcome` + `collect_evidence` | minimal evidence, no screenshots or traces |
| `reconcile_unknown_outcome` | `reconcile` | API: read-only lookup by key. Browser: the user records what they checked |

**Routing vocabulary** (`model.ROUTING_CAPABILITIES`) is a view over the evidence-levelled
capabilities. Rows marked *trait* are what a workflow demands, not what NoEfforts can do:

- a trait is "yes" or "no" only with evidence (a fixture's own design counts only for that
  fixture);
- "expected" is used only for a planned specification;
- "unknown" otherwise.

Levels: `fixture` = local fixture only; `observed` = seen read-only on one real page; `none` =
not implemented. **No cell is `live_fill` or `live_submit`.**

| Capability | fixture_ats | greenhouse_hosted | greenhouse_dom | fake_api | greenhouse_readonly | freehire / mock | workday (planned) | lever (planned) | manual_handoff |
|---|---|---|---|---|---|---|---|---|---|
| discovery | none | none | none | none | none | fixture | none | none | none |
| public_schema_read | fixture | fixture | observed | fixture | observed | none | none | none | none |
| API_submission | none | none | none | fixture | none | none | none | none | none |
| browser_inspection | fixture | fixture | observed | none | observed | none | none | none | none |
| browser_fill | fixture | fixture | fixture | none | none | none | none | none | none |
| document_upload | fixture | fixture | fixture | fixture | none | none | none | none | none |
| login_required *(trait)* | no | unknown | no | no | no | n/a | expected | unknown | n/a |
| manual_verification_required *(trait)* | yes | unknown | unknown | no | n/a | n/a | expected | unknown | n/a |
| CAPTCHA_possible *(trait)* | no | unknown | unknown | no | unknown | n/a | expected | expected | n/a |
| multi_step *(trait)* | no | unknown | no | no | no | n/a | expected | unknown | n/a |
| location_picker | none | none | none | none | none | none | none | none | none |
| custom_dropdown | none | none | fixture | none | observed (structure only) | none | none | none | none |
| confirmation_detection | fixture | fixture | fixture | fixture | none | none | none | none | none |

Both views are served at `GET /api/providers` (`routing_capabilities`, `traits`,
`interface`, `stage`). `tests/test_lever.py` fails when a column of the table above differs
from the registry.

**Routing order** (`routing.decide`, `routing.route_for_job`; `GET /api/jobs/{id}/route`):

0. **Identity.** The job's ATS comes from known hostnames.
   - An ATS with only a planned adapter (Workday) is a manual handoff that says so.
   - A form captured as one ATS for a job on another is refused: it never reaches the wrong
     adapter.
1. **Enabled:** production, and a job on a real employer's site, give a manual handoff that
   says so (`production_disabled`, `real_destination_disabled`, in the adapter policy's own
   words). No provider has live support. This comes before any form step: capturing a form
   could not change it, so the user is never asked for one there. `decide` applies the same
   gate again to a captured destination.
2. **No captured form** (a local fixture, or a job without an address): a manual handoff
   ("Capture the application form first."). A job source never supplies the form.
3. **Required controls NoEfforts cannot fill** (search pickers, page-managed hidden values,
   unknown widgets, and controls on the page that the job data does not list, which are
   captured as blocking fields): a **checkpoint**, reached before anything is disclosed or
   approved. They are never turned into a guessed answer.
4. **Authorized API (A):** only with the user's grant, configured credentials, declared
   support and the provider's identity rule. No undocumented or inferred private endpoint.
   The package approval, document digests, answer provenance and evidence are exactly as for
   the browser route.
5. **Browser (B):** only an adapter that `policy.adapter_for` names for this form source and
   origin.
   - Before any disclosure, the runner re-checks the destination, adapter and version
     (approval binding), approval state, documents, mapping and form fingerprint.
   - After filling, it reads every value back.
   - A click is never assumed to open a control, persist a value or submit.
6. **Otherwise:** a manual handoff. At run time every stop gives its reason: unsupported
   control, unknown question, CAPTCHA, login, verification code, page change, changed form,
   uncertain mapping, or unknown result.

**Reason codes** (`routing.REASONS`). Every decision carries exactly one.
`tests/test_reason_codes.py` fails when a code is added or removed without this table changing
with it, when a code other than the fallback has no path that produces it, or when a decision
or refusal in the source relies on the default code or names one this table does not list.

| Code | Route | Produced by | When |
|---|---|---|---|
| `api_authorized` | api | `decide` | the user's grant for that provider and origin, configured credentials and declared API support |
| `browser_supported` | browser | `decide` | `policy.adapter_for` names an adapter for this form source and origin |
| `planned_adapter_only` | manual | identity (`decide`, `route_for_job`) | the job's ATS has only a planned adapter (Workday, Lever) |
| `form_ats_mismatch` | manual | identity | the captured form belongs to a different ATS than the job |
| `no_form_captured` | manual | `route_for_job` | a local fixture, or a job without an address, has no application form captured yet |
| `unsupported_required_control` | checkpoint | `route_for_job` | the form has required controls NoEfforts cannot fill |
| `real_destination_disabled` | manual | `route_for_job` (before any form step), `decide` | a real origin. `policy.adapter_for` refuses it, and the router's own gate refuses it again even if the adapter policy accepted it (tested) |
| `production_disabled` | manual | `route_for_job` (before any form step), `decide` (`policy.adapter_for`) | automatic submission is not available in production |
| `no_captured_destination` | manual | `decide` (`policy.adapter_for`) | no origin or submit address was captured |
| `submit_origin_mismatch` | manual | `decide` (`policy.adapter_for`) | the form submits to a different site than the job page |
| `no_adapter` | manual, or a refusal | `decide` (`policy.adapter_for`), `policy.check_binding` | the captured form's source is not one an adapter executes (an unlisted source is refused, never given to the generic fixture adapter: I2, D47); or queueing or running a destination whose route is a manual handoff |
| `source_record_incomplete` | manual | discovery `application_route` | the discovery record lacks what a tracker job needs (its `missing` list) |
| `source_posting_closed` | manual | discovery `application_route` | the posting was closed at its source before it was linked, so no tracker job exists |
| `no_supported_provider` | manual | nothing | the fail-closed fallback: the default of `RouteDecision` and `UnsupportedDestination`, and what an unknown code is recorded as. No path produces it (tested over a grid of sample origins, submit addresses, form sources, ATS hosts and API grant states, in the test and production environments) |

- A browser refusal for a fixture destination (`no_captured_destination`,
  `submit_origin_mismatch`) does not block an authorized API route. The API adapter sends only
  to the authorized origin's own API, never to the captured form's submit address.
- Every decision also carries:
  - an API grant state: `granted`, `none` or `not_applicable`;
  - the evidence level behind the route (`routing.evidence_level`): the provider's support for
    API submission or browser filling, or `none` for a checkpoint or a manual handoff.
- `GET /api/jobs/{id}/route` and the discovery view of a record (`GET /api/discovery/jobs/{id}`,
  its `route`) return the code, the grant state and the evidence level.
- The job page shows the route's label, and the code under the message. For an API or
  browser route it also shows the provider key and its support label ("Support states and
  wording" in §1).

**Route audit** (`routing.audit_route`, `audit/service.py`):

- A route decision is recorded as a `route.decision` audit event with only these fields:
  - the internal job id;
  - the route (`api`, `browser`, `checkpoint` or `manual`);
  - the provider key and adapter version;
  - the reason code;
  - the evidence level behind the route;
  - the grant state.
- A decision is recorded when it differs from the job's last recorded one. A route shown again
  unchanged adds nothing, on the job page or in the discovery view of a linked record. A
  discovery record without a tracker job has no job to record against.
- User-facing route messages are generic. A checkpoint gives the number of controls NoEfforts
  cannot fill, never their labels or keys, which are the employer's wording.
- Audit `meta` is sanitized before it is stored, for every event:
  - keys naming sensitive material (credentials, contact data, names, titles, URLs,
    employers, files, answers, raw content) are redacted;
  - non-identifier values are omitted: free text, URLs, e-mail addresses, exception text and
    nested objects;
  - external identifiers such as a posting's question keys are stored as keyed, user-scoped
    references (`ref:v2:`, HMAC-SHA-256 with the server-held `NOEFFORTS_AUDIT_REF_KEY`; details
    in `docs/audit-events.md`); a `field` key, which always held one, is stored as `field_ref`.
- Rows stored before sanitizing existed are repaired once by migration `c303eee5a3c9`
  (`audit/repair.py`, repair version 1), and legacy unkeyed references are removed by
  migration `7a1e4c2b9d30` (repair version 2: each becomes `[omitted]`, since its source is no
  longer stored). Both repairs:
  - pass every `audit_events.meta` object through the current sanitizer, scoped by the row's
    user; a value that is not an object becomes `{}` (a JSON null, which holds nothing, is
    left as it is); they read only `id`, `user_id` and `meta`, and write only `meta`;
  - rewrite only rows whose metadata changes, so a second run changes nothing;
  - are irreversible: the downgrade restores nothing and no removed value is kept;
  - output aggregate counts only (rows scanned, rows changed); a failure names the
    error type only, with no message or chained exception, and the transaction rolls back.
- The browser runner logs an unexpected exception by type only, and the egress proxy logs
  destination counts, never hosts.

**Provider roles:**

| Component | Primary role | Not responsible for |
|---|---|---|
| Freehire or other job source | Discover/import job listings and URLs | Filling or submitting employer applications |
| ATS adapter | Read, map, fill and verify a specific ATS workflow | Broad compatibility claims without evidence |
| Browser worker | Execute approved browser steps in isolation | Guessing facts or bypassing restrictions |
| Authorized API connector | Structured retrieval/submission where permitted | Replacing browser support everywhere |
| Candidate profile and answer bank | Approved facts and reusable answers | Inferring missing legal/sensitive answers |
| User | Approval, verification, manual checkpoints, final scope decisions | Repeatedly re-entering already approved facts |

## 3. API-provider contract (internal; no real ATS is claimed to offer it)

`adapters/fake_api.py` is NoEfforts' own contract. It is exercised only against the local
fake API on the synthetic receiver (`fixtures/ats_receiver/fake_api.py`). That fake API has
its own state and writes acceptances to the receiver's own ledger, independent of NoEfforts'
database. **Greenhouse, Workday, Tsenta or any other ATS is not claimed to provide this
interface.** A real API provider would need its own adapter, its own capability entry and
its own receiver-style tests.

| Step | Request | Disclosure boundary |
|---|---|---|
| `validate_before_disclosure` | GET the job's schema; refuse unless it equals the approved fields | none (nothing about the candidate is sent) |
| gate before disclosure | as for the browser (approval live, hash identical) | `disclosure_started_at` |
| `prepare` | create a draft with the approved answers (`Idempotency-Key: <attempt>:draft`) | answers disclosed |
| `upload` | attach each approved document; the returned sha256 must equal the approved digest | documents disclosed |
| gate before send | as for the browser (generation-fenced) | `sending` |
| `submit` | once, `Idempotency-Key: <attempt id>` | final submission |
| `reconcile` | GET status by idempotency key; read-only | none |

How outcomes are classified:

| What the API does | Outcome | Notes |
|---|---|---|
| 401/403 on the schema | `failed_safe` | before disclosure |
| 429 on the schema | `failed_safe` | before disclosure; not retried |
| schema differs from the approval | `failed_safe` | before disclosure |
| 422 on submit | `rejected` | |
| 200 with a receipt | `confirmed` | evidence is `receipt_ref_sha256`, never the receipt |
| 429, 5xx or a timeout after sending | `unknown` | never resent; a second delivery is `ignored` |
| accepted, then the response is lost | `unknown` | the ledger shows one acceptance; `runner.reconcile_api` reports `accepted` and records an event, but leaves the state for the user |

Rules for the adapter:

- Requests go only to the destination's own fixture origin, and redirects are never followed.
- The bearer token lives in settings (`NOEFFORTS_FAKE_API_TOKEN`). It is never written to
  evidence, events or logs.
- Exceptions are logged by type only.

**Credentials for a real API** are out of scope. They would need:

- a per-employer agreement;
- secret storage;
- a capability entry with `observed` evidence;
- a separate approval.

## 4. Browser adapter lifecycle

1. **Inspect** the fixture form (or, read-only and separately approved, a real one). Map
   every control to exactly one job-data field by evidence.
2. **Build an immutable package:** answers, consents, documents (digests), destination and
   form fingerprint, policy versions. Hash it.
3. **Review and approval** bind that hash, the provider and its version, with an expiry.
4. **Start an isolated browser session:** own network, PID and mount namespaces; an egress
   proxy restricted to the destination host and port.
5. **Revalidate before disclosure** (gate 1). The page is re-extracted and must equal the
   approved schema, and the approval must still be live. Nothing is typed until then.
6. **Fill only supported fields:**
   - exact labels;
   - dropdowns only through a named strategy with post-action evidence (D31);
   - unsupported controls are refused, never interpreted.
7. **Read back** every value and each uploaded file's identity (name and digest).
8. **Pause at checkpoints** (section 5). The state is preserved and the user is told what is
   needed.
9. **Revalidate immediately before the final submit** (gate 2, fenced by `generation`).
10. **Submit once,** only under the separate send authorization.
11. **Classify** the outcome as confirmed (receipt bound to the attempt), rejected or
    unknown.
12. **Reconcile unknown outcomes** with the user. Never resend automatically.

Disclosure boundaries. Each one is reached at a different point:

| Action | Is it a disclosure? | Boundary in NoEfforts |
|---|---|---|
| Filling a field | Yes, potentially. Page scripts can read typed values and may transmit them. | gate 1 (`disclosure_started_at`) before the first keystroke |
| Uploading a document | Yes, always. The file leaves the machine when attached. | gate 1; recorded as a disclosure with its digest |
| Autosave or background requests | Yes, without a click. The fixture counts them as disclosures. | covered by gate 1; any request outside the destination is refused by the proxy |
| Moving to a later page | Yes. A "Next" usually sends the page's data and is often validated by the server. | **not supported:** multi-page forms are refused (`unsupported`). A future multi-page adapter needs a disclosure boundary per step. |
| Final submission | the application itself | gate 2 (`sending`), once, never retried |

## 5. CAPTCHA and verification checkpoints (`providers/checkpoints.py`)

| Challenge | NoEfforts does | Resumable in NoEfforts |
|---|---|---|
| CAPTCHA | detects it, stops before disclosure, tells the user to apply on the employer's site | no |
| Bot challenge | detects it, stops | no |
| Login or MFA | stops; never signs in for the user | no |
| SMS code | stops; text-message codes are not supported | no |
| Email code | the user types the code; it is used once, for that attempt and round, then erased | yes, with manual entry only |
| Identity check | stops | no |

NoEfforts never:

- solves or outsources a CAPTCHA;
- evades bot protection or bypasses access control;
- infers a code or a credential;
- reuses a code outside the attempt and round it was issued for (old rounds are replays,
  covered by the execution tests).

A static test fails if a known solver service or stealth library name appears in `app/`. **No
mailbox integration exists.** Any future one requires a separate compliance and technical
decision. Mobile codes stay manual and are currently unsupported.

## 6. Discovery: Freehire (fixture only)

**Freehire: Potential future discovery provider; not yet connected or validated.** Nothing
calls Freehire. There are two providers:

- **`freehire`:** a client built to Freehire's documented public read API, tested only against
  a local stand-in (`fixtures/ats_receiver/freehire_fixture.py`). It refuses any base URL that
  is not a fixture origin.
- **`freehire_mock`:** reads `fixtures/discovery/freehire_mock.json`, whose record shape is
  NoEfforts' own invention.

The interface, contract, filters, merge policy, API and status table are in
`docs/discovery.md`. The rest of this section describes the shared rules.

**Integration plan:**

- **Optional and replaceable.** Freehire supplies job metadata and application URLs only. No
  job source is authoritative for the employer's live application schema: the form is always
  captured from the employer's own page, and an import never creates a form (tested).
- **Deduplication** against existing jobs, in this order:
  1. the normalized application URL;
  2. the job URL;
  3. the ATS requisition identity, which is part of the job's dedupe key when the host is
     recognised;
  4. one conservative employer, title and location match;
  5. the source's own id, which keeps each record linked.
- **Provenance and freshness:** the source provenance and the import timestamp are kept for
  every record.
- **Before any live integration:** the terms, permitted use (personal prototype only, D34),
  rate limits, freshness and field coverage are validated. Freehire is not contacted
  otherwise.

**Normalized record** (`discovery/provider.NormalizedJob`):

- source and identity: source provider, source job id, raw-source fingerprint (sha256);
- the posting: title, employer, location, remote/hybrid/onsite/unknown, published date,
  description summary;
- URLs: the job URL and application URL, exactly as given;
- ATS, detected from known hostnames only (a fixture origin is "unknown");
- source facts;
- `closed_at_source` and the reasons it cannot be linked (`missing`).

The import timestamp is on the stored row.

**Source facts versus candidate facts.** What a source says about sponsorship is stored as a
source fact: `{"value": yes|no|unknown, "stated_by": provider}`. It is never written to the
candidate's profile.

**Unknown stays unknown.** Nothing about sponsorship, authorization, salary, location or
eligibility is inferred. A missing field stays missing or `unknown`.

**Deduplication:**

- One row per (user, provider, source job id).
- An unchanged fingerprint is counted as `unchanged`.
- Complete records go through `jobs.upsert_job`. Its canonical URL drops tracking parameters,
  so two source records for one posting share one tracker job, and a posting the user already
  tracks is linked rather than duplicated.

**Incomplete records** (no URL, title or employer) are kept, not linked. The user imports the
job manually (`POST /api/jobs`).

**Stale records:**

- a record missing from the latest listing is marked "not in the latest source listing";
- a record closed at the source is marked "closed at source";
- the tracker job is never changed or deleted by this;
- a record listed again is un-staled.

**Application route** (`service.application_route`):

- a record without a tracker job is a manual handoff: `source_record_incomplete` ("Import this
  job manually.") or, for a posting closed at its source before it was linked,
  `source_posting_closed`;
- a linked record has its tracker job's route (`routing.route_for_job`): a manual handoff until
  the job's application form has been captured, then `routing.decide`. For the fixture posting
  that is `greenhouse_dom`; for a real origin it is the manual handoff.

## 7. Workday (future adapter specification only)

**No Workday automation exists.** `workday` is registered as a *planned* provider:

- it has no operations, no capabilities, no code, no fixture and no observation;
- routing turns every Workday job into a manual handoff that says so ("Workday applications are
  not supported yet"), never into the Greenhouse or fixture adapter (tested).

A Workday adapter will likely require the following. These are expectations, recorded as
"expected" traits, not observations:

- **Employer-scoped accounts and sessions.** Each employer's site may need its own candidate
  account, so a session belongs to one employer.
- **User-assisted login and verification.** The user signs in and completes any email or
  security prompt themselves. NoEfforts never creates accounts, stores passwords or enters
  codes for the user.
- **Multi-step forms.** Each "Next" is a disclosure boundary (section 4), so the single-gate
  model is not enough. Pages and drafts may be saved by the employer long before the final
  submit.
- **Repeating work-history and education records.** These are lists, not a flat field set:
  list-shaped answers with stable order and readback per entry.
- **Custom dropdowns and autocomplete widgets** need D31-style strategies with evidence.
  Search-as-you-type stays unsupported until proven.
- **Résumé parsing and prefill validation.** Fields Workday prefills from an uploaded résumé
  must be read back and compared with the approved package before going on. A prefilled
  value is never accepted as approved.
- **Per-step validation.** The server can reject a step after data was sent. That is
  classified per step as rejected or unknown, never retried blindly.
- **Checkpoints** for CAPTCHA, security prompts, unfamiliar questions and unsupported widgets
  (section 5).
- **Separate approvals:** one before any data disclosure and another before the final
  submission.

Safe implementation sequence: the admission ladder (`docs/provider-admission.md`, "How to
admit the next ATS"), with its owner stops; each needs its own approval before the next.
Workday is computed at `planned`, stopped before `public_doc_reviewed` (no public-docs and
terms review is recorded). What Workday adds to the ladder's steps:

- the local synthetic fixture needs multi-page forms, an account checkpoint, repeating
  sections, custom controls, step validation and per-step disclosure counting in the receiver
  ledger;
- the read-only observation follows the `greenhouse_readonly` model (GET only, no account, no
  typing), and an evidence-backed extractor maps each observed control to exactly one field;
- a user-assisted login and checkpoint strategy: the user signs in themselves, and NoEfforts
  never stores the credentials;
- the rehearsal (D41) has a disclosure boundary per page: each "Next" is one.

## 7b. Lever (future adapter specification only)

**No Lever automation exists, and nothing was read from Lever** (no page, API or
documentation). `lever` is registered as a *planned* provider:

- it has no operations, no capabilities, no code, no fixture and no observation;
- **identity** (`jobs.canonical.detect_ats`): a posting is `jobs.lever.co/{company}/{posting
  id}` or `jobs.eu.lever.co/…`, where the posting id is a UUID. An `/apply` suffix and query
  strings are accepted, and `lever-source…` tracking parameters are dropped. The vendor's own
  site, a company page without a posting, a non-UUID id and lookalike hosts are not Lever
  (tested);
- **routing** turns every Lever job into a manual handoff that says so ("Lever applications
  are not supported yet", `planned_adapter_only`). It is never routed to the Greenhouse or
  fixture adapter, even with a form captured as Greenhouse, and its form is never captured as
  a Greenhouse form (tested);
- **support wording** is "Planned only: no automation exists"
  (`providers/wording.py`).

Expectations for a future Lever adapter. They are unverified, recorded as traits only where
the specification expects something, and as "unknown" otherwise:

- **CAPTCHA possible:** expected. A checkpoint for the user, never solved.
- **Login:** unknown. A hosted application form without a candidate account is expected but
  not verified, so the trait is not "no".
- **Multi-step:** unknown. A single page is expected but not verified.
- **Manual verification:** unknown.
- **Sensitive questions** (for example an optional demographic survey) would follow the
  existing consent model: never inferred, disclosed only by an explicit per-question choice.
- **Any API route** would need the employer's own authorization. None exists for
  candidates, so the authorized-API route does not apply.

Safe implementation sequence: the admission ladder (`docs/provider-admission.md`, "How to
admit the next ATS"). Lever is computed at `planned`; its next stage, `public_doc_reviewed`,
needs the owner's approved review of Lever's public documentation and terms, recorded in
repository-safe form. A local fixture, a read-only observation, the rehearsal (D41) and a pilot
follow, the last three each with their own approval.

## 8. Greenhouse status (no Greenhouse request was made in this task)

The short, evidence-linked handoff is `docs/greenhouse-readiness-gap.md`.

**Greenhouse is not generally supported.**

- **Fixture compatibility exists:** `greenhouse_hosted` and `greenhouse_dom` (version 3)
  against two labelled local approximations.
- **Real-page observation exists only within the earlier read-only limits** (runs #3–#9; the
  last, run #9 on `e1bd9e7`, is evidence only).
- **Real form mapping is partial:**
  - 19 mapped fields have a consistent required state;
  - the résumé and cover letter map through their labelled groups;
  - the résumé is required by its group.
- **Not proven:**
  - dropdown behaviour: no opening evidence within run #9's 600 ms window, which does not
    show they cannot open; the D31 strategies are fixture-only;
  - location handling: the missing location control and the page-managed coordinates;
  - the unmatched required controls (`u1`, `u2`);
  - real uploads;
  - real submission.
- **Real Greenhouse origins stay blocked** for filling and submission. `real_destinations` is
  false, and real origins route to a manual handoff.
- **Fixture success is not real-site compatibility.** No mapping rule was weakened to change
  this.
- **Pilot readiness is computed, not claimed** (`providers/readiness.py`,
  `GET /api/providers/greenhouse_dom/readiness`): the seven conditions for proposing a live
  filling pilot, each derived from recorded evidence. Today none of the seven is met. The
  owner's optional manual check (Path A, `providers/path_a.py`) is kept as fixed choices only
  and meets none of them.

- **A first real submission would need a rehearsal first** (E6,
  `docs/rehearsal-prerequisite.md`): a valid recorded rehearsal on the same employer board by
  the same provider, checked at five layers. It is built and tested on the fixtures only and
  enables nothing; real Greenhouse origins are refused before it is reached.

The real-page diagnostic work (read-only observation, `gh_readonly.py`, the decision point in
`docs/greenhouse-readonly-compatibility-proposal.md`) is kept separate from any future
submission development. No observation can become filling: the observation provider has no
fill, upload or submit operation.

## 9. Safety rules and the tests that hold them

| Rule | Evidence |
|---|---|
| Standard questions use approved facts first, deterministically (no LLM) | `test_full_workflow_with_zero_llm_calls`, `test_fixture_classification_table`, `test_unknown_or_unapproved_facts_never_resolve` |
| Long-form content is manual unless an approved AI provider is connected | `test_long_form_is_unresolved_without_draft`, `test_drafting_unavailable_without_provider`, `test_fake_provider_draft_is_validated_and_needs_acceptance` |
| Never fabricate qualifications, salary, legal answers, sponsorship, authorization, demographics or coordinates | `test_sponsorship_timeframes`, `test_without_sponsorship_needs_both_facts`, `test_vague_or_country_less_questions_need_user`, `test_option_mismatch_is_not_guessed`, `test_sensitive_needs_answer_and_disclosure_consent`, `test_location_job_is_a_checkpoint`, `test_an_unsupported_required_control_is_a_checkpoint_before_disclosure` |
| CAPTCHA is a manual checkpoint, never solved or bypassed; claimed only where the adapter detects one | `test_a_captcha_becomes_a_user_action_never_an_automated_solve`, `test_captcha_stops_before_anything_is_disclosed`, `test_a_captcha_on_the_form_stops_before_anything_is_disclosed`, `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one`, `test_no_solver_or_evasion_code_exists`, `test_no_checkpoint_is_ever_completed_by_noefforts` |
| Email or mobile verification needs an explicit user checkpoint | `test_security_code_wrong_then_right` (the code is entered by the user; old rounds are replays); SMS codes are unsupported (`checkpoints.py`) |
| Unknown outcomes are reconciled, never resubmitted | `test_accepted_but_response_lost_is_unknown_and_never_resent`, `test_outcomes_after_sending`, `test_outcome_classification` |
| An approval binds destination, adapter and version, documents, answers, consents and relevant facts | `test_manifest_binds_owner_destination_documents_and_policy`, `test_approval_records_the_execution_method`, `test_accepted_draft_depends_on_its_facts` |
| Any material change invalidates the approval | `test_an_adapter_version_mismatch_blocks_queueing_and_execution`, `test_original_adapter_approval_cannot_run_through_a_new_route`, `test_edit_committed_after_approval_invalidates_before_queue`, `test_drift_after_approval_stops_before_anything_is_disclosed`, `test_granting_the_api_retires_a_browser_approval_and_revoking_retires_it_again` |
| A known API connector is never chosen without the user's explicit authorization | `test_a_known_api_connector_is_never_selected_without_explicit_authorization`, `test_without_authorization_the_api_is_never_contacted` |
| A job source is never a form schema | `test_freehire_imports_are_never_treated_as_form_schemas` |
| Audit events and logs carry safe metadata only (no applicant data, documents, credentials, employer or posting identifiers, raw exceptions or page content) | `tests/test_audit_privacy.py`: sanitizer tests per prohibited category, `test_record_sanitizes_before_anything_is_stored`, `test_route_decisions_are_audited_without_applicant_or_external_data`, `test_a_full_application_leaves_no_applicant_or_posting_data_in_audit_events`, `test_a_rejected_draft_records_a_reason_code_not_its_content`, `test_unexpected_runner_errors_are_logged_by_type_only`, `test_the_egress_proxy_never_logs_destination_hosts` |
| Audit rows stored before sanitizing are repaired once, irreversibly and idempotently, with counts-only output | `tests/test_audit_repair.py`: `test_repair_sanitizes_every_legacy_row_and_a_second_run_changes_nothing`, `test_a_failed_repair_reveals_no_legacy_content`, `test_the_migration_repairs_legacy_rows_reports_counts_only_and_is_irreversible` |
| Audit references are keyed and user-scoped; legacy unkeyed references are removed | `tests/test_audit_refs.py`: `test_same_user_and_input_give_a_stable_versioned_reference`, `test_different_users_never_share_a_reference_for_the_same_input`, `test_changing_the_key_changes_every_reference`, `test_a_missing_or_short_key_fails_closed_without_showing_it`, `test_production_refuses_a_test_only_key`, `test_stored_references_are_user_scoped_and_hold_no_raw_key_or_secret`, `test_the_v2_migration_removes_legacy_references_and_is_idempotent` |
| Internal failures reach users only as generic wording and fixed codes | `tests/test_error_boundary.py`: `test_an_isolation_failure_reaches_the_user_as_a_code_only`, `test_a_form_capture_mismatch_shows_a_generic_message_and_a_code`, `test_an_unexpected_error_is_a_generic_500_logged_by_type`, `test_expected_errors_keep_their_status_and_own_messages` |
| Access logs carry route templates, never raw paths | `tests/test_access_log.py`: `test_access_lines_carry_the_route_template_never_the_raw_path`, `test_raw_access_records_from_the_server_are_dropped`, `test_the_real_server_prints_route_templates_only` |
| Retained errors, evidence and library logs keep no values, hosts or field keys | `tests/test_retained_data_privacy.py`: `test_a_database_error_never_carries_bound_values`, `test_a_failed_task_is_logged_by_exception_type_only`, `test_destinations_are_classified_without_a_lookup`; `test_browser_cannot_reach_other_origins` |
| An unsupported ATS is never routed to another ATS's adapter | `test_a_workday_job_is_shown_unsupported_never_routed_to_greenhouse`, `test_a_form_from_another_ats_is_refused` |

## 10. Admitting a provider (I2)

`docs/provider-admission.md`: how far each provider's code and recorded evidence take it on the
admission ladder (`providers/admission.py`, `GET /api/providers/admission`), the eleven
requirements and the checks behind them, the owner's four boundaries, the cap at
`rehearsal_ready`, the frozen waivers and known gaps, and the steps for the next ATS. A
provider's support state never ranks above its admission. Since I2 a captured form whose source
no adapter executes is refused (`no_adapter`) instead of falling through to the generic fixture
adapter (`policy.FORM_SOURCE_ADAPTERS`, `GENERIC_FORM_SOURCES`).
