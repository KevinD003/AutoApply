import { readFileSync } from "node:fs";
import { inflateRawSync } from "node:zlib";

import { expect, test } from "@playwright/test";

// Priority B (D77, docs/account-deletion.md): the full export through the page, then deletion,
// after which the account cannot sign in and its session is gone. Synthetic account only.

// The entries of a ZIP written by Python's zipfile (sizes in each local header).
function unzip(buf: Buffer): Record<string, Buffer> {
  const out: Record<string, Buffer> = {};
  let i = 0;
  while (buf.readUInt32LE(i) === 0x04034b50) {
    const method = buf.readUInt16LE(i + 8);
    const size = buf.readUInt32LE(i + 18);
    const nameLen = buf.readUInt16LE(i + 26);
    const extraLen = buf.readUInt16LE(i + 28);
    const name = buf.subarray(i + 30, i + 30 + nameLen).toString("utf8");
    const start = i + 30 + nameLen + extraLen;
    const data = buf.subarray(start, start + size);
    out[name] = method === 8 ? inflateRawSync(data) : Buffer.from(data);
    i = start + size;
  }
  return out;
}

test("the account's data is exported, then the account is deleted for good", async ({ page }, info) => {
  const email = `account.${info.project.name}.${Date.now()}@example.com`;
  const password = "synthetic-password-1";
  const reg = await page.request.post("/api/auth/register", { data: { email, password } });
  expect(reg.status()).toBe(201);
  const h = { "X-CSRF-Token": (await reg.json()).csrf_token as string };
  const title = `Synthetic Role ${info.project.name}`;
  const job = await page.request.post("/api/jobs", {
    headers: h,
    data: { url: "https://careers.example.com/synthetic/1", title, employer: "Fictional Employer" },
  });
  expect(job.status()).toBe(201);
  const notes = Buffer.from("Synthetic notes for the export test.\n");
  const doc = await page.request.post("/api/documents", {
    headers: h,
    multipart: { file: { name: "notes.txt", mimeType: "text/plain", buffer: notes }, kind: "other" },
  });
  expect(doc.status()).toBe(201);

  await page.goto("/account");
  const deleted = page.getByRole("list", { name: "What will be deleted" });
  await expect(deleted).toContainText("1 jobs");
  await expect(deleted).toContainText("1 documents (and their files)");
  await expect(page.getByText("Nothing about your account is kept in NoEfforts afterwards.")).toBeVisible();
  await expect(page.getByRole("list", { name: "What deletion cannot reach" })).toContainText("Backups made before");

  // The export: every record, and the document's file byte for byte.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download all my data" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^noefforts-export-\d{8}\.zip$/);
  const files = unzip(readFileSync((await download.path()) as string));
  const data = JSON.parse(files["noefforts-export.json"].toString("utf8"));
  expect(data.tables.users[0].email).toBe(email);
  expect(data.tables.users[0].password_hash).toBeUndefined();
  expect(data.tables.jobs.map((j: { title: string }) => j.title)).toEqual([title]);
  const [d] = data.tables.documents;
  expect(files[d.file].equals(notes)).toBe(true);
  expect(files["README.txt"].toString("utf8")).toContain("users.password_hash");

  // Deletion: the phrase first, then the password.
  const remove = page.getByRole("button", { name: "Delete my account" });
  await page.getByLabel("Your password").fill("wrong-password-9");
  await expect(remove).toBeDisabled();
  await page.getByLabel(/Type “delete my account” to confirm/).fill("delete my account");
  await remove.click();
  await expect(page.getByRole("alert").filter({ hasText: "That is not your password" })).toBeVisible();
  expect((await page.request.get("/api/auth/me")).status()).toBe(200);
  await page.getByLabel("Your password").fill(password);
  await remove.click();
  await expect(page).toHaveURL(/\/login\?deleted=1$/);
  await expect(page.getByText("Your account and everything in it were deleted.")).toBeVisible();

  // Access has ended, and the old password signs nobody in.
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" })).toBeVisible();
});
