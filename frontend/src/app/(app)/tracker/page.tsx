"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, inputCls, Loading } from "@/components/ui";
import { api, Application } from "@/lib/api";

const LABEL: Record<string, string> = {
  draft: "Draft",
  preparing: "Preparing",
  awaiting_approval: "Awaiting your approval",
  queued: "Queued",
  running: "Running",
  needs_user_action: "Needs your action",
  ready_to_submit: "Ready to submit",
  submitting: "Submitting",
  submitted_confirmed: "Submitted (confirmed)",
  submitted_unconfirmed: "Submitted (not confirmed)",
  failed_retryable: "Failed (can retry)",
  failed_terminal: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
};

// User-performable actions per state; the server enforces the same rules.
const ACTIONS: Record<string, { to: string; label: string; reason?: string }[]> = {
  draft: [
    { to: "submitted_unconfirmed", label: "I applied myself", reason: "User reported a manual submission" },
    { to: "cancelled", label: "Cancel" },
  ],
  awaiting_approval: [{ to: "cancelled", label: "Cancel" }],
  needs_user_action: [{ to: "cancelled", label: "Cancel" }],
};

const OUTCOMES = ["none", "interviewing", "offer", "rejected", "withdrawn", "no_response"];

function tone(state: string) {
  if (state === "submitted_confirmed") return "green";
  if (state.startsWith("failed") || state === "cancelled" || state === "expired") return "red";
  if (state === "needs_user_action" || state === "awaiting_approval" || state === "submitted_unconfirmed") return "amber";
  return "indigo";
}

function Tracker() {
  const highlight = useSearchParams().get("highlight");
  const [apps, setApps] = useState<Application[] | null>(null);
  const [open, setOpen] = useState<Application | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Application[]>("/applications").then(setApps).catch((e) => {
      setError(e);
      setApps([]);
    });
  }, []);
  useEffect(load, [load]);

  const show = useCallback(async (id: string) => {
    try {
      setOpen(await api<Application>(`/applications/${id}`));
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    if (highlight) show(highlight);
  }, [highlight, show]);

  async function act(id: string, to: string, reason?: string) {
    setError(null);
    try {
      setOpen(await api<Application>(`/applications/${id}/transition`, { json: { to, reason } }));
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function setOutcome(id: string, outcome: string) {
    try {
      setOpen(await api<Application>(`/applications/${id}`, { method: "PATCH", json: { outcome } }));
      load();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Application tracker</h1>
      <ErrorBox error={error} />
      {open && (
        <Card
          title={`${open.job.title ?? "Untitled"} — ${open.job.employer ?? ""}`}
          actions={<Button variant="secondary" onClick={() => setOpen(null)}>Close</Button>}
        >
          <p className="mb-3 text-sm">
            Status: <Badge tone={tone(open.state)}>{LABEL[open.state] ?? open.state}</Badge>
          </p>
          {!["draft", "submitted_confirmed", "submitted_unconfirmed", "cancelled"].includes(open.state) && (
            <p className="mb-3 text-sm">
              <Link className="text-indigo-700 underline" href={`/applications/${open.id}`}>
                Open the application review
              </Link>
            </p>
          )}
          {open.state === "submitted_unconfirmed" && <Reconcile appId={open.id} onDone={setOpen} />}
          <div className="mb-3 flex flex-wrap gap-2">
            {(ACTIONS[open.state] ?? []).map((a) => (
              <Button key={a.to} variant={a.to === "cancelled" ? "danger" : "secondary"} onClick={() => act(open.id, a.to, a.reason)}>
                {a.label}
              </Button>
            ))}
          </div>
          <label className="mb-4 block text-sm">
            <span className="mb-1 block font-medium">Outcome</span>
            <select className={`${inputCls} sm:w-60`} value={open.outcome} onChange={(e) => setOutcome(open.id, e.target.value)}>
              {OUTCOMES.map((o) => (
                <option key={o} value={o}>{o.replace("_", " ")}</option>
              ))}
            </select>
          </label>
          <h3 className="mb-2 text-sm font-semibold">Timeline</h3>
          <ol className="space-y-2 border-l-2 border-slate-200 pl-4 text-sm">
            {open.events?.map((e, i) => (
              <li key={i}>
                <span className="text-slate-500">{new Date(e.created_at).toLocaleString()}</span> —{" "}
                {e.kind === "state_change" ? `${e.from_state ? LABEL[e.from_state] + " → " : ""}${LABEL[e.to_state ?? ""]}` : e.reason}
                {e.kind === "state_change" && e.reason && <span className="text-slate-500"> ({e.reason})</span>}
                <span className="text-xs text-slate-400"> by {e.actor}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}
      <Card title="All applications">
        {apps === null ? (
          <Loading />
        ) : apps.length === 0 ? (
          <Empty>Nothing tracked yet. Open a job and choose “Track application”.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {apps.map((a) => (
              <li key={a.id}>
                <button onClick={() => show(a.id)} className="flex w-full flex-col gap-1 py-3 text-left hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between sm:px-2">
                  <span>
                    <span className="block font-medium">{a.job.title ?? "Untitled"}</span>
                    <span className="block text-sm text-slate-600">{a.job.employer}</span>
                  </span>
                  <span className="flex gap-2">
                    {a.outcome !== "none" && <Badge>{a.outcome.replace("_", " ")}</Badge>}
                    {a.last_attempt?.state === "rehearsed" && <Badge tone="indigo">Rehearsal finished: nothing submitted</Badge>}
                    <Badge tone={tone(a.state)}>{LABEL[a.state] ?? a.state}</Badge>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function Reconcile({ appId, onDone }: { appId: string; onDone: (a: Application) => void }) {
  const [evidence, setEvidence] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function send(finding: "received" | "not_received") {
    setError(null);
    try {
      onDone(
        await api<Application>(`/applications/${appId}/reconcile`, {
          json: { finding, evidence, confirm_not_received: confirm },
        }),
      );
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="mb-4 space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
      <p className="font-medium text-amber-900">
        We do not know whether the employer received this. Check before doing anything else — there is no one-click resubmit.
      </p>
      <label className="block">
        <span className="mb-1 block">What did you check?</span>
        <textarea
          className={inputCls}
          rows={2}
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
          placeholder="e.g. Found confirmation email ref 1234 / Called HR on 3 May, nothing on file"
        />
      </label>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />I checked and the employer did not receive it
      </label>
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={evidence.trim().length < 15} onClick={() => send("received")}>
          It was received
        </Button>
        <Button variant="secondary" disabled={evidence.trim().length < 15 || !confirm} onClick={() => send("not_received")}>
          It was not received
        </Button>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Tracker />
    </Suspense>
  );
}
