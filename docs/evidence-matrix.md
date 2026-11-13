# Evidence matrix (Phase C validation)

Baseline before this work: commit `58ac9ea` (clean tree apart from an untracked Redis
`dump.rdb`, since git-ignored), 95 backend tests passed, ruff clean. Environment: cloud sandbox,
Python 3.12.3, PostgreSQL 16.15, Redis 7.0.15, Celery 5.6.3 / kombu 5.6.2 / redis-py 6.4.0
(prefork pool), SQLAlchemy 2.0.55, FastAPI 0.149.0, Alembic 1.20.0, Playwright 1.56.0 (Python)
with Chromium 141.0.7390.37, Node 22.22.0, Next.js 15.5.4.

"Oracle" = the synthetic receiver's own SQLite ledger (`fixtures/ats_receiver`), which shares
no code or database with NoEfforts. "Mock" marks anything simulated.

## The Greenhouse pilot holds an answer to the length limit its page shows (D161, 2026-11-13; local only)

Nothing here ran against a real page. Branch `pilot-limits`. The runs drive the API and the
runner, by id (`greenhouse_dom`) and through the pilot (`greenhouse_live`), against the second
Greenhouse-style stand-in (its limits, the scripts that set them, its locks and its saves as you
type are fixture assumptions), with the receiver's ledger as the oracle (its acceptances, its
uploads and the page's saves); or read pages at capture; or compare with Chromium's own behaviour;
or run the read-only survey on the stand-in. All in `tests/test_pilot_limits.py`.

| Claim | Test | Result |
|---|---|---|
| Before D161 the pilot typed an answer cut, after the résumé's upload | `test_before_d161_an_answer_past_the_page_s_limit_was_typed_cut_after_the_upload` (2), `test_before_d161_a_limit_lowered_on_focus_left_the_page_holding_it_cut`, `test_before_d161_the_question_the_page_shows_was_typed_cut` | `abandoned` after one upload, the page holding 3 of the answer's characters |
| The capture records a typed question's limit as the browser reads it | `test_the_pilot_records_a_typed_question_s_limit_as_the_browser_reads_it` (10), `test_the_limit_of_a_question_the_page_shows_later_is_recorded` | ASCII digits, whitespace around them, the first of two; a sign, a decimal point, another script's digit, 0 or more than the browser reads: none |
| Only where the browser holds typing to it | `test_a_limit_is_recorded_only_where_the_browser_holds_typing_to_it` (8), `test_the_capture_reads_which_controls_hold_typing_to_a_limit` (19), `test_only_a_typed_answer_is_held_to_a_limit` (3), `test_a_limit_is_recorded_exactly_where_the_browser_cuts_what_is_typed` (14, Chromium), `test_a_limit_only_the_page_s_script_sets_is_not_recorded` | a text type, the first `type`, ASCII case aside (capitals; the Kelvin sign is no `k`); not a number or a date; a locked control too, except one the page locks and fills itself; recorded exactly where Chromium cuts what is typed |
| A locked control the page unlocks | `test_a_locked_control_s_limit_is_recorded_unless_the_page_fills_it`, `test_a_control_served_locked_and_unlocked_by_the_page_is_cut_as_typed` (Chromium), `test_a_control_the_page_unlocks_is_held_to_the_limit_it_was_served_with` (4) | disabled until loaded, read-only until it has focus: the limit is yours before approval; "Sam" sent, the page saving 3 characters |
| Held to it before you approve | `test_an_answer_longer_than_the_page_s_limit_is_yours_to_shorten_before_approval` (2), `test_an_answer_at_the_page_s_limit_is_sent_whole` (2) | refused when saved, naming 5/3; the shorter one sent; one at the limit sent whole |
| A limit the page shows now stops before anything is entered | `test_a_limit_the_page_s_script_lowers_pauses_before_anything_is_entered` (2), `test_a_limit_written_so_no_read_records_it_stops_plainly_naming_it` (2), `test_reading_the_form_again_records_the_limit_the_page_now_shows` | `failed_safe`, no upload; D132's pause naming the limit, or a plain stop; read again, a new version, the shorter answer sent |
| Never typed cut | `test_a_limit_lowered_as_the_control_gets_focus_is_never_typed_cut` (2), `test_a_question_the_page_shows_is_not_entered_when_its_limit_is_lowered_on_focus`, `test_the_check_before_typing_reads_the_limit_once_the_control_has_focus` (Chromium) | `abandoned` naming the limit, no save of the answer at all; the résumé's upload before it recorded |
| After filling | `test_a_limit_lowered_once_the_answer_is_typed_stops_before_the_send_gate` (2), `test_after_filling_a_question_the_page_did_not_show_is_not_held_to_its_limit` | `abandoned`, nothing sent; a question never shown left alone, `confirmed` |
| What the live check holds | `test_what_the_check_holds_to_the_live_limit` (Chromium), `test_the_live_read_goes_through_the_browser_s_own_definitions` (Chromium), `test_a_locked_prefilled_email_is_not_held_to_a_limit_the_page_sets` | typed text, a text area as a box; not a number, a number box, the location search's text; the page's own `maxLength`, `getAttribute` and `type` ignored; D129's locked email `confirmed`, sent as the page holds it |
| The survey reports it | `test_the_survey_reports_each_typed_question_s_limit_as_the_browser_and_capture_read_it`, `test_the_survey_reads_a_page_served_with_a_byte_that_is_no_utf8`, `test_the_page_as_served_is_decoded_as_the_capture_decodes_it`, `test_the_survey_says_which_typed_question_has_no_control_to_read`, `test_the_survey_says_what_it_could_not_read_of_the_page_as_served` | the browser's and the capture's reading, numbers only, through the privacy guard, nothing disclosed; "not_applicable" for a list or a file; "not_observable" where there is no control or the page as served cannot be read; the page as served decoded as the capture decodes it, a byte that is no UTF-8 replaced |
| Every other flow unchanged | the suites the change touches; the regression set | pass (`docs/implementation-status.md`) |
| Each part is needed | 30 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

## A control the page gives its application form from outside its markup is read as a question, and the form must send nothing NoEfforts did not read, by the click on its own button (D160, 2026-11-13; local only)

Nothing here ran against a real page. Branch `outside-controls`. The runs drive the API and the
runner against the base stand-in (`cfg["sends"]`), Lever-style and Greenhouse classic's, with
the receiver's ledger as the oracle (its acceptances, the disclosures, the requests it received);
or read pages at capture against Chromium's own list of the form's controls for the same pages;
or run each adapter's checks on its own stand-in's page in Chromium. All in
`tests/test_outside_controls.py`.

| Claim | Test | Result |
|---|---|---|
| Before D160 the employer received what the page wrote | `test_before_d160_the_employer_received_what_the_page_wrote` (6 modes; D160's parts switched off), `test_before_d160_the_final_click_sent_elsewhere` (2) | `confirmed`, the acceptance holding the page's text (a control given from outside, at load or once typed; a custom element, by name or as a second "Why us"; a hidden control the parser gives the form); the click sent to another address, or another form sent |
| A control given from outside is read and refused, as the browser gives it | `test_a_control_given_to_the_form_from_outside_is_read_and_refused` (3), `test_every_kind_of_control_given_from_outside_is_refused` (8), `test_what_the_browser_does_not_give_the_form_is_not_read` (11), `test_a_form_without_an_id_is_given_nothing`, `test_a_control_given_from_outside_keeps_whether_the_page_requires_it`, `test_a_control_inside_the_form_given_to_another_keeps_d159_s_reason` | read in the page's order, refused (`GIVEN_FROM_OUTSIDE`); an attribute written twice by its first value, ids and controls in a template or noscript left out, an element that is no control not read |
| The read equals Chromium's own list of the form's controls | `test_the_form_is_read_as_chromium_gives_it_its_controls` (21 pages) | the same names, none unread, none read that Chromium does not send |
| Greenhouse classic, Workday-style | `test_greenhouse_classic_refuses_a_page_that_gives_its_form_a_control_the_job_data_lacks`, `..._adopts_the_refusal_of_a_question_given_from_outside`, `test_a_work_entry_control_given_from_outside_is_the_work_history_checkpoint` | a difference (capture refused); refused as the page reads it; D149's checkpoint |
| A required one is a checkpoint; an empty optional one is left blank | `test_a_required_control_given_from_outside_is_a_checkpoint`, `test_an_empty_optional_control_given_from_outside_is_left_blank` | never approvable; `confirmed`, nothing under it |
| One holding the page's text stops before anything is entered | `test_a_control_given_from_outside_holding_page_text_stops_before_anything_is_entered` | `failed_safe`, no disclosure (before the reviews: `abandoned`, the résumé uploaded) |
| A control no read shows stops before anything is entered | `test_a_control_no_read_shows_stops_the_attempt_before_anything_is_entered` (5), `test_a_second_control_under_a_read_question_s_name_stops_where_a_read_misses_it` | `failed_safe`, no disclosure, no pause, the count named and no name |
| ... and after filling | `test_a_custom_control_added_once_an_answer_is_typed_stops_before_the_send_gate`, `test_a_control_given_once_an_answer_is_typed_stops_before_the_send_gate` | `abandoned`, no acceptance |
| The final click must send the form read | `test_a_final_click_that_would_send_elsewhere_stops_before_anything_is_entered` (2), `test_the_final_click_must_send_the_form_checked` (7, Chromium) | `failed_safe`, no request to send; another form, an address, method, encoding or window, two forms of the id: refused |
| A form not singled out, or unreadable, is a plain stop | `test_a_form_that_cannot_be_singled_out_stops_before_anything_is_entered`, `test_a_form_the_runner_cannot_read_is_a_plain_stop` (2), `test_greenhouse_classic_s_form_it_cannot_read_is_a_plain_stop` | `failed_safe`, nothing entered (before: an internal error, or everything entered first) |
| A file question's form sends the file alone | `test_a_hidden_value_under_the_file_question_s_name_is_never_sent` (there at load; added once "Why us" is typed, after the upload), `test_a_hosted_file_question_s_form_must_send_the_file_alone` (Lever-style, Greenhouse classic) | `abandoned`, no acceptance; the readback stops the one added after the upload |
| The reads see the form whatever its controls are named | `test_the_form_is_read_whatever_its_controls_are_named`, `test_the_form_s_controls_are_counted_passively`, `test_a_control_the_parser_gives_the_form_outside_its_markup_is_counted`, `test_a_custom_control_is_read_by_its_name_attribute` | counted, read, the character set read; no `formdata` event; Chromium's own entry list holds what is counted |
| Each adapter on its own page | `test_each_adapter_reads_its_own_page_without_a_stop_and_stops_what_no_read_shows` (5) | no stop as served; a custom element, a button sending elsewhere: stopped |
| What is counted | `test_what_the_read_does_not_show_is_counted` (7) | per name, a group's choices and a refused question aside |
| A final button that cannot be read stops plainly | `test_a_button_that_cannot_be_found_fails_closed` (D154's) | `REFUSAL_UNREAD` (before 9838d26, found by the regression set: the error raised) |
| Every other flow unchanged | the suites the change touches; the regression set | pass after one fix, 9838d26 (`docs/implementation-status.md`) |
| Each part is needed | 25 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

## An ordinary answer is read back as its form would send it, and a control whose form would send something else is refused when the form is read (D159, 2026-11-13; local only)

Nothing here ran against a real page. Branch `sent-as-approved`. The runs drive the API and the
runner against the base stand-in (its "Why us" text area, limited to 1000; `cfg["sends"]`) and
Greenhouse classic's stand-in, with the receiver's ledger as the oracle (its acceptances, the
page's own saves as it is typed, and the requests it received); or read pages at capture; or
drive the readback in Chromium on a page of its own, against Chromium's own `FormData` for the
same page. All in `tests/test_sent_as_approved.py` unless named.

| Claim | Test | Result |
|---|---|---|
| Before D159 the employer received something else | `test_before_d159_the_employer_received_something_else` (3 modes; D159's checks switched off) | `confirmed`, and the acceptance holds your text with line breaks inserted, or nothing under the question |
| What the form would send is read back, and nothing else is sent | `test_what_the_form_would_send_is_read_back_and_nothing_else_is_sent` (hard wrap, another form, disabled, a second control: each made once "Why us" is typed), `test_a_value_the_page_puts_under_an_unanswered_question_s_name_is_never_sent` | `abandoned`, no acceptance |
| A page that sends from `formdata` receives nothing from the readback | `test_a_page_that_sends_from_formdata_receives_nothing_from_the_readback` (a rehearsal), `test_a_stop_after_filling_sends_nothing_through_the_page_s_formdata`; `test_the_form_is_read_as_the_browser_would_send_it_without_its_formdata_event`, `test_a_work_entry_is_read_back_without_its_form_s_formdata_event` (Chromium) | `rehearsed` and `abandoned` with no acceptance and no request to submit (the first version: an acceptance in each); no `formdata` event; the passive read equals Chromium's own `FormData` for the same page wherever it knows the value |
| A choice is read as its form would send it | `test_a_choice_the_page_disables_once_chosen_is_never_taken_as_sent` | `abandoned`, no acceptance (before: `confirmed` without your answer) |
| A refused question is never filled, and an optional one never stops the run | `test_a_text_area_that_hard_wraps_when_the_form_is_read_is_left_blank`, `test_an_optional_choice_refused_when_the_form_is_read_is_left_blank` (a box, a group), `test_greenhouse_classic_never_sends_page_text_in_a_question_it_refused` | `confirmed`, nothing under the question; on Greenhouse classic, page text in it stops the run (`abandoned`, no acceptance) |
| Refused when the form is read, as Chromium sends | `test_a_text_area_that_hard_wraps_is_refused_when_the_form_is_read` (14 spellings), `test_a_control_given_to_a_form_by_name_is_refused` (9 controls), `test_a_control_whose_dirname_sends_a_field_of_its_own_is_refused` (9 controls, named and empty), `test_a_refused_question_keeps_whether_the_page_requires_it`, `test_a_reason_read_before_keeps_its_wording`; `test_workday_entry_details.py` (D155's cases, as Chromium reads them) | hard, physical and on refused, off, virtual and spaced values read; `dirname` refused where Chromium sends a field; `form` always; one field per group |
| Greenhouse classic: the page's refusal and limit, the cross-check kept | `test_greenhouse_classic_refuses_it_as_its_page_reads_it`, `test_greenhouse_classic_keeps_its_cross_check_where_the_page_refuses_a_question`, `test_greenhouse_classic_holds_an_answer_to_its_page_s_own_limit` | refused; a control of another type, alike in all else, still a disagreement (with the refusal adopted first, as the first version did, it was not); the page's limit recorded |
| A form whose limit changed is a new version | `test_a_form_whose_limit_changed_is_a_new_version` | read again unchanged: the same version; lowered: the next, holding the new limit |
| A lowered limit stops before anything is entered | `test_an_answer_longer_than_the_page_now_accepts_pauses_before_anything_is_entered`, `test_reading_the_form_again_records_the_new_limit_and_your_shorter_answer_is_sent`, `test_greenhouse_classic_pauses_on_a_limit_its_page_lowers_and_a_read_records_it`, `test_greenhouse_classic_pauses_on_a_limit_its_page_s_script_sets` | D132's pause naming the limit, nothing in the ledger; read again: a new version, the pause resolved, the answer yours to shorten (D158); the shorter one `confirmed` |
| A limit no read would record is a plain stop | `test_a_limit_no_read_of_the_form_would_record_stops_plainly_naming_it` ("500.0") | `failed_safe`, no pause, nothing in the ledger, the limit named |
| A value the control would cut is never typed | `test_a_limit_lowered_while_the_answers_are_typed_never_gets_a_cut_answer` (once the first name is typed; on focus) | `abandoned`, no acceptance, no save of the answer by the page (before: saved cut, 500 characters) |
| A form in another character set never sends an answer changed | `test_a_form_in_another_character_set_never_sends_an_answer_changed` | an answer with "☕": `failed_safe`, nothing entered; a plain one: `confirmed` |
| A number is typed exactly | `test_a_number_is_typed_exactly`, `test_a_number_is_typed_and_read_back_exactly_in_the_browser` | 12345678 typed and held as 12345678 (before: 1.23457e+07) |
| A work entry's control must belong to its form | `test_an_entry_control_given_to_another_form_on_the_page_is_found` | found (before: passed when the other form exists) |
| The comparison is exact | `test_sends_is_exact` | one value once; an unanswered question nothing but empty |
| Every other flow unchanged | the suites the change touches; the regression set | pass (`docs/implementation-status.md`) |
| Each part is needed | 29 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

## An ordinary question's length limit is read as the browser reads it, and your answer held to it as its form sends it (D158, 2026-11-13; local only)

Nothing here ran against a real page. Branch `question-limits`. The runs drive the API and the
runner against the base stand-in (its "Why us" text area, limited to 1000, `receiver.LIMITS`),
with the receiver's ledger as the oracle (its acceptances, and its own check of the limit on what
it receives); or read pages at capture; or drive the answer box in the browser. All in
`tests/test_question_limits.py` unless named.

| Claim | Test | Result |
|---|---|---|
| An answer at its limit as its form sends it is sent whole | `test_an_answer_at_its_limit_as_the_form_sends_it_is_sent_whole` (999 for the browser, 1000 as sent) | `confirmed`; the acceptance holds it whole; the page's own check accepts it |
| One its form would send longer is refused when saved | `test_an_answer_the_form_would_send_too_long_is_refused_when_saved` | 400, "1001/1000 characters as the form sends them"; at 1000, 200 |
| Before D158 it reached the page and was refused there | `test_what_the_page_s_own_check_refuses_never_reaches_it_now` (the old count, code points, monkeypatched) | not `confirmed`, no acceptance: the page's own check refused it after the final click |
| Counted as the form sends it | `test_an_answer_is_held_to_its_limit_as_its_form_sends_it` (9 cases), `test_a_text_area_s_line_breaks_are_kept_as_one_lf_each` | LF, CR and CRLF each one line break counting 2; a character outside the plane 2 |
| A one-line box holds no line break | `test_a_one_line_box_holds_no_line_break` (text, email, tel, url; LF, CR, CRLF) | refused when saved (before: accepted, then the readback stopped the attempt) |
| A broken character is refused plainly | `test_a_broken_character_is_refused_plainly` | ValueError, never the codec's words or a server error |
| An answer you gave that no longer fits is a checkpoint, even optional | `test_an_answer_saved_before_that_no_longer_fits_is_a_checkpoint_even_when_optional` | `needs_user`, unresolved, the count named (before: `blank_optional`, sent empty) |
| A draft is fitted to its field, never offered when accepting would refuse it | `test_a_draft_its_form_would_send_too_long_is_never_offered`, `test_a_cached_draft_that_no_longer_fits_is_replaced_not_offered_again`, `test_a_draft_for_a_one_line_box_is_offered_on_one_line` | 422, nothing kept; a new draft requested; offered on one line and accepted |
| The limit is read as the browser reads it | `test_a_question_s_limit_is_read_as_the_browser_reads_it` (12 spellings, a limit written twice) | ASCII whitespace read; the first of two read; signs, other characters, 0 and above 100,000 not recorded |
| The stand-in's own check counts what it receives | `test_the_stand_in_refuses_what_it_receives_longer_than_its_limit` | CRLF and a character outside the plane counted 2 |
| The answer box counts as the form sends it | `frontend/e2e/question-limits.spec.ts` (desktop and mobile) | "6/1000 (a line break counts as two)"; "1001/1000" in red at the browser's own 1000 |
| Every other flow unchanged | the 29 suites the change touches; the regression set of 85 files | pass (`docs/implementation-status.md`) |
| Each part is needed | 16 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

## A Workday-style work entry's length limits are read, and your record held to them (D157, 2026-11-13; local only)

Nothing here ran against a real page. Branch `workday-entry-limits`. The runs drive the runner
against the Workday-style stand-in's wizard (FIXTURE ASSUMPTION FA7, variants
`experience_limits` and `experience_limits_at_load`), with the receiver's ledger as the oracle
(its page-2 draft rows, acceptances and disclosures); or read stand-in pages at capture; or
drive the section's executor on pages set in Chromium. All in
`tests/test_workday_entry_limits.py` unless named.

| Claim | Test | Result |
|---|---|---|
| Your work history within the page's limits is sent | `test_your_work_history_within_the_page_s_limits_is_sent` (`experience_limits`, two records) | the package freezes the four limits; `confirmed`, both entries in page 2's draft row, one acceptance. Before D157: the form was one checkpoint when it was read |
| A value exactly at its limit, as its form sends it, is sent whole | `test_a_value_at_the_page_s_limit_is_sent_whole` (a title of 38 letters and an emoji, 40; a role description of 199 characters with a line break, 200 as sent) | `confirmed`; page 2's draft row holds each whole; one acceptance |
| A record longer than the page accepts blocks approval | `test_a_record_longer_than_the_page_accepts_blocks_approval` (216 characters; 200 for the browser but 201 as sent) | one unresolved `section:employment:…:description` key; approval refused (409); no disclosure, nothing accepted. In the first version (36be30b) the second was approved, then refused by the page's own check after pages 1 and 2 were sent (both reviews) |
| An entry on the page limited otherwise is refused when the form is read | `test_an_entry_on_the_page_limited_otherwise_is_refused_when_the_form_is_read` (`experience_limits_at_load`); `test_an_entry_on_the_page_limited_otherwise_is_one_checkpoint` (4 cases and a date's limit that fits) | `WORK_KEY` unresolved, approval refused, no disclosure; a date limit MM/YYYY fits does not count |
| A limit is read only as the browser reads it, never an error of capture | `test_a_limit_is_read_as_the_browser_reads_it` (6 spellings), `test_a_limit_nothing_can_honour_is_one_checkpoint` (22 cases: signs, other characters and scripts, sizes, thousands of digits, an attribute written twice, a box, a date under 7, minlength, pattern), `test_a_control_s_limit_is_its_number_none_or_unreadable` | as stated; nothing larger than the browser's own limit is ever read |
| minlength and pattern on an entry already on the page are refused | `test_an_entry_on_the_page_with_another_constraint_is_one_checkpoint` | one checkpoint (before D157 the entry was accepted) |
| Limits are written and fingerprinted only when set | `test_limits_are_written_and_fingerprinted_only_when_set`; `test_package_contract.py` (an `experience_limits` capture; the shape recorded under version 3) | a section without limits dumps and fingerprints as before; a changed limit changes the fingerprint |
| Length is counted as the form sends it | `test_length_is_counted_as_the_form_sends_it` (5 cases), `test_a_record_longer_than_the_page_accepts_is_yours_to_shorten` | a line break 2, a character outside the plane 2; the message names the limit and the length, never the text |
| The spec, resolution and frozen content refuse what they do not know | `test_a_section_s_limits_are_known_fields_in_range`, `test_a_section_with_limits_never_named_is_not_supported`, `test_frozen_limits_are_checked_before_anything_is_entered` (12 cases) | refused, unsupported or a checkpoint; sorted when written |
| Entering never types a value its page would cut | `test_a_frozen_value_within_its_limit_is_planned_and_greenhouse_never_plans_one`, `test_the_plan_holds_each_value_to_its_limit_past_the_content_check`, `test_the_executor_refuses_a_value_its_page_would_cut` (3), `test_a_limit_the_page_sets_on_the_entry_it_adds_stops_before_anything_is_cut` (Chromium) | the plan refuses past the content check; a limit the page's script sets on the entry it adds stops it before typing (the control stays empty); Greenhouse never plans a limited section |
| Hand-set limits and the generic reader | `test_a_form_given_by_hand_never_names_limits`, `test_an_ordinary_question_s_limit_never_breaks_reading_the_form` (9) | 400; the form is read whatever the limit says, the limit recorded only as ASCII digits from 1 to 100,000 (before: a superscript digit, thousands of digits, 0 or 524288 failed the whole read) |
| The stand-in's own check counts what it receives | `test_the_stand_in_refuses_a_part_longer_than_its_limit` | a part past its limit refused, a line break counted 2 (CRLF) |
| Every other flow unchanged | the 21 suites the change touches; the regression set of 84 files (on a5870b5) | pass (`docs/implementation-status.md`) |
| Each part is needed | 41 changes (37 on a5870b5, 4 on 45937de), one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

In D155's section, "A page's limit on a role description's length: still refused at capture"
describes the capture before D157.

## Before each wizard page's Next, what the page itself would refuse stops the attempt with that page never sent (D156, 2026-11-13; local only)

Nothing here ran against a real page. Branch `wizard-next-checks`. The runs drive the runner
against the Workday-style stand-in's wizard (FIXTURE ASSUMPTIONS FA1-FA8, cfg `page_check`),
with the receiver's ledger as the oracle (its draft rows, acceptances and the POSTs it logged);
or drive the two checks on pages set in Chromium. All in `tests/test_wizard_next_checks.py`
unless named.

| Claim | Test | Result |
|---|---|---|
| A page whose script marks a field as not valid is never sent | `test_a_field_the_page_marks_stops_the_wizard_before_that_pages_next` (`custom_error`; the page's own Next would send it) | `abandoned` before page 1's Next: no draft row, no gate for that Next, no click; the read after the page's readback; counts only. Before D156: pages 1 to 4 saved at the employer, then the final click found refused |
| A Next the page refuses while a field is marked is never clicked | `test_a_next_the_page_refuses_while_a_field_is_marked_is_never_clicked` (`next_aria`) | stopped before the gate; no click recorded. Before D156: clicked, "the employer's page showed an error after a page's Next" |
| A mark on the field filled last counts, once focus left it | `test_a_mark_on_the_field_filled_last_counts_once_focus_left_it` (`next_aria_last`) | stopped before the gate (with focus still there: not counted, clicked, refused) |
| A value the final click's own validation refuses stops before its page is sent | `test_a_value_the_final_clicks_validation_refuses_stops_before_its_page_is_sent` (`pattern`) | stopped before page 1's Next, nothing sent. Before D156 (and in D156's first version): pages 1 to 4 sent, then stopped before the send gate |
| What only the review page refuses is left to the final click | `test_a_value_the_review_page_alone_refuses_is_left_to_the_final_click` (`late_invalid`) | pages 1 to 4 sent; stopped before the send gate (D154) |
| A Next the page keeps disabled stops before its gate | `test_a_next_the_page_keeps_disabled_stops_before_its_gate` (`next_disabled`, page 2) | page 1 sent, page 2 never; no gate for page 2's Next and no click; no readback of page 2. Before D156: the click waited 20 s and was recorded as unanswered ("does not know whether that page was saved") |
| A Next kept disabled for a question the page showed says so | `test_a_next_kept_disabled_for_a_question_the_page_showed_says_so` (`next_needs_answers`, `follow_up_revealed_required`) | D148's reason (the question the page revealed requires an answer), page 4 never sent |
| A Next enabled later is waited for, as long as its click waited | `test_a_next_enabled_3_s_after_the_pages_last_answer_is_waited_for` (`next_late_enable`, the final button's limit shortened to 1 s) | `confirmed`, one acceptance |
| What the page changes while it keeps its Next disabled is read back | `test_what_the_page_changes_while_it_keeps_its_next_disabled_is_read_back` (`next_late_rewrite`) | "1 field(s) did not keep their values"; page 1 never sent |
| A mark the page clears when focus leaves a field is cleared before the read | `test_a_mark_the_page_clears_when_focus_leaves_the_field_is_cleared_before_the_read` (`focus_validation`) | the page marked City once while it was filled; at the read City has no mark and no focus; `confirmed` |
| A page that cannot be read before a Next is the stop's while the worker is being stopped | `test_a_next_unreadable_while_the_worker_is_being_stopped_ends_as_the_stop` (both reads, each with and without a stop request) | the stop's reason; otherwise the unread reason, every approval retired |
| On a page: the Next is its page's one button, shown and enabled, waited for within its own limit | `test_the_next_is_its_own_pages_one_button` (none, two, owned by no form), `test_a_next_hidden_or_disabled_is_unavailable` (3), `test_a_next_the_page_enables_or_draws_later_is_waited_for_and_the_lease_renewed` | as stated; the lease renewed while waiting; a Next drawn late waited for |
| On a page: which marks count before a Next | `test_on_a_scripts_next_only_the_pages_marks_on_fields_shown_count`, `test_a_mark_on_the_field_that_has_focus_is_not_counted`, `test_marks_inside_a_part_of_the_page_that_has_focus_count` (also the final click's read), `test_a_next_that_is_the_browsers_validated_submission_counts_every_page` | only the page's own marks on fields shown, never on what has focus unless that is a container; a native Next (refused at capture) counts every page |
| On a page: the final click's validation for the pages filled so far | `test_what_the_final_click_would_refuse_on_the_pages_filled_so_far_is_read_before_a_next` | by kind, pages 1 to i only, where the final click is the browser's own validated submission; never with `novalidate` or `formnovalidate`; never a mark on what has focus |
| Focus leaves a filled page; the read is passive | `test_focus_leaves_what_has_it_once_a_page_is_filled`, `test_the_read_is_passive_and_names_counts_only` | focus on the body, the page's own blur handled once; no `invalid` or focus event fired by the read; counts only |
| A failed Next click is still reported as possibly sent | `test_workday_wizard.py::test_a_next_whose_click_fails_says_the_page_may_have_been_saved` | the click reached and failed; "does not know whether that page was saved" (before 04350e6 the test passed without reaching the click) |
| Every other flow unchanged | the 11 suites the change touches; the regression set of 83 files | pass (`docs/implementation-status.md`) |
| Each part is needed | 17 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

In D154's section, "Before each wizard page's Next, the page's own marks are not read" describes
the runner before D156.

## A Workday-style work entry's Location and Role Description come from your record (D155, 2026-11-12; local only)

Nothing here ran against a real page. Branch `workday-entry-details`. The runs drive the runner
against the Workday-style stand-in's Work Experience section (FA7: the wizard's My Experience
page, and the single page), with the receiver's ledger as the oracle (its page-2 draft rows and
its acceptances); or read capture, the spec, resolution and the frozen content alone; or drive
the section's executor on a page set in Chromium.

| Claim | Test | Result |
|---|---|---|
| Your record's location and role description are sent where the entry asks them | `test_workday_entry_details.py::test_your_location_and_role_description_are_sent_on_their_page`, `test_on_the_single_page_they_are_sent_too` | `confirmed`; the page-2 draft row (the single page's acceptance) holds the record's location and its role description with its line breaks; a role with no description on its record is sent empty. Before D155: both always empty |
| A page that requires them sends yours | `test_a_page_that_requires_them_sends_yours` (`experience_parts_required`) | `confirmed`, one acceptance, the page's own checks satisfied. Before D155: the form was refused when it was read |
| A page that requires one your record lacks blocks approval | `test_a_page_that_requires_one_your_record_lacks_blocks_approval` | the package lists the record's field as unresolved; approval refused; nothing reached the receiver |
| Capture names the parts the entry asks, and which the page requires | `test_the_entry_s_location_and_role_description_are_named_with_the_section`, `test_a_page_that_requires_them_is_read_not_refused` (`required`, `aria-required`, Role Description), `test_an_entry_that_asks_neither_names_neither` | `parts`, `required_parts` as asked; none for an entry without them (and no `parts` key) |
| The spec accepts only known parts, sorted and once; they are part of the form, and written only when named | `test_a_section_names_only_known_parts_sorted_and_once` (5), `test_the_parts_are_part_of_the_form_and_written_only_when_named` | refused; four distinct fingerprints; a section without parts dumps as before |
| Resolution takes your record's own text, never a guess | `test_your_record_s_location_and_role_description_are_resolved_as_written`, `test_nothing_on_your_record_is_never_sent_and_never_guessed` (4), `test_a_part_the_page_requires_and_your_record_lacks_is_yours_to_add`, `test_a_location_with_a_line_break_is_yours_to_fix`, `test_a_section_asking_a_part_never_named_is_not_supported`, `test_a_section_that_does_not_ask_them_resolves_as_before` | resolved as written (line breaks as one LF); blank: not sent; required and blank: yours to add; a location with a line break: yours to fix; an unknown part: unsupported; a section without parts: the five fields only |
| Frozen content carries them only where the section names them; Greenhouse never plans such a section | `test_frozen_parts_it_cannot_enter_exactly_are_refused` (11, each refused by the check it names: rows carry part fields only where the case is about one), `test_greenhouse_never_plans_a_section_that_names_parts` | refused |
| The plan enters what the row holds and keeps the rest empty | `test_the_plan_enters_the_parts_your_record_holds`, `test_the_plan_leaves_empty_what_your_record_does_not_hold`, `test_a_section_frozen_before_d155_is_planned_as_before` | as stated |
| On the page: entered and read back exactly | `test_both_are_entered_and_read_back_exactly`, `test_a_role_description_the_page_changes_is_found`, `test_one_your_record_does_not_hold_stays_empty_and_is_checked` | exact values (the role description with LF); a change found by the readback; an empty part stays empty and a value the page puts there is found |
| An edit to your location retires the approval; an edit to your role description is in the version diff | `test_an_edit_to_your_location_retires_the_approval`, `test_an_edit_to_your_role_description_is_in_the_version_diff` | every approval retired; approved again, the new location is sent; the diff names the role description field only, before and after |
| What the employer would receive is what was typed | `test_a_control_whose_form_would_send_otherwise_than_typed_is_one_checkpoint` (a hard-wrapping text area, twice; another `wrap`; `dirname`; `form`), `test_a_soft_wrapping_role_description_is_read`; on the page, `test_what_the_form_would_send_is_read_back_not_only_what_the_control_shows` (hard wrap set after filling), `test_a_control_its_form_would_not_send_is_found` | refused when the form is read (the work history checkpoint); a soft-wrapping one read; after filling, the readback finds a value its form would send otherwise, while the control still shows the approved text |
| An entry already on the page asks its parts as the template does | `test_an_entry_on_the_page_that_asks_its_parts_otherwise_is_one_checkpoint` (lacking one; requiring one alone; asking one the template does not), `test_an_entry_on_the_page_asking_its_parts_as_the_template_does_is_read` | refused when the form is read (before D155's review: accepted, then stopped after values were entered); one asking them as the template does is read |
| An entry a parsed resume adds or fills is never adopted | `test_an_entry_a_parsed_resume_fills_is_never_adopted`; `test_workday_experience.py::test_an_entry_a_parsed_resume_adds_is_never_sent` (one record, none) | `abandoned` before anything is typed into the section (the work history values reason; with no record, the entries-beyond reason); page 1 saved, page 2 never sent; before the review: with every part on your record, the parse's entry was filled over and sent |
| A page reacting when focus leaves a field reacts before the readback | `test_a_page_that_rewrites_a_value_when_focus_leaves_it_stops_the_entry` | the entry stops at the rewritten control |
| The resume reader's note is never sent as your words | `test_a_role_description_still_holding_the_resume_reader_s_note_is_yours_to_edit` | yours to edit, first line or later |
| Approvals given before D155, and a page that starts requiring a part, pause | `test_an_approval_given_before_d155_pauses_before_anything_is_entered` (approved on a capture without parts, simulated), `test_a_page_that_starts_requiring_them_after_approval_pauses` | `failed_safe`, a pause open, nothing reached the receiver |
| Parts are NoEfforts' own | `test_a_form_given_by_hand_never_names_parts` | the manual form endpoint refuses them (400) |
| The stand-in's own refusal (the oracle) | `test_the_stand_in_refuses_an_entry_without_a_part_it_requires` | an entry without its Location refused in `experience_parts_required`, accepted elsewhere |
| Greenhouse's sections and every other form unchanged; the new paths recorded under `SCHEMA_VERSION` 3 | `test_workday_experience.py::test_a_greenhouse_section_reads_and_fingerprints_as_before`, `test_package_contract.py::test_the_package_shape_is_the_one_recorded_for_its_schema_version` (a section with a record holding both parts and one holding neither), the 14 suites the change touches and the regression set of 82 files | pass (`docs/implementation-status.md`) |
| Each part is needed | 33 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails the tests named for its part |

In D149's section, "Location and Role Description are never entered" describes the adapter
before D155.

## Before the send gate, what the page itself would refuse at the final click stops the attempt; filling waits for what the answers started (D154, 2026-11-12; local only)

Nothing here ran against a real page. Branch `page-own-checks`. The runs drive the runner against
the Workday-style stand-in (single page and wizard, FA8), the second Greenhouse-style stand-in
and the receiver's own form (`page_check`; FIXTURE ASSUMPTIONS), with the receiver's ledger as
the oracle; or drive the checks on pages set in Chromium, where the browser's own validation is
the oracle.

| Claim | Test | Result |
|---|---|---|
| A value the browser would refuse stops before the send gate | `test_page_own_checks.py::test_a_value_the_browser_would_refuse_stops_before_the_send_gate` (a pattern; a custom error the page's script set) | `abandoned`, every approval retired; receiver ledger: no final POST, nothing accepted; the reason names counts only. Before D154: `unknown` (no request; quarantined) |
| A field the page's own script refuses stops before the send gate | `test_a_field_the_pages_own_script_refuses_stops_before_the_send_gate` (`aria-invalid`; a custom error with the page's `checkValidity()` at its click) | `abandoned`; no POST to the submit address. Before D154: `rejected` after `sending` (`CLIENT_BLOCKED`) |
| A final click that cannot be made stops before the send gate | `test_a_submit_button_the_page_keeps_disabled_stops_before_the_send_gate`, `test_a_v2_submit_button_kept_disabled_stops_before_the_send_gate`, `test_a_second_submit_button_stops_before_the_send_gate` (the receiver's own form) | `abandoned`; nothing sent. Before D154: `unknown`, or an internal error after the gate |
| A form's other buttons are never taken for its submit button | `test_a_forms_other_buttons_are_never_taken_for_its_submit_button` (the receiver's own form with a "Save for later" button) | `confirmed`, one acceptance, one final POST |
| A page that keeps Submit disabled until an unlisted click (R11.8, the v1 Greenhouse stand-in) stops after the wait | `test_greenhouse_adapter.py::test_a_submit_button_waiting_for_an_unlisted_click_stops_before_the_final_click` | `abandoned` before the send gate with D154's reason, nothing clicked, one upload in the ledger (before D154: the adapter's own "still disabled" stop, at once) |
| A submit button enabled a moment after the last answer is waited for, before the readback | `test_a_submit_button_enabled_a_second_after_the_last_answer_is_waited_for`, `test_a_v2_submit_button_enabled_a_second_later_is_waited_for`; `test_what_the_page_changes_while_it_keeps_submit_disabled_is_read_back` | `confirmed`, one acceptance; the field the page rewrote meanwhile stops the readback (`abandoned`, nothing sent; before D154 and in its first version: `confirmed`, the rewritten value sent) |
| A stale mark on the field that has focus is not counted | `test_a_mark_the_page_would_clear_when_focus_leaves_the_field_is_not_counted` (the page checks a field when focus leaves it, and refuses its own submission while one is marked) | `confirmed`, one acceptance (D154's first version: `abandoned`, the safety review's blocker) |
| A question the page shows after a request is waited for | `test_a_follow_up_shown_after_a_request_pauses_for_your_answer`; `test_a_follow_up_shown_after_a_request_stops_a_wizard_before_its_pages_next`; `test_an_answered_follow_up_shown_after_a_request_is_entered` (single page, wizard) | unanswered: the conditional-required pause (D135), nothing sent; on a wizard, stopped before page 4's Next (draft pages 1 to 3 only); answered: entered and `confirmed`, the answer in the acceptance. Before D154: `rejected` after the application (or page 4) was sent |
| The browser validates every page of a wizard at the final click | `test_a_wizard_whose_review_page_refuses_an_earlier_page_stops_before_the_send_gate` | `abandoned` on the review page; draft pages 1 to 4, no final POST. Before D154: `unknown` |
| A page still loading after the answers stops before its checks | `test_a_page_still_loading_after_the_answers_stops_before_its_checks` (single page; wizard page 1) | `abandoned`, every approval retired, nothing sent (on the wizard, no draft). Before D154: `confirmed` (never waited) |
| A page unreadable while the worker is being stopped ends as the stop | `test_a_page_unreadable_while_the_worker_is_being_stopped_ends_as_the_stop` | the stop's outcome ("the worker was asked to stop"); otherwise the refusal, every approval retired |
| A rehearsal of a page that would refuse the click is never recorded | `test_a_rehearsal_of_a_page_that_would_refuse_the_click_is_never_recorded` | `abandoned`, no rehearsal record. Before D154: `rehearsed` |
| What the page never reads does not stop it | `test_a_hidden_field_a_novalidate_page_never_reads_is_not_counted`; `test_security_code_boxes_shown_before_the_click_are_left_for_the_checkpoint` | `confirmed`; the security code entered only from the checkpoint, then `confirmed` |
| What the read counts | `test_page_refusal_read.py` (68 cases on pages set in Chromium) | where the browser validates: every invalid control, hidden ones too, by kind (typing-only states included; a form-associated element; controls tied by `form=`); disabled, read-only, hidden-type and template controls not; where the script decides (`novalidate`, `formnovalidate`, a non-submit button): only the page's own marks on shown elements, never the markup's constraints; marks on the focused field and its wrapper never; `aria-invalid` only as "true"; marks hidden, invisible, transparent, inert or aria-hidden never; radios and nested marks once; a checkpoint's boxes and their wrapper never, as the Greenhouse DOM adapter's click takes them; the button: none, two, in no form, disabled, hidden, `aria-disabled`, enabled later, a checkpoint shown while waiting, a page closed |
| The checks act on nothing | `test_the_checks_fire_no_event_run_no_check_and_change_nothing`; `test_the_read_returns_counts_only` | no `invalid`, focus, input, change or scroll event, no `checkValidity()`/`reportValidity()` call, the form's markup and focus unchanged; four keys, numbers and a boolean |
| The adapters' paths as before | the 84 files the change touches: 14 run on their own, 70 within the regression set | pass: the 14 on their own (368 passed in 14.2 min on 5db60c8), the other 70 within the regression set |
| Each part is needed | 49 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each of the 49 fails a test, the one named for its part (one only once 5db60c8 gave the receiver's own form a button that does not submit it) |

In D148's section, "a required one shown after that check would make the page's own checks refuse
the final click, which ends as an unknown outcome" describes the runner before D154.

## A list is judged by the page's record of changes to a list, and the option is chosen from one read (D153, 2026-11-12; local only)

Nothing here ran against a real page. Branch `whole-page-check`. The runs drive the adapter
through the runner against the second Greenhouse-style stand-in (`gh2_dd`, `gh2_sections`,
`gh2_loc_search`; FIXTURE ASSUMPTIONS), with the receiver's ledger as the oracle; or drive the
probe, the choice or the survey on the stand-in's page in Chromium.

| Claim | Test | Result |
|---|---|---|
| The adapter's classification leaves out the whole page's 150 ms check; the survey's keeps it | `test_list_record.py::test_the_adapters_classification_leaves_out_the_whole_pages_check`; `test_dropdown_strategies.py::test_settled_means_unchanged_by_the_pages_own_record` (the page changed 20 ms before) | one probe read: `partially_observed` (`still_changing`) by the survey's classification, `observed_sufficiently` by the adapter's; the engine settles three equal reads with the page's last change 20 ms old |
| A page busy elsewhere has its lists settle in a real page's window | `test_dropdown_strategies.py::test_a_page_busy_elsewhere_has_its_lists_settle_in_a_real_pages_window` (a change every 100, 250, 300 ms); `test_section_list_settle.py::test_a_page_busy_elsewhere_does_not_hold_up_a_section_list` (300, 100 ms) | `confirmed`; receiver ledger: one acceptance, each approved option. Against the code before D153: the 100 and 250 ms dropdown cases and the 100 ms section case refused |
| What the page's record counts as a change to a list | `test_list_record.py` (12 cases counted, 5 not) | counted: a `<style>` added, removed, its text, its text node, one inside an added element; a stylesheet `<link>`'s attribute and its `rel` set away; the control's `aria-controls` and class; `aria-owns` on an element holding the control; the control moved; an id elsewhere. Not counted: text and an inline style elsewhere; an attribute of an element holding a `<style>`; another attribute of an element holding the control; a class elsewhere, even one a style sheet reads (the record's limit) |
| A page whose style sheet keeps changing has its lists refused | `test_dropdown_strategies.py::test_a_page_whose_style_sheet_keeps_changing_has_its_lists_refused`; `test_section_list_settle.py::test_a_list_changed_only_by_a_style_sheet_is_refused_however_slowly_it_is_read`, `test_a_list_held_back_only_by_the_pages_record_says_so`; `test_greenhouse_controls.py::test_suggestions_on_a_page_whose_style_sheet_keeps_changing_never_settle`; `test_survey_settle_rule.py::test_a_style_sheet_that_keeps_changing_holds_the_rule` | dropdowns: `failed_safe` before anything is entered (`list_changed_recently`); a section: stops naming `list_changed_recently`; the location search: `abandoned` after the search text (counted as disclosed), `LOCATION_NO_LIST`; the survey: not met |
| A list switched through its control is refused before anything is entered | `test_dropdown_strategies.py::test_a_list_switched_through_its_control_is_refused_before_anything_is_entered` (`controls_flip`, `class_flip`: every 125 ms) | `failed_safe`, "its list could not be read completely"; receiver ledger: no disclosure, nothing accepted |
| The choice takes the option from one read of the list, and reads its text again | `test_dropdown_choice.py` (5: the list unchanged; relinked, its first option hidden, a copy of the approved option first, all after the list was judged; the option given another's text after the read) | unchanged: the approved option chosen; otherwise no option clicked and the control left empty. Against the code before D153, the three changes to the list each had a wrong option clicked |
| The survey judges and compares as the adapter would | `test_survey_settle_rule.py::test_changes_elsewhere_on_the_page_are_not_a_lists` (100, 300 ms), `test_a_containers_list_on_a_page_busy_elsewhere_meets_it` (path C) | the rule met and the options compared (`options_match_api: true`); the survey's own `open_state` `partially_observed` (`still_changing`) at 100 ms, for the control's action and for the container's |
| A reset clears the style ticker | `test_survey_settle_rule.py::test_a_reset_clears_the_page_busy_elsewhere` | the page served after a reset has neither ticker |
| The surveys and the adapter's paths as before | the 38 files the change touches: 12 run on their own, 26 within the regression set | pass: the 12 on their own (354 passed on 5e42918), the other 26 within the regression set |
| Each part is needed | 21 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each of the 21 fails a test, the one named for its part |

In D145's section, the result of "A page that keeps changing elsewhere does not hold up a settled
list" ("the classification's own 150 ms check still counts changes anywhere") describes the
adapter before D153.

## The read-only survey publishes whether each list met the adapter's settle rule (D152, 2026-11-12; local only)

Nothing here ran against a real page; no run is requested. Branch `survey-settle-rule`. The runs
are the survey itself (`gh_readonly.observe_page` with widget inspection) through the real
browser path against the second Greenhouse-style stand-in's dropdowns (`gh2_dd`, FIXTURE
ASSUMPTIONS); the receiver's request log shows nothing was disclosed or accepted, and every
summary passes the leak guard. All in `tests/test_survey_settle_rule.py` unless named.

| Claim | Test | Result |
|---|---|---|
| The rule's parts, each on its own | `test_the_rule_at_the_last_read` (8), `test_nothing_is_judged_where_no_list_opened` (3), `test_a_window_shorter_than_the_adapters_publishes_the_parts_but_no_verdict` | no record of a change is quiet, 500 ms is, 499 ms is not; every read compared; the survey's own test and a pending request each keep `met` false; nothing judged where no list opened; no verdict in a window under 1.5 s |
| The numbers are the adapter's | `test_the_quiet_time_and_the_window_are_the_adapters` | 500 ms and 1.5 s, equal to `dropdowns.STABLE_MS` and `SETTLE_MS`; path A's window shorter |
| A settled list meets it; path A gives no verdict | `test_a_settled_list_meets_the_rule_in_the_adapters_window`, `test_path_a_publishes_the_parts_but_never_a_verdict` | met for all three lists on path B; on path A the parts, `met: null`, counted not applicable |
| A list that keeps changing never meets it | `test_a_list_that_keeps_changing_never_meets_it` (600 ms and 1.5 s windows), `test_a_containers_list_that_keeps_changing_does_not_meet_it` | `list_quiet: false` for every list; not met where judged |
| The survey's own test and the rule can differ | `test_the_survey_s_own_test_and_the_adapter_s_rule_can_differ` (options shown 250 ms after the click) | "observed sufficiently" at 600 ms with `list_quiet: false`; met in the adapter's window |
| Changes elsewhere are not a list's | `test_changes_elsewhere_on_the_page_are_not_a_lists` (a change every 300 ms) | `list_quiet: true` for every list |
| Pending as the adapter counts it | `test_an_answer_still_awaited_at_the_last_read_holds_the_rule` (3 s, 0 s), `test_only_the_actions_own_requests_count_as_pending`, `test_a_containers_own_request_still_awaited_holds_the_rule`, `test_a_containers_action_counts_only_its_own_requests`, `test_a_request_the_page_cancels_is_no_longer_pending`, `test_a_request_is_pending_until_it_has_finished` | a request still unfinished at the last read holds the rule; only the action's own requests count; a cancelled one is finished; one whose status has arrived is not |
| Counted as the adapter would reach the list | `test_a_list_opened_by_its_container_is_judged_on_that_action`, `test_a_list_after_an_undetermined_click_is_not_counted`, `test_a_list_is_counted_as_the_adapter_would_reach_it` (6), `test_a_skipped_widget_is_not_counted`, mixed counts in `test_only_the_actions_own_requests_count_as_pending` | the container's list counted after a click that opened nothing, not after an undetermined one; skipped widgets not counted |
| Nothing judged without a list | `test_a_list_that_never_opens_is_not_judged`, `test_a_control_that_leaves_the_page_is_not_judged`, and the address-change test in `test_widget_inspection.py` | all four `null` |
| A reset clears the stand-in's ticker | `test_a_reset_clears_the_page_busy_elsewhere` | the page served after a reset has no ticker (D145's leaked into later tests) |
| The surveys as before | `test_widget_inspection.py`, `test_widget_detector.py`, `test_locale_observation.py`, `test_dropdown_observation_c.py` (the container record's keys), `test_readonly_cli_process.py`, the adapter's dropdown tests | pass, within the 15 suites the change touches (677 passed on 26e6cdc) |
| Each part is needed | 22 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each of the 22 fails a test |

## A section's combobox chooses only from a list that has settled (D151, 2026-11-12; local only)

Nothing here ran against a real page or a real account; no real Greenhouse section has been
observed. Branch `section-list-settle`. The runs are against the second Greenhouse-style stand-in's
education section (`gh2_sections`) and its list behaviours (FIXTURE ASSUMPTIONS); the receiver's
ledger is the oracle for what was sent. "On the page" rows drive the stand-in's page in a browser
without the runner. All in `tests/test_section_list_settle.py` unless named.

| Claim | Test | Result |
|---|---|---|
| A list that arrives late is chosen from once it has settled | `test_a_section_list_that_arrives_late_is_chosen_from_once_it_has_settled` (4: loading for 0.3 s and 2.5 s; react-select's notice and indicator for 1.5 s; one placeholder option until a same-origin GET answers after 1.2 s) | `confirmed`, the approved options sent; each list waited for its own answer |
| A list that never settles stops the section, nothing chosen | `test_a_section_list_that_does_not_settle_stops_the_section` (4: re-rendered every 60 ms or 300 ms; a style sheet hiding another option every 300 ms; loading for ten minutes) | `abandoned`, "#school--0: its list did not settle in time", never the value; nothing accepted |
| How often it is read does not decide (D145) | `…_keeps_changing_is_refused_however_slowly_it_is_read` (read every 590, 600, 610, 1200 ms), `…_has_settled_is_chosen_from_when_read_slowly` (2) | refused; settled lists still chosen from |
| Changes elsewhere on the page are not a list's | `test_a_page_busy_elsewhere_does_not_hold_up_a_section_list` (every 300 and 600 ms in a stand-in's window, every 600 ms in a real page's) | `confirmed` |
| Requests as a dropdown's (D104, D108) | `test_a_section_list_whose_opening_sends_or_fails_to_load_is_refused` (a POST by fetch, by sendBeacon; a GET answered 404) | `abandoned`, "its options load from the network in a way NoEfforts does not accept" |
| Exactly one option reads the approved text, and it is shown | `test_an_approved_option_the_list_does_not_show_is_never_clicked`, `test_a_hidden_copy_of_the_approved_option_refuses_the_list` | refused before any click |
| On the page: nothing clicked, the list closed, nothing left behind | `test_no_option_is_clicked_in_a_section_list_that_never_settles`, `test_the_probe_is_set_for_the_choice_and_taken_off_after` | the control empty, no option selected, the list closed; the observer and the request listeners removed after a refusal and after a choice |
| The windows | `test_a_real_pages_window_is_shorter_than_a_stand_ins`, `test_a_control_that_never_opens_stops_the_wait_after_a_real_pages_window` | a list loading for 3.5 s refused in a real page's window and chosen from in a stand-in's; a control that never opens given up after six reads |
| A list changed after it settled is not chosen from | `test_a_list_changed_after_it_settled_is_not_chosen_from` (reversed, the option re-keyed, a copy added) | refused, "its list changed before the choice"; nothing selected |
| A control leaving the page | `test_a_control_that_leaves_the_page_while_its_list_is_read_stops_at_once` | refused, "is no longer on the page", within 6 s (2 s to close the list) |
| The tests tell the old rule apart | the 30, with `greenhouse_sections.py` and `greenhouse_dom.py` as before D151 | 25 fail; the five that pass must pass either way (a settled list read slowly, a page busy elsewhere, a hidden copy of the approved option) |
| The sections as before | `test_section_widgets.py`, `test_greenhouse_sections_browser.py`, `test_greenhouse_sections_e2e.py`, D150's section stop tests in `test_worker_stop.py` | pass, within the 15 suites the change touches (423 passed on 21e2289) |
| Each part is needed | 20 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each of the 20 fails a test |

## A request to stop the worker honoured before the next protected step (D150, 2026-11-12; local only)

Nothing here ran against a real page or a real account. Branch `worker-stop-request`. The runs
are against the local stand-ins (FIXTURE ASSUMPTIONS); the receiver's ledger is the oracle for
everything said to have reached the employer. "In-process" rows run the runner in the test
process with the request set at a named point (a test-only fault action, `stop`, or a stand-in
for one step); the "real worker" rows start a Celery worker (prefork, one process) and send its
main process SIGTERM, as `docker compose stop` does. All in `tests/test_worker_stop.py`.

| Claim | Test | Result |
|---|---|---|
| The flag reaches a pool process: forked after the import, or a new interpreter mapping the file named at `worker_init`; the file is removed at `worker_shutdown` | `test_the_flag_is_shared_with_a_process_forked_after_it_and_starts_cleared`, `test_shared_through_its_file_a_process_started_afresh_sees_the_request` | the child sees the parent's later request; a new process starts cleared; the file is gone after `unshare` |
| Before anything is entered, the attempt goes back in the queue; the next worker sends it once | `test_stopped_before_anything_is_entered_the_attempt_goes_back_in_the_queue` (4 adapters) | `pending`, a new outbox message, the receiver asked nothing; then `confirmed`, accepted once |
| After the disclosure gate, abandoned for good | `test_stopped_after_the_disclosure_gate_the_attempt_is_abandoned_for_good` (4 adapters, 2 points) | `abandoned` with the stop's text; no upload before the first field; never run again; the requeue never asked for (its refusal once data was entered stays a second guard) |
| Counted with the sweeper's re-queues | `test_a_third_stop_in_a_row_before_entry_fails_safe_as_the_sweeper_would` | `requeued`, `requeued`, `failed_safe` ("Worker kept stopping…"), `failed_retryable` |
| Past the send gate the click and its outcome are completed; an error there is unknown | `test_after_the_send_gate_the_click_and_its_outcome_are_completed`, `test_an_error_after_the_send_gate_while_stopping_is_an_unknown_outcome` | `confirmed`, accepted once; `unknown`, `submitted_unconfirmed` |
| Before the claim, nothing claimed, a new message | `test_a_worker_asked_to_stop_claims_nothing` | `pending`, generation 0, one new message; the next worker sends it once |
| A wizard stops before the next page's step | `test_on_a_wizard_a_stop_request_ends_the_run_before_the_next_page_step` (2 points) | drafts saved: none, or page 1 only; no step recorded past the stop; every approval retired |
| Each gate reads the request last and commits nothing | `test_a_stop_while_the_disclosure_gate_runs_records_nothing_and_requeues`, `…_send_gate_runs_never_clicks`, `…_a_wizard_s_step_gate_runs_records_no_step` | no disclosure stamp or event (re-queued); no `send_authorized`, nothing accepted; no `step_authorized` |
| A browser lost while stopping is the stop's | `test_an_error_while_the_worker_is_stopping_ends_as_the_stop_does` (2), `test_a_stop_while_the_first_page_loads_puts_the_attempt_back_at_once` (2), `test_a_browser_that_cannot_be_started_while_stopping_is_the_stop_s` | re-queued or abandoned with the stop's text, never "internal error"; the first page's wait ends well within its eight seconds |
| Between controls on the adapters | `test_workday_section_entries_stop_at_the_next_control`, `test_greenhouse_section_controls_stop_at_the_next_one`, `test_greenhouse_section_rows_are_not_added_after_a_stop`, `test_on_greenhouse_pages_the_stop_is_read_after_the_page_settles_from_an_upload`, `test_on_the_hosted_form_a_stop_during_the_wait_for_a_shown_question_enters_it_not`, `test_a_stop_during_a_heartbeat_is_read_before_the_step_it_precedes` | no page action after the request (every typing, click, choice and upload recorded); one section control entered; no "Add another"; no document sent |
| A rehearsal that has filled ends as rehearsed | `test_a_rehearsal_that_has_filled_ends_as_rehearsed` | `rehearsed`, nothing accepted |
| The code wait enters no code after the request | `test_waiting_for_a_code_a_stop_request_leaves_the_verification_unfinished`, `test_a_code_taken_after_the_stop_request_is_never_entered_and_is_erased` | "Verification was not completed: …"; the challenge not done, no code given to the employer; the request closed, its code erased |
| The API route | `test_on_the_api_route_a_stop_request_ends_the_run_before_its_next_request` (3), `test_a_stop_while_the_api_reads_the_job_s_schema_puts_the_attempt_back`, `test_a_stop_while_the_api_creates_the_draft_sends_no_document`, `test_on_the_api_route_an_error_while_the_worker_is_stopping_ends_as_the_stop_does` (2) | the API asked nothing, or only the schema (re-queued); no draft after the gate; no document after the draft; never submitted; the requeue never asked for after the gate; an error with a stop requested (the schema's answer cut off, as urllib raises it, or an error after the gate) re-queued or abandoned with the stop's text, never "internal error" |
| The re-queue's fence; a new message only for a waiting attempt | `test_the_requeue_writes_nothing_for_a_worker_that_no_longer_holds_the_attempt`, `test_a_new_message_is_queued_only_for_an_attempt_still_waiting` | nothing written for another worker or generation, a cancel, an expired lease or data entered; no message for a cancel requested or a claimed attempt |
| Playwright without its own signal handling; the worker stopped first, with time for a click's answer | `test_the_browser_is_launched_without_playwright_s_own_signal_handling`, `test_the_worker_stops_before_its_browser_and_waits_for_a_click_s_answer` | `handle_sigint/sigterm/sighup` false; `depends_on` the runner and the proxy; `stop_grace_period` ≥ the real-page watch + 20 s |
| A real worker told to stop (SIGTERM) | `test_a_real_worker_told_to_stop_…` (5: before the send gate, before opening the form, after the send gate, in the code wait, as it takes an attempt) | as above, with the receiver's ledger; the flag file made at start and removed at exit; the worker exited 2.3 to 2.5 s after its held process was released |
| Each part is needed | 46 changes, one at a time, the named tests run, the file restored (`docs/implementation-status.md`) | each fails a test: 43 with the tests named first; one more against the whole file; the last two after two tests were added (aeab20d) |

## Workday-style Work Experience: your approved work history entered on My Experience (D149, 2026-11-12; local only)

Nothing here ran against a real page or a real account, and no real Workday work-history section
was observed. Branch `wizard-experience` (from D148's branch). The section, its entries and the
page's own checks are the stand-in's FIXTURE ASSUMPTION FA7 (`fixtures/ats_receiver/workday_like.py`).
The receiver's ledger is the oracle for everything said to have reached the employer: its
`draft_page` rows (a wizard page's Next) and its acceptances. The rows marked "a page set in the
browser" drive the adapter or the executor on a page set in Chromium, with no receiver. Tests in
`tests/test_workday_experience.py`.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Capture reads the section as an employment section, never its controls as questions | `test_capture_reads_the_section_and_never_its_controls_as_questions`, `test_entries_are_never_read_as_questions_however_many_or_unlabelled` | kind, `#id` root, no page on a single page; empty entries at load accepted; `aria-required` read; only the résumé is a question; 50 entries (350 controls) or an unlabelled one read without error |
| On the wizard, the section is on its page | `test_on_a_wizard_the_section_is_on_its_page` | `step` "My Experience"; no `work…` question; the receiver's ledger empty (capture reads, never sends) |
| Any other work history is one required checkpoint | `test_any_other_work_history_is_one_required_checkpoint` (53 cases), `test_controls_named_as_entries_without_a_section_are_a_checkpoint` | another control or part, a part missing, absent, twice, split or of another kind, a value in the template or an entry, a ticked box, entries not numbered from 0; no Add, two, a submitting, disabled, hidden or wrongly named one, another clickable control, a button in an entry; no template, one unfound or inside the form or the section; an entry outside the section; two sections, another kind, another marker; an id badly formed, too long, with a line break or used twice; a hidden or disabled section or control, read-only, length or pattern limits; a required box or a required control NoEfforts leaves empty; a date that does not say MM/YYYY; a custom control; a page name too long: no section, no `work…` question, `work_experience` required and unsupported |
| A page question sharing a checkpoint's key never hides it, and is held to the page rule | `test_a_page_question_named_like_a_checkpoint_never_hides_it` (3 keys), `test_a_page_question_named_like_a_checkpoint_is_on_its_page_like_any_other` (4 keys) | the checkpoint replaces it, its key once; on the review page, `bot_check` included, the wizard is refused (the several-pages checkpoint) |
| A page without the section reads as before; a Greenhouse section is stored and fingerprinted as before | `test_a_page_without_the_section_reads_as_before`, `test_a_greenhouse_section_reads_and_fingerprints_as_before` | the default page's fingerprint equals the one pinned before D142; no section and no checkpoint; the Greenhouse fingerprint equals the formula before D149 |
| The section's page and requirement are part of the form | `test_the_section_s_page_and_requirement_are_part_of_the_form` | three different fingerprints; a page named so it would read as another page and requirement fingerprints apart; the review page, or a page on a form with none, refused |
| The package freezes your approved work history on its page | `test_the_package_freezes_your_work_history_on_its_page` | rows newest first as on Greenhouse, a current role's end date omitted; `step` "My Experience" |
| A required section waits for your approved work history | `test_a_section_the_page_requires_needs_your_approved_work_history` | `section:employment` unresolved with its message; approval refused (409); one record approved: resolved, approved |
| A line break or a blank is a checkpoint when the package is built | `test_a_line_break_or_a_blank_is_a_checkpoint_when_the_package_is_built` (2 cases) | the title or the employer needs you |
| Work history the section cannot take blocks approval | `test_work_history_the_section_cannot_take_blocks_approval` | `work_experience` unresolved; no section frozen; approval refused |
| Each entry is added, entered on its page and sent | `test_each_entry_is_added_entered_on_its_page_and_sent` | receiver ledger: drafts for pages 1 to 4, page 2's with both entries exactly as approved (the current role's To empty, its box ticked; Location and Role Description empty), no other page's with any; the acceptance the same; nine `section_field` disclosures in order; every page read back with no mismatch |
| With no approved work history, no entry is sent; a required section is sent with yours | `test_with_no_approved_work_history_no_entry_is_sent`, `test_a_required_section_is_sent_with_your_entry` | page 2's draft and the acceptance: no entry; the required one: yours |
| An entry a parsed resume adds is never sent | `test_an_entry_a_parsed_resume_adds_is_never_sent` (one record, none) | `abandoned`; receiver ledger: a draft for page 1 only, no submit; page 2's readback mismatched |
| An empty entry already there is filled in place | `test_an_empty_entry_already_there_is_filled_in_place` (one record, two) | page 2's draft: entry 0 as approved, entry 1 added for the second record |
| Before anything is entered: more entries than approved | `test_an_empty_entry_with_no_record_for_it_stops_before_anything_is_entered`, `test_a_page_showing_an_entry_after_approval_stops_before_anything_is_entered` | `failed_safe` with the "more entries" text; receiver ledger empty (no draft, no upload); nothing entered |
| A stop after an entry keeps what was entered | `test_a_stop_after_an_entry_keeps_what_was_entered` | `abandoned` with the section text; a draft for page 1 only; the first entry's four controls recorded as disclosures |
| An entry changed after its page was saved is never sent on | `test_an_entry_changed_after_its_page_was_saved_is_never_sent_on` | `abandoned`; drafts for pages 1 and 2 only; page 3's readback (every page before it) mismatched |
| A build that cannot read the section pauses before anything is entered (why no version change) | `test_a_build_that_cannot_read_the_section_pauses_before_anything_is_entered` | the section-blind read simulated: `failed_safe`, an open form-change pause, receiver ledger empty |
| An entry that will not appear stops the attempt | `test_an_entry_that_will_not_appear_stops_the_attempt` | `abandoned` with the section text; a draft for page 1 only, no submit; no section disclosure |
| A section changed after approval pauses before anything is entered | `test_a_section_changed_after_approval_pauses_before_anything_is_entered` | `failed_safe` with an open form-change pause; receiver ledger empty |
| A work history edit retires the approval (D140) | `test_a_work_history_edit_retires_the_approval` | the record the package sends edited: every approval retired; approved again, the new title in page 2's draft |
| On the single page, each entry is entered and sent | `test_on_the_single_page_each_entry_is_entered_and_sent` | the acceptance holds both entries exactly as approved |
| The plan; a frozen section it cannot enter exactly | `test_the_plan_enters_what_was_approved_and_leaves_the_rest_empty`, `test_a_frozen_section_it_cannot_enter_exactly_is_refused` (7 cases) | ops and blanks per entry, scoped to the section; bad month or year, education, a non-`#id` root, a record twice, an unknown or unresolved field refused |
| Before anything is entered (a page set in the browser) | `test_before_anything_is_entered_a_section_off_its_page_stops_the_attempt`, `…_a_section_it_cannot_enter_is_a_plain_stop`, `…_an_entry_it_cannot_type_into_stops_it` (4 cases), `…_entries_beyond_the_approved_ones_stop_it`, `…_entries_holding_values_stop_it` | refused, nothing entered: off its page, unplannable, an entry hidden, in a disabled fieldset, read-only or disabled, more entries than approved, a value a script put there |
| Entering and reading back (a page set in the browser) | `test_entries_are_added_entered_and_read_back`, `test_a_value_is_entered_and_read_back_exactly`, `test_the_add_button_is_found_by_its_text`, `test_the_readback_finds_every_difference_and_any_entry_beyond_the_plan`, `test_an_empty_entry_beyond_the_plan_is_found_too`, `test_a_section_the_page_no_longer_has_is_found`, `test_the_readback_refuses_a_control_left_empty_that_the_page_requires` | nine controls entered in order; spaces kept; a line break refused; the button found by its text; a filled description, a To, a title, a box, a third entry, an empty one, a missing section, a required To or box left empty: each reported, never a value |
| Stops while entering (a page set in the browser) | `test_an_entry_that_does_not_appear_stops_with_what_was_entered`, `test_a_section_without_one_add_button_is_never_clicked`, `test_a_section_whose_one_button_is_not_its_add_is_never_clicked`, `test_a_control_that_does_not_keep_its_value_stops_the_entry`, `test_a_browser_error_while_entering_is_the_section_s_stop` | refused, with what the page was given reported (a control not kept, or one the browser failed on, included) |
| The adapter (a page set in the browser) | `test_the_adapter_enters_a_single_page_s_section_and_reads_it_back`, `test_each_entry_control_is_reported_to_the_runner_as_it_is_entered`, `test_on_a_wizard_a_section_is_entered_and_read_back_with_its_own_page` | disclosures per control, each reported to the runner's recorder as made; page 1 fills and reads back nothing of it; page 2 does |
| The package contract | `tests/test_package_contract.py` | `.sections[].step` recorded under version 3 |
| Each part is needed | 43 changes on 5e891ad, 64 on e30ba41 and 83 on bdb5311, each in turn (D149 in `docs/decisions.md`); one of the 64 made the module fail to compile and so showed nothing (replaced by a valid change in the next round) | each fails a test |

## A Workday-style follow-up question, entered only when the page shows it (D148, 2026-11-11; local only)

Nothing here ran against a real page or a real account, and no real Workday follow-up question
was observed. Branch `wizard-follow-up` (from D147's branch). The question and when it is shown
are the stand-in's FIXTURE ASSUMPTION FA6 (`fixtures/ats_receiver/workday_like.py`). The
receiver's ledger is the oracle for everything said to have reached the employer: its
`draft_page` rows (a wizard page's Next) and its acceptances. The rows marked "a page set in the
browser" drive the adapter on a page set in Chromium, with no receiver. Tests in
`tests/test_workday_follow_up.py`.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Capture marks a control hidden at load inside its page, by any of the markup signals, and nothing else | `test_capture_marks_a_question_hidden_inside_its_page` (8 cases) | `hidden`, `aria-hidden="true"`, `display: none`, `visibility: hidden !important` on a wrapper, and `hidden` on the control itself: `Condition(UNKNOWN_TRIGGER)`; a hidden sibling closed before it, `display: block` and `aria-hidden="false"`: no condition; the trigger never marked |
| A checkpoint stays one; a hidden choice is marked (and never filled) | `test_capture_never_marks_a_checkpoint_and_marks_a_hidden_choice` | a hidden picker stays unsupported with no condition; a hidden radio group carries the condition |
| A hidden file input, and a group with one option hidden, are never marked | `test_capture_never_marks_a_file_input_or_a_group_partly_shown` | the file input and the group carry no condition |
| Only the application form, and only below it | `test_capture_reads_only_the_application_form` | a hidden wrapper around the whole form, and hidden controls of the same names outside it (a template, outside the form), mark nothing |
| A wizard page hidden at load marks none of its questions | `test_a_wizard_page_hidden_at_load_marks_none_of_its_questions` | of every question on pages 2 to 4, only the follow-up carries the condition, on its page, optional |
| Only you answer it, never saved for reuse | `test_it_is_yours_to_answer_and_never_saved_for_reuse` | blank and optional, open to your answer, neither bankable nor draftable, explained as shown by the page |
| Required in the markup, it waits for your answer | `test_one_required_in_the_markup_waits_for_your_answer` | unresolved, approval refused; answered, nothing unresolved |
| Shown, it is entered on its page and sent | `test_shown_it_is_entered_on_its_page_and_sent` | receiver ledger: drafts for pages 1 to 4, page 4's with the answer; the acceptance has it; every page read back with no mismatch; the check after the last Next matched |
| Not shown, it is never entered or waited for | `test_not_shown_it_is_never_entered_or_waited_for` (answered or not) | Days chosen: page 4's draft and the acceptance hold it empty; confirmed |
| Shown, optional and unanswered, it stays empty | `test_shown_optional_and_unanswered_it_stays_empty` | page 4's draft and the acceptance hold it empty; confirmed |
| Shown, required and unanswered: the wizard page's Next is never clicked | `test_shown_required_and_unanswered_stops_before_its_next` | `abandoned` with the conditional-required text, naming no question; receiver ledger: drafts for pages 1 to 3 only, no POST to draft 4 or the submit; a gate before page 4's fill and none before its Next; no pause |
| Required only once shown, and answered: still the approved form | `test_required_once_shown_and_answered_it_is_sent` | page 4's draft and the acceptance have the answer; confirmed |
| Required in the markup and answered, but not shown | `test_required_in_the_markup_and_answered_is_entered_only_when_shown` | page 4's draft and the acceptance hold it empty; confirmed |
| One the page now requires, approved optional: nothing is entered | `test_one_the_page_now_requires_stops_before_anything_is_entered` (wizard, single page) | `failed_safe` with an open form-change pause; receiver ledger: no disclosure, no acceptance; nothing entered |
| One the page removes instead of hiding stops the attempt | `test_one_the_page_removes_instead_of_hiding_stops_the_attempt` (wizard, single page) | `abandoned`; receiver ledger: no submit; on the wizard drafts for pages 1 to 3 only, no POST to draft 4, the follow-up text |
| One the page requires while hidden stops the attempt | `test_one_the_page_requires_while_hidden_stops_the_attempt` (wizard, single page) | `abandoned` with the "left empty" text; receiver ledger: no submit; on the wizard drafts for pages 1 to 3 only |
| The same shape, shown, is sent | `test_one_the_page_requires_while_hidden_is_sent_once_shown` | the acceptance has the answer; confirmed |
| An approval from before D148 pauses; a fresh read marks the question | `test_an_approval_from_before_d148_pauses_and_a_fresh_read_marks_it` | the capture simulated without the condition: `failed_safe`, receiver ledger empty; reading the form again ends the pause, and the package's row carries the condition |
| A single page: shown, entered and sent | `test_single_page_shown_it_is_entered_and_sent` | the acceptance has the answer |
| A single page: not shown, never waited for | `test_single_page_not_shown_it_is_never_waited_for` | the acceptance holds it empty; confirmed |
| A single page: shown, required and unanswered pauses for your answer | `test_single_page_shown_required_and_unanswered_pauses_for_your_answer` | receiver ledger: no submit, no acceptance; an open `conditional_required` pause counting 1; the attempt entered data and never reached the send gate; the question now asks for your answer |
| After filling, what the page shows is what was entered | `test_after_filling_what_the_page_shows_is_what_was_entered` (8 cases, a page set in the browser) | entered then hidden, or shown and answered but not entered: a stop; shown, required, unanswered and typed: `ConditionalRequired(1)`; a shown required choice: a stop that sends you to the employer's site; hidden, required and empty: a stop; shown optional unanswered, hidden and not entered, shown and entered: nothing |
| Before filling, a shown one is left to the fill | `test_before_filling_a_shown_one_is_left_to_the_fill` (a page set in the browser) | at open, no finding; once filled, the same page is one |
| A question hidden once answers were entered is the page's reaction | `test_a_question_the_page_hides_once_answers_were_entered_is_its_reaction` (a page set in the browser) | visible when approved, hidden now: before filling a changed form, after filling none |
| The live form, shown or hidden; required compared before entry, the page's reaction after; its wording counts | `test_the_live_form_reads_as_approved_shown_or_hidden_and_once_filled_required_or_not` (a page set in the browser) | shown now: matches; required before entry: `FormChanged`; after entry: matches; reworded: `FormChanged` |
| A removed one never waited for at readback | `test_readback_never_waits_for_a_question_the_page_removed` (a page set in the browser) | not entered: nothing to read; entered: did not keep its value; under 5 s |
| Before a wizard page's Next, a removed or reworded one stops it | `test_before_a_wizard_page_s_next_a_removed_or_reworded_one_stops_it` (a page set in the browser) | removed: the follow-up stop; reworded while shown, optional and empty: "the form has changed"; as approved: nothing |
| A wizard rechecks what its filled pages left empty | `test_a_wizard_rechecks_what_its_filled_pages_left_empty` (a page set in the browser) | another page filled: nothing; its own page filled, then required while empty: the "left empty" stop |
| A shown one that cannot be typed into is never waited for | `test_a_shown_one_that_cannot_be_typed_into_is_never_waited_for` (a page set in the browser) | disabled: not entered, under 5 s; the check after filling stops it |
| The readback catches a value the page put in one not entered | `test_readback_catches_a_value_the_page_put_in_one_not_entered` (a page set in the browser) | the follow-up reported |
| An approved value for a hidden choice is refused before anything is entered | `test_an_approved_answer_to_a_choice_the_page_shows_by_itself_is_refused` (a page set in the browser) | refused, as D135; with no value: nothing |
| Pages without such a question read as before | `tests/test_workday_wizard.py` (`test_non_wizard_fingerprints_are_unchanged`) and the suites the change touches | the default page's pinned fingerprint unchanged; the suites the change touches passed: 234 tests before the reviews, 302 after the first, 312 on 67e382f |
| Each part is needed | 23 changes on 9c3bf1c, 30 on 4f90edc and 38 on 67e382f, each in turn (D148 in `docs/decisions.md`); one of the 38 (controls outside the form) failed a test only once its test covered a visible control of the same name outside the form (a9f4222) | each fails a test |

## A restored database comes up held, and nothing it restored runs (D147, 2026-11-11; local only)

Nothing here ran against a real page or a real account. Branch `restore-hold` (from D146's
branch). A restore is made here by giving the database's stamp another database's identity,
which is what a restore leaves behind; one test makes a real copy of a migrated database
(`CREATE DATABASE ... TEMPLATE`), and the Compose smoke test (CI only, not run locally) a real
dump and restore. The receiver's ledger is the oracle for everything said to have reached the
employer. Every form is a local stand-in. Tests in `tests/test_restore_hold.py` unless another
file is named.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A database stamps itself with its own identity and is not held | `test_a_database_stamps_itself_and_is_not_held` | one stamp, the database's own oid and its cluster's identifier; resolving does nothing |
| A copy of a migrated database is held; the original is not; the downgrade refuses while held | `tests/test_migrations.py`: `test_d147_the_stamp_is_the_databases_own_and_a_copy_of_it_is_held` | the upgrade stamps the database it runs in; a real copy of it (another database, the same rows) is held, the original is not; with another database's stamp the downgrade raises; without it, the table is dropped |
| A database with no stamp is not held | `test_a_database_with_no_stamp_is_not_held` | a queued attempt is claimed as usual |
| A restore onto another server is held, though its oid is the same | `test_a_restore_onto_another_server_is_held_though_its_oid_is_the_same` | with another cluster's identifier and this database's oid, the claim refuses; resolving ends the queued attempt and keeps only this database's stamp. (Two new clusters gave their first database the same oid, 16384, measured outside the tests) |
| A stamp the new server wrote first does not hide the restore | `test_a_stamp_the_new_server_wrote_first_does_not_hide_the_restore` | this database's stamp and the backup's side by side: held, the claim refuses; resolved, only this database's is left |
| Held, nothing is claimed, queued or approved | `test_a_restored_database_takes_nothing_and_queues_nothing` | the claim refuses, a delivery is ignored, the attempt stays queued; queueing another application and approving a third are refused (409, `restored_backup_held`); receiver ledger: nothing |
| The standing rule does nothing while held, and leaves to you what began before the restore | `test_the_standing_rule_does_nothing_while_held` | its tick approves and queues nothing; resolved, it is paused; resumed, it skips the application with `restored_from_backup` and approves nothing |
| What was queued is quarantined, never run; an approval of an application not queued is retired too | `test_resolving_ends_what_was_queued_and_never_runs_it` | the attempt `unknown` with its explanation, its application `submitted_unconfirmed`; both applications' approvals retired (`restored_from_backup`, audited); its unpublished message never published; the relay and the republishing pass publish nothing; receiver ledger: nothing |
| Each state in progress quarantined, never back in the queue | `test_resolving_quarantines_each_state_in_progress` (4 cases) | taken before anything was entered, entered, sending, waiting for a code: `unknown` with the phase's explanation, the application `submitted_unconfirmed`, the cancel requested, the claim refuses each; receiver ledger: nothing |
| A rehearsal in progress quarantined too | `test_a_rehearsal_in_progress_is_quarantined_too` (2 cases) | queued and entered: `unknown`, the application `submitted_unconfirmed` (the submission after a rehearsal may have been sent); the claim refuses each; receiver ledger: nothing |
| A verification request ends with its attempt | `test_a_request_for_a_code_ends_with_its_attempt` | a request holding a code: `expired`, its code erased |
| An application in a state the restore does not expect | `test_an_application_in_a_state_it_does_not_expect_is_left_as_it_is` | its attempt ended `unknown`, the application not moved, the pass finished |
| The sweeper leaves a held database to the resolver | `test_the_sweeper_leaves_a_restored_database_to_the_resolver` | an entered attempt with an expired lease: the sweep does nothing while held; resolved, `unknown` and quarantined |
| Cancelling, revoking and pausing wait for the resolver | `test_cancelling_revoking_and_pausing_wait_for_the_resolver` | cancel and revoke refused (409, `restored_backup_held`); pausing pauses and leaves the rule's attempt and approval alone; resolved, quarantined |
| Every account's rule paused, with its reason; every account told | `test_resolving_pauses_every_rule_and_tells_every_account` | the rule that was on is paused (1), audited with `restored_from_backup`; both accounts' feeds have the restore item, needing action; an account made after the restore has none |
| The relay's task, and the relay command, resolve a restore first | `test_the_relay_task_resolves_a_restore_before_it_publishes`, `test_the_relay_command_resolves_a_restore_first` | nothing published, the attempt ended; a newer queued application is then published |
| A pass that stops half way is finished by the next, keeping its counts | `test_a_pass_that_stops_half_way_is_finished_by_the_next` | stopped after the first account's rule was paused: still held, the attempt ended, one pause counted; the next pass finishes with both pauses counted |
| A second resolver finds it resolved under the lock | `test_a_resolver_that_finds_it_resolved_under_the_lock_does_nothing` | an attempt queued after the resolution stays queued, its approval live |
| One resolver at a time | `test_one_resolver_at_a_time` | with the lock held elsewhere, a pass returns `busy`, the relay's task publishes nothing, the claim refuses, `restore-resolve` exits 1; then it resolves |
| A restore NoEfforts cannot recognize; the command line | `test_force_resolves_a_database_restored_another_way` | `restore-resolve` without a restore: "not held"; with `--force`: what was queued is ended; `restore-status` shows it |
| `--force` holds the database before anything else | `test_force_holds_the_database_before_anything_else` | a pass that stops before ending anything leaves the database held (its stamp of no database); the next pass resolves it |
| A real worker never runs what a restored database queued | `test_a_worker_never_runs_what_a_restored_database_queued` | a real Celery worker takes the message while the database is held: refused; resolved, the attempt is over; receiver ledger: nothing |
| A real dump and restore in the Compose stack, the guide's checks | `scripts/docker-smoke.sh` (CI only) | after the guide's restore, the app alone shows the database held; with the rest started, the scheduler resolves it (`restore-status`: not held, a `restored_at`). Passed in the pull request's CI on f102f50 (#56) |
| The stamp names no account | `tests/test_account.py` (the export decision) | the table is left out of the account export, with why; no account's rows name it |
| Each part is needed | 39 changes, each in turn (D147 in `docs/decisions.md`) | each fails a test |

## An attempt still waiting to be taken is published again (D146, 2026-11-11; local only)

Nothing here ran against a real page or a real account. Branch `republish-queued` (from D145's
branch). The rule is tested against the database with a `publish` that only records. The three
end-to-end rows use a real Celery prefork worker on the run's own Redis, and the receiver's
ledger is the oracle for everything said to have reached the employer. Every form is a local
stand-in. Tests in `tests/test_republish_queued.py`. What the rule leaves open, a restored
database first, is in D146 (`docs/decisions.md`).

| Requirement | Test | Oracle / evidence |
|---|---|---|
| An attempt still queued is published again once its message is old, and not before | `test_an_attempt_still_queued_is_published_again_once_its_message_is_old` | its message made to look a minute short of the wait: nothing; 5 s past it: published again, to the same task, the id only; the message's time and count updated; nothing again straight after; the attempt still `pending`, generation 0, never claimed |
| Only an attempt the claim would still take is published again | `test_only_an_attempt_the_claim_would_still_take_is_published_again` | the same old message with the attempt put in each of the ten other states, then with a cancel requested, then with a disclosure recorded: never published; back as it was queued: published |
| The attempt's newest message decides | `test_the_attempts_newest_message_decides` | a second message not yet dispatched: nothing (the relay publishes it); dispatched a moment ago: nothing; both old: one publication, recorded on the newer message |
| A broker that is down ends the pass and leaves the rest for the next | `test_a_broker_that_is_down_leaves_it_for_the_next_pass` | two old attempts and a `publish` that raises with a URL in its text: the longest-waiting one tried and no other, nothing counted, its age unchanged, only the error's type stored; the next pass publishes both |
| Two passes at once publish it once | `test_two_passes_at_once_publish_it_once` | a second pass run while the first is inside its publish: it skips the message and publishes nothing |
| A claim does not wait for a pass | `test_a_claim_does_not_wait_for_a_pass_that_is_publishing` | a worker's claim made from inside the pass's own publish returns before the pass ends (it was given 20 s), generation 1 |
| An attempt put back in the queue can still be revoked | `test_an_attempt_put_back_in_the_queue_can_still_be_revoked` | claimed, its worker gone, put back by a sweep (its application still running): revoking returns `cancelled`, the attempt is cancelled, the application waits for a new approval, a later claim does nothing (before the fix: a 500, nothing revoked, the attempt still pending); receiver ledger: nothing accepted |
| The wait is the setting | `test_the_wait_is_the_setting` | with the setting at 900 s, a message six minutes old is not published again; one sixteen minutes old is |
| Extra messages never add a run | `test_extra_messages_never_add_a_run` | a message added every time the attempt is queued, the worker lost each time before entering anything: claimed once when queued and once for each time the sweeper puts it back (three in all), every other delivery refused, then `failed_safe` (claims made directly; no worker runs) |
| An attempt that entered data is never claimed | `test_an_attempt_that_entered_data_is_never_claimed` | a queued attempt given a disclosure time by hand: the claim returns nothing and changes nothing; without it, the same attempt is claimed |
| The longest wait first, and no more than the limit | `test_the_oldest_wait_first_and_no_more_than_the_limit` | two old attempts and a limit of one: the older, then the newer, then nothing |
| The relay's own task does it | `test_the_relay_task_publishes_again_too` | the task run directly with a recording `publish`: 1, then 0, and once the message is old, 1; the task is in the schedule |
| The wait is five minutes and cannot be set below one | `test_the_wait_is_five_minutes_and_cannot_be_set_below_one` | the setting's default is 300; 60 is accepted and 59 refused when the settings are built |
| A message the broker lost: the application is submitted once it is published again | `test_an_attempt_whose_message_was_lost_is_sent_once_it_is_published_again` | the broker's lists emptied after the relay; with a worker running the attempt is still `pending`, unclaimed, 3 s later; published again after the wait: `confirmed`, one claim; receiver ledger: accepted 1 |
| A worker process lost before it claimed: the same | `test_an_attempt_whose_worker_died_before_claiming_it_is_published_again` | a worker told to exit before the claim: the message taken and acknowledged (queue 0, unacknowledged 0), the attempt `pending` with no claim, a sweep recovers nothing, receiver accepted 0; published again and run by another worker: `confirmed`, one claim, accepted 1 |
| A message that was not lost is still sent once | `test_an_attempt_whose_message_was_not_lost_is_still_sent_once` | published again while the first message still waits: two messages; a worker: `confirmed`, "delivery ignored" in its log, one claim; the receiver, told to accept a repeat, counted 1 |
| Each part of the rule is needed | 21 changes, each in turn (D146 in `docs/decisions.md`) | each fails a test |

## A dropdown's list settled by the page's own record of its last change to a list (D145, 2026-11-11; local only)

Nothing here ran against a real page or a real account. Branch `dropdown-settle`. Every form is
a local stand-in (FIXTURE ASSUMPTIONS), and the receiver's ledger is the oracle for everything
said to have reached the employer. Tests in `tests/test_dropdown_strategies.py` unless another
file is named. What the rule does not cover is listed in D145 (`docs/decisions.md`).

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A list that keeps being re-rendered is refused however slowly it is read, before anything is disclosed | `test_a_list_that_keeps_changing_is_refused_however_slowly_it_is_read` (the reading interval set to 590, 600, 610 and 1200 ms) | the stand-in list re-rendered every 300 ms: the attempt `failed_safe`, "its list could not be read completely", `still_changing` or `list_changed_recently`; receiver ledger: no disclosure, nothing accepted. Before D145 (measured): refused for another reason at 590 ms, judged settled at 610 ms |
| A list that has settled is still accepted when read slowly | `test_a_list_that_has_settled_is_accepted_when_read_slowly` (a list shown at once; one that arrives after 1.2 s and stays) | read every 600 ms: `confirmed`; receiver ledger: one acceptance, each of the three dropdowns carrying its approved option |
| A page that keeps changing elsewhere does not hold up a settled list | `test_a_page_that_keeps_changing_elsewhere_does_not_hold_up_a_settled_list` (an element outside every list changing every 300 ms, and every 600 ms) | `confirmed`; receiver ledger: one acceptance, each of the three dropdowns carrying its approved option. In a stand-in's window: the classification's own 150 ms check still counts changes anywhere, and a page changing something every 250 to 300 ms can have a list refused in a real page's window (D145; rank 19) |
| The same within a real page's window | `test_a_page_busy_elsewhere_passes_every_check_in_a_real_pages_window` (the stand-in given the 1.5 s a real page gets; an element outside every list changing every 600 ms) | `confirmed`; receiver ledger: one acceptance, each of the three dropdowns carrying its approved option. With the whole page's record put back (D145's first version): `failed_safe` at a check in 6 of 6 runs |
| A list that starts changing after its check is not chosen from, and nothing is sent | `test_a_list_that_starts_changing_after_the_check_stops_the_attempt_before_sending` (each list stable at its first opening, re-rendered every 300 ms from its second) | `abandoned`, "did not keep their values"; receiver ledger: nothing accepted, and disclosures (this stop comes after data was entered) |
| What the page's record takes for a change to a list | `test_the_pages_record_tells_a_change_to_a_list_from_a_change_elsewhere` | a real browser on the stand-in page with one list open, a fresh record before each change. Not the list's: an element arriving elsewhere, its text, an attribute of it. The list's: text inside an option, an attribute of one, a child of the list, an attribute of the body (which holds it), an element holding an option arriving, the list removed, and 250 changes at once |
| Settled means unchanged for half a second by that record | `test_settled_means_unchanged_by_the_pages_own_record` | the engine on a stand-in for the page's probe (no browser): three identical reads are not settled while the record stays recent, nor at 499 ms (`list_changed_recently`); they are at 500 ms, with no record at all, and with the list's record old while the whole page's is 200 ms old |
| Three equal reads are still needed | `test_three_equal_reads_are_still_needed` | the same stand-in, no record: settled at the third read and not before; reads that differ in turn are never settled (`still_changing_or_loading`, after the window's six reads) |
| A control that is gone when the observer is installed is refused | `test_a_control_that_is_gone_before_the_action_is_refused`; `test_a_control_absent_only_when_the_observer_is_installed_is_refused` | `Refused`, "the control disappeared": when it stays gone, and when it is back for every read after that instant with an earlier dropdown's quiet record (which would otherwise be taken as settled) |
| Suggestions that keep changing never count as exactly one | `tests/test_greenhouse_controls.py`: `test_suggestions_that_keep_changing_never_count_as_exactly_one` (both structures; read every 250 and every 600 ms) | the stand-in's suggestions shown in turn, every 300 ms, as one "Springfield" and as the two of that name: `abandoned`, no settled list; receiver ledger: nothing accepted, one upload and the search text counted as disclosed |
| An error from the page before the location is typed records no disclosure of it | `tests/test_greenhouse_controls.py`: `test_a_page_error_before_typing_records_no_location_disclosure` | the adapter on a page that fails while the observer is installed: `LocationStopped`, "the location search could not be completed", with only the earlier disclosures |
| Every earlier dropdown and control case holds | the two files' other 96 cases | both files whole on ae54f21: 58 and 58 passed |
| Each part of the rule is needed | 18 changes, each in turn, then 2 more for the second review's fixes (D145 in `docs/decisions.md`) | each fails a test |

## Attempts on a queue and a worker of their own (D144, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `attempt-queue` (from D143's
branch, fa36039). Real Celery prefork workers on the run's own Redis; the receiver's ledger is
the oracle for everything said to have reached the employer. Every form is a local stand-in.
Tests in `tests/test_attempt_queue.py` unless another file is named. The Compose layout itself
runs only in CI (the `docker-smoke` and `execution-compose` jobs): this sandbox has no Docker
daemon, so the rows that name a Compose scenario rest on that job, which passed on the pull
request (#53, on e40ee72).

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Only an attempt's task goes to the attempts' queue; every other task, and everything the schedule names, to the default queue; each queue has an exchange and routing key of its own | `test_only_an_attempts_task_goes_to_the_attempts_queue` | Celery's own router for every registered `noefforts.` task; the declared queues' exchanges and keys; the schedule's task names |
| Each message reaches one queue only: an attempt's (from the relay, or the task's own `delay`) the attempts' queue, a periodic task's the default queue | `test_each_message_reaches_one_queue_only` | the real broker: the length of each queue's Redis list after each publish (0/1, 0/2, then 1/2) |
| Each queue is bound to an exchange of its own name and to no other | `test_each_queue_is_bound_to_its_own_exchange_only` | the real broker's binding table after both queues are declared on a broker that never saw them |
| A worker started without `-Q` takes both queues (development, the tests) | `test_a_worker_started_without_queues_takes_both` | one real worker: the attempt `confirmed`, a periodic task received by the same worker; receiver ledger: accepted 1 |
| Two attempts waiting for codes do not hold up the periodic tasks; a third application waits in the queue, unclaimed | `test_two_attempts_waiting_for_codes_do_not_hold_up_the_periodic_tasks` | a worker of the attempts' queue with two processes, both held in the code wait, and a worker of the default queue: a sweep published then is received and finished by the second worker at once, recovering nothing; the third attempt `pending`, no claim, its message still in the broker's list; both codes entered: all three `confirmed`, one claim each; receiver ledger: accepted 3 |
| A message for an attempt on another queue is passed on and never run there | `test_a_message_on_another_queue_is_passed_on_and_never_run_there` | published to the default queue as a relay did before D144; a worker of that queue returns `forwarded`, claims nothing and makes no request to the receiver; the message is then in the attempts' list; a worker of that queue runs it: `confirmed`, one claim; receiver ledger: accepted 1 |
| A message is passed on once at most | `test_a_message_is_passed_on_once_at_most`, `test_a_message_passed_on_is_marked_as_passed_on` | a message already marked, on the default queue: the worker of that queue runs it (`confirmed`, accepted 1) and passes nothing on; the mark is set by the pass-on and only then (the task run with a delivery from the default queue, the publish recorded) |
| A task called directly (no delivery) is run | `test_a_task_called_directly_is_run` | the task function and its eager `apply`, with an unknown attempt: `ignored` (the claim's answer), nothing published |
| The attempts' worker removes its own host's stale browser directories, never a live process's | `test_an_attempts_worker_removes_its_own_hosts_stale_browser_directories` | a directory named for a process that has exited is gone after the task; one named for this process stays |
| A cleanup that fails never stops the attempt; its failure is logged by type only | `test_a_cleanup_that_fails_does_not_stop_the_attempt` | the cleanup made to raise an error whose text names a path: the task still runs the attempt and returns its result; the log has the error's type and not the path |
| A directory that vanishes under the cleanup is skipped | `test_a_directory_that_vanishes_under_the_cleanup_is_not_an_error` | a directory removed between the cleanup's two looks at it: no error, and the other stale directory is still removed |
| The smoke test's ping passes only when both named workers answered | `test_the_smoke_check_needs_both_named_workers_to_answer`; `scripts/test_smoke_lib.sh` | `scripts/smoke_lib.sh` run on Celery's real `inspect ping` reply: with the `attempts@` worker alone it fails, with `scheduler@` too it passes; the script's own cases: one worker, both, and a name that only ends like the wanted one |
| Compose: `worker` takes only the attempts' queue with one process per browser slot; `scheduler` takes only the default queue, runs the schedule, and has no runner token, no control socket and only the application's network; every declared queue has one worker | `test_deployment_config.py`: `test_attempts_have_a_worker_of_their_own_and_the_schedule_runs_once` | `docker-compose.yml` read as a file, against the queues the application declares and the runner's `MAX_SESSIONS` |
| Both overlays treat the two workers alike; the scheduler gets every owner setting and starts only once the API is healthy | `test_deployment_config.py`: `test_the_execution_test_overlay_gives_both_workers_the_same_settings`, `test_the_greenhouse_pilot_override_changes_only_what_it_says`, `test_every_owner_setting_in_the_example_reaches_the_api_and_the_worker`, `test_the_worker_and_web_app_start_only_once_the_api_is_healthy` | the three Compose files and `.env.example` read as files |
| In the Compose stack: each worker takes its own queue; while the worker's one process waits for a code, the scheduler publishes a second application, which waits unclaimed; both are then submitted once (CI only) | `compose_tests/run_execution_test.py`: `s_scheduler_runs_while_an_attempt_waits_for_its_code` | Celery's `inspect active_queues`; the broker's list lengths; the scheduler's and the worker's logs; receiver ledger: one acceptance each |
| In the Compose stack: a killed worker's attempt is swept while that worker is still down (CI only) | `compose_tests/run_execution_test.py`: `s_worker_killed_mid_submit` | the attempt `unknown` with `worker` not running and `scheduler` running; receiver ledger: at most one acceptance |

## Recovery hardening: a run budget, one task time limit, leases that follow progress, requests that end with their attempt (D143, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `recovery-hardening` (from D142's
branch, 85e0213). Every form is a local stand-in (FIXTURE ASSUMPTIONS); the receiver gains one
option, `verify_delay_s` (the code is accepted at once, its reply arrives later). The receiver's
ledger is the oracle for everything said to have reached the employer. Rows edited by hand in a
test are marked simulated. Tests in `tests/test_recovery_hardening.py` unless another file is
named.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| An attempt's task has one time limit and no soft limit; the default has no soft limit and every other task sets 240 s itself; the three parts add up to 1380 s, under the visibility timeout; the waits after the click fit their part | `test_an_attempts_task_has_one_time_limit_that_covers_the_whole_code_wait` | the registered tasks' own limits; the settings' defaults (420, 360, 600); a real Greenhouse page's wait (123 s) twice and a minute, within 360 |
| The browser runner's session and the egress proxy's session outlast the task | `test_the_browser_and_proxy_sessions_outlast_the_attempts_task` | the defaults in `docker-compose.yml`, `browser/launcher.js` and `sandbox/proxy_service.py` (1500 each), at least the limit and a minute |
| A run past its budget stops before the final click, as its phase says, and says the time limit: after opening the form, between fields, right before the send gate (generic form, gh2 by id, the pilot stand-in, Workday-style) | `test_a_run_past_its_budget_stops_before_the_final_click` (12 cases) | the run clock moved past the budget at the point (test-only `elapse`); `failed_safe` or `abandoned`, no `send_started_at`, "the run reached its time limit and was stopped", never "internal error"; receiver ledger: nothing accepted; no upload unless the form had been filled; a second run `ignored`, the request log unchanged |
| A run within its budget is not stopped | `test_a_run_within_its_budget_is_not_stopped` | 30 s under the budget at the send gate: `confirmed`; receiver ledger: accepted 1 |
| The budget never stops a run after the send gate | `test_the_budget_never_stops_a_run_after_the_send_gate` | the run clock moved past the budget right after the send gate: `confirmed`; receiver ledger: accepted 1 |
| A wizard past its budget stops for good | `test_a_wizard_past_its_budget_stops_for_good` | `abandoned` with the wizard text and the time limit; receiver ledger: draft 1 only, nothing accepted; every approval retired; a second run `ignored` |
| At the task's limit the worker process is ended, nothing is redelivered and the sweeper decides | `test_at_the_time_limit_the_worker_process_is_ended_and_the_sweeper_decides` | a real Celery prefork worker with a 32-second limit, hung after the final click: its log has "Hard time limit (32s) exceeded" and no "Soft time limit"; the broker's queue and unacked set empty 4 s later; one claim; the attempt still `sending`; receiver ledger: accepted 1; swept `unknown`, `submitted_unconfirmed`; a second run `ignored`, still 1 |
| A code typed for an attempt that then ends is erased and its request closed | `test_a_code_typed_for_an_attempt_that_then_ends_is_erased_and_its_request_closed` | a real worker process held in the code wait, then failing: the request `submitted` with the code, then `expired` with none; the same code again: 409; `unknown`, `submitted_unconfirmed`; receiver ledger: nothing accepted, the challenge not done |
| A request takes a code only while its attempt waits; the sweeper leaves a live wait alone, also in the minute after its time ran out, and closes the rest | `test_a_request_takes_a_code_only_while_its_attempt_waits_and_the_sweeper_closes_the_rest` | a real worker process held in the code wait; simulated: the request's expiry 30 s and 120 s ago (closed 0, then 1), an ended attempt with an open request (409 "not waiting for a code", nothing stored), the same holding a code (the sweep closes 1 and erases it); receiver ledger: nothing accepted |
| A code typed late in its wait is entered under a lease that covers its answer | `test_a_code_typed_late_in_its_wait_is_entered_under_a_lease_that_covers_its_answer` | a real worker process; simulated: 8 s of lease left; the receiver answers the code 12 s after accepting it (`verify_delay_s`): `confirmed`, finished after that lease had ended; the request `done`; receiver ledger: accepted 1 |
| A code accepted in the last moment of its wait is still entered; the budget does not apply after the final click | `test_a_code_accepted_in_the_last_moment_of_its_wait_is_still_entered` | a real worker process held in the code wait; the code accepted (202); simulated: the request's expiry a second ago, and the worker's clock past the end of its wait and past its budget; another code then: 409; released: `confirmed`, the request `done`; receiver ledger: accepted 1 |
| Recording evidence renews the lease and never shortens it; an expired one is never revived | `test_recording_evidence_renews_the_lease_and_never_shortens_it` | simulated leases of 2 s, the lease and 500 s, and expired: renewed to the lease, kept, `LostAuthority` (also from the heartbeat) |
| A slow form keeps its lease while it makes progress | `test_a_slow_form_keeps_its_lease_while_it_makes_progress` | a real worker process with a 15-second lease, a second before every field: `confirmed` more than 20 s after its disclosure began; receiver ledger: accepted 1 |
| A worker that stops making progress loses its lease (as before D143: no background heartbeat) | `test_a_worker_that_stops_making_progress_loses_its_lease` | 20 s without a step under a 15-second lease: `lost_authority`; swept `abandoned` (never taken over); receiver ledger: nothing accepted; a second run `ignored` |
| The send lease covers the adapter's wait for the answer: at least the submit timeout, at most the allowance, plus 30 s | `test_the_send_lease_covers_the_adapters_wait_for_the_answer` | the adapters' own answers (generic 30; Greenhouse stand-in 55; a real page 123, or 190 with a 120-second timeout; the code step on a real page 141); the lease the gate sets, exactly, for no wait, 123 s, one second under the submit timeout, and 10,000 s |
| The Greenhouse watch ends by the clock its lease was sized to | `test_the_greenhouse_watch_ends_by_the_clock_its_lease_was_sized_to` | the adapter's watch on a stand-in page object whose reads take half a second each (no browser): a 1-second watch ends `unknown` after 1.5 s, not after its five steps (3.75 s) |
| The mailbox filler entering a code while the sweeper closes its request waits for it | `test_inbox.py::test_the_mail_entering_a_code_while_the_sweeper_closes_its_request_waits_for_it` | two real PostgreSQL transactions on separate connections, the sweeper held after it locked the application; the filler waits on a row lock; neither side errors (no deadlock); swept `unknown` 1, errors 0; no code entered, the request `expired` with none stored, no inbox event |
| The runner asks the send gate for its adapter's wait | `test_a_worker_killed_after_entering_data_is_never_run_again` (the two `before_click` cases) | the killed worker's lease is exactly its send start plus the adapter's wait and 30 s (gh2 by id: 16 + 30 with the tests' 4-second submit timeout) |
| A cancel after entry says what may have been entered; before entry it says nothing was | `test_a_cancel_after_entry_says_what_may_have_been_entered`, `test_a_cancel_before_anything_was_entered_says_so` | a real worker process held before the send gate, or before opening the form; receiver ledger: nothing accepted; one upload, or none |
| A cancel while a form is filled stops the worker between fields | `test_a_cancel_while_a_form_is_filled_stops_the_worker_between_fields` | a real worker process, two seconds before every field and a renewal every four, the page saving each field as it changes (the receiver's `autosave`); cancelled once two fields were saved: `lost_authority`, the attempt `cancelled` with the after-entry text; receiver ledger: fewer saved fields than the package's answers by more than two, nothing accepted |
| A cancelled attempt hands over no document | `test_a_cancelled_attempt_hands_over_no_document` | a real worker process held after the disclosure gate, with a 240-second lease (no renewal falls due); cancelled, then released: `lost_authority`; receiver ledger: fields before the document saved (autosave), no upload, nothing accepted |
| A worker killed before anything was sent is run again once (gh2 by id, Workday-style) | `test_a_worker_killed_before_anything_was_sent_is_run_again_once` (2 cases) | exit 137 before opening the form; receiver ledger: nothing disclosed; re-pended, `confirmed`, a third run `ignored`; accepted 1 |
| A worker killed after entering data, at the send gate, around the final click or after the employer's receipt is never run again (gh2 by id, Workday-style) | `test_a_worker_killed_after_entering_data_is_never_run_again` (8 cases) | exit 137; the resume on the receiver's ledger; accepted 0, 0, 1, 1; swept `abandoned` or `unknown` (`submitted_unconfirmed`); a second run `ignored`; the request log unchanged |
| A worker killed on the wizard's review page is never run again | `test_a_worker_killed_on_the_wizards_review_page_is_never_run_again` (2 cases) | exit 137 before the send gate or before the click; receiver ledger: drafts 1 to 4, nothing accepted; swept `abandoned` or `unknown`; approving refused (`wizard_draft_at_employer`); the request log unchanged |
| A stopped wizard says what was sent and what was never done; an unanswered Next says the page may have been saved | `test_workday_wizard.py::test_a_next_is_never_clicked_twice` (3 cases) | the outcome text; receiver ledger as before (one POST to draft 2) |
| A Next whose click fails says the page may have been saved, and carries its evidence | `test_workday_wizard.py::test_a_next_whose_click_fails_says_the_page_may_have_been_saved` | the adapter's method on a page that breaks at the click (no browser): `StoppedAfterDisclosure`, the text, a `draft_page` row with ack `none` |
| Each listed check fails without what it checks | 31 changes, one at a time: 30 failed their test on the first pass; one did not (a send lease shorter than the submit timeout: the test's bounds were too loose for the tests' 4-second timeout), caught once the test compared the lease exactly; the three lease changes run again, each failing. Among the 31, two existing sweeper rules removed (never re-pend an attempt that entered data, or one that was sending): the new crash tests fail | recorded in `docs/automation-loop.md` |

## A Workday-style multi-page wizard, filled forward only (D142, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `workday-wizard` (from D141's
branch, 2dfc956). The wizard, its pages, its drafts and every `wizard` variant are FIXTURE
ASSUMPTIONS (FA1-FA5, `fixtures/ats_receiver/workday_like.py`). The receiver's ledger is the
oracle: POSTs counted per page from its request log, values read from its `draft_page` rows and
acceptances. Tests in `tests/test_workday_wizard.py`.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Capture reads every page with its step and is not a checkpoint; the package names the pages | `test_capture_reads_every_page_with_its_step` | receiver ledger: one GET, nothing disclosed; schema `wizard.pages` in FA2 order, each question's page; `exp.details` `blank_optional`; package `wizard` |
| A wizard that is not exactly what the executor drives is the several-pages checkpoint (a question on no page, a question on the review page, pages out of order or miscounted, the submit not on the last page, two Nexts, a nested step, the D88 marker beside it) | `test_a_malformed_wizard_is_a_checkpoint` (9 cases) | `workday.extract_schema`: `wizard` None, `multi_step` required unsupported; the unchanged page gives a wizard |
| Every other form's fingerprint is unchanged | `test_non_wizard_fingerprints_are_unchanged` | fingerprints of the default Workday-style page and the generic form, computed on 2dfc956 before any edit |
| Each page is sent once, in order, then one submit | `test_each_page_is_sent_once_in_order_then_submitted` | receiver ledger: draft 1, the résumé, drafts 2, 3, 4; one POST per page and one final POST; each draft exactly that page's approved values; the acceptance equals the drafts merged; events: a step gate before each step, in order, before `send_authorized`; evidence: four `step` rows, one readback, one recheck, no answer value |
| A page is read back, unanswered fields included, before its Next (contract scenario `each_step_read_back_before_next`) | `test_a_page_is_read_back_before_its_next` | receiver ledger: draft 1 and the résumé only, no POST to draft 2, nothing accepted; page 2's `step` row mismatched; every approval retired; approving refused (`wizard_draft_at_employer`) |
| A page already saved that the page changes is never sent on | `test_a_saved_page_that_changes_is_never_sent_on` | receiver ledger: draft 1 holds the approved first name; no POST to draft 2 or the submit; nothing accepted |
| A revocation or a profile edit between pages stops at the next gate; a cancel there is refused and a revocation then stops it; a profile edit after the last Next stops at the send gate | `test_a_change_between_pages_stops_at_the_next_gate` (5 cases) | a real worker process paused at `before_fill_gate_2`, `before_next_gate_2` or `before_send_gate`; receiver ledger: draft 1 (and the résumé only once page 2's fill gate passed), or drafts 1-4, never the submit; nothing accepted; every case `abandoned` with the wizard text and every approval invalidated: the revocations (also after the cancel) keep "Revoked by you", the profile edits are retired with the wizard reason; the cancel: 409 `wizard_in_progress` on both routes, the attempt still held and the application `running` |
| A lost worker mid-wizard is never taken over | `test_a_lost_worker_mid_wizard_is_never_taken_over` | sweep: `abandoned` 1, never re-pended, the wizard text; approvals retired; the released worker `lost_authority`; receiver ledger: no POST to draft 2 |
| A worker killed after a Next leaves its record | `test_a_worker_killed_after_a_next_leaves_its_record` | exit 137 at `after_next_ack_2`; receiver ledger: drafts 1 and 2; the `step_authorized` event of page 2's Next exists, its draft evidence does not; swept `abandoned`; approving refused; a second run `ignored` |
| A Next is never clicked twice: an error, no answer in time, a question revealed on a later page | `test_a_next_is_never_clicked_twice` (3 cases) | receiver ledger: one POST to draft 2 (still one after a 3-second window), none to draft 3, nothing accepted; `abandoned`, never `rejected` or confirmed; no pause row; approvals retired |
| A Next after which the page shows a confirmation or "already applied" is quarantined and never run again | `test_a_next_that_may_have_submitted_is_quarantined` (2 cases) | receiver ledger: accepted 1 or 0, no POST to the submit; `unknown` with `wizard_possibly_submitted`; `submitted_unconfirmed`; a second run `ignored`; reconciled as not received, queueing refused (`wizard_draft_at_employer`); the ledger unchanged |
| A form change, "already applied" at open and a rehearsal stop before anything is disclosed | `test_stops_before_disclosure_leave_no_mark` (3 cases) | receiver ledger: nothing disclosed, no POST; drift: a `form_changed` pause, approving refused (`form_recapture_needed`); "already applied": its text, approving still allowed; rehearsal: approving refused (`wizard_rehearsal_unsupported`), a scope set by hand (simulated) `failed_safe` with `wizard_rehearsal` |
| Once entered, never run again: approve (single and batch, also with an approval restored by hand), queue, enqueue and claim; deleting the evidence changes nothing | `test_once_entered_it_never_runs_again` | receiver ledger: nothing sent; every approval retired; 409 `wizard_draft_at_employer`; batch `refused`; queueing from where the stop left it refused as a transition (400, still `needs_user_action`); `svc.enqueue` and `pk.require_valid_approval` raise the code; a pending attempt inserted by hand in a queued application (simulated) `claim_refused_wizard_draft`, no request |
| Another account on the same posting, and the same account's other application, are not refused; the other account reaches nothing of the first | `test_another_account_on_the_same_posting_is_not_refused` | both approve (200); 404 on the first account's approve, attempts and transition; receiver ledger: nothing sent for the first application |
| An unknown final click on a wizard is quarantined and never run again | `test_an_unknown_final_click_on_a_wizard_is_quarantined_and_never_rerun` | receiver ledger: drafts 1-4, accepted 1; `unknown`, `submitted_unconfirmed`, `ignored`; reconciled as not received, queueing refused with the wizard code |
| The standing rule never drives a wizard | `test_the_standing_rule_never_drives_a_wizard` | not a rule candidate; an attempt marked as the rule's (simulated) refused at claim (`claim_refused_rule_wizard`), with the rule switched on; no receiver request |
| The step gate is fenced and ordered; `fail_safe` after disclosure abandons | `test_the_step_gate_is_fenced_and_ordered` | `LostAuthority` for a stale generation, another worker, an expired lease and after the send gate; `GateRefused` (`wizard_step_order`) before the disclosure gate, out of order, page 1 twice and on a package without a wizard; one event; `disclosure_started_at` unchanged; `pause_after_entry` False; `fail_safe` → `abandoned`; receiver ledger: the captures only |
| A cancel while the page-4 Next may submit is refused, and the Next is quarantined | `test_a_cancel_while_a_next_may_submit_is_refused_and_the_next_quarantined` | a real worker process paused at `after_next_ack_4` (`next_submits`); receiver ledger: accepted 1 before and after, no POST to the submit; the cancel 409 `wizard_in_progress`; `unknown` (`wizard_possibly_submitted`), `submitted_unconfirmed` |
| A stopped wizard stays where it stopped and is not listed for review | `test_a_stopped_wizard_stays_where_it_stopped` (an abandon, a sweep) | the application `needs_user_action` before and after reading the package and the review list; absent from `/review/packages` |
| A question moved to another page, or a renamed page, changes the fingerprint, and only through its wizard part | `test_a_question_moved_to_another_page_or_a_renamed_page_changes_the_fingerprint` | `form_fingerprint` differs, every field fingerprint equal; the `page_shift` variant reads as the move |
| A question moved to another page after approval stops before anything is sent | `test_a_question_moved_to_another_page_after_approval_stops_before_disclosure` | `failed_safe`, an open `form_changed` pause; receiver ledger: nothing disclosed, no POST to any draft |
| A Next that saves the page but does not show the next one stops there | `test_a_next_that_does_not_show_the_next_page_stops_there` (`next_stays`) | `abandoned` with the next-page text; receiver ledger: one POST to draft 2, none to draft 3; no step gate for page 3 |
| A manual form cannot set `wizard` | `test_a_manual_form_cannot_set_wizard` | 400 "'wizard' is set by NoEfforts only"; the same form without it 201; receiver ledger: no request |
| A wizard package on another adapter is refused at the disclosure gate | `test_a_wizard_package_on_another_adapter_is_refused_at_the_disclosure_gate` | a stored form given `wizard` by hand (simulated), `fixture_ats`: `GateRefused` `wizard_adapter`, no disclosure stamp; receiver ledger: nothing sent |
| A single-page package that meets a wizard stops before anything is sent | `test_a_single_page_package_meeting_a_wizard_stops_before_disclosure` | `failed_safe` with the several-pages text, no pause; receiver ledger: nothing disclosed, no POST |
| The package shape is recorded under SCHEMA_VERSION 3 | `test_package_contract.py::test_the_package_shape_is_the_one_recorded_for_its_schema_version` | `.wizard.pages[]` from a wizard captured from the receiver |
| Each listed check fails without what it checks | 63 sabotage runs, one change at a time: each of these checks' own test fails without it (the capture's wizard and its seven rules, rule 6's "not on the last page" half, the fingerprint's wizard part (made unconditional, and deleted), the order of pages and documents, each step gate, the step rows, one click, the readback before the Next and over every page so far, the gate's checks, the wizard outcome, the sweeper's branch, the event before the click, the check after a Next and the next-page check, the quarantine, the disclosure stamp, the rehearsal refusal, each never-again check and its place, its scope, the rule's claim guard, the gate's lock, order and the undisclosed guard, the cancel refusal, the settle guard, the review list's exclusion, the manual form's refusal, the `wizard_adapter` refusal, the wizard markers on a single-page package). The first pass missed three (the page-count rule, the page-order rule, `require_valid_approval`'s check), each caught once a case was added. Not sabotaged: the `settled` check and the redirect and `blocked_reason` checks after a Next, and the quarantine's own fence | recorded in `docs/automation-loop.md` |

## An employment stand-in, and section comboboxes safe on react-select pages (D141, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `section-widgets` (from D140's
branch, 08cd8bd). The employment section, its ids and every `section_widget` variant are FIXTURE
ASSUMPTIONS. The receiver's ledger is the oracle. Tests in `tests/test_section_widgets.py`.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A current role sends "current" and no end date, beside the education section | `test_a_current_role_sends_current_and_no_end_date` | receiver ledger: company, title, start month "1" and year, `current-role-0` "true", no end month or year; `school--0` |
| A past role sends its end date | `test_a_past_role_sends_its_end_date` | receiver ledger: `current-role-0` "false", end month "11", year "2018" |
| Each section adds and fills its own rows, newest first | `test_each_section_adds_and_fills_its_own_rows` | receiver ledger: two rows in each section, each from its own record |
| Nothing is typed into a section combobox | `test_section_comboboxes_are_never_typed_into` | receiver ledger: the page's own typing counter "0" |
| A react-select-style section, whose comboboxes name their list only while open (as the one real react-select recorded did, D130), is read from that list once open, read back from its single value and sends the frozen ids | `test_a_react_select_section_reads_back_from_its_single_value` | receiver ledger: school, degree, discipline ids; months |
| A choice the page ignores is never submitted | `test_a_choice_the_page_ignores_is_never_submitted` | `abandoned`; receiver ledger: nothing accepted |
| A control that records another id after choosing (an education combobox; months are matched by text only) is never submitted | `test_a_control_recording_another_id_after_choosing_is_refused` | `abandoned` ("after choosing"); receiver ledger: nothing accepted, no "zz" |
| An option that exposes another id once its list opens is never clicked; the refusal names the control, never the value | `test_an_option_exposing_another_id_is_never_clicked` | `abandoned` ("school--0", "records another id", no school name); receiver ledger: nothing accepted |
| A row the page shows beyond the plan must hold nothing | `test_a_row_the_page_shows_beyond_the_plan_must_hold_nothing` | `abandoned` ("did not keep their values"); receiver ledger: nothing accepted |
| An end date the page fills for a current role is never submitted | `test_an_end_date_the_page_fills_for_a_current_role_is_refused` | `abandoned` ("did not keep their values"); receiver ledger: nothing accepted |
| A v5 worker cannot claim a package approved at v6 | `test_greenhouse_sections_e2e.py::test_a_section_package_cannot_reach_a_section_blind_worker[greenhouse-dom-v5]`, `test_approval_binding.py` (v5 encountered) | `failed_safe`; receiver ledger empty; the approval retired, never renewed |
| Each check fails without what it checks | the old typing filler restored: 3 fail; the section readback removed: 1; both id checks removed: 1; after the review, the list read before opening: 1 (the react-select test); the id check before the click removed: 1 (its own test); the check beyond the plan removed: 1 (its own test) | recorded in `docs/automation-loop.md` |

## Education and work history reviewable and diffed (D140, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `sections-review` (from D139's
branch, 84af539). The education stand-in (`gh2_sections`) is a FIXTURE ASSUMPTION (D120); the
receiver's ledger is the oracle for what reached the employer. API tests in
`tests/test_sections_review.py` unless named otherwise.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| An education edit retires the approval at once; the reason and the notice name the section, never its values; queueing is refused | `test_an_education_edit_retires_the_approval_at_once_and_is_named_in_the_reason` | approvals; a new version built by the edit; history "education changed"; notification text; `approval_needed` |
| A section change is shown by record and field | `test_a_section_change_is_shown_by_row_and_field` | `package/diff` `sections` |
| An added and a removed record are shown | `test_an_added_and_a_removed_record_are_shown` | `package/diff` `sections` |
| A current role's end date is shown as not sent; an employment edit retires the approval and is diffed | `test_a_current_role_shows_its_end_date_as_not_sent_and_a_change_to_it_is_diffed` | package; approvals; `package/diff` |
| An edit to the other kind leaves an approval alone; another account's edit never touches yours; their diff of yours is 404 | `test_an_edit_to_the_other_kind_leaves_an_approval_alone`, `test_another_users_edit_never_touches_your_approval` | approvals, versions; 404 |
| Versions without sections diff to none | `test_versions_without_sections_diff_to_no_sections` | `package/diff` |
| Each record route retires on its own: an edit, an added record, a deleted one, approving a proposed one (no approve call follows, nothing reads the package first) | `test_an_edit_alone_retires_the_approval`, `test_adding_a_record_alone_retires_the_approval`, `test_deleting_a_record_alone_retires_the_approval`, `test_approving_a_proposed_record_alone_retires_the_approval` | approvals, versions |
| A section that becomes a question for you, or stops being one, is said so (also from an empty section), never as records removed or added | `test_a_section_that_becomes_a_question_for_you_is_said_so_never_as_records_removed`, `test_an_empty_section_that_becomes_a_question_for_you_is_a_visible_change` | `package/diff` `status` |
| On the education stand-in, an edit retires the approval; approved again, the new degree reaches the employer once | `test_greenhouse_sections_e2e.py::test_an_education_edit_retires_the_approval_and_the_new_value_is_sent` | `approval_needed`; receiver ledger: nothing, then `degree--0` "deg_mast", one acceptance |
| An edit while a worker holds the attempt is stopped at the send gate | `test_greenhouse_sections_e2e.py::test_an_education_edit_while_a_worker_holds_the_attempt_stops_it_at_the_send_gate` | a real worker process paused before the send gate; `abandoned`; receiver ledger: nothing accepted |
| The section shape is recorded under SCHEMA_VERSION 3 | `test_package_contract.py::test_the_package_shape_is_the_one_recorded_for_its_schema_version` | key paths of an education and an employment section |
| The review page shows the education sent and, after an edit, the change by record and field | `e2e/sections-review.spec.ts` (desktop and mobile) | the page |
| Each check fails without what it checks | the eager retirement removed: 2; the section diff removed: 3; the section summary removed: 1; the gate's hash check removed: 1; after the review, each route's hook removed alone: 1 or 2; the account scope removed: 1; the "needs you" status removed: 2 | recorded in `docs/automation-loop.md` |

## Your self-identification on Greenhouse- and Workday-shaped forms (D139, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `self-id-ledger` (from D138's
branch, e3e584a). The required gender (`gh2_eeo_required`), the Workday-style veteran,
Hispanic-origin and disability questions (`wd_self_identify`), the required Workday-style gender
(`wd_gender_required`) and the values each sends are FIXTURE ASSUMPTIONS. The receiver's ledger
is the oracle for what reached the employer. Tests in `tests/test_self_identification_ledger.py`
unless named otherwise.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Off, or on without a matching label, an optional gender is never sent (gh2, by id and pilot) | `test_without_a_match_you_chose_gender_is_never_sent` | receiver ledger: no `question_8113` |
| On, your label is sent; a decline label sends the form's decline (gh2, by id and pilot) | `test_opted_in_your_label_is_sent_and_a_decline_label_sends_the_forms_decline` | receiver ledger: `question_8113` "3" |
| Your "Don't disclose" for one application beats your standing self-identification | `test_your_dont_disclose_for_one_application_beats_your_standing_self_identification` | receiver ledger: no `question_8113` |
| A required gender without a match waits for you; "Don't disclose" sends the decline (gh2; Workday-style) | `test_a_required_gender_without_a_match_waits_for_you_and_dont_disclose_sends_the_decline`, `test_on_workday_pages_a_required_gender_waits_for_you_and_dont_disclose_sends_the_decline` | approval refused (`package_unresolved`), receiver ledger empty; then "3" / "Decline" |
| Turned off or changed after approval, the approval is retired at once and queueing refused; approved again, the package as it now stands is sent (gh2, by id and pilot; Workday-style) | `test_withdrawing_or_changing_it_after_approval_retires_the_approval_at_once`, `test_on_workday_pages_withdrawing_or_changing_it_retires_the_approval` | `applications_to_approve_again` 1; no live approval; reason names the question, never the value; `approval_needed`; receiver ledger: nothing, then blank or the new value |
| Turned off while queued: the queued attempt is refused before any page is opened (gh2; Workday-style) | `test_withdrawing_it_while_queued_stops_the_queued_attempt_before_anything_is_sent`, `test_on_workday_pages_withdrawing_it_while_queued_sends_nothing` | run `ignored`; receiver ledger: no request disclosed, nothing accepted |
| Turned off while a worker holds the attempt: the send gate abandons it | `test_withdrawing_it_while_a_worker_holds_the_attempt_stops_it_at_the_send_gate`; `test_execution_validation.py::test_every_protected_mutation_stops_a_running_attempt[self_identification]` | a real worker process paused before the send gate; `abandoned`, "changed after approval"; receiver ledger: nothing accepted |
| A label that changes nothing sent leaves an approval alone | `test_an_unrelated_change_to_it_leaves_an_approval_alone` | approval live; receiver ledger: "1" |
| A save also retires an approval already out of date for another reason (a phone edited after approving) | `test_a_save_also_retires_an_approval_already_out_of_date_for_another_reason` | `applications_to_approve_again` 1; the reason names the phone, not the gender; receiver ledger: the new phone and "1" once approved again |
| Workday-style: your label is sent as the option's own value; each question takes only the label naming its category; a bare "No" and two labels for one question are never used | `test_on_workday_pages_your_label_is_sent_as_the_options_own_value`, `test_on_workday_pages_each_question_takes_only_the_label_that_names_its_category`, `test_on_workday_pages_two_labels_for_one_question_are_never_guessed` | receiver ledger: `vd.gender`, `vd.veteran` "Not a veteran", `si.disability` "No"; `vd.hispanic` blank; your eligibility and sponsorship facts |
| Workday-style: a decline label declines only where the other choices name a category | `test_on_workday_pages_a_decline_label_declines_only_where_the_choices_name_a_category` | receiver ledger: gender and veteran "Decline"; Hispanic origin and disability blank |
| The standing rule sends your gender as stated; turned off after it queued the submission, nothing is sent and the rule leaves the application to you | `test_auto_apply.py::test_the_rule_sends_your_self_identification_and_withdrawing_it_stops_what_it_queued` | receiver ledger: "1"; or nothing accepted, the rule's next step `attempt_stopped` |
| The profile page opts in and, turned off after an approval, says the approval must be given again | `e2e/self-identification.spec.ts` (desktop and mobile) | the page's message; queueing refused (`approval_needed`); the package's gender blank |
| Each check fails without what it checks | the eager retirement removed: 9 tests and the e2e test; the gate's hash check removed: 2; self-identification over "Don't disclose": 3; the Workday decline wording removed: 2; the "names a category" rule removed: 1 | recorded in `docs/automation-loop.md` |

## Saved answers on Greenhouse- and Workday-shaped forms (D138, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Merged as #47 (a7f8742; built on branch
`provider-reuse` from D137's branch, 035a085); fixtures and tests only. The second Greenhouse-style fixture's jobs 5020004-5020006 and
the Workday-style mode `wd_bank_question` are FIXTURE ASSUMPTIONS. The receiver's ledger is the
oracle for what reached the employer.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A saved answer is reused on the next Greenhouse-style job asking the same question (another question id), and the employer receives it both times | `test_on_greenhouse_pages_a_saved_answer_reaches_the_next_application` | receiver ledger: 2 acceptances, the same option value |
| A look-alike that names a country is neither reused nor suggested; nothing is approved until it is answered | `test_a_question_that_only_looks_the_same_never_reuses_the_saved_answer` | package, suggestions; approval refused (409) and queueing refused (it still waits for your answer), so nothing can be sent |
| Editing a saved answer retires the approval that used it and refuses to queue it; approved again, the new answer is sent | `test_editing_a_saved_answer_asks_again_before_anything_is_sent` | approvals; queueing refused (`approval_needed`); receiver ledger: the new option value once approved again |
| On the Workday-style form, the education answer is reused and "Preferred shift" is never saved or reused | `test_on_workday_pages_a_saved_answer_is_reused_and_a_shift_never_is` | saved answers; receiver ledger: the same education, each its own shift |
| Each test fails without what it checks | reuse switched off: 3 of 4 fail; the scope check switched off: the shift test; reuse keyed on the first 36 characters: the look-alike test | recorded in `docs/automation-loop.md` |

## What reached the employer stays recorded whatever fails after it (D137, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Merged as #46 (e2fd286; built on branch
`disclosure-evidence` from D136's branch, 9602bda). Failures are injected with `NOEFFORTS_FAULT` (test-only): `raise` an unexpected
error, `exit` a killed worker. The receiver's ledger is the oracle for what reached the employer.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A completed run records each disclosure once (recorded as made, never again after filling) | `test_a_completed_run_records_each_disclosure_once` | evidence rows |
| An unexpected error after an upload keeps its evidence; the attempt is abandoned and never retried | `test_an_unexpected_error_after_an_upload_keeps_its_evidence` | receiver ledger: 1 upload, 0 accepted; evidence row |
| A worker killed after an upload leaves its evidence; the sweeper abandons it, never retried | `test_a_worker_killed_after_an_upload_leaves_its_evidence` | receiver ledger; evidence row written before the exit |
| An error during an upload counts the document as possibly received | `test_an_error_during_an_upload_counts_the_document_as_possibly_received` | evidence `ack` `none`; 0 accepted |
| The same on Greenhouse's id-only page | `test_on_greenhouse_pages_an_error_after_an_upload_keeps_its_evidence` | receiver ledger: 1 upload |
| Through the authorized API: an error after a document keeps its evidence | `test_through_the_api_an_error_after_a_document_keeps_its_evidence` | receiver ledger: the document arrived; evidence rows |
| Through the API: a document sent with no answer counts as possibly received | `test_an_api_upload_without_an_answer_counts_as_possibly_received` | evidence `ack` `no_response`; receiver ledger: it arrived |
| An error during an upload counts it as possibly received on Greenhouse's id-only page, the Workday-style page and the first Greenhouse-style page | `test_on_each_page_adapter_an_error_during_an_upload_counts_it` | evidence `ack` `none`; 0 accepted |
| A failure before the document is handed over stays an internal error, with nothing recorded | `test_a_failure_before_the_document_is_handed_over_stays_an_internal_error` | evidence: none; receiver ledger: nothing |
| An upload stop logs its cause's type and place, never its message | `test_an_upload_stop_keeps_the_type_and_place_of_what_caused_it` | log record |
| Through the API, only a refusal before anything was sent counts as never arrived (destination not enabled, no credentials, an address the fixture check refuses, a refused connection); a redirect, a reset, a timeout, a closed or broken answer may have arrived | `test_only_a_request_refused_before_sending_counts_as_never_arrived` | unit (`_may_have_arrived`) |
| Through the API, a draft or a document received then answered with a redirect, and a draft received but not created, are recorded | `test_through_the_api_a_request_answered_badly_after_it_arrived_is_recorded` | evidence `no_response` / `not_created`; receiver ledger: each arrived |
| Each test fails without its change | the recorder not installed: 4 of the first 7 fail; an interrupted upload not converted: 1; the API's unanswered upload not converted: 1; disclosures recorded again after filling: 1. Review fixes: a redirect treated as refused: 2; the uncreated draft unrecorded: 1; conversion before the hand-over: 1; the hand-over mark removed: 2 on the generic form, 1 each on the other three page adapters; the cause not logged: 1 | recorded in `docs/automation-loop.md` |

## A control NoEfforts cannot fill is refused when the form is read (D136, 2026-11-10; local only)

Nothing here ran against a real page or a real account. Branch `capture-refusals` (from `main`
53b28af), merged as #45 (32c8f7c). The second Greenhouse-style fixture is the stand-in: modes `gh2_native_select` and
`gh2_native_select_optional` render question_8104 as a native `<select>` (a FIXTURE ASSUMPTION), and
the tests add a `<select multiple>` and a consent checkbox. The receiver's ledger is the oracle for
what was submitted.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| Reading the form lets through exactly what the adapter fills (one list; every field type, as a combobox and not) | `test_capture_lets_through_exactly_what_the_adapter_fills` | unit |
| A native dropdown is refused when the form is read; the page's combobox for the same question stays a choice | `test_a_native_dropdown_is_refused_when_the_form_is_read` | form schema |
| A list of several choices on a native `<select multiple>` is refused when the form is read | `test_a_list_of_several_choices_is_refused_when_the_form_is_read` | form schema |
| A consent checkbox is refused when the form is read | `test_a_consent_checkbox_is_refused_when_the_form_is_read` | form schema |
| A required native dropdown is a checkpoint: no answer accepted here, approval refused, nothing disclosed | `test_a_required_native_dropdown_is_a_checkpoint_and_nothing_is_sent` | receiver ledger: no disclosure, 0 accepted |
| An optional native dropdown is left blank and the rest is sent (before D136: stopped as a form change, "widget", nothing disclosed) | `test_an_optional_native_dropdown_is_left_blank_and_the_application_is_sent` | receiver ledger: 1 acceptance without it |
| Each test fails without its change | the reading step's refusal removed: 5 of 6 fail; the native-dropdown rule removed: 4 of 6; the adapter given its own list, with the checkbox added: 1 of 6 (the shared-list test) | recorded in `docs/automation-loop.md` |

## A question the page shows after an earlier answer (D135, 2026-11-09; local only)

Nothing here ran against a real page or a real account. Branch `conditional-pauses` (from `main`
2e10418), merged as #44 (53b28af). The second Greenhouse-style fixture is the stand-in: question_8105 is hidden
until question_8104 is "Yes", and mode `gh2_conditional_required` (a FIXTURE ASSUMPTION) marks it
required when shown. The receiver's ledger is the oracle for what was submitted.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A typed question the page reveals is yours to answer and never saved for reuse; answered, it is resolved from your answer | `test_a_question_the_page_reveals_is_yours_to_answer` | package content |
| A saved answer or a draft is never used for it (required: it waits for your answer); your answer or an approved profile fact is | `test_a_saved_answer_or_a_draft_is_never_used_for_it` | resolution |
| While paused on such a question, every one you can answer asks for an answer; one you cannot answer here is never forced | `test_while_paused_on_such_a_question_every_one_you_can_answer_asks` | resolution |
| A choice hidden at load is still never filled (required: apply on the employer's site) | `test_a_choice_the_page_reveals_is_still_never_filled` | resolution |
| Your answer is entered when the page shows the question (by id and through the pilot) | `test_an_answer_is_entered_when_the_page_shows_the_question` | receiver ledger: the acceptance holds it |
| It is never entered when the page never shows the question | `test_an_answer_is_never_entered_when_the_page_never_shows_the_question` | receiver ledger: the acceptance lacks it |
| A revealed question the page requires, unanswered, pauses the application after filling with nothing submitted; every approval retired; counts only; listed under Questions; trying again refused until answered; then exactly one acceptance with your answer (by id and through the pilot) | `test_a_revealed_question_the_page_requires_pauses_then_one_attempt_sends_it` | receiver ledger: 0 accepted, then 1 with the answer; the pause row; the attempt's events and outcome |
| An optional question the page reveals but does not require stays blank when unanswered (unchanged) | `test_trigger_answer_reveals_a_question_that_is_left_alone` | receiver ledger |

## Your pause and your revocation reach what the standing rule queued (D134, 2026-11-09; local only)

Nothing here ran against a real page or a real account; every recorded permission ended on
2026-11-06. Branch `rule-respects-owner` (from `main` ab671e1; `main` merged in after D133), merged
as #43 (2e10418). The rule's tests run on the second Greenhouse-style fixture through the pilot
(`execution_harness.pilot_on`), with the receiver's ledger as the oracle for what was disclosed and
submitted.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A pause cancels a rehearsal the rule queued before a worker took it: nothing is disclosed, the rule's approval is retired ("Your automatic rule was paused") and the application waits for approval; resumed, the rule rehearses it | `test_pausing_stops_what_the_rule_queued_before_a_worker_takes_it` | receiver ledger: no disclosure, nothing accepted, then the rehearsal; the pause's reply counts one cancelled and one approval |
| A pause that lands just after a worker took the attempt stops it before anything is entered; the application waits for you; resumed, the rule rehearses it | `test_pausing_stops_an_attempt_a_worker_holds_before_anything_is_entered` | receiver ledger: no disclosure, then the rehearsal |
| What you queued yourself, on your own approval, runs through a pause | `test_what_you_queued_yourself_is_never_stopped_by_a_pause` | receiver ledger: disclosed; the pause's reply counts nothing |
| After you revoke, the rule never approves that application again | `test_after_you_revoke_the_rule_never_approves_that_application_again` | approvals (none given again); the rule's event `owner_revoked`; receiver ledger: no disclosure |
| Switched off on the server, a worker refuses an attempt the rule queued before opening anything | `test_switched_off_the_rules_queued_attempt_is_refused_when_a_worker_takes_it` | receiver ledger: no disclosure, nothing accepted; the attempt ends `failed_safe` |
| A pause recorded without stopping anything (as an older version recorded it) is still read when a worker takes the rule's attempt | `test_a_pause_recorded_without_stopping_is_still_read_when_a_worker_takes_it` | receiver ledger: no disclosure |
| A pause waits for the rule's step being approved and queued (two database connections), and a step after the pause approves nothing | `test_a_pause_waits_for_a_job_being_queued_then_the_job_sees_it` | the lock wait (a 300 ms lock timeout); approvals; receiver ledger |
| Another account's pause touches nothing of yours | `test_a_pause_never_touches_another_accounts_work` | its reply counts nothing; your attempt stays pending |
| The two provenance columns are in the account export; the pause's audit row names its keys | `test_every_table_and_column_has_an_export_decision`, `test_audit_inventory.py` | the export decision table; the audit inventory |
| The Tracker's card says what a pause stopped, and nothing when it stopped nothing; resuming clears it | `frontend/e2e/auto-apply-pause.spec.ts` (desktop, mobile) | the browser: the real pause reply, then counts altered in the browser only |
| Each test fails without its change | seven runs, each with one change removed | each fails its tests |

## Reuse and suggestion guards (D133, 2026-11-06; local only)

Nothing here ran against a real page or a real account. The screening job (5020003) on the second
Greenhouse-style fixture is a FIXTURE ASSUMPTION: a real board sends its equal-opportunity
questions in `compliance[]`. Branch `suggestion-guards` (from `main` bd38529; `main` merged in
after D132), merged as #41 (da7ac61). The review fixes (D133, "Adversarial review") are the rows marked
"review".

| Requirement | Test | Oracle / evidence |
|---|---|---|
| "I don't wish to self-identify" and "I do not wish to self-identify" (a typographic apostrophe too) are the form's one decline option; two declines are never chosen between; self-describe is never a decline | `test_disclosure_ledger.py::test_the_one_decline_option_is_the_answer`, `::test_without_exactly_one_decline_option_a_required_question_stays_a_checkpoint` | resolution |
| Self-identification (D122) takes the new decline wording only where the other options name a category: gender declined; Hispanic origin and a felony question stay yours; a race multi-select takes only the decline | `test_self_identification.py::test_i_dont_wish_to_self_identify_declines_only_where_the_options_name_a_category` | resolution |
| With self-identification on, whatever labels it holds, every question-safety row (controls included) resolves as without it, except an equal-opportunity question in a self-identification section; "Don't disclose" always wins | `test_question_safety.py::test_self_identification_answers_only_the_eeo_rows`, rows `c5.selfid.*` | resolution, compared with the run without it |
| The legacy collision corpus is unchanged by self-identification, with each option as a label | `test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome[*-each_option]` | resolution |
| A screening form: with "Male" and "No" saved, only gender is answered; felony and sponsorship wait; approval and queueing are refused and nothing is disclosed; once answered and included, exactly those answers arrive (by id and through the pilot) | `test_greenhouse_dom.py::test_self_identification_never_answers_a_screening_question`, `::test_the_screening_questions_map_to_one_control_each` | receiver ledger: 0 accepted and no disclosure, then 1 accepted with the three values |
| A saved answer is suggested only when the question it was given to is still reused: never a fact, one employer's question, a sensitive topic, an unrebuildable row or a follow-up's answer saved since D131 (one saved before D131 cannot be told apart: deferred); each witness is suggested with the check off | `test_answer_brain_rules.py` (`_suggestible`), `test_answer_brain.py::test_an_answer_saved_for_a_question_never_reused_is_never_suggested`, `::test_a_follow_up_answer_is_never_suggested_for_a_question_on_its_own` | suggestions API |
| Never a suggestion that would be refused on accept (longer than the field allows) | `test_answer_brain.py::test_a_saved_answer_that_would_not_fit_the_field_is_never_suggested` | suggestions API |
| Vetoes over label and help text: negation, units, languages, names, products, number words, countries in help text; fifteen rewordings stay unvetoed; every family is load-bearing; one API case per family | `test_answer_brain_rules.py` (veto table, help only, controls, `::test_every_word_family_is_load_bearing`), `test_answer_brain.py::test_similar_wording_that_differs_on_what_matters_is_never_suggested` | pure; suggestions API |
| The rule score reads the wording only; twelve rewordings at or above 0.6, four unrelated pairs below; a model trained the wrong way round suggests nothing below the floor | `test_answer_brain_rules.py` (score tests), `test_answer_brain.py::test_a_trained_model_never_suggests_below_the_rule_floor` | pure; a trained LightGBM/XGBoost model; suggestions API |
| "Use here only" answers this application and saves nothing; the suggestion returns next time; "Use and save" saves; unknown fields are refused | `test_answer_brain.py::test_use_here_only_answers_this_application_and_saves_nothing`, `::test_a_verdict_with_a_field_the_api_does_not_take_is_refused`, `frontend/e2e/answer-suggestions.spec.ts` (desktop, mobile) | answer bank rows; labels |
| A page failing while it renders keeps the app's navigation and recovers with "Try again"; the error is never shown | `frontend/e2e/error-boundary.spec.ts` (desktop, mobile) | the browser, the reply altered in the browser only |
| Review: an "If not, ..." help text no longer cancels the other label's negation; U.S. / U.K.; hyphenated number words; numbers in order with a.m. / p.m.; bounds, quantities, schedules, workplaces, employment types, levels, restrictions and negating words; non-Latin scripts; other apostrophes; bare "Yes/No" and "no." are not negations | `test_answer_brain_rules.py` (veto table rows after "what the first build missed", `::test_an_answering_instruction_in_the_help_text_cancels_no_negation`, controls, `::test_every_word_family_is_load_bearing`, `::test_every_kind_of_alternative_is_load_bearing`) | pure |
| Review: equal scores prefer the saved answer whose help text matches, whatever the row order; a long label is not kept in the vetoes' cache | `test_answer_brain_rules.py::test_equal_scores_prefer_the_matching_help_text_whatever_the_row_order`, `::test_a_long_label_is_read_afresh_not_cached` | pure |
| Review: a multi-select offering only Yes, No and a decline is never answered with the decline from self-identification, whichever wording; "self identify" without the hyphen is a decline and a sensitive option | `test_self_identification.py::test_a_multi_select_decline_is_taken_only_where_the_other_options_name_a_category`, `test_disclosure_ledger.py::test_the_one_decline_option_is_the_answer`, `test_classify_vocabulary.py` | resolution |
| Each test fails without its change | run once each: the resolver before step 1; the pre-D131 code (c4503cf); the previous suggestion service, vetoes, scoring and router; no `error.jsx` | recorded in `decisions.md` D133 |

## Optional phone left blank beside a control NoEfforts cannot set (D130, 2026-11-05; local only)

Nothing here ran against a real page. The fixture (`gh2_phone_companion`) follows the structure of
one owner-supplied markup fragment and read-only run #11; everything else in it is a FIXTURE
ASSUMPTION. Branch `greenhouse-phone-companion` (on top of D129), not on `main`.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| An optional phone whose named group holds exactly one other, unrequired control: the phone is left blank and the control is not a question (real page and stand-in) | `test_phone_companion.py::test_the_optional_phone_is_left_blank_and_its_second_control_is_not_a_question` | captured schema |
| A required control (attribute, ARIA, its own or the group's marker), a required phone (page or job data), two controls, one outside the group, or any other visible control in the group stays a blocking checkpoint; nothing can be approved (a hidden input in the group is ignored, as everywhere in E3) | `::test_anything_else_stays_a_blocking_unlisted_control_and_the_phone_is_asked`, `::test_when_the_structure_does_not_hold_nothing_can_be_approved`, `::test_every_property_of_the_structure_is_needed` | captured schema; unresolved; approval refused; no disclosure |
| Opacity never makes a control hidden | `::test_opacity_never_makes_a_control_hidden` | snapshot |
| The phone is never taken from the profile and nothing can be typed in its place; package shape unchanged | `::test_the_phone_is_left_blank_whatever_the_profile_holds`, `::test_the_package_leaves_the_phone_blank_and_needs_nothing_more` | resolution; 400 on input; SHAPES[3] |
| Confirmed with no phone sent, the page's default unchanged and the control never touched (by id, pilot, real-board adapter, a different library id) | `::test_the_application_goes_through_with_the_phone_empty_and_the_control_untouched`, `::test_a_library_id_that_differs_from_the_captured_one_is_the_same_structure`, `::test_on_a_real_board_the_rule_applies` | receiver ledger: no `phone`; default value; the page's own `fx_companion_touched` = 0 |
| Required or holding a number on the live page → stopped before any disclosure; filled after the upload → stopped before the send; changed after approval → stopped before any disclosure; a rehearsal stops before sending | `::test_required_or_holding_a_number_on_the_live_page_it_stops_before_anything_is_entered`, `::test_a_number_the_page_puts_in_after_the_upload_stops_it_before_submitting`, `::test_a_page_that_changed_after_approval_stops_before_anything_is_entered`, `::test_a_rehearsal_stops_before_submitting` | receiver ledger: no disclosure / upload only / no acceptance; sabotage (live state ignored) turns the prefilled case into a stop after disclosure |
| An approval recorded before the extraction bump (v3) is retired and must be given again | `::test_an_approval_from_before_the_extraction_bump_is_retired_never_renewed` | approval rows; no disclosure |
| The review shows "Phone omitted: this optional phone/country control is not supported for automatic filling.", never as the owner's choice; the profile is unchanged | `::test_the_phone_is_left_blank_whatever_the_profile_holds`, `::test_the_package_leaves_the_phone_blank_and_needs_nothing_more`, `test_section_free_route.py` | package rows; profile |
| The section-free route with D129 (pilot path): capture, locked identity, phone omitted, approved answers and résumé, readback, rehearsal stop, separately approved single submission; a late control and a cancellation on the same form | `test_section_free_route.py` | receiver ledger: no disclosure at capture; upload of the approved bytes only in the rehearsal, no acceptance; one acceptance (locked email, no phone, picker default, touch counter 0); none after a late control or a cancellation |

## Locale exception, the non-GET stop, hidden search inputs, the handoff (D111, 2026-11-01; local only)

Nothing here ran against a real page. Fixtures are built from run #11's single observation or are
FIXTURE ASSUMPTIONS.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A non-GET request while the page loads stops widget inspection before any action, and never arrives | `test_widget_inspection.py::test_a_beacon_while_the_page_loads_stops_before_any_action`; `test_readonly_cli_process.py::test_dropdown_mode_stops_at_a_beacon_sent_while_the_page_loads` | independent listener: nothing; 0 actions; reason "a non-GET request was attempted" |
| A non-GET request from a dropdown stops the inspection at that action, and no later request is sent | `test_widget_inspection.py::test_a_beacon_from_a_dropdown_stops_the_inspection_at_that_action` | independent listener: nothing; no later action |
| The pilot's locale requests pass only from the main frame | `test_greenhouse_live.py::test_a_locale_file_passes_only_from_the_pages_main_frame` | receiver log |
| A followed redirect of a locale request is recorded (browser-fetch modes) or refused before its target (driver-fetch mode); the runner stops on it before entering and before submitting | `::test_a_redirect_of_a_locale_request_is_never_followed_unseen[browser_fetches/driver_fetches]`, `::test_the_runner_stops_on_a_followed_locale_redirect_before_entering_and_before_submitting` | receiver log; `EgressLog.redirected`; sabotage (no listener) fails the browser-fetch case |
| Locale requests are capped per session at path C's page-request budget | `::test_locale_requests_are_bounded_by_path_cs_request_budget` | receiver log; `blocked` |
| A search input the page hides in one question's group is not a question while hidden, unrequired and empty; shown, required (control or group) or holding a value stops before entering; shown after filling stops before submitting | `test_hidden_search.py` (by id and pilot) | receiver ledger: accepted with nothing sent for it; or no disclosure; or no acceptance; sabotage (visibility condition removed) fails the "shown" cases |
| Required or standalone ones stay blocking checkpoints | `test_hidden_search.py::test_required_or_outside_a_group_nothing_can_be_approved`, `::test_anything_else_stays_a_blocking_unlisted_control`, `::test_the_shape_needs_every_property_and_exactly_one_question_in_the_group` | unresolved; approval refused; no disclosure |
| A list needing another host stops before disclosure; that host hears nothing; no pilot rule admits it | `test_dropdown_strategies.py::test_a_list_that_needs_another_host_stops_before_disclosure_and_the_host_never_hears`, `::test_a_required_unlisted_dropdown_that_needs_another_host_is_a_checkpoint`, `::test_no_pilot_rule_admits_another_greenhouse_host_or_a_data_endpoint` | independent listener: nothing; receiver ledger: no disclosure |
| The milestone-B handoff shows exactly what would be disclosed and each prerequisite as it is; it is ready only with permissions 1-3 and a rehearsal approval; a rehearsal then stops before submitting | `test_rehearsal_handoff.py` | package content; receiver ledger: disclosures, no acceptance; 404 cross-tenant |

## Greenhouse dropdowns: react-select readback, container click, read-only path C (D109, 2026-11-01; local only)

Fixture behaviours are FIXTURE ASSUMPTIONS modelled on react-select and on the owner's previous
bot. None of this has run on a real page.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A choice on react-select markup is read back from its single-value element (the input keeps only search text) | `test_dropdown_strategies.py::test_each_strategy_selects_exactly_the_approved_option[react_select]`, `[container_only]` | receiver acceptance holds the approved options; sabotage (input-value readback): both cases abandoned with "3 field(s) did not keep their values" |
| A list that opens only from its react-select container is opened by `click_container` and verified like any list | `[container_only]` above | the same exact-list checks; `confirmed` |
| Path C's rule: the observed `/locales/*/*.json` shape, segments 1-128 with single dots; `..`, `%`, leading dot, other shapes, queries, other hosts, methods, types, initiators, redirects refused | `test_dropdown_observation_c.py::test_path_c_allows_*`, `::test_path_c_refuses_*`, `::test_a_real_page_takes_path_b_or_path_c_and_nothing_wider` | `locale_refusal` and the context layer agree |
| A hashed locale name refused by path B loads under path C (2xx) and the list opens at the control's click | `::test_a_hashed_locale_name_refused_by_path_b_loads_under_path_c_and_the_list_opens` | receiver log: the page and the one locale file, GETs only |
| An allowed locale request that fails is not counted as loaded | `::test_an_allowed_locale_request_that_fails_is_not_counted_as_loaded` | outcome `4xx` |
| The container fallback: one click, only without an opening, only with a container, only within budget | `::test_a_list_that_opens_only_from_its_container_is_opened_by_the_fallback`, `::test_without_a_container_or_budget_there_is_no_second_click` | `container_attempt`, `opened_by`; no class name in the summary |
| React-select markup recorded as booleans only | `::test_react_select_markup_is_recorded_as_booleans_only` | `markup`; guard passes; no `select__` text |
| The workflow entry point | `test_readonly_cli_process.py::test_dropdown_mode_entry_point_completes_with_path_c_and_states_its_rule` | fresh process, exit 0; 3 API GETs, the page and one hashed locale file |

## A dropdown that sends when opened; widget observations kept apart (D108, 2026-11-01; local only)

Synthetic data and local stand-ins only. Nothing here was run against a real page; run #10's
record is not reclassified.

| Requirement | Test | Oracle / evidence |
|---|---|---|
| A dropdown that POSTs to another origin when opened (fetch or `navigator.sendBeacon`) stops the attempt; the POST never arrives; nothing is filled, uploaded or submitted | `test_dropdown_strategies.py::test_a_dropdown_that_posts_to_another_origin_when_opened_stops_the_attempt` (fetch/sendbeacon, stand-in/real destination) | An independent HTTP listener on the other origin records nothing; the receiver's ledger has no disclosure and no acceptance, and only GETs; `failed_safe` with the dropdown reason |
| The same dropdown without the POST goes through (the stop comes from the POST) | `test_the_beacon_dropdown_is_otherwise_an_ordinary_one` | `confirmed`, 1 acceptance, listener empty |
| Sabotage: a beacon POST is not a fetch/XHR, so before D108 it did not count | the test above with the non-GET rule removed | both `sendbeacon` cases ended `confirmed` (the attempt went on and submitted); the listener still saw nothing |
| An existing answer changing, a control added or removed, focus leaving the control, a class-name hint and a visible option list are separate observations | `test_widget_inspection.py::test_each_thing_an_opening_does_is_observed_on_its_own` (hint_only, other_value, remove_control, anon_change) | `observations` per widget; each stops the inspection with its own reason; no value or identifier in the published summary |
| A hidden control added is never an existing answer changing; an id-less change is unknown, not a change | `test_widget_detector.py::test_control_changes_are_kept_apart`, `::test_an_id_used_twice_is_compared_only_when_it_is_unambiguous` | `compare_controls`; sabotage (an added id counted as a change) fails 2 cases |
| A class-name hint alone is not an opening | `test_widget_detector.py::test_a_class_name_hint_alone_is_not_an_opening` | `undetermined`; with an expanded state it stays `opened_options_not_observable`; sabotage fails 3 cases |
| The adapter refuses each change with its own reason | `test_dropdown_strategies.py::test_the_adapter_names_what_an_opening_changed_and_refuses_each` | `dropdowns._changed` |

## Greenhouse controls on local stand-ins (D104, 2026-10-31; local stand-ins only)

Tests are in `test_greenhouse_controls.py` unless noted; the oracle is the receiver's ledger
(`fixtures/ats_receiver/greenhouse_v2.py`, modes `gh2_phone_country`, `gh2_loc_search`, `gh2_dd`
`late_*`). Every structure is a FIXTURE ASSUMPTION: synthetic coverage is not evidence that a real
page works, and on any destination that is not a local stand-in each control stops the attempt
before anything is entered.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Only these structures, only on stand-ins | `greenhouse_dom.phone_country_field`, `location_picker`, `build_schema(stand_ins=…)` | `test_capture_recognises_the_phone_country_picker_and_the_location_search_on_stand_ins`, `test_anything_but_these_structures_stays_a_checkpoint_at_capture`, `test_a_page_that_is_not_a_stand_in_never_gets_these_rules`, `test_a_widget_is_never_accepted_from_a_hand_made_form` | pass | not seen on a real page |
| Phone country from a unique calling code only | `resolver._phone_country` | `test_phone_country_only_from_a_calling_code_that_names_exactly_one_option`, `test_an_unapproved_phone_number_never_chooses`, `test_a_unique_calling_code_chooses_the_country_and_it_is_read_back` | pass | — |
| +1 or no code: your choice, never residence | as above | `test_a_shared_calling_code_is_a_checkpoint_until_you_choose`, `test_no_calling_code_is_a_checkpoint_never_inferred_from_residence` | pass | — |
| Location text: residence fact or your answer | `resolver._location_search` | `test_location_search_text_is_the_residence_fact_or_your_answer_never_saved_or_guessed` | pass | — |
| Typed after the gate, counted, exact suggestion, page-set coordinates | `GreenhouseDomAdapter._search_location`, `_location_readback` | `test_location_exact_or_checkpoint` (ledger: one `location_search` disclosure, the exact suggestion's coordinates, no write to a hidden value but the page's) | pass | — |
| None, several, label only, nothing set: stop after disclosure, never retried | as above | `test_a_location_that_is_not_exactly_one_suggestion_set_by_the_page_stops_the_attempt` | pass | — |
| Prefill never trusted | `_location_state_dirty` | `test_a_location_the_page_filled_itself_is_never_trusted` | pass | — |
| Structures re-proven before disclosure | `schema_matches` | `test_a_changed_structure_after_approval_stops_before_anything_is_entered` | pass | — |
| Late options: bounded, settled, exact; refused otherwise | `dropdowns._observe(late=True)`, `_data_refusal` | `test_dropdown_strategies.py` (`late_*`, `delayed`, `locale_on_open`), `test_late_options_through_both_adapters` | pass | — |
| Real destinations refused | `STAND_IN_ONLY`; `late` only on stand-ins | `test_on_a_destination_that_is_not_a_stand_in_they_stop_before_anything_is_entered`, `test_capabilities_stay_fixture_only_and_real_destinations_refused` | pass | — |
| No SCHEMA_VERSION change for other packages | `package.build_content` | `test_only_forms_with_these_controls_carry_a_widget_so_schema_version_stays` | pass | — |
| Sabotage | one guard at a time, 26 changes | all caught; 25 on the first run, the three-read rule alone only after `late_slow_changing` was added (`implementation-status.md`, D104) | pass | — |

## A daily check of a job board you choose (D96, 2026-10-31; local stand-ins only)

Tests are in `test_board_daily_check.py`; the oracle for requests is the stand-in's ledger.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Your choice per board; off until chosen | `daily_check`; `board_sync.due` | `test_nothing_is_read_on_its_own_until_you_choose_it_for_a_board` | pass | — |
| Once a day, through the D95 boundary | `check_due` calls `sync` | `test_a_daily_board_is_read_once_a_day_through_the_same_boundary` (ledger: GET only, no cookie, credential or body) | pass | — |
| Never while off, paused, backing off or turned off | `due` filters and `sync` refusals (two layers) | `test_not_when_boards_are_off_paused_backing_off_or_turned_off`, `test_a_failed_daily_read_changes_nothing_and_backs_off` | pass | — |
| New postings noticed, never a job or an email | `notifications/service._boards`; `baseline_at` | `test_new_postings_after_the_first_read_are_one_notice_a_day_never_a_job`, `board-sources.spec.ts` | pass | — |
| Limit per account; account isolation | `daily_check_limit`; scoped queries | `test_the_daily_limit_and_another_account`, `test_every_query_of_the_feed_is_scoped_to_the_account` | pass | — |
| A board being read is skipped | the row lock (`NOWAIT`) | `test_a_board_its_owner_is_reading_is_skipped` | pass | — |
| Export and audit | export columns; `daily_check_on/off`, `daily_check` | `test_your_choice_is_exported`, the once-a-day test (audit) | pass | — |
| Sabotage | 11 single changes, 3 double | 8 caught alone, 3 caught with both layers removed (`implementation-status.md`) | pass | — |

## Employer job boards (D95, 2026-10-30; local stand-ins only, no real board read)

The oracle is the stand-in's own request ledger (`board_requests` in the receiver's SQLite,
`fixtures/ats_receiver/board_feeds.py`): method, path, query, whether a cookie, an
`Authorization` header or a body came. Boards and postings are fictional. Tests are in
`test_board_sources.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Off by default; explicit per-board activation | `board_sources_enabled`; `POST /discovery/sources`; "Read now" | `test_off_by_default_nothing_is_read`, `board-sources.spec.ts` | pass | — |
| A board is an identifier, never a URL | `boards.check_identifier`, encoded path | `test_a_board_is_an_identifier_never_a_url` (URL, `../`, space, unknown provider, unknown region: 400, no request) | pass | — |
| Fixed hosts, HTTPS, public addresses at connect, no redirects | `urlsafety.public_https_opener`, `_NoRedirect` | `test_the_public_opener_refuses_other_hosts_plain_http_and_private_addresses`, `test_outside_tests_the_fixed_public_host_is_used_never_an_override`, the `redirect` case of `test_a_failed_read_changes_nothing_and_backs_off` | pass | the real hosts were never contacted |
| GET only; nothing of the user sent | fixed headers, no cookie jar | `test_a_greenhouse_board_is_read_once_with_nothing_of_yours` (ledger: one GET, no cookie, no credential, no body), `board-sources.spec.ts` (same, through the UI) | pass | — |
| Documented paging and completeness | Greenhouse `meta.total`; Lever short page | `test_a_lever_board_is_paged_until_a_short_page`, `test_only_a_complete_read_says_a_posting_is_no_longer_listed`, `test_an_incomplete_read_never_marks_anything_closed` | pass | completeness rules are inferred from the docs (`docs/research/job-board-apis.md`) |
| Failures, limits, rate limiting, backoff | `BoardError` codes, `backoff`, size cap, `next_allowed_at` | `test_a_failed_read_changes_nothing_and_backs_off` (404, 503, 429 with Retry-After, redirect, oversize, not JSON, Lever page 2 failing), `test_backoff_is_bounded`, `test_two_reads_of_one_board_at_once_are_refused` | pass | no rate limit is documented for either read API |
| Normalization, malformed and missing values | `boards.normalize` | `test_malformed_records_are_skipped`, the two read tests | pass | — |
| Malicious descriptions and links | `plain_summary`, `_safe_url`, links never fetched | `test_untrusted_content_and_links_are_neutralised` (script, `onerror`, `javascript:`, `data:`, metadata and loopback links) | pass | — |
| Duplicates: repeated reads, saves, other sources | one row per board and posting id; `service._existing_job` | `test_repeated_reads_never_duplicate`, `test_a_posting_is_saved_once_and_reconciled_with_your_existing_jobs` | pass | — |
| Pause, resume, rename, remove | `PATCH`, `DELETE` | `test_pause_resume_rename_and_remove`, `board-sources.spec.ts` | pass | — |
| Account isolation | `user_id` on every query; 404 | `test_another_account_never_reaches_your_boards` | pass | — |
| Discovery never touches applications | reads and saves only jobs and discovered rows | `test_discovery_never_creates_an_application_route_or_approval` | pass | — |
| Export, deletion, audit, logs | `board_sources` exported; cascades; audit codes only | `test_export_deletion_audit_and_logs_keep_board_data_where_it_belongs`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Owner settings reach the containers (D94 fix) | `docker-compose.yml` pass-throughs | `test_every_owner_setting_in_the_example_reaches_the_api_and_the_worker` (`test_deployment_config.py`); `docker compose config` with a synthetic `.env` | pass | not run on the owner's machine |
| Sabotage | 12 guards | each caught (`implementation-status.md`) | pass | — |

## Email reminders to the owner (D94, 2026-10-30; local SMTP sink only)

The oracle is the sink's own ledger (`fixtures/ats_receiver/mail_sink.py`), which shares no code
or database with NoEfforts. Tests are in `test_email_reminders.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Off by default; opt-in needs a verified address | `config_problem`, `set_enabled`, `verify_code` | `test_off_by_default_nothing_is_ever_sent`, `test_turning_it_on_needs_a_verified_address_entered_in_the_app`, `test_codes_expire_run_out_and_are_limited_and_addresses_are_checked`, `email.spec.ts` | pass | — |
| Minimal content, safe link, owner only | `digest_message`; recipient from settings only | `test_the_digest_says_only_the_category_and_links_to_the_tracker`, `test_nothing_is_ever_emailed_to_anyone_but_the_verified_owner`, `email.spec.ts` | pass | — |
| Categories, daily digest, deduplication | `digest_items`, dedupe key, emailed keys | `test_attention_items_are_their_own_category_and_choices_are_respected`, `test_one_digest_a_day_and_no_item_is_put_in_a_second_digest`, `test_an_item_read_in_the_app_is_not_emailed`, `test_before_the_hour_nothing_is_sent` | pass | — |
| Opt-out, new address, deletion before dispatch | `cancel_pending`; re-check at claim | `test_opting_out_or_removing_the_address_before_dispatch_cancels`, `test_a_new_address_needs_verifying_again_and_cancels_what_is_pending`, `test_deleting_the_account_before_dispatch_sends_nothing` | pass | an accepted message cannot be recalled |
| Duplicate workers, fencing, recovery | lock + skip-locked claim, `generation`, `recover_stale` | `test_two_workers_for_one_delivery_send_it_once`, `test_a_late_result_after_recovery_is_fenced`, `test_a_worker_lost_while_sending_leaves_it_uncertain` | pass | — |
| Refusal, timeout, uncertain acceptance | `SmtpTransport` classification; bounded retries | `test_a_definite_transient_refusal_is_retried_a_bounded_number_of_times`, `test_a_refusal_then_acceptance_is_sent_once`, `test_a_permanent_refusal_fails_and_is_not_retried`, `test_a_refused_connection_is_a_definite_failure`, `test_a_possible_acceptance_is_uncertain_and_never_resent` | pass | not exactly-once: NoEfforts never resends an uncertain message, but neither it nor SMTP can rule out a duplicate further down the delivery chain |
| No application change; no follow-up marked done | reminders read only | `test_reminders_never_change_an_application_or_mark_a_follow_up_done`, `email.spec.ts` | pass | — |
| Isolation, tokens, privacy of logs, audit, export | `session_only`; sanitized logs; export lists | `test_another_account_and_api_tokens_never_reach_your_email_settings`, `test_logs_and_audit_keep_no_address_code_or_message_and_the_export_keeps_your_settings`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Configuration checked before sending | `config_problem` | `test_the_configuration_is_checked_before_anything_is_sent` | pass | — |
| Honest validation exit codes | `scripts/validate.sh` | `scripts/test_validate.sh` (CI docker-smoke job) | pass | — |
| Sabotage | 13 guards | each caught (`implementation-status.md`) | pass | — |

## Freehire signals, display-only (D93, 2026-10-30; fixture only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Only the documented fields, each with its type | `provider.freehire_signals` | `test_reality_is_read_field_by_field_with_its_documented_type_and_nothing_else` | pass | the fixture's shapes stand in for Freehire's reference |
| Worded in the source's terms, attributed | `provider.describe_signals`; Discover; job page | `test_signals_are_described_in_the_sources_terms_without_a_verdict`, `test_the_listing_and_the_job_page_show_what_freehire_says`, `discovery.spec.ts` | pass | — |
| Refreshed without counting as a change | stored in `normalized`, outside the fingerprint | `test_signals_refresh_on_every_read_without_counting_as_a_change`, `test_counters_and_reality_ticking_are_not_a_change` | pass | — |
| Never an input | code scan of every reader | `test_signals_never_reach_matching_approval_routing_or_execution` | pass | — |
| Sabotage | 4 guards | each caught (`implementation-status.md`) | pass | — |

## Follow-ups (D92, 2026-10-30; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Only after a submission; due after the set days, a chosen day, or from an interview's day | `followups/service.py` `evaluate` | `test_nothing_to_follow_up_before_the_application_is_submitted`, `test_due_seven_days_after_you_applied_and_notified_then`, `test_the_days_are_the_owner_setting`, `test_remind_me_on_a_day_you_choose_within_a_year`, `test_an_interview_you_recorded_starts_the_wait_from_its_day` | pass | — |
| Your actions: done, a day, stop, resume; closed by an outcome | `POST /applications/{id}/follow-up` | `test_saying_you_followed_up_starts_the_next_wait_and_a_new_notification`, `test_stopping_the_reminders_and_resuming_them`, `test_an_outcome_that_closes_the_application_ends_the_reminders`, `test_every_closing_outcome_closes_it`, `follow-ups.spec.ts` | pass | — |
| Due is notified in the app; nothing is sent | `notifications/service.py` `_follow_ups` | the same tests; `follow-ups.spec.ts` | pass | no outside delivery (row 8) |
| The message uses the job, the day and your approved name only | `followups/service.py` `draft` | `test_the_message_uses_the_job_your_approved_name_and_nothing_else_of_yours`, `test_without_a_name_the_message_says_where_yours_goes` | pass | — |
| Account isolation, CSRF, token scope | `_owned`, scoped queries, the `read` allow-list | `test_another_account_never_sees_or_changes_your_follow_up`, `test_a_change_needs_the_csrf_token`, `test_a_read_token_lists_follow_ups_but_never_reads_the_message_or_changes_one`, `follow-ups.spec.ts` | pass | — |
| Audit, export, deletion | `follow_up.update`; `follow_ups` exported; cascades | `test_your_choices_are_audited_by_action_only_and_exported_with_the_account`, `test_deleting_the_application_or_the_account_deletes_your_choices`, `test_every_table_and_column_has_an_export_decision` | pass | — |
| Sabotage | 9 guards | 7 caught alone; 2 double layers caught together (`implementation-status.md`) | pass | — |

## Capture-only browser extension (D90, 2026-10-30; local only, Chromium)

The extension (`extension/`) is loaded unpacked into Playwright's Chromium in
`frontend/e2e/extension.spec.ts` (desktop project), against the real web app and API. Postings
are the local receiver's fictional pages; accounts are synthetic.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Least permissions: no page access, NoEfforts on this machine only | `manifest.json`: `activeTab`, `storage`, loopback host permissions, no content scripts | "the extension asks for the least" (manifest and code checked statically) | pass | — |
| Sends the address (no fragment) and title only, with the token, never the browser's cookies | `lib.js` `checkTab`, `saveJob` (`credentials: "omit"`, `redirect: "error"`) | "what is sent" (the request as made, through a stand-in `fetch`) | pass | — |
| Only plain http to 127.0.0.1 or localhost | `checkBase` | "what is sent" (nine addresses) and the options test | pass | — |
| Keeps only an `import:jobs`-only token NoEfforts accepts; never shows it; drops it when the address changes | `checkToken` (`GET /api/token`), `options.js` | "options keep only a token..." (a `read`+`import:jobs` token, an unknown token, a good token, an address change) | pass | — |
| Saves the tab's job once to the token owner's account, not the signed-in browser session's | `background.js` → `POST /api/jobs` | "a fictional posting's tab is saved..." (owner's list has it once with its title; the bystander signed in in that browser does not) | pass | — |
| Cannot read a tab you did not click its button on; refuses a non-web page | `activeTab` only; `checkTab` | "a tab you did not click the button on is never read..." | pass | the `activeTab` grant by a real toolbar click is not automatable in Playwright |
| Sabotage | 7 guards broken one at a time | each caught (`implementation-status.md`) | pass | — |

## Installable web app with an offline page (D89, 2026-10-30; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Installable: manifest, icons, a service worker | `public/manifest.webmanifest`, `layout.tsx`, `public/sw.js` | `pwa.spec.ts` "the app can be installed" (desktop and mobile) | pass | install prompt itself not automated |
| Offline, a page load shows the offline page | `sw.js`: network first for page loads, `offline.html` only when that fails | `pwa.spec.ts` "offline, a page shows the offline page" | pass | — |
| Nothing about you is kept on the device | the worker caches `offline.html` and one icon, nothing else | the same test: after browsing four pages signed in, the caches hold exactly those two files | pass | — |
| The image serves it | `frontend/Dockerfile` copies `public/` | `scripts/docker-smoke.sh` (manifest, offline page) in CI `docker-smoke` | CI | not run in the sandbox (no Docker daemon) |
| Sabotage | 2 guards broken (cache pages; no offline fallback) | each caught (`implementation-status.md`) | pass | — |

## Workday-style adapter against the local receiver (D88, 2026-10-30; local only, checkpoint-first)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Workday-style approximation only, never with a real Workday tenant. Tests are in
`test_workday_adapter.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Account, password and verification steps are checkpoints | password inputs unsupported; `blocked_reason`; verification after the click is unknown | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints`, `test_an_account_gate_or_several_pages_after_approval_stop_before_disclosure`, `test_email_verification_after_the_final_click_is_a_hard_stop`, `workday.spec.ts` | pass | — |
| Several pages are a checkpoint | `multi_step` field at capture; `blocked_reason` | the same tests, `workday.spec.ts` | pass | page-by-page disclosure not built |
| A challenge on the page is a checkpoint, never solved (added after CI #127) | `bot_check` field at capture; `blocked_reason`; registry claims `captcha_checkpoint` | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints[wd_challenge-bot_check]`, `test_a_challenge_that_appears_after_approval_stops_before_disclosure`, `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one` | pass | Workday documents no challenge; the mode is fixture design |
| Résumé-parsing prefill is never trusted | `prefilled_values` at capture; readback of unanswered fields | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints`, `test_resume_parsing_is_never_trusted_without_readback` | pass | — |
| Complex location fields and custom dropdowns are checkpoints | dependent lists read as unsupported pickers; ARIA widgets unsupported | `test_accounts_several_pages_prefill_and_complex_fields_are_checkpoints` | pass | — |
| Approved values, byte-identical documents | `fixture_workday` fill and upload (hosted-form base) | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `workday.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits; submission needs its own approval | the existing rehearsal stop and scopes | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `workday.spec.ts` | pass | — |
| No duplicate send; an uncertain send is quarantined | claim fencing; unknown outcome | `test_a_duplicate_delivery_never_submits_twice`, `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_workday-*]` | pass | — |
| Upload evidence kept after a partial failure | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Changed inputs cancel the approval; drift stops | package versioning; fingerprint | `test_a_changed_approved_input_invalidates_the_approval`, `test_form_changed_after_approval_stops_before_disclosure` | pass | — |
| Off-site pages and redirects stop; the confirmation is bound | runner same-origin check; egress; `_bound` | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered`, `test_confirmation_bound_to_attempt` | pass | — |
| Real Workday stays a manual handoff | no Workday identity; planned `workday` | `test_a_real_workday_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `workday.spec.ts` | pass | — |
| Sabotage | 8 guards broken one at a time, then 2 for the challenge stop | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Ashby-style adapter against the local receiver (D87, 2026-10-30; local only)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Ashby-style approximation only, never with a real Ashby posting. Tests are in
`test_ashby_adapter.py` unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Approved values, byte-identical documents | `fixture_ashby` fill and upload (hosted-form base) | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `ashby.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits | the existing rehearsal stop | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `ashby.spec.ts` | pass | — |
| Submission needs its own approval | approval scopes (unchanged) | the same tests (the rehearsal's approval is used up) | pass | — |
| A duplicate delivery never submits twice | claim fencing (unchanged) | `test_a_duplicate_delivery_never_submits_twice` (receiver non-idempotent) | pass | — |
| Upload evidence kept after a partial failure | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Unknown required controls block | capture as unsupported; drift check | `test_an_unsupported_required_control_or_the_spam_check_blocks_approval`, `test_form_changed_after_approval_stops_before_disclosure`, `test_unknown_sponsorship_blocks_approval` | pass | — |
| The spam check is a hard stop | bot-check field at capture; `blocked_reason`; unknown after the click | `test_an_unsupported_required_control_or_the_spam_check_blocks_approval`, `test_a_spam_check_that_appears_after_approval_stops_before_disclosure`, `test_the_spam_check_or_a_repeat_after_the_final_click_is_a_hard_stop`, `test_a_confirmation_page_that_also_shows_a_bot_check_is_not_a_confirmation` | pass | — |
| A page value nobody approved is never sent | readback of unanswered fields | `test_a_resume_autofill_that_changes_a_field_stops_before_submit` | pass | — |
| The cookie banner is never clicked | nothing outside the form is clicked | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `ashby.spec.ts` (no `cookie_choice` in the ledger) | pass | — |
| Changed approved inputs cancel the approval | package versioning (unchanged) | `test_a_changed_approved_input_invalidates_the_approval` | pass | — |
| An uncertain final send is quarantined, never retried | unknown outcome (unchanged) | `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_ashby-*]` | pass | — |
| Off-site pages and redirects stop | runner same-origin check; egress | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered` | pass | — |
| Real Ashby stays a manual handoff; fixture evidence enables nothing | no Ashby identity, no specification | `test_a_real_ashby_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `ashby.spec.ts` | pass | — |
| Sabotage | 10 guards broken one at a time | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Fixture-origin boundary (D86, 2026-10-30; local only)

Every public address below comes from a fake resolver; each check refuses before a connection
is opened, so nothing public was contacted. Tests are in `test_fixture_origin_boundary.py`
unless named otherwise.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Single-label names only if listed exactly | `urlsafety.FIXTURE_SERVICE_HOSTS` (`receiver`) | `test_only_names_listed_exactly_are_fixture_hosts`, `test_an_unlisted_single_label_name_is_refused`, `test_lever_adapter.py::test_only_the_listed_compose_receiver_name_is_a_fixture_host` | pass | — |
| A listed name resolving publicly is refused | `connect_fixture` (every resolved address); egress proxy `check_destination` | `test_a_listed_name_resolving_to_a_public_address_is_refused_before_connecting`, `test_a_listed_name_is_read_only_while_it_resolves_locally`, `test_execution_through_a_listed_name_follows_where_it_resolves`, `test_the_proxy_refuses_a_fixture_name_resolving_outside_the_test_network` | pass | — |
| The address actually connected to is checked | `connect_fixture` peer check; proxy peer check before relaying | `test_the_address_actually_connected_to_is_checked_again`, `test_the_proxy_checks_the_peer_it_actually_reached` | pass | — |
| Test networks are narrow and private | `parse_fixture_networks`; Settings validator; proxy service startup | `test_a_test_network_must_be_a_narrow_private_network`, `test_test_networks_must_be_given_as_a_list`, `test_the_proxy_service_takes_its_own_test_network_and_refuses_a_wide_one` | pass | — |
| Redirects refused, every hop checked | fixture opener follows none and checks each request's origin; browser hops through the proxy | `test_the_opener_never_follows_a_redirect`, `test_every_request_the_opener_makes_is_checked_by_origin`, `test_a_capture_redirect_off_the_fixture_is_never_followed`, `test_lever_adapter.py::test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered` | pass | — |
| Outside the test environment, refused | `is_fixture_origin` needs `env == "test"` | `test_fixture_origins_are_refused_outside_the_test_environment` (development, staging, production) | pass | — |
| Other spellings of an address; IPv6 loopback and mapped forms | standard-form literals only; `_legacy_ipv4` in `check_url_syntax` | `test_other_spellings_of_a_loopback_address_never_count`, `test_other_spellings_of_a_public_address_are_public_not_fixtures`, `test_ipv6_loopback_and_mapped_forms`, `test_fixture_addresses_are_loopback_or_on_the_test_network` | pass | — |
| A fixture is never browsed without the egress proxy | `browser_session` refuses `isolation=off` (`fixture_needs_proxy`) | `test_a_fixture_is_never_browsed_without_the_egress_proxy` | pass | — |
| In `netns` mode every connection leaves through the proxy | driver never fetches or connects (was: GET/HEAD and WebSockets from the driver) | probe (no proxy decision for the destination with interception on, before the fix); `test_in_netns_mode_the_page_load_itself_passes_the_egress_proxy`, `test_execution_through_a_listed_name_follows_where_it_resolves` (refused at the proxy) | pass | — |
| Compose execution still works | `fixtures` pinned to `10.231.47.0/24`, `NOEFFORTS_ENV=test` on the API and worker, test network on API, worker and proxy | CI `execution-compose` on the commit (no Docker daemon in this sandbox) | see `implementation-status.md` | not run locally |
| Sabotage | 14 guards broken one at a time | each caught, restored by MD5 (`implementation-status.md`) | pass | — |

## Lever-style adapter against the local receiver (D85, 2026-10-30; local only)

The oracle is the receiver's own ledger. Passing shows compatibility with the labelled
Lever-style approximation only, never with a real Lever posting.

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Approved values, byte-identical documents | `fixture_lever` fill and upload | `test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents`, `lever.spec.ts` | pass | — |
| A rehearsal discloses under its approval, never submits | the existing rehearsal stop | `test_a_rehearsal_discloses_under_its_approval_and_never_submits`, `lever.spec.ts` | pass | — |
| Submission needs its own approval | approval scopes (unchanged) | the same tests (the rehearsal's approval is used up) | pass | — |
| A duplicate delivery never submits twice | claim fencing (unchanged) | `test_a_duplicate_delivery_never_submits_twice` (receiver non-idempotent) | pass | — |
| A partial upload failure keeps earlier disclosures' evidence | `UploadFailed` disclosures | `test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure` | pass | — |
| Unknown required controls block approval or execution | capture as unsupported; drift check | `test_a_required_picker_or_a_bot_check_on_the_form_blocks_approval`, `test_form_changed_after_approval_stops_before_disclosure`, `test_unknown_authorization_blocks_approval` | pass | — |
| A page value nobody approved is never sent | readback of unanswered fields | `test_a_parsed_resume_that_changes_a_field_stops_before_submit` | pass | — |
| Changed approved inputs invalidate authorization | package versioning (unchanged) | `test_a_changed_approved_input_invalidates_the_approval` | pass | — |
| An uncertain final send is quarantined, never retried | unknown outcome (unchanged) | `test_an_uncertain_final_send_is_quarantined_and_never_retried`, `test_outcomes_after_the_final_click`, `test_reconciling_an_unknown_outcome_never_sends_again[fixture_lever-*]` | pass | — |
| Real Lever stays a manual handoff; fixture evidence enables nothing | no Lever identity; planned `lever` | `test_a_real_lever_posting_is_never_read_and_is_a_manual_handoff`, `test_fixture_evidence_never_enables_a_real_destination`, `lever.spec.ts` | pass | — |
| The app never calls it live support | labels from `providers/wording.py` | `test_the_app_never_calls_this_live_support` | pass | — |
| No hostname, redirect or configuration escape | runner same-origin check; egress; local fixture hosts | `test_a_form_page_off_the_destination_site_is_never_opened`, `test_a_redirect_off_the_local_site_is_blocked_before_anything_is_entered`, `test_listing_a_public_site_as_a_fixture_never_makes_it_one` | pass | — |
| Sabotage | 7 guards broken one at a time | each caught, restored by MD5 | pass | — |

## API tokens, CLI and MCP (D84, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Displayed once, never stored in plaintext | `apitokens.service.create` keeps the SHA-256 only | `test_a_token_is_shown_once_and_only_its_hash_is_kept`, `api-tokens.spec.ts` (gone after "I have copied it" and a reload) | pass | — |
| Expires by default | 30 days default, 1-90 enforced | `test_a_token_always_expires_and_has_known_scopes`, `test_expired_revoked_and_unknown_tokens_read_the_same` | pass | — |
| Revocable, effective at once | `revoked_at`; checked on every request | the same test, `api-tokens.spec.ts` (401 after revoke) | pass | — |
| Scope enforcement, default deny | allow-list per scope in `current_user` | `test_every_route_outside_a_scope_refuses_the_token_before_doing_anything` (every route, both scopes, nothing audited), `test_no_scope_reaches_review_consent_approval_submission_or_your_facts`, `test_an_import_token_adds_a_job_and_nothing_else` | pass | — |
| Session-only for management, export, deletion | `session_only` | `test_session_only_routes_refuse_a_token_even_next_to_a_valid_session` | pass | — |
| Tenant isolation | a token resolves to one user | `test_a_token_reads_its_own_account_only` | pass | — |
| Log redaction | access log by template; no header logged | `test_no_log_line_carries_a_token`, `test_against_a_real_server_the_cli_and_mcp_work_and_no_output_shows_the_token` (uvicorn, CLI and MCP subprocesses) | pass | — |
| Your facts stay in the app | job read by token without eligibility | `test_a_token_reads_a_job_without_the_eligibility_that_shows_your_facts` | pass | Match summaries still name your approved skills and licences the job mentions (documented) |
| No surface bypasses review, consent or approval | no such CLI command or MCP tool; API refuses tokens there | `test_the_mcp_server_offers_read_tools_and_never_a_way_to_apply`, the route sweep | pass | Not tried with a third-party MCP client |
| Sabotage | 8 guards broken one at a time (scope check, expiry, hash comparison, plaintext stored, rate limit, session-only, cookie fallback, eligibility hiding) | each caught, restored by MD5; the hash comparison was missed at first (the tampered token was a revoked one), and a tampered active token was added | pass | — |

## In-app notifications (D83, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Truthful: a notification says what its record says now | `notifications/service.py` derives each one from checkpoints, approvals, rehearsal records and attempts every time | `test_a_failure_says_what_happened_and_never_promises_a_retry` (real unknown and rejected outcomes), `test_a_verification_code_request_needs_you_until_it_ends` (simulated rows) | pass | Expired approvals (not invalidated) are not notified |
| Deduplicated: one per record | keyed by the record; a used-up approval and a rehearsed attempt are not notified apart from their rehearsal | `test_a_rehearsal_is_one_notification_not_three`, `test_a_receipt_is_notified_once_with_its_evidence_class_and_a_link` | pass | — |
| Nothing you did yourself is news | approvals you revoked and attempts you cancelled are left out | `test_an_approval_that_stops_applying_is_notified_but_not_one_you_revoked`, `test_nothing_is_notified_for_what_you_cancelled` | pass | A package you changed yourself still notifies the approval it ended (on purpose: it no longer applies) |
| Tenant-scoped read state | `notification_reads`; another account's key is 404 and nothing is marked | `test_read_marks_are_yours_and_another_account_cannot_see_or_touch_them`, `test_every_query_of_the_feed_is_scoped_to_the_account` | pass | — |
| No delivery outside the app | no mail, network or task library in the module; used by its own routes only | `test_nothing_in_notifications_can_send_anything_anywhere` | pass | — |
| Exported and deleted with the account | export inventory; FK cascade | `test_read_marks_are_exported_and_deleted_with_the_account`, `test_d83_adds_notification_reads_and_downgrade_drops_only_them` | pass | — |
| In the browser: receipt and invalidated approval, read/unread, links, per account | `notifications/page.tsx`, header count | `notifications.spec.ts` (desktop, mobile) against the real worker and receiver | pass | — |

## Jobs-list match summary (D82, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| The list and the job page cannot disagree | `fit.summary(fit.assess(...))` | `test_the_jobs_list_summarises_the_same_assessment_and_hides_nothing` | pass | — |
| No score, verdict or probability; eligibility not summarised | summary keys fixed | `test_the_summary_says_nothing_about_eligibility`, `test_no_text_calls_it_a_prediction_a_score_or_a_verdict`, `match-summary.spec.ts` word checks | pass | — |
| A job without text is "not compared", not "names none" | `compared` flag | `test_a_job_without_text_is_not_compared_rather_than_naming_nothing` | pass | — |

## Workday and Ashby shapes, embeds, credentials, custom widgets (D81, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| An account gate is never passed for the user; no password is asked for or kept | password and one-time-code inputs unsupported | `test_workday_account_gate_and_traps_are_never_filled`, `test_a_credential_input_is_never_a_text_field` | pass | — |
| An unknown required question is never dropped | ARIA widgets without native input → unsupported | `test_a_required_custom_widget_blocks_instead_of_disappearing` (4 widgets), the two fixture tests, `test_a_visible_listbox_owned_by_a_combobox_is_part_of_that_control` | pass | Widgets with no ARIA role at all stay invisible to the extractor (a page script, a canvas) |
| Ashby embeds are recognised, fail-closed | `detect_ats` | positive (3), malformed (4), ambiguity and host-precedence tests, the gap probe | pass | The any-host trust is a recorded gap |
| Sensitive and legal questions on these shapes are never answered for the user | resolver (unchanged) | the two fixture tests | pass | — |
| The owner's verification returns only safe output | `verify-local.sh` summary | `test_verify_local_reports_each_step_and_never_a_value`, `test_verify_local_ends_with_a_safe_summary_when_docker_is_missing` | pass | The Mac run itself is pending |

## Lever-shaped form, checkpoint-first (D80, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| A search-as-you-type picker is never filled as text | `forms.extract_form_schema` (combobox, aria-autocomplete → unsupported) | `test_every_documented_trap_is_a_checkpoint_or_a_blank`, `test_words_alone_are_not_a_bot_check_and_a_plain_input_is_not_a_combobox` | pass | — |
| A CAPTCHA is never solved; the user applies themselves | bot-check field on the generic capture path | `test_the_bot_check_blocks_approval_even_when_everything_else_is_answered`, `test_a_bot_check_is_found_by_its_documented_markup` (6 markups) | pass | The Greenhouse paths rely on their adapters' stop (unchanged) |
| Lever traps from the research are checkpoints | `fixtures/lever.html` | `test_lever_fixture.py` | pass | Shapes search-reported, not observed |
| Unknown authorization stays unknown | resolver (unchanged) | `test_unknown_authorization_stays_unknown` | pass | — |

## Export, deletion, saved-answer editing, preview, explainable match (D77-D79, 2026-10-29; local only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Export is complete and scoped to the account | `account/export.py` (explicit column lists) | `test_the_export_holds_everything_of_the_account_and_nothing_of_another`, `test_every_table_and_column_has_an_export_decision`, `account.spec.ts` | pass | — |
| Export holds no secret or keyed material | column and JSON-key exclusions, keyed-reference scrubber | `test_the_export_holds_no_secret_and_no_keyed_material`, `test_the_scrubber_leaves_out_keyed_values_inside_json` | pass | — |
| Deletion removes every row, file and session of the account only | cascade from `users` (checked in the migrated database), files after commit | `test_every_table_that_names_an_account_is_deleted_with_it`, `test_deletion_removes_every_row_file_and_session_of_the_account_only`, `account.spec.ts` | pass | Not run against a real account (by instruction) |
| Deletion never causes a resubmission | refused past the send gate; pending work deleted; a holding worker fenced out | `test_deletion_is_refused_while_a_submission_may_be_in_flight`, `test_queued_work_stops_a_pending_attempt_and_its_message_do_nothing`, `test_a_worker_holding_an_attempt_is_fenced_out_and_never_sends`, the two gate races | pass | — |
| Retention is a decision, not invented policy | `account/policy.py` | `test_the_deletion_document_lists_exactly_the_reason_codes_and_policy` | default: nothing kept | Owner decision open |
| A saved-answer edit keeps provenance and history and invalidates approvals | `preparation/bank_edit.py` | `test_an_edit_is_a_new_version_and_the_application_asks_for_approval_again`, `test_the_history_keeps_every_version`, `test_every_protected_mutation_stops_a_running_attempt[answer_bank_edit]`, `answers-edit.spec.ts` | pass | — |
| Preview introduces no external service or active content | text as JSON, shown in a `<pre>` | `test_the_preview_is_the_text_as_data_never_the_file`, `answers-edit.spec.ts` (markup shown, not run; no request off the machine) | pass | — |
| Match explained by component, unknown stays unknown, never a probability | `jobs/fit.py` | `test_fit.py` (each result, side-by-side eligibility, qualifications from approved facts, the wording scan, the job page API) | pass | No jobs-list summary yet |

## Owner deployment readiness (D76, 2026-10-29; sandbox CLI and CI only)

| Requirement | Implementation | Evidence | Result | Gaps |
|---|---|---|---|---|
| Compose refuses to start without its secrets | `${VAR:?}` for `AUDIT_REF_KEY`, `BROWSER_RUNNER_TOKEN`, `EGRESS_CONTROL_TOKEN` | `docker compose config` exit 1 without `AUDIT_REF_KEY` (sandbox); `test_every_required_compose_variable_is_in_the_example_and_the_checker` | pass | — |
| Secrets checked before start, never printed | `scripts/check_env.py` | `test_the_example_file_is_refused_until_its_secrets_are_set`, `test_a_good_file_passes_and_no_value_is_printed`, `test_a_bad_file_fails_without_printing_its_values`, `test_reused_secrets_missing_keys_and_outbound_switches` | pass | Not run on a Mac's system `python3` |
| Nothing reachable from another machine | every published port on 127.0.0.1 | `test_every_published_port_is_bound_to_this_machine_only`; rendered `docker compose config` | pass | — |
| Worker and web app never start before migrations finish | API health check; `depends_on: service_healthy`; `alembic upgrade head && uvicorn` | `test_the_worker_and_web_app_start_only_once_the_api_is_healthy`; probe exit 1 with no API, 0 with one, even with a dead proxy configured | pass in the sandbox | CI `docker-smoke` exercises it in real containers |
| Backup and rollback restore the data from before the backup, and nothing after | `docs/deployment.md` sections 5 and 7 | CI `docker-smoke`: back up, second account, drop and restore, first session works, second login 401 | see implementation-status for the CI run | Not run on the owner's machine |
| Backups never committed | `.gitignore` `backups/`; hygiene rule for `backups/` and `.dump` | `test_backups_are_never_committed`, `test_the_rules_catch_what_they_are_for` | pass | — |
| Runs on the owner's Mac | `docs/deployment.md` section 10, `scripts/verify-local.sh` | — | **not run** | Needs the owner to run it |

## One synthetic journey through the whole product (D75, 2026-10-29; local only)

Synthetic data, the receiver's stand-in of Freehire's documented API, and the independent
receiver; its ledger is the oracle. `frontend/e2e/journey.spec.ts`, desktop and mobile.

| Requirement | Step in `journey.spec.ts` | Result |
|---|---|---|
| Facts and preferences apart | "register; facts and preferences are kept apart" | work authorization per country; preferences on their own page |
| Proposed facts used only once approved | "a resume proposes facts" | 1 work and 1 education entry proposed, approved one by one |
| Normalization and dedupe | "discovery: normalized, deduplicated, never re-added" | the source's repeated listing links to the same job; a second search adds nothing |
| Preference review apart from eligibility | "job page: preferences explained apart from eligibility" | title and location reasons; "says nothing about eligibility or sponsorship" |
| Unknown becomes a checkpoint | "what is unknown is asked" | 3 questions asked; approval disabled until answered |
| Tailored material reviewed before use | "a tailored resume is read, accepted and chosen" | cited facts shown; offered at once after accepting (fixed) |
| Disclosure-only rehearsal | "a rehearsal fills and checks, and never submits" | ledger: +1 upload, +0 acceptances |
| Stale approvals invalidated | "a separate approval to submit; a fact changed after it invalidates it" | "Approval invalidated", the change shown, submit disabled until approved again |
| Versions consistent | "what arrived is what was approved, exactly once" | ledger: the new phone, the user's answer, the tailored DOCX's SHA-256; attempts `confirmed`, `rehearsed` |
| No blind resubmission | "no blind resubmission" | the same application reopens; queueing again refused; still 1 acceptance |
| Receipt, tracker, outcome timeline | "tracker: receipt, timeline and an outcome" | receipt-sourced state; link back to the application (fixed); outcome on the timeline |
| Fixtures never make a real destination ready | "fixture evidence never makes a real destination ready" | `real_destination_disabled`; no test-only form control (fixed) |

## Claude as the drafting provider, built and off (L4, 2026-10-29; local only, no request to Anthropic)

A stub SDK client (returning the SDK's own `Message` type) and a stub resolver stand in for
Anthropic's API and DNS; no key exists and nothing was sent. Decision D74.

| Requirement | Evidence | Result |
|---|---|---|
| Off unless the owner configures it | `tests/test_drafting_provider.py::test_off_unless_the_owner_configures_it`, `::test_without_a_provider_nothing_changes` | no provider without `anthropic`, NoEfforts' own key and a priced model; an ambient `ANTHROPIC_API_KEY` is ignored; 503 as before |
| The client: the server's key, no retries | `::test_the_client_uses_only_the_servers_key_and_never_retries`, `::test_the_key_never_reaches_a_response` | `max_retries=0`; the key is in no response and no settings dump |
| Owner account and consent to the exact text | `::test_a_draft_needs_the_owners_account_and_consent_to_this_text`, `::test_another_account_is_refused_and_one_consent_never_covers_another`, `::test_a_changed_consent_text_needs_a_new_agreement` | 409 `drafting_consent_needed`, 503 `drafting_not_for_this_account`, 409 `consent_text_changed`; nothing sent before consent or after withdrawal; audit by digest |
| Every sending provider is gated | `::test_every_provider_class_in_the_app_declares_whether_it_sends_anything_out`, `::test_an_unbound_provider_never_sends` | the one class sets `external = True`; an unbound one refuses |
| The request | `::test_the_request_is_the_rules_and_one_json_message_with_no_sampling_or_tools` | the rules as the system prompt; one ASCII JSON user message with the approved facts; JSON output schema; effort `medium`; no sampling, thinking or tool fields |
| The budget | `::test_no_budget_sends_nothing`, `::test_a_request_whose_worst_case_does_not_fit_is_never_sent`, `::test_the_worst_case_is_reserved_before_sending_then_the_reported_cost_is_kept`, `::test_a_settled_request_frees_what_it_did_not_use`, `::test_concurrent_reservations_never_pass_the_budget_together` | reserved before sending, then the reported cost; 6 concurrent reservations with room for 2: 2 reserved |
| Failures keep nothing | `::test_a_failure_keeps_nothing_and_says_why` (9 cases), `::test_an_api_host_resolving_to_a_private_address_is_never_contacted`, `::test_a_provider_draft_is_checked_like_every_draft` | 502 with a fixed code; no draft stored; timeouts, unknown errors and (D97) error replies such as 500 and 400 keep the worst case as `unknown`; only a request refused before it left is `not_sent` at 0; a private address is never contacted; the draft checks still apply |
| Tailored documents | `::test_a_tailored_resume_goes_through_the_same_checks` | the same gates; `document.generation_failed` audited by code |
| Migration | `tests/test_migrations.py::test_l4_adds_drafting_consents_and_usage_and_downgrade_drops_only_them` | one consent per user and provider; rows deleted with the user; downgrade drops only them |
| In the browser | `frontend/e2e/drafting-consent.spec.ts` (desktop, mobile; a synthetic consent view) | not configured said; what is sent and never sent shown; agree and turn off; the review page links to the profile card |
| Sabotage | 17 cases (owner, consent version, withdrawal, budget, lock, reported cost, any version, timeout cost, destination check, `external`, key, retries, refusal, job text in the system prompt, reservation after sending, unbound use, the gate) | 17 caught; the race case caught in 5 of 5 further runs, and passes 8 of 8 when intact |

## The Greenhouse pilot (D102, 2026-10-31; built and off)

The second local Greenhouse-style approximation (`fixtures/ats_receiver/greenhouse_v2.py`) plays a
real board host and its Job Board API (test-only settings); real Greenhouse hosts are refused in
the test environment. Decision D102.

| Requirement | Evidence | Result |
|---|---|---|
| Off by default | `tests/test_greenhouse_live.py::test_off_by_default_a_real_greenhouse_post_is_neither_read_nor_routed` | a real Greenhouse post: capture 409, route `real_destination_disabled`, no form kept |
| The owner's account only; per account | `::test_the_owner_captures_through_the_pilot_and_no_one_else_can` | owner: form `greenhouse_live`, route `browser`; another account: 409, `live_not_for_this_account`, the owner's job 404 |
| Production with the browser's own sandbox | `::test_the_pilot_runs_only_in_production_with_the_browsers_own_sandbox` | `needs_container` without `container`, `needs_production` outside production |
| Greenhouse board hosts only | `::test_only_a_job_post_on_a_greenhouse_board_host_is_the_pilots` | https, no port, no userinfo, exact hosts and paths; look-alikes refused |
| No real host from tests; public addresses in production | `::test_no_real_greenhouse_host_is_contacted_from_tests`, `::test_in_production_only_greenhouse_hosts_at_public_addresses_are_read` | refused before any connection; a Greenhouse name resolving to this machine refused; the stand-in ignored in production |
| robots.txt and the post's own data | `::test_robots_and_the_posts_own_identity_are_checked_before_a_form_is_kept` | `robots_disallowed`, `not_this_post`: nothing kept |
| No redirect; only Greenhouse's static assets | `::test_a_redirect_is_never_followed`, `::test_the_browser_may_load_only_greenhouses_static_assets_on_a_real_board` | redirect refused; the B3 CDN rule on a real board, none on the stand-in |
| Rehearsal first per employer | `::test_the_first_application_to_an_employer_is_a_rehearsal` | an approval to submit refused before the rehearsal; the rehearsal: disclosures, 0 accepted; then one acceptance |
| Switching it off stops what was approved | `::test_switching_the_pilot_off_stops_an_approved_application_before_anything_is_sent` | `failed_safe`; the ledger: 0 disclosures, 0 accepted; `live_not_enabled` |
| Fill, upload, outcome scenarios (the receiver's ledger) | `tests/test_greenhouse_dom.py` `pilot` cases, `tests/test_upload_evidence.py` `greenhouse_pilot`, `tests/test_execution_failures.py::test_reconciling_an_unknown_outcome_never_sends_again[greenhouse_live-*]` | every scenario its fixture levels require (`tests/provider_contracts.py` `SCENARIO_TESTS`) |
| Registry, admission, reason codes, documentation | `tests/test_providers.py`, `tests/test_provider_contracts.py`, `tests/test_provider_admission.py`, `tests/test_reason_codes.py` | the pilot alone names real destinations and claims no live support; admitted to `observed_read_only`; four `live_*` codes, each produced by a path |
| Deployment | `tests/test_deployment_config.py::test_the_greenhouse_pilot_override_changes_only_what_it_says` | `docker-compose.pilot.yml`: production for the API and worker; an outbound network for the egress proxy alone; the browser's networks stay internal |
| In the browser | `frontend/e2e/greenhouse-pilot.spec.ts` (desktop, mobile; a synthetic route) | refused while off; "Read the Greenhouse form" while on |

## Your Gmail, read-only (D101, 2026-10-31; local only)

A local stand-in of the Gmail API (`fixtures/ats_receiver/inbox_fixture.py`), synthetic messages
only. Decision D101.

| Requirement | Evidence | Result |
|---|---|---|
| Fixed wording, never guessed | `tests/test_inbox.py::test_messages_are_sorted_by_fixed_wording`, `::test_a_code_is_taken_only_when_exactly_one_follows_the_word` | seven kinds; mixed wording "unclear"; one code or none |
| Off until connected and turned on | `::test_nothing_is_read_until_the_owner_connects_it`, `::test_codes_are_never_read_while_turned_off` | 409 while off; no request to the mailbox while codes are off |
| A waiting code step filled once | `::test_a_waiting_code_step_is_filled_from_the_mail_once` | the receiver's challenge done and one acceptance; the message used once; no code in the database or the audit |
| Unclear codes left to you | `::test_a_code_from_another_sender_or_two_codes_are_left_to_you` | another sender ignored; two codes not entered; you type it |
| Outcomes proposed, confirmed by you | `::test_application_emails_are_proposed_and_confirmed_by_you` | proposed for the one named application; recorded as `user_reported` with the email's day on confirmation, once; nothing read twice; no text in responses |
| Per account | same test | another account sees no events; its accept is 404 |
| A "received" email settles an unknown outcome only with you | `::test_a_received_email_settles_a_submission_of_unknown_outcome_when_you_confirm`, `::test_a_received_email_is_only_noted_once_the_submission_is_settled`, `::test_a_proposed_reconciliation_is_refused_once_settled_another_way` | receiver accepted once, answer lost: `submitted_unconfirmed`; proposed; your confirmation is the reconcile transition (actor you, the email as evidence), once; 404 for another account; 409 once settled; after a receipt only noted; the ledger still shows one acceptance |
| Failures by code; hosts | `::test_a_refused_connection_is_reported_by_its_code`, `::test_the_reader_contacts_no_other_host`, `::test_an_unknown_id_is_never_requested` | `revoked` reported and audited by code; another host refused before connecting |
| Connecting | `::test_connecting_asks_for_read_only_mail_and_keeps_the_token_private` | read-only scope, PKCE S256, offline access; a non-Google server or another scope refused; token file 0600 |
| The guard | `tests/test_forbidden_capabilities.py::test_reading_mail_is_allowed_only_in_the_inbox_reader_and_only_its_names` | the reader's names only; IMAP, another scope or an SDK there fail, and the same names elsewhere fail |
| In the browser | `frontend/e2e/inbox.spec.ts` (desktop, mobile; a synthetic view) | 4 passed with `account.spec.ts`: not available said; a proposal confirmed; codes switch shown; no overflow |
| Sabotage | 14 cases | 14 caught (one after a test was added) |

## Listings by application platform (D100, 2026-10-31; local only)

Synthetic listing addresses, parsed and never fetched. Decision D100.

| Requirement | Evidence | Result |
|---|---|---|
| An import keeps only the chosen platforms | `tests/test_discovery_platforms.py::test_an_import_keeps_only_the_chosen_platforms` | Greenhouse and Lever of five: 2 kept and added to jobs, 3 filtered out and not stored |
| Listed and counted by platform, per account | `::test_postings_are_listed_and_counted_by_platform` | counts per platform with labels; `?platform=` filters; an unknown name is 422; another account sees none |
| Known platforms only | `::test_the_import_route_takes_known_platforms_only` | an unknown platform 422; local fixture addresses are "Other or not recognised" |
| In the browser | `frontend/e2e/discovery-platforms.spec.ts` (desktop, mobile) | Greenhouse only: 5 filtered out, 0 added; Other: 5 added; the list's filter with counts; no sideways scroll |
| Sabotage | 4 cases | 4 caught |

## Saved answers imported from a file (D99, 2026-10-31; local only)

Synthetic rows only. Decision D99.

| Requirement | Evidence | Result |
|---|---|---|
| Each row judged by the saved-answer rules | `tests/test_bank_import.py::test_each_row_is_judged_by_the_rules_for_saved_answers` | 18 rows: 3 importable; protected, sensitive, template, employer, time, credential, place, long text, placeholder, conflict (both rows), duplicate, blank refused; a dry run writes nothing; no row text in the response |
| Proposals, never used until approved | `::test_imported_answers_are_proposals_until_approved`, `::test_a_proposal_answers_nothing_until_you_approve_it` | `import` / `proposed`; a yes/no answer bound to the options Yes and No; history "imported from a file"; a new application uses it only after approval; approving twice is 409; audit counts only |
| Nothing replaced; per account | `::test_nothing_already_saved_is_replaced`, `::test_another_accounts_proposal_is_not_found` | `already_saved`; another account's proposal 404 |
| Limits | `::test_limits` | 0 rows, more than 5,000 rows or a question over 2,000 characters: 422 |
| In the browser | `frontend/e2e/answers-import.spec.ts` (desktop, mobile) | a JSON file checked and one row added; "Approve"; a review sheet keeps only the rows marked yes or edit, with the corrected answer |
| Sabotage | 9 cases | 9 caught |

## Question wordings from the owner's archive (D98, 2026-10-31; local only)

Synthetic paraphrases only; the archive stays private. Decision D98.

| Requirement | Evidence | Result |
|---|---|---|
| New sensitive topics never saved | `tests/test_classify_archive_wordings.py::test_a_sensitive_topic_is_never_saved` (17 wordings, select and text) | sensitive, not bankable, not draftable |
| Equal-opportunity topics in more forms | `::test_an_equal_opportunity_question_is_sensitive` (9) | sensitive `demographic` |
| Legal status in other words | `::test_a_legal_status_question_is_a_checkpoint` (13, select and text) | `legal_status`, protected, no value, not bankable |
| Licences and address parts | `::test_a_licence_or_an_address_part_is_never_saved` (8) | not bankable |
| Nothing nearby changed | `::test_nearby_wordings_are_unchanged` (9), `::test_the_bare_state_of_residence_label_is_still_a_profile_fact` | unchanged; existing suites 2,017 passed |
| Drafts | `::test_a_draft_that_states_a_new_topic_is_refused` | a draft stating first-generation status or a church is refused |
| Sabotage | 17 cases, one pattern each | 17 caught |

## Drafting spend view and ledger (D97, 2026-10-31; local only)

A stub SDK client and a stub resolver stand in for Anthropic; no key, no paid request. Decision D97.

| Requirement | Evidence | Result |
|---|---|---|
| Each amount says its basis | `tests/test_drafting_provider.py::test_the_spend_view_says_what_each_amount_is` | an estimate and a kept worst case shown apart; server total, what is left, tokens, 14 days, 20 requests, the price list; no prompt, draft, job text or key in the response |
| A request left unsettled | `::test_a_reservation_never_settled_is_shown_as_unknown_and_still_counts` | shown as held, then unknown after the timeout; still counted |
| Settled once | `::test_a_request_is_settled_once` | a second settlement returns False and changes nothing, either way round |
| The midnight boundary | `::test_the_budget_resets_at_midnight_utc` | a request reserved at 23:59:59 stays on its day when settled after midnight; the new day starts from 0 |
| Per account | `::test_the_spend_view_is_per_account_and_says_nothing_of_the_budget_to_others`, `::test_the_spend_view_with_drafting_off` | another account sees none of your rows and no server figures; off: nothing offered |
| Export | `::test_the_export_holds_the_usage_records_and_the_budget_settings` | rows with `cost_basis` and `price_version`; a `drafting_budget` block; no key |
| Migration | `tests/test_migrations.py::test_d97_gives_every_drafting_amount_its_basis` | reserved, not_sent, estimated, unknown; an old error row at 0 regains its worst case; downgrade drops only the two columns |
| In the browser | `frontend/e2e/drafting-spend.spec.ts` (desktop, mobile; a synthetic view) | not offered said; budget, reset, what is left, each basis, the price list; no sideways scroll on a phone |
| Sabotage | 10 drafting cases (see `implementation-status.md`, D97) | 10 caught |

## Form readiness wait (D97, 2026-10-31; local only)

| Requirement | Evidence | Result |
|---|---|---|
| A ready page proceeds at once | `tests/test_form_readiness.py::test_a_ready_page_proceeds_at_once` | under 1 s (113 ms median in the adapter tests, 491 ms before) |
| A slow request of the page is waited for | `::test_a_slow_request_of_the_page_is_waited_for`, `tests/test_dropdown_strategies.py` (`locale_delay_ms` 2500) | waited for the 1.2 s request; the slow locale case still selects the approved option |
| Never ready stops safely | `::test_a_page_that_never_finishes_loading_is_not_ready`, `tests/test_dropdown_strategies.py::test_a_form_still_loading_after_the_allowance_stops_before_anything_is_entered` | not ready at the allowance; failed safe; the receiver's ledger: nothing disclosed or accepted, the locale file requested once, GET only |
| Not waited on | `::test_images_and_event_streams_are_not_waited_for` | a hanging image and an open event stream: ready under 1 s |
| Listeners removed | `::test_the_tracker_stops_listening_when_closed` | nothing counted after close |
| Sabotage | 5 readiness cases | 5 caught |

## Public-address check before every real server-side request (R10.5, 2026-10-29; local only)

No request to any real host was made: a stub resolver and a stub opener stand in for the network.

| Requirement | Evidence | Result |
|---|---|---|
| The read-only check's API host must resolve publicly before anything is sent | `tests/test_gh_readonly.py::test_the_real_api_host_must_resolve_publicly_before_anything_is_sent` (private, loopback, metadata) | stopped; nothing sent, nothing counted |
| Checked before every request, not only the first | `::test_a_public_api_host_is_checked_before_every_request` | resolved twice for two requests |
| The local fixture is never resolved | `::test_the_local_fixture_is_not_resolved` and the existing fixture tests | unchanged |
| The other server-side fetches | `test_freehire_live_read.py::test_the_live_address_is_checked_before_the_approval_is_used` (S7); `test_greenhouse_adapter.py::test_real_greenhouse_posts_are_not_read` (capture reads fixtures only) | already covered |
| Sabotage | 4 cases (no check, first request only, fixture resolved, unsafe ignored) | 4 caught |

## Tailored resumes and cover letters (L2, L3, 2026-10-29; local only, no provider)

A labelled test double stands in for the provider; none is configured. Decision D73.

| Requirement | Evidence | Result |
|---|---|---|
| Nothing without a provider | `tests/test_generated_documents.py::test_nothing_is_generated_without_a_provider` | 503; nothing stored |
| Stored unaccepted for one application | `::test_a_tailored_resume_is_stored_unaccepted_for_this_application`, `::test_a_cover_letter_is_generated_without_a_base`, `::test_a_docx_round_trips_and_escapes_markup` | DOCX, `generated`, its application, its cited facts; refused until accepted; then in the package with its provenance |
| Checked like drafts | `::test_a_document_failing_the_draft_checks_is_never_stored`, `::test_the_request_holds_only_approved_facts_and_quoted_job_text` | four codes; nothing stored; audit by code only |
| Diff from the base | `::test_a_tailored_resume_shows_what_changed_from_its_base` | the changed lines |
| Never elsewhere, never stale | `::test_a_document_is_never_used_for_another_application`, `::test_a_changed_fact_makes_it_unusable`, `::test_a_document_whose_facts_changed_cannot_be_accepted` | 409 with its code; the row asks again, never another document in its place |
| Reject; other users | `::test_rejecting_deletes_it_and_its_file`, `::test_another_users_application_and_documents_are_404` | row and file gone; 404 |
| In the browser | `frontend/e2e/generated.spec.ts` (desktop, mobile; a synthetic list) | not configured said; cited facts and changes shown; accepted |
| Sabotage | 9 cases | 9 caught (one after a stale-accept test was added) |

## Facts proposed from a resume (L1, 2026-10-29; local only, no provider)

Synthetic PDF, DOCX and TXT files built in the tests. Decision D72.

| Requirement | Evidence | Result |
|---|---|---|
| Text from PDF, DOCX, TXT | `tests/test_resume_facts.py::test_text_is_read_from_pdf_docx_and_txt`, `::test_only_the_first_pages_of_a_long_pdf_are_read` | the same lines; 10 pages at most |
| Unreadable files | `::test_unreadable_documents_say_why`, `::test_a_docx_whose_document_part_is_too_large_is_refused` | `unreadable`, `no_text`, `unsupported`, `too_large` |
| Only stated facts | `::test_only_stated_facts_are_proposed`, `::test_nothing_is_inferred` | work, education, credentials; dates kept as written; two legal and sensitive lines skipped |
| Proposed until approved | `::test_proposed_facts_wait_for_approval_and_are_not_used_until_then` | `proposed`, `resume_parse`; no grounding fact until approved; audited by count |
| Once only; other users | `::test_proposing_again_adds_nothing_already_there`, `::test_errors_and_other_users` | nothing twice; 404 across users; a cover letter refused |
| In the browser | `frontend/e2e/documents.spec.ts` "a resume's facts are proposed" (desktop, mobile) | proposed, approved one by one |
| Sabotage | 9 cases | 9 caught (one rerun after its edit was a syntax error, which proves nothing) |

## SCHEMA_VERSION 3 (C18, 2026-10-29; local only)

Synthetic data. Decision D71. Every approval given under 2 is invalidated.

| Requirement | Evidence | Result |
|---|---|---|
| Preference facts hashed by value | `tests/test_schema_v3.py::test_changing_only_the_salary_range_is_a_new_version` | the same number sent, a new version and hash |
| The shape | `tests/test_package_contract.py` (shape 3 beside an unchanged shape 2) | equal |
| `accept` enforced | `::test_accepts` (8 cases), `::test_a_txt_resume_into_a_pdf_or_docx_field_is_a_checkpoint` | a checkpoint; no document sent |
| Implicit and chosen resumes | `::test_an_implicit_resume_is_explained_as_proposed_and_a_chosen_one_as_chosen` | two explanations |
| Generated documents | `::test_a_generated_document_is_used_only_once_accepted`, `::test_an_uploaded_document_records_its_origin` | 409 until accepted; provenance in the package |
| An answer awaiting consent | `::test_an_answer_awaiting_consent_is_never_written_into_a_version`, `tests/test_disclosure_ledger.py` | empty in every version; shown from the live answer; included, then withheld |
| Old approvals | `::test_an_approval_given_under_schema_2_is_invalidated` | a new version; not approved |
| Sabotage | 9 cases | 9 caught |

## Deleting documents (C17, 2026-10-29; local only)

Synthetic documents and the generic receiver. Decision D70.

| Requirement | Evidence | Result |
|---|---|---|
| A version, then every version | `tests/test_document_deletion.py::test_deleting_a_version_removes_its_row_and_file_only`, `::test_deleting_a_document_removes_every_version` | download 404; the files gone; the other version kept; audited with scope and count |
| Another user | `::test_another_users_document_is_404_and_untouched` | 404; file and download untouched |
| Never while needed | `::test_a_document_in_an_approved_package_is_not_deleted_until_revoked`, `::test_a_document_a_running_attempt_needs_is_not_deleted` | `document_in_approval` until revoked, then deleted and the package asks again; `document_in_attempt` even after the approval expired |
| Race with an approval | `::test_a_delete_waiting_for_an_approval_in_progress_sees_it` | waits on the application lock, then refuses |
| An application's choice | `::test_an_application_that_chose_a_deleted_version_asks_again`, `::test_a_past_package_version_keeps_only_what_it_recorded` | the choice removed; the new version without it; the diff shows it gone |
| In the browser | `frontend/e2e/documents.spec.ts` (desktop, mobile) | a version, then the document, deleted |
| Sabotage | 8 cases | 8 caught |

## Credentials as grounded facts (C16, 2026-10-29; local only, no provider)

Synthetic credentials; labelled test doubles. Decision D69.

| Requirement | Evidence | Result |
|---|---|---|
| Only approved, unexpired credentials of this user | `tests/test_credentials.py::test_only_approved_unexpired_credentials_of_this_user_ground_a_draft` | expiring today and no expiry kept; expired, proposed, rejected and another user's excluded |
| A credential named only from a cited credential | `::test_a_credential_named_in_a_draft_must_be_a_cited_credential`, `::test_a_draft_cannot_claim_an_expired_credential` | `uncited_credential` for a job title, an employment description or an expired credential |
| Never saved for reuse | `::test_a_licence_answer_is_never_saved_for_reuse`, `::test_a_licence_question_is_never_answered_from_the_profile_or_the_bank`, `tests/test_bank_scope.py` (48 table rows) | 400; nothing saved; answered for each application |
| Only narrows | `::test_the_credential_family_only_narrows`, `tests/test_bank_scope.py::test_every_family_use_is_load_bearing` (four new witness rows) | other categories kept; every family still load-bearing |
| Sabotage | 8 cases | 8 caught |

## Drafting hardening (C15, 2026-10-29; local only, no provider)

Labelled test doubles stand in for a provider; nothing is sent anywhere. Decision D68.

| Requirement | Evidence | Result |
|---|---|---|
| Each rejection code | `tests/test_drafting.py::test_each_rejection_code` (13 cases), `::test_the_codes_are_listed_and_documented` | every code produced; the audit table lists them |
| Numbers from the job text, the question or an uncited fact | `::test_numbers_echoed_from_the_job_text_or_the_question_are_rejected`, `::test_a_number_from_a_fact_the_draft_does_not_cite_is_rejected` | `invented_numbers` |
| Legal status and sensitive topics | the parametrized rows ("never need sponsorship", "as a woman and veteran", citizenship, disability, criminal record) | `legal_status`, `sensitive_topic` |
| Planted instruction (R11.9) | `::test_the_prompt_quotes_employer_text_and_never_lets_it_out`, `::test_a_planted_instruction_never_changes_the_facts_and_obeying_it_is_rejected` | the job text is one quoted string; the facts are the same with or without it; obeying it is rejected |
| Grounding scope | `::test_grounding_uses_only_this_users_approved_records` | proposed, rejected and other users' records excluded |
| Accept checks | `::test_a_fact_edited_between_request_and_accept_is_refused`, `::test_a_question_reworded_before_accept_is_refused`, `::test_a_question_that_can_no_longer_be_drafted_is_refused`, `::test_a_draft_that_no_longer_fits_is_a_409_not_a_500` | 409 with `draft_facts_changed`, `draft_inputs_changed`, `not_draftable`, `draft_does_not_fit` |
| Audit, cited facts, cache, order | `::test_accepting_is_audited_by_reference_and_shows_the_cited_facts`, `::test_drafts_are_listed_in_the_order_they_were_made` | `draft.accepted` with a reference only; an accepted draft returned as accepted; creation order |
| Rejecting | `::test_rejecting_erases_the_text_and_it_is_never_offered_again`, `::test_an_accepted_draft_is_not_rejected_and_another_users_is_404` | text NULL; `by_user`; a new draft next time; 404 across users and applications |
| In the browser | `frontend/e2e/drafts.spec.ts` (desktop, mobile; the package view with one synthetic draft) | cited facts shown; a changed fact flagged; rejected |
| Sabotage | 17 cases | 17 caught (the order test rewritten so that a wrong order is always caught) |

## Freehire contract hardening (S6, 2026-10-28; fixture only, no Freehire API request)

The local stand-in of Freehire's documented API on the receiver; its request table is the
oracle for what was asked. Synthetic listings. Decision D67.

| Requirement | Evidence | Result |
|---|---|---|
| Counters and `reality` are not a change (R9.4) | `tests/test_freehire_discovery.py::test_counters_and_reality_ticking_are_not_a_change` (mode `fh_reality_tick`) | import 0 changed, 5 unchanged; refresh `unchanged`; a real change still counted |
| Tagged and referral URLs (R9.5) | `::test_a_tagged_url_and_its_untagged_form_are_one_posting` | one `dedupe_key`; same ATS |
| Aggregator address (R9.6) | `::test_an_aggregator_url_is_an_unknown_ats_and_a_manual_handoff` | `unknown`; manual handoff |
| Undocumented fields (R9.7) | `::test_the_2026_10_26_undocumented_fields_are_not_read` | same record, same fingerprint |
| Waiting after `Retry-After` (R9.2) | `::test_an_import_before_retry_after_is_refused`, `::test_a_refused_refresh_holds_back_the_next_refresh_and_import`, `::test_without_retry_after_nothing_is_held_back`; `test_freehire_live_read.py::test_a_run_held_back_by_retry_after_does_not_use_its_approval` | 429 with "Nothing was sent", no request in the stand-in's table; another user not held back; no wait without the header; the live approval left unused |
| Migration | `tests/test_migrations.py::test_s6_adds_the_discovery_backoffs_and_downgrade_drops_only_them` | added; dropped alone on downgrade |
| In the browser | `frontend/e2e/discovery.spec.ts` "a listing refreshes from its source; a Retry-After holds the next request back" (desktop, mobile) | unchanged, gone, refused with Retry-After, then held back |
| Sabotage | 8 cases | 8 caught (one after a 429 without `Retry-After` was added) |

## Version diff (C14, 2026-10-28; local only)

The receiver's form and a fictional manual form; synthetic data. Decision D66.

| Requirement | Evidence | Result |
|---|---|---|
| A changed answer by its label | `tests/test_version_diff.py::test_a_changed_answer_is_shown_by_its_label_and_shown_values` | one row; before and after as shown; no fact references |
| Since the approved version | `::test_what_changed_since_the_approved_version` | the approved side marked; consent change shown |
| A new document version | `::test_a_new_document_version_is_shown` | shown by name |
| A reworded question | `::test_a_reworded_question_is_shown_as_a_changed_question` | question and answer changed |
| Read-only | `::test_the_diff_is_read_only`, `::test_the_diff_never_builds_a_version` | no package version or audit row added |
| Unknown version, another user | `::test_unknown_versions_and_other_users_are_404` | 404 |
| In the browser | `frontend/e2e/review-edit.spec.ts` "after an edit, the page shows what changed since the approved version" | the change listed by label |
| Sabotage | 6 cases | 6 caught (one after a test was added for a pending version) |

## Approval reasons and revoking (C13, 2026-10-28; local only)

The generic receiver; its ledger is the oracle. Decision D65.

| Requirement | Evidence | Result |
|---|---|---|
| The document lists exactly the codes | `tests/test_approval_reasons.py::test_the_document_lists_exactly_the_codes` | equal |
| Each code produced by its path | `::test_approval_refusals_carry_their_codes`, `::test_queueing_refusals_carry_their_codes`, `::test_a_recorded_confirmation_is_never_queued_again_with_its_code` | 409 with `(reason: code)` for all nine |
| Revoke before a worker takes the attempt | `::test_revoking_before_a_worker_takes_the_attempt_stops_it_at_once` | cancelled at once; waits for approval; a late delivery ignored; nothing disclosed; approving again submits once |
| Revoke while a worker holds it | `::test_revoking_while_a_worker_holds_the_attempt_leaves_it_to_the_gates`; `test_lock_order.py::test_a_revoke_arriving_while_a_worker_claims_the_attempt_waits_then_leaves_it_to_the_gates` | the gate refuses; nothing disclosed; no deadlock |
| Revoke after the final click | `::test_revoking_after_the_final_click_is_refused` (sending, awaiting a code); `test_lock_order.py::test_a_revoke_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it` | refused with `revoke_in_flight`; the approval unchanged |
| Cross-tenant | `::test_another_users_revoke_is_404` | 404 |
| In the browser | `frontend/e2e/approval-revoke.spec.ts` (desktop, mobile) | the notice says what was stopped; refused while submitting with its code; the ledger counts |
| Sabotage | 6 cases | 6 caught |

## Review page: change, clear, optional answers, cover letter, destination (C12, 2026-10-28; local only)

The Greenhouse-like fixture form and the generic receiver; synthetic data. Decision D64.

| Requirement | Evidence | Result |
|---|---|---|
| Each question says what the page may offer | `tests/test_review_controls.py::test_each_question_says_what_the_page_may_offer`, `::test_the_page_controls_never_change_the_package` | outside the content; a question not asked, a document, an acknowledgment and a profile fact are not answered here |
| Clearing an answer | `::test_clearing_an_answer_removes_it_and_is_audited_without_its_key` | needs an answer again; one audit row with a reference, never the key |
| Cover letter chosen and left out | `::test_an_optional_cover_letter_is_chosen_and_left_out_again` | sent, then not; a resume refused as a cover letter |
| Cross-tenant | `::test_another_users_application_cannot_be_cleared_or_changed` | 404; nothing changed |
| Where the form sends | `::test_the_page_says_where_the_form_sends` | fixture or employer label |
| In the browser | `frontend/e2e/review-edit.spec.ts` (desktop, mobile) | change, clear, answer again, an optional answer; the ledger holds the changed values; a cover letter chosen, then "None" |
| Sabotage | 6 cases | 6 caught |

## Salary units (C9, 2026-10-28; local only)

Synthetic preferences; no database. Decision D63.

| Requirement | Evidence | Result |
|---|---|---|
| Sent only in units the question allows | `tests/test_resolver.py::test_a_salary_is_sent_only_in_units_the_question_allows` (8 cases) | a number only with both units stated; text with its own units |
| Other or unstated units are the user's | `::test_a_salary_in_other_or_unstated_units_is_the_users_answer` (15 cases), `::test_a_bare_dollar_sign_is_not_another_currencys_answer` | needs the user; nothing sent |
| No currency or period in Preferences | `::test_an_expectation_without_its_currency_or_period_is_never_sent` | never sent |
| Sweep | 805 forms × 32 contexts against the C8 tree | 5,476 withdrawals; the only new values are the user's typed answers |
| Sabotage | 8 cases | 8 caught |

## Fixture variants from the legacy notes (S5, 2026-10-28; local only)

FIXTURE ASSUMPTIONS from `legacy-audit.md` R7: they show what the adapters do on such a page,
not that a real page behaves this way. The receiver's ledger is the oracle. Decision D62.

| Requirement | Evidence | Result |
|---|---|---|
| Confirmation bound to the attempt (R6.4, R6.5, §1.0 item 12) | `test_greenhouse_adapter.py::test_confirmation_bound_to_attempt`, `test_greenhouse_dom.py::test_confirmation_bound_to_attempt`, `test_execution_failures.py::test_confirmation_bound_to_attempt`, `test_api_provider.py::test_confirmation_bound_to_attempt` | words on the form, a path saying "confirmation", another posting's page, a message present before the click, another application's acceptance: never confirmed |
| A box the page unticks (R2.9) | `test_greenhouse_adapter.py::test_readback_mismatch_stops_before_submit_when_the_page_unticks_an_approved_box` | abandoned before the send gate; 0 acceptances |
| Autofill after an upload (R2.7) | `test_greenhouse_dom.py::test_readback_mismatch_stops_before_submit_when_an_upload_rewrites_fields` | abandoned; 2 fields counted; the upload kept |
| Code boxes and unknown code steps (R7.4) | `test_greenhouse_adapter.py::test_code_entered_by_user_only_one_character_per_box`, `::test_code_entered_by_user_only_an_unrecognised_code_entry_is_never_filled` | only the user's code; a code that does not fit never typed; unknown code step: nothing typed |
| Bot check after the click (R4.9b) | `test_greenhouse_adapter.py::test_a_challenge_after_the_final_click_is_never_confirmed_or_clicked_again`, the same in `test_greenhouse_dom.py` | unknown, one click in the ledger, never clicked again |
| Banners and "I agree" (R11.8) | `test_greenhouse_adapter.py::test_no_cookie_banner_or_i_agree_button_is_ever_clicked`, `::test_a_submit_button_waiting_for_an_unlisted_click_stops_before_the_final_click` | no click recorded; a disabled submit stops before the send gate |
| A second page (R2.10, §1.0 item 4) | `test_greenhouse_adapter.py::test_each_step_read_back_before_next_a_second_page_stops_before_disclosure`, the same in `test_greenhouse_dom.py` | failed_safe before any disclosure; captured that way, refused |
| An unlisted option (§1.0 item 6) | `test_greenhouse_dom.py::test_unlisted_option_is_checkpoint` | failed_safe before any disclosure, counted, never named |
| Admission scenarios (R3.1) | `test_provider_contracts.py::test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap` | every new pair mapped to a ledger test; no gap |
| Sabotage | 15 cases (each adapter safeguard, the three admission rules) | 15 caught |

## The disclose path, counted by the receiver (C8, 2026-10-28; local only)

The synthetic receiver's own ledger is the oracle; a synthetic candidate. Decision D61. No
external request.

| Requirement | Evidence | Result |
|---|---|---|
| "Include this answer" sends the answer | `tests/test_disclosure_ledger.py::test_include_sends_your_answer` | the ledger holds `gender=w` |
| "Don't disclose" on an optional question sends nothing | `::test_dont_disclose_on_an_optional_question_sends_nothing` | no value in the ledger |
| An answer without a choice is never sent | `::test_an_answer_without_a_choice_is_never_sent`, `::test_a_required_question_without_a_choice_blocks_approval` | approval refused (409); nothing accepted |
| "Don't disclose" on a required question | `::test_dont_disclose_on_a_required_question_sends_the_forms_decline_option`, `::test_the_decline_option_is_shown_for_review_and_never_saved` (receiver mode `required_eeo`) | the ledger holds `gender=decline`; the row says why; never saved |
| Only one exact decline option is used | `::test_the_one_decline_option_is_the_answer`, `::test_without_exactly_one_decline_option_a_required_question_stays_a_checkpoint`, `::test_the_decline_option_is_never_picked_without_dont_disclose`, `::test_an_optional_question_is_left_blank_even_with_a_decline_option`, `::test_a_multi_choice_decline_is_one_selected_option`, `::test_a_text_question_has_no_decline_option` | no option, two, or a looser wording: checkpoint |
| A saved answer needs "Include" on each form | `::test_a_saved_answer_is_proposed_and_sent_only_after_include` | proposed, then sent after the choice |
| In the browser | `frontend/e2e/submission.spec.ts` "a sensitive answer is sent only as chosen" (desktop, mobile) | the ledger holds `w`, then `decline` |
| Sabotage | removing the mapping, taking the first of several, applying it to optional questions, a substring match, saving it | each caught (7, 1, 2, 5 and 5 failures) |

## Answers and consents bound to their question (C7, 2026-10-28; local only)

A fictional manual form recaptured with other wording. Decision D60. No external request.

| Requirement | Evidence | Result |
|---|---|---|
| An answer for another wording is asked again | `tests/test_input_binding.py::test_an_answer_for_another_wording_is_asked_again`, `::test_a_choice_answer_for_other_options_is_asked_again` | the same question recaptured keeps the answer; other wording or options: unanswered, with the reason |
| Agreeing to one statement never agrees to another | `::test_agreeing_to_one_statement_never_agrees_to_another` | the reworded acknowledgment is unanswered and blocks approval until agreed again |
| "Include this answer" covers only the answer it was given for | `::test_a_disclose_choice_covers_only_the_answer_it_was_given_for`, `::test_the_digest_is_scoped_to_the_user_and_the_question` | a changed answer needs the choice again; the row holds a keyed digest, never the answer; "Don't disclose" is kept |
| Rows saved before C7 | `::test_rows_saved_before_binding_use_the_form_version_they_were_saved_against` | compared with the form version current when saved; a "disclose" without a digest asked again |
| Approval | `::test_a_changed_question_invalidates_the_approval_of_its_answer` | invalidated; the changed question unresolved |

## Job signals (S3, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the source; synthetic jobs and
applications. Decision D59. Nothing contacted Freehire or an employer.

| Requirement | Evidence | Result |
|---|---|---|
| Approval waits while you excluded or closed the job (R5.11) | `tests/test_job_signals.py::test_approval_waits_while_you_excluded_or_closed_the_job` | 409 with the reason code; no approval row; the review and job pages carry the message |
| A posting its source closed, or that is gone, waits for "still open" (R9.8) | `::test_a_posting_its_source_closed_waits_for_your_statement` (closed, gone), `::test_a_posting_missing_from_a_listing_is_not_a_closed_posting` | the tracker job unchanged; refused until your statement; the same report repeated keeps it answered; a new closure after it asks again |
| A repost is a possible duplicate, never merged (R5.9) | `::test_a_repost_is_a_possible_duplicate_and_never_merged` (fixture mode `fh_repost`), `::test_the_same_role_is_the_same_employer_title_and_location` (7 cases), `::test_a_draft_application_is_not_a_prior_application`; `frontend/e2e/job-signals.spec.ts` | a new job; the other job's application state and outcome shown; both copies refused until "a different role"; a later application asks again |
| Concurrent approvals of two copies (R12.5) | `::test_concurrent_approvals_of_two_copies_are_both_refused` | both refused, no approval row |
| Another user's applications are never a signal (R13) | `::test_another_users_applications_are_never_a_signal_and_their_jobs_are_not_found` | no duplicate; 404 for their job; nothing audited for them |
| Greenhouse embed URLs (R5.10) | `::test_a_greenhouse_embed_url_is_the_same_posting_as_its_board_url`, `::test_a_job_stored_under_its_url_key_is_found_again` | same identity as the board URL; a job stored under its old key found again |
| Reason codes and migration | `::test_the_reason_codes_are_documented_exactly`; `tests/test_migrations.py::test_s3_adds_the_job_signal_times_and_downgrade_drops_only_them` | `docs/job-signals.md` lists exactly the codes; stale rows backfilled; downgrade drops only the three columns |

## One link of a kind (C10, 2026-10-28; local only)

Resolver tests with synthetic links, and one fictional manual form in the browser. Decision D58.
No external request.

| Requirement | Evidence | Result |
|---|---|---|
| The one link of its kind is the answer, the same address spelled twice being one | `tests/test_resolver.py::test_the_one_link_of_its_kind_is_the_answer` (8 cases: another kind beside it, `www.`, a trailing slash, a LinkedIn subdomain, `/pub/`, a company page beside a profile) | Profile fact, the links fact recorded |
| Several links of one kind are never chosen between | `::test_several_links_of_one_kind_are_never_chosen_between` (4 cases) | nothing sent; the user's typed answer or a saved answer to this exact question; the links fact kept on a typed answer |
| The host decides the kind | `::test_a_link_of_another_kind_is_never_the_answer` (7 cases: a company or jobs page, look-alike hosts, a query string, a LinkedIn link for a website question) | no answer from the profile |
| The review page says why | `frontend/e2e/review-reasons.spec.ts` | the count of LinkedIn profile links and S4's "not a web address" shown under each question, with its answer box |

## State, City and Country lists (C11, 2026-10-28; local only)

Resolver tests with synthetic facts, and one fictional manual form through the API. Decision
D57. No external request.

| Requirement | Evidence | Result |
|---|---|---|
| A list naming every US state gets the profile's state, by name or postal code, for a US residence | `tests/test_resolver.py::test_a_list_of_every_us_state_gets_the_profiles_state` (13 lists); corpus row `r8_6_ctrl_state_select_every_us_state` | Mapped from profile, the fact recorded, never saved |
| Any other State list is the user's answer for this application, never a dead end | `::test_any_other_state_list_is_the_users_answer_for_this_application` (16 lists: not offered, twice, name and code, short, incomplete, near match, part of a name, unknown or another country, an Australian or Kenyan list, yes/no), `::test_one_state_is_not_a_set_of_options`; corpus rows `r8_6_state_select_short_list_has_residence`, `r8_6_state_select_code_shared_by_another_country` | nothing sent; the user may answer; a saved answer never takes its place; the answer keeps the fact, so a profile edit asks again |
| A City list is never picked from the profile | `::test_a_city_list_is_never_picked_from_the_profile`; `frontend/e2e/place-lists.spec.ts` (the review page says why and offers no reuse); corpus rows `r8_3_city_select_residence_offered_required`, `r8_3_location_radio_residence_offered_required` | the offered residence city is not ticked; the user answers it; typed text still gets the profile's city |
| A Country list without exactly one option for the profile's country is answered by the user | `::test_a_country_list_without_one_option_for_your_country_is_answered_for_this_application`; corpus row `r8_6_country_select_without_residence` | no snapped option; the user may answer |
| Through the API: refused reuse, the typed answer kept, a move re-maps the state | `tests/test_answers_that_do_not_fit.py::test_state_city_and_country_lists_are_never_a_dead_end` | 400 for reuse and for typing over the mapped state; 200 for the per-application answer; a new version and an invalidated approval after the profile moves |
| A State list still asks for the state in the profile when there is none | `::test_a_state_list_without_a_verified_state_still_asks_for_it_in_the_profile` | unchanged: no per-application answer for a missing or unapproved state |

## Watched Freehire searches (S8, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the live origin; its request table is the
oracle. Decision D56. Nothing contacted Freehire.

| Requirement | Evidence | Result |
|---|---|---|
| A new posting reaches the job list at the next check, with one request | `tests/test_freehire_watch.py::test_a_new_posting_reaches_the_job_list_at_the_next_check`, `::test_a_check_asks_for_the_newest_postings_first` | the first check reads two pages; the next reads one page, newest first, and stops at a known posting |
| Never more often than the interval; never two checks of one watch at once | `::test_a_watch_is_checked_no_sooner_than_its_interval`, `::test_one_watch_is_never_checked_twice_at_once` | no request inside the interval; a locked watch is skipped |
| Only an owner's active watch reads | `::test_only_an_active_watch_of_an_owner_reads`, `::test_discovery_off_means_no_check`, `::test_another_address_pauses_the_watch`, `::test_the_address_is_checked_before_every_check` | another account or another address: paused, no request; stopped or ended watches: never checked |
| Bounded by Freehire's answers and the daily cap; never retried inside a check | `::test_a_429_waits_for_retry_after_and_nothing_is_retried_inside_a_check`, `::test_a_longer_retry_after_than_the_interval_is_honoured`, `::test_failures_back_off_and_ten_in_a_row_pause_the_watch`, `::test_the_daily_request_cap_is_never_passed` | waits 60, 120 … 3,600 s; at least Retry-After; paused after ten; the cap defers to the next UTC day |
| Watches are the owner's to see and stop; the command bounds them | `::test_watches_are_listed_and_stopped_only_by_their_owner`, `::test_the_watch_command_records_a_bounded_standing_approval`; `tests/test_migrations.py::test_s8_adds_bounded_watches_and_downgrade_drops_only_them` | another user: empty list, 404; 60 s to a day, at most 90 days |
| A deleted posting stays deleted | `::test_a_deleted_posting_is_erased_and_never_pulled_again`, `::test_deleting_a_posting_keeps_a_job_you_applied_to`; `frontend/e2e/discovery.spec.ts` | content erased, id kept, its job removed unless it has an application; a later search does not add it back |

## Owner-approved live Freehire read (S7, 2026-10-28; local only)

The local stand-in of Freehire's documented API plays the live origin; its request table is the
oracle for what was asked. Decision D55. Nothing contacted Freehire.

| Requirement | Evidence | Result |
|---|---|---|
| No live read without the owner's approval for the exact search | `tests/test_freehire_live_read.py::test_a_live_read_without_an_approval_is_refused_and_asks_nothing`, `::test_the_approval_binds_the_exact_search`, `::test_an_approval_outside_its_window_is_refused` | 403, no request, the approval left unused |
| One approval, one run, before the first request | `::test_with_its_approval_the_owner_reads_live_once`, `::test_a_failed_run_used_its_approval_and_is_never_rerun`, `::test_the_approved_page_limit_holds` | the second run is refused; a failed run is not re-run; at most the approved pages |
| Owner account only | `::test_only_the_owner_account_reads_live`; `tests/test_freehire_discovery.py::test_a_live_base_url_is_refused_before_any_request` | another account, or no owner configured: 403, nothing looked up or requested |
| The address is public before any request; no other address | `::test_the_live_address_is_checked_before_the_approval_is_used`, `::test_any_other_address_stays_refused_with_an_approval`, `::test_the_live_flag_opens_only_the_live_origin`, `::test_refresh_and_healthcheck_never_read_live` | refused before a request, the approval left unused |
| The approval command records one bounded run | `::test_the_approval_command_records_one_bounded_run`, `::test_the_approval_command_refuses_an_account_that_does_not_exist`; `tests/test_migrations.py::test_s7_adds_bounded_run_approvals_and_downgrade_drops_only_them` | 1-5 pages, 1-24 hours, a search and a retention statement; database checks refuse the rest |

## Legacy collision corpus and static guards (S4, 2026-10-27; local only)

Synthetic wordings and facts with sentinel values; no legacy data. Decision D54; rules in
`docs/answer-policy.md` (rows 1a, 2a, 3, 4 and the S4 rules). "Before" is the previous commit's
resolver on the same rows.

| Requirement | Evidence | Result |
|---|---|---|
| Each legacy wording trap gets only its safe outcome | `tests/test_resolver.py::test_a_legacy_collision_gets_only_its_safe_outcome` (244 rows of `tests/legacy_collisions.json`, each run through `package.resolve_answers` with sockets refused) | before: 104 of 244 rows wrong (47 of the first 164); now 0. Every control row passes on both |
| The corpus covers each plan row and its legacy finding; the sentinel check sees a leak | `::test_the_corpus_covers_each_plan_row_and_names_its_legacy_finding`, `::test_the_sentinel_check_sees_a_leak` | R8.1-R8.11, R8.16, R2.9 each have rows; the reuse rows have an exact-reuse control |
| A fact that does not fit its field is never sent, and becomes the user's answer | `::test_a_fact_answer_that_does_not_fit_its_field_is_never_resolved`, `::test_a_multi_answer_is_a_non_empty_set_of_offered_options`, `tests/test_answers_that_do_not_fit.py::test_a_fact_that_does_not_fit_is_the_users_answer_never_saved_and_tied_to_the_fact` | before: a link typed into a Yes/No choice, a country as text into a multi-select, "Yes" into a long answer. Now the user answers it for this application only (saving it for reuse is a 400 and writes nothing), and changing the fact it was about invalidates the approval |
| Each new pattern matches what it is for and nothing else | `tests/test_classify_vocabulary.py::test_each_pattern_added_for_the_legacy_corpus_matches_what_it_is_for`, `::test_residence_nationality_and_a_negated_right_to_work_are_protected`, `::test_a_statement_that_names_no_fact_the_grammar_reads_is_never_checked`, `::test_a_statement_about_no_profile_fact_stays_your_consent_choice` | over-narrowing found by the review ("US-based hours", a language row, Workday's "My Experience", a rating scale) pinned as controls |
| A negated right to work with a sensitive help, option or section stays sensitive (review round 3) | `tests/test_resolver.py::test_a_negated_right_to_work_with_a_sensitive_signal_stays_sensitive`; corpus row `r8_10_prevent_work_help_disability`; the third-person preference rows `r8_3_city_help_team_would_like`, `r8_3_country_select_step_we_would_like` | before the round-3 fix: a typed answer resolved with no disclose choice and a Country follow-up filled from residence; a City or Country field whose help says the team would like you somewhere filled from residence. Both as at the previous commit now |
| Page text cannot make one field slow (review round 3) | `tests/test_classify_vocabulary.py::test_residence_nationality_and_a_negated_right_to_work_are_protected` (a list of eleven places); equivalence and timing checked with scratch scripts | before: up to 215 ms for one field and about 60 s for a 300-field form; now about 1.5 ms per field. The windowed negation search equals the old one on 200,000 random help texts |
| A typed number is shown with every digit | `tests/test_resolver.py::test_a_typed_number_is_shown_with_every_digit` | before: 912345678 was shown as "9.12346e+08" (six significant digits) |
| Only narrowing | the sweep in D54 (scratch harness, not in the repository) | 16,359 forms x 432 contexts, 7,080,048 rows against the previous commit's resolver: 0 newly answered automatically, bankable or draftable; the fixture forms unchanged |
| No mailbox client, mail host, mail API or mail program; none as a dependency (R7.5) | `tests/test_forbidden_capabilities.py::test_no_mailbox_client_is_imported_or_addressed_anywhere`, `::test_no_mail_or_capture_package_is_a_dependency_or_installed_by_an_image`, `::test_the_mail_guard_catches_each_sample`, `::test_the_dependency_guard_reads_every_manifest_and_pytest_setting` | clean on the tree; every planted sample caught |
| No screenshot, video, trace, HAR or captured session where a page runs (R11.4) | `::test_no_screenshot_video_trace_har_or_captured_session_in_python`, `::test_no_capture_in_the_browser_runner`, `::test_the_capture_guard_catches_each_sample`, `::test_the_runner_guard_catches_each_sample`, `::test_the_infrastructure_guard_catches_each_sample`, `::test_the_guards_leave_prose_and_ordinary_code_alone`, `::test_the_scanned_tree_is_the_repository` | clean on the tree; every planted sample caught, prose and ordinary code left alone |

## Outcome integrity and funnel (S2, 2026-10-27; local only)

Synthetic applications and the local receiver; its ledger is the oracle for what the employer
accepted. Decision D53; rules in `docs/architecture.md` ("Application state machine", "Refusal
codes").

| Requirement | Evidence | Result |
|---|---|---|
| A user's confirmation needs what they checked and is never a receipt | `tests/test_applications.py::test_a_user_confirmation_needs_stated_evidence`, `::test_a_user_confirmation_is_recorded_as_user_claimed_never_as_a_receipt`, `::test_the_service_refuses_a_user_confirmation_without_evidence`, `::test_only_a_receipt_or_the_users_statement_enters_submitted_confirmed` | before: confirmed with no evidence (200), indistinguishable from a receipt |
| Reconcile evidence is kept apart and never a 500 | `tests/test_applications.py::test_reconcile_evidence_is_kept_apart_from_the_reason_and_never_a_500` | before: 2,000 characters returned 500, 20 spaces were accepted |
| An outcome needs a known submission; Withdrawn always allowed | `::test_an_outcome_before_any_submission_is_refused_with_a_reason_code`, `::test_an_application_closed_before_submission_takes_no_employer_outcome`, `::test_outcome_choices_follow_the_submission_rule`, `tests/test_funnel.py::test_form_rejected_is_not_employer_declined` | before: any outcome on a draft (200) |
| Outcomes are dated, sourced and audited without free text | `::test_assessment_received_is_recordable_with_the_date_and_note_the_user_gives`, `::test_an_outcome_date_and_note_need_an_outcome_and_no_future_date`, `::test_restating_an_outcome_with_a_date_adds_an_event_and_repeating_it_adds_none`, `tests/test_audit_privacy.py::test_an_outcome_is_audited_with_its_value_and_source_only` | before: no date, source, assessment value or audit row |
| Owner switches need no migration | `::test_the_owner_can_switch_the_refusal_to_a_flag_without_a_migration`, `::test_the_owner_can_route_confirmations_through_reconcile_only` | both switch at call time |
| Refusal codes are a fixed, documented set | `::test_outcome_refusal_codes_are_fixed_identifiers_documented_once` | every `Refused(...)` names a literal code; disjoint from route and rehearsal codes |
| Events are insert-only and their provenance is checked in the database | `tests/test_application_events_db.py::test_application_events_are_insert_only_and_their_provenance_is_checked`, `tests/test_migrations.py::test_s2_adds_assessment_received_and_outcome_fields_without_rewriting_a_row`, `::test_disposable_downgrade_and_reupgrade` | UPDATE and a direct DELETE refused; a cascade still deletes; rows written before S2 untouched |
| The funnel counts the user's own applications, from the ledger's point of view | `tests/test_funnel.py::test_a_receipt_confirmed_submission_counts_once_and_matches_the_ledger`, `::test_an_unknown_outcome_is_unconfirmed_until_confirmed_and_a_receipt_outranks_a_claim`, `::test_a_receipt_recorded_while_quarantined_counts_as_a_receipt`, `::test_applied_by_hand_is_user_claimed_and_never_a_receipt` | submitted total equals the ledger's accepted count in each case |
| Funnel rules (pure) | `::test_reached_stages_count_what_was_recorded_and_never_infer_one`, `::test_a_change_to_none_takes_back_only_the_value_it_replaced`, `::test_no_response_yet_is_computed_from_the_current_submission_and_never_stored`, `::test_fewer_than_twenty_submissions_are_too_few_to_compare`, `::test_sources_follow_receipts_and_who_made_the_move` | no rate in the response |
| Per user; reading writes nothing; route order | `::test_outcome_history_and_the_funnel_are_per_user`, `::test_reading_the_funnel_writes_nothing`, `::test_the_funnel_route_is_matched_before_an_application_id` | before: `/applications/funnel` was taken as an application id (422) |
| Races with the worker's receipt (D46) | `tests/test_outcome_races.py` (3 tests; a barrier and lock waiters, no sleeps; the real worker against the receiver in two of them) | before: the PATCH lost the row version (500) |
| The tracker shows what each submission rests on | `frontend/e2e/phase-a.spec.ts`, `submission.spec.ts`, `tracker-outcomes.spec.ts` (desktop and mobile) | exact labels; ledger at 1 accepted where a submission ran |

## Preparation: bank scope (C6, 2026-10-27; local only)

Synthetic facts and wordings; fictional employers. Decision D51; rules in
`docs/answer-policy.md` row 5.

| Requirement | Evidence | Result |
|---|---|---|
| Answers that depend on the employer, the job or the date are never reused | `tests/test_bank_scope.py::test_bank_scope_table` (1,037 rows), `test_no_c6_row_is_ever_answered_from_the_bank`, `tests/test_bank_scope_api.py::test_answers_that_depend_on_the_employer_the_job_or_the_date_are_never_saved` | before: "this company", "previously worked for", "relevant experience", start date, availability, notice, relocation and salary resolved from a saved answer (reproduced against the previous commit). Now never bankable; saving returns 400 with the reason and stores nothing |
| A saved answer is bound to its help text | `test_question_key_*`, `test_a_saved_answer_needs_the_same_help_text`, `test_from_bank_checks_the_stored_help_text`, `test_a_saved_answer_is_reused_only_for_the_same_help_text` | before: reused for other help text or none. Now only for the same normalized help text |
| Saved answers from before C6 are kept, not re-keyed | `test_an_entry_saved_before_c6_answers_only_a_question_without_help_text`, `test_saved_answers_from_before_c6_are_kept_and_answer_only_a_question_without_help_text`, `tests/test_migrations.py::test_c6_saved_answers_keep_their_key_and_gain_no_help_text` | same id, key, value and version; answer only questions without help text; out-of-scope ones listed as "Not reused" |
| Follow-ups, repeated wording, sections | `test_a_follow_up_of_a_question_that_is_not_reused_is_not_reused`, `test_the_same_wording_twice_on_one_form_is_never_answered_from_the_bank`, `test_a_follow_up_or_a_repeated_question_is_never_saved` | never reused, 400 on save |
| Concurrent saves and deletes never fail | `tests/test_bank_races.py` (5 tests, 6 cases; deterministic: a barrier and lock waiters, no sleeps) | run against the previous code: two IntegrityError 23505 (a 500), a lost version increment, StaleDataError, a second delete not refused. Now serialized; the second delete is 404 |
| Only narrowing | `test_positive_controls_behave_exactly_as_before_c3_c5` with `C6_DELTA` (9 controls), `test_each_c6_delta_only_narrows`, the property tests | verified on the working tree against `7669c61` with scratch scripts: 1,315,200 form resolutions, 0 violations |
| Review findings fixed (D51) | `tests/test_bank_scope_api.py::test_saving_and_listing_never_fail_on_unusual_text`, `::test_a_follow_up_in_a_package_built_before_c6_checks_its_parent_again`, 62 more table rows in `tests/bank_scope_wordings.json`, the `E_APPLY` family in `test_every_family_use_is_load_bearing` | a NUL in help text or an answer, a long stored option and NaN no longer return 500; a frozen package's follow-up checks its parent; the missed wordings are refused; 20 deliberate breaks, each caught |
| The stable reuse question reaches the employer | `tests/test_execution_validation.py` (`answer_bank_delete`, receiver mode `bank_question`), `frontend/e2e/phase-b.spec.ts` | a saved education answer is reused for a second application, and deleting it after approval stops the running attempt (receiver ledger); the review page offers the reuse box on the education question and not on "How did you hear about this job?" or Gender, and the Saved answers page shows the help text |

## Preparation: statements, legal facts and sensitive topics (C3-C5, 2026-10-26; local only)

Synthetic facts and wordings; pure resolver tests run the package loop
(`package.resolve_answers`); API tests use fictional manual forms. Decision D49; rules in
`docs/answer-policy.md`.

| Requirement | Evidence | Result |
|---|---|---|
| A statement of a profile fact is checked only with agree and a true approved fact | `tests/test_question_safety.py::test_question_safety_table` (c3 rows), `tests/test_question_safety_api.py::test_a_fact_statement_is_checked_only_while_the_approved_fact_makes_it_true` | before: "I am legally authorized to work in the United States" checked from agree alone for an applicant not authorized (reproduced against the previous commit). Now checked only when the approved fact holds, with the fact recorded; not authorized, unknown, not applicable or not approved: a checkpoint; editing the fact after approval gives a new version, invalidates the approval and unchecks it (before, the approval survived) |
| Statements NoEfforts cannot check are never checked | table rows c3.neg, c3.compound, c3.anyemployer, c3.res.newmexico, c3.please_confirm, c3.help_condition, c3.veteran and others | negated, compound, qualified, regional, help-text-qualified and sensitive statements: a checkpoint agree cannot clear; declining an optional one leaves a box unchecked and a choice blank, never "No" (`test_a_declined_optional_statement_choice_is_left_blank_never_no`) |
| Eligibility misreads become checkpoints | table rows `c4.*` (eligibility, legal status, residence context) | before: a work-permit question answered inverted from the authorization fact, "New Mexico" from Mexico's fact, "for any employer" yes for an employer-tied visa, a saved citizenship answer reused (each reproduced against the previous commit). Now each is a question the user answers for this application, never from the profile or the bank |
| Sensitive topics, by wording, help text, options, section and parent | table rows `c5.*` (topics, EEO structure, help text, follow-ups); `test_a_follow_up_of_a_sensitive_question_needs_its_own_consent`, `test_a_health_question_is_never_drafted` | criminal history, health, accommodations, age variants, salary history, IDs, family, military, political, caste, minority identity: sensitive, never saved, reused or drafted; a follow-up of a sensitive answer needs its own consent |
| Nothing new is saved for reuse; old saved answers are kept, unused | `test_sensitive_and_legal_answers_are_never_saved_for_reuse`, `test_answers_saved_before_c3_c5_are_kept_but_no_longer_used` | saving citizenship, criminal, current-salary, references, generic, work-permit and statement answers: 400, nothing stored; ordinary and legacy EEO answers save as before (C8 decides the EEO policy); entries saved earlier stay listed and answer nothing, for anyone |
| What the adversarial review found | table rows `rv.*`; `tests/test_classify_vocabulary.py::test_each_pattern_added_after_review_matches_what_it_is_for`, `test_a_heading_that_adds_to_its_help_statement`, `test_a_country_whose_name_looks_like_a_region_is_still_a_country`; `test_a_citizenship_statement_is_placed_in_one_country_or_none`, `test_a_dual_citizenship_statement_is_never_checked` | each reported wording probed against the previous commit and the change: a sensitive-and-citizenship checkbox resolved from agree (a regression, fixed); the rest were gaps the change did not close (statements in other words, unplaced citizenship, headings, a declined optional statement answering "No", help text after "Answer for …", other times and held sponsorship, Country fields about work authorization or the job, regions, examples and organisations). Each is now a checkpoint, blank, or checked only on a true fact |
| Only narrowing | `test_positive_controls_behave_exactly_as_before_c3_c5` (46 rows pinned to the previous resolver), `test_no_c3_c5_row_is_ever_answered_from_the_profile_or_the_bank` (9 profiles × 5 consents × 3 bank states), `tests/test_classify_vocabulary.py` (94) | controls identical in every attribute; no other row is ever answered from the profile or the bank or made reusable. Verified once against the previous commit with scratchpad scripts (not in the repository): 117 fixture forms and test wordings, 52,800 rows identical except wrong-kind stored consents; 452,520 resolutions with no new automatic answer and nothing newly reusable or draftable; fixture package hashes 40/40 unchanged |

## Preparation: guards, and only resolved answers sent (C1, C2, 2026-10-23; local only)

Synthetic candidate and fixture forms; execution against the local receiver, whose ledger is
the oracle for what was sent. Decision D48.

| Requirement | Evidence | Result |
|---|---|---|
| An answer that is not resolved is never sent | `tests/test_sending.py::test_a_stale_accepted_draft_is_a_checkpoint_even_when_optional` | before the fix: an optional accepted draft whose fact changed became "blank" but kept its text, the package was approved (200) and the ledger showed the stale text sent, reproduced. Now the question is a checkpoint (`needs_user`, approval 409); the user's own replacement is approved and is what the ledger shows |
| The package builder keeps no value on a blank row | `test_the_builder_clears_a_blank_row_whatever_the_resolver_returns`, `test_every_fixture_package_sends_only_resolved_answers` (7 packages), and the invariant checked in each package test of the file | with a resolver forced to return values on blank rows, none reaches the package; over the fixture, receiver and Greenhouse-fixture packages, a blank row has no value or display, a row with a value is resolved or blocks approval, documents are exactly the resolved document rows |
| A document question that is not asked | `test_a_document_question_that_is_not_asked_attaches_nothing`, `test_a_document_question_that_depends_on_a_missing_question_attaches_nothing` (2) | before the fix: HTTP 500 (TypeError) for the package view and every answer saved, reproduced. Now no document is attached until the question applies; a required one depending on a missing question is a checkpoint |
| The worker refuses a stored package that is not the approved one, before any adapter code | `test_the_runner_refuses_before_anything_is_sent` (8: four adapters; a resolved answer changed in the stored package without its hash; a value on a row that is not resolved with every hash made to agree) | `failed_safe`, no disclosure started; the ledger has no request at all after preparation. Found on the way: nothing compared the stored package with its approval before; with this check removed, the changed resolved answer is sent and confirmed (the gates rebuild the package from current data, which still matches) |
| Each adapter fills only resolved answers (runner check bypassed) | `test_each_adapter_fills_only_resolved_answers` (4), `test_the_adapter_view_drops_only_what_is_not_resolved`, `test_nothing_else_reads_answer_values_for_sending` | with the runner's check bypassed and the stored package changed without its hash (the gates, rebuilding from current data, pass), each adapter confirms and the injected text appears nowhere in the ledger |
| The package shape is pinned to `SCHEMA_VERSION` | `tests/test_package_contract.py` (3) | 96 key paths over six synthetic packages (every fact-reference type, answer value shape, condition and unsupported control) equal the shape recorded for version 2; the hash ignores only fact-reference version counters |
| Cross-tenant routes C1 found untested | `tests/test_preparation.py::test_tenant_isolation_for_revoke_documents_drafts_and_the_bank` | revoke, document selection (with the other user's or the owner's document), draft acceptance (the other user's application or the owner's other application), the document list and versions: 404 or nothing of the owner's; the owner's approval stays live; another user never resolves a question from the owner's saved answer |
| No candidate document, secret or captured session is committed | `tests/test_repo_hygiene.py` (3) | over what a commit would contain (`git ls-files`, tracked plus untracked files that are not ignored): no document, spreadsheet, environment file (other than `.env.example`), key, browser capture (traces, `.auth/`, storage state, cookies) or database file; every email address, in any file whatever its encoding, on a reserved domain, or the owner's own no-reply address. The review found the first version would have failed on its own sample address once committed (it scanned only tracked files); the sample is now built at run time and untracked files are scanned too |

## Provider admission (I2, 2026-10-22; local only, no external request)

Computed from code tables and recorded evidence (`providers/admission.py`,
`docs/provider-admission.md`); a synthetic example provider ("exampleats", `.invalid` hosts)
built into copies of the tables, never registered. Execution scenarios use the local receiver;
its ledger is the oracle.

| Requirement | Evidence | Result |
|---|---|---|
| Every provider's admission is computed, and no claim exceeds it | `tests/test_provider_admission.py`: `test_each_registered_provider_gets_its_computed_admission` (10), `test_every_registered_provider_is_admitted_to_what_it_claims` | all ten within their claims; `greenhouse_dom` and `greenhouse_readonly` at `observed_read_only`, `greenhouse_hosted`, `fixture_ats`, `fake_api` and the two discovery providers at `fixture_only`, `lever` and `workday` at `planned`, `manual_handoff` at `registered`; none `rehearsal_ready` |
| Every requirement has checks; every check is reachable and breakable | `test_every_requirement_has_a_check`, `test_every_check_is_met_on_the_complete_example` (37), `test_every_check_is_caught_by_its_sabotage` (37), `test_the_example_reaches_each_stage_only_when_its_requirements_are_met` (6), `test_a_key_is_safe_only_when_named_after_its_ats_or_kind` (10), `test_text_naming_an_identifier_is_caught` (8), `test_text_naming_no_identifier_passes` (7) | each check met on the complete example and broken by one change that stops it before its stage, breaking exactly that check and its declared dependencies (8 checks have one or two); each stage from `registered` to `rehearsal_ready` reached exactly |
| Owner boundaries and the cap | `test_nothing_passes_the_real_destination_cap`, `test_an_owner_boundary_is_never_passed_without_its_record` (4) | even with every check met the example stops at `rehearsal_ready` (`real_destinations_refused`); with the cap lifted in the test only, the doc review, the read-only runs, permission C and permission D (each its own record) still stop it without their record |
| Waivers keep pre-I2 claims, never advance them | `test_a_waiver_never_advances_a_provider_beyond_its_claim`, `test_waivers_are_frozen_to_the_pre_admission_providers_and_still_real`, `test_a_waiver_for_a_new_provider_has_no_effect`, `test_raising_a_claim_never_raises_a_waiver`, `test_a_new_adapter_under_a_pre_admission_key_inherits_no_waiver`, `test_the_by_ats_view_shows_what_is_held_only_by_a_waiver` | `greenhouse_dom` with every rehearsal condition met in memory still stops at its claim on its waived doc review; three waivers, each covering a check that fails without it, each capped at the claim frozen at I2; `greenhouse_hosted` raised in memory to observed with credited runs stays at `fixture_only` (caught); the by-ATS view shows Greenhouse's waived doc review |
| Recorded runs credit only when single-use and completed | `test_every_observed_cell_is_credited_by_a_completed_single_use_run`, `test_a_run_without_its_own_approval_or_not_completed_credits_nothing`, `test_the_recorded_runs_are_the_documented_runs`, `test_a_structure_only_observation_never_meets_a_rehearsal_condition`, `test_manual_evidence_that_would_change_a_condition_is_caught` | every observed cell, and the Greenhouse providers' "no" traits, credited by runs #4, #6, #8 or #9 (the generic fixture adapters' "no" traits are their fixtures' design); #1-#3 and #7 credit nothing, #5 records nothing to credit; the dropdowns are structure only, so the rehearsal condition stays unmet even if readiness counted the level; Path A recorded with any answers changes no readiness condition (computed) |
| Admission is pure and advisory | `test_admission_reads_no_database_and_no_repository_file`, `test_admission_imports_no_browser_code`, `test_computing_admission_changes_nothing`, `test_nothing_routes_labels_or_approves_on_admission`, `test_served_admission_carries_only_fixed_identifiers`, `test_the_api_serves_admission` | same result with file reads and the database refused; no browser module loaded (subprocess); registry, readiness, versions and support states unchanged, no audit row; only the providers API imports it; served strings are fixed identifiers only; 401 without a session |
| The tables are the code, the tests and the docs | `tests/test_provider_contracts.py` (39); `tests/test_provider_admission.py::test_the_documented_admission_tables_are_the_code` | identity contract for all six ATS names (positive, variants, tracking parameters dropped from the canonical URL, vendor site, non-posting, lookalike, fixture origin, foreign form, bounded parts); five known gaps each still reproduced (a gap with several behaviours while any of them does); fixture paths exist; policy, runner, rehearsal, discovery and observer tables equal the registry's; receipt keys pinned per adapter; every route's metadata survives the sanitizer; the documented capability matrix and support states equal the registry, and the admission doc's tables the code |
| Fixture scenarios | `test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap` | 32 required scenarios, each a ledger test; five were missing and were added: `tests/test_execution_failures.py::test_reconciling_an_unknown_outcome_never_sends_again` (three browser adapters, both findings), `tests/test_greenhouse_adapter.py::test_page_altering_a_filled_value_stops_before_submit`, and the API upload-failure case now reads the ledger |
| An approval sends once (D15) | `test_reconciling_an_unknown_outcome_never_sends_again` (6), `tests/test_execution_security.py::test_a_submission_whose_code_was_never_entered_never_sends_again_on_its_approval`, `test_a_late_receipt_after_a_not_received_reconciliation_still_counts_and_nothing_resends`, `test_not_received_is_refused_once_the_employers_receipt_was_recorded`, `test_an_application_with_a_recorded_receipt_is_never_queued_again` (simulated state) | before the fix: after a "not received" reconciliation, queueing again sent the application a second time with the old approval (ledger: 2 accepted), reproduced; an abandoned code step left its approval live after the final click. Now each retires the approval (`reconciled_not_received`, `verification_not_completed`) and queueing is refused (409) with the ledger unchanged; a late receipt confirms the application (it was lost before); "not received" is refused once a receipt is recorded; a recorded confirmation is never queued again |
| A manual-handoff approval never runs through an adapter (D28) | `tests/test_approval_binding.py::test_an_approval_given_for_a_manual_handoff_never_runs_through_an_adapter`, `tests/test_rehearsal_prerequisite.py::test_an_approval_given_for_a_manual_handoff_is_shown_against_the_route_that_would_run` | before the fix: recorded with no adapter, it read as a pre-binding approval and was queued (200) once the route became an adapter's. Now it records `manual_handoff`, is retired at queueing (409) and nothing is disclosed; the review shows the prerequisite of the route that would run |
| An unlisted form source is refused | `test_an_unknown_form_source_is_refused_not_given_to_the_fixture_adapter`; `tests/test_reason_codes.py::test_no_destination_falls_through_to_the_fallback` | `no_adapter`, a manual handoff, never the generic fixture adapter; the known sources route as before |
| Over-long identities and cells | `test_an_over_long_identity_is_never_a_server_error`, `test_identity_parts_are_bounded` (6), `tests/test_jobs.py::test_an_over_long_cell_is_that_rows_error_never_a_server_error` | before: HTTP 500 (DataError) for an over-long company or posting id, and for an import with an over-long cell; now 201 and recognised again (200), a URL that canonicalizes past its column is a 400, and an over-long cell is its row's error |
| Spec invariants | `tests/test_providers.py`: `test_every_spec_error_branch_has_a_case`, `test_registry_problems_reject_inconsistent_entries` (7), `test_a_side_table_naming_an_unregistered_provider_is_refused` | 20 `raise SpecError` branches, each with its own negative case (6 had none before I2); every cross-provider problem refused at import |

## Lock order and race guarantees (E6 follow-up, 2026-10-22; local only)

Two real PostgreSQL transactions on separate connections per test, synchronized by barriers
at exact lock points and by the waiting side's lock wait read from `pg_stat_activity` (no
timing sleeps); every side must finish within 30 seconds. Synthetic data, the local receiver.

| Requirement | Evidence (`tests/test_lock_order.py`) | Result |
|---|---|---|
| A cancel racing a gate never deadlocks | `test_a_cancel_arriving_while_the_disclosure_gate_holds_its_locks_waits_for_it`, `test_a_cancel_arriving_while_the_send_gate_holds_its_locks_is_refused_after_it` | before the fix: deadlock (40P01), reproduced first. Now the cancel waits: after the disclosure gate it cancels (the worker's next fenced step is refused; nothing reached the receiver here); after the send gate it is refused ("in flight"), the outcome is the worker's (`unknown`, quarantined), never retried |
| A cancel committed before a gate stops it | `test_a_cancel_committed_before_a_gate_checks_stops_that_gate` (disclosure, send) | the gate, waiting for the attempt, finds it cancelled: lost authority (before the fix: a raw serialization error); attempt and application `cancelled`, nothing authorized |
| Worker writes and cancel | `test_a_cancel_racing_the_worker_writing_an_outcome_waits_for_it`, `test_a_cancel_racing_the_worker_recording_evidence_waits_for_it`, `test_a_cancel_arriving_while_a_worker_claims_the_attempt_waits_for_the_claim`, `test_a_duplicate_delivery_while_a_gate_holds_the_attempt_is_ignored_without_waiting` | before the fix the outcome and evidence races deadlocked (the evidence one through the foreign key's key-share lock on the application); now each waits and the worker's write stands. A claim racing a cancel waits for it (the claim locks the attempt first too). A duplicate delivery does not even wait: it is ignored, the first worker keeps its authority (the reported duplicate-claim risk does not exist: the claim matches only a pending attempt) |
| Cancel and a new attempt being queued | `test_a_cancel_waiting_for_a_queueing_transaction_takes_its_new_attempt_too`, `test_a_cancel_never_waits_for_an_attempt_it_finds_after_the_application_lock` | the cancel takes the attempt queued while it waited (before the fix: a stale application copy, `StaleDataError`); if a claim holds that attempt, the cancel is refused ("Try again") instead of deadlocking, the claim proceeds, and a second cancel holds |
| Withdrawal and deletion racing the send gate | `test_a_withdrawal_arriving_while_the_send_gate_relies_on_the_rehearsal_waits`, `test_a_withdrawal_committed_while_the_send_gate_waits_for_the_record_stops_it`, `test_an_evidence_deletion_arriving_while_the_send_gate_relies_on_its_receipt_waits`, `test_an_evidence_deletion_committed_while_the_send_gate_waits_for_the_receipt_stops_it` | arriving while the gate holds the record or receipt: they wait, the gate authorizes the send (`met` / `established`), and the withdrawal or deletion then applies to later submissions only. Committed first: the gate sees it and refuses (`rehearsal_revoked`), nothing is sent (receiver: no new acceptance) |
| A gate checks what is committed, after its locks | `test_an_edit_committed_while_a_gate_waits_stops_that_gate` (answer or profile; disclosure or send gate), `test_a_note_saved_while_a_gate_waits_does_not_stop_it`, `test_a_write_to_the_approval_waits_for_a_gate_that_holds_it` | before the fix (REPEATABLE READ snapshot at the first statement), all four edit cases passed the gate with the content as approved, and a note made it refuse; reproduced first. Now an answer or profile change committed while the gate waits is seen ("changed after approval"), nothing authorized; a note is no reason to refuse; a direct approval write waits for the gate holding the approval row |
| Queueing again with an earlier attempt still pending | `test_queueing_again_stops_an_earlier_attempt_that_can_no_longer_run`, `test_queueing_again_while_the_earlier_attempt_is_being_claimed_never_deadlocks` | before: an uncaught duplicate (HTTP 500). Now the earlier attempt (pending under a stale approval, nothing disclosed) is stopped and the new one queued; while a worker is taking it, queueing is refused ("Try again") instead of waiting, and the claim then stops the earlier attempt; nothing reached the receiver |
| Clearing and saving one input | `test_clearing_an_input_while_it_is_being_saved_serializes_instead_of_deadlocking` (consent, answer) | held the moment its delete is flushed: the clear already holds the application, the save waits, and its value remains. Deleting first (or taking the application only after the delete) deadlocked |
| The rehearsal stop and the sweeper | `test_a_cancel_racing_the_rehearsal_stop_waits_for_it`, `test_a_cancel_racing_the_sweeper_waits_for_it` | the cancel waits; the stop ends `rehearsed`, the sweeper re-pends, and the cancel then cancels; with cancel in the old order both deadlocked (40P01) |
| Sabotage | applied one at a time, each reverted | 17, each caught: cancel in the old order against the rehearsal stop and the sweeper, the clear taking the application only after its delete, a gate skipping a locked attempt instead of waiting; and: cancel in the old order (against a gate, against evidence recording), claim locking the application first, cancel waiting at its re-check, no re-check, no refresh, clearing an answer or a consent before the application lock, the gates reading a REPEATABLE READ snapshot again, no stop of the earlier attempt (against a plain re-queue, against a claim), queueing waiting for the earlier attempt (caught as a bounded 30-second hang), the gates not locking the approval row. The E6 record and receipt lock checks, re-run against the gates' new reads, are caught by the tests in which a withdrawal or deletion must wait |

## Rehearsal prerequisite (E6, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only; the rule is put on fictional `e6-` fixture forms
by the test-only setting (`env == "test"`). Real destinations are refused before it. The
receiver's ledger is the oracle for what reached the synthetic employer. Rows edited by hand
are labelled simulated in the tests.

| Requirement | Evidence (`tests/test_rehearsal_prerequisite.py` unless noted) | Result |
|---|---|---|
| A fixture path without the rule needs nothing | `test_a_fixture_path_without_the_marker_needs_no_rehearsal` | review `not_required`; confirmed; the send gate records `not_required`; ledger 1 accepted, 1 upload |
| The first submission on a path needs a recorded rehearsal | `test_the_first_submission_on_a_path_needs_a_recorded_rehearsal` | review `unmet` / `no_rehearsal` with its fixed message; approve 409 "(reason: no_rehearsal)", no approval row; queueing refused; nothing posted to the receiver |
| A rehearsal is never permission to submit | `test_a_valid_rehearsal_then_a_separate_approval_to_submit` | after the rehearsal: `met`, but queueing without a new approval is 409; the approval to submit names the rehearsal; confirmed, send gate records `met`; ledger 1 accepted, 2 uploads; every attempt labelled `fixture` |
| An established path, and what ends it | `test_a_confirmed_submission_establishes_its_path`, `test_a_submission_made_while_the_rule_did_not_apply_establishes_nothing`, `test_an_established_path_needs_a_new_rehearsal_after_an_adapter_version_change`, `test_a_newer_failed_rehearsal_outvotes_an_established_path` | a confirmed submission after a rehearsal establishes the path (a withdrawal of the older rehearsal changes nothing); the next submission records `established`; once every establishing receipt is deleted, the withdrawn rehearsal decides: `rehearsal_revoked`. A submission made while the rule did not apply establishes nothing; another class (simulated) or an adapter version change ends it; a newer failed rehearsal outvotes it |
| The newest result decides, by when it finished | `test_a_later_failed_rehearsal_supersedes_an_earlier_success`, `test_the_rehearsal_that_finished_last_decides_whatever_the_queue_order`, `test_an_in_progress_rehearsal_never_displaces_a_finished_one` | a newer failure: `rehearsal_failed` (approve 409); a rehearsal queued first and failing last decides; a waiting rehearsal leaves the finished one deciding; only a waiting one: `rehearsal_in_progress` |
| A path is user, provider, origin and board | `test_one_rehearsal_serves_another_posting_on_the_same_path`, `test_a_rehearsal_on_another_board_does_not_count`, `test_a_rehearsal_never_counts_for_another_user`, `test_the_user_filter_holds_even_if_path_references_collided`, `test_the_path_is_user_provider_origin_and_board`, `test_an_attempt_and_its_record_keep_the_path_only_as_a_keyed_reference` | another posting on the board: `met`; another board or user: `no_rehearsal`; another user's withdraw or attempts: 404; the same stored reference asked by another user finds nothing; the reference changes with each component, never contains the board or host, and is never served |
| Each layer refuses alone | `test_each_layer_refuses_with_the_others_bypassed` (approve, enqueue, claim, disclosure, send, none), `test_turning_the_rule_on_after_queueing_is_caught_by_the_worker`, `test_a_claim_refused_after_a_sweeper_repend_leaves_nothing_running` | approve: 409, no approval; enqueue: 409, no attempt or outbox row; claim: `failed_safe`, `claim_refused_rehearsal`, no request at the receiver; disclosure: `failed_safe`, nothing uploaded; send: `abandoned`, 1 upload, 0 accepted, never re-pended; none bypassed: confirmed. A re-claim after a re-pend leaves the application `needs_user_action`, not `running` |
| A withdrawal or deletion racing a gate | `test_withdrawing_the_relied_on_rehearsal_while_the_send_gate_waits`, `test_a_withdrawal_after_the_gate_snapshot_is_refused_not_missed`, `test_deleting_an_establishing_receipt_after_the_gate_snapshot_is_refused` | a worker held before the send gate: `abandoned` with `rehearsal_revoked`, 0 accepted; a withdrawal or receipt deletion committed after the gate took the attempt and before it read (second session): the gate sees it and refuses with `rehearsal_revoked` |
| Fail-closed | `test_a_stale_window_outside_its_bounds_fails_closed`, `test_an_error_while_checking_is_a_refusal_and_leaves_the_session_usable`, `test_a_rehearsal_with_no_record_cannot_be_withdrawn_or_counted`, `test_a_fixture_rehearsal_never_satisfies_a_real_path` | an invalid window: `rehearsal_check_unavailable`; 31 days (simulated): `rehearsal_stale`; a statement the database refuses: `rehearsal_check_unavailable`, the session still usable, approve 409; no record: `rehearsal_evidence_missing`, not withdrawable (404); a fixture record for a real-class check: `rehearsal_mismatched` |
| Real destinations are still refused first; the setting only adds the rule | `test_a_real_destination_is_still_refused_first`, `test_the_marker_only_adds_the_rule_and_only_in_tests` | with the rule on every path: `not_applicable` / `real_destination_disabled` before and after approving; queueing 409 with the manual-handoff message, no attempt. The setting is ignored outside `env == "test"`, never removes the rule, and leaves routing, the adapter and the class unchanged |
| Every code is produced by its own path | `tests/test_rehearsal_codes.py` (17) | each of the 12 codes produced by its own cause; fixed identifiers, safe for audit, apart from the routing codes; messages name no destination; the documented codes, messages and statuses equal the code |
| Readiness counts a real submission only after a held prerequisite | `tests/test_pilot_readiness.py`: `test_a_real_submission_counts_only_after_its_prerequisite_held` | simulated rows: a real-class confirmation counts only once its send gate recorded the prerequisite held; still 0 of 7 met |
| The UI shows the requirement with its code | `frontend/e2e/rehearsal-prerequisite.spec.ts` (desktop, mobile); `frontend/e2e/submission.spec.ts` | `no_rehearsal` shown, approve to submit disabled, the server's 409 with the same code; rehearse: allowed; withdraw (two steps): `rehearsal_revoked` on the row and the attempt; rehearse again, approve, submit: 1 accepted, 3 uploads; an unmarked form shows no code and labels its attempt as fixture evidence |
| Sabotage | applied one at a time, each reverted | 28 checks, each caught (one, an exception read as met, was missed at first; a test was added): each layer removed (5), the rule applied to rehearsals, no user filter, any success instead of the newest, a waiting rehearsal displacing a finished one, no board in the path, no class comparison, no approval binding, no record lock, no receipt lock, the marker outside tests, establishing without a receipt, with any confirmed submission, or ignoring the adapter version, the send gate not recording the prerequisite, readiness without it, an exception as met, no savepoint, no age check, no evidence re-read, queue-time order, an approved manual handoff read through its legacy binding, a refused re-claim left running, withdrawal offered without a record |

## Rehearsal stop, rehearsal records and readiness evidence (E5 step 3, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only. The receiver's ledger is the oracle for what
reached the synthetic employer.

| Requirement | Evidence (`tests/test_rehearsal_stop.py` unless noted) | Result |
|---|---|---|
| A rehearsal records what it proved, at its stop | `test_a_rehearsal_records_what_it_proved_at_its_stop` (browser, API) | one record: class `fixture`, route, adapter and current version, 1 of 1 uploads acknowledged, readback 0 mismatched (API: none), recheck matched, nothing unresolved; it holds; one `package.approval_retired`; ledger 1 upload, 0 accepted |
| The stop repeats the gate | `test_a_revocation_at_the_stop_ends_abandoned_not_rehearsed`, `test_a_change_to_the_profile_at_the_stop_ends_abandoned`, `test_a_cancel_at_the_stop_is_not_a_rehearsal`, `test_a_lost_lease_at_the_stop_is_not_a_rehearsal`, `test_a_revocation_committed_while_the_stop_waits_is_refused` | a worker held at the stop: revoked, edited, cancelled or swept, the attempt ends `abandoned` or `cancelled`, never `rehearsed`, with no record; a revoked approval is shown as revoked and no retirement is recorded for it |
| The stop checks the evidence | `test_the_stop_ends_rehearsed_only_with_complete_evidence`, `test_the_stop_refuses_incomplete_or_contradicting_evidence` (5), `test_the_stop_refuses_an_upload_not_acknowledged` (2), `test_the_stop_refuses_a_document_that_was_not_approved`, `test_the_api_route_reads_the_form_again_before_its_stop` | missing recheck, readback or upload: `rehearsal_evidence_missing`; a readback mismatch, a changed form, an unacknowledged upload or an unapproved document: `rehearsal_evidence_inconsistent`; the code is kept on the outcome event. Requests the egress proxy denied are counted in the record, not disqualifying |
| A record holds only while it is true | `test_a_record_holds_only_while_its_evidence_and_attributes_do`, `test_deleting_an_applications_evidence_revokes_its_rehearsals` | another adapter version or class: mismatched; past 30 days: stale; an invalid window: check unavailable; an edited readback: inconsistent; an expired row: missing; a tampered class: mismatched; evidence deleted: revoked (another user: 404) |
| A destination keeps its class | `test_a_gate_refuses_a_destination_whose_class_changed`, `test_an_attempt_queued_before_classes_were_recorded_is_refused_plainly`, `test_only_a_configured_fixture_origin_outside_production_is_a_fixture` | recorded at queueing; a gate refuses a changed class, and an attempt with no recorded class (queued before this change) with its own plain message, before anything is disclosed; production and unknown origins are `real` |
| A checking error is a refusal | `test_a_failed_statement_while_checking_a_record_is_a_refusal_not_an_error` | a statement the database refuses: `rehearsal_check_unavailable`, and the caller's session stays usable (a savepoint) |
| No identifiers kept | `test_records_events_and_audit_hold_no_external_identifiers`, `test_the_ack_and_strength_vocabulary_matches_the_adapters` | the record, events and audit hold no URL, host, slug, field or name; the shared vocabulary equals the adapters' |
| Readiness counts recorded evidence by class, and nothing meets a real condition | `tests/test_pilot_readiness.py`: `test_recorded_evidence_meets_nothing_while_real_destinations_are_disabled`, `test_a_real_condition_needs_real_destinations_and_evidence_of_its_own_class`, `test_each_condition_is_met_only_by_its_own_evidence_class`, `test_the_documented_evidence_classes_are_the_code`, `test_readiness_reads_only_the_callers_own_records`, `test_the_api_serves_readiness` | every count high: 0 met; with real destinations patched on, fixture evidence meets nothing and each real condition needs its own class; one class per condition; the documented table is the code; the endpoint counts only the caller's records (another user: 0), and a record edited to claim a real destination counts as not holding |

## Gates and concurrent revocation (2026-10-22; local only; mechanism superseded by D46)

| Requirement | Evidence | Result |
|---|---|---|
| A revocation committed while a gate waits for the application lock stops that gate | `tests/test_gate_snapshot_race.py`, `test_a_revocation_committed_while_a_gate_waits_is_refused` (disclosure gate, send gate) | a second session revokes after the gate took the attempt and before its application lock; the gate refuses. At the time (D43, REPEATABLE READ) the refusal was "the approval changed while it was being checked", and removing the approval lock was caught. Since D46 the gate reads after its locks and refuses with "approval revoked, expired or superseded" whether or not the approval row is locked; the approval lock is now tested by `tests/test_lock_order.py::test_a_write_to_the_approval_waits_for_a_gate_that_holds_it` |

## Upload evidence and rehearsal results (E5 step 2, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only (the clinic form, both Greenhouse-style
approximations, the fake API). The receiver's ledger is the oracle for what the synthetic
employer kept.

| Requirement | Evidence (`tests/test_upload_evidence.py` unless noted) | Result |
|---|---|---|
| An upload is kept as its digest and a fixed acknowledgement | `test_an_upload_is_kept_as_its_digest_and_acknowledgement_never_the_pages_id` (3 forms) | `{field, ack: attachment_shown, sha256}`, the digest the receiver stored; the page's own attachment id appears nowhere in the evidence |
| A failed upload keeps the evidence of every upload before it | `test_a_failed_upload_keeps_the_evidence_of_every_upload_before_it` (2 Greenhouse-style forms, resume then cover letter, the cover letter refused) | `abandoned`; evidence: resume `attachment_shown`, cover letter `error_shown`; the receiver kept only the resume; 0 acceptances. Before, both were lost with the exception |
| A refused or unacknowledged upload is kept as such | `test_a_refused_upload_is_kept_as_refused`, `test_an_upload_the_page_never_acknowledges_is_kept_as_unacknowledged` | `error_shown`; `none` when the page hears back too late (the receiver did keep it); both `abandoned`, 0 acceptances |
| The API route keeps the same evidence | `test_the_api_route_keeps_the_same_evidence` (2) | the draft, then the upload with `digest_matched`, or `not_kept` when the API refuses it (`abandoned`) |
| A rehearsal's result is shown as such | `tests/test_rehearsal.py`; `frontend/e2e/submission.spec.ts` | the used approval is `used_by_rehearsal` (version, time), not an invalidation; a revocation is still `invalidated` with its reason; the tracker's `last_attempt` is `rehearsed`, then `confirmed` after an approval to submit; the review page and tracker show "Rehearsal finished: nothing submitted" |

## Rehearsal: disclosure without submission (E5 step 1, 2026-10-22; fixtures only)

Synthetic candidate and local fixtures only (the clinic form, the second Greenhouse-style
approximation, the fake API). The receiver's ledger is the oracle.

| Requirement | Evidence (`tests/test_rehearsal.py` unless noted) | Result |
|---|---|---|
| A rehearsal fills and checks, then stops before submitting | `test_a_rehearsal_fills_and_checks_then_stops_without_submitting`; `frontend/e2e/submission.spec.ts` (desktop and mobile) | attempt `rehearsed`; the ledger has one upload whose digest is the approved document's; 0 acceptances and no submit request; disclosure and readback evidence, no receipt; application `needs_user_action`. Removing the runner's stop is caught |
| The approval is used up | same test | the approval is retired ("Used by a rehearsal") in the same transaction; queueing again is refused (409); one `package.approval_retired` event with `rehearsal_completed`. Not retiring it is caught |
| Submitting afterwards needs its own approval and a new attempt | `test_after_a_rehearsal_an_approval_to_submit_submits_once`; the e2e test | after approving to submit: one acceptance, two uploads (each attempt repeats every check), attempts `confirmed` and `rehearsed` |
| The send gate refuses a rehearsal on its own | `test_the_send_gate_refuses_a_rehearsal_even_if_the_runner_did_not_stop`, `test_the_send_gate_itself_refuses_an_approval_to_fill_only` | with the runner's stop bypassed: `abandoned`, 0 acceptances, no send started. Removing the gate's refusal is caught: the attempt then ends `confirmed`. Removing both makes a rehearsal submit, which the first test catches |
| Every route rehearses the same way | `test_a_rehearsal_on_the_greenhouse_style_form`, `test_the_api_route_rehearses_too` | id-mapping adapter: one upload, 0 acceptances. API route: a draft and its upload, no submit call, 0 acceptances. Removing the API route's stop is caught |
| The scope is explicit and never switched silently | `test_the_scope_defaults_to_submit_is_validated_and_is_never_switched_silently` | no scope given: `submit` (existing flows unchanged); same scope again: the same approval; the other scope while approved: 409; an unknown scope: 422; another user: 404; `package.approve` records `scope`. Swapping the scope in silently, or not storing it, is caught |

## Lever as a planned provider (2026-10-22; local only, nothing read from Lever)

The Lever URLs in these tests are fictional (company "acme", a random posting id) and are
never requested.

| Requirement | Evidence (`tests/test_lever.py` unless noted) | Result |
|---|---|---|
| Identity from known hostnames only | `test_lever_postings_are_identified_from_their_hostname_and_path` (4), `test_anything_else_is_not_lever` (5) | posting, `/apply`, tracking query and EU host: `lever`, company and posting id; tracking parameters dropped. Vendor site, company page, non-UUID id, lookalike host and a query parameter: `unknown` |
| A specification only | `test_lever_is_a_specification_only` | planned; no operations or capabilities; every routing capability `none`; CAPTCHA `expected`; login, multi-step and verification `unknown` with "unverified" (never "no"); "Planned only: no automation exists". Claiming login "no", or not expecting a CAPTCHA, is caught |
| An honest route, never another ATS's adapter | `test_a_lever_job_is_shown_unsupported_and_never_routed_to_greenhouse`; `frontend/e2e/routing.spec.ts` | manual handoff, `planned_adapter_only`, "Lever applications are not supported yet"; a Greenhouse form source changes nothing; Greenhouse capture refused (400) with 0 requests; the job page shows it. Unlinking Lever from its ATS is caught |
| The documented vocabulary is the registry | `test_the_documented_routing_vocabulary_is_the_registry` | every column of the routing-vocabulary table, Lever's included, equals `routing_view`; a drifted cell is caught |
| A form-ATS mismatch still has a path | `tests/test_reason_codes.py`, `test_a_form_from_another_ats_is_refused` | shown with a fictional Ashby posting (no specification): `form_ats_mismatch` |

## Greenhouse: page controls the job data does not list (2026-10-22; local only, no external request)

Local fixture (`gh2_dd_extras`: a phone-country selector inside the phone group and a required
dropdown the job data does not list) only. No real page was read.

| Requirement | Evidence (`tests/test_dropdown_strategies.py`) | Result |
|---|---|---|
| A control the job data does not list is a checkpoint from capture | `test_unlisted_dropdowns_are_a_checkpoint_from_capture` | both captured as blocking fields with a fixed reason, never interpreted; route `checkpoint` (`unsupported_required_control`, "2 required controls"); both unresolved in the package; approval refused; 0 disclosures. Not capturing them, or capturing them as optional, is caught |
| One that appears after approval still stops before disclosure | `test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure` | captured and approved without them; the page then shows them: `failed_safe`, "2 new field(s)", counted, never named; 0 disclosures. Dropping the run-time check is caught |

## Greenhouse: Path A record and pilot readiness (2026-10-22; local only, no external request)

No page was visited and no manual observation was recorded: every answer in these tests is
synthetic and labelled so. Results are from the cloud sandbox.

| Requirement | Evidence | Result |
|---|---|---|
| The Path A record ships pending | `tests/test_path_a.py`: `test_the_shipped_record_is_pending` | `docs/evidence/path-a.json` is `{"status": "pending"}`; every assessment is `unknown`; a record filled in for the owner is caught |
| Only the checklist's fixed choices can be recorded | `test_anything_but_the_fixed_choices_is_refused_without_echoing_it` (9 cases), `test_the_questions_follow_the_checklist` | wording, an unknown question, extra fields, another source, a bad date, a third dropdown, no answers, a guessed status and a URL are refused; no refusal echoes the value; the questions follow the checklist's 8 (question 8 for two controls); accepting free text is caught |
| Answers are advisory | `test_a_record_is_assessed_but_never_changes_support`, `test_policy_limits_hold_whatever_the_answers` (6 cases) | a candidate strategy or a blocker per answer; the registry is unchanged; search-as-you-type and partial lists stay unsupported whatever the answers |
| Readiness is derived from evidence | `tests/test_pilot_readiness.py`: `test_no_condition_is_met_today`, `test_a_condition_follows_the_registry_alone` | 0 of 7 met, not proposable, Path A pending; raising one capability to `observed` in a patched registry meets exactly that condition |
| The owner's observation meets no condition | `test_the_owners_manual_observation_meets_no_condition` | even the most favourable answers meet 0 of 7; letting Path A meet one is caught |
| The documented status is the computed one | `test_the_documented_status_equals_the_computed_one` | the table in `docs/greenhouse-readiness-gap.md` equals the computation; a drifted row is caught |
| Served to signed-in users only | `test_the_api_serves_readiness` | `GET /api/providers/greenhouse_dom/readiness` equals the computation; 401 without a session (dropping authentication is caught) |

## Question keys out of URL paths (2026-10-22; local only, no external request)

Synthetic data and local fixtures only. Results are from the cloud sandbox (PostgreSQL 16,
Redis 7); the Compose execution test, which also calls these endpoints, runs in CI only.

| Requirement | Evidence (`tests/test_api_paths.py` unless noted) | Result |
|---|---|---|
| No path carries external text | `test_every_path_parameter_is_an_internal_id_or_one_of_our_own_names` (read from the OpenAPI schema) | every path parameter is a UUID except `name` (NoEfforts' own fixture-form and provider names) |
| The key-in-path routes are gone | `test_the_key_in_path_routes_are_gone` | for an existing application, `PUT`/`DELETE …/answers/{key}`, `PUT …/consents/{key}` and `POST …/answers/{key}/draft` are 404 |
| Answers, consents, clearing and drafts take the key in the body | `test_answers_consents_clearing_and_drafts_take_the_key_in_the_body` | an answer saved, then cleared (back to `needs_user`); a consent choice and a draft refused for a question that takes neither, without echoing the key; an unknown key 404 without echoing it; malformed keys 422 before the handler; another user's application 404 on all four routes |
| Access logs | `tests/test_access_log.py` (3 tests) | the body-keyed route logs as `PUT /api/applications/{app_id}/answers`; the old key-in-path form logs as `PUT unmatched_route` 404; no key, token, e-mail, URL or id on any line, including from a real uvicorn |
| Every caller moved | the application page, `frontend/e2e/submission.spec.ts`, 51 backend test calls, `compose_tests/run_execution_test.py` | full backend suite and Playwright pass on the new routes |

## Support-state wording (2026-10-22; local only, no external request)

Synthetic data and local fixtures only. No support state changed: the wording now follows from
the evidence already recorded. Results are from the cloud sandbox (PostgreSQL 16, Redis 7).

| Requirement | Evidence (`tests/test_support_wording.py` unless noted) | Result |
|---|---|---|
| Support states follow the evidence | `test_each_providers_support_state_follows_its_evidence` | 10 providers: 5 `fixture_only`, 2 `observed_read_only` (`greenhouse_dom`, `greenhouse_readonly`), `workday` and `lever` planned, `manual_handoff` manual; ignoring observed evidence is caught |
| No live label in advance | `test_a_live_level_has_no_label_until_one_is_added_deliberately` | a spec given `live_fill` derives `live`, and its label and route qualifier lookups fail; adding a live label is caught |
| API and browser routes carry their evidence | `test_an_api_or_browser_route_always_carries_its_evidence` | no evidence → refused; every implemented API or browser provider's route reads "(local test fixture only)"; allowing a bare route is caught |
| No label claims more than its evidence | `test_no_label_claims_more_than_its_evidence` | no "live", "supported" (other than "Not supported"), "available", "compatible" or "verified"; every test-source label says "local test" and "(fictional employer)"; a label claiming support is caught |
| Every stored form source is worded | `test_every_form_source_the_capture_code_stores_is_worded` (read from the source) | the 5 sources the capture code assigns equal the label table; a missing one is caught |
| The pages write no support wording of their own | `test_the_frontend_writes_no_support_wording_of_its_own` | no served label and none of the retired qualifiers in `frontend/src`; a page that hard-codes one is caught |
| The API serves the labels | `test_the_api_serves_the_labels` | providers, discovery sources, a job's route (manual, then browser), the form and the package view; the job page and the application page get the same form label; dropping the package view's label is caught |
| Wording never changes a package | `test_wording_never_changes_the_package_or_its_hash` | the label is outside the content; rewording it changes neither the package version nor its hash |
| The same form, the same words, on both pages | `frontend/e2e/submission.spec.ts` (both Greenhouse-style forms), `phase-b.spec.ts`, `discovery.spec.ts`, `routing.spec.ts` | one label on the job page and the application page; the discover page shows the served "Local test fixtures only"; the button reads "Read Greenhouse-style test form" |

## Route reason codes and route truthfulness (2026-10-22; local only, no external request)

Synthetic data and local fixtures only; no employer, ATS or Freehire was contacted. No provider
support state changed. Results are from the cloud sandbox (PostgreSQL 16, Redis 7).

| Requirement | Evidence (`tests/test_reason_codes.py` unless noted) | Result |
|---|---|---|
| Every code but the fallback has a producing path | `test_every_code_but_the_fallback_has_a_path_and_the_fallback_has_none`, `test_each_code_is_produced_by_its_path` (13 paths) | each of the 13 codes produced by its own path: `decide`, `route_for_job` through the API, `policy.check_binding` (`no_adapter`), the discovery view (`source_record_incomplete`, `source_posting_closed`); a code added without a path is caught |
| No decision or refusal relies on the fallback | `test_every_decision_and_refusal_in_the_code_names_a_known_code` (read from the source), `test_no_destination_falls_through_to_the_fallback` (test and production) | every `RouteDecision` names a reason and every `UnsupportedDestination` a fixed code listed in `REASONS`; 576 decisions over sample destinations (origin, submit address, form source, ATS host), with and without an API grant, in test and production: none gets `no_supported_provider`, and only fixture origins outside production get an API or browser route. A refusal left on the default code is caught by all three tests |
| Codes are safe to record | `test_codes_are_fixed_identifiers_that_are_safe_to_record` | lowercase identifiers; each survives the audit sanitizer unchanged |
| The router refuses real destinations on its own | `test_the_router_refuses_a_real_destination_even_if_the_adapter_policy_accepts_it` | with `policy.adapter_for` patched to accept everything, a non-fixture origin is still a manual handoff (`real_destination_disabled`); removing the router's own gate is caught |
| A real destination is told so before any form step | `test_a_real_destination_is_told_so_before_any_form_step`; `test_freehire_imports_are_never_treated_as_form_schemas`; `frontend/e2e/routing.spec.ts` | a job on a non-fixture site: `real_destination_disabled` with the adapter policy's own message, never "Capture the application form first.", and still so after a form is attached; production: `production_disabled` before any form lookup; a fixture job or a job without an address: `no_form_captured`; imported discovery jobs follow the same rule; the job page shows it (desktop and mobile) |
| A browser refusal does not block an authorized API route | `test_a_browser_refusal_does_not_block_an_authorized_api_route` | no submit address, or a cross-origin one: API `fake_api` with the grant and credentials; without a grant the refusal stands (`no_captured_destination`) |
| The documentation lists exactly the codes | `test_the_documentation_lists_exactly_the_reason_codes` | the table in `docs/provider-architecture.md` equals `REASONS` (14 codes); a removed row is caught |
| A route is audited once per change | `test_a_repeated_route_check_is_recorded_once_and_each_change_again` | 3 identical checks → 1 row; form captured, API granted, grant revoked → 4 rows in all, the last equal to the second (a change from the previous one); removing the comparison is caught |
| The discovery view audits a linked record's route like the job page | `test_the_discovery_view_records_a_linked_jobs_route_as_the_job_page_does` | view → 1 row for the tracker job; the job page then shows the same decision and adds none; an unlinked record and another user's view (404) add none. Not auditing the view, or not deduplicating, is caught |
| The audit inventory cannot hide keys | `tests/test_audit_inventory.py` | a `record(**meta)` call fails the scan, so every event's keys stay readable |
| A posting closed before linking says so | `test_each_code_is_produced_by_its_path[source_posting_closed]` | mock feed with the posting closed at its first import: no tracker job; route "This posting was closed at its source, so it was not added to your tracker." (`source_posting_closed`), not "Import this job manually."; removing the branch is caught |
| The job page names the provider and its evidence | `frontend/e2e/routing.spec.ts` | Workday: `planned_adapter_only`, no provider line; no form: `no_form_captured`; a form captured from the local receiver: "Browser adapter (local test fixture only)", `browser_supported`, and (since the support-wording change below) "Provider: fixture_ats — Local test fixtures only", equal to what the API serves |

## Privacy, audit and baseline corrections (2026-10-21; local only, no external request)

Synthetic data and local fixtures only. Results are from the cloud sandbox (PostgreSQL 16,
Redis 7); CI results are in `docs/implementation-status.md`.

| Requirement | Evidence (`tests/test_audit_privacy.py` unless noted) | Result |
|---|---|---|
| Prohibited audit keys are redacted | `test_prohibited_keys_are_redacted` (6 categories) | every value `[redacted]` |
| Unsafe values are omitted under any key | `test_unsafe_values_are_omitted_under_any_key` (12 values) | `[omitted]` |
| Safe metadata kept; external ids become references | `test_safe_metadata_is_kept_and_external_identifiers_become_references`, `test_sanitizing_is_idempotent` | unchanged; `field` → `field_ref`; a second pass changes nothing |
| Sanitizing happens before storage | `test_record_sanitizes_before_anything_is_stored` | stored row redacted and omitted; fails when the sanitizer is bypassed |
| Route decisions audited with safe fields only | `test_route_decisions_are_audited_without_applicant_or_external_data` | 5 decisions, exactly 6 keys each, no synthetic marker |
| Generic route messages | `test_ui_route_messages_are_generic_and_carry_a_reason_code` | no form wording; `unsupported_required_control` |
| A full application leaves no applicant or posting data | `test_a_full_application_leaves_no_applicant_or_posting_data_in_audit_events` | no marker in any audit row |
| Drafts recorded by reference and reason code | `test_a_rejected_draft_records_a_reason_code_not_its_content`, `test_a_created_draft_records_a_field_reference_not_the_question_key` | `field_ref` + `invented_numbers`; no draft text |
| Logs keep the error type, never the payload | `test_unexpected_runner_errors_are_logged_by_type_only`, `test_the_egress_proxy_never_logs_destination_hosts` | type name only, no traceback; destination count only |
| Legacy audit rows repaired once, irreversibly | `tests/test_audit_repair.py`: `test_repair_sanitizes_every_legacy_row_and_a_second_run_changes_nothing`, `test_the_migration_repairs_legacy_rows_reports_counts_only_and_is_irreversible` | 18 synthetic rows: 13 changed, then 0; downgrade restores nothing; output is counts only |
| A failed repair reveals nothing | `tests/test_audit_repair.py`: `test_a_failed_repair_reveals_no_legacy_content` | type name only, nothing chained, transaction rolled back |
| Audit inventory matches the code | `tests/test_audit_inventory.py`: `test_the_inventory_lists_exactly_the_events_the_code_writes`, `test_every_documented_metadata_key_survives_the_sanitizer` | fails on a removed document row or an added code key (both checked) |
| Documents cite only existing tests | `tests/test_doc_references.py`: `test_every_cited_test_exists` | every cited test function or module exists |
| CAPTCHA claimed only where detected | `tests/test_execution_routing.py`: `test_a_captcha_checkpoint_is_claimed_only_where_the_adapter_detects_one`; `tests/test_greenhouse_dom.py`: `test_a_captcha_on_the_form_stops_before_anything_is_disclosed` | `fixture_ats` claims none; `greenhouse_dom` stops with 0 disclosures |
| Cancel echoes only its own refusal | `tests/test_execution_failures.py`: `test_cancel_reports_only_its_own_refusals` | terminal state 400; any other error stays a server error; fails with the old catch-all |
| Route endpoint is tenant-scoped | `tests/test_execution_routing.py`: `test_another_users_job_route_is_not_found_and_not_audited` | 404; no route decision recorded |
| Keyed references: stable per user and key, unrelated across users and keys | `tests/test_audit_refs.py`: `test_same_user_and_input_give_a_stable_versioned_reference`, `test_different_users_never_share_a_reference_for_the_same_input`, `test_changing_the_key_changes_every_reference`, `test_a_reference_is_not_the_legacy_unkeyed_hash` | `ref:v2:` + 32 hex; no identifier or key in it; a legacy reference becomes `[omitted]` (also inside a list) |
| The key is mandatory and never shown | `tests/test_audit_refs.py`: `test_a_missing_or_short_key_fails_closed_without_showing_it`, `test_production_refuses_a_test_only_key`, `test_the_key_is_not_in_the_settings_repr` | missing or short key: references and API start-up refused; production refuses a test-only key; the key is in no message or repr |
| Stored references are user-scoped | `tests/test_audit_refs.py`: `test_stored_references_are_user_scoped_and_hold_no_raw_key_or_secret` | two users, same question: different `field_ref`; same user: identical; no raw key or secret in the rows |
| Legacy references removed once, irreversibly | `tests/test_audit_refs.py`: `test_the_v2_migration_removes_legacy_references_and_is_idempotent` | 8 synthetic rows from 2 users: 6 changed, then 0; no legacy reference, raw key or secret in the rows or the output; downgrade restores nothing |
| Isolation failures show a code only | `tests/test_error_boundary.py`: `test_an_isolation_failure_reaches_the_user_as_a_code_only`, `test_a_refusing_runner_keeps_neither_its_address_nor_its_body`, `test_a_refusing_egress_proxy_and_failing_namespaces_keep_no_output` | outcome `browser isolation unavailable (runner_refused)`; no address, body, token, question key or traceback in the outcome, API, audit rows or app logs; fails when the raw error is stored |
| Form-capture mismatch is generic | `tests/test_error_boundary.py`: `test_a_form_capture_mismatch_shows_a_generic_message_and_a_code` (3 modes); `test_capture_refused_when_page_disagrees_with_job_data`, `test_capture_refuses_an_ambiguous_page` | 409, "unsupported or incomplete" + reason code; no field key, address or path |
| Form drift, uploads and readback give counts and fixed reasons | `test_form_changed_after_approval_stops_before_disclosure`, `test_combobox_that_does_not_keep_its_choice_is_caught_by_readback`, `test_unlisted_dropdowns_that_appear_after_approval_stop_before_disclosure`, `test_page_requires_a_field_with_no_approved_answer_stops_before_disclosure`, `test_unverifiable_dropdowns_stop_before_anything_is_disclosed` | "1 new field(s)", "1 field(s) did not keep their values", "2 new field(s)", "required by the page, no approved answer", the dropdown's own refusal reason; no field key |
| Unexpected API errors are a generic 500 | `tests/test_error_boundary.py`: `test_an_unexpected_error_is_a_generic_500_logged_by_type` (route, attempts, authentication); `tests/test_execution_failures.py`: `test_cancel_reports_only_its_own_refusals` | generic body; security headers kept; log is type + method + route template; fails without the boundary |
| Expected errors unchanged | `tests/test_error_boundary.py`: `test_expected_errors_keep_their_status_and_own_messages` | 401 anonymous, 404 cross-tenant, 422 validation, 409 refusal |
| Access logs carry route templates only | `tests/test_access_log.py`: `test_access_lines_carry_the_route_template_never_the_raw_path`, `test_raw_access_records_from_the_server_are_dropped`, `test_the_real_server_prints_route_templates_only` | real uvicorn: `"PUT /api/applications/{app_id}/answers HTTP/1.1"` (the key in the body), the old key-in-path form as `"PUT unmatched_route HTTP/1.1" 404`, health 200; no question key, token, e-mail, URL, id or client address; fails without the filter |
| The web server logs no raw paths | `frontend/e2e/log-privacy.spec.ts` (development request log off; proxy failure without its URL); manual run of `next dev` and `next start` against an unreachable backend | no marker in either log; "Failed to proxy an API request to the backend (ECONNREFUSED)" |
| Retained errors are types only | `tests/test_execution_failures.py`: `test_broker_outage_after_commit_loses_nothing` | outbox `last_error` is `ConnectionError`; the broker URL and its password are not kept |
| Database errors carry no bound values | `tests/test_retained_data_privacy.py`: `test_a_database_error_never_carries_bound_values` | "SQL parameters hidden"; no answer text or e-mail; fails without `hide_parameters` |
| Library logs keep exception types only | `tests/test_retained_data_privacy.py`: `test_a_failed_task_is_logged_by_exception_type_only`, `test_the_filter_reduces_handler_errors_and_reprs_to_types` | a real eager Celery failure is logged as `RuntimeError`, no traceback, no quoted row; fails without the filter |
| Evidence keeps counts and categories | `tests/test_retained_data_privacy.py`: `test_destinations_are_classified_without_a_lookup`; `test_browser_cannot_reach_other_origins`, `test_page_altering_a_filled_value_stops_before_submit`, `test_full_run_sends_exactly_the_approved_values` | blocked: loopback >= 2, link-local >= 1, private >= 1, no host; readback `{"checked": n, "mismatched": k}`; receipt without title or path; fails when hosts are kept |

## Execution routing (2026-10-21; local only, no external request)

These are local fixture tests. The receiver, its Greenhouse-style forms and its fake API are
labelled stand-ins, and nothing claims live API or ATS compatibility.

| Requirement | Evidence (`tests/test_execution_routing.py` unless noted) | Result |
|---|---|---|
| Routing vocabulary, no live claims | `test_every_provider_declares_the_routing_vocabulary_without_live_claims` | 13 names for every provider; no `live_*` level; `greenhouse_dom`: browser_fill and custom_dropdown fixture, location_picker fixture since D104 (a local stand-in; none before), public_schema_read observed, CAPTCHA_possible unknown |
| Workday is a specification only | `test_workday_is_a_specification_only` | stage planned; every capability none; traits "expected"; status says not supported |
| Interface only where operations exist | `test_interface_is_implemented_only_where_the_operations_exist` | 9 names; manual handoff only `request_user_action`; Workday and Freehire none |
| API vs browser vs manual | `test_route_selection_api_then_browser_then_manual` | no form: manual; captured: browser `greenhouse_dom`; grant without token: browser; grant plus token: API `fake_api`; real origin: manual |
| API connector needs explicit authorization | `test_a_known_api_connector_is_never_selected_without_explicit_authorization` | token configured, no grant: browser, with the reason "no active authorization"; 0 `/fapi/` requests |
| Unsupported capability: checkpoint before disclosure | `test_an_unsupported_required_control_is_a_checkpoint_before_disclosure` | location job: route `checkpoint`, "Nothing is sent"; coordinates unresolved; approval refused; 0 disclosures. Mutation-checked |
| Adapter version mismatch | `test_an_adapter_version_mismatch_blocks_queueing_and_execution` | 409 at queue; after queueing: `failed_safe` "execution method changed"; 0 disclosures, 0 acceptances |
| Job source is not a form schema | `test_freehire_imports_are_never_treated_as_form_schemas` | after an import: 0 `JobForm` rows; every linked job "Capture the application form first."; only `search` requested; the client has no form method |
| Workday never routed to Greenhouse | `test_a_workday_job_is_shown_unsupported_never_routed_to_greenhouse`, `test_a_form_from_another_ats_is_refused`; `frontend/e2e/routing.spec.ts` | Workday job: manual "Workday applications are not supported yet", even with a Greenhouse form source; Greenhouse capture refused (400) with 0 requests; a Lever job with a Greenhouse form refused; the job page shows it (desktop and mobile). Mutation-checked |
| CAPTCHA is a user action | `test_a_captcha_becomes_a_user_action_never_an_automated_solve` | `failed_safe` "does not solve"; application `needs_user_action`; 0 disclosures; every checkpoint policy non-automated |

## Freehire discovery provider (2026-10-21; fixture only, no Freehire API request)

All of this is local fixture evidence. The oracle is the fixture's own request table
(`freehire_requests`: route, offset, limit, whether an Authorization header was present). It
runs against `fixtures/ats_receiver/freehire_fixture.py`, a stand-in shaped like Freehire's
public API reference as reviewed on 2026-10-21, with synthetic data. **Nothing here shows
compatibility with the live Freehire service.** Personal prototype only (D34).

| Requirement | Evidence (`tests/test_freehire_discovery.py` unless noted) | Result |
|---|---|---|
| Off by default; nothing requested | `test_defaults_are_off_with_no_base_url_and_no_key`, `test_disabled_by_default_and_nothing_is_requested` | default settings: no provider, no base URL, no key, no rate setting; import and healthcheck 409; 0 fixture requests; unknown provider 404 |
| No live access | `test_a_live_base_url_is_refused_before_any_request` | `https://freehire.me` refused before any request (network call patched to fail the test); nothing written |
| Status table honest; key never shown | `test_status_table_and_capabilities_never_claim_external_testing` | external configured/tested/production false; no "600" claimed; attribution "via freehire.me"; only "configured: yes/no" for the key |
| Mock never in production | `test_mock_provider_is_never_enabled_in_production` | refused |
| Documented shapes; pagination; dedup | `test_import_pages_normalizes_and_deduplicates` | 5 open records in 3 pages (offsets 0/2/4, no key); the closed posting is absent from search; top-level `work_mode` read (hybrid/onsite/remote); `enrichment.employment_type`; plain-text summary; tri-state sponsorship with basis "provider enrichment"; duplicate slug linked by job URL; no-URL record incomplete |
| `work_mode` from the top level only | `test_work_mode_is_read_from_the_top_level_only`, `test_undocumented_fields_are_not_read` | the old shape (only `enrichment.work_mode`) gives `unknown`; `last_seen_at` not read; undocumented work-mode or non-boolean sponsorship values stay unknown. Mutation-checked: an enrichment fallback fails the test |
| No raw payload kept | `test_no_raw_payload_is_kept` | stored keys are exactly the normalized fields and `raw_ref` (provider, id, fingerprint, field names); no HTML, enrichment, counters or `reality`; the tracker job gets the plain summary |
| Attribution | `test_every_listing_is_credited_via_freehire`, `test_the_mock_is_never_credited_to_freehire`; `e2e/discovery.spec.ts` | every Freehire listing and job-page source carries `{"text": "via freehire.me", "url": null}` (no documented listing URL); mock credited "local mock data (not from freehire.me)"; UI shows the credit on all 5 listings and on the job page |
| Pacing from documented headers | `test_paging_stops_when_the_documented_budget_is_used_up`, `test_without_rate_headers_nothing_is_assumed_or_waited` | `X-RateLimit-Remaining: 0` stops after 2 pages (truncated, reason quotes the headers); 2 requests; no sleep anywhere (patched to fail); without headers all pages read, no waiting. Mutation-checked: ignoring Remaining fails the test |
| 429 | `test_a_429_is_reported_with_retry_after_and_never_retried` | 503 "Freehire is rate limiting requests (Retry-After: 30 s); not retried. Nothing was changed."; exactly 1 request; no sleep; nothing written |
| Closed and stale | `test_a_posting_closed_since_is_absent_from_search_and_seen_closed_by_detail`, `test_detail_serves_a_closed_posting_and_it_never_creates_a_job`, `test_refresh_marks_a_record_gone` | absent from search: not marked stale (listing never complete); refresh sees `closed_at`: "closed at source", link and tracker job kept; detail serves a closed posting; 404 → "no longer at the source" |
| No `/status` use | `test_healthcheck_makes_no_request_and_never_uses_status` | healthcheck is configuration only (0 requests even during an outage); imports never call `/status`. Mutation-checked: a healthcheck calling `/status` fails the test |
| Unchanged re-import; changed posting; matching | `test_reimport_is_unchanged`, `test_a_changed_posting_is_recorded_and_the_users_job_is_left_alone`, `test_existing_jobs_are_matched_by_url_then_conservatively_and_never_modified` | 5 unchanged; `changed_fields` title, location with the user's edit kept; matched by job URL and by employer/title/location; existing job never modified |
| Filters on supplied data only | `test_filters_use_only_what_the_source_supplied`, `test_sponsorship_filter_matches_only_a_stated_yes`, `test_preferences_are_used_only_when_asked` | missing data = "not enough data"; stated mismatch excludes; sponsorship "offered" matches only a stated yes; preferences only on request |
| Failures change nothing | `test_provider_failures_change_nothing` (outage, bad JSON, pagination loop, timeout) | 503 "Nothing was changed"; 0 rows, 0 jobs |
| Outage never blocks the rest | `test_an_outage_never_blocks_manual_jobs_imports_or_tracking` | manual job 201, CSV import 1 created, application 201 |
| Malformed; bounded paging | `test_malformed_records_are_skipped_and_counted`, `test_paging_is_bounded_and_loops_are_refused`, `test_truncated_listing_is_reported` | 2 skipped, 5 imported; repeated cursor refused; page limit reported as the stop reason; nothing past the 10,000 window |
| Isolation; key; markup | `test_discovered_jobs_are_user_scoped`, `test_the_key_is_sent_by_the_server_only_and_never_shown`, `test_untrusted_markup_becomes_short_plain_text` | other user: empty / 404; key sent only as a server bearer, absent from responses and logs; scripts dropped, 500-character cap |
| UI, desktop + mobile | `frontend/e2e/discovery.spec.ts` | source status, import result, "Source: Freehire" with "via freehire.me" (5), missing fields, sponsorship basis, existing job linked and unchanged with the credit on its page, outage message, manual job still added |

## Submission providers, fake API and discovery (2026-10-21; local only)

All of this is **local fixture evidence**. No external service was contacted. The fake API is
NoEfforts' own contract, and the Freehire provider is a mock with an invented record shape.
The oracle for the API route is the receiver's ledger (drafts, uploads, acceptances keyed by
the idempotency key).

| Requirement | Evidence | Result |
|---|---|---|
| No live claim from a fixture | `test_only_the_pilot_is_enabled_for_real_destinations_and_none_claims_live_support`, `test_real_page_evidence_is_recorded_only_where_it_exists`, `test_spec_invariants_reject_unsupported_claims` (6) | no `live_fill`/`live_submit` anywhere; `observed` only where run evidence exists; unsupported specs refused on import |
| Capabilities machine-readable | `test_capabilities_are_machine_readable_through_the_api` | `GET /api/providers`, `GET /api/execution/capabilities` → `providers` |
| Routing: real destination, nothing captured | `test_real_destinations_go_to_a_manual_handoff`, `test_no_captured_destination_is_a_manual_handoff` | manual handoff |
| Browser vs API selection | `test_browser_unless_the_api_is_authorized_configured_and_supported`, `test_observation_and_discovery_providers_are_never_routes` | API only with the user's grant + credentials + support; revoke → browser; observation/discovery never chosen |
| Grants are user-scoped and fixture-only | `test_authorizations_are_user_scoped_and_fixture_only` | non-fixture origin 400; non-API provider 400; other user's delete 404; other user still routes to the browser |
| Approval invalidated by a route change | `test_granting_the_api_retires_a_browser_approval_and_revoking_retires_it_again`, `test_missing_credentials_after_approval_stop_before_anything_is_sent` | 409 at queue (approval retired); token removed after approval → failed_safe "execution method changed", 0 API requests |
| No run without authorization | `test_without_authorization_the_api_is_never_contacted` | browser route; 0 `/fapi/` requests |
| No stale approval | `test_a_stale_approval_stops_before_disclosure` | not run; 0 POSTs, 0 disclosures |
| No wrong provider | `test_an_attempt_recorded_for_another_provider_is_refused` | failed_safe; 0 API requests, 0 acceptances |
| API happy path sends exactly the approved package | `test_authorized_api_submission_sends_exactly_the_approved_package` | 1 acceptance, key = attempt id, every value equal, upload digest = approved, no form-page request during the run |
| Refusals before disclosure | `test_refusals_before_disclosure` (schema changed, 401, 429) | failed_safe after the schema GET only; 0 disclosures |
| Outcomes after sending | `test_outcomes_after_sending` (422, 500, 429) | rejected / unknown / unknown; exactly 1 submit; second delivery ignored |
| Accepted but response lost | `test_accepted_but_response_lost_is_unknown_and_never_resent` | unknown; ledger 1 acceptance; reconcile (read-only) = accepted; still 1 submit; state left unknown; event recorded |
| Idempotency at the API | `test_the_fake_api_itself_never_accepts_one_key_twice` | same key → same draft, same receipt, 1 acceptance; incomplete → 422; status lookup by key |
| No leakage | `test_api_evidence_and_logs_carry_no_candidate_data_secrets_or_raw_ids` | email, phone, token, raw receipt, document bytes absent from evidence, events, outcome detail and captured logs; evidence holds `receipt_ref_sha256` |
| Discovery: import, normalization, dedup | `test_import_normalizes_deduplicates_and_keeps_incomplete_records_unlinked`, `test_a_posting_the_user_already_tracks_is_linked_not_duplicated` | 5 records → 3 tracker jobs (tracking-parameter duplicate merged); existing job linked; URLs preserved; ATS "unknown" for the fixture origin |
| Discovery: unknown stays unknown | `test_missing_data_stays_missing_and_source_facts_stay_out_of_the_profile` | sponsorship yes/unknown/no as stated; location `None`; workplace `unknown`; no salary or eligibility; 0 work-authorization rows |
| Discovery: stale, unchanged, scoped | `test_reimport_is_unchanged_and_stale_records_are_marked_not_deleted`, `test_discovered_jobs_are_user_scoped` | re-import 5 unchanged; missing → stale, tracker job kept; closed → stale; relisted → un-staled; other user sees nothing |
| Discovery → application route | `test_application_route_is_a_manual_handoff_until_a_form_is_captured`; `tests/test_reason_codes.py` | incomplete → "Import this job manually." (`source_record_incomplete`); closed before linking → `source_posting_closed`; uncaptured → "Capture the application form first."; real origin → manual; captured fixture form → browser `greenhouse_dom` |
| Checkpoints, never solved | `test_no_checkpoint_is_ever_completed_by_noefforts`, `test_no_solver_or_evasion_code_exists`, `test_manual_handoff_spec_cannot_fill`; existing `test_captcha_stops_before_anything_is_disclosed` and the emailed-code round tests in `test_execution_security.py` | no automated checkpoint; only an emailed code typed by the user resumes; no solver or stealth library in `app/` |

## Id-only page mapping, v2 fixture and adapter, output privacy (2026-10-20)

Everything here is **local fixture evidence**. Nothing in this section touched Greenhouse or
any real employer, and none of it shows that a real page can be filled or submitted.

| Requirement | Evidence | Result |
|---|---|---|
| Unique, labelled, type-suited control per API field | `test_every_api_field_maps_to_exactly_one_labelled_control` | 12/12 mapped on v2 job 5020001 |
| Ambiguous / mislabelled / missing controls refused | `test_ambiguous_or_mismatched_mappings_are_rejected` (3 modes); capture 409 | refused, never guessed |
| Search picker and hidden coordinates not filled | `test_text_question_rendered_as_search_picker_is_unsupported_not_typed`, `test_location_job_is_a_checkpoint` | unsupported → checkpoint |
| Preferred name, unknown conditions not guessed | `test_preferred_name_and_unknown_condition_are_not_guessed` | `needs_user`; conditional value `None` |
| Notice is not consent | `test_notice_is_not_a_field_and_no_consent_is_invented` | no checkbox invented |
| Full run, values verified at the receiver | `test_full_run_sends_exactly_the_approved_values` | combobox values `1`/`913`/`0`, preferred name as typed, upload digest = approved, readback 0 mismatches |
| Combobox value readback | `test_combobox_that_does_not_keep_its_choice_is_caught_by_readback` | abandoned, 0 acceptances |
| Drift after approval stops before disclosure | `test_drift_after_approval_stops_before_anything_is_disclosed` (5 modes: duplicate id, label, missing, new question, swapped options) | failed_safe, 0 disclosures |
| Outcomes, no retry | `test_outcome_classification` (6 modes) | rejected / unknown / abandoned as listed; second delivery ignored |
| Original fixture and routing unchanged | `test_greenhouse_adapter.py`, `test_original_fixture_still_routes_to_the_original_adapter` | passed |
| Output privacy (allowlist, aliases, guard) | `test_success_output_has_aliases_and_no_markers`, `test_failure_paths_print_types_only`, `test_guard_rejects_unknown_strings_and_derived_values` | no marker on success or failure paths; suppressed output on a guard failure |
| Mapping evidence collector (B2 code) | `test_mapping_evidence_on_the_v2_fixture`, `..._reports_ambiguous_and_absent_explicitly`, `test_blocked_dependency_marks_rendering_possibly_incomplete` | per-field ids, labels, roles, visibility; denied script → "may be incomplete" |
| Same collector in the isolated container | Compose `s_readonly_mapping_in_container` | CI #34 (`6d0a437`): passed; execution-compose 80 checks, 0 failed |
| UI, desktop + mobile | e2e "Greenhouse-style v2 form …" | local `submission.spec.ts`: 20 passed; CI #34 full Playwright suite: 26 passed |
| Approval bound to the execution method | `tests/test_approval_binding.py` (9) | new route or version → queue refused and approval retired; change after loading → stopped at the gate; tampered attempt adapter → failed_safe; pre-binding approvals kept while unchanged; 0 disclosures in every refusal |
| B2 limits enforced | `tests/test_gh_readonly.py` limit tests | navigation, redirects, request budget, received-bytes stop, retained DOM, deadline, watchdog, output size; fixtures only |
| Options only on open | `test_options_rendered_only_on_open_are_not_observable_not_a_mismatch` | `not_observable_at_load` |
| Widget inspection (local only; not approved for a real page) | `tests/test_widget_inspection.py` (18), Compose `s_readonly_widget_inspection_in_container` | open/close only, nothing selected; action, time and request budgets; submission cancelled, upload POST and navigation refused before sending, same-origin GET data request refused; challenge, dialog, file chooser, address change stop; receiver saw only the page GET |
| Workflow entry point in a fresh process; explicit outcome | `tests/test_readonly_cli_process.py` (3) | `python -m … --inspect-widgets` against the receiver: navigation through the filter, inspection completed, exit 0; injected filter failure: page never requested, exit 6 within seconds; no browser left behind; public output has no traceback or marker. Mutation-checked (entry point misplaced; filter not fail-closed) |
| Detector limits (independent widget model) | `tests/test_widget_detector.py` | portal, unlinked popup, wrapper state and delayed lists: found and compared. Late lists, lists without roles, and lists waiting on refused data: opened, not observable. Silent widget: undetermined. Wrong click target: not opened. Virtualized list: partial and never compared. Refused data requests published as path shapes only |
| Required signals and execution rule | `tests/test_required_signals.py` | signals recorded separately (attachments included). An unmarked required field runs with its answer. A page-required field with no approved answer is refused before disclosure (ARIA or label marker). Mutation-checked against the old rule |
| Real posting, run #9 (diagnostic re-observation) | run [39612152070](https://github.com/KevinD003/AutoApply/actions/runs/39612152070) on `e1bd9e7` (pinned branch, CI #52) | workflow success; observation `completed`. A 3×200; 1 navigation, 26 GET, 0 non-GET; 24 actions on 12 dropdowns. All 12 `not_opened`: no opening evidence **within the 600 ms window** for a click on the control (not proof that they cannot open); 0 DOM change. Refused data requests all `GET /locales/*/*.json` (4 at load, 7 during actions). Required evidence consistent for 19 of 19 mapped fields; the resume is required by its group |
| Dropdown strategies (adapter, fixture only) | `tests/test_dropdown_strategies.py` | click, ArrowDown, single trigger, locale-at-load, delayed and preselected-first: the exact approved option is submitted. Not opened by any strategy, type-only, two triggers, network-loaded, too slow, virtualized and duplicated: refused before disclosure. Ignored or wrong choice: caught by readback, never submitted. Dropdowns the job data does not list: a checkpoint from capture, or a stop before disclosure if they appear after approval. Mutation-checked (first option; network) |
| Run-#9 signature vs fixtures | `test_run9_signature_is_consistent_with_a_locale_gate_but_does_not_prove_it` | a locale-gated widget under the inspection policy shows run #9's signature; an inert one shows it without the requests. Consistency only |

Fixture assumptions (not observed on any real page): how comboboxes open and select, option
values, the upload endpoint and status element, JSON submission, the confirmation message and
condition triggers.

## Read-only Greenhouse check: code and fixture evidence (2026-10-20)

- **Approval.** The user approved permissions A and B for one posting, on condition that no
  employer or person name goes into the repository. C and D are not approved.
- **Code-tested revision:** `86fa55e`. CI #30
  [39428565520](https://github.com/KevinD003/AutoApply/actions/runs/39428565520) passed all four
  jobs. execution-compose: **76/76**, including `s_readonly_observation_in_container`:
  - the fixture form was read in the isolated browser (15 fields);
  - the page's on-load POST was blocked;
  - 0 disclosures at the receiver.
- **Local:** `tests/test_gh_readonly.py` 10 passed; with `test_greenhouse_adapter.py`, 34
  passed.
- **Not run against Greenhouse yet.** The development sandbox's network policy denied
  `boards-api.greenhouse.io` (403 at the environment proxy, one attempt, not retried). The real
  run is the manual workflow `greenhouse-readonly.yml`, which waits for the repository secret
  `GH_READONLY_POSTING`.

## Proxy control-plane separation and recovery (2026-10-20)

Scope: local implementation and synthetic tests only. No external posting was retrieved, no
page was opened, and no candidate data was used.

- **Baseline.** Before this work HEAD was `a595795`, docs-only after code `9d6bd7e` (CI #24,
  above; CI #25 on `a595795` passed).
- **Code-tested revision:** `d62bea7`. CI #28
  [39421195994](https://github.com/KevinD003/AutoApply/actions/runs/39421195994) passed all four
  jobs:
  - backend: 234 passed, 1 skipped (the same root-only PID 1 test as before);
  - frontend e2e: passed;
  - docker-smoke: passed;
  - execution-compose: **73/73 checks**
    ([job](https://github.com/KevinD003/AutoApply/actions/runs/39421195994/job/118622270249)).

| Revision | Change | CI | Outcome |
|---|---|---|---|
| `4a0bd5a` | control API moved to a UNIX socket on the `egress_control` volume (proxy rw, worker ro); `exec_proxyctl` removed; new control-plane, recovery and post-OOM checks | #26 | execution-compose 73/73 ✓, frontend ✓, smoke ✓; backend ✗: `test_runner_and_proxy_control_need_their_tokens` got BrokenPipeError instead of 401 |
| `3fb3a9f` | docs (approval request) on the same code | #27 | all ✓ (the race did not trigger) |
| `d62bea7` | control API reads the request body before refusing (reproduced: 10/500 refused requests broke before, 0/500 after) | #28 | all ✓ |

**Proxy management reachability (Compose, CI #28, from inside the browser container)**

| Check | Result |
|---|---|
| TCP connect to every port 1–65535 of `egress-proxy` | only **3128** accepts |
| Control socket path in the browser container | absent |
| Sensitivity control: a listener on `0.0.0.0:3199` started inside the proxy container | found by the same scan (`[3128, 3199]`) |
| Through the proxy with a real session's credentials: `CONNECT egress-proxy:3129`, `egress-proxy:3128`, `127.0.0.1:3128`, `localhost:3129`, `worker:8000`; absolute GET `http://egress-proxy:3129/health`, `http://127.0.0.1:3128/` | all **403** |
| Positive control: `CONNECT receiver:8799` with the same credentials | 200 |
| Worker over the socket: create, inspect, delete own session; no token | 201/200/200, then 404 after delete; 401 without token |
| After `docker compose restart egress-proxy` | only 3128 open; worker reaches control again; approved run confirmed |

**Recovery (Compose, CI #28)**

| Scenario | Result |
|---|---|
| Runner restart with an open session | old endpoint and secret refused; old runner session unknown (404); old proxy session deleted (200); `/tmp` clean; new attempt confirmed |
| Memory hog → OOM kill → restart | hog attempt `failed_safe`, 0 accepted, still one attempt with `retry_count` 0 (not replayed); `/tmp` clean; next attempt confirmed |
| Browser lost after disclosure (local pytest) | `abandoned`, `needs_user_action`, retry 0, 0 accepted; a redelivery is ignored |

**Receiver acceptance counts (CI #28):** 1 each for:
- the approved run after the proxy restart;
- the Greenhouse security-code flow (0 before the code);
- the hostile page;
- the run with interception off;
- the attempt after OOM recovery;
- the attempt after the runner restart.

Interrupted runs:
- unknown with a duplicate delivery: 1;
- runner killed mid-submit: ≤ 1;
- worker killed mid-submit: ≤ 1, never resent.

Stop-safely cases: 0.

**New tests**

| Test | What it checks |
|---|---|
| `test_control_api_is_an_owner_only_unix_socket_not_a_network_listener` | the control API is an owner-only UNIX socket, not a network listener |
| `test_restart_replaces_a_stale_control_socket` | a restart replaces a stale socket |
| `test_refusals_are_delivered_not_broken_pipes` | regression for the CI #26 race |
| `test_browser_lost_after_disclosure_is_abandoned_not_retried` | browser lost after disclosure is abandoned, not retried |
| Compose `s_control_plane_separation` | the reachability checks above |
| Compose `s_runner_restart_recovery` | the restart recovery checks above |
| Compose `s_memory_exhaustion` | extended with the post-OOM checks |

Local runs (`d62bea7` code):
- `tests/test_container_runner.py`: 18 passed;
- `tests/test_browser_isolation.py`: 18 passed (on `4a0bd5a`);
- ruff: clean.

The full local suite was not rerun; CI #28 ran it.

## Isolated Compose execution milestone (2026-10-20)

Scope: the browser runs in its own sandboxed container behind a per-session egress proxy, and
the Compose stack is tested **only against the synthetic receiver**. No real employer pages,
candidate data, external accounts or paid services were used. Architecture and limits:
`docs/execution-service.md`.

**Four statuses, kept separate**

| Status | Result | Evidence |
|---|---|---|
| App-stack Docker smoke (`docker-smoke`) | passed | CI #24 [job](https://github.com/KevinD003/AutoApply/actions/runs/39376203647/job/118474795589) |
| Containerized browser execution (`execution-compose`) | passed, 56/56 checks, synthetic receiver only | CI #24 [job](https://github.com/KevinD003/AutoApply/actions/runs/39376203647/job/118474795553) |
| Fixture adapter compatibility (Greenhouse-shaped fixture) | passed (pytest + Compose security-code flow) | `test_greenhouse_adapter.py` (CI #24 backend), `s_greenhouse_security_code_flow` |
| Actual Greenhouse compatibility | **not tested** (no real page read) | proposal only: `docs/greenhouse-readonly-compatibility-proposal.md` |

**Phase 0 reconciliation**
- **Start state.** HEAD `4683d35` was docs-only on code `cc6c1da`. Its CI run #16 completed
  green, so the documentation follow-up's CI did finish.
- **Final code-tested revision of this milestone:** `9d6bd7e`. CI #24
  [39376203647](https://github.com/KevinD003/AutoApply/actions/runs/39376203647) passed every
  job:
  - backend: 230 passed, 1 skipped (`test_self_check_finds_its_browsers_when_the_runner_is_pid_1`
    needs root; the skip reason is printed, and the Compose job covers the same case);
  - frontend: e2e, desktop and mobile; the step passed (the log tail does not show a count);
  - docker-smoke: passed;
  - execution-compose: 56/56 checks.
- **CI host:** ubuntu-24.04, Docker 28.0.4, kernel 6.17.0-1022-azure. The value of
  `kernel.apparmor_restrict_unprivileged_userns` was 1, i.e. the restriction stayed on and was
  not relaxed for this job.

| Revision | Change | CI | Outcome / cause of failure |
|---|---|---|---|
| `6d1c790` | browser-runner, session proxy, Compose topology, harness | #17 | exec ✗: the host-side test could not reach the receiver on an internal network |
| `0e684e5` | receiver reached via `compose exec`; read-only proposal | #18 | exec ✗: admin reset sent as GET |
| `e29a6b2` | tri-state conditions, attempt-bound confirmation, harness fixes | #19 | backend ✗ (a test race, below); exec ✗ (receiver bound to loopback) |
| `617ec12` | docs only (same code as `e29a6b2`) | #20 | same as #19 |
| `dcc4500` | relay control channel, version check, interception switch, unplaceable conditions, new scenarios | #21 | backend ✗ (canary port reused in the test); exec ✗ (self-check failed with the runner as PID 1; a dependency recreate took the API down) |
| `a073a95` | canary port fix | #22 | backend ✓ frontend ✓ smoke ✓; exec cancelled (still had the PID 1 bug) |
| `992d6b2` | PID 1 self-check fix; `--no-deps`; API check per scenario | #23 | all ✓ |
| `9d6bd7e` | PID 1 regression test (reproduced first: old launcher → "no browser processes found") | #24 | all ✓ |

**Defects found and fixed in this milestone (each now has a test that would fail)**

| Defect | Test |
|---|---|
| A conditional question was marked "not asked" when its trigger was merely unanswered | `test_unanswered_trigger_keeps_its_conditional_question_pending` |
| A condition on a missing, later or circular question was evaluated as false | `test_unplaceable_condition_is_a_checkpoint_not_a_guess` |
| Any confirmation page counted, even one for a different posting | `test_outcome_classification[gh_confirm_other_job]` (→ unknown), `[gh_confirm_redirect]` (→ confirmed) |
| A stale or killed controller could leave a running browser; anyone with the endpoint could attach | `test_control_channel_is_single_use_and_authenticated`, `test_hard_killed_controller_leaves_no_browser`, `test_unused_session_expires`; Compose `s_worker_killed_mid_submit` |
| A runner/worker Playwright mismatch would surface as a confusing protocol error | `test_driver_version_mismatch_is_refused_with_reason` |
| The self-check inspected every Chromium on the host, and found none of its own when it was PID 1 | `test_self_check_finds_its_browsers_when_the_runner_is_pid_1` (local, root); Compose `s_sandbox_selfcheck` |
| A test race: the lease was expired while the worker still held the row lock | `test_no_takeover_while_old_worker_may_have_disclosed` (waits for the fault point's marker) |

**Requirement → implementation → test → result (all on `9d6bd7e`, CI #24 unless noted)**

| Requirement | Implementation | Test(s) | Result | Limitation |
|---|---|---|---|---|
| Unprivileged browser user; Chromium sandbox enabled and verified | uid 10002; `chromiumSandbox: true`; self-check of its own renderers (`Seccomp: 2`, no `--no-sandbox`, no uid 0) | `s_container_configuration`, `s_sandbox_selfcheck`, `test_runner_verified_its_own_sandbox` | pass (renderer uid 10002, seccomp 2, NoNewPrivs 1) | verified on GitHub ubuntu-24.04 only |
| Seccomp + capabilities; no privileged mode, socket, host network or mounts | Docker default seccomp + clone/unshare/setns/chroot; `cap_drop: ALL`; no-new-privileges | `s_container_configuration` (docker inspect), probe (CapEff/CapBnd 0) | pass | seccomp rule provenance in `browser/README.md` |
| Fail closed if isolation cannot start | 503 from runner → `IsolationUnavailable` → failed_safe | `s_sandbox_unavailable` (unmodified Docker seccomp), `s_runner_unavailable`, `test_container_mode_fails_closed_when_the_runner_is_unavailable` | pass, 0 disclosures | — |
| No credentials or app files in the browser environment | minimal env; no volumes | `s_browser_container_probe` + insecure control `s_probe_detects_an_insecure_configuration` | pass; the control flagged fake env, mounted secret, reachable DB/Redis | the runner's own token is present (authenticates the worker only) |
| Default-deny egress at the infrastructure boundary | internal networks; session proxy (exact host:port, public IPs unless fixture, connect to the checked IP, 407 without a session) | probe (DNS EAI_AGAIN; DB/Redis/API/web/receiver/canary unresolvable; metadata/internet ENETUNREACH; worker refused); `s_infrastructure_only_egress`; `test_container_boundary_alone_blocks_egress_without_interception` | pass; with interception off: 0 blocked in-process, canary 0 hits, proxy denied `10.0.0.1:80`, `169.254.169.254:80`, `::1:80`, `canary:8798` | proxy control port reachable from the browser network (token-gated, 401) |
| Narrow control channel; stale authority revoked | loopback browser server; relay needs runner token + session secret; single connection; close on disconnect | runner tests above; `s_worker_killed_mid_submit` | pass: sessions 0 within 20 s after the worker kill | liveness is TCP-based |
| CPU, memory, process and time limits | 1536 MiB / 1.5 CPU / 512 pids / per-session 45 s (test) or 600 s | `s_memory_exhaustion`, `s_session_time_limit` | pass: hog page → failed_safe, 0 accepted, container OOM-killed and restarted; slow page → failed_safe, 0 disclosures | the memory limit is per container, so a hog ends the whole runner (one session at a time) |
| No resend after ambiguous outcomes; duplicate delivery ignored | unchanged state machine | `s_unknown_then_duplicate_delivery`, `s_runner_lost_during_submission`, `s_worker_killed_mid_submit` | pass; receiver acceptances 1 each, attempt `unknown`, `retry_count` 0 | not exactly-once: an uncertain outcome is quarantined, not proven |
| Full approved path | prepare → approve → queue → isolated browser → upload → code checkpoint → submit | `s_greenhouse_security_code_flow` | confirmed; acceptances 0 → 1 (none before the code); 1 upload with the approved digest | synthetic code step (unverified for real Greenhouse) |
| No secrets in logs | logging of ids only | `s_greenhouse_security_code_flow` log scan (code, runner, control, admin tokens across all services) | pass | — |
| Cleanup and evidence retention | session close on exit; `retain_until` on evidence; deletion API | same scenario; `test_evidence_lifecycle.py` | pass: sessions 0, no profile in `/tmp`, evidence deleted (200) | — |

**Receiver counts (Compose, CI #24, receiver ledger)**

| Scenario | Accepted | Other |
|---|---|---|
| Greenhouse security-code flow | 0 before the code, 1 after | 1 upload disclosure, digest = approved document |
| Hostile page | 1 | canary 0 hits; 7 requests blocked in-process |
| Interception off | 1 | canary 0 hits; 4 destinations denied by the proxy |
| Accepted, response dropped, then a duplicate delivery | 1 | attempt `unknown`, delivery ignored |
| Runner killed mid-submit | 1 | attempt `unknown`, never resent |
| Worker killed mid-submit | 1 | swept to `unknown`, `retry_count` 0 |
| Runner down / sandbox unavailable / memory hog / session limit | 0 | 0 disclosures, failed_safe |

Local runs (cloud sandbox, no Docker daemon):
- `uv run pytest` on `dcc4500`: 229 passed, 1 failed. The failure was the canary port reuse,
  fixed in `a073a95`.
- `tests/test_container_runner.py` on `9d6bd7e`: 14 passed (includes the PID 1 test, which runs
  here as root).
- ruff check and format: clean.

## Milestone 2 closeout and first ATS adapter (2026-10-20)

**Revisions and CI** (links: `https://github.com/KevinD003/AutoApply/actions/runs/<id>`)

| Revision | What | CI run (all jobs) | Backend tests | e2e | Docker smoke |
|---|---|---|---|---|---|
| `c7c4109` | milestone 2 as handed over | #13 [39359765119](https://github.com/KevinD003/AutoApply/actions/runs/39359765119): backend, frontend, docker-smoke passed | 188 passed, 0 skipped (CI log) | step passed | passed |
| `0fca81b` | closeout fixes (below) | #14 [39363852006](https://github.com/KevinD003/AutoApply/actions/runs/39363852006): all passed | 193 passed locally; CI step passed | 22 passed locally (see caveat) | passed in CI |
| `cc6c1da` | Greenhouse adapter + docs | #15 [39365659479](https://github.com/KevinD003/AutoApply/actions/runs/39365659479): backend, frontend (e2e), docker-smoke all passed | 212 passed, 0 skipped (local, `pytest -rs`) | 24 passed locally (desktop + mobile) | passed in CI |

Job links for #13: [backend](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422934216),
[frontend](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422933900),
[docker-smoke](https://github.com/KevinD003/AutoApply/actions/runs/39359765119/job/118422934152).

Local vs CI:
- **Sandbox (local):** runs as root, so the browser namespaces are created without a user
  namespace for the outer layer. PostgreSQL 16 is a disposable `initdb` cluster. Chromium is
  /opt/pw-browsers build 1194. No Docker daemon.
- **CI:** a non-root runner, using unprivileged user namespaces after the AppArmor sysctl
  (a CI host setting). PostgreSQL and Redis run as service containers (backend Redis from
  apt). Chromium is installed by Playwright. The real Docker daemon is used for the smoke
  test.
- **Caveat:** the local e2e run for `0fca81b` overlapped edits to backend files; its servers
  had loaded most code at start. CI #14 is the authoritative e2e result for that revision.
- **Docker:** Smoke-tested in GitHub CI; not yet verified on the user's Mac.

**Closeout findings (each with a test that failed first or that pins existing behaviour)**

| # | Finding | Kind | Fix | Test |
|---|---|---|---|---|
| C1 | Chromium inherited the worker's working directory (still the hidden backend tree, because a mount does not move a process already inside it) and descriptors above 3/4 | real gap, reproduced (`CWD_LEAK`, `FD_LEAK` before the fix) | chdir to the work dir; close fds ≥ 5 before exec | `test_browser_cannot_see_worker_process_secrets_or_other_attempts` |
| C2 | A browser that fails to start inside the namespaces surfaced as a generic error | behaviour was already a safe stop; made explicit | launch failure → `IsolationUnavailable` → failed_safe, never an unisolated retry | `test_isolation_failure_refuses_instead_of_browsing_unrestricted[unshare_rejects, unshare_missing]` |
| C3 | Work directories of hard-killed workers were left behind | real (observed) | PID-tagged work dirs; the sweep task removes those whose PID is gone | `test_stale_workdirs_of_dead_workers_are_removed` |
| C4 | Proxy DNS and CONNECT had no direct tests | evidence gap | none needed | `test_proxy_checks_every_resolved_address_and_connects_to_the_checked_one`, `test_proxy_connect_and_absolute_http_follow_the_same_policy` |
| C5 | Cancel during a code wait was not tested | evidence gap | none needed (already refused) | code-wait regression: cancel 409, one attempt |
| C6 | Smoke checks had no test of their failure paths | evidence gap | `scripts/smoke_lib.sh` | `scripts/test_smoke_lib.sh` (CI): request failure, HTTP error, wrong content, exited container, docker failing |

**Regression evidence re-verified (implementation · test · result)**

| Area | Implementation | Tests | Limitation |
|---|---|---|---|
| Checkpoint state frozen | `package.execution_owns_state` in `ensure_current` and the user transition route | `test_reads_and_user_actions_during_code_wait_cannot_reopen_submission` (package reads, user transitions incl. cancel → 409, one attempt); e2e reload during the code wait | the code wait reuses `needs_user_action`; the guard, not a separate state, keeps the meanings apart |
| Duplicate POST at teardown | non-GET/HEAD → `route.continue_()`; failed GET fetch → abort | `test_closing_the_browser_mid_submit_never_resends[netns,off]` (fails on the old code; local server counts POSTs) + the receiver-ledger e2e that first showed 2 acceptances | observed with Playwright Python 1.56.0 / Chromium 141, not claimed for Playwright in general. Not exactly-once: an accepted-but-unanswered submit is `unknown` and reconciled; broker redelivery is refused by the claim CAS (`test_redelivery_after_*`) |
| HTTP methods and redirects | GET/HEAD fetched with hops checked; other methods sent by the browser, hops checked by the proxy (host:port); no retries after the send gate; ambiguous responses → unknown | isolation and failure-mode tests | a POST redirect to another path on the same host:port is followed |
| UI state | `ExecutionCard` polls only while active, then refreshes once | e2e: no attempt requests for 4 s after the final state; no Cancel after `unknown`; desktop + mobile for queueing, verification, cancel, unknown, reconciliation | — |
| Protected mutations | send gate rebuilds content under the app row lock in REPEATABLE READ and compares hashes, so every mutation path is checked by the same validated-versioning step whether or not the path locks | `test_every_protected_mutation_stops_a_running_attempt[10 paths]`, approve-vs-edit interleavings, `test_restoring_a_fact_does_not_resurrect_a_revoked_approval` | a mutation committed after the gate does not change what is sent (`test_mutations_after_send_gate_do_not_change_what_was_sent`) |
| Filled values and bytes | readback of every control; disclosure digest = approved digest = receiver digest | tamper tests (4); `test_autosave_and_upload_are_counted_separately_from_acceptance`; Greenhouse full-run test | — |
| Material form change | fingerprint check before disclosure and after fill | `conditional_field` mode; Greenhouse `gh_drift` | — |
| Tenancy of evidence and checkpoints | owner checks | `test_execution_resources_are_tenant_bound`, cross-user code 404, evidence deletion 404 | — |
| Retention and leaks | daily purge; user deletion; leak scans of DB rows and real worker logs | `test_retention_purge`, `test_no_secrets_in_real_worker_logs`, code-checkpoint leak scan | CI debug artifacts (Playwright traces of the *test* browser, uploaded only on failure, 7-day retention) contain what the test typed, including synthetic codes; they are not scanned. Never run e2e with real data |

**First adapter: Greenhouse-hosted (fixture approximation)** — `backend/tests/test_greenhouse_adapter.py`
(19 tests, all real processes against the receiver; nothing simulated except the fixture itself)

| Requirement | Test | Receiver ledger |
|---|---|---|
| Posting identity (real hosts, embed, fixture path; fixture path on a real host is not a fixture) | `test_posting_identity_from_real_and_fixture_urls` | — |
| Exact wording, help, options, required, types | `test_schema_keeps_exact_wording_help_options_and_required` | — |
| Hidden and unknown controls → unsupported | `test_hidden_and_unknown_controls_become_unsupported` | — |
| JSON vs page cross-check (extra field, reworded question) | `test_job_data_and_page_must_agree`, `test_capture_refused_when_page_disagrees_with_job_data` | — |
| Form capture refuses real posts | `test_real_greenhouse_posts_are_not_read` | — |
| Unsupported required control is a checkpoint (no input, no approval) | `test_required_unsupported_control_is_a_checkpoint` | — |
| Conditional question not asked / asked and required | `test_conditional_question_follows_its_trigger`, `test_conditional_question_is_filled_when_it_applies` | 1 acceptance with the conditional answer |
| Full run: exact values, withheld sensitive answer blank, attachment disclosed once with the approved digest, confirmation-page evidence | `test_full_run_is_confirmed_and_sends_exactly_the_approved_values` | 1 acceptance, 1 upload |
| Security code: wrong then right; not accepted before the code | `test_security_code_wrong_then_right` (real worker process) | 0 before, 1 after |
| CAPTCHA → stop before disclosure | `test_captcha_stops_before_anything_is_disclosed` | 0 disclosures, 0 accepted |
| Form changed after approval → stop before disclosure | `test_form_changed_after_approval_stops_before_disclosure` | 0, 0 |
| Rejected / unknown / dropped / upload failure; never resent | `test_outcome_classification[5 modes]` | 0 / 0 / 1 / 1 / 0, unchanged after a second delivery |
| Capability flags | `test_capability_flags` | — |
| UI: read form, review exact wording, conditional "not asked", approve, submit | e2e "Greenhouse-style form: …" (desktop + mobile) | +1 acceptance, 1 attempt |

Fixture compatibility only: the fixture is an approximation built from public documentation,
not Greenhouse markup; no real employer form has been tested.

## Validation milestone 2 (submission UI, real failures, isolation)

Each row names the test, whether the failure is **real** (a real process, broker, browser or
namespace really did it) or **simulated** (we edited the database or injected a fault), and
the outcome counted by the receiver's ledger.

**Revision binding**

| Item | Value |
|---|---|
| Baseline | `ad57210` (CI run #4: all jobs green) |
| Final code commit | `bae5120` |
| CI on that commit | run #12 (`bae5120`): backend, frontend (all e2e), docker-smoke **all passed**. Earlier runs on this work: #6 (`e11484d`) backend failed (no `redis-server` binary), #9 (`292ecb9`) backend and frontend passed but docker-smoke failed (web container exited), #10 (`6c850d7`) docker-smoke failed at the worker-ping step (shell pipeline bug), #11 (`416cf70`) all passed |
| Diff since baseline | `git diff --stat ad57210 bae5120`: 35 files changed, 2405 insertions, 134 deletions |
| Local checks on final code | `ruff check` + `ruff format --check` clean; `pytest`: 188 passed; `tsc --noEmit` + `npm run lint` clean; `npx playwright test`: 22 passed (desktop + mobile). Local runs on `292ecb9`; later commits changed only the Next config file type and the smoke script, and CI ran everything on `bae5120` |

**Defects found by this round (all fixed, each with a test that failed first)**

| # | Defect | How it was found | Fix | Regression test |
|---|---|---|---|---|
| B1 | During a verification-code wait, the review page's package read re-settled the application from `needs_user_action` to `awaiting_approval` while the approval was still valid. **Submit was re-enabled after the data had been sent**, and the worker crashed on an illegal transition. | browser test (code flow) | `package.execution_owns_state`: no re-settling and no user transitions (409) while a worker holds the attempt | `test_reads_and_user_actions_during_code_wait_cannot_reopen_submission`; e2e reload during the code wait |
| B2 | A submit POST was sent **twice**. The in-process route used `route.fetch` + `fulfill`; when the worker gave up and closed the browser, Playwright resumed the paused original request. The receiver counted 2 acceptances for 1 attempt. | browser test (unknown outcome); reproduced with a stand-alone script | non-idempotent requests go out once via `continue_()` (hops checked by the egress proxy); a failed GET fetch aborts | `test_closing_the_browser_mid_submit_never_resends[netns,off]` |
| B3 | Submission card re-fetched attempts in a tight loop (the effect depended on its own result) and left the status stale after the final state (Cancel button still shown) | browser test | poll only while an attempt is active; refresh the application once at the end | e2e: no attempt requests in 4 s after the final state; no Cancel button after `unknown` |
| B4 | e2e worker supervisor started Celery in its own session, so Playwright's teardown left the worker running | stale processes after a run | worker stays in the supervisor's process group | — (harness) |
| B6 | Docker web container exited at start: `next.config.ts` needs TypeScript, absent from the production image; the auto-install failed as the non-root user. A global TypeScript in this sandbox had masked it locally | CI docker-smoke logs | `next.config.mjs` | CI `docker-smoke` |
| B5 | CI run #2 Phase A failure (likely cause; traces of that run were not kept): the test filled the login form's identically labelled fields during a slow client-side navigation to /register | reproduced deterministically with a 1.5 s route delay | wait for the URL and the register button before filling | `navigation-race.spec.ts` |

**Matrix**

| Requirement | Test(s) | Real / simulated | Result (receiver ledger) |
|---|---|---|---|
| Approve, queue, double-click | `submission.spec.ts` "approve, double-click submit…" (desktop + mobile) | real UI, API, Celery worker, isolated browser, receiver | 1 acceptance, 1 attempt; polling stops |
| Reload during execution | "reload during execution…" | real | 1 attempt, 1 acceptance |
| Revoked / expired approval | "revoked and expired approvals…" | revoke real; **expiry simulated** (`expires_at` set in the past) | Submit disabled; API 409; 0 attempts |
| Cancel before dispatch | "cancel before dispatch…" (receiver delays the form 10 s) | real | cancelled; 0 accepted, 0 disclosures after a bounded 12 s observation window |
| Cancel refused after dispatch | "cancel refused once the submit step has begun" (receiver delays 8 s) | real | UI shows the refusal; 1 accepted |
| Codes: wrong, replay, other user, right; reload while waiting | "verification codes…" | real | replay 409, other user 404, Submit stays closed after reload; 1 accepted |
| Expired code | "expired verification…" | **expiry simulated** (`expires_at` in the past) | abandoned; 0 accepted |
| Unknown outcome, reconciliation | "unknown outcome is reconciled…" (receiver accepts, never replies) | real timeout | `submitted_unconfirmed` → reconciled; 1 accepted, 1 attempt |
| Readback: text cleared, select changed, checkbox unchecked, file lost | `test_page_altering_a_filled_value_stops_before_submit[text,select,checkbox,file]` (receiver page script alters the control) | real browser and page | abandoned before send; mismatch key recorded (no values); 0 accepted |
| Broker outage | `test_real_broker_outage_around_outbox_publication`, `test_worker_survives_broker_restart` | real: the disposable Redis process (port 6391) is stopped and restarted empty | outbox keeps the message, published once on recovery; 1 accepted |
| Redelivery: accepted, response lost | `test_redelivery_after_accepted_but_response_lost` | real `kill -9` of the worker mid-send; real kombu redelivery after a 5 s visibility timeout (test-only; production 3600 s); **dead worker's lease expiry simulated** before the sweep | redelivered task refused by the claim CAS; 1 accepted; `unknown` → `submitted_unconfirmed` |
| Redelivery: crash after acceptance | `test_redelivery_after_crash_after_acceptance` | worker blocked by an injected fault after the receipt, then really killed; rest as above | 1 accepted, no second send |
| Every protected mutation path while running | `test_every_protected_mutation_stops_a_running_attempt[answer, answer_bank_delete, consent, document_version, draft_accept, form_version, job_destination, preferences, profile_name, work_authorization]` | real worker process paused after filling; mutation through the public API | abandoned at the send gate; 0 accepted |
| Unrelated edit / edit after the send gate | `test_unrelated_edit_does_not_stop_a_running_attempt`, `test_mutations_after_send_gate_do_not_change_what_was_sent` | real | confirmed; the approved snapshot was sent |
| Uploads and autosave counted separately | `test_autosave_and_upload_are_counted_separately_from_acceptance` | real | 1 upload (digest equals the approved document), ≥5 autosaves, 1 acceptance |
| Revoking cannot recall sent data | `test_revoking_after_disclosure_cannot_recall_transmitted_data` | real paused process | abandoned; upload and autosaves stay in the ledger; 0 accepted |
| Stale worker: paused process vs ownership change | `test_stale_worker_with_real_lease_expiry` (3 s lease, **real** wall-clock expiry) vs `test_old_worker_cannot_continue_after_lease_loss` (**simulated** expiry) | as stated | old worker: `lost_authority`; 1 accepted |
| Browser network isolation without interception | `test_isolation_alone_blocks_egress_without_interception`, `test_namespace_alone_has_no_network`, `test_loopback_destination_denied_without_fixture_exception`, `test_proxy_policy_unit`, `test_free_port_helper_is_not_reachable_from_namespace` | real namespaces, real Chromium, real proxy | canary 0 hits; every off-destination host:port in the proxy's deny log |
| Separation from orchestrator credentials | `test_browser_cannot_see_worker_process_secrets_or_other_attempts`, `test_default_hidden_paths_cover_code_config_and_storage`, `test_refuses_a_browser_binary_inside_a_hidden_path` | real namespaces; synthetic marker files only | worker's /proc entry, hidden dirs and files, and other attempts' work dirs invisible; `umount` refused inside |
| Production cannot disable isolation | `test_production_refuses_to_run_without_isolation`; no UI or API setting exists | real | failed_safe; 0 disclosures |
| Full run through the proxy | `test_full_run_goes_through_the_proxy` + every e2e submission | real | confirmed; 1 accepted |
| Evidence retention and deletion | `test_retention_purge`, `test_user_can_delete_evidence_and_others_cannot`, `test_cannot_delete_evidence_while_running` | real (retention date set in the past) | purged; other users get 404; 409 while running |
| Fake secrets not in logs | `test_no_secrets_in_real_worker_logs` (real Celery worker at DEBUG), leak scan in the code-checkpoint test | real | 0 hits |
| CI #2 investigation | `navigation-race.spec.ts` | real slow navigation (route delay) | B5 reproduced deterministically and fixed; run #2's traces were not kept, so it is the likely, not the proven, cause of that run; no retries or sleeps added |
| Docker smoke | CI job `docker-smoke` (`scripts/docker-smoke.sh`) | real Docker on GitHub's runner | **passed** in CI run #12: build, migrations on start, register/session, web pages and API proxy, worker answers a broker ping, data survives a backend restart. Two defects found on the way: the web image could not load `next.config.ts` without TypeScript (fixed with `.mjs`), and a `| grep -q` pipeline failed the step under pipefail. Never run in this sandbox (no Docker daemon) |

## Earlier Phase C rows (commit `ebb3e3b`; superseded cells marked)

| Requirement | Implementation | Tests | Result | Remaining limit |
|---|---|---|---|---|
| Manifest binds owner, destination origin + submit endpoint, form fingerprint, wording/help/options/required, typed answers, document versions + byte digests, consents, policy version | `preparation/package.py` (`SCHEMA_VERSION = 2`) | `test_approval_hardening::test_manifest_binds_owner_destination_documents_and_policy` | pass | Legal text is the field label; no separate legal-document versioning |
| Client-supplied hash cannot approve | `package.approve` recomputes server-side | `test_client_hash_alone_cannot_approve` | pass | — |
| Approval expiry | `PackageApproval.expires_at`, `active_approval` | `test_approval_expires` | pass | Default 72h, not user-configurable |
| Monotonic revocation; restore doesn't resurrect | new version per change; approvals never un-invalidated | `test_restoring_a_fact_does_not_resurrect_a_revoked_approval` | pass | — |
| false / null / decline / blank are distinct | resolver values; hash covers them | `test_false_null_and_decline_are_distinct`, `test_empty_text_is_rejected_not_stored_as_answer` | pass | — |
| Draft dependencies registered | `ApplicationInput.meta`, stale-draft check | `test_accepted_draft_depends_on_its_facts` (**test-only fake provider**) | pass | No real LLM provider exists |
| Approve vs protected edit (deterministic interleaving) | row lock + server rebuild | `test_edit_committed_between_review_and_approve_blocks_approval`, `test_edit_committed_after_approval_invalidates_before_queue` | pass | — |
| Concurrent rebuilds | `lock_application` in `ensure_current` | `test_concurrent_rebuilds_write_one_version` | pass | — |
| Queue/claim vs revocation | claim re-checks approval under lock | `test_revocation_before_claim`, `test_revocation_while_preparing_stops_before_disclosure`, `test_revocation_after_disclosure_stops_before_send` | pass, oracle 0 | — |
| Worker preparing vs document change | send gate rebuilds content | `test_document_change_after_approval_stops_send` | pass, oracle 0 | Documents cannot be deleted at all (no endpoint) |
| Cancellation vs final dispatch | cancel and send gate share locks | `test_cancel_before_send_gate_wins` (oracle 0), `test_cancel_after_send_gate_is_refused` (oracle 1) | pass | After the gate, cancel is refused; data in flight cannot be recalled |
| Form schema change after approval | fingerprint check before and after fill | `test_receiver_failure_modes[conditional_field]` | pass, oracle 0 accepted, 0 disclosures | — |
| Disclosure authority separate from submit | `gate_before_disclosure` / `gate_before_send`; disclosure evidence | `test_crash_after_disclosure_is_not_retried` (oracle: 1 upload, 0 accepted) | pass | Fill on an autosaving form counts as disclosure; we assume any fill may transmit |
| Duplicate deliveries | claim CAS | `test_duplicate_delivery_sequential_is_ignored`, `test_competing_workers_on_one_attempt_send_once` (non-idempotent receiver, 3 processes), Celery `test_duplicate_deliveries_through_celery_send_once` (3 deliveries) | pass, oracle 1 | — |
| One active attempt per application | partial unique index | `test_second_active_attempt_is_blocked_by_database` | pass | — |
| Crash before external write | sweeper re-pends (bounded) | `test_crash_before_any_external_write_is_retried_once_safely`, Celery `test_death_before_any_write_recovers_through_outbox` | pass, oracle 1 | — |
| Crash at final-send boundary | `sending` → sweep → `unknown` | `test_crash_at_final_send_boundary_becomes_unknown`, Celery `test_worker_process_death_at_send_is_not_redelivered` | pass, oracle 0, no redelivery | — |
| Accepted, response dropped | submit timeout → `unknown` | `test_accepted_but_response_dropped` | pass, oracle 1 | — |
| Crash after receipt, before local commit | sweep → `unknown`; reconcile | `test_crash_after_receipt_before_local_commit` | pass, oracle 1 | Receipt lost locally; user reconciles |
| Code accepted, reply lost (D50) | the code step's timeout → `unknown`; the worker may move `needs_user_action` → `submitted_unconfirmed` | `test_an_unknown_result_after_the_code_is_quarantined_and_never_sent_again` (receiver `verify_drop`) | pass, oracle 1, no second send in a 3 s window, re-queue refused | Before D50 the transition was refused: the worker crashed and the application stayed "needs your action" although the employer had it |
| Worker died in the code wait (D50) | sweep → `unknown`, checkpoint expired, held code erased | `test_the_sweeper_quarantines_a_worker_that_died_waiting_for_the_code` (another user's stale attempt re-pended in the same sweep) | pass, oracle 0 accepted, the challenge never completed | Before D50 the sweep raised and rolled back every stale attempt in its batch, every 15 s |
| One stale attempt cannot be recovered (D50) | a savepoint per attempt; counted in `errors` | `test_one_row_that_cannot_be_recovered_does_not_stop_the_others` (a database error injected after the row's changes) | pass: the others recovered, the failing one unchanged and recovered by the next sweep | — |
| No transition listed twice (D50) | AST scan of every dict literal in `app/` | `test_no_dict_literal_in_the_backend_repeats_a_key` | pass | ruff checks literal keys only |
| Ambiguous server errors | → `unknown` | `test_receiver_failure_modes[error_before_accept / error_after_accept]` | pass, oracle 0 / 1 | Both look identical from outside, so both stay unknown |
| Validation failure, expired session, upload failure, slow reply | → `rejected` / `abandoned` / `confirmed` | parametrized failure-mode tests, `test_slow_but_successful_response` | pass | — |
| Stale worker after lease loss | fencing generation, heartbeat, gate | `test_old_worker_cannot_continue_after_lease_loss` (oracle 1), `test_no_takeover_while_old_worker_may_have_disclosed` (oracle 0) | pass | Old browser is closed when its worker detects lost authority; no OS-level kill of a hung browser |
| Broker outage after DB commit | transactional outbox | `test_broker_outage_after_commit_loses_nothing` | pass | **Mock** here; superseded by the real outage tests above |
| Celery settings reviewed | `app/worker.py` docstring | Celery tests above | pass | Redelivery now exercised (above), with a 5 s test-only visibility timeout |
| Read back actual control values | `FixtureAtsAdapter.readback` | every confirmed run; oracle field values checked in `test_happy_path_submits_once_with_receipt` | pass | Forced for text, select, checkbox and file (above) |
| Capability flags | `execution/policy.py::CAPABILITIES` | `GET /api/execution/capabilities` (no dedicated test) | implemented | Only `fixture_ats` exists |
| Real employer destinations refused | `policy.adapter_for` | `test_real_employer_destination_is_refused_at_queue` | pass | — |
| Production rejects fixture URLs | `is_fixture_origin` ignores settings in production | `test_production_rejects_fixture_destinations` | pass | — |
| Browser egress | route allow-list, redirect check, service workers blocked, resolver rules, pop-ups closed | `test_browser_cannot_reach_other_origins` (img, iframe, fetch, beacon, single and chained redirects to another port; metadata, RFC1918, IPv6 loopback) | pass, canary 0 hits | **Found and fixed a redirect bypass.** Superseded: network namespace + egress proxy (above) |
| Verification-code checkpoints | `Checkpoint`, `submit_code`, `take_code` | `test_code_checkpoint_wrong_then_right_code_and_replay`, `..._expiry_...`, `test_too_many_wrong_codes` | pass | Worker holds a slot while waiting (bounded by TTL) |
| No secrets in artifacts | evidence minimization; codes erased | leak scan inside the code-checkpoint test (fake OTP + fake secret; evidence, events, audit, timeline, outbox, checkpoints, attempts, worker stdout/stderr) | pass, 0 hits | Broker payloads checked by construction (ids only), not scanned |
| Tenancy for Phase B/C resources | owner checks; worker derives tenant from attempt | `test_tenant_isolation_for_preparation`, `test_execution_resources_are_tenant_bound`, `test_worker_derives_tenant_from_attempt_not_payload`, code checkpoint cross-user check | pass | — |
| Migrations | Alembic | `test_migrations.py`: empty→head, populated Phase A→head with data preserved, downgrade/re-upgrade (disposable DB) | pass | Phase A's downgrade was edited after the fact (not deployed anywhere); future fixes use new migrations |
| Test DB safety | conftest refuses non-`*_test` DBs | — | implemented | — |
| CI | `.github/workflows/ci.yml` | see implementation-status for the run result | — | — |
| Docker | `docker-compose.yml` | CI `docker-smoke` | Smoke-tested in GitHub CI; not yet verified on the user's Mac. | no Docker daemon in this sandbox |

## Not credited

- REA: only `--help` was run; no analysis.
- Tsenta, Gmail, Freehire, LLM providers: no access, no implementation, no tests.
- Execution UI: browser-tested in milestone 2 (above).
- Greenhouse or any other real ATS: proposal only (`docs/first-adapter-proposal.md`).
