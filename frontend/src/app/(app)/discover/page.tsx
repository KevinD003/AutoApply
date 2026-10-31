"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import BoardSources from "@/components/BoardSources";
import { Badge, Button, Card, Credit, Empty, ErrorBox, Field, inputCls, Loading, Notice, splitList } from "@/components/ui";
import {
  api,
  DiscoveredJob,
  DiscoveryPlatform,
  DiscoveryDeleteResult,
  DiscoveryImportResult,
  DiscoveryProviderInfo,
  DiscoveryWatch,
} from "@/lib/api";

const LINK_TEXT: Record<string, string> = {
  new_job: "added to your jobs",
  application_url: "already in your jobs (same application link)",
  job_url: "already in your jobs (same job link)",
  employer_title_location: "already in your jobs (same employer, title and location)",
  previous_link: "already in your jobs",
};

const SPONSORSHIP_TEXT = { yes: "says yes", no: "says no", unknown: "not stated" } as const;

// While a watched search is active the list reloads on its own (D56): new postings appear
// without a page reload, within about a minute of reaching Freehire.
const REFRESH_MS = 20_000;

// D100: the platforms a listing's address can name (jobs/canonical.py), and "unknown".
const PLATFORM_CHOICES: [string, string][] = [
  ["greenhouse", "Greenhouse"],
  ["lever", "Lever"],
  ["ashby", "Ashby"],
  ["workday", "Workday"],
  ["workable", "Workable"],
  ["smartrecruiters", "SmartRecruiters"],
  ["unknown", "Other or not recognised"],
];

