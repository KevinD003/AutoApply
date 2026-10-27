# Outcome diagnostics

Status: 2026-10-27; code references are to NoEfforts `3af29f0` (Q1, D50) unless marked; C6 (D51) landed afterwards as `b6e4cf4`; completeness-critic fixes G2 and G12-G14 applied.

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
| `prepared` | A package exists for the current form | A package version | `AppState.awaiting_approval` (`M/applications/states.py:15`); package versions (`M/preparation/package.py`) | Implicit state, not an outcome; fine |
| `approved` | The user approved this exact package for submission (or for a rehearsal) | `PackageApproval` row bound to the content hash, not expired or revoked | `PackageApproval`; `AppState.queued` once queued | No application state for "approved, not queued"; derive it from the approval rows (NEW, display only) |
| `disclosed` | Some data left NoEfforts toward the employer (fill, autosave or upload), whether or not it was submitted | `ExecutionAttempt.disclosure_started_at`; attempt state `abandoned` or `rehearsed` (`M/execution/models.py:33-37`) | Attempt level only | NEW: derive an application-level "disclosed" flag for the funnel from its attempts; never stored separately |
| `submitted_unconfirmed` | The final send may have happened; the outcome is unknown | Attempt state `unknown`; or the user's "I applied myself" | `AppState.submitted_unconfirmed` (`M/applications/states.py:22`) | Two meanings share one state (worker-unknown vs user-claimed manual application); the event's `actor` tells them apart. NEW: show the source |
| `submitted_confirmed` | The employer's receipt was observed | Receipt evidence from the attempt (`M/execution/service.py:674-716`) | `AppState.submitted_confirmed` (`:21`) | **A user can set it from `submitted_unconfirmed` with no evidence** through `POST /applications/{id}/transition` (`states.py:92`; `M/applications/router.py:207-278`). Only `/reconcile` demands stated evidence. NEW (slice S2): a user confirmation needs stated evidence and is recorded as user-claimed |
| `rejected` | The employer declined the candidate | User-reported (later: an employer email, only with an inbox permission) | `Outcome.rejected` (`:39`) | Same word as `AttemptState.rejected` (the *form* refused the submission → `failed_terminal`). NEW: label them "form rejected" vs "employer declined" in the UI and docs |
| `assessment_received` | The employer sent a test, task or screening questionnaire | User-reported | **missing** (`Outcome` has `none`, `interviewing`, `offer`, `rejected`, `withdrawn`, `no_response`; `M/applications/states.py:35-41`) | NEW: add the value (PostgreSQL enum `app_outcome`, so a migration) |
| `interview_received` | An interview was offered or scheduled | User-reported | `Outcome.interviewing` (`:37`) | One value; no rounds or dates. Keep one value; record the date the user says it happened |
| `withdrawn` | The user withdrew | User action | `Outcome.withdrawn` (`:40`) | — |
| `no_response` | Nothing heard back | User-set today | `Outcome.no_response` (`:41`) | No time rule. NEW: a *computed* "no response yet (N days since confirmed submission)" shown in the funnel, never stored as an outcome; the user sets `no_response` explicitly when they decide |
| (extra) `offer` | — | User-reported | `Outcome.offer` (`:38`) | — |

**Recording today (CONFIRMED):** `PATCH /applications/{id}` with `outcome` accepts any
application state, even `draft` (`M/applications/router.py:345-366`). It inserts an
`ApplicationEvent(kind="outcome")` with the reason `"outcome: old → new"` (`:353-362`): no date of
the employer's event, no source, no evidence note, and no audit `record()` call. The tracker page
has an outcome select (`frontend/src/app/(app)/tracker/page.tsx:82-84,118-125`). Only
`tests/test_applications.py::test_user_transitions_and_timeline` covers it.

**No funnel or metrics exist (CONFIRMED):** no aggregation endpoint or page
(grep of the modules for funnel, metrics, stats found nothing relevant).

### 1.1 Proposed outcome record (NEW, design only)

Each outcome change stays an insert-only `ApplicationEvent`, plus:

- `occurred_on` (date, optional): when the user says the employer acted, separate from entry time;
- `source`: `user_reported` today; `receipt` for the worker's confirmation; `employer_email` only
  if an inbox permission is ever granted (D10), and never set by inference;
- a short `evidence_note` (optional for outcomes, required for a user confirmation of a
  submission), stored like the reconcile finding, never copied into audit rows;
- an audit `record()` with the outcome value and source only (no free text), per
  `docs/audit-events.md` conventions;
- refusal of an outcome other than `withdrawn` on an application that never reached a submitted
  state, or a visible flag on it (owner decision).

### 1.2 Funnel computation (NEW)

- Per user only; computed from states and events at read time; never compared across users.
- Counts: prepared → approved → disclosed → submitted (confirmed by receipt / unconfirmed /
  user-claimed shown separately) → any response → assessment → interview → offer; plus
  rejected, withdrawn, no response.
- Every count shows its denominator, and with fewer than about 20 submissions the page says the
  numbers are too few to compare.
- **Tests use the receiver ledger as the oracle** for "submitted"; the funnel is a user-facing
  view, never the source of truth for test assertions (CLAUDE.md).

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
| submitted, unconfirmed | 2 | 1 reconciled "received" with evidence, 1 open |
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

### 5.3 A synthetic outcome event (proposed shape)

```json
{"kind": "outcome", "from": "none", "to": "assessment_received", "actor": "user",
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
