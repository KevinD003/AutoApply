# Your Gmail, read-only (D101)

> **Not authorized (D103).** Building this was requested. Reading the owner's mailbox was not
> authorized, and the 2026-10-30 rule ("Do not: Read my inbox or retrieve OTPs") still stands.
> Each use checks for the owner's recorded authorization (`backend/app/core/authorizations.py`,
> empty): `read_codes` and `enter_codes` for codes, `read_application_email` for replies. Without
> it nothing is read, whatever is switched on or connected, and Account says so. A code you type
> yourself at the checkpoint works as before. The full list: `docs/activation-status.md`.

NoEfforts can read your own Gmail, read-only, for two things you turn on separately in
Account → "Email (your Gmail, read-only)":

- **Verification codes.** While one of your applications waits at a code step, NoEfforts reads
  the emails that arrived since the step opened. It enters a code for you only when exactly one
  new email from the application system (Greenhouse, Lever, Ashby, Workday: their sending
  domains are `NOEFFORTS_INBOX_CODE_SENDERS`) reads as a code email and holds exactly one code.
  Otherwise, or if the employer rejects that code, you type it as before. A message is used once.
- **Application emails.** NoEfforts reads what arrived since its last read (the first read goes
  back 30 days) and sorts each email by fixed wording rules: rejected, interview, assessment,
  received, unclear or other. A rejection, interview or assessment that names exactly one of your
  submitted applications (its employer's name, as you saved it) is shown as **waiting for you**:
  you confirm it (it is then recorded on the application as your outcome, dated the day the email
  arrived) or dismiss it. Nothing is recorded without you: outcomes are what you report (D53).
- **Whether a submission arrived.** When NoEfforts sent an application but never saw the
  employer's answer, the application waits as "submitted, unconfirmed" and is never sent again.
  A "thank you for applying / we received your application" email that names exactly that
  application is shown as **waiting for you**: confirming it settles the submission as received,
  with the email as what you checked (the same as reconciling it yourself).

It never sends, deletes, labels or marks anything read. It keeps what each email said (its
kind, the sender's domain, the day, the application) and a keyed reference so it is read once;
never the text, the subject, the sender's name or a code. Your Gmail token stays on your machine.

## Connect it (once, on your own machine)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use one),
   enable the **Gmail API**, and configure the **OAuth consent screen** (user type "External",
   your own address as a test user).
2. Create an **OAuth client ID** of type **Desktop app** and download its JSON
   (`credentials.json`). Keep it out of this repository; do not paste it anywhere.
3. From `backend/`:

   ```
   uv run python -m app.modules.inbox.connect --credentials ~/Downloads/credentials.json \
       --out ~/.noefforts/inbox-token.json
   ```

   Your browser opens Google's consent page asking for read-only access to your mail
   (`gmail.readonly`); approve it. The token is written to `--out`, readable by you only, and
   never printed.
4. In `.env`: `NOEFFORTS_INBOX_ENABLED=true`, `NOEFFORTS_INBOX_OWNER_EMAILS=["you@…"]` (your
   NoEfforts account's email) and `NOEFFORTS_INBOX_TOKEN_FILE` set to the token's path. With
   Docker Compose, mount the token read-only into the `api` and `worker` services in a
   `docker-compose.override.yml` of your own, for example
   `- ~/.noefforts/inbox-token.json:/run/secrets/inbox-token.json:ro`, and set
   `NOEFFORTS_INBOX_TOKEN_FILE=/run/secrets/inbox-token.json`.
5. Restart, then turn each use on in Account.

## Disconnect

Turn both off in Account, delete the token file, and remove NoEfforts in your Google Account's
"Third-party access" page.

## What is not verified

- Every test runs against a local stand-in of the API (`fixtures/ats_receiver/inbox_fixture.py`)
  with synthetic messages. No real mailbox and no real application system's code email has been
  read by this code.
- The wording rules were written from typical phrasing, not from your mail. An email they read
  as more than one thing is "unclear" and nothing is proposed.
- Google's OAuth documentation says that an app in "Testing" status gets refresh tokens that
  expire after 7 days (not re-checked from this environment). If reading stops with "Gmail
  refused the connection", run step 3 again.
