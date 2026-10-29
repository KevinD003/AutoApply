"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice } from "@/components/ui";
import { api, Doc } from "@/lib/api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [versions, setVersions] = useState<Record<string, Doc[]>>({});
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [preview, setPreview] = useState<Record<string, { text: string; truncated: boolean } | { error: unknown }>>({});

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

  // Priority C (D78): the text NoEfforts reads from the file, shown as plain text only. The file
  // itself is never rendered here (no PDF viewer, no HTML), and nothing is fetched from elsewhere.
  async function togglePreview(d: Doc) {
    if (preview[d.id]) {
      setPreview((cur) => {
        const next = { ...cur };
        delete next[d.id];
        return next;
      });
      return;
    }
    try {
      const p = await api<{ text: string; truncated: boolean }>(`/documents/${d.id}/preview`);
      setPreview((cur) => ({ ...cur, [d.id]: p }));
    } catch (e) {
      setPreview((cur) => ({ ...cur, [d.id]: { error: e } }));
    }
  }

  // C17 (D70): a version, or every version, is deleted with its file; refused while an approved
  // package or a submission in progress needs it.
  async function remove(d: Doc, scope: "version" | "lineage") {
    setError(null);
    setNotice("");
    setConfirming(null);
    try {
      await api(`/documents/${d.id}?scope=${scope}`, { method: "DELETE" });
      setNotice(scope === "lineage" ? `Deleted “${d.label}” and all its versions.` : `Deleted version ${d.version} of “${d.label}”.`);
      setVersions((cur) => {
        const next = { ...cur };
        delete next[d.lineage_id];
        return next;
      });
      load();
    } catch (e) {
      setError(e);
    }
  }

  // L1 (D72): what this resume states becomes proposed profile facts, used only once approved.
  async function propose(d: Doc) {
    setError(null);
    setNotice("");
    try {
      const r = await api<{ proposed: Record<string, number>; skipped: { existing: number; sensitive: number } }>(
        `/documents/${d.id}/propose-facts`,
        { method: "POST" },
      );
      const p = r.proposed;
      setNotice(
        `Proposed from “${d.label}”: ${p.employment} work ${p.employment === 1 ? "entry" : "entries"}, ${p.education} education ` +
          `${p.education === 1 ? "entry" : "entries"}, ${p.credential} licence${p.credential === 1 ? "" : "s"} or certification${p.credential === 1 ? "" : "s"}. ` +
          `Review and approve them in your profile; nothing is used until you do.` +
          (r.skipped.existing ? ` ${r.skipped.existing} already in your profile.` : "") +
          (r.skipped.sensitive ? ` ${r.skipped.sensitive} line${r.skipped.sensitive === 1 ? "" : "s"} about legal status or a personal topic not read.` : ""),
      );
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
        {notice && <Notice>{notice}</Notice>}
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
                    <button className="text-sm text-indigo-700 underline" aria-expanded={!!preview[d.id]} onClick={() => togglePreview(d)}>
                      {preview[d.id] ? "Hide text" : "Preview text"}
                    </button>
                    {d.version > 1 && (
                      <button className="text-sm text-indigo-700 underline" onClick={() => showVersions(d)}>History</button>
                    )}
                    <Upload compact lineage={d} onDone={load} />
                    {d.kind === "resume" && (
                      <button className="text-sm text-indigo-700 underline" onClick={() => propose(d)}>
                        Propose profile facts
                      </button>
                    )}
                    {confirming === d.lineage_id ? (
                      <span className="flex items-center gap-2 text-sm">
                        Delete this document, every version and its files?
                        <button className="text-red-700 underline" onClick={() => remove(d, "lineage")}>
                          Yes, delete
                        </button>
                        <button className="text-slate-600 underline" onClick={() => setConfirming(null)}>
                          Keep it
                        </button>
                      </span>
                    ) : (
                      <button className="text-sm text-red-700 underline" onClick={() => setConfirming(d.lineage_id)}>
                        Delete
                      </button>
                    )}
                  </div>
                </div>
                {preview[d.id] &&
                  ("error" in preview[d.id] ? (
                    <div className="mt-2">
                      <ErrorBox error={(preview[d.id] as { error: unknown }).error} />
                    </div>
                  ) : (
                    <figure className="mt-2">
                      <pre
                        aria-label={`Text of ${d.label}`}
                        className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800"
                      >
                        {(preview[d.id] as { text: string }).text}
                      </pre>
                      <figcaption className="mt-1 text-xs text-slate-500">
                        The text NoEfforts reads from this file, as plain text; layout and images are not shown.
                        {(preview[d.id] as { truncated: boolean }).truncated && " Only the beginning is shown."}
                      </figcaption>
                    </figure>
                  ))}
                {versions[d.lineage_id] && (
                  <ul className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2 text-sm">
                    {versions[d.lineage_id].map((v) => (
                      <li key={v.id}>
                        v{v.version} — {new Date(v.created_at).toLocaleString()} —{" "}
                        <a className="text-indigo-700 underline" href={`/api/documents/${v.id}/download`}>download</a>
                        {" — "}
                        <button className="text-red-700 underline" onClick={() => remove(v, "version")}>
                          delete this version
                        </button>
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
