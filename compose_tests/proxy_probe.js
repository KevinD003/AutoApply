// Runs INSIDE the browser-runner container (piped to its node on stdin). With a real session's
// proxy credentials (SESSION_ID / SESSION_TOKEN, allow-list = the receiver), asks the egress
// proxy to reach places other than the allowed destination, including the proxy itself.
// Prints the proxy's status line for each request. Test-only.
"use strict";
const net = require("net");

const auth = Buffer.from(`${process.env.SESSION_ID}:${process.env.SESSION_TOKEN}`).toString("base64");

function ask(request) {
  return new Promise((resolve) => {
    const s = net.connect({ host: "egress-proxy", port: 3128, timeout: 5000 });
    let buf = "";
    s.on("connect", () => s.write(request));
    s.on("data", (d) => { buf += d; if (buf.includes("\r\n")) { s.destroy(); resolve(buf.split("\r\n")[0]); } });
    s.on("timeout", () => { s.destroy(); resolve("timeout"); });
    s.on("error", (e) => resolve(e.code || "error"));
    s.on("close", () => resolve(buf.split("\r\n")[0] || "closed"));
  });
}

const connect = (hp) => `CONNECT ${hp} HTTP/1.1\r\nHost: ${hp}\r\nProxy-Authorization: Basic ${auth}\r\n\r\n`;
const get = (url, host) => `GET ${url} HTTP/1.1\r\nHost: ${host}\r\nProxy-Authorization: Basic ${auth}\r\nConnection: close\r\n\r\n`;

(async () => {
  const out = {
    // positive control: the session's own destination works with these credentials
    "CONNECT receiver:8799": await ask(connect("receiver:8799")),
    "CONNECT egress-proxy:3129": await ask(connect("egress-proxy:3129")),
    "CONNECT egress-proxy:3128": await ask(connect("egress-proxy:3128")),
    "CONNECT 127.0.0.1:3128": await ask(connect("127.0.0.1:3128")),
    "CONNECT localhost:3129": await ask(connect("localhost:3129")),
    "GET http://egress-proxy:3129/health": await ask(get("http://egress-proxy:3129/health", "egress-proxy:3129")),
    "GET http://127.0.0.1:3128/": await ask(get("http://127.0.0.1:3128/", "127.0.0.1:3128")),
    "CONNECT worker:8000": await ask(connect("worker:8000")),
  };
  console.log(JSON.stringify(out));
})();
