# Email-to-application status tracking

Recognise recruitment emails in the owner's own mailbox, match each to the right application, and
update the tracker when the evidence is clear — deterministically, privately, and only with the
owner's explicit, recorded authorization.

This extends the existing `inbox` module (D101/D103/D117). It does **not** add a parallel status
system: `Application.state` + `Application.outcome` + the insert-only `ApplicationEvent` history
remain the single source of truth, and every status change still goes through
`applications.service` (`record_outcome` / `transition`), exactly as manual entry does.

## Activation dependency (read this first)

The feature is **built but gated off**. To process a real mailbox, all of:

1. **A recorded authorization for `read_application_email`** in `app/core/authorizations.py`
   (the `RECORDED` register). Today only `read_codes`/`enter_codes` are recorded (D117);
   application-email reading is **not**. The register, by its own rule, is never added from a
   feature request, a config switch or a deployment file — only from the owner's explicit words,
   quoted in `docs/decisions.md`. Until that entry exists, every read is refused (`not_authorized`).
2. **`InboxSettings.tracking_enabled = true`** (per-account opt-in; off by default).
3. **A connected read-only Gmail token** (`python -m app.modules.inbox.connect`, token stored on
   the owner's machine, never in the repo, DB or image).
4. The owner's account (`inbox_owner_emails`) and `NOEFFORTS_INBOX_ENABLED` for the server.

Auto-apply additionally requires `InboxSettings.auto_apply = true` (off by default).

**Consent defaults.** A new account starts with **every** mailbox-processing option off — codes,
application-email tracking and auto-apply alike (`settings_of`). Each is turned on separately by the
owner; connecting Gmail, or turning one on, never turns on another. This moves the D117 code-reading
toggle from on-by-default to opt-in; the D117 *authorization* (what the owner's words permit) is
unchanged — only the default toggle moved.

## How it works (spec section → implementation)

- **§1 Matching** — `inbox/rules.py::match()`. Several deterministic signals, strongest first:
  exact application/requisition id (from the job's `requisition_id` / posting URL), an established
  **email thread** link (a prior event sharing the message's keyed `thread_ref`), the employer
  identified by name **or by the sender's own domain**, the job title (with seniority-word
  variants), and corroboration from a known ATS sender. A company name **alone** is never enough;
  two equally plausible applications are never chosen between. When the match is weak or ambiguous
  the message becomes a **review** item, never an update. Match confidence (`match_band`:
  strong/good/weak/ambiguous/none) is kept separate from classification confidence.
- **§2 Events** — `inbox/rules.py::classify_detail()`. The full taxonomy (received, under_review,
  assessment, assessment_reminder, interview, interview_scheduled, interview_rescheduled,
  interview_cancelled, info_requested, next_round, offer, rejected, position_closed, withdrawn,
  talent_pool, recommendation, other, unclear) by fixed wording — no LLM. An assessment invite is
  not completion; a scheduling link is not a booked interview; a cancellation is not a rejection;
  an offer is "offer received", never acceptance; a job recommendation is not an update.
  Conflicting signals in one message → `unclear` (`class_band` = ambiguous).
- **§3 Timeline + derived status** — the recognised event lives on `InboxEvent` (its kind, the two
  confidence bands, the match basis as short codes, the proposed and previous outcome, the source
  message reference and the change origin via `state`), separate from the application's
  `state`/`outcome`. Temporal guards (`inbox/service.py::_guard`, explicit rules, **no numeric
  stage ranking**): a late acknowledgement never undoes a later stage; a reminder never resets a
  later stage; an older message never overrides newer activity; a manual correction is never
  silently overridden; genuine conflicts become review items. Messages are deduped by
  `(user, message_ref)` and processed oldest-first. Submission evidence (confirmed / your statement
  / unconfirmed) and the recruitment stage (assessment / interviewing / offer / rejected…) are
  **separate dimensions**: an outcome email changes only the recruitment stage, never the submission
  evidence. The one email that can strengthen submission evidence is an explicit "we received your
  application" acknowledgement, and only under the tested `_settles` rule (D103): it names the
  employer *and* the job title, arrived after that submission's final click, reconciles a submission
  of *unknown* outcome, and you confirm it. An interview invitation and a scheduled interview both
  derive the "interviewing" stage but stay distinct on the event timeline (`kind`) and in the
  application's outcome note. Undo records a compensating outcome back to the value before the event
  and is refused when a newer update has since superseded it (the `applied_outcome` guard), so undo
  never clobbers a newer stage — undo the newer one first.
- **§4 Automatic vs review** — `InboxSettings.auto_apply`. A clear update is applied automatically
  only when it maps unambiguously to one application (match strong/good), its meaning is explicit
  (`class_band == explicit`), it is temporally consistent, and nothing is locked or conflicting.
  Everything else is proposed for review. No calibrated-looking confidence percentages. An
  automatic change is still recorded, audited and **undoable**.
- **§5 Silence** — reuses `followups` (it already computes "no response for N days" from the
  application's own records) and the funnel's 21-day "no response yet" stage. Recording an
  email-derived outcome resets/closes those clocks automatically. Silence is never a rejection;
  nothing is auto-sent.
- **§6 Parsing** — `inbox/parsing.py::current_text()` trims quoted reply history and reads the
  forwarded body of a forward, so the **current** message is classified, not a quoted old
  rejection. Message content is untrusted data: instructions in a body are never followed, no
  remote assets/pixels are loaded, no links or attachments are opened, nothing is sent.
- **§7 Permissions & privacy** — separate from OTP access and sending. Honest scope copy in the
  API (`SCOPE_NOTE`): read-only access can read bodies (broader than what is used); the app-side
  filter does not narrow the Google-issued scope. Opt-in, a bounded first-read window
  (`inbox_first_read_days`), connected-account visibility, pause/disconnect, revocation handling,
  and deletion via account deletion (all `inbox_*` tables cascade on user delete). No message
  text, subject, sender name or code is stored, logged, or put in fixtures/CI/notification
  previews — only a keyed message reference, the sender's domain, the recognised event and the
  application. No mark-read, label, send or delete capability.
- **§8 Synchronisation** — bounded, restart-safe, incremental polling by timestamp cursor
  (`last_checked_at`), advanced only on a complete read. Duplicate delivery and reconnect are
  idempotent (`message_ref` uniqueness). A pass reads at most `_MAX_READ` messages; if that is hit
  the cursor is **not** advanced and the condition is surfaced (`too_many`) rather than silently
  skipping intermediate mail. Expired tokens / revoked consent / unreachable Gmail are reported by
  fixed codes.
- **§9 Tracker UX** — the API exposes, per event: the matched application, the recognised event,
  previous → proposed/current outcome, a plain-language "why it matched", an automatic/review
  label, the timestamp, and Confirm / Correct / Undo / "wrong application" (relink) actions. A
  restrained notification (`email_update` kind) says only that an application status was updated,
  with no content in the preview. The frontend surfaces these in two places that share one row
  component (`components/EmailUpdateRow.jsx`) and one data hook (`lib/useInbox.js`): an **"Email
  updates" card on the tracker** (`components/EmailUpdates.jsx`), where proposals, auto-applied
  updates and review/unlinked items are confirmed, corrected, undone or re-linked; and the
  **Account → Email card** (`components/InboxCard.jsx`), which also carries the §7 settings (codes,
  tracking, the opt-in `auto_apply` toggle) and the honest read-only scope copy. The notifications
  feed renders the `email_update` kind (`app/(app)/notifications/page.jsx`), linking to the
  tracker. All of it reads nothing but the API fields above — no message content exists client-side.
  The tracker leads with what needs attention (email updates to confirm/correct, follow-ups due),
  then the applications and their stages, with a compact overview (a few meaningful chips) whose
  denominators and submission-evidence split live in an expandable "Full breakdown"; automation
  settings sit at the foot of the page. Each application row shows its submission evidence and its
  recruitment stage as distinct pills, and the open application shows both as labelled lines. The
  layout holds at phone width (verified in `e2e/email-updates.spec.ts` on the mobile project).
- **§10 Tests** — `tests/test_inbox_tracking.py` (pure classification/matching/parsing/injection)
  and the stateful flow tests in `tests/test_inbox.py`, on synthetic fixtures only. They prove,
  among others, that unrelated mail never updates an application, that injected "instructions" are
  data, that a quoted old rejection is not recorded, and that the feature is tenant-isolated. One
  coherent end-to-end scenario asserts the recognised event, the outcome, the funnel summary, the
  application row and the notification all agree and that undo restores every surface; further cases
  cover undo after a newer event, an ambiguous match that updates no application at an employer,
  assessment, interview-invitation-vs-scheduled, inactivity-vs-rejection, and consent independence.
  The UI's own coherence across a reload is in `e2e/email-updates.spec.ts`.

## Residual / real-device limitations

- Live processing needs the recorded `read_application_email` authorization (above) — the exact
  activation dependency; it is intentionally not added here.
- Work on a real inbox was not done and must not be: all tests use the local Gmail stand-in
  (`fixtures/ats_receiver/inbox_fixture.py`).
- The sync cap (`_MAX_READ`) fails safe (surfaces `too_many`, never skips) rather than paging an
  unbounded backfill; a smaller first-read window resolves a very large initial backlog.
