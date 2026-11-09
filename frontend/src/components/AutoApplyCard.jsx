"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Button, Card, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";

// D134: what pausing stopped of the rule's queued work (the pause's reply).
function stoppedNotice({ cancelled, stopped, in_flight: inFlight }) {
  const n = cancelled + stopped;
  const parts = [];
  if (n)
    parts.push(
      `Stopped ${n} application${n === 1 ? "" : "s"} it had queued, before sending.`,
    );
  if (inFlight) {
    parts.push(
      `${inFlight} ${inFlight === 1 ? "was" : "were"} already being sent and could not be stopped; the outcome shows on the Tracker.`,
    );
  }
  return parts.join(" ");
}

// D113: your standing rule to apply automatically (backend app/modules/autoapply): whether it
// acts here, today's count against the cap, what it did for each job, and your pause switch.
export default function AutoApplyCard() {
  const [s, setS] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/auto-apply").then(setS).catch(setError);
  }, []);

  async function toggle(paused) {
    setError(null);
    try {
      setS(await api("/auto-apply", { method: "PUT", json: { paused } }));
    } catch (e) {
      setError(e);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (!s) return null;
  return (
    <Card
      title="Automatically submit applications"
      actions={
        s.paused ? (
          <Button onClick={() => toggle(false)}>{s.chosen ? "Resume" : "Turn on"}</Button>
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
          <Badge tone="amber">{s.chosen ? "Paused by you" : "Off until you turn it on"}</Badge>
        ) : (
          <Badge tone="slate">Not acting here</Badge>
        )}{" "}
        {s.unavailable && !s.paused && <span className="text-ink-muted">{s.unavailable.message}</span>}
      </p>
      {s.paused && !s.chosen && <p className="mb-2 text-sm">{s.consent}</p>}
      {s.stopped && stoppedNotice(s.stopped) && (
        <p className="mb-2 text-sm" role="status">
          {stoppedNotice(s.stopped)}
        </p>
      )}
      <p className="mb-2 text-sm text-ink-muted">
        Fully answered Greenhouse applications only; the first one to each employer is a rehearsal that never submits.
        Pausing also stops what it queued that has not started sending; an application whose approval you revoke stays
        yours. Today: {s.approved_today} of {s.daily_cap}.
        {s.permission_attempts && (
          <>
            {" "}
            Your recorded permission: {s.permission_attempts.used} of {s.permission_attempts.of} attempts used.
          </>
        )}
      </p>
      {s.events.length > 0 && (
        <ul className="divide-y divide-hairline text-sm" aria-label="What automatic applying did">
          {s.events.map((e, i) => (
            <li key={i} className="py-2">
              <span className="text-ink-faint">{new Date(e.at).toLocaleString()}</span> —{" "}
              {e.application_id ? (
                <Link className="text-brand underline" href={`/applications/${e.application_id}`}>
                  {e.job}
                </Link>
              ) : (
                <Link className="text-brand underline" href={`/jobs/${e.job_id}`}>
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
