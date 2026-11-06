"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import AutoApplyCard from "@/components/AutoApplyCard";
import EmailUpdates from "@/components/EmailUpdates";
import FollowUpCard from "@/components/FollowUpCard";
import {
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorText,
  inputCls,
  Loading,
  Pill,
  SectionTitle,
} from "@/ui/primitives";
import { IconTracker } from "@/ui/icons";
import { applicationStatus, OF_LABEL, OUTCOME_LABEL, STAGE_LABEL, STATE_LABEL } from "@/ui/status";

/*
  Application tracker (premium .jsx). The state/outcome vocabulary and every user-
  facing string are preserved verbatim from the previous implementation (see
  @/ui/status and the inline maps below) so tracker-outcomes.spec, follow-ups,
  submission, routing and phase-b all keep passing. Truthful status only: a
  submission is never shown as confirmed without evidence, and an uncertain outcome
  is reconciled, never auto-retried.
*/

// User-performable actions per state; the server enforces the same rules.
const ACTIONS = {
  draft: [
    { to: "submitted_unconfirmed", label: "I applied myself", reason: "User reported a manual submission" },
    { to: "cancelled", label: "Cancel" },
  ],
  awaiting_approval: [{ to: "cancelled", label: "Cancel" }],
  // D132: an application waiting for you (a question, or a form that changed) can also be
  // applied to on the employer's site and recorded here.
  needs_user_action: [
    { to: "submitted_unconfirmed", label: "I applied myself", reason: "User reported a manual submission" },
    { to: "cancelled", label: "Cancel" },
  ],
};

// An attempt that still holds the application (a verification code awaited, a send under way):
// the server refuses a manual record or a cancellation here until it ends, so neither is offered.
const HELD = ["claimed", "sending", "awaiting_code"];

function actionsFor(app) {
  return HELD.includes(app.last_attempt?.state) ? [] : (ACTIONS[app.state] ?? []);
}

// A submission NoEfforts is still handling: recording Withdrawn does not stop it.
const IN_PROGRESS = ["queued", "running", "ready_to_submit", "submitting"];

