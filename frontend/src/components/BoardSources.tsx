"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Notice } from "./ui";
import { api } from "@/lib/api";

// D95: public job boards you add (Greenhouse, Lever), read only when you press "Read now", or
// once a day for a board where you tick "Check daily" (D96).
// What the board says (listed or not), whether it is in your jobs, and how it matches you are
// shown apart; none of them is a way to apply.
interface Provider {
  key: string;
  label: string;
  identifier: string;
  regions: string[];
}
interface Source {
  id: string;
  provider: string;
  provider_label: string;
  region: string;
  board: string;
  employer: string;
  paused: boolean;
  daily_check: boolean;
  next_check_after: string | null;
  last_success_at: string | null;
  last_status: "ok" | "failed" | null;
  last_error: string | null;
  listed: number;
  no_longer_listed: number;
  in_your_jobs: number;
}
interface Posting {
  id: string;
  title: string | null;
  location: string | null;
  workplace: string | null;
  employment_type: string | null;
  job_url: string | null;
  source_lists_it: boolean;
  no_longer_listed_since: string | null;
  job_id: string | null;
  match: { label: string };
}
interface View {
  enabled: boolean;
  providers: Provider[];
  not_built: Record<string, string>;
  daily_check_limit: number;
  items: Source[];
}

export default function BoardSources() {
  const [v, setV] = useState<View | null>(null);
  const [provider, setProvider] = useState("greenhouse");
  const [region, setRegion] = useState("global");
  const [board, setBoard] = useState("");
  const [employer, setEmployer] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [posts, setPosts] = useState<Posting[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<View>("/discovery/sources").then(setV).catch(setError);
  }, []);
  useEffect(load, [load]);

  const showPostings = useCallback(async (id: string) => {
    setOpen(id);
    setPosts((await api<{ items: Posting[] }>(`/discovery/sources/${id}/postings`)).items);
  }, []);

  async function run(fn: () => Promise<string | void>) {
    setError(null);
    setNotice("");
    try {
      const msg = await fn();
      if (msg) setNotice(msg);
      load();
    } catch (e) {
      setError(e);
    }
  }

  if (!v) return <ErrorBox error={error} />;
  const spec = v.providers.find((p) => p.key === provider);
  return (
    <Card title="Employer job boards">
      <p className="text-sm text-slate-600">
        Add an employer&rsquo;s public job board and read it when you choose, or once a day if you tick &ldquo;Check daily&rdquo;. NoEfforts asks the provider&rsquo;s public postings
        feed for that one board, sends nothing of yours, and adds a posting to your jobs only when you save it.
      </p>
      {!v.enabled && <Notice>Reading job boards is not switched on for this NoEfforts. You can add boards; nothing is read.</Notice>}
      {Object.entries(v.not_built).map(([k, why]) => (
        <p key={k} className="mt-1 text-xs text-slate-500">
          {k[0].toUpperCase() + k.slice(1)}: not available. {why}
        </p>
      ))}
      <ErrorBox error={error} />
      {notice && <p className="mt-2 text-sm text-green-800" role="status">{notice}</p>}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="Provider">
          <select className={`${inputCls} sm:w-48`} value={provider} onChange={(e) => { setProvider(e.target.value); setRegion("global"); }}>
            {v.providers.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </Field>
        {spec && spec.regions.length > 1 && (
          <Field label="Region">
            <select className={`${inputCls} sm:w-28`} value={region} onChange={(e) => setRegion(e.target.value)}>
              {spec.regions.map((r) => <option key={r} value={r}>{r === "eu" ? "EU" : "Global"}</option>)}
            </select>
          </Field>
        )}
        <Field label={spec ? `Board (${spec.identifier})` : "Board"}>
          <input className={`${inputCls} sm:w-48`} value={board} onChange={(e) => setBoard(e.target.value)} />
        </Field>
        <Field label="Employer">
          <input className={`${inputCls} sm:w-56`} value={employer} onChange={(e) => setEmployer(e.target.value)} />
        </Field>
        <Button
          disabled={!board || !employer}
          onClick={() => run(async () => {
            await api("/discovery/sources", { json: { provider, region, board, employer } });
            setBoard("");
            setEmployer("");
            return "Board added. Press “Read now” to read it.";
          })}
        >
          Add board
        </Button>
      </div>
      {v.items.length === 0 ? (
        <Empty>No job boards yet.</Empty>
      ) : (
        <ul className="mt-4 divide-y divide-slate-100">
          {v.items.map((s) => (
            <li key={s.id} className="space-y-1 py-3 text-sm" data-testid="board-source">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{s.employer}</span>
                <Badge>{s.provider_label}{s.region === "eu" ? " (EU)" : ""}</Badge>
                {s.paused && <Badge tone="slate">paused</Badge>}
                {s.daily_check && !s.paused && <Badge tone="indigo">checked daily</Badge>}
                {s.last_status === "failed" && <Badge tone="red">last read failed</Badge>}
              </div>
              <p className="text-slate-600">
                {s.last_success_at ? `Last read ${new Date(s.last_success_at).toLocaleString()} · ` : "Not read yet · "}
                {s.listed} listed · {s.no_longer_listed} no longer listed · {s.in_your_jobs} in your jobs
              </p>
              {s.last_status === "failed" && s.last_error && <p className="text-xs text-red-700">{s.last_error}</p>}
              {s.daily_check && s.next_check_after && v.enabled && (
                <p className="text-xs text-slate-500">Next daily check after {new Date(s.next_check_after).toLocaleString()}</p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!v.enabled || s.paused}
                  onClick={() => run(async () => {
                    const r = await api<{ status: string; listed: number; message?: string }>(`/discovery/sources/${s.id}/sync`, { method: "POST" });
                    if (open === s.id) await showPostings(s.id);
                    return r.status === "ok" ? `Read: ${r.listed} listed.` : `Not read: ${r.message ?? "the read failed"} Nothing was changed.`;
                  })}
                >
                  Read now
                </Button>
                <Button variant="secondary" onClick={() => run(async () => { await showPostings(s.id); })}>Show postings</Button>
                <Button variant="secondary" onClick={() => run(async () => { await api(`/discovery/sources/${s.id}`, { method: "PATCH", json: { paused: !s.paused } }); })}>
                  {s.paused ? "Resume" : "Pause"}
                </Button>
                <label className="flex min-h-10 items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={s.daily_check}
                    onChange={(e) => run(async () => {
                      await api(`/discovery/sources/${s.id}`, { method: "PATCH", json: { daily_check: e.target.checked } });
                      return e.target.checked
                        ? "This board will be read once a day; new postings appear in your notifications."
                        : "Daily check off. The board is read only when you press “Read now”.";
                    })}
                  />
                  Check daily
                </label>
                <Button
                  variant="danger"
                  onClick={() => run(async () => {
                    await api(`/discovery/sources/${s.id}`, { method: "DELETE" });
                    if (open === s.id) setOpen(null);
                    return "Board removed. Jobs you saved from it stay in your jobs.";
                  })}
                >
                  Remove
                </Button>
              </div>
              {open === s.id && (
                <ul className="mt-2 space-y-2 border-l-2 border-slate-200 pl-3" aria-label="Postings">
                  {posts.length === 0 && <li className="text-slate-500">No postings read yet.</li>}
                  {posts.map((p) => (
                    <li key={p.id} data-testid="board-posting">
                      <span className="font-medium">{p.title ?? "Untitled posting"}</span>{" "}
                      <span className="text-slate-600">
                        {[p.location, p.workplace !== "unknown" ? p.workplace : null, p.employment_type].filter(Boolean).join(" · ")}
                      </span>
                      <span className="block text-xs">
                        <Badge tone={p.source_lists_it ? "green" : "slate"}>
                          {p.source_lists_it ? "Source lists it" : `No longer listed by the board since ${new Date(p.no_longer_listed_since!).toLocaleDateString()}`}
                        </Badge>{" "}
                        <span className="text-slate-500">Match: {p.match.label}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap gap-3 text-xs">
                        {p.job_url && (
                          <a className="text-indigo-700 underline" href={p.job_url} target="_blank" rel="noopener noreferrer nofollow">
                            Posting at the source
                          </a>
                        )}
                        {p.job_id ? (
                          <Link className="text-indigo-700 underline" href={`/jobs/${p.job_id}`}>In your jobs</Link>
                        ) : (
                          <button
                            className="text-indigo-700 underline"
                            onClick={() => run(async () => {
                              await api(`/discovery/sources/postings/${p.id}/save`, { method: "POST" });
                              await showPostings(s.id);
                              return "Saved to your jobs.";
                            })}
                          >
                            Save to my jobs
                          </button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
