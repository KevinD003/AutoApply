import { expect, test } from "@playwright/test";

// C11 (D57) on the review page: a State list naming every US state gets the profile's state; a
// City list is never picked from the profile, says why, and is answered for this application
// without a reuse offer. A fictional manual form; synthetic data only.
const STATES = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
  "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
  "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
  "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
  "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
];

test("state and city lists on the review page", async ({ page }, info) => {
  const email = `c11.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (
      await put("/profile", {
        full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic",
        contact_email: "sam.synthetic@example.com", residence_country: "US", residence_region: "TX",
        residence_city: "Springfield", links: [],
      })
    ).ok(),
  ).toBeTruthy();
  const job = await (await post("/jobs", { title: "Clinic Assistant", employer: "Example Health (fictional)" })).json();
  const form = {
    title: "Synthetic form",
    fields: [
      {
        key: "state", label: "State", type: "select", required: true,
        options: [{ value: "", label: "Select one" }, ...STATES.map((s, i) => ({ value: `s${i}`, label: s }))],
      },
      {
        key: "city", label: "City", type: "select", required: true,
        options: [{ value: "s", label: "Springfield" }, { value: "a", label: "Austin" }],
      },
    ],
  };
  expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
  const app = await (await post("/applications", { job_id: job.job.id })).json();
  await page.goto(`/applications/${app.id}`);

  const state = page.getByRole("listitem").filter({ hasText: "Your state of residence (TX) matched the option 'Texas'." });
  await expect(state).toHaveCount(1);
  await expect(state.getByText("Mapped from profile")).toBeVisible();

  const city = page.getByRole("listitem").filter({ has: page.getByLabel("City", { exact: true }) });
  await expect(city).toHaveCount(1);
  await expect(city.getByText(/NoEfforts never picks one from your profile's city/)).toBeVisible();
  await expect(city.getByText("Reuse for this exact question in future applications")).toHaveCount(0);
  await city.getByLabel("City", { exact: true }).selectOption("Springfield");
  await city.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Answer saved.")).toBeVisible();
  await expect(page.getByText("Ready for your approval")).toBeVisible();
});
