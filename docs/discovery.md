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

Freehire: **Potential future discovery provider; not yet connected or validated.**

- **Product model:** personal prototype only (D34). Freehire's terms allow keyless use for
  "your own job search, research, or a tool you run for yourself". Showing postings to other
  people needs a Freehire API plan. Multi-user behaviour (a plan, and deletion within 30 days
  after it ends) is **not implemented** and waits on a plan or written clarification from
  Freehire.
- **No live access:** no request to freehire.me's API was made while building or testing
  this. The client refuses any base URL that is not a local fixture origin, so it cannot
  reach Freehire until that check is changed in a reviewed commit.
- **Before any live test:** it needs its own approval naming the exact query, page limit,
  time window and data-retention statement.

## Configuration (server-side only; everything off by default)

| Setting | Default | Meaning |
|---|---|---|
| `NOEFFORTS_DISCOVERY_PROVIDERS` | `[]` | Feature flag. A provider runs only if it is listed. |
| `NOEFFORTS_FREEHIRE_BASE_URL` | empty | Must be a fixture origin in this version. |
| `NOEFFORTS_FREEHIRE_API_KEY` | empty | Optional. Sent as `Authorization: Bearer` by the backend only. |
| `NOEFFORTS_FREEHIRE_PAGE_SIZE` / `_MAX_PAGES` | 50 / 5 | Bounded paging. |
| `NOEFFORTS_FREEHIRE_TIMEOUT_SECONDS` | 10 | Request timeout. |

There is no request-rate setting: Freehire documents no keyless figure, so none is assumed
(see "Rate limits" below).

Where the key is never exposed:

- the frontend, which only sees a "configured: yes/no" flag;
- the isolated browser, which never runs for discovery;
- API responses, logs and test output (tested).

The key lives in settings only.

## Freehire contract (public documentation as reviewed on 2026-10-21)

Source: the documentation review in `docs/research/freehire.md`, covering the API reference,
its OpenAPI document, the terms ("Last updated: October 19, 2026") and the Jobs API page.
Only what the documentation states is relied on.

**Endpoints used:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `https://freehire.me/api/v1/jobs/search` | the listing (open postings only) |
| `GET` | `https://freehire.me/api/v1/jobs/{public_slug}` | one job; also served after it closes, with `closed_at` |

- **`/status` is not used.** It is documented as "Ingest-fleet health, per provider", which is
  the state of Freehire's crawlers, not whether the API answers. Freehire documents no API
  health endpoint, so the healthcheck makes **no request**: it reports only whether the
  client is configured for a fixture.
- **Search parameters:**
  - `q`, `limit` (1–100) and `offset`;
  - facet filters, documented but not used by NoEfforts. NoEfforts filters locally, on what
    the source supplied.
- **Authentication:** none for documented public reads. A personal API key (Bearer) is
  documented. None is configured.
- **Rate limits:**
  - **No keyless figure is documented.** Reads are "limited per address", and the figures in
    force are reported by `GET /plans`, which NoEfforts does not call.
  - Documented: every response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
    `X-RateLimit-Reset`, and a refusal is `429` with `Retry-After`.
  - NoEfforts paces **only** from those headers: when `X-RateLimit-Remaining` reaches 0, paging
    stops and the import is marked truncated. The reason is shown, with the reset value as
    sent; its unit is not documented, so it is not interpreted.
  - NoEfforts never waits and never retries. A `429` ends the run, reports `Retry-After` and
    writes nothing. Without the headers, NoEfforts assumes no rate.
- **Pagination:** offset-based. `offset + limit <= 10000`, otherwise 400 "pagination too
  deep".
  - NoEfforts never asks beyond that window, and stops at `MAX_PAGES`.
  - It refuses a response whose `meta.offset` differs from the request, or a page identical to
    an earlier one (loop).
- **Response shape:** collections are `{"data": [...], "meta": {"total", "limit", "offset"}}`;
  single items are `{"data": {...}}`.
- **Fields read** (all documented in the API reference's job example):
  - identity and source: `public_slug`, `source`, `url`;
  - the posting: `title`, `company`, `location`, `description` (HTML), `cities[]`;
  - **`work_mode` (top level)**;
  - dates: `posted_at`, `updated_at`, `closed_at`;
  - `enrichment.employment_type` and `enrichment.visa_sponsorship` (boolean).
- **Not read, because undocumented:** `last_seen_at` and an `apply_url` on the job object.
  The `utm_source=freehire.me` suffix seen on 2026-10-19 is undocumented too; tracking
  parameters are dropped for deduplication anyway.
- **Sponsorship from enrichment** is stored with basis "provider enrichment", because how
  enrichment is produced is not documented. It is never treated as the employer's statement,
  and any value other than a boolean stays unknown.
- **Terms that apply** (quoted in `docs/research/freehire.md`):
  - no scraping beyond the documented API and no bypassing of rate limits or authentication;
  - keyless use is personal and non-commercial;
  - with a plan: attribution (a link to the freehire.me page or "via freehire.me"), no
    redistribution, and deletion within 30 days after the plan ends;
  - the postings belong to the employers.

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
- **Freshness:** the source's `updated_at` (`last_seen_at` is undocumented and not read), and
  our own first-seen, last-seen and import times.
- **Source facts:** `sponsorship_offered` as yes/no/unknown with `stated_by` and `basis`.
- **Attribution:** `{"text": "via freehire.me", "url": null}`, shown with every Freehire
  listing and on the job page. The documentation gives no listing-page URL for a job, so the
  credit is text, not a link. The local mock is credited "local mock data (not from
  freehire.me)".
- **Debugging reference:** `raw_ref` holds the provider, id, fingerprint and field names, never
  the raw payload.
- **No raw payload is kept** (tested). In particular, none of these are stored:
  - the HTML description;
  - the enrichment object;
  - counters;
  - the `reality` signals.

  The tracker job receives the plain-text summary only.

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
7. **Stale and closed records:**
   - Freehire's search returns open postings only, so a posting that has closed simply stops
     appearing. A single-record refresh (`get_job`) sees its `closed_at` and marks it "closed
     at source", keeping the link and the tracker job as they are.
   - A record no longer served at all is marked "no longer at the source".
   - For complete-listing providers only (the mock), a record absent from a complete,
     unfiltered listing is marked stale. The Freehire client is never treated as complete.
8. **Truncation:** a page limit or an exhausted rate budget stops paging. What was read is
   kept, and the result says `truncated` with the reason (`stop_reason`).

## API

| Method and path | Purpose |
|---|---|
| `GET /api/discovery/providers` | name, label, enabled, capabilities, configured flags (no values), status table |
| `POST /api/discovery/providers/{name}/healthcheck` | `{ok, detail}`; 409 when disabled. For Freehire, configuration only: no request is made |
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
- Every listing shows "via freehire.me". The job page names the discovery source with the same
  credit.

## Limitations

- **Documentation date:** the contract is from the documentation as read on 2026-10-21.
  Before any live call, re-read the docs and terms and record any changes.
- **Undocumented details:**
  - `X-RateLimit-Reset` has no documented unit;
  - `work_mode` values outside remote/hybrid/onsite stay unknown;
  - response schemas are examples only (no required or nullable fields are specified).
- **Imports run inside the request,** bounded by page count and timeout. A background job would
  be needed for larger imports.
- **Freehire listings are query-scoped, never complete,** so "missing from the listing" is never
  used to mark a Freehire record stale.
- **Not implemented** (needs a plan or written clarification from Freehire):
  - multi-user use;
  - plan-based storage;
  - deletion within 30 days after a plan ends.
