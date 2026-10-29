# Approval reasons (C13, D65)

Why NoEfforts refuses to approve a package, to queue an approved one, or to revoke an approval.
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

## Revoking while an attempt is in progress

- **No worker has taken it yet:** the attempt is cancelled at once (nothing was entered or
  sent) and the application waits for an approval again. The page says the queued submission
  was stopped before anything was sent.
- **A worker holds it, before the final click:** the approval is revoked and the gates refuse
  it, so the worker stops; anything it already entered on the employer's form stays entered.
- **After the final click** (`sending`, or waiting for a verification code): refused with
  `revoke_in_flight`; the approval stays as it was, since revoking could not stop what may
  already have been sent.

`package.revoke` records which of these happened (`queued_attempt`: `none`, `cancelled` or
`stopping`).
