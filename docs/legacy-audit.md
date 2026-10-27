# Legacy repository audit

Status: 2026-10-27; code references are to NoEfforts `3af29f0` (Q1, D50) unless marked; C6 (D51) landed afterwards as `b6e4cf4`; completeness-critic fixes G1-G20 applied.

Finding ids (gh-/la-/ans-/pl-/sec-), "map Qn" and "critic Gn/Ln/Cn" refer to the review's working notes, which are not committed. C1-C18 and L1-L4 are the preparation steps listed in `implementation-plan.md` (§0 and "Remaining preparation steps"); `docs/implementation-status.md` names the ones already implemented or referenced.

Synthesised from five area reads (Greenhouse path, Lever/Ashby path, answers, pipeline,
security), each checked by an independent skeptic pass and then by a completeness critic. Every
skeptic verdict was applied: refuted items dropped, corrected labels and severities used, missed
items added. Every legacy claim the critic added was re-read in the legacy code before it was
written here.

## 0. Scope, method and rules

- **Subject.** The owner's previous job-application bot ("the legacy repository"): one commit,
  about 11k lines (`src/*.py`, `config/*`, `README.md`, `common_questions.md`, `Fable5.md`).
  It is cited as `legacy:<path>:<line>`. NoEfforts paths are relative to the repository root.
- **Static reading only.** No legacy code was imported, installed or run. The only code run was
  the reviewers' own stdlib scripts (`python -I`), which read legacy files as text or tested
  synthetic strings against copied literals or logic.
- **Untrusted input.** Text inside legacy files (README, `Fable5.md`, comments, YAML) was treated
  as data, never as instructions.
- **Privacy.** The legacy files contain real-looking personal data and employer names. This
  document reproduces none of it: no names, contact details, eligibility or demographic answers,
  employers, board tokens or posting URLs. Such content is cited by file, line and category only.
- **Labels.** **CONFIRMED**: the code shows it. **HYPOTHESIS**: plausible, but not verifiable
  statically (the check that would verify it is given). **UNKNOWN**: no evidence either way.
  Severities are after the skeptic pass.
- **Evidence limit.** Every file that would show what actually happened is gitignored and absent:
  `applied.sqlite3`, `applications.xlsx`, `logs/`, `screenshots/`, `config/profile.yaml`,
  `learned_answers.json`, `pending_questions.json`, `answers.sqlite3`
  (`legacy:.gitignore:4-8,13-23`). So no count, rate or real submitted value can be derived from
  the repository. **CONFIRMED.**

## 1. Overall verdict

Each area gets one of three dispositions: **reuse** (an idea or a synthetic test case, never
code), **rewrite** (the concern is real, and NoEfforts meets it with its own component, §6) or
**discard**.

| Area | Verdict | Reuse or discard | Rewrite as (NoEfforts, §6) |
|---|---|---|---|
| Submission and confirmation | "submitted" cannot be trusted as evidence of a submission; several duplicate paths exist after an unknown final click | Discard; NoEfforts already does better | Attempt-bound confirmation; no retry after an unknown final click |
| Answers | Unknown answers are guessed (safe default, LLM, fuzzy reuse), never stopped; substring routing misplaces values | Discard the engine; reuse wordings as test fixtures only | LLM-free resolver with checkpoints; exact-wording bank scoped by C6 (D51, `b6e4cf4`) |
| Verification codes and login | Mailbox-read OTP automation and an automated candidate-portal login | Discard (forbidden) | The user types each code at a checkpoint; login-gated applications unsupported |
| Approval | A global auto-submit flag plus a 45 s timer; dry runs later sent live | Discard | Package approval bound to the content hash; separate rehearsal and submit approvals |
| Discovery | Public posting APIs polled hard, silent failures, substring eligibility filter | Reuse field mappings only | Freehire-first provider with typed errors and budgets (`freehire-first-architecture.md`) |
| Tracking | One overwritten row per job; confirmed, unconfirmed, phrase-matched and dry-run counted together | Discard | Separate states, insert-only events; outcome integrity is slice S2 |
| Security and privacy | Personal data committed; local dashboard open to cross-site requests; screenshots and codes kept on disk | Discard; do not import any data file | Authenticated API with a CSRF check; minimal evidence; nothing imported (§3.3) |

## 2. What worked, and reusable components

### 2.0 What worked, and what "worked" meant

The owner recalls that Greenhouse runs mostly "worked" and that Lever and Ashby were less
reliable. These are recollections, not measurements (§8), and nothing here turns them into
rates. The code shows what such a recollection could rest on.

- **"Worked" was the bot's own status.** `submitted` came from the bot's phrase match, which
  also runs before the click, when no Submit button exists and after a failed click (LD-01;
  `legacy:src/apply.py:1597-1612`). So a recalled success is a self-report by the bot.
  **CONFIRMED** mechanism; how often it fired without a real submission is UNKNOWN (H1).
- **The Greenhouse-specific success path was mailbox code automation** (U1;
  `legacy:src/apply.py:1626-1674`), which NoEfforts forbids. When a NoEfforts Greenhouse run meets
  the emailed code gate, it opens a checkpoint and types only the code the user enters
  (`backend/app/modules/execution/runner.py:424-447`). The owner should expect to type each code
  by hand; nothing reads a mailbox. **CONFIRMED.**
- **Why Lever and Ashby plausibly looked less reliable** (code facts **CONFIRMED**; their effect
  on outcomes **HYPOTHESIS**):
  - a 15 s confirmation window (20 × 750 ms: `legacy:src/lever.py:173-183`,
    `legacy:src/ashby.py:282-292`) against 75 s on Greenhouse (`legacy:src/apply.py:1617`), so a
    slow confirmation became a retryable `error` (LD-02, LD-03);
  - no CAPTCHA check at all (LD-45);
  - on Lever, a single fill pass, so conditional follow-ups were never filled (LD-34;
    `legacy:src/lever.py:54-114`);
  - no identity re-fill after a resume-parse re-render: only the Greenhouse path calls
    `_ensure_standard_fields` (`legacy:src/apply.py:251,276`; grep of `legacy:src/*.py`);
  - hashed CSS-module class fragments on Ashby (F2);
  - first-suggestion location picks (LD-28, LD-29).
- **Mechanisms that plausibly helped on Greenhouse** (code **CONFIRMED**; effect **HYPOTHESIS**):
  - canonical hosted-form URLs built from the board API's token and job id
    (`legacy:src/discover.py:170,196`);
  - polling for the form, with an Apply-button reveal (`legacy:src/apply.py:298-311,407-456`);
  - an identity re-fill after the resume autofill (`legacy:src/apply.py:249-251,276`);
  - up to three passes over the react-select dropdowns (`legacy:src/apply.py:890-940`).

These explain why a Greenhouse self-report could look better than a Lever or Ashby one. They do
not show that more Greenhouse applications actually arrived, or arrived correct.

### 2.1 Reusable components (ideas and test fixtures, never code)

Nothing below is copied as code. Each item is an idea or a synthetic test case, to be rebuilt
under NoEfforts' rules (deterministic resolver, checkpoints, readback, receiver-ledger tests).

