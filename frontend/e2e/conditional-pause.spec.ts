import { APIRequestContext, expect, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";
import { openMoreIfMobile } from "./nav-helpers";

// D135: on the second Greenhouse-style form, "Which team did you work in?" is hidden until "Have
// you worked for Northwind Example before?" is "Yes", and this mode makes the page require it once
// shown (a FIXTURE ASSUMPTION). Approved with it blank, the run stops after filling with nothing
// submitted and the application pauses; Questions shows it, trying again waits for the answer, and
// once it is answered and approved exactly one run submits it. Through the real UI and the Celery
// worker; the receiver's ledger is the oracle. Synthetic data, fictional employer.
test.describe.configure({ mode: "serial" });

const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume (D135)\n");
const SLUG = "gh2-northwind-5020001";

async function admin(request: APIRequestContext, path: string, body?: object) {
  const r = body
    ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: body })
    : await request.get(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function accepted(request: APIRequestContext) {
  const l = await admin(request, "ledger");
  return (l.acceptances as { slug: string; fields: Record<string, string> }[]).filter((a) => a.slug === SLUG);
}

test("a question the page reveals and requires pauses; answer it, try again, and one run submits it", async ({ page, request }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `d135.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
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
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: `${RECEIVER}/gh2/northwind/jobs/5020001`, title: "Support Specialist", employer: "Northwind Example (fictional)" },
    })
  ).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form/greenhouse`, { headers: h })).status()).toBe(201);
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();
  for (const [key, value] of [
    ["preferred_name", { text: "Sammy" }],
    ["question_8101", { label: "Yes" }],
    ["question_8104", { label: "Yes" }],
  ] as const) {
    expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
  }
  const before = (await accepted(request)).length;

  try {
    await admin(request, "config", { mode: "gh2_conditional_required" });
    await page.goto(`/applications/${app.id}`);
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await expect(page.getByText("Approved", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Submit approved package" }).click();
    await expect(page.getByText("Stopped after entering data, not submitted", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
    expect((await accepted(request)).length).toBe(before); // nothing submitted
    await page.reload();
    await expect(page.getByRole("group", { name: "The employer's page asked a question" })).toBeVisible();

    await openMoreIfMobile(page);
    await page.getByRole("link", { name: "Questions", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Questions needing your answer" })).toBeVisible();
    await expect(page.getByText("The employer's page asked a question it shows only after an earlier answer, and requires it.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Read the form again" })).toHaveCount(0); // a read cannot show it
    await page.getByRole("button", { name: "Try this version again" }).click(); // not yet: it waits for the answer
    await expect(page.getByText(/Answer the questions the employer's page shows after an earlier answer first/)).toBeVisible();
    await page.getByLabel("Which team did you work in?").fill("Platform");
    await page.getByRole("button", { name: "Save answer" }).click();
    await expect(page.getByText(/Answer saved/)).toBeVisible();
    await page.getByRole("button", { name: "Try this version again" }).click();
    await expect(page.getByText("No questions are waiting for you.")).toBeVisible();

    await page.goto(`/applications/${app.id}`);
    await expect(page.getByRole("group", { name: "The employer's page asked a question" })).toHaveCount(0);
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await expect(page.getByText("Approved", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Submit approved package" }).click();
    await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
    const mine = await accepted(request);
    expect(mine.length).toBe(before + 1); // exactly one submission
    const sent = mine[mine.length - 1].fields;
    expect(sent.question_8104).toBe("1");
    expect(sent.question_8105).toBe("Platform");
  } finally {
    await admin(request, "config", { mode: "normal" }); // the shared receiver goes back to normal
  }
});
