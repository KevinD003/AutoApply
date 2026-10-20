# Read-only Greenhouse compatibility check — approval request

**Status: pending.** It waits for the user to name one public posting. Nothing here has been
run. No posting was chosen on the user's behalf, and no Greenhouse or employer URL has been
requested.

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
