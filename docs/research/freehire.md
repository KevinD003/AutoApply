# Freehire — research notes

Integration status (2026-10-21): `docs/discovery.md`. Built to the 2026-10-19 contract below and
tested only against a local fixture; no live call is enabled. The documentation review of
2026-10-21 (next section) supersedes the earlier notes wherever they differ; see D34.

## Documentation review, 2026-10-21 (public documentation and terms only)

**Scope and method.** Public pages only, fetched live through Firecrawl (`maxAge: 0`):

| Page | Purpose | Coverage |
|---|---|---|
| https://freehire.me/docs/api | API reference | read in full |
| https://freehire.me/api-reference.openapi.json | the reference's downloadable OpenAPI document | parts relevant to this review read; the whole text searched for the relevant terms (below) |
| https://freehire.me/terms | terms | read in full |
| https://freehire.me/jobs-api | API plans | read in full |
| https://freehire.me/pricing | consumer plans only; no API figures | read in full |

- **The OpenAPI document:** OpenAPI 3.1.0, `info.version` 1.0.0, 123 paths.
  - Checked: its description, the operations under review, its security schemes and the list
    of public GET paths.
  - Searched across the whole text: rate-limit figures and headers, `last_seen`, `first_seen`,
    `apply_url`, cache, retention, attribution, `via freehire`, robots.
  - All 36 description paragraphs also appear on the docs page, which was read in full.
- **Not requested:** any `/api/v1` endpoint (search, detail, status, plans or anything else),
  any account or authenticated page, any key.
- **Caveat:** the docs page is a rendered app. Whether its own scripts made background
  requests while Firecrawl rendered it is not known. NoEfforts sent none.

**Source dates:**

| Source | Date |
|---|---|
| Terms | "Last updated: October 19, 2026" |
| API reference | no date; OpenAPI `info.version` 1.0.0 |
| Jobs API page | no date |
| All pages | read on 2026-10-21 |

### Confirmed (documentation agrees with the 2026-10-19 notes)

| Item | Documentation says |
|---|---|
| Base URL | `https://freehire.me/api/v1` (page and OpenAPI `servers`) |
| Read auth | job, search, facet and company endpoints need no authentication and may be called cross-origin. These operations carry `security: []` in the OpenAPI document: `/jobs`, `/jobs/search`, `/agent/jobs/search`, `/jobs/facets`, `/jobs/{slug}`, `/jobs/{slug}/similar`, `/jobs/{slug}/copies`, `/jobs/{slug}/apply-form`, `/jobs/find`, `/status` and others |
| Keys | personal key as `Authorization: Bearer`. Keys are created only in the account UI (`/my/api-keys`), never through the API. Session cookie `hire_token` |
| Envelope | single item `{"data": {...}}`; collections `{"data": [...], "meta": {"total", "limit", "offset"}}`; errors `{"error": "..."}` |
| Single-job lookup | `GET /jobs/{slug}` (`public_slug`) returns `{"data": {...}}` and serves closed jobs too, with `closed_at` |
| Pagination | `limit` default 20, max 100; `offset` default 0; `offset + limit` ≤ 10000, otherwise 400 `pagination too deep` (a refusal, deliberately not a clamp) |
| `GET /jobs` | only `limit`/`offset`. Other params are ignored and listed in `meta.ignored_params` |
| `/jobs/{slug}/copies` | `limit` 1–200, default 50 |
| `/jobs/{slug}/apply-form` | 404 when no form was captured. Captured for a minority of postings |
| Search params | `q`; `q_fields` (subset of title, company, description, location); `sort` (`created_at`, `posted_at`, `view_count`, `salary_min`, `salary_max`); `order` (`asc`/`desc`, default `desc`); `limit`; `offset`; facet filters with `_mode=and` and `_exclude` |
| `/agent/jobs/search` | same filters plus `description_format` = `html` (default) / `text` / `markdown` |
| Terms: automation | "no scraping beyond our documented API (and within it, the data licence below), no attempting to bypass rate limits or authentication" |
| Operator | ILYA STRELOV TECNOLOGIA DA INFORMACAO LTDA (CNPJ 58.774.293/0001-44), Florianópolis, Brazil |

