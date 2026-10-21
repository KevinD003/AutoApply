# Read-only Greenhouse compatibility check — approval request

**Status: A and B approved by the user (2026-10-20) and used (read-only run #3; results in
`docs/greenhouse-compatibility-report.md`). C and D not approved. A follow-up read-only run
("Follow-up observation B2", below) is requested and not approved; it has not been run.**

The user wrote: "You can do everything that you want to do about the greenhouse but make sure
that no employee name is found in Rep. I can approve for both of them."
- Permissions A and B are granted for **one** public posting, which the user left to the
  developer to choose.
- Condition: no employer name, and no person's name, may appear in the repository. That
  includes committed docs and reports, CI logs and CI artifacts (the repository is public).
- Disclosing candidate data (C) and submitting an application (D) remain **not approved**.
  The general "do anything" does not cover them.
- **Execution is blocked in the development sandbox.** Its permission policy refused the first
  outbound request to Greenhouse. The sandbox's own TLS-re-terminating proxy would also make B
  require trusting a broad CA in the browser, which this plan rules out. See "How it will
  run" below.

This request covers **reading** one public posting. It is not a request to disclose candidate
data or to submit an application. Reviewing the documentation mentioned here is not legal
approval.

## Permissions (each recorded separately; none implies the next)

| | Permission | What it allows | Requested here |
|---|---|---|---|
| **A** | Retrieve public job/schema data | the HTTP GETs listed under A, for the one named posting | yes |
| **B** | Open the public application page in the isolated browser | one page load under B, observe only | yes, separately |
| **C** | Disclose candidate data | — | **no** |
| **D** | Submit an application | — | **no** |

A and B never imply C or D. B may be approved without A, or A without B. Approval covers
exactly the posting named below; it never extends automatically to other jobs, boards or
employers.

## What the user supplies

- `BOARD`: the board token, and `JOB_ID`: the numeric job id. These come from a public URL of
  the form `https://job-boards.greenhouse.io/BOARD/jobs/JOB_ID`, which the user chooses.
- A statement that the posting is public and the user is entitled to view it.
- Specific question: does the employer's careers page carry terms that forbid automated
  reading? Answer yes, no or unknown. If yes, stop. If unknown, the user decides whether to
  proceed.

## A — HTTP retrieval (backend HTTP client, no browser)

| # | Method and exact URL | Purpose |
|---|---|---|
| A0 | `GET https://boards-api.greenhouse.io/robots.txt` | check whether the API path is disallowed for automated clients |
| A1 | `GET https://boards-api.greenhouse.io/v1/boards/BOARD/jobs/JOB_ID?questions=true` | the documented job post JSON: questions, field names/types, required flags, options, data-compliance (consent) |
| A2 | `GET https://boards-api.greenhouse.io/v1/boards/BOARD` | board name only, to confirm the employer identity matches the posting |

- **Budget:** at most 3 requests in total, one each. No automatic retries; one manual retry of
  a request that got no response (connection failure) is allowed.
- **Limits:** 10 s timeout and 2 MB response limit per request.
- **Redirects:** not followed. A 3xx is recorded (status and target origin only) and ends A.
- **Client:**
  - the existing URL safety checks (public addresses only, connect to the checked address);
  - no cookies, no credentials, no API key;
  - a `User-Agent` that names NoEfforts and says it is a compatibility check.
- **Methods:** GET only. No other method is sent.

## B — Isolated browser, observe only

| Item | Value |
|---|---|
| Top-level navigation | exactly one: `https://job-boards.greenhouse.io/BOARD/jobs/JOB_ID` |
| Where | the Compose browser-runner (sandbox on, unprivileged user, limits), through the session egress proxy |
| Egress allow-list | `job-boards.greenhouse.io:443` **only** |
| Other origins | denied by the proxy and recorded as host:port. They are reported as "requested but not allowed". If the form needs one to render, that is a finding: naming and adding it needs a new approval round |
| Scripts | the page's own scripts **will execute** (the hosted board renders client-side). They run under the browser sandbox and can reach only the allowed origin |
| Redirects | a redirect within `job-boards.greenhouse.io` is followed. Any redirect to another origin (e.g. an employer-hosted careers page or embed) stops B; only the target origin is recorded |
| Budget | 1 navigation; at most 150 subresource requests and 20 MB; 60 s wall clock |
| Interaction | none: no typing, focus, clicks, uploads or scrolling into the form. The page is read once after load |
| Requests other than GET/HEAD | blocked before sending and recorded (method, host, path without query). Analytics or autosave POSTs are never let through |
| Session state | fresh browser context: no cookies, storage or profile from before; discarded at the end. Service workers blocked |
| Bot checks | if a CAPTCHA or bot-check script or element is detected, stop. Never solved, bypassed or waited out |

