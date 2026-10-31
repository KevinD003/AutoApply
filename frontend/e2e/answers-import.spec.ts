import { expect, test } from "@playwright/test";

// D99: saved answers imported from a file are checked by the rules for saved answers, added as
// proposals and used only once approved. Synthetic rows only.
test("saved answers are imported as proposals and approved one by one", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `import.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/answers");
  await expect(page.getByText("No saved answers yet.")).toBeVisible();
  const rows = [
    { question: "Do you have advanced spreadsheet skills?", answer: "Yes" },
    { question: "Are you authorized to work in the United States?", answer: "Yes" },
    { question: "Do you attend church regularly?", answer: "No" },
    { question: "Have you worked for {company} before?", answer: "No" },
  ];
  await page.getByLabel("File of questions and answers").setInputFiles({
    name: "answers.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(rows)),
  });
  const check = page.getByTestId("import-check");
  await expect(check).toContainText("4 rows: 1 can be added, 3 not imported.");
  await expect(check).toContainText("work authorization, sponsorship, citizenship or residence");
  await expect(check).toContainText("a sensitive topic");
  await expect(check).toContainText("{company}");
  await page.getByRole("button", { name: "Add 1 as proposals" }).click();
  await expect(page.getByText("1 added as proposals.")).toBeVisible();

  const item = page.getByRole("listitem").filter({ hasText: "Do you have advanced spreadsheet skills?" });
  await expect(item.getByText("Not used until you approve it.")).toBeVisible();
  await item.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved: it now answers this exact question.")).toBeVisible();
  await expect(item.getByText("Not used until you approve it.")).toHaveCount(0);
  await expect(item.getByRole("button", { name: "Approve" })).toHaveCount(0);

  // A review sheet: only the rows marked yes or edit, an edit with its corrected answer.
  const csv =
    'approve (yes/no/edit),your corrected answer,question,answer\n' +
    'yes,,Do you enjoy public speaking?,Yes\n' +
    'no,,Do you like spreadsheets?,Yes\n' +
    'edit,Python and SQL,"Which languages do you use, mostly?",Python\n';
  await page.getByLabel("File of questions and answers").setInputFiles({
    name: "review.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(check).toContainText("2 rows: 2 can be added");
  await page.getByRole("button", { name: "Add 2 as proposals" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Which languages do you use, mostly?" })).toContainText("Python and SQL");
  await expect(page.getByText("Do you like spreadsheets?")).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
