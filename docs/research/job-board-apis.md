# Public job-board posting APIs: Greenhouse, Lever, Ashby (2026-10-30)

Scope: bounded, read-only reading of each vendor's public developer documentation, to build
read-only connectors for an employer's **published postings** (D95). No board, posting, API
endpoint, careers site, sign-in or form of any employer was requested; no account was used.
Example boards and companies named inside the documentation are **not** repeated here.

## Labels used

- **documented**: read in a page I opened, with its URL.
- **inferred**: my reasoning from documented facts; says what it rests on.
- **not documented**: looked for in the pages read and not found.
- **unverified**: not read in any official page (search results, memory); never built on.

## Sources read

| URL | Date (UTC) | Result |
|---|---|---|
| https://developers.greenhouse.io/job-board.html | 2026-10-30 | **inaccessible**: DNS failure (`ENOTFOUND`), the session's network allowlist |
| https://github.com/grnhse/greenhouse-api-docs | 2026-10-30 | accessible: Greenhouse's official repository of the source of developers.greenhouse.io (the rendered page links to it as its `github_link`) |
| https://raw.githubusercontent.com/grnhse/greenhouse-api-docs/master/source/job-board.html.md | 2026-10-30 | accessible: the Job Board API page's index (its includes: introduction, jobs, offices, departments, sections, educations, boards, applications) |
| `.../source/includes/job-board/_introduction.md`, `_jobs.md`, `_boards.md`, `_applications.md` (same base) | 2026-10-30 | accessible, read in full |
| `.../source/includes/harvest/_introduction.md` (same base) | 2026-10-30 | accessible; read for the authentication and rate-limit sections only |
| https://raw.githubusercontent.com/lever/postings-api/master/README.md | 2026-10-30 | accessible, read in full (25,813 bytes; also read on 2026-10-29, `docs/research/lever.md`) |
| https://developers.ashbyhq.com/ | 2026-10-30 | **inaccessible**: DNS failure (`ENOTFOUND`), as on 2026-10-29 (`docs/research/ashby.md`) |

The Greenhouse pages were read from the repository source rather than the rendered site. They
are the same text Greenhouse publishes; whether the rendered site has changed since the
repository's last commit was not checked.

## Public postings versus everything else

| Vendor | Public, unauthenticated, read-only (used) | Needs employer credentials or acts as a candidate (never used) |
|---|---|---|
| Greenhouse | **documented**: "Job Board data is publicly available, so authentication is not required for any GET endpoints." `GET /v1/boards/{board_token}/jobs` lists a board's published job posts | **documented**: the application `POST https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{id}` requires Basic Auth with the employer's Job Board API key; Harvest (the employer's management API) requires the employer's credentials |
| Lever | **documented**: the Postings API lists "published job postings"; `GET /v0/postings/SITE?skip=X&limit=Y`; "not available via unencrypted HTTP" | **documented**: the apply `POST /v0/postings/SITE/POSTING-ID` "need[s] an API key" that a Super Admin generates; the Data API (OAuth, `docs/research/lever.md`) is the employer's |
| Ashby | **unverified**: search results describe a public job posting API; no page could be opened | **unverified** |

A connector that only reads public postings needs no employer credential, and none is accepted
or stored.

## Greenhouse Job Board API: what the connector uses (documented)

- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`.
  `board_token` is the "Job Board URL token"; `content=true` "include[s] the full post
  description, department, and office of each job post".
- **Response:** `{"jobs": [ ... ], "meta": {"total": n}}`. Each job: `id` (the job post; "the
  unique identifier for the job post"), `internal_job_id` (the job; null for prospect posts),
  `title`, `updated_at`, `requisition_id`, `location.name`, `absolute_url`, `language`,
  `metadata` (custom fields the employer chose to expose), and with `content=true`: `content`
  (HTML, entity-encoded: the example shows `&lt;p&gt;`), `departments`, `offices`.
- **Not documented:** paging for this list (none is described; one response is the list), a
  status code for an unknown board, rate limits for the Job Board API (Harvest documents `429`
  with `Retry-After`; the Job Board pages say nothing), a posting date on the list (the single
  job adds `first_published`; the connector does not request single jobs).
- **Inferred, and how the connector uses it:** `meta.total` is the number of published posts, so
  a read is **complete** only when `meta.total` equals the number of jobs received; otherwise
  nothing is concluded about postings that are missing. A `404` is read as "no public board by
  that name" (not documented; nothing else is concluded from it). A `429` is honoured with its
  `Retry-After` if one comes (defensive: documented for Harvest only).

## Lever Postings API: what the connector uses (documented)

- **Request:** `GET https://api.lever.co/v0/postings/{site}?mode=json&skip=X&limit=Y`; the EU
  instance is `api.eu.lever.co`. "All URL parameters must be properly URL encoded." `mode=json`
  has precedence over the `Accept` header.
- **Response:** a JSON list of postings: `id`, `text` (the posting name), `categories`
  (`location`, `commitment`, `team`, `department`, `allLocations`), `country`, `opening` /
  `openingPlain`, `description` / `descriptionPlain`, `descriptionBody` /
  `descriptionBodyPlain`, `lists`, `additional` / `additionalPlain`, `hostedUrl`, `applyUrl`,
  `workplaceType` (`unspecified`, `on-site`, `remote`, `hybrid`), optional `salaryRange`,
  `salaryDescription` / `salaryDescriptionPlain`.
- **Not documented:** a total count, a posting date or update time, the order of results, a
  status code for an unknown site, rate limits for reading (the only documented limit is for
  application POSTs: more than 2 a second gets `429`).
- **Inferred, and how the connector uses it:** with `skip`/`limit` paging and no total, a read is
  **complete** only when a page comes back shorter than the page size; if the page limit stops
  it first, the read is incomplete and closes nothing. Salary fields are not read (a pay range
  is the employer's statement, kept out until there is a design for it).

## Ashby: not built

`developers.ashbyhq.com` could not be opened (DNS, the session's allowlist) on 2026-10-29 and
again on 2026-10-30. Search results name a public job posting API, but a search snippet is not
documentation: no endpoint, schema, paging or completeness rule could be confirmed, so no Ashby
connector is built. The app says so where boards are added. Remedy: add `developers.ashbyhq.com`
(and `docs.ashbyhq.com`) to the environment's allowed domains; then read the pages and build it
the same way.

## What was verified against a real board

Nothing. Every request in the tests went to a local stand-in of the documented shapes
(`fixtures/ats_receiver/board_feeds.py`, fictional boards and postings) whose own ledger records
each request. No real Greenhouse or Lever board has been read by this code.
