import { expect, test } from "@playwright/test";

import { RECEIVER, RECEIVER_TOKEN } from "../playwright.config";

// D95: an employer's public job board, added, read on request, a posting saved, checked daily
// (D96), paused and removed, through the real UI against the receiver's stand-in of the
// documented Greenhouse feed. Its own request ledger is the oracle for what was asked and that
// nothing of the user was sent. Fictional boards and synthetic accounts only.
test("add a job board, read it, save a posting, pause and remove it", async ({ page, request }, info) => {
  const board = `northwind-${info.project.name}-${Date.now()}`;
  await page.request.post("/api/auth/register", {
    data: { email: `boards.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  await page.goto("/discover");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Employer job boards" }) });
  await expect(card.getByText(/Ashby: not available/)).toBeVisible();
  await card.getByLabel("Board (board token)").fill(board);
  await card.getByLabel("Employer").fill("Northwind (fictional)");
  await card.getByRole("button", { name: "Add board" }).click();
  await expect(card.getByText("Not read yet · 0 listed · 0 no longer listed · 0 in your jobs")).toBeVisible();

  await card.getByRole("button", { name: "Read now" }).click();
  await expect(card.getByRole("status")).toHaveText("Read: 2 listed.");
  await card.getByRole("button", { name: "Show postings" }).click();
  const posts = card.getByTestId("board-posting");
  await expect(posts).toHaveCount(2);
  await expect(posts.first().getByText("Source lists it")).toBeVisible();
  await expect((await (await page.request.get("/api/jobs")).json()).items).toHaveLength(0); // nothing added by a read

  const support = posts.filter({ hasText: "Support Specialist (fictional)" });
  await support.getByRole("button", { name: "Save to my jobs" }).click();
  await expect(support.getByRole("link", { name: "In your jobs" })).toBeVisible();
  const saved = (await (await page.request.get("/api/jobs")).json()).items;
  expect(saved.map((j: { title: string }) => j.title)).toEqual(["Support Specialist (fictional)"]);

  // The stand-in's own ledger: one GET of the documented path, no cookie, no credential, no body.
  const l = await (await request.get(`${RECEIVER}/_admin/ledger`, { headers: { "X-Admin-Token": RECEIVER_TOKEN } })).json();
  const mine = (l.board_requests as { method: string; path: string; query: string; cookie: boolean; auth: boolean; body_len: number }[])
    .filter((r) => r.path.includes(board));
  expect(mine).toEqual([{ method: "GET", path: `/gh-board/v1/boards/${board}/jobs`, query: "content=true", cookie: false, auth: false, body_len: 0 }]);

  // D96: a daily check is your choice for this board; the worker reads it (backend tests).
  await card.getByLabel("Check daily").check();
  await expect(card.getByRole("status")).toHaveText("This board will be read once a day; new postings appear in your notifications.");
  await expect(card.getByText("checked daily", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Pause" }).click();
  await expect(card.getByText("checked daily", { exact: true })).toHaveCount(0);
  await expect(card.getByText("paused", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Read now" })).toBeDisabled();
  await card.getByRole("button", { name: "Remove" }).click();
  await expect(card.getByText("Board removed. Jobs you saved from it stay in your jobs.")).toBeVisible();
  await expect(card.getByTestId("board-source")).toHaveCount(0);
  expect((await (await page.request.get("/api/jobs")).json()).items).toHaveLength(1);

  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);
});
