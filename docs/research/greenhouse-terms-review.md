# Greenhouse: public documentation and terms review (D102, 2026-10-31)

**Who and why.** A review of Greenhouse's public documentation and terms, made by me (the
assistant building NoEfforts under the owner's standing authorization) when the owner asked, on
2026-10-31, for applications to Greenhouse-hosted job boards to be automated. Recorded as
`providers/evidence.py` `DOC_REVIEWS` → `("greenhouse", "D102")`. It is not legal advice and not
the owner's acceptance of anything (D91: "a review of public terms would be mine, recorded as
such"). The owner decides whether to switch the Greenhouse pilot on.

## Sources read (2026-10-31)

| Source | What it says that matters here |
|---|---|
| Greenhouse privacy policy, `https://www.greenhouse.com/privacy-policy` | "This Privacy Policy does not apply to the Personal Information collected and used by Greenhouse customers, such as when you apply to a job via a Greenhouse-hosted job board." An application on a hosted board is handled by the employer (Greenhouse's customer), under the employer's own notice. |
| Greenhouse legal index, `https://www.greenhouse.com/legal` | Lists the privacy policy, a bias-audit statement, a cookie notice, a CCPA notice for people applying to Greenhouse itself, the master subscription agreement and data processing addendum (both between Greenhouse and its customers) and subprocessors. **No terms of use for candidates using hosted job boards are listed.** |
| MyGreenhouse User Agreement, `https://my.greenhouse.io/users/agreement` (effective 29 January 2025) | Governs MyGreenhouse accounts (the candidate portal). The user agrees to "provide accurate information" and not to "(v) override any security features or bypass or circumvent any access controls or use limits of the Services" nor "(z) use automated means, including spiders, robots, crawlers, or similar means or processes to access or use the Services". "Services" is MyGreenhouse. |
| Greenhouse Job Board API documentation (`github.com/grnhse/greenhouse-api-docs`, read for D95; `docs/research/job-board-apis.md`) | The job post endpoint `GET /v1/boards/{board}/jobs/{id}?questions=true` is public (no key). Submitting an application through the API needs the employer's API key: it is for employers, not candidates. |
| `boards-api.greenhouse.io/robots.txt` (read in owner-approved read-only runs, `docs/greenhouse-compatibility-report.md`) | Did not disallow the job post path. |

## What follows for NoEfforts

1. **No Greenhouse candidate terms were found for applying on a hosted job board.** The
   employer is the one the candidate deals with there; each employer may publish its own
   applicant notice (usually linked from its board). NoEfforts cannot review every employer's
   notice; the owner applies to each employer as themselves, with their own approval of each
   application.
2. **Greenhouse forbids automated use of MyGreenhouse.** NoEfforts never uses MyGreenhouse: the
   pilot's browser has no account, no cookies and no sign-in, and a login or account page stops
   an attempt (a fixed stop condition, `docs/live-pilot-gate.md` §5). This is a clear signal of
   Greenhouse's stance on automation in its own candidate product; it does not by its terms
   cover anonymous hosted job boards, but Greenhouse or an employer may still refuse or flag
   automated applications. NoEfforts never bypasses a check: a CAPTCHA or bot check stops the
   attempt and hands it to you.
3. **Accuracy.** Every answer sent is one you approved, from facts you approved; nothing is
   inferred (CLAUDE.md). This matches the one obligation every source shares: accurate
   information about yourself.
4. **Reading.** The pilot reads only the job post's public data (Job Board API) and its page,
   where robots.txt allows it, one job post at a time when you capture it: GETs to Greenhouse's
   own hosts, nothing of yours sent.
5. **Applying.** One application per job, after your approval of that exact package, the first
   to each employer a rehearsal that never submits, at most one final click and never a retry
   after it (an uncertain result is quarantined for you to reconcile).

## Not reviewed

- Each employer's own applicant privacy notice or terms.
- Greenhouse's developer documentation site itself (`developers.greenhouse.io` was unreachable
  from the build environment in D95; its repository was read instead).
- Any jurisdiction's law on automated applications. Not legal advice.