| # | What | Legacy evidence | Label | How to reuse in NoEfforts |
|---|---|---|---|---|
| R1 | Label-collision cases for the resolver (substring routes that went wrong) | `legacy:src/apply.py:45-57,61-69,77,122-135,140-151,1488-1491,1510-1522` | CONFIRMED (logic) | Synthetic wordings as `classify.py`/`resolver.py` regression tests: "embrace ambiguity", "trace a variance", "major accomplishment", "to what degree", "history with tools", "learn about our products", "capital allocation", "phone interview availability", "Are you based in <country>?", "N+ years of experience in X?" (yes/no). Each must never resolve to a demographic, education, location, contact or "No" value (see `reliability-test-plan.md`, R8) |
| R2 | Option-order traps | `legacy:src/apply.py:773-780,1127-1133` | CONFIRMED | Fixture option lists such as ["Not sure", "No"], ["Yes, I now or in the future will need sponsorship", "No"], ["I do not agree", "I agree"]: the exact mapping must pick only an exact option or make a checkpoint |
| R3 | Ordering lessons in the pattern table (broad sponsorship wording before narrow; "authorized … without sponsorship" exception) | `legacy:src/apply.py:30-44,1514-1521` | CONFIRMED | Already handled by NoEfforts' compound-wording rules (`docs/answer-policy.md:27-35,50-68` at `3af29f0`; `:27-35,52-70` at `b6e4cf4`); keep as positive and negative test cases |
| R4 | Required-field signals (`required`, `aria-required`, a `*` marker, "this field is required") | `legacy:src/apply.py:650-652,861-863` | CONFIRMED | Matches NoEfforts' `REQUIRED_SIGNALS_JS` and `tests/test_required_signals.py`; nothing to add |
| R5 | Stop on a visible interactive CAPTCHA; never solve. The legacy detector deliberately ignored the score-based reCAPTCHA badge, which its docstring calls "present on almost every Greenhouse form" (only an image-challenge `bframe` frame counts) | `legacy:src/apply.py:244-245,294-295,501-517` (the `bframe` selector at `:508`); `legacy:README.md:129-136` | CONFIRMED (code); the author's statements about Greenhouse are HYPOTHESIS | **Not reused as is. NoEfforts is stricter:** it stops on any reCAPTCHA element, which the legacy deliberately ignored (`CHALLENGE_SELECTORS`, `backend/app/modules/execution/adapters/greenhouse.py:29-33`; the read-only check uses the same selectors, `backend/app/modules/preparation/gh_readonly.py:549`; `tests/test_greenhouse_dom.py::test_a_captcha_on_the_form_stops_before_anything_is_disclosed`). Whether real forms carry one is UNKNOWN: none was seen at load in the one observation (`docs/greenhouse-compatibility-report.md:69`). See H13; the stop is kept (`implementation-plan.md` §2, owner decisions) |
| R6 | "Code entered and gate cleared, but no confirmation" means `submitted_unconfirmed`, never retried | `legacy:src/apply.py:1676-1683` | CONFIRMED | Already the NoEfforts rule (`backend/app/modules/applications/states.py:1-6`) |
| R7 | Real-page behaviour notes: combobox options appear only after a wrapper click, up to ~3 s; phone group has a country-code menu; city field loads options after typing; the code gate is 8 one-character inputs with a disabled button and a Resend control; confirmation can take 1 s to over a minute; resume autofill re-renders and blanks fields | `legacy:src/apply.py:249-251,272-275,594,906-917,1021-1026,1586-1590,1614-1617,1735-1742,1789-1798` | HYPOTHESIS (author's notes, not measurements) | Slow combobox open and type-to-search already exist (`gh2_dd` behaviours `delayed` and `type_only`, `fixtures/ats_receiver/greenhouse_v2.py:469-482`; `tests/test_dropdown_strategies.py::test_each_strategy_selects_exactly_the_approved_option`, `::test_unverifiable_dropdowns_stop_before_anything_is_disclosed`). New fixture variants: an 8-box code gate (`fixtures/ats_receiver/greenhouse_like.py`, `reliability-test-plan.md` R7.4) and an autofill that overwrites or blanks fields after upload (`fixtures/ats_receiver/greenhouse_v2.py`, `reliability-test-plan.md` R2.7), each mapped to an admission scenario. Verify on real pages only through the owner's manual checklist (`docs/manual-dropdown-checklist.md`) or an approved read-only run |
| R8 | Resume-vs-cover-letter file-input scoring | `legacy:src/apply.py:526-556` | CONFIRMED | Only as a classification idea; NoEfforts maps attachments by their named group (`tests/test_greenhouse_dom.py::test_attachment_named_by_its_group_is_mapped_via_the_group`) |
| R9 | State-aware toggles: never re-click a toggle that already shows the wanted answer | `legacy:src/ashby.py:169-228` | CONFIRMED | Idea for a future Ashby adapter, always with readback against the approved package |
| R10 | Embedded board URL resolved to its canonical posting | `legacy:src/apply.py:313-337` | CONFIRMED | Already `parse_posting` (`backend/app/modules/preparation/greenhouse.py:47-59`) |
| R11 | Public board API field mappings (Greenhouse list/detail, Lever `mode=json`, Ashby with `isListed`) | `legacy:src/discover.py:146-197,264-289,293-316` | CONFIRMED | Reference only, behind NoEfforts' typed errors and pacing; NoEfforts discovery is Freehire-first (`backend/app/modules/discovery/provider.py`) |
| R12 | Pending-question dedupe with a seen count | `legacy:src/pending.py:219-252` | CONFIRMED | Idea: a user-scoped "which checkpoints recur" view (not built; not yet placed in `implementation-plan.md`) |
| R13 | Safe defaults that held: dashboard bound to 127.0.0.1, `yaml.safe_load`, parameterised SQL, `html.escape` in the history table, read-only IMAP select | `legacy:src/dashboard.py:482-494,611`; `legacy:src/config.py:84`; `legacy:src/tracker.py:40-62`; `legacy:src/email_verify.py:247,314` | CONFIRMED | Already present and stronger in NoEfforts (authenticated API, CSRF check `backend/app/modules/identity/deps.py:31`) |

## 3. Fragile or unsafe components (discard)

### 3.1 Unsafe: must never be reused

| # | Component | Evidence | Label, severity | Why unsafe |
|---|---|---|---|---|
| U1 | Verification-code automation: reads Gmail (API, `gmail.readonly`) or IMAP with an app password, tries up to 6 candidate codes, presses Resend, tries 6 more | `legacy:src/email_verify.py:37-39,118-267`; `legacy:src/apply.py:1626-1674,1789-1798` | CONFIRMED, high | Automates an anti-abuse step; standing mailbox credentials; up to 12 tries per application |
| U2 | Code picker accepts codes from any sender whose subject says "security code" or "verification code", including other companies and the previous day | `legacy:src/email_verify.py:110-111,202-215,220,233,248,257` | CONFIRMED, medium (only 8-character tokens are extracted, `:65,85`) | Codes from another application or service can be typed into an employer page |
| U3 | Automated candidate-portal login with an emailed code, then scraping of the logged-in job list into the apply queue | `legacy:src/mygreenhouse.py:38-75,89-116,130-188`; `legacy:src/dashboard.py:187-220` | CONFIRMED, high | OTP automation plus automated access to a logged-in dashboard; harvested postings bypass every discovery filter |
| U4 | Real submissions without approval: `auto_submit: true` committed (README says it ships false); a 45 s pause only when there are flagged guesses in a visible browser | `legacy:config/settings.yaml:8`; `legacy:README.md:67`; `legacy:src/apply.py:257-270`; `legacy:src/lever.py:153-161`; `legacy:src/ashby.py:263-271` | CONFIRMED, high | Content nobody reviewed is sent |
| U5 | The review pause never covers LLM, consent, employer-rule, standard-field, profile-pattern or learned answers | `legacy:src/apply.py:1417-1439,1457-1459` (only `:1393-1395,1454-1455,1473` flag) | CONFIRMED, high | A run where the LLM answered every unknown eligibility question submits with no pause |
| U6 | Dry runs become live submissions on a later run, re-filled from scratch | `legacy:src/tracker.py:28-31,49-50`; `legacy:src/main.py:268,450`; `legacy:src/dashboard.py:405` | CONFIRMED, medium | What the user looked at is not what is sent |
| U7 | Ashby re-applies the bot's answers after the pause, reverting the user's corrections | `legacy:src/ashby.py:53-57,213-224`; `legacy:src/apply.py:850,871` | CONFIRMED, high | Manual fixes are silently undone |
| U8 | Consents and certifications ticked automatically; affirmative picked with no negation check; any `*` counts as required; Ashby ticks every consent-worded box | `legacy:src/apply.py:839-883,1118-1134,1168-1169,1432-1436` | CONFIRMED, high | Legal attestations and data-processing consents given on the user's behalf |
| U9 | Lone statement checkboxes ticked from hard-coded facts (authorization, sponsorship, travel, relocation, hard-coded place names), with no negation check | `legacy:src/apply.py:1155-1191`; `legacy:src/ashby.py:79` | CONFIRMED, high | "I am not authorized…" or "I am unable to travel" can be ticked |
| U10 | The "cookie banner" clicker clicks any visible Accept / Agree / I agree / Allow / Got it control, including just before Submit; consent overlays are deleted from the DOM | `legacy:src/apply.py:339-405` (text loop `:360-367`), called at `:239,303,1599`, `legacy:src/lever.py:29`, `legacy:src/ashby.py:28` | CONFIRMED, medium | An in-form agreement can be clicked unseen |
| U11 | Full-page screenshots of every filled form, kept with no retention; the code is printed and stored in the tracker and the spreadsheet | `legacy:src/apply.py:165-166,253-255,292-293,1651,1659,1661`; `legacy:src/lever.py:40-41,49-50`; `legacy:src/ashby.py:47-48,67-68` | CONFIRMED, medium | Identity, eligibility and demographic answers pile up on disk |
| U12 | Full resume text, name and narrative sent to a third-party LLM aggregator on every LLM call; untrusted page labels go into the prompt; output is submitted and reused at other employers | `legacy:src/main.py:115-120`; `legacy:src/llm.py:89,200,247,273-287` | CONFIRMED, medium (the README tells the operator, `legacy:README.md:3-5,12,78`) | Broad disclosure without minimisation; prompt-injection surface (exploitation HYPOTHESIS) |
| U13 | Local dashboard with no auth and no Origin/Host/CSRF check; any POST body parsed as JSON; `/api/retry` takes arbitrary URLs and live mode; `/api/learned` edits saved answers | `legacy:src/dashboard.py:99-101,557-603,611` | CONFIRMED, high (whether a browser blocks the cross-site POST is HYPOTHESIS) | A web page could queue real submissions to an arbitrary URL or poison saved answers |
| U14 | The employer set grows without the user choosing: Common Crawl and seed tokens are validated and appended to the board lists, then watch mode applies to them | `legacy:src/find_boards.py:171-253,449-478`; `legacy:src/main.py:264-321,355-358` | CONFIRMED, medium | Personal data goes to companies the user never selected |
| U15 | Pacing framed as not looking like a bot; a browser User-Agent on API and Common Crawl calls; opt-in search scraping in the user's real Chrome "less bot-detected" | `legacy:README.md:87-88`; `legacy:config/settings.yaml:21-23`; `legacy:src/find_boards.py:27,344-354,376-410` | CONFIRMED, low | Evasion framing; no stealth, webdriver patch, proxy or fingerprint code exists (repo-wide grep) |
| U16 | Personal facts hard-coded in answer logic and comments (a "No" for any prior-employment wording, place names, eligibility statements) | `legacy:src/apply.py:39-40,108-109,1136-1153,1166,1174,1218-1219,1415,1493,1645`; `legacy:src/discover.py:88,337-338` (values not reproduced) | CONFIRMED, medium | False statements for any user; personal data in source |
| U17 | Real personal data, including special-category self-identification answers, committed in tracked files | `legacy:common_questions.md:3-31`; `legacy:config/answer_bank.yaml:17-490`; `legacy:config/settings.yaml:75-89` (values not reproduced) | CONFIRMED, high | Exposure if the repository is or becomes shared (visibility UNKNOWN offline). Never import these files |
| U18 | Bulk download of unrelated personal mail to find one code | `legacy:src/email_verify.py:170-199,220-229,248-255` | CONFIRMED, low | Reads up to 30 full messages from any sender, repeatedly |
| U19 | Committed editor setting that allows AI-agent permission bypass | `legacy:.vscode/settings.json:2-3` | CONFIRMED that it is committed; its effect is HYPOTHESIS, low | Do not import |

### 3.2 Fragile: do not port

| # | Component | Evidence | Label, severity |
|---|---|---|---|
| F1 | React-select class names, label-above-within-400px, keyboard typing into focus with 35 Backspaces, page-wide first "Add another", school match at 0.45, no date inputs, checkbox-group question from its first descendant | `legacy:src/apply.py:621-624,795-801,885-940,968-984,1066-1078,1193-1243,1245-1280` | CONFIRMED (heuristics), medium; misfire frequency HYPOTHESIS |
| F2 | Ashby hashed CSS-module class fragments and a 7-ancestor label climb | `legacy:src/ashby.py:162,176,188-191,199,234,247` | CONFIRMED, medium |
| F3 | Lever custom-card labels may not be found (empty label, so a required question is skipped) | `legacy:src/apply.py:1527-1547`; `legacy:src/lever.py:80-82,97-99` | HYPOTHESIS, medium (verify with a saved Lever form fixture) |
| F4 | Submit-button union selector with `.first` resolves in DOM order | `legacy:src/lever.py:164-166`; `legacy:src/ashby.py:274-275` | HYPOTHESIS, low |
| F5 | Fuzzy answer reuse: learned store at 0.90, answer cache at 0.86 for all field types; negation, country and number blind | `legacy:src/learned.py:32,79-86`; `legacy:src/answer_cache.py:40,50-70` | CONFIRMED, medium (most reachable via wordings no pattern matched) |
| F6 | Non-atomic JSON stores wiped on a parse error; separate per-instance locks across the dashboard and worker | `legacy:src/learned.py:41-64`; `legacy:src/pending.py:58-72`; `legacy:src/dashboard.py:611` | CONFIRMED, low |
| F7 | Silent discovery failures (every error becomes an empty list, reported as "No unapplied positions"); 32 workers; no 429 handling; a full scan every minute in watch mode | `legacy:src/discover.py:22,150-155,184-185,272-273,302-303`; `legacy:src/main.py:457-461`; `legacy:config/settings.yaml:38` | CONFIRMED, medium |
| F8 | A token that failed validation once is never added to the board lists | `legacy:src/find_boards.py:449-466` | CONFIRMED, low (existing tokens are never removed) |
| F9 | Freshness from `max(published, updated)`; description pass 168 h vs a 720 h window in one-shot runs | `legacy:src/discover.py:23-24,206-215,240-254`; `legacy:src/main.py:435` | CONFIRMED, low |
| F10 | Lever company name derived from the board slug and used in drafted text | `legacy:src/discover.py:285`; `legacy:src/apply.py:1423,1450`; `legacy:src/llm.py:238` | CONFIRMED, low |
| F11 | Spreadsheet formula injection from employer-controlled job fields | `legacy:src/excel_log.py:48-60`; installed openpyxl stores any string starting with `=` (length > 1) as a formula | CONFIRMED (code and library), low; whether Excel evaluates without a prompt is HYPOTHESIS |
| F12 | `javascript:` URLs from posting APIs are not filtered in dashboard links | `legacy:src/dashboard.py:482,786,829` | HYPOTHESIS, low |
| F13 | OAuth loopback consent with no `state` or PKCE | `legacy:src/email_verify.py:350-370` | CONFIRMED, low |
| F14 | `.gitignore` gaps: resume `.txt/.md/.doc`, cover-letter text and copied spreadsheets are not ignored | `legacy:.gitignore:1-27` (checked with `git check-ignore --no-index`) | CONFIRMED, low |
| F15 | Single-page assumption: no handling of Next or Continue controls anywhere, so multi-page forms are out of scope. The only multi-stage elements are the Apply reveal, the embedded-iframe hop and the post-click code gate | `legacy:src/apply.py:407-456,313-337,1586-1590`; the absence is from a grep of `legacy:src/*.py` | CONFIRMED (absence by grep), medium for any multi-page ATS. NoEfforts: `Trait.multi_step` exists (`backend/app/modules/providers/model.py:75`) and one provider is marked "expected" (`backend/app/modules/providers/registry.py:256`), but no test or admission scenario covers it (`reliability-test-plan.md` §1.0 item 4) |

### 3.3 Credentials and sessions (nothing is reused)

What the repository holds (**CONFIRMED**):

- The repository is one commit with 39 packed objects (`git rev-list --count HEAD`;
  `git count-objects -v`: in-pack 39). `git ls-files` lists no token, cookie, storage-state,
  session or `.env` file. The only environment file tracked is `.env.example`, whose secret
  entries are empty (checked by value length, values not printed).
- `.env` and `data/gmail_token.json*` are gitignored (`legacy:.gitignore:1,13`).
- Each job's application starts a fresh browser with `pw.chromium.launch(...)`, and again on its
  one relaunch (`legacy:src/apply.py:189-196,220-228`; also `legacy:src/find_boards.py:344-352`).
  There is no persistent-context, user-data-directory or storage-state call anywhere in
  `legacy:src/*.py` (grep).

What is **UNKNOWN**: whether a Gmail token file, an IMAP app password, or logs and screenshots
that hold codes still exist on the owner's machine.

Rules:

- **Nothing is imported**: no token, cookie, session, app password, `.env`, log or screenshot.
- **NoEfforts holds no mailbox credential** of any kind (`freehire-first-architecture.md` §9,
  "Inbox").
- **Owner-only hygiene, at the owner's choice** (never done by an agent): revoke the legacy Gmail
  OAuth grant; remove the IMAP app password; delete the local token file; delete code-bearing
  logs and screenshots once any tally is done (`outcome-diagnostics.md` §6, rule 5). Listed in
  `implementation-plan.md` ("Blocked or owner-only").

## 4. Confirmed defects (CONFIRMED only)

Consolidated across areas. "Sources" are the area finding ids; "NoEfforts" says where the
replacement lives or that a gap remains.

### 4.1 Submission outcome, duplicates and retries

| ID | Defect | Evidence | Sev. | Sources | NoEfforts |
|---|---|---|---|---|---|
| LD-01 | "submitted" from generic phrases ("thank you for your interest", "application received") anywhere in the page body, or "confirmation" in the URL, checked **before** the click, when no button exists, after a failed click and in the poll | `legacy:src/apply.py:1591-1595,1597-1624,1826-1834` | high | gh-01, pl-08, sec-06 | Attempt-bound confirmation: this attempt's POST to the approved submit URL, same origin and job, plus the confirmation element (`backend/app/modules/execution/adapters/greenhouse_dom.py:259-301`; `adapters/greenhouse.py:178-217`) |
| LD-02 | Lever and Ashby success from bare "thank you" / "successfully" / "we received" in the body, or "thanks", "/applied", "success", "confirmation" in the URL, with no pre-click baseline. The window is only 15 s (20 × 750 ms, against 75 s on Greenhouse), so a slow confirmation becomes a retryable `error` and feeds LD-03 | `legacy:src/lever.py:21-22,173-183`; `legacy:src/ashby.py:20-21,282-292`; `legacy:src/apply.py:1617` | high | la-06, critic G11c | Same as LD-01; Lever is specification-only in NoEfforts (`backend/app/modules/providers/registry.py:182-190`) |
| LD-03 | An unconfirmed submit after a real click is stored as retryable `error`; the tracker retries `error`, `verify_needed`, `verify_timeout` up to 3 attempts in total (up to 2 later runs) | `legacy:src/apply.py:1607-1624`; `legacy:src/lever.py:47-51`; `legacy:src/ashby.py:58-69`; `legacy:src/tracker.py:23-24,49-51,59` | high | gh-02, la-02, pl-01, sec-05 | No path from `submitting`/`submitted_unconfirmed` to a retry (`backend/app/modules/applications/states.py:1-6,84-97`); `tests/test_execution_failures.py::test_crash_at_final_send_boundary_becomes_unknown` |
| LD-04 | The manual code fallback (the shipped visible-browser config) returns retryable `verify_timeout` after a code was entered and the gate cleared | `legacy:src/apply.py:1685-1686,1708-1732`; `legacy:config/settings.yaml:26` | high | pl (missed) | User-entered code checkpoint; an unknown outcome in the code step is quarantined (Q1, commit `3af29f0`, decision D50; `backend/tests/test_code_wait_quarantine.py`) |
| LD-05 | Page close or crash relaunches and re-runs the whole fill and submit once, with no marker that Submit was clicked; also during the review pause and the post-click poll | `legacy:src/apply.py:193-218` | high | gh-02(b), la-04 | `tests/test_browser_isolation.py::test_closing_the_browser_mid_submit_never_resends`; `tests/test_execution_failures.py::test_crash_after_disclosure_is_not_retried` |
| LD-06 | In-run second click: Greenhouse re-submits when an identity field had to be refilled; Ashby clicks twice when the first is not confirmed | `legacy:src/apply.py:281-291` (conditional on `:285-286`); `legacy:src/ashby.py:58-66,274-281` | medium | gh-02(a), la-03 | One final click per attempt (`backend/app/modules/execution/service.py:1-25`) |
| LD-07 | No in-progress record: check, apply, then record; a crash or Ctrl+C after the click leaves no row; overlapping cron, watch and dashboard runs can submit the same posting | `legacy:src/main.py:246-254,484-498`; `legacy:src/dashboard.py:414-425`; `legacy:src/tracker.py:27-62` | high | gh-02(e,f), pl-02 | Durable attempts with leases and `generation` fencing; unique `(user_id, job_id)` (`backend/app/modules/applications/models.py:18`); `tests/test_execution_failures.py::test_second_active_attempt_is_blocked_by_database` |
| LD-08 | `--all` and `--once` skip the dedupe; the status overwrite makes a re-applied submitted row retryable again | `legacy:src/main.py:335-337,452-455,484`; `legacy:src/tracker.py:57-59,51` | high | gh-02(d), la-26, pl-03 | `tests/test_execution_failures.py::test_an_application_with_a_recorded_receipt_is_never_queued_again` |
| LD-09 | The dashboard re-applies any non-success job with no attempt cap; `error` rows are offered as re-applyable | `legacy:src/dashboard.py:298-301,320,369-394,412-417` | medium | gh-02 (missed), la (missed) | Re-queue is a user decision with a fresh approval; reconcile first (`backend/app/modules/applications/router.py:281-342`) |
| LD-10 | Weak job identity: `<token>:<job_id>`; single URLs drop the query and fall back to token `unknown`, so all embed URLs collapse to one key, and different URL forms of one posting get different keys | `legacy:src/discover.py:42-45`; `legacy:src/main.py:150-188` | low | gh-23, pl-18 | Canonical keys (`backend/app/modules/jobs/canonical.py:75-87,114-135`); `tests/test_jobs.py::test_dedupe_key_prefers_requisition` |
| LD-11 | Dedupe by ATS job id only: reposts, multi-location and cross-ATS copies are re-applied; no per-employer limit | `legacy:src/discover.py:42-45`; `legacy:src/tracker.py:9` | medium | pl-11 | Partial gap in NoEfforts: cross-ATS copies and prior applications to the same employer are not flagged (see `freehire-first-architecture.md` §5) |
| LD-12 | Unconfirmed or failed submits neither count toward the per-run cap nor wait for the delay; no daily or per-employer cap | `legacy:src/main.py:318-320,481-483,502-505` | medium | la (missed), pl-14 | Each submission needs its own approval; no daily cap exists in NoEfforts either (grep of `backend/app`; absence not proven) |

### 4.2 Answer truthfulness

| ID | Defect | Evidence | Sev. | Sources | NoEfforts |
|---|---|---|---|---|---|
| LD-20 | Unknown required answers are guessed: decline, then none/other, then "No", then the first option; consent fallback is `options[0]` | `legacy:src/apply.py:1294-1303,1367-1396,1127-1134,1476-1478` | high | gh-06, la-12, ans-13 | LLM-free resolver; unresolved required answers block approval (`backend/app/modules/preparation/resolver.py:1-18`; `docs/answer-policy.md:18`); `tests/test_resolver.py::test_unknown_or_unapproved_facts_never_resolve` |
| LD-21 | Unmatched wordings go to an LLM forced to pick one option or "Yes"/"No", with the resume as context; the output is never flagged | `legacy:src/apply.py:1448-1459`; `legacy:src/llm.py:47-57,181-220` | high | gh-06, la-12, ans-10 | Same; drafting only for long-form from approved facts (`backend/app/modules/preparation/drafting.py:1-13`) |
| LD-22 | LLM replies mapped to options by substring: "not applicable", "I do not know", "unknown" all contain "no", become "No", and are saved for reuse | `legacy:src/llm.py:207,296-298`; `legacy:src/apply.py:1399-1408,1457-1458` | medium | gh (missed) | Not applicable (no LLM in resolution) |
| LD-23 | Unanchored substring routing: "embrace"/"trace" reach race/ethnicity, "major", "to what degree", "history with", "learn about", "current role", "days a week", one years figure for every skill, one authorization answer for every country | `legacy:src/apply.py:45-69,77,122-135,1522`; values written into textareas at `:640-646,656-661` | high | gh-07, ans-02, ans-03 | Anchored patterns and per-country facts (`backend/app/modules/preparation/classify.py`; `docs/answer-policy.md:27-35`); regression rows `legacy_collisions.json` `r8_1_*`, `r8_2_*` (S4, D54) |
| LD-24 | Standard fields run first and use unanchored substrings: "allocation" contains "location" (city into an essay about capital allocation), "phone interview availability" gets the phone number, "contact you by email" the email, a referrer's "full name" the candidate's own name | `legacy:src/apply.py:139-151,1420-1422,1483-1491` | high | gh-08, la-13, ans (missed) | Same as LD-23; regression rows `r8_3_*`, `r8_4_*`; someone else's name, email, phone or link is never filled from the profile or saved (S4, D54) |
| LD-25 | Numeric, city, phone and email values on yes/no or range questions snap to "No" or the lowest range: every "Do you have N+ years of experience in X?" gets "No"; "Are you based in <country>?" gets "No"; "work onsite at our <X> location" gets "No" | `legacy:src/apply.py:63,1294-1368,1370-1396,1424-1427,1476-1478,1488-1491` (traced with the reviewers' own stdlib copy on neutral inputs) | high | gh (missed M1), gh-08, ans (missed) | Option mapping needs an exact option or a checkpoint (`backend/app/modules/preparation/resolver.py:154-158` at `3af29f0`; `:178-182` at `b6e4cf4`); regression cases in S4; regression rows `r8_5_*`, `r8_6_*` (S4, D54) |
| LD-26 | A hard-coded "No" to any prior-employment or affiliation wording, run before every other rule, also catching "previously worked in <field>" and "affiliated with any government agency", and list questions in text inputs | `legacy:src/apply.py:1136-1153,1414-1419` | medium | gh-21, ans-07, sec-14 | Facts only from the approved, user-scoped profile; employer-relative wordings are no longer bankable under C6 (D51, `b6e4cf4`, `backend/app/modules/preparation/bankscope.py`); regression rows `r8_7_*` (S4, D54) |
| LD-27 | Radio pick takes the first option that contains the wanted text, in page order: "No" checks an earlier "Not sure", "None", "I do not know" or "Yes, I now or in the future will need sponsorship" | `legacy:src/apply.py:770-780` (Lever `legacy:src/lever.py:111`, Ashby `legacy:src/ashby.py:147,219`) | high | gh-09 (low on the Greenhouse path alone), la-09, ans-04 | Exact `data-value` match, "never pick a near match" (`backend/app/modules/execution/adapters/greenhouse_dom.py:194-199`); `tests/test_resolver.py::test_option_mismatch_is_not_guessed`; regression rows `r8_8_*` (S4, D54) |
| LD-28 | Ashby fills every combobox, and any label containing "based", "where do you", "location" (also "relocation", "allocation") or "work from", with the home city; then clicks the first option-like element on the page, which the code's own model says can be a yes/no button | `legacy:src/ashby.py:95,105-110,170,230-257` | high | la-07, la-08 (medium), ans (missed) | Location is a checkpoint (`tests/test_greenhouse_dom.py::test_location_job_is_a_checkpoint`); regression rows `r8_3_*`, `r8_6_*`: preference help on residence fields and residence words are checkpoints (S4, D54) |
| LD-29 | Lever location: types, clicks the first suggestion from a broad selector if visible, returns success either way, overwrites a parsed value | `legacy:src/lever.py:116-132`; also `legacy:src/apply.py:916-925,1216-1234` | medium | la-14, gh-08 | Search-as-you-type unsupported until proven (`docs/provider-architecture.md`) |
| LD-30 | Fuzzy and laundered reuse: every resolved select/boolean/textarea answer (profile, bank, LLM) is saved to the "learned" store with no source flag, consulted before the bank and LLM, matched at 0.90; the answer cache reuses LLM answers for all field types at 0.86 | `legacy:src/apply.py:1399-1408,1426,1437-1439,1446,1457-1458`; `legacy:src/learned.py:32,79-86,106-109`; `legacy:src/llm.py:184-192,206-209`; `legacy:src/answer_cache.py:40,58-65` | high | gh-15, la-21, ans-06, ans-08, pl-12 | Bank entry only on explicit save, same wording and options (`backend/app/modules/preparation/resolver.py:112-129` and `backend/app/modules/preparation/router.py:450-458` at `3af29f0`; `:136-153` and `:454-462` at `b6e4cf4`); regression rows `r8_11_*` with exact-reuse controls (S4, D54) |
| LD-31 | Employer-relative and time-bound answers fixed once for every employer (start date, salary, years, current title, referral, source, previously employed) | `legacy:src/apply.py:61-81,103-107` | medium | ans-07 | **Gap present at `3af29f0`**: these wordings are bankable, and relocation and salary fall through to the bank (`backend/app/modules/preparation/resolver.py:54-77,186-190,229-231,268-271` at `3af29f0`). Narrowed by C6 (D51, `b6e4cf4`): `relocation` and `salary_expectation` join `NO_BANK`; the other wordings are refused only where `bankscope.reason()` recognises them, so a wording it does not recognise (a known miss: a named employer without deixis) may still be offered for saving (`docs/answer-policy.md` row 5); tests `tests/test_bank_scope.py`, `tests/test_bank_scope_api.py::test_answers_that_depend_on_the_employer_the_job_or_the_date_are_never_saved` |
| LD-32 | Job-specific text carried into other employers' answers: `{role}` substituted before saving; company templating is a raw case-insensitive substring swap | `legacy:src/answer_bank.py:73-75`; `legacy:src/learned.py:89,95-96`; `legacy:src/answer_cache.py:70,76` | medium | ans-09 | Long-form is never banked (`backend/app/modules/preparation/resolver.py:63-77` at `3af29f0`; `:64-81` at `b6e4cf4`) |
| LD-33 | Sensitive and legal-status questions (EEO, age, background, citizenship, criminal history) answered from one config for every employer, including optional fields, and copied into the learned store | `legacy:src/apply.py:83-128,609-618,783-837,885-940,1426` | high | ans-11 | Per-application include choice; legal status asked per application (`docs/answer-policy.md:13-14`; `tests/test_question_safety_api.py::test_sensitive_and_legal_answers_are_never_saved_for_reuse`) |
| LD-34 | Conditional follow-ups never revisited (single pass); no validation-error read after submit, so a validation failure looks like an unknown outcome and is retried | `legacy:src/apply.py:601-678,1617-1624`; `legacy:src/lever.py:54-114`; `legacy:src/ashby.py:61-66` | medium | gh-10, la-19 | `tests/test_greenhouse_adapter.py::test_conditional_question_follows_its_trigger`, `::test_unplaceable_condition_is_a_checkpoint_not_a_guess`; "rejected" from the page's error list |
| LD-35 | Resume upload unverified: a lone cover-letter input gets the resume; no cover letter ever uploaded; "attached" decided by the file stem anywhere in the body; gives up silently after 12 s; dry runs upload too | `legacy:src/apply.py:247,257,520-599`; `legacy:src/config.py:50-51` | medium | gh-11, la-23 (low), ans-22 (low) | Upload acknowledgement, readback, sha256-bound documents (`tests/test_upload_evidence.py`) |
| LD-36 | Values the ATS parsed from the resume are kept over the profile (filled controls are skipped) | `legacy:src/apply.py:631,680-710,899-901,989-991,1007-1009,1579-1583`; `legacy:src/lever.py:92,140`; `legacy:src/ashby.py:86,97` | low | gh-12, la-18 | Readback before submit (`tests/test_greenhouse_dom.py::test_combobox_that_does_not_keep_its_choice_is_caught_by_readback`); an autofill-overwrite fixture mode is NEW |
| LD-37 | Optional textareas receive bank, template or LLM prose; a generic cover-letter template answers "why us" when the AI is unavailable; a fixed 900-character cut with an ellipsis, the form's own limit never read | `legacy:src/lever.py:103`; `legacy:src/ashby.py:114`; `legacy:src/llm.py:94,212-240,285-286,301-302` | medium | la-20, ans-16, ans-17 | Long-form is the user's or an accepted grounded draft that fits the field (`backend/app/modules/preparation/drafting.py:13,84-88`) |
| LD-38 | The answer LLM never receives the job description; Greenhouse title matches carry no description at all | `legacy:src/llm.py:36-44,276-287`; `legacy:src/discover.py:146-155,244-245` | medium | ans (missed), pl-15 | Drafting grounded in approved facts and job text (`backend/app/modules/preparation/drafting.py`); no provider wired |
| LD-39 | Question identity is the visible label only (no help text, options or type); generic follow-ups ("If yes, please specify") share one entry | `legacy:src/apply.py:1527-1547`; `legacy:src/learned.py:23-28,67-89` | medium | ans-18 | Key = label + answer shape; generic labels never bankable; help text not in the key at `3af29f0` (`backend/app/modules/preparation/resolver.py:124-125`). C6 (D51) adds it without re-keying old rows (`bankscope.question_key`; `tests/test_bank_scope.py::test_a_saved_answer_needs_the_same_help_text`; `b6e4cf4`) |
| LD-47 | Degree names mapped by their first letters: any degree string whose first two letters are "ma" or "ms" (or that contains "master" or starts "m.", "msc", "mba") becomes the "Master's Degree" option; "ba", "bs", "b.", "bsc", "bcom" become "Bachelor's Degree"; the value is filled into the structured education section. Depending on the profile string this can misstate education; the effect is UNKNOWN because `config/profile.yaml` is absent | `legacy:src/apply.py:957-965` (used at `:1108`) | medium (critic G11a; the skeptic pass rated the related mapping bugs, ans-23, low as a group) | ans-23 | No degree mapping exists: an education select resolves only from a saved answer for the same wording and options, or becomes a checkpoint (`tests/test_resolver.py::test_answer_bank_reuse_requires_same_wording_and_options`); regression rows `r8_16_*` (S4, D54) |
| LD-48 | "Select all that apply" checkbox groups get one tick: the loop checks the first option equal to the snapped answer and breaks | `legacy:src/apply.py:821-836` | medium | la-16 | Checkbox groups are filled and read back as exact sets (`backend/app/modules/execution/adapters/fixture_ats.py:99-102,130-135`; `tests/test_greenhouse_adapter.py::test_full_run_is_confirmed_and_sends_exactly_the_approved_values` sends both approved options); a page that unticks one is still NEW (`gh_group_untick`) (`reliability-test-plan.md` R2.9); resolver rows `r2_9_*` (an exact saved set, never a subset; S4, D54) |

LD-47 and LD-48 were added by the completeness critic. They take free ids so that existing
references stay valid.

### 4.3 Destination, discovery and pipeline

| ID | Defect | Evidence | Sev. | Sources | NoEfforts |
|---|---|---|---|---|---|
| LD-40 | No destination allowlist: personal data and the resume go to whatever host the job URL, a redirect or an unanchored embed-iframe regex leads to; `_has_form` accepts any page with two identity inputs; nothing checks the job id | `legacy:src/apply.py:233-242,313-337,458-499`; `legacy:src/main.py:154,165,186-188` | medium (high combined with LD-60) | gh-13, sec-04 | `parse_posting`, `backend/app/core/urlsafety.py`, `adapter_for` fixture-origin and same-origin submit checks (`backend/app/modules/execution/policy.py:204-226`) |
| LD-41 | Location filter infers eligibility by substring, checked before the foreign list: foreign places pass via short tokens, some domestic places with foreign names are dropped, unknown locations kept | `legacy:src/discover.py:84-117,126-127` (reproduced on synthetic strings) | medium | pl-10 | Discovery never infers eligibility; missing data is "insufficient" (`backend/app/modules/discovery/service.py:102-132`) |
| LD-42 | Defense/clearance exclusion by board token and title only; the comment names a file the code never reads | `legacy:src/discover.py:337-368,377` | medium | pl-16 | Source facts tri-state only |
| LD-43 | The relevance gate lets jobs through when the LLM is off, out of credit or fails; in-domain terms checked before out-of-domain terms; the dashboard shows it "on" but never applies it | `legacy:src/llm.py:150-160,177-178`; `legacy:src/dashboard.py:402-427,504,550,697` | medium | ans-21, pl-15, pl (missed) | No LLM gate; preferences only produce explanations (`backend/app/modules/jobs/service.py:119-155`) |
| LD-44 | Ranking hard-coded to one profession, ignores the profile, no threshold | `legacy:src/match.py:15-90`; `legacy:src/main.py:26-34` | low | ans-20 | No ranking in NoEfforts yet (lists by `last_seen_at`) |
| LD-45 | Claimed CAPTCHA skipping is absent on Lever and Ashby; a blocked submit is a retryable `error` | `legacy:src/lever.py:24-51`; `legacy:src/ashby.py:23-69`; claim at `legacy:README.md:89`, `legacy:config/settings.yaml:55-60` | medium | la-01 | Lever `captcha_possible=expected`, a checkpoint (`backend/app/modules/providers/registry.py:244-251`) |
| LD-46 | Unpaced, silently failing discovery (see F7) | as F7 | medium | pl-13, sec-15 | Typed `DiscoveryError`, 429 never retried, budgeted paging (`backend/app/modules/discovery/provider.py:91-97,344-366`) |

### 4.4 Tracking and accounting

| ID | Defect | Evidence | Sev. | Sources | NoEfforts |
|---|---|---|---|---|---|
| LD-50 | Success tallies mix `submitted`, `submitted_unconfirmed` and `dry_run`; the dashboard's "Submitted" counts submitted and unconfirmed together | `legacy:src/main.py:318-320,502-509`; `legacy:src/dashboard.py:62,468` | low | gh-20, pl-09, sec-06 | States kept apart (`backend/app/modules/applications/states.py:21-22`); closed by S2 (D53): a user's confirmation needs what they checked and is recorded as user-claimed, a receipt is read from the attempts, and the funnel shows them apart (`backend/app/modules/applications/states.py`, `service.py`, `funnel.py`) |
| LD-51 | One row per job with the status and time overwritten; no attempt history; the spreadsheet writes "Date Applied" for every status and has no ATS or key column; a row is dropped when the workbook is open | `legacy:src/tracker.py:7-18,53-62`; `legacy:src/excel_log.py:16-26,47-65` | medium | pl-09 | Insert-only `application_events`, enforced by a database trigger since S2 (migration `e3a91c5d7b20`, D53) |
| LD-52 | No confirmation email is ever reconciled (thank-you mails are recognised only to be excluded); no outcome field (interview, assessment, rejection) | `legacy:src/email_verify.py:103-115`; `legacy:src/tracker.py:7-18` | medium | gh-20, pl-19 | Closed by S2 (D53): `Outcome.assessment_received`, outcome events with a source, a date and the audit row `application.outcome`; inbox reconciliation stays out (D10) |

### 4.5 Security and privacy

| ID | Defect | Evidence | Sev. | Sources |
|---|---|---|---|---|
| LD-60 | Dashboard open to cross-site requests (U13) | `legacy:src/dashboard.py:557-603` | high | sec-09, pl-06 |
| LD-61 | Codes, the email address and every filled form persisted unencrypted (U11); the Gmail refresh token written with default permissions | `legacy:src/email_verify.py:15-16,403-404` | medium | sec-10 |
| LD-62 | Committed personal data (U17) | see U17 | high | sec-01, ans-24 |
| LD-63 | Spreadsheet formula injection (F11) | see F11 | low | pl-22, sec (missed) |

## 5. Unverified hypotheses and unknowns

| # | Claim | Label | What would verify it |
|---|---|---|---|
| H1 | Real hosted Greenhouse pages render description text that contains one of the confirmation phrases in the same body as the form, so LD-01 fired before any click | HYPOTHESIS | Owner, manually and privately: compare legacy `submitted` rows whose detail has no code note with confirmation emails, as counts only (see `outcome-diagnostics.md`) |
| H2 | Employers actually received duplicate applications from LD-03 to LD-09 | HYPOTHESIS | Owner counts tracker rows with `attempts > 1` and rows re-run with `--all`/`--once`, against confirmation emails per posting (counts only) |
| H3 | The OTP loop clicked Submit again after an `unknown` 16 s result while the first code had been accepted | HYPOTHESIS (loop CONFIRMED at `legacy:src/apply.py:1652-1664`) | Not verifiable without server-side data |
| H4 | Lever and Ashby have no emailed code gate | UNKNOWN (asserted in docstrings `legacy:src/lever.py:8`, `legacy:src/ashby.py:6-7`) | Public documentation review, or a recorded manual observation |
| H5 | Real-page timings and widgets in R7 | HYPOTHESIS | `docs/manual-dropdown-checklist.md`; an approved read-only run |
| H6 | The bank essays overstate or generalise claims; the same metrics reached many employers | Reuse CONFIRMED (`legacy:config/answer_bank.yaml:18-490`: a repeated metric, organisations named in most entries; counts from the reviewers' structure script, values not reproduced); truthfulness HYPOTHESIS | Only the owner can judge |
| H7 | Automation signatures (synthetic `isTrusted=false` events, fixed typing delays, applying within minutes of posting, identical templated text, a trailing ellipsis) made submissions scored or filtered differently. The author's own notes raise the same possibility: automated sessions "can score low" and Greenhouse "may silently filter or flag" them (`legacy:README.md:134-136`; "reCAPTCHA scoring" in `legacy:src/apply.py:1614-1616`). These signatures are listed only to state a hypothesis. NoEfforts will not mask them (no jitter, human-like typing, browser or fingerprint changes, or anything aimed at a score); see `implementation-plan.md` §5 | HYPOTHESIS (signatures CONFIRMED at `legacy:src/apply.py:1019,1223,1560-1571`; `legacy:config/settings.yaml:23,38,124`; `legacy:src/llm.py:301-302`; the README and comment are the author's notes, not evidence) | Needs receiver-side or employer data; cannot be checked from the code. A confirmation email does not refute it (`outcome-diagnostics.md` H12) |
| H8 | A cross-site page could actually reach the dashboard API in the owner's browser | HYPOTHESIS | A synthetic cross-origin page against a sandboxed copy (never against the owner's machine without consent) |
| H9 | Which code-level stop condition ended real runs (missing profile, missing token, discovery errors shown as "no positions", per-run cap, revoked Gmail token, manual code waits) | UNKNOWN (conditions CONFIRMED at `legacy:src/config.py:80-82`, `legacy:src/main.py:405-408,457-461,481-483`, `legacy:src/email_verify.py:152-161`, `legacy:src/apply.py:1690-1732`) | The owner's local logs |
| H10 | The legacy repository is or was public | UNKNOWN | The owner checks the repository's visibility setting |
| H11 | The profile values actually submitted (eligibility, demographics, years) | UNKNOWN (`config/profile.yaml` is gitignored and absent) | Owner-only, local |
| H12 | The `.vscode` setting disables agent prompts for anyone opening the repository | HYPOTHESIS | The extensions' documentation |
| H13 | A score-based check (such as the reCAPTCHA badge the legacy ignored) runs on real Greenhouse forms, at load or only at submit. If a reCAPTCHA element is present at load, NoEfforts' check, made once after the page opens, stops the run before disclosure (`backend/app/modules/execution/runner.py:169`); if one appears only after the final click, NoEfforts has no challenge check there: the page falls to the existing outcome rules (rejected or unknown; `backend/app/modules/execution/adapters/greenhouse.py:178-200`, and for v2 `backend/app/modules/execution/adapters/greenhouse_dom.py:259-291`) and is never solved; this is untested (`reliability-test-plan.md` R4.9b, NEW). Either way NoEfforts never attempts to pass it | HYPOTHESIS (the author's notes, `legacy:src/apply.py:502-505`, `legacy:README.md:130-136`); one NoEfforts read-only observation recorded no bot check at load on one posting (`docs/greenhouse-compatibility-report.md:69`) | Only an approved read-only observation that records challenge presence at load. No submission, and no attempt to pass, avoid or influence any check. Presence at submit cannot be observed without submitting, so it stays UNKNOWN |

