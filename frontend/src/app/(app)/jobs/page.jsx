"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import {
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  inputCls,
  Loading,
  Pill,
  SectionTitle,
  StatusPill,
} from "@/ui/primitives";
import { SwipeDeck } from "@/ui/SwipeDeck";
import { BrandMark } from "@/ui/BrandMark";
import { IconBriefcase, IconChevronRight, IconCompass, IconMapPin } from "@/ui/icons";

/*
  Jobs — the premium list and the mobile swipe discovery, wired to the real API.

  The default LIST view preserves the exact contract the e2e suite relies on
  (match-summary.spec, phase-b): each job is an <li> whose title is a role=link
  with the exact title text, a data-testid="match-summary" line with verbatim
  wording, a "Why" link to /jobs/{id}#match, and the Add-job / Import forms with
  their existing labels.

  SWIPE discovery (mobile-first, also usable on desktop and by keyboard):
    right = "Apply"  -> application INTENT: the job is shortlisted to prepare.
                         It never creates a disclosure or a submission, and never
                         shows an "Applied" state. The actual application is
                         created when you "Start application" on a shortlisted job.
    left  = "Pass"   -> the job is excluded with the reason "Passed in discovery".
    Both are persisted (account-scoped, via PATCH /jobs/{id}), both are undoable,
    and passed jobs stay in a reviewable Passed collection (status = Excluded).
*/

const STATUS_TONE = { new: "brand", shortlisted: "positive", excluded: "neutral", closed: "neutral" };
const PASS_REASON = "Passed in discovery";

function named(what, items) {
  const shown = items.slice(0, 3).join(", ");
  return `${what}: ${shown}${items.length > 3 ? ` and ${items.length - 3} more` : ""}`;
}

// B (D82): the one-line match explanation. Text is preserved verbatim from the prior
// implementation (match-summary.spec): preferences counted, approved qualifications the job
// names, how much is unknown. No score, verdict or probability.
function matchQuals(m) {
  if (!m.compared) return "Skills and licences not compared";
  if (m.skills_named.length + m.licences_named.length === 0) return "Names none of your approved skills or licences";
  return [m.skills_named.length && named("Names your skills", m.skills_named), m.licences_named.length && named("licences", m.licences_named)]
    .filter(Boolean)
    .join("; ");
}

function MatchLine({ jobId, m }) {
  return (
    <p className="mt-1 text-xs text-ink-muted" data-testid="match-summary">
      <span>Your preferences: {m.label}</span>
      <span aria-hidden="true"> · </span>
      <span>{matchQuals(m)}</span>
      <span aria-hidden="true"> · </span>
      <span>{m.unknown ? `${m.unknown} not known` : "Nothing marked unknown"}</span>
      <span aria-hidden="true"> · </span>
      <Link href={`/jobs/${jobId}#match`} className="text-brand underline">
        Why
      </Link>
    </p>
  );
}

export default function JobsPage() {
  const [mode, setMode] = useState("list");
  return (
    <>
      <SectionTitle
        hint={
          <div className="inline-flex rounded-full border border-hairline-strong p-0.5 text-sm" role="tablist" aria-label="Jobs view">
            {[
              ["list", "List"],
              ["swipe", "Swipe"],
            ].map(([k, label]) => (
              <button
                key={k}
                role="tab"
                aria-selected={mode === k}
                onClick={() => setMode(k)}
                className={`focus-ring rounded-full px-3 py-1 font-medium transition ${mode === k ? "bg-brand text-brand-contrast" : "text-ink-muted hover:text-ink"}`}
              >
                {label}
              </button>
            ))}
          </div>
        }
      >
        Jobs
      </SectionTitle>

      {mode === "list" ? <ListView /> : <SwipeView onSwitchToList={() => setMode("list")} />}
    </>
  );
}

