# Lever: public-documentation research (2026-10-29)

Scope: bounded, read-only reading of Lever's public vendor documentation. No employer board,
posting, API call, sign-in or form submission was made. Example boards named inside the docs
were **not** visited (and are not named here).

## Labels used

- **documented**: read by me in a page I opened, with its URL.
- **search-reported**: a web-search result summary attributes this to the URL given, but the page
  itself could not be opened from this session (host blocked, see "Sources read"). It is a lead to
  confirm, not evidence. It does not count towards `public_doc_reviewed`.
- **inferred**: my reasoning from documented facts; says what it rests on.
- **unknown**: nothing found.

## Sources read

| URL | Date (UTC) | Result |
|---|---|---|
| https://github.com/lever/postings-api | 2026-10-29 | accessible (official Lever repo) |
| https://raw.githubusercontent.com/lever/postings-api/master/README.md | 2026-10-29 | accessible, HTTP 200, read in full (25,813 bytes) |
| https://github.com/orgs/lever/repositories | 2026-10-29 | accessible (29 repos; only `postings-api` and `integrator-resources` are relevant) |
| https://github.com/lever/integrator-resources | 2026-10-29 | accessible (README: Data API Postman collection, OAuth example app) |
| https://github.com/lever/integrator-resources/tree/main/DataAPIPostman | 2026-10-29 | accessible |
| https://raw.githubusercontent.com/lever/integrator-resources/main/DataAPIPostman/Lever-DataAPI-Collection.json | 2026-10-29 | accessible, HTTP 200, 152,004 bytes; request tree and selected bodies read |
| https://raw.githubusercontent.com/lever/integrator-resources/main/DataAPIPostman/Lever-OAuth-Environment.json | 2026-10-29 | accessible, HTTP 200 |
| https://hire.lever.co/developer/documentation | 2026-10-29 ~15:23 | **inaccessible**: `getaddrinfo ENOTFOUND hire.lever.co`, i.e. the host is outside this session's network allowlist (not a vendor block) |
| https://help.lever.co/hc/en-us | 2026-10-29 ~15:24 | **inaccessible**: `getaddrinfo ENOTFOUND help.lever.co` (same cause) |

Not attempted (after four vendor-doc hosts failed DNS, the tool guidance was to stop trying more
hosts): https://www.lever.co/legal, https://www.lever.co/legal/terms-of-service,
https://hire.lever.co/developer/partner.

Search-result URLs used for **search-reported** facts (pages not opened):
https://hire.lever.co/developer/documentation,
https://hire.lever.co/developer/updates,
https://hire.lever.co/developer/partner,
https://help.lever.co/hc/en-us/articles/20087243347741-Configuring-your-Lever-application-form,
https://help.lever.co/hc/en-us/articles/20087340764701-Using-equal-employment-opportunity-EEO-questions,
https://help.lever.co/s/article/How-Lever-supports-OFCCP-compliance-efforts,
https://help.lever.co/hc/en-us/articles/20087359881245-Relying-on-explicit-consent-for-data-retention,
https://help.lever.co/hc/en-us/articles/20087339443101-Configuring-General-Data-Protection-Regulation-GDPR-settings,
https://help.lever.co/hc/en-us/articles/20087458260893-Blocking-repeat-applications,
https://help.lever.co/s/article/Fraud-Signals,
https://help.lever.co/s/article/Making-responses-to-custom-application-questions-secret,
https://www.lever.co/legal.

## 1. Public, unauthenticated job/posting API (Postings API)

Source for every **documented** item here: the postings-api README (URL above).

- **documented** Base URLs: `https://api.lever.co/v0/postings/` (global) and
  `https://api.eu.lever.co/v0/postings/` (EU). "The API is not available via unencrypted HTTP."
- **documented** `GET /v0/postings/SITE?skip=X&limit=Y` (list) and `GET /v0/postings/SITE/POSTING-ID`
  (one posting, JSON only). Each company "currently only has one site (usually your company name
  with no spaces)".