Engineering preconditions for B (not built yet; each needs its own review and synthetic test
before B can run):
1. A read-only adapter mode. Navigate and extract only. No fill or submit code path is
   reachable from it, and non-GET/HEAD requests are blocked, with a fixture test showing a
   page script's POST is blocked and recorded.
2. An explicit, off-by-default setting that allows that one origin for that one run. Real
   destinations stay refused everywhere else.
3. The Compose execution test passing on the image and host used for the run.

## Stop conditions (A and B)

Stop and report if any of these happen:
- robots.txt disallows the path;
- the posting returns 404/410, or the identity in A2 does not match the posting;
- any redirect to another origin;
- any login prompt, CAPTCHA or bot check;
- any request budget or time limit is reached;
- a sandbox self-check or isolation failure;
- an unexpected certificate or TLS error (never bypassed);
- anything that would require typing or clicking.

## Artifacts

All artifacts stay in the developer's workspace and are not committed.

| Artifact | Contents | Retention |
|---|---|---|
| A responses | raw JSON (public job data; no candidate data) and robots.txt | deleted within 30 days |
| B extraction | rendered form schema: labels, control types, names, required flags, options, help text; conditional/dynamic behaviour seen after load | deleted within 30 days |
| B request log | method, host:port, path without query, status, allowed/denied. No headers, cookies or bodies | deleted within 30 days |
| Committed report | the comparison below, using field keys, types and flags. Question wording is paraphrased, and the employer is named only if the user agrees | kept in the repository |

Not produced: screenshots, traces, HAR files, DOM dumps, cookies, or any candidate data.

## How it will run (implemented; not yet run against Greenhouse)

| Piece | What it does |
|---|---|
| `backend/app/modules/preparation/gh_readonly.py` | **A:** `fetch` sends three GETs to `https://boards-api.greenhouse.io` only, within a budget of 3, with no redirects, a 10 s timeout, a 2 MB limit, a robots.txt check and an identifying User-Agent. **B:** `observe_page` makes one page load in the isolated browser container; every non-GET/HEAD request is blocked before it leaves the browser; nothing is typed, clicked or uploaded; it stops at a bot check or an off-origin redirect. **Gating:** both refuse unless `NOEFFORTS_READONLY_GREENHOUSE_APPROVED` equals that posting's `<board>/<job_id>`. There is no code path to fill, upload or submit |
| `publishable()` | the only output: structure, types, flags and counts, plus third-party hosts reduced to known kinds or "other". No labels, wording, titles, employer or person names, URLs or board token |
| `scripts/greenhouse-readonly-check.sh` + `docker-compose.readonly-check.yml` | the deployment stack, with the egress proxy given an outbound network. The browser stays on internal networks, and its session allow-list is `job-boards.greenhouse.io:443` (public addresses only). Raw responses stay inside the worker container and are **destroyed when the stack is removed at the end of the run** (stricter than the 30 days above). No container logs are printed |
| `.github/workflows/greenhouse-readonly.yml` | **manual only** (`workflow_dispatch`). The posting comes from the repository secret `GH_READONLY_POSTING`, which GitHub masks in logs; no artifacts are uploaded |
| Tests | `backend/tests/test_gh_readonly.py` (10, against the local fixture): approval gating, budget and host, robots.txt, redirects, page POST blocked with 0 disclosures, bot check, container-only for real pages, no fixture names in the published summary. Compose `s_readonly_observation_in_container` runs the same B path through the real runner and proxy |

Why it runs in GitHub Actions and not in the development sandbox:
- the sandbox's permission policy refused the outbound request;
- its egress re-terminates TLS, which would require the browser to trust a broad CA, and this
  plan rules that out.

To run it:
1. **Choose the posting:** any public `https://job-boards.greenhouse.io/<BOARD>/jobs/<JOB_ID>`.
2. **Store it** as the repository secret `GH_READONLY_POSTING` with the value
   `<BOARD>/<JOB_ID>`: GitHub → Settings → Secrets and variables → Actions → New repository
   secret.
3. **Start it:** Actions → "Greenhouse read-only check (manual)" → Run workflow (B on by
   default).
4. **Commit:** the run prints only the anonymous summary. That summary, plus the comparison
   against the fixture, is what gets committed as `docs/greenhouse-compatibility-report.md`.

## Runs

