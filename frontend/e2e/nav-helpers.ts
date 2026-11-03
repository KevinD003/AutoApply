import { Page } from "@playwright/test";

// D125 mobile navigation: the secondary destinations (Documents, Saved answers, Profile,
// Preferences, Account) are top-nav links on desktop but live in the floating bottom nav's
// "More" sheet below `sm`. Open "More" first when it is present, so a subsequent
// getByRole("link", { name }) click resolves on both the desktop (1280) and mobile (390)
// projects. A no-op on desktop, where the "More" button is display:none.
export async function openMoreIfMobile(page: Page) {
  const more = page.getByRole("button", { name: "More", exact: true });
  if (await more.isVisible().catch(() => false)) await more.click();
}
