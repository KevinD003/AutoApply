# Freehire — research notes

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
