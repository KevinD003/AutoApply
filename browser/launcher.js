// NoEfforts browser runner: launches one Chromium per attempt for the orchestration worker.
//
// Runs inside the browser container as an unprivileged user, with the Playwright driver that
// ships with the pinned Python package (same version as the worker's client). Every launch
// option that matters for isolation is fixed HERE, not chosen by the caller:
//   * Chromium's own sandbox is on (never --no-sandbox); a self-check at startup verifies that
//     renderers really run under seccomp-bpf, and the runner refuses all sessions if not;
//   * all traffic goes to the configured egress proxy, with per-session credentials;
//   * each session has a hard time limit and the number of sessions is capped (one by default:
//     sessions in one container share a user, so concurrent tenants are not isolated);
//   * the browser's own protocol server listens on loopback only. The worker reaches it through
//     this service: one authenticated connection per session, and when that connection ends
//     the browser is closed, so a lost or stale worker leaves no browser behind to drive.
// The only secret here is the runner token, which authorises use of this runner and nothing
// else (no database, broker, mailbox or cloud credentials exist in this container).

"use strict";
const http = require("http");
const net = require("net");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");

const DRIVER = process.env.DRIVER_PACKAGE;
const { chromium } = require(DRIVER);

const PORT = Number(process.env.RUNNER_PORT || 9330);
const TOKEN = process.env.RUNNER_TOKEN || "";
const PROXY = process.env.EGRESS_PROXY || ""; // e.g. http://egress-proxy:3128
const PUBLIC_HOST = process.env.RUNNER_PUBLIC_HOST || os.hostname();
const MAX_SESSIONS = Number(process.env.MAX_SESSIONS || 1);
const CONNECT_SECONDS = Number(process.env.CONNECT_SECONDS || 30);
const DRIVER_VERSION = require(`${DRIVER}/package.json`).version;
const MAX_SESSION_SECONDS = Number(process.env.MAX_SESSION_SECONDS || 600);
const HOSTNAME_RE = /^[A-Za-z0-9.-]{1,253}$/;

const sessions = new Map(); // id -> {server, timer, started, secret, connected, sockets}
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
    const ppid = (pid) => Number(((readProc(pid, "status") || "").match(/^PPid:\s*(\d+)$/m) || [])[1] || 0);
    const ours = (pid) => {
      // Only this runner's own descendants (on a host without a PID namespace, other users'
      // browsers are visible too and say nothing about ours).
      for (let p = Number(pid), n = 0; p > 1 && n < 64; p = ppid(p), n++) if (p === process.pid) return true;
      return false;
    };
    for (const pid of fs.readdirSync("/proc").filter((p) => /^\d+$/.test(p))) {
      const status = readProc(pid, "status");
      const cmd = (readProc(pid, "cmdline") || "").split("\0").join(" ");
      if (!status || !/chrom|headless_shell/.test(cmd) || !ours(pid)) continue;
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
  clearTimeout(s.connectTimer);
  for (const sock of s.sockets) sock.destroy();
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
    host: "127.0.0.1", // reachable only through the authenticated relay below
    port: 0,
    wsPath: "/" + crypto.randomBytes(16).toString("hex"),
  });
  const secret = crypto.randomBytes(24).toString("hex");
  const s = { server, secret, started: Date.now(), connected: false, sockets: new Set() };
  s.timer = setTimeout(() => closeSession(id, "time limit"), MAX_SESSION_SECONDS * 1000);
  s.connectTimer = setTimeout(() => s.connected || closeSession(id, "never connected"), CONNECT_SECONDS * 1000);
  sessions.set(id, s);
  server.process().on("exit", () => closeSession(id, "browser exited"));
  log("session started", { id, sessions: sessions.size });
  return {
    id,
    ws_endpoint: `ws://${PUBLIC_HOST}:${PORT}/sessions/${id}/ws/${secret}`,
    max_seconds: MAX_SESSION_SECONDS,
  };
}

function secretMatches(got, want) {
  const a = Buffer.from(String(got));
  const b = Buffer.from(want);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function refuseUpgrade(socket, code, text) {
  socket.end(`HTTP/1.1 ${code} ${text}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
}

function relay(req, socket, head) {
  // One connection per session, authenticated by the runner token AND the session's secret.
  const m = new URL(req.url, "http://runner").pathname.match(/^\/sessions\/([0-9a-f]{16})\/ws\/([0-9a-f]{48})$/);
  const s = m && sessions.get(m[1]);
  if (!m || !s || !authorised(req) || !secretMatches(m[2], s.secret)) return refuseUpgrade(socket, 401, "Unauthorized");
  if (s.connected) return refuseUpgrade(socket, 409, "Conflict"); // single use: no second controller
  s.connected = true;
  clearTimeout(s.connectTimer);
  const id = m[1];
  const inner = new URL(s.server.wsEndpoint());
  const upstream = net.connect(Number(inner.port), "127.0.0.1");
  s.sockets.add(socket).add(upstream);
  socket.setKeepAlive(true, 10000);
  socket.setNoDelay(true);
  const lines = [`GET ${inner.pathname} HTTP/1.1`, `Host: 127.0.0.1:${inner.port}`];
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const k = req.rawHeaders[i].toLowerCase();
    if (k === "host" || k === "x-runner-token") continue;
    lines.push(`${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}`);
  }
  upstream.on("connect", () => {
    upstream.write(lines.join("\r\n") + "\r\n\r\n");
    if (head && head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  // The controller is gone (or the browser is): end the browser too, so nothing keeps a page
  // that a later or stale worker could drive.
  const end = (why) => closeSession(id, why);
  socket.on("close", () => end("controller disconnected"));
  upstream.on("close", () => end("browser connection closed"));
  socket.on("error", () => {});
  upstream.on("error", () => {});
  log("controller connected", { id });
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://runner");
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, sandbox.ok ? 200 : 503, {
        sandbox_ok: sandbox.ok, sandbox: sandbox.report, sessions: sessions.size,
        max_sessions: MAX_SESSIONS, driver_version: DRIVER_VERSION,
      });
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

server.on("upgrade", (req, socket, head) => {
  try {
    relay(req, socket, head);
  } catch (e) {
    log("upgrade failed", { error: String(e.message || e).split("\n")[0] });
    socket.destroy();
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
