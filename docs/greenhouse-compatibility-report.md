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

## B2 — per-field mapping observation (manual run #4, authorized once)

- **Run:** manual run #4 ([39455167671](https://github.com/KevinD003/AutoApply/actions/runs/39455167671)),
  2026-10-20.
  - Revision `151e7a0`: the `a11c71d` code plus docs-only commits.
  - Workflow conclusion: success. Run once, not retried.
- **Requests:**
  - A: 3 GETs, all HTTP 200; identity checks passed.
  - B: 1 navigation (HTTP 200) and 9 browser requests in total; 0 non-GET; 43,185 bytes
    received.
  - No limit was reached, no bot check, network idle reached, ready state `complete`.
- **Blocked dependencies:** 8 of the 9 requests went to other `greenhouse.io` hosts (2 hosts)
  and were refused by the allow-list: 5 scripts, 2 stylesheets, 1 image.
  - Only the page document itself loaded. What was observed is the page as served, **without**
    those scripts and styles.
  - Their purpose is not inferred. Anything they would add or change (for example dropdown
    option lists or other widgets) was not observable. The run reports
    `may_be_incomplete: true`.
- **Output privacy:** the printed summary passed the guard. The run log contains no raw custom
  question id and no posting URL (checked over the whole log). Raw data stayed in the worker
  container, which the script's exit trap removes (`compose down -v`).

All results below were observed at load, with no interaction, and apply to this posting only.

| Observation | Fields | Detail |
|---|---|---|
| **unique** | 17 of 22 | `first_name`, `last_name`, `preferred_name`, `email`, `phone`, plus 12 custom questions (`q01`–`q12`). Each has exactly one control with that id, a suitable element and an accessible name equal to the label (via `<label for>` for text inputs, `aria-labelledby` for comboboxes), and is visible. Required attributes match the job data |
| **incompatible** | 2: `resume`, `cover_letter` | one file input each, with a matching id and visible, but the accessible name differs from the job-data label, and no control carries that label. Refused, not guessed |
| **absent** | 1: `location` | no control with that id at load, and no control labelled with its wording |
| **not_observable** | 2: `latitude`, `longitude` | page-managed values: no control with those ids at load; what writes them cannot be seen without interaction |
| ambiguous | 0 | — |

- **Dropdowns (7 single-choice custom questions):** each is a unique `role=combobox` input. It
  controls **no listbox at load**, so its options are `not_observable_at_load`. They were not
  assumed to equal the job data and are not counted as a mismatch.
- **Controls no API field names:** 5, all visible, labelled `role=combobox` inputs in the
  form. 2 carry a required attribute, and 1 sits in a group with another control. None is a
  text alternative of an API field. Their purpose is not inferred.
- **Totals:** 24 controls = 17 unique + 2 file inputs + 5 unnamed comboboxes.

**What this means:**
- **Shown:** 17 of 22 job-data fields correspond one-to-one, by id and label, to controls on
  this page as served.
- **Not shown:**
  - that any of them can be filled, or that dropdown values can be chosen;
  - how the attachments or the location picker behave;
  - what the blocked scripts would have changed.
- **Today's adapter would refuse this posting** before disclosing anything, because of the
  attachment label mismatch and the absent location control. It would be a checkpoint anyway,
  because of the required hidden coordinates.
- **Fixture assumptions** (combobox opening, option lists, uploads, submission) remain
  assumptions; B2 neither confirms nor refutes them, since the scripts that implement them were
  blocked.

## Host identification (manual run #5, authorized once)

- **Run:** manual run #5 ([39475562252](https://github.com/KevinD003/AutoApply/actions/runs/39475562252)),
  revision `90a12ab`, `--identify-only`. Success.
- **Requests:** 0 API requests; 1 page navigation (HTTP 200); 9 browser requests, all GET;
  43,050 bytes received. B2's allow-list was unchanged, so both hosts below stayed blocked
  (refused before sending).
- **Page:** the same structure as B2 (24 id-only controls, 12 comboboxes, 2 file inputs).

| Blocked host | Port | Scheme | Requests (all GET) | Resource types |
|---|---|---|---|---|
| `job-boards.cdn.greenhouse.io` | 443 | https | 7 | script 5, stylesheet 2 |
| `recruiting.cdn.greenhouse.io` | 443 | https | 1 | image 1 |

Both names passed the publication rules: plain `*.greenhouse.io` names containing neither the
board token, nor the job id, nor any other value derived from the posting. Their purpose is not
inferred beyond the request types observed.

## B3 — page loaded with its approved dependencies (manual run #6, authorized once)

- **Run:** manual run #6 ([39490684255](https://github.com/KevinD003/AutoApply/actions/runs/39490684255)),
  revision `bf6642b`.
  - CI #42 passed all four jobs on that exact revision first, including the container-mode B3
    policy scenario.
  - Conclusion: success. No stop; run once, not retried.
