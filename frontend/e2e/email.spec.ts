import { APIRequestContext, expect, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D94: email reminders to the account owner, through the real UI, the API and the Celery worker,
// against the receiver's local SMTP sink, whose own ledger is the oracle. example.com addresses
// only; nothing is relayed anywhere. Never an email to an employer or a recruiter.
interface Mail {
  to: string[];
  subject: string;
  body: string;
}

async function mailTo(request: APIRequestContext, address: string): Promise<Mail[]> {
  const r = await request.get(`${RECEIVER}/_admin/mail`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  return ((await r.json()).messages as Mail[]).filter((m) => m.to.includes(address));
}

test("an owner verifies an address, opts in, gets one daily digest with a safe link, and opts out", async ({ page, request }, info) => {
  const address = `email.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `owner.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };

  await page.goto("/account");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Email reminders" }) });
  await expect(card.getByText("Off unless you turn it on.")).toBeVisible();
  await card.getByLabel("Your email address").fill(address);
  await card.getByRole("button", { name: "Save address" }).click();
  await expect(card.getByText("Not verified", { exact: true })).toBeVisible();
  await expect(card.getByText("Reminders off", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Send me a code" }).click();
  await expect.poll(async () => (await mailTo(request, address)).length, { timeout: 30_000 }).toBe(1);
  const [codeMail] = await mailTo(request, address);
  expect(codeMail.subject).toBe("NoEfforts: your verification code");
  const code = codeMail.body.split("verification code is ")[1].slice(0, 6);
  await card.getByLabel("Code from the email").fill(code);
  await card.getByRole("button", { name: "Verify" }).click();
  await expect(card.getByText("Verified", { exact: true })).toBeVisible();
  await card.getByLabel("Digest hour (UTC)").selectOption("0");
  await card.getByRole("button", { name: "Turn email reminders on" }).click();
  await expect(card.getByText("Reminders on", { exact: true })).toBeVisible();

  // A submitted application whose follow-up is due today.
  const job = await page.request.post("/api/jobs", { headers: h, data: { title: "Pastry Cook (fictional)", employer: "Synthetic Bakery" } });
  const appId = (await (await page.request.post("/api/applications", { headers: h, data: { job_id: (await job.json()).job.id } })).json()).id;
  await page.request.post(`/api/applications/${appId}/transition`, { headers: h, data: { to: "submitted_unconfirmed", reason: "I applied" } });
  const today = new Date().toISOString().slice(0, 10);
  await page.request.post(`/api/applications/${appId}/follow-up`, { headers: h, data: { action: "remind", remind_on: today } });

  // The worker sends one digest: the category and a link, nothing about the job or me.
  await expect.poll(async () => (await mailTo(request, address)).length, { timeout: 45_000 }).toBe(2);
  const digest = (await mailTo(request, address))[1];
  expect(digest.subject).toBe("NoEfforts reminders: 1 due");
  expect(digest.body).toContain("Follow-ups due: 1");
  const link = `http://127.0.0.1:3100/tracker?highlight=${appId}`;
  expect(digest.body).toContain(`A follow-up is due: ${link}`);
  for (const privateText of ["Pastry Cook", "Synthetic Bakery", "Kind regards", "Following up on my application"]) {
    expect(digest.body).not.toContain(privateText);
  }

  // Following the link only shows the page: nothing about the application changes.
  const before = await (await page.request.get(`/api/applications/${appId}`)).json();
  await page.goto(link);
  await expect(page.getByRole("region", { name: "Follow-up" }).getByText("Time to follow up")).toBeVisible();
  const after = await (await page.request.get(`/api/applications/${appId}`)).json();
  expect([after.state, after.outcome, after.events.length]).toEqual([before.state, before.outcome, before.events.length]);
  expect((await (await page.request.get(`/api/applications/${appId}/follow-up`)).json()).followed_up_on).toBeNull();

  // No second digest for the same item; opting out is one click.
  await page.waitForTimeout(5_000);
  expect(await mailTo(request, address)).toHaveLength(2);
  await page.goto("/account");
  await expect(card.getByText(/Daily digest \(1 item\): accepted by the mail server/)).toBeVisible();
  await card.getByRole("button", { name: "Turn email reminders off" }).click();
  await expect(card.getByText("Reminders off", { exact: true })).toBeVisible();

  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);
});
