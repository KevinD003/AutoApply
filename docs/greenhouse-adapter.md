# Greenhouse-hosted adapter (fixture-verified)

Status: **implemented and tested against a local, labelled approximation only.** It has not
been run against Greenhouse or any real employer. Real Greenhouse destinations are refused at
queue time, and NoEfforts' form capture refuses to read real job posts. (One public posting was
observed read-only by the separate, owner-authorized manual workflow described in
`docs/greenhouse-compatibility-report.md`; nothing was filled or submitted.) Passing the tests
shows compatibility with the fixture, not with any real employer's form.

## Why Greenhouse

Greenhouse was the candidate in `docs/first-adapter-proposal.md`, and the choice holds. Its
public Job Board API documents a typed question schema per job post: wording, description,
required flag, field types and option values. That lets preparation be deterministic and gives
a second view to cross-check against the rendered page. Lever and Ashby also publish postings,
but their application endpoints likewise need the employer's key and add nothing for a
candidate-side tool. One adapter, not several.

## Access basis (kept separate)

| Access | What it allows | Used here |
|---|---|---|
| Public job post JSON (`GET …/jobs/{id}?questions=true`) | reading the questions | fixture only; reading real posts is not enabled |
| Employer-authorised API (application POST with the employer's key) | submitting as the employer's integration | no: candidate-side tools do not hold that key |
| Hosted form in a browser | what a candidate does | fixture only |
| Sandbox | none known for candidates | none |

Reading a public post is not permission to submit an application.

## What is supported (fixture)

| Step | Behaviour | Code |
|---|---|---|
| Posting identity | board token and job id from `job-boards.greenhouse.io/{board}/jobs/{id}`, `boards.greenhouse.io/…`, `embed/job_app?for=&token=`, or the fixture path `/gh/{board}/jobs/{id}` on a fixture origin | `preparation/greenhouse.py::parse_posting` |
| Inspect and extract | the job post JSON and the rendered page are read, mapped and **cross-checked**. Wording, description, type, required flag, options and the submit target must agree; otherwise the capture is refused. Show-if conditions come from the page | `build_schema`, `POST /api/jobs/{id}/form/greenhouse` |
| Field mapping | `input_text` → text (email and phone typed), `textarea`, `input_file` → document (the "paste instead" box is an alternative, not used), `multi_value_single_select` → select, `multi_value_multi_select` → checkbox group, data-compliance consent → consent checkbox with the page's wording | `_field` |
| Unsupported controls | hidden values (for example location coordinates) and unknown types become `unsupported`: required ones block approval (apply manually); optional ones stay blank. Never guessed, never typed by the user | `FieldType.unsupported`, resolver |
| Standard answers | the existing deterministic resolver, by wording: names, email, phone, links, work authorization, documents; no job-field assumptions | `resolver.py` |
| Long-form answers | written by the user (or an accepted draft if a provider is configured); no live AI needed | existing answer flow |
| Conditional questions | evaluated against the answer that shows them. If the condition is not met, the question is "not asked": nothing entered or sent. If it is met, the question is required and resolved normally | `package._condition_met` |
| Review and approval | unchanged: the exact wording and the source of every answer are shown; approval is bound to the package hash | existing |
| Execution | in the isolated browser: CAPTCHA or bot check → stop before disclosure. A form changed since approval → stop before disclosure. Fill in form order (conditional after its trigger); attachments upload when chosen and count as disclosures; read every control back; send gate; submit | `execution/adapters/greenhouse.py` |
| Security code | the "enter the emailed code, then submit again" step uses the existing code checkpoint (wrong code → new round; expiry → abandoned). **Synthetic/unverified:** the step is the fixture's own design; capability flag `unverified.security_code` | `enter_code` |
| Outcomes | confirmation page → confirmed (evidence strength `employer_confirmation_page`; no application id is shown), **only if** it answers this attempt's own POST to the approved submit URL and is shown on the same origin under the same job path; a confirmation for another posting or origin → unknown; error list → rejected; timeout, 5xx or anything unrecognised → unknown → reconciliation, never resent | `_click`, `_ours` |
| Conditional questions | trigger answered and not matching → not asked; matching → asked; trigger unanswered → still pending (blocks approval if required); trigger missing, later or circular → never filled, required → apply manually | `package.build_content` |
| Hidden inputs | page-managed (`form_token`, `*_attachment_id`) are protocol, never questions; hidden inputs declared as questions in the job data are unsupported (required → apply manually) | `greenhouse.schema_from_api`, extractor |
| Capability flags | `inspect, extract, fill, upload, checkpoint, submit, confirm` true; `real_destinations` false | `policy.CAPABILITIES["greenhouse_hosted"]` |

## Not supported

- Real Greenhouse posts or employers: reading and submitting are both refused.
- CAPTCHA or bot checks: stop, never solved or bypassed.
- Location pickers with hidden coordinates: a checkpoint when required.
- Multi-page or login-gated (MyGreenhouse) applications.
- Pasting text instead of attaching a document.
- Employer-authorised API submission.
- Demographic sections beyond an ordinary sensitive question: these use the existing consent
  flow (default: not disclosed).

## Fixture

`fixtures/ats_receiver/greenhouse_like.py` is an approximation built from the public
documentation and reported candidate behaviour. It is not Greenhouse markup. It serves:
- the job post JSON and the hosted form;
- attachment upload;
- submission and the security code.

The receiver's modes cover:
- normal and delayed submission;
- validation errors;
- errors before and after acceptance;
- a dropped response;
- a failed upload;
- CAPTCHA;
- a page that disagrees with the job data (`gh_drift`);
- the security code.

Two fictional jobs: 4012001 (all supported types, a conditional question, GDPR consent) and
4012002 (a location picker with hidden coordinates).

## Tests

`backend/tests/test_greenhouse_adapter.py` (19 tests, receiver ledger as oracle) and the e2e
test "Greenhouse-style form: …" in `frontend/e2e/submission.spec.ts` (desktop and mobile).

## Before any real use

See `docs/live-pilot-gate.md`. At minimum:
- legal review of Greenhouse's terms for automated submission;
- verify the real page structure and the security-code step against one authorised posting
  (the DOM view is fixture-shaped today);
- a CAPTCHA policy per board;
- the browser sandbox limits in `docs/architecture.md`.
