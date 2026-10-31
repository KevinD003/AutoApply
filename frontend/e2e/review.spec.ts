import { expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D105: the review page approves only the packages you tick, each with its own scope, and sends
// nothing. Synthetic data only; the receiver's ledger is the oracle for "nothing sent".
const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function setup(page: Page, slugs: string[]): Promise<string[]> {
  const email = `review.${RUN}.${Math.random().toString(36).slice(2, 8)}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
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
  const ids: string[] = [];
  for (const [n, slug] of slugs.entries()) {
    const job = await (
      await post("/jobs", { url: `${RECEIVER}/apply/${slug}`, title: `Clinic Assistant ${n + 1}`, employer: "Example Health Clinic (fictional)" })
    ).json();
    const html = await (await page.request.get(`${RECEIVER}/apply/${slug}`)).text();
    expect((await post(`/jobs/${job.job.id}/form`, { html })).ok()).toBeTruthy();
    const app = await (await post("/applications", { job_id: job.job.id })).json();
    await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
    await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
    ids.push(app.id);
  }
  return ids;
}

test("approve two ticked packages, each with its own scope; nothing is sent", async ({ page, request }, info) => {
  const slugs = [`rv1-${info.project.name}-${RUN}`, `rv2-${info.project.name}-${RUN}`];
  const [a, b] = await setup(page, slugs);
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "Review and approve" })).toBeVisible();
  const approveBtn = page.getByRole("button", { name: /Approve the \d+ ticked package/ });
  await expect(approveBtn).toBeDisabled(); // nothing is approved by default
  const rows = page.getByTestId("review-item");
  await expect(rows).toHaveCount(2);
  await rows.filter({ hasText: "Clinic Assistant 1" }).getByLabel("Rehearsal: fill and check, never submit").check();
  await rows.filter({ hasText: "Clinic Assistant 2" }).getByLabel("Submit once").check();
  await expect(page.getByRole("button", { name: "Approve the 2 ticked package(s)" })).toBeEnabled();
  await page.getByRole("button", { name: "Approve the 2 ticked package(s)" }).click();
  await expect(page.getByText(/^Approved: Rehearsal: fill and check, never submit, until/)).toBeVisible();
  await expect(page.getByText(/^Approved: Submit once, until/)).toBeVisible();
  // Each application shows its own approval, and neither was queued.
  for (const [id, label] of [[a, "Approved for a rehearsal only (never submits)"], [b, "Approved"]] as const) {
    await page.goto(`/applications/${id}`);
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  const l = await (await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } })).json();
  expect(l.disclosures.filter((d: { slug: string }) => slugs.includes(d.slug))).toHaveLength(0);
  expect(l.acceptances.filter((x: { slug: string }) => slugs.includes(x.slug))).toHaveLength(0);
});
