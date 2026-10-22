"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Credit, Empty, ErrorBox, Field, inputCls, Loading, Notice, splitList } from "@/components/ui";
import { api, DiscoveredJob, DiscoveryImportResult, DiscoveryProviderInfo } from "@/lib/api";

const LINK_TEXT: Record<string, string> = {
  new_job: "added to your jobs",
  application_url: "already in your jobs (same application link)",
  job_url: "already in your jobs (same job link)",
  employer_title_location: "already in your jobs (same employer, title and location)",
  previous_link: "already in your jobs",
};

const SPONSORSHIP_TEXT = { yes: "says yes", no: "says no", unknown: "not stated" } as const;

export default function DiscoverPage() {
  const [providers, setProviders] = useState<DiscoveryProviderInfo[] | null>(null);
  const [rows, setRows] = useState<DiscoveredJob[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, r] = await Promise.all([
        api<DiscoveryProviderInfo[]>("/discovery/providers"),
        api<DiscoveredJob[]>("/discovery/jobs"),
      ]);
      setProviders(p);
      setRows(r);
    } catch (e) {
      setError(e);
      setProviders([]);
      setRows([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
      {enabled.length > 0 && <RunDiscovery providers={enabled} onDone={load} />}
      <Card title={`Discovered (${rows?.length ?? 0})`}>
        {rows === null ? (
          <Loading />
        ) : rows.length === 0 ? (
          <Empty>Nothing discovered yet.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map((r) => (
              <DiscoveredRow key={r.id} r={r} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function RunDiscovery({ providers, onDone }: { providers: DiscoveryProviderInfo[]; onDone: () => void }) {
  const [provider, setProvider] = useState(providers[0].name);
  const [titles, setTitles] = useState("");
  const [cities, setCities] = useState("");
  const [query, setQuery] = useState("");
  const [sponsorship, setSponsorship] = useState("any");
  const [usePrefs, setUsePrefs] = useState(false);
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

function DiscoveredRow({ r }: { r: DiscoveredJob }) {
  const sponsorship = r.source_facts.sponsorship_offered;
  return (
    <li className="space-y-1 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-900">{r.title ?? "Untitled listing"}</span>
        <Badge>Source: {r.provider_label}</Badge>
        <Credit a={r.attribution} />
        {r.stale && <Badge tone="amber">{r.stale_reason}</Badge>}
        {r.status === "incomplete" && <Badge tone="red">incomplete</Badge>}
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
      </div>
    </li>
  );
}
