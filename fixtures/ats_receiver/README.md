# Synthetic ATS receiver (test oracle)

A local, fictional applicant-tracking-system used to test NoEfforts execution. It is **not**
part of the product and must never be deployed.

- Independent of NoEfforts: it imports nothing from `backend/app` and keeps its own SQLite
  ledger, so tests count accepted applications from the receiver's side, not from NoEfforts'
  database.
- Fictional employer ("Example Health Clinic, fictional"); synthetic data only.
- Configurable failure modes (set through an admin endpoint protected by a token):
  `normal`, `delay`, `drop_after_accept`, `validation_fail`, `error_before_accept`,
  `error_after_accept`, `expired_session`, `upload_fail`, `conditional_field`, `otp`, `hostile`.
- `idempotent=true` makes repeated submissions of the same form token return the original
  receipt; `idempotent=false` accepts every POST, so duplicate-send bugs are visible.
- Two labelled Greenhouse-style approximations, mounted on the same receiver and ledger. Neither
  is Greenhouse code or markup:
  - `greenhouse_like.py` (`/gh/...`): named controls and native selects;
  - `greenhouse_v2.py` (`/gh2/...`): id-only controls and ARIA comboboxes, the structure seen
    at load on one real posting. Its widget behaviour is a fixture assumption, listed in the
    file header.

Run: `uv run --project backend python fixtures/ats_receiver/receiver.py --port 8765 --ledger /tmp/ledger.db --admin-token secret`
