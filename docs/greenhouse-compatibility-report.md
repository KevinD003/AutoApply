# Greenhouse read-only compatibility report (one real posting, anonymous)

- **Scope:** one public posting on a Greenhouse-hosted board, chosen by the user.
  - Per the approval, the employer and posting are **not named** anywhere in the repository.
  - Everything below describes **this one posting at load time**. None of it is a claim about
    Greenhouse in general, and none of it shows that filling or submitting would work.
- **What was done:** permission A (job post JSON, 3 GETs) and permission B (one page load in
  the isolated browser, observe only).
  - No candidate data, typing, clicks, focus, uploads or submission.
- **Tested revision and run:** `e2a8d97`, manual workflow "Greenhouse read-only check" run #3
  ([39432345404](https://github.com/KevinD003/AutoApply/actions/runs/39432345404)), 2026-10-20.
  - The workflow completed successfully (exit 0).
  - Runs #1 (secret not set, no request sent) and #2 (A completed; B stopped on the extraction
    error and the code dropped A's summary, fixed in `e2a8d97`) are listed in the proposal's
    runs table.
- **Raw data:** the responses and the page were destroyed with the CI stack at the end of the
  run.

## Result by stage

| Stage | Result | Evidence |
|---|---|---|
| API retrieval (A) | **succeeded** | robots.txt, job post and board: 3 GETs, all HTTP 200; identity checks passed |
| Page observation (B) | **succeeded** | HTTP 200, 9 requests, no bot check, no non-GET request attempted, DOM counts collected |
| DOM extraction by the current extractor | **failed** | `ExtractionError`: the extractor needs `name` attributes and the page's controls have none |
| Mapping API fields to page controls | **not observed** | run #3 collected counts, not per-field correspondence (see "Follow-up") |
| Filling, uploads, submission, confirmation | **untested** | not authorized; never attempted |

## What the page load sent

- **To `job-boards.greenhouse.io`:** 9 GET requests from the isolated browser, i.e. ordinary
  page loading.
  - These carry normal network metadata: the GitHub runner's IP address, the headless
    browser's User-Agent and standard request headers.
  - No cookies from before the run, no candidate data, no form fields and no form submission.
  - No non-GET request was attempted (none was blocked either).
- **To the 2 denied hosts:** nothing.
  - Both are other `greenhouse.io` hosts. Our egress proxy refused them by allow-list before
    resolving or connecting, so the hosts were not contacted.
  - Their purpose is **unknown**. It is not inferred from the hostname.
- **Rendering may have been incomplete.**
  - A form with 24 controls was present after load, but the 2 denied requests may have carried
    something the page needed.
  - Run #3 did not record their resource type, so whether parts of the page were missing is
    unknown.

## A — job post JSON (3 GETs: robots.txt, job, board; all 200)

| Observation | Value | Fixture assumption | Verdict |
|---|---|---|---|
| Posting identity | job id matches; company name matches the board; `absolute_url` present | same fields | **matches** |
| Questions | 16 questions + 3 location questions | similar shape | matches |
| Field types | `input_text` 11, `multi_value_single_select` 7, `input_file` 2, `textarea` 2, `input_hidden` 2 | all five types are in the fixture | **matches**: no unknown types |
| Standard fields | `first_name`, `last_name`, `preferred_name` (required), `email`, `phone`, `resume` + `resume_text` (one required question, two alternatives), `cover_letter` + `cover_letter_text` (optional) | first fixture has these except `preferred_name` | close; `preferred_name` **required** here |
| Selects | option counts 2, 2, 250, 26, 2, 2, 2 | fixture uses short lists | matches the type; long lists not exercised |
| Location | `location` (text, required) plus `latitude` and `longitude` (`input_hidden`, required) | the fixture's location job has the same | **matches**; under our rules this makes the posting a **checkpoint** (required hidden coordinates are never filled) |
| Data compliance | one `gdpr` entry, `requires_consent: false` | first fixture job requires consent | differs (no consent checkbox expected here) |
| Demographic questions | key present, empty | not modelled | not exercised |
| Extra top-level keys | `ai_disclaimer`, `include_ai_disclaimer`, `ai_opt_out_request_url`, `application_deadline`, `compliance`, `departments`, `offices`, `metadata`, `language`, `first_published`, `updated_at`, `internal_job_id` | not in the first fixture | **new**: an AI-use notice/opt-out and a deadline exist in the data; their UI was not examined |
| Mapping by `schema_from_api` | 22 fields, 19 required; unsupported: `latitude`, `longitude` | — | the mapping code handles every type |

## B — rendered page (one load, observe only)

| Observation | Value | Fixture assumption | Verdict |
|---|---|---|---|
| Load | HTTP 200; 9 requests; no bot check present at load; no iframes | — | page readable |
| Other destinations | 2 requests to other `greenhouse.io` hosts denied by the allow-list | — | effect **unknown** (see above) |
| Form element | 1 `<form>`; 0 controls outside it | one form | matches |
| Control naming | **0** controls with a `name` attribute; **24** with an `id` only | every control has `name` = API field name | **differs**: the cause of the extraction failure |
| Selects | **0** native `<select>`; **12** ARIA `role=combobox` widgets | native `<select>` | **differs** |
| Inputs | 30 text, 1 tel, 2 file; 0 textareas visible at load | text, email, tel, file, textarea, checkbox | differs: textarea alternatives not visible at load (a toggle is likely but not confirmed) |
| Labels / buttons | 26 labels, 21 buttons | label `for` + one submit | not compared per field |
| Extraction | `ExtractionError`: no named fields | — | **not compatible** with the original extractor |

## Conclusions for this posting

- **Confirmed:**
  - the job post JSON shape and field types match what the API mapping handles;
  - the posting's identity checks out;
  - the page loads in the isolated browser without a bot check and attempts no non-GET request
    at load;
  - the required hidden coordinates make this posting a manual checkpoint under our rules.
- **Differences from the first fixture:**
  - id-only controls and ARIA comboboxes instead of named controls and native selects;
  - `preferred_name` is required;
  - no consent checkbox (`requires_consent: false`);
  - AI-notice and deadline fields exist.
- **Consequence:**
  - the original adapter **refuses** this posting at capture (fails closed);
  - the posting would be a checkpoint anyway because of the hidden coordinates.
- **Unknown:**
  - whether control ids equal the API field names, and whether labels correspond;
  - how comboboxes take values and whether their options are in the DOM before opening;
  - whether the textarea alternatives appear on demand;
  - the upload mechanism, the submit endpoint, any security-code step, the confirmation;
  - conditional questions (only the state at load was seen);
  - what the 2 denied requests were for, and whether the page rendered completely;
  - how the AI notice is shown.

## Log cleanup (prepared; nothing deleted, awaiting the user's decision)

Manual "Greenhouse read-only check" runs. None has artifacts: the workflow uploads none and
the API lists 0 for each.

| Run | Id | Revision | Result | Posting-related identifiers in the log |
|---|---|---|---|---|
| #1 | 39430360802 | `fd9b03d` | stopped: secret not set; no request sent | none expected (nothing fetched) |
| #2 | 39430833585 | `fd9b03d` | A completed; B stopped with an extraction error; only a fixed stop line was printed | none found in its printed output. The rest is build and container start-up output. Not scanned line by line |
| #3 | 39432345404 | `e2a8d97` | completed | **yes:** job `check` (118660349161), step 4 "Read-only check (anonymous summary only)". The printed summary lists the posting's custom question field names, which carry the posting's numeric question ids. No names, labels, wording or URLs |

- **Proposed:**
  - delete the **logs** of run #3 (Actions → run → "Delete all logs"); keep the run record
    itself;
  - optionally do the same for run #2, as a precaution.
- **Afterwards:** the runs keep their metadata (number, revision, date, conclusion).
- **The sanitized outcome** (this report) is kept in the repository with the tested revision
  (`e2a8d97`) and run number.
- Nothing is deleted until the user authorizes these specific logs.
- **Since `835c34a`** the CLI prints custom question ids only as aliases, and suppresses any
  output that fails its privacy check.

## What was built from this result (local only)

- **Second local fixture**, `fixtures/ats_receiver/greenhouse_v2.py`.
  - It models the structure observed above: id-only controls, ARIA comboboxes, a required
    preferred name, an AI notice that is not consent, compound attachment fields, a hidden
    conditional question and a location search picker with hidden coordinates.
  - Widget behaviour there (combobox opening and selection, upload reporting, JSON submission,
    confirmation, condition triggers, option values) is a labelled **fixture assumption**.
- **Evidence-based mapper**, `app/modules/preparation/greenhouse_dom.py`. A field is mapped only
  when all of these hold:
  - exactly one control has `id` equal to the field name;
  - its element or role suits the field type;
  - its accessible name equals the label.
  Anything else (absent, ambiguous, type or label mismatch) refuses the form.
- **Adapter `greenhouse_dom`**, fixture-only with `real_destinations: false`. Real Greenhouse
  destinations stay refused for filling and submission.
- None of this was run against the real page. **Mapping on the real page is unproven** until
  the follow-up observation (below) is approved and run.

## Follow-up (needs a new approval; not run)

- One more read-only observation, collecting per-field mapping evidence, is described with its
  enforced limits and approval text in `docs/greenhouse-readonly-compatibility-proposal.md`
  ("Follow-up observation B2").
- The original approval was single-use and is exhausted; it does **not** cover this run.
