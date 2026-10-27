# Freehire-first architecture

Status: 2026-10-27; code references are to NoEfforts `3af29f0` (Q1, D50) unless marked; C6 (D51) landed afterwards as `b6e4cf4`; completeness-critic fixes G7-G10 and G15 applied.

Finding ids (gh-/la-/ans-/pl-/sec-), "map Qn" and "critic Gn/Ln/Cn" refer to the review's working notes, which are not committed. C1-C18 and L1-L4 are the preparation steps listed in `implementation-plan.md` (§0 and "Remaining preparation steps"); `docs/implementation-status.md` names the ones already implemented or referenced.

A design for the workflow Freehire discovery → normalized records →
dedup and eligibility → match and rank → preparation → provider routing → execution →
confirmation → outcomes. It describes NoEfforts at `3af29f0` (C3-C5 at `7669c61`, then the Q1 quarantine fix), the Freehire refresh of 2026-10-26, and the gaps.
Nothing here is live: the Freehire client refuses every non-fixture base URL
(`backend/app/modules/discovery/provider.py:312-320`) and every real employer destination is
refused (`backend/app/modules/execution/policy.py:214-215`).

Labels: **CONFIRMED** (code, a fetched page or Freehire source at `ab47628` shows it),
**HYPOTHESIS**, **UNKNOWN**, **NEW** (proposed, not built). Paths: `M/` =
`backend/app/modules/`, `C/` = `backend/app/core/`, `D/` = `docs/`.

## 1. Data flow

```
 Freehire documented read API (keyless, or a plan key held server-side)
        |  GET /jobs, GET /jobs/{public_slug}           [discovery: off by default; fixture-only today]
        v
 (1) M/discovery/provider.py  FreehireApiProvider     header-only pacing; 429 reported, never retried;
        |                     normalize_job()          documented fields only; tri-state source facts
        v
 (2) discovered_jobs (per user)  M/discovery/models.py   provenance, fingerprint, stale flag, attribution
        |
        v
 (3) dedup + eligibility       M/discovery/service.py, M/jobs/canonical.py, M/jobs/service.py
        |   link to an existing tracker job, or upsert a new one (ON CONFLICT on (user_id, dedupe_key))
        |   source facts shown, never compared with the user's facts         [eligibility check: NEW, design §5.4]
        v
 (4) match / rank              M/jobs/service.py:119-155 (explanations only; no score)   [ranking: NEW]
        |
        |   ==== user action: "Track / Prepare" (POST /applications) — nothing below is automatic ====
        v
 (5) preparation               M/preparation/ (form capture by an execution-side path, deterministic
        |                      resolver, documents, package, approval bound to the content hash)
        v
 (6) provider routing          M/providers/routing.py  authorized API -> browser adapter -> checkpoint/manual
        |                      admission stage caps what a provider may do (M/providers/admission.py)
        v
 (7) execution                 M/execution/ durable attempt, two gates, generation-fenced writes,
        |                      rehearsal prerequisite, sandboxed browser behind an egress proxy
        v
 (8) confirmation              attempt-bound receipt -> submitted_confirmed; unknown -> submitted_unconfirmed
        |                      (quarantine, reconciliation with stated evidence, never re-sent)
        v
 (9) outcomes                  M/applications/states.py Outcome; insert-only application_events
                               [funnel, outcome provenance and "assessment": built (S2, D53)]
```

Trust boundaries (CONFIRMED unless NEW):

- **Freehire data is untrusted input.** Text is reduced to plain text and truncated
  (`M/discovery/provider.py:118-126`; `tests/test_freehire_discovery.py::test_untrusted_markup_becomes_short_plain_text`).
- **Job text never decides what is drafted** (rule, NEW). The 500-character summary is copied into
  `Job.description` when a job is linked (`M/discovery/service.py:195`). No drafting provider
  exists today (`M/preparation/drafting.py:72-74`), but any future prompt must receive job text
  only as quoted, untrusted data. It can never change which approved facts are used, add a fact
  or change a number. The legacy bot put job text and page labels straight into its prompts
  (`legacy-audit.md` U12; `legacy:src/llm.py:161-171,276-287`). Test: `reliability-test-plan.md`
  R11.9 (NEW, written once a provider exists; `implementation-plan.md` C15).
- **A Freehire record is never a form.** Imports are never treated as form schemas
  (`tests/test_execution_routing.py::test_freehire_imports_are_never_treated_as_form_schemas`;
  decision D35).
