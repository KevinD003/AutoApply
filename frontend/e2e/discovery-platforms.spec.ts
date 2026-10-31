import { expect, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D100: listings by application platform, read from each listing's address. The receiver's
// Freehire stand-in serves synthetic listings on local fixture addresses, which name no known
// platform ("Other or not recognised"). Nothing contacts Freehire or a real job board.
test("listings are kept and filtered by application platform", async ({ page }, info) => {
  const mode = await page.request.post(`${RECEIVER}/_admin/config`, {
    headers: { "X-Admin-Token": RECEIVER_TOKEN },
    data: { fh_mode: "normal" },
  });
  expect(mode.ok()).toBeTruthy();
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `platforms.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/discover");
  const find = page.locator("section", { has: page.getByRole("heading", { name: "Find jobs" }) });
  // Only Greenhouse listings: none of these is on Greenhouse, so none is kept or added.
  await find.getByLabel("Greenhouse", { exact: true }).check();
  await find.getByRole("button", { name: "Find jobs" }).click();
  await expect(find.getByText(/5 listings read .*: 0 new.*0 added to your jobs.*5 filtered out/)).toBeVisible();
  await expect(page.getByText("Discovered (0)")).toBeVisible();

  // Listings on other addresses: kept and added as before.
  await find.getByLabel("Greenhouse", { exact: true }).uncheck();
  await find.getByLabel("Other or not recognised").check();
  await find.getByRole("button", { name: "Find jobs" }).click();
  await expect(find.getByText(/5 listings read .*: 5 new.*0 filtered out/)).toBeVisible();
  await expect(page.getByText("Discovered (5)")).toBeVisible();
  await expect(page.getByText("Platform: Other or not recognised")).toHaveCount(5);

  // The list's platform filter, with counts.
  const filter = page.getByLabel("Application platform", { exact: true });
  await expect(filter.locator("option")).toHaveText(["All (5)", "Other or not recognised (5)"]);
  await filter.selectOption("unknown");
  await expect(page.getByText("Discovered (5)")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
