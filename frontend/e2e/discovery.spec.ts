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
  await expect(sources.getByText("Local test fixtures only").first()).toBeVisible(); // served, derived from evidence

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

  // Deleting a listing (D56) removes it and the job it created; a later search never adds it back.
  await page.locator("li", { hasText: "Data Analyst" }).getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Deleted “Data Analyst”; it will not be added again. Its job was removed too.")).toBeVisible();
  await expect(page.getByText("Discovered (4)")).toBeVisible();
  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(page.getByText(/5 listings read/)).toBeVisible();
  await expect(page.getByText("Discovered (4)")).toBeVisible();
  await expect(page.locator("li", { hasText: "Data Analyst" })).toHaveCount(0); // no listing row

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
  await expect(page.getByText("Discovered (4)")).toBeVisible();
  await fhMode(page.request, "normal");
  await page.goto("/jobs");
  await page.getByLabel("Title").fill("Hand-entered role");
  await page.getByLabel("Employer").fill("Example Co (fictional)");
  await page.getByRole("button", { name: "Add job" }).click();
  await expect(page.getByText("Job added.")).toBeVisible();
});

test("watched searches are listed and can be stopped", async ({ page }, info) => {
  // The watch itself is recorded by the owner on the backend host (D56); this checks the page.
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `watch.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  let stopped = false;
  const watch = () => ({
    id: "11111111-1111-4111-8111-111111111111",
    provider: "freehire",
    query: "financial analyst",
    interval_seconds: 60,
    not_after: "2026-12-31T00:00:00Z",
    stopped,
    paused_reason: null,
    last_checked_at: "2026-10-28T01:00:00Z",
    next_check_at: "2026-10-28T01:01:00Z",
    last_outcome: "ok",
    found_total: 3,
  });
  await page.route("**/api/discovery/watches", (route) => route.fulfill({ json: [watch()] }));
  await page.route("**/api/discovery/watches/*/stop", (route) => {
    stopped = true;
    return route.fulfill({ json: watch() });
  });
  await page.goto("/discover");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Watched searches" }) });
  await expect(card.getByText("“financial analyst”")).toBeVisible();
  await expect(card.getByText("active", { exact: true })).toBeVisible();
  await expect(card.getByText(/every 60 s until .* · found 3/)).toBeVisible();
  await card.getByRole("button", { name: "Stop watching" }).click();
  await expect(card.getByText("stopped", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Stop watching" })).toHaveCount(0);
});

test("a listing refreshes from its source; a Retry-After holds the next request back", async ({ page }, info) => {
  // S6 (D67): one record re-read at the source; the linked job is never changed by it.
  await fhMode(page.request, "normal");
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `refresh.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  await page.goto("/discover");
  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(page.getByText("Discovered (5)")).toBeVisible();
  const row = (title: string) => page.locator("li", { hasText: title });

  await row("Field Technician").getByRole("button", { name: "Refresh from source" }).click();
  await expect(page.getByText("“Field Technician” is unchanged at the source.")).toBeVisible();

  await fhMode(page.request, "fh_gone");
  await row("Office Coordinator").getByRole("button", { name: "Refresh from source" }).click();
  await expect(page.getByText(/“Office Coordinator” is no longer at the source\. .*your job was not changed\./)).toBeVisible();
  await expect(row("Office Coordinator").getByText("no longer at the source", { exact: true })).toBeVisible();

  // The source refuses with Retry-After: reported, not retried; then nothing is sent until it runs out.
  const r = await page.request.post(`${RECEIVER}/_admin/config`, {
    headers: { "X-Admin-Token": RECEIVER_TOKEN },
    data: { fh_mode: "fh_rate_limited", fh_retry_after: 600 },
  });
  expect(r.ok()).toBeTruthy();
  await row("Field Technician").getByRole("button", { name: "Refresh from source" }).click();
  await expect(page.getByText(/Freehire is rate limiting requests \(Retry-After: 600 s\); not retried\. Nothing was changed\./)).toBeVisible();
  const back = await page.request.post(`${RECEIVER}/_admin/config`, {
    headers: { "X-Admin-Token": RECEIVER_TOKEN },
    data: { fh_mode: "normal", fh_retry_after: 30 },
  });
  expect(back.ok()).toBeTruthy();
  await row("Field Technician").getByRole("button", { name: "Refresh from source" }).click();
  await expect(page.getByText(/Freehire asked NoEfforts to wait before sending more of your requests; try again after \d\d:\d\d:\d\d UTC\. Nothing was sent\./)).toBeVisible();
  await expect(page.getByText("Discovered (5)")).toBeVisible();
});
