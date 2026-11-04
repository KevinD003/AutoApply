"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import ApiTokens from "@/components/ApiTokens";
import DraftingSpend from "@/components/DraftingSpend";
import EmailReminders from "@/components/EmailReminders";
import InboxCard from "@/components/InboxCard";
import { Button, Card, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, setCsrf } from "@/lib/api";

const COUNT_LABELS = {
  jobs: "jobs",
  applications: "applications",
  documents: "documents (and their files)",
  saved_answers: "saved answers",
  watches: "watched searches",
};

function GroupHeading({ children }) {
  return <h2 className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">{children}</h2>;
}

// Priority B (D77, docs/account-deletion.md): a full export, and deletion that takes effect at
// once, refused while a submission may be in flight. Slice C: the settings are grouped
// (connections, notifications, privacy & data, developer tools in a disclosure), and deletion is
// a clearly separate, danger-styled section — distinct from setup.
export default function AccountPage() {
  const router = useRouter();
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [password, setPassword] = useState("");
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api("/account/deletion").then(setPreview).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function remove(e) {
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
      <h1 className="font-display text-[1.7rem] font-semibold leading-[1.1] text-ink">Account</h1>

      <GroupHeading>Connections</GroupHeading>
      <InboxCard />

      <GroupHeading>Notifications</GroupHeading>
      <EmailReminders />

      <GroupHeading>Privacy &amp; data</GroupHeading>
      <Card title="Your data">
        <p className="mb-3 text-sm text-ink-muted">
          One ZIP file with every record NoEfforts holds about your account and every document file. Login and session
          secrets and the server&apos;s internal keys are left out; the file&apos;s README lists what and why.
        </p>
        <a
          href="/api/account/export"
          download
          className="inline-block min-h-10 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong"
        >
          Download all my data
        </a>
      </Card>

      <details open className="group rounded-[var(--r-lg)] border border-hairline bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5">
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-2 text-base font-semibold text-ink [&::-webkit-details-marker]:hidden">
          Developer tools
          <span className="text-xs font-normal text-ink-faint group-open:hidden">Show</span>
          <span className="hidden text-xs font-normal text-ink-faint group-open:inline">Hide</span>
        </summary>
        <p className="mt-1 text-sm text-ink-muted">Personal access tokens for the API, CLI and MCP, and this server&apos;s AI drafting spend.</p>
        <div className="mt-4 space-y-5">
          <ApiTokens />
          <DraftingSpend />
        </div>
      </details>

      <GroupHeading>Delete account</GroupHeading>
      <section className="rounded-[var(--r-lg)] border border-[color:var(--danger)]/30 bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5">
        <h2 className="text-base font-semibold text-danger-ink">Delete my account</h2>
        <p className="mt-1 text-sm text-ink-muted">Deleting takes effect at once and cannot be undone. It deletes:</p>
        <ul className="my-2 list-disc pl-5 text-sm text-ink-muted" aria-label="What will be deleted">
          {Object.entries(preview.counts).map(([k, n]) => (
            <li key={k}>
              {n} {COUNT_LABELS[k] ?? k}
            </li>
          ))}
          <li>your profile, facts, preferences, packages, approvals, history and sessions</li>
        </ul>
        <p className="text-sm text-ink-muted">
          {preview.retained_in_database.length === 0
            ? "Nothing about your account is kept in NoEfforts afterwards."
            : `Kept afterwards: ${preview.retained_in_database.join(", ")}.`}
        </p>
        <p className="mt-3 text-sm font-medium text-ink">What deletion cannot reach</p>
        <ul className="my-2 list-disc pl-5 text-sm text-ink-muted" aria-label="What deletion cannot reach">
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
          <div role="alert" className="mt-3 rounded-lg border border-caution/30 bg-caution-weak p-3 text-sm text-caution-ink">
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
      </section>
    </>
  );
}
