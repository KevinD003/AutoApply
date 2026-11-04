import { expect, Page, test } from "@playwright/test";

// D124: mobile swipe discovery, wired to the real API. Right = Apply (application
// INTENT: the job is shortlisted to prepare — never a submission, never an "Applied"
// state). Left = Pass (excluded, reason "Passed in discovery"). Both persist
// account-scoped, both undo, passed roles stay in the Excluded collection. Uses the
// always-present accessible Apply/Pass buttons (the documented swipe fallback), so it
// runs identically on desktop and the mobile project. Synthetic data only.

async function register(page: Page, info: { project: { name: string } }) {
  const email = `swipe.${info.project.name}.${Date.now()}@example.com`;
  const reg = await page.request.post("/api/auth/register", { data: { email, password: "synthetic-password-1" } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  for (const t of ["Swipe Role A", "Swipe Role B", "Swipe Role C"]) {
    const r = await page.request.post("/api/jobs", { headers: h, data: { title: t, employer: "Synthetic Co" } });
    expect(r.ok()).toBeTruthy();
  }
  return h;
}

test("swipe discovery: apply shortlists, pass excludes, both persist and undo; no Applied state", async ({ page }, info) => {
  await register(page, info);
  await page.goto("/jobs");

  await page.getByRole("tab", { name: "Swipe" }).click();
  const tally = page.getByText(/\d+ to apply · \d+ passed/);
  await expect(tally).toHaveText("0 to apply · 0 passed");

  // Apply (right) on the top card.
  await page.getByRole("button", { name: "Apply to this job" }).click();
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // Pass (left) on the next card.
  await page.getByRole("button", { name: "Pass this job" }).click();
  await expect(tally).toHaveText("1 to apply · 1 passed");

  // Undo the pass.
  await page.getByRole("button", { name: "Undo the last decision" }).click();
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // Back to the list: exactly one shortlisted job, with a "Start application" action,
  // and it is NOT shown as "Applied". Nothing is in the Excluded (passed) collection.
  await page.getByRole("tab", { name: "List" }).click();
  await page.getByLabel("Filter by status").selectOption("shortlisted");
  const shortlisted = page.locator("li").filter({ has: page.getByRole("button", { name: "Start application" }) });
  await expect(shortlisted).toHaveCount(1);
  await expect(page.getByText("Applied", { exact: true })).toHaveCount(0);

  await page.getByLabel("Filter by status").selectOption("excluded");
  await expect(page.getByText("Passed in discovery")).toHaveCount(0);

  // Persistence: the shortlist survives a reload (it was saved via the API).
  await page.reload();
  await page.getByLabel("Filter by status").selectOption("shortlisted");
  await expect(page.locator("li").filter({ has: page.getByRole("button", { name: "Start application" }) })).toHaveCount(1);
});

test("swipe gesture: a drag past the threshold commits; a short drag snaps back with no decision", async ({ page }, info) => {
  // The pointer-drag path itself (useSwipe: axis-lock, threshold, snap-back), not just the
  // always-present buttons. A horizontal drag past the threshold decides; a short drag below it
  // is a cancelled gesture that must restore the card and record nothing. Synthetic data only.
  await register(page, info);
  await page.goto("/jobs");
  await page.getByRole("tab", { name: "Swipe" }).click();

  const tally = page.getByText(/\d+ to apply · \d+ passed/);
  await expect(tally).toHaveText("0 to apply · 0 passed");

  const deck = page.getByRole("group", { name: /Job discovery deck/ });
  await expect(deck).toBeVisible();

  // A deliberate pointer drag on the top card, started in its (non-interactive) header so the
  // gesture engages — useSwipe ignores pointerdowns that land on a link/button/control.
  async function drag(dx: number) {
    const box = (await deck.boundingBox())!;
    const x = box.x + box.width / 2;
    const y = box.y + 40; // the card's gradient header: no link or button sits there
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 12, y); // cross the 8px axis-decide horizontally -> engage the swipe
    await page.mouse.move(x + dx, y, { steps: 12 });
    await page.mouse.up();
  }

  // Far to the right, past the 110px threshold = Apply. The card animates off and the decision
  // is saved via the API; the tally reflects exactly one "to apply".
  await drag(220);
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // A short drag (30px: below the 110px threshold and below the 40px flick distance) is a
  // cancelled gesture — it must snap back and record nothing.
  await drag(30);
  await expect(tally).toHaveText("1 to apply · 0 passed");

  // The card that snapped back is unharmed and still swipeable: a full drag now commits it too,
  // proving the cancel left the deck in a working state (not a stuck or half-committed card).
  await drag(220);
  await expect(tally).toHaveText("2 to apply · 0 passed");

  // Nothing is ever shown as "Applied": apply is an intent to prepare, never a submission.
  await expect(page.getByText("Applied", { exact: true })).toHaveCount(0);
});
