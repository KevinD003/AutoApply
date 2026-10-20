// NoEfforts browser runner: launches one Chromium per attempt for the orchestration worker.
//
// Runs inside the browser container as an unprivileged user, with the Playwright driver that
// ships with the pinned Python package (same version as the worker's client). Every launch
// option that matters for isolation is fixed HERE, not chosen by the caller:
//   * Chromium's own sandbox is on (never --no-sandbox); a self-check at startup verifies that
//     renderers really run under seccomp-bpf, and the runner refuses all sessions if not;
//   * all traffic goes to the configured egress proxy, with per-session credentials;
//   * each session has a hard time limit and the number of sessions is capped.
// The only secret here is the runner token, which authorises use of this runner and nothing
// else (no database, broker, mailbox or cloud credentials exist in this container).

"use strict";
const http = require("http");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");

const DRIVER = process.env.DRIVER_PACKAGE;
const { chromium } = require(DRIVER);

const PORT = Number(process.env.RUNNER_PORT || 9330);
const TOKEN = process.env.RUNNER_TOKEN || "";
const PROXY = process.env.EGRESS_PROXY || ""; // e.g. http://egress-proxy:3128
const PUBLIC_HOST = process.env.RUNNER_PUBLIC_HOST || os.hostname();
const MAX_SESSIONS = Number(process.env.MAX_SESSIONS || 2);
const MAX_SESSION_SECONDS = Number(process.env.MAX_SESSION_SECONDS || 600);
const HOSTNAME_RE = /^[A-Za-z0-9.-]{1,253}$/;

const sessions = new Map(); // id -> {server, timer, started}
let sandbox = { ok: false, report: "self-check not run yet" };

function log(msg, extra) {
  // Never log URLs, page content or credentials: ids, counts and reasons only.
  console.log(JSON.stringify({ t: new Date().toISOString(), msg, ...(extra || {}) }));
}

function launchOptions({ proxyUser, proxyPass, allowedHost }) {
  const args = ["--disable-background-networking", "--no-first-run", "--disable-sync"];
  if (allowedHost && HOSTNAME_RE.test(allowedHost)) {
    // Defence in depth: resolve nothing but the destination and the proxy itself (the
    // proxy decides anyway; the browser has no other route).
    const proxyHost = PROXY ? new URL(PROXY).hostname : "";
    const keep = [allowedHost, proxyHost].filter((h) => h && HOSTNAME_RE.test(h));
    args.push(`--host-resolver-rules=MAP * ~NOTFOUND , ${keep.map((h) => `EXCLUDE ${h}`).join(" , ")}`);
  }
  const opts = {
    headless: true,
    chromiumSandbox: true,
    args,
    env: { PATH: "/usr/bin:/bin", HOME: os.tmpdir(), TMPDIR: os.tmpdir() },
    timeout: 30000,
  };
  if (PROXY) {
    opts.proxy = { server: PROXY, bypass: "<-loopback>" };
    if (proxyUser) Object.assign(opts.proxy, { username: proxyUser, password: proxyPass });
  }
  return opts;
}

function readProc(pid, file) {
  try {
    return fs.readFileSync(`/proc/${pid}/${file}`, "utf8");
  } catch {
    return null;
  }
}

