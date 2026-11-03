# Greenhouse rehearsal runbook (disclosure-only — never submits)

A rehearsal fills a real Greenhouse application form, uploads the resume, reads its own answers
back, re-checks the form, and **stops before the final submit**. It discloses real data to the
employer's page; it does not submit. This runbook is for the **owner's own deployment** (the
Docker Compose stack, `docs/deployment.md` / `docs/owner-mac-verification.md`), where the owner's
data and the pilot switch live. It is not run from a development sandbox, and nothing in this
document initiates a live run.

Everything below was verified against the code at the revision that introduced this file. No
personal values appear here; the owner's facts live only in the running app.

---

## What a rehearsal proves — and what it does not

- It is **disclosure-only** (`ApprovalScope.disclose_only`). It never clicks submit.
- Its evidence is written to the **`execution_evidence`** table (`app/modules/execution/models.py`),
  **not** to the synthetic fixture "receiver ledger" (that ledger exists only for local tests; a
  real employer never posts to it). A rehearsal's rows:
  - `disclosure` rows — one per disclosed field; an upload row also carries the document's
    `sha256` and the page's own acknowledgement value (`attachment_shown` — the real page showing
    the attached file's name, D116).
  - one `readback` row — the filled values read back from the page (`mismatched` count; **0** means
    what was filled matches what was intended).
  - one `recheck` row — `{"form": "matched"}`, meaning the pre-send re-reconciliation
    (`schema_matches`) passed again after filling.
  - `egress` rows — counts of requests the egress proxy denied (a denial means the control held).
  - `strength` stays **`none`**. The confirmation strengths (`employer_receipt`,
    `employer_confirmation_page`, `api_receipt`) are produced only by a real **submission**, never
    by a rehearsal. **An upload acknowledgement is not a confirmed application submission.**
- Each evidence row is bound to `attempt_id` + `application_id` + `user_id`; the attempt binds to
  the exact **package version** (`attempt.package_id`) and the approval; the uploaded documents'
  `(field, sha256)` must equal the approved package's documents, binding the **document version**.
  On a clean rehearsal a `RehearsalRecord` is written (bound to the attempt, path, adapter,
  adapter version and destination class) and is re-checked against the live evidence rows whenever
  it is relied on (`rehearsal.assess_record`).
- **Unverified on a real page.** This evidence machinery is implemented and tested against local
  fixtures only; it has never run against a real Greenhouse page. Whether a real page's upload
  acknowledgement and confirmation are recognized exactly as the fixtures model them is unverified.
  A first real rehearsal therefore either passes every check (producing the evidence above) or
  **stops safely before disclosure** — both are acceptable first outcomes.

A rehearsal **does not unlock submission universally.** A valid rehearsal satisfies the submission
prerequisite (E6) only for the **same user + provider + employer-board path**, must still meet the
evidence and invalidation rules, and a real submission still needs its **own** separate
`submit`-scope approval and must pass every gate again.

---

## Why this is executable without a circular gate

- The submission prerequisite (a prior successful rehearsal, E6) is checked **only for `submit`
  approvals** (`package.approve`: `if scope == ApprovalScope.submit …`). A `disclose_only`
  rehearsal has **no** rehearsal prerequisite, so it does not require the evidence it is meant to
  establish.