export default function DiscoverPage() {
  const [providers, setProviders] = useState<DiscoveryProviderInfo[] | null>(null);
  const [rows, setRows] = useState<DiscoveredJob[] | null>(null);
  const [watches, setWatches] = useState<DiscoveryWatch[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [platform, setPlatform] = useState("");
  const [platforms, setPlatforms] = useState<DiscoveryPlatform[]>([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, r, w, pl] = await Promise.all([
        api<DiscoveryProviderInfo[]>("/discovery/providers"),
        api<DiscoveredJob[]>(`/discovery/jobs${platform ? `?platform=${encodeURIComponent(platform)}` : ""}`),
        api<DiscoveryWatch[]>("/discovery/watches"),
        api<DiscoveryPlatform[]>("/discovery/platforms"),
      ]);
      setProviders(p);
      setRows(r);
      setWatches(w);
      setPlatforms(pl);
    } catch (e) {
      setError(e);
      setProviders([]);
      setRows([]);
    }
  }, [platform]);

  useEffect(() => {
    load();
  }, [load]);

  const watching = watches.some((w) => !w.stopped && !w.paused_reason);
  useEffect(() => {
    if (!watching) return;
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [watching, load]);

  async function remove(r: DiscoveredJob) {
    setNotice(null);
    try {
      const out = await api<DiscoveryDeleteResult>(`/discovery/jobs/${r.id}`, { method: "DELETE" });
      setNotice(
        `Deleted “${r.title ?? "listing"}”; it will not be added again. ` +
          (out.job_deleted ? "Its job was removed too." : `Its job stays: ${out.job_kept_because}.`),
      );
      load();
    } catch (e) {
      setError(e);
    }
  }

  // S6 (D67): re-reads this one record at its source. Never a live read; the linked job is not
  // changed, only what the source says about it.
  async function refresh(r: DiscoveredJob) {
    setNotice(null);
    setError(null);
    try {
      const out = await api<{ outcome: "updated" | "unchanged" | "gone" }>(`/discovery/jobs/${r.id}/refresh`, {
        method: "POST",
      });
      const name = `“${r.title ?? "listing"}”`;
      setNotice(
        out.outcome === "gone"
          ? `${name} is no longer at the source. It stays here, marked as such; your job was not changed.`
          : out.outcome === "updated"
            ? `${name} changed at the source. Your job was not changed.`
            : `${name} is unchanged at the source.`,
      );
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function stop(w: DiscoveryWatch) {
    try {
      await api(`/discovery/watches/${w.id}/stop`, { method: "POST" });
      load();
    } catch (e) {
      setError(e);
    }
  }

  const enabled = providers?.filter((p) => p.enabled) ?? [];
  return (
    <>
      <h1 className="text-xl font-semibold">Discover jobs</h1>
      <p className="text-sm text-slate-600">
        Listings come from third-party sources. They are not verified, and nothing here means you are eligible, that an
        employer sponsors visas, or that NoEfforts can apply for you. Adding a job by link and spreadsheet import keep
        working whether or not a source is available.
      </p>
      <ErrorBox error={error} />
      {providers === null ? (
        <Loading />
      ) : (
        <Card title="Sources">
          <ul className="space-y-2 text-sm">
            {providers.map((p) => (
              <li key={p.name} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{p.label}</span>
                <Badge tone={p.enabled ? "green" : "slate"}>{p.enabled ? "enabled" : "disabled"}</Badge>
                <Badge tone="amber">{p.support_label}</Badge>
                <span className="text-slate-500">{p.status.note}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <BoardSources />
      {watches.length > 0 && <Watches watches={watches} onStop={stop} />}
      {enabled.length > 0 && <RunDiscovery providers={enabled} onDone={load} />}
      {notice && <Notice>{notice}</Notice>}
      <Card title={`Discovered (${rows?.length ?? 0})`}>
        {platforms.length > 0 && (
          <label className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-600">Application platform</span>
            <select
              aria-label="Application platform"
              className={`${inputCls} !w-auto`}
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
              <option value="">All ({platforms.reduce((n, p) => n + p.count, 0)})</option>
              {platforms.map((p) => (
                <option key={p.platform} value={p.platform}>
                  {p.label} ({p.count})
                </option>
              ))}
            </select>
          </label>
        )}
        {rows === null ? (
          <Loading />
        ) : rows.length === 0 ? (
          <Empty>Nothing discovered yet.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map((r) => (
              <DiscoveredRow key={r.id} r={r} onDelete={() => remove(r)} onRefresh={() => refresh(r)} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function Watches({ watches, onStop }: { watches: DiscoveryWatch[]; onStop: (w: DiscoveryWatch) => void }) {
  return (
    <Card title="Watched searches">
      <p className="mb-2 text-xs text-slate-500">
        Checked automatically, newest postings first; new ones are added to your jobs. Recorded with{" "}
        <code>python -m app.modules.discovery.watch</code>.
      </p>
      <ul className="space-y-2 text-sm">
        {watches.map((w) => {
          const state = w.stopped ? "stopped" : w.paused_reason ? `paused: ${w.paused_reason}` : "active";
          return (
            <li key={w.id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">“{w.query}”</span>
              <Badge tone={state === "active" ? "green" : state === "stopped" ? "slate" : "amber"}>{state}</Badge>
              <span className="text-slate-600">
                every {w.interval_seconds < 120 ? `${w.interval_seconds} s` : `${Math.round(w.interval_seconds / 60)} min`} until{" "}
                {new Date(w.not_after).toLocaleDateString()} · found {w.found_total}
                {w.last_checked_at ? ` · last check ${new Date(w.last_checked_at).toLocaleTimeString()} (${w.last_outcome})` : ""}
              </span>
              {state === "active" && (
                <Button variant="secondary" onClick={() => onStop(w)}>
                  Stop watching
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function RunDiscovery({ providers, onDone }: { providers: DiscoveryProviderInfo[]; onDone: () => void }) {
  const [provider, setProvider] = useState(providers[0].name);
  const [titles, setTitles] = useState("");
  const [cities, setCities] = useState("");
  const [query, setQuery] = useState("");
  const [sponsorship, setSponsorship] = useState("any");
  const [usePrefs, setUsePrefs] = useState(false);
  const [only, setOnly] = useState<string[]>([]);
  const [result, setResult] = useState<DiscoveryImportResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await api<DiscoveryImportResult>("/discovery/import", {
          json: {
            provider,
            titles: splitList(titles),
            cities: splitList(cities),
            query: query.trim() || null,
            sponsorship,
            use_preferences: usePrefs,
            platforms: only,
          },
        }),
      );
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Find jobs">
      <form onSubmit={submit} className="space-y-3">
        {providers.length > 1 && (
          <Field label="Source">
            <select className={inputCls} value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Titles" hint="Comma-separated. Matched against the listing's title.">
            <input className={inputCls} value={titles} onChange={(e) => setTitles(e.target.value)} />
          </Field>
          <Field label="Cities" hint="Listings without a location are kept and marked “not enough data”.">
            <input className={inputCls} value={cities} onChange={(e) => setCities(e.target.value)} />
          </Field>
        </div>
        <Field label="Search text" hint="Sent to the source's own search.">
          <input className={inputCls} value={query} onChange={(e) => setQuery(e.target.value)} />
        </Field>
        <Field label="Visa sponsorship" hint="Only what the source states. Unknown stays unknown.">
          <select className={inputCls} value={sponsorship} onChange={(e) => setSponsorship(e.target.value)}>
            <option value="any">Any</option>
            <option value="offered">Only listings that state sponsorship is offered</option>
          </select>
        </Field>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Application platform</legend>
          <p className="text-xs text-slate-500">
            Read from each listing&rsquo;s address. Tick one or more to keep only those listings; every one kept is added
            to your jobs. None ticked: every platform. A platform says nothing about whether NoEfforts can apply there.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {PLATFORM_CHOICES.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={only.includes(value)}
                  onChange={(e) => setOnly((cur) => (e.target.checked ? [...cur, value] : cur.filter((x) => x !== value)))}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={usePrefs} onChange={(e) => setUsePrefs(e.target.checked)} />
          Use my preferences for empty filters (titles, cities, work modes)
        </label>
        <ErrorBox error={error} />
        {result && (
          <Notice>
            {result.fetched} listings read ({result.pages} page{result.pages === 1 ? "" : "s"}
            {result.truncated ? `, stopped early: ${result.stop_reason}` : ""}): {result.created} new, {result.updated} changed,{" "}
            {result.unchanged} unchanged; {result.linked_new_jobs} added to your jobs, {result.linked_existing_jobs} already
            there; {result.incomplete} incomplete; {result.excluded_by_filters} filtered out; {result.insufficient_data} with
            not enough data; {result.malformed} unreadable.
          </Notice>
        )}
        <Button type="submit" disabled={busy}>{busy ? "Searching…" : "Find jobs"}</Button>
      </form>
    </Card>
  );
}

function DiscoveredRow({ r, onDelete, onRefresh }: { r: DiscoveredJob; onDelete: () => void; onRefresh: () => void }) {
  const sponsorship = r.source_facts.sponsorship_offered;
  return (
    <li className="space-y-1 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-900">{r.title ?? "Untitled listing"}</span>
        <Badge>Source: {r.provider_label}</Badge>
        <Badge tone="indigo">Platform: {r.platform_label}</Badge>
        <Credit a={r.attribution} />
        {r.stale && <Badge tone="amber">{r.stale_reason}</Badge>}
        {r.status === "incomplete" && <Badge tone="red">incomplete</Badge>}
        {r.job_signals?.application && (
          <Badge tone="indigo">
            Your application: {r.job_signals.application.state}
            {r.job_signals.application.outcome !== "none" ? ` · ${r.job_signals.application.outcome}` : ""}
          </Badge>
        )}
        {(r.job_signals?.possible_duplicates ?? 0) > 0 && <Badge tone="amber">Possible duplicate of a role you applied to</Badge>}
      </div>
      <p className="text-slate-600">
        {[r.employer, r.location, r.workplace !== "unknown" ? r.workplace : null, r.employment_type].filter(Boolean).join(" · ") ||
          "Details not provided"}
      </p>
      <p className="text-xs text-slate-500">
        Last seen {new Date(r.last_seen_at).toLocaleString()}
        {r.published_on ? ` · posted ${r.published_on}` : ""}
        {sponsorship ? ` · sponsorship: source ${SPONSORSHIP_TEXT[sponsorship.value]}${sponsorship.value !== "unknown" ? ` (${sponsorship.basis})` : ""}` : ""}
      </p>
      {(r.signal_lines?.length ?? 0) > 0 && (
        // D93: in the source's own terms, display-only; never used to match, approve or apply.
        <p className="text-xs text-slate-600" data-testid="source-signals">
          {r.provider_label} says: {r.signal_lines!.join(" · ")} <span className="text-slate-400">(not checked by NoEfforts)</span>
        </p>
      )}
      {r.missing.length > 0 && (
        <p className="text-xs text-red-700">
          Missing: {r.missing.join(", ")}. <Link className="underline" href="/jobs">Add it manually</Link>.
        </p>
      )}
      {r.filter?.result === "insufficient" && (
        <p className="text-xs text-amber-800">Not enough data to check: {r.filter.fields.join(", ")}.</p>
      )}
      {r.changed_fields.length > 0 && (
        <p className="text-xs text-slate-600">Changed at the source: {r.changed_fields.join(", ")}. Your job was not changed.</p>
      )}
      <div className="flex flex-wrap gap-3 text-xs">
        {r.job_id && (
          <Link className="text-indigo-700 underline" href={`/jobs/${r.job_id}`}>
            {LINK_TEXT[r.link_basis ?? "previous_link"] ?? "in your jobs"}
          </Link>
        )}
        {r.job_url && (
          <a className="break-all text-indigo-700 underline" href={r.job_url} target="_blank" rel="noopener noreferrer nofollow">
            Original listing
          </a>
        )}
        <button type="button" className="text-indigo-700 underline" onClick={onRefresh}>
          Refresh from source
        </button>
        <button type="button" className="text-red-700 underline" onClick={onDelete}>
          Delete
        </button>
      </div>
    </li>
  );
}
