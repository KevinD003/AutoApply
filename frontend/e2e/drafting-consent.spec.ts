import { expect, Route, test } from "@playwright/test";

// L4 (D74): AI drafting is off until the user agrees, in the profile, to the exact text shown,
// and only where the server's owner set it up. The e2e server has no provider, so the offered
// view is a synthetic one served in place of the server's (the endpoints are tested in
// backend/tests/test_drafting_provider.py); without one the page says it is not configured.
test("AI drafting is turned on and off in the profile, with what is sent", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `consent.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/profile");
  const card = page.locator("#ai-drafting");
  await expect(card.getByText("AI drafting is not configured on this server.")).toBeVisible();

  let given: string | null = null;
  const view = () => ({
    status: given ? "available" : "consent_needed",
    offered: true,
    provider: "Anthropic (Claude)",
    model: "claude-opus-5-5",
    consent: {
      version: "v-synthetic",
      text: "When AI drafting is on, NoEfforts sends one request to Anthropic (synthetic wording).",
      sends: ["your approved work history"],
      never_sends: ["your work authorization, sponsorship, residence or nationality"],
    },
    given_at: given,
    earlier_text: false,
    spent_today_usd: 0.01,
    daily_budget_usd: 5,
  });
  const bodies: unknown[] = [];
  await page.route("**/api/drafting/consent", (route: Route) => {
    const m = route.request().method();
    if (m === "PUT") {
      bodies.push(route.request().postDataJSON());
      given = "2026-10-29T03:00:00Z";
    }
    if (m === "DELETE") given = null;
    return route.fulfill({ json: view() });
  });
  await page.reload();
  await expect(card.getByText("Off", { exact: true })).toBeVisible();
  await expect(card.getByText("your approved work history")).toBeVisible();
  await expect(card.getByText("your work authorization, sponsorship, residence or nationality")).toBeVisible();
  await expect(card.getByLabel("What you agree to")).toHaveText(/synthetic wording/);
  await card.getByRole("button", { name: "I agree: turn AI drafting on" }).click();
  await expect(card.getByText("On", { exact: true })).toBeVisible();
  expect(bodies).toEqual([{ version: "v-synthetic" }]);
  await card.getByRole("button", { name: "Turn AI drafting off" }).click();
  await expect(card.getByRole("button", { name: "I agree: turn AI drafting on" })).toBeVisible();
});

test("the review page sends you to the profile when consent is missing", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `consent-review.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await (await page.request.post("/api/jobs", { headers: h, data: { title: "Clinic Assistant", employer: "Example Health (fictional)" } })).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form`, { headers: h, data: { fixture: "basic" } })).ok()).toBeTruthy();
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();

  await page.route(`**/api/applications/${app.id}/package`, async (route: Route) => {
    const response = await route.fetch();
    const json = await response.json();
    return route.fulfill({ response, json: { ...json, drafting_available: false, drafting_status: "consent_needed" } });
  });
  await page.goto(`/applications/${app.id}`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Tailored resume and cover letter" }) });
  await expect(card.getByText("AI drafting is off for your account.")).toBeVisible();
  await expect(card.getByRole("link", { name: "Turn it on in your profile" })).toHaveAttribute("href", "/profile#ai-drafting");
});