| Run | Revision | Result |
|---|---|---|
| sandbox, 2026-10-20 | `86fa55e` | A not sent: the environment proxy denied `boards-api.greenhouse.io` (403). One attempt, not retried |
| CI read-only #1 | `fd9b03d` | stopped before any request: the secret was not set yet |
| CI read-only #2 | `fd9b03d` | A completed (3 GETs). B loaded the page but found **no extractable form fields**, and the run stopped. The code dropped A's summary on that stop; fixed so A is always reported and B reports anonymous DOM counts. Rerun under the user's broad statement ("You can do anything that you wanna do about the greenhouse"); see the note below |
| CI read-only #3 | `e2a8d97` | **completed.** A: 3×200. B: page 200, 9 GET requests, no non-GET request, no bot check; form not extractable (id-only controls, ARIA comboboxes). Report: `docs/greenhouse-compatibility-report.md` |
| CI read-only #4 (B2) | `151e7a0` | **completed**, authorized once. A: 3×200. B: 1 navigation, 9 requests (8 to other greenhouse.io hosts, blocked), 0 non-GET, 43,185 bytes. Mapping: 17 unique, 2 incompatible, 1 absent, 2 not observable |
| CI read-only #5 (identification) | `90a12ab` | **completed**, authorized once, `--identify-only`: 0 API requests; 1 navigation, 9 GET requests; blocked hosts: `job-boards.cdn.greenhouse.io:443` (5 script, 2 stylesheet), `recruiting.cdn.greenhouse.io:443` (1 image) |
| CI read-only #6 (B3) | `bf6642b` | **completed**, authorized once, after CI #42 passed on that revision. A: 3×200. B: 1 navigation, 19 GET requests; CDN scripts/stylesheets loaded; refused: 4 data requests + 6 fonts to the CDN, 1 image to the other host. Mapping unchanged from B2; attachments sit in groups named by the question |
| CI read-only #7 (widget inspection) | `2b0bcbb` (= `1fc58b2` + docs) | authorized once; workflow **succeeded but the page observation failed**: A 3×200; the page navigation was held inside the browser by a failing request filter (a `NameError` in script mode) and timed out after 60 s; **0 widget actions, no page evidence**. Authorization used; not rerun. Fixed locally afterwards |
| CI read-only #8 (replacement widget inspection) | `181b7c3` (pinned branch) | authorized once (conditional; conditions met, CI #49). Workflow success; **observation outcome `completed`**: A 3×200; 1 navigation, 26 GET requests, 0 non-GET; 12 dropdowns opened and closed (24 actions); **no option list observable** for any of them; 7 CDN data requests refused during actions; no selection or structural change. Not a compatibility result |
| CI read-only #9 (diagnostic re-observation) | `e1bd9e7` (pinned branch) | authorized once, after CI #52. Workflow success; **observation outcome `completed`**. A 3×200; 1 navigation, 26 GET requests; 24 actions on 12 dropdowns. All 12 `not_opened` within 600 ms, with 0 DOM mutations after each click. All 11 refused data requests are `GET /locales/*/*.json`. Required evidence consistent for all 19 mapped fields (resume required by its group) |

**Note on the budget.** A was written as "at most 3 requests in total" and B as "exactly one"
navigation. Runs #2 and #3 each used that budget once more, relying on the user's general
statement. From now on, every further read of the posting needs its own explicit approval
(below). Nothing further has been run.

## Follow-up observation B2 — approval request (not run)

**Status: authorized by the user for one run on 2026-10-20 and used (manual run #4,
39455167671, revision `151e7a0` = `a11c71d` code). Results: `docs/greenhouse-compatibility-report.md`
("B2"). The authorization is exhausted; any further run needs a new one.** The A/B approval
was single-use and was not reused.

### Enforced limits (`gh_readonly.Limits`, tested locally against fixtures)

| Limit | Value | Exact meaning | Test |
|---|---|---|---|
| API requests | 3 | GETs to `boards-api.greenhouse.io` only (robots.txt, job post, board); a 4th is refused before sending | `test_permission_a_three_gets_raw_data_kept_out_of_the_summary`, `test_budget_and_host_are_fixed` |
| API response size | 2,000,000 bytes each | read up to the limit; a larger body stops A | `test_api_response_size_limit_stops` |
| Top-level navigations | 1 | the page load itself; any later main-frame navigation is aborted **before it is sent** and stops the run | `test_second_top_level_navigation_is_aborted_and_stops` |
| Redirects | ≤ 3 hops, same origin | more hops stop; a hop to another origin is refused and stops; API redirects are never followed | `test_redirect_hops_are_limited`, `test_redirect_to_another_origin_stops`, `test_redirect_is_not_followed` |
| Browser requests | 150 | every request the page starts, redirect hops included; beyond it requests are aborted before sending and the run stops | `test_total_request_budget_stops` |
| Received bytes | 20,000,000 | **a stop condition, not a transfer cap**: summed from what the browser reports per finished request; once passed, further requests are aborted and the run stops, but a response already in flight still completes | `test_received_bytes_stop` |
| Retained page data | 2,000,000 characters | the serialized DOM kept in memory for reading; larger stops | `test_retained_dom_limit_stops` |
| Observation deadline | 90 s from the start of B | every browser wait is clamped to the time left; the run stops when none is left (in-process) | `test_overall_deadline_stops_a_slow_page` |
| Whole-run deadline | 150 s (A + B) | a watchdog thread prints one fixed line and ends the process (exit 5) whatever it is doing; the script also kills the command at 200 s; the job at 20 min | `test_watchdog_ends_the_whole_run_with_a_fixed_line` |
| Printed output | 262,144 bytes | larger, or failing the privacy guard: nothing but a refusal is printed (exit 4) | `test_output_size_limit_suppresses`, guard tests |

