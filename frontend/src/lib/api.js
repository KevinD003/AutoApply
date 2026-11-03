export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let csrfToken = null;

export function setCsrf(token) {
  csrfToken = token;
}

function messageFrom(body, status) {
  if (body && typeof body === "object" && "detail" in body) {
    const d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d))
      return d
        .map((e) => [e.loc?.slice(1).join("."), e.msg].filter(Boolean).join(": "))
        .join("; ");
  }
  return `Request failed (${status})`;
}

export async function api(path, opts = {}) {
  const method = opts.method ?? (opts.json !== undefined || opts.form ? "POST" : "GET");
  const headers = {};
  if (opts.json !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.form ?? (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
  });
  if (res.status === 204) return undefined;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status));
  return body;
}

// Window event the notifications bell and feed listen for to re-read the unread count.
export const NOTIFICATIONS_CHANGED = "noefforts:notifications";
