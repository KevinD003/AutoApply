"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice } from "@/components/ui";
import { api, Job } from "@/lib/api";

interface ImportResult {
  total_rows: number;
  created: number;
  duplicates: number;
  errors: number;
  rows: { row: number; row_id: string; outcome: string; errors?: string[] }[];
}

const STATUS_TONE = { new: "indigo", shortlisted: "green", excluded: "red", closed: "slate" } as const;

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (status) p.set("status", status);
    try {
      const r = await api<{ items: Job[]; total: number }>(`/jobs?${p}`);
      setJobs(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e);
      setJobs([]);
    }
  }, [q, status]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <h1 className="text-xl font-semibold">Jobs</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <AddJob onAdded={load} />
        <ImportJobs onImported={load} />
      </div>
      <Card
        title={`Your jobs (${total})`}
        actions={
          <div className="flex gap-2 text-sm">
            <a className="text-indigo-700 underline" href="/api/jobs/export?format=csv">Export CSV</a>
            <a className="text-indigo-700 underline" href="/api/jobs/export?format=xlsx">Export XLSX</a>
          </div>
        }
      >
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <input aria-label="Search jobs" className={inputCls} placeholder="Search title, employer, location" value={q} onChange={(e) => setQ(e.target.value)} />
          <select aria-label="Filter by status" className={`${inputCls} sm:w-44`} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="new">New</option>
            <option value="shortlisted">Shortlisted</option>
            <option value="excluded">Excluded</option>
            <option value="closed">Closed</option>
          </select>
        </div>
        <ErrorBox error={error} />
        {jobs === null ? (
          <Loading />
        ) : jobs.length === 0 ? (
          <Empty>No jobs yet. Add a job link above or import a spreadsheet.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {jobs.map((j) => (
              <li key={j.id}>
                <Link href={`/jobs/${j.id}`} className="flex flex-col gap-1 py-3 hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between sm:px-2">
                  <div>
                    <p className="font-medium text-slate-900">{j.title ?? "Untitled role"}</p>
                    <p className="text-sm text-slate-600">
                      {[j.employer, j.location].filter(Boolean).join(" · ") || "Details not provided"}
                    </p>
                    {j.exclusion_reason && <p className="text-xs text-red-700">{j.exclusion_reason}</p>}
                  </div>
                  <div className="flex gap-2">
                    {j.ats_provider !== "unknown" && <Badge>{j.ats_provider}</Badge>}
                    <Badge tone={STATUS_TONE[j.status]}>{j.status}</Badge>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function AddJob({ onAdded }: { onAdded: () => void }) {
  const [form, setForm] = useState({ url: "", title: "", employer: "", location: "" });
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v.trim()));
      const r = await api<{ duplicate: boolean }>("/jobs", { json: body });
      setNotice(r.duplicate ? "You already have this job — nothing was duplicated." : "Job added.");
      setForm({ url: "", title: "", employer: "", location: "" });
      onAdded();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Add a job">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Job link" hint="Paste a posting URL, or fill in title and employer.">
          <input className={inputCls} type="url" inputMode="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Title">
            <input className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </Field>
          <Field label="Employer">
            <input className={inputCls} value={form.employer} onChange={(e) => setForm({ ...form, employer: e.target.value })} />
          </Field>
        </div>
        <Field label="Location">
          <input className={inputCls} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </Field>
        <ErrorBox error={error} />
        {notice && <Notice>{notice}</Notice>}
        <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add job"}</Button>
      </form>
    </Card>
  );
}

function ImportJobs({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      setResult(await api<ImportResult>("/jobs/import", { form }));
      onImported();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const problems = result?.rows.filter((r) => r.outcome === "error") ?? [];
  return (
    <Card title="Import CSV / XLSX">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-slate-600">
          Columns: <code>job_url</code>, <code>employer</code>, <code>title</code>, <code>location</code>, <code>status</code>,{" "}
          <code>posted_on</code>, <code>requisition_id</code>, <code>notes</code>, <code>row_id</code>. Each row needs a link, or a title and employer.
        </p>
        <input aria-label="Spreadsheet file" type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
        <ErrorBox error={error} />
        {result && (
          <Notice>
            {result.created} added, {result.duplicates} already known, {result.errors} with problems ({result.total_rows} rows).
          </Notice>
        )}
        {problems.length > 0 && (
          <ul className="max-h-40 overflow-y-auto rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
            {problems.map((p) => (
              <li key={p.row}>
                Row {p.row} ({p.row_id}): {p.errors?.join("; ")}
              </li>
            ))}
          </ul>
        )}
        <Button type="submit" disabled={!file || busy}>{busy ? "Importing…" : "Import"}</Button>
      </form>
    </Card>
  );
}
