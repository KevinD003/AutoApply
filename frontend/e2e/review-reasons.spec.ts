import { expect, test } from "@playwright/test";

// C10 (D58) on the review page: with two LinkedIn profile links in the profile, NoEfforts does not
// pick the first; the row says why and takes the user's answer. A website stored without a
// scheme does not fit a web-address field (S4), and the row says that too. A fictional manual
// form; synthetic data only.
test("the review page says why a link is not filled", async ({ page }, info) => {
  const email = `c10.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (
      await put("/profile", {
        full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com",
        links: ["https://www.linkedin.com/in/sam-synthetic", "https://www.linkedin.com/in/sam-synthetic-two", "sam.example.com"],
      })
    ).ok(),
  ).toBeTruthy();
  const job = await (await post("/jobs", { title: "Clinic Assistant", employer: "Example Health (fictional)" })).json();
  const form = {
    title: "Synthetic form",
    fields: [
      { key: "li", label: "LinkedIn profile", type: "url", required: true },
      { key: "web", label: "Website", type: "url", required: true },
    ],
  };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await page.goto(`/applications/${app.id}`);

  const li = page.getByRole("listitem").filter({ has: page.getByLabel("LinkedIn profile", { exact: true }) });
  await expect(li.getByText(/Your profile has 2 LinkedIn profile links, so NoEfforts does not choose one/)).toBeVisible();
  const web = page.getByRole("listitem").filter({ has: page.getByLabel("Website", { exact: true }) });
  await expect(web.getByText(/does not fit this field \(not a web address\)/)).toBeVisible();

  await li.getByLabel("LinkedIn profile", { exact: true }).fill("https://www.linkedin.com/in/sam-synthetic-two");
  await li.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Answer saved.")).toBeVisible();
  await expect(page.getByText("https://www.linkedin.com/in/sam-synthetic-two")).toBeVisible();
});
