# Greenhouse readiness gap (handoff, 2026-10-21)

**Status:** Greenhouse fixture support exists. One real posting has been structurally observed,
but real filling and submission remain disabled.

This is not a claim that Greenhouse is supported. Everything marked "real page" is from one
anonymous public posting, observed read-only at load, with clicks and Escapes on its dropdowns
only (runs #9 and #10). No candidate data, typing, selection, upload, login, verification code or
submission has ever been sent to a real page.

Primary evidence: `docs/greenhouse-compatibility-report.md` (runs #3–#10);
`docs/evidence-matrix.md` (fixture tests); `docs/provider-architecture.md` §8.

## Support matrix

| Capability | Status | Evidence level | Safe behavior |
|---|---|---|---|
| Field identification | Partial | Real page | Map only unique controls |
| Text field filling | Fixture-tested | Local fixture | Do not enable on real page yet |
| File uploads | Fixture-tested | Local fixture | Do not enable on real page yet |
| Attachments mapping | Partial | Real page structure | Require approved file/version |
| Dropdowns | Unknown | Real page inspection inconclusive | Stop and require manual action |
| Location picker | Unsupported on real pages; a local stand-in only (D104) | Real page structure; stand-in: local fixture | Stop and require manual action |
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
  - Run #10 (path B, 1.5 s): no locale file was allowed, because all 12 real requests failed the
    rule's path element. 6 of the 7 dropdowns reached were `not_opened`. `q11` showed only a
    class-name hint, and the page tried a POST to another Greenhouse host, which was blocked and
    stopped the run. Whether the lists wait on the locale files was not tested.
  - Strategies (D31) are fixture-only: `tests/test_dropdown_strategies.py`.
- **Location picker.** The job data asks for `location` plus required hidden `latitude` and
  `longitude`. No location control was found on the page, and the coordinates are
  page-managed. The rule is `test_location_job_is_a_checkpoint`. D104 handles a local
  stand-in of a location search only (`docs/location-handling.md`, D104 section); it is not
  evidence for the real page.
- **Unknown required controls.** `u1`–`u5` are dropdown-like controls that match no
  job-data question. `u1` (inside the phone group) and `u2` are required. Their purpose is not
  inferred. D104's phone country picker is a local stand-in of one possible structure only;
  it does not say what `u1` is.
  - On the local fixture, such a control is captured as a blocking field, so the route is a
    checkpoint and the package cannot be approved before anything is queued
    (`test_unlisted_dropdowns_are_a_checkpoint_from_capture`).
  - One that appears only after approval stops the attempt before disclosure
    (`test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure`).
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
- D104, on local stand-ins only: a phone country picker (chosen by a unique calling code, or by
  you), a location search (the exact suggestion, coordinates set by the page), and dropdown
  lists that arrive late (a bounded wait, settled and exact).

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
   coordinates. Otherwise postings with that question stay a manual handoff. The options and
   the evidence each would need are in `docs/location-handling.md` (design only).
4. **Real upload evidence:** attachments uploaded to a real form, proven on their own (an
   upload is a disclosure: the document reaches the employer before any submit). What that
   evidence would be is in `docs/upload-and-submission-evidence.md`. The rehearsal it needs
   (an approval to disclose only) exists and is tested on the local fixtures only; it has never
   run against a real page. Its stop repeats every gate check and records what it proved, and
   readiness counts such a record only while it still holds and only for a real destination.
5. **Real submission evidence:** a real final submit and its confirmation, proven separately
   from uploads. A submission through a new path needs a valid recorded rehearsal on that path
   first (E6, `docs/rehearsal-prerequisite.md`; built on the fixtures only), and readiness counts
   a real submission only if its send gate found that prerequisite held.
6. **The gate in `docs/live-pilot-gate.md`:** you name the posting, the data to disclose and
   the stop conditions, and give separate yes/no permissions for disclosure (C) and
   submission (D). The isolation requirements must hold.
7. **A capability entry raised from `fixture` to `observed`** for exactly the capabilities
   used, with a reviewed change to `real_destinations`. This is never done to claim progress.

**Status** (computed by `providers/readiness.py` from recorded evidence, for the pilot adapter
`greenhouse_live` (D106), and served at `GET /api/providers/greenhouse_live/readiness`.
Before D106 it was computed for `greenhouse_dom`, the fixture-only rules the pilot applies. That
provider never runs on a real destination, so conditions 4, 5 and 7 could never have been met
there. `GET /api/providers/greenhouse_dom/readiness` still serves that provider's own checklist.
The table is the baseline, with no user's records read; the endpoint also counts the signed-in
user's own records for that adapter by evidence class. Each condition also carries what it needs
next (`path`: needs, why, next action, what NoEfforts can do, what the owner must do, what stops a
real attempt meanwhile, which tests verify it). `docs/activation-status.md` lists the same per
condition. `tests/test_pilot_readiness.py` fails when this table and the code disagree):

| Condition | Status | Evidence |
|---|---|---|
| `dropdowns` | not met | run #11 (read-only, locale files loaded): 12 of 12 opened at the control's click, 11 lists read, the 7 mapped ones equal to their job data; a required one (`u3`) had no readable options; the pilot still refuses the locale files; `custom_dropdowns` is `fixture` for the pilot |
| `unmatched_required_controls` | not met | run #11: `u1` (required, phone group) a 244-option list, `u3` (required) no readable options; no mapping rule for either on a real page (D104's phone country rule runs on local stand-ins only) |
| `location` | not met | the pilot has no `location_picker` (D104's search is a local stand-in only, refused on a real page) |
| `real_upload` | not met | `file_upload` is `fixture`; met only by a rehearsal record that still holds on a real destination; none can exist: permissions 1-3 are not recorded |
| `real_submission` | not met | `final_submit` is `fixture`; met only by a real submission with an attempt-bound confirmation after the rehearsal prerequisite held; permission 4 is not recorded |
| `pilot_gate` | not met | recorded in `app/core/authorizations.py`: none; missing: read, open, disclose, submit |
| `capability_entry` | not met | part 1 done: the pilot's reviewed real-destination entry (D102); part 2 not: deterministic_fill, custom_dropdowns, file_upload, final_submit and confirmation_detection are still at fixture |

- A condition is met only by evidence of its own kind: a capability level the registry records
  (reaching `observed` needs an approved read-only run), the gate's separate permissions, or,
  for `real_upload` and `real_submission`, `real_destinations` together with recorded evidence
  of their own class. The five evidence classes (fixture, public-doc expectation, read-only
  observation, rehearsal, real submission) are kept apart:
  `docs/upload-and-submission-evidence.md` ("Evidence classes"). Fixture evidence meets
  nothing.
- **Path A** (the optional manual check, `docs/manual-dropdown-checklist.md`) is recorded in
  `docs/evidence/path-a.json` as fixed choices only (`providers/path_a.py`). It is shown beside
  the conditions it bears on and meets none of them. Until the owner answers, the record says
  `pending`; NoEfforts never fills it in.
- **On the admission ladder** (I2, `docs/provider-admission.md`): each condition is required at
  the stage whose evidence can first meet it. `dropdowns`, `unmatched_required_controls` and
  `location` before `rehearsal_ready`; `real_upload` only for `rehearsed`; `real_submission`,
  `pilot_gate` and `capability_entry` only for `live`. So a rehearsal is never asked to wait
  for evidence only a rehearsal or a submission can produce. For `dropdowns` and `location`
  admission is stricter than this table: it also needs a behaviour credit from a recorded
  read-only run, and the runs so far credit the dropdowns as structure only. `greenhouse_dom` is
  admitted to `observed_read_only`; the conditions and this table are unchanged (the gate
  permission is recorded as two values, C and D, both false; the condition needs both).

## Rule for any future real-page request

No identical dropdown observation will be requested again. Run #9 already answered what a
click plus a 600 ms wait can show. A future request must differ materially and state which
question it can answer that run #9 could not. The candidates already written up, neither
authorized, are:

- **A:** your manual structural feedback (`docs/manual-dropdown-checklist.md`). No automated
  access.
- **B:** run #9's scope with only the locale JSON files permitted, with the adapter's 1500 ms
  settle window. Approved once and run as run #10 on 2026-11-01 (D107). Its exact rule allowed
  none of the real locale files, so it did not answer whether the widgets wait on them. The
  summary now names which properties of a refused path failed. A rule that fits the real paths,
  and running it, would each need their own review and approval. Readiness is unchanged
  (0 of 7).

See "Next decision point" in `docs/greenhouse-readonly-compatibility-proposal.md`.
