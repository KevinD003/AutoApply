import { createHash } from "node:crypto";

import { APIRequestContext, expect, Page, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// The whole product journey on synthetic data, through the real UI, the API, the Celery worker
// and the independent receiver, whose ledger is the oracle for what was sent:
// discovery (the receiver's stand-in of Freehire's documented API) → normalization and dedupe →
// preferences → facts proposed from a resume and approved → tailored resume reviewed → package
// approval → disclosure-only rehearsal → a separate approval to submit → submission → receipt →
// tracker, timeline and outcome. The tailored text comes from the labelled local fixture
// provider (backend preparation/fixture_provider.py), honoured only in env "test" for journey.*
// accounts (playwright.config.ts). Nothing leaves this machine.
test.describe.configure({ mode: "serial" });

const SLUG = "gh2-northwind-5020001"; // the receiver's Greenhouse-style form the listing links to
const RESUME = [
  "Sam Journey",
  "Experience",
  "Support Lead at Example Clinic (fictional), Jan 2020 – Present",
  "• Answered customer emails and chat for 3 clinics",
  "Education",
  "Associate of Arts, Communication — Example Community College",
].join("\n");

async function admin(request: APIRequestContext, path: string, body?: object) {
  const r = body
    ? await request.post(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: body })
    : await request.get(`${RECEIVER}/_admin/${path}`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

type Acceptance = { slug: string; fields: Record<string, string> };
type Disclosure = { slug: string; kind: string; detail: string };
async function ledger(request: APIRequestContext) {
  const l = await admin(request, "ledger");
  return {
    accepted: (l.acceptances as Acceptance[]).filter((a) => a.slug === SLUG),
    uploads: (l.disclosures as Disclosure[]).filter((d) => d.slug === SLUG && d.kind === "upload").map((d) => JSON.parse(d.detail)),
  };
}

const card = (page: Page, title: string) => page.locator("section", { has: page.getByRole("heading", { name: title, exact: true }) });

test("one synthetic journey: discovery to receipt, tracker and outcome", async ({ page, request }, info) => {
  test.setTimeout(420_000);
  await admin(request, "config", { mode: "normal", delay_s: 0, form_delay_s: 0, idempotent: false, fh_mode: "normal" });
  const before = await ledger(request);
  const email = `journey.${info.project.name}.${Date.now()}@example.com`;

  await test.step("register; facts and preferences are kept apart", async () => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("synthetic-password-1");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/profile/);
    const contact = card(page, "Contact and residence");
    await contact.getByLabel("Full name").fill("Sam Journey");
    await contact.getByLabel("First (given) name").fill("Sam");
    await contact.getByLabel("Last (family) name").fill("Journey");
    await contact.getByLabel("Contact email").fill("sam.journey@example.com");
    await contact.getByLabel("Phone").fill("+1 555 0100");
    await contact.getByLabel("Country you currently live in").fill("US");
    await contact.getByLabel("City").fill("Springfield");
    await contact.getByRole("button", { name: "Save" }).click();
    await expect(contact.getByText("Saved.")).toBeVisible();
    const auth = card(page, "Work authorization and sponsorship");
    await auth.getByLabel("Country code").fill("US");
    await auth.getByLabel("Authorized", { exact: true }).selectOption("yes");
    await auth.getByLabel("Sponsorship now").selectOption("no");
    await auth.getByLabel("Sponsorship later").selectOption("no");
    await auth.getByRole("button", { name: "Add country" }).click();
    await expect(auth.getByText(/Summary: authorized Yes, sponsorship now No, later No/)).toBeVisible();

    await page.goto("/preferences");
    await page.getByLabel("Job titles").fill("Support Specialist");
    await page.getByLabel("Target locations").fill("Riverton");
    await page.getByRole("checkbox", { name: "hybrid" }).check();
    await page.getByRole("button", { name: "Save preferences" }).click();
    await expect(page.getByText("Preferences saved.")).toBeVisible();
  });

  await test.step("a resume proposes facts; nothing is used until approved", async () => {
    await page.goto("/documents");
    const upload = card(page, "Upload a document");
    await upload.getByLabel("File").setInputFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from(RESUME) });
    await upload.getByLabel("Label (optional)").fill("General resume");
    await upload.getByRole("button", { name: "Upload" }).click();
    await expect(upload.getByText("Uploaded.")).toBeVisible();
    await page.getByRole("button", { name: "Propose profile facts" }).click();
    await expect(page.getByText(/Proposed from “General resume”: 1 work entry, 1 education entry/)).toBeVisible();
    await page.goto("/profile");
    const work = card(page, "Work history");
    await expect(work.getByText("Proposed from your resume")).toBeVisible();
    await work.getByRole("button", { name: "Approve" }).click();
    await expect(work.getByText("Proposed from your resume")).toHaveCount(0);
    const edu = card(page, "Education");
    await edu.getByRole("button", { name: "Approve" }).click();
    await expect(edu.getByText("Proposed from your resume")).toHaveCount(0);
  });

  let jobId = "";
  await test.step("discovery: normalized, deduplicated, never re-added", async () => {
    await page.goto("/discover");
    await page.getByRole("button", { name: "Find jobs" }).click();
    await expect(page.getByText(/listings read/)).toBeVisible();
    // The same posting listed twice by the source (another slug, another tracking parameter)
    // becomes one job: the copy links to it.
    const support = page.locator("li", { hasText: "Support Specialist" });
    await expect(support).toHaveCount(2);
    await expect(support.getByRole("link", { name: "added to your jobs" })).toHaveCount(1);
    await expect(support.getByRole("link", { name: /already in your jobs/ })).toHaveCount(1);
    await expect(support.first().getByText(/sponsorship: source says yes \(provider enrichment\)/)).toBeVisible();
    const href = await support.getByRole("link", { name: "added to your jobs" }).getAttribute("href");
    jobId = href!.split("/jobs/")[1];
    // A second search adds nothing.
    await page.getByRole("button", { name: "Find jobs" }).click();
    await expect(page.getByText(/listings read .*: 0 new/)).toBeVisible();
    await page.goto("/jobs");
    await expect(page.getByRole("link", { name: "Support Specialist" })).toHaveCount(1);
  });

  let appId = "";
  await test.step("job page: preferences explained apart from eligibility; the form is captured", async () => {
    await page.goto(`/jobs/${jobId}`);
    const why = card(page, "Why this job matches (or doesn't)");
    await expect(why.getByText("Title matches 'Support Specialist'")).toBeVisible();
    await expect(why.getByText("Location is one of your targets")).toBeVisible();
    await expect(page.getByText("A source listing is not verified, and says nothing about eligibility or sponsorship.")).toBeVisible();
    await page.getByRole("button", { name: "Read Greenhouse-style test form" }).click();
    await expect(page.getByText(/Greenhouse-style form mapped by id and label/)).toBeVisible();
    await expect(card(page, "How NoEfforts could apply").getByText(/local test fixture only/)).toBeVisible();
    await page.getByRole("button", { name: "Prepare application" }).click();
    await expect(page).toHaveURL(/\/applications\//);
    appId = page.url().split("/applications/")[1];
  });

  await test.step("what is unknown is asked, and nothing can be approved until it is", async () => {
    const pending = card(page, "Needs your answer (3)");
    await expect(pending).toBeVisible();
    // Not copied from the given name; the role's country is unknown, so authorization there is
    // asked, never inferred from the US fact; a question about this employer is never guessed.
    await expect(pending.getByText("Preferred First Name")).toBeVisible();
    await expect(pending.getByText("Are you legally authorized to work in the country where this role is based?")).toBeVisible();
    await expect(pending.getByText("Have you worked for Northwind Example before?")).toBeVisible();
    await expect(page.getByRole("button", { name: /Approve package v\d+/ })).toBeDisabled();
    const answer = async (label: string, fill: (c: ReturnType<Page["getByLabel"]>) => Promise<unknown>) => {
      const item = page.getByRole("listitem").filter({ has: page.getByLabel(label, { exact: true }) });
      await fill(item.getByLabel(label, { exact: true }));
      await item.getByRole("button", { name: "Save answer" }).click();
      await expect(page.getByLabel(label, { exact: true })).toHaveCount(0);
    };
    await answer("Preferred First Name", (c) => c.fill("Sammy"));
    await answer("Are you legally authorized to work in the country where this role is based?", (c) => c.selectOption({ label: "Yes" }));
    await answer("Have you worked for Northwind Example before?", (c) => c.selectOption({ label: "No" }));
    await expect(card(page, "Needs your answer (0)")).toBeVisible();
  });

  let tailoredId = "";
  await test.step("a tailored resume is read, accepted and chosen", async () => {
    const tailored = card(page, "Tailored resume and cover letter");
    await tailored.getByRole("button", { name: "Tailor my resume for this job" }).click();
    await expect(tailored.getByText("Waiting for you to read it")).toBeVisible();
    await expect(tailored.getByText(/Support Lead at Example Clinic \(fictional\)/).first()).toBeVisible();
    await tailored.getByRole("button", { name: "Accept" }).click();
    await expect(tailored.getByText("Accepted: choose it above")).toBeVisible();
    // Offered at once in the resume choice, without reloading the page.
    const choice = card(page, "Documents").getByLabel("Resume to send");
    const option = choice.locator("option", { hasText: "Resume for Support Specialist" });
    await expect(option).toHaveCount(1);
    tailoredId = (await option.getAttribute("value"))!;
    await choice.selectOption(tailoredId);
    await expect(card(page, "Documents").getByText(/resume: .*Resume for Support Specialist/)).toBeVisible();
  });

  await test.step("a rehearsal fills and checks, and never submits", async () => {
    await page.getByRole("button", { name: /Approve a rehearsal of v\d+/ }).click();
    await expect(page.getByText("Approved for a rehearsal only (never submits)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit approved package" })).toHaveCount(0);
    await page.getByRole("button", { name: "Start rehearsal (nothing is submitted)" }).click();
    await expect(page.getByText("Rehearsal finished: nothing submitted", { exact: true }).first()).toBeVisible({ timeout: 90_000 });
    const l = await ledger(request);
    expect(l.accepted.length).toBe(before.accepted.length); // nothing accepted
    expect(l.uploads.length).toBe(before.uploads.length + 1); // the tailored resume was uploaded once
  });

  await test.step("a separate approval to submit; a fact changed after it invalidates it", async () => {
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await expect(page.getByText("Approved", { exact: true })).toBeVisible();
    const approvedVersion = Number((await page.getByText(/^Package v\d+/).first().textContent())!.match(/v(\d+)/)![1]);
    await page.goto("/profile");
    const contact = card(page, "Contact and residence");
    await contact.getByLabel("Phone").fill("+1 555 0199");
    await contact.getByRole("button", { name: "Save" }).click();
    await expect(contact.getByText("Saved.")).toBeVisible();
    await page.goto(`/applications/${appId}`);
    await expect(page.getByText("Approval invalidated")).toBeVisible();
    await expect(page.getByText(/answers changed: phone/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit approved package" })).toBeDisabled();
    await page.getByRole("button", { name: `What changed since you approved v${approvedVersion}` }).click();
    await expect(page.getByText(/\+1 555 0100 → \+1 555 0199/)).toBeVisible();
    await page.getByRole("button", { name: /Approve package v\d+/ }).click();
    await expect(page.getByText("Approved", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Submit approved package" }).click();
    await expect(page.getByText("Employer receipt received", { exact: true }).first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("Local test fixture: counts for nothing on a real employer's form").first()).toBeVisible();
  });

  await test.step("what arrived is what was approved, exactly once", async () => {
    const l = await ledger(request);
    expect(l.accepted.length).toBe(before.accepted.length + 1);
    const sent = l.accepted[l.accepted.length - 1].fields;
    expect(sent.phone).toBe("+1 555 0199"); // the changed fact, approved again
    expect(sent.preferred_name).toBe("Sammy");
    const file = await page.request.get(`/api/documents/${tailoredId}/download`);
    const sha = createHash("sha256").update(await file.body()).digest("hex");
    const last = l.uploads[l.uploads.length - 1];
    expect(last.sha256).toBe(sha); // the tailored resume as accepted, byte for byte
    const attempts = await (await page.request.get(`/api/applications/${appId}/attempts`)).json();
    expect(attempts.map((a: { state: string }) => a.state)).toEqual(["confirmed", "rehearsed"]);
  });

  await test.step("no blind resubmission: the job, a duplicate listing or the API", async () => {
    await expect(page.getByRole("button", { name: "Submit approved package" })).toHaveCount(0);
    await page.goto(`/jobs/${jobId}`);
    await page.getByRole("button", { name: "Prepare application" }).click();
    await expect(page).toHaveURL(new RegExp(`/applications/${appId}$`)); // the same application
    const csrf = (await (await page.request.get("/api/auth/me")).json()).csrf_token as string;
    const again = await page.request.post(`/api/applications/${appId}/transition`, { headers: { "X-CSRF-Token": csrf }, data: { to: "queued" } });
    expect([400, 409]).toContain(again.status());
    expect((await ledger(request)).accepted.length).toBe(before.accepted.length + 1);
  });

  await test.step("tracker: receipt, timeline and an outcome with its source", async () => {
    await page.goto("/tracker");
    await page.getByText("Support Specialist").first().click();
    const open = card(page, "Support Specialist — Northwind Example (fictional)");
    await expect(open.getByText("Submitted (employer receipt)")).toBeVisible();
    await expect(open.getByRole("link", { name: /Open the application/ })).toBeVisible();
    await open.getByLabel("Outcome").selectOption({ label: "Interviewing" });
    await open.getByLabel("Note (optional, private)").fill("Phone screen booked (synthetic)");
    await open.getByRole("button", { name: "Record outcome" }).click();
    const lines = open.getByTestId("event-line");
    await expect(lines.filter({ hasText: "Outcome: No outcome yet → Interviewing" })).toHaveCount(1);
    await expect(lines.filter({ hasText: "employer receipt" })).toHaveCount(1);
    await expect(page.getByText("Confirmed by employer receipt: 1", { exact: true })).toBeVisible();
  });

  await test.step("fixture evidence never makes a real destination ready", async () => {
    await page.goto("/jobs");
    await page.getByLabel("Job link").fill("https://job-boards.greenhouse.io/northwind/jobs/5020001");
    await page.getByLabel("Title").fill("Support Specialist (real host, never contacted)");
    await page.getByLabel("Employer").fill("Northwind Example (fictional)");
    await page.getByRole("button", { name: "Add job" }).click();
    await expect(page.getByText("Job added.")).toBeVisible();
    await page.getByRole("link", { name: "Support Specialist (real host, never contacted)" }).click();
    const route = card(page, "How NoEfforts could apply");
    await expect(route.getByText(/Reason code: real_destination_disabled/)).toBeVisible();
    // No test-only form control is offered there: nothing could make it a supported destination.
    await expect(page.getByText(/This posting is on a real employer's site/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Read Greenhouse-style test form" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Attach test form" })).toHaveCount(0);
  });
});