### Newly documented (not in the 2026-10-19 notes)

- **Facet and filter list** (`/jobs/search`, `/jobs/facets`):
  - facets: `collections`, `regions`, `work_mode` (remote, hybrid, onsite), `category`,
    `ai_archetype`, `seniority`, `role_type`, `skills`, `domains`, `company_type`,
    `countries`, `cities`, `metros`, `relocation`, `employment_type` (full_time, part_time,
    contract, internship, fellowship), `english_level`, `posting_language`, `reality`,
    `salary_currency`, `company_slug`, `source`, `company_size`, `education_level`,
    `salary_period`;
  - numeric and boolean: `visa_sponsorship` (true/false), `requires_clearance`,
    `salary_min`, `salary_max`, `experience_years_min`, `experience_years_max`,
    `experience_include_unspecified`, `posted_within_days` (the date the source states),
    `open_within_days` (first recorded by Freehire);
  - geography (`regions`/`countries`/`metros`/`cities`) is one OR group;
  - unknown params are ignored, listed in `meta.ignored_params` (at most 10) with
    `did_you_mean`.
- **Job object, as in the docs' `GET /jobs` example:**
  - identity and source: `public_slug`, `source`, `manually_added`, `external_id`, `url`;
  - the posting: `title`, `company`, `company_slug`, `location`, `description`;
  - geography and classification: `countries[]`, `regions[]`, **`work_mode` (top level)**,
    `skills[]`, `cities[]`, `collections[]`, `is_tech`;
  - dates: `posted_at`, `created_at`, `updated_at`, `closed_at`;
  - `enrichment`, `enriched_at`, `enrichment_version`;
  - counters: `view_count`, `applied_count`;
  - `reality{class, age_days, repost_count, mass_posting_count, fake_freshness}`.
- **Enrichment sub-fields (example):** `summary`, `seniority`, `category`, `employment_type`,
  `relocation`, `visa_sponsorship` (boolean), `experience_years_min`, `english_level`,
  `education_level`, `domains[]`, `posting_language`, `company_type`, `company_size`,
  `salary_min`, `salary_max`, `salary_currency`, `salary_period`.
  - The docs do not say how enrichment is produced.
- **Descriptions:** `/jobs/search` returns a *truncated index preview* of `description`;
  `/agent/jobs/search` returns it in full.
- **Closed postings:** excluded from lists and search; served only by the detail endpoint.
  Postings that leave their source are "closed rather than deleted" (Jobs API page).
- **`/jobs/find`:** takes query parameter `url` ("the posting's URL in the wild"). The 2026-10-19
  notes had this as unknown.
- **`/jobs/{slug}/copies`:** items carry `location`, `apply_url`, `posted_at`.
- **Rate-limit signalling:**
  - every response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
    `X-RateLimit-Reset`;
  - a refusal is `429` with `Retry-After`;
  - errors are 400, 401, 403, 404, and 503 ("search temporarily unavailable").
- **API plans** (Jobs API page; no date):
  - API: $29.00/month, 1,200 requests a minute per account, no daily cap;
  - Data: $99.00/month, 6,000 requests a minute.
  - Both: all filters and fields; keys share the account budget; a key of an account without
    a plan is "limited like no key at all".
- **A change feed with webhooks** is announced as "the next thing we are building". Not
  available.

### Contradictions with the 2026-10-19 notes (or with what NoEfforts assumed)

| Earlier statement | Documentation now |
|---|---|
| Public reads 600/min, `/agent/jobs/search` 300/min (observed in source at `ec6e65f7`). D7 called 600/min "documented" | No keyless figure is documented: reads are "limited per address", and `GET /plans` "reports the figures in force as `api_limits`". `/plans` is not listed in the OpenAPI paths. **The 600/300 figures are not confirmed by documentation**, and D7's word "documented" was wrong |
| "No explicit data licence or attribution requirement for API data found" | **The terms now have a data licence** (below). Attribution, storage, retention and redistribution are all stated |
| Terms "last updated October 16, 2026" (repo source) | The live page says "Last updated: October 19, 2026" |
| NoEfforts' client reads work mode from `enrichment.work_mode` (labelled an assumption) | `work_mode` is a **top-level** job field in the docs example. `enrichment.employment_type` and `enrichment.visa_sponsorship` are confirmed as enrichment fields |
| `/status` was used by NoEfforts' client as an API health check | It is documented as "Ingest-fleet health, per provider" (healthy, cooled or failing boards): ingest health, not API availability |

