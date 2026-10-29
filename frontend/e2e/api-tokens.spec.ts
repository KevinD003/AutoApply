import { expect, request as pwRequest, test } from "@playwright/test";

// Priority D (D84, docs/api-tokens.md): a token is made on the Account page, shown once, reads
// the account's jobs with the header alone, is refused everything else, and stops working when
// revoked. The script side talks to the API directly, as the CLI and MCP server do (no cookie).
// Synthetic account only.
const API = "http://127.0.0.1:8100/api";

test("a token is shown once, reads within its scope, and stops when revoked", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `tokens.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const title = `Token Role ${info.project.name}`;
  expect((await page.request.post("/api/jobs", { headers: h, data: { url: `https://careers.example.com/tokens/${Date.now()}`, title } })).status()).toBe(201);

  await page.goto("/account");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "API tokens" }) });
  await expect(card.getByText("No tokens yet.")).toBeVisible();
  await card.getByLabel("Label").fill("e2e script");
  await expect(card.getByLabel("Expires after (days)")).toHaveValue("30");
  await card.getByRole("button", { name: "Make a token" }).click();
  const shown = card.getByLabel("New API token");
  await expect(shown).toHaveText(/^ne_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$/);
  const token = (await shown.textContent())!;
  await expect(card.getByText("it is shown only once")).toBeVisible();
  const row = card.getByRole("list", { name: "Your API tokens" }).getByRole("listitem");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("e2e script");
  await expect(row).toContainText("active");
  await expect(row).toContainText(`ne_${token.slice(3, 11)}_…`);

  // A script: no cookie, the header only.
  const script = await pwRequest.newContext();
  const auth = { Authorization: `Bearer ${token}` };
  const jobs = await script.get(`${API}/jobs`, { headers: auth });
  expect(jobs.status()).toBe(200);
  expect((await jobs.json()).items.map((j: { title: string }) => j.title)).toEqual([title]);
  // Outside its scope: refused, whatever the route.
  expect((await script.post(`${API}/jobs`, { headers: auth, data: { url: "https://careers.example.com/x" } })).status()).toBe(403);
  expect((await script.get(`${API}/account/tokens`, { headers: auth })).status()).toBe(403);
  expect((await script.get(`${API}/account/export`, { headers: auth })).status()).toBe(403);
  expect((await script.get(`${API}/profile`, { headers: auth })).status()).toBe(403);

  // Shown once: gone from the page after "I have copied it", and after a reload.
  await card.getByRole("button", { name: "I have copied it" }).click();
  await expect(card.getByLabel("New API token")).toHaveCount(0);
  await page.reload();
  expect(await page.content()).not.toContain(token);
  await expect(row).toContainText("last used");

  await row.getByRole("button", { name: "Revoke" }).click();
  await expect(row).toContainText("revoked");
  await expect(row.getByRole("button", { name: "Revoke" })).toHaveCount(0);
  const after = await script.get(`${API}/jobs`, { headers: auth });
  expect(after.status()).toBe(401);
  expect((await after.json()).detail).toContain("(reason: token_invalid)");
  await script.dispose();
});