function ListView() {
  const [jobs, setJobs] = useState(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState(null);
  const router = useRouter();

  const load = useCallback(async () => {
    setError(null);
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (status) p.set("status", status);
    try {
      const r = await api(`/jobs?${p}`);
      setJobs(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e);
      setJobs([]);
    }
  }, [q, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function startApplication(jobId) {
    try {
      const app = await api("/applications", { json: { job_id: jobId } });
      router.push(`/applications/${app.id}`);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <AddJob onAdded={load} />
        <ImportJobs onImported={load} />
      </div>
      <Card
        title={`Your jobs (${total})`}
        actions={
          <div className="flex gap-3 text-sm">
            <a className="text-brand underline" href="/api/jobs/export?format=csv">
              Export CSV
            </a>
            <a className="text-brand underline" href="/api/jobs/export?format=xlsx">
              Export XLSX
            </a>
          </div>
        }
      >
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <input
            aria-label="Search jobs"
            className={inputCls}
            placeholder="Search title, employer, location"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select aria-label="Filter by status" className={`${inputCls} sm:w-44`} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="new">New</option>
            <option value="shortlisted">Shortlisted</option>
            <option value="excluded">Excluded (passed)</option>
            <option value="closed">Closed</option>
          </select>
        </div>
        <ErrorText error={error} />
        {jobs === null ? (
          <Loading />
        ) : jobs.length === 0 ? (
          <EmptyState title="No jobs yet" icon={<IconBriefcase size={28} />}>
            Add a job link above, import a spreadsheet, or switch to Swipe to triage new roles.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-hairline">
            {jobs.map((j) => (
              <li key={j.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <Link href={`/jobs/${j.id}`} className="font-medium text-ink hover:text-brand hover:underline">
                    {j.title ?? "Untitled role"}
                  </Link>
                  <p className="text-sm text-ink-muted">{[j.employer, j.location].filter(Boolean).join(" · ") || "Details not provided"}</p>
                  {j.exclusion_reason && <p className="text-xs text-ink-faint">{j.exclusion_reason}</p>}
                  {j.match && <MatchLine jobId={j.id} m={j.match} />}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {j.ats_provider !== "unknown" && <Pill tone="neutral">{j.ats_provider}</Pill>}
                  <StatusPill tone={STATUS_TONE[j.status] ?? "neutral"}>{j.status}</StatusPill>
                  {j.status === "shortlisted" && (
                    <Button size="sm" onClick={() => startApplication(j.id)}>
                      Start application
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function SwipeView({ onSwitchToList }) {
  const [deck, setDeck] = useState(null);
  const [history, setHistory] = useState([]); // { job, dir }
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api(`/jobs?status=new&limit=50`);
      setDeck(r.items);
    } catch (e) {
      setError(e);
      setDeck([]);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function decide(job, dir) {
    // Optimistically remove from the deck; restore on failure (reconnect-safe).
    setDeck((d) => (d ? d.filter((c) => c.id !== job.id) : d));
    setBusy(true);
    setError(null);
    const patch =
      dir === "apply" ? { status: "shortlisted" } : { status: "excluded", exclusion_reason: PASS_REASON };
    try {
      await api(`/jobs/${job.id}`, { method: "PATCH", json: patch });
      setHistory((h) => [...h, { job, dir }]);
    } catch (e) {
      setError(e);
      setDeck((d) => (d ? [job, ...d] : [job])); // put it back, nothing lost
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    const last = history[history.length - 1];
    if (!last) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/jobs/${last.job.id}`, { method: "PATCH", json: { status: "new", exclusion_reason: "" } });
      setHistory((h) => h.slice(0, -1));
      setDeck((d) => (d ? [last.job, ...d] : [last.job]));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const applied = history.filter((h) => h.dir === "apply").length;
  const passed = history.filter((h) => h.dir === "pass").length;

  if (deck === null && !error) return <Loading label="Loading jobs to triage…" />;

  return (
    <div className="space-y-4">
      <Banner tone="info">
        Swipe right to <strong>apply</strong> (adds the role to prepare — nothing is submitted) or left to{" "}
        <strong>pass</strong>. Every decision is saved and can be undone; passed roles stay under{" "}
        <button className="underline" onClick={onSwitchToList}>
          Excluded (passed)
        </button>{" "}
        in the list.
      </Banner>
      <ErrorText error={error} />
      <p className="text-center text-sm text-ink-muted" aria-live="polite">
        {applied} to apply · {passed} passed
      </p>

      <SwipeDeck
        cards={deck ?? []}
        renderCard={(job) => <SwipeCard job={job} />}
        onDecide={decide}
        onUndo={undo}
        canUndo={history.length > 0 && !busy}
        applyLabel="Apply"
        passLabel="Pass"
        emptyState={
          <Card>
            <div className="py-8 text-center">
              <p className="font-medium text-ink">You&apos;re all caught up</p>
              <p className="mt-1 text-sm text-ink-muted">
                {applied > 0 ? `${applied} role(s) are ready to prepare.` : "No new jobs to triage right now."}
              </p>
              <div className="mt-4 flex justify-center gap-2">
                <Button variant="secondary" onClick={onSwitchToList}>
                  Back to list
                </Button>
                {applied > 0 && <Button onClick={() => router.push("/jobs")}>Prepare shortlisted</Button>}
              </div>
            </div>
          </Card>
        }
      />
    </div>
  );
}

function SwipeCard({ job }) {
  return (
    <div className="flex h-full flex-col">
      <div className="brand-grad relative h-24 shrink-0 p-4 text-white">
        <div className="flex items-center justify-between">
          <Pill className="bg-white/20 text-white">
            <IconCompass size={13} /> {job.ats_provider !== "unknown" ? job.ats_provider : "New role"}
          </Pill>
          <BrandMark size={22} />
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-5">
        <div>
          <h3 className="text-xl font-semibold tracking-tight text-ink">{job.title ?? "Untitled role"}</h3>
          {job.employer && <p className="mt-1 text-sm text-ink-muted">{job.employer}</p>}
          {job.location && (
            <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-ink-muted">
              <IconMapPin size={16} /> {job.location}
            </p>
          )}
        </div>
        {job.match && (
          <div className="rounded-[var(--r-md)] bg-surface-2 p-3">
            <MatchLine jobId={job.id} m={job.match} />
          </div>
        )}
        <p className="mt-auto text-xs text-ink-faint">
          Right = apply (prepare it — nothing is submitted). Left = pass. You approve every submission yourself.
        </p>
        <Link href={`/jobs/${job.id}`} className="inline-flex items-center gap-1 text-sm text-brand underline">
          View details <IconChevronRight size={14} />
        </Link>
      </div>
    </div>
  );
}

function AddJob({ onAdded }) {
  const [form, setForm] = useState({ url: "", title: "", employer: "", location: "" });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v.trim()));
      const r = await api("/jobs", { json: body });
      setNotice(r.duplicate ? "You already have this job — nothing was duplicated." : "Job added.");
      setForm({ url: "", title: "", employer: "", location: "" });
      onAdded();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Add a job">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Job link" hint="Paste a posting URL, or fill in title and employer.">
          <input className={inputCls} type="url" inputMode="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Title">
            <input className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </Field>
          <Field label="Employer">
            <input className={inputCls} value={form.employer} onChange={(e) => setForm({ ...form, employer: e.target.value })} />
          </Field>
        </div>
        <Field label="Location">
          <input className={inputCls} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </Field>
        <ErrorText error={error} />
        {notice && <Banner tone="positive">{notice}</Banner>}
        <Button type="submit" disabled={busy}>
          {busy ? "Adding…" : "Add job"}
        </Button>
      </form>
    </Card>
  );
}

function ImportJobs({ onImported }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      setResult(await api("/jobs/import", { form }));
      onImported();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const problems = result?.rows.filter((r) => r.outcome === "error") ?? [];
  return (
    <Card title="Import CSV / XLSX">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-ink-muted">
          Columns: <code>job_url</code>, <code>employer</code>, <code>title</code>, <code>location</code>, <code>status</code>,{" "}
          <code>posted_on</code>, <code>requisition_id</code>, <code>notes</code>, <code>row_id</code>. Each row needs a link, or a title and
          employer.
        </p>
        <input
          aria-label="Spreadsheet file"
          type="file"
          accept=".csv,.xlsx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-ink-muted file:mr-3 file:rounded-[var(--r-md)] file:border-0 file:bg-surface-3 file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink"
        />
        <ErrorText error={error} />
        {result && (
          <Banner tone="positive">
            {result.created} added, {result.duplicates} already known, {result.errors} with problems ({result.total_rows} rows).
          </Banner>
        )}
        {problems.length > 0 && (
          <ul className="max-h-40 overflow-y-auto rounded-[var(--r-md)] bg-caution-weak p-3 text-xs text-caution-ink">
            {problems.map((p) => (
              <li key={p.row}>
                Row {p.row} ({p.row_id}): {p.errors?.join("; ")}
              </li>
            ))}
          </ul>
        )}
        <Button type="submit" disabled={!file || busy}>
          {busy ? "Importing…" : "Import"}
        </Button>
      </form>
    </Card>
  );
}
