import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D88: the Workday-style adapter (`fixture_workday`), checkpoint-first, through the real UI, the
// Celery worker and the labelled local approximation (fixtures/ats_receiver/workday_like.py),
// whose ledger is the oracle. Local test fixture only: a real Workday posting stays a manual
// handoff. Synthetic data.
test.describe.configure({ mode: "serial" });

const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume (Workday-style)\n");
const req = () => `R-${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;

async function ledger(request: APIRequestContext, slug: string) {
  const r = await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  const l = await r.json();
  return {
    accepted: (l.acceptances as { slug: string; fields: Record<string, unknown> }[]).filter((a) => a.slug === slug),
    uploads: (l.disclosures as { kind: string; slug: string }[]).filter((d) => d.slug === slug && d.kind === "upload").length,
  };
}

async function candidate(page: Page, tag: string, links: string[] = []) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `workday.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  await page.request.put("/api/profile", {
    headers: h,
    data: {
      full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic",
      contact_email: "sam.synthetic@example.com", phone: "+1 555 0100",
      residence_country: "US", residence_city: "Springfield", links,
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

async function workdayJob(page: Page, h: Record<string, string>, id: string, title: string) {
  return (
    await (
      await page.request.post("/api/jobs", {
        headers: h,
        data: { url: `${RECEIVER}/workday/examplehealth/${id}`, title, employer: "Example Health (fictional)" },
      })
    ).json()
  ).job.id as string;
}

const badge = (page: Page, text: string) => page.getByText(text, { exact: true }).first();
const routeCard = (page: Page) =>
  page.locator("section", { has: page.getByRole("heading", { name: "How NoEfforts could apply" }) });

test("a single-page Workday-style application is read, rehearsed, then submitted once after its own approval", async ({ page, request }, info) => {
  const id = req();
  const slug = `workday-examplehealth-${id}`;
  const h = await candidate(page, info.project.name);
  const jobId = await workdayJob(page, h, id, "Registered Nurse, Night Shift");

  await page.goto(`/jobs/${jobId}`);
  await page.getByRole("button", { name: "Read Workday-style test form" }).click();
  await expect(page.getByText("Workday-style application: local test approximation (fictional employer)")).toBeVisible();
  await expect(routeCard(page).getByText("Browser adapter (local test fixture only)")).toBeVisible();
  await expect(routeCard(page)).not.toContainText(/\blive\b/i);

  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: jobId } })).json();
  for (const [key, value] of [
    ["legalName--firstName", { text: "Sam" }],
    ["q.licence_type", { label: "RN" }],
    ["q.shift", { label: "Nights" }],
  ] as const) {
    expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
  }
  await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "terms_ack", choice: "agree" } });

  await page.goto(`/applications/${app.id}`);
  await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
  await expect(page.getByText("Approved for a rehearsal only (never submits)")).toBeVisible();
  await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
  await expect(badge(page, "Rehearsal finished: nothing submitted")).toBeVisible({ timeout: 60_000 });
  let l = await ledger(request, slug);
  expect(l.uploads).toBe(1);
  expect(l.accepted).toHaveLength(0);

  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Submit approved package" }).click();
  await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
  l = await ledger(request, slug);
  expect(l.accepted).toHaveLength(1);
  const sent = l.accepted[0].fields;
  expect(sent["legalName--firstName"]).toBe("Sam");
  expect(sent["q.work_eligibility"]).toBe("Yes"); // from your US work authorization
  expect(sent["q.sponsorship"]).toBe("No");
  expect(sent["terms_ack"]).toBe("1");
  expect(sent["vd.gender"] ?? "").toBe(""); // never chosen for you

  await page.goto("/tracker");
  await expect(page.getByText("Submitted (employer receipt)", { exact: true }).first()).toBeVisible();
});

test("an account gate or several pages are checkpoints: nothing is sent", async ({ page, request }, info) => {
  const h = await candidate(page, `${info.project.name}-gate`);
  try {
    for (const mode of ["wd_account_required", "wd_multi_step"]) {
      await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode } });
      const id = req();
      const jobId = await workdayJob(page, h, id, `Nurse (${mode})`);
      await page.goto(`/jobs/${jobId}`);
      await page.getByRole("button", { name: "Read Workday-style test form" }).click();
      await expect(page.getByText("Workday-style application: local test approximation (fictional employer)")).toBeVisible();
      await expect(routeCard(page).getByText("Needs you: a step NoEfforts cannot do").first()).toBeVisible();
      const route = await (await page.request.get(`/api/jobs/${jobId}/route`)).json();
      expect(route.route).toBe("checkpoint");
      expect((await ledger(request, `workday-examplehealth-${id}`)).uploads).toBe(0);
    }
  } finally {
    // The shared receiver goes back to normal even if a check above failed.
    await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode: "normal" } });
  }
});