- **The only path from discovery to an application is a user action.** Discovery creates jobs
  only (`M/discovery/service.py:186-197`); the only `insert(Application)` is the user's
  `POST /applications` (`M/applications/router.py:149-164`).
- **Freehire is never an execution destination** (D34). Its `/jobs/{slug}/direct-apply`,
  `/submissions/prefill`, `/jobs/resolve`, assistant and OJCP surfaces are out of scope.

## 2. Integration contract

### 2.1 Endpoints

| Endpoint | Documented | Use | Label |
|---|---|---|---|
| `GET /jobs` (filters, offset paging) | yes | Import pages | CONFIRMED in use |
| `GET /jobs/{public_slug}` | yes | Refresh one record; serves closed jobs | CONFIRMED in use |
| `GET /jobs/{slug}/copies` | yes | Lists per-city copies with their own `apply_url` and the cluster size | NEW: candidate for §5 (possible duplicates) and an apply URL; not used today |
| `GET /jobs/find?url=` | yes | Returns the slug for a URL, or `null` with `meta.ats_board: bool` | NEW: optional "is this already in the catalogue" check; never as ATS identification (it does not name the ATS) |
| `GET /plans` | described, not an OpenAPI path | Would give `api_limits` | Not called; do not depend on it |
| `GET /jobs/{slug}/apply-form` | yes | A reading preview: no control ids, options, values, consent text or capture time | Never a fill schema; at most "questions to prepare", shown as untrusted text (NEW, optional) |
| `/jobs/{slug}/direct-apply`, `/submissions/prefill`, `/jobs/resolve`, `/ojcp/*`, `/assistant/*`, `/me/*` | partly or not | Submitting on Freehire, writes, authenticated or undocumented | Never used |

### 2.2 Job object fields

| Field | Documented | NoEfforts use | Notes |
|---|---|---|---|
| `public_slug` | yes | `source_job_id` | Stable public identity: minted once, survives close and reopen (Freehire `jobs.sql:399-402`). CONFIRMED. **Stable per row only:** Freehire's row identity is `(source, external_id)`, and a repost under a new `external_id` is a new row with a new slug (Freehire `jobs.sql:403`; `jobreality/classify.go:27-31`). So dedup by slug misses reposts (§5.2) |
| `title`, `company`, `location`, `cities` | yes | Normalized fields | Truncated plain text (`M/discovery/provider.py:440-449`) |
| `url` | yes | `job_url` | **Always tagged** `utm_source=freehire.me` and re-encoded (Freehire `outboundurl.go:47-59`); for aggregator sources it is a tracking redirect, not the employer's page; some adapters append a referral code. CONFIRMED (Freehire code); the reference does not say so |
| `source` | yes | `source_platform` (display only) | Freehire's ingest provider key; names the aggregator for around 100 sources. Never the ATS (D35). CONFIRMED |
| `posted_at` | yes | `published_on` | The *effective* date: source date unless missing or in the future; some boards restate it every crawl |
| `created_at`, `open_within_days` | yes | not read | NEW: `created_at` is the better "first seen" date for freshness |
| `updated_at` | yes | `source_updated_at` | Bumped by content changes only |
| `closed_at` | yes | `closed_at_source` | Lists never contain closed jobs; the detail endpoint serves them |
| `work_mode` | yes | `workplace` | Top level; deterministic dictionary |
| `enrichment.employment_type` | yes | `employment_type` | Deterministic dictionary value on read |
| `enrichment.visa_sponsorship` | yes | `source_facts.sponsorship_offered` with `basis: "provider enrichment"` | Model-extracted; absent = not stated; reliability UNKNOWN. Never compared with the user's sponsorship fact |
| `enrichment.summary` | yes | not read | Model-synthesised; not shown as the employer's text |
| `description` | yes | `description_summary` (500 chars) | Plain text |
| `reality{class, age_days, repost_count, mass_posting_count, fake_freshness}` | yes | not read (D: deliberately) | Deterministic (Freehire `jobreality/classify.go`). NEW, owner decision: show as "Freehire says: likely evergreen / reposted N times", display-only, never a filter on facts |
| `last_seen_at`, `ghost`, `auto_apply_available`, `metros`, `direct_apply`, `ai_interview_reports`, vote counters | **no** | never read | Present in Freehire code, absent from the reference. Must not be read as facts (`tests/test_freehire_discovery.py::test_undocumented_fields_are_not_read`) |
| `application_url` / `apply_url` on the job | **no** (only on `/copies` items, where it equals the tagged `url`) | `application_url = None` (`M/discovery/provider.py:454`) | CONFIRMED there is none |

