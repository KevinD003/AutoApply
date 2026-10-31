# What is built, and what is permitted (D103)

Built is not authorized. This table separates five things for every feature that would act on
the owner's real accounts or on a real employer:

1. **Implemented:** the code exists.
2. **Fixture-tested:** it passes tests against local stand-ins only.
3. **Consent configured:** the owner's per-account setting or switch exists and is set.
4. **Operationally authorized:** the owner's explicit, recorded authorization, entered in
   `backend/app/core/authorizations.py` from the owner's own words.
5. **Real-service verified:** it has worked against the real service.

Recorded on 2026-10-31.

| Feature | Implemented | Fixture-tested | Consent configured | Operationally authorized | Real-service verified |
|---|---|---|---|---|---|
| Gmail: read code emails and enter a code (D101) | Yes | Yes: local Gmail stand-in, receiver ledger | No: off by default; no credentials provided; no account connected | **No** | No |
| Gmail: read application emails and propose outcomes (D101) | Yes | Yes: local Gmail stand-in | No | **No** | No |
| Typing a verification code yourself (checkpoint) | Yes | Yes | Not needed: your own action | Not needed | No real code step has been reached |
| Greenhouse pilot, permission 1: read a real job post (D102) | Yes | Yes: stand-in board and API | No: switch off | **No** | No: the earlier read-only observations (B2/B3) were a separate, owner-approved check, not the pilot |
| Greenhouse pilot, permission 2: open the application page | Yes | Yes | No | **No** | No |
| Greenhouse pilot, permission 3: disclose (fill and upload, the rehearsal) | Yes | Yes: receiver ledger | No | **No** | No |
| Greenhouse pilot, permission 4: submit | Yes | Yes: receiver ledger | No | **No** | No |
| Your approval of each package (per application, D57) | Yes | Yes | Given per application, in the app | Not a register entry: it is your act each time | Not on a real destination |

The computed readiness checklist for a live Greenhouse pilot (`providers/readiness.py`, the seven
conditions of docs/greenhouse-readiness-gap.md) shows **0 of 7 met** on 2026-10-31:

- dropdowns: not met;
- unmatched required controls: not met;
- location: not met;
- real upload: not met;
- real submission: not met;
- pilot gate: not met;
- capability entry: not met.

## Activation checklist

Everything still needed before either feature may act for real. Nothing below can be done by a
setting alone, and nothing here is done.

**Reading your Gmail (D101)**

1. Your explicit written authorization, naming each use you allow:
   - reading code emails;
   - entering a code from them;
   - reading application emails.

   Also name which mail it covers, and when it ends. It is entered in
   `backend/app/core/authorizations.py` with your words quoted in a new decision, by a reviewed
   change.
2. Your own Google Cloud OAuth client (`credentials.json`), kept on your machine. Never paste it
   into chat.
3. One connect run on your machine (`docs/inbox.md`), granting `gmail.readonly` in your browser.
4. On the server: `NOEFFORTS_INBOX_ENABLED=true`, your address in `NOEFFORTS_INBOX_OWNER_EMAILS`,
   and the token file.
5. Each use turned on in Account.
6. A first check against your real mailbox, recorded as real-service evidence.

**The Greenhouse pilot (D102)**

1. Your explicit written permission for each step you allow, separately:
   - 1 read the job post;
   - 2 open its page;
   - 3 disclose (fill and upload);
   - 4 submit.

   Also name which postings it covers, and when it ends. It is entered in the register as above.
   The register is in Git, so it must not name employers, postings or boards (D95). It can cover
   "postings I approve in the app, one by one". A list of named postings would need a private
   permission record that does not exist yet.
2. The readiness conditions that apply, met by the evidence `providers/readiness.py` counts, not
   by assertion: today 0 of 7. Expect the first real rehearsals to stop on dropdowns, unlisted
   controls such as the phone country picker, location search and upload acknowledgement.
3. A production deployment with Chromium's own sandbox:
   - `NOEFFORTS_ENV=production`;
   - `NOEFFORTS_BROWSER_ISOLATION=container`;
   - `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`;
   - your address in `NOEFFORTS_LIVE_OWNER_EMAILS` (`docker-compose.pilot.yml`).
4. For each application, your approval of its exact package. The first to each employer must be
   a rehearsal (fill and check, never submit), then a separate approval to submit.
5. The first real rehearsal's result, recorded as real-service evidence before any submission.
