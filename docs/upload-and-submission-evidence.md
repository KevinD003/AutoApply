# Upload and submission evidence (2026-10-22)

**Status:**
- **Steps 1 to 4 are built and tested on the local fixtures only:** the rehearsal, the page's
  acknowledgement of each upload, readiness reading recorded rehearsal evidence, and the
  rehearsal required before the first submission through each path (see "Order of work"
  below).
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
| Each upload or disclosure | `disclosure` | the field reference; how it was acknowledged, as a fixed value (page: `attachment_shown`, `error_shown` or `none`; API: `digest_matched` or `not_kept`); and the digest of what was sent, which must equal the approved document's SHA-256. Kept for a failed upload too, with every upload before it in the attempt | the file, its name, the page's wording, the page's own attachment id |
| After filling | `readback` | how many answers were checked and how many did not keep their values | which fields (the posting's keys) |
| The form checked again after filling | `recheck` | `{"form": "matched"}`, written only when the form is still the approved one (the API route: its schema read again, for a rehearsal) | the form's fields |
| Blocked requests | `egress` | counts by address category | hosts or URLs |
| The final click | `receipt` | receipt id, confirmation, final origin, HTTP status, confirmation strength | page title, path or text |
| The result | outcome | `confirmed`, `rejected` or `unknown`; for a rehearsal, `rehearsed` (nothing submitted). An unknown outcome is reconciled by the user and never resent | |

A rehearsal ends only through its stop, which repeats every gate check under the same locks
(the approval still live, the content and the execution method unchanged, the destination's
class) and checks that these rows show a complete rehearsal: every approved document uploaded
once with its digest and acknowledged, the readback with no mismatch (the API route: its
draft), the recheck, nothing unresolved (requests the egress controls denied are counted, not
disqualifying). Only then, in
the same commit, it writes a **rehearsal record** (`rehearsal_records`: counts, route, adapter
and version, destination class; nothing that names a host, board, field or file) and ends
`rehearsed`. Otherwise the attempt ends `abandoned`, with a fixed reason code on its event
when the evidence was the problem (`rehearsal_evidence_missing` or
`rehearsal_evidence_inconsistent`), and the gate's own message otherwise. A record holds
only while its evidence rows still agree with it, it is younger than 30 days
(`rehearsal_max_age_days`), its adapter version is the current one, and it is not revoked
(deleting an application's evidence revokes its records).

The receiver's own ledger (`fixtures/ats_receiver`) is the oracle for what reached the
synthetic employer: disclosures, uploads with their digests, and acceptances. None of this
evidence has ever been produced against a real page.

## Evidence classes

Kept apart everywhere (`providers/evidence.py`; the readiness summary lists each with the
conditions it alone can meet and the caller's counts in it).

**Evidence classes** (`tests/test_pilot_readiness.py` fails when this table and the code
disagree):

| Class | What it is | Can meet |
|---|---|---|
| `fixture` | a run against a local, fictional test fixture | nothing |
| `public_doc_expectation` | what public documentation describes; unverified, never seen | nothing |
| `read_only_observation` | a real page seen read-only in an approved run; never filled there | `dropdowns`, `location` |
| `rehearsal` | a real form filled and checked under an approval to disclose only; nothing submitted | `real_upload` |
| `real_submission` | a real final submit with an attempt-bound confirmation | `real_submission` |

A fixture rehearsal is recorded and shown as fixture evidence; it never counts as rehearsal
evidence, however complete. Today every record is a fixture record.

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
3. **Upload evidence that is the page's, not only NoEfforts' (built, fixtures only).** The
   digest sent equals the approved document. The page's acknowledgement of each upload (on
   the fixtures, its status element) is recorded as a fixed value, never as page text or the
   page's own attachment id. An upload the page refuses, or never acknowledges, is recorded
   too, with every upload made before it in the attempt, before the attempt stops: that data
   may already have reached the employer.
4. **Readiness reading it (built, fixtures only).** `real_upload` is met only by a rehearsal
   record that still holds, on a real destination, with an upload, and only while real
   destinations are enabled. Fixture records are shown and never counted. Until real
   destinations are enabled through the gate, it stays not met.

## What is missing for submission evidence

The receipt and outcome evidence above already proves a submission on the fixtures. For a
real destination, three things are missing:

- the submission approval (permission D);
- an attempt on that destination after a recorded rehearsal. That order is enforced (E6,
  built and tested on the fixtures only, `docs/rehearsal-prerequisite.md`): a submission
  through a path needs a valid recorded rehearsal on it first, unless a submission there was
  already confirmed after one;
- the same evidence, held to the same "confirmed only on an attempt-bound confirmation" rule.

What readiness counts as real-submission evidence is a confirmed attempt of class `real` with
an attempt-bound confirmation whose send gate found the rehearsal prerequisite held. None can
exist while real destinations are disabled, so `real_submission` stays not met.

## Order of work (each its own step; fixtures first)

1. **Done, fixtures only:** the rehearsal on the fixtures, a disclosure-only approval and the
   rehearsal stop.
   - The receiver's ledger shows the upload, with the approved document's digest, and
     **0 acceptances** (`tests/test_rehearsal.py`, `frontend/e2e/submission.spec.ts`).
   - The review page offers the rehearsal approval and shows its result.
2. **Done, fixtures only:**
   - the page's acknowledgement of an upload recorded as a fixed value (item 3 above);
   - the review page and the tracker showing a rehearsal's result
     (`tests/test_upload_evidence.py`, `tests/test_rehearsal.py`,
     `frontend/e2e/submission.spec.ts`).
3. **Done, fixtures only:** the rehearsal stop as a gate, the rehearsal record, and readiness
   reading the caller's recorded evidence by class (`tests/test_rehearsal_stop.py`,
   `tests/test_pilot_readiness.py`). It still shows the real conditions not met, because no
   real destination is enabled.
4. **Done, fixtures only (E6):** a recorded, valid rehearsal required before the first
   submission through each employer/provider path, at five layers
   (`docs/rehearsal-prerequisite.md`, `tests/test_rehearsal_prerequisite.py`,
   `tests/test_rehearsal_codes.py`, `frontend/e2e/rehearsal-prerequisite.spec.ts`).

None of these steps enables a real destination, relaxes the disclosure or submission
permissions, or approves a pilot. Each of those remains the owner's decision through the gate.