No byte cap on network transfer is claimed beyond the stop condition above.

### What is read, per API field (no interaction)

- **One observation:** `unique`, `absent` (no control with that id at load), `ambiguous`
  (several), `incompatible` (wrong element or role, or a label mismatch), or `not_observable`
  (page-managed values such as hidden coordinates).
- **The checks behind it**, each `true`, `false`, `not_observable_at_load` or
  `not_applicable`:
  - `label`;
  - `element`;
  - `options`: options that exist only after a dropdown opens are `not_observable_at_load`,
    never assumed equal and never counted as a mismatch;
  - `visible`.
- Grouping and ARIA relations, the required attribute, and how the label was found.
- Page controls that no API field names, described without their ids.
- Failed or denied requests by resource type, destination kind and error code; network-idle and
  ready state.

The mapping rules are the adapter's own; nothing is relaxed for B2. Every result is a live
observation at load. The fixture's widget behaviour is a separate, labelled assumption and is
not reported as observed.

### Output and retention

- **Printed:** the structural summary only.
  - Allowlisted vocabulary; custom question ids as `q01`…; counts and flags.
  - No labels, wording, option text, URLs, page text, screenshots, traces, HTML, response bodies
    or exception messages.
- **Where it is kept:**
  - in the run's log, under the repository's log retention or until deleted;
  - in a committed report that paraphrases it.
- **Raw data** (API JSON, DOM): only inside the worker container, destroyed when the stack is
  removed at the end of the run. No artifacts are uploaded.

### The request (send back, or say no)

```
I authorize one read-only observation B2 of the posting stored in the GH_READONLY_POSTING
secret (not echoed here):
- 3 API requests and 1 application-page navigation;
- enforced limits: 150 browser requests, 3 same-origin redirect hops, a 20 MB received-data
  stop, a 90 s observation deadline and a 150 s whole-run deadline;
- existing allowed destinations only (boards-api.greenhouse.io for A,
  job-boards.greenhouse.io:443 for the page);
- no clicks, typing, uploads, location searches, candidate sessions, OTP requests,
  submissions or automatic retries;
- output: the structural summary above, kept in the run log and a committed report; raw data
  destroyed at the end of the run.
C (candidate data disclosure) and D (submission) remain unapproved.
```

Run once authorized: Actions → "Greenhouse read-only check (manual)" → `observe` and `mapping`
checked, once.

## B3 — approved scope (approved 2026-10-20 for one run; run once as manual run #6 on `bf6642b` after CI #42 passed; authorization used)

**Purpose:** find out whether loading the page's own blocked dependencies changes the form,
and whether it resolves B2's specific gaps. Those gaps are:
- the attachment label mismatch;
- the absent location control;
- the page-managed coordinates;
- the 5 unmatched comboboxes;
- dropdown options not observable at load;
- required flags and visible questions;
- any bot challenge.

**Allow-list (exact; no wildcards, no automatic expansion):**