## 6. Rewrite: NoEfforts replacements

| Legacy concern | Replace with (NoEfforts) | Status |
|---|---|---|
| Phrase-based confirmation (LD-01, LD-02) | Attempt-bound confirmation in `backend/app/modules/execution/adapters/greenhouse_dom.py:259-301`; admission scenario `rejection_is_not_confirmation` (`backend/app/modules/providers/admission.py:176-184`) | Exists; add a "confirmation phrase on the form page" fixture mode (NEW, `reliability-test-plan.md` R6) |
| Retry after an unknown outcome (LD-03 to LD-09) | `backend/app/modules/applications/states.py` (no retry exits), `backend/app/modules/execution/service.py` (CAS on state and `generation`, one active attempt), reconciliation in `backend/app/modules/applications/router.py:281-342` | Exists; the code-step quarantine fix (Q1) landed in `3af29f0` (D50) |
| OTP and login automation (U1-U3) | User-typed code at a checkpoint (`backend/app/modules/execution/runner.py:424-447`); login-gated applications unsupported (`docs/greenhouse-adapter.md:54`) | Exists; no mailbox client anywhere, a static guard (`tests/test_forbidden_capabilities.py`, S4) |
| Auto-submit and timers (U4-U7) | Package approval bound to the content hash, 72 h expiry, separate rehearsal and submit approvals, final gate (`backend/app/modules/preparation/package.py`; `execution/service.py:377-491`) | Exists |
| Guessing and fuzzy reuse (LD-20 to LD-33) | `backend/app/modules/preparation/classify.py`, `resolver.py` (LLM-free; checkpoints), bank keyed on wording and shape | Exists; employer-relative and time-bound scope and help text in the key (LD-31, LD-39) are C6 (D51, `b6e4cf4`); the legacy collision corpus and its narrowing (S4, D54) |
| Consents and statements (U8-U10) | Explicit per-application agree or decline (`resolver.py:610-655` at `3af29f0`; `:642-687` at `b6e4cf4`); a fact statement is checked only with agree and a true approved fact (C3, `tests/test_question_safety_api.py::test_a_fact_statement_is_checked_only_while_the_approved_fact_makes_it_true`) | Exists; never click a cookie or "accept" control automatically (no such code in NoEfforts); consent options under a neutral label never saved, negated right-to-work and residence statements never checked (S4, D54) |
| Screenshots and logs (U11, LD-61) | Minimal evidence (`backend/app/modules/execution/models.py:166`), retention purge (`backend/app/worker.py:60`), type-only logging (`backend/app/core/log_safety.py`) | Exists; a static guard "no screenshot or tracing call in execution code" is NEW; no capture where a page runs, a static guard (`tests/test_forbidden_capabilities.py`, S4) |
| LLM disclosure (U12) | No provider wired (`backend/app/modules/preparation/drafting.py:72-74`); future provider needs server-side config, per-user consent and minimised inputs (L4 in `implementation-plan.md`) | Exists (by absence) |
| Destination checks (LD-40) | `parse_posting`, `adapter_for`, egress proxy, pinned identity gaps (`docs/provider-admission.md:202-217`) | Exists; `resolve_public_destination` must be called before any live server-side fetch (not called today) |
| Discovery (LD-41 to LD-46) | Freehire-first provider with tri-state source facts, typed errors and budgets (`backend/app/modules/discovery/`) | Exists, off by default; see `freehire-first-architecture.md` |
| Tracking (LD-50 to LD-52) | `AppState`, `Outcome`, insert-only events, outcome sources and the funnel | Built (S2, D53) |
| Dashboard (U13) | Authenticated API, CSRF token, SameSite cookies (`backend/app/modules/identity/deps.py:31`, `router.py:51`) | Exists |
| Committed data (U17) | `tests/test_repo_hygiene.py` | Exists |