- **Requests:**
  - API: 3 GETs, all 200.
  - Page: 1 navigation (200); 19 browser requests, all GET; 0 non-GET attempted;
    391,888 bytes received.
  - No limit reached, no bot challenge, network idle reached.
- **Allowed and loaded:** scripts and stylesheets from `job-boards.cdn.greenhouse.io:443`.
- **Refused before sending, by the approved policy:**
  - 10 requests to `job-boards.cdn.greenhouse.io`: 4 data requests (fetch) and 6 fonts;
  - 1 image request to `recruiting.cdn.greenhouse.io`, which stayed blocked.
  What those would have provided is unknown. Rendering is still reported as possibly
  incomplete.
- **Privacy:** the printed summary passed the guard. The whole log contains no raw question id
  and no posting URL. Raw data was destroyed with the stack.

**Comparison with B2** (field by field, via `compare_runs` over both published summaries):

| Question | B2 | B3 |
|---|---|---|
| Field observations | 17 unique, 2 incompatible, 1 absent, 2 not observable | **unchanged**: no field changed observation |
| Attachment controls (`resume`, `cover_letter`) | incompatible (own label differs) | still incompatible under B3's rules. **New evidence:** each file input sits in a group whose accessible name equals the question exactly, and the input's own label differs |
| Location control | absent | absent |
| Hidden coordinates | not observable (page-managed) | not observable (no such controls at load) |
| Dropdown options | 7 × not observable at load | 7 × still not observable without interaction (no listbox in the DOM) |
| The 5 unmatched comboboxes | not classified | 1 inside the same group as an API field's control (`phone`); 4 standalone and labelled, none labelled like an API question; 2 of the 5 carry a required attribute. Purpose not inferred |
| Required flags | — | unchanged for every field |
| DOM counts | 24 id-only controls, 12 comboboxes, 2 file inputs | identical |
| Bot challenge | none | none |

**What this means:**
- Loading the approved scripts and stylesheets did **not** change the form at load.
- The remaining gaps need interaction (dropdown options, the location search) or the refused
  data requests, and neither is authorized. They are reported as not observable without
  interaction; no further no-interaction run is proposed.
- **Attachments: one evidence-backed local change** (below). The rest of the posting stays
  refused by the adapter, for several reasons:
  - the absent location control;
  - the required hidden coordinates (a checkpoint);
  - 4 visible comboboxes the job data does not list, one of them required;
  - the attachment inputs carry no required attribute although the job data requires the
    resume (a "changed" field to the adapter).

**Local change justified by B3:**
- **New mapping status `mapped_via_group`, for attachments only.** It applies when all of
  these hold:
  - exactly one control has the field's id;
  - it is a file input;
  - its enclosing group is named exactly as the question;
  - that group contains no other file input.
- **What does not qualify:** a group named differently, or a group holding two file inputs.
  Both stay `label_mismatch` and are refused.
- **Tests and fixture:** fixture modes `gh2_attach_group(_wrong|_shared)`; tests in
  `tests/test_greenhouse_dom.py`, including a full fixture run with receiver-verified upload
  digests.
- **Effect on this posting:** none. It remains refused.
- **Interpretation:** B3's printed result predates this rule (it reports `incompatible`). Under
  the new rule these two fields would map, with every other gap unchanged.

## B3 evidence record (closed 2026-10-20; accepted as complete)

These four things are kept apart.

1. **B3 live observations:** manual run #6, revision `bf6642b`, once, after CI #42 passed on
   that revision.
   - Mapping unchanged from B2.
   - Attachment inputs sit in groups named exactly as their questions.
   - Recorded above. This is the only real-page evidence.
2. **The attachment mapping change made afterwards:** `mapped_via_group`, attachments only.
   It was written from that evidence, in `ee35b49`.
3. **Its local tests:** fixture modes `gh2_attach_group(_wrong|_shared)` and
   `tests/test_greenhouse_dom.py`.
   - **Final tested revision `ee35b49`, CI #43** ([39492067001](https://github.com/KevinD003/AutoApply/actions/runs/39492067001)):
     - backend 317 passed, 1 skipped;
     - Playwright 26 passed;
     - execution-compose 85 checks, 0 failed;
     - docker-smoke passed.
   - The existing execution regressions are unchanged and still pass.
4. **Remaining live incompatibilities:**
   - the absent location control;
   - the required, page-managed coordinates;
   - 4 standalone comboboxes not in the job data (1 required);
   - a combobox inside the phone field's group;
   - attachment inputs without a required attribute while the job data requires the resume;
   - dropdown options not observable without interaction.

**The attachment rule has not been validated against any later real run.** B3's printed
result predates it, and no external run has happened since run #6.

## Dropdowns: what the retained evidence shows (no new requests)

Source: B3's published anonymous summary and local code only. No page was retrieved and no
destroyed raw data was reconstructed.

