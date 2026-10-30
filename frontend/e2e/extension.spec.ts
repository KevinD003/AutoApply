import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { APIRequestContext, BrowserContext, chromium, expect, Page, request as playwrightRequest, test } from "@playwright/test";

import { RECEIVER } from "../playwright.config";

// D90: the capture-only browser extension (extension/) loaded into a real Chromium. It sends a
// tab's address and title to your own NoEfforts with an `import:jobs` token, and nothing else:
// it never reads, fills or submits a page. Synthetic accounts and fictional postings only.
const EXTENSION = path.resolve(__dirname, "../../extension");
type Saved = { ok: boolean; message: string; jobUrl?: string };
// The extension APIs these tests call from the extension's own pages (evaluated in the browser).
declare const chrome: {
  tabs: { query(q: object): Promise<{ id?: number; url?: string }[]> };
  runtime: { getURL(p: string): string; sendMessage(m: object): Promise<Saved> };
};
const BASE = "http://127.0.0.1:3100";

// Desktop project only (playwright.config.ts): an extension is a desktop browser feature.
test.describe.configure({ mode: "serial" });

let context: BrowserContext;
let profile: string;
let extensionId: string;
let api: APIRequestContext; // the token's owner, signed in outside the extension's browser

async function account(r: APIRequestContext, tag: string) {
  const reg = await r.post("/api/auth/register", {
    data: { email: `extension.${tag}.${Date.now()}@example.com`, password: "synthetic-password-1" },
  });
  expect(reg.status()).toBe(201);
  return { "X-CSRF-Token": (await reg.json()).csrf_token as string };
}

async function token(scopes: string[]) {
  const h = await account(api, `owner-${scopes.join("-").replace(/[^a-z-]/g, "")}`);
  const r = await api.post("/api/account/tokens", { headers: h, data: { label: "extension e2e", scopes, expires_in_days: 7 } });
  expect(r.status()).toBe(201);
  return (await r.json()).token as string;
}

