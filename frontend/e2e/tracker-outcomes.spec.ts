import { expect, test } from "@playwright/test";

// Outcomes (S2, D53): refused before NoEfforts knows of a submission, recorded with the date the
// user gives after one, and counted per user with no rate. Synthetic data only.
test("outcomes: refused before a submission, dated after one, counted per user", async ({ page }) => {
  const email = `outcomes.${Date.now()}.${Math.random().toString(36).slice(2)}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await page.request.post("/api/jobs", { headers: h, data: { title: "Pastry Cook", employer: "Synthetic Bakery" } });
  const jobId = (await job.json()).job.id as string;
  const app = await page.request.post("/api/applications", { headers: h, data: { job_id: jobId } });
  const appId = (await app.json()).id as string;

  const early = await page.request.patch(`/api/applications/${appId}`, { headers: h, data: { outcome: "interviewing" } });
  expect(early.status()).toBe(400);
  expect((await early.json()).detail).toContain("(reason: outcome_before_submission)");

  await page.goto(`/tracker?highlight=${appId}`);
  const outcome = page.getByLabel("Outcome");
  await expect(outcome.locator("option")).toHaveText(["No outcome yet", "Withdrawn"]);
  await expect(page.getByText(/Employer outcomes can be recorded once NoEfforts knows of a submission/)).toBeVisible();
  await expect(page.getByText("Submitted: 0 of 1 tracked", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "I applied myself" }).click();
  await expect(page.getByText("Applied by you, not confirmed (your statement): 1", { exact: true })).toBeVisible();
  await expect(outcome.locator("option")).toContainText(["Assessment received"]);

  await outcome.selectOption("assessment_received");
  await page.getByLabel("When it happened (optional)").fill("2026-10-20");
  await page.getByLabel("Note (optional, private)").fill("Synthetic test link received");
  await page.getByRole("button", { name: "Record outcome" }).click();
  await expect(
    page.getByText("Outcome: No outcome yet → Assessment received · happened on 2026-10-20 · you reported", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Note: Synthetic test link received", { exact: true })).toBeVisible();
  await expect(page.getByText("Assessment received: 1 of 1 submitted", { exact: true })).toBeVisible();
  await expect(page.getByText("Any response: 1 of 1 submitted", { exact: true })).toBeVisible();
  await expect(page.getByText("1 submission is too few to compare rates; 1 response so far.", { exact: true })).toBeVisible();
  expect(await page.locator("section", { hasText: "Your applications so far" }).innerText()).not.toContain("%");

  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);
});
