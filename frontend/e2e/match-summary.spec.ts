import { expect, test } from "@playwright/test";

// B (D82): the jobs list shows the job page's match explanation in one line: your preferences
// counted, your approved qualifications the job names, how much is unknown, and a link to the
// full explanation. No score, verdict or probability. Synthetic account and jobs only.

test("each listed job summarises its match explanation and links to it", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `match-summary.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  expect((await page.request.put("/api/profile", { headers: h, data: { skills: ["Excel", "Scheduling"] } })).ok()).toBeTruthy();
  expect((await page.request.put("/api/profile/preferences", { headers: h, data: { titles: ["Support Specialist"] } })).ok()).toBeTruthy();
  expect((await page.request.post("/api/profile/credentials", { headers: h, data: { name: "CPR", expires_on: "2030-01-01" } })).status()).toBe(201);
  const add = async (data: object) => {
    const r = await page.request.post("/api/jobs", { headers: h, data });
    expect(r.ok()).toBeTruthy();
    return (await r.json()).job.id as string;
  };
  const withText = await add({
    url: `https://careers.example.com/match/${Date.now()}/1`,
    title: "Support Specialist",
    employer: "Fictional Clinic",
    description: "Answer patients' calls. Daily Excel reports. CPR certification required.",
  });
  await add({ url: `https://careers.example.com/match/${Date.now()}/2`, title: "Warehouse Associate", employer: "Fictional Depot" });

  await page.goto("/jobs");
  const row = (title: string) => page.locator("li", { has: page.getByRole("link", { name: title, exact: true }) });
  const first = row("Support Specialist").getByTestId("match-summary");
  await expect(first).toContainText("Your preferences: 1 of 1 checked preferences met");
  await expect(first).toContainText("Names your skills: Excel; licences: CPR");
  const second = row("Warehouse Associate").getByTestId("match-summary");
  await expect(second).toContainText("Your preferences: 0 of 1 checked preferences met");
  // No description: nothing was compared, which is not the same as "names none of yours".
  await expect(second).toContainText("Skills and licences not compared");
  // A job that matches nothing is still listed; nothing is hidden or ranked down.
  await expect(page.getByRole("link", { name: "Warehouse Associate", exact: true })).toBeVisible();
  for (const s of [first, second]) {
    const text = ((await s.textContent()) ?? "").toLowerCase();
    for (const word of ["score", "eligib", "sponsor", "likely", "chance", "%", "qualif"]) {
      expect(text, word).not.toContain(word);
    }
  }
  const unknown = Number(((await first.textContent()) ?? "").match(/(\d+) not known/)?.[1] ?? 0);

  await first.getByRole("link", { name: "Why" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${withText}#match$`));
  const why = page.locator("#match");
  await expect(why.getByRole("heading", { name: "Why this job matches (or doesn't)" })).toBeInViewport();
  await expect(why.getByText("Your preferences: 1 of 1 checked preferences met")).toBeVisible();
  // The list's "not known" count is the job page's list of what is missing.
  await expect(why.getByRole("list", { name: "Missing information" }).getByRole("listitem")).toHaveCount(unknown);
});
