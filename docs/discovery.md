# Job discovery providers

Discovery providers only find jobs. They never submit applications, never inspect employer
forms, never bypass access restrictions and never infer application questions. A discovered
job says nothing about eligibility, sponsorship or whether NoEfforts can apply to it.

Manual job entry (`POST /api/jobs`) and CSV/XLSX import (`POST /api/jobs/import`) never depend
on a provider and keep working during a provider outage. This is tested.

## Provider status

| Provider | Implemented locally | External API configured | External API tested | Production-ready |
|---|---|---|---|---|
| `freehire`: client for Freehire's documented public read API | yes (fixture of the documented API) | **no** (possible for the owner, with a run approval, D55) | **no** | **no** |
| `freehire_mock`: local mock file | yes (invented record shape) | n/a | n/a | no (refused in production) |

Freehire: **Not yet validated against Freehire.** A live read is possible for the owner's
account only, with the owner's single-use run approval (D55, "Live read" below); none has been
made.

- **Product model:** personal prototype only (D34). Freehire's terms allow keyless use for
  "your own job search, research, or a tool you run for yourself". Showing postings to other
  people needs a Freehire API plan. Multi-user behaviour (a plan, and no longer showing
  Freehire postings when it ends) is **not implemented** and waits on a plan or written
  clarification from Freehire.
- **Live access only by approval (D55):** no request to freehire.me's API was made while
  building or testing this. The client refuses any base URL other than a local fixture origin
  or exactly `https://freehire.me`, and the latter only for an import by an account named in
  `NOEFFORTS_DISCOVERY_OWNER_EMAILS` that uses that account's run approval for the exact
  search. The owner stated on 2026-10-28 that reading postings through Freehire's documented
  API for their own job search is allowed under the rule against automated access to
  competitor APIs (D55). The terms changed three times in ten days: re-read them on the day of
  each run.

## Configuration (server-side only; everything off by default)

| Setting | Default | Meaning |
|---|---|---|
| `NOEFFORTS_DISCOVERY_PROVIDERS` | `[]` | Feature flag. A provider runs only if it is listed. |
| `NOEFFORTS_DISCOVERY_OWNER_EMAILS` | `[]` | The only accounts that may read Freehire live, each run with its own approval (D55). Empty: nobody. |
| `NOEFFORTS_FREEHIRE_BASE_URL` | empty | A fixture origin, or `https://freehire.me` for the owner's approved runs (D55). Anything else is refused. |
| `NOEFFORTS_FREEHIRE_API_KEY` | empty | Optional. Sent as `Authorization: Bearer` by the backend only. |
| `NOEFFORTS_FREEHIRE_PAGE_SIZE` / `_MAX_PAGES` | 50 / 5 | Bounded paging. |
| `NOEFFORTS_FREEHIRE_TIMEOUT_SECONDS` | 10 | Request timeout. |
| `NOEFFORTS_FREEHIRE_DAILY_REQUEST_BUDGET` | 1440 | Requests watched searches may make per UTC day, across all watches (D56). |

There is no request-rate setting. The API reference gives no keyless figure; the Jobs API
and pricing pages state 600 requests a minute per address (2026-10-26), and Freehire's code
holds a stricter mode (120/min and 2,000/day) that a configuration switch turns on. So no
figure is assumed (see "Rate limits" below).

Where the key is never exposed:

- the frontend, which only sees a "configured: yes/no" flag;
- the isolated browser, which never runs for discovery;
- API responses, logs and test output (tested).

The key lives in settings only.

## Live read (D55, owner only)

1. Re-read Freehire's terms (https://freehire.me/terms) on the day.
2. Configure the backend: `NOEFFORTS_DISCOVERY_PROVIDERS=["freehire"]`,
   `NOEFFORTS_FREEHIRE_BASE_URL=https://freehire.me`,
   `NOEFFORTS_DISCOVERY_OWNER_EMAILS=["<your login>"]`, and restart the API.
3. Approve one run (nothing is requested by this):

   ```bash
   cd backend
   uv run python -m app.modules.discovery.approve --email <your login> \
       --query "financial analyst" --pages 1 --hours 2 \
       --retention "Discovered postings are kept until I delete them."
   ```

   At most 5 pages and 24 hours. The query must match, exactly, what you type in Discover's
   search box.
4. On Discover, search for exactly that query. The import first checks the account and the
   approval, then that `freehire.me` resolves to public addresses only (`urlsafety`), then
   marks the approval used (committed) and reads at most the approved pages.