**Rule (CONFIRMED in code, keep):** read documented fields only; record the field *names* seen
(`raw_keys`) but never the payload (`tests/test_freehire_discovery.py::test_no_raw_payload_is_kept`).

## 3. Normalization and provenance

- **Normalized record** (`M/discovery/provider.py:38-68`): every value as the source gave it or
  `None`, never guessed; `workplace` and source facts tri-state; `missing` lists why a record
  cannot be linked automatically; `attribution` shown with every listing. CONFIRMED.
- **Provenance to keep per record:** provider name, `public_slug`, fetch time, the documented
  field names present, the fingerprint, and for each source fact `stated_by` and `basis`.
  CONFIRMED (except fetch time per field: UNKNOWN whether stored separately from `last_seen_at`).
- **Fingerprint churn (CONFIRMED from both codebases, effect unmeasured).** NoEfforts fingerprints
  the whole raw record (`M/discovery/provider.py:103-104`) and counts a differing fingerprint as
  "updated" (`M/discovery/service.py:239-246`). Freehire's `reality.age_days` changes daily and
  its counters change with traffic, so nearly every refresh would count as "updated", often with
  empty `changed_fields`. **NEW:** fingerprint only the documented fields NoEfforts reads,
  excluding `reality` and counters, with a test.
- **Tracking parameters.** The canonical URL drops `utm_*`, `source`, `src`, `ref`, `referrer`,
  `gh_src`, `gclid`, `fbclid` and Lever source parameters (`M/jobs/canonical.py:8-10`). CONFIRMED.
  Whether Freehire's referral parameters use other names is UNKNOWN; **NEW:** a canonical-URL test
  over a tagged URL, and display of the untagged URL to the user.
- **Aggregator URLs.** When the host is not a recognised ATS host, `ats_provider` is `unknown`
  (`M/jobs/canonical.py:46-87`) and the route is a manual handoff. CONFIRMED. A recognised ATS host
  reached through an aggregator redirect cannot be told apart statically (HYPOTHESIS that it
  occurs); the execution-side capture (§6) is what proves the destination.
- **Facts vs preferences vs source facts.** Source facts are the employer's or Freehire's
  statements about the job; they never enter the profile
  (`tests/test_discovery.py::test_missing_data_stays_missing_and_source_facts_stay_out_of_the_profile`).
  Discovery filters come from preferences only, and only when asked
  (`M/discovery/router.py:170-180`). CONFIRMED.

## 4. Freshness and expiry

| Signal | Source | Rule |
|---|---|---|
| Closed before linking | `closed_at` non-null | Never creates a tracker job (`M/discovery/service.py:182-185`); route `source_posting_closed`. CONFIRMED |
| Gone (detail 404) | refresh | The discovered row is marked stale, never deleted (`M/discovery/service.py:257-258,358-360`). CONFIRMED |
| Stale by absence | complete listings only | Never for Freehire, whose listing is not complete (`M/discovery/service.py:317-330`). CONFIRMED |
| Closed **after** linking | refresh | **Gap:** only the discovered row changes; the tracker `Job.status` is never set to `closed`, and preparation, approval and queueing never read it (map Q3). **NEW:** a warning on the job and review pages and a refusal to *approve* while the linked source says closed, overridable by an explicit user statement that it is still open (a user action, audited) |
| Age | `created_at` (first recorded), `posted_at` (effective) | Display both; never derive "fresh" from `posted_at` alone (boards restate it). NEW |
| Re-verification at the ATS | — | Not discovery's job. Before any send the execution side captures the live form and compares it with the approved package (D35; `tests/test_greenhouse_adapter.py::test_form_changed_after_approval_stops_before_disclosure`). Fixture-only today |

Legacy lesson: freshness from `max(published, updated)` made edited old postings look new
(`legacy:src/discover.py:206-215`); NoEfforts keeps the dates separate. CONFIRMED.

### 4.1 Malformed, stale and ambiguous records: none proceeds without a user action

