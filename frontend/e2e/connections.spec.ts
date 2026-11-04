import { expect, Route, test } from "@playwright/test";

// D128: the Account → Connections "Gmail" card. The browser OAuth flow itself is external
// (Google's consent page), so the e2e drives the card's states against a synthetic /connections
// view — the endpoints themselves are tested in backend/tests/test_connections.py — and checks
// that "Connect Gmail" is a real top-level navigation to the backend start route.
test("the Gmail card shows connect, then the connected mailbox, and a disconnect control", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `conn.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  const SCOPE_LABEL =
    "Read-only access to your Gmail. NoEfforts can read your mail; it can never send, reply, delete, mark read or change labels, and stores no message content.";
  let gmail: Record<string, unknown> = {
    available: true,
    why_not: null,
    is_owner: true,
    state: "not_connected",
    email: null,
    scope_label: SCOPE_LABEL,
    connected_at: null,
    last_error: null,
  };
  await page.route("**/api/connections", (route: Route) => route.fulfill({ json: { gmail } }));

  await page.goto("/account");
  const notConnected = page.getByTestId("gmail-not-connected");
  await expect(notConnected).toBeVisible();
  await expect(notConnected).toContainText("read-only");
  // Connect is a real navigation to the backend start route (the system browser), not a fetch.
  await expect(page.getByTestId("gmail-connect")).toHaveAttribute("href", "/api/connections/gmail/start");

  // Now connected: the card shows the connected mailbox identity and a disconnect control.
  gmail = { ...gmail, state: "connected", email: "owner.inbox@example.com" };
  await page.reload();
  const connected = page.getByTestId("gmail-connected");
  await expect(connected).toContainText("owner.inbox@example.com");
  await expect(connected.getByRole("button", { name: "Disconnect Google access" })).toBeVisible();

  // The page fits its width on both the desktop and mobile projects (layout consistency).
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("the Gmail card says so when the web flow is not available", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `conn2.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  await page.route("**/api/connections", (route: Route) =>
    route.fulfill({ json: { gmail: { available: false, why_not: "not_enabled", is_owner: false, state: "not_connected", scope_label: "" } } }),
  );
  await page.goto("/account");
  await expect(page.getByTestId("gmail-unavailable")).toContainText("switched off");
});
