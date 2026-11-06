import { expect, test } from "@playwright/test";

// D133 on the review page: a saved answer suggested for a reworded question can be used here only
// (this application, nothing saved for the wording, so it is suggested again next time) or used
// and saved (kept for the new wording too). Fictional manual forms; synthetic data only.
const SAVED = "Which programming language do you use most?";
const REWORDED = "Which programming language do you use the most?";
const LANGS = [
  { value: "py", label: "Python" },
  { value: "go", label: "Go" },
  { value: "rs", label: "Rust" },
];

test("a suggestion is used here only, then used and saved", async ({ page }, info) => {
  const email = `d133.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const put = (url: string, data: object) => page.request.put(`/api${url}`, { headers: h, data });
  const post = (url: string, data: object) => page.request.post(`/api${url}`, { headers: h, data });
  expect(
    (await put("/profile", { full_name: "Sam Synthetic", given_name: "Sam", family_name: "Synthetic", contact_email: "sam.synthetic@example.com" })).ok(),
  ).toBeTruthy();
  let n = 0;
  async function application(label: string): Promise<string> {
    n += 1;
    const job = await (await post("/jobs", { title: `Synthetic Analyst ${n}`, employer: "Example Health (fictional)" })).json();
    const form = { title: "Synthetic form", fields: [{ key: "lang", label, type: "select", required: true, options: LANGS }] };
    expect((await post(`/jobs/${job.job.id}/form`, { form })).status()).toBe(201);
    return (await (await post("/applications", { job_id: job.job.id })).json()).id as string;
  }
  async function saved(): Promise<number> {
    return ((await (await page.request.get("/api/answer-bank")).json()) as unknown[]).length;
  }

  const first = await application(SAVED);
  const r = await put(`/applications/${first}/answers`, { key: "lang", value: { label: "Python" }, save_to_bank: true });
  expect(r.ok()).toBeTruthy();
  expect(await saved()).toBe(1);

  const suggestion = (p: typeof page) => p.getByTestId("answer-suggestion").filter({ hasText: REWORDED });
  const second = await application(REWORDED);
  await page.goto(`/applications/${second}`);
  await expect(suggestion(page).getByText("Python", { exact: true })).toBeVisible();
  await suggestion(page).getByRole("button", { name: "Use here only" }).click();
  await expect(page.getByText("Answer saved for this application.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Needs your answer \(0\)$/ })).toBeVisible();
  await expect(page.getByTestId("answer-suggestion")).toHaveCount(0);
  expect(await saved()).toBe(1);

  const third = await application(REWORDED);
  await page.goto(`/applications/${third}`);
  const offered = suggestion(page);
  await expect(offered.getByText("Python", { exact: true })).toBeVisible();
  await offered.getByRole("button", { name: "Use and save" }).click();
  await expect(page.getByText("Answer saved, and kept for this exact question next time.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Needs your answer \(0\)$/ })).toBeVisible();
  expect(await saved()).toBe(2);
});
