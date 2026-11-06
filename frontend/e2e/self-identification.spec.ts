import { expect, test } from "@playwright/test";

// D122 and D131 on the review page: a question answered from your saved self-identification
// says where its answer came from ("Your self-identification") instead of breaking the page, and
// a criminal-history question is never answered from it, even with "No" among your labels. A
// fictional manual form; synthetic data only (the standard public EEOC option labels).
test("a self-identified answer shows its source; a criminal-history question stays yours", async ({ page }, info) => {
  const email = `d131.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (await put("/profile", { full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com" })).ok(),
  ).toBeTruthy();
  expect((await put("/profile/self-identification", { enabled: true, labels: ["Male", "No"] })).ok()).toBeTruthy();
  const job = await (await post("/jobs", { title: "Clinic Assistant", employer: "Example Health (fictional)" })).json();
  const form = {
    title: "Synthetic form",
    fields: [
      {
        key: "gender",
        label: "Gender",
        type: "select",
        required: false,
        options: [
          { value: "1", label: "Male" },
          { value: "2", label: "Female" },
          { value: "3", label: "Decline To Self Identify" },
        ],
      },
      {
        key: "felony",
        label: "Have you ever been convicted of a felony?",
        type: "select",
        required: true,
        options: [
          { value: "y", label: "Yes" },
          { value: "n", label: "No" },
        ],
      },
    ],
  };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await page.goto(`/applications/${app.id}`);

  const sensitive = page.locator("section").filter({ has: page.getByRole("heading", { name: "Sensitive disclosures and acknowledgments" }) });
  const gender = sensitive.getByRole("listitem").filter({ hasText: "Gender" });
  await expect(gender.getByText("Your self-identification", { exact: true })).toBeVisible();
  const felony = sensitive.getByRole("listitem").filter({ hasText: "Have you ever been convicted of a felony?" });
  await expect(felony.getByText("Unresolved", { exact: true })).toBeVisible();
  await expect(felony.getByText("Your self-identification", { exact: true })).toHaveCount(0);
  await expect(felony.getByText(/NoEfforts never infers this/)).toBeVisible();
});

// D131 follow-up: a standard label that contains commas is one label, kept whole. Split on commas,
// "No, I do not have a disability and have not had one in the past" became a bare "No".
test("a self-identification label with commas is saved and shown as one label", async ({ page }, info) => {
  const email = `d131b.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const disability = "No, I do not have a disability and have not had one in the past";

  await page.goto("/profile");
  const card = page.locator("section", { has: page.getByRole("heading", { name: /^Self-identification \(EEOC/ }) });
  const box = card.getByLabel("Your self-identification labels (one per line, exactly as forms word them)");
  await box.fill(`Male\n${disability}\n`);
  await card.getByRole("button", { name: "Save self-identification" }).click();
  await expect(card.getByText("Saved.", { exact: true })).toBeVisible();

  const saved = await (await page.request.get("/api/profile/self-identification")).json();
  expect(saved.labels).toEqual(["Male", disability]);
  await page.reload();
  await expect(card.getByLabel("Your self-identification labels (one per line, exactly as forms word them)")).toHaveValue(
    `Male\n${disability}`,
  );
});
