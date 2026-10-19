import { expect, test } from "@playwright/test";

// Regression test for CI run #2: client-side navigation from /login to /register delayed by
// 1.5s (as on a slow CI runner). Filling immediately after clicking the link filled the
// *login* form's identically labelled fields; the register form then submitted empty.
// The fixed sequence waits for the register page before filling.
test("register after slow navigation from login", async ({ page }) => {
  await page.route(/\/register/, async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await page.goto("/jobs");
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
  await page.getByLabel("Email").fill(`race.${test.info().project.name}.${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("synthetic-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();
});
