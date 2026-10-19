import { expect, test } from "@playwright/test";

// One persistent end-to-end slice: register, profile facts, preferences, add + import jobs,
// upload a document, track an application and record its outcome. Synthetic data only.
test("phase A slice", async ({ page }, info) => {
  const email = `synthetic.${info.project.name}.${Date.now()}@example.com`;

  await page.goto("/jobs");
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("link", { name: "Create an account" }).click();
  // The login page has fields with the same labels: wait until the register page is really
  // showing before filling (CI run #2 failed on exactly this race; see e2e/navigation-race).
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("synthetic-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();

  // Facts
  await page.getByLabel("Full name").fill("Synthetic Candidate");
  await page.getByLabel("City").fill("Springfield");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByText(/Version 1 · user entered/)).toBeVisible();

  await page.getByLabel("Country code").fill("ca");
  await page.getByLabel("Authorized", { exact: true }).selectOption("yes");
  await page.getByLabel("Sponsorship now", { exact: true }).selectOption("no");
  await page.getByRole("button", { name: "Add country" }).click();
  await expect(page.getByText(/authorized Yes, sponsorship now No, later Not answered/)).toBeVisible();

  // Preferences
  await page.getByRole("link", { name: "Preferences" }).click();
  await page.getByLabel("Job titles").fill("Electrician");
  await page.getByLabel("Employers to exclude").fill("Blocked Corp");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Preferences saved.")).toBeVisible();

  // Jobs: manual + duplicate
  await page.getByRole("link", { name: "Jobs" }).click();
  await page.getByLabel("Job link").fill("https://boards.greenhouse.io/synthetic/jobs/4242?utm_source=e2e");
  await page.getByLabel("Title").fill("Journeyman Electrician");
  await page.getByLabel("Employer").fill("Synthetic Power");
  await page.getByRole("button", { name: "Add job" }).click();
  await expect(page.getByText("Job added.")).toBeVisible();
  await page.getByLabel("Job link").fill("https://boards.greenhouse.io/synthetic/jobs/4242");
  await page.getByRole("button", { name: "Add job" }).click();
  await expect(page.getByText(/already have this job/)).toBeVisible();

  // Import
  const csv = "title,employer,location\nApprentice Electrician,Blocked Corp,Remote\nSite Lead,Grid Co,Springfield\n,,\nNo Employer,,\n";
  await page.getByLabel("Spreadsheet file").setInputFiles({ name: "jobs.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/2 added, 0 already known, 1 with problems/)).toBeVisible();
  await expect(page.getByText("Your jobs (3)")).toBeVisible();
  await expect(page.getByText(/Blocked Corp' is on your excluded list/)).toBeVisible();

  // Job detail + explanations + track
  await page.getByText("Journeyman Electrician").click();
  await expect(page.getByText("Title matches 'Electrician'")).toBeVisible();
  await page.getByRole("button", { name: "Track application" }).click();
  await expect(page.getByRole("heading", { name: "Application tracker" })).toBeVisible();
  await page.getByRole("button", { name: "I applied myself" }).click();
  await expect(page.getByText("Submitted (not confirmed)", { exact: true }).first()).toBeVisible();
  // Uncertain outcome: reconciliation requires saying what was checked; no one-click resubmit.
  await page.getByLabel("What did you check?").fill("Confirmation email received, ref SYN-123");
  await page.getByRole("button", { name: "It was received" }).click();
  await expect(page.getByText("Submitted (confirmed)", { exact: true }).first()).toBeVisible();
  await page.getByLabel("Outcome").selectOption("interviewing");
  await expect(page.getByText("outcome: none → interviewing")).toBeVisible();

  // Documents
  await page.getByRole("link", { name: "Documents" }).click();
  await page.getByLabel("File").setInputFiles({ name: "resume.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n% synthetic\n") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("resume.pdf · 0 KB · v1")).toBeVisible();

  // Persistence: reload and confirm data survives.
  await page.reload();
  await expect(page.getByText("resume.pdf · 0 KB · v1")).toBeVisible();
  await page.getByRole("link", { name: "Tracker" }).click();
  await expect(page.getByText("Submitted (confirmed)")).toBeVisible();

  await page.screenshot({ path: `test-results/phase-a-${info.project.name}.png`, fullPage: true });
});
