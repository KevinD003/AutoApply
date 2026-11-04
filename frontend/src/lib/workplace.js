// Shared work-arrangement presentation (Slice D). The backend sends a normalized workplace
// token (remote | hybrid | onsite) ONLY when a discovery source gave one (content.py /
// discovery provider); it is never inferred and never set from a manually added job. Used by
// both the jobs-list card and the job detail page so the two can never disagree.

export const WORKPLACE = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
  on_site: "On-site",
  "on-site": "On-site",
};

// A human label for a workplace token, or null when none was given (so callers render nothing —
// an absent work arrangement is left absent, never guessed). An unknown token is title-cased.
export function workplaceLabel(w) {
  if (!w) return null;
  return WORKPLACE[w] ?? w.charAt(0).toUpperCase() + w.slice(1);
}
