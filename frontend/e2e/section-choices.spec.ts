import { expect, test } from "@playwright/test";

// D164: a part of your education no option of the employer's form matches is yours to choose, from
// the form's own options, for this application only; once your record changes, the choice no
// longer applies. A fictional manual form with an education section; synthetic data.
test("you choose the employer's option for a school none matches, and it is sent as chosen", async ({ page }, info) => {
  const email = `d164.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object = {}) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (await put("/profile", { full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com" })).ok(),
  ).toBeTruthy();
  const record = {
    institution: "Unlisted Academy",
    degree: "Bachelor's Degree",
    field_of_study: "Computer Science",
    start_date: "2014-09-01",
    end_date: "2018-05-01",
  };
  const edu = await (await post("/profile/education", record)).json();
  expect((await post(`/profile/education/${edu.id}/approve`)).ok()).toBeTruthy();

  const job = await (await post("/jobs", { title: "Clinic Assistant", employer: "Example Health (fictional)" })).json();
  const form = {
    title: "Synthetic form with an education section",
    fields: [{ key: "nickname", label: "Nickname", type: "text", required: false }],
    sections: [
      {
        kind: "education",
        root: "#education-section",
        schools: [
          { id: "s1", text: "State University" },
          { id: "s2", text: "Metro College" },
        ],
        degrees: [{ id: "d1", text: "Bachelor's Degree" }],
        disciplines: [{ id: "x1", text: "Computer Science" }],
      },
    ],
  };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = await (await post("/applications", { job_id: job.job.id })).json();

  await page.goto(`/applications/${app.id}`);
  const approve = page.getByRole("button", { name: /^Approve package v\d+$/ });
  await expect(approve).toBeDisabled();
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Choose from the employer's options" }) });
  await expect(card.getByText("Your record says: Unlisted Academy")).toBeVisible();
  await card.getByLabel("School").selectOption({ label: "Metro College" });
  await card.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Chosen for this application.")).toBeVisible();

  // The package now sends the option you chose, and nothing is left for you to settle.
  const sections = page.locator("section", { has: page.getByRole("heading", { name: "Education and work history" }) });
  await expect(sections.getByRole("group", { name: "Education" }).getByText("Metro College", { exact: true })).toBeVisible();
  await expect(approve).toBeEnabled();
  const pkg = (await (await page.request.get(`/api/applications/${app.id}/package`)).json()).package;
  expect(pkg.content.sections[0].rows[0].fields.school_name_id.value).toEqual({ id: "s2" });

  // Your record changes: the choice no longer applies, and you are asked again.
  expect((await put(`/profile/education/${edu.id}`, { ...record, end_date: "2018-06-01" })).ok()).toBeTruthy();
  await page.reload();
  await expect(card.getByText(/The option you chose no longer applies/)).toBeVisible();
  await expect(approve).toBeDisabled();
});
