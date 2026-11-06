import { expect, test } from "@playwright/test";

// D133: a page that fails while it is being shown keeps the app around it (navigation, sign out)
// and offers to try again, instead of the blank "Application error" screen. The failure here is
// forced in the browser only: the application's package reply arrives without its package, which
// the review page reads while rendering. Nothing is changed on the server. Synthetic data only.
test("a page that fails while rendering keeps the app around it and recovers", async ({ page }, info) => {
  const email = `d133b.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  const job = await (await post("/jobs", { title: "Synthetic Coordinator", employer: "Example Health (fictional)" })).json();
  const form = { title: "Synthetic form", fields: [{ key: "q", label: "Do you have a portfolio?", type: "text", required: true }] };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = (await (await post("/applications", { job_id: job.job.id })).json()).id as string;

  const pattern = `**/api/applications/${app}/package`;
  await page.route(pattern, async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), package: null } });
  });
  await page.goto(`/applications/${app}`);
  const failed = page.getByRole("heading", { name: "This page could not be shown", level: 1 });
  await expect(failed).toBeVisible();
  await expect(failed).toBeFocused();
  await expect(page.getByRole("alert").filter({ hasText: "Anything you already saved is kept." })).toBeVisible();
  await expect(page.getByText(/Application error/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "NoEfforts home" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

  // The app around it still works: away and back, the page still says what happened.
  await page.getByRole("link", { name: "NoEfforts home" }).click();
  await expect(page).toHaveURL(/\/jobs/);
  await page.goBack();
  await expect(failed).toBeVisible();

  // With the reply whole again, "Try again" shows the page.
  await page.unroute(pattern);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Destination" })).toBeVisible();
  await expect(failed).toHaveCount(0);
});
