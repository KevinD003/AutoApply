"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice } from "@/components/ui";
import { api, Doc } from "@/lib/api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [versions, setVersions] = useState<Record<string, Doc[]>>({});
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Doc[]>("/documents").then(setDocs).catch((e) => {
      setError(e);
      setDocs([]);
    });
  }, []);
  useEffect(load, [load]);

  async function showVersions(d: Doc) {
    try {
      const v = await api<Doc[]>(`/documents/${d.id}/versions`);
      setVersions((cur) => ({ ...cur, [d.lineage_id]: v }));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Documents</h1>
      <Upload onDone={load} />
      <Card title="Your documents">
        <ErrorBox error={error} />
        {docs === null ? (
          <Loading />
        ) : docs.length === 0 ? (
          <Empty>Upload your resume to get started. Originals are kept unchanged; new uploads become new versions.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {docs.map((d) => (
              <li key={d.id} className="py-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-medium">{d.label}</p>
                    <p className="text-sm text-slate-600">
                      {d.original_filename} · {(d.size_bytes / 1024).toFixed(0)} KB · v{d.version}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{d.kind.replace("_", " ")}</Badge>
                    <a className="text-sm text-indigo-700 underline" href={`/api/documents/${d.id}/download`}>Download</a>
                    {d.version > 1 && (
                      <button className="text-sm text-indigo-700 underline" onClick={() => showVersions(d)}>History</button>
                    )}
                    <Upload compact lineage={d} onDone={load} />
                  </div>
                </div>
                {versions[d.lineage_id] && (
                  <ul className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2 text-sm">
                    {versions[d.lineage_id].map((v) => (
                      <li key={v.id}>
                        v{v.version} — {new Date(v.created_at).toLocaleString()} —{" "}
                        <a className="text-indigo-700 underline" href={`/api/documents/${v.id}/download`}>download</a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function Upload({ onDone, lineage, compact }: { onDone: () => void; lineage?: Doc; compact?: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("resume");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (lineage) form.append("lineage_id", lineage.lineage_id);
      else {
        form.append("kind", kind);
        if (label) form.append("label", label);
      }
      await api("/documents", { form });
      setDone(true);
      setFile(null);
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (compact)
    return (
      <form onSubmit={submit} className="flex items-center gap-2">
        <label className="cursor-pointer text-sm text-indigo-700 underline">
          New version
          <input type="file" accept=".pdf,.docx,.txt" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {file && <Button type="submit" disabled={busy} className="!min-h-8 !px-2 !py-1">Upload {file.name}</Button>}
        {error ? <span className="text-xs text-red-700">{(error as Error).message}</span> : null}
      </form>
    );

  return (
    <Card title="Upload a document">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="File" hint="PDF, DOCX or TXT, up to 10 MB.">
          <input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
        </Field>
        <Field label="Type">
          <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="resume">Resume</option>
            <option value="cover_letter">Cover letter</option>
            <option value="other">Other</option>
          </select>
        </Field>
        <Field label="Label (optional)">
          <input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. General resume" />
        </Field>
        <div className="sm:col-span-3 space-y-2">
          <ErrorBox error={error} />
          {done && <Notice>Uploaded.</Notice>}
          <Button type="submit" disabled={!file || busy}>{busy ? "Uploading…" : "Upload"}</Button>
        </div>
      </form>
    </Card>
  );
}
