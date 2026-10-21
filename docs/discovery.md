# Job discovery providers

Discovery providers only find jobs. They never submit applications, never inspect employer
forms, never bypass access restrictions and never infer application questions. A discovered
job says nothing about eligibility, sponsorship or whether NoEfforts can apply to it.

Manual job entry (`POST /api/jobs`) and CSV/XLSX import (`POST /api/jobs/import`) never depend
on a provider and keep working during a provider outage. This is tested.

## Provider status

| Provider | Implemented locally | External API configured | External API tested | Production-ready |
|---|---|---|---|---|
| `freehire`: client for Freehire's documented public read API | yes (fixture of the documented API) | **no** | **no** | **no** |
| `freehire_mock`: local mock file | yes (invented record shape) | n/a | n/a | no (refused in production) |

Freehire: **Potential future discovery provider; not yet connected or validated.** No request
to freehire.me was made while building or testing this. The client refuses any base URL that
is not a local fixture origin, so it cannot reach Freehire until that check is changed in a
reviewed commit.

## Configuration (server-side only; everything off by default)

| Setting | Default | Meaning |
|---|---|---|
| `NOEFFORTS_DISCOVERY_PROVIDERS` | `[]` | Feature flag. A provider runs only if it is listed. |
| `NOEFFORTS_FREEHIRE_BASE_URL` | empty | Must be a fixture origin in this version. |
| `NOEFFORTS_FREEHIRE_API_KEY` | empty | Optional. Sent as `Authorization: Bearer` by the backend only. |
| `NOEFFORTS_FREEHIRE_PAGE_SIZE` / `_MAX_PAGES` | 50 / 5 | Bounded paging. |
| `NOEFFORTS_FREEHIRE_MIN_INTERVAL_MS` | 1000 | Spacing between requests. |
| `NOEFFORTS_FREEHIRE_TIMEOUT_SECONDS` | 10 | Request timeout. |

Where the key is never exposed:

- the frontend, which only sees a "configured: yes/no" flag;
- the isolated browser, which never runs for discovery;
- API responses, logs and test output (tested).

The key lives in settings only.

## Freehire contract, as recorded (not re-verified in this task)

Source: `docs/research/freehire.md`. That was a documentation and source review on 2026-10-19
of freehire.me's API docs page and the MIT-licensed repository at `ec6e65f7`, plus one
1-record read made then. No Freehire request was made for this milestone.

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `https://freehire.me/api/v1/jobs/search` | the listing |
| `GET` | `https://freehire.me/api/v1/jobs/{public_slug}` | one job, closed jobs included |
| `GET` | `https://freehire.me/api/v1/status` | health |

- **Search parameters:**
  - `q`, `limit` (1–100) and `offset`;
  - facet filters, documented but not used by NoEfforts. NoEfforts filters locally, on what
    the source supplied.
- **Authentication:** none for public reads. A personal API key (Bearer) is documented for
  authenticated surfaces.
