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
| Degree | `educations[][degree_id]` | `GET .../education/degrees` — exact texts (verified 2026-11-03): "High School", "Associate's Degree", "Bachelor's Degree", "Master's Degree", "Master of Business Administration (M.B.A.)", "Juris Doctor (J.D.)", "Doctor of Medicine (M.D.)", "Doctor of Philosophy (Ph.D.)", "Engineer's Degree", "Other". Ids are per-organization — match by text, never by id. |
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

## Full-repo review (all 8 API sections), 2026-11-02

Went through every section of `grnhse/greenhouse-api-docs` (assessment, audit-log,
candidate-ingestion, gho, harvest, job-board, onboarding_webhooks, webhooks) and `schemas/`.
**Only the Job Board API has public, keyless GET endpoints** (its own introduction: "Job Board
data is publicly available, so authentication is not required for any GET endpoints"). Every
other section needs an employer/partner API key, OAuth token, or an employer-registered webhook
receiver, so none is callable by a keyless browser filler. They are useful only as the
authoritative value-set dictionary below.

### The operational caveat that matters most

`job-board/_applications.md`: **Greenhouse does not server-validate required fields on submit.**
A form missing a required answer is not rejected by Greenhouse's own API — the page's client
checks, or ours, must enforce it. This confirms our design: `execution.gate_before_send` sends
only a fully resolved package, and the adapter re-checks every page-required field before the
final click (`greenhouse_dom.schema_matches`, "required by the page, no approved answer"). That
enforcement is load-bearing, not belt-and-braces.

### Authoritative value-sets (reference; we read the live set from the job endpoint at fill time)

- **Field-type enum** (`job-board/_jobs.md`): `input_text`, `input_hidden`, `textarea`,
  `input_file`, `multi_value_single_select` (radios/select — a dropdown),
  `multi_value_multi_select` (checkboxes/multiselect). All mapped (D119).
- **EEOC exact option labels** (`harvest/_eeoc.md`), which render on the form; in the Job Board
  submit body they are integer ids `gender`, `race`, `veteran_status`, `disability_status`:
  - Race: American Indian or Alaskan Native; Asian; Black or African American; Hispanic or
    Latino; White; Native Hawaiian or Other Pacific Islander; Two or More Races; Decline To Self
    Identify.
  - Gender: Male; Female; Decline To Self Identify.
  - Veteran: I am not a protected veteran; I identify as one or more of the classifications of a
    protected veteran; I don't wish to answer.
  - Disability: Yes, I have a disability (or history/record); No, I don't have a disability (or
    history/record); I don't wish to answer.
  - **Not auto-filled** (a non-negotiable rule). Our decline option matching
    (`resolver.py`: "decline to self-identify", "i don't wish to answer") lines up with the two
    decline labels, so a user who declines maps to the right option.
- **Demographic questions** (`harvest/_demographic_data.md`): org-custom (Greenhouse Inclusion),
  `multi_value_single_select` / `multi_value_multi_select`, answer options may be
  `free_form: true`; always optional; the applicant's explicit choice.
- **Custom-field value types** (`harvest/_custom_fields.md`): `short_text, long_text, yes_no,
  single_select, multi_select, currency, currency_range, number, number_range, date, url, user`.
  The Job Board API renders these to the six field types above, so no new control type reaches
  us; a range or currency question arrives as text/select and is handled or becomes a checkpoint.
- **Education** (`job-board/_educations.md`, `_degrees.md`): `/education/degrees`,
  `/education/disciplines`, `/education/schools`, each `{id, text}`, `?term=` search, 100/page.
  Degrees (exact texts, verified 2026-11-03): "High School", "Associate's Degree", "Bachelor's
  Degree", "Master's Degree", "Master of Business Administration (M.B.A.)", "Juris Doctor (J.D.)",
  "Doctor of Medicine (M.D.)", "Doctor of Philosophy (Ph.D.)", "Engineer's Degree", "Other"; ids
  are per-organization, so match by text. **Dates are month+year integers**
  (`educations[][start_date][month|year]`), start before end. Employment (`employments[]`):
  `company_name`, `title`, `start_date` {month,year}, `current` ("true"/"false"), and `end_date`
  {month,year} only when `current` is false. → D120 resolution layer built
  (`app/modules/preparation/structured_sections.py`); the rendered hosted-form DOM and live
  package wiring remain the isolated gaps.
- **Location**: free-text `location` + hidden `latitude`/`longitude` + `country_short_name`
  (ISO-2); `location` is ignored unless lat+long are also sent (a Google Places flow). Matches
  our D104 design (search picker; coordinates set by the page; country from the approved
  location).
- **Consent field names**: `data_compliance[gdpr_consent_given]` (deprecated),
  `gdpr_processing_consent_given`, `gdpr_retention_consent_given`,
  `gdpr_demographic_data_consent_given`; checkbox value `1`/`true`. Driven by the job data's
  `data_compliance[].requires_consent`; the applicant's choice.
- **Attachments**: pdf, doc, docx, txt, rtf; size > 0. Matches our `_FILE_ACCEPT`.

### Outcome vocabulary (reference only; we cannot receive employer webhooks)

`application.status` across the API is `rejected | active | hired`. Recruiting webhook actions
(`webhooks/_application_events.md`, `_candidate_events.md`): `reject_candidate`,
`hire_candidate`, `candidate_stage_change`, `new_candidate_application`, etc.; rejection carries
`rejection_reason{id,name,type}`. We cannot subscribe (the employer must register a receiver), so
our outcome model stays user-reported plus the inbox email proposals (D53, D101) — this vocab is
a cross-check for those, nothing to call.

### Net

The only keyless, candidate-usable surface is the Job Board GET endpoints, which we already use
(`GET .../jobs/{id}?questions=true` for the per-job form schema, plus the education lookups for
D120). Everything else is employer-credentialed and is treated as reference, never called.
