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

**Note on the budget.** A was written as "at most 3 requests in total" and B as "exactly one"
navigation. Runs #2 and #3 each used that budget once more, relying on the user's general
statement. From now on, every further read of the posting needs its own explicit approval
(below). Nothing further has been run.

## Follow-up observation B2 — approval request (not run)

**Status: requested, not approved, not run.** The approval of A and B covered one navigation,
so another page load needs a new approval. It covers **only** a read-only observation.

**Purpose:** find out how this posting's page controls correspond to the job post's fields:
whether each API field has exactly one control, with the same id, a matching label and a
suitable role. Counts alone (run #3) do not show that.

**Requests (same posting, the `GH_READONLY_POSTING` secret unchanged):**

| Step | What | Budget |
|---|---|---|
| A again | robots.txt, job post, board: GETs to `boards-api.greenhouse.io` | 3 GETs (the mapping needs the job data; raw data is not kept between runs) |
| B2 | one page load of the posting in the isolated browser | 1 navigation; at most 150 requests (enforced: further requests are aborted and the run stops); 60 s navigation timeout plus at most 17 s of waiting for the page to settle; the job's 20-minute limit |

**Correction:** B's text promised a 20 MB limit and a 60 s wall clock. The code enforces the
request count and per-operation timeouts, not a byte total or a single wall clock. That applied
to runs #2 and #3 too. B2 is described as the code actually behaves.

**Limits (unchanged from B):**
- allow-list `job-boards.greenhouse.io:443` only, with no expanded domains;
- no clicks, typing, focus, scrolling, uploads or form submission;
- every non-GET request blocked before sending;
- a fresh browser context, with no candidate session or cookies;
- stop at a bot check or an off-origin redirect;
- **no automatic retry**. If the run fails, it is reported, not rerun.

**What is read, after load, without interacting:**
- the serialized DOM;
- computed visibility of each candidate control;
- the text of options already present in each combobox's listbox (compared in the worker; never
  printed).

**Collected, per API field** (printed with custom ids as aliases `q01`…):
- the number of controls whose `id` equals the field name: unique, absent or ambiguous;
- whether the accessible name matches the label (via `aria-labelledby`, `<label for>`,
  wrapping label or `aria-label`), and how many controls carry that label;
- the element and type (`input`/`select`/`textarea`, input type) and the role (e.g.
  `combobox`);
- grouping and ARIA relations: inside a group or fieldset, `aria-controls` → listbox,
  `aria-describedby`;
- hidden (an attribute on the control or an ancestor) vs computed-visible; required attribute
  vs API required;
- for comboboxes: options present at load, and whether they equal the API options;
- a status per field (mapped / absent / ambiguous / type mismatch / label mismatch / search
  picker / page-managed hidden value), listed by status, so absent and ambiguous fields are
  explicit.

**Also collected:**
- page controls that no API field names: element, type, role, labelled, hidden/visible,
  whether it is an API field's text alternative, and the id's shape (never the id itself);
- requests that failed or were denied: resource type, destination kind, same-origin flag and
  the browser's error code, so a missing script or data request shows that rendering may be
  incomplete;
- whether the page reached network idle, and its ready state.

**Not collected:** labels, wording, option text, ids of custom questions, URLs, page text,
screenshots, traces, HTML, response bodies or exception messages.

**What the run sends:**
- ordinary page-loading GET requests to the allowed host, with normal network metadata (runner
  IP address, browser User-Agent, standard headers);
- nothing to denied hosts: the proxy refuses them before resolving them;
- no candidate data and no form submission.

**Output:**
- printed only after the CLI's privacy guard passes it: allowlisted vocabulary, aliases, and a
  scan for values derived from the posting;
- otherwise a refusal is printed (exit 4) and nothing else.

**How it would run, once approved:** Actions → "Greenhouse read-only check (manual)" → Run
workflow with `observe` and `mapping` both checked. The code is in place
(`gh_readonly.mapping_evidence`) and tested against the local v2 fixture. `mapping` defaults
to off.

**What it cannot show:**
- whether filling, combobox selection, uploads or submission work;
- conditional questions that appear only after an answer;
- anything a denied host would have provided.

Successful mapping would still not be evidence of submission compatibility.

**Approval text (send it back edited, or say no):**

```
I approve one more read-only run (A again + B2) for the same posting
(the GH_READONLY_POSTING secret), under the limits in
docs/greenhouse-readonly-compatibility-proposal.md "Follow-up observation B2".
One run only; no automatic retry.
This does not approve disclosing candidate data (C), filling a real page, uploads,
location searches, security-code requests, or submitting an application (D).
```

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
