"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";

// D105: review several packages and approve the ones you tick, each on its own. A batch is only
// a list of single approvals: each names its package version and content hash as shown here and
// its own scope; nothing is approved by default, nothing is queued or sent.

type Scope = "submit" | "disclose_only";

interface ReviewItem {
  application_id: string;
  state: string;
  title: string;
  employer: string;
  destination: string;
  form_source: string;
  version: number;
  content_hash: string;
  answers: number;
  documents: number;
  blocked: string[];
  approval: { scope: Scope; expires_at: string; version: number } | null;
  rehearsal_prerequisite: { status: string; message: string; label: string };
}

interface ReviewList {
  items: ReviewItem[];
  max_items: number;
  approval_ttl_hours: number;
}

interface Result {
  application_id: string;
  version: number;
  status: "approved" | "refused" | "not_found";
  scope?: Scope;
  expires_at?: string;
  reason?: string;
}

const SCOPE_LABEL: Record<Scope, string> = {
  disclose_only: "Rehearsal: fill and check, never submit",
  submit: "Submit once",
};

export default function ReviewPage() {
  const [data, setData] = useState<ReviewList | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [picked, setPicked] = useState<Record<string, Scope | undefined>>({});
  const [results, setResults] = useState<Record<string, Result>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<ReviewList>("/review/packages")
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  const chosen = Object.entries(picked).filter(([, s]) => s) as [string, Scope][];

  async function approve() {
    if (!data || !chosen.length) return;
    setBusy(true);
    setError(null);
    try {
      const byId = Object.fromEntries(data.items.map((i) => [i.application_id, i]));
      const items = chosen.map(([id, scope]) => ({
        application_id: id,
        version: byId[id].version,
        content_hash: byId[id].content_hash,
        scope,
      }));
      const r = await api<{ results: Result[] }>("/review/approve", { json: { items } });
      setResults(Object.fromEntries(r.results.map((x) => [x.application_id, x])));
      setPicked({});
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Review and approve</h1>
      <p className="text-sm text-slate-600">
        Tick the packages you have reviewed and choose what each approval allows. Each is approved on its own, for the
        version shown, its application and its destination only, and expires after {data?.approval_ttl_hours ?? "—"}{" "}
        hours. Approving sends nothing: you still start each application from its page. A package that changed after
        this list was loaded is refused, never replaced. Nothing here approves future applications.
      </p>
      <ErrorBox error={error} />
      {data && data.items.length === 0 && <Empty>No package is waiting for your approval.</Empty>}
      {data && data.items.length > 0 && (
        <Card
          title={`${data.items.length} package(s) you can review`}
          actions={
            <Button onClick={approve} disabled={busy || chosen.length === 0 || chosen.length > data.max_items}>
              {`Approve the ${chosen.length} ticked package(s)`}
            </Button>
          }
        >
          <ul className="divide-y divide-slate-100">
            {data.items.map((i) => {
              const res = results[i.application_id];
              const scope = picked[i.application_id];
              const blocked = i.blocked.length > 0;
              const rehearseFirst = i.rehearsal_prerequisite.status === "unmet";
              return (
                <li key={i.application_id} className="py-3" data-testid="review-item">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <Link href={`/applications/${i.application_id}`} className="font-medium text-indigo-700 underline">
                        {i.title}
                      </Link>{" "}
                      <span className="text-sm text-slate-600">at {i.employer}</span>
                      <p className="text-xs text-slate-500">
                        Package v{i.version} · {i.answers} answer(s) · {i.documents} document(s) · {i.destination} ·{" "}
                        {i.form_source}
                      </p>
                      <p className="font-mono text-xs text-slate-400" title="The package's content hash">
                        {i.content_hash.slice(0, 12)}
                      </p>
                    </div>
                    {i.approval && (
                      <Badge tone="green">
                        {i.approval.scope === "submit" ? "Approved to submit" : "Approved for a rehearsal"}
                      </Badge>
                    )}
                  </div>
                  {blocked && (
                    <ul className="mt-1 list-disc pl-5 text-sm text-amber-800">
                      {i.blocked.map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  )}
                  {!blocked && !i.approval && (
                    <fieldset className="mt-2 flex flex-wrap gap-3 text-sm">
                      <legend className="sr-only">{`Approval for ${i.title}`}</legend>
                      {(["disclose_only", "submit"] as Scope[]).map((s) => (
                        <label key={s} className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={scope === s}
                            disabled={s === "submit" && rehearseFirst}
                            onChange={(e) =>
                              setPicked((p) => ({ ...p, [i.application_id]: e.target.checked ? s : undefined }))
                            }
                          />
                          {SCOPE_LABEL[s]}
                        </label>
                      ))}
                      {rehearseFirst && (
                        <span className="text-xs text-slate-500">{i.rehearsal_prerequisite.message}</span>
                      )}
                    </fieldset>
                  )}
                  {res && (
                    <p role="status" className={`mt-1 text-sm ${res.status === "approved" ? "text-emerald-700" : "text-red-700"}`}>
                      {res.status === "approved"
                        ? `Approved: ${SCOPE_LABEL[res.scope as Scope]}, until ${new Date(res.expires_at as string).toLocaleString()}`
                        : res.status === "not_found"
                          ? "Not found"
                          : `Not approved: ${res.reason}`}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
