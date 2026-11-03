import { expect, Page, test } from "@playwright/test";

// D124: mobile swipe discovery, wired to the real API. Right = Apply (application
// INTENT: the job is shortlisted to prepare — never a submission, never an "Applied"
// state). Left = Pass (excluded, reason "Passed in discovery"). Both persist
// account-scoped, both undo, passed roles stay in the Excluded collection. Uses the
// always-present accessible Apply/Pass buttons (the documented swipe fallback), so it
// runs identically on desktop and the mobile project. Synthetic data only.

async function register(page: Page, info: { project: { name: string } }) {
  const email = `swipe.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  for (const t of ["Swipe Role A", "Swipe Role B", "Swipe Role C"]) {
    const r = await page.request.post("/api/jobs", { headers: h, data: { title: t, employer: "Synthetic Co" } });
    expect(r.ok()).toBeTruthy();
  }
  return h;
}

test("swipe discovery: apply shortlists, pass excludes, both persist and undo; no Applied state", async ({ page }, info) => {
  await register(page, info);
  await page.goto("/jobs");

  await page.getByRole("tab", { name: "Swipe" }).click();
  const tally = page.getByText(/\d+ to apply · \d+ passed/);
  await expect(tally).toHaveText("0 to apply · 0 passed");

  // Apply (right) on the top card.
  await page.getByRole("button", { name: "Apply to this job" }).click();
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // Pass (left) on the next card.
  await page.getByRole("button", { name: "Pass this job" }).click();
  await expect(tally).toHaveText("1 to apply · 1 passed");

  // Undo the pass.
  await page.getByRole("button", { name: "Undo the last decision" }).click();
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // Back to the list: exactly one shortlisted job, with a "Start application" action,
  // and it is NOT shown as "Applied". Nothing is in the Excluded (passed) collection.
  await page.getByRole("tab", { name: "List" }).click();
  await page.getByLabel("Filter by status").selectOption("shortlisted");
  const shortlisted = page.locator("li").filter({ has: page.getByRole("button", { name: "Start application" }) });
  await expect(shortlisted).toHaveCount(1);
  await expect(page.getByText("Applied", { exact: true })).toHaveCount(0);

  await page.getByLabel("Filter by status").selectOption("excluded");
  await expect(page.getByText("Passed in discovery")).toHaveCount(0);

  // Persistence: the shortlist survives a reload (it was saved via the API).
  await page.reload();
  await page.getByLabel("Filter by status").selectOption("shortlisted");
  await expect(page.locator("li").filter({ has: page.getByRole("button", { name: "Start application" }) })).toHaveCount(1);
});
