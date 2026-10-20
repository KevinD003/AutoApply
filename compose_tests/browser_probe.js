// Runs INSIDE the browser-runner container (piped to its node on stdin) as the container's
// user. Reports what a compromised browser process there could see or reach. Test-only.
"use strict";
const fs = require("fs");
const net = require("net");
const http = require("http");
const dns = require("dns");

const status = fs.readFileSync("/proc/self/status", "utf8");
const field = (k) => ((status.match(new RegExp(`^${k}:\\s*(.*)$`, "m")) || [])[1] || "").trim();
const exists = (p) => { try { fs.accessSync(p); return true; } catch { return false; } };
const writable = (p) => { try { fs.writeFileSync(p, "x"); fs.unlinkSync(p); return true; } catch { return false; } };

function tcp(host, port) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port, timeout: 3000 });
    const done = (r) => { s.destroy(); resolve(r); };
    s.on("connect", () => done("open"));
    s.on("timeout", () => done("timeout"));
    s.on("error", (e) => done(e.code || "error"));
  });
}

async function openPorts(host) {
  // Every TCP port of `host`, from here. Reachability, not an HTTP status: a port counts as
  // open only if a TCP connection is accepted.
  const ip = await new Promise((r) => dns.lookup(host, (e, a) => r(e ? null : a)));
  if (!ip) return { error: "unresolvable" };
  const open = [];
  let next = 1;
  async function worker() {
    while (next <= 65535) {
      const port = next++;
      if ((await tcp(ip, port)) === "open") open.push(port);
    }
  }
  await Promise.all(Array.from({ length: 400 }, worker));
  return open.sort((a, b) => a - b);
}

(async () => {
  const targets = [["postgres", 5432], ["redis", 6379], ["backend", 8000], ["frontend", 3000],
    ["receiver", 8799], ["canary", 8798], ["169.254.169.254", 80], ["1.1.1.1", 443],
    ["worker", 8000], ["egress-proxy", 3128]];
  const reach = {};
  for (const [h, p] of targets) reach[`${h}:${p}`] = await tcp(h, p);
  // A name lookup outside the stack would be a side channel (DNS exfiltration) even without
  // any TCP route.
  const external_dns = await new Promise((resolve) =>
    dns.lookup("example.com", (err, addr) => resolve(err ? (err.code || "error") : `resolved ${addr}`)));
  const envKeys = Object.keys(process.env).sort();
  console.log(JSON.stringify({
    uid: process.getuid(), gid: process.getgid(),
    cap_eff: field("CapEff"), cap_prm: field("CapPrm"), cap_bnd: field("CapBnd"),
    no_new_privs: field("NoNewPrivs"), seccomp: field("Seccomp"),
    env_keys: envKeys,
    credential_like_env: envKeys.filter((k) => /DATABASE|REDIS|POSTGRES|CONTROL_TOKEN|ANTHROPIC|AWS|GOOGLE|GMAIL|SECRET|PASSWORD/i.test(k)),
    paths_present: ["/data", "/data/storage", "/app", "/.env", "/var/run/docker.sock", "/run/secrets", "/fixture",
      "/run/egress-control", "/run/egress-control/control.sock"].filter(exists),
    root_writable: writable("/probe-write-test"), etc_writable: writable("/etc/probe-write-test"),
    tmp_writable: writable("/tmp/probe-write-test"),
    reach, external_dns, proxy_open_ports: process.env.SCAN === "0" ? null : await openPorts("egress-proxy"),
  }));
})();