| Control | Count | At load |
|---|---|---|
| Mapped dropdown questions `q01 q02 q03 q04 q07 q09 q11` | 7 | <ul><li>Each is an `input` with `role=combobox`, unique id, named via `aria-labelledby`, `aria-describedby` present, not in a group.</li><li>The required attribute matches the job data for all 7 (required).</li><li>No listbox in the DOM (`controls_listbox: false`).</li><li>The job data lists 2, 2, 250, 26, 2, 2 and 2 options.</li></ul> |
| Combobox in the phone field's group (`u1`) | 1 | <ul><li>Named via `aria-labelledby`, not like any API question.</li><li>Carries a required signal.</li><li>The phone text input itself maps uniquely, and its group is named as the phone question.</li></ul> |
| Standalone unmatched comboboxes (`u2`–`u5`) | 4 | <ul><li>Labelled, visible, in the form, not in any group.</li><li>None labelled like an API question.</li><li>`u2` carries a required signal; `u3`–`u5` do not.</li></ul> |

**How "required" is represented (what was recorded):**
- **Input level:** `required_attr` was recorded, but it merges the HTML `required` attribute
  and `aria-required="true"`. Which of the two the page uses was not recorded.
- **Group level:**
  - the phone and attachment groups were recorded as groups (`in_group`, `group_label`);
  - no group-level required signal was recorded.
- **Label marker (e.g. a trailing `*`):** not recorded.
- **Attachments:** neither required signal is present, although the job data requires the
  resume.

**What the evidence cannot settle without interaction:**
- the options of any dropdown, and whether they equal the job data's options;
- whether `u1` is a supporting control (e.g. a dialling-country picker for the phone number)
  or a question;
- what `u2`–`u5` ask: their wording is not retained and must not be published;
- whether they behave like questions (own options, not equal to any API question's);
- whether opening any dropdown adds, removes or re-requires controls;
- whether a location control appears only through interaction;
- whether option lists depend on the 4 data requests to the CDN that were refused at load.

**Proposed next step:** a bounded widget inspection, implemented and tested locally, **not
approved and not run**. See `docs/greenhouse-readonly-compatibility-proposal.md`, "Widget
inspection".

## Widget inspection (manual run #7, authorized once): failed before any widget action

- **Run:** [39535843106](https://github.com/KevinD003/AutoApply/actions/runs/39535843106),
  revision `2b0bcbb`. That is `1fc58b2`, whose CI #45 passed, plus a status-doc change; CI #46
  on `2b0bcbb` also passed.
  - Workflow conclusion: success, because the CLI reports a stop and exits normally.
  - Page observation: `error (TimeoutError)`. Run once, not retried.
- **Requests:**
  - **API:** 3 GETs, all 200. This is the authorized budget, now used.
  - **Page:** the one navigation was intercepted by the in-browser request filter, which
    raised `NameError` on it. The filter neither continued nor aborted it, so the request
    stayed pending inside the browser, and the navigation timed out after 60 s.
  - This is the only request the filter saw (one traceback in the log). Requests the filter
    holds are not released to the network. There is no server-side request record for a
    real site, so "not sent" rests on that mechanism, not on a ledger.
- **Widget actions:** 0.
- **Page evidence:** none. No options, required signals or structure were observed.
- **Cause (code defect, mine):**
  - the CLI runs the module as a script (`python -m`);
  - its `if __name__ == "__main__"` block stood before the inspection code at the end of
    the file, so in script mode `main()` ran before `DATA_REQUEST_TYPES` existed;
  - the tests and the Compose scenario import the module, which defines everything first,
    so none of them could see this.
- **Privacy:**
  - the guarded summary printed only `mode`, the 3 status codes, the stop and the approved
    subresource rule;
  - the one extra log output is that traceback: code lines and container file paths, no
    URL, host, label or posting detail;
  - secrets were masked; raw data was destroyed with the stack.
- **Fixed afterwards, locally:**
  - the entry point is now the module's last statement, and a test enforces it;
  - the request filter fails closed: any error aborts the request and stops the run with
    "the request filter failed", instead of leaving the request pending;
  - both new tests fail on `1fc58b2` (mutation-checked) and pass with the fix.
  The behaviour within the authorized scope is unchanged.
- **Unknowns:** everything listed under "Dropdowns" above is still unknown.

## Log cleanup (run #3's logs deleted with authorization; runs #1 and #2 untouched)

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
- **Done 2026-10-20, with the user's authorization:**
  - the logs of run #3 (39432345404) were deleted (API: 204);
  - its run record remains;
  - runs #1 and #2, other runs and commits were not touched.
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

## Follow-up (B2 has now run; see above)

- One more read-only observation, collecting per-field mapping evidence, is described with its
  enforced limits and approval text in `docs/greenhouse-readonly-compatibility-proposal.md`
  ("Follow-up observation B2").
- The original approval was single-use and is exhausted; it does **not** cover this run.
