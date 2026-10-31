"use client";

import { ChangeEvent, useState } from "react";

import { Button, Card, ErrorBox, Notice } from "./ui";
import { api, BankImportResult } from "@/lib/api";

// D99: saved answers from a file you supply (another tool's question/answer pairs, or a review
// sheet). The file is read here, in your browser; only its questions and answers go to your own
// NoEfforts. Each row is judged by the rules for saved answers; the rest become proposals that
// answer nothing until you approve each one below.
type Row = { question: string; answer: string };

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(cell);
      cell = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

/** Rows from JSON ([{question, answer}] or {answers: [...]}) or CSV with question and answer
 * columns. A review sheet with an "approve" column keeps only the rows marked yes or edit, and
 * an edit uses "your corrected answer". */
export function rowsFrom(name: string, text: string): Row[] {
  if (name.toLowerCase().endsWith(".json")) {
    const data = JSON.parse(text);
    const list = Array.isArray(data) ? data : Array.isArray(data?.answers) ? data.answers : [];
    return list
      .filter((d: unknown) => d && typeof d === "object")
      .map((d: Record<string, unknown>) => ({
        question: String(d.question ?? d.label ?? ""),
        answer: String(d.answer ?? d.value ?? ""),
      }));
  }
  const [head, ...body] = parseCsv(text);
  if (!head) return [];
  const col = (re: RegExp) => head.findIndex((h) => re.test(h.trim().toLowerCase()));
  const q = col(/^question$/);
  const a = col(/^answer$/);
  const approve = col(/^approve/);
  const corrected = col(/corrected answer/);
  if (q < 0 || a < 0) throw new Error("The CSV needs a 'question' and an 'answer' column.");
  return body.flatMap((r) => {
    const mark = approve >= 0 ? (r[approve] ?? "").trim().toLowerCase() : "yes";
    if (mark !== "yes" && mark !== "edit") return [];
    const fixed = corrected >= 0 ? (r[corrected] ?? "").trim() : "";
    return [{ question: r[q] ?? "", answer: mark === "edit" && fixed ? fixed : r[a] ?? "" }];
  });
}

export default function BankImport({ onDone }: { onDone: () => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [check, setCheck] = useState<BankImportResult | null>(null);
  const [done, setDone] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function pick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    setRows(null);
    setCheck(null);
    setDone("");
    setError(null);
    if (!file) return;
    try {
      const parsed = rowsFrom(file.name, await file.text());
      if (parsed.length === 0) throw new Error("No question and answer rows in this file.");
      if (parsed.length > 5000) throw new Error("At most 5,000 rows at a time.");
      setRows(parsed);
      setCheck(await api<BankImportResult>("/answer-bank/import", { json: { rows: parsed, dry_run: true } }));
    } catch (err) {
      setError(err);
    }
  }

  async function add() {
    if (!rows) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<BankImportResult>("/answer-bank/import", { json: { rows, dry_run: false } });
      setDone(`${r.added} added as proposals. Approve each one below before it is used.`);
      setRows(null);
      setCheck(null);
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Import saved answers">
      <p className="text-sm text-slate-600">
        A JSON or CSV file of questions and answers, for example from another tool. It is read in your browser and only its questions
        and answers are sent to your own NoEfforts. Each one is checked by the rules above; what passes is added as a proposal that
        answers nothing until you approve it. Work authorization, sponsorship, residence, sensitive topics, answers about one
        employer or job, and a question given twice with different answers are never imported.
      </p>
      <input
        type="file"
        accept=".json,.csv,application/json,text/csv"
        aria-label="File of questions and answers"
        className="mt-2 block w-full text-sm"
        onChange={pick}
      />
      <ErrorBox error={error} />
      {done && <Notice>{done}</Notice>}
      {check && (
        <div className="mt-3 space-y-2 text-sm" data-testid="import-check">
          <p>
            {check.rows} rows: <span className="font-medium">{check.importable} can be added</span>, {check.rows - check.importable}{" "}
            not imported.
          </p>
          {Object.keys(check.refused).length > 0 && (
            <ul className="list-disc pl-5 text-slate-600">
              {Object.entries(check.refused)
                .sort((x, y) => y[1] - x[1])
                .map(([k, n]) => (
                  <li key={k}>
                    {n}: {check.reasons[k] ?? k}
                  </li>
                ))}
            </ul>
          )}
          <Button onClick={add} disabled={busy || check.importable === 0}>
            {busy ? "Adding…" : `Add ${check.importable} as proposals`}
          </Button>
        </div>
      )}
    </Card>
  );
}
