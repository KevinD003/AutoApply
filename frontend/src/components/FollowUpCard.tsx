"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, ErrorBox, inputCls } from "@/components/ui";
import { api, FollowUp, NOTIFICATIONS_CHANGED } from "@/lib/api";

// D92: when to check on an application you submitted, and a message to copy. Derived from the
// application's own records (backend followups/service.py); NoEfforts sends nothing itself.
const STATUS: Record<FollowUp["status"], { label: string; tone: "slate" | "green" | "amber" | "red" | "indigo" }> = {
  not_submitted: { label: "Nothing to follow up yet", tone: "slate" },
  scheduled: { label: "Follow-up scheduled", tone: "indigo" },
  due: { label: "Time to follow up", tone: "amber" },
  stopped: { label: "Reminders stopped", tone: "slate" },
  closed: { label: "Closed by the outcome you recorded", tone: "slate" },
};

function day(iso: string | null | undefined) {
  return iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }) : "";
}

export default function FollowUpCard({
  appId,
  refreshKey,
  hideUntilSubmitted = false,
}: {
  appId: string;
  refreshKey?: string | number;
  hideUntilSubmitted?: boolean;
}) {
  const [f, setF] = useState<FollowUp | null>(null);
  const [remindOn, setRemindOn] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<FollowUp>(`/applications/${appId}/follow-up`).then(setF).catch(setError);
  }, [appId]);
  useEffect(load, [load, refreshKey]);

  async function act(action: "done" | "remind" | "stop" | "resume") {
    setError(null);
    try {
      setF(await api<FollowUp>(`/applications/${appId}/follow-up`, { json: { action, ...(action === "remind" ? { remind_on: remindOn } : {}) } }));
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
    } catch (e) {
      setError(e);
    }
  }

  async function copy() {
    if (!f?.draft) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${f.draft.subject}\n\n${f.draft.body}`);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  if (!f) return <ErrorBox error={error} />;
  if (hideUntilSubmitted && f.status === "not_submitted") return null;
  const s = STATUS[f.status];
  return (
    <section aria-label="Follow-up" className="mb-3 rounded-lg border border-slate-200 p-3 text-sm">
      <h3 className="mb-2 font-semibold">Follow-up</h3>
      <ErrorBox error={error} />
      <p className="flex flex-wrap items-center gap-2">
        <Badge tone={s.tone}>{s.label}</Badge>
        {(f.status === "scheduled" || f.status === "due") && <span data-testid="follow-up-due">{f.status === "due" ? "Due" : "On"} {day(f.due_on)}</span>}
      </p>
      {f.status === "not_submitted" && (
        <p className="mt-2 text-slate-600">Once this application is submitted (or you record that you applied yourself), NoEfforts reminds you to check on it.</p>
      )}
      {f.status !== "not_submitted" && (
        <p className="mt-2 text-slate-600">
          Submitted {day(f.submitted_on)}
          {f.followed_up_on && <> · you followed up {day(f.followed_up_on)}</>}. Reminders come {f.days} days after you applied, after you
          last followed up, or after an interview or assessment you recorded, and stop once an outcome closes the application.
        </p>
      )}
      {(f.status === "scheduled" || f.status === "due") && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Button onClick={() => act("done")}>I followed up</Button>
          <label className="flex flex-col">
            <span className="mb-1 text-xs font-medium">Remind me on</span>
            <input type="date" aria-label="Remind me on" className={`${inputCls} sm:w-44`} value={remindOn} onChange={(e) => setRemindOn(e.target.value)} />
          </label>
          <Button variant="secondary" disabled={!remindOn} onClick={() => act("remind")}>Set reminder</Button>
          <Button variant="secondary" onClick={() => act("stop")}>Stop reminders</Button>
        </div>
      )}
      {f.status === "stopped" && (
        <div className="mt-3">
          <Button variant="secondary" onClick={() => act("resume")}>Resume reminders</Button>
        </div>
      )}
      {f.draft && f.status !== "closed" && (
        <details className="mt-3">
          <summary className="cursor-pointer text-indigo-700 underline">A message you can copy</summary>
          <p className="mt-2 text-xs text-slate-500">
            NoEfforts never sends it. It uses the job, the day you applied{f.draft.name_missing ? "" : " and your name from your profile"}, nothing else.
            {f.draft.name_missing && " Add your name in your profile, or replace “[Your name]”."}
          </p>
          <p className="mt-2 font-medium" data-testid="follow-up-subject">Subject: {f.draft.subject}</p>
          <pre className="mt-1 whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-sans" data-testid="follow-up-body">{f.draft.body}</pre>
          <Button variant="secondary" onClick={copy}>{copied ? "Copied" : "Copy message"}</Button>
        </details>
      )}
    </section>
  );
}
