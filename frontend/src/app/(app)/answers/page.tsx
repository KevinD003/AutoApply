"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { api, BankEntry } from "@/lib/api";

function show(e: BankEntry): string {
  const v = e.value as Record<string, unknown>;
  if (Array.isArray(v.labels)) return (v.labels as string[]).join(", ");
  for (const k of ["text", "number", "date"]) if (v[k] !== undefined) return String(v[k]);
  if (typeof v.checked === "boolean") return v.checked ? "Checked" : "Unchecked";
  return JSON.stringify(v);
}

export default function AnswersPage() {
  const [items, setItems] = useState<BankEntry[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<BankEntry[]>("/answer-bank").then(setItems).catch((e) => {
      setError(e);
      setItems([]);
    });
  }, []);
  useEffect(load, [load]);

  async function remove(id: string) {
    try {
      await api(`/answer-bank/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Saved answers</h1>
      <p className="text-sm text-slate-600">
        Answers you chose to reuse. Each is tied to the exact wording of the question, its help text and, for multiple-choice
        questions, the options the employer offered. If any of these changes, NoEfforts asks you again instead of guessing. Answers
        that depend on the employer, the job or the date are never offered for saving: how you heard about a job, referrals, working
        for or applying to an employer before, relevant experience and a job&apos;s requirements, start dates, availability,
        schedules, notice periods, years of experience, anything current or valid now, pay and salary, relocation, commuting,
        travel, work location and addresses. Neither are work authorization, sponsorship, residence, legal statements and sensitive
        topics. NoEfforts recognises known wordings only, so check what you save. Answers saved before a rule was added stay
        listed here, marked “Not reused”, and answer nothing.
      </p>
      <Card>
        <ErrorBox error={error} />
        {items === null ? (
          <Loading />
        ) : items.length === 0 ? (
          <Empty>No saved answers yet. Tick “Reuse for this exact question” when answering an application.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {items.map((e) => (
              <li key={e.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="text-sm">
                  <p className="font-medium">{e.question_text}</p>
                  <p>
                    Answer: <span className="font-medium">{show(e)}</span>
                  </p>
                  {e.options_snapshot.length > 0 && <p className="text-xs text-slate-500">Options when saved: {e.options_snapshot.join(" · ")}</p>}
                  {e.help_text ? (
                    <p className="line-clamp-3 text-xs text-slate-500">Help text when saved: {e.help_text}</p>
                  ) : e.help_text === null && !e.not_reused ? (
                    <p className="text-xs text-slate-500">Saved before NoEfforts recorded help text: reused only where the question has none.</p>
                  ) : null}
                  {e.not_reused && (
                    <p className="text-xs text-slate-600">
                      <Badge tone="amber">Not reused</Badge> {e.not_reused} You can delete it.
                    </p>
                  )}
                  <p className="text-xs text-slate-500">
                    v{e.version} · updated {new Date(e.updated_at).toLocaleString()} {e.sensitive && <Badge tone="amber">Sensitive</Badge>}
                  </p>
                </div>
                <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(e.id)}>
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
