import { expect, Route, test } from "@playwright/test";

// L2/L3 (D73): a tailored resume shows the facts it uses and what changed from its base, and is
// accepted or rejected. No drafting provider exists, so the list is a synthetic one served in
// place of the server's (the endpoints are tested in backend/tests/test_generated_documents.py);
// without a provider the page says so.
test("a tailored resume is read with its changes, then accepted", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `generated.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const job = await (await page.request.post("/api/jobs", { headers: h, data: { title: "Clinic Assistant", employer: "Example Health (fictional)" } })).json();
  expect((await page.request.post(`/api/jobs/${job.job.id}/form`, { headers: h, data: { fixture: "basic" } })).ok()).toBeTruthy();
  const app = await (await page.request.post("/api/applications", { headers: h, data: { job_id: job.job.id } })).json();

  await page.goto(`/applications/${app.id}`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Tailored resume and cover letter" }) });
  await expect(card.getByText("AI drafting is not configured on this server.")).toBeVisible();

  let accepted = false;
  const doc = () => ({
    id: "33333333-3333-4333-8333-333333333333",
    kind: "resume",
    label: "Resume for Clinic Assistant",
    created_at: "2026-10-29T01:00:00Z",
    accepted,
    usable: accepted,
    stale: false,
    text: "Front Desk\nHandled patient intake for 3 doctors.",
    cited: [{ kind: "employment", text: "Front Desk at Synthetic Care: Handled patient intake for 3 doctors." }],
    base_label: "base.txt",
    diff: [
      { op: " ", line: "Front Desk" },
      { op: "-", line: "Answered phones." },
      { op: "+", line: "Handled patient intake for 3 doctors." },
    ],
  });
  await page.route(`**/api/applications/${app.id}/generated-documents`, (route: Route) => route.fulfill({ json: [doc()] }));
  await page.route(`**/api/applications/${app.id}/generated-documents/*/accept`, (route: Route) => {
    accepted = true;
    return route.fulfill({ json: doc() });
  });
  await page.reload();
  await expect(card.getByText("Waiting for you to read it")).toBeVisible();
  await expect(card.getByText("Front Desk at Synthetic Care: Handled patient intake for 3 doctors.")).toBeVisible();
  const changes = card.getByLabel("Changes from base.txt");
  await expect(changes.getByText("Answered phones.")).toHaveClass(/line-through/);
  await expect(changes.getByText("Handled patient intake for 3 doctors.")).toBeVisible();
  await card.getByRole("button", { name: "Accept" }).click();
  await expect(card.getByText("Accepted. Choose it above to send it with this application.")).toBeVisible();
  await expect(card.getByText("Accepted: choose it above")).toBeVisible();
  await expect(card.getByRole("button", { name: "Reject" })).toHaveCount(0);
});
