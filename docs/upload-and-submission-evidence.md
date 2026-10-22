# Upload and submission evidence (2026-10-22)

**Status:**
- **Step 1 is built and tested on the local fixtures only:** the rehearsal (see "Order of
  work" below).
- **The rest is design.**
- **Nothing here is enabled for a real destination.**

This document describes the evidence a future, separately approved pilot would have to
produce for two of the conditions in `docs/greenhouse-readiness-gap.md`:
- real upload evidence (`real_upload`);
- real submission evidence (`real_submission`).

Neither is met (`providers/readiness.py`), and neither can be while `real_destinations` is
false.

## Why two kinds of evidence

The live-pilot gate (`docs/live-pilot-gate.md`, §2) separates the user's permissions:

- **permission 3, "C" (disclosure):** filling the form. An attachment uploads when it is
  chosen, so a résumé reaches the employer before any submit, and a page that autosaves may
  receive typed values too;
- **permission 4, "D" (submission):** the final click, once.

Permission C never implies D. So upload evidence has to be proven on its own, by an attempt
that discloses and then stops, before any submission is attempted.

## What every attempt records today (fixtures, tested)

| Step | Evidence | Kept | Never kept |
|---|---|---|---|
| Each upload or disclosure | `disclosure` | the field reference, the upload id and the digest of what was sent, which must equal the approved document's SHA-256 | the file, its name, the page's wording |
| After filling | `readback` | how many answers were checked and how many did not keep their values | which fields (the posting's keys) |
| Blocked requests | `egress` | counts by address category | hosts or URLs |
| The final click | `receipt` | receipt id, confirmation, final origin, HTTP status, confirmation strength | page title, path or text |
| The result | outcome | `confirmed`, `rejected` or `unknown`; for a rehearsal, `rehearsed` (nothing submitted). An unknown outcome is reconciled by the user and never resent | |

The receiver's own ledger (`fixtures/ats_receiver`) is the oracle for what reached the
synthetic employer: disclosures, uploads with their digests, and acceptances. None of this
evidence has ever been produced against a real page.

## What is missing for upload evidence proven on its own

1. **A disclosure-only approval (built, fixtures only).** An approval has a scope:
   - `submit`: the default, and what every earlier approval meant;
   - `disclose_only`: permits filling, uploads and the checks, never the final click.

   The scope is fixed when the approval is given and bound to the same package version,
   content hash and adapter version as any approval. Approving with another scope while an
   approval is active is refused: the user revokes first.
2. **A rehearsal stop (built, fixtures only).** An attempt approved for disclosure only runs
   exactly as one approved to submit, up to the send gate: the disclosure gate, filling,
   uploads, readback, and the form re-checked after filling. It then ends `rehearsed`, which
   says nothing was submitted. The application waits for the user.
   - It is never retried and never continues into a submit.
   - The send gate refuses any approval that is not `submit`. The runner's stop and this
     refusal are each tested with the other bypassed or removed.
   - The rehearsal uses its approval up, in the same transaction that ends the attempt.
     Submitting afterwards needs an approval to submit and a new attempt, which repeats every
     check.
3. **Upload evidence that is the page's, not only NoEfforts'.** The digest sent equals the
   approved document. In addition, the page's own acknowledgement of the upload (on the
   fixture, its status element) is recorded as a fixed outcome, never as page text.
4. **Readiness reading it.** `real_upload` would be met only by such evidence from a real
   destination. Until real destinations are enabled through the gate, it stays not met.

## What is missing for submission evidence

The receipt and outcome evidence above already proves a submission on the fixtures. For a
real destination, three things are missing:

- the submission approval (permission D);
- an attempt on that destination after a recorded rehearsal;
- the same evidence, held to the same "confirmed only on an attempt-bound confirmation" rule.

`real_submission` stays not met until that evidence exists.

## Order of work (each its own step; fixtures first)

1. **Done, fixtures only:** the rehearsal on the fixtures, a disclosure-only approval and the
   rehearsal stop.
   - The receiver's ledger shows the upload, with the approved document's digest, and
     **0 acceptances** (`tests/test_rehearsal.py`, `frontend/e2e/submission.spec.ts`).
   - The review page offers the rehearsal approval and shows its result.
2. The tracker showing a rehearsal's result, and the page's own acknowledgement of an upload
   recorded as a fixed outcome (item 3 above).
3. Readiness reading recorded rehearsal and submission evidence. It still shows them not met
   for real, because no real destination is enabled.

None of these steps enables a real destination, relaxes the disclosure or submission
permissions, or approves a pilot. Each of those remains the owner's decision through the gate.
