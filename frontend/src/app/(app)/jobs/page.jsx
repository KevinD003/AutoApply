"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { salaryDisplay } from "@/lib/salary";
import {
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  IconButton,
  inputCls,
  Loading,
  Pill,
  SectionTitle,
  StatusPill,
} from "@/ui/primitives";
import { Sheet } from "@/ui/motion";
import { SwipeDeck } from "@/ui/SwipeDeck";
import { BrandMark } from "@/ui/BrandMark";
import { cx } from "@/ui/cx";
import { IconBriefcase, IconChevronRight, IconCompass, IconMapPin, IconUpload, IconX } from "@/ui/icons";

/*
  Jobs — a jobs-first premium experience, wired to the real API (Slice B).

  Hierarchy (leads with jobs, not data entry):
    1. heading + context;
    2. a prominent List / Swipe control;
    3. the jobs list (premium cards) or the swipe deck;
    4. SECONDARY: "Add a job" and "Import jobs" open sheets; exports live in a small menu.

  Each card exposes only what a source actually gave (backend JobOut.card, from the same
  consolidation the detail page uses): title/employer, location + work arrangement, salary with
  its original figures, a short description preview, application status, the match summary, and
  save / details / apply actions. Nothing is invented — a field no source gave is simply absent.

  e2e contract preserved (match-summary.spec, jobs-swipe.spec, phase-*): LIST rows are <li>s whose
  title is a role=link with the exact title, a data-testid="match-summary" line with the verbatim
  wording and a "Why" link to /jobs/{id}#match; the List/Swipe tabs; the "Search jobs" and
  "Filter by status" controls; the "Start application" action on shortlisted jobs; and the swipe
  Apply/Pass/Undo controls. The Add-job and Import forms keep their field labels and submit-button
  names ("Add job", "Import"); they now live in sheets opened by the "Add a job" / "Import jobs"
  secondary actions.

  SWIPE discovery (mobile-first, also usable on desktop and by keyboard):
    right = "Apply" -> application INTENT: the job is shortlisted to prepare. It never creates a
                       disclosure or a submission, and never shows an "Applied" state.
    left  = "Pass"  -> the job is excluded with the reason "Passed in discovery".
    Both persist (account-scoped, PATCH /jobs/{id}) and are undoable.
*/

const STATUS_TONE = { new: "brand", shortlisted: "positive", excluded: "neutral", closed: "neutral" };
const PASS_REASON = "Passed in discovery";
const WORKPLACE = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", on_site: "On-site", "on-site": "On-site" };
const workplaceLabel = (w) => (w ? (WORKPLACE[w] ?? w.charAt(0).toUpperCase() + w.slice(1)) : null);

function named(what, items) {
  const shown = items.slice(0, 3).join(", ");
  return `${what}: ${shown}${items.length > 3 ? ` and ${items.length - 3} more` : ""}`;
}

// B (D82): the one-line match explanation. Wording preserved verbatim (match-summary.spec):
// preferences counted, approved qualifications the job names, how much is unknown. No score.
function matchQuals(m) {
  if (!m.compared) return "Skills and licences not compared";
  if (m.skills_named.length + m.licences_named.length === 0) return "Names none of your approved skills or licences";
  return [m.skills_named.length && named("Names your skills", m.skills_named), m.licences_named.length && named("licences", m.licences_named)]
    .filter(Boolean)
    .join("; ");
}

