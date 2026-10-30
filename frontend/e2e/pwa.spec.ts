import { expect, Page, test } from "@playwright/test";

// D89: NoEfforts can be installed as a web app. Its service worker keeps exactly one thing for
// offline use, a static offline page: never a page of the app, an API response or anything
// about you. Synthetic account only.
test.use({ serviceWorkers: "allow" });
test.describe.configure({ mode: "serial" });

async function register(page: Page, tag: string) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `pwa.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
}

async function cachedPaths(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const out: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const req of await cache.keys()) out.push(new URL(req.url).pathname);
    }
    return out.sort();
  });
}

async function controlled(page: Page) {
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => undefined));
  if (!(await page.evaluate(() => !!navigator.serviceWorker.controller))) await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
}

test("the app can be installed: a manifest with icons and a service worker", async ({ page, request }) => {
  await page.goto("/login");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBe("/manifest.webmanifest");
  const manifest = await (await request.get(href!)).json();
  expect(manifest).toMatchObject({ name: "NoEfforts", short_name: "NoEfforts", start_url: "/jobs", display: "standalone" });
  const sizes = (manifest.icons as { sizes: string; type: string; src: string }[]).map((i) => i.sizes);
  expect(sizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  for (const icon of manifest.icons as { src: string }[]) {
    const r = await request.get(icon.src);
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toContain("image/png");
  }
  await controlled(page);
  const script = await page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? "");
  expect(new URL(script).pathname).toBe("/sw.js");
});

test("offline, a page shows the offline page, and nothing about you was kept on the device", async ({ page, context }, info) => {
  await register(page, info.project.name);
  await page.goto("/jobs");
  await controlled(page);
  // Browse the app online first: none of it may end up in the worker's cache.
  for (const path of ["/jobs", "/tracker", "/notifications", "/profile"]) {
    await page.goto(path);
    await expect(page.locator("body")).not.toBeEmpty();
  }
  expect(await cachedPaths(page)).toEqual(["/icons/icon-192.png", "/offline.html"]);

  await context.setOffline(true);
  try {
    await page.goto("/tracker");
    await expect(page.locator("[data-offline-page]")).toBeVisible();
    await expect(page.getByRole("heading", { name: "You are offline" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("example.com"); // nothing about you
  } finally {
    await context.setOffline(false);
  }
  await page.goto("/tracker");
  await expect(page.locator("[data-offline-page]")).toHaveCount(0); // back online: the real page
  expect(await cachedPaths(page)).toEqual(["/icons/icon-192.png", "/offline.html"]);
});
