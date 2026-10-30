# Synthetic ATS receiver (test oracle)

A local, fictional applicant-tracking-system used to test NoEfforts execution. It is **not**
part of the product and must never be deployed.

- Independent of NoEfforts: it imports nothing from `backend/app` and keeps its own SQLite
  ledger, so tests count accepted applications from the receiver's side, not from NoEfforts'
  database.
- Fictional employer ("Example Health Clinic, fictional"); synthetic data only.
- Configurable failure modes (set through an admin endpoint protected by a token):
  `normal`, `delay`, `drop_after_accept`, `validation_fail`, `error_before_accept`,
  `error_after_accept`, `expired_session`, `upload_fail`, `conditional_field`, `otp`, `hostile`,
  `hog` (the page tries to exhaust memory), `bank_question` (adds the required, stable question
  "Highest level of education completed", which the saved-answer tests reuse; D51),
  `required_eeo` (the Gender self-identification question becomes required, as some boards make
  it; D61). Option
  `verify_drop=true` (with `otp`): the code is accepted but the reply never arrives (D50).
- `idempotent=true` makes repeated submissions of the same form token return the original
  receipt; `idempotent=false` accepts every POST, so duplicate-send bugs are visible.
- Two labelled Greenhouse-style approximations, mounted on the same receiver and ledger. Neither
  is Greenhouse code or markup:
  - `greenhouse_like.py` (`/gh/...`): named controls and native selects;
  - `greenhouse_v2.py` (`/gh2/...`): id-only controls and ARIA comboboxes, the structure seen
    at load on one real posting. Its widget behaviour is a fixture assumption, listed in the
    file header.

- A labelled Lever-style approximation, `lever_like.py` (`/lever/<site>/<posting>`, its form
  at `/apply`; D85), on the same ledger. It is not Lever code or markup: documents uploaded
  when chosen, the resume prefill (`lever_prefill`), the confirmation page and its reference
  are fixture design choices; its modes are listed in the file header.

- A labelled Ashby-style approximation, `ashby_like.py` (`/ashby/<board>/<posting>`, its form
  on `/application`; D87), on the same ledger. It is not Ashby code or markup: files uploaded
  when chosen, resume autofill (`ashby_autofill`), the spam-check marker
  (`data-ashby-spam-check`; Ashby documents a score, no widget), the pages after a flagged or
  repeated application, and the confirmation page are fixture design choices. A click on its
  cookie banner is recorded (`cookie_choice`) so tests can show nothing clicks it.

- A labelled Workday-style approximation, `workday_like.py` (`/workday/<tenant>/<req>`, its
  application at `/apply`; D88), on the same ledger, checkpoint-first. It is not Workday code or
  markup: the single-page "apply manually" application, files uploaded when chosen, the parse
  response (`wd_resume_parse`), the step marker (`data-workday-progress`), the cascade marker
  (`data-cascade-from`), the challenge widget (`wd_challenge`; Workday documents none) and the
  confirmation page are fixture design choices; the account gate, several pages, prefill and
  verification are modes, listed in the file header.

- **S5 variants (D62). FIXTURE ASSUMPTION, every one:** built from the legacy author's notes
  on real pages (`docs/legacy-audit.md` R7, HYPOTHESIS), they show how the adapters handle
  such a page (by stopping or by verified success), never that a real page behaves this way.
  - generic receiver: `accepted_elsewhere` (accepted, then a receipt shown on another
    posting's page after a redirect);
  - `greenhouse_like.py`: `gh_phrase_in_body` (confirmation-like words on the form and on its
    errors page), the board `thanks-confirmation` (a posting path holding both words),
    `gh_security_code_boxes` (eight one-character boxes, submit disabled until full),
    `gh_security_code_other` (a code entry with no input), `gh_challenge_after_submit` (the
    form loads clean; a bot check shows after the final click, which is recorded as
    `submit_challenged`), `gh_group_untick` (the page unticks one approved box),
    `gh_consent_banner` and `gh_consent_blocking` (a cookie banner and an in-form "I agree"
    button, each click recorded as `consent_click`; in the blocking mode the submit button
    stays disabled until "I agree"), `gh_two_steps` (the rest of the form on a second page);
  - `greenhouse_v2.py`: `gh2_phrase_in_body` and `gh2_phrase_no_confirmation` (a status
    message worded like a confirmation already on the form), `gh2_option_unlisted` (a dropdown
    with one option the job data does not list), `gh2_autofill_overwrite` (after the resume
    upload is acknowledged, the phone is rewritten and the last name blanked),
    `gh2_challenge_after_submit`, `gh2_two_steps`;
  - `fake_api.py`: `fapi_receipt_other` (accepted, but the reply names another application).

Run: `uv run --project backend python fixtures/ats_receiver/receiver.py --port 8765 --ledger /tmp/ledger.db --admin-token secret`
