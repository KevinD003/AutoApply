import { execSync } from "node:child_process";

import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// Submission UI against the synthetic receiver and a real Celery worker. The receiver's own
// ledger is the oracle for what was accepted. Synthetic data only.
test.describe.configure({ mode: "serial" });

const DB = (process.env.NOEFFORTS_E2E_DATABASE_URL ?? "postgresql+psycopg://postgres@127.0.0.1:5432/noefforts_e2e").replace(
  "postgresql+psycopg://",
  "postgresql://",
);
const RUN = Date.now().toString(36); // unique slugs per run, in case a ledger is reused
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

function sql(q: string) {
  execSync(`psql "${DB}" -v ON_ERROR_STOP=1 -qc "${q}"`);
}

async function admin(request: APIRequestContext, path: string, body?: object) {
  const r = body
    ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: body })
    : await request.get(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function ledger(request: APIRequestContext, slug: string) {
  const l = await admin(request, "ledger");
  return {
    accepted: l.acceptances.filter((a: { slug: string }) => a.slug === slug).length,
    disclosures: l.disclosures.filter((d: { slug: string }) => d.slug === slug).length,
    challenges: l.challenges as { id: string; code: string }[],
  };
}

/** Synthetic candidate + approved-ready application via the API (same browser context). */
async function setup(page: Page, slug: string): Promise<{ appId: string; csrf: string }> {
  const email = `sub.${slug}.${Date.now()}@example.com`;
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
  await put(`/applications/${app.id}/answers/hear_about`, { value: { label: "Referral" } });
  await put(`/applications/${app.id}/consents/privacy_ack`, { choice: "agree" });
  return { appId: app.id, csrf };
}

async function approveAndSubmit(page: Page, appId: string, opts: { double?: boolean } = {}) {
  await page.goto(`/applications/${appId}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  const submit = page.getByRole("button", { name: "Submit approved package" });
  if (opts.double) await submit.dblclick();
  else await submit.click();
}

const badge = (page: Page, text: string) => page.getByText(text, { exact: true }).first();

test.beforeEach(async ({ request }) => {
  await admin(request, "config", { mode: "normal", delay_s: 0, form_delay_s: 0, idempotent: false });
});

test("approve, double-click submit, see receipt; exactly one acceptance", async ({ page, request }, info) => {
  const slug = `ok-${info.project.name}-${RUN}`;
  const { appId } = await setup(page, slug);
  await approveAndSubmit(page, appId, { double: true });
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/^Receipt R-/)).toBeVisible();
  expect(await page.locator("li", { hasText: /Employer receipt received|Waiting|Filling|Submitting/ }).count()).toBe(1);
  expect((await ledger(request, slug)).accepted).toBe(1);
  // Final state: the page stops polling (it used to re-fetch attempts in a tight loop).
  let polls = 0;
  page.on("request", (r) => {
    if (r.url().includes("/attempts")) polls++;
  });
  await page.waitForTimeout(4000);
  expect(polls).toBe(0);
  await page.goto("/tracker");
  await expect(page.getByText("Submitted (confirmed)").first()).toBeVisible();
});

test("reload during execution keeps state and creates no second attempt", async ({ page, request }, info) => {
  const slug = `reload-${info.project.name}-${RUN}`;
  await admin(request, "config", { mode: "delay", delay_s: 6 });
  const { appId } = await setup(page, slug);
  await approveAndSubmit(page, appId);
  await expect(badge(page, "Submitting")).toBeVisible({ timeout: 30_000 });
  await page.reload();
  await expect(badge(page, "Submitting")).toBeVisible();
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  const attempts = await (await page.request.get(`/api/applications/${appId}/attempts`)).json();
  expect(attempts.length).toBe(1);
  expect((await ledger(request, slug)).accepted).toBe(1);
});

test("revoked and expired approvals cannot be submitted", async ({ page }, info) => {
  const { appId, csrf } = await setup(page, `revoke-${info.project.name}-${RUN}`);
  await page.goto(`/applications/${appId}`);
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await page.getByRole("button", { name: "Revoke approval" }).click();
  await expect(page.getByRole("button", { name: "Submit approved package" })).toBeDisabled();
  // Expired: approve again, then age the approval in the database.
  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByRole("button", { name: "Submit approved package" })).toBeEnabled();
  sql(`update package_approvals set expires_at = now() - interval '1 minute' where application_id = '${appId}'`);
  await page.reload();
  await expect(page.getByRole("button", { name: "Submit approved package" })).toBeDisabled();
  const r = await page.request.post(`/api/applications/${appId}/transition`, { headers: { "X-CSRF-Token": csrf }, data: { to: "queued" } });
  expect(r.status()).toBe(409);
});

test("cancel before dispatch stops it; nothing reaches the employer", async ({ page, request }, info) => {
  const slug = `cancel-${info.project.name}-${RUN}`;
  const { appId } = await setup(page, slug);
  await admin(request, "config", { form_delay_s: 10 }); // the worker's form load is now slow
  await approveAndSubmit(page, appId);
  await expect(badge(page, "Filling the form")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Cancelled.")).toBeVisible();
  // Bounded observation window: the worker's slow form load finishes after ~10s; afterwards it
  // must notice the cancellation and stop without entering anything.
  await page.waitForTimeout(12_000);
  const l = await ledger(request, slug);
  expect(l.accepted).toBe(0);
  expect(l.disclosures).toBe(0);
});

test("cancel refused once the submit step has begun", async ({ page, request }, info) => {
  const slug = `late-cancel-${info.project.name}-${RUN}`;
  const { appId, csrf } = await setup(page, slug);
  await admin(request, "config", { mode: "delay", delay_s: 8 });
  await approveAndSubmit(page, appId);
  await expect(badge(page, "Submitting")).toBeVisible({ timeout: 30_000 });
  // The UI no longer offers cancel, and the API refuses it: the data may already be in flight.
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0, { timeout: 10_000 });
  const r = await page.request.post(`/api/applications/${appId}/cancel`, { headers: { "X-CSRF-Token": csrf } });
  expect(r.status()).toBe(409);
  expect(await r.text()).toContain("may already be in flight");
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  expect((await ledger(request, slug)).accepted).toBe(1);
});

test("verification codes: wrong, replayed, other user, then right", async ({ page, browser, request }, info) => {
  const slug = `otp-${info.project.name}-${RUN}`;
  const { appId, csrf } = await setup(page, slug);
  await admin(request, "config", { mode: "otp" });
  await approveAndSubmit(page, appId);
  await expect(page.getByLabel("Verification code")).toBeVisible({ timeout: 60_000 });
  // Reload while waiting (the page re-reads the package): submission must stay closed.
  await page.reload();
  await expect(page.getByLabel("Verification code")).toBeVisible();
  const submit = page.getByRole("button", { name: "Submit approved package" });
  expect((await submit.count()) === 0 || (await submit.isDisabled())).toBeTruthy();
  const cps = async () => (await (await page.request.get(`/api/applications/${appId}/attempts`)).json())[0].checkpoints;
  const first = (await cps())[0];
  // Wrong code through the UI.
  await page.getByLabel("Verification code").fill("000000");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("Attempt 2 of 3")).toBeVisible({ timeout: 30_000 });
  const real = (await ledger(request, slug)).challenges.at(-1)!.code;
  // Replay of round 1 is refused.
  const replay = await page.request.post(`/api/applications/${appId}/checkpoints/${first.id}/code`, {
    headers: { "X-CSRF-Token": csrf }, data: { round: 1, code: real },
  });
  expect(replay.status()).toBe(409);
  // Another user cannot submit it.
  const other = await browser.newContext({ baseURL: "http://127.0.0.1:3100" });
  const o = await other.request.post("/api/auth/register", { data: { email: `other.${Date.now()}@example.com`, password: "synthetic-password-1" } });
  const oc = (await o.json()).csrf_token;
  const cross = await other.request.post(`/api/applications/${appId}/checkpoints/${first.id}/code`, {
    headers: { "X-CSRF-Token": oc }, data: { round: 2, code: real },
  });
  expect(cross.status()).toBe(404);
  await other.close();
  await page.getByLabel("Verification code").fill(real);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  expect((await ledger(request, slug)).accepted).toBe(1);
});

test("expired verification stops without acceptance", async ({ page, request }, info) => {
  const slug = `otp-exp-${info.project.name}-${RUN}`;
  const { appId } = await setup(page, slug);
  await admin(request, "config", { mode: "otp" });
  await approveAndSubmit(page, appId);
  await expect(page.getByLabel("Verification code")).toBeVisible({ timeout: 60_000 });
  sql(`update checkpoints set expires_at = now() - interval '1 minute' where application_id = '${appId}'`);
  await expect(badge(page, "Stopped after entering data, not submitted")).toBeVisible({ timeout: 60_000 });
  expect((await ledger(request, slug)).accepted).toBe(0);
});

test("unknown outcome is reconciled in the tracker, never resubmitted", async ({ page, request }, info) => {
  const slug = `unknown-${info.project.name}-${RUN}`;
  const { appId } = await setup(page, slug);
  await admin(request, "config", { mode: "drop_after_accept" });
  await approveAndSubmit(page, appId);
  await expect(badge(page, "Outcome unknown — check before doing anything")).toBeVisible({ timeout: 60_000 });
  // The application status follows the attempt without a reload (no stale Cancel button).
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0, { timeout: 10_000 });
  expect((await ledger(request, slug)).accepted).toBe(1);
  await page.goto("/tracker");
  await page.getByText("Clinic Assistant").first().click();
  await page.getByLabel("What did you check?").fill("Receiver ledger shows one receipt for this job");
  await page.getByRole("button", { name: "It was received" }).click();
  await expect(page.getByText("Submitted (confirmed)").first()).toBeVisible();
  expect((await ledger(request, slug)).accepted).toBe(1);
  const attempts = await (await page.request.get(`/api/applications/${appId}/attempts`)).json();
  expect(attempts.length).toBe(1);
});

test("Greenhouse-style form: read from job data and page, prepare, approve, submit once", async ({ page, request }) => {
  // Same synthetic candidate as the other tests, on the receiver's labelled Greenhouse approximation.
  const email = `sub.gh.${RUN}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  const csrf = (await reg.json()).csrf_token as string;
  const h = { "X-CSRF-Token": csrf };
  await page.request.put("/api/profile", {
    headers: h,
    data: {
      full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic",
      contact_email: "sam.synthetic@example.com", phone: "+1 555 0100",
      residence_country: "US", residence_city: "Springfield", links: [],
    },
  });
  await page.request.post("/api/profile/work-authorizations", {
    headers: h, data: { country_code: "US", authorized: "yes", sponsorship_needed_now: "no", sponsorship_needed_future: "no" },
  });
  await page.request.post("/api/documents", {
    headers: h, multipart: { file: { name: "resume.pdf", mimeType: "application/pdf", buffer: PDF }, kind: "resume" },
  });
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: `${RECEIVER}/gh/examplehealth/jobs/4012001`, title: "Patient Services Coordinator", employer: "Example Health Network (fictional)" },
    })
  ).json();
  const before = (await ledger(request, "gh-examplehealth-4012001")).accepted;

  await page.goto(`/jobs/${job.job.id}`);
  await page.getByRole("button", { name: "Read Greenhouse form" }).click();
  await expect(page.getByText("Greenhouse-style form (local test approximation)")).toBeVisible();
  await page.getByRole("button", { name: "Prepare application" }).click();
  await expect(page).toHaveURL(/\/applications\//);
  const appId = page.url().split("/applications/")[1];
  await expect(page.getByText("Greenhouse-style form — local test approximation, fictional employer")).toBeVisible();
  // Exact employer wording is shown for review.
  await expect(page.getByText("Are you legally authorized to work in the United States?")).toBeVisible();

  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  await put(`/applications/${appId}/answers/question_7004`, { value: { label: "Referral" } });
  await put(`/applications/${appId}/answers/question_7005`, { value: { label: "No" } });
  await put(`/applications/${appId}/consents/question_7009`, { choice: "withhold" });
  await put(`/applications/${appId}/consents/gdpr_processing_consent_given`, { choice: "agree" });
  await page.reload();
  await expect(page.getByText("Not asked: this question only appears for a different answer above.")).toBeVisible();

  await approveAndSubmit(page, appId);
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  const l = await ledger(request, "gh-examplehealth-4012001");
  expect(l.accepted).toBe(before + 1);
  const attempts = await (await page.request.get(`/api/applications/${appId}/attempts`)).json();
  expect(attempts.length).toBe(1);
});