5. A second search, a different search, an expired approval, another account, a refresh of a
   record or a health check makes no request (403 or 409). A run that fails (a 429, an outage)
   has used its approval; approve again for another try. Nothing runs on its own.

## Watched searches (D56, owner only)

Freehire offers no push or webhook, so new postings are found by checking. A watch is a standing
approval for one search; the worker checks it as often as once a minute.

```bash
cd backend
uv run python -m app.modules.discovery.watch create --email <your login> \
    --query "financial analyst" --every 60 --days 30 \
    --retention "Discovered postings are kept until I delete them."
uv run python -m app.modules.discovery.watch list --email <your login>
uv run python -m app.modules.discovery.watch stop --id <watch id>
```

- The worker (`celery -A app.worker worker --beat`) must run, with the settings of "Live read"
  above. Every 10 s it checks each watch that is due: newest postings first, at most two
  requests, stopping at a posting it already has. New ones are added to your jobs, credited
  "via freehire.me".
- Timing: about a minute after a posting appears in Freehire's search. Freehire crawls the
  employers' boards on its own schedule, so it can lag the employer's own site.
- Budget: `NOEFFORTS_FREEHIRE_DAILY_REQUEST_BUDGET` (default 1,440 requests per UTC day across
  all watches; one watch at 60 s uses about that). A check that could pass it waits for the
  next UTC day. Freehire's pending strict mode would allow 2,000 a day per address.
- Failures: never retried inside a check. The next check waits the interval doubled per failure
  in a row (at most an hour), and at least a 429's Retry-After; ten in a row pause the watch.
  A watch also pauses for an account that is not an owner, or an address other than
  `https://freehire.me`.
- Discover lists your watches (with "Stop watching") and reloads every 20 s while one is
  active. `GET /api/discovery/watches`, `POST /api/discovery/watches/{id}/stop`.

## Deleting a discovered posting (D56)

"Delete" on Discover (`DELETE /api/discovery/jobs/{id}`) erases the posting's content and keeps
only its id, so no search or watch adds it again. The job it created in your tracker is deleted
too, unless you added that job yourself, another posting links to it, or it has an application;
the answer says which.

## Freehire contract (public documentation as reviewed on 2026-10-21, re-checked 2026-10-26)

Source: the documentation review in `docs/research/freehire.md`, covering the API reference,
its OpenAPI document, the terms ("Last updated: October 19, 2026") and the Jobs API page, and
its re-check of 2026-10-26 (terms dated October 26, 2026; the job operations used here are
unchanged). Only what the documentation states is relied on.

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
  - **The API reference gives no keyless figure.** Reads are "limited per address", and the
    figures in force are reported by `GET /plans`, which NoEfforts does not call. The Jobs API
    and pricing pages say 600 a minute per address (2026-10-26), but a stricter pending mode
    (120/min and 2,000/day) exists in Freehire's code, so no figure is relied on.
  - Documented: every response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
    `X-RateLimit-Reset`, and a refusal is `429` with `Retry-After`.
  - NoEfforts paces **only** from those headers: when `X-RateLimit-Remaining` reaches 0, paging
    stops and the import is marked truncated. The reason is shown, with the reset value as
    sent; its unit is not documented, so it is not interpreted (Freehire's code uses whole
    seconds, which is not relied on).
  - NoEfforts never waits and never retries. A `429` ends the run, reports `Retry-After` and
    writes nothing. Without the headers, NoEfforts assumes no rate.
  - S6 (D67): a `Retry-After` in seconds is kept per user (at most a day). Until then that
    user's imports and refreshes are refused (`429`, "Nothing was sent.") before any request
    and before a live run approval is used; nothing re-runs by itself. Other users are not
    held back.
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
  - with a plan: attribution (a link to the freehire.me page or "via freehire.me") and no
    redistribution; when the plan ends, stop showing the postings. The terms of October 26,
    2026 replaced the earlier deletion within 30 days with "you may keep what you stored for
    your own internal analysis";
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
- **Fingerprint (S6, D67):** only the documented fields NoEfforts reads (`FREEHIRE_READ` and, from
  `enrichment`, `FREEHIRE_ENRICHMENT_READ`). `reality`, counters, enrichment metadata and
  undocumented fields never make a record "changed".
- **No raw payload is kept** (tested). In particular, none of these are stored:
  - the HTML description;
  - the enrichment object;
  - counters.

  The tracker job receives the plain-text summary only.
