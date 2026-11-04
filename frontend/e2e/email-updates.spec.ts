import { expect, Route, test } from "@playwright/test";

// Email-to-application status tracking (spec §9), through the real tracker UI. The e2e server has
// no Gmail connected and the read_application_email authorization is not recorded, so — exactly as
// inbox.spec.ts does — the /api/inbox endpoint is served from a synthetic view here; the gating
// and the stateful flows (auto-apply, correct/undo/relink, temporal guards, tenant isolation) are
// proven against the real API and a local Gmail stand-in in backend/tests/test_inbox.py.

const APP1 = "00000000-0000-4000-8000-000000000001";
const APP2 = "00000000-0000-4000-8000-000000000002";

type Call = { method: string; path: string; body?: unknown };

async function register(page: import("@playwright/test").Page, name: string) {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `updates.${name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
}

test("the tracker proposes email updates and you confirm, correct, undo and re-link them", async ({ page }, info) => {
  await register(page, info.project.name);

  const states: Record<string, string> = { p1: "proposed", p2: "proposed", a1: "auto_applied", u1: "unlinked" };
  const links: Record<string, string | null> = { p1: APP1, p2: APP1, a1: APP2, u1: null };
  const base: Record<string, Record<string, unknown>> = {
    p1: { kind: "rejected", proposed_outcome: "rejected", prev_outcome: "none", why_matched: "the requisition ID in the message", automatic: false, match_band: "strong", class_band: "explicit", sender_domain: "acme-mail.greenhouse.io", received_at: "2026-10-30T09:00:00Z" },
    p2: { kind: "assessment", proposed_outcome: "assessment_received", prev_outcome: "none", why_matched: "the employer's name, the job title", automatic: false, match_band: "good", class_band: "explicit", sender_domain: "northwind.example", received_at: "2026-10-30T08:00:00Z" },
    a1: { kind: "interview_scheduled", proposed_outcome: "interviewing", prev_outcome: "none", why_matched: "an earlier message in the same email thread", automatic: true, match_band: "strong", class_band: "explicit", sender_domain: "contoso.example", received_at: "2026-10-29T09:00:00Z" },
    u1: { kind: "offer", proposed_outcome: "offer", prev_outcome: null, why_matched: null, automatic: false, match_band: "weak", class_band: "explicit", sender_domain: "mailer.unknown-bulk.example", received_at: "2026-10-28T09:00:00Z" },
  };
  const view = () => ({
    available: true,
    why_not: null,
    codes_enabled: true,
    tracking_enabled: true,
    auto_apply: true,
    scope_note: "NoEfforts uses read-only Gmail access; it stores no message text and sends nothing.",
    last_checked_at: "2026-10-31T10:00:00Z",
    last_error: null,
    events: ["p1", "p2", "a1", "u1"].map((id) => ({
      id,
      state: states[id],
      application_id: links[id],
      needs_review: states[id] === "proposed" || states[id] === "review",
      ...base[id],
    })),
  });

  const calls: Call[] = [];
  await page.route("**/api/inbox**", async (route: Route) => {
    const req = route.request();
    const url = req.url();
    const path = url.slice(url.indexOf("/api/inbox"));
    const body = req.method() === "POST" && req.postData() ? JSON.parse(req.postData()!) : undefined;
    calls.push({ method: req.method(), path, body });
    const m = path.match(/\/events\/(\w+)\/(accept|undo|dismiss|relink)/);
    if (m) {
      const [, id, action] = m;
      if (action === "accept") states[id] = "accepted";
      else if (action === "undo") states[id] = "undone";
      else if (action === "dismiss") states[id] = "dismissed";
      else if (action === "relink") {
        const to = (body as { application_id?: string } | undefined)?.application_id ?? null;
        links[id] = to;
        states[id] = to ? "proposed" : "unlinked";
      }
    }
    await route.fulfill({ json: view() });
  });
  await page.route("**/api/applications", async (route: Route) => {
    await route.fulfill({
      json: [
        { id: APP1, job: { title: "Support Specialist", employer: "Northwind Example" }, state: "submitted_unconfirmed", outcome: "none", reached_submission: true },
        { id: APP2, job: { title: "Data Analyst", employer: "Contoso Example" }, state: "submitted_unconfirmed", outcome: "none", reached_submission: true },
      ],
    });
  });

  await page.goto("/tracker");
  await expect(page.getByText("Email updates", { exact: true })).toBeVisible();
  const updates = page.getByTestId("email-updates");

  // Each recognised event reads as something, says what it would record, and why it matched —
  // with the one that was applied automatically marked as such (spec §2/§3/§4/§9).
  const p1 = updates.locator("li", { hasText: "reads as a rejection" });
  const p2 = updates.locator("li", { hasText: "reads as an assessment" });
  const a1 = updates.locator("li", { hasText: "reads as a scheduled interview" });
  const u1 = updates.locator("li", { hasText: "reads as an offer" });
  await expect(p1).toContainText("Would record: Employer declined");
  await expect(p1).toContainText("Matched by the requisition ID in the message");
  await expect(a1).toContainText("Recorded automatically: Interviewing");
  await expect(a1).toContainText("Matched by an earlier message in the same email thread");
  await expect(u1).toContainText("Would record: Offer");

  // Confirm a clear proposal; it records the outcome and shows as recorded.
  await p1.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByText("Recorded on the application.")).toBeVisible();
  await expect(p1).toContainText("recorded by you");

  // Correct one: record a different outcome than the email read as.
  await p2.getByRole("button", { name: "Correct…" }).click();
  await p2.getByLabel("Outcome to record").selectOption("interviewing");
  await p2.getByRole("button", { name: "Record", exact: true }).click();
  await expect(p2).toContainText("recorded by you");

  // Undo the automatically applied one; it leaves the actionable list.
  await a1.getByRole("button", { name: "Undo" }).click();
  await expect(updates.locator("li", { hasText: "reads as a scheduled interview" })).toHaveCount(0);

  // Re-link an unlinked one to the right application ("wrong application"); it becomes a proposal.
  await u1.getByRole("button", { name: "Wrong application" }).click();
  await u1.getByLabel("Link to application").selectOption(APP1);
  await u1.getByRole("button", { name: "Save" }).click();
  await expect(u1).toContainText("waiting for you");

  // The actions reached the documented endpoints, with the corrected outcome and the chosen
  // application carried in the body — never a content field.
  expect(calls.find((c) => c.path === "/api/inbox/events/p1/accept")?.body).toBeUndefined();
  expect(calls.find((c) => c.path === "/api/inbox/events/p2/accept")?.body).toEqual({ outcome: "interviewing" });
  expect(calls.some((c) => c.path === "/api/inbox/events/a1/undo")).toBeTruthy();
  expect(calls.find((c) => c.path === "/api/inbox/events/u1/relink")?.body).toEqual({ application_id: APP1 });

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("an email-update notification is restrained and points to the tracker", async ({ page }, info) => {
  await register(page, info.project.name);
  await page.route("**/api/notifications**", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fulfill({ json: {} });
    await route.fulfill({
      json: {
        items: [
          {
            key: "inbox:e1:proposed",
            kind: "email_update",
            at: "2026-10-31T10:00:00Z",
            application_id: APP1,
            job: "Support Specialist · Northwind Example",
            title: "An email may update an application",
            text: "A recruitment email looks like an update to one of your applications. Confirm or dismiss it on the tracker.",
            needs_action: true,
            read: false,
            link: "/tracker",
          },
        ],
        total: 1,
        unread: 1,
      },
    });
  });

  await page.goto("/notifications");
  const item = page.locator("li", { hasText: "An email may update an application" });
  await expect(item.getByText("Email update", { exact: true })).toBeVisible();
  await expect(item.getByText("Needs you", { exact: true })).toBeVisible();
  // Deliberately generic: no sender, subject or message content in the preview (none is stored).
  await expect(item).toContainText("Confirm or dismiss it on the tracker.");
  await expect(item.getByRole("link", { name: "Open application" })).toHaveAttribute("href", "/tracker");
});
