"use client";

import { useCallback, useEffect, useId, useState } from "react";

import { api } from "@/lib/api";
import { Button, Card, ErrorBox } from "./ui";

const ENGINE = {
  lightgbm: "your own LightGBM model",
  xgboost: "your own XGBoost model",
  rules: "similar wording (your model trains once you have judged enough suggestions)",
};

// D132's wording for a saved answer, so the two pages say the same thing.
const KEPT = "Answer saved, and kept for this exact question next time.";
const HERE_ONLY = "Answer saved for this application.";

/** D115: saved answers the answer brain proposes for questions worded differently. "Use and
 * save" answers the question and keeps the answer for this exact wording too; "Use here only"
 * (D133) answers it for this application alone; "Not this" is never proposed again for it. Each
 * choice teaches your own model. onView(view, notice) receives the package after a use. */
export default function AnswerSuggestions({ appId, version, onView }) {
  const uid = useId();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api(`/applications/${appId}/suggestions`).then(setData).catch(setError);
  }, [appId]);

  useEffect(() => {
    load();
  }, [load, version]);

  async function use(s, saveToBank) {
    await run(async () => {
      const json = { key: s.key, bank_entry_id: s.bank_entry_id, save_to_bank: saveToBank };
      const view = await api(`/applications/${appId}/suggestions/accept`, { method: "POST", json });
      onView(view, saveToBank ? KEPT : HERE_ONLY);
    });
  }

  async function reject(s) {
    await run(async () => {
      const json = { key: s.key, bank_entry_id: s.bank_entry_id };
      setData(await api(`/applications/${appId}/suggestions/reject`, { method: "POST", json }));
    });
  }

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      await action();
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
        Ranked by {ENGINE[data.brain.engine] ?? data.brain.engine}. Nothing is filled in until you choose. “Use and save”
        also keeps the answer for this exact question next time; “Use here only” answers this application alone.
      </p>
      <ErrorBox error={error} />
      <ul className="space-y-4">
        {data.suggestions.map((s, i) => {
          const about = `${uid}-q${i} ${uid}-a${i}`;
          return (
            <li key={`${s.key}:${s.bank_entry_id}`} className="border-b border-hairline pb-3" data-testid="answer-suggestion">
              <p id={`${uid}-q${i}`} className="text-sm font-medium">
                {s.label}
              </p>
              <p id={`${uid}-a${i}`} className="mt-1 text-sm">
                <span className="text-ink-faint">Your answer to “{s.saved_question}”:</span> <strong>{s.display}</strong>
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button disabled={busy} aria-describedby={about} className="!min-h-9 !py-1.5" onClick={() => use(s, true)}>
                  Use and save
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  aria-describedby={about}
                  className="!min-h-9 !py-1.5"
                  onClick={() => use(s, false)}
                >
                  Use here only
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  aria-describedby={about}
                  className="!min-h-9 !py-1.5"
                  onClick={() => reject(s)}
                >
                  Not this
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
