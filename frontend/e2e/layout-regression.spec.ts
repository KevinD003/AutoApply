import { expect, Page, test, TestInfo } from "@playwright/test";

// Maintained layout/navigation regression guard (Slice A). Real assertions, not screenshots:
// it encodes the invariants the UX layout investigation established
// (docs/ux-layout-investigation.md), so a future change cannot silently reintroduce a real
// overlap, an unpinned header, or horizontal overflow. Runs on both the desktop (1280) and
// mobile (390) projects; the fixed bottom nav exists only on the mobile project (sm:hidden),
// so its invariants are guarded by the project. Synthetic data only.

const isMobile = (info: TestInfo) => info.project.name === "mobile";

async function register(page: Page, info: TestInfo): Promise<Record<string, string>> {
  const email = `layout.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  // Enough jobs — one with a long description — that the list is taller than the viewport, so
  // "scrolled to the bottom" genuinely exercises the fixed bottom nav against real content.
  const jobs = [
    { title: "Senior Platform Engineer", employer: "Northwind Analytics", location: "Remote (US)", description: "We offer $150,000 - $190,000 per year. ".repeat(20) },
    { title: "Registered Nurse, ICU", employer: "Cedar Valley Health", location: "Springfield, IL" },
    { title: "Journeyman Electrician", employer: "Synthetic Power Co", location: "Austin, TX" },
    { title: "Warehouse Associate", employer: "Fabrikam Depot", location: "Reno, NV" },
    { title: "Product Designer", employer: "Globex Studio", location: "Hybrid (Berlin)" },
  ];
  for (const data of jobs) {
    expect((await page.request.post("/api/jobs", { headers: h, data })).ok()).toBeTruthy();
  }
  return h;
}

// Lowest interactive element in <main>, and the fixed bottom nav's top edge, in viewport
// coordinates (what the user sees). Used to prove nothing is tucked behind the nav.
async function lowestVsNav(page: Page) {
  return page.evaluate(() => {
    const nav = document.querySelector('nav[aria-label="Primary"]') as HTMLElement | null;
    if (!nav) return null;
    const navTop = nav.getBoundingClientRect().top;
    let lowest = -Infinity;
    let offender = "";
    for (const el of Array.from(document.querySelectorAll("main a, main button, main input, main select, main textarea"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue; // not rendered
      if (r.bottom > lowest) {
        lowest = r.bottom;
        offender = (el.textContent || (el as HTMLElement).getAttribute("aria-label") || el.tagName).trim().slice(0, 40);
      }
    }
    return { navTop, lowest, offender };
  });
}

test("the sticky header stays pinned and the page never overflows horizontally", async ({ page }, info) => {
  await register(page, info);

  for (const path of ["/jobs", "/profile"]) {
    await page.goto(path);
    await expect(page.getByRole("banner")).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);

    const headerTop = () => page.getByRole("banner").evaluate((el) => el.getBoundingClientRect().top);
    expect(await headerTop(), `header at top of ${path}`).toBeLessThanOrEqual(1);
    await page.evaluate(() => window.scrollTo(0, Math.round(document.body.scrollHeight / 2)));
    await page.waitForTimeout(150);
    expect(await headerTop(), `header still pinned after scroll on ${path}`).toBeLessThanOrEqual(1);
    await page.evaluate(() => window.scrollTo(0, 0));
  }
});

test("the fixed bottom nav never hides content or primary actions", async ({ page }, info) => {
  test.skip(!isMobile(info), "the fixed bottom nav only exists on the mobile viewport");
  await register(page, info);
  await page.goto("/jobs");
  await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();
  // Wait for the list to load so the page is taller than the viewport (real content below the fold).
  await expect(page.getByRole("link", { name: "Senior Platform Engineer", exact: true })).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(200);
  const res = await lowestVsNav(page);
  expect(res, "no fixed bottom nav found").not.toBeNull();
  expect(res!.lowest, `"${res!.offender}" sits under the bottom nav`).toBeLessThanOrEqual(res!.navTop + 1);
});

test("swipe decision controls are reachable, not hidden behind the bottom nav", async ({ page }, info) => {
  await register(page, info);
  await page.goto("/jobs");
  await page.getByRole("tab", { name: "Swipe" }).click();

  const apply = page.getByRole("button", { name: "Apply to this job" });
  const pass = page.getByRole("button", { name: "Pass this job" });
  await expect(apply).toBeVisible();
  await expect(pass).toBeVisible();

  if (isMobile(info)) {
    // The controls sit below the deck, so they start below the fold; the invariant is that they
    // can be brought fully ABOVE the fixed bottom nav (reachable), which scrolling to the end does.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(200);
    const r = await page.evaluate(() => {
      const nav = (document.querySelector('nav[aria-label="Primary"]') as HTMLElement).getBoundingClientRect();
      const btns = Array.from(document.querySelectorAll("button")).filter((b) => /this job$/.test(b.getAttribute("aria-label") || ""));
      const low = Math.max(...btns.map((b) => b.getBoundingClientRect().bottom));
      return { navTop: nav.top, low };
    });
    expect(r.low, "swipe controls under the bottom nav").toBeLessThanOrEqual(r.navTop + 1);
  }
});

test("the app is fully usable with reduced motion", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await register(page, info);
  await page.goto("/jobs");

  await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Senior Platform Engineer", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Swipe" }).click();
  await expect(page.getByRole("button", { name: "Apply to this job" })).toBeVisible();
  await page.getByRole("tab", { name: "List" }).click();
  await expect(page.getByRole("link", { name: "Registered Nurse, ICU", exact: true })).toBeVisible();
});
