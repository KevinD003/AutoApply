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
  discovered_from: {
    provider: string;
    label: string;
    source_url: string | null;
    attribution: Attribution;
    last_seen_at: string;
    stale: boolean;
    stale_reason: string | null;
    changed_fields: string[];
  }[];
}

export interface Attribution {
  text: string;
  url: string | null;
}

export interface DiscoveryProviderInfo {
  name: string;
  label: string;
  enabled: boolean;
  capabilities: Record<string, unknown>;
  status: {
    implemented_locally: boolean;
    external_api_configured: boolean;
    external_api_tested: boolean;
    production_ready: boolean;
    note: string;
  };
  support_label: string; // derived from the provider registry's evidence (backend providers/wording.py)
}

export interface SourceFact {
  value: "yes" | "no" | "unknown";
  stated_by: string;
  basis: string;
}

export interface DiscoveredJob {
  id: string;
  provider: string;
  provider_label: string;
  source_job_id: string;
  title: string | null;
  employer: string | null;
  location: string | null;
  workplace: string;
  employment_type: string | null;
  job_url: string | null;
  application_url: string | null;
  published_on: string | null;
  source_updated_at: string | null;
  attribution: Attribution;
  status: "linked" | "incomplete" | "closed";
  job_id: string | null;
  link_basis: string | null;
  missing: string[];
  filter: { result: "match" | "insufficient"; fields: string[] } | null;
  source_facts: { sponsorship_offered?: SourceFact };
  stale: boolean;
  stale_reason: string | null;
  changed_fields: string[];
  last_seen_at: string;
}

export interface DiscoveryImportResult {
  provider: string;
  fetched: number;
  pages: number;
  truncated: boolean;
  stop_reason: string | null;
  created: number;
  updated: number;
  unchanged: number;
  malformed: number;
  duplicates_in_listing: number;
  excluded_by_filters: number;
  insufficient_data: number;
  incomplete: number;
  stale: number;
  linked_new_jobs: number;
  linked_existing_jobs: number;
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
    // scope: "submit" fills and submits once; "disclose_only" is a rehearsal that never submits.
    | { status: "approved"; approved_at: string; version: number; scope: ApprovalScope }
    | { status: "invalidated"; approved_at: string; invalidated_at: string; reason: string }
    | { status: "not_approved" };
  history: { version: number; created_at: string; change_summary: string[]; was_approved: boolean }[];
  // Served wording (backend providers/wording.py): set when the form's source is a local test stand-in.
  labels: { form_source: string | null };
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

export type ApprovalScope = "submit" | "disclose_only";

export interface AttemptView {
  id: string;
  state: string;
  adapter: string;
  approval_scope: ApprovalScope | null;
  created_at: string;
  disclosure_started_at: string | null;
  send_started_at: string | null;
  finished_at: string | null;
  outcome: string | null;
  events: { kind: string; generation: number; at: string }[];
  checkpoints: { id: string; status: string; round: number; message: string | null; expires_at: string; wrong_attempts: number; max_attempts: number }[];
  evidence: { kind: string; strength: string; data: Record<string, unknown>; at: string }[];
}
