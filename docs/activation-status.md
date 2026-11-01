# Activating the Greenhouse pilot: status and owner handoff (D103, D106)

This is the one activation guide. `docs/greenhouse-live.md` describes what the pilot does,
`docs/greenhouse-readiness-gap.md` the evidence behind the checklist, and
`docs/live-pilot-gate.md` the gate it applies. They all point here for what to do next.

Nothing below has been run against a real employer. This document does not authorize running
it: each real step needs your own words first (§4).

Reading your Gmail (D101) is a separate, optional feature. It is **not** needed for the pilot,
and it stays off and unauthorized. A verification code you type yourself works without it.

## 0. Four different things

| | What it is | Who gives it | Where it is recorded | How it ends | When that takes effect |
|---|---|---|---|---|---|
| **Development approval** | Permission to write and test code | You (2026-10-30 standing authorization) | The conversation; `docs/decisions.md` | You say so | Immediately; it never touched a real employer anyway |
| **Operational consent** | Your permission for the pilot's steps (1 read, 2 open, 3 disclose, 4 submit), each separately, with what it covers and an end date | Only you, in writing | `backend/app/core/authorizations.py`, a reviewed change quoting your words (one entry, not one per application) | On its end date, or when you withdraw it | End date: at the next protected step, in the running process. Withdrawal: when the API and worker restart (§8) |
| **Per-application approval** | Your approval of one application's exact package (version, content hash, destination, scope "rehearsal" or "submit once"), expiring | You, in the app: the application's page, or **Review** for several | The database (`package_approvals`), never in code | Its expiry; "Revoke approval" in the app; any change to the package or destination | At the next gate, in the running worker (row-locked, tested) |
| **Provider readiness** | Whether the evidence exists that would make a broader pilot reasonable to propose (§3) | Nobody "gives" it; it is computed from recorded evidence | `providers/readiness.py`, `GET /api/providers/greenhouse_live/readiness` | n/a | Advisory: it enables and blocks nothing. What blocks a real attempt is listed per condition under "stopped at run time by" |

An ordinary application never needs a code change. Operational consent is a one-time entry
per scope you choose, for example "postings I approve in the app, one at a time, until
2026-12-31". Each application is then approved in the app.

## Where each feature stands (2026-11-01)

| Feature | Implemented | Tested locally | Consent configured | Operationally authorized | Tried for real |
|---|---|---|---|---|---|
| Greenhouse pilot, 1 read the job post | Yes | Yes (stand-in board and API) | Only on your machine (switch, owner, production) | **Yes, D112**: until 2026-11-06, at most 5 attempts | No (earlier read-only runs were a separate, approved check) |
| Greenhouse pilot, 2 open the page | Yes | Yes | As above | **Yes, D112** (same entry) | No |
| Greenhouse pilot, 3 disclose (the rehearsal) | Yes | Yes (receiver ledger) | As above | **Yes, D112** (same entry) | No |
| Greenhouse pilot, 4 submit | Yes | Yes (receiver ledger) | As above | **Yes, D112** (same entry); only after that employer path's rehearsal held | No |
| Phone country, location search, late dropdowns (D104) | Yes | Yes, local stand-ins only | n/a | n/a | No; refused on a real page |
| Pilot locale exception: path C's rule, fetch guard, redirect stop, 150-request cap (D110, D111) | Yes, on main | Yes (receiver log; both fetch modes) | Part of permission 2 (open): not recorded | Code change authorized 2026-11-01; use **No** | No |
| Hidden search input in a question's group (D111) | Yes | Yes (fixture from run #11's one observation, receiver ledger) | n/a | n/a | No |
| Milestone-B handoff on the application page (D111) | Yes | Yes (synthetic) | n/a: read-only | n/a | No |
| Review page: approve several packages (D105) | Yes | Yes | n/a: each approval is yours | n/a | No |
| Read-only check, path B: the locale exception (`inspect_widgets_locales`, D106) | Yes | Yes: the v2 fixture's locale gate, the receiver's log | n/a: dispatched by hand | Approved once (D107) and **used** | Yes, once: run #10, a policy stop. No locale file was allowed (the real paths failed the rule), so it did not test the dropdowns' dependence on them (D107) |
| Read-only check, path C: dropdown observation (`inspect_dropdowns`, D109) | Yes | Yes: hashed locale names, 404 outcomes, a container-only list, react-select markup | n/a: dispatched by hand | Approved once (D110) and **used** | Yes, once: run #11, completed. Both locale files loaded; 12 of 12 dropdowns opened at the control's click; the 7 mapped lists equal their job data (D110) |
| Gmail: codes and replies (D101, optional) | Yes | Yes | No | **No** | No |
| Typing a verification code yourself | Yes | Yes | Not needed | Not needed | No real code step reached |

