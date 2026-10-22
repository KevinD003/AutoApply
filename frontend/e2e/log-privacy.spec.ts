import { expect, test } from "@playwright/test";

import nextConfig from "../next.config.mjs";
import { register } from "../src/instrumentation";

// The web server never logs raw request paths: they can hold a posting's question key. These
// checks run in Node (no browser); synthetic markers only.
const RAW = "http://127.0.0.1:8100/api/applications/x/answers/question_8101?token=tok_SYNTHETIC";

test("the development request log is off", async ({}, info) => {
  test.skip(info.project.name !== "desktop", "configuration check; once is enough");
  const logging = nextConfig.logging;
  expect(logging && logging.incomingRequests).toBe(false);
});

test("a failed API proxy is logged without its URL", async ({}, info) => {
  test.skip(info.project.name !== "desktop", "configuration check; once is enough");
  const lines: string[] = [];
  const saved = { error: console.error, runtime: process.env.NEXT_RUNTIME };
  console.error = (...args: unknown[]) => lines.push(args.map(String).join(" "));
  process.env.NEXT_RUNTIME = "nodejs";
  try {
    register();
    console.error(`Failed to proxy ${RAW}`, Object.assign(new Error(`connect to ${RAW}`), { code: "ECONNREFUSED" }));
    console.error("an unrelated error", 42);
  } finally {
    console.error = saved.error;
    if (saved.runtime === undefined) delete process.env.NEXT_RUNTIME;
    else process.env.NEXT_RUNTIME = saved.runtime;
  }
  expect(lines).toEqual(["Failed to proxy an API request to the backend (ECONNREFUSED)", "an unrelated error 42"]);
  expect(lines.join("\n")).not.toContain("question_8101");
  expect(lines.join("\n")).not.toContain("tok_SYNTHETIC");
});
