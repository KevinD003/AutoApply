# Workday: public-documentation research (2026-10-29)

Scope: bounded, read-only reading of Workday's public vendor documentation. No
`*.myworkdayjobs.com` site, employer careers site, API call, sign-in or form submission was made.

**Headline: no Workday documentation page could be opened from this session.** `doc.workday.com`
fails DNS resolution (outside the session's network allowlist). Workday's GitHub organisation was
reachable but has no recruiting material. Everything below is therefore **search-reported** (a web
search summary of a doc.workday.com, community.workday.com or workday.com page I could not open),
**inferred** or **unknown**. None of it is enough to record `public_doc_reviewed` for Workday.

## Labels used

- **documented**: read by me in a page I opened, with its URL. (No Workday fact qualifies.)
- **search-reported**: a web-search summary attributes this to the URL given; the page was not
  opened. A lead to confirm, not evidence.
- **inferred**: my reasoning from the above; says what it rests on.
- **unknown**: nothing found.

## Sources read

| URL | Date (UTC) | Result |
|---|---|---|
| https://doc.workday.com/ | 2026-10-29 ~15:24 | **inaccessible**: `getaddrinfo ENOTFOUND doc.workday.com` (host outside this session's network allowlist; not a vendor block) |
| https://github.com/Workday | 2026-10-29 | accessible; 55 repos, first 10 shown; none about recruiting |
| https://github.com/Workday/WorkdayDeveloperProgram | 2026-10-29 | accessible; Workday Build examples ("not an officially supported Workday product"); no recruiting, candidate or career-site content |
| https://github.com/orgs/Workday/repositories?q=recruit | 2026-10-29 | accessible; "No repositories matched your search." |

Not attempted (after four vendor-doc hosts failed DNS, the tool guidance was to stop trying more
hosts): https://community.workday.com/sites/default/files/file-hosting/productionapi/index.html
(Workday Web Services directory), https://developer.workday.com/,
https://www.workday.com/en-us/legal/end-user-agreement.html.

Search-result URLs used for **search-reported** facts (pages not opened):

- Candidate Home: https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/gtv1538650489786.html
- External career sites: https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/san1394588983205.html,
  https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/ddo1548786792678.html
- GA4 custom events (page names): https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/hnr1671753523279.html
- Course manuals: https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/career-sites.html,
  https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/prospects-and-candidates.html,
  https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/job-requisition-components.html
- Resume parsing: https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/candidates/set-up-prospects-and-candidates/hdc1552497830785.html
- Self-identification of disability: https://doc.workday.com/admin-guide/en-us/human-capital-management/country-specific-information-and-reporting/united-states-reporting-requirements/self-identification-of-disability/gjd1595597354997.html
- Questionnaires: https://doc.workday.com/admin-guide/en-us/manage-workday/business-processes/questionnaires/questionnaire-video-examples/collect-information-from-job-applicants/create-a-questionnaire.html
- Tenant setup: https://doc.workday.com/admin-guide/en-us/manage-workday/tenant-configuration/tenant-setup/lde1511812666156.html,
  https://doc.workday.com/admin-guide/en-us/manage-workday/tenant-configuration/tenant-setup/dan1370796470031.html
- Duplicates and withdrawal: https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/candidates/duplicate-candidate-merging/rsy1568992210598.html,
  https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/job-applications/zrk1513293483267.html
- Web services: https://community.workday.com/sites/default/files/file-hosting/productionapi/Recruiting/v25.2/Recruiting.html,
  https://community.workday.com/sites/default/files/file-hosting/productionapi/Recruiting/v23.2/Put_Candidate.html,
  https://community.workday.com/sites/default/files/file-hosting/productionapi/Recruiting/v30.2/Get_Job_Postings.html,
  https://developer.workday.com/documentation/GUID-6b063b57-9d85-474b-99b0-734d714652fd-enHYPHENus/RESTAPIsinAppsandIntegrations
- WCL accounts: https://doc.workday.com/user-guide/en-us/workday-central-login-wcl-/wev1666724954446.html
- Terms: https://www.workday.com/en-us/legal/end-user-agreement.html,
  https://www.workday.com/en-us/privacy/recruiting-privacy-statement.html

## 1. Public, unauthenticated job/posting API

- **unknown** No public, unauthenticated job-posting API was found in any vendor documentation
  surfaced by search.
- **search-reported** (Recruiting web service pages on community.workday.com) The SOAP Recruiting
  service has `Get_Job_Postings` ("returns information for Job Postings specified in the
  requests"; filters by date, posting site, supervisory organization, requisition, active only).
- **search-reported** (Workday training material) Web-service access uses an Integration System
  User (ISU); REST uses OAuth 2.0 API clients registered by the tenant ("OAuth 2.0 Clients
  Enabled", "Register API Client"), and access follows the tenant's security groups.
- **inferred** Every documented API is tenant-authenticated (credentials held by the employer).
  There is nothing a candidate-side product may call.

## 2. Application submission APIs

- **search-reported** (Put_Candidate pages) `Put_Candidate` "adds or updates a candidate";
  Job Application Data or Prospect Data is required on add; an "Add Only" flag makes "Candidate
  already exists" a validation error.
- **inferred** Requires the employer's ISU or OAuth client; not usable by a third party acting for a
  candidate. No idempotency key was seen; "Add Only" is the only duplicate control found.
- **unknown** What confirms a submission through the API (response shape not read).

## 3. Hosted application page (as documented, not observed)

- **search-reported** (Create External Career Sites; course manual) An external career site has a
  Job Listing page, a Job Details page and an Application form that is "an application wizard";
  sections may include contact information, experience, application questions, voluntary
  disclosures, terms and conditions, and final review.
- **search-reported** (GA4 custom events reference) Page names: My Information, My Experience,
  Voluntary Disclosures, Self Identify, Application Questions (1 of 2, 2 of 2), an optional
  Supplementary Questionnaire, Review; final submission is logged separately. The order depends on
  the site's configuration.
- **search-reported** (Candidate Home; Edit Tenant Setup - Recruiting) Sign-in is optional by
  default. "Require Candidate Home Account" makes candidates create an account before submitting.
  If it is not selected, Workday selects "Enable Candidate Verification Email". Email is the
  account identifier. Tenant password rules show on account creation. Candidates may also create an
  account after applying. Signed-in candidates can reuse their last application and see status.
- **search-reported** (WCL guide, a different product) Workday Central Login uses a 6-digit
  emailed one-time code and authenticator-app setup. Whether candidate accounts use it is
  **unknown**.
- **search-reported** (Resume parsing concept) Candidates may attach a resume or skip it and enter
  details manually. Parsing fills personal and contact information, work experience, education and
  languages, but does not auto-fill Languages or Skills, and "results can vary based on resume
  format". Admins can hide parsing.
- **search-reported** (External career sites) "Quick Apply" fills the application from a resume,
  CV or previous application; "Apply with LinkedIn" (and SEEK) prefill from a profile.
- **search-reported** (Questionnaires; job requisition components) Question types: date, multiple
  choice (single or multi select), number, text, attachment. Questions can be required. Branching
  follow-ups hang off a single-select question, up to six levels. Up to 50 questions. Multiple-choice
  answers can carry a score. Standard mapped eligibility questions exist: age, work eligibility,
  sponsorship, salary, notice period, start date.
- **search-reported** Voluntary disclosures (ethnicity, gender, veteran status) appear only for
  jobs with a U.S. primary location. The U.S. disability self-identification form (CC-305) is
  optional unless the administrator requires it, and shows before submission for U.S. jobs.
- **search-reported** A terms-and-conditions text, when configured, adds an acknowledgement check
  box.
- **search-reported** (Duplicate merging; withdrawal) Email identifies candidates; "Enable
  Automatic Candidate Merging" merges duplicates applying on external sites. Internal candidates
  cannot reapply to a requisition while active; no such rule found for external candidates.
  External candidates with an account may Withdraw, if the stage allows it.
- **unknown** CAPTCHA or bot checks: searches found nothing in Workday's documentation.
- **unknown** Whether drafts are saved per step on the server before final submit.
- **unknown** Per-step server validation behaviour (only implied by the wizard).

## 4. URL patterns (checked against `detect_ats`)

- **search-reported** (Create External Career Sites) The site ID "becomes part of the URL" and
  "Workday converts spaces to dashes". The Prospect page is "[External site URL]/introduceYourself".
- **search-reported** Tenant URLs include a customisable tenant base name.
- **unknown** The `myworkdayjobs.com` host pattern, the job path and any `/apply` sub-path: no vendor
  page found states them. The search tool itself called `<tenant>.wdN.myworkdayjobs.com/<site>`
  "general knowledge … unverified".

Checked locally with fictional URLs (no network). The shapes are the repository's own test shapes
plus unverified candidates:

| Fictional URL | `detect_ats` |
|---|---|
| `https://examplehealth.wd5.myworkdayjobs.com/en-US/External/job/Remote/Nurse_R-100001` | workday, req `R-100001` |
| `https://examplehealth.wd103.myworkdayjobs.com/External/job/Remote/Nurse_JR100001` | workday, req `JR100001` |
| `…/job/Remote/Nurse_R-100001/apply` (unverified shape) | **unknown** |
| `…/job/Remote/Nurse_R-100001/apply/autofillWithResume` (unverified shape) | **unknown** |
| `https://examplehealth.wd5.myworkdayjobs.com/External/introduceYourself` | unknown (correct: not a posting) |
| `https://wd5.myworkdaysite.com/recruiting/examplehealth/External/job/Remote/Nurse_R-100001` (unverified shape) | **unknown** |

- **inferred** The regex requires the path to end with `_<req>`, so any apply sub-path or an
  alternative host returns `unknown` (a manual handoff, the safe failure). Whether those shapes
  exist must come from documentation or the approved read-only observation, not from guessing.

## 5. Terms, robots, automated access

- **search-reported** (Workday US End User Agreement, workday.com) "You may not use automated
  software, scripts, or other methods of accessing or using the Website without Workday's consent";
  scraping, crawlers and bypassing access controls are also barred. It refers to "the Website";
  whether it covers employers' `myworkdayjobs.com` career sites is **unknown**.
- **search-reported** Each career site may show the employer's own terms and conditions.
- **inferred** This clause is a real risk for any browser automation on Workday-hosted sites. It
  needs the owner's (and possibly legal) review before a fixture-to-observation step.

## 6. Contradictions and updates for docs/provider-architecture.md §7

1. "Employer-scoped accounts and sessions": search-reported docs say the account is **configurable
   per tenant** (optional by default, mandatory if required), so `login_required: expected` is
   too strong. Suggest "expected on some tenants; per-tenant setting".
2. "User-assisted login and verification": consistent (email verification is a tenant option).
3. "Multi-step forms": consistent (application wizard; page names above).
4. "Repeating work-history and education records": consistent (My Experience; parsing fills work
   experience and education).
5. "Résumé parsing and prefill validation": consistent, and parsing is documented as imperfect.
6. "Checkpoints for CAPTCHA": CAPTCHA is not documented; keep the checkpoint, but
   `captcha_possible` should be `unknown` (not seen in docs) rather than "expected" if the trait
   must rest on evidence.
7. Not in the spec: voluntary disclosures and CC-305 only for U.S. jobs; a terms-and-conditions
   acknowledgement; standard eligibility questions (work eligibility, sponsorship, salary, age);
   branching questionnaires; Quick Apply / LinkedIn prefill; candidate merging by email; the
   end-user agreement's automated-access clause.
8. "stopped before `public_doc_reviewed`": this review cannot lift it, since no Workday doc page
   was opened.

## 7. Proposed synthetic fixture: "Example Health (fictional)"

**Implemented (D81)** as `backend/app/modules/preparation/fixtures/workday.html` (the form only, as a
preparation fixture; no receiver route and no adapter). Tests: `backend/tests/test_workday_ashby_fixtures.py`.

A local multi-page wizard served by the receiver. Page names follow the search-reported GA4
list. (u) marks a shape I have not seen documented; it is a fixture design choice.

```json
{
  "tenant": "examplehealth-fictional",
  "site_id": "External",
  "posting": {"title": "Registered Nurse, Night Shift (fictional)", "req": "R-100001",
              "primary_location_country": "US", "url": "http://127.0.0.1:8799/workday/External/job/Springfield/Nurse_R-100001"},
  "account": {"mode": "optional | mandatory", "verification_email": true,
              "password_rules_shown": true, "code_entered_by_user": true},
  "start": {"options": ["attach_resume_and_parse", "apply_manually", "use_last_application (signed in)",
                        "apply_with_linkedin (disabled in fixture)"]},
  "pages": [
    {"step": "my_information", "fields": [
      {"key": "source", "type": "select", "required": true, "label": "How did you hear about us?",
       "options": ["Job board", "Referral", "Other"], "widget": "custom dropdown (u)"},
      {"key": "previous_worker", "type": "radio", "required": true, "options": ["Yes", "No"]},
      {"key": "country", "type": "select", "required": true, "options": ["Fictionland", "Otherland"]},
      {"key": "legal_name.first", "type": "text", "required": true},
      {"key": "legal_name.last", "type": "text", "required": true},
      {"key": "address.line1", "type": "text"}, {"key": "address.city", "type": "text"},
      {"key": "address.postal_code", "type": "text"},
      {"key": "email", "type": "email", "required": true},
      {"key": "phone.device_type", "type": "select", "options": ["Mobile", "Home"]},
      {"key": "phone.country_code", "type": "select", "options": ["+000 Fictionland"]},
      {"key": "phone.number", "type": "tel", "required": true}]},
    {"step": "my_experience", "fields": [
      {"key": "work[0].title", "type": "text", "repeat": "work"},
      {"key": "work[0].company", "type": "text", "repeat": "work"},
      {"key": "work[0].current", "type": "checkbox", "repeat": "work"},
      {"key": "work[0].from", "type": "date", "repeat": "work"},
      {"key": "work[0].to", "type": "date", "repeat": "work", "condition": "work[0].current = false"},
      {"key": "work[0].description", "type": "textarea", "repeat": "work"},
      {"key": "education[0].school", "type": "unsupported", "repeat": "education",
       "unsupported_reason": "search-as-you-type (u)"},
      {"key": "education[0].degree", "type": "select", "repeat": "education", "options": ["Fictional BSc", "Other"]},
      {"key": "languages[0]", "type": "select", "repeat": "languages", "note": "not auto-filled by parsing"},
      {"key": "skills", "type": "unsupported", "unsupported_reason": "multi-select search (u); not auto-filled"},
      {"key": "resume", "type": "file", "accept": ".pdf,.doc,.docx"},
      {"key": "websites[0]", "type": "url", "repeat": "websites"}]},
    {"step": "application_questions_1_of_2", "fields": [
      {"key": "q.work_eligibility", "type": "radio", "required": true, "options": ["Yes", "No"]},
      {"key": "q.sponsorship", "type": "radio", "required": true, "options": ["Yes", "No"]},
      {"key": "q.licence_type", "type": "radio", "required": true, "options": ["RN", "LPN", "None"]},
      {"key": "q.licence_number", "type": "text", "condition": "q.licence_type in [RN, LPN]"},
      {"key": "q.licence_state", "type": "select", "condition": "q.licence_type in [RN, LPN]",
       "options": ["Fictional State A", "Fictional State B"], "note": "branch level 2 of max 6"}]},
    {"step": "application_questions_2_of_2", "fields": [
      {"key": "q.salary_expectation", "type": "number"},
      {"key": "q.start_date", "type": "date"},
      {"key": "q.notice_period", "type": "number"},
      {"key": "q.shifts", "type": "checkbox_group", "options": ["Nights", "Weekends", "On call"]},
      {"key": "q.licence_copy", "type": "file", "required": false}]},
    {"step": "voluntary_disclosures", "us_only": true, "fields": [
      {"key": "vd.ethnicity", "type": "select", "options": ["(fictional list)", "Decline"]},
      {"key": "vd.gender", "type": "select", "options": ["(fictional list)", "Decline"]},
      {"key": "vd.veteran", "type": "select", "options": ["(fictional list)", "Decline"]},
      {"key": "vd.terms_ack", "type": "checkbox", "required": true,
       "label": "I have read and agree to the (fictional) terms and conditions"}]},
    {"step": "self_identify", "us_only": true, "form": "CC-305", "fields": [
      {"key": "si.name", "type": "text"}, {"key": "si.date", "type": "date"},
      {"key": "si.disability", "type": "radio",
       "options": ["Yes", "No", "I do not want to answer"]}]},
    {"step": "review", "fields": []}
  ],
  "modes": ["account_mandatory", "verification_email", "resume_prefill_overwrites",
            "parse_misreads_dates", "step_validation_rejects_page_2", "branching_reveals_fields",
            "non_us_posting_hides_disclosures", "duplicate_candidate_merged",
            "withdraw_available", "terms_ack_required"]
}
```

The receiver ledger must count disclosures per step (each "Next" sends data) and the final submit
separately, and record any server-side draft.

## 8. Checkpoints (stop and ask the user)

1. Account sign-in or creation, password and email verification code: always the user, never stored.
2. Choosing resume parsing, manual entry, last application or LinkedIn prefill: the user's choice.
3. Every page boundary ("Next"): a disclosure boundary with its own permission.
4. Every prefilled value (parsed resume, last application): read back against the approved
   package; a mismatch stops.
5. Work eligibility, sponsorship, residence, salary, age: tri-state facts; unknown stays unknown.
6. Voluntary disclosures and CC-305: explicit per-question choice; decline is valid.
7. Terms-and-conditions acknowledgement: a legal attestation, only the user ticks it.
8. Search-as-you-type controls (school, skills) and custom dropdowns without evidence: unsupported.
9. Branching questions that appear after an answer: re-extract, and stop if not understood.
10. A per-step validation error after data was sent: classify rejected or unknown; never resend.
11. Any CAPTCHA or security prompt: hand off.
12. A possible duplicate (same email and requisition, or an existing account with an application).
13. Final submit: separate approval; unknown outcome becomes `submitted_unconfirmed`.
14. Before any automation at all: the owner's decision on the end-user agreement's
    automated-access clause.