async function extensionPage(file: string): Promise<Page> {
  const page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/${file}`);
  return page;
}

/** Ask the background worker to save a tab, as the popup does after you click its button. */
async function save(from: Page, url: string): Promise<Saved> {
  return from.evaluate(async (u) => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((t) => t.url === u);
    if (!tab) return { ok: false, message: "no such tab visible to the extension" };
    return chrome.runtime.sendMessage({ type: "save", tabId: tab.id });
  }, url);
}

test.beforeAll(async () => {
  profile = mkdtempSync(path.join(tmpdir(), "noefforts-ext-"));
  context = await chromium.launchPersistentContext(profile, {
    // The headless shell cannot load extensions: the full Chromium (new headless) can.
    ...(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : { channel: "chromium" }),
    headless: true,
    baseURL: BASE,
    serviceWorkers: "allow",
    args: [`--disable-extensions-except=${EXTENSION}`, `--load-extension=${EXTENSION}`],
  });
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent("serviceworker");
  extensionId = new URL(worker.url()).host;
  api = await playwrightRequest.newContext({ baseURL: BASE });
});

test.afterAll(async () => {
  await context?.close();
  await api?.dispose();
  if (profile) rmSync(profile, { recursive: true, force: true });
});

test("the extension asks for the least: no page access, no content scripts, NoEfforts on this machine only", async () => {
  const manifest = JSON.parse(readFileSync(path.join(EXTENSION, "manifest.json"), "utf8"));
  expect(manifest.manifest_version).toBe(3);
  expect([...manifest.permissions].sort()).toEqual(["activeTab", "storage"]);
  expect([...manifest.host_permissions].sort()).toEqual(["http://127.0.0.1/*", "http://localhost/*"]);
  for (const key of ["content_scripts", "optional_permissions", "optional_host_permissions", "web_accessible_resources", "externally_connectable"]) {
    expect(manifest[key]).toBeUndefined();
  }
  // Nothing in it reads a page: no scripting, no DOM of a tab, no cookies.
  for (const file of ["lib.js", "background.js", "popup.js", "options.js"]) {
    const code = readFileSync(path.join(EXTENSION, file), "utf8");
    expect(code).not.toMatch(/chrome\.(scripting|cookies|webRequest|history|downloads)|executeScript|document\.cookie/);
  }
});

test("what is sent: the address (no fragment) and title, with the token, never your browser's cookies", async () => {
  const page = await extensionPage("options.html");
  const out = await page.evaluate(async () => {
    const lib = await import(chrome.runtime.getURL("lib.js"));
    const seen: { url: string; init: RequestInit }[] = [];
    const fake = async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ job: { id: "j-1" }, duplicate: false }), { status: 201 });
    };
    const saved = await lib.saveJob(
      { base: "http://127.0.0.1:3100", token: "ne_abcdefgh_secret" },
      { url: "https://jobs.example.com/p/1?ref=x#apply", title: "  Nurse  ", favIconUrl: "https://x/y.ico", id: 7 },
      fake,
    );
    return {
      saved,
      seen: seen.map((s) => ({ url: s.url, ...s.init, body: JSON.parse(String(s.init.body)) })),
      bases: ["http://127.0.0.1:3000", "http://localhost:3100/", "https://127.0.0.1:3000", "http://noefforts.example.com",
        "http://127.0.0.1:3000/api", "http://u:p@127.0.0.1:3000", "http://127.0.0.1:3000/?x=1", "file:///etc", "nonsense"]
        .map((b) => { const r = lib.checkBase(b); return r instanceof Error ? "refused" : r; }),
      tabs: [undefined, { url: "chrome://settings" }, { url: "file:///tmp/a.html" }, { url: "about:blank" }, { url: "javascript:alert(1)" }, { url: "http://x.example/" }]
        .map((t) => { const r = lib.checkTab(t); return r instanceof Error ? "refused" : r; }),
    };
  });
  expect(out.saved).toEqual({ ok: true, message: "Saved to NoEfforts.", jobUrl: "http://127.0.0.1:3100/jobs/j-1" });
  expect(out.seen).toHaveLength(1);
  const sent = out.seen[0];
  expect(sent.url).toBe("http://127.0.0.1:3100/api/jobs");
  expect(sent.method).toBe("POST");
  expect(sent.credentials).toBe("omit");
  expect(sent.redirect).toBe("error");
  expect(sent.headers).toMatchObject({ Authorization: "Bearer ne_abcdefgh_secret" });
  expect(sent.body).toEqual({ url: "https://jobs.example.com/p/1?ref=x", title: "Nurse" }); // nothing else
  expect(out.bases).toEqual(["http://127.0.0.1:3000", "http://localhost:3100", "refused", "refused", "refused", "refused", "refused", "refused", "refused"]);
  expect(out.tabs).toEqual(["refused", "refused", "refused", "refused", "refused", { url: "http://x.example/" }]);
  await page.close();
});

test("options keep only a token NoEfforts accepts with the import:jobs scope alone, and never show it again", async () => {
  const page = await extensionPage("options.html");
  await expect(page.getByText("No token saved yet.")).toBeVisible();
  await page.getByLabel("NoEfforts address").fill("http://noefforts.example.com");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("only to NoEfforts on this machine");

  await page.getByLabel("NoEfforts address").fill(BASE);
  await page.getByLabel("Token").fill(await token(["read", "import:jobs"]));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Not saved. Use a token with only the import:jobs scope");
  await page.getByLabel("Token").fill("ne_abcdefgh_" + "x".repeat(43));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("did not accept that token");
  await expect(page.getByText("No token saved yet.")).toBeVisible();

  const good = await token(["import:jobs"]);
  await page.getByLabel("Token").fill(good);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Saved.");
  await expect(page.getByText("A token is saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Token")).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(good);

  // A token checked against one address is never sent to another: changing it drops the token.
  await page.getByLabel("NoEfforts address").fill("http://localhost:3100");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("the token was removed");
  await expect(page.getByText("No token saved yet.")).toBeVisible();
  await page.close();
});

test("a fictional posting's tab is saved to the token owner's NoEfforts once, through the background worker", async () => {
  // A second account signed in inside the extension's browser: its session is never used.
  const bystander = await account(context.request, "bystander");
  expect(bystander["X-CSRF-Token"]).toBeTruthy();

  const owner = await account(api, "saver");
  const issued = await api.post("/api/account/tokens", { headers: owner, data: { label: "extension", scopes: ["import:jobs"], expires_in_days: 7 } });
  const secret = (await issued.json()).token as string;
  const options = await extensionPage("options.html");
  await options.getByLabel("NoEfforts address").fill(BASE);
  await options.getByLabel("Token").fill(secret);
  await options.getByRole("button", { name: "Save", exact: true }).click();
  await expect(options.getByRole("status")).toHaveText("Saved.");

  const req = `R-${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
  const posting = `${RECEIVER}/workday/examplehealth/${req}`;
  const tab = await context.newPage();
  await tab.goto(posting);
  const title = await tab.title();

  const first = await save(options, posting);
  expect(first).toMatchObject({ ok: true, message: "Saved to NoEfforts." });
  const again = await save(options, posting);
  expect(again).toMatchObject({ ok: true, message: "Already in NoEfforts." });

  const mine = await (await api.get("/api/jobs")).json();
  const saved = (mine.items as { url: string; title: string | null; id: string }[]).filter((j) => j.url === posting);
  expect(saved).toHaveLength(1);
  expect(saved[0].title).toBe(title || null);
  expect(first.jobUrl).toBe(`${BASE}/jobs/${saved[0].id}`);
  const theirs = await (await context.request.get("/api/jobs")).json();
  expect((theirs.items as { url: string }[]).some((j) => j.url === posting)).toBe(false);
  await tab.close();
  await options.close();
});

test("a tab you did not click the button on is never read, and the popup refuses a page that is not a web page", async () => {
  // Without a click on its button (activeTab), the extension cannot see another site's tab.
  await context.route("https://jobs.example.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<title>Fictional posting</title><h1>Fictional posting</h1>" }),
  );
  const elsewhere = await context.newPage();
  await elsewhere.goto("https://jobs.example.com/careers/123");
  const options = await extensionPage("options.html");
  const visible = await options.evaluate(async () =>
    (await chrome.tabs.query({})).map((t) => t.url ?? null).filter((u) => u?.includes("example.com")),
  );
  expect(visible).toEqual([]);

  const popup = await extensionPage("popup.html"); // opened as a tab, it is the active tab itself
  await popup.getByRole("button", { name: "Save this job" }).click();
  await expect(popup.getByRole("status")).toHaveText("This tab is not a web page, so there is no job to save.");
  await popup.close();
  await options.close();
  await elsewhere.close();
});
