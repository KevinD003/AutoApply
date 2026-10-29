# Ashby: public-documentation research (2026-10-29)

Scope: bounded, read-only reading of Ashby's public vendor documentation. No `jobs.ashbyhq.com`
board, `api.ashbyhq.com` call, employer careers site, sign-in or form submission was made. Example
boards named in search results were **not** visited (and are not named here).

**Headline: no Ashby documentation page could be opened from this session.**
`developers.ashbyhq.com` fails DNS resolution (outside the session's network allowlist). Ashby's
GitHub organisation has no documentation. Everything below is **search-reported**, **inferred** or
**unknown**. It is not enough to record `public_doc_reviewed` for Ashby.

## Labels used

- **documented**: read by me in a page I opened, with its URL. (No Ashby fact qualifies.)
- **search-reported**: a web-search summary attributes this to the URL given; the page was not
  opened. A lead to confirm, not evidence.
- **inferred**: my reasoning from the above; says what it rests on.
- **unknown**: nothing found.

## Sources read

| URL | Date (UTC) | Result |
|---|---|---|
| https://developers.ashbyhq.com/ | 2026-10-29 ~15:24 | **inaccessible**: `getaddrinfo ENOTFOUND developers.ashbyhq.com` (host outside this session's network allowlist; not a vendor block) |
| https://github.com/ashbyhq | 2026-10-29 | accessible; 4 repos (forks of libpg-query-node, libpg_query, sentry-action-release; `vigilant-waffle`), none about job boards or APIs |

Not attempted (after four vendor-doc hosts failed DNS, the tool guidance was to stop trying more
hosts): https://docs.ashbyhq.com/ (knowledge base), https://www.ashbyhq.com/resources/terms.

Search-result URLs used for **search-reported** facts (pages not opened):

- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://developers.ashbyhq.com/docs/creating-a-custom-careers-page
- https://developers.ashbyhq.com/reference/applicationformsubmit
- https://developers.ashbyhq.com/reference/jobpostinginfo
- https://developers.ashbyhq.com/reference/jobpostinglist
- https://developers.ashbyhq.com/reference/surveysubmissioncreate
- https://developers.ashbyhq.com/reference/surveysubmitwebhook
- https://developers.ashbyhq.com/reference/authentication, https://developers.ashbyhq.com/docs/introduction
- https://docs.ashbyhq.com/how-do-i-generate-an-api-key
- https://docs.ashbyhq.com/application-forms
- https://docs.ashbyhq.com/candidate-files-and-file-categories
- https://docs.ashbyhq.com/job-board-application-spam-protection
- https://docs.ashbyhq.com/job-board-configuring-your-setup
- https://docs.ashbyhq.com/embedding-ashby-job-boards-in-an-external-careers-page
- https://docs.ashbyhq.com/routes-for-integrating-your-ashby-job-board-with-your-careers-page
- https://docs.ashbyhq.com/application-requests, https://docs.ashbyhq.com/application-limits
- https://docs.ashbyhq.com/candidate-profile, https://docs.ashbyhq.com/candidate-profile-candidate-feed
- https://docs.ashbyhq.com/job-board-cookie-consent-settings
- https://www.ashbyhq.com/resources/terms

## 1. Public, unauthenticated job/posting API

- **search-reported** (public-job-posting-api) `GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation={true/false}`.
  The board name is the slug in the hosted board URL.
- **search-reported** Response fields: `apiVersion` (currently "1"), `jobs[]` with `title`,
  `location`, `secondaryLocations` (name plus address), `department`, `team`, `isListed`, `isRemote`
  (true for Remote and Hybrid; use `workplaceType` to tell them apart), `workplaceType`,
  `employmentType` (`FullTime`, `PartTime`, `Intern`, `Contract`, `Temporary`), `publishedAt`
  ("when the job was last published"), `descriptionHtml`, `descriptionPlain`, `address`, `jobUrl`,
  `applyUrl`, and with `includeCompensation` the compensation summaries
  (`compensationTierSummary`, `scrapeableCompensationSalarySummary`, `compensationTiers`,
  `summaryComponents`). The docs' table and example disagree on where compensation sits.
- **search-reported** `isListed: false` postings are reachable only by direct link; "Unlisted job
  postings should not be displayed publicly."
- **search-reported** For a fully custom page using only this API, applicants are still sent to the
  hosted board to apply.
- **inferred** The public API does not include the application form; the form definition
  (`applicationFormDefinition`) comes from the authenticated `jobPosting.info`.
- **unknown** Pagination (the endpoint appears to return the whole board) and any rate limit on the
  public endpoint.

## 2. Application submission APIs (employer API key)

- **search-reported** (applicationformsubmit; creating-a-custom-careers-page)
  `POST https://api.ashbyhq.com/applicationForm.submit`, `Content-Type: multipart/form-data`,
  permission `candidatesWrite`. Body: `jobPostingId`, `applicationForm` with `fieldSubmissions`
  keyed by each field's `path` (for example `_systemfield_name`), a file field pointing to a separate
  multipart part (example key `resume_1`, "any string … unique in the request form"), optional
  `utmData` and tag ids, and `allowSubmissionForUnpublishedJobPosting`.
- **search-reported** Job boards should use `applicationForm.submit`, not `application.create`
  (which is for sourcing).
- **search-reported** Survey forms (for example EEOC) are submitted **after** the application with
  `surveySubmission.create` (`surveyFormDefinitionId`, `candidateId`, `applicationId`,
  `submittedValues`; `candidatesWrite`). EEOC and diversity answers are never included in the
  `surveySubmit` webhook payload.
- **search-reported** (authentication; introduction; API-key article) HTTP Basic auth, API key as
  username, blank password; 401 without a key, 403 for a wrong or deactivated key or a missing
  permission. Keys are generated by Organization Admins (Admin > Integrations > API Credentials) on
  some plans. "The full Ashby API isn't intended to be used directly from a browser" (no CORS).
- **search-reported** Rate limit: 1,000 requests per minute per API key (stricter report limits).
- **search-reported** Duplicates (application-requests; application-limits): an application whose
  email matches an existing candidate is attached to that profile; reapplying with the same details
  while active does not create a second consideration; different details create a profile that may
  be flagged as a duplicate; admins can configure application limits matched by email.
- **unknown** The success response shape, an idempotency key, and the API's response when an
  application limit blocks a submission.
- **inferred** Not usable by NoEfforts: every submission endpoint needs the employer's key.

## 3. Hosted application page (as documented, not observed)

- **search-reported** (application-forms) A posting has an application form plus optional survey
  forms (for example EEOC). Forms can be shared, customised per posting or inherit the default.
  Question types in the form builder include Yes/No (with "no answer" when not required), Resume
  (once per form), File (one upload), Candidate's location (once per form) and Other location.
  Conditional logic is supported.
- **search-reported** (creating-a-custom-careers-page) API field types: `String`, `Email`, `File`,
  `Date`, `Number`, `Boolean`, `LongText`, `ValueSelect`, `MultiValueSelect`, `Phone`, `Score`,
  `SocialLink`. Each field has `id`, `type`, `path`, `humanReadablePath`, `title`, `isNullable`,
  with a sibling `isRequired`. **unknown** How options are listed for select fields
  (`selectableValues` was seen only in other contexts), and how the help centre's location question
  appears in the API enum (it is not in the list above).
- **search-reported** (candidate-files) File questions accept up to 50 MB in common document,
  image and video types; executables and some text formats (for example .md) are not supported.
- **search-reported** (job-board-configuring-your-setup) Optional resume autofill ("Show Autofill
  Field on Application Forms?") fills resume, name, email, location, education history and social
  links; not every field is filled for every resume; resumes up to 16 MB are parsed.
- **search-reported** (job-board-application-spam-protection) Ashby scores each submission as human
  or bot. Levels run from strict to permissive, or none; permissive is recommended; strict "can
  block real candidates". **unknown** The mechanism (no reCAPTCHA or hCaptcha mention found) and
  what a blocked candidate sees.
- **search-reported** (job-board-cookie-consent-settings) The job board has cookie-consent
  settings, so a consent banner may appear.
- **unknown** Candidate accounts or sign-in: none found. **inferred** not required.
- **unknown** Multi-step: not documented; whether EEOC survey questions show on the same page as the
  application is unknown.
- **unknown** Email verification codes: none found.

## 4. URL patterns (checked against `detect_ats`)

- **search-reported** Board `jobs.ashbyhq.com/{slug}`; posting `jobs.ashbyhq.com/{slug}/{uuid}`;
  the embed's `data-tab="application"` opens the application tab; the employer's careers page gets
  `?ashby_jid=<uuid>` from "View Posting"; custom domains are not supported (embed via script or
  iframe). The documented `applyUrl` example is a placeholder (`…/example/apply`).

Checked locally with fictional URLs (no network):

| Fictional URL | `detect_ats` |
|---|---|
| `https://jobs.ashbyhq.com/examplehealth/<uuid>` | ashby |
| `https://jobs.ashbyhq.com/examplehealth/<uuid>/application` | ashby |
| `https://careers.examplehealth.invalid/jobs?ashby_jid=<uuid>` | **unknown**; ashby since D81 |
| `https://jobs.ashbyhq.com/example/apply` (the docs' placeholder) | unknown |

- **inferred** Embedded postings on employer sites (`ashby_jid`) are not recognised, unlike
  Greenhouse's `gh_jid`, which `detect_ats` handles. Adding it would need an identity test with
  `.invalid` hosts; the company slug cannot be read from such a URL.

## 5. Terms, robots, automated access

- **search-reported** (www.ashbyhq.com/resources/terms) The Customer Terms of Service (section 5.1,
  acceptable use) bind customers; no rule for third parties reading public postings was found.
- **search-reported** "Unlisted job postings should not be displayed publicly"; if you expose
  postings publicly, set `listedOnly` (authenticated list endpoint).
- **unknown** Candidate terms, robots.txt, or rules on automated use of the hosted form.

## 6. Contradictions with the repository

- docs/provider-architecture.md has no Ashby specification, and the registry has no `ashby`
  provider. Ashby is identity-only (docs/implementation-plan.md: "Ashby identity-only"). Nothing
  contradicts that.
- The legacy audit (docs/legacy-audit.md U8, U10, LD-28) says the old code ticked consent boxes,
  clicked "accept" banners and filled any "location" label with the home city. The documented
  cookie-consent settings and the two location question types make these checkpoints, which agrees
  with the repository's current rules.

## 7. Proposed synthetic fixture: "Example Health (fictional)"

**Implemented (D81)** as `backend/app/modules/preparation/fixtures/ashby.html` (the form only, as a
preparation fixture; no receiver route and no adapter). Tests: `backend/tests/test_workday_ashby_fixtures.py`.

A local fixture with two views: the public posting list (search-reported shape) and the
form definition (search-reported `applicationFormDefinition` and `surveyFormDefinitions`). NoEfforts
would read the form from the hosted page, so the fixture should render these fields as a page with
the same paths.

```json
{
  "posting_api": {
    "apiVersion": "1",
    "jobs": [{
      "id": "00000000-0000-4000-8000-00000000b001",
      "title": "Clinical Data Analyst (fictional)",
      "location": "Springfield (fictional)",
      "secondaryLocations": [{"location": "Shelbyville (fictional)", "address": {"addressCountry": "Fictionland"}}],
      "department": "Analytics", "team": "Clinical Data",
      "isListed": true, "isRemote": true, "workplaceType": "Hybrid",
      "employmentType": "FullTime",
      "publishedAt": "2026-01-01T00:00:00.000Z",
      "descriptionHtml": "<p>Example Health (fictional)…</p>", "descriptionPlain": "Example Health (fictional)…",
      "jobUrl": "http://127.0.0.1:8799/ashby/examplehealth/00000000-0000-4000-8000-00000000b001",
      "applyUrl": "http://127.0.0.1:8799/ashby/examplehealth/00000000-0000-4000-8000-00000000b001/application"
    }, {
      "id": "00000000-0000-4000-8000-00000000b002", "title": "Unlisted role (fictional)", "isListed": false
    }]
  },
  "applicationFormDefinition": {"sections": [{"fields": [
    {"isRequired": true,  "field": {"path": "_systemfield_name",   "type": "String",   "title": "Name"}},
    {"isRequired": true,  "field": {"path": "_systemfield_email",  "type": "Email",    "title": "Email"}},
    {"isRequired": false, "field": {"path": "_systemfield_resume", "type": "File",     "title": "Resume"}},
    {"isRequired": false, "field": {"path": "phone",               "type": "Phone",    "title": "Phone"}},
    {"isRequired": false, "field": {"path": "linkedin",            "type": "SocialLink","title": "LinkedIn"}},
    {"isRequired": true,  "field": {"path": "location",            "type": "Location (unconfirmed)", "title": "Candidate's location"}},
    {"isRequired": true,  "field": {"path": "authorized",          "type": "Boolean",  "title": "Are you authorized to work in Fictionland?"}},
    {"isRequired": true,  "field": {"path": "sponsorship",         "type": "Boolean",  "title": "Will you require sponsorship?"}},
    {"isRequired": false, "field": {"path": "years_sql",           "type": "Number",   "title": "Years of SQL experience"}},
    {"isRequired": false, "field": {"path": "start_date",          "type": "Date",     "title": "Earliest start date"}},
    {"isRequired": true,  "field": {"path": "tool",                "type": "ValueSelect", "title": "Primary analysis tool",
                                    "options (unconfirmed shape)": ["R", "Python", "Other"]}},
    {"isRequired": false, "field": {"path": "tool_other",          "type": "String",   "title": "Which tool?"},
     "condition (unconfirmed shape)": {"path": "tool", "any_of": ["Other"]}},
    {"isRequired": false, "field": {"path": "domains",             "type": "MultiValueSelect", "title": "Clinical domains",
                                    "options (unconfirmed shape)": ["Oncology", "Cardiology", "Pediatrics"]}},
    {"isRequired": false, "field": {"path": "why",                 "type": "LongText", "title": "Why Example Health?"}},
    {"isRequired": false, "field": {"path": "portfolio",           "type": "File",     "title": "Work sample"}},
    {"isRequired": false, "field": {"path": "score",               "type": "Score",    "title": "(recruiter-only; must not render)"}}
  ]}]},
  "surveyFormDefinitions": [{"id": "eeoc-fictional", "title": "Voluntary EEOC survey (fictional)", "fields": [
    {"path": "gender",   "type": "ValueSelect", "options": ["(fictional list)", "Decline to self-identify"]},
    {"path": "race",     "type": "ValueSelect", "options": ["(fictional list)", "Decline to self-identify"]},
    {"path": "veteran",  "type": "ValueSelect", "options": ["(fictional list)", "Decline to self-identify"]},
    {"path": "disability","type": "ValueSelect","options": ["Yes", "No", "I do not want to answer"]}]}],
  "modes": ["autofill_from_resume", "spam_protection_strict_blocks", "cookie_banner",
            "conditional_reveals_field", "duplicate_email_attaches_to_existing",
            "application_limit_blocks", "unlisted_posting_direct_link_only"]
}
```

Mapping to NoEfforts `FieldType`: String→text, Email→email, Phone→tel, LongText→textarea,
Number→number, Date→date, File→file, SocialLink→url, ValueSelect→select or radio (by rendered
control), MultiValueSelect→checkbox_group or multiselect, Boolean→radio (Yes/No buttons; "no
answer" when optional), Score→unsupported (not candidate-facing, inferred), location→unsupported
(checkpoint).

## 8. Checkpoints (stop and ask the user)

1. Spam-protection block or any challenge: hand off; outcome unknown, never resubmitted.
2. Cookie-consent banner: never clicked for the user.
3. Candidate's location and Other location: residence is a fact, never filled from a preference.
4. Resume autofill: every autofilled value read back; a mismatch stops.
5. Boolean authorization and sponsorship questions: tri-state facts; unknown stays unknown.
6. Any consent or certification checkbox: the user's own choice.
7. EEOC survey: optional; explicit per-question choice; decline is valid.
8. Conditional fields revealed after an answer: re-extract; stop if not understood.
9. Unlisted postings (`isListed: false`): never shown in discovery lists.
10. A possible repeat application (same email): stop before sending.
11. Final submit: separate approval; unknown outcome becomes `submitted_unconfirmed`.
