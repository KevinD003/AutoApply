# Your Gmail, read-only (D101, D117)

> **Verification codes are authorized (D117); application-email reading is not.** The owner's
> words on 2026-11-02 ("read my email and search for the greenhouse the most recent otp ...
> paste it in the greenhouse applications") lifted the earlier "Do not read my inbox or retrieve
> OTPs" **for verification codes only**. Recorded in `backend/app/core/authorizations.py`:
> `read_codes` and `enter_codes` for the owner's own mailbox, through 2026-11-06. Reading
> **application emails** (`read_application_email`) is still not authorized, so that half stays
> off whatever is switched on. On by default for the owner outside tests; it still needs the
> token from the connect step below. A code you type yourself at the checkpoint works as before.

## What access this grants — and what it does not

The point of the setup below is that you can see exactly what NoEfforts can do with your mail
before you grant anything:

| | |
|---|---|
| **Scope requested** | `https://www.googleapis.com/auth/gmail.readonly` — read only. Nothing else. |
| **Can** | read message headers and bodies, to find a verification code. |
| **Cannot** | send, reply, forward, delete, trash, archive, label, mark read, or change any setting — the read-only scope has no permission to, and the code calls no such method. |
| **Reads only** | messages from the application systems' code senders (`NOEFFORTS_INBOX_CODE_SENDERS`), and only while one of your applications is waiting at a code step. Not your whole mailbox, not continuously. |
| **Keeps** | per code email: a keyed reference (so it is read once), the day, the sender's domain. **Never** the code, the subject, the body, or the sender's name. The code is entered and discarded, never stored, logged, put in audit/evidence, or shown. |
| **Token** | the OAuth refresh token is written to a file on your machine, readable by you only, and never printed or committed. You point NoEfforts at that file. |
| **Revoke** | delete the token file, and remove NoEfforts in your Google Account's "Third-party access" page. Access ends at once. |
| **You can audit it** | the whole read path is one file, `backend/app/modules/inbox/service.py` (`fill_codes`), and the only scope is in `backend/app/modules/inbox/provider.py` (`SCOPE`). |

The flow is Google's documented one for installed apps: a loopback redirect to 127.0.0.1 on a
free port, a `state` value, and PKCE (S256). No client secret is shipped; you create your own
OAuth client in your own Google Cloud project, so the trust is between you and Google.

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

> Since D128 the normal way to connect is in the app — Account → Connections → **Connect Gmail** —
> which runs the same read-only OAuth flow in your browser and stores the token on the server,
> with nothing to run by hand (it needs the server's `inbox_oauth_enabled` and a **Web
> application** OAuth client). The CLI below stays as an operator fallback and still works.

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

## Keeping it connected (the 7-day token)

Google expires the refresh token of an OAuth app left in **"Testing"** status after 7 days, so
reading would stop after a week. Two ways to avoid re-running the connect step every week, both
in your own Google Cloud Console:

- **Simplest:** on the **OAuth consent screen**, press **"Publish app"** to move it to
  **"In production"**. For a `gmail.readonly` app used only by you, Google shows an
  "unverified app" notice you click past (you are the developer and the only user); the refresh
  token then does not expire on the 7-day schedule. No Google verification review is needed for
  your own use.
- **Or** keep it in "Testing" and re-run the connect step when reading stops with "Gmail refused
  the connection".

Either way the scope stays `gmail.readonly`; publishing changes only the token lifetime, not
what NoEfforts can access.

## What is not verified

- Every test runs against a local stand-in of the API (`fixtures/ats_receiver/inbox_fixture.py`)
  with synthetic messages. No real mailbox and no real application system's code email has been
  read by this code.
- The wording rules were written from typical phrasing, not from your mail. An email they read
  as more than one thing is "unclear" and nothing is proposed.
- Google's OAuth documentation says that an app in "Testing" status gets refresh tokens that
  expire after 7 days (not re-checked from this environment). If reading stops with "Gmail
  refused the connection", run step 3 again.
