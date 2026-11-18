// D168: words the debugger pages share (backend app/modules/debug/service.py names the stages).
export const STAGE = {
  discovery: { label: "Found", tone: "slate" },
  capture: { label: "Form read", tone: "indigo" },
  package: { label: "Package", tone: "indigo" },
  draft: { label: "AI draft", tone: "slate" },
  approval: { label: "Approval", tone: "green" },
  rule: { label: "Standing rule", tone: "amber" },
  state: { label: "Status", tone: "slate" },
  attempt: { label: "Attempt", tone: "indigo" },
  pause: { label: "Paused", tone: "amber" },
  email: { label: "Email", tone: "slate" },
  audit: { label: "Audit log", tone: "slate" },
};

export function stage(key) {
  // An unknown stage is shown plainly, never a crash.
  return STAGE[key] ?? { label: key, tone: "slate" };
}

export function when(at) {
  return at ? new Date(at).toLocaleString() : "—";
}

// A job's address is page data (untrusted): linked only when it is an http(s) address.
export function safeHref(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : null;
}