| Record condition | Behaviour | Evidence | Can it proceed without a user action? |
|---|---|---|---|
| Malformed (not an object, or no usable `public_slug`) | Skipped and counted in an import; a malformed single-record refresh is a typed `bad_response` error and writes nothing | `M/discovery/provider.py:434-438`; `M/discovery/service.py:298-302,361-364`; `tests/test_freehire_discovery.py::test_malformed_records_are_skipped_and_counted` | No. CONFIRMED |
| Incomplete (no URL, title or employer) | Kept unlinked with the missing fields listed; route `source_record_incomplete` (import manually) | `M/discovery/provider.py:151-159`; `M/discovery/service.py:259-262,386-390`; `tests/test_freehire_discovery.py::test_incomplete_records_wait_for_a_manual_import` | No. CONFIRMED |
| Freehire direct-apply job (applications taken on Freehire) | Its `url` is empty (Freehire `jobview.go:44-48`), so it arrives as an incomplete record ("no job or application URL") and stays unlinked. Freehire is never an execution destination (D34) | `M/discovery/provider.py:151-154`; the same path as the incomplete-record test above | No. CONFIRMED (NoEfforts code; Freehire code at `ab47628`) |
| Closed before linking | Never creates a tracker job; route `source_posting_closed` | `M/discovery/service.py:182-185,380-385`; `tests/test_freehire_discovery.py::test_detail_serves_a_closed_posting_and_it_never_creates_a_job` | No. CONFIRMED |
| Closed or gone after linking | Only the discovered row is marked stale; the tracker job is unchanged, and preparation, approval and queueing never read it | `M/discovery/service.py:257-258,358-360` | Not automatically, but **residual gap**: the user can still prepare, approve and queue it with no warning. S3 adds a refusal at approval (`implementation-plan.md` S3; `reliability-test-plan.md` R5.11, R9.8) |
| Excluded by the user | `POST /applications` checks ownership only | `M/applications/router.py:145-147` | Not automatically; same residual gap and fix as above |
| Stale by absence | Applies to complete listings only, never to Freehire | `M/discovery/service.py:317-330` | Not applicable |
| Suspicious (scam, ghost job, repost) | No detection; Freehire's `reality` signals are not read (§2.2) | — | No automatic step exists; the user decides on each job |
| Ambiguous (several dedup candidates) | The conservative fallback links only on exactly one match; otherwise a new job is created | `M/discovery/service.py:168` | No. CONFIRMED |
| Any record | Discovery creates jobs only; the only `insert(Application)` is the user's `POST /applications`; approval and queueing are user actions; real destinations are refused | `M/discovery/service.py:186-197`; `M/applications/router.py:149-164`; `M/execution/policy.py:214-215` | **No. CONFIRMED** |

## 5. Dedup: across sources and against prior applications

### 5.1 What exists (CONFIRMED)

- Within discovery: one row per (user, provider, source id) (`M/discovery/models.py:17`); a repeat
  within one listing counts once (`M/discovery/service.py:303-305`).
- Discovery → tracker: match on canonical application URL, then canonical job URL; else a
  conservative fallback (exactly one URL-less job with the same employer key, title and location);
  else upsert (`M/discovery/service.py:139-197`).
- Tracker key: ATS requisition > employer + requisition > canonical-URL hash > employer + title +
  location fingerprint, inserted with `ON CONFLICT DO NOTHING` (`M/jobs/canonical.py:114-135`;
  `M/jobs/service.py:82-88`; `tests/test_jobs.py::test_concurrent_upserts_create_one_job`).
- Applications: one per (user, job), idempotent create (`M/applications/models.py:18`;
  `tests/test_applications.py::test_create_is_idempotent`).

### 5.2 Gaps

