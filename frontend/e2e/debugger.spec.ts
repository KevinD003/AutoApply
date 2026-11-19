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

const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

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
  // Never a keyed reference, a token or a code; nothing wider than the screen.
  expect(await page.content()).not.toContain("ref:v2:");
  expect(await overflow(page)).toBeLessThanOrEqual(1);
  // Read-only: the page sent nothing to the receiver.
  expect(await accepted(request, slug)).toBe(1);

  // The console, from the Account page: every switch, the rules, and this account's activity.
  await openMoreIfMobile(page);
  await page.getByRole("link", { name: "Account", exact: true }).click();
  await page.getByRole("link", { name: "Open the debugger" }).click();
  await expect(page.getByRole("heading", { name: "Debugger" })).toBeVisible();
  expect(await overflow(page)).toBeLessThanOrEqual(1);
  const features = page.getByRole("list", { name: "Features" });
  await expect(features).toContainText("Automatic applying (your standing rule)");
  await expect(features).toContainText("Applying to real Greenhouse jobs (fill and submit)");
  await expect(features).toContainText("NOEFFORTS_AUTO_APPLY_ENABLED");
  // This account is not the server's owner here (sole-owner mode is off in tests).
  await expect(page.getByText("Only the server's owner sees the recorded permissions.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Rules that always apply" })).toContainText("never retried");
  const activity = page.getByRole("list", { name: "Activity" });
  await expect(activity).toContainText("Attempt ended: confirmed");
  await activity.getByRole("link", { name: "Open trace" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/applications/${appId}/debug$`));
  await expect(page.getByRole("heading", { name: "Process trace" })).toBeVisible();
});

test("each recorded permission says whose approvals it covers", async ({ page }, info) => {
  // D172. Only the server's owner sees the recorded permissions, and no account is the owner
  // here: the console's own answer is shown as the owner would get it, with three synthetic
  // permissions (yours, your standing rule's, both).
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `debug.permissions.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const entry = {
    what: "greenhouse_pilot", decision: "D172", given_on: "2026-11-18", words: "synthetic", data: "synthetic",
    actions: ["disclose", "open", "read"], ends_on: "2026-11-30", state: "active", active: true,
    max_attempts: 2, attempts_used: 0,
  };
  await page.route("**/api/debug/system", async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    json.account = { ...json.account, owner: true };
    json.permissions = [
      ...[["owner"], ["rule"], ["owner", "rule"]].map((approvers) => ({ ...entry, approvers })),
      // D173: one whose owner's words set no end date and no attempt limit.
      { ...entry, decision: "D173", approvers: ["owner", "rule"], ends_on: null, max_attempts: null, attempts_used: null },
    ];
    await route.fulfill({ response, json });
  });
  await page.goto("/debug");
  const rows = page.getByRole("list", { name: "Recorded permissions" }).getByRole("listitem");
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(0)).toContainText("steps: disclose, open, read · for your own approvals, one at a time");
  await expect(rows.nth(1)).toContainText("for your standing rule's approvals");
  await expect(rows.nth(1)).not.toContainText("your own approvals");
  await expect(rows.nth(2)).toContainText("for your own approvals, one at a time and your standing rule's approvals");
  await expect(rows.nth(0)).toContainText("0 of 2 used (every account's, whoever approved them)");
  await expect(rows.nth(0)).toContainText(", ends 2026-11-30");
  await expect(rows.nth(0)).not.toContainText("no end date");
  await expect(rows.nth(0)).not.toContainText("no attempt limit");
  await expect(rows.nth(3)).toContainText("no end date (until you withdraw it)");
  await expect(rows.nth(3)).toContainText("no attempt limit");
  await expect(rows.nth(3)).not.toContainText("used (every account's");
  expect(await overflow(page)).toBeLessThanOrEqual(1);
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
