import { expect, Route, test } from "@playwright/test";

// D101: the Account page's email card. The e2e server has no Gmail connected, so the connected
// view is a synthetic one served in place of the server's (the endpoints are tested against a
// local stand-in of the API in backend/tests/test_inbox.py); without one the card says so.
test("the email card proposes what an email said and you confirm it", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `inbox.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  await page.goto("/account");
  await expect(page.getByTestId("inbox-unavailable")).toContainText("switched off on this server");

  let state = "proposed";
  const calls: string[] = [];
  const view = () => ({
    available: true,
    why_not: null,
    codes_enabled: true,
    tracking_enabled: true,
    last_checked_at: "2026-10-31T10:00:00Z",
    last_error: null,
    events: [
      { id: "e1", received_at: "2026-10-30T09:00:00Z", sender_domain: "examplehealth.test", kind: "rejected",
        state, application_id: "00000000-0000-4000-8000-000000000001" },
      { id: "e2", received_at: "2026-10-29T09:00:00Z", sender_domain: "us.greenhouse-mail.io", kind: "code",
        state: "code_used", application_id: "00000000-0000-4000-8000-000000000002" },
    ],
  });
  await page.route("**/api/inbox**", (route: Route) => {
    const url = route.request().url();
    calls.push(`${route.request().method()} ${url.slice(url.indexOf("/api/inbox"))}`);
    if (url.endsWith("/accept")) state = "accepted";
    return route.fulfill({ json: view() });
  });
  await page.reload();
  const events = page.getByTestId("inbox-events");
  await expect(events).toContainText("from examplehealth.test · reads as a rejection");
  await expect(events).toContainText("waiting for you");
  await expect(events).toContainText("code entered for you");
  await events.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Recorded on the application.")).toBeVisible();
  await expect(events).toContainText("recorded by you");
  expect(calls).toContain("POST /api/inbox/events/e1/accept");
  await expect(page.getByLabel(/Enter verification codes for me/)).toBeChecked();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