| Gap | Effect | Proposal (NEW) |
|---|---|---|
| Cross-ATS and careers-page copies get different keys | Same role, two applications | "Possible duplicate" checkpoint: same `employer_key` + normalized title (+ location when both have one) as a job that already has an application in any state past `draft`. Never auto-merge; the user confirms "different role" or links |
| The URL-matching fallback skips jobs that have a URL | A second job for the same posting | Same check as above, display-only on the Discover row |
| `/jobs/{slug}/copies` unused | Per-city copies not grouped | Optional: fetch copies on demand for one record; show cluster size; never auto-link |
| No prior-application signal on Discover or the job page | User cannot see "already applied" | Show the existing application's state and outcome on both pages (user-scoped query) |
| Greenhouse embed URLs without `for=` keyed on the employer name (`M/jobs/canonical.py:85-86,127`) | May not match the hosted-board URL (HYPOTHESIS) | A `dedupe_key` test over both URL forms |
| Reposts: the same role under a new `external_id` gets a new slug (§2.2) | Same role, a second application | The possible-duplicate check above covers it (same `employer_key` and normalized title); a Freehire fixture mode with the same employer and title under a new slug tests it (`reliability-test-plan.md` R5.9; `implementation-plan.md` S3) |
| "Have you applied here before?" answered from the bank across employers | Wrong statement | Not bankable under C6 (D51, `b6e4cf4`). A later step could pre-fill from NoEfforts' own history for the same employer, as a proposed value the user confirms (NEW, needs a decision) |

Legacy lessons guarded: LD-10, LD-11 (`legacy-audit.md`).

### 5.3 Rule

Dedup never deletes, merges or modifies a job the user already tracks
(`tests/test_freehire_discovery.py::test_existing_jobs_are_matched_by_url_then_conservatively_and_never_modified`).
CONFIRMED; keep.

### 5.4 Eligibility (job level)

No code compares a job's location or required authorization with the user's facts (map Q4).
CONFIRMED. A future check (NEW, needs a decision) must:

- read approved facts, preferences and source facts side by side and **show** them, never mix them;
- stay tri-state: "source says sponsorship offered: yes / no / not stated" next to "your
  sponsorship need: yes / no / unknown";
- never filter out or rank down a job silently on an inferred fact (legacy LD-41 dropped and
  admitted postings by substring);
- be advisory in discovery; the binding answers are still resolved per question at preparation.

## 6. Destination identification and validation

1. **A Freehire record never proves that a form is supported.** `source` may name an aggregator,
   `url` may be a tracking redirect, `auto_apply_available` is undocumented and "never a guarantee"
   in Freehire's own code. CONFIRMED.
2. **ATS identification is from known hostnames and paths of the URL only** (D35;
   `M/jobs/canonical.py:46-87`). Anything else is `unknown` and gets a manual handoff
   (`M/providers/routing.py:184-186`). CONFIRMED.
3. **Destination-form inspection is an execution-adapter step, not discovery scraping.** The form
   is captured only by the preparation/execution capture paths (fixture or pasted HTML today;
   real postings refused with 409, `M/preparation/router.py:175-200` at `3af29f0`; `:180-205` at
   `b6e4cf4`), under the provider-admission stage of that provider
   (`M/providers/admission.py`: `observed_read_only` needs a per-run owner approval). Discovery
   never fetches employer pages. CONFIRMED.
4. **Validation layers before any send** (CONFIRMED, in order): route refuses planned-only ATS and
   form/ATS mismatch → refuses a real origin or production → requires a captured form →
   unsupported required control is a checkpoint → `decide()` → `adapter_for` (fixture origin,
   same-origin submit URL) → `check_binding` and the rehearsal prerequisite at enqueue → both gates
   re-check binding and destination class → sandboxed browser behind a per-session egress proxy
   (`M/providers/routing.py:118-247`; `M/execution/policy.py:204-226`;
   `M/execution/service.py:106-128,396-413`).
5. **Known identity gaps** stay pinned by probes until closed: `identity_jid_any_host`,
   `identity_rules_disagree`, `identity_unknown_skips_form_check`,
   `identity_stored_unknown_not_redetected`, `identity_variant_unrecognised`
   (`M/providers/admission.py` `KNOWN_GAPS`; `D/provider-admission.md:202-217`). CONFIRMED.
6. **Before any live server-side fetch** (a live Freehire base URL or a live capture),
   `resolve_public_destination` (`C/urlsafety.py:93`) must be called; today nothing in `app/` calls
   it, because every server-side fetch is fixture-gated. CONFIRMED gap, to close before enabling.

Legacy lessons guarded: LD-40 (any host, any "Apply" link, any page with two identity inputs).

## 7. Rate limits, backoff and failure handling

