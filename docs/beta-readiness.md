# Invite-only beta readiness checklist (NoEfforts)

Status as of 2026-11-05, after D128 (browser Gmail OAuth) merged to `main` as `9a7f390`.

This is the release-candidate checklist for an **invite-only beta** — real people, on their own
phones and laptops, using a reachable deployment. It reuses the evidence that already exists
(tests, e2e, docs) and marks every gap explicitly. It authorizes nothing: no mailbox is read, no
Google account is connected, no application is submitted, and no hosting is provisioned by
preparing this document.

The guiding distinction throughout: **what is proven locally/synthetically** vs **what needs
real external integration to verify**. They are not the same, and a green local suite does not
close a real-integration gap.

---

## 0. The four environments (do not conflate them)

An invite-only beta is the third row. Almost everything is proven for the first two rows and
**not yet built or verified for the third and fourth.**

| Environment | Who uses it | Where it runs | Public address / TLS | External network | Real employer submission |
|---|---|---|---|---|---|
| **Local development** | this project | disposable DBs, fixtures | none | all off; fixtures stand in | no — fixtures refuse real destinations |
| **Owner testing** | the owner alone | owner's own machine, Docker Compose | none (127.0.0.1 only) | off unless the owner sets a switch; Greenhouse pilot possible under `NOEFFORTS_ENV=production` + recorded permission | owner only, fully gated |
| **External invited users (beta)** | invited testers, their own devices | **a reachable host — NOT built/verified** | **required — NOT built** | per-user, off by default | **must stay off for invited users** |
| **Production operation** | ongoing service | hosted, managed | required + managed secrets, backups, monitoring — **NOT built** | as configured | as gated |

The current documented deployment (`docs/deployment.md`) is the **owner-testing** row only: it
states plainly it "is not a production deployment (no TLS, no public address, no managed
secrets)," and every port is bound to `127.0.0.1`. The invite-only beta row is the gap this
checklist is about.

---

## 1. Area-by-area readiness

Legend: ✅ proven locally · ⚙️ needs real external integration/config · 🔬 needs real-device/real-source verification · ⛔ blocker for an invite-only beta.

### 1. Actual deployment and secure cross-device access ⛔
- **Built / evidence:** Docker Compose stack (`docs/deployment.md`), built and started on every
  push by the `docker-smoke` and `execution-compose` CI jobs; `scripts/verify-local.sh`;
  `test_deployment_config.py` (every `NOEFFORTS_*` setting is passed through Compose).
