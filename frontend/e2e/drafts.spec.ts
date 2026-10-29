import { expect, Route, test } from "@playwright/test";

// C15 (D68): a proposed draft shows the facts it cites and can be rejected. No drafting provider
// exists, so the package view is the server's own with one synthetic draft added, and the
// rejection is answered with the server's own view (the endpoint itself is tested in
// backend/tests/test_drafting.py).
test("a draft shows the facts it cites and can be rejected", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `drafts.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await (await page.request.post("/api/jobs", { headers: h, data: { title: "Clinic Assistant", employer: "Example Health (fictional)" } })).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form`, { headers: h, data: { fixture: "basic" } })).ok()).toBeTruthy();
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();

  let rejected = false;
  await page.route(`**/api/applications/${app.id}/package`, async (route: Route) => {
    const real = await (await route.fetch()).json();
    const draft = {
      id: "22222222-2222-4222-8222-222222222222",
      field_key: "why_us",
      text: "I supported 3 doctors at the front desk and want to keep doing it well.",
      evidence: ["employment:1", "profile:1:summary"],
      cited: [
        { kind: "employment", text: "Front Desk at Synthetic Care: Handled patient intake for 3 doctors." },
        { kind: null, text: null },
      ],
      provider: "test-fake",
    };
    await route.fulfill({ json: { ...real, drafting_available: true, drafts: rejected ? [] : [draft] } });
  });
  await page.route(`**/api/applications/${app.id}/drafts/*/reject`, async (route: Route) => {
    rejected = true;
    const real = await (await page.request.get(`/api/applications/${app.id}/package`)).json();
    await route.fulfill({ json: { ...real, drafting_available: true, drafts: [] } });
  });

  await page.goto(`/applications/${app.id}`);
  const card = page.locator("div", { has: page.getByText(/^Draft from test-fake/) }).last();
  await expect(card.getByText("Based only on these facts from your profile:")).toBeVisible();
  await expect(card.getByText("Work history: Front Desk at Synthetic Care: Handled patient intake for 3 doctors.")).toBeVisible();
  await expect(card.getByText("A fact that has changed since (request a new draft)")).toBeVisible();
  await card.getByRole("button", { name: "Reject this draft" }).click();
  await expect(page.getByText("Draft rejected and deleted. It will not be offered again.")).toBeVisible();
  await expect(page.getByText(/^Draft from test-fake/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Request a draft" }).first()).toBeVisible();
});
