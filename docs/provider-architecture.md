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
- an API provider without `official_api_submission`, or a browser provider claiming it.

So a fixture success can never become a live claim by accident. Reaching `observed`,
`live_fill` or `live_submit` requires an edit to the registry and a review. The registry is
served at `GET /api/providers` and inside `GET /api/execution/capabilities` (`providers`).

### Capability matrix (registry as committed)

Columns: FA = `fixture_ats`, GH = `greenhouse_hosted`, GD = `greenhouse_dom`, API =
`fake_api`, RO = `greenhouse_readonly` (observation), FH = `freehire_mock` and `freehire`
(discovery; identical rows), MH = `manual_handoff`. A dash means none.

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
| captcha_checkpoint | fixture | fixture | fixture | – | – | – | – |
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

- a manual handoff until the job's application form has been captured;
- after that, `routing.decide`. For the fixture posting that is `greenhouse_dom`; for a real
  origin it is the manual handoff.

## 7. Workday (documentation and fixture strategy only)

Nothing for Workday is built or accessed. Workday needs its own adapter rather than a
variant of the Greenhouse one. These are expectations to verify, not observations:

- **Employer-scoped candidate accounts.** Each employer's site may require its own account,
  so a session belongs to one employer.
- **Login and session requirements.** Signing in is a checkpoint (`login_required`).
  NoEfforts never creates accounts or enters passwords for the user.
- **Multi-page navigation.** Each "Next" is a disclosure boundary (section 4), so the
  single-gate model is not enough.
- **Repeating employment and education entries.** These are lists of records, not a flat
  field set. The package needs list-shaped answers with stable ordering and readback per
  entry.
- **Custom controls.** Search-as-you-type selectors, date widgets and nested dropdowns need
  D31-style strategies with evidence.
- **Step-level validation.** The server can reject a step after data was sent. That must be
  classified as rejected or unknown per step, never retried blindly.
- **Possible verification checkpoints** (email, SMS, bot checks), per section 5.
- **Disclosure before the final submit.** Pages and drafts may be saved by the employer well
  before submission.

Safe implementation sequence. Each step needs its own approval before the next:

1. A local synthetic fixture: multi-page, an account checkpoint, repeating sections, custom
   controls, step validation and per-step disclosure counting in the receiver ledger.
2. A read-only, approved compatibility observation (the `greenhouse_readonly` model: GET only,
   no account, no typing).
3. An evidence-backed extractor mapping each observed control to exactly one field.
4. A supported-control matrix, with capability entries at `fixture` and then `observed`.
5. A user-assisted login and checkpoint strategy: the user signs in themselves, and NoEfforts
   never stores the credentials.
6. An approved dry-run filling fixture, with a disclosure boundary per page.
7. A separately approved real pilot.

## 8. Greenhouse status (no Greenhouse request was made in this task)

The short, evidence-linked handoff is `docs/greenhouse-readiness-gap.md`.


- **Observed:** the real page structure, in limited read-only runs, the last being run #9 on
  `e1bd9e7` (evidence only; see `docs/implementation-status.md`).
- **Required state:** all 19 mapped fields have a consistent required-state interpretation.
  The résumé is required by its group.
- **Dropdowns: unresolved.**
  - Run #9 recorded no opening evidence for any of the 12 dropdowns within its 600 ms
    window.
  - That does not show they cannot open.
  - The D31 strategies are fixture-only.
- **Blockers:**
  - the location-related controls (the missing location control and the page-managed
    coordinates);
  - the unmatched required controls (`u1`, `u2`).
- **Adapter:** `greenhouse_dom` (version 3) keeps refusing that posting for live filling and
  submission. `real_destinations_enabled` is false.
- **Fixture success is not real-site compatibility.** No mapping rule was weakened to change
  this.
