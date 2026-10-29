"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import AnswerInput from "@/components/AnswerInput";
import ExecutionCard from "@/components/ExecutionCard";
import { Badge, Button, Card, ErrorBox, inputCls, Loading, Notice } from "@/components/ui";
import { api, ApiError, Doc, GeneratedDoc, PackageAnswer, PackageDiff, PackageDraft, PackageView, ReviewControls } from "@/lib/api";

const SOURCE: Record<string, { label: string; tone: "green" | "indigo" | "amber" | "slate" | "red" }> = {
  profile_fact: { label: "Profile fact", tone: "green" },
  deterministic_mapping: { label: "Mapped from profile", tone: "green" },
  answer_bank: { label: "Saved answer", tone: "indigo" },
  user_entered: { label: "Your answer", tone: "indigo" },
  draft: { label: "Accepted draft", tone: "amber" },
  document: { label: "Document", tone: "green" },
  consent: { label: "Your consent choice", tone: "indigo" },
  unresolved: { label: "Unresolved", tone: "red" },
};

const PREREQUISITE_TONE: Record<string, "green" | "amber" | "slate"> = {
  met: "green",
  established: "green",
  unmet: "amber",
  not_required: "slate",
  not_applicable: "slate",
};

// C13: what revoking did to a submission in progress (backend execution.service.stop_for_revoke).
const REVOKE_NOTICE: Record<string, string> = {
  none: "Approval revoked.",
  cancelled: "Approval revoked. The queued submission was stopped before anything was sent.",
  stopping:
    "Approval revoked. The submission in progress stops before the final click; anything already entered on the employer's form stays entered.",
};

