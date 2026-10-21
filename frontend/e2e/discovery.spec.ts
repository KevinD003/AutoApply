import { APIRequestContext, expect, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// Discovery through the local stand-in of Freehire's documented read API on the receiver
// (fixtures/ats_receiver/freehire_fixture.py). Synthetic listings only; nothing contacts Freehire.

async function fhMode(request: APIRequestContext, mode: string) {
  const r = await request.post(`${RECEIVER}/_admin/config`, { headers: { "X-Admin-Token": RECEIVER_TOKEN }, data: { fh_mode: mode } });
  expect(r.ok()).toBeTruthy();
}

test("discover jobs: source, import result, duplicates, incomplete fields, outage", async ({ page }, info) => {
  await fhMode(page.request, "normal");
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `discover.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const csrf = (await reg.json()).csrf_token as string;
  // A job the user already has: discovery must link to it, not duplicate or change it.
  const mine = await page.request.post("/api/jobs", {
    headers: { "X-CSRF-Token": csrf },
    data: { url: `${RECEIVER}/gh2/northwind/jobs/5020002`, title: "My own title" },
  });
  expect(mine.status()).toBe(201);

  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "Discover jobs" })).toBeVisible();
  await expect(page.getByText(/They are not verified/)).toBeVisible();
  const sources = page.locator("section", { has: page.getByRole("heading", { name: "Sources" }) });
  await expect(sources.getByText("enabled", { exact: true })).toBeVisible();
  await expect(sources.getByText("not tested against the live service").first()).toBeVisible();

  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(
    page.getByText(/5 listings read \(3 pages\): 5 new, 0 changed, 0 unchanged; 2 added to your jobs, 2 already there; 1 incomplete/),
  ).toBeVisible();
  await expect(page.getByText("Discovered (5)")).toBeVisible();
  await expect(page.getByText("Source: Freehire").first()).toBeVisible();
  await expect(page.getByText(/Missing: no job or application URL/)).toBeVisible();
  // Every listing carries the source's credit (no documented listing-page URL: text only).
  await expect(page.getByText("via freehire.me", { exact: true })).toHaveCount(5);
  await expect(page.getByText(/sponsorship: source says yes \(provider enrichment\)/).first()).toBeVisible();
  await expect(page.getByText(/sponsorship: source not stated/).first()).toBeVisible();

  // The already-tracked job is linked as it is, and shows its source.
  await expect(page.getByRole("link", { name: "already in your jobs (same job link)" }).first()).toBeVisible();
  await page.goto(`/jobs/${(await mine.json()).job.id}`);
  await expect(page.getByText("Found through a discovery source")).toBeVisible();
  await expect(page.getByText("via freehire.me", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "My own title" })).toBeVisible();

  // A source outage changes nothing and says so; adding a job by hand still works.
  await fhMode(page.request, "fh_outage");
  await page.goto("/discover");
  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(page.getByText("Freehire is unavailable (HTTP 503). Nothing was changed.")).toBeVisible();
  await expect(page.getByText("Discovered (5)")).toBeVisible();
  await fhMode(page.request, "normal");
  await page.goto("/jobs");
  await page.getByLabel("Title").fill("Hand-entered role");
  await page.getByLabel("Employer").fill("Example Co (fictional)");
  await page.getByRole("button", { name: "Add job" }).click();
  await expect(page.getByText("Job added.")).toBeVisible();
});
