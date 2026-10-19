import { defineConfig } from "@playwright/test";

// End-to-end tests drive the real Next.js app against the real FastAPI backend and a dedicated
// PostgreSQL database (NOEFFORTS_E2E_DATABASE_URL). All data is synthetic.
const db = process.env.NOEFFORTS_E2E_DATABASE_URL ?? "postgresql+psycopg://postgres@127.0.0.1:5432/noefforts_e2e";
const backendEnv = { NOEFFORTS_DATABASE_URL: db, NOEFFORTS_STORAGE_DIR: "/tmp/noefforts-e2e-storage" };

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
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
      command: "uv run alembic upgrade head && uv run uvicorn app.main:app --port 8100",
      cwd: "../backend",
      url: "http://127.0.0.1:8100/api/health",
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
