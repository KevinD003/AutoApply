import { expect, test } from "@playwright/test";

// C17 (D70): a version, or every version, of a document is deleted with its file. Synthetic
// documents only.
const PDF = Buffer.from("%PDF-1.4\n% synthetic e2e document\n");

test("a document version, then the whole document, is deleted", async ({ page }, info) => {
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `documents.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const upload = async (lineage?: string) => {
    const multipart: Record<string, string | { name: string; mimeType: string; buffer: Buffer }> = {
      file: { name: "resume.pdf", mimeType: "application/pdf", buffer: PDF },
      kind: "resume",
    };
    if (lineage) multipart.lineage_id = lineage;
    const r = await page.request.post("/api/documents", { headers: h, multipart });
    expect(r.status()).toBe(201);
    return r.json();
  };
  const v1 = await upload();
  await upload(v1.lineage_id);

  await page.goto("/documents");
  await expect(page.getByText(/resume\.pdf · 0 KB · v2/)).toBeVisible();
  await page.getByRole("button", { name: "History" }).click();
  await page.locator("li", { hasText: /^v1 —/ }).getByRole("button", { name: "delete this version" }).click();
  await expect(page.getByText("Deleted version 1 of “resume.pdf”.")).toBeVisible();
  expect((await page.request.get(`/api/documents/${v1.id}/download`)).status()).toBe(404);

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("Delete this document, every version and its files?")).toBeVisible();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText("Deleted “resume.pdf” and all its versions.")).toBeVisible();
  await expect(page.getByText(/Upload your resume to get started/)).toBeVisible();
});

test("a resume's facts are proposed and wait for approval in the profile", async ({ page }, info) => {
  // L1 (D72): read from a synthetic plain-text resume; nothing is used until approved.
  const reg = await page.request.post("/api/auth/register", {
    data: { email: `resume-facts.${info.project.name}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const text = [
    "Experience",
    "Front Desk Lead at Synthetic Care Clinic",
    "• Handled patient intake",
    "US citizen, no sponsorship needed",
    "Certifications",
    "Phlebotomy Technician, issued by Synthetic Board, expires 2030-05-31",
  ].join("\n");
  const r = await page.request.post("/api/documents", {
    headers: h,
    multipart: { file: { name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from(text) }, kind: "resume" },
  });
  expect(r.status()).toBe(201);

  await page.goto("/documents");
  await page.getByRole("button", { name: "Propose profile facts" }).click();
  await expect(page.getByText(/Proposed from “resume\.txt”: 1 work entry, 0 education entries, 1 licence or certification\./)).toBeVisible();
  await expect(page.getByText(/1 line about legal status or a personal topic not read\./)).toBeVisible();

  await page.goto("/profile");
  const work = page.locator("li", { hasText: "Front Desk Lead — Synthetic Care Clinic" });
  await expect(work.getByText("Proposed from your resume")).toBeVisible();
  const cert = page.locator("li", { hasText: "Phlebotomy Technician — Synthetic Board" });
  await expect(cert.getByText("Valid until 2030-05-31")).toBeVisible();
  await work.getByRole("button", { name: "Approve" }).click();
  await expect(work.getByText("Proposed from your resume")).toHaveCount(0);
  await expect(cert.getByText("Proposed from your resume")).toBeVisible();
});