function eventLine(e) {
  if (e.kind === "state_change") {
    const by = e.source === "receipt" ? " · employer receipt" : e.source === "user_claimed" ? " · your statement" : "";
    return `${e.from_state ? STATE_LABEL[e.from_state] + " → " : ""}${STATE_LABEL[e.to_state ?? ""]}${by}`;
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
  const [apps, setApps] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [open, setOpen] = useState(null);
  const [due, setDue] = useState(new Set());
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api("/applications")
      .then(setApps)
      .catch((e) => {
        setError(e);
        setApps([]);
      });
    api("/applications/funnel")
      .then(setFunnel)
      .catch(() => setFunnel(null));
    api("/follow-ups")
      .then((r) => setDue(new Set(r.items.filter((f) => f.status === "due").map((f) => f.application_id ?? ""))))
      .catch(() => setDue(new Set()));
  }, []);
  useEffect(load, [load]);

  const show = useCallback(async (id) => {
    try {
      setOpen(await api(`/applications/${id}`));
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    if (highlight) show(highlight);
  }, [highlight, show]);

  function done(a) {
    setOpen(a);
    load();
  }

  async function act(id, to, reason) {
    setError(null);
    try {
      done(await api(`/applications/${id}/transition`, { json: { to, reason } }));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <SectionTitle>Application tracker</SectionTitle>
      <ErrorText error={error} />
      {open && (
        <Card
          title={`${open.job.title ?? "Untitled"} — ${open.job.employer ?? ""}`}
          actions={
            <Button variant="secondary" onClick={() => setOpen(null)}>
              Close
            </Button>
          }
        >
          <div className="mb-3 space-y-1 text-sm">
            <p>
              Submission: <Status app={open} />
            </p>
            <p>
              Recruitment stage:{" "}
              <Pill tone={open.outcome === "none" ? "neutral" : "brand"}>{OUTCOME_LABEL[open.outcome]}</Pill>
            </p>
          </div>
          {open.state !== "draft" && (
            <p className="mb-3 text-sm">
              <Link className="text-brand underline" href={`/applications/${open.id}`}>
                {open.state.startsWith("submitted")
                  ? "Open the application (what was sent, and its receipt)"
                  : "Open the application review"}
              </Link>
            </p>
          )}
          {open.state === "submitted_unconfirmed" && (
            <Reconcile key={open.id} appId={open.id} receipt={open.submission === "receipt"} onDone={done} />
          )}
          <div className="mb-3 flex flex-wrap gap-2">
            {actionsFor(open).map((a) => (
              <Button key={a.to} variant={a.to === "cancelled" ? "danger" : "secondary"} onClick={() => act(open.id, a.to, a.reason)}>
                {a.label}
              </Button>
            ))}
          </div>
          <OutcomeForm key={`${open.id}-${open.outcome}-${open.events?.length ?? 0}`} app={open} onDone={done} />
          <FollowUpCard appId={open.id} refreshKey={`${open.state}-${open.outcome}-${open.events?.length ?? 0}`} />
          <h3 className="mb-2 text-sm font-semibold text-ink">Timeline</h3>
          <ol className="space-y-2 border-l-2 border-hairline pl-4 text-sm">
            {open.events?.map((e, i) => (
              <li key={i} className="min-w-0 break-words">
                <span className="text-ink-faint">{new Date(e.created_at).toLocaleString()}</span> —{" "}
                <span data-testid="event-line">{eventLine(e)}</span>
                {e.kind === "state_change" && e.reason && <span className="text-ink-faint"> ({e.reason})</span>}
                <span className="text-xs text-ink-faint"> by {e.actor}</span>
                {e.evidence_note && (
                  <span className="block text-ink-muted">
                    {e.kind === "outcome" ? `Note: ${e.evidence_note}` : `What you checked: ${e.evidence_note}`}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </Card>
      )}
      <EmailUpdates onApplied={load} />
      {funnel && <FunnelCard f={funnel} />}
      <Card title="All applications">
        {apps === null ? (
          <Loading />
        ) : apps.length === 0 ? (
          <EmptyState title="Nothing tracked yet" icon={<IconTracker size={28} />}>
            Open a job and choose “Start application”, or swipe right in Jobs to shortlist roles to prepare.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-hairline">
            {apps.map((a) => (
              <li key={a.id}>
                <button
                  onClick={() => show(a.id)}
                  className="focus-ring flex w-full flex-col gap-1 rounded-[var(--r-md)] py-3 text-left hover:bg-surface-2 sm:flex-row sm:items-center sm:justify-between sm:px-2"
                >
                  <span className="min-w-0">
                    <span className="block font-medium text-ink">{a.job.title ?? "Untitled"}</span>
                    <span className="block text-sm text-ink-muted">{a.job.employer}</span>
                  </span>
                  <span className="flex flex-wrap gap-2">
                    {due.has(a.id) && <Pill tone="caution">Follow up due</Pill>}
                    {a.outcome !== "none" && <Pill tone="neutral">{OUTCOME_LABEL[a.outcome]}</Pill>}
                    {!a.reached_submission && a.outcome !== "none" && a.outcome !== "withdrawn" && (
                      <Pill tone="neutral">Recorded before it was submitted</Pill>
                    )}
                    {a.last_attempt?.state === "rehearsed" && <Pill tone="brand">Rehearsal finished: nothing submitted</Pill>}
                    <Status app={a} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <AutoApplyCard />
    </>
  );
}

function Status({ app }) {
  const { label, tone } = applicationStatus(app);
  return <Pill tone={tone}>{label}</Pill>;
}

function OutcomeForm({ app, onDone }) {
  const choices = app.outcome_choices ?? [];
  const options = choices.includes(app.outcome) ? choices : [app.outcome, ...choices];
  const [outcome, setOutcome] = useState(app.outcome);
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const sentDate = outcome !== "none" ? date : "";
  const changed = outcome !== app.outcome || sentDate !== "" || note.trim() !== "";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api(`/applications/${app.id}`, {
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
        <span className="mb-1 block font-medium text-ink">Outcome</span>
        <select className={`${inputCls} sm:w-60`} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          {options.map((o) => (
            <option key={o} value={o}>
              {OUTCOME_LABEL[o]}
            </option>
          ))}
        </select>
      </label>
      {!choices.includes("interviewing") && (
        <p className="text-ink-muted">
          Employer outcomes can be recorded once NoEfforts knows of a submission. Withdrawn can always be recorded.
          {(app.state === "draft" || app.state === "needs_user_action") && " If you applied yourself, choose “I applied myself” first."}
        </p>
      )}
      {outcome === "withdrawn" && app.state === "submitting" && (
        <p className="text-caution-ink">
          Recording Withdrawn does not stop this submission; it may already have reached the employer and can no longer be cancelled.
        </p>
      )}
      {outcome === "withdrawn" && IN_PROGRESS.includes(app.state) && app.state !== "submitting" && (
        <p className="text-caution-ink">Recording Withdrawn does not stop a submission in progress; use Cancel on the application review.</p>
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
        <span className="mt-1 block text-xs text-ink-muted">Kept on this application&apos;s timeline; it cannot be edited or removed.</span>
      </label>
      <p className="text-xs text-ink-muted">To correct a mistake, set it back to No outcome yet, then choose the right one.</p>
      <ErrorText error={error} />
      <Button variant="secondary" disabled={!changed || busy} onClick={save}>
        Record outcome
      </Button>
    </div>
  );
}

function FunnelCard({ f }) {
  const label = (stage) =>
    stage === "no_response_yet"
      ? `No response yet (${f.no_response_after_days} days or more since it was recorded as submitted, computed)`
      : STAGE_LABEL[stage] ?? stage;
  const count = (stage) => f.stages.find((s) => s.stage === stage)?.count ?? 0;
  // A compact, meaningful overview: tracked and submitted always, plus any recruitment stage or
  // "no response yet" that is actually non-zero — never a wall of zero-count rows. The full
  // breakdown, with denominators and the submission-evidence split, is one tap away.
  const chips = [
    ["Tracked", f.tracked, "neutral"],
    ["Submitted", count("submitted"), "brand"],
    ...["assessment_received", "interviewing", "offer", "rejected"]
      .map((o) => [OUTCOME_LABEL[o], count(o), "neutral"])
      .filter(([, n]) => n > 0),
    ...(count("no_response_yet") > 0 ? [["No response yet", count("no_response_yet"), "caution"]] : []),
  ];
  return (
    <Card title="Overview">
      <div className="flex flex-wrap gap-2" aria-label="Application overview">
        {chips.map(([lbl, n, tone]) => (
          <Pill key={lbl} tone={tone}>
            {lbl}: {n}
          </Pill>
        ))}
      </div>
      <details className="mt-3">
        <summary className="focus-ring cursor-pointer text-sm font-medium text-brand">Full breakdown</summary>
        <ul className="mt-2 space-y-1 text-sm text-ink">
          {f.stages.map((s) => (
            <li key={s.stage} className="min-w-0 break-words">{`${label(s.stage)}: ${s.count} of ${s.of} ${OF_LABEL[s.of_stage] ?? s.of_stage}`}</li>
          ))}
        </ul>
        <ul className="mt-3 space-y-1 text-sm text-ink">
          <li>{`Confirmed by employer receipt: ${f.submitted.receipt}`}</li>
          <li>{`Confirmed by you (your statement): ${f.submitted.confirmed_by_you}`}</li>
          <li>{`Applied by you, not confirmed (your statement): ${f.submitted.applied_by_you}`}</li>
          <li>{`Not confirmed (outcome unknown): ${f.submitted.unconfirmed}`}</li>
        </ul>
        {f.note && <p className="mt-3 text-sm text-ink">{f.note}</p>}
        {f.outcome_before_submission > 0 && (
          <p className="mt-2 text-sm text-ink">{`${f.outcome_before_submission} with an employer outcome recorded before any submission (not counted above)`}</p>
        )}
        <p className="mt-3 text-xs text-ink-muted">
          Counts of your own applications, computed when you open this page. Nothing here is recorded as an outcome, and no rate is shown.
        </p>
      </details>
    </Card>
  );
}

function Reconcile({ appId, receipt, onDone }) {
  const [evidence, setEvidence] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState(null);

  async function send(finding) {
    setError(null);
    try {
      onDone(
        await api(`/applications/${appId}/reconcile`, {
          json: { finding, evidence, confirm_not_received: confirm },
        }),
      );
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="mb-4 space-y-2 rounded-[var(--r-md)] border border-[color:var(--caution)]/30 bg-caution-weak p-3 text-sm">
      <p className="font-medium text-caution-ink">
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
        <span className="mt-1 block text-xs text-ink-muted">
          Your answer is recorded as your statement, with what you checked, apart from any employer receipt NoEfforts observed. It is kept on
          this application&apos;s timeline and cannot be edited or removed.
        </span>
      </label>
      {!receipt && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />I checked and the employer did not receive it
        </label>
      )}
      <ErrorText error={error} />
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
