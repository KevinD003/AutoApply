import { expect, Page, test } from "@playwright/test";

// D126: the premium job-detail view renders the complete, structured, sanitized `content`
// (GET /jobs/{id}.content) — the description as safe blocks (headings/paragraphs/lists), the
// source's own sections, salary with its provenance, and "Salary not provided." when absent.
// Blocks are rendered as React elements, never raw HTML, so nothing from the posting executes
// or is fetched. Synthetic data only.

async function register(page: Page, info: { project: { name: string } }) {
  const email = `detail.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  return { "X-CSRF-Token": (await reg.json()).csrf_token as string };
}

async function addJob(page: Page, h: Record<string, string>, data: object): Promise<string> {
  const r = await page.request.post("/api/jobs", { headers: h, data });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).job.id as string;
}

test("job detail renders sanitized content and salary provenance", async ({ page }, info) => {
  const h = await register(page, info);

  // A realistic posting pasted with formatting — a heading/list structure, a safe link, a
  // salary line, and an injected <script> that must never run or be rendered as a tag.
  const rich = [
    "<h3>About the role</h3>",
    '<p>Join <b>Northwind</b> as a Journeyman Electrician. <a href="https://example.test/apply">Apply here</a>.</p>',
    "<h3>Responsibilities</h3><ul><li>Install and maintain systems</li><li>Read blueprints</li></ul>",
    "<h3>Compensation</h3><p>We offer $85,000 - $105,000 per year plus benefits.</p>",
    '<script>window.__xss = 1</script><img src="x" onerror="window.__xss = 2">',
  ].join("");
  const richId = await addJob(page, h, {
    title: "Journeyman Electrician",
    employer: "Northwind Utilities (fictional)",
    location: "Riverton, OR",
    description: rich,
  });
  const bareId = await addJob(page, h, {
    title: "Front Desk Associate",
    employer: "Fabrikam (fictional)",
    description: "A friendly front-desk role. Greet visitors and answer calls.",
  });

  // ── The rich posting ──────────────────────────────────────────────────────────────────────
  await page.goto(`/jobs/${richId}`);
  const about = page.getByRole("heading", { name: "About this role" });
  await expect(about).toBeVisible();

  // The description renders with its structure: headings, a list, emphasis.
  const desc = page.getByTestId("job-description");
  await expect(page.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await expect(desc.getByText("Install and maintain systems")).toBeVisible();
  await expect(desc.getByText("Northwind")).toBeVisible(); // the <b> in the description body

  // The safe link survived (http(s)); it opens in a new tab with a safe rel.
  const link = page.getByRole("link", { name: "Apply here" });
  await expect(link).toHaveAttribute("href", "https://example.test/apply");
  await expect(link).toHaveAttribute("rel", /noopener/);

  // Salary was extracted from the text, shown as given, with its provenance; nothing annualized.
  // ($85,000 also appears in the description body, so anchor on the unique provenance line.)
  await expect(page.getByText(/Found in the description text/)).toBeVisible();
  await expect(page.getByText("$85,000", { exact: false }).first()).toBeVisible();

  // The injected script/image never ran, and no <script>/<img> reached the DOM of the content.
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  const body = page.getByTestId("job-description");
  expect(await body.locator("script, img").count()).toBe(0);
  // The tags are gone entirely, not shown as literal text.
  await expect(page.getByText("<script>", { exact: false })).toHaveCount(0);

  await page.screenshot({ path: `test-results/job-detail-${info.project.name}.png`, fullPage: true });

  // ── The posting with no salary ────────────────────────────────────────────────────────────
  await page.goto(`/jobs/${bareId}`);
  await expect(page.getByRole("heading", { name: "About this role" })).toBeVisible();
  await expect(page.getByText("Salary not provided.")).toBeVisible();
  await expect(page.getByText("Greet visitors and answer calls.")).toBeVisible();
});
