import { defineConfig } from "@playwright/test";

// End-to-end tests drive the real Next.js app against the real FastAPI backend, a real Celery
// worker (with beat) and the synthetic ATS receiver, on a dedicated PostgreSQL database
// (NOEFFORTS_E2E_DATABASE_URL). All data is synthetic; nothing leaves this machine.
const db = process.env.NOEFFORTS_E2E_DATABASE_URL ?? "postgresql+psycopg://postgres@127.0.0.1:5432/noefforts_e2e";
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
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3100",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    {
      // Fresh ledger per run: the receiver is the oracle, so stale rows must not carry over.
      command: `rm -f /tmp/noefforts-e2e-ledger.db && uv run python ../fixtures/ats_receiver/receiver.py --port 8799 --ledger /tmp/noefforts-e2e-ledger.db --admin-token ${RECEIVER_TOKEN}`,
      cwd: "../backend",
      url: `${RECEIVER}/apply/health-check`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "uv run alembic upgrade head && uv run uvicorn app.main:app --port 8100",
      cwd: "../backend",
      url: "http://127.0.0.1:8100/api/health",
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "uv run python scripts/e2e_worker.py 8797",
      cwd: "../backend",
      url: "http://127.0.0.1:8797/",
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // Rewrites are resolved at build time, so build against the test backend first.
      command: "npx next build && npx next start -p 3100",
      url: "http://127.0.0.1:3100/login",
      env: { NOEFFORTS_BACKEND_URL: "http://127.0.0.1:8100" },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
