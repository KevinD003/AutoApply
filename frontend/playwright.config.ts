import { defineConfig } from "@playwright/test";

// End-to-end tests drive the real Next.js app against the real FastAPI backend, a real Celery
// worker (with beat) and the synthetic ATS receiver, on a dedicated PostgreSQL database
// (NOEFFORTS_E2E_DATABASE_URL). All data is synthetic; nothing leaves this machine.
//
// D103: the database is a disposable one, owned by the test-only role and marked as such
// (cd backend && uv run python -m tests.isolation create --name noefforts_e2e_test); the API
// refuses any other before migrating. Each server holds its ports (and the API its Redis
// database and a claim on the database) for as long as it runs, so a second run, or a backend
// test run on the same ports, is refused rather than raced.
export const E2E_DATABASE =
  process.env.NOEFFORTS_E2E_DATABASE_URL ?? "postgresql+psycopg://noefforts_tester@127.0.0.1:5432/noefforts_e2e_test";
const db = E2E_DATABASE;
const hold = (what: string, command: string, cwd = "") =>
  `uv run python -m tests.isolation hold ${what}${cwd ? ` --cwd ${cwd}` : ""} -- sh -c '${command}'`;
export const RECEIVER = "http://127.0.0.1:8799";
export const RECEIVER_TOKEN = "e2e-receiver-admin-token"; // test-only receiver admin token
const backendEnv = {
  NOEFFORTS_DATABASE_URL: db,
  NOEFFORTS_STORAGE_DIR: "/tmp/noefforts-e2e-storage",
  // Test-only audit reference key (production refuses any "test-only" key).
  NOEFFORTS_AUDIT_REF_KEY: "test-only-audit-reference-key-for-e2e",
  NOEFFORTS_FIXTURE_ORIGINS: JSON.stringify([RECEIVER]),
  NOEFFORTS_SUBMIT_TIMEOUT_SECONDS: "20",
  NOEFFORTS_CHECKPOINT_TTL_SECONDS: "90",
  NOEFFORTS_OUTBOX_RELAY_INTERVAL_SECONDS: "1",
  NOEFFORTS_REDIS_URL: process.env.NOEFFORTS_E2E_REDIS_URL ?? "redis://127.0.0.1:6379/5",
  // Discovery against the receiver's stand-in of Freehire's documented API (never Freehire).
  NOEFFORTS_DISCOVERY_PROVIDERS: JSON.stringify(["freehire"]),
  NOEFFORTS_FREEHIRE_BASE_URL: `${RECEIVER}/freehire-fixture`,
  NOEFFORTS_FREEHIRE_PAGE_SIZE: "2",
  // env "test" differs from "development" only where a test-only switch is honoured: the fault
  // points (inactive without NOEFFORTS_FAULT) and the setting below, which puts the rehearsal
  // prerequisite (E6) on the fictional "e6-" fixture forms only. It can only add the rule.
  NOEFFORTS_ENV: "test",
  NOEFFORTS_EXECUTION_TEST_REHEARSAL_RULE_PATHS: JSON.stringify(["fixture_ats:e6-*"]),
  // Test-only as well: journey.* accounts draft with the labelled local fixture provider
  // (backend preparation/fixture_provider.py); every other account sees drafting as not configured.
  NOEFFORTS_DRAFTING_TEST_FIXTURE_USERS: JSON.stringify(["journey.*@example.com"]),
  // D94: email reminders go to the receiver's local SMTP sink only (port MAIL_PORT), to
  // example.com addresses only; nothing is relayed anywhere.
  NOEFFORTS_EMAIL_ENABLED: "true",
  NOEFFORTS_EMAIL_SMTP_HOST: "127.0.0.1",
  NOEFFORTS_EMAIL_SMTP_PORT: "8796",
  NOEFFORTS_EMAIL_SMTP_STARTTLS: "false",
  NOEFFORTS_EMAIL_FROM: "noefforts@example.com",
  NOEFFORTS_EMAIL_RECIPIENT_DOMAINS: JSON.stringify(["example.com"]),
  NOEFFORTS_EMAIL_DISPATCH_INTERVAL_SECONDS: "2",
  NOEFFORTS_EMAIL_TIMEOUT_SECONDS: "5",
  NOEFFORTS_PUBLIC_BASE_URL: "http://127.0.0.1:3100",
  // D95: public job-board connectors, pointed at the receiver's stand-ins of the documented feeds
  // (the override is honoured only in the test environment, for a listed fixture origin).
  NOEFFORTS_BOARD_SOURCES_ENABLED: "true",
  NOEFFORTS_BOARD_API_OVERRIDES: JSON.stringify({ greenhouse: `${RECEIVER}/gh-board`, lever: `${RECEIVER}/lever-board` }),
  NOEFFORTS_BOARD_MIN_INTERVAL_SECONDS: "0",
};

// Offline emulation reaches a service worker's own requests only with this switch (Playwright
// 1.56, crServiceWorker.js). Only pwa.spec.ts allows service workers; the others block them.
process.env.PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS = "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3100",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
    trace: "retain-on-failure",
    // The offline-page worker (D89) is blocked everywhere except pwa.spec.ts, so request
    // routing in the other specs sees every request.
    serviceWorkers: "block",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    // The browser extension (D90) is a desktop browser feature: its spec runs on desktop only.
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }, testIgnore: /extension\.spec\.ts/ },
  ],
  webServer: [
    {
      // Fresh ledger per run: the receiver is the oracle, so stale rows must not carry over.
      command: hold(
        "8799,8796",
        `rm -f /tmp/noefforts-e2e-ledger.db && exec uv run python ../fixtures/ats_receiver/receiver.py --port 8799 --ledger /tmp/noefforts-e2e-ledger.db --admin-token ${RECEIVER_TOKEN} --smtp-port 8796`,
      ),
      cwd: "../backend",
      url: `${RECEIVER}/apply/health-check`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: hold("8100,redis,db", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --port 8100"),
      cwd: "../backend",
      url: "http://127.0.0.1:8100/api/health",
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: hold("8797", "exec uv run python scripts/e2e_worker.py 8797"),
      cwd: "../backend",
      url: "http://127.0.0.1:8797/",
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // Rewrites are resolved at build time, so build against the test backend first.
      command: hold("3100", "npx next build && exec npx next start -p 3100", "../frontend"),
      cwd: "../backend",
      url: "http://127.0.0.1:3100/login",
      env: { NOEFFORTS_BACKEND_URL: "http://127.0.0.1:8100" },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
