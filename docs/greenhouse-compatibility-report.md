# Greenhouse read-only compatibility report (one real posting, anonymous)

- **What was checked:** one public posting on a Greenhouse-hosted board, chosen by the user.
  Per the approval, the employer and posting are **not named** anywhere in the repository.
- **What was done:** permissions A (job post JSON) and B (one page load in the isolated
  browser) only. No candidate data, no typing, no clicks, no uploads, no submission.
- **When and where:** 2026-10-20, read-only run #3
  ([workflow run](https://github.com/KevinD003/AutoApply/actions/runs/39432345404)) on
  `e2a8d97`.
- **Raw data:** responses and page were destroyed with the CI stack at the end of the run.
- **Scope of the conclusions:** this one posting only. Nothing below shows that submitting an
  application would work.

## A — job post JSON (3 GETs: robots.txt, job, board; all 200)

| Observation | Value | Fixture assumption | Verdict |
|---|---|---|---|
| Posting identity | job id matches; company name matches the board; `absolute_url` present | same fields | **matches** |
| Questions | 16 questions + 3 location questions | similar shape | matches |
| Field types | `input_text` 11, `multi_value_single_select` 7, `input_file` 2, `textarea` 2, `input_hidden` 2 | all five types are in the fixture | **matches**: no unknown types |
| Standard fields | `first_name`, `last_name`, `preferred_name` (required), `email`, `phone`, `resume` + `resume_text` (one required question, two alternatives), `cover_letter` + `cover_letter_text` (optional) | fixture has these except `preferred_name` | close; `preferred_name` **required** here |
| Selects | option counts 2, 2, 250, 26, 2, 2, 2 | fixture uses short lists | matches the type; long lists not exercised |
| Location | `location` (text, required) plus `latitude` and `longitude` (`input_hidden`, required) | the fixture's location job has the same | **matches**; our policy makes this posting a **checkpoint** (required hidden coordinates cannot be filled) |
| Data compliance | one `gdpr` entry, `requires_consent: false` | fixture job 4012001 requires consent | differs (no consent checkbox expected here) |
| Demographic questions | key present, empty | not modelled | not exercised |
| Extra top-level keys | `ai_disclaimer`, `include_ai_disclaimer`, `ai_opt_out_request_url`, `application_deadline`, `compliance`, `departments`, `offices`, `metadata`, `language`, `first_published`, `updated_at`, `internal_job_id` | not in the fixture | **new**: an AI-use disclaimer/opt-out and a deadline exist in the data; their UI was not examined |
| Mapping by `schema_from_api` | 22 fields, 19 required; unsupported: `latitude`, `longitude` | — | mapping code handles every type |

## B — rendered page (one load, observe only)

| Observation | Value | Fixture assumption | Verdict |
|---|---|---|---|
| Load | HTTP 200; 9 requests; no non-GET request attempted; no bot check present at load; no iframes | — | page readable |
| Other destinations | 2 requests to other `greenhouse.io` hosts were denied by the allow-list (only `job-boards.greenhouse.io` was allowed); the form rendered anyway | — | effect of those 2 requests **unknown** |
| Form element | 1 `<form>`; 0 controls outside it | one form | matches |
| Control naming | **0** controls with a `name` attribute; **24** with an `id` only | every control has `name` = API field name | **differs**: the cause of the extraction failure |
| Selects | **0** native `<select>`; **12** ARIA `role=combobox` widgets | native `<select>` | **differs** |
| Inputs | 30 text, 1 tel, 2 file; 0 textareas visible at load | text, email, tel, file, textarea, checkbox | differs: the textarea alternatives are not visible at load (probably behind a toggle; not confirmed) |
| Labels / buttons | 26 labels, 21 buttons | label `for` + one submit | not compared in detail |
| Extraction | `ExtractionError`: our extractor found no named fields | — | **not compatible** with the current extractor |

## Conclusions

- **Confirmed:**
  - the job post JSON shape and field types match what the adapter maps;
  - the posting's identity checks out;
  - the page loads in the isolated browser without a bot check, and sends nothing on load;
  - the required hidden coordinates make this posting a manual checkpoint under our rules.
- **Differences from the fixture:**
  - the rendered form uses id-only controls and ARIA comboboxes instead of named controls and
    native selects;
  - `preferred_name` is required;
  - no consent checkbox (`requires_consent: false`);
  - AI-disclaimer and deadline fields exist.
- **Consequence:**
  - the current Greenhouse adapter would **refuse** this posting at capture time (schema could
    not be built), i.e. it fails closed;
  - it is **not compatible** with this real page as built;
  - the posting would be a checkpoint anyway because of the hidden coordinates.
- **Unknown:**
  - whether control ids equal the API field names;
  - how comboboxes take values;
  - whether textarea alternatives appear on demand;
  - the upload mechanism, the submit endpoint, any security-code step, the confirmation page;
  - conditional questions (only the state at load was seen);
  - what the 2 denied `greenhouse.io` requests were for;
  - how the AI disclaimer is shown.

## Proposed next steps (none done yet)

1. **One more read-only run** (same approval) that records, per API field, whether a control
   with `id` equal to the field name exists, its tag, its `role` and whether it is labelled.
   Booleans only, so it stays anonymous. That would tell whether id-based matching is
   possible.
2. **A second fixture variant** (`hosted-v2`) with id-only controls and ARIA comboboxes. The
   extractor and adapter would be changed and tested against it, with fail-closed behaviour
   kept for anything unmatched.
3. Until then, real Greenhouse destinations stay refused for execution, as they are now.
