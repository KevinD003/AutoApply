import { expect, test } from "@playwright/test";

// Priority C (D78): a saved answer is edited as a new version with its history kept, and a
// document's text is previewed as plain text only. Synthetic account and local test form only.

test("a saved answer is edited as a new version, with its history", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `answers-edit.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/jobs");
  await page.getByLabel("Title").fill("Front Desk Associate");
  await page.getByLabel("Employer").fill("Example Logistics (fictional)");
  await page.getByRole("button", { name: "Add job" }).click();
  await page.getByText("Front Desk Associate").click();
  await page.getByLabel("Test form").selectOption("tricky");
  await page.getByRole("button", { name: "Attach test form" }).click();
  await expect(page.getByText(/Form v1 · 17 questions/)).toBeVisible();
  await page.getByRole("button", { name: "Prepare application" }).click();
  const edu = page.getByRole("listitem").filter({ has: page.getByLabel("Highest level of education completed") });
  await edu.getByLabel("Highest level of education completed").selectOption("Bachelor's degree");
  await edu.getByText("Reuse for this exact question in future applications").click();
  await edu.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Answer saved.")).toBeVisible();

  await page.getByRole("link", { name: "Saved answers" }).click();
  const item = page.getByRole("listitem").filter({ hasText: "Highest level of education completed" });
  await expect(item.getByText("Bachelor's degree", { exact: true })).toBeVisible();
  await item.getByRole("button", { name: "Edit" }).click();
  await item.getByLabel("New answer").selectOption("master's degree or higher");
  await item.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByText(/^Saved as version 2\./)).toBeVisible();
  await expect(item.getByText("master's degree or higher", { exact: true })).toBeVisible();
  await expect(item.getByText(/^v2 · updated/)).toBeVisible();
  // The question it answers is unchanged.
  await expect(item.getByText("Help text when saved: Choose the highest level you have finished.")).toBeVisible();

  await item.getByRole("button", { name: "History" }).click();
  const versions = item.getByRole("list", { name: "Versions" }).getByRole("listitem");
  await expect(versions).toHaveCount(2);
  await expect(versions.nth(0)).toContainText("v2: master's degree or higher · edited by you");
  await expect(versions.nth(1)).toContainText("v1: Bachelor's degree · saved from an application");
});

test("a document's text is previewed as plain text, never rendered", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `preview.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const text = '<img src="x" onerror="window.__ran=1"><script>window.__ran=2</script>\nSynthetic notes';
  const r = await page.request.post("/api/documents", {
    headers: h,
    multipart: { file: { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from(text) }, kind: "other" },
  });
  expect(r.status()).toBe(201);
  const outside: string[] = [];
  page.on("request", (req) => {
    const u = new URL(req.url());
    if (u.hostname !== "localhost" && u.hostname !== "127.0.0.1") outside.push(u.hostname);
  });

  await page.goto("/documents");
  await page.getByRole("button", { name: "Preview text" }).click();
  const shown = page.getByLabel("Text of notes.txt");
  await expect(shown).toContainText('<img src="x" onerror="window.__ran=1">');
  await expect(shown).toContainText("Synthetic notes");
  await expect(page.getByText(/as plain text; layout and images are not shown/)).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __ran?: number }).__ran)).toBeUndefined();
  expect(await shown.locator("img, script").count()).toBe(0);
  expect(outside).toEqual([]);
  await page.getByRole("button", { name: "Hide text" }).click();
  await expect(shown).toHaveCount(0);
});
