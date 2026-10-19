import { expect, test } from "@playwright/test";

// Phase B: profile → questions → deterministic resolution → missing-answer checkpoint →
// user correction → package review → approval → invalidation after a fact change.
// Uses the local "basic" fixture form (fictional employer) and synthetic data only.
test("phase B preparation and approval", async ({ page }, info) => {
  const email = `synthetic.b.${info.project.name}.${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("synthetic-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();

  await page.getByLabel("Full name").fill("Sam Synthetic");
  await page.getByLabel("First (given) name").fill("Sam");
  await page.getByLabel("Last (family) name").fill("Synthetic");
  await page.getByLabel("Contact email").fill("sam.synthetic@example.com");
  await page.getByLabel("Phone").fill("+1 555 0100");
  await page.getByLabel("Country you currently live in").fill("US");
  await page.getByLabel("City").fill("Springfield");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.getByLabel("Country code").fill("US");
  await page.getByLabel("Authorized", { exact: true }).selectOption("yes");
  await page.getByLabel("Sponsorship now", { exact: true }).selectOption("no");
  await page.getByLabel("Sponsorship later", { exact: true }).selectOption("no");
  await page.getByRole("button", { name: "Add country" }).click();
  await expect(page.getByText(/authorized Yes, sponsorship now No, later No/)).toBeVisible();

  await page.getByRole("link", { name: "Documents" }).click();
  await page.getByLabel("File").setInputFiles({ name: "resume.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n% synthetic\n") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("resume.pdf · 0 KB · v1")).toBeVisible();

  await page.getByRole("link", { name: "Jobs" }).click();
  await page.getByLabel("Title").fill("Clinic Assistant");
  await page.getByLabel("Employer").fill("Example Health Clinic");
  await page.getByRole("button", { name: "Add job" }).click();
  await page.getByText("Clinic Assistant").click();
  await page.getByLabel("Test form").selectOption("basic");
  await page.getByRole("button", { name: "Attach test form" }).click();
  await expect(page.getByText(/Form v1 · 15 questions/)).toBeVisible();
  await page.getByRole("button", { name: "Prepare application" }).click();

  // Review: deterministic answers with sources; checkpoints for the rest.
  await expect(page.getByText("Local test fixture — fictional employer")).toBeVisible();
  await expect(page.getByText("Needs your input")).toBeVisible();
  await expect(page.getByText("Profile: authorized to work in United States = yes.")).toBeVisible();
  await expect(page.getByText(/Profile \(United States\): needs sponsorship now = no, later = no/)).toBeVisible();
  await expect(page.getByText("Required: How did you hear about this job?")).toBeVisible();
  await expect(page.getByText("AI drafting is not configured on this server. Write this answer yourself.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve package/ })).toBeDisabled();

  await page.getByLabel("How did you hear about this job?").first().selectOption("Referral");
  await page.getByText("Reuse for this exact question in future applications").first().click();
  await page.getByRole("button", { name: "Save answer" }).first().click();
  await expect(page.getByText("Answer saved.")).toBeVisible();
  await page.getByRole("button", { name: "I agree" }).click();
  await expect(page.getByText("Ready for your approval")).toBeVisible();

  await page.getByRole("button", { name: /Approve package v\d+/ }).click();
  await expect(page.getByText("Approved. This approval covers exactly this package version.")).toBeVisible();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/phase-b-review-${info.project.name}.png`, fullPage: true });

  // Change a protected fact: approval must be invalidated.
  await page.getByRole("link", { name: "Profile" }).click();
  await page.getByLabel("Will need sponsorship later").selectOption("yes");
  await expect(page.getByText(/later Yes · v2/)).toBeVisible();
  await page.getByRole("link", { name: "Tracker" }).click();
  await page.getByText("Clinic Assistant").click();
  await page.getByRole("link", { name: "Open the application review" }).click();
  await expect(page.getByText("Approval invalidated")).toBeVisible();
  await expect(page.getByText(/Package changed in version \d+: answers changed: sponsorship_us$/)).toBeVisible();

  // Saved answer is listed and bound to its wording.
  await page.getByRole("link", { name: "Saved answers" }).click();
  await expect(page.getByText("How did you hear about this job?")).toBeVisible();
  await expect(page.getByText("Referral", { exact: true })).toBeVisible();

  await page.goto(page.url().replace("/answers", "/tracker"));
  await page.screenshot({ path: `test-results/phase-b-${info.project.name}.png`, fullPage: true });
});
