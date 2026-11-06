import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";
import { openMoreIfMobile } from "./nav-helpers";

// D132: the employer's form changes after approval. The run stops before anything is sent, the
// application pauses, "Questions needing your answer" shows it, reading the form again brings the
// new question, and once it is answered and approved exactly one new run fills it. Through the
// real UI and the Celery worker against the labelled local Workday-style approximation, whose
// ledger is the oracle. Synthetic data, fictional employer.
test.describe.configure({ mode: "serial" });

const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume (D132)\n");
const req = () => `R-${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
const admin = (request: APIRequestContext, mode: string) =>
  request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode } });

async function uploads(request: APIRequestContext, slug: string) {
  const l = await (await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } })).json();
  return (l.disclosures as { kind: string; slug: string }[]).filter((d) => d.slug === slug && d.kind === "upload").length;
}

async function candidate(page: Page, tag: string) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `d132.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
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
  return h;
}

test("a form that changes during a run pauses; read it again, answer, and one new run fills it", async ({ page, request }, info) => {
  const id = req();
  const slug = `workday-examplehealth-${id}`;
  const h = await candidate(page, info.project.name);
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: `${RECEIVER}/workday/examplehealth/${id}`, title: "Registered Nurse, Weekends", employer: "Example Health (fictional)" },
    })
  ).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form/workday`, { headers: h })).status()).toBe(201);
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();
  for (const [key, value] of [
    ["legalName--firstName", { text: "Sam" }],
    ["q.licence_type", { label: "RN" }],
    ["q.shift", { label: "Nights" }],
  ] as const) {
    expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
  }
  await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "terms_ack", choice: "agree" } });

  try {
    await page.goto(`/applications/${app.id}`);
    await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
    await expect(page.getByText("Approved for a rehearsal only (never submits)")).toBeVisible();
    await admin(request, "wd_drift"); // the employer adds a required question before the run
    await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
    await expect(page.getByText("Stopped before sending anything", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
    expect(await uploads(request, slug)).toBe(0); // stopped before anything was sent
    await page.reload();
    await expect(page.getByRole("group", { name: "The employer's form no longer matches" })).toBeVisible();

    await openMoreIfMobile(page);
    await page.getByRole("link", { name: "Questions" }).click();
    await expect(page.getByRole("heading", { name: "Questions needing your answer" })).toBeVisible();
    await expect(page.getByText("The employer's form no longer matches what you approved.")).toBeVisible();
    await page.getByRole("button", { name: "Read the form again" }).click();
    await expect(page.getByText("The form was read again: answer what is new below, then approve on the application's page.")).toBeVisible();
    await page.getByLabel("Are you available to work weekends?").selectOption("Yes");
    await page.getByRole("button", { name: "Save answer" }).click();
    await expect(page.getByText(/Answer saved/)).toBeVisible();
    await expect(page.getByText("No questions are waiting for you.")).toBeVisible();

    await page.goto(`/applications/${app.id}`);
    await expect(page.getByRole("group", { name: "The employer's form no longer matches" })).toHaveCount(0);
    await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
    await expect(page.getByText("Approved for a rehearsal only (never submits)")).toBeVisible();
    await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
    await expect(page.getByText("Rehearsal finished: nothing submitted", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
    expect(await uploads(request, slug)).toBe(1); // exactly one new run disclosed, once
  } finally {
    await admin(request, "normal"); // the shared receiver goes back to normal whatever happened
  }
});

test("another account sees none of it", async ({ page }, info) => {
  await candidate(page, `${info.project.name}-other`);
  await page.goto("/questions");
  await expect(page.getByText("No questions are waiting for you.")).toBeVisible();
});
