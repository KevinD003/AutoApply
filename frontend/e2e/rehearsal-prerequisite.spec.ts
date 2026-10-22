import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// The rehearsal prerequisite (E6) in the UI: before the first submission through a path, a
// successful rehearsal is required, shown with its fixed reason code; withdrawing it brings the
// requirement back; submitting still needs its own approval. The rule is put on the fictional
// "e6-" fixture forms by a test-only setting (playwright.config.ts). The receiver's ledger is the
// oracle for what was sent. Synthetic data only.
test.describe.configure({ mode: "serial" });

const RUN = Date.now().toString(36);
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function ledger(request: APIRequestContext, slug: string) {
  const r = await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  expect(r.ok()).toBeTruthy();
  const l = await r.json();
  return {
    accepted: l.acceptances.filter((a: { slug: string }) => a.slug === slug).length,
    uploads: l.disclosures.filter((d: { slug: string; kind: string }) => d.slug === slug && d.kind === "upload").length,
  };
}

async function setup(page: Page, slug: string): Promise<{ appId: string; csrf: string }> {
  const email = `e6.${slug}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const csrf = (await reg.json()).csrf_token as string;
  const h = { "X-CSRF-Token": csrf };
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
  return { appId: app.id, csrf };
}

const prerequisite = (page: Page) => page.getByRole("group", { name: "Before the first submission" });
const approveToSubmit = (page: Page) => page.getByRole("button", { name: /^Approve package v\d+$/ });

async function rehearse(page: Page) {
  // Wait for this rehearsal's own result: an earlier one keeps its "finished" badge.
  const finished = page.getByText("Rehearsal finished: nothing submitted", { exact: true });
  const before = await finished.count();
  await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
  await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
  await expect(finished).toHaveCount(before + 1, { timeout: 60_000 });
}

test("the first submission on a path waits for a rehearsal; withdrawing it brings the requirement back", async ({ page, request }, info) => {
  const slug = `e6-${info.project.name}-${RUN}`;
  const { appId, csrf } = await setup(page, slug);
  await page.goto(`/applications/${appId}`);
  await expect(prerequisite(page)).toContainText("Reason code: no_rehearsal");
  await expect(approveToSubmit(page)).toBeDisabled();
  // The server refuses on its own too, with the same fixed code, and nothing reaches the form.
  const pkg = (await (await page.request.get(`/api/applications/${appId}/package`)).json()).package;
  const r = await page.request.post(`/api/applications/${appId}/package/approve`, {
    headers: { "X-CSRF-Token": csrf },
    data: { version: pkg.version, content_hash: pkg.content_hash },
  });
  expect(r.status()).toBe(409);
  expect(await r.text()).toContain("(reason: no_rehearsal)");
  expect((await ledger(request, slug)).uploads).toBe(0);

  await rehearse(page);
  await expect(prerequisite(page)).not.toContainText("Reason code:");
  await expect(approveToSubmit(page)).toBeEnabled();
  await expect(page.getByText("This rehearsal's record still holds.")).toBeVisible();

  await page.getByRole("button", { name: "Withdraw rehearsal" }).click();
  await page.getByRole("button", { name: "Confirm: withdraw this rehearsal" }).click();
  await expect(prerequisite(page)).toContainText("Reason code: rehearsal_revoked");
  await expect(approveToSubmit(page)).toBeDisabled();
  const withdrawn = page.getByRole("listitem").filter({ hasText: "This rehearsal's record no longer holds" });
  await expect(withdrawn.getByText("rehearsal_revoked", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Withdraw rehearsal" })).toHaveCount(0);

  await rehearse(page);
  await expect(approveToSubmit(page)).toBeEnabled();
  await approveToSubmit(page).click();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  const l = await ledger(request, slug);
  expect(l.accepted).toBe(1);
  expect(l.uploads).toBe(3); // two rehearsals and the submission each uploaded the resume
  const attempts = await (await page.request.get(`/api/applications/${appId}/attempts`)).json();
  expect(attempts.map((a: { state: string }) => a.state)).toEqual(["confirmed", "rehearsed", "rehearsed"]);
  expect(attempts[0].rehearsal_prerequisite).toBe("met");
  expect(new Set(attempts.map((a: { evidence_class: string }) => a.evidence_class))).toEqual(new Set(["fixture"]));
});
