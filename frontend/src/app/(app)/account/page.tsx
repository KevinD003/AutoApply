"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import ApiTokens from "@/components/ApiTokens";
import DraftingSpend from "@/components/DraftingSpend";
import EmailReminders from "@/components/EmailReminders";
import InboxCard from "@/components/InboxCard";
import { Button, Card, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, setCsrf } from "@/lib/api";

interface DeletionPreview {
  counts: Record<string, number>;
  submitted_applications: number;
  blocked_by: string[];
  blocked_reasons: string[];
  retained_in_database: string[];
  grace_period_days: number;
  outside_noefforts: { what: string; note: string }[];
  confirmation: string;
}

const COUNT_LABELS: Record<string, string> = {
  jobs: "jobs",
  applications: "applications",
  documents: "documents (and their files)",
  saved_answers: "saved answers",
  watches: "watched searches",
};

// Priority B (D77, docs/account-deletion.md): a full export, and deletion that takes effect at
// once, refused while a submission may be in flight.
export default function AccountPage() {
  const router = useRouter();
  const [preview, setPreview] = useState<DeletionPreview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [password, setPassword] = useState("");
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<DeletionPreview>("/account/deletion").then(setPreview).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function remove(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/account/delete", { json: { password, confirmation: phrase } });
      setCsrf(null);
      router.replace("/login?deleted=1");
    } catch (err) {
      setError(err);
      load();
    } finally {
      setBusy(false);
    }
  }

  if (!preview) return error ? <ErrorBox error={error} /> : <Loading />;
  const blocked = preview.blocked_by.length > 0;
  return (
    <>
      <h1 className="text-xl font-semibold text-slate-900">Account</h1>
      <Card title="Your data">
        <p className="mb-3 text-sm text-slate-700">
          One ZIP file with every record NoEfforts holds about your account and every document file. Login and session
          secrets and the server&apos;s internal keys are left out; the file&apos;s README lists what and why.
        </p>
        <a
          href="/api/account/export"
          download
          className="inline-block min-h-10 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Download all my data
        </a>
      </Card>
      <EmailReminders />
      <InboxCard />
      <ApiTokens />
      <DraftingSpend />
      <Card title="Delete my account">
        <p className="text-sm text-slate-700">Deleting takes effect at once and cannot be undone. It deletes:</p>
        <ul className="my-2 list-disc pl-5 text-sm text-slate-700" aria-label="What will be deleted">
          {Object.entries(preview.counts).map(([k, n]) => (
            <li key={k}>
              {n} {COUNT_LABELS[k] ?? k}
            </li>
          ))}
          <li>your profile, facts, preferences, packages, approvals, history and sessions</li>
        </ul>
        <p className="text-sm text-slate-700">
          {preview.retained_in_database.length === 0
            ? "Nothing about your account is kept in NoEfforts afterwards."
            : `Kept afterwards: ${preview.retained_in_database.join(", ")}.`}
        </p>
        <p className="mt-3 text-sm font-medium text-slate-800">What deletion cannot reach</p>
        <ul className="my-2 list-disc pl-5 text-sm text-slate-700" aria-label="What deletion cannot reach">
          {preview.submitted_applications > 0 && (
            <li>
              {preview.submitted_applications} application(s) were already sent: the employer keeps its copy.
            </li>
          )}
          {preview.outside_noefforts.map((o) => (
            <li key={o.what}>{o.note}</li>
          ))}
        </ul>
        {blocked ? (
          <div role="alert" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {preview.blocked_reasons.join(" ")}
          </div>
        ) : (
          <form onSubmit={remove} className="mt-4 space-y-3">
            <Field label="Your password">
              <input
                className={inputCls}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field label={`Type “${preview.confirmation}” to confirm`}>
              <input className={inputCls} autoComplete="off" required value={phrase} onChange={(e) => setPhrase(e.target.value)} />
            </Field>
            <ErrorBox error={error} />
            <Button type="submit" variant="danger" disabled={busy || phrase.trim().toLowerCase() !== preview.confirmation}>
              {busy ? "Deleting…" : "Delete my account"}
            </Button>
          </form>
        )}
      </Card>
    </>
  );
}
