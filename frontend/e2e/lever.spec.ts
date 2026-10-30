import { randomUUID } from "node:crypto";

import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D85: the Lever-style adapter (`fixture_lever`) through the real UI, the Celery worker and the
// labelled local approximation (fixtures/ats_receiver/lever_like.py), whose ledger is the
// oracle. Local test fixture only: a real Lever posting stays a manual handoff. Synthetic data.
test.describe.configure({ mode: "serial" });

const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume (Lever-style)\n");

async function ledger(request: APIRequestContext, slug: string) {
  const r = await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  const l = await r.json();
  return {
    accepted: (l.acceptances as { slug: string; fields: Record<string, unknown> }[]).filter((a) => a.slug === slug),
    uploads: (l.disclosures as { kind: string; slug: string }[]).filter((d) => d.slug === slug && d.kind === "upload").length,
  };
}

async function candidate(page: Page, tag: string) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `lever.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" },
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

const badge = (page: Page, text: string) => page.getByText(text, { exact: true }).first();

test("a Lever-style form is read, rehearsed without submitting, then submitted once after its own approval", async ({ page, request }, info) => {
  const posting = randomUUID();
  const slug = `lever-examplehealth-${posting}`;
  const h = await candidate(page, info.project.name);
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: `${RECEIVER}/lever/examplehealth/${posting}`, title: "Registered Nurse, Night Shift", employer: "Example Health (fictional)" },
    })
  ).json();

  await page.goto(`/jobs/${job.job.id}`);
  await page.getByRole("button", { name: "Read Lever-style test form" }).click();
  await expect(page.getByText("Lever-style form: local test approximation (fictional employer)")).toBeVisible();
  const route = page.locator("section", { has: page.getByRole("heading", { name: "How NoEfforts could apply" }) });
  await expect(route.getByText("Browser adapter (local test fixture only)")).toBeVisible();
  await expect(route).not.toContainText(/\blive\b/i);

  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();
  // What NoEfforts cannot know is yours to give: the shift, sponsorship asked with no country
  // named, and both consents.
  for (const [key, value] of [
    ["cards[q1][field0]", { label: "Nights" }],
    ["cards[q1][field2]", { label: "No" }],
  ] as const) {
    expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
  }
  await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "consent[marketing]", choice: "decline" } });
  await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "consent[store]", choice: "agree" } });

  await page.goto(`/applications/${app.id}`);
  await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
  await expect(page.getByText("Approved for a rehearsal only (never submits)")).toBeVisible();
  await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
  await expect(badge(page, "Rehearsal finished: nothing submitted")).toBeVisible({ timeout: 60_000 });
  let l = await ledger(request, slug);
  expect(l.uploads).toBe(1); // the resume reached the receiver under the rehearsal's approval
  expect(l.accepted).toHaveLength(0); // nothing was submitted

  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Local test fixture: counts for nothing on a real employer's form").first()).toBeVisible();
  l = await ledger(request, slug);
  expect(l.accepted).toHaveLength(1);
  const sent = l.accepted[0].fields;
  expect(sent["name"]).toBe("Sam Synthetic");
  expect(sent["cards[q1][field0]"]).toBe("Nights");
  expect(sent["cards[q1][field1]"]).toBe("Yes"); // from your US work authorization
  expect(sent["consent[store]"]).toBe("on");
  expect(sent["consent[marketing]"]).toBeUndefined();
  expect(sent["location"] ?? "").toBe(""); // a picker: never typed into

  await page.goto("/tracker");
  await expect(page.getByText("Submitted (employer receipt)", { exact: true }).first()).toBeVisible();
  await page.goto("/notifications");
  const list = page.getByRole("list", { name: "Notifications" });
  await expect(list).toContainText("Employer receipt received");
  await expect(list).toContainText("Rehearsal completed: nothing was submitted");
  expect((await ledger(request, slug)).accepted).toHaveLength(1);
});

test("a real Lever posting is never read and stays a manual handoff", async ({ page, request }, info) => {
  const h = await candidate(page, `${info.project.name}-real`);
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: `https://jobs.lever.co/acme/${randomUUID()}`, title: "Nurse (real host, never contacted)", employer: "Acme" },
    })
  ).json();
  await page.goto(`/jobs/${job.job.id}`);
  const route = page.locator("section", { has: page.getByRole("heading", { name: "How NoEfforts could apply" }) });
  await expect(route.getByText("Manual: apply on the employer's site").first()).toBeVisible();
  await expect(route).toContainText("Lever applications are not supported yet");
  const r = await page.request.post(`/api/jobs/${job.job.id}/form/lever`, { headers: h });
  expect(r.status()).toBe(409);
  const before = await (await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } })).json();
  expect((before.requests as { path: string }[]).some((x) => x.path.includes("/acme/"))).toBe(false);
});
