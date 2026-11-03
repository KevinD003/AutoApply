"use client";

import { useEffect, useState } from "react";

import { Badge, Card, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";

// D111 §5: what a disclosure-only rehearsal on the employer's real Greenhouse page would
// disclose, how it stops before submitting, and which prerequisites hold now (backend
// execution/handoff.py). It reads only and grants nothing; every gate checks again.
export default function RehearsalHandoff({ appId, refreshKey }) {
  const [h, setH] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/applications/${appId}/rehearsal-handoff`).then(setH).catch(setError);
  }, [appId, refreshKey]);

  if (error) return <ErrorBox error={error} />;
  if (!h) return null;
  const real = h.prerequisites.some((p) => p.code === "greenhouse_posting" && p.met);
  if (!real && h.destination.form_source !== "greenhouse_live") return null;

  return (
    <Card title="Rehearsal on the employer's real page (milestone B)">
      <p className="mb-3 text-sm">
        {h.ready ? (
          <Badge tone="green">Every prerequisite holds</Badge>
        ) : (
          <Badge tone="amber">{h.outstanding.length} prerequisite(s) outstanding</Badge>
        )}{" "}
        <span className="text-ink-muted">{h.not_a_permission}</span>
      </p>
      <details className="mb-3" open={!h.ready}>
        <summary className="cursor-pointer text-sm font-medium">Prerequisites</summary>
        <ul className="mt-2 space-y-1 text-sm" aria-label="Prerequisites">
          {h.prerequisites.map((p) => (
            <li key={p.code} className="flex flex-wrap items-baseline gap-2">
              <Badge tone={p.met ? "green" : "amber"}>{p.met ? "holds" : "outstanding"}</Badge>
              <span>{p.label}</span>
              {p.detail && <span className="text-ink-faint">({p.detail})</span>}
            </li>
          ))}
          <li className="flex flex-wrap items-baseline gap-2">
            <Badge tone="slate">separate</Badge>
            <span>{h.submit_permission.label}</span>
            <span className="text-ink-faint">({h.submit_permission.met ? "recorded" : "not recorded"}; {h.submit_permission.detail})</span>
          </li>
        </ul>
      </details>
      <details className="mb-3">
        <summary className="cursor-pointer text-sm font-medium">What filling and uploading would disclose ({h.will_disclose.length})</summary>
        <ul className="mt-2 space-y-1 text-sm">
          {h.will_disclose.map((w) => (
            <li key={w.key}>
              <span className="font-medium">{w.label}</span>: {w.display ?? "—"} <span className="text-ink-faint">({w.how})</span>
            </li>
          ))}
        </ul>
        {h.not_disclosed.length > 0 && <p className="mt-2 text-sm text-ink-muted">Not entered: {h.not_disclosed.length} question(s), as your package shows.</p>}
        <ul className="mt-2 list-disc pl-5 text-sm text-ink-muted">
          {h.exposure.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      </details>
      <details className="mb-3">
        <summary className="cursor-pointer text-sm font-medium">How it stops before submitting</summary>
        <ul className="mt-2 list-disc pl-5 text-sm">
          {h.stop_before_submit.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </details>
      <details>
        <summary className="cursor-pointer text-sm font-medium">The evidence a rehearsal leaves</summary>
        <ul className="mt-2 list-disc pl-5 text-sm">
          {h.expected_evidence.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      </details>
    </Card>
  );
}
