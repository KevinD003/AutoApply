# Greenhouse readiness gap (handoff, 2026-10-21)

**Status:** Greenhouse fixture support exists. One real posting has been structurally observed,
but real filling and submission remain disabled.

This is not a claim that Greenhouse is supported. Everything marked "real page" is from one
anonymous public posting, observed read-only at load, with clicks and Escapes on its dropdowns
only (run #9). No candidate data, typing, selection, upload, login, verification code or
submission has ever been sent to a real page.

Primary evidence: `docs/greenhouse-compatibility-report.md` (runs #3–#9);
`docs/evidence-matrix.md` (fixture tests); `docs/provider-architecture.md` §8.

## Support matrix

| Capability | Status | Evidence level | Safe behavior |
|---|---|---|---|
| Field identification | Partial | Real page | Map only unique controls |
| Text field filling | Fixture-tested | Local fixture | Do not enable on real page yet |
| File uploads | Fixture-tested | Local fixture | Do not enable on real page yet |
| Attachments mapping | Partial | Real page structure | Require approved file/version |
| Dropdowns | Unknown | Real page inspection inconclusive | Stop and require manual action |
| Location picker | Unsupported | Real page structure | Stop and require manual action |
| Unknown required controls | Unsupported | Real page structure | Stop and require manual action |
| CAPTCHA | Manual handoff only | Policy | Never solve or bypass |
| Verification code | Fixture-tested | Local fixture | Require manual checkpoint |
| Submission | Not authorized / unproven | None | Disabled for real origins |

Where each row's evidence lives:

- **Field identification.**
  - Real-page mapping: report, "Diagnostic re-observation (run #9)": 19 of 19 mapped fields
    `consistent`.
  - Fixture rule (one unique, labelled, type-suited control per field):
    `test_every_api_field_maps_to_exactly_one_labelled_control` and
    `test_ambiguous_or_mismatched_mappings_are_rejected`.
- **Text field filling:** `test_full_run_sends_exactly_the_approved_values` (v2 fixture, with
  readback). No real page has been typed into.
- **File uploads:** `test_full_run_with_group_named_attachments`; the upload digest is checked
  at the receiver. Nothing has been uploaded to a real page.
- **Attachments mapping.**
  - Runs #8 and #9: `resume` and `cover_letter` matched through their labelled groups. `resume` is
    required by its group; `cover_letter` is optional.
  - Rule: `test_attachment_group_must_be_named_exactly_and_hold_one_file_input`.
  - A file is sent only if it is in the approved package (sha256-bound).
- **Dropdowns.**
  - Run #9: all 12 `not_opened`, meaning no opening evidence within 600 ms of a click on the
    control, and 0 DOM change.
  - Strategies (D31) are fixture-only: `tests/test_dropdown_strategies.py`.
- **Location picker.** The job data asks for `location` plus required hidden `latitude` and
  `longitude`. No location control was found on the page, and the coordinates are
  page-managed. The rule is `test_location_job_is_a_checkpoint`.
- **Unknown required controls.** `u1`–`u5` are dropdown-like controls that match no
  job-data question. `u1` (inside the phone group) and `u2` are required. Their purpose is not
  inferred.
- **CAPTCHA.**
  - `test_captcha_stops_before_anything_is_disclosed`.
  - Policy: `providers/checkpoints.py`.
  - No challenge was seen in runs #3–#9.
- **Verification code:** `test_security_code_wrong_then_right` (first fixture; the emailed-code
  step is the fixture's own design). The code is entered manually by the user.
- **Submission:** fixture only. `real_destinations` is false, and real origins route to a
  manual handoff (`test_real_destinations_go_to_a_manual_handoff`).

## Confirmed on a real read-only page (one posting)

- **Job post JSON:** 22 fields, 19 required. Every type is handled by the mapper; `latitude`
  and `longitude` are unsupported. (Run #3.)
- **Page controls:** they have ids but no `name` (runs #3, #4). The current DOM mapper maps
  the fields uniquely. The 2 attachments match through their labelled groups (first in run
  #8, again in #9). All 19 mapped fields have a consistent required state (run #9).
- **Required state:** carried by `aria-required` plus a label marker, never by HTML
  `required`. The résumé's requirement is on its group. (Run #9.)
- **Dropdowns:** 12 ARIA comboboxes (`aria-haspopup`, `aria-autocomplete="list"`) with no
  options in the DOM at load and no reaction to a click within 600 ms. (Runs #8, #9.)
- **Unmatched controls:** 5 dropdown-like controls (`u1`–`u5`), 2 of them required.
- **No location control** at load, even though the job data requires one.
- **Refused requests:** 11 data requests were refused, all `GET /locales/*/*.json`. Whether
  they carry option data is not proven.
- **Bot checks:** none seen, and no non-GET request was attempted by the page during
  observation.

## Confirmed only on fixtures

- Filling text, email, phone and textarea fields, with readback.
- Selecting from a combobox by the exact approved label.
- Uploads with digest check.
- Group-named attachments.
- The emailed security code.
- CAPTCHA stop.
- Drift detection before disclosure.
- Outcome classification (confirmed, rejected, unknown) with no resend.
- The D31 dropdown strategies (click, ArrowDown, single trigger).

## Assumed fixture behavior (never seen on a real page)

- How a combobox opens and how its options are rendered and selected.
- Option values.
- The upload endpoint and status element, and attachment ids.
- JSON submission to the form's submit path, the confirmation message, and redirects.
- The security-code step.
- Condition triggers (which answer reveals which question).

## Unknown or unsupported real-page behavior

- **Unknown:**
  - whether and how the dropdowns open (another element, a key press, a longer delay, or the
    refused locale files);
  - their options;
  - what `u1`–`u5` ask;
  - how the page sets the coordinates;
  - upload, validation and submission behavior;
  - confirmation;
  - whether a challenge appears when submitting.
- **Unsupported by policy:**
  - location search pickers and hidden coordinates;
  - search-as-you-type selection;
  - virtualized or partial option lists;
  - multi-page or login-gated forms;
  - CAPTCHA solving.

## Before a live filling pilot can be proposed

1. **Dropdowns:** evidence that each required dropdown opens through one bounded,
   fixture-tested strategy, with a complete list equal to the job data's options. Otherwise
   that posting stays a manual handoff.
2. **`u1` and `u2`:** they are understood and either mapped by evidence, or the posting stays
   refused. Their purpose is never guessed.
3. **Location:** a supported, evidence-backed way to set the location without writing hidden
   coordinates. Otherwise postings with that question stay a manual handoff.
4. **Real upload evidence:** attachments uploaded to a real form, proven on their own (an
   upload is a disclosure: the document reaches the employer before any submit).
5. **Real submission evidence:** a real final submit and its confirmation, proven separately
   from uploads.
6. **The gate in `docs/live-pilot-gate.md`:** you name the posting, the data to disclose and
   the stop conditions, and give separate yes/no permissions for disclosure (C) and
   submission (D). The isolation requirements must hold.
7. **A capability entry raised from `fixture` to `observed`** for exactly the capabilities
   used, with a reviewed change to `real_destinations`. This is never done to claim progress.

## Rule for any future real-page request

No identical dropdown observation will be requested again. Run #9 already answered what a
click plus a 600 ms wait can show. A future request must differ materially and state which
question it can answer that run #9 could not. The candidates already written up, neither
authorized, are:

- **A:** your manual structural feedback (`docs/manual-dropdown-checklist.md`). No automated
  access.
- **B:** run #9's scope with only the locale JSON files permitted. This tests whether the
  widgets are waiting on them.

See "Next decision point" in `docs/greenhouse-readonly-compatibility-proposal.md`.
