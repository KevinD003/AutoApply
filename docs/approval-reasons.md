# Approval reasons (C13, D65)

Why NoEfforts refuses to approve a package, to queue an approved one, or to revoke an approval
(and, on a multi-page form, to cancel an attempt in progress: `wizard_in_progress`, D142).
Each refusal is a 409 whose message ends with `(reason: code)`, a fixed code that is safe to
record. Implemented in `backend/app/modules/preparation/package.py` (`APPROVAL_REASONS`) and
`backend/app/modules/execution/service.py`; tested in `backend/tests/test_approval_reasons.py`,
which also checks that this table lists exactly these codes. A job's own signals (closed,
excluded, possible duplicate) have their codes in `docs/job-signals.md`, and the rehearsal
prerequisite has its codes in `docs/rehearsal-prerequisite.md`.

| Code | Message |
|---|---|
| `package_changed` | The package changed since you reviewed it. Review the latest version and approve again. |
| `package_unresolved` | Resolve every required question before approving. |
| `approval_other_scope` | This package is already approved ‹for a rehearsal / to submit›. Revoke that approval first. |
| `approval_needed` | Approve the current package version before queueing. |
| `already_confirmed` | The employer's confirmation of this application was recorded; it is not sent again. |
| `submission_in_progress` | A submission is in progress; wait for it to finish or cancel it. |
| `attempt_running` | An earlier attempt for this application is still running. Wait for it to finish, then queue again. |
| `attempt_being_claimed` | An earlier attempt for this application is being picked up by a worker; it will stop, because the package changed. Try again in a moment. |
| `revoke_in_flight` | The submission may already be in flight, so revoking cannot stop it. Wait for the outcome, or reconcile it. |
| `form_recapture_needed` | The employer's form no longer matched the approved one when it ran. Read the form again under Questions, or choose "Try this version again" there; nothing can be approved until then. |
| `form_change_unexplained` | Reading the employer's form again showed no difference NoEfforts can see (the page's own scripts may add it). Choose "Try this version again" under Questions, or apply on the employer's site. |
| `wizard_draft_at_employer` | NoEfforts already entered this application on the employer's multi-page form, which may keep it as a draft or have received it. It never runs it again: finish it on the employer's site. |
| `wizard_rehearsal_unsupported` | A rehearsal is not available on a multi-page form: the employer saves each page as you go. Approve it to submit, or apply on the employer's site. |
| `wizard_in_progress` | NoEfforts is entering this application on the employer's multi-page form, and each page it already sent may be saved or received there, so cancelling cannot undo it. Revoke the approval to stop it before the next page. |
| `restored_backup_held` | This server's database was restored from a backup, and NoEfforts has not yet ended what the backup showed as queued or in progress. Nothing can be approved, queued, cancelled or revoked until it has; the scheduler does it within seconds of starting. |

## Revoking while an attempt is in progress

- **No worker has taken it yet:** the attempt is cancelled at once (nothing was entered or
  sent) and the application waits for an approval again. The page says the queued submission
  was stopped before anything was sent.
- **A worker holds it, before the final click:** the approval is revoked and the gates refuse
  it, so the worker stops; anything it already entered on the employer's form stays entered.
- **After the final click** (`sending`, or waiting for a verification code): refused with
  `revoke_in_flight`; the approval stays as it was, since revoking could not stop what may
  already have been sent.
- **On a multi-page form (D142), once its first page may have been sent:** cancelling is refused
  (`wizard_in_progress`), and revoking is how it is stopped: the next page's gate refuses the
  revoked approval, the attempt ends with the wizard's outcome, and a page's Next already in
  flight is still recorded (and quarantined if the page shows a confirmation).

`package.revoke` records which of these happened (`queued_attempt`: `none`, `cancelled` or
`stopping`).
