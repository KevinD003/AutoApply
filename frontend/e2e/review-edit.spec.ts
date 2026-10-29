import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// C12 (D64): on the review page an answer can be changed or cleared, an optional question
// answered, an optional cover letter chosen and left out, and the page says where the form
// sends. The receiver's own ledger shows what was sent. Synthetic data only.
test.describe.configure({ mode: "serial" });

const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e document\n");

async function admin(request: APIRequestContext, path: string, body?: object) {
  const h = { "X-Admin-Token": RECEIVER_TOKEN };
  const r = body ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: h, data: body }) : await request.get(`${RECEIVER}/_admin/${path}`, { headers: h });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function candidate(page: Page, tag: string) {
  const reg = await page.request.post("/api/auth/register", { data: { email: `review.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  await put("/profile", {
    full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com",
    phone: "+1 555 0100", residence_country: "US", residence_city: "Springfield", links: [],
  });
  await post("/profile/work-authorizations", { country_code: "US", authorized: "yes", sponsorship_needed_now: "no", sponsorship_needed_future: "no" });
  const upload = (name: string, kind: string) =>
    page.request.post("/api/documents", { headers: h, multipart: { file: { name, mimeType: "application/pdf", buffer: PDF }, kind } });
  await upload("resume.pdf", "resume");
  return { h, put, post, upload };
}

const row = (page: Page, label: RegExp) => page.locator("li", { has: page.locator("p", { hasText: label }) }).last();

test("change, clear and answer optional questions; the ledger shows what was sent", async ({ page, request }, info) => {
  await admin(request, "config", { mode: "normal" });
  const slug = `review-${info.project.name}-${RUN}`;
  const { put, post } = await candidate(page, slug);
  const job = await (await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title: "Clinic Assistant", employer: "Example Health Clinic (fictional)" })).json();
  const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
  expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });

  await page.goto(`/applications/${app.id}`);
  const where = page.getByRole("group", { name: "Where this goes" });
  await expect(where).toContainText(`Sends to ${RECEIVER}`);
  await expect(where).toContainText("Local test fixture");

  // Change an answer given for this application.
  const hear = row(page, /^How did you hear about this job\?/);
  await hear.getByRole("button", { name: "Change answer" }).click();
  await hear.getByRole("combobox", { name: "How did you hear about this job?" }).selectOption({ label: "Job board" });
  await hear.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Answer saved.")).toBeVisible();
  await expect(row(page, /^How did you hear about this job\?/)).toContainText("Job board");

  // Clear it: the question waits for an answer again, and approval waits too.
  await row(page, /^How did you hear about this job\?/).getByRole("button", { name: "Clear my answer" }).click();
  await expect(page.getByText("Your answer for this application was cleared.")).toBeVisible();
  const pending = page.locator("section", { has: page.getByRole("heading", { name: /^Needs your answer \(1\)$/ }) });
  await expect(page.getByRole("heading", { name: /^Needs your answer \(1\)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve package v\d+/ })).toBeDisabled();
  await pending.getByRole("combobox", { name: "How did you hear about this job?" }).selectOption({ label: "Job board" });
  await pending.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByRole("heading", { name: /^Needs your answer \(0\)$/ })).toBeVisible();

  // Answer an optional question nothing in the profile answers.
  const reloc = row(page, /^Are you willing to relocate\?/);
  await expect(reloc).toContainText("(left blank)");
  await reloc.getByRole("button", { name: "Answer this optional question" }).click();
  await reloc.getByRole("combobox", { name: "Are you willing to relocate?" }).selectOption({ label: "No" });
  await reloc.getByRole("button", { name: "Save answer" }).click();
  await expect(row(page, /^Are you willing to relocate\?/)).toContainText("Your answer");

  // A protected fact is changed in the profile, not here.
  const auth = row(page, /^Are you legally authorized to work in the United States\?/);
  await expect(auth.getByRole("button", { name: "Change answer" })).toHaveCount(0);
  await expect(auth.getByRole("link", { name: "Change it in your profile" })).toBeVisible();

  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  const l = await admin(request, "ledger");
  const got = l.acceptances.filter((a: { slug: string }) => a.slug === slug);
  expect(got.length).toBe(1);
  expect(got[0].fields.hear_about).toBe("board");
  expect(got[0].fields.relocate).toBe("no");
});

test("an optional cover letter is chosen, then left out", async ({ page }, info) => {
  const { post, upload } = await candidate(page, `letter-${info.project.name}`);
  await upload("letter.pdf", "cover_letter");
  const job = await (
    await post("/jobs", { url: `${RECEIVER}/gh/examplehealth/jobs/4012001`, title: "Patient Services Coordinator", employer: "Example Health Network (fictional)" })
  ).json();
  expect((await post(`/jobs/${job.job.id}/form/greenhouse`, {})).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await page.goto(`/applications/${app.id}`);
  const letter = page.getByRole("combobox", { name: "Cover letter to send (optional)" });
  await letter.selectOption({ label: "letter.pdf (v1)" });
  await expect(page.getByText("Cover letter chosen.")).toBeVisible();
  let docs = (await (await page.request.get(`/api/applications/${app.id}/package`)).json()).package.content.documents;
  expect(docs.map((d: { field: string }) => d.field)).toContain("cover_letter");
  await letter.selectOption({ label: "None" });
  await expect(page.getByText("No cover letter will be sent.")).toBeVisible();
  docs = (await (await page.request.get(`/api/applications/${app.id}/package`)).json()).package.content.documents;
  expect(docs.map((d: { field: string }) => d.field)).not.toContain("cover_letter");
});

test("after an edit, the page shows what changed since the approved version", async ({ page, request }, info) => {
  // C14 (D66): read-only; nothing is approved, rebuilt or recorded by looking.
  await admin(request, "config", { mode: "normal" });
  const slug = `diff-${info.project.name}-${RUN}`;
  const { put, post } = await candidate(page, slug);
  const job = await (await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title: "Clinic Assistant", employer: "Example Health Clinic (fictional)" })).json();
  const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
  expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  const hear = row(page, /^How did you hear about this job\?/);
  await hear.getByRole("button", { name: "Change answer" }).click();
  await hear.getByRole("combobox", { name: "How did you hear about this job?" }).selectOption({ label: "Job board" });
  await hear.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Approval invalidated")).toBeVisible();
  await page.getByRole("button", { name: /^What changed since you approved v\d+$/ }).click();
  const changes = page.getByRole("list", { name: /^Changes from v\d+ to v\d+$/ });
  await expect(changes).toContainText("How did you hear about this job?: Referral → Job board (answer changed)");
});
