"use client";

import { useCallback, useEffect, useState } from "react";

import { api, AnswerSuggestion, PackageView, SuggestionsView } from "@/lib/api";
import { Button, Card, ErrorBox } from "./ui";

const ENGINE: Record<string, string> = {
  lightgbm: "your own LightGBM model",
  xgboost: "your own XGBoost model",
  rules: "similar wording (your model trains once you have judged enough suggestions)",
};

/** D115: saved answers the answer brain proposes for questions worded differently. "Use this"
 * answers the question and remembers it for this exact wording; "Not this" is never proposed
 * again for it. Each choice teaches your own model. */
export default function AnswerSuggestions({
  appId,
  version,
  onView,
}: {
  appId: string;
  version: number;
  onView: (v: PackageView) => void;
}) {
  const [data, setData] = useState<SuggestionsView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<SuggestionsView>(`/applications/${appId}/suggestions`).then(setData).catch(setError);
  }, [appId]);

  useEffect(() => {
    load();
  }, [load, version]);

  async function judge(s: AnswerSuggestion, what: "accept" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const json = { key: s.key, bank_entry_id: s.bank_entry_id };
      if (what === "accept") {
        onView(await api<PackageView>(`/applications/${appId}/suggestions/accept`, { method: "POST", json }));
      } else {
        setData(await api<SuggestionsView>(`/applications/${appId}/suggestions/reject`, { method: "POST", json }));
      }
    } catch (e) {
      setError(e);
      load();
    } finally {
      setBusy(false);
    }
  }

  if (!data || data.suggestions.length === 0) return error ? <ErrorBox error={error} /> : null;
  return (
    <Card title={`Suggested from your saved answers (${data.suggestions.length})`}>
      <p className="mb-3 text-sm text-ink-muted">
        Ranked by {ENGINE[data.brain.engine] ?? data.brain.engine}. Nothing is filled in until you choose.
      </p>
      <ErrorBox error={error} />
      <ul className="space-y-4">
        {data.suggestions.map((s) => (
          <li key={`${s.key}:${s.bank_entry_id}`} className="border-b border-hairline pb-3" data-testid="answer-suggestion">
            <p className="text-sm font-medium">{s.label}</p>
            <p className="mt-1 text-sm">
              <span className="text-ink-faint">Your answer to “{s.saved_question}”:</span> <strong>{s.display}</strong>
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button disabled={busy} className="!min-h-9 !py-1.5" onClick={() => judge(s, "accept")}>
                Use this
              </Button>
              <Button variant="secondary" disabled={busy} className="!min-h-9 !py-1.5" onClick={() => judge(s, "reject")}>
                Not this
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
