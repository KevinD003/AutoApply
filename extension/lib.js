// Shared by the popup, the options page and the background worker (D90). The extension sends a
// job page's address and title to your own NoEfforts, nothing else: no page content, no form,
// no cookie. It talks only to NoEfforts on this machine (host_permissions), with a token you
// created in Account -> API tokens with the `import:jobs` scope, which can add jobs and nothing
// more (docs/api-tokens.md).

export const DEFAULT_BASE = "http://127.0.0.1:3000";
const LOOPBACK = new Set(["127.0.0.1", "localhost"]);
const MAX_TITLE = 300;

/** The NoEfforts address to use, or an Error: plain http to this machine only. */
export function checkBase(value) {
  let u;
  try {
    u = new URL(String(value || "").trim());
  } catch {
    return new Error("The NoEfforts address must be a web address, like http://127.0.0.1:3000.");
  }
  if (u.protocol !== "http:" || !LOOPBACK.has(u.hostname)) {
    return new Error("This extension talks only to NoEfforts on this machine (http://127.0.0.1 or http://localhost).");
  }
  if (u.username || u.password || u.search || u.hash || (u.pathname && u.pathname !== "/")) {
    return new Error("The NoEfforts address must be just the address, with no path, query or login.");
  }
  return u.origin;
}

/** What is sent for a tab, or an Error: an http(s) page's address and title, nothing else. */
export function checkTab(tab) {
  let u;
  try {
    u = new URL(tab && tab.url ? tab.url : "");
  } catch {
    return new Error("This tab is not a web page, so there is no job to save.");
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return new Error("This tab is not a web page, so there is no job to save.");
  }
  u.hash = "";
  const title = String((tab && tab.title) || "").trim().slice(0, MAX_TITLE);
  return title ? { url: u.href, title } : { url: u.href };
}

/** Whether NoEfforts at `base` accepts `token` with the `import:jobs` scope and nothing more.
 * Resolves to null when it does, else to the reason to show; never throws. */
export async function checkToken(base, token, fetchFn = fetch) {
  let r;
  try {
    r = await fetchFn(`${base}/api/token`, {
      credentials: "omit",
      redirect: "error",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
  } catch {
    return "NoEfforts could not be reached at that address. Is it running?";
  }
  if (r.status === 401) return "NoEfforts did not accept that token (unknown, expired or revoked).";
  if (!r.ok) return `NoEfforts did not check the token: HTTP ${r.status}`;
  let scopes;
  try {
    scopes = (await r.json()).scopes;
  } catch {
    scopes = undefined;
  }
  if (!Array.isArray(scopes) || scopes.length !== 1 || scopes[0] !== "import:jobs") {
    return "Use a token with only the import:jobs scope: this extension needs nothing more, so it keeps nothing more.";
  }
  return null;
}

/** Add the tab's job to NoEfforts. Resolves to {ok, message, jobUrl?}; never throws. */
export async function saveJob(settings, tab, fetchFn = fetch) {
  const base = checkBase(settings && settings.base);
  if (base instanceof Error) return { ok: false, message: base.message };
  const token = String((settings && settings.token) || "").trim();
  if (!token) return { ok: false, message: "Add your NoEfforts token in the extension's options first." };
  const job = checkTab(tab);
  if (job instanceof Error) return { ok: false, message: job.message };
  let r;
  try {
    r = await fetchFn(`${base}/api/jobs`, {
      method: "POST",
      credentials: "omit", // the token alone: never your browser's NoEfforts session
      redirect: "error",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(job),
    });
  } catch {
    return { ok: false, message: "NoEfforts could not be reached at that address. Is it running?" };
  }
  let data = {};
  try {
    data = await r.json();
  } catch {
    data = {};
  }
  if (!r.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `HTTP ${r.status}`;
    return { ok: false, message: `NoEfforts did not save it: ${detail}` };
  }
  const id = data && data.job && data.job.id;
  const again = data && data.duplicate === true;
  return {
    ok: true,
    message: again ? "Already in NoEfforts." : "Saved to NoEfforts.",
    jobUrl: id ? `${base}/jobs/${encodeURIComponent(id)}` : undefined,
  };
}
