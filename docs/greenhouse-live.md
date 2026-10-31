# The Greenhouse pilot (D102)

Applying to real Greenhouse-hosted job posts through NoEfforts. **Off by default**, for your own
account only, and never yet run on a real page: everything below has been tested against a local
stand-in of a Greenhouse board only (`fixtures/ats_receiver/greenhouse_v2.py`).

## What happens when it is on

1. **You add a Greenhouse job** (Discover, a job board you follow, or paste its address:
   `https://job-boards.greenhouse.io/<board>/jobs/<id>`, `boards.greenhouse.io`, the EU hosts,
   or an `embed/job_app?for=…&token=…` link).
2. **You capture its form** (the job page's "Capture the form"). NoEfforts reads the job's public
   data from Greenhouse's Job Board API and its page from the board host: GET requests only, to
   Greenhouse's own hosts at public addresses, where their robots.txt allows it, no redirects,
   nothing of yours sent. The page's controls must match the job data one for one (by id,
   accessible name and role); if they do not, nothing is kept and the reason is shown.
3. **You review and approve** the exact package, as for every application. Questions NoEfforts
   cannot answer from your approved facts and answers stay open for you; sensitive questions are
   never answered without your choice.
4. **The first application to each employer is a rehearsal** (an approval to "fill and check,
   never submit"). The browser fills the form, uploads your documents, reads every answer back and
   stops before the final click. Your documents and typed answers do reach the employer's page
   (that is what a rehearsal checks); nothing is submitted.
5. **Then you approve the submission** of that package separately. NoEfforts fills the form
   again, checks it again, and clicks submit once. A result it cannot recognise is
   "submitted, unconfirmed" and is never sent again: you reconcile it (D101 can propose that from
   the employer's "we received your application" email).

It stops, never guesses, and never retries after the final click, on: a CAPTCHA or bot check, a
login or account page, a control the job data does not list (for example a phone country picker
or a location search), a dropdown it cannot open and read exactly, an answer that does not read
back, an upload the page does not acknowledge, the page changing after your approval, or the
pilot being switched off.

## Turning it on (on your own machine)

1. Read `docs/research/greenhouse-terms-review.md` (Greenhouse's public terms, as reviewed on
   2026-10-31; not legal advice). In short: no Greenhouse terms for candidates on hosted boards
   were found; Greenhouse forbids automated use of **MyGreenhouse**, which NoEfforts never uses; each
   employer may have its own applicant notice.
2. In `.env`:
   ```
   NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true
   NOEFFORTS_LIVE_OWNER_EMAILS=["you@…"]   # your NoEfforts account's email
   ```
3. Start the stack with the pilot override (production mode, container isolation, and an outbound
   route for the egress proxy only):
   ```
   docker compose -f docker-compose.yml -f docker-compose.pilot.yml up -d
   ```
   Production mode switches off the local test fixtures. The browser runs in its own container
   with Chromium's sandbox on and can reach only the one board host of its session, plus
   Greenhouse's static scripts and stylesheets (`job-boards.cdn.greenhouse.io`).
4. Turning it off: set `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=false` and restart. An application
   already queued then stops before anything is entered.

## What is not verified

- **No real Greenhouse page has been filled, uploaded to or submitted to by this code.** One real
  posting was observed read-only in earlier runs (`docs/greenhouse-compatibility-report.md`):
  its controls had ids and accessible names (19 of 19 fields mapped), its dropdowns did not open
  within the observation window (run #9), it had dropdown-like controls the job data does not
  list (one inside the phone field), and its location question needs a search picker. On such a
  posting the pilot stops before entering anything; the reason is shown.
- How a real form uploads, submits and confirms is the stand-in's design. Expect the first real
  rehearsals to stop with a reason; each reason tells what to build next.
- Whether a real page needs its own scripts to show the form to a plain GET (then capture says so
  and nothing is kept).
