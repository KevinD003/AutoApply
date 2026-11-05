# Greenhouse section-free path: live handoff (prepared, not executed)

**Status: prepared.** This authorizes nothing. It states what is operational locally for a
Greenhouse application that has **no** Education/Employment structured section (the common case,
and the shape of the one real form the owner shared on 2026-11-05), the exact evidence still
missing before a real run, and the single narrowest live request that would close it. The one
activation guide remains `docs/activation-status.md`; this is a focused addendum for this path and
does not restate or change it.

The owner-supplied DOM snapshot is one closed-state observation. It does **not** by itself
authorize any new browser access or disclosure, and it is not proof of general Greenhouse coverage.

## What is operational locally (synthetic stand-ins; receiver-ledger proven)

| Capability | State | Evidence |
|---|---|---|
| Identity: a locked, pre-filled email is verified before disclosure | **new (D129)** | `test_greenhouse_controls.py::test_a_locked_prefilled_email_that_{matches,differs,...}` — match → trusted + submitted (never overwritten); mismatch → refused before disclosure; locked-empty required → refused |
| Approved document upload (résumé/cover letter), byte-identical | reused (D116) | `_attach` binds the sha256-verified approved bytes; the receiver records the content digest; ack checked; no retry after disclosure |
| Approved answers + profile links (e.g. LinkedIn `question_<digits>`) | reused | the resolver fills a link from the profile's host-matched link (exactly one, or a checkpoint), not the answer bank |
| Self-identification / EEO (owner's own stated labels, opt-in) | reused (D122) | standing consent fills only an exact option match; never overrides a per-application choice; never replaces a per-application disclosure consent for other sensitive questions |
| Phone-country picker | stand-in only (D104) | exact calling-code match or checkpoint; shared `+1` → checkpoint; never from residence |
| Unknown/unexpected required controls | reused | become blocking checkpoints at capture and stop the attempt before disclosure |
| Real destinations | **refused** | `real_destinations: false`; the pilot (`greenhouse_live`) is the only real path, behind the gates below |

## The remaining evidence gap (what is unobserved, never invented)

For a real section-free posting, the gaps are the real **react-select** controls whose option list
the closed-state snapshot does not show, and the first real rehearsal/submission evidence. Mapped to
`providers/readiness.py` (greenhouse_live: 1 of 7 met):

- **Phone-country / EEO option lists (readiness #2, `u1`).** The real controls are react-select with
  unstable `react-select-N-input` ids and a listbox that renders only when opened; their options are
  not in the snapshot. A private, in-app read of the opened options (permission 2, a browser
  capture not yet built) is needed. Until then these fail closed (checkpoint) — never a wrong fill.
- **Required dropdowns open and read completely (readiness #1).** Fixture-only; needs one real
  rehearsal on a posting whose required lists are readable.
- **Real upload evidence (readiness #4)** and **real submission evidence (readiness #5).** Need one
  disclosure-only rehearsal, then (separately) one confirmed submit, on the chosen posting.
- **Capabilities raised fixture → observed (readiness #7).** A reviewed change *after* the evidence,
  never before.

A section-free posting that happens to have **no** phone-country/location/required-dropdown controls
(e.g. the owner's shared form, whose phone is optional) may need only #4/#5 — the first rehearsal
and submit — not the react-select observation. The posting choice decides which gaps apply.

## Current operational permissions, budget and expiry (verify before any run; never silently renew)

From `docs/activation-status.md` and `backend/app/core/authorizations.py`:

- **Operational consent (D112)** covers all four pilot steps (1 read, 2 open, 3 disclose, 4 submit),
  **until 2026-11-06**, **at most 5 attempts** past the disclosure gate. Today is 2026-11-05, so it
  lapses on its own tomorrow or at the fifth attempt. It must be **renewed in writing** when it
  lapses; this handoff does not renew it.
- **Per-application approval** binds one package (version, content hash, destination) with scope
  `rehearsal` (disclose-only) or `submit once`, and expires. A submit needs a prior held rehearsal
  on that employer path.
- Read / open / disclosure-rehearsal / final-submit stay **distinct**, each gated separately.

## The single narrowest live request (to prepare for the owner, when they choose)

> On **one** owner-selected real Greenhouse **section-free** posting, under the existing D112
> operational consent (or its written renewal if lapsed): perform steps 1–3 only — read the post,
> open the page, and run **one disclosure-only rehearsal** (scope `rehearsal`) — to record the first
> real upload evidence (#4) and, if the posting has a react-select phone-country/EEO control, to read
> its opened option list (#2). **No submission.** Submission (step 4, scope `submit once`) is a
> separate, later request, only after that path's rehearsal holds.

Nothing above runs until the owner records the permission and chooses the posting. No real employer
interaction is authorized by this document.
