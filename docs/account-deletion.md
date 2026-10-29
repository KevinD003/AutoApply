# Your data: full export and account deletion

How NoEfforts exports everything it holds about an account, and what deleting an account does,
at once and later (priority B, D77). Code: `backend/app/modules/account/` (`export.py`,
`deletion.py`, and `policy.py` for the retention decision). Tests:
`backend/tests/test_account.py`. The page is **Account** in the app.

## Export

**Account → Download all my data** returns one ZIP file:

- `noefforts-export.json`: every record that names your account, table by table, including:
  - profile, facts and their versions;
  - work authorizations, preferences, licences, work history and education;
  - jobs and discovered postings, watches and run approvals;
  - documents' details, saved answers;
  - applications, their inputs, packages, approvals, drafts, attempts, checkpoints (without
    codes), evidence, rehearsal records and events;
  - drafting consents and usage;
  - audit events.
- `documents/`: each document's file, byte for byte, named by its id. Its original name is in
  the JSON; a name you gave a file is never used as a path in the archive.
- `README.txt`: how many records each table holds, and what was left out and why.

**Left out, and why** (the same list is in `README.txt` and in the JSON under `left_out`):

| Left out | Why |
|---|---|
| table `user_sessions` | session secrets (token digests and CSRF tokens) |
| table `outbox_messages` | an internal delivery queue (attempt ids and dispatch counters only) |
| table `discovery_backoffs` | a timer that spaces out requests to a source; nothing about you |
| `users.password_hash` | your password's hash: a login secret |
| `applications.lock_version` | an internal concurrency counter |
| `documents.storage_key` | where the server keeps the file; the file is in `documents/` |
| `execution_attempts` `generation`, `lease_owner`, `lease_expires_at`, `heartbeat_at`; `attempt_events.generation` | worker lease and fencing internals |
| `execution_attempts.path_ref`, `rehearsal_records.path_ref` | a keyed reference (an HMAC under the server's key) |
| `checkpoints.code` | a verification code: a secret, erased once used |
| inside JSON values: `value_digest`, `consent_digests`, and any `ref:…` keyed reference | keyed digests and references (HMACs under the server's key) |

Every other column of every listed table is exported. A table or column added later is **not**
exported until it is listed. The test
`test_every_table_and_column_has_an_export_decision` fails until it is listed or left out with
a reason. Every query is scoped to your account, and a test checks that the archive holds
nothing of another account. Each export is recorded in your audit log as `account.export`,
with counts only.

## Deletion

**Account → Delete my account** asks for your password and the phrase "delete my account". It
first shows:
- what will be deleted (counts);
- how many applications were already sent;
- anything that blocks deletion now.

### What is deleted, at once, in one transaction

Everything that names the account. Every table that does references the account with
`ON DELETE CASCADE`, which the test `test_every_table_that_names_an_account_is_deleted_with_it`
checks in the migrated database. That covers:
- the account and every session, so access ends at once;
- profile, facts and versions, preferences, work authorizations, licences, work history,
  education;
- documents, and then their files;
- jobs, discovered postings, watches and run approvals;
- saved answers;
- applications, inputs, packages, approvals, drafts;
- attempts, their events and outbox messages, checkpoints, evidence and rehearsal records;
- drafting consents and usage;
- every audit event of the account.

Files are removed after the database commit. If the commit fails, rows and files both stay. A
file that cannot be removed is logged by error type only.

### Queued and running work

| What is in progress | What deletion does |
|---|---|
| A watched search being checked | Waits for that check to finish; the watch is then deleted and never checked again. |
| A submission queued, not yet picked up | Deleted. A message for it still in the broker finds nothing, and nothing is sent. |
| A submission a worker has picked up, before the send step | Waits for any gate holding it, then deletes it. The worker's next step finds no attempt and stops; it never reaches the send step. What it had already entered on a form page stays entered there, as after a cancel. |
| A submission past the send step (`sending`, or waiting for a verification code) | **Refused, nothing deleted** (`deletion_submission_in_flight`). It may already be on its way. Wait for its outcome, or reconcile it in the tracker, then delete. |

A submission is never retried because of a deletion. Deletion takes the execution lock order
(attempt, then application; `docs/architecture.md`), and the tests race it against both gates.

### Refusals

| Code | When |
|---|---|
| `deletion_submission_in_flight` | A submission may be in flight (above). |
| `deletion_busy` | A concurrent change deadlocked with the deletion twice; nothing was deleted; try again. |
| `deletion_unconfirmed` | The phrase "delete my account" was not typed. |
| `deletion_password` | The password was wrong. |

### What is kept in NoEfforts after deletion

**Nothing** (`policy.RETAINED_IN_DATABASE` is empty). No record of the account or of its
deletion remains in the database. The only trace is one log line, "account deleted: N document
file(s) removed", with no account id or address. Deletion is immediate, with no grace period and
no undo (`policy.GRACE_PERIOD_DAYS = 0`). The same address can sign up again, as a new, empty
account.

### What deletion cannot reach

| `policy.OUTSIDE_NOEFFORTS` | |
|---|---|
| `employers` | Applications already sent are held by the employer or its application system. NoEfforts cannot delete them; ask the employer. |
| `backups` | Backups made before the deletion still hold the account until they are deleted. Restoring one brings the account back (`docs/deployment.md`). |
| `logs` | Server logs carry no applicant data by design (error types and route templates only) and are kept as long as the server's log settings keep them. |
| `ai_provider` | If AI drafting was used, what was sent to the provider is kept under that provider's own terms. NoEfforts cannot delete it there. (Drafting is off unless the owner turns it on, D74.) |

## Owner decision: retention (not a legal policy)

NoEfforts has no legal retention policy, and this document does not invent one. The defaults
above are the most protective that keep every safety rule. Whether anything should be kept
after deletion is the owner's decision, isolated in `backend/app/modules/account/policy.py`.
Examples: an audit record of the deletion, a period in which deletion can be undone, how long
backups are kept. Changing it needs:
- a table outside the account (every table that names the account is deleted with it);
- its own tests;
- an update here.

Running a deletion against a real account is the account holder's own action in the app. The
tests use synthetic accounts only.
