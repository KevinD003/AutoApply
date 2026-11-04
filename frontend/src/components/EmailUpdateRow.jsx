"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, inputCls } from "@/components/ui";
import { api } from "@/lib/api";
import { OUTCOME_LABEL } from "@/ui/status";

// What each recognised email reads as (spec §2). Kept in step with inbox/rules.classify; the
// backend recognises and matches — these are display labels only, never a decision.
export const KIND = {
  code: "verification code",
  received: "says your application was received",
  rejected: "reads as a rejection",
  offer: "reads as an offer",
  interview: "reads as an interview invitation",
  interview_scheduled: "reads as a scheduled interview",
  interview_rescheduled: "reads as a rescheduled interview",
  interview_cancelled: "reads as a cancelled interview",
  assessment: "reads as an assessment",
  assessment_reminder: "reads as an assessment reminder",
  next_round: "reads as an invitation to the next round",
  under_review: "says your application is under review",
  info_requested: "asks for more information",
  talent_pool: "says your details were kept on file",
  position_closed: "says the position is on hold or closed",
  recommendation: "a job recommendation",
  unclear: "unclear: it reads as more than one thing",
  other: "other",
};

// The event's state → how it is shown. Mirrors inbox/service states.
export const STATE = {
  proposed: { label: "waiting for you", tone: "amber" },
  review: { label: "needs your review", tone: "amber" },
  auto_applied: { label: "status recorded automatically", tone: "indigo" },
  accepted: { label: "recorded by you", tone: "green" },
  noted: { label: "noted", tone: "slate" },
  unlinked: { label: "names none of your applications (or several)", tone: "slate" },
  dismissed: { label: "dismissed", tone: "slate" },
  undone: { label: "undone", tone: "slate" },
  code_used: { label: "code entered for you", tone: "slate" },
  code_unclear: { label: "not entered: more than one code, or none", tone: "slate" },
};

// Display-only fallback from a recognised event to the outcome it would record, mirroring
// inbox/service.OUTCOME_OF, so the right action still shows for an event stored before the
// proposed_outcome field existed. The backend recomputes and validates; nothing here decides it.
const OUTCOME_OF_KIND = {
  rejected: "rejected",
  offer: "offer",
  withdrawn: "withdrawn",
  interview: "interviewing",
  interview_scheduled: "interviewing",
  interview_rescheduled: "interviewing",
  next_round: "interviewing",
  assessment: "assessment_received",
  assessment_reminder: "assessment_received",
};

// Outcomes offered when you correct what an email said, or record one for an event that names
// none (spec §4). The server enforces what is allowed for that application.
const CORRECTABLE = ["rejected", "interviewing", "assessment_received", "offer", "withdrawn"];

// One recognised email: what it reads as, what it matched and why, and the actions its state
// allows. `act` (from useInbox) runs the request and folds the new view back in.
export default function EmailUpdateRow({ e, act, busy, apps, loadApps }) {
  const [picker, setPicker] = useState(null); // null | "outcome" | "relink"
  const implied = e.proposed_outcome ?? OUTCOME_OF_KIND[e.kind] ?? null;
  const [outcome, setOutcome] = useState(CORRECTABLE.includes(implied) ? implied : "rejected");
  const [target, setTarget] = useState("");

  const linked = Boolean(e.application_id);
  const isReceived = e.kind === "received";
  const open = e.state === "proposed" || e.state === "review";
  const canConfirm = open && linked && (Boolean(implied) || isReceived);
  const canRecord = open && linked && !implied && !isReceived; // informational + linked: pick one
  const canCorrect = open && linked && Boolean(implied) && !isReceived;
  const canUndo = (e.state === "accepted" || e.state === "auto_applied") && !isReceived;
  const canRelink = ["proposed", "review", "unlinked", "noted"].includes(e.state);
  const canDismiss = ["proposed", "review", "unlinked", "noted"].includes(e.state);

  const url = (p) => `/inbox/events/${e.id}/${p}`;
  const btn = "!min-h-8 !px-2 !py-1";

  async function record() {
    if (await act(api(url("accept"), { json: { outcome } }), { applied: true, notice: "Recorded on the application." }))
      setPicker(null);
  }
  async function relink() {
    if (await act(api(url("relink"), { json: { application_id: target || null } }), { notice: target ? "Linked." : "Unlinked." }))
      setPicker(null);
  }

  return (
    <li className="flex flex-col gap-2 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span>
          {new Date(e.received_at).toLocaleDateString()} · from {e.sender_domain} · {KIND[e.kind] ?? e.kind}
        </span>
        <Badge tone={(STATE[e.state] ?? { tone: "slate" }).tone}>{(STATE[e.state] ?? { label: e.state }).label}</Badge>
        {e.application_id && (
          <Link className="text-brand underline" href={`/applications/${e.application_id}`}>
            application
          </Link>
        )}
      </div>
      {(e.proposed_outcome || e.why_matched) && (
        <p className="text-xs text-ink-faint">
          {e.proposed_outcome && (
            <span>
              {e.automatic ? "Recorded automatically: " : "Would record: "}
              {OUTCOME_LABEL[e.proposed_outcome] ?? e.proposed_outcome}
              {e.prev_outcome && e.prev_outcome !== e.proposed_outcome && e.prev_outcome !== "none" && (
                <> (was {OUTCOME_LABEL[e.prev_outcome] ?? e.prev_outcome})</>
              )}
              {". "}
            </span>
          )}
          {e.why_matched && <span>Matched by {e.why_matched}.</span>}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {canConfirm && (
          <Button
            className={btn}
            disabled={busy}
            onClick={() =>
              act(api(url("accept"), { method: "POST" }), {
                applied: true,
                notice: isReceived ? "Marked as received." : "Recorded on the application.",
              })
            }
          >
            {isReceived ? "Confirm it was received" : "Confirm"}
          </Button>
        )}
        {(canCorrect || canRecord) && (
          <Button variant="secondary" className={btn} disabled={busy} onClick={() => setPicker(picker === "outcome" ? null : "outcome")}>
            {canRecord ? "Record an outcome…" : "Correct…"}
          </Button>
        )}
        {canRelink && (
          <Button
            variant="secondary"
            className={btn}
            disabled={busy}
            onClick={() => {
              loadApps();
              setPicker(picker === "relink" ? null : "relink");
            }}
          >
            Wrong application
          </Button>
        )}
        {canUndo && (
          <Button variant="secondary" className={btn} disabled={busy} onClick={() => act(api(url("undo"), { method: "POST" }), { applied: true, notice: "Undone." })}>
            Undo
          </Button>
        )}
        {canDismiss && (
          <Button variant="secondary" className={btn} disabled={busy} onClick={() => act(api(url("dismiss"), { method: "POST" }))}>
            Dismiss
          </Button>
        )}
      </div>
      {picker === "outcome" && (
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Outcome to record" className={`${inputCls} sm:w-56`} value={outcome} onChange={(ev) => setOutcome(ev.target.value)}>
            {CORRECTABLE.map((o) => (
              <option key={o} value={o}>
                {OUTCOME_LABEL[o]}
              </option>
            ))}
          </select>
          <Button className={btn} disabled={busy} onClick={record}>
            Record
          </Button>
        </div>
      )}
      {picker === "relink" && (
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Link to application" className={`${inputCls} sm:w-72`} value={target} onChange={(ev) => setTarget(ev.target.value)}>
            <option value="">None of my applications</option>
            {(apps ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
          <Button className={btn} disabled={busy} onClick={relink}>
            Save
          </Button>
        </div>
      )}
    </li>
  );
}
