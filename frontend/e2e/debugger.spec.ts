import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";
import { openMoreIfMobile } from "./nav-helpers";

// D168: the owner's console. One application traced from its form read to its receipt (the
// receiver's own ledger is the oracle for what was accepted), every switch and recorded
// permission, the account's activity, and another account's application refused. Read-only.
// Synthetic data only.
test.describe.configure({ mode: "serial" });

const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function admin(request: APIRequestContext, path: string, body?: object) {
  const r = body
    ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: body })
    : await request.get(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function accepted(request: APIRequestContext, slug: string) {
  const l = await admin(request, "ledger");
  return l.acceptances.filter((a: { slug: string }) => a.slug === slug).length;
}

/** A synthetic candidate with an application ready to approve, made through the API. */
async function setup(page: Page, slug: string): Promise<string> {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `debug.${slug}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  await put("/profile", {
    full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic",
    contact_email: "sam.synthetic@example.com", phone: "+1 555 0100",
    residence_country: "US", residence_city: "Springfield", links: [],
  });
  await post("/profile/work-authorizations", {
    country_code: "US", authorized: "yes", sponsorship_needed_now: "no", sponsorship_needed_future: "no",
  });
  await page.request.post("/api/documents", {
    headers: h, multipart: { file: { name: "resume.pdf", mimeType: "application/pdf", buffer: PDF }, kind: "resume" },
  });
  const job = await (await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title: "Clinic Assistant", employer: "Example Health Clinic (fictional)" })).json();
  const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
  expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
  return app.id as string;
}

test.beforeEach(async ({ request }) => {
  await admin(request, "config", { mode: "normal", delay_s: 0, form_delay_s: 0, idempotent: false });
});

test("an application is traced from its form read to its receipt, and every switch is shown", async ({ page, request }, info) => {
  const slug = `debug-${info.project.name}-${RUN}`;
  const appId = await setup(page, slug);
  await page.goto(`/applications/${appId}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  expect(await accepted(request, slug)).toBe(1);

  // The trace, from the review page.
  await page.getByRole("link", { name: "Debug this application" }).click();
  await expect(page.getByRole("heading", { name: "Process trace" })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Timeline" });
  await expect(timeline).toContainText("Form read, version 1");
  await expect(timeline).toContainText("Approved by you");
  await expect(timeline).toContainText("Final click (send) started");
  await expect(timeline).toContainText("Attempt ended: confirmed");
  await page.locator("summary").filter({ hasText: /^Attempts \(1\)$/ }).click(); // a closed section opens on its summary
  await expect(page.getByText("Final click started", { exact: true })).toBeVisible();
  // Never a keyed reference, a token or a code.
  expect(await page.content()).not.toContain("ref:v2:");
  // Read-only: the page sent nothing to the receiver.
  expect(await accepted(request, slug)).toBe(1);

  // The console: every switch, the recorded permissions, the rules, and this account's activity.
  await openMoreIfMobile(page);
  await page.getByRole("link", { name: "Debugger", exact: true }).click(); // not "← Debugger"
  await expect(page.getByRole("heading", { name: "Debugger" })).toBeVisible();
  const features = page.getByRole("list", { name: "Features" });
  await expect(features).toContainText("Automatic applying (your standing rule)");
  await expect(features).toContainText("Applying to real Greenhouse jobs (fill and submit)");
  await expect(features).toContainText("NOEFFORTS_AUTO_APPLY_ENABLED");
  await expect(page.getByRole("list", { name: "Recorded permissions" })).toContainText("Recorded in D");
  await expect(page.getByRole("list", { name: "Rules that always apply" })).toContainText("never retried");
  const activity = page.getByRole("list", { name: "Activity" });
  await expect(activity).toContainText("Attempt ended: confirmed");
  await activity.getByRole("link", { name: "Open trace" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/applications/${appId}/debug$`));
  await expect(page.getByRole("heading", { name: "Process trace" })).toBeVisible();
});

test("another account's application is not found", async ({ page }, info) => {
  const appId = await setup(page, `debug-other-${info.project.name}-${RUN}`);
  await page.context().clearCookies();
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `debug.second.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  await page.goto(`/applications/${appId}/debug`);
  // (Next.js keeps its own empty route announcer with the alert role too.)
  await expect(page.getByRole("alert").filter({ hasText: "No application of yours has this address." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Process trace" })).toHaveCount(0);
});
