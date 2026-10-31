import { expect, Route, test } from "@playwright/test";

// D102: the job page of a real Greenhouse job post. The e2e server runs with the Greenhouse pilot
// off, so a real board is refused as before; the pilot's own view (its route served by the API
// with the pilot on for this account) is then served in place of the server's, and reading the
// form is answered synthetically: nothing is requested from Greenhouse (the capture itself is
// tested against a local stand-in in backend/tests/test_greenhouse_live.py).
test("a real Greenhouse job post: refused while the pilot is off, readable while it is on", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `pilot.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const csrf = (await reg.json()).csrf_token as string;
  const job = (
    await (
      await page.request.post("/api/jobs", {
        headers: { "X-CSRF-Token": csrf },
        data: {
          url: "https://job-boards.greenhouse.io/exampleboard/jobs/4000001", // a fictional board, never contacted
          title: "Support Specialist",
          employer: "Example Board (fictional)",
        },
      })
    ).json()
  ).job.id as string;

  await page.goto(`/jobs/${job}`);
  const routeCard = page.locator("section", { has: page.getByRole("heading", { name: "How NoEfforts could apply" }) });
  await expect(routeCard.getByText("Reason code: real_destination_disabled")).toBeVisible();
  await expect(page.getByText(/This posting is on a real employer/)).toBeVisible();
  await expect(page.getByTestId("greenhouse-pilot")).toHaveCount(0);

  // With the pilot on for this account the API routes the job to "capture the form first".
  const served = await (await page.request.get(`/api/jobs/${job}/route`)).json();
  const reads: string[] = [];
  await page.route(`**/api/jobs/${job}/route`, (route: Route) =>
    route.fulfill({
      json: { ...served, message: "Capture the application form first.", reason: "no_form_captured" },
    }),
  );
  await page.route(`**/api/jobs/${job}/form/greenhouse`, (route: Route) => {
    reads.push(route.request().method());
    return route.fulfill({
      status: 201,
      json: {
        version: 1,
        source: "greenhouse_live",
        source_label: "Greenhouse job post read through the Greenhouse pilot",
        source_ref: null,
        schema: { title: null, fields: [{}, {}, {}] },
      },
    });
  });
  await page.reload();
  const pilot = page.getByTestId("greenhouse-pilot");
  await expect(pilot).toContainText("the Greenhouse pilot is on for your account");
  await expect(pilot).toContainText("the first one to this employer is a rehearsal that never submits");
  await pilot.getByRole("button", { name: "Read the Greenhouse form" }).click();
  await expect(page.getByText("Form v1 · 3 questions · source: greenhouse_live")).toBeVisible();
  expect(reads).toEqual(["POST"]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
