import { expect, test } from "@playwright/test";

// D134: pausing the standing rule says what it stopped of the work the rule had already queued.
// The server's reply carries the counts (backend `test_auto_apply.py` checks them against the
// receiver's ledger); here the Tracker's card shows them. With nothing queued, the real reply
// stops nothing and the card says nothing; the counts in the second pause are altered in the
// browser only, nothing is changed on the server. Synthetic data only.
test("pausing the rule says what it stopped of the work it had queued", async ({ page }, info) => {
  const email = `d134.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);

  await page.goto("/tracker");
  const title = page.getByRole("heading", { name: "Automatically submit applications", level: 2 });
  const card = page.locator("section", { has: title });
  await expect(card.getByText("Pausing also stops what it queued that has not started sending")).toBeVisible();
  const notice = card.getByRole("status");

  // Nothing queued: the real pause stops nothing and says nothing.
  await card.getByRole("button", { name: "Turn on" }).click();
  await card.getByRole("button", { name: "Pause" }).click();
  await expect(card.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(notice).toHaveCount(0);

  // The rule had queued two that had not started sending and one that was being sent. Only a
  // pause's reply carries counts; resuming is left as the server sends it.
  await page.route("**/api/auto-apply", async (route) => {
    const request = route.request();
    if (request.method() !== "PUT" || request.postDataJSON()?.paused !== true) return route.fallback();
    const response = await route.fetch();
    const stopped = { cancelled: 1, stopped: 1, in_flight: 1, approvals: 2 };
    await route.fulfill({ response, json: { ...(await response.json()), stopped } });
  });
  await card.getByRole("button", { name: "Resume" }).click();
  await card.getByRole("button", { name: "Pause" }).click();
  await expect(notice).toHaveText(
    "Stopped 2 applications it had queued, before sending. 1 was already being sent and could not be stopped; the outcome shows on the Tracker.",
  );

  // Resuming clears the notice; it describes one pause, not the state.
  await card.getByRole("button", { name: "Resume" }).click();
  await expect(card.getByRole("button", { name: "Pause" })).toBeVisible();
  await expect(notice).toHaveCount(0);
});
