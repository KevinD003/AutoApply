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
  signals: JobSignals;
}

// S3 (backend jobs/signals.py): what about the job holds an approval back. Messages are served.
export interface JobSignals {
  source_closed: { provider: string; provider_label: string; reason: string; since: string } | null;
  possible_duplicates: {
    job_id: string;
    title: string | null;
    employer: string | null;
    location: string | null;
    application_id: string;
    state: string;
    outcome: string;
  }[];
  open_confirmed_at: string | null;
  distinct_confirmed_at: string | null;
  approval_blocked: { code: string; message: string } | null;
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
  // S3: the linked job's own application and how many possible duplicates it has.
  job_signals: { application: { state: string; outcome: string } | null; possible_duplicates: number } | null;
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
  deleted_by_you: number;
}

// A watched search (D56): the owner's standing approval, recorded on the backend host.
export interface DiscoveryWatch {
  id: string;
  provider: string;
  query: string;
  interval_seconds: number;
  not_after: string;
  stopped: boolean;
  paused_reason: string | null;
  last_checked_at: string | null;
  next_check_at: string;
  last_outcome: string | null;
  found_total: number;
}

export interface DiscoveryDeleteResult {
  job_deleted: boolean;
  job_kept_because: string | null;
}

export type Outcome =
  | "none"
  | "assessment_received"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "no_response";

// What a submission rests on (D53): computed by the server, never sent by the client.
export type SubmissionBasis = "receipt" | "user_claimed" | "unconfirmed";

export interface Application {
  id: string;
  job: Pick<Job, "id" | "title" | "employer" | "location" | "url" | "ats_provider">;
  state: string;
  state_changed_at: string;
  outcome: Outcome;
  notes: string | null;
  created_at: string;
  // The latest execution attempt, if any (state from the execution service).
  last_attempt: { state: string; approval_scope: "submit" | "disclose_only" | null } | null;
  submission: SubmissionBasis | null;
  reached_submission: boolean;
  outcome_choices?: Outcome[]; // detail only
  events?: {
    kind: string;
    from_state: string | null;
    to_state: string | null;
    actor: string;
    reason: string | null;
    from_outcome: Outcome | null;
    to_outcome: Outcome | null;
    source: "receipt" | "user_claimed" | "user_reported" | null;
    occurred_on: string | null;
    evidence_note: string | null;
    created_at: string;
  }[];
}

export interface FunnelStage {
  stage: string;
  count: number;
  of: number;
  of_stage: string;
}

// Counts and their denominators only; never a rate (D53).
export interface Funnel {
  tracked: number;
  stages: FunnelStage[];
  submitted: {
    total: number;
    receipt: number;
    user_claimed: number;
    unconfirmed: number;
    confirmed_by_you: number;
    applied_by_you: number;
  };
  no_response_after_days: number;
  min_submissions_to_compare: number;
  too_few_to_compare: boolean;
  note: string | null;
  outcome_before_submission: number;
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
        origin: string | null;
        submit_url: string | null;
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
    // A rehearsal used this approval up: nothing was submitted.
    | { status: "used_by_rehearsal"; approved_at: string; rehearsed_at: string; version: number }
    | { status: "invalidated"; approved_at: string; invalidated_at: string; reason: string }
    | { status: "not_approved" };
  history: { version: number; created_at: string; change_summary: string[]; was_approved: boolean }[];
  // Served wording (backend providers/wording.py): set when the form's source is a local test stand-in.
  labels: { form_source: string | null; destination: string | null };
  // C12: what the review page may offer per question key (outside the package content).
  review: Record<string, ReviewControls>;
  // Whether a submission here needs a successful rehearsal first (backend execution/rehearsal.py).
  // All text is served; reason_code is a fixed code (a rehearsal code, or the route's own code
  // when NoEfforts does not submit here at all).
  rehearsal_prerequisite: RehearsalPrerequisite;
  // S3: the job's own signals (closed, excluded, possible duplicate), outside the package.
  job_signals: JobSignals;
  drafting_available: boolean;
  drafts: { id: string; field_key: string; text: string; evidence: string[]; provider: string }[];
}

// C14: what changed between two versions of a package (read-only, the page's own words).
export interface PackageDiff {
  from: { version: number; content_hash: string; created_at: string; was_approved: boolean };
  to: { version: number; content_hash: string; created_at: string; was_approved: boolean };
  answers: {
    key: string;
    label: string;
    step: string | null;
    changed: ("value" | "question" | "basis" | "added" | "removed")[];
    before: { display: string | null; status: string; source: string } | null;
    after: { display: string | null; status: string; source: string } | null;
  }[];
  documents: { field: string; before: string | null; after: string | null }[];
  consents: { key: string; label: string; before: string | null; after: string | null }[];
  destination: { field: string; before: unknown; after: unknown }[];
}

export interface ReviewControls {
  answer_here: boolean; // answer or change it on this page
  clear: boolean; // an answer given for this application is stored and can be removed
  document_role: "resume" | "cover_letter" | null;
  not_asked: boolean;
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
  /** null: saved before NoEfforts recorded help text (C6); "": the question had none. */
  help_text: string | null;
  /** Why this saved answer no longer answers its own question (D51), or null. */
  not_reused: string | null;
}

export type ApprovalScope = "submit" | "disclose_only";

export interface RehearsalPrerequisite {
  status: "met" | "established" | "unmet" | "not_required" | "not_applicable";
  reason_code: string | null;
  message: string;
  label: string;
}

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
  // What the result counts as (one evidence class), with its served label; null when it counts
  // as none. rehearsal_prerequisite: how the send gate found it (met, established, not_required).
  destination_class: "fixture" | "real" | null;
  evidence_class: string | null;
  evidence_label: string | null;
  rehearsal_prerequisite: string | null;
  // For a finished rehearsal: "valid" while its own record holds, or the fixed code saying why
  // not; withdrawable when it has a record that is not revoked yet.
  rehearsal: { status: string; revoked_at: string | null; withdrawable: boolean } | null;
  events: { kind: string; generation: number; detail?: Record<string, unknown>; at: string }[];
  checkpoints: { id: string; status: string; round: number; message: string | null; expires_at: string; wrong_attempts: number; max_attempts: number }[];
  evidence: { kind: string; strength: string; data: Record<string, unknown>; at: string }[];
}
