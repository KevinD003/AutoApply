import { expect, test } from "@playwright/test";

// D124 Phase F: the Google Drive import section appears on Documents only when the
// server has it enabled AND configured (the e2e backend env provides synthetic public
// client-id/api-key). The real Google Picker + OAuth are external and owner-activated,
// so this verifies the status-gated UI and the backend status endpoint — not the Google
// flow itself. Synthetic data only.

test("Drive import section shows when enabled + configured, with its scope promise", async ({ page }, info) => {
  const email = `drive.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);

  // The status endpoint reflects the enabled+configured server, and exposes only the
  // public browser values and the narrow scope.
  const st = await (await page.request.get("/api/integrations/drive/status")).json();
  expect(st.enabled).toBe(true);
  expect(st.configured).toBe(true);
  expect(st.scope).toContain("/auth/drive.file");
  expect(st.client_id).toBeTruthy();

  await page.goto("/documents");
  await expect(page.getByRole("heading", { name: "Import from Google Drive" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Import from Google Drive" })).toBeVisible();
  // The user-facing promise: only the picked file, never a scan, never a change to Drive.
  await expect(page.getByText(/only ever sees the one file you pick/)).toBeVisible();
});
