import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// C13 (D65): revoking says what it stopped; once the final click has begun it is refused with
// its reason code. The receiver's own ledger is the oracle. Synthetic data only.
test.describe.configure({ mode: "serial" });

const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function admin(request: APIRequestContext, path: string, body?: object) {
  const h = { "X-Admin-Token": RECEIVER_TOKEN };
  const r = body ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: h, data: body }) : await request.get(`${RECEIVER}/_admin/${path}`, { headers: h });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function accepted(request: APIRequestContext, slug: string) {
  const l = await admin(request, "ledger");
  return l.acceptances.filter((a: { slug: string }) => a.slug === slug).length as number;
}

async function approvedApplication(page: Page, slug: string): Promise<string> {
  const reg = await page.request.post("/api/auth/register", { data: { email: `revoke.${slug}.${Date.now()}@example.com`, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  await put("/profile", {
    full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com",
    phone: "+1 555 0100", residence_country: "US", residence_city: "Springfield", links: [],
  });
  await post("/profile/work-authorizations", { country_code: "US", authorized: "yes", sponsorship_needed_now: "no", sponsorship_needed_future: "no" });
  await page.request.post("/api/documents", { headers: h, multipart: { file: { name: "resume.pdf", mimeType: "application/pdf", buffer: PDF }, kind: "resume" } });
  const job = await (await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title: "Clinic Assistant", employer: "Example Health Clinic (fictional)" })).json();
  const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
  expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  return app.id;
}

test.beforeEach(async ({ request }) => {
  await admin(request, "config", { mode: "normal", delay_s: 0, form_delay_s: 0 });
});

test("revoking while the form is being filled stops the submission and says so", async ({ page, request }, info) => {
  const slug = `revoke-fill-${info.project.name}-${RUN}`;
  await approvedApplication(page, slug);
  await admin(request, "config", { form_delay_s: 10 }); // the worker's form load is slow
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Filling the form", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Revoke approval" }).click();
  await expect(page.getByText(/^Approval revoked\. The (queued submission was stopped|submission in progress stops)/)).toBeVisible();
  await page.waitForTimeout(12_000); // the slow form load ends; the worker must stop
  expect(await accepted(request, slug)).toBe(0);
});

test("revoking after the final click has begun is refused with its reason", async ({ page, request }, info) => {
  const slug = `revoke-send-${info.project.name}-${RUN}`;
  await approvedApplication(page, slug);
  await admin(request, "config", { mode: "delay", delay_s: 8 });
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Submitting", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Revoke approval" }).click();
  await expect(page.getByText(/may already be in flight, so revoking cannot stop it/)).toBeVisible();
  await expect(page.getByText(/reason: revoke_in_flight/)).toBeVisible();
  await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  expect(await accepted(request, slug)).toBe(1);
});