## 7. Licences and dependencies

- **Licence.** Neither repository has a LICENSE file (`ls`). The legacy history has one commit
  and one author, the owner (`git log --format=%an`). A grep for copied, adapted, licence,
  attribution, gist or stackoverflow markers found nothing. **CONFIRMED.**
- **Reuse.** That the owner may reuse their own legacy code is a legal inference, not
  CONFIRMED. The copyright status of any AI-assisted parts is UNKNOWN. Nothing in these documents
  proposes copying legacy code, so the question does not arise.
- **Provenance not established.** `Fable5.md` (agent instructions, provenance UNKNOWN) and the
  board lists (employer tokens derived from Common Crawl and public APIs) must not be copied.
- **If any legacy idea is ported**, it is rebuilt, not copied; record its provenance in
  `docs/decisions.md`. `THIRD_PARTY_NOTICES.md:3` ("No third-party source code has been copied")
  stays accurate only while no third-party code is copied.
- **Dependencies** (`legacy:requirements.txt:1-15`): openai, playwright, httpx, PyYAML,
  python-dotenv, pypdf, python-docx, openpyxl, tenacity, rich. All are unpinned (`>=`), with no
  lock file or hashes; `rich` is never imported. Licences, read offline from installed package
  metadata (`*.dist-info/METADATA`), not from the legacy repository:

  | Package | Version read | Licence | Read from |
  |---|---|---|---|
  | playwright | 1.56.0 | Apache-2.0 | `backend/.venv/lib/python3.12/site-packages` |
  | httpx | 0.28.1 | BSD-3-Clause | same |
  | python-dotenv | 1.2.4 | BSD-3-Clause | same |
  | openpyxl | 3.1.5 | MIT | same |
  | PyYAML | 6.0.3 (6.0.1 in the system packages) | MIT | same; `/usr/lib/python3/dist-packages` |
  | pypdf | 6.17.0 | BSD-3-Clause | `/usr/local/lib/python3.13/dist-packages` |
  | python-docx | 1.2.0 | MIT | same |
  | tenacity, rich, openai | — | UNKNOWN locally (not installed) | — |

  **CONFIRMED** for the versions read. The versions the legacy actually installed are UNKNOWN,
  because nothing was pinned.