## 3 (first): the readiness checklist, computed

Computed for the pilot adapter `greenhouse_live` on 2026-11-01: **1 of 7 met** (condition 6, by
your recorded permission, D112, while it holds; 0 of 7 before it). The checklist is
the evidence for proposing the pilot more widely. Conditions 1-3 describe the one real posting
observed so far. The run-time checks apply them to every posting: a posting without such a
control is not blocked by them, but no condition is met by that.

| # | Condition | Why it is not met | Needs | Smallest next action | NoEfforts can do | You must do | Stopped at run time by | Verified by |
|---|---|---|---|---|---|---|---|---|
| 1 | Each required dropdown opens through one bounded, tested strategy, with the complete list | The pilot's `custom_dropdowns` is fixture-only. Run #9 (600 ms, every data request refused) saw no list open. Run #10 (path B, 1.5 s) allowed no locale file, because the real paths failed the approved rule. So it did not test whether the lists wait on them; 6 of the 7 dropdowns it reached showed no opening evidence | Observation, then code | One rehearsal on a posting whose required dropdowns all have readable lists | Done: path C and run #11 (lists open once the locale files load; 7 mapped lists equal their job data); the react-select readback; the pilot's locale exception integrated with redirect detection and a request cap (D111) | Choose the posting; permissions 1-3; approve its rehearsal | `dropdowns.verify` before the disclosure gate: a list it cannot open, read completely and match exactly stops the attempt with nothing entered | `test_dropdown_strategies.py`, `test_pilot_readiness.py` |
| 2 | The two required controls no question matches (run #11's `u1` in the phone group and `u3`; aliases are numbered per run) are understood and mapped by evidence | `u1`: its label and whether its options state calling codes were not recorded, and its react-select options exist only once opened. `u3`: no readable options, while a request to another Greenhouse host was refused. No rule maps them on a real page; D104's phone country rule is a local stand-in. D111: the page's hidden search input is not one of them | Observation (private), then code | `u1`: a private, in-app read of its label and options under permission 2 (a browser capture, not built yet). `u3`: none without new evidence | Built: the hidden-search rule and `u3` regressions (D111). Next: the browser capture for `u1` | Permission 2, once that capture exists | Capture refuses a required control the job data does not list (E3); one appearing later stops the attempt before disclosure | `test_greenhouse_dom.py`, `test_greenhouse_controls.py` |
| 3 | A supported, evidence-backed way to set the location without writing hidden coordinates | No location control at load on the observed posting; D104's search is a local stand-in | Observation, consent, code | For a first rehearsal, choose a posting with no location question. For this posting, note how its location control appears (typing in it is a disclosure: permission 3) | After an observation: a mirroring fixture and a reviewed change letting D104's search run on that structure | Choice of posting; a Path A note | A location search on a real page stops the attempt before anything is entered; hidden coordinates are never written | `test_greenhouse_controls.py` |
| 4 | Real upload evidence | It needs a disclosure-only rehearsal that uploaded to a real form and still holds. None can run: permissions 1-3 are not recorded, and the pilot runs nowhere | Consent, configuration, your machine | Record permissions 1-3; start the production configuration (§5); approve and watch one rehearsal (§6) | Nothing further in code; the rehearsal machinery and its counting exist | The permission, the start, the approval | The rehearsal stops before the send gate, which refuses a disclose-only approval | `test_rehearsal_stop.py`, `test_pilot_readiness.py` |
| 5 | Real submission evidence | It needs a real final submit, confirmed, after a valid rehearsal on that path (E6). Permission 4 is not recorded | Consent, your machine | After the rehearsal holds: record permission 4, approve "Submit once" (§7) | Nothing further in code | Permission 4; the approval | The rehearsal prerequisite at approval, queueing and both gates; the send gate needs permission 4; no retry after the final click | `test_rehearsal_prerequisite.py`, `test_greenhouse_live.py` |
| 6 | Your separate, recorded permission for each step; the posting named by your approval of its package | **Met (D112)**: all four steps, until 2026-11-06, at most 5 attempts past the disclosure gate. It lapses on its own after that day or at the fifth attempt | Consent | Renew in writing when it lapses | Done: your words recorded with the decision and its tests; the limit enforced at the disclosure gate | Approve each package in the app | `live.permission_refusal` at capture, routing, queueing, before the page opens and at both gates; the attempt limit at the disclosure gate | `test_greenhouse_live.py`, `test_authorizations.py` |
| 7 | Capabilities raised from fixture to observed, with a reviewed real-destination change | Part 1 is done: the pilot's reviewed real-destination entry (D102). Part 2 is not: `deterministic_fill`, `custom_dropdowns`, `file_upload`, `final_submit` and `confirmation_detection` are still at fixture | Code, after evidence | After evidence that the dropdowns open, the first rehearsal and the first submission: a reviewed change raising exactly what has evidence | That change and its tests, never before the evidence | Nothing beyond the evidence steps | Registry levels and `policy.CAPABILITIES`; `model.PILOTS` allows real destinations to the pilot alone | `test_pilot_readiness.py`, `test_provider_contracts.py` |

**Order:** 6 (permissions 1-3) → §5 → 4 (one rehearsal) → 6 (permission 4) → 5 (one
submission) → 7. Conditions 1-3 run in parallel through run C (D109; run B was used by run #10), or
are avoided for a first posting that has no such controls.

**Dropdowns on a real rehearsal.** Run #11 found the real dropdowns open once the page's
locale files load. Since D111 (your authorization of the code change, 2026-11-01) the pilot may
load them under read-only path C's exact rule:
- GET `fetch` from the main frame, no query, no redirect;
- the page's fetch guard;
- a followed redirect stops the attempt;
- at most 150 such requests per session.

Nothing has used it. It acts only while the pilot runs, which needs the recorded permissions
(none exist) and your approval of each application.

**The in-app handoff (D111).** For a real Greenhouse job, the application's page shows what a
rehearsal would disclose, how it stops before submitting, and which prerequisites hold now
(`GET /api/applications/{id}/rehearsal-handoff`). It grants nothing.

## 1. Local verification (your machine; nothing real)

1. `./scripts/verify-local.sh` (`docs/deployment.md` §9) does three things: it checks `.env`,
   validates Compose, and runs the smoke test as a throwaway project. Its summary is safe to
   share.
2. The suites, if you want them: `scripts/validate.sh all`. Each suite runs on a disposable
   database it creates and drops (`docs/test-isolation.md`).

## 2. Synthetic end-to-end acceptance walkthrough (local receiver only)

`cd frontend && npx playwright test e2e/journey.spec.ts e2e/greenhouse-pilot.spec.ts e2e/review.spec.ts`
(with the disposable e2e database, `CLAUDE.md`). Each step drives the real UI against the
synthetic receiver, whose ledger is the oracle:

- discover → job → capture the form;
- review → approve a rehearsal → the rehearsal fills and stops;
- approve "Submit once" → one submission → the receipt;
- the Review page approving two packages, each on its own.

Nothing leaves your machine. Passing it says the product works on stand-ins, not on a real page.

## 3. Missing Greenhouse observations

- **Path A** (`docs/manual-dropdown-checklist.md`): your own browser, on the observed posting,
  about 10 minutes. You record answers only (`docs/evidence/path-a.json` is still `pending`).
  It meets no condition, but it chooses the next check.
- **Run B** (`docs/greenhouse-readonly-compatibility-proposal.md`, path B): **used.** It ran
  once as run #10 on 2026-11-01 (D107; `docs/greenhouse-compatibility-report.md`).
  - Result: a policy stop. The rule allowed no locale file: all 12 real requests failed its
    path element. The dropdowns' dependence on those files was therefore **not tested**.
  - 6 of the 7 dropdowns reached showed no opening evidence within 1.5 s. On one, the page
    tried a POST to another Greenhouse host, which was blocked before sending and stopped the
    run.
  - Since then, the summary names which properties of a refused path failed.
- **Run C** (path C, D109; built, not approved): the observed locale shape allowed with outcomes
  recorded, plus one react-select container click. The request is in the proposal, path C.
- **Location:** a note from Path A on how the location control appears. Or choose a first
  posting without a location question.

## 4. Permission form (copy, fill, send in chat; do not put employer names in git)

```
Greenhouse pilot permission (NoEfforts)

Step 1  read the public job post (job data and page, GET only):     yes / no
Step 2  open the application page in the isolated browser:          yes / no
Step 3  disclose: fill the form and upload my approved documents,
        stopping before the final click (a rehearsal):                yes / no
Step 4  submit: one final click, after a rehearsal on that
        employer's path held:                                         yes / no

Postings covered:   only postings I approve in the NoEfforts app, one at a time
At most:            <N> applications
Data covered:       only what each approved package contains
Starts / ends:      <date> / <date>
Stop rules:         anything not understood stops the attempt; no retry
                    after the final click; my "Revoke approval" or "Cancel" ends it
Signed:             <your name>, <date>
```

What happens with it:
- Your words become one register entry (`authorizations.py`) and one decision in
  `docs/decisions.md`.
- Each posting is named only in the app, by your approval of its package. That stays in your
  private database and never goes to git (D95).
- A "no" or a blank means that step stays refused.

## 5. Safe configuration and startup

- **What "production configuration" means here:** the stack runs on **your own machine** with
  `NOEFFORTS_ENV=production`. That setting:
  - turns off the test fixtures and their origins;
  - refuses test-only keys;
  - lets the pilot reach real Greenhouse hosts;
  - requires the browser's container isolation.

  It does **not** mean public hosting, a domain, TLS, paid infrastructure or other users. Compose
  binds every port to `127.0.0.1`. Only the egress proxy gets an outbound network, and only to
  the session's board host and Greenhouse's static assets, and (the locale exception, D111)
  the page's locale files under read-only path C's exact rule.
- **Needs:** Docker (Compose v2). On a Mac this is unverified (`docs/owner-mac-verification.md`).
- **`.env`:**
  - `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`;
  - `NOEFFORTS_LIVE_OWNER_EMAILS=["<your account email>"]`;
  - the secrets that `scripts/check_env.py` asks for.

  `NOEFFORTS_BROWSER_ISOLATION=container` comes from the pilot override.
- **Check first (D112):** `./scripts/verify-local.sh --pilot`. It adds two checks to the usual
  ones: your `.env` has the switch on and exactly your account named, and the pilot overlay is
  valid. It prints key names only, never a value.
- **Start:** `docker compose -f docker-compose.yml -f docker-compose.pilot.yml up -d`, then the
  health check (`docs/deployment.md` §4).
- **Your permission is recorded (D112)** until 2026-11-06, for at most 5 attempts. The
  application's page shows "Attempts left". After that date, or at the limit, the job's route
  says `live_not_authorized` or the attempt stops with `live_limit_reached`, and nothing more is
  read or sent until you renew it in writing.

## 6. Disclosure-only rehearsal plan (permissions 1-3 recorded, D112)

1. Choose a posting:
   - on `job-boards.greenhouse.io` or `boards.greenhouse.io`;
   - preferably with no location question and few dropdowns.
2. Add it as a job, and "Capture the form" (step 1). If capture refuses, the reason says why;
   nothing was kept.
3. Review the package. Answer what is open. Approve **"Rehearsal: fill and check, never
   submit"**.
4. Queue it. The worker:
   - opens the page (step 2) and checks it against your approval;
   - fills and uploads (step 3);
   - reads every answer back;
   - **stops before the final click**.
5. The result shows on the application: "rehearsed", or the stop and its reason. Report back
   only the outcome and the reason code. Never the page, the employer or your data.
6. Your documents and typed answers reached the employer's page. Nothing was submitted.

## 7. Separately authorized submission plan (permission 4 recorded, D112; needs a rehearsal that holds)

1. Approve **"Submit once"** for the same application, a new approval.
2. Queue it. It re-checks everything, fills again, and passes the send gate (step 4). It clicks
   submit once.
3. The outcome is one of:
   - **confirmed**: the employer's page confirmed, bound to this attempt;
   - **rejected by the form**;
   - **submitted, unconfirmed**: the outcome is unknown. It is **never resent**; you reconcile
     it (§8).

## 8. Stop, revocation and uncertain outcomes

| You want to | Do | Takes effect |
|---|---|---|
| Stop one application | "Revoke approval" on its page, or "Cancel" in the Tracker | At the next gate, in the running worker: a queued attempt is cancelled; a running one stops before the next protected step (tested) |
| Stop everything now | `docker compose stop worker` | Immediately: no further step is taken. An attempt that had passed the send gate becomes "submitted, unconfirmed", never retried |
| Switch the pilot off | `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=false`, then restart API and worker | At restart; a queued application then stops before anything is entered (tested) |
| Withdraw a permission | Tell me. The register entry is removed by a reviewed change, then the API and worker are restarted | **At restart.** A running process keeps the register it imported, so stop the worker first if it must take effect now |
| Let a permission lapse | Nothing: its end date | At the next protected step, in the running process (`covers` reads today's date each time; tested) |

**Submitted, unconfirmed** means the final click happened but no confirmation was seen. The
application waits for you and is never resent. Check the employer's site or your email, then use
"Reconcile" in the Tracker, stating what you checked. A new submission would need a new approval
from you.

## 9. After each owner action

| You | Then possible |
|---|---|
| Choose a posting whose required controls are all mapped; read it, then approve its package as a rehearsal (after permissions 1-3 + the start) | One disclosure-only rehearsal (conditions 1, 4); the locale exception is already in code (D111) |
| Path A answers | What this posting's `u1` and `u3` ask, if this posting is ever to be used |
| Permissions 1-3 + the start | One disclosure-only rehearsal on a posting you choose (condition 4) |
| Permission 4 | One submission of an application whose rehearsal held (condition 5) |
| Both done | A reviewed change raising exactly the capabilities with evidence (condition 7) |
