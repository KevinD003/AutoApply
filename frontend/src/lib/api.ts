export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function setCsrf(token: string | null) {
  csrfToken = token;
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d))
      return d
        .map((e: { loc?: string[]; msg?: string }) =>
          [e.loc?.slice(1).join("."), e.msg].filter(Boolean).join(": "),
        )
        .join("; ");
  }
  return `Request failed (${status})`;
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; json?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = opts.method ?? (opts.json !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (opts.json !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.form ?? (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
  });
  if (res.status === 204) return undefined as T;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status));
  return body as T;
}

export type TriState = "yes" | "no" | "unknown" | "not_applicable";

export interface Me {
  user_id: string;
  email: string;
  csrf_token: string;
}

export interface Job {
  id: string;
  employer: string | null;
  title: string | null;
  location: string | null;
  url: string | null;
  canonical_url: string | null;
  ats_provider: string;
  requisition_id: string | null;
  source: string;
  status: "new" | "shortlisted" | "excluded" | "closed";
  exclusion_reason: string | null;
  notes: string | null;
  posted_on: string | null;
  first_seen_at: string;
  last_seen_at: string;
  seen_count: number;
}

export interface JobDetail extends Job {
  description: string | null;
  explanations: { kind: "match" | "mismatch" | "exclude" | "info"; text: string }[];
}

export interface Application {
  id: string;
  job: Pick<Job, "id" | "title" | "employer" | "location" | "url" | "ats_provider">;
  state: string;
  state_changed_at: string;
  outcome: string;
  notes: string | null;
  created_at: string;
  events?: {
    kind: string;
    from_state: string | null;
    to_state: string | null;
    actor: string;
    reason: string | null;
    created_at: string;
  }[];
}

export interface Doc {
  id: string;
  lineage_id: string;
  version: number;
  kind: string;
  label: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  origin: string;
  created_at: string;
}

export interface FormOption {
  value: string;
  label: string;
}

export interface PackageAnswer {
  key: string;
  label: string;
  help_text: string | null;
  type: string;
  required: boolean;
  step: string | null;
  max_length: number | null;
  options: FormOption[];
  status: "resolved" | "needs_user" | "needs_consent" | "blank_optional";
  source: string;
  value: Record<string, unknown> | null;
  display: string | null;
  explanation: string;
  fact_refs: { type: string; id: string; version: number | string | null; field: string }[];
  intent: string;
  sensitive: boolean;
  acknowledgment: boolean;
  protected: boolean;
  bankable: boolean;
  user_input_allowed: boolean;
  draftable: boolean;
}

export interface PackageView {
  application_id: string;
  state: string;
  package: {
    id: string;
    version: number;
    content_hash: string;
    created_at: string;
    change_summary: string[];
    content: {
      destination: {
        job_id: string;
        employer: string | null;
        title: string | null;
        url: string | null;
        ats_provider: string;
        form_version: number;
        form_source: string;
        form_title: string | null;
      };
      documents: { field: string; document_id: string; version: number; display: string }[];
      answers: PackageAnswer[];
      consents: Record<string, string>;
      unresolved: string[];
      validation_errors: { key: string; message: string }[];
    };
  };
  approval:
    | { status: "approved"; approved_at: string; version: number }
    | { status: "invalidated"; approved_at: string; invalidated_at: string; reason: string }
    | { status: "not_approved" };
  history: { version: number; created_at: string; change_summary: string[]; was_approved: boolean }[];
  drafting_available: boolean;
  drafts: { id: string; field_key: string; text: string; evidence: string[]; provider: string }[];
}

export interface BankEntry {
  id: string;
  question_text: string;
  answer_shape: string;
  value: Record<string, unknown>;
  options_snapshot: string[];
  sensitive: boolean;
  version: number;
  updated_at: string;
}