### Usage restrictions (terms, "Last updated: October 19, 2026", quoted)

- **Without a plan:** "the API is for personal and non-commercial use — your own job search,
  research, or a tool you run for yourself. Showing our postings in a product or service you
  offer to others, paid or not, needs a plan."
- **With a plan:** "you may store the data you read through our API and show it in your own
  product, including a commercial one".
- **No resale:** "You may not resell or redistribute the raw data — as a download, a dataset,
  or an API or feed whose purpose is to hand the postings on to other services."
- **Attribution:** "Every posting you show must link to its page on freehire.me or carry the
  credit 'via freehire.me'."
- **Retention:** "When the plan ends, so does this permission: stop showing the postings and
  delete what you stored within 30 days."
- **Ownership:** "The postings themselves still belong to the employers who published them,
  and these terms do not grant rights an employer or original source has not given us."
- **Accuracy:** "we don't guarantee a listing is still open, and applying is between you and
  the employer".

### Still missing (not stated in the documentation reviewed)

- **The keyless rate-limit figure.** Only `GET /plans` reports it, and calling that is out of
  scope.
- **`last_seen_at`:** not in the docs example, nowhere in the OpenAPI document. The Jobs API
  page mentions "first and last seen" lifecycle data without naming a field. (It was observed
  in the live response and the source on 2026-10-19.)
- **The `utm_source=freehire.me` suffix on `url`:** not documented. The docs example URL has
  none. It was observed live on 2026-10-19.
- **An `apply_url` on the job object:** not documented. It appears only on `/copies` items.
  The Jobs API page says the API carries "the employer's own ATS link" without naming the
  field.
- **How enrichment (including `visa_sponsorship`) is produced,** and how reliable it is.
- **Caching, and whether storage is permitted without a plan.** The licence grants storage
  "while your account holds an API plan". Nothing addresses storage under keyless personal
  use. **Not inferred.**
- **Response schemas.** The OpenAPI document gives examples only (`components.schemas` is
  empty), so required and nullable fields are not specified.

---

## Earlier notes (2026-10-19)

