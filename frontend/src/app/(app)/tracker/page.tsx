"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, inputCls, Loading } from "@/components/ui";
import { api, Application, Funnel, Outcome } from "@/lib/api";

// Neutral state names (the timeline); the badges say what a submission rests on (stateLabel).
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

const OUTCOME_LABEL: Record<Outcome, string> = {
  none: "No outcome yet",
  assessment_received: "Assessment received",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Employer declined",
  withdrawn: "Withdrawn",
  no_response: "No response",
};

const STAGE_LABEL: Record<string, string> = {
  prepared: "Prepared",
  approved: "Approved (to submit or to rehearse)",
  disclosed: "Data entered on an employer's form",
  form_rejected: "Form rejected (the employer's form refused it)",
  submitted: "Submitted",
  responded: "Any response",
  assessment_received: "Assessment received",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Employer declined",
  no_response: "No response (you marked it)",
  withdrawn: "Withdrawn after submitting",
  withdrawn_before_submission: "Withdrawn before submitting",
};

const OF_LABEL: Record<string, string> = {
  tracked: "tracked",
  prepared: "prepared",
  approved: "approved",
  disclosed: "with data entered",
  submitted: "submitted",
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

// A submission NoEfforts is still handling: recording Withdrawn does not stop it.
const IN_PROGRESS = ["queued", "running", "ready_to_submit", "submitting"];

function stateLabel(a: Application) {
  if (a.state === "submitted_confirmed") {
    return a.submission === "receipt" ? "Submitted (employer receipt)" : "Submitted (confirmed by you)";
  }
  if (a.state === "submitted_unconfirmed") {
    if (a.submission === "receipt") return "Receipt recorded: confirm it below";
    if (a.submission === "user_claimed") return "Applied by you (not confirmed)";
    return "Submitted (not confirmed)";
  }
  if (a.state === "failed_terminal" && a.last_attempt?.state === "rejected") return "Form rejected";
  return LABEL[a.state] ?? a.state;
}

function tone(a: Application) {
  if (a.submission === "receipt") return "green";
  if (a.submission === "user_claimed") return "indigo";
  if (a.state.startsWith("failed") || a.state === "cancelled" || a.state === "expired") return "red";
  if (a.state === "needs_user_action" || a.state === "awaiting_approval" || a.state === "submitted_unconfirmed") return "amber";
  return "indigo";
}

type AppEvent = NonNullable<Application["events"]>[number];

function eventLine(e: AppEvent) {
  if (e.kind === "state_change") {
    const by = e.source === "receipt" ? " · employer receipt" : e.source === "user_claimed" ? " · your statement" : "";
    return `${e.from_state ? LABEL[e.from_state] + " → " : ""}${LABEL[e.to_state ?? ""]}${by}`;
  }
  if (e.kind === "outcome" && e.from_outcome && e.to_outcome) {
    const when = e.occurred_on ? ` · happened on ${e.occurred_on}` : "";
    return `Outcome: ${OUTCOME_LABEL[e.from_outcome]} → ${OUTCOME_LABEL[e.to_outcome]}${when} · you reported`;
  }
  if (e.kind === "outcome") return `${e.reason} · recorded before sources were kept`;
  return e.reason ?? "";
}

function Tracker() {
  const highlight = useSearchParams().get("highlight");
  const [apps, setApps] = useState<Application[] | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [open, setOpen] = useState<Application | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Application[]>("/applications").then(setApps).catch((e) => {
      setError(e);
      setApps([]);
    });
    api<Funnel>("/applications/funnel").then(setFunnel).catch(() => setFunnel(null));
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

  function done(a: Application) {
    setOpen(a);
    load();
  }

  async function act(id: string, to: string, reason?: string) {
    setError(null);
    try {
      done(await api<Application>(`/applications/${id}/transition`, { json: { to, reason } }));
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
            Status: <Badge tone={tone(open)}>{stateLabel(open)}</Badge>
          </p>
          {open.state !== "draft" && (
            // Also after submitting: the review page holds the package that was sent and its receipt.
            <p className="mb-3 text-sm">
              <Link className="text-indigo-700 underline" href={`/applications/${open.id}`}>
                {open.state.startsWith("submitted") ? "Open the application (what was sent, and its receipt)" : "Open the application review"}
              </Link>
            </p>
          )}
          {open.state === "submitted_unconfirmed" && (
            <Reconcile key={open.id} appId={open.id} receipt={open.submission === "receipt"} onDone={done} />
          )}
          <div className="mb-3 flex flex-wrap gap-2">
            {(ACTIONS[open.state] ?? []).map((a) => (
              <Button key={a.to} variant={a.to === "cancelled" ? "danger" : "secondary"} onClick={() => act(open.id, a.to, a.reason)}>
                {a.label}
              </Button>
            ))}
          </div>
          <OutcomeForm key={`${open.id}-${open.outcome}-${open.events?.length ?? 0}`} app={open} onDone={done} />
          <h3 className="mb-2 text-sm font-semibold">Timeline</h3>
          <ol className="space-y-2 border-l-2 border-slate-200 pl-4 text-sm">
            {open.events?.map((e, i) => (
              <li key={i} className="min-w-0 break-words">
                <span className="text-slate-500">{new Date(e.created_at).toLocaleString()}</span> —{" "}
                <span data-testid="event-line">{eventLine(e)}</span>
                {e.kind === "state_change" && e.reason && <span className="text-slate-500"> ({e.reason})</span>}
                <span className="text-xs text-slate-400"> by {e.actor}</span>
                {e.evidence_note && (
                  <span className="block text-slate-500">
                    {e.kind === "outcome" ? `Note: ${e.evidence_note}` : `What you checked: ${e.evidence_note}`}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </Card>
      )}
      {funnel && <FunnelCard f={funnel} />}
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
                  <span className="min-w-0">
                    <span className="block font-medium">{a.job.title ?? "Untitled"}</span>
                    <span className="block text-sm text-slate-600">{a.job.employer}</span>
                  </span>
                  <span className="flex flex-wrap gap-2">
                    {a.outcome !== "none" && <Badge>{OUTCOME_LABEL[a.outcome]}</Badge>}
                    {!a.reached_submission && a.outcome !== "none" && a.outcome !== "withdrawn" && (
                      <Badge>Recorded before it was submitted</Badge>
                    )}
                    {a.last_attempt?.state === "rehearsed" && <Badge tone="indigo">Rehearsal finished: nothing submitted</Badge>}
                    <Badge tone={tone(a)}>{stateLabel(a)}</Badge>
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

function OutcomeForm({ app, onDone }: { app: Application; onDone: (a: Application) => void }) {
  const choices = app.outcome_choices ?? [];
  const options = choices.includes(app.outcome) ? choices : [app.outcome, ...choices];
  const [outcome, setOutcome] = useState<Outcome>(app.outcome);
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const sentDate = outcome !== "none" ? date : ""; // only the date on screen is sent
  const changed = outcome !== app.outcome || sentDate !== "" || note.trim() !== "";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api<Application>(`/applications/${app.id}`, {
          method: "PATCH",
          json: { outcome, occurred_on: sentDate || undefined, evidence_note: note.trim() || undefined },
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 space-y-2 text-sm">
      <label className="block">
        <span className="mb-1 block font-medium">Outcome</span>
        <select className={`${inputCls} sm:w-60`} value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome)}>
          {options.map((o) => (
            <option key={o} value={o}>
              {OUTCOME_LABEL[o]}
            </option>
          ))}
        </select>
      </label>
      {!choices.includes("interviewing") && (
        <p className="text-slate-600">
          Employer outcomes can be recorded once NoEfforts knows of a submission. Withdrawn can always be recorded.
          {app.state === "draft" && " If you applied yourself, choose “I applied myself” first."}
        </p>
      )}
      {outcome === "withdrawn" && app.state === "submitting" && (
        <p className="text-amber-800">
          Recording Withdrawn does not stop this submission; it may already have reached the employer and can no longer be cancelled.
        </p>
      )}
      {outcome === "withdrawn" && IN_PROGRESS.includes(app.state) && app.state !== "submitting" && (
        <p className="text-amber-800">Recording Withdrawn does not stop a submission in progress; use Cancel on the application review.</p>
      )}
      {outcome !== "none" && (
        <label className="block">
          <span className="mb-1 block">When it happened (optional)</span>
          <input type="date" className={`${inputCls} sm:w-60`} max={today} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      )}
      <label className="block">
        <span className="mb-1 block">Note (optional, private)</span>
        <textarea className={inputCls} rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        <span className="mt-1 block text-xs text-slate-500">Kept on this application&apos;s timeline; it cannot be edited or removed.</span>
      </label>
      <p className="text-xs text-slate-500">To correct a mistake, set it back to No outcome yet, then choose the right one.</p>
      <ErrorBox error={error} />
      <Button variant="secondary" disabled={!changed || busy} onClick={save}>
        Record outcome
      </Button>
    </div>
  );
}

function FunnelCard({ f }: { f: Funnel }) {
  const label = (stage: string) =>
    stage === "no_response_yet"
      ? `No response yet (${f.no_response_after_days} days or more since it was recorded as submitted, computed)`
      : STAGE_LABEL[stage] ?? stage;
  return (
    <Card title="Your applications so far">
      <ul className="space-y-1 text-sm">
        {f.stages.map((s) => (
          <li key={s.stage} className="min-w-0 break-words">{`${label(s.stage)}: ${s.count} of ${s.of} ${OF_LABEL[s.of_stage] ?? s.of_stage}`}</li>
        ))}
      </ul>
      <ul className="mt-3 space-y-1 text-sm">
        <li>{`Confirmed by employer receipt: ${f.submitted.receipt}`}</li>
        <li>{`Confirmed by you (your statement): ${f.submitted.confirmed_by_you}`}</li>
        <li>{`Applied by you, not confirmed (your statement): ${f.submitted.applied_by_you}`}</li>
        <li>{`Not confirmed (outcome unknown): ${f.submitted.unconfirmed}`}</li>
      </ul>
      {f.note && <p className="mt-3 text-sm text-slate-700">{f.note}</p>}
      {f.outcome_before_submission > 0 && (
        <p className="mt-2 text-sm text-slate-700">{`${f.outcome_before_submission} with an employer outcome recorded before any submission (not counted above)`}</p>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Counts of your own applications, computed when you open this page. Nothing here is recorded as an outcome, and no rate is shown.
      </p>
    </Card>
  );
}

function Reconcile({ appId, receipt, onDone }: { appId: string; receipt: boolean; onDone: (a: Application) => void }) {
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
        {receipt
          ? "NoEfforts recorded the employer's receipt for this submission; confirm it with what you checked."
          : "We do not know whether the employer received this. Check before doing anything else — there is no one-click resubmit."}
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
        <span className="mt-1 block text-xs text-slate-500">
          Your answer is recorded as your statement, with what you checked, apart from any employer receipt NoEfforts observed. It is kept on
          this application&apos;s timeline and cannot be edited or removed.
        </span>
      </label>
      {!receipt && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />I checked and the employer did not receive it
        </label>
      )}
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={evidence.trim().length < 15} onClick={() => send("received")}>
          It was received
        </Button>
        {!receipt && (
          <Button variant="secondary" disabled={evidence.trim().length < 15 || !confirm} onClick={() => send("not_received")}>
            It was not received
          </Button>
        )}
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