| Item | Rule | Status |
|---|---|---|
| Budget per import | At most 5 pages × 50 records (`D/discovery.md:37`) | CONFIRMED |
| Pacing | From `X-RateLimit-Remaining` only; stop at 0 (`M/discovery/provider.py:410-417`). Do not hard-code Freehire's published 600/min: a pending strict anonymous mode (120/min, 2,000/day, Freehire `public_gate.go:31-36`) can be switched on without notice | CONFIRMED |
| 429 | Reported with `Retry-After`, never retried in the same run (`tests/test_freehire_discovery.py::test_a_429_is_reported_with_retry_after_and_never_retried`) | CONFIRMED |
| Backoff across runs | **Gap:** `Retry-After` reaches the error text only (`M/discovery/provider.py:349-359`); nothing stores a "not before" time (a grep of `M/discovery/` finds no `retry_after`, `cooldown` or `not_before`), so a user can re-import at once after a 429. **NEW:** persist a per-user "not before" from `Retry-After` (per account once multi-user) and refuse imports until then with a typed `DiscoveryError` (`rate_limited`). There is no automatic re-run. Test: `tests/test_freehire_discovery.py::test_an_import_before_retry_after_is_refused` (NEW; the fixture mode `fh_rate_limited` already sends `Retry-After: 30`, `fixtures/ats_receiver/freehire_fixture.py:120-123`) | Gap CONFIRMED; fix NEW (`implementation-plan.md` S6) |
| No rate headers | Nothing assumed, nothing waited (`::test_without_rate_headers_nothing_is_assumed_or_waited`) | CONFIRMED |
| `X-RateLimit-Reset` | Undocumented unit (seconds in Freehire code); do not schedule from it | CONFIRMED |
| Paging safety | Offset window ≤ 10,000; loops refused; truncation reported (`::test_paging_is_bounded_and_loops_are_refused`, `::test_truncated_listing_is_reported`) | CONFIRMED |
| Fetch all, then write | A failure mid-import writes nothing (`M/discovery/service.py:80-95,283-350`; `::test_provider_failures_change_nothing`) | CONFIRMED |
| Outage isolation | Manual jobs, imports and tracking keep working (`::test_an_outage_never_blocks_manual_jobs_imports_or_tracking`) | CONFIRMED |
| Errors are typed, never empty results | `DiscoveryError` kinds (`M/discovery/provider.py:91-97`) — the legacy bot reported outages as "no positions" (LD-46) | CONFIRMED |
| Import runs inside the HTTP request | Long imports block a request (`D/discovery.md:211-212`) | Gap; NEW: a background job with the same budget |
| Identification | Requests identify NoEfforts honestly (`M/discovery/provider.py:333`); no browser User-Agent, no stealth | CONFIRMED |

## 8. Retention and deletion

- **Stored:** normalized fields and a summary of at most 500 characters, copied into
  `Job.description` when linked (`M/discovery/service.py:195`); no raw payload, HTML, enrichment
  summary or counters. CONFIRMED.
- **Not implemented:** a TTL or purge for discovered rows; a delete endpoint for discovered rows
  or tracker jobs; account deletion (`D/implementation-status.md`, row "Account deletion / data export: not started"). CONFIRMED.
- **Freehire terms (2026-10-26):** the 30-day deletion after a plan ends was removed; a plan holder
  must stop *showing* postings when the plan ends and may keep stored data for internal analysis.
  The terms are silent on storage under keyless personal use. CONFIRMED (fetched page).
  - **NEW:** `docs/discovery.md` and D34 still describe the 30-day deletion; refresh them.
  - **NEW, owner decision:** the retention statement that each live run's approval must name
    (for example: "discovered rows kept until I delete them; a delete control is required first").
  - **NEW:** per-user delete of discovered rows, and a "hide Freehire-sourced postings" switch for
    a plan lapse (multi-user only).
- **Execution evidence:** 365 days, purged daily (`C/config.py:44`; `backend/app/worker.py:60`).
  CONFIRMED.

## 9. Privacy and approval boundaries

| Boundary | Rule | Status |
|---|---|---|
| What leaves NoEfforts to Freehire | Only the query: filters taken from preferences when the user asks (title, city, workplace, sponsorship filter). These are the user's preferences disclosed to a third party | CONFIRMED in code; NEW: the per-run approval must name the exact query |
| What never leaves | Profile facts, documents, answers, application history | CONFIRMED (discovery never reads facts, `D/discovery.md:148-149`) |
| API key | Server-side only, never shown (`::test_the_key_is_sent_by_the_server_only_and_never_shown`) | CONFIRMED |
| Tenancy | Every discovery query is user-scoped (`M/discovery/router.py:120-124,209`; `::test_discovered_jobs_are_user_scoped`) | CONFIRMED |
| LLM | None in discovery, matching or resolution | CONFIRMED |
| Application creation | User action only | CONFIRMED |
| Disclosure and submission | A separate approval to disclose (rehearsal) and to submit, both bound to the package hash; real destinations refused; live pilot permissions 1-4 unanswered (`D/live-pilot-gate.md:22-35`) | CONFIRMED |
| Inbox | No mailbox access of any kind; confirmation emails are not ingested (Gmail OAuth not started, D10) | CONFIRMED |
| Evidence | Minimal: no tracing, screenshots, answer values, codes or cookies (`M/execution/models.py:166`) | CONFIRMED |