- Date: 2026-10-19
- Sources: https://github.com/strelov1/freehire (shallow clone at `research/src/freehire`), https://freehire.me/docs/api, https://freehire.me/api/v1/jobs?limit=1 (both fetched via Firecrawl), `web/src/routes/terms/+page.svelte` in repo.
- Labels: **observed** (read in code / live response), **documented** (freehire's docs/AGENTS.md say so), **inferred**, **unknown**.

## Identity

| Fact | Label | Source |
|---|---|---|
| Pinned commit `ec6e65f7bc165d690970e7a5b902f35bf5b49c27` (2026-10-19T16:28:40-03:00, "Export every catalogued ingest provider, including never-crawled ones (#3313)") | observed | `git log -1` |
| License: MIT, "Copyright (c) 2026 freehire contributors". Obligation: keep the copyright + permission notice in copies/substantial portions; no warranty | observed | LICENSE |
| MIT covers the **code**, not the crawled job postings (third-party employer content). README claims "pipeline and data both in the open" but no data licence file was found | observed (no data licence found) / inferred (data not MIT-licensed by freehire) | README, repo tree |
| Operator: "ILYA STRELOV TECNOLOGIA DA INFORMACAO LTDA", Florianópolis, Brazil | observed | terms page source |
| Stack: Go (`go 1.26.9`, Fiber v2), PostgreSQL+pgvector, sqlc, Meilisearch, Redis, S3, langchaingo/Bifrost/Langfuse for LLM, SvelteKit web, WXT+Svelte Chrome MV3 extension, chromedp for browser automation, `bogdanfinn/tls-client` for Chrome TLS/HTTP2 fingerprint spoofing | observed | go.mod, README, internal/ingest/sources/fingerprinthttp.go |

## 1. Job ingestion (discovery)

- **observed**: `internal/ingest/sources/` holds ~290 adapter files (581 files incl. tests), e.g. greenhouse, lever, ashby, workday, smartrecruiters, icims, adzuna, arbeitnow, hhru, djinni, jobvite, bamboohr …; workers `cmd/ingest <provider>`, `cmd/ingest-scheduler`, `cmd/harvest-*`, `cmd/tg-ingest` (Telegram) + `cmd/tg-extract` (LLM extraction).
- **documented** (README/docs/sources.md snapshot): 225 live sources, 92 ATS platforms, 3,300,615 open postings, 294,282 companies.
- **observed (live)**: `GET /api/v1/jobs?limit=1` returned `meta.total: 5712071` on 2026-10-19 (higher than the README figure).
- **observed**: `cmd/harvest-linkedin/discover.go` calls `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` to build a company worklist; `fingerprinthttp.go` spoofs Chrome JA3+HTTP/2 because some edges (Meta, Bayt/Akamai, GulfTalent/Cloudflare) reject Go's default fingerprint. Caveat: this is bot-protection evasion against third-party sites — **do not copy** into NoEfforts.
- Pipeline (documented): fetch → normalize → dedup (stable key) → upsert; soft-close lifecycle; LLM enrichment optional.

## 2. Public API (discovery source)

Base: `https://freehire.me/api/v1` (`app.Group("/api/v1")`, internal/api/handler/handler.go:916 — observed).

Public, unauthenticated reads verified **in code** (route → file):

| Method & path | Params (from code/docs) | Code |
|---|---|---|
| `GET /jobs` | `limit` (1–100, default 20), `offset`; any other param ignored and echoed in `meta.ignored_params` | jobs.go:57 |
| `GET /jobs/find` | URL lookup (param name not verified — **unknown**) | jobs.go:59 |
| `GET /jobs/:slug` | path `slug` = `public_slug`; serves closed jobs too | jobs.go:60 |
| `GET /jobs/:slug/copies` | `limit` 1–200 (docs), `offset` | jobs.go:61 |
| `GET /jobs/:slug/apply-form` | — ; 404 when no captured form | jobs.go:62, apply_form.go:25 |
| `GET /jobs/search` | `q`, `q_fields`, `sort` (`created_at`,`posted_at`,`view_count`,`salary_min`,`salary_max`), `order`, `limit`, `offset` + facet filters (`regions`,`countries`,`cities`,`work_mode`,`category`,`seniority`,`skills`,`employment_type`,`visa_sponsorship`,`salary_min`, `posted_within_days`, `open_within_days`, … with `_mode=and` / `_exclude`) | search.go:68 (params documented on freehire.me/docs/api) |
| `GET /agent/jobs/search` | same + `description_format` = `html`\|`text`\|`markdown`; full descriptions | search.go:71 |
| `GET /jobs/facets` | same filters | search.go:72 |
| `GET /jobs/:slug/similar` | `limit` | search.go:73 |

Also documented (not individually code-verified here): `GET /companies`, `/companies/{slug}`, `/geo/cities`, `/stats/*`, `/insights/*`, `/status`. Authenticated surfaces use session cookie or personal API key `Authorization: Bearer <token>` (documented).

Response shape (observed live + `internal/job/jobview/jobview.go`): `{"data":[{public_slug, source, manually_added, external_id, url (original ATS URL with `?utm_source=freehire.me` appended), title, company, company_slug, location, description (HTML), countries[], regions[], skills[], cities[], collections[], posted_at, created_at, updated_at, last_seen_at, closed_at, enrichment{...}, enriched_at, enrichment_version, view_count, applied_count, upvote_count, downvote_count, my_vote}], "meta":{"limit","offset","total"}}`. Errors `{"error": "..."}`.

Pagination: `offset + limit <= 10000` else 400 `pagination too deep` (observed in handler.go `pageParamsWindowed`; documented).

Rate limits (observed, internal/api/handler/public_read_limit.go, keyed by IP, per minute): public reads **600/min**; `/agent/jobs/search` **300/min**; suggest 1200/min; talent catalogue 120/min. Live API status: **observed live** (HTTP 200, `application/json`) on 2026-10-19.

## 3. Form recognition (capture)

- **observed**: `internal/ingest/applyform/` captures each posting's ATS application form from the platform's public JSON: Greenhouse `https://boards-api.greenhouse.io/v1/boards`, Workable `https://apply.workable.com/api/v1/jobs/%s/form`, Ashby `https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting`, Dover `https://app.dover.com/api/v1/inbound/application-portal-job/%s`, Lever (region read from stored URL), Recruitee (form arrives with the crawl).
- **observed** `Form` shape: `{provider, fields[{id, label, type (normalized FieldType), raw_type, required, section, demographic, options[{label,value}]}]}`; IDs stored verbatim (e.g. `question_67165648`).
- Public projection via `GET /jobs/:slug/apply-form` → `{"data":{"provider","basics":[...],"questions":[{"text","required","answer"?}]}}` (observed in display.go; documented example).
- **documented**: only "roughly a sixth of technical ATS platforms are readable at all"; 404→discard, 429→defer (no retry charge); defaults batch 200, concurrency 4, max 5000/run.

## 4. Submission

- **observed**: `cmd/auto-apply` + `internal/application/autoapply` (queue drain) + `internal/api/atsapply` (driver). Driver = in-process **chromedp headless Chrome** with `disable-blink-features=AutomationControlled`; fills and submits only **Greenhouse and Lever** (layouts measured), everything else parks `not implemented`. Ashby/Workable optional fallback via browser-use.com cloud API, **off by default** (`AUTO_APPLY_BROWSERUSE_ENFORCE`).
- **documented** invariants worth copying as *design rules*: submit only when every required field resolves; never guess (select answers must match platform option labels); sensitive-keyword and geography gates park; captcha-protected postings park (explicitly "not an attempt to bypass bot protection"); claim only rows with `review_decision = 'approved'` and an approved tailored CV; "never submit twice".
- Entry point: `POST /jobs/:slug/auto-apply` (cookie + paid plan), `POST /me/auto-apply/:queueId/tailor`, `/review` (observed in assistant.go:217-223).

## 5. Confirmation

- **observed** (`internal/api/atsapply/fill.go`): after the click, page text is matched against positive markers only: "thank you for applying", "application submitted", "application received", "we have received your application", "we've received your application"; refusal markers "please try again", "there was an error"; captcha-refusal markers ("could not verify", …) are the only retry-safe refusal.
- **documented**: no marker → `StatusUnconfirmed`, dead-lettered immediately (no retry, to avoid duplicate submission). browser-use path requires a strict final-line `CONFIRMED:` / `UNCONFIRMED` / `PARKED:` marker.
- Post-submit email confirmation: Gmail sync (`gmail.readonly`, internal/application/gmailsync/connector.go:23) + hosted inbox link recruiter mail to applications (observed/documented). No screenshot/DOM-evidence capture was found (not searched exhaustively — **unknown**).

## Terms / caveats

- freehire.me Terms (last updated October 16, 2026, observed in repo source): "no scraping beyond our documented API, no attempting to bypass rate limits or authentication". Using the documented API within rate limits appears permitted (**inferred**).
- No explicit data licence or attribution requirement for API data found (**unknown**); job content belongs to employers/sources. URLs carry `utm_source=freehire.me` — strip or keep consciously.
- Some upstream sources (LinkedIn guest API, fingerprint-spoofed edges, hh.ru etc.) may violate those sites' terms; consuming freehire's derived data inherits provenance risk (**inferred**).

## Reuse recommendation

1. **Use the public API as an optional discovery source** (`/jobs/search` or `/agent/jobs/search` with `description_format=markdown`), behind an adapter, throttled well below 600/min, honouring the 10k window, recording `source`/`external_id`/original `url` and applying our own freshness check against the original ATS before acting. Do not make it a hard dependency (single-operator hosted service).
2. **Reuse ideas, optionally code (MIT, with notice)**: the Greenhouse/Lever/Ashby/Workable/Dover public form-schema endpoints and `Form` model (`internal/ingest/applyform`) and the confirmation/park/dead-letter rules are directly relevant. It is Go; NoEfforts would likely port concepts rather than import.
3. **Do not reuse**: `fingerprinthttp` (TLS spoofing), LinkedIn harvesting, chromedp stealth flags, browser-use cloud fallback.