function MatchLine({ jobId, m }) {
  return (
    <p className="mt-2 text-xs text-ink-muted" data-testid="match-summary">
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

// The fact chips a card shows when a source gave them (salary, work arrangement, type, platform).
function FactChips({ job }) {
  const card = job.card ?? {};
  const salary = salaryDisplay(card.salary);
  const workplace = workplaceLabel(card.workplace);
  const chips = [];
  if (salary) chips.push(<Pill key="sal" tone="positive">{salary}</Pill>);
  if (workplace) chips.push(<Pill key="wp" tone="brand">{workplace}</Pill>);
  if (card.employment_type) chips.push(<Pill key="et" tone="neutral">{card.employment_type}</Pill>);
  if (card.seniority) chips.push(<Pill key="sen" tone="neutral">{card.seniority}</Pill>);
  if (job.ats_provider && job.ats_provider !== "unknown") chips.push(<Pill key="ats" tone="neutral">{job.ats_provider}</Pill>);
  if (!chips.length) return null;
  return <div className="mt-2.5 flex flex-wrap items-center gap-2">{chips}</div>;
}

export default function JobsPage() {
  const [mode, setMode] = useState("list");
  const [sheet, setSheet] = useState(null); // "add" | "import" | null
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  const close = () => setSheet(null);

  return (
    <>
      <SectionTitle hint={<ViewToggle mode={mode} onChange={setMode} />}>Jobs</SectionTitle>

      <div className="-mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-xl text-sm text-ink-muted">
          Discover roles, triage them by swipe, and track what you apply to. You approve every application yourself.
        </p>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => setSheet("add")}>
            <IconBriefcase size={16} /> Add a job
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setSheet("import")}>
            <IconUpload size={16} /> Import jobs
          </Button>
          <ExportMenu />
        </div>
      </div>

      <div>{mode === "list" ? <ListView reloadKey={reloadKey} /> : <SwipeView reloadKey={reloadKey} onSwitchToList={() => setMode("list")} />}</div>

      <Sheet open={sheet === "add"} onClose={close} labelledBy="add-sheet-title">
        <SheetHeader id="add-sheet-title" title="Add a job" onClose={close} />
        <div className="px-4 pb-5 sm:px-5">
          <AddJob onAdded={reload} />
        </div>
      </Sheet>
      <Sheet open={sheet === "import"} onClose={close} labelledBy="import-sheet-title">
        <SheetHeader id="import-sheet-title" title="Import jobs" onClose={close} />
        <div className="px-4 pb-5 sm:px-5">
          <ImportJobs onImported={reload} />
        </div>
      </Sheet>
    </>
  );
}

