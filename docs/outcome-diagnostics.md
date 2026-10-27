# Outcome diagnostics

Status: 2026-10-27; code references are to NoEfforts `3af29f0` (Q1, D50) unless marked; C6 (D51) landed afterwards as `b6e4cf4`; S2 (D53) built §1 since, and §1 describes it as built; completeness-critic fixes G2 and G12-G14 applied.

Finding ids (gh-/la-/ans-/pl-/sec-), "map Qn" and "critic Gn/Ln/Cn" refer to the review's working notes, which are not committed. C1-C18 and L1-L4 are the preparation steps listed in `implementation-plan.md` (§0 and "Remaining preparation steps"); `docs/implementation-status.md` names the ones already implemented or referenced.

How NoEfforts should record what happened to each application, what
historical evidence could help explain the legacy bot's results, what each kind of evidence needs
as a separate permission, and how to tell submission errors from quality, role-fit, eligibility,
timing and duplicate problems. NoEfforts at `3af29f0`. All examples are synthetic.

Labels: **CONFIRMED**, **HYPOTHESIS**, **UNKNOWN**, **NEW** (proposed, not built).
`M/` = `backend/app/modules/`.

## 1. Funnel schema vs what exists

| Stage | Meaning | Evidence that establishes it | In NoEfforts today | Gap |
|---|---|---|---|---|
| `prepared` | A package exists | A package version | `AppState.awaiting_approval` (`M/applications/states.py:15`); package versions (`M/preparation/package.py`) | Built (S2, D53): any package version of the application counts |
| `approved` | The user approved a package, to submit or to rehearse | A `PackageApproval` row | `PackageApproval` | Built (S2, D53): any approval of any scope, ever, including revoked or expired ones; derived, never stored |
| `disclosed` | Some data left NoEfforts toward the employer (fill, autosave or upload), whether or not it was submitted | `ExecutionAttempt.disclosure_started_at` | Attempt level | Built (S2, D53): an attempt with `disclosure_started_at` set (rehearsals included); derived, never stored |
| `submitted_unconfirmed` | The final send may have happened; the outcome is unknown | Attempt state `unknown`; or the user's "I applied myself" | `AppState.submitted_unconfirmed` | Built (S2, D53): the event's `source` tells them apart (`user_claimed` for the user's statement, none for the worker's or sweeper's unknown outcome); the page says "Applied by you (not confirmed)" or "Submitted (not confirmed)" |
| `submitted_confirmed` | The employer's receipt was observed, or the user confirmed it | A confirmed attempt (receipt); or the user's statement with what they checked | `AppState.submitted_confirmed` | Closed (S2, D53): a user's confirmation needs 15 to 2,000 characters of what they checked and is recorded as `user_claimed`; a receipt is read from the attempts, so a late receipt that left the application `submitted_unconfirmed` still counts as one |
| `rejected` | The employer declined the candidate | User-reported (later: an employer email, only with an inbox permission) | `Outcome.rejected` | Built (S2, D53): shown as "Employer declined"; a form that refused the submission (`AttemptState.rejected`, `failed_terminal`) is "Form rejected" and is never an employer outcome |
| `assessment_received` | The employer sent a test, task or screening questionnaire | User-reported | `Outcome.assessment_received` | Built (S2, D53; migration `e3a91c5d7b20`) |
| `interview_received` | An interview was offered or scheduled | User-reported | `Outcome.interviewing` | One value; no rounds. The user can give the date it happened (S2) |
| `withdrawn` | The user withdrew | User action | `Outcome.withdrawn` (`:40`) | — |
| `no_response` | Nothing heard back | User-set | `Outcome.no_response` | Built (S2, D53): "no response yet" (21 days or more in the current submitted stretch, outcome none) is computed in the funnel, never stored; the user sets `no_response` when they decide |
| (extra) `offer` | — | User-reported | `Outcome.offer` (`:38`) | — |

**Recording before S2:** `PATCH /applications/{id}` accepted any outcome in any state, even
`draft`, with no date, no source, no note and no audit row. S2 (D53) replaced it as below.

### 1.1 Outcome record (built, S2, D53)

Each outcome change is one insert-only `ApplicationEvent(kind="outcome")` (a database trigger
refuses UPDATE, and DELETE unless it cascades) with:

- `from_outcome` and `to_outcome`: the change, typed; rows written before S2 keep NULL and count
  only through the application's current outcome (unknown stays unknown);
- `occurred_on` (date, optional): when the user says the employer acted, no later than UTC today
  plus one day;
- `source`: `user_reported` for an outcome; `receipt` and `user_claimed` mark what a submission
  rests on; `employer_email` does not exist and would need an inbox permission (D10); a source
  is set by the server only, never sent by a client;
- `evidence_note`: the user's private note on an outcome (optional), or what they checked when
  confirming a submission (required, 15 to 2,000 characters); served to its owner only, never
  copied into audit rows or logs, and it cannot be edited or removed;
- an audit row `application.outcome` with `to` and `source` only;
- refusal of an outcome other than none or withdrawn on an application with no submission
  NoEfforts knows of (`(reason: outcome_before_submission)`; codes in `architecture.md`,
  "Refusal codes"). The owner can switch this to a visible flag without a data migration.

### 1.2 Funnel (built, S2, D53: `GET /applications/funnel`, `M/applications/funnel.py`)

Per user only, computed when read, never stored, never compared across users, no rate. Each
count has its denominator:

| Count | Rule | Of |
|---|---|---|
| tracked | the user's applications | |
| prepared | a package exists | tracked |
| approved | an approval of any scope exists, ever | prepared |
| disclosed | an attempt with `disclosure_started_at` (rehearsals included) | approved |
| form_rejected | an attempt the employer's form refused ("Form rejected", never "Employer declined") | disclosed |
| submitted | the submission rests on a receipt, the user's statement, or is unconfirmed | tracked |
| responded; assessment_received, interviewing, offer, rejected | the value was recorded (a change to none takes back the value it replaced; nothing is implied) | submitted |
| no_response | the current outcome is no_response | submitted |
| no_response_yet | outcome none, no response recorded, 21 days or more in the current submitted stretch (computed) | submitted |
| withdrawn | withdrawn was recorded | submitted |
| withdrawn_before_submission | withdrawn, on an application never submitted | tracked |

The submitted split (receipt, user_claimed, unconfirmed) sums to the total; user_claimed splits
into "confirmed by you" and "applied by you". Outcomes recorded on an application never
submitted (before S2, or under the owner's flag switch) are counted apart and in no stage.
Below 20 submissions the page says "N submissions is too few to compare rates". **Tests use the
receiver ledger as the oracle** for "submitted"; the funnel is a user-facing view, never the
source of truth for test assertions (CLAUDE.md).

### 1.3 Refusal codes (D53)

The closed set (`evidence_required`, `outcome_before_submission`, `confirm_through_reconcile`)
and their exact messages are listed under "Refusal codes" in `architecture.md`.

## 2. Historical evidence that would help, and the permission each needs

None of this evidence is in the legacy repository: the run databases, spreadsheet, logs,
screenshots, profile and answer stores are gitignored and absent (`legacy:.gitignore:4-8,13-23`).
CONFIRMED. Each item below needs its **own** explicit permission from the owner; one permission
never implies another. Processing is always local, by the owner or a script the owner runs,
producing **counts and categories only**; nothing is committed, uploaded or pasted into a
conversation.

| Evidence | What it could answer | Risk | Separate permission needed | Safe processing |
|---|---|---|---|---|
| Legacy tracker database (`applied.sqlite3`: key, status, detail, attempts, timestamp) | How many rows per status; how many `attempts > 1`; how many "submitted" with no code note | Detail can hold verification codes (`legacy:src/apply.py:1659`) and screenshot names | **Historical-data permission** (owner's local files) | A local read-only script that prints counts per status and per attempts bucket; never prints keys, URLs or details |
| Legacy spreadsheet (`applications.xlsx`) | Same, with dates; rows per ATS | Employer-controlled cells could be formulas (`F11`); holds employer names and titles | Same permission | Open with formulas disabled, or read values only; output counts per status and month |
| Legacy run logs (`logs/run.log`) | Which stop condition ended runs (H9); errors and code prompts | Printed codes and email (`legacy:src/apply.py:1651,1661,1705`) | Same permission | Grep for fixed status words only; counts |
| Legacy screenshots | Whether specific answers (eligibility, experience) were wrong | Contain every filled answer, including demographics | Same permission, **and** the owner reviews them personally; never shared or analysed by an agent | Owner-only manual tally by category ("experience question answered No: yes/no") |
| Legacy answer stores (`learned_answers.json`, `pending_questions.json`, `answers.sqlite3`) and profile | Which answers were guessed, learned or LLM-produced; frequency of unknown questions | Personal facts and demographics | Same permission; owner-only for values | A local script that prints counts per source and per category, no values |
| Confirmation emails | How many applications reached an ATS; per ATS; per month | Mailbox content is broadly personal | **Inbox permission** (separate; read-only; a defined date range and sender filter; owner runs the search themself) | The owner counts matching messages in their own mail client; or, only if the owner wants it later, a scoped OAuth design under D10. Never automated reading in this project now |
| Employer replies (rejections, assessments, interview invitations) | Response rates by stage | Same | Same inbox permission, separately stated | Owner tallies by category |
| Resume versions used | Format and content issues (parseability, length, tailoring) | Personal data | **Document permission** (owner shares a redacted version or reviews privately) | Owner-only review against a checklist; no upload to an LLM |
| The postings applied to | Role fit, seniority, location and eligibility mismatches, reposts and evergreen postings, timing | Real employer data; terms of the source | **Real-postings permission** (owner-provided list or tracker export; any re-fetch is a live request needing its own approval and terms check) | A sample (for example 30 rows chosen at random by the owner), categorised by the owner: fit / partial / mismatch; location eligible / not / unclear |
| The candidate-portal account history (the ATS's own "my applications" page) | Which applications the ATS shows as received | Logged-in third-party account | **Owner manual check only**; automated access is forbidden (CLAUDE.md; legacy U3) | Owner counts by hand |
| Applications the owner sent by hand in the same period, if any (optional, NEW) | A natural comparison: responses to hand-sent against bot-sent applications, counts only. Confounded by role mix, timing and effort, so it can only weakly inform H3, H5 or H12, and any result must be labelled so | The same tracker and mailbox data as above | The historical-data and inbox permissions, each stated again for this comparison | The owner counts responses in each group; no names and no per-employer rows |
| Employer-side data (optional, NEW) | What an employer actually received, and how it was screened | Contacts real employers about the owner's own applications | **Owner decision**, employer by employer: asking directly, or a statutory data-access request where one applies. Whether one applies, and what comes back, is UNKNOWN | Owner only, never automated; NoEfforts sends nothing |

## 3. Telling causes apart

Each row is one hypothesis. "Automation detection" is one row among many and is never assumed.
None is established today; each column says what would support or refute it.

| # | Hypothesis | Legacy code path that makes it plausible | Evidence needed (permission) | Supports if… | Refutes if… | NoEfforts guard going forward |
|---|---|---|---|---|---|---|
| H1 | Many recorded "submissions" never happened | LD-01, LD-02 (phrase match before the click), LD-35 (missing resume) | Tracker counts + confirmation-email counts (historical, inbox) | "submitted" rows clearly outnumber confirmation emails for the same ATS and period | Counts roughly match | Attempt-bound receipt; receiver-ledger tests (`reliability-test-plan.md` R6) |
| H2 | Duplicates annoyed or confused employers | LD-03 to LD-11 | Tracker rows with `attempts > 1`; runs with `--all`/`--once`; emails per posting (historical, inbox) | Several confirmations for one posting | One confirmation per posting | No retry after the final click; one application per job; possible-duplicate flag (S3) |
| H3 | Eligibility answers were wrong or inferred | LD-21 to LD-23, LD-27, U9 | Owner's review of screenshots and answer stores (historical, owner-only) | Wrong country, inferred, or inverted answers found | Answers match the facts | LLM-free resolver; per-country facts; C3-C5 |
| H4 | Experience and location questions were answered "No" | LD-25, LD-24, LD-26 | Same | "No" found on questions the candidate qualified for | Not found | Exact option mapping or checkpoint; collision corpus (R8) |
| H5 | Role fit: titles, seniority or skills did not match | LD-43, LD-44 (fail-open relevance, one-profession ranking) | Sample of postings (real-postings permission) | Many partial or mismatched roles | Mostly good fit | User chooses each job; explanations; ranking is NEW and transparent |
| H6 | Location or work-authorization eligibility mismatch | LD-41 (foreign places admitted), LD-42 | Same sample | Many postings the candidate could not legally take | Few | Source facts shown, never inferred (`freehire-first-architecture.md` §5.4) |
| H7 | Generic or repeated essays; no use of the job description | LD-37, LD-38, LD-32, `legacy-audit.md` H6 | Owner reviews the essays used (historical, owner-only) | Identical text and metrics across employers | Tailored text | Long-form is the user's or an accepted grounded draft (C15) |
| H8 | Resume quality or format | One resume for every role (LD-35) | Resume versions (document permission) | Parse problems, length, or the resume does not show the posting's stated requirements (owner judgement). How any ATS ranks resumes is UNKNOWN, and NoEfforts makes no ranking claim | Clean | Document library; tailoring is not started (L1-L3 in `implementation-plan.md`) |
| H9 | Timing: applied very early, to reposted, evergreen or ghost postings | Watch every minute (`legacy:config/settings.yaml:38`); freshness from `max(published, updated)` (F9) | Posting and application dates; for current postings Freehire's documented `reality` signals | Many postings reposted or evergreen | Mostly fresh, single postings | Separate dates; optional display of `reality` (owner decision) |
| H10 | Volume and saturation: many applications to the same employers | No per-employer limit (LD-11, LD-12) | Tracker counts per employer (historical; counts only, no names) | A few employers received many applications | Spread out | Possible-duplicate flag; a per-employer view (NEW) |
| H11 | Required fields missing or validation failures counted as success | LD-34, LD-35, LD-01 | Overlap of H1 with screenshots showing validation errors (owner-only) | Screenshots show errors on "submitted" rows | None | Readback, rejected from the page's error list |
| H12 | Automation was detected or scored down by the ATS or employer | Signatures CONFIRMED (`legacy-audit.md` H7): synthetic events, fixed delays, instant applications, templated text. The author's own notes, HYPOTHESIS as facts about Greenhouse: the score-based reCAPTCHA badge was deliberately not treated as a stop, automated sessions "can score low", and Greenhouse "may silently filter or flag" them (`legacy:README.md:129-136`; `legacy:src/apply.py:501-517`; "reCAPTCHA scoring" at `legacy:src/apply.py:1614-1616`). The README's only suggested check was one application-received email (`legacy:README.md:137-138`), while the same passage says there is no guarantee a submission lands in the recruiter's pipeline (`:135-136`). Third-party, unverified: a comment in Freehire's code says its own browser "lost Greenhouse's invisible reCAPTCHA as often as it passed it" (Freehire `internal/api/atsapply/client.go:56-88`); it is not evidence about the owner's applications | Employer-side or ATS-side data, which the owner does not have | Cannot be supported from the owner's data alone | Cannot be refuted either. **A confirmation email does not refute it**: it shows receipt by the ATS, not how the application was scored or screened | NoEfforts never hides automation (CLAUDE.md): no jitter, human-like typing, browser or fingerprint changes, or anything aimed at a score (`implementation-plan.md` §5); submission only after explicit approval; honest identification |
| H13 | The market base rate for these roles is simply low | — | External data (not available) | UNKNOWN | UNKNOWN | Funnel per user with denominators |
| H14 | Fixed employer-relative answers did not fit the posting (an out-of-range salary, a start date, a relocation answer) | LD-31: salary, start date and relocation answered once for every employer (`legacy:src/apply.py:50,61-62`) | Owner's private review of the answers given (historical, owner-only), as categories only | Answers that conflict with a posting's stated range, date or location | Answers fit the postings | C6 (D51): these wordings are answered per application and never reused (`b6e4cf4`) |

**Order of checks (cheapest, least invasive first):** H1 and H2 from local historical counts →
H10 from the same counts → H3, H4, H7, H11, H14 by the owner privately → H5, H6, H9 on a small
posting sample → H8 on the resume. H12 and H13 stay open without new data. Of the two optional
rows in §2, the hand-sent comparison informs H12 only weakly; only employer-side data could bear
on it directly.

## 4. What cannot be concluded

- **No cause for the absence of interviews can be established from the legacy repository.**
  The data is absent and no outcome was ever recorded (`legacy:src/tracker.py:7-18`). CONFIRMED.
- **The recalled figures are not measurements.** The recalled share of Greenhouse runs that
  "worked" and the recalled number of submissions cannot be checked from the code, and the legacy
  tallies they would come from mix confirmed, unconfirmed, phrase-matched, dry-run and duplicate
  rows (`legacy-audit.md` LD-50). They must not be presented as rates.
- **Confirmation emails prove receipt by an ATS, not correctness or screening.**
- **Automation detection cannot be shown or ruled out** without employer-side data (H12).
- **A future NoEfforts funnel will not explain the past either**; it can only measure new
  applications made under its rules.

## 5. Synthetic examples

All numbers and names below are invented for illustration. They are not the owner's data and
are not estimates of it.

### 5.1 A synthetic funnel (one fictional user, "Sam Synthetic")

| Stage | Count | Note |
|---|---|---|
| prepared | 24 | |
| approved | 20 | 4 parked on checkpoints |
| disclosed | 19 | 1 rehearsal only |
| submitted, confirmed by receipt | 16 | ledger-equivalent in tests |
| submitted, unconfirmed | 2 | 1 reconciled "received" with evidence (the built funnel counts it as user-claimed, "confirmed by you"), 1 open |
| submitted, user-claimed (applied by hand) | 1 | shown separately |
| any response | 6 | of 19 submitted |
| assessment_received | 2 | |
| interview_received | 1 | |
| rejected (employer declined) | 3 | distinct from "form rejected" (0) |
| no response yet (over 21 days) | 9 | computed, not stored |

The page would say: "19 submissions is too few to compare rates; 6 responses so far."

### 5.2 A synthetic diagnostic tally (owner-run, counts only)

```
legacy tracker (synthetic): submitted 50, submitted_unconfirmed 4, error 12, dry_run 7
  rows with attempts > 1: 9
confirmation emails in the same period (owner's own count): 38
=> H1 (some "submitted" never sent) is supported for this synthetic data; H2 needs the 9 rows
   checked against emails per posting.
```

### 5.3 A synthetic outcome event (as built, S2)

```json
{"kind": "outcome", "from_outcome": "none", "to_outcome": "assessment_received", "actor": "user",
 "source": "user_reported", "occurred_on": "2026-11-03", "evidence_note": "(optional, private)"}
```

The audit row for it would carry only `{"to": "assessment_received", "source": "user_reported"}`.

## 6. Privacy rules for any diagnostic work

1. Local only; counts and categories only; nothing committed (`tests/test_repo_hygiene.py` keeps
   documents and session files out of the repository).
2. No inbox, portal or posting access without its own explicit permission, stated in advance with
   its scope (date range, senders, sample size).
3. Never run legacy code; diagnostic scripts read legacy files as text, with `python -I`, from a
   directory outside the legacy repository.
4. Screenshots and answer values are reviewed by the owner only.
5. Delete working copies after the tally; keep only the counts the owner chooses to keep.
