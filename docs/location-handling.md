# Location questions without hidden coordinates (design, 2026-10-22; D104, 2026-10-31)

**Status (D104, 2026-10-31): a local stand-in is supported; every real page stays a
checkpoint.** The owner's instruction of 2026-10-31 ("Proceed with local stand-ins for … Location
search") is the policy change the "page's own search picker" row below asked for, **for local
stand-ins only**, under the constraints quoted in the D104 section at the end. On any other page,
and on every real board, nothing below changes: the location question stays a checkpoint and
the user completes the application on the employer's site. Synthetic coverage of the stand-in is
not evidence that a real page works. No page was visited for this document.

Before D104 (kept for the record): **design only.** A posting with a location question that
NoEfforts cannot answer through a visible, evidence-backed control stays a checkpoint.

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
- **Nothing is typed into a search picker on a real page** to make it offer results, and no
  result is chosen from a list that typing produced there. Search-as-you-type selection stays
  unsupported everywhere except the D104 local stand-in (`execution/adapters/dropdowns.py`,
  `CAPABILITIES["location_picker"]`).
- **Facts and preferences stay apart.** A location question could ask where the candidate
  lives (a fact: the profile's residence, user-approved), or where they want to work (a
  preference: targets). Its meaning is never inferred. A question whose meaning is not clearly
  one of them is a checkpoint, never a guess. This is the same rule as
  `test_residence_and_target_location_stay_separate`.
- **Unknown stays unknown.** Without the profile's approved residence, there is nothing to
  answer with.

## What NoEfforts does today (tested)

- A search picker is captured as an unsupported question, never typed into
  (`test_text_question_rendered_as_search_picker_is_unsupported_not_typed`), on every page but
  the D104 local stand-in (below).
- The location posting's route is a **checkpoint** before anything is disclosed, the hidden
  coordinates stay unresolved, and the package cannot be approved
  (`test_location_job_is_a_checkpoint`,
  `test_an_unsupported_required_control_is_a_checkpoint_before_disclosure`).
- The pilot-readiness condition `location` is not met (`providers/readiness.py`).

## Options, and the evidence each would need

| Option | What it would do | Allowed? | Evidence needed before any code |
|---|---|---|---|
| A visible plain-text location control | Fill it with the profile's approved residence city, only if the question is clearly about where the candidate lives, and only when no hidden coordinate is required alongside it | Possible later | A read-only observation showing such a control, labelled like the job-data question, and the coordinates optional or absent in that form; a fixture that mirrors it; mapping and readback tests; then `location_picker` raised from `none` only with its own reviewed evidence |
| The page's own search picker | Type a place, wait for results, choose one, let the page set the coordinates | **Local stand-ins only (D104).** On a real page: no, search-as-you-type stays unsupported | The owner's policy change is given for local stand-ins only (2026-10-31). For a real page: a read-only observation of a real location control (run #9 found none at load), its own capability entry, receiver-style tests and the owner's permission; synthetic coverage counts for none of it |
| A user-assisted step inside an automated attempt | Pause the attempt, let the user choose the location in the isolated browser, then continue | No: there is no way for a person to act inside the isolated browser, and a hand-over mid-attempt mixes disclosure boundaries | Would need its own design for a disclosure boundary per step, and the owner's approval |
| An authorized API that accepts a location without coordinates | Send the approved location as text through an employer-authorized API | Only with a real authorized API, which does not exist for candidates on this ATS | The employer's authorization and documentation; the API route's own capability entry |

## Decision for now

Location postings on real pages stay a checkpoint. The only option that could change that
without a further change of policy is the visible plain-text control, and only with the evidence
in its row. Path A (`docs/manual-dropdown-checklist.md`) does not ask about location, and would
not count as evidence for it.

## D104: the local stand-in (2026-10-31)

The owner's words: "Location labels must not be treated as proof of a selected structured
location. Do not manufacture hidden coordinates or trust résumé-parsing/prefill blindly.
Ambiguous or unsupported choices become checkpoints. Synthetic control coverage is not evidence
that the real page works. No real rehearsal or submission is authorized by this message."

- **The stand-in** (`fixtures/ats_receiver/greenhouse_v2.py`, mode `gh2_loc_search`, a FIXTURE
  ASSUMPTION): a search picker in a group named as its question, holding the hidden latitude and
  longitude its own script sets when a suggestion is clicked. Typing asks the receiver's places
  endpoint, and the ledger records each search text as a disclosure.
- **Capture** (`greenhouse_dom.location_picker`, extraction `greenhouse-dom-v3`): recognised
  only on a local stand-in (a fixture origin; there is none in production), only in exactly that
  structure, and only for the job data's one text location question with its hidden values. The
  question becomes a text question asked through the search (`widget: location_search`); each
  hidden value is `location_structured`: never filled, not a question, checked after the search.
  Anything else stays the checkpoint described above.
- **What is typed** (`resolver._location_search`): the approved residence fact only where the
  existing rules already classify the question as residence (here "Location (City)": the
  profile's approved city), otherwise your answer for this application. Never a saved answer, a
  draft, a target location, résumé parsing or anything the page proposes. A question that is
  sensitive or a statement is not typed at all.
- **When** (`GreenhouseDomAdapter._search_location`): only after the disclosure gate, as one
  input of the whole approved text; the ledger counts it as a disclosure, and so does NoEfforts'
  evidence (`location_search_text`, never the text).
- **Choice:** the suggestions must settle (not busy, nothing loading, the same list read three
  times in a row) within 5 seconds; then exactly one suggestion must equal the approved text
  (whitespace and case aside). None or several: the attempt stops. Never the first or the
  highlighted suggestion, never Enter.
- **Proof:** after the click the page itself must have set every hidden value (empty before,
  non-empty after, and NoEfforts never writes them) and still show the approved text. A matching
  label alone stops the attempt. Readback checks the same again before submitting.
- **Prefill is never trusted:** a location or hidden value already on the page before anything
  is entered stops the attempt before disclosure; one the page fills after the résumé upload
  stops it before anything is typed.
- **Stops are final:** after the search text was disclosed, any of these ends the attempt as
  abandoned with a fixed reason, never retried.
- **Real destinations:** a form that needs this control stops before anything is entered on any
  destination that is not a local stand-in (`STAND_IN_ONLY`). The registry's `location_picker`
  is `fixture` for `greenhouse_dom` (the stand-in) and `none` for `greenhouse_live`; the
  readiness condition `location` stays not met.
- **Tests** (`tests/test_greenhouse_controls.py`, the receiver's ledger as the oracle, each
  through both adapters): `test_location_exact_or_checkpoint`,
  `test_a_location_that_is_not_exactly_one_suggestion_set_by_the_page_stops_the_attempt`,
  `test_a_location_the_page_filled_itself_is_never_trusted`,
  `test_on_a_destination_that_is_not_a_stand_in_they_stop_before_anything_is_entered`.
