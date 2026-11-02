# Greenhouse application fields — the official catalogue

Source: the official Greenhouse Job Board API docs (`github.com/grnhse/greenhouse-api-docs`,
`source/includes/job-board/`, read 2026-11-02). This records every field the documented
application form can contain, so our DOM filler (Playwright/Chromium) is checked against the
authoritative list. We hold **no** API key and submit through the browser only (D102/D116,
D119); the API is read-only here, as the field source.

A job post's fields are read live from `GET /boards/{token}/jobs/{id}?questions=true`
(`greenhouse.schema_from_api`). This table is the reference the capture is checked against.

## Standard fields (always by these exact names)

| Field | HTML name | Our handling |
|---|---|---|
| First name | `first_name` | text — profile fact |
| Last name | `last_name` | text — profile fact |
| Email | `email` | email — profile fact |
| Phone | `phone` | tel — profile fact |
| Location | `location` | search picker (D104 stand-in; real = checkpoint) |
| Latitude / Longitude | `latitude`, `longitude` | `input_hidden`: set by the page, never typed (checkpoint) |
| Country | `country_short_name` | from the approved location, exact code |
| Resume | `resume` | file upload, confirmed by filename (D116) |
| Cover letter | `cover_letter` | file upload |
| Referral source token | `mapped_url_token` | not applicant data; the `gh_src` token only |

## Custom questions (`question_<id>`)

| Documented type | POST shape | Our control | Status |
|---|---|---|---|
| short text | `question_1: "text"` | text | filled |
| long text | `textarea` | textarea | filled |
| single select (**dropdown**) | `question_2: <value>` | select, exact option | filled |
| multi select | `question_3: [<v>,<v>]` (`question_3[]`) | checkbox group | filled |
| attachment (file) | `resume`/`question_file` | file | filled |
| attachment by URL | `question_N_url` + `_url_filename` | — | **not yet** (we upload a file, not a URL) |
| attachment by content | `question_N_content` (base64) + `_content_filename` | — | **not yet** |

## Education section (`educations[][...]`) — the dropdowns

| Field | POST shape | Populated from |
|---|---|---|
| School | `educations[][school_name_id]` | `GET /boards/{token}/education/schools` (id + text) |
| Degree | `educations[][degree_id]` | `GET .../education/degrees` (High School, Associate's, Bachelor's, Master's, M.B.A., J.D., M.D., Ph.D., Engineer's, Other) |
| Discipline | `educations[][discipline_id]` | `GET .../education/disciplines` |
| Start / End | `educations[][start_date][month|year]`, `[end_date][...]` | month + year |

These are **ID-based dropdowns**, not free text: the hosted form shows degree/discipline as
selects whose option values are those ids. Degree and discipline are a fixed, non-sensitive
vocabulary — mappable from the applicant's approved education record by an exact/alias table
(as countries and states already are). School is a large search list and stays a checkpoint
(never fuzzy-matched). **Status: not yet extracted; today the whole section is an unlisted
control the adapter stops on (a checkpoint).**

## Employment section (`employments[][...]`)

`company_name`, `title`, `start_date[month|year]`, `end_date[month|year]`, `current` (bool).
Filled from the applicant's approved employment records. **Status: not yet extracted
(checkpoint).**

## EEOC / demographic (`demographic_answers[][...]`)

`question_id`, `answer_options[][answer_option_id]`, optional `[text]` (free-form). Also the
government-contractor `compliance` section (gender, race, veteran, disability). **Never
auto-filled**: demographics and legal attestations are never inferred (a non-negotiable rule).
Each is the applicant's own explicit per-application choice, never saved for reuse. Surfaced as
a question to answer, not a default.

## Consent (`data_compliance[...]`)

`gdpr_consent_given` (deprecated), `gdpr_processing_consent_given`,
`gdpr_retention_consent_given`, `gdpr_demographic_data_consent_given`. The job data's
`data_compliance[].requires_consent` drives whether a consent checkbox is required; its wording
is taken from the page. The applicant's own choice (C3), never auto-ticked (U8).

## What this confirms vs. what remains

- **Confirmed filled:** every standard field and every custom-question field type, including
  single-select and multi-select **dropdowns**, with exact options from the API
  (`tests/test_greenhouse_api_coverage.py`).
- **Remaining (D120, scoped, not built):** the structured **education and employment** sections
  (the degree/discipline dropdowns map from the degrees/disciplines endpoints and the
  applicant's approved records; school stays a checkpoint), and the attachment-by-URL /
  attachment-by-content question variants.
- **By rule, not auto-filled:** EEOC/demographic answers and consent — the applicant's explicit
  choice.