- What a rehearsal **does** require, in order:
  1. The pilot switch on in the owner's deployment: `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`
     (`docker-compose.pilot.yml`).
  2. The account is the configured pilot owner (`live_owner_emails` allow-list) and env is right
     (`execution/live.py` `environment_refusal` / `refusal`).
  3. A **recorded authorization** covering `read`, `open` and `disclose` — recorded in reviewed
     code (`app/core/authorizations.py`, D112/D113/D114), **valid through calendar date
     2026-11-06 inclusive**, evaluated against the **server's local date** (`date.today() <=
     2026-11-06`); it lapses the moment the server's local date is 2026-11-07. No time-of-day or
     explicit time zone is recorded. **Do not extend it.**
  4. A shared attempt budget: **at most 5** attempts that reach the disclosure gate (rehearsals and
     submissions alike), counted across all accounts since 2026-11-01. Each rehearsal consumes one.
  5. A form that **captures cleanly** (below) and a per-application `disclose_only` approval.
- **Gate check before any execute step:** on the application's route card the route must read
  **`greenhouse_live` ("browser … the Greenhouse pilot, on for this account")**. If it instead
  reads **`manual_handoff`**, the attached reason is the exact missing prerequisite (pilot off,
  not this account, or no recorded authorization). **Do not queue it** — there is nothing to run,
  and the message names what to fix.

---

## The education/employment section (D120): do not rehearse it to capture it

- If a posting's form shows an **education/employment section**, capture **fails closed**:
  `build_schema` raises `SchemaMismatch` ("form_sources_disagree") and `POST
  /jobs/{id}/form/greenhouse` returns **409 — no form is stored, so no package, approval, or
  rehearsal can exist**. A rehearsal therefore **cannot** be used to obtain that section's DOM.
- If instead the section is rendered only by client-side JavaScript (so a no-JS capture GET misses
  it), the package captures "clean," but the worker reads the **fully rendered DOM** before
  disclosure and stops: `adapter.schema_matches` (called before `fill`, `runner.py`) flags the
  live control as a **new field** and the attempt ends `failed_safe` with nothing disclosed.
  Regressions: `tests/test_greenhouse_adapter.py::test_form_changed_after_approval_stops_before_disclosure`
  (static) and `::test_a_required_control_added_only_by_javascript_stops_before_disclosure`
  (injected by JS after load). A zero-error package never hides a control the live page shows.
- **So choose a rehearsal posting with no education/employment section and no other unsupported
  control** (all required controls supported, package fully resolved). Education-section evidence
  is gathered **separately** and is not part of this rehearsal.

---

## Steps

Prerequisites confirmed first (stop if any is not true):

- `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true` and the owner account named — run
  `python3 scripts/check_env.py --pilot <your .env>` and `./scripts/verify-local.sh --pilot`.
  **Scope limit:** these check your `.env` and compose config and run a **throwaway** `noefforts_smoke`
  Compose project (its own volumes, removed at the end). They do **not** read or verify your actual
  running stack. A green result proves your configuration is valid, **not** that your live stack is
  up and correctly running the pilot — confirm that separately in step 1.
- Your approved records cover the form's required facts (work authorization, sponsorship, salary;
  self-identification only if you have turned it on). Any gap appears as a checkpoint and is never
  inferred or filled.
- At least 1 of the shared 5 attempts remains, and today's server-local date is on or before
  2026-11-06.

1. **Health / stack.** Confirm your **running** stack answers `GET /api/health` (not the throwaway
   smoke project). Bring the pilot overlay up as `docs/activation-status.md` §5 describes.
2. **Identify the application privately.** In the **Tracker**, open the target application and read
   its **route card**: it names the real destination (host + Greenhouse job id) and must read
   **`greenhouse_live` ("the Greenhouse pilot, on for this account")**. If it reads
   `manual_handoff`, stop and fix the named prerequisite.
3. **Review approved facts, answers and document versions.** On the **Review** page, confirm each
   answer's source and the attached resume's version, and that your Profile records are approved.
   The rehearsal panel (`GET /applications/{id}/rehearsal-handoff`) lists what the rehearsal needs.
4. **Confirm every required control is supported.** The package must have **zero `unresolved` and
   zero `validation_errors`** (`GET /applications/{id}/package`). If the posting has an
   education/employment section, capture will have failed (step 2 shows no captured form) — pick a
   different posting. Resolve any checkpoint yourself first; nothing is guessed.
5. **Approve for a rehearsal (disclosure-only).** On the **Review** page, approve with the
   **rehearsal (fill and check, never submit)** scope. (Underlying call: `POST
   /applications/{id}/package/approve` with `{version, content_hash, scope: "disclose_only"}` — the
   version and hash shown on the page. Prefer the page's action over posting this by hand.)
6. **What reaches the employer.** Queuing the rehearsal **discloses real data**: the package's
   resolved answers are typed into the employer's page and the resume is uploaded. It then stops
   before the submit. Treat this as a real disclosure even though nothing is submitted.
7. **Execute.** On the application, start the run (underlying: `POST
   /applications/{id}/transition` with `{to: "queued"}`). The worker claims it, the
   `greenhouse_live` adapter fills + uploads, reads back, re-checks, and **stops at the submit
   gate**. No submit is clicked.
8. **Verification code (if the page asks).** If a code step appears, the attempt waits
   (`needs_user_action`); enter the code in the app's checkpoint. The manual code checkpoint is
   implemented and fixture-tested; whether a real Greenhouse code challenge is recognized exactly
   is unverified (first real run). Gmail auto-entry is **optional** (`python -m
   app.modules.inbox.connect`) and under its own recorded authorization; the manual path does not
   depend on it.
9. **Stop / cancel — and what it does not undo.** Three distinct actions:
   - **Cancel execution** (`POST /applications/{id}/cancel`) — stops future work on the attempt.
   - **Withdraw the rehearsal** (`POST /applications/{id}/rehearsals/{attempt_id}/withdraw`) —
     invalidates the rehearsal record so it no longer counts toward a submission.
   - **Revoke the approval** (`POST /applications/{id}/package/revoke`) — invalidates the approval.
   None of these **retracts data already disclosed to the employer or an upload already completed** —
   they only stop further work and invalidate NoEfforts-side records. The adapter also self-stops on
   any policy violation (an unexpected non-GET, a disallowed redirect, an unsupported or new
   control). An **uncertain** final-click outcome is quarantined (`submitted_unconfirmed`) and is
   **never retried automatically**.
10. **Success evidence & an uncertain result.** Success = an attempt in state `rehearsed` with a
    valid `RehearsalRecord` and `execution_evidence` rows (disclosure with the page's
    `attachment_shown` ack bound to the resume `sha256`, `readback` mismatched = 0, `recheck`
    matched), shown on the Review page and Tracker. No screenshots or raw logs are needed. If the
    outcome is uncertain, leave it quarantined, do **not** re-run, and reconcile it in the Tracker.

---

## Explicit statements

- A rehearsal **discloses** your data to the employer even though it never submits.
- **No final submission click is authorized** by preparing or running a rehearsal.
- **No automatic retry** after an uncertain outcome.
- **Gmail is optional**; the manual verification-code checkpoint remains supported.
- Nothing (screenshots, raw logs, personal documents) needs to be pasted into chat.

## The one unavoidable owner action

Run steps 1–10 on your own deployment, on a Greenhouse posting with **no** education/employment
section, while the recorded authorization still holds (server-local date on or before 2026-11-06),
and only if step 2 shows the `greenhouse_live` route. This is authorized by your recorded
permission plus a per-application approval — not by this document.
