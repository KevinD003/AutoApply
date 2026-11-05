# Greenhouse structured sections: the one rendered-page observation still needed (D120)

**Status:** prepared, **not executed**. This is an evidence request for the owner to authorize
separately, like Path A (`docs/manual-dropdown-checklist.md`) or the read-only Greenhouse check.
No applicant data is entered, nothing is uploaded, nothing is submitted, and no mailbox or new
network host is involved.

## Why this is the remaining gap

The structured Education/Employment repeating sections are now implemented and tested **locally,
end to end** (resolution → package freeze → approval → the real runner → the independent receiver
ledger), against a synthetic stand-in that renders the structure the owner's **legacy bot**
recorded (`autojob-greenhouse/src/apply.py` `_fill_work_history`, ~2026-10). That is **historical
evidence, not a current real-page observation.** Because of that, the section is **stand-in-only**:
on any real destination the adapter returns `STAND_IN_ONLY` and refuses before anything is entered
(exactly as D104's phone-country / location-search controls do). It cannot be enabled on a real
Greenhouse posting until the structure is confirmed on one.

## The smallest observation that lifts the gate

On **one** real Greenhouse hosted posting that shows a structured **Education** section (and, if
present, **Employment**), a read-only inspection of the rendered DOM — record only structure, never
applicant data, employer identity, or posting URL in git:

1. **Section container (`root`).** The selector of the element wrapping the section (the executor
   scopes "Add another" to it). The stand-in assumes `#education-section` / `#employment-section`.
2. **Row-0 control ids.** Confirm (or correct) these legacy ids:
   - Education: `school--0`, `degree--0`, `discipline--0`, `start-month--0`, `start-year--0`,
     `end-month--0`, `end-year--0` (note the **double** dash).
   - Employment: `company-name-0`, `title-0`, `start-date-month-0`, `start-date-year-0`,
     `current-role-0`, `end-date-month-0`, `end-date-year-0` (**single** dash).
3. **Add-another + row-1 ids.** The control that adds a row (role/accessible name — the stand-in
   uses a button named “Add another”) and the id pattern of the second row (`--1` / `-1`).
4. **Month combobox option text.** The one assumption readback currently guards: are months
   rendered as `September`, `09`, or `9`? (The stand-in uses the full month name.)
5. **Option source for school/degree/discipline.** Whether the option lists come from the
   documented Job Board education endpoints (`{id,text}`) or are rendered inline, and the exact
   option **text** for a couple of known degrees (to confirm the exact-match resolver will match).

## Refinement from a real (section-free) Greenhouse form (owner-provided, 2026-11-05)

The owner shared the rendered DOM of one real Greenhouse hosted apply form. It carried the ordinary
controls — name, a disabled pre-filled email, a phone-country picker, phone, résumé/cover-letter
attach (Attach / Google Drive / Enter manually), one custom `question_<digits>` free-text field, a
block of EEO/demographic selects, and "Submit application" — but **no** Education or Employment
structured section. So it does **not** lift this gate; it does, however, sharpen the request:

- The modern form renders its comboboxes (phone country, the EEO selects) as **react-select**
  widgets: a `div.select__control` container, a type-ahead `input` whose id is an unstable
  mount-order id (`react-select-N-input`) with its label via `aria-labelledby` (a React `useId`),
  and the chosen value shown in a `div.select__single-value` sibling — **not** a native `<select>`
  and **not** a stable, content-derived id.
- Therefore the single most decisive thing the Education observation must settle is **which markup
  the school/degree/discipline controls use**: the legacy plain `<input id="school--0">` that the
  bot recorded, or a react-select widget like the rest of the modern form. That choice decides the
  executor path — the existing `_select_combobox` already drives a react-select by its
  `aria-controls` listbox (and `execution.adapters.dropdowns` already reads `select__single-value`),
  whereas a plain input uses the text path. Record the container/widget type for one such control
  alongside the row-0 ids above.

This refinement changes no code and lifts no gate; it only makes the read-only request more precise.

## Scope and constraints (what to authorize)

- **Read-only.** Open the posting and inspect the DOM. **No** field is filled, **no** document is
  uploaded, **no** submit is clicked — this is an observation, not a disclosure or rehearsal.
- One posting; no mailbox; no new allowed host; no stealth or evasion.
- Return only the **sanitized structure** (selectors/ids/option-text format), no employer name,
  no posting URL, no applicant values — the same discipline as the existing read-only checks.

## What happens after the evidence

- **If the structure matches** the legacy ids: a small reviewed change lifts the stand-in-only
  gate for the section (raising the capability as D104 did once observed), with the existing
  receiver-ledger e2e re-run on the fixture first.
- **If it differs:** update `preparation.greenhouse_dom.detect_sections` and the id maps in
  `execution.adapters.greenhouse_sections` to the observed structure, re-validate on the fixture,
  then lift. No real submission happens as part of this; a first real rehearsal/submit stays behind
  the separate Greenhouse-pilot permissions (`docs/activation-status.md`).

This document authorizes none of the above; it states the smallest evidence that would.