- **Rate limits** (read in Freehire's source, per IP): 600 requests per minute for public reads, 300 for
  `/agent/jobs/search`.
  - NoEfforts spaces requests at 1 per second by default.
  - It never retries. A 429 ends the run and reports `Retry-After`.
- **Pagination:** offset-based. `offset + limit <= 10000`, otherwise 400 "pagination too
  deep".
  - NoEfforts never asks beyond that window, and stops at `MAX_PAGES`.
  - It refuses a response whose `meta.offset` differs from the request, or a page identical to
    an earlier one (loop).
- **Response shape:** `{"data": [...], "meta": {"limit", "offset", "total"}}`. Each record has:
  - identity and source: `public_slug`, `source`, `external_id`;
  - `url`, the original posting with `utm_source=freehire.me` appended;
  - the posting: `title`, `company`, `location`, `description` (HTML), `cities[]`;
  - dates: `posted_at`, `updated_at`, `last_seen_at`, `closed_at`;
  - `enrichment{...}`.
- **Assumed, not verified:** the `enrichment` sub-keys `work_mode`, `employment_type` and
  `visa_sponsorship`. Values outside the known set are ignored and stay unknown. Sponsorship
  from enrichment is stored with basis "provider enrichment", because it may be
  machine-derived. It is never treated as the employer's statement.
- **Permitted-use assumptions** (from the review):
  - Freehire's terms forbid scraping beyond the documented API and bypassing rate limits or
    authentication, so NoEfforts uses only the documented read endpoints, within their limits;
  - no data licence was found, and job content belongs to the employers and sources, so it is
    used for the user's own job tracking only, never redistributed;
  - some upstream sources may have provenance issues of their own, which is one more reason
    every listing is shown as unverified.

## Normalized record (`discovery/provider.NormalizedJob`)

- **Identity:** provider and provider job id (`public_slug`).
- **The posting:**
  - employer, title, location, cities;
  - remote/hybrid/onsite or `unknown`;
  - employment type;
  - published date;
  - a plain-text summary: tags and scripts removed, at most 500 characters, always rendered as
    text.
- **URLs:** the job URL exactly as given, plus an application URL when a source gives a
  separate one.
- **ATS:** from known hostnames only. What the source says it crawled is kept separately
  (`source_platform`).
- **Freshness:** the source's `updated_at` and `last_seen_at`, and our own first-seen,
  last-seen and import times.
- **Source facts:** `sponsorship_offered` as yes/no/unknown with `stated_by` and `basis`.
- **Debugging reference:** `raw_ref` holds the provider, id, fingerprint and field names, never
  the raw payload. The raw payload is not stored.

## Import rules (`discovery/service.import_from`)

1. **Fetch first, write after.** An outage, a rate limit, bad JSON, a timeout or a pagination
   loop returns 503 and writes nothing.
2. **Malformed records** (not an object, no usable id) are skipped and counted. A repeated id
   within one listing is counted once.
3. **Filters** use the request's titles, cities, work modes and sponsorship ("offered" matches
   only a stated yes). "Use my preferences" fills empty filters from the user's preferences
   (targets). Facts such as sponsorship needs are never used.
   - A stated mismatch excludes the record.
   - Missing data is "not enough data": the record is kept and marked, unless the user asks
     for strict filtering. Missing data never counts as a match.
4. **Deduplication against the user's jobs:**
   - first the normalized application URL, then the job URL (tracking parameters dropped);
   - then, conservatively, exactly one existing job with no URL and the same employer, title
     and location;
   - the source id keeps each record linked across refreshes.
5. **Merge policy: discovery never modifies an existing tracker job.**
   - It links to the job as it is.
   - A refresh records which fields changed at the source (`changed_fields`, `changed_at`) and
     shows them. The user edits the job if they want to.
   - New jobs are created only when nothing matches.
   - A posting already closed at the source never creates a job.
6. **Incomplete records** (no URL, title or employer) are kept, unlinked, with the missing
   fields listed. The user adds the job by hand.
7. **Stale records:**
   - a record closed at the source;
   - a record no longer at the source (single-record refresh);
   - for complete-listing providers only, a record absent from a complete, unfiltered listing.
     The Freehire client is never treated as complete.

## API

| Method and path | Purpose |
|---|---|
| `GET /api/discovery/providers` | name, label, enabled, capabilities, configured flags (no values), status table |
| `POST /api/discovery/providers/{name}/healthcheck` | `{ok, detail}`; 409 when disabled |
| `POST /api/discovery/import` | run one import; 409 when disabled, 503 on a provider failure (nothing changed) |
| `GET /api/discovery/jobs`, `GET /api/discovery/jobs/{id}` | the user's discovered records; the detail includes the application route (manual handoff until a form is captured) |
| `POST /api/discovery/jobs/{id}/refresh` | re-read one record (`get_job`) |

All of these are user-scoped: another user's record returns 404. The job detail
(`GET /api/jobs/{id}`) lists the discovery sources of a job (`discovered_from`).

## UI

- **Discover** (`/discover`) shows:
  - the sources and their status;
  - a search form, shown only when a provider is enabled;
  - the import result: read, new, changed, unchanged, linked or new jobs, incomplete, filtered
    out, not enough data, unreadable;
  - each record's source, freshness, duplicate result, missing fields, "not enough data"
    fields, changes at the source, and its sponsorship statement with its basis.
- A banner says that listings are not verified and imply no eligibility, sponsorship or
  automatic application.
- The job page names the discovery source.

## Limitations

- **The Freehire contract is from a review on 2026-10-19.**
  - Before any live call, re-read the docs and terms and record any changes.
  - The `enrichment` keys, `work_mode` values and the single-job response wrapper
    (`{"data": {...}}`) are assumptions.
- **Imports run inside the request:** bounded by page count, timeout and spacing. A background
  job would be needed for larger imports.
- **Freehire listings are query-scoped, never complete,** so "missing from the listing" is never
  used to mark a Freehire record stale.