test("a Languages or Skills section the page does not require is left empty, shown so, and never sent", async ({ page, request }, info) => {
  // D165 (FIXTURE ASSUMPTION FA10): sections NoEfforts does not fill, on the single page. D166: its
  // Websites section is filled from your profile's links, and this candidate has none.
  const id = req();
  const slug = `workday-examplehealth-${id}`;
  const h = await candidate(page, `${info.project.name}-other`);
  try {
    await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode: "wd_other_sections" } });
    const jobId = await workdayJob(page, h, id, "Registered Nurse (other sections)");
    await page.goto(`/jobs/${jobId}`);
    await page.getByRole("button", { name: "Read Workday-style test form" }).click();
    await expect(page.getByText("Workday-style application: local test approximation (fictional employer)")).toBeVisible();
    await expect(routeCard(page).getByText("Browser adapter (local test fixture only)")).toBeVisible();

    const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: jobId } })).json();
    for (const [key, value] of [
      ["legalName--firstName", { text: "Sam" }],
      ["q.licence_type", { label: "RN" }],
      ["q.shift", { label: "Nights" }],
    ] as const) {
      expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
    }
    await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "terms_ack", choice: "agree" } });

    await page.goto(`/applications/${app.id}`);
    for (const name of ["Languages", "Skills"]) {
      await expect(page.getByText(`Left empty: NoEfforts does not fill this form's ${name} section`)).toBeVisible();
    }
    await expect(page.getByText("Nothing is sent here: your approved profile has no links.")).toBeVisible();
    await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
    await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
    await expect(badge(page, "Rehearsal finished: nothing submitted")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await page.getByRole("button", { name: "Submit approved package" }).click();
    await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
    const l = await ledger(request, slug);
    expect(l.accepted).toHaveLength(1);
    expect(Object.keys(l.accepted[0].fields).filter((k) => /^(lang|web|skill)\[/.test(k))).toEqual([]);
  } finally {
    // The shared receiver goes back to normal even if a check above failed.
    await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode: "normal" } });
  }
});

test("your profile's links fill a Websites section, shown on the review page and sent as approved", async ({ page, request }, info) => {
  // D166 (FIXTURE ASSUMPTION FA11): on the single page, beside FA10's sections left empty.
  const id = req();
  const slug = `workday-examplehealth-${id}`;
  const h = await candidate(page, `${info.project.name}-websites`, ["github.com/sam-synthetic", "https://sam.example/portfolio"]);
  try {
    await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode: "wd_other_sections" } });
    const jobId = await workdayJob(page, h, id, "Registered Nurse (websites)");
    await page.goto(`/jobs/${jobId}`);
    await page.getByRole("button", { name: "Read Workday-style test form" }).click();
    await expect(page.getByText("Workday-style application: local test approximation (fictional employer)")).toBeVisible();

    const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: jobId } })).json();
    for (const [key, value] of [
      ["legalName--firstName", { text: "Sam" }],
      ["q.licence_type", { label: "RN" }],
      ["q.shift", { label: "Nights" }],
    ] as const) {
      expect((await page.request.put(`/api/applications/${app.id}/answers`, { headers: h, data: { key, value } })).ok()).toBeTruthy();
    }
    await page.request.put(`/api/applications/${app.id}/consents`, { headers: h, data: { key: "terms_ack", choice: "agree" } });

    await page.goto(`/applications/${app.id}`);
    const card = page.locator("section", { has: page.getByRole("heading", { name: "Education, work history and websites" }) });
    const websites = card.getByRole("group", { name: "Websites" });
    // the address each entry is given: written with https:// where the link names no scheme
    await expect(websites.getByText("https://github.com/sam-synthetic", { exact: true })).toBeVisible();
    await expect(websites.getByText("https://sam.example/portfolio", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
    await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
    await expect(badge(page, "Rehearsal finished: nothing submitted")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await page.getByRole("button", { name: "Submit approved package" }).click();
    await expect(badge(page, "Employer receipt received")).toBeVisible({ timeout: 60_000 });
    const l = await ledger(request, slug);
    expect(l.accepted).toHaveLength(1);
    const sent = Object.fromEntries(Object.entries(l.accepted[0].fields).filter(([k]) => /^(lang|web|skill)\[/.test(k)));
    expect(sent).toEqual({ "web[0].url": "https://github.com/sam-synthetic", "web[1].url": "https://sam.example/portfolio" });
  } finally {
    // The shared receiver goes back to normal even if a check above failed.
    await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { mode: "normal" } });
  }
});

test("a real Workday posting is never read and stays a manual handoff", async ({ page, request }, info) => {
  const h = await candidate(page, `${info.project.name}-real`);
  const job = await (
    await page.request.post("/api/jobs", {
      headers: h,
      data: { url: "https://acme.wd5.myworkdayjobs.com/External/job/Springfield/Nurse_R-100001", title: "Nurse (real host, never contacted)", employer: "Acme" },
    })
  ).json();
  await page.goto(`/jobs/${job.job.id}`);
  await expect(routeCard(page).getByText("Manual: apply on the employer's site").first()).toBeVisible();
  const r = await page.request.post(`/api/jobs/${job.job.id}/form/workday`, { headers: h });
  expect(r.status()).toBe(409);
  const l = await (await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } })).json();
  expect((l.requests as { path: string }[]).some((x) => x.path.includes("myworkday"))).toBe(false);
});
