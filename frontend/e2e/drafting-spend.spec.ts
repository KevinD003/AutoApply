import { expect, Route, test } from "@playwright/test";

// D97: the Account page shows what AI drafting used against the server's daily budget, each
// amount with its basis. The e2e server has no provider, so the offered view is a synthetic one
// served in place of the server's (the endpoint is tested in
// backend/tests/test_drafting_provider.py); without one the card says nothing is counted.
test("the drafting spend card says what each amount is", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `spend.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/account");
  await expect(page.getByTestId("spend-not-offered")).toBeVisible();

  const totals = { requests: 2, input_tokens: 1200, output_tokens: 300, estimated_usd: 0.0108, worst_case_usd: 0.4 };
  await page.route("**/api/drafting/usage", (route: Route) =>
    route.fulfill({
      json: {
        offered: true,
        provider: "anthropic",
        model: "claude-opus-5-5",
        budget_usd: 5,
        resets: "daily at 00:00 UTC",
        day: "2026-10-31",
        all_accounts_today_usd: 0.4108,
        remaining_usd: 4.5892,
        today: totals,
        days: [{ day: "2026-10-31", ...totals }],
        recent: [
          { at: "2026-10-31T10:01:00Z", provider: "anthropic", model: "claude-opus-5-5", status: "settled",
            outcome: "provider_timeout", cost_usd: 0.4, cost_basis: "unknown", input_tokens: null,
            output_tokens: null, price_version: "anthropic-list-2026-10-06" },
          { at: "2026-10-31T10:00:00Z", provider: "anthropic", model: "claude-opus-5-5", status: "settled",
            outcome: "drafted", cost_usd: 0.0108, cost_basis: "estimated", input_tokens: 1200,
            output_tokens: 300, price_version: "anthropic-list-2026-10-06" },
        ],
        pricing: { version: "anthropic-list-2026-10-06", model: "claude-opus-5-5", input_per_mtok: 4, output_per_mtok: 20 },
      },
    }),
  );
  await page.reload();
  const today = page.getByTestId("spend-today");
  await expect(today).toContainText("$5.0000");
  await expect(today).toContainText("daily at 00:00 UTC");
  await expect(today).toContainText("$4.5892");
  await expect(page.getByText("not an invoice", { exact: false })).toBeVisible();
  const requests = page.getByTestId("spend-requests");
  await expect(requests.getByText("unknown: worst case kept")).toBeVisible();
  await expect(requests.getByText("estimated", { exact: true })).toBeVisible();
  await expect(page.getByTestId("spend-days")).toContainText("worst case kept $0.4000");
  await expect(page.getByText("anthropic-list-2026-10-06", { exact: false })).toBeVisible();
  // Fits a phone: no sideways scrolling.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