## 10. Personal prototype vs multi-user

| Topic | Personal prototype (D34: one owner, their own search) | Multi-user / offered to others |
|---|---|---|
| Freehire licence | Keyless: "personal and non-commercial use … a tool you run for yourself" | **An API plan is required** ("showing our postings in a product or service you offer to others, paid or not") |
| Who may import | Should be the owner only. **Gap:** `POST /auth/register` is open and the discovery flag is per deployment, not per user (`M/identity/router.py:58-66`; `M/discovery/provider.py:486-493`) | Per-tenant scoping, one shared account budget, tenant-fair pacing |
| Attribution | "via freehire.me" on every listing (`::test_every_listing_is_credited_via_freehire`) | Same, plus the jobs list and CSV/XLSX export, which carry no credit today (`M/jobs/spreadsheet.py:26-38`) |
| End of plan | n/a | Stop showing Freehire-sourced postings (NEW); whether tracker jobs created from postings count as "showing" is UNKNOWN (needs Freehire's written answer) |
| Upstream rights | Same caveat | Freehire "do[es] not grant rights an employer or original source has not given us"; its own per-source terms check is still open; some sources are fetched with fingerprint spoofing or account harvesting (Freehire `fingerprinthttp.go`, `cmd/harvest-linkedin`). Legal review needed before commercial display |
| Porting Freehire code | If Freehire's ATS host table (`atsboard/board.go`, MIT) were ever ported, `THIRD_PARTY_NOTICES.md:3` ("No third-party source code has been copied") would become false and an MIT notice would be required (`legacy-audit.md` §7). Not proposed | Same |
| Competitor rule | CLAUDE.md forbids automated access to competitor dashboards and APIs; Freehire now sells consumer auto-apply. Whether the documented, licensed public read API is still allowed under that rule needs an explicit owner statement | Same, with more weight |

## 11. Live-access blockers (exact)

Personal-prototype live read:

1. **No approval for a live call exists.** Each run needs its own approval naming the query, page
   limit, time window and retention statement (`D/discovery.md:27-28`; D34).
2. **Code refuses non-fixture base URLs** (`M/discovery/provider.py:312-320`); a reviewed change is
   needed, which must also call `resolve_public_destination` (§6.6) and restrict imports to the
   owner's account (§10).
3. **Owner decision on the competitor rule** (§10).
4. **Owner retention statement** under keyless use (§8).
5. **Reachability:** the cloud sandbox proxy returned 403 for Freehire on 2026-10-19 (D7);
   not re-tested. UNKNOWN; a local run may be needed.
6. **Re-read the terms on the day of the run** (three revisions in ten days).

Multi-user: all of the above, plus an API plan, Freehire's written clarifications (§10), the
plan-lapse "stop showing" behaviour, attribution on every surface, a legal review of upstream
rights, multi-tenant pacing and per-tenant scoping.

Execution (for any employer destination): live pilot permissions 1-4
(`D/live-pilot-gate.md:22-35`); `DISCLOSURE_PERMISSION_RECORDED` and
`SUBMISSION_PERMISSION_RECORDED` are `False` (`M/providers/readiness.py:27-28`); admission is
capped at `rehearsal_ready` and no provider has reached it (`M/providers/admission.py:86-87`);
the Greenhouse terms review is unrecorded. CONFIRMED.

## 12. Open owner decisions

1. Competitor rule and Freehire (§10).
2. Retention statement for discovered rows (§8).
3. Whether to display Freehire's documented `reality` signals (display-only) (§2.2).
4. Whether a job-level eligibility view is wanted, and its exact wording (§5.4).
5. Whether "possible duplicate" should block preparation or only warn (§5.2).
6. Personal-prototype restriction in code: owner-only discovery (§10).