- **documented** List parameters: `mode` (json, iframe, html; the query parameter beats the
  `Accept` header), `skip`, `limit`, `location`, `commitment`, `team`, `department` (repeatable,
  OR'ed, case sensitive with multiple values), `level`, `group` (`location`/`commitment`/`team`),
  `css` and `resize` (iframe mode; must be allow-listed in the employer's job-site settings).
- **documented** Pagination: `skip` and `limit` only. No cursor, no total count documented.
- **documented** Posting fields: `id`, `text`, `categories` (`location`, `commitment`, `team`,
  `department`, `allLocations`), `country` (ISO 3166-1 alpha-2 or null), `opening`,
  `openingPlain`, `description`, `descriptionPlain`, `descriptionBody`, `descriptionBodyPlain`,
  `lists` (`{text, content}`), `additional`, `additionalPlain`, `hostedUrl`, `applyUrl`,
  `workplaceType` (`unspecified`, `on-site`, `remote`, `hybrid`), `salaryRange` (`currency`,
  `interval`, `min`, `max`; optional), `salaryDescription`, `salaryDescriptionPlain`.
- **documented** What it does **not** do (quoted list): no full-text search; no cross-origin
  requests from outside the company's domains (CORS); no internal postings; no iframe for detail or
  application pages; no custom success/error URLs; it does not "Expose custom questions built into
  your job postings"; no referral information.
- **documented** "all job postings in the `published` state are publicly viewable. These jobs may be
  scraped by third parties. All other jobs are completely hidden from the jobs API."
- **inferred** The GET endpoints need no key: the README asks for a key only for the POST
  (`?key=APIKEY`) and shows none for GET. CORS limits browsers only, not a server-side reader.
- **inferred (important)** The public API cannot give NoEfforts the application form: no custom
  questions, no EEO section, no consent text, no required flags. A form can only come from the
  hosted page (read-only observation) or from the authenticated Data API (employer key).
- **documented** No rate limit is stated for the GET endpoints. **unknown** whether one exists.
- **unknown** Enum values of `salaryRange.interval`.

## 2. Application submission APIs

### 2a. Postings API POST (employer key)

Source: postings-api README.

- **documented** `POST /v0/postings/SITE/POSTING-ID?key=APIKEY`. JSON or multipart form-data;
  "our API only accepts resumes in multipart form data mode".
- **documented** "To use the POST API, you need an API key, which a Super Admin of your account can
  generate from your integrations settings page".
- **documented** Fields: `name` (required), `email` (required, needs "@", "Candidate records will
  be merged when email addresses match"), `resume` (file, multipart only), `phone`, `org`, `urls`
  (object, e.g. `{"GitHub": "..."}` or `urls[GitHub]=...`), `comments`, `silent` (suppresses the
  confirmation email), `source`, `ip` ("used for detecting country for compliance reasons"),
  `timezone`, `userAgent`, `acceptLanguage`, `referer`, `consent.marketing`, `consent.store` (each
  optionally `{provided, compliancePolicyId}`, "waved rollouts starting mid-September, 2024"),
  `opportunityLocation`.
- **documented** "Required fields and url fields can be customized per account"; administrators
  "can customize their job applications and choose to make other fields required".
- **documented** Success: `200` with `{ok:true, applicationId: '...'}`; error: an HTTP error code
  with `{ok:false, error:<error string>}`.
- **documented** Duplicates: "Lever de-dupes candidates using the email address field". No
  idempotency key is documented.
- **documented** Rate limit: `429` if a custom job site sends "more than 2 application POST requests
  per second"; it "may also be changed without warning". The README tells integrators to queue and
  retry 429s, calls the hosted form "a best practice", and asks custom forms to "Implement spam
  mitigations such as captchas and session or IP based rate limits".
- **inferred** Not usable by NoEfforts: the key belongs to the employer's Super Admin. This matches
  the repository's statement that the authorized-API route does not apply to Lever.

### 2b. Data API (`hire.lever.co/developer/documentation`, page not reachable)

- **documented** (Postman collection, official repo) Collection-level auth is HTTP Basic with
  `username = {{apiKey}}`; most requests are configured for OAuth 2.0 (client id/secret, scopes;
  the environment's `Scopes` value is `offline_access`). Endpoints include `/postings`,
  `/postings/:posting`, `/opportunities` (`?parse=true&perform_as=`), `/uploads`,
  `/opportunities/:opportunity/files`, `/form_templates`. The collection's "Apply to a Posting"
  entry is empty (no URL or body).
- **documented** (Postman) A form-template example uses field types `date` and `currency` with
  `text`, `description`, `required`. These are internal forms, not candidate questions.
- **search-reported** (hire.lever.co/developer/documentation) `GET /postings/:posting/apply`
  ("Retrieve posting application questions") lists the questions on a posting's form with
  required flags, and includes EEO questions when enabled. `POST /postings/:posting/apply`
  submits; `customQuestions` order must match the questions endpoint; `personalInformation` and
  `eeoResponses` are separate objects; files go first through the upload endpoint; it only works for
  `published` or `unlisted` postings; no confirmation email unless `send_confirmation_email=true`
  (default false). A changelog entry (hire.lever.co/developer/updates) adds an `origin` field
  (`applied` or `internal`).
- **search-reported** Custom-question types: two search summaries disagree. One lists file upload,
  dropdown, multiple choice, multiple select, text, textarea and university; another confirms only
  `multiple-select` and `textarea` in a sample response and says files go through the upload
  endpoint. The exact type strings are **unknown** until the page is read.
- **search-reported** Rate limit: token bucket per API key, "10 requests per second" steady, bursts
  "up to 20", not guaranteed; retry with exponential backoff.
- **search-reported** (hire.lever.co/developer/partner) OAuth is "part of our partner integration
  program, and apps must be registered"; "completing and releasing an integration is a requirement
  for being a Lever partner".
- **inferred** A third party may use the Data API only as a registered partner authorised by each
  employer (OAuth) or with the employer's own key. Neither is a candidate-side route.

## 3. Hosted application page (as documented, not observed)

- **documented** (README) Hosted job site `https://jobs.lever.co/SITE` (EU `jobs.eu.lever.co`),
  posting `…/SITE/POSTING-ID`, form `…/SITE/POSTING-ID/apply`. "The API is modeled off our hosted
  jobs form."
- **documented** (README) The hosted form "properly handles all custom form configurations … and
  maintains very high availability including queuing and retries at peak times".
- **search-reported** (Configuring your Lever application form) Default fields: Resume, Full Name,
  Email, Phone, Current Location, Current company. Full Name and Email required by default; the
  others can be made required. Current Location is pre-filled from a parsed resume, otherwise
  picked manually. File-upload questions accept files up to 100 MB. A "suspicious user (a bot)"
  cannot use the Current Location drop-down "unless they solve the hCaptcha puzzle".
- **search-reported** (EEO article, OFCCP article) EEO questions (gender, race, veteran status,
  disability) are configured by Admins in Settings > Company > Surveys; short and long versions;
  for U.S.-based postings; disability collection only for U.S. federal contractors; Lever adopted
  the 2023 CC-305 disability form.
- **search-reported** (explicit-consent and GDPR articles) In explicit-consent mode the storage
  checkbox is mandatory to submit; a marketing consent checkbox is optional; a privacy-policy link
  can appear "above the 'Submit Application' button".
- **search-reported** (Making responses … secret) Custom questions can be marked secret; the
  candidate sees the same form.
- **search-reported** (Blocking repeat applications) A job-site setting blocks repeat
  applications; "applications submitted via Lever's API will not be blocked".
- **search-reported** (Fraud Signals) Post-submission fraud screening (fake emails, virtual phone
  numbers, fast completion, mass application patterns).
- **unknown** Candidate account or sign-in: none mentioned in anything read. **inferred** not
  required (the README sends candidates straight to the hosted form), but not documented.
- **unknown** Multi-step: nothing read says the form is one page or several.
- **unknown** Email or SMS verification codes: none mentioned.
- **unknown** What the hosted success page shows.

## 4. URL patterns (checked against `detect_ats`)

Documented shapes: `jobs.lever.co/SITE/POSTING-ID[/apply]` and `jobs.eu.lever.co/…`; posting ids
in the README's examples are UUIDs. Checked locally with fictional URLs (no network):

| Fictional URL | `detect_ats` |
|---|---|
| `https://jobs.lever.co/examplehealth/<uuid>` | lever |
| `https://jobs.lever.co/examplehealth/<uuid>/apply` | lever |
| `https://jobs.eu.lever.co/examplehealth/<uuid>/apply?lever-source=x` | lever (tracking dropped) |
| `https://jobs.sandbox.lever.co/examplehealth/<uuid>` | unknown |
| `https://api.lever.co/v0/postings/examplehealth/<uuid>` | unknown |

- **inferred** Consistent with the docs. A sandbox job host is only **inferred** (search results
  show a `hire.sandbox.lever.co` developer host); leaving it unrecognised is the safe default.
- **inferred** API URLs being "unknown" is right: they are data endpoints, not postings to apply to.

## 5. Terms, robots, automated access

- **documented** (README) Published postings "may be scraped by third parties". This is a
  statement of fact, not a grant of permission.
- **documented** (README) Application POSTs are rate limited "to guard against possible misuse".
- **search-reported** (www.lever.co/legal) The Legal Center lists a "Developer Sandbox Terms of
  Use"; its text was not seen. The customer Terms of Service govern customers.
- **unknown** Any Lever terms for candidates or for automated use of the hosted form; robots.txt was
  not read (fetching it from the job-site host is outside the approved scope).

## 6. Contradictions and updates for docs/provider-architecture.md §7b

1. "nothing was read from Lever (no page, API or documentation)": no longer true after this review
   (the Postings API README was read). Update only once the owner records the review.
2. "A hosted application form without a candidate account is expected": not contradicted, still
   undocumented. Keep the trait `unknown`.
3. "CAPTCHA possible: expected": supported (search-reported hCaptcha on Current Location for
   suspicious users; the README asks custom forms to use captchas).
4. "Multi-step: unknown": still unknown.
5. "Any API route would need the employer's own authorization": confirmed (POST key from a Super
   Admin; Data API key or partner OAuth).
6. Not in the spec yet: the public API does not expose custom questions, so the form must come from
   the hosted page; candidates merge by email; consent `store`/`marketing` with a compliance policy;
   EEO only on U.S. postings; the README's advice to retry 429s does not apply to NoEfforts, which
   never retries a final send.

## 7. Proposed synthetic fixture: "Example Health (fictional)"

A local fixture only (for `fixtures/ats_receiver`), never a real host. `<id>` is a fictional
UUID such as `00000000-0000-4000-8000-00000000a001`. Fields marked (sr) are search-reported
shapes to confirm.

```json
{
  "posting": {
    "id": "00000000-0000-4000-8000-00000000a001",
    "text": "Registered Nurse, Night Shift (fictional)",
    "categories": {"location": "Springfield (fictional)", "commitment": "Full-time",
                   "team": "Nursing", "department": "Clinical",
                   "allLocations": ["Springfield (fictional)", "Shelbyville (fictional)"]},
    "country": "US",
    "opening": "<p>Example Health (fictional) is hiring.</p>", "openingPlain": "Example Health (fictional) is hiring.",
    "description": "<p>…</p>", "descriptionPlain": "…",
    "descriptionBody": "<p>…</p>", "descriptionBodyPlain": "…",
    "lists": [{"text": "Requirements", "content": "<li>A fictional licence</li>"}],
    "additional": "", "additionalPlain": "",
    "hostedUrl": "http://127.0.0.1:8799/lever/examplehealth/<id>",
    "applyUrl": "http://127.0.0.1:8799/lever/examplehealth/<id>/apply",
    "workplaceType": "on-site",
    "salaryRange": {"currency": "USD", "interval": "fixture-placeholder", "min": 70000, "max": 90000},
    "salaryDescription": "<p>Fictional range</p>", "salaryDescriptionPlain": "Fictional range"
  },
  "form": {
    "single_page": true,
    "sections": [
      {"key": "personal", "fields": [
        {"key": "resume", "type": "file", "required": false, "accept": ".pdf,.doc,.docx"},
        {"key": "name", "type": "text", "required": true, "label": "Full name"},
        {"key": "email", "type": "email", "required": true},
        {"key": "phone", "type": "tel", "required": false},
        {"key": "location", "type": "unsupported", "required": false, "label": "Current location",
         "unsupported_reason": "location autocomplete; prefilled from resume; may raise hCaptcha (sr)"},
        {"key": "org", "type": "text", "required": false, "label": "Current company"}]},
      {"key": "links", "fields": [
        {"key": "urls[LinkedIn]", "type": "url"}, {"key": "urls[GitHub]", "type": "url"},
        {"key": "urls[Portfolio]", "type": "url"}, {"key": "urls[Other]", "type": "url"}]},
      {"key": "custom_questions (sr)", "fields": [
        {"key": "cards[q1][field0]", "type": "text", "required": true, "label": "Fictional licence number"},
        {"key": "cards[q1][field1]", "type": "textarea", "required": false, "label": "Why Example Health?"},
        {"key": "cards[q1][field2]", "type": "select", "required": true, "label": "Preferred shift",
         "options": ["Nights", "Days", "Either"]},
        {"key": "cards[q1][field3]", "type": "radio", "required": true,
         "label": "Are you legally authorized to work in the fictional country?", "options": ["Yes", "No"]},
        {"key": "cards[q1][field4]", "type": "checkbox_group", "required": false, "label": "Certifications",
         "options": ["BLS", "ACLS", "PALS"]},
        {"key": "cards[q1][field5]", "type": "file", "required": false, "label": "Cover letter"},
        {"key": "cards[q1][field6]", "type": "unsupported", "label": "University",
         "unsupported_reason": "university picker (sr); search-as-you-type"}]},
      {"key": "comments", "fields": [{"key": "comments", "type": "textarea", "label": "Additional information"}]},
      {"key": "eeo (sr; US postings only)", "optional_section": true, "fields": [
        {"key": "eeo[gender]", "type": "select", "options": ["Female", "Male", "Decline to self-identify"]},
        {"key": "eeo[race]", "type": "select", "options": ["(fictional list)", "Decline to self-identify"]},
        {"key": "eeo[veteran]", "type": "select", "options": ["(fictional list)", "Decline to self-identify"]},
        {"key": "eeo[disability]", "type": "select", "options": ["Yes", "No", "I do not want to answer"],
         "note": "CC-305; federal contractors only"}]},
      {"key": "consent (sr)", "fields": [
        {"key": "consent[store]", "type": "checkbox", "required": "explicit-consent mode only"},
        {"key": "consent[marketing]", "type": "checkbox", "required": false}],
       "privacy_policy_link_above_submit": true}
    ]
  },
  "modes": ["hcaptcha_on_location", "explicit_consent_required", "eeo_hidden_non_us",
            "duplicate_email_merges_silently", "resume_prefills_location", "confirmation_email_sent"]
}
```

The receiver ledger should count one candidate per email (Lever merges by email) and record each
send separately, so a duplicate send is visible in the ledger even though Lever would not show it.
The confirmation page is a fixture design choice (undocumented) and must be labelled as such.

## 8. Checkpoints (stop and ask the user)

1. Any CAPTCHA, including hCaptcha on Current Location: hand off, never solve.
2. Current Location: residence is a fact; a resume-prefilled value is never accepted as approved.
3. Explicit storage consent and marketing consent: each is the user's own choice, never ticked
   for them. Show the privacy-policy link.
4. EEO and disability (CC-305) questions: never inferred; disclosed only by explicit per-question
   choice; "decline" is a valid answer.
5. Authorization and sponsorship custom questions: tri-state facts; unknown stays unknown.
6. University picker and any other search-as-you-type control: unsupported until proven.
7. A resume-parsed prefill that differs from the approved package: read back and stop.
8. Any field the extractor cannot map (Lever's custom questions are not in the public API).
9. Final submit: separate explicit approval; an unknown outcome becomes `submitted_unconfirmed`,
   never retried (whatever the README says about retrying 429s on the API).
10. A possible repeat application (same email, same posting): stop before sending.
