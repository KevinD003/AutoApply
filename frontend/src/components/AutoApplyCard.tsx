"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Button, Card, ErrorBox } from "@/components/ui";
import { api, AutoApplyState } from "@/lib/api";

// D113: your standing rule to apply automatically (backend app/modules/autoapply): whether it
// acts here, today's count against the cap, what it did for each job, and your pause switch.
export default function AutoApplyCard() {
  const [s, setS] = useState<AutoApplyState | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<AutoApplyState>("/auto-apply").then(setS).catch(setError);
  }, []);

  async function toggle(paused: boolean) {
    setError(null);
    try {
      setS(await api<AutoApplyState>("/auto-apply", { method: "PUT", json: { paused } }));
    } catch (e) {
      setError(e);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (!s) return null;
  return (
    <Card
      title="Automatic applying"
      actions={
        s.paused ? (
          <Button onClick={() => toggle(false)}>Resume</Button>
        ) : (
          <Button variant="secondary" onClick={() => toggle(true)}>
            Pause
          </Button>
        )
      }
    >
      <p className="mb-2 text-sm">
        {s.active ? (
          <Badge tone="green">On</Badge>
        ) : s.paused ? (
          <Badge tone="amber">Paused by you</Badge>
        ) : (
          <Badge tone="slate">Not acting here</Badge>
        )}{" "}
        {s.unavailable && !s.paused && <span className="text-slate-600">{s.unavailable.message}</span>}
      </p>
      <p className="mb-2 text-sm text-slate-600">
        Fully answered Greenhouse applications only; the first one to each employer is a rehearsal that never submits. Today:{" "}
        {s.approved_today} of {s.daily_cap}.
        {s.permission_attempts && (
          <>
            {" "}
            Your recorded permission: {s.permission_attempts.used} of {s.permission_attempts.of} attempts used.
          </>
        )}
      </p>
      {s.events.length > 0 && (
        <ul className="divide-y divide-slate-100 text-sm" aria-label="What automatic applying did">
          {s.events.map((e, i) => (
            <li key={i} className="py-2">
              <span className="text-slate-500">{new Date(e.at).toLocaleString()}</span> —{" "}
              {e.application_id ? (
                <Link className="text-indigo-700 underline" href={`/applications/${e.application_id}`}>
                  {e.job}
                </Link>
              ) : (
                <Link className="text-indigo-700 underline" href={`/jobs/${e.job_id}`}>
                  {e.job}
                </Link>
              )}
              : {e.text}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
