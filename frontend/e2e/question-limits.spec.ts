import { expect, test } from "@playwright/test";

// D158: an answer box counts what you type as the employer's form sends it, the count its limit
// holds the answer to (an emoji counts two, a line break two: sent as CRLF), and says so when a
// line break is in it. The basic fixture's "Why us" box is limited to 1000 (its `maxlength`).
test("the answer box counts as the form sends it", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `limits.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await (await page.request.post("/api/jobs", { headers: h, data: { title: "Clinic Assistant", employer: "Example Health (fictional)" } })).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form`, { headers: h, data: { fixture: "basic" } })).ok()).toBeTruthy();
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();

  await page.goto(`/applications/${app.id}`);
  const box = page.locator("#in-why_us");
  await expect(box).toBeVisible();
  const counter = box.locator("xpath=following-sibling::p[1]");
  await box.fill("abcde");
  await expect(counter).toHaveText("5/1000");
  await box.fill("ab\ncd");
  await expect(counter).toHaveText("6/1000 (a line break counts as two)");
  await box.fill("a\u{1F600}");
  await expect(counter).toHaveText("3/1000");
});