| Host | Port | Methods | Resource types | Basis (observed in run #5) |
|---|---|---|---|---|
| `job-boards.greenhouse.io` (unchanged) | 443 | GET, HEAD | as in B2 | the page itself |
| `job-boards.cdn.greenhouse.io` (new) | 443 | GET, HEAD | script, stylesheet only | the page requested 5 scripts and 2 stylesheets from it |
| `recruiting.cdn.greenhouse.io` | — | — | — | **not proposed:** its only observed request was 1 image. It stays blocked and is reported |

- **Anything else stays blocked before sending:**
  - any other host;
  - any other resource type or method to the new host (font, xhr, fetch, media and so on);
  - every non-GET to any host.
- **After scripts run:**
  - the same rules still apply;
  - each blocked request is recorded by structural category;
  - rendering is reported as incomplete when one is refused.
  No host is added during the run.
- **Redirects:**
  - the page: at most 3 same-origin hops, as in B2;
  - a subresource redirect to any host or resource type outside the table is refused and
    recorded.
- **Stop conditions:**
  - all of B2's: a second navigation, a redirect to another origin, the 150-request budget,
    the 20 MB received-data stop (a stop condition, **not** a strict transfer cap), the
    retained-DOM limit, the 90 s and 150 s deadlines, the output limit;
  - plus any bot challenge, which is never solved or bypassed.
  A stop is reported and never retried.
- **Observe-only:**
  - the same posting and a fresh browser context, with no candidate data;
  - no clicks, typing, uploads, location searches, OTP requests or submission.
- **API requests:** the comparison needs the job data, so B3 would make B2's 3 API requests
  once. This needs the same explicit approval as the page load.
- **Output and retention:**
  - B2's allowlisted structural summary (aliases, guard, 256 KiB cap) plus a field-by-field
    comparison with B2;
  - raw data destroyed with the stack; nothing uploaded.
- **Method policy, as approved:**
  - API host: GET only.
  - Page origin: GET only. HEAD to the page origin is now refused too; B2 allowed it, but no
    HEAD was observed in B2.
  - `job-boards.cdn.greenhouse.io`: GET and HEAD, only for scripts and stylesheets.
  - Everything else is refused before sending and recorded (method and path only).
- **How it is enforced** (`execution.browser.SubresourceRule`; the read-only observation
  only, never execution):
  - the browser's resolver rules;
  - the in-browser request filter: origin, method and resource type, and every redirect
    target in the driver-fetch mode;
  - the egress-proxy session allow-list: exact host:port;
  - the browser runner's resolver exemptions;
  - WebSockets to the dependency origin are routed and never connected.
  The rule is a fixed constant in code (`gh_readonly._b3_rules`). Any other rule on a real
  page is refused.
- **In container mode the browser follows redirects itself.** The proxy then refuses any hop
  to a host outside the allow-list. The resource type cannot change across a redirect.
- **Tested locally** (`tests/test_b3_policy.py`: 7 tests, through Chromium in its network
  namespace behind the egress proxy), against a fixture dependency origin:
  - approved scripts and stylesheets load, including a same-origin script redirect;
  - data requests, fonts, images, WebSockets, HEAD to the page, POST, and a redirect off the
    approved origins are never sent (receiver request log);
  - a mutation check confirmed that the test catches a missing resource-type restriction.
- **Container mode:** Compose `s_readonly_b3_dependency_policy_in_container` runs the same
  scenario through the real runner and session proxy; the canary must stay silent.
- **Comparison:** `gh_readonly.compare_runs(b2, b3)` runs locally over the two published
  summaries.

## Widget inspection — approved 2026-10-21 for one run; run once as manual run #7, which failed before any widget action (authorization used)

**Purpose:** find out how the visible dropdowns relate to the application questions. Five
questions, nothing else:
- which controls correspond to API questions;
- whether each unmatched control is an additional candidate question, a supporting control, or
  unresolved;
- whether options become observable when a dropdown is opened;
- whether a location-related control appears;
- whether opening a dropdown changes required fields or the form's structure.

**Posting:** the existing approved one, referenced only through the repository secret
`GH_READONLY_POSTING`. It is unchanged and not named anywhere.

**Run:** once, as manual "Greenhouse read-only check" with only `inspect_widgets` = true
(`--inspect-widgets`). It runs on the revision whose CI passed, and is not retried.

**Widget actions (the only interaction):**
- **Targets:** each combobox present in the DOM at load, in a fixed order:
  - first the 7 that map to API dropdown questions (`q01 q02 q03 q04 q07 q09 q11`);
  - then the 5 unmatched ones (`u1` = the one inside the phone field's group; `u2`–`u5` = the
    4 standalone ones).
  Controls that appear later are counted, never acted on.
- **Per target, two actions:**
  1. open: one click on the combobox itself;
  2. close: one Escape key press on the same combobox.
  It then waits at most 600 ms after each action.
- **Maximum:** 24 actions (12 targets × 2). This is enforced: a widget is never half-done, so
  it is either opened and closed or not touched. Elements without a safe id, or not visible
  and unique, are skipped.
- **Only the target receives the click.** If another element would receive it (an overlay,
  for example), nothing is clicked. The widget is reported as `pointer_intercepted`.
- **Never done:**
  - option selection;
  - typing or text entry;
  - focusing other elements;
  - any other button, link, checkbox or file input;
  - uploads, location searches, form progression, submission;
  - OTP requests or candidate sessions.
  No answer is selected and no candidate data exists in the run.
- **Defences besides "we do not click it":**
  - before the first action a guard cancels and counts any form submission (the `submit`
    event, `form.submit()` and `requestSubmit()`);
  - a file chooser is intercepted and recorded, and no file is ever set;
  - dialogs are dismissed and recorded.

**Destinations and methods: B3's, unchanged, plus one restriction.**

| Destination | Methods | Resource types |
|---|---|---|
| `boards-api.greenhouse.io` | GET | the 3 API requests (robots.txt, job, board) |
| page origin | GET only, 1 navigation | as in B3, **minus every data request type** |
| `job-boards.cdn.greenhouse.io:443` | GET, HEAD | script, stylesheet only |
| `recruiting.cdn.greenhouse.io` and everything else | — | blocked |

- **New restriction for this mode:** every data request (`xhr`, `fetch`, `eventsource`,
  `websocket`, `ping`) is refused before sending. This holds at every origin, the page
  origin included, and for GET too: GET is not assumed harmless.
  - No data endpoint is approved.
  - A widget that needs one stays closed or empty. That is reported as a boundary, never
    unlocked.
- **Already refused at load in B3:** the 4 data requests to the CDN. They stay refused here.
  If dropdown options depend on them, the result will say so: a widget opens without options,
  or a data request is refused during an action.
- **Requests during actions:** counted separately (routed requests, refused data requests by
  type, blocked non-GET). They share the page's 150-request budget.

**Are the three API requests necessary? Yes, for two of the five questions.**
- **What they are needed for:**
  - mapping a control to an API question needs the question labels;
  - "options match the API question" needs the option texts.
  B3's raw API data was destroyed with the stack, as approved. Only anonymous counts were
  retained.
- **Without them:** the inspection could report only:
  - option counts, compared against B3's retained counts (2, 2, 250, 26, 2, 2, 2);
  - required and structure changes.
  It could not say which control is which question.
- **Recommendation:** include them. They are the same 3 GETs as in B2/B3.

**Budgets (enforced, `gh_readonly.Limits`):**

| Budget | Value | When reached |
|---|---|---|
| API requests | 3 | the run stops |
| top-level navigations | 1 | a second one is refused before sending and stops the inspection |
| redirect hops | 3 (same origin) | the run stops |
| page requests (load + actions) | 150 | refused; the run stops |
| received data | 20 MB | **a stop condition, not a transfer cap** |
| retained DOM | 2M characters | the run stops |
| widget actions | 24 | the inspection stops |
| settle per action | 600 ms | — |
| inspection time | 30 s | the inspection stops; the summary is still read |
| observation | 90 s | the run stops |
| whole run | 150 s watchdog (exit 5), plus an outer 200 s kill | the run stops |
| printed output | 256 KiB | larger output is suppressed |

**Stop conditions:** the inspection ends at the first of these. Each is reported with its
reason, never retried, and no further widget is touched:
- a bot challenge;
- a navigation attempt;
- a change of the page address (including history and hash changes);
- a redirect to another origin;
- an attempted submission;
- an attempted non-GET request (e.g. an upload);
- a file chooser;
- a dialog;
- opening a widget changes a value or selects an option;
- the action, time or request budget runs out.
Required-field, visibility, validity, alert and control-count changes are **recorded**, not
stops. A refused data request is recorded, not a stop.

**Output:** anonymous, through the existing allowlist and leak guard. There is:
- no question wording, option text, label, id, URL, host beyond the printable
  `*.greenhouse.io` names, or employer data;
- for widgets, only aliases (`q01…`, `u1…`).

Per widget:
- opened or closed;
- how the list was found (`aria` reference, or the only visible listbox);
- option count;
- whether the options equal the mapped question's (`options_match_api`);
- which API questions have exactly this option list (aliases);
- selections and value changes (must be 0 and false);
- address change;
- required signals kept apart: HTML attribute, ARIA attribute, enclosing group's ARIA
  attribute, label marker;
- structural changes: control, required, hidden, invalid and alert counts; controls added;
- submit attempts, refused data requests, blocked non-GET.

Totals:
- targets, actions and the stop reason;
- whether a location control exists at the end;
- control counts at the end;
- refused data requests at load and during actions, by type;
- requests during actions;
- recorded events.

Option texts are compared inside the worker only. A virtualised list may show fewer options
than it has: then the counts differ and the result says "not equal". Nothing is inferred
from that.

**Retention:** as B3.
- Raw data stays inside the worker container and is destroyed with the stack.
- No artifacts are uploaded.
- Only the guarded summary appears in the run log.

**Tested locally** (`tests/test_widget_inspection.py`, 18 tests, Chromium in its network
namespace behind the egress proxy, fixture mode `gh2_widgets`; widget behaviour is a FIXTURE
ASSUMPTION):
- options become observable on opening with nothing selected;
- the action, time and page-request budgets are enforced;
- a widget-started submission is cancelled, an upload POST is blocked, and a file chooser
  stops the inspection;
- a same-origin GET data request is refused and reported;
- a navigation is refused before sending; an address change, a challenge, a dialog and a
  selection on open each stop the inspection;
- a required-flag change is recorded;
- a widget covered by another element is not clicked at all: it is reported as
  `pointer_intercepted` and the inspection continues;
- the output is anonymous and the guard rejects an unknown string;
- a real page is inspected only under the B3 policy.
The receiver's request log is the oracle in every test: only the page GET reached it.

Compose `s_readonly_widget_inspection_in_container` repeats the normal, data-request, upload
and submission cases through the real runner and session proxy.

**The request (send back, or say no):**

> I approve one widget-inspection run (`inspect_widgets` only) on the existing approved
> posting (secret `GH_READONLY_POSTING`), on the revision whose CI passed. It may make B3's 3
> API GETs and one page load under B3's destinations and methods, with every data request
> refused. It may then open and close each combobox present at load, at most 24 actions in
> total (one click and one Escape per combobox), within the limits above. No option
> selection, typing, upload, location search, OTP, candidate data or submission. Stop
> conditions and retention as listed. Run once; do not retry; report anonymously.

## Replacement widget inspection (authorized 2026-10-21, conditional; run once as manual run #8; authorization used)

- **Condition met:** the fresh-process regression and the explicit outcome are in place,
  and CI passed on the code revision below.
- **Code revision:** `181b7c357652c4403d4cb9e23250758a77262dfc` (`181b7c3`).
  - The run is dispatched from the branch `readonly-inspect-181b7c3`, created at exactly that
    commit and verified through the API before dispatch.
  - It is not run from a moving `main`. The run record's head SHA is checked afterwards.
- **CI #49** ([39543318002](https://github.com/KevinD003/AutoApply/actions/runs/39543318002))
  on `181b7c3`, all four jobs passed:
  - backend: 340 passed, 1 skipped, including `test_readonly_cli_process.py` (3) and
    `test_widget_inspection.py` (20);
  - frontend: full Playwright suite passed;
  - execution-compose: 89 checks, 0 failed;
  - docker-smoke: passed.
- **Scope:** unchanged from the approval above.
  - The 3 API GETs and 1 page navigation.
  - At most 12 dropdowns present at the start, and at most 24 open/close actions (one click
    and one Escape each).
  - B3's destinations and method/resource restrictions; every data request blocked.
  - All budgets; the existing stops, including the immediate filter-failure stop.
  - Anonymous output; raw data destroyed with the stack.
- **How the result is read:**
  - the workflow is green only for outcome `completed`;
  - `policy_stop` (exit 7) means partial evidence;
  - `internal_error` (exit 6) means the check failed;
  - the workflow status is never read as the page-inspection result: the printed `outcome`
    is.

## Diagnostic re-observation — authorized 2026-10-21 for one run; run once as manual run #9 (authorization used)

**Why:** run #8's detector cannot tell "did not open" apart from "opened, but not in a way
it could read" (see the report, "Detector diagnosis after run #8"). The new diagnostics can,
but only on the page itself: run #8's output cannot be reclassified afterwards.

**Is it necessary?**
- To answer the dropdown question: yes.
- For safety: no. The posting stays refused regardless, because of the absent location
  control, the page-managed coordinates and the unexplained `u1`–`u5`, of which `u1` and
  `u2` are required.

**Scope: run #8's, unchanged.**
- **Requests:** the 3 API GETs and 1 page navigation.
- **Destinations and methods:** B3's.
  - `job-boards.cdn.greenhouse.io`: scripts and stylesheets only, GET/HEAD;
  - every data request refused at every origin, GET included;
  - `recruiting.cdn.greenhouse.io` and everything else blocked.
- **Actions:** at most 12 dropdowns present at the start, at most 24 actions. One click on
  the control and one Escape; nothing else.
- **Budgets:**
  - 600 ms per action, sampled 3 times and not extended;
  - 30 s inspection, 90 s observation, 150 s run, 200 s outer kill;
  - 150 requests, 20 MB received (a stop condition, not a cap), 2M characters retained;
  - 256 KiB output.
- **Stops:** as before, including the immediate filter-failure stop.
- **Excluded:** no selection, typing, scrolling of lists, uploads, location search, OTP,
  candidate data or submission.

**What it adds** (reads only): the per-action diagnostics and `open_state`, required signals
for every control (attachments included), and path shapes of the refused data requests.

**How the result would be read:**
- `observed_sufficiently`: compare with the job data.
- `opened_options_not_observable` with data requests refused during that action: the path
  shapes show what was asked. Only if one shape plainly points at the option list would a
  **separate** request be proposed, for that one exact host, method (GET) and path shape.
  Never all CDN data requests.
- `not_opened` with focus on the control: the click does not open these widgets. Any other
  action (a wrapper, a key) is a new action type needing its own approval.
- `undetermined` or `click_failed`: reported as such; no follow-up is implied.

**Pinned revision:** `e1bd9e711f30c550b842280a6d9e3975bdbcb69d` (`e1bd9e7`).
- CI #52 ([39602660714](https://github.com/KevinD003/AutoApply/actions/runs/39602660714)) passed
  all four jobs on it.
- If approved, it would be dispatched from a branch created at exactly that commit and
  verified before dispatch, as for run #8. No branch has been created yet.

## Next decision point — two alternatives, neither authorized

**Update (2026-10-21):** the owner chose A, carried out by the owner in their own browser;
B remains unauthorized (`docs/implementation-status.md`).

Run #9 is the last external activity. Neither path below runs without explicit approval.

### A. Manual structural feedback (recommended first)

- **Who:** you, in your own browser, using `docs/manual-dropdown-checklist.md`. No candidate
  data, no sharing of content.
- **Cost:** no automated access.
- **How the answers would choose the next evidence-backed check** (each strategy is
  fixture-tested only):

| Your answer | What it indicates | Next step it would justify |
|---|---|---|
| A click opens a menu | `click_control` is plausible; run #9's silence then points at something missing in the observed page, such as the refused locale files (Q6) | path B |
| Opens only via a small arrow button | `trigger_button` | a separately approved check of exactly that action |
| Opens only via the keyboard | `arrow_down` | a separately approved check of exactly that action |
| Opens only when typing / typing required | search-as-you-type | none: stays unsupported, like location search |
| Noticeable delay | the 600 ms window may be too short | a separately approved, longer window |
| Dialog or inline pattern | which popup source the detector must read | fixture work first |
| Hundreds of options | likely partial or virtualized rendering | none: stays unsupported (no scrolling) |
| Locale files load in your browser | consistent with the locale-gate hypothesis | path B |

### B. Narrow locale-resource observation (only if A, or your judgement, points at it)

- **Technical basis:** all 11 data requests refused in run #9 have one shape. The widgets
  showed no DOM reaction to clicks. A locale-gated fixture reproduces that signature under
  the same policy. That is consistent with a locale gate, not proof of one.
- **Proposed scope:** run #9's scope, with exactly one exception:

| Item | Value |
|---|---|
| Host | `job-boards.cdn.greenhouse.io:443` only |
| Method | GET only |
| Resource type | `fetch` only |
| Path | `/locales/<segment>/<segment>.json`; each segment 1–32 of `[A-Za-z0-9_-]` |
| Query string | none (a request with any query is refused) |
| Redirects | none followed |
| Everything else | unchanged: other CDN data, fonts, images, other hosts and every other data request refused; no API calls beyond the 3 GETs |
| Actions and limits | run #9's: at most 12 dropdowns, 24 click/Escape actions, all budgets and stops |
| Privacy | locale responses are never retained or printed; only the guarded anonymous summary |
| Excluded | answer selection, typing, uploads, location search, login, OTP, submission |

- **Before such a run:** the exact path rule would have to be implemented and tested, and CI
  passed on a pinned revision. None of that exists yet.
- **What it would answer:** whether the widgets react to a click once their locale files
  load. Opening them would still not mean that filling or submission works.

## Deliverable: the comparison (once A/B are separately approved and run)

| Area | Compared |
|---|---|
| Posting identity | board token, job id, title, and employer name in A2 vs. the page |
| Schema vs. visible controls | every API question vs. every rendered control: present in both, API only, page only |
| Labels, options, required flags | exact match, normalised match, or different |
| Consent | data-compliance flags vs. the consent wording and control actually shown |
| Conditional/dynamic questions | questions that appear or change after load or by answer (observed only at load, since nothing is answered) |
| Uploads | attachment fields, accepted types, upload mechanism visible on the page |
| Unsupported controls and bot checks | controls the extractor cannot map; any challenge script seen |
| Differences from the synthetic fixture | `fixtures/ats_receiver/greenhouse_like.py` assumptions that do not hold, with the fixture changes proposed |

The report lists confirmed observations, differences and unknowns separately. It says what
could not be observed: dynamic questions that need answers, the security-code step,
confirmation pages, and anything needing a denied origin. **Successful extraction is not
evidence of submission compatibility; submission stays unverified and disabled.**

## Approval text for the user (fill in and send)

```
I approve permission A for:
  posting  https://job-boards.greenhouse.io/<BOARD>/jobs/<JOB_ID>
  requests A0, A1, A2 as listed in docs/greenhouse-readonly-compatibility-proposal.md
I approve / do not approve permission B for the same posting, under the listed limits,
  after the B preconditions are implemented and tested.
The posting is public and I am entitled to view it.
Employer terms forbidding automated reading: yes / no / unknown (proceed: yes / no).
The employer may / may not be named in the committed report.
This does not approve disclosing candidate data (C) or submitting an application (D).
```
