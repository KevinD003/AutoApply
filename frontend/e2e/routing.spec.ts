import { expect, test } from "@playwright/test";

// The job page says how NoEfforts could apply. Synthetic jobs only; nothing is requested from
// any employer: the routes below are decided from the job's address and captured form alone.
test("job page shows the execution route: Workday unsupported, uncaptured form manual", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `route.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const csrf = (await reg.json()).csrf_token as string;
  const add = async (data: object) =>
    (await (await page.request.post("/api/jobs", { headers: { "X-CSRF-Token": csrf }, data })).json()).job.id as string;

  const workday = await add({
    url: "https://acme-example.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R-1234",
    title: "Engineer",
    employer: "Acme Example (fictional)",
  });
  await page.goto(`/jobs/${workday}`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "How NoEfforts could apply" }) });
  await expect(card.getByText("Manual: apply on the employer's site")).toBeVisible();
  await expect(card.getByText(/Workday applications are not supported yet/)).toBeVisible();

  const plain = await add({ title: "Clerk", employer: "Example Co (fictional)" });
  await page.goto(`/jobs/${plain}`);
  await expect(card.getByText("Capture the application form first.")).toBeVisible();
});
