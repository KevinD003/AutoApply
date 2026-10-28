import { expect, Page, test } from "@playwright/test";

// S3 (D59) in the UI: a role that looks like one you already applied to is shown on the job page
// and the review page, and approval waits until you say it is a different role. Two fictional
// postings of one role (two URLs), the local basic test form; synthetic data only.
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e resume\n");

async function setup(page: Page, run: string) {
  const reg = await page.request.post("/api/auth/register", { data: { email: `s3.${run}@example.com`, password: "synthetic-password-1" } });
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
  async function application(n: number) {
    const body = { title: "Data Analyst", employer: "Contoso Example (fictional)", url: `https://jobs.example.test/contoso/${run}-${n}` };
    const job = (await (await post("/jobs", body)).json()).job;
    expect((await post(`/jobs/${job.id}/form`, { fixture: "basic" })).status()).toBe(201);
    const app = await (await post("/applications", { job_id: job.id })).json();
    await put(`/applications/${app.id}/answers`, { key: "hear_about", value: { label: "Referral" } });
    await put(`/applications/${app.id}/consents`, { key: "privacy_ack", choice: "agree" });
    await page.request.get(`/api/applications/${app.id}/package`);
    return { jobId: job.id as string, appId: app.id as string };
  }
  return { first: await application(1), second: await application(2) };
}

test("a possible duplicate waits for your statement", async ({ page }, info) => {
  const { first, second } = await setup(page, `${info.project.name}-${Date.now()}`);
  await page.goto(`/applications/${second.appId}`);
  const about = page.getByRole("group", { name: "About this job" });
  await expect(about.getByText(/It looks like a role you already applied to/)).toBeVisible();
  await expect(about.getByText("job_possible_duplicate")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Approve package v\d+$/ })).toBeDisabled();

  await about.getByRole("link", { name: "Open the job page" }).click();
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Before you apply" }) });
  await expect(card.getByText("Looks like a role you already applied to", { exact: true })).toBeVisible();
  await expect(card.getByRole("link", { name: /Data Analyst · Contoso Example \(fictional\)/ })).toHaveAttribute("href", `/jobs/${first.jobId}`);
  await expect(card.getByText("awaiting_approval")).toBeVisible();
  await card.getByRole("button", { name: "This is a different role" }).click();
  await expect(page.getByRole("heading", { name: "Before you apply" })).toHaveCount(0);

  await page.goto(`/applications/${second.appId}`);
  await expect(page.getByRole("group", { name: "About this job" })).toHaveCount(0);
  await page.getByRole("button", { name: /^Approve package v\d+$/ }).click();
  await expect(page.getByText("Approved. This approval covers exactly this package version.")).toBeVisible();
});
