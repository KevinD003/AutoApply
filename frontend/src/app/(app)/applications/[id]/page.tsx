"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import AnswerInput from "@/components/AnswerInput";
import ExecutionCard from "@/components/ExecutionCard";
import { Badge, Button, Card, ErrorBox, inputCls, Loading, Notice } from "@/components/ui";
import { api, ApiError, Doc, PackageAnswer, PackageView } from "@/lib/api";

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

const STATE_LABEL: Record<string, string> = {
  needs_user_action: "Needs your input",
  awaiting_approval: "Ready for your approval",
  queued: "Approved and queued",
  running: "Being filled in",
  submitting: "Submitting",
  submitted_confirmed: "Submitted (employer receipt)",
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

  async function call(path: string, method: string, json: unknown, ok?: string) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      setView(await api<PackageView>(path, { method, json }));
      if (ok) setNotice(ok);
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
  const resumes = docs.filter((d) => d.kind === "resume");
  const drafts = Object.fromEntries(view.drafts.map((d) => [d.field_key, d]));

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
      </Card>

      <Card title="Status">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={ready ? "green" : "amber"}>{STATE_LABEL[view.state] ?? view.state}</Badge>
          <span>
            Package v{view.package.version} · <code title={view.package.content_hash}>{view.package.content_hash.slice(0, 12)}</code>
          </span>
          {view.approval.status === "approved" && <Badge tone="green">Approved</Badge>}
          {view.approval.status === "not_approved" && <Badge>Not approved</Badge>}
          {view.approval.status === "invalidated" && <Badge tone="red">Approval invalidated</Badge>}
        </div>
        {view.approval.status === "invalidated" && (
          <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-800">{view.approval.reason}</p>
        )}
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
            disabled={!ready || busy || view.approval.status === "approved"}
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
          {view.approval.status === "approved" && (
            <Button variant="secondary" disabled={busy} onClick={() => call(`/applications/${id}/package/revoke`, "POST", {}, "Approval revoked.")}>
              Revoke approval
            </Button>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Approval is tied to this exact content. Changing a fact, document, answer, consent or the job itself creates a new version
          that needs approval again. Approvals also expire after a few days.
        </p>
      </Card>

      <ExecutionCard appId={id} appState={view.state} approved={view.approval.status === "approved"} onChange={load} />

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
        {c.documents.map((d) => (
          <p key={d.field} className="mt-2 text-sm text-slate-600">
            {d.field}: {d.display}
          </p>
        ))}
      </Card>

      <Card title={`Needs your answer (${pending.length})`}>
        {pending.length === 0 ? (
          <p className="text-sm text-slate-600">Nothing left to answer here.</p>
        ) : (
          <ul className="space-y-5">
            {pending.map((q) => (
              <li key={q.key} className="border-b border-slate-100 pb-4">
                <QuestionHeader q={q} />
                {q.user_input_allowed ? (
                  <AnswerInput
                    q={q}
                    busy={busy}
                    onSave={(value, save_to_bank) => call(`/applications/${id}/answers/${q.key}`, "PUT", { value, save_to_bank }, "Answer saved.")}
                  />
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
            {special.map((q) => (
              <li key={q.key} className="border-b border-slate-100 pb-4">
                <QuestionHeader q={q} />
                {q.acknowledgment ? (
                  <ChoiceRow
                    current={c.consents[q.key]}
                    choices={[
                      ["agree", "I agree"],
                      ["decline", "I decline"],
                    ]}
                    onPick={(choice) => call(`/applications/${id}/consents/${q.key}`, "PUT", { choice })}
                  />
                ) : (
                  <div className="space-y-2">
                    <AnswerInput q={q} busy={busy} onSave={(value) => call(`/applications/${id}/answers/${q.key}`, "PUT", { value })} />
                    <ChoiceRow
                      current={c.consents[q.key]}
                      choices={[
                        ["disclose", "Include this answer"],
                        ["withhold", "Don't disclose"],
                      ]}
                      onPick={(choice) => call(`/applications/${id}/consents/${q.key}`, "PUT", { choice })}
                    />
                  </div>
                )}
              </li>
            ))}
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
                      try {
                        await api(`/applications/${id}/answers/${q.key}/draft`, { method: "POST" });
                        load();
                      } catch (e) {
                        setError(e);
                      }
                    }}
                    onAccept={(draftId) => call(`/applications/${id}/drafts/${draftId}/accept`, "POST", {})}
                  />
                )}
                {q.draftable && q.status !== "resolved" && (
                  <div className="mt-2">
                    <AnswerInput q={q} busy={busy} onSave={(value) => call(`/applications/${id}/answers/${q.key}`, "PUT", { value }, "Answer saved.")} />
                  </div>
                )}
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
            </li>
          ))}
        </ol>
      </Card>
    </>
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

function DraftControls({
  available,
  draft,
  onRequest,
  onAccept,
}: {
  available: boolean;
  draft?: { id: string; text: string; provider: string };
  onRequest: () => void;
  onAccept: (id: string) => void;
}) {
  if (!available)
    return <p className="mt-1 text-xs text-slate-500">AI drafting is not configured on this server. Write this answer yourself.</p>;
  return (
    <div className="mt-2 space-y-2">
      {draft ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
          <p className="mb-1 text-xs font-medium text-amber-900">Draft from {draft.provider} — check every claim before using it</p>
          <p className="whitespace-pre-wrap">{draft.text}</p>
          <Button className="mt-2 !min-h-9 !py-1.5" variant="secondary" onClick={() => onAccept(draft.id)}>
            Use this draft
          </Button>
        </div>
      ) : (
        <Button variant="secondary" className="!min-h-9 !py-1.5" onClick={onRequest}>
          Request a draft
        </Button>
      )}
    </div>
  );
}