function ViewToggle({ mode, onChange }) {
  return (
    <div
      role="tablist"
      aria-label="Jobs view"
      className="inline-flex rounded-[var(--r-md)] border border-hairline-strong bg-surface p-1 shadow-[var(--shadow-sm)]"
    >
      {[
        ["list", "List"],
        ["swipe", "Swipe"],
      ].map(([k, label]) => (
        <button
          key={k}
          role="tab"
          aria-selected={mode === k}
          onClick={() => onChange(k)}
          className={cx(
            "focus-ring ne-interactive min-h-9 rounded-[var(--r-sm)] px-4 text-sm font-semibold",
            mode === k ? "bg-brand text-brand-contrast shadow-[var(--shadow-sm)]" : "text-ink-muted hover:text-ink",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function SheetHeader({ id, title, onClose }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-4 sm:px-5">
      <h2 id={id} className="font-display text-[1.35rem] font-semibold text-ink">
        {title}
      </h2>
      <IconButton label="Close" tone="neutral" className="h-9 w-9" onClick={onClose}>
        <IconX size={18} />
      </IconButton>
    </div>
  );
}

function ExportMenu() {
  const item = "block rounded-[var(--r-sm)] px-3 py-2 text-sm text-ink hover:bg-surface-3";
  return (
    <details className="group relative">
      <summary className="focus-ring ne-interactive inline-flex min-h-9 cursor-pointer list-none items-center gap-1.5 rounded-[var(--r-md)] border border-hairline-strong bg-surface px-3 text-sm font-medium text-ink shadow-[var(--shadow-sm)] hover:bg-surface-3 [&::-webkit-details-marker]:hidden">
        Export <IconChevronRight size={14} className="rotate-90 opacity-60" />
      </summary>
      <div className="absolute right-0 z-20 mt-1 w-44 rounded-[var(--r-md)] border border-hairline bg-surface p-1 shadow-[var(--shadow-md)]">
        <a href="/api/jobs/export?format=csv" className={item} download>
          Export CSV
        </a>
        <a href="/api/jobs/export?format=xlsx" className={item} download>
          Export XLSX
        </a>
      </div>
    </details>
  );
}

function ListView({ reloadKey }) {
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
  }, [load, reloadKey]);

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
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          aria-label="Search jobs"
          className={inputCls}
          placeholder="Search title, employer, location"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select aria-label="Filter by status" className={`${inputCls} sm:w-48`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="new">New</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="excluded">Excluded (passed)</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      <h2 className="text-sm font-semibold text-ink-faint">Your jobs ({total})</h2>
      <ErrorText error={error} />

      {jobs === null ? (
        <Loading />
      ) : jobs.length === 0 ? (
        <EmptyState title="No jobs yet" icon={<IconBriefcase size={28} />}>
          Use “Add a job” or “Import jobs” above, or switch to Swipe to triage new roles.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {jobs.map((j) => (
            <li
              key={j.id}
              className="ne-interactive rounded-[var(--r-lg)] border border-hairline bg-surface p-4 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] sm:p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link
                    href={`/jobs/${j.id}`}
                    className="font-display text-[1.15rem] font-semibold leading-tight text-ink hover:text-brand hover:underline"
                  >
                    {j.title ?? "Untitled role"}
                  </Link>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-sm text-ink-muted">
                    {j.employer && <span className="font-medium text-ink">{j.employer}</span>}
                    {j.location && (
                      <span className="inline-flex items-center gap-1">
                        <IconMapPin size={14} className="text-ink-faint" /> {j.location}
                      </span>
                    )}
                    {!j.employer && !j.location && "Details not provided"}
                  </p>
                </div>
                <StatusPill tone={STATUS_TONE[j.status] ?? "neutral"}>{j.status}</StatusPill>
              </div>

              <FactChips job={j} />

              {j.card?.description_preview && <p className="mt-2.5 line-clamp-2 text-sm text-ink-muted">{j.card.description_preview}</p>}

              {j.exclusion_reason && <p className="mt-2 text-xs text-ink-faint">{j.exclusion_reason}</p>}

              {j.match && <MatchLine jobId={j.id} m={j.match} />}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Link href={`/jobs/${j.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
                  View details <IconChevronRight size={14} />
                </Link>
                {j.status === "shortlisted" && (
                  <Button size="sm" className="ml-auto" onClick={() => startApplication(j.id)}>
                    Start application
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SwipeView({ reloadKey, onSwitchToList }) {
  const [deck, setDeck] = useState(null);
  const [history, setHistory] = useState([]); // { job, dir }
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

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
  }, [load, reloadKey]);

  async function decide(job, dir) {
    // Optimistically remove from the deck; restore on failure (reconnect-safe).
    setDeck((d) => (d ? d.filter((c) => c.id !== job.id) : d));
    setBusy(true);
    setError(null);
    const patch = dir === "apply" ? { status: "shortlisted" } : { status: "excluded", exclusion_reason: PASS_REASON };
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
        Swipe right to <strong>apply</strong> (adds the role to prepare — nothing is submitted) or left to <strong>pass</strong>. Every decision
        is saved and can be undone; passed roles stay under{" "}
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
                {applied > 0 && <Button onClick={onSwitchToList}>Prepare shortlisted</Button>}
              </div>
            </div>
          </Card>
        }
      />
    </div>
  );
}

function SwipeCard({ job }) {
  const card = job.card ?? {};
  const salary = salaryDisplay(card.salary);
  const workplace = workplaceLabel(card.workplace);
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
          <h3 className="font-display text-[1.4rem] font-semibold leading-tight text-ink">{job.title ?? "Untitled role"}</h3>
          {job.employer && <p className="mt-1.5 text-sm font-medium text-ink-muted">{job.employer}</p>}
          {job.location && (
            <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-ink-muted">
              <IconMapPin size={16} /> {job.location}
            </p>
          )}
          {(salary || workplace) && (
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              {salary && <Pill tone="positive">{salary}</Pill>}
              {workplace && <Pill tone="brand">{workplace}</Pill>}
            </div>
          )}
          {card.description_preview && <p className="mt-2.5 line-clamp-3 text-sm text-ink-muted">{card.description_preview}</p>}
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
  );
}