- **Gap (blocker):** local-only. No TLS, no reachable public address, no managed secrets; not
  yet run on the owner's Mac (`docs/owner-mac-verification.md` still pending). **Cross-device
  access (a tester's phone reaching the server) does not exist yet** — it needs a real host with
  TLS and a reachable `public_base_url`. This blocker gates areas 2, 3, 4 and 9 below.

### 2. Google OAuth configuration and provider requirements ⚙️ (depends on #1)
- **Built / evidence:** browser OAuth authorization-code flow (`app/modules/connections`), off by
  default (`config.py:150-154` — `inbox_oauth_enabled=False`, empty client id/secret,
  `inbox_connections_dir`). PKCE (S256), single-use account-bound expiring state, exact read-only
  scope verification, 0600 per-account token file. `test_connections.py` (14 tests, local Google
  stand-in), `connections.spec.ts` e2e.
- **Gap (not a single click):** the owner must, in order — (a) create a Google Cloud **Web
  application** OAuth client; (b) register exactly one redirect URI,
  `<public_base_url>/api/connections/gmail/callback`; (c) set `inbox_oauth_enabled`,
  `inbox_oauth_client_id`, `inbox_oauth_client_secret`, `inbox_connections_dir`; (d) deploy at a
  `public_base_url` Google can redirect back to; (e) pass **Google's OAuth verification** for the
  restricted `gmail.readonly` scope (a review process that can take days–weeks). Steps (b) and (d)
  depend on blocker #1. **Never run against real Google.**

### 3. Mobile onboarding and connection flow ⚙️🔬 (depends on #1, #2)
- **Built / evidence:** responsive premium UI (D124/D125); installable PWA (`pwa.spec.ts`); the
  e2e suite runs on a **mobile viewport project (~390px)** alongside desktop (1280px);
  `layout-regression.spec.ts` (pinned header, no horizontal overflow, fixed bottom nav never
  hides content), `theme-motion.spec.ts`. The Gmail connect control is a **top-level navigation
  to the system browser, not an embedded webview** (D128) — the correct, supported mobile OAuth
  pattern.
- **Gap:** CI uses Chromium **emulation** at a phone viewport, not a real device. The
  connect→Google→callback round-trip on a phone needs the real deployment (#1) and OAuth client
  (#2). A phone's `localhost` is not the server's.

### 4. Drive document import ⚙️ (depends on #1)
- **Built / evidence:** `app/modules/drive` (Phase F, D124), owner-activated, narrowest scope
  (`drive.file`), Picker-chosen single file, type-allowlisted, never lists/scans/modifies Drive,
  off by default. `test_drive.py`, `drive.spec.ts` e2e.
- **Gap:** needs the owner's public Google OAuth **client id + API key** (`NOEFFORTS_GOOGLE_DRIVE_*`)
  and the same reachable deployment for the Picker/redirect. **Never run against real Drive.**

### 5. Job description and source-provided salary display ✅ (live data source ⚙️)
- **Built / evidence:** sanitized structured ingestion (`content.py`), salary **with provenance,
  never invented** (D126); `job-detail-content.spec.ts`, `test_discovery_content.py`,
  `test_jobs_content_detail.py`. Renders exactly what a source provides, or "Salary not provided."
- **Gap:** rendering is proven. The **live data feeding it** is not: real board discovery
  (`NOEFFORTS_BOARD_SOURCES_ENABLED`, Greenhouse/Lever feeds) and Freehire are off by default and
  "never run against a real board while building this (local stand-ins only)." Read-only public
  GETs — lower risk — but unverified on real sources.

### 6. Swipe → preparation → review → tracker ✅
- **Built / evidence:** the core journey, the most thoroughly proven path. `jobs-swipe.spec.ts`,
  `phase-a.spec.ts`, `phase-b.spec.ts`, `review.spec.ts`, `review-edit.spec.ts`,
  `review-reasons.spec.ts`, `submission.spec.ts`, `tracker-outcomes.spec.ts`, `journey.spec.ts`
  — all against the **real backend + synthetic receiver**, desktop and mobile. Right-swipe is
  intent-only (never a submission; never an "Applied" state).
- **Gap:** none in the flow itself for the beta beyond the deployment (#1). (Submission to a
  *real* employer is the separately gated concern in area 10.)

### 7. Recruitment-email suggestion, correction, undo and automatic status mode ✅ (real mailbox ⚙️)
- **Built / evidence:** `app/modules/inbox` (D93–D101, D127); `email.spec.ts`,
  `email-updates.spec.ts`, `inbox.spec.ts`, `test_inbox.py`. Suggestion → owner correction →
  undo, with **undo-after-newer refused**; automatic status mode updates only the recruitment
  stage (never submission evidence) and is distinct from automatic *applying*.
- **Separation (important):** pausing recruitment tracking does **not** stop separately-enabled
  verification-code reading — it has its own gate (surfaced in `InboxCard`). No control is
  labelled "stops all reads" unless it stops every mailbox-processing purpose.
- **Gap:** all processing is **off and unauthorized** until a user (a) connects Gmail (needs
  #1+#2), (b) grants `read_application_email` consent (D127/D103), and (c) turns tracking on.
  **Never run against a real mailbox**, so classification quality on real email is unverified.

### 8. Backup restoration, export and deletion ✅ (Mac/operator ⚙️)
- **Built / evidence:** in-app full export + account deletion (`app/modules/account`,
  `test_account.py`, `docs/account-deletion.md`): one ZIP of everything, cascade deletion in one
  transaction, refusal while a submission is in flight, nothing retained. Backup/restore
  (`docs/deployment.md` §5–7) is **smoke-tested in CI** (`docker-smoke`): back up → create a
  second account → restore → first account's session still works, second account is gone.
- **Gap:** backup/restore is verified on Linux CI, not the owner's Mac, and is an **operator CLI
  procedure** (`pg_dump`/`pg_restore`) — fine for an owner-operated beta, but it means the owner
  is the DBA. Export and deletion are in-app and fully tested.

### 9. iPhone and Android acceptance 🔬 (blocker for "acceptance")
- **Built / evidence:** Playwright mobile-viewport project across the journey + layout/theme/motion
  specs; PWA install (`pwa.spec.ts`).
- **Gap:** **no real-device testing.** CI is Chromium emulation at a phone viewport — not iOS
  Safari or Android Chrome. iOS Safari PWA quirks, real touch behavior, and the on-device OAuth
  redirect/resume are unverified. This is a named beta-acceptance gap.

### 10. Unsupported / live-unverified ATS paths remain clearly restricted ✅ (a strength to preserve)
- **Built / evidence:** real-destination submission is gated (`docs/activation-status.md`): only
  the Greenhouse pilot, time-limited by recorded permission, on the owner's own machine with
  `NOEFFORTS_ENV=production` + `NOEFFORTS_LIVE_OWNER_EMAILS` naming that one account +
  per-application approval + a prior rehearsal per employer path. Lever/Ashby/Workday adapters are
  **fixture-only, refused on a real page.** Enforced by `test_provider_admission.py`,
  `test_pilot_readiness.py`, `test_provider_contracts.py`, `test_execution_routing.py`,
  `test_greenhouse_live.py`, the forbidden-capabilities static guard, no-retry-after-send, and
  `submitted_unconfirmed` quarantine. Live Greenhouse readiness is **1 of 7** conditions.
- **Beta invariant to verify in the deployment config:** invited users must **not** be able to
  trigger a real submission. The gates make this so (real destinations are allowed only to the
  owner's named account, under `production` + explicit recorded permission). Confirm
  `NOEFFORTS_LIVE_GREENHOUSE_ENABLED` is off (or owner-only) in the beta environment.

---

## 2. Release blockers (ordered)

1. **No verified public/production deployment** (TLS, reachable `public_base_url`, managed
   secrets). Gates cross-device access, D128 Gmail OAuth, Drive import, and real mobile onboarding.
   *This is the single thing that unblocks the most.*
2. **Google OAuth real integration** (Gmail D128 + Drive): owner-created Web OAuth client(s),
   registered callback(s), and **Google verification for `gmail.readonly`** — multi-step,
   external, and time-dependent on Google's review. Depends on #1.
3. **Real-device mobile acceptance** (iOS Safari / Android Chrome) — only emulated so far.
4. **Owner-Mac deployment unverified** (`docs/owner-mac-verification.md` pending).
5. *(Quality, not a hard blocker)* real-email classification and real-board/Freehire discovery
   data — read-only, lower risk, but unverified on real sources.

Explicitly **not** beta prerequisites (per owner direction): a full Node.js backend migration,
extra animations, more fixture ATS adapters, or all-ATS automation.

## 3. The smallest next owner configuration action

**Decide and provision the beta's reachable URL** — the public hostname (domain) and TLS-terminated
host where the beta will run. Everything cross-device hangs off it: the D128 OAuth callback URI
(#2b) and Drive client are registered *against that URL*, `public_base_url` is set *to that URL*,
and phones can only reach the server *through that URL*.

This is a real, multi-step provisioning task — **not a single toggle.** After it, the dependent
chain is, in order: register the Google **Web application** OAuth client + callback URI → set the
four `inbox_oauth_*`/`inbox_connections_dir` settings and `public_base_url` → submit the
`gmail.readonly` scope for Google verification → deploy → verify the connect flow on a real phone.

Provisioning hosting, exposing services publicly, and Google's verification are the **owner's** to
do; this project does not do them, and does not touch a real mailbox or submit any application.