const STATE_LABEL: Record<string, string> = {
  needs_user_action: "Needs your input",
  awaiting_approval: "Ready for your approval",
  queued: "Approved and queued",
  running: "Being filled in",
  submitting: "Submitting",
  submitted_confirmed: "Submitted (confirmed)", // receipt or your statement: see the tracker (D53)
  submitted_unconfirmed: "Submitted? Outcome unknown",
};

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [view, setView] = useState<PackageView | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [noForm, setNoForm] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setView(await api<PackageView>(`/applications/${id}/package`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setNoForm(e.message);
      else setError(e);
    }
  }, [id]);

  useEffect(() => {
    load();
    api<Doc[]>("/documents").then(setDocs).catch(() => undefined);
  }, [load]);

  async function call(path: string, method: string, json: unknown, ok?: string | ((v: PackageView & { revoke_effect?: string }) => string)) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const v = await api<PackageView & { revoke_effect?: string }>(path, { method, json });
      setView(v);
      if (ok) setNotice(typeof ok === "function" ? ok(v) : ok);
    } catch (e) {
      setError(e);
      if (e instanceof ApiError && e.status === 409) load();
    } finally {
      setBusy(false);
    }
  }

  const groups = useMemo(() => {
    if (!view) return [];
    const out = new Map<string, PackageAnswer[]>();
    for (const a of view.package.content.answers) {
      const k = a.step ?? "Questions";
      out.set(k, [...(out.get(k) ?? []), a]);
    }
    return [...out.entries()];
  }, [view]);

  if (noForm)
    return (
      <Card title="No application form yet">
        <p className="text-sm">{noForm} Attach a form from the job page first.</p>
      </Card>
    );
  if (!view)
    return (
      <>
        <ErrorBox error={error} />
        <Loading label="Preparing your application package…" />
      </>
    );

  const c = view.package.content;
  const answers = c.answers;
  const pending = answers.filter((a) => a.status === "needs_user" && !a.sensitive && !a.acknowledgment);
  const special = answers.filter((a) => a.sensitive || a.acknowledgment);
  const ready = c.unresolved.length === 0 && c.validation_errors.length === 0;
  // L2/L3: a generated document is offered only once accepted, and only for its own application.
  const usable = (d: Doc) => d.origin !== "generated" || (!!d.accepted_at && d.made_for_application_id === id);
  const resumes = docs.filter((d) => d.kind === "resume" && usable(d));
  const letters = docs.filter((d) => d.kind === "cover_letter" && usable(d));
  const rc = (key: string): ReviewControls | undefined => view.review?.[key];
  const coverQ = answers.find((a) => rc(a.key)?.document_role === "cover_letter");
  const sendsTo = originOf(c.destination.submit_url);
  const clear = (key: string) => call(`/applications/${id}/answers/clear`, "POST", { key }, "Your answer for this application was cleared.");
  const save = (key: string) => (value: Record<string, unknown>, save_to_bank = false) =>
    call(`/applications/${id}/answers`, "PUT", { key, value, save_to_bank }, "Answer saved.");
  const drafts = Object.fromEntries(view.drafts.map((d) => [d.field_key, d]));
  const prereq = view.rehearsal_prerequisite;
  const approvedBefore = view.history.find((h) => h.was_approved && h.version < view.package.version)?.version;

  return (
    <>
      <Link href="/tracker" className="text-sm text-indigo-700 underline">
        ← Tracker
      </Link>
      <Card title="Destination">
        <p className="text-lg font-semibold">{c.destination.title ?? "Untitled role"}</p>
        <p className="text-slate-700">{c.destination.employer}</p>
        <p className="mt-1 text-sm text-slate-600">
          Form v{c.destination.form_version} ({c.destination.form_source}
          {c.destination.form_title ? ` — ${c.destination.form_title}` : ""})
        </p>
        {view.labels.form_source && (
          <p className="mt-2">
            <Badge tone="amber">{view.labels.form_source}</Badge>
          </p>
        )}
        <div className="mt-2 text-sm text-slate-700" role="group" aria-label="Where this goes">
          {sendsTo ? (
            <p>
              Sends to <code>{sendsTo}</code>
              {c.destination.origin && c.destination.origin !== sendsTo && (
                <>
                  {" "}
                  (the form itself is on <code>{c.destination.origin}</code>)
                </>
              )}
            </p>
          ) : (
            <p>The form does not say where it sends: nothing can be submitted from here.</p>
          )}
          {view.labels.destination && (
            <p className="mt-1">
              <Badge tone={view.labels.destination.startsWith("Local test") ? "slate" : "indigo"}>{view.labels.destination}</Badge>
            </p>
          )}
        </div>
      </Card>

      <Card title="Status">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={ready ? "green" : "amber"}>{STATE_LABEL[view.state] ?? view.state}</Badge>
          <span>
            Package v{view.package.version} · <code title={view.package.content_hash}>{view.package.content_hash.slice(0, 12)}</code>
          </span>
          {view.approval.status === "approved" &&
            (view.approval.scope === "disclose_only" ? (
              <Badge tone="indigo">Approved for a rehearsal only (never submits)</Badge>
            ) : (
              <Badge tone="green">Approved</Badge>
            ))}
          {view.approval.status === "not_approved" && <Badge>Not approved</Badge>}
          {view.approval.status === "invalidated" && <Badge tone="red">Approval invalidated</Badge>}
          {view.approval.status === "used_by_rehearsal" && (
            <Badge tone="indigo">Rehearsal of v{view.approval.version} finished: nothing submitted</Badge>
          )}
        </div>
        {view.approval.status === "used_by_rehearsal" && (
          <p className="mt-2 rounded-lg bg-indigo-50 p-2 text-sm text-indigo-900">
            The rehearsal used its approval up. Approve again to submit, or to rehearse again.
          </p>
        )}
        {view.approval.status === "invalidated" && (
          <div className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-800">
            <p>{view.approval.reason}</p>
            {approvedBefore && approvedBefore < view.package.version && (
              <DiffToggle appId={id} from={approvedBefore} to={view.package.version} label={`What changed since you approved v${approvedBefore}`} />
            )}
          </div>
        )}
        {view.job_signals.approval_blocked && (
          <div className="mt-3 rounded-lg bg-amber-50 p-2 text-sm text-amber-900" role="group" aria-label="About this job">
            <p>{view.job_signals.approval_blocked.message}</p>
            <p className="mt-1">
              <Link className="text-indigo-700 underline" href={`/jobs/${c.destination.job_id}`}>
                Open the job page
              </Link>{" "}
              <span className="text-xs text-slate-500">
                Reason code: <code>{view.job_signals.approval_blocked.code}</code>
              </span>
            </p>
          </div>
        )}
        <div className="mt-3 rounded-lg border border-slate-200 p-2 text-sm" role="group" aria-label="Before the first submission">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">Before the first submission</span>
            <Badge tone={PREREQUISITE_TONE[prereq.status] ?? "slate"}>{prereq.label}</Badge>
          </p>
          <p className="mt-1">{prereq.message}</p>
          {prereq.reason_code && (
            <p className="mt-1 text-xs text-slate-500">
              Reason code: <code>{prereq.reason_code}</code>
            </p>
          )}
        </div>
        {c.validation_errors.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-red-800" aria-label="Validation errors">
            {c.validation_errors.map((e) => (
              <li key={e.key}>{e.message}</li>
            ))}
          </ul>
        )}
        <div className="mt-3 space-y-2">
          <ErrorBox error={error} />
          {notice && <Notice>{notice}</Notice>}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            disabled={!ready || busy || view.approval.status === "approved" || prereq.status === "unmet" || !!view.job_signals.approval_blocked}
            onClick={() =>
              call(
                `/applications/${id}/package/approve`,
                "POST",
                { version: view.package.version, content_hash: view.package.content_hash },
                "Approved. This approval covers exactly this package version.",
              )
            }
          >
            Approve package v{view.package.version}
          </Button>
          <Button
            variant="secondary"
            disabled={!ready || busy || view.approval.status === "approved" || !!view.job_signals.approval_blocked}
            onClick={() =>
              call(
                `/applications/${id}/package/approve`,
                "POST",
                { version: view.package.version, content_hash: view.package.content_hash, scope: "disclose_only" },
                "Approved for a rehearsal: the form will be filled and checked, and never submitted.",
              )
            }
          >
            Approve a rehearsal of v{view.package.version} (fill and check, never submit)
          </Button>
          {view.approval.status === "approved" && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() =>
                call(`/applications/${id}/package/revoke`, "POST", {}, (v) => REVOKE_NOTICE[v.revoke_effect ?? "none"] ?? REVOKE_NOTICE.none)
              }
            >
              Revoke approval
            </Button>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Approval is tied to this exact content. Changing a fact, document, answer, consent or the job itself creates a new version
          that needs approval again. Approvals also expire after a few days. A rehearsal fills the form and uploads your documents
          exactly as a submission would, checks them, then stops: nothing is submitted, and the approval is used up. Revoking stops
          a queued submission before anything is sent, and one in progress before the final click; once the final click has begun it
          cannot be revoked.
        </p>
      </Card>

      <ExecutionCard
        appId={id}
        appState={view.state}
        approved={view.approval.status === "approved"}
        scope={view.approval.status === "approved" ? view.approval.scope : null}
        prerequisiteUnmet={prereq.status === "unmet"}
        onChange={load}
      />

      <Card title="Documents">
        {resumes.length === 0 ? (
          <p className="text-sm">
            No resume uploaded. <Link className="text-indigo-700 underline" href="/documents">Upload one</Link>.
          </p>
        ) : (
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Resume to send</span>
            <select
              className={inputCls}
              value={c.documents.find((d) => d.field === "resume")?.document_id ?? ""}
              onChange={(e) => call(`/applications/${id}/documents`, "PUT", { resume_document_id: e.target.value })}
            >
              <option value="">Choose…</option>
              {resumes.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label} (v{d.version})
                </option>
              ))}
            </select>
          </label>
        )}
        {coverQ &&
          (letters.length === 0 ? (
            <p className="mt-3 text-sm">
              This form asks for a cover letter{coverQ.required ? "" : " (optional)"}. None uploaded:{" "}
              <Link className="text-indigo-700 underline" href="/documents">upload one</Link>.
            </p>
          ) : (
            <label className="mt-3 block text-sm">
              <span className="mb-1 block font-medium">Cover letter to send{coverQ.required ? "" : " (optional)"}</span>
              <select
                className={inputCls}
                value={c.documents.find((d) => d.field === coverQ.key)?.document_id ?? ""}
                onChange={(e) =>
                  e.target.value
                    ? call(`/applications/${id}/documents`, "PUT", { cover_letter_document_id: e.target.value }, "Cover letter chosen.")
                    : call(`/applications/${id}/documents`, "PUT", { clear: ["cover_letter"] }, "No cover letter will be sent.")
                }
              >
                <option value="">{coverQ.required ? "Choose…" : "None"}</option>
                {letters.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label} (v{d.version})
                  </option>
                ))}
              </select>
            </label>
          ))}
        {c.documents.map((d) => (
          <p key={d.field} className="mt-2 text-sm text-slate-600">
            {d.field}: {d.display}
          </p>
        ))}
      </Card>

      <Tailored appId={id} available={view.drafting_available} onChange={load} />

      <Card title={`Needs your answer (${pending.length})`}>
        {pending.length === 0 ? (
          <p className="text-sm text-slate-600">Nothing left to answer here.</p>
        ) : (
          <ul className="space-y-5">
            {pending.map((q) => (
              <li key={q.key} className="border-b border-slate-100 pb-4">
                <QuestionHeader q={q} />
                {q.user_input_allowed ? (
                  <>
                    <AnswerInput q={q} busy={busy} offerReuse onSave={save(q.key)} />
                    {rc(q.key)?.clear && (
                      <Button variant="secondary" disabled={busy} className="mt-2 !min-h-9 !py-1.5" onClick={() => clear(q.key)}>
                        Clear my answer
                      </Button>
                    )}
                  </>
                ) : (
                  <p className="text-sm">
                    Fix this in your <Link className="text-indigo-700 underline" href="/profile">profile</Link> so every application stays
                    consistent.
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Sensitive disclosures and acknowledgments">
        {special.length === 0 ? (
          <p className="text-sm text-slate-600">None on this form.</p>
        ) : (
          <ul className="space-y-5">
            {special.map((q0) => {
              // C18: what awaits your consent comes from your live answer, not the package.
              const live = rc(q0.key);
              const q = live?.proposed_value ? { ...q0, value: live.proposed_value, display: live.proposed ?? null } : q0;
              return (
              <li key={q.key} className="border-b border-slate-100 pb-4">
                <QuestionHeader q={q} />
                {q.acknowledgment ? (
                  <ChoiceRow
                    current={c.consents[q.key]}
                    choices={[
                      ["agree", "I agree"],
                      ["decline", "I decline"],
                    ]}
                    onPick={(choice) => call(`/applications/${id}/consents`, "PUT", { key: q.key, choice })}
                  />
                ) : (
                  <div className="space-y-2">
                    <AnswerInput key={`${q.key}-${view.package.version}`} q={q} busy={busy} onSave={(value) => save(q.key)(value)} />
                    <ChoiceRow
                      current={c.consents[q.key]}
                      choices={[
                        ["disclose", "Include this answer"],
                        ["withhold", "Don't disclose"],
                      ]}
                      onPick={(choice) => call(`/applications/${id}/consents`, "PUT", { key: q.key, choice })}
                    />
                    {rc(q.key)?.clear && (
                      <Button variant="secondary" disabled={busy} className="!min-h-9 !py-1.5" onClick={() => clear(q.key)}>
                        Clear my answer
                      </Button>
                    )}
                  </div>
                )}
              </li>
              );
            })}
          </ul>
        )}
      </Card>

      {groups.map(([step, qs]) => (
        <Card key={step} title={step}>
          <ul className="divide-y divide-slate-100">
            {qs.map((q) => (
              <li key={q.key} className="py-3">
                <QuestionHeader q={q} />
                <p className="text-sm">
                  <span className="font-medium">{q.display ?? (q.status === "blank_optional" ? "(left blank)" : "—")}</span>
                </p>
                {q.draftable && (
                  <DraftControls
                    available={view.drafting_available}
                    draft={drafts[q.key]}
                    onRequest={async () => {
                      setError(null);
                      setNotice("");
                      try {
                        const d = await api<{ status: string }>(`/applications/${id}/drafts`, { method: "POST", json: { key: q.key } });
                        // C15: the same facts and question give the same draft; one already used is said so.
                        if (d.status === "accepted") setNotice("You already used this draft for these facts: it is your answer below.");
                        load();
                      } catch (e) {
                        setError(e);
                      }
                    }}
                    onAccept={(draftId) => call(`/applications/${id}/drafts/${draftId}/accept`, "POST", {}, "Draft used as your answer.")}
                    onReject={(draftId) =>
                      call(`/applications/${id}/drafts/${draftId}/reject`, "POST", {}, "Draft rejected and deleted. It will not be offered again.")
                    }
                  />
                )}
                {q.draftable && q.status !== "resolved" && (
                  <div className="mt-2">
                    <AnswerInput q={q} busy={busy} onSave={(value) => save(q.key)(value)} />
                  </div>
                )}
                <RowActions
                  key={`${q.key}-${view.package.version}`}
                  q={q}
                  controls={rc(q.key)}
                  busy={busy}
                  onSave={save(q.key)}
                  onClear={() => clear(q.key)}
                />
              </li>
            ))}
          </ul>
        </Card>
      ))}

      <Card title="Version history">
        <ol className="space-y-1 text-sm">
          {view.history.map((h) => (
            <li key={h.version}>
              v{h.version} — {new Date(h.created_at).toLocaleString()} — {h.change_summary.join("; ")}
              {h.was_approved && <span className="text-emerald-700"> (was approved)</span>}
              {h.version > 1 && <DiffToggle appId={id} from={h.version - 1} to={h.version} label={`What changed in v${h.version}`} />}
            </li>
          ))}
        </ol>
      </Card>
    </>
  );
}

const CHANGED: Record<string, string> = {
  value: "answer changed",
  question: "the question changed",
  basis: "the facts behind it changed",
  added: "new question",
  removed: "question removed",
};

/** C14: a read-only list of what changed between two package versions. */
function DiffToggle({ appId, from, to, label }: { appId: string; from: number; to: number; label: string }) {
  const [diff, setDiff] = useState<PackageDiff | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function toggle() {
    if (!open && !diff) {
      try {
        setDiff(await api<PackageDiff>(`/applications/${appId}/package/diff?from_version=${from}&to_version=${to}`));
      } catch (e) {
        setError(e);
      }
    }
    setOpen(!open);
  }
  const shown = (x: { display: string | null; status: string } | null) =>
    x === null ? "—" : (x.display ?? (x.status === "blank_optional" ? "(left blank)" : "(no answer)"));
  const empty = diff && !diff.answers.length && !diff.documents.length && !diff.consents.length && !diff.destination.length;
  return (
    <div className="mt-1">
      <button type="button" className="text-xs text-indigo-700 underline" aria-expanded={open} onClick={toggle}>
        {open ? "Hide changes" : label}
      </button>
      <ErrorBox error={error} />
      {open && diff && (
        <ul className="mt-1 space-y-1 rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700" aria-label={`Changes from v${diff.from.version} to v${diff.to.version}`}>
          {empty && <li>Nothing you would see changed (only record versions).</li>}
          {diff.answers.map((a) => (
            <li key={a.key}>
              <span className="font-medium">{a.label}</span>: {shown(a.before)} → {shown(a.after)}{" "}
              <span className="text-slate-500">({a.changed.map((c) => CHANGED[c] ?? c).join(", ")})</span>
            </li>
          ))}
          {diff.documents.map((d) => (
            <li key={d.field}>
              <span className="font-medium">Document ({d.field.replace("_", " ")})</span>: {d.before ?? "none"} → {d.after ?? "none"}
            </li>
          ))}
          {diff.consents.map((c) => (
            <li key={c.key}>
              <span className="font-medium">{c.label}</span>: {c.before ?? "no choice"} → {c.after ?? "no choice"}
            </li>
          ))}
          {diff.destination.map((d) => (
            <li key={d.field}>
              <span className="font-medium">Destination ({d.field.replace("_", " ")})</span>: {String(d.before ?? "—")} → {String(d.after ?? "—")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function originOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/** C12: change a resolved answer, answer an optional question, clear an answer given here, or
 * go to the profile for a fact that belongs there. Questions waiting for an answer, sensitive
 * questions and acknowledgments have their own cards above. */
function RowActions({
  q,
  controls,
  busy,
  onSave,
  onClear,
}: {
  q: PackageAnswer;
  controls: ReviewControls | undefined;
  busy: boolean;
  onSave: (value: Record<string, unknown>, saveToBank: boolean) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (q.sensitive || q.acknowledgment) return null;
  const editable =
    !!controls?.answer_here && (q.status === "resolved" || q.status === "blank_optional") && !(q.draftable && q.status !== "resolved");
  const label = q.status === "blank_optional" ? "Answer this optional question" : "Change answer";
  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap gap-2">
        {editable && (
          <Button type="button" variant="secondary" aria-expanded={open} className="!min-h-9 !py-1.5" onClick={() => setOpen(!open)}>
            {open ? "Cancel" : label}
          </Button>
        )}
        {controls?.clear && (
          <Button type="button" variant="secondary" disabled={busy} className="!min-h-9 !py-1.5" onClick={onClear}>
            Clear my answer
          </Button>
        )}
        {q.protected && !q.user_input_allowed && q.status === "resolved" && (
          <Link className="self-center text-sm text-indigo-700 underline" href="/profile">
            Change it in your profile
          </Link>
        )}
      </div>
      {editable && open && <AnswerInput q={q} busy={busy} offerReuse onSave={onSave} />}
    </div>
  );
}

function QuestionHeader({ q }: { q: PackageAnswer }) {
  const s = SOURCE[q.status === "resolved" ? q.source : q.status === "blank_optional" && q.source === "consent" ? "consent" : "unresolved"];
  return (
    <div className="mb-2">
      <p className="text-sm font-medium text-slate-900">
        {q.label} {q.required ? <span className="text-red-700">*</span> : <span className="text-xs text-slate-500">(optional)</span>}
      </p>
      {q.help_text && <p className="text-xs text-slate-500">{q.help_text}</p>}
      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
        {q.status === "blank_optional" && q.source !== "consent" ? <Badge>Blank (optional)</Badge> : <Badge tone={s.tone}>{s.label}</Badge>}
        {q.sensitive && <Badge tone="amber">Sensitive</Badge>}
        {q.acknowledgment && <Badge tone="amber">Legal / consent</Badge>}
        {q.protected && <Badge>Protected fact</Badge>}
        <span>{q.explanation}</span>
      </p>
    </div>
  );
}

function ChoiceRow({ current, choices, onPick }: { current?: string; choices: [string, string][]; onPick: (c: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2" role="group">
      {choices.map(([value, label]) => (
        <Button key={value} type="button" variant={current === value ? "primary" : "secondary"} aria-pressed={current === value} onClick={() => onPick(value)} className="!min-h-9 !py-1.5">
          {label}
        </Button>
      ))}
    </div>
  );
}

const FACT_KIND: Record<string, string> = { summary: "Profile summary", skills: "Skills", employment: "Work history", education: "Education" };

function DraftControls({
  available,
  draft,
  onRequest,
  onAccept,
  onReject,
}: {
  available: boolean;
  draft?: PackageDraft;
  onRequest: () => void;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  if (!available)
    return <p className="mt-1 text-xs text-slate-500">AI drafting is not configured on this server. Write this answer yourself.</p>;
  return (
    <div className="mt-2 space-y-2">
      {draft ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
          <p className="mb-1 text-xs font-medium text-amber-900">Draft from {draft.provider} — check every claim before using it</p>
          <p className="whitespace-pre-wrap">{draft.text}</p>
          <div className="mt-2 text-xs text-slate-700">
            <p className="font-medium">Based only on these facts from your profile:</p>
            <ul className="list-disc pl-5">
              {draft.cited.map((c, i) => (
                <li key={i}>{c.text === null ? "A fact that has changed since (request a new draft)" : `${FACT_KIND[c.kind ?? ""] ?? c.kind}: ${c.text}`}</li>
              ))}
            </ul>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button className="!min-h-9 !py-1.5" variant="secondary" onClick={() => onAccept(draft.id)}>
              Use this draft
            </Button>
            <Button className="!min-h-9 !py-1.5" variant="secondary" onClick={() => onReject(draft.id)}>
              Reject this draft
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="secondary" className="!min-h-9 !py-1.5" onClick={onRequest}>
          Request a draft
        </Button>
      )}
    </div>
  );
}

// L2/L3 (D73): a resume tailored to this job, or a cover letter, written from your approved facts
// only. Nothing is used until you accept it, and it stops being usable when a fact it cites changes.
function Tailored({ appId, available, onChange }: { appId: string; available: boolean; onChange: () => void }) {
  const [items, setItems] = useState<GeneratedDoc[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const load = useCallback(() => {
    api<GeneratedDoc[]>(`/applications/${appId}/generated-documents`).then(setItems).catch((e) => {
      setError(e);
      setItems([]);
    });
  }, [appId]);
  useEffect(load, [load]);

  async function act(path: string, body: unknown, ok: string) {
    setError(null);
    setNotice("");
    try {
      await api(path, { method: "POST", ...(body ? { json: body } : {}) });
      setNotice(ok);
      load();
      onChange();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card title="Tailored resume and cover letter">
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      {available ? (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => act(`/applications/${appId}/generated-documents`, { kind: "resume" }, "A tailored resume was written: read it below.")}>
            Tailor my resume for this job
          </Button>
          <Button variant="secondary" onClick={() => act(`/applications/${appId}/generated-documents`, { kind: "cover_letter" }, "A cover letter was written: read it below.")}>
            Write a cover letter for this job
          </Button>
        </div>
      ) : (
        <p className="text-sm text-slate-600">AI drafting is not configured on this server. Upload your own resume or cover letter instead.</p>
      )}
      {items && items.length > 0 && (
        <ul className="mt-3 space-y-4">
          {items.map((g) => (
            <li key={g.id} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{g.label}</span>
                {g.stale ? (
                  <Badge tone="red">Facts changed: write a new one</Badge>
                ) : g.accepted ? (
                  <Badge tone="green">Accepted: choose it above</Badge>
                ) : (
                  <Badge tone="amber">Waiting for you to read it</Badge>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-600">Check every claim. It uses only these facts from your profile:</p>
              <ul className="list-disc pl-5 text-xs text-slate-700">
                {g.cited.map((c, i) => (
                  <li key={i}>{c.text === null ? "A fact that has changed since" : c.text}</li>
                ))}
              </ul>
              {g.diff ? (
                <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-xs" aria-label={`Changes from ${g.base_label}`}>
                  <p className="mb-1 font-sans text-slate-600">Changes from {g.base_label}:</p>
                  {g.diff.map((d, i) => (
                    <p key={i} className={d.op === "+" ? "text-emerald-800" : d.op === "-" ? "text-red-700 line-through" : "text-slate-600"}>
                      {d.op === " " ? "\u00a0" : d.op} {d.line}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-2">{g.text}</p>
              )}
              {!g.accepted && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {!g.stale && (
                    <Button className="!min-h-9 !py-1.5" variant="secondary" onClick={() => act(`/applications/${appId}/generated-documents/${g.id}/accept`, null, "Accepted. Choose it above to send it with this application.")}>
                      Accept
                    </Button>
                  )}
                  <Button className="!min-h-9 !py-1.5" variant="secondary" onClick={() => act(`/applications/${appId}/generated-documents/${g.id}/reject`, null, "Rejected and deleted.")}>
                    Reject
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
