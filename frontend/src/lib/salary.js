// Shared salary presentation (Slice B). The backend sends salary with its provenance and the
// original figures (content.py); nothing here annualizes or converts — the figures are shown
// exactly as given. Used by both the jobs-list card and the job detail page so they agree.

export const SAL_PROVENANCE = {
  structured: "From the posting’s structured data",
  enrichment: "Estimated by the discovery source",
  extracted: "Found in the description text",
};

export const SAL_KIND = {
  base: "base pay",
  bonus: "bonus",
  equity: "equity",
  ote: "on-target earnings",
  total: "total",
};

// The figure as given: the extracted snippet verbatim, or the structured amount/range with its
// currency and period. Returns null when there is no salary (callers show "Salary not provided.").
export function salaryDisplay(s) {
  if (!s) return null;
  if (s.text) return s.text; // extracted: the original snippet, exactly as written
  const sym = s.currency_symbol || "";
  const code = !s.currency_symbol && s.currency ? ` ${s.currency}` : "";
  const amount = s.min && s.max ? `${sym}${s.min}–${sym}${s.max}` : `${sym}${s.amount || s.min || s.max || ""}`;
  const per = s.period ? ` / ${s.period}` : s.period_raw ? ` (${s.period_raw})` : "";
  return `${amount}${code}${per}`.trim();
}
