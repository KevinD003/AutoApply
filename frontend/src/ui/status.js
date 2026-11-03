/*
  Single source of truth for how application / package / route state is shown.

  Ported verbatim from the behaviour in src/app/(app)/tracker/page.tsx and
  src/app/(app)/review/page.tsx, then extended with the route-card and
  rehearsal-prerequisite vocabulary from the verified backend contract
  (providers/routing.py, execution/rehearsal.py). Pure functions, no React —
  so the premium .jsx screens and any Node tooling share one vocabulary.

  Tones map to the semantic palette in globals.css:
    brand · positive · caution · danger · info · neutral
*/

// Neutral timeline state names (never a verdict). applications/states.py AppState.
export const STATE_LABEL = {
  draft: "Draft",
  preparing: "Preparing",
  awaiting_approval: "Awaiting your approval",
  queued: "Queued",
  running: "Running",
  needs_user_action: "Needs your action",
  ready_to_submit: "Ready to submit",
  submitting: "Submitting",
  submitted_confirmed: "Submitted (confirmed)",
  submitted_unconfirmed: "Submitted (not confirmed)",
  failed_retryable: "Failed (can retry)",
  failed_terminal: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
};

// applications/states.py Outcome — what the user reports the employer did, never inferred.
export const OUTCOME_LABEL = {
  none: "No outcome yet",
  assessment_received: "Assessment received",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Employer declined",
  withdrawn: "Withdrawn",
  no_response: "No response",
};

// applications/funnel.py stage names.
export const STAGE_LABEL = {
  prepared: "Prepared",
  approved: "Approved (to submit or to rehearse)",
  disclosed: "Data entered on an employer's form",
  form_rejected: "Form rejected (the employer's form refused it)",
  submitted: "Submitted",
  responded: "Any response",
  assessment_received: "Assessment received",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Employer declined",
  no_response: "No response (you marked it)",
  no_response_yet: "No response yet",
  withdrawn: "Withdrawn after submitting",
  withdrawn_before_submission: "Withdrawn before submitting",
};

export const OF_LABEL = {
  tracked: "tracked",
  prepared: "prepared",
  approved: "approved",
  disclosed: "with data entered",
  submitted: "submitted",
};

// Package answer status → short label (preparation/resolver.py Resolution.status).
export const ANSWER_STATUS_LABEL = {
  resolved: "Ready",
  needs_user: "Needs your answer",
  needs_consent: "Needs your consent",
  blank_optional: "Optional — left blank",
};

export const ANSWER_STATUS_TONE = {
  resolved: "positive",
  needs_user: "caution",
  needs_consent: "caution",
  blank_optional: "neutral",
};

// Route-card label/tone (providers/routing.py RouteDecision.route).
export const ROUTE_LABEL = {
  api: "Authorized API",
  browser: "Browser adapter",
  checkpoint: "Needs you: a step NoEfforts cannot do",
  manual_handoff: "Manual: apply on the employer's site",
};

export function routeTone(route) {
  if (route === "api" || route === "browser") return "brand";
  if (route === "checkpoint") return "caution";
  return "neutral"; // manual_handoff — neutral, not an error
}

// execution/rehearsal.py status → label/tone (also surfaced in the package view).
export const REHEARSAL_LABEL = {
  met: "Rehearsal passed",
  established: "Submitted here before, after a rehearsal",
  unmet: "Rehearsal needed before the first submission",
  not_required: "No rehearsal needed (local test form)",
  not_applicable: "Not applicable: you apply on the employer's site",
};

export function rehearsalTone(status) {
  if (status === "met" || status === "established" || status === "not_required") return "positive";
  if (status === "unmet") return "caution";
  return "neutral";
}

/*
  The display status + tone for one application row (AppOut), computed exactly as
  tracker/page.tsx did: submission basis wins, then failure/cancel, then the
  neutral state label. Returns { label, tone }.
*/
export function applicationStatus(a) {
  let label;
  if (a.state === "submitted_confirmed") {
    label = a.submission === "receipt" ? "Submitted (employer receipt)" : "Submitted (confirmed by you)";
  } else if (a.state === "submitted_unconfirmed") {
    if (a.submission === "receipt") label = "Receipt recorded: confirm it below";
    else if (a.submission === "user_claimed") label = "Applied by you (not confirmed)";
    else label = "Submitted (not confirmed)";
  } else if (a.state === "failed_terminal" && a.last_attempt?.state === "rejected") {
    label = "Form rejected";
  } else {
    label = STATE_LABEL[a.state] ?? a.state;
  }

  let tone = "brand";
  if (a.submission === "receipt") tone = "positive";
  else if (a.submission === "user_claimed") tone = "brand";
  else if (a.state.startsWith("failed") || a.state === "cancelled" || a.state === "expired") tone = "danger";
  else if (
    a.state === "needs_user_action" ||
    a.state === "awaiting_approval" ||
    a.state === "submitted_unconfirmed"
  )
    tone = "caution";

  return { label, tone };
}

/*
  A high-level "journey stage" for the premium Tracker/Review surfaces — the
  honest, human phase the mandate asks for. Derived only from fields the server
  provides on AppOut; it never implies a confirmed outcome that isn't evidenced.
*/
export function journeyStage(a) {
  const rehearsed = a.last_attempt?.state === "rehearsed";
  switch (a.state) {
    case "draft":
    case "preparing":
      return { key: "preparing", label: "Preparing", tone: "neutral" };
    case "awaiting_approval":
      return { key: "review", label: "Ready for your review", tone: "caution" };
    case "needs_user_action":
      return { key: "needs_you", label: "Needs your action", tone: "caution" };
    case "queued":
    case "running":
    case "ready_to_submit":
    case "submitting":
      return { key: "in_progress", label: "Working on it", tone: "brand" };
    case "submitted_unconfirmed":
      return { key: "awaiting_confirmation", label: "Awaiting confirmation", tone: "caution" };
    case "submitted_confirmed":
      return { key: "submitted", label: "Submitted", tone: "positive" };
    case "failed_retryable":
    case "failed_terminal":
      return { key: "failed", label: "Didn't go through", tone: "danger" };
    case "cancelled":
      return { key: "cancelled", label: "Cancelled", tone: "neutral" };
    case "expired":
      return { key: "expired", label: "Expired", tone: "neutral" };
    default:
      return rehearsed
        ? { key: "rehearsed", label: "Rehearsal finished — nothing submitted", tone: "brand" }
        : { key: "unknown", label: STATE_LABEL[a.state] ?? a.state, tone: "neutral" };
  }
}
