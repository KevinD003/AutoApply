# Proposal: read-only Greenhouse compatibility check (not executed, not approved)

Purpose: find out whether the fixture-verified Greenhouse mapping matches one real job post,
**without** sending candidate data. Nothing here has been run. Reviewing documentation is not
legal approval, and public access to job data is not permission to submit applications.

## What is requested, exactly

The user chooses **one** live posting and names its board token and job id. Then:

| # | Request | Purpose | Tool | Separate gate |
|---|---|---|---|---|
| R1 | `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true` | the documented job post JSON: questions, types, options, required flags, data-compliance | backend HTTP client (SSRF checks, no cookies, no credentials, one request) | **Gate A** |
| R2 | `GET https://boards-api.greenhouse.io/v1/boards/{board}` (optional) | confirm the board token and employer name | same | Gate A |
| R3 | load `https://job-boards.greenhouse.io/{board}/jobs/{job_id}` in the isolated browser and read the DOM. No typing, clicking, uploads or scrolling into the form; no cookies kept | compare the rendered form with the JSON and with the fixture's DOM assumptions | browser-runner container, egress allow-list = that host:port only | **Gate B** (actual browsing) |

That is at most three requests (R3 also loads the page's own subresources). Nothing else: no
retries in a loop, no crawling of other jobs, no API keys, no login, no candidate data, no
uploads, no form filling, no CAPTCHA interaction (if one appears, stop), and no submission.

## What would be recorded

- **Field shape:** the posting's question keys, types, required flags and option labels, and
  a diff against our mapping. Question wording stays local in the developer's workspace and is
  not committed.
- **Rendered page:** whether the DOM exposes label/for or ARIA associations our extractor can
  read, how the attachment control works, and whether a CAPTCHA or bot-check script is
  present.
- **Not recorded:** cookies, screenshots, traces or personal data.

## Access conditions and open questions

| Topic | Status |
|---|---|
| Greenhouse documents the Job Board API GET endpoints as public, with no authentication ([docs](https://docs.greenhouse.io/job-board.html)) | documentation read; access terms and rate limits **not verified** |
| Application POST via the Job Board API requires the employer's API key | documentation read: not usable by a candidate tool and not proposed |
| Greenhouse terms of service / acceptable use for automated access to hosted boards | **open**: not reviewed by counsel |
| `robots.txt` of `boards-api.greenhouse.io` and `job-boards.greenhouse.io` | **open**: not fetched in this milestone |
| The employer's own terms for its careers pages | **open** |
| Is automated *reading* of one public post acceptable to the employer? | **open**: needs the user's judgement, and possibly the employer's |
| Is automated *submission* ever acceptable? | out of scope here; see `docs/live-pilot-gate.md` |

## Preconditions before Gate A

- The user names the board token and job id.
- The user states that they are entitled to view that posting (it is public).
- A reviewed code change adds an explicit, off-by-default setting, for example
  `NOEFFORTS_READONLY_GREENHOUSE_HOSTS=["boards-api.greenhouse.io"]`. It enables R1 and R2
  for that one post only; it must not enable submission or browsing.
- Requests go through the existing URL safety checks, have a timeout, and are logged with the
  URL and status only.

## Preconditions before Gate B

- Everything above.
- The browser-runner's Compose execution test passes on the exact host and image used.
- The egress allow-list contains only `job-boards.greenhouse.io:443`; the proxy gets an
  outbound network for this run only.
- The adapter runs in a read-only mode that cannot fill or submit (a separate capability flag,
  off by default), and the code path has its own tests.

## What this does not establish

- Compatibility with other employers, or with the same employer after they change their form.
- That submission would work. Gate B observes the form; it never interacts with it.