- **Freehire's `reality` signals (D93), display-only:** its five documented fields (`class`,
  `age_days`, `repost_count`, `mass_posting_count`, `fake_freshness`) are read, each only with
  its documented type, into `source_signals`, and refreshed on every read without making a record
  "changed". Discover and the job page show them as "Freehire says: …" in its own terms. Matching,
  approval, routing and execution never read them (`test_signals_never_reach_matching_approval_routing_or_execution`).

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
| `POST /api/discovery/import` | run one import; 409 when disabled or the address is refused, 403 when a live read has no owner or no run approval for the exact search (D55), 503 on a provider failure (nothing changed) |
| `GET /api/discovery/jobs`, `GET /api/discovery/jobs/{id}` | the user's discovered records. The detail includes the application route with its reason code, grant state and evidence level: a manual handoff until a form is captured, or, without a tracker job, `source_record_incomplete` or `source_posting_closed`. Viewing a linked record records its job's route decision as the job page does (changes only) |
| `POST /api/discovery/jobs/{id}/refresh` | re-read one record (`get_job`): `unchanged`, `updated` or `gone`; fixture only: a live record is never re-read (D55); 429 while a `Retry-After` runs (D67) |
| `DELETE /api/discovery/jobs/{id}` | delete a record: content erased, id kept so it is never added again; its job too when discovery created it and nothing depends on it (D56) |
| `GET /api/discovery/watches`, `POST /api/discovery/watches/{id}/stop` | your watched searches; stop one (D56) |

All of these are user-scoped: another user's record returns 404. The job detail
(`GET /api/jobs/{id}`) lists the discovery sources of a job (`discovered_from`).

## UI

- **Discover** (`/discover`) shows:
  - the sources and their status;
  - a search form, shown only when a provider is enabled;
  - the import result: read, new, changed, unchanged, linked or new jobs, incomplete, filtered
    out, not enough data, unreadable;
  - each record's source, freshness, duplicate result, missing fields, "not enough data"
    fields, changes at the source, and its sponsorship statement with its basis;
  - "Refresh from source" on each record, which says whether it is unchanged, changed (the
    user's job is not changed) or no longer at the source (S6, D67).
- A banner says that listings are not verified and imply no eligibility, sponsorship or
  automatic application.
- Every listing shows "via freehire.me". The job page names the discovery source with the same
  credit.

## Limitations

- **Documentation date:** the contract is from the documentation as read on 2026-10-21 and
  re-checked on 2026-10-26. Before any live call, re-read the docs and terms and record any
  changes.
- **Undocumented details:**
  - `X-RateLimit-Reset` has no documented unit (whole seconds in Freehire's code, not relied
    on);
  - `work_mode` values outside remote/hybrid/onsite stay unknown;
  - response schemas are examples only (no required or nullable fields are specified).
- **Imports run inside the request,** bounded by page count and timeout (kept so in S6, D67;
  watched searches run in the background). A background job would be needed for larger
  imports.
- **Freehire listings are query-scoped, never complete,** so "missing from the listing" is never
  used to mark a Freehire record stale.
- **Not implemented** (needs a plan or written clarification from Freehire):
  - multi-user use;
  - plan-based storage;
  - no longer showing Freehire postings when a plan ends (the terms of October 26, 2026
    replaced the earlier deletion within 30 days).
- **Data quality seen in the 2026-10-26 re-check** (read from Freehire's source; S6, D67):
  - a non-empty `url` carries `utm_source=freehire.me` with a re-encoded query. The tag is
    dropped with the other `utm_*` parameters, and the ATS is identified from host and path
    only (D35). Referral codes (`referral-code`, `referral_code`) are dropped too since S6.
    Both have a test; other referral parameters a source may add are not known;
  - for aggregator sources `url` is a tracking redirect, not the employer's page, and which
    sources are aggregators is not documented. Such an address is an unknown ATS and a manual
    handoff (tested in S6);
  - a direct-apply job takes applications on Freehire and has an empty `url`; it can never be
    an execution destination (D34);
  - handled in S6: the fingerprint no longer covers `reality.age_days` or counters, which change
    daily. A record stored before S6 counts once as changed on its next read.

## Closed postings and possible duplicates (S3, D59)

A posting its source reports closed, or that is gone at its address on a refresh, is shown on its
tracker job as "source says closed", and an approval to apply waits for your "It is still open"
(the job itself is not changed). Each Discover row shows your application to its job, if any,
and whether the job looks like a role you already applied to (same employer, title and
location), for example a Freehire repost under a new slug. See `docs/job-signals.md`.