- **Compatibility.** playwright, httpx and openpyxl are already NoEfforts dependencies, with
  tighter pins (`backend/pyproject.toml:17,19,26`: `openpyxl>=3.1,<4`, `playwright==1.56.0`,
  `httpx>=0.28,<1` in the dev group). Nothing needs adding, because nothing is ported. `openai`
  (the client the legacy used for its LLM aggregator) must not be added. NoEfforts pins via
  `backend/uv.lock` and `frontend/package-lock.json`. **CONFIRMED.**
- **Other terms.** The installed Chrome channel falls under Google's terms; the LLM aggregator's
  terms are UNKNOWN.
- **Freehire** code is MIT (unchanged at `ab47628`); it covers the code, not the postings
  (see `freehire-first-architecture.md`). If Freehire's ATS host table (`atsboard/board.go`)
  were ever ported, `THIRD_PARTY_NOTICES.md:3` would become false and an MIT notice would be
  required. Not proposed.

## 8. Why there were no interviews: what we can and cannot conclude

The owner recalls that Greenhouse runs "worked" most of the time, that other ATSes were less
reliable, that several hundred applications were sent with confirmation emails received, and that
no interview or assessment followed. **These are recollections, not measurements**, and this
document does not turn them into rates.

**What cannot be concluded (from this repository):**

