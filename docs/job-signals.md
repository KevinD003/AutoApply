# Job signals (S3, D59)

What NoEfforts knows about a job that should stop an approval, shown on the job page, on the
Discover row and on the review page before anything is disclosed. Implemented in
`backend/app/modules/jobs/signals.py`; tested in `backend/tests/test_job_signals.py`.

## The signals

- **Source says closed.** A discovered posting linked to the job was reported closed by its
  source (`closed_at`), or is gone at its address (a 404 on a refresh). The job itself is never
  changed: discovery never edits a tracker job (`docs/discovery.md`); the signal is read from
  the discovered rows. A record that is stale only because a complete listing left it out is
  shown as stale, not as closed.
- **Excluded or closed by you.** The job's own status. Change it on the job page.
- **Possible duplicate.** Another of your jobs has the same employer (its key: case, spacing and
  legal suffixes ignored) and the same title (case and spacing ignored), and the same location
  when both jobs have one, and it has an application past draft. Jobs are never merged or
  linked: you see the other job, its application's state and its outcome. A Freehire repost
  (a new slug for the same employer and title) is caught this way.

## What answers each one

- **"It is still open"** (`POST /api/jobs/{id}/still-open`, audited as `job.confirm_open`):
  answers a source-closed signal until the source reports it closed again after your statement.
  The same report repeated keeps its first time, so it does not ask again.
- **"This is a different role"** (`POST /api/jobs/{id}/different-role`, audited as
  `job.confirm_distinct`): answers the possible duplicates known now; an application to the same
  role made later asks again.
- Your own status (excluded, closed) is answered by changing it.

Preparation is never blocked. Approval is refused (409) with one of these reason codes, checked
in this order, until the signal is answered. The check is outside the package content, so
answering it never changes the package or its hash.

| Code | Message |
|---|---|
| `job_excluded` | You excluded this job. Change its status on the job page before approving an application to it. |
| `job_closed_by_you` | You marked this job closed. Change its status on the job page before approving an application to it. |
| `job_source_closed` | Its source says this posting is closed or gone. If it is still open, say so on the job page, then approve. |
| `job_possible_duplicate` | It looks like a role you already have an application for (same employer and title). If it is a different role, say so on the job page, then approve. |

## Not covered yet

- An approval given before a signal appeared is not withdrawn; the signal shows on the job and
  review pages, and a new approval is refused. Real employer destinations are refused anyway
  (manual handoff, `docs/live-pilot-gate.md`).
- "Possible duplicate" compares one tracker job with another; postings Freehire groups as
  copies (`/jobs/{slug}/copies`) are not fetched.

## Greenhouse embed URLs (R5.10)

`boards.greenhouse.io/embed/job_app?for=<board>&token=<job id>` is read as the Greenhouse
posting `<board>/<job id>`, so it has the same identity as the board URL
(`boards.greenhouse.io/<board>/jobs/<job id>`). Without `for=` the board is not in the URL and
the employer's name stands in: the identities match only when the board's name is the
employer's. A job stored before S3 under its URL identity keeps it; the same URL finds it again
instead of adding a second job.