async function selfCheck() {
  // Launch exactly as sessions do, open a page, then inspect every browser process we own.
  const uid = process.getuid();
  if (uid === 0) return { ok: false, report: "runner must not run as root" };
  let browser;
  try {
    browser = await chromium.launch(launchOptions({}));
    const page = await browser.newPage();
    await page.setContent("<p>self-check</p>");
    const procs = [];
    for (const pid of fs.readdirSync("/proc").filter((p) => /^\d+$/.test(p))) {
      const status = readProc(pid, "status");
      const cmd = (readProc(pid, "cmdline") || "").split("\0").join(" ");
      if (!status || !/chrom|headless_shell/.test(cmd)) continue;
      const field = (k) => ((status.match(new RegExp(`^${k}:\\s*(.*)$`, "m")) || [])[1] || "").trim();
      procs.push({
        pid: Number(pid),
        type: (cmd.match(/--type=([a-z-]+)/) || [])[1] || "browser",
        uid: Number(field("Uid").split(/\s+/)[0]),
        seccomp: field("Seccomp"),
        no_new_privs: field("NoNewPrivs"),
        no_sandbox_flag: cmd.includes("--no-sandbox"),
      });
    }
    await browser.close();
    browser = null;
    const renderers = procs.filter((p) => p.type === "renderer");
    const problems = [];
    if (!procs.length) problems.push("no browser processes found");
    if (procs.some((p) => p.no_sandbox_flag)) problems.push("a process runs with --no-sandbox");
    if (procs.some((p) => p.uid === 0)) problems.push("a process runs as root");
    if (!renderers.length) problems.push("no renderer process found");
    if (renderers.some((p) => p.seccomp !== "2")) problems.push("a renderer is not under seccomp-bpf");
    return {
      ok: problems.length === 0,
      report: problems.length ? problems.join("; ") : "sandboxed",
      runner_uid: uid,
      processes: procs.map(({ pid, ...rest }) => rest),
    };
  } catch (e) {
    return { ok: false, report: `browser did not start with its sandbox: ${String(e.message || e).split("\n")[0]}` };
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

function authorised(req) {
  const got = Buffer.from(String(req.headers["x-runner-token"] || ""));
  const want = Buffer.from(TOKEN);
  return TOKEN.length >= 16 && got.length === want.length && crypto.timingSafeEqual(got, want);
}

function send(res, code, body) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const c of req) {
    size += c.length;
    if (size > 16384) throw new Error("body too large");
    chunks.push(c);
  }
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

async function closeSession(id, reason) {
  const s = sessions.get(id);
  if (!s) return false;
  sessions.delete(id);
  clearTimeout(s.timer);
  await s.server.close().catch(() => {});
  log("session closed", { id, reason, seconds: Math.round((Date.now() - s.started) / 1000) });
  return true;
}

async function createSession(body) {
  const id = crypto.randomBytes(8).toString("hex");
  const opts = launchOptions({
    proxyUser: String(body.proxy_username || ""),
    proxyPass: String(body.proxy_password || ""),
    allowedHost: String(body.allowed_host || ""),
  });
  const server = await chromium.launchServer({
    ...opts,
    host: "0.0.0.0",
    port: 0,
    wsPath: "/" + crypto.randomBytes(16).toString("hex"),
  });
  const timer = setTimeout(() => closeSession(id, "time limit"), MAX_SESSION_SECONDS * 1000);
  sessions.set(id, { server, timer, started: Date.now() });
  server.process().on("exit", () => closeSession(id, "browser exited"));
  const ws = new URL(server.wsEndpoint());
  ws.hostname = PUBLIC_HOST;
  log("session started", { id, sessions: sessions.size });
  return { id, ws_endpoint: ws.toString(), max_seconds: MAX_SESSION_SECONDS };
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://runner");
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, sandbox.ok ? 200 : 503, { sandbox_ok: sandbox.ok, sandbox: sandbox.report, sessions: sessions.size });
    }
    if (!authorised(req)) return send(res, 401, { error: "unauthorised" });
    if (req.method === "GET" && url.pathname === "/selfcheck") {
      return send(res, 200, sandbox);
    }
    if (req.method === "POST" && url.pathname === "/sessions") {
      if (!sandbox.ok) return send(res, 503, { error: `sandbox unavailable: ${sandbox.report}` });
      if (!PROXY) return send(res, 503, { error: "no egress proxy configured" });
      if (sessions.size >= MAX_SESSIONS) return send(res, 429, { error: "too many sessions" });
      return send(res, 201, await createSession(await readJson(req)));
    }
    const m = url.pathname.match(/^\/sessions\/([0-9a-f]{16})$/);
    if (req.method === "DELETE" && m) {
      return send(res, (await closeSession(m[1], "closed by worker")) ? 200 : 404, {});
    }
    return send(res, 404, { error: "not found" });
  } catch (e) {
    log("request failed", { error: String(e.message || e).split("\n")[0] });
    return send(res, 500, { error: "internal error" });
  }
});

(async () => {
  sandbox = await selfCheck();
  log("sandbox self-check", { ok: sandbox.ok, report: sandbox.report });
  server.listen(PORT, "0.0.0.0", () => log("listening", { port: PORT }));
})();

for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, async () => {
    for (const id of [...sessions.keys()]) await closeSession(id, "shutdown");
    process.exit(0);
  });
}
