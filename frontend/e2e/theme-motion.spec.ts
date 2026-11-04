import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

// Slice D: a maintained assertion suite for the theme — driven through the REAL toggle control in
// the header, never page.emulateMedia({colorScheme}), which the app deliberately ignores — for the
// single motion system's reduced-motion behaviour, and for the non-purple petrol/teal palette.
// Synthetic data only. The brand row (with the toggle) is on every viewport, so these run on both
// the desktop and mobile projects.

async function register(page: Page, info: TestInfo) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `theme.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
}

const token = (page: Page, name: string) =>
  page.evaluate((n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name);
const dataTheme = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-theme"));
const bodyBg = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
// Computed animation-duration comes back in seconds ("0.3s") or ms ("0.001ms"); normalise to ms.
const animMs = (loc: Locator) =>
  loc.evaluate((el: Element) => {
    const d = getComputedStyle(el).animationDuration;
    return d.endsWith("ms") ? parseFloat(d) : parseFloat(d) * 1000;
  });

test("the theme is driven by the real toggle, applies its tokens and persists", async ({ page }, info) => {
  await register(page, info);
  await page.goto("/jobs");
  await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();

  // Default is light during the migration; the one accent is the deep petrol/teal, never a purple.
  expect(await dataTheme(page)).not.toBe("dark");
  expect((await token(page, "--brand")).toLowerCase()).toBe("#0c6b74");
  const lightSurface = await token(page, "--surface");
  const lightBg = await bodyBg(page);

  // Switch to dark through the actual header control (not media emulation).
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  expect(await dataTheme(page)).toBe("dark");
  await expect(page.getByRole("button", { name: "Switch to light theme" })).toBeVisible();
  // The dark tokens actually took effect — not just the attribute flipping.
  expect((await token(page, "--brand")).toLowerCase()).toBe("#2fb6b0");
  expect(await token(page, "--surface")).not.toBe(lightSurface);
  expect(await bodyBg(page)).not.toBe(lightBg);
  expect(await page.evaluate(() => localStorage.getItem("ne-theme"))).toBe("dark");

  // The choice survives a reload (the root layout's pre-paint script re-applies it before paint).
  await page.reload();
  expect(await dataTheme(page)).toBe("dark");
  expect(await bodyBg(page)).not.toBe(lightBg);

  // And back to light through the control; the tokens revert exactly.
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  expect(await dataTheme(page)).toBe("light");
  expect((await token(page, "--brand")).toLowerCase()).toBe("#0c6b74");
  expect(await token(page, "--surface")).toBe(lightSurface);
  expect(await bodyBg(page)).toBe(lightBg);
});

test("reduced motion collapses the one motion system without hiding content", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await register(page, info);
  await page.goto("/jobs");

  // The route-transition entrance wrapper is present and its content is readable at once...
  const risen = page.locator(".animate-rise").first();
  await expect(risen).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();
  // ...with its entrance animation collapsed to ~instant by the single reduced-motion rule.
  expect(await animMs(risen)).toBeLessThanOrEqual(1);
});

test("with motion allowed the entrance animation is real (demonstrated, not claimed)", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await register(page, info);
  await page.goto("/jobs");

  const risen = page.locator(".animate-rise").first();
  await expect(risen).toBeVisible();
  // The same element animates for a real, bounded duration when motion is allowed — so the
  // reduced-motion rule above is gating one real motion system, not decorating a no-op.
  expect(await animMs(risen)).toBeGreaterThan(1);
});