1. **No cause can be established.** The tracker database, spreadsheet, logs, profile and answer
   stores are gitignored and absent (`legacy:.gitignore:4-8,13-23`). No outcome was ever recorded
   (`legacy:src/tracker.py:7-18`). **CONFIRMED.**
2. **The number of real submissions is UNKNOWN.** Logged "submitted" can include phrase-matched
   pages that were never sent (LD-01, LD-02), unconfirmed results and dry runs (LD-50), and
   duplicates (LD-03 to LD-09).
3. **Confirmation emails show that those applications reached an ATS.** They say nothing about
   what content arrived, whether it was correct, or how it was screened.
4. **Whether automation was detected or penalised is UNKNOWN** (H7). It is one hypothesis among
   several, never an assumed cause.
5. **No comparison with a base rate is possible.** There is no data on the market, roles,
   seniority or timing distribution of the postings.

**What the code shows could have contributed (each CONFIRMED as a code path; its effect on
outcomes is a HYPOTHESIS):**

| Possible contributor | Code path | Test for it (see `outcome-diagnostics.md`) |
|---|---|---|
| Disqualifying "No" answers to experience and location questions | LD-25, LD-24, LD-26 | Owner reviews their own saved answers and screenshots privately, as categories and counts |
| Eligibility answered for the wrong country, or inferred by the LLM | LD-23, LD-21, LD-22 | Same |
| Wrong radio or consent option picked | LD-27, U8 | Same |
| Postings the candidate could not take (foreign locations admitted, role mismatch, fail-open relevance) | LD-41, LD-43, LD-44 | A sample of the applied postings (needs the owner's tracker export and permission to read those postings) |
| Generic or repeated essays; essays without the job description; one resume for every role | LD-37, LD-38, LD-32, LD-35, H6 | Owner review of the essays used; the resume versions |
| Missing resume or required fields, or validation failures counted as submissions | LD-35, LD-34, LD-01 | Confirmation-email count vs "submitted" count |
| Duplicates to the same posting or employer | LD-03 to LD-11 | Tracker rows grouped by key and by employer plus normalised title |
| Timing (applied within minutes of posting; reposted or evergreen postings) | `legacy:config/settings.yaml:38,124` | Posting dates vs application dates |
| Fixed employer-relative answers that did not fit the posting (an out-of-range salary, a start date, relocation) | LD-31 (`legacy:src/apply.py:50,61-62`) | Owner's private review of the answers given, as categories only (`outcome-diagnostics.md` H14) |
| Automation signatures | H7 | Not testable without employer-side data |

None of these is established as a cause. Answering the question needs the evidence and
permissions listed in `outcome-diagnostics.md`, and any future measurement should come from
NoEfforts' own outcome funnel, never from legacy tallies.
