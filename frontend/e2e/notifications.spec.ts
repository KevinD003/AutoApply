import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// Priority C (D83): in-app notifications, derived from the records they describe. A receipt from
// the synthetic receiver (through the real Celery worker) and an approval that stopped applying
// are notified once each, linked to the application, read and unread per account. Nothing is
// delivered outside the app. Synthetic data only.
test.describe.configure({ mode: "serial" });

const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function admin(request: APIRequestContext, path: string, body: object) {
  const r = await request.post(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: body });
  expect(r.ok()).toBeTruthy();
}

async function setup(page: Page, slug: string, title: string) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `notify.${slug}.${Date.now()}@example.com`, password: "synthetic-password-1" },
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
  const job = await (await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title, employer: "Example Health Clinic (fictional)" })).json();
  const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
  expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
  return { appId: app.id as string, put, post };
}

const bell = (page: Page) => page.getByRole("banner").getByRole("link", { name: /^Notifications/ });

test("a receipt and an approval that stopped applying are notified once, linked, and read per account", async ({ page, request }, info) => {
  await admin(request, "config", { mode: "normal", delay_s: 0, form_delay_s: 0, idempotent: false });
  const slug = `notify-${info.project.name}-${RUN}`;
  const first = await setup(page, slug, "Clinic Assistant (notify)");

  await page.goto("/notifications");
  await expect(page.getByText(/Nothing yet\./)).toBeVisible();
  await expect(page.getByText(/NoEfforts sends no email, text message or push notification/)).toBeVisible();
  await expect(bell(page)).toHaveAccessibleName("Notifications");

  // A submission to the local receiver, through the worker: one receipt notification.
  await page.goto(`/applications/${first.appId}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });

  await page.goto("/notifications");
  await expect(bell(page)).toHaveAccessibleName("Notifications, 1 unread");
  const list = page.getByRole("list", { name: "Notifications" });
  await expect(list.getByRole("listitem")).toHaveCount(1);
  const receipt = list.getByRole("listitem").first();
  await expect(receipt).toContainText("Employer receipt received");
  // A local test form: never called a submission to a real employer.
  await expect(receipt).toContainText("Local test fixture: counts for nothing on a real employer's form");
  await expect(receipt).toContainText("Clinic Assistant (notify)");
  await page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(bell(page)).toHaveAccessibleName("Notifications");
  await page.reload();  // derived from the record: reading creates nothing new
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText("0 unread of 1")).toBeVisible();
  await receipt.getByRole("link", { name: "Open application" }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${first.appId}$`));

  // A second account (this browser now signs in as it): its approval stops applying when its
  // package changes. It sees its own notification only, never the first account's receipt.
  const second = await setup(page, `${slug}-b`, "Clinic Assistant (notify b)");
  const pkg = (await (await page.request.get(`/api/applications/${second.appId}/package`)).json()).package;
  expect((await second.post(`/applications/${second.appId}/package/approve`, { version: pkg.version, content_hash: pkg.content_hash })).ok()).toBeTruthy();
  expect((await second.put(`/applications/${second.appId}/answers`, { key: "hear_about", value: { label: "Job board" } })).ok()).toBeTruthy();
  await page.goto("/notifications");
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(list).not.toContainText("Employer receipt received");
  await expect(list).toContainText("Your approval to submit no longer applies");
  await expect(list).toContainText("Package changed in version");
  await expect(list).toContainText("Clinic Assistant (notify b)");
  await expect(bell(page)).toHaveAccessibleName("Notifications, 1 unread");
  await list.getByRole("button", { name: "Mark as read" }).click();
  await expect(bell(page)).toHaveAccessibleName("Notifications");
  await list.getByRole("button", { name: "Mark as unread" }).click();
  await expect(bell(page)).toHaveAccessibleName("Notifications, 1 unread");
  await list.getByRole("link", { name: "Open application" }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${second.appId}$`));
  await expect(bell(page)).toHaveAccessibleName("Notifications");  // opening it read it
});
