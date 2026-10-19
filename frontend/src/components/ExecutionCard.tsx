"use client";

import { useCallback, useEffect, useState } from "react";

import { api, AttemptView } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, inputCls, Notice } from "./ui";

const STATE: Record<string, { label: string; tone: "green" | "amber" | "red" | "indigo" | "slate" }> = {
  pending: { label: "Waiting for a worker", tone: "indigo" },
  claimed: { label: "Filling the form", tone: "indigo" },
  sending: { label: "Submitting", tone: "amber" },
  awaiting_code: { label: "Needs your verification code", tone: "amber" },
  confirmed: { label: "Employer receipt received", tone: "green" },
  unknown: { label: "Outcome unknown — check before doing anything", tone: "red" },
  rejected: { label: "Refused by the employer's form", tone: "red" },
  failed_safe: { label: "Stopped before sending anything", tone: "slate" },
  abandoned: { label: "Stopped after entering data, not submitted", tone: "amber" },
  cancelled: { label: "Cancelled", tone: "slate" },
};

export default function ExecutionCard({ appId, appState, approved, onChange }: { appId: string; appState: string; approved: boolean; onChange: () => void }) {
  const [attempts, setAttempts] = useState<AttemptView[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");

  const load = useCallback(() => {
    api<AttemptView[]>(`/applications/${appId}/attempts`).then(setAttempts).catch(setError);
  }, [appId]);

  useEffect(() => {
    load();
    const active = attempts.some((a) => ["pending", "claimed", "sending", "awaiting_code"].includes(a.state));
    if (!active) return;
    const t = setInterval(() => {
      load();
      onChange();
    }, 3000);
    return () => clearInterval(t);
  }, [load, onChange, attempts]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setError(null);
    setNotice("");
    try {
      await fn();
      setNotice(ok);
      load();
      onChange();
    } catch (e) {
      setError(e);
    }
  }

  const openCp = attempts.flatMap((a) => a.checkpoints).find((c) => c.status === "open");

  return (
    <Card title="Submission">
      <p className="mb-3 text-sm text-slate-600">
        Automatic submission works only for local test forms (fictional employers) in this version. For real employers, apply on their site
        and record it in the tracker.
      </p>
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      <div className="my-3 flex flex-wrap gap-2">
        {appState === "awaiting_approval" && (
          <Button disabled={!approved} onClick={() => act(() => api(`/applications/${appId}/transition`, { json: { to: "queued" } }), "Queued.")}>
            Submit approved package
          </Button>
        )}
        {["queued", "running", "needs_user_action"].includes(appState) && (
          <Button variant="danger" onClick={() => act(() => api(`/applications/${appId}/cancel`, { method: "POST" }), "Cancelled.")}>
            Cancel
          </Button>
        )}
      </div>
      {openCp && (
        <form
          className="mb-4 space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            act(() => api(`/applications/${appId}/checkpoints/${openCp.id}/code`, { json: { round: openCp.round, code } }), "Code sent to the worker.").then(() => setCode(""));
          }}
        >
          <p className="font-medium text-amber-900">{openCp.message ?? "Enter the verification code the employer sent you."}</p>
          <p className="text-xs text-amber-900">
            Attempt {openCp.wrong_attempts + 1} of {openCp.max_attempts} · expires {new Date(openCp.expires_at).toLocaleTimeString()}
          </p>
          <label className="block">
            <span className="mb-1 block">Verification code</span>
            <input className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="numeric" />
          </label>
          <Button type="submit" disabled={!code.trim()}>
            Send code
          </Button>
        </form>
      )}
      {attempts.length === 0 ? (
        <p className="text-sm text-slate-600">No submission attempts yet.</p>
      ) : (
        <ul className="space-y-3">
          {attempts.map((a) => {
            const s = STATE[a.state] ?? { label: a.state, tone: "slate" as const };
            const receipt = a.evidence.find((e) => e.kind === "receipt");
            return (
              <li key={a.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <Badge tone={s.tone}>{s.label}</Badge>
                  <span className="text-xs text-slate-500">{new Date(a.created_at).toLocaleString()}</span>
                </p>
                {a.outcome && <p className="mt-1">{a.outcome}</p>}
                {receipt && (
                  <p className="mt-1">
                    Receipt <code>{String(receipt.data.receipt_id)}</code> from {String(receipt.data.final_origin)}
                  </p>
                )}
                <p className="mt-1 text-xs text-slate-500">
                  {a.disclosure_started_at ? "Data entered on the employer's form. " : "Nothing entered yet. "}
                  {a.send_started_at ? "Submit step started." : ""}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
