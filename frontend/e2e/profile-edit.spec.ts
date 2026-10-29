import { expect, test } from "@playwright/test";

// Priority C (D78): work history, education and licences are edited in place, as a new
// version of the record. Synthetic account only.

test("a work history record and a licence are edited in place", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `profile-edit.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  expect((await page.request.post("/api/profile/employment", { headers: h, data: { employer: "Fictional Clinic", title: "Receptionist" } })).status()).toBe(201);
  expect((await page.request.post("/api/profile/credentials", { headers: h, data: { name: "CPR", expires_on: "2030-01-01" } })).status()).toBe(201);

  await page.goto("/profile");
  const work = page.locator("section", { has: page.getByRole("heading", { name: "Work history" }) });
  await expect(work.getByText("Receptionist — Fictional Clinic")).toBeVisible();
  await work.getByRole("button", { name: "Edit" }).click();
  await expect(work.getByLabel("Job title")).toHaveValue("Receptionist");
  await work.getByLabel("Job title").fill("Front Desk Lead");
  await work.getByRole("button", { name: "Save changes" }).click();
  await expect(work.getByText("Front Desk Lead — Fictional Clinic")).toBeVisible();
  await expect(work.getByText("Receptionist — Fictional Clinic")).toHaveCount(0);
  await expect(work.getByRole("button", { name: "Add position" })).toBeVisible();

  const lic = page.locator("section", { has: page.getByRole("heading", { name: "Licences and certifications" }) });
  await lic.getByRole("button", { name: "Edit" }).click();
  await lic.getByLabel("Expires on").fill("2031-06-30");
  await lic.getByRole("button", { name: "Save changes" }).click();
  await expect(lic.getByText("Valid until 2031-06-30")).toBeVisible();

  const jobs = await (await page.request.get("/api/profile/employment")).json();
  expect(jobs).toHaveLength(1);
  expect(jobs[0].title).toBe("Front Desk Lead");
  expect(jobs[0].version).toBe(2);
  const creds = await (await page.request.get("/api/profile/credentials")).json();
  expect(creds[0].version).toBe(2);
});
