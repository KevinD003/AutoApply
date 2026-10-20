# Proposal: first ATS adapter (not started)

Status: **implemented against the local fixture only** (see `docs/greenhouse-adapter.md`).
Nothing has been run against Greenhouse or any real employer, and no real employer or ATS was
contacted. The live pilot gate is `docs/live-pilot-gate.md`. Real destinations stay refused (`execution/policy.py`) until this adapter has its own
capability entry and receiver-style tests. A real pilot additionally needs separate approval of
the employer, the job, the exact data, the disclosure scope and the final submission.

## Choice: Greenhouse hosted application forms, one workflow

**Workflow supported:** a single-page Greenhouse-hosted application form for one job post:
- standard fields (name, email, phone, location);
- resume upload;
- custom questions of the types `input_text`, `textarea`, `input_file`,
  `multi_value_single_select` and `multi_value_multi_select`;
- GDPR consent where the post requires it;
- an optional post-submit email security code, handled through the existing checkpoint.

Nothing else: no candidate login, no multi-step flows, no other ATS.

Why Greenhouse first:
- **Typed schema without scraping.** The public Job Board API returns a post's application
  questions without authentication: `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true`
  ([docs](https://docs.greenhouse.io/job-board.html)).
  - It lists each field's name, type, required flag and options, the location questions and
    `data_compliance` (GDPR consent).
  - That maps directly onto our `FormSchema`, and gives a second, independent fingerprint to
    compare with the rendered form before disclosure.
- **One form shape across employers**, so one adapter covers many destinations.
- **The code wait exists already.** Candidates report an email security code on some boards:
  enter it on the form, then resubmit. Third-party tools also describe it. Our
  `awaiting_code` checkpoint already models this, but it is **not confirmed by official
  Greenhouse documentation**, so it must be verified first.

Not usable: the Job Board API's application POST needs the employer's API key. A candidate-side
tool must use the hosted form in the browser.

## Stop conditions (never guessed, never bypassed)

| Situation | Outcome |
|---|---|
| CAPTCHA or bot challenge shown | stop; `failed_safe` before disclosure, `abandoned` after; never solved or bypassed |
| A field type or question we do not map | checkpoint for the user before approval; nothing sent |
| Demographic / EEO sections | only with explicit per-application consent; default decline |
| Location autocomplete that needs hidden latitude/longitude | only if the values are deterministic; otherwise a checkpoint |
| Rendered form differs from the API schema | stop before disclosure (fingerprint mismatch) |
| No clear confirmation after submit | `unknown`, then reconciliation; never resubmitted automatically |
| Login or account creation (MyGreenhouse) requested | stop; out of scope |

## Implementation order

1. **Fixture first.**
   - Build a Greenhouse-like mode in `fixtures/ats_receiver`, using only the documented
     schema: field names, `question_<id>` keys, the resume plus resume-text pair, location
     fields and the GDPR consent block.
   - Add the security-code-then-resubmit flow.
   - Keep its own ledger as the oracle.
2. **Adapter.** Add `greenhouse_hosted` with a capability entry that stays disabled for real
   origins. Rerun the whole failure matrix against the fixture:
   - duplicate deliveries, crashes at every boundary, dropped responses;
   - readback tampering, mutations, egress and tenancy.
3. **Read-only schema fetch**, behind a separate setting and the same SSRF checks, so packages
   can be prepared for real postings. Still no submission. This is a new outbound integration
   and needs its own approval.
4. **Pilot.** Only after separate approval of the employer, job, data, disclosure scope and
   final submission, with one user, one application, and manual reconciliation.

## To verify before any code

- Greenhouse's terms for automated submission through hosted boards (legal review).
- Whether the security-code step is documented, and its exact shape: resubmit versus a separate
  verify request, code format, expiry.
- Which boards show a CAPTCHA, and at what step.
- How embedded boards (`?gh_jid=` on employer sites) differ from the hosted page.
