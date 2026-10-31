"use client";

import { useCallback, useEffect, useState } from "react";

import BankImport from "@/components/BankImport";
import { Badge, Button, Card, Empty, ErrorBox, inputCls, Loading, Notice } from "@/components/ui";
import { api, BankEdit, BankEntry, BankVersion } from "@/lib/api";

function show(e: BankEntry): string {
  const v = e.value as Record<string, unknown>;
  if (Array.isArray(v.labels)) return (v.labels as string[]).join(", ");
  for (const k of ["text", "number", "date"]) if (v[k] !== undefined) return String(v[k]);
  if (typeof v.checked === "boolean") return v.checked ? "Checked" : "Unchecked";
  return JSON.stringify(v);
}

function showValue(v: Record<string, unknown>): string {
  return show({ value: v } as BankEntry);
}

// Priority C (D78): an edit keeps the question it answers, writes a new version (the earlier
// ones stay in the history), and every application that used the earlier version asks for
// approval again.
function Editor({ e, onSaved, onCancel }: { e: BankEntry; onSaved: (r: BankEdit) => void; onCancel: () => void }) {
  const v = e.value as Record<string, unknown>;
  const [labels, setLabels] = useState<string[]>(Array.isArray(v.labels) ? (v.labels as string[]).map((l) => l.toLowerCase()) : []);
  const [text, setText] = useState(String(v.text ?? v.number ?? v.date ?? ""));
  const [checked, setChecked] = useState(v.checked === true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    const value =
      e.answer_shape === "choice" || e.answer_shape === "multi"
        ? { labels }
        : e.answer_shape === "boolean"
          ? { checked }
          : e.answer_shape === "number"
            ? { number: Number(text) }
            : e.answer_shape === "date"
              ? { date: text }
              : { text };
    try {
      onSaved(await api<BankEdit>(`/answer-bank/${e.id}`, { method: "PUT", json: { value } }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
      {e.answer_shape === "choice" ? (
        <select aria-label="New answer" className={inputCls} value={labels[0] ?? ""} onChange={(x) => setLabels([x.target.value])}>
          {e.options_snapshot.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : e.answer_shape === "multi" ? (
        <fieldset aria-label="New answer" className="space-y-1">
          {e.options_snapshot.map((o) => (
            <label key={o} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={labels.includes(o)}
                onChange={(x) => setLabels((cur) => (x.target.checked ? [...cur, o] : cur.filter((l) => l !== o)))}
              />
              {o}
            </label>
          ))}
        </fieldset>
      ) : e.answer_shape === "boolean" ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={checked} onChange={(x) => setChecked(x.target.checked)} /> Checked
        </label>
      ) : e.answer_shape === "number" || e.answer_shape === "date" ? (
        <input aria-label="New answer" className={inputCls} type={e.answer_shape} value={text} onChange={(x) => setText(x.target.value)} />
      ) : (
        <textarea aria-label="New answer" className={inputCls} rows={4} value={text} onChange={(x) => setText(x.target.value)} />
      )}
      <ErrorBox error={error} />
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save new version"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function History({ id }: { id: string }) {
  const [versions, setVersions] = useState<BankVersion[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<BankVersion[]>(`/answer-bank/${id}/history`).then(setVersions).catch(setError);
  }, [id]);
  if (error) return <ErrorBox error={error} />;
  if (!versions) return <Loading />;
  return (
    <ol aria-label="Versions" className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3 text-xs text-slate-600">
      {versions.map((h) => (
        <li key={h.version}>
          v{h.version}: <span className="font-medium text-slate-800">{showValue(h.value)}</span> · {h.how} ·{" "}
          {new Date(h.recorded_at).toLocaleString()}
        </li>
      ))}
    </ol>
  );
}

export default function AnswersPage() {
  const [items, setItems] = useState<BankEntry[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    api<BankEntry[]>("/answer-bank").then(setItems).catch((e) => {
      setError(e);
      setItems([]);
    });
  }, []);
  useEffect(load, [load]);

  async function approve(id: string) {
    try {
      await api(`/answer-bank/${id}/approve`, { method: "POST" });
      setNotice("Approved: it now answers this exact question.");
      load();
    } catch (e) {
      setError(e);
    }
  }

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
        {notice && <Notice>{notice}</Notice>}
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
                  {e.approval_status === "proposed" && (
                    <p className="text-xs text-slate-600">
                      <Badge tone="indigo">Imported</Badge> Not used until you approve it. Check the answer is true for you today.
                    </p>
                  )}
                  {e.not_reused && (
                    <p className="text-xs text-slate-600">
                      <Badge tone="amber">Not reused</Badge> {e.not_reused} You can delete it.
                    </p>
                  )}
                  <p className="text-xs text-slate-500">
                    v{e.version} · updated {new Date(e.updated_at).toLocaleString()} {e.sensitive && <Badge tone="amber">Sensitive</Badge>}
                  </p>
                  {editing === e.id && (
                    <Editor
                      e={e}
                      onCancel={() => setEditing(null)}
                      onSaved={(r) => {
                        setEditing(null);
                        setNotice(
                          r.changed
                            ? `Saved as version ${r.entry.version}.` +
                                (r.applications_to_approve_again > 0
                                  ? ` ${r.applications_to_approve_again} application(s) used the earlier answer and need your approval again.`
                                  : "")
                            : "Nothing changed.",
                        );
                        load();
                      }}
                    />
                  )}
                  {history === e.id && <History id={e.id} />}
                </div>
                <div className="flex shrink-0 gap-2">
                  {e.approval_status === "proposed" && !e.not_reused && (
                    <Button className="!min-h-8 !px-2 !py-1" onClick={() => approve(e.id)}>
                      Approve
                    </Button>
                  )}
                  {!e.not_reused && (
                    <Button variant="secondary" className="!min-h-8 !px-2 !py-1" onClick={() => setEditing(editing === e.id ? null : e.id)}>
                      Edit
                    </Button>
                  )}
                  <Button variant="secondary" className="!min-h-8 !px-2 !py-1" onClick={() => setHistory(history === e.id ? null : e.id)}>
                    History
                  </Button>
                  <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(e.id)}>
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <BankImport onDone={load} />
    </>
  );
}
