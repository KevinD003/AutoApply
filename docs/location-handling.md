# Location questions without hidden coordinates (design, 2026-10-22)

**Status: design only.** Nothing here changes behaviour. A posting with a location question
that NoEfforts cannot answer through a visible, evidence-backed control stays a checkpoint:
the user completes the application on the employer's site. No page was visited for this
document.

## The problem

- **The real posting, observed read-only** (`docs/greenhouse-compatibility-report.md`, runs
  #3–#9): the job data asks a required `location` question plus required hidden `latitude`
  and `longitude`. No location control was found on the page at load. The coordinates are
  page-managed: whatever sets them is the page's own logic, not a field a person types into.
- **The local fixture** (`LOC_JOB` on the v2 fixture, a FIXTURE ASSUMPTION): a search picker
  that searches as you type and fills the hidden coordinates. The id-mapping extractor
  recognises it as a search picker and captures the question as unsupported.

## Rules that do not change

- **Hidden coordinates are never written.** They are page-managed values, and writing them
  would assert a place the page did not choose.
- **Nothing is typed into a search picker** to make it offer results, and no result is chosen
  from a list that typing produced. Search-as-you-type selection is unsupported by policy
  (`execution/adapters/dropdowns.py`, `CAPABILITIES`).
- **Facts and preferences stay apart.** A location question could ask where the candidate
  lives (a fact: the profile's residence, user-approved), or where they want to work (a
  preference: targets). Its meaning is never inferred. A question whose meaning is not clearly
  one of them is a checkpoint, never a guess. This is the same rule as
  `test_residence_and_target_location_stay_separate`.
- **Unknown stays unknown.** Without the profile's approved residence, there is nothing to
  answer with.

## What NoEfforts does today (tested)

- A search picker is captured as an unsupported question, never typed into
  (`test_text_question_rendered_as_search_picker_is_unsupported_not_typed`).
- The location posting's route is a **checkpoint** before anything is disclosed, the hidden
  coordinates stay unresolved, and the package cannot be approved
  (`test_location_job_is_a_checkpoint`,
  `test_an_unsupported_required_control_is_a_checkpoint_before_disclosure`).
- The pilot-readiness condition `location` is not met (`providers/readiness.py`).

## Options, and the evidence each would need

| Option | What it would do | Allowed? | Evidence needed before any code |
|---|---|---|---|
| A visible plain-text location control | Fill it with the profile's approved residence city, only if the question is clearly about where the candidate lives, and only when no hidden coordinate is required alongside it | Possible later | A read-only observation showing such a control, labelled like the job-data question, and the coordinates optional or absent in that form; a fixture that mirrors it; mapping and readback tests; then `location_picker` raised from `none` only with its own reviewed evidence |
| The page's own search picker | Type a place, wait for results, choose one, let the page set the coordinates | No: search-as-you-type is unsupported by policy | Would need a policy change by the owner. It is a materially different strategy: typing into a third-party widget and choosing from results NoEfforts did not produce |
| A user-assisted step inside an automated attempt | Pause the attempt, let the user choose the location in the isolated browser, then continue | No: there is no way for a person to act inside the isolated browser, and a hand-over mid-attempt mixes disclosure boundaries | Would need its own design for a disclosure boundary per step, and the owner's approval |
| An authorized API that accepts a location without coordinates | Send the approved location as text through an employer-authorized API | Only with a real authorized API, which does not exist for candidates on this ATS | The employer's authorization and documentation; the API route's own capability entry |

## Decision for now

Location postings stay a checkpoint. The only option that could change that without a change
of policy is the visible plain-text control, and only with the evidence in its row. Until
then, nothing in this document is implemented. Path A (`docs/manual-dropdown-checklist.md`)
does not ask about location, and would not count as evidence for it.
