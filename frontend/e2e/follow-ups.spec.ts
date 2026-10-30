import { expect, test } from "@playwright/test";

// D92: follow-ups, through the real UI. A reminder to check on an application you submitted,
// derived from its own records, with a message to copy; NoEfforts sends nothing. Synthetic data.
test("a submitted application gets a follow-up: scheduled, due on the day you choose, done, closed by an outcome", async ({ page }) => {
  const email = `followups.${Date.now()}.${Math.random().toString(36).slice(2)}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  await page.request.put("/api/profile", { headers: h, data: { full_name: "Sam Synthetic", links: [] } });
  const job = await page.request.post("/api/jobs", { headers: h, data: { title: "Pastry Cook", employer: "Synthetic Bakery" } });
  const jobId = (await job.json()).job.id as string;
  const appId = (await (await page.request.post("/api/applications", { headers: h, data: { job_id: jobId } })).json()).id as string;

  await page.goto(`/tracker?highlight=${appId}`);
  const card = page.getByRole("region", { name: "Follow-up" });
  await expect(card.getByText("Nothing to follow up yet")).toBeVisible();

  await page.getByRole("button", { name: "I applied myself" }).click();
  await expect(card.getByText("Follow-up scheduled")).toBeVisible();
  await expect(card.getByTestId("follow-up-due")).toContainText("On ");
  await card.getByText("A message you can copy").click();
  await expect(card.getByTestId("follow-up-subject")).toHaveText("Subject: Following up on my application: Pastry Cook");
  await expect(card.getByTestId("follow-up-body")).toContainText("I applied for the Pastry Cook position at Synthetic Bakery on");
  await expect(card.getByTestId("follow-up-body")).toContainText("Kind regards,\nSam Synthetic");
  await expect(card.getByTestId("follow-up-body")).not.toContainText(email);

  // Remind me today: due now, shown in the list and in the notifications.
  const today = await page.evaluate(() => new Date().toISOString().slice(0, 10));
  await card.getByLabel("Remind me on").fill(today);
  await card.getByRole("button", { name: "Set reminder" }).click();
  await expect(card.getByText("Time to follow up")).toBeVisible();
  await page.goto("/tracker");
  await expect(page.getByText("Follow up due", { exact: true })).toBeVisible();
  await page.goto("/notifications");
  await expect(page.getByText("Time to follow up").first()).toBeVisible();
  await expect(page.getByText("Follow-up", { exact: true }).first()).toBeVisible();

  // I followed up: the next one is scheduled again and the notification is gone.
  await page.goto(`/tracker?highlight=${appId}`);
  await card.getByRole("button", { name: "I followed up" }).click();
  await expect(card.getByText("Follow-up scheduled")).toBeVisible();
  await expect(card.getByText(/you followed up/)).toBeVisible();
  const feed = await (await page.request.get("/api/notifications")).json();
  expect((feed.items as { kind: string }[]).filter((i) => i.kind === "follow_up")).toHaveLength(0);

  // An outcome that closes the application ends the reminders.
  await page.getByLabel("Outcome").selectOption("rejected");
  await page.getByRole("button", { name: "Record outcome" }).click();
  await expect(card.getByText("Closed by the outcome you recorded")).toBeVisible();
  await expect(card.getByRole("button", { name: "I followed up" })).toHaveCount(0);

  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);
});

test("another account never sees your follow-up", async ({ page, playwright }) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `followups.owner.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await page.request.post("/api/jobs", { headers: h, data: { title: "Baker", employer: "Synthetic Bakery" } });
  const appId = (await (await page.request.post("/api/applications", { headers: h, data: { job_id: (await job.json()).job.id } })).json()).id;
  await page.request.post(`/api/applications/${appId}/transition`, { headers: h, data: { to: "submitted_unconfirmed", reason: "I applied" } });

  const other = await playwright.request.newContext({ baseURL: "http://127.0.0.1:3100" });
  const r2 = await other.post("/api/auth/register", { data: { email: `followups.other.${Date.now()}@example.com`, password: "synthetic-password-1" } });
  const h2 = { "X-CSRF-Token": (await r2.json()).csrf_token as string };
  expect((await other.get(`/api/applications/${appId}/follow-up`)).status()).toBe(404);
  expect((await other.post(`/api/applications/${appId}/follow-up`, { headers: h2, data: { action: "stop" } })).status()).toBe(404);
  expect((await (await other.get("/api/follow-ups")).json()).items).toEqual([]);
  await other.dispose();
});
