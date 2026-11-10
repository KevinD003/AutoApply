import { expect, test } from "@playwright/test";

// D140: the education a package sends (a D120 structured section) is shown on the review page as
// frozen in the package, and after you edit the record behind it, the version history names the
// change and shows it by record and field. A fictional manual form with a section; synthetic data.
test("the education a package sends is shown, and an edit to it is named and shown in the diff", async ({ page }, info) => {
  const email = `d140.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object = {}) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (await put("/profile", { full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com" })).ok(),
  ).toBeTruthy();
  const record = {
    institution: "State University",
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
        schools: [{ id: "s1", text: "State University" }],
        degrees: [
          { id: "d1", text: "Bachelor's Degree" },
          { id: "d2", text: "Master's Degree" },
        ],
        disciplines: [{ id: "x1", text: "Computer Science" }],
      },
    ],
  };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  const pkg = (await (await page.request.get(`/api/applications/${app.id}/package`)).json()).package;
  const approved = await post(`/applications/${app.id}/package/approve`, { version: pkg.version, content_hash: pkg.content_hash });
  expect(approved.status(), await approved.text()).toBe(200);

  await page.goto(`/applications/${app.id}`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Education and work history" }) });
  const education = card.getByRole("group", { name: "Education" });
  await expect(education.getByText("State University", { exact: true })).toBeVisible();
  await expect(education.getByText("Bachelor's Degree", { exact: true })).toBeVisible();
  await expect(education.getByText("09/2014", { exact: true })).toBeVisible();

  // The record is edited (and stays approved): the approval is retired and a new version is built.
  expect((await put(`/profile/education/${edu.id}`, { ...record, degree: "Master's Degree" })).ok()).toBeTruthy();
  await page.reload();
  await expect(education.getByText("Master's Degree", { exact: true })).toBeVisible();
  const history = page.locator("section", { has: page.getByRole("heading", { name: "Version history" }) });
  await expect(history.getByText(/education changed/)).toBeVisible();
  await history.getByRole("button", { name: "What changed in v2" }).click();
  const changes = history.getByRole("list", { name: "Changes from v1 to v2" });
  await expect(changes.getByText("State University (changed): Degree Bachelor's Degree → Master's Degree")).toBeVisible();
  await expect(changes.getByText("Nothing you would see changed (only record versions).")).toHaveCount(0);
});
